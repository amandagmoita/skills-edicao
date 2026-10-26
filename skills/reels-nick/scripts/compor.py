"""compor.py — monta o Reel no estilo "Nick" quadro a quadro, a partir do mapa.json.

Estilo medido na referência (referencia/referencias-estilo.md): cada substantivo da fala vira imagem no
mesmo segundo. Três layouts se alternam a cada ~2-3 s:
  dividida  fundo claro em cima com o elemento, a pessoa num cartão de cantos arredondados embaixo e a cabeça
            passando por cima da borda do cartão; legenda preta logo acima da cabeça.
  cheia     só o elemento (card do item da lista, logo grande, fluxo, janela no escuro), legenda no meio.
  rosto     close no rosto, legenda branca no peito.
Elementos: logos que se acumulam, card do item, janela de navegador (marca-texto, contorno, clique,
contador), contador, fluxo, gráfico que se desenha, antes x depois, foto da pessoa citada, imagem, vídeo,
órbita, logo digitando, título do gancho com pílula. Legenda acumula palavra a palavra, cada uma entrando
por desfoque; palavra-chave em serifa itálica na cor de destaque. CTA "comenta + PALAVRA" com brilho.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_nick.mp4 | final_nick.mp4

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
    x = cl(x)
    c1 = 1.7
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- cores (medidas na referência)
# palavra-chave, contador, contorno, clique. Padrão = cor de destaque do perfil; o azul da referência é "#3188FD".
DESTAQUE = hexa(MAPA.get("destaque", PERFIL["cor_destaque"]))
DESTAQUE2 = hexa(MAPA.get("destaque2", "#E79786"))      # ordinal do card do item ("O SEGUNDO")
TINTA = (1, 1, 1)
BRANCO = (255, 255, 255)


def _escurece(c: tuple, f: float) -> tuple:
    return tuple(int(v * f) for v in c)


def _clareia(c: tuple, f: float) -> tuple:
    return tuple(int(v + (255 - v) * f) for v in c)


# Cor de destaque CLARA (ex.: amarelo #FFC700): some em fundo branco. Aí o texto em cima dela é preto,
# a palavra-chave em fundo claro vira texto preto sobre faixa amarela (marca-texto) e linha/número no
# branco usam a cor escurecida. Com cor escura (o azul da referência) nada disso muda.
ACENTO_CLARO = 0.299 * DESTAQUE[0] + 0.587 * DESTAQUE[1] + 0.114 * DESTAQUE[2] > 165
DESTAQUE_LINHA = _escurece(DESTAQUE, 0.88) if ACENTO_CLARO else DESTAQUE   # contorno, clique, fluxo
DESTAQUE_NUM = _escurece(DESTAQUE, 0.78) if ACENTO_CLARO else DESTAQUE     # número em fundo branco
SOBRE_DESTAQUE = TINTA if ACENTO_CLARO else BRANCO                          # texto em cima da pílula
LINHA_LARG = 5 if ACENTO_CLARO else 4
MARCA_TEXTO = hexa(MAPA["marca_texto"]) if MAPA.get("marca_texto") else \
    (_clareia(DESTAQUE, 0.45) if ACENTO_CLARO else hexa("#B3D7FF"))        # padrão: seleção azul do macOS
BORDA_JANELA = hexa(MAPA["borda_janela"]) if MAPA.get("borda_janela") else \
    (_escurece(DESTAQUE, 0.92) if ACENTO_CLARO else hexa("#548FD6"))
CINZA = (128, 128, 132)
CINZA_CLARO = (232, 232, 235)

# ---------------------------------------------------------------- fontes (variáveis do sistema)
_SF = "/System/Library/Fonts/SFNS.ttf"
_NYI = "/System/Library/Fonts/NewYorkItalic.ttf"
FONTES = {
    "sans": (_SF, "Bold"), "sans_semi": (_SF, "Semibold"), "sans_heavy": (_SF, "Heavy"),
    "sans_medio": (_SF, "Medium"), "serifa": (_NYI, "Bold Italic"), "serifa_semi": (_NYI, "Semibold Italic"),
}


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, var = FONTES[tipo]
    f = ImageFont.truetype(arq, max(6, int(size)))
    f.set_variation_by_name(var)
    return f


for _k in FONTES:
    F(_k, 20)

# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "card_escala": 0.84,   # dividida: tamanho do vídeo da pessoa dentro do cartão (margem lateral = sobra)
    "cabeca": 0.50,        # dividida: topo do cabelo nesta fração da altura (referência: 51-58%)
    "card_corte": 0.22,    # borda de cima do cartão: tanto do "rosto" do Vision abaixo do topo dele
    "card_raio": 84,       # cantos do cartão (referência: ~8% da largura)
    "leg_acima": 92,       # dividida: centro da legenda tantos px acima do topo do cabelo
    "leg_tam": 72,         # legenda SF Pro Bold
    "palco_topo": 150,     # nada sobe acima disto (barra do Instagram)
    "palco_folga": 64,     # espaço entre o elemento e a legenda
    "cheia_palco": [0.12, 0.54],   # cheia: faixa vertical do elemento
    "cheia_leg": 0.61,     # cheia: centro da legenda
    "rosto_zoom": 1.18,    # close: zoom no rosto
    "rosto_cy": 0.34,      # close: centro do rosto nesta fração da altura
    "rosto_leg": 170,      # close: legenda tantos px abaixo da base do "rosto" do Vision (≈ queixo)
    "leg_max": 0.76,       # legenda nunca desce além disto (interface do Instagram)
}
LAY.update(MAPA.get("layout", {}))

# dividida: geometria do cartão (fixa no vídeo inteiro; cada tomada só alinha o topo do cabelo)
S_CARD = float(LAY["card_escala"])
WS, HS = int(W * S_CARD) // 2 * 2, int(H * S_CARD) // 2 * 2
X_CARD = (W - WS) // 2
Y_CABECA = int(H * LAY["cabeca"])
CARD_TOPO = int(Y_CABECA + np.median([(g["rosto"][1] + LAY["card_corte"] * g["rosto"][3] - g["topo"]) * S_CARD
                                      for g in MED]))
LEG_DIV = Y_CABECA - LAY["leg_acima"]


def dy_card(t: float) -> int:
    return int(Y_CABECA - MED[grupo(t)]["topo"] * S_CARD)


# ---------------------------------------------------------------- utilidades de imagem
def cola_centro(dest: Image.Image, im: Image.Image | None, cx: float, cy: float) -> None:
    if im is None:
        return
    x, y = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
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


def escala(im: Image.Image, s: float) -> Image.Image:
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.BICUBIC)


def surge(im: Image.Image | None, k: float, escala0: float = 0.86, raio0: float = 16) -> Image.Image | None:
    """Entrada da referência: nasce menor, borrado e transparente e assenta em ~0,2 s."""
    if im is None or k <= 0:
        return None
    if k >= 1:
        return im
    k = ease_out(k)
    s = lerp(escala0, 1, k)
    w, h = max(2, int(im.width * s)), max(2, int(im.height * s))
    r = raio0 * (1 - k)
    m = int(r * 2) + 2
    tmp = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    tmp.alpha_composite(im.resize((w, h), Image.BILINEAR), (m, m))
    return opaco(desfoca(tmp, r), k)


def k_in(t: float, t0: float, d: float = 0.22) -> float:
    return cl((t - t0) / d)


SOMBRA_M = 40


@functools.lru_cache(maxsize=256)
def cartao(w: int, h: int, r: int = 22, fundo: tuple = BRANCO, sombra: float = 0.16,
           borda: tuple | None = None, bw: int = 0) -> Image.Image:
    """Card arredondado com sombra suave. Margem SOMBRA_M em volta (conteúdo começa em (M, M))."""
    M = SOMBRA_M
    im = Image.new("RGBA", (w + 2 * M, h + 2 * M), (0, 0, 0, 0))
    if sombra:
        s = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((M, M + 10, M + w, M + h + 10), radius=r,
                                            fill=(0, 0, 0, int(255 * sombra)))
        im.alpha_composite(s.filter(ImageFilter.GaussianBlur(16)))
    ImageDraw.Draw(im).rounded_rectangle((M, M, M + w - 1, M + h - 1), radius=r, fill=fundo + (255,),
                                         outline=(borda + (255,)) if borda else None, width=bw)
    return im


@functools.lru_cache(maxsize=64)
def mascara_arred(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    return m


def arredonda(im: Image.Image, r: int) -> Image.Image:
    out = im.convert("RGBA").copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mascara_arred(im.width, im.height, r)))
    return out


def com_sombra(im: Image.Image, r: int = 22, sombra: float = 0.18) -> Image.Image:
    base = cartao(im.width, im.height, r, sombra=sombra).copy()
    base.alpha_composite(arredonda(im, r), (SOMBRA_M, SOMBRA_M))
    return base


def contem(im: Image.Image, w: float, h: float) -> Image.Image:
    s = min(w / im.width, h / im.height)
    return im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)


def cobre(im: Image.Image, w: int, h: int, alto: bool = False, oy: float = 0.0) -> Image.Image:
    """Cobre w x h e corta. alto=True mantém o topo (documento); oy = deslocamento extra (rolagem, 0-1)."""
    esc = max(w / im.width, h / im.height)
    r = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
    x = (r.width - w) // 2
    sobra = r.height - h
    y = int(sobra * oy) if alto else sobra // 2
    return r.crop((x, y, x + w, y + h))


def degrade_v(w: int, h: int, c0: tuple, c1: tuple) -> Image.Image:
    k = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(c0, np.float32) * (1 - k) + np.array(c1, np.float32) * k
    arr = np.repeat(arr, w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def mascara_texto(txt: str, f: ImageFont.FreeTypeFont, pad: int = 30) -> Image.Image:
    l, t, r, b = f.getbbox(txt)
    w, h = int(r - l) + 2 * pad, int(f.size * 1.5) + 2 * pad
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((w / 2, h / 2), txt, font=f, fill=255, anchor="mm")
    return m


def texto(txt: str, tipo: str, tam: float, cor: tuple, sombra: float = 0.0, degrade: tuple | None = None,
          brilho: tuple | None = None) -> Image.Image:
    """Texto solto com sombra opcional, degradê vertical (c0, c1) e brilho colorido por baixo."""
    m = mascara_texto(txt, F(tipo, int(tam)))
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    if brilho:
        g = Image.new("RGBA", m.size, brilho + (255,))
        g.putalpha(m.filter(ImageFilter.GaussianBlur(tam * 0.28)).point(lambda v: int(min(255, v * 1.6))))
        im.alpha_composite(g, (0, int(tam * 0.12)))
    if sombra:   # sombra justa + halo largo e fraco (lê em cima de roupa e parede claras)
        for raio, forca in ((tam * 0.22, 0.45), (max(3, tam * 0.07), 1.0)):
            s = Image.new("RGBA", m.size, (0, 0, 0, 255))
            s.putalpha(m.filter(ImageFilter.GaussianBlur(raio)).point(lambda v, f=forca: int(min(255, v * sombra * f))))
            im.alpha_composite(s, (0, max(2, int(tam * 0.04))))
    corpo = degrade_v(m.width, m.height, *degrade) if degrade else Image.new("RGBA", m.size, cor + (255,))
    corpo.putalpha(m)
    im.alpha_composite(corpo)
    return im


def recorta_vazio(im: Image.Image) -> Image.Image:
    bb = im.getchannel("A").getbbox()
    return im.crop(bb) if bb else im


# ---------------------------------------------------------------- arquivos e vídeos
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


def e_video(arq: str) -> bool:
    return Path(arq).suffix.lower() in (".mov", ".mp4", ".m4v", ".webm")


@functools.lru_cache(maxsize=96)
def imagem(arq: str, recorte: tuple | None = None) -> Image.Image:
    im = Image.open(_resolve(arq)).convert("RGBA")
    if recorte:
        x, y, w, h = recorte
        im = im.crop((x, y, x + w, y + h))
    return im


class LeitorVideo:
    """Um ffmpeg por vídeo, aberto no 1º quadro em que ele aparece; entrega quadros cw x ch (cobre e recorta)."""

    def __init__(self, arq: Path, inicio: float, vel: float, crop, cw: int, ch: int, t0: float, alto: bool = True):
        self.arq, self.inicio, self.vel, self.crop, self.alto = arq, inicio, vel, crop, alto
        self.cw, self.ch, self.t0 = cw // 2 * 2, ch // 2 * 2, t0
        self.proc, self.ultimo, self.k = None, None, 0

    def vf(self, com_vel: bool = True) -> str:
        c = self.crop
        y = "0" if self.alto else "(ih-oh)/2"
        return ((f"crop={c[2]}:{c[3]}:{c[0]}:{c[1]}," if c else "") +
                (f"setpts=PTS/{self.vel}," if com_vel else "") +
                f"scale={self.cw}:{self.ch}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={self.cw}:{self.ch}:(iw-ow)/2:{y},fps={FPS_NUM}/{FPS_DEN}")

    def quadro(self, t: float) -> Image.Image:
        tam = self.cw * self.ch * 3
        if ARGS.so_quadros or ARGS.storyboard:   # quadro avulso: busca direto no tempo
            src = self.inicio + (t - self.t0) * self.vel
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, src):.3f}", "-i", str(self.arq),
                                  "-frames:v", "1", "-vf", self.vf(False), "-f", "rawvideo", "-pix_fmt", "rgb24",
                                  "-"], capture_output=True, check=True).stdout
            return Image.frombytes("RGB", (self.cw, self.ch), raw[:tam]).convert("RGBA")
        if self.proc is None:
            self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{self.inicio:.3f}", "-i", str(self.arq),
                                          "-an", "-vf", self.vf(), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                         stdout=subprocess.PIPE)
        alvo = int((t - self.t0) * FPS + 1e-6)
        while self.k <= alvo:
            buf = self.proc.stdout.read(tam)
            if len(buf) == tam:
                self.ultimo = Image.frombytes("RGB", (self.cw, self.ch), buf).convert("RGBA")
            self.k += 1
        return self.ultimo if self.ultimo is not None else Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 255))

    def fecha(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc = None


def tamanho_fonte(arq: str, recorte) -> tuple[int, int]:
    if recorte:
        return int(recorte[2]), int(recorte[3])
    if e_video(arq):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", str(_resolve(arq))],
                             capture_output=True, text=True, check=True).stdout.strip().split(",")
        return int(out[0]), int(out[1])
    im = imagem(arq)
    return im.width, im.height


class Midia:
    """Imagem ou vídeo entregue em cw x ch (cobre). Vídeo abre um LeitorVideo."""

    def __init__(self, spec: dict, cw: int, ch: int, t0: float, alto: bool = True):
        self.arq = spec["arquivo"]
        self.rec = tuple(spec["recorte"]) if spec.get("recorte") else None
        self.cw, self.ch, self.alto = cw // 2 * 2, ch // 2 * 2, alto
        self.leitor = None
        if e_video(self.arq):
            self.leitor = LeitorVideo(_resolve(self.arq), float(spec.get("inicio", 0)),
                                      float(spec.get("velocidade", 1)), self.rec, self.cw, self.ch, t0, alto)

    def quadro(self, t: float, oy: float = 0.0) -> Image.Image:
        if self.leitor:
            return self.leitor.quadro(t)
        return self._img(round(oy, 3))

    @functools.lru_cache(maxsize=8)
    def _img(self, oy: float) -> Image.Image:
        return cobre(imagem(self.arq, self.rec), self.cw, self.ch, self.alto, oy)

    def fecha(self) -> None:
        if self.leitor:
            self.leitor.fecha()


# ================================================================ ELEMENTOS
class Elemento:
    claro_proprio = None      # True/False quando o elemento cobre o fundo (foto, vídeo de tela cheia)
    sem_legenda = False       # o card do item esconde a legenda (a referência não legenda o "THE SECOND")

    def __init__(self, spec: dict, cena: "Cena"):
        self.spec, self.cena = spec, cena
        self.t0, self.t1 = cena.t0, cena.t1

    def desenha(self, cv: Image.Image, t: float, box: tuple) -> None:
        pass

    def eventos(self) -> list[tuple[float, str]]:
        return []

    def itens_tempos(self) -> list[tuple[str, float]]:
        return []

    def fecha(self) -> None:
        pass


def logo_img(it: dict, alt: float, claro: bool) -> Image.Image:
    """Logo/ícone (arquivo) ou marca em texto ("texto"), com altura alt."""
    if it.get("arquivo"):
        im = recorta_vazio(imagem(it["arquivo"]))
        im = contem(im, alt * float(it.get("proporcao_max", 2.6)), alt)
        if it.get("texto"):   # ícone + nome ao lado (ex.: "Google AI Studio")
            tx = recorta_vazio(texto(it["texto"], "sans_semi", alt * 0.42, TINTA if claro else BRANCO))
            out = Image.new("RGBA", (im.width + 24 + tx.width, max(im.height, tx.height)), (0, 0, 0, 0))
            out.alpha_composite(im, (0, (out.height - im.height) // 2))
            out.alpha_composite(tx, (im.width + 24, (out.height - tx.height) // 2))
            return out
        return im
    return recorta_vazio(texto(it["texto"], "sans_semi", alt * 0.42, TINTA if claro else BRANCO))


class Logos(Elemento):
    """Logo novo nasce grande no centro; o anterior encolhe e desce pra fileira de baixo (v3 9-12 s)."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.itens = spec["itens"]
        self.tis = [T_na(it["em"]) if "em" in it else self.t0 for it in self.itens]

    def itens_tempos(self):
        return [(it.get("texto") or Path(it.get("arquivo", "?")).stem, ti) for it, ti in zip(self.itens, self.tis)]

    def eventos(self):
        return [(ti, "pop") for ti in self.tis]

    @functools.lru_cache(maxsize=64)
    def _img(self, i: int, alt: int) -> Image.Image:
        return logo_img(self.itens[i], alt, self.cena.claro)

    def desenha(self, cv, t, box):
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        big = int(min(bh * 0.6, 380, bw * 0.5))
        row = int(min(84, big * 0.26))
        gap = 34
        cx = (x0 + x1) / 2
        c = max([i for i, ti in enumerate(self.tis) if ti <= t], default=-1)
        if c < 0:
            return
        # centraliza pela altura real do grande (marca em texto é baixa; logo é quadrado)
        hb = min(big, self._img(c, big).height * min(1.0, bw * 0.92 / self._img(c, big).width))
        cy_big = y0 + (bh - (hb + gap + row)) / 2 + hb / 2
        cy_row = cy_big + hb / 2 + gap + row / 2
        k = ease_out(k_in(t, self.tis[c], 0.25))

        def fileira(n: int) -> list[float]:
            ws = [self._img(i, row).width for i in range(n)]
            tot = sum(ws) + 22 * max(0, n - 1)
            xs, x = [], cx - tot / 2
            for w in ws:
                xs.append(x + w / 2)
                x += w + 22
            return xs

        novos, velhos = fileira(c), fileira(c - 1) if c > 0 else []
        for i in range(c):
            im = self._img(i, row)
            if i < c - 1:
                x = lerp(velhos[i], novos[i], k)
                cola_centro(cv, im, x, cy_row)
            else:   # o que era grande encolhe até a fileira
                g = self._img(i, big)
                if g.width > bw * 0.92:
                    g = escala(g, bw * 0.92 / g.width)
                alvo = self._img(i, row).width / g.width        # chega com a largura que terá na fileira
                s = lerp(1.0, alvo, ease_out(min(1.0, k * 1.8)))   # encolhe antes de andar
                cola_centro(cv, escala(g, s), lerp(cx, novos[i], k), lerp(cy_big, cy_row, k))
        g = self._img(c, big)
        if g.width > bw * 0.92:   # marca em texto comprida: encolhe pra caber
            g = escala(g, bw * 0.92 / g.width)
        cola_centro(cv, surge(g, k_in(t, self.tis[c], 0.22)), cx, cy_big)


class Item(Elemento):
    """Card do item da lista: ordinal em serifa itálica salmão, ícone em quadrado arredondado, nome
    em serifa itálica cinza metálico (v3 14,4 s). Esconde a legenda."""
    sem_legenda = True

    def eventos(self):
        return [(self.t0, "pop")]

    @functools.lru_cache(maxsize=4)
    def _partes(self, lado: int):
        sp = self.spec
        ic = None
        if sp.get("arquivo"):
            ic = recorta_vazio(imagem(sp["arquivo"]))
            if sp.get("fundo_icone", False):   # logo solto vira ícone de app: quadrado branco com sombra
                pad = int(lado * 0.2)
                lg = contem(ic, lado - 2 * pad, lado - 2 * pad)
                card = cartao(lado, lado, int(lado * 0.23), sombra=0.18).copy()
                cola_centro(card, lg, card.width / 2, card.height / 2)
                ic = card
            else:   # ícone de app (já vem com o quadrado arredondado): só ganha sombra
                ic = contem(ic, lado, lado)
                sh = Image.new("RGBA", (ic.width + 80, ic.height + 80), (0, 0, 0, 0))
                a = ic.getchannel("A").filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.25))
                s = Image.new("RGBA", ic.size, (0, 0, 0, 255))
                s.putalpha(a)
                sh.alpha_composite(s, (40, 52))
                sh.alpha_composite(ic, (40, 40))
                ic = sh
        claro = self.cena.claro
        ordem = sp.get("ordem")
        o = texto(ordem.upper(), "serifa", 70, DESTAQUE2,
                  degrade=(tuple(int(c * 0.9) for c in DESTAQUE2), tuple(int(lerp(c, 255, 0.3)) for c in DESTAQUE2))) if ordem else None
        nome = sp.get("nome")
        cinza = ((30, 30, 32), (165, 165, 170)) if claro else ((255, 255, 255), (150, 150, 158))
        n = texto(nome.upper(), "serifa", 92, BRANCO, sombra=0.35, degrade=cinza) if nome else None
        return ic, (recorta_vazio(o) if o else None), (recorta_vazio(n) if n else None)

    def desenha(self, cv, t, box):
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + 40
        lado = int(min(430, (y1 - y0) * 0.62))
        ic, o, n = self._partes(lado)
        if ic is not None:
            cola_centro(cv, surge(ic, k_in(t, self.t0)), cx, cy)
        h2 = lado / 2
        if o is not None:   # ordinal encostado em cima do ícone, nome logo embaixo (v3 15 s)
            cola_centro(cv, surge(o, k_in(t, self.t0 + 0.05)), cx, cy - h2 - o.height / 2 - 14)
        if n is not None:
            cola_centro(cv, surge(n, k_in(t, self.t0 + 0.12)), cx, cy + h2 + n.height / 2 + 18)


def cursor_img(tam: int = 46) -> Image.Image:
    """Seta do macOS: preta com contorno branco."""
    s = tam / 24
    pts = [(1, 1), (1, 18), (5.5, 14), (8.5, 21), (11.5, 19.8), (8.6, 13), (14.5, 13)]
    im = Image.new("RGBA", (int(26 * s), int(26 * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(x * s, y * s) for x, y in pts], fill=(0, 0, 0, 255), outline=(255, 255, 255, 255), width=max(2, int(s * 1.4)))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.35))
    sh.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (2, 3), a)
    sh.alpha_composite(im)
    return sh


CURSOR = None


def odometro(valor: float, alvo: int, f: ImageFont.FreeTypeFont, cor: tuple, prefixo: str = "",
             sufixo: str = "") -> Image.Image:
    """Número que roda dígito a dígito (as unidades giram, a dezena vira quando a unidade passa do 9)."""
    x = max(0.0, valor)
    fr = x - math.floor(x)
    inteiro = int(math.floor(x))
    # só os dígitos que já existem (sem buraco entre o prefixo e o número enquanto ele cresce)
    nd = min(len(str(abs(int(alvo)))), len(str(inteiro + (1 if fr > 0.5 else 0))))
    lh = int(f.size * 1.08)
    dw = int(max(f.getlength(str(d)) for d in range(10)))
    pw = int(f.getlength(prefixo)) if prefixo else 0
    sw = int(f.getlength(sufixo)) if sufixo else 0
    im = Image.new("RGBA", (pw + nd * dw + sw + 8, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if prefixo:
        d.text((0, lh / 2), prefixo, font=f, fill=cor + (255,), anchor="lm")
    for i in range(nd):          # i = posição a partir da direita
        dig = (inteiro // 10 ** i) % 10
        rola = fr if all(((inteiro // 10 ** j) % 10) == 9 for j in range(i)) else 0.0
        col = Image.new("RGBA", (dw, lh), (0, 0, 0, 0))
        dc = ImageDraw.Draw(col)
        off = -rola * lh
        dc.text((dw / 2, lh / 2 + off), str(dig), font=f, fill=cor + (255,), anchor="mm")
        dc.text((dw / 2, lh / 2 + off + lh), str((dig + 1) % 10), font=f, fill=cor + (255,), anchor="mm")
        if 0.02 < rola < 0.98:
            col = col.filter(ImageFilter.GaussianBlur(1.2))
        im.alpha_composite(col, (pw + (nd - 1 - i) * dw, 0))
    if sufixo:
        d.text((pw + nd * dw + 4, lh / 2), sufixo, font=f, fill=cor + (255,), anchor="lm")
    return im


def valor_contador(t: float, t0: float, de: float, ate: float, dur: float) -> float:
    return lerp(de, ate, ease_out((t - t0) / dur))


class Janela(Elemento):
    """Janela do Safari desenhada com a página real dentro (v1). Dentro: marca-texto, contorno,
    clique no botão, balão com contador. Coordenadas em px da fonte (já recortada)."""

    BARRA = 60

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.sw, self.sh = tamanho_fonte(spec["arquivo"], spec.get("recorte"))
        self.midia = None
        self.geo = None

    def _geo(self, box):
        if self.geo is None:
            x0, y0, x1, y1 = box
            ww = int(min((x1 - x0) * float(self.spec.get("largura", 0.94)), 980))
            cw = ww - 4
            ch_nat = cw * self.sh / self.sw
            ch = int(min(ch_nat, (y1 - y0) - self.BARRA - 30, float(self.spec.get("altura_max", 9e9))))
            self.geo = (ww, cw, ch, cw / self.sw)
            self.midia = Midia(self.spec, cw, ch, self.t0, alto=True)
        return self.geo

    def _oy(self, t):
        rol = self.spec.get("rolagem")
        if not rol:
            return 0.0
        # "rolagem": [[palavra, tomada, fração 0-1, duração?], ...] (ou [segundos, fração, duração?]):
        # parada até a palavra, depois rola até a fração em "duração" s (padrão 0,8). Começa no topo.
        v = 0.0
        for r in rol:
            quando, resto = (r[:2], r[2:]) if isinstance(r[0], str) else (r[0], r[1:])
            ta, alvo, dur = T_na(quando), float(resto[0]), float(resto[1]) if len(resto) > 1 else 0.8
            if t < ta:
                break
            v = lerp(v, alvo, ease_in_out((t - ta) / dur))
        return v

    def eventos(self):
        ev = [(T_na(c["em"]), "clique") for c in self.spec.get("cliques", [])]
        ev += [(T_na(c["em"]), "pop") for c in self.spec.get("contornos", [])]
        if self.spec.get("contador"):
            ev.append((T_na(self.spec["contador"]["em"]), "pop"))
        return ev

    def itens_tempos(self):
        out = []
        for nome in ("marcas", "contornos", "cliques"):
            out += [(f"{nome[:-1]} {i + 1}", T_na(c["em"])) for i, c in enumerate(self.spec.get(nome, []))]
        return out

    @functools.lru_cache(maxsize=4)
    def _moldura(self, ww: int, ch: int, url: str) -> Image.Image:
        """Janela vazia: barra com bolinhas e endereço, contorno azul fino com brilho."""
        hh = self.BARRA + ch + 4
        r = 24
        M = SOMBRA_M
        im = cartao(ww, hh, r, sombra=0.20).copy()
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((M, M, M + ww - 1, M + self.BARRA + r), radius=r, fill=(246, 246, 247, 255))
        d.rectangle((M, M + self.BARRA - 1, M + ww - 1, M + self.BARRA + r), fill=(255, 255, 255, 255))
        d.line((M, M + self.BARRA - 1, M + ww - 1, M + self.BARRA - 1), fill=(222, 222, 226, 255), width=2)
        for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            cx = M + 30 + i * 26
            d.ellipse((cx - 8, M + 22, cx + 8, M + 38), fill=c + (255,))
        pw = int(ww * 0.52)
        px = M + (ww - pw) // 2
        d.rounded_rectangle((px, M + 13, px + pw, M + 47), radius=10, fill=(232, 232, 236, 255))
        fu = F("sans_medio", 22)
        if url:
            tw = fu.getlength(url)
            lx = M + ww / 2 - tw / 2 + 10
            d.text((lx, M + 30), url, font=fu, fill=(70, 70, 75, 255), anchor="lm")
            cx = lx - 18   # cadeado
            d.rounded_rectangle((cx - 7, M + 29, cx + 7, M + 40), radius=2, fill=(110, 110, 115, 255))
            d.arc((cx - 5, M + 21, cx + 5, M + 33), 180, 360, fill=(110, 110, 115, 255), width=2)
        borda = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(borda).rounded_rectangle((M, M, M + ww - 1, M + hh - 1), radius=r,
                                                outline=BORDA_JANELA + (255,), width=3)
        brilho = borda.filter(ImageFilter.GaussianBlur(7))
        im.alpha_composite(brilho)
        im.alpha_composite(borda)
        return im

    def desenha(self, cv, t, box):
        ww, cw, ch, s = self._geo(box)
        sp = self.spec
        oy = self._oy(t)
        cont = self.midia.quadro(t, oy).copy()
        # deslocamento vertical da fonte por causa da rolagem (pra marcas acompanharem a página)
        alt_tot = self.sh * s
        desl = (alt_tot - ch) * oy if alt_tot > ch else 0.0

        def p(x, y):
            return x * s, y * s - desl

        d = ImageDraw.Draw(cont)
        for mk in sp.get("marcas", []):        # marca-texto correndo pela frase
            ta = T_na(mk["em"])
            dur = float(mk.get("dur", 0.6)) if "ate" not in mk else max(0.1, T_na(mk["ate"]) - ta)
            k = ease_in_out((t - ta) / dur)
            if k <= 0:
                continue
            x, y, w, h = mk["caixa"]
            ax, ay = p(x, y)
            bx, by = p(x + w * k, y + h)
            reg = cont.crop((int(ax), int(ay), max(int(ax) + 1, int(bx)), int(by))).convert("RGB")
            tint = Image.new("RGB", reg.size, MARCA_TEXTO)
            cont.paste(ImageChops.multiply(reg, tint).convert("RGBA"), (int(ax), int(ay)))
        for ct in sp.get("contornos", []):     # contorno arredondado em volta do número/palavra
            ta = T_na(ct["em"])
            if t < ta:
                continue
            k = ease_out((t - ta) / 0.18)
            x, y, w, h = ct["caixa"]
            ax, ay = p(x, y)
            bx, by = p(x + w, y + h)
            sx = lerp(1.15, 1, k)
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            hw, hh = (bx - ax) / 2 * sx + 8, (by - ay) / 2 * sx + 6
            d.rounded_rectangle((cx - hw, cy - hh, cx + hw, cy + hh), radius=12,
                                outline=DESTAQUE_LINHA + (int(255 * k),), width=LINHA_LARG)
        janela = self._moldura(ww, ch, sp.get("url", "")).copy()
        M = SOMBRA_M
        x0j, y0j = M + 2, M + self.BARRA
        # o canto de baixo da página segue o arredondado da janela
        cw_, ch_ = cont.size
        canto = mascara_arred(cw_, ch_ + 40, 22).crop((0, 40, cw_, ch_ + 40))
        janela.paste(cont, (x0j, y0j), canto)
        # cliques: cursor vai até o ponto e o botão ganha contorno na palavra
        cliques = sp.get("cliques", [])
        global CURSOR
        if cliques:
            if CURSOR is None:
                CURSOR = cursor_img()
            repouso = (cw * 0.82 / s, ch * 0.9 / s + desl / s)   # cursor parado no canto antes do 1º clique
            pos = repouso
            ant = repouso
            for c in cliques:
                tc = T_na(c["em"])
                alvo = c["ponto"]
                if t >= tc - 0.35:
                    k = ease_in_out((t - (tc - 0.35)) / 0.35)
                    pos = (lerp(ant[0], alvo[0], k), lerp(ant[1], alvo[1], k))
                    if t >= tc and c.get("caixa"):
                        x, y, w, h = c["caixa"]
                        ax, ay = p(x, y)
                        bx, by = p(x + w, y + h)
                        ImageDraw.Draw(janela).rounded_rectangle(
                            (x0j + ax - 6, y0j + ay - 6, x0j + bx + 6, y0j + by + 6), radius=14,
                            outline=DESTAQUE_LINHA + (255,), width=LINHA_LARG)
                ant = alvo
            if pos is not None:
                px, py = p(*pos)
                cs = CURSOR
                ultimo = max([T_na(c["em"]) for c in cliques if T_na(c["em"]) <= t], default=-9)
                if 0 <= t - ultimo < 0.12:
                    cs = escala(CURSOR, 0.86)
                janela.alpha_composite(cs, (int(x0j + px - 3), int(y0j + py - 3)))
        ctd = sp.get("contador")
        if ctd and t >= T_na(ctd["em"]):          # balão branco com o número rodando
            ta = T_na(ctd["em"])
            v = valor_contador(t, ta, float(ctd.get("de", 0)), float(ctd["valor"]), float(ctd.get("dur", 0.7)))
            num = odometro(v, int(ctd["valor"]), F("sans", int(ctd.get("tam", 110))), DESTAQUE_NUM,
                           ctd.get("prefixo", ""), ctd.get("sufixo", ""))
            rot = texto(ctd["rotulo"], "sans_semi", 30, CINZA) if ctd.get("rotulo") else None
            bw_ = max(num.width, rot.width - 40 if rot else 0) + 60
            bh_ = num.height + (34 if rot else 0) + 36
            bal = cartao(bw_, bh_, 22, sombra=0.22).copy()
            bal.alpha_composite(num, (SOMBRA_M + (bw_ - num.width) // 2, SOMBRA_M + 14))
            if rot:
                cola_centro(bal, rot, bal.width / 2, SOMBRA_M + 14 + num.height + 12)
            if "ponto" in ctd:
                px, py = p(*ctd["ponto"])
                cx, cy = x0j + px, y0j + py
            else:
                cx, cy = janela.width / 2, y0j + ch * 0.62
            cola_centro(janela, surge(bal, k_in(t, ta, 0.2)), cx, cy)
        x0, y0, x1, y1 = box
        cola_centro(cv, surge(janela, k_in(t, self.t0)), (x0 + x1) / 2, (y0 + y1) / 2)

    def fecha(self):
        if self.midia:
            self.midia.fecha()


class Contador(Elemento):
    """Número grande rodando dígito a dígito + rótulo (v1 8,5 s; v3 7,5 s). "valor" = número final
    ("ate" é a hora de a cena sair, como em toda cena)."""

    def eventos(self):
        return [(T_na(self.spec["em_numero"]) if "em_numero" in self.spec else self.t0, "pop")]

    def desenha(self, cv, t, box):
        sp = self.spec
        x0, y0, x1, y1 = box
        ta = T_na(sp["em_numero"]) if "em_numero" in sp else self.t0
        cor = hexa(sp["cor"]) if sp.get("cor") else \
            (DESTAQUE_NUM if self.cena.claro else (DESTAQUE if ACENTO_CLARO else BRANCO))
        v = valor_contador(t, ta, float(sp.get("de", 0)), float(sp["valor"]), float(sp.get("dur", 0.9)))
        tam = int(sp.get("tam", 230))
        num = odometro(v, int(sp["valor"]), F("sans", tam), cor, sp.get("prefixo", ""), sp.get("sufixo", ""))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 30
        cola_centro(cv, surge(num, k_in(t, self.t0)), cx, cy)
        if sp.get("rotulo"):
            rot = texto(sp["rotulo"], "sans_semi", 46, (90, 90, 96) if self.cena.claro else (220, 220, 226))
            cola_centro(cv, surge(rot, k_in(t, self.t0 + 0.08)), cx, cy + num.height / 2 + 40)


def no_img(it: dict, claro: bool, lado: int = 118) -> Image.Image:
    """Nó do fluxo: ícone em card branco arredondado, ou pílula com texto."""
    if it.get("arquivo"):
        card = cartao(lado, lado, 26, sombra=0.14).copy()
        lg = contem(recorta_vazio(imagem(it["arquivo"])), lado * 0.66, lado * 0.66)
        cola_centro(card, lg, card.width / 2, card.height / 2)
        return card
    linhas = it["rotulo"].split("\n")
    f = F("sans_semi", int(it.get("tam", 46)))
    tw = int(max(f.getlength(l) for l in linhas)) + 56
    th = int(f.size * 1.25 * len(linhas)) + 34
    card = cartao(tw, th, 22, sombra=0.14).copy()
    d = ImageDraw.Draw(card)
    cor = hexa(it["cor"]) if it.get("cor") else TINTA
    for i, l in enumerate(linhas):
        d.text((card.width / 2, SOMBRA_M + 17 + f.size * 1.25 * (i + 0.5)), l, font=f, fill=cor + (255,), anchor="mm")
    return card


def doc_img(lado: int = 120, rotulo: str | None = None) -> Image.Image:
    """Documento no centro do fluxo (v3 30 s): card branco com o desenho de uma folha."""
    card = cartao(lado, lado, 26, sombra=0.14).copy()
    d = ImageDraw.Draw(card)
    M = SOMBRA_M
    w, h = lado * 0.36, lado * 0.46
    x, y = M + (lado - w) / 2, M + (lado - h) / 2
    d.polygon([(x, y), (x + w * 0.68, y), (x + w, y + h * 0.26), (x + w, y + h), (x, y + h)], outline=(40, 40, 44, 255),
              width=4)
    for i in range(3):
        yy = y + h * (0.45 + i * 0.17)
        d.line((x + w * 0.2, yy, x + w * 0.8, yy), fill=(40, 40, 44, 255), width=3)
    if rotulo:
        tx = texto(rotulo, "sans_semi", 42, TINTA)
        out = Image.new("RGBA", (max(card.width, tx.width), card.height + tx.height - 30), (0, 0, 0, 0))
        out.alpha_composite(card, ((out.width - card.width) // 2, 0))
        out.alpha_composite(tx, ((out.width - tx.width) // 2, card.height - 46))
        return out
    return card


def bezier(p0, p1, p2, p3, n=40, k=1.0):
    pts = []
    for i in range(int(n * k) + 1):
        u = i / n
        a = (1 - u) ** 3
        b = 3 * u * (1 - u) ** 2
        c = 3 * u ** 2 * (1 - u)
        e = u ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + e * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + e * p3[1]))
    return pts


class Fluxo(Elemento):
    """Nós nascendo um por um, ligados por linha curva ao centro (v3 30-33 s).
    sentido "entra": nós em arco em cima, centro embaixo (fontes → resultado).
    sentido "sai": centro em cima, nós embaixo (uma coisa → várias)."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.itens = spec["itens"]
        self.tis = [T_na(it["em"]) if "em" in it else self.t0 for it in self.itens]

    def itens_tempos(self):
        return [(it.get("rotulo") or Path(it.get("arquivo", "?")).stem, ti) for it, ti in zip(self.itens, self.tis)]

    def eventos(self):
        return [(ti, "pop") for ti in self.tis]

    @functools.lru_cache(maxsize=32)
    def _no(self, i):
        return no_img(self.itens[i], self.cena.claro)

    @functools.lru_cache(maxsize=2)
    def _centro(self):
        c = self.spec.get("centro", {})
        if c.get("arquivo") or (c.get("rotulo") and not c.get("doc", True)):
            return no_img(c, self.cena.claro, 170)
        return doc_img(170, c.get("rotulo"))

    def desenha(self, cv, t, box):
        x0, y0, x1, y1 = box
        sai = self.spec.get("sentido", "entra") == "sai"
        n = len(self.itens)
        cen = self._centro()
        cx = (x0 + x1) / 2
        y_cen = y0 + cen.height / 2 + 10 if sai else y1 - cen.height / 2 - 10
        y_nos = y1 - 110 if sai else y0 + 90
        larg = [self._no(i).width - 2 * SOMBRA_M for i in range(n)]
        tot = sum(larg)
        folga = max(20, ((x1 - x0) - tot) / max(1, n))
        xs, x = [], cx - (tot + folga * (n - 1)) / 2
        for w in larg:
            xs.append(x + w / 2)
            x += w + folga
        arco = float(self.spec.get("arco", 60))
        d = ImageDraw.Draw(cv)
        meio = (n - 1) / 2
        ys = [y_nos + (arco * (1 - (abs(i - meio) / max(1, meio)) ** 2) * (1 if sai else -1)) * (1 if n > 2 else 0)
              for i in range(n)]
        # linhas primeiro (passam por baixo dos cards)
        for i in range(n):
            k = ease_in_out((t - self.tis[i] - 0.05) / 0.4)
            if k <= 0:
                continue
            no = self._no(i)
            nh = (no.height - 2 * SOMBRA_M) / 2
            cor = hexa(self.itens[i]["cor_linha"]) if self.itens[i].get("cor_linha") else DESTAQUE_LINHA
            if sai:
                a = (cx, y_cen + cen.height / 2 - SOMBRA_M + 4)
                b = (xs[i], ys[i] - nh)
            else:
                a = (xs[i], ys[i] + nh)
                b = (cx, y_cen - cen.height / 2 + SOMBRA_M + 6)
            mid = (a[1] + b[1]) / 2
            pts = bezier(a, (a[0], mid), (b[0], mid), b, 48, k)
            if len(pts) > 1:
                d.line(pts, fill=cor + (255,), width=5, joint="curve")
            if k >= 1:
                d.ellipse((b[0] - 6, b[1] - 6, b[0] + 6, b[1] + 6), fill=cor + (255,))
        cola_centro(cv, surge(cen, k_in(t, self.t0)), cx, y_cen)
        for i in range(n):
            cola_centro(cv, surge(self._no(i), k_in(t, self.tis[i])), xs[i], ys[i])


class Grafico(Elemento):
    """Gráfico de linha que se desenha durante a frase (v3 23-26 s, estrelas no GitHub)."""

    def desenha(self, cv, t, box):
        sp = self.spec
        x0, y0, x1, y1 = box
        gw, gh = int(min(900, x1 - x0)), int(min(560, y1 - y0))
        card = cartao(gw, gh, 22, sombra=0.12).copy()
        d = ImageDraw.Draw(card)
        M = SOMBRA_M
        ax0, ay0, ax1, ay1 = M + 90, M + 90, M + gw - 40, M + gh - 70
        for i in range(5):
            y = lerp(ay1, ay0, i / 4)
            d.line((ax0, y, ax1, y), fill=(236, 236, 240, 255), width=2)
        d.line((ax0, ay0, ax0, ay1), fill=(160, 160, 166, 255), width=2)
        d.line((ax0, ay1, ax1, ay1), fill=(160, 160, 166, 255), width=2)
        if sp.get("nome"):   # "titulo" é o título do gancho (da cena); o do gráfico é "nome"
            cor = hexa(sp.get("cor", "#E8735A"))
            d.ellipse((M + 34, M + 34, M + 50, M + 50), fill=cor + (255,))
            d.text((M + 62, M + 42), sp["nome"], font=F("sans_semi", 30), fill=(60, 60, 66, 255), anchor="lm")
        eixos = sp.get("eixo_x", [])
        for i, rot in enumerate(eixos):
            x = lerp(ax0, ax1, i / max(1, len(eixos) - 1))
            d.text((x, ay1 + 30), rot, font=F("sans_medio", 24), fill=(120, 120, 126, 255), anchor="mm")
        vals = [float(v) for v in sp["pontos"]]
        vmin, vmax = min(vals + [0]), max(vals)
        ta = T_na(sp["em_linha"]) if "em_linha" in sp else self.t0 + 0.15
        tb = T_na(sp["ate_linha"]) if "ate_linha" in sp else self.t1 - 0.25
        k = ease_in_out((t - ta) / max(0.1, tb - ta))
        pts = [(lerp(ax0, ax1, i / (len(vals) - 1)), lerp(ay1, ay0, (v - vmin) / max(1e-9, vmax - vmin)))
               for i, v in enumerate(vals)]
        if k > 0:
            # caminho parcial com interpolação do último trecho
            tot = len(pts) - 1
            pos = k * tot
            i = int(pos)
            parcial = pts[: i + 1]
            if i < tot:
                f = pos - i
                parcial.append((lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f)))
            cor = hexa(sp.get("cor", "#E8735A"))
            if len(parcial) > 1:
                d.line(parcial, fill=cor + (255,), width=6, joint="curve")
            ex, ey = parcial[-1]
            d.ellipse((ex - 9, ey - 9, ex + 9, ey + 9), fill=cor + (255,))
            if sp.get("valor_final") and k >= 1:
                d.text((ex - 10, ey - 36), sp["valor_final"], font=F("sans", 38), fill=cor + (255,), anchor="rm")
        cola_centro(cv, surge(card, k_in(t, self.t0)), (x0 + x1) / 2, (y0 + y1) / 2)


class Comparacao(Elemento):
    """Antes x depois: dois cards empilhados com etiqueta em pílula (v1 21-26 s)."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.midias = None

    def desenha(self, cv, t, box):
        sp = self.spec
        x0, y0, x1, y1 = box
        gap = 34
        cw = int(min(820, x1 - x0))
        ch = int(min(cw * 0.62, ((y1 - y0) - gap) / 2))
        if self.midias is None:
            self.midias = [Midia(it, cw, ch, self.t0, alto=False) for it in sp["itens"]]
        rot = sp.get("rotulos", ["antes", "depois"])
        cores = [(20, 20, 22), DESTAQUE]
        cx = (x0 + x1) / 2
        cy0 = (y0 + y1) / 2 - (ch + gap) / 2
        for i, m in enumerate(self.midias):
            im = com_sombra(m.quadro(t), 22, 0.22)
            f = F("sans", 26)
            tw = int(f.getlength(rot[i])) + 30
            pil = Image.new("RGBA", (tw, 44), (0, 0, 0, 0))
            ImageDraw.Draw(pil).rounded_rectangle((0, 0, tw - 1, 43), radius=22, fill=cores[i % 2] + (255,))
            cor_txt = SOBRE_DESTAQUE if i % 2 else BRANCO
            ImageDraw.Draw(pil).text((tw / 2, 22), rot[i], font=f, fill=cor_txt + (255,), anchor="mm")
            im.alpha_composite(pil, (SOMBRA_M + 18, SOMBRA_M + 16))
            cola_centro(cv, surge(im, k_in(t, self.t0 + 0.12 * i)), cx, cy0 + i * (ch + gap))

    def fecha(self):
        for m in self.midias or []:
            m.fecha()


class Foto(Elemento):
    """Foto (ou vídeo) da pessoa citada. Na dividida cobre o fundo inteiro acima do cartão (v2 0 s);
    com "cartao": true vira card arredondado no palco. Na cheia cobre a tela."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.cobre_fundo = not spec.get("cartao", False)
        if self.cobre_fundo:
            self.claro_proprio = False
        self.midia = None

    def fundo(self, t: float) -> Image.Image:
        alt = H if self.cena.layout == "cheia" else CARD_TOPO + 40
        if self.midia is None:
            self.midia = Midia(self.spec, W, alt, self.t0, alto=False)
        im = self.midia.quadro(t)
        if self.cena.layout != "cheia":   # escurece de leve embaixo pra legenda branca ler
            g = np.zeros((alt, W, 4), np.uint8)
            g[..., 3] = (np.linspace(0, 1, alt) ** 2 * 110).astype(np.uint8)[:, None]
            im = im.copy()
            im.alpha_composite(Image.fromarray(g, "RGBA"))
        return im

    def desenha(self, cv, t, box):
        if self.cobre_fundo:
            return
        x0, y0, x1, y1 = box
        if self.midia is None:
            w, h = tamanho_fonte(self.spec["arquivo"], self.spec.get("recorte"))
            s = min((x1 - x0) * 0.9 / w, (y1 - y0) / h)
            self.midia = Midia(self.spec, int(w * s), int(h * s), self.t0)
        im = com_sombra(self.midia.quadro(t), 26, 0.22)
        cola_centro(cv, surge(im, k_in(t, self.t0)), (x0 + x1) / 2, (y0 + y1) / 2)

    def fecha(self):
        if self.midia:
            self.midia.fecha()


class Midiacard(Elemento):
    """Imagem ou vídeo contido no palco; "cartao": true (padrão) = cantos arredondados e sombra."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.midia = None

    def desenha(self, cv, t, box):
        x0, y0, x1, y1 = box
        if self.midia is None:
            w, h = tamanho_fonte(self.spec["arquivo"], self.spec.get("recorte"))
            s = min((x1 - x0) * float(self.spec.get("largura", 0.92)) / w, (y1 - y0) / h)
            self.midia = Midia(self.spec, int(w * s), int(h * s), self.t0, alto=False)
        im = self.midia.quadro(t)
        if self.spec.get("cartao", True):
            im = com_sombra(im, 26, 0.2)
        cola_centro(cv, surge(im, k_in(t, self.t0)), (x0 + x1) / 2, (y0 + y1) / 2)

    def fecha(self):
        if self.midia:
            self.midia.fecha()


class Orbita(Elemento):
    """Logo no centro, ferramentas em anéis tracejados girando devagar (v2 3,5-5,5 s)."""

    def __init__(self, spec, cena):
        super().__init__(spec, cena)
        self.itens = spec["itens"]
        self.tis = [T_na(it["em"]) if "em" in it else self.t0 + 0.06 * i for i, it in enumerate(self.itens)]

    def eventos(self):
        return [(self.t0, "pop")]

    @functools.lru_cache(maxsize=32)
    def _no(self, i, lado):
        return no_img(self.itens[i], self.cena.claro, lado)

    def desenha(self, cv, t, box):
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        R2 = min((x1 - x0) / 2 - 70, (y1 - y0) / 2 - 50)
        R1 = R2 * 0.55
        d = ImageDraw.Draw(cv)
        cores = [(66, 133, 244), (251, 188, 5)]
        for r, cor in ((R1, cores[0]), (R2, cores[1])):
            k = ease_out(k_in(t, self.t0, 0.3))
            n = 60
            for j in range(n):
                if j % 2:
                    continue
                a0 = 2 * math.pi * j / n
                a1 = 2 * math.pi * (j + 1) / n
                if j / n > k:
                    break
                d.arc((cx - r, cy - r, cx + r, cy + r), math.degrees(a0), math.degrees(a1), fill=cor + (200,), width=4)
        c = self.spec.get("centro")
        if c:
            lg = contem(recorta_vazio(imagem(c)), 150, 150)
            cola_centro(cv, surge(lg, k_in(t, self.t0)), cx, cy)
        n = len(self.itens)
        gira = (t - self.t0) * float(self.spec.get("velocidade", 8))
        for i in range(n):
            anel = R1 if i % 2 == 0 else R2
            ang = math.radians(-90 + 360 * i / n + gira * (1 if i % 2 == 0 else -0.7))
            no = self._no(i, 104)
            cola_centro(cv, surge(no, k_in(t, self.tis[i])), cx + anel * math.cos(ang), cy + anel * math.sin(ang))


class Digitando(Elemento):
    """Símbolo surge e o nome se escreve letra por letra (v3 36,4 s, Anthropic)."""

    def eventos(self):
        return [(self.t0, "pop")]

    def desenha(self, cv, t, box):
        sp = self.spec
        x0, y0, x1, y1 = box
        cx = (x0 + x1) / 2
        tam = int(sp.get("tam", 92))
        cor = TINTA if self.cena.claro else BRANCO
        ic = None
        if sp.get("arquivo"):
            ic = contem(recorta_vazio(imagem(sp["arquivo"])), 330, 300)
        tot = (ic.height + 40 if ic else 0) + tam
        cy = (y0 + y1) / 2 - tot / 2
        if ic is not None:
            cola_centro(cv, surge(ic, k_in(t, self.t0)), cx, cy + ic.height / 2)
            cy += ic.height + 40
        txt = sp["texto"]
        ta = T_na(sp["em_texto"]) if "em_texto" in sp else self.t0 + 0.2
        por = float(sp.get("por_letra", 0.055))
        nvis = int(cl((t - ta) / por, 0, len(txt)))
        if nvis:
            f = F(sp.get("fonte", "sans"), tam)
            full_w = f.getlength(txt)
            parte = txt[:nvis]
            im = texto(parte, sp.get("fonte", "sans"), tam, cor)
            # mantém o texto ancorado à esquerda da posição final (as letras nascem no lugar certo)
            cola_centro(cv, im, cx - full_w / 2 + f.getlength(parte) / 2, cy + tam / 2)


TIPOS = {"logos": Logos, "item": Item, "janela": Janela, "contador": Contador, "fluxo": Fluxo,
         "grafico": Grafico, "comparacao": Comparacao, "foto": Foto, "imagem": Midiacard, "video": Midiacard,
         "orbita": Orbita, "digitando": Digitando}


# ================================================================ CENAS
FUNDOS_CLAROS = ("branco", "fosco")


class Cena:
    """Um trecho com layout fixo (dividida | cheia | rosto) e, nas duas primeiras, um elemento."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.layout = spec.get("layout", "dividida")
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        tipo = spec.get("tipo")
        padrao = {"dividida": "branco", "cheia": "desfocado" if tipo == "janela" else "branco", "rosto": None}
        self.fundo = spec.get("fundo", padrao[self.layout])
        f = self.fundo or ""
        self.claro = f in FUNDOS_CLAROS or (f.startswith("#") and sum(hexa(f)) > 450)
        self.el = TIPOS[tipo](spec, self) if tipo else None
        if self.el is not None and self.el.claro_proprio is not None:
            self.claro = self.el.claro_proprio
        self.titulo = spec.get("titulo")
        if self.titulo is not None and (not isinstance(self.titulo, list) or not self.titulo):
            sys.exit(f'cena {tipo or self.layout}: "titulo" é lista de 1-2 linhas, ex.: ["Claude agora faz", "motion"]')
        self.zoom = float(spec.get("zoom", LAY["rosto_zoom"]))
        if self.t1 <= self.t0:
            sys.exit(f"cena {tipo or self.layout}: termina antes de começar ({self.t0:.2f}-{self.t1:.2f})")

    def nome(self) -> str:
        return f"{self.layout:8s} {self.spec.get('tipo', '')}"

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def estilo_leg(self) -> str | None:
        if self.spec.get("legenda") is False or (self.el is not None and self.el.sem_legenda):
            return None
        if self.layout == "cheia":
            return self.spec.get("legenda", "serifa") + ("_claro" if self.claro else "_escuro")
        if self.layout == "dividida":
            return "sans_claro" if self.claro else "sans_escuro"
        return "sans_escuro"

    def eventos(self) -> list[tuple[float, str]]:
        return self.el.eventos() if self.el else []


CENAS = sorted([Cena(s) for s in MAPA.get("cenas", [])], key=lambda c: c.t0)
for _a, _b in zip(CENAS, CENAS[1:]):
    if _b.t0 < _a.t1 and "ate" not in _a.spec:
        _a.t1 = _b.t0   # sem "ate" explícito, a cena de trás cede o lugar
    if _b.t0 < _a.t1 - 1e-3:
        sys.exit(f"duas cenas ao mesmo tempo ({_a.nome()} até {_a.t1:.2f} e {_b.nome()} a partir de {_b.t0:.2f})")
PADRAO = Cena({"layout": MAPA.get("padrao", {}).get("layout", "rosto"), "em": 0, "ate": TOTAL,
               "zoom": MAPA.get("padrao", {}).get("zoom", LAY["rosto_zoom"])})


def cena_em(t: float) -> Cena:
    for c in CENAS:
        if c.ativo(t):
            return c
    return PADRAO


def janelas_mascara() -> list[tuple[float, float]]:
    """Trechos da tela dividida (a cabeça da pessoa passa por cima da borda do cartão)."""
    return [(c.t0 - 0.05, c.t1 + 0.05) for c in CENAS if c.layout == "dividida"]


_MASC = {"n": None, "im": None}


def mascara(n: int) -> Image.Image | None:
    if _MASC["n"] != n:
        p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
        _MASC["n"], _MASC["im"] = n, (Image.open(p).convert("L") if p.exists() else None)
    return _MASC["im"]


# ---------------------------------------------------------------- fundos
def _mini_borrado(fr: Image.Image, r: float = 6) -> Image.Image:
    return fr.convert("RGB").resize((W // 12, H // 12), Image.BILINEAR).filter(ImageFilter.GaussianBlur(r))


def fundo(nome: str, fr: Image.Image, alt: int = H) -> Image.Image:
    if nome == "branco":
        return Image.new("RGBA", (W, alt), (253, 253, 253, 255))
    if nome == "preto":
        return Image.new("RGBA", (W, alt), (0, 0, 0, 255))
    if nome == "escuro":
        return degrade_v(W, alt, (24, 26, 36), (8, 9, 14))
    if nome == "fosco":   # o próprio vídeo, borrado e lavado de branco azulado (v1)
        m = np.asarray(_mini_borrado(fr), np.float32)
        m = m * 0.16 + np.array([234, 238, 241], np.float32) * 0.84
        return Image.fromarray(m.astype(np.uint8)).resize((W, H), Image.BILINEAR).crop((0, 0, W, alt)).convert("RGBA")
    if nome == "desfocado":   # o próprio vídeo borrado e escurecido (janela no escuro, v1 3-6 s)
        m = np.asarray(_mini_borrado(fr, 4), np.float32) * 0.32
        return Image.fromarray(m.astype(np.uint8)).resize((W, H), Image.BILINEAR).crop((0, 0, W, alt)).convert("RGBA")
    if nome.startswith("#"):
        return Image.new("RGBA", (W, alt), hexa(nome) + (255,))
    return Image.open(_resolve(nome)).convert("RGBA").resize((W, alt))


# ---------------------------------------------------------------- cartão da dividida
@functools.lru_cache(maxsize=2)
def card_formas() -> tuple[Image.Image, Image.Image]:
    """Máscara do cartão (cantos de cima arredondados, desce além do rodapé) e a sombra suave dele."""
    r = int(LAY["card_raio"])
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle((X_CARD, CARD_TOPO, X_CARD + WS - 1, H + r * 2), radius=r, fill=255)
    s = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    s.putalpha(m.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.22)))
    g = Image.new("RGBA", (W, H), (255, 255, 255, 255))   # brilho branco fino na borda (referência)
    borda = Image.new("L", (W, H), 0)
    ImageDraw.Draw(borda).rounded_rectangle((X_CARD, CARD_TOPO, X_CARD + WS - 1, H + r * 2), radius=r,
                                            outline=255, width=6)
    g.putalpha(borda.filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.7)))
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sombra.alpha_composite(s, (0, 8))
    sombra.alpha_composite(g)
    return m, sombra


def monta_dividida(fr: Image.Image, t: float, n: int, cena: Cena) -> Image.Image:
    dy = dy_card(t)
    if cena.el is not None and isinstance(cena.el, Foto) and cena.el.cobre_fundo:
        cv = fundo("preto", fr)
        cv.alpha_composite(cena.el.fundo(t), (0, 0))
    else:
        cv = fundo(cena.fundo, fr)
    pequeno = fr.resize((WS, HS), Image.BILINEAR)
    m_card, sombra = card_formas()
    cv.alpha_composite(sombra)
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    camada.paste(pequeno, (X_CARD, dy))
    camada.putalpha(ImageChops.multiply(camada.getchannel("A"), m_card))
    cv.alpha_composite(camada)
    m = mascara(n)
    if m is not None:   # a cabeça passa por cima da borda do cartão
        lim = CARD_TOPO + 30
        h_src = int((lim - dy) / S_CARD)
        if h_src > 0:
            mm = m.crop((0, 0, W, min(H, h_src))).resize((WS, max(1, lim - dy)), Image.BILINEAR)
            pe = pequeno.crop((0, 0, WS, max(1, lim - dy)))
            alfa = Image.new("L", (W, H), 0)
            alfa.paste(mm, (X_CARD, dy))
            alfa = alfa.crop((0, 0, W, lim))
            # some suavemente nos últimos 30 px (emenda invisível com o cartão)
            rampa = np.ones((lim, W), np.float32)
            rampa[CARD_TOPO:lim] = np.linspace(1, 0, lim - CARD_TOPO)[:, None]
            alfa = Image.fromarray((np.asarray(alfa, np.float32) * rampa).astype(np.uint8))
            pessoa = Image.new("RGBA", (W, lim), (0, 0, 0, 0))
            pessoa.paste(pe, (X_CARD, dy))
            sh = Image.new("RGBA", (W, lim), (0, 0, 0, 255))
            sh.putalpha(alfa.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.18)))
            cv.alpha_composite(sh, (0, 6))
            pessoa.putalpha(alfa)
            cv.alpha_composite(pessoa, (0, 0))
    return cv


def zoom_rosto(fr: Image.Image, t: float, z: float) -> tuple[Image.Image, float]:
    """Close: amplia z vezes em volta do rosto. Devolve o quadro e o y do queixo na tela."""
    r = MED[grupo(t)]["rosto"]
    fcx, fcy = r[0] + r[2] / 2, r[1] + r[3] / 2
    if z <= 1.001:
        return fr, r[1] + r[3]
    cw, ch = W / z, H / z
    x = cl(fcx - cw / 2, 0, W - cw)
    y = cl(fcy - ch * LAY["rosto_cy"], 0, H - ch)
    out = fr.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((W, H), Image.BICUBIC)
    return out, (r[1] + r[3] - y) * z


# ---------------------------------------------------------------- título do gancho
@functools.lru_cache(maxsize=8)
def titulo_imgs(l1: str, l2: str) -> tuple[Image.Image, Image.Image]:
    a = recorta_vazio(texto(l1, "sans", 62, TINTA))
    f = F("serifa", 70)
    tw = int(f.getlength(l2)) + 44
    th = int(f.size * 1.3)
    pil = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(pil).rounded_rectangle((0, 0, tw - 1, th - 1), radius=8, fill=DESTAQUE + (255,))
    ImageDraw.Draw(pil).text((tw / 2, th / 2 + 2), l2, font=f, fill=SOBRE_DESTAQUE + (255,), anchor="mm")
    return a, pil


def desenha_titulo(cv: Image.Image, t: float, cena: Cena, y0: float) -> float:
    """Título em duas linhas no topo (v1 0-3 s); a pílula abre do centro e o texto entra depois.
    Devolve o y onde o palco pode começar."""
    l1, l2 = cena.titulo[0], cena.titulo[1] if len(cena.titulo) > 1 else ""
    a, pil = titulo_imgs(l1, l2)
    cx = W / 2
    cola_centro(cv, surge(a, k_in(t, cena.t0)), cx, y0 + a.height / 2)
    y2 = y0 + a.height + 14 + pil.height / 2
    if l2:
        k = ease_out(k_in(t, cena.t0 + 0.08, 0.25))
        if k > 0:
            vazio = Image.new("RGBA", pil.size, (0, 0, 0, 0))
            ImageDraw.Draw(vazio).rounded_rectangle((0, 0, pil.width - 1, pil.height - 1), radius=8,
                                                    fill=DESTAQUE + (255,))
            w = max(4, int(pil.width * k))
            caixa = vazio.crop(((pil.width - w) // 2, 0, (pil.width + w) // 2, pil.height))
            cola_centro(cv, caixa, cx, y2)
            kt = k_in(t, cena.t0 + 0.28, 0.18)
            if kt > 0:
                cola_centro(cv, opaco(pil, kt), cx, y2)
    return y2 + pil.height / 2 + 28


# ================================================================ LEGENDA (acumula palavra a palavra)
SINAIS = ".,!?;:…\"'“”()[]"
DEST = {limpa(p) for p in MAPA.get("destaques", [])}


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    maxp = int(MAPA.get("leg_palavras", 3))
    maxc = int(MAPA.get("leg_chars", 18))
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
        partes = []
        for j in b:
            t = WORDS[j]["t"].strip().strip(SINAIS)
            ini_frase = j == 0 or WORDS[j - 1]["t"].rstrip()[-1:] in ".!?:" or WORDS[j - 1]["seg"] != WORDS[j]["seg"]
            if ini_frase and not (len(t) > 1 and t.isupper()):
                t = t[0].lower() + t[1:]
            partes.append((t, WORDS[j]["s"]))
        ini = WORDS[b[0]]["s"] - 0.04
        prox = WORDS[blocos[k + 1][0]]["s"] - 0.04 if k + 1 < len(blocos) else TOTAL
        fim = prox if prox - WORDS[b[-1]]["e"] < 0.6 else WORDS[b[-1]]["e"] + 0.2
        out.append({"palavras": partes, "ini": max(0.0, ini), "fim": min(TOTAL, fim)})
    return out


def _estilo_palavra(p: str, base: str) -> tuple[str, float, tuple | None]:
    """(fonte, fator de tamanho, cor) de cada palavra. None = cor padrão do estilo."""
    if base.startswith("serifa"):
        return "serifa", 1.0, None
    if limpa(p) in DEST:
        return "serifa", 1.1, DESTAQUE
    if any(c.isdigit() for c in p):
        return "sans", 1.0, DESTAQUE
    return "sans", 1.0, None


@functools.lru_cache(maxsize=4096)
def palavra_img(p: str, estilo: str) -> Image.Image:
    claro = estilo.endswith("_claro")
    tam = LAY["leg_tam"] * (1.05 if estilo.startswith("serifa") else 1)
    fonte, fat, cor = _estilo_palavra(p, estilo)
    if estilo.startswith("serifa"):
        p = p.upper()
    padrao = TINTA if claro else BRANCO
    if cor is not None and claro and ACENTO_CLARO:   # amarelo no branco: texto preto sobre faixa amarela
        return texto_faixa(p, fonte, tam * fat, TINTA, DESTAQUE)
    if cor is not None and not claro and not ACENTO_CLARO:   # no vídeo/escuro o azul clareia (v1: "library")
        cor = tuple(int(lerp(c, 255, 0.3)) for c in cor)
    return texto(p, fonte, tam * fat, cor or padrao, sombra=0 if claro else 0.85)


def texto_faixa(txt: str, tipo: str, tam: float, cor: tuple, faixa: tuple) -> Image.Image:
    """Palavra sobre faixa de marca-texto (cobre do meio da letra pra baixo, passa um pouco das bordas)."""
    m = mascara_texto(txt, F(tipo, int(tam)))
    bb = m.getbbox() or (0, 0, m.width, m.height)
    im = Image.new("RGBA", m.size, (0, 0, 0, 0))
    alt = bb[3] - bb[1]
    ImageDraw.Draw(im).rounded_rectangle((bb[0] - 12, bb[1] + alt * 0.30, bb[2] + 12, bb[3] + alt * 0.06),
                                         radius=8, fill=faixa + (255,))
    corpo = Image.new("RGBA", m.size, cor + (255,))
    corpo.putalpha(m)
    im.alpha_composite(corpo)
    return im


def legenda_img(palavras: list[tuple[str, float]], t: float, estilo: str) -> Image.Image | None:
    vis = [(p, s) for p, s in palavras if t >= s - 0.04]
    if not vis:
        return None
    imgs = [palavra_img(p, estilo) for p, _ in vis]
    pad = 30
    esp = int(LAY["leg_tam"] * 0.26)
    ws = [im.width - 2 * pad for im in imgs]
    tot = sum(ws) + esp * (len(ws) - 1)
    hh = max(im.height for im in imgs)
    out = Image.new("RGBA", (tot + 2 * pad, hh), (0, 0, 0, 0))
    x = pad
    for i, ((p, s), im) in enumerate(zip(vis, imgs)):
        k = k_in(t, s - 0.04, 0.12)
        if k < 1:   # a palavra nova entra por desfoque
            im = opaco(desfoca(im, 8 * (1 - ease_out(k))), ease_out(k))
        out.alpha_composite(im, (x - pad, (hh - im.height) // 2))
        x += ws[i] + esp
    return out


# ================================================================ CTA (comenta + PALAVRA com brilho)
CTA = MAPA.get("cta")
if CTA:
    CTA_T0 = T(CTA["em"])
    CTA_T1 = T_fim(CTA.get("ate"), CTA["em"]) if CTA.get("ate") is not None else TOTAL
    CTA_TP = T_na(CTA["palavra_em"]) if CTA.get("palavra_em") is not None else CTA_T0


@functools.lru_cache(maxsize=4)
def cta_imgs() -> tuple[Image.Image, Image.Image]:
    l1 = texto(CTA.get("texto", "comenta"), "serifa", LAY["leg_tam"] * 1.05, BRANCO, sombra=0.55)
    pal = CTA["palavra"]
    if CTA.get("aspas", True):
        pal = f"“{pal}”"
    tam = 132
    while F("sans_heavy", tam).getlength(pal) > W * 0.86 and tam > 60:
        tam -= 4
    cor = hexa(CTA["cor"]) if CTA.get("cor") else DESTAQUE
    clara = cor if ACENTO_CLARO else tuple(int(lerp(c, 255, 0.45)) for c in cor)
    l2 = texto(pal, "sans_heavy", tam, BRANCO, sombra=0.3, degrade=((255, 255, 255), clara), brilho=cor)
    return l1, l2


# ================================================================ composição
def compoe(fr: Image.Image, t: float, legendas: list[dict], n: int) -> Image.Image:
    cena = cena_em(t)
    lay = cena.layout
    if lay == "dividida":
        cv = monta_dividida(fr, t, n, cena)
        y0 = LAY["palco_topo"]
        if cena.titulo:
            y0 = desenha_titulo(cv, t, cena, y0)
        box = (60, y0, W - 60, LEG_DIV - LAY["leg_tam"] / 2 - LAY["palco_folga"])
        leg_y = LEG_DIV
    elif lay == "cheia":
        if cena.el is not None and isinstance(cena.el, Foto) and cena.el.cobre_fundo:
            cv = cena.el.fundo(t).copy()
        else:
            cv = fundo(cena.fundo, fr)
        a, b = LAY["cheia_palco"]
        y0 = H * a
        if cena.titulo:
            y0 = desenha_titulo(cv, t, cena, y0)
        box = (60, y0, W - 60, H * b)
        leg_y = H * float(cena.spec.get("leg_y", LAY["cheia_leg"]))
    else:
        cv, queixo = zoom_rosto(fr, t, cena.zoom)
        cv = cv.copy()
        box = None
        leg_y = min(H * LAY["leg_max"], queixo + LAY["rosto_leg"])
    if cena.el is not None and box is not None:
        cena.el.desenha(cv, t, box)
    if CTA and CTA_T0 <= t < CTA_T1:
        l1, l2 = cta_imgs()
        if t < CTA_TP:
            cola_centro(cv, l1, W / 2, leg_y)
        else:
            k = mola((t - CTA_TP) / 0.32)
            cola_centro(cv, l1, W / 2, leg_y - 46)
            cola_centro(cv, escala(l2, max(0.05, k)), W / 2, leg_y + l2.height * 0.26)
        return cv
    estilo = cena.estilo_leg()
    if estilo:
        for b in legendas:
            if b["ini"] <= t < b["fim"]:
                cola_centro(cv, legenda_img(b["palavras"], t, estilo), W / 2, leg_y)
                break
    return cv


# ================================================================ áudio (voz + efeito curto nas trocas)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome.startswith("whoosh"):
        d = 0.3
        n = int(d * SR)
        esp = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= np.exp(-((np.log(f + 1) - np.log(2400)) ** 2) / 0.9)
        x = np.fft.irfft(esp, n) * _env(n, 0.55)
        return x / (np.abs(x).max() + 1e-9)
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
    ant = PADRAO
    for c in CENAS:
        if c.t0 > 0.05 and (c.layout != ant.layout or c.t0 - ant.t1 > 0.05 or c.layout != "rosto"):
            ev.append((c.t0, "whoosh"))
        ev += c.eventos()
        ant = c
    # volta pro rosto depois de uma cena também troca a tela
    for c in CENAS:
        if c.t1 < TOTAL - 0.1 and cena_em(c.t1 + 0.01) is PADRAO and c.layout != "rosto":
            ev.append((c.t1, "whoosh"))
    if CTA and CTA.get("palavra_em") is not None:
        ev.append((CTA_TP, "pop"))
    return sorted(ev)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -26) if isinstance(cfg, dict) else -26
        ultimo = -9.0
        for t, nome in eventos_som():
            if t - ultimo < 0.1:
                continue
            ultimo = t
            s = sfx(nome) * 10 ** (gdb / 20) * (0.8 if nome == "pop" else 1)
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


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_SB = {"logos": "Logos que se acumulam", "item": "Card do item da lista", "janela": "Janela com a página real",
            "contador": "Contador rodando", "fluxo": "Fluxo que se desenha", "grafico": "Gráfico que cresce",
            "comparacao": "Antes x depois", "foto": "Foto da pessoa citada", "imagem": "Imagem no palco",
            "video": "Vídeo no palco", "orbita": "Órbita de logos", "digitando": "Logo digitando"}
LAYOUT_SB = {"dividida": "Tela dividida", "cheia": "Tela cheia", "rosto": "Close no rosto"}


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1: min(t, t1 - 0.05)
    br = lambda s: s.replace(".", ",")
    ms, avisos = [], []

    def pronto_itens(c: Cena) -> list[tuple[str, float, float]]:
        """(nome, quando acontece, quando já está inteiro na tela) de cada item do elemento."""
        el, sp = c.el, c.spec
        if isinstance(el, Janela):
            out = []
            for i, mk in enumerate(sp.get("marcas", [])):
                ta = T_na(mk["em"])
                dur = float(mk.get("dur", 0.6)) if "ate" not in mk else max(0.1, T_na(mk["ate"]) - ta)
                out.append((f"marca-texto {i + 1}", ta, ta + dur + 0.05))
            out += [(f"contorno {i + 1}", T_na(x["em"]), T_na(x["em"]) + 0.3) for i, x in enumerate(sp.get("contornos", []))]
            out += [(f"clique {i + 1}", T_na(x["em"]), T_na(x["em"]) + 0.3) for i, x in enumerate(sp.get("cliques", []))]
            if sp.get("contador"):
                ta = T_na(sp["contador"]["em"])
                out.append((f"contador {sp['contador'].get('valor', '')}", ta, ta + float(sp["contador"].get("dur", 0.7)) + 0.05))
            for r in sp.get("rolagem", []):
                quando, resto = (r[:2], r[2:]) if isinstance(r[0], str) else (r[0], r[1:])
                ta = T_na(quando)
                out.append(("rolagem da página", ta, ta + (float(resto[1]) if len(resto) > 1 else 0.8) + 0.05))
            return out
        if isinstance(el, (Logos, Fluxo)):
            extra = 0.5 if isinstance(el, Fluxo) else 0.35   # no fluxo a linha leva 0,4 s pra chegar
            return [(n.replace("\n", " "), te, te + extra) for n, te in el.itens_tempos()]
        if isinstance(el, Orbita):
            return [(it.get("texto") or Path(it.get("arquivo", "?")).stem, ti, ti + 0.3)
                    for it, ti in zip(el.itens, el.tis)]
        return []

    def pronto_base(c: Cena) -> float:
        """Quando a tela da cena já está inteira (sem contar itens que entram depois)."""
        el, sp = c.el, c.spec
        p = c.t0 + (0.55 if c.titulo else 0.35)
        if isinstance(el, Item):
            p = max(p, c.t0 + 0.45)
        elif isinstance(el, Contador):
            ta = T_na(sp["em_numero"]) if "em_numero" in sp else c.t0
            p = max(p, ta + float(sp.get("dur", 0.9)) + 0.05)
        elif isinstance(el, Grafico):
            tb = T_na(sp["ate_linha"]) if "ate_linha" in sp else c.t1 - 0.25
            p = max(p, tb + 0.1)
        elif isinstance(el, Comparacao):
            p = max(p, c.t0 + 0.5)
        elif isinstance(el, Digitando):
            ta = T_na(sp["em_texto"]) if "em_texto" in sp else c.t0 + 0.2
            p = max(p, ta + float(sp.get("por_letra", 0.055)) * len(sp["texto"]) + 0.1)
        elif isinstance(el, Orbita):
            p = max(p, c.t0 + 0.4)
        elif c.layout == "rosto":
            p = c.t0 + 0.2
        return p

    def desc_cena(c: Cena) -> str:
        sp = c.spec
        partes = []
        if c.el is None:
            partes.append(f"zoom {c.zoom:.2f}x".replace(".", ","))
        if c.titulo:
            partes.append("título: " + " / ".join(SB.limpa_marcacao(str(x)) for x in c.titulo))
        if c.layout != "rosto" and c.fundo and not (isinstance(c.el, Foto) and c.el.cobre_fundo):
            partes.append(f"fundo {c.fundo}")
        if sp.get("url"):
            partes.append(sp["url"])
        if isinstance(c.el, Item):
            partes.append(" ".join(x for x in (sp.get("ordem"), sp.get("nome")) if x))
        elif isinstance(c.el, Contador):
            partes.append(f"{sp.get('prefixo', '')}{sp['valor']}{sp.get('sufixo', '')} {sp.get('rotulo', '')}".strip())
        elif isinstance(c.el, Grafico):
            partes.append(" — ".join(str(x) for x in (sp.get("nome"), sp.get("valor_final")) if x))
        elif isinstance(c.el, Comparacao):
            partes.append(" x ".join(sp.get("rotulos", [])))
        elif isinstance(c.el, Digitando):
            partes.append(f'escreve "{sp["texto"]}"')
        elif isinstance(c.el, Fluxo):
            cen = sp.get("centro", {})
            partes.append(("tudo entra em " if sp.get("sentido", "entra") == "entra" else "sai de ") +
                          (cen.get("rotulo") or Path(cen.get("arquivo", "?")).stem))
        elif isinstance(c.el, Orbita) and sp.get("centro"):
            partes.append(f"centro {Path(sp['centro']).stem}")
        nomes = [n for n, _, _ in pronto_itens(c)]
        if nomes:
            partes.append(" · ".join(nomes))
        if sp.get("arquivo"):
            partes.append("arquivo: " + Path(sp["arquivo"]).name)
        if c.el is not None and c.el.sem_legenda:
            partes.append("sem legenda")
        elif c.spec.get("legenda") is False:
            partes.append("sem legenda")
        return " — ".join(p for p in partes if p) or "—"

    for c in CENAS:
        nome = LAYOUT_SB[c.layout] + (": " + NOMES_SB.get(c.spec.get("tipo"), c.spec.get("tipo")) if c.el else "")
        if c.titulo:
            nome += " + título do gancho com pílula"
        itens = pronto_itens(c)
        g0 = grupo(c.t0 + 0.15)
        primeiros = [x for x in itens if grupo(x[1]) <= g0]
        depois = [x for x in itens if grupo(x[1]) > g0]
        m = {"t0": c.t0, "t1": c.t1, "quadro": cap(max([pronto_base(c)] + [p for _, _, p in primeiros]), c.t1),
             "tipo": nome, "desc": desc_cena(c)}
        av = []
        if c.t1 - c.t0 < 0.8:
            av.append(f"cena de {c.t1 - c.t0:.2f} s (a referência não passa de ~1 s mesmo no card do item)")
        # mesma regra do resumo(): item do elemento a menos de 0,6 s da saída (a rolagem não entra na conta)
        tarde = [n for n, te, _ in primeiros if c.t1 - te < 0.6 and n != "rolagem da página"]
        if tarde:
            av.append(f"{', '.join(tarde)} acontece menos de 0,6 s antes da cena sair")
        if av:
            m["aviso"] = br("; ".join(av))
        ms.append(m)
        for g in sorted({grupo(te) for _, te, _ in depois}):
            xs = [x for x in depois if grupo(x[1]) == g]
            m = {"t0": min(te for _, te, _ in xs), "t1": c.t1, "quadro": cap(max(p for _, _, p in xs), c.t1),
                 "tipo": nome + " (entra mais)", "desc": " · ".join(n for n, _, _ in xs)}
            tarde = [n for n, te, _ in xs if c.t1 - te < 0.6 and n != "rolagem da página"]
            if tarde:
                m["aviso"] = f"{', '.join(tarde)} acontece menos de 0,6 s antes da cena sair"
            ms.append(m)
    # volta pro close (padrão) entre as cenas
    proximos = sorted([c.t0 for c in CENAS] + [TOTAL])
    inicios = [(0.0, CENAS[0].t0 if CENAS else TOTAL)] if not CENAS or CENAS[0].t0 > 0.05 else []
    for c in CENAS:
        if c.t1 < TOTAL - 0.1 and cena_em(c.t1 + 0.01) is PADRAO:
            inicios.append((c.t1, min(x for x in proximos if x >= c.t1 + 0.01)))
    for a, b in inicios:
        if b - a < 0.1 or (CTA and CTA_T0 <= a + 0.3 and CTA_T1 >= b - 0.05):   # o CTA já mostra o close
            continue
        m = {"t0": a, "t1": b, "quadro": cap(a + 0.25, b), "tipo": LAYOUT_SB[PADRAO.layout] +
             (" (volta)" if a > 0 else ""), "desc": br(f"padrão: zoom {PADRAO.zoom:.2f}x, legenda no peito")}
        if b - a < 0.8 and b < TOTAL - 0.05:
            m["aviso"] = br(f"close de só {b - a:.2f} s entre duas cenas (pisca; cena com menos de 0,8 s)")
        ms.append(m)
    if CTA:
        ms.append({"t0": CTA_T0, "t1": CTA_T1, "quadro": cap(CTA_TP + 0.4, CTA_T1), "tipo": "CTA com brilho",
                   "desc": f"{CTA.get('texto', 'comenta')} + {CTA['palavra']}" +
                           (" (no close)" if cena_em(CTA_TP + 0.4) is PADRAO else "")})

    conta = {"dividida": 0, "cheia": 0, "rosto": 0}
    trocas, ant = 0, None
    for k in range(N_FRAMES):
        c = cena_em(k / FPS)
        conta[c.layout] += 1
        if c is not ant:
            trocas, ant = trocas + 1, c
    faixa = {"dividida": (0.30, 0.46), "cheia": (0.36, 0.48), "rosto": (0.17, 0.22)}
    fora = [f"{LAYOUT_SB[l].lower()} {v / max(1, N_FRAMES):.0%} (referência {a:.0%}-{b:.0%})"
            for l, v in conta.items() for a, b in [faixa[l]] if not a <= v / max(1, N_FRAMES) <= b]
    if fora:
        avisos.append("tempo por tela fora da referência: " + ", ".join(fora))
    passo = TOTAL / max(1, trocas)
    if not 2.1 <= passo <= 3.0:
        avisos.append(br(f"uma troca de tela a cada {passo:.1f} s (referência: 2,1-3 s)"))

    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]
    arqs = []

    def junta(a):
        if isinstance(a, dict):
            a = a.get("arquivo")
        if a and isinstance(a, str) and a not in [x for x, _ in arqs]:
            try:
                ok = _resolve(a).exists()
            except SystemExit:
                ok = False
            arqs.append((a, ok))

    for sp in MAPA.get("cenas", []):
        junta(sp.get("arquivo"))
        if sp.get("fundo") and sp["fundo"] not in ("branco", "preto", "escuro", "fosco", "desfocado") \
                and not str(sp["fundo"]).startswith("#"):
            junta(sp["fundo"])
        junta(sp.get("centro") if isinstance(sp.get("centro"), (str, dict)) else None)
        for it in sp.get("itens", []):
            junta(it)
    if MAPA.get("musica"):
        junta(MAPA["musica"])

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, legendas, n)

    out = SB.gerar(EDIT, "Nick", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ================================================================ main
def resumo() -> None:
    print(f"linha do tempo:  (dividida: cabelo em {Y_CABECA}px, borda do cartão em {CARD_TOPO}px = "
          f"{CARD_TOPO / H:.0%}, vídeo da pessoa a {S_CARD:.2f}x)")
    for c in CENAS:
        extra = f" zoom {c.zoom:.2f}" if c.layout == "rosto" else f" fundo {c.fundo}" if c.fundo else ""
        if c.titulo:
            extra += f" [título: {' / '.join(c.titulo)}]"
        print(f"  {c.t0:6.2f}-{c.t1:6.2f} ({c.t1 - c.t0:4.1f}s) {c.nome()}{extra}")
        if c.el:
            for nome, te in c.el.itens_tempos():
                nome = nome.replace("\n", " ")
                print(f"           · {te:6.2f} {nome}")
                if c.t1 - te < 0.6:
                    print(f"  ATENÇÃO: '{nome}' acontece {c.t1 - te:.2f}s antes da cena sair (mín. ~0,6 s)")
        if c.t1 - c.t0 < 0.8:
            print(f"  ATENÇÃO: cena de {c.t1 - c.t0:.2f}s (a referência não passa de ~1 s mesmo no card do item)")
    if CTA:
        print(f"  {CTA_T0:6.2f}-{CTA_T1:6.2f} cta      {CTA.get('texto', 'comenta')} {CTA['palavra']} (palavra em {CTA_TP:.2f})")
    conta = {"dividida": 0, "cheia": 0, "rosto": 0}
    trocas = 0
    ant = None
    for k in range(N_FRAMES):
        c = cena_em(k / FPS)
        conta[c.layout] += 1
        if c is not ant:
            trocas += 1
            ant = c
    print("  tempo por layout: " + ", ".join(f"{l} {v / max(1, N_FRAMES):.0%}" for l, v in conta.items()) +
          "  (referência: dividida 30-46%, cheia 36-48%, rosto 17-22%)")
    print(f"  uma troca de tela a cada {TOTAL / max(1, trocas):.1f}s (referência: 2,1-3 s)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if janelas_mascara() and not (EDIT / "masks" / "out").exists():
        sys.exit("tem tela dividida (cabeça por cima do cartão): rode mascaras.py antes")
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
    prenorm = EDIT / f"{modo}_nick.prenorm.mp4"
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
        for c in CENAS:   # fecha o ffmpeg de quem já saiu
            if t >= c.t1 and c.el is not None:
                c.el.fecha()
        k += 1
        if k % 300 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_nick.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
