"""medir.py — onde está a cabeça e o rosto da pessoa em cada tomada (o telão encosta no topo da cabeça,
a legenda foge do rosto). Mede na base cortada, então já leva em conta a troca de enquadramento.

Uso: $PY medir.py <edit_dir> [--final]
Gera <edit>/medidas.json: {"grupos": [{"topo": y, "rosto": [x, y, w, h]}, ...]} em px de 1080x1920.
topo = o MAIS ALTO dos quadros amostrados (a cabeça sobe quando a pessoa gesticula); rosto = mediana.
Rodar de novo SEMPRE que a base mudar.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
BIN = AQUI / "bin" / "medir"


def main() -> None:
    edit = Path(sys.argv[1]).resolve()
    final = "--final" in sys.argv
    if not BIN.exists():
        BIN.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(AQUI / "medir.swift"), "-o", str(BIN)], check=True)
    info = json.loads((edit / "base_info.json").read_text())
    base = edit / f"base_{'final' if final else 'preview'}.mov"
    edl = json.loads((edit / "edl.json").read_text())["ranges"]
    offs = list(itertools.accumulate([0.0] + info["duracoes"]))
    ng = max(r["grupo"] for r in edl) + 1
    pasta = edit / "verify" / "medir"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    for g in range(ng):
        idx = [i for i, r in enumerate(edl) if r["grupo"] == g]
        a, b = offs[idx[0]], offs[idx[-1] + 1]
        for k, f in enumerate((0.15, 0.4, 0.65, 0.9)):
            t = a + (b - a) * f
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(base), "-frames:v", "1",
                            "-y", str(pasta / f"g{g:02d}_{k}.jpg")], check=True)
    linhas = subprocess.run([str(BIN), str(pasta)], capture_output=True, text=True, check=True).stdout
    medidas = [json.loads(l) for l in linhas.splitlines() if l.strip()]
    grupos = []
    for g in range(ng):
        ms = [m for m in medidas if m["arquivo"].startswith(f"g{g:02d}_")]
        topos = [m["topo"] for m in ms if m["topo"] is not None]
        rostos = [m["rosto"] for m in ms if m["rosto"] is not None]
        if not topos or not rostos:
            sys.exit(f"tomada {g}: não achei a pessoa/rosto nos quadros de {pasta}")
        grupos.append({"topo": int(min(topos)), "rosto": [int(v) for v in np.median(np.array(rostos), axis=0)]})
        print(f"tomada {g:02d}: topo {grupos[-1]['topo']:4d}  rosto {grupos[-1]['rosto']}")
    (edit / "medidas.json").write_text(json.dumps({"grupos": grupos}, indent=1))


if __name__ == "__main__":
    main()
