#!/usr/bin/env python3
"""transcrever.py — transcrição por palavra com whisper.cpp local (large-v3).

Uso:
  python3 transcrever.py <video> <pasta_projeto> [--idioma pt]

Gera em <pasta_projeto>:
  audio16k.wav       áudio mono 16 kHz
  whisper.json       saída bruta do whisper-cli
  palavras.json      [{"w": "palavra", "s": 1.23, "e": 1.56}, ...] em segundos do vídeo CRU
"""
import argparse, json, os, re, subprocess, sys

WHISPER = os.path.expanduser("~/.cache/hyperframes/whisper/whisper.cpp/build/bin/whisper-cli")
MODELO = os.path.expanduser("~/.cache/hyperframes/whisper/models/ggml-large-v3.bin")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("projeto")
    ap.add_argument("--idioma", default="pt")
    a = ap.parse_args()
    os.makedirs(a.projeto, exist_ok=True)
    wav = os.path.join(a.projeto, "audio16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)

    base = os.path.join(a.projeto, "whisper")
    # --dtw large.v3 (com PONTO) é o preset certo; o hífen quebra (aprendizado da /reel-editor)
    subprocess.run([WHISPER, "--model", MODELO, "--language", a.idioma, "--dtw", "large.v3",
                    "--max-len", "1", "--split-on-word", "--output-json-full",
                    "--output-file", base, "--file", wav, "--no-prints"], check=True)

    dados = json.load(open(base + ".json"))
    palavras = []
    for seg in dados.get("transcription", []):
        txt = seg.get("text", "").strip()
        if not txt or re.fullmatch(r"\[.*\]|\(.*\)", txt):
            continue
        s = seg["offsets"]["from"] / 1000.0
        e = seg["offsets"]["to"] / 1000.0
        # pontuação solta gruda na palavra anterior
        if palavras and re.fullmatch(r"[\.,!?;:…]+", txt):
            palavras[-1]["w"] += txt
            continue
        palavras.append({"w": txt, "s": round(s, 3), "e": round(max(e, s + 0.05), 3)})

    out = os.path.join(a.projeto, "palavras.json")
    json.dump(palavras, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(palavras)} palavras -> {out}")
    print(" ".join(p["w"] for p in palavras)[:600])


if __name__ == "__main__":
    sys.exit(main())
