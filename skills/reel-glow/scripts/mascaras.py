"""mascaras.py — recorte da pessoa (Apple Vision) nos quadros em que algo passa atrás da cabeça
(gancho, número) e, com a presença ligada, em todo B-roll e tela preta (a pessoa vai pro canto).

Uso: $PY mascaras.py <edit_dir> [--final]
Lê os tempos do gancho e do número gigante pelo próprio compor.py (mesma conta, sem duplicar),
extrai esses quadros de base_*.mov em 540x960 e grava masks/out/f_<quadro>.png.
Rodar de novo SEMPRE que a base mudar (corte novo = quadros novos).
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
    janelas = []
    if C.GANCHO:
        janelas.append((max(0.0, C.GANCHO["ini"] - 0.1), C.GANCHO["fim"] + 0.1))
    if C.NUMERO:
        janelas.append((C.NUMERO["ini"] - 0.1, C.NUMERO["fim"] + 0.1))
    if C.PRESENCA:   # a pessoa recortada no canto durante B-roll e telas pretas
        janelas += [(b["ini"] - 0.05, b["fim"] + 0.05) for b in C.BROLLS]
        janelas += [(tl["ini"] - 0.05, tl["fim"] + 0.05) for tl in C.TELAS]
    janelas += [(C.OFF[g["tomada"]] - 0.05, C.OFF[g["tomada"] + 1] + 0.05) for g in C.GRAFICOS]   # gráfico atrás da cabeça
    if C.FX_BANCO:   # efeitos da /reel-efeitos que põem algo atrás da pessoa
        janelas += C.FX_BANCO.janelas_mascara()
    if not janelas:
        print("nada passa atrás da cabeça: sem máscara"); return
    base = C.EDIT / f"base_{'final' if C.ARGS.final else 'preview'}.mov"
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in janelas)
    m = C.EDIT / "masks"
    shutil.rmtree(m, ignore_errors=True)
    (m / "src").mkdir(parents=True)
    # -frame_pts: o nome do arquivo é o número do quadro na base (é como o compor procura)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(base), "-vf", f"select='{sel}',scale=540:960",
                    "-vsync", "0", "-frame_pts", "1", str(m / "src" / "f_%06d.png")], check=True)
    subprocess.run([str(BIN), str(m / "src"), str(m / "out")], check=True)
    print(f"{len(list((m / 'out').glob('*.png')))} máscaras em {m / 'out'}  (janelas {janelas})")


if __name__ == "__main__":
    main()
