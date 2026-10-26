"""compor.py — monta o Reel no estilo "iPhone" quadro a quadro, a partir do mapa.json.

Estilo medido na referência (referencia/referencias-estilo.md): a plataforma citada acende em NEON atrás
da cabeça (a pessoa recortada na frente), ícones neon sobem e se encaixam no peito, título só de contorno
com brilho e miolo transparente marca o passo, e a demonstração aparece dentro de um iPhone 3D que sobe
do pé da tela, cresce devagar (aproxima) e balança, com o fundo desfocado e escuro e o toque marcado na
tela. Linha neon de crescimento no peito, clarão laranja nas trocas de seção, cartão de perfil no CTA.
Legenda pequena, condensada, caixa alta, 1-2 palavras, sempre no mesmo lugar.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard                # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_iphone.mp4 | final_iphone.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov | base_final.mov, masks/out (mascaras.py), imagens em <edit>/assets/ (logos.py).
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # nome, @, cor de destaque e foto do criador (perfil.json)
FOTO_PERFIL = str(perfil.foto())   # foto do cartão de perfil (cai na foto genérica do pack)

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


def acha(texto: str, grupo_: int) -> int:
    alvo = limpa(texto)
    for i, w in enumerate(WORDS):
        if w["seg"] == grupo_ and limpa(w["t"]) == alvo:
            return i
    fala = " ".join(w["t"] for w in WORDS if w["seg"] == grupo_)
    sys.exit(f'palavra "{texto}" não está na tomada {grupo_}. Fala da tomada: {fala}')


ANTECIPA = float(MAPA.get("antecipa", 0.12))


def T(spec) -> float:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] (ANTECIPA s antes da palavra) |
    [palavra, tomada, atraso] (atraso explícito em relação ao início da palavra)."""
    if isinstance(spec, (int, float)):
        return float(spec)
    w = WORDS[acha(spec[0], int(spec[1]))]
    d = float(spec[2]) if len(spec) > 2 else -ANTECIPA
    return max(0.0, w["s"] + d)


def T_na(spec) -> float:
    """Tempo em que um ITEM acontece: na palavra (sem antecipar)."""
    if isinstance(spec, list) and len(spec) == 2:
        return T(spec) + ANTECIPA
    return T(spec)


def grupo(t: float) -> int:
    return max(0, min(_NG - 1, bisect.bisect_right(OFF, t) - 1))


def T_fim(spec_ate, spec_em) -> float:
    """Fim de um elemento: `ate` explícito, senão o fim da tomada em que ele começa."""
    if spec_ate is not None:
        return T(spec_ate)
    return OFF[grupo(T(spec_em)) + 1]


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    x = cl(x)
    return 1 - (1 - x) ** 3


def ease_in(x: float) -> float:
    return cl(x) ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def mola(x: float) -> float:
    x = cl(x)
    c1 = 1.7
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rosto(t: float) -> dict:
    """Medidas (topo da cabeça, caixa do rosto) da tomada em t."""
    return MED[grupo(t)]


# ---------------------------------------------------------------- cores e fontes
COR = hexa(MAPA.get("cor", PERFIL["cor_destaque"]))       # legenda (cor de destaque do perfil)
COR_TITULO = MAPA.get("cor_titulo", MAPA.get("cor", PERFIL["cor_destaque"]))   # título neon de contorno
# cores neon das marcas mais citadas (degradê do contorno); o mapa pode trocar com "cores"
CORES_MARCA = {
    "instagram": ["#8A3FFC", "#E1306C", "#FF8A3D"], "claude": ["#D97757", "#FFB38A"],
    "anthropic": ["#D97757", "#FFB38A"], "chatgpt": ["#19C37D", "#8CF5D2"], "openai": ["#19C37D", "#8CF5D2"],
    "whatsapp": ["#25D366", "#A6FFC9"], "youtube": ["#FF1744", "#FF8A80"], "gemini": ["#4285F4", "#A67CF0", "#E5677A"],
    "tiktok": ["#25F4EE", "#FE2C55"], "notion": ["#F2F2F2", "#9AA0A6"], "linkedin": ["#0A66C2", "#6FB7FF"],
    "canva": ["#00C4CC", "#7D2AE8"], "hotmart": ["#F04E23", "#FF9B6B"], "gmail": ["#EA4335", "#FBBC04"],
}
NEON_ICONES = ["#FF3EA5", "#2BFFC6", "#3D8BFF", "#FFC700", "#B266FF"]   # rosa, verde-água, azul (referência)

_DIN = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
_AVC = "/System/Library/Fonts/Avenir Next Condensed.ttc"
_SF = "/System/Library/Fonts/SFNS.ttf"


@functools.lru_cache(maxsize=64)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    if tipo == "legenda":
        return ImageFont.truetype(_DIN, size)
    if tipo == "titulo":
        return ImageFont.truetype(_AVC, size, index=9)        # Heavy Italic (o "STEP 1" da referência)
    if tipo == "sf_bold":
        f = ImageFont.truetype(_SF, size)
        try:
            f.set_variation_by_name("Semibold")
        except Exception:  # noqa: BLE001
            pass
        return f
    return ImageFont.truetype(_SF, size)


# ---------------------------------------------------------------- utilidades de imagem
def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    if p.is_absolute() and p.exists():
        return p
    for cand in (EDIT / "assets" / arq, EDIT / "assets" / f"{arq}.png", EDIT / "assets" / f"{arq}.jpg",
                 EDIT / arq, PASTA / arq, SKILL / "assets" / arq, SKILL / "assets" / f"{arq}.png"):
        if cand.exists():
            return cand.resolve()
    sys.exit(f"não achei o arquivo {arq} (procurei em assets/ e na pasta do vídeo)")


def e_video(arq: str) -> bool:
    return Path(arq).suffix.lower() in (".mov", ".mp4", ".m4v", ".webm")


@functools.lru_cache(maxsize=64)
def imagem(arq: str) -> Image.Image:
    return Image.open(_resolve(arq)).convert("RGBA")


def blur_l(a: np.ndarray, r: float) -> np.ndarray:
    """Desfoque gaussiano de uma máscara 0..1 (rápido: desfoca em resolução menor quando o raio é grande)."""
    h, w = a.shape
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")
    if r > 12:
        f = 4
        im = im.resize((max(1, w // f), max(1, h // f)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(r / f))
        im = im.resize((w, h), Image.BILINEAR)
    else:
        im = im.filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, np.float32) / 255


def gradiente(w: int, h: int, cores: list) -> np.ndarray:
    """Degradê diagonal (canto de cima à esquerda → canto de baixo à direita) passando pelas cores."""
    cs = np.array([hexa(c) for c in cores], np.float32)
    if len(cs) == 1:
        return np.broadcast_to(cs[0], (h, w, 3)).copy()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = xx / max(1, w) * 0.55 + yy / max(1, h) * 0.45
    u = (u - u.min()) / max(1e-6, u.max() - u.min())
    pos = u * (len(cs) - 1)
    i = np.clip(pos.astype(int), 0, len(cs) - 2)
    f = (pos - i)[..., None]
    return cs[i] * (1 - f) + cs[i + 1] * f


def neon(alfa: np.ndarray, cores: list, raio: float, nucleo_branco: float = 0.55, tinta: np.ndarray | None = None,
         forca: float = 1.0) -> Image.Image:
    """Tubo de neon: núcleo quase branco onde `alfa` = 1, halo curto e halo largo na cor (degradê)."""
    h, w = alfa.shape
    g = gradiente(w, h, cores)
    h1 = blur_l(alfa, raio) * 1.0 * forca
    h2 = blur_l(alfa, raio * 3.2) * 0.85 * forca
    nucleo = g * (1 - nucleo_branco) + 255 * nucleo_branco
    P = nucleo * alfa[..., None] + g * (h1 + h2)[..., None]
    A = alfa + h1 + h2
    if tinta is not None:
        P += g * tinta[..., None]
        A = A + tinta
    rgb = np.where(A[..., None] > 1e-4, P / np.maximum(A, 1e-4)[..., None], 0)
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(A, 0, 1) * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def morfo(a: np.ndarray, tam: int, dilata: bool) -> np.ndarray:
    tam = max(3, int(tam) | 1)
    im = Image.fromarray((a * 255).astype(np.uint8), "L")
    im = im.filter(ImageFilter.MaxFilter(tam) if dilata else ImageFilter.MinFilter(tam))
    return np.asarray(im, np.float32) / 255


def opaco(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def cola(dest: Image.Image, im: Image.Image | None, cx: float, cy: float) -> None:
    """alpha_composite centrado em (cx, cy), aceitando imagem que sai pelas bordas."""
    if im is None:
        return
    x, y = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def escala(im: Image.Image, s: float) -> Image.Image:
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)


def ret_arred(w: int, h: int, r: int, cor) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=cor)
    return im


# ---------------------------------------------------------------- base e máscaras
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw).convert("RGBA")


_MASC = {"n": None, "im": None}


def mascara(n: int) -> Image.Image | None:
    if _MASC["n"] != n:
        p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
        _MASC["n"], _MASC["im"] = n, (Image.open(p).convert("L") if p.exists() else None)
    return _MASC["im"]


ZOOMS = {int(k): (v if isinstance(v, list) else [v, v]) for k, v in MAPA.get("zooms", {}).items()}


def zoom_de(t: float) -> float:
    g = grupo(t)
    if g not in ZOOMS:
        return 1.0
    a, b = ZOOMS[g]
    return lerp(a, b, ease_in_out((t - OFF[g]) / max(0.1, OFF[g + 1] - OFF[g])))


def aplica_zoom(im: Image.Image, t: float, z: float) -> Image.Image:
    if z <= 1.001:
        return im
    r = rosto(t)["rosto"]
    cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
    w, h = W / z, H / z
    x0 = cl(cx - w / 2, 0, W - w)
    y0 = cl(cy - h / 2, 0, H - h)
    return im.transform((W, H), Image.EXTENT, (x0, y0, x0 + w, y0 + h), Image.BICUBIC)


# ================================================================ elementos
class Elemento:
    t0 = 0.0
    t1 = 0.0
    camada = "frente"          # "atras" (atrás da pessoa, precisa de máscara) | "tela" (iPhone) | "frente"

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def eventos(self) -> list[tuple[float, str]]:
        return []

    def nome(self) -> str:
        return type(self).__name__.lower()

    def fecha(self) -> None:
        pass


def _cores_logo(arq: str, cores) -> list:
    if cores:
        return list(cores)
    nome = limpa(Path(arq).stem)
    for k, v in CORES_MARCA.items():
        if k in nome:
            return v
    return [MAPA.get("cor", PERFIL["cor_destaque"]), "#FFFFFF"]


@functools.lru_cache(maxsize=16)
def logo_neon(arq: str, lado: int, cores: tuple, modo: str) -> Image.Image:
    """Logo oficial virado neon: contorno (padrão) ou o desenho cheio, com tinta da cor por dentro."""
    im = imagem(arq)
    k = lado / max(im.width, im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    m = int(lado * 0.32)
    a = np.zeros((im.height + 2 * m, im.width + 2 * m), np.float32)
    a[m:m + im.height, m:m + im.width] = np.asarray(im.getchannel("A"), np.float32) / 255
    a = (a > 0.5).astype(np.float32)
    traco = max(5, lado * 0.017)
    if modo == "cheio":
        linha = a
        tinta = None
    else:
        linha = np.clip(morfo(a, traco * 0.6, True) - morfo(a, traco * 0.6, False), 0, 1)
        tinta = blur_l(a, lado * 0.01) * 0.2
    linha = blur_l(linha, 1.2)
    return neon(linha, list(cores), raio=max(6, lado * 0.022), nucleo_branco=0.6, tinta=tinta)


def acende(d: float, dur_on: float = 0.42) -> float:
    """Neon ligando: pisca fraco/forte até firmar (medido na referência: 0,3-0,5 s)."""
    pts = [(0.0, 0.0), (0.05, 0.75), (0.10, 0.12), (0.17, 0.95), (0.23, 0.35), (0.32, 1.0)]
    d = d * 0.32 / dur_on
    if d >= pts[-1][0]:
        return 1.0
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if a <= d < b:
            return lerp(va, vb, (d - a) / (b - a))
    return 0.0


class Glow(Elemento):
    """Logo da plataforma em neon ATRÁS da cabeça (a pessoa recortada na frente). Vários logos = troca com
    piscada na palavra de cada um ("itens": [{"logo", "em", "cores"}])."""
    camada = "atras"

    def __init__(self, s: dict):
        self.s = s
        itens = s.get("itens") or [{"logo": s["logo"], "em": s["em"], "cores": s.get("cores")}]
        self.itens = [{"logo": it["logo"], "t": T(it.get("em", s["em"])),
                       "cores": tuple(_cores_logo(it["logo"], it.get("cores") or s.get("cores")))} for it in itens]
        self.t0 = self.itens[0]["t"]
        self.t1 = T_fim(s.get("ate"), s["em"])
        r = rosto(self.t0)
        self.lado = int(W * float(s.get("tamanho", 0.70)))
        fx, fy, fw, fh = r["rosto"]
        self.cx = float(s.get("x", fx + fw / 2))
        self.cy = float(s.get("y", (r["topo"] + fy + fh) / 2 - 0.03 * H))
        self.modo = s.get("modo", "contorno")

    def item(self, t: float) -> tuple[int, dict]:
        k = 0
        for i, it in enumerate(self.itens):
            if t >= it["t"]:
                k = i
        return k, self.itens[k]

    def desenha(self, cv: Image.Image, t: float) -> None:
        k, it = self.item(t)
        a = acende(t - it["t"])
        if k > 0 and t - it["t"] < 0.12:          # o anterior apaga antes do próximo acender
            it = self.itens[k - 1]
            a = 1 - (t - self.itens[k]["t"]) / 0.12
        if self.t1 - t < 0.2:
            a *= (self.t1 - t) / 0.2
        a *= 1 + 0.05 * math.sin(2 * math.pi * 1.3 * (t - self.t0))
        im = logo_neon(it["logo"], self.lado, it["cores"], self.modo)
        s = lerp(0.93, 1.0, ease_out((t - it["t"]) / 0.35))
        im = escala(im, s) if s < 0.999 else im
        cola(cv, opaco(im, cl(a)), self.cx, self.cy + 4 * math.sin(2 * math.pi * (t - self.t0) / 3.2))

    def eventos(self):
        return [(it["t"], "neon") for it in self.itens]

    def nome(self):
        return "glow " + " → ".join(Path(it["logo"]).stem for it in self.itens)


@functools.lru_cache(maxsize=32)
def icone_neon(arq: str, lado: int, cor: str) -> Image.Image:
    """SF Symbol (ou PNG com transparência) cheio de cor neon, borda clara e halo."""
    im = imagem(arq)
    k = lado / max(im.width, im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    m = int(lado * 0.45)
    a = np.zeros((im.height + 2 * m, im.width + 2 * m), np.float32)
    a[m:m + im.height, m:m + im.width] = np.asarray(im.getchannel("A"), np.float32) / 255
    borda = np.clip(a - morfo(a, max(3, lado * 0.035), False), 0, 1)
    base = neon(a, [cor], raio=lado * 0.05, nucleo_branco=0.18, forca=0.9)
    arr = np.asarray(base, np.float32).copy()
    arr[..., :3] = arr[..., :3] * (1 - 0.55 * borda[..., None]) + 255 * 0.55 * borda[..., None]
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


class Icones(Elemento):
    """Ícones neon (SF Symbols) que sobem do pé da tela e se encaixam no peito, um por palavra."""

    POS = {1: [(0, 0)], 2: [(-0.62, 0), (0.62, 0)], 3: [(-0.15, -0.55), (-0.62, 0.38), (0.58, 0.22)],
           4: [(-0.6, -0.45), (0.6, -0.45), (-0.6, 0.5), (0.6, 0.5)]}

    def __init__(self, s: dict):
        self.s = s
        self.itens = []
        for i, it in enumerate(s["itens"]):
            self.itens.append({"arq": it["simbolo"], "t": T_na(it.get("em", s["em"])) if "em" in it else T(s["em"]) + 0.18 * i,
                               "cor": it.get("cor", NEON_ICONES[i % len(NEON_ICONES)])})
        self.t0 = min(it["t"] for it in self.itens) - 0.05
        self.t1 = T_fim(s.get("ate"), s["em"])
        self.lado = int(s.get("lado", 210))
        self.gira = bool(s.get("gira", False))
        r = rosto(self.t0)
        fx, fy, fw, fh = r["rosto"]
        self.cx = float(s.get("x", W / 2))
        self.cy = float(s.get("y", min(H * 0.70, fy + fh + 360)))

    def desenha(self, cv: Image.Image, t: float) -> None:
        pos = self.POS[min(4, len(self.itens))]
        sai = cl((t - (self.t1 - 0.22)) / 0.22)
        for i, it in enumerate(self.itens):
            d = t - it["t"]
            if d < 0:
                continue
            k = ease_out(d / 0.38)
            px, py = pos[i % len(pos)]
            x = self.cx + px * self.lado * 1.15
            y_alvo = self.cy + py * self.lado * 1.15
            y = lerp(H + self.lado, y_alvo, k) + 6 * math.sin(2 * math.pi * (d / 2.4) + i)
            im = icone_neon(it["arq"], self.lado, it["cor"])
            if self.gira:
                im = im.rotate((-1) ** i * 38 * d, resample=Image.BICUBIC)
            s = lerp(0.7, 1.0, mola(d / 0.4)) * (1 - 0.35 * ease_in(sai))
            im = escala(im, s)
            cola(cv, opaco(im, 1 - sai), x, y + 60 * ease_in(sai))

    def eventos(self):
        return [(it["t"], "sobe_curto") for it in self.itens]

    def nome(self):
        return "ícones " + ", ".join(Path(it["arq"]).stem for it in self.itens)


@functools.lru_cache(maxsize=16)
def titulo_neon(txt: str, tam: int, cor: str) -> Image.Image:
    """Título só de contorno: traço neon por fora da letra, miolo com tinta fraca (transparente)."""
    f = F("titulo", tam)
    bb = f.getbbox(txt)
    m = int(tam * 0.45)
    w, h = bb[2] - bb[0] + 2 * m, bb[3] - bb[1] + 2 * m
    sw = max(4, tam // 34)
    cheio = Image.new("L", (w, h), 0)
    ImageDraw.Draw(cheio).text((m - bb[0], m - bb[1]), txt, font=f, fill=255)
    borda = Image.new("L", (w, h), 0)
    ImageDraw.Draw(borda).text((m - bb[0], m - bb[1]), txt, font=f, fill=255, stroke_width=sw, stroke_fill=255)
    a = np.asarray(cheio, np.float32) / 255
    b = np.asarray(borda, np.float32) / 255
    linha = np.clip(b - morfo(a, max(3, sw * 0.9), False), 0, 1)
    return neon(blur_l(linha, 0.8), [cor], raio=tam * 0.05, nucleo_branco=0.45, tinta=a * 0.14)


class Titulo(Elemento):
    """'PASSO 1' gigante, itálico condensado, só contorno neon, no peito."""

    def __init__(self, s: dict):
        self.s = s
        self.txt = s["texto"].upper()
        self.t0 = T(s["em"])
        self.t1 = T_fim(s.get("ate"), s["em"])
        r = rosto(self.t0)
        fx, fy, fw, fh = r["rosto"]
        self.tam = int(s.get("tamanho", 240))
        self.cy = float(s.get("y", min(H * 0.68, fy + fh + 300)))

    def desenha(self, cv: Image.Image, t: float) -> None:
        d = t - self.t0
        im = titulo_neon(self.txt, self.tam, self.s.get("cor", COR_TITULO))
        if im.width > W * 0.96:
            im = escala(im, W * 0.96 / im.width)
        a = acende(d, 0.25) * cl((self.t1 - t) / 0.15)
        s = lerp(1.18, 1.0, ease_out(d / 0.2))
        if d < 0.2:
            im = im.filter(ImageFilter.GaussianBlur(10 * (1 - d / 0.2)))
        cola(cv, opaco(escala(im, s) if s > 1.001 else im, a), W / 2, self.cy)

    def eventos(self):
        return [(self.t0, "impacto")]

    def nome(self):
        return f"título {self.txt}"


class Linha(Elemento):
    """Linha neon de crescimento: onda que sobe da esquerda pra direita no peito e se apaga pela cauda."""

    def __init__(self, s: dict):
        self.s = s
        self.t0 = T(s["em"])
        self.dur = float(s.get("dur", 1.5))
        self.t1 = self.t0 + self.dur
        self.cor = s.get("cor", "#39FF14")
        r = rosto(self.t0)
        fx, fy, fw, fh = r["rosto"]
        y0 = float(s.get("y", min(H * 0.74, fy + fh + 470)))
        xs = np.linspace(-60, W + 60, 260)
        u = (xs + 60) / (W + 120)
        ys = y0 + 120 - 330 * u ** 1.35 + 70 * np.sin(u * 2 * math.pi * 1.6)
        self.pts = np.stack([xs, ys], 1)
        seg = np.hypot(*np.diff(self.pts, axis=0).T)
        self.s_acum = np.concatenate([[0], np.cumsum(seg)])

    def desenha(self, cv: Image.Image, t: float) -> None:
        d = (t - self.t0) / self.dur
        cabeca = ease_out(d / 0.5)
        cauda = ease_in_out((d - 0.45) / 0.55)
        L = self.s_acum[-1]
        sel = (self.s_acum >= cauda * L) & (self.s_acum <= cabeca * L)
        p = self.pts[sel]
        if len(p) < 2:
            return
        f = 2
        y_min, y_max = int(p[:, 1].min()) - 120, int(p[:, 1].max()) + 120
        hh = max(4, (y_max - y_min) // f)
        m = Image.new("L", (W // f, hh), 0)
        ImageDraw.Draw(m).line([((x) / f, (y - y_min) / f) for x, y in p], fill=255, width=max(2, 12 // f), joint="curve")
        a = np.asarray(m.resize((W, hh * f), Image.BILINEAR), np.float32) / 255
        im = neon(a, [self.cor], raio=16, nucleo_branco=0.5)
        cv.alpha_composite(im.crop((0, max(0, -y_min), W, im.height)), (0, max(0, y_min)))

    def eventos(self):
        return [(self.t0, "brilho")]


class Clarao(Elemento):
    """Light leak laranja que varre da esquerda (troca de seção)."""

    def __init__(self, spec):
        self.t0 = T(spec) if not isinstance(spec, dict) else T(spec["em"])
        self.dur = 0.45
        self.t1 = self.t0 + self.dur

    def desenha(self, cv: Image.Image, t: float) -> None:
        u = (t - self.t0) / self.dur
        inten = math.sin(math.pi * cl(u)) ** 1.2
        if inten < 0.02:
            return
        w, h = W // 8, H // 8
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx = lerp(-0.25, 0.55, u) * w
        cy = lerp(0.35, 0.6, u) * h
        dx = (xx - cx) / (w * 0.42)
        dy = (yy - cy) / (h * 0.75)
        r = np.exp(-(dx ** 2 + dy ** 2) * 1.6)
        faixa = np.exp(-(((xx - cx) * 0.9 + (yy - cy) * 0.35) / (w * 0.10)) ** 2)
        k = np.clip((r * 0.95 + faixa * 0.55) * inten, 0, 1)
        cor = np.array([255, 150, 60], np.float32)
        branco = np.clip(k * 1.6 - 0.7, 0, 1)[..., None]
        luz = (cor * (1 - branco) + 255 * branco) * k[..., None]
        luz = Image.fromarray(np.clip(luz, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.BILINEAR)
        base = np.asarray(cv.convert("RGB"), np.float32)
        L = np.asarray(luz, np.float32)
        out = 255 - (255 - base) * (255 - L) / 255         # screen
        cv.paste(Image.fromarray(out.astype(np.uint8), "RGB"))

    def eventos(self):
        return [(self.t0, "whoosh")]

    def nome(self):
        return "clarão"


class Cartao(Elemento):
    """Cartão de perfil do Instagram (foto, @, botão que muda no clique) no peito, como o CTA da referência."""

    def __init__(self, s: dict):
        self.s = s
        self.t0 = T(s["em"])
        self.t1 = T_fim(s.get("ate"), s["em"]) if s.get("ate") is not None else TOTAL
        self.tc = T_na(s["clique"]) if s.get("clique") is not None else self.t0 + 1.0
        r = rosto(self.t0)
        fx, fy, fw, fh = r["rosto"]
        self.cy = float(s.get("y", min(H * 0.70, fy + fh + 300)))

    @functools.lru_cache(maxsize=4)
    def img(self, clicado: bool) -> Image.Image:
        w, h = 700, 116
        c = ret_arred(w, h, 26, (255, 255, 255, 255))
        d = ImageDraw.Draw(c)
        foto = imagem(self.s.get("foto", FOTO_PERFIL)).convert("RGBA")
        lado = 80
        foto = foto.resize((lado, lado), Image.LANCZOS)
        mk = Image.new("L", (lado, lado), 0)
        ImageDraw.Draw(mk).ellipse((0, 0, lado - 1, lado - 1), fill=255)
        c.paste(foto, (20, (h - lado) // 2), mk)
        d.text((118, h / 2 - 2), self.s.get("arroba", PERFIL["instagram"]), font=F("sf_bold", 33), fill=(20, 20, 20), anchor="lm")
        bt = self.s.get("botao_depois", "Seguindo") if clicado else self.s.get("botao", "Seguir")
        f = F("sf_bold", 30)
        bw = max(150, int(f.getlength(bt)) + 56)
        x0 = w - bw - 18
        cor_b, cor_t = ((239, 239, 239), (20, 20, 20)) if clicado else ((0, 149, 246), (255, 255, 255))
        d.rounded_rectangle((x0, 26, w - 18, h - 26), 16, fill=cor_b)
        d.text((x0 + bw / 2, h / 2), bt, font=f, fill=cor_t, anchor="mm")
        sombra = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rounded_rectangle((40, 48, w + 40, h + 48), 26, fill=(0, 0, 0, 110))
        sombra = sombra.filter(ImageFilter.GaussianBlur(16))
        sombra.alpha_composite(c, (40, 40))
        return sombra

    def desenha(self, cv: Image.Image, t: float) -> None:
        d = t - self.t0
        im = self.img(t >= self.tc)
        k = ease_out(d / 0.28)
        sai = cl((t - (self.t1 - 0.2)) / 0.2)
        if k < 1:   # nasce de uma barra estreita, como na referência
            w = max(40, int(im.width * lerp(0.35, 1.0, k)))
            im = im.resize((w, im.height), Image.BILINEAR)
        s = 1.0 - 0.06 * math.sin(math.pi * cl((t - self.tc) / 0.2)) if t >= self.tc else 1.0
        im = escala(im, s) if s < 0.999 else im
        cola(cv, opaco(im, min(1.0, d / 0.12) * (1 - sai)), W / 2, self.cy)
        if self.tc <= t < self.tc + 0.45:     # toque no botão
            u = (t - self.tc) / 0.45
            rr = int(lerp(18, 60, u))
            toque = Image.new("RGBA", (2 * rr + 4, 2 * rr + 4), (0, 0, 0, 0))
            ImageDraw.Draw(toque).ellipse((2, 2, 2 * rr + 2, 2 * rr + 2), fill=(255, 255, 255, int(150 * (1 - u))))
            cola(cv, toque, W / 2 + 350 - 18 - 90, self.cy)

    def eventos(self):
        return [(self.t0, "pop"), (self.tc, "clique")]

    def nome(self):
        return f"cartão {self.s.get('arroba', PERFIL['instagram'])}"


# ---------------------------------------------------------------- iPhone 3D
PW, PH = 700, 1440          # corpo do iPhone em px (antes da escala)
BORDA, BISEL = 11, 13       # aro prata, borda preta
SX0, SY0 = BORDA + BISEL, BORDA + BISEL
SW, SH = PW - 2 * SX0, PH - 2 * SY0
R_CORPO, R_TELA = 112, 92
BARRA = 70                  # barra de status desenhada quando a fonte não é gravação de iPhone


@functools.lru_cache(maxsize=1)
def moldura() -> tuple[Image.Image, Image.Image]:
    """(aro + borda + ilha dinâmica com a tela vazada, máscara da tela)."""
    m = 8
    im = Image.new("RGBA", (PW + 2 * m, PH + 2 * m), (0, 0, 0, 0))
    # botões laterais
    d = ImageDraw.Draw(im)
    for x, y0, y1 in ((m - 5, 300, 380), (m - 5, 420, 540), (m - 5, 570, 690), (PW + m - 1, 430, 610)):
        d.rounded_rectangle((x, y0, x + 6, y1), 3, fill=(150, 150, 158, 255))
    # aro prata em degradê
    aro = Image.fromarray(np.dstack([gradiente(PW, PH, ["#F4F4F7", "#A9A9B2", "#E6E6EA", "#8E8E97"]),
                                     np.full((PH, PW), 255, np.float32)]).astype(np.uint8), "RGBA")
    mk = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(mk).rounded_rectangle((0, 0, PW - 1, PH - 1), R_CORPO, fill=255)
    im.paste(aro, (m, m), mk)
    ImageDraw.Draw(im).rounded_rectangle((m + 2, m + 2, m + PW - 3, m + PH - 3), R_CORPO - 2,
                                         outline=(255, 255, 255, 160), width=2)
    ImageDraw.Draw(im).rounded_rectangle((m + BORDA, m + BORDA, m + PW - BORDA - 1, m + PH - BORDA - 1),
                                         R_CORPO - BORDA, fill=(8, 8, 10, 255))
    tela = Image.new("L", im.size, 0)
    ImageDraw.Draw(tela).rounded_rectangle((m + SX0, m + SY0, m + SX0 + SW - 1, m + SY0 + SH - 1), R_TELA, fill=255)
    a = np.asarray(im.getchannel("A"), np.int16) - np.asarray(tela, np.int16)
    im.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L"))
    # ilha dinâmica (vai por cima da tela)
    ilha = Image.new("RGBA", im.size, (0, 0, 0, 0))
    iw, ih = 196, 58
    ImageDraw.Draw(ilha).rounded_rectangle(((im.width - iw) / 2, m + SY0 + 22, (im.width + iw) / 2, m + SY0 + 22 + ih),
                                           ih // 2, fill=(0, 0, 0, 255))
    im.alpha_composite(ilha)
    return im, tela


def coefs(origem: list, destino: list) -> list:
    """Coeficientes do Image.PERSPECTIVE (mapeiam ponto da SAÍDA → ponto da origem)."""
    A, B = [], []
    for (x, y), (X, Y) in zip(destino, origem):
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y]); B.append(X)
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y]); B.append(Y)
    return list(np.linalg.solve(np.array(A, float), np.array(B, float)))


def projeta(w: float, h: float, yaw: float, pitch: float, roll: float) -> list:
    """Cantos de um retângulo w×h girado em 3D (graus) e projetado em perspectiva, centrado em (0, 0)."""
    a, b, c = map(math.radians, (yaw, pitch, roll))
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    Rm = Rz @ Rx @ Ry
    f = 2.6 * h
    out = []
    for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        p = Rm @ np.array([x, y, 0.0])
        z = p[2] + f
        out.append((p[0] * f / z, p[1] * f / z))
    return out


class Leitor:
    """ffmpeg aberto quando o iPhone entra: um quadro da gravação por quadro de saída."""

    def __init__(self, arq: Path, inicio: float, vel: float, vf: str, size: tuple):
        self.size = size
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{inicio:.3f}", "-i", str(arq), "-an", "-vf",
                                   f"{vf},setpts=(PTS-STARTPTS)/{vel},fps={FPS_NUM}/{FPS_DEN}",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.ult = None

    def proximo(self) -> Image.Image:
        tam = self.size[0] * self.size[1] * 3
        buf = self.p.stdout.read(tam)
        if len(buf) == tam:
            self.ult = Image.frombytes("RGB", self.size, buf)
        return self.ult

    def fecha(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()


class IPhone(Elemento):
    """A demonstração dentro de um iPhone 3D: sobe do pé da tela, aproxima devagar, balança, sai voando
    pra cima. Fundo (a pessoa) desfocado e escurecido enquanto ele está na tela."""
    camada = "tela"

    def __init__(self, s: dict):
        self.s = s
        self.t0 = T(s["em"])
        self.t1 = T_fim(s.get("ate"), s["em"])
        self.arq = _resolve(s["arquivo"])
        self.video = e_video(str(self.arq))
        self.inicio = float(s.get("inicio", 0))
        self.vel = float(s.get("velocidade", 1))
        self.zoom = s.get("zoom", [0.62, 0.78])        # altura do iPhone na tela (fração): depois de entrar → no fim
        self.toques = [{"caixa": tq["caixa"], "t": T_na(tq["em"]), "dur": float(tq.get("dur", 1.1))}
                       for tq in s.get("toques", [])]
        self.focos = [{"caixa": fc["caixa"], "t0": T(fc["em"]), "t1": T(fc["ate"]) if fc.get("ate") else self.t1 - 0.4,
                       "z": float(fc.get("zoom", 0))} for fc in s.get("focos", [])]
        self.rolagem = [(T(r[0]), float(r[1]), float(r[2]) if len(r) > 2 else 0.8) for r in s.get("rolagem", [])]
        self.fase = float(s.get("fase", sum(map(ord, s["arquivo"])) % 7))
        self.alinha = s.get("alinha", "topo")        # "baixo" = conversa de chat (caixa de mensagem no pé)
        self.leitor = None
        # tamanho da fonte (já recortada)
        if self.video:
            pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                            "stream=width,height", "-of", "json", str(self.arq)],
                                           capture_output=True, text=True, check=True).stdout)["streams"][0]
            fw, fh = pr["width"], pr["height"]
        else:
            fw, fh = imagem(str(self.arq)).size
        self.rec = s.get("recorte") or [0, 0, fw, fh]
        rx, ry, rw, rh = self.rec
        self.barra = s.get("barra", not (rh > rw and rw / rh < 0.52))   # gravação de iPhone já tem a barra
        self.esc = min(1.0, 2 * SW / rw)            # guarda 2x a largura da tela (pro foco não borrar)
        self.fsize = (int(rw * self.esc) // 2 * 2, int(rh * self.esc) // 2 * 2)
        self.vf = f"crop={rw}:{rh}:{rx}:{ry},scale={self.fsize[0]}:{self.fsize[1]}"

    # --- conteúdo da tela
    def fonte(self, t: float) -> Image.Image:
        if not self.video:
            im = imagem(str(self.arq)).convert("RGB")
            rx, ry, rw, rh = self.rec
            return im.crop((rx, ry, rx + rw, ry + rh)).resize(self.fsize, Image.LANCZOS)
        if ARGS.so_quadros or ARGS.storyboard:   # quadro avulso: busca direta (o leitor é sequencial)
            ts = self.inicio + (t - self.t0) * self.vel
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", str(self.arq), "-vf", self.vf,
                                  "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, check=True).stdout
            return Image.frombytes("RGB", self.fsize, raw)
        if self.leitor is None:
            self.leitor = Leitor(self.arq, self.inicio, self.vel, self.vf, self.fsize)
        return self.leitor.proximo()

    def caixa_fonte(self, caixa: list) -> list:
        """Caixa em px da gravação original → px da fonte já recortada e reduzida."""
        x, y, w, h = caixa
        return [(x - self.rec[0]) * self.esc, (y - self.rec[1]) * self.esc, w * self.esc, h * self.esc]

    def janela(self, t: float, fw: int, fh: int, alt_util: int) -> tuple:
        """Parte da fonte que aparece na tela (x, y, w, h em px da fonte): rolagem e foco (zoom na tela)."""
        vw = fw
        vh = vw * alt_util / SW
        frac = 0.0
        for t_r, alvo, dur in self.rolagem:
            if t >= t_r:
                frac = lerp(frac, alvo, ease_in_out((t - t_r) / dur))
        vx, vy = 0.0, frac * max(0.0, fh - vh)
        if self.alinha == "baixo" and fh < vh:      # fonte mais baixa que a tela: encosta no pé
            vy = fh - vh
        for fc in self.focos:
            k = ease_in_out((t - fc["t0"]) / 0.45) * (1 - ease_in_out((t - fc["t1"]) / 0.35))
            if k <= 0:
                continue
            bx, by, bw, bh = self.caixa_fonte(fc["caixa"])
            z = fc["z"] or cl(fw * 0.86 / bw, 1.0, 3.0)
            w2 = fw / z
            h2 = w2 * alt_util / SW
            x2 = cl(bx + bw / 2 - w2 / 2, 0, fw - w2)
            y2 = cl(by + bh / 2 - h2 / 2, 0, max(0, fh - h2))
            vx, vy, vw, vh = lerp(vx, x2, k), lerp(vy, y2, k), lerp(vw, w2, k), lerp(vh, h2, k)
        return vx, vy, vw, vh

    def tela(self, t: float) -> Image.Image:
        src = self.fonte(t)
        fw, fh = src.size
        topo = BARRA if self.barra else 0
        alt = SH - topo
        vx, vy, vw, vh = self.janela(t, fw, fh, alt)
        fundo_px = src.getpixel((fw // 2, 2)) if self.alinha == "baixo" else src.getpixel((fw // 2, fh - 3))
        corpo = src.transform((SW, alt), Image.EXTENT, (vx, vy, vx + vw, vy + vh), Image.BICUBIC, fillcolor=fundo_px)
        # RGB de propósito: num RGBA o ImageDraw SUBSTITUI o pixel (alfa junto) e o toque vira buraco preto
        tela = Image.new("RGB", (SW, SH), (0, 0, 0))
        tela.paste(corpo.convert("RGB"), (0, topo))
        d = ImageDraw.Draw(tela, "RGBA")
        k = SW / vw
        for tq in self.toques:
            u = (t - tq["t"]) / tq["dur"]
            if not 0 <= u < 1:
                continue
            bx, by, bw, bh = self.caixa_fonte(tq["caixa"])
            x0, y0 = (bx - vx) * k, (by - vy) * k + topo
            x1, y1 = x0 + bw * k, y0 + bh * k
            a = min(1.0, u / 0.08) * (1 - cl((u - 0.8) / 0.2))
            d.rounded_rectangle((x0 - 6, y0 - 4, x1 + 6, y1 + 4), 14, fill=(255, 59, 92, int(95 * a)),
                                outline=(255, 59, 92, int(230 * a)), width=4)
            rr = lerp(16, 46, cl(u / 0.35))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(255, 255, 255, int(150 * (1 - cl(u / 0.35)))))
        if self.barra:
            topo_px = np.asarray(corpo.crop((0, 0, SW, 6)).convert("RGB"), np.float32).reshape(-1, 3).mean(0)
            d.rectangle((0, 0, SW, topo), fill=tuple(int(v) for v in topo_px))
            claro = topo_px.mean() > 140
            tinta = (15, 15, 15, 255) if claro else (250, 250, 250, 255)
            d.text((70, 40), "9:41", font=F("sf_bold", 30), fill=tinta, anchor="lm")
            for i in range(4):           # sinal
                hh = 8 + i * 4
                d.rounded_rectangle((SW - 158 + i * 10, 50 - hh, SW - 152 + i * 10, 50), 2, fill=tinta)
            d.rounded_rectangle((SW - 104, 30, SW - 60, 50), 6, outline=tinta, width=2)      # bateria
            d.rounded_rectangle((SW - 100, 34, SW - 70, 46), 3, fill=tinta)
        return tela

    def aparelho(self, t: float) -> Image.Image:
        mold, mk_tela = moldura()
        im = Image.new("RGBA", mold.size, (0, 0, 0, 0))
        m = 8
        im.paste(self.tela(t), (m + SX0, m + SY0), mk_tela.crop((m + SX0, m + SY0, m + SX0 + SW, m + SY0 + SH)))
        # reflexo leve do vidro
        brilho = Image.new("L", im.size, 0)
        ImageDraw.Draw(brilho).polygon([(0, 0), (im.width * 0.55, 0), (0, im.height * 0.38)], fill=22)
        brilho = Image.composite(brilho, Image.new("L", im.size, 0), mk_tela)
        im.alpha_composite(Image.merge("RGBA", (Image.new("L", im.size, 255),) * 3 + (brilho,)))
        im.alpha_composite(mold)
        return im

    # --- movimento
    D_IN, D_OUT = 0.55, 0.38

    def estado(self, t: float) -> dict:
        d = t - self.t0
        u_in = cl(d / self.D_IN)
        u_out = cl((t - (self.t1 - self.D_OUT)) / self.D_OUT)
        z0, z1 = self.zoom
        prog = cl((d - self.D_IN) / max(0.2, self.t1 - self.t0 - self.D_IN - self.D_OUT))
        alt = lerp(0.42, z0, ease_out(u_in)) if u_in < 1 else lerp(z0, z1, ease_in_out(prog))
        alt *= H
        cy = lerp(H + alt * 0.30, H * 0.52, ease_out(u_in)) - ease_in(u_out) * (H * 0.52 + alt * 0.62 + 60)
        ph = self.fase
        return {
            "alt": alt, "cx": W / 2 + 14 * math.sin(2 * math.pi * d / 6.0 + ph), "cy": cy,
            "yaw": 11 * math.sin(2 * math.pi * d / 4.4 + ph) * lerp(1.6, 1.0, u_in),
            "pitch": 7 * math.sin(2 * math.pi * d / 5.2 + ph + 1.3) + lerp(14, 0, ease_out(u_in)),
            "roll": lerp(-13, 0, ease_out(u_in)) + 3 * math.sin(2 * math.pi * d / 6.3 + ph) + 9 * ease_in(u_out),
            "fundo": cl(d / 0.25) * (1 - cl((t - (self.t1 - 0.22)) / 0.22)),
        }

    def fundo(self, cv: Image.Image, t: float) -> Image.Image:
        k = self.estado(t)["fundo"]
        if k <= 0:
            return cv
        pequeno = cv.convert("RGB").resize((W // 10, H // 10), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.2 * k + 0.3))
        borrado = pequeno.resize((W, H), Image.BILINEAR)
        escuro = Image.blend(borrado, Image.new("RGB", (W, H), (0, 0, 0)), 0.42).convert("RGBA")
        return Image.blend(cv, escuro, k)

    def desenha(self, cv: Image.Image, t: float) -> None:
        e = self.estado(t)
        ap = self.aparelho(t)
        s = e["alt"] / ap.height
        q = projeta(ap.width * s, ap.height * s, e["yaw"], e["pitch"], e["roll"])
        q = [(x + e["cx"], y + e["cy"]) for x, y in q]
        x0, y0 = int(min(p[0] for p in q)) - 2, int(min(p[1] for p in q)) - 2
        x1, y1 = int(max(p[0] for p in q)) + 2, int(max(p[1] for p in q)) + 2
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            return
        # sombra macia embaixo
        f = 4
        sb = Image.new("L", (W // f, H // f), 0)
        ImageDraw.Draw(sb).polygon([(x / f, (y + 38) / f) for x, y in q], fill=150)
        sb = sb.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BILINEAR)
        cv.alpha_composite(Image.merge("RGBA", (Image.new("L", (W, H), 0),) * 3 + (sb,)))
        local = [(x - x0, y - y0) for x, y in q]
        orig = [(0, 0), (ap.width, 0), (ap.width, ap.height), (0, ap.height)]
        im = ap.transform((x1 - x0, y1 - y0), Image.PERSPECTIVE, coefs(orig, local), Image.BICUBIC)
        cv.alpha_composite(im.crop((max(0, -x0), max(0, -y0), im.width, im.height)), (max(0, x0), max(0, y0)))

    def eventos(self):
        return [(self.t0, "sobe"), (self.t1 - self.D_OUT, "whoosh")] + [(tq["t"], "clique") for tq in self.toques]

    def nome(self):
        return f"iPhone {Path(self.s['arquivo']).name}"

    def fecha(self):
        if self.leitor:
            self.leitor.fecha()
            self.leitor = None


# ---------------------------------------------------------------- lê o mapa
ELEMENTOS: list[Elemento] = []
ELEMENTOS += [Glow(s) for s in MAPA.get("glows", [])]
ELEMENTOS += [IPhone(s) for s in MAPA.get("iphones", [])]
ELEMENTOS += [Icones(s) for s in MAPA.get("icones", [])]
ELEMENTOS += [Titulo(s) for s in MAPA.get("titulos", [])]
ELEMENTOS += [Linha(s) for s in MAPA.get("linhas", [])]
ELEMENTOS += [Clarao(s) for s in MAPA.get("claroes", [])]
if MAPA.get("cartao"):
    ELEMENTOS.append(Cartao(MAPA["cartao"]))
ELEMENTOS.sort(key=lambda e: e.t0)
GLOWS = [e for e in ELEMENTOS if isinstance(e, Glow)]
IPHONES = [e for e in ELEMENTOS if isinstance(e, IPhone)]
FRENTE = [e for e in ELEMENTOS if e.camada == "frente" and not isinstance(e, Clarao)]
CLAROES = [e for e in ELEMENTOS if isinstance(e, Clarao)]


def janelas_mascara() -> list[tuple[float, float]]:
    """Trechos com logo neon atrás da cabeça (a pessoa recortada na frente)."""
    return [(g.t0 - 0.05, g.t1 + 0.05) for g in GLOWS]


# ---------------------------------------------------------------- legenda
SINAIS = ".,!?;:…\"'“”()[]"


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    maxp = int(MAPA.get("leg_palavras", 2))
    maxc = int(MAPA.get("leg_chars", 14))
    blocos, atual = [], []

    def fecha():
        if atual:
            blocos.append(list(atual))
            atual.clear()

    for i, w in enumerate(WORDS):
        txt = w["t"].strip()
        if not txt.strip(SINAIS):
            continue
        if atual and (WORDS[atual[-1]]["seg"] != w["seg"] or w["s"] - WORDS[atual[-1]]["e"] > 0.35):
            fecha()
        cand = " ".join(WORDS[j]["t"].strip().strip(SINAIS) for j in atual + [i])
        if atual and (len(atual) >= maxp or len(cand) > maxc):
            fecha()
        atual.append(i)
        if txt[-1:] in ".!?,;:":
            fecha()
    fecha()
    out = []
    for k, b in enumerate(blocos):
        txt = " ".join(WORDS[j]["t"].strip() for j in b).strip(" ,;:")
        ini = WORDS[b[0]]["s"] - 0.04
        prox = WORDS[blocos[k + 1][0]]["s"] - 0.04 if k + 1 < len(blocos) else TOTAL
        fim = prox if prox - WORDS[b[-1]]["e"] < 0.6 else WORDS[b[-1]]["e"] + 0.2
        out.append({"txt": txt.upper(), "ini": max(0.0, ini), "fim": min(TOTAL, fim), "g": WORDS[b[0]]["seg"]})
    return out


LEG_TAM = int(MAPA.get("leg_tamanho", 66))


@functools.lru_cache(maxsize=256)
def legenda_img(txt: str) -> Image.Image:
    """Caixa alta condensada amarela, contorno escuro fino + sombra macia (legível na blusa clara e no iPhone)."""
    f = F("legenda", LEG_TAM)
    bb = f.getbbox(txt, stroke_width=4)
    m = 30
    w, h = bb[2] - bb[0] + 2 * m, bb[3] - bb[1] + 2 * m
    pos = (m - bb[0], m - bb[1])
    sombra = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sombra).text(pos, txt, font=f, fill=200, stroke_width=6, stroke_fill=200)
    sombra = sombra.filter(ImageFilter.GaussianBlur(9))
    im = Image.merge("RGBA", (Image.new("L", (w, h), 0),) * 3 + (sombra,))
    ImageDraw.Draw(im).text(pos, txt, font=f, fill=COR + (255,), stroke_width=3, stroke_fill=(25, 20, 10, 255))
    return im


def leg_y(t: float) -> float:
    if MAPA.get("leg_y"):
        return float(MAPA["leg_y"])
    r = rosto(t)["rosto"]
    return cl(r[1] + r[3] + 80, H * 0.46, H * 0.60)


# ---------------------------------------------------------------- composição do quadro
def compoe(fr: Image.Image, t: float, legendas: list[dict], n: int) -> Image.Image:
    z = zoom_de(t)
    cv = aplica_zoom(fr, t, z)
    glows = [g for g in GLOWS if g.ativo(t)]
    if glows:
        pessoa = cv.copy()
        for g in glows:
            g.desenha(cv, t)
        m = mascara(n)
        if m is not None:
            m = aplica_zoom(m.convert("RGBA"), t, z).getchannel("R") if z > 1.001 else m
            cv = Image.composite(pessoa, cv, m)
    for e in IPHONES:
        if e.ativo(t):
            cv = e.fundo(cv, t)
            e.desenha(cv, t)
    for e in FRENTE:
        if e.ativo(t):
            e.desenha(cv, t)
    for e in CLAROES:
        if e.ativo(t):
            e.desenha(cv, t)
    for b in legendas:
        if b["ini"] <= t < b["fim"]:
            cola(cv, legenda_img(b["txt"]), W / 2, leg_y(b["ini"]))
            break
    return cv


# ================================================================ áudio (voz + efeito curto por evento)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def _ruido_banda(n: int, fc: float, rng, larg: float = 0.9) -> np.ndarray:
    esp = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    esp *= np.exp(-((np.log(f + 1) - np.log(fc)) ** 2) / larg)
    return np.fft.irfft(esp, n)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome in ("whoosh", "sobe", "sobe_curto"):
        d = {"whoosh": 0.32, "sobe": 0.5, "sobe_curto": 0.22}[nome]
        n = int(d * SR)
        x = _ruido_banda(n, 2200 if nome == "whoosh" else 1600, rng)
        if nome != "whoosh":       # sobe: o brilho do ruído cresce
            x = x * np.linspace(0.4, 1.0, n) + _ruido_banda(n, 4200, rng) * np.linspace(0, 0.6, n)
        x = x * _env(n, 0.6 if nome != "whoosh" else 0.5)
        return x / (np.abs(x).max() + 1e-9) * (0.7 if nome == "sobe_curto" else 1.0)
    if nome == "neon":             # zumbido elétrico que pisca junto com o acender
        d = 0.45
        n = int(d * SR)
        tt = np.arange(n) / SR
        zum = sum(np.sin(2 * np.pi * 120 * k * tt) / k for k in (1, 2, 3, 5))
        pis = np.array([acende(v) for v in tt]) * np.exp(-tt * 3)
        x = (zum * 0.5 + rng.standard_normal(n) * 0.35) * pis
        return x / (np.abs(x).max() + 1e-9) * 0.8
    if nome == "brilho":           # cintilar que sobe (linha de crescimento)
        d = 0.9
        n = int(d * SR)
        tt = np.arange(n) / SR
        fr = 900 + 2400 * (tt / d) ** 1.5
        x = np.sin(2 * np.pi * np.cumsum(fr) / SR) * 0.35 + _ruido_banda(n, 6000, rng) * 2
        x = x * _env(n, 0.55)
        return x / (np.abs(x).max() + 1e-9) * 0.6
    if nome == "impacto":
        d = 0.45
        n = int(d * SR)
        tt = np.arange(n) / SR
        x = np.sin(2 * np.pi * (70 - 30 * tt / d) * tt) * np.exp(-tt * 9) + _ruido_banda(n, 900, rng) * 3 * np.exp(-tt * 30)
        return x / (np.abs(x).max() + 1e-9) * 0.9
    if nome == "clique":
        d = 0.03
        n = int(d * SR)
        tt = np.arange(n) / SR
        x = rng.standard_normal(n) * np.exp(-tt * 260) + np.sin(2 * np.pi * 2600 * tt) * np.exp(-tt * 200)
        return x / (np.abs(x).max() + 1e-9) * 0.6
    d = 0.08   # pop
    n = int(d * SR)
    tt = np.arange(n) / SR
    fr = 1200 + (560 - 1200) * tt / d
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 40) * 0.7


def eventos_som() -> list[tuple[float, str]]:
    ev = []
    for e in ELEMENTOS:
        ev += e.eventos()
    return sorted(ev)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -24) if isinstance(cfg, dict) else -24
        ultimo = -9.0
        for t, nome in eventos_som():
            if t - ultimo < 0.08:
                continue
            ultimo = t
            s = sfx(nome) * 10 ** (gdb / 20)
            i = int(max(0, t) * SR)
            pista[i:i + len(s)] += s[: len(pista) - i]
    mus = MAPA.get("musica")
    if mus:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mus.get("inicio", 0)), "-i", str(_resolve(mus["arquivo"])),
                              "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = int(TOTAL * SR)
        x = np.tile(x, n // len(x) + 1)[:n]
        x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 10 ** (mus.get("db", -30) / 20)
        # a referência derruba a trilha a zero por um instante em cada troca de seção (clarão)
        for c in CLAROES:
            a, b = int(c.t0 * SR), int((c.t0 + 0.12) * SR)
            x[a:b] *= 0.05
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
    for e in ELEMENTOS:
        print(f"  {e.t0:6.2f}-{e.t1:6.2f} ({e.t1 - e.t0:4.1f}s) {e.nome()}")
        if isinstance(e, (Glow, IPhone, Titulo)) and e.t1 - e.t0 < 0.9:
            print(f"  ATENÇÃO: {e.nome()} dura {e.t1 - e.t0:.2f}s (curto demais pra ler)")
    for a, b in itertools.combinations(GLOWS + IPHONES, 2):
        if a.t0 < b.t1 and b.t0 < a.t1:
            print(f"  ATENÇÃO: {a.nome()} e {b.nome()} se sobrepõem")

    def frac(lst):
        return sum(1 for k in range(N_FRAMES) if any(e.ativo(k / FPS) for e in lst)) / max(1, N_FRAMES)
    graf = [e for e in ELEMENTOS if not isinstance(e, Clarao)]
    print(f"  iPhone na tela {frac(IPHONES):.0%} (referência ~40%), logo neon {frac(GLOWS):.0%} (~19%), "
          f"algum gráfico {frac(graf):.0%}, rosto limpo {1 - frac(graf):.0%} (~30%)")
    ts = sorted({round(e.t0, 2) for e in graf})
    if ts:
        vaos = np.diff([0.0] + ts + [TOTAL])
        print(f"  maior trecho sem elemento novo: {vaos.max():.1f}s (referência: ~3 s)")


# ================================================================ STORYBOARD (aprovação antes do render)
def _falta_arquivo(motivo) -> Image.Image:
    """Quadro no lugar de um arquivo que não existe (o storyboard não pode morrer por isso)."""
    im = Image.new("RGBA", (W, H), (40, 0, 8, 255))
    ImageDraw.Draw(im).multiline_text((60, H / 2), "FALTA ARQUIVO\n" + str(motivo), font=F("sf_bold", 44),
                                      fill=(255, 120, 130, 255), anchor="lm")
    return im


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1, t0=0.0: max(t0, min(t, t1 - 0.05))
    br = lambda s: s.replace(".", ",")
    curto = lambda e: (br(f"dura {e.t1 - e.t0:.1f} s: curto demais pra ler (mínimo ~0,9 s)")
                       if e.t1 - e.t0 < 0.9 else None)
    ms, avisos = [], []
    for e in ELEMENTOS:
        if isinstance(e, Glow):
            for i, it in enumerate(e.itens):
                fim = e.itens[i + 1]["t"] if i + 1 < len(e.itens) else e.t1
                m = {"t0": it["t"], "t1": fim, "quadro": cap(it["t"] + 0.5, fim, it["t"]),
                     "tipo": "Logo neon atrás da cabeça" + (" (troca com piscada)" if i else ""),
                     "desc": f"{Path(it['logo']).stem} — " + " → ".join(it["cores"]) + f" ({e.modo})"}
                if i == 0 and curto(e):
                    m["aviso"] = curto(e)
                ms.append(m)
        elif isinstance(e, IPhone):
            m = {"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + e.D_IN + 0.35, e.t1 - e.D_OUT, e.t0),
                 "tipo": "iPhone 3D com a demonstração",
                 "desc": f"{Path(e.s['arquivo']).name} a partir de {br(f'{e.inicio:.1f}')} s"
                         + (f", {br(f'{e.vel:g}')}x" if e.vel != 1 else "") + " — sobe do pé, aproxima, sai voando"}
            if curto(e):
                m["aviso"] = curto(e)
            ms.append(m)
            for tq in e.toques:
                fim = min(e.t1, tq["t"] + tq["dur"])
                ms.append({"t0": tq["t"], "t1": fim, "quadro": cap(tq["t"] + 0.3, fim, tq["t"]),
                           "tipo": "Toque marcado na tela do iPhone", "desc": f"caixa {tq['caixa']} (px da gravação)"})
            for fc in e.focos:
                ms.append({"t0": fc["t0"], "t1": fc["t1"], "quadro": cap(fc["t0"] + 0.5, fc["t1"], fc["t0"]),
                           "tipo": "Foco: aproxima um detalhe da tela", "desc": f"caixa {fc['caixa']} (px da gravação)"})
            for t_r, alvo, dur in e.rolagem:
                ms.append({"t0": t_r, "t1": t_r + dur, "quadro": cap(t_r + dur, e.t1, t_r),
                           "tipo": "Rolagem da tela do iPhone", "desc": f"rola até {alvo:.0%} do print"})
        elif isinstance(e, Icones):
            ult = max(it["t"] for it in e.itens)
            ms.append({"t0": e.t0, "t1": e.t1, "quadro": cap(ult + 0.45, e.t1, e.t0),
                       "tipo": "Ícones neon sobem pro peito" + (" (girando)" if e.gira else ""),
                       "desc": " · ".join(Path(it["arq"]).stem for it in e.itens)})
        elif isinstance(e, Titulo):
            m = {"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + 0.4, e.t1, e.t0),
                 "tipo": "Título de contorno neon", "desc": e.txt}
            if curto(e):
                m["aviso"] = curto(e)
            ms.append(m)
        elif isinstance(e, Linha):
            ms.append({"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + 0.45 * e.dur, e.t1, e.t0),
                       "tipo": "Linha neon de crescimento", "desc": f"onda {e.cor} no peito, {br(f'{e.dur:.1f}')} s"})
        elif isinstance(e, Clarao):
            ms.append({"t0": e.t0, "t1": e.t1, "quadro": e.t0 + e.dur / 2, "tipo": "Transição: clarão laranja",
                       "desc": "troca de seção do roteiro"})
        elif isinstance(e, Cartao):
            ms.append({"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + 0.4, min(e.tc, e.t1), e.t0),
                       "tipo": "Cartão de perfil (CTA)",
                       "desc": f"@{e.s.get('arroba', PERFIL['instagram'])} · botão \"{e.s.get('botao', 'Seguir')}\""})
            ms.append({"t0": e.tc, "t1": e.t1, "quadro": cap(e.tc + 0.12, e.t1, e.tc), "tipo": "Toque no botão do cartão",
                       "desc": (f"botão vira \"{e.s.get('botao_depois', 'Seguindo')}\""
                                if e.s.get('botao_depois', 'Seguindo') != e.s.get('botao', 'Seguir')
                                else "círculo de toque no botão")})
    for g, (a, b) in sorted(ZOOMS.items()):
        if g < _NG and max(a, b) > 1.001:
            ms.append({"t0": OFF[g], "t1": OFF[g + 1], "quadro": OFF[g + 1] - 0.05, "tipo": "Câmera: aproxima",
                       "desc": br(f"{a:.2f}x → {b:.2f}x ao longo da tomada")})

    # ---- avisos globais (os mesmos do resumo)
    for a, b in itertools.combinations(GLOWS + IPHONES, 2):
        if a.t0 < b.t1 and b.t0 < a.t1:
            avisos.append(f"{a.nome()} e {b.nome()} se sobrepõem")

    def frac(lst):
        return sum(1 for k in range(N_FRAMES) if any(e.ativo(k / FPS) for e in lst)) / max(1, N_FRAMES)
    graf = [e for e in ELEMENTOS if not isinstance(e, Clarao)]
    avisos.append(f"iPhone na tela {frac(IPHONES):.0%} (referência ~40%), logo neon {frac(GLOWS):.0%} (~19%), "
                  f"algum gráfico {frac(graf):.0%}, rosto limpo {1 - frac(graf):.0%} (~30%)")
    ts = sorted({round(e.t0, 2) for e in graf})
    if ts:
        vaos = np.diff([0.0] + ts + [TOTAL])
        avisos.append(br(f"maior trecho sem elemento novo: {vaos.max():.1f} s") + " (referência ~3 s)")

    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]
    nomes = [it["logo"] for s in MAPA.get("glows", []) for it in (s.get("itens") or [{"logo": s.get("logo")}])]
    nomes += [it.get("simbolo") for s in MAPA.get("icones", []) for it in s.get("itens", [])]
    nomes += [s.get("arquivo") for s in MAPA.get("iphones", [])]
    if MAPA.get("cartao"):
        nomes.append(MAPA["cartao"].get("foto", FOTO_PERFIL))
    if MAPA.get("musica"):
        nomes.append(MAPA["musica"].get("arquivo"))
    arqs = []
    for a in nomes:
        if a and a not in [x for x, _ in arqs]:
            try:
                _resolve(a); ok = True
            except SystemExit:
                ok = False
            arqs.append((a, ok))

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        try:
            return compoe(quadro_base(n), t, legendas, n)
        except SystemExit as e:
            return _falta_arquivo(e.code)

    out = SB.gerar(EDIT, "iPhone", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if GLOWS and not (EDIT / "masks" / "out").exists():
        sys.exit("tem logo neon atrás da cabeça: rode mascaras.py antes")
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
    prenorm = EDIT / f"{modo}_iphone.prenorm.mp4"
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
        for e in IPHONES:   # fecha o ffmpeg de quem já saiu
            if t >= e.t1:
                e.fecha()
        k += 1
        if k % 300 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_iphone.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
