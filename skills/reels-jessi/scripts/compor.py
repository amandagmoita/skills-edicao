"""compor.py — monta o Reel no estilo "Jessi" quadro a quadro, a partir do mapa.json.

Estilo medido na referência (referencia/referencias-estilo.md, Reel da Jessi Jean "get Claude to edit our
yaps"): cada benefício falado vira um OBJETO que faz a ação na tela no mesmo segundo, quase sempre uma
interface que o público reconhece (pasta do Finder com cursor, texto selecionado que troca de fonte, card
que gira opções, timeline de editor). Legenda de UMA palavra, sans branca, palavra de benefício em serifa
itálica amarela; três tamanhos (aparte pequeno, normal, interjeição gigante). Escrita à mão com seta pro
comentário sobre a própria pessoa. Texto e B-roll atrás da cabeça; interface na frente.

Camadas de cada quadro:
  atrás   linhas de título marcadas "atras", tira de B-roll, grade de Reels, metade dos cards da explosão
  pessoa  o vídeo recortado pelo Vision (masks/out), só quando há algo atrás
  frente  cards, tela de vidro, escrita à mão, Finder, card escuro, editor, card de documento, timeline,
          botão, título na frente, legenda

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_jessi.mp4 | final_jessi.mp4

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
    [palavra, tomada, atraso] (atraso em relação ao início da palavra)."""
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
    """Passa do tamanho e volta."""
    x = cl(x)
    c1 = 1.7
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- cores
# Referência: amarelo-manteiga #F5E57D. Padrão: cor de destaque do perfil (padrão do pack #FFC700).
AMARELO = hexa(MAPA.get("destaque", PERFIL["cor_destaque"]))
BRANCO = (255, 255, 255)
TINTA = (20, 20, 22)
AZUL_SEL = (120, 196, 255)        # realce de texto selecionado (referência 28,0 s)
AZUL_PASTA = (88, 170, 245)       # pasta do Finder
VERMELHO = (255, 59, 48)          # bolinha de contagem
PETROLEO = (42, 157, 159)         # faixa de clipes da timeline
LARANJA = (232, 120, 72)          # faixa de legendas da timeline

# ---------------------------------------------------------------- fontes (só fontes do Mac)
_SF = "/System/Library/Fonts/SFNS.ttf"
_DIDOT = "/System/Library/Fonts/Supplemental/Didot.ttc"
_NOTE = "/System/Library/Fonts/Noteworthy.ttc"
FONTES = {
    "sans": (_SF, 0, "Medium"), "sans_semi": (_SF, 0, "Semibold"), "sans_bold": (_SF, 0, "Bold"),
    "sans_reg": (_SF, 0, "Regular"),
    "serifa": (_DIDOT, 1, None),          # Didot Itálico: condensado + engrossado em mascara_texto
    "mao": (_NOTE, 0, None),              # Noteworthy Light: letra de caneta
}
# A serifa da referência é itálica condensada de contraste alto (cara de Instrument Serif Italic).
# Didot Itálico estreitado a 82% e engrossado 1 px de cada lado é o mais perto que o Mac tem.
SERIFA_COND = float(MAPA.get("serifa_cond", 0.82))
SERIFA_PESO = int(MAPA.get("serifa_peso", 3))


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, idx, var = FONTES[tipo]
    f = ImageFont.truetype(arq, max(6, int(size)), index=idx)
    if var:
        f.set_variation_by_name(var)
    return f


# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "topo": 150,             # nada sobe acima disto (barra do Instagram), salvo linha "atras"
    "base": 0.76,            # nada desce além disto (legenda e botões do Instagram)
    "leg_tam": 96,           # legenda de uma palavra (sans)
    "leg_serifa": 1.38,      # palavra amarela fica isto maior (referência: ~1,3-1,4x)
    "leg_gigante": 2.1,      # interjeição ("oh," da referência)
    "leg_aparte": 50,        # aparte pequeno ("no, seriously.")
    "leg_track": -0.03,
    "leg_queixo": 175,       # legenda: tantos px abaixo do queixo
    "leg_min": 0.52, "leg_max": 0.66,
    "tit_tam": 88,           # título empilhado: corpo da sans; serifa = tit_tam * leg_serifa
    "rosto_cy": 0.40,
}
LAY.update(MAPA.get("layout", {}))


# ---------------------------------------------------------------- utilidades de imagem
def cola(dest: Image.Image, im: Image.Image | None, x: int, y: int) -> None:
    if im is None:
        return
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def cola_centro(dest: Image.Image, im: Image.Image | None, cx: float, cy: float) -> None:
    if im is None:
        return
    cola(dest, im, int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


def desfoca(im: Image.Image, r: float) -> Image.Image:
    if r < 0.4:
        return im
    return im.convert("RGBa").filter(ImageFilter.GaussianBlur(r)).convert("RGBA")


def opaco(im: Image.Image | None, a: float) -> Image.Image | None:
    if im is None or a >= 0.999:
        return im
    if a <= 0.001:
        return None
    out = im.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * cl(a))))
    return out


def escala(im: Image.Image, s: float, sy: float | None = None) -> Image.Image:
    sy = s if sy is None else sy
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * sy))), Image.BICUBIC)


def gira(im: Image.Image, graus: float) -> Image.Image:
    if abs(graus) < 0.05:
        return im
    return im.rotate(graus, resample=Image.BICUBIC, expand=True)


def com_margem(im: Image.Image, m: int) -> Image.Image:
    out = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    out.alpha_composite(im, (m, m))
    return out


def k_in(t: float, t0: float, d: float = 0.2) -> float:
    return cl((t - t0) / d)


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
    """Card arredondado com sombra macia embaixo (todos os objetos da referência têm)."""
    m = 44
    base = Image.new("RGBA", (im.width + 2 * m, im.height + 2 * m), (0, 0, 0, 0))
    s = Image.new("L", base.size, 0)
    ImageDraw.Draw(s).rounded_rectangle((m, m + dy, m + im.width, m + im.height + dy), radius=r, fill=int(255 * forca))
    sh = Image.new("RGBA", base.size, (0, 0, 0, 255))
    sh.putalpha(s.filter(ImageFilter.GaussianBlur(raio)))
    base.alpha_composite(sh)
    base.alpha_composite(arredonda(im, r), (m, m))
    return base


def cobre(im: Image.Image, w: int, h: int) -> Image.Image:
    esc = max(w / im.width, h / im.height)
    r = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def contem(im: Image.Image, w: float, h: float) -> Image.Image:
    s = min(w / im.width, h / im.height)
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)


# ---------------------------------------------------------------- texto
@functools.lru_cache(maxsize=2048)
def mascara_texto(txt: str, tipo: str, tam: int, track: float = 0.0) -> tuple[Image.Image, int]:
    """(máscara L, y da linha de base). Serifa sai estreitada e engrossada (ver SERIFA_COND)."""
    f = F(tipo, tam)
    pad = int(tam * 0.35) + 8
    asc, desc = f.getmetrics()
    larg = sum(f.getlength(c) for c in txt) + track * tam * max(0, len(txt) - 1)
    w, h = int(larg) + 2 * pad, asc + desc + 2 * pad
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    x, base = pad, pad + asc
    for c in txt:
        d.text((x, base), c, font=f, fill=255, anchor="ls")
        x += f.getlength(c) + track * tam
    if tipo == "serifa":
        if SERIFA_PESO > 1:
            m = m.filter(ImageFilter.MaxFilter(SERIFA_PESO))
        if SERIFA_COND != 1.0:
            m = m.resize((max(2, int(m.width * SERIFA_COND)), m.height), Image.LANCZOS)
    return m, base


def sombra_de(m: Image.Image, raio: float, forca: float, dy: int = 0, cor: tuple = (0, 0, 0)) -> Image.Image:
    s = Image.new("RGBA", m.size, cor + (255,))
    s.putalpha(m.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: int(min(255, v * forca))))
    if dy:
        out = Image.new("RGBA", m.size, (0, 0, 0, 0))
        out.alpha_composite(s, (0, dy))
        return out
    return s


@functools.lru_cache(maxsize=2048)
def palavra(txt: str, tipo: str, tam: int, cor: tuple, halo: float = 0.75, track: float = 0.0) -> tuple[Image.Image, int]:
    """Palavra pronta (RGBA) e a linha de base. Halo escuro macio + sombra curta: roupa branca e parede
    clara comem texto branco (a referência quase não tem sombra porque o fundo dela é escuro)."""
    m, base = mascara_texto(txt, tipo, tam, track)
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    if halo:
        im.alpha_composite(sombra_de(m, tam * 0.22, halo * 0.75))
        im.alpha_composite(sombra_de(m, max(2, tam * 0.045), halo, max(1, int(tam * 0.02))))
    c = Image.new("RGBA", m.size, cor + (255,))
    c.putalpha(m)
    im.alpha_composite(c)
    return im, base


def tokens(linha: str) -> list[tuple[str, str]]:
    """'um empreendedor *perde*' → [('um','sans'), ('empreendedor','sans'), ('perde','serifa')]."""
    out = []
    serif = False
    for p in linha.split():
        abre, fecha = p.startswith("*"), p.endswith("*") and len(p) > 1
        if abre:
            serif = True
        txt = p.strip("*")
        out.append((txt, "serifa" if serif else "sans"))
        if fecha:
            serif = False
    return out


def linha_img(toks: list[tuple[str, str]], tam: int, visiveis: int | None = None, halo: float = 0.75) -> Image.Image:
    """Monta uma linha misturando sans branca e serifa amarela pela linha de base. As palavras ainda não
    faladas ocupam lugar (a linha não pula) mas ficam invisíveis."""
    pecas = []
    for i, (txt, tipo) in enumerate(toks):
        tt = int(tam * LAY["leg_serifa"]) if tipo == "serifa" else tam
        cor = AMARELO if tipo == "serifa" else BRANCO
        im, base = palavra(txt, tipo, tt, cor, halo, LAY["leg_track"] if tipo == "sans" else 0.0)
        pecas.append((im, base, tt))
    # margem real de cada peça (a serifa foi estreitada junto com a margem)
    pad = [int((int(p[2] * 0.35) + 8) * (SERIFA_COND if tp == "serifa" else 1)) for p, (_, tp) in zip(pecas, toks)]
    esp = int(tam * 0.26)
    larg = sum(p[0].width - 2 * pd for p, pd in zip(pecas, pad)) + esp * (len(pecas) - 1)
    asc = max(p[1] for p in pecas)
    desc = max(p[0].height - p[1] for p in pecas)
    out = Image.new("RGBA", (larg + 2 * max(pad), asc + desc), (0, 0, 0, 0))
    x = max(pad)
    for i, ((im, base, _), pd) in enumerate(zip(pecas, pad)):
        if visiveis is None or i < visiveis:
            out.alpha_composite(im, (x - pd, asc - base))
        x += im.width - 2 * pd + esp
    return out


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


@functools.lru_cache(maxsize=128)
def imagem(arq: str) -> Image.Image:
    return Image.open(_resolve(arq)).convert("RGBA")


# ================================================================ CÂMERA (zoom por tomada, degraus, aproximação)
# Na referência a câmera muda de enquadramento a cada ~2,5 s (corte seco) e dá degrau de zoom no mesmo take.
ZOOM_TOMADAS = MAPA.get("zoom_tomadas", [1.0, 1.08])
DEGRAUS = sorted([(T(d["em"]), float(d["z"])) for d in MAPA.get("degraus", [])])
APROX = sorted([(T(d["em"]), float(d["z"]), float(d.get("dur", 0.4))) for d in MAPA.get("aproxima", [])])


def zoom_em(t: float) -> float:
    g = grupo(t)
    z = float(ZOOM_TOMADAS[g % len(ZOOM_TOMADAS)])
    a, b = OFF[g], OFF[g + 1]
    eventos = [(td, "d", zd, 0) for td, zd in DEGRAUS if a <= td < b] + \
              [(ta, "a", za, da) for ta, za, da in APROX if a <= ta < b]
    for te, tipo, ze, de in sorted(eventos):
        if t < te:
            break
        z = ze if tipo == "d" else lerp(z, ze, ease_in_out((t - te) / de))
    return max(1.0, z)


def camera(t: float) -> tuple[float, float, float]:
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
    """Topo do cabelo, caixa do rosto e queixo já na tela (depois do zoom)."""
    cam = cam or camera(t)
    g = MED[grupo(t)]
    r = g["rosto"]
    _, topo = na_tela(cam, 0, g["topo"])
    x0, y0 = na_tela(cam, r[0], r[1])
    x1, y1 = na_tela(cam, r[0] + r[2], r[1] + r[3])
    return {"topo": topo, "x0": x0, "x1": x1, "y0": y0, "queixo": y1, "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2}


# ================================================================ ELEMENTOS
class Elemento:
    atras = False            # tem parte atrás da pessoa (precisa de máscara)
    esconde_legenda = False
    som_entrada = "pop"

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        if self.t1 <= self.t0:
            sys.exit(f"{spec.get('tipo')}: termina antes de começar ({self.t0:.2f}-{self.t1:.2f})")

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1 + self.saida_d()

    def saida_d(self) -> float:
        return 0.16

    def k_saida(self, t: float) -> float:
        return 1 - ease_out(cl((t - self.t1) / self.saida_d())) if t >= self.t1 else 1.0

    def desenha_atras(self, cv: Image.Image, t: float, cam: tuple) -> None:
        pass

    def desenha_frente(self, cv: Image.Image, t: float, cam: tuple) -> None:
        pass

    def eventos(self) -> list[tuple[float, str]]:
        return [(self.t0, self.som_entrada)]

    def itens_tempos(self) -> list[tuple[str, float]]:
        return []

    def tempo_item(self, spec) -> float:
        return T(spec) + ANTECIPA if isinstance(spec, list) and len(spec) == 2 else T(spec)


def pos_px(p, padrao=(0.5, 0.5)) -> tuple[float, float]:
    p = p or padrao
    return float(p[0]) * W, float(p[1]) * H


# ---------------------------------------------------------------- cursor do Mac (desenhado)
@functools.lru_cache(maxsize=8)
def cursor_img(tam: int = 54, apertado: bool = False) -> Image.Image:
    s = tam / 24
    pts = [(0, 0), (0, 17), (4.2, 13.2), (7, 19.5), (9.6, 18.4), (6.9, 12.3), (12.3, 12.3)]
    pts = [(2 + x * s, 2 + y * s) for x, y in pts]
    im = Image.new("RGBA", (int(16 * s) + 6, int(24 * s) + 6), (0, 0, 0, 0))
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    sh = sombra_de(m, 3, 0.5, 2)
    im.alpha_composite(sh)
    d = ImageDraw.Draw(im)
    d.polygon(pts, fill=(250, 250, 250, 255))
    inner = [(2 + (x - 2) * 0.82 + 0.9 * s, 2 + (y - 2) * 0.82 + 1.5 * s) for x, y in pts]
    d.polygon(inner, fill=(15, 15, 15, 255))
    if apertado:
        im = escala(im, 0.88)
    return im


# ---------------------------------------------------------------- cards que aparecem (Reels dos episódios, docs)
def card_img(arq: str, larg: int, estilo: str = "foto", handle: str = "", rotulo: str = "") -> Image.Image:
    """estilo "foto": imagem com borda branca fina e cantos arredondados; "ig": cabeçalho do Instagram
    (avatar + @ + selo) em cima, como os cards dos episódios anteriores da referência (0,3-2,3 s)."""
    src = imagem(arq)
    alt = int(larg * src.height / src.width)
    alt = min(alt, int(larg * 1.6))
    foto = cobre(src, larg, alt)
    if estilo == "ig":
        cab = int(larg * 0.17)
        card = Image.new("RGBA", (larg, alt + cab), (255, 255, 255, 255))
        card.alpha_composite(foto, (0, cab))
        d = ImageDraw.Draw(card)
        r = int(cab * 0.32)
        cy = cab // 2
        d.ellipse((int(cab * 0.25), cy - r, int(cab * 0.25) + 2 * r, cy + r), fill=(205, 205, 210))
        f = F("sans_semi", max(10, int(cab * 0.32)))
        x = int(cab * 0.25) + 2 * r + int(cab * 0.18)
        d.text((x, cy), handle or PERFIL["instagram"], font=f, fill=TINTA, anchor="lm")
        xs = x + f.getlength(handle or PERFIL["instagram"]) + cab * 0.12
        rr = cab * 0.12
        d.ellipse((xs, cy - rr, xs + 2 * rr, cy + rr), fill=(0, 149, 246))
        return com_sombra(card, int(larg * 0.07), 0.38, 16, 8)
    b = max(4, int(larg * 0.025))
    card = Image.new("RGBA", (larg, alt), (255, 255, 255, 255))
    card.alpha_composite(arredonda(cobre(src, larg - 2 * b, alt - 2 * b), int(larg * 0.05)), (b, b))
    if rotulo:
        f = F("sans_semi", max(16, int(larg * 0.11)))
        tw = f.getlength(rotulo)
        ph = int(larg * 0.19)
        pill = Image.new("RGBA", (int(tw + ph * 0.9), ph), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, ph - 1), radius=ph // 2, fill=(255, 255, 255, 245))
        ImageDraw.Draw(pill).text((pill.width / 2, ph / 2), rotulo, font=f, fill=TINTA, anchor="mm")
        card.alpha_composite(pill, ((larg - pill.width) // 2, alt - ph - int(larg * 0.06)))
    return com_sombra(card, int(larg * 0.07), 0.38, 16, 8)


class Cards(Elemento):
    """Cards que aparecem secos, já no tamanho, levemente inclinados, um por palavra (Reels dos episódios
    anteriores 0,3 e 1,0 s; documentos). itens: [{arquivo, em, pos:[x,y], larg, incl, estilo, handle, rotulo}]"""

    def __init__(self, spec):
        super().__init__(spec)
        self.itens = []
        for i, it in enumerate(spec["itens"]):
            larg = int(it.get("larg", 250))
            im = card_img(it["arquivo"], larg, it.get("estilo", spec.get("estilo", "foto")),
                          it.get("handle", spec.get("handle", "")), it.get("rotulo", ""))
            incl = float(it.get("incl", 4 if i % 2 else -4))
            self.itens.append({"t": self.tempo_item(it.get("em", spec["em"])) - ANTECIPA,
                               "im": gira(im, incl), "pos": pos_px(it.get("pos"))})

    def desenha_frente(self, cv, t, cam):
        ks = self.k_saida(t)
        for it in self.itens:
            if t < it["t"]:
                continue
            k = ease_out(k_in(t, it["t"], 0.09))
            im = escala(it["im"], lerp(0.9, 1, k)) if k < 1 else it["im"]
            cola_centro(cv, opaco(im, min(k * 1.4, 1) * ks), *it["pos"])

    def eventos(self):
        return [(it["t"], "pop") for it in self.itens]

    def itens_tempos(self):
        return [(Path(s["arquivo"]).stem, it["t"]) for s, it in zip(self.spec["itens"], self.itens)]


# ---------------------------------------------------------------- tela de vidro (10,7-12,0 s)
class Vidro(Elemento):
    """Retângulo arredondado com borda de vidro fosco (o fundo atrás desfocado e clareado) e a imagem dentro,
    aproximando devagar. pos [x,y] = centro; larg/alt em px; incl em graus."""
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.w, self.h = int(spec.get("larg", 300)), int(spec.get("alt", 440))
        self.cx, self.cy = pos_px(spec.get("pos"), (0.80, 0.30))
        self.incl = float(spec.get("incl", 3))
        self.src = imagem(spec["arquivo"])

    def desenha_frente(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, 0.2))
        a = min(1.0, k * 1.3) * self.k_saida(t)
        if a <= 0:
            return
        w, h = self.w, self.h
        b = int(w * 0.045)
        x0, y0 = int(self.cx - w / 2), int(self.cy - h / 2 + 50 * (1 - k))
        fundo = cv.crop((x0, y0, x0 + w, y0 + h)).filter(ImageFilter.GaussianBlur(16))
        fundo = Image.blend(fundo, Image.new("RGBA", fundo.size, (255, 255, 255, 255)), 0.38)
        kb = 1 + 0.07 * cl((t - self.t0) / max(0.5, self.t1 - self.t0))
        foto = cobre(self.src, int((w - 2 * b) * kb), int((h - 2 * b) * kb))
        foto = foto.crop(((foto.width - (w - 2 * b)) // 2, (foto.height - (h - 2 * b)) // 2,
                          (foto.width - (w - 2 * b)) // 2 + w - 2 * b, (foto.height - (h - 2 * b)) // 2 + h - 2 * b))
        fundo.alpha_composite(arredonda(foto, int(w * 0.07)), (b, b))
        ImageDraw.Draw(fundo).rounded_rectangle((0, 0, w - 1, h - 1), radius=int(w * 0.11),
                                                outline=(255, 255, 255, 150), width=2)
        card = gira(com_sombra(fundo, int(w * 0.11), 0.3, 18, 10), self.incl)
        cola_centro(cv, opaco(card, a), self.cx, y0 + h / 2)


# ---------------------------------------------------------------- escrita à mão + seta (9,0-10,6 s)
class Mao(Elemento):
    """Frase em letra de caneta que se escreve e uma seta curva que se desenha apontando pra pessoa.
    texto (\\n quebra), pos [x,y] = canto sup. esquerdo do texto, alvo [x,y] = ponta da seta,
    curva (+ ou -) = para que lado a seta arqueia."""
    som_entrada = "caneta"

    def __init__(self, spec):
        super().__init__(spec)
        self.linhas = spec["texto"].split("\n")
        self.tam = int(spec.get("tam", 78))
        self.x, self.y = pos_px(spec.get("pos"), (0.06, 0.20))
        self.alvo = pos_px(spec.get("alvo"), (0.30, 0.34))
        self.curva = float(spec.get("curva", 1.0))
        self.n = sum(len(l) for l in self.linhas)
        self.d_txt = min(0.45, 0.03 * self.n)
        f = F("mao", self.tam)
        self.lh = int(self.tam * 1.08)
        self.larg = max(f.getlength(l) for l in self.linhas)

    def ponto(self, u: float):
        """Seta: bezier quadrática do pé do texto até o alvo."""
        p0 = (self.x + self.larg * 0.55, self.y + self.lh * len(self.linhas) + 10)
        p2 = self.alvo
        mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
        nx, ny = -(p2[1] - p0[1]), p2[0] - p0[0]
        n = math.hypot(nx, ny) or 1
        p1 = (mx + nx / n * 70 * self.curva, my + ny / n * 70 * self.curva)
        x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u ** 2 * p2[0]
        y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u ** 2 * p2[1]
        return x, y

    def desenha_frente(self, cv, t, cam):
        a = self.k_saida(t)
        if a <= 0:
            return
        camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        f = F("mao", self.tam)
        kt = cl((t - self.t0) / self.d_txt)
        mostra = int(round(self.n * kt))
        for i, l in enumerate(self.linhas):
            vis = l[:max(0, mostra)]
            mostra -= len(l)
            if vis:
                d.text((self.x, self.y + i * self.lh), vis, font=f, fill=255)
        ks = cl((t - self.t0 - self.d_txt) / 0.2)
        if ks > 0:
            pts = [self.ponto(u) for u in np.linspace(0, ks, 24)]
            d.line(pts, fill=255, width=6, joint="curve")
            if ks >= 0.98:   # ponta da seta
                (xa, ya), (xb, yb) = self.ponto(0.9), self.ponto(1.0)
                ang = math.atan2(yb - ya, xb - xa)
                for s in (-1, 1):
                    d.line([(xb, yb), (xb - 26 * math.cos(ang + s * 0.55), yb - 26 * math.sin(ang + s * 0.55))],
                           fill=255, width=6)
        camada.alpha_composite(sombra_de(m, 7, 0.85, 2))
        c = Image.new("RGBA", (W, H), BRANCO + (255,))
        c.putalpha(m)
        camada.alpha_composite(c)
        im = opaco(camada, a)
        if im is not None:
            cv.alpha_composite(im)


# ---------------------------------------------------------------- Finder: arrasta pra pasta (13,1-14,5 s)
@functools.lru_cache(maxsize=4)
def pasta_img(larg: int) -> Image.Image:
    h = int(larg * 0.78)
    im = Image.new("RGBA", (larg, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    escuro = tuple(int(c * 0.82) for c in AZUL_PASTA)
    d.rounded_rectangle((0, 0, int(larg * 0.42), int(h * 0.3)), radius=int(larg * 0.06), fill=escuro)
    d.rounded_rectangle((0, int(h * 0.12), larg, h), radius=int(larg * 0.07), fill=escuro)
    d.rounded_rectangle((0, int(h * 0.22), larg, h), radius=int(larg * 0.07), fill=AZUL_PASTA)
    return im


def arquivo_icone(arq: str, larg: int) -> Image.Image:
    alt = int(larg * 1.3)
    card = Image.new("RGBA", (larg, alt), (255, 255, 255, 255))
    b = max(3, larg // 18)
    card.alpha_composite(cobre(imagem(arq), larg - 2 * b, alt - 2 * b), (b, b))
    return com_sombra(card, max(4, larg // 10), 0.35, 6, 3)


class Finder(Elemento):
    """Janela branca do Finder: pilha de arquivos à esquerda, pasta azul à direita; o cursor arrasta a pilha
    pra pasta, aparece a bolinha vermelha com a contagem e a pilha some dentro. arquivos: lista de imagens;
    nome: rótulo da pasta; arrasta: quando o cursor pega (padrão 0,35 s depois de entrar)."""

    def __init__(self, spec):
        super().__init__(spec)
        self.larg, self.alt = int(spec.get("larg", 700)), int(spec.get("alt", 250))
        self.cx, self.cy = pos_px(spec.get("pos"), (0.5, 0.70))
        self.t_arr = self.tempo_item(spec["arrasta"]) if spec.get("arrasta") else self.t0 + 0.35
        self.icones = [gira(arquivo_icone(a, 118), r) for a, r in zip(spec["arquivos"], (-8, 4, 12, -3))]
        self.nome = spec.get("nome", "Briefing")
        self.n = len(spec["arquivos"])

    def desenha_frente(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, 0.14))
        a = min(1.0, k * 1.4) * self.k_saida(t)
        if a <= 0:
            return
        w, h = self.larg, self.alt
        jan = Image.new("RGBA", (w, h), (255, 255, 255, 250))
        x0, y0 = int(self.cx - w / 2), int(self.cy - h / 2)
        # pasta
        pw = int(h * 0.62)
        pasta = pasta_img(pw)
        px, py = int(w * 0.78 - pw / 2), int(h * 0.42 - pasta.height / 2)
        dt = t - self.t_arr
        chegou = dt > 0.62
        if chegou:   # pula ao receber
            s = mola(cl((dt - 0.62) / 0.28))
            pasta = escala(pasta, lerp(1.12, 1, s) if s < 1 else 1)
        jan.alpha_composite(pasta, (px + (pw - pasta.width) // 2, py + (int(pw * 0.78) - pasta.height) // 2))
        f = F("sans_reg", int(h * 0.1))
        ImageDraw.Draw(jan).text((w * 0.78, py + pw * 0.78 + h * 0.09), self.nome, font=f, fill=(60, 60, 64), anchor="mm")
        if chegou:
            br = int(h * 0.075)
            bx, by = px + pw - br, py + int(pw * 0.08)
            ImageDraw.Draw(jan).ellipse((bx - br, by - br, bx + br, by + br), fill=VERMELHO)
            ImageDraw.Draw(jan).text((bx, by), str(self.n), font=F("sans_bold", int(br * 1.3)), fill=BRANCO, anchor="mm")
        card = com_sombra(jan, int(h * 0.12), 0.3, 18, 10)
        m = 44
        cv_card = card
        # pilha: parada na esquerda, vai com o cursor, encolhe dentro da pasta
        sx0, sy0 = w * 0.25, h * 0.5
        sx1, sy1 = px + pw / 2, py + pw * 0.4
        u = ease_in_out(cl((dt - 0.12) / 0.5))
        ex = lerp(sx0, sx1, u)
        ey = lerp(sy0, sy1, u) - math.sin(u * math.pi) * h * 0.25
        enc = 1 - cl((dt - 0.55) / 0.12)
        if enc > 0:
            esc = lerp(1, 0.55, u) * (0.3 + 0.7 * enc) * (1.06 if 0 < dt < 0.12 else 1)
            for i, ic in enumerate(self.icones):
                im = escala(ic, esc)
                cola_centro(cv_card, opaco(im, enc), m + ex + (i - 1) * 26 * esc, m + ey + (i - 1) * 6 * esc)
        # cursor
        if -0.25 < dt < 0.95:
            if dt < 0:
                cxp = lerp(w * 0.55, sx0 + 30, ease_out(cl((dt + 0.25) / 0.25)))
                cyp = lerp(h * 0.95, sy0 + 20, ease_out(cl((dt + 0.25) / 0.25)))
            else:
                cxp, cyp = ex + 30, ey + 20
            cola(cv_card, cursor_img(54, 0 <= dt < 0.62), int(m + cxp), int(m + cyp))
        cola(cv, opaco(escala(cv_card, lerp(0.92, 1, k)) if k < 1 else cv_card, a), x0 - m, y0 - m)

    def eventos(self):
        return [(self.t0, "pop"), (self.t_arr, "clique"), (self.t_arr + 0.62, "pop")]

    def itens_tempos(self):
        return [("arrasta", self.t_arr)]


# ---------------------------------------------------------------- card escuro "custom animation" (18,4-19,9 s)
class CardEscuro(Elemento):
    """Card preto vertical que entra deslizando pela borda, inclinado; fundo com a palavra repetida em cinza
    escuro; as linhas se escrevem na fala (sans branca pequena / *serifa amarela grande*); sublinhado amarelo
    que se desenha e brilhinhos. linhas: [{txt, em}] ou strings (entram juntas com o card)."""
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.lado = spec.get("lado", "dir")
        self.w, self.h = int(spec.get("larg", 380)), int(spec.get("alt", 560))
        self.cy = float(spec.get("y", 0.33)) * H
        self.incl = float(spec.get("incl", -5 if self.lado == "dir" else 5))
        self.linhas = []
        for l in spec["linhas"]:
            l = {"txt": l} if isinstance(l, str) else l
            self.linhas.append({"toks": tokens(l["txt"]), "t": self.tempo_item(l["em"]) - ANTECIPA if l.get("em") else self.t0})
        fundo = spec.get("fundo") or " ".join(tx for l in self.linhas for tx, tp in l["toks"] if tp == "serifa")
        self.fundo = self._fundo(fundo or "ia")

    def _fundo(self, palavra_fundo: str) -> Image.Image:
        im = Image.new("RGBA", (self.w, self.h), (16, 16, 18, 255))
        d = ImageDraw.Draw(im)
        f = F("serifa", 74)
        y = -20
        i = 0
        while y < self.h:
            d.text((-60 + (i % 2) * 70, y), (palavra_fundo + " ") * 4, font=f, fill=(44, 44, 46))
            y += 78
            i += 1
        return im

    def desenha_frente(self, cv, t, cam):
        card = self.fundo.copy()
        tam = int(self.w * float(self.spec.get("letra", 0.15)))
        y = self.h * 0.28
        ult = None
        for l in self.linhas:
            if t < l["t"]:
                break
            li = linha_img(l["toks"], tam, halo=0.0)
            k = ease_out(k_in(t, l["t"], 0.1))
            li = opaco(escala(li, lerp(0.92, 1, k)), k) if k < 1 else li
            cola_centro(card, li, self.w / 2, y)
            ult = (y, li.width, l["t"])
            y += li.height * 0.78
        if ult:
            yl, wl, tl = ult
            ku = ease_out(cl((t - tl - 0.12) / 0.3))
            if ku > 0:
                lw = wl * 0.62
                ImageDraw.Draw(card).line([(self.w / 2 - lw / 2, yl + tam * 0.75), (self.w / 2 - lw / 2 + lw * ku, yl + tam * 0.75)],
                                          fill=AMARELO, width=5)
            for j, (sx, sy) in enumerate(((0.83, -0.55), (0.18, 0.95), (0.88, 0.7))):
                kk = math.sin(cl((t - tl - j * 0.15) / 0.6) * math.pi)
                if kk > 0:
                    r = 9 * kk
                    cx, cy = self.w * sx, yl + tam * sy
                    ImageDraw.Draw(card).polygon([(cx, cy - r * 2), (cx + r * 0.4, cy), (cx, cy + r * 2), (cx - r * 0.4, cy)], fill=AMARELO)
                    ImageDraw.Draw(card).polygon([(cx - r * 2, cy), (cx, cy - r * 0.4), (cx + r * 2, cy), (cx, cy + r * 0.4)], fill=AMARELO)
        im = gira(com_sombra(card, int(self.w * 0.09), 0.45, 20, 10), self.incl)
        k = ease_out(k_in(t, self.t0, 0.22))
        ks = 1 - self.k_saida(t)
        dentro = W - 22 + 44 - im.width / 2 if self.lado == "dir" else 22 - 44 + im.width / 2
        fora = W + im.width / 2 if self.lado == "dir" else -im.width / 2
        cx = lerp(fora, dentro, k) if ks <= 0 else lerp(dentro, fora, ease_out(ks))
        cola_centro(cv, im, cx, self.cy)

    def eventos(self):
        return [(self.t0, "whoosh")] + [(l["t"], "pop") for l in self.linhas[1:]]


# ---------------------------------------------------------------- texto selecionado que troca de fonte (27,2-28,5 s)
class Editor(Elemento):
    """Texto branco com a barra de formatação (B I U Aa) em cima; o cursor seleciona (realce azul) e o texto
    vira serifa amarela. texto, seleciona (quando o cursor arrasta), troca (quando vira amarelo), pos [x,y]."""

    def __init__(self, spec):
        super().__init__(spec)
        self.txt = spec["texto"]
        self.tam = int(spec.get("tam", 84))
        self.cx, self.cy = pos_px(spec.get("pos"), (0.5, 0.71))
        self.t_sel = self.tempo_item(spec["seleciona"]) if spec.get("seleciona") else self.t0 + 0.4
        self.t_troca = self.tempo_item(spec["troca"]) if spec.get("troca") else self.t_sel + 0.45
        self.branco = linha_img([(p, "sans") for p in self.txt.split()], self.tam)
        self.amarelo = linha_img([(p, "serifa") for p in self.txt.split()], self.tam)

    def barra(self) -> Image.Image:
        w, h = 250, 62
        im = Image.new("RGBA", (w, h), (255, 255, 255, 245))
        d = ImageDraw.Draw(im)
        for i, (c, tipo) in enumerate((("B", "sans_bold"), ("I", "serifa"), ("U", "sans_reg"), ("Aa", "sans_reg"))):
            x = 34 + i * 60
            d.text((x, h / 2), c, font=F(tipo, 30), fill=(70, 70, 74), anchor="mm")
        d.line([(34 + 2 * 60 - 10, h / 2 + 15), (34 + 2 * 60 + 10, h / 2 + 15)], fill=(70, 70, 74), width=2)
        return escala(com_sombra(im, 14, 0.25, 8, 4), 1.35)

    def desenha_frente(self, cv, t, cam):
        a = min(1.0, k_in(t, self.t0, 0.12) * 1.5) * self.k_saida(t)
        if a <= 0:
            return
        trocou = t >= self.t_troca
        txt = self.amarelo if trocou else self.branco
        if trocou:
            s = mola(cl((t - self.t_troca) / 0.25))
            txt = escala(txt, lerp(1.1, 1, s)) if s < 1 else txt
        tw = self.branco.width - 2 * (int(self.tam * 0.35) + 8)
        x_ini = self.cx - tw / 2
        if not trocou:
            ks = cl((t - self.t_sel) / 0.35)
            if ks > 0:
                hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(hl).rectangle((x_ini - 8, self.cy - self.tam * 0.62, x_ini - 8 + (tw + 16) * ks,
                                              self.cy + self.tam * 0.52), fill=AZUL_SEL + (140,))
                hl = opaco(hl, a)
                if hl is not None:
                    cv.alpha_composite(hl)
        cola_centro(cv, opaco(txt, a), self.cx, self.cy)
        if t < self.t_troca + 0.25:
            cola_centro(cv, opaco(self.barra(), a), self.cx - tw * 0.1, self.cy - self.tam * 1.3)
        # cursor: entra, arrasta de ponta a ponta, clica no Aa
        if self.t_sel - 0.3 < t < self.t_troca + 0.3:
            if t < self.t_sel:
                u = ease_out(cl((t - self.t_sel + 0.3) / 0.3))
                px, py = lerp(self.cx + tw * 0.7, x_ini, u), lerp(self.cy + 120, self.cy, u)
            elif t < self.t_sel + 0.35:
                u = cl((t - self.t_sel) / 0.35)
                px, py = lerp(x_ini, x_ini + tw, u), self.cy
            else:
                u = ease_in_out(cl((t - self.t_sel - 0.35) / max(0.1, self.t_troca - self.t_sel - 0.4)))
                px, py = lerp(x_ini + tw, self.cx - tw * 0.1 + 128, u), lerp(self.cy, self.cy - self.tam * 1.3, u)
            cola(cv, opaco(cursor_img(54, abs(t - self.t_troca) < 0.08), a), int(px), int(py))

    def eventos(self):
        return [(self.t0, "pop"), (self.t_sel, "clique"), (self.t_troca, "clique")]

    def itens_tempos(self):
        return [("seleciona", self.t_sel), ("troca", self.t_troca)]


# ---------------------------------------------------------------- card que gira opções e para (28,6-30,4 s)
PALETAS = [["#FFC700", "#FFE27A", "#F2EDE4", "#C9A27A", "#1B1B1B"], ["#E86A92", "#F6B5C7", "#F7EFE9", "#9C6B5A", "#2B2B2B"],
           ["#5B8DEF", "#A9C4F7", "#EEF2F8", "#7C8A9E", "#1C2230"], ["#6FAF7B", "#C7E3C1", "#F3F1E8", "#8C7A5B", "#222222"],
           ["#E3803F", "#F5C38E", "#FAF1E6", "#8E5B3E", "#2A1F1A"]]


class CardDoc(Elemento):
    """Card branco que entra pela lateral e mostra um documento; a cada item ele embaralha opções por ~0,25 s
    (troca a cada 0,06 s, como as fontes da referência) e para no item falado. itens: [{titulo, arquivo, em}],
    rotulo (itálico no topo), pilula (embaixo)."""
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.lado = spec.get("lado", "esq")
        self.w, self.h = int(spec.get("larg", 340)), int(spec.get("alt", 470))
        self.cy = float(spec.get("y", 0.33)) * H
        self.itens = [{"titulo": it["titulo"], "arq": it["arquivo"], "t": self.tempo_item(it["em"]) - ANTECIPA}
                      for it in spec["itens"]]
        self.rotulo = spec.get("rotulo", "feito pra você")
        self.pilula = spec.get("pilula", "gerado da reunião")

    @functools.lru_cache(maxsize=64)
    def card(self, idx: int, paleta: int, selecionado: bool) -> Image.Image:
        w, h = self.w, self.h
        it = self.itens[idx]
        im = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        d = ImageDraw.Draw(im)
        rot, base = palavra(self.rotulo, "serifa", 40, (60, 60, 64), 0.0)
        im.alpha_composite(rot, (16 - int(40 * 0.35) - 8 + 10, 18 - (base - 40)))
        bx, by, bw, bh = 22, 74, w - 44, int(h * 0.44)
        im.alpha_composite(arredonda(cobre(imagem(it["arq"]), bw, bh), 12), (bx, by))
        if selecionado:
            d.rectangle((bx - 4, by - 4, bx + bw + 4, by + bh + 4), outline=(90, 160, 240), width=3)
            for cx, cy in ((bx - 4, by - 4), (bx + bw + 4, by - 4), (bx - 4, by + bh + 4), (bx + bw + 4, by + bh + 4)):
                d.rectangle((cx - 6, cy - 6, cx + 6, cy + 6), fill=BRANCO, outline=(90, 160, 240), width=2)
        ft = F("sans_semi", 40)
        while ft.getlength(it["titulo"]) > w - 44 and ft.size > 20:
            ft = F("sans_semi", ft.size - 2)
        yt = by + bh + 18
        d.text((22, yt), it["titulo"], font=ft, fill=TINTA)
        cores = PALETAS[paleta % len(PALETAS)]
        yc = yt + ft.size + 34
        passo = (w - 44 - 36) / 4
        for j, c in enumerate(cores):
            cx = 40 + j * passo
            d.ellipse((cx - 18, yc - 18, cx + 18, yc + 18), fill=hexa(c))
        f = F("sans_semi", 22)
        pw = int(f.getlength(self.pilula) + 54)
        d.rounded_rectangle((22, h - 52, 22 + pw, h - 18), radius=17, fill=(250, 238, 190))
        d.ellipse((34, h - 41, 46, h - 29), fill=AMARELO)
        d.text((54, h - 35), self.pilula, font=f, fill=TINTA, anchor="lm")
        return com_sombra(im, int(w * 0.07), 0.35, 18, 10)

    def estado(self, t: float) -> tuple[int, int, bool]:
        atual = 0
        for i, it in enumerate(self.itens):
            if t >= it["t"]:
                atual = i
        tl = self.itens[atual]["t"]
        if 0 <= t - tl < 0.26 and (atual > 0 or tl > self.t0 + 0.05):
            n = int((t - tl) / 0.06)
            return (atual + n + 1) % len(self.itens), n + 1, True
        return atual, atual, t - tl < 0.6

    def desenha_frente(self, cv, t, cam):
        idx, pal, sel = self.estado(max(t, self.itens[0]["t"]))
        im = gira(self.card(idx, pal, sel), 4 if self.lado == "esq" else -4)
        k = ease_out(k_in(t, self.t0, 0.22))
        ks = 1 - self.k_saida(t)
        dentro = 20 - 44 + im.width / 2 if self.lado == "esq" else W - 20 + 44 - im.width / 2
        fora = -im.width / 2 if self.lado == "esq" else W + im.width / 2
        cx = lerp(fora, dentro, k) if ks <= 0 else lerp(dentro, fora, ease_out(ks))
        cola_centro(cv, im, cx, self.cy)

    def eventos(self):
        ev = [(self.t0, "whoosh")]
        for it in self.itens[1:]:
            ev += [(it["t"] + j * 0.06, "tique") for j in range(4)]
        return ev

    def itens_tempos(self):
        return [(it["titulo"], it["t"]) for it in self.itens]


# ---------------------------------------------------------------- timeline de editor (34,4-37,1 s)
class Timeline(Elemento):
    """Janela escura de editor sobe por baixo; as faixas enchem da esquerda pra direita (clipes em
    azul-petróleo, legendas em laranja) e a agulha corre. rotulos: [{texto, em, cor}] aparecem na faixa de
    cima onde a agulha está. titulo: nome do projeto na barra."""
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.w, self.h = int(spec.get("larg", 900)), int(spec.get("alt", 290))
        self.cx, self.cy = pos_px(spec.get("pos"), (0.5, 0.705))
        self.titulo = spec.get("titulo", "projeto · v1")
        self.enche = float(spec.get("enche", 1.1))
        self.rotulos = [{"txt": r["texto"], "t": self.tempo_item(r["em"]) - ANTECIPA, "cor": hexa(r.get("cor", "#E8784A"))}
                        for r in spec.get("rotulos", [])]

    def agulha(self, t: float) -> float:
        return cl((t - self.t0 - 0.1) / max(0.5, self.t1 - self.t0 - 0.1))

    def desenha_frente(self, cv, t, cam):
        w, h = self.w, self.h
        im = Image.new("RGBA", (w, h), (30, 30, 34, 250))
        d = ImageDraw.Draw(im)
        for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            d.ellipse((22 + i * 30, 18, 40 + i * 30, 36), fill=c)
        d.text((w / 2, 27), self.titulo, font=F("sans_reg", 22), fill=(170, 170, 176), anchor="mm")
        x0, x1 = 70, w - 30
        d.line([(x0, 58), (x1, 58)], fill=(70, 70, 76), width=1)
        for i in range(5):
            x = x0 + (x1 - x0) * i / 4
            d.line([(x, 52), (x, 64)], fill=(90, 90, 96), width=1)
            d.text((x + 6, 58), f"00:{i * 10:02d}", font=F("sans_reg", 15), fill=(120, 120, 126), anchor="lm")
        for i, nome in enumerate(("T", "L", "V")):
            d.text((34, 108 + i * 62), nome, font=F("sans_semi", 20), fill=(110, 110, 116), anchor="mm")
        kf = ease_out(cl((t - self.t0 - 0.05) / self.enche))
        kl = ease_out(cl((t - self.t0 - 0.3) / self.enche))
        # faixa V: clipes
        xv = x0 + (x1 - x0) * kf
        n = 14
        for i in range(n):
            a, b = x0 + (x1 - x0) * i / n + 2, x0 + (x1 - x0) * (i + 1) / n - 2
            if a >= xv:
                break
            fim = min(b, xv)
            if fim - a < 14:   # clipe ainda nascendo: estreito demais pro canto arredondado
                break
            d.rounded_rectangle((a, 210, fim, 252), radius=6, fill=PETROLEO)
            d.rectangle((a + 4, 216, fim - 4, 222), fill=(80, 190, 190))
        # faixa L: legendas (blocos laranja curtos)
        xl = x0 + (x1 - x0) * kl
        x = x0
        i = 0
        while x < xl:
            larg = 22 + (i * 37 % 19)
            if min(x + larg, xl) - x >= 10:
                d.rounded_rectangle((x, 150, min(x + larg, xl), 178), radius=4, fill=LARANJA)
            x += larg + 5
            i += 1
        # faixa T: rótulos que aparecem onde a agulha está (sem encavalar no anterior)
        x_livre = x0
        for r in self.rotulos:
            if t < r["t"]:
                continue
            kr = mola(cl((t - r["t"]) / 0.22))
            xr = x0 + (x1 - x0) * self.agulha(r["t"])
            f = F("sans_bold", 26)
            tw = f.getlength(r["txt"])
            pill = Image.new("RGBA", (int(tw + 30), 42), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, 41), radius=8, fill=r["cor"])
            ImageDraw.Draw(pill).text((pill.width / 2, 21), r["txt"], font=f, fill=BRANCO, anchor="mm")
            xp = cl(max(xr - pill.width / 2, x_livre), x0, x1 - pill.width)
            x_livre = xp + pill.width + 8
            pill = escala(pill, max(0.3, kr))
            im.alpha_composite(pill, (int(xp + (int(tw + 30) - pill.width) / 2), int(108 - pill.height / 2)))
        xa = x0 + (x1 - x0) * self.agulha(t)
        d.line([(xa, 64), (xa, h - 18)], fill=(240, 240, 240), width=3)
        d.ellipse((xa - 8, 54, xa + 8, 70), fill=(240, 240, 240))
        card = com_sombra(im, 24, 0.45, 20, 10)
        k = ease_out(k_in(t, self.t0, 0.2))
        ks = 1 - self.k_saida(t)
        dy = 160 * (1 - k) + 200 * ease_out(ks)
        cola_centro(cv, opaco(card, min(1.0, k * 1.4) * (1 - ks)), self.cx, self.cy + dy)

    def eventos(self):
        return [(self.t0, "whoosh")] + [(r["t"], "pop") for r in self.rotulos]

    def itens_tempos(self):
        return [(r["txt"], r["t"]) for r in self.rotulos]


# ---------------------------------------------------------------- tira de B-roll atrás da cabeça (14,6-16,2 s)
class Tira(Elemento):
    """Fila horizontal de cards de borda a borda, na altura da cabeça, ATRÁS da pessoa, deslizando devagar pra
    esquerda. arquivos: lista; y: centro (fração); alt: altura do card."""
    atras = True
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.alt = int(spec.get("alt", 300))
        self.y = float(spec.get("y", 0.15)) * H
        self.cards = [arredonda(cobre(imagem(a), int(self.alt * 0.74), self.alt), 18) for a in spec["arquivos"]]
        self.vel = float(spec.get("vel", 70))

    def desenha_atras(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, 0.25))
        a = min(1.0, k * 1.3) * self.k_saida(t)
        if a <= 0:
            return
        gap = 16
        passo = self.cards[0].width + gap
        total = passo * len(self.cards)
        desl = (t - self.t0) * self.vel + 260 * (1 - k)
        x = -passo * 0.4 - desl % total + 260 * (1 - k)
        i = 0
        while x < W + passo:
            cola_centro(cv, opaco(self.cards[i % len(self.cards)], a), x + passo / 2, self.y)
            x += passo
            i += 1


# ---------------------------------------------------------------- explosão de miniaturas (12,1-13,0 s)
class Explosao(Elemento):
    """~16 miniaturas saem do corpo da pessoa e se espalham em volta (fora do rosto), em cascata de 0,035 s; umas
    ficam atrás da pessoa, outras na frente. Saem encolhendo de volta pro centro. arquivos: lista (repete)."""
    atras = True
    som_entrada = "pop"

    def __init__(self, spec):
        super().__init__(spec)
        n = int(spec.get("n", 16))
        rng = np.random.default_rng(int(spec.get("semente", 7)))
        arqs = spec["arquivos"]
        self.cards = []
        g = MED[grupo(self.t0)]
        fx0, fy0, fw, fh = g["rosto"]
        rosto = (fx0 - 40, g["topo"] - 20, fx0 + fw + 40, fy0 + fh + 30)
        tent = 0
        while len(self.cards) < n and tent < 4000:
            tent += 1
            x, y = rng.uniform(70, W - 70), rng.uniform(LAY["topo"] + 90, H * LAY["base"] - 110)
            if rosto[0] < x < rosto[2] and rosto[1] < y < rosto[3]:
                continue
            if any(math.hypot(x - c["x"], y - c["y"]) < 175 for c in self.cards):
                continue
            larg = int(rng.uniform(120, 165))
            self.cards.append({"x": x, "y": y, "im": gira(card_img(arqs[len(self.cards) % len(arqs)], larg),
                                                        float(rng.uniform(-9, 9))),
                               "atras": bool(rng.random() < 0.45), "atraso": len(self.cards) * 0.035})
        self.origem = (W / 2, (fy0 + fh) + 260)

    def _desenha(self, cv, t, atras):
        ks = cl((t - self.t1) / self.saida_d())
        for c in self.cards:
            if c["atras"] != atras:
                continue
            tc = t - self.t0 - c["atraso"]
            if tc < 0:
                continue
            k = ease_out(cl(tc / 0.22))
            u = k * (1 - ease_out(ks))
            x, y = lerp(self.origem[0], c["x"], u), lerp(self.origem[1], c["y"], u)
            cola_centro(cv, opaco(escala(c["im"], lerp(0.3, 1, u)), min(1.0, k * 2) * (1 - ks)), x, y)

    def desenha_atras(self, cv, t, cam):
        self._desenha(cv, t, True)

    def desenha_frente(self, cv, t, cam):
        self._desenha(cv, t, False)

    def saida_d(self):
        return 0.2

    def eventos(self):
        return [(self.t0 + c["atraso"], "pop") for c in self.cards[::3]]


# ---------------------------------------------------------------- grade de perfil (23,6-26,5 s)
class Grade(Elemento):
    """A tela vira a grade de Reels do criador (3 colunas, com views), rolando devagar, com a pessoa recortada na frente.
    Entra por fusão rápida com leve giro. arquivos: lista; views: lista de textos (opcional)."""
    atras = True
    som_entrada = "whoosh"

    def __init__(self, spec):
        super().__init__(spec)
        self.arqs = spec["arquivos"]
        self.views = spec.get("views", [])
        cw = W // 3
        ch = int(cw * 16 / 9 * 0.75)
        linhas = math.ceil(H / ch) + 3
        self.img = Image.new("RGBA", (W, ch * linhas), (12, 12, 12, 255))
        for i in range(3 * linhas):
            c = cobre(imagem(self.arqs[i % len(self.arqs)]), cw - 3, ch - 3)
            if self.views:
                ImageDraw.Draw(c).text((14, ch - 34), "▷ " + self.views[i % len(self.views)], font=F("sans_semi", 26),
                                       fill=BRANCO, stroke_width=2, stroke_fill=(0, 0, 0))
            self.img.alpha_composite(c, ((i % 3) * cw, (i // 3) * ch))
        self.ch = ch

    def desenha_atras(self, cv, t, cam):
        k = ease_out(k_in(t, self.t0, 0.2))
        a = k * self.k_saida(t)
        if a <= 0:
            return
        y = int((t - self.t0) * 90) % self.ch
        g = self.img.crop((0, y, W, y + H))
        g = gira(g, 2.5 * (1 - k)) if k < 1 else g
        cola_centro(cv, opaco(g, a), W / 2, H / 2)


# ---------------------------------------------------------------- botão "Saiba mais" com toque (CTA)
class Botao(Elemento):
    """Barra de CTA no estilo do Instagram; o cursor chega e toca (aperta, onda, fica amarela).
    texto, toque (quando toca), pos [x,y]."""

    def __init__(self, spec):
        super().__init__(spec)
        self.txt = spec.get("texto", "Saiba mais")
        self.cx, self.cy = pos_px(spec.get("pos"), (0.5, 0.72))
        self.t_toque = self.tempo_item(spec["toque"]) if spec.get("toque") else self.t0 + 0.4
        self.w, self.h = int(spec.get("larg", 760)), 100

    def desenha_frente(self, cv, t, cam):
        a = min(1.0, k_in(t, self.t0, 0.14) * 1.4) * self.k_saida(t)
        if a <= 0:
            return
        dt = t - self.t_toque
        aceso = dt >= 0
        im = Image.new("RGBA", (self.w, self.h), (AMARELO if aceso else (255, 255, 255)) + (250,))
        d = ImageDraw.Draw(im)
        d.text((40, self.h / 2), self.txt, font=F("sans_semi", 46), fill=TINTA, anchor="lm")
        d.line([(self.w - 56, self.h / 2 - 14), (self.w - 42, self.h / 2), (self.w - 56, self.h / 2 + 14)], fill=TINTA, width=5)
        if 0 <= dt < 0.45:
            r = 30 + 380 * ease_out(dt / 0.45)
            onda = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(onda).ellipse((self.w * 0.62 - r, self.h / 2 - r, self.w * 0.62 + r, self.h / 2 + r),
                                         fill=(255, 255, 255, int(120 * (1 - dt / 0.45))))
            im.alpha_composite(onda)
        card = com_sombra(im, 24, 0.35, 16, 8)
        s = 0.96 if 0 <= dt < 0.1 else 1.0
        k = ease_out(k_in(t, self.t0, 0.16))
        cola_centro(cv, opaco(escala(card, s * lerp(0.9, 1, k)), a), self.cx, self.cy + 40 * (1 - k))
        if self.t_toque - 0.35 < t < self.t_toque + 0.4:
            u = ease_out(cl((t - self.t_toque + 0.35) / 0.35))
            px = lerp(self.cx + 380, self.cx + self.w * 0.12, u)
            py = lerp(self.cy + 260, self.cy, u)
            cola(cv, opaco(cursor_img(58, 0 <= dt < 0.1), a), int(px), int(py))

    def eventos(self):
        return [(self.t0, "pop"), (self.t_toque, "clique")]

    def itens_tempos(self):
        return [("toque", self.t_toque)]


TIPOS = {"cards": Cards, "vidro": Vidro, "mao": Mao, "finder": Finder, "card_escuro": CardEscuro, "editor": Editor,
         "card_doc": CardDoc, "timeline": Timeline, "tira": Tira, "explosao": Explosao, "grade": Grade, "botao": Botao}


def _cria(spec: dict) -> Elemento:
    if spec["tipo"] not in TIPOS:
        sys.exit(f"tipo desconhecido: {spec['tipo']} (tipos: {', '.join(TIPOS)})")
    return TIPOS[spec["tipo"]](spec)


ELEMENTOS = sorted([_cria(s) for s in MAPA.get("elementos", [])], key=lambda e: e.t0)


# ================================================================ TÍTULO EMPILHADO (2,3-4,9 s; 41,7-42,8 s)
class Titulo:
    """Bloco de linhas que se monta na fala, misturando sans branca e *serifa amarela*. Cada palavra aparece
    quando é falada (palavra que a pessoa não fala entra junto com a anterior). Linha com "atras": true fica atrás
    da cabeça (a cabeça cobre o meio, como "learn h_w to" da referência). Enquanto o título está na tela, a
    legenda some.
    spec: {em, ate, y (centro da 1ª linha da frente, fração), tam, linhas: ["texto", {txt, y, atras, tam}]}"""

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        self.tam = int(spec.get("tam", LAY["tit_tam"]))
        i0 = acha(spec["em"][0], int(spec["em"][1])) if isinstance(spec["em"], list) else 0
        ptr = i0
        self.linhas = []
        y_frente = float(spec.get("y", 0.56)) * H
        for l in spec["linhas"]:
            l = {"txt": l} if isinstance(l, str) else dict(l)
            toks = tokens(l["txt"])
            tempos = []
            ult = self.t0
            for tx, _ in toks:
                achou = None
                for j in range(ptr, min(len(WORDS), ptr + 6)):
                    if limpa(WORDS[j]["t"]) == limpa(tx):
                        achou = j
                        break
                if achou is not None:
                    ult = max(self.t0, WORDS[achou]["s"] - ANTECIPA)
                    ptr = achou + 1
                tempos.append(ult)
            tam = int(l.get("tam", self.tam))
            alt = int(tam * (LAY["leg_serifa"] if any(tp == "serifa" for _, tp in toks) else 1.0) * 1.02)
            if "y" in l:
                y = float(l["y"]) * H
            else:
                y = y_frente + alt / 2
                y_frente += alt
            self.linhas.append({"toks": toks, "tempos": tempos, "y": y, "atras": bool(l.get("atras")), "tam": tam})
        self.atras = any(l["atras"] for l in self.linhas)

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1 + 0.12

    def desenha(self, cv: Image.Image, t: float, atras: bool) -> None:
        a = 1 - cl((t - self.t1) / 0.12)
        for l in self.linhas:
            if l["atras"] != atras:
                continue
            vis = sum(1 for tt in l["tempos"] if t >= tt)
            if vis == 0:
                continue
            im = linha_img(l["toks"], l["tam"], vis)
            cola_centro(cv, opaco(im, a), W / 2, l["y"])

    def marcos(self) -> list[float]:
        return sorted(set(tt for l in self.linhas for tt in l["tempos"]))


TITULOS = sorted([Titulo(s) for s in MAPA.get("titulos", [])], key=lambda x: x.t0)


# ================================================================ MÁSCARA (a pessoa na frente)
def janelas_mascara() -> list[tuple[float, float]]:
    js = [(x.t0 - 0.05, x.t1 + 0.2) for x in TITULOS if x.atras]
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


# ================================================================ LEGENDA (uma palavra; aparte; gigante)
def _indices(specs) -> set[int]:
    return {acha(s[0], int(s[1])) for s in specs}


AMARELAS = _indices(MAPA.get("amarelas", []))
GIGANTES = _indices(MAPA.get("gigantes", []))
APARTES = [(T(a["em"]), T_fim(a.get("ate"), a["em"])) for a in MAPA.get("apartes", [])]


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    out = []
    usados = set()
    for a0, a1 in APARTES:   # aparte: a frase inteira, pequena, numa linha (ou duas)
        idx = [i for i, w in enumerate(WORDS) if a0 - 0.01 <= w["s"] < a1]
        if not idx:
            continue
        usados.update(idx)
        toks = [(WORDS[i]["t"].strip(), "serifa" if i in AMARELAS else "sans") for i in idx]
        out.append({"toks": toks, "ini": WORDS[idx[0]]["s"] - 0.03, "fim": WORDS[idx[-1]]["e"] + 0.12,
                    "tam": LAY["leg_aparte"], "tipo": "aparte"})
    for i, w in enumerate(WORDS):
        if i in usados or not any(c.isalnum() for c in w["t"]):
            continue
        tipo = "gigante" if i in GIGANTES else "normal"
        estilo = "serifa" if (i in AMARELAS or i in GIGANTES) else "sans"
        tam = int(LAY["leg_tam"] * (LAY["leg_gigante"] / LAY["leg_serifa"] if tipo == "gigante" else 1))
        out.append({"toks": [(w["t"].strip(), estilo)], "ini": w["s"] - 0.03, "fim": w["e"] + 0.15, "tam": tam, "tipo": tipo})
    out.sort(key=lambda b: b["ini"])
    for k in range(len(out) - 1):   # troca seca: cada palavra fica até a próxima entrar (se o vão for curto)
        prox = out[k + 1]["ini"]
        if prox - out[k]["fim"] < 0.5 or prox < out[k]["fim"]:
            out[k]["fim"] = prox
    return out


@functools.lru_cache(maxsize=4096)
def _leg_img(toks: tuple, tam: int) -> Image.Image:
    im = linha_img(list(toks), tam)
    if im.width > W * 0.92:   # aparte comprido: quebra em duas linhas
        meio = len(toks) // 2
        a, b = linha_img(list(toks[:meio]), tam), linha_img(list(toks[meio:]), tam)
        out = Image.new("RGBA", (max(a.width, b.width), int(a.height * 0.82) + b.height), (0, 0, 0, 0))
        out.alpha_composite(a, ((out.width - a.width) // 2, 0))
        out.alpha_composite(b, ((out.width - b.width) // 2, int(a.height * 0.82)))
        return out
    return im


def legenda_y(t: float, cam: tuple) -> float:
    c = cabeca(t, cam)
    return cl(c["queixo"] + LAY["leg_queixo"], H * LAY["leg_min"], H * LAY["leg_max"])


# ================================================================ composição
def compoe(fr: Image.Image, t: float, legendas: list[dict], n: int) -> Image.Image:
    cam = camera(t)
    quadro = aplica_camera(fr, cam)
    cv = quadro.copy()
    tits = [x for x in TITULOS if x.ativo(t)]
    els = [e for e in ELEMENTOS if e.ativo(t)]
    if any(x.atras for x in tits) or any(e.atras for e in els):
        for e in els:
            e.desenha_atras(cv, t, cam)
        for x in tits:
            x.desenha(cv, t, True)
        m = mascara(n)
        if m is not None:
            pessoa = quadro.copy()
            pessoa.putalpha(aplica_camera(m, cam, Image.BILINEAR))
            cv.alpha_composite(pessoa)
    for e in els:
        e.desenha_frente(cv, t, cam)
    for x in tits:
        x.desenha(cv, t, False)
    if not tits and not any(e.esconde_legenda for e in els):
        for b in legendas:
            if b["ini"] <= t < b["fim"]:
                cola_centro(cv, _leg_img(tuple(b["toks"]), b["tam"]), W / 2, legenda_y(t, cam))
                break
    return cv


# ================================================================ áudio (voz + efeitos discretos)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome == "whoosh":
        n = int(0.3 * SR)
        esp = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= np.exp(-((np.log(f + 1) - np.log(2400)) ** 2) / 0.8)
        x = np.fft.irfft(esp, n) * _env(n, 0.55)
        return x / (np.abs(x).max() + 1e-9)
    if nome in ("clique", "tique"):   # clique de mouse: estalo curto
        d = 0.03 if nome == "clique" else 0.018
        n = int(d * SR)
        tt = np.arange(n) / SR
        x = rng.standard_normal(n) * np.exp(-tt * 380) + np.sin(2 * np.pi * 3200 * tt) * np.exp(-tt * 260) * 0.6
        return x / (np.abs(x).max() + 1e-9) * (0.9 if nome == "clique" else 0.5)
    if nome == "caneta":
        n = int(0.4 * SR)
        x = rng.standard_normal(n)
        esp = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= (f > 2500) & (f < 8000)
        x = np.fft.irfft(esp, n) * _env(n, 0.15) * (0.6 + 0.4 * np.sin(np.arange(n) / SR * 2 * np.pi * 14))
        return x / (np.abs(x).max() + 1e-9) * 0.4
    d = 0.07   # pop
    n = int(d * SR)
    tt = np.arange(n) / SR
    fr = 1200 + (600 - 1200) * tt / d
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 45) * 0.6


def eventos_som() -> list[tuple[float, str]]:
    ev = []
    for e in ELEMENTOS:
        ev += e.eventos()
    return sorted(ev)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -28) if isinstance(cfg, dict) else -28
        ultimo = {}
        for t, nome in eventos_som():
            if t - ultimo.get(nome, -9) < (0.05 if nome == "tique" else 0.1):
                continue
            ultimo[nome] = t
            ganho = {"pop": 0.7, "clique": 0.9, "tique": 0.6, "caneta": 0.8}.get(nome, 1.0)
            s = sfx(nome) * 10 ** (gdb / 20) * ganho
            i = int(max(0, t) * SR)
            pista[i:i + len(s)] += s[: len(pista) - i]
    mus = MAPA.get("musica")   # a referência tem trilha bem baixa; só com arquivo e licença de uso
    if mus:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mus.get("inicio", 0)), "-i", str(_resolve(mus["arquivo"])),
                              "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = int(TOTAL * SR)
        x = np.tile(x, n // len(x) + 1)[:n]
        x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 10 ** (mus.get("db", -32) / 20)
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
def resumo(legendas: list[dict]) -> None:
    print("linha do tempo:")
    marcos = []
    for x in TITULOS:
        print(f"  {x.t0:6.2f}-{x.t1:6.2f} título   {' / '.join(l if isinstance(l, str) else l['txt'] for l in x.spec['linhas'])}")
        marcos += x.marcos()
    for e in ELEMENTOS:
        print(f"  {e.t0:6.2f}-{e.t1:6.2f} {e.spec['tipo']:11s} {'(atrás) ' if e.atras else ''}")
        marcos.append(e.t0)
        for nome, te in e.itens_tempos():
            print(f"           · {te:6.2f} {nome}")
            marcos.append(te)
            if e.t1 - te < 0.4:
                print(f"  ATENÇÃO: '{nome}' acontece {e.t1 - te:.2f}s antes do elemento sair (mín. ~0,4 s)")
    for td, z in DEGRAUS:
        print(f"  {td:6.2f}        degrau   zoom {z:.2f}")
        marcos.append(td)
    for ta, z, d in APROX:
        print(f"  {ta:6.2f}        aproxima zoom {z:.2f} em {d:.1f}s")
        marcos.append(ta)
    marcos += [b["ini"] for b in legendas if b["tipo"] != "normal" or any(tp == "serifa" for _, tp in b["toks"])]
    marcos = sorted(set([0.0] + marcos + list(OFF[1:-1]) + [TOTAL]))
    com_grafico = sum(min(TOTAL, e.t1) - e.t0 for e in ELEMENTOS) + sum(x.t1 - x.t0 for x in TITULOS)
    print(f"  evento visual a cada {TOTAL / max(1, len(marcos) - 1):.1f}s (referência: ~1,5 s); "
          f"objeto/título na tela ~{100 * com_grafico / TOTAL:.0f}% do tempo (referência: ~51%)")
    for a, b in zip(marcos, marcos[1:]):
        if b - a > 3.0:
            print(f"  ATENÇÃO: {b - a:.1f}s sem nada novo ({a:.2f}-{b:.2f}): degrau, palavra amarela ou objeto")
    js = janelas_mascara()
    print(f"  recorte da pessoa em {sum(b - a for a, b in js):.1f}s de {TOTAL:.1f}s")


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_SB = {"cards": "Cards de vidro", "vidro": "Tela de vidro com a imagem", "mao": "Escrita à mão com seta",
            "finder": "Pasta do Finder com cursor arrastando", "card_escuro": "Card escuro com texto e sublinhado",
            "editor": "Texto selecionado que troca pra serifa", "card_doc": "Card de documento que embaralha",
            "timeline": "Timeline de editor se enchendo", "tira": "Tira de B-roll atrás da cabeça",
            "explosao": "Explosão de miniaturas em volta da pessoa", "grade": "Grade de Reels atrás da cabeça",
            "botao": "Botão com toque"}


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1: min(t, t1 - 0.05)
    ms, avisos = [], []
    for x in TITULOS:
        linhas = [l if isinstance(l, str) else l["txt"] for l in x.spec["linhas"]]
        atras = any(isinstance(l, dict) and l.get("atras") for l in x.spec["linhas"])
        ms.append({"t0": x.t0, "t1": x.t1, "quadro": cap(max(x.marcos() + [x.t0]) + 0.35, x.t1),
                   "tipo": "Título empilhado" + (" (1ª linha atrás da cabeça)" if atras else ""),
                   "desc": " / ".join(SB.limpa_marcacao(l) for l in linhas)})
    for e in ELEMENTOS:
        tempos = [te for _, te in e.itens_tempos()]
        nome = NOMES_SB.get(e.spec["tipo"], e.spec["tipo"])
        desc = SB.textos_do_spec(e.spec) or ("“" + str(e.spec.get("texto", "Saiba mais")) + "”, com toque do dedo"
                                             if e.spec["tipo"] == "botao" else "—")
        m = {"t0": e.t0, "t1": e.t1, "quadro": cap(max([e.t0 + 0.8] + [te + 0.35 for te in tempos]), e.t1),
             "tipo": nome, "desc": desc}
        curtos = [n for n, te in e.itens_tempos() if e.t1 - te < 0.4]
        if curtos:
            m["aviso"] = f"{', '.join(curtos)} acontece menos de 0,4 s antes de sair"
        ms.append(m)
    for b in legendas:
        if b["tipo"] in ("gigante", "aparte"):
            txt = " ".join(tx for tx, _ in b["toks"])
            ms.append({"t0": b["ini"], "t1": b["fim"], "quadro": cap(b["ini"] + 0.2, b["fim"]),
                       "tipo": "Interjeição gigante" if b["tipo"] == "gigante" else "Aparte pequeno", "desc": txt})
    for td, z in DEGRAUS:
        ms.append({"t0": td, "t1": td, "quadro": td + 0.15, "tipo": "Câmera: degrau",
                   "desc": f"corte seco pra {'mais perto' if z > 1 else 'mais longe'} ({z:.2f}x)".replace(".", ",")})
    for ta, z, d in APROX:
        ms.append({"t0": ta, "t1": ta + d, "quadro": ta + d, "tipo": "Câmera: aproxima",
                   "desc": f"aproxima devagar até {z:.2f}x em {d:.1f} s".replace(".", ",")})
    marcos = []
    for x in TITULOS:
        marcos += x.marcos()
    for e in ELEMENTOS:
        marcos += [e.t0] + [te for _, te in e.itens_tempos()]
    marcos += [td for td, _ in DEGRAUS] + [ta for ta, _, _ in APROX]
    marcos += [b["ini"] for b in legendas if b["tipo"] != "normal" or any(tp == "serifa" for _, tp in b["toks"])]
    marcos = sorted(set([0.0, TOTAL] + marcos + list(OFF[1:-1])))
    for a, b in zip(marcos, marcos[1:]):
        if b - a > 3.0:
            avisos.append(f"{b - a:.1f} s sem nada novo ({a:.1f}–{b:.1f} s): degrau, palavra amarela ou objeto"
                          .replace(".", ","))
    com_grafico = sum(min(TOTAL, e.t1) - e.t0 for e in ELEMENTOS) + sum(x.t1 - x.t0 for x in TITULOS)
    pct = 100 * com_grafico / TOTAL
    if abs(pct - 51) > 15:
        avisos.append(f"objeto/título na tela {pct:.0f}% do tempo (referência ~51%)")
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

    out = SB.gerar(EDIT, "Jessi", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if janelas_mascara() and not (EDIT / "masks" / "out").exists():
        sys.exit("tem coisa atrás da pessoa (título atrás, tira, explosão, grade): rode mascaras.py antes")
    legendas = monta_legendas()
    resumo(legendas)
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
    prenorm = EDIT / f"{modo}_jessi.prenorm.mp4"
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
    out = EDIT / f"{modo}_jessi.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
