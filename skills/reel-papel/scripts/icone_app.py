"""icone_app.py — baixa o ícone oficial de um app (App Store do Brasil) pra cena "app citado aparece".

Uso (Python do video-use):
  $PY icone_app.py "whatsapp" whatsapp          # baixa o 1º resultado → assets/icones/whatsapp.png
  $PY icone_app.py "google drive" drive --n 2   # escolhe o 2º resultado da lista
  $PY icone_app.py "notas" notas --lista        # só lista os 8 primeiros resultados, não baixa

Os ícones ficam na pasta da skill (assets/icones/) e servem pra todos os vídeos. O mapa.json usa o
nome do arquivo ("arquivo": "whatsapp"). SEMPRE conferir o nome do app que o script imprime: a busca
às vezes devolve um app parecido (ex.: "WhatsApp Business" no lugar do WhatsApp).
Ícone de app que não está na App Store (ex.: Claude Code, CapCut desktop): salvar um PNG quadrado
manualmente em assets/icones/<nome>.png.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

PASTA = Path(__file__).resolve().parent.parent / "assets" / "icones"


def busca(termo: str, n: int = 8) -> list[dict]:
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": termo, "entity": "software", "country": "br", "limit": n})
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)["results"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("termo")
    ap.add_argument("nome", nargs="?")
    ap.add_argument("--n", type=int, default=1, help="qual resultado baixar (1 = primeiro)")
    ap.add_argument("--lista", action="store_true")
    a = ap.parse_args()
    res = busca(a.termo)
    if not res:
        sys.exit(f'nada encontrado pra "{a.termo}"')
    for i, r in enumerate(res, 1):
        print(f"{i}. {r['trackName']}  ({r.get('sellerName', '')})")
    if a.lista or not a.nome:
        return
    r = res[a.n - 1]
    url = r["artworkUrl512"].replace("512x512bb.jpg", "1024x1024bb.png")
    try:
        dado = urllib.request.urlopen(url, timeout=30).read()
    except Exception:
        dado = urllib.request.urlopen(r["artworkUrl512"], timeout=30).read()
    im = Image.open(io.BytesIO(dado)).convert("RGB").resize((512, 512), Image.LANCZOS)
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / f"{a.nome}.png"
    im.save(destino)
    print(f"→ baixado: {r['trackName']}  em {destino}")


if __name__ == "__main__":
    main()
