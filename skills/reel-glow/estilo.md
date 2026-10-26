# Estilo "glow" — valores exatos

Origem: padrões medidos num Reel de referência (54 s, cabeça falante com legenda amarela, objeto
3D atrás da cabeça, número gigante, telas pretas com objeto, clipes de B-roll, sticker tracejado,
efeito em cada evento) + 3 voltas de ajuste (glow, zoom animado, fala contínua, gráficos animados).

## Quadro
- 1080×1920, fps da fonte, cor: UMA análise pro vídeo todo (`eq` leve do video-use, ex.
  `contrast=1.03:saturation=1.04`), nunca por trecho (a cor oscilaria no corte).
- Zoom alternado fixo: tomadas ímpares com recorte de 87% (≈115%) no 4K antes de escalar,
  deslocado pra cima (x 6,5%, y 3,5%) pra manter o rosto.
- Zoom animado (~6 tomadas de fala): escala na curva cúbica ao longo da tomada inteira, âncora
  no rosto (540, 900). Aproxima 1,00→1,12 (1,15 no CTA) ou afasta 1,13→1,00.

## Legenda (peito)
- Poppins Bold 60 px, branca, sombra preta borrada (raio 7, 75%, 3 px abaixo), sem contorno.
- Centro da 1ª linha em y = 1215. 2–3 palavras por bloco, inteiras (sem karaokê); quebra em
  pontuação ou pausa ≥ 0,3 s. Pontuação final removida (vírgula, ponto), "?" fica.
- Bloco fica até o próximo começar (se a distância < 0,6 s) ou até 0,25 s depois da última palavra.
- Chave: 2ª linha, CAIXA ALTA, Poppins Bold 104 px (encolhe até caber em 980 px), amarelo glow,
  entra com pop 82%→100% em 0,14 s na hora da palavra. Pop sonoro baixinho (-21 dB).
- Letra a letra (1 por vídeo): letras surgem fora de ordem em 0,4 s.
- Fecho: última frase inteira em amarelo glow, 80 px.
- Sem legenda nas telas pretas (a fala vira o texto da tela).
- Sobre B-roll claro: faixa preta suave atrás da legenda (perfil exp⁴ centrado em y 1265,
  meia-altura ~230 px, 70%).

## Amarelo glow (cor de destaque)
- Núcleo #FFEC5C (255, 236, 92). Halo #FFC400 em duas camadas: desfoque 22 px a 55% e 8 px a 85%
  (alfa × 1,6), por baixo do núcleo. Vale pra chave, fecho, palavras-amarelas das telas, traços
  das cenas (contornos, linhas, setas, barras de destaque) e a moldura do sticker.
- Vem do perfil (`cor_destaque` em `~/.claude/padroes-edicao/perfil.json`). No padrão (#FFC700) são
  os valores acima; outra cor vira o halo e o núcleo é a mesma cor clareada 45%.

## Gancho (0–3 s)
- Objeto 3D (gpt-image, fundo transparente) com 560 px de altura cai de y -380 até o centro em
  (650, 400) entre 0,25 s e 0,95 s, girando de -40° pra -18°, flutua e some encolhendo até 2,95 s.
- Fica ATRÁS da pessoa (máscara do Apple Vision): o cabelo passa por cima.
- Som: whoosh subindo + impacto no pouso.

## Número gigante
- Poppins Bold 760 px × 0,95, branco listrado na horizontal (10 px cheio / 4 px a 27%) com brilho
  leve, centro em y 470, atrás da pessoa. Entra 0,12 s antes da palavra encolhendo 114%→100% com
  fade de 0,25 s, cresce 4% devagar, sai em fade no fim da tomada.

## Telas pretas
- Fundo: luz radial (centro 46, borda 8) + granulado animado (6 texturas revezando).
- Texto: Poppins Bold 66 px, linhas de até 900 px, começando em y 300, palavras aparecem no tempo
  da fala (layout da frase inteira fixo). Palavras listadas em `amarelo` em glow.
- Troca de cena (quando `empurrao`): 0,32 s, painel sai pra esquerda e o novo entra da direita,
  com desfoque horizontal proporcional à velocidade.
- Cenas (ver SKILL.md seção 6): mini-Reel = cartão escuro arredondado com play e 2 linhas de
  legenda; etiquetas = pílula escura com texto amarelo 40 px; nós do fluxo = círculos r 140 com o
  objeto 3D dentro (175 px), apagados a 55% até acender; curva = exp(3,2x) em 0,9 s com seta.
- Som: impacto + whoosh na entrada; whoosh na troca; pop em cada etiqueta/nó; whoosh_sobe em
  barra que dispara e na curva.

## B-roll
- Tela cheia 9:16 (recorte da gravação ou clipe vertical escalado), aproximação contínua
  1,00→1,06. Legenda continua por cima. Whoosh na entrada de cada bloco (não entre clipes colados).

## Presença (padrão do estilo)
- Em todo B-roll e tela preta a pessoa fica na tela, recortada pelo Apple Vision, no canto de baixo à
  direita; o corpo sai pela borda de baixo. Sombra preta borrada (18 px, 45%, 10 px abaixo); bordas
  laterais do recorte somem em 70 px; entra subindo 420 px em 0,3 s no começo do bloco.
- B-roll: escala 0,6, ponto `ancora_rosto` da base em (790, 1310); legenda em y 1540 com a faixa
  escura centrada em 1590 quando o fundo é claro.
- Tela preta: escala 0,5, rosto em (800, 1650); a cena (não o texto) encolhe pra 75% em direção a
  (540, 560) pra liberar o canto.

## Sticker
- Moldura 270 px tracejada (traço 18, vão 12, 6 px) em amarelo glow, fundo escuro 43%, objeto
  230 px dentro, centro (540, 300) acima da cabeça. Pop com passada na entrada, some encolhendo.
  ~1,8 s a partir da palavra.

## Som
- Sem música (padrão do estilo). Efeitos sintetizados (numpy), variações revezando por tipo:
  whoosh (passa-banda que varre 300→2600 Hz, 0,45 s), whoosh_sobe (200→3200 Hz, 0,5 s), impacto
  (seno 48 Hz com queda + clique), pop (seno 1100→520 Hz, 90 ms).
- Níveis antes da normalização: -14 a -21 dB por evento (voz bruta ~ -17 dB RMS).
- Normalização em 2 passadas: -14 LUFS, pico real ≤ -1 dBTP, LRA 11.

## Ritmo
- Fala contínua: borda 40 ms antes / 60 ms depois da voz; pausa ≥ 0,22 s dentro da frase vira
  corte; sem respiro de fim de bloco. Maior silêncio resultante ≈ 0,25 s.
