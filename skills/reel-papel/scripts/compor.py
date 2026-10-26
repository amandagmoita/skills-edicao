"""compor.py — monta o Reel no estilo "papel", quadro a quadro, a partir do mapa.json.

Estilo: versão 2 do Reel do @justyn.ai ("I didn't edit a single second of this video. Claude did."),
analisada em referencia/referencias-estilo.md. Cada frase vira, no mesmo segundo, um
objeto do mundo da edição desenhado como papel na paleta do cenário: tíquete de impressora numerado,
régua, teclas caindo, tira de filme marcada à caneta, capa de revista, celular, widget que apaga itens,
conta-gotas, mural de cards, letreiro com o vídeo dentro das letras. Legenda karaokê serifada em caixa
reta, que obedece aos comandos (escada, gigante). Transição só quando ilustra a palavra.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_papel.mp4 | final_papel.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov / base_final.mov, masks/out/ (mascaras.py), ícones em <skill>/assets/icones/

Camadas de um quadro, de baixo pra cima:
  base → abertura (zoom) → cor (P&B, escuro, quente) → títulos atrás da cabeça (pessoa na frente)
  → tela cheia (grade, cartela, celular, revista, letreiro, feed, capítulos) → objetos por cima
  → transição (íris, persiana, borrão) → legenda
"""

from __future__ import annotations

import argparse
import functools
import itertools
import json
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # nome, @, cor de destaque, foto, produto e link do criador

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
ANT = 0.10          # objetos entram 0,1 s antes da palavra (na referência entram colados na fala)

# ================================================================ linha do tempo
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
    sys.exit(f"medidas.json tem {len(MED)} tomadas e o corte tem {_NG}: rode medir.py de novo")


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


def grupo_em(t: float) -> int:
    g = 0
    for k in range(_NG):
        if OFF[k] <= t + 1e-6:
            g = k
    return g


def topo(t: float) -> int:
    return MED[grupo_em(t)]["topo"]


def rosto(t: float) -> list[int]:
    return MED[grupo_em(t)]["rosto"]


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    return 1 - (1 - cl(x)) ** 3


def ease_in(x: float) -> float:
    return cl(x) ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def mola(x: float, c1: float = 1.7) -> float:
    """back-out: passa um pouco do lugar e volta."""
    x = cl(x)
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ================================================================ paleta (sai do cenário)
def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


PALETAS = {
    # a da referência: parede verde da sala dele, papel creme, latão das arandelas, caneta rosa
    "floresta": {"escuro": "#173328", "caixa": "#1C362E", "claro": "#F2ECE0", "destaque": "#C3A386",
                 "caneta": "#E0708C"},
    # cenário de exemplo (padrão): parede oliva, sofá creme, dourado de brinco/espelho, vermelho de unha
    "oliva": {"escuro": "#2C2A1E", "caixa": "#34311F", "claro": "#F2ECE0", "destaque": "#C9A66B",
              "caneta": "#E0313B"},
}
_pal = MAPA.get("paleta", "oliva")
_pal = {**PALETAS["oliva"], **(PALETAS[_pal] if isinstance(_pal, str) else _pal)}
ESCURO, CAIXA, CLARO, DESTAQUE, CANETA = (hexa(_pal[k]) for k in ("escuro", "caixa", "claro", "destaque", "caneta"))


def mistura(c1, c2, k: float) -> tuple:
    return tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))


APAGADO = mistura(CAIXA, CLARO, 0.38)     # palavra da legenda ainda não falada
TINTA = mistura(ESCURO, (0, 0, 0), 0.25)  # texto escuro sobre papel

# ================================================================ fontes
_SUP = "/System/Library/Fonts/Supplemental/"
FONTES = {   # tipo: (arquivo, índice, nome esperado) — conferido no início (fonte errada cai em outra calada)
    "titulo": (_SUP + "Didot.ttc", 0, ("Didot", "Regular")),
    "serifa": (_SUP + "Bodoni 72.ttc", 0, ("Bodoni 72", "Book")),
    "italico": (_SUP + "Bodoni 72.ttc", 1, ("Bodoni 72", "Book Italic")),
    "legenda": (_SUP + "Bodoni 72.ttc", 0, ("Bodoni 72", "Book")),
    "mono": ("/System/Library/Fonts/Menlo.ttc", 1, ("Menlo", "Bold")),
    "mono_fino": ("/System/Library/Fonts/Menlo.ttc", 0, ("Menlo", "Regular")),
    "sans": ("/System/Library/Fonts/Avenir Next.ttc", 8, ("Avenir Next", "Heavy")),
    "ui": ("/System/Library/Fonts/Avenir Next.ttc", 2, ("Avenir Next", "Demi Bold")),
    "ui_fino": ("/System/Library/Fonts/Avenir Next.ttc", 5, ("Avenir Next", "Medium")),
    "mao": (_SUP + "Bradley Hand Bold.ttf", 0, ("Bradley Hand", "Bold")),
}
for _k, (_arq, _i, _nome) in FONTES.items():
    if ImageFont.truetype(_arq, 20, index=_i).getname() != _nome:
        sys.exit(f"fonte {_k}: esperava {_nome} em {_arq}[{_i}]")
# estreitamento horizontal: a referência usa serifa alta e estreita (Didot e Bodoni são largas)
COND = {"titulo": 0.78, "legenda": 0.9, "serifa": 0.92, "italico": 0.92}


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, idx, _ = FONTES[tipo]
    return ImageFont.truetype(arq, size, index=idx)


@functools.lru_cache(maxsize=4096)
def palavra_img(txt: str, tipo: str, size: int, cor: tuple) -> tuple[Image.Image, int]:
    """Texto numa imagem justa na horizontal, com a linha de base em y = ascent. Devolve (img, ascent)."""
    f = F(tipo, size)
    asc, desc = f.getmetrics()
    pad = int(size * 0.12)
    w = int(f.getlength(txt)) + 2 * pad
    im = Image.new("RGBA", (max(1, w), asc + desc), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, asc), txt, font=f, fill=cor + (255,), anchor="ls")
    k = COND.get(tipo, 1.0)
    if k != 1.0:
        im = im.resize((max(1, int(im.width * k)), im.height), Image.LANCZOS)
    return im, asc


def larg_txt(txt: str, tipo: str, size: int) -> float:
    return F(tipo, size).getlength(txt) * COND.get(tipo, 1.0)


# ================================================================ utilidades de desenho
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


def sombra(im: Image.Image, raio: int = 16, forca: float = 0.32, dy: int = 9) -> Image.Image:
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


def com_sombra(dest: Image.Image, im: Image.Image, x: float, y: float, **kw) -> None:
    s = sombra(im, **kw)
    m = (s.width - im.width) // 2
    cola(dest, s, x - m, y - m)


def ret(w: int, h: int, r: int, cor, borda=None, larg_borda: int = 2) -> Image.Image:
    im = Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, int(w) - 1, int(h) - 1), radius=max(0, min(r, int(h) // 2, int(w) // 2)),
                                         fill=cor, outline=borda, width=larg_borda if borda else 0)
    return im


def gira(im: Image.Image, graus: float) -> Image.Image:
    return im if abs(graus) < 0.05 else im.rotate(graus, resample=Image.BICUBIC, expand=True)


def escala(im: Image.Image, k: float) -> Image.Image:
    if abs(k - 1) < 1e-3:
        return im
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BILINEAR)


def cobre(im: Image.Image, w: int, h: int, foco: tuple[float, float] = (0.5, 0.42)) -> Image.Image:
    """Redimensiona cobrindo w×h (corta o excesso em volta do ponto de foco, em fração)."""
    k = max(w / im.width, h / im.height)
    nw, nh = max(w, int(im.width * k + 0.5)), max(h, int(im.height * k + 0.5))
    im = im.resize((nw, nh), Image.BILINEAR)
    x = int(cl(foco[0] * nw - w / 2, 0, nw - w))
    y = int(cl(foco[1] * nh - h / 2, 0, nh - h))
    return im.crop((x, y, x + w, y + h))


def circulo_img(im: Image.Image, d: int, anel=None) -> Image.Image:
    im = cobre(im, d, d).convert("RGBA")
    m = Image.new("L", (d, d), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d - 1, d - 1), fill=255)
    im.putalpha(m)
    if anel:
        ImageDraw.Draw(im).ellipse((1, 1, d - 2, d - 2), outline=anel, width=max(2, d // 22))
    return im


def mascara_bloco(w: int, h: int, k: float) -> Image.Image:
    """Revela de baixo pra cima: as letras sobem de dentro de uma fenda (máscara)."""
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rectangle((0, 0, w, h), fill=255)
    return m


def sobe_de_mascara(dest: Image.Image, im: Image.Image, x: float, y: float, k: float) -> None:
    """Cola im em (x, y) entrando de baixo pra cima por uma máscara do tamanho dela (k = 0..1)."""
    if k <= 0:
        return
    dy = int((1 - ease_out(k)) * im.height * 1.05)
    vis = im.crop((0, 0, im.width, max(1, im.height - dy)))
    cola(dest, vis, x, y + dy)


def traco_parcial(d: ImageDraw.ImageDraw, pts: list[tuple[float, float]], k: float, cor, larg: int) -> None:
    """Desenha a fração k de uma polilinha (traço de caneta sendo feito)."""
    if k <= 0 or len(pts) < 2:
        return
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    alvo = sum(segs) * cl(k)
    feito = [pts[0]]
    for i, s in enumerate(segs):
        if alvo >= s:
            feito.append(pts[i + 1])
            alvo -= s
        else:
            f = alvo / s if s else 0
            feito.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
            break
    d.line(feito, fill=cor, width=larg, joint="curve")
    r = larg / 2
    for p in (feito[0], feito[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=cor)


def elipse_mao(cx, cy, rx, ry, seed=0, voltas=1.12, n=90) -> list[tuple[float, float]]:
    """Elipse de caneta: começa no alto, passa um pouco do início e treme de leve."""
    rng = random.Random(seed)
    fase = [rng.uniform(0, 6.28) for _ in range(3)]
    pts = []
    for i in range(n + 1):
        a = -math.pi / 2 - 0.35 + 2 * math.pi * voltas * i / n
        ruido = 1 + 0.025 * math.sin(3 * a + fase[0]) + 0.018 * math.sin(5 * a + fase[1])
        deriva = 1 + 0.06 * i / n
        pts.append((cx + rx * ruido * deriva * math.cos(a), cy + ry * ruido * math.sin(a)))
    return pts


def desfoque_eixo(im: Image.Image, r: int, eixo: int) -> Image.Image:
    """Borrão de movimento (média móvel) num eixo: 1 = horizontal, 0 = vertical."""
    if r < 2:
        return im
    a = np.asarray(im.convert("RGB"), np.float32)
    pad = [(0, 0), (0, 0), (0, 0)]
    pad[eixo] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=eixo)
    if eixo == 1:
        out = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    else:
        out = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")


def timecode(t: float) -> str:
    q = int(round((t % 1) * 30))
    s = int(t)
    return f"00:00:{s:02d}:{q:02d}"


def tc_curto(t: float) -> str:
    return f"00:{int(t):02d}.{int((t % 1) * 100):02d}"


# ================================================================ base: leitura de quadros
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    n = max(0, min(N_FRAMES - 1, n))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw[: W * H * 3]).convert("RGBA")


@functools.lru_cache(maxsize=96)
def quadro_cache(n: int) -> Image.Image:
    return quadro_base(n)


def quadro_em(t: float) -> Image.Image:
    return quadro_cache(max(0, min(N_FRAMES - 1, round(t * FPS))))


def mascara(n: int) -> Image.Image | None:
    p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
    if not p.exists():
        return None
    m = Image.open(p).convert("L")
    if m.size != (W, H):
        m = m.resize((W, H), Image.BILINEAR)
    return m.filter(ImageFilter.GaussianBlur(1.2))


def rosto_img(t: float, d: int) -> Image.Image:
    """Avatar redondo da pessoa, tirado do próprio vídeo (pra comentário, seguir, widget)."""
    x, y, w, h = rosto(t)
    fr = quadro_em(t)
    m = int(w * 0.35)
    crop = fr.crop((max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)))
    return circulo_img(crop, d)


def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    return p if p.is_absolute() else (PASTA / p).resolve()


@functools.lru_cache(maxsize=64)
def quadro_arquivo(arq: str, t: float) -> Image.Image:
    p = _resolve(arq)
    if not p.exists():
        sys.exit(f"não achei {p}")
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return Image.open(p).convert("RGBA")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-f", "image2pipe",
                          "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    import io
    return Image.open(io.BytesIO(raw)).convert("RGBA")


class LeitorVideo:
    """Um ffmpeg por vídeo que roda dentro de um elemento, aberto no 1º quadro em que ele aparece."""

    def __init__(self, arq: str, inicio: float, w: int, h: int, t0: float):
        self.arq, self.inicio, self.w, self.h, self.t0 = _resolve(arq), inicio, w, h, t0
        if not self.arq.exists():
            sys.exit(f"não achei {self.arq}")
        self.proc, self.ultimo, self.k = None, None, 0

    def vf(self) -> str:
        return (f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase:flags=bilinear,"
                f"crop={self.w}:{self.h},fps={FPS_NUM}/{FPS_DEN}")

    def quadro(self, t: float) -> Image.Image:
        if ARGS.so_quadros or ARGS.storyboard or self.arq.suffix.lower() in (".png", ".jpg", ".jpeg"):
            return cobre(quadro_arquivo(str(self.arq), round(self.inicio + max(0.0, t - self.t0), 2)), self.w, self.h)
        if self.proc is None:
            self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{self.inicio:.3f}", "-i", str(self.arq),
                                          "-an", "-vf", self.vf(), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                         stdout=subprocess.PIPE)
        alvo = int((t - self.t0) * FPS)
        tam = self.w * self.h * 3
        while self.k <= alvo:
            buf = self.proc.stdout.read(tam)
            if len(buf) == tam:
                self.ultimo = Image.frombytes("RGB", (self.w, self.h), buf).convert("RGBA")
            self.k += 1
        return self.ultimo if self.ultimo is not None else Image.new("RGBA", (self.w, self.h), ESCURO + (255,))

    def fecha(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc = None


# ================================================================ elementos
class El:
    camada = "sobre"        # cor | atras | tela | sobre
    precisa_mascara = False

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"]) - spec.get("antecipa", ANT)
        if isinstance(spec["em"], list) and spec.get("antecipa", ANT) < 0.2:
            self.t0 = max(self.t0, OFF[int(spec["em"][1])])   # não antecipa por cima do corte
        self.t1 = T(spec["ate"], True) if spec.get("ate") is not None else fim_tomada(spec["em"])
        if self.t1 - self.t0 < 0.5:
            print(f"ATENÇÃO {spec.get('tipo')} em {self.t0:.2f}s fica só {self.t1 - self.t0:.2f}s na tela")
        self.topo = topo(self.t0 + 0.15)
        self.leitores: list[LeitorVideo] = []

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def k_in(self, t: float, d: float = 0.25) -> float:
        return cl((t - self.t0) / d)

    def k_out(self, t: float, d: float = 0.18) -> float:
        return cl((t - (self.t1 - d)) / d)

    def sons(self) -> list[tuple[float, str, float]]:
        return []

    def fecha(self) -> None:
        for l in self.leitores:
            l.fecha()

    def resumo(self) -> str:
        return ""


# ---------------------------------------------------------------- título gigante atrás da cabeça
class Titulo(El):
    """Palavra-tese gigante em serifa alta, ATRÁS da cabeça (a pessoa fica na frente das letras).
    spec: linhas, fonte (titulo|serifa), destaque [palavras em itálico dourado], destaque_em, anim
    (mascara|letras), tamanho, y (base da última linha; padrão: topo da cabeça + 30% da letra)."""
    camada = "atras"
    precisa_mascara = True

    def __init__(self, spec):
        super().__init__(spec)
        self.fonte = spec.get("fonte", "titulo")
        self.anim = spec.get("anim", "mascara")
        self.dest = {limpa(p) for p in spec.get("destaque", [])}
        self.td = T(spec["destaque_em"]) - 0.05 if spec.get("destaque_em") else None
        tam = spec.get("tamanho", 250 if self.fonte == "titulo" else 150)
        while max(self._larg(l, tam) for l in spec["linhas"]) > W - 90 and tam > 60:
            tam -= 6
        self.tam = tam
        self.y_base = spec.get("y", self.topo + int(tam * 0.32))

    def _tipo(self, p: str) -> str:
        return "italico" if limpa(p) in self.dest else self.fonte

    def _larg(self, linha: str, tam: int) -> float:
        ps = linha.split()
        esp = F(self.fonte, tam).getlength(" ") * COND.get(self.fonte, 1) * (1.25 if self.fonte == "titulo" else 1)
        return sum(larg_txt(p, self._tipo(p), tam if self._tipo(p) == self.fonte else int(tam * 0.95)) for p in ps) + esp * (len(ps) - 1)

    def desenha(self, fr: Image.Image, t: float) -> None:
        tam = self.tam
        lh = int(tam * (0.86 if self.fonte == "titulo" else 1.0))
        linhas = self.spec["linhas"]
        esp = F(self.fonte, tam).getlength(" ") * COND.get(self.fonte, 1) * (1.25 if self.fonte == "titulo" else 1)
        for li, linha in enumerate(linhas):
            base = self.y_base - (len(linhas) - 1 - li) * lh
            x = (W - self._larg(linha, tam)) / 2
            for pi, p in enumerate(linha.split()):
                tipo = self._tipo(p)
                destaque = tipo == "italico"
                tm = tam if not destaque else int(tam * 0.95)
                cor = DESTAQUE if destaque else CLARO
                img, asc = palavra_img(p, tipo, tm, cor)
                larg = larg_txt(p, tipo, tm)
                if destaque and self.td is not None:
                    t_ent = self.td
                else:
                    t_ent = self.t0 + 0.1 * li + 0.06 * pi
                if self.anim == "letras" and not destaque:
                    # letra por letra (como o NEVER): cada letra aparece seca, 0,05 s uma da outra
                    n = max(1, int((t - t_ent) / 0.05) + 1) if t >= t_ent else 0
                    sub = p[:n]
                    if sub:
                        im2, a2 = palavra_img(sub, tipo, tm, cor)
                        cola(fr, im2, x - tm * 0.12 * COND.get(tipo, 1), base - a2)
                else:
                    sobe_de_mascara(fr, img, x - tm * 0.12 * COND.get(tipo, 1), base - asc, (t - t_ent) / 0.22)
                x += larg + esp

    def sons(self):
        s = [(self.t0, "impacto", -19)]
        if self.td is not None:
            s.append((self.td, "ding", -22))
        return s

    def resumo(self):
        return "TÍTULO " + " / ".join(self.spec["linhas"])


# ---------------------------------------------------------------- grade (calendário de quadros)
class Grade(El):
    """Tela chapada com uma grade de casas numeradas que enchem com quadros do próprio vídeo; as
    palavras faladas sobem como título; no fim a câmera mergulha numa casa e ela vira a tela cheia.
    spec: celulas (10), colunas (5), quadros ("tomadas" | lista de segundos), zoom (s antes do fim)."""
    camada = "tela"

    def __init__(self, spec):
        super().__init__(spec)
        self.n = spec.get("celulas", 10)
        self.cols = spec.get("colunas", 5)
        self.rows = math.ceil(self.n / self.cols)
        self.cw = int((W - 120 - (self.cols - 1) * 14) / self.cols)
        self.ch = int(self.cw * 16 / 9)
        gh = self.rows * self.ch + (self.rows - 1) * 14
        self.gx, self.gy = 60, int(H * 0.56 - gh / 2)
        q = spec.get("quadros", "tomadas")
        if q == "tomadas":
            gs = list(range(1, _NG)) or [0]
            ts = [(OFF[g] + OFF[g + 1]) / 2 for g in gs]
        else:
            ts = [float(v) for v in q]
        ts = (ts * (self.n // max(1, len(ts)) + 1))[: self.n]
        self.thumbs = [cobre(quadro_em(tt), self.cw, self.ch) for tt in ts]
        self.dz = spec.get("zoom", 0.32)
        self.palavras = [w for w in WORDS if self.t0 + ANT - 0.05 <= w["s"] < self.t1 - 0.05]

    def celula(self, i: int) -> tuple[int, int]:
        r, c = divmod(i, self.cols)
        return self.gx + c * (self.cw + 14), self.gy + r * (self.ch + 14)

    def canvas(self, fr: Image.Image, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), ESCURO + (255,))
        d = ImageDraw.Draw(cv)
        ini, fim = self.t0 + 0.12, self.t1 - self.dz - 0.05
        cheias = int(cl((t - ini) / max(0.1, fim - ini)) * self.n + 0.999) if t >= ini else 0
        vazio = mistura(ESCURO, CLARO, 0.07)
        for i in range(self.n):
            x, y = self.celula(i)
            if i < cheias:
                im = self.thumbs[i] if i < self.n - 1 or t < self.t1 - self.dz else cobre(fr, self.cw, self.ch)
                cv.alpha_composite(im, (x, y))
                if i == cheias - 1:
                    d.rectangle((x - 2, y - 2, x + self.cw + 1, y + self.ch + 1), outline=DESTAQUE + (255,), width=4)
            else:
                d.rectangle((x, y, x + self.cw, y + self.ch), fill=vazio + (255,))
                d.text((x + self.cw / 2, y + self.ch / 2), f"{i + 1:02d}", font=F("mono_fino", 26),
                       fill=mistura(ESCURO, CLARO, 0.28) + (255,), anchor="mm")
        # título: as palavras faladas sobem uma a uma, em linhas, acima da grade
        tam = 118
        linhas, cur = [], []
        for w in self.palavras:
            tst = cur + [w]
            if cur and sum(larg_txt(x["t"].upper().strip(",.?!"), "titulo", tam) + 26 for x in tst) > W - 140:
                linhas.append(cur)
                cur = [w]
            else:
                cur = tst
        if cur:
            linhas.append(cur)
        lh = int(tam * 0.98)
        y_base = self.gy - 40 - (len(linhas) - 1) * lh
        for li, ln in enumerate(linhas):
            lw = sum(larg_txt(x["t"].upper().strip(",.?!"), "titulo", tam) + 26 for x in ln) - 26
            x = (W - lw) / 2
            for w in ln:
                txt = w["t"].upper().strip(",.?!")
                img, asc = palavra_img(txt, "titulo", tam, CLARO)
                sobe_de_mascara(cv, img, x - tam * 0.12 * COND["titulo"], y_base + li * lh - asc, (t - w["s"] + 0.06) / 0.18)
                x += larg_txt(txt, "titulo", tam) + 26
        return cv

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        cv = self.canvas(fr, t)
        kz = cl((t - (self.t1 - self.dz)) / self.dz)
        if kz <= 0:
            return cv
        # mergulho na última casa: o retângulo de recorte vai da tela inteira até a casa
        k = ease_in_out(kz)
        x, y = self.celula(self.n - 1)
        x0, y0, x1, y1 = 0 + (x - 0) * k, 0 + (y - 0) * k, W + (x + self.cw - W) * k, H + (y + self.ch - H) * k
        im = cv.crop((int(x0), int(y0), int(x1), int(y1))).resize((W, H), Image.BILINEAR)
        return fr if kz >= 0.999 else im

    def sons(self):
        s = [(self.t0, "whoosh", -20)]
        ini, fim = self.t0 + 0.12, self.t1 - self.dz - 0.05
        for i in range(self.n):
            s.append((ini + (fim - ini) * i / self.n, "tecla", -24))
        s.append((self.t1 - self.dz, "whoosh_sobe", -19))
        return s

    def resumo(self):
        return f"GRADE {self.n} casas"


# ---------------------------------------------------------------- tíquete de impressora numerado
_N_TIQ = itertools.count(1)


class Tiquete(El):
    """Papel de impressora que sai de uma fenda acima da cabeça: rótulo + número, hora, texto em
    máquina de escrever e TOTAL. Volta sugado pra fenda no fim. spec: rotulo, numero, para, texto,
    total, cps (letras/s), y (fenda)."""

    LARG = 540

    def __init__(self, spec):
        super().__init__(spec)
        self.num = spec.get("numero", next(_N_TIQ))
        self.rotulo = spec.get("rotulo", "INSTRUÇÃO")
        self.para = spec.get("para", "PARA O CLAUDE")
        self.texto = spec["texto"].upper()
        self.total = spec.get("total")
        self.y_fenda = spec.get("y", self.topo - 40)
        f = F("mono", 40)
        self.linhas = []
        cur = ""
        for p in self.texto.split():
            tst = (cur + " " + p).strip()
            if f.getlength(tst) <= self.LARG - 56 or not cur:
                cur = tst
            else:
                self.linhas.append(cur)
                cur = p
        if cur:
            self.linhas.append(cur)
        self.ta = self.t0 + 0.32
        cps = spec.get("cps", 20)
        nch = sum(len(l) for l in self.linhas)
        disp = max(0.4, (self.t1 - 0.75) - self.ta)
        self.cps = max(cps, nch / disp)
        self.t_tot = self.ta + nch / self.cps + 0.12
        self.papel = self._papel()

    def _papel(self) -> Image.Image:
        lw = self.LARG
        h = 112 + len(self.linhas) * 50 + (64 if self.total else 0) + 22
        im = Image.new("RGBA", (lw, h), CLARO + (255,))
        d = ImageDraw.Draw(im)
        tinta = TINTA + (255,)
        fraco = mistura(CLARO, TINTA, 0.55) + (255,)
        d.text((28, 30), self.rotulo, font=F("mono", 25), fill=tinta, anchor="lm")
        d.text((lw - 28, 30), f"{self.num:02d}" if isinstance(self.num, int) else str(self.num), font=F("mono", 25),
               fill=tinta, anchor="rm")
        d.text((28, 62), tc_curto(self.t0 + ANT), font=F("mono_fino", 19), fill=fraco, anchor="lm")
        d.text((lw - 28, 62), self.para, font=F("mono_fino", 19), fill=fraco, anchor="rm")
        for x in range(28, lw - 28, 14):
            d.line((x, 86, x + 7, 86), fill=fraco, width=2)
        # dente de serra no alto (papel rasgado)
        a = im.getchannel("A")
        da = ImageDraw.Draw(a)
        for x in range(0, lw, 16):
            da.polygon([(x, 0), (x + 16, 0), (x + 8, 7)], fill=0)
        im.putalpha(a)
        return im

    def _papel_ate(self, t: float) -> tuple[Image.Image, int]:
        """Papel com o texto digitado até t, e a altura que já saiu da fenda."""
        im = self.papel.copy()
        d = ImageDraw.Draw(im)
        tinta = TINTA + (255,)
        n = int((t - self.ta) * self.cps) if t >= self.ta else 0
        alt = 104
        alt = int(104 * ease_out((t - self.t0 - 0.1) / 0.2))
        for i, l in enumerate(self.linhas):
            if n <= 0:
                break
            y = 104 + i * 50
            d.text((28, y + 24), l[:n], font=F("mono", 40), fill=tinta, anchor="lm")
            if n < len(l) and int(t * 4) % 2 == 0:
                cx = 28 + F("mono", 40).getlength(l[:n])
                d.rectangle((cx + 2, y + 6, cx + 20, y + 42), fill=tinta)
            alt = max(alt, 104 + i * 50 + int(50 * ease_out(cl((t - (self.ta + sum(len(x) for x in self.linhas[:i]) / self.cps)) / 0.1))))
            n -= len(l)
        if self.total and t >= self.t_tot:
            y = 112 + len(self.linhas) * 50
            fraco = mistura(CLARO, TINTA, 0.55) + (255,)
            for x in range(28, self.LARG - 28, 14):
                d.line((x, y, x + 7, y), fill=fraco, width=2)
            d.text((28, y + 32), "TOTAL", font=F("mono", 22), fill=tinta, anchor="lm")
            d.text((self.LARG - 28, y + 32), self.total.upper(), font=F("mono", 22), fill=tinta, anchor="rm")
            alt = max(alt, int(y + 64 * ease_out((t - self.t_tot) / 0.12) + 22))
        else:
            alt = max(alt, 104 + 8)
        return im, min(alt + 14, im.height)

    def desenha(self, fr: Image.Image, t: float) -> None:
        kf = ease_out(self.k_in(t, 0.14))
        ks = self.k_out(t, 0.3)
        im, alt = self._papel_ate(t)
        alt = int(alt * (1 - ease_in(cl(ks / 0.75))))
        cx = W / 2
        fy = self.y_fenda
        # fenda (a "impressora"): barra escura com tracejado e um ponto dourado
        fw = int((self.LARG + 70) * (0.6 + 0.4 * kf) * (1 - 0.4 * cl((ks - 0.7) / 0.3)))
        fa = kf * (1 - cl((ks - 0.75) / 0.25))
        if fa > 0.02:
            fenda = ret(fw, 30, 15, ESCURO + (255,))
            dd = ImageDraw.Draw(fenda)
            for x in range(24, fw - 50, 18):
                dd.line((x, 15, x + 9, 15), fill=mistura(ESCURO, CLARO, 0.35) + (255,), width=2)
            dd.ellipse((fw - 34, 9, fw - 22, 21), fill=DESTAQUE + (255,))
            cola(fr, com_alfa(fenda, fa), cx - fw / 2, fy - 4)
        if alt > 4:
            vis = im.crop((0, 0, im.width, alt))
            com_sombra(fr, vis, cx - im.width / 2, fy - alt, raio=12, forca=0.28, dy=6)

    def sons(self):
        s = [(self.t0 + 0.05, "impressora", -21)]
        n = 0
        for l in self.linhas:
            for ch in l:
                if ch != " ":
                    s.append((self.ta + n / self.cps, "tecla", -27 - 3 * (n % 3)))
                n += 1
        if self.total:
            s.append((self.t_tot, "pop", -18))
        s.append((self.t1 - 0.3, "impressora", -24))
        return s

    def resumo(self):
        return f"TÍQUETE {self.rotulo} {self.num}: {self.texto}"


# ---------------------------------------------------------------- régua (temperatura, tamanho…)
class Regua(El):
    """Régua escura que desce no alto e corre de um valor ao outro; o valor na agulha fica dourado.
    spec: valores [..], efeito (quente|frio|escuro|null: muda a imagem junto com a régua), y."""

    def __init__(self, spec):
        super().__init__(spec)
        self.valores = [str(v) for v in spec["valores"]]
        self.efeito = spec.get("efeito")
        self.y = spec.get("y", 150)
        self.passo = max(150, int(max(F("mono", 34).getlength(v) for v in self.valores) + 50))

    def progresso(self, t: float) -> float:
        return ease_in_out((t - self.t0 - 0.15) / max(0.3, self.t1 - self.t0 - 0.45))

    def filtro(self, fr: Image.Image, t: float) -> Image.Image:
        if not self.efeito:
            return fr
        k = self.progresso(t)
        if t >= self.t1:
            k = 1.0
        return aplica_cor(fr, self.efeito, k)

    def desenha(self, fr: Image.Image, t: float) -> None:
        pw, ph = 680, 118
        ki, ko = ease_out(self.k_in(t, 0.16)), ease_in(self.k_out(t, 0.14))
        y = self.y - (1 - ki) * 200 - ko * 220
        painel = ret(pw, ph, 14, ESCURO + (245,), borda=mistura(ESCURO, CLARO, 0.2) + (255,))
        d = ImageDraw.Draw(painel)
        k = self.progresso(t)
        pos = k * self.passo * (len(self.valores) - 1)
        cx = pw / 2
        claro = mistura(ESCURO, CLARO, 0.8) + (255,)
        fraco = mistura(ESCURO, CLARO, 0.4) + (255,)
        for j in range(-40, 40 * len(self.valores)):
            x = cx + j * (self.passo / 10) - pos
            if not 12 < x < pw - 12:
                continue
            maior = j % 10 == 0
            d.line((x, 14, x, 14 + (24 if maior else 12)), fill=claro if maior else fraco, width=2)
        for i, v in enumerate(self.valores):
            x = cx + i * self.passo - pos
            if 30 < x < pw - 30:
                perto = abs(x - cx) < self.passo / 2
                d.text((x, 80), v, font=F("mono", 34), fill=(DESTAQUE + (255,)) if perto else claro, anchor="mm")
        d.polygon([(cx - 9, 6), (cx + 9, 6), (cx, 20)], fill=DESTAQUE + (255,))
        d.line((cx, 6, cx, 52), fill=DESTAQUE + (255,), width=3)
        com_sombra(fr, painel, (W - pw) / 2, y, raio=10, forca=0.3, dy=5)

    def sons(self):
        return [(self.t0, "whoosh_curto", -20)] + [(self.t0 + 0.2 + i * 0.09, "tecla", -26) for i in range(8)]

    def resumo(self):
        return "RÉGUA " + " → ".join(self.valores) + (f" ({self.efeito})" if self.efeito else "")


def aplica_cor(fr: Image.Image, modo: str, k: float) -> Image.Image:
    if k <= 0.001:
        return fr
    a = np.asarray(fr.convert("RGB"), np.float32)
    if modo == "pb":
        g = a @ np.array([0.299, 0.587, 0.114], np.float32)
        g = np.clip((g - 128) * 1.12 + 128, 0, 255)
        b = np.repeat(g[..., None], 3, axis=2)
    elif modo == "escuro":
        g = a @ np.array([0.299, 0.587, 0.114], np.float32)
        b = a * 0.45 + g[..., None] * 0.55
        b = b * 0.62 * np.array([0.96, 1.0, 1.06], np.float32)
    elif modo == "quente":
        b = a * np.array([1.10, 1.02, 0.84], np.float32) + np.array([10, 4, -6], np.float32)
    elif modo == "frio":
        b = a * np.array([0.9, 0.98, 1.1], np.float32)
    else:
        sys.exit(f"cor: modo {modo} não existe (pb | escuro | quente | frio)")
    out = a + (b - a) * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")


class Cor(El):
    """Troca de cor seca na palavra (escuro, P&B, quente, frio). spec: modo."""
    camada = "cor"

    def __init__(self, spec):
        spec.setdefault("antecipa", 0.0)
        super().__init__(spec)
        self.modo = spec["modo"]

    def filtro(self, fr, t):
        return aplica_cor(fr, self.modo, 1.0)

    def sons(self):
        return [(self.t0, "whoosh_curto", -22)]

    def resumo(self):
        return f"COR {self.modo}"


# ---------------------------------------------------------------- conta-gotas + paleta hex
class Paleta(El):
    """Conta-gotas voa pela imagem pegando cores; cada uma cai num cartão com o código hex.
    spec: pontos [[x, y], ...] em fração da tela (padrão: parede, cabelo, rosto, roupa), x, y do cartão."""

    def __init__(self, spec):
        super().__init__(spec)
        x, y, w, h = rosto(self.t0 + 0.1)
        self.pontos = [tuple(p) for p in spec.get("pontos", [])] or [
            (0.18, 0.30), ((x + w * 0.5) / W, (y - h * 0.25) / H), ((x + w * 0.3) / W, (y + h * 0.6) / H),
            (0.5, 0.80), (0.85, 0.45)]
        self.cores: dict[int, tuple] = {}
        self.dt = max(0.18, (self.t1 - self.t0 - 0.5) / len(self.pontos))

    def desenha(self, fr: Image.Image, t: float) -> None:
        ki, ko = ease_out(self.k_in(t, 0.2)), self.k_out(t, 0.15)
        cw, chh = 190, 64 + len(self.pontos) * 62
        cx, cy = 40 - (1 - ki) * 260 - ko * 300, H * 0.27
        card = ret(cw, chh, 18, CLARO + (255,))
        d = ImageDraw.Draw(card)
        d.text((18, 26), "PALETA", font=F("mono", 17), fill=mistura(CLARO, TINTA, 0.55) + (255,), anchor="lm")
        for i in range(3):
            d.ellipse((cw - 50 + i * 12, 22, cw - 44 + i * 12, 28), fill=mistura(CLARO, TINTA, 0.5) + (255,))
        for i, (px, py) in enumerate(self.pontos):
            tp = self.t0 + 0.25 + i * self.dt
            if t >= tp + 0.12:
                if i not in self.cores:
                    self.cores[i] = fr.convert("RGB").resize((W // 8, H // 8)).getpixel((int(px * W / 8), int(py * H / 8)))
                c = self.cores[i]
                y = 56 + i * 62
                d.rounded_rectangle((16, y, 66, y + 50), radius=8, fill=c + (255,))
                d.text((80, y + 25), "#%02X%02X%02X" % c, font=F("mono", 19), fill=TINTA + (255,), anchor="lm")
        com_sombra(fr, card, cx, cy, raio=12, forca=0.3, dy=6)
        # o conta-gotas: vai de um ponto ao outro
        if ko < 0.5:
            i = int(cl((t - self.t0 - 0.05) / self.dt, 0, len(self.pontos) - 1e-6))
            a = self.pontos[max(0, i - 1)] if i > 0 else (0.5, 0.15)
            b = self.pontos[i]
            k = ease_in_out((t - (self.t0 + 0.05 + i * self.dt)) / (self.dt * 0.7))
            px, py = (a[0] + (b[0] - a[0]) * k) * W, (a[1] + (b[1] - a[1]) * k) * H
            gota = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
            dg = ImageDraw.Draw(gota)
            dg.line((18, 72, 66, 24), fill=(30, 30, 30, 255), width=12)
            dg.line((60, 30, 76, 14), fill=(30, 30, 30, 255), width=20)
            dg.ellipse((6, 60, 30, 84), outline=CLARO + (255,), width=4)
            cola(fr, gota, px - 18, py - 78)

    def sons(self):
        return [(self.t0, "whoosh_curto", -21)] + [(self.t0 + 0.37 + i * self.dt, "pop", -19) for i in range(len(self.pontos))]

    def resumo(self):
        return f"PALETA {len(self.pontos)} cores"


# ---------------------------------------------------------------- cards que flutuam (Reels)
class Cards(El):
    """Cards verticais (Reels do criador, prints) nascem pequenos atrás da parede e crescem até uma fileira
    em cima da cabeça, levemente tortos, boiando. spec: itens [{arquivo, inicio, rotulo, em}], largura."""

    def __init__(self, spec):
        super().__init__(spec)
        self.cw = spec.get("largura", 220)
        self.ch = int(self.cw * 16 / 9)
        rng = random.Random(len(spec["itens"]) * 7 + int(self.t0 * 10))
        self.itens = []
        n = len(spec["itens"])
        gap = 28
        tot = n * self.cw + (n - 1) * gap
        for i, it in enumerate(spec["itens"]):
            te = T(it["em"]) - ANT if it.get("em") else self.t0 + i * 0.12
            l = LeitorVideo(it["arquivo"], float(it.get("inicio", 1.0)), self.cw, self.ch, te)
            self.leitores.append(l)
            self.itens.append({"te": te, "leitor": l, "rotulo": it.get("rotulo"),
                               "x": (W - tot) / 2 + i * (self.cw + gap), "rot": rng.uniform(-4, 4),
                               "fase": rng.uniform(0, 6.28),
                               "de": (W / 2 + rng.uniform(-260, 260), self.topo - 120 + rng.uniform(-80, 40))})
        self.y = spec.get("y", self.topo - 40 - self.ch - 70)

    def desenha(self, fr: Image.Image, t: float) -> None:
        ko = ease_in(self.k_out(t, 0.16))
        for it in self.itens:
            if t < it["te"]:
                continue
            k = mola((t - it["te"]) / 0.4, 1.2)
            kk = ease_out((t - it["te"]) / 0.4)
            card = Image.new("RGBA", (self.cw + 12, self.ch + 12), CLARO + (255,))
            card.alpha_composite(it["leitor"].quadro(t), (6, 6))
            if it["rotulo"]:
                f = F("mono", 24)
                tw = f.getlength(it["rotulo"].upper())
                chip = ret(int(tw + 28), 44, 4, CAIXA + (255,))
                ImageDraw.Draw(chip).text((14, 22), it["rotulo"].upper(), font=f, fill=CLARO + (255,), anchor="lm")
                cola(card, chip, (card.width - chip.width) / 2, card.height - 58)
            esc = 0.35 + 0.65 * k
            im = gira(escala(card, esc), it["rot"] * kk)
            im = com_alfa(im, min(1.0, 0.4 + kk) * (1 - ko))
            boia = 6 * math.sin(t * 2.2 + it["fase"])
            tx, ty = it["x"] + self.cw / 2, self.y + self.ch / 2 + boia
            fx, fy = it["de"]
            cx, cy = fx + (tx - fx) * kk, fy + (ty - fy) * kk - ko * 80
            s = sombra(im, raio=12, forca=0.3, dy=7)
            cola_centro(fr, s, cx, cy)

    def sons(self):
        return [(it["te"], "whoosh_curto", -21) for it in self.itens]

    def resumo(self):
        return "CARDS " + ", ".join((it["rotulo"] or "?") for it in self.itens)


# ---------------------------------------------------------------- chuva de teclas
class Chuva(El):
    """Teclas (atalhos, palavras, perguntas) caem do teto e se empilham em cima da cabeça.
    spec: teclas [texto ou [texto, legenda_pequena]], escuras (a cada quantas uma escura, padrão 4)."""

    def __init__(self, spec):
        super().__init__(spec)
        rng = random.Random(int(self.t0 * 100))
        self.itens = []
        teclas = spec["teclas"]
        n = len(teclas)
        dt = min(0.09, max(0.04, (self.t1 - self.t0 - 0.9) / max(1, n)))
        fileiras = [self.topo - 70, self.topo - 175, self.topo - 280, self.topo - 385]
        por_fil = 5
        for i, tk in enumerate(teclas):
            txt, sub = (tk if isinstance(tk, list) else [tk, ""]) + [""] * (0 if isinstance(tk, list) else 0)
            esc = (i % spec.get("escuras", 4)) == 3
            f = F("ui", 40)
            w = max(104, int(f.getlength(txt) + 44))
            im = ret(w, 98, 16, (ESCURO if esc else CLARO) + (255,))
            d = ImageDraw.Draw(im)
            cor = CLARO if esc else TINTA
            d.text((w / 2, 44 if sub else 49), txt, font=f, fill=cor + (255,), anchor="mm")
            if sub:
                d.text((w / 2, 80), sub, font=F("mono_fino", 13), fill=mistura(CLARO if esc else TINTA, ESCURO if esc else CLARO, 0.45) + (255,), anchor="mm")
            # borda inferior (espessura de tecla)
            base = ret(w, 106, 16, mistura(ESCURO if esc else CLARO, (0, 0, 0), 0.25) + (255,))
            base.alpha_composite(im, (0, 0))
            fil = (i // por_fil) % len(fileiras)
            col = i % por_fil
            x = 110 + col * ((W - 220) / (por_fil - 1)) + rng.uniform(-40, 40) + (fil % 2) * 50
            self.itens.append({"img": base, "te": self.t0 + 0.1 + i * dt, "x": cl(x, 90, W - 90),
                               "y": fileiras[fil] + rng.uniform(-18, 18), "r0": rng.uniform(-30, 30),
                               "r1": rng.uniform(-9, 9)})

    def desenha(self, fr: Image.Image, t: float) -> None:
        ko = self.k_out(t, 0.18)
        for it in self.itens:
            if t < it["te"]:
                continue
            k = (t - it["te"]) / 0.32
            if k < 1:
                y = -160 + (it["y"] + 160) * ease_in(k) ** 0.8
                r = it["r0"] + (it["r1"] - it["r0"]) * k
            else:
                q = cl((k - 1) / 0.6)
                y = it["y"] - 18 * math.sin(math.pi * q) * (1 - q)
                r = it["r1"]
            y += ko * (H * 0.4) * ko
            cola_centro(fr, sombra(gira(it["img"], r), raio=8, forca=0.3, dy=5), it["x"], y)

    def sons(self):
        return [(it["te"] + 0.3, "queda", -20) for it in self.itens]

    def resumo(self):
        return f"CHUVA {len(self.itens)} teclas"


# ---------------------------------------------------------------- tira de filme com caneta
class Filme(El):
    """Folha creme com 2 tiras de filme que enchem com quadros do bruto; a caneta marca o que cortar.
    spec: quadros (lista de segundos da saída | "auto"), marcas [{tipo: circulo|x, quadro(s), texto, em}],
    rodape."""

    def __init__(self, spec):
        super().__init__(spec)
        self.n = 12
        self.fw, self.fh = 120, 150
        q = spec.get("quadros", "auto")
        ts = [TOTAL * (i + 0.5) / self.n for i in range(self.n)] if q == "auto" else [float(v) for v in q][: self.n]
        self.thumbs = [cobre(quadro_em(tt), self.fw, self.fh) for tt in ts]
        self.tcs = [tc_curto(tt) for tt in ts]
        self.marcas = []
        for m in spec.get("marcas", []):
            self.marcas.append({**m, "te": T(m["em"]) - 0.05 if m.get("em") else self.t0 + 0.9})
        self.folha = self._folha()
        self.y = spec.get("y", self.topo - 60 - self.folha.height)

    def _folha(self) -> Image.Image:
        pw = 6 * (self.fw + 14) + 50
        im = Image.new("RGBA", (pw, 2 * (self.fh + 92) + 90), CLARO + (255,))
        d = ImageDraw.Draw(im)
        for r in range(2):
            y0 = 60 + r * (self.fh + 92)
            d.rectangle((18, y0, pw - 18, y0 + self.fh + 36), fill=(18, 18, 18, 255))
            for x in range(26, pw - 26, 22):
                d.rounded_rectangle((x, y0 + 5, x + 11, y0 + 13), radius=2, fill=CLARO + (255,))
                d.rounded_rectangle((x, y0 + self.fh + 23, x + 11, y0 + self.fh + 31), radius=2, fill=CLARO + (255,))
        rod = self.spec.get("rodape", f"BRUTO · {int(TOTAL // 60)}:{int(TOTAL % 60):02d}")
        d.text((pw - 26, im.height - 22), rod, font=F("mono_fino", 16), fill=mistura(CLARO, TINTA, 0.6) + (255,), anchor="rm")
        return im

    def pos_quadro(self, i: int) -> tuple[int, int]:
        r, c = divmod(i, 6)
        return 32 + c * (self.fw + 14), 60 + r * (self.fh + 92) + 18

    def desenha(self, fr: Image.Image, t: float) -> None:
        im = self.folha.copy()
        d = ImageDraw.Draw(im)
        for i in range(self.n):
            te = self.t0 + 0.35 + i * 0.045
            x, y = self.pos_quadro(i)
            if t >= te:
                im.alpha_composite(self.thumbs[i], (x, y))
            d.text((x + self.fw / 2, y + self.fh + 36), self.tcs[i], font=F("mono_fino", 13),
                   fill=mistura(CLARO, TINTA, 0.6) + (255,), anchor="mm")
        caneta = CANETA + (255,)
        for j, m in enumerate(self.marcas):
            k = (t - m["te"]) / 0.35
            if k <= 0:
                continue
            idx = m.get("quadros", [m.get("quadro", 0)])
            if m["tipo"] == "circulo":
                x, y = self.pos_quadro(idx[0])
                traco_parcial(d, elipse_mao(x + self.fw / 2, y + self.fh / 2, self.fw * 0.62, self.fh * 0.6, seed=j), k, caneta, 5)
            else:
                for q, i in enumerate(idx):
                    x, y = self.pos_quadro(i)
                    kq = cl(k * len(idx) - q)
                    traco_parcial(d, [(x + 10, y + 12), (x + self.fw - 10, y + self.fh - 12)], cl(kq * 2), caneta, 5)
                    traco_parcial(d, [(x + self.fw - 12, y + 14), (x + 12, y + self.fh - 10)], cl(kq * 2 - 1), caneta, 5)
            if m.get("texto"):
                x, y = self.pos_quadro(idx[0])
                f = F("mao", 40)
                tw = f.getlength(m["texto"])
                faixa = Image.new("RGBA", (int(tw) + 10, 56), (0, 0, 0, 0))
                ImageDraw.Draw(faixa).text((4, 28), m["texto"], font=f, fill=caneta, anchor="lm")
                vis = faixa.crop((0, 0, max(1, int(faixa.width * cl(k * 1.4))), faixa.height))
                yl = 2 if idx[0] < 6 else im.height - 58
                im.alpha_composite(vis, (int(cl(x + self.fw / 2 - tw / 2, 6, im.width - tw - 6)), yl))
        ki = self.k_in(t, 0.38)
        ko = ease_in(self.k_out(t, 0.16))
        rot = -7 * (1 - ease_out(ki))
        y = self.y - (1 - mola(ki, 1.0)) * 420 - ko * 700
        g = gira(im, rot)
        s = sombra(g, raio=14, forca=0.3, dy=8)
        cola_centro(fr, s, W / 2, y + im.height / 2)

    def sons(self):
        s = [(self.t0, "whoosh", -20)] + [(self.t0 + 0.35 + i * 0.045, "tecla", -27) for i in range(0, self.n, 2)]
        s.append((self.t0 + 0.4, "obturador", -20))
        s += [(m["te"], "caneta", -17) for m in self.marcas]
        return s

    def resumo(self):
        return f"FILME com {len(self.marcas)} marcas"


# ---------------------------------------------------------------- cartela ("alguns minutos depois")
class Cartela(El):
    """Tela chapada com timecode correndo e palavras subindo uma a uma. spec: linhas, timecode."""
    camada = "tela"

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), ESCURO + (255,))
        d = ImageDraw.Draw(cv)
        linhas = [l.upper() for l in self.spec["linhas"]]
        tam = self.spec.get("tamanho", 140)
        lh = int(tam * 0.98)
        y0 = H * 0.42 - (len(linhas) - 1) * lh / 2
        if self.spec.get("timecode", True):
            d.text((W / 2, y0 - tam * 0.95), timecode(t), font=F("mono_fino", 26), fill=DESTAQUE + (255,), anchor="mm")
        dt = max(0.12, (self.t1 - self.t0 - 0.4) / max(1, len(linhas)))
        for i, l in enumerate(linhas):
            img, asc = palavra_img(l, "titulo", tam, CLARO)
            sobe_de_mascara(cv, img, (W - img.width) / 2, y0 + i * lh - asc + tam * 0.35, (t - self.t0 - 0.05 - i * dt) / 0.2)
        return cv

    def sons(self):
        return [(self.t0, "whoosh_curto", -21)] + [(self.t0 + 0.1 + i * 0.15, "tecla", -24) for i in range(6)]

    def resumo(self):
        return "CARTELA " + " ".join(self.spec["linhas"])


# ---------------------------------------------------------------- celular (o vídeo encolhe pra dentro)
class Celular(El):
    """O plano encolhe pra dentro de um celular creme; com "entra", no fim a câmera mergulha no celular
    e ele vira a tela cheia do plano seguinte. spec: entra (true), largura."""
    camada = "tela"

    def __init__(self, spec):
        spec.setdefault("antecipa", 0.0)
        super().__init__(spec)
        self.pw = spec.get("largura", 440)
        self.entra = spec.get("entra", True)

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), ESCURO + (255,))
        ki = ease_in_out(self.k_in(t, 0.3))
        ko = ease_in_out(cl((t - (self.t1 - 0.3)) / 0.3)) if self.entra else 0.0
        k = ki * (1 - ko)
        if k <= 0.001:
            return fr
        sw = self.pw - 28
        sh = int(sw * 16 / 9)
        cx, cy = W / 2, H * 0.43
        # tela do celular: interpola do quadro inteiro até a tela pequena
        w = W + (sw - W) * k
        h = H + (sh - H) * k
        x, y = W / 2 + (cx - W / 2) * k - w / 2, H / 2 + (cy - H / 2) * k - h / 2
        borda = 14 * k
        r = int(56 * k)
        corpo = ret(int(w + 2 * borda), int(h + 2 * borda), r + int(borda), CLARO + (255,))
        tela = fr.resize((max(1, int(w)), max(1, int(h))), Image.BILINEAR)
        m = Image.new("L", tela.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, tela.width - 1, tela.height - 1), radius=r, fill=255)
        tela.putalpha(m)
        corpo.alpha_composite(tela, (int(borda), int(borda)))
        if k > 0.5:
            dc = ImageDraw.Draw(corpo)
            dc.rounded_rectangle((-3, int(h * 0.22), 4, int(h * 0.22) + 70), radius=3, fill=mistura(CLARO, TINTA, 0.25) + (255,))
        com_sombra(cv, corpo, x - borda, y - borda, raio=18, forca=0.35 * k, dy=10)
        return cv

    def sons(self):
        s = [(self.t0, "whoosh_curto", -20)]
        if self.entra:
            s.append((self.t1 - 0.3, "whoosh_sobe", -20))
        return s

    def resumo(self):
        return "CELULAR" + (" (mergulha no fim)" if self.entra else "")


# ---------------------------------------------------------------- letreiro (vídeo dentro das letras)
class Letreiro(El):
    """Tela creme com letras gigantes; o vídeo aparece DENTRO das letras. Entra grande e assenta; sai
    empurrado pra esquerda. spec: linhas (ex. ["HU", "GE"]) ou texto (quebra no meio)."""
    camada = "tela"

    def __init__(self, spec):
        super().__init__(spec)
        txt = spec.get("texto", "")
        self.linhas = spec.get("linhas") or ([txt[: (len(txt) + 1) // 2], txt[(len(txt) + 1) // 2:]] if len(txt) > 3 else [txt])
        self.linhas = [l.upper() for l in self.linhas]
        tam = 900
        while max(larg_txt(l, "titulo", tam) for l in self.linhas) > W * 0.9 or tam * 0.82 * len(self.linhas) > H * 0.86:
            tam -= 10
        self.tam = tam
        self.mask = self._mask()

    def _mask(self) -> Image.Image:
        m = Image.new("L", (W, H), 0)
        lh = int(self.tam * 0.80)
        y0 = H / 2 - lh * len(self.linhas) / 2
        for i, l in enumerate(self.linhas):
            img, asc = palavra_img(l, "titulo", self.tam, (255, 255, 255))
            a = img.getchannel("A")
            # recorta a altura da caixa alta (sem descendente)
            top = int(asc - self.tam * 0.72)
            a = a.crop((0, max(0, top), a.width, asc + 4))
            m.paste(a, (int((W - a.width) / 2), int(y0 + i * lh + (lh - a.height) / 2)), a)
        return m

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        ki = ease_out(self.k_in(t, 0.22))
        z = 1.35 - 0.35 * ki
        cv = Image.new("RGBA", (W, H), CLARO + (255,))
        dentro = aplica_cor(fr, "escuro", 0.35)
        m = self.mask
        if z != 1:
            mw, mh = int(W * z), int(H * z)
            m = m.resize((mw, mh), Image.BILINEAR).crop(((mw - W) // 2, (mh - H) // 2, (mw - W) // 2 + W, (mh - H) // 2 + H))
        cv = Image.composite(dentro, cv, m)
        ko = ease_in(self.k_out(t, 0.14))
        if ko > 0:
            out = fr.copy()
            out.alpha_composite(cv.crop((int(W * ko), 0, W, H)), (0, 0))
            return out
        return cv

    def sons(self):
        return [(self.t0, "impacto", -16), (self.t1 - 0.14, "whoosh_curto", -21)]

    def resumo(self):
        return "LETREIRO " + "".join(self.linhas)


# ---------------------------------------------------------------- feed rolando borrado
class Feed(El):
    """O feed rola rápido na vertical, borrado (o mundo dos outros). spec: itens [{arquivo, inicio}],
    por_item (s que cada um leva pra passar)."""
    camada = "tela"

    def __init__(self, spec):
        spec.setdefault("antecipa", 0.0)
        super().__init__(spec)
        self.imgs = [cobre(quadro_arquivo(str(_resolve(it["arquivo"])), float(it.get("inicio", 1.0))), W, H)
                     for it in spec["itens"]]
        self.por = spec.get("por_item", 0.32)

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        dur = self.t1 - self.t0
        # anda rápido e freia no último item
        k = (t - self.t0) / dur
        pos = (len(self.imgs) - 1) * (1 - (1 - k) ** 2)
        vel = 2 * (len(self.imgs) - 1) * (1 - k) / dur
        i = int(pos)
        f = pos - i
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        a = self.imgs[i % len(self.imgs)]
        b = self.imgs[(i + 1) % len(self.imgs)]
        cv.alpha_composite(a, (0, int(-f * H)))
        cv.alpha_composite(b, (0, int((1 - f) * H)))
        r = int(min(40, vel * H / FPS * 0.22))
        return desfoque_eixo(cv, r, 0)

    def sons(self):
        return [(self.t0, "whoosh", -17), (self.t0 + 0.4, "whoosh", -21)]

    def resumo(self):
        return f"FEED {len(self.imgs)} itens"


# ---------------------------------------------------------------- caneta no rosto
class Caneta(El):
    """Caneta circula a cabeça da pessoa e escreve uma palavra com seta (como o "me" da referência).
    spec: palavra, pb (true: imagem em preto e branco enquanto dura)."""

    def __init__(self, spec):
        spec.setdefault("antecipa", 0.0)
        super().__init__(spec)
        self.pb = spec.get("pb", True)
        x, y, w, h = rosto(self.t0 + 0.1)
        self.cx, self.cy = x + w / 2, y + h * 0.38
        self.rx, self.ry = w * 0.9, h * 1.05
        self.pts = elipse_mao(self.cx, self.cy, self.rx, self.ry, seed=3)

    def filtro(self, fr, t):
        return aplica_cor(fr, "pb", 1.0) if self.pb else fr

    def desenha(self, fr: Image.Image, t: float) -> None:
        camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(camada)
        cor = CANETA + (255,)
        k = (t - self.t0 - 0.12) / 0.4
        traco_parcial(d, self.pts, k, cor, 8)
        kp = (t - self.t0 - 0.5) / 0.3
        if kp > 0 and self.spec.get("palavra"):
            px, py = self.cx + self.rx * 0.55, self.cy - self.ry - 120
            traco_parcial(d, [(px - 20, py + 40), (px - 60, py + 95), (self.cx + self.rx * 0.25, self.cy - self.ry + 4)], kp * 1.6, cor, 6)
            ax, ay = self.cx + self.rx * 0.25, self.cy - self.ry + 4
            if kp > 0.6:
                d.line((ax, ay, ax - 4, ay - 26), fill=cor, width=6)
                d.line((ax, ay, ax + 22, ay - 14), fill=cor, width=6)
            f = F("mao", 78)
            tw = f.getlength(self.spec["palavra"])
            faixa = Image.new("RGBA", (int(tw) + 16, 110), (0, 0, 0, 0))
            ImageDraw.Draw(faixa).text((6, 55), self.spec["palavra"], font=f, fill=cor, anchor="lm")
            vis = faixa.crop((0, 0, max(1, int(faixa.width * cl(kp * 1.2 - 0.2))), faixa.height))
            camada.alpha_composite(vis, (int(cl(px - 30, 20, W - tw - 30)), int(py - 50)))
        fr.alpha_composite(camada)

    def sons(self):
        return [(self.t0 + 0.12, "caneta", -16), (self.t0 + 0.5, "caneta", -20)]

    def resumo(self):
        return f"CANETA \"{self.spec.get('palavra', '')}\"" + (" (P&B)" if self.pb else "")


# ---------------------------------------------------------------- mural de cards na parede
class Mural(El):
    """Cards com quadros DESTE vídeo (já editados) voam e se pregam na parede, tortos, como storyboard.
    spec: quadros (segundos da saída), nota (texto de um papel preso), largura."""

    def __init__(self, spec):
        super().__init__(spec)
        self.cw = spec.get("largura", 118)
        self.ch = int(self.cw * 16 / 9)
        rng = random.Random(11)
        self.itens = []
        ts = spec["quadros"]
        y_lin = max(140, self.topo - 70 - self.ch - 30)
        n = len(ts)
        gap = (W - 80 - n * self.cw) / max(1, n - 1)
        for i, tq in enumerate(ts):
            ang = rng.uniform(0, 6.28)
            self.itens.append({"tq": float(tq), "te": self.t0 + 0.1 + i * 0.09, "x": 40 + i * (self.cw + gap),
                               "y": y_lin + rng.uniform(-14, 14), "rot": rng.uniform(-7, 7),
                               "de": (W / 2 + math.cos(ang) * 900, y_lin + math.sin(ang) * 700)})
        self._imgs: dict[int, Image.Image] = {}

    def _img(self, i: int) -> Image.Image:
        if i not in self._imgs:
            tq = self.itens[i]["tq"]
            n = round(tq * FPS)
            q = compoe(quadro_base(n), tq, n, LEGENDAS, sem=(Mural,))
            card = Image.new("RGBA", (self.cw + 10, self.ch + 10), CLARO + (255,))
            card.alpha_composite(cobre(q, self.cw, self.ch, (0.5, 0.5)), (5, 5))
            self._imgs[i] = card
        return self._imgs[i]

    def desenha(self, fr: Image.Image, t: float) -> None:
        ko = ease_in(self.k_out(t, 0.2))
        for i, it in enumerate(self.itens):
            if t < it["te"]:
                continue
            k = ease_out((t - it["te"]) / 0.3)
            fx, fy = it["de"]
            x = fx + (it["x"] + self.cw / 2 - fx) * k
            y = fy + (it["y"] + self.ch / 2 - fy) * k - ko * 400
            im = gira(self._img(i), it["rot"] + (1 - k) * 40)
            cola_centro(fr, sombra(im, raio=8, forca=0.3, dy=5), x, y)
            if k >= 1:
                d = ImageDraw.Draw(fr)
                d.ellipse((x - 7, y - self.ch / 2 - 4, x + 7, y - self.ch / 2 + 10), fill=CANETA + (255,))
        if self.spec.get("nota") and t >= self.t0 + 0.6:
            nota = ret(230, 170, 4, CLARO + (255,))
            dn = ImageDraw.Draw(nota)
            for j, l in enumerate(quebra(self.spec["nota"], F("mao", 30), 200)[:4]):
                dn.text((14, 30 + j * 36), l, font=F("mao", 30), fill=TINTA + (255,), anchor="lm")
            k = ease_out((t - self.t0 - 0.6) / 0.3)
            cola_centro(fr, sombra(gira(nota, 4), raio=8, forca=0.3, dy=5), W - 150 + (1 - k) * 400, self.topo + 120 - ko * 400)

    def sons(self):
        return [(it["te"], "whoosh_curto", -24) for it in self.itens]

    def resumo(self):
        return f"MURAL {len(self.itens)} cards"


def quebra(txt: str, fonte: ImageFont.FreeTypeFont, larg: int) -> list[str]:
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


# ---------------------------------------------------------------- thread de comentário (nota → resposta → ✓)
class Nota(El):
    """Cartão de comentário: nome + texto digitado, depois a resposta, depois ✓ de resolvido.
    spec: nome, texto, resposta_nome, resposta, avatar ("rosto" | "claude" | letra)."""

    def __init__(self, spec):
        super().__init__(spec)
        self.cps = 26
        self.ta = self.t0 + 0.3
        self.t_resp = self.ta + len(spec["texto"]) / self.cps + 0.25
        self.t_ok = self.t_resp + 0.45
        if self.t_ok > self.t1 - 0.2:
            self.cps = len(spec["texto"]) / max(0.3, (self.t1 - 1.0) - self.ta)
            self.t_resp = self.ta + len(spec["texto"]) / self.cps + 0.2
            self.t_ok = self.t_resp + 0.35

    def _avatar(self, quem: str, d: int) -> Image.Image:
        if quem == "rosto":
            return rosto_img(self.t0, d)
        im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        dd.ellipse((0, 0, d - 1, d - 1), fill=DESTAQUE + (255,))
        dd.text((d / 2, d / 2 + 1), (quem or "C")[0].upper(), font=F("ui", int(d * 0.55)), fill=CLARO + (255,), anchor="mm")
        return im

    def desenha(self, fr: Image.Image, t: float) -> None:
        cw = 660
        f = F("ui_fino", 30)
        l1 = quebra(self.spec["texto"], f, cw - 120)
        l2 = quebra(self.spec.get("resposta", ""), f, cw - 150)
        h = 110 + len(l1) * 40 + (90 + len(l2) * 40 if t >= self.t_resp and l2 else 0) + 20
        card = ret(cw, h, 18, CLARO + (255,))
        d = ImageDraw.Draw(card)
        card.alpha_composite(self._avatar(self.spec.get("avatar", "rosto"), 52), (24, 24))
        d.text((92, 42), self.spec.get("nome", PERFIL["nome"]), font=F("ui", 26), fill=TINTA + (255,), anchor="lm")
        d.text((92 + F("ui", 26).getlength(self.spec.get("nome", PERFIL["nome"])) + 16, 42), "agora", font=F("ui_fino", 22),
               fill=mistura(CLARO, TINTA, 0.5) + (255,), anchor="lm")
        n = int((t - self.ta) * self.cps) if t >= self.ta else 0
        for i, l in enumerate(l1):
            if n <= 0:
                break
            d.text((92, 90 + i * 40), l[:n], font=f, fill=TINTA + (255,), anchor="lm")
            n -= len(l) + 1
        if t >= self.t_resp and l2:
            y0 = 100 + len(l1) * 40
            k = ease_out((t - self.t_resp) / 0.2)
            card.alpha_composite(com_alfa(self._avatar(self.spec.get("resposta_avatar", "claude"), 44), k), (92, y0 + 6))
            d.text((150, y0 + 28), self.spec.get("resposta_nome", "Claude"), font=F("ui", 24), fill=TINTA + (int(255 * k),), anchor="lm")
            for i, l in enumerate(l2):
                d.text((150, y0 + 72 + i * 40), l, font=f, fill=TINTA + (int(255 * k),), anchor="lm")
        ki, ko = ease_out(self.k_in(t, 0.2)), ease_in(self.k_out(t, 0.15))
        x = W - cw - 36 + (1 - ki) * 300
        y = self.spec.get("y", 150) - ko * 500
        com_sombra(fr, com_alfa(card, ki), x, y, raio=14, forca=0.3, dy=7)
        if t >= self.t_ok:
            k = mola((t - self.t_ok) / 0.25)
            ok = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            dk = ImageDraw.Draw(ok)
            dk.ellipse((0, 0, 63, 63), fill=DESTAQUE + (255,))
            dk.line((17, 33, 28, 44, 47, 21), fill=CLARO + (255,), width=7, joint="curve")
            cola_centro(fr, escala(ok, max(0.05, k)), x + 6, y + 6)

    def sons(self):
        s = [(self.t0, "whoosh_curto", -21)]
        s += [(self.ta + i / self.cps, "tecla", -28) for i in range(0, len(self.spec["texto"]), 2)]
        s += [(self.t_resp, "pop", -18), (self.t_ok, "ding", -21)]
        return s

    def resumo(self):
        return f"NOTA: {self.spec['texto']} → {self.spec.get('resposta', '')}"


# ---------------------------------------------------------------- widget que apaga itens (modo edição)
class Widget(El):
    """Cartão creme estilo iPhone em modo edição: ícones tremendo com o "–"; cada um encolhe e some na
    palavra; o contador cai; no fim vira uma frase em itálico. spec: titulo, itens [{icone | rosto |
    glifo, nome, sai_em}], final {texto, em}, unidade ("apps")."""

    def __init__(self, spec):
        super().__init__(spec)
        self.itens = []
        for it in spec["itens"]:
            self.itens.append({**it, "ts": T(it["sai_em"]) - 0.05 if it.get("sai_em") else None})
        fin = spec.get("final")
        self.tf = T(fin["em"]) - 0.05 if fin else None
        self.y = spec.get("y", 150)
        self.icones: list[Image.Image] = []
        for it in self.itens:
            if it.get("icone"):
                p = SKILL / "assets" / "icones" / f"{it['icone']}.png"
                if not p.exists():
                    sys.exit(f"ícone {p.name} não existe: $PY icone_app.py \"<app>\" {it['icone']}")
                ic = cobre(Image.open(p).convert("RGBA"), 112, 112)
            elif it.get("rosto"):
                ic = cobre(rosto_img(self.t0, 112), 112, 112)
            else:
                ic = ret(112, 112, 26, ESCURO + (255,))
                ImageDraw.Draw(ic).text((56, 58), it.get("glifo", it.get("nome", "?")[:2]), font=F("ui", 40),
                                        fill=CLARO + (255,), anchor="mm")
            m = Image.new("L", (112, 112), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, 111, 111), radius=26, fill=255)
            ic.putalpha(Image.composite(ic.getchannel("A"), Image.new("L", (112, 112), 0), m))
            self.icones.append(ic)

    def desenha(self, fr: Image.Image, t: float) -> None:
        n = len(self.itens)
        cw, ch = max(560, 150 * n + 60), 230
        card = ret(cw, ch, 30, CLARO + (255,))
        d = ImageDraw.Draw(card)
        vivos = [i for i, it in enumerate(self.itens) if it["ts"] is None or t < it["ts"] + 0.15]
        cont = len([i for i, it in enumerate(self.itens) if it["ts"] is None or t < it["ts"]])
        d.text((30, 34), self.spec.get("titulo", "MODO EDIÇÃO"), font=F("mono", 18), fill=CANETA + (255,), anchor="lm")
        final = self.tf is not None and t >= self.tf
        d.text((cw - 30, 34), f"{0 if final else cont} {self.spec.get('unidade', 'apps')}", font=F("mono_fino", 18),
               fill=mistura(CLARO, TINTA, 0.5) + (255,), anchor="rm")
        if final:
            k = ease_out((t - self.tf) / 0.2)
            img, asc = palavra_img(self.spec["final"]["texto"], "italico", 72, TINTA)
            cola(card, com_alfa(img, k), (cw - img.width) / 2, ch / 2 + 22 - asc + (1 - k) * 20)
        else:
            # posições: os vivos se espalham por igual; quem está saindo encolhe no lugar
            for slot, i in enumerate(vivos):
                it = self.itens[i]
                x_alvo = (cw - 150 * len([j for j in vivos if self.itens[j]["ts"] is None or t < self.itens[j]["ts"]])) / 2
                ordem = [j for j in vivos if self.itens[j]["ts"] is None or t < self.itens[j]["ts"]]
                if i in ordem:
                    x = x_alvo + 150 * ordem.index(i) + 19
                else:
                    x = (cw - 150 * len(vivos)) / 2 + 150 * slot + 19
                esc = 1.0 if it["ts"] is None or t < it["ts"] else max(0.0, 1 - ease_in((t - it["ts"]) / 0.15))
                if esc <= 0.02:
                    continue
                rot = 2.2 * math.sin(t * 18 + i * 1.7)
                ic = gira(escala(self.icones[i], esc), rot)
                cola_centro(card, ic, x + 56, 120)
                if esc > 0.6:
                    d.ellipse((x - 8, 56, x + 22, 86), fill=(70, 70, 70, 255))
                    d.line((x + 1, 71, x + 13, 71), fill=(255, 255, 255, 255), width=4)
                    d.text((x + 56, 198), it.get("nome", ""), font=F("ui_fino", 20), fill=TINTA + (255,), anchor="mm")
        ki, ko = ease_out(self.k_in(t, 0.18)), ease_in(self.k_out(t, 0.15))
        y = self.y - (1 - ki) * 320 - ko * 380
        com_sombra(fr, card, (W - cw) / 2, y, raio=14, forca=0.3, dy=8)

    def sons(self):
        s = [(self.t0, "whoosh_curto", -20)]
        s += [(it["ts"], "pop", -16) for it in self.itens if it["ts"] is not None]
        if self.tf is not None:
            s.append((self.tf, "ding", -21))
        return s

    def resumo(self):
        return "WIDGET " + ", ".join(it.get("nome", "?") for it in self.itens) + (f" → {self.spec['final']['texto']}" if self.tf else "")


# ---------------------------------------------------------------- capa de revista
class Revista(El):
    """O plano encolhe e vira a foto de uma capa de revista creme. spec: cabecalho [esq, meio, dir],
    titulo (masthead), linha, italico."""
    camada = "tela"

    def __init__(self, spec):
        spec.setdefault("antecipa", 0.0)
        super().__init__(spec)
        self.cx0, self.cy0, self.cw, self.chh = 70, 120, W - 140, H - 300
        self.foto = (self.cx0 + 40, self.cy0 + 300, self.cw - 80, int((self.cw - 80) * 0.78))

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), ESCURO + (255,))
        k = ease_in_out(self.k_in(t, 0.32))
        capa = ret(self.cw, self.chh, 4, CLARO + (255,))
        d = ImageDraw.Draw(capa)
        cab = self.spec.get("cabecalho", ["Nº 01", "A EDIÇÃO", "OUT 2026"])
        fr_ = mistura(CLARO, TINTA, 0.55) + (255,)
        d.text((40, 40), cab[0], font=F("mono", 18), fill=fr_, anchor="lm")
        d.text((self.cw / 2, 40), cab[1], font=F("mono", 18), fill=fr_, anchor="mm")
        d.text((self.cw - 40, 40), cab[2], font=F("mono", 18), fill=fr_, anchor="rm")
        d.line((40, 62, self.cw - 40, 62), fill=fr_, width=2)
        cv.alpha_composite(com_alfa(capa, k), (self.cx0, self.cy0))
        tit = self.spec.get("titulo", "EDITADO").upper()
        tam = 300
        while larg_txt(tit, "titulo", tam) > self.cw - 70:
            tam -= 6
        img, asc = palavra_img(tit, "titulo", tam, ESCURO)
        sobe_de_mascara(cv, img, (W - img.width) / 2, self.cy0 + 70 + tam * 0.86 - asc, (t - self.t0 - 0.2) / 0.3)
        # foto = o plano ao vivo, encolhendo do quadro inteiro até o retângulo da capa
        fx, fy, fw, fh = self.foto
        x0, y0, x1, y1 = 0 + fx * k, 0 + fy * k, W + (fx + fw - W) * k, H + (fy + fh - H) * k
        alvo = cobre(fr, int(x1 - x0), int(y1 - y0), (0.5, 0.45))
        cv.alpha_composite(alvo, (int(x0), int(y0)))
        if k > 0.95:
            dd = ImageDraw.Draw(cv)
            bx, by = fx + fw - 120, fy + fh - 90
            dd.rectangle((bx - 8, by - 8, bx + 100, by + 70), fill=(255, 255, 255, 255))
            rng = random.Random(5)
            x = bx
            while x < bx + 92:
                wv = rng.choice([2, 2, 3, 5])
                dd.rectangle((x, by, x + wv - 1, by + 50), fill=(20, 20, 20, 255))
                x += wv + rng.choice([2, 3])
            yl = fy + fh + 70
            if self.spec.get("linha") and t >= self.t0 + 0.45:
                im2, a2 = palavra_img(self.spec["linha"], "serifa", 60, TINTA)
                cola(cv, im2, (W - im2.width) / 2, yl - a2 + 40)
            if self.spec.get("italico") and t >= self.t0 + 0.65:
                kk = ease_out((t - self.t0 - 0.65) / 0.25)
                im3, a3 = palavra_img(self.spec["italico"], "italico", 112, TINTA)
                vis = im3.crop((0, 0, max(1, int(im3.width * kk)), im3.height))
                cola(cv, vis, (W - im3.width) / 2, yl + 150 - a3)
        return cv

    def sons(self):
        return [(self.t0, "whoosh", -19), (self.t0 + 0.2, "impacto", -21), (self.t0 + 0.65, "whoosh_curto", -23)]

    def resumo(self):
        return f"REVISTA {self.spec.get('titulo', '')}"


# ---------------------------------------------------------------- capítulos com a pessoa recortada
class Capitulos(El):
    """A pessoa recortada na frente de um fundo escuro (o vídeo do material) + pílulas de capítulo com barra
    de progresso. spec: fundo {arquivo, inicio} (opcional), itens [{rotulo, em}]."""
    camada = "tela"
    precisa_mascara = True

    def __init__(self, spec):
        super().__init__(spec)
        fu = spec.get("fundo")
        self.leitor = LeitorVideo(fu["arquivo"], float(fu.get("inicio", 0)), W, H, self.t0) if fu else None
        if self.leitor:
            self.leitores.append(self.leitor)
        self.itens = [{**it, "te": T(it["em"]) - ANT if it.get("em") else self.t0} for it in spec["itens"]]

    def tela(self, fr: Image.Image, t: float) -> Image.Image:
        cv = Image.new("RGBA", (W, H), ESCURO + (255,))
        if self.leitor:
            cv = aplica_cor(self.leitor.quadro(t), "escuro", 0.8)
        n = round(t * FPS)
        m = mascara(n)
        if m is not None:
            corte = fr.copy()
            corte.putalpha(m)
            bb = m.getbbox()
            if bb:
                corte = corte.crop(bb)
                k = 0.62
                corte = escala(corte, k)
                cola(cv, corte, 40, H - corte.height - 60)
        atual = max([i for i, it in enumerate(self.itens) if t >= it["te"]], default=0)
        it = self.itens[atual]
        pw, ph = 520, 110
        pill = ret(pw, ph, 16, CAIXA + (240,), borda=mistura(CAIXA, CLARO, 0.25) + (255,))
        d = ImageDraw.Draw(pill)
        d.text((26, 40), f"{atual + 1:02d}", font=F("mono", 22), fill=mistura(CAIXA, CLARO, 0.5) + (255,), anchor="lm")
        d.text((80, 40), it["rotulo"], font=F("ui", 32), fill=CLARO + (255,), anchor="lm")
        fim = self.itens[atual + 1]["te"] if atual + 1 < len(self.itens) else self.t1
        kp = cl((t - it["te"]) / max(0.2, fim - it["te"]))
        d.rounded_rectangle((26, 78, pw - 26, 86), radius=4, fill=mistura(CAIXA, CLARO, 0.2) + (255,))
        d.rounded_rectangle((26, 78, 26 + (pw - 52) * kp, 86), radius=4, fill=CLARO + (255,))
        ke = ease_out((t - it["te"]) / 0.18)
        cola(cv, com_alfa(pill, ke), W - pw - 50, H * 0.52 + (1 - ke) * 40)
        return cv

    def sons(self):
        return [(it["te"], "whoosh_curto", -21) for it in self.itens]

    def resumo(self):
        return "CAPÍTULOS " + " / ".join(it["rotulo"] for it in self.itens)


# ---------------------------------------------------------------- CTA: comentário, seguir, faixa
class Comenta(El):
    """Palavra gigante cai letra a letra, a caixa de comentário digita a palavra, vira balão e chega a
    resposta. spec: palavra, resposta, conta."""

    def __init__(self, spec):
        super().__init__(spec)
        self.p = spec["palavra"].upper()
        self.tl = self.t0 + 0.15
        self.td = self.tl + 0.12 * len(self.p) + 0.25
        self.t_pub = self.td + 0.1 * len(self.p) + 0.2
        self.t_resp = self.t_pub + 0.5

    def desenha(self, fr: Image.Image, t: float) -> None:
        ki, ko = ease_out(self.k_in(t, 0.2)), ease_in(self.k_out(t, 0.15))
        y = 140 - (1 - ki) * 200 - ko * 400
        bw = 860
        # letras gigantes caindo (antes do balão)
        if t < self.t_pub:
            tam = 190
            tot = larg_txt(self.p, "sans", tam) + 10 * (len(self.p) - 1)
            x = (W - tot) / 2
            for i, ch in enumerate(self.p):
                te = self.tl + 0.12 * i
                lw = larg_txt(ch, "sans", tam)
                if t >= te:
                    k = (t - te) / 0.22
                    yy = y + 150 - (1 - mola(k, 1.4)) * 260
                    if t > self.td:
                        q = (t - self.td - i * 0.05) / 0.3
                        yy += ease_in(q) * 500
                    img, asc = palavra_img(ch, "sans", tam, ESCURO)
                    cola(fr, img, x - tam * 0.12, yy - asc + tam * 0.5)
                x += lw + 10
        caixa = ret(bw, 92, 46, (255, 255, 255, 255))
        d = ImageDraw.Draw(caixa)
        d.ellipse((18, 18, 74, 74), fill=mistura(CLARO, TINTA, 0.2) + (255,))
        n = int((t - self.td) / 0.1) if t >= self.td else 0
        if n <= 0:
            d.text((92, 46), "Adicione um comentário…", font=F("ui_fino", 28), fill=(160, 160, 160, 255), anchor="lm")
        else:
            d.text((92, 46), self.p[:n] + ("|" if t < self.t_pub and int(t * 4) % 2 == 0 else ""), font=F("ui", 30),
                   fill=(20, 20, 20, 255), anchor="lm")
        pub = t >= self.t_pub - 0.15
        d.rounded_rectangle((bw - 150, 22, bw - 22, 70), radius=24, fill=(ESCURO if pub else (225, 225, 225)) + (255,))
        d.text((bw - 86, 46), "Publicar", font=F("ui", 22), fill=(CLARO if pub else (170, 170, 170)) + (255,), anchor="mm")
        if t < self.t_pub + 0.1:
            com_sombra(fr, caixa, (W - bw) / 2, y + 420, raio=10, forca=0.25, dy=5)
        else:
            b = ret(bw, 110, 24, (255, 255, 255, 255))
            db = ImageDraw.Draw(b)
            b.alpha_composite(rosto_img(self.t0, 56) if False else ret(56, 56, 28, mistura(CLARO, TINTA, 0.2) + (255,)), (22, 27))
            db.text((96, 38), "você · agora", font=F("ui_fino", 22), fill=(130, 130, 130, 255), anchor="lm")
            db.text((96, 74), self.p, font=F("ui", 32), fill=(20, 20, 20, 255), anchor="lm")
            db.text((bw - 40, 55), "♥", font=F("ui", 34), fill=CANETA + (255,), anchor="mm")
            com_sombra(fr, b, (W - bw) / 2, y + 420, raio=10, forca=0.25, dy=5)
            if t >= self.t_resp:
                k = ease_out((t - self.t_resp) / 0.2)
                r = ret(bw - 70, 110, 24, (255, 255, 255, 255))
                dr = ImageDraw.Draw(r)
                r.alpha_composite(rosto_img(self.t0, 56), (22, 27))
                dr.text((96, 38), f"{self.spec.get('conta', PERFIL['instagram'])} · agora", font=F("ui_fino", 22), fill=(130, 130, 130, 255), anchor="lm")
                dr.text((96, 74), self.spec.get("resposta", "Te mandei no direct!"), font=F("ui", 30), fill=(20, 20, 20, 255), anchor="lm")
                com_sombra(fr, com_alfa(r, k), (W - bw) / 2 + 70, y + 545 + (1 - k) * 30, raio=10, forca=0.25, dy=5)

    def sons(self):
        s = [(self.tl + 0.12 * i + 0.1, "queda", -18) for i in range(len(self.p))]
        s += [(self.td + 0.1 * i, "tecla", -24) for i in range(len(self.p))]
        s += [(self.t_pub, "pop", -16), (self.t_resp, "ding", -20)]
        return s

    def resumo(self):
        return f"COMENTA {self.p}"


class Seguir(El):
    """Pílula com o rosto da pessoa: "+ Seguir" vira "✓ Seguindo" no toque; etiquetas aparecem coladas.
    spec: toque_em, etiquetas [{texto, em}], y."""

    def __init__(self, spec):
        super().__init__(spec)
        self.tt = T(spec["toque_em"]) if spec.get("toque_em") else self.t0 + 1.0
        self.etq = [{**e, "te": T(e["em"]) - 0.05 if e.get("em") else self.tt + 0.4} for e in spec.get("etiquetas", [])]

    def desenha(self, fr: Image.Image, t: float) -> None:
        ki, ko = mola(self.k_in(t, 0.3)), ease_in(self.k_out(t, 0.15))
        y = self.spec.get("y", LEG_Y - 130) + (1 - ki) * 90 + ko * 300
        seguindo = t >= self.tt
        txt = "✓ Seguindo" if seguindo else "+ Seguir"
        pw = 300
        pill = ret(pw, 76, 38, CAIXA + (255,))
        kf = cl(abs(t - self.tt) / 0.08) if abs(t - self.tt) < 0.08 else 1.0
        ImageDraw.Draw(pill).text((pw / 2, 38), txt, font=F("ui", 32), fill=CLARO + (255,), anchor="mm")
        pill = pill.resize((pw, max(2, int(76 * kf))), Image.BILINEAR)
        av = circulo_img(rosto_img(self.t0, 84), 84, anel=DESTAQUE + (255,))
        x0 = (W - pw - 100) / 2
        cola(fr, com_alfa(av, min(1, ki)), x0, y - 4)
        com_sombra(fr, com_alfa(pill, min(1, ki)), x0 + 100, y + (76 - pill.height) / 2, raio=8, forca=0.25, dy=4)
        x_e = x0 + 100
        for e in self.etq:
            if t < e["te"]:
                continue
            k = mola((t - e["te"]) / 0.25)
            img, asc = palavra_img(e["texto"], "italico", 36, TINTA)
            chip = ret(img.width + 20, 54, 6, CLARO + (255,))
            chip.alpha_composite(img, (10, 27 - asc + 14))
            cola(fr, escala(chip, max(0.05, k)), x_e, y - 64)
            x_e += chip.width + 12

    def sons(self):
        return [(self.t0, "pop", -18), (self.tt, "clique", -14)] + [(e["te"], "pop", -21) for e in self.etq]

    def resumo(self):
        return "SEGUIR"


class Faixa(El):
    """Faixa escura no alto: "Comenta "PALAVRA"" + linha de baixo. spec: titulo, palavra, sub."""

    def desenha(self, fr: Image.Image, t: float) -> None:
        bw, bh = 900, 150
        b = ret(bw, bh, 18, CAIXA + (250,))
        d = ImageDraw.Draw(b)
        t1 = self.spec.get("titulo", "Comenta")
        p = f"“{self.spec['palavra'].upper()}”"
        f1 = F("sans", 52)
        im2, a2 = palavra_img(p, "italico", 64, DESTAQUE)
        tw = f1.getlength(t1) + 18 + im2.width
        x = (bw - tw) / 2
        d.text((x, 62), t1, font=f1, fill=CLARO + (255,), anchor="ls")
        b.alpha_composite(im2, (int(x + f1.getlength(t1) + 18), int(64 - a2)))
        d.text((bw / 2, 108), self.spec.get("sub", "e eu te mando o passo a passo"), font=F("ui_fino", 28),
               fill=CLARO + (255,), anchor="mm")
        k = ease_out(self.k_in(t, 0.22))
        ko = ease_in(self.k_out(t, 0.15))
        vis = b.crop((0, 0, bw, max(1, int(bh * k))))
        cola(fr, vis, (W - bw) / 2, 120 - ko * 300)

    def sons(self):
        return [(self.t0, "whoosh_curto", -20)]

    def resumo(self):
        return f"FAIXA comenta {self.spec['palavra']}"


TIPOS = {"titulo": Titulo, "grade": Grade, "tiquete": Tiquete, "regua": Regua, "cor": Cor, "paleta": Paleta,
         "cards": Cards, "chuva": Chuva, "filme": Filme, "cartela": Cartela, "celular": Celular,
         "letreiro": Letreiro, "feed": Feed, "caneta": Caneta, "mural": Mural, "nota": Nota, "widget": Widget,
         "revista": Revista, "capitulos": Capitulos, "comenta": Comenta, "seguir": Seguir, "faixa": Faixa}

# ================================================================ legenda
LEG = MAPA.get("legenda_cfg", {})
LEG_TAM = LEG.get("tamanho", 56)
LEG_MAX = LEG.get("max_palavras", 4)
LEG_Y = LEG.get("y", int(H * 0.71))


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    blocos, i = [], 0
    while i < len(WORDS):
        cur, j = [i], i + 1
        while j < len(WORDS) and len(cur) < LEG_MAX:
            if WORDS[j]["s"] - WORDS[j - 1]["e"] >= 0.3 or WORDS[j - 1]["t"].rstrip()[-1] in ".,!?;:":
                break
            if WORDS[j]["seg"] != WORDS[j - 1]["seg"]:
                break
            if larg_txt(" ".join(WORDS[k]["t"] for k in cur + [j]), "legenda", LEG_TAM) > 820:
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


LEGENDAS: list[dict] = []
MODOS = []
for _m in MAPA.get("legenda_modos", []):
    MODOS.append({"modo": _m["modo"], "t0": T(_m["em"]) - 0.02, "t1": T(_m["ate"], True) + 0.25 if _m.get("ate") else fim_tomada(_m["em"])})


def desenha_bloco(fr: Image.Image, palavras: list[dict], t: float, y: float, tam: int, caixa: bool = True,
                  a: float = 1.0) -> None:
    esp = larg_txt(" ", "legenda", tam)
    imgs = []
    for w in palavras:
        cor = CLARO if t >= w["s"] - 0.03 else APAGADO
        if not caixa and t < w["s"] - 0.03:
            cor = mistura(ESCURO, CLARO, 0.45)
        imgs.append(palavra_img(w["t"], "legenda", tam, cor))
    pads = [tam * 0.12 * COND["legenda"] for _ in imgs]
    larg = sum(im.width - 2 * p for (im, _), p in zip(imgs, pads)) + esp * (len(imgs) - 1)
    alt = int(tam * 1.3)
    x0 = (W - larg) / 2
    if caixa:
        bx = ret(int(larg + 2 * tam * 0.32), alt, 0, CAIXA + (int(250 * a),))
        cola(fr, bx, x0 - tam * 0.32, y - alt / 2)
    x = x0
    for (im, asc), p in zip(imgs, pads):
        cola(fr, com_alfa(im, a), x - p, y + tam * 0.36 - asc)
        x += im.width - 2 * p + esp


def desenha_legenda(fr: Image.Image, t: float, solta: bool) -> None:
    for m in MODOS:
        if m["t0"] <= t < m["t1"]:
            ws = [w for w in WORDS if m["t0"] - 0.05 <= w["s"] <= t + 0.02 and w["s"] < m["t1"]]
            if not ws:
                break
            if m["modo"] == "escada":
                # cada palavra numa caixa própria, empilhadas, cada uma maior que a anterior
                ws = ws[-4:]
                tams = [46, 62, 84, 112][: len(ws)]
                y = LEG_Y + 110
                for w, tm in reversed(list(zip(ws, tams))):
                    k = ease_out((t - w["s"] + 0.03) / 0.12)
                    tm2 = int(tm * (0.7 + 0.3 * k))
                    desenha_bloco(fr, [w], t + 1, y - tm2 * 0.65, tm2)
                    y -= tm2 * 1.3 + 8
                return
            if m["modo"] == "grande":
                # a legenda pula pro alto e fica enorme, uma palavra por linha
                tm = 150
                y0 = H * 0.30
                for i, w in enumerate(ws[-4:]):
                    k = ease_out((t - w["s"] + 0.03) / 0.15)
                    y_dest = y0 + i * tm * 1.35
                    yy = LEG_Y + (y_dest - LEG_Y) * k
                    desenha_bloco(fr, [w], t + 1, yy, int(LEG_TAM + (tm - LEG_TAM) * k))
                return
    b = next((b for b in LEGENDAS if b["ini"] <= t < b["fim"]), None)
    if b:
        ps = [WORDS[k] for k in b["idx"]]
        if solta:
            desenha_bloco(fr, ps, t, H * 0.80, 44, caixa=False)
        else:
            desenha_bloco(fr, ps, t, LEG_Y, LEG_TAM)


# ================================================================ transições
class Transicao:
    def __init__(self, spec: dict):
        self.tipo = spec["tipo"]
        g = spec["tomada"]
        self.tc = OFF[g]
        self.d = spec.get("dura", {"iris": 0.26, "persiana": 0.3, "borrao": 0.24, "zoom": 0.22}[self.tipo])
        self.g = g
        if self.tipo == "iris":
            x, y, w, h = MED[g]["rosto"]
            self.c = (x + w * 0.32, y + h * 0.42)

    def ativa(self, t: float) -> bool:
        if self.tipo == "borrao":
            return abs(t - self.tc) < self.d / 2
        return self.tc <= t < self.tc + self.d

    def aplica(self, fr: Image.Image, t: float, velho: Image.Image | None) -> Image.Image:
        k = (t - self.tc) / self.d
        if self.tipo == "iris" and velho is not None:
            r = 8 + ease_in(k) * math.hypot(W, H)
            m = Image.new("L", (W, H), 0)
            cx, cy = self.c
            ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
            out = Image.composite(fr, velho, m)
            ImageDraw.Draw(out).ellipse((cx - r, cy - r, cx + r, cy + r), outline=CLARO + (255,), width=5)
            return out
        if self.tipo == "persiana" and velho is not None:
            out = velho.copy()
            n = 8
            sw = W // n
            for i in range(n):
                kk = cl((k - i * 0.06) / 0.5)
                if kk <= 0:
                    continue
                dy = int((1 - ease_out(kk)) * 220 * (1 if i % 2 else -1))
                fat = fr.crop((i * sw, 0, (i + 1) * sw if i < n - 1 else W, H))
                out.paste(fat, (i * sw, dy))
                if dy:
                    out.paste(fat, (i * sw, dy - H if dy > 0 else dy + H))
            return out
        if self.tipo == "borrao":
            kk = 1 - abs(t - self.tc) / (self.d / 2)
            z = 1 + 0.06 * kk
            nw, nh = int(W * z), int(H * z)
            fr = fr.resize((nw, nh), Image.BILINEAR).crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))
            return desfoque_eixo(fr, int(60 * kk), 1)
        return fr


TRANS = [Transicao(s) for s in MAPA.get("transicoes", [])]
ABRE = MAPA.get("abertura", True)

# ================================================================ montagem
_ELS = []
FALTANDO: list[str] = []   # só no --storyboard: elemento cujo arquivo/ícone não existe (o vídeo para no erro)
for _s in MAPA.get("elementos", []):
    if _s["tipo"] not in TIPOS:
        sys.exit(f"tipo {_s['tipo']} não existe: {', '.join(TIPOS)}")
    if ARGS.storyboard:
        try:
            _ELS.append(TIPOS[_s["tipo"]](_s))
        except SystemExit as _ex:
            if "não achei" not in str(_ex) and "ícone" not in str(_ex):
                raise
            FALTANDO.append(f"{_s['tipo']} em {_s.get('em')}: {_ex}")
        continue
    _ELS.append(TIPOS[_s["tipo"]](_s))
ELS = sorted(_ELS, key=lambda e: e.t0)


def janelas_mascara() -> list[tuple[float, float]]:
    return [(e.t0 - 0.05, e.t1 + 0.05) for e in ELS if e.precisa_mascara]


def compoe(fr: Image.Image, t: float, n: int, legendas: list[dict], sem: tuple = ()) -> Image.Image:
    original = fr
    ativos = [e for e in ELS if e.ativo(t) and not isinstance(e, sem)]
    # 1. abertura: a câmera começa colada e abre
    if ABRE and t < 0.24:
        z = 1 + 0.2 * (1 - ease_out(t / 0.24))
        nw, nh = int(W * z), int(H * z)
        cx, cy = rosto(0)[0] + rosto(0)[2] / 2, rosto(0)[1] + rosto(0)[3] / 2
        x0 = int(cl(cx * z - W / 2, 0, nw - W))
        y0 = int(cl(cy * z - H / 2, 0, nh - H))
        fr = fr.resize((nw, nh), Image.BILINEAR).crop((x0, y0, x0 + W, y0 + H))
        original = fr
    # 2. cor
    for e in ELS:   # régua com efeito deixa a cor até o fim da tomada
        if isinstance(e, Regua) and e.efeito and e.t1 <= t < fim_tomada(e.spec["em"]) and e not in ativos:
            fr = aplica_cor(fr, e.efeito, 1.0)
    for e in ativos:
        if hasattr(e, "filtro"):
            fr = e.filtro(fr, t)
    if fr is not original:
        original_cor = fr
    else:
        original_cor = original
    # 3. títulos atrás da cabeça
    atras = [e for e in ativos if e.camada == "atras"]
    if atras:
        camada = fr.copy()
        for e in atras:
            e.desenha(camada, t)
        m = mascara(n)
        fr = Image.composite(original_cor, camada, m) if m is not None else camada
    # 4. tela cheia
    tela = [e for e in ativos if e.camada == "tela"]
    solta = False
    for e in tela:
        fr = e.tela(fr, t)
        solta = solta or isinstance(e, (Grade, Cartela, Celular, Feed))
    # 5. objetos por cima
    for e in ativos:
        if e.camada == "sobre":
            e.desenha(fr, t)
    # 6. transições
    for tr in TRANS:
        if tr.ativa(t):
            velho = None
            if tr.tipo in ("iris", "persiana"):
                velho = compoe_velho(tr)
            fr = tr.aplica(fr, t, velho)
    # 7. legenda
    if legendas is not None and not (MAPA.get("legenda") is False):
        desenha_legenda(fr, t, solta)
    return fr


@functools.lru_cache(maxsize=8)
def _velho(tc: float) -> Image.Image:
    n = max(0, round(tc * FPS) - 1)
    return compoe(quadro_base(n), n / FPS, n, None)


def compoe_velho(tr: Transicao) -> Image.Image:
    return _velho(tr.tc)


# ================================================================ áudio: efeitos sintetizados
def _norm(x):
    return x / (np.abs(x).max() + 1e-9)


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
    return _norm(out)


def sfx_impacto(d=0.7, seed=1):
    n = int(d * SR)
    tt = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * (48 + 60 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 7)
    clique = np.random.default_rng(seed).standard_normal(n) * np.exp(-tt * 90) * 0.5
    return _norm(corpo + clique)


def sfx_pop(d=0.09, f0=1100, f1=520):
    n = int(d * SR)
    tt = np.arange(n) / SR
    f = f0 + (f1 - f0) * tt / d
    return _norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 45))


def sfx_tecla(seed=0):
    n = int(0.035 * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    ruido = rng.standard_normal(n) * np.exp(-tt * 260)
    tom = np.sin(2 * np.pi * rng.uniform(1700, 2600) * tt) * np.exp(-tt * 300) * 0.4
    return _norm(np.convolve(ruido + tom, np.ones(3) / 3, mode="same"))


def sfx_ding(d=0.9):
    n = int(d * SR)
    tt = np.arange(n) / SR
    out = (np.sin(2 * np.pi * 1318.5 * tt) + 0.45 * np.sin(2 * np.pi * 2637 * tt) +
           0.2 * np.sin(2 * np.pi * 1975.5 * tt)) * np.exp(-tt * 5.5)
    out[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return _norm(out)


def sfx_clique():
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    return _norm(np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 120) +
                 np.random.default_rng(9).standard_normal(n) * np.exp(-tt * 400) * 0.6)


def sfx_impressora(d=0.45, seed=3):
    """Papel saindo da impressora: rajada de cliques secos a ~28 por segundo."""
    n = int(d * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(seed)
    for k in range(int(d * 28)):
        i = int(k / 28 * SR)
        c = sfx_tecla(int(rng.integers(0, 50))) * rng.uniform(0.4, 0.8)
        out[i:i + len(c)] += c[: n - i]
    ruido = rng.standard_normal(n) * 0.08 * np.sin(np.pi * np.arange(n) / n)
    return _norm(out + ruido)


def sfx_obturador():
    a = sfx_clique()
    out = np.zeros(int(0.16 * SR))
    out[: len(a)] += a
    out[int(0.09 * SR): int(0.09 * SR) + len(a)] += a[: len(out) - int(0.09 * SR)] * 0.7
    return _norm(out)


def sfx_caneta(d=0.4, seed=4):
    """Caneta riscando: ruído agudo com tremor."""
    n = int(d * SR)
    tt = np.arange(n) / SR
    r = np.random.default_rng(seed).standard_normal(n)
    r = r - np.convolve(r, np.ones(6) / 6, mode="same")
    am = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 9 * tt))
    return _norm(r * am * np.sin(np.pi * tt / d) ** 0.5)


def sfx_queda(seed=5):
    n = int(0.18 * SR)
    tt = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * (160 + 80 * np.exp(-tt * 40)) * tt) * np.exp(-tt * 30)
    estalo = np.random.default_rng(seed).standard_normal(n) * np.exp(-tt * 300) * 0.4
    return _norm(corpo + estalo)


def trilha_sfx() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    sons = {"whoosh": [sfx_whoosh(0.42, seed=s) for s in (1, 2, 3)],
            "whoosh_curto": [sfx_whoosh(0.22, 600, 4200, seed=s) for s in (6, 7)],
            "whoosh_sobe": [sfx_whoosh(0.5, 200, 3200, seed=s) for s in (4, 5)],
            "impacto": [sfx_impacto(seed=s) for s in (1, 2)],
            "pop": [sfx_pop(), sfx_pop(0.08, 1300, 650), sfx_pop(0.1, 950, 480)],
            "tecla": [sfx_tecla(s) for s in range(6)],
            "ding": [sfx_ding()], "clique": [sfx_clique()], "impressora": [sfx_impressora(), sfx_impressora(seed=8)],
            "obturador": [sfx_obturador()], "caneta": [sfx_caneta(), sfx_caneta(seed=9)],
            "queda": [sfx_queda(s) for s in range(4)]}
    giro = {k: itertools.cycle(v) for k, v in sons.items()}
    ev: list[tuple[float, str, float]] = []
    for e in ELS:
        ev += e.sons()
    for tr in TRANS:
        ev.append((tr.tc - (0.12 if tr.tipo == "borrao" else 0.02), "whoosh" if tr.tipo != "persiana" else "whoosh_curto", -18))
    if ABRE:
        ev.append((0.0, "whoosh_curto", -24))
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
NOMES_SB = {"titulo": "Título atrás da cabeça", "grade": "Grade de quadros do vídeo", "tiquete": "Tíquete de impressora",
            "regua": "Régua que corre", "cor": "Troca de cor", "paleta": "Conta-gotas e paleta",
            "cards": "Cards dos Reels do criador", "chuva": "Chuva de teclas", "filme": "Tira de filme marcada à caneta",
            "cartela": "Cartela de tempo passando", "celular": "Vídeo encolhe pro celular",
            "letreiro": "Letreiro com o vídeo dentro das letras", "feed": "Feed rolando borrado",
            "caneta": "Caneta circula o rosto", "mural": "Mural de cards deste vídeo",
            "nota": "Nota de comentário (texto → resposta → ✓)", "widget": "Widget apagando itens",
            "revista": "Capa de revista", "capitulos": "Capítulos com a pessoa recortada", "comenta": "CTA de comentário",
            "seguir": "CTA seguir", "faixa": "Faixa \"Comenta\""}
NOMES_COR = {"pb": "preto e branco", "escuro": "escuro", "quente": "quente", "frio": "frio"}


def _desc_sb(e: El, SB) -> str:
    """O que entra na tela, em português, a partir do spec do elemento."""
    s, tp = e.spec, e.spec["tipo"]
    nome = lambda a: Path(str(a)).name
    if tp == "tiquete":
        num = f"{e.num:02d}" if isinstance(e.num, int) else str(e.num)
        return f'{e.rotulo} {num} {e.para}: "{s["texto"]}"' + (f' · TOTAL {s["total"]}' if s.get("total") else "")
    if tp == "titulo":
        d = " / ".join(SB.limpa_marcacao(l) for l in s["linhas"])
        d += " — letra por letra" if e.anim == "letras" else " — sobe de trás de uma máscara"
        return d + (f'; itálico dourado em {" ".join(s["destaque"])}' if s.get("destaque") else "")
    if tp == "grade":
        return f"{e.n} casas com quadros do próprio vídeo, palavras faladas sobem; mergulha na última casa"
    if tp == "regua":
        return " → ".join(e.valores) + (f"; a imagem fica {NOMES_COR.get(e.efeito, e.efeito)} até o fim da frase"
                                        if e.efeito else "")
    if tp == "cor":
        return f"imagem em {NOMES_COR.get(e.modo, e.modo)} na palavra"
    if tp == "cards":
        return " · ".join(f'{it.get("rotulo") or "?"} ({nome(it["arquivo"])})' for it in s["itens"])
    if tp == "chuva":
        return " · ".join(k if isinstance(k, str) else k[0] for k in s.get("teclas", []))
    if tp == "filme":
        return "marcas: " + (" · ".join(m.get("texto", m["tipo"]) for m in s.get("marcas", [])) or "nenhuma")
    if tp == "celular":
        return "o plano encolhe pra dentro de um celular" + ("; no fim a câmera mergulha nele" if e.entra else "")
    if tp == "letreiro":
        return "".join(e.linhas)
    if tp == "feed":
        return f"{len(s['itens'])} vídeos: " + ", ".join(dict.fromkeys(nome(it["arquivo"]) for it in s["itens"]))
    if tp == "caneta":
        return f'escreve "{s.get("palavra", "")}" com seta' + (" (imagem em P&B)" if e.pb else "")
    if tp == "mural":
        return f'{len(s.get("quadros", []))} quadros deste vídeo' + (f'; nota: "{s["nota"]}"' if s.get("nota") else "")
    if tp == "nota":
        return f'{s.get("nome", "")}: "{s["texto"]}" → {s.get("resposta_nome", PERFIL["nome"])}: "{s.get("resposta", "")}"'
    if tp == "widget":
        return (f'{s.get("titulo", "")}: ' + ", ".join(it.get("nome", "?") for it in s["itens"]) + " somem"
                + (f' → "{s["final"]["texto"]}"' if s.get("final") else ""))
    if tp == "revista":
        return f'{s.get("titulo", "")} — {s.get("linha", "")} {s.get("italico", "")}'.strip(" —")
    if tp == "comenta":
        return f'palavra {s.get("palavra", "")}' + (f' → resposta "{s["resposta"]}"' if s.get("resposta") else "")
    if tp == "seguir":
        return "+ Seguir vira ✓ Seguindo" + (": " + ", ".join(x["texto"] for x in s["etiquetas"]) if s.get("etiquetas") else "")
    if tp == "faixa":
        return f'{s.get("titulo", "Comenta")} "{s.get("palavra", "")}" — {s.get("sub", "")}'.strip(" —")
    if tp == "capitulos":
        return " / ".join(it["rotulo"] for it in s["itens"])
    return SB.textos_do_spec(s) or e.resumo()


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    br = lambda x: f"{x:.1f}".replace(".", ",")
    ms, avisos = [], []
    tem_mascara = lambda t: (EDIT / "masks" / "out" / f"f_{round(t * FPS):06d}.png").exists()
    # saída de cada tipo: o quadro fica antes dela (tíquete é sugado 0,3 s; grade e celular mergulham)
    margem = {"tiquete": 0.35, "celular": 0.35}
    for e in ELS:
        tp = e.spec["tipo"]
        ev = [x for x, _, _ in e.sons() if x < e.t1 - 0.3]
        q = max([e.t0 + 0.45] + [x + 0.35 for x in ev])   # depois do último evento (tecla, pop, ✓, marca...)
        if tp == "titulo":
            pal = [(li, pi, p) for li, l in enumerate(e.spec["linhas"]) for pi, p in enumerate(l.split())]
            q = max(e.t0 + 0.1 * li + 0.06 * pi + (0.05 * len(p) + 0.05 if e.anim == "letras" else 0.25)
                    for li, pi, p in pal)
            if e.td is not None:
                q = max(q, e.td + 0.25)
        elif tp == "caneta":
            q = e.t0 + 0.85
        elif tp == "feed":
            q = e.t0 + 0.35
        fim = e.t1 - (e.dz + 0.05 if tp == "grade" else margem.get(tp, 0.2))
        q = max(e.t0 + 0.02, min(q, fim))
        nome = NOMES_SB.get(tp, tp)
        if tp == "titulo" and e.anim == "letras":
            nome += " (letra por letra)"
        if tp == "regua" and e.efeito:
            nome += f" e deixa a imagem {NOMES_COR.get(e.efeito, e.efeito)}"
        if tp == "cor":
            nome += f": {NOMES_COR.get(e.modo, e.modo)}"
        m = {"t0": max(0.0, e.t0), "t1": e.t1, "quadro": q, "tipo": nome, "desc": _desc_sb(e, SB) or "—"}
        if e.precisa_mascara and not tem_mascara(q):
            m["aviso"] = "sem máscara neste quadro: o título cobre a pessoa (rodar mascaras.py)"
        elif e.t1 - e.t0 < 0.5:   # mesma regra do ATENÇÃO impresso pelo compor
            m["aviso"] = f"fica só {br(e.t1 - e.t0)} s na tela (mínimo ~0,5 s)"
        elif tp == "tiquete" and e.ta + sum(len(l) for l in e.linhas) / e.cps > e.t1 - 0.3:
            m["aviso"] = "o texto não termina de digitar antes de o tíquete voltar pra fenda (frase curta)"
        ms.append(m)
    # câmera
    if ABRE:
        ms.append({"t0": 0.0, "t1": 0.24, "quadro": 0.04, "tipo": "Câmera: abertura",
                   "desc": "começa colada no rosto e abre em 0,24 s"})
    # legenda que obedece (escada, gigante)
    for md in MODOS:
        ws = [w for w in WORDS if md["t0"] - 0.05 <= w["s"] < md["t1"]]
        q = (ws[min(3, len(ws) - 1)]["s"] + 0.15) if ws else md["t0"] + 0.3
        ms.append({"t0": md["t0"], "t1": md["t1"], "quadro": max(md["t0"] + 0.02, min(q, md["t1"] - 0.05)),
                   "tipo": "Legenda em escada" if md["modo"] == "escada" else "Legenda gigante no alto",
                   "desc": ("cada palavra numa caixa, empilhadas e crescendo" if md["modo"] == "escada"
                            else "a legenda pula pro alto, uma palavra por linha") +
                           (f': "{" ".join(w["t"] for w in ws[:4])}"' if ws else "")})
    # transições temáticas
    blocos = [tm[2] if len(tm) > 2 else "" for tm in MAPA.get("tomadas", [])]
    nomes_tr = {"iris": "íris", "persiana": "persiana", "borrao": "borrão", "zoom": "zoom"}
    for tr in TRANS:
        if tr.tipo == "borrao":
            t0, t1, q = tr.tc - tr.d / 2, tr.tc + tr.d / 2, tr.tc
        else:
            t0, t1, q = tr.tc, tr.tc + tr.d, tr.tc + tr.d * 0.45
        bloco = f" (bloco {blocos[tr.g]})" if len(blocos) == _NG and blocos[tr.g] else ""
        ms.append({"t0": t0, "t1": t1, "quadro": q, "tipo": f"Transição: {nomes_tr.get(tr.tipo, tr.tipo)}",
                   "desc": f"entrada da tomada {tr.g + 1}{bloco}"})
    for m in ms:
        for k in ("t0", "t1", "quadro"):
            m[k] = round(float(m[k]), 2)
    # avisos globais: os mesmos da linha do tempo impressa + o que falta
    for f in FALTANDO:
        avisos.append(f"elemento sem arquivo, fora do storyboard (o render para aqui): {f}")
    if any(e.precisa_mascara for e in ELS) and not (EDIT / "masks" / "out").exists():
        avisos.append("tem título atrás da cabeça ou capítulos e falta a pasta masks/: rode mascaras.py")
    for a, b in trechos_limpos():
        avisos.append(f"trecho limpo de {br(b - a)} s ({br(a)}–{br(b)} s): na referência quase nada passa de 1 s")
    if MAPA.get("legenda") is False:
        avisos.append("legenda desligada no mapa (\"legenda\": false)")
    # arquivos que a edição usa
    arqs: list[tuple[str, bool]] = []
    for s in MAPA.get("elementos", []):
        nomes = [s.get("arquivo"), (s.get("fundo") or {}).get("arquivo")] + list(s.get("arquivos", []))
        nomes += [i.get("arquivo") for i in s.get("itens", []) if isinstance(i, dict)]
        for a in nomes:
            if a and a not in [x for x, _ in arqs]:
                arqs.append((a, _resolve(a).exists()))
        for i in s.get("itens", []):
            if isinstance(i, dict) and i.get("icone"):
                a = f'ícone {i["icone"]}.png'
                if a not in [x for x, _ in arqs]:
                    arqs.append((a, (SKILL / "assets" / "icones" / f'{i["icone"]}.png').exists()))
    if MAPA.get("musica"):
        arqs.append((MAPA["musica"]["arquivo"], _resolve(MAPA["musica"]["arquivo"]).exists()))
    cenas = [{"t0": round(OFF[g], 2), "t1": round(OFF[g + 1], 2),
              "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)} for g in range(_NG)]

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, n, legendas)

    out = SB.gerar(EDIT, "Papel", TOTAL, cenas, ms, quadro, avisos, arqs)
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


def linha_do_tempo() -> None:
    print(f"{TOTAL:.1f} s, {len(ELS)} elementos (um a cada {TOTAL / max(1, len(ELS)):.1f} s), {len(TRANS)} transições")
    for e in ELS:
        print(f"  {e.t0:6.2f}–{e.t1:6.2f}  {e.resumo()}")
    for tr in TRANS:
        print(f"  {tr.tc:6.2f}        TRANSIÇÃO {tr.tipo}")
    for a, b in trechos_limpos():
        print(f"ATENÇÃO trecho limpo de {b - a:.1f} s ({a:.1f}–{b:.1f}): na referência quase nada passa de 1 s")


def trechos_limpos() -> list[tuple[float, float]]:
    """Trechos sem nenhum objeto acima de 1,6 s (a referência quase não tem)."""
    marcas = sorted([(e.t0, e.t1) for e in ELS] + [(m["t0"], m["t1"]) for m in MODOS])
    t, buraco = 0.0, []
    for a, b in marcas:
        if a - t > 1.6:
            buraco.append((t, a))
        t = max(t, b)
    if TOTAL - t > 1.6:
        buraco.append((t, TOTAL))
    return buraco


def main() -> None:
    global LEGENDAS
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if ARGS.storyboard:   # sem máscara não para aqui: o storyboard avisa no momento
        LEGENDAS[:] = monta_legendas()
        storyboard(LEGENDAS)
        return
    if any(e.precisa_mascara for e in ELS) and not (EDIT / "masks" / "out").exists():
        sys.exit("tem título atrás da cabeça ou capítulos: rode mascaras.py")
    LEGENDAS[:] = monta_legendas()
    linha_do_tempo()
    modo = "final" if ARGS.final else "preview"

    if ARGS.so_quadros:
        pasta = EDIT / "verify" / "quadros"
        pasta.mkdir(parents=True, exist_ok=True)
        for f in pasta.glob("q_*.jpg"):
            f.unlink()
        for ts in ARGS.so_quadros.split(","):
            t = float(ts)
            n = round(t * FPS)
            compoe(quadro_base(n), t, n, LEGENDAS).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
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
    prenorm = EDIT / f"{modo}_papel.prenorm.mp4"
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
        enc.stdin.write(compoe(fr, t, k, LEGENDAS).convert("RGB").tobytes())
        for e in ELS:
            if t >= e.t1:
                e.fecha()
        k += 1
        if k % 150 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_papel.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
