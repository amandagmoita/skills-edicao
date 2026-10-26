---
name: reel-autoridade
description: >
  Edita um vídeo CRU de cabeça falante no estilo "autoridade" (engenharia reversa do Reel do
  Jordan Belfort sobre cold call): legenda de 2-4 palavras na altura do peito com palavra-chave
  na cor de destaque e caixa alta, número-tese gigante ATRÁS da cabeça, telas pretas com objeto
  3D como metáfora, objeto 3D surgindo atrás da cabeça, títulos em Didot itálico, sticker
  tracejado, jump cuts com troca de zoom, zoom punch nas emendas e SFX. Estilo FIXO: não precisa
  de vídeo de referência. Entrega REEL_PRONTO.mp4 + pacote CapCut. Gatilhos: "/reel-autoridade",
  "edita no estilo autoridade", "edita no estilo do Belfort", "edita esse vídeo cru", "edição
  estilo lobo de wall street". Para editar copiando OUTRA referência qualquer, usar /reel-editor.
  Idioma: PT-BR.
---

# Reel Autoridade

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal. A cor de
destaque do perfil vira o `cor` do `mapa.json` (o `rascunho_mapa.py` já preenche; `--cor` troca) e o
CTA usa o produto/link do perfil. Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh`
do pack ou preencher o arquivo.

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack (vale pra todas as skills de Reels).
O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê de cada
número) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem
fazer outro corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill: o `cortar.py` já corta assim (imprime "corte com sobreposição: N emendas, som da fala
  anterior por baixo X-Y ms"; o normal fica entre ~155 e 170 ms). `corte.json` (segmentos
  in/out/ini/fim) segue a IMAGEM; `palavras_corte.json` segue o SOM (a última palavra de uma fala
  aparece quando é ouvida). O rabo do último trecho continua com o respiro do CTA (voz + 0,48 s).
  O módulo mantém enquadramento no rosto, zoom e cor iguais aos do resto do corte.

## 0. Onde fica cada coisa
- `estilo.md` — o padrão visual detalhado. LER antes de montar o mapa.
- `scripts/` — o pipeline (todos aceitam `-h` no cabeçalho do arquivo):
  `transcrever.py` → `cortar.py` (chama `rosto_segmentos.py`) → [`transcrever_corte.py`] → `rascunho_mapa.py` → (Claude edita o mapa) →
  `gerar_objetos.py` → `render_camadas.py --previa` → `render_camadas.py --storyboard` (usuário aprova) →
  `render_camadas.py` → `compor.py`
- `scripts/visao.swift` — rosto e recorte da pessoa pelo Apple Vision; compila sozinho na
  1ª vez em `scripts/bin/visao`.
- Transcrição: whisper.cpp do HyperFrames (`~/.cache/hyperframes/whisper/...`, modelo large-v3).
- Objetos 3D: `OPENAI_API_KEY` em `~/.claude/env`.
- Projeto de cada vídeo: pasta do projeto `~/Reels/AAAA-MM-DD-slug/`.

Rodar os scripts com `python3` (sem `-I`: o Pillow está no site-packages do usuário) e com
o caminho absoluto `~/.claude/skills/reel-autoridade/scripts/...`.

## 1. Entrada
- Vídeo cru (obrigatório). Vertical da cintura pra cima é o ideal; horizontal funciona (vira 9:16
  muito fechado, rosto ocupando ~65% da largura, e o número gigante fica quase todo atrás da cabeça).
- Antes de cortar, conferir se o vídeo é o certo (folha de quadros + início da transcrição): pode
  ser uma série de ganchos soltos ou outro arquivo. Na dúvida, perguntar.
- Música (opcional): arquivo de áudio, entra baixinha com ducking automático.
- Se o usuário não disser o tema/CTA, tirar da própria fala. CTA de produto = produto/link do perfil.

## 2. Transcrever e cortar
```bash
S=~/.claude/skills/reel-autoridade/scripts
P="<pasta do projeto>"
python3 $S/transcrever.py "<video cru>" "$P"
```
Ler `palavras.json` NUMERADO e decidir o que sai (repetição, frase errada que foi refeita,
"ééé", começo antes de a pessoa falar). Regra: quando uma frase se repete, fica a ÚLTIMA versão.
```bash
python3 -c "import json;p=json.load(open('$P/palavras.json'));print(' '.join(f'{i}:{x[\"w\"]}' for i,x in enumerate(p)))"
python3 $S/cortar.py "<video cru>" "$P" --remover "12-19,40-44"
```
Conferir o total impresso. Reel desse estilo fica entre 35 e 70 s; se passar muito, propor
ao usuário o que cortar de conteúdo (não decidir sozinho o que é corte de mensagem).

### 2b. Gravação frase por frase (comum em quem lê roteiro)
Várias tomadas da mesma frase em sequência são o jeito de gravar, não erro. Regra: fica a ÚLTIMA
tomada completa; fragmento ("O cliente manda uma...") sai. Se duas tomadas têm partes melhores em
lugares diferentes, PERGUNTAR (dá pra juntar o começo de uma com o fim da outra).

Nesse modo o whisper no cru NÃO serve pra cortar: funde tomadas, empilha palavras de fragmento no
mesmo instante e alucina repetição (a mesma frase x11) e frases fantasma ("Legenda por Sônia
Ruberti", "Tchau") em trecho curto ou ruído. Fluxo certo:
1. Achar as regiões de fala pela energia: `python3 -c "import sys;sys.path.insert(0,'$S');from cortar import pausas;..."`
   (lista as faixas entre pausas de 0,3 s).
2. Transcrever CADA região isolada com o whisper-cli (`-nt -np`, 0,15 s de folga): é isso que
   mostra quais são as tomadas. Região de 0,1–0,5 s quase sempre é estalo/respiro → fora.
3. Montar a lista de faixas que FICAM e cortar com `--manter-tempo "1.66-8.14,9.32-13.2,..."`
   (na ordem em que devem aparecer; pode voltar no tempo pra juntar pedaços de tomadas).
4. `python3 $S/transcrever_corte.py "$P"` refaz `palavras_corte.json` UMA TOMADA POR VEZ
   (o corte inteiro de uma vez desliza até 18 s; pedaço de 8 s engolia a última palavra;
   pedaço < 1,5 s alucina) e prende cada palavra no início real da voz, inclusive na emenda.
5. O whisper troca palavra ("a"→"Há", "caso"→"casa") e às vezes perde uma. Não brigar com
   isso: o mapa usa o TEXTO DO ROTEIRO e tira do whisper só os tempos, alinhando as duas
   sequências com `difflib` (um script curto no projeto, `montar_mapa.py`, que ancora legenda,
   títulos, telas pretas, stickers e transições no texto falado; recortou? roda de novo e tudo
   acompanha).
6. Conferir a duração do `base_corte.mp4` com o total impresso pelo `cortar.py`.

## 3. Rascunho do mapa
```bash
python3 $S/rascunho_mapa.py "$P"            # cor = cor de destaque do perfil; --cor "#RRGGBB" troca
```
Gera `mapa.json` com as legendas já em blocos de 2-4 palavras e imprime a timeline.

## 4. Montar o mapa de edição (trabalho do Claude)
Editar `mapa.json` seguindo `estilo.md`. O campo `rosa` (legenda) e `cor: "rosa"` (título) são nomes
antigos: querem dizer "na cor de destaque" (`cor` do mapa). Densidade-alvo por minuto de vídeo
(mais alta que a do Reel do Belfort):

| Elemento | Quantos | Onde |
|---|---|---|
| `objeto_gancho` | 0–1 | 0–3 s, ligado à 1ª frase (alternativa: o gancho vira um `objetos_atras`) |
| `legendas[].chave` | 1 a cada 2–4 blocos | o substantivo que carrega a ideia |
| `legendas[].rosa` | 2–4 blocos | frase-tese e as últimas frases, inteiras na cor de destaque |
| `numeros` | 0–2 | só número que resume a tese, falado em voz alta |
| `telas_pretas` | 2–3 | conceitos abstratos que ganham metáfora visual |
| `stickers` | 0–2 | substantivo concreto citado de passagem |
| `objetos_atras` | MÁXIMO 4 por vídeo | `{ini, fim, imagem, tamanho (0,5–0,66), dx, giro, alto}`: objeto 3D que sobe de trás da cabeça; o mais usado do estilo |
| `titulos` | 8–10 (~1 a cada 6–7 s) | `{ini, fim, sub, texto, cor}`: palavra que a pessoa FALA, em Didot itálico atrás da cabeça; `cor` "rosa" (= destaque) ou "branco"; nunca junto com sticker, gancho ou tela preta |
| `transicoes` | 8–10 (~1 a cada 6 s) | lista de tempos (s) de emendas que abrem frase nova → zoom punch no `compor.py` |

Regras:
- Chave: tirar a(s) última(s) palavra(s) do `texto` e pôr em `chave` (vira caixa alta, na cor de
  destaque). Se a palavra-chave está no meio, reorganizar o bloco (ajustar `ini`/`fim` pelas palavras).
- Nunca dois efeitos grandes sobrepostos (número, tela preta, gancho). Sticker pode coexistir
  com legenda.
- Título no ar = sem legenda (o motor esconde); não repetir a mesma palavra em destaque duas vezes.
- Tela preta: `ini`/`fim` alinhados com o começo de uma palavra e o fim de uma frase; o texto
  que aparece é o que a pessoa FALA naquele trecho, então escolher trecho de 4–12 palavras.
  `destaques` = 1–3 palavras do trecho.
- Número: `texto` curto ("4x", "60s", "10k", "3"), janela de 1,2–2,5 s começando na palavra.
  Roteiro sem número falado = sem número gigante (não inventar).
- Objeto do gancho: `lado` "direita" | "esquerda" | "acima"; `tamanho` 0,3–0,45 da largura;
  `giro` -20 a 20. No vertical 4K com rosto centralizado sobra pouca parede dos lados e o objeto
  lateral bate na borda: usar `lado: "acima"`, `tamanho` ~0,34. Sticker idem, acima do cabelo.
- Objetos atrás da cabeça: 1 por ideia concreta da fala, alternando com os títulos, sem nunca
  sobrepor. Mais de 4 por vídeo fica excessivo: o gancho + as 3 ideias mais concretas.
- `objetos_ia`: um item por imagem usada (`nome` = arquivo em `assets/`), `descricao` em
  inglês, objeto único, concreto, fotografável. Evitar marca, texto e pessoa. Objeto num tom da
  cor de destaque amarra o visual; mudou a cor, refazer esses objetos (dourado combina sempre).
- Transição do estilo é só o zoom punch (flash branco e chave tremendo não combinam com ele).

Depois, MOSTRAR AO USUÁRIO o plano em linguagem simples, antes de gastar com imagem:
a timeline com os efeitos (tempo, frase, o que aparece) e a lista de objetos a gerar.
Só seguir com o "ok" do usuário.

## 5. Objetos 3D
```bash
python3 $S/gerar_objetos.py "$P"
```
gpt-image-1.5 com fundo transparente, ~15 s e ~US$0,04 cada, em paralelo. Pula o que já existe
(pra refazer um, apague o PNG). Olhar cada PNG antes de seguir.

## 6. Prévia, render e composição
```bash
python3 $S/render_camadas.py "$P" --previa 0.5,<t do número>,<t da tela preta>,<t do sticker>,<t final>
```
Ler as prévias (`$P/previa/*.jpg`) e comparar com o `estilo.md`. Checar: legenda
no peito e legível, número aparecendo atrás da cabeça, objeto do gancho sem cobrir o rosto,
sticker inteiro no quadro, texto da tela preta alinhado. Ajustar o mapa e repetir.

### 6b. STORYBOARD pro usuário aprovar (obrigatório, antes do render)
```bash
python3 $S/render_camadas.py "$P" --storyboard     # ~2-5 s → "$P/storyboard.html" + storyboard.json
```
Uma página com uma cena por segmento do corte (a fala entre aspas) e o QUADRO REAL de cada momento
(objeto do gancho, número, título Didot, objeto atrás, sticker, tela preta e o zoom punch das emendas,
simulado no quadro porque no vídeo ele é do `compor.py`), com código (3B), tempo, o que entra e avisos
(efeitos grandes sobrepostos, mais de 4 objetos atrás, trecho longo sem efeito).
- Mandar com `SendUserFile` (`display: render`). Esperar "aprovado". Pedido por código → mudar o
  `mapa.json`, `--storyboard` de novo e reenviar. Só o storyboard aprovado vai pro render abaixo.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py`. A parte desta
  skill é a função `storyboard()` do `render_camadas.py`.

Render (só com o storyboard aprovado):
```bash
python3 $S/render_camadas.py "$P"          # camadas.mov + legendas.srt (~20 s por 30 s de vídeo)
python3 $S/compor.py "$P" [--musica faixa.mp3]
```

## 7. Conferência antes de entregar
- MEDIR o corte (não só ler a transcrição): silêncio no começo+fim de cada segmento pelo
  limiar de voz (`energia()` do `cortar.py`), alvo ≤ 0,15 s por emenda (o normal é ~0,10 s); e erro
  entre a 1ª palavra de cada tomada no `palavras_corte.json` e o início da voz, alvo ≤ 0,05 s.
- Folha de contato do final:
  `ffmpeg -i "$P/REEL_PRONTO.mp4" -vf "fps=1.5,scale=180:-1,tile=12x4" -frames:v 1 "$P/final_folha.jpg"` e LER.
  A folha (com `fps=…,tile`) pode mostrar quadros "desfocados" que não existem no vídeo; só os 3–4
  quadros do zoom punch são desfocados de verdade. Pra checar desfoque, medir nitidez por quadro.
- Loudness perto de -14 LUFS: `ffmpeg -i "$P/REEL_PRONTO.mp4" -af ebur128=framelog=quiet -f null - 2>&1 | grep I:`
- Sem fone: conferir os efeitos sonoros pelo espectrograma (varredura visível = whoosh; chiado
  uniforme = filtro errado).
- Assistir mentalmente a sequência: algum trecho de mais de 3 s sem nada mudando na tela?
  Se sim, pôr uma chave ou sticker ali.

## 8. Entrega
```
<projeto>/
├─ REEL_PRONTO.mp4
├─ mapa.json                 ← o plano de edição (refaz qualquer ajuste em minutos)
└─ pacote-capcut/
   ├─ base_corte.mp4         ← cortado, 9:16, cor e áudio tratados
   ├─ camadas_chromakey.mp4  ← todos os gráficos em fundo VERDE (Chroma key no CapCut)
   ├─ camadas_alpha.mov      ← mesmos gráficos com transparência (CapCut desktop) — arquivo grande
   ├─ legendas.srt
   ├─ sfx_trilha.wav + sfx/
   └─ montagem.md
```
Mandar o `REEL_PRONTO.mp4` ao usuário com SendUserFile e dizer em 2 linhas o que entrou.
Ajuste pedido depois ("tira essa tela preta", "muda a chave") = editar `mapa.json` e rodar
de novo só `render_camadas.py` + `compor.py`.

## Armadilhas
- O whisper "estica" cada palavra até a próxima: pausa NÃO sai do tempo das palavras, sai da energia
  do áudio (limiar adaptativo em `pausas()` do `cortar.py`): piso de ruído + 8 dB, entre -50 e -28 dB,
  e nunca a mais de 18 dB abaixo da voz (p90). Com folga maior, ruído de sala a -50 dB e respiração
  (~-35 dB) contavam como fala e sobravam segundos de respiro no corte. Gap de pausa: 0,22 s.
- Fala corrida sem pausa ainda precisa trocar zoom: o `cortar.py` divide no fim de frase.
- `aparar()` encosta cada segmento na voz (p90−16 dB, 0,05 s antes / 0,18 s depois) e descarta
  segmento sem voz. Só voz CONTÍNUA (≥ 40 ms) conta, senão estalo de respiração estica o fim da
  tomada; folga de 0,12 s cortava o "-so" de "caso" (decai de -26 a -35 dB); segmento com < 0,15 s
  de voz sai. Último segmento ganha folga extra (o CTA não termina seco).
- Legenda: a caixa do Vision vai da sobrancelha ao queixo; com 1,25h a legenda caía no queixo. Padrão:
  y + 1,75h (peito), entre 55% e 72% da altura. Rosto medido por SEGMENTO (`rosto_segmentos.py`, roda
  sozinho no fim do `cortar.py`), porque gravando frase por frase a pessoa muda de posição.
- O microfone aparece como "não pessoa" na máscara do Vision: o número passa por cima dele.
  Aceitável; se incomodar, posicionar o número mais alto.
- Chroma key do pacote CapCut é VERDE (magenta apagaria um destaque rosa). Cor de destaque verde no
  perfil quebraria a chave: avisar o usuário.
- Título Didot: centrado no topo da cabeça, a cabeça comia o meio da palavra. O motor deixa só o
  terço de baixo passar atrás do cabelo e, se a cabeça esconde mais de 15%, joga o título pra frente.

## 9. Fechamento
Registrar no topo deste arquivo (Aprendizados acumulados) o que mudou no uso: preferência
do usuário, efeito que foi cortado, problema de script. Se for regra de estilo, atualizar
também `estilo.md`.
