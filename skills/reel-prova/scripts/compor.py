"""compor.py — monta o Reel no estilo "prova", quadro a quadro, a partir do mapa.json.

Estilo inspirado no Reel do @justyn.ai (ver referencia/referencias-estilo.md):
títulos animados sobre fundo chapado no gancho, o app aparece quando é citado, caixas de texto que
abrem e digitam, a prova do processo (vídeos, documentos, telas) no alto da tela, legenda karaokê
serifada e ritmo rápido.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_prova.mp4 | final_prova.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (do cortar.py), base_preview.mov
    (ou base_final.mov), masks/out/ (do mascaras.py), ícones em <skill>/assets/icones/

Camadas, de baixo pra cima (legenda SEMPRE por último):
  gancho: fundo chapado + títulos → pessoa recortada na frente
  resto:  base → títulos atrás da cabeça (pessoa na frente) → descida (a imagem desce e abre o palco
          quando uma prova/caixa precisa de espaço) → títulos na frente → apps → palco (caixas e
          provas) → borrão de transição → legenda
"""

from __future__ import annotations

import argparse
import functools
import itertools
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # nome, @ e produto do criador (~/.claude/padroes-edicao/perfil.json)

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("edit", type=Path)
_ap.add_argument("--so-quadros", default="")
_ap.add_argument("--final", action="store_true")
_ap.add_argument("--storyboard", action="store_true")
ARGS, _ = _ap.parse_known_args()
EDIT = ARGS.edit.resolve()
PASTA = EDIT.parent

W, H = 1080, 1920
SR = 48000

# ---------------------------------------------------------------- linha do tempo (igual reel-glow)
MAPA = json.loads((EDIT / "mapa.json").read_text())
_INFO = json.loads((EDIT / "base_info.json").read_text())
FPS_NUM, FPS_DEN = _INFO["fps"]
FPS = FPS_NUM / FPS_DEN
_EDL = json.loads((EDIT / "edl.json").read_text())["ranges"]
_ROFF = list(itertools.accumulate([0.0] + _INFO["duracoes"]))
_NG = max(r["grupo"] for r in _EDL) + 1
OFF = [min(_ROFF[i] for i, r in enumerate(_EDL) if r["grupo"] == g) for g in range(_NG)] + [_ROFF[-1]]
DURS = [OFF[g + 1] - OFF[g] for g in range(_NG)]
WORDS = [{"s": a, "e": b, "t": t, "seg": k} for a, b, t, k in json.loads((EDIT / "words_out.json").read_text())]
TOTAL = OFF[-1]
N_FRAMES = round(TOTAL * FPS)


def limpa(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


def acha(texto: str, grupo: int) -> int:
    alvo = limpa(texto)
    for i, w in enumerate(WORDS):
        if w["seg"] == grupo and limpa(w["t"]) == alvo:
            return i
    fala = " ".join(w["t"] for w in WORDS if w["seg"] == grupo)
    sys.exit(f'palavra "{texto}" não está na tomada {grupo}. Fala da tomada: {fala}')


def T(spec, fim: bool = False) -> float | None:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] | [palavra, tomada, atraso]."""
    if spec is None:
        return None
    if isinstance(spec, (int, float)):
        return float(spec)
    p, g = spec[0], int(spec[1])
    d = float(spec[2]) if len(spec) > 2 else 0.0
    w = WORDS[acha(p, g)]
    return (w["e"] if fim else w["s"]) + d


def fim_tomada(spec) -> float:
    return OFF[int(spec[1]) + 1] if isinstance(spec, list) else TOTAL


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    x = cl(x)
    return 1 - (1 - x) ** 3


def ease_in(x: float) -> float:
    x = cl(x)
    return x ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def mola(x: float) -> float:
    """back-out: passa um pouco do tamanho final e volta (entrada com 'mola')."""
    x = cl(x)
    c1 = 1.9
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ---------------------------------------------------------------- paleta e fontes
def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# escuro (fundo, caixas de legenda), claro (texto, cartões), destaque (palavra-chave)
PALETAS = {
    "floresta": ("#143026", "#EEEBDE", "#C9A96E"),   # a da referência (parede verde + latão)
    "cafe": ("#2A221C", "#F2ECE1", "#C9A46A"),
    "grafite": ("#18181A", "#F1EEE7", "#E2C15A"),
    "vinho": ("#3A1621", "#F4EAE4", "#D8A25E"),
    "marinho": ("#13213A", "#EEF0EC", "#D9B36C"),
}
_p = MAPA.get("paleta", "floresta")
_p = PALETAS[_p] if isinstance(_p, str) else (_p["escuro"], _p["claro"], _p["destaque"])
ESCURO, CLARO, DESTAQUE = (hexa(c) for c in _p)
VERMELHO = (226, 58, 76)
CINZA = tuple(int(a * 0.45 + b * 0.55) for a, b in zip(ESCURO, CLARO))   # palavra ainda não falada

_SUP = "/System/Library/Fonts/Supplemental/"
FONTES = {   # tipo: (arquivo, índice, nome esperado) — conferido no início (fonte errada cai em outra calada)
    "serifa": (_SUP + "Didot.ttc", 0, ("Didot", "Regular")),
    "italico": (_SUP + "Didot.ttc", 1, ("Didot", "Italic")),
    "sans": ("/System/Library/Fonts/Avenir Next.ttc", 8, ("Avenir Next", "Heavy")),
    "legenda": (_SUP + "Bodoni 72.ttc", 0, ("Bodoni 72", "Book")),
    "ui": ("/System/Library/Fonts/HelveticaNeue.ttc", 10, ("Helvetica Neue", "Medium")),
    "ui_bold": ("/System/Library/Fonts/HelveticaNeue.ttc", 1, ("Helvetica Neue", "Bold")),
    "ui_regular": ("/System/Library/Fonts/HelveticaNeue.ttc", 0, ("Helvetica Neue", "Regular")),
    "mono": ("/System/Library/Fonts/Menlo.ttc", 0, ("Menlo", "Regular")),
}
for _k, (_arq, _i, _nome) in FONTES.items():
    if ImageFont.truetype(_arq, 20, index=_i).getname() != _nome:
        sys.exit(f"fonte {_k}: esperava {_nome} em {_arq}[{_i}]")


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, i, _ = FONTES[tipo]
    return ImageFont.truetype(arq, max(6, int(size)), index=i)


# ---------------------------------------------------------------- layout
LAY = {"topo_cabeca": 300,      # y (px de 1080x1920) do topo do cabelo no take de fala
       "leg_y": 1180,           # centro da legenda (peito)
       "palco_topo": 70,        # topo das caixas e provas
       "descida_max": 520}
LAY.update(MAPA.get("layout", {}))
TOPO = LAY["topo_cabeca"]


def fundo_chapado() -> Image.Image:
    """Cor escura da paleta com uma luz suave no alto (não fica 'cor de PowerPoint')."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    luz = np.clip(1 - np.sqrt(((xx - W / 2) / (W * 0.9)) ** 2 + ((yy - H * 0.25) / (H * 0.7)) ** 2), 0, 1)
    base = np.array(ESCURO, np.float32)[None, None, :] * (0.88 + 0.22 * luz[..., None])
    rng = np.random.default_rng(3)
    base += rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")


FUNDO = fundo_chapado()


# ---------------------------------------------------------------- utilidades de desenho
def cola(dest: Image.Image, im: Image.Image, x: float, y: float) -> None:
    """alpha_composite que aceita imagem saindo pelas bordas (x, y = canto sup. esq.)."""
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def cola_centro(dest: Image.Image, im: Image.Image, cx: float, cy: float) -> None:
    cola(dest, im, cx - im.width / 2, cy - im.height / 2)


def com_alfa(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v, k=max(0.0, a): int(v * k)))
    return im


def sombra(im: Image.Image, raio: int = 18, forca: float = 0.35, dy: int = 10) -> Image.Image:
    """Devolve a imagem com sombra suave embaixo (canvas maior; o desenho fica centrado)."""
    m = raio * 2 + abs(dy)
    out = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    a = Image.new("L", out.size, 0)
    a.paste(im.getchannel("A"), (m, m + dy))
    a = a.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: int(v * forca))
    preto = Image.new("RGBA", out.size, (0, 0, 0, 255))
    preto.putalpha(a)
    out.alpha_composite(preto)
    out.alpha_composite(im, (m, m))
    return out


def ret_arred(w: int, h: int, r: int, cor) -> Image.Image:
    im = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=min(r, h // 2, w // 2), fill=cor)
    return im


def quebra_texto(txt: str, fonte: ImageFont.FreeTypeFont, larg: int) -> list[str]:
    linhas, cur = [], ""
    for p in txt.split():
        tst = (cur + " " + p).strip()
        if fonte.getlength(tst) <= larg or not cur:
            cur = tst
        else:
            linhas.append(cur)
            cur = p
    if cur:
        linhas.append(cur)
    return linhas


def luminancia(fr: Image.Image, box) -> float:
    return float(np.asarray(fr.crop(box).convert("L")).mean())


def mistura(c1, c2, k: float) -> tuple:
    return tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- base: leitura de quadros
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw).convert("RGBA")


@functools.lru_cache(maxsize=64)
def _quadro_cache(n: int) -> Image.Image:
    return quadro_base(n)


def mascara(n: int) -> Image.Image | None:
    p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
    if not p.exists():
        return None
    m = Image.open(p).convert("L")
    if m.size != (W, H):
        m = m.resize((W, H), Image.BILINEAR)
    return m.filter(ImageFilter.GaussianBlur(1.2))


def pessoa_na_frente(fr: Image.Image, fundo_alterado: Image.Image, n: int) -> Image.Image:
    m = mascara(n)
    if m is None:
        return fundo_alterado
    return Image.composite(fr, fundo_alterado, m)


# ================================================================ TÍTULOS ANIMADOS
# spec: {"linhas": ["QUANTO", "TEMPO"], "fonte": "serifa" | ["sans", "italico"], "anim": "letras" |
#        "mascara" | "rola" | "pop" | "seco", "em": [palavra, tomada], "ate": ..., "destaque": ["TEMPO"],
#        "destaque_em": [palavra, tomada], "faixa": false, "atras": true, "y": <base da última linha>,
#        "tamanho": px, "cor": "auto" | "claro" | "escuro", "alinha": "centro" | "esquerda"}
TAM_PADRAO = {"serifa": 230, "sans": 165, "italico": 150}
ENTRELINHA = {"serifa": 0.86, "sans": 0.84, "italico": 0.92}


class Titulo:
    def __init__(self, spec: dict, t0: float, t1: float, no_gancho: bool):
        self.spec = spec
        self.t0, self.t1 = t0, t1
        self.no_gancho = no_gancho
        self.anim = spec.get("anim", "letras")
        self.faixa = spec.get("faixa", False)
        self.atras = spec.get("atras", not self.faixa)
        self.saida = "corte" if no_gancho else spec.get("saida", "some")
        self.td = T(spec.get("destaque_em"))
        destaque = {limpa(x) for x in spec.get("destaque", [])}
        linhas = spec["linhas"]
        tipos = spec.get("fonte", "serifa")
        tipos = [tipos] * len(linhas) if isinstance(tipos, str) else tipos
        larg_max = spec.get("largura", 980)
        self.linhas = []
        for txt, tipo in zip(linhas, tipos):
            size = spec.get("tamanho", TAM_PADRAO[tipo])
            f = F(tipo, size)
            while f.getlength(txt) > larg_max and size > 40:
                size -= 6
                f = F(tipo, size)
            self.linhas.append({"txt": txt, "tipo": tipo, "f": f, "size": size})
        # empilha as linhas de baixo pra cima a partir da base da última linha
        # padrão: a base da última linha encosta no topo do cabelo (só a parte de baixo passa atrás)
        y_base = spec.get("y", TOPO + 40)
        for ln in reversed(self.linhas):
            ln["base"] = y_base
            l, t, r, b = ln["f"].getbbox(ln["txt"], anchor="ls")
            ln["top"], ln["bot"] = y_base + t, y_base + b
            y_base -= int(ln["size"] * ENTRELINHA[ln["tipo"]])
        topo = min(ln["top"] for ln in self.linhas)
        if topo < 56:   # título de 2 linhas grandes passaria do alto da tela: desce o bloco todo
            for ln in self.linhas:
                for k in ("base", "top", "bot"):
                    ln[k] += 56 - topo
        alinha = spec.get("alinha", "centro")
        k = 0
        for ln in self.linhas:
            # o espaço da Didot (sobretudo a itálica) é estreito demais em tamanho gigante: alarga
            extra = ln["size"] * (0.0 if ln["tipo"] == "sans" else 0.14)
            palavras = ln["txt"].split(" ")
            w = ln["f"].getlength(ln["txt"]) + extra * (len(palavras) - 1)
            ln["x0"] = (W - w) / 2 if alinha == "centro" else 60
            ln["w"] = w
            chars = []
            pos = 0
            for pi, p in enumerate(palavras):
                for j, ch in enumerate(p):
                    x = ln["x0"] + ln["f"].getlength(ln["txt"][:pos + j]) + extra * pi
                    chars.append({"ch": ch, "x": x, "k": k, "dest": limpa(p) in destaque and bool(limpa(p))})
                    k += 1
                pos += len(p) + 1
            ln["chars"] = chars
        self.n_chars = k
        self.stagger = min(0.06, 0.5 / max(1, k))
        self.cor_txt = CLARO
        self.top = min(ln["top"] for ln in self.linhas)
        self.bot = max(ln["bot"] for ln in self.linhas)

    def decide_cor(self, fr: Image.Image, n: int) -> None:
        """'auto': texto escuro se o FUNDO atrás do título for claro (parede clara). A pessoa fica de
        fora da conta (cabelo escuro no meio puxava a média pra baixo e o texto saía claro na parede clara)."""
        modo = self.spec.get("cor", "auto")
        if self.faixa or self.no_gancho or modo == "claro":
            self.cor_txt = CLARO
        elif modo == "escuro":
            self.cor_txt = ESCURO
        else:
            box = (40, max(0, int(self.top)), W - 40, min(H, int(self.bot)))
            lum = np.asarray(fr.crop(box).convert("L"), np.float32)
            m = mascara(n)
            if m is not None:
                fora = np.asarray(m.crop(box), np.float32) < 100
                lum = lum[fora] if fora.sum() > 500 else lum
            self.cor_txt = ESCURO if float(lum.mean()) > 150 else CLARO
        # sobre o vídeo (fora do fundo chapado e sem faixa) o título ganha sombra suave pra ler em
        # parede clara e teto escuro ao mesmo tempo
        self.sombra = not self.faixa and not self.no_gancho

    def _cor(self, c: dict, tipo: str) -> tuple:
        if c["dest"]:
            return DESTAQUE
        if self.faixa:
            return DESTAQUE if tipo == "italico" else CLARO
        return self.cor_txt

    def desenha(self, camada: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        u = t - self.t0
        # saída
        a_saida, dy_saida, sobe = 1.0, 0.0, 0.0
        if self.saida == "some":
            v = (self.t1 - t) / 0.18
            a_saida, dy_saida = ease_out(v), -18 * (1 - ease_out(v))
        elif self.saida == "sobe":
            sobe = ease_in(1 - (self.t1 - t) / 0.24) if self.t1 - t < 0.24 else 0.0
        bloco = None
        destino = camada
        if getattr(self, "sombra", False):
            camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if self.anim == "pop":
            bloco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            alvo = bloco
        else:
            alvo = camada
        for i, ln in enumerate(self.linhas):
            M = 100
            lh = int(ln["bot"] - ln["top"]) + 2 * M
            lyr = Image.new("RGBA", (W, lh), (0, 0, 0, 0))
            d = ImageDraw.Draw(lyr)
            base_local = ln["base"] - ln["top"] + M
            recorta = self.anim in ("mascara", "rola") or sobe > 0
            # faixa escura atrás da linha (estilo "BIGGER / captions.")
            if self.faixa:
                lf = ease_out((u - i * 0.12) / 0.16)
                if lf > 0:
                    x0 = ln["x0"] - 26
                    x1 = x0 + (ln["w"] + 52) * lf
                    d.rectangle((x0, M - 16, x1, lh - M + 18), fill=ESCURO + (int(240 * a_saida),))
            atraso_txt = i * 0.12 + (0.08 if self.faixa else 0)
            for c in ln["chars"]:
                cor = self._cor(c, ln["tipo"])
                if self.anim == "letras":
                    e = ease_out((u - c["k"] * self.stagger) / 0.18)
                    dy = 46 * (1 - e)
                elif self.anim in ("mascara", "rola"):
                    li = 0 if self.anim == "rola" else atraso_txt
                    e1 = ease_out((u - li) / 0.26)
                    e, dy = (1.0 if e1 > 0 else 0.0), (lh - 2 * M + 30) * (1 - e1)
                else:   # pop / seco
                    e, dy = 1.0, 0.0
                if self.faixa and self.anim not in ("letras",):
                    e = e * ease_out((u - atraso_txt) / 0.12)
                if c["dest"] and self.td is not None:
                    ed = ease_out((t - self.td) / 0.16)
                    e, dy = e * ed, dy + 26 * (1 - ed)
                if e <= 0.01:
                    continue
                dy += dy_saida - sobe * (lh - 2 * M + 30)
                d.text((c["x"], base_local + dy), c["ch"], font=ln["f"], fill=cor + (int(255 * e * a_saida),),
                       anchor="ls")
            if recorta:   # só aparece dentro da caixa da linha: sobe "de trás de uma máscara"
                lyr = lyr.crop((0, M - 14, W, lh - M + 14))
                cola(alvo, lyr, 0, ln["top"] - 14)
            else:
                cola(alvo, lyr, 0, ln["top"] - M)
        if bloco is not None:   # pop: o bloco todo entra grande e assenta
            s = 1.28 - 0.28 * ease_out(u / 0.2)
            a = ease_out(u / 0.12) * a_saida
            bb = bloco.getbbox()
            if bb:
                im = bloco.crop(bb)
                if abs(s - 1) > 0.003:
                    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
                cola_centro(camada, com_alfa(im, a), (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        if camada is not destino:   # sombra suave por baixo do título
            bb = camada.getbbox()
            if bb:
                x0, y0 = max(0, bb[0] - 40), max(0, bb[1] - 40)
                x1, y1 = min(W, bb[2] + 40), min(H, bb[3] + 40)
                pedaco = camada.crop((x0, y0, x1, y1))
                a = pedaco.getchannel("A").filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.55))
                sb = Image.new("RGBA", pedaco.size, (0, 0, 0, 255))
                sb.putalpha(a)
                destino.alpha_composite(sb, (x0, y0 + 4))
                destino.alpha_composite(pedaco, (x0, y0))


# gancho: fundo chapado + sequência de títulos; cada título dura até o próximo começar
GANCHO = MAPA.get("gancho")
G_FIM = 0.0
TIT_GANCHO: list[Titulo] = []
if GANCHO:
    G_FIM = T(GANCHO["ate"]) if GANCHO.get("ate") is not None else OFF[1]
    specs = GANCHO.get("titulos", [])
    inis = [T(s["em"]) for s in specs]
    for k, s in enumerate(specs):
        prox = specs[k + 1] if k + 1 < len(specs) else None
        t1 = inis[k + 1] if prox else G_FIM
        # o 1º título já está entrando no quadro 0 (é a capa do Reel no feed)
        t0 = min(inis[k] - 0.04, -0.25) if k == 0 else inis[k] - 0.04
        tt = Titulo(s, t0, t1, True)
        if prox and prox.get("anim") == "rola":
            tt.saida, tt.t1 = "sobe", t1 + 0.24
        TIT_GANCHO.append(tt)

TITULOS: list[Titulo] = []
for s in MAPA.get("titulos", []):
    t0 = T(s["em"]) - 0.04
    t1 = T(s["ate"]) if s.get("ate") is not None else t0 + s.get("dura", fim_tomada(s["em"]) - t0)
    TITULOS.append(Titulo(s, t0, t1, False))


def timecode(t: float) -> str:
    f = int((t % 1) * FPS)
    s = int(t)
    return f"00:00:{s:02d}:{f:02d}"


# ================================================================ APPS (ícone aparece quando é citado)
# spec: {"icones": [{"arquivo": "whatsapp", "nome": "WhatsApp", "em": [palavra, tomada]}], "risco": false,
#        "sai": {"em": [palavra, tomada], "modo": "cai" | "some"}, "ate": ..., "y": 200, "tamanho": 170}
@functools.lru_cache(maxsize=None)
def icone(arquivo: str, tam: int, nome: str, cor_rot: tuple) -> Image.Image:
    for p in (EDIT / "assets" / "icones" / f"{arquivo}.png", SKILL / "assets" / "icones" / f"{arquivo}.png"):
        if p.exists():
            break
    else:
        sys.exit(f'ícone "{arquivo}" não existe: rode icone_app.py "<nome do app>" {arquivo}')
    im = Image.open(p).convert("RGBA").resize((tam, tam), Image.LANCZOS)
    m = Image.new("L", (tam * 4, tam * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, tam * 4 - 1, tam * 4 - 1), radius=int(tam * 4 * 0.225), fill=255)
    im.putalpha(m.resize((tam, tam), Image.LANCZOS))
    if not nome:
        return sombra(im, 14, 0.35, 8)
    f = F("ui", int(tam * 0.16))
    lw = int(f.getlength(nome)) + 8
    out = Image.new("RGBA", (max(tam, lw), tam + int(tam * 0.28)), (0, 0, 0, 0))
    out.alpha_composite(im, ((out.width - tam) // 2, 0))
    ImageDraw.Draw(out).text((out.width / 2, tam + int(tam * 0.06)), nome, font=f, fill=cor_rot + (255,), anchor="mt")
    return sombra(out, 14, 0.35, 8)


class GrupoApps:
    def __init__(self, spec: dict):
        self.spec = spec
        self.tam = spec.get("tamanho", 170)
        self.y = spec.get("y", max(150, TOPO - 120))
        self.risco = spec.get("risco", False)
        self.itens = []
        for it in spec["icones"]:
            self.itens.append({"arq": it["arquivo"], "nome": it.get("nome", ""), "te": T(it["em"]),
                               "tr": T(it.get("risco_em")) if it.get("risco_em") else None})
        n = len(self.itens)
        passo = self.tam + spec.get("espaco", 46)
        for k, it in enumerate(self.itens):
            it["x"] = W / 2 + (k - (n - 1) / 2) * passo
        sai = spec.get("sai")
        self.modo_sai = sai.get("modo", "cai") if sai else "some"
        self.ts = T(sai["em"]) if sai else None
        ultimo = spec["icones"][-1]["em"]
        self.t0 = min(it["te"] for it in self.itens) - 0.05
        if self.ts is not None:
            self.t1 = self.ts + 0.75
        elif spec.get("ate") is not None:
            self.t1 = T(spec["ate"])
        else:
            # app citado no fim da frase sumia em 0,6 s (Meet em "reunião", 1º teste): fica no mínimo
            # 2 s depois do último ícone entrar, mas sai antes da próxima prova do palco aparecer
            te_ult = max(it["te"] for it in self.itens)
            self.t1 = max(fim_tomada(ultimo), te_ult + spec.get("minimo", 2.0))
            proximas = [e.t0 for e in PALCO if e.t0 > te_ult]
            if proximas:
                self.t1 = min(self.t1, max(fim_tomada(ultimo), min(proximas) - 0.05))
        self.cor_rot = CLARO

    def desenha(self, camada: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        for k, it in enumerate(self.itens):
            u = t - it["te"]
            if u < 0:
                continue
            esc = 0.35 + 0.65 * mola(u / 0.3)
            alfa = ease_out(u / 0.08)
            ang, dx, dy = 0.0, 0.0, 0.0
            if self.ts is not None and self.modo_sai == "cai":
                v = t - (self.ts + k * 0.07)
                if v > 0:
                    lado = -1 if k % 2 == 0 else 1
                    ang, dx, dy = lado * 80 * v, lado * 70 * v, 2400 * v * v
                    alfa *= 1 - cl((v - 0.3) / 0.25)
            elif self.modo_sai == "some" or self.ts is not None:
                fim = self.ts + 0.2 if self.ts is not None else self.t1
                alfa *= ease_out((fim - t) / 0.15)
            if alfa <= 0.01:
                continue
            im = icone(it["arq"], self.tam, it["nome"], self.cor_rot).copy()
            if self.risco or it["tr"] is not None:
                tr = it["tr"] if it["tr"] is not None else it["te"] + 0.32
                v = ease_out((t - tr) / 0.16)
                if v > 0:
                    d = ImageDraw.Draw(im)
                    m = (im.width - self.tam) / 2
                    cx, cy = im.width / 2, m * 0 + (im.height - self.tam * 0.28) / 2
                    p0 = (cx - self.tam * 0.48, cy - self.tam * 0.36)
                    p1 = (cx + self.tam * 0.48, cy + self.tam * 0.36)
                    pv = (p0[0] + (p1[0] - p0[0]) * v, p0[1] + (p1[1] - p0[1]) * v)
                    d.line((p0, pv), fill=(255, 255, 255, 255), width=17)
                    d.line((p0, pv), fill=VERMELHO + (255,), width=11)
            if abs(esc - 1) > 0.004:
                im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.LANCZOS)
            if abs(ang) > 0.1:
                im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
            cola_centro(camada, com_alfa(im, alfa), it["x"] + dx, self.y + dy)



# ================================================================ PALCO: caixas e provas no alto
# Todo elemento do palco tem: t0 (começa a abrir), t1 (termina de fechar), retângulo, e desenha().
# Se um começa até 0,08 s depois do anterior acabar, ele NASCE do anterior (o contêiner se transforma).
class ElementoPalco:
    tipo = "?"

    def __init__(self, spec: dict):
        self.spec = spec
        self.espaco = spec.get("espaco", True)   # False: não desce a imagem
        self.anterior: ElementoPalco | None = None
        self.e_cartao = True

    def rect(self) -> tuple:
        return (self.x, self.y, self.w, self.h)

    def precisa(self) -> float:
        """Quanto a imagem precisa descer pra este elemento não cobrir o rosto."""
        return max(0.0, self.y + self.h + 40 - TOPO) if self.espaco else 0.0

    def entrada(self, t: float) -> float:
        return ease_out((t - self.t0) / (0.26 if self.anterior else 0.2))

    def saida(self, t: float) -> float:
        return ease_out((self.t1 - t) / 0.16)

    def imagem(self, t: float) -> Image.Image:
        raise NotImplementedError

    def desenha(self, camada: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        e, s = self.entrada(t), self.saida(t)
        im = self.imagem(t)
        x, y, w, h = self.rect()
        if self.anterior is not None and e < 1:
            # nasce do anterior: contêiner interpolado + conteúdo aparecendo
            ax, ay, aw, ah = self.anterior.rect()
            k = ease_in_out(e)
            cx, cy = ax + aw / 2 + (x + w / 2 - ax - aw / 2) * k, ay + ah / 2 + (y + h / 2 - ay - ah / 2) * k
            cw, ch = aw + (w - aw) * k, ah + (h - ah) * k
            caixa = sombra(ret_arred(int(cw), int(ch), 28, CLARO + (255,)), 16, 0.3, 8)
            cola_centro(camada, caixa, cx, cy)
            if k > 0.45:
                im2 = im.resize((max(1, int(im.width * cw / w)), max(1, int(im.height * ch / h))), Image.LANCZOS)
                cola_centro(camada, com_alfa(im2, (k - 0.45) / 0.55), cx, cy)
            return
        if e < 1 or s < 1:
            # abre como persiana: nasce de uma linha e cresce na vertical; fecha do mesmo jeito
            k = min(e, s)
            hh = max(4, int(im.height * k))
            im = im.resize((im.width, hh), Image.LANCZOS)
            im = com_alfa(im, min(1.0, k * 2))
        if self.e_cartao:
            im = sombra(im, 18, 0.34, 10)
        cola_centro(camada, im, x + w / 2, y + h / 2)


def _cartao_base(w: int, h: int) -> Image.Image:
    return ret_arred(w, h, 30, CLARO + (255,))


def _rotulo_peq(d: ImageDraw.ImageDraw, x: int, y: int, txt: str, cor, size: int = 21) -> None:
    f = F("ui_bold", size)
    for ch in txt:
        d.text((x, y), ch, font=f, fill=cor)
        x += f.getlength(ch) + 2.5


class Comando(ElementoPalco):
    """Caixa 'PARA O CLAUDE': digita → enviado (spinner) → pronto (✓ e o resultado em itálico)."""
    tipo = "comando"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.ta = T(spec["em"])
        self.texto = spec["texto"]
        self.t0 = self.ta - 0.22
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else None
        self.cps = spec.get("cps", 22)
        if self.t1 is not None and spec.get("feito"):
            # o "pronto ✓" precisa ficar ~0,8 s na tela: se a caixa fecha cedo, digita mais rápido
            folga = self.t1 - self.ta - 0.8 - 0.25 - 0.35
            if folga > 0.3 and len(self.texto) / self.cps > folga:
                self.cps = len(self.texto) / folga
        self.t_dig = self.ta + len(self.texto) / self.cps
        self.t_env = self.t_dig + 0.25
        self.t_feito = T(spec["feito_em"]) if spec.get("feito_em") else self.t_env + 0.6
        if self.t1 is not None and not spec.get("feito_em"):
            self.t_feito = max(self.t_env + 0.3, min(self.t_feito, self.t1 - 0.8))
        if self.t1 is None:
            self.t1 = max(self.t_feito + 1.0, fim_tomada(spec["em"]))
        self.w = 960
        self.f = F("ui", 40)
        self.linhas = quebra_texto(self.texto, self.f, self.w - 68 - 110)
        self.h = 100 + 50 * len(self.linhas)
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])

    def imagem(self, t: float) -> Image.Image:
        im = _cartao_base(self.w, self.h)
        d = ImageDraw.Draw(im)
        feito = t >= self.t_feito and self.spec.get("feito")
        enviado = t >= self.t_env
        rot = self.spec.get("rotulo_feito", "PRONTO") if feito else ("ENVIADO" if enviado else
                                                                     self.spec.get("rotulo", "PARA O CLAUDE"))
        _rotulo_peq(d, 34, 26, rot, mistura(ESCURO, CLARO, 0.45) + (255,))
        if feito:
            fi = F("italico", 50)
            ef = ease_out((t - self.t_feito) / 0.2)
            d.text((34, 70 + (1 - ef) * 14), self.spec["feito"], font=fi, fill=ESCURO + (int(255 * ef),))
        else:
            n = int(cl((t - self.ta) * self.cps, 0, len(self.texto)))
            mostrado = self.texto[:n]
            cor = mistura(ESCURO, CLARO, 0.5) if enviado else ESCURO
            y = 66
            resto = mostrado
            for ln in self.linhas:
                parte = resto[:len(ln)]
                resto = resto[len(ln) + 1:]
                d.text((34, y), parte, font=self.f, fill=cor + (255,))
                y += 50
                if not resto:
                    break
            if not enviado and int(t * 2.2) % 2 == 0:   # cursor piscando
                lin_i = 0
                acum = 0
                for i, ln in enumerate(self.linhas):
                    if n <= acum + len(ln):
                        lin_i = i
                        break
                    acum += len(ln) + 1
                pref = self.texto[acum:n]
                cx = 34 + self.f.getlength(pref) + 3
                cy = 66 + 50 * lin_i
                d.rectangle((cx, cy + 4, cx + 3, cy + 44), fill=ESCURO + (255,))
        # botão redondo à direita
        r = 36
        bx, by = self.w - 34 - r, self.h / 2
        if feito:
            d.ellipse((bx - r, by - r, bx + r, by + r), fill=DESTAQUE + (255,))
            d.line(((bx - 15, by + 1), (bx - 4, by + 12), (bx + 16, by - 12)), fill=ESCURO + (255,), width=7,
                   joint="curve")
        elif enviado:
            d.ellipse((bx - r, by - r, bx + r, by + r), fill=ESCURO + (255,))
            a0 = (t * 540) % 360
            d.arc((bx - 18, by - 18, bx + 18, by + 18), a0, a0 + 260, fill=CLARO + (255,), width=5)
        else:
            d.ellipse((bx - r, by - r, bx + r, by + r), fill=ESCURO + (255,))
            d.line(((bx, by + 16), (bx, by - 15)), fill=CLARO + (255,), width=6)
            d.line(((bx - 12, by - 4), (bx, by - 16), (bx + 12, by - 4)), fill=CLARO + (255,), width=6, joint="curve")
        return im


class Conversa(ElementoPalco):
    """Mensagem digitada + resposta (ex.: a pessoa pede, o Claude responde)."""
    tipo = "conversa"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.ta = T(spec["em"])
        self.cps = spec.get("cps", 18)
        self.t_dig = self.ta + len(spec["texto"]) / self.cps
        self.t_resp = T(spec["resposta_em"]) if spec.get("resposta_em") else self.t_dig + 0.35
        self.t0 = self.ta - 0.22
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else max(self.t_resp + 1.2, fim_tomada(spec["em"]))
        self.w = 960
        self.f = F("ui_regular", 34)
        self.l1 = quebra_texto(spec["texto"], self.f, self.w - 150)
        self.l2 = quebra_texto(spec.get("resposta", ""), self.f, self.w - 150) if spec.get("resposta") else []
        self.h1 = 90 + 44 * len(self.l1)
        self.h = self.h1 + (60 + 44 * len(self.l2) if self.l2 else 0) + 10
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])

    def _linha(self, d, y, nome, cor_av, ini, linhas, n_chars, alfa):
        a = int(255 * alfa)
        d.ellipse((30, y, 84, y + 54), fill=cor_av + (a,))
        d.text((57, y + 27), ini, font=F("ui_bold", 26), fill=CLARO + (a,), anchor="mm")
        d.text((100, y + 2), nome, font=F("ui_bold", 26), fill=ESCURO + (a,))
        resto, yy = n_chars, y + 40
        for ln in linhas:
            parte = ln[:max(0, resto)]
            d.text((100, yy), parte, font=self.f, fill=mistura(ESCURO, CLARO, 0.15) + (a,))
            resto -= len(ln) + 1
            yy += 44

    def imagem(self, t: float) -> Image.Image:
        tem_resp = t >= self.t_resp and self.l2
        k = ease_out((t - self.t_resp) / 0.22) if tem_resp else 0.0
        h = int(self.h1 + 10 + (self.h - self.h1 - 10) * k)
        im = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        im.alpha_composite(_cartao_base(self.w, h), (0, 0))
        d = ImageDraw.Draw(im)
        n = int(cl((t - self.ta) * self.cps, 0, len(self.spec["texto"])))
        nome = self.spec.get("nome", PERFIL["nome"])
        self._linha(d, 24, nome, DESTAQUE, nome[:1] or "A", self.l1, n, 1.0)
        if tem_resp:
            self._linha(d, self.h1 + 6, self.spec.get("resposta_nome", "Claude"), (204, 112, 82),
                        self.spec.get("resposta_nome", "C")[0], self.l2, 9999, k)
        return im


class Comentario(ElementoPalco):
    """CTA de comentário: título fixo + campo digitando a palavra + coração + resposta do perfil."""
    tipo = "comentario"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.ta = T(spec["em"])
        self.t_dig = self.ta + 0.18 + len(spec["texto"]) / 9
        self.t_cor = self.t_dig + 0.45
        self.t_resp = T(spec["resposta_em"]) if spec.get("resposta_em") else self.t_dig + 0.9
        self.t0 = self.ta - 0.25
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else TOTAL
        self.w = 940
        self.ft = F("ui_bold", 42)
        self.lt = quebra_texto(spec.get("titulo", ""), self.ft, self.w - 120)
        self.ht = 40 + 52 * len(self.lt)
        self.h = self.ht + 22 + 96 + (110 if spec.get("resposta") else 0)
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])
        self.e_cartao = False

    def imagem(self, t: float) -> Image.Image:
        im = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        # título: caixa branca com texto escuro centrado
        larg = int(max(self.ft.getlength(l) for l in self.lt)) + 60
        tit = ret_arred(larg, self.ht, 18, (255, 255, 255, 255))
        dt = ImageDraw.Draw(tit)
        for i, l in enumerate(self.lt):
            dt.text((larg / 2, 22 + 52 * i), l, font=self.ft, fill=(20, 20, 20, 255), anchor="mt")
        im.alpha_composite(tit, ((self.w - larg) // 2, 0))
        # campo do comentário
        y = self.ht + 22
        campo = ret_arred(self.w, 96, 48, (255, 255, 255, 255))
        dc = ImageDraw.Draw(campo)
        dc.ellipse((22, 20, 78, 76), fill=(205, 205, 205, 255))
        n = int(cl((t - self.ta - 0.18) * 9, 0, len(self.spec["texto"])))
        txt = self.spec["texto"][:n]
        if n == 0:
            dc.text((100, 48), "Adicione um comentário...", font=F("ui_regular", 32), fill=(150, 150, 150, 255),
                    anchor="lm")
        else:
            dc.text((100, 48), txt, font=F("ui_bold", 36), fill=(20, 20, 20, 255), anchor="lm")
        cx, cy = self.w - 62, 48
        cor = t >= self.t_cor
        pts = [(cx + 17 * math.sin(a) ** 3, cy - 1 - (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a)
                                                         - math.cos(4 * a)) * 1.25) for a in np.linspace(0, 2 * math.pi, 60)]
        if cor:
            s = 1 + 0.35 * (1 - ease_out((t - self.t_cor) / 0.25))
            pts = [(cx + (px - cx) * s, cy + (py - cy) * s) for px, py in pts]
            dc.polygon(pts, fill=(237, 73, 86, 255))
        else:
            dc.line(pts + [pts[0]], fill=(40, 40, 40, 255), width=4)
        im.alpha_composite(campo, (0, y))
        if self.spec.get("resposta") and t >= self.t_resp:
            k = ease_out((t - self.t_resp) / 0.22)
            resp = ret_arred(self.w - 70, 92, 46, (255, 255, 255, 255))
            dr = ImageDraw.Draw(resp)
            dr.ellipse((18, 18, 74, 74), fill=ESCURO + (255,))
            dr.text((46, 46), self.spec.get("perfil", PERFIL["instagram"])[:1].upper(), font=F("ui_bold", 28), fill=CLARO + (255,),
                    anchor="mm")
            dr.text((94, 22), self.spec.get("perfil", PERFIL["instagram"]), font=F("ui_bold", 24), fill=(20, 20, 20, 255))
            dr.text((94, 52), self.spec["resposta"], font=F("ui_regular", 30), fill=(40, 40, 40, 255))
            cola(im, com_alfa(resp, k), 70, y + 106 + (1 - k) * 30)
        return im


class Link(ElementoPalco):
    """CTA de link: cartão do produto com botão que é tocado."""
    tipo = "link"

    def __init__(self, spec: dict):
        if not spec.get("titulo"):   # sem título no mapa: o produto do perfil
            spec["titulo"] = PERFIL["produto"] or "Meu Produto"
        super().__init__(spec)
        self.t0 = T(spec["em"]) - 0.2
        self.tt = T(spec["toque_em"]) if spec.get("toque_em") else self.t0 + 1.2
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else TOTAL
        self.w, self.h = 960, 250
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])

    def imagem(self, t: float) -> Image.Image:
        im = _cartao_base(self.w, self.h)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((30, 30, 220, 220), radius=26, fill=ESCURO + (255,))
        mono = self.spec.get("monograma", self.spec["titulo"][:2])
        d.text((125, 125), mono, font=F("italico", 74 if len(mono) <= 3 else 52), fill=DESTAQUE + (255,), anchor="mm")
        d.text((252, 40), self.spec["titulo"], font=F("ui_bold", 46), fill=ESCURO + (255,))
        fs = F("ui_regular", 28)
        for i, l in enumerate(quebra_texto(self.spec.get("sub", ""), fs, self.w - 290)[:2]):
            d.text((252, 100 + 36 * i), l, font=fs, fill=mistura(ESCURO, CLARO, 0.4) + (255,))
        bt = self.spec.get("botao", "Saiba mais")
        fb = F("ui_bold", 32)
        bw = int(fb.getlength(bt)) + 70
        bx0, by0 = self.w - 30 - bw, self.h - 30 - 70
        aperta = 0.0
        if t >= self.tt:
            aperta = 1 - ease_out((t - self.tt) / 0.3)
        cor_b = mistura(DESTAQUE, ESCURO, 0.35 * aperta)
        d.rounded_rectangle((bx0, by0, bx0 + bw, by0 + 70), radius=35, fill=cor_b + (255,))
        d.text((bx0 + bw / 2, by0 + 35), bt, font=fb, fill=ESCURO + (255,), anchor="mm")
        if self.tt <= t < self.tt + 0.5:   # toque: onda saindo do botão
            v = (t - self.tt) / 0.5
            r = 20 + 90 * ease_out(v)
            cx, cy = bx0 + bw / 2, by0 + 35
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=ESCURO + (int(200 * (1 - v)),), width=5)
        return im


# ---------------------------------------------------------------- provas
class LeitorVideo:
    """Um ffmpeg por prova de vídeo, aberto no 1º quadro em que a prova aparece."""

    def __init__(self, prova: "ProvaVideo"):
        self.p, self.proc, self.ultimo, self.k = prova, None, None, 0

    def vf(self) -> str:
        p = self.p
        c = p.crop
        return ((f"crop={c[2]}:{c[3]}:{c[0]}:{c[1]}," if c else "") + f"setpts=PTS/{p.vel},"
                f"scale={p.cw}:{p.ch}:force_original_aspect_ratio=increase:flags=lanczos,crop={p.cw}:{p.ch},"
                f"fps={FPS_NUM}/{FPS_DEN}")

    def quadro(self, t: float) -> Image.Image:
        p = self.p
        if ARGS.so_quadros or ARGS.storyboard:   # prévia/storyboard: um quadro avulso
            src = p.inicio + (t - p.t0) * p.vel
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src:.3f}", "-i", str(p.arq), "-frames:v", "1",
                                  "-vf", self.vf().replace(f"setpts=PTS/{p.vel},", ""), "-f", "rawvideo",
                                  "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
            return Image.frombytes("RGB", (p.cw, p.ch), raw[: p.cw * p.ch * 3]).convert("RGBA")
        if self.proc is None:
            self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{p.inicio:.3f}", "-i", str(p.arq),
                                          "-vf", self.vf(), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                         stdout=subprocess.PIPE)
        alvo = int((t - p.t0) * FPS)
        while self.k <= alvo:
            buf = self.proc.stdout.read(p.cw * p.ch * 3)
            if len(buf) == p.cw * p.ch * 3:
                self.ultimo = Image.frombytes("RGB", (p.cw, p.ch), buf).convert("RGBA")
            self.k += 1
        return self.ultimo if self.ultimo is not None else Image.new("RGBA", (p.cw, p.ch), CLARO + (255,))

    def fecha(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc = None


def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    return p if p.is_absolute() else (PASTA / p).resolve()


def _tamanho_video(arq: Path) -> tuple[int, int]:
    w, h = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "csv=p=0", str(arq)]).decode().strip().split(",")[:2]
    return int(w), int(h)


class ProvaVideo(ElementoPalco):
    """Gravação de tela (ou qualquer clipe) rodando num cartão no alto, com rótulo e selo."""
    tipo = "video"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.arq = _resolve(spec["arquivo"])
        if not self.arq.exists():
            sys.exit(f"prova de vídeo: não achei {self.arq}")
        self.inicio = float(spec.get("inicio", 0.0))
        self.vel = float(spec.get("velocidade", 1.0))
        self.crop = spec.get("recorte")
        sw, sh = (self.crop[2], self.crop[3]) if self.crop else _tamanho_video(self.arq)
        asp = sw / sh
        w = spec.get("largura", 760)
        h = w / asp
        hmax = spec.get("altura_max", 520)
        if h > hmax:
            h, w = hmax, hmax * asp
        self.cw, self.ch = int(w) // 2 * 2, int(h) // 2 * 2
        self.borda = 8
        self.rotulo = spec.get("rotulo")
        self.w = self.cw + 2 * self.borda
        self.h = self.ch + 2 * self.borda + (74 if self.rotulo else 0)
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])
        self.t0 = T(spec["em"]) - 0.12
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else self.t0 + spec.get("dura", fim_tomada(spec["em"]) - self.t0)
        self.leitor = LeitorVideo(self)

    def imagem(self, t: float) -> Image.Image:
        im = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        moldura = ret_arred(self.cw + 2 * self.borda, self.ch + 2 * self.borda, 30, CLARO + (255,))
        im.alpha_composite(moldura)
        q = self.leitor.quadro(t)
        # aproximação lenta dentro do cartão
        z = 1 + 0.06 * ease_in_out((t - self.t0) / max(0.5, self.t1 - self.t0))
        if z > 1.002:
            nw, nh = int(self.cw * z), int(self.ch * z)
            q = q.resize((nw, nh), Image.BICUBIC).crop(((nw - self.cw) // 2, (nh - self.ch) // 2,
                                                         (nw - self.cw) // 2 + self.cw, (nh - self.ch) // 2 + self.ch))
        m = Image.new("L", (self.cw, self.ch), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, self.cw - 1, self.ch - 1), radius=22, fill=255)
        q = q.copy()
        q.putalpha(m)
        im.alpha_composite(q, (self.borda, self.borda))
        d = ImageDraw.Draw(im)
        if self.spec.get("selo"):
            fs = F("ui_bold", 24)
            s = self.spec["selo"]
            sw = int(fs.getlength(s)) + 30
            d.rounded_rectangle((self.w - self.borda - 18 - sw, self.borda + 16, self.w - self.borda - 18,
                                 self.borda + 56), radius=20, fill=(0, 0, 0, 170))
            d.text((self.w - self.borda - 18 - sw / 2, self.borda + 36), s, font=fs, fill=(255, 255, 255, 255),
                   anchor="mm")
        if self.rotulo:
            fr_ = F("ui_bold", 32)
            partes = self.rotulo.split("*")   # *trecho* = destaque
            larg = sum(fr_.getlength(p) for p in partes) + 48
            y0 = self.ch + 2 * self.borda + 14
            x0 = (self.w - larg) / 2
            d.rounded_rectangle((x0, y0, x0 + larg, y0 + 56), radius=14, fill=(255, 255, 255, 255))
            x = x0 + 24
            for i, p in enumerate(partes):
                d.text((x, y0 + 28), p, font=fr_, fill=(VERMELHO if i % 2 else (25, 25, 25)) + (255,), anchor="lm")
                x += fr_.getlength(p)
        return im


def cartao_doc(titulo: str, w: int, h: int, sub: str = "") -> Image.Image:
    im = ret_arred(w, h, 18, CLARO + (255,))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 14), radius=7, fill=DESTAQUE + (255,))
    d.rectangle((0, 8, w - 1, 14), fill=DESTAQUE + (255,))
    f = F("legenda", 34)
    y = 36
    for l in quebra_texto(titulo, f, w - 44)[:3]:
        d.text((22, y), l, font=f, fill=ESCURO + (255,))
        y += 38
    if sub:
        d.text((22, y + 4), sub.upper(), font=F("ui_bold", 16), fill=mistura(ESCURO, CLARO, 0.45) + (255,))
        y += 26
    rng = np.random.default_rng(len(titulo))
    y += 16
    while y < h - 40:
        d.rounded_rectangle((22, y, 22 + int((w - 44) * rng.uniform(0.55, 1.0)), y + 9), radius=4,
                            fill=mistura(CLARO, ESCURO, 0.16) + (255,))
        y += 24
    return im


class ProvaCartoes(ElementoPalco):
    """Cartões (documentos gerados ou imagens) que entram um por um, espalhados e flutuando."""
    tipo = "cartoes"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = []
        for it in spec["itens"]:
            self.itens.append({**it, "te": T(it["em"]), "tok": T(it.get("ok_em")) if it.get("ok_em") else None})
        n = len(self.itens)
        self.cw, self.chh = spec.get("cartao", [230, 300])
        xs = {1: [540], 2: [370, 710], 3: [230, 540, 850]}.get(n, list(np.linspace(170, 910, n)))
        rot = [-7, 5, -4, 6, -3, 4]
        self.y = spec.get("y", LAY["palco_topo"])
        for k, it in enumerate(self.itens):
            it["x"] = xs[k]
            it["y"] = self.y + self.chh / 2 + 20 + (k % 2) * 60
            it["rot"] = rot[k % len(rot)]
            if it.get("arquivo"):
                src = Image.open(_resolve(it["arquivo"])).convert("RGBA")
                esc = max(self.cw / src.width, self.chh / src.height)
                src = src.resize((int(src.width * esc), int(src.height * esc)), Image.LANCZOS)
                src = src.crop(((src.width - self.cw) // 2, 0, (src.width - self.cw) // 2 + self.cw, self.chh))
                mk = ret_arred(self.cw, self.chh, 18, (255, 255, 255, 255)).getchannel("A")
                src.putalpha(mk)
                it["img"] = src
            else:
                it["img"] = cartao_doc(it["titulo"], self.cw, self.chh, it.get("sub", ""))
        self.x, self.w = 40, W - 80
        self.h = self.chh + 100
        self.t0 = min(it["te"] for it in self.itens) - 0.1
        ult = spec["itens"][-1]["em"]
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else fim_tomada(ult)
        self.e_cartao = False

    def entrada(self, t: float) -> float:
        return 1.0

    def desenha(self, camada: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        s = self.saida(t)
        for k, it in enumerate(self.itens):
            u = t - it["te"]
            if u < 0:
                continue
            esc = (0.45 + 0.55 * mola(u / 0.32)) * (0.85 + 0.15 * s)
            ang = it["rot"] * (0.4 + 0.6 * ease_out(u / 0.4)) + 1.2 * math.sin(t * 1.7 + k)
            dy = 7 * math.sin(t * 2.1 + k * 1.3)
            im = it["img"].copy()
            if it["tok"] is not None and t >= it["tok"]:
                v = mola((t - it["tok"]) / 0.25)
                r = int(30 * v)
                if r > 2:
                    d = ImageDraw.Draw(im)
                    cx, cy = self.cw - 36, self.chh - 36
                    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DESTAQUE + (255,))
                    if v > 0.6:
                        d.line(((cx - 12, cy), (cx - 3, cy + 10), (cx + 13, cy - 9)), fill=ESCURO + (255,), width=6,
                               joint="curve")
            im = sombra(im, 14, 0.4, 8)
            im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.LANCZOS)
            im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
            cola_centro(camada, com_alfa(im, ease_out(u / 0.1) * s), it["x"], it["y"] + dy)


class ProvaImagem(ProvaVideo):
    """Uma imagem (print, documento) num cartão, igual ao de vídeo mas parado."""
    tipo = "imagem"

    def __init__(self, spec: dict):
        ElementoPalco.__init__(self, spec)
        self.arq = _resolve(spec["arquivo"])
        src = Image.open(self.arq).convert("RGBA")
        if spec.get("recorte"):
            x, y, w, h = spec["recorte"]
            src = src.crop((x, y, x + w, y + h))
        asp = src.width / src.height
        w = spec.get("largura", 760)
        h = w / asp
        hmax = spec.get("altura_max", 520)
        if h > hmax:
            h, w = hmax, hmax * asp
        self.cw, self.ch = int(w), int(h)
        self.src = src.resize((self.cw, self.ch), Image.LANCZOS)
        self.borda, self.rotulo, self.crop = 8, spec.get("rotulo"), None
        self.w = self.cw + 2 * self.borda
        self.h = self.ch + 2 * self.borda + (74 if self.rotulo else 0)
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])
        self.t0 = T(spec["em"]) - 0.12
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else self.t0 + spec.get("dura", fim_tomada(spec["em"]) - self.t0)
        self.inicio, self.vel = 0.0, 1.0
        self.leitor = self

    def quadro(self, t: float) -> Image.Image:
        return self.src

    def fecha(self) -> None:
        pass


class ProvaRelogio(ElementoPalco):
    """Placar de virar: conta de 'de' até 'para' (ex.: 3:00 → 0:45), com rótulo em cima."""
    tipo = "relogio"

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.t0 = T(spec["em"]) - 0.1
        self.dura = spec.get("dura", 1.0)
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else max(self.t0 + self.dura + 1.0, fim_tomada(spec["em"]))
        self.w, self.h = 560, 250
        self.x, self.y = (W - self.w) / 2, spec.get("y", LAY["palco_topo"])

    @staticmethod
    def _seg(s: str) -> int:
        m, ss = s.split(":")
        return int(m) * 60 + int(ss)

    def imagem(self, t: float) -> Image.Image:
        a, b = self._seg(self.spec["de"]), self._seg(self.spec["para"])
        k = ease_in_out((t - self.t0 - 0.35) / self.dura)
        v = round(a + (b - a) * k)
        txt = f"{v // 60}:{v % 60:02d}"
        im = ret_arred(self.w, self.h, 24, ESCURO + (255,))
        d = ImageDraw.Draw(im)
        rot = self.spec.get("rotulo_final", self.spec.get("rotulo", "")) if k >= 1 else self.spec.get("rotulo", "")
        f = F("ui_bold", 22)
        d.text((self.w / 2, 34), " ".join(rot.upper()), font=f, fill=mistura(CLARO, ESCURO, 0.35) + (255,), anchor="mm")
        fd = F("serifa", 150)
        tw = sum(fd.getlength(c) + 18 for c in txt)
        x = (self.w - tw) / 2
        for c in txt:
            cw = fd.getlength(c) + 18
            if c != ":":
                d.rounded_rectangle((x, 64, x + cw - 6, 228), radius=10, fill=mistura(ESCURO, (0, 0, 0), 0.35) + (255,))
                d.line((x, 146, x + cw - 6, 146), fill=ESCURO + (255,), width=3)
            d.text((x + (cw - 6) / 2, 150), c, font=fd, fill=CLARO + (255,), anchor="mm")
            x += cw
        return im


TIPOS = {"comando": Comando, "conversa": Conversa, "comentario": Comentario, "link": Link,
         "video": ProvaVideo, "cartoes": ProvaCartoes, "imagem": ProvaImagem, "relogio": ProvaRelogio}
PALCO: list[ElementoPalco] = []
FALTANDO: list[str] = []   # só no --storyboard: prova cujo arquivo não existe (o vídeo para no erro)
for s in MAPA.get("palco", []):
    if s["tipo"] not in TIPOS:
        sys.exit(f'tipo de palco desconhecido: {s["tipo"]} (tipos: {", ".join(TIPOS)})')
    if ARGS.storyboard:
        try:
            PALCO.append(TIPOS[s["tipo"]](s))
        except (SystemExit, FileNotFoundError) as ex:
            if isinstance(ex, SystemExit) and "não achei" not in str(ex):
                raise
            FALTANDO.append(f'{s["tipo"]} em {s.get("em")}: {ex}')
        continue
    PALCO.append(TIPOS[s["tipo"]](s))
PALCO.sort(key=lambda e: e.t0)
for a, b in zip(PALCO, PALCO[1:]):   # um nasce do outro quando encostam
    if b.t0 - a.t1 < 0.08 and a.e_cartao and b.e_cartao and b.spec.get("nasce_do_anterior", True):
        a.t1 = b.t0 + 0.02
        b.anterior = a

APPS = [GrupoApps(s) for s in MAPA.get("apps", [])]   # depois do palco: a duração dos ícones olha a próxima prova


# ---------------------------------------------------------------- descida (abre o palco)
def _janelas_descida() -> list[tuple[float, float, float]]:
    js = sorted((e.t0, e.t1, e.precisa()) for e in PALCO if e.precisa() > 0)
    unidas: list[list[float]] = []
    for a, b, p in js:
        if unidas and a - unidas[-1][1] < 0.8:
            unidas[-1][1] = max(unidas[-1][1], b)
            unidas[-1][2] = max(unidas[-1][2], p)
        else:
            unidas.append([a, b, p])
    return [(a, b, min(p, LAY["descida_max"])) for a, b, p in unidas]


DESCIDAS = _janelas_descida()


def descida(t: float) -> float:
    d = 0.0
    for a, b, p in DESCIDAS:
        if a - 0.2 <= t < b + 0.3:
            k = min(ease_in_out((t - (a - 0.2)) / 0.3), ease_in_out((b + 0.3 - t) / 0.3))
            d = max(d, p * k)
    return d


SOMBRA_BORDA = None


def desce(fr: Image.Image, d: float) -> Image.Image:
    global SOMBRA_BORDA
    if SOMBRA_BORDA is None:
        g = np.zeros((60, W, 4), np.uint8)
        g[..., 3] = (np.linspace(0, 90, 60) ** 1.4 / 90 ** 0.4).astype(np.uint8)[:, None]
        SOMBRA_BORDA = Image.fromarray(g, "RGBA")
    out = FUNDO.copy()
    cola(out, fr, 0, d)
    cola(out, SOMBRA_BORDA, 0, d - 60)
    return out


# ================================================================ LEGENDA karaokê
LEG = MAPA.get("legenda_cfg", {})
LEG_TAM = LEG.get("tamanho", 52)
LEG_MAX = LEG.get("max_palavras", 4)


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    quebra = {acha(p, g) for p, g in MAPA.get("quebra_legenda", [])}
    sem = [(T(a), T(b, True)) for a, b in MAPA.get("sem_legenda", [])]
    blocos, i = [], 0
    while i < len(WORDS):
        if any(a <= WORDS[i]["s"] < b for a, b in sem):
            i += 1
            continue
        cur, j = [i], i + 1
        while j < len(WORDS) and len(cur) < LEG_MAX and j not in quebra:
            if WORDS[j]["s"] - WORDS[j - 1]["e"] >= 0.3 or WORDS[j - 1]["t"].rstrip()[-1] in ".,!?;:":
                break
            if F("legenda", LEG_TAM).getlength(" ".join(WORDS[k]["t"] for k in cur + [j])) > 860:
                break
            cur.append(j)
            j += 1
        blocos.append({"idx": cur})
        i = j
    for k, b in enumerate(blocos):
        b["ini"] = WORDS[b["idx"][0]]["s"]
        fim = WORDS[b["idx"][-1]]["e"]
        if k + 1 < len(blocos):
            ns = WORDS[blocos[k + 1]["idx"][0]]["s"]
            b["fim"] = ns if ns - fim < 0.6 else fim + 0.25
        else:
            b["fim"] = TOTAL
    return blocos


def desenha_legenda(fr: Image.Image, b: dict, t: float, y: float) -> None:
    f = F("legenda", LEG_TAM)
    palavras = [WORDS[k] for k in b["idx"]]
    txt = " ".join(w["t"] for w in palavras)
    tw = f.getlength(txt)
    pad_x, alt = 22, int(LEG_TAM * 1.32)
    x0 = (W - tw) / 2
    caixa = ret_arred(int(tw + 2 * pad_x), alt, 8, ESCURO + (238,))
    cola(fr, caixa, x0 - pad_x, y - alt / 2)
    d = ImageDraw.Draw(fr)
    x = x0
    for w in palavras:
        cor = CLARO if t >= w["s"] - 0.03 else CINZA
        d.text((x, y + 2), w["t"], font=f, fill=cor + (255,), anchor="lm")
        x += f.getlength(w["t"] + " ")


# ================================================================ transição: borrão de movimento
BORRAO = [OFF[g] for g in MAPA.get("borrao", [])]


def desfoque_h(im: Image.Image, r: int) -> Image.Image:
    if r < 2:
        return im
    a = np.asarray(im.convert("RGB"), np.float32)
    c = np.cumsum(np.pad(a, ((0, 0), (r + 1, r), (0, 0)), mode="edge"), axis=1)
    out = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")


def borra(fr: Image.Image, t: float) -> Image.Image:
    for tc in BORRAO:
        dt = abs(t - tc)
        if dt < 0.12:
            k = 1 - dt / 0.12
            z = 1 + 0.05 * k
            nw, nh = int(W * z), int(H * z)
            fr = fr.resize((nw, nh), Image.BILINEAR).crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W,
                                                           (nh - H) // 2 + H))
            return desfoque_h(fr, int(70 * k))
    return fr


# ================================================================ composição de um quadro
def compoe(fr: Image.Image, t: float, n: int, legendas: list[dict]) -> Image.Image:
    original = fr
    if GANCHO and t < G_FIM:
        fundo = FUNDO.copy() if GANCHO.get("fundo", True) else fr.copy()
        for tt in TIT_GANCHO:
            tt.desenha(fundo, t)
        if GANCHO.get("timecode", True):
            ImageDraw.Draw(fundo).text((70, TOPO + 330), timecode(t), font=F("mono", 30),
                                       fill=mistura(CLARO, ESCURO, 0.45) + (255,))
        m = mascara(n)
        fr = Image.composite(original, fundo, m) if m is not None else fundo
    else:
        atras = [tt for tt in TITULOS if tt.atras and tt.t0 <= t < tt.t1]
        if atras:
            camada = fr.copy()
            for tt in atras:
                tt.desenha(camada, t)
            fr = pessoa_na_frente(original, camada, n)
        d = descida(t)
        if d > 0.5:
            fr = desce(fr, d)
        for tt in TITULOS:
            if not tt.atras:
                tt.desenha(fr, t)
        for g in APPS:
            g.desenha(fr, t)
        for e in PALCO:
            e.desenha(fr, t)
    fr = borra(fr, t)
    b = next((b for b in legendas if b["ini"] <= t < b["fim"]), None)
    if b:
        desenha_legenda(fr, b, t, LAY["leg_y"] + (descida(t) if not (GANCHO and t < G_FIM) else 0))
    return fr


def prepara_cores() -> None:
    """Cor dos títulos e rótulos dos apps decidida uma vez, pelo quadro onde eles entram."""
    for tt in TITULOS:
        n = min(N_FRAMES - 1, round((tt.t0 + 0.1) * FPS))
        tt.decide_cor(_quadro_cache(n), n)
    for g in APPS:
        fr = _quadro_cache(min(N_FRAMES - 1, round((g.t0 + 0.1) * FPS)))
        g.cor_rot = ESCURO if luminancia(fr, (60, int(g.y - 100), W - 60, int(g.y + 130))) > 135 else CLARO


# ================================================================ áudio: efeitos sintetizados
def sfx_whoosh(d=0.5, f0=300, f1=2600, seed=0):
    n = int(d * SR)
    r = np.random.default_rng(seed).standard_normal(n)
    tt = np.arange(n) / SR
    fc = f0 * (f1 / f0) ** (tt / d)
    out = np.zeros(n)
    y1 = y2 = 0.0
    rr = 0.985
    for i in range(n):
        w = 2 * math.pi * fc[i] / SR
        y = r[i] * (1 - rr) + 2 * rr * math.cos(w) * y1 - rr * rr * y2
        out[i], y2, y1 = y, y1, y
    out *= np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 2
    return out / (np.abs(out).max() + 1e-9)


def sfx_impacto(d=0.7, seed=1):
    n = int(d * SR)
    tt = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * (48 + 60 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 7)
    clique = np.random.default_rng(seed).standard_normal(n) * np.exp(-tt * 90) * 0.5
    out = corpo + clique
    return out / np.abs(out).max()


def sfx_pop(d=0.09, f0=1100, f1=520):
    n = int(d * SR)
    tt = np.arange(n) / SR
    f = f0 + (f1 - f0) * tt / d
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 45)
    return out / np.abs(out).max()


def sfx_tecla(seed=0):
    n = int(0.035 * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    ruido = rng.standard_normal(n) * np.exp(-tt * 260)
    tom = np.sin(2 * np.pi * rng.uniform(1700, 2600) * tt) * np.exp(-tt * 300) * 0.4
    out = np.convolve(ruido + tom, np.ones(3) / 3, mode="same")
    return out / np.abs(out).max()


def sfx_ding(d=0.9):
    n = int(d * SR)
    tt = np.arange(n) / SR
    out = (np.sin(2 * np.pi * 1318.5 * tt) + 0.45 * np.sin(2 * np.pi * 2637 * tt) +
           0.2 * np.sin(2 * np.pi * 1975.5 * tt)) * np.exp(-tt * 5.5)
    out[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return out / np.abs(out).max()


def sfx_clique():
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    out = np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 120) + np.random.default_rng(9).standard_normal(n) * np.exp(-tt * 400) * 0.6
    return out / np.abs(out).max()


def trilha_sfx() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    sons = {"whoosh": [sfx_whoosh(0.42, seed=s) for s in (1, 2, 3)],
            "whoosh_curto": [sfx_whoosh(0.22, 600, 4200, seed=s) for s in (6, 7)],
            "whoosh_sobe": [sfx_whoosh(0.5, 200, 3200, seed=s) for s in (4, 5)],
            "impacto": [sfx_impacto(seed=s) for s in (1, 2)],
            "pop": [sfx_pop(), sfx_pop(0.08, 1300, 650), sfx_pop(0.1, 950, 480)],
            "tecla": [sfx_tecla(s) for s in range(6)],
            "ding": [sfx_ding()], "clique": [sfx_clique()]}
    giro = {k: itertools.cycle(v) for k, v in sons.items()}
    ev: list[tuple[float, str, float]] = []
    for k, tt in enumerate(TIT_GANCHO):
        ev.append((tt.t0, "impacto" if k == 0 else "whoosh_curto", -17 if k == 0 else -21))
        if tt.td is not None:
            ev.append((tt.td, "pop", -19))
    for tt in TITULOS:
        ev += [(tt.t0 - 0.15, "whoosh_sobe", -21), (tt.t0 + 0.02, "impacto", -19)]
    for g in APPS:
        for it in g.itens:
            ev.append((it["te"], "pop", -15))
            if g.risco or it["tr"] is not None:
                ev.append(((it["tr"] if it["tr"] is not None else it["te"] + 0.32), "whoosh_curto", -20))
        if g.ts is not None and g.modo_sai == "cai":
            ev.append((g.ts, "whoosh", -18))
    for e in PALCO:
        if e.anterior is None:
            ev.append((e.t0 - 0.12, "whoosh", -20))
        if isinstance(e, (Comando, Conversa)):
            texto = e.texto if isinstance(e, Comando) else e.spec["texto"]
            for i, ch in enumerate(texto):
                if ch != " ":
                    ev.append((e.ta + i / e.cps, "tecla", -27 - 3 * ((i * 7) % 3)))
            if isinstance(e, Comando):
                ev.append((e.t_env, "pop", -16))
                if e.spec.get("feito"):
                    ev.append((e.t_feito, "ding", -19))
            else:
                ev.append((e.t_resp, "pop", -17))
        elif isinstance(e, Comentario):
            for i in range(len(e.spec["texto"])):
                ev.append((e.ta + 0.18 + i / 9, "tecla", -26))
            ev += [(e.t_cor, "pop", -16), (e.t_resp, "ding", -20)]
        elif isinstance(e, Link):
            ev.append((e.tt, "clique", -14))
        elif isinstance(e, ProvaCartoes):
            for it in e.itens:
                ev.append((it["te"], "pop", -16))
                if it["tok"] is not None:
                    ev.append((it["tok"], "ding", -22))
        elif isinstance(e, ProvaRelogio):
            for k in range(8):
                ev.append((e.t0 + 0.35 + k * e.dura / 8, "tecla", -20))
    for tc in BORRAO:
        ev.append((tc - 0.18, "whoosh", -16))
    for t, tipo, gdb in ev:
        s = next(giro[tipo]) * 10 ** (gdb / 20)
        i = int(max(0, t) * SR)
        pista[i:i + len(s)] += s[: len(pista) - i]
    return pista[: int(TOTAL * SR)]


def musica() -> np.ndarray | None:
    cfg = MAPA.get("musica")
    if not cfg:
        return None
    arq = _resolve(cfg["arquivo"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = int(TOTAL * SR)
    x = np.tile(x, n // len(x) + 1)[:n]
    x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 10 ** (cfg.get("db", -30) / 20)
    fade = int(1.5 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_PALCO = {"comando": "Caixa de comando", "conversa": "Conversa digitada", "comentario": "CTA de comentário",
               "link": "CTA de link (botão tocado)", "video": "Prova: gravação de tela",
               "cartoes": "Prova: documentos entrando um a um", "imagem": "Prova: print/imagem",
               "relogio": "Prova: relógio de virar"}
NOMES_ANIM = {"letras": "letra por letra", "mascara": "sobe de trás de uma máscara", "rola": "rola de baixo",
              "pop": "entra grande e assenta", "seco": "corte seco"}


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    br = lambda s: s.replace(".", ",")
    ms, avisos, marcos = [], [], []   # marcos: tudo que entra na tela (inclusive itens de dentro de um elemento)

    def cap(t: float, t0: float, t1: float, margem: float = 0.05) -> float:
        return max(t0 + 0.02, min(t, t1 - margem))

    def tem_mascara(t: float) -> bool:
        return (EDIT / "masks" / "out" / f"f_{round(t * FPS):06d}.png").exists()

    def icone_ok(arq: str) -> bool:
        return any(p.exists() for p in (EDIT / "assets" / "icones" / f"{arq}.png",
                                        SKILL / "assets" / "icones" / f"{arq}.png"))

    # arquivos do mapa (antes de tirar o que falta)
    arqs: list[tuple[str, bool]] = []

    def anota(nome: str, ok: bool) -> None:
        if nome and nome not in [x for x, _ in arqs]:
            arqs.append((nome, ok))
    for g in MAPA.get("apps", []):
        for it in g.get("icones", []):
            anota(f'ícone {it["arquivo"]}.png', icone_ok(it["arquivo"]))
    for s in MAPA.get("palco", []):
        for a in [s.get("arquivo")] + [i.get("arquivo") for i in s.get("itens", []) if isinstance(i, dict)]:
            if a:
                anota(a, _resolve(a).exists())
    if MAPA.get("musica"):
        anota(MAPA["musica"]["arquivo"], _resolve(MAPA["musica"]["arquivo"]).exists())
    # ícone que falta derrubaria o quadro (sys.exit no desenho): fica fora do storyboard
    for g in APPS:
        fora = [it["arq"] for it in g.itens if not icone_ok(it["arq"])]
        if fora:
            avisos.append(f'falta o ícone {", ".join(fora)}: rode icone_app.py (fica fora dos quadros)')
            g.itens = [it for it in g.itens if icone_ok(it["arq"])]
    APPS[:] = [g for g in APPS if g.itens]
    for f in FALTANDO:
        avisos.append(f"prova sem arquivo, fora do storyboard (o render para aqui): {f}")

    def pronto_titulo(x: Titulo) -> float:
        """Instante em que o título inteiro (e o destaque) já está na tela."""
        if x.anim == "letras":
            e = (x.n_chars - 1) * x.stagger + 0.2
        elif x.anim in ("mascara", "rola"):
            e = 0.12 * (len(x.linhas) - 1) + (0.08 if x.faixa else 0) + 0.3
        elif x.anim == "pop":
            e = 0.25
        else:
            e = 0.1
        if x.faixa:
            e = max(e, 0.12 * (len(x.linhas) - 1) + 0.3)
        q = x.t0 + e
        if x.td is not None:
            q = max(q, x.td + 0.2)
        return q

    def desc_titulo(x: Titulo) -> str:
        d = " / ".join(SB.limpa_marcacao(l) for l in x.spec["linhas"]) + f" — {NOMES_ANIM.get(x.anim, x.anim)}"
        if x.spec.get("destaque"):
            d += f"; destaque: {', '.join(x.spec['destaque'])}"
        return d

    curto = lambda dur: f"fica só {br(f'{dur:.1f}')} s na tela: conferir se dá pra ler (elemento na última palavra some com a tomada)"

    # gancho: títulos no fundo chapado, a pessoa recortada na frente
    for k, x in enumerate(TIT_GANCHO):
        q = cap(pronto_titulo(x), x.t0, x.t1, 0.26 if x.saida == "sobe" else 0.05)
        d = desc_titulo(x)
        if k == 0:
            d = "capa do Reel no feed; " + d + ("; timecode no canto" if GANCHO.get("timecode", True) else "")
        m = {"t0": max(0.0, x.t0), "t1": x.t1, "quadro": q, "tipo": "Título do gancho no fundo chapado", "desc": d}
        if not tem_mascara(max(0.0, q)):
            m["aviso"] = "sem máscara neste quadro: a pessoa some atrás do fundo (rodar mascaras.py)"
        ms.append(m)
    if GANCHO:
        ms.append({"t0": G_FIM, "t1": G_FIM, "quadro": G_FIM + 0.1, "tipo": "Transição: fim do gancho",
                   "desc": "sai o fundo chapado, volta o vídeo da pessoa"})
    # títulos fora do gancho
    for x in TITULOS:
        tipo = "Título com faixa (na frente)" if x.faixa else ("Título atrás da cabeça" if x.atras else "Título na frente")
        q = cap(pronto_titulo(x), x.t0, x.t1, 0.2 if x.saida == "some" else 0.05)
        m = {"t0": x.t0, "t1": x.t1, "quadro": q, "tipo": tipo, "desc": desc_titulo(x)}
        if x.atras and not tem_mascara(q):
            m["aviso"] = "sem máscara neste quadro: o título cobre a pessoa (rodar mascaras.py)"
        elif x.t1 - x.t0 < 1.0:
            m["aviso"] = curto(x.t1 - x.t0)
        ms.append(m)
    # apps citados
    for g in APPS:
        te_ult = max(it["te"] for it in g.itens)
        fim_q = (g.ts - 0.02) if g.ts is not None else g.t1 - 0.2
        nomes = ", ".join(it["nome"] or it["arq"] for it in g.itens)
        d = nomes + (" (com risco vermelho)" if g.risco or any(it["tr"] is not None for it in g.itens) else "")
        if g.ts is not None:
            d += f"; saem {'caindo' if g.modo_sai == 'cai' else 'sumindo'} em {br(f'{g.ts:.1f}')} s"
        marcos.extend(it["te"] for it in g.itens)
        m = {"t0": g.t0, "t1": g.t1, "quadro": max(g.t0 + 0.05, min(te_ult + 0.35, fim_q)),
             "tipo": "App citado" if len(g.itens) == 1 else "Apps citados", "desc": d}
        minimo = g.spec.get("minimo", 2.0)
        if g.ts is None and g.t1 - te_ult < minimo - 0.01:
            m["aviso"] = (f"{g.itens[-1]['nome'] or g.itens[-1]['arq']} fica só {br(f'{g.t1 - te_ult:.1f}')} s "
                          f"(mínimo da skill: {br(f'{minimo:.0f}')} s); encurtou pra não cruzar com a próxima prova")
        ms.append(m)
        if g.ts is not None and g.modo_sai == "cai":
            ms.append({"t0": g.ts, "t1": g.t1, "quadro": cap(g.ts + 0.22, g.ts, g.t1), "tipo": "Apps caem",
                       "desc": f"{nomes} caem girando (\"espalhado\")"})
    # palco: caixas e provas. t0 do momento = a palavra em que entra (a caixa abre 0,1-0,25 s antes,
    # e por esse começo antecipado o momento cairia na cena anterior do storyboard)
    for e in PALCO:
        tipo = NOMES_PALCO.get(e.tipo, e.tipo)
        nasce = "; nasce da caixa anterior" if e.anterior is not None else ""
        if isinstance(e, Comando):
            fim_dig = e.t_env if e.spec.get("feito") else e.t1
            ms.append({"t0": e.ta, "t1": fim_dig, "quadro": cap(e.t_dig + 0.05, e.t0, fim_dig),
                       "tipo": "Caixa de comando digitando",
                       "desc": f'{e.spec.get("rotulo", "PARA O CLAUDE")}: "{e.texto}"{nasce}'})
            if e.spec.get("feito"):
                m = {"t0": e.t_feito, "t1": e.t1, "quadro": cap(e.t_feito + 0.3, e.t_feito, e.t1, 0.2),
                     "tipo": "Comando pronto ✓", "desc": f'{e.spec.get("rotulo_feito", "PRONTO")}: {e.spec["feito"]}'}
                if e.t1 - e.t_feito < 0.8:
                    m["aviso"] = f"o \"pronto ✓\" fica só {br(f'{e.t1 - e.t_feito:.1f}')} s (regra da skill: ~0,8 s)"
                ms.append(m)
            continue
        if isinstance(e, Conversa):
            q = (e.t_resp + 0.3) if e.l2 else e.t_dig + 0.1
            ini = e.ta
            marcos.append(e.t_resp)
            d = f'{e.spec.get("nome", PERFIL["nome"])}: "{e.spec["texto"]}"'
            if e.l2:
                d += f' → {e.spec.get("resposta_nome", "Claude")}: "{e.spec["resposta"]}"'
        elif isinstance(e, Comentario):
            q = (e.t_resp + 0.3) if e.spec.get("resposta") else e.t_cor + 0.3
            ini = e.ta
            marcos += [e.t_cor, e.t_resp]
            d = f'{e.spec.get("titulo", "")} — digita "{e.spec["texto"]}"'
            if e.spec.get("resposta"):
                d += f' — resposta: "{e.spec["resposta"]}"'
        elif isinstance(e, Link):
            q = e.tt + 0.15
            ini = e.t0 + 0.2
            marcos.append(e.tt)
            d = f'{e.spec["titulo"]} — {e.spec.get("sub", "")} — botão "{e.spec.get("botao", "Saiba mais")}" tocado em {br(f"{e.tt:.1f}")} s'
        elif isinstance(e, ProvaCartoes):
            q = max([it["te"] + 0.4 for it in e.itens] + [it["tok"] + 0.3 for it in e.itens if it["tok"] is not None])
            ini = min(it["te"] for it in e.itens)
            marcos += [it["te"] for it in e.itens] + [it["tok"] for it in e.itens if it["tok"] is not None]
            d = " · ".join((it.get("titulo") or Path(it.get("arquivo", "")).name) + (" ✓" if it["tok"] is not None else "")
                           for it in e.itens)
        elif isinstance(e, ProvaRelogio):
            q = e.t0 + 0.35 + e.dura + 0.15
            ini = e.t0 + 0.1
            rot = e.spec.get("rotulo", "")
            d = f'{rot + ": " if rot else ""}{e.spec["de"]} → {e.spec["para"]}' + (
                f' ({e.spec["rotulo_final"]})' if e.spec.get("rotulo_final") else "")
        elif isinstance(e, ProvaVideo):   # vídeo e imagem
            q = e.t0 + 0.5
            ini = e.t0 + 0.12
            d = SB.textos_do_spec(e.spec)
            if e.tipo == "video":
                d += f'; a partir de {br(f"{e.inicio:.1f}")} s' + (f", {br(f'{e.vel:g}')}x" if e.vel != 1 else "")
            if e.spec.get("recorte"):
                d += f'; recorte {e.spec["recorte"]}'
        else:
            q, d, ini = e.t0 + 0.5, SB.textos_do_spec(e.spec), e.t0
        m = {"t0": ini, "t1": e.t1, "quadro": cap(q, e.t0, e.t1, 0.2), "tipo": tipo, "desc": (d or "—") + nasce}
        if e.t1 - e.t0 < 1.0:
            m["aviso"] = curto(e.t1 - e.t0)
        ms.append(m)
    # câmera: a imagem da pessoa desce e abre o palco
    for a, b, p in DESCIDAS:
        # t0 = quando a imagem termina de descer (começa 0,2 s antes da prova abrir)
        ms.append({"t0": a + 0.1, "t1": b + 0.3, "quadro": a + 0.25, "tipo": "Câmera: a pessoa desce e abre o palco",
                   "desc": f"a imagem desce {p:.0f} px pra prova caber sem cobrir o rosto"})
    # transições
    blocos = [tm[2] if len(tm) > 2 else "" for tm in MAPA.get("tomadas", [])]
    for gi in MAPA.get("borrao", []):
        tc = OFF[gi]
        virada = (f" ({blocos[gi - 1]} → {blocos[gi]})" if len(blocos) == _NG and 0 < gi and blocos[gi]
                  and blocos[gi] != blocos[gi - 1] else "")
        ms.append({"t0": tc - 0.12, "t1": tc + 0.12, "quadro": tc, "tipo": "Transição: borrão de movimento",
                   "desc": "virada de bloco do roteiro" + virada})
    for m in ms:
        for k in ("t0", "t1", "quadro"):
            m[k] = round(float(m[k]), 2)
    # ritmo (referência: elemento novo a cada ~2 s, um trecho limpo de ~3 s na virada)
    marcos = sorted(set([0.0, TOTAL] + [m["t0"] for m in ms] + [round(x, 2) for x in marcos] + list(OFF[1:-1])))
    for a, b in zip(marcos, marcos[1:]):
        if b - a > 3.0:
            avisos.append(br(f"{b - a:.1f} s sem nada novo ({a:.1f}–{b:.1f} s): a referência põe elemento novo "
                             "a cada ~2 s (um trecho limpo de ~3 s na virada é ok)"))
    if MAPA.get("legenda") is False:
        avisos.append("legenda desligada no mapa (\"legenda\": false)")
    cenas = [{"t0": round(OFF[g], 2), "t1": round(OFF[g + 1], 2),
              "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)} for g in range(_NG)]

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, n, legendas)

    out = SB.gerar(EDIT, "Prova", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ================================================================ main
def pico_real(arq: Path) -> float:
    log = subprocess.run(["ffmpeg", "-nostats", "-i", str(arq), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(log.rsplit("Peak:", 1)[1].split()[0])


def segura_pico(out: Path) -> None:
    tp = pico_real(out)
    if tp <= -1.0:
        return
    tmp = out.with_suffix(".lim.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-c:v", "copy", "-af",
                    "aresample=192000,alimiter=limit=0.83:attack=1:release=40:level=false,aresample=48000",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(out)
    print(f"  pico real {tp:.1f} → {pico_real(out):.1f} dBTP (limitador)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    legendas = monta_legendas()
    prepara_cores()
    modo = "final" if ARGS.final else "preview"

    if ARGS.storyboard:
        storyboard(legendas)
        return

    if ARGS.so_quadros:
        pasta = EDIT / "verify" / "quadros"
        pasta.mkdir(parents=True, exist_ok=True)
        for ts in ARGS.so_quadros.split(","):
            t = float(ts)
            n = round(t * FPS)
            compoe(quadro_base(n), t, n, legendas).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
        print(f"prévias em {pasta}")
        return

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(BASE), "-vn", "-ac", "2", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    voz = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, 2) / 32768
    extra = trilha_sfx()
    mus = musica()
    if mus is not None:
        extra = extra[: len(mus)] + mus[: len(extra)]
    n = min(len(voz), len(extra))
    mix = voz[:n] + extra[:n, None]
    wav = EDIT / f"mix_{modo}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(BASE), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    prenorm = EDIT / f"{modo}_prova.prenorm.mp4"
    preset, crf = ("slow", "17") if ARGS.final else ("medium", "20")
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", f"{FPS_NUM}/{FPS_DEN}", "-i", "-", "-i", str(wav),
                            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", preset, "-crf", crf,
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                            "-movflags", "+faststart", str(prenorm)], stdin=subprocess.PIPE)
    tam = W * H * 3
    k = 0
    while True:
        buf = dec.stdout.read(tam)
        if len(buf) < tam:
            break
        t = k / FPS
        fr = Image.frombytes("RGB", (W, H), buf).convert("RGBA")
        enc.stdin.write(compoe(fr, t, k, legendas).convert("RGB").tobytes())
        for e in PALCO:   # fecha o ffmpeg de quem já saiu
            if isinstance(e, ProvaVideo) and t >= e.t1:
                e.leitor.fecha()
        k += 1
        if k % 150 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_prova.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
