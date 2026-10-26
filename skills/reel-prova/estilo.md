# Estilo "prova": valores

Origem: Reel do @justyn.ai "I didn't edit a single second of this video. Claude did." (54 s).
Medição quadro a quadro em `referencia/referencias-estilo.md`.

## Princípio
O vídeo prova o que a pessoa fala. Toda frase tem uma imagem colada nela, que entra NA palavra (0,1–0,3 s de
diferença no máximo): o app citado, a caixa de comando, o documento gerado, a gravação de tela. Só um
trecho fica limpo (sem gráfico), de propósito, na frase do diferencial ou da virada.

## Paleta
Três cores: escuro (fundo do gancho, palco, caixa da legenda), claro (texto e cartões) e destaque (palavra-
chave, botão, ✓). Tirar do cenário do vídeo quando der (a referência usou o verde da parede e o latão das
arandelas). Presets no compor.py: floresta, cafe, grafite, vinho, marinho; ou `{"escuro","claro","destaque"}`.
Vermelho #E23A4C só no risco do app.

## Tipografia (fontes do macOS, conferidas no início do compor)
| Uso | Fonte | Tamanho padrão |
|---|---|---|
| Título-tese, caixa alta | Didot Regular | 230 px |
| Título de impacto | Avenir Next Heavy | 165 px |
| Virada / palavra final | Didot Italic | 150 px (destaque na cor de destaque) |
| Legenda | Bodoni 72 Book | 52 px |
| Interface (caixas, rótulos) | Helvetica Neue Medium/Bold/Regular | 21–46 px |
| Timecode do gancho | Menlo | 30 px |

## Movimento (medido na referência)
- Gancho: fundo chapado em 0,2 s, título troca a cada ~0,5–1 s, alternando as 3 fontes. Corte seco pra sala no fim.
- `letras`: uma letra a cada ~0,06 s, cada uma sobe 46 px e aparece em 0,18 s.
- `mascara`: a linha sobe de trás da linha de base em 0,26 s; linhas com 0,12 s de intervalo.
- `rola`: o título anterior sobe e sai pelo alto enquanto o novo entra por baixo (0,24 s).
- `pop`: entra 28% maior e assenta em 0,2 s.
- Palavra de destaque pode entrar depois, na hora em que é falada (`destaque_em`).
- Ícone de app: cresce de 35% com mola (passa do tamanho e volta) em 0,3 s; risco vermelho desenhado em
  0,16 s; saída "cai": tomba girando e cai com gravidade em ~0,55 s, um ícone 0,07 s depois do outro.
- Caixas: abrem como persiana (de uma linha fina até a altura toda, 0,2 s) e fecham do mesmo jeito.
  Digitação a ~22 caracteres/s (padrão do motor; acelera se a caixa fecha cedo) com cursor piscando; enviado = texto cinza + spinner; pronto = ✓ + resultado
  em itálico.
- Elemento que começa colado no anterior NASCE dele: o cartão muda de tamanho e posição em 0,26 s.
- Descida: quando a prova precisa de espaço, a imagem da pessoa desce (0,3 s) e abre um palco na cor escura.
- Cartões: entram um por um com mola, levemente tortos, flutuando (±7 px, ±1,2°).
- Borrão de movimento nas viradas de bloco (0,12 s antes e depois do corte, até 70 px).

## Legenda
Bodoni 52 px em caixa escura sem borda, 2 a 4 palavras, centro em y 1180 (peito). Palavra já falada em claro,
as próximas em cinza (mistura de claro e escuro) na mesma caixa. Desce junto quando a imagem desce.

## Som
Um efeito por evento, sintetizado: impacto no 1º título, whoosh curto nos outros, pop no ícone, tecla na
digitação, ding no ✓, clique no botão, whoosh no borrão. Música só se o usuário pedir (`"musica"` no mapa, -30 dB).
