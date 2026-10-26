"""mascaras.py — recorte da pessoa (Apple Vision) só nos quadros em que algo passa atrás dela
(prévia, parede, órbita, palavra do antes e depois), onde a luz depende da silhueta (holofote) e nos
quadros de onde a cabeça é medida (congela, zoom, miniaturas da prévia).

Uso: $PY mascaras.py <edit_dir> [--final]
Lê os tempos pelo próprio compor.py (mesma conta, sem duplicar) e grava masks/out/f_<quadro>.png.
Rodar de novo SEMPRE que a base mudar (corte novo = quadros novos).

Os quadros saem numerados em sequência e são renomeados pelo índice real: o -frame_pts do ffmpeg
devolve o pts no timebase do arquivo, que nem sempre é o número do quadro.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import compor as C  # noqa: E402  (lê sys.argv: <edit_dir> [--final])

BIN = AQUI / "bin" / "mascara"


def main() -> None:
    if not BIN.exists():
        BIN.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(AQUI / "mascara.swift"), "-o", str(BIN)], check=True)
    quadros: set[int] = set()
    for e in C.EFEITOS:
        for a, b in e.janelas():
            quadros.update(range(C.nq(a - 0.05), C.nq(b + 0.05) + 1))
        quadros.update(e.quadros())
    if C.CTA:
        quadros.add(C.nq(C.CTA.t0))
    lista = sorted(q for q in quadros if 0 <= q < C.N_FRAMES)
    m = C.EDIT / "masks"
    shutil.rmtree(m, ignore_errors=True)
    (m / "src").mkdir(parents=True)
    sel = "+".join(f"eq(n\\,{q})" for q in lista)
    (m / "select.txt").write_text(f"select='{sel}'")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(C.BASE), "-filter_script:v", str(m / "select.txt"),
                    "-vsync", "0", "-start_number", "0", str(m / "src" / "s_%06d.png")], check=True)
    feitos = sorted((m / "src").glob("s_*.png"))
    if len(feitos) != len(lista):
        sys.exit(f"extraí {len(feitos)} quadros, esperava {len(lista)}")
    for arq, q in zip(feitos, lista):
        arq.rename(m / "src" / f"f_{q:06d}.png")
    subprocess.run([str(BIN), str(m / "src"), str(m / "out")], check=True)
    shutil.rmtree(m / "src", ignore_errors=True)
    print(f"{len(list((m / 'out').glob('*.png')))} máscaras em {m / 'out'}")


if __name__ == "__main__":
    main()
