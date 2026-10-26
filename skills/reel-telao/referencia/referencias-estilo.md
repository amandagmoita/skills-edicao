# Estilo "telão" (B-roll em cima da cabeça)

Origem: Reel de um criador sobre o "Jun", sistema de agentes de conteúdo (81 s, 720×1280, 30 qps, em inglês).
Tudo aqui foi medido no arquivo: quadros a cada 1/30 s nos pontos de troca, transcrição com tempo por palavra (ElevenLabs Scribe), nível de áudio a cada 0,05 s. Onde o Gemini discordou da medição, vale a medição (anotado no fim).

Medidas em pixels estão convertidas pra tela de 1080×1920 (o original é 720×1280, multiplicado por 1,5).

---

## A ideia em uma frase

Ele grava uma cabeça falante comum, com bastante parede livre acima da cabeça, e usa essa parede como um telão: cada frase ganha uma imagem, um meme ou um vídeo "pendurado" em cima da cabeça. Quando o assunto é o sistema dele, a tela se divide e a metade de cima vira a tela do sistema funcionando. Dois terços do vídeo têm alguma coisa além do rosto dele na tela.

## Os números do ritmo

- 81 s, 264 palavras, 3,3 palavras/s. Maior pausa entre palavras: 0,46 s. A fala é contínua.
- 14 trocas de elemento visual em 81 s (uma a cada ~5,8 s, mas concentradas nos primeiros 66 s: uma a cada ~4,7 s).
- Tempo de tela por tipo:
  - imagem/meme/vídeo em cima da cabeça: 22,3 s (28%);
  - tela dividida: 32,2 s (40%);
  - só ele, limpo: 26,6 s (32%).
- Trecho limpo mais longo: os 15,5 s finais (65,6 s → fim), justo na parte emocional ("o objetivo não é substituir meu time"). No miolo, nunca passa de 5,3 s sem elemento.

## Linha do tempo completa

| Tempo | Elemento | O que aparece | Fala no momento |
|---|---|---|---|
| 0,0–2,8 | Colagem (3 vídeos) | Reels de outros criadores sobre "Claude editando" | "Everyone's talking about Claude editing right now" |
| 2,8–4,2 | Limpo | Legenda sobe pra parede | "but before that, it was" |
| 4,2–7,9 | Colagem (3 vídeos) | Reels de outros: "Turn Claude into a text hook machine", "your script", "Connect Claude and Instagram" | "use AI for your hooks, your scripts, your idea generation" |
| 7,9–9,8 | Meme em vídeo | Jim Carrey digitando desesperado (Todo Poderoso) | "So you copy their workflows" |
| 9,8–15,1 | Limpo | Corte com aproximação em 11,3 s | "Maybe it works once, then the next output looks totally different" |
| 15,1–17,0 | Meme imagem | Nazaré confusa com as contas | "you don't know what to prompt it" |
| 17,0–19,0 | Limpo | Corte pra plano mais fechado | "because you don't know why it worked" |
| 19,0–23,9 | Tela dividida 40/60 | 6 bolinhas "step 1…6" acendendo uma a uma, fundo preto | "All of these workflows are linear by nature… one direction" |
| 23,9–26,0 | Meme imagem | Roll Safe (cara apontando pra cabeça) com fundo de cérebros rosa | "But our human minds work more like" |
| 26,0–28,3 | Imagem ilustrativa | Cérebro de quebra-cabeça branco com peça vermelha, fundo azul | "beautiful, intelligent puzzle pieces" |
| 28,3–31,4 | Imagem ilustrativa | Peças brancas com a do meio amarela se encaixando | "a piece only fits when it can connect" |
| 31,4–33,8 | Limpo | Plano mais aberto | "So you're not bad at using AI" |
| 33,8–40,3 | Tela dividida 50/50 | Mapa de agentes dele (fundo preto, nós coloridos com brilho), câmera passeando pelo mapa | "you were just taking one linear workflow… build out the whole picture" |
| 40,3–44,8 | Prova em cima da cabeça (2 vídeos) | Grade dos Reels dele rolando + chamada de vídeo com o time | "six and a half years… posting daily and building a team" |
| 44,8–65,6 | Tela dividida 50/50 | O mesmo mapa; o cursor clica em cada agente na hora que ele fala o nome | "A director… an interviewer… a researcher… a launch planner and an offer creator" |
| 65,6–81,2 | Limpo | Corte pra outro enquadramento; CTA aos 77,0 s | "The goal here is not to replace my team…" |

---

## 1. Elementos em cima da cabeça

### Como são posicionados
- A base do elemento encosta no topo da cabeça (ou nos óculos em cima da cabeça). Na tela de 1920 de altura, a base fica por volta de y 820–840 (43–44% da altura) e o topo entre y 300 e 340.
- Centralizado na horizontal, por cima da cabeça.
- Um elemento sozinho ocupa 58–62% da largura (~630–670 px). Mantém a proporção original da imagem (16:9 no meme do teclado, 4:3 nos outros). Nunca é esticado nem recortado pra caber num molde.
- Sem borda, sem sombra, sem canto arredondado. É um retângulo chapado colado na parede. O efeito parece "recortado e colado", e é isso que dá o ar de meme.
- O enquadramento da gravação deixa a parede livre: a cabeça dele fica na altura de ~45% da tela, com ~40% de parede vazia acima. Sem isso o estilo não funciona.

### Como entram e saem
- Corte seco. No quadro anterior não existe, no seguinte já está inteiro no tamanho final. Nenhum fade, zoom ou deslize (conferido quadro a quadro em 4,17 s, 7,87 s, 15,1 s, 26,0 s e 28,3 s).
- Troca de um elemento pra outro também é corte seco, sem passar pelo vazio.
- A troca cai 0,1 a 0,25 s antes da palavra que o elemento ilustra (7,87 s → "So" 8,06 s; 15,10 s → "you don't" 15,16 s; 23,9 s → "But" 24,0 s; 26,0 s → "beautiful" 26,26 s; 28,3 s → "piece" 28,58 s). O olho chega antes do ouvido.

### Os quatro tipos que ele usa
1. **Colagem de prova social (0–7,9 s).** Três vídeos verticais de outros criadores, rodando sem som, lado a lado. Cada um com ~22% da largura (~240 px), formato 9:16, o do meio ~40–60 px mais alto que os laterais. A segunda colagem mistura formatos (quadrado preto à esquerda, vertical no meio, 4:3 à direita, levemente sobrepostos). Serve pra dizer "todo mundo está falando disso" sem precisar dizer.
2. **Meme (7,9 s; 15,1 s; 23,9 s).** Meme famoso, reconhecível em meio segundo, que traduz a emoção da frase: desespero de copiar workflow (teclado), confusão (Nazaré), "pensa comigo" (Roll Safe). Pode ser vídeo (o do teclado roda) ou imagem parada.
3. **Imagem ilustrativa (26,0–31,4 s).** Imagem de conceito, estilo render 3D limpo, que desenha a metáfora que ele está falando (cérebro de quebra-cabeça → peça que encaixa). Duas imagens em sequência contam a metáfora em dois passos: o problema (peça solta) e a solução (peça encaixada).
4. **Prova pessoal (40,3–44,8 s).** Dois vídeos dele próprio: grade do perfil rolando (prova de "posto todo dia") e chamada de vídeo com o time (prova de "montei um time"). Mesma regra de colagem, só que agora a prova é dele.

---

## 2. Tela dividida

- Corte seco pra dentro e pra fora, igual aos elementos.
- Metade de cima: gráfico ou gravação de tela em fundo quase preto (#000000 no gráfico de passos, #060710 no mapa de agentes). Ocupa a largura toda, sem moldura.
- Metade de baixo: a mesma gravação dele, reenquadrada pra caber (cabeça e tronco; rosto por volta de 60–65% da altura total).
- A proporção muda conforme o conteúdo:
  - gráfico de passos (19,0 s): divisão em 40/60, linha em y ~777 de 1920;
  - mapa de agentes (33,8 s e 44,8 s): divisão em 50/50, linha em y ~960.
- O que vai em cima é sempre o "como funciona por dentro":
  - **Gráfico animado simples** (19,0–23,9 s): seis bolinhas com "step 1…6" acendendo da esquerda pra direita, uma a cada ~0,5 s, desenhando a palavra "linear". Visual mínimo, cinza e branco sobre preto.
  - **Tela do sistema de IA dele** (33,8–40,3 s e 44,8–65,6 s): o mapa dos agentes (Director, Interviewer, Researcher, Scriptwriter, Repurposer, Launch Planner, Offer Creator) como uma constelação com brilho colorido. Primeiro a câmera passeia pelo mapa todo; depois o cursor clica em cada agente e o mapa dá zoom nele, mostrando as tarefas daquele agente em volta.
- Sincronia do clique com a fala: cada agente ganha foco 0,2–0,3 s antes de ser falado (Director em 46,5 s, falado em 46,72 s; Interviewer 51,3 s / 51,64 s; Researcher 56,1 s / 56,4 s; Repurposer 60,5 s / 60,82 s; Launch Planner 63,3 s / 63,58 s). A gravação de tela foi editada pra bater com a voz, não o contrário.

### O que "mostra que é feito com IA" neste vídeo
Ele não usa imagem com selo de IA. O que prova IA é a tela dividida com o sistema de agentes funcionando: nome de agente, tarefas em volta, cursor clicando. A sensação de "isso é IA de verdade" vem da interface, não de uma imagem gerada. As imagens ilustrativas (cérebro, quebra-cabeça) parecem banco de imagem ou render; não dá pra afirmar se são geradas por IA.

---

## 3. Legenda

- Uma palavra por vez, trocando junto com a fala (média de 0,3 s por palavra).
- Branca, sans geométrica de peso médio/seminegrito (parecida com Montserrat SemiBold), sombra suave escura. Sem contorno, sem caixa, sem cor de destaque, sem emoji.
- Minúscula como falada; nome próprio mantém maiúscula ("Claude", "AI"). Sem pontuação.
- Tamanho: ~90 px de corpo na tela de 1080 (a palavra "generation" ocupa ~43% da largura).
- **A posição muda pra fugir do que está na tela:**
  - com elemento em cima da cabeça: legenda no peito, y ~1390–1420 (72–74%); na prova do time, um pouco mais alta, y ~1230 (64%);
  - na tela dividida: também no peito da metade de baixo, y ~1350–1500 (70–78%);
  - sem nada em cima da cabeça: a legenda sobe pra parede, acima da cabeça, y ~540 (28%).
- A regra prática: a legenda ocupa o espaço vazio que sobrou. Nunca fica em cima do rosto nem em cima de um elemento. O salto pra parede nos trechos limpos também serve pra preencher o espaço que o elemento deixou.

## 4. CTA

- Aos 77,0 s, na palavra "stories", entra "follow for part 2" no estilo de texto nativo do Instagram: caixa branca de cantos arredondados, texto preto em negrito, centralizado no peito (y ~1290). Fica até o fim (4,2 s).
- Enquanto o CTA está na tela, a legenda volta pra parede, acima da cabeça.
- "Parte 2" transforma o vídeo em série: motivo pra seguir.

## 5. Cortes e enquadramento

- Fala contínua, sem respiro entre tomadas.
- Trocas de enquadramento por corte seco (sem zoom animado): 11,3 s (aproxima), 17,0 s (mais fechado), 31,4 s (abre), 46,5 s, 56,1 s, 65,6 s, 73,3 s, 76,2 s. Ele alterna entre plano médio e plano um pouco mais fechado.
- Ele juntou tomadas de dias diferentes (óculos na cabeça em umas, coque em outras). Continuidade de visual não importa.
- Câmera fixa, frontal, altura dos olhos. Cenário: parede clara, luminária dourada acesa atrás, notebook fechado na frente, monitor na lateral esquerda.

## 6. Som

- Música de fundo do começo ao fim, baixa: nas pausas entre palavras o nível fica entre −24 e −30 dB, contra −13 a −18 dB da voz (música ~10–15 dB abaixo). O som das pausas tem graves tonais (40–120 Hz), sinal de música, não ruído de sala.
- Os vídeos e memes em cima da cabeça entram mudos.
- Efeito sonoro: não confirmei um padrão. O Gemini listou "whoosh/pop" em quase toda entrada, mas a medição de agudos só mostra pico isolado em 19,0 s (entrada da tela dividida) e 28,3 s (peça do quebra-cabeça), sem padrão em 26,0 s e 44,8 s. Se tem efeito, é discreto e não está em todas as entradas.

## 7. Estrutura do roteiro (a ordem dos elementos segue o argumento)

1. **Gancho com prova social (0–8 s):** "todo mundo está falando de X" + colagem de vídeos de outros criadores sobre X.
2. **Dor com meme (8–19 s):** o que dá errado quando você copia o workflow dos outros. Um meme por emoção.
3. **Conceito desenhado (19–31 s):** tela dividida com gráfico simples (linear) → imagens da metáfora (quebra-cabeça).
4. **Virada (31–34 s):** "você não é ruim em IA", trecho limpo.
5. **Prova + sistema (34–66 s):** prova pessoal (perfil + time) em cima da cabeça → tela dividida com o sistema de IA, um clique por agente falado.
6. **Fecho humano + série (66–81 s):** sem elemento, foco no rosto, "follow for part 2".

---

## Como adaptar pro seu conteúdo

- **Gravação:** câmera mais baixa ou mais afastada que o habitual, cabeça por volta de 45% da altura, 40% de parede livre acima. É a mudança mais importante na hora de gravar.
- **Prova social do gancho:** colagem de 3 Reels (BR ou gringos) sobre o tema do dia, rodando mudos em cima da cabeça.
- **Memes:** de preferência memes que o seu público reconhece na hora (Nazaré confusa é BR). Vale montar um banco de memes por emoção: desespero, confusão, "pensa comigo", vitória, choque.
- **Imagem ilustrativa da metáfora:** gerada com IA (gpt-image ou similar) no mesmo estilo render 3D limpo de fundo chapado. Duas imagens por metáfora: problema e solução.
- **Tela dividida "feito com IA":** gravação de tela do seu sistema de verdade (Claude Code, um painel, uma automação) com o cursor clicando em cada parte na hora em que o nome é falado. Onde não houver tela real, um gráfico simples animado (passos acendendo, fluxo) em fundo escuro. Também dá pra usar imagem gerada por IA na metade de cima.
- **Prova pessoal:** grade do seu perfil rolando, print de venda, painel de números.
- **Legenda:** palavra por palavra, branca, que muda de lugar pra fugir dos elementos.
- **CTA:** "parte 2" vira série; ou uma palavra-CTA de comentário (costuma render mais comentário que "siga pra mais").

## Divergências com o Gemini (vale a medição)

| Ponto | Gemini disse | Medição mostrou |
|---|---|---|
| Entrada das imagens | zoom/escala, cantos arredondados, sombra | corte seco, tamanho final no 1º quadro, canto reto, sem sombra |
| Entrada da tela dividida | desliza de cima com "bounce" | corte seco |
| Zoom nas tomadas | zoom animado em 0:10 e 0:13 | só corte seco com troca de enquadramento (11,3 s) |
| Meme do teclado | Christian Bale | Jim Carrey em "Todo Poderoso" |
| Efeitos sonoros | whoosh/pop em quase toda entrada | sem padrão confirmado; picos só em 19,0 s e 28,3 s |
