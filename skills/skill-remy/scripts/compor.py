"""compor.py — monta o Reel no estilo "Remy" (quadro branco que pensa junto) quadro a quadro, a partir do mapa.json.

Estilo medido em 22/10/2026 (referencia/referencias-estilo.md): a metade de cima vira um quadro branco de
software que desenha o argumento na palavra exata (lista que ganha itens, riscos à mão, saídas iguais,
leque de cards com foco por desfoque, mapa mental, chat recebendo arquivos), a pessoa em plano aberto embaixo.
Fora do quadro: pasta com os resultados cobrindo o rosto, print com marca-texto, pilha de prints, título
de série na parede, adesivo recortado. Tudo nasce do desfoque ou em cascata; troca de cena no quadro é por
desfoque. Legenda Poppins Bold branca em blocos de 2-3 palavras. Cor de destaque do perfil (padrão #FFC700). Sem música.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_remy.mp4 | final_remy.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (cortar.py), medidas.json (medir.py),
    base_preview.mov | base_final.mov, imagens em <edit>/assets/.

Camadas, de baixo pra cima: base (ou quadro branco em cima + base reenquadrada embaixo) → painel solto →
título na parede → adesivo → legenda / CTA (sempre por último).
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
    """Tempo em que um ITEM acontece: na palavra (sem antecipar), como na referência."""
    if isinstance(spec, list) and len(spec) == 2:
        return T(spec) + ANTECIPA
    return T(spec)


def T_fim(spec_ate, spec_em) -> float:
    if spec_ate is not None:
        return T(spec_ate)
    # sem "ate": vai até o fim da tomada em que entrou
    return OFF[int(spec_em[1]) + 1] if isinstance(spec_em, list) else OFF[grupo(float(spec_em)) + 1]


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


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


# ---------------------------------------------------------------- cores
AMARELO = hexa(MAPA.get("destaque", PERFIL["cor_destaque"]))   # cor de destaque (mapa > perfil)
AMARELO_TXT = (150, 112, 0)                              # amarelo escurecido p/ número em fundo branco
TINTA = (24, 24, 24)
CINZA = (150, 150, 150)
CINZA_CLARO = (226, 226, 224)
LINHA = (43, 43, 43)
VERMELHO = (204, 66, 42)                                 # risco à mão (medido na referência: #CC422A)
BRANCO = (255, 255, 255)

# ---------------------------------------------------------------- fontes (conferidas: fonte errada cai em outra calada)
_AV = "/System/Library/Fonts/Avenir Next.ttc"
_POP = str(SKILL / "assets" / "fonts" / "Poppins-Bold.ttf")
_MENLO = "/System/Library/Fonts/Menlo.ttc"
_NOTE = "/System/Library/Fonts/Noteworthy.ttc"


def _indice(arq: str, estilo: str) -> int:
    for i in range(8):
        try:
            if ImageFont.truetype(arq, 20, index=i).getname()[1] == estilo:
                return i
        except OSError:
            break
    sys.exit(f"não achei o estilo {estilo} em {arq}")


FONTES = {
    "legenda": (_POP, 0, ("Poppins", "Bold")),
    "titulo": (_POP, 0, ("Poppins", "Bold")),
    "ui": (_AV, 2, ("Avenir Next", "Demi Bold")),
    "ui_bold": (_AV, 0, ("Avenir Next", "Bold")),
    "ui_medio": (_AV, 5, ("Avenir Next", "Medium")),
    "mono": (_MENLO, 0, ("Menlo", "Regular")),
    "mao": (_NOTE, _indice(_NOTE, "Bold"), ("Noteworthy", "Bold")),
}
for _k, (_arq, _i, _nome) in FONTES.items():
    if ImageFont.truetype(_arq, 20, index=_i).getname() != _nome:
        sys.exit(f"fonte {_k}: esperava {_nome} em {_arq}[{_i}]")


@functools.lru_cache(maxsize=None)
def F(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    arq, i, _ = FONTES[tipo]
    return ImageFont.truetype(arq, max(6, int(size)), index=i)


def quebra(txt: str, f: ImageFont.FreeTypeFont, maxw: float) -> list[str]:
    linhas, atual = [], ""
    for p in txt.split():
        cand = f"{atual} {p}".strip()
        if f.getlength(cand) <= maxw or not atual:
            atual = cand
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


# ---------------------------------------------------------------- layout (px de 1080x1920; mapa["layout"] sobrescreve)
LAY = {
    "divisao": 0.55,        # quadro branco: altura MÁXIMA do painel de cima (referência: borda a ~55%); a
                            # altura real sai da conta abaixo (PH_QUADRO), igual em todas as cenas
    "sobe": 190,            # a cabeça passa por cima da borda tantos px, medido no ponto MAIS ALTO da tomada
                            # (no resto do tempo passa menos; referência: 120-210 em 1920)
    "boca_max": 0.80,       # com quadro, a base do "rosto" do Vision (≈ boca) não desce além disto
    "faixa_leg": 104,       # com quadro, a legenda vira texto PRETO escrito no quadro, logo acima da cabeça;
                            # esta faixa fica livre de componentes (rosto grande no quadro: no peito não cabe)
    "sobra": 30,            # print solto: base fica isto acima do topo do cabelo
    "topo_min": 150,        # nada sobe acima disto (barra do Instagram)
    "leg_tam": 66,          # legenda Poppins Bold
    "leg_peito": 330,       # legenda em tela cheia: tantos px abaixo do "rosto" do Vision (que termina na boca)
    "leg_max": 0.78,        # legenda nunca desce além disto (interface do Instagram)
    "pasta_lado": 0.86,     # pasta: lado do card quadrado (fração da largura)
    "pasta_cy": 0.44,       # pasta: centro vertical (fração da altura)
}
LAY.update(MAPA.get("layout", {}))

# Altura do quadro: a cabeça sobe "sobe" px por cima da borda e o rosto não pode descer além de boca_max
# (a interface do Instagram cobre o rodapé). Conta feita com o maior rosto do vídeo, pra borda ficar no
# mesmo lugar em todas as cenas.
_ROSTO_MAX = max(g["rosto"][1] + g["rosto"][3] - g["topo"] for g in MED)
PH_QUADRO = int(min(H * LAY["divisao"], H * LAY["boca_max"] - _ROSTO_MAX + LAY["sobe"])) // 2 * 2


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
    """Desfoque com alfa pré-multiplicado (sem franja escura na borda)."""
    if r < 0.4:
        return im
    return im.convert("RGBa").filter(ImageFilter.GaussianBlur(r)).convert("RGBA")


def opaco(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    out = im.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * cl(a))))
    return out


def surge(im: Image.Image, k: float, escala0: float = 0.9, raio0: float = 14) -> Image.Image | None:
    """Entrada por desfoque (o movimento mais repetido da referência): menor e borrado → nítido."""
    if k >= 1:
        return im
    if k <= 0:
        return None
    k = ease_out(k)
    s = lerp(escala0, 1, k)
    w, h = max(2, int(im.width * s)), max(2, int(im.height * s))
    r = raio0 * (1 - k)
    m = int(r * 2) + 2
    tmp = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    tmp.alpha_composite(im.resize((w, h), Image.BILINEAR), (m, m))
    return opaco(desfoca(tmp, r), k)


@functools.lru_cache(maxsize=256)
def cartao(w: int, h: int, r: int = 18, borda: tuple | None = None, bw: int = 0,
           fundo: tuple = BRANCO, sombra: bool = True) -> Image.Image:
    """Card com sombra suave. Margem M em volta (o conteúdo começa em (M, M))."""
    M = CARTAO_M
    im = Image.new("RGBA", (w + 2 * M, h + 2 * M), (0, 0, 0, 0))
    if sombra:
        s = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((M, M + 8, M + w, M + h + 8), radius=r, fill=(0, 0, 0, 46))
        im.alpha_composite(s.filter(ImageFilter.GaussianBlur(13)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((M, M, M + w - 1, M + h - 1), radius=r, fill=fundo + (255,),
                        outline=(borda + (255,)) if borda else None, width=bw)
    return im


CARTAO_M = 28
LISTA_TAM = 50


@functools.lru_cache(maxsize=4)
def fundo_quadro(w: int, h: int) -> Image.Image:
    """Quase branco com degradê leve e grade pontilhada fraca (canvas de Figma)."""
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    base = (lerp(245, 233, 1) * 0 + 245 - 12 * yy)
    arr = np.repeat(np.repeat(base[..., None], w, axis=1), 3, axis=2)
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    for y in range(18, h, 36):
        for x in range(18, w, 36):
            d.ellipse((x - 1.4, y - 1.4, x + 1.4, y + 1.4), fill=(0, 0, 0, 22))
    return im


def traco_mao(d: ImageDraw.ImageDraw, x0: float, y: float, x1: float, k: float, cor: tuple, larg: int = 6,
              seed: int = 0) -> None:
    """Risco de caneta, um pouco torto, crescendo da esquerda pra direita."""
    if k <= 0:
        return
    rng = np.random.default_rng(seed)
    fase, amp = rng.uniform(0, 6), rng.uniform(1.5, 3)
    xe = lerp(x0, x1, ease_out(k))
    n = max(2, int((xe - x0) / 12))
    pts = [(lerp(x0, xe, i / n), y + amp * math.sin(fase + i * 0.9) + (i / n) * 3) for i in range(n + 1)]
    d.line(pts, fill=cor + (255,), width=larg, joint="curve")


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


@functools.lru_cache(maxsize=64)
def imagem(arq: str) -> Image.Image:
    return Image.open(_resolve(arq)).convert("RGBA")


def cobre(im: Image.Image, w: int, h: int, alto: bool = True) -> Image.Image:
    """Redimensiona cobrindo w x h e corta (alto=True mantém o topo, bom pra documento)."""
    esc = max(w / im.width, h / im.height)
    r = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
    x = (r.width - w) // 2
    y = 0 if alto else (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


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


# ================================================================ elemento base
class Elemento:
    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.t1 = T_fim(spec.get("ate"), spec["em"])
        if self.t1 <= self.t0:
            sys.exit(f"{self.nome()}: termina antes de começar ({self.t0:.2f}-{self.t1:.2f})")

    def nome(self) -> str:
        return self.spec.get("arquivo") or self.spec.get("tipo") or self.spec.get("texto") or "?"

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.t1

    def precisa(self) -> float:
        """Quanto a imagem da pessoa precisa descer pra este elemento caber acima da cabeça."""
        return 0.0

    def eventos(self) -> list[tuple[float, str]]:
        """(tempo, som) pros efeitos sonoros."""
        return [(self.t0, "whoosh")]

    def itens_tempos(self) -> list[tuple[str, float]]:
        return []

    def fecha(self) -> None:
        pass


# ================================================================ QUADRO BRANCO (tela dividida)
class Quadro(Elemento):
    escuro = True   # legenda preta escrita no quadro branco (imagem/vídeo cobrindo o quadro: legenda branca)

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.ph = int(H * float(spec["divisao"])) // 2 * 2 if "divisao" in spec else PH_QUADRO
        self.na_frente = bool(spec.get("na_frente", True))   # cabeça da pessoa passa por cima da borda
        # entrada: "corte" (padrão no meio do vídeo, como na referência) ou "surge" (abertura da referência:
        # quadro 0 limpo, o painel dissolve de cima saindo maior e desfocado, a imagem da pessoa desce junto).
        # A 1ª cena do vídeo (em ≈ 0) surge por padrão.
        self.entra = spec.get("entra", "surge" if self.t0 < 0.05 else "corte")
        self.dur_entra = float(spec.get("dur_entra", 0.3))
        # altura útil dos componentes: acima da cabeça e da faixa da legenda
        self.uh = self.ph - (LAY["sobe"] if self.na_frente else 0) - LAY["faixa_leg"]
        self.anterior: Quadro | None = None
        self._ultimo_painel = None

    def entrada(self, t: float) -> float:
        """0 → 1 durante a entrada "surge"; 1 no resto do tempo."""
        if self.entra != "surge" or self.anterior is not None:
            return 1.0
        return ease_out((t - self.t0) / self.dur_entra)

    def dy(self, t: float) -> int:
        """Quanto a imagem da pessoa desce pra cabeça ficar na borda (topo do cabelo 'sobe' px acima dela)."""
        alvo = self.ph - LAY["sobe"] if self.na_frente else self.ph + 20
        return int(max(0, alvo - topo(t)))

    def painel(self, t: float) -> Image.Image:
        im = fundo_quadro(W, self.ph).copy()
        self.conteudo(im, t)
        return im

    def conteudo(self, im: Image.Image, t: float) -> None:
        pass

    def ultimo_painel(self) -> Image.Image:
        if self._ultimo_painel is None:
            self._ultimo_painel = self.painel(self.t1 - 1 / FPS)
        return self._ultimo_painel

    def monta(self, fr: Image.Image, painel: Image.Image, t: float, n: int) -> Image.Image:
        k = self.entrada(t)
        dy = int(self.dy(t) * k)
        if k < 1:   # surge: sai 8% maior (preso no alto), desfocado e transparente, e assenta
            esc = lerp(1.08, 1.0, k)
            g = painel.resize((int(W * esc), int(self.ph * esc)), Image.BILINEAR)
            x0 = (g.width - W) // 2
            painel = opaco(desfoca(g.crop((x0, 0, x0 + W, self.ph)), 10 * (1 - k)), k)
        base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        base.alpha_composite(fr.crop((0, 0, W, H - dy)), (0, dy))
        out = base.copy()
        out.alpha_composite(painel, (0, 0))
        m = mascara(n) if self.na_frente else None
        if m is not None:   # a pessoa recortada passa na frente do quadro (só a parte acima da borda importa)
            mm = Image.new("L", (W, H), 0)
            mm.paste(m.crop((0, 0, W, H - dy)), (0, dy))
            mm = mm.crop((0, 0, W, self.ph))
            sombra = Image.new("RGBA", (W, self.ph), (0, 0, 0, 255))
            sombra.putalpha(mm.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.32)))
            out.alpha_composite(sombra.crop((0, 0, W, self.ph - 8)), (0, 8))   # sombra só no quadro
            pessoa = base.crop((0, 0, W, self.ph))
            pessoa.putalpha(mm)
            out.alpha_composite(pessoa, (0, 0))
        return out

    def leg_y(self, t: float) -> float:
        y = self.ph - (LAY["sobe"] if self.na_frente else 0) - LAY["faixa_leg"] / 2 - 4
        k = self.entrada(t)
        if k < 1:   # durante a entrada a legenda viaja do peito até o quadro
            y = lerp(min(H * LAY["leg_max"], queixo(t) + LAY["leg_peito"]), y, k)
        return y

    def eventos(self):
        # entrada por corte = whoosh; troca de cena dentro do quadro (desfoque) = whoosh mais baixo
        return [(self.t0, "whoosh" if self.anterior is None else "whoosh_baixo")]


class QuadroVideo(Quadro):
    """Gravação de tela no quadro (prova do processo)."""
    escuro = False

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.leitor = LeitorVideo(_resolve(spec["arquivo"]), float(spec.get("inicio", 0)),
                                  float(spec.get("velocidade", 1)), spec.get("recorte"), W, self.ph, self.t0)

    def painel(self, t: float) -> Image.Image:
        return self.leitor.quadro(t)

    def fecha(self) -> None:
        self.leitor.fecha()


class QuadroImagem(Quadro):
    """Imagem cobrindo o quadro (o gancho da referência: imagem no topo, corte seco)."""
    escuro = False

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.im = cobre(imagem(spec["arquivo"]), W, self.ph, alto=False)

    def painel(self, t: float) -> Image.Image:
        return self.im


class QuadroImagens(Quadro):
    """Fotos/miniaturas que representam a fala, em grade, entrando do desfoque na palavra (as capas de
    vídeo de gancho da referência). spec: itens [{arquivo, em, rotulo}], proporcao ("16:9", "4:5", "1:1"),
    colunas, girar (true = colagem levemente torta)."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = spec["itens"]
        n = len(self.itens)
        self.te = [T_na(it["em"]) if it.get("em") is not None else self.t0 + 0.15 * i
                   for i, it in enumerate(self.itens)]
        a, b = (float(v) for v in str(spec.get("proporcao", "16:9")).split(":"))
        asp = a / b
        cols = int(spec.get("colunas") or (n if n <= 3 else 2 if n == 4 else 3))
        rows = math.ceil(n / cols)
        gap = 30
        rot_h = 44 if any(it.get("rotulo") for it in self.itens) else 0
        aw, ah = W - 100, self.uh - 50
        w = (aw - (cols - 1) * gap) / cols
        h = w / asp
        if rows * (h + rot_h) + (rows - 1) * gap > ah:
            h = (ah - (rows - 1) * gap) / rows - rot_h
            w = h * asp
        self.w, self.h, self.rot_h = int(w), int(h), rot_h
        tot_w = cols * w + (cols - 1) * gap
        tot_h = rows * (h + rot_h) + (rows - 1) * gap
        x0, y0 = W / 2 - tot_w / 2, 25 + (ah - tot_h) / 2
        rng = np.random.default_rng(3)
        self.pos = []
        for i in range(n):
            r, c = divmod(i, cols)
            na_linha = min(cols, n - r * cols)   # última linha incompleta fica centralizada
            xl = W / 2 - (na_linha * w + (na_linha - 1) * gap) / 2
            self.pos.append((xl + c * (w + gap) + w / 2, y0 + r * (h + rot_h + gap) + (h + rot_h) / 2,
                             float(rng.uniform(-3, 3)) if spec.get("girar") else 0.0))

    @functools.lru_cache(maxsize=16)
    def _img(self, i: int) -> Image.Image:
        it = self.itens[i]
        w, h = self.w, self.h
        im = cartao(w, h + self.rot_h, r=18).copy()
        foto = cobre(imagem(it["arquivo"]), w, h, alto=False)
        mk = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mk).rounded_rectangle((0, 0, w - 1, h - 1 + (18 if self.rot_h else 0)), radius=18, fill=255)
        im.paste(foto, (CARTAO_M, CARTAO_M), mk)
        if it.get("rotulo"):
            ImageDraw.Draw(im).text((CARTAO_M + w / 2, CARTAO_M + h + self.rot_h / 2), it["rotulo"],
                                    font=F("ui", 30), fill=TINTA + (255,), anchor="mm")
        if self.spec.get("girar"):
            im = im.rotate(-self.pos[i][2], resample=Image.BICUBIC, expand=True)
        return im

    def conteudo(self, im: Image.Image, t: float) -> None:
        for i, (x, y, _) in enumerate(self.pos):
            cola_centro(im, surge(self._img(i), (t - self.te[i]) / 0.2), x, y)

    def eventos(self):
        return super().eventos() + [(te, "pop") for te in self.te[1:]]

    def itens_tempos(self):
        return [(it.get("rotulo") or Path(it["arquivo"]).stem, te) for it, te in zip(self.itens, self.te)]


class QuadroLista(Quadro):
    """Card de lista que ganha um item por fala (o 'STEPS' da referência), com risco à mão, post-it
    e saídas iguais descendo do card.
    spec: titulo, itens [{texto, em, riscar}], riscar (risca todos, em cascata), nota, saidas {n, em, rotulo}."""

    LIN = 98

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = []
        risca_todos = T_na(spec["riscar"]) if spec.get("riscar") is not None else None
        for i, it in enumerate(spec.get("itens", [])):
            te = T_na(it["em"]) if it.get("em") is not None else self.t0
            tr = T_na(it["riscar"]) if it.get("riscar") is not None else (
                risca_todos + 0.12 * i if risca_todos is not None else None)
            self.itens.append({**it, "te": te, "tr": tr})
        self.saidas = spec.get("saidas")
        self.ts = T_na(self.saidas["em"]) if self.saidas else None
        self.nota = spec.get("nota")
        n = max(1, len(self.itens))
        # largura pelo item mais longo; se não couber (com o post-it ao lado), a letra encolhe
        larg_max = W - 70 - (320 if self.nota else 0)
        self.tam = LISTA_TAM
        maior = max([it["texto"] for it in self.itens] or [""], key=len)
        while self.tam > 34 and 84 + F("ui", self.tam).getlength(maior) + 90 > larg_max:
            self.tam -= 2
        self.cw = int(min(larg_max, max(560, 84 + F("ui", self.tam).getlength(maior) + 90)))
        self.ch = 104 + n * self.LIN + 30
        self.cx = (35 + self.cw / 2) if self.nota else W / 2
        if self.saidas:
            self.cy = 46 + self.ch / 2
        else:
            self.cy = self.uh / 2
        self.cab = self._cabecalho()

    def _cabecalho(self) -> Image.Image:
        im = cartao(self.cw, self.ch).copy()
        d = ImageDraw.Draw(im)
        M = CARTAO_M
        d.text((M + 40, M + 38), f"— {self.spec.get('titulo', '').upper()}", font=F("mono", 30), fill=CINZA + (255,))
        return im

    @functools.lru_cache(maxsize=32)
    def _linha(self, i: int) -> Image.Image:
        it = self.itens[i]
        f = F("ui", self.tam)
        im = Image.new("RGBA", (self.cw - 60, self.LIN), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((10, self.LIN / 2), f"{i + 1:02d}", font=F("mono", 34), fill=AMARELO_TXT + (255,), anchor="lm")
        d.text((84, self.LIN / 2), it["texto"], font=f, fill=TINTA + (255,), anchor="lm")
        return im

    @functools.lru_cache(maxsize=8)
    def _nota_img(self) -> Image.Image:
        f = F("mao", 50)
        linhas = quebra(self.nota, f, 210)
        w, h = 270, 64 + 62 * len(linhas)
        im = cartao(w, h, r=6, fundo=(250, 250, 244)).copy()
        d = ImageDraw.Draw(im)
        for k, l in enumerate(linhas):
            d.text((CARTAO_M + 26, CARTAO_M + 30 + 62 * k), l, font=f, fill=(140, 140, 140, 255))
        return im.rotate(-3, resample=Image.BICUBIC, expand=True)

    @functools.lru_cache(maxsize=8)
    def _saida(self, i: int, w: int, h: int) -> Image.Image:
        im = cartao(w, h, r=12).copy()
        d = ImageDraw.Draw(im)
        M = CARTAO_M
        rot = self.saidas.get("rotulo", "SAÍDA")
        d.text((M + 18, M + 20), f"{rot} {i + 1:02d}", font=F("mono", 22), fill=CINZA + (255,))
        d.rounded_rectangle((M + 18, M + 54, M + w * 0.78, M + 68), radius=4, fill=TINTA + (255,))
        for k in range(3):
            y = M + 92 + k * 26
            d.text((M + 18, y - 9), f"{k + 1}", font=F("mono", 16), fill=CINZA + (255,))
            d.rounded_rectangle((M + 40, y - 4, M + w * (0.82 - 0.1 * k), y + 4), radius=3, fill=CINZA_CLARO + (255,))
        d.rounded_rectangle((M + 18, M + h - 44, M + w * 0.5, M + h - 22), radius=5, fill=TINTA + (255,))
        return im

    def conteudo(self, im: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(im)
        cola_centro(im, surge(self.cab, (t - self.t0) / 0.18), self.cx, self.cy)
        x_lin = self.cx - self.cw / 2 + 30
        y_lin0 = self.cy - self.ch / 2 + 104
        for i, it in enumerate(self.itens):
            yc = y_lin0 + i * self.LIN + self.LIN / 2
            cola_centro(im, surge(self._linha(i), (t - it["te"]) / 0.2, escala0=0.96, raio0=10),
                        x_lin + (self.cw - 60) / 2, yc)
            if it["tr"] is not None and t >= it["tr"]:
                larg = 84 + F("ui", self.tam).getlength(it["texto"]) + 24
                traco_mao(d, x_lin, yc + 2, x_lin + larg, (t - it["tr"]) / 0.25, VERMELHO, 8, seed=i)
        if self.nota:
            nx = self.cx + self.cw / 2 + 165
            cola_centro(im, surge(self._nota_img(), (t - self.t0 - 0.1) / 0.2), nx, self.cy - self.ch / 2 + 90)
        if self.saidas and t >= self.ts:
            n = int(self.saidas.get("n", 3))
            ow, oh = 220, 236
            vao = 34
            tot = n * ow + (n - 1) * vao
            xs = [W / 2 - tot / 2 + ow / 2 + i * (ow + vao) for i in range(n)]
            yb = self.cy + self.ch / 2           # base do card
            ybar = yb + 44
            ytop = ybar + 40                     # topo das saídas
            k = ease_out((t - self.ts) / 0.3)
            # tronco → barra → descidas, desenhados em sequência
            d.line((self.cx, yb, self.cx, lerp(yb, ybar, cl(k * 3))), fill=LINHA + (255,), width=3)
            if k > 1 / 3:
                kk = cl((k - 1 / 3) * 3)
                d.line((lerp(self.cx, xs[0], kk), ybar, lerp(self.cx, xs[-1], kk), ybar), fill=LINHA + (255,), width=3)
            if k > 2 / 3:
                kk = cl((k - 2 / 3) * 3)
                for x in xs:
                    d.line((x, ybar, x, lerp(ybar, ytop, kk)), fill=LINHA + (255,), width=3)
            for i, x in enumerate(xs):
                cola_centro(im, surge(self._saida(i, ow, oh), (t - self.ts - 0.3 - 0.12 * i) / 0.18), x, ytop + oh / 2)

    def eventos(self):
        ev = super().eventos()
        if self.ts is not None:
            ev.append((self.ts + 0.3, "pop"))
        for it in self.itens:
            if it["tr"] is not None:
                ev.append((it["tr"], "risco"))
        return ev

    def itens_tempos(self):
        return [(it["texto"], it["te"]) for it in self.itens if it.get("em") is not None]


class QuadroCards(Quadro):
    """Leque de cards; o card falado ganha borda amarela, sobe e fica nítido, o que ainda não foi falado
    fica borrado (o 'Content Principles' da referência). spec: itens [{texto, em}], titulo [l1, l2], titulo_em."""

    CW, CH = 300, 340

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = [{**it, "te": T_na(it["em"]) if it.get("em") is not None else None} for it in spec["itens"]]
        n = len(self.itens)
        self.titulo = spec.get("titulo")
        self.tt = T_na(spec["titulo_em"]) if spec.get("titulo_em") is not None else self.t0 + 0.35
        self.cy = self.uh * (0.34 if self.titulo else 0.5)
        passo = 326 if n <= 3 else 250
        self.pos = []
        for i in range(n):
            a = lerp(-8, 8, i / max(1, n - 1)) if n > 1 else 0
            x = W / 2 + (i - (n - 1) / 2) * passo
            self.pos.append((x, self.cy + abs(a) * 2.2, a))

    @functools.lru_cache(maxsize=64)
    def _card(self, i: int, borrado: bool, ativo: bool) -> Image.Image:
        it = self.itens[i]
        w, h = self.CW, self.CH
        im = cartao(w, h, r=16, borda=AMARELO if ativo else None, bw=7 if ativo else 0).copy()
        conteudo = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(conteudo)
        M = CARTAO_M
        d.text((M + 26, M + 26), f"{i + 1:02d}", font=F("mono", 28), fill=AMARELO_TXT + (255,))
        if it.get("arquivo"):   # card com foto: imagem em cima, nome embaixo
            fw, fh = w - 36, int(h * 0.5)
            foto = cobre(imagem(it["arquivo"]), fw, fh, alto=False)
            mk = Image.new("L", (fw, fh), 0)
            ImageDraw.Draw(mk).rounded_rectangle((0, 0, fw - 1, fh - 1), radius=10, fill=255)
            conteudo.paste(foto, (M + 18, M + 66), mk)
            f = F("ui_bold", 42)
            for k, l in enumerate(quebra(it["texto"], f, w - 52)[:2]):
                d.text((M + 26, M + 76 + fh + 12 + 48 * k), l, font=f, fill=TINTA + (255,))
        else:
            f = F("ui_bold", 50)
            for k, l in enumerate(quebra(it["texto"], f, w - 52)[:3]):
                d.text((M + 26, M + 74 + 60 * k), l, font=f, fill=TINTA + (255,))
        if ativo:
            d.rounded_rectangle((M + 22, M + h - 26, M + w - 60, M + h - 16), radius=5, fill=AMARELO + (255,))
        elif not it.get("arquivo"):
            for k in range(2):
                d.rounded_rectangle((M + 22, M + h - 62 + k * 20, M + w - 50 - 40 * k, M + h - 54 + k * 20),
                                    radius=4, fill=CINZA_CLARO + (255,))
        if borrado:
            conteudo = desfoca(conteudo, 7)
        im.alpha_composite(conteudo)
        return im

    @functools.lru_cache(maxsize=4)
    def _titulo_img(self) -> tuple[Image.Image, Image.Image]:
        f = F("titulo", 96)
        l1, l2 = self.titulo
        im1 = Image.new("RGBA", (int(f.getlength(l1)) + 20, 124), (0, 0, 0, 0))
        ImageDraw.Draw(im1).text((10, 62), l1, font=f, fill=TINTA + (255,), anchor="lm")
        im2 = Image.new("RGBA", (int(f.getlength(l2)) + 20, 124), (0, 0, 0, 0))
        ImageDraw.Draw(im2).text((10, 62), l2, font=f, fill=TINTA + (255,), anchor="lm")
        return im1, im2

    def conteudo(self, im: Image.Image, t: float) -> None:
        ke = ease_out((t - self.t0) / 0.4)          # o leque abre a partir de um card só
        ativos = [i for i, it in enumerate(self.itens) if it["te"] is not None and t >= it["te"]]
        atual = max(ativos, key=lambda i: self.itens[i]["te"]) if ativos else None
        ordem = sorted(range(len(self.itens)), key=lambda i: (i == atual, i))
        for i in ordem:
            it = self.itens[i]
            x, y, a = self.pos[i]
            falado = it["te"] is not None and t >= it["te"]
            if i == atual:
                kk = ease_out((t - it["te"]) / 0.2)
                card = self._card(i, False, True)
                if kk < 1:
                    card = Image.blend(self._card(i, True, False), card, kk)
                sub, esc = 26 * kk, 1 + 0.06 * kk
            else:
                card = self._card(i, not falado, False)
                sub, esc = 0, 1.0
            cx, cy = lerp(W / 2, x, ke), lerp(self.cy, y - sub, ke)
            esc *= lerp(0.6, 1, ke)
            c = card.resize((int(card.width * esc), int(card.height * esc)), Image.BICUBIC) if esc != 1 else card
            c = c.rotate(-a * ke, resample=Image.BICUBIC, expand=True)
            if ke < 1:
                c = opaco(desfoca(c, 10 * (1 - ke)), cl(ke * 2))
            cola_centro(im, c, cx, cy)
        if self.titulo and t >= self.tt:
            im1, im2 = self._titulo_img()
            k = ease_out((t - self.tt) / 0.25)
            y1 = self.uh * 0.74 + 30 * (1 - k)
            cola_centro(im, opaco(im1, k), W / 2, y1)
            y2 = y1 + 104
            km = ease_out((t - self.tt - 0.25) / 0.3)
            if km > 0:   # marca-texto amarelo atrás da 2ª palavra
                d = ImageDraw.Draw(im)
                x0 = W / 2 - im2.width / 2 + 6
                d.rounded_rectangle((x0, y2 + 6, x0 + (im2.width - 12) * km, y2 + 46), radius=8, fill=AMARELO + (255,))
            k2 = ease_out((t - self.tt - 0.12) / 0.25)
            cola_centro(im, opaco(im2, k2), W / 2, y2 + 30 * (1 - k2))

    def eventos(self):
        ev = super().eventos()
        if self.titulo:
            ev.append((self.tt + 0.25, "risco"))
        return ev

    def itens_tempos(self):
        return [(it["texto"], it["te"]) for it in self.itens if it["te"] is not None]


class QuadroMapa(Quadro):
    """Mapa mental: pílula amarela no centro, ramos que se desenham e nós que surgem um a um na fala.
    spec: centro, centro_em, itens [{texto, em}], angulos (opcional)."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.tc = T_na(spec["centro_em"]) if spec.get("centro_em") is not None else self.t0
        n = len(spec["itens"])
        angs = spec.get("angulos") or [-90 + 360 * i / n + (180 / n if n % 2 == 0 else 0) for i in range(n)]
        rx, ry = W * 0.31, self.uh * 0.36
        self.c = (W / 2, self.uh * 0.5)
        self.itens = []
        for i, (it, a) in enumerate(zip(spec["itens"], angs)):
            te = T_na(it["em"]) if it.get("em") is not None else self.tc + 0.3 + 0.2 * i
            p = (self.c[0] + rx * math.cos(math.radians(a)), self.c[1] + ry * math.sin(math.radians(a)))
            self.itens.append({**it, "te": te, "p": p})

    @functools.lru_cache(maxsize=16)
    def _pilula(self, txt: str, centro: bool) -> Image.Image:
        f = F("ui_bold", 58) if centro else F("ui", 44)
        tw = f.getlength(txt)
        w, h = int(tw + (84 if centro else 60)), (104 if centro else 84)
        im = cartao(w, h, r=h // 2, fundo=AMARELO if centro else BRANCO,
                    borda=None if centro else (214, 214, 212), bw=0 if centro else 2).copy()
        ImageDraw.Draw(im).text((im.width / 2, im.height / 2 + 1), txt, font=f, fill=TINTA + (255,), anchor="mm")
        return im

    def conteudo(self, im: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(im)
        for it in self.itens:   # ramo cresce do centro até o nó nos 0,25 s antes do nó surgir
            k = ease_out((t - (it["te"] - 0.25)) / 0.25)
            if k > 0 and t >= self.tc:
                d.line((self.c, (lerp(self.c[0], it["p"][0], k), lerp(self.c[1], it["p"][1], k))),
                       fill=LINHA + (255,), width=4)
        cola_centro(im, surge(self._pilula(self.spec["centro"], True), (t - self.tc) / 0.2), *self.c)
        for it in self.itens:
            pil = self._pilula(it["texto"], False)
            x = cl(it["p"][0], pil.width / 2 - 8, W - pil.width / 2 + 8)   # pílula nunca sai da tela
            cola_centro(im, surge(pil, (t - it["te"]) / 0.18), x, it["p"][1])

    def itens_tempos(self):
        return [(it["texto"], it["te"]) for it in self.itens]


class QuadroChat(Quadro):
    """Caixa de chat; arquivos surgem em cascata e voam pra dentro dela na palavra (o 'you've fed it').
    spec: placeholder, itens [{rotulo, icone: audio|doc|chat|imagem, arquivo}], enviar."""

    IW, IH = 270, 210

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = spec["itens"]
        self.te = [T_na(it["em"]) if it.get("em") is not None else self.t0 + 0.15 + 0.18 * i
                   for i, it in enumerate(self.itens)]
        self.tv = T_na(spec["enviar"]) if spec.get("enviar") is not None else None
        n = len(self.itens)
        vao = 34
        tot = n * self.IW + (n - 1) * vao
        self.xs = [W / 2 - tot / 2 + self.IW / 2 + i * (self.IW + vao) for i in range(n)]
        self.y = self.uh * 0.34
        self.box = (54, self.uh - 150, W - 54, self.uh - 10)

    @functools.lru_cache(maxsize=16)
    def _item(self, i: int) -> Image.Image:
        it = self.itens[i]
        w, h = self.IW, self.IH
        im = cartao(w, h, r=16).copy()
        d = ImageDraw.Draw(im)
        M = CARTAO_M
        cx, cy = M + w / 2, M + 82
        ic = it.get("icone", "doc")
        if ic == "imagem" and it.get("arquivo"):
            im.alpha_composite(cobre(imagem(it["arquivo"]), w - 24, 96), (M + 12, M + 12))
        elif ic == "audio":
            for k, a in enumerate([14, 30, 46, 24, 38, 18, 30, 12]):
                x = cx - 70 + k * 20
                d.rounded_rectangle((x - 5, cy - a / 2, x + 5, cy + a / 2), radius=5, fill=AMARELO + (255,))
        elif ic == "chat":
            d.rounded_rectangle((cx - 52, cy - 34, cx + 52, cy + 22), radius=18, fill=AMARELO + (255,))
            d.polygon([(cx - 30, cy + 20), (cx - 44, cy + 40), (cx - 12, cy + 20)], fill=AMARELO + (255,))
            for k in range(3):
                d.ellipse((cx - 26 + k * 26 - 6, cy - 12, cx - 26 + k * 26 + 6, cy), fill=TINTA + (255,))
        else:   # doc
            d.rounded_rectangle((cx - 34, cy - 44, cx + 34, cy + 40), radius=8, fill=BRANCO + (255,),
                                outline=TINTA + (255,), width=4)
            for k in range(3):
                d.line((cx - 20, cy - 18 + k * 18, cx + 20 - 10 * (k == 2), cy - 18 + k * 18), fill=TINTA + (255,),
                       width=4)
            d.rectangle((cx - 34, cy - 44, cx + 34, cy - 34), fill=AMARELO + (255,))
        d.text((M + w / 2, M + h - 34), it["rotulo"], font=F("ui", 34), fill=TINTA + (255,), anchor="mm")
        return im

    @functools.lru_cache(maxsize=4)
    def _caixa(self, com_anexo: bool) -> Image.Image:
        x0, y0, x1, y1 = self.box
        im = cartao(x1 - x0, y1 - y0, r=30, borda=(218, 218, 216), bw=2).copy()
        d = ImageDraw.Draw(im)
        M = CARTAO_M
        if not com_anexo:
            d.text((M + 40, M + (y1 - y0) / 2), self.spec.get("placeholder", "Pergunte qualquer coisa"),
                   font=F("ui_medio", 42), fill=(160, 160, 160, 255), anchor="lm")
        r = 34
        bx, by = M + (x1 - x0) - 34 - r, M + (y1 - y0) / 2
        d.ellipse((bx - r, by - r, bx + r, by + r), fill=(AMARELO if com_anexo else (210, 210, 208)) + (255,))
        d.line((bx, by + 12, bx, by - 12), fill=TINTA + (255,), width=5)
        d.line((bx - 11, by - 1, bx, by - 13, bx + 11, by - 1), fill=TINTA + (255,), width=5, joint="curve")
        return im

    def conteudo(self, im: Image.Image, t: float) -> None:
        x0, y0, x1, y1 = self.box
        enviado = self.tv is not None and t >= self.tv + 0.2
        cola_centro(im, self._caixa(enviado), (x0 + x1) / 2, (y0 + y1) / 2)
        for i in range(len(self.itens)):
            item = self._item(i)
            if self.tv is None or t < self.tv + 0.06 * i:
                cola_centro(im, surge(item, (t - self.te[i]) / 0.2), self.xs[i], self.y)
                continue
            k = ease_in_out((t - self.tv - 0.06 * i) / 0.4)
            alvo = (x0 + 80 + i * 118, (y0 + y1) / 2)
            esc = lerp(1, 0.38, k)
            c = item.resize((max(2, int(item.width * esc)), max(2, int(item.height * esc))), Image.BICUBIC)
            borrao = 9 * math.sin(math.pi * k)   # borrão de movimento no meio do voo
            cola_centro(im, desfoca(c, borrao), lerp(self.xs[i], alvo[0], k), lerp(self.y, alvo[1], k))

    def eventos(self):
        ev = super().eventos()
        if self.tv is not None:
            ev.append((self.tv, "whoosh"))
        return ev


# ================================================================ PAINEL SOLTO (fora do quadro branco)
class Painel(Elemento):
    def desenha(self, fr: Image.Image, t: float, d: float = 0.0) -> None:
        pass


class PainelPasta(Painel):
    """Card quadrado no meio da tela (cobre o rosto): pasta amarela com contador e miniaturas dos
    resultados entrando uma a uma. spec: rotulo, itens [{arquivo, em}], selo ("✓ PRONTO")."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.lado = int(W * LAY["pasta_lado"]) // 2 * 2
        self.cy = H * LAY["pasta_cy"]
        self.itens = spec["itens"]
        self.te = [T_na(it["em"]) if it.get("em") is not None else self.t0 + 0.35 + 0.3 * i
                   for i, it in enumerate(self.itens)]
        n = len(self.itens)
        self.tw = 196 if n <= 4 else 160
        self.th = int(self.tw * 1.36)

    @functools.lru_cache(maxsize=2)
    def _fundo(self) -> Image.Image:
        s = self.lado
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        im.alpha_composite(fundo_quadro(s, s))
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, s - 1, s - 1), radius=8, fill=255)
        im.putalpha(m)
        return im

    @functools.lru_cache(maxsize=16)
    def _thumb(self, i: int) -> Image.Image:
        w, h = self.tw, self.th
        b = 5
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        foto = cobre(imagem(self.itens[i]["arquivo"]), w - 2 * b, h - 2 * b)
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=255)
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=AMARELO + (255,))
        im.paste(foto, (b, b))
        im.putalpha(m)
        selo = self.spec.get("selo", "✓ PRONTO")
        f = F("ui_bold", 20)
        sw = int(f.getlength(selo)) + 26
        out = Image.new("RGBA", (w, h + 18), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 18))
        d = ImageDraw.Draw(out)
        d.rounded_rectangle((w / 2 - sw / 2, 2, w / 2 + sw / 2, 34), radius=16, fill=AMARELO + (255,))
        d.text((w / 2, 18), selo, font=f, fill=TINTA + (255,), anchor="mm")
        return out

    def _pasta(self, n: int) -> Image.Image:
        f = F("ui_bold", 40)
        txt = self.spec.get("rotulo", "resultados")
        tw = f.getlength(txt)
        w, h = int(tw + 200), 92
        im = cartao(w, h, r=24, fundo=AMARELO).copy()
        d = ImageDraw.Draw(im)
        M = CARTAO_M
        x, y = M + 30, M + h / 2
        d.rounded_rectangle((x, y - 18, x + 50, y + 22), radius=5, fill=TINTA + (255,))
        d.rounded_rectangle((x, y - 26, x + 22, y - 12), radius=4, fill=TINTA + (255,))
        d.text((x + 70, y + 1), txt, font=f, fill=TINTA + (255,), anchor="lm")
        bx = M + w - 50
        d.ellipse((bx - 26, y - 26, bx + 26, y + 26), fill=BRANCO + (255,))
        d.text((bx, y + 1), f"×{n}", font=F("ui_bold", 26), fill=TINTA + (255,), anchor="mm")
        return im

    def desenha(self, fr: Image.Image, t: float, desc: float = 0.0) -> None:
        s = self.lado
        x0, y0 = int(W / 2 - s / 2), int(self.cy - s / 2)
        fr.alpha_composite(self._fundo(), (x0, y0))
        d = ImageDraw.Draw(fr)
        n = len(self.itens)
        vao = 26
        tot = n * self.tw + (n - 1) * vao
        xs = [W / 2 - tot / 2 + self.tw / 2 + i * (self.tw + vao) for i in range(n)]
        py = y0 + s * 0.26
        ybar = py + 90
        yth = y0 + s * 0.66
        entrou = sum(1 for te in self.te if t >= te)
        for i, x in enumerate(xs):   # ramo desce até a miniatura logo antes dela entrar
            k = ease_out((t - (self.te[i] - 0.2)) / 0.2)
            if k <= 0:
                continue
            d.line((W / 2, py + 40, W / 2, ybar), fill=LINHA + (255,), width=3)
            d.line((W / 2, ybar, lerp(W / 2, x, k), ybar), fill=LINHA + (255,), width=3)
            if k >= 1:
                d.line((x, ybar, x, yth - self.th / 2 - 8), fill=LINHA + (255,), width=3)
        cola_centro(fr, self._pasta(entrou), W / 2, py)
        for i, x in enumerate(xs):
            cola_centro(fr, surge(self._thumb(i), (t - self.te[i]) / 0.22, escala0=0.85, raio0=16), x, yth)

    def eventos(self):
        return [(self.t0, "whoosh")] + [(te, "pop") for te in self.te]

    def cobre_y(self, y: float) -> bool:
        """A legenda cai em cima do card? (aí ela fica preta)"""
        return abs(y - self.cy) < self.lado / 2 - 20

    def itens_tempos(self):
        return [(Path(it["arquivo"]).stem, te) for it, te in zip(self.itens, self.te)]


class PainelPrint(Painel):
    """Print solto acima da cabeça (Insights, painel de vendas) com marca-texto passando no número na
    palavra. spec: arquivo, largura, marcas [{em, caixa: [x, y, w, h] em px da imagem original}]."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        src = imagem(spec["arquivo"])
        w = int(W * float(spec.get("largura", 0.86)))
        self.esc = w / src.width
        self.im = src.resize((w, int(src.height * self.esc)), Image.LANCZOS)
        self.marcas = [{**m, "te": T_na(m["em"])} for m in spec.get("marcas", [])]

    def precisa(self) -> float:
        return max(0.0, LAY["topo_min"] + self.im.height + LAY["sobra"] - topo(self.t0))

    def desenha(self, fr: Image.Image, t: float, d: float = 0.0) -> None:
        im = self.im.copy()
        dr = ImageDraw.Draw(im, "RGBA")
        for m in self.marcas:
            k = ease_out((t - m["te"]) / 0.25)
            if k > 0:
                x, y, w, h = [v * self.esc for v in m["caixa"]]
                dr.rounded_rectangle((x - 6, y - 4, x - 6 + (w + 12) * k, y + h + 4), radius=6, fill=AMARELO + (150,))
        base = topo(t) + d - LAY["sobra"]
        y = max(LAY["topo_min"], base - im.height)
        cola_centro(fr, opaco(im, ease_out((t - self.t0) / 0.15)), W / 2, y + im.height / 2)

    def eventos(self):
        return [(self.t0, "whoosh")] + [(m["te"], "risco") for m in self.marcas]


class PainelPilha(Painel):
    """Prints caindo empilhados, um a cada 'passo' s, cada um mais baixo (os perfis estudados).
    spec: itens [arquivo ou {arquivo, em}], largura, degrau, passo."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.itens = [it if isinstance(it, dict) else {"arquivo": it} for it in spec["itens"]]
        larg = int(W * float(spec.get("largura", 0.84)))
        self.ims = []
        for it in self.itens:
            src = imagem(it["arquivo"])
            self.ims.append(src.resize((larg, int(src.height * larg / src.width)), Image.LANCZOS))
        passo = float(spec.get("passo", 0.4))
        self.te = [T_na(it["em"]) if it.get("em") is not None else self.t0 + passo * i
                   for i, it in enumerate(self.itens)]
        self.degrau = int(spec.get("degrau", 210))

    def desenha(self, fr: Image.Image, t: float, d: float = 0.0) -> None:
        for i, (im, te) in enumerate(zip(self.ims, self.te)):
            k = ease_out((t - te) / 0.22)
            if k <= 0:
                continue
            top = LAY["topo_min"] + 60 + i * self.degrau - 40 * (1 - k)
            cola_centro(fr, surge(im, k, escala0=0.96, raio0=10), W / 2, top + im.height / 2)

    def eventos(self):
        return [(te, "whoosh_baixo") for te in self.te]


# ================================================================ TÍTULO NA PAREDE (vinheta)
class Titulo(Elemento):
    """Texto grande branco na parede acima da cabeça + etiqueta em fita amarela com letra de mão.
    spec: texto, etiqueta, em, ate."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.tag_t = self.t0 + float(spec.get("atraso_etiqueta", 0.25))

    @functools.lru_cache(maxsize=4)
    def _texto(self) -> Image.Image:
        txt = self.spec["texto"]
        tam = 210
        f = F("titulo", tam)
        while f.getlength(txt) > W * 0.8 and tam > 90:
            tam -= 6
            f = F("titulo", tam)
        tw = int(f.getlength(txt)) + 60
        th = int(tam * 1.25)
        cam = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(cam).text((tw / 2, th / 2), txt, font=f, fill=255, anchor="mm")
        im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        sombra = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
        sombra.putalpha(cam.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.45)))
        im.alpha_composite(sombra, (0, 5))
        branco = Image.new("RGBA", (tw, th), BRANCO + (255,))
        branco.putalpha(cam)
        im.alpha_composite(branco)
        return im

    @functools.lru_cache(maxsize=4)
    def _etiqueta(self) -> Image.Image:
        txt = self.spec.get("etiqueta", "")
        f = F("mao", 70)
        tw = int(f.getlength(txt))
        w, h = tw + 70, 104
        im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        s = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rectangle((20, 26, 20 + w, 26 + h), fill=(0, 0, 0, 70))
        im.alpha_composite(s.filter(ImageFilter.GaussianBlur(8)))
        d = ImageDraw.Draw(im)
        d.rectangle((20, 20, 20 + w, 20 + h), fill=AMARELO + (255,))
        d.text((20 + w / 2, 20 + h / 2 + 2), txt, font=f, fill=TINTA + (255,), anchor="mm")
        return im.rotate(5, resample=Image.BICUBIC, expand=True)

    def precisa(self) -> float:
        return max(0.0, LAY["topo_min"] + self._texto().height + 30 - topo(self.t0))

    def desenha(self, fr: Image.Image, t: float, d: float = 0.0) -> None:
        tx = self._texto()
        cy = max(LAY["topo_min"] + tx.height / 2, topo(t) + d - 30 - tx.height / 2)
        cola_centro(fr, surge(tx, (t - self.t0) / 0.14, escala0=0.94, raio0=18), W / 2, cy)
        if self.spec.get("etiqueta") and t >= self.tag_t:
            et = self._etiqueta()
            k = mola((t - self.tag_t) / 0.3)
            e = et.resize((max(2, int(et.width * k)), max(2, int(et.height * k))), Image.BICUBIC)
            cola_centro(fr, e, W / 2 + tx.width / 2 - et.width * 0.62, cy + tx.height * 0.5 + et.height * 0.22)

    def eventos(self):
        ev = [(self.t0, "whoosh")]
        if self.spec.get("etiqueta"):
            ev.append((self.tag_t, "pop"))
        return ev


# ================================================================ ADESIVO (recorte com contorno branco)
class Adesivo(Elemento):
    """Colagem em primeiro plano: PNG com fundo transparente, borda branca de papel recortado à mão,
    NA FRENTE da pessoa (o cara com cabeça de máquina de escrever da referência), por corte seco. Vários podem
    estar ao mesmo tempo (colagem). spec: arquivo, em, ate, largura (0.62), x (0.68, centro), y (centro;
    padrão = preso na base da tela), giro (graus), entra ("corte" | "pop")."""

    def __init__(self, spec: dict):
        super().__init__(spec)
        src = imagem(spec["arquivo"])
        bb = src.getchannel("A").point(lambda v: 255 if v > 30 else 0).getbbox()
        if bb:
            src = src.crop(bb)
        w = int(W * float(spec.get("largura", 0.62)))
        im = src.resize((w, int(src.height * w / src.width)), Image.LANCZOS)
        b = 14
        big = Image.new("RGBA", (im.width + 6 * b, im.height + 6 * b), (0, 0, 0, 0))
        big.alpha_composite(im, (3 * b, 3 * b))
        a = big.getchannel("A").point(lambda v: 255 if v > 40 else 0)
        dentro = a.filter(ImageFilter.MaxFilter(2 * (b - 5) + 1))
        fora = a.filter(ImageFilter.MaxFilter(2 * (b + 5) + 1))
        rng = np.random.default_rng(len(spec["arquivo"]))
        ruido = Image.fromarray((rng.random((big.height // 6 + 1, big.width // 6 + 1)) * 255).astype(np.uint8))
        ruido = ruido.resize(big.size, Image.BICUBIC).point(lambda v: 255 if v > 120 else 0)
        papel = Image.composite(fora, dentro, ruido)   # borda irregular, como recortado com tesoura
        borda = Image.new("RGBA", big.size, BRANCO + (255,))
        borda.putalpha(papel.filter(ImageFilter.GaussianBlur(0.8)))
        sombra = Image.new("RGBA", big.size, (0, 0, 0, 255))
        sombra.putalpha(papel.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35)))
        out = Image.new("RGBA", big.size, (0, 0, 0, 0))
        out.alpha_composite(sombra, (0, 8))
        out.alpha_composite(borda)
        out.alpha_composite(big)
        giro = float(spec.get("giro", 0))
        self.im = out.rotate(giro, resample=Image.BICUBIC, expand=True) if giro else out

    def desenha(self, fr: Image.Image, t: float) -> None:
        im = self.im
        if self.spec.get("entra") == "pop":
            k = mola((t - self.t0) / 0.3)
            im = im.resize((max(2, int(im.width * k)), max(2, int(im.height * k))), Image.BICUBIC)
        x = W * float(self.spec.get("x", 0.68))
        y = H * float(self.spec["y"]) if "y" in self.spec else H - self.im.height / 2 + 30
        cola_centro(fr, im, x, y)

    def eventos(self):
        return [(self.t0, "pop")]


# ---------------------------------------------------------------- elementos do mapa
_TIPOS_QUADRO = {"imagens": QuadroImagens, "lista": QuadroLista, "cards": QuadroCards, "mapa": QuadroMapa, "chat": QuadroChat,
                 "video": QuadroVideo, "imagem": QuadroImagem}
_TIPOS_PAINEL = {"pasta": PainelPasta, "print": PainelPrint, "pilha": PainelPilha}
QUADRO = [_TIPOS_QUADRO[s["tipo"]](s) for s in MAPA.get("quadro", [])]
PAINEL = [_TIPOS_PAINEL[s["tipo"]](s) for s in MAPA.get("painel", [])]
TITULO = [Titulo(s) for s in MAPA.get("titulo", [])]
ADESIVO = [Adesivo(s) for s in MAPA.get("adesivo", [])]
for _lista, _nome in ((QUADRO, "quadro"), (PAINEL, "painel"), (TITULO, "título")):   # adesivos podem se somar
    _ord = sorted(_lista, key=lambda e: e.t0)
    for _a, _b in zip(_ord, _ord[1:]):
        if _b.t0 < _a.t1 and "ate" not in _a.spec and _b.t0 > _a.t0 + 0.5:
            _a.t1 = _b.t0   # sem "ate" explícito, a cena de trás cede o lugar pra que entra antecipada
        if _b.t0 < _a.t1 - 1e-3:
            sys.exit(f"{_nome}: dois elementos ao mesmo tempo ({_a.nome()} até {_a.t1:.2f} e {_b.nome()} "
                     f"a partir de {_b.t0:.2f})")
        if _nome == "quadro" and abs(_b.t0 - _a.t1) < 0.06:
            _b.anterior = _a   # cenas coladas: a de trás sai por desfoque
for _q in QUADRO:
    for _p in PAINEL:
        if _p.t0 < _q.t1 - 1e-3 and _q.t0 < _p.t1 - 1e-3:
            sys.exit(f"quadro {_q.nome()} e painel {_p.nome()} ao mesmo tempo ({max(_q.t0, _p.t0):.2f})")


def janelas_mascara() -> list[tuple[float, float]]:
    """Trechos em que a pessoa passa na frente do quadro (o mascaras.py recorta só esses quadros)."""
    return [(q.t0 - 0.05, q.t1 + 0.05) for q in QUADRO if q.na_frente]


_MASC = {"n": None, "im": None}


def mascara(n: int) -> Image.Image | None:
    if _MASC["n"] != n:
        p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
        _MASC["n"], _MASC["im"] = n, (Image.open(p).convert("L") if p.exists() else None)
    return _MASC["im"]


def ativo(lista, t):
    for e in lista:
        if e.ativo(t):
            return e
    return None


# ================================================================ CTA (palavra grande na legenda)
CTA = MAPA.get("cta")
if CTA:
    CTA_T0 = T(CTA["em"])
    CTA_T1 = T_fim(CTA.get("ate"), CTA["em"]) if CTA.get("ate") is not None else TOTAL
    CTA_TP = T_na(CTA["palavra_em"]) if CTA.get("palavra_em") is not None else CTA_T0


@functools.lru_cache(maxsize=4)
def cta_imgs() -> tuple[Image.Image, Image.Image]:
    l1 = texto_leg(CTA.get("texto", "comenta"), LAY["leg_tam"] * 0.9, BRANCO)
    pal = CTA["palavra"]
    if CTA.get("aspas", True):
        pal = f"“{pal}”"
    tam = 128
    while F("legenda", tam).getlength(pal) > W * 0.88 and tam > 60:
        tam -= 4
    return l1, texto_leg(pal, tam, AMARELO)


# ================================================================ LEGENDA (blocos de 2-3 palavras)
SINAIS = ".,!?;:…\"'“”()[]"


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
            partes.append(t)
        ini = WORDS[b[0]]["s"] - 0.03
        prox = WORDS[blocos[k + 1][0]]["s"] - 0.03 if k + 1 < len(blocos) else TOTAL
        fim = prox if prox - WORDS[b[-1]]["e"] < 0.6 else WORDS[b[-1]]["e"] + 0.2
        out.append({"txt": " ".join(partes), "ini": max(0.0, ini), "fim": min(TOTAL, fim)})
    return out


@functools.lru_cache(maxsize=1024)
def texto_leg(txt: str, tam: float, cor: tuple = BRANCO) -> Image.Image:
    f = F("legenda", int(tam))
    tw = int(f.getlength(txt)) + 60
    th = int(f.size * 1.6)
    cam = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(cam).text((tw / 2, th / 2), txt, font=f, fill=255, anchor="mm")
    contorno = Image.new("L", (tw, th), 0)   # contorno escuro fino: lê também em cima do quadro branco
    ImageDraw.Draw(contorno).text((tw / 2, th / 2), txt, font=f, fill=255, anchor="mm", stroke_width=3,
                                  stroke_fill=255)
    im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    preto = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    preto.putalpha(cam.filter(ImageFilter.GaussianBlur(8)).point(lambda v: int(v * 0.6)))
    im.alpha_composite(preto, (0, 4))
    preto2 = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    preto2.putalpha(contorno.point(lambda v: int(v * 0.55)))
    im.alpha_composite(preto2)
    corpo = Image.new("RGBA", (tw, th), cor + (255,))
    corpo.putalpha(cam)
    im.alpha_composite(corpo)
    return im


@functools.lru_cache(maxsize=1024)
def texto_quadro(txt: str, tam: float) -> Image.Image:
    """Legenda escrita no quadro branco: preta, sem sombra (a referência inverte a legenda em fundo claro)."""
    f = F("legenda", int(tam))
    im = Image.new("RGBA", (int(f.getlength(txt)) + 60, int(f.size * 1.6)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((im.width / 2, im.height / 2), txt, font=f, fill=TINTA + (255,), anchor="mm")
    return im


def leg_y(t: float, q, d: float = 0.0) -> float:
    lim = H * LAY["leg_max"]
    if q is not None:
        return min(lim, q.leg_y(t))
    return min(lim, queixo(t) + d + LAY["leg_peito"])


# ================================================================ DESCIDA (o rosto da pessoa fica alto no quadro)
def descida(t: float) -> float:
    """Quanto a imagem desce agora: entra em 0,3 s quando um título/print precisa de parede e volta em
    0,25 s quando ele sai (não volta se ele vai até o fim do vídeo)."""
    d = 0.0
    for e in TITULO + PAINEL:
        p = e.precisa()
        if p <= 0 or not e.ativo(t):
            continue
        k = ease_out((t - e.t0) / 0.3)
        if e.t1 < TOTAL - 0.05:
            k = min(k, ease_out((e.t1 - t) / 0.25))
        d = max(d, p * k)
    return d


_SOMBRA_BORDA = None


def desce(fr: Image.Image, d: float) -> Image.Image:
    """Empurra a imagem d px pra baixo; o espaço de cima vira continuação da parede (topo esticado,
    borrado e um pouco mais escuro), com uma sombra suave na emenda."""
    global _SOMBRA_BORDA
    d = int(round(d))
    if _SOMBRA_BORDA is None:
        g = np.zeros((40, W, 4), np.uint8)
        g[..., 3] = np.linspace(0, 70, 40).astype(np.uint8)[:, None]
        _SOMBRA_BORDA = Image.fromarray(g, "RGBA")
    out = Image.new("RGBA", (W, H))
    faixa = fr.crop((0, 0, W, 24)).resize((W, d + 24), Image.BILINEAR).filter(ImageFilter.GaussianBlur(18))
    faixa = Image.eval(faixa.convert("RGB"), lambda v: int(v * 0.86)).convert("RGBA")
    out.alpha_composite(faixa, (0, 0))
    out.alpha_composite(fr.crop((0, 0, W, H - d)), (0, d))
    out.alpha_composite(_SOMBRA_BORDA, (0, max(0, d - 40)))
    return out


# ================================================================ composição
def compoe(fr: Image.Image, t: float, legendas: list[dict], n: int) -> Image.Image:
    q = ativo(QUADRO, t)
    if q is not None:
        pan = q.painel(t)
        if q.anterior is not None and t < q.t0 + 0.3:   # troca de cena: a anterior borra e some
            k = ease_out((t - q.t0) / 0.3)
            velho = desfoca(q.anterior.ultimo_painel(), 4 + 26 * k)
            if velho.size != pan.size:
                velho = velho.resize(pan.size)
            pan = pan.copy()
            pan.alpha_composite(opaco(velho, 1 - k))
        fr = q.monta(fr, pan, t, n)
    d = 0.0
    if q is None:
        d = descida(t)
        if d > 0.5:
            fr = desce(fr, d)
        p = ativo(PAINEL, t)
        if p is not None:
            p.desenha(fr, t, d)
        tit = ativo(TITULO, t)
        if tit is not None:
            tit.desenha(fr, t, d)
    for a in ADESIVO:
        if a.ativo(t):
            a.desenha(fr, t)
    y = leg_y(t, q, d)
    if CTA and CTA_T0 <= t < CTA_T1:
        l1, l2 = cta_imgs()
        if t < CTA_TP:
            cola_centro(fr, l1, W / 2, y)
        else:
            k = mola((t - CTA_TP) / 0.3)
            cola_centro(fr, l1, W / 2, y - 40)
            e = l2.resize((max(2, int(l2.width * k)), max(2, int(l2.height * k))), Image.BICUBIC)
            cola_centro(fr, e, W / 2, y + l2.height * 0.42)
        return fr
    for b in legendas:
        if b["ini"] <= t < b["fim"]:
            escuro = (q is not None and q.escuro and q.entrada(t) >= 0.5) or (q is None and isinstance(ativo(PAINEL, t), PainelPasta)
                                                       and ativo(PAINEL, t).cobre_y(y))
            img = texto_quadro(b["txt"], LAY["leg_tam"]) if escuro else texto_leg(b["txt"], LAY["leg_tam"])
            cola_centro(fr, img, W / 2, y)
            break
    return fr


# ================================================================ áudio (sem música; efeito curto nas entradas)
def _env(n: int, sobe: float) -> np.ndarray:
    tt = np.linspace(0, 1, n)
    return np.where(tt < sobe, tt / sobe, ((1 - tt) / (1 - sobe)) ** 2)


def sfx(nome: str) -> np.ndarray:
    rng = np.random.default_rng(len(nome))
    if nome.startswith("whoosh"):
        d = 0.32
        n = int(d * SR)
        ruido = rng.standard_normal(n)
        esp = np.fft.rfft(ruido)
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= np.exp(-((np.log(f + 1) - np.log(2200)) ** 2) / 0.9)   # banda em volta de ~2 kHz
        x = np.fft.irfft(esp, n) * _env(n, 0.55)
        x /= np.abs(x).max() + 1e-9
        return x * (0.5 if nome == "whoosh_baixo" else 1.0)
    if nome == "risco":   # caneta/marca-texto: ruído agudo curto
        d = 0.16
        n = int(d * SR)
        x = rng.standard_normal(n)
        esp = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        esp *= (f > 3000) * (f < 9000)
        x = np.fft.irfft(esp, n) * _env(n, 0.2)
        return x / (np.abs(x).max() + 1e-9) * 0.45
    d = 0.09   # pop
    n = int(d * SR)
    tt = np.arange(n) / SR
    fr = 1100 + (520 - 1100) * tt / d
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 38)


def eventos_som() -> list[tuple[float, str]]:
    ev = []
    for e in QUADRO + PAINEL + TITULO + ADESIVO:
        ev += e.eventos()
    if CTA and CTA.get("palavra_em") is not None:
        ev.append((CTA_TP, "pop"))
    return sorted(ev)


def trilha_extra() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    cfg = MAPA.get("sfx", True)
    if cfg:
        gdb = cfg.get("db", -24) if isinstance(cfg, dict) else -24
        ultimo = -9.0
        for t, nome in eventos_som():
            if t - ultimo < 0.12:   # dois sons colados viram um
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
NOMES_SB = {"imagem": "Quadro: foto-meme cobrindo o quadro", "video": "Quadro: gravação de tela",
            "imagens": "Quadro branco: fotos da fala", "lista": "Quadro branco: lista que ganha itens",
            "cards": "Quadro branco: leque de cards", "mapa": "Quadro branco: mapa mental",
            "chat": "Quadro branco: chat recebendo arquivos",
            "pasta": "Pasta com os resultados (cobre o rosto)", "print": "Print com marca-texto",
            "pilha": "Pilha de prints"}


def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda t, t1: min(t, t1 - 0.05)
    br = lambda s: s.replace(".", ",")
    stem = lambda a: Path(str(a)).stem
    ms, avisos = [], []

    def partes(e) -> tuple[float, list[tuple[str, float, float]], str, str]:
        """(quando a base do elemento está inteira, [(item, quando acontece, quando está inteiro)], tipo, desc)."""
        sp = e.spec
        itens, desc = [], []
        if isinstance(e, Quadro):
            tipo = NOMES_SB.get(sp["tipo"], sp["tipo"])
            if e.anterior is not None:
                ent, desc = 0.35, ["troca por desfoque"]
            elif e.entra == "surge":
                ent, desc = e.dur_entra + 0.05, [br(f"surge do desfoque em {e.dur_entra:.1f} s")]
            else:
                ent, desc = 0.3, ["entra por corte seco"]
            if not e.na_frente:
                desc.append("cabeça embaixo da borda")
            base = e.t0 + ent
            if isinstance(e, QuadroImagens):
                itens = [(n, te, te + 0.25) for n, te in e.itens_tempos()]
            elif isinstance(e, QuadroLista):
                desc.append(f"título: {sp.get('titulo', '')}" + (f" · post-it: {e.nota}" if e.nota else ""))
                ja = [it["texto"] for it in e.itens if it.get("em") is None]
                if ja:
                    desc.append("já na lista: " + " · ".join(ja))
                itens = [(it["texto"], it["te"], it["te"] + 0.25) for it in e.itens if it.get("em") is not None]
                itens += [(f"risco em {it['texto']}", it["tr"], it["tr"] + 0.3) for it in e.itens if it["tr"] is not None]
                if e.saidas:
                    n = int(e.saidas.get("n", 3))
                    itens.append((f"{n} saídas iguais", e.ts, e.ts + 0.3 + 0.12 * (n - 1) + 0.2))
            elif isinstance(e, QuadroCards):
                itens = [(it["texto"], it["te"], it["te"] + 0.3) for it in e.itens if it["te"] is not None]
                if e.titulo:
                    itens.append(("título: " + " / ".join(e.titulo), e.tt, e.tt + 0.35))
            elif isinstance(e, QuadroMapa):
                itens = [(f"centro {sp['centro']}", e.tc, e.tc + 0.25)] + \
                        [(n, te, te + 0.2) for n, te in e.itens_tempos()]
            elif isinstance(e, QuadroChat):
                itens = [(it["rotulo"], te, te + 0.25) for it, te in zip(e.itens, e.te)]
                if e.tv is not None:
                    itens.append(("arquivos voam pro chat", e.tv, e.tv + 0.06 * (len(e.itens) - 1) + 0.45))
        elif isinstance(e, Painel):
            tipo = NOMES_SB.get(sp["tipo"], sp["tipo"])
            base = e.t0 + 0.4
            if isinstance(e, PainelPasta):
                desc.append(f"pasta {sp.get('rotulo', '')} · selo {sp.get('selo', '✓ PRONTO')}")
                itens = [(n, te, te + 0.25) for n, te in e.itens_tempos()]
            elif isinstance(e, PainelPrint):
                itens = [(f"marca-texto {i + 1}", m["te"], m["te"] + 0.3) for i, m in enumerate(e.marcas)]
            elif isinstance(e, PainelPilha):
                itens = [(stem(it["arquivo"]), te, te + 0.25) for it, te in zip(e.itens, e.te)]
        elif isinstance(e, Titulo):
            tipo = "Título na parede" + (" com fita amarela" if sp.get("etiqueta") else "")
            desc.append(sp["texto"] + (f" + {sp['etiqueta']}" if sp.get("etiqueta") else ""))
            base = max(e.t0 + 0.35, e.tag_t + 0.35 if sp.get("etiqueta") else 0)
        else:   # Adesivo
            tipo = "Recorte de papel em primeiro plano"
            desc.append("entra com mola" if sp.get("entra") == "pop" else "entra por corte seco")
            base = e.t0 + (0.35 if sp.get("entra") == "pop" else 0.1)
        if e.precisa() > 0:
            desc.append(f"a imagem da pessoa desce {e.precisa():.0f} px")
        arqs = [sp.get("arquivo")] if sp.get("arquivo") else []
        arqs += [it.get("arquivo") if isinstance(it, dict) else it for it in sp.get("itens", [])]
        arqs = [a for a in arqs if a]
        if arqs:
            desc.append("arquivos: " + ", ".join(dict.fromkeys(Path(str(a)).name for a in arqs)))
        return base, itens, tipo, " — ".join(d for d in desc if d)

    todos = sorted(QUADRO + PAINEL + TITULO + ADESIVO, key=lambda e: e.t0)
    for e in todos:
        base, itens, tipo, desc = partes(e)
        regra = {n for n, _ in e.itens_tempos()}   # o resumo() avisa só destes
        g0 = grupo(e.t0 + 0.15)
        primeiros = [x for x in itens if grupo(x[1]) <= g0]
        depois = [x for x in itens if grupo(x[1]) > g0]
        arq_stems = {stem(it.get("arquivo") if isinstance(it, dict) else it) for it in e.spec.get("itens", [])}
        nomes = [n for n, _, _ in primeiros]
        nomes = "" if nomes and set(nomes) <= arq_stems else " · ".join(nomes)   # só o nome do arquivo: já está no desc
        m = {"t0": e.t0, "t1": e.t1, "quadro": cap(max([base] + [p for _, _, p in primeiros]), e.t1),
             "tipo": tipo, "desc": " — ".join(x for x in (desc, nomes) if x) or "—"}
        av = []
        if e.t1 - e.t0 < 1.2:
            av.append(br(f"fica só {e.t1 - e.t0:.2f} s na tela (mín. ~1,2 s)"))
        tarde = [n for n, te, _ in primeiros if n in regra and e.t1 - te < 0.8]
        if tarde:
            av.append(f"{', '.join(tarde)} surge menos de 0,8 s antes de sair: usar palavra anterior ou estender o 'ate'")
        if av:
            m["aviso"] = "; ".join(av)
        ms.append(m)
        for g in sorted({grupo(te) for _, te, _ in depois}):
            xs = [x for x in depois if grupo(x[1]) == g]
            m = {"t0": min(te for _, te, _ in xs), "t1": e.t1, "quadro": cap(max(p for _, _, p in xs), e.t1),
                 "tipo": tipo + " (entra mais)", "desc": " · ".join(n for n, _, _ in xs)}
            tarde = [n for n, te, _ in xs if n in regra and e.t1 - te < 0.8]
            if tarde:
                m["aviso"] = f"{', '.join(tarde)} surge menos de 0,8 s antes de sair: usar palavra anterior ou estender o 'ate'"
            ms.append(m)
    # troca de tela: o quadro/painel/título sai e fica só a pessoa
    grandes = QUADRO + PAINEL + TITULO
    for e in grandes:
        a = e.t1
        if a >= TOTAL - 0.1 or any(x.ativo(a + 0.01) for x in grandes):
            continue
        b = min([x.t0 for x in grandes if x.t0 > a] + [TOTAL])
        if b - a < 0.2 or (CTA and CTA_T0 <= a + 0.3 and CTA_T1 >= b - 0.05):   # o CTA já mostra a pessoa limpa
            continue
        if any(x.ativo(a + 0.05) for x in ADESIVO):   # o recorte já está na frente: o quadro dele mostra a troca
            continue
        ms.append({"t0": a, "t1": b, "quadro": cap(a + 0.3, b), "tipo": "Só a pessoa em tela cheia",
                   "desc": "sai " + ("o quadro" if e in QUADRO else "o painel" if e in PAINEL else "o título") +
                           ", legenda no peito"})
    if CTA:
        ms.append({"t0": CTA_T0, "t1": CTA_T1, "quadro": cap(CTA_TP + 0.35, CTA_T1),
                   "tipo": "CTA: palavra grande em amarelo", "desc": f"{CTA.get('texto', '')} + {CTA['palavra']}".strip()})

    listas = (QUADRO, PAINEL, TITULO, ADESIVO)
    cob = sum(1 for k in range(N_FRAMES) if any(ativo(l, k / FPS) for l in listas)) / max(1, N_FRAMES)
    if not 0.60 <= cob <= 0.70:
        avisos.append(f"elemento na tela em {cob:.0%} do vídeo (referência: 63%; meta 60-70%)")
    limpo, ini = 0.0, 0.0
    for k in range(N_FRAMES + 1):
        t = k / FPS
        if k == N_FRAMES or any(ativo(l, t) for l in listas):
            limpo = max(limpo, t - ini)
            ini = t + 1 / FPS
    if limpo > 6.0:
        avisos.append(br(f"maior trecho só com a pessoa: {limpo:.1f} s (referência: 5,7 s; meta até ~6 s)"))

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

    for lado in ("quadro", "painel", "adesivo"):
        for sp in MAPA.get(lado, []):
            junta(sp.get("arquivo"))
            for it in sp.get("itens", []):
                junta(it)
    if MAPA.get("musica"):
        junta(MAPA["musica"])

    def quadro(t: float) -> Image.Image:
        n = round(t * FPS)
        return compoe(quadro_base(n), t, legendas, n)

    out = SB.gerar(EDIT, "Remy", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ================================================================ main
def resumo() -> None:
    print(f"linha do tempo:  (quadro branco: borda em {PH_QUADRO}px = {PH_QUADRO / H:.0%} da altura, "
          f"cabeça sobe {LAY['sobe']}px por cima)")
    todos = [(e, "quadro") for e in QUADRO] + [(e, "painel") for e in PAINEL] + \
            [(e, "título") for e in TITULO] + [(e, "adesivo") for e in ADESIVO]
    for e, lado in sorted(todos, key=lambda x: x[0].t0):
        extra = " (sai por desfoque da anterior)" if getattr(e, "anterior", None) else ""
        if isinstance(e, Quadro) and e.entra == "surge" and e.anterior is None:
            extra += f" (entra surgindo em {e.dur_entra:.2f}s)"
        if isinstance(e, Quadro):
            extra += f" [quadro {e.ph / H:.0%} da altura]"
        if e.precisa() > 0:
            extra += f" [imagem desce {e.precisa():.0f}px]"
        print(f"  {e.t0:6.2f}-{e.t1:6.2f} ({e.t1 - e.t0:4.1f}s) {lado:7s} {Path(str(e.nome())).name}{extra}")
        for nome, te in e.itens_tempos():
            print(f"           · {te:6.2f} {nome}")
            if e.t1 - te < 0.8:
                print(f"  ATENÇÃO: '{nome}' surge {e.t1 - te:.2f}s antes de sair (mín. ~0,8 s): "
                      f"usar palavra anterior ou estender o 'ate'")
        if e.t1 - e.t0 < 1.2:
            print(f"  ATENÇÃO: {e.nome()} fica só {e.t1 - e.t0:.2f}s na tela (mín. ~1,2 s)")
    if CTA:
        print(f"  {CTA_T0:6.2f}-{CTA_T1:6.2f} cta     {CTA.get('texto', '')} {CTA['palavra']} (palavra em {CTA_TP:.2f})")
    cob = sum(1 for k in range(N_FRAMES) if any(ativo(l, k / FPS) for l in (QUADRO, PAINEL, TITULO, ADESIVO))) \
        / max(1, N_FRAMES)
    print(f"  com elemento na tela: {cob:.0%} do vídeo (referência: 63%)")
    limpo, ini = 0.0, 0.0
    for k in range(N_FRAMES + 1):
        t = k / FPS
        if k == N_FRAMES or any(ativo(l, t) for l in (QUADRO, PAINEL, TITULO, ADESIVO)):
            limpo = max(limpo, t - ini)
            ini = t + 1 / FPS
    print(f"  maior trecho só com a pessoa: {limpo:.1f}s (referência: 5,7 s, com cortes de enquadramento dentro)")


def main() -> None:
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    if janelas_mascara() and not (EDIT / "masks" / "out").exists():
        sys.exit("tem quadro com a cabeça na frente: rode mascaras.py antes")
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
    prenorm = EDIT / f"{modo}_remy.prenorm.mp4"
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
        for e in QUADRO + PAINEL:   # fecha o ffmpeg de quem já saiu
            if t >= e.t1:
                e.fecha()
        k += 1
        if k % 300 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_remy.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
