"""cortar.py — corte de fala contínua a partir das tomadas escolhidas no mapa.json.

Uso (sempre com o Python do video-use):
  PY=~/Developer/video-use/.venv/bin/python
  $PY cortar.py <edit_dir> frases          # lista as frases com tempo (pra escolher as tomadas)
  $PY cortar.py <edit_dir> edl             # mapa.json["tomadas"] → edl.json (bordas na voz, pausas viram corte)
  $PY cortar.py <edit_dir> base [--final]  # extrai os trechos e junta em base_preview.mov (ou base_final.mov)

Lê:  <edit>/mapa.json, <edit>/transcripts/<fonte>.json (Scribe do video-use)
Gera: edl.json, clips_*/seg_NN.mov, base_*.mov, base_info.json (fps + duração de cada trecho),
      words_out.json (cada palavra mantida na linha do tempo de saída, com a tomada de origem)

CORTE COM SOBREPOSIÇÃO (padrão do pack pra toda edição de Reels):
  em cada emenda o vídeo da fala A sai 0,10 s antes da voz de A acabar, o áudio de A continua
  por baixo de B até 0,06 s depois da voz (fade 80 ms) e B entra 0,04 s antes da própria voz.
  A regra mora em ~/.claude/padroes-edicao/corte_sobreposto.py (+ corte-sobreposto.md): este
  arquivo só chama o módulo. Mudou a regra? Muda lá, nunca aqui.

Por que cada coisa (bugs reais achados na prática):
  - escala fixa 1080x1920: o is_portrait_source do video-use usa `stream_side_data=rotation`, que o
    ffprobe 6.0 recusa; o erro é engolido e o vertical sai 1920x3414.
  - cada trecho tem N quadros exatos e áudio PCM do mesmo tamanho, cortados por FILTRO
    (trim/atrim). Com AAC por trecho o concat acumula 0,2-0,6 s de deriva entre voz, vídeo e
    legenda; com -frames:v o ffmpeg encerra o áudio junto com o último quadro e perde 2-20 ms.
  - "tomada" (grupo) é a unidade do mapa: quando uma pausa interna vira corte, a tomada vira
    vários trechos, mas efeitos e legendas continuam ancorados nela.
"""

from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.home() / "Developer/video-use/helpers"))
import render as R  # noqa: E402
from grade import auto_grade_for_clip  # noqa: E402

sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import corte_sobreposto as CS  # noqa: E402

# mapa.json["corte"] sobrescreve qualquer um destes; "limiar_voz" (dB) fixa o limiar em vez do adaptativo
PADRAO = {"pad_in": 0.04, "pad_out": 0.06, "split_gap": 0.22,
          "zoom_alternado": True, "zoom_crop": [0.87, 0.065, 0.035]}


# ------------------------------------------------------------------ util
def carrega(edit: Path) -> tuple[dict, Path, dict]:
    mapa = json.loads((edit / "mapa.json").read_text())
    fonte = Path(mapa["fonte"])
    if not fonte.is_absolute():
        fonte = (edit.parent / fonte).resolve()
    cfg = {**PADRAO, **mapa.get("corte", {})}
    return mapa, fonte, cfg


def palavras(edit: Path, fonte: Path) -> list[dict]:
    tr = json.loads((edit / "transcripts" / f"{fonte.stem}.json").read_text())
    return [w for w in tr["words"] if w.get("type") == "word"]


def duracao(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(p)]).decode().strip())


def fps_fonte(fonte: Path) -> Fraction:
    r = R.probe_source_fps(fonte) or "24"
    return Fraction(r)


def rms_db(fonte: Path, t0: float, t1: float, hop: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t0):.3f}", "-i", str(fonte),
                          "-t", f"{t1 - max(0, t0):.3f}", "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(float) / 32768
    w = int(16000 * hop)
    n = len(x) // w
    db = 20 * np.log10(np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(1)) + 1e-9)
    return max(0, t0) + np.arange(n) * hop, db


def limiar_voz(fonte: Path) -> float:
    """Voz = acima de p90 - 22 dB da fonte inteira. No 1º vídeo deu -33 dB: a respiração
    antes da frase (-35/-40 dB) fica de fora e o 's' final que decai (-28/-32 dB) fica dentro."""
    _, db = rms_db(fonte, 0, duracao(fonte))
    return float(np.percentile(db, 90) - 22)


def _anda(db: np.ndarray, i: int, passo: int, lim: float, max_queda: int = 4) -> int:
    ultimo, queda, j = i, 0, i
    while 0 <= j + passo < len(db):
        j += passo
        if db[j] > lim:
            ultimo, queda = j, 0
        else:
            queda += 1
            if queda > max_queda:
                break
    return ultimo


def refina(fonte: Path, ini: float, fim: float, lim: float) -> tuple[float, float]:
    """Encosta as bordas na voz real (o Scribe deriva 50-100 ms). Só anda PRA FORA da palavra,
    no máx. 0,25 s, e só enquanto há voz contínua."""
    t, db = rms_db(fonte, ini - 0.25, ini)
    on = ini
    if len(db) and db[-1] > lim:
        on = float(t[_anda(db, len(db) - 1, -1, lim)])
    t, db = rms_db(fonte, fim, fim + 0.25)
    off = fim
    if len(db) and db[0] > lim:
        off = float(t[_anda(db, 0, 1, lim)] + 0.01)
    return on, off


# ------------------------------------------------------------------ comandos
def cmd_frases(edit: Path) -> None:
    _, fonte, _ = carrega(edit) if (edit / "mapa.json").exists() else ({}, None, {})
    if fonte is None:
        tr = sorted((edit / "transcripts").glob("*.json"))[0]
        fonte = Path(tr.stem)
    ws = palavras(edit, fonte)
    linha, ultimo = [], None
    for w in ws:
        if ultimo is not None and w["start"] - ultimo >= 0.5:
            print(" ".join(linha)); linha = []
        linha.append(f"{w['text']}[{w['start']:.2f}-{w['end']:.2f}]")
        ultimo = w["end"]
    print(" ".join(linha))


def cmd_edl(edit: Path) -> None:
    mapa, fonte, cfg = carrega(edit)
    ws = palavras(edit, fonte)
    total_fonte = duracao(fonte)
    lim = float(cfg["limiar_voz"]) if "limiar_voz" in cfg else limiar_voz(fonte)
    trechos = []
    for g, tomada in enumerate(mapa["tomadas"]):
        s, e = float(tomada[0]), float(tomada[1])
        bloco = tomada[2] if len(tomada) > 2 else ""
        tw = [w for w in ws if w["end"] > s + 1e-3 and w["start"] < e - 1e-3]
        if not tw:
            sys.exit(f"tomada {g} ({s}-{e}) sem palavras na transcrição")
        partes, cur = [], [tw[0]]
        for w in tw[1:]:
            if w["start"] - cur[-1]["end"] >= cfg["split_gap"]:
                partes.append(cur); cur = [w]
            else:
                cur.append(w)
        partes.append(cur)
        for pi, parte in enumerate(partes):
            ps = max(s, parte[0]["start"]) if pi == 0 else parte[0]["start"]
            pe = min(e, parte[-1]["end"]) if pi == len(partes) - 1 else parte[-1]["end"]
            on, off = refina(fonte, ps, pe, lim)
            voz_ini, voz_fim = CS.bordas_finas(fonte, on, off, lim - CS.ABAIXO_DB)
            a, b = max(0.0, on - cfg["pad_in"]), min(total_fonte, off + cfg["pad_out"])
            a_min, a_max = 0.0, total_fonte
            antes = [w for w in ws if w["end"] <= ps + 1e-3]
            depois = [w for w in ws if w["start"] >= pe - 1e-3 and w["start"] > ps]
            if antes:
                a_min = antes[-1]["end"] + 0.02
                a = max(a, a_min)
            if depois:
                a_max = depois[0]["start"] - 0.02
                b = min(b, a_max)
            trechos.append({"source": fonte.stem, "start": round(a, 3), "end": round(b, 3), "beat": bloco,
                            "grupo": g, "zoom": cfg["zoom_alternado"] and g % 2 == 1,
                            "voz_ini": round(max(voz_ini, a_min), 3), "voz_fim": round(min(voz_fim, a_max), 3),
                            "a_min": round(a_min, 3), "a_max": round(a_max, 3),
                            "quote": " ".join(w["text"] for w in parte)})
    # pausa que o Scribe viu mas a voz não tem (bordas se cruzam): junta de volta
    unidos = [trechos[0]]
    for r in trechos[1:]:
        u = unidos[-1]
        if r["grupo"] == u["grupo"] and r["start"] < u["end"] + 0.08:
            u["end"], u["quote"] = max(u["end"], r["end"]), u["quote"] + " " + r["quote"]
            u["voz_fim"], u["a_max"] = max(u["voz_fim"], r["voz_fim"]), r["a_max"]
        else:
            unidos.append(r)
    # tomadas que se tocam na fonte (fala contínua, sem pausa entre elas): as folgas se cruzariam e
    # repetiriam 20-40 ms de voz, e o fade de cada trecho abriria um buraco no meio da fala.
    # Encontram-se num ponto só, no meio do vão entre as palavras; `colado` tira o fade da junta.
    for u, r in zip(unidos, unidos[1:]):
        if r["start"] < u["end"] + 0.08:
            c = round((u["end"] + r["start"]) / 2, 3)
            u["end"] = r["start"] = u["voz_fim"] = r["voz_ini"] = c
            r["colado"] = True
    total = sum(r["end"] - r["start"] for r in unidos)
    (edit / "edl.json").write_text(json.dumps({
        "version": 1, "sources": {fonte.stem: str(fonte)}, "ranges": unidos, "grade": "auto-once",
        "overlays": [], "total_duration_s": round(total, 3)}, indent=2, ensure_ascii=False))
    for i, r in enumerate(unidos):
        print(f"[{i:02d}] {r['start']:7.2f}-{r['end']:7.2f} ({r['end'] - r['start']:4.2f}s) g{r['grupo']:02d} "
              f"{'Z' if r['zoom'] else ' '}{'=' if r.get('colado') else ' '}{r['beat']:8s} {r['quote'][:44]}")
    print(f"limiar de voz {lim:.1f} dB · total {total:.2f}s em {len(unidos)} trechos")


def extrai_video(fonte: Path, v0: Fraction, n: int, fps: Fraction, vf: str, out: Path, final: bool) -> None:
    """n quadros exatos a partir do quadro v0 (já na grade). -ss meio quadro antes + trim por
    quadro: sem isso o ffmpeg pega o quadro seguinte e a imagem fica 1 quadro adiantada."""
    vf = f"{vf},trim=end_frame={n},setpts=PTS-STARTPTS"
    preset, crf = ("fast", "18") if final else ("medium", "22")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, float(v0 - Fraction(1, 2) / fps)):.6f}",
                    "-t", f"{float(n / fps) + 0.5:.3f}", "-i", str(fonte), "-an", "-vf", vf,
                    "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
                    "-r", f"{fps.numerator}/{fps.denominator}", str(out)], check=True)


def cmd_base(edit: Path, final: bool) -> None:
    mapa, fonte, cfg = carrega(edit)
    edl = json.loads((edit / "edl.json").read_text())
    fps = fps_fonte(fonte)
    modo = "final" if final else "preview"
    clips = edit / f"clips_{modo}"
    clips.mkdir(exist_ok=True)
    for velho in list(clips.glob("seg_*.mov")) + list(clips.glob("seg_*.mp4")):
        velho.unlink()

    # "corte": {"cor": false} = fonte já tratada (vídeo que já veio editado): não mexe na cor
    grade = auto_grade_for_clip(fonte, start=min(20.0, duracao(fonte) / 4),
                                duration=min(150.0, duracao(fonte) / 2))[0] if cfg.get("cor", True) else ""
    print(f"cor: {grade or '(nenhuma)'}  (uma análise pro vídeo todo: cor não oscila no corte)")

    w, h = (int(x) for x in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(fonte)]).decode().strip().split(",")[:2])
    nove16 = "" if abs(w / h - 9 / 16) < 0.01 or w < h else "crop=trunc(ih*9/16/2)*2:ih,"  # horizontal: centro 9:16
    z, zx, zy = cfg["zoom_crop"]
    zoom = f"crop=trunc(iw*{z}/2)*2:trunc(ih*{z}/2)*2:trunc(iw*{zx}/2)*2:trunc(ih*{zy}/2)*2,"

    # Corte com sobreposição (padrão do pack): o módulo decide imagem e som de cada trecho.
    # edl antigo (sem voz_ini/voz_fim): a voz fica dentro das folgas pad_in/pad_out.
    rs = edl["ranges"]
    trechos = [{"voz_ini": r.get("voz_ini", r["start"] + cfg["pad_in"]),
                "voz_fim": r.get("voz_fim", r["end"] - cfg["pad_out"]),
                "a_min": r.get("a_min", 0.0), "a_max": r.get("a_max", float("inf")),
                "colado": bool(r.get("colado"))} for r in rs]
    # Pontas do vídeo respeitam pad_in/pad_out do mapa ("sem corte" usa 0,5 s): o som começa no
    # mais cedo dos dois e termina com o maior rabo. As emendas do meio seguem o padrão fixo.
    trechos[0]["voz_ini"] = min(trechos[0]["voz_ini"], rs[0]["start"] + CS.FOLGA_S)
    plano = CS.planejar(trechos, fps, rabo_final=max(CS.RABO_S, float(cfg["pad_out"])))
    durs = [float(Fraction(p["nq"]) / fps) for p in plano]
    segs = []
    for i, (r, p) in enumerate(zip(rs, plano)):
        vf = nove16 + (zoom if r["zoom"] else "") + "scale=1080:1920" + (f",{grade}" if grade else "")
        out = clips / f"seg_{i:02d}.mp4"
        extrai_video(fonte, p["v0"], p["nq"], fps, vf, out, final)
        segs.append(out)
        print(f"  trecho {i:02d} {'Z' if r['zoom'] else ' '} {p['nq']} quadros"
              f"{'' if r.get('colado') or i == 0 else ' | som da fala anterior por baixo'}", flush=True)
    video = edit / f"_video_{modo}.mp4"
    R.concat_segments(segs, video, edit)
    audio = edit / f"_audio_{modo}.wav"
    CS.montar_audio(fonte, plano, fps, audio)
    base = edit / f"base_{modo}.mov"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "pcm_s16le", str(base)], check=True)
    video.unlink(missing_ok=True)
    audio.unlink(missing_ok=True)
    (edit / "base_info.json").write_text(json.dumps(
        {"fps": [fps.numerator, fps.denominator], "duracoes": durs, "base": base.name,
         "corte": "sobreposto", "plano": [{**p, "v0": float(p["v0"])} for p in plano]}))

    # palavras na linha do tempo de saída pelo SOM (a última palavra de A aparece quando é ouvida)
    out_w = CS.palavras_saida(palavras(edit, fonte), plano, [r["grupo"] for r in rs])
    (edit / "words_out.json").write_text(json.dumps(out_w, ensure_ascii=False))
    emendas = CS.conferir(base, plano, fps)["emendas"]
    sob = [e["som_de_A_por_baixo_ms"] for e in emendas if not e["colado"]]
    print(f"base pronta: {base}  ({sum(durs):.3f}s, conferir com ffprobe) | "
          f"{len(sob)} emendas sobrepostas, som de A por baixo {min(sob, default=0)}-{max(sob, default=0)} ms")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    edit_dir, cmd = Path(sys.argv[1]).resolve(), sys.argv[2]
    if cmd == "frases":
        cmd_frases(edit_dir)
    elif cmd == "edl":
        cmd_edl(edit_dir)
    elif cmd == "base":
        cmd_base(edit_dir, "--final" in sys.argv)
    else:
        sys.exit(__doc__)
