"""aplicar.py — aplica os efeitos da biblioteca (efeitos.py) em cima de qualquer vídeo vertical.

Uso (Python do video-use):
  PY=~/Developer/video-use/.venv/bin/python
  $PY aplicar.py <projeto>/efeitos.json --so-quadros 0.4,1.5,2.6   # JPGs em <projeto>/efeitos_work/quadros/
  $PY aplicar.py <projeto>/efeitos.json --storyboard               # storyboard.html pro usuário aprovar ANTES
  $PY aplicar.py <projeto>/efeitos.json [--saida nome.mp4]          # vídeo completo

efeitos.json (caminhos relativos à pasta do json):
{
  "video": "base.mov",                     # qualquer tamanho: vira 1080x1920 (preenche e corta)
  "cor": "#F7E476",                         # cor de destaque (opcional; sem ela vale a cor_destaque do perfil; halo derivado dela)
  "ancora_rosto": [540, 900],               # opcional: sem isso, estimado pelo recorte a cada quadro
  "rotulos": false,                         # true = contador "01/17" + nome do efeito (modo catálogo)
  "serie": {"titulo": "17 efeitos", "sub": "que o Claude cria"},   # opcional: título fixo no topo
  "saida_padrao": 0.15,                     # segundos de fusão de volta ao vídeo no fim de cada efeito
  "volume_sfx": 0.5,
  "normaliza": true,                       # volume final em -14 LUFS (padrão do pack)
  "ate": 20.0,                              # opcional: só os primeiros N segundos
  "efeitos": [{"nome": "orbit", "ini": 0.0, "fim": 1.1, "imagens": "prints/"}, ...]
}

Recorte da pessoa (Apple Vision) só nos quadros dentro de efeitos que precisam dele; fica em
<projeto>/efeitos_work/masks/ e é reaproveitado enquanto o vídeo e as janelas não mudarem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import efeitos as FX  # noqa: E402

# Perfil do criador (~/.claude/padroes-edicao/perfil.json): cor de destaque padrão quando o json não traz "cor".
sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import perfil  # noqa: E402
PERFIL = perfil.carregar()

W, H = FX.W, FX.H
BIN = AQUI / "bin" / "mascara"


def sonda(video: Path) -> tuple[float, float, bool]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,r_frame_rate:format=duration",
                          "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a, b = v["r_frame_rate"].split("/")
    return int(a) / int(b), float(j["format"]["duration"]), any(s["codec_type"] == "audio" for s in j["streams"])


VF = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"


def decodifica(video: Path, ate: float | None = None):
    lim = ["-t", f"{ate}"] if ate else []
    return subprocess.Popen(["ffmpeg", "-v", "error", *lim, "-i", str(video), "-vf", VF, "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)


def garante_bin():
    """Binário do recorte: o desta skill; se faltar, compila do .swift; sem os dois, usa o do /reel-glow."""
    global BIN
    if BIN.exists():
        return
    if (AQUI / "mascara.swift").exists():
        BIN.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(AQUI / "mascara.swift"), "-o", str(BIN)], check=True)
        return
    irmao = Path.home() / ".claude/skills/reel-glow/scripts/bin/mascara"
    if not irmao.exists():
        sys.exit("falta o binário do recorte (scripts/bin/mascara) e o mascara.swift")
    BIN = irmao


def mascaras(video: Path, work: Path, fps: float, janelas: list, quadros: list[int] | None = None) -> Path:
    """Recorte dos quadros nas janelas (ou só dos quadros pedidos). Devolve a pasta das máscaras."""
    garante_bin()
    out = work / "masks" / "out"
    chave = hashlib.md5(json.dumps([str(video), video.stat().st_mtime, janelas]).encode()).hexdigest()
    marca = work / "masks" / "chave.txt"
    if quadros is None and marca.exists() and marca.read_text() == chave:
        return out
    src = work / "masks" / "src"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    if quadros is not None:
        alvo = [q for q in quadros if not (out / f"f_{q:06d}.png").exists()]
        for q in alvo:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{q / fps:.4f}", "-i", str(video), "-vf", VF,
                                  "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, check=True).stdout
            Image.frombytes("RGB", (W, H), raw).resize((540, 960)).save(src / f"f_{q:06d}.png")
    else:
        shutil.rmtree(out, ignore_errors=True)
        dec = decodifica(video)
        k, tam = 0, W * H * 3
        while True:
            buf = dec.stdout.read(tam)
            if len(buf) < tam:
                break
            t = k / fps
            if any(a <= t < b for a, b in janelas):
                Image.frombytes("RGB", (W, H), buf).resize((540, 960)).save(src / f"f_{k:06d}.png")
            k += 1
        dec.wait()
    if any(src.iterdir()):
        subprocess.run([str(BIN), str(src), str(out)], check=True, stdout=subprocess.DEVNULL)
    if quadros is None:
        marca.write_text(chave)
    return out


def le_mascara(pasta: Path, n: int) -> Image.Image | None:
    p = pasta / f"f_{n:06d}.png"
    if not p.exists():
        return None
    return Image.open(p).convert("L").resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))


def storyboard(cfg, pasta, video, work, fps, dur, banco, janelas) -> None:
    """Storyboard de aprovação (antes do render): uma cena por efeito, com o quadro REAL do efeito
    já montado. Gerador comum a todas as skills de Reels: ~/.claude/padroes-edicao/storyboard.py.
    Quando os efeitos vêm pela chave "efeitos" de outra skill (glow etc.), o storyboard é o daquela skill."""
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB
    efs = sorted(cfg["efeitos"], key=lambda e: float(e["ini"]))
    cenas, ms, avisos = [], [], []
    for i, e in enumerate(efs):
        t0, t1 = float(e["ini"]), float(e["fim"])
        info = FX.EFEITOS.get(e["nome"], {})
        cenas.append({"t0": t0, "t1": t1, "fala": e.get("fala", ""), "nome": info.get("rotulo") or e["nome"]})
        extra = {k: v for k, v in e.items() if k not in ("nome", "ini", "fim", "fala")}
        ms.append({"t0": t0, "t1": t1, "quadro": min(t0 + max(0.5, 0.55 * (t1 - t0)), t1 - 0.05),
                   "tipo": f"Efeito {e['nome']}" + (f" ({info['rotulo']})" if info.get("rotulo") else ""),
                   "desc": SB.textos_do_spec(extra) or ", ".join(f"{k}: {v}" for k, v in extra.items()) or "padrão"})
        if i and t0 < float(efs[i - 1]["fim"]):
            avisos.append(f"{efs[i - 1]['nome']} e {e['nome']} se sobrepõem ({efs[i - 1]['fim']}–{t0} s)")
    if len(efs) > 1:
        media = dur / len(efs)
        if media < 6:
            avisos.append(f"1 efeito a cada {media:.1f} s; o padrão é ~1 a cada 10 s, ligado à frase".replace(".", ","))
    ns = [round(m["quadro"] * fps) for m in ms]
    mp = mascaras(video, work, fps, janelas, [n for n in ns if any(x <= n / fps < y for x, y in janelas)])

    def quadro(t: float):
        n = round(t * fps)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / fps:.4f}", "-i", str(video), "-vf", VF,
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        fr = Image.frombytes("RGB", (W, H), raw).convert("RGBA")
        return banco.aplica(fr, n / fps, n, le_mascara(mp, n))

    out = SB.gerar(pasta, "Efeitos", dur, cenas, ms, quadro, avisos, titulo=pasta.name)
    print(f"storyboard: {out}  ({len(ms)} efeitos)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", type=Path)
    ap.add_argument("--so-quadros", default="")
    ap.add_argument("--saida", default="")
    ap.add_argument("--storyboard", action="store_true")
    a = ap.parse_args()
    cfg_path = a.json.resolve()
    pasta = cfg_path.parent
    cfg = json.loads(cfg_path.read_text())
    video = (pasta / cfg["video"]).resolve()
    work = pasta / "efeitos_work"
    work.mkdir(exist_ok=True)
    fps, dur, tem_audio = sonda(video)
    ate = cfg.get("ate")              # opcional: renderiza só os primeiros N segundos
    if ate:
        dur = min(dur, float(ate))
    banco = FX.Banco(cfg["efeitos"], fps, pasta, cfg.get("cor", PERFIL["cor_destaque"]), cfg.get("halo"),
                     cfg.get("ancora_rosto"), cfg.get("rotulos", False), cfg.get("serie"),
                     cfg.get("saida_padrao", 0.15))
    janelas = banco.janelas_mascara()

    if a.storyboard:
        storyboard(cfg, pasta, video, work, fps, dur, banco, janelas)
        return

    if a.so_quadros:
        ts = [float(x) for x in a.so_quadros.split(",")]
        ns = [round(t * fps) for t in ts]
        mp = mascaras(video, work, fps, janelas, [n for n, t in zip(ns, ts)
                                                  if any(x <= t < y for x, y in janelas)])
        qd = work / "quadros"
        qd.mkdir(exist_ok=True)
        for t, n in zip(ts, ns):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / fps:.4f}", "-i", str(video), "-vf", VF,
                                  "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, check=True).stdout
            fr = Image.frombytes("RGB", (W, H), raw).convert("RGBA")
            banco.aplica(fr, n / fps, n, le_mascara(mp, n)).convert("RGB").save(qd / f"q_{t:06.2f}.jpg", quality=88)
        print(f"prévias em {qd}")
        return

    print(f"recorte da pessoa em {len(janelas)} janelas...", flush=True)
    mp = mascaras(video, work, fps, janelas)

    # áudio: som original + efeitos sonoros
    sr = FX.SR
    n_s = int(dur * sr)
    voz = np.zeros((n_s, 2), np.float32)
    if tem_audio:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-t", f"{dur}", "-i", str(video), "-vn", "-ac", "2", "-ar", str(sr),
                              "-f", "s16le", "-"], capture_output=True, check=True).stdout
        v = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, 2) / 32768
        voz[:min(n_s, len(v))] = v[:n_s]
    sfx = FX.sintetiza(banco.eventos_som(), dur, sr, cfg.get("volume_sfx", 0.5))
    mix = voz + sfx[:n_s, None]
    pico = np.abs(mix).max()
    if pico > 0.97:
        mix *= 0.97 / pico
    wav = work / "mix.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())

    saida = pasta / (a.saida or f"{video.stem}_efeitos.mp4")
    dec = decodifica(video, ate)
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", f"{fps}", "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                            *(["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000"] if cfg.get("normaliza", True) else []),
                            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(saida)],
                           stdin=subprocess.PIPE)
    tam = W * H * 3
    k = 0
    total = int(dur * fps)
    while True:
        buf = dec.stdout.read(tam)
        if len(buf) < tam:
            break
        t = k / fps
        fr = Image.frombytes("RGB", (W, H), buf).convert("RGBA")
        if banco.ativo(t) or banco.serie:
            fr = banco.aplica(fr, t, k, le_mascara(mp, k) if any(x <= t < y for x, y in janelas) else None)
        enc.stdin.write(fr.convert("RGB").tobytes())
        k += 1
        if k % 60 == 0:
            print(f"  {k}/{total} quadros", flush=True)
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"pronto: {saida}  ({k} quadros, {k / fps:.2f} s)")


if __name__ == "__main__":
    main()
