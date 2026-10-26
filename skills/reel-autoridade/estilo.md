# Estilo "autoridade" — o padrão que a skill reproduz

Referência: Reel do Jordan Belfort sobre cold call (54s, vertical).

## A ideia em uma frase
Cabeça falante simples, gravada uma vez, e a edição troca alguma coisa na tela a cada 1–2
segundos: legenda nova, palavra-chave saltando, número gigante, tela preta com metáfora.
O original tem só 9 cortes de cena em 54s; o resto do ritmo é legenda + zoom + som.

## Paleta
- Branco nas legendas, preto nas telas pretas, UMA cor de destaque.
- Original: amarelo #F8D810. Na skill: a cor de destaque do perfil (`cor` no `mapa.json`,
  preenchida pelo `rascunho_mapa.py`). Nos campos do mapa ela ainda se chama "rosa".
- Nada de outra cor. Se o objeto 3D tiver cor, tudo bem; o texto não.

## Legenda (o elemento que mais aparece)
- Poppins Bold, branca, sombra preta suave (sem caixa, sem contorno).
- 2 a 4 palavras por tela. Troca no ritmo da fala, sem karaokê.
- Na altura do peito / em cima do microfone, NUNCA no rodapé.
- Palavra-chave: vai pra uma 2ª linha, CAIXA ALTA, ~1,6x maior, na cor de destaque.
  Ex.: "they hear one word" / **SALESMAN**. Uma chave a cada 2–4 blocos, não mais.
- Frases de fecho (as 2–3 últimas, ou a frase-tese) inteiras na cor de destaque.
- Entra PALAVRA POR PALAVRA, cada palavra no lugar fixo da frase inteira (nada anda quando a
  próxima entra), com "pop" (cresce de 65% a 100% com leve passada em ~0,13 s) no tempo da fala.
- Some quando um título está no ar.

## Número-tese gigante atrás da cabeça
- Quando a fala tem um número que resume a tese (4 segundos, 60 segundos, 3x, R$ 10 mil).
- Branco, listrado na horizontal (persiana), brilho leve, sufixo menor ("4" grande, "s" menor).
- A pessoa fica NA FRENTE (recorte pelo Apple Vision). Se o enquadramento for tão fechado
  que a pessoa cobre mais de 65% do número, ele vai pra frente sozinho.
- Entra encolhendo (122% → 100%) e cresce devagar até sair. No máximo 2 por vídeo.

## Tela preta com metáfora
- Fundo quase preto, luz suave no centro, granulado animado.
- As palavras do trecho entram uma a uma quando são faladas, centralizadas no terço de cima.
  As palavras-conceito na cor de destaque.
- Um objeto 3D realista sozinho no meio-baixo da tela, entrando de baixo e flutuando.
  O objeto é a METÁFORA literal do conceito: ampulheta = tempo, diamante = valor,
  homem de terno com maleta = vendedor, prédio = empresa.
- 2 a 3 por vídeo, cada uma de 1,5 a 4 s. A voz continua por baixo.

## Objeto 3D surgindo atrás da cabeça (o mais usado do estilo)
- Como o iPhone e o globo do Belfort: objeto grande (50–66% da largura) que SOBE de trás da
  cabeça em 0,5 s, cresce de 55% a 100%, flutua e some encolhendo. A pessoa fica sempre na
  frente (máscara). Centro na altura da testa: metade de cima aparece.
- NO MÁXIMO 4 por vídeo (mais que isso fica excessivo): o gancho + as 3 ideias mais concretas
  da fala (fora do horário → lua, jurídico → balança, lembrete → sino). Nunca junto de título.
- Sempre que der, com um detalhe na cor de destaque (balão, check, olhos do robô), o resto realista.

## Título em fonte de destaque
- Didot Italic (`/System/Library/Fonts/Supplemental/Didot.ttc`, índice 1), na cor de destaque, até
  250 px de altura e 94% da largura, com uma linha pequena em Poppins branca em cima ("a lista de" /
  *documentos*).
- ATRÁS da cabeça (máscara do Vision): a palavra fica acima da cabeça e só o terço de baixo
  passa por trás do cabelo. Centrada no topo da cabeça, a cabeça comia o meio da palavra.
- Entra subindo 50 px e encolhendo de 110% a 100% em 0,3 s; whoosh baixinho.
- 1 a cada 6–7 s. A palavra é a que a pessoa está falando (não inventar "sozinho" se ela disse
  "automaticamente").

## Transição: zoom punch nas emendas
- Na emenda que abre frase nova, o vídeo de baixo entra 16% mais perto e volta a 100% em
  0,28 s (curva cúbica), com desfoque nos 0,1 s iniciais e whoosh. Legenda e títulos não
  mexem. Fora das telas pretas. É a única transição do estilo (flash branco e tremida não entram).

## Sticker
- Ícone pequeno numa moldura quadrada tracejada na cor de destaque, acima da cabeça (globo = "o
  mundo deles").
- 0 a 2 por vídeo, 1,5 a 2,5 s.

## Gancho (0–3 s)
- Frase de proibição ou de erro comum, terminando em aberto ("Nunca abra uma ligação com…").
- Um objeto 3D ligado à fala: cai do alto girando e encaixa ao lado da cabeça (no original, o
  iPhone na orelha enquanto ele imita a abertura ruim) ou surge atrás da cabeça.
- A 1ª legenda já tem chave na cor de destaque com o TEMA do vídeo.

## Ritmo e som
- Jump cut em toda pausa > 0,22 s, e NADA de respiro nas emendas (respiro sobrando é o erro que
  mais derruba o estilo). Troca de zoom (100% ↔ 108%) a cada corte, e a cada fim de frase quando
  o trecho é longo, pra esconder a emenda.
- Um som por TIPO de efeito, com variações revezando (o mesmo som em tudo fica repetitivo):
  objeto atrás da cabeça = whoosh subindo + baque; tela preta = riser + impacto;
  título = brilho de sinos; zoom punch = estalo + soco grave; chave = pop; 1ª chave = ding.
- Música de fundo baixa, a voz sempre manda.

## Roteiro que o estilo pede (o que gravar)
Proibição → por que dá errado → a regra com número → o que fazer → script/exemplo literal
→ por que funciona → contraste em espelho ("Faz X, acabou. Faz Y, você tem uma chance") →
fecho voltando no número do gancho.
