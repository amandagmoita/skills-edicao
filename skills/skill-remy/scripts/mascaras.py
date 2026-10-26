"""mascaras.py — recorte da pessoa (Apple Vision) nos quadros em que ela fica na frente de algo:
a cabeça da pessoa passando na frente do quadro branco.

Uso: $PY mascaras.py <edit_dir> [--final]
Lê as janelas pelo próprio compor.py (mesma conta), extrai esses quadros da base em 1080x1920 e grava
masks/out/f_<quadro>.png. Rodar de novo SEMPRE que a base ou o tempo desses elementos mudar.
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
    janelas = [(max(0.0, a), b) for a, b in C.janelas_mascara()]
    if not janelas:
        print("nenhum quadro com a pessoa na frente: sem máscara")
        return
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in janelas)
    m = C.EDIT / "masks"
    shutil.rmtree(m, ignore_errors=True)
    (m / "src").mkdir(parents=True)
    # -frame_pts: o nome do arquivo é o número do quadro na base (é como o compor procura)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(C.BASE), "-vf", f"select='{sel}'",
                    "-vsync", "0", "-frame_pts", "1", str(m / "src" / "f_%06d.png")], check=True)
    subprocess.run([str(BIN), str(m / "src"), str(m / "out")], check=True)
    shutil.rmtree(m / "src", ignore_errors=True)
    print(f"{len(list((m / 'out').glob('*.png')))} máscaras em {m / 'out'}  (janelas {janelas})")


if __name__ == "__main__":
    main()
