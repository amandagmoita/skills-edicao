#!/usr/bin/env python3
"""cortar.py — jump cuts nas pausas + 9:16 centrado no rosto + punch-in alternado.

Uso:
  python3 cortar.py <video_cru> <pasta_projeto> [--gap 0.22] [--pad 0.06]
                    [--remover "12-19,40-44"] [--zoom 1.08] [--fps 30]

Precisa de <pasta_projeto>/palavras.json (transcrever.py).
--remover: faixas de ÍNDICES de palavra (inclusive) a jogar fora: repetição, erro, "ééé".
           Os índices são os do palavras.json (o Claude escolhe lendo a transcrição numerada).
--remover-tempo: faixas em SEGUNDOS do vídeo cru ("28.3-31.1,105-107.7"). Para quando o
           whisper funde duas tomadas da mesma frase numa só ou empilha as palavras de um
           fragmento no mesmo instante: aí o índice não separa as tomadas e o tempo separa.
--manter-tempo: o inverso: SÓ estas faixas em segundos do cru ficam (as pausas dentro delas
           continuam sendo cortadas), NA ORDEM EM QUE FOREM LISTADAS: dá pra juntar o começo
           de uma tomada com o fim de outra gravada antes. É o modo certo para gravação frase por frase com várias
           tomadas (comum em quem lê roteiro): o whisper erra o fim da palavra em até 0,6 s e o
           rabo da tomada descartada vaza. Achar as faixas pela energia do áudio
           (pausas() deste arquivo) e confirmar cada uma com o whisper no trecho isolado.

Corte das falas: CORTE COM SOBREPOSIÇÃO (padrão do pack pra toda edição de Reels).
  Em cada emenda o vídeo da fala A sai 0,10 s antes da voz de A acabar, o áudio de A continua por
  baixo de B até 0,06 s depois da voz (fade 80 ms), B entra 0,04 s antes da voz. A regra mora em
  ~/.claude/padroes-edicao/corte_sobreposto.py (+ corte-sobreposto.md). Mudou? Muda lá.

Gera:
  base_corte.mp4        1080x1920, 30 fps, cor levemente quente, áudio normalizado (-14 LUFS)
  corte.json            {"segmentos": [{"in","out","ini","fim","zoom","rosto":{x,y,w,h}}], "total": s}
                        "rosto" já em PIXELS do quadro final (1080x1920) daquele segmento
  palavras_corte.json   palavras com tempos na timeline do corte, com o índice original "i"
"""
import argparse, array, json, math, os, shutil, subprocess, sys, wave

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/.claude/padroes-edicao"))
import corte_sobreposto as CS  # noqa: E402
W, H = 1080, 1920


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("erro:\n" + " ".join(cmd)[:300] + "\n" + r.stderr[-1500:])
    return r.stdout


def visao():
    b = os.path.join(AQUI, "bin", "visao")
    if not os.path.exists(b):
        os.makedirs(os.path.dirname(b), exist_ok=True)
        sh(["swiftc", "-O", os.path.join(AQUI, "visao.swift"), "-o", b])
    return b


def faixas(txt):
    fora = set()
    for parte in filter(None, (txt or "").replace(" ", "").split(",")):
        a, _, b = parte.partition("-")
        fora.update(range(int(a), int(b or a) + 1))
    return fora


def pausas(wav, minimo, janela=0.02):
    """Trechos sem voz com pelo menos `minimo` s. Limiar adaptativo: piso de ruído
    (percentil 10 da energia) + 8 dB, nunca abaixo de -50 dB nem acima de -28 dB, e
    nunca a mais de 18 dB abaixo da voz (percentil 90): ruído de sala a -50 dB com voz
    a -13 dB passava como fala e virava pedacinho de 0,1 s entre as tomadas; com 30 dB e
    até 22 dB a RESPIRAÇÃO (~-35 dB com voz a -14) ainda contava como fala e sobravam ~11 s
    de respiro num corte de 96 s."""
    w = wave.open(wav)
    taxa, n = w.getframerate(), w.getnframes()
    amostras = array.array("h", w.readframes(n))
    passo = int(taxa * janela)
    db = []
    for i in range(0, len(amostras) - passo, passo):
        bloco = amostras[i:i + passo]
        db.append(10 * math.log10(sum(x * x for x in bloco) / passo / 32768 ** 2 + 1e-12))
    if not db:
        return []
    ordem = sorted(db)
    limiar = min(max(ordem[len(db) // 10] + 8, ordem[len(db) * 9 // 10] - 18, -50), -28)
    saida, ini = [], None
    for k, v in enumerate(db + [0]):
        if v < limiar and ini is None:
            ini = k
        elif v >= limiar and ini is not None:
            if (k - ini) * janela >= minimo:
                saida.append((ini * janela, k * janela))
            ini = None
    return saida


def energia(wav, janela=0.01):
    """dB por janela de 10 ms + limiar de VOZ (percentil 90 - 16 dB; respiração fica a ~-21): acima disso é fala
    de verdade; respiração, estalo de boca e ruído de sala ficam abaixo."""
    w = wave.open(wav)
    taxa, n = w.getframerate(), w.getnframes()
    amostras = array.array("h", w.readframes(n))
    passo = int(taxa * janela)
    db = [10 * math.log10(sum(x * x for x in amostras[i:i + passo]) / passo / 32768 ** 2 + 1e-12)
          for i in range(0, len(amostras) - passo, passo)]
    ordem = sorted(db)
    return db, janela, ordem[len(db) * 9 // 10] - 16


def aparar(segs, db, janela, voz, antes=0.05, depois=0.18):
    """Encosta cada segmento na fala: tira o respiro do começo e do fim (o corte por pausa só
    pega silêncio >= --gap, então até 0,6 s de respiro ficava colado em cada tomada) e
    descarta segmento sem nenhuma fala (estalo, respiração solta)."""
    out = []
    for s in segs:
        k0, k1 = int(s["in"] / janela), min(int(s["out"] / janela), len(db))
        # só vale voz CONTÍNUA (>= 40 ms): respiração solta estala em janelas de 10 ms acima
        # do limiar e o fim do segmento ia até o último estalo (0,7 s depois de "Drive,")
        ativos, corrida = [], []
        for k in range(k0, k1 + 1):
            if k < k1 and db[k] > voz:
                corrida.append(k)
            else:
                if len(corrida) >= 4:
                    ativos += corrida
                corrida = []
        if len(ativos) < 15:  # menos de 0,15 s de voz: rabo de palavra, estalo ou respiro
            continue
        out.append({"in": max(s["in"], ativos[0] * janela - antes),
                    "out": min(s["out"], (ativos[-1] + 1) * janela + depois),
                    # voz de verdade + limites que o som não passa (corte com sobreposição)
                    "voz_in": ativos[0] * janela, "voz_out": (ativos[-1] + 1) * janela,
                    "a_min": s["in"], "a_max": s["out"]})
    return out


def juntar(intervalos):
    out = []
    for a, b in intervalos:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def tamanho_exibido(video, proj):
    """Tamanho do quadro já com a rotação aplicada (vídeo de celular vem rotacionado)."""
    png = os.path.join(proj, "_quadro.png")
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", video, "-frames:v", "1", png])
    out = sh(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", png])
    os.remove(png)
    w, h = out.strip().split(",")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("projeto")
    ap.add_argument("--gap", type=float, default=0.22)
    ap.add_argument("--pad", type=float, default=0.06)
    ap.add_argument("--remover", default="")
    ap.add_argument("--remover-tempo", default="")
    ap.add_argument("--manter-tempo", default="")
    ap.add_argument("--zoom", type=float, default=1.08)
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    P = a.projeto

    palavras = json.load(open(os.path.join(P, "palavras.json")))
    fora = faixas(a.remover)
    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", a.video]).strip())

    # 1) segmentos de fala. O whisper "estica" as palavras por cima das pausas, então as
    #    pausas vêm da ENERGIA do áudio; as palavras removidas viram cortes forçados.
    #    Silêncio encolhe "pad" de cada lado (respiro); palavra removida sai exata.
    cortes = [(s + a.pad, e - a.pad) for s, e in pausas(os.path.join(P, "audio16k.wav"), a.gap)]
    cortes += [(palavras[i]["s"], palavras[i]["e"]) for i in sorted(fora) if i < len(palavras)]
    for parte in filter(None, a.remover_tempo.replace(" ", "").split(",")):
        t0, _, t1 = parte.partition("-")
        cortes.append((float(t0), float(t1)))
    janelas = []
    for parte in filter(None, a.manter_tempo.replace(" ", "").split(",")):
        t0, _, t1 = parte.partition("-")
        janelas.append((float(t0), float(t1)))
    if not janelas:
        mantidas = [p for i, p in enumerate(palavras) if i not in fora]
        if mantidas:  # antes da 1ª e depois da última palavra mantida
            cortes += [(0.0, mantidas[0]["s"] - a.pad), (mantidas[-1]["e"] + a.pad, dur)]
        janelas = [(0.0, dur)]
    cortes = juntar(sorted((c0, c1) for c0, c1 in cortes if c1 > c0))
    # cada janela, NA ORDEM DADA (permite montar frase com pedaços de tomadas diferentes),
    # menos os cortes que caem dentro dela
    segs = []
    for w0, w1 in janelas:
        t0 = w0
        for c0, c1 in cortes:
            if c1 <= t0 or c0 >= w1:
                continue
            if c0 > t0:
                segs.append({"in": max(0.0, t0), "out": min(w1, c0)})
            t0 = max(t0, c1)
        if w1 > t0:
            segs.append({"in": t0, "out": min(w1, dur)})
    db, jan, voz = energia(os.path.join(P, "audio16k.wav"))
    segs = aparar(segs, db, jan, voz)
    if segs:  # o vídeo não termina colado na última consoante do CTA
        segs[-1]["out"] = min(segs[-1]["out"] + 0.3, dur)
        segs[-1]["a_max"] = min(segs[-1]["a_max"] + 0.3, dur)
    # quantiza no frame para áudio e vídeo baterem
    q = lambda t: round(t * a.fps) / a.fps
    for s in segs:
        s["in"], s["out"] = q(s["in"]), q(s["out"])
    segs = [s for s in segs if s["out"] - s["in"] >= 2 / a.fps]

    # 1b) trecho longo sem pausa ainda troca de zoom: divide no fim de frase (>= 2,5 s)
    #     ou, sem pontuação, a cada ~5 s numa fronteira de palavra. Sem corte no áudio.
    divididos = []
    for sg in segs:
        dentro = [p for i, p in enumerate(palavras) if i not in fora and sg["in"] < p["e"] < sg["out"]]
        ini = sg["in"]
        for p, prox in zip(dentro, dentro[1:]):
            ponto = q((p["e"] + prox["s"]) / 2)
            fim_frase = p["w"][-1:] in ".!?,:"
            if (fim_frase and ponto - ini >= 2.5) or ponto - ini >= 5.0:
                if sg["out"] - ponto >= 1.2:
                    divididos.append({"in": ini, "out": ponto, "colado": ini != sg["in"],
                                      "voz_in": sg["voz_in"] if ini == sg["in"] else ini, "voz_out": ponto,
                                      "a_min": sg["a_min"], "a_max": sg["a_max"]})
                    ini = ponto
        divididos.append({"in": ini, "out": sg["out"], "colado": ini != sg["in"],
                          "voz_in": sg["voz_in"] if ini == sg["in"] else ini, "voz_out": sg["voz_out"],
                          "a_min": sg["a_min"], "a_max": sg["a_max"]})
    segs = divididos

    # 2) rosto no vídeo cru
    fdir = os.path.join(P, "_frames_rosto")
    shutil.rmtree(fdir, ignore_errors=True); os.makedirs(fdir)
    sh(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", f"fps={min(1.0, 15 / max(dur, 1)):.3f}",
        os.path.join(fdir, "%03d.jpg")])
    sh([visao(), "rosto", fdir, os.path.join(P, "rosto_cru.json")])
    shutil.rmtree(fdir, ignore_errors=True)
    r = json.load(open(os.path.join(P, "rosto_cru.json")))

    # 3) recorte 9:16 em torno do rosto
    sw, shh = tamanho_exibido(a.video, P)
    if sw / shh > 9 / 16:
        cw, ch = shh * 9 / 16, shh
    else:
        cw, ch = sw, sw * 16 / 9
    fcx, fcy = r["cx"] * sw, r["cy"] * shh

    def caixa(zoom):
        w, h = cw / zoom, ch / zoom
        x = min(max(fcx - w / 2, 0), sw - w)
        # rosto no terço superior do quadro (~36% da altura), como na referência
        y = min(max(fcy - h * 0.36, 0), shh - h)
        return int(x) // 2 * 2, int(y) // 2 * 2, int(w) // 2 * 2, int(h) // 2 * 2

    # Corte com sobreposição: o módulo decide onde a imagem e o som de cada trecho começam e acabam.
    # O rabo do último trecho mantém o respiro do CTA (voz + 0,18 + 0,3 s, como antes).
    plano = CS.planejar([{"voz_ini": s["voz_in"], "voz_fim": s["voz_out"], "colado": s["colado"],
                          "a_min": s["a_min"], "a_max": s["a_max"]} for s in segs], a.fps, rabo_final=0.48)
    for s, p in zip(segs, plano):
        s["in"], s["out"] = float(p["v0"]), float(p["v0"]) + p["nq"] / a.fps

    filtros, n = [], len(segs)
    # cada entrada do vídeo só pode ser lida pra frente: tomada que volta no tempo (frase
    # montada com pedaços fora de ordem) abre o vídeo de novo como outra entrada. Com uma
    # entrada só, o trim "pra trás" embaralhou o corte (98 s viraram 116 s com 11 s mudos).
    entrada, fim_atual = [], []
    for s in segs:
        if not fim_atual or s["in"] < fim_atual[-1]:
            fim_atual.append(s["out"])
        else:
            fim_atual[-1] = s["out"]
        entrada.append(len(fim_atual) - 1)
    for e in range(len(fim_atual)):
        meus = [i for i in range(n) if entrada[i] == e]
        filtros.append(f"[{e}:v]split={len(meus)}" + "".join(f"[v{i}]" for i in meus))
    t, saida_segs = 0.0, []
    for i, s in enumerate(segs):
        zoom = 1.0 if i % 2 == 0 else a.zoom
        x, y, w, h = caixa(zoom)
        filtros.append(f"[v{i}]trim={s['in']:.4f}:{s['out']:.4f},setpts=PTS-STARTPTS,"
                       f"crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,setsar=1,fps={a.fps}[vv{i}]")
        d = s["out"] - s["in"]
        k = W / w
        rosto = {"x": (r["x"] * sw - x) * k, "y": (r["y"] * shh - y) * k,
                 "w": r["w"] * sw * k, "h": r["h"] * shh * k}
        saida_segs.append({"in": s["in"], "out": s["out"], "ini": round(t, 4), "fim": round(t + d, 4),
                           "zoom": zoom, "rosto": {k2: round(v, 1) for k2, v in rosto.items()}})
        t += d
    filtros.append("".join(f"[vv{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    filtros.append("[vc]eq=contrast=1.04:saturation=1.08,colorbalance=rm=0.03:bm=-0.03,format=yuv420p[vout]")

    script = os.path.join(P, "_corte.filtro")
    open(script, "w").write(";\n".join(filtros))
    base = os.path.join(P, "base_corte.mp4")
    print(f"{len(palavras)} palavras, {len(fora)} removidas, {n} segmentos, {t:.1f}s (cru: {dur:.1f}s)")
    audio = os.path.join(P, "_audio_corte.wav")
    CS.montar_audio(a.video, plano, a.fps, audio, pos_filtro="highpass=f=80,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000")
    sh(["ffmpeg", "-v", "error", "-y"] + ["-i", a.video] * len(fim_atual) + ["-i", audio, "-filter_complex_script", script,
        "-map", "[vout]", "-map", f"{len(fim_atual)}:a", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", base])
    os.remove(audio)
    sob = [e["som_de_A_por_baixo_ms"] for e in CS.conferir(base, plano, a.fps)["emendas"] if not e["colado"]]
    print(f"corte com sobreposição: {len(sob)} emendas, som da fala anterior por baixo {min(sob, default=0)}-{max(sob, default=0)} ms")

    # 4) palavras na timeline do corte
    # pelo SOM: a última palavra de A aparece quando é ouvida, mesmo com a imagem já em B
    novas = []
    for pl in plano:
        desloc = pl["som_saida"] - pl["a0"]
        for i, p in enumerate(palavras):
            if i in fora or p["e"] <= pl["a0"] or p["s"] >= pl["a1"]:
                continue
            ini = max(p["s"], pl["a0"]) + desloc
            fim = min(p["e"], pl["a1"]) + desloc
            novas.append({"i": i, "w": p["w"], "s": round(ini, 3), "e": round(max(fim, ini + 0.05), 3)})
    # palavra que cruza uma divisão de zoom aparece nos dois lados: vira uma só
    unicas = {}
    for p in novas:
        if p["i"] in unicas:
            u = unicas[p["i"]]
            u["s"], u["e"] = min(u["s"], p["s"]), max(u["e"], p["e"])
        else:
            unicas[p["i"]] = p
    novas = sorted(unicas.values(), key=lambda p: p["s"])
    json.dump(novas, open(os.path.join(P, "palavras_corte.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"segmentos": saida_segs, "total": round(t, 4), "fps": a.fps},
              open(os.path.join(P, "corte.json"), "w"), indent=1)
    print(f"-> {base}")
    # rosto de verdade em cada segmento (a mediana do cru não acompanha a troca de tomada)
    subprocess.run([sys.executable, os.path.join(AQUI, "rosto_segmentos.py"), P], check=True)


if __name__ == "__main__":
    sys.exit(main())
