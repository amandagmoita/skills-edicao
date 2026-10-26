---
name: reel-editor
description: >
  Edita um Reel/vídeo vertical (talking-head) no estilo de um VÍDEO DE REFERÊNCIA
  do Instagram/TikTok/YouTube — faz engenharia reversa do modelo (cortes, ritmo,
  legendas, gráficos, SFX) e reproduz no vídeo do usuário. Se NÃO houver referência,
  analisa o próprio vídeo, escolhe os melhores trechos, remove pausas/espaços vazios
  e entrega o corte final guiado pela transcrição. Usa as skills do HyperFrames como
  sub-agentes para os gráficos/animações, libass para legendas karaokê, ffmpeg para
  corte/cor/zoom/composição e (se instalado) o MCP gemini-video para "assistir" a referência.
  Gatilhos: "editar reel", "edita meu vídeo", "reel no estilo de", "edição de reel",
  "cortar pausas do vídeo", "transformar em reel", "/reel-editor". Idioma: PT-BR.
metadata:
  tags: reel, edição de vídeo, hyperframes, gemini, legendas, talking-head, instagram, ffmpeg
---

# 🎬 Reel Editor — edição de Reels guiada por referência

> ## 🔄 SKILL VIVA — ATUALIZE-SE A CADA APRENDIZADO
> **Esta é uma skill viva.** Sempre que, durante uma edição, surgir um novo aprendizado
> (um truque de ffmpeg, um bug e seu workaround, uma decisão de estilo que funcionou ou
> não, um parâmetro melhor, um formato que o CapCut leu/não leu, uma preferência do
> usuário), **registre no `## 📚 Log de Aprendizados` no fim deste arquivo ANTES de
> encerrar** — e, se for uma regra de processo, atualize a etapa correspondente. O objetivo
> é que cada Reel saia melhor e mais rápido que o anterior. Não deixe o aprendizado só na
> conversa: ele tem que voltar pra cá.

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do
Instagram, cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado
pessoal: a cor de destaque é o acento visual dos gráficos, e o CTA usa o produto/link e o @ do perfil.
Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher o arquivo.

---

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack.
O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê de cada
número) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem
fazer outro corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill (corte montado à mão no ffmpeg): NUNCA cortar áudio e vídeo juntos por trecho. Seguir os
  passos do `corte-sobreposto.md`: `CS.planejar` → vídeo SEM áudio de cada trecho (`v0`, `nq`) → concat →
  `CS.montar_audio` (som sobreposto) → juntar. Legendas pelo som: `CS.palavras_saida`. Conferir com `CS.conferir`.

---

## 0. O que esta skill faz
Pega um vídeo vertical (talking-head, com rosto) e entrega um **Reel editado**:
corte + ritmo + 9:16 + cor + áudio tratado + **legendas karaokê** + **gráficos/animações**
+ **SFX**, no estilo de uma referência (Modo A) ou auto-otimizado (Modo B).

**Entrega sempre 2 coisas:**
- `REEL_PRONTO.mp4` — versão final composta, pronta pra postar.
- `pacote-capcut/` — camadas separadas pra ajuste fino no CapCut (ver §7).

## 1. Inputs
- **Vídeo do usuário** (obrigatório) — o talking-head a ser editado.
- **Vídeo de referência** (opcional, mas é o padrão) — link ou arquivo. Define o estilo.
- **Transcrição** (opcional) — se vier, usa; senão, gera com Whisper.

> **Pergunte no começo:** "Tem um vídeo de referência?" → **Modo A**. Se não → **Modo B**.

## 2. Setup (uma vez por máquina) — ferramentas + ⚠️ gotchas
Tudo offline, sem Homebrew. Detalhes e armadilhas (NÃO repita os erros):
- **ffmpeg/ffprobe**: `ffmpeg-static` (npm) dá o ffmpeg arm64; o **ffprobe** do `ffprobe-static`
  vem rotulado errado (x86) → usar **`@ffprobe-installer/ffprobe`** (arm64 real). Symlink em `~/.local/bin`.
  npm bloqueia install-scripts → rodar `node node_modules/ffmpeg-static/install.js` e `chmod +x` manual.
- **yt-dlp**: binário standalone macOS (`yt-dlp_macos`) em `~/.local/bin`. Instagram exige login →
  se falhar, peça o usuário baixar o reel manualmente.
- **HyperFrames**: `npx -y hyperframes` (Node ≥ 22). `hyperframes browser ensure` baixa o Chrome de render.
- **Whisper** (transcrição PT): o hyperframes COMPILA whisper.cpp (precisa `cmake` → `pip install --user cmake`).
  ⚠️ **BUG**: `hyperframes transcribe` passa `--dtw large-v3` (hífen) mas whisper.cpp espera preset
  **`large.v3`** (pontos). Workaround: rodar `whisper-cli` direto:
  `~/.cache/hyperframes/whisper/whisper.cpp/build/bin/whisper-cli --model .../ggml-large-v3.bin
   --language pt --dtw large.v3 --max-len 1 --split-on-word --output-json-full --output-file <out>`.
  `--split-on-word` é o que dá palavras limpas pra legenda karaokê.
- **MCP gemini-video** (opcional, não vem no pack): servidor MCP com a tool `gemini_analyze_video`
  (params `prompt` + `video_path`/`youtube_url`). Precisa `GEMINI_API_KEY`.
  ⚠️ Gemini **não lê link do Instagram** — baixe o arquivo e mande por `video_path`.
  Sem esse MCP: extrair quadros com ffmpeg (2 fps no vídeo todo, 10 fps nas trocas) e ler as imagens,
  medir cor em pixel e volume com ffmpeg, e transcrever com o Whisper.

## 3. MODO A — com vídeo de referência (padrão)
O **Gemini é quem "assiste"** a referência (ou, sem o MCP, os quadros extraídos); você (Claude) orquestra.

1. **Obter a referência**: `yt-dlp` o link → `referencia/`. Se travar (login), peça o arquivo.
2. **Estudar o modelo** (gemini-video MCP): chame `gemini_analyze_video` com um prompt estruturado
   pedindo, com timestamps: duração/energia, estrutura (hook→desenvolvimento→CTA), nº de cortes e
   duração média de plano, **estilo das legendas** (fonte, cor, caixa, posição, animação palavra-a-palavra),
   zoom/punch-ins, b-roll/overlays, color grade, SFX, e uma **"receita replicável"**. Salve em `mapa-de-estilo.md`.
3. **Analisar o vídeo do usuário** (gemini-video): conteúdo por blocos com timestamps, hook, **CTA
   existente** (transcreva exata), ideias pra ilustrar (b-roll/gráfico/tela dividida) e beats de energia.
4. **Roteiro** (`roteiro-edicao.md` + `roteiro-producao.md`): cruze o estilo da ref. com o conteúdo do
   usuário. Defina o corte (quais trechos manter, com timestamps reais da transcrição), e **cena a cena**
   os gráficos com **PROMPT/BRIEF de cada um**, zoom, SFX, legenda. **Aprove com o usuário antes de produzir.**
5. **Produza** (§5) e **entregue** (§7).

## 4. MODO B — sem referência (auto-otimização)
Sem modelo pra imitar → o objetivo é um corte limpo e dinâmico do próprio vídeo:
1. **Transcreva** (Whisper, §2) → palavras + frases com timestamps.
2. **Remova espaços vazios**: detecte silêncios/pausas longas (`ffmpeg silencedetect` ou gaps na
   transcrição > ~0.4-0.6s) e corte. Tire também repetições/hesitações óbvias.
3. **Escolha os melhores trechos**: priorize hook forte + densidade de informação; se a transcrição
   existir, monte o corte por frases coerentes (não corte no meio de palavra).
4. **Padrão do pack**: legendas karaokê (branco/caixa cinza), 9:16, cor com leve pop,
   áudio -14 LUFS, punch-ins nos beats, CTA mantida. Gráficos só se agregarem.
5. Entregue (§7). (Se o usuário quiser, depois vira Modo A com uma referência.)

## 5. Produção (as 5 etapas) — ordem fixa
Use o **ffmpeg** pro vídeo/áudio e **dispare sub-agentes HyperFrames** pros gráficos.

1. **Base** (ffmpeg): cortar os trechos **com sobreposição** (seção "Corte das falas": vídeo e som
   separados pelo módulo `corte_sobreposto.py`) → `base_cut`; depois **cor**
   (`eq=contrast=1.06:saturation=1.12` + leve unsharp) + **áudio** (`highpass=80,acompressor,loudnorm=I=-14:TP=-1.5:LRA=11`)
   → `base_treated`; depois **punch-in zooms** (`scripts/gen_zoom.py` → filtro `zoompan`) → `base_final`.
2. **Legendas karaokê** (libass, `scripts/gen_captions.py`): remapeia timestamps (origem→corte),
   gera `.ass` (uma palavra/vez, pop, MAIÚSCULAS, **caixa cinza @55%**, terço inferior, fonte Poppins/Montserrat)
   e `.srt` por frases. Renderiza camada transparente:
   `color=...:format=rgba,colorchannelmixer=aa=0,subtitles=legendas.ass:fontsdir=fonts:alpha=1,format=yuva444p10le`
   → ProRes 4444. ⚠️ Sem `colorchannelmixer=aa=0`+`:alpha=1` o alpha sai preto.
3. **Gráficos/animações** → **SUB-AGENTE HyperFrames** (§6). Uma composição HTML transparente (1080×1920),
   tudo no **terço superior** (headroom) pra não cobrir rosto nem legenda. Render `--format mov`
   (~1,5 min pra 54 s de vídeo).
   ⚠️ `.badge` precisa `white-space:nowrap`. ⚠️ `data-duration` define a duração do .mov → gera cauda
   congelada → aparar no fim da fala. O GSAP preserva o `translateX(-50%)` do CSS (centralizar assim é seguro).
3b. **STORYBOARD pro usuário aprovar (obrigatório, ANTES de renderizar os gráficos e a composição final).**
   Com `base_final`, o `.ass` e a composição HyperFrames já escrita (sem render), tirar os quadros dos
   momentos: `npx hyperframes snapshot --at t1,t2,...` (um tempo por gráfico/zoom/transição, quando
   o elemento já está inteiro) e montar a página com o gerador comum:
```python
import sys, subprocess; from pathlib import Path; from PIL import Image
sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao")); import storyboard as SB
def quadro(t):   # quadro do corte + legenda queimada + snapshot dos gráficos (PNG transparente) em t
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", "base_final.mp4", "-vf",
                          "subtitles=legendas.ass:fontsdir=fonts", "-frames:v", "1", "-f", "image2pipe",
                          "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    im = Image.open(__import__("io").BytesIO(raw)).convert("RGBA")
    gfx = Path(f"snapshots/t{t:.2f}.png")          # caminho que o snapshot gerou pra esse tempo
    if gfx.exists(): im.alpha_composite(Image.open(gfx).convert("RGBA").resize(im.size))
    return im
SB.gerar(Path("."), "Reel Editor", total, cenas, momentos, quadro, avisos)
# cenas: uma por frase do corte [{"t0","t1","fala"}]; momentos: [{"t0","t1","quadro","tipo","desc"}]
```
   Mandar `storyboard.html` com `SendUserFile` (`display: render`) e esperar o "aprovado" do usuário.
   Pedido por código ("4B: ...") → mudar o roteiro/composição e gerar de novo. Só depois renderizar
   (passo 3 e 5). Na 1ª vez, conferir o caminho real dos PNGs que o `snapshot` gera e ajustar `gfx`.
4. **SFX** (`scripts/gen_sfx.py`): sintetize whoosh/pop/ding/key no ffmpeg (não há sfx locais, só manifest)
   e monte a trilha com `adelay+amix:normalize=0+alimiter`, posicionada nas transições/entradas.
5. **Composição final** (ffmpeg): `base_final` + `gfx_overlay` + `legendas_overlay` + (voz `amix` SFX) →
   `REEL_PRONTO.mp4`. Aparar no fim da fala. Verificar com `ffprobe` + ler frames.

> **Verifique SEMPRE visualmente**: extraia frames (`ffmpeg -ss t ... -frames:v 1`) e leia as imagens
> (você é multimodal) antes de declarar pronto. Compare lado a lado com o `mapa-de-estilo.md`.

## 6. Sub-agentes HyperFrames (gráficos)
Dispare um sub-agente (Agent tool) instruído a **usar as skills do HyperFrames** pra autorar a composição:
- `/hyperframes-core` (contrato `data-*`, clips, tracks, timeline GSAP paused em `window.__timelines`),
- `/hyperframes-animation` (entradas: pop/`back.out`, slide, stagger; pulsos finitos, seek-safe),
- `/hyperframes-creative` (paleta/tipografia/composição),
- `/hyperframes-cli` (lint → render `--format mov`).
Passe pro sub-agente: o `roteiro-producao.md` (cena a cena), a paleta/acento (acento = `cor_destaque` do
perfil), a fonte (embutir via @font-face) e os PROMPTS/BRIEFS de cada gráfico. UI de produto (ex.: Claude)
imita o app real, não um mockup genérico. Peça composição **transparente**, elementos no terço superior, e os
arquivos `.mov` renderizados. (Para legendas "dentro da cena"/cinematográficas dá pra usar uma skill de legenda embutida, se
estiver instalada; mas para o estilo simples branco-em-caixa-cinza + camada separada, libass é melhor.)

## 7. Entregáveis + ⚠️ CapCut
O CapCut (sobretudo no celular) **não importa vídeo com fundo transparente**. Por isso entregue os gráficos
em **chroma key** (fundo magenta `#FF00FF`, **sem sombras** — `box-shadow/text-shadow/filter: none`) pro
usuário remover com o Chroma/Croma. E legendas como **SRT** (texto nativo editável).
```
projeto-reel/
├─ REEL_PRONTO.mp4                 ← final composto, pra postar
└─ pacote-capcut/
   ├─ base_tratada.mp4             ← vídeo (corte+cor+áudio+zoom)
   ├─ gfx_chromakey.mp4            ← gráficos em fundo magenta (Chroma Key) ✅ celular+PC
   ├─ legendas.srt                 ← legendas editáveis (importar) ✅ celular+PC
   ├─ gfx_overlay.mov              ← gráficos com alpha real (só desktop)
   ├─ legendas_overlay.mov         ← legendas com alpha real (só desktop)
   ├─ sfx/                         ← whoosh/pop/ding/key soltos
   └─ montagem.md                  ← guia de remontagem no CapCut
```
A **música** é escolhida pelo usuário no fim (deixar a voz dominante). Os roteiros (`mapa-de-estilo.md`,
`roteiro-edicao.md`, `roteiro-producao.md`) ficam na pasta do projeto.

## 8. Scripts auxiliares (em `scripts/`)
- `gen_zoom.py` — gera o filtro `zoompan` a partir de um JSON de janelas de zoom.
- `gen_captions.py` — gera `.ass` (karaokê) + `.srt` a partir do transcript de palavras + mapa de corte.
- `gen_sfx.py` — sintetiza SFX e monta a trilha a partir de um JSON de eventos.
Todos são parametrizados por JSON/args — ver o cabeçalho de cada um.

---

## 📚 Log de Aprendizados
> Adicione no topo (mais recente primeiro): `AAAA-MM-DD — aprendizado → o que mudou`.
- (registrar aqui novos aprendizados, com data)
