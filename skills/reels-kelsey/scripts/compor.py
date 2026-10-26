"""compor.py — monta o Reel no estilo "Kelsey" quadro a quadro, a partir do mapa.json.

Estilo medido na referência (referencia/referencias-estilo.md): capa de revista em movimento. A pessoa fica na
tela inteira; as palavras fortes viram TÍTULO em serifa grande ATRÁS da cabeça (recorte da pessoa por cima),
montado palavra por palavra na fala, com a palavra-chave em degradê lilás. Dados viram objetos neon
(número enchendo, arco, barra que conta), itens viram pílulas que nascem de um ponto, e o material real
da pessoa aparece em 3D (prints em livro aberto, cards orbitando, muro de fotos, print em tela cheia com caneta).
O ritmo vem da câmera: degraus de zoom por corte seco, aproximação suave, flash branco com zoom out.

Cada quadro tem três camadas:
  atrás   títulos, número/arco "atrás", muro, livro, metade de trás dos cards
  pessoa  o próprio vídeo recortado pelo Vision (masks/out) — só quando há algo atrás
  frente  legenda pequena, pílulas, lista, notificação, balões, ícones, barra, objeto, cronômetro

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_kelsey.mp4 | final_kelsey.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov | base_final.mov, masks/out (mascaras.py), imagens em <edit>/assets/.
"""

from __future__ import annotations

import argparse
import bisect
import functools
import itertools
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # nome, @, cor de destaque e foto do criador (perfil.json)

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


ANTECIPA = float(MAPA.get("antecipa", 0.06))


def T(spec) -> float:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] (ANTECIPA s antes da palavra) |
    [palavra, tomada, atraso] (atraso explícito em relação ao início da palavra)."""
    if isinstance(spec, (int, float)):
        return float(spec)
    w = WORDS[acha(spec[0], int(spec[1]))]
    d = float(spec[2]) if len(spec) > 2 else -ANTECIPA
    return max(0.0, w["s"] + d)


def grupo(t: float) -> int:
    return max(0, min(_NG - 1, bisect.bisect_right(OFF, t) - 1))


def T_fim(spec_ate, spec_em) -> float:
    """Sem "ate": vai até o fim da tomada do "em"."""
    if spec_ate is not None:
        return T(spec_ate)
    return OFF[int(spec_em[1]) + 1] if isinstance(spec_em, list) else OFF[grupo(float(spec_em)) + 1]


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    x = cl(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def mola(x: float) -> float:
    """Passa do tamanho e volta (pulo dos ícones)."""
    x = cl(x)
    c1 = 1.9
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clareia(c: tuple, f: float) -> tuple:
    return tuple(int(v + (255 - v) * f) for v in c)


def escurece(c: tuple, f: float) -> tuple:
    return tuple(int(v * f) for v in c)


# ---------------------------------------------------------------- cores (medidas na referência)
DESTAQUE = hexa(MAPA.get("destaque", "#7A5AD3"))      # palavra-chave do título: começo do degradê (roxo)
DESTAQUE2 = hexa(MAPA.get("destaque2", "#D9B8F7"))    # fim do degradê (lilás claro)
NEON = hexa(MAPA.get("neon", "#FC49C2"))              # número, arco, barra (rosa neon)
BORDA_PILULA = hexa(MAPA.get("borda_pilula", "#FF2D55"))   # pílula escura (v1: vermelho; v2: rosa)
VIDRO = hexa(MAPA.get("vidro", "#7A4FD8"))            # pílula de vidro (v4: roxo)
CANETA = hexa(MAPA.get("caneta", "#EC280B"))          # círculo à mão sobre o print
BRANCO = (255, 255, 255)
TINTA = (12, 12, 14)

# ---------------------------------------------------------------- fontes
_SF, _SFI, _SFR = "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/SFNSItalic.ttf", "/System/Library/Fonts/SFNSRounded.ttf"
_BOD = "/System/Library/Fonts/Supplemental/Bodoni 72.ttc"
_HN = "/System/Library/Fonts/HelveticaNeue.ttc"
FONTES = {
    "serifa": (_BOD, 2, None), "serifa_it": (_BOD, 1, None),           # títulos (Bodoni 72 Bold / Book Italic)
    "leve": (_SF, 0, "Light"), "leve_it": (_SFI, 0, "Light Italic"),   # legenda da fala
    "sans": (_SF, 0, "Bold"), "sans_semi": (_SF, 0, "Semibold"), "sans_reg": (_SF, 0, "Regular"),
    "sans_medio": (_SF, 0, "Medium"), "redonda": (_SFR, 0, "Bold"), "redonda_semi": (_SFR, 0, "Semibold"),
    # Helvetica Neue: legenda (v1 itálica de peso normal, v4 fina), palavra de ligação e notificação
    "hn_it": (_HN, 11, None), "hn_fino": (_HN, 7, None), "hn_ultra": (_HN, 5, None),
    "hn_reg": (_HN, 0, None), "hn_bold": (_HN, 1, None), "hn_medio": (_HN, 10, None),
}


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, idx, var = FONTES[tipo]
    f = ImageFont.truetype(arq, max(6, int(size)), index=idx)
    if var:
        f.set_variation_by_name(var)
    return f


for _k in FONTES:
    F(_k, 20)

# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "topo": 150,            # nada sobe acima disto (barra do Instagram)
    "base": 0.76,           # nada desce além disto (legenda e botões do Instagram)
    "tit_largura": 0.94,    # título: linha mais longa ocupa até isto da largura (referência: 75-130%)
    "tit_max": 300,         # título: maior corpo de letra
    "tit_min": 110,
    "tit_sobre": 0.34,      # título atrás da cabeça: fração da altura do bloco que desce por trás do cabelo
    "tit_escada": 0.06,     # deslocamento lateral alternado das linhas (escada)
    "tit_track": -0.035,    # letras mais juntas (a referência é bem apertada)
    "leg_tam": 60,          # legenda da fala (Helvetica Neue Medium Italic, v1)
    "leg_queixo": 240,      # legenda: tantos px abaixo do queixo (base do "rosto" do Vision)
    "leg_min": 0.50, "leg_max": 0.70,
    "rosto_cy": 0.40,       # zoom: centro do rosto nesta fração da altura do recorte
}
LAY.update(MAPA.get("layout", {}))
# legenda da referência: Helvetica Neue com letras juntas. "italico" = v1 ("a reason", "followers"),
# "fino" = v4 ("homeowners", "attention in")
LEG_ESTILO = MAPA.get("legenda_estilo", "italico")
LEG_FONTE = {"italico": "hn_it", "fino": "hn_fino", "ultrafino": "hn_ultra"}.get(LEG_ESTILO, "hn_it")


# ---------------------------------------------------------------- utilidades de imagem
def cola_centro(dest: Image.Image, im: Image.Image | None, cx: float, cy: float) -> None:
    if im is None:
        return
    x, y = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
    cola(dest, im, x, y)


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


def surge(im: Image.Image | None, k: float, escala0: float = 0.86, raio0: float = 14) -> Image.Image | None:
    """Entrada padrão: nasce um pouco menor, borrado e transparente e assenta."""
    if im is None or k <= 0:
        return None
    if k >= 1:
        return im
    k = ease_out(k)
    r = raio0 * (1 - k)
    out = escala(com_margem(im, int(r * 2) + 2), lerp(escala0, 1, k))
    return opaco(desfoca(out, r), k)


def k_in(t: float, t0: float, d: float = 0.25) -> float:
    return cl((t - t0) / d)


def degrade(w: int, h: int, c0: tuple, c1: tuple, horizontal: bool = False) -> Image.Image:
    n = w if horizontal else h
    k = np.linspace(0, 1, n, dtype=np.float32)
    arr = np.array(c0, np.float32)[None, :] * (1 - k)[:, None] + np.array(c1, np.float32)[None, :] * k[:, None]
    arr = np.repeat(arr[None, :, :], h, 0) if horizontal else np.repeat(arr[:, None, :], w, 1)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


@functools.lru_cache(maxsize=1024)
def mascara_texto(txt: str, tipo: str, tam: int, track: float = 0.0, pad: int = 40) -> Image.Image:
    """Texto em tons de cinza com espaçamento entre letras ajustável (track = fração do corpo)."""
    f = F(tipo, tam)
    larg = sum(f.getlength(c) for c in txt) + track * tam * max(0, len(txt) - 1)
    w, h = int(larg) + 2 * pad, int(tam * 1.45) + 2 * pad
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    x = pad
    for c in txt:
        d.text((x, h / 2), c, font=f, fill=255, anchor="lm")
        x += f.getlength(c) + track * tam
    return m


def sombra_de(m: Image.Image, raio: float, forca: float, dy: int = 0, cor: tuple = (0, 0, 0)) -> Image.Image:
    s = Image.new("RGBA", m.size, cor + (255,))
    s.putalpha(m.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: int(min(255, v * forca))))
    if dy:
        out = Image.new("RGBA", m.size, (0, 0, 0, 0))
        out.alpha_composite(s, (0, dy))
        return out
    return s


def texto(txt: str, tipo: str, tam: float, cor: tuple = BRANCO, sombra: float = 0.0, brilho: tuple | None = None,
          track: float = 0.0, corpo: Image.Image | None = None) -> Image.Image:
    m = mascara_texto(txt, tipo, int(tam), track)
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    if brilho:
        im.alpha_composite(sombra_de(m, tam * 0.22, 1.5, 0, brilho))
        im.alpha_composite(sombra_de(m, tam * 0.07, 1.2, 0, brilho))
    if sombra:
        im.alpha_composite(sombra_de(m, tam * 0.20, sombra * 0.55, max(2, int(tam * 0.03))))
        im.alpha_composite(sombra_de(m, max(2, tam * 0.05), sombra, max(1, int(tam * 0.02))))
    c = corpo.resize(m.size) if corpo is not None else Image.new("RGBA", m.size, cor + (255,))
    c.putalpha(m)
    im.alpha_composite(c)
    return im


def recorta_vazio(im: Image.Image) -> Image.Image:
    bb = im.getchannel("A").getbbox()
    return im.crop(bb) if bb else im


@functools.lru_cache(maxsize=64)
def mascara_arred(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    return m


def arredonda(im: Image.Image, r: int) -> Image.Image:
    out = im.convert("RGBA").copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mascara_arred(im.width, im.height, r)))
    return out


def com_sombra(im: Image.Image, r: int, forca: float = 0.35, raio: float = 18, dy: int = 10) -> Image.Image:
    m = 40
    base = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    s = Image.new("L", base.size, 0)
    ImageDraw.Draw(s).rounded_rectangle((m, m + dy, m + im.width, m + im.height + dy), radius=r, fill=int(255 * forca))
    sh = Image.new("RGBA", base.size, (0, 0, 0, 255))
    sh.putalpha(s.filter(ImageFilter.GaussianBlur(raio)))
    base.alpha_composite(sh)
    base.alpha_composite(arredonda(im, r), (m, m))
    return base


def contem(im: Image.Image, w: float, h: float) -> Image.Image:
    s = min(w / im.width, h / im.height)
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)


def cobre(im: Image.Image, w: int, h: int) -> Image.Image:
    esc = max(w / im.width, h / im.height)
    r = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def _coefs(dst: list, src: list) -> list:
    """Coeficientes de Image.PERSPECTIVE que levam os 4 pontos src (na imagem) para dst (na saída)."""
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return list(np.linalg.solve(np.array(A, float), np.array(B, float)))


def perspectiva(im: Image.Image, cantos: list) -> tuple[Image.Image, int, int]:
    """Deforma im para os 4 cantos dados (sup-esq, sup-dir, inf-dir, inf-esq) em px da tela.
    Devolve a imagem recortada e a posição (x, y) onde colar."""
    xs, ys = [p[0] for p in cantos], [p[1] for p in cantos]
    x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(math.ceil(max(xs))), int(math.ceil(max(ys)))
    loc = [(x - x0, y - y0) for x, y in cantos]
    src = [(0, 0), (im.width, 0), (im.width, im.height), (0, im.height)]
    out = im.transform((max(2, x1 - x0), max(2, y1 - y0)), Image.PERSPECTIVE, _coefs(loc, src), Image.BICUBIC)
    return out, x0, y0


# ---------------------------------------------------------------- arquivos
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
                 EDIT / arq, PASTA / arq, SKILL / "assets" / arq, SKILL / "assets" / f"{arq}.png"):
        if cand.exists():
            return cand.resolve()
    sys.exit(f"não achei o arquivo {arq} (procurei em assets/ e na pasta do vídeo)")


@functools.lru_cache(maxsize=96)
def imagem(arq: str, recorte: tuple | None = None) -> Image.Image:
    im = Image.open(_resolve(arq)).convert("RGBA")
    if recorte:
        x, y, w, h = recorte
        im = im.crop((x, y, x + w, y + h))
    return im


def img_spec(it) -> Image.Image:
    if isinstance(it, str):
        return imagem(it)
    return imagem(it["arquivo"], tuple(it["recorte"]) if it.get("recorte") else None)


# ================================================================ CÂMERA (degraus, aproximação, flash)
ZOOM_TOMADAS = MAPA.get("zoom_tomadas", [1.0])      # ciclo por tomada (ex.: [1.0, 1.12] alterna)
DEGRAUS = sorted([(T(d["em"]), float(d["z"])) for d in MAPA.get("degraus", [])])
APROX = sorted([(T(d["em"]), float(d["z"]), float(d.get("dur", 0.5))) for d in MAPA.get("aproxima", [])])
TRANS = sorted([(T(d["em"]), d.get("tipo", "flash")) for d in MAPA.get("transicoes", [])])
FLASH_Z, FLASH_D = 1.3, 0.5          # cena nova entra 1,3x e afasta até 1x em 0,5 s (v4 33,8 s)


def zoom_em(t: float) -> float:
    g = grupo(t)
    z = float(ZOOM_TOMADAS[g % len(ZOOM_TOMADAS)]) if isinstance(ZOOM_TOMADAS, list) else 1.0
    a, b = OFF[g], OFF[g + 1]
    eventos = [(td, "d", zd, 0) for td, zd in DEGRAUS if a <= td < b] + \
              [(ta, "a", za, da) for ta, za, da in APROX if a <= ta < b]
    for te, tipo, ze, de in sorted(eventos):
        if t < te:
            break
        if tipo == "d":
            z = ze
        else:
            z = lerp(z, ze, ease_in_out((t - te) / de))
    for tf, tipo in TRANS:
        if tipo == "flash" and 0 <= t - tf < FLASH_D:
            z *= lerp(FLASH_Z, 1.0, ease_out((t - tf) / FLASH_D))
    return max(1.0, z)


def camera(t: float) -> tuple[float, float, float]:
    """(z, x0, y0): recorte W/z x H/z começando em (x0, y0) da base, centrado no rosto."""
    z = zoom_em(t)
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


def cabeca(t: float, cam: tuple | None = None) -> dict:
    """Topo do cabelo, centro e base do rosto, já na tela (depois do zoom)."""
    cam = cam or camera(t)
    g = MED[grupo(t)]
    r = g["rosto"]
    _, topo = na_tela(cam, 0, g["topo"])
    cx, cy = na_tela(cam, r[0] + r[2] / 2, r[1] + r[3] / 2)
    _, queixo = na_tela(cam, 0, r[1] + r[3])
    return {"topo": topo, "cx": cx, "cy": cy, "queixo": queixo, "larg": r[2] * cam[0]}


def perfil_pessoa(t: float, t_fim: float | None = None):
    """Devolve faixa(y0, y1) -> (esquerda, direita) do corpo dela na tela nessa faixa de altura, ou None.
    Junta as máscaras do Vision de 5 quadros entre t e t_fim (ela mexe a cabeça enquanto o título está na
    tela; medir só a entrada deixa o cabelo cobrir a ponta da palavra depois). Sem máscara, usa o rosto."""
    cam = camera(t)
    t_fim = t if t_fim is None else max(t, t_fim - 0.05)
    junta = None
    for tt in np.linspace(t, t_fim, 5):
        m = mascara(round(tt * FPS))
        if m is None:
            continue
        a = np.asarray(aplica_camera(m, cam, Image.BILINEAR).resize((W // 4, H // 4), Image.BILINEAR)) > 110
        junta = a if junta is None else (junta | a)
    if junta is not None:
        mm = junta

        def faixa(y0: float, y1: float):
            a, b = int(cl(y0 / 4, 0, H / 4 - 1)), int(cl(y1 / 4, 1, H / 4))
            cols = np.where(mm[a:b].any(0))[0]
            if len(cols) < 6:
                return None
            return float(cols.min() * 4), float(cols.max() * 4 + 4)
        return faixa
    c = cabeca(t, cam)

    def faixa_rosto(y0: float, y1: float):
        if y1 < c["topo"]:
            return None
        meia = c["larg"] * (0.75 if y0 < c["queixo"] else 1.4)
        return c["cx"] - meia, c["cx"] + meia
    return faixa_rosto


class perfil_rosto:
    """faixa(y0, y1) -> (esquerda, direita) do ROSTO na tela (com folga), ou None fora da altura do rosto.
    Junta o enquadramento do começo e do fim do título (um degrau de zoom no meio aumenta o rosto)."""

    def __init__(self, t0: float, t1: float):
        rs = []
        for tt in (t0, max(t0, t1 - 0.05)):
            cam = camera(tt)
            r = MED[grupo(tt)]["rosto"]
            x0, y0 = na_tela(cam, r[0], r[1])
            x1, y1 = na_tela(cam, r[0] + r[2], r[1] + r[3])
            rs.append((x0, y0, x1, y1))
        x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
        x1, y1 = max(r[2] for r in rs), max(r[3] for r in rs)
        fx, fy = (x1 - x0) * float(LAY.get("rosto_folga", 0.08)), (y1 - y0) * 0.10
        self.x0, self.x1 = x0 - fx, x1 + fx
        self.faixa_y = (y0 - fy, y1 + fy * 0.3)

    def __call__(self, a: float, b: float):
        if b < self.faixa_y[0] or a > self.faixa_y[1]:
            return None
        return self.x0, self.x1


# ================================================================ TÍTULOS (serifa atrás da cabeça)
# Materiais medidos DENTRO das letras da referência (escuro → claro). Não é cor chapada: é metal líquido,
# a cor varia em faixas de reflexo, com brilho branco, e a letra é translúcida (o cabelo aparece através).
MATERIAIS = {
    # Todos na mesma receita do rosa: só tons vivos e claros, sem faixa escura dentro da
    # letra; o metal é um brilho leve. O contraste com o fundo vem do halo escuro atrás da letra.
    "rosa":    ["#C2288E", "#E03AA8", "#F552B8", "#FF72C8", "#FFA6DC"],   # "understand", "content"
    "lilas":   ["#7A45E0", "#8F5CFF", "#A274FF", "#B98EFF", "#D6B8FF"],   # "agent", "ready"
    "cromo":   ["#3E8FD0", "#5BA8E6", "#7FC0F2", "#A9D8FA", "#DDF1FF"],   # azul-prata gelado ("People", "agent.")
    "cobre":   ["#D06A38", "#E5824C", "#F29C68", "#FAB98C", "#FFDCC2"],   # "successful", "can't sell"
    "vinho":   ["#B8213F", "#D23A4E", "#E85A5E", "#F57E72", "#FFB0A0"],   # "hearing"
    "azul":    ["#1C8FD0", "#22A7E8", "#3EC0F5", "#76D8FF", "#C2F0FF"],   # "matters", "markets"
    "dourado": ["#E0A010", "#F2B415", "#FFC700", "#FFD84A", "#FFEDA0"],   # amarelo de destaque em metal
}
MAT_DESTAQUE = MAPA.get("material", "rosa")         # *palavra*
# quanto a cor varia dentro da letra (0 = chapado, 1 = metal líquido forte). 1 fica difícil de ler:
# o padrão é um metalizado sutil, cor viva e clara com um brilho suave correndo.
VAR_METAL = float(MAPA.get("variacao_metal", 0.30))
MAT_2 = MAPA.get("material2", "cromo")               # +palavra+
OPAC_TIT = float(MAPA.get("opacidade_titulo", 0.96))  # letra translúcida
VIDRO_TIT = float(MAPA.get("vidro_titulo", 0.86))     # quanto do título aparece por cima dela (efeito vidro)


def _rampa(stops: list[str], v: np.ndarray) -> np.ndarray:
    cs = np.array([hexa(s) for s in stops], np.float32)
    x = np.clip(v, 0, 1) * (len(cs) - 1)
    i = np.clip(np.floor(x).astype(int), 0, len(cs) - 2)
    f = (x - i)[..., None]
    return cs[i] * (1 - f) + cs[i + 1] * f


@functools.lru_cache(maxsize=256)
def textura(w: int, h: int, material: str, seed: int) -> Image.Image:
    """Metal líquido: faixas de reflexo onduladas (seno sobre ruído suave), mais claro em cima, com
    brilhos brancos estreitos nas cristas."""
    rng = np.random.default_rng(seed)
    pequeno = rng.random((max(2, h // 40 + 2), max(2, w // 70 + 2))).astype(np.float32)
    ruido = np.asarray(Image.fromarray((pequeno * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                       np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yn, xn = yy / max(1, h), xx / max(1, w)
    diag = xn * 0.55 + yn * 0.9
    ondas = 0.5 + 0.5 * np.sin(2 * np.pi * (diag * 1.35 + ruido * 0.9 + rng.random()))
    v = 0.52 + VAR_METAL * (ondas - 0.5) * 1.6 + 0.16 * (0.5 - yn)   # luz suave vem de cima
    cor = _rampa(MATERIAIS.get(material, MATERIAIS["rosa"]), v)
    crista = np.clip((ondas - 0.90) / 0.10, 0, 1)[..., None] * (1 - yn[..., None] * 0.6)
    cor = cor + (255 - cor) * crista * (0.15 + 0.45 * VAR_METAL)
    return Image.fromarray(np.clip(cor, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def letra_premium(txt: str, tipo: str, tam: int, material: str | None, seed: int = 0) -> Image.Image:
    """Palavra do título: corpo em metal (ou branco), translúcido, com bisel de luz no alto da letra e
    sombra macia. material=None → branco liso (v2 "You should be")."""
    m = mascara_texto(txt, tipo, tam, LAY["tit_track"])
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    # halo escuro largo + sombra justa: separa o título do fundo claro (parede clara atrás da pessoa)
    im.alpha_composite(sombra_de(m, tam * 0.30, float(MAPA.get("halo_titulo", 0.45)), max(2, int(tam * 0.02))))
    im.alpha_composite(sombra_de(m, tam * 0.06, 0.55, max(2, int(tam * 0.025))))
    if material:
        corpo = textura(m.width, m.height, material, seed)
        opac = OPAC_TIT
    else:
        corpo = degrade(m.width, m.height, (255, 255, 255), (232, 232, 238))
        opac = min(1.0, OPAC_TIT + 0.08)
    corpo.putalpha(m.point(lambda v: int(v * opac)))
    im.alpha_composite(corpo)
    # bisel: luz fina na borda de cima das letras (diferença da máscara com ela mesma descida 2 px)
    d = max(2, int(tam * 0.012))
    desce = Image.new("L", m.size, 0)
    desce.paste(m, (0, d))
    borda = ImageChops.subtract(m, desce).filter(ImageFilter.GaussianBlur(0.8))
    luz = Image.new("RGBA", m.size, (255, 255, 255, 255))
    luz.putalpha(borda.point(lambda v: int(v * (0.55 if material else 0.25))))
    im.alpha_composite(luz)
    return im


def tokens_linha(linha: str) -> list[dict]:
    """'Quanto *tempo* _um_ /vez/ +agora+' → [{t, estilo}]: *x* destaque (material rosa), +x+ segundo
    material (cromado), _x_ ligação (sans pequena), /x/ itálico. Combináveis: */x/* = destaque itálico."""
    out = []
    for p in linha.split():
        est = {"destaque": False, "ligacao": False, "italico": False, "metal2": False}
        mudou = True
        while mudou and len(p) > 2:
            mudou = False
            for marca, chave in (("*", "destaque"), ("_", "ligacao"), ("/", "italico"), ("+", "metal2")):
                if p.startswith(marca) and (p.endswith(marca) or p.rstrip(".,!?;:").endswith(marca)):
                    pont = p[len(p.rstrip(".,!?;:")):]
                    p = p.rstrip(".,!?;:")[1:-1] + pont
                    est[chave] = True
                    mudou = True
        out.append({"t": p, **est})
    return out


class Titulo:
    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        self.atras = not spec.get("frente", False)
        self.cor = hexa(spec["cor"]) if spec.get("cor") else None
        self.linhas = [tokens_linha(l) for l in spec["linhas"]]
        # cada token entra na palavra falada (procura em ordem a partir do "em"); sem achar, entra junto do anterior
        i0 = acha(spec["em"][0], int(spec["em"][1])) if isinstance(spec["em"], list) else \
            next((i for i, w in enumerate(WORDS) if w["s"] >= self.t0 - 0.05), 0)
        j, ult = i0, self.t0
        for lin in self.linhas:
            for tk in lin:
                alvo = limpa(tk["t"])
                achou = None
                for k in range(j, min(len(WORDS), j + 14)):
                    if limpa(WORDS[k]["t"]) == alvo and WORDS[k]["s"] < self.t1:
                        achou = k
                        break
                if achou is not None:
                    tk["tempo"] = max(self.t0, WORDS[achou]["s"] - ANTECIPA)
                    j = achou + 1
                else:
                    tk["tempo"] = ult + 0.06
                ult = tk["tempo"]
        self._layout = None

    # ---- desenho de cada palavra
    def _img_token(self, tk: dict, tam: int) -> Image.Image:
        if tk["ligacao"]:   # palavra de ligação: sans negrito branca pequena (v1 "in 2027,", "give your")
            return texto(tk["t"], "hn_bold", tam * 0.30, BRANCO, sombra=0.6, track=-0.02)
        tipo = "serifa_it" if tk["italico"] else "serifa"
        mat = self.spec.get("material", MAT_DESTAQUE) if tk["destaque"] else \
            (self.spec.get("material2", MAT_2) if tk["metal2"] else self.spec.get("material_base"))
        return letra_premium(tk["t"], tipo, tam, mat, seed=sum(map(ord, tk["t"])) + tam)

    def _tam_linha(self, lin: list[dict]) -> int:
        larg100 = 0.0
        for tk in lin:
            tipo = "hn_bold" if tk["ligacao"] else ("serifa_it" if tk["italico"] else "serifa")
            f = 0.30 if tk["ligacao"] else 1.0
            larg100 += F(tipo, int(100 * f)).getlength(tk["t"]) * (1 + (0 if tk["ligacao"] else LAY["tit_track"] * 0.6))
        larg100 += 22 * (len(lin) - 1)
        tam = int(cl(W * LAY["tit_largura"] * 100 / max(1, larg100), LAY["tit_min"], LAY["tit_max"]))
        return int(self.spec["tamanho"]) if self.spec.get("tamanho") else tam

    def _linha(self, lin: list[dict], tam: int, encaixa: bool = False) -> tuple[list[Image.Image], float, float]:
        imgs = [recorta_vazio(self._img_token(tk, tam)) for tk in lin]
        if encaixa and not self.spec.get("tamanho"):   # mede o que foi desenhado (com sombra) e encaixa na largura
            tot = sum(im.width for im in imgs) + tam * 0.20 * (len(imgs) - 1)
            lim = W * LAY["tit_largura"]
            if tot > lim:
                tam = max(int(LAY["tit_min"] * 0.8), int(tam * lim / tot))
                imgs = [recorta_vazio(self._img_token(tk, tam)) for tk in lin]
        corpo = [im.height for im, tk in zip(imgs, lin) if not tk["ligacao"]] or [imgs[0].height]
        return imgs, max(corpo), tam * 0.20

    def layout(self, t: float) -> list[dict]:
        """Calcula UMA vez (na entrada). Títulos GRANDES e colados nela. Só o ROSTO é proibido: cabelo e
        corpo podem ficar por baixo das letras (a parte que passa sobre ela aparece como vidro, v2 "agent.").
        Linhas de cima pra baixo: acima do rosto, centralizadas em escada; a linha que cai na altura do rosto
        se divide e contorna o rosto (v2 "You [cabeça] should"); se ficar pequena demais pulando o rosto,
        desce pro peito."""
        if self._layout is not None:
            return self._layout
        perfil = perfil_rosto(self.t0, self.t1)
        rosto_y0, rosto_y1 = perfil.faixa_y
        tuck = float(LAY.get("tit_encosta", 0))
        y = H * float(self.spec["y"]) if self.spec.get("y") is not None else float(LAY["topo"])
        self._layout = []
        for li, lin in enumerate(self.linhas):
            tam = self._tam_linha(lin)
            imgs, alt, esp = self._linha(lin, tam, encaixa=True)
            tam = int(round(esp / 0.20))
            ext = perfil(y + alt * 0.18, y + alt * 0.92)
            if ext is not None and not self.spec.get("centro"):
                # cabe dividido sem encolher muito? senão pula o rosto e vai pro peito
                pl, pr = ext
                ws = [im.width for im in imgs]
                livre = (pl - 30) + (W - 30 - pr)
                if sum(ws) * 0.72 > livre or len(lin) == 1 and max(ws) * 0.8 > max(pl - 30, W - 30 - pr):
                    y = max(y, rosto_y1 + 10)
                    ext = perfil(y + alt * 0.18, y + alt * 0.92)
            itens = []   # (im, tk, cx, cy_base)
            if ext is None or self.spec.get("centro"):
                ws = [im.width for im in imgs]
                tot = sum(ws) + esp * (len(ws) - 1)
                off = LAY["tit_escada"] * W * (1 if li % 2 else -1) if len(self.linhas) > 1 else 0
                x = cl(W / 2 - tot / 2 + off, 36, W - 36 - tot)
                for im, tk, w_ in zip(imgs, lin, ws):
                    itens.append((im, tk, x + w_ / 2))
                    x += w_ + esp
            else:
                pl, pr = ext
                livre_e, livre_d = max(1.0, pl + tuck - 36), max(1.0, W - 36 - (pr - tuck))
                ws = [im.width for im in imgs]
                melhor = None
                for k in range(0, len(lin) + 1):   # k tokens à esquerda, o resto à direita
                    we = sum(ws[:k]) + esp * max(0, k - 1)
                    wd = sum(ws[k:]) + esp * max(0, len(lin) - k - 1)
                    f = min(1.0, livre_e / we if we else 9, livre_d / wd if wd else 9)
                    if melhor is None or f > melhor[0]:
                        melhor = (f, k)
                f, k = melhor
                novo = max(int(LAY.get("tit_min_lado", 92)), int(tam * f))
                if novo != tam:
                    tam = novo
                    imgs, alt, esp = self._linha(lin, tam)
                    ws = [im.width for im in imgs]
                x = pl + tuck - (sum(ws[:k]) + esp * max(0, k - 1))
                x = max(36, x)
                for im, tk, w_ in zip(imgs[:k], lin[:k], ws[:k]):
                    itens.append((im, tk, x + w_ / 2))
                    x += w_ + esp
                x = min(pr - tuck, W - 36 - (sum(ws[k:]) + esp * max(0, len(lin) - k - 1)))
                for im, tk, w_ in zip(imgs[k:], lin[k:], ws[k:]):
                    itens.append((im, tk, x + w_ / 2))
                    x += w_ + esp
            for im, tk, cx in itens:
                cy = y + alt * 0.62 if tk["ligacao"] else y + alt - im.height / 2
                self._layout.append({"im": im, "tk": tk, "cx": cx, "cy": cy})
            y += alt * 0.86          # linhas encavaladas (a referência sobrepõe um pouco)
        return self._layout

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1 + 0.22

    def desenha(self, cv: Image.Image, t: float) -> None:
        saida = cl((t - self.t1) / 0.22) if t >= self.t1 else 0.0
        for it in self.layout(t):
            tk, im = it["tk"], it["im"]
            k = k_in(t, tk["tempo"], 0.28)
            if k <= 0:
                continue
            if k < 1:   # entra ~1,35x maior, desfocada e transparente, e encolhe até o lugar (v1 0-0,4 s)
                e = ease_out(k)
                r = 16 * (1 - e)
                im = opaco(desfoca(escala(com_margem(im, int(r * 2) + 2), lerp(1.35, 1, e)), r), e)
            elif tk["destaque"] and t - tk["tempo"] < 1.3:
                im = brilho_corre(im, (t - tk["tempo"] - 0.28) / 1.0)
            if saida > 0:   # sai com desfoque e rastro horizontal curto
                e = ease_out(saida)
                im = opaco(desfoca(escala(com_margem(im, 24), lerp(1, 1.18, e), 1.0), 10 * e), 1 - e)
            cola_centro(cv, im, it["cx"], it["cy"])


def brilho_corre(im: Image.Image, k: float) -> Image.Image:
    """Faixa clara que varre a palavra-chave uma vez da esquerda pra direita (v1 "successful")."""
    if not 0 < k < 1:
        return im
    a = np.asarray(im, np.float32).copy()
    w = a.shape[1]
    xs = np.arange(w, dtype=np.float32)
    c = lerp(-0.2, 1.2, k) * w
    faixa = np.exp(-((xs - c) / (w * 0.10)) ** 2)[None, :, None] * 0.55
    a[..., :3] = a[..., :3] + (255 - a[..., :3]) * faixa
    return Image.fromarray(a.astype(np.uint8), "RGBA")


TITULOS = sorted([Titulo(s) for s in MAPA.get("titulos", [])], key=lambda x: x.t0)


# ================================================================ ELEMENTOS
class Elemento:
    atras = False            # tem parte atrás da pessoa (precisa de máscara)
    esconde_legenda = False

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        if self.t1 <= self.t0:
            sys.exit(f"{spec.get('tipo')}: termina antes de começar ({self.t0:.2f}-{self.t1:.2f})")

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1 + self.saida_d()

    def saida_d(self) -> float:
        return 0.2

    def k_saida(self, t: float) -> float:
        return 1 - ease_out(cl((t - self.t1) / self.saida_d())) if t >= self.t1 else 1.0

    def desenha_atras(self, cv: Image.Image, t: float, cam: tuple) -> None:
        pass

    def desenha_frente(self, cv: Image.Image, t: float, cam: tuple) -> None:
        pass

    def eventos(self) -> list[tuple[float, str]]:
        return []

    def itens_tempos(self) -> list[tuple[str, float]]:
        return []

    def tempos_itens(self, chave: str = "itens") -> list[float]:
        return [T(it["em"]) + ANTECIPA if isinstance(it["em"], list) and len(it["em"]) == 2 else T(it["em"])
                for it in self.spec.get(chave, [])]


# ---------------------------------------------------------------- pílula (nasce de um ponto e estica)
@functools.lru_cache(maxsize=128)
def pilula_img(txt: str, estilo: str, cor: tuple, larg_frac: float = 1.0, com_texto: bool = True,
               tam: int = 40) -> Image.Image:
    f = F("sans_semi", tam)
    h = int(tam * 2.0)
    w_total = int(f.getlength(txt) + tam * 1.6)
    w = max(h, int(lerp(h, w_total, larg_frac)))
    m = 46
    im = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    caixa = (m, m, m + w - 1, m + h - 1)
    forma = Image.new("L", im.size, 0)
    ImageDraw.Draw(forma).rounded_rectangle(caixa, radius=h // 2, fill=255)
    if estilo == "neon":   # preta com borda neon e brilho (v1 vermelho, v2 rosa)
        brilho = Image.new("RGBA", im.size, cor + (255,))
        anel = Image.new("L", im.size, 0)
        ImageDraw.Draw(anel).rounded_rectangle(caixa, radius=h // 2, outline=255, width=5)
        brilho.putalpha(anel.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(min(255, v * 1.6))))
        im.alpha_composite(brilho)
        corpo = Image.new("RGBA", im.size, (8, 8, 10, 255))
        corpo.putalpha(forma)
        im.alpha_composite(corpo)
        borda = Image.new("RGBA", im.size, clareia(cor, 0.15) + (255,))
        borda.putalpha(anel)
        im.alpha_composite(borda)
        cor_txt = BRANCO
    else:                  # vidro colorido translúcido com borda clara (v4 roxo)
        corpo = Image.new("RGBA", im.size, cor + (255,))
        corpo.putalpha(forma.point(lambda v: int(v * 0.42)))
        im.alpha_composite(corpo)
        anel = Image.new("L", im.size, 0)
        ImageDraw.Draw(anel).rounded_rectangle(caixa, radius=h // 2, outline=255, width=4)
        brilho = Image.new("RGBA", im.size, clareia(cor, 0.35) + (255,))
        brilho.putalpha(anel.filter(ImageFilter.GaussianBlur(6)))
        im.alpha_composite(brilho)
        borda = Image.new("RGBA", im.size, clareia(cor, 0.55) + (255,))
        borda.putalpha(anel.point(lambda v: int(v * 0.9)))
        im.alpha_composite(borda)
        cor_txt = BRANCO
    if com_texto:
        ImageDraw.Draw(im).text((im.width / 2, im.height / 2), txt, font=f, fill=cor_txt + (255,), anchor="mm")
    return im


def pilula_animada(txt: str, estilo: str, cor: tuple, t: float, t0: float, tam: int = 40) -> Image.Image | None:
    """0-0,12 s: ponto cresce; 0,12-0,36 s: estica até a largura do texto; texto entra no fim (v1 9 s)."""
    d = t - t0
    if d < 0:
        return None
    if d < 0.12:
        im = pilula_img(txt, estilo, cor, 0.0, False, tam)
        return escala(im, max(0.05, ease_out(d / 0.12)))
    larg = ease_out((d - 0.12) / 0.24)
    im = pilula_img(txt, estilo, cor, round(larg, 2), larg >= 0.999, tam)
    if larg >= 0.999 and d < 0.5:
        return opaco(im, 1.0)
    return im


def luz_na_pessoa(cv: Image.Image, cx: float, cy: float, cor: tuple, forca: float = 0.20) -> None:
    """A borda neon da pílula tinge a roupa perto dela (v1 9-12 s)."""
    r = 260
    g = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(g).ellipse((r * 0.35, r * 0.35, r * 1.65, r * 1.65), fill=int(255 * forca))
    g = g.filter(ImageFilter.GaussianBlur(70))
    camada = Image.new("RGBA", g.size, cor + (255,))
    camada.putalpha(g)
    cola_centro(cv, camada, cx, cy)


class Pilulas(Elemento):
    """Itens falados viram pílulas, uma de cada lado ou em triângulo. estilo "neon" (preta, borda neon) | "vidro"."""

    def __init__(self, spec):
        super().__init__(spec)
        self.estilo = spec.get("estilo", "neon")
        self.cor = hexa(spec["cor"]) if spec.get("cor") else (BORDA_PILULA if self.estilo == "neon" else VIDRO)
        self.tempos = self.tempos_itens()

    def _pos(self, i: int, n: int, t: float, cam: tuple) -> tuple[float, float]:
        it = self.spec["itens"][i]
        if it.get("pos"):
            return W * it["pos"][0], H * it["pos"][1]
        ly = legenda_y(self.t0, cam)   # tudo em volta da legenda, sem encostar nela
        if n == 3:   # triângulo em volta dela (v4 21-23 s)
            return [(W * 0.24, ly - 120), (W * 0.76, ly - 120), (W * 0.5, ly + 125)][i]
        lado = it.get("lado", "esq" if i % 2 == 0 else "dir")
        return (W * 0.24 if lado == "esq" else W * 0.77), ly - 120 + 130 * (i // 2) + (0 if lado == "esq" else 80)

    def desenha_frente(self, cv, t, cam):
        n = len(self.spec["itens"])
        ks = self.k_saida(t)
        for i, (it, ti) in enumerate(zip(self.spec["itens"], self.tempos)):
            im = pilula_animada(it["texto"], self.estilo, self.cor, t, ti, int(self.spec.get("tam", 40)))
            if im is None:
                continue
            x, y = self._pos(i, n, t, cam)
            if self.estilo == "neon":
                luz_na_pessoa(cv, x, y, self.cor, 0.16 * ks)
            cola_centro(cv, opaco(im, ks), x, y)

    def eventos(self):
        return [(ti, "pop") for ti in self.tempos]

    def itens_tempos(self):
        return [(it["texto"], ti) for it, ti in zip(self.spec["itens"], self.tempos)]


# ---------------------------------------------------------------- lista em pílulas de vidro (v1 25-28 s)
@functools.lru_cache(maxsize=64)
def vidro_img(txt: str, tam: int = 34) -> Image.Image:
    f = F("sans_reg", tam)
    h = int(tam * 1.9)
    w = int(f.getlength(txt) + tam * 1.4)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(70, 70, 76, 150),
                                         outline=(255, 255, 255, 60), width=2)
    ImageDraw.Draw(im).text((w / 2, h / 2), txt, font=f, fill=(255, 255, 255, 240), anchor="mm")
    return com_sombra(im, h // 2, 0.25, 14, 6)


class Lista(Elemento):
    def __init__(self, spec):
        super().__init__(spec)
        self.tempos = self.tempos_itens()

    def desenha_frente(self, cv, t, cam):
        x0 = W * float(self.spec.get("x", 0.06))
        y0 = H * float(self.spec.get("y", 0.40))
        ks = self.k_saida(t)
        for i, (it, ti) in enumerate(zip(self.spec["itens"], self.tempos)):
            im = surge(vidro_img(it["texto"], int(self.spec.get("tam", 34))), k_in(t, ti, 0.22))
            if im is None:
                continue
            cola(cv, opaco(im, ks), int(x0 - 40), int(y0 + i * 92 - im.height / 2))

    def eventos(self):
        return [(ti, "pop") for ti in self.tempos]

    def itens_tempos(self):
        return [(it["texto"], ti) for it, ti in zip(self.spec["itens"], self.tempos)]


# ---------------------------------------------------------------- notificação de vidro (v2 5,2 s)
class Notificacao(Elemento):
    def __init__(self, spec):
        super().__init__(spec)
        self._img = None

    def img(self) -> Image.Image:
        if self._img is not None:
            return self._img
        w, h = int(W * 0.86), 150
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=44, fill=(92, 96, 90, 205),
                                             outline=(255, 255, 255, 40), width=2)
        av = 92
        if self.spec.get("avatar"):
            a = cobre(imagem(self.spec["avatar"]), av, av)
        else:   # rosto da pessoa, tirado do próprio vídeo
            fr = quadro_base(round(self.t0 * FPS))
            r = MED[grupo(self.t0)]["rosto"]
            m = int(r[2] * 0.25)
            a = fr.crop((r[0] - m, r[1] - m, r[0] + r[2] + m, r[1] + r[3] + m)).resize((av, av), Image.LANCZOS)
        mk = Image.new("L", (av, av), 0)
        ImageDraw.Draw(mk).ellipse((0, 0, av - 1, av - 1), fill=255)
        a = a.convert("RGBA")
        a.putalpha(mk)
        im.alpha_composite(a, (30, (h - av) // 2))
        d = ImageDraw.Draw(im)
        d.text((146, 46), self.spec.get("nome", PERFIL["nome"]), font=F("hn_bold", 34), fill=BRANCO + (255,), anchor="lm")
        d.text((146, 96), self.spec["texto"], font=F("hn_reg", 31), fill=(236, 236, 236, 255), anchor="lm")
        self._img = com_sombra(im, 44, 0.28, 20, 10)
        return self._img

    def desenha_frente(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, 0.3))
        if k <= 0:
            return
        im = self.img()
        if k < 1:
            im = opaco(desfoca(im, 10 * (1 - k)), k)
        y = H * float(self.spec.get("y", 0.15)) - 70 * (1 - k)
        cola_centro(cv, opaco(im, self.k_saida(t)), W / 2, y)

    def eventos(self):
        return [(self.t0, "notificacao")]


# ---------------------------------------------------------------- balões de chat espalhados (v2 27,3 s)
class Baloes(Elemento):
    SLOTS = [(0.24, 0.42, -6), (0.77, 0.40, 5), (0.22, 0.56, 4), (0.78, 0.55, -4), (0.50, 0.30, -3), (0.50, 0.66, 3)]

    def __init__(self, spec):
        super().__init__(spec)
        self.tempos = self.tempos_itens()

    @functools.lru_cache(maxsize=16)
    def img(self, txt: str, rotulo: str) -> Image.Image:
        f = F("sans_semi", 30)
        w, h = int(f.getlength(txt) + 60), 74
        im = Image.new("RGBA", (w + 20, h + 46), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if rotulo:
            d.text((26, 14), rotulo, font=F("sans_medio", 20), fill=(255, 255, 255, 190), anchor="lm")
        y0 = 30
        d.rounded_rectangle((0, y0, w, y0 + h), radius=h // 2, fill=(46, 46, 50, 215))
        d.polygon([(18, y0 + h - 14), (4, y0 + h + 14), (40, y0 + h - 4)], fill=(46, 46, 50, 215))
        d.text((w / 2, y0 + h / 2), txt, font=f, fill=BRANCO + (255,), anchor="mm")
        return com_sombra(im, 20, 0.22, 14, 6)

    def desenha_frente(self, cv, t, cam):
        ks = self.k_saida(t)
        for i, (it, ti) in enumerate(zip(self.spec["itens"], self.tempos)):
            k = cl((t - ti) / 0.3)
            if k <= 0:
                continue
            x, y, rot = self.SLOTS[i % len(self.SLOTS)]
            if it.get("pos"):
                x, y = it["pos"]
            im = self.img(it.get("texto", self.spec.get("texto", "")), it.get("rotulo", self.spec.get("rotulo", "")))
            im = escala(im, max(0.05, mola(k))).rotate(rot, Image.BICUBIC, expand=True)
            cola_centro(cv, opaco(im, ks * min(1, k * 3)), W * x, H * y)

    def eventos(self):
        return [(ti, "pop") for ti in self.tempos]

    def itens_tempos(self):
        return [(it.get("texto", self.spec.get("texto", "")), ti) for it, ti in zip(self.spec["itens"], self.tempos)]


# ---------------------------------------------------------------- ícones de rede pulando (v4 31,6 s)
class Icones(Elemento):
    SLOTS = [(0.20, 0.40), (0.80, 0.40), (0.50, 0.60), (0.20, 0.60), (0.80, 0.60)]

    def __init__(self, spec):
        super().__init__(spec)
        self.tempos = self.tempos_itens()

    @functools.lru_cache(maxsize=16)
    def img(self, arq: str, lado: int) -> Image.Image:
        im = contem(imagem(arq), lado, lado)
        return com_sombra(im, int(lado * 0.22), 0.30, 16, 8) if im.getchannel("A").getextrema()[0] > 200 else im

    def desenha_frente(self, cv, t, cam):
        ks = self.k_saida(t)
        lado = int(self.spec.get("tam", 170))
        for i, (it, ti) in enumerate(zip(self.spec["itens"], self.tempos)):
            k = cl((t - ti) / 0.32)
            if k <= 0:
                continue
            x, y = it.get("pos") or self.SLOTS[i % len(self.SLOTS)]
            im = escala(self.img(it["arquivo"], lado), max(0.05, mola(k)))
            cola_centro(cv, opaco(im, ks), W * x, H * y)

    def eventos(self):
        return [(ti, "pop") for ti in self.tempos]

    def itens_tempos(self):
        return [(it["arquivo"], ti) for it, ti in zip(self.spec["itens"], self.tempos)]


# ---------------------------------------------------------------- número neon enchendo (v4 10,4 s "74%")
def neon_texto(txt: str, tam: int, cor: tuple, nivel: float) -> Image.Image:
    """Número em sans arredondada: até `nivel` (de baixo pra cima) rosa neon com brilho; acima, cinza translúcido."""
    m = mascara_texto(txt, "redonda", tam, -0.02, pad=int(tam * 0.4))
    bb = m.getbbox() or (0, 0, m.width, m.height)
    corte = int(bb[3] - (bb[3] - bb[1]) * cl(nivel))
    baixo = m.copy()
    ImageDraw.Draw(baixo).rectangle((0, 0, m.width, corte), fill=0)
    cima = m.copy()
    ImageDraw.Draw(cima).rectangle((0, corte, m.width, m.height), fill=0)
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    im.alpha_composite(sombra_de(baixo, tam * 0.16, 1.1, 0, cor))
    c = Image.new("RGBA", m.size, (150, 150, 158, 255))
    c.putalpha(cima.point(lambda v: int(v * 0.55)))
    im.alpha_composite(c)
    corpo = degrade(m.width, m.height, clareia(cor, 0.25), cor)
    corpo.putalpha(baixo)
    im.alpha_composite(corpo)
    return im


class Numero(Elemento):
    def __init__(self, spec):
        super().__init__(spec)
        self.atras = bool(spec.get("atras", False))
        self.valor = str(spec["valor"])
        self.cor = hexa(spec["cor"]) if spec.get("cor") else NEON

    def _txt(self, t: float) -> str:
        de = self.spec.get("de")
        if de is None:
            return self.valor
        num = "".join(c for c in self.valor if c.isdigit() or c in ",.")
        alvo = float(num.replace(".", "").replace(",", ".")) if num else 0
        v = lerp(float(de), alvo, ease_out(k_in(t, self.t0, 0.7)))
        pre = self.valor[: self.valor.index(num[0])] if num else ""
        suf = self.valor[self.valor.rindex(num[-1]) + 1:] if num else ""
        return f"{pre}{int(round(v)):,}".replace(",", ".") + suf

    def _desenha(self, cv, t, cam):
        tam = int(self.spec.get("tam", 330))
        nivel = ease_out(k_in(t, self.t0 + 0.05, 0.55))
        im = neon_texto(self._txt(t), tam, self.cor, nivel)
        k = ease_out(k_in(t, self.t0, 0.25))
        if k < 1:
            im = opaco(desfoca(escala(com_margem(im, 30), lerp(1.25, 1, k)), 14 * (1 - k)), k)
        c = cabeca(self.t0, cam)   # na frente: logo abaixo da legenda (v4 "homeowners" em cima do 74%)
        y = H * float(self.spec["y"]) if self.spec.get("y") is not None else \
            (c["topo"] + 40 if self.atras else min(H * LAY["base"] - tam * 0.35, legenda_y(self.t0, cam) + tam * 0.62))
        cola_centro(cv, opaco(im, self.k_saida(t) * (1 if self.atras else 0.93)), W / 2, y)

    def desenha_atras(self, cv, t, cam):
        if self.atras:
            self._desenha(cv, t, cam)

    def desenha_frente(self, cv, t, cam):
        if not self.atras:
            self._desenha(cv, t, cam)

    def eventos(self):
        return [(self.t0, "brilho")]


# ---------------------------------------------------------------- arco neon + contador (v1 16,3 s)
@functools.lru_cache(maxsize=16)
def pilula_numero(txt: str, tam: int = 44) -> Image.Image:
    f = F("sans_semi", tam)
    ic = int(tam * 0.9)
    w, h = int(f.getlength(txt) + ic + tam * 1.6), int(tam * 2.0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(28, 28, 32, 225), outline=(255, 255, 255, 30), width=2)
    x, cy = tam * 0.7, h / 2   # bonequinho de "seguidores"
    d.ellipse((x + ic * 0.30, cy - ic * 0.48, x + ic * 0.70, cy - ic * 0.08), fill=(160, 172, 200, 255))
    d.pieslice((x, cy - ic * 0.02, x + ic, cy + ic * 0.95), 180, 360, fill=(160, 172, 200, 255))
    d.text((x + ic + tam * 0.35, cy), txt, font=f, fill=BRANCO + (255,), anchor="lm")
    return com_sombra(im, h // 2, 0.25, 14, 6)


class Arco(Elemento):
    atras = True

    def __init__(self, spec):
        super().__init__(spec)
        self.t_para = T(spec["em_para"]) if spec.get("em_para") else self.t0 + 1.2
        self.cor = hexa(spec["cor"]) if spec.get("cor") else NEON

    def _geo(self, cam):
        c = cabeca(self.t0, cam)
        r = c["larg"] * 0.82
        return c["cx"], c["cy"] - c["larg"] * 0.05, r

    def desenha_atras(self, cv, t, cam):
        cx, cy, r = self._geo(cam)
        ks = self.k_saida(t)
        k = ease_in_out(cl((t - self.t0) / max(0.3, self.t_para - self.t0 + 0.3)))
        a0, a1 = 200.0, lerp(200.0, 340.0, k)
        m = int(r * 0.25)
        tam = int(2 * r + 2 * m)
        anel = Image.new("L", (tam, tam), 0)
        bb = (m, m, m + 2 * r, m + 2 * r)
        ImageDraw.Draw(anel).arc(bb, a0, max(a0 + 1, a1), fill=255, width=int(r * 0.07))
        im = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
        im.alpha_composite(sombra_de(anel, r * 0.10, 1.4, 0, self.cor))
        corpo = Image.new("RGBA", (tam, tam), clareia(self.cor, 0.2) + (255,))
        corpo.putalpha(anel)
        im.alpha_composite(corpo)
        ang = math.radians(a1)   # bolinha branca na ponta
        px, py = m + r + r * math.cos(ang), m + r + r * math.sin(ang)
        rr = r * 0.055
        ImageDraw.Draw(im).ellipse((px - rr, py - rr, px + rr, py + rr), fill=BRANCO + (255,))
        cola_centro(cv, opaco(im, ks * min(1, (t - self.t0) / 0.15)), cx, cy)

    def desenha_frente(self, cv, t, cam):
        cx, cy, r = self._geo(cam)
        ks = self.k_saida(t)
        y = cy + r * 0.25
        a = surge(pilula_numero(str(self.spec["de"])), k_in(t, self.t0, 0.25))
        cola_centro(cv, opaco(a, ks) if a else None, max(150, cx - r - 40), y)
        b = surge(pilula_numero(str(self.spec["para"])), k_in(t, self.t_para, 0.25))
        cola_centro(cv, opaco(b, ks) if b else None, min(W - 150, cx + r + 40), y)

    def eventos(self):
        return [(self.t0, "brilho"), (self.t_para, "pop")]


# ---------------------------------------------------------------- barra neon que conta (v4 6,5 s)
class Barra(Elemento):
    def __init__(self, spec):
        super().__init__(spec)
        self.cor = hexa(spec["cor"]) if spec.get("cor") else NEON
        self.dur = float(spec.get("dur", 1.4))

    def desenha_frente(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, self.dur))
        w, h = int(W * 0.62), 40
        m = 40
        im = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        trilho = Image.new("L", im.size, 0)
        ImageDraw.Draw(trilho).rounded_rectangle((m, m, m + w, m + h), radius=h // 2, fill=255)
        t_ = Image.new("RGBA", im.size, (255, 255, 255, 255))
        t_.putalpha(trilho.point(lambda v: int(v * 0.16)))
        im.alpha_composite(t_)
        wf = max(h, int(w * k))
        cheio = Image.new("L", im.size, 0)
        ImageDraw.Draw(cheio).rounded_rectangle((m, m, m + wf, m + h), radius=h // 2, fill=255)
        im.alpha_composite(sombra_de(cheio, 16, 1.3, 0, self.cor))
        corpo = degrade(im.width, im.height, clareia(self.cor, 0.35), self.cor, horizontal=True)
        corpo.putalpha(cheio)
        im.alpha_composite(corpo)
        v = lerp(float(self.spec.get("de", 0)), float(self.spec["valor"]), k)
        txt = f"{int(round(v))}{self.spec.get('sufixo', '%')}"
        ImageDraw.Draw(im).text((m + wf - 16, m + h / 2), txt, font=F("sans", 24), fill=BRANCO + (255,), anchor="rm")
        c = cabeca(self.t0, cam)
        y = H * float(self.spec["y"]) if self.spec.get("y") is not None else \
            cl(legenda_y(self.t0, cam) - 120, H * 0.40, H * 0.66)
        cola_centro(cv, opaco(surge(im, k_in(t, self.t0, 0.2)) or im, self.k_saida(t)), W / 2, y)
        if self.spec.get("rotulo"):
            r = texto(self.spec["rotulo"], "sans_medio", 34, BRANCO, sombra=0.6)
            cola_centro(cv, opaco(r, self.k_saida(t) * k_in(t, self.t0, 0.25)), W / 2, y - 66)

    def eventos(self):
        return [(self.t0, "brilho")]


# ---------------------------------------------------------------- cronômetro (v2: o fio do vídeo)
class Cronometro(Elemento):
    def desenha_frente(self, cv, t, cam):
        de = float(self.spec.get("de", 30))
        k = cl((t - self.t0) / max(0.1, self.t1 - self.t0))
        resto = max(0, de * (1 - k))
        lado = int(self.spec.get("tam", 230))
        im = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=int(lado * 0.18), fill=(10, 10, 14, 215))
        m = int(lado * 0.14)
        d.ellipse((m, m, lado - m, lado - m), outline=(255, 255, 255, 40), width=6)
        d.arc((m, m, lado - m, lado - m), -90, -90 + 360 * (1 - k), fill=clareia(NEON, 0.35) + (255,), width=6)
        d.text((lado / 2, lado / 2), f"00:{int(math.ceil(resto)):02d}", font=F("sans_semi", int(lado * 0.20)),
               fill=BRANCO + (255,), anchor="mm")
        x, y = self.spec.get("pos", [0.18, 0.62])
        cola_centro(cv, opaco(surge(com_sombra(im, int(lado * 0.18), 0.3), k_in(t, self.t0)), self.k_saida(t)), W * x, H * y)


# ---------------------------------------------------------------- objeto (chave 3D, card do perfil) flutuando
class Objeto(Elemento):
    def desenha_frente(self, cv, t, cam):
        if not self.spec.get("atras"):
            self._d(cv, t)

    def desenha_atras(self, cv, t, cam):
        if self.spec.get("atras"):
            self._d(cv, t)

    @property
    def atras(self):
        return bool(self.spec.get("atras"))

    @functools.lru_cache(maxsize=4)
    def _img(self) -> Image.Image:
        im = contem(img_spec(self.spec), int(self.spec.get("tam", 300)), int(self.spec.get("tam", 300)))
        if self.spec.get("card"):
            im = com_sombra(im, int(self.spec.get("raio", 22)), 0.35)
        return im

    def _d(self, cv, t):
        k = ease_out(k_in(t, self.t0, 0.45))
        if k <= 0:
            return
        x, y = self.spec.get("pos", [0.78, 0.30])
        lado = -1 if x > 0.5 else 1
        dx = (1 - k) * W * 0.5 * -lado            # voa do lado de fora pra dentro
        flutua = math.sin((t - self.t0) * 2.4) * 10
        rot = (1 - k) * 40 * lado + math.sin((t - self.t0) * 1.7) * 5 + float(self.spec.get("giro", 0))
        im = self._img().rotate(rot, Image.BICUBIC, expand=True)
        cola_centro(cv, opaco(im, min(1, k * 1.5) * self.k_saida(t)), W * x + dx, H * y + flutua)

    def eventos(self):
        return [(self.t0, "whoosh")]


# ---------------------------------------------------------------- cards girando na cintura (v1 29,9 s)
class Cards(Elemento):
    atras = True

    def __init__(self, spec):
        super().__init__(spec)
        self.arqs = spec["arquivos"]
        lado = int(spec.get("tam", 270))
        self.imgs = [com_sombra(cobre(img_spec(a), lado, int(lado * 1.3)), 24, 0.35) for a in self.arqs]
        self.vel = float(spec.get("voltas_por_s", 0.22))

    def _cards(self, t: float, cam: tuple) -> list[tuple[float, Image.Image, float, float]]:
        c = cabeca(self.t0, cam)
        cy = H * float(self.spec["y"]) if self.spec.get("y") is not None else cl(c["queixo"] + 420, H * 0.55, H * 0.70)
        rx, ry = W * 0.40, H * 0.045
        n = len(self.imgs)
        out = []
        for i, im in enumerate(self.imgs):
            k = ease_out(k_in(t, self.t0 + i * 0.12, 0.35))
            if k <= 0:
                continue
            ang = 2 * math.pi * (i / n + (t - self.t0) * self.vel) + math.pi / 2
            prof = math.sin(ang)                          # >0 = na frente
            s = (0.70 + 0.30 * (prof + 1) / 2) * lerp(0.5, 1, k)
            x = W / 2 + rx * math.cos(ang)
            y = cy + ry * prof
            esc = escala(im, s)
            # gira de leve conforme passa pelo lado (perspectiva barata)
            out.append((prof, opaco(esc, k * self.k_saida(t)), x, y))
        return sorted(out, key=lambda o: o[0])

    def desenha_atras(self, cv, t, cam):
        for prof, im, x, y in self._cards(t, cam):
            if prof < 0:
                cola_centro(cv, desfoca(im, 2.5), x, y)

    def desenha_frente(self, cv, t, cam):
        for prof, im, x, y in self._cards(t, cam):
            if prof >= 0:
                cola_centro(cv, im, x, y)

    def eventos(self):
        return [(self.t0, "whoosh")]


# ---------------------------------------------------------------- muro de fotos atrás da pessoa (v4 2,5 s)
class Muro(Elemento):
    atras = True

    def __init__(self, spec):
        super().__init__(spec)
        self._base = None

    def base(self) -> Image.Image:
        if self._base is not None:
            return self._base
        arqs = self.spec["arquivos"]
        cols, rows = 3, 4
        cw, ch = int(W * 1.12 / cols), int(H * 1.12 / rows)
        cv = Image.new("RGBA", (int(W * 1.12), int(H * 1.12)), (236, 234, 230, 255))
        rng = np.random.default_rng(7)
        k = 0
        for r in range(rows):
            for c in range(cols):
                im = cobre(img_spec(arqs[k % len(arqs)]), cw - 10, ch - 10)
                k += 1
                im = im.rotate(float(rng.uniform(-3, 3)), Image.BICUBIC, expand=True)
                cola_centro(cv, im, c * cw + cw / 2 + rng.uniform(-8, 8), r * ch + ch / 2 + rng.uniform(-8, 8))
        self._base = cv
        return cv

    def desenha_atras(self, cv, t, cam):
        z = lerp(1.0, 1.07, cl((t - self.t0) / max(0.5, self.t1 - self.t0)))
        b = self.base()
        w, h = int(W / z * 1.0), int(H / z * 1.0)
        x0, y0 = (b.width - w) // 2, (b.height - h) // 2
        im = b.crop((x0, y0, x0 + w, y0 + h)).resize((W, H), Image.BILINEAR)
        cv.alpha_composite(opaco(im, self.k_saida(t)))


# ---------------------------------------------------------------- dois prints em livro aberto (v1 12,4 s)
class Livro(Elemento):
    atras = True

    def desenha_atras(self, cv, t, cam):
        a, b = self.spec["arquivos"][:2]
        k = ease_out(k_in(t, self.t0, 0.4))
        if k <= 0:
            return
        pw, ph = W * 0.43, H * 0.40
        c = cabeca(self.t0, cam)
        y0 = H * float(self.spec["y"]) if self.spec.get("y") is not None else max(LAY["topo"] - 20, c["topo"] - ph * 0.45)
        cx = W / 2
        dob = 0.10 * ph    # quanto as bordas de fora sobem/descem (o "V")
        ab = lerp(0.6, 1.0, k)   # abre um pouco na entrada
        esq = [(cx - pw * ab, y0 - dob), (cx, y0), (cx, y0 + ph), (cx - pw * ab, y0 + ph + dob)]
        dir_ = [(cx, y0), (cx + pw * ab, y0 - dob), (cx + pw * ab, y0 + ph + dob), (cx, y0 + ph)]
        for arq, cantos in ((a, esq), (b, dir_)):
            im = cobre(img_spec(arq), int(pw), int(ph))
            im, x, y = perspectiva(im, cantos)
            cola(cv, opaco(desfoca(im, 8 * (1 - k)), k * self.k_saida(t)), x, y)


# ---------------------------------------------------------------- print em tela cheia com caneta (v1 55-60 s)
class Tela(Elemento):
    esconde_legenda = True

    def __init__(self, spec):
        super().__init__(spec)
        self.circ = [{"caixa": c["caixa"], "t": T(c["em"]) + ANTECIPA} for c in spec.get("circulos", [])]

    @functools.lru_cache(maxsize=1)
    def _img(self) -> Image.Image:
        return img_spec(self.spec).convert("RGBA")

    def desenha_tela(self, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), (250, 250, 250, 255))
        src = self._img().copy()
        d = ImageDraw.Draw(src)
        lw = max(4, int(src.width / 140))
        for c in self.circ:   # elipse à mão, desenhada em ~0,45 s, passa um pouco do começo
            k = ease_out(cl((t - c["t"]) / 0.45))
            if k <= 0:
                continue
            x, y, w, h = c["caixa"]
            cx, cy, rx, ry = x + w / 2, y + h / 2, w * 0.62, h * 0.85
            pts = []
            n = int(80 * k * 1.15) + 2
            for i in range(n):
                a = -2.2 + (i / 80) * 2 * math.pi
                wob = 1 + 0.05 * math.sin(a * 3 + 1)
                pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a) + i * h * 0.004))
            d.line(pts, fill=CANETA + (255,), width=lw, joint="curve")
        k = ease_out(k_in(t, self.t0, 0.5))
        # print largo (tela do computador) cresce até ~42% da altura e passa das bordas; retrato cabe na largura
        s1 = max(W * 0.96 / src.width, H * float(self.spec.get("altura", 0.48)) / src.height)
        s = s1 * lerp(0.42, 1.0, k)
        im = src.resize((int(src.width * s), int(src.height * s)), Image.BICUBIC)
        # inclinação 3D: a base fica mais larga (vista de cima) e passeia devagar
        inc = lerp(0.16, 0.08, k)
        x0 = (W - im.width) / 2
        if im.width > W and self.circ:   # mais largo que a tela: centraliza nos círculos
            mcx = np.mean([c["caixa"][0] + c["caixa"][2] / 2 for c in self.circ]) * s
            x0 = cl(W / 2 - mcx, W - im.width - 30, 30)
        y0 = H * 0.30 - (t - self.t0) * 30
        cantos = [(x0 + im.width * inc, y0), (x0 + im.width * (1 - inc), y0),
                  (x0 + im.width * (1 + inc * 0.4), y0 + im.height), (x0 - im.width * inc * 0.4, y0 + im.height)]
        im2, x, y = perspectiva(im, cantos)
        # parte de baixo desfocada (profundidade de campo)
        nit = im2
        bor = desfoca(im2, 10)
        rampa = np.clip((np.arange(im2.height) / im2.height - 0.55) / 0.35, 0, 1)
        mk = Image.fromarray((np.repeat(rampa[:, None], im2.width, 1) * 255).astype(np.uint8))
        mix = Image.composite(bor, nit, mk)
        cola(cv, com_sombra_solta(mix), x - 40, y - 40)
        return cv

    def eventos(self):
        return [(self.t0, "whoosh")] + [(c["t"], "caneta") for c in self.circ]

    def itens_tempos(self):
        return [("círculo", c["t"]) for c in self.circ]


def com_sombra_solta(im: Image.Image) -> Image.Image:
    m = 40
    base = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    base.alpha_composite(sombra_de(com_margem(im, m).getchannel("A"), 24, 0.25, 12))
    base.alpha_composite(im, (m, m))
    return base


TIPOS = {"pilulas": Pilulas, "lista": Lista, "notificacao": Notificacao, "baloes": Baloes, "icones": Icones,
         "numero": Numero, "arco": Arco, "barra": Barra, "cronometro": Cronometro, "objeto": Objeto,
         "cards": Cards, "muro": Muro, "livro": Livro, "tela": Tela}


def _cria(spec: dict) -> Elemento:
    if spec.get("tipo") not in TIPOS:
        sys.exit(f'elemento "{spec.get("tipo")}" não existe. Tipos: {", ".join(TIPOS)}')
    return TIPOS[spec["tipo"]](spec)


ELEMENTOS = sorted([_cria(s) for s in MAPA.get("elementos", [])], key=lambda e: e.t0)
# muro entra e sai por flash/desfoque (v4 2,4 s e 4,4 s), a não ser que o mapa diga "transicao": false
_EXPLICITAS = list(TRANS)
for _e in ELEMENTOS:
    if isinstance(_e, (Muro, Tela)) and _e.spec.get("transicao", True):
        for _t, _tipo in ((_e.t0, "flash" if isinstance(_e, Muro) else "desfoque"), (_e.t1, "desfoque")):
            if not any(abs(_t - _x) < 0.25 for _x, _ in _EXPLICITAS):   # a do mapa manda
                TRANS.append((_t, _tipo))
TRANS.sort()


def janelas_mascara() -> list[tuple[float, float]]:
    """Trechos com algo ATRÁS dela (título, arco, muro, livro, cards, número/objeto atrás)."""
    js = [(x.t0 - 0.05, x.t1 + 0.3) for x in TITULOS if x.atras]
    js += [(e.t0 - 0.05, e.t1 + 0.3) for e in ELEMENTOS if e.atras]
    js.sort()
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
        _MASC["n"], _MASC["im"] = n, (Image.open(p).convert("L").filter(ImageFilter.GaussianBlur(1.2)) if p.exists() else None)
    return _MASC["im"]


# ================================================================ LEGENDA (pequena, fina, 1-2 palavras, troca)
def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    maxp = int(MAPA.get("leg_palavras", 2))
    maxc = int(MAPA.get("leg_chars", 16))
    blocos, atual = [], []

    def fecha():
        if atual:
            blocos.append(list(atual))
            atual.clear()

    for i, w in enumerate(WORDS):
        txt = w["t"].strip()
        if not any(c.isalnum() for c in txt):
            continue
        if atual and (WORDS[atual[-1]]["seg"] != w["seg"] or w["s"] - WORDS[atual[-1]]["e"] > 0.3):
            fecha()
        cand = " ".join(WORDS[j]["t"].strip() for j in atual + [i])
        if atual and (len(atual) >= maxp or len(cand) > maxc):
            fecha()
        atual.append(i)
        if txt[-1:] in ".!?,;:":
            fecha()
    fecha()
    out = []
    for k, b in enumerate(blocos):
        txt = " ".join(WORDS[j]["t"].strip() for j in b)
        ini = WORDS[b[0]]["s"] - 0.03
        prox = WORDS[blocos[k + 1][0]]["s"] - 0.03 if k + 1 < len(blocos) else TOTAL
        fim = prox if prox - WORDS[b[-1]]["e"] < 0.5 else WORDS[b[-1]]["e"] + 0.15
        out.append({"txt": txt, "ini": max(0.0, ini), "fim": min(TOTAL, fim)})
    return out


@functools.lru_cache(maxsize=2048)
def legenda_img(txt: str) -> Image.Image:
    # branco fino com sombra dupla: a referência usa só sombra leve, mas roupa branca come o texto
    return texto(txt, LEG_FONTE, LAY["leg_tam"], BRANCO, sombra=0.9, track=float(LAY.get("leg_track", -0.045)))


def legenda_y(t: float, cam: tuple) -> float:
    c = cabeca(t, cam)
    return cl(c["queixo"] + LAY["leg_queixo"], H * LAY["leg_min"], H * LAY["leg_max"])


# ================================================================ TRANSIÇÕES (flash, desfoque)
def efeito_transicao(cv: Image.Image, t: float) -> Image.Image:
    for tf, tipo in TRANS:
        d = t - tf
        if tipo == "flash" and -0.07 <= d < 0.05:
            # 1-2 quadros estourados de branco e desfocados (v1 5,8 s; v4 33,7 s)
            k = 1 - abs(d + 0.01) / 0.06
            k = cl(k)
            im = desfoca(cv, 22 * k)
            branco = Image.new("RGBA", (W, H), (255, 252, 246, 255))
            return Image.blend(im, branco, 0.78 * k)
        if tipo == "flash" and 0.05 <= d < 0.20:
            # zoom out com desfoque radial curto na entrada (v4 33,8 s)
            k = 1 - (d - 0.05) / 0.15
            out = cv
            for s, a in ((1.04, 0.33), (1.08, 0.22)):
                c = escala(cv, s)
                x, y = (c.width - W) // 2, (c.height - H) // 2
                out = Image.blend(out, c.crop((x, y, x + W, y + H)), a * k)
            return out
        if tipo == "desfoque" and -0.12 <= d < 0.12:
            k = 1 - abs(d) / 0.12
            return desfoca(cv, 20 * ease_out(k))
    return cv


# ================================================================ composição
def compoe(fr: Image.Image, t: float, legendas: list[dict], n: int) -> Image.Image:
    cam = camera(t)
    tela = next((e for e in ELEMENTOS if isinstance(e, Tela) and e.t0 <= t < e.t1), None)
    if tela is not None:
        return efeito_transicao(tela.desenha_tela(t), t)
    quadro = aplica_camera(fr, cam)
    cv = quadro.copy()
    tits = [x for x in TITULOS if x.ativo(t)]
    els = [e for e in ELEMENTOS if e.ativo(t)]
    atras = [x for x in tits if x.atras] + [e for e in els if e.atras]
    if atras:
        for e in els:
            e.desenha_atras(cv, t, cam)
        camada = None
        if any(x.atras for x in tits):
            camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for x in tits:
                if x.atras:
                    x.desenha(camada, t)
            cv.alpha_composite(camada)
        m = mascara(n)
        if m is not None:   # ela por cima de tudo que está atrás
            mt = aplica_camera(m, cam, Image.BILINEAR)
            pessoa = quadro.copy()
            pessoa.putalpha(mt)
            cv.alpha_composite(pessoa)
            if camada is not None and VIDRO_TIT > 0:
                # vidro: o título continua visível por cima dela, translúcido (v2 "agent.", v4 "blessed")
                a = ImageChops.multiply(camada.getchannel("A"), mt.point(lambda v: int(v * VIDRO_TIT)))
                vidro = camada.copy()
                vidro.putalpha(a)
                cv.alpha_composite(vidro)
    for e in els:
        e.desenha_frente(cv, t, cam)
    for x in tits:
        if not x.atras:
            x.desenha(cv, t)
    # legenda pequena some quando tem título na tela (o título substitui a legenda)
    if not tits and not any(e.esconde_legenda for e in els):
        for b in legendas:
            if b["ini"] <= t < b["fim"]:
                im = legenda_img(b["txt"])
                k = k_in(t, b["ini"], 0.08)
                if k < 1:
                    im = opaco(desfoca(im, 6 * (1 - k)), k)
                cola_centro(cv, im, W / 2, legenda_y(t, cam))
                break
    return efeito_transicao(cv, t)


# ================================================================ áudio (voz + efeitos raros)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome == "impacto":   # grave curto na troca com flash (v4 ~35 s)
        n = int(0.55 * SR)
        tt = np.arange(n) / SR
        fr = 70 * np.exp(-tt * 3) + 38
        x = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 6)
        x += rng.standard_normal(n) * np.exp(-tt * 40) * 0.15
        return x / (np.abs(x).max() + 1e-9)
    if nome in ("whoosh", "notificacao"):
        d = 0.32 if nome == "whoosh" else 0.18
        n = int(d * SR)
        esp = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= np.exp(-((np.log(f + 1) - np.log(2600 if nome == "whoosh" else 4200)) ** 2) / 0.8)
        x = np.fft.irfft(esp, n) * _env(n, 0.55)
        return x / (np.abs(x).max() + 1e-9) * (1 if nome == "whoosh" else 0.6)
    if nome == "brilho":    # cintilar agudo curto (v4 5,5-6,5 s)
        n = int(0.4 * SR)
        tt = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * (9 + i * 3)) for i, f0 in enumerate((2637, 3520, 4186)))
        return x / (np.abs(x).max() + 1e-9) * 0.45
    if nome == "caneta":
        n = int(0.35 * SR)
        x = rng.standard_normal(n)
        esp = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= (f > 3000) & (f < 9000)
        x = np.fft.irfft(esp, n) * _env(n, 0.2)
        return x / (np.abs(x).max() + 1e-9) * 0.35
    d = 0.07   # pop
    n = int(d * SR)
    tt = np.arange(n) / SR
    fr = 1300 + (600 - 1300) * tt / d
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 45) * 0.6


def eventos_som() -> list[tuple[float, str]]:
    ev = []
    for tf, tipo in TRANS:
        if tipo == "flash":
            ev += [(tf - 0.12, "whoosh"), (tf, "impacto")]
        else:
            ev.append((tf - 0.1, "whoosh"))
    for e in ELEMENTOS:
        ev += e.eventos()
    return sorted(ev)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -27) if isinstance(cfg, dict) else -27
        ultimo = {}
        for t, nome in eventos_som():
            if t - ultimo.get(nome, -9) < 0.12:
                continue
            ultimo[nome] = t
            ganho = {"impacto": 1.6, "pop": 0.7, "brilho": 0.8}.get(nome, 1.0)
            s = sfx(nome) * 10 ** (gdb / 20) * ganho
            i = int(max(0, t) * SR)
            pista[i:i + len(s)] += s[: len(pista) - i]
    mus = MAPA.get("musica")   # a referência não tem trilha; só com arquivo e licença de uso
    if mus:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mus.get("inicio", 0)), "-i", str(_resolve(mus["arquivo"])),
                              "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = int(TOTAL * SR)
        x = np.tile(x, n // len(x) + 1)[:n]
        x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 10 ** (mus.get("db", -30) / 20)
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
    print("linha do tempo:")
    marcos = []
    for x in TITULOS:
        frase = " / ".join(x.spec["linhas"])
        print(f"  {x.t0:6.2f}-{x.t1:6.2f} título   {frase}{'' if x.atras else '  (na frente)'}")
        for lin in x.linhas:
            for tk in lin:
                marcos.append(tk["tempo"])
        if x.t1 - x.t0 < 1.0:
            print(f"  ATENÇÃO: título de {x.t1 - x.t0:.2f}s (a referência segura ~1,5-3 s)")
    for e in ELEMENTOS:
        print(f"  {e.t0:6.2f}-{e.t1:6.2f} {e.spec['tipo']:8s} {'(atrás) ' if e.atras else ''}")
        marcos.append(e.t0)
        for nome, te in e.itens_tempos():
            print(f"           · {te:6.2f} {nome}")
            marcos.append(te)
            if e.t1 - te < 0.5:
                print(f"  ATENÇÃO: '{nome}' acontece {e.t1 - te:.2f}s antes do elemento sair (mín. ~0,5 s)")
    for td, z in DEGRAUS:
        print(f"  {td:6.2f}        degrau   zoom {z:.2f}")
        marcos.append(td)
    for ta, z, d in APROX:
        print(f"  {ta:6.2f}        aproxima zoom {z:.2f} em {d:.1f}s")
        marcos.append(ta)
    for tf, tipo in TRANS:
        print(f"  {tf:6.2f}        {tipo}")
        marcos.append(tf)
    marcos = sorted(set([0.0] + marcos + list(OFF[1:-1]) + [TOTAL]))
    buracos = [(a, b) for a, b in zip(marcos, marcos[1:]) if b - a > 3.0]
    print(f"  algo novo na tela a cada {TOTAL / max(1, len(marcos) - 1):.1f}s em média (referência: ~1-1,5 s)")
    for a, b in buracos:
        print(f"  ATENÇÃO: {b - a:.1f}s sem nada novo ({a:.2f}-{b:.2f}): pôr degrau de zoom, pílula ou título")
    js = janelas_mascara()
    print(f"  recorte da pessoa em {sum(b - a for a, b in js):.1f}s de {TOTAL:.1f}s")


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_SB = {"pilulas": "Pílulas", "lista": "Lista em pílulas de vidro", "notificacao": "Notificação de vidro",
            "baloes": "Balões de chat", "icones": "Ícones pulando", "numero": "Número neon",
            "arco": "Arco de crescimento em volta da cabeça", "barra": "Barra que conta",
            "cronometro": "Cronômetro", "objeto": "Objeto voando", "cards": "Cards girando na cintura",
            "muro": "Muro de fotos atrás da pessoa", "livro": "Prints em livro aberto atrás da pessoa",
            "tela": "Print em tela cheia com caneta vermelha"}


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1: min(t, t1 - 0.05)
    ms, avisos = [], []
    for x in TITULOS:
        fim_tok = max([tk["tempo"] for lin in x.linhas for tk in lin] + [x.t0])
        m = {"t0": x.t0, "t1": x.t1, "quadro": cap(fim_tok + 0.35, x.t1),
             "tipo": "Título de revista " + ("atrás da pessoa" if x.atras else "na frente"),
             "desc": " / ".join(SB.limpa_marcacao(l) for l in x.spec["linhas"])}
        if x.t1 - x.t0 < 1.0:
            m["aviso"] = f"fica só {x.t1 - x.t0:.1f} s na tela (a referência segura ~1,5-3 s)"
        ms.append(m)
    for e in ELEMENTOS:
        tempos = [te for _, te in e.itens_tempos()]
        nome = NOMES_SB.get(e.spec["tipo"], e.spec["tipo"])
        if e.spec["tipo"] == "pilulas":
            nome += " de vidro" if e.spec.get("estilo") == "vidro" else " neon"
        if e.atras and "atrás" not in nome:
            nome += " (atrás da pessoa)"
        m = {"t0": e.t0, "t1": e.t1, "quadro": cap(max([e.t0 + 0.8] + [te + 0.35 for te in tempos]), e.t1),
             "tipo": nome, "desc": SB.textos_do_spec(e.spec) or "—"}
        curtos = [n for n, te in e.itens_tempos() if e.t1 - te < 0.5]
        if curtos:
            m["aviso"] = f"{', '.join(curtos)} aparece menos de 0,5 s antes de sair"
        ms.append(m)
    for td, z in DEGRAUS:
        ms.append({"t0": td, "t1": td, "quadro": td + 0.15, "tipo": "Câmera: degrau",
                   "desc": f"corte seco pra mais perto ({z:.2f}x)".replace(".", ",")})
    for ta, z, d in APROX:
        ms.append({"t0": ta, "t1": ta + d, "quadro": ta + d, "tipo": "Câmera: aproxima",
                   "desc": f"aproxima devagar até {z:.2f}x em {d:.1f} s".replace(".", ",")})
    for tf, tipo in TRANS:
        ms.append({"t0": tf, "t1": tf, "quadro": tf + 0.12,
                   "tipo": "Transição: " + ("flash branco" if tipo == "flash" else tipo),
                   "desc": "troca de bloco do roteiro"})
    marcos = sorted(set([0.0, TOTAL] + [m["t0"] for m in ms] + list(OFF[1:-1])))
    for a, b in zip(marcos, marcos[1:]):
        if b - a > 3.0:
            avisos.append(f"{b - a:.1f} s sem nada novo ({a:.1f}–{b:.1f} s): dá pra pôr degrau de zoom, pílula ou título"
                          .replace(".", ","))
    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]
    arqs = []
    for spec in MAPA.get("elementos", []):
        nomes = [spec.get("arquivo"), spec.get("avatar")] + list(spec.get("arquivos", []))
        nomes += [i.get("arquivo") for i in spec.get("itens", []) if isinstance(i, dict)]
        for a in nomes:
            if isinstance(a, dict):
                a = a.get("arquivo")
            if a and a not in [x for x, _ in arqs]:
                try:
                    _resolve(a); ok = True
                except SystemExit:
                    ok = False
                arqs.append((a, ok))

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, legendas, n)

    out = SB.gerar(EDIT, "Kelsey", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if janelas_mascara() and not (EDIT / "masks" / "out").exists():
        sys.exit("tem coisa atrás da pessoa (título, arco, muro...): rode mascaras.py antes")
    legendas = monta_legendas()
    resumo()
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
            compoe(quadro_base(n), t, legendas, n).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
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
    prenorm = EDIT / f"{modo}_kelsey.prenorm.mp4"
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
        enc.stdin.write(compoe(fr, t, legendas, k).convert("RGB").tobytes())
        k += 1
        if k % 300 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_kelsey.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
