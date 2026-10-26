# Corte com sobreposição — padrão de TODA edição de Reels do pack

Calibrado em 6 rodadas de teste até a emenda ficar contínua, sem respiro e sem "pulo" de imagem.
Vale pra qualquer estilo de edição, das skills que já existem e das que forem criadas.
O estilo muda os gráficos, as legendas e os efeitos. O corte das falas é sempre este.

## O que acontece em cada emenda entre duas falas (A → B)

```
vídeo: |------ A ------|------ B ------
som A: |------ A ---------\
som B:                 |------ B ------
```

| medida | valor | o que é |
|---|---|---|
| `CEDO_S` | 0,10 s | o vídeo de A sai 0,10 s antes de a voz de A terminar |
| `RABO_S` | 0,06 s | o áudio de A continua até 0,06 s depois da voz, por baixo do vídeo de B |
| `FADE_RABO` | 80 ms | o áudio de A some nesse tempo |
| `FOLGA_S` | 0,04 s | B começa 0,04 s antes da voz (fade de entrada de 30 ms) |

- As duas falas ficam sobrepostas por ~0,16 s, **somadas** (amix sem normalizar, sem baixar o volume).
- Não sobra pausa vazia entre as falas.
- A imagem de B entra no quadro mais próximo do início do som de B. A diferença entre som e imagem é de no máximo meio quadro (≤ 21 ms a 24 qps), menos do que o olho percebe.
- **Fala contínua** na fonte (tomadas que se tocam, divisão de zoom sem pausa) junta exata, sem sobrepor e sem fade.
- O último trecho termina normal: o som vai até a voz + o rabo, e a imagem acaba junto com ele.

## O que não funcionou na calibragem (não repetir)

1. A imagem de B entrando 0,5 s antes da voz de B mostrava a pessoa calada olhando o roteiro.
2. Diminuir essa entrada (0,2 s, 0,1 s, rente à voz) melhorou, mas a emenda continuou se notando.
3. Nem tirando a folga resolveu: o problema era o **fim de A**, cortado depois da voz e com silêncio.
4. Com a sobreposição a emenda sumiu; a folga de 0,04 s antes de B evita abafar a primeira sílaba.

## Como usar

Código único: `~/.claude/padroes-edicao/corte_sobreposto.py` (rodar com `~/Developer/video-use/.venv/bin/python`).

```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
import corte_sobreposto as CS

# 1. trechos na ordem de saída, com onde a voz começa/termina na fonte
#    (afinar com CS.bordas_finas(fonte, ini, fim, limiar_de_voz - CS.ABAIXO_DB))
plano = CS.planejar([{"voz_ini": 7.09, "voz_fim": 9.44}, {"voz_ini": 23.18, "voz_fim": 26.37}], fps)
# 2. vídeo SEM áudio: de cada trecho, p["nq"] quadros a partir de p["v0"]
#    ffmpeg -ss {v0 - 0.5/fps} -i fonte -an -vf "trim=end_frame={nq},setpts=PTS-STARTPTS" ...
#    (o -ss meio quadro antes + trim por quadro garante o quadro certo; sem isso a imagem pula 1 quadro)
# 3. som sobreposto do tamanho exato do vídeo
CS.montar_audio(fonte, plano, fps, edit / "audio.wav")
# 4. concat dos vídeos (-c copy) + audio.wav → base
# 5. palavras pra legenda/efeitos pelo SOM: CS.palavras_saida(palavras, plano, grupos)
# 6. CS.conferir(saida, plano, fps) → sobreposição em cada emenda (~150-180 ms) e estalos
```

Quem já usa: o `cortar.py` compartilhado (reel-glow, reel-garrafal, reel-numerado, reel-papel,
reel-prova, reel-telao, reels-kelsey, reels-nick, skill-remy, skill-iphone, reels-jessi), o `cortar.py` da reel-autoridade
e as instruções da reel-editor. Skill nova de edição de Reels: copiar o `cortar.py` compartilhado
(ele já importa este módulo) ou chamar o módulo direto. Nunca implementar outro corte.

## Conferir antes de entregar (não dá pra ouvir, então medir)

- A sincronia da imagem: o quadro de saída 1 s dentro de cada fala tem que bater com o quadro da fonte (−1/0/+1 → 0).
- `CS.conferir`: o som de A por baixo de B fica entre ~140 e 180 ms em cada emenda não colada, e o salto no ponto do corte fica pequeno, perto do salto da própria voz.
- Volume no teto: comparar com a fonte. Gravação de celular costuma já bater no teto, e a soma não pode piorar isso nas emendas.

