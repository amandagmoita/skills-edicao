"""conferir.py — medição antes de mostrar ao usuário (não dá pra ouvir: tudo é medido).

Uso: $PY conferir.py <edit_dir> <video.mp4>
Mede:
  1. silêncios >= 0,2 s na base (fala contínua: o maior deve ficar perto de 0,25 s)
  2. cada emenda. Corte com sobreposição (padrão do pack, base_info["corte"] == "sobreposto"):
     o som da fala anterior continua 140-180 ms por baixo da seguinte e o salto no ponto do corte
     fica perto do da própria voz (sem estalo). Base antiga: RMS em ±5 ms do corte < -40 dB.
     Junta colada (fala contínua) nos dois casos: a base tem que ser a própria fonte em volta dela.
  3. duração do vídeo x soma dos trechos, resolução, loudness (-14 LUFS) e pico real
  4. folha de contato 1 quadro/s em verify/folha.jpg — LER antes de entregar
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def audio(p: Path, sr: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(float) / 32768


def main() -> None:
    edit, video = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    info = json.loads((edit / "base_info.json").read_text())
    base = edit / info["base"]
    durs = info["duracoes"]

    x = audio(base, 16000)
    n = len(x) // 160
    db = 20 * np.log10(np.sqrt((x[: n * 160].reshape(n, 160) ** 2).mean(1)) + 1e-9)
    lim = np.percentile(db, 90) - 24
    q, runs, i = db < lim, [], 0
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            if (j - i) * 0.01 >= 0.2:
                runs.append((round(i * 0.01, 2), round((j - i) * 0.01, 2)))
            i = j
        else:
            i += 1
    print(f"1. silêncios >= 0,2 s na base: {len(runs)}  maior: {max([d for _, d in runs], default=0):.2f}s  {runs}")

    y = audio(base, 48000)
    edl = json.loads((edit / "edl.json").read_text())
    rs = edl["ranges"]
    fonte = Path(next(iter(edl["sources"].values())))
    src = audio(fonte, 48000) if any(r.get("colado") for r in rs) else None
    if info.get("corte") == "sobreposto":
        plano = info["plano"]
        fora, estalos, quebradas, sob, n_col = [], [], [], [], 0
        for k in range(len(plano) - 1):
            a, b = plano[k], plano[k + 1]
            corte = b["saida"]
            if rs[k + 1].get("colado"):
                n_col += 1
                c, s0 = int(round(b["som_saida"] * 48000)), int(round(b["a0"] * 48000))
                w_, f_ = y[c - 960: c + 960], src[s0 - 960: s0 + 960]
                erro = np.abs(w_ - f_).mean() / max(np.abs(f_).mean(), 0.01)
                if erro > 0.01:
                    quebradas.append((k, round(corte, 2), round(erro, 3)))
                continue
            por_baixo = 1000 * (a["som_saida"] + a["a1"] - a["a0"] - corte)
            sob.append(round(por_baixo))
            if not 120 <= por_baixo <= 200:
                fora.append((k, round(corte, 2), round(por_baixo)))
            c = int(round(corte * 48000))
            salto = np.abs(np.diff(y[c - 144: c + 144])).max()
            voz = np.abs(np.diff(y[c + 480: c + 4800])).max()
            if salto > max(0.05, 1.5 * voz):
                estalos.append((k, round(corte, 2), round(float(salto), 3)))
        print(f"2. emendas sobrepostas: {len(sob)} | som da anterior por baixo {min(sob, default=0)}-{max(sob, default=0)} ms"
              f" (fora de 120-200: {fora or 'nenhuma'}) | estalo: {estalos or 'nenhum'}"
              + (f" | juntas coladas fora da fonte: {quebradas or 'nenhuma'}  ({n_col} coladas)" if n_col else ""))
    else:
        ini_src = float(rs[0]["start"]) if rs else 0.0
        ruins, quebradas, n_col = [], [], 0
        for k, b in enumerate(itertools.accumulate(durs[:-1])):
            c = int(round(b * 48000))
            ini_src = ini_src + durs[k] if rs[k + 1].get("colado") else float(rs[k + 1]["start"])
            if rs[k + 1].get("colado"):
                # junta colada (fala contínua, sem fade): a base tem que ser a própria fonte em volta dela
                n_col += 1
                s = int(round(ini_src * 48000))
                a, f = y[c - 960: c + 960], src[s - 960: s + 960]
                erro = np.abs(a - f).mean() / max(np.abs(f).mean(), 0.01)   # piso: junta em silêncio
                if erro > 0.01:
                    quebradas.append((k, round(b, 2), round(erro, 3)))
                continue
            w = y[max(0, c - 240): c + 240]
            r = 20 * np.log10(np.sqrt((w ** 2).mean()) + 1e-9)
            if r > -40:
                ruins.append((k, round(b, 2), round(r, 1)))
        print(f"2. (base antiga, sem sobreposição) emendas com som no ponto de corte: {ruins or 'nenhuma'}"
              f"  ({len(durs) - 1 - n_col} emendas)"
              + (f" | juntas coladas fora da fonte: {quebradas or 'nenhuma'}  ({n_col} coladas)" if n_col else ""))

    pr = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                                  "-of", "compact", str(video)]).decode().strip()
    lu = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128=peak=true",
                         "-f", "null", "-"], capture_output=True, text=True).stderr
    resumo = lu[lu.rfind("Summary"):]
    integ = [l.strip() for l in resumo.splitlines() if l.strip().startswith(("I:", "Peak:"))]
    print(f"3. soma dos trechos {sum(durs):.3f}s | {pr.replace(chr(10), ' | ')} | {' '.join(integ)}")

    folha = edit / "verify" / "folha.jpg"
    folha.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    "fps=1,scale=150:-2,drawtext=fontfile=/System/Library/Fonts/Menlo.ttc:text='%{pts\\:hms}':"
                    "x=3:y=3:fontsize=12:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=14x7",
                    "-frames:v", "1", str(folha)], check=True)
    print(f"4. folha de contato: {folha}")


if __name__ == "__main__":
    main()
