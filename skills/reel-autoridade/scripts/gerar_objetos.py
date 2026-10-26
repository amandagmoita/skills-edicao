#!/usr/bin/env python3
"""gerar_objetos.py — gera os objetos 3D (fundo transparente) listados em mapa.json -> "objetos_ia".

Uso:
  python3 gerar_objetos.py <pasta_projeto> [--qualidade medium] [--so nome1,nome2]

Cada item: {"nome": "ampulheta", "descricao": "an antique wooden hourglass with sand falling"}
Saída: <pasta_projeto>/assets/<nome>.png (recortado no conteúdo). Pula o que já existe.
Chave: OPENAI_API_KEY em ~/.claude/env. Modelo: gpt-image-1.5 (cai pro gpt-image-1 se falhar).
Custo de referência: ~US$0,04 por imagem em medium 1024x1024.
"""
import argparse, base64, io, json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

MODELOS = ["gpt-image-1.5", "gpt-image-1"]
ESTILO = ("Photorealistic 3D product render of {d}. A single object, centered, whole object visible "
          "with generous margin, three-quarter view, dramatic studio lighting with a soft warm key light "
          "and a subtle rim light, glossy premium materials, high detail. Isolated on a fully transparent "
          "background. No text, no logo, no floor, no cast shadow, no reflection surface.")


def chave():
    """OPENAI_API_KEY da variável de ambiente ou de ~/.claude/env."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    arq = os.path.expanduser("~/.claude/env")
    for linha in (open(arq) if os.path.exists(arq) else []):
        linha = linha.strip()
        if linha.startswith("OPENAI_API_KEY="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("sem chave da OpenAI: ponha OPENAI_API_KEY=... em ~/.claude/env (ou rode o instalar.sh do pack). Sem ela, use imagens suas em assets/.")


def gera(k, item, pasta, qualidade):
    destino = os.path.join(pasta, item["nome"] + ".png")
    if os.path.exists(destino):
        return f"{item['nome']}: já existe"
    ultimo = ""
    for modelo in MODELOS:
        corpo = json.dumps({"model": modelo, "prompt": ESTILO.format(d=item["descricao"]),
                            "size": "1024x1024", "quality": qualidade, "background": "transparent",
                            "output_format": "png", "n": 1}).encode()
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=corpo,
                                     headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            t0 = time.time()
            d = json.load(urllib.request.urlopen(req, timeout=240))
            img = Image.open(io.BytesIO(base64.b64decode(d["data"][0]["b64_json"]))).convert("RGBA")
            bbox = img.getchannel("A").getbbox()
            (img.crop(bbox) if bbox else img).save(destino)
            return f"{item['nome']}: ok ({modelo}, {time.time() - t0:.0f}s)"
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: {e.code} {e.read().decode()[:200]}"
    return f"{item['nome']}: FALHOU — {ultimo}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto"); ap.add_argument("--qualidade", default="medium")
    ap.add_argument("--so", default="")
    a = ap.parse_args()
    mapa = json.load(open(os.path.join(a.projeto, "mapa.json")))
    itens = mapa.get("objetos_ia", [])
    if a.so:
        nomes = set(a.so.split(","))
        itens = [i for i in itens if i["nome"] in nomes]
    if not itens:
        print("nada em objetos_ia"); return
    pasta = os.path.join(a.projeto, "assets"); os.makedirs(pasta, exist_ok=True)
    k = chave()
    with ThreadPoolExecutor(4) as ex:
        for msg in ex.map(lambda i: gera(k, i, pasta, a.qualidade), itens):
            print(msg)


if __name__ == "__main__":
    sys.exit(main())
