---
name: reel-garrafal
description: >
  Edita um vídeo cru de cabeça falante no estilo "letras garrafais" (mapeado do Reel "counting frames",
  34 s): tutorial que mostra o que fala. Abre com 5 B-rolls de 8-3-3-4-5 quadros, uma palavra GARRAFAL
  por corte. O tipo de letra diz o tipo de palavra: legenda pequena sem serifa no peito, palavra concreta
  cresce com brilho, palavra de valor vira serifa itálica, o NOME do assunto aparece em serifa ultra
  condensada atrás da cabeça. Respiros em tela branca ou preta com palavra minúscula, "os outros" em P&B
  com lente curva e moldura que encolhe, B-roll macro P&B, diagrama montando em fundo branco, tela
  dividida (tela em cima, a pessoa embaixo), gravação de tela com zoom e cursor, retrospectiva em cards
  no fim. Luz: brilho branco nas letras, estouro de luz antes do corte, desfoque pra foco ao voltar pro
  rosto. Trilha baixa + riser + whoosh. Gatilhos: "/reel-garrafal", "edita no estilo letras garrafais",
  "edita igual o vídeo do counting frames", "edita com abertura de quadros". Outros estilos: título de
  revista /reels-kelsey, logos em tela dividida /reels-nick, quadro branco /skill-remy, glow /reel-glow.
  Referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel garrafal

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (CTA, nome do
produto em retrospectiva ou conceito). Se o arquivo não existir, pedir ao usuário pra rodar o
`instalar.sh` do pack ou preencher o arquivo. Este estilo é monocromático: a cor de destaque só entra se
o usuário pedir (contorno do item da tela e blocos do diagrama).

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack.
O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz da pessoa acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê, o que já foi
testado e descartado) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem
fazer outro corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill: o `cortar.py ... base` já corta assim (imprime "N emendas sobrepostas, som de A por
  baixo X-Y ms"). O `conferir.py` mede na linha 2: som da fala anterior por baixo entre 120 e 200 ms,
  sem estalo, juntas coladas iguais à fonte. `words_out.json` segue o SOM: a última palavra de uma fala
  aparece quando é ouvida, mesmo com a imagem já na tomada seguinte. `base_info.json` traz o `plano`.

## 0. Antes de começar
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo vai em `<pasta>/garrafal/`.
  Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do vídeo antes de transcrever (nome com "edit" pode ser vídeo pronto).
- Perguntar pelos B-rolls: a abertura precisa de 5 planos curtos do processo do usuário (olho em macro,
  mão no teclado, tela do Claude em macro, mesa, silhueta na janela). Sem eles, a abertura usa recortes em
  macro das gravações de tela dele, ou imagens geradas (`gerar_imagens.py`).
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reel-garrafal/scripts
E="<pasta>/garrafal"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Se outra skill já cortou esse vídeo
(`remy/`, `nick/`, `kelsey/`...), copiar `edl.json base_info.json words_out.json medidas.json` e ligar
`base_*.mov` em vez de refazer.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
$PY $S/cortar.py "$E" edl && $PY $S/cortar.py "$E" base && $PY $S/medir.py "$E"
```
A referência fala a 3,1 palavras/s com pausas de até ~0,5 s antes de cada bloco novo: aqui a pausa curta
é permitida quando cai numa tela de respiro (branca ou preta).

## 2. Montar o roteiro de tela e MOSTRAR antes de renderizar
Classificar cada palavra da transcrição numa destas vozes (é o centro do estilo):

| Voz | Quando | Como (1080×1920) |
|---|---|---|
| `base` | palavra comum | Helvetica Neue Bold ~60 px, branca, sombra curta, uma palavra por vez, y 52-55% (abaixo do queixo da pessoa: medir) |
| `destaque` | verbo de ação, objeto concreto, número | mesma fonte ~150 px, brilho branco |
| `garrafal` | palavra-tema sobre B-roll | mesma fonte ~280 px (66% da largura), brilho; nunca sobre o rosto |
| `italico` | valor/emoção ("mais fácil", "melhor", pergunta) | serifa itálica alto contraste ~105 px, brilho |
| `conceito` | NOME do assunto, não falado ("GANCHO", "PROMPT") | serifa didone ultra condensada ~300 px de altura, topo (13-29%), ATRÁS da cabeça, brilho forte, ~1,4 s |
| `sussurro` | pausa, frase de passagem COMPLETA (nunca pedaço como "Mas e se") | ~20 px, sozinha em tela #F2F2F2 (preta) ou #000 (branca) |

Entrada: nada aparece pronto. Translúcida e desfocada por 2-6 quadros e firma; o `conceito` entra cinza e
ganha brilho em ~6 quadros. Troca exata na palavra falada.

Blocos de tela (um a cada ~1,1 s na referência):
1. `abertura`: 5 B-rolls de 8, 3, 3, 4, 5 quadros + plano longo; uma palavra `garrafal` por corte; riser
   por baixo. O 1º quadro do primeiro B-roll em P&B.
2. `rosto`: talking head; ao voltar pra ele, desfoque → foco em ~8 quadros.
3. `respiro_branco` / `respiro_preto`: tela inteira com `sussurro`; whoosh na entrada.
4. `outros`: P&B, lente curva nas bordas, moldura que encolhe com fundo preto (literalmente "dar zoom out");
   pra quando a fala é sobre o jeito errado ou o que "a maioria faz".
5. `macro`: B-roll em P&B (teclado, tela em macro com retículo) com `garrafal` por cima.
6. `diagrama`: fundo #F2F2F2, palavra preta ~150 px + blocos coloridos com rótulo chegando um a um,
   bipe a cada bloco.
7. `dividida`: 50/50, gravação de tela em cima, a pessoa embaixo, legenda `base` pequena logo ABAIXO da
   emenda (em cima, a interface clara come a parte de cima da letra).
8. `tela`: gravação de tela cheia com zoom no detalhe, cursor grande, contorno branco no item falado,
   caixa translúcida com rótulo `destaque`.
9. `retrospectiva`: fundo #F2F2F2, os clipes da abertura (ou o resultado do tutorial) em card ~44% da
   largura, corte seco entre eles, perto do CTA.

Luz: brilho branco em todo texto grande; estouro de luz (clareia 3-4 quadros) antes dos cortes do gancho;
P&B nos blocos `outros` e `macro`.

A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.
B-roll ou gravação de tela que falta aparece marcado FALTA no fim do storyboard.

## 3. Recortar e prévias
```bash
$PY $S/mascaras.py "$E"        # recorte da pessoa nos trechos com palavra-conceito (~1 min); refazer se o mapa mudar
$PY $S/compor.py "$E" --so-quadros 0.1,0.5,1.4,3,5,7,10,13,16,20,25,30   # JPGs em verify/quadros/
```
Ler as prévias em tamanho real: palavra branca legível em todo fundo (B-roll, interface, blusa branca),
conceito lendo por cima do cabelo e nunca no rosto, nada vazando da largura.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~10 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(cada B-roll da abertura, palavra garrafal/destaque/serifa itálica, palavra-conceito atrás da cabeça,
respiro, "os outros" em P&B, macro, diagrama, tela dividida, gravação de tela com zoom e contorno,
retrospectiva, volta pro rosto com desfoque, câmera mais perto, estouro de luz), com código (4B), tempo,
o que entra em português e os avisos de ritmo. Cena sem nada novo aparece com um quadro só ("só a pessoa + legenda").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~8 MB, imagens embutidas; esta
  skill tem muitos momentos porque cada palavra grande é um).
- Esperar "aprovado". Pedido por código ("4B: troca a palavra", "7: tira o macro") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu num conceito, `--storyboard` de novo e reenviar. Só o storyboard aprovado
  vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos momentos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                 # ~10 min → preview_garrafal.mp4
$PY $S/conferir.py "$E" "$E/preview_garrafal.mp4"     # silêncios, emendas, loudness, folha de contato
```
Tem que dar: emendas < -40 dB, -14 LUFS, pico < -1 dBTP. Ler a folha.
Aprovado → `cortar.py base --final`, `medir.py --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real: `referencia/mapa-exemplo.json`)
Tempos: segundos, `[palavra, tomada]` (entra 0,03 s antes), `[palavra, tomada, atraso]`,
`["inicio", tomada]`, `["fim", tomada]`. Bloco sem `ate` vai até o próximo bloco; buraco entre blocos = rosto.
```jsonc
{
  "blocos": [
    {"tipo": "abertura", "em": 0, "ate": [...], "estouro": true, "luz": 0.62,
     "clipes": [{"arquivo": "a.png", "quadros": 8, "foco": [0.5, 0.45], "z0": 1.06, "z1": 1.14, "pb": false},
                ..., {"arquivo": "longo.png"}]},          // 8,3,3,4,5 + um sem "quadros" (vai até o fim)
    {"tipo": "rosto", "em": [...], "z": 1.12, "foco": true},   // foco = entra desfocada quando vem de outro bloco
    {"tipo": "respiro", "em": [...], "cor": "branco|preto"},
    {"tipo": "macro", "em": [...], "pb": true, "estouro": false, "clipes": [{"arquivo": "x.png", "em": [...]}]},
    {"tipo": "outros", "em": [...], "ate": [...], "escala_final": 0.66, "curva": 0.07},
    {"tipo": "diagrama", "em": [...], "y": 0.53, "titulo_y": 0.40,
     "itens": [{"texto": "briefing", "em": [...], "cor": "#0F258D", "larg": 1.3}]},
    {"tipo": "dividida", "em": [...], "fonte": "gravacao.mov", "t_fonte": 11.0, "caixa": [x, y, w],
     "zooms": [{"em": [...], "caixa": [x, y, w]}]},       // px da gravação (4K); altura sai da proporção
    {"tipo": "tela", "em": [...], "fonte": "gravacao.mov", "t_fonte": 4.6, "caixa": [x, y, w], "texto_y": 0.66,
     "zooms": [...], "contornos": [{"em": [...], "caixa": [x, y, w, h], "cor": "#141414"}]},
    {"tipo": "retrospectiva", "em": [...], "arquivos": ["a.png", ...], "quadros": [8, 8, 8, 30], "larg": 0.44}
  ],
  "palavras": [   // sem entrada = voz padrão do bloco (rosto/dividida/tela/macro: base; abertura: garrafal;
                  // outros: destaque; respiro: sussurro; diagrama: preto grande)
    {"em": ["um", 0], "ate": ["perde", 0], "voz": "italico"},    // "ate" junta palavras numa só tela
    {"em": ["e", 6], "ate": ["anotações", 6], "texto": "anotações", "voz": "garrafal"},
    {"em": [...], "some": true}                                 // não mostra
  ],
  "conceitos": [{"texto": "RETRABALHO", "em": [...], "ate": [...], "topo": 175}],
  "layout": {"base_tam": 62, "destaque_tam": 150, "garrafal_tam": 280, "italico_tam": 128,
             "leg_queixo": 150, "conceito_alt": 270, "conceito_vidro": 0.62},   // ver LAY no compor.py
  "sfx": {"db": -26},                                  // false = sem efeito
  "musica": {"arquivo": "trilha.mp3", "db": -28}       // só com arquivo e licença do usuário
}
```

## Regras do estilo (não mudar sem o usuário pedir)
- O tipo de letra diz o tipo de palavra (tabela da seção 2). Nunca duas vozes grandes ao mesmo tempo.
- O vídeo prova o que ensina: o gancho já usa a técnica, e o fim mostra o resultado em retrospectiva.
- B-roll é do processo do usuário, filmado ou gravado da tela. Nada de banco de imagem.
- Monocromático: branco com brilho, P&B, preto e #F2F2F2. Cor só na gravação de tela e no diagrama.
- Tela de respiro (branca ou preta) só leva pensamento COMPLETO que caiba em ~0,5-1,5 s ("O cliente já
  explicou tudo"). Pedaço de frase ("Mas e se") sozinho na tela não faz sentido. Se a frase é longa, não
  cortar no meio pra caber na pausa: tira o respiro e a virada entra direto no rosto com desfoque → foco.
- Fontes: as do Mac mais perto da referência (Helvetica Neue Bold, Bodoni 72). Playfair Display Bold
  Italic (Google Fonts) só baixando com o ok do usuário.
- Corte seco entre blocos; os únicos "efeitos" de transição são desfoque → foco, estouro de luz e a
  moldura que encolhe.

## Armadilhas
- Parede clara (bege, branca) come o brilho branco: o `conceito` atrás da cabeça pede halo escuro.
- Não escurecer a gravação pra imitar o quarto escuro da referência (pele fica suja). O contraste
  vem do P&B e das telas pretas.
- A condensada do "HOOK" não existe no Mac. Bodoni 72 Bold apertada a ~42% com espaço negativo entre
  letras é o mais perto.
- Brilho branco desfocado dentro de uma margem curta vira CAIXA cinza em volta da palavra: a margem tem
  que ser maior que o raio (`pinta` amplia ~0,75 do corpo antes de desfocar).
- B-roll claro (papel, caderno) come a letra branca. A referência é escura: todo B-roll entra escurecido
  (`luz` 0,62 + contraste 1,12; por clipe ou bloco).
- Gravação de tela do Claude é BRANCA (a da referência era um editor escuro). Palavra em bloco `tela`
  ganha caixa escura translúcida (como o "2 clips" da referência); contorno do item sai escuro
  (#141414), porque branco some.
- Título do diagrama com duas palavras passa da largura: o motor encolhe até 92%.
- Gravação de tela em 4K costuma ter barra preta em cima e embaixo (y < 150 e > 2040): caixa começa em
  y 150.
- Os primeiros ~0,5 s de uma gravação de tela podem mostrar "Loading page": escolher `t_fonte` olhando a
  folha de quadros.
- `mascaras.py` importa ESTE `compor.py` (mesma conta das janelas): mudou o mapa, roda de novo.
- Trilha: a referência tem trilha baixa (8-12 dB abaixo da voz), mas só entra com arquivo e licença do
  usuário (`"musica": {"arquivo": ..., "db": -28}`).
