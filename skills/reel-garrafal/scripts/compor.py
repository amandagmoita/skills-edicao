"""compor.py — monta o Reel no estilo "letras garrafais" quadro a quadro, a partir do mapa.json.

Estilo medido (referencia/referencias-estilo.md, Reel "counting frames"): tutorial que mostra
o que fala. O tipo de letra diz o tipo de palavra (legenda pequena sem serifa, destaque grande com brilho,
garrafal sobre B-roll, serifa itálica pra valor, palavra-conceito ultra condensada atrás da cabeça, sussurro
minúsculo em tela branca ou preta). A tela troca a cada ~1 s entre blocos: abertura em 8-3-3-4-5 quadros,
rosto, respiro, "outros" em P&B com lente curva e moldura que encolhe, macro P&B, diagrama no branco, tela
dividida, gravação de tela com zoom, retrospectiva em cards. Luz: brilho nas letras, estouro antes do
corte, desfoque → foco na volta pro rosto.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/
  $PY compor.py <edit_dir> --storyboard                # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_garrafal.mp4 | final_garrafal.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov | base_final.mov, masks/out (mascaras.py), imagens e vídeos em <edit>/assets/ ou na
    pasta do vídeo.
"""

from __future__ import annotations

import argparse
import bisect
import functools
import itertools
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

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

# ---------------------------------------------------------------- linha do tempo
MAPA = json.loads((EDIT / "mapa.json").read_text())
_INFO = json.loads((EDIT / "base_info.json").read_text())
FPS_NUM, FPS_DEN = _INFO["fps"]
FPS = FPS_NUM / FPS_DEN
_EDL = json.loads((EDIT / "edl.json").read_text())["ranges"]
_ROFF = list(itertools.accumulate([0.0] + _INFO["duracoes"]))
_NG = max(r["grupo"] for r in _EDL) + 1
OFF = [min(_ROFF[i] for i, r in enumerate(_EDL) if r["grupo"] == g) for g in range(_NG)] + [_ROFF[-1]]
WORDS = [{"s": a, "e": b, "t": t, "seg": k} for a, b, t, k in json.loads((EDIT / "words_out.json").read_text())]
TOTAL = OFF[-1]
N_FRAMES = round(TOTAL * FPS)
QD = 1 / FPS

_MED_ARQ = EDIT / "medidas.json"
if not _MED_ARQ.exists():
    sys.exit("falta medidas.json: rode medir.py")
MED = json.loads(_MED_ARQ.read_text())["grupos"]
if len(MED) != _NG:
    sys.exit("medidas.json é de outro corte: rode medir.py de novo")


def limpa(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


def acha(texto: str, grupo: int) -> int:
    alvo = limpa(texto)
    for i, w in enumerate(WORDS):
        if w["seg"] == grupo and limpa(w["t"]) == alvo:
            return i
    fala = " ".join(w["t"] for w in WORDS if w["seg"] == grupo)
    sys.exit(f'palavra "{texto}" não está na tomada {grupo}. Fala da tomada: {fala}')


ANTECIPA = float(MAPA.get("antecipa", 0.03))


def T(spec) -> float:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] (ANTECIPA s antes da palavra) |
    [palavra, tomada, atraso] | ["fim", tomada] (fim da tomada) | ["inicio", tomada]."""
    if isinstance(spec, (int, float)):
        return float(spec)
    if spec[0] == "fim":
        return OFF[int(spec[1]) + 1]
    if spec[0] == "inicio":
        return OFF[int(spec[1])]
    w = WORDS[acha(spec[0], int(spec[1]))]
    d = float(spec[2]) if len(spec) > 2 else -ANTECIPA
    return max(0.0, w["s"] + d)


def grupo(t: float) -> int:
    return max(0, min(_NG - 1, bisect.bisect_right(OFF, t) - 1))


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    x = cl(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


BRANCO = (255, 255, 255)
PRETO = (0, 0, 0)
TINTA = (14, 14, 14)
CLARO = hexa(MAPA.get("fundo_claro", "#F2F2F2"))      # tela de respiro, diagrama, retrospectiva (medido)

# ---------------------------------------------------------------- fontes (todas do Mac)
_HN = "/System/Library/Fonts/HelveticaNeue.ttc"
_BOD = "/System/Library/Fonts/Supplemental/Bodoni 72.ttc"
FONTES = {
    "sans": (_HN, 1),        # Helvetica Neue Bold: base, destaque, garrafal, diagrama, sussurro
    "italica": (_BOD, 1),    # Bodoni 72 Book Italic, engrossada no desenho
    "conceito": (_BOD, 2),   # Bodoni 72 Bold, apertada na largura
}


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, idx = FONTES[tipo]
    return ImageFont.truetype(arq, max(6, int(size)), index=idx)


# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "topo": 150,              # barra do Instagram
    "base": 0.76,             # nada desce além disto
    "base_tam": 62,           # legenda base (ref. ~40 px em 720)
    "destaque_tam": 150,      # ref. "a chair" ~100 px em 720
    "garrafal_tam": 280,      # ref. "This" ~190 px em 720
    "garrafal_larg": 0.86,    # garrafal nunca passa disto da largura
    "italico_tam": 128,       # ref. "even" ~70 px em 720 (x-height 42)
    "sussurro_tam": 24,       # ref. "who" 13 px de altura em 720
    "diagrama_tam": 128,      # ref. "sequence" ~100 px em 720
    "track": -0.025,          # letras um pouco apertadas
    "leg_queixo": 150,        # legenda no rosto: px abaixo do queixo
    "leg_min": 0.52, "leg_max": 0.66,
    "conceito_alt": 270,      # altura das maiúsculas da palavra-conceito
    "conceito_aperta": 0.44,  # largura da Bodoni Bold apertada (ref. ultra condensada)
    "conceito_larg": 0.90,
    "conceito_topo": 175,     # topo das letras
    "conceito_vidro": 0.62,   # quanto aparece por cima do cabelo (rosto nunca)
    "div_base_tam": 44, "div_destaque_tam": 92, "div_italico_tam": 84,
    "rosto_cy": 0.40,
}
LAY.update(MAPA.get("layout", {}))


# ---------------------------------------------------------------- utilidades de imagem
def cola_centro(dest: Image.Image, im: Image.Image | None, cx: float, cy: float) -> None:
    if im is None:
        return
    cola(dest, im, int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


def cola(dest: Image.Image, im: Image.Image, x: int, y: int) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def desfoca(im: Image.Image, r: float) -> Image.Image:
    if r < 0.4:
        return im
    return im.convert("RGBa").filter(ImageFilter.GaussianBlur(r)).convert("RGBA")


def opaco(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    out = im.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * cl(a))))
    return out


def escala(im: Image.Image, s: float, sy: float | None = None) -> Image.Image:
    sy = s if sy is None else sy
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * sy))), Image.BICUBIC)


def com_margem(im: Image.Image, m: int) -> Image.Image:
    out = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    out.alpha_composite(im, (m, m))
    return out


def pb(im: Image.Image, contraste: float = 1.25) -> Image.Image:
    g = ImageOps.grayscale(im.convert("RGB"))
    g = ImageEnhance.Contrast(g).enhance(contraste)
    return g.convert("RGBA")


@functools.lru_cache(maxsize=1024)
def mascara_texto(txt: str, tipo: str, tam: int, track: float = 0.0, pad: int = 60, grossa: int = 0) -> Image.Image:
    f = F(tipo, tam)
    larg = sum(f.getlength(c) for c in txt) + track * tam * max(0, len(txt) - 1)
    w, h = int(larg) + 2 * pad, int(tam * 1.45) + 2 * pad
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    x = pad
    for c in txt:
        d.text((x, h / 2), c, font=f, fill=255, anchor="lm")
        x += f.getlength(c) + track * tam
    if grossa:
        m = m.filter(ImageFilter.MaxFilter(grossa))
    bb = m.getbbox()
    if bb:   # corta o vazio e deixa margem pro brilho
        x0, y0, x1, y1 = bb
        m = m.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))
    return m


def sombra_de(m: Image.Image, raio: float, forca: float, cor: tuple = PRETO, dy: int = 0) -> Image.Image:
    s = Image.new("RGBA", m.size, cor + (255,))
    s.putalpha(m.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: int(min(255, v * forca))))
    if dy:
        out = Image.new("RGBA", m.size, (0, 0, 0, 0))
        out.alpha_composite(s, (0, dy))
        return out
    return s


def pinta(m: Image.Image, cor: tuple, brilho: float = 0.0, sombra: float = 0.0, tam: float = 100) -> Image.Image:
    """Texto aceso: sombra escura macia (separa do fundo claro atrás da pessoa) + brilho branco largo + letra."""
    if brilho or sombra:   # margem maior que o raio, senão o brilho é cortado e vira caixa
        mg = int(tam * (0.75 if brilho else 0.4))
        m2 = Image.new("L", (m.width + 2 * mg, m.height + 2 * mg), 0)
        m2.paste(m, (mg, mg))
        m = m2
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    if sombra:
        im.alpha_composite(sombra_de(m, tam * 0.16, sombra * 0.9, PRETO, max(1, int(tam * 0.02))))
        im.alpha_composite(sombra_de(m, max(1.5, tam * 0.035), sombra, PRETO, max(1, int(tam * 0.015))))
    if brilho:
        im.alpha_composite(sombra_de(m, tam * 0.30, 0.55 * brilho, BRANCO))
        im.alpha_composite(sombra_de(m, tam * 0.09, 0.85 * brilho, BRANCO))
    c = Image.new("RGBA", m.size, cor + (255,))
    c.putalpha(m)
    im.alpha_composite(c)
    return im


def cobre(im: Image.Image, w: int, h: int, foco: tuple = (0.5, 0.5)) -> Image.Image:
    """Recorta pra preencher w×h sem esticar, centrado no foco (fração da imagem)."""
    s = max(w / im.width, h / im.height)
    r = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    x = cl(foco[0] * r.width - w / 2, 0, r.width - w)
    y = cl(foco[1] * r.height - h / 2, 0, r.height - h)
    return r.crop((int(x), int(y), int(x) + w, int(y) + h))


@functools.lru_cache(maxsize=64)
def mascara_arred(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    return m


# ---------------------------------------------------------------- fontes de imagem/vídeo
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw).convert("RGBA")


def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    if p.is_absolute() and p.exists():
        return p
    for cand in (EDIT / "assets" / arq, EDIT / "assets" / f"{arq}.png", EDIT / "assets" / f"{arq}.jpg",
                 EDIT / arq, PASTA / arq, SKILL / "assets" / arq):
        if cand.exists():
            return cand.resolve()
    sys.exit(f"não achei o arquivo {arq} (procurei em assets/ e na pasta do vídeo)")


@functools.lru_cache(maxsize=64)
def imagem(arq: str) -> Image.Image:
    return Image.open(_resolve(arq)).convert("RGBA")


def _dims(p: Path) -> tuple[int, int, float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    a, b = out[2].split("/")
    return int(out[0]), int(out[1]), int(a) / int(b)


class FonteVideo:
    """Gravação de tela lida em sequência (um ffmpeg aberto); salto pra trás ou longe reabre."""

    def __init__(self, arq: str):
        self.p = _resolve(arq)
        self.w, self.h, self.fps = _dims(self.p)
        self.proc, self.pos, self.ultimo = None, -1, None

    def _abre(self, n: int) -> None:
        if self.proc:
            self.proc.kill()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{n / self.fps:.4f}", "-i", str(self.p),
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.pos = n - 1

    def quadro(self, t: float) -> Image.Image:
        n = max(0, round(t * self.fps))
        if self.proc is None or n <= self.pos - 1 or n > self.pos + 30:
            if n == self.pos and self.ultimo is not None:
                return self.ultimo
            self._abre(n)
        tam = self.w * self.h * 3
        while self.pos < n:
            buf = self.proc.stdout.read(tam)
            if len(buf) < tam:
                break
            self.pos += 1
            self.ultimo = Image.frombytes("RGB", (self.w, self.h), buf)
        return self.ultimo


_FONTES_VIDEO: dict[str, FonteVideo] = {}


def video(arq: str) -> FonteVideo:
    if arq not in _FONTES_VIDEO:
        _FONTES_VIDEO[arq] = FonteVideo(arq)
    return _FONTES_VIDEO[arq]


# ================================================================ CÂMERA no rosto
def camera(t: float, z: float) -> tuple[float, float, float]:
    if z <= 1.0005:
        return 1.0, 0.0, 0.0
    r = MED[grupo(t)]["rosto"]
    fcx, fcy = r[0] + r[2] / 2, r[1] + r[3] / 2
    cw, ch = W / z, H / z
    return z, cl(fcx - cw / 2, 0, W - cw), cl(fcy - ch * LAY["rosto_cy"], 0, H - ch)


def aplica_camera(im: Image.Image, cam: tuple, filtro=Image.BICUBIC) -> Image.Image:
    z, x0, y0 = cam
    if z <= 1.0005:
        return im
    return im.crop((int(x0), int(y0), int(x0 + W / z), int(y0 + H / z))).resize((W, H), filtro)


def na_tela(cam: tuple, x: float, y: float) -> tuple[float, float]:
    z, x0, y0 = cam
    return (x - x0) * z, (y - y0) * z


def cabeca(t: float, cam: tuple) -> dict:
    g = MED[grupo(t)]
    r = g["rosto"]
    _, topo = na_tela(cam, 0, g["topo"])
    cx, cy = na_tela(cam, r[0] + r[2] / 2, r[1] + r[3] / 2)
    x0, y0 = na_tela(cam, r[0], r[1])
    x1, y1 = na_tela(cam, r[0] + r[2], r[1] + r[3])
    return {"topo": topo, "cx": cx, "cy": cy, "queixo": y1, "rosto": (x0, y0, x1, y1)}


# ================================================================ BLOCOS DE TELA
class Bloco:
    tipo = "rosto"
    voz_padrao = "base"

    def __init__(self, spec: dict, t0: float, t1: float):
        self.spec, self.t0, self.t1 = spec, t0, t1
        self.estouro = bool(spec.get("estouro", False))

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def fundo(self, fr: Image.Image, t: float) -> Image.Image:
        return fr

    def eventos(self) -> list[tuple[float, str]]:
        return [(self.t0 - 0.12, "whoosh")]


class Rosto(Bloco):
    """A pessoa na tela inteira. Volta de outro bloco = entra desfocada e firma em ~8 quadros (ref. 2,0 / 8,5 / 33 s)."""
    tipo = "rosto"

    def __init__(self, spec, t0, t1, vem_de_outro: bool):
        super().__init__(spec, t0, t1)
        self.vem_de_outro = vem_de_outro
        self.z = float(spec.get("z", 1.0))

    def cam(self, t: float) -> tuple:
        return camera(t, self.z)

    def fundo(self, fr, t):
        im = aplica_camera(fr, self.cam(t))
        if self.vem_de_outro and self.spec.get("foco", True):
            k = (t - self.t0) / float(self.spec.get("foco_dur", 0.30))
            if k < 1:
                im = desfoca(im, 16 * (1 - ease_out(k)))
        return im

    def eventos(self):
        return []


class Respiro(Bloco):
    """Tela inteira #F2F2F2 ou preta com palavra minúscula (ref. 4,4-5,4 s e 13,1-14,0 s)."""
    tipo = "respiro"
    voz_padrao = "sussurro"

    def fundo(self, fr, t):
        cor = PRETO if self.spec.get("cor") == "preto" else CLARO
        return Image.new("RGBA", (W, H), cor + (255,))


def quadro_imagem(arq: str, foco: tuple, z: float, preto_branco: bool, luz: float = 0.62) -> Image.Image:
    im = imagem(arq)
    alvo_w, alvo_h = int(W * z), int(H * z)
    c = cobre(im, alvo_w, alvo_h, foco)
    if z != 1.0:
        x, y = (c.width - W) // 2, (c.height - H) // 2
        c = c.crop((x, y, x + W, y + H))
    c = pb(c) if preto_branco else c.convert("RGBA")
    if luz < 0.999:   # B-roll da ref. é escuro (quarto à noite); imagem clara come a letra branca
        c = ImageEnhance.Brightness(ImageEnhance.Contrast(c.convert("RGB")).enhance(1.12)).enhance(luz).convert("RGBA")
    return c


class Abertura(Bloco):
    """5 B-rolls de 8, 3, 3, 4, 5 quadros + plano longo (ref. 0-1,96 s). 1º quadro em P&B (o olho "acende")."""
    tipo = "abertura"
    voz_padrao = "garrafal"

    def __init__(self, spec, t0, t1):
        super().__init__(spec, t0, t1)
        self.clipes = []
        n0 = round(t0 * FPS)   # conta em quadros inteiros: soma de frações de segundo erra 1 quadro
        for c in spec["clipes"]:
            q = c.get("quadros")
            a = (n0 - 0.5) / FPS
            fim = (n0 + q - 0.5) / FPS if q else t1
            self.clipes.append((max(t0, a), min(fim, t1), c))
            n0 += q or 0

    def fundo(self, fr, t):
        for a, b, c in self.clipes:
            if a <= t < b:
                k = (t - a) / max(QD, b - a)
                z = lerp(c.get("z0", 1.06), c.get("z1", 1.14), k)
                primeiro = (a == self.t0 and t - a < QD * 0.99)
                return quadro_imagem(c["arquivo"], tuple(c.get("foco", (0.5, 0.5))), z,
                                     c.get("pb", False) or primeiro, float(c.get("luz", self.spec.get("luz", 0.62))))
        return fr

    def eventos(self):
        return [(self.t0, "riser")]


class Macro(Bloco):
    """B-roll em P&B, cada clipe entra na palavra (ref. teclado, trackpad, timecode 11,3-13,1 s)."""
    tipo = "macro"
    voz_padrao = "base"

    def __init__(self, spec, t0, t1):
        super().__init__(spec, t0, t1)
        self.clipes = sorted([(T(c["em"]) if "em" in c else t0, c) for c in spec["clipes"]], key=lambda x: x[0])
        self.clipes[0] = (t0, self.clipes[0][1])

    def fundo(self, fr, t):
        idx = max(i for i, (a, _) in enumerate(self.clipes) if a <= t or i == 0)
        a, c = self.clipes[idx]
        b = self.clipes[idx + 1][0] if idx + 1 < len(self.clipes) else self.t1
        k = (t - a) / max(QD, b - a)
        z = lerp(c.get("z0", 1.10), c.get("z1", 1.22), k)
        return quadro_imagem(c["arquivo"], tuple(c.get("foco", (0.5, 0.5))), z, self.spec.get("pb", True),
                             float(c.get("luz", self.spec.get("luz", 0.62))))

    def eventos(self):
        ev = [(self.t0 - 0.12, "whoosh")]
        ev += [(a, "tique") for a, _ in self.clipes[1:]]
        return ev


def lente(card: Image.Image, c: float) -> Image.Image:
    """Bordas curvas pra dentro (ref. 5,9-8,4 s): lados mais estreitos no meio, topo/base curvados de leve."""
    if c <= 0.001:
        return card
    a = np.asarray(card)
    h, w = a.shape[:2]
    v = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    u = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    xe = 1 - c * (1 - v ** 2)
    ye = 1 - c * 0.35 * (1 - u ** 2)
    us, vs = u / xe, v / ye
    dentro = (np.abs(us) <= 1) & (np.abs(vs) <= 1)
    xi = np.clip(((us + 1) / 2 * (w - 1)).round().astype(np.int32), 0, w - 1)
    yi = np.clip(((vs + 1) / 2 * (h - 1)).round().astype(np.int32), 0, h - 1)
    out = a[yi, xi].copy()
    out[~dentro] = 0
    return Image.fromarray(out, "RGBA")


class Outros(Bloco):
    """O jeito errado/repetido em P&B: entra com desfoque de movimento, a borda curva e a moldura encolhe
    num card sobre preto, literalmente "dando zoom out" (ref. 5,36-8,48 s)."""
    tipo = "outros"
    voz_padrao = "destaque"

    def fundo(self, fr, t):
        d = t - self.t0
        dur = self.t1 - self.t0
        im = pb(fr, 1.3)
        if d < 0.16:   # entra borrado e grande (ref. q134-137)
            k = d / 0.16
            c = escala(im, lerp(1.25, 1.0, ease_out(k)))
            x, y = (c.width - W) // 2, (c.height - H) // 2
            return desfoca(c.crop((x, y, x + W, y + H)), 14 * (1 - k))
        k = ease_in_out((d - 0.16) / max(0.3, dur - 0.16))
        s = lerp(1.0, float(self.spec.get("escala_final", 0.66)), k)
        curva = lerp(0.0, float(self.spec.get("curva", 0.07)), cl(k * 2.2))
        card = lente(escala(im, s), curva)
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        cola_centro(cv, card, W / 2, H * lerp(0.5, 0.47, k))
        return cv


class Diagrama(Bloco):
    """Fundo #F2F2F2, a fala em preto grande e blocos coloridos chegando um a um, piscando cor
    (ref. 14,0-15,24 s)."""
    tipo = "diagrama"
    voz_padrao = "diagrama"

    def __init__(self, spec, t0, t1):
        super().__init__(spec, t0, t1)
        self.itens = [(T(it["em"]) if "em" in it else t0, it) for it in spec["itens"]]

    def fundo(self, fr, t):
        cv = Image.new("RGBA", (W, H), CLARO + (255,))
        larg_total = W * 0.86
        pesos = [float(it.get("larg", 1)) for _, it in self.itens]
        x = (W - larg_total) / 2
        y = H * float(self.spec.get("y", 0.53))
        hb = 74
        d = ImageDraw.Draw(cv)
        for (te, it), p in zip(self.itens, pesos):
            wb = larg_total * p / sum(pesos)
            k = (t - te) / 0.16
            if k >= 0:
                cor = hexa(it.get("cor", "#0F258D"))
                kk = ease_out(k)
                clara = 0.75 * (1 - cl(k))       # chega clarinho e firma (ref. q353-366)
                cor = tuple(int(lerp(c, 255, clara)) for c in cor)
                dx = 40 * (1 - kk)
                bloco = Image.new("RGBA", (int(wb) - 4, hb), cor + (255,))
                bloco.putalpha(mascara_arred(bloco.width, hb, 6).point(lambda v: int(v * (0.4 + 0.6 * kk))))
                if k < 1:
                    bloco = desfoca(com_margem(bloco, 12), 6 * (1 - kk))
                    cola(cv, bloco, int(x + dx) - 12, int(y) - 12)
                else:
                    cola(cv, bloco, int(x), int(y))
                rot = pinta(mascara_texto(it["texto"], "sans", 40, LAY["track"], 10), TINTA)
                cola_centro(cv, opaco(rot, kk), x + wb / 2, y - 34)
                d = ImageDraw.Draw(cv)
            x += wb
        return cv

    def eventos(self):
        return [(self.t0 - 0.12, "whoosh")] + [(te, "bipe") for te, _ in self.itens]


def recorte_video(arq: str, t_fonte: float, caixa: list, w: int, h: int) -> Image.Image:
    fv = video(arq)
    q = fv.quadro(t_fonte)
    x, y, cw = caixa[0], caixa[1], caixa[2]
    ch = cw * h / w
    if ch > fv.h:
        ch = fv.h
        cw = ch * w / h
    x = cl(x, 0, fv.w - cw)
    y = cl(y, 0, fv.h - ch)
    return q.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((w, h), Image.LANCZOS).convert("RGBA")


def caixa_em(lista: list[tuple[float, list]], t: float, dur: float = 0.45) -> list:
    """Interpola entre enquadramentos da gravação de tela (zoom suave no detalhe falado)."""
    atual = lista[0][1]
    for i, (te, cx) in enumerate(lista):
        if t < te:
            break
        k = ease_in_out((t - te) / dur)
        ant = lista[i - 1][1] if i else cx
        atual = [lerp(a, b, k) for a, b in zip(ant, cx)]
    return atual


class Dividida(Bloco):
    """Gravação de tela em cima (50%), a pessoa embaixo; legenda pequena na emenda (ref. 15,2-19,2 s)."""
    tipo = "dividida"
    voz_padrao = "base"

    def __init__(self, spec, t0, t1):
        super().__init__(spec, t0, t1)
        self.caixas = [(t0, spec["caixa"])] + [(T(c["em"]), c["caixa"]) for c in spec.get("zooms", [])]

    def t_fonte(self, t):
        return float(self.spec.get("t_fonte", 0)) + (t - self.t0) * float(self.spec.get("velocidade", 1.0))

    def fundo(self, fr, t):
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        cima = recorte_video(self.spec["fonte"], self.t_fonte(t), caixa_em(self.caixas, t), W, H // 2)
        cv.alpha_composite(cima, (0, 0))
        r = MED[grupo(t)]["rosto"]
        fcy = r[1] + r[3] / 2
        y0 = int(cl(fcy - (H // 2) * 0.44, 0, H - H // 2))
        cv.alpha_composite(fr.crop((0, y0, W, y0 + H // 2)), (0, H // 2))
        return cv


class Tela(Bloco):
    """Gravação de tela cheia com zoom no detalhe e contorno branco no item falado (ref. 19,2-23,0 s)."""
    tipo = "tela"
    voz_padrao = "base"

    def __init__(self, spec, t0, t1):
        super().__init__(spec, t0, t1)
        self.caixas = [(t0, spec["caixa"])] + [(T(c["em"]), c["caixa"]) for c in spec.get("zooms", [])]
        self.contornos = [(T(c["em"]), c) for c in spec.get("contornos", [])]

    def fundo(self, fr, t):
        tf = float(self.spec.get("t_fonte", 0)) + (t - self.t0) * float(self.spec.get("velocidade", 1.0))
        cx = caixa_em(self.caixas, t)
        im = recorte_video(self.spec["fonte"], tf, cx, W, H)
        fv = video(self.spec["fonte"])
        cw = cx[2]
        ch = min(fv.h, cw * H / W)
        cw = ch * W / H
        x0 = cl(cx[0], 0, fv.w - cw)
        y0 = cl(cx[1], 0, fv.h - ch)
        s = W / cw
        d = ImageDraw.Draw(im)
        for te, c in self.contornos:
            if t >= te and t < T(c["ate"]) if "ate" in c else t >= te:
                bx, by, bw, bh = c["caixa"]
                k = ease_out((t - te) / 0.15)
                pad = 10 * (1 - k)
                cor = hexa(c.get("cor", self.spec.get("cor_contorno", "#141414")))   # ref. branco em UI escura
                d.rounded_rectangle(((bx - x0) * s - pad, (by - y0) * s - pad, (bx + bw - x0) * s + pad,
                                     (by + bh - y0) * s + pad), radius=12, outline=cor + (int(255 * k),),
                                    width=7)
        return im


class Retrospectiva(Bloco):
    """Fundo #F2F2F2 com o que foi ensinado em card central (~44% da largura), corte seco (ref. 31,2-32,9 s)."""
    tipo = "retrospectiva"
    voz_padrao = "sussurro_card"

    def fundo(self, fr, t):
        cv = Image.new("RGBA", (W, H), CLARO + (255,))
        arqs = self.spec["arquivos"]
        qs = self.spec.get("quadros", [7])
        n = int((t - self.t0) * FPS)
        acc, i = 0, 0
        while True:
            q = qs[i] if i < len(qs) else qs[-1]
            if n < acc + q or i >= len(arqs) - 1:
                break
            acc += q
            i += 1
        cw = int(W * float(self.spec.get("larg", 0.44)))
        chh = int(cw * 16 / 9)
        it = arqs[i]
        arq, foco = (it, (0.5, 0.0)) if isinstance(it, str) else (it["arquivo"], tuple(it.get("foco", (0.5, 0.0))))
        card = cobre(imagem(arq), cw, chh, foco)
        if n - acc < 1 and i == 0:
            card = pb(card)
        sombra = Image.new("RGBA", (cw + 80, chh + 80), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rectangle((40, 50, cw + 40, chh + 50), fill=(0, 0, 0, 60))
        cola_centro(cv, sombra.filter(ImageFilter.GaussianBlur(18)), W / 2, H / 2)
        cola_centro(cv, card.convert("RGBA"), W / 2, H / 2)
        return cv


TIPOS = {"rosto": Rosto, "respiro": Respiro, "abertura": Abertura, "macro": Macro, "outros": Outros,
         "diagrama": Diagrama, "dividida": Dividida, "tela": Tela, "retrospectiva": Retrospectiva}


def monta_blocos() -> list[Bloco]:
    specs = sorted([(T(b["em"]), b) for b in MAPA.get("blocos", [])], key=lambda x: x[0])
    out: list[Bloco] = []
    cursor = 0.0
    for i, (t0, b) in enumerate(specs):
        prox = specs[i + 1][0] if i + 1 < len(specs) else TOTAL
        t1 = min(T(b["ate"]), prox) if "ate" in b else prox
        if t0 > cursor + 1e-6:   # buraco = rosto
            out.append(Rosto({}, cursor, t0, bool(out) and out[-1].tipo != "rosto"))
        if b["tipo"] == "rosto":
            out.append(Rosto(b, t0, t1, bool(out) and out[-1].tipo != "rosto"))
        else:
            out.append(TIPOS[b["tipo"]](b, t0, t1))
        cursor = t1
    if cursor < TOTAL - 1e-6:
        out.append(Rosto({}, cursor, TOTAL, bool(out) and out[-1].tipo != "rosto"))
    return out


BLOCOS = monta_blocos()


def bloco_em(t: float) -> Bloco:
    for b in BLOCOS:
        if b.ativo(t):
            return b
    return BLOCOS[-1]


# ================================================================ PALAVRAS (uma por vez, cada uma na sua voz)
def monta_palavras() -> list[dict]:
    ov = {}
    for e in MAPA.get("palavras", []):
        ov[acha(e["em"][0], int(e["em"][1]))] = e
    out, i = [], 0
    while i < len(WORDS):
        w = WORDS[i]
        if not any(c.isalnum() for c in w["t"]):
            i += 1
            continue
        e = ov.get(i)
        j = acha(e["ate"][0], int(e["ate"][1])) if e and "ate" in e else i
        txt = e.get("texto") if e and e.get("texto") else " ".join(WORDS[k]["t"].strip() for k in range(i, j + 1))
        txt = txt.strip().rstrip(",;:")
        out.append({"txt": txt, "voz": e.get("voz") if e else None, "ini": max(0.0, w["s"] - ANTECIPA),
                    "e": WORDS[j]["e"], "seg": w["seg"], "some": bool(e and e.get("some"))})
        i = j + 1
    for k, p in enumerate(out):
        prox = out[k + 1]["ini"] if k + 1 < len(out) else TOTAL
        p["fim"] = prox if prox - p["e"] < 0.5 else p["e"] + 0.2
    return out


PALAVRAS = monta_palavras()
_PAL_INI = [p["ini"] for p in PALAVRAS]


def palavra_em(t: float) -> dict | None:
    k = bisect.bisect_right(_PAL_INI, t) - 1
    if k >= 0 and PALAVRAS[k]["ini"] <= t < PALAVRAS[k]["fim"]:
        return PALAVRAS[k]
    return None


@functools.lru_cache(maxsize=2048)
def img_voz(txt: str, voz: str, contexto: str) -> Image.Image:
    """A imagem da palavra em cada voz. contexto = claro (fundo claro da gravação, bege/branco) | escuro | branco."""
    tr = LAY["track"]
    escuro = contexto == "escuro"
    sombra = 0.0 if escuro else 0.75
    div = contexto == "dividida"
    if voz == "sussurro":
        cor = BRANCO if contexto == "preto" else TINTA
        return pinta(mascara_texto(txt, "sans", LAY["sussurro_tam"], -0.01, 8), cor)
    if voz == "sussurro_card":
        return pinta(mascara_texto(txt, "sans", 34, -0.01, 16), TINTA)
    if voz == "diagrama":
        m = mascara_texto(txt, "sans", LAY["diagrama_tam"], -0.035, 30)
        if m.width > W * 0.92:
            m = m.resize((int(W * 0.92), int(m.height * W * 0.92 / m.width)), Image.LANCZOS)
        return pinta(m, TINTA)
    if contexto == "tela":   # interface clara: palavra branca numa caixa escura translúcida
        im = img_voz(txt, voz, "escuro")
        bb = im.getchannel("A").point(lambda v: 255 if v > 200 else 0).getbbox() or (0, 0, im.width, im.height)
        px, py = 34, 18
        caixa = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(caixa).rounded_rectangle((bb[0] - px, bb[1] - py, bb[2] + px, bb[3] + py), radius=22,
                                                fill=(18, 18, 20, 175))
        caixa.alpha_composite(im)
        return caixa
    if voz == "base":
        tam = LAY["div_base_tam"] if div else LAY["base_tam"]
        return pinta(mascara_texto(txt, "sans", tam, tr, 24), BRANCO, brilho=0.0, sombra=0.95, tam=tam)
    if voz == "destaque":
        tam = LAY["div_destaque_tam"] if div else LAY["destaque_tam"]
        m = mascara_texto(txt, "sans", tam, -0.035, 70)
        if m.width > W * 0.94:
            m = m.resize((int(W * 0.94), int(m.height * W * 0.94 / m.width)), Image.LANCZOS)
        return pinta(m, BRANCO, brilho=0.9, sombra=sombra * 0.8, tam=tam)
    if voz == "italico":
        tam = LAY["div_italico_tam"] if div else LAY["italico_tam"]
        m = mascara_texto(txt, "italica", tam, -0.01, 60, grossa=5)
        if m.width > W * 0.94:
            m = m.resize((int(W * 0.94), int(m.height * W * 0.94 / m.width)), Image.LANCZOS)
        return pinta(m, BRANCO, brilho=0.85, sombra=sombra * 0.8, tam=tam)
    # garrafal
    tam = LAY["garrafal_tam"]
    m = mascara_texto(txt, "sans", tam, -0.04, 90)
    lim = W * LAY["garrafal_larg"] + 180
    if m.width > lim:
        m = m.resize((int(lim), int(m.height * lim / m.width)), Image.LANCZOS)
    return pinta(m, BRANCO, brilho=1.0, sombra=0.5, tam=tam * min(1, lim / max(1, m.width)))


def contexto_de(b: Bloco) -> str:
    if b.tipo == "tela":
        return "tela"
    if b.tipo in ("abertura", "macro", "outros"):
        return "escuro"
    if b.tipo == "respiro":
        return "preto" if b.spec.get("cor") == "preto" else "branco"
    if b.tipo == "dividida":
        return "dividida"
    return "claro"


def voz_de(p: dict, b: Bloco) -> str:
    if b.tipo == "respiro":
        return "sussurro"
    if b.tipo == "diagrama":
        return "diagrama"
    if b.tipo == "retrospectiva":
        return "sussurro_card"
    if b.tipo == "dividida" and p["voz"] in ("garrafal",):
        return "destaque"
    return p["voz"] or b.spec.get("voz") or b.voz_padrao


def y_da_palavra(voz: str, b: Bloco, t: float) -> float:
    if b.tipo == "dividida":   # logo abaixo da emenda: em cima é interface clara e come a letra branca
        return H / 2 + float(LAY.get("div_desce", 0.62)) * {"base": LAY["div_base_tam"], "destaque": LAY["div_destaque_tam"],
                                                         "italico": LAY["div_italico_tam"]}.get(voz, 60)
    if b.tipo == "diagrama":
        return H * float(b.spec.get("titulo_y", 0.40))
    if b.tipo in ("respiro", "retrospectiva"):
        return H * 0.5 if b.tipo == "respiro" else H * 0.5 + W * float(b.spec.get("larg", 0.44)) * 16 / 18 + 60
    if b.tipo == "rosto" and voz != "garrafal":
        c = cabeca(t, b.cam(t))
        return cl(c["queixo"] + LAY["leg_queixo"], H * LAY["leg_min"], H * LAY["leg_max"])
    return H * float(b.spec.get("texto_y", 0.5))


def desenha_palavra(cv: Image.Image, b: Bloco, t: float) -> None:
    p = palavra_em(t)
    if p is None or p["some"]:
        return
    voz = voz_de(p, b)
    im = img_voz(p["txt"], voz, contexto_de(b))
    d = t - max(p["ini"], b.t0)
    dur = {"base": 0.06, "sussurro": 0.06, "sussurro_card": 0.06, "garrafal": 0.10}.get(voz, 0.16)
    k = cl(d / dur)
    if k < 1:   # nada aparece pronto: entra translúcida, desfocada e um pouco maior e firma
        kk = ease_out(k)
        im = opaco(desfoca(escala(com_margem(im, 12), lerp(1.07, 1.0, kk)), 9 * (1 - kk)), lerp(0.3, 1.0, kk))
    cola_centro(cv, im, W / 2, y_da_palavra(voz, b, t))


# ================================================================ PALAVRA-CONCEITO atrás da cabeça
@functools.lru_cache(maxsize=32)
def img_conceito(txt: str) -> tuple[Image.Image, Image.Image]:
    """(halo escuro + brilho, letra) — a letra separada pra aplicar o vidro por cima do cabelo."""
    alt = LAY["conceito_alt"]
    tam = int(alt / 0.70)                   # maiúscula da Bodoni ~0,70 do corpo
    m = mascara_texto(txt.upper(), "conceito", tam, -0.10, 80)
    m = m.resize((max(2, int(m.width * LAY["conceito_aperta"])), m.height), Image.LANCZOS)
    lim = W * LAY["conceito_larg"] + 160
    if m.width > lim:
        m = m.resize((int(lim), int(m.height * lim / m.width)), Image.LANCZOS)
    fundo = Image.new("RGBA", m.size, (0, 0, 0, 0))
    fundo.alpha_composite(sombra_de(m, 34, 0.75, PRETO))     # halo escuro: separa de parede clara (bege/branca)
    fundo.alpha_composite(sombra_de(m, 26, 0.70, BRANCO))    # brilho (ref. HOOK aceso)
    fundo.alpha_composite(sombra_de(m, 8, 0.85, BRANCO))
    letra = Image.new("RGBA", m.size, BRANCO + (255,))
    letra.putalpha(m)
    return fundo, letra


class Conceito:
    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T(spec["ate"]) if "ate" in spec else self.t0 + 1.6

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def camada(self, t: float) -> tuple[Image.Image, Image.Image, Image.Image]:
        """(tela inteira do conceito, só a letra, alfa total) já com a animação: entra cinza e translúcida,
        acende em ~6 quadros (ref. q75-81), sai com desfoque."""
        fundo, letra = img_conceito(self.spec["texto"])
        k = ease_out((t - self.t0) / 0.22)
        sai = cl((self.t1 - t) / 0.12)
        a = min(k, sai)
        cinza = 1 - k
        le = letra.copy()
        if cinza > 0:
            v = int(255 - 120 * cinza)
            le = Image.new("RGBA", letra.size, (v, v, v, 255))
            le.putalpha(letra.getchannel("A"))
        comp = Image.new("RGBA", letra.size, (0, 0, 0, 0))
        comp.alpha_composite(opaco(fundo, a * (0.35 + 0.65 * k)))
        comp.alpha_composite(opaco(le, lerp(0.55, 1.0, k) * a))
        if sai < 1:
            comp = desfoca(comp, 10 * (1 - sai))
        s = lerp(1.04, 1.0, k)
        comp = escala(comp, s) if s != 1 else comp
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        topo = int(self.spec.get("topo", LAY["conceito_topo"]))
        # a máscara tem margem de 80 px em cima: alinha o topo da LETRA
        bb = letra.getchannel("A").getbbox() or (0, 0, letra.width, letra.height)
        cola(cv, comp, int(W / 2 - comp.width / 2), int(topo - bb[1] * s))
        return cv


CONCEITOS = sorted([Conceito(s) for s in MAPA.get("conceitos", [])], key=lambda c: c.t0)


def janelas_mascara() -> list[tuple[float, float]]:
    js = sorted((c.t0 - 0.05, c.t1 + 0.1) for c in CONCEITOS)
    out = []
    for a, b in js:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


_MASC = {"n": None, "im": None}


def mascara(n: int) -> Image.Image | None:
    if _MASC["n"] != n:
        p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
        _MASC["n"], _MASC["im"] = n, (Image.open(p).convert("L").filter(ImageFilter.GaussianBlur(1.2))
                                      if p.exists() else None)
    return _MASC["im"]


# ================================================================ LUZ
def estouro(cv: Image.Image, t: float, b: Bloco) -> Image.Image:
    """A imagem clareia 3-4 quadros e corta seco (ref. q45-48, brilho 63→76)."""
    if not b.estouro:
        return cv
    d = b.t1 - t
    if d > 4 * QD:
        return cv
    k = 1 - d / (4 * QD)
    rgb = cv.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(1 + 0.45 * k)
    glow = rgb.filter(ImageFilter.GaussianBlur(30))
    rgb = ImageChops.screen(rgb, ImageEnhance.Brightness(glow).enhance(0.35 * k))
    return rgb.convert("RGBA")


# ================================================================ composição
def compoe(fr: Image.Image, t: float, n: int) -> Image.Image:
    b = bloco_em(t)
    cv = b.fundo(fr, t).copy()
    if b.tipo == "rosto":
        cs = [c for c in CONCEITOS if c.ativo(t)]
        if cs:
            cam = b.cam(t)
            cam_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for c in cs:
                cam_layer.alpha_composite(c.camada(t))
            atras = b.fundo(fr, t)   # mesma imagem, pra recortar a pessoa por cima
            cv.alpha_composite(cam_layer)
            m = mascara(n)
            if m is not None:
                mt = aplica_camera(m, cam, Image.BILINEAR)
                pessoa = atras.copy()
                pessoa.putalpha(mt)
                cv.alpha_composite(pessoa)
                # vidro: a palavra continua lendo por cima do cabelo, nunca sobre o rosto
                rx0, ry0, rx1, ry1 = cabeca(t, cam)["rosto"]
                proib = Image.new("L", (W, H), 0)
                ImageDraw.Draw(proib).ellipse((rx0 - 20, ry0 - 70, rx1 + 20, ry1 + 120), fill=255)
                proib = proib.filter(ImageFilter.GaussianBlur(30))
                a = ImageChops.multiply(cam_layer.getchannel("A"), mt.point(lambda v: int(v * LAY["conceito_vidro"])))
                a = ImageChops.subtract(a, proib)
                vidro = cam_layer.copy()
                vidro.putalpha(a)
                cv.alpha_composite(vidro)
    desenha_palavra(cv, b, t)
    return estouro(cv, t, b)


# ================================================================ áudio (voz + efeitos; trilha só com arquivo do usuário)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome == "riser":     # tom que sobe sob a abertura (ref. 0-0,8 s, linha diagonal no espectro)
        d = 0.85
        n = int(d * SR)
        tt = np.arange(n) / SR
        fr = 300 * (8 ** (tt / d))
        x = np.sin(2 * np.pi * np.cumsum(fr) / SR) * (tt / d) ** 1.5
        ruido = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * (np.fft.rfftfreq(n, 1 / SR) > 2500), n)
        x = x * 0.6 + ruido / (np.abs(ruido).max() + 1e-9) * (tt / d) ** 2 * 0.4
        x *= np.where(tt > d - 0.03, (d - tt) / 0.03, 1)
        return x / (np.abs(x).max() + 1e-9)
    if nome == "whoosh":
        n = int(0.30 * SR)
        esp = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= np.exp(-((np.log(f + 1) - np.log(2400)) ** 2) / 0.9)
        x = np.fft.irfft(esp, n) * _env(n, 0.6)
        return x / (np.abs(x).max() + 1e-9)
    if nome == "bipe":      # bipe curto de interface (ref. 13,4-14,5 s)
        n = int(0.07 * SR)
        tt = np.arange(n) / SR
        x = np.sin(2 * np.pi * 1760 * tt) * np.exp(-tt * 55)
        return x * 0.5
    # tique: clique seco na troca de B-roll
    n = int(0.03 * SR)
    tt = np.arange(n) / SR
    return rng.standard_normal(n) * np.exp(-tt * 260) * 0.35


def eventos_som() -> list[tuple[float, str]]:
    ev = []
    for b in BLOCOS:
        ev += b.eventos()
    return sorted(e for e in ev if e[0] >= 0)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -26) if isinstance(cfg, dict) else -26
        for t, nome in eventos_som():
            ganho = {"riser": 0.8, "bipe": 0.8, "tique": 0.7}.get(nome, 1.0)
            s = sfx(nome) * 10 ** (gdb / 20) * ganho
            i = int(max(0, t) * SR)
            pista[i:i + len(s)] += s[: len(pista) - i]
    mus = MAPA.get("musica")   # ref. tem trilha 8-12 dB abaixo da voz; só com arquivo e licença do usuário
    if mus:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mus.get("inicio", 0)), "-i", str(_resolve(mus["arquivo"])),
                              "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = int(TOTAL * SR)
        x = np.tile(x, n // len(x) + 1)[:n]
        x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 10 ** (mus.get("db", -28) / 20)
        fade = int(1.5 * SR)
        x[-fade:] *= np.linspace(1, 0, fade)
        pista[:n] += x
    return pista[: int(TOTAL * SR)]


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


# ================================================================ main
def resumo() -> None:
    print("blocos:")
    for b in BLOCOS:
        print(f"  {b.t0:6.2f}-{b.t1:6.2f} {b.tipo}{'  +estouro' if b.estouro else ''}")
    for c in CONCEITOS:
        print(f"  {c.t0:6.2f}-{c.t1:6.2f} conceito {c.spec['texto']}")
    trocas = len(BLOCOS) + sum(len(getattr(b, 'clipes', [])) for b in BLOCOS)
    print(f"  {trocas} trocas de tela em {TOTAL:.1f}s: uma a cada {TOTAL / max(1, trocas):.1f}s (ref. ~1,1 s)")
    longos = [b for b in BLOCOS if b.tipo == "rosto" and b.t1 - b.t0 > 4.5 and not any(
        c.t0 < b.t1 and c.t1 > b.t0 for c in CONCEITOS)]
    for b in longos:
        print(f"  ATENÇÃO: {b.t1 - b.t0:.1f}s de rosto sem troca ({b.t0:.2f}-{b.t1:.2f})")
    vozes = {}
    for p in PALAVRAS:
        v = voz_de(p, bloco_em(p["ini"] + 0.01))
        vozes[v] = vozes.get(v, 0) + 1
    print("  vozes:", ", ".join(f"{k} {v}" for k, v in sorted(vozes.items())))


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_SB = {"respiro": "Respiro em tela {cor}", "macro": "B-roll macro P&B", "outros": "Os outros em P&B (moldura encolhe)",
            "diagrama": "Diagrama no branco", "dividida": "Tela dividida (gravação em cima, a pessoa embaixo)",
            "tela": "Gravação de tela cheia", "retrospectiva": "Retrospectiva em cards",
            "garrafal": "Palavra garrafal", "destaque": "Destaque com brilho", "italico": "Serifa itálica"}


def _falta_arquivo(motivo) -> Image.Image:
    """Quadro no lugar de um arquivo que não existe (o storyboard não pode morrer por isso)."""
    im = Image.new("RGBA", (W, H), (40, 0, 8, 255))
    ImageDraw.Draw(im).multiline_text((60, H / 2), "FALTA ARQUIVO\n" + str(motivo), font=F("sans", 44),
                                      fill=(255, 120, 130, 255), anchor="lm")
    return im


def storyboard() -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1, t0=0.0: max(t0, min(t, t1 - 0.05))
    br = lambda s: s.replace(".", ",")
    ms, avisos = [], []

    def falas(b: Bloco) -> str:
        return " ".join(p["txt"] for p in PALAVRAS if b.t0 <= p["ini"] + 0.01 < b.t1 and not p["some"])

    # ---- blocos de tela (com câmera e transições de luz)
    for b in BLOCOS:
        if b.tipo == "rosto":
            if b.vem_de_outro and b.spec.get("foco", True):
                ms.append({"t0": b.t0, "t1": b.t1, "quadro": cap(b.t0 + 0.06, b.t1, b.t0),
                           "tipo": "Volta pro rosto: desfoque → foco",
                           "desc": f"entra desfocada e firma em {float(b.spec.get('foco_dur', 0.30)):.2f} s"
                           .replace(".", ",")})
            if b.z > 1.0005:
                ms.append({"t0": b.t0, "t1": b.t1, "quadro": cap(b.t0 + 0.5, b.t1, b.t0), "tipo": "Câmera: mais perto",
                           "desc": br(f"rosto a {b.z:.2f}x nesta tomada")})
        elif b.tipo == "abertura":
            for i, (a, c_fim, c) in enumerate(b.clipes, 1):
                q = c.get("quadros")
                ms.append({"t0": a, "t1": c_fim, "quadro": cap((a + c_fim) / 2, c_fim + 0.05, a),
                           "tipo": f"Abertura: B-roll {i}/{len(b.clipes)}" + (f" ({q} quadros)" if q else " (plano longo)"),
                           "desc": f"{c['arquivo']}" + (" · 1º quadro em P&B" if i == 1 else "")})
        elif b.tipo == "macro":
            for i, (a, c) in enumerate(b.clipes):
                c_fim = b.clipes[i + 1][0] if i + 1 < len(b.clipes) else b.t1
                ms.append({"t0": a, "t1": c_fim, "quadro": cap(a + 0.25, c_fim, a),
                           "tipo": NOMES_SB["macro"] + (f" {i + 1}/{len(b.clipes)}" if len(b.clipes) > 1 else ""),
                           "desc": c["arquivo"] + ("" if b.spec.get("pb", True) else " (colorido)")})
        else:
            m = {"t0": b.t0, "t1": b.t1, "tipo": NOMES_SB[b.tipo].format(
                cor="preta" if b.spec.get("cor") == "preto" else "branca"), "quadro": cap(b.t0 + 0.4, b.t1, b.t0)}
            if b.tipo == "respiro":
                m["desc"] = f'"{falas(b)}"' if falas(b) else "sem palavra"
            elif b.tipo == "outros":
                m["quadro"] = cap(b.t1 - 0.3, b.t1, b.t0)
                m["desc"] = f"a cena da pessoa em P&B vira card sobre preto (até {float(b.spec.get('escala_final', 0.66)):.0%})"
            elif b.tipo == "diagrama":
                m["quadro"] = cap(max(te for te, _ in b.itens) + 0.3, b.t1, b.t0)
                m["desc"] = f'título "{falas(b)}" — blocos: ' + " · ".join(it["texto"] for _, it in b.itens)
            elif b.tipo in ("dividida", "tela"):
                m["quadro"] = cap(b.t0 + 0.5, b.caixas[1][0] if len(b.caixas) > 1 else b.t1, b.t0)
                m["desc"] = f"{b.spec['fonte']} a partir de {br(str(b.spec.get('t_fonte', 0)))} s"
            elif b.tipo == "retrospectiva":
                arqs = [a if isinstance(a, str) else a["arquivo"] for a in b.spec["arquivos"]]
                qs = b.spec.get("quadros", [7])
                ini_ult = sum((qs[i] if i < len(qs) else qs[-1]) for i in range(len(arqs) - 1))
                m["quadro"] = cap(b.t0 + (ini_ult + 3) / FPS, b.t1, b.t0)
                m["desc"] = "cards em corte seco: " + ", ".join(arqs)
            ms.append(m)
            if b.tipo in ("dividida", "tela"):
                for i, (te, cx) in enumerate(b.caixas[1:], 1):
                    prox = b.caixas[i + 1][0] if i + 1 < len(b.caixas) else b.t1
                    ms.append({"t0": te, "t1": prox, "quadro": cap(te + 0.5, prox, te), "tipo": "Zoom na gravação",
                               "desc": f"enquadra o detalhe (x {cx[0]}, y {cx[1]}, largura {cx[2]} px da gravação)"})
            if b.tipo == "tela":
                for te, c in b.contornos:
                    fim = T(c["ate"]) if "ate" in c else b.t1
                    ms.append({"t0": te, "t1": fim, "quadro": cap(te + 0.25, fim, te), "tipo": "Contorno no item falado",
                               "desc": f"caixa {c['caixa']} em {c.get('cor', b.spec.get('cor_contorno', '#141414'))}"})
        if b.estouro:
            te = b.t1 - 4 * QD
            ms.append({"t0": te, "t1": b.t1, "quadro": cap(b.t1 - QD, b.t1, te), "tipo": "Luz: estouro antes do corte",
                       "desc": "a imagem clareia 4 quadros e corta seco"})

    # ---- palavra-conceito atrás da cabeça
    for c in CONCEITOS:
        m = {"t0": c.t0, "t1": c.t1, "quadro": cap(c.t0 + 0.35, c.t1, c.t0),
             "tipo": "Palavra-conceito atrás da cabeça", "desc": c.spec["texto"]}
        if c.t1 - c.t0 < 1.0:
            m["aviso"] = br(f"fica só {c.t1 - c.t0:.1f} s (a referência segura ~1,4 s)")
        ms.append(m)

    # ---- palavras nas vozes grandes (a voz já resolvida pelo bloco em que caem)
    for p in PALAVRAS:
        if p["some"]:
            continue
        b = bloco_em(p["ini"] + 0.01)
        voz = voz_de(p, b)
        if voz not in ("garrafal", "destaque", "italico"):
            continue
        fim = min(p["fim"], b.t1)
        ms.append({"t0": p["ini"], "t1": p["fim"], "quadro": cap(max(p["ini"], b.t0) + 0.22, fim, p["ini"]),
                   "tipo": NOMES_SB[voz] + (" (caixa escura)" if b.tipo == "tela" else ""), "desc": f'"{p["txt"]}"'})

    # ---- avisos globais (os mesmos do resumo)
    trocas = len(BLOCOS) + sum(len(getattr(b, 'clipes', [])) for b in BLOCOS)
    avisos.append(br(f"{trocas} trocas de tela em {TOTAL:.1f} s: uma a cada {TOTAL / max(1, trocas):.1f} s")
                  + " (referência ~1,1 s)")
    for b in BLOCOS:
        if b.tipo == "rosto" and b.t1 - b.t0 > 4.5 and not any(c.t0 < b.t1 and c.t1 > b.t0 for c in CONCEITOS):
            avisos.append(br(f"{b.t1 - b.t0:.1f} s de rosto sem troca de tela ({b.t0:.1f}–{b.t1:.1f} s)"))

    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]
    arqs = []
    for spec in MAPA.get("blocos", []):
        nomes = [c.get("arquivo") for c in spec.get("clipes", [])] + [spec.get("fonte")]
        nomes += [a if isinstance(a, str) else a.get("arquivo") for a in spec.get("arquivos", [])]
        for a in nomes:
            if a and a not in [x for x, _ in arqs]:
                try:
                    _resolve(a); ok = True
                except SystemExit:
                    ok = False
                arqs.append((a, ok))
    if MAPA.get("musica"):
        a = MAPA["musica"]["arquivo"]
        try:
            _resolve(a); ok = True
        except SystemExit:
            ok = False
        arqs.append((a, ok))

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        try:
            return compoe(quadro_base(n), t, n)
        except SystemExit as e:
            return _falta_arquivo(e.code)

    out = SB.gerar(EDIT, "Garrafal", TOTAL, cenas, ms, quadro, avisos, arqs)
    for fv in _FONTES_VIDEO.values():
        if fv.proc:
            fv.proc.kill()
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if CONCEITOS and not (EDIT / "masks" / "out").exists():
        sys.exit("tem palavra-conceito atrás da pessoa: rode mascaras.py antes")
    resumo()
    modo = "final" if ARGS.final else "preview"

    if ARGS.storyboard:
        storyboard()
        return

    if ARGS.so_quadros:
        pasta = EDIT / "verify" / "quadros"
        pasta.mkdir(parents=True, exist_ok=True)
        for ts in ARGS.so_quadros.split(","):
            t = float(ts)
            n = round(t * FPS)
            compoe(quadro_base(n), t, n).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
        print(f"prévias em {pasta}")
        return

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(BASE), "-vn", "-ac", "2", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    voz = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, 2) / 32768
    extra = trilha_extra()
    n = min(len(voz), len(extra))
    mix = voz[:n] + extra[:n, None]
    wav = EDIT / f"mix_{modo}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(BASE), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    prenorm = EDIT / f"{modo}_garrafal.prenorm.mp4"
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
        enc.stdin.write(compoe(fr, t, k).convert("RGB").tobytes())
        k += 1
        if k % 150 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    for fv in _FONTES_VIDEO.values():
        if fv.proc:
            fv.proc.kill()
    out = EDIT / f"{modo}_garrafal.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
