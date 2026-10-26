# Estilo "Nick": tela dividida que desenha a fala (3 Reels)

Três Reels de ferramentas de IA analisados (v1 = "Claude can now make motion graphics", 30 s; v2 = "10 AI vibe coding tools do Google", 48 s; v3 = "5 plugins pro Claude Code", 47 s), com transcrição por palavra, folhas de 2 quadros/s e animações a 10 quadros/s nos momentos-chave.

v1 e v3 são do mesmo criador e da mesma edição. v2 é outro rosto e outra família de edição (legenda em caixa cinza, quase tudo em tela cheia, trilha por baixo). Dele a skill aproveita só duas coisas: a foto da pessoa citada e a órbita de logos. O resto do estilo sai de v1 e v3.

## A ideia que faz funcionar

Cada substantivo da fala vira imagem no mesmo segundo. Ele fala "Gemini" e o logo do Gemini cai na tela; fala "Instagram, LinkedIn, X, Reddit" e os quatro ícones nascem um por um, ligados por linha a um documento; fala "mais de 230" e um contador roda de 0 a 230 em cima do número sublinhado na página. Quem só olha entende o vídeo sem ouvir. Quem só ouve não perde nada. É didático porque a tela repete a frase em outra língua, a visual.

Segunda coisa: a prova é sempre o material real. Logo oficial do app, página verdadeira do produto, gráfico de estrelas do GitHub, a interface com o cursor clicando. Nada de ilustração genérica de "IA".

## Os três layouts (e quanto tempo cada um ocupa)

| layout | v1 (30 s) | v3 (47 s) | quando entra |
|---|---|---|---|
| dividida | 46% | 30% | explicação com prova: página, logos em sequência, gráfico, terminal |
| cheia (sem rosto) | 36% | 48% | nome de item da lista, logo grande, fluxo, ataque, antes x depois |
| rosto (close) | 17% | 22% | benefício, opinião, frase de efeito, CTA |

Troca de layout a cada 2,1 s (v3) a 3 s (v1). Dentro de cada cena acontece alguma coisa a cada ~1 s (palavra marcada, logo novo, clique, número rodando). Não existe plano médio parado: quando o rosto aparece sozinho, é close (zoom de ~1,25x no rosto).

### Dividida
- Metade de cima: fundo branco liso (v3, #FDFDFD) ou fosco claro azulado (v1, média #E9ECEE, com sombra de folhagem bem fraca). Às vezes escuro azul-marinho (v3 0 s, combinando com a arte pixelada).
- O vídeo dele vira um cartão de cantos arredondados (raio ~8% da largura) com brilho branco suave em volta, encostado no rodapé. Borda de cima do cartão entre 64% (v3) e 73% (v1) da altura.
- A cabeça passa POR CIMA da borda do cartão: cabelo e testa saem do cartão (recorte da pessoa). Topo do cabelo em ~51-58% da altura. É o que dá profundidade.
- Legenda logo acima da cabeça (centro ~75 px acima do topo do cabelo, em 1080x1920), preta.
- Elemento no espaço de cima, entre ~8% e ~45% da altura, centralizado.

### Cheia
- Fundos medidos: branco (card do item, logos, fluxo), preto (ataque hacker, logos "Veo 3"), escuro desfocado (a própria tela do app, ampliada e borrada, atrás da janela nítida), bege da marca (arte do Claude Code), cor sólida da marca citada (roxo do Jules, amarelo do Nano Banana em v2).
- Legenda em ~56-60% da altura. Em v3 ela vira serifa itálica em CAIXA ALTA (preta no branco, branca no escuro), uma ou duas palavras.

### Rosto
- Close no rosto, legenda branca no peito (~58-70% da altura), sans negrito com sombra suave.

## Elementos (o que aparece em cima)

1. **Logos que se acumulam** (v3 9-12 s). Logo novo nasce grande no centro, desfocado e um pouco menor, e assenta em 0,2 s. O anterior encolhe e desce pra uma fileira de ícones pequenos embaixo. Na 4ª marca a fileira tem os 3 anteriores. Cada logo entra na palavra do nome.
2. **Card do item da lista** (v3 14,4 / 20,6 / 27,4 / 35 s). Tela cheia branca, ícone do app num quadrado arredondado com sombra, "THE SECOND" em serifa itálica caixa alta com degradê salmão (#E79786) em cima, nome do app em serifa itálica cinza metálico embaixo. Dura ~1 s. É o separador da lista.
3. **Janela de navegador** (v1 quase inteiro). Janela do Safari desenhada (três bolinhas, barra de endereço com cadeado e URL), cantos arredondados, contorno azul fino com brilho (#548FD6). Dentro, a página real. Coisas que acontecem dentro:
   - marca-texto azul claro de seleção do macOS correndo pela frase no ritmo da fala ("each shown next to the prompt");
   - contorno azul arredondado desenhado em volta de um número (#088BFD) + balão branco com o número rodando tipo odômetro (116 → 230) e rótulo pequeno ("real examples");
   - cursor indo até um filtro e clicando: o botão ganha contorno azul na palavra falada ("product videos", "demos", "mobile app", "charts");
   - rolagem da página e troca de página por desfoque.
4. **Contador** (v1 8,5 s; v3 7,5 s). Número que roda dígito a dígito subindo, em azul (#0083FF) no balão ou na própria legenda ("over 523" → "600").
5. **Fluxo** (v3 30,4-33,4 s). Documento no centro embaixo, ícones das plataformas nascendo em arco em cima, cada um na palavra do nome, com linha curva colorida desenhando do ícone até o documento.
6. **Gráfico que se desenha** (v3 23,4-26,4 s). Gráfico de linha real (estrelas no GitHub) com a linha crescendo da esquerda pra direita durante a frase.
7. **Antes x depois** (v1 21-26 s). Duas janelas empilhadas, etiquetas em pílula ("original" preta, "remake" azul), as duas rodando o mesmo movimento.
8. **Ataque / varredura** (v3 15,4-18 s). Logo com anel girando, janela do site, linha vermelha varrendo, carimbo "BREACHED", tudo vira vermelho no "hacker". Específico de assunto; fica como modelo de "animação que encena o verbo".
9. **Logo digitando** (v3 36,4-38,4 s). Símbolo da Anthropic e o nome escrito letra por letra.
10. **Título do gancho** (v1 0-3 s). "Claude Can Now Make" em sans preta + "Motion Graphics" em serifa itálica branca numa pílula azul, em cima de uma janela com o produto rodando. "It's Called" usa a mesma pílula (v1 7 s), e em v3 "it's called" vira serifa itálica verde da marca em cima do logo.
11. **Foto da pessoa citada** (v2 0-0,5 s). Fala "todo mundo tá obcecado pelo ChatGPT" e a metade de cima mostra o Sam Altman. Pessoa citada = rosto dela na tela, sem legenda de nome.
12. **Órbita** (v2 3,5-5,5 s). Logo do Google no centro, ícones das ferramentas em anéis tracejados, título "10 AI Vibe Coding Tools" em sans itálica pesada.
13. **Mockups de interface** (v2 23,5-26 s). Três telas de celular lado a lado, título em serifa itálica.

## Legenda

- 1 a 3 palavras por bloco, centralizada. As palavras se ACUMULAM no ritmo da fala: "is" → "is over" → "is over 230". Cada palavra entra por desfoque em ~0,1 s (borrada e transparente → nítida).
- Fonte: SF Pro Display Bold (a sans do sistema da Apple). Preta (#010101) em fundo claro, branca com sombra suave em vídeo e fundo escuro. Tamanho ~72 px em 1080.
- Palavra-chave em serifa itálica azul (#3188FD): "professional", "library", "best ones", "animated", "style", "brand", "product". Número em sans azul ("230"). Uma por bloco, no máximo.
- Na tela cheia de v3: serifa itálica caixa alta ("ATTACKS", "YOUR VIBE", "INSTAGRAM").
- Sem pontuação, minúscula no começo de frase.

## CTA

Última frase em close. "comment" em serifa itálica branca pequena e, embaixo, a palavra entre aspas em SF Pro Heavy grande com degradê branco → azul (#69B4F9) e brilho azul por baixo (v1), ou branco → laranja do Claude (v3). Entra na palavra "comment" e fica até o fim. Ele aponta pra baixo com o dedo.

## Ritmo e som

- 4,1 palavras/s em v1 e v3; maior pausa 0,26 s (cortes colados, sem respiro). v2: 3,8 palavras/s, pausas de até 0,74 s.
- Roteiro: gancho com promessa e número ("5 plugins", "230 vídeos") → "it's called X" → lista com prova item a item → "go try it yourselves" → "comment X and I'll DM you the link".
- Som: v2 tem trilha contínua (o nível nas pausas fica em -22 dB, ~5 dB abaixo da voz). Em v1 e v3 as pausas são curtas demais pra afirmar trilha; picos agudos curtos coincidem com a maioria das trocas de cena grandes em v1 (2,98 / 6,4 / 8,0 / 12,7 / 18,5 / 26,1 s), o que indica um "whoosh" leve na troca. Isto é medida indireta (espectrograma), não confirmada.

## Adaptação pra quem usa a skill

- Enquadramento fechado (rosto ~41% da largura, topo do cabelo em ~12% da altura) funciona: na dividida o vídeo vai reduzido (~0,84-0,86x) dentro do cartão, com margem lateral de ~60 px, igual a v1; a cabeça sai por cima com o recorte do Vision.
- Cor de destaque: a referência usa azul de interface (#3188FD). Na skill o padrão é a cor de destaque do perfil (padrão #FFC700) e o azul fica disponível com `"destaque": "#3188FD"` no mapa. Cor clara (como o amarelo) lê mal em fundo branco: o motor dá tratamento próprio (texto preto sobre pílula/faixa, linha e número escurecidos; ver SKILL.md).
- Idioma: "THE SECOND" vira "O SEGUNDO"/"A SEGUNDA" etc.; "comment" vira "comenta".
