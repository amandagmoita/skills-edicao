"""logos.py — busca logos e ícones OFICIAIS pra <edit>/assets/ (o estilo usa sempre o material real).

Uso: $PY logos.py <edit_dir> <fonte> [<fonte> ...]
Fontes:
  app:Claude                ícone do app instalado no Mac (o mesmo do Finder), 1024 px → assets/claude.png
  app:Notas=notas           com "=nome" escolhe o nome do arquivo
  si:anthropic              logo da marca no Simple Icons (SVG renderizado pelo Quick Look), preto
  si:claude:#D97757=claude_logo   com cor
  url:https://...png=nome   baixa uma imagem qualquer (logo do site, foto da pessoa citada)
  sf:gearshape.fill=engrenagem   SF Symbol do macOS (ícone neon da /skill-iphone), 512 px

Pula o que já existe (pra refazer, apague o PNG). Sem conversor de SVG instalado no Mac: o Quick Look
(qlmanage) desenha o SVG em fundo branco e aqui o branco vira transparente.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

AQUI = Path(__file__).resolve().parent
BIN = AQUI / "bin" / "icone"
BIN_SF = AQUI / "bin" / "simbolo"
SI = "https://cdn.jsdelivr.net/npm/simple-icons@13.21.0/icons/{}.svg"
PASTAS_APPS = ["/Applications", "/System/Applications", "/System/Applications/Utilities",
               "/System/Library/CoreServices", str(Path.home() / "Applications")]


def slug(txt: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in txt.lower()).strip("_")


def acha_app(nome: str) -> Path:
    for p in PASTAS_APPS:
        cand = Path(p) / f"{nome}.app"
        if cand.exists():
            return cand
    for p in PASTAS_APPS:   # sem diferenciar maiúscula
        for c in Path(p).glob("*.app"):
            if c.stem.lower() == nome.lower():
                return c
    sys.exit(f"app {nome} não encontrado em {', '.join(PASTAS_APPS)}")


def icone_app(nome: str, out: Path) -> None:
    if not BIN.exists():
        BIN.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(AQUI / "icone.swift"), "-o", str(BIN)], check=True)
    subprocess.run([str(BIN), str(acha_app(nome)), str(out), "1024"], check=True)
    im = Image.open(out).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    if bb:
        im.crop(bb).save(out)


def simple_icon(s: str, cor: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / f"{s}.svg"
        try:
            urllib.request.urlretrieve(SI.format(s), svg)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Simple Icons não tem '{s}' ({e}); procure o slug em simpleicons.org")
        subprocess.run(["qlmanage", "-t", "-s", "1024", "-o", tmp, str(svg)], capture_output=True, check=True)
        png = Path(tmp) / f"{s}.svg.png"
        if not png.exists():
            sys.exit(f"o Quick Look não desenhou {svg.name}")
        lum = np.asarray(Image.open(png).convert("L"), np.float32)
    alfa = np.clip((255 - lum) * 1.02, 0, 255).astype(np.uint8)
    rgb = tuple(int(cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    arr = np.zeros(alfa.shape + (4,), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = alfa
    im = Image.fromarray(arr, "RGBA")
    bb = im.getchannel("A").getbbox()
    (im.crop(bb) if bb else im).save(out)


def sf_symbol(nome: str, out: Path) -> None:
    if not BIN_SF.exists():
        BIN_SF.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(AQUI / "simbolo.swift"), "-o", str(BIN_SF)], check=True)
    subprocess.run([str(BIN_SF), nome, str(out), "512"], check=True)
    im = Image.open(out).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    if bb:
        im.crop(bb).save(out)


def baixa(url: str, out: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(out.with_suffix(".tmp"), "wb") as f:
        shutil.copyfileobj(r, f)
    Image.open(out.with_suffix(".tmp")).convert("RGBA").save(out)
    out.with_suffix(".tmp").unlink()


def main() -> None:
    edit = Path(sys.argv[1]).resolve()
    pasta = edit / "assets"
    pasta.mkdir(parents=True, exist_ok=True)
    for fonte in sys.argv[2:]:
        nome = None
        if "=" in fonte:   # "=nome" no fim (url sempre termina assim, mesmo tendo "=" na query)
            a, b = fonte.rsplit("=", 1)
            if b and all(c.isalnum() or c in "_-" for c in b):
                fonte, nome = a, b
        tipo, resto = fonte.split(":", 1)
        if tipo == "app":
            out = pasta / f"{nome or slug(resto)}.png"
            if not out.exists():
                icone_app(resto, out)
        elif tipo == "si":
            partes = resto.split(":")
            out = pasta / f"{nome or slug(partes[0])}.png"
            if not out.exists():
                simple_icon(partes[0], partes[1] if len(partes) > 1 else "#000000", out)
        elif tipo == "sf":
            out = pasta / f"{nome or slug(resto)}.png"
            if not out.exists():
                sf_symbol(resto, out)
        elif tipo == "url":
            if not nome:
                sys.exit("url: precisa de =nome no fim")
            out = pasta / f"{nome}.png"
            if not out.exists():
                baixa(resto, out)
        else:
            sys.exit(f"fonte desconhecida: {fonte}")
        im = Image.open(out)
        print(f"  {out.name}  {im.width}x{im.height}")


if __name__ == "__main__":
    main()
