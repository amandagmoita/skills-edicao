#!/usr/bin/env python3
"""
gen_sfx.py — sintetiza SFX (whoosh/pop/ding/key) no ffmpeg e/ou monta a trilha de SFX
posicionando cada efeito num tempo da timeline do corte.

Não há SFX locais no HyperFrames (só manifest) → sintetizamos com lavfi.

1) Sintetizar a biblioteca (uma vez por projeto, numpy + scipy):
     python3 gen_sfx.py --synth <sfxdir>
   gera whoosh_1-3, sobe_1-2, riser, boom, punch_1-2, pop_1-3, brilho_1-3, ding, key
   (+ whoosh.wav e pop.wav por compatibilidade).

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

TAXA = 48000


def _grava(caminho, sinal):
    import numpy as np, wave
    sinal = np.asarray(sinal, dtype=float)
    pico = np.max(np.abs(sinal)) or 1.0
    sinal = sinal / pico * 0.89
    if sinal.ndim == 1:
        sinal = np.stack([sinal, sinal], axis=1)
    w = wave.open(caminho, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(TAXA)
    w.writeframes((sinal * 32767).astype("<i2").tobytes()); w.close()


def _passa_banda(ruido, f0, f1, q=1.6):
    """Ruído filtrado com o centro varrendo de f0 a f1 (exponencial). Butterworth de 4ª ordem
    por bloco de 1024 amostras, sobrepostos com janela de Hann. O filtro de estado variável
    da 1ª versão era largo demais: o agudo do ruído dominava e o whoosh soava como chiado."""
    import numpy as np
    from scipy import signal
    n, bloco, passo = len(ruido), 1024, 512
    out = np.zeros(n + bloco); jan = np.hanning(bloco)
    base = np.pad(ruido, (bloco, bloco))
    largura = 1 + 0.9 / q
    for ini in range(0, n, passo):
        fc = f0 * (f1 / f0) ** (min(ini + bloco / 2, n) / n)
        lo, hi = max(fc / largura, 30), min(fc * largura, TAXA / 2 - 500)
        sos = signal.butter(2, [lo, hi], btype="bandpass", fs=TAXA, output="sos")
        trecho = signal.sosfilt(sos, base[ini:ini + 2 * bloco])[bloco:]
        out[ini:ini + bloco] += trecho[:bloco] * jan
    return out[:n]


def _env(n, pico, ataque=2.0, queda=2.5):
    import numpy as np
    x = np.arange(n) / n
    sobe = (x / pico) ** ataque
    desce = ((1 - x) / (1 - pico)) ** queda
    return np.where(x < pico, sobe, desce)


def _tom(f0, f1, dur, queda=6.0, parciais=((1, 1.0),)):
    import numpy as np
    n = int(dur * TAXA); t = np.arange(n) / TAXA
    f = f0 * (f1 / f0) ** (t / dur)
    fase = 2 * np.pi * np.cumsum(f) / TAXA
    s = sum(a * np.sin(fase * m) for m, a in parciais)
    return s * np.exp(-queda * t / dur)


def synth(sfxdir):
    """Biblioteca de SFX com VARIAÇÕES (um som só pra tudo soava repetitivo):
    cada tipo de efeito tem o seu som e 2-3 versões que o compor.py reveza."""
    import numpy as np
    os.makedirs(sfxdir, exist_ok=True)
    j = lambda f: os.path.join(sfxdir, f)
    rng = np.random.default_rng(7)
    ruido = lambda d: rng.standard_normal(int(d * TAXA))
    estereo = lambda a, b: np.stack([a, b], axis=1)
    # whooshes: varredura de ruído filtrado (subindo, descendo, rápido)
    for nome, d, f0, f1, pico in [("whoosh_1", 0.45, 450, 2600, 0.4), ("whoosh_2", 0.6, 2600, 320, 0.35),
                                   ("whoosh_3", 0.32, 1400, 5200, 0.5)]:
        a = _passa_banda(ruido(d), f0, f1) * _env(int(d * TAXA), pico)
        b = _passa_banda(ruido(d), f0 * 1.05, f1 * 0.95) * _env(int(d * TAXA), pico)
        _grava(j(nome + ".wav"), estereo(a, b))
    # objeto subindo atrás da cabeça: whoosh que sobe + baque grave no fim (2 versões)
    for nome, d, f1, grave in [("sobe_1", 0.55, 3200, 70), ("sobe_2", 0.5, 2400, 90)]:
        w = _passa_banda(ruido(d), 300, f1) * _env(int(d * TAXA), 0.75, 1.5, 4)
        baque = np.concatenate([np.zeros(int(0.36 * TAXA)), _tom(grave * 1.8, grave, 0.3, 5)])
        baque = np.pad(baque, (0, max(0, len(w) + int(0.3 * TAXA) - len(baque))))
        _grava(j(nome + ".wav"), np.pad(w, (0, len(baque) - len(w))) * 0.8 + baque * 0.9)
    # tela preta: riser de 0,6 s que termina num impacto grave
    d = 0.6
    riser = _passa_banda(ruido(d), 200, 3000, 2.5) * (np.arange(int(d * TAXA)) / (d * TAXA)) ** 2.2
    riser += _tom(180, 720, d, 0.1, ((1, 0.25), (2, 0.1))) * (np.arange(int(d * TAXA)) / (d * TAXA)) ** 3
    impacto = _tom(110, 38, 0.7, 4.5, ((1, 1.0), (2, 0.25))) + _passa_banda(ruido(0.7), 800, 200) * _env(int(0.7 * TAXA), 0.02, 1, 6) * 0.6
    _grava(j("riser.wav"), np.concatenate([riser * 0.7, impacto]))
    _grava(j("boom.wav"), impacto)
    # zoom punch: estalo curto + soco grave (2 versões)
    for nome, grave, brilho in [("punch_1", 85, 3500), ("punch_2", 65, 2400)]:
        n = int(0.28 * TAXA)
        estalo = _passa_banda(ruido(0.28), brilho, brilho * 0.4, 1.2) * _env(n, 0.03, 1, 7)
        _grava(j(nome + ".wav"), estalo * 0.7 + _tom(grave * 1.6, grave, 0.28, 5) * 0.9)
    # pop de bolha: tom que despenca (3 alturas)
    for nome, f0, f1 in [("pop_1", 950, 320), ("pop_2", 720, 240), ("pop_3", 1200, 420)]:
        p = _tom(f0, f1, 0.1, 5, ((1, 1.0), (2, 0.2)))
        p[:int(0.002 * TAXA)] *= np.linspace(0, 1, int(0.002 * TAXA))
        _grava(j(nome + ".wav"), np.pad(p, (0, int(0.05 * TAXA))))
    # brilho de título: arpejo de sinos suave (3 acordes)
    for nome, notas in [("brilho_1", (1046.5, 1318.5, 1568.0)), ("brilho_2", (1174.7, 1480.0, 1760.0)),
                        ("brilho_3", (987.8, 1244.5, 1480.0))]:
        tot = np.zeros(int(0.95 * TAXA))
        for k, fq in enumerate(notas):
            nota = _tom(fq, fq, 0.8, 5.5, ((1, 1.0), (2.76, 0.18), (5.4, 0.06)))
            ini = int(k * 0.055 * TAXA); tot[ini:ini + len(nota)] += nota[:len(tot) - ini]
        _grava(j(nome + ".wav"), estereo(tot, np.roll(tot, int(0.012 * TAXA))))
    # ding da 1ª palavra-chave e clique de tecla
    _grava(j("ding.wav"), _tom(1245, 1245, 0.6, 6, ((1, 1.0), (1.5, 0.5))))
    _grava(j("key.wav"), _tom(1600, 1500, 0.035, 4))
    # compatibilidade com projetos antigos
    import shutil
    shutil.copy(j("whoosh_1.wav"), j("whoosh.wav")); shutil.copy(j("pop_1.wav"), j("pop.wav"))
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
