#!/usr/bin/env python3
"""
gen_sfx.py — sintetiza SFX (whoosh/pop/ding/key) no ffmpeg e/ou monta a trilha de SFX
posicionando cada efeito num tempo da timeline do corte.

Não há SFX locais no HyperFrames (só manifest) → sintetizamos com lavfi.

1) Sintetizar os arquivos base (uma vez por projeto):
     python3 gen_sfx.py --synth <sfxdir>
   gera whoosh.wav, pop.wav, ding.wav, key.wav em <sfxdir>.

2) Montar a trilha a partir de um JSON de eventos:
     python3 gen_sfx.py --events events.json --sfxdir <sfxdir> --out sfx_track.wav --total 54.4
   events.json: [{"t": 0.0, "file": "whoosh.wav", "vol": 0.9}, {"t": 5.5, "file": "pop.wav"}, ...]

Convenção de uso: whoosh nas transições de cena; pop nas entradas de elementos;
ding nas viradas positivas; key (repetido) no typewriter das UIs.
Depois mixe no vídeo final:  [voz][sfx]amix=inputs=2:normalize=0,alimiter=limit=0.95
"""
import os, json, argparse, subprocess

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg erro:\n" + r.stderr[-1200:])

def synth(sfxdir):
    os.makedirs(sfxdir, exist_ok=True)
    j = lambda f: os.path.join(sfxdir, f)
    # whoosh: ruído rosa filtrado com swell
    run(["ffmpeg","-y","-f","lavfi","-i","anoisesrc=d=0.5:c=pink:a=0.6",
         "-af","bandpass=f=1100,afade=t=in:st=0:d=0.07,afade=t=out:st=0.16:d=0.34,volume=1.8",
         "-ar","48000","-ac","2", j("whoosh.wav")])
    # pop: sine curto com decay
    run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=620:duration=0.11",
         "-af","afade=t=out:st=0:d=0.11:curve=exp,volume=0.55","-ar","48000","-ac","2", j("pop.wav")])
    # ding: dois sines com decay exponencial
    run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=1245:duration=0.6",
         "-f","lavfi","-i","sine=frequency=1865:duration=0.6",
         "-filter_complex","[0][1]amix=inputs=2,afade=t=out:st=0.04:d=0.56:curve=exp,volume=0.7",
         "-ar","48000","-ac","2", j("ding.wav")])
    # key: clique curto
    run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=1600:duration=0.035",
         "-af","afade=t=out:st=0:d=0.035,volume=0.4","-ar","48000","-ac","2", j("key.wav")])
    print("SFX sintetizados em", sfxdir)

def build(events_path, sfxdir, out, total):
    events = json.load(open(events_path))
    inputs, filters = [], []
    for i, e in enumerate(events):
        inputs += ["-i", os.path.join(sfxdir, e["file"])]
        ms = int(round(e["t"]*1000)); vol = e.get("vol", 1.0)
        filters.append(f"[{i}]adelay={ms}:all=1,volume={vol}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(events)))
    fc = ";".join(filters) + f";{mix}amix=inputs={len(events)}:normalize=0:dropout_transition=0,alimiter=limit=0.95,apad,atrim=0:{total}[out]"
    run(["ffmpeg","-y"] + inputs + ["-filter_complex", fc, "-map","[out]","-ar","48000","-ac","2", out])
    print(f"trilha SFX ({len(events)} eventos) -> {out}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", metavar="SFXDIR")
    ap.add_argument("--events"); ap.add_argument("--sfxdir"); ap.add_argument("--out")
    ap.add_argument("--total", type=float, default=60.0)
    a = ap.parse_args()
    if a.synth:
        synth(a.synth)
    if a.events:
        build(a.events, a.sfxdir, a.out, a.total)

if __name__ == "__main__":
    main()
