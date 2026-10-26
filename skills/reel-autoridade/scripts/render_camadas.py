#!/usr/bin/env python3
"""render_camadas.py — desenha TODAS as camadas visuais do estilo numa trilha RGBA.

Uso:
  python3 render_camadas.py <pasta_projeto>                 # render completo -> camadas.mov
  python3 render_camadas.py <pasta_projeto> --previa 1.2,8,15  # só PNGs compostos sobre o vídeo
  python3 render_camadas.py <pasta_projeto> --storyboard       # storyboard.html pro usuário aprovar ANTES do render

Lê: mapa.json, corte.json, palavras_corte.json, base_corte.mp4 (pra máscara e prévia).
Gera:
  camadas.mov        ProRes 4444 com alpha, 1080x1920, mesma duração do corte
  legendas.srt       legendas editáveis (CapCut)
  previa/*.png       com --previa: quadro do vídeo + camadas, pra conferir antes do render

Ordem das camadas (de baixo pra cima):
  número gigante e título em Didot (com a pessoa recortada por cima) → sticker → objeto do gancho
  → legenda → tela preta (opaca, com texto e objeto próprios)
"""
import argparse, json, math, os, random, re, shutil, subprocess, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # cor de destaque do criador (~/.claude/padroes-edicao/perfil.json)

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(AQUI, "..", "assets", "fonts", "Poppins-Bold.ttf")
W, H = 1080, 1920
BRANCO = (255, 255, 255)
# títulos atrás da cabeça: Didot Italic (escolhida entre Didot, Futura condensada e Bodoni). Fonte do sistema do Mac, índice 1 do .ttc = Italic.
FONTE_TITULO = ("/System/Library/Fonts/Supplemental/Didot.ttc", 1)


# ---------- utilidades ----------
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_back(x, s=1.9):
    x = min(max(x, 0.0), 1.0) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def fonte(px):
    return ImageFont.truetype(FONTE, int(px))


def limpa(w):
    return re.sub(r"[^\wÀ-ÿ%$]", "", w.lower())


def sombra(sprite, raio=9, desloc=(0, 5), opac=0.6):
    """Sombra suave embaixo do sprite (texto/imagem com alpha)."""
    m = 30
    tela = Image.new("RGBA", (sprite.width + 2 * m, sprite.height + 2 * m), (0, 0, 0, 0))
    a = sprite.getchannel("A").point(lambda v: int(v * opac))
    preto = Image.new("RGBA", sprite.size, (0, 0, 0, 255)); preto.putalpha(a)
    tela.alpha_composite(preto, (m + desloc[0], m + desloc[1]))
    tela = tela.filter(ImageFilter.GaussianBlur(raio))
    tela.alpha_composite(sprite, (m, m))
    return tela


def texto_sprite(txt, px, cor, tracking=0):
    """Altura = ascendente+descendente da fonte: toda palavra do mesmo tamanho divide a
    mesma linha de base, então palavras soltas ("a", "seus") alinham entre si."""
    f = fonte(px)
    asc, desc = f.getmetrics()
    x0, _, x1, _ = f.getbbox(txt)
    topo = int(asc * 0.18)  # corta o respiro de cima que a Poppins reserva para acentos altos
    img = Image.new("RGBA", (x1 - x0 + 4 + tracking * len(txt), asc + desc - topo + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = 2
        for ch in txt:
            d.text((x - x0, 2 - topo), ch, font=f, fill=cor)
            x += f.getlength(ch) + tracking
    else:
        d.text((2 - x0, 2 - topo), txt, font=f, fill=cor)
    return img


def cabe(sprite, largura):
    if sprite.width <= largura:
        return sprite
    k = largura / sprite.width
    return sprite.resize((int(sprite.width * k), int(sprite.height * k)), Image.LANCZOS)


def escala(sprite, k):
    if abs(k - 1) < 0.01:
        return sprite
    return sprite.resize((max(1, int(sprite.width * k)), max(1, int(sprite.height * k))), Image.BILINEAR)


def cola_centro(tela, sprite, cx, cy, alpha=1.0, giro=0.0):
    if giro:
        sprite = sprite.rotate(giro, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * max(alpha, 0))))
    x, y = int(cx - sprite.width / 2), int(cy - sprite.height / 2)
    # alpha_composite não aceita destino negativo: recorta
    sx, sy = max(0, -x), max(0, -y)
    if sx >= sprite.width or sy >= sprite.height or x >= W or y >= H:
        return
    if sx or sy:
        sprite = sprite.crop((sx, sy, sprite.width, sprite.height))
    tela.alpha_composite(sprite, (max(x, 0), max(y, 0)))


def carrega(proj, caminho):
    p = caminho if os.path.isabs(caminho) else os.path.join(proj, caminho)
    img = Image.open(p).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def ativo(lista, t):
    for e in lista:
        if e["ini"] <= t < e["fim"]:
            return e
    return None


# ---------- elementos ----------
class Render:
    def __init__(self, proj):
        self.P = proj
        self.mapa = json.load(open(os.path.join(proj, "mapa.json")))
        self.corte = json.load(open(os.path.join(proj, "corte.json")))
        self.palavras = json.load(open(os.path.join(proj, "palavras_corte.json")))
        self.fps = self.corte.get("fps", 30)
        self.total = self.corte["total"]
        self.cor = hex_rgb(self.mapa.get("cor", PERFIL["cor_destaque"]))
        self.cache = {}
        for k in ("numeros", "telas_pretas", "stickers", "legendas"):
            self.mapa.setdefault(k, [])
        self._fundo_preto()

    def rosto(self, t):
        for s in self.corte["segmentos"]:
            if s["ini"] <= t < s["fim"]:
                return s["rosto"]
        return self.corte["segmentos"][-1]["rosto"]

    # --- legenda: 2-4 palavras brancas; chave em caixa alta, na cor de destaque, maior, 2ª linha ---
    def legenda(self, tela, t):
        if ativo(self.mapa["telas_pretas"], t):
            return
        # título em destaque no ar = sem legenda (mais fluido)
        if ativo(self.mapa.get("titulos", []), t):
            return
        l = ativo(self.mapa["legendas"], t)
        if not l:
            return
        chave_cache = ("leg", l["ini"])
        if chave_cache not in self.cache:
            self.cache[chave_cache] = self.legenda_layout(l)
        itens = self.cache[chave_cache]
        if not itens:
            return
        r = self.rosto(t)
        # caixa do Vision vai da sobrancelha ao queixo: 1,25h caía no queixo; 1,75h é o peito
        cy = min(max(r["y"] + r["h"] * 1.75, H * 0.55), H * 0.72)
        # palavra por palavra: o lugar de cada palavra é o da frase inteira,
        # então nada "anda" quando a próxima entra; cada uma entra com pop no tempo da fala
        for spr, dx, dy, tw in itens:
            if t < tw:
                continue
            dt = t - tw
            k = 0.65 + 0.35 * ease_back(dt / 0.13)
            cola_centro(tela, escala(spr, k), W / 2 + dx, cy + dy, alpha=min(1.0, ease_out(dt / 0.08)))

    def legenda_layout(self, l):
        """[(sprite com sombra, dx, dy do centro do bloco, tempo em que a palavra entra)]"""
        cor1 = self.cor if l.get("rosa") else BRANCO
        linhas = []
        if l.get("texto"):
            linhas.append((l["texto"].split(), 68, cor1, int(W * 0.84)))
        if l.get("chave"):
            linhas.append((l["chave"].upper().split(), 112, self.cor, int(W * 0.88)))
        if not linhas:
            return []
        n_total = sum(len(ws) for ws, *_ in linhas)
        # tempo de cada palavra: as palavras do corte dentro do bloco, em ordem
        falas = [p for p in self.palavras if l["ini"] - 0.03 <= p["s"] < l["fim"]]
        if len(falas) >= n_total:
            tempos = [p["s"] for p in falas[:n_total]]
        else:  # contagem não bate: espalha no bloco
            dur = max(l["fim"] - l["ini"], 0.1)
            tempos = [l["ini"] + dur * 0.8 * i / max(n_total, 1) for i in range(n_total)]
        tempos[0] = min(tempos[0], l["ini"])
        sprites_linhas, k = [], 0
        for ws, px, cor, largmax in linhas:
            sprs = [texto_sprite(w, px, cor) for w in ws]
            esp = fonte(px).getlength(" ")
            larg = sum(sp.width for sp in sprs) + esp * (len(sprs) - 1)
            esc = min(1.0, largmax / larg)
            if esc < 1:
                sprs = [escala(sp, esc) for sp in sprs]; esp *= esc; larg *= esc
            sprites_linhas.append((sprs, esp, larg, tempos[k:k + len(ws)])); k += len(ws)
        gap = -6
        alt = sum(max(sp.height for sp in sl[0]) for sl in sprites_linhas) + gap * (len(sprites_linhas) - 1)
        itens, y = [], -alt / 2
        for sprs, esp, larg, ts in sprites_linhas:
            h = max(sp.height for sp in sprs)
            x = -larg / 2
            for sp, tw in zip(sprs, ts):
                itens.append((sombra(sp, raio=8, desloc=(0, 4), opac=0.65), x + sp.width / 2, y + h / 2, tw))
                x += sp.width + esp
            y += h + gap
        return itens

    # --- objeto 3D surgindo ATRÁS da cabeça (o celular e o globo do Reel do Belfort) ---
    def objeto_atras(self, tela, t, frame):
        if ativo(self.mapa["telas_pretas"], t):
            return
        it = ativo(self.mapa.get("objetos_atras", []), t)
        if not it:
            return
        key = ("atr", it["ini"])
        if key not in self.cache:
            img = carrega(self.P, it["imagem"])
            k = min(W * it.get("tamanho", 0.66) / img.width, H * 0.38 / img.height)
            img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
            self.cache[key] = sombra(img, raio=22, desloc=(0, 18), opac=0.45)
        spr = self.cache[key]
        dt, resto = t - it["ini"], it["fim"] - t
        p = ease_back(dt / 0.5, 1.3)
        sai = min(1.0, ease_out(resto / 0.2))
        r = self.rosto(t)
        # centro na altura da testa: metade de cima aparece, a de baixo some atrás da cabeça
        cx = r["x"] + r["w"] / 2 + W * it.get("dx", 0.0)
        cy_fim = r["y"] - r["h"] * it.get("alto", 0.10)
        cy = cy_fim + (1 - min(p, 1.0)) * spr.height * 0.55 + 8 * math.sin(dt * 2.0)
        giro = it.get("giro", 0) * min(p, 1.0) + 2 * math.sin(dt * 1.4)
        camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cola_centro(camada, escala(spr, max((0.55 + 0.45 * p) * sai, 0.01)), cx, cy,
                    alpha=min(1.0, ease_out(dt / 0.15)) * sai, giro=giro)
        mask = self.mascara(frame)
        if mask is not None:  # sempre atrás: a pessoa fica na frente
            camada.putalpha(ImageChops.multiply(camada.getchannel("A"), ImageChops.invert(mask)))
        tela.alpha_composite(camada)

    # --- número gigante listrado atrás da cabeça ---
    def numero_sprite(self, txt):
        m = re.match(r"^([\d.,+x%]+)(.*)$", txt)
        dig, suf = (m.group(1), m.group(2)) if m else (txt, "")
        a = texto_sprite(dig, 560, BRANCO, tracking=-10)
        b = texto_sprite(suf, 230, BRANCO) if suf.strip() else None
        larg = a.width + (b.width + 8 if b else 0)
        img = Image.new("RGBA", (larg, a.height), (0, 0, 0, 0))
        img.alpha_composite(a, (0, 0))
        if b:
            img.alpha_composite(b, (a.width + 8, a.height - b.height - 10))
        img = cabe(img, int(W * 0.9))
        # listras horizontais (persiana): 9 px cheios, 5 px vazios
        listra = Image.new("L", img.size, 0)
        d = ImageDraw.Draw(listra)
        for y in range(0, img.height, 14):
            d.rectangle((0, y, img.width, y + 8), fill=255)
        img.putalpha(ImageChops.multiply(img.getchannel("A"), listra))
        brilho = img.filter(ImageFilter.GaussianBlur(14))
        brilho.putalpha(brilho.getchannel("A").point(lambda v: int(v * 0.45)))
        out = Image.new("RGBA", (img.width + 60, img.height + 60), (0, 0, 0, 0))
        out.alpha_composite(brilho, (30, 30)); out.alpha_composite(img, (30, 30))
        return out

    def numero(self, tela, t, frame):
        n = ativo(self.mapa["numeros"], t)
        if not n:
            return
        key = ("num", n["texto"])
        if key not in self.cache:
            self.cache[key] = self.numero_sprite(n["texto"])
        spr = self.cache[key]
        dt, resto = t - n["ini"], n["fim"] - t
        k = (1.22 - 0.22 * ease_out(dt / 0.28)) * (1 + 0.04 * dt / max(n["fim"] - n["ini"], 0.1))
        alpha = min(ease_out(dt / 0.2), min(resto / 0.15, 1))
        r = self.rosto(t)
        cy = max(r["y"] + r["h"] * 0.35 - spr.height / 2, spr.height / 2 - 30)
        camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cola_centro(camada, escala(spr, k), W / 2, cy, alpha=alpha)
        mask = self.mascara(frame)
        if mask is not None:  # a pessoa fica NA FRENTE: buraco no número onde tem pessoa
            antes = camada.getchannel("A")
            depois = ImageChops.multiply(antes, ImageChops.invert(mask))
            if ("vis", n["ini"]) not in self.cache:
                soma = lambda im: sum(i * c for i, c in enumerate(im.histogram()))
                self.cache[("vis", n["ini"])] = soma(depois) / max(soma(antes), 1)
            # enquadramento fechado esconde o número quase todo: aí ele fica na frente
            if self.cache[("vis", n["ini"])] >= 0.35:
                camada.putalpha(depois)
        tela.alpha_composite(camada)

    # --- título em Didot itálico ATRÁS da cabeça (palavra de destaque) ---
    def titulo_sprite(self, item):
        def linha(txt, fonte_, cor):
            d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=fonte_)
            img = Image.new("RGBA", (x1 - x0 + 40, y1 - y0 + 40), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((20 - x0, 20 - y0), txt, font=fonte_, fill=cor)
            return img
        principal = linha(item["texto"], ImageFont.truetype(FONTE_TITULO[0], 300, index=FONTE_TITULO[1]),
                          self.cor if item.get("cor", "rosa") == "rosa" else BRANCO)
        principal = cabe(principal, int(W * 0.94))
        if principal.height > 250:
            principal = escala(principal, 250 / principal.height)
        partes = [principal]
        if item.get("sub"):
            partes.insert(0, cabe(linha(item["sub"], fonte(54), BRANCO), int(W * 0.8)))
        larg = max(p.width for p in partes)
        alt = sum(p.height for p in partes) - 10 * (len(partes) - 1)
        img = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
        y = 0
        for p in partes:
            img.alpha_composite(p, ((larg - p.width) // 2, y)); y += p.height - 10
        brilho = img.filter(ImageFilter.GaussianBlur(16))
        brilho.putalpha(brilho.getchannel("A").point(lambda v: int(v * 0.35)))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(brilho); out.alpha_composite(img)
        return sombra(out, raio=12, desloc=(0, 6), opac=0.5), principal.height

    def titulo(self, tela, t, frame):
        if ativo(self.mapa["telas_pretas"], t):
            return
        it = ativo(self.mapa.get("titulos", []), t)
        if not it:
            return
        key = ("tit", it["ini"])
        if key not in self.cache:
            self.cache[key] = self.titulo_sprite(it)
        spr, alt_principal = self.cache[key]
        dt, resto = t - it["ini"], it["fim"] - t
        p = ease_out(dt / 0.3)
        alpha = min(p, min(resto / 0.15, 1))
        k = 1.10 - 0.10 * p + 0.025 * dt  # entra encolhendo e segue crescendo devagar
        r = self.rosto(t)
        # só o terço de baixo da palavra grande passa por trás do cabelo: no 1º teste ela ficava
        # centrada no topo da cabeça e a cabeça cobria o meio ("advo…dos")
        topo_cabeca = r["y"] - r["h"] * 0.55
        cy = max(topo_cabeca + alt_principal * 0.30 - spr.height / 2, spr.height / 2 - 10) + 50 * (1 - p)
        camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cola_centro(camada, escala(spr, k), W / 2, cy, alpha=alpha)
        mask = self.mascara(frame)
        if mask is not None:
            antes = camada.getchannel("A")
            depois = ImageChops.multiply(antes, ImageChops.invert(mask))
            if ("visT", it["ini"]) not in self.cache:
                soma = lambda im: sum(i * c for i, c in enumerate(im.histogram()))
                self.cache[("visT", it["ini"])] = soma(depois) / max(soma(antes), 1)
            # palavra de destaque tem que LER: se a cabeça esconde mais de 15% ("advo…dos" nas
            # tomadas com zoom de 108%), o título passa na frente do cabelo
            if self.cache[("visT", it["ini"])] >= 0.85:
                camada.putalpha(depois)
        tela.alpha_composite(camada)

    def mascara(self, frame):
        p = os.path.join(self.P, "mascaras", f"{frame:06d}.png")
        if not os.path.exists(p):
            return None
        m = Image.open(p).convert("L").resize((W, H), Image.BILINEAR)
        return m.filter(ImageFilter.GaussianBlur(1.5))

    def prepara_mascaras(self, frames_alvo=None):
        """Extrai do base_corte só os quadros com número gigante e recorta a pessoa."""
        janelas = self.mapa["numeros"] + self.mapa.get("titulos", []) + self.mapa.get("objetos_atras", [])
        if not janelas:
            return
        md = os.path.join(self.P, "mascaras"); qd = os.path.join(self.P, "_quadros_num")
        shutil.rmtree(qd, ignore_errors=True); os.makedirs(qd); os.makedirs(md, exist_ok=True)
        base = os.path.join(self.P, "base_corte.mp4")
        for n in janelas:
            f0, f1 = int(n["ini"] * self.fps), int(math.ceil(n["fim"] * self.fps))
            if frames_alvo is not None:
                for f in [f for f in frames_alvo if f0 <= f <= f1]:
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{f / self.fps:.4f}", "-i", base,
                                    "-frames:v", "1", "-vf", "scale=540:960",
                                    os.path.join(qd, f"{f:06d}.jpg")], check=True)
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{f0 / self.fps:.4f}", "-i", base,
                            "-frames:v", str(f1 - f0 + 1), "-vf", "scale=540:960", "-start_number", str(f0),
                            os.path.join(qd, "%06d.jpg")], check=True)
        bin_ = os.path.join(AQUI, "bin", "visao")
        if not os.path.exists(bin_):
            os.makedirs(os.path.dirname(bin_), exist_ok=True)
            subprocess.run(["swiftc", "-O", os.path.join(AQUI, "visao.swift"), "-o", bin_], check=True)
        subprocess.run([bin_, "mascara", qd, md], check=True, capture_output=True)
        shutil.rmtree(qd, ignore_errors=True)

    # --- sticker com moldura tracejada acima da cabeça ---
    def sticker_sprite(self, caminho):
        lado = int(W * 0.2)
        img = carrega(self.P, caminho)
        k = (lado - 28) / max(img.width, img.height)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
        caixa = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        caixa.alpha_composite(img, ((lado - img.width) // 2, (lado - img.height) // 2))
        d = ImageDraw.Draw(caixa)
        traco, vazio, esp = 16, 10, 4
        for x in range(0, lado, traco + vazio):
            d.rectangle((x, 0, min(x + traco, lado), esp), fill=self.cor)
            d.rectangle((x, lado - esp - 1, min(x + traco, lado), lado), fill=self.cor)
        for y in range(0, lado, traco + vazio):
            d.rectangle((0, y, esp, min(y + traco, lado)), fill=self.cor)
            d.rectangle((lado - esp - 1, y, lado, min(y + traco, lado)), fill=self.cor)
        return sombra(caixa, raio=10, opac=0.45)

    def sticker(self, tela, t):
        s = ativo(self.mapa["stickers"], t)
        if not s:
            return
        key = ("stk", s["imagem"])
        if key not in self.cache:
            self.cache[key] = self.sticker_sprite(s["imagem"])
        spr = self.cache[key]
        dt, resto = t - s["ini"], s["fim"] - t
        k = ease_back(dt / 0.25) * min(1, ease_out(resto / 0.15))
        r = self.rosto(t)
        cy = r["y"] - r["h"] * 0.35 - spr.height * 0.5  # acima do cabelo, não na testa
        cx = r["x"] + r["w"] / 2
        if cy - spr.height / 2 < 40:  # sem espaço acima: vai pro lado da cabeça
            cy = r["y"] + spr.height * 0.4
            cx = r["x"] + r["w"] + spr.width * 0.45 if cx < W / 2 else r["x"] - spr.width * 0.45
        cx = min(max(cx, spr.width / 2 + 10), W - spr.width / 2 - 10)
        cola_centro(tela, escala(spr, max(k, 0.01)), cx, cy + 6 * math.sin(dt * 2 * math.pi * 0.7))

    # --- objeto do gancho: cai do alto girando e encaixa ao lado da cabeça ---
    def gancho(self, tela, t):
        g = self.mapa.get("objeto_gancho")
        if not g or not (g["ini"] <= t < g["fim"]):
            return
        key = ("gch", g["imagem"])
        if key not in self.cache:
            img = carrega(self.P, g["imagem"])
            larg = int(W * g.get("tamanho", 0.4))
            img = img.resize((larg, int(img.height * larg / img.width)), Image.LANCZOS)
            self.cache[key] = sombra(img, raio=16, desloc=(0, 14), opac=0.5)
        spr = self.cache[key]
        r = self.rosto(t)
        lado = g.get("lado", "direita")
        if lado == "acima":
            cx, cy = r["x"] + r["w"] / 2, r["y"] - r["h"] * 0.4 - spr.height * 0.5  # caixa começa na sobrancelha
        else:
            sinal = 1 if lado == "direita" else -1
            cx = r["x"] + r["w"] / 2 + sinal * (r["w"] * 0.5 + spr.width * 0.58)  # 0.45 encostava na bochecha
            cy = r["y"] + r["h"] * 0.45
        cx = min(max(cx, spr.width * 0.35), W - spr.width * 0.35)
        cy = max(cy, spr.height * 0.4)
        dt, resto = t - g["ini"], g["fim"] - t
        p = ease_back(dt / 0.5, 1.4)
        giro_final = g.get("giro", -15)
        y = -spr.height + (cy + spr.height) * p
        giro = giro_final + 40 * (1 - ease_out(dt / 0.5)) + 2 * math.sin(dt * 3)
        k = min(1, ease_out(resto / 0.18))
        cola_centro(tela, escala(spr, max(k, 0.01)), cx, y, giro=giro)

    # --- tela preta: granulado, vinheta, texto palavra a palavra e objeto 3D ---
    def _fundo_preto(self):
        base = Image.new("RGB", (W, H), (9, 9, 10))
        luz = Image.new("L", (W, H), 0)
        ImageDraw.Draw(luz).ellipse((-W * 0.2, H * 0.12, W * 1.2, H * 0.95), fill=255)
        luz = luz.filter(ImageFilter.GaussianBlur(260))
        base = Image.composite(Image.new("RGB", (W, H), (34, 34, 36)), base, luz)
        self.preto = base.convert("RGBA")
        rnd = random.Random(7)
        self.graos = []
        for _ in range(4):
            g = Image.effect_noise((W // 2, H // 2), 60).resize((W, H), Image.NEAREST)
            g = g.point(lambda v: int(v))
            gr = Image.new("RGBA", (W, H), (255, 255, 255, 0))
            gr.putalpha(g.point(lambda v: int(max(v - 128, 0) * 0.16)))
            self.graos.append(gr)
            rnd.random()

    def tela_preta(self, tela, t, frame):
        b = ativo(self.mapa["telas_pretas"], t)
        if not b:
            return
        tela.alpha_composite(self.preto)
        tela.alpha_composite(self.graos[frame % len(self.graos)])
        dt = t - b["ini"]
        # objeto: sobe girando e flutua
        if b.get("objeto"):
            key = ("obj", b["objeto"])
            if key not in self.cache:
                img = carrega(self.P, b["objeto"])
                k = min(W * 0.62 / img.width, H * 0.40 / img.height)
                img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
                self.cache[key] = sombra(img, raio=24, desloc=(0, 30), opac=0.7)
            spr = self.cache[key]
            p = ease_out(dt / 0.45)
            cola_centro(tela, spr, W / 2, H * 0.66 + 220 * (1 - p) + 10 * math.sin(dt * 2.2),
                        alpha=p, giro=-10 * (1 - p) + 3 * math.sin(dt * 1.3))
        # texto: as palavras do trecho entram quando são faladas
        key = ("tp", b["ini"])
        if key not in self.cache:
            dest = {limpa(x) for x in b.get("destaques", [])}
            ws = [p for p in self.palavras if b["ini"] - 0.05 <= p["s"] < b["fim"]]
            f = fonte(74)
            linhas, linha, larg = [], [], 0
            for p in ws:
                lw = f.getlength(p["w"] + " ")
                if linha and larg + lw > W * 0.78:
                    linhas.append(linha); linha, larg = [], 0
                linha.append((p, lw)); larg += lw
            if linha:
                linhas.append(linha)
            itens, y = [], H * 0.17
            for ln in linhas:
                total = sum(lw for _, lw in ln)
                x = (W - total) / 2
                for p, lw in ln:
                    cor = self.cor if limpa(p["w"]) in dest else BRANCO
                    itens.append((p, x, y, sombra(texto_sprite(p["w"], 74, cor), raio=6, opac=0.5)))
                    x += lw
                y += 92
            self.cache[key] = itens
        for p, x, y, spr in self.cache[key]:
            dp = t - (p["s"] - 0.04)
            if dp < 0:
                continue
            a = ease_out(dp / 0.12)
            sub = 14 * (1 - a)
            cola_centro(tela, spr, x + spr.width / 2 - 30, y + sub + spr.height / 2 - 30, alpha=a)

    # --- quadro completo ---
    def quadro(self, frame):
        t = frame / self.fps
        tela = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.objeto_atras(tela, t, frame)
        self.numero(tela, t, frame)
        self.titulo(tela, t, frame)
        self.sticker(tela, t)
        self.gancho(tela, t)
        self.legenda(tela, t)
        self.tela_preta(tela, t, frame)
        return tela


def srt(mapa, destino):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    with open(destino, "w") as f:
        for i, l in enumerate(mapa["legendas"], 1):
            txt = l["texto"] + ("\n" + l["chave"].upper() if l.get("chave") else "")
            f.write(f"{i}\n{ts(l['ini'])} --> {ts(l['fim'])}\n{txt.strip()}\n\n")


def storyboard(R, proj):
    """Uma página com cada momento da edição (quadro REAL: vídeo cortado + camadas, com o zoom punch
    das emendas) pro usuário aprovar antes do render. Gerador comum a todas as skills de Reels:
    ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, os.path.expanduser("~/.claude/padroes-edicao"))
    import storyboard as SB
    m = R.mapa
    cap = lambda t, fim: min(t, fim - 0.05)
    br = lambda x: f"{x:.2f}".replace(".", ",")

    def desc(it, *extra):
        partes = [SB.textos_do_spec(it)] + [(", ".join(map(str, it[k])) if isinstance(it[k], list) else str(it[k]))
                                            for k in extra if it.get(k)]
        img = it.get("imagem") or it.get("objeto")
        if img:
            partes.append("imagem: " + os.path.basename(img))
        return " — ".join(x for x in partes if x) or "—"

    ms = []
    g = m.get("objeto_gancho")
    if g:
        ms.append({"t0": g["ini"], "t1": g["fim"], "quadro": cap(g["ini"] + 0.9, g["fim"]),
                   "tipo": "Objeto do gancho caindo", "desc": desc(g, "lado")})
    for n in m.get("numeros", []):
        ms.append({"t0": n["ini"], "t1": n["fim"], "quadro": cap(n["ini"] + 0.5, n["fim"]),
                   "tipo": "Número gigante atrás da cabeça", "desc": desc(n)})
    for it in m.get("titulos", []):
        ms.append({"t0": it["ini"], "t1": it["fim"], "quadro": cap(it["ini"] + 0.5, it["fim"]),
                   "tipo": "Título Didot atrás da cabeça" + (" (cor de destaque)" if it.get("cor") == "rosa" else ""),
                   "desc": " ".join(x for x in (it.get("sub"), it.get("texto")) if x) or "—"})
    for it in m.get("objetos_atras", []):
        ms.append({"t0": it["ini"], "t1": it["fim"], "quadro": cap(it["ini"] + 0.7, it["fim"]),
                   "tipo": "Objeto 3D subindo atrás da cabeça", "desc": desc(it)})
    for st in m.get("stickers", []):
        ms.append({"t0": st["ini"], "t1": st["fim"], "quadro": cap(st["ini"] + 0.4, st["fim"]),
                   "tipo": "Sticker tracejado", "desc": desc(st)})
    for b in m.get("telas_pretas", []):
        ms.append({"t0": b["ini"], "t1": b["fim"], "quadro": cap(b["ini"] + 0.9, b["fim"]),
                   "tipo": "Tela preta com objeto", "desc": desc(b, "destaques")})
    for t in m.get("transicoes", []):
        ms.append({"t0": t, "t1": t, "quadro": t + 0.05, "tipo": "Zoom punch na emenda",
                   "desc": "a imagem dá um soco de zoom (1,16x) e volta em 0,28 s"})
    grandes = sorted([(x["ini"], x["fim"]) for k in ("numeros", "telas_pretas") for x in m.get(k, [])]
                     + ([(g["ini"], g["fim"])] if g else []))
    avisos = [f"efeitos grandes sobrepostos em {br(a1)}–{br(b0)} s (número, tela preta ou gancho)"
              for (a0, b0), (a1, b1) in zip(grandes, grandes[1:]) if a1 < b0]
    if len(m.get("objetos_atras", [])) > 4:
        avisos.append(f"{len(m['objetos_atras'])} objetos atrás da cabeça (máximo 4 por vídeo)")
    marcos = sorted(set([0.0, R.total] + [x["t0"] for x in ms]
                        + [sg["ini"] for sg in R.corte["segmentos"][1:]]))
    for a0, b0 in zip(marcos, marcos[1:]):
        if b0 - a0 > 4.0:
            avisos.append(f"{br(b0 - a0)} s sem efeito novo ({br(a0)}–{br(b0)} s): título, objeto ou punch")
    cenas = [{"t0": sg["ini"], "t1": sg["fim"],
              "fala": " ".join(p["w"] for p in R.palavras if sg["ini"] - 0.01 <= p["s"] < sg["fim"] - 0.01)}
             for sg in R.corte["segmentos"]]
    arqs = []
    for k in ("numeros", "titulos", "objetos_atras", "stickers", "telas_pretas"):
        for it in m.get(k, []):
            for a in (it.get("imagem"), it.get("objeto")):
                if a and a not in [x for x, _ in arqs]:
                    arqs.append((a, os.path.exists(a if os.path.isabs(a) else os.path.join(proj, a))))
    if g and g.get("imagem"):
        arqs.append((g["imagem"], os.path.exists(os.path.join(proj, g["imagem"]))))

    tempos = sorted(set(round(min(max(x["quadro"], 0), R.total - 0.05), 2) for x in ms)
                    | {round((c["t0"] + c["t1"]) / 2, 2) for c in cenas})
    R.prepara_mascaras([int(round(t * R.fps)) for t in tempos])
    punch = set(round(t, 2) for t in m.get("transicoes", []))
    jpg = os.path.join(proj, "_sb_base.jpg")

    def quadro(t):
        f = int(round(t * R.fps))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{f / R.fps:.4f}", "-i",
                        os.path.join(proj, "base_corte.mp4"), "-frames:v", "1", jpg], check=True)
        img = Image.open(jpg).convert("RGBA")
        if any(abs(t - p) < 0.3 for p in punch):   # o punch é do compor.py: simulado aqui (1,16x, foco no rosto)
            z = 1.16
            w2, h2 = int(W / z), int(H / z)
            x0, y0 = (W - w2) // 2, int((H - h2) * 0.33)
            img = img.crop((x0, y0, x0 + w2, y0 + h2)).resize((W, H), Image.LANCZOS)
        img.alpha_composite(R.quadro(f))
        return img

    out = SB.gerar(proj, "Autoridade", R.total, cenas, ms, quadro, avisos, arqs,
                   titulo=os.path.basename(os.path.abspath(proj)))
    if os.path.exists(jpg):
        os.remove(jpg)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto")
    ap.add_argument("--previa", help="tempos (s) separados por vírgula")
    ap.add_argument("--storyboard", action="store_true", help="storyboard.html pra aprovação antes do render")
    a = ap.parse_args()
    R = Render(a.projeto)

    if a.storyboard:
        storyboard(R, a.projeto)
        return

    if a.previa:
        tempos = [float(x) for x in a.previa.split(",")]
        frames = [int(round(x * R.fps)) for x in tempos]
        R.prepara_mascaras(frames)
        pd = os.path.join(a.projeto, "previa"); os.makedirs(pd, exist_ok=True)
        for f in frames:
            jpg = os.path.join(pd, "_base.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{f / R.fps:.4f}", "-i",
                            os.path.join(a.projeto, "base_corte.mp4"), "-frames:v", "1", jpg], check=True)
            img = Image.open(jpg).convert("RGBA")
            img.alpha_composite(R.quadro(f))
            img.convert("RGB").resize((540, 960)).save(os.path.join(pd, f"t{f / R.fps:06.2f}.jpg"), quality=88)
        os.remove(jpg)
        print("prévias ->", pd)
        return

    R.prepara_mascaras()
    srt(R.mapa, os.path.join(a.projeto, "legendas.srt"))
    n = int(round(R.total * R.fps))
    saida = os.path.join(a.projeto, "camadas.mov")
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                           "-s", f"{W}x{H}", "-r", str(R.fps), "-i", "-",
                           "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                           "-vendor", "apl0", saida], stdin=subprocess.PIPE)
    vazio = Image.new("RGBA", (W, H), (0, 0, 0, 0)).tobytes()
    for f in range(n):
        q = R.quadro(f)
        ff.stdin.write(vazio if q.getbbox() is None else q.tobytes())
        if f % 150 == 0:
            print(f"quadro {f}/{n}", flush=True)
    ff.stdin.close(); ff.wait()
    print("->", saida)


if __name__ == "__main__":
    sys.exit(main())
