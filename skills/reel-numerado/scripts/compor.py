"""compor.py — monta o Reel no estilo "numerado" quadro a quadro, a partir do mapa.json.

Estilo tirado do Reel "7 video effects" do @tenfoldmarc (ver referencia/referencias-estilo.md):
selo branco fixo no topo com o item da lista ("#3 Marketing é educação"), um efeito por item que acontece
na palavra que combina com ele, corte seco pra tomada nova a cada item, legenda minúscula numa linha com
duas escalas (palavra-chave sozinha sai maior e amarela), CTA de comentário animado, um whoosh grave
repetido em tudo que se move.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,3.2,9.6   # JPGs de prévia em verify/quadros/
  $PY compor.py <edit_dir> --linha                     # só imprime a linha do tempo e os ATENÇÃO
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo: preview_numerado.mp4 | final_numerado.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json (do cortar.py), base_preview.mov
    (ou base_final.mov), masks/out/f_<quadro>.png (do mascaras.py)

Ordem das camadas: congela (troca o quadro) → zoom (recorta) → luz (antes/depois, holofote) →
coisas atrás da pessoa (prévia, parede, órbita de trás, palavra do antes/depois) → pessoa →
coisas na frente (órbita da frente, rótulos, checklist) → selo → CTA → legenda.
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
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

AQUI = Path(__file__).resolve().parent
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("edit", type=Path)
_ap.add_argument("--so-quadros", default="")
_ap.add_argument("--final", action="store_true")
_ap.add_argument("--linha", action="store_true")
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
DURS = [OFF[g + 1] - OFF[g] for g in range(_NG)]
WORDS = [{"s": a, "e": b, "t": t, "seg": k} for a, b, t, k in json.loads((EDIT / "words_out.json").read_text())]
TOTAL = OFF[-1]
N_FRAMES = round(TOTAL * FPS)


def limpa(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


def acha_seq(texto: str, grupo: int) -> list[int]:
    """Índices das palavras de `texto` (uma ou várias) na tomada. "texto#2" = 2ª ocorrência."""
    k = 1
    if "#" in texto:
        texto, k = texto.rsplit("#", 1)
        k = int(k)
    alvo = [limpa(p) for p in texto.split()]
    idx = [i for i, w in enumerate(WORDS) if w["seg"] == grupo]
    achou = 0
    for j in range(len(idx) - len(alvo) + 1):
        if all(limpa(WORDS[idx[j + q]]["t"]) == alvo[q] for q in range(len(alvo))):
            achou += 1
            if achou == k:
                return idx[j:j + len(alvo)]
    fala = " ".join(WORDS[i]["t"] for i in idx)
    sys.exit(f'"{texto}" não está na tomada {grupo} (ocorrência {k}). Fala da tomada: {fala}')


def T(spec, fim: bool = False) -> float | None:
    """Tempo na SAÍDA. spec = segundos | [palavra, tomada] | [palavra, tomada, atraso]."""
    if spec is None:
        return None
    if isinstance(spec, (int, float)):
        return float(spec)
    seq = acha_seq(spec[0], int(spec[1]))
    d = float(spec[2]) if len(spec) > 2 else 0.0
    return (WORDS[seq[-1]]["e"] if fim else WORDS[seq[0]]["s"]) + d


def tomada_de(t: float) -> int:
    return max(g for g in range(_NG) if OFF[g] <= t + 1e-6)


def fim_tomada_de(t: float) -> float:
    return OFF[tomada_de(t) + 1]


def cl(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def ease_out(x: float) -> float:
    return 1 - (1 - cl(x)) ** 3


def ease_in(x: float) -> float:
    return cl(x) ** 3


def ease_in_out(x: float) -> float:
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def mola(x: float) -> float:
    """back-out: passa um pouco do tamanho final e volta (0 → 1)."""
    x = cl(x)
    return 1 + 2.9 * (x - 1) ** 3 + 1.9 * (x - 1) ** 2


# ---------------------------------------------------------------- cores e fontes
def hexa(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


AMARELO = hexa(MAPA.get("destaque", "#F0E478"))   # medido na referência
BRANCO = (252, 252, 252)
PRETO = (17, 17, 17)
PAINEL = (30, 42, 42)                              # fundo do checklist (#1E2A2A medido)
UI_ESCURO = (18, 18, 18)                           # caixa de comentário (#121212 medido)
SFNS = "/System/Library/Fonts/SFNS.ttf"            # SF Pro: o desenho mais perto da referência


@functools.lru_cache(maxsize=None)
def F(peso: str, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(SFNS, max(6, int(size)))
    f.set_variation_by_name(peso)
    return f


if F("Black", 40).getlength("edited") <= F("Regular", 40).getlength("edited"):
    sys.exit("SF Pro sem pesos variáveis: confira /System/Library/Fonts/SFNS.ttf")


# ---------------------------------------------------------------- utilidades de imagem
def cola(dest: Image.Image, im: Image.Image, x: float, y: float) -> None:
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    w, h = min(im.width - sx, dest.width - dx), min(im.height - sy, dest.height - dy)
    if w > 0 and h > 0:
        dest.alpha_composite(im.crop((sx, sy, sx + w, sy + h)), (dx, dy))


def cola_centro(dest: Image.Image, im: Image.Image, cx: float, cy: float) -> None:
    cola(dest, im, cx - im.width / 2, cy - im.height / 2)


def com_alfa(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def ret_arred(w: int, h: int, r: int, cor) -> Image.Image:
    im = Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), int(r), fill=cor)
    return im


def sombra(im: Image.Image, raio: int = 16, forca: float = 0.45, dy: int = 8) -> Image.Image:
    pad = raio * 2
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad + dy), (0, 0, 0, 0))
    preto = Image.new("RGBA", im.size, (0, 0, 0, 255))
    preto.putalpha(im.getchannel("A").point(lambda v: int(v * forca)))
    out.paste(preto, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(raio))
    out.alpha_composite(im, (pad, pad))
    return out


def arredonda(im: Image.Image, r: int, borda: int = 0, cor_borda=BRANCO) -> Image.Image:
    """Cantos arredondados + borda (cartão de celular)."""
    w, h = im.size
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    if borda:
        fundo = ret_arred(w + 2 * borda, h + 2 * borda, r + borda, cor_borda + (255,))
        fundo.alpha_composite(out, (borda, borda))
        out = fundo
    return out


def quebra(txt: str, f: ImageFont.FreeTypeFont, larg: int) -> list[str]:
    linhas, cur = [], ""
    for p in txt.split():
        teste = (cur + " " + p).strip()
        if f.getlength(teste) <= larg or not cur:
            cur = teste
        else:
            linhas.append(cur)
            cur = p
    if cur:
        linhas.append(cur)
    return linhas


def texto_espacado(d: ImageDraw.ImageDraw, x: float, y: float, txt: str, f, cor, esp: float) -> float:
    for ch in txt:
        d.text((x, y), ch, font=f, fill=cor)
        x += f.getlength(ch) + esp
    return x


# ---------------------------------------------------------------- base e recorte
BASE = EDIT / f"base_{'final' if ARGS.final else 'preview'}.mov"


def quadro_base(n: int) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(BASE), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (W, H), raw).convert("RGBA")


@functools.lru_cache(maxsize=16)
def quadro_cache(n: int) -> Image.Image:
    return quadro_base(n)


@functools.lru_cache(maxsize=8)
def mascara(n: int) -> Image.Image | None:
    p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
    if not p.exists():
        return None
    m = Image.open(p).convert("L")
    if m.size != (W, H):
        m = m.resize((W, H), Image.BILINEAR)
    return m.filter(ImageFilter.GaussianBlur(1.5))


CAB_PADRAO = (540, 720)   # (centro x da cabeça, topo do cabelo) quando não há recorte


@functools.lru_cache(maxsize=None)
def cabeca(n: int) -> tuple[int, int]:
    """Centro x da cabeça e topo do cabelo, medidos no recorte do quadro n."""
    m = mascara(n)
    if m is None:
        print(f"  aviso: sem recorte no quadro {n}, usando cabeça padrão {CAB_PADRAO}")
        return CAB_PADRAO
    a = np.asarray(m) > 128
    linhas = np.where(a.sum(1) > 25)[0]
    if not len(linhas):
        return CAB_PADRAO
    topo = int(linhas[0])
    faixa = a[topo:topo + 220]
    xs = np.where(faixa.sum(0) > 3)[0]
    return int((xs.min() + xs.max()) / 2), topo


def nq(t: float) -> int:
    return min(N_FRAMES - 1, max(0, round(t * FPS)))


def _resolve(arq: str) -> Path:
    p = Path(arq).expanduser()
    return p if p.is_absolute() else (PASTA / p).resolve()


# ================================================================ EFEITOS
class Efeito:
    tem_atras = False

    def __init__(self, spec: dict):
        self.spec = spec
        self.t0 = T(spec.get("em"))
        self.t1 = T(spec["ate"]) if spec.get("ate") is not None else fim_tomada_de(self.t0)
        self.fim = self.t1             # até quando desenha (saída animada pode passar do t1)

    def ativo(self, t: float) -> bool:
        return self.t0 <= t < self.fim

    def janelas(self) -> list[tuple[float, float]]:
        return []

    def quadros(self) -> list[int]:
        return []

    def miniatura_t(self) -> float:
        return min(self.t0 + 0.8, self.fim - 0.05)

    def sons(self) -> list[tuple[float, str, float]]:
        return []

    def quadro(self, fr, m, t, n):
        return fr, m

    def transforma(self, fr, m, t):
        return fr, m

    def luz(self, fr, m, t):
        return fr

    def atras(self, bg, m, t):
        pass

    def frente(self, fr, m, t):
        pass

    def resumo(self) -> str:
        return ""


# ---------------------------------------------------------------- prévia numerada
class Previa(Efeito):
    """Miniaturas numeradas dos itens (quadros do próprio vídeo) surgindo em arco acima da cabeça."""
    tem_atras = True

    def __init__(self, spec):
        super().__init__(spec)
        self.n = int(spec.get("n", 10))
        self.td = T(spec.get("destaque_em"))
        self.passo = float(spec.get("intervalo", 0.07))
        self._cartoes = None

    def janelas(self):
        return [(self.t0, self.fim)]

    def _tempos_itens(self) -> list[float]:
        out = []
        for k in range(1, self.n + 1):
            g = min(k, _NG - 1)
            ef = [e for e in EFEITOS if e is not self and tomada_de(e.t0) == g]
            out.append(ef[0].miniatura_t() if ef else OFF[g] + DURS[g] * 0.5)
        return out

    def quadros(self):
        return [nq(t) for t in self._tempos_itens()]

    def cartoes(self) -> list[Image.Image]:
        if self._cartoes is None:
            cw, ch = 148, 263
            self._cartoes = []
            for k, tk in enumerate(self._tempos_itens(), 1):
                n = nq(tk)
                img = compoe(quadro_cache(n), tk, n, [], leg=False).convert("RGB")
                img = img.resize((cw, ch), Image.LANCZOS)
                c = arredonda(img, 16, 4)
                tela = Image.new("RGBA", (c.width + 16, c.height + 16), (0, 0, 0, 0))
                tela.alpha_composite(c, (16, 16))
                d = ImageDraw.Draw(tela)
                d.ellipse((0, 0, 42, 42), fill=AMARELO + (255,), outline=PRETO + (255,), width=2)
                d.text((21, 22), str(k), font=F("Bold", 24), fill=PRETO + (255,), anchor="mm")
                self._cartoes.append(tela)
        return self._cartoes

    def atras(self, bg, m, t):
        cx, topo = cabeca(nq(self.t0 + 0.05))
        cs = self.cartoes()
        xs = np.linspace(95, W - 95, self.n)
        incl = [-7, 5, -4, 6, -6, 4, -5, 7, -3, 5, -6, 4]
        ordem = list(range(self.n))
        if self.td is not None and t >= self.td:
            ordem = ordem[:-1] + [self.n - 1]
        for i in ordem:
            ti = self.t0 + self.passo * i
            if t < ti:
                continue
            p = (t - ti) / 0.22
            s = mola(p)
            if s <= 0.02:
                continue
            c = cs[i]
            destaque = self.td is not None and i == self.n - 1 and t >= self.td
            if destaque:
                k = ease_out((t - self.td) / 0.25)
                s *= 1 + 0.32 * k
                aro = ret_arred(c.width - 6, c.height - 6, 24, AMARELO + (255,))
                brilho = aro.filter(ImageFilter.GaussianBlur(14))
                tela = Image.new("RGBA", (c.width + 40, c.height + 40), (0, 0, 0, 0))
                tela.alpha_composite(com_alfa(brilho, 0.9 * k), (20, 20))
                tela.alpha_composite(com_alfa(aro, k), (23, 23))
                tela.alpha_composite(c, (20, 20))
                c = tela
            c = c.resize((max(2, int(c.width * s)), max(2, int(c.height * s))), Image.BICUBIC)
            c = sombra(c.rotate(incl[i % len(incl)], expand=True, resample=Image.BICUBIC), 12, 0.4, 6)
            y = topo - 250 - 110 * math.sin(math.pi * i / max(1, self.n - 1))
            cola_centro(bg, com_alfa(c, cl(p * 3)), xs[i], y)

    def sons(self):
        ev = [(self.t0 - 0.05, "whoosh", -27)]
        ev += [(self.t0 + self.passo * i + 0.03, "pop", -31) for i in range(self.n)]
        if self.td is not None:
            ev.append((self.td, "whoosh_curto", -25))
        return ev

    def resumo(self):
        return f"{self.n} miniaturas" + (f", destaque no {self.n} em {self.td:.2f}" if self.td else "")


# ---------------------------------------------------------------- parede de manchetes
PALETAS_CARTAO = [((44, 30, 74), (128, 44, 92)), ((14, 48, 58), (8, 18, 28)), ((70, 24, 24), (20, 10, 12)),
                  ((24, 24, 28), (60, 60, 70)), ((30, 60, 40), (10, 24, 16))]


def gradiente(w: int, h: int, c1, c2) -> Image.Image:
    a = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(c1)[None, None, :] * (1 - a) + np.array(c2)[None, None, :] * a)
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8)).convert("RGBA")


def cartao_manchete(estilo: str, texto: str, k: int, w: int = 300, h: int = 533) -> Image.Image:
    rng = np.random.default_rng(k + 7)
    c1, c2 = PALETAS_CARTAO[k % len(PALETAS_CARTAO)]
    if estilo == "post":
        im = Image.new("RGBA", (w, h), (243, 241, 236, 255))
        d = ImageDraw.Draw(im)
        d.ellipse((22, 26, 70, 74), fill=(201, 195, 184, 255))
        d.rounded_rectangle((84, 34, 200, 46), 6, fill=(60, 60, 60, 255))
        d.rounded_rectangle((84, 56, 160, 66), 5, fill=(170, 170, 170, 255))
        f = F("Bold", 31)
        y = 100
        for ln in quebra(texto, f, w - 44)[:5]:
            d.text((22, y), ln, font=f, fill=PRETO + (255,))
            y += 40
        y += 14
        for larg in (250, 230, 180, 240, 120):
            d.rounded_rectangle((22, y, 22 + larg, y + 12), 6, fill=(200, 198, 192, 255))
            y += 26
        foto = gradiente(w - 44, max(40, h - y - 70), (180, 170, 150), (120, 110, 100))
        foto = foto.filter(ImageFilter.GaussianBlur(3))
        im.alpha_composite(arredonda(foto, 14), (22, y + 8))
        for i in range(4):
            d.ellipse((24 + i * 60, h - 42, 44 + i * 60, h - 22), fill=(150, 150, 150, 255))
    elif estilo == "manchete":
        im = gradiente(w, h, c1, c2)
        ruido = Image.fromarray((rng.random((h // 8, w // 8)) * 90).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        im = Image.composite(Image.new("RGBA", (w, h), (255, 255, 255, 255)), im,
                             ruido.point(lambda v: int(v * 0.35)))
        d = ImageDraw.Draw(im)
        f = F("Black", 33)
        linhas = quebra(texto.upper(), f, w - 70)[:4]
        alt = 44 * len(linhas) + 26
        d.rounded_rectangle((20, 110, w - 20, 110 + alt), 10, fill=(224, 48, 58, 255))
        y = 123
        for ln in linhas:
            d.text((w / 2, y), ln, font=f, fill=BRANCO + (255,), anchor="ma")
            y += 44
        cam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dc = ImageDraw.Draw(cam)
        dc.ellipse((w / 2 - 60, h - 250, w / 2 + 60, h - 130), fill=(255, 255, 255, 50))
        dc.rounded_rectangle((w / 2 - 100, h - 120, w / 2 + 100, h - 20), 50, fill=(255, 255, 255, 40))
        im.alpha_composite(cam.filter(ImageFilter.GaussianBlur(2)))
    else:   # reel
        im = gradiente(w, h, c1, c2)
        d = ImageDraw.Draw(im)
        f = F("Black", 38)
        y = 120
        for ln in quebra(texto, f, w - 50)[:4]:
            d.text((w / 2, y), ln, font=f, fill=BRANCO + (255,), anchor="ma")
            y += 46
        cam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dc = ImageDraw.Draw(cam)
        dc.ellipse((w / 2 - 70, h - 300, w / 2 + 70, h - 160), fill=(255, 255, 255, 40))
        dc.rounded_rectangle((22, h - 24, w - 22, h - 19), 3, fill=(255, 255, 255, 80))
        im.alpha_composite(cam)
        d.ellipse((22, h - 78, 58, h - 42), fill=(220, 220, 220, 255))
        d.text((68, h - 60), "@conteudo.diario", font=F("Semibold", 19), fill=(235, 235, 235, 255), anchor="lm")
        d.rounded_rectangle((22, h - 24, 22 + int((w - 44) * 0.4), h - 19), 3, fill=(255, 255, 255, 255))
    return sombra(arredonda(im, 26, 5), 16, 0.45, 8)


class Parede(Efeito):
    """Prints de conteúdo de outros pendurados na parede atrás da cabeça: despencam e saem voando."""
    tem_atras = True
    POS = [(-330, -430, -7), (-60, -570, 4), (230, -480, -4), (420, -290, 6), (-430, -170, 5), (360, -110, -6)]

    def __init__(self, spec):
        super().__init__(spec)
        self.fim = self.t1 + 0.25
        self.cs = [cartao_manchete(c.get("estilo", "reel"), c["texto"], k) for k, c in enumerate(spec["cartoes"])]

    def janelas(self):
        return [(self.t0, self.fim)]

    def atras(self, bg, m, t):
        cx, topo = cabeca(nq(self.t0 + 0.05))
        for i, c in enumerate(self.cs[:len(self.POS)]):
            dx, dy, ang = self.POS[i]
            ti = self.t0 + 0.05 * i
            if t < ti:
                continue
            y = topo + dy - 1100 * (1 - ease_out((t - ti) / 0.35))
            if t >= self.t1:
                y -= 1400 * ease_in((t - self.t1 - 0.03 * i) / 0.25)
            cola_centro(bg, c.rotate(ang, expand=True, resample=Image.BICUBIC), cx + dx, y)

    def sons(self):
        return [(self.t0 + 0.28, "impacto", -17), (self.t1 - 0.05, "whoosh", -24)]

    def resumo(self):
        return f"{len(self.cs)} cartões, saem em {self.t1:.2f}"


# ---------------------------------------------------------------- órbita
class Orbita(Efeito):
    """Celulares com Reels da pessoa girando em volta do tronco, os de trás menores e desfocados."""
    tem_atras = True
    CW, CH = 200, 356

    def __init__(self, spec):
        super().__init__(spec)
        self.volta = float(spec.get("volta_s", 4.0))
        self.raio = float(spec.get("raio", 400))
        self._quadros = None

    def janelas(self):
        return [(self.t0, self.fim)]

    def miniatura_t(self):
        return min(self.t0 + 1.0, self.fim - 0.05)

    def videos(self) -> list[np.ndarray]:
        if self._quadros is None:
            dur = self.fim - self.t0 + 0.3
            self._quadros = []
            for v in self.spec["videos"]:
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{float(v.get('inicio', 0)):.3f}",
                                      "-i", str(_resolve(v["arquivo"])), "-t", f"{dur:.3f}", "-vf",
                                      f"scale={self.CW}:{self.CH}:force_original_aspect_ratio=increase,"
                                      f"crop={self.CW}:{self.CH},fps={FPS_NUM}/{FPS_DEN}",
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     capture_output=True, check=True).stdout
                arr = np.frombuffer(raw, np.uint8).reshape(-1, self.CH, self.CW, 3)
                self._quadros.append(arr)
        return self._quadros

    def _cartoes(self, t: float):
        cx, topo = cabeca(nq(self.t0 + 0.05))
        cy = topo + float(self.spec.get("altura", 470))
        vs = self.videos()
        K = len(vs)
        out = []
        for k, arr in enumerate(vs):
            th = 2 * math.pi * k / K + 2 * math.pi * (t - self.t0) / self.volta
            z = math.cos(th)
            x = cx + self.raio * math.sin(th)
            y = cy + 70 * z
            s = (0.6 + 0.4 * (z + 1) / 2) * mola((t - self.t0 - 0.05 * k) / 0.3)
            if s < 0.03:
                continue
            esq = 0.35 + 0.65 * abs(z)
            fi = min(len(arr) - 1, int((t - self.t0) * FPS))
            out.append((z, x, y, s, esq, -8 * math.sin(th), arr[fi]))
        return out

    def _desenha(self, dest, c):
        z, x, y, s, esq, rot, px = c
        im = arredonda(Image.fromarray(px), 18, 3)
        im = im.resize((max(2, int(im.width * s * esq)), max(2, int(im.height * s))), Image.BICUBIC)
        im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
        if z < 0:
            im = im.filter(ImageFilter.GaussianBlur(2 + 3 * -z))
            im = com_alfa(im, 0.85)
        else:
            im = sombra(im, 10, 0.4, 6)
        cola_centro(dest, im, x, y)

    def atras(self, bg, m, t):
        for c in sorted(self._cartoes(t), key=lambda c: c[0]):
            if c[0] < 0:
                self._desenha(bg, c)

    def frente(self, fr, m, t):
        for c in sorted(self._cartoes(t), key=lambda c: c[0]):
            if c[0] >= 0:
                self._desenha(fr, c)

    def sons(self):
        return [(self.t0 - 0.05, "whoosh", -23)]

    def resumo(self):
        return f"{len(self.spec['videos'])} vídeos, uma volta a cada {self.volta:.1f}s"


# ---------------------------------------------------------------- zoom digital
class Zoom(Efeito):
    """Aproximação em degraus no rosto (suave ou seca com borrão) e puxão de volta no fim."""
    DUR = {"suave": 0.7, "seco": 0.1}
    DERIVA = 0.07   # aproximação lenta entre os degraus (por segundo)

    def __init__(self, spec):
        self.passos = [(T(p[0]), float(p[1]), p[2] if len(p) > 2 else "seco") for p in spec["passos"]]
        spec = {**spec, "em": self.passos[0][0]}
        super().__init__(spec)
        self.tv = T(spec.get("volta"))
        self.fim = self.tv + 0.16 if self.tv is not None else fim_tomada_de(self.t0)

    def quadros(self):
        return [nq(self.t0)]

    def miniatura_t(self):
        return min(self.passos[-1][0] + 0.3, self.fim - 0.05)

    def _v(self, t: float) -> float:
        v, fim_ant = 1.0, None
        for ti, si, modo in self.passos:
            if fim_ant is not None:
                v += min(0.12, self.DERIVA * max(0.0, min(t, ti) - fim_ant))
            if t < ti:
                return v
            d = self.DUR.get(modo, 0.1)
            x = (t - ti) / d
            v = v + (si - v) * (ease_out(x) if modo == "suave" else ease_in_out(x))
            fim_ant = ti + d
        return v + min(0.12, self.DERIVA * max(0.0, t - fim_ant))

    def escala(self, t: float) -> float:
        if self.tv is not None and t >= self.tv:
            b = self._v(self.tv)
            return b + (1 - b) * ease_in_out((t - self.tv) / 0.16)
        return self._v(t)

    def _caixa(self, v: float) -> tuple:
        cx, topo = cabeca(nq(self.t0))
        cy = topo + 350
        w, h = W / v, H / v
        x0 = cl(cx - w / 2, 0, W - w)
        y0 = cl(cy - h * 0.42, 0, H - h)
        return (x0, y0, x0 + w, y0 + h)

    def transforma(self, fr, m, t):
        v = self.escala(t)
        if abs(v - 1) < 1e-3:
            return fr, m
        va = self.escala(t - 1 / FPS)
        if abs(v - va) > 0.025:
            # borrão de movimento: média de várias escalas entre o quadro anterior e este. Com 5 amostras o
            # salto grande (2x → 1x em 0,16 s) aparecia como cópias do rosto; uma amostra a
            # cada 0,005 de escala + desfoque leve vira rastro contínuo.
            k = int(min(48, max(8, abs(v - va) / 0.005)))
            acc = None
            for q in np.linspace(va, v, k):
                a = np.asarray(fr.resize((W, H), Image.BILINEAR, box=self._caixa(q)), np.float32)
                acc = a if acc is None else acc + a
            out = Image.fromarray((acc / k).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2))
        else:
            out = fr.resize((W, H), Image.BICUBIC, box=self._caixa(v))
        mm = m.resize((W, H), Image.BILINEAR, box=self._caixa(v)) if m is not None else None
        return out, mm

    def sons(self):
        ev = [(ti - 0.08, "whoosh_grave", -22 if modo == "seco" else -28) for ti, _, modo in self.passos]
        if self.tv is not None:
            ev.append((self.tv - 0.06, "whoosh_grave", -21))
        return ev

    def resumo(self):
        p = ", ".join(f"{s:.2f}x {m} em {t:.2f}" for t, s, m in self.passos)
        return p + (f", volta em {self.tv:.2f}" if self.tv else "")


# ---------------------------------------------------------------- holofote
class Holofote(Efeito):
    """A sala apaga na palavra; sobra um cone de luz atrás da cabeça e o rosto iluminado."""

    def __init__(self, spec):
        super().__init__(spec)
        self.tem_fim = spec.get("ate") is not None
        self.fim = self.t1 + (0.25 if self.tem_fim else 0)
        self._mapa = None

    def janelas(self):
        return [(self.t0, self.fim)]

    def miniatura_t(self):
        return min(self.t0 + 0.5, self.fim - 0.05)

    def _luz_fundo(self):
        if self._mapa is None:
            cx, topo = cabeca(nq(self.t0))
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            cone = np.exp(-(((xx - cx) / 270) ** 2 + ((yy - (topo + 60)) / 620) ** 2))
            fundo = 0.09 + 0.78 * cone
            queda = np.clip(1 - (yy - (topo + 430)) / 900, 0.16, 1.0) * 0.96
            self._mapa = (fundo, np.maximum(fundo, queda))
        return self._mapa

    def luz(self, fr, m, t):
        k = ease_out((t - self.t0) / 0.2)
        if self.tem_fim and t >= self.t1:
            k *= 1 - ease_in_out((t - self.t1) / 0.25)
        if k <= 0.001:
            return fr
        fundo, pessoa = self._luz_fundo()
        a = np.asarray(m, np.float32) / 255 if m is not None else 0.0
        L = fundo * (1 - a) + pessoa * a
        L = 1 - k + k * L
        arr = np.asarray(fr.convert("RGB"), np.float32) * L[..., None]
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

    def resumo(self):
        return f"apaga em {self.t0:.2f}, " + (f"acende em {self.t1:.2f}" if self.tem_fim else "escuro até o corte")


# ---------------------------------------------------------------- congela e rotula
class Congela(Efeito):
    """O quadro para, pisca, escurece; rótulos com linha apontam pra pessoa. A voz continua."""

    def __init__(self, spec):
        super().__init__(spec)
        self.n0 = nq(self.t0)
        self.rot = []
        for r in spec.get("rotulos", []):
            self.rot.append({"texto": r["texto"], "te": T(r["em"]), "alvo": r.get("alvo", "peito")})

    def quadros(self):
        return [self.n0]

    def miniatura_t(self):
        return min((self.rot[-1]["te"] + 0.3) if self.rot else self.t0 + 0.3, self.t1 - 0.05)

    def quadro(self, fr, m, t, n):
        fr = quadro_cache(self.n0).copy()
        m = mascara(self.n0)
        x = (t - self.t0) / 0.12
        fr = ImageEnhance.Color(fr).enhance(1 - 0.5 * ease_out(x))
        fr = ImageEnhance.Brightness(fr).enhance(1 - 0.3 * ease_out(x))
        if x < 1:
            fr = Image.blend(fr, Image.new("RGBA", (W, H), (255, 255, 255, 255)), 0.55 * (1 - x))
        return fr, m

    def _pontos(self, r) -> tuple[tuple[float, float], tuple[float, float], bool]:
        cx, topo = cabeca(self.n0)
        if r["alvo"] == "cabeca":
            p = (cx + 25, topo + 55)
            c = (min(W - 190, p[0] + 270), p[1] - 140)
            return p, c, True
        p = (cx - 200, topo + 700)            # ombro: fora da legenda centralizada (y≈1390)
        c = (max(170, p[0] - 130), p[1] - 330)
        return p, c, False

    def _pilula(self, i: int, txt: str) -> Image.Image:
        f = F("Bold", 38)
        tw = f.getlength(txt)
        w, h = int(tw + 96), 66
        im = ret_arred(w, h, 18, BRANCO + (255,))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((12, 15, 54, 51), 8, fill=AMARELO + (255,))
        d.text((33, 33), f"{i:02d}", font=F("Bold", 17), fill=PRETO + (255,), anchor="mm")
        d.text((66, 33), txt, font=f, fill=PRETO + (255,), anchor="lm")
        return sombra(im, 12, 0.35, 5)

    def frente(self, fr, m, t):
        saida = ease_in((t - (self.t1 - 0.14)) / 0.14)
        d = ImageDraw.Draw(fr)
        for i, r in enumerate(self.rot, 1):
            te = r["te"]
            if t < te - 0.12:
                continue
            p, c, direita = self._pontos(r)
            pil = self._pilula(i, r["texto"])
            borda_x = c[0] - pil.width / 2 + 40 if direita else c[0] + pil.width / 2 - 40
            fim_linha = (borda_x, c[1] + 22)
            kl = ease_out((t - (te - 0.05)) / 0.12)
            a_lin = int(255 * (1 - saida))
            if kl > 0:
                q = (p[0] + (fim_linha[0] - p[0]) * kl, p[1] + (fim_linha[1] - p[1]) * kl)
                d.line([p, q], fill=(255, 255, 255, a_lin), width=3)
            s = mola((t - (te - 0.12)) / 0.15)
            r1, r2 = 13 * s, 7 * s
            d.ellipse((p[0] - r1, p[1] - r1, p[0] + r1, p[1] + r1), outline=AMARELO + (a_lin,), width=3)
            d.ellipse((p[0] - r2, p[1] - r2, p[0] + r2, p[1] + r2), fill=AMARELO + (a_lin,))
            kp = (t - (te + 0.03)) / 0.15
            if kp <= 0:
                continue
            im = com_alfa(pil, ease_out(kp) * (1 - saida))
            if kp < 1:
                im = im.filter(ImageFilter.GaussianBlur(6 * (1 - kp)))
            cola_centro(fr, im, c[0] + 140 * saida, c[1])

    def sons(self):
        ev = [(self.t0, "clique", -21), (self.t0, "whoosh_curto", -25), (self.t1 - 0.06, "whoosh_grave", -22)]
        ev += [(r["te"], "pop", -26) for r in self.rot]
        return ev

    def resumo(self):
        return f"{self.t1 - self.t0:.2f}s parado, rótulos: " + ", ".join(f"{r['texto']}@{r['te']:.2f}" for r in self.rot)


# ---------------------------------------------------------------- antes e depois
class AntesDepois(Efeito):
    """Versão apagada ('antes'), depois a barra corre e revela a versão com cor e a palavra atrás da cabeça."""

    def __init__(self, spec):
        super().__init__(spec)
        self.tb = T(spec["barra"])
        self.palavra = spec.get("palavra", "")
        self.segura = float(spec.get("segura", 1.5))
        self._vinheta = None
        self._pal = None

    def janelas(self):
        return [(self.tb - 0.05, self.fim)]

    def miniatura_t(self):
        return min(self.tb + 1.0, self.fim - 0.05)

    def xd(self, t: float) -> float:
        if t < self.tb:
            return W + 80
        x = W + 80 - (W + 80 - 30) * ease_out((t - self.tb) / 0.8)
        ts = self.tb + 0.8 + self.segura
        if t >= ts:
            x = 30 - 140 * ease_in((t - ts) / 0.35)
        return x

    def _depois(self, fr, m):
        if self._vinheta is None:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
            self._vinheta = np.clip(1 - 0.35 * r ** 2, 0.55, 1)[..., None]
        out = ImageEnhance.Contrast(fr).enhance(1.15)
        out = ImageEnhance.Color(out).enhance(1.28)
        arr = np.asarray(out.convert("RGB"), np.float32) * self._vinheta
        arr[..., 2] *= 0.96
        out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        if self.palavra:
            if self._pal is None:
                cx, topo = cabeca(nq(self.tb + 0.1))
                tam = 200
                while F("Black", tam).getlength(self.palavra) > 960 and tam > 80:
                    tam -= 6
                f = F("Black", tam)
                im = Image.new("RGBA", (W, tam * 2), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((W / 2, tam * 1.3), self.palavra, font=f, fill=BRANCO + (255,), anchor="ms")
                self._pal = (sombra(im, 14, 0.5, 8), cx, topo + 95 - tam * 1.3)
            pal, cx, y = self._pal
            bg = out.copy()
            cola(bg, pal, cx - pal.width / 2, y - 28)
            out = Image.composite(out, bg, m) if m is not None else bg
        return out

    @staticmethod
    def _antes(fr):
        out = ImageEnhance.Color(fr).enhance(0.35)
        out = ImageEnhance.Contrast(out).enhance(0.82)
        return ImageEnhance.Brightness(out).enhance(1.05)

    @staticmethod
    def _pil(txt: str, amarela: bool) -> Image.Image:
        f = F("Bold" if amarela else "Semibold", 30)
        w = int(f.getlength(txt) + 44)
        im = ret_arred(w, 52, 26, (AMARELO + (255,)) if amarela else (20, 20, 20, 160))
        ImageDraw.Draw(im).text((w / 2, 27), txt, font=f, fill=(PRETO if amarela else BRANCO) + (255,), anchor="mm")
        return im

    def luz(self, fr, m, t):
        antes = self._antes(fr)
        x = self.xd(t)
        if x >= W:
            out = antes
        else:
            out = self._depois(fr, m)
            if x > 0:
                out.paste(antes.crop((0, 0, int(x), H)), (0, 0))
        y = LEG_Y + 100
        d = ImageDraw.Draw(out)
        if x >= W:
            cola_centro(out, self._pil("antes", False), 830, y)
            return out
        if -40 < x < W:
            d.line([(x, 0), (x, H)], fill=(255, 255, 255, 235), width=4)
            d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=(250, 250, 250, 255))
            for s in (-1, 1):
                d.line([(x + s * 6, y - 9), (x + s * 15, y), (x + s * 6, y + 9)], fill=(40, 40, 40, 255), width=4)
        pa = self._pil("antes", False)
        cola(out, pa, x - 48 - pa.width, y - 26)
        cola(out, self._pil("depois", True), max(x + 48, 24), y - 26)
        return out

    def sons(self):
        ts = self.tb + 0.8 + self.segura
        return [(self.t0, "clique", -27), (self.tb - 0.05, "whoosh", -21), (ts, "whoosh_grave", -24)]

    def resumo(self):
        return f"apagado em {self.t0:.2f}, barra em {self.tb:.2f}, palavra '{self.palavra}'"


# ---------------------------------------------------------------- checklist
class Checklist(Efeito):
    """Painel escuro no canto que entra vazio (esqueleto) e se preenche e marca conforme a pessoa fala."""
    X, Y, LARG = 36, 350, 340

    def __init__(self, spec):
        super().__init__(spec)
        self.itens = []
        for it in spec["itens"]:
            self.itens.append({**it, "te": T(it["em"]), "tok": T(it.get("ok"))})
        oks = [it["tok"] for it in self.itens if it["tok"] is not None]
        self.t_feito = max(oks) if len(oks) == len(self.itens) else None

    def miniatura_t(self):
        return min((self.t_feito + 0.15) if self.t_feito else self.t1 - 0.3, self.fim - 0.05)

    def _linhas(self, txt):
        return quebra(txt, F("Bold", 32), self.LARG - 22 - 34 - 18 - 22)

    def frente(self, fr, m, t):
        x0 = self.X - (self.LARG + 60) * (1 - ease_out((t - self.t0) / 0.3))
        a = cl((t - self.t0) / 0.15)
        cab = quebra("• " + self.spec.get("titulo", "").upper(), F("Semibold", 18), self.LARG - 150)
        alt_itens = [max(2, len(self._linhas(it["texto"]))) * 37 + 30 for it in self.itens]
        h = 24 + 26 * len(cab) + 18 + 24 + sum(alt_itens) + 8
        im = ret_arred(self.LARG, h, 26, PAINEL + (242,))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, self.LARG - 1, h - 1), 26, outline=(255, 255, 255, 28), width=2)
        y = 24
        for ln in cab:
            texto_espacado(d, 22, y, ln, F("Semibold", 18), (150, 165, 165, 255), 1.6)
            y += 26
        feitos = sum(1 for it in self.itens if it["tok"] is not None and t >= it["tok"])
        tudo = self.t_feito is not None and t >= self.t_feito
        cont = f"{feitos} de {len(self.itens)}"
        fc = F("Bold", 18)
        cw = int(fc.getlength(cont) + 24)
        d.rounded_rectangle((self.LARG - 20 - cw, 22, self.LARG - 20, 52), 15,
                            fill=(AMARELO if tudo else (52, 64, 64)) + (255,))
        d.text((self.LARG - 20 - cw / 2, 37), cont, font=fc, fill=(PRETO if tudo else (200, 210, 210)) + (255,),
               anchor="mm")
        y += 18
        n = len(self.itens)
        seg = (self.LARG - 44 - 8 * (n - 1)) / n
        for i, it in enumerate(self.itens):
            sx = 22 + i * (seg + 8)
            d.rounded_rectangle((sx, y, sx + seg, y + 5), 3, fill=(60, 74, 74, 255))
            if it["tok"] is not None and t >= it["tok"]:
                k = ease_out((t - it["tok"]) / 0.2)
                d.rounded_rectangle((sx, y, sx + seg * k, y + 5), 3, fill=AMARELO + (255,))
        y += 24
        for it, ah in zip(self.itens, alt_itens):
            cy = y + 34
            ok = it["tok"] is not None and t >= it["tok"]
            ccx = 22 + 17
            if ok:
                s = mola((t - it["tok"]) / 0.2)
                r = 17 * s
                d.ellipse((ccx - r, cy - r, ccx + r, cy + r), fill=AMARELO + (255,))
                if s > 0.6:
                    d.line([(ccx - 8, cy), (ccx - 2, cy + 6), (ccx + 9, cy - 6)], fill=PRETO + (255,), width=4)
            else:
                d.ellipse((ccx - 17, cy - 17, ccx + 17, cy + 17), outline=(94, 107, 107, 255), width=3)
            tx = 22 + 34 + 18
            if t < it["te"]:
                d.rounded_rectangle((tx, cy - 16, tx + 190, cy - 3), 6, fill=(52, 64, 64, 255))
                d.rounded_rectangle((tx, cy + 10, tx + 120, cy + 23), 6, fill=(52, 64, 64, 255))
            else:
                k = ease_out((t - it["te"]) / 0.15)
                camada = Image.new("RGBA", im.size, (0, 0, 0, 0))
                dc = ImageDraw.Draw(camada)
                yy = cy - 18 + 10 * (1 - k)
                for ln in self._linhas(it["texto"]):
                    xx = tx
                    for p in ln.split():
                        amarelo = limpa(p) in {limpa(q) for q in it.get("destaque", "").split()}
                        dc.text((xx, yy), p, font=F("Bold", 32), fill=(AMARELO if amarelo else BRANCO) + (255,))
                        xx += F("Bold", 32).getlength(p + " ")
                    yy += 37
                im.alpha_composite(com_alfa(camada, k))
            y += ah
        if tudo:
            k = ease_out((t - self.t_feito) / 0.25)
            aro = Image.new("RGBA", (self.LARG + 40, h + 40), (0, 0, 0, 0))
            ImageDraw.Draw(aro).rounded_rectangle((20, 20, self.LARG + 19, h + 19), 26, outline=AMARELO + (255,),
                                                  width=4)
            brilho = aro.filter(ImageFilter.GaussianBlur(10))
            tela = Image.new("RGBA", aro.size, (0, 0, 0, 0))
            tela.alpha_composite(com_alfa(brilho, k))
            tela.alpha_composite(im, (20, 20))
            tela.alpha_composite(com_alfa(aro, k))
            s = 22 * mola((t - self.t_feito) / 0.3)
            if s > 1:
                cxs, cys = self.LARG + 12, 22
                pts = [(cxs, cys - s), (cxs + s * 0.25, cys - s * 0.25), (cxs + s, cys), (cxs + s * 0.25, cys + s * 0.25),
                       (cxs, cys + s), (cxs - s * 0.25, cys + s * 0.25), (cxs - s, cys), (cxs - s * 0.25, cys - s * 0.25)]
                ImageDraw.Draw(tela).polygon(pts, fill=AMARELO + (255,))
            im, dx = tela, -20
        else:
            dx = 0
        cola(fr, sombra(com_alfa(im, a), 18, 0.4, 8), x0 + dx - 36, self.Y + dx - 36)

    def sons(self):
        ev = [(self.t0 - 0.05, "whoosh_grave", -23), (self.t0, "impacto", -24)]
        ev += [(it["tok"], "tique", -23) for it in self.itens if it["tok"] is not None]
        if self.t_feito is not None:
            ev.append((self.t_feito + 0.05, "chime", -24))
        return ev

    def resumo(self):
        return ", ".join(f"{it['texto']} (texto {it['te']:.2f}, ok {it['tok']:.2f})" for it in self.itens)


TIPOS = {"previa": Previa, "parede": Parede, "orbita": Orbita, "zoom": Zoom, "holofote": Holofote,
         "congela": Congela, "antes_depois": AntesDepois, "checklist": Checklist}
EFEITOS: list[Efeito] = [TIPOS[e["tipo"]](e) for e in MAPA.get("efeitos", [])]


# ================================================================ SELO DO TOPO
SELOS = {int(k): v for k, v in MAPA.get("selos", {}).items()}


@functools.lru_cache(maxsize=None)
def selo_img(txt: str) -> Image.Image:
    f = F("Bold", 40)
    w = int(f.getlength(txt) + 52)
    im = ret_arred(w, 83, 16, BRANCO + (255,))
    ImageDraw.Draw(im).text((w / 2, 43), txt, font=f, fill=PRETO + (255,), anchor="mm")
    return sombra(im, 12, 0.25, 4)


def desenha_selo(fr: Image.Image, t: float) -> None:
    if CTA and t >= CTA.t0:
        return
    g = tomada_de(t)
    txt = SELOS.get(g)
    if not txt:
        return
    k = ease_out((t - OFF[g]) / 0.25)
    im = selo_img(txt)
    s = 0.94 + 0.06 * k
    if s < 0.999:
        im = im.resize((int(im.width * s), int(im.height * s)), Image.BICUBIC)
    cola_centro(fr, com_alfa(im, k), W / 2, 234 + 83 / 2 + 2)


# ================================================================ CTA DE COMENTÁRIO
class Cta:
    """Caixa de comentário do Instagram: digita a palavra, posta, e chega a resposta com o link."""

    def __init__(self, spec):
        self.spec = spec
        self.t0 = T(spec["em"])
        self.pal = spec.get("palavra", "QUERO").upper()
        self.t_bar = self.t0 + 0.35
        self.t_foco = self.t0 + 0.9
        self.t_dig = self.t0 + 1.1
        self.t_dig_fim = self.t_dig + 0.07 * len(self.pal)
        self.t_env = self.t_dig_fim + 0.25
        self.t_resp = self.t_env + 0.35
        self.t_link = self.t_env + 0.85
        self._avatar = None

    def avatar(self) -> Image.Image:
        if self._avatar is None:
            fr = quadro_cache(nq(self.t0)).convert("RGB")
            cx, topo = CAB_PADRAO
            m = mascara(nq(self.t0))
            if m is not None:
                cx, topo = cabeca(nq(self.t0))
            cy, r = topo + 350, 190
            rosto = fr.crop((cx - r, cy - r, cx + r, cy + r)).resize((64, 64), Image.LANCZOS)
            mk = Image.new("L", (64, 64), 0)
            ImageDraw.Draw(mk).ellipse((0, 0, 63, 63), fill=255)
            av = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
            ImageDraw.Draw(av).ellipse((0, 0, 71, 71), fill=AMARELO + (255,))
            av.paste(rosto, (4, 4), mk)
            self._avatar = av
        return self._avatar

    def desenha(self, fr: Image.Image, t: float) -> None:
        if t < self.t0:
            return
        k = ease_out((t - self.t0) / 0.35)
        grad = np.zeros((H, W, 4), np.uint8)
        a = np.clip((np.arange(H) - H * 0.5) / (H * 0.5), 0, 1) * 160 * k
        grad[..., 3] = a[:, None].astype(np.uint8)
        fr.alpha_composite(Image.fromarray(grad))
        d = ImageDraw.Draw(fr)
        yb = CTA_Y + 150
        if self.t_bar <= t < self.t_env + 0.12:
            kb = ease_out((t - self.t_bar) / 0.2) * (1 - cl((t - self.t_env) / 0.12))
            bw, bh = 720, 100
            bar = ret_arred(bw, bh, 50, UI_ESCURO + (236,))
            db = ImageDraw.Draw(bar)
            foco = t >= self.t_foco
            db.rounded_rectangle((0, 0, bw - 1, bh - 1), 50, outline=(AMARELO + (255,)) if foco else (255, 255, 255, 40),
                                 width=3 if foco else 2)
            db.ellipse((22, 24, 74, 76), fill=(120, 120, 120, 255))
            db.ellipse((38, 32, 58, 52), fill=(200, 200, 200, 255))
            db.chord((28, 50, 68, 90), 180, 360, fill=(200, 200, 200, 255))
            n = 0 if t < self.t_dig else min(len(self.pal), int((t - self.t_dig) / 0.07) + 1)
            if n:
                db.text((96, 51), self.pal[:n], font=F("Heavy", 46), fill=BRANCO + (255,), anchor="lm")
                xc = 96 + F("Heavy", 46).getlength(self.pal[:n]) + 4
            else:
                db.text((96, 51), "Adicione um comentário...", font=F("Regular", 32), fill=(138, 138, 138, 255),
                        anchor="lm")
                xc = 96
            if foco and int((t - self.t_foco) * 2.2) % 2 == 0:
                db.line([(xc, 30), (xc, 72)], fill=AMARELO + (255,), width=3)
            env = n == len(self.pal) and n > 0
            db.ellipse((bw - 76, 24, bw - 24, 76), fill=(AMARELO + (255,)) if env else (42, 42, 42, 255))
            cc = PRETO if env else (200, 200, 200)
            db.line([(bw - 50, 63), (bw - 50, 37)], fill=cc + (255,), width=4)
            db.line([(bw - 61, 48), (bw - 50, 37), (bw - 39, 48)], fill=cc + (255,), width=4)
            cola_centro(fr, com_alfa(bar, kb), W / 2, yb + 30 * (1 - kb))
        if t >= self.t_env:
            s = mola((t - self.t_env) / 0.25)
            fp, fw = F("Medium", 30), F("Black", 58)
            larg = int(fp.getlength("você") + fw.getlength(self.pal) + 72)
            bolha = ret_arred(larg, 96, 48, BRANCO + (255,))
            dbo = ImageDraw.Draw(bolha)
            dbo.text((30, 50), "você", font=fp, fill=(140, 140, 140, 255), anchor="lm")
            dbo.text((30 + fp.getlength("você ") + 6, 50), self.pal, font=fw, fill=PRETO + (255,), anchor="lm")
            tela = Image.new("RGBA", (larg + 30, 126), (0, 0, 0, 0))
            tela.alpha_composite(bolha, (0, 30))
            dt = ImageDraw.Draw(tela)
            hx, hy = larg - 6, 30
            dt.ellipse((hx - 22, hy - 22, hx + 22, hy + 22), fill=(240, 69, 122, 255))
            dt.ellipse((hx - 10, hy - 8, hx, hy + 2), fill=BRANCO + (255,))
            dt.ellipse((hx, hy - 8, hx + 10, hy + 2), fill=BRANCO + (255,))
            dt.polygon([(hx - 10, hy - 2), (hx + 10, hy - 2), (hx, hy + 10)], fill=BRANCO + (255,))
            tela = tela.resize((max(2, int(tela.width * s)), max(2, int(tela.height * s))), Image.BICUBIC)
            bx = 300
            d.ellipse((bx - 92, CTA_Y - 30, bx - 32, CTA_Y + 30), fill=(150, 150, 150, 255))
            cola(fr, sombra(tela, 12, 0.3, 5), bx - 24 - 24, CTA_Y - 63 * s - 24 - 15 * s)
        if t >= self.t_resp:
            kr = ease_out((t - self.t_resp) / 0.2)
            d.line([(240, CTA_Y + 35), (240, CTA_Y + 163), (262, CTA_Y + 163)], fill=(255, 255, 255, int(150 * kr)), width=3)
            cola_centro(fr, com_alfa(self.avatar(), kr), 298, CTA_Y + 163)
            if t < self.t_link:
                card = ret_arred(150, 74, 30, UI_ESCURO + (240,))
                dc = ImageDraw.Draw(card)
                for i in range(3):
                    b = 0.5 + 0.5 * math.sin((t - self.t_resp) * 9 - i * 0.9)
                    dc.ellipse((36 + i * 30 - 7, 30, 36 + i * 30 + 7, 44), fill=(200, 200, 200, int(120 + 135 * b)))
                cola(fr, com_alfa(card, kr), 350, CTA_Y + 126)
            else:
                kl = mola((t - self.t_link) / 0.3)
                f1, f2 = F("Medium", 38), F("Bold", 32)
                lk = self.spec.get("link", "o link")
                pw = int(f2.getlength(lk) + 96)
                cw = int(max(f1.getlength(self.spec.get("resposta", "Te mandei o link")) + 60, pw + 40))
                card = ret_arred(cw, 196, 30, UI_ESCURO + (240,))
                dc = ImageDraw.Draw(card)
                dc.rounded_rectangle((0, 0, cw - 1, 195), 30, outline=(255, 255, 255, 30), width=2)
                dc.text((30, 52), self.spec.get("resposta", "Te mandei o link"), font=f1, fill=BRANCO + (255,),
                        anchor="lm")
                dc.rounded_rectangle((20, 104, 20 + pw, 170), 33, fill=AMARELO + (255,))
                lx, ly = 52, 137
                dc.rounded_rectangle((lx - 14, ly - 3, lx + 2, ly + 9), 6, outline=PRETO + (255,), width=3)
                dc.rounded_rectangle((lx - 2, ly - 9, lx + 14, ly + 3), 6, outline=PRETO + (255,), width=3)
                dc.text((76, 137), lk, font=f2, fill=PRETO + (255,), anchor="lm")
                card = card.resize((max(2, int(cw * (0.6 + 0.4 * kl))), max(2, int(196 * (0.6 + 0.4 * kl)))),
                                   Image.BICUBIC)
                cola(fr, sombra(com_alfa(card, cl(kl * 2)), 14, 0.35, 6), 350 - 28, CTA_Y + 65 - 28)

    def fim(self) -> float:
        return self.t_link + 0.3

    def sons(self):
        ev = [(self.t_bar, "whoosh_curto", -27)]
        ev += [(self.t_dig + i * 0.07, "tecla", -28) for i in range(len(self.pal))]
        ev += [(self.t_env, "clique", -20), (self.t_env + 0.02, "pop", -24), (self.t_link, "ding", -23)]
        return ev


CTA_Y = MAPA.get("cta", {}).get("y", 1330) if MAPA.get("cta") else 1330   # centro do comentário postado
CTA = Cta(MAPA["cta"]) if MAPA.get("cta") else None


# ================================================================ LEGENDA
LEG = MAPA.get("legenda_cfg", {})
LEG_TAM = LEG.get("tamanho", 64)
LEG_GRANDE = LEG.get("tamanho_grande", 88)
LEG_Y = LEG.get("y", 1390)   # ref. 1167 (61%) cairia na boca de quem é enquadrado mais baixo: abaixo do queixo
LEG_Y_CTA = LEG.get("y_cta", 560)
LEG_MAX = LEG.get("max_palavras", 4)
PONT = ".,:;!?\"“”…"


def palavra_tela(t: str) -> str:
    return t.strip(PONT).lower()


AMARELAS: set[int] = set()
GRANDES: dict[int, list[int]] = {}
for _c in MAPA.get("chave", []):
    _seq = acha_seq(_c[0], int(_c[1]))
    AMARELAS.update(_seq)
    if len(_c) > 2 and _c[2] == "grande":
        GRANDES[_seq[0]] = _seq


def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:
        return []
    dentro = {i for seq in GRANDES.values() for i in seq}
    blocos, i = [], 0
    while i < len(WORDS):
        if i in GRANDES:
            blocos.append({"idx": GRANDES[i], "grande": True})
            i = GRANDES[i][-1] + 1
            continue
        cur, j = [i], i + 1
        while j < len(WORDS) and len(cur) < LEG_MAX and j not in dentro and WORDS[j]["seg"] == WORDS[i]["seg"]:
            if WORDS[j]["s"] - WORDS[j - 1]["e"] >= 0.3 or WORDS[j - 1]["t"].rstrip()[-1] in ".,!?;:":
                break
            if F("Bold", LEG_TAM).getlength(" ".join(palavra_tela(WORDS[k]["t"]) for k in cur + [j])) > 880:
                break
            cur.append(j)
            j += 1
        blocos.append({"idx": cur, "grande": False})
        i = j
    for k, b in enumerate(blocos):
        b["ini"] = WORDS[b["idx"][0]]["s"] - 0.03
        fim = WORDS[b["idx"][-1]]["e"]
        if k + 1 < len(blocos):
            ns = WORDS[blocos[k + 1]["idx"][0]]["s"] - 0.03
            b["fim"] = ns if ns - fim < 0.6 else fim + 0.25
        else:
            b["fim"] = TOTAL
        tam = LEG_GRANDE if b["grande"] else LEG_TAM
        txt = " ".join(palavra_tela(WORDS[q]["t"]) for q in b["idx"])
        while F("Bold", tam).getlength(txt) > 960 and tam > 40:
            tam -= 4
        b["tam"] = tam
    return blocos


@functools.lru_cache(maxsize=512)
def sprite_palavra(txt: str, cor: tuple, tam: int) -> tuple[Image.Image, int]:
    f = F("Bold", tam)
    asc, desc = f.getmetrics()
    pad = 26
    w = int(f.getlength(txt)) + 2 * pad
    h = asc + desc + 2 * pad
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad, pad + asc), txt, font=f, fill=(0, 0, 0, 165), anchor="ls")
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)), (0, 4))
    ImageDraw.Draw(out).text((pad, pad + asc), txt, font=f, fill=cor + (255,), anchor="ls")
    return out, pad + asc


def desenha_legenda(fr: Image.Image, b: dict, t: float, y: float) -> None:
    tam = b["tam"]
    f = F("Bold", tam)
    ws = [(WORDS[k], palavra_tela(WORDS[k]["t"]), b["grande"] or k in AMARELAS) for k in b["idx"]]
    larg = sum(f.getlength(p) for _, p, _ in ws) + f.getlength(" ") * (len(ws) - 1)
    x = (W - larg) / 2
    base_y = y + tam * 0.33
    for w, p, am in ws:
        if t >= w["s"] - 0.05:
            sp, asc = sprite_palavra(p, AMARELO if am else BRANCO, tam)
            k = (t - (w["s"] - 0.05)) / 0.12
            if k < 1:
                sp = com_alfa(sp.filter(ImageFilter.GaussianBlur(6 * (1 - k))), 0.25 + 0.75 * k)
            cola(fr, sp, x - 26, base_y - asc)
        x += f.getlength(p + " ")


# ================================================================ composição de um quadro
def compoe(fr: Image.Image, t: float, n: int, legendas: list[dict], leg: bool = True) -> Image.Image:
    ativos = [e for e in EFEITOS if e.ativo(t)]
    m = mascara(n) if any(e.tem_atras or isinstance(e, (Holofote, AntesDepois)) for e in ativos) else None
    for e in ativos:
        fr, m = e.quadro(fr, m, t, n)
    for e in ativos:
        fr, m = e.transforma(fr, m, t)
    for e in ativos:
        fr = e.luz(fr, m, t)
    atras = [e for e in ativos if e.tem_atras]
    if atras:
        bg = fr.copy()
        for e in atras:
            e.atras(bg, m, t)
        fr = Image.composite(fr, bg, m) if m is not None else bg
    for e in ativos:
        e.frente(fr, m, t)
    desenha_selo(fr, t)
    if CTA:
        CTA.desenha(fr, t)
    if leg:
        b = next((b for b in legendas if b["ini"] <= t < b["fim"]), None)
        if b:
            desenha_legenda(fr, b, t, LEG_Y_CTA if CTA and t >= CTA.t0 else LEG_Y)
    return fr


# ================================================================ linha do tempo
def linha_do_tempo() -> None:
    print(f"{TOTAL:.2f}s, {_NG} tomadas, {N_FRAMES} quadros")
    for g in range(_NG):
        efs = [e for e in EFEITOS if tomada_de(e.t0) == g]
        nome = SELOS.get(g, "(sem selo)")
        print(f"  tomada {g:2d} {OFF[g]:6.2f}-{OFF[g + 1]:6.2f}  {nome}")
        for e in efs:
            print(f"      {type(e).__name__:11s} {e.t0:6.2f}-{e.fim:6.2f}  {e.resumo()}")
            if e.t0 > OFF[g + 1] - 0.6:
                print(f"      ATENÇÃO: começa a {OFF[g + 1] - e.t0:.2f}s do corte")
            if isinstance(e, Checklist) and e.t_feito and e.t_feito > OFF[g + 1] - 0.4:
                print(f"      ATENÇÃO: checklist fecha {OFF[g + 1] - e.t_feito:.2f}s antes do corte")
    if CTA:
        print(f"  CTA em {CTA.t0:.2f}: posta {CTA.t_env:.2f}, link {CTA.t_link:.2f}")
        if CTA.fim() > TOTAL - 0.6:
            print(f"  ATENÇÃO: o link aparece só {TOTAL - CTA.t_link:.2f}s antes do fim (mín. ~0,9 s)")


# ================================================================ STORYBOARD (aprovação antes do render)
def storyboard(legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    global EFEITOS
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    cap = lambda q, t0, t1: max(t0, min(q, t1 - 0.05))
    br = lambda x: f"{x:.2f}".replace(".", ",")
    ms, avisos = [], []

    # arquivos do mapa (vídeos da órbita); vídeo que falta sai da órbita só no storyboard, com aviso
    arqs = []
    for e in EFEITOS:
        if isinstance(e, Orbita):
            for v in e.spec["videos"]:
                if v["arquivo"] not in [a for a, _ in arqs]:
                    arqs.append((v["arquivo"], _resolve(v["arquivo"]).exists()))
            faltam = [v for v in e.spec["videos"] if not _resolve(v["arquivo"]).exists()]
            if faltam:
                avisos.append("órbita sem " + ", ".join(Path(v["arquivo"]).name for v in faltam)
                              + ": arquivo não encontrado (fica fora do storyboard)")
                e.spec = {**e.spec, "videos": [v for v in e.spec["videos"] if v not in faltam]}
    EFEITOS = [e for e in EFEITOS if not (isinstance(e, Orbita) and not e.spec["videos"])]
    if not (EDIT / "masks" / "out").exists() and any(e.tem_atras or isinstance(e, (Holofote, AntesDepois))
                                                    for e in EFEITOS):
        avisos.append("sem masks/out: rode mascaras.py antes (sem recorte, o que é atrás da pessoa sai na frente)")

    # selo do topo: um por tomada (some no CTA); as palavras amarelas pequenas da tomada vão junto
    grandes = {i for seq in GRANDES.values() for i in seq}
    for g in range(_NG):
        fim = min(OFF[g + 1], CTA.t0) if CTA else OFF[g + 1]
        amarelas = [palavra_tela(WORDS[i]["t"]) for i in sorted(AMARELAS - grandes) if WORDS[i]["seg"] == g]
        extra = ("; amarelas na legenda: " + ", ".join(amarelas)) if amarelas else ""
        if SELOS.get(g) and fim > OFF[g]:
            ms.append({"t0": OFF[g], "t1": fim, "quadro": cap(OFF[g] + 0.35, OFF[g], fim), "tipo": "Selo do topo",
                       "desc": f"“{SELOS[g]}”{extra}"})
        elif amarelas:   # tomada sem selo (gancho): marca a 1ª palavra amarela
            ts = WORDS[min(i for i in AMARELAS - grandes if WORDS[i]["seg"] == g)]["s"]
            ms.append({"t0": ts, "t1": OFF[g + 1], "quadro": cap(ts + 0.15, ts, OFF[g + 1]),
                       "tipo": "Legenda com palavra amarela", "desc": extra[2:]})
    # bloco de legenda que é só palavra-chave: sai sozinho, maior e amarelo
    for b in legendas:
        if b["grande"]:
            ms.append({"t0": b["ini"], "t1": b["fim"], "quadro": cap(WORDS[b["idx"][-1]]["s"] + 0.15, b["ini"], b["fim"]),
                       "tipo": "Legenda grande amarela",
                       "desc": " ".join(palavra_tela(WORDS[q]["t"]) for q in b["idx"])})

    for e in EFEITOS:
        g = tomada_de(e.t0)
        perto_corte = (f"começa a {br(OFF[g + 1] - e.t0)} s do corte" if e.t0 > OFF[g + 1] - 0.6 else None)
        novos = []
        if isinstance(e, Previa):
            fim_cartoes = e.t0 + e.passo * (e.n - 1) + 0.3
            novos.append({"t0": e.t0, "t1": e.fim, "quadro": cap(fim_cartoes, e.t0, e.td or e.fim),
                          "tipo": "Prévia numerada dos itens", "desc": f"{e.n} miniaturas em arco acima da cabeça"})
            if e.td is not None:
                novos.append({"t0": e.td, "t1": e.fim, "quadro": cap(e.td + 0.3, e.td, e.fim),
                              "tipo": "Prévia: destaque no último", "desc": f"a miniatura {e.n} cresce com aro amarelo"})
        elif isinstance(e, Parede):
            novos.append({"t0": e.t0, "t1": e.fim, "quadro": cap(e.miniatura_t(), e.t0, e.t1),
                          "tipo": "Parede de manchetes atrás da cabeça",
                          "desc": " · ".join(c["texto"] for c in e.spec["cartoes"][:len(Parede.POS)])})
        elif isinstance(e, Orbita):
            vs = e.spec["videos"]
            novos.append({"t0": e.t0, "t1": e.fim, "quadro": cap(e.miniatura_t(), e.t0, e.fim),
                          "tipo": "Órbita de Reels em 3D",
                          "desc": f"{len(vs)} vídeos: " + ", ".join(Path(v["arquivo"]).name for v in vs)})
        elif isinstance(e, Zoom):
            fins = [p[0] for p in e.passos[1:]] + [e.tv if e.tv is not None else e.fim]
            for (ti, si, modo), tf in zip(e.passos, fins):
                novos.append({"t0": ti, "t1": tf, "quadro": cap(ti + Zoom.DUR.get(modo, 0.1) + 0.05, ti, tf),
                              "tipo": f"Câmera: zoom {'suave' if modo == 'suave' else 'seco'}",
                              "desc": f"aproxima até {si:.2f}x no rosto".replace(".", ",")})
            if e.tv is not None:
                fim_t = fim_tomada_de(e.tv)
                novos.append({"t0": e.tv, "t1": fim_t, "quadro": cap(e.tv + 0.25, e.tv, fim_t),
                              "tipo": "Câmera: puxão de volta", "desc": "volta pro enquadramento normal (com rastro)"})
        elif isinstance(e, Holofote):
            novos.append({"t0": e.t0, "t1": e.fim, "quadro": cap(e.miniatura_t(), e.t0, e.fim),
                          "tipo": "Holofote (a sala apaga)",
                          "desc": "cone de luz atrás da cabeça; " + (f"acende em {br(e.t1)} s" if e.tem_fim
                                                                       else "escuro até o corte")})
        elif isinstance(e, Congela):
            primeiro = min([r["te"] - 0.12 for r in e.rot] + [e.t1])
            novos.append({"t0": e.t0, "t1": e.t1, "quadro": cap(min(e.t0 + 0.2, primeiro - 0.02), e.t0, e.t1),
                          "tipo": "Congela o quadro", "desc": f"para {br(e.t1 - e.t0)} s, pisca e escurece; a voz continua"})
            for i, r in enumerate(e.rot, 1):
                novos.append({"t0": max(e.t0, r["te"] - 0.12), "t1": e.t1, "quadro": cap(r["te"] + 0.2, r["te"], e.t1),
                              "tipo": "Rótulo com linha", "desc": f"{i:02d} {r['texto']} (aponta pro "
                              + ("rosto" if r["alvo"] == "cabeca" else "peito") + ")"})
        elif isinstance(e, AntesDepois):
            novos.append({"t0": e.t0, "t1": e.tb, "quadro": cap(e.t0 + 0.4, e.t0, e.tb),
                          "tipo": "Antes e depois: versão apagada", "desc": "cor lavada com a pílula “antes”"})
            novos.append({"t0": e.tb, "t1": e.fim, "quadro": cap(e.miniatura_t(), e.tb, e.fim),
                          "tipo": "Antes e depois: barra revela",
                          "desc": "barra corre e revela a versão com cor"
                          + (f"; palavra “{e.palavra}” atrás da cabeça" if e.palavra else "")})
        elif isinstance(e, Checklist):
            vazio = min([it["te"] for it in e.itens] + [e.t0 + 0.5]) - 0.02
            novos.append({"t0": e.t0, "t1": e.fim, "quadro": cap(max(e.t0 + 0.32, min(vazio, e.t0 + 0.5)), e.t0, e.fim),
                          "tipo": "Checklist que se preenche", "desc": f"“{e.spec.get('titulo', '')}”: entra vazio"})
            for it in e.itens:
                q = (it["tok"] + 0.3) if it["tok"] is not None else it["te"] + 0.2
                mi = {"t0": it["te"], "t1": e.fim, "quadro": cap(q, it["te"], e.fim), "tipo": "Item do checklist",
                      "desc": it["texto"] + (f" (marca em {br(it['tok'])} s)" if it["tok"] is not None else " (sem marcar)")}
                if it["tok"] is not None and it["tok"] == e.t_feito and e.t_feito > OFF[g + 1] - 0.4:
                    mi["aviso"] = f"checklist fecha {br(OFF[g + 1] - e.t_feito)} s antes do corte"
                novos.append(mi)
        if perto_corte and novos:
            novos[0]["aviso"] = perto_corte
        ms += novos

    if CTA:
        ms.append({"t0": CTA.t0, "t1": TOTAL, "quadro": cap(CTA.t_dig_fim + 0.1, CTA.t0, CTA.t_env),
                   "tipo": "CTA: caixa de comentário", "desc": f"digita “{CTA.pal}”; a legenda sobe"})
        ms.append({"t0": CTA.t_env, "t1": TOTAL, "quadro": cap(CTA.t_env + 0.3, CTA.t_env, CTA.t_link),
                   "tipo": "CTA: comentário postado", "desc": f"“você {CTA.pal}” com coração"})
        m = {"t0": CTA.t_link, "t1": TOTAL, "quadro": cap(CTA.t_link + 0.35, CTA.t_link, TOTAL),
             "tipo": "CTA: resposta com o link",
             "desc": f"“{CTA.spec.get('resposta', 'Te mandei o link')}” + botão “{CTA.spec.get('link', 'o link')}”"}
        if CTA.fim() > TOTAL - 0.6:
            m["aviso"] = f"o link aparece só {br(TOTAL - CTA.t_link)} s antes do fim (mín. ~0,9 s)"
            avisos.append(m["aviso"])
        ms.append(m)

    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]

    def quadro(t: float) -> Image.Image:
        n = nq(t)
        return compoe(quadro_base(n), t, n, legendas)

    out = SB.gerar(EDIT, "Numerado", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ================================================================ áudio: efeitos sintetizados
def _ressoa(ruido: np.ndarray, fc: np.ndarray, rr: float = 0.985) -> np.ndarray:
    out = np.zeros(len(ruido))
    y1 = y2 = 0.0
    for i in range(len(ruido)):
        w = 2 * math.pi * fc[i] / SR
        y = ruido[i] * (1 - rr) + 2 * rr * math.cos(w) * y1 - rr * rr * y2
        out[i], y2, y1 = y, y1, y
    return out


def sfx_whoosh(d=0.4, f0=300, f1=2600, seed=0):
    n = int(d * SR)
    tt = np.arange(n) / SR
    out = _ressoa(np.random.default_rng(seed).standard_normal(n), f0 * (f1 / f0) ** (tt / d))
    out *= np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 2
    return out / (np.abs(out).max() + 1e-9)


def sfx_impacto(d=0.6, seed=1):
    n = int(d * SR)
    tt = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * (48 + 60 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 7)
    clique = np.random.default_rng(seed).standard_normal(n) * np.exp(-tt * 90) * 0.5
    out = corpo + clique
    return out / np.abs(out).max()


def sfx_pop(d=0.09, f0=1100, f1=520):
    n = int(d * SR)
    tt = np.arange(n) / SR
    out = np.sin(2 * np.pi * np.cumsum(f0 + (f1 - f0) * tt / d) / SR) * np.exp(-tt * 45)
    return out / np.abs(out).max()


def sfx_tecla(seed=0):
    n = int(0.035 * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    out = rng.standard_normal(n) * np.exp(-tt * 260) + np.sin(2 * np.pi * rng.uniform(1700, 2600) * tt) * np.exp(-tt * 300) * 0.4
    out = np.convolve(out, np.ones(3) / 3, mode="same")
    return out / np.abs(out).max()


def sfx_tique():
    """clique agudo e curto (8-10 kHz, < 0,1 s), como os tiques do checklist da referência."""
    n = int(0.05 * SR)
    tt = np.arange(n) / SR
    out = np.sin(2 * np.pi * 2900 * tt) * np.exp(-tt * 140) * 0.6
    out += np.random.default_rng(3).standard_normal(n) * np.exp(-tt * 500) * 0.5
    return out / np.abs(out).max()


def sfx_ding(d=0.9, f=1318.5):
    n = int(d * SR)
    tt = np.arange(n) / SR
    out = (np.sin(2 * np.pi * f * tt) + 0.45 * np.sin(2 * np.pi * 2 * f * tt) + 0.2 * np.sin(2 * np.pi * 1.5 * f * tt)) * np.exp(-tt * 5.5)
    out[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return out / np.abs(out).max()


def sfx_chime():
    a, b = sfx_ding(0.8, 1046.5), sfx_ding(0.7, 1568)
    out = np.zeros(int(0.9 * SR))
    out[: len(a)] += a
    out[int(0.09 * SR): int(0.09 * SR) + len(b)] += b * 0.8
    return out / np.abs(out).max()


def sfx_clique():
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    out = np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 120) + np.random.default_rng(9).standard_normal(n) * np.exp(-tt * 400) * 0.6
    return out / np.abs(out).max()


def trilha_sfx() -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    sons = {"whoosh": [sfx_whoosh(0.4, seed=s) for s in (1, 2, 3)],
            "whoosh_grave": [sfx_whoosh(0.22, 180, 900, seed=s) for s in (11, 12, 13)],   # o whoosh repetido da ref.
            "whoosh_curto": [sfx_whoosh(0.22, 600, 4200, seed=s) for s in (6, 7)],
            "impacto": [sfx_impacto(seed=s) for s in (1, 2)],
            "pop": [sfx_pop(), sfx_pop(0.08, 1300, 650), sfx_pop(0.1, 950, 480)],
            "tecla": [sfx_tecla(s) for s in range(6)], "tique": [sfx_tique()],
            "ding": [sfx_ding()], "chime": [sfx_chime()], "clique": [sfx_clique()]}
    giro = {k: itertools.cycle(v) for k, v in sons.items()}
    ev = [s for e in EFEITOS for s in e.sons()] + (CTA.sons() if CTA else [])
    if MAPA.get("sfx") is False:
        ev = []
    for t, tipo, gdb in ev:
        s = next(giro[tipo]) * 10 ** (gdb / 20)
        i = int(max(0, t) * SR)
        pista[i:i + len(s)] += s[: len(pista) - i]
    return pista[: int(TOTAL * SR)]


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
    linha_do_tempo()
    if ARGS.linha:
        return
    if not BASE.exists():
        sys.exit(f"falta {BASE.name}: rode cortar.py base{' --final' if ARGS.final else ''}")
    legendas = monta_legendas()
    modo = "final" if ARGS.final else "preview"

    if ARGS.storyboard:
        storyboard(legendas)
        return

    if ARGS.so_quadros:
        pasta = EDIT / "verify" / "quadros"
        pasta.mkdir(parents=True, exist_ok=True)
        for ts in ARGS.so_quadros.split(","):
            t = float(ts)
            n = nq(t)
            compoe(quadro_base(n), t, n, legendas).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
        print(f"prévias em {pasta}")
        return

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(BASE), "-vn", "-ac", "2", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    voz = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, 2) / 32768
    extra = trilha_sfx()
    n = min(len(voz), len(extra))
    mix = voz[:n] + extra[:n, None]
    wav = EDIT / f"mix_{modo}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())

    for e in EFEITOS:          # prepara antes do laço o que lê outros quadros (prévia) ou outros vídeos (órbita)
        if isinstance(e, Previa):
            e.cartoes()
        if isinstance(e, Orbita):
            e.videos()

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(BASE), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    prenorm = EDIT / f"{modo}_numerado.prenorm.mp4"
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
        k += 1
        if k % 150 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    out = EDIT / f"{modo}_numerado.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
