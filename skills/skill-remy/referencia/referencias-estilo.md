# Estilo "quadro branco que pensa junto" (Reel "Skill of the Week: Content Principles")

Origem: Reel de 61,0 s, 720×1280, 25 qps, em inglês, um episódio da série "Skill of the Week" de um criador que ensina skills do Claude pra conteúdo (crédito do estilo a esse criador).

Como foi medido: folhas de contato a cada 0,5 s, tiras de 8 quadros (a cada 1/12 a 1/3 s) em volta de cada entrada de gráfico, detecção de corte no ffmpeg, transcrição local (whisper large-v3), nível de áudio a cada 0,1 s e energia por faixa de frequência a cada 50 ms (pra achar música e efeitos), cores amostradas em pixel. Movimento e som foram lidos só nos quadros e no espectro.

Medidas em pixel no tamanho do original (720×1280). Pra 1080×1920, multiplica por 1,5.

---

## A ideia em uma frase

A metade de cima da tela vira um quadro branco de software (cards, setas, mapa mental, pastas) que desenha, no mesmo segundo, o raciocínio que ele está falando. A gente não vê "efeito": vê a explicação sendo montada como num Figma ou num Notion, com a cara dele embaixo. O vídeo parece um produto, não um Reel editado.

## Os números do ritmo

- 252 palavras em 61 s: 4,1 palavras/s. Fala rápida e sem respiro.
- Nenhuma pausa audível acima de ~0,25 s. Os dois únicos silêncios de verdade (28,6 s e 33,6 s) duram menos de 0,1 s e caem em corte.
- 21 cortes detectados. Cada corte troca enquadramento ou tomada (ele gravou o texto várias vezes, com e sem óculos, com notebook, com caderno).
- Uns 32 eventos gráficos em 61 s, mas em blocos: gráfico na tela em ~63% do tempo (38 s de 61). Os trechos só com ele duram de 2 a 5,7 s, e dentro deles há corte de enquadramento a cada ~2,5 s. Ou seja: nunca passa de ~3 s sem nada mudando.
- Legenda em blocos de 2 a 3 palavras, trocando a cada ~0,5 a 0,8 s.
- Sem música de fundo. Nos silêncios o nível cai 20 dB abaixo do resto (graves a -41 dB), o que não aconteceria com trilha por baixo. Efeitos sonoros discretos nas entradas grandes (ver "Som").

## Estrutura (o roteiro que a edição veste)

1. Gancho-problema (0 a 8,6 s): "por que a IA escreve mal mesmo depois de você dar todos os vídeos e ganchos?" A tela mostra as IAs como gente numa reunião, um cara com cabeça de máquina de escrever, e os vídeos de gancho sendo jogados no chat.
2. Diagnóstico (8,6 a 21,2 s): "ela só copia os passos". A tela desenha os passos 1-2-3, gera três roteiros iguais, risca os passos de vermelho, apaga tudo com desfoque e desenha o mapa mental "how to think".
3. Vinheta da série (21,2 a 25,7 s): título "SKILL of the week" em cima da cabeça.
4. Apresentação da skill (25,7 a 39 s): nome em cards, prova de estudo (perfis dos criadores que ele estudou), os princípios acendendo um a um.
5. Uso e prova de resultado (39 a 54,3 s): como usar, pasta da skill com os Reels feitos com ela, print de Insights com marca-texto amarelo nos números.
6. CTA (54,3 a 61 s): "comenta SKILL", palavra grande na legenda.

## Linha do tempo completa

| Tempo (s) | Plano | O que aparece | Fala |
|---|---|---|---|
| 0,0–1,5 | Médio, ele sentado na poltrona | Imagem ocupando o topo (até ~37% da altura): reunião de escritório com logos do Gemini, ChatGPT e Claude no lugar das cabeças. Entra com um fade de ~0,2 s no primeiro quadro | "Why is AI so bad at" |
| 1,5–2,7 | CORTE: mais fechado nele | Recorte (com contorno branco de adesivo) de um cara de camiseta digitando, com uma máquina de escrever antiga no lugar da cabeça, entra seco no canto de baixo à direita, na frente dele | "writing content" |
| 2,7–4,4 | CORTE para tela dividida | Quadro branco cobre o topo (borda a 42%, ~537 px). Embaixo, a mesma tomada mais aberta, a cabeça encostando na borda. No quadro: caixa de chat "Ask anything" e miniaturas de vídeos de gancho ("FIX Your HOOKS", "KILLER HOOKS", "The HOOK", "Hook Masterclass") que aparecem em sequência | "despite all of the YouTube videos and viral hooks" |
| 4,4–5,0 | idem | As miniaturas encolhem com borrão de movimento e voam pra dentro da caixa de chat, virando anexos | "that you've fed it" |
| 5,0–8,6 | CORTE: close, tela cheia, sem gráfico | Só ele e a legenda. Corte de tomada em 5,2 | "Well it's because all Claude actually takes from those videos is the steps" |
| 8,6–11,2 | Tela dividida de novo | Card "STEPS" aparece (fade ~0,15 s) e os itens entram um por fala: "01 Bold claim", "02 Numbered list", "03 Follow for more". Ao lado, um post-it cinza claro "why it works?" escrito à mão, quase apagado (o que falta) | "Step one, make a bold claim. Step two, numbered list. Step three, CTA" |
| 11,2–12,4 | idem | Do card descem linhas azuis (desenhadas da esquerda pra direita em ~0,3 s) e três cards "OUTPUT 01/02/03" entram com ~0,12 s de intervalo, todos iguais | |
| 12,4–16,4 | CORTE: tela cheia, médio; 15,8 corte pra plano aberto | Sem gráfico | "It just blindly copies the steps but completely misses the thinking behind them. The fix I've found" |
| 16,5–17,4 | Aberto | Janela com Reels antigos dele surge no alto à direita, na frente da parede, trocando 3 vezes em ~0,3 s cada, cada um com a legenda queimada original e o contador de views amarelo (103K, 423K, 496K) | "that works pretty well" |
| 17,5–18,3 | Tela dividida | Volta o quadro de passos. "Bold claim" e "Numbered list" levam risco vermelho à mão | "is to stop giving Claude" |
| 18,3–18,6 | idem | Transição: o quadro inteiro desfoca e some (~0,3 s) enquanto nasce um retângulo azul claro no centro | "steps altogether" |
| 18,6–20,2 | idem | Mapa mental: pílula azul "how to think" no centro, linhas saindo e nós brancos entrando um a um a cada ~0,2 s ("Why it hooks", "Curiosity", "Specificity", "Tension", "Payoff"). Depois três cards de exemplo sobem embaixo | "and instead teach it how to think" |
| 21,2–25,7 | CORTE: plano aberto (teto aparecendo) | "SKILL" branco enorme no espaço da parede acima da cabeça, entra com borrão de movimento em ~0,12 s. Logo depois a etiqueta azul inclinada "of the week" (letra cursiva) com um clipe de papel. Cesta vermelha em cima do K. Ele segura um caderno preto como objeto de cena | "Welcome to Skill of the Week, ladies and gentlemen, where every week I share with you one useful agent skill" |
| 25,7–28,4 | Tela dividida | Um card nasce pequeno e borrado no centro e se abre em leque de três cards (01, 02, 03, conteúdo borrado). Embaixo sobe "Content" preto e "Principles" azul com sublinhado à mão | "This week's skill is called Content Principles" |
| 28,4–30,9 | CORTE: médio, ele põe os óculos | Sem gráfico | "and it is made by yours truly" |
| 30,9–33,1 | CORTE: com notebook | Prints de perfis (YouTube do Kallaway, Mino Lee; Instagram do briarcochran, viralvideo.club) caem empilhados, um a cada ~0,4 s, cobrindo o rosto dele | "I've spent over 500 hours studying the greats of short-form content" |
| 33,1–35,3 | CORTE: mais fechado | Sem gráfico | "and distilled everything I've learned into one skill" |
| 35,3–38,9 | Tela dividida | Os três cards do leque. O card falado ganha borda azul, sobe um pouco e fica nítido; os outros ficam borrados. Acende "01 Curiosity loops", depois "02 Specificity", depois "03 Line 1 sells line 2". Em "and so on" entram mais dois cards (04, 05) atrás | "Opening curiosity loops, using specificity, line 1 has to sell line 2, and so on" |
| 39,0–44,9 | Cortes: aberto com caderno (39,2), médio (41,1), aberto (42,2) | Sem gráfico, o maior trecho limpo do vídeo (5,7 s), mas com 3 trocas de enquadramento | "Simply use this skill while making any content..." |
| 44,9–47,5 | Aberto | Card branco quadrado no meio da tela, cobrindo o rosto inteiro: pasta azul "content-principles" com contador, ramos descendo e miniaturas dos Reels dele com selo "✓ SKILL" entrando uma a uma a partir do borrão. O contador da pasta sobe junto | "I now use this skill for every single piece of content that I produce" |
| 47,6–50,0 | CORTE: médio-fechado | Sem gráfico | "In just the last 30 days, when I've really dialed in the skill" |
| 50,0–54,2 | CORTE: aberto | Painel "Insights" do Instagram (12 Sep–11 Oct: Views 1.8M, New followers 15.3K) aparece no alto, em ~0,15 s. Em "1.8 million" um marca-texto amarelo-limão passa da esquerda pra direita sobre "1.8M" (~0,25 s). Em "15,000 followers" o mesmo no 15.3K | "I've doubled my views to 1.8 million and gained an additional 15,000 followers" |
| 54,3–56,5 | CORTE: close bem fechado | Sem gráfico | "And more importantly my videos don't feel like AI slop" |
| 56,5–61,0 | CORTE: aberto | Em "comment" a legenda normal; em "SKILL" a palavra entra GRANDE, entre aspas, numa segunda linha (~2x o tamanho) | "I shouldn't even be doing this, but if you want access comment the word SKILL..." |

## O sistema visual

### Revisão (segunda leitura)

Três detalhes que a primeira leitura não pegou ou mediu errado:
- **A cabeça passa na frente do quadro.** Em todas as telas divididas a pessoa está recortada por cima do quadro branco: o topo do cabelo fica 80 a 140 px (no 720p) acima da borda, às vezes até a altura dos olhos. O quadro fica atrás dele, como uma parede. É isso que tira a cara de "tela cortada ao meio".
- **A borda do quadro fica em ~55% da altura** (708 de 1280 px em 3,6 s), não em 42%. A medida antiga pegou a base de um card, não a borda. Na imagem do gancho (0,5 s), a borda fica em 50% (635 px), e a cabeça também passa por cima.
- **O gancho é colagem.** De 0,1 a 1,5 s: foto montada no topo (reunião de escritório com os logos do Gemini, do ChatGPT e do Claude no lugar das cabeças) com ele embaixo. De 1,6 a 2,6 s: tela cheia com um recorte em primeiro plano NA FRENTE dele, preso no canto de baixo, ocupando ~57% da largura (um cara de camiseta digitando, com uma máquina de escrever antiga no lugar da cabeça). O recorte tem borda branca irregular, de papel cortado com tesoura, e entra por corte seco. As imagens sempre desenham a frase: "IA ruim em escrever" vira IAs com cabeça de logo e um cara com cabeça de máquina de escrever.
- **No quadro, imagem também conta.** As capas dos vídeos de gancho (2×2, cantos arredondados, sombra suave) aparecem em cascata no "YouTube videos and viral hooks" e voam pra dentro do chat no "fed it".

### Layout: a tela dividida em quadro branco

É o elemento principal e o que dá cara ao vídeo. Aparece 5 vezes (2,7 / 8,6 / 17,5 / 25,7 / 35,3 s) e soma ~17 s.
- O quadro branco cobre do topo até ~55% da altura (708 de 1280 px), com a cabeça dele passando por cima da borda (ver a revisão acima). Borda reta, sem cantos arredondados.
- Fundo quase branco, com um degradê leve pro cinza (#F0F0F0 a #E4E4E4). Em alguns quadros aparece uma grade pontilhada bem fraca, tipo canvas de Figma.
- Embaixo fica a tomada aberta dele, com a cabeça encostando na borda. Isso só funciona porque ele gravou essas falas num plano mais aberto: o rosto já nasce na metade de baixo.
- A legenda continua no peito dele, na mesma altura de sempre.
- Entra e sai por corte seco. Dentro do quadro, as trocas de estado são por desfoque (o quadro anterior borra e some em ~0,3 s enquanto o novo nasce).

### Variações de "quadro" fora da tela dividida
- Card quadrado centralizado (44,9 a 47,5 s), cantos retos, cobrindo o rosto dele. Corajoso: por 2,5 s não se vê a cara dele, só a prova.
- Painel solto no alto, na frente da parede (Insights em 50 s, perfis em 30,9 s, Reels antigos em 16,5 s). Aqui não há quadro branco: o print flutua sobre a sala.
- Título na parede acima da cabeça (SKILL of the week), só em plano aberto, onde há espaço de teto.
- Imagem no topo (0 s) e recorte com contorno branco na frente dele (1,5 s): só no gancho.

### Paleta medida
- Azul elétrico dos elementos de interface (pasta, pílula do mapa mental, bordas de card ativo, linhas): #1E42F0.
- Azul da etiqueta "of the week": #305ABA (mais fechado, parece fita de papel).
- Vermelho do risco à mão e da cesta: #CC422A.
- Marca-texto: amarelo-limão #E4FC00.
- Branco dos cards #FFFFFF sobre fundo #F0F0F0, texto preto.
- Fora isso, só as cores do próprio vídeo (sala bege e cinza, camiseta branca). Não há cor de marca forte: o azul é "cor de app", e é isso que faz parecer software.

### Tipografia
- Legenda: fonte pixelada (bitmap) em minúsculas, branca, com sombra preta difusa. Parece Departure Mono ou parecida (grátis). Tamanho ~26 px de altura de maiúscula no 720p. Uma linha só, 2 a 3 palavras, centralizada no peito (~67% da altura).
- Na palavra do CTA ("SKILL") a mesma fonte pixelada aparece em caixa alta, entre aspas, numa segunda linha com o dobro do tamanho.
- Interface (cards, mapa, pasta): sans geométrica arredondada (parece Satoshi, General Sans ou Inter Display) em peso médio/semibold. Números "01, 02, 03" em mono pequeno azul.
- Título da série: sans grotesca grande e apertada (tipo Helvetica Neue/Inter Display Medium), branca, ~75 px de altura. A etiqueta usa letra cursiva de pincel (parece Caveat Brush ou Kalam Bold) sobre a fita azul, inclinada uns 5°.
- Anotações à mão ("why it works?", risco vermelho, sublinhado do "Principles"): traço de caneta, irregular de propósito. É o toque humano no meio da interface limpa.

### Legenda quando o fundo é claro
Sobre o print branco dos perfis (31,9 s) a legenda aparece preta com halo branco; sobre o card de pasta (46,3 s) ela fica branca com sombra, quase sumindo. Não deu pra cravar se é um modo de mesclagem ou ajuste manual. Pra nossa skill: a legenda precisa ler em fundo claro, então vale contorno escuro fino ou trocar a cor quando cai em cima de branco.

## Catálogo de movimentos (como cada coisa entra)

O padrão é sempre o mesmo: nada aparece pronto. Ou nasce do borrão, ou se desenha, ou entra em sequência com a fala.

1. Entrada por desfoque ("blur-in"). Título SKILL, cards do leque, miniaturas na pasta: começam borrados e um pouco menores e ficam nítidos em 0,1 a 0,2 s. É o movimento mais repetido.
2. Saída por desfoque. Quando o quadro de passos dá lugar ao mapa mental, tudo borra e some em ~0,3 s. Serve de transição dentro do quadro branco.
3. Construção item a item no ritmo da fala. Cada "step one / two / three" põe uma linha no card na hora em que é dito. Cada princípio acende quando é falado. Os nós do mapa entram a cada ~0,2 s.
4. Linha que se desenha. Ramos azuis do card de passos e do mapa mental crescem do centro pras pontas em ~0,3 s, e só então os cards da ponta aparecem.
5. Entrada em cascata (stagger). Outputs 01/02/03 a cada ~0,12 s; perfis empilhados a cada ~0,4 s; miniaturas na pasta a cada ~0,3 s.
6. Foco por desfoque do resto. No leque de princípios, o card falado fica nítido com borda azul e os outros ficam borrados. É um "holofote" feito com blur, sem escurecer nada.
7. Objeto que obedece à fala. As miniaturas de vídeo voam pra dentro da caixa de chat no "you've fed it". Os passos levam risco vermelho no "stop giving Claude steps". O marca-texto passa no número quando o número é dito.
8. Contador vivo. O número da pasta sobe a cada miniatura que entra; os Reels antigos trocam com o contador de views mudando.
9. Corte seco pra imagem/recorte no gancho. Sem animação: a imagem já está lá no quadro seguinte.

Não vi zoom animado nas tomadas dele (nos quadros a cada 0,5 s o tamanho do rosto não muda dentro de uma tomada). A variação de escala vem toda do corte entre tomadas gravadas em distâncias diferentes: close, médio, aberto. E o enquadramento é escolhido pelo gráfico que vai entrar: aberto quando o gráfico ocupa o topo ou a parede, close quando a frase é só dele.

## Som

- Sem música. Voz seca do começo ao fim.
- Efeitos curtos e agudos (whoosh/pop) aparecem no espectro sem voz por trás em pelo menos: 2,7 s (quadro branco entra), 4,9 s (miniaturas voam pro chat), 7,8 s, 19,8 s (mapa mental), 21,8 s (etiqueta "of the week"), 50,9 s (marca-texto no 1.8M) e 59,2 s (palavra SKILL do CTA). Volume baixo, abaixo da voz.
- Os Reels antigos (16,5 s) entram mudos: a fala dele continua por cima. A prova ali é visual (contador de views), não sonora.
- Ressalva: sem o Gemini, os efeitos foram achados por energia de frequência alta. A posição bate com as entradas, mas o tipo exato do som (whoosh, pop, clique) precisa de ouvido.

## O que faz esse vídeo ser interessante (e não só "bonito")

1. O gráfico explica, não decora. Cada quadro branco é um diagrama do argumento: passos → três roteiros iguais → risca → mapa de pensamento. Dá pra entender o vídeo no mudo.
2. Linguagem de software. Cards, pastas, chat, Insights, mapa mental: é a interface de onde o público trabalha. Pra um vídeo sobre skill do Claude, a forma já é o assunto.
3. Construção em tempo real. Nada aparece pronto, tudo se monta na palavra exata. O olho fica preso esperando o próximo item.
4. Prova em camadas, nessa ordem: reputação (perfis dos criadores que ele estudou), uso (pasta com os Reels feitos com a skill), resultado (Insights com marca-texto). E a prova é dele mesmo, com os números reais.
5. Série com vinheta. "Skill of the Week" no meio do vídeo (não no começo) depois do gancho já ter segurado. Cria motivo pra seguir.
6. Respiro calculado. Os trechos sem gráfico caem nas frases de opinião ("ele só copia os passos", "não parece IA"), sempre num close. O contraste com os blocos densos faz o rosto pesar mais.
7. Objeto de cena por tomada. Óculos, notebook, caderno: cada tomada tem uma coisa diferente na mão, o que dá variedade sem precisar de cenário novo.

## Encaixe na skill de edição

O que a skill precisa saber fazer, em ordem de importância:
1. Tela dividida em quadro branco com a tomada aberta da pessoa embaixo, cabeça passando na frente da borda. Pede plano aberto com bastante parede acima da cabeça; se a tomada for fechada, a skill baixa o quadro e desce a imagem da pessoa.
2. Biblioteca de componentes de interface: card de lista que ganha itens na fala, ramos que se desenham, mapa mental com nós em sequência, leque de cards com foco por desfoque, pasta com miniaturas e contador, caixa de chat recebendo anexos, painel de métrica com marca-texto.
3. Anotação à mão por cima da interface: risco vermelho, sublinhado, post-it com letra cursiva.
4. Vinheta de série no plano aberto (título grande na parede + etiqueta cursiva em fita colorida + objeto pequeno). O nome da série é livre (o `titulo` aceita qualquer texto; sem série, vira o nome do produto do perfil).
5. Prova em painel solto: print real do usuário (Insights, painel de vendas, perfil) com marca-texto passando no número na hora em que ele é falado.
6. Legenda de 2-3 palavras, uma linha, no peito, com palavra do CTA grande em segunda linha.
7. Entrada e saída por desfoque como padrão; corte seco só no gancho.
8. Sem música, efeito curto só nas entradas grandes.

Escolhas da skill em relação à referência:
- Cor de interface: a cor de destaque do perfil (padrão #FFC700) no lugar do azul elétrico "de app".
- Fonte da legenda: Poppins Bold no lugar da pixelada, que é a parte mais "assinatura" desse criador; copiar igual deixa o vídeo parecido demais com o dele.
- O card cobrindo o rosto inteiro por 2-3 s (pasta) fica como na referência.

Diferença pras outras skills do pack: a /reel-glow usa tela preta com gráfico; a /reel-telao põe imagem em cima da cabeça; a /reel-prova e a /reel-papel trabalham com objetos e tíquetes. Nenhuma tem o quadro branco de interface que se constrói com a fala, que é o centro deste estilo.
