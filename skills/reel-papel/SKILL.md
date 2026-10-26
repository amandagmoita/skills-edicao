---
name: reel-papel
description: >
  Edita um vídeo cru de cabeça falante no estilo "papel" (versão 2 do Reel do @justyn.ai "I didn't edit
  a single second of this video. Claude did."): cada frase vira, no mesmo segundo, um objeto do mundo da
  edição desenhado como papel na paleta do cenário do vídeo. Tíquete de impressora numerado saindo de
  uma fenda acima da cabeça (o fio da história: um por comando, lição ou passo), título gigante em serifa
  alta ATRÁS da cabeça, calendário de quadros do próprio vídeo com mergulho numa casa, régua que corre (e
  esquenta a imagem), teclas caindo, tira de filme marcada à caneta, cartela "alguns minutos depois", o
  vídeo encolhendo pra dentro de um celular, letreiro com o vídeo dentro das letras, feed rolando
  borrado, caneta circulando o rosto em P&B, mural de cards deste vídeo, thread de comentário com ✓,
  widget de iPhone apagando itens, capa de revista, capítulos com a pessoa recortada, CTA de comentário e
  seguir. Legenda karaokê serifada em caixa reta que obedece aos comandos (escada, gigante). Transição só
  quando ilustra a palavra (íris, persiana, borrão). Um efeito sonoro por evento. Usa o video-use pra
  transcrever. Gatilhos: "/reel-papel", "edita no estilo papel", "edita no estilo da v2 do Justyn",
  "edita com tíquete", "edita com os objetos de edição", "estilo revista e tíquete". Para a v1 do Justyn
  (caixas de chat, ícones riscados) ver /reel-prova; telão ver /reel-telao; glow ver /reel-glow;
  referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel Papel

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (nome na
`nota`, @ no `comenta`, produto e link no CTA). Se o arquivo não existir, pedir ao usuário pra rodar o
`instalar.sh` do pack ou preencher o arquivo. O motor já usa o `nome` e o `instagram` do perfil quando o
mapa não traz `nome`/`resposta_nome`/`conta`. As cores deste estilo vêm da `paleta` do cenário, não da
cor de destaque.

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
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo que for gerado vai em `<pasta>/papel/`.
  Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do arquivo antes de transcrever: nome com "edit" pode ser vídeo pronto.
  Conferir se sobra parede acima da cabeça (tíquete, régua, cards e títulos moram ali).
- Se o vídeo já foi cortado por outra skill com as MESMAS tomadas (ex.: `telao/`), dá pra copiar
  `edl.json`, `base_info.json`, `words_out.json`, `medidas.json`, `transcripts/` e ligar as bases com
  `ln -s` em vez de cortar de novo. Tomada diferente = cortar de novo.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reel-papel/scripts
E="<pasta>/papel"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Reaproveitar se já existir.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
```
Tomadas como no /reel-glow (fica a tomada completa; fragmento e respiração saem). Vídeo de uma tomada só:
uma tomada por ideia/item. Cada tomada troca de enquadramento (zoom alternado), como os 9 cenários da
referência.

## 2. Montar o mapa (o plano vai pra aprovação no storyboard, passo 3b)
O trabalho do Claude aqui é casar cada frase com UM objeto que a ilustra literalmente. Perguntas por frase:

| A frase… | Elemento | Como na referência |
|---|---|---|
| é um comando, um pedido, um passo ou um item numerado | `tiquete` | "INSTRUCTION 01 · TOTAL 1 SENTENCE" (em vídeo de lista vira o fio: "LIÇÃO 01 … DE 10", um por item, com o resumo do item digitado) |
| é a tese curta ("nunca", "dez coisas", "escutar") | `titulo` atrás da cabeça | I DIDN'T EDIT, NEVER |
| tem uma virada com palavra-chave ("a última é a *mais importante*") | `titulo` fonte serifa + `destaque` | "Claude *did.*" |
| fala de quantidade/tempo do próprio vídeo ("um segundo", "dez coisas") | `grade` | calendário de quadros |
| diz que algo some, sai, não precisa ("nem X, nem Y, nada") | `widget` com `sai_em` + `final` | apps apagados → "nothing." |
| fala de mudar cor/clima/temperatura ou de ir de A a B | `regua` (com `efeito`) ou `cor` | Kelvin esquentando, "moody" |
| fala de muitas coisas chegando, perguntas, ferramentas | `chuva` | atalhos de editor caindo |
| fala de bruto, processo, erro, o que cortar | `filme` com `marcas` | "dead air", "cut" |
| passa tempo ("minutos depois", "no longo prazo") | `cartela` | A FEW MINUTES LATER |
| "o que você está vendo", "no celular", "na tela" | `celular` (mergulha no fim) | "what you're seeing now" |
| uma palavra-choque curta | `letreiro` (vídeo dentro das letras) | HUGE |
| "todo mundo", "o feed", "os outros" | `feed` rolando borrado | concorrentes |
| "eu", "você", "meu jeito", "vistos" | `caneta` (P&B opcional) | círculo + "me" |
| estrutura, roteiro, partes do vídeo | `mural` com quadros deste vídeo | storyboard pregado |
| conversa, pedido de ajuste, pergunta de seguidor | `nota` (texto → resposta → ✓) | "beat 23" |
| cita conteúdos/Reels/resultados do criador | `cards` (vídeos do criador flutuando) | "my best videos float in" |
| resultado final, sucesso, "parece de revista" | `revista` | capa EDITED |
| "gravei um material", "passo a passo" | `capitulos` (a pessoa recortada) | 01 raw take … 04 finished |
| CTA de comentário / seguir | `comenta`, `seguir`, `faixa` | caixa digitando EDIT, Following |
| "a legenda cresce", "maior", ênfase de 3-4 palavras | `legenda_modos` escada / grande | captions come in / Bigger |

Densidade da referência (54 s): algo novo a cada ~1,5 s, nenhum trecho limpo acima de ~1 s, tíquete 3-4
vezes (ou um por item em vídeo de lista), 3 a 5 transições temáticas. O `compor.py` imprime a linha do
tempo e avisa trecho limpo acima de 1,6 s e elemento que fica menos de 0,5 s.

A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais (a lista de arquivos usados, Reels
finalizados do usuário pros cards e o feed, sai na mesma página). Não mandar tabela em texto antes.

## 3. Cortar, medir, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K HEVC (rodar em segundo plano)
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada (Vision) → medidas.json
$PY $S/mascaras.py "$E"             # recorte da pessoa nos títulos atrás da cabeça e nos capítulos
$PY $S/compor.py "$E" --so-quadros 0.05,0.9,2.0,3.9,4.25,5.9,7.5,11.6,14.2,19,22.4,24.5,28.2,35.3,38.6,44.9,55.5,63
```
Montar as prévias numa folha e LER: título passando atrás do cabelo, tíquete sem cobrir a testa, legenda
fora do rosto, nada embaixo de 78% da altura, cores certas (P&B, quente) nos lugares certos.
Base nova → `medir.py` e `mascaras.py` de novo. Mudou tempo de título → `mascaras.py` de novo.
`--so-quadros` APAGA as prévias antigas de `verify/quadros/` antes de gravar as novas: guardar antes o
que precisar comparar. Tempos de referência: prévia de 49 quadros ~20 s; máscaras de 3 títulos ~25 s.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~10 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(tíquete, título atrás da cabeça, grade, régua, cor, chuva, filme, celular, letreiro, feed, caneta,
mural, nota, cards, widget, revista, CTA, abertura, legenda em escada/gigante, íris/persiana/borrão), com
código (4B), tempo, o que entra em português e os avisos (elemento com menos de 0,5 s, tíquete que não
termina de digitar, falta de máscara, trecho limpo acima de 1,6 s, arquivo faltando). Cena sem nada novo
aparece com um quadro só.
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~4 MB, imagens embutidas).
- Esperar "aprovado". Pedido por código ("4B: troca o objeto", "7: tira a caneta") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu em título atrás da pessoa ou capítulos, `--storyboard` de novo e reenviar.
  Só o storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos elementos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~1-2 min (65 s de vídeo ≈ 80 s, fora a base) → preview_papel.mp4
$PY $S/conferir.py "$E" "$E/preview_papel.mp4"         # silêncios, emendas, loudness, folha de contato
ffmpeg -v error -y -i "$E/preview_papel.mp4" -vf scale=720:-2 -c:v libx264 -crf 24 -c:a aac -b:a 128k "$E/preview_papel_celular.mp4"
```
`conferir.py` tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP.
Conferir no VÍDEO (não só nas prévias) as transições, quadro a quadro: mergulho da grade, íris, persiana.
Aprovado → `cortar.py base --final`, `medir.py --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: `[palavra, tomada]` (objeto entra 0,1 s antes, nunca antes do corte), `[palavra, tomada, atraso]`
ou segundos da saída. `ate` omitido = fim da tomada do `em`. Palavra sem pontuação, a 1ª ocorrência
NAQUELA tomada vale (cuidado com palavra repetida).
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.14, "GANCHO"], ...],
  "paleta": "oliva",            // oliva (padrão: parede oliva, sofá creme) | floresta (a da referência) | {"escuro","caixa","claro","destaque","caneta"}
  "abertura": true,              // câmera começa colada e abre em 0,24 s
  "elementos": [
    {"tipo": "titulo", "linhas": ["DEZ COISAS"], "em": ["dez", 0], "antecipa": 0.3},      // anim mascara | letras
    {"tipo": "titulo", "fonte": "serifa", "linhas": ["a última é a", "mais importante."],
     "destaque": ["mais", "importante."], "destaque_em": ["mais", 0], "em": ["última", 0]},
    {"tipo": "grade", "celulas": 10, "colunas": 5, "em": [...], "ate": [...]},            // quadros: "tomadas" | [s, ...]
    {"tipo": "tiquete", "rotulo": "LIÇÃO", "para": "DE 10", "texto": "...", "total": "1 frase", "em": [...], "ate": [...]},
    {"tipo": "regua", "valores": ["5600K", "3200K"], "efeito": "quente", "em": [...]},    // efeito: quente|frio|escuro
    {"tipo": "cor", "modo": "pb", "em": [...]},                                           // pb|escuro|quente|frio
    {"tipo": "paleta", "em": [...]},                                                      // conta-gotas + hex (pontos opcionais)
    {"tipo": "cards", "itens": [{"arquivo": "../outro-video/final.mp4", "inicio": 2, "rotulo": "atrair", "em": [...]}], "em": [...]},
    {"tipo": "chuva", "teclas": ["⌘K", ["J", "voltar"], "por quê?"], "em": [...]},
    {"tipo": "filme", "marcas": [{"tipo": "circulo", "quadro": 2, "texto": "processo", "em": [...]},
                                 {"tipo": "x", "quadros": [5, 7], "texto": "corta", "em": [...]}], "em": [...]},
    {"tipo": "cartela", "linhas": ["ALGUNS", "MINUTOS", "DEPOIS"], "em": [...]},
    {"tipo": "celular", "entra": true, "em": [...]},
    {"tipo": "letreiro", "texto": "MEIO", "em": [...], "ate": [...]},                      // ou "linhas": ["HU","GE"]
    {"tipo": "feed", "itens": [{"arquivo": "...", "inicio": 3}], "em": [...], "ate": [...]},
    {"tipo": "caneta", "palavra": "você", "pb": true, "em": [...]},
    {"tipo": "mural", "quadros": [10.0, 14.2, 18.5], "nota": "texto à mão", "em": [...], "ate": [...]},
    {"tipo": "nota", "nome": "...", "avatar": "m", "texto": "...", "resposta_nome": "Seu Nome",
     "resposta_avatar": "rosto", "resposta": "...", "em": [...]},
    {"tipo": "widget", "titulo": "MODO EDIÇÃO", "unidade": "apps", "itens": [
       {"icone": "whatsapp", "nome": "WhatsApp", "sai_em": [...]}, {"rosto": true, "nome": "Você", "sai_em": [...]},
       {"glifo": "R$", "nome": "Seu produto", "sai_em": [...]}], "final": {"texto": "nada.", "em": [...]}, "em": [...]},
    {"tipo": "revista", "cabecalho": ["Nº 10", "A EDIÇÃO …", "OUT 2026"], "titulo": "SUCESSO",
     "linha": "dar mais do que", "italico": "receber.", "em": [...]},
    {"tipo": "capitulos", "fundo": {"arquivo": "../gravacao.mov", "inicio": 5}, "itens": [{"rotulo": "O bruto", "em": [...]}], "em": [...]},
    {"tipo": "comenta", "palavra": "EDIT", "resposta": "Te mandei no direct!", "em": [...]},
    {"tipo": "seguir", "toque_em": [...], "etiquetas": [{"texto": "dicas de IA", "em": [...]}], "em": [...]},
    {"tipo": "faixa", "titulo": "Comenta", "palavra": "EDIT", "sub": "e eu te mando o passo a passo", "em": [...]}
  ],
  "transicoes": [{"tipo": "iris", "tomada": 1}, {"tipo": "persiana", "tomada": 6}, {"tipo": "borrao", "tomada": 4}],
  "legenda_modos": [{"modo": "escada", "em": [...]}, {"modo": "grande", "em": [...], "ate": [...]}],
  "legenda_cfg": {"tamanho": 56, "max_palavras": 4, "y": 1363},   // opcional; "legenda": false desliga
  "musica": {"arquivo": "trilha.mp3", "db": -30}                   // opcional; a referência tem música baixa
}
```
Opções comuns: `antecipa` (s), `y` (posição do tíquete/régua/cards), `tamanho` (títulos). Ícones de app:
`$PY $S/icone_app.py "<nome do app>" <arquivo>` → `assets/icones/` (já tem whatsapp, meet, drive, notas,
claude, chatgpt).

## Regras do estilo (não mudar sem o usuário pedir)
- Paleta sai do cenário do vídeo (parede, sofá, dourado de brinco/espelho, vermelho de unha ou de um
  objeto). Nada de cor fora da paleta, exceto o feed dos outros. Cenário diferente das paletas prontas →
  `"paleta": {"escuro", "caixa", "claro", "destaque", "caneta"}` amostrado do próprio vídeo.
- Interface nunca é print de software cru: tudo redesenhado como papel/objeto na paleta. A única tela
  real é o feed, e ela passa borrada.
- Tíquete: papel creme serrilhado saindo de uma fenda escura com ponto dourado, texto em máquina de
  escrever, número e hora; volta sugado pra fenda.
- Títulos gigantes: serifa alta e estreita, creme, ATRÁS da cabeça, entrando por máscara de baixo pra
  cima (ou letra por letra). Itálico dourado só na palavra da virada.
- Legenda: serifa, creme, caixa reta escura sem borda, peito (71% da altura), 2-4 palavras, karaokê
  (próximas palavras apagadas dentro da mesma caixa). Solta e pequena nas telas chapadas. Em escada:
  máx. 4 palavras, 46 → 112 px, base em `LEG_Y + 110` (com 5 palavras e tamanho crescendo sem freio ela
  cobre o rosto).
- Transição temática só quando ilustra a palavra; no resto, corte seco.
- Objetos de papel têm sombra leve e ficam um pouco tortos; painéis (régua, widget) ficam retos.
- Saídas rápidas (0,1-0,2 s). Nada fica na tela depois que a frase acaba.
- Um efeito sonoro por evento (impressora, tecla, pop, ding, caneta, obturador, queda, whoosh). Música
  só com arquivo e licença do usuário.

## Armadilhas
- As do /reel-glow sobre corte e áudio continuam valendo (`cortar.py` e `conferir.py` são os mesmos).
- `medidas.json` com número de tomadas diferente do corte = o compor para. Base nova = medir de novo.
- Máscara é por número de quadro: base nova ou título mudado de lugar = `mascaras.py` de novo.
- Prévia `--so-quadros` lê UM quadro de cada vídeo de card/feed; no vídeo final os cards rodam.
- Mural compõe os quadros do próprio vídeo na hora (com tíquetes, títulos): mudar o mapa muda o mural.
- O conta-gotas lê a cor no quadro em que pega; em prévia avulsa a cor pode diferir do vídeo.
- Objeto que entra 0,1 s antes da palavra NÃO pode antecipar por cima do corte: aparece no último quadro
  da tomada anterior e suja a íris. O motor prende o início no começo da tomada.
- Borrão do feed forte demais vira mancha: limite de 40 px.
- Rótulo à caneta de quadro da fileira de baixo do filme vai embaixo da folha (em cima, cola no da
  fileira de cima).
- `ate` que aponta pra 1ª ocorrência de uma palavra que vem ANTES do `em` dá elemento com duração
  negativa. Conferir a linha do tempo impressa: o compor avisa "fica só X s na tela".
- Tíquete de frase curta volta pra fenda antes de terminar de digitar; a linha do tempo impressa não
  pega, o storyboard avisa no momento.
- Fontes: a referência parece usar Instrument Serif, JetBrains Mono e Inter. Sem elas instaladas, o motor
  usa Didot estreitada (títulos), Bodoni 72 (legenda e itálico), Menlo Bold (tíquete), Avenir Next
  (interface) e Bradley Hand (caneta). Trocar pelas originais (Google Fonts, grátis) é escolha do usuário.
