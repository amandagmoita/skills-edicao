"""gerar_imagens.py — imagens de IA listadas em mapa.json["imagens"] (fotos do quadro e recortes da colagem).

Uso: $PY gerar_imagens.py <edit_dir> [nome ...]
Saída: <edit>/assets/<nome>.png. Pula o que já existe (pra refazer, apague o PNG).
Chave: OPENAI_API_KEY em ~/.claude/env. gpt-image-1.5 (cai pro gpt-image-1), ~US$0,04-0,06 cada,
~20-40 s, em paralelo. "descricao" em inglês, sem texto na imagem.

Estilos (campo "estilo"):
  foto     foto realista que REPRESENTA a frase (vai no quadro branco: cena "imagens", card com foto,
           imagem no topo do gancho). Padrão 1536x1024.
  recorte  objeto/pessoa sozinho, FUNDO TRANSPARENTE, pra colagem em primeiro plano ("adesivo"). Vale
           montagem estilo meme (o cara com cabeça de máquina de escrever da referência). Padrão 1024x1536.
  meme     foto montada estilo meme pro topo do gancho (logos/objetos no lugar das cabeças etc.).
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

ESTILOS = {
    "foto": ("Realistic editorial photograph: {d}. Natural light, candid documentary feel, shallow depth of "
             "field, rich detail, reads instantly at small size. No text, no letters, no numbers, no logo, "
             "no watermark."),
    "recorte": ("{d}. Single isolated subject, full subject visible with nothing cropped, photographic and "
                "realistic, crisp edges, on a fully transparent background. No text, no letters, no logo, "
                "no watermark, no shadow on the ground."),
    "meme": ("Funny photo collage in the style of a viral internet meme: {d}. Realistic photo base, the "
             "absurd element obvious at a glance. No text, no captions, no letters, no watermark."),
}
TAMANHO = {"foto": "1536x1024", "recorte": "1024x1536", "meme": "1536x1024"}


def chave() -> str:
    """OPENAI_API_KEY da variável de ambiente ou de ~/.claude/env."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    arq = Path.home() / ".claude/env"
    for linha in (arq.read_text().splitlines() if arq.exists() else []):
        if linha.strip().startswith("OPENAI_API_KEY="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("sem chave da OpenAI: ponha OPENAI_API_KEY=... em ~/.claude/env (ou rode o instalar.sh do pack). Sem ela, use imagens suas em assets/.")


def gera(k: str, spec: dict, pasta: Path) -> str:
    nome = spec["nome"]
    destino = pasta / f"{nome}.png"
    if destino.exists():
        return f"{nome}: já existe"
    estilo = spec.get("estilo", "foto")
    prompt = ESTILOS[estilo].format(d=spec["descricao"])
    corpo_base = {"prompt": prompt, "size": spec.get("tamanho", TAMANHO[estilo]), "quality": "medium",
                  "output_format": "png", "n": 1}
    if estilo == "recorte":
        corpo_base["background"] = "transparent"
    ultimo = ""
    for modelo in ("gpt-image-1.5", "gpt-image-1"):
        corpo = json.dumps({"model": modelo, **corpo_base}).encode()
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=corpo,
                                     headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            t0 = time.time()
            d = json.load(urllib.request.urlopen(req, timeout=300))
            im = Image.open(io.BytesIO(base64.b64decode(d["data"][0]["b64_json"])))
            im = im.convert("RGBA") if estilo == "recorte" else im.convert("RGB")
            if estilo == "recorte" and im.getchannel("A").getextrema()[0] == 255:
                ultimo = f"{modelo}: veio sem transparência"
                continue
            im.save(destino)
            return f"{nome}: ok ({modelo}, {time.time() - t0:.0f}s)"
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: {e.code} {e.read().decode()[:200]}"
        except Exception as e:  # noqa: BLE001  (timeout de rede: tenta o outro modelo)
            ultimo = f"{modelo}: {e}"
    return f"{nome}: FALHOU — {ultimo}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    edit = Path(sys.argv[1]).resolve()
    so = set(sys.argv[2:])
    lista = [s for s in json.loads((edit / "mapa.json").read_text()).get("imagens", [])
             if not so or s["nome"] in so]
    pasta = edit / "assets"
    pasta.mkdir(exist_ok=True)
    k = chave()
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(lambda s: gera(k, s, pasta), lista):
            print(r, flush=True)
