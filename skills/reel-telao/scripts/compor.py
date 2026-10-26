"""compor.py — monta o Reel no estilo "telão" quadro a quadro, a partir do mapa.json.

Estilo mapeado de uma referência (referencia/referencias-estilo.md): a parede acima da cabeça vira telão
(imagem da metáfora, foto de reação/meme, colagem de vídeos, prova pessoal), tudo por CORTE SECO,
retângulo chapado sem borda nem sombra, base encostando no topo da cabeça; tela dividida com a tela do
sistema / gráfico simples em fundo escuro; legenda palavra por palavra, branca, que pula pra parede
quando não tem nada em cima da cabeça; CTA no estilo de texto nativo do Instagram.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_telao.mp4 | final_telao.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov | base_final.mov, imagens em <edit>/assets/.

Camadas, de baixo pra cima: base (ou tela dividida: painel de cima + base reenquadrada embaixo)
→ telão em cima da cabeça → CTA → legenda (sempre por último).
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

PERFIL = perfil.carregar()   # cor de destaque do criador (~/.claude/padroes-edicao/perfil.json)

AQUI = Path(__file__).resolve().parent
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

# ---------------------------------------------------------------- linha do tempo (igual reel-prova)
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


ANTECIPA = float(MAPA.get("antecipa", 0.15))   # a imagem chega antes da palavra (referência: 0,1-0,25 s)


def T(spec) -> float:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] (entra ANTECIPA s antes da palavra) |
    [palavra, tomada, atraso] (atraso explícito em relação ao início da palavra)."""
    if isinstance(spec, (int, float)):
        return float(spec)
    w = WORDS[acha(spec[0], int(spec[1]))]
    d = float(spec[2]) if len(spec) > 2 else -ANTECIPA
    return max(0.0, w["s"] + d)


def T_fim(spec_ate, spec_em) -> float:
    if spec_ate is not None:
        return T(spec_ate)
    return OFF[int(spec_em[1]) + 1] if isinstance(spec_em, list) else TOTAL


def grupo(t: float) -> int:
    return max(0, min(_NG - 1, bisect.bisect_right(OFF, t) - 1))


def topo(t: float) -> int:
    return MED[grupo(t)]["topo"]


def queixo(t: float) -> int:
    r = MED[grupo(t)]["rosto"]
    return r[1] + r[3]


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x: float) -> float:
    x = cl(x)
    return 1 - (1 - x) ** 3


def mola(x: float) -> float:
    x = cl(x)
    c1 = 1.7
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- fontes (conferidas: fonte errada cai em outra calada)
_AV = "/System/Library/Fonts/Avenir Next.ttc"
FONTES = {
    "legenda": (_AV, 2, ("Avenir Next", "Demi Bold")),
    "cta": (_AV, 0, ("Avenir Next", "Bold")),
    "rotulo": (_AV, 5, ("Avenir Next", "Medium")),
    "rotulo_on": (_AV, 2, ("Avenir Next", "Demi Bold")),
    "rotulo_destaque": (_AV, 0, ("Avenir Next", "Bold")),
}
for _k, (_arq, _i, _nome) in FONTES.items():
    if ImageFont.truetype(_arq, 20, index=_i).getname() != _nome:
        sys.exit(f"fonte {_k}: esperava {_nome} em {_arq}[{_i}]")


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, i, _ = FONTES[tipo]
    return ImageFont.truetype(arq, max(6, int(size)), index=i)


# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "sobra": 14,            # o telão desce isso abaixo do topo do cabelo (encosta na cabeça, como na referência)
    "topo_min": 150,        # o telão nunca sobe acima disto (fica abaixo da barra do Instagram)
    "larg_imagem": 0.62,    # imagem/meme sozinho: 62% da largura (referência 58-62%)
    "larg_tile": 0.22,      # colagem: cada vídeo 22% da largura
    "degrau": 50,           # colagem: o do meio fica mais alto
    "vao": 14,              # colagem: espaço entre vídeos
    "divisao": 0.45,        # tela dividida: altura do painel de cima (0,45 deixa o rosto alto o bastante)
    "respiro_div": 40,      # tela dividida: parede acima da cabeça que aparece no painel de baixo
    "leg_tam": 86,          # legenda (a palavra "generation" ocupa ~43% da largura, como na referência)
    "leg_peito": 230,       # legenda com telão: tantos px abaixo do queixo
    "leg_parede": 175,      # legenda sem telão: tantos px acima do topo da cabeça
    "leg_div": 75,          # legenda na tela dividida: abaixo do queixo
    "leg_max": 0.78,        # legenda nunca desce além disto (a interface do Instagram cobre o rodapé)
}
LAY.update(MAPA.get("layout", {}))
FUNDO_DIV = hexa(MAPA.get("fundo_dividida", "#060710"))
DESTAQUE = hexa(MAPA.get("destaque", PERFIL["cor_destaque"]))


# ---------------------------------------------------------------- base
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw).convert("RGBA")


def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    if p.is_absolute():
        return p
    for cand in (EDIT / "assets" / arq, EDIT / "assets" / f"{arq}.png", EDIT / "assets" / f"{arq}.jpg",
                 PASTA / arq):
        if cand.exists():
            return cand.resolve()
    sys.exit(f"não achei o arquivo {arq} (procurei em assets/ e na pasta do vídeo)")


def _tamanho_video(arq: Path) -> tuple[int, int]:
    w, h = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "csv=p=0", str(arq)]).decode().strip().split(",")[:2]
    return int(w), int(h)


class LeitorVideo:
    """Um ffmpeg por vídeo, aberto no 1º quadro em que ele aparece; entrega quadros cw x ch (cobre e recorta)."""

    def __init__(self, arq: Path, inicio: float, vel: float, crop, cw: int, ch: int, t0: float):
        self.arq, self.inicio, self.vel, self.crop = arq, inicio, vel, crop
        self.cw, self.ch, self.t0 = cw // 2 * 2, ch // 2 * 2, t0
        self.proc, self.ultimo, self.k = None, None, 0

    def vf(self, com_vel: bool = True) -> str:
        c = self.crop
        return ((f"crop={c[2]}:{c[3]}:{c[0]}:{c[1]}," if c else "") +
                (f"setpts=PTS/{self.vel}," if com_vel else "") +
                f"scale={self.cw}:{self.ch}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={self.cw}:{self.ch},fps={FPS_NUM}/{FPS_DEN}")

    def quadro(self, t: float) -> Image.Image:
        tam = self.cw * self.ch * 3
        if ARGS.so_quadros or ARGS.storyboard:
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


# ================================================================ TELÃO (em cima da cabeça)
class Telao:
    """Base de tudo que fica em cima da cabeça: entra e sai por corte seco, sem borda/sombra/canto."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        if self.t1 <= self.t0:
            sys.exit(f"telão {spec}: termina antes de começar ({self.t0:.2f}-{self.t1:.2f})")

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def base_y(self, t: float) -> int:
        return topo(t) + LAY["sobra"]

    def caixa(self, asp: float, larg: float, t: float) -> tuple[int, int]:
        w = W * larg
        h = w / asp
        hmax = self.base_y(t) - LAY["topo_min"]
        if h > hmax:
            h, w = hmax, hmax * asp
        return int(w) // 2 * 2, int(h) // 2 * 2

    def fecha(self) -> None:
        pass


class TelaoImagem(Telao):
    def __init__(self, spec: dict):
        super().__init__(spec)
        self.im = Image.open(_resolve(spec["arquivo"])).convert("RGBA")
        self.larg = float(spec.get("largura", LAY["larg_imagem"]))

    @functools.lru_cache(maxsize=8)
    def _no_tamanho(self, w: int, h: int) -> Image.Image:
        return self.im.resize((w, h), Image.LANCZOS)

    def desenha(self, fr: Image.Image, t: float) -> None:
        w, h = self.caixa(self.im.width / self.im.height, self.larg, t)
        fr.alpha_composite(self._no_tamanho(w, h), ((W - w) // 2, self.base_y(t) - h))


class TelaoVideo(Telao):
    def __init__(self, spec: dict):
        super().__init__(spec)
        arq = _resolve(spec["arquivo"])
        crop = spec.get("recorte")
        sw, sh = (crop[2], crop[3]) if crop else _tamanho_video(arq)
        w, h = self.caixa(sw / sh, float(spec.get("largura", LAY["larg_imagem"])), self.t0)
        self.w, self.h = w, h
        self.leitor = LeitorVideo(arq, float(spec.get("inicio", 0)), float(spec.get("velocidade", 1)), crop,
                                  w, h, self.t0)

    def desenha(self, fr: Image.Image, t: float) -> None:
        fr.alpha_composite(self.leitor.quadro(t), ((W - self.w) // 2, self.base_y(t) - self.h))

    def fecha(self) -> None:
        self.leitor.fecha()


class TelaoColagem(Telao):
    """Vídeos verticais lado a lado, rodando mudos (prova social do gancho). O do meio fica mais alto."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = spec["itens"]
        n = len(self.itens)
        tw = int(W * float(spec.get("largura_item", LAY["larg_tile"]))) // 2 * 2
        th = int(tw * 16 / 9) // 2 * 2
        hmax = self.base_y(self.t0) - LAY["degrau"] - LAY["topo_min"]
        if th > hmax:
            th = hmax // 2 * 2
            tw = int(th * 9 / 16) // 2 * 2
        self.tw, self.th = tw, th
        total = n * tw + (n - 1) * LAY["vao"]
        self.xs = [int((W - total) / 2 + i * (tw + LAY["vao"])) for i in range(n)]
        meio = n // 2 if n % 2 else -1
        self.degraus = [LAY["degrau"] if i == meio else 0 for i in range(n)]
        self.leitores = [LeitorVideo(_resolve(it["arquivo"]), float(it.get("inicio", 0)), 1.0, it.get("recorte"),
                                     tw, th, self.t0) for it in self.itens]

    def desenha(self, fr: Image.Image, t: float) -> None:
        by = self.base_y(t)
        for x, d, lt in zip(self.xs, self.degraus, self.leitores):
            fr.alpha_composite(lt.quadro(t), (x, by - self.th - d))

    def fecha(self) -> None:
        for lt in self.leitores:
            lt.fecha()


# ================================================================ TELA DIVIDIDA
@functools.lru_cache(maxsize=None)
def brilho(raio: int, cor: tuple, forca: float) -> Image.Image:
    """Mancha de luz redonda (glow) com queda suave."""
    n = 2 * raio + 1
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) - raio
    d = np.sqrt(xx ** 2 + yy ** 2) / raio
    a = np.clip(1 - d, 0, 1) ** 2.2 * forca
    im = np.zeros((n, n, 4), np.uint8)
    im[..., :3] = cor
    im[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(im, "RGBA")


def cola_centro(dest: Image.Image, im: Image.Image, cx: float, cy: float) -> None:
    x, y = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


@functools.lru_cache(maxsize=4)
def fundo_escuro(h: int) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:W].astype(np.float32)
    luz = np.clip(1 - np.sqrt(((xx - W / 2) / (W * 0.8)) ** 2 + ((yy - h / 2) / (h * 0.9)) ** 2), 0, 1)
    base = np.array(FUNDO_DIV, np.float32)[None, None, :] + 10 * luz[..., None] ** 2
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")


class Dividida:
    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        self.div = int(H * float(spec.get("divisao", LAY["divisao"]))) // 2 * 2
        self.ph = self.div

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def janela(self, t: float) -> int:
        """y do topo do pedaço da base que vai no painel de baixo (cabeça logo abaixo da divisão)."""
        hh = H - self.div
        return int(cl(topo(t) - LAY["respiro_div"], 0, H - hh))

    def desenha(self, fr: Image.Image, t: float) -> Image.Image:
        y0 = self.janela(t)
        out = Image.new("RGBA", (W, H))
        out.alpha_composite(fr.crop((0, y0, W, y0 + H - self.div)), (0, self.div))
        out.alpha_composite(self.painel(t), (0, 0))
        return out

    def leg_y(self, t: float) -> float:
        return queixo(t) - self.janela(t) + self.div + LAY["leg_div"]

    def fecha(self) -> None:
        pass


class DivididaVideo(Dividida):
    def __init__(self, spec: dict):
        super().__init__(spec)
        self.leitor = LeitorVideo(_resolve(spec["arquivo"]), float(spec.get("inicio", 0)),
                                  float(spec.get("velocidade", 1)), spec.get("recorte"), W, self.ph, self.t0)

    def painel(self, t: float) -> Image.Image:
        return self.leitor.quadro(t)

    def fecha(self) -> None:
        self.leitor.fecha()


class DivididaImagem(Dividida):
    def __init__(self, spec: dict):
        super().__init__(spec)
        im = Image.open(_resolve(spec["arquivo"])).convert("RGBA")
        esc = max(W / im.width, self.ph / im.height)
        im = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
        x, y = (im.width - W) // 2, (im.height - self.ph) // 2
        self.im = im.crop((x, y, x + W, y + self.ph))

    def painel(self, t: float) -> Image.Image:
        return self.im


class DivididaPassos(Dividida):
    """Bolinhas em linha que acendem uma a uma na palavra (o 'step 1…6' da referência).
    item: {"rotulo": "meio", "em": [palavra, tomada], "destaque": true}. Sem "em" = fica apagado."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = []
        for it in spec["itens"]:
            te = T(it["em"]) + ANTECIPA if it.get("em") is not None else None   # acende NA palavra
            self.itens.append({**it, "te": te})
        n = len(self.itens)
        m = 170 if n <= 4 else 110
        self.xs = [m + (W - 2 * m) * i / max(1, n - 1) for i in range(n)]
        self.y = self.ph * 0.47

    def painel(self, t: float) -> Image.Image:
        im = fundo_escuro(self.ph).copy()
        d = ImageDraw.Draw(im)
        trilho = (78, 80, 100, 255)
        d.line((self.xs[0], self.y, self.xs[-1], self.y), fill=trilho, width=3)
        for i in range(1, len(self.itens)):   # o trecho até a próxima bolinha enche antes dela acender
            te = self.itens[i]["te"]
            if te is None:
                continue
            k = ease_in_out((t - (te - 0.35)) / 0.35)
            if k > 0:
                x0 = self.xs[i - 1]
                d.line((x0, self.y, x0 + (self.xs[i] - x0) * k, self.y), fill=(235, 235, 240, 255), width=4)
        for x, it in zip(self.xs, self.itens):
            on = it["te"] is not None and t >= it["te"]
            dest = it.get("destaque", False)
            if on:
                k = mola((t - it["te"]) / 0.3)
                cor = DESTAQUE if dest else (255, 255, 255)
                r = (30 if dest else 18) * k
                pulso = 1 + (0.06 * math.sin((t - it["te"]) * 5) if dest else 0)
                cola_centro(im, brilho(130 if dest else 70, cor, 0.75 if dest else 0.5), x, self.y)
                d.ellipse((x - r * pulso, self.y - r * pulso, x + r * pulso, self.y + r * pulso), fill=cor + (255,))
                f = F("rotulo_destaque", 50) if dest else F("rotulo_on", 38)
                d.text((x, self.y + (78 if dest else 62)), it["rotulo"], font=f, fill=cor + (255,), anchor="mt")
            else:
                d.ellipse((x - 15, self.y - 15, x + 15, self.y + 15), fill=FUNDO_DIV + (255,),
                          outline=(112, 114, 134, 255), width=3)
                d.text((x, self.y + 58), it["rotulo"], font=F("rotulo", 34), fill=(122, 124, 144, 255), anchor="mt")
        return im


class DivididaNos(Dividida):
    """Constelação: um nó central e satélites que acendem (cor própria + brilho) quando a pessoa fala o nome;
    a 'câmera' anda até o satélite aceso (o mapa de agentes da referência, com clique por nome)."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        n = len(spec["itens"])
        angs = spec.get("angulos") or [-150 + 360 * i / n for i in range(n)]
        R_ = min(W, self.ph) * 0.36
        self.itens = []
        for it, a in zip(spec["itens"], angs):
            p = (R_ * math.cos(math.radians(a)), R_ * math.sin(math.radians(a)))
            te = T(it["em"]) + ANTECIPA if it.get("em") is not None else None
            self.itens.append({**it, "p": p, "te": te, "c": hexa(it.get("cor", "#FFFFFF"))})
        rng = np.random.default_rng(7)
        self.estrelas = [(float(x), float(y), int(a)) for x, y, a in
                         zip(rng.uniform(-W * 0.7, W * 0.7, 90), rng.uniform(-self.ph * 0.7, self.ph * 0.7, 90),
                             rng.integers(30, 110, 90))]
        self.centro = spec.get("centro", "")

    def camera(self, t: float) -> tuple[float, float, float]:
        cx, cy, z = 0.0, 0.0, 1.0
        for it in sorted([i for i in self.itens if i["te"] is not None], key=lambda i: i["te"]):
            alvo = (it["p"][0] * 0.42, it["p"][1] * 0.42, 1.16)
            k = ease_in_out((t - (it["te"] - 0.25)) / 0.5)
            if k <= 0:
                break
            cx, cy, z = (cx + (alvo[0] - cx) * k, cy + (alvo[1] - cy) * k, z + (alvo[2] - z) * k)
        return cx, cy, z

    def painel(self, t: float) -> Image.Image:
        im = fundo_escuro(self.ph).copy()
        d = ImageDraw.Draw(im)
        cx, cy, z = self.camera(t)

        def tela(p):
            return (W / 2 + (p[0] - cx) * z, self.ph / 2 + (p[1] - cy) * z)

        for x, y, a in self.estrelas:
            sx, sy = tela((x * 0.6, y * 0.6))   # estrelas andam menos que os nós (profundidade)
            if 0 <= sx < W and 0 <= sy < self.ph:
                d.ellipse((sx - 1.5, sy - 1.5, sx + 1.5, sy + 1.5), fill=(200, 205, 230, a))
        c = tela((0, 0))
        ultimo = max([i["te"] for i in self.itens if i["te"] is not None and t >= i["te"]], default=None)
        for it in self.itens:
            s = tela(it["p"])
            on = it["te"] is not None and t >= it["te"]
            d.line((c, s), fill=(it["c"] + (190,)) if on else (88, 92, 118, 120), width=3 if on else 2)
            if it["te"] is not None and it["te"] - 0.35 <= t < it["te"]:   # pulso viaja do centro até o nó
                k = ease_in_out((t - (it["te"] - 0.35)) / 0.35)
                px, py = c[0] + (s[0] - c[0]) * k, c[1] + (s[1] - c[1]) * k
                cola_centro(im, brilho(26, it["c"], 0.9), px, py)
        cola_centro(im, brilho(int(80 * z), (255, 255, 255), 0.45), *c)
        d.ellipse((c[0] - 20 * z, c[1] - 20 * z, c[0] + 20 * z, c[1] + 20 * z), fill=(255, 255, 255, 255))
        if self.centro:
            d.text((c[0], c[1] + 36 * z), self.centro, font=F("rotulo_on", int(36 * z)), fill=(240, 240, 245, 255),
                   anchor="mt")
        for it in self.itens:
            s = tela(it["p"])
            on = it["te"] is not None and t >= it["te"]
            if on:
                foco = it["te"] == ultimo
                k = mola((t - it["te"]) / 0.3)
                cola_centro(im, brilho(int((150 if foco else 90) * z), it["c"], 0.8 if foco else 0.45), *s)
                r = (24 if foco else 17) * z * k
                d.ellipse((s[0] - r, s[1] - r, s[0] + r, s[1] + r), fill=it["c"] + (255,))
                d.ellipse((s[0] - r - 9, s[1] - r - 9, s[0] + r + 9, s[1] + r + 9), outline=it["c"] + (200,), width=2)
                f = F("rotulo_destaque" if foco else "rotulo_on", int((46 if foco else 36) * z))
                d.text((s[0], s[1] + r + 22), it["rotulo"], font=f,
                       fill=(255, 255, 255, 255) if foco else (220, 222, 232, 255), anchor="mt")
            else:
                r = 13 * z
                d.ellipse((s[0] - r, s[1] - r, s[0] + r, s[1] + r), fill=FUNDO_DIV + (255,),
                          outline=(105, 108, 130, 255), width=3)
                d.text((s[0], s[1] + r + 18), it["rotulo"], font=F("rotulo", int(32 * z)), fill=(118, 120, 142, 255),
                       anchor="mt")
        return im


# ---------------------------------------------------------------- elementos do mapa
_TIPOS_TELAO = {"imagem": TelaoImagem, "video": TelaoVideo, "colagem": TelaoColagem}
_TIPOS_DIV = {"video": DivididaVideo, "imagem": DivididaImagem, "passos": DivididaPassos, "nos": DivididaNos}
FORA_SB: list[tuple[dict, str]] = []   # só no --storyboard: elemento que não deu pra montar (arquivo/palavra)


def _monta(tipos: dict, specs: list[dict]) -> list:
    out = []
    for s in specs:
        try:
            out.append(tipos[s["tipo"]](s))
        except SystemExit as erro:
            if not ARGS.storyboard:
                raise
            FORA_SB.append((s, str(erro)))
    return out


TELAO = _monta(_TIPOS_TELAO, MAPA.get("telao", []))
DIVIDIDA = _monta(_TIPOS_DIV, MAPA.get("dividida", []))
for _lista, _nome in ((TELAO, "telão"), (DIVIDIDA, "tela dividida")):
    for _a, _b in zip(sorted(_lista, key=lambda e: e.t0), sorted(_lista, key=lambda e: e.t0)[1:]):
        if _b.t0 < _a.t1 - 1e-3:
            sys.exit(f"{_nome}: dois elementos ao mesmo tempo ({_a.spec.get('arquivo', _a.spec['tipo'])} até "
                     f"{_a.t1:.2f} e {_b.spec.get('arquivo', _b.spec['tipo'])} a partir de {_b.t0:.2f})")


def ativo(lista, t):
    for e in lista:
        if e.ativo(t):
            return e
    return None


# ================================================================ CTA (texto nativo do Instagram)
CTA = MAPA.get("cta")
if CTA:
    CTA_T0 = T(CTA["em"])
    CTA_T1 = T_fim(CTA.get("ate"), CTA["em"]) if CTA.get("ate") is not None else TOTAL


@functools.lru_cache(maxsize=4)
def caixa_cta(txt: str) -> Image.Image:
    f = F("cta", int(CTA.get("tamanho", 50)))
    tw = int(f.getlength(txt))
    bw, bh = tw + 56, int(f.size * 1.55)
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=22, fill=(255, 255, 255, 255))
    d.text((bw / 2, bh / 2 + 2), txt, font=f, fill=(12, 12, 12, 255), anchor="mm")
    return im


# ================================================================ LEGENDA (uma palavra por vez)
SINAIS = ".,!?;:…\"'“”()[]"


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    out = []
    for i, w in enumerate(WORDS):
        txt = w["t"].strip().strip(SINAIS)
        if not txt:
            continue
        inicio_frase = i == 0 or WORDS[i - 1]["t"].rstrip()[-1:] in ".!?:" or WORDS[i - 1]["seg"] != w["seg"]
        if inicio_frase and not (len(txt) > 1 and txt.isupper()):
            txt = txt[0].lower() + txt[1:]
        fim = WORDS[i + 1]["s"] if i + 1 < len(WORDS) and WORDS[i + 1]["s"] - w["e"] < 0.6 else w["e"] + 0.2
        out.append({"txt": txt, "ini": max(0.0, w["s"] - 0.03), "fim": min(TOTAL, fim - 0.03)})
    return out


@functools.lru_cache(maxsize=512)
def palavra_img(txt: str) -> Image.Image:
    f = F("legenda", LAY["leg_tam"])
    tw = int(f.getlength(txt)) + 60
    th = int(f.size * 1.6)
    camada = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(camada).text((tw / 2, th / 2), txt, font=f, fill=255, anchor="mm")
    sombra = camada.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.6))
    im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    preto = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    preto.putalpha(sombra)
    im.alpha_composite(preto, (0, 4))
    branco = Image.new("RGBA", (tw, th), (255, 255, 255, 255))
    branco.putalpha(camada)
    im.alpha_composite(branco)
    return im


def leg_y(t: float, telao, div, cta_on: bool) -> float:
    lim = H * LAY["leg_max"]
    if div is not None:
        return min(lim, div.leg_y(t))
    if telao is not None and not cta_on:
        return min(lim, queixo(t) + LAY["leg_peito"])
    return max(330, topo(t) - LAY["leg_parede"])     # parede acima da cabeça


# ================================================================ composição
def compoe(fr: Image.Image, t: float, legendas: list[dict]) -> Image.Image:
    div = ativo(DIVIDIDA, t)
    tel = None if div is not None else ativo(TELAO, t)
    if div is not None:
        fr = div.desenha(fr, t)
    elif tel is not None:
        tel.desenha(fr, t)
    cta_on = bool(CTA) and CTA_T0 <= t < CTA_T1
    if cta_on:
        cola_centro(fr, caixa_cta(CTA["texto"]), W / 2, min(H * LAY["leg_max"], queixo(t) + LAY["leg_peito"]))
    for b in legendas:
        if b["ini"] <= t < b["fim"]:
            cola_centro(fr, palavra_img(b["txt"]), W / 2, leg_y(t, tel, div, cta_on))
            break
    return fr


# ================================================================ áudio
def sfx_pop(d=0.09, f0=1100, f1=520):
    n = int(d * SR)
    tt = np.arange(n) / SR
    f = f0 + (f1 - f0) * tt / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 38)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx")
    if cfg:   # referência: sem padrão claro de efeito; se ligar, é um pop discreto em cada entrada
        gdb = cfg.get("db", -26) if isinstance(cfg, dict) else -26
        for e in TELAO + DIVIDIDA:
            s = sfx_pop() * 10 ** (gdb / 20)
            i = int(max(0, e.t0) * SR)
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
def _nome_arq(a) -> str:
    return Path(str(a)).name


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda q, t0, t1: max(t0, min(q, t1 - 0.05))
    estilo_img = {i["nome"]: i.get("estilo") for i in MAPA.get("imagens", [])}
    ms, avisos = [], []
    for e in TELAO:
        sp = e.spec
        if isinstance(e, TelaoColagem):
            tipo = "Telão: colagem de Reels rodando mudos"
            desc = f"{len(e.itens)} vídeos: " + ", ".join(_nome_arq(i["arquivo"]) for i in e.itens)
        elif isinstance(e, TelaoVideo):
            tipo = "Telão: vídeo"
            desc = f"arquivo: {_nome_arq(sp['arquivo'])}"
        else:
            est = estilo_img.get(sp["arquivo"])
            tipo = {"reacao": "Telão: foto de reação", "ilustrativa": "Telão: imagem ilustrativa"}.get(
                est, "Telão: imagem")
            desc = f"arquivo: {_nome_arq(sp['arquivo'])}"
        m = {"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + 0.35, e.t0, e.t1), "tipo": tipo, "desc": desc}
        if e.t1 - e.t0 < 1.2:
            m["aviso"] = f"fica só {e.t1 - e.t0:.1f} s na tela (mín. ~1,2 s)".replace(".", ",")
        ms.append(m)
    for e in DIVIDIDA:
        sp = e.spec
        m = {"t0": e.t0, "t1": e.t1, "quadro": cap(e.t0 + 0.5, e.t0, e.t1)}
        if isinstance(e, DivididaVideo):
            vel = float(sp.get("velocidade", 1))
            m.update(tipo="Tela dividida: gravação de tela", desc=f"arquivo: {_nome_arq(sp['arquivo'])}"
                     + (f", {vel:g}x mais rápido".replace(".", ",") if vel != 1 else ""))
        elif isinstance(e, DivididaImagem):
            m.update(tipo="Tela dividida: imagem", desc=f"arquivo: {_nome_arq(sp['arquivo'])}")
        else:
            passos = isinstance(e, DivididaPassos)
            nomes = [it["rotulo"] + (" (destaque)" if it.get("destaque") else "")
                     + (" (fica apagado)" if it["te"] is None else "") for it in e.itens]
            if passos:
                m.update(tipo="Tela dividida: passos", desc="entra apagado: " + " → ".join(nomes))
            else:
                m.update(tipo="Tela dividida: nós do sistema",
                         desc=(f"centro “{e.centro}”; " if e.centro else "") + "nós: " + ", ".join(nomes))
            # o painel entra apagado: quadro antes do 1º item acender
            tes = [it["te"] for it in e.itens if it["te"] is not None]
            m["quadro"] = cap(min([e.t0 + 0.3] + [te - 0.4 for te in tes]), e.t0, e.t1)
            for it in e.itens:
                if it["te"] is None:
                    continue
                mi = {"t0": it["te"], "t1": e.t1, "quadro": cap(it["te"] + 0.35, it["te"], e.t1),
                      "tipo": "Passo acende" if passos else "Nó acende",
                      "desc": it["rotulo"] + (" (destaque)" if it.get("destaque") else "")}
                if e.t1 - it["te"] < 0.8:
                    mi["aviso"] = (f"acende {e.t1 - it['te']:.1f} s antes da tela sair (mín. ~0,8 s): acender numa "
                                   f"palavra anterior ou estender o 'ate'").replace(".", ",", 1)
                ms.append(mi)
        if e.t1 - e.t0 < 1.2:
            m["aviso"] = f"fica só {e.t1 - e.t0:.1f} s na tela (mín. ~1,2 s)".replace(".", ",")
        ms.append(m)
    if CTA:
        ms.append({"t0": CTA_T0, "t1": CTA_T1, "quadro": cap(CTA_T0 + 0.35, CTA_T0, CTA_T1),
                   "tipo": "CTA (texto nativo do Instagram)", "desc": f"“{CTA['texto']}”; a legenda sobe pra parede"})
    for sp, erro in FORA_SB:
        avisos.append(f"não entrou na edição ({sp.get('tipo')} {sp.get('arquivo', '')}): {erro}")
    cob = sum(1 for k in range(N_FRAMES) if ativo(TELAO, k / FPS) or ativo(DIVIDIDA, k / FPS)) / max(1, N_FRAMES)
    avisos.append(f"com elemento na tela: {cob:.0%} do vídeo (referência: 68%)")
    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]
    arqs = []
    specs = MAPA.get("telao", []) + MAPA.get("dividida", []) + ([MAPA["musica"]] if MAPA.get("musica") else [])
    for spec in specs:
        nomes = [spec.get("arquivo")] + [i.get("arquivo") for i in spec.get("itens", []) if isinstance(i, dict)]
        for a in nomes:
            if a and a not in [x for x, _ in arqs]:
                try:
                    _resolve(a); ok = True
                except SystemExit:
                    ok = False
                arqs.append((a, ok))

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, legendas)

    out = SB.gerar(EDIT, "Telão", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ================================================================ main
def resumo() -> None:
    print("linha do tempo:")
    for e in sorted(TELAO + DIVIDIDA, key=lambda e: e.t0):
        lado = "telão   " if isinstance(e, Telao) else "dividida"
        nome = e.spec.get("arquivo") or e.spec["tipo"]
        print(f"  {e.t0:6.2f}-{e.t1:6.2f} ({e.t1 - e.t0:4.1f}s) {lado} {Path(str(nome)).name}")
    if CTA:
        print(f"  {CTA_T0:6.2f}-{CTA_T1:6.2f} cta      {CTA['texto']}")
    # o que entra na última palavra da frase some com a tomada: conferir quanto tempo fica na tela
    for e in TELAO + DIVIDIDA:
        if e.t1 - e.t0 < 1.2:
            print(f"  ATENÇÃO: {e.spec.get('arquivo', e.spec['tipo'])} fica só {e.t1 - e.t0:.2f}s na tela (mín. ~1,2 s)")
        for it in getattr(e, "itens", []):
            if isinstance(it, dict) and it.get("te") is not None and e.t1 - it["te"] < 0.8:
                print(f"  ATENÇÃO: '{it['rotulo']}' acende {e.t1 - it['te']:.2f}s antes da tela sair "
                      f"(mín. ~0,8 s): acender numa palavra anterior ou estender o 'ate'")
    cob = sum(1 for k in range(N_FRAMES) if ativo(TELAO, k / FPS) or ativo(DIVIDIDA, k / FPS)) / max(1, N_FRAMES)
    print(f"  com elemento na tela: {cob:.0%} do vídeo (referência: 68%)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
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
            compoe(quadro_base(n), t, legendas).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
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
    prenorm = EDIT / f"{modo}_telao.prenorm.mp4"
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
        enc.stdin.write(compoe(fr, t, legendas).convert("RGB").tobytes())
        for e in TELAO + DIVIDIDA:   # fecha o ffmpeg de quem já saiu
            if t >= e.t1:
                e.fecha()
        k += 1
        if k % 300 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_telao.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
