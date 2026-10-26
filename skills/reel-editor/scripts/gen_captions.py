#!/usr/bin/env python3
"""
gen_captions.py — gera legendas karaokê (.ass, uma palavra por vez, com "pop")
+ .srt por frases, remapeando os timestamps do vídeo ORIGINAL para o CORTE final.

Uso:
  python3 gen_captions.py \
    --words words.json \           # JSON do whisper-cli (--output-json-full): chave "transcription"
    --segments segments.json \     # mapa de corte: [[src_in, src_out, out_start], ...] (s)
    --total 54.4 \                 # duração do corte final (s)
    --out-ass legendas.ass --out-srt legendas.srt \
    [--font Poppins] [--fontpx 118] [--marginv 300] [--box-alpha 0x73] [--box-rgb 2B2B2B]

Depois renderize a CAMADA TRANSPARENTE (alpha correto):
  ffmpeg -y -f lavfi -i "color=c=black:s=1080x1920:r=30:d=<total>" \
    -vf "format=rgba,colorchannelmixer=aa=0,subtitles=legendas.ass:fontsdir=fonts:alpha=1,format=yuva444p10le" \
    -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le legendas_overlay.mov

Whisper recomendado (PT, palavras limpas):
  whisper-cli --model ggml-large-v3.bin --language pt --dtw large.v3 --max-len 1 \
    --split-on-word --output-json-full --output-file words
"""
import json, re, argparse

def remap(ws, we, segs):
    for sin, sout, ostart in segs:
        if sin <= ws < sout:
            a = ws - sin + ostart
            b = min(we, sout) - sin + ostart
            return a, max(b, a + 0.05)
    return None

def clean(w):
    return re.sub(r'[,.;:!?]+$', '', w.strip()).upper()

def ts_ass(t):
    h = int(t//3600); t -= h*3600; m = int(t//60); t -= m*60; s = int(t); cs = int(round((t-s)*100))
    if cs == 100: s += 1; cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def ts_srt(t):
    h = int(t//3600); t -= h*3600; m = int(t//60); t -= m*60; s = int(t); ms = int(round((t-s)*1000))
    if ms == 1000: s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--out-ass", required=True)
    ap.add_argument("--out-srt", required=True)
    ap.add_argument("--font", default="Poppins")
    ap.add_argument("--fontpx", type=int, default=118)
    ap.add_argument("--marginv", type=int, default=300)
    ap.add_argument("--box-alpha", default="73")   # ASS: 00=opaco, FF=transparente (73 ~= 55% opaco)
    ap.add_argument("--box-rgb", default="2B2B2B") # cinza
    a = ap.parse_args()

    segs = json.load(open(a.segments))
    d = json.load(open(a.words))
    words = []
    for s in d.get("transcription", []):
        t = s.get("text", "").strip()
        if not t: continue
        ws = s["offsets"]["from"]/1000.0; we = s["offsets"]["to"]/1000.0
        m = remap(ws, we, segs)
        if m: words.append({"a": m[0], "b": m[1], "text": t})
    words.sort(key=lambda w: w["a"])

    # cor da caixa em formato ASS &HAABBGGRR (BBGGRR = invertido de RRGGBB)
    rr, gg, bb = a.box_rgb[0:2], a.box_rgb[2:4], a.box_rgb[4:6]
    box = f"&H{a.box_alpha}{bb}{gg}{rr}"

    ass = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Kar,{a.font},{a.fontpx},&H00FFFFFF,&H00FFFFFF,{box},{box},-1,0,0,0,100,100,1,0,3,16,0,2,80,80,{a.marginv},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text",
    ]
    for i, w in enumerate(words):
        a0 = w["a"]
        nxt = words[i+1]["a"] if i+1 < len(words) else min(w["b"]+0.4, a.total)
        end = nxt if (nxt - a0) <= 1.2 else min(a0+1.2, a.total)
        eff = r"{\fad(40,0)\fscx116\fscy116\t(0,130,\fscx100\fscy100)}"
        ass.append(f"Dialogue: 0,{ts_ass(a0)},{ts_ass(end)},Kar,,0,0,,{eff}{clean(w['text'])}")
    open(a.out_ass, "w").write("\n".join(ass))

    # SRT por frases
    phrases = []; cur = []
    for i, w in enumerate(words):
        cur.append(w)
        brk = bool(re.search(r'[,.;:!?]$', w["text"])) or len(cur) >= 6
        gap = (i+1 < len(words) and words[i+1]["a"] - w["b"] > 0.5)
        if brk or gap or i == len(words)-1:
            phrases.append((cur[0]["a"], cur[-1]["b"], " ".join(clean(x["text"]) for x in cur)))
            cur = []
    srt = []
    for idx, (x, y, text) in enumerate(phrases, 1):
        srt += [str(idx), f"{ts_srt(x)} --> {ts_srt(y)}", text, ""]
    open(a.out_srt, "w").write("\n".join(srt))
    print(f"palavras={len(words)} frases={len(phrases)} -> {a.out_ass}, {a.out_srt}")

if __name__ == "__main__":
    main()
