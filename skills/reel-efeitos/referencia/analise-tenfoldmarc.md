# Engenharia reversa: "17 video effects claude can create" (@tenfoldmarc)

Crédito: estilo original de Marc Cleroux (@tenfoldmarc, nicho Claude Code para não técnicos). Vídeo analisado: 29,1 s, 720x1280, 30 fps.

Como foi feita a análise: assisti frame a frame (2 fps no vídeo todo, 10 fps nas trocas), medi cor em pixel e volume do áudio com ffmpeg, e usei o Gemini para transcrição e sons. Onde o Gemini errou, está corrigido no fim.

---

## O vídeo em uma frase

Os primeiros 18 segundos são um catálogo: 17 efeitos diferentes aplicados em cima da mesma gravação dele sentado no chão, cada um durando cerca de 1 segundo, com o nome do efeito escrito grande e falado em voz alta. Só depois disso ele fala a promessa e o CTA. O efeito é a prova, e a prova vem antes do pitch.

## Linha do tempo

| Tempo | Bloco | O que acontece |
|---|---|---|
| 0,0 a 18,3 s | Catálogo | 17 efeitos, ~1,07 s cada, troca por corte seco. Título fixo no topo + contador "01/17" + nome do efeito em amarelo. Ele fala só o nome de cada efeito. |
| 18,3 a 23,5 s | Promessa | "I'm about to reveal 26 video effects that Claude can create 100% for you in the next few days." Legenda em frase, sem efeito visual. |
| 23,5 a 26,8 s | CTA comentário | "Comment STUDIO and I'll send you the invite link." Entra mockup do perfil dele no Instagram, aba de comentários, "STUDIO" sendo digitado e postado. |
| 26,8 a 28,9 s | CTA seguir | "Make sure to follow for more AI tips like this." O mesmo mockup vira o perfil e o botão Follow é tocado (azul vira "Following"). |
| 28,9 s | Fim | Último frame preto. Corte seco, sem tela de encerramento. |

Detalhe curioso: o título diz 17 efeitos e a fala diz 26. Pode ser erro, pode ser isca para comentário ("são 17 ou 26?"). Não dá para saber.

---

## A moldura fixa (o que fica igual nos 17 efeitos)

É isso que transforma 17 efeitos soltos em uma série. Vale copiar a ideia inteira.

1. Título no topo, duas linhas centralizadas: "17 video effects" em amarelo, grande, e "claude can create" em branco, menor, logo abaixo. Fica ali do efeito 1 ao 11 e some do 12 em diante (quando os efeitos precisam da tela toda).
2. Contador "01/17" pequeno, branco, em cima do nome do efeito. Ele diz quanto falta e segura quem quer ver o próximo.
3. Nome do efeito em amarelo, gigante, minúsculo, peso extra bold. Fica na altura do quadril (uns 65% da tela). A posição muda quando o efeito pede: em "green screen" sobe e fica na mesma linha do contador; em "cover story" vai para a esquerda em duas linhas; em "paper cut" o rótulo é substituído pelas próprias letras de recorte.
4. Tipografia: sans-serif geométrica bem pesada, minúscula, letras apertadas (cara de Inter Display / SF Pro Display Heavy). Sombra preta suave atrás, sem contorno duro, sem caixa.
5. Amarelo medido no pixel: **#F7E476**. É um amarelo-manteiga, mais claro e menos saturado que o #FFC700 padrão do pack. Combina com a imagem dele, que é escura e dessaturada.

## Transições

Diferente do que o Gemini disse, não existe "slide" entre os efeitos. Olhando a 10 fps:

- A troca de um efeito para o outro é corte seco. O título e o contador ficam parados, só o efeito e o rótulo mudam.
- Como cada efeito tem 1 segundo, o movimento vem de dentro do efeito (cards entrando, gráfico subindo, texto se montando), não da transição.
- Os cortes também são jump cuts entre tomadas: ele muda levemente de posição entre um nome e outro.
- Exceções que funcionam como transição de verdade: "zoom-through cut" (a câmera mergulha numa área escura até a tela ficar preta e sai no próximo) e "pull-back reveal" (o vídeo encolhe e vira uma janela dentro de outra tela).

## Os 17 efeitos, um por um

Coluna "Para nós" = se vale incorporar nas skills do pack e com o quê. Recorte de pessoa = a pessoa recortada do fundo para elementos passarem atrás dela (no pack isso já existe no /reel-glow e no /reel-telao).

| # | Nome | Tempo | O que acontece na tela | Para nós |
|---|---|---|---|---|
| 01 | orbit | 0,0 s | Cards verticais de reels dele (miniaturas de celular) giram em órbita 3D em volta do corpo. Alguns passam na frente, outros atrás dele. | Sim. Ótimo para "olha o que eu já fiz". Precisa de recorte de pessoa. |
| 02 | couch wall | 1,0 s | A parede atrás dele é preenchida aos poucos por uma colagem de prints e reels dele. Ele continua na frente. | Sim. Prova social instantânea (prints de resultado, de alunos, de posts). |
| 03 | ui world | 2,0 s | O fundo inteiro vira a interface do Claude (creme, logo serifado "Claude" no topo) e uma caixa de prompt digita "Edit my reel in my style" com cursor piscando. Ele fica na frente. | Muito, pra quem fala de IA: o cenário vira o Claude e o prompt se digita sozinho. |
| 04 | frame break | 3,0 s | O vídeo encolhe para um card arredondado sobre fundo escuro desfocado, e a cabeça dele sai para fora do card (efeito "pular da moldura"). | Sim, como abertura de bloco. |
| 05 | digital zoom | 4,0 s | Punch-in no rosto. | Já usamos. |
| 06 | phone mockup | 5,0 s | Um iPhone preto entra pela direita, ligeiramente inclinado, com brilho/sombra escura em volta. Na tela: "Edit my clips into a reel", três itens sendo marcados e botão amarelo "Done". | Sim. Ver seção de mockups. |
| 07 | checklist | 6,5 s | Card escuro translúcido no canto superior esquerdo: "EDIT WITH CLAUDE 0 of 3" com barra de progresso. Itens "Drop your clips / Trigger the skill / Post it" ganham check amarelo um a um. | Muito. Perfeito para passo a passo de tutorial. |
| 08 | headline wall | 7,5 s | Recortes de papel com manchetes ("Claude can edit your videos now"), barra de busca "can claude edit videos", cards de tweet, com marca-texto amarelo, vão grudando na parede atrás dele. | Sim. Igual ao telão, mas com manchete de notícia. Ótimo para novidade de IA. |
| 09 | zoom-through cut | 8,5 s | Zoom rápido para dentro de uma área escura até a tela ficar preta, e sai na cena seguinte. | Sim, como transição entre blocos. |
| 10 | chart grow | 10,0 s | Grade branca fina no fundo, linha branca com pontos, e de repente a linha vira amarela com brilho e dispara para cima. Passa por trás da cabeça dele. | Já temos parecido no /reel-glow. Adotar o brilho no ponto final. |
| 11 | pull-back reveal | 11,0 s | O vídeo encolhe e vira a prévia dentro da janela do Claude (fundo off-white). Um painel "Working on" entra com checklist ("Transcribed the take", "Cut 17 effect slots", "Built every effect", "Captions added", "Graded and mixed") e uma barra "rendering" com forma de onda vai enchendo. | Muito. Mostra o bastidor da IA trabalhando. |
| 12 | green screen | 12,0 s | Fundo vira preto liso. Ele fica embaixo, e um card no alto mostra outra gravação dele (outro cenário, com neon). Rótulo sobe para a linha do contador. | Sim, para mostrar antes/depois ou "eu em outro lugar". |
| 13 | paper cut | 13,5 s | Colagem de scrapbook: letras de bilhete de sequestro formando "PAPER CUT" (cada letra num papel de cor diferente), rabiscos de giz azul e vermelho, papel rasgado amarelo e kraft, papel quadriculado. Ele aparece recortado com borda branca de adesivo. | Talvez. Estilo forte, foge da identidade limpa das outras skills. Bom para conteúdo leve. |
| 14 | doodle boil | 14,0 s | Contorno branco de giz em volta da silhueta dele, tremendo (efeito "boil" de animação à mão). Coração rosa e estrelinhas amarelas sendo desenhadas ao lado da cabeça. | Sim, para momentos de emoção ou "eu amei isso". |
| 15 | vertigo | 15,0 s | Dolly zoom: o fundo aproxima enquanto ele fica do mesmo tamanho. | Sim, para frase de impacto. |
| 16 | cover story | 15,5 s | Capa de revista: "STUDIO" gigante em serifa fina (estilo Didot) atrás da cabeça, revelado de baixo para cima; moldura fina; textos pequenos "THE AI ISSUE" e "NO EDITOR REQUIRED"; embaixo, em itálico serifado, "Claude edited this reel". Rótulo vai para a esquerda. | Muito. Conversa com a Didot do /reel-autoridade. |
| 17 | glass type | 17,0 s | Texto "CLAUDE" em 3D de vidro/cromado aparece na parede atrás da cabeça, se montando letra por letra. | Sim. Alternativa ao número gigante atrás da cabeça. |

## Legenda da fala (de 18,3 s em diante)

- Não é palavra por palavra. É frase curta por vez, de 3 a 6 palavras.
- Duas linhas: a primeira branca e menor ("i'm about to reveal"), a segunda amarela e maior com a palavra-chave ("26 video effects", "100% for you", "STUDIO", "like this.").
- A linha amarela entra com desfoque que vira nítido (blur in), em uns 3 frames. A frase sai do mesmo jeito, desfocando (visível em "and i'll send you the invite link").
- Tudo minúsculo, inclusive início de frase. Só a palavra do CTA ("STUDIO") vai em caixa alta.
- Pontuação mantida: vírgula e ponto final aparecem ("in the next few days.", "if you want it,").
- Posição: na altura do peito enquanto ele fala sozinho. Quando o mockup do Instagram entra, a legenda sobe para o topo da tela, acima da cabeça, para não brigar com o mockup.
- Mesma fonte e mesma sombra dos rótulos de efeito, o que deixa o vídeo inteiro com uma identidade só.

## Mockups (o "phone mockup" e os outros)

São três tipos de tela falsa no vídeo, todos em modo escuro ou off-white limpo, nunca print cru:

1. iPhone (efeito 06). Corpo preto, cantos bem arredondados, inclinado alguns graus, brilho escuro em volta. Entra pela direita. Dentro, a interface tem fundo preto, texto branco pequeno, checks verdes/amarelos e um botão amarelo arredondado. Os itens se marcam em sequência, então o mockup tem animação interna, não é imagem parada.
2. Janela do Claude (efeitos 03 e 11). Fundo creme, logo serifado "Claude", caixa de prompt branca com sombra suave e cursor digitando. No 11, a janela tem barra de título de navegador (três bolinhas) e painel lateral flutuante.
3. Perfil do Instagram (CTA, 23,5 s em diante). Card escuro com cantos arredondados, só a parte de cima do perfil: @, foto, números (372 posts, 103K, 205), bio e botões. Fica centralizado sobre as pernas dele, com o rosto livre. Sequência:
   - abre a aba Comments com a fileira de emojis
   - "STUD..." vai sendo digitado no campo
   - um círculo de toque aparece no "Post"
   - o comentário "STUDIO" aparece publicado como "you · now", e um coração vermelho pisca
   - o card vira o perfil com a grade de reels, um toque no botão azul "Follow" e ele vira "Following"
   É o CTA mostrado como tutorial: a pessoa vê exatamente o gesto que precisa fazer.

## Áudio

- Sem música de fundo. Medi o volume nas pausas: entre -42 e -56 dB, ou seja, só ruído de sala. O vídeo é voz seca.
- Ele fala o nome de cada efeito no catálogo ("orbit", "couch wall"...). A voz dá o ritmo do corte.
- Efeitos sonoros por evento, segundo o Gemini: whoosh nas trocas, digitação no "ui world" e no comentário, clique quando card entra, "ding" no gráfico, som de papel no "paper cut", rabisco no "doodle boil", tap no Follow. Não consegui confirmar por medição; os picos de volume nas trocas batem com isso, mas podem ser a própria fala.

## Gravação

- Uma tomada só, cenário único: sala, ele sentado no chão em cima do tapete, encostado no sofá.
- Câmera bem baixa, quase no chão, olhando levemente para cima. O tapete ocupa o terço de baixo, o que deixa espaço livre para rótulos e mockups.
- Ele ocupa o centro, do quadril para cima, com muito ar acima da cabeça. Esse espaço é o que permite colocar coisas atrás da cabeça (STUDIO, CLAUDE, manchetes).
- Cor fria e dessaturada, imagem escura. O amarelo-manteiga é a única cor quente forte, então tudo que é amarelo vira foco.
- Roupa casual (boné virado para trás, camisa verde), microfone de lapela visível. Nada de estúdio: o contraste entre cenário caseiro e edição sofisticada é parte da mensagem ("a IA fez isso").

## Por que prende

1. Prova antes da promessa. Em 1 segundo você já viu um efeito que parece caro. O pitch só chega depois de 17 provas.
2. Mudança visual a cada ~1 segundo durante 18 segundos. Não dá tempo de rolar.
3. Contador 01/17. Cria a lista a ser completada.
4. Metalinguagem: o vídeo foi editado pela ferramenta que ele está vendendo ("Claude edited this reel" aparece na capa de revista). O formato é o produto.
5. Uma cor só de destaque. Tudo que importa é amarelo, o resto some.
6. CTA demonstrado no mockup. Ninguém fica em dúvida sobre o que comentar.
7. Palavra-CTA ligada ao produto ("STUDIO" é o nome do que ele entrega), não genérica.
8. Possível isca de comentário no 17 x 26.

---

## O que levar para as skills do pack

Prioridade alta (combinam com conteúdo de IA e o pipeline já tem metade):

- Moldura de série: título fixo no topo + contador "01/07" + rótulo grande. Funciona para qualquer listicle ("7 coisas que o Claude faz").
- "ui world": cenário vira a interface do Claude com prompt digitando. É o efeito mais forte pra conteúdo de IA.
- Checklist que se marca sozinho (card escuro translúcido, checks amarelos). Encaixa em todo passo a passo.
- Pull-back reveal com painel "Working on". Mostra a IA trabalhando, que é o que conteúdo de IA quer provar.
- Mockup de perfil do Instagram no CTA, com a palavra sendo digitada e o Follow sendo tocado.
- Legenda em duas linhas (branca pequena + amarela grande), com entrada e saída em desfoque, subindo para o topo quando entra mockup.
- Capa de revista com título serifado atrás da cabeça. Dá para casar com a Didot do /reel-autoridade.

Prioridade média: orbit, couch wall, headline wall, frame break, zoom-through, glass type, vertigo.

Deixar de fora, por ora: paper cut (estética de colagem que destoa das outras skills).

Pontos que o usuário decide:
- Cor: a cor de destaque do perfil (padrão #FFC700, mais viva) ou o #F7E476 da referência (`"cor"` no efeitos.json).
- Música: a referência é voz seca, igual às outras skills do pack (sem música).

---

## Correções ao que o Gemini disse

- Disse que havia música eletrônica de fundo. Não há (medido; na segunda pergunta o próprio Gemini voltou atrás).
- Disse que toda troca de efeito era "zoom-out + slide para a direita". Não é: é corte seco com título parado.
- Disse que a legenda era palavra por palavra. É frase por frase, em duas linhas.
- Disse que havia um texto amarelo "follow" acima do mockup. Não vi em nenhum frame; o "follow" é o botão do perfil sendo tocado.
- Os tempos de fala que ele deu adiantam ~1 s no fim do catálogo; a tabela acima usa os tempos dos frames.
