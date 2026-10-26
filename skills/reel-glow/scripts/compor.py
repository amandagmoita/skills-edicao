"""compor.py — monta o Reel no estilo glow, quadro a quadro, a partir do mapa.json.

Uso (Python do video-use):
  $PY compor.py <edit_dir> --so-quadros 0.5,9.6,...   # JPGs de prévia em verify/quadros/ (rápido)
  $PY compor.py <edit_dir> --storyboard               # storyboard.html pro usuário aprovar ANTES do render
  $PY compor.py <edit_dir> [--final]                   # vídeo completo: preview_glow.mp4 | final_glow.mp4

Lê: mapa.json, edl.json, base_info.json, words_out.json, base_preview.mov (ou base_final.mov),
    masks/out/ (recorte da pessoa, do mascaras.py), assets/*.png (objetos 3D, do gerar_assets.py)

Camadas, de baixo pra cima (legenda SEMPRE por último):
  base (cortes + zoom alternado) → B-roll → objeto do gancho / número gigante atrás da cabeça
  (pessoa recortada na frente) → zoom animado do take → sticker → legenda
  Tela preta substitui o quadro inteiro (a voz continua) e não tem legenda: o texto é a fala.

Estilo (detalhe em estilo.md): Poppins Bold branca com sombra suave, 2-3 palavras inteiras no
peito; chave em 2ª linha, caixa alta, amarelo GLOW (núcleo #FFEC5C + halo #FFC400); um SFX
sintetizado por evento visual, sem música.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import subprocess
import sys
import wave
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402

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
# Cor de destaque vem do perfil do criador (~/.claude/padroes-edicao/perfil.json, campo cor_destaque).
# No padrão (#FFC700) fica o amarelo glow medido do estilo: núcleo #FFEC5C + halo #FFC400.
# Outra cor: ela vira o halo e o núcleo é a mesma cor clareada 45%.
sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402
PERFIL = perfil.carregar()
_DEST = str(PERFIL["cor_destaque"]).strip().lstrip("#").upper()
if _DEST == "FFC700" or len(_DEST) != 6:
    AMARELO = (255, 236, 92)         # núcleo do amarelo glow (#FFEC5C)
    HALO = (255, 196, 0)             # halo do glow (#FFC400)
else:
    HALO = tuple(int(_DEST[i:i + 2], 16) for i in (0, 2, 4))
    AMARELO = tuple(round(c + (255 - c) * 0.45) for c in HALO)
BRANCO = (255, 255, 255)
FONTE = str(AQUI.parent / "assets" / "fonts" / "Poppins-Bold.ttf")
SR = 48000

MAPA = json.loads((EDIT / "mapa.json").read_text())
_INFO = json.loads((EDIT / "base_info.json").read_text())
FPS_NUM, FPS_DEN = _INFO["fps"]
FPS = FPS_NUM / FPS_DEN
_EDL = json.loads((EDIT / "edl.json").read_text())["ranges"]
_ROFF = list(itertools.accumulate([0.0] + _INFO["duracoes"]))
_NG = max(r["grupo"] for r in _EDL) + 1
# OFF[g] = início da tomada g na saída; OFF[g+1] = fim. Uma tomada pode ter virado vários trechos
# (pausa interna cortada), mas tudo no mapa se ancora na tomada.
OFF = [min(_ROFF[i] for i, r in enumerate(_EDL) if r["grupo"] == g) for g in range(_NG)] + [_ROFF[-1]]
DURS = [OFF[g + 1] - OFF[g] for g in range(_NG)]
WORDS = [{"s": a, "e": b, "t": t, "seg": k} for a, b, t, k in json.loads((EDIT / "words_out.json").read_text())]
TOTAL = OFF[-1]
N_FRAMES = round(TOTAL * FPS)


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTE, size)


def limpa(t: str) -> str:
    return t.strip().strip('"“”').rstrip(",.;:!?")


def acha(texto: str, grupo: int) -> int:
    """Índice da 1ª palavra `texto` dentro da tomada `grupo` (sem pontuação, sem caixa)."""
    try:
        return next(i for i, w in enumerate(WORDS) if limpa(w["t"]).lower() == texto.lower() and w["seg"] == grupo)
    except StopIteration:
        falas = " ".join(w["t"] for w in WORDS if w["seg"] == grupo)
        sys.exit(f'mapa.json: palavra "{texto}" não está na tomada {grupo}: "{falas}"')


def t_pal(texto: str, grupo: int) -> float:
    return WORDS[acha(texto, grupo)]["s"]


# ---------------------------------------------------------------- linha do tempo (do mapa.json)
TELAS = []
for tl in MAPA.get("telas", []):
    cenas = tl["cenas"] if len(tl["cenas"]) == len(tl["tomadas"]) else [tl["cenas"][0]] * len(tl["tomadas"])
    TELAS.append({"segs": tl["tomadas"], "cenas": cenas, "push": tl.get("empurrao", True),
                  "amarelo": [[a.lower() for a in x] for x in tl.get("amarelo", [[]] * len(tl["tomadas"]))],
                  "ini": OFF[tl["tomadas"][0]], "fim": float(tl.get("ate", OFF[tl["tomadas"][-1] + 1]))})
# "ate" (segundos da SAÍDA, opcional): a tela fica até aqui mesmo depois da última tomada acabar
# (a fonte ainda mostra a tela branca); o texto da última tomada fica parado.

BROLLS = [{"segs": b["tomadas"], "arq": b["arquivo"], "src": float(b.get("inicio", 0.0)),
           "crop": tuple(b["recorte"]) if b.get("recorte") else None,
           "ini": OFF[b["tomadas"][0]], "fim": OFF[b["tomadas"][-1] + 1]} for b in MAPA.get("brolls", [])]

# Zoom animado nos takes de fala: {tomada: [escala inicial, escala final]}, âncora no rosto.
ZOOMS = {int(k): tuple(v) for k, v in MAPA.get("zooms", {}).items()}
ANCORA = tuple(MAPA.get("ancora_rosto", [540, 900]))

# Efeitos da biblioteca /reel-efeitos (opcional, só liga com a chave no mapa):
# "efeitos": [{"nome": "orbit", "tomada": 4, "palavra": "x" (opcional), "dur": 1.2 (opcional), ...parâmetros}]
# ou com "ini"/"fim" em segundos da saída. Sem "palavra" começa na tomada; sem "dur" vai até o fim dela.
FX_BANCO = None
if MAPA.get("efeitos"):
    sys.path.insert(0, str(Path.home() / ".claude/skills/reel-efeitos/scripts"))
    import efeitos as FX  # noqa: E402

    def _janela_fx(e: dict) -> dict:
        if "ini" in e:
            return e
        g = e["tomada"]
        ini = t_pal(e["palavra"], g) - 0.1 if e.get("palavra") else OFF[g]
        return {**e, "ini": ini, "fim": ini + e["dur"] if "dur" in e else OFF[g + 1]}

    FX_BANCO = FX.Banco([_janela_fx(e) for e in MAPA["efeitos"]], FPS, PASTA, cor=AMARELO, halo=HALO,
                        ancora=ANCORA if "ancora_rosto" in MAPA else None)


def zoom_quadro(fr: Image.Image, t: float) -> Image.Image:
    k = max(i for i in range(len(DURS)) if OFF[i] <= t)
    if k not in ZOOMS:
        return fr
    s0, s1 = ZOOMS[k]
    sc = s0 + (s1 - s0) * ease_in_out((t - OFF[k]) / DURS[k])
    if abs(sc - 1) < 0.002:
        return fr
    nw, nh = int(W * sc), int(H * sc)
    big = fr.resize((nw, nh), Image.BICUBIC)
    x0 = int(min(max(ANCORA[0] * sc - ANCORA[0], 0), nw - W))
    y0 = int(min(max(ANCORA[1] * sc - ANCORA[1], 0), nh - H))
    return big.crop((x0, y0, x0 + W, y0 + H))


def vf_broll(b: dict) -> str:
    crop = b["crop"]
    return (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else "") + \
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS_NUM}/{FPS_DEN}"


def _aproxima(fr: Image.Image, b: dict, t: float) -> Image.Image:
    """Leve aproximação contínua no B-roll (1,00 → 1,06)."""
    sc = 1 + 0.06 * ease_in_out((t - b["ini"]) / (b["fim"] - b["ini"]))
    nw, nh = int(W * sc), int(H * sc)
    return fr.resize((nw, nh), Image.BICUBIC).crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))


class LeitorBroll:
    """Um ffmpeg por trecho de B-roll, aberto quando o trecho começa."""

    def __init__(self):
        self.ativo, self.proc, self.ultimo = None, None, None

    def quadro(self, t: float) -> Image.Image | None:
        b = next((b for b in BROLLS if b["ini"] <= t < b["fim"]), None)
        if b is None:
            return None
        if b is not self.ativo:
            if self.proc:
                self.proc.kill()
            self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{b['src']:.3f}", "-i", str(PASTA / b["arq"]),
                                          "-vf", vf_broll(b), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                         stdout=subprocess.PIPE)
            self.ativo, self.ultimo = b, None
        buf = self.proc.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.ultimo = Image.frombytes("RGB", (W, H), buf).convert("RGBA")
        return _aproxima(self.ultimo, b, t) if self.ultimo is not None else None


def broll_still(t: float) -> Image.Image | None:
    b = next((b for b in BROLLS if b["ini"] <= t < b["fim"]), None)
    if b is None:
        return None
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{b['src'] + t - b['ini']:.3f}", "-i", str(PASTA / b["arq"]),
                          "-frames:v", "1", "-vf", vf_broll(b), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return _aproxima(Image.frombytes("RGB", (W, H), raw).convert("RGBA"), b, t)


NUMERO = None
if MAPA.get("numero"):
    _n = MAPA["numero"]
    NUMERO = {"texto": _n["texto"], "ini": t_pal(_n["palavra"], _n["tomada"]) - 0.12, "fim": OFF[_n["tomada"] + 1] - 0.08}

GANCHO = None
if MAPA.get("gancho"):
    GANCHO = {"obj": MAPA["gancho"]["objeto"], "ini": 0.25, "pousa": 0.95, "fim": 2.95, "x": 650, "y": 400, "alt": 560}
    GANCHO.update({k: v for k, v in MAPA["gancho"].items() if k in ("ini", "pousa", "fim", "x", "y", "alt")})

STICKER = None
if MAPA.get("sticker"):
    _s = MAPA["sticker"]
    _t = t_pal(_s["palavra"], _s["tomada"])
    STICKER = {"obj": _s["objeto"], "ini": _t - 0.1, "fim": _t + _s.get("dura", 1.8) - 0.1, "y": _s.get("y", 300),
               "x": _s.get("x", W // 2)}

# Chaves: [1ª palavra da chave, tomada, nº de palavras da chave, nº de palavras antes na 1ª linha]
CHAVES = [tuple(c) for c in MAPA.get("chaves", [])]
LETRA_A_LETRA = acha(*MAPA["letra_a_letra"]) if MAPA.get("letra_a_letra") else None
FECHO = acha(*MAPA["fecho"]) if MAPA.get("fecho") else None


def _faixa(centro: float) -> Image.Image:
    """Faixa escura suave atrás da legenda (perfil exp⁴, meia-altura ~230 px, 70%)."""
    y = np.arange(H, dtype=np.float32)
    perfil = np.exp(-(((y - centro) / 230) ** 4)) * 0.7 * 255
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.putalpha(Image.fromarray(np.repeat(perfil[:, None], W, 1).astype(np.uint8)))
    return im


FAIXA = _faixa(1265)

# Presença: no B-roll e nas telas pretas a pessoa continua na tela, recortada no canto de baixo à
# direita (padrão do estilo). "rosto" = onde o ponto
# `ancora_rosto` da base vai parar; o resto do corpo sai pela borda de baixo.
# mapa.json "presenca": false desliga; um dict sobrescreve qualquer valor abaixo.
PRESENCA = None if MAPA.get("presenca") is False else {
    "broll": {"escala": 0.6, "rosto": [790, 1310], "leg_y": 1540},
    "tela": {"escala": 0.5, "rosto": [800, 1650], "cena_escala": 0.75},
}
if PRESENCA and isinstance(MAPA.get("presenca"), dict):
    for _k, _v in MAPA["presenca"].items():
        PRESENCA[_k].update(_v)
FAIXA_PRES = _faixa(PRESENCA["broll"]["leg_y"] + 50) if PRESENCA else None

# mapa.json "legenda_y": [[t0, t1, y], ...] em segundos da SAÍDA. Muda a altura da legenda nesse
# trecho (fonte que já veio editada com a pessoa pequena no canto: legenda vai pro peito dela).
# Fundo claro na área ganha a mesma faixa escura do B-roll.
LEG_TRECHOS = [tuple(x) for x in MAPA.get("legenda_y", [])]
_FAIXAS_Y: dict = {}


def leg_y_trecho(fr: Image.Image, t: float) -> int | None:
    y = next((int(c) for a, b, c in LEG_TRECHOS if a <= t < b), None)
    if y is not None and np.asarray(fr.crop((0, y - 160, W, y + 240)).convert("L")).mean() > 120:
        if y not in _FAIXAS_Y:
            _FAIXAS_Y[y] = _faixa(y + 50)
        fr.alpha_composite(_FAIXAS_Y[y])
    return y


def em_tela_preta(t: float) -> bool:
    return any(tl["ini"] <= t < tl["fim"] for tl in TELAS)


# ---------------------------------------------------------------- legendas
def monta_legendas() -> list[dict]:
    if MAPA.get("legenda") is False:   # fonte já veio com legenda gravada: não desenha outra
        return []
    chave_em: dict[int, tuple[int, int]] = {}
    quebra = set()
    for txt, perto, nk, npre in CHAVES:
        i = acha(txt, perto)
        chave_em[i - npre] = (npre, nk)
        quebra.update({i - npre, i + nk})
    if FECHO is not None:
        quebra.add(FECHO)

    blocos: list[dict] = []
    i = 0
    vis = [k for k, w in enumerate(WORDS) if not em_tela_preta(w["s"])]
    vis_set = set(vis)
    while i < len(WORDS):
        if i not in vis_set:
            i += 1
            continue
        if i in chave_em:
            npre, nk = chave_em[i]
            blocos.append({"pre": list(range(i, i + npre)), "chave": list(range(i + npre, i + npre + nk))})
            i += npre + nk
            continue
        if i == FECHO:
            blocos.append({"pre": [], "chave": [], "fecho": list(range(i, len(WORDS)))})
            break
        cur = [i]
        j = i + 1
        while j < len(WORDS) and j in vis_set and j not in quebra and len(cur) < 3:
            gap = WORDS[j]["s"] - WORDS[j - 1]["e"]
            if gap >= 0.3 or WORDS[j - 1]["t"].rstrip()[-1] in ".,!?;:":
                break
            cur.append(j)
            j += 1
        blocos.append({"pre": cur, "chave": []})
        i = j

    for k, b in enumerate(blocos):
        idx = b["pre"] + b["chave"] + b.get("fecho", [])
        b["ini"] = WORDS[idx[0]]["s"]
        fim = WORDS[idx[-1]]["e"]
        nxt = blocos[k + 1] if k + 1 < len(blocos) else None
        if nxt:
            ns = WORDS[(nxt["pre"] + nxt["chave"] + nxt.get("fecho", []))[0]]["s"]
            b["fim"] = ns if ns - fim < 0.6 else fim + 0.25
        else:
            b["fim"] = TOTAL
        b["fim"] = min(b["fim"], next((tl["ini"] for tl in TELAS if b["ini"] < tl["ini"]), TOTAL))
        b["t_chave"] = WORDS[b["chave"][0]]["s"] if b["chave"] else None
    return blocos


def sombra_texto(img_size, desenha) -> Image.Image:
    """Desenha texto com sombra preta suave (sem contorno), como na referência."""
    camada = Image.new("RGBA", img_size, (0, 0, 0, 0))
    sombra = Image.new("L", img_size, 0)
    desenha(ImageDraw.Draw(sombra), None)
    sombra = sombra.filter(ImageFilter.GaussianBlur(7))
    preto = Image.new("RGBA", img_size, (0, 0, 0, 0))
    preto.putalpha(sombra.point(lambda v: int(v * 0.75)))
    camada.alpha_composite(preto, (0, 3))
    desenha(ImageDraw.Draw(camada), True)
    return camada


def glow(camada: Image.Image, forte: float = 1.0) -> Image.Image:
    """Amarelo glow: halo largo + halo curto saturados por baixo do texto/traço amarelo."""
    a = camada.getchannel("A")
    out = Image.new("RGBA", camada.size, (0, 0, 0, 0))
    for raio, alfa in ((22, 0.55), (8, 0.85)):
        h = a.filter(ImageFilter.GaussianBlur(raio)).point(lambda v, k=alfa * forte: min(255, int(v * k * 1.6)))
        cor = Image.new("RGBA", camada.size, HALO + (0,))
        cor.putalpha(h)
        out.alpha_composite(cor)
    out.alpha_composite(camada)
    return out


def texto_linha(txt: str, size: int, cor, max_w: int = 980) -> Image.Image:
    while True:
        f = font(size)
        bb = f.getbbox(txt)
        if bb[2] - bb[0] <= max_w or size <= 30:
            break
        size -= 4
    w, h = bb[2] - bb[0] + 40, bb[3] + 40

    pad = 30 if cor == AMARELO else 0       # espaço pro halo não ser cortado
    w, h = w + 2 * pad, h + 2 * pad

    def d(dr, real):
        dr.text((20 + pad - bb[0], 16 + pad), txt, font=f, fill=(cor + (255,)) if real else 255)
    if cor != AMARELO:
        return sombra_texto((w, h), d)
    nucleo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d(ImageDraw.Draw(nucleo), True)
    return glow(nucleo)


LEG_Y = 1215           # centro da 1ª linha (peito)
LEG_SIZE, CHAVE_SIZE = 60, 104
cache_txt: dict = {}


def img_txt(txt, size, cor):
    k = (txt, size, cor)
    if k not in cache_txt:
        cache_txt[k] = texto_linha(txt, size, cor)
    return cache_txt[k]


def desenha_legenda(fr: Image.Image, b: dict, t: float, leg_y: int = LEG_Y) -> None:
    if b.get("fecho"):
        txt = " ".join(limpa(WORDS[i]["t"]) for i in b["fecho"])
        im = img_txt(txt, 80, AMARELO)
        fr.alpha_composite(im, (W // 2 - im.width // 2, leg_y - im.height // 2))
        return
    if b["pre"]:
        txt = " ".join(limpa(WORDS[i]["t"]) for i in b["pre"]) if b["chave"] else \
            " ".join(WORDS[i]["t"].strip().strip('"“”') for i in b["pre"]).rstrip(",.;:")
        im = img_txt(txt, LEG_SIZE, BRANCO)
        y = leg_y - im.height // 2
        fr.alpha_composite(im, (W // 2 - im.width // 2, y))
    if b["chave"] and t >= b["t_chave"]:
        txt = " ".join(limpa(WORDS[i]["t"]) for i in b["chave"]).upper()
        im = img_txt(txt, CHAVE_SIZE, AMARELO)
        dt = t - b["t_chave"]
        if b["chave"][0] == LETRA_A_LETRA:
            im = letra_a_letra(txt, dt)
        else:
            s = 0.82 + 0.18 * ease_out(dt / 0.14)
            if s < 0.999:
                im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        y0 = (leg_y + 34 if b["pre"] else leg_y - 40) - 30   # -30: margem do halo
        fr.alpha_composite(im, (W // 2 - im.width // 2, y0 + (img_txt(txt, CHAVE_SIZE, AMARELO).height - im.height) // 2))


def letra_a_letra(txt: str, dt: float) -> Image.Image:
    """Como o SALESMAN da referência: letras aparecem fora de ordem até completar a palavra."""
    ordem = list(range(len(txt)))
    random.Random(7).shuffle(ordem)
    n = int(len(txt) * ease_out(dt / 0.4)) + (1 if dt > 0 else 0)
    vis = set(ordem[:n])
    mascarado = "".join(c if k in vis else " " for k, c in enumerate(txt))
    base = img_txt(txt, CHAVE_SIZE, AMARELO)
    f = font(CHAVE_SIZE)
    bb = f.getbbox(txt)
    w, h = base.size

    def d(dr, real):
        x = 50 - bb[0]
        for k, c in enumerate(txt):
            if k in vis:
                dr.text((x, 46), c, font=f, fill=(AMARELO + (255,)) if real else 255)
            x += f.getlength(c)
    if not mascarado.strip():
        return Image.new("RGBA", (w, h))
    nucleo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d(ImageDraw.Draw(nucleo), True)
    return glow(nucleo)


# ---------------------------------------------------------------- objetos e máscara
ASSETS = {p.stem: Image.open(p).convert("RGBA") for p in sorted((EDIT / "assets").glob("*.png"))}


def obj(nome: str, alt: int, giro: float = 0.0, escala: float = 1.0) -> Image.Image:
    if nome not in ASSETS:
        sys.exit(f'objeto "{nome}" não existe em assets/ (rode gerar_assets.py)')
    im = ASSETS[nome]
    h = max(2, int(alt * escala))
    w = max(2, int(im.width * h / im.height))
    im = im.resize((w, h), Image.LANCZOS)
    return im.rotate(giro, resample=Image.BICUBIC, expand=True) if abs(giro) > 0.1 else im


def mascara(n: int) -> Image.Image | None:
    p = EDIT / "masks" / "out" / f"f_{n:06d}.png"
    if not p.exists():
        return None
    m = Image.open(p).convert("L").resize((W, H), Image.BILINEAR)
    return m.filter(ImageFilter.GaussianBlur(1.5))


def pessoa_na_frente(fr: Image.Image, fundo_alterado: Image.Image, n: int) -> Image.Image:
    m = mascara(n)
    if m is None:
        return fundo_alterado
    return Image.composite(fr, fundo_alterado, m)


def cola_cortado(dest: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """alpha_composite que aceita imagem saindo pelas bordas."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dest.width, x + im.width), min(dest.height, y + im.height)
    if x1 > x0 and y1 > y0:
        dest.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def presenca(dest: Image.Image, fr: Image.Image, n: int, cfg: dict, dt: float) -> None:
    """Ela recortada (máscara do quadro n da base) no canto de baixo à direita, com sombra suave
    pra separar de fundo branco; entra subindo de baixo nos primeiros 0,3 s do bloco."""
    m = mascara(n)
    if m is None:
        return
    s = cfg["escala"]
    w, h = int(W * s), int(H * s)
    ms = m.resize((w, h), Image.BILINEAR)
    # braço que encosta na borda do quadro original viraria um corte reto: borda some em 70 px
    rampa = np.clip(np.minimum(np.arange(w), np.arange(w)[::-1]) / 70, 0, 1)
    ms = Image.fromarray((np.asarray(ms, np.float32) * rampa[None, :]).astype(np.uint8))
    pessoa = fr.resize((w, h), Image.LANCZOS)
    pessoa.putalpha(ms)
    sombra = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sombra.putalpha(ms.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.45)))
    x = int(cfg["rosto"][0] - s * ANCORA[0])
    y = int(cfg["rosto"][1] - s * ANCORA[1] + 420 * (1 - ease_out(dt / 0.3)))
    cola_cortado(dest, sombra, x, y + 10)
    cola_cortado(dest, pessoa, x, y)


def numero_listrado(txt: str) -> Image.Image:
    f = font(760)
    bb = f.getbbox(txt)
    w, h = bb[2] - bb[0] + 80, bb[3] - bb[1] + 80
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((40 - bb[0], 40 - bb[1]), txt, font=f, fill=255)
    listras = np.zeros((h, w), np.uint8)
    for y in range(h):
        listras[y, :] = 255 if (y % 14) < 10 else 70      # persiana horizontal
    a = np.asarray(m).astype(np.float32) * listras / 255.0
    brilho = Image.fromarray(np.asarray(m)).filter(ImageFilter.GaussianBlur(18))
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    alpha = np.clip(a * 0.95 + np.asarray(brilho, np.float32) * 0.25, 0, 255).astype(np.uint8)
    img.putalpha(Image.fromarray(alpha))
    return img


NUM_IMG = numero_listrado(NUMERO["texto"]) if NUMERO else None


# ---------------------------------------------------------------- tela preta
rng = np.random.default_rng(3)
GRAOS = [Image.fromarray(rng.integers(0, 22, (H // 2, W // 2), dtype=np.uint8)).resize((W, H)) for _ in range(6)]


_yy, _xx = np.mgrid[0:H, 0:W]
LUZ = np.clip(46 - 40 * np.sqrt(((_xx - W / 2) / (W * 0.75)) ** 2 + ((_yy - H * 0.45) / (H * 0.6)) ** 2), 8, 46)


def fundo_preto(n: int) -> Image.Image:
    g = np.asarray(GRAOS[n % len(GRAOS)], np.float32) - 11
    v = np.clip(LUZ + g * 0.6, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([v, v, v + 1]), "RGB").convert("RGBA")


def texto_tela(tl: dict, k: int, t: float) -> Image.Image:
    """A fala do trecho surgindo palavra por palavra no terço de cima (layout fixo)."""
    seg = tl["segs"][k]
    ws = [w for w in WORDS if w["seg"] == seg]
    amarelo = set(tl["amarelo"][k])
    f = font(66)
    linhas, cur, larg = [], [], 0
    for w in ws:
        tw = f.getlength(w["t"].strip().strip('"“”') + " ")
        if cur and larg + tw > 900:
            linhas.append(cur); cur, larg = [], 0
        cur.append(w); larg += tw
    if cur:
        linhas.append(cur)
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    am = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = 300 - (len(linhas) - 1) * 45
    for ln in linhas:
        txts = [w["t"].strip().strip('"“”') for w in ln]
        total = sum(f.getlength(x + " ") for x in txts) - f.getlength(" ")
        x = W / 2 - total / 2
        for w, s_ in zip(ln, txts):
            if t >= w["s"] - 0.02:
                destino = am if limpa(w["t"]).lower() in amarelo else p
                ImageDraw.Draw(destino).text((x, y), s_, font=f, fill=(AMARELO if destino is am else BRANCO) + (255,))
            x += f.getlength(s_ + " ")
        y += 92
    if am.getbbox():
        p.alpha_composite(glow(am, 0.9))
    return p


def pop(dt: float, dur: float = 0.2) -> float:
    """Escala de entrada com leve passada (0 → 1,15 → 1)."""
    if dt <= 0:
        return 0.0
    return ease_out(dt / dur) * (1 + 0.15 * math.sin(min(dt / (dur * 1.6), 1) * math.pi))


def cola(dest: Image.Image, im: Image.Image, cx: float, cy: float, esc: float = 1.0, alfa: float = 1.0) -> None:
    if esc <= 0.02 or alfa <= 0.01:
        return
    if abs(esc - 1) > 0.01:
        im = im.resize((max(2, int(im.width * esc)), max(2, int(im.height * esc))), Image.LANCZOS)
    if alfa < 0.999:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alfa)))
    dest.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


_cache_cena: dict = {}


def mini_reel(w: int, h: int, brilho: float) -> Image.Image:
    """Cartão de Reel genérico: play + duas linhas de legenda."""
    k = ("reel", w, h, round(brilho, 2))
    if k not in _cache_cena:
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        b = int(40 + 70 * brilho)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(6, w // 10), fill=(b, b, b + 5, 255),
                            outline=(95 + int(80 * brilho),) * 3 + (255,), width=max(2, w // 70))
        cx, cy, r = w / 2, h * 0.42, w * 0.15
        d.polygon([(cx - r * 0.6, cy - r), (cx - r * 0.6, cy + r), (cx + r, cy)], fill=(235, 235, 235, 220))
        for i, fw in enumerate((0.7, 0.48)):
            y0 = h * 0.70 + i * h * 0.08
            d.rounded_rectangle((w * 0.15, y0, w * (0.15 + fw), y0 + h * 0.035), radius=4, fill=(160, 160, 166, 220))
        _cache_cena[k] = im
    return _cache_cena[k]


def cartao(w: int, h: int, brilho: float) -> Image.Image:
    """Cartão escuro vazio (fundo dos ícones do raio-X com `icones`)."""
    k = ("cartao", w, h, round(brilho, 2))
    if k not in _cache_cena:
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        b = int(30 + 40 * brilho)
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=(b, b, b + 5, 255),
                                             outline=(80 + int(80 * brilho),) * 3 + (255,), width=4)
        _cache_cena[k] = im
    return _cache_cena[k]


def chip(txt: str) -> Image.Image:
    k = ("chip", txt)
    if k not in _cache_cena:
        f = font(40)
        tw = int(f.getlength(txt))
        im = Image.new("RGBA", (tw + 64, 74), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, tw + 63, 73), radius=37, fill=(18, 18, 20, 235), outline=AMARELO + (255,), width=4)
        d.text((32, 12), txt, font=f, fill=AMARELO + (255,))
        _cache_cena[k] = im
    return _cache_cena[k]


def cena_raiox(t: float, c: dict, g: int) -> Image.Image:
    """Raio-X: grade de mini-Reels (uma coluna por palavra); a lupa varre as colunas e cada uma
    acende em glow com a etiqueta quando a palavra é falada.
    c = {"tipo": "raiox", "palavras": [...], "rotulos": [...], "objeto": "lupa",
         "icones": [...] (opcional: em vez dos mini-Reels, 1 cartão por coluna com esse objeto 3D)}"""
    t0 = OFF[g]
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    icones = c.get("icones")
    cw, ch, gap = (290, 420, 36) if icones else (230, 360, 48)
    nc = len(c["palavras"])
    xs = [W / 2 + (i - (nc - 1) / 2) * (cw + gap) for i in range(nc)]
    ys = [1120] if icones else [880, 1290]
    marcos = [t_pal(w, g) for w in c["palavras"]]
    rotulos = c["rotulos"]
    if t < marcos[0]:
        cf = -0.7 + 0.7 * ease_out((t - t0) / max(0.05, marcos[0] - t0))
    else:
        cf = float(nc - 1)
        for i in range(nc - 1):
            if t < marcos[i + 1]:
                cf = i + ease_in_out((t - marcos[i]) / 0.35)
                break
    for ci, x in enumerate(xs):
        ativo = t >= marcos[ci]
        perto = max(0.0, 1 - abs(cf - ci))
        for ri, y in enumerate(ys):
            ap = ease_out((t - t0 - 0.07 * (ci * 2 + ri)) / 0.3)
            br = min(1.0, 0.7 * perto + (0.3 if ativo else 0.0))
            if icones:   # cartão escuro com o objeto: apagado até a palavra, depois pulsa uma vez
                cola(p, cartao(cw, ch, round(br * 10) / 10), x, y, 0.85 + 0.15 * ap, ap)
                dt = t - marcos[ci]
                pul = 1 + 0.12 * math.sin(min(dt / 0.4, 1) * math.pi) if ativo else 1.0
                o = obj(icones[ci], int(230 * pul), (6 * math.sin(dt * 9) * math.exp(-dt * 3)) if ativo else 0)
                cola(p, o, x, y, 0.85 + 0.15 * ap, ap * (1.0 if ativo else 0.45 + 0.3 * perto))
            else:
                cola(p, mini_reel(cw, ch, round(br * 10) / 10), x, y, 0.85 + 0.15 * ap, ap)
            if ativo:
                a = ease_out((t - marcos[ci]) / 0.2)
                ImageDraw.Draw(hl).rounded_rectangle((x - cw / 2 - 8, y - ch / 2 - 8, x + cw / 2 + 8, y + ch / 2 + 8),
                                                     radius=30, outline=AMARELO + (int(255 * a),), width=7)
        if ativo:
            cola(hl, chip(rotulos[ci]), x, ys[0] - ch / 2 - 75, pop(t - marcos[ci]))
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.8))
    lx = W / 2 + (cf - (nc - 1) / 2) * (cw + gap)
    ly = sum(ys) / len(ys) + 20 * math.sin((t - t0) * 3)
    o = obj(c.get("objeto", "lupa"), 470, -8 + 6 * math.sin((t - t0) * 2.5))
    p.alpha_composite(o, (int(lx - o.width * 0.36), int(ly - o.height * 0.36)))   # lente sobre a coluna
    return p


def bezier(p0, p1, p2, u):
    return ((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u ** 2 * p2[0],
            (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u ** 2 * p2[1])


def seta(d: ImageDraw.ImageDraw, pts: list, cor, larg: int) -> None:
    d.line(pts, fill=cor, width=larg, joint="curve")
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    L = larg * 3.2
    d.polygon([(x2 + math.cos(ang) * L * 0.6, y2 + math.sin(ang) * L * 0.6),
               (x2 + math.cos(ang + 2.5) * L, y2 + math.sin(ang + 2.5) * L),
               (x2 + math.cos(ang - 2.5) * L, y2 + math.sin(ang - 2.5) * L)], fill=cor)


def cena_barras(t: float, c: dict, g: int) -> Image.Image:
    """Barras: 5 barras sobem, a de destaque fica na média e DISPARA em glow na palavra `dispara`,
    com seta de tendência; o objeto aparece no topo dela na palavra `entra_objeto`.
    c = {"tipo": "barras", "dispara": "atenção", "entra_objeto": "nicho", "objeto": "vestido"}"""
    t0 = OFF[g]
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, dh = ImageDraw.Draw(p), ImageDraw.Draw(hl)
    base_y, bw, gap, n, Hmax, dest = 1660, 140, 42, 5, 800, 3
    x0 = W / 2 - (n * bw + (n - 1) * gap) / 2
    alturas = [0.30, 0.46, 0.36, 1.0, 0.50]
    tm, ta = t_pal(c["entra_objeto"], g), t_pal(c["dispara"], g)
    d.line((x0 - 30, base_y + 3, x0 + n * bw + (n - 1) * gap + 30, base_y + 3), fill=(95, 95, 100, 255), width=4)
    topo = []
    for i in range(n):
        u = ease_out((t - t0 - 0.06 * i) / 0.55)
        if i == dest:   # a barra de destaque sobe até a média e dispara na palavra de `dispara`
            u = 0.42 * u + 0.58 * ease_out((t - ta) / 0.5)
        h = Hmax * alturas[i] * u
        x = x0 + i * (bw + gap)
        topo.append((x + bw / 2, base_y - h))
        if h > 2:
            (dh if i == dest else d).rounded_rectangle((x, base_y - h, x + bw, base_y), radius=18,
                                                       fill=(AMARELO if i == dest else (72, 72, 78)) + (255,))
    if t >= ta:
        u = ease_in_out((t - ta) / 0.55)
        a0, a2 = (x0 - 10, base_y - 140), (topo[dest][0] - bw * 0.9, base_y - Hmax - 30)
        a1 = (x0 + 220, base_y - 160)
        pts = [bezier(a0, a1, a2, u * k / 24) for k in range(25)]
        if u > 0.02:
            seta(dh, pts, BRANCO + (255,), 9)
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.9))
    if t >= tm - 0.05:
        o = obj(c["objeto"], 360, 4 * math.sin((t - tm) * 2.2))
        cola(p, o, topo[dest][0], topo[dest][1] - 190, pop(t - tm + 0.05, 0.25))
    return p


def ativacao_no(no: dict) -> float:
    return t_pal(no["palavra"], no["tomada"]) if no.get("palavra") else OFF[no["tomada"]] + 0.08


def cena_fluxo(t: float, c: dict, g: int) -> Image.Image:
    """Fluxo de etapas (cobre várias tomadas): cada nó acende na sua palavra (ou no começo da sua
    tomada), uma linha corre até ele quando a tomada dele começa e, opcionalmente, uma curva de
    crescimento se desenha embaixo na palavra da `curva`.
    c = {"tipo": "fluxo", "nos": [{"objeto", "rotulo", "palavra"|null, "tomada"}...],
         "curva": {"palavra", "tomada"}|null}"""
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, dh = ImageDraw.Draw(p), ImageDraw.Draw(hl)
    nos = c["nos"]
    nn = len(nos)
    passo = 1035 / nn
    xs, y = [W / 2 + (i - (nn - 1) / 2) * passo for i in range(nn)], 900
    r = 140 if nn <= 3 else 0.4 * passo
    icones, rot = [n_["objeto"] for n_ in nos], [n_["rotulo"] for n_ in nos]
    t0 = OFF[nos[0]["tomada"]]
    ativ = [ativacao_no(n_) for n_ in nos]
    ligar = [OFF[n_["tomada"]] - 0.12 for n_ in nos[1:]]
    for i in range(nn - 1):   # trilho cinza + linha amarela que corre na hora da passagem
        aa = ease_out((t - t0 - 0.2) / 0.4)
        if aa > 0:
            d.line((xs[i] + r + 10, y, xs[i + 1] - r - 10, y), fill=(70, 70, 76, int(255 * aa)), width=6)
        if t >= ligar[i]:
            u = ease_in_out((t - ligar[i]) / 0.35)
            xa = xs[i] + r + 10
            dh.line((xa, y, xa + (xs[i + 1] - r - 10 - xa) * u, y), fill=AMARELO + (255,), width=9)
    f = font(40)
    for i in range(nn):
        ap = ease_out((t - t0 - 0.12 * i) / 0.35)
        if ap <= 0:
            continue
        ativo = t >= ativ[i]
        dt = t - ativ[i]
        pul = 1 + 0.12 * math.sin(min(dt / 0.4, 1) * math.pi) if ativo else 1.0
        rr = r * (0.8 + 0.2 * ap) * pul
        if ativo and icones[i] == "lampada":   # lâmpada acende: brilho atrás
            bril = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bril).ellipse((xs[i] - 170, y - 170, xs[i] + 170, y + 170),
                                         fill=AMARELO + (int(120 * (0.6 + 0.4 * math.exp(-dt * 2))),))
            p.alpha_composite(bril.filter(ImageFilter.GaussianBlur(40)))
        d.ellipse((xs[i] - rr, y - rr, xs[i] + rr, y + rr), fill=(28, 28, 32, int(255 * ap)),
                  outline=(85, 85, 92, int(255 * ap)), width=6)
        if ativo:
            dh.ellipse((xs[i] - rr - 4, y - rr - 4, xs[i] + rr + 4, y + rr + 4), outline=AMARELO + (255,), width=9)
        o = obj(icones[i], int(175 * pul), (6 * math.sin(dt * 9) * math.exp(-dt * 3)) if ativo else 0)
        cola(p, o, xs[i], y, ap, ap if ativo else 0.55 * ap)
        tw = f.getlength(rot[i])
        (dh if ativo else d).text((xs[i] - tw / 2, y + r + 34), rot[i], font=f,
                                  fill=(AMARELO + (255,)) if ativo else (150, 150, 156, int(255 * ap)))
    tv = t_pal(c["curva"]["palavra"], c["curva"]["tomada"]) if c.get("curva") else 1e9
    if t >= tv - 0.15:   # curva de crescimento
        X0, X1, Yb, Ht = 150, 930, 1740, 500
        aa = ease_out((t - tv + 0.15) / 0.3)
        d.line((X0, Yb - Ht - 20, X0, Yb, X1 + 20, Yb), fill=(80, 80, 86, int(255 * aa)), width=5)
        u = ease_in_out((t - tv) / 0.9)
        kk = 3.2
        pts = [(X0 + (X1 - X0) * x, Yb - Ht * (math.exp(kk * x) - 1) / (math.exp(kk) - 1))
               for x in np.linspace(0, max(u, 0.001), 40)]
        if u > 0.02:
            seta(dh, pts, AMARELO + (255,), 10)
            for j, lim in enumerate((0.35, 0.62, 0.86)):
                if u >= lim:
                    x = lim
                    cx, cy = X0 + (X1 - X0) * x, Yb - Ht * (math.exp(kk * x) - 1) / (math.exp(kk) - 1)
                    cola(p, mini_reel(80, 128, 0.6), cx - 60, cy - 72, pop((u - lim) * 0.9 / 1.0 * 1.0 + 0.0001, 0.2))
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.9))
    return p


def cena_objeto(t: float, c: dict, g: int) -> Image.Image:
    """Objeto 3D sozinho subindo de baixo e flutuando (a tela preta mais simples).
    c = {"tipo": "objeto", "objeto": "ampulheta"}"""
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dt = t - OFF[g]
    sobe = ease_out(dt / 0.55)
    o = obj(c["objeto"], c.get("altura", 760), (1 - sobe) * -18 + 3 * math.sin(dt * 1.6))
    cy = H * 0.66 + (1 - sobe) * 900 + 12 * math.sin(dt * 2.1)
    p.alpha_composite(o, (int(W / 2 - o.width / 2), int(cy - o.height / 2)))
    return p


def tracejado(d: ImageDraw.ImageDraw, box: tuple, cor, larg: int = 5, traco: int = 18, vao: int = 12) -> None:
    x0, y0, x1, y1 = box
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        comp = math.hypot(b[0] - a[0], b[1] - a[1])
        for s0 in range(0, int(comp), traco + vao):
            u0, u1 = s0 / comp, min(s0 + traco, comp) / comp
            d.line((a[0] + (b[0] - a[0]) * u0, a[1] + (b[1] - a[1]) * u0,
                    a[0] + (b[0] - a[0]) * u1, a[1] + (b[1] - a[1]) * u1), fill=cor, width=larg)


def cena_memorial(t: float, c: dict, g: int) -> Image.Image:
    """Documento que a IA escreve sozinha (cobre várias tomadas): o cartão sobe 0,5 s antes da palavra
    `preenche` e as linhas se preenchem na palavra `preenche`; na palavra de `falta` as linhas listadas somem e
    viram buraco tracejado com etiqueta FALTOU; em cada `inventa` a linha treme e ganha INVENTADO.
    `pedido` (opcional) = balão de chat que digita o pedido na palavra dada, acima do cartão.
    c = {"tipo": "memorial", "titulo": "...", "linhas": [rótulos], "preenche": [palavra, tomada],
         "pedido": {"palavra", "tomada", "texto"}|null,
         "falta": {"palavra", "tomada", "linhas": [i...]}, "inventa": [{"palavra", "tomada", "linha"}...]}"""
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, dh = ImageDraw.Draw(p), ImageDraw.Draw(hl)
    tp = t_pal(*c["preenche"])
    ped = c.get("pedido")
    if ped:   # balão de chat digitando o pedido antes do documento
        tpd = t_pal(ped["palavra"], ped["tomada"])
        if t >= tpd - 0.05:
            fb = font(46)
            txt = ped["texto"]
            n = int(len(txt) * min(1.0, max(0.0, (t - tpd) / 0.9)))
            ab = ease_out((t - tpd + 0.05) / 0.2)
            bw = fb.getlength(txt) + 110
            bx0, by0 = W / 2 - bw / 2, 560
            d.rounded_rectangle((bx0, by0, bx0 + bw, by0 + 104), radius=52, fill=(44, 44, 50, int(255 * ab)),
                                outline=(110, 110, 118, int(255 * ab)), width=3)
            vis = txt[:n] + ("|" if n < len(txt) and int(t * 6) % 2 == 0 else "")
            d.text((bx0 + 55, by0 + 24), vis, font=fb, fill=(240, 240, 245, int(255 * ab)))
    ap = ease_out((t - tp + 0.5) / 0.45)
    if ap <= 0:
        return p
    dy = (1 - ap) * 90
    X0, X1, Y0, Y1 = 120, 960, (720 if ped else 560) + dy, 1760 + dy
    d.rounded_rectangle((X0, Y0, X1, Y1), radius=34, fill=(30, 30, 34, int(240 * ap)),
                        outline=(90, 90, 98, int(255 * ap)), width=4)
    ft = font(44)
    if t >= tp - 0.1:   # título do documento
        a = ease_out((t - tp + 0.1) / 0.3)
        tw = ft.getlength(c["titulo"])
        d.text((W / 2 - tw / 2, Y0 + 50), c["titulo"], font=ft, fill=(235, 235, 240, int(255 * a)))
        d.line((X0 + 60, Y0 + 130, X0 + 60 + (X1 - X0 - 120) * a, Y0 + 130), fill=(80, 80, 88, 255), width=3)
    linhas = c["linhas"]
    fl = font(36)
    tf = t_pal(c["falta"]["palavra"], c["falta"]["tomada"]) if c.get("falta") else 1e9
    faltam = {i: tf + 0.18 * k for k, i in enumerate(c.get("falta", {}).get("linhas", []))}
    inventa = {v["linha"]: t_pal(v["palavra"], v["tomada"]) for v in c.get("inventa", [])}
    passo = (Y1 - Y0 - 200) / len(linhas)
    VX0, VX1 = X0 + 375, X1 - 50
    for i, rot in enumerate(linhas):
        y = Y0 + 175 + i * passo + passo / 2
        ti = tp + 0.15 + 0.16 * i
        if t < ti - 0.05:
            continue
        a = ease_out((t - ti + 0.05) / 0.2)
        d.text((X0 + 60, y - 24), rot, font=fl, fill=(170, 170, 178, int(255 * a)))
        cresce = ease_out((t - ti) / 0.3)
        larg_v = (VX1 - VX0) * (0.62 + 0.3 * ((i * 37) % 10) / 10)
        bx = (VX0, y - 15, VX0 + larg_v * cresce, y + 15)
        if i in faltam and t >= faltam[i]:
            dt = t - faltam[i]
            some = 1 - ease_out(dt / 0.25)
            if some > 0.01:
                d.rounded_rectangle(bx, radius=15, fill=(105, 105, 112, int(255 * some)))
            if dt > 0.15:
                tracejado(dh, (VX0 - 6, y - 34, VX1, y + 34), AMARELO + (int(255 * ease_out((dt - 0.15) / 0.2)),), 5)
                cola(hl, chip("FALTOU"), VX1 - 110, y - 2, pop(dt - 0.15))
        elif i in inventa and t >= inventa[i]:
            dt = t - inventa[i]
            if dt < 0.45:   # tremida de glitch: fatias deslocadas
                rnd = random.Random(int(t * 24) * 7 + i)
                for fat in range(3):
                    off = rnd.uniform(-38, 38)
                    yy = y - 15 + fat * 10
                    d.rectangle((VX0 + off, yy, VX0 + larg_v + off, yy + 10), fill=(150, 150, 158, 255))
            else:
                d.rounded_rectangle(bx, radius=15, fill=(70, 64, 30, 255))
                dh.rounded_rectangle((bx[0] - 6, y - 21, bx[2] + 6, y + 21), radius=20, outline=AMARELO + (255,), width=5)
                cola(hl, chip("INVENTADO"), VX1 - 150, y - 2, pop(dt - 0.45))
        elif cresce > 0.01:
            d.rounded_rectangle(bx, radius=15, fill=(105, 105, 112, 255))
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.9))
    return p


def _pos_ramos(c: dict) -> tuple:
    ns = len(c["saidas"])
    passo = 340 if ns <= 3 else 1000 / ns
    return (W / 2, 760), (W / 2, 1110), [(W / 2 + (i - (ns - 1) / 2) * passo, 1530) for i in range(ns)]


def cena_ramos(t: float, c: dict, g: int) -> Image.Image:
    """Um vira vários: a origem (no alto) liga no centro, e o centro se abre em N saídas embaixo.
    Cada nó acende na sua palavra (ou no começo da sua tomada) e a linha até ele corre nos 0,35 s
    antes. Ilustra "faz uma vez, a IA transforma em tudo".
    c = {"tipo": "ramos", "origem": {objeto, rotulo, palavra|null, tomada}, "centro": {...},
         "saidas": [{...}, ...]}"""
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, dh = ImageDraw.Draw(p), ImageDraw.Draw(hl)
    po, pm, ps = _pos_ramos(c)
    ro, rm, rs = 120, 135, 105
    nos = [(c["origem"], po, ro, "dir"), (c["centro"], pm, rm, "dir")] + [(s, q, rs, "baixo") for s, q in zip(c["saidas"], ps)]
    t0 = OFF[c["origem"]["tomada"]]
    ativ = [ativacao_no(n_) for n_, *_ in nos]
    # ligações: origem→centro reta; centro→cada saída em curva que abre pro lado e desce
    lig = [([pm[0], po[1] + ro + 10], [pm[0], pm[1] - rm - 10], None, ativ[1])]
    for (q, ta) in zip(ps, ativ[2:]):
        a0, a2 = (pm[0], pm[1] + rm + 10), (q[0], q[1] - rs - 10)
        lig.append((a0, a2, (q[0], a0[1] + 40) if abs(q[0] - pm[0]) > 1 else None, ta))
    aa = ease_out((t - t0 - 0.2) / 0.4)
    for a0, a2, a1, ta in lig:
        pts = [bezier(a0, a1, a2, k / 24) for k in range(25)] if a1 else [tuple(a0), tuple(a2)]
        if aa > 0:
            d.line(pts, fill=(70, 70, 76, int(255 * aa)), width=6, joint="curve")
        if t >= ta - 0.35:
            u = ease_in_out((t - ta + 0.35) / 0.35)
            if u > 0.02:
                parc = [bezier(a0, a1, a2, u * k / 24) for k in range(25)] if a1 else \
                    [tuple(a0), (a0[0] + (a2[0] - a0[0]) * u, a0[1] + (a2[1] - a0[1]) * u)]
                dh.line(parc, fill=AMARELO + (255,), width=9, joint="curve")
    f = font(40)
    for i, ((n_, (x, y), r, lado), ta) in enumerate(zip(nos, ativ)):
        ap = ease_out((t - t0 - 0.1 * i) / 0.35)
        if ap <= 0:
            continue
        ativo, dt = t >= ta, t - ta
        pul = 1 + 0.12 * math.sin(min(dt / 0.4, 1) * math.pi) if ativo else 1.0
        rr = r * (0.8 + 0.2 * ap) * pul
        if ativo and i == 1:   # o centro (a IA) acende: brilho atrás
            bril = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bril).ellipse((x - 190, y - 190, x + 190, y + 190),
                                         fill=AMARELO + (int(110 * (0.6 + 0.4 * math.exp(-dt * 2))),))
            p.alpha_composite(bril.filter(ImageFilter.GaussianBlur(45)))
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(28, 28, 32, int(255 * ap)),
                  outline=(85, 85, 92, int(255 * ap)), width=6)
        if ativo:
            dh.ellipse((x - rr - 4, y - rr - 4, x + rr + 4, y + rr + 4), outline=AMARELO + (255,), width=9)
        o = obj(n_["objeto"], int(r * 1.3 * pul), (6 * math.sin(dt * 9) * math.exp(-dt * 3)) if ativo else 0)
        cola(p, o, x, y, ap, ap if ativo else 0.5 * ap)
        tw = f.getlength(n_["rotulo"])
        tx, ty = (x + r + 34, y - 30) if lado == "dir" else (x - tw / 2, y + r + 30)
        (dh if ativo else d).text((tx, ty), n_["rotulo"], font=f,
                                  fill=(AMARELO + (255,)) if ativo else (150, 150, 156, int(255 * ap)))
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.9))
    return p


# ---------------------------------------------------------------- gráficos acima da cabeça
# mapa.json "graficos": [{"tipo": "topo", "tomada": g, "nos": [{"objeto", "rotulo", "palavra"}...],
#                         "y": 270, "raio": 88, "passo": 300}]
# No take de fala (sem tela preta): uma fileira de nós no espaço livre ACIMA da cabeça, atrás do
# cabelo (recorte da pessoa na frente). Os nós entram apagados no começo da tomada, a linha corre
# 0,35 s antes da palavra de cada nó e ele acende nela; tudo some nos últimos 0,3 s da tomada.
GRAFICOS = [g_ for g_ in MAPA.get("graficos", []) if g_.get("tipo", "topo") == "topo"]


def grafico_topo(t: float, c: dict) -> Image.Image:
    g = c["tomada"]
    t0, t1 = OFF[g], OFF[g + 1]
    p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, dh = ImageDraw.Draw(p), ImageDraw.Draw(hl)
    nos = c["nos"]
    nn = len(nos)
    y, r, passo = c.get("y", 270), c.get("raio", 88), c.get("passo", 300)
    xs = [W / 2 + (i - (nn - 1) / 2) * passo for i in range(nn)]
    ativ = [t_pal(n_["palavra"], g) for n_ in nos]
    for i in range(nn - 1):   # trilho claro + linha amarela que corre até o próximo nó
        aa = ease_out((t - t0 - 0.15) / 0.4)
        x0, x1 = xs[i] + r + 8, xs[i + 1] - r - 8
        if aa > 0:
            d.line((x0, y, x1, y), fill=(255, 255, 255, int(120 * aa)), width=5)
        tl = ativ[i + 1] - 0.35
        if t >= tl:
            u = ease_in_out((t - tl) / 0.35)
            dh.line((x0, y, x0 + (x1 - x0) * u, y), fill=AMARELO + (255,), width=8)
    f = font(34)
    for i, n_ in enumerate(nos):
        ap = ease_out((t - t0 - 0.1 * i) / 0.35)
        if ap <= 0:
            continue
        ativo = t >= ativ[i]
        dt = t - ativ[i]
        pul = 1 + 0.14 * math.sin(min(dt / 0.4, 1) * math.pi) if ativo else 1.0
        rr = r * (0.8 + 0.2 * ap) * pul
        d.ellipse((xs[i] - rr, y - rr, xs[i] + rr, y + rr), fill=(22, 22, 26, int(215 * ap)),
                  outline=(130, 130, 138, int(255 * ap)), width=5)
        if ativo:
            dh.ellipse((xs[i] - rr - 4, y - rr - 4, xs[i] + rr + 4, y + rr + 4), outline=AMARELO + (255,), width=8)
        o = obj(n_["objeto"], int(118 * pul), (6 * math.sin(dt * 9) * math.exp(-dt * 3)) if ativo else 0)
        cola(p, o, xs[i], y, ap, ap if ativo else 0.5 * ap)
        if ativo:
            cola(hl, chip(n_["rotulo"]), xs[i], y + r + 52, 0.8 * pop(dt))
        else:   # rótulo apagado numa pílula escura (parede clara atrás)
            tw = f.getlength(n_["rotulo"])
            d.rounded_rectangle((xs[i] - tw / 2 - 22, y + r + 28, xs[i] + tw / 2 + 22, y + r + 78), radius=25,
                                fill=(18, 18, 20, int(170 * ap)))
            d.text((xs[i] - tw / 2, y + r + 33), n_["rotulo"], font=f, fill=(190, 190, 196, int(255 * ap)))
    if hl.getbbox():
        p.alpha_composite(glow(hl, 0.8))
    sai = ease_out((t1 - t) / 0.3)
    if sai < 0.999:
        p.putalpha(p.getchannel("A").point(lambda v: int(v * sai)))
    return p


CENAS = {"raiox": cena_raiox, "barras": cena_barras, "fluxo": cena_fluxo, "objeto": cena_objeto,
         "memorial": cena_memorial, "ramos": cena_ramos}


def painel_tela(tl: dict, k: int, t: float) -> Image.Image:
    p = texto_tela(tl, k, t)
    c = tl["cenas"][k]
    cena = CENAS[c["tipo"]](t, c, tl["segs"][k])
    s = PRESENCA["tela"]["cena_escala"] if PRESENCA else 1.0
    if s < 0.999:   # com a pessoa no canto, a cena encolhe em direção ao texto do alto e libera o canto
        cena = cena.resize((int(W * s), int(H * s)), Image.BILINEAR)
        p.alpha_composite(cena, (int(540 * (1 - s)), int(560 * (1 - s))))
    else:
        p.alpha_composite(cena)
    return p


def frame_tela(tl: dict, t: float, n: int) -> Image.Image:
    fundo = fundo_preto(n)
    bordas = [OFF[s] for s in tl["segs"][1:]]
    k = sum(1 for b in bordas if t >= b)
    if tl.get("push", True):
        TR = 0.32
        for bi, b in enumerate(bordas):
            if b - TR / 2 <= t < b + TR / 2:          # empurrão lateral com desfoque
                u = ease_in_out((t - (b - TR / 2)) / TR)
                a = painel_tela(tl, bi, t)
                c = painel_tela(tl, bi + 1, max(t, b))
                vel = math.sin(u * math.pi)
                for painel, dx in ((a, -u * W), (c, (1 - u) * W)):
                    if abs(dx) < W:
                        fundo.alpha_composite(desfoque_h(painel, int(70 * vel)), (int(dx), 0))
                return fundo
    fundo.alpha_composite(painel_tela(tl, k, t))
    return fundo


def desfoque_h(im: Image.Image, r: int) -> Image.Image:
    if r < 2:
        return im
    a = np.asarray(im, np.float32)
    passos = range(-r // 2, r // 2 + 1, max(1, r // 8))
    out = sum(np.roll(a, s, axis=1) for s in passos) / len(passos)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- sticker
def sticker(t: float) -> Image.Image | None:
    if not STICKER or not (STICKER["ini"] <= t < STICKER["fim"]):
        return None
    dt, resta = t - STICKER["ini"], STICKER["fim"] - t
    s = ease_out(dt / 0.18) * (1 + 0.12 * math.sin(min(dt / 0.3, 1) * math.pi)) * ease_out(resta / 0.15)
    if s < 0.02:
        return None
    L = 270
    fundo_box = Image.new("RGBA", (L + 80, L + 80), (0, 0, 0, 0))
    ImageDraw.Draw(fundo_box).rounded_rectangle((40, 40, L + 40, L + 40), radius=26, fill=(20, 20, 20, 110))
    box = Image.new("RGBA", (L + 80, L + 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    per = [(40, 40, L + 40, 40), (L + 40, 40, L + 40, L + 40), (L + 40, L + 40, 40, L + 40), (40, L + 40, 40, 40)]
    for x0, y0, x1, y1 in per:
        comp = math.hypot(x1 - x0, y1 - y0)
        for s0 in range(0, int(comp), 30):
            a0, a1 = s0 / comp, min(s0 + 18, comp) / comp
            d.line((x0 + (x1 - x0) * a0, y0 + (y1 - y0) * a0, x0 + (x1 - x0) * a1, y0 + (y1 - y0) * a1),
                   fill=AMARELO + (255,), width=6)
    box = glow(box, 0.7)
    o = obj(STICKER["obj"], 230, -8)
    fundo_box.alpha_composite(box)
    box = fundo_box
    box.alpha_composite(o, ((L + 80 - o.width) // 2, (L + 80 - o.height) // 2))
    return box.resize((max(2, int(box.width * s)), max(2, int(box.height * s))), Image.LANCZOS)


# ---------------------------------------------------------------- composição do quadro
def ini_bloco_broll(t: float) -> float:
    """Início do bloco de B-roll em que t está (clipes colados um no outro contam como um bloco)."""
    b = next(b for b in BROLLS if b["ini"] <= t < b["fim"])
    while True:
        ant = next((a for a in BROLLS if abs(a["fim"] - b["ini"]) < 1e-6), None)
        if ant is None:
            return b["ini"]
        b = ant


# mapa.json "blur": [[t0, t1, x, y, w, h], ...] em segundos da SAÍDA e pixels de 1080x1920.
# Esconde dado sensível da fonte (chave de API, e-mail, senha): pixeliza e desfoca a caixa,
# antes de qualquer outra camada (a pessoa recortada e a presença já saem borradas).
BLURS = [tuple(b) for b in MAPA.get("blur", [])]


def borra(fr: Image.Image, t: float) -> Image.Image:
    for t0, t1, x, y, w, h in BLURS:
        if t0 <= t < t1:
            box = (int(x), int(y), int(x + w), int(y + h))
            reg = fr.crop(box)
            reg = reg.resize((max(1, reg.width // 24), max(1, reg.height // 24)), Image.BILINEAR)
            reg = reg.resize((box[2] - box[0], box[3] - box[1]), Image.BILINEAR).filter(ImageFilter.GaussianBlur(10))
            fr = fr.copy()
            fr.paste(reg, box[:2])
    return fr


def compoe(fr: Image.Image, t: float, n: int, broll: Image.Image | None, legendas: list[dict]) -> Image.Image:
    if BLURS:
        fr = borra(fr, t)
    tela = next((tl for tl in TELAS if tl["ini"] <= t < tl["fim"]), None)
    if tela:
        out = frame_tela(tela, t, n)          # voz continua, legenda vira o texto da tela
        if PRESENCA:
            # "janelas" (opcional): a pessoa só aparece onde está de fato na fonte; fora delas o recorte
            # pegaria transição/notebook e viraria um fantasma. A entrada sobe a partir da janela.
            jan = PRESENCA["tela"].get("janelas")
            j0 = tela["ini"] if jan is None else next((a for a, b in jan if a <= t < b), None)
            if j0 is not None:
                presenca(out, fr, n, PRESENCA["tela"], t - j0)
        return out

    leg_y = LEG_Y
    if broll is not None:
        pessoa = fr
        fr = broll.copy()
        if PRESENCA:
            leg_y = PRESENCA["broll"]["leg_y"]
            if np.asarray(fr.crop((0, leg_y - 160, W, leg_y + 240)).convert("L")).mean() > 120:
                fr.alpha_composite(FAIXA_PRES)
            presenca(fr, pessoa, n, PRESENCA["broll"], t - ini_bloco_broll(t))
        # B-roll claro (tela do Claude) engole legenda branca e amarela: faixa escura suave atrás
        elif np.asarray(fr.crop((0, 1080, W, 1460)).convert("L")).mean() > 120:
            fr.alpha_composite(FAIXA)
    else:
        # atrás da cabeça: gancho e número
        if GANCHO and GANCHO["ini"] <= t < GANCHO["fim"]:
            u = ease_out((t - GANCHO["ini"]) / (GANCHO["pousa"] - GANCHO["ini"]))
            sai = ease_out((GANCHO["fim"] - t) / 0.25)
            o = obj(GANCHO["obj"], GANCHO["alt"], -40 + 22 * u + 2 * math.sin(t * 3), max(0.05, sai))
            cx, cy = GANCHO["x"], -380 + (GANCHO["y"] + 380) * u + 6 * math.sin(t * 2.4)
            atras = fr.copy()
            atras.alpha_composite(o, (int(cx - o.width / 2), int(cy - o.height / 2)))
            fr = pessoa_na_frente(fr, atras, n)
        if NUMERO and NUMERO["ini"] <= t < NUMERO["fim"]:
            dt, resta = t - NUMERO["ini"], NUMERO["fim"] - t
            s = 1.14 - 0.14 * ease_out(dt / 0.35) + 0.04 * (dt / (NUMERO["fim"] - NUMERO["ini"]))
            alfa = min(ease_out(dt / 0.25), ease_out(resta / 0.25))
            im = NUM_IMG.resize((int(NUM_IMG.width * s * 0.95), int(NUM_IMG.height * s * 0.95)), Image.LANCZOS)
            if alfa < 0.999:
                im.putalpha(im.getchannel("A").point(lambda v: int(v * alfa)))
            atras = fr.copy()
            atras.alpha_composite(im, (W // 2 - im.width // 2, 470 - im.height // 2))
            fr = pessoa_na_frente(fr, atras, n)
        for gr in GRAFICOS:   # gráfico acima da cabeça, atrás do cabelo (antes do zoom, como o gancho)
            if OFF[gr["tomada"]] <= t < OFF[gr["tomada"] + 1]:
                atras = fr.copy()
                atras.alpha_composite(grafico_topo(t, gr))
                fr = pessoa_na_frente(fr, atras, n)
        if FX_BANCO and FX_BANCO.ativo(t):   # efeito da /reel-efeitos (antes do zoom, como o gancho)
            fr = FX_BANCO.aplica(fr, t, n, mascara(n))
        fr = zoom_quadro(fr, t)
        st = sticker(t)
        if st is not None:
            fr.alpha_composite(st, (STICKER["x"] - st.width // 2, STICKER["y"] - st.height // 2))
        leg_y = leg_y_trecho(fr, t) or leg_y

    # legenda por ÚLTIMO (regra 1)
    b = next((b for b in legendas if b["ini"] <= t < b["fim"]), None)
    if b:
        desenha_legenda(fr, b, t, leg_y)
    return fr


# ---------------------------------------------------------------- áudio: SFX
def sfx_whoosh(d=0.5, f0=300, f1=2600, seed=0):
    n = int(d * SR)
    r = np.random.default_rng(seed).standard_normal(n)
    t = np.arange(n) / SR
    fc = f0 * (f1 / f0) ** (t / d)
    out = np.zeros(n)
    # passa-banda variável: ressonador de 2 polos com centro varrendo
    y1 = y2 = 0.0
    for i in range(n):
        w = 2 * math.pi * fc[i] / SR
        rr = 0.985
        y = r[i] * (1 - rr) + 2 * rr * math.cos(w) * y1 - rr * rr * y2
        out[i], y2, y1 = y, y1, y
    env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2
    out = out * env
    return out / (np.abs(out).max() + 1e-9)


def sfx_impacto(d=0.7, seed=1):
    n = int(d * SR)
    t = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * (48 + 60 * np.exp(-t * 18)) * t) * np.exp(-t * 7)
    clique = np.random.default_rng(seed).standard_normal(n) * np.exp(-t * 90) * 0.5
    out = corpo + clique
    return out / np.abs(out).max()


def sfx_pop(d=0.09, f0=1100, f1=520):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * t / d
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
    return out / np.abs(out).max()


def trilha_sfx(legendas: list[dict]) -> np.ndarray:
    pista = np.zeros(int(TOTAL * SR) + SR)
    sons = {"whoosh": [sfx_whoosh(0.45, seed=s) for s in (1, 2, 3)],
            "whoosh_sobe": [sfx_whoosh(0.5, 200, 3200, seed=s) for s in (4, 5)],
            "impacto": [sfx_impacto(seed=s) for s in (1, 2)],
            "pop": [sfx_pop(), sfx_pop(0.08, 1300, 650), sfx_pop(0.1, 950, 480)]}
    giro = {k: itertools.cycle(v) for k, v in sons.items()}
    eventos: list[tuple[float, str, float]] = []   # (tempo, tipo, ganho dB)
    if GANCHO:
        eventos += [(GANCHO["ini"] - 0.05, "whoosh_sobe", -16), (GANCHO["pousa"] - 0.02, "impacto", -18)]
    if NUMERO:
        eventos += [(NUMERO["ini"] - 0.15, "whoosh_sobe", -17), (NUMERO["ini"] + 0.05, "impacto", -16)]
    for tl in TELAS:
        eventos += [(tl["ini"] - 0.02, "impacto", -15), (tl["ini"] - 0.2, "whoosh", -19)]
        if tl.get("push", True):
            eventos += [(OFF[s] - 0.22, "whoosh", -17) for s in tl["segs"][1:]]
    vistas = set()
    for tl in TELAS:
        for k, c in enumerate(tl["cenas"]):
            if id(c) in vistas:
                continue
            vistas.add(id(c))
            g = tl["segs"][k]
            if c["tipo"] == "raiox":
                eventos += [(t_pal(w, g), "pop", -17) for w in c["palavras"]]
            elif c["tipo"] == "barras":
                eventos += [(t_pal(c["dispara"], g), "whoosh_sobe", -19), (t_pal(c["entra_objeto"], g), "pop", -15)]
            elif c["tipo"] == "fluxo":
                for i, n_ in enumerate(c["nos"]):
                    if i:
                        eventos.append((OFF[n_["tomada"]] - 0.12, "whoosh", -21))
                    eventos.append((ativacao_no(n_), "pop", -17))
                if c.get("curva"):
                    eventos.append((t_pal(c["curva"]["palavra"], c["curva"]["tomada"]) - 0.1, "whoosh_sobe", -17))
            elif c["tipo"] == "memorial":
                if c.get("pedido"):
                    eventos.append((t_pal(c["pedido"]["palavra"], c["pedido"]["tomada"]), "pop", -18))
                eventos.append((t_pal(*c["preenche"]) - 0.05, "whoosh_sobe", -21))
                if c.get("falta"):
                    tf = t_pal(c["falta"]["palavra"], c["falta"]["tomada"])
                    eventos += [(tf + 0.18 * k + 0.15, "pop", -16) for k in range(len(c["falta"]["linhas"]))]
                for v in c.get("inventa", []):
                    ti = t_pal(v["palavra"], v["tomada"])
                    eventos += [(ti, "whoosh", -21), (ti + 0.45, "pop", -15)]
            elif c["tipo"] == "ramos":
                eventos.append((ativacao_no(c["origem"]), "pop", -18))
                for n_ in [c["centro"]] + c["saidas"]:
                    ta = ativacao_no(n_)
                    eventos += [(ta - 0.35, "whoosh", -21), (ta, "pop", -17)]
    inicios = [b["ini"] for b in BROLLS if not any(abs(c["fim"] - b["ini"]) < 1e-6 for c in BROLLS)]
    eventos += [(t0 - 0.2, "whoosh", -18) for t0 in inicios]
    if STICKER:
        eventos += [(STICKER["ini"], "pop", -14)]
    for gr in GRAFICOS:
        ats = [t_pal(n_["palavra"], gr["tomada"]) for n_ in gr["nos"]]
        eventos += [(OFF[gr["tomada"]] + 0.05, "whoosh_sobe", -21)]
        eventos += [(a - 0.35, "whoosh", -22) for a in ats[1:]] + [(a, "pop", -16) for a in ats]
    for b in legendas:
        if b["chave"]:
            eventos.append((b["t_chave"], "pop", -21))
    for t, tipo, g in eventos:
        s = next(giro[tipo]) * 10 ** (g / 20)
        i = int(max(0, t) * SR)
        pista[i:i + len(s)] += s[: len(pista) - i]
    if FX_BANCO:
        fx = FX.sintetiza(FX_BANCO.eventos_som(), TOTAL, SR, 0.35)
        pista[:len(fx)] += fx
    return pista[: int(TOTAL * SR)]


# ---------------------------------------------------------------- prévia de um quadro
def quadro_previa(base: Path, t: float, legendas: list[dict]) -> Image.Image:
    """Quadro composto em t, igual ao do vídeo (usado pelo --so-quadros e pelo --storyboard)."""
    n = round(t * FPS)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(base), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fr = Image.frombytes("RGB", (W, H), raw).convert("RGBA")
    return compoe(fr, t, n, broll_still(t), legendas)


# ================================================================ STORYBOARD (aprovação antes do render)
NOMES_SB = {"raiox": "Tela preta: raio-X", "barras": "Tela preta: barras que disparam",
            "fluxo": "Tela preta: fluxo de etapas", "objeto": "Tela preta: objeto 3D",
            "memorial": "Tela preta: documento (FALTOU / INVENTADO)", "ramos": "Tela preta: um vira vários"}


def _cena_pronta(c: dict, g: int) -> tuple[float, float]:
    """(última entrada, instante em que a cena da tela preta já está inteira), com os tempos de cena_*."""
    tp = c["tipo"]
    ev: list[tuple[float, float]] = []   # (entra, margem até assentar)
    if tp == "objeto":
        ev = [(OFF[g], 0.6)]
    elif tp == "raiox":
        ev = [(t_pal(w, g), 0.4) for w in c["palavras"]]
    elif tp == "barras":
        ev = [(t_pal(c["dispara"], g), 0.6), (t_pal(c["entra_objeto"], g), 0.3)]
    elif tp == "fluxo":
        ev = [(ativacao_no(n_), 0.4) for n_ in c["nos"]]
        if c.get("curva"):
            ev.append((t_pal(c["curva"]["palavra"], c["curva"]["tomada"]), 0.95))
    elif tp == "ramos":
        ev = [(ativacao_no(n_), 0.4) for n_ in [c["origem"], c["centro"]] + c["saidas"]]
    elif tp == "memorial":
        tp_ = t_pal(*c["preenche"])
        ev = [(tp_ + 0.15 + 0.16 * (len(c["linhas"]) - 1), 0.3)]
        if c.get("pedido"):
            ev.append((t_pal(c["pedido"]["palavra"], c["pedido"]["tomada"]), 0.95))
        if c.get("falta"):
            ev.append((t_pal(c["falta"]["palavra"], c["falta"]["tomada"]) + 0.18 * (len(c["falta"]["linhas"]) - 1), 0.4))
        ev += [(t_pal(v["palavra"], v["tomada"]), 0.65) for v in c.get("inventa", [])]
    else:
        ev = [(OFF[g], 0.8)]
    return max(a for a, _ in ev), max(a + m for a, m in ev)


def _desc_cena(c: dict) -> str:
    tp = c["tipo"]
    if tp == "objeto":
        return f'objeto "{c["objeto"]}" sobe e flutua'
    if tp == "raiox":
        base = "cartões com " + ", ".join(c["icones"]) if c.get("icones") else "grade de mini-Reels"
        return f'{base}; {c.get("objeto", "lupa")} varre e acende: ' + " · ".join(c["rotulos"])
    if tp == "barras":
        return f'barra dispara em "{c["dispara"]}", objeto "{c["objeto"]}" entra em "{c["entra_objeto"]}"'
    if tp == "fluxo":
        txt = " → ".join(n_["rotulo"] for n_ in c["nos"])
        return txt + (f' + curva de crescimento em "{c["curva"]["palavra"]}"' if c.get("curva") else "")
    if tp == "ramos":
        return (f'{c["origem"]["rotulo"]} → {c["centro"]["rotulo"]} → '
                + " · ".join(s_["rotulo"] for s_ in c["saidas"]))
    if tp == "memorial":
        extra = []
        if c.get("falta"):
            extra.append("FALTOU em " + ", ".join(c["linhas"][i] for i in c["falta"]["linhas"]))
        if c.get("inventa"):
            extra.append("INVENTADO em " + ", ".join(c["linhas"][v["linha"]] for v in c["inventa"]))
        return f'documento "{c["titulo"]}": ' + " / ".join(c["linhas"]) + ("; " + "; ".join(extra) if extra else "")
    return _textos_sb(c)


def _textos_sb(spec: dict) -> str:
    """textos_do_spec + as chaves de texto/arquivo dos efeitos que ele não lê (itens em texto, capa...)."""
    import storyboard as SB
    partes = [SB.textos_do_spec(spec)]
    itens = [str(i) for i in spec.get("itens", []) if isinstance(i, str)]
    if itens:
        partes.append(" · ".join(itens))
    partes += [SB.limpa_marcacao(str(spec[k])) for k in ("esq", "dir", "selo", "chamada", "sub")
               if spec.get(k) not in (None, "")]
    for k in ("imagens", "midia"):
        v = spec.get(k)
        if v:
            partes.append(f"{k}: " + (", ".join(Path(x).name for x in v) if isinstance(v, list) else str(v)))
    return " — ".join(p for p in partes if p)


def storyboard(base: Path, legendas: list[dict]) -> None:
    """Uma página com cada momento da edição (quadro REAL composto) pro usuário aprovar antes do render.
    Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB

    def tem_mascara(t: float) -> bool:
        return (EDIT / "masks" / "out" / f"f_{round(t * FPS):06d}.png").exists()

    SEM_REC = "sem recorte da pessoa neste quadro: vai sair NA FRENTE dela (rode mascaras.py)"
    ms, avisos = [], []

    def add(t0, t1, q, tipo, desc, aviso=None, fim_util=None):
        lim = (t1 if fim_util is None else fim_util) - 0.05
        m = {"t0": t0, "t1": t1, "quadro": max(t0, min(q, lim)), "tipo": tipo, "desc": desc or "—"}
        if aviso:
            m["aviso"] = aviso
        ms.append(m)
        return m

    # objeto do gancho, número, sticker
    if GANCHO:
        q = GANCHO["pousa"] + 0.05
        add(GANCHO["ini"], GANCHO["fim"], q, "Objeto 3D do gancho (cai atrás da cabeça)",
            f'objeto "{GANCHO["obj"]}"', None if tem_mascara(q) else SEM_REC)
    if NUMERO:
        q = NUMERO["ini"] + 0.4
        add(NUMERO["ini"], NUMERO["fim"], q, "Número gigante listrado atrás da cabeça", NUMERO["texto"],
            None if tem_mascara(q) else SEM_REC)
    if STICKER:
        add(STICKER["ini"], STICKER["fim"], STICKER["ini"] + 0.3, "Sticker tracejado", f'objeto "{STICKER["obj"]}"')

    # telas pretas: um momento por cena (cena que atravessa várias tomadas conta uma vez) + empurrões
    for tl in TELAS:
        bordas = [OFF[s] for s in tl["segs"][1:]]
        k = 0
        while k < len(tl["segs"]):
            k1 = k
            while k1 + 1 < len(tl["segs"]) and tl["cenas"][k1 + 1] is tl["cenas"][k]:
                k1 += 1
            c, g = tl["cenas"][k], tl["segs"][k]
            t0 = tl["ini"] if k == 0 else OFF[g]
            t1 = tl["fim"] if k1 == len(tl["segs"]) - 1 else OFF[tl["segs"][k1 + 1]]
            interna = k1 < len(tl["segs"]) - 1 and tl["push"]
            fim_util = t1 - (0.16 if interna else 0.0)          # fora do empurrão lateral
            ultima, pronta = _cena_pronta(c, g)
            gq = max((s for s in tl["segs"][k:k1 + 1] if OFF[s] <= min(pronta, fim_util - 0.05)), default=g)
            ult = max([w["s"] for w in WORDS if w["seg"] == gq] + [OFF[gq]])
            q = max(t0, min(max(pronta, ult + 0.05), fim_util - 0.05))
            amarelo = sorted({a for kk in range(k, k1 + 1) for a in tl["amarelo"][kk]})
            desc = _desc_cena(c) + (f'; em amarelo: {", ".join(amarelo)}' if amarelo else "")
            aviso = None
            if fim_util - ultima < 0.5:
                aviso = f"o último item entra só {max(0.0, fim_util - ultima):.1f} s antes de a cena sair".replace(".", ",")
            jan = PRESENCA["tela"].get("janelas") if PRESENCA else None
            if PRESENCA and (jan is None or any(a <= q < b for a, b in jan)):
                desc += "; a pessoa recortada no canto"
                if not tem_mascara(q):
                    aviso = "sem recorte da pessoa neste quadro: ela não aparece no canto (rode mascaras.py)"
            add(t0, t1, q, NOMES_SB.get(c["tipo"], "Tela preta: " + c["tipo"]), desc, aviso, fim_util)
            k = k1 + 1
        if tl["push"]:
            for b in bordas:
                add(b - 0.16, b + 0.16, b, "Transição: empurrão lateral", "troca de cena dentro da tela preta")

    # B-roll
    for b in BROLLS:
        desc = f'{b["arq"]} a partir de {b["src"]:.1f} s'.replace(".", ",", 1) + \
            (f'; recorte {b["crop"][2]}×{b["crop"][3]} em ({b["crop"][0]}, {b["crop"][1]})' if b["crop"] else "")
        q = b["ini"] + 0.4
        aviso = None
        if not (PASTA / b["arq"]).exists():
            aviso = "arquivo de B-roll não existe na pasta do projeto"
        elif PRESENCA and not tem_mascara(q):
            aviso = "sem recorte da pessoa neste quadro: ela não aparece no canto (rode mascaras.py)"
        add(b["ini"], b["fim"], q, "B-roll (gravação de tela)", desc + ("; a pessoa recortada no canto" if PRESENCA else ""),
            aviso)

    # gráfico acima da cabeça
    for gr in GRAFICOS:
        g = gr["tomada"]
        q = max(t_pal(n_["palavra"], g) for n_ in gr["nos"]) + 0.4
        add(OFF[g], OFF[g + 1], q, "Gráfico acima da cabeça", " → ".join(n_["rotulo"] for n_ in gr["nos"]),
            None if tem_mascara(min(q, OFF[g + 1] - 0.35)) else SEM_REC, OFF[g + 1] - 0.3)

    # efeitos da /reel-efeitos
    if FX_BANCO:
        for it in FX_BANCO.itens:
            e = FX.EFEITOS[it["p"]["nome"]]
            d = it["fim"] - it["ini"]
            tempos = it["p"].get("tempos")
            q = it["ini"] + (max(tempos) + 0.35 if tempos else max(0.8, 0.6 * d))
            sai = float(it["p"].get("saida", FX_BANCO.saida)) if e["saida"] else 0.0
            aviso = None
            if e["mascara"] and not tem_mascara(min(q, it["fim"] - sai - 0.05)):
                aviso = "efeito usa o recorte da pessoa e não há máscara neste quadro (rode mascaras.py)"
            desc = _textos_sb({k: v for k, v in it["p"].items() if k != "nome"})
            add(it["ini"], it["fim"], q, f'Efeito: {e["rotulo"] or it["p"]["nome"]}',
                desc or f"{d:.1f} s na tela".replace(".", ","), aviso, it["fim"] - sai)

    # zoom animado nos takes
    for k_, (s0, s1) in sorted(ZOOMS.items()):
        t0, t1 = OFF[k_], OFF[k_ + 1]
        q = t1 if s1 >= s0 else t0 + 0.1
        verbo = "aproxima" if s1 > s0 else "afasta"
        aviso = None
        if (GANCHO and GANCHO["ini"] < t1 and GANCHO["fim"] > t0) or (NUMERO and NUMERO["ini"] < t1 and NUMERO["fim"] > t0):
            aviso = "zoom na tomada do gancho/número: a máscara é do quadro sem zoom (regra da skill)"
        add(t0, t1, q, "Zoom animado", f"{verbo} devagar de {s0:.2f}x a {s1:.2f}x".replace(".", ","), aviso)

    # blur de dado sensível
    for t0, t1, x, y, w, h in BLURS:
        add(t0, t1, (t0 + t1) / 2, "Blur (dado escondido)", f"caixa {int(w)}×{int(h)} em ({int(x)}, {int(y)})")

    # legenda: palavra-chave amarela, letra a letra, frase final
    for b in legendas:
        if b.get("fecho"):
            add(b["ini"], b["fim"], b["ini"] + 0.2, "Frase final em amarelo glow",
                " ".join(limpa(WORDS[i]["t"]) for i in b["fecho"]))
        elif b["chave"]:
            chave = " ".join(limpa(WORDS[i]["t"]) for i in b["chave"]).upper()
            pre = " ".join(limpa(WORDS[i]["t"]) for i in b["pre"])
            lal = b["chave"][0] == LETRA_A_LETRA
            add(b["t_chave"], b["fim"], b["t_chave"] + (0.45 if lal else 0.2),
                "Palavra-chave letra a letra" if lal else "Palavra-chave amarela glow",
                (pre + " / " if pre else "") + chave)

    # avisos globais: buraco sem nada novo (a folha de conferência procura > 5 s parado). Tela preta,
    # B-roll, efeito, gráfico e zoom animam a si mesmos: o tempo deles não conta como parado.
    marcos = sorted(set([0.0, TOTAL] + [m["t0"] for m in ms] + list(OFF[1:-1])))
    animados = [(m["t0"], m["t1"]) for m in ms if m["tipo"].startswith(("Tela preta", "B-roll", "Efeito", "Gráfico", "Zoom"))]
    for a, b in zip(marcos, marcos[1:]):
        livres, x = [], a
        for a2, b2 in sorted(animados):
            if b2 > x and a2 < b:
                livres.append((x, max(x, a2)))
                x = max(x, b2)
        livres.append((x, b))
        x0, x1 = max(livres, key=lambda v: v[1] - v[0])
        if x1 - x0 > 5.0:
            avisos.append(f"{x1 - x0:.1f} s sem nada novo ({x0:.1f}–{x1:.1f} s): dá pra pôr zoom, chave ou efeito"
                          .replace(".", ","))
    if any(m.get("aviso", "").startswith("sem recorte") or "máscara" in m.get("aviso", "") for m in ms):
        avisos.append("tem momento sem o recorte da pessoa (máscara): rode mascaras.py antes de aprovar")

    # imagens e vídeos que o mapa usa
    objetos = []
    if GANCHO:
        objetos.append(GANCHO["obj"])
    if STICKER:
        objetos.append(STICKER["obj"])
    vistas = set()
    for tl in TELAS:
        for c in tl["cenas"]:
            if id(c) in vistas:
                continue
            vistas.add(id(c))
            nos = c.get("nos", []) + ([c["origem"], c["centro"]] + c["saidas"] if c["tipo"] == "ramos" else [])
            objetos += [c[k] for k in ("objeto",) if c.get(k)] + list(c.get("icones") or []) + \
                [n_["objeto"] for n_ in nos]
            if c["tipo"] == "raiox" and not c.get("objeto"):
                objetos.append("lupa")
    for gr in GRAFICOS:
        objetos += [n_["objeto"] for n_ in gr["nos"]]
    arqs = []
    for o in dict.fromkeys(objetos):
        arqs.append((f"assets/{o}.png", o in ASSETS))
    for b in BROLLS:
        if b["arq"] not in [x for x, _ in arqs]:
            arqs.append((b["arq"], (PASTA / b["arq"]).exists()))
    for e in MAPA.get("efeitos", []):
        for k in ("imagens", "midia"):
            v = e.get(k)
            for a in ([v] if isinstance(v, str) else v or []):
                if a not in [x for x, _ in arqs]:
                    arqs.append((a, (PASTA / a).exists()))
    faltam = [n for n, ok in arqs if not ok]
    if faltam:
        avisos.append(f"faltam {len(faltam)} arquivo(s): " + ", ".join(faltam))

    cenas = [{"t0": OFF[g], "t1": OFF[g + 1], "fala": " ".join(w["t"] for w in WORDS if w["seg"] == g)}
             for g in range(_NG)]

    def quadro(t: float) -> Image.Image:
        try:
            return quadro_previa(base, t, legendas)
        except (SystemExit, subprocess.CalledProcessError) as erro:   # arquivo ausente não derruba a página
            n = round(t * FPS)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", str(base), "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
            fr = Image.frombytes("RGB", (W, H), raw).convert("RGBA")
            d = ImageDraw.Draw(fr)
            d.rectangle((0, 820, W, 1100), fill=(160, 20, 30, 255))
            d.text((W / 2, 960), "FALTA ARQUIVO", font=font(80), fill=BRANCO + (255,), anchor="mm")
            d.text((W / 2, 1045), str(erro)[:60], font=font(30), fill=BRANCO + (255,), anchor="mm")
            return fr

    out = SB.gerar(EDIT, "Glow", TOTAL, cenas, ms, quadro, avisos, arqs)
    print(f"storyboard: {out}  ({len(cenas)} cenas, {len(ms)} momentos)")


# ---------------------------------------------------------------- main
def pico_real(arq: Path) -> float:
    log = subprocess.run(["ffmpeg", "-nostats", "-i", str(arq), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(log.rsplit("Peak:", 1)[1].split()[0])


def segura_pico(out: Path) -> None:
    """loudnorm às vezes passa do teto (-1 dBTP) quando a voz tem estalo forte. Só nesse caso:
    limitador nos picos (-1,6 dBFS, 4x sobreamostrado), vídeo copiado, volume geral intacto."""
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
    legendas = monta_legendas()
    modo = "final" if ARGS.final else "preview"
    base = EDIT / f"base_{modo}.mov"
    if not base.exists():
        sys.exit(f"falta {base.name}: rode cortar.py base{' --final' if ARGS.final else ''}")

    if ARGS.storyboard:
        storyboard(base, legendas)
        return

    if ARGS.so_quadros:
        pasta = EDIT / "verify" / "quadros"
        pasta.mkdir(parents=True, exist_ok=True)
        for ts in ARGS.so_quadros.split(","):
            t = float(ts)
            quadro_previa(base, t, legendas).convert("RGB").save(pasta / f"q_{t:06.2f}.jpg", quality=88)
        print(f"prévias em {pasta}")
        return

    # ---- áudio: voz da base + SFX
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(base), "-vn", "-ac", "2", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    voz = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, 2) / 32768
    sfx = trilha_sfx(legendas)
    n = min(len(voz), len(sfx))
    mix = voz[:n] + sfx[:n, None]
    wav = EDIT / f"mix_{modo}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())

    # ---- vídeo quadro a quadro
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(base), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    leitor = LeitorBroll()
    prenorm = EDIT / f"{modo}_glow.prenorm.mp4"
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
        enc.stdin.write(compoe(fr, t, k, leitor.quadro(t), legendas).convert("RGB").tobytes())
        k += 1
        if k % 240 == 0:
            print(f"  {k}/{N_FRAMES} quadros", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    if leitor.proc:
        leitor.proc.kill()
    out = EDIT / f"{modo}_glow.mp4"
    R.apply_loudnorm_two_pass(prenorm, out, preview=False)
    prenorm.unlink(missing_ok=True)
    segura_pico(out)
    print(f"pronto: {out}  ({k} quadros, {k / FPS:.2f}s)")


if __name__ == "__main__":
    main()
