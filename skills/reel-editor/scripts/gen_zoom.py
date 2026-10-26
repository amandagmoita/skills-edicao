#!/usr/bin/env python3
"""
gen_zoom.py — gera o filtro ffmpeg `zoompan` com punch-in zooms suaves.

Uso:
  python3 gen_zoom.py windows.json [--amt 0.08] [--ramp 0.25] [--fps 30] [--w 1080] [--h 1920]

windows.json: lista de janelas [start, end] em segundos, na timeline do CORTE final.
  Ex.: [[0.3,1.6],[19.0,20.2],[25.4,26.6],[48.2,54.2]]

Saída (stdout): a string do filtro. Use assim (mantendo o áudio):
  ZP=$(python3 gen_zoom.py windows.json)
  ffmpeg -y -i in.mp4 -vf "$ZP" -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy out.mp4

Cada janela faz um trapézio (sobe em RAMP s, segura, desce em RAMP s) somado via max().
"""
import sys, json, argparse

def trap(a, b, ramp, fps):
    t = f"(on/{fps})"
    return (f"clip(min(min(({t}-{a})/{ramp}\\,({b}-{t})/{ramp})\\,1)\\,0\\,1)")

def nested_max(items):
    if len(items) == 1:
        return items[0]
    return f"max({items[0]}\\,{nested_max(items[1:])})"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("windows")
    ap.add_argument("--amt", type=float, default=0.08)
    ap.add_argument("--ramp", type=float, default=0.25)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    a = ap.parse_args()
    wins = json.load(open(a.windows))
    if not wins:
        # sem janelas: zoom neutro (identidade)
        print(f"zoompan=z=1:d=1:s={a.w}x{a.h}:fps={a.fps}")
        return
    traps = [trap(x[0], x[1], a.ramp, a.fps) for x in wins]
    z = f"1+{a.amt}*{nested_max(traps)}"
    print(f"zoompan=z='{z}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={a.w}x{a.h}:fps={a.fps}")

if __name__ == "__main__":
    main()
