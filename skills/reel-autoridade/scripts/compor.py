#!/usr/bin/env python3
"""compor.py — junta base + camadas + SFX (+ música) e monta o pacote CapCut.

Uso:
  python3 compor.py <pasta_projeto> [--musica arquivo.mp3] [--vol-musica 0.12]

Lê: base_corte.mp4, camadas.mov, mapa.json, legendas.srt
Gera:
  REEL_PRONTO.mp4
  pacote-capcut/  base_corte.mp4, camadas_alpha.mov, camadas_chromakey.mp4 (fundo VERDE),
                  legendas.srt, sfx_trilha.wav, sfx/, montagem.md

SFX automáticos a partir do mapa (variações se revezam, ver eventos()):
  sobe_*    objeto surgindo atrás da cabeça      riser   tela preta (impacto na entrada)
  brilho_*  título em Didot                      punch_* zoom punch nas emendas
  pop_*     chave/legenda destacada e sticker    boom    número gigante
  ding      a primeira legenda com chave
"""
import argparse, json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("erro:\n" + r.stderr[-1500:])


def eventos(mapa):
    """Cada tipo de efeito tem o seu som e as variações se revezam: com um whoosh só pra tudo
    a edição soava repetitiva."""
    from itertools import cycle
    v = {k: cycle(x) for k, x in {
        "sobe": ["sobe_1.wav", "sobe_2.wav"], "whoosh": ["whoosh_1.wav", "whoosh_3.wav", "whoosh_2.wav"],
        "punch": ["punch_1.wav", "punch_2.wav"], "pop": ["pop_1.wav", "pop_2.wav", "pop_3.wav"],
        "brilho": ["brilho_1.wav", "brilho_2.wav", "brilho_3.wav"]}.items()}
    ev = []
    g = mapa.get("objeto_gancho")
    if g:
        ev.append({"t": g["ini"], "file": next(v["whoosh"]), "vol": 0.9})
    for b in mapa.get("telas_pretas", []):  # riser termina no impacto exatamente na entrada
        ev.append({"t": max(b["ini"] - 0.6, 0), "file": "riser.wav", "vol": 0.8})
    for s in mapa.get("stickers", []):
        ev.append({"t": s["ini"], "file": next(v["pop"]), "vol": 0.6})
    for n in mapa.get("numeros", []):
        ev.append({"t": n["ini"], "file": "boom.wav", "vol": 0.9})
    for x in mapa.get("objetos_atras", []):
        ev.append({"t": x["ini"], "file": next(v["sobe"]), "vol": 0.8})
    for x in mapa.get("titulos", []):
        ev.append({"t": x["ini"], "file": next(v["brilho"]), "vol": 0.42})
    for t in mapa.get("transicoes", []):
        ev.append({"t": max(t - 0.02, 0), "file": next(v["punch"]), "vol": 0.6})
    primeira = True
    for l in mapa.get("legendas", []):
        if l.get("chave") and primeira:
            ev.append({"t": l["ini"], "file": "ding.wav", "vol": 0.5}); primeira = False
        elif l.get("chave") or l.get("rosa"):
            ev.append({"t": l["ini"], "file": next(v["pop"]), "vol": 0.6})
    return sorted(ev, key=lambda e: e["t"])


def punch(tempos, fps=30, forca=0.16, dur=0.28, foco=0.33):
    """Zoom punch nas emendas: no quadro da emenda a imagem
    entra 16% mais perto e volta a 100% em 0,28 s, com desfoque nos 3 primeiros quadros.
    Mexe só no vídeo de base: legenda e títulos ficam parados por cima."""
    if not tempos:
        return "[0:v]"
    t = f"(in/{fps})"
    z = "+".join(f"if(between({t},{x:.3f},{x + dur:.3f}),{forca}*pow(1-({t}-{x:.3f})/{dur},3),0)"
                 for x in tempos)
    blur = "+".join(f"between(t,{x:.3f},{x + 0.1:.3f})" for x in tempos)
    return (f"[0:v]zoompan=z='1+{z}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*{foco}':d=1:"
            f"s=1080x1920:fps={fps},gblur=sigma=9:enable='{blur}'[b];[b]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto")
    ap.add_argument("--musica"); ap.add_argument("--vol-musica", type=float, default=0.12)
    a = ap.parse_args()
    P = a.projeto
    mapa = json.load(open(os.path.join(P, "mapa.json")))
    total = json.load(open(os.path.join(P, "corte.json")))["total"]
    musica = a.musica or mapa.get("musica")

    pac = os.path.join(P, "pacote-capcut"); sfxdir = os.path.join(pac, "sfx")
    os.makedirs(sfxdir, exist_ok=True)
    gen = os.path.join(AQUI, "gen_sfx.py")
    sh([sys.executable, gen, "--synth", sfxdir])
    evj = os.path.join(P, "sfx_eventos.json")
    json.dump(eventos(mapa), open(evj, "w"), indent=1)
    trilha = os.path.join(pac, "sfx_trilha.wav")
    sh([sys.executable, gen, "--events", evj, "--sfxdir", sfxdir, "--out", trilha, "--total", f"{total:.3f}"])

    base, cam = os.path.join(P, "base_corte.mp4"), os.path.join(P, "camadas.mov")
    entradas = ["-i", base, "-i", cam, "-i", trilha]
    audio = "[0:a][2:a]amix=inputs=2:normalize=0:duration=first"
    if musica:
        entradas += ["-stream_loop", "-1", "-i", musica]
        # música abaixa sozinha quando a voz entra (sidechain)
        audio = (f"[3:a]volume={a.vol_musica},aresample=48000[m];[0:a]asplit[v1][v2];"
                 f"[m][v1]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[md];"
                 f"[v2][2:a][md]amix=inputs=3:normalize=0:duration=first")
    filtro = (f"{punch(mapa.get('transicoes', []))}[1:v]overlay=0:0:format=auto,format=yuv420p[v];"
              f"{audio},alimiter=limit=0.95[a]")
    final = os.path.join(P, "REEL_PRONTO.mp4")
    sh(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final])

    # pacote CapCut. Chroma key em VERDE: com destaque rosa/amarelo o magenta comeria o texto
    # (cor de destaque verde no perfil quebraria esta chave).
    shutil.copy(base, os.path.join(pac, "base_corte.mp4"))
    shutil.copy(cam, os.path.join(pac, "camadas_alpha.mov"))
    srt = os.path.join(P, "legendas.srt")
    if os.path.exists(srt):
        shutil.copy(srt, os.path.join(pac, "legendas.srt"))
    sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x00FF00:s=1080x1920:r=30:d={total:.3f}",
        "-i", cam, "-filter_complex", "[0][1]overlay=0:0,format=yuv420p", "-c:v", "libx264", "-crf", "16",
        "-t", f"{total:.3f}", os.path.join(pac, "camadas_chromakey.mp4")])
    open(os.path.join(pac, "montagem.md"), "w").write(
        "# Montagem no CapCut\n\n"
        "1. Trilha principal: `base_corte.mp4` (já cortado, enquadrado e com áudio tratado).\n"
        "2. Sobreposição: `camadas_chromakey.mp4` → Recortar → Chroma key → conta-gotas no verde.\n"
        "   No computador dá pra usar `camadas_alpha.mov` direto (já tem transparência).\n"
        "   As camadas já trazem legenda, número gigante, telas pretas, sticker e objeto do gancho.\n"
        "3. Áudio extra: `sfx_trilha.wav` (efeitos já no tempo certo). Volume a gosto.\n"
        "4. Quer legenda editável em vez da queimada? Use a base sem camadas e importe `legendas.srt`.\n"
        "5. Música: escolha no CapCut e deixe bem baixa (a voz manda).\n")
    print("->", final)
    print("->", pac)


if __name__ == "__main__":
    sys.exit(main())
