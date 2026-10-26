#!/usr/bin/env python3
"""transcrever_corte.py — refaz palavras_corte.json transcrevendo o base_corte.mp4 EM PEDAÇOS.

Uso:
  python3 transcrever_corte.py <pasta_projeto> [--min 1.5] [--trocar "branco?=branco.,clode=Claude"]

Por que existe: com gravação frase por frase (várias tomadas), os tempos do whisper no cru
não servem pro corte (o whisper funde tomadas e empilha palavras de fragmento), e transcrever
o corte inteiro de uma vez DESLIZA: num corte de 98 s ele chegou a marcar palavra em 115 s.
Aqui cada TOMADA (fronteira de segmento que não é divisão de zoom: pausa ou emenda) é
transcrita sozinha e recebe o deslocamento; tomada com menos de --min s junta com a seguinte.

--trocar: correções de texto "errado=certo" separadas por vírgula, aplicadas na palavra
          (ou sequência de palavras) exata. Ex.: nome de produto que o whisper erra.
Também espalha palavras que o whisper empilha no mesmo instante (início de frase) e PRENDE
cada palavra no início real da voz: o whisper gruda as primeiras palavras no começo do pedaço
mesmo quando ali é silêncio, e a legenda aparecia 0,3–0,6 s antes da fala.
"""
import argparse, json, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortar import energia

WHISPER = os.path.expanduser("~/.cache/hyperframes/whisper/whisper.cpp/build/bin/whisper-cli")
MODELO = os.path.expanduser("~/.cache/hyperframes/whisper/models/ggml-large-v3.bin")


def transcreve(wav, base):
    subprocess.run([WHISPER, "--model", MODELO, "--language", "pt", "--dtw", "large.v3",
                    "--max-len", "1", "--split-on-word", "--output-json-full",
                    "--output-file", base, "--file", wav, "--no-prints"], check=True,
                   capture_output=True)
    out = []
    for seg in json.load(open(base + ".json")).get("transcription", []):
        txt = seg.get("text", "").strip()
        if not txt or re.fullmatch(r"\[.*\]|\(.*\)", txt):
            continue
        s, e = seg["offsets"]["from"] / 1000.0, seg["offsets"]["to"] / 1000.0
        if out and re.fullmatch(r"[\.,!?;:…]+", txt):
            out[-1]["w"] += txt
            continue
        out.append({"w": txt, "s": s, "e": max(e, s + 0.05)})
    return out


def espalha(ps):
    k = 0
    while k < len(ps):
        j = k
        while j + 1 < len(ps) and ps[j + 1]["s"] - ps[k]["s"] < 0.03:
            j += 1
        if j > k:
            a = ps[k]["s"]
            b = ps[j + 1]["s"] if j + 1 < len(ps) and ps[j + 1]["s"] - ps[j]["e"] < 0.1 else ps[j]["e"]
            passo = (b - a) / (j - k + 1)
            for m in range(j - k + 1):
                ps[k + m]["s"], ps[k + m]["e"] = a + m * passo, a + (m + 1) * passo
        k = j + 1


def troca(ps, regras):
    for errado, certo in regras:
        e, c = errado.split(), certo.split()
        k = 0
        while k + len(e) <= len(ps):
            if [p["w"] for p in ps[k:k + len(e)]] == e:
                novo = {"w": " ".join(c), "s": ps[k]["s"], "e": ps[k + len(e) - 1]["e"]}
                ps[k:k + len(e)] = [novo]
            k += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto")
    ap.add_argument("--min", type=float, default=1.5)
    ap.add_argument("--trocar", default="")
    a = ap.parse_args()
    P = a.projeto
    segs = json.load(open(os.path.join(P, "corte.json")))["segmentos"]

    # fronteiras boas = fim de segmento que NÃO é seguido de divisão de zoom colada
    # (corte.json não guarda "colado": divisão de zoom é quando o próximo começa onde este acaba no cru)
    # um pedaço por TOMADA (fecha em toda emenda real), juntando tomada curta (< --min s) com a
    # seguinte: pedaço longo desliza e engole a última palavra; pedaço de 0,3 s alucina
    pedacos, ini = [], segs[0]["ini"]
    for k, s in enumerate(segs):
        prox = segs[k + 1] if k + 1 < len(segs) else None
        colado = prox is not None and abs(prox["in"] - s["out"]) < 1e-3
        if prox is None or (not colado and s["fim"] - ini >= a.min):
            pedacos.append((ini, s["fim"]))
            if prox:
                ini = prox["ini"]
    palavras = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, (t0, t1) in enumerate(pedacos):
            wav = os.path.join(tmp, f"{n}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}",
                            "-i", os.path.join(P, "base_corte.mp4"), "-vn", "-ac", "1", "-ar", "16000",
                            # 0,6 s de silêncio no fim: com o corte colado na fala o whisper
                            # engolia a última palavra do pedaço ("cliente.", "de caso.")
                            "-af", "apad=pad_dur=0.6", wav],
                           check=True)
            ps = transcreve(wav, os.path.join(tmp, str(n)))
            espalha(ps)
            for p in ps:
                palavras.append({"w": p["w"], "s": round(t0 + p["s"], 3),
                                 "e": round(min(t0 + p["e"], t1), 3)})
    # prende no início da voz: palavra que começa em silêncio anda até a 1ª janela com voz
    wav = os.path.join(P, "_base16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(P, "base_corte.mp4"),
                    "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    db, jan, voz = energia(wav)
    os.remove(wav)
    tem_voz = lambda t0, t1: any(db[k] > voz for k in range(int(t0 / jan), min(int(t1 / jan) + 1, len(db))))
    for k, p in enumerate(palavras):
        if tem_voz(p["s"], p["s"] + 0.06):
            continue
        limite = palavras[k + 1]["e"] if k + 1 < len(palavras) else p["e"] + 0.5
        j = int(p["s"] / jan)
        while j < len(db) and j * jan < limite and db[j] <= voz:
            j += 1
        if j * jan < limite:
            p["s"] = round(j * jan, 3)
            p["e"] = round(max(p["e"], p["s"] + 0.08), 3)
    # emenda entre tomadas: o whisper estica a última palavra da tomada anterior por cima da
    # emenda e a 1ª palavra da tomada nova chegava 0,2–0,45 s atrasada. Na emenda a palavra
    # anterior TERMINA ali e a seguinte começa onde a voz começa.
    for k, sg in enumerate(segs):
        if k == 0 or abs(sg["in"] - segs[k - 1]["out"]) < 1e-3:
            continue  # divisão de zoom no meio da fala, não é emenda
        b = sg["ini"]
        prox = next((i for i, p in enumerate(palavras) if p["s"] >= b - 0.02), None)
        if prox is None:
            continue
        j = int(b / jan)
        while j < len(db) and db[j] <= voz and j * jan < palavras[prox]["s"]:
            j += 1
        onset = j * jan
        if prox > 0 and palavras[prox - 1]["e"] > b:
            palavras[prox - 1]["e"] = round(b, 3)
        if palavras[prox]["s"] > onset + 0.05:
            palavras[prox]["s"] = round(onset, 3)
    for k in range(len(palavras) - 1):  # manter a ordem depois de empurrar
        if palavras[k + 1]["s"] < palavras[k]["s"]:
            palavras[k + 1]["s"] = palavras[k]["s"]
    regras = [tuple(x.split("=", 1)) for x in a.trocar.split(",") if "=" in x]
    troca(palavras, regras)
    for i, p in enumerate(palavras):
        p["i"] = i
    json.dump(palavras, open(os.path.join(P, "palavras_corte.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(pedacos)} pedaços, {len(palavras)} palavras -> palavras_corte.json")
    print(" ".join(f"{p['w']}@{p['s']:.1f}" for p in palavras))


if __name__ == "__main__":
    sys.exit(main())
