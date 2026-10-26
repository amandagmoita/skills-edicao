#!/usr/bin/env python3
"""rosto_segmentos.py — mede o rosto EM CADA SEGMENTO do corte e grava em corte.json.

Uso:
  python3 rosto_segmentos.py <pasta_projeto>

O cortar.py enquadra pelo rosto MEDIANO do vídeo cru inteiro. Isso basta pro recorte 9:16,
mas não pra posicionar legenda, número e gancho: gravando frase por frase a pessoa muda de
posição entre tomadas (inclina, chega perto) e a legenda, calculada pelo rosto médio, caía
no queixo ou na boca. Aqui cada segmento ganha o próprio rosto, medido no base_corte.mp4
(3 quadros por segmento, mediana pelo Apple Vision), já em pixels do quadro 1080x1920.
O cortar.py chama este script no fim; rodar sozinho serve pra projeto antigo.
"""
import json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920


def main():
    P = sys.argv[1]
    visao = os.path.join(AQUI, "bin", "visao")
    corte_f = os.path.join(P, "corte.json")
    corte = json.load(open(corte_f))
    base = os.path.join(P, "base_corte.mp4")
    tmp = os.path.join(P, "_rosto_seg")
    shutil.rmtree(tmp, ignore_errors=True)
    medidos = 0
    for k, s in enumerate(corte["segmentos"]):
        d = os.path.join(tmp, str(k)); os.makedirs(d)
        dur = s["fim"] - s["ini"]
        for n, frac in enumerate((0.25, 0.5, 0.75)):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s['ini'] + dur * frac:.3f}", "-i", base,
                            "-frames:v", "1", "-vf", "scale=540:-2", os.path.join(d, f"{n}.jpg")], check=True)
        saida = os.path.join(d, "r.json")
        r = subprocess.run([visao, "rosto", d, saida], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(saida):
            continue  # sem rosto: fica o da mediana do cru
        f = json.load(open(saida))
        s["rosto"] = {"x": round(f["x"] * W, 1), "y": round(f["y"] * H, 1),
                      "w": round(f["w"] * W, 1), "h": round(f["h"] * H, 1)}
        medidos += 1
    shutil.rmtree(tmp, ignore_errors=True)
    json.dump(corte, open(corte_f, "w"), indent=1)
    print(f"rosto medido em {medidos}/{len(corte['segmentos'])} segmentos -> corte.json")


if __name__ == "__main__":
    sys.exit(main())
