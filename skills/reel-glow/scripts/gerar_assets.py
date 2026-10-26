"""gerar_assets.py — objetos 3D (fundo transparente) listados em mapa.json["objetos"].

Uso: $PY gerar_assets.py <edit_dir> [nome ...]
Saída: <edit>/assets/<nome>.png recortado no conteúdo. Pula o que já existe (pra refazer, apague o PNG).
Chave: OPENAI_API_KEY em ~/.claude/env. gpt-image-1.5 (cai pro gpt-image-1), ~US$0,04 cada, ~15 s,
em paralelo. "descricao" em inglês, objeto único e concreto, sem marca, texto ou pessoa.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ESTILO = ("Photorealistic 3D render of {d}. A single object, whole object visible with generous margin, "
          "three-quarter view, cinematic low-key studio lighting, soft warm key light and a subtle rim light, "
          "premium realistic materials, high detail. Isolated on a fully transparent background. "
          "No text, no letters, no logo, no floor, no shadow, no reflection surface.")


def chave() -> str:
    """OPENAI_API_KEY da variável de ambiente ou de ~/.claude/env."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    arq = Path.home() / ".claude/env"
    for linha in (arq.read_text().splitlines() if arq.exists() else []):
        if linha.strip().startswith("OPENAI_API_KEY="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("sem chave da OpenAI: ponha OPENAI_API_KEY=... em ~/.claude/env (ou rode o instalar.sh do pack). Sem ela, use imagens suas em assets/.")


def gera(k: str, nome: str, descricao: str, pasta: Path) -> str:
    destino = pasta / f"{nome}.png"
    if destino.exists():
        return f"{nome}: já existe"
    ultimo = ""
    for modelo in ("gpt-image-1.5", "gpt-image-1"):
        corpo = json.dumps({"model": modelo, "prompt": ESTILO.format(d=descricao), "size": "1024x1024",
                            "quality": "medium", "background": "transparent", "output_format": "png",
                            "n": 1}).encode()
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=corpo,
                                     headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            t0 = time.time()
            d = json.load(urllib.request.urlopen(req, timeout=240))
            img = Image.open(io.BytesIO(base64.b64decode(d["data"][0]["b64_json"]))).convert("RGBA")
            bbox = img.getchannel("A").getbbox()
            (img.crop(bbox) if bbox else img).save(destino)
            return f"{nome}: ok ({modelo}, {time.time() - t0:.0f}s)"
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: {e.code} {e.read().decode()[:200]}"
    return f"{nome}: FALHOU — {ultimo}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    edit = Path(sys.argv[1]).resolve()
    objetos = json.loads((edit / "mapa.json").read_text()).get("objetos", {})
    nomes = sys.argv[2:] or list(objetos)
    pasta = edit / "assets"
    pasta.mkdir(exist_ok=True)
    k = chave()
    with ThreadPoolExecutor(6) as ex:
        for msg in ex.map(lambda n: gera(k, n, objetos[n], pasta), nomes):
            print(msg)
