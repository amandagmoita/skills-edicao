"""efeitos.py — biblioteca de efeitos visuais para Reels 1080x1920.

Engenharia reversa do Reel "17 video effects claude can create" (@tenfoldmarc).
Cada efeito é uma função que recebe o quadro original (+ recorte da pessoa) e devolve o quadro
novo. Serve pra qualquer skill de Reel: o aplicar.py roda em cima de um vídeo pronto, e o
compor.py do /reel-glow chama o Banco direto (chave "efeitos" do mapa).

Uso como biblioteca:
    import efeitos as FX
    banco = FX.Banco(lista, fps=30, pasta=Path("projeto"), cor="#F7E476", ancora=(540, 900))
    fr = banco.aplica(fr_rgba_1080x1920, t, n, mascara_L_ou_None)
    banco.janelas_mascara()      # [(t0, t1)] onde o efeito precisa do recorte da pessoa
    audio = FX.sintetiza(banco.eventos_som(), total_s, sr=48000)   # mono float

Item da lista: {"nome": "orbit", "ini": 3.2, "fim": 4.4, ...parâmetros}. Nomes e parâmetros:
dicionário CATALOGO no fim do arquivo (o SKILL.md repete em tabela).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from scipy import ndimage

W, H = 1080, 1920
AQUI = Path(__file__).resolve().parent
SUP = "/System/Library/Fonts/Supplemental/"
FONTES = {
    "poppins": (str(AQUI.parent / "assets" / "fonts" / "Poppins-Bold.ttf"), 0),
    "helv": ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    "helv_b": ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    "helv_m": ("/System/Library/Fonts/HelveticaNeue.ttc", 10),
    "helv_cb": ("/System/Library/Fonts/HelveticaNeue.ttc", 9),
    "didot": (SUP + "Didot.ttc", 0),
    "didot_i": (SUP + "Didot.ttc", 1),
    "didot_b": (SUP + "Didot.ttc", 2),
    "bodoni": (SUP + "Bodoni 72.ttc", 0),
    "bodoni_b": (SUP + "Bodoni 72.ttc", 2),
    "georgia": (SUP + "Georgia.ttf", 0),
    "georgia_b": (SUP + "Georgia Bold.ttf", 0),
    "georgia_i": (SUP + "Georgia Italic.ttf", 0),
    "times_b": (SUP + "Times New Roman Bold.ttf", 0),
    "courier_b": (SUP + "Courier New Bold.ttf", 0),
    "arial_black": (SUP + "Arial Black.ttf", 0),
    "impact": (SUP + "Impact.ttf", 0),
    "typewriter_b": (SUP + "AmericanTypewriter.ttc", 2),
    "futura_b": (SUP + "Futura.ttc", 4),
    "rockwell_b": (SUP + "Rockwell.ttc", 2),
    "mono": ("/System/Library/Fonts/SFNSMono.ttf", 0),
}


@lru_cache(None)
def fonte(nome: str, tam: int) -> ImageFont.FreeTypeFont:
    arq, i = FONTES[nome]
    return ImageFont.truetype(arq, tam, index=i)


# ------------------------------------------------------------------ tempo e curvas
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def rampa(u, a, b):
    return clamp((u - a) / (b - a)) if b > a else float(u >= a)


def eo(x):          # sai rápido, chega devagar
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ei(x):
    x = clamp(x)
    return x ** 3


def eio(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def volta(x, s=1.7):  # passa um pouco do ponto e volta (pop)
    x = clamp(x) - 1
    return 1 + x * x * ((s + 1) * x + s)


def hexcor(s) -> tuple:
    if isinstance(s, (list, tuple)):
        return tuple(s[:3])
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mistura(a, b, k):
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))


# ------------------------------------------------------------------ desenho
def caixa(w, h, r, fill, borda=None, lb=0, k=2) -> Image.Image:
    """Retângulo arredondado com borda lisa (desenha em 2x e reduz)."""
    w, h = max(2, int(w)), max(2, int(h))
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w * k - 1, h * k - 1), int(r * k), fill=fill,
                                         outline=borda, width=int(lb * k))
    return im.resize((w, h), Image.LANCZOS)


def arredonda(im: Image.Image, r: int) -> Image.Image:
    im = im.convert("RGBA")
    m = caixa(im.width, im.height, r, (255, 255, 255, 255)).getchannel("A")
    a = np.minimum(np.asarray(im.getchannel("A")), np.asarray(m))
    im.putalpha(Image.fromarray(a))
    return im


def texto(s: str, f: str, tam: int, cor, esp: float = 0.0) -> Image.Image:
    """Texto numa imagem justa (altura = ascendente + descendente). esp = espaçamento em fração do tamanho."""
    ft = fonte(f, tam)
    asc, desc = ft.getmetrics()
    cor = tuple(cor) + ((255,) if len(cor) == 3 else ())
    if not esp:
        w = int(ft.getlength(s) + tam * 0.25) + 8
        im = Image.new("RGBA", (w, asc + desc + 8), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((4, 4), s, font=ft, fill=cor, anchor="la")
        return im
    larg = [ft.getlength(c) for c in s]
    w = int(sum(larg) + esp * tam * max(0, len(s) - 1) + tam * 0.25) + 8
    im = Image.new("RGBA", (w, asc + desc + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 4.0
    for c, lw in zip(s, larg):
        d.text((x, 4), c, font=ft, fill=cor, anchor="la")
        x += lw + esp * tam
    return im


def quebra(s: str, f: str, tam: int, larg: int) -> list[str]:
    ft = fonte(f, tam)
    linhas, atual = [], ""
    for p in s.split():
        tenta = (atual + " " + p).strip()
        if ft.getlength(tenta) <= larg or not atual:
            atual = tenta
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def com_sombra(im: Image.Image, blur=20, alfa=0.45, dy=12) -> Image.Image:
    """Devolve a imagem com sombra embutida (mesmo centro, margem em volta)."""
    pad = blur * 2 + abs(dy)
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: int(v * alfa))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 255))
    sh.putalpha(a)
    out.paste(sh, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(im, (pad, pad))
    return out


def cola_xy(dest: Image.Image, im: Image.Image, x: int, y: int) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def cola(dest, im, cx, cy, esc=1.0, alfa=1.0, giro=0.0) -> None:
    if esc <= 0.01 or alfa <= 0.01:
        return
    if abs(esc - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.BICUBIC)
    if abs(giro) > 0.05:
        im = im.rotate(giro, Image.BICUBIC, expand=True)
    if alfa < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alfa)))
    cola_xy(dest, im, int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


def brilho(camada: Image.Image, halo=(255, 196, 0), forte=1.0) -> Image.Image:
    """Halo de luz em volta do que estiver desenhado na camada (glow). Blur em meia resolução."""
    a = camada.getchannel("A")
    pq = a.resize((camada.width // 2, camada.height // 2), Image.BILINEAR)
    out = Image.new("RGBA", camada.size, (0, 0, 0, 0))
    for raio, k in ((11, 0.55), (4, 0.85)):
        hh = pq.filter(ImageFilter.GaussianBlur(raio)).resize(camada.size, Image.BILINEAR)
        hh = hh.point(lambda v, k=k * forte: min(255, int(v * k * 1.6)))
        c = Image.new("RGBA", camada.size, tuple(halo) + (0,))
        c.putalpha(hh)
        out.alpha_composite(c)
    out.alpha_composite(camada)
    return out


def sombra_texto(im: Image.Image, blur=7, alfa=0.75) -> Image.Image:
    return com_sombra(im, blur, alfa, 3)


def transforma(im: Image.Image, s: float, px: float, py: float, dx=0.0, dy=0.0, fundo=None) -> Image.Image:
    """Escala s em torno de (px, py) e move esse ponto (dx, dy). Funciona em RGBA e L."""
    a = 1 / s
    c = px - (px + dx) * a
    f = py - (py + dy) * a
    if fundo is None:
        fundo = 0 if im.mode == "L" else (0, 0, 0, 255)
    return im.transform(im.size, Image.AFFINE, (a, 0, c, 0, a, f), Image.BILINEAR, fillcolor=fundo)


def escurece(im: Image.Image, k: float) -> Image.Image:
    """k=0 mantém, k=1 preto."""
    if k <= 0.001:
        return im
    a = np.asarray(im, np.float32)
    a[..., :3] *= (1 - k)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def desfoca(im: Image.Image, r: float) -> Image.Image:
    """Desfoque forte barato: reduz 4x, desfoca, volta."""
    pq = im.resize((im.width // 4, im.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(max(0.5, r / 4)))
    return pq.resize(im.size, Image.BILINEAR)


def tracejado(d: ImageDraw.ImageDraw, p0, p1, cor, larg=2, traco=12, vao=10) -> None:
    x0, y0 = p0
    x1, y1 = p1
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1:
        return
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    s = 0.0
    while s < L:
        e = min(L, s + traco)
        d.line((x0 + ux * s, y0 + uy * s, x0 + ux * e, y0 + uy * e), fill=cor, width=larg)
        s += traco + vao


def parcial(pts, k):
    """Primeiros k (0..1) do comprimento de uma polilinha."""
    if k <= 0:
        return pts[:1]
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    alvo = sum(seg) * clamp(k)
    out = [pts[0]]
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if alvo >= L:
            out.append(b)
            alvo -= L
        else:
            f = alvo / L if L else 0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            break
    return out


def check(d: ImageDraw.ImageDraw, cx, cy, r, cor, larg=4) -> None:
    d.line((cx - r * 0.45, cy + r * 0.02, cx - r * 0.1, cy + r * 0.38, cx + r * 0.5, cy - r * 0.35),
           fill=cor, width=larg, joint="curve")


# ------------------------------------------------------------------ pessoa (recorte)
def info_pessoa(m: Image.Image | None) -> dict | None:
    if m is None:
        return None
    a = np.asarray(m.resize((270, 480), Image.BILINEAR)) > 128
    linhas = np.where(a.sum(1) > 3)[0]
    if len(linhas) == 0:
        return None
    topo = int(linhas[0])
    faixa = a[topo:topo + 25]
    cols = np.where(faixa.any(0))[0]
    return {"topo": topo * 4, "cx": int(cols.mean() * 4) if len(cols) else W // 2,
            "base": int(linhas[-1]) * 4, "x0": int(np.where(a.any(0))[0][0]) * 4,
            "x1": int(np.where(a.any(0))[0][-1]) * 4}


def recorte(fr: Image.Image, m: Image.Image) -> Image.Image:
    im = fr.copy()
    im.putalpha(m)
    return im


def pessoa_na_frente(alterado: Image.Image, original: Image.Image, m: Image.Image | None) -> Image.Image:
    return alterado if m is None else Image.composite(original, alterado, m)


def sem_pessoa(fr: Image.Image, m: Image.Image | None) -> Image.Image:
    """Fundo sem a pessoa: preenche o buraco com a média borrada do entorno (convolução normalizada)."""
    if m is None:
        return fr
    k = 8
    sm = np.asarray(fr.convert("RGB").resize((W // k, H // k), Image.BILINEAR), np.float32)
    w = 1 - np.asarray(m.resize((W // k, H // k), Image.BILINEAR), np.float32) / 255
    w = ndimage.minimum_filter(w, 5)
    out = conf_acc = None
    for sig in (6, 18, 50):          # raio pequeno perto da borda, raio grande no meio do buraco
        num = ndimage.gaussian_filter(sm * w[..., None], (sig, sig, 0))
        den = ndimage.gaussian_filter(w, sig)[..., None]
        est = num / np.maximum(den, 1e-4)
        conf = np.clip(den * 4, 0, 1)
        if out is None:
            out, conf_acc = est, conf
        else:
            out = out * conf_acc + est * (1 - conf_acc)
            conf_acc = np.maximum(conf_acc, conf)
    fill = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR).convert("RGBA")
    md = m.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(6))
    return Image.composite(fill, fr, md)


# ------------------------------------------------------------------ contexto de um quadro
@dataclass
class Ctx:
    fr: Image.Image
    m: Image.Image | None
    u: float              # segundos desde o início do efeito
    d: float              # duração do efeito
    p: dict               # parâmetros do item
    n: int                # quadro global
    t: float              # tempo global
    fps: float
    cor: tuple
    halo: tuple
    pasta: Path
    cache: dict
    ancora: tuple | None = None
    info: dict | None = field(default=None)

    @property
    def rosto(self) -> tuple:
        """(x, y) do rosto: parâmetro > âncora do projeto > estimado pelo recorte (topo + 200)."""
        if "rosto" in self.p:
            return tuple(self.p["rosto"])
        if self.ancora:
            return tuple(self.ancora)
        if self.info:
            return (self.info["cx"], self.info["topo"] + 200)
        return (W // 2, 900)

    @property
    def topo(self) -> int:
        """Topo da cabeça (y)."""
        if "topo" in self.p:
            return int(self.p["topo"])
        if self.info:
            return self.info["topo"]
        return self.rosto[1] - 200


EFEITOS: dict[str, dict] = {}


def efeito(nome, mascara=True, rotulo="", saida=True, topo=False, rotulo_y=None):
    """topo=True: o efeito ocupa o alto da tela e esconde o título da série. rotulo_y: altura do rótulo no catálogo."""
    def dec(fn):
        EFEITOS[nome] = {"fn": fn, "mascara": mascara, "rotulo": rotulo, "saida": saida, "sons": None,
                         "topo": topo, "rotulo_y": rotulo_y}
        return fn
    return dec


def sons(nome):
    def dec(fn):
        EFEITOS[nome]["sons"] = fn
        return fn
    return dec


def imagens(c: Ctx, chave="imagens", minimo=6) -> list[Image.Image]:
    """Imagens do parâmetro (lista de arquivos ou uma pasta, relativo à pasta do projeto)."""
    if "_imgs" in c.cache:
        return c.cache["_imgs"]
    src = c.p.get(chave)
    arqs = []
    if isinstance(src, str):
        pp = (c.pasta / src)
        arqs = sorted(x for x in pp.iterdir() if x.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if pp.is_dir() else [pp]
    elif isinstance(src, list):
        arqs = [c.pasta / x for x in src]
    ims = [Image.open(a).convert("RGB") for a in arqs]
    if not ims:   # sem imagem: cartões coloridos genéricos
        cores = [(40, 44, 60), (72, 52, 90), (30, 70, 80), (90, 60, 40), (50, 50, 50), (80, 30, 50)]
        for i in range(minimo):
            im = Image.new("RGB", (400, 700), cores[i % len(cores)])
            ImageDraw.Draw(im).text((200, 350), "IA", font=fonte("poppins", 120), fill=(255, 255, 255), anchor="mm")
            ims.append(im)
    while len(ims) < minimo:
        ims = ims + ims
    c.cache["_imgs"] = ims
    return ims


def tempos_itens(p: dict, n: int, padrao: list) -> list:
    """Momento (s desde o início do efeito) em que cada item marca: "tempos" do mapa ou o padrão espalhado."""
    t = p.get("tempos")
    return [float(x) for x in t][:n] if t and len(t) >= n else padrao


def cartao_reel(img: Image.Image, w: int, h: int, r=22, borda=5) -> Image.Image:
    card = caixa(w, h, r, (255, 255, 255, 255))
    foto = arredonda(ImageOps.fit(img, (w - 2 * borda, h - 2 * borda), Image.LANCZOS).convert("RGBA"), r - borda)
    card.alpha_composite(foto, (borda, borda))
    return com_sombra(card, 14, 0.5, 10)


# ================================================================== 01 orbit
@efeito("orbit", rotulo="órbita")
def fx_orbit(c: Ctx) -> Image.Image:
    """Cartões (prints/reels) girando em volta do corpo em 3D: os de trás passam atrás da pessoa."""
    n = int(c.p.get("quantos", 6))
    if "cards" not in c.cache:
        ims = imagens(c, minimo=n)
        cw = int(c.p.get("largura", 200))
        c.cache["cards"] = [cartao_reel(ims[i], cw, int(cw * 1.78)) for i in range(n)]
    rx, ry = c.rosto
    cx, cy = rx, ry + c.p.get("altura", 260)
    Rx, Ry = c.p.get("raio", 420), c.p.get("inclina", 120)
    th0 = c.u * c.p.get("vel", 1.4) + c.p.get("fase", 0.6)
    atras, frente = [], []
    for i, card in enumerate(c.cache["cards"]):
        th = th0 + 2 * math.pi * i / n
        z = math.sin(th)
        x = cx + Rx * math.cos(th)
        y = cy + Ry * z
        esc = (0.74 + 0.30 * z) * volta(rampa(c.u, 0.03 * i, 0.03 * i + 0.3))
        item = (z, card, x, y, esc, -10 * math.cos(th), 0.75 + 0.25 * (z + 1) / 2)
        (atras if z < 0 else frente).append(item)
    bg = c.fr.copy()
    for z, card, x, y, esc, giro, alfa in sorted(atras, key=lambda a: a[0]):
        cola(bg, card, x, y, esc, alfa, giro)
    out = pessoa_na_frente(bg, c.fr, c.m)
    for z, card, x, y, esc, giro, alfa in sorted(frente, key=lambda a: a[0]):
        cola(out, card, x, y, esc, 1.0, giro)
    return out


@sons("orbit")
def s_orbit(p, d):
    return [(0.0, "whoosh", 0.5)] + [(0.03 * i + 0.05, "pop", 0.25) for i in range(int(p.get("quantos", 6)))]


# ================================================================== 02 parede
@efeito("parede", rotulo="parede de prints")
def fx_parede(c: Ctx) -> Image.Image:
    """A parede atrás da pessoa vai sendo coberta por prints/reels, um a um."""
    if "tiles" not in c.cache:
        cols = int(c.p.get("colunas", 4))
        gap = 16
        tw = (W - gap * (cols + 1)) // cols
        th = int(tw * 1.25)
        ate = int(c.p.get("ate", H))
        rng = np.random.default_rng(int(c.p.get("semente", 7)))
        linhas = math.ceil(ate / (th + gap))
        ims = imagens(c, minimo=cols * linhas)
        tiles = []
        k = 0
        for li in range(linhas):
            for co in range(cols):
                x = gap + co * (tw + gap) + tw / 2 + rng.uniform(-8, 8) + (tw / 2 if li % 2 else 0) - tw / 4
                y = gap + li * (th + gap) + th / 2 + rng.uniform(-8, 8)
                tl = cartao_reel(ims[k % len(ims)], tw, th, r=14, borda=4)
                tiles.append([x, y, tl, rng.uniform(-4, 4)])
                k += 1
        ordem = rng.permutation(len(tiles))
        janela = float(c.p.get("entra_em", 0.6))
        for j, i in enumerate(ordem):
            tiles[i].append(janela * j / len(tiles))
        c.cache["tiles"] = tiles
    bg = escurece(c.fr, 0.45)
    for x, y, tl, giro, t0 in c.cache["tiles"]:
        k = rampa(c.u, t0, t0 + 0.2)
        if k > 0:
            cola(bg, tl, x, y, 1.12 - 0.12 * volta(k), min(1, k * 2), giro)
    return pessoa_na_frente(bg, c.fr, c.m)


@sons("parede")
def s_parede(p, d):
    j = float(p.get("entra_em", 0.6))
    return [(0.0, "whoosh", 0.35)] + [(j * i / 8, "pop", 0.18) for i in range(8)]


# ================================================================== 03 ui
def _logo_claude(alt=56) -> Image.Image:
    t = texto("Claude", "georgia", alt, (61, 57, 41))
    r = alt * 0.42
    lado = int(r * 2 + 8)
    s = Image.new("RGBA", (lado * 2, lado * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for i in range(12):
        a = i * math.pi / 6
        d.line((lado, lado, lado + math.cos(a) * r * 2, lado + math.sin(a) * r * 2), fill=(217, 119, 87), width=int(alt * 0.16))
    s = s.resize((lado, lado), Image.LANCZOS)
    out = Image.new("RGBA", (s.width + 14 + t.width, max(s.height, t.height)), (0, 0, 0, 0))
    out.alpha_composite(s, (0, (out.height - s.height) // 2))
    out.alpha_composite(t, (s.width + 14, (out.height - t.height) // 2 + 4))
    return out


def _fundo_creme() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.35) / H) ** 2)
    base = np.array([245, 242, 234], np.float32)
    a = base[None, None, :] - (v[..., None] * 38)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


@efeito("ui", rotulo="mundo do app", topo=True, rotulo_y=980)
def fx_ui(c: Ctx) -> Image.Image:
    """O cenário vira a interface do Claude: a pessoa desce e a caixa de prompt se digita sozinha."""
    if "bg" not in c.cache:
        c.cache["bg"] = _fundo_creme()
        c.cache["logo"] = _logo_claude(54)
    k = eo(rampa(c.u, 0, 0.35))
    dy = c.p.get("desce", 360) * k
    frs = transforma(c.fr, 1, 0, 0, 0, dy)
    out = Image.blend(frs, c.cache["bg"], k) if c.m is not None else frs
    if c.m is not None:
        out = Image.composite(frs, out, transforma(c.m, 1, 0, 0, 0, dy))
    # caixa de prompt e logo descem junto com a tela
    sobe = -260 * (1 - k)
    logo = c.cache["logo"]
    cola(out, logo, W / 2, 150 + sobe, alfa=k)
    bw, bh, by = 960, 190, 260 + sobe
    caixa_p = caixa(bw, bh, 34, (255, 255, 255, 255), (226, 222, 212, 255), 2)
    d = ImageDraw.Draw(caixa_p)
    s = c.p.get("texto", "Edita meu reel no meu estilo")
    dig = rampa(c.u, 0.35, 0.35 + min(1.3, c.d * 0.55))
    vis = s[:int(round(len(s) * dig))]
    ft = fonte("helv", 40)
    d.text((44, 40), vis, font=ft, fill=(40, 38, 34), anchor="la")
    if dig < 1 or int(c.u * 2.6) % 2 == 0:
        x = 44 + ft.getlength(vis) + 4
        d.line((x, 42, x, 88), fill=(40, 38, 34), width=3)
    cinza = (130, 126, 116)
    d.line((52, 142, 72, 142), fill=cinza, width=3)
    d.line((62, 132, 62, 152), fill=cinza, width=3)
    for yy_ in (136, 148):
        d.line((100, yy_, 124, yy_), fill=cinza, width=3)
    pronto = dig >= 1
    bc = (217, 119, 87) if pronto else (30, 30, 30)
    d.ellipse((bw - 96, 112, bw - 40, 168), fill=bc)
    d.line((bw - 68, 156, bw - 68, 126), fill=(255, 255, 255), width=4)
    d.line((bw - 80, 138, bw - 68, 126, bw - 56, 138), fill=(255, 255, 255), width=4)
    cola(out, com_sombra(caixa_p, 18, 0.18, 8), W / 2, by + bh / 2, alfa=k)
    return out


@sons("ui")
def s_ui(p, d):
    s = p.get("texto", "Edita meu reel no meu estilo")
    dur = min(1.3, d * 0.55)
    ev = [(0.0, "whoosh", 0.45)] + [(0.35 + dur * i / len(s), "tecla", 0.22) for i in range(0, len(s), 2)]
    return ev + [(0.37 + dur, "clique", 0.4)]


# ================================================================== 04 moldura
@efeito("moldura", rotulo="saindo da moldura")
def fx_moldura(c: Ctx) -> Image.Image:
    """O vídeo encolhe pra um cartão arredondado e a cabeça escapa por cima da borda."""
    sf = c.p.get("escala", 0.64)
    k = eo(rampa(c.u, 0, 0.35))
    s = 1 - (1 - sf) * k
    rx, ry = c.rosto
    corte = c.p.get("corte", 40)          # topo do cartão em relação aos olhos (negativo = acima)
    fundo = escurece(desfoca(c.fr, 40), 0.55)
    esc = transforma(c.fr, s, W / 2, ry)
    x0, x1 = W / 2 - W * s / 2, W / 2 + W * s / 2
    topo_ini = ry - ry * s
    topo = topo_ini + ((ry + corte) - topo_ini) * k
    base = ry + (H - ry) * s - 30 * k
    cw, ch = int(x1 - x0), int(base - topo)
    out = fundo.copy()
    if cw > 10 and ch > 10:
        card = arredonda(esc.crop((int(x0), int(topo), int(x1), int(base))), int(44 * k))
        borda = caixa(cw, ch, int(44 * k), None, (255, 255, 255, 110), 3)
        card.alpha_composite(borda)
        cola_xy(out, com_sombra(card, 26, 0.6 * k, 18), int(x0) - 26 * 2 - 18, int(topo) - 26 * 2 - 18)
    if c.m is not None:
        out.alpha_composite(recorte(esc, transforma(c.m, s, W / 2, ry)))
    return out


@sons("moldura")
def s_moldura(p, d):
    return [(0.0, "whoosh", 0.45), (0.33, "impacto", 0.25)]


# ================================================================== 05 zoom
@efeito("zoom", mascara=False, rotulo="zoom digital", saida=False)
def fx_zoom(c: Ctx) -> Image.Image:
    """Punch-in rápido no rosto com tremidinha, aproxima um pouco mais e volta no fim."""
    S = c.p.get("escala", 1.35)
    k = eo(rampa(c.u, 0, 0.16))
    s = 1 + (S - 1) * k + 0.04 * rampa(c.u, 0.16, c.d)
    s = 1 + (s - 1) * (1 - eio(rampa(c.u, c.d - 0.14, c.d))) if c.p.get("volta", True) else s
    tr = c.p.get("tremor", 10) * (1 - rampa(c.u, 0, 0.35))
    rx, ry = c.rosto
    return transforma(c.fr, s, rx, ry, tr * math.sin(c.u * 90), tr * math.cos(c.u * 77))


@sons("zoom")
def s_zoom(p, d):
    return [(0.0, "impacto", 0.35), (0.0, "whoosh_curto", 0.3)]


# ================================================================== 06 celular
def _celular(c: Ctx, u: float) -> Image.Image:
    pw, ph = 440, 900
    if "corpo" not in c.cache:
        corpo = caixa(pw, ph, 74, (14, 14, 16, 255), (70, 70, 76, 255), 3)
        tela = caixa(pw - 32, ph - 32, 60, (19, 20, 24, 255))
        corpo.alpha_composite(tela, (16, 16))
        ImageDraw.Draw(corpo).rounded_rectangle((pw / 2 - 62, 34, pw / 2 + 62, 68), 17, fill=(0, 0, 0))
        c.cache["corpo"] = corpo
    im = c.cache["corpo"].copy()
    d = ImageDraw.Draw(im)
    d.text((48, 36), "9:41", font=fonte("helv_b", 24), fill=(255, 255, 255))
    y = 120
    for ln in quebra(c.p.get("titulo", "Edita meus clipes num reel"), "helv_b", 40, pw - 90):
        d.text((44, y), ln, font=fonte("helv_b", 40), fill=(255, 255, 255))
        y += 48
    d.text((44, y + 8), c.p.get("sub", "Claude · agora"), font=fonte("helv", 24), fill=(150, 150, 158))
    itens = c.p.get("itens", ["Melhores takes", "Legendas prontas", "Efeitos aplicados"])
    span = max(0.3, c.d - 0.9)
    y0 = y + 90
    for i, it in enumerate(itens):
        ti = tempos_itens(c.p, len(itens), [0.45 + k * span / (len(itens) + 0.5) for k in range(len(itens))])[i]
        ok = u >= ti
        cy = y0 + i * 86
        if ok:
            r = 22 * volta(rampa(u, ti, ti + 0.15))
            d.ellipse((66 - r, cy - r, 66 + r, cy + r), fill=c.cor)
            check(d, 66, cy, 20, (20, 20, 20), 4)
        else:
            d.ellipse((44, cy - 22, 88, cy + 22), outline=(90, 90, 96), width=3)
        d.text((108, cy), it, font=fonte("helv_m", 30), fill=(240, 240, 240) if ok else (160, 160, 168), anchor="lm")
    tb = (tempos_itens(c.p, len(itens), [0.45 + k * span / (len(itens) + 0.5) for k in range(len(itens))])[-1]
          + span / (len(itens) + 0.5))
    if u >= tb:
        aperta = 1 - 0.06 * math.sin(math.pi * rampa(u, tb + 0.2, tb + 0.4))
        bw, bh = int(340 * aperta), int(76 * aperta)
        bt = caixa(bw, bh, bh // 2, c.cor + (255,))
        bd = ImageDraw.Draw(bt)
        check(bd, bw / 2 - 66, bh / 2, 18, (20, 20, 20), 4)
        bd.text((bw / 2 + 14, bh / 2), c.p.get("botao", "Pronto"), font=fonte("helv_b", 32), fill=(20, 20, 20), anchor="mm")
        cola(im, bt, pw / 2, ph - 120, alfa=rampa(u, tb, tb + 0.12))
    return im


@efeito("celular", rotulo="celular")
def fx_celular(c: Ctx) -> Image.Image:
    """iPhone escuro entra pela lateral, inclinado, com checklist se marcando e botão Pronto."""
    k = eo(rampa(c.u, 0, 0.4))
    tel = com_sombra(_celular(c, c.u), 34, 0.6, 20)
    esc = c.p.get("escala", 0.8)
    lado = 1 if c.p.get("lado", "direita") == "direita" else -1
    cx = c.p.get("x", 810 if lado > 0 else 270) + lado * 760 * (1 - k)
    cy = c.p.get("y", c.rosto[1] - 120)
    giro = c.p.get("giro", 7 * lado) + 8 * lado * (1 - k)
    if c.p.get("atras", True):
        bg = c.fr.copy()
        cola(bg, tel, cx, cy, esc, 1, giro)
        return pessoa_na_frente(bg, c.fr, c.m)
    out = c.fr.copy()
    cola(out, tel, cx, cy, esc, 1, giro)
    return out


@sons("celular")
def s_celular(p, d):
    n = len(p.get("itens", [0, 0, 0]))
    span = max(0.3, d - 0.9)
    tis = tempos_itens(p, n, [0.45 + i * span / (n + 0.5) for i in range(n)])
    ev = [(0.0, "whoosh", 0.45)] + [(t, "pop", 0.3) for t in tis]
    return ev + [(tis[-1] + span / (n + 0.5) + 0.2, "clique", 0.4)]


# ================================================================== 07 checklist
@efeito("checklist", mascara=False, rotulo="checklist", topo=True)
def fx_checklist(c: Ctx) -> Image.Image:
    """Cartão escuro translúcido no canto: os itens ganham check um por um e a barra enche."""
    itens = c.p.get("itens", ["Solta seus clipes", "Chama a skill", "Posta"])
    n = len(itens)
    cw = 640
    chh = 118 + 84 * n
    span = max(0.3, c.d - 0.7)
    tis = tempos_itens(c.p, n, [0.4 + i * span / n for i in range(n)])
    feitos = sum(c.u >= t for t in tis)
    card = caixa(cw, chh, 30, (16, 16, 18, 215), (255, 255, 255, 34), 2)
    d = ImageDraw.Draw(card)
    d.ellipse((34, 38, 44, 48), fill=c.cor)
    d.text((56, 43), c.p.get("titulo", "EDITAR COM CLAUDE"), font=fonte("helv_b", 22), fill=(175, 175, 180), anchor="lm")
    d.text((cw - 34, 43), f"{feitos} de {n}", font=fonte("helv_m", 22), fill=(175, 175, 180), anchor="rm")
    gap = 10
    sw = (cw - 68 - gap * (n - 1)) / n
    for i, ti in enumerate(tis):
        x = 34 + i * (sw + gap)
        d.rounded_rectangle((x, 72, x + sw, 78), 3, fill=(64, 64, 68))
        f = eo(rampa(c.u, ti, ti + 0.2))
        if f > 0:
            d.rounded_rectangle((x, 72, x + sw * f, 78), 3, fill=c.cor)
    for i, (it, ti) in enumerate(zip(itens, tis)):
        cy = 132 + i * 84
        ok = c.u >= ti
        if ok:
            r = 21 * volta(rampa(c.u, ti, ti + 0.15))
            d.ellipse((58 - r, cy - r, 58 + r, cy + r), fill=c.cor)
            check(d, 58, cy, 19, (18, 18, 18), 4)
        else:
            d.ellipse((37, cy - 21, 79, cy + 21), outline=(110, 110, 116), width=3)
        d.text((100, cy), it, font=fonte("helv_b", 32), fill=c.cor if ok else (240, 240, 240), anchor="lm")
    k = eo(rampa(c.u, 0, 0.32))
    lado = c.p.get("lado", "esquerda")
    x = (40 if lado == "esquerda" else W - 40 - cw)
    x += (-700 if lado == "esquerda" else 700) * (1 - k)
    out = c.fr.copy()
    sh = com_sombra(card, 22, 0.45, 10)
    cola(out, sh, x + cw / 2, c.p.get("y", 230) + chh / 2, alfa=k)
    return out


@sons("checklist")
def s_checklist(p, d):
    n = len(p.get("itens", [0, 0, 0]))
    span = max(0.3, d - 0.7)
    return [(0.0, "whoosh", 0.4)] + [(t, "pop", 0.32) for t in tempos_itens(p, n, [0.4 + i * span / n for i in range(n)])]


# ================================================================== 08 manchetes
def _nota(it, cor) -> Image.Image:
    f = it.get("fonte", "georgia_b")
    tam = it.get("tam", 40)
    w = it.get("largura", 360)
    linhas = quebra(it["texto"], f, tam, w - 52)
    lh = int(tam * 1.18)
    im = Image.new("RGBA", (w, 52 + lh * len(linhas)), (250, 248, 242, 255))
    d = ImageDraw.Draw(im)
    ft = fonte(f, tam)
    dest = (it.get("destaque") or "").lower()
    for i, ln in enumerate(linhas):
        y = 26 + i * lh
        x = 26
        for pal in ln.split(" "):
            lw = ft.getlength(pal)
            if dest and dest in pal.lower():
                d.rectangle((x - 4, y + tam * 0.25, x + lw + 4, y + tam * 1.08), fill=cor + (210,))
            d.text((x, y), pal, font=ft, fill=(22, 22, 22))
            x += lw + ft.getlength(" ")
    fita = Image.new("RGBA", (120, 34), (236, 228, 205, 170))
    out = Image.new("RGBA", (im.width, im.height + 20), (0, 0, 0, 0))
    out.alpha_composite(im, (0, 20))
    cola(out, fita, im.width / 2, 22, giro=-4)
    return out


def _busca(it, cor) -> Image.Image:
    s = it["texto"]
    ft = fonte("helv", 30)
    w = int(ft.getlength(s)) + 110
    im = caixa(w, 74, 37, (255, 255, 255, 255), (220, 220, 225, 255), 2)
    d = ImageDraw.Draw(im)
    d.ellipse((26, 24, 46, 44), outline=(120, 120, 128), width=3)
    d.line((43, 41, 52, 50), fill=(120, 120, 128), width=3)
    x = 70
    dest = (it.get("destaque") or "").lower()
    for pal in s.split(" "):
        lw = ft.getlength(pal)
        if dest and dest in pal.lower():
            d.rectangle((x - 3, 22, x + lw + 3, 54), fill=cor + (220,))
        d.text((x, 37), pal, font=ft, fill=(30, 30, 34), anchor="lm")
        x += lw + ft.getlength(" ")
    return im


@lru_cache(maxsize=1)
def _perfil() -> dict:
    """Perfil do criador (~/.claude/padroes-edicao/perfil.json): nome e @ padrão do cartão de tweet."""
    import sys
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import perfil
    return perfil.carregar()


def _tweet(it, cor) -> Image.Image:
    w = it.get("largura", 400)
    linhas = quebra(it["texto"], "helv", 28, w - 56)
    hh = 96 + 36 * len(linhas) + 20
    im = caixa(w, hh, 22, (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((24, 24, 70, 70), fill=(205, 205, 212))
    d.text((84, 30), it.get("nome", _perfil()["nome"]), font=fonte("helv_b", 24), fill=(20, 20, 24))
    d.text((84, 58), it.get("arroba", "@" + _perfil()["instagram"]), font=fonte("helv", 20), fill=(130, 130, 140))
    for i, ln in enumerate(linhas):
        d.text((28, 92 + i * 36), ln, font=fonte("helv", 28), fill=(20, 20, 24))
    return im


def _tag(it, cor) -> Image.Image:
    t = texto(it["texto"].upper(), "helv_b", 22, (255, 255, 255), 0.12)
    im = caixa(t.width + 34, 50, 25, (14, 14, 16, 255))
    im.alpha_composite(t, (17, (50 - t.height) // 2 + 1))
    return im


CARTOES = {"nota": _nota, "busca": _busca, "tweet": _tweet, "tag": _tag}
MANCHETES_PADRAO = [
    {"tipo": "nota", "texto": "O Claude agora edita seus vídeos", "destaque": "edita"},
    {"tipo": "busca", "texto": "o claude edita vídeo?", "destaque": "claude"},
    {"tipo": "tweet", "texto": "O Claude editou esse reel inteiro. Eu só gravei."},
    {"tipo": "nota", "texto": "Cortou meu reel todo.", "fonte": "georgia_i", "largura": 300},
    {"tipo": "tag", "texto": "notícia de IA"},
]


@efeito("manchetes", rotulo="mural de manchetes")
def fx_manchetes(c: Ctx) -> Image.Image:
    """Recortes de notícia, busca e tweet grudando na parede atrás da cabeça, um de cada vez."""
    itens = c.p.get("itens", MANCHETES_PADRAO)
    if "cards" not in c.cache:
        c.cache["cards"] = [com_sombra(CARTOES[it.get("tipo", "nota")](it, c.cor), 14, 0.4, 8) for it in itens]
    cx, tp = c.rosto[0], c.topo
    slots = c.p.get("posicoes") or [(cx - 290, tp - 90, -4), (cx + 270, tp - 20, 3), (cx - 300, tp + 190, 3),
                                    (cx + 300, tp + 230, -3), (cx + 10, tp - 260, 1), (cx - 330, tp + 420, -2),
                                    (cx + 330, tp + 450, 2)]
    n = len(itens)
    passo = min(0.16, c.d * 0.6 / max(1, n))
    bg = c.fr.copy()
    for i, card in enumerate(c.cache["cards"]):
        x, y, g = slots[i % len(slots)]
        x = clamp(x, card.width / 2 - 30, W - card.width / 2 + 30)
        y = clamp(y, card.height / 2 + 10, H - card.height / 2 - 10)
        ti = i * passo
        k = rampa(c.u, ti, ti + 0.2)
        if k > 0:
            cola(bg, card, x, y, 1.25 - 0.25 * volta(k), min(1, k * 3), g)
    return pessoa_na_frente(bg, c.fr, c.m)


@sons("manchetes")
def s_manchetes(p, d):
    n = len(p.get("itens", MANCHETES_PADRAO))
    passo = min(0.16, d * 0.6 / max(1, n))
    return [(i * passo, "papel", 0.3) for i in range(n)]


# ================================================================== 09 mergulho
def _zoom_borrado(fr, s, ax, ay, rastro):
    acc = None
    nn = 4
    for j in range(nn):
        sj = s * (1 - rastro * j / nn)
        a = np.asarray(transforma(fr, max(1.0, sj), ax, ay), np.float32)
        acc = a if acc is None else acc + a
    return Image.fromarray((acc / nn).astype(np.uint8), "RGBA")


@efeito("mergulho", mascara=False, rotulo="zoom de passagem", saida=False)
def fx_mergulho(c: Ctx) -> Image.Image:
    """Transição: a câmera mergulha num ponto escuro até ficar preto e sai do preto no quadro seguinte."""
    ax, ay = c.p.get("alvo") or (c.rosto[0], c.rosto[1] + 420)
    h = c.d / 2
    if c.u < h:
        k = ei(c.u / h)
        out = _zoom_borrado(c.fr, 1 + 6 * k, ax, ay, 0.18 * k)
        return escurece(out, rampa(c.u, h * 0.5, h))
    k = eo((c.u - h) / h)
    out = _zoom_borrado(c.fr, 2.4 - 1.4 * k, W / 2, H / 2, 0.15 * (1 - k))
    return escurece(out, 1 - rampa(c.u, h, h + h * 0.4))


@sons("mergulho")
def s_mergulho(p, d):
    return [(0.0, "whoosh_longo", 0.55), (d / 2, "whoosh_curto", 0.35)]


# ================================================================== 10 grafico
@efeito("grafico", rotulo="gráfico subindo")
def fx_grafico(c: Ctx) -> Image.Image:
    """Grade no fundo, linha branca andando e de repente disparando pra cima em amarelo com brilho."""
    rx, ry = c.rosto
    if "grade" not in c.cache:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        for x in range(0, W, 96):
            d.line((x, 0, x, H), fill=(255, 255, 255, 48), width=2)
        for y in range(0, H, 96):
            d.line((0, y, W, y), fill=(255, 255, 255, 48), width=2)
        c.cache["grade"] = g
    by = c.p.get("y", ry + 130)
    brancos = [(70, by + 20), (240, by - 5), (400, by + 12), (565, by - 30)]
    pico = tuple(c.p.get("pico", (960, by - 600)))
    k1 = eio(rampa(c.u, 0.05, 0.4 * c.d))
    k2 = eo(rampa(c.u, 0.42 * c.d, 0.75 * c.d))
    bg = escurece(c.fr, 0.3 * rampa(c.u, 0, 0.2))
    grade = c.cache["grade"]
    if c.u < 0.2:
        grade = grade.copy()
        grade.putalpha(grade.getchannel("A").point(lambda v: int(v * rampa(c.u, 0, 0.2))))
    bg.alpha_composite(grade)
    cam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cam)
    pts = parcial(brancos, k1)
    if len(pts) > 1:
        d.line(pts, fill=(255, 255, 255, 240), width=6, joint="curve")
    for p in brancos:
        if pts and (p in pts[:-1] or p == pts[-1]) and (p[0] <= pts[-1][0]):
            d.ellipse((p[0] - 18, p[1] - 18, p[0] + 18, p[1] + 18), outline=(255, 255, 255, 110), width=3)
            d.ellipse((p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8), fill=(255, 255, 255, 255))
    if k2 <= 0 and len(pts):
        tx, ty = pts[-1]
        tracejado(d, (tx, ty), (W, ty), (255, 255, 255, 120), 2)
        d.line((tx, ty, tx, ty - 260), fill=(255, 255, 255, 140), width=2)
    amarelo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if k2 > 0:
        a0 = brancos[-1]
        tip = (a0[0] + (pico[0] - a0[0]) * k2, a0[1] + (pico[1] - a0[1]) * k2)
        area = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(area).polygon([a0, tip, (tip[0], by + 60), (a0[0], by + 60)], fill=c.cor + (55,))
        bg.alpha_composite(area)
        da = ImageDraw.Draw(amarelo)
        da.line([a0, tip], fill=c.cor + (255,), width=9)
        da.ellipse((tip[0] - 13, tip[1] - 13, tip[0] + 13, tip[1] + 13), fill=c.cor + (255,))
        pulso = (c.u * 2.2) % 1
        rr = 22 + 26 * pulso
        da.ellipse((tip[0] - rr, tip[1] - rr, tip[0] + rr, tip[1] + rr), outline=c.cor + (int(220 * (1 - pulso)),), width=4)
        tracejado(da, tip, (W, tip[1]), c.cor + (160,), 2)
        if c.p.get("valor") and k2 > 0.6:
            t = texto(c.p["valor"], "poppins", 76, c.cor)
            cola(amarelo, t, min(W - t.width / 2 - 20, tip[0]), tip[1] - 80, alfa=rampa(k2, 0.6, 1))
        amarelo = brilho(amarelo, c.halo)
    bg.alpha_composite(cam)
    bg.alpha_composite(amarelo)
    return pessoa_na_frente(bg, c.fr, c.m)


@sons("grafico")
def s_grafico(p, d):
    return [(0.05, "whoosh_curto", 0.3), (0.42 * d, "whoosh_sobe", 0.5), (0.75 * d, "ding", 0.4)]


# ================================================================== 11 recuo
@efeito("recuo", mascara=False, rotulo="recuo pra janela")
def fx_recuo(c: Ctx) -> Image.Image:
    """O vídeo encolhe e vira a prévia dentro da janela do Claude, com painel de etapas e barra renderizando."""
    if "bg" not in c.cache:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
        a = np.array([240, 238, 232], np.float32)[None, None, :] - v[..., None] * 70
        c.cache["bg"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
        rng = np.random.default_rng(3)
        c.cache["onda"] = rng.uniform(0.2, 1.0, 64)
    k = eo(rampa(c.u, 0, 0.45))
    sf = c.p.get("escala", 0.58)
    s = 1 - (1 - sf) * k
    cx, cy = W / 2 + 60 * k, H / 2 + 60 * k
    ww, wh = W * s, H * s
    x0, y0 = cx - ww / 2, cy - wh / 2
    out = c.cache["bg"].copy()
    jan = arredonda(c.fr.resize((int(ww), int(wh)), Image.BILINEAR), int(30 * k))
    barra_h = int(54 * k)
    if barra_h > 2:
        topo = caixa(int(ww), barra_h + 30, 30, (252, 252, 250, 255))
        dt = ImageDraw.Draw(topo)
        for i in range(3):
            dt.ellipse((24 + i * 26, barra_h / 2 - 7, 38 + i * 26, barra_h / 2 + 7), fill=(205, 205, 205))
        dt.text((ww - 24, barra_h / 2), "Claude", font=fonte("helv_m", 22), fill=(60, 60, 60), anchor="rm")
        jan_total = Image.new("RGBA", (int(ww), int(wh) + barra_h), (0, 0, 0, 0))
        jan_total.alpha_composite(topo, (0, 0))
        jan_total.alpha_composite(jan, (0, barra_h))
    else:
        jan_total = jan
    # barra "renderizando" dentro da janela, embaixo
    kr = rampa(c.u, 0.45, 0.6)
    if kr > 0:
        rw, rh = int(ww - 40), 74
        rb = caixa(rw, rh, 14, (250, 250, 248, int(235 * kr)))
        dr = ImageDraw.Draw(rb)
        dr.ellipse((16, 14, 26, 24), fill=(59, 108, 246))
        dr.text((34, 19), "renderizando", font=fonte("mono", 18), fill=(110, 110, 110), anchor="lm")
        prog = rampa(c.u, 0.5, c.d - 0.1)
        onda = c.cache["onda"]
        bw = (rw - 32) / len(onda)
        for i, v in enumerate(onda):
            x = 16 + i * bw
            hh_ = 6 + 22 * v
            on = (i + 1) / len(onda) <= prog
            dr.rectangle((x, 52 - hh_ / 2, x + bw * 0.6, 52 + hh_ / 2), fill=(59, 108, 246) if on else (200, 200, 205))
        jan_total.alpha_composite(rb, (20, jan_total.height - rh - 20))
    cola_xy(out, com_sombra(jan_total, 30, 0.35 * k, 16), int(x0) - 60 - 16, int(y0 - barra_h) - 60 - 16)
    # painel "Trabalhando em"
    itens = c.p.get("itens", ["Transcrevi a fala", "Cortei os takes", "Apliquei os efeitos", "Legendas prontas", "Cor e som"])
    kp = eo(rampa(c.u, 0.35, 0.6))
    if kp > 0:
        pw, ph = 380, 76 + 50 * len(itens)
        pn = caixa(pw, ph, 22, (255, 255, 255, 255))
        dp = ImageDraw.Draw(pn)
        dp.ellipse((22, 30, 32, 40), fill=(59, 108, 246))
        dp.text((42, 35), c.p.get("titulo", "Trabalhando em"), font=fonte("helv_m", 22), fill=(70, 70, 70), anchor="lm")
        span = max(0.4, c.d - 0.8)
        for i, it in enumerate(itens):
            ti = tempos_itens(c.p, len(itens), [0.55 + (k + 1) * span / (len(itens) + 1) for k in range(len(itens))])[i]
            yy = 84 + i * 50
            if c.u >= ti:
                dp.ellipse((22, yy - 13, 48, yy + 13), fill=(52, 168, 83))
                check(dp, 35, yy, 11, (255, 255, 255), 3)
                cor_t = (40, 40, 40)
            elif c.u >= ti - 0.7:   # girando um pouco antes de marcar
                a0 = (c.u * 540) % 360
                dp.arc((22, yy - 13, 48, yy + 13), a0, a0 + 270, fill=(120, 120, 120), width=3)
                cor_t = (40, 40, 40)
            else:
                dp.ellipse((22, yy - 13, 48, yy + 13), outline=(210, 210, 210), width=2)
                cor_t = (175, 175, 175)
            dp.text((62, yy), it, font=fonte("helv", 24), fill=cor_t, anchor="lm")
        cola(out, com_sombra(pn, 22, 0.25, 10), x0 + 40 - 260 * (1 - kp), y0 + 330, alfa=kp)
    return out


@sons("recuo")
def s_recuo(p, d):
    n = len(p.get("itens", [0] * 5))
    span = max(0.4, d - 0.8)
    return [(0.0, "whoosh", 0.45)] + [(t, "pop", 0.2) for t in tempos_itens(p, n, [0.55 + (i + 1) * span / (n + 1) for i in range(n)])]


# ================================================================== 12 chroma
def _midia(c: Ctx) -> Image.Image | None:
    src = c.p.get("midia")
    if not src:
        return None
    arq = c.pasta / src
    if arq.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        if "midia" not in c.cache:
            c.cache["midia"] = Image.open(arq).convert("RGBA")
        return c.cache["midia"]
    if "quadros" not in c.cache:   # vídeo: decodifica só o trecho usado, no tamanho do cartão
        import subprocess
        ini = float(c.p.get("midia_ini", 0))
        w, h = 460, 640
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ini}", "-t", f"{c.d + 0.2}", "-i", str(arq),
                              "-vf", f"fps={c.fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        n = len(raw) // (w * h * 3)
        c.cache["quadros"] = [Image.frombytes("RGB", (w, h), raw[i * w * h * 3:(i + 1) * w * h * 3]) for i in range(n)]
    q = c.cache["quadros"]
    return q[min(len(q) - 1, int(c.u * c.fps))].convert("RGBA") if q else None


@efeito("chroma", rotulo="fundo trocado", topo=True, rotulo_y=830)
def fx_chroma(c: Ctx) -> Image.Image:
    """Fundo some (vira escuro liso), a pessoa desce e um cartão no alto mostra outro vídeo/imagem."""
    fundo = hexcor(c.p.get("fundo", "#0E0F12"))
    if "bg" not in c.cache:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.3) / H) ** 2)
        a = np.array(fundo, np.float32)[None, None, :] + 18 * (1 - np.clip(v * 1.6, 0, 1))[..., None]
        c.cache["bg"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
    k = eo(rampa(c.u, 0, 0.3))
    rx, ry = c.rosto
    s = 1 - 0.18 * k
    dy = c.p.get("desce", 300) * k
    frs = transforma(c.fr, s, rx, ry, 0, dy)
    out = Image.blend(c.fr, c.cache["bg"], k)
    if c.m is not None:
        out.alpha_composite(recorte(frs, transforma(c.m, s, rx, ry, 0, dy)))
    med = _midia(c) or c.fr
    cw, ch = 460, 640
    card = arredonda(ImageOps.fit(med, (cw, ch), Image.LANCZOS).convert("RGBA"), 30)
    card.alpha_composite(caixa(cw, ch, 30, None, (255, 255, 255, 70), 3))
    k2 = eo(rampa(c.u, 0.12, 0.45))
    cola(out, com_sombra(card, 24, 0.55, 14), W / 2, 110 + ch / 2 - 760 * (1 - k2))
    return out


@sons("chroma")
def s_chroma(p, d):
    return [(0.0, "whoosh", 0.45), (0.3, "pop", 0.3)]


# ================================================================== 13 colagem
def _rasgado(w, h, cor, rng, k=2) -> Image.Image:
    pts = []
    for x in np.linspace(0, w, 18):
        pts.append((x, rng.uniform(0, 14)))
    for y in np.linspace(0, h, 24):
        pts.append((w - rng.uniform(0, 14), y))
    for x in np.linspace(w, 0, 18):
        pts.append((x, h - rng.uniform(0, 14)))
    for y in np.linspace(h, 0, 24):
        pts.append((rng.uniform(0, 14), y))
    im = Image.new("RGBA", (int(w * k), int(h * k)), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon([(x * k, y * k) for x, y in pts], fill=cor)
    return im.resize((int(w), int(h)), Image.LANCZOS)


def _giz(w, h, cor, rng, linhas=14, larg=8) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(linhas):
        y = h * (i + 0.5) / linhas
        d.line((rng.uniform(0, w * 0.15), y + rng.uniform(-6, 6), rng.uniform(w * 0.85, w), y + rng.uniform(-10, 10)),
               fill=cor, width=larg)
        if i < linhas - 1:
            d.line((rng.uniform(w * 0.85, w), y, rng.uniform(0, w * 0.15), y + h / linhas), fill=cor, width=larg - 2)
    ruido = Image.fromarray((rng.uniform(0, 1, (h, w)) > 0.35).astype(np.uint8) * 255)
    a = np.minimum(np.asarray(im.getchannel("A")), np.asarray(ruido))
    im.putalpha(Image.fromarray(a))
    return im


def _bilhete(titulo, rng) -> list:
    """Letras de bilhete de sequestro: cada uma num papel, fonte e giro diferentes."""
    fontes = ["didot_b", "georgia_b", "impact", "courier_b", "arial_black", "times_b", "typewriter_b", "rockwell_b", "futura_b"]
    papeis = [((250, 250, 247), (20, 20, 20)), ((20, 20, 20), (250, 250, 247)), ((200, 30, 45), (255, 255, 255)),
              ((30, 60, 185), (255, 255, 255)), ((242, 214, 75), (20, 20, 20)), ((215, 210, 198), (20, 20, 20))]
    out = []
    for ch in titulo:
        if ch == " ":
            out.append(None)
            continue
        f = fontes[rng.integers(len(fontes))]
        bgc, fc = papeis[rng.integers(len(papeis))]
        tam = int(rng.uniform(118, 150))
        t = texto(ch, f, tam, fc)
        bb = t.getbbox() or (0, 0, t.width, t.height)
        t = t.crop(bb)
        pad = int(rng.uniform(12, 22))
        tile = Image.new("RGBA", (t.width + 2 * pad, t.height + 2 * pad), bgc + (255,))
        tile.alpha_composite(t, (pad, pad))
        out.append(com_sombra(tile, 6, 0.35, 4).rotate(rng.uniform(-9, 9), Image.BICUBIC, expand=True))
    return out


@efeito("colagem", rotulo="colagem de papel", topo=True)
def fx_colagem(c: Ctx) -> Image.Image:
    """Scrapbook: papel, giz e letras recortadas no fundo; a pessoa vira adesivo com borda branca."""
    if "bg" not in c.cache:
        rng = np.random.default_rng(int(c.p.get("semente", 5)))
        papel = np.full((H, W, 3), (241, 238, 230), np.float32) + rng.normal(0, 4, (H, W, 1))
        bg = Image.fromarray(np.clip(papel, 0, 255).astype(np.uint8)).convert("RGBA")
        quad = Image.new("RGBA", (620, 760), (248, 248, 250, 255))
        dq = ImageDraw.Draw(quad)
        for x in range(0, 620, 38):
            dq.line((x, 0, x, 760), fill=(170, 195, 230), width=2)
        for y in range(0, 760, 38):
            dq.line((0, y, 620, y), fill=(170, 195, 230), width=2)
        cola(bg, com_sombra(quad, 10, 0.25, 6), 760, 1380, giro=3)
        cola(bg, com_sombra(_rasgado(560, 420, (201, 165, 110, 255), rng), 10, 0.3, 6), 230, 900, giro=-6)
        cola(bg, com_sombra(_rasgado(480, 360, (242, 214, 75, 255), rng), 10, 0.3, 6), 860, 780, giro=8)
        cola(bg, _giz(420, 260, (90, 110, 210, 210), rng), 300, 640, giro=-12)
        cola(bg, _giz(200, 300, (215, 70, 70, 220), rng, 10, 7), 900, 1180, giro=20)
        c.cache["bg"] = bg
        c.cache["letras"] = _bilhete(c.p.get("titulo", "RECORTE").upper(), rng)
    b = int(c.u * 8)                       # "stop motion": tudo treme 8 vezes por segundo
    jr = np.random.default_rng(b)
    out = c.cache["bg"].copy()
    letras = c.cache["letras"]
    palavras, atual = [], []
    for L in letras:
        if L is None:
            palavras.append(atual)
            atual = []
        else:
            atual.append(L)
    palavras.append(atual)
    y = c.p.get("y", 250)
    i = 0
    for pal in palavras:
        if not pal:
            continue
        larg = sum(L.width - 18 for L in pal)
        x = W / 2 - larg / 2
        alt = max(L.height for L in pal)
        for L in pal:
            k = rampa(c.u, 0.035 * i, 0.035 * i + 0.16)
            cola(out, L, x + L.width / 2 - 9 + jr.uniform(-2, 2), y + alt / 2 + jr.uniform(-2, 2) - 60 * (1 - k),
                 1.3 - 0.3 * volta(k), min(1, k * 3), jr.uniform(-1.5, 1.5))
            x += L.width - 18
            i += 1
        y += alt - 10
    if c.m is not None:
        rx, ry = c.rosto
        s = c.p.get("escala", 0.82)
        frs = transforma(c.fr, s, rx, H, W / 2 - rx, 0)
        ms = transforma(c.m, s, rx, H, W / 2 - rx, 0)
        borda = ms.filter(ImageFilter.MaxFilter(25)).filter(ImageFilter.GaussianBlur(1.5))
        adesivo = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        adesivo.putalpha(borda)
        adesivo = com_sombra(adesivo, 16, 0.35, 10)
        k = eo(rampa(c.u, 0, 0.25))
        pad = (adesivo.width - W) // 2
        cola_xy(out, adesivo, -pad + int(jr.uniform(-2, 2)), -pad + int(140 * (1 - k)))
        p = recorte(frs, ms)
        cola_xy(out, p, int(jr.uniform(-2, 2)), int(140 * (1 - k)))
    return Image.blend(c.fr, out, rampa(c.u, 0, 0.1)) if c.u < 0.1 else out


@sons("colagem")
def s_colagem(p, d):
    n = len(p.get("titulo", "RECORTE").replace(" ", ""))
    return [(0.0, "papel", 0.45)] + [(0.035 * i, "pop", 0.14) for i in range(0, n, 2)]


# ================================================================== 14 rabisco
def _coracao(cx, cy, s):
    t = np.linspace(0, 2 * math.pi, 60)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return [(cx + a * s / 32, cy + b * s / 32) for a, b in zip(x, y)]


def _brilho_estrela(cx, cy, r):
    pts = []
    for i in range(4):
        a = i * math.pi / 2 - math.pi / 2
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        a2 = a + math.pi / 4
        pts.append((cx + math.cos(a2) * r * 0.26, cy + math.sin(a2) * r * 0.26))
    return pts + pts[:1]


@efeito("rabisco", rotulo="rabisco vivo")
def fx_rabisco(c: Ctx) -> Image.Image:
    """Contorno de giz tremendo em volta da silhueta + coração e brilhos desenhados à mão."""
    if c.m is None:
        return c.fr
    b = int(c.u * 10)
    jr = np.random.default_rng(b)
    pq = np.asarray(c.m.resize((W // 2, H // 2), Image.BILINEAR)) > 128
    fora = ndimage.binary_dilation(pq, iterations=11)
    dentro = ndimage.binary_dilation(pq, iterations=8)
    anel = (fora & ~dentro).astype(np.float32)
    ruido = ndimage.zoom(jr.normal(0, 1, (2, 30, 17)), (1, 32, 32), order=1)[:, :H // 2, :W // 2]
    yy, xx = np.mgrid[0:H // 2, 0:W // 2].astype(np.float32)
    anel = ndimage.map_coordinates(anel, [yy + 2.5 * ruido[0], xx + 2.5 * ruido[1]], order=1)
    giz = jr.uniform(0.45, 1.0, anel.shape)
    alfa = np.clip(anel * giz * 255 * 1.3, 0, 255).astype(np.uint8)
    # revela girando em volta do centro do corpo
    inf = c.info or {"cx": W // 2, "topo": 600, "base": H}
    ang = (np.arctan2(yy - (inf["topo"] + inf["base"]) / 4, xx - inf["cx"] / 2) + math.pi) / (2 * math.pi)
    alfa = np.where(ang <= eio(rampa(c.u, 0, 0.35)), alfa, 0).astype(np.uint8)
    contorno = Image.new("RGBA", (W // 2, H // 2), (255, 255, 255, 0))
    contorno.putalpha(Image.fromarray(alfa))
    out = c.fr.copy()
    out.alpha_composite(contorno.resize((W, H), Image.BILINEAR))
    # rabiscos perto da cabeça
    cam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cam)
    cx, tp = c.rosto[0], c.topo
    j = lambda: jr.uniform(-3, 3)  # noqa: E731
    hx, hy = cx - c.p.get("afasta", 270), tp + 30
    sx, sy = cx + c.p.get("afasta", 270), tp - 10
    k1 = rampa(c.u, 0.15, 0.55)
    cor_c = hexcor(c.p.get("cor_coracao", "#F28DB2"))
    if rampa(c.u, 0.55, 0.8) > 0:   # preenchimento do coração em zigue-zague
        poly = _coracao(hx, hy, 120)
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).polygon(poly, fill=255)
        z = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dz = ImageDraw.Draw(z)
        f = rampa(c.u, 0.55, 0.8)
        for i in range(int(14 * f)):
            yl = hy - 50 + i * 8
            dz.line((hx - 70 + j(), yl + j(), hx + 70 + j(), yl + 6 + j()), fill=cor_c + (230,), width=7)
        cam.paste(z, (0, 0), m)
    d.line([(x + j(), y + j()) for x, y in parcial(_coracao(hx, hy, 120), k1)], fill=(255, 255, 255, 235), width=7, joint="curve")
    est = _brilho_estrela(sx, sy, 62)
    if k1 >= 1:
        d.polygon([(x + j(), y + j()) for x, y in est], fill=c.cor + (255,))
    d.line([(x + j(), y + j()) for x, y in parcial(est, k1)], fill=c.cor + (255,), width=6, joint="curve")
    est2 = _brilho_estrela(sx + 70, sy - 70, 26)
    d.line([(x + j(), y + j()) for x, y in parcial(est2, rampa(c.u, 0.4, 0.7))], fill=(255, 255, 255, 230), width=5)
    for i in range(3):   # risquinhos de "brilho" no coração
        a = -2.4 + i * 0.45
        p0 = (hx + math.cos(a) * 95, hy - 40 + math.sin(a) * 95)
        p1 = (hx + math.cos(a) * 125, hy - 40 + math.sin(a) * 125)
        if rampa(c.u, 0.5 + i * 0.05, 0.6 + i * 0.05) > 0:
            d.line((p0[0] + j(), p0[1] + j(), p1[0] + j(), p1[1] + j()), fill=(255, 255, 255, 230), width=5)
    out.alpha_composite(cam)
    return out


@sons("rabisco")
def s_rabisco(p, d):
    return [(0.0, "rabisco", 0.4), (0.5, "rabisco", 0.3)]


# ================================================================== 15 vertigo
@efeito("vertigo", rotulo="vertigo")
def fx_vertigo(c: Ctx) -> Image.Image:
    """Dolly zoom: o fundo avança enquanto a pessoa fica do mesmo tamanho."""
    rx, ry = c.rosto
    k = eio(rampa(c.u, 0, c.d))
    s = 1 + c.p.get("forca", 0.42) * k
    if c.m is None:
        return transforma(c.fr, s, rx, ry)
    fundo = transforma(sem_pessoa(c.fr, c.m), s, rx, ry)
    sp = 1 - 0.04 * k
    p = recorte(transforma(c.fr, sp, rx, H), transforma(c.m, sp, rx, H))
    fundo.alpha_composite(p)
    return fundo


@sons("vertigo")
def s_vertigo(p, d):
    return [(0.0, "whoosh_longo", 0.4)]


# ================================================================== 16 capa
@efeito("capa", rotulo="capa de revista", topo=True)
def fx_capa(c: Ctx) -> Image.Image:
    """Capa de revista: título serifado gigante atrás da cabeça, moldura fina e chamadas."""
    titulo = c.p.get("titulo", "STUDIO")
    if "titulo" not in c.cache:
        ff = c.p.get("fonte", "bodoni")   # Bodoni 72 Book: fino como a referência e com número de altura cheia
        tam = 300
        while fonte(ff, tam).getlength(titulo) > 980 and tam > 60:
            tam -= 6
        t = texto(titulo, ff, tam, (255, 255, 255))
        c.cache["titulo"] = t.crop(t.getbbox())
    t = c.cache["titulo"]
    yc = c.p.get("y", max(t.height / 2 + 60, c.topo - 60))   # cabeça cobre só a base das letras
    k = eo(rampa(c.u, 0, 0.42))
    vis = t.copy()
    corte = int(t.height * (1 - k))      # revela de baixo pra cima
    a = np.asarray(vis.getchannel("A")).copy()
    a[:corte] = 0
    vis.putalpha(Image.fromarray(a))
    bg = c.fr.copy()
    grad = np.zeros((H, W), np.float32)
    grad[:600] = np.linspace(0.45, 0, 600)[:, None]
    grad[H - 700:] = np.linspace(0, 0.6, 700)[:, None]
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sombra.putalpha(Image.fromarray((grad * 255 * rampa(c.u, 0, 0.25)).astype(np.uint8)))
    bg.alpha_composite(sombra)
    cola(bg, vis, W / 2, yc)
    out = pessoa_na_frente(bg, c.fr, c.m)
    d = ImageDraw.Draw(out)
    kb = eio(rampa(c.u, 0, 0.5))
    ins = 28
    perim = [(W / 2, ins), (W - ins, ins), (W - ins, H - ins), (ins, H - ins), (ins, ins), (W / 2, ins)]
    d.line(parcial(perim, kb), fill=(255, 255, 255, 230), width=2)
    ka = rampa(c.u, 0.3, 0.5)
    if ka > 0:
        yl = yc + t.height / 2 + 22
        e = texto(c.p.get("esq", "A EDIÇÃO DA IA"), "helv_m", 20, (255, 255, 255), 0.25)
        dd = texto(c.p.get("dir", "SEM EDITOR"), "helv_m", 20, (255, 255, 255), 0.25)
        cola(out, e, 70 + e.width / 2, yl, alfa=ka)
        cola(out, dd, W - 70 - dd.width / 2, yl, alfa=ka)
    kc = eo(rampa(c.u, 0.3, 0.85))
    if kc > 0:
        yb = c.p.get("y_chamada", H - 330)
        lab = texto(c.p.get("selo", "COMO FOI FEITO"), "helv_m", 18, (255, 255, 255), 0.25)
        d.line((70, yb - 30, 110, yb - 30), fill=(255, 255, 255), width=2)
        cola(out, lab, 70 + lab.width / 2, yb, alfa=kc)
        y = yb + 30
        for ln in quebra(c.p.get("chamada", "O Claude editou este reel"), "didot_i", 76, 900):
            tl = texto(ln, "didot_i", 76, (255, 255, 255))
            vis2 = tl.crop((0, 0, max(1, int(tl.width * kc)), tl.height))
            cola_xy(out, vis2, 66, int(y))
            y += 84
    return out


@sons("capa")
def s_capa(p, d):
    return [(0.0, "whoosh", 0.45), (0.3, "clique", 0.3)]


# ================================================================== 17 vidro
@efeito("vidro", rotulo="letra de vidro")
def fx_vidro(c: Ctx) -> Image.Image:
    """Letras 3D de vidro na parede atrás da cabeça, montando uma a uma (refração + borda de luz)."""
    s = c.p.get("texto", "CLAUDE")
    f = c.p.get("fonte", "arial_black")
    if "letras" not in c.cache:
        tam = 240
        while fonte(f, tam).getlength(s) > 940 and tam > 60:
            tam -= 6
        ft = fonte(f, tam)
        asc, desc = ft.getmetrics()
        x = (W - ft.getlength(s)) / 2
        letras = []
        for ch in s:
            m = Image.new("L", (int(ft.getlength(ch)) + 40, asc + desc + 20), 0)
            ImageDraw.Draw(m).text((20, 10), ch, font=ft, fill=255)
            letras.append((x - 20, m))
            x += ft.getlength(ch)
        c.cache["letras"] = letras
        c.cache["alt"] = asc + desc + 20
    alt = c.cache["alt"]
    yc = c.p.get("y", c.topo + 30)
    y0 = int(yc - alt / 2)
    faixa = (0, max(0, y0 - 80), W, min(H, y0 + alt + 80))
    fw, fh = faixa[2] - faixa[0], faixa[3] - faixa[1]
    M = Image.new("L", (fw, fh), 0)
    for i, (x, m) in enumerate(c.cache["letras"]):
        k = eo(rampa(c.u, 0.07 * i, 0.07 * i + 0.3))
        if k <= 0:
            continue
        mm = m if k >= 1 else m.point(lambda v, k=k: int(v * k))
        M.paste(Image.new("L", m.size, 255), (int(x), int(y0 - faixa[1] + 50 * (1 - k))), mm)
    Ma = np.asarray(M, np.float32) / 255
    bg = c.fr.copy()
    regiao = np.asarray(bg.crop(faixa), np.float32)
    out = regiao.copy()
    # profundidade (extrusão)
    prof = 14
    for j in range(prof, 0, -1):
        sh = ndimage.shift(Ma, (j * 1.0, j * 0.6), order=0)
        tom = 70 + 70 * (1 - j / prof)
        out[..., :3] = out[..., :3] * (1 - sh[..., None] * 0.9) + tom * sh[..., None] * 0.9
    # face de vidro: fundo borrado e deslocado (refração), clareado
    borr = np.asarray(Image.fromarray(regiao.astype(np.uint8), "RGBA").filter(ImageFilter.GaussianBlur(7)), np.float32)
    borr = np.roll(borr, (-8, -12), (0, 1))
    face = np.clip(borr[..., :3] * 1.08 + 38, 0, 255)
    out[..., :3] = out[..., :3] * (1 - Ma[..., None] * 0.92) + face * Ma[..., None] * 0.92
    # borda de luz em cima/esquerda e sombra embaixo/direita
    luz = np.clip(Ma - ndimage.shift(Ma, (4, 4), order=0), 0, 1)
    sombra = np.clip(Ma - ndimage.shift(Ma, (-4, -4), order=0), 0, 1)
    out[..., :3] = out[..., :3] * (1 - luz[..., None] * 0.85) + 255 * luz[..., None] * 0.85
    out[..., :3] = out[..., :3] * (1 - sombra[..., None] * 0.35)
    # reflexo diagonal que atravessa as letras
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float32)
    pos = (c.u / max(c.d, 0.01)) * (fw + fh) * 1.2 - fh
    faixa_luz = np.exp(-((xx + yy * 0.6 - pos) / 40) ** 2) * Ma * 0.5
    out[..., :3] = out[..., :3] + (255 - out[..., :3]) * faixa_luz[..., None]
    bg.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"), faixa[:2])
    return pessoa_na_frente(bg, c.fr, c.m)


@sons("vidro")
def s_vidro(p, d):
    n = len(p.get("texto", "CLAUDE"))
    return [(0.07 * i + 0.1, "vidro", 0.22) for i in range(n)]


# ================================================================== rótulos (catálogo / série)
def desenha_rotulo(fr: Image.Image, idx: int, total: int, nome: str, cor, y=1470) -> None:
    """Contador "01/17" + nome do efeito em amarelo, como na referência."""
    cont = sombra_texto(texto(f"{idx:02d}/{total:02d}", "helv_b", 30, (255, 255, 255)))
    nm = sombra_texto(texto(nome, "poppins", 92, cor), 9, 0.7)
    cola(fr, cont, W / 2, y)
    cola(fr, nm, W / 2, y + 74)


def desenha_serie(fr: Image.Image, titulo: str, sub: str, cor, y=150) -> None:
    t = sombra_texto(texto(titulo, "poppins", 80, cor), 9, 0.7)
    s = sombra_texto(texto(sub, "poppins", 46, (255, 255, 255)), 8, 0.7)
    cola(fr, t, W / 2, y)
    cola(fr, s, W / 2, y + 66)


# ================================================================== banco (lista de efeitos de um vídeo)
class Banco:
    def __init__(self, lista: list[dict], fps: float, pasta: Path, cor="#F7E476", halo=None,
                 ancora=None, rotulos=False, serie=None, saida_padrao=0.15):
        self.itens = []
        for i, it in enumerate(lista):
            if it["nome"] not in EFEITOS:
                raise SystemExit(f'efeito "{it["nome"]}" não existe. Opções: {", ".join(EFEITOS)}')
            self.itens.append({"p": it, "ini": float(it["ini"]), "fim": float(it["fim"]), "cache": {}, "i": i})
        self.fps = fps
        self.pasta = Path(pasta)
        self.cor = hexcor(cor)
        self.halo = hexcor(halo) if halo else mistura(self.cor, (255, 170, 0), 0.5)
        self.ancora = tuple(ancora) if ancora else None
        self.rotulos = rotulos
        self.serie = serie
        self.saida = saida_padrao

    def ativo(self, t):
        return next((it for it in self.itens if it["ini"] <= t < it["fim"]), None)

    def janelas_mascara(self) -> list[tuple]:
        return [(it["ini"] - 0.05, it["fim"] + 0.05) for it in self.itens if EFEITOS[it["p"]["nome"]]["mascara"]]

    def aplica(self, fr: Image.Image, t: float, n: int, m: Image.Image | None) -> Image.Image:
        it = self.ativo(t)
        out = fr
        if it:
            e = EFEITOS[it["p"]["nome"]]
            d = it["fim"] - it["ini"]
            c = Ctx(fr=fr, m=m if e["mascara"] else None, u=t - it["ini"], d=d, p=it["p"], n=n, t=t, fps=self.fps,
                    cor=self.cor, halo=self.halo, pasta=self.pasta, cache=it["cache"], ancora=self.ancora,
                    info=info_pessoa(m))
            out = e["fn"](c).convert("RGBA")
            sai = float(it["p"].get("saida", self.saida)) if e["saida"] else 0.0
            if sai > 0 and c.u > d - sai:
                out = Image.blend(fr, out, clamp((d - c.u) / sai))
            ent = float(it["p"].get("entrada", 0))
            if ent > 0 and c.u < ent:
                out = Image.blend(fr, out, clamp(c.u / ent))
            if self.rotulos:
                out = out.copy()
                desenha_rotulo(out, it["i"] + 1, len(self.itens), it["p"].get("rotulo", e["rotulo"]), self.cor,
                               it["p"].get("rotulo_y") or e["rotulo_y"] or 1470)
        if self.serie and not (it and EFEITOS[it["p"]["nome"]]["topo"]):
            out = out.copy() if out is fr else out
            desenha_serie(out, self.serie.get("titulo", ""), self.serie.get("sub", ""), self.cor)
        return out

    def eventos_som(self) -> list[tuple]:
        ev = []
        for it in self.itens:
            e = EFEITOS[it["p"]["nome"]]
            if e["sons"] and it["p"].get("som", True):
                for u, tipo, g in e["sons"](it["p"], it["fim"] - it["ini"]):
                    ev.append((it["ini"] + u, tipo, g))
        return ev


# ================================================================== sons sintetizados (sem arquivo)
SR = 48000


def _env(n, ataque=0.005, decai=20.0):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t * decai)


def _whoosh(d=0.5, f0=300, f1=2600, seed=0):
    n = int(d * SR)
    r = np.random.default_rng(seed).standard_normal(n)
    t = np.arange(n) / SR
    fc = f0 * (f1 / f0) ** (t / d)
    out = np.zeros(n)
    y1 = y2 = 0.0
    rr = 0.985
    for i in range(n):
        w = 2 * math.pi * fc[i] / SR
        y = r[i] * (1 - rr) + 2 * rr * math.cos(w) * y1 - rr * rr * y2
        out[i], y2, y1 = y, y1, y
    out *= np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2
    return out / (np.abs(out).max() + 1e-9)


def _mix(*partes):
    """Soma sons de durações diferentes (completa os curtos com silêncio)."""
    n = max(len(x) for x in partes)
    out = np.zeros(n)
    for x in partes:
        out[:len(x)] += x
    return out


def _tom(f, d, decai):
    n = int(d * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * _env(n, 0.002, decai)


@lru_cache(None)
def som(tipo: str) -> np.ndarray:
    rng = np.random.default_rng(abs(hash(tipo)) % 1000)
    if tipo == "whoosh":
        return _whoosh(0.45, 300, 2600)
    if tipo == "whoosh_curto":
        return _whoosh(0.22, 600, 3200, 2)
    if tipo == "whoosh_longo":
        return _whoosh(0.9, 200, 3500, 3)
    if tipo == "whoosh_sobe":
        return _whoosh(0.6, 400, 5000, 4)
    if tipo == "pop":
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        f = 1100 + (520 - 1100) * t / 0.09
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
    if tipo == "clique":
        n = int(0.04 * SR)
        return _mix(rng.standard_normal(n) * _env(n, 0.0005, 160) * 0.7, _tom(2400, 0.04, 120) * 0.5)
    if tipo == "tecla":
        n = int(0.03 * SR)
        return _mix(rng.standard_normal(n) * _env(n, 0.0003, 260), _tom(rng.uniform(1500, 2100), 0.03, 200) * 0.3)
    if tipo == "ding":
        return _mix(_tom(1760, 0.9, 5), _tom(2640, 0.9, 7) * 0.4, _tom(3520, 0.6, 9) * 0.2)
    if tipo == "vidro":
        return _mix(_tom(2900, 0.5, 9), _tom(4350, 0.4, 12) * 0.5, _tom(6100, 0.3, 16) * 0.25)
    if tipo == "impacto":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        corpo = np.sin(2 * np.pi * (48 + 60 * np.exp(-t * 18)) * t) * np.exp(-t * 7)
        return corpo + rng.standard_normal(n) * np.exp(-t * 90) * 0.5
    if tipo == "papel":
        n = int(0.35 * SR)
        r = rng.standard_normal(n)
        r = r - np.concatenate([[0], r[:-1]]) * 0.9          # agudo de papel
        am = (rng.uniform(0, 1, n // 400 + 1) > 0.5).repeat(400)[:n] * 0.7 + 0.3
        return r * am * _env(n, 0.01, 7)
    if tipo == "rabisco":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        r = rng.standard_normal(n)
        r = r - np.concatenate([[0], r[:-1]]) * 0.8
        return r * (0.5 + 0.5 * np.sin(2 * np.pi * 13 * t)) * np.sin(np.pi * t / 0.45)
    raise ValueError(tipo)


def sintetiza(eventos: list[tuple], total_s: float, sr: int = SR, ganho=0.5) -> np.ndarray:
    assert sr == SR
    out = np.zeros(int(total_s * sr) + sr)
    for t, tipo, g in eventos:
        s = som(tipo)
        s = s / (np.abs(s).max() + 1e-9)
        i = int(max(0, t) * sr)
        j = min(len(out), i + len(s))
        out[i:j] += s[:j - i] * g * ganho
    return out[:int(total_s * sr)]


CATALOGO = {nome: {"rotulo": e["rotulo"], "precisa_recorte": e["mascara"], "doc": (e["fn"].__doc__ or "").strip()}
            for nome, e in EFEITOS.items()}
