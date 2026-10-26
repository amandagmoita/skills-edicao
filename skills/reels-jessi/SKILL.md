---
name: reels-jessi
description: >
  Edita um vídeo cru de cabeça falante no estilo "Jessi" (engenharia reversa do Reel da Jessi Jean,
  @jessijeanhome, "get Claude to edit our yaps"): cada benefício falado vira um OBJETO que faz a ação na
  tela no mesmo segundo, quase sempre uma interface conhecida. Pasta do Finder com cursor arrastando
  arquivos, explosão de miniaturas em volta da pessoa, tela de vidro com a imagem, card escuro com texto
  que se escreve e sublinhado na cor de destaque, texto selecionado que troca pra serifa colorida, card de
  documento que embaralha opções e para no item falado, timeline de editor se enchendo, tira de B-roll e
  grade de Reels atrás da cabeça, botão "Saiba mais" com toque. Escrita à mão com seta pro comentário
  sobre a própria pessoa. Legenda de UMA palavra (sans branca, palavra de benefício em serifa itálica na
  cor de destaque do perfil), aparte pequeno e interjeição gigante; título empilhado que se monta na
  fala. Gatilhos: "/reels-jessi", "edita no estilo Jessi", "edita com objetos", "edita com pasta e
  cursor", "edita igual o Reel da Jessi". Título de revista ver /reels-kelsey; tela dividida com logos ver
  /reels-nick; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reels Jessi

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @, cor de
destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal: a cor de destaque
é a da serifa e dos detalhes, o @ vai nos cards estilo Instagram, o produto/link no título do fecho e no
botão do CTA. Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher o
arquivo (modelo em `~/.claude/padroes-edicao/perfil.exemplo.json`).

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack. O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` e
`~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem fazer outro corte.
- Nesta skill: `cortar.py ... base` já corta assim. O `conferir.py` mede na linha 2: som da fala anterior
  por baixo entre 120 e 200 ms, sem estalo. `words_out.json` segue o SOM. `base_info.json` traz o `plano`.

## 0. Antes de começar
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo vai em `<pasta>/jessi/`.
  Nunca escrever dentro da skill nem do video-use.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reels-jessi/scripts
E="<pasta>/jessi"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Se outra skill já transcreveu esse
vídeo, copiar `transcripts/<video>.json` de lá e as `tomadas` do mapa de lá (o corte é refeito aqui, com
sobreposição).
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
```

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
A pergunta por frase: "que objeto FAZ o que a pessoa está dizendo?" De preferência uma interface que o público
reconhece. Nada decorativo: se a frase não tem ação, fica só com a legenda.
- Gancho e fecho → `titulos` empilhados (2-4 linhas), `*serifa colorida*` (cor de destaque) na palavra de benefício. No fecho, o
  produto do perfil. Uma
  linha pode ir `"atras": true` na faixa acima da cabeça (a cabeça passa na frente).
- Juntar/organizar/mandar arquivos → `finder` (cursor arrasta a pilha pra pasta, bolinha com a contagem).
- Volume, bagunça, "uma semana de..." → `explosao` (~16 miniaturas saem da pessoa e se espalham).
- Citar uma coisa (documento, Reel anterior, app) → `cards` (secos, inclinados, um por palavra;
  `"estilo": "ig"` = card de Reel com cabeçalho do Instagram).
- "O cliente explicou na reunião", resultado funcionando → `vidro` (tela de vidro com a imagem).
- Promessa/benefício com nome → `card_escuro` (texto se escreve, sublinhado na cor de destaque, brilhinhos).
- Transformar/combinar/mudar o estilo → `editor` (texto selecionado vira serifa na cor de destaque).
- Vários entregáveis de uma vez → `card_doc` (embaralha e para em cada item falado).
- Processo, fluxo, "dá pra editar tudo" → `timeline` (faixas enchendo, rótulos onde a agulha passa).
- B-roll ou material do criador de fundo → `tira` (atrás da cabeça); prova de volume → `grade` (perfil com views).
- Comentário sobre a própria pessoa ("de novo...", "toda. santa. vez.") → `mao` (letra à mão + seta pra pessoa).
- CTA de link → `botao` (cursor toca "Saiba mais", leva ao link do perfil); CTA de comentário → título empilhado com a palavra.
- Legenda: `amarelas` = palavra de benefício/emoção na cor de destaque (1 a cada 4-6 palavras); `gigantes` = interjeição de
  virada ("Mas", "Ah"), com `degraus` de zoom pra perto; `apartes` = frase de passagem em letra pequena.
- Câmera: `zoom_tomadas` alterna enquadramento a cada tomada; `degraus` secos na palavra forte.

Ritmo da referência: evento visual a cada ~1,5 s, objeto na tela ~51% do tempo, nunca mais de ~3 s sem
nada mudando. O `compor.py` imprime as duas contas e avisa buraco. A aprovação do plano é no STORYBOARD
(passo 3b), com os quadros reais: não mandar tabela em texto antes. Imagem paga (gpt-image) ainda pede o
"ok" do usuário antes de gerar.
```bash
$PY $S/logos.py "$E" app:Claude si:instagram          # logos oficiais pros cards
$PY $S/gerar_imagens.py "$E"                          # ilustração (gpt-image, ~US$0,05) só sem material real
```

## 3. Cortar, medir, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada → medidas.json
$PY $S/mascaras.py "$E"             # recorte da pessoa nos trechos com algo ATRÁS (título atrás, tira, explosão, grade)
$PY $S/compor.py "$E" --so-quadros 1,3.5,5.2,8.2,10.6,13.6,17.2,20.9,24.9,29.6,31.6,36.6,42.9
```
Ler as prévias: nada sobre o rosto, nada cortado na borda, letra legível no tamanho do celular, legenda
sem bater em objeto, nada abaixo de 76% da altura. `mascaras.py` roda de novo sempre que mudar o tempo
de algo atrás da pessoa.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~5-10 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(título empilhado, cada objeto, interjeição gigante, aparte, degrau, aproximação), com código (4B), tempo,
o que entra em português e os avisos de ritmo. Cena sem nada novo mostra o que continua na tela ou "Só você".
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular.
- Esperar o "aprovado" do usuário. Pedido por código ("4B: troca o card", "7: tira a explosão") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu em algo atrás da pessoa, `--storyboard` de novo e reenviar.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py`. A parte desta skill
  é a função `storyboard()` do `compor.py` (nomes dos objetos em `NOMES_SB`).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~5 min → preview_jessi.mp4
$PY $S/conferir.py "$E" "$E/preview_jessi.mp4"         # silêncios, emendas, loudness, folha de contato
```
Tem que dar: maior silêncio ≈ 0,25 s, sobreposição 120-200 ms nas emendas, -14 LUFS, pico < -1 dBTP.
Ler `verify/folha.jpg`. Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `medir.py --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: `[palavra, tomada]` (entra 0,06 s antes), `[palavra, tomada, atraso]` ou segundos. Sem `ate`, vai
até o fim da tomada do `em`. Posições `[x, y]` em fração da tela.
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "destaque": "#FFC700",                        // cor da serifa e dos detalhes (padrão: cor de destaque do perfil)
  "zoom_tomadas": [1.0, 1.08],                  // ciclo por tomada (troca de enquadramento no corte)
  "degraus": [{"em": ["mas", 7], "z": 1.22}],
  "aproxima": [{"em": [...], "z": 1.2, "dur": 0.4}],
  "amarelas": [["tudo", 1], ...], "gigantes": [["mas", 7]], "apartes": [{"em": ["e", 4], "ate": ...}],
  "titulos": [{"em": ["sabe", 0], "y": 0.555, "tam": 88,
               "linhas": [{"txt": "sabe quanto tempo", "y": 0.105, "atras": true}, "um empreendedor *perde*"]}],
  "elementos": [
    {"tipo": "cards", "em": [...], "itens": [{"arquivo": "proposta.png", "em": [...], "pos": [0.15, 0.37],
      "larg": 280, "incl": -4, "rotulo": "Proposta", "estilo": "foto|ig", "handle": "seuperfil"}]},
    {"tipo": "vidro", "em": [...], "arquivo": "reuniao.png", "pos": [0.84, 0.33], "larg": 330, "alt": 470, "incl": 3},
    {"tipo": "mao", "em": [...], "ate": [...], "texto": "tudo de\nnovo...", "pos": [0.03, 0.21], "alvo": [0.26, 0.37], "curva": 1},
    {"tipo": "finder", "em": [...], "arrasta": [...], "arquivos": ["a.png", "b.png", "c.png"], "nome": "Briefing", "pos": [0.5, 0.705]},
    {"tipo": "card_escuro", "em": [...], "lado": "dir", "y": 0.34, "larg": 360, "alt": 540, "letra": 0.15,
      "linhas": [{"txt": "gerar o", "em": [...]}, {"txt": "*briefing*", "em": [...]}], "fundo": "briefing"},
    {"tipo": "editor", "em": [...], "texto": "essas informações", "seleciona": [...], "troca": [...], "pos": [0.5, 0.715], "tam": 96},
    {"tipo": "card_doc", "em": [...], "lado": "esq", "y": 0.34, "larg": 320, "alt": 480, "rotulo": "da reunião",
      "pilula": "gerado com IA", "itens": [{"titulo": "Proposta", "arquivo": "proposta.png", "em": [...]}]},
    {"tipo": "timeline", "em": [...], "titulo": "projeto · cliente", "enche": 1.1,
      "rotulos": [{"texto": "BRIEFING", "em": [...], "cor": "#E8784A"}]},
    {"tipo": "tira", "em": [...], "arquivos": [...], "y": 0.13, "alt": 300, "vel": 70},
    {"tipo": "explosao", "em": [...], "arquivos": [...], "n": 16, "semente": 7},
    {"tipo": "grade", "em": [...], "arquivos": [...], "views": ["12,3 mil", "874 mil"]},
    {"tipo": "botao", "em": [...], "ate": [...], "toque": ["saiba", 12], "texto": "Saiba mais", "pos": [0.5, 0.72]}
  ],
  "layout": {"leg_tam": 96, "leg_queixo": 175, "tit_tam": 88},   // ver LAY no compor.py
  "sfx": {"db": -28},                                         // false = sem efeito
  "musica": {"arquivo": "trilha.mp3", "db": -32}              // referência tem trilha bem baixa; só com licença de uso
}
```

## Regras do estilo (não mudar sem o usuário pedir)
- Objeto literal, não decoração: ele faz a ação da frase, de preferência numa interface conhecida, com
  cursor quando há gesto. Movimento DENTRO do objeto (cursor, seleção, faixa enchendo, embaralhar).
- Legenda de uma palavra, sans branca com letras juntas; palavra de benefício em serifa itálica na cor de
  destaque ~1,4x maior. Aparte em letra pequena; interjeição gigante. Título empilhado substitui a legenda.
- Cards arredondados, sombra macia, inclinação leve (3-6°); entram secos ou deslizando pela lateral e
  saem pelo mesmo lado em ~0,16 s.
- Texto e B-roll atrás da cabeça; interface na frente.
- Som discreto: whoosh nas entradas laterais, clique no cursor, tique ao embaralhar, pop nos cards,
  risco de caneta na letra à mão. Sem trilha por padrão.

- Objeto só entra se FAZ a ação da frase. Logo ou ilustração que só enfeita (logo do app em
  "inteligência artificial", ampulheta em "economizar") sai: a referência fica com objeto na tela ~51% do
  tempo; um mapa com 83% fica poluído. Frase de CTA pode ficar limpa, só com degrau de zoom, como os
  trechos limpos da referência.
- Cor de destaque: padrão = cor do perfil (`"destaque"` no mapa troca; a referência usa amarelo-manteiga
  #F5E57D).
- Fontes só do Mac (baixar fonte só com o ok do usuário): legenda em SF Pro Medium com letras juntas;
  serifa colorida em Didot Itálico estreitado a 82% e engrossado (`serifa_cond`, `serifa_peso`), o mais
  perto da Instrument Serif Italic da referência; letra à mão em Noteworthy Light.

### Gravação em close (a referência é plano aberto)
- Zonas que sobram com cabelo em y≈200-270 e rosto de x≈260 a 760: faixa estreita acima da cabeça (só 1
  linha de título "atrás"), laterais do rosto (cards verticais de até ~330 px) e a faixa da frente do
  corpo entre a legenda e 76% da altura (Finder, editor, timeline, botão).
- Roupa branca come texto branco: toda palavra tem halo escuro macio + sombra curta.
- Objeto pequeno some no celular: card escuro ≥ 360 px com letra a 15% da largura do card; card de
  documento ≥ 320 px; cards ≥ 280 px; letra à mão 78 px com traço de 6 px.

## Armadilhas
- Base nova = `medir.py` e `mascaras.py` de novo (o compor para se o número de tomadas não bater).
- Mudou o tempo de algo atrás da pessoa → `mascaras.py` de novo.
- Explosão usa o rosto da tomada em que começa pra fugir dele; com degrau de zoom no meio, conferir prévia.
- Card lateral mais largo que ~330 px encosta no rosto em gravação close (rosto em x≈260-760).
- `palavra "x" não está na tomada N`: a palavra do mapa tem que bater com a transcrição, pontuação junto
  conta só se a transcrição tiver (o `limpa` ignora pontuação, então "zero," e "zero" valem igual).
- Serifa estreitada perde a margem junto: o espaço entre palavras mistas é calculado com a margem já
  estreitada (senão "essas informações" vira "essasinformações").
- Rótulos da timeline nunca encavalam: cada um começa depois do anterior.
- Card na lateral se posiciona pelo corpo do card (descontando os 44 px de sombra), senão corta na borda.
