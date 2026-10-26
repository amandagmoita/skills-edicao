"""corte_sobreposto.py — o padrão de corte de fala do pack. Vale pra TODA edição de Reels.

Calibrado em 6 rodadas de teste até a emenda ficar contínua, sem respiro e sem "pulo".
Referência: ~/.claude/padroes-edicao/corte-sobreposto.md

Em toda emenda entre duas falas (A → B):
  - o VÍDEO de A sai CEDO_S (0,10 s) antes da voz de A terminar;
  - o ÁUDIO de A continua por baixo do vídeo de B até RABO_S (0,06 s) depois da voz e some em
    FADE_RABO (80 ms). As duas falas se sobrepõem ~0,16 s, somadas (sem baixar o volume);
  - B entra com FOLGA_S (0,04 s) antes da voz, fade de entrada de 30 ms.

    vídeo: |------ A ------|------ B ------
    som A: |------ A ---------\\
    som B:                 |------ B ------

Fala contínua na fonte (`colado`: tomadas que se tocam, divisão de zoom sem pausa) junta exata,
sem sobrepor e sem fade.

Uso típico:
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import corte_sobreposto as CS
    plano = CS.planejar([{"voz_ini": 7.09, "voz_fim": 9.44}, ...], fps)   # ordem de saída
    for p in plano: extrair vídeo SEM áudio do quadro p["v0"] por p["nq"] quadros
    CS.montar_audio(fonte, plano, "audio.wav")                            # som sobreposto
    juntar vídeo (concat) + audio.wav

Histórico das rodadas (o que NÃO fazer):
  v1 imagem de B 0,5 s antes da voz de B → aparecia a pessoa calada olhando o roteiro;
  v2 0,2 s melhorou; v3 0,1 s ainda longe; v4 rente à voz quase;
  teste sem folga (voz no quadro do corte) ainda quase: o problema era o FIM de A;
  sobreposto (este) sem folga perfeito → com a folga de 0,04 s de volta: final.
"""

from __future__ import annotations

import subprocess
from fractions import Fraction
from pathlib import Path

# numpy só nas funções de MEDIR (rms_db, bordas_finas, conferir): planejar/montar_audio/palavras_saida
# rodam no python3 do sistema (3.9, sem numpy), que é o que a reel-autoridade usa.

CEDO_S = 0.10      # vídeo de A sai antes da voz de A acabar
RABO_S = 0.06      # áudio de A continua depois da voz acabar
FADE_RABO = 0.08   # e some nesse tempo
FOLGA_S = 0.04     # B começa esse tempo antes da voz
FADE_IN = 0.03     # entrada de B (30 ms: sem estalo e sem abafar a 1ª sílaba, porque há folga)
FADE_FIM = 0.03    # saída do último trecho
ABAIXO_DB = 7.0    # bordas finas: limiar de voz - 7 dB (≈ -40 dB com voz a -33): pega o "s" suave e o decaimento


def rms_db(fonte: Path, t0: float, t1: float, hop: float = 0.005):
    import numpy as np
    t0 = max(0.0, t0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", str(fonte), "-t", f"{t1 - t0:.3f}",
                          "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(float) / 32768
    w = int(16000 * hop)
    n = len(x) // w
    db = 20 * np.log10(np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(1)) + 1e-9)
    return t0 + np.arange(n) * hop, db


def bordas_finas(fonte: Path, voz_ini: float, voz_fim: float, lim_fino: float,
                 maximo: float = 0.12) -> tuple[float, float]:
    """Afina onde a voz começa e termina com um limiar mais baixo (lim_fino). Só anda PRA FORA
    (nunca corta palavra), no máximo `maximo` s, e só enquanto o som é contínuo."""
    t, db = rms_db(fonte, voz_ini - maximo, voz_ini)
    ini = voz_ini
    for k in range(len(db) - 1, -1, -1):
        if db[k] > lim_fino:
            ini = float(t[k])
        else:
            break
    t, db = rms_db(fonte, voz_fim, voz_fim + maximo)
    fim = voz_fim
    for k in range(len(db)):
        if db[k] > lim_fino:
            fim = float(t[k] + 0.005)
        else:
            break
    return ini, fim


def planejar(trechos: list[dict], fps, rabo_final: float = RABO_S) -> list[dict]:
    """trechos (na ordem de saída), cada um com:
         voz_ini, voz_fim  onde a voz começa/termina na fonte (s)
         a_min, a_max      opcional: o som não passa daqui (palavra vizinha que foi descartada)
         colado            opcional: fala contínua com o anterior (voz_ini dele == voz_fim do anterior)
       Devolve, por trecho: v0 (Fraction, início da imagem na fonte, na grade de quadros), nq (quadros),
       a0/a1 (som na fonte), fade_in/fade_out, saida (onde a imagem entra na saída, s) e
       som_saida (onde o som entra na saída, s; difere da imagem em no máx. meio quadro).
    """
    fps = Fraction(fps)
    n = len(trechos)
    plano: list[dict] = []
    saida = Fraction(0)
    for i, t in enumerate(trechos):
        colado_antes = i > 0 and bool(t.get("colado"))
        colado_depois = i + 1 < n and bool(trechos[i + 1].get("colado"))
        a_min, a_max = t.get("a_min", 0.0), t.get("a_max", float("inf"))
        if colado_antes:
            ant = plano[-1]
            v0 = ant["v0"] + Fraction(ant["nq"]) / fps
            a0, fade_in = float(v0), 0.0
        else:
            a0 = max(t["voz_ini"] - FOLGA_S, a_min, 0.0)
            v0 = Fraction(round(Fraction(a0) * fps)) / fps
            if i == 0:
                a0 = float(v0)  # 1º trecho: som e imagem no mesmo quadro
            fade_in = FADE_IN
        if colado_depois:
            v_fim = a1 = trechos[i + 1]["voz_ini"]   # a1 é acertado pro fim exato do último quadro abaixo
            fade_out = 0.0
        elif i == n - 1:
            v_fim = a1 = min(t["voz_fim"] + rabo_final, a_max)
            fade_out = FADE_FIM
        else:
            cedo = min(CEDO_S, 0.3 * (t["voz_fim"] - t["voz_ini"]))  # fala curtíssima não some
            v_fim = t["voz_fim"] - cedo
            a1 = min(t["voz_fim"] + RABO_S, a_max)
            fade_out = FADE_RABO
        nq = max(2, round((Fraction(v_fim) - v0) * fps))
        if colado_depois:
            # fala contínua: o som de A termina EXATAMENTE onde a imagem (e o som) de B começa
            a1 = float(v0 + Fraction(nq) / fps)
        plano.append({"v0": v0, "nq": nq, "a0": a0, "a1": float(a1), "fade_in": fade_in, "fade_out": fade_out,
                      "saida": float(saida), "som_saida": max(0.0, float(saida) + a0 - float(v0))})
        saida += Fraction(nq) / fps
    return plano


def duracao_total(plano: list[dict], fps) -> float:
    return float(sum(Fraction(p["nq"]) for p in plano) / Fraction(fps))


def montar_audio(fonte: Path, plano: list[dict], fps, saida_wav: Path, canais: int = 2,
                 pos_filtro: str = "") -> None:
    """Som de cada trecho posicionado junto da imagem e SOMADO (amix sem normalizar), com o
    tamanho exato do vídeo. `pos_filtro` (ex. "highpass=f=80,loudnorm=...") entra depois da soma.

    Trechos colados (fala contínua) viram UM pedaço só de áudio: são contínuos na fonte, e
    emendá-los na mixagem deixava até meio quadro de buraco ou de som repetido na junta.
    Posição em AMOSTRAS (adelay ...S), não em ms: 0,5 ms de erro na junta já dá estalo."""
    total = duracao_total(plano, fps)
    pedacos = []
    for p in plano:
        if pedacos and p["fade_in"] == 0:
            pedacos[-1]["a1"], pedacos[-1]["fade_out"] = p["a1"], p["fade_out"]
        else:
            pedacos.append(dict(p))
    partes, rotulos = [], []
    for i, p in enumerate(pedacos):
        d = p["a1"] - p["a0"]
        f = f"[0:a]atrim=start={p['a0']:.6f}:end={p['a1']:.6f},asetpts=PTS-STARTPTS,aresample=48000"
        if p["fade_in"]:
            f += f",afade=t=in:st=0:d={p['fade_in']}"
        if p["fade_out"]:
            f += f",afade=t=out:st={max(0.0, d - p['fade_out']):.6f}:d={p['fade_out']}"
        amostras = round(48000 * p["som_saida"])
        if amostras:
            f += f",adelay={amostras}S:all=1"
        partes.append(f + f"[a{i}]")
        rotulos.append(f"[a{i}]")
    mix = (f"{''.join(rotulos)}amix=inputs={len(pedacos)}:normalize=0:duration=longest" if len(pedacos) > 1
           else f"{rotulos[0]}anull")
    fim = f",apad,atrim=end_sample={round(total * 48000)}" + (f",{pos_filtro}" if pos_filtro else "")
    fc = ";".join(partes) + ";" + mix + fim + "[aout]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(fonte), "-filter_complex", fc, "-map", "[aout]",
                    "-ac", str(canais), "-ar", "48000", "-c:a", "pcm_s16le", str(saida_wav)], check=True)


def palavras_saida(palavras: list[dict], plano: list[dict], grupos: list | None = None,
                   ini: str = "start", fim: str = "end", texto: str = "text") -> list[tuple]:
    """Cada palavra mantida na linha do tempo de SAÍDA, pelo SOM (a palavra final de A aparece
    quando é ouvida, mesmo que a imagem já seja de B). Devolve (s, e, texto, grupo)."""
    out = []
    for k, p in enumerate(plano):
        g = grupos[k] if grupos else k
        desloc = p["som_saida"] - p["a0"]
        for w in palavras:
            if w[fim] > p["a0"] and w[ini] < p["a1"]:
                txt = w[texto]
                if w[ini] < p["a0"] and "-" in txt:
                    txt = txt.split("-")[-1]
                out.append((round(max(p["a0"], w[ini]) + desloc, 3), round(min(p["a1"], w[fim]) + desloc, 3), txt, g))
    return out


def conferir(saida_mp4: Path, plano: list[dict], fps) -> dict:
    """Mede o que dá pra medir sem ouvir: tamanho, sobreposição em cada emenda, estalo, teto."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(saida_mp4), "-vn", "-ac", "1", "-ar", "48000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(float) / 32768
    emendas = []
    for a, b in zip(plano, plano[1:]):
        corte = b["saida"]
        k = int(corte * 48000)
        salto = float(np.abs(np.diff(x[max(0, k - 144):k + 144])).max()) if len(x) > k + 144 else 0.0
        fim_som_a = a["som_saida"] + a["a1"] - a["a0"]
        emendas.append({"corte": round(corte, 3), "som_de_A_por_baixo_ms": round(1000 * (fim_som_a - corte)),
                        "salto": round(salto, 3), "colado": b["fade_in"] == 0})
    return {"total_esperado": round(duracao_total(plano, fps), 3), "emendas": emendas}
