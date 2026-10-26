---
name: reel-glow
description: >
  Edita um vídeo cru de cabeça falante no estilo "glow": fala contínua (pausa máx. ~0,25 s),
  legenda Poppins branca inteira no peito com palavra-chave em AMARELO GLOW (ou na cor de destaque
  do perfil) na 2ª linha, objeto 3D caindo atrás da cabeça no gancho, número gigante listrado atrás
  da cabeça, telas pretas com GRÁFICOS ANIMADOS que reagem à fala (raio-X de Reels, barras que
  disparam, fluxo de etapas com curva de crescimento), B-roll das gravações de tela do usuário com a
  legenda por cima, zoom animado nos takes, sticker tracejado e um efeito sonoro por evento (sem
  música). Usa o video-use pra transcrever. Gatilhos: "/reel-glow", "edita no estilo glow",
  "edita esse vídeo com gráficos e b-roll", "edita com telas pretas animadas". Para estilo
  autoridade (Didot, Belfort) ver /reel-autoridade; para copiar uma referência NOVA, analisar a
  referência do zero (não usar esta skill como estilo). Idioma: PT-BR.
---

# Reel Glow

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do
Instagram, cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado
pessoal (CTA, cor, @). Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack
ou preencher o arquivo. O `compor.py` já lê a cor de destaque sozinho: no padrão (#FFC700) sai o
amarelo glow medido do estilo; outra cor vira o halo, com o núcleo clareado.

**Regras do estilo que valem sempre:**
- Referência nova que o usuário mandar é analisada do zero; esta skill não substitui essa análise.
- Sem música, só efeitos sonoros (padrão do estilo).
- B-roll de preferência com as gravações de tela do próprio usuário: é mais prova que clipe gerado.
- No B-roll e nas telas pretas a pessoa CONTINUA na tela, recortada no canto de baixo à direita
  (`presenca`, ligada por padrão; `"presenca": false` desliga).
- Mexeu no motor (`compor.py`/`cortar.py`)? Toda opção nova tem que ser aditiva: um mapa que não usa
  a opção sai igual. Conferir com `--so-quadros` nos mesmos segundos antes e depois da mudança.

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack. O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê de cada
número) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem fazer outro
corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill: o `cortar.py ... base` já corta assim (imprime "N emendas sobrepostas, som de A por
  baixo X-Y ms"). O `conferir.py` mede na linha 2: som da fala anterior por baixo entre 120 e 200 ms,
  sem estalo, juntas coladas iguais à fonte. `words_out.json` segue o SOM: a última palavra de uma fala
  aparece quando é ouvida, mesmo com a imagem já na tomada seguinte. `base_info.json` traz o `plano`.

## 0. O que precisa estar instalado
- **video-use** em `~/Developer/video-use` (transcrição Scribe + helpers). Rodar TUDO com
  `PY=~/Developer/video-use/.venv/bin/python` (em muitos Macs não existe `python`, e o `python3`
  do sistema é 3.9 sem numpy). Chave ElevenLabs em `~/Developer/video-use/.env`.
- ffmpeg/ffprobe no PATH (6.0 serve), `swiftc` (Xcode CLT) pro recorte da pessoa.
- `OPENAI_API_KEY` em `~/.claude/env` (objetos 3D).
- Scripts: `S=~/.claude/skills/reel-glow/scripts`. Todos têm o uso no cabeçalho.

## 1. Pasta do projeto
Vídeo cru + B-roll (gravações de tela, clipes) na MESMA pasta (ex.: `~/Reels/meu-video/`); tudo que
for gerado vai em `<pasta>/edit/`. Nunca escrever dentro da skill nem do video-use.
- B-roll que mora em outra pasta: trazer com hard link (`ln`, mesmo disco), que não ocupa espaço.
  Symlink NÃO serve: o `transcribe.py` resolve o link e grava a transcrição na pasta do original.
- Antes de transcrever, olhar uma folha de quadros do arquivo: nome com "edit" pode ser vídeo já
  editado (ver "Fonte que já veio editada" nas Armadilhas). Havendo cru e editado na pasta, perguntar
  ao usuário qual usar.

## 2. Transcrever (custa crédito: só quando o usuário mandou o vídeo pra editar)
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
$PY $S/cortar.py "<pasta>/edit" frases        # frases com tempo de cada palavra
```
Ler as frases e escolher as **tomadas**, na ordem em que vão aparecer:
- Quem grava frase por frase costuma repetir: fica a tomada COMPLETA (normalmente a última).
  Fragmento ("Quer o pro--") sai. Suspiro/respiração antes da 1ª fala sai.
- Gaguejo grudado numa palavra só ("anali-analise" vira 1 token no Scribe): achar o ponto exato
  pela energia (RMS de 20 ms) e começar a tomada depois do pedaço errado.
- O Scribe às vezes rotula ruído como evento ("[som de notificação]"): medir o nível antes de manter.
  Num caso real era -60 dB, ou seja, 1,4 s mudo no fim.
- Cada tomada = `[início da 1ª palavra, fim da última palavra, "BLOCO"]`. O índice da tomada
  (0, 1, 2…) é como o resto do mapa se refere a ela.
- Vídeo de UMA tomada só, lido de ponta a ponta sem repetir: tomada = oração (vírgula/ponto), só pra
  ancorar efeitos; quase não há corte. Tomadas que se tocam na fonte viram trechos `colado`.

## 3. Montar o mapa.json (trabalho do Claude)
Modelo completo e comentado: seção 7. Densidade do estilo (vídeo de ~80 s):

| Elemento | Quantos | Regra |
|---|---|---|
| `chaves` | ~1 a cada 7 s (12 em 82 s) | substantivo/ideia que carrega a frase; vira 2ª linha amarela glow |
| `letra_a_letra` | 1 | a palavra-CTA ("VIRAL") surge letra por letra |
| `fecho` | 1 | última frase inteira em amarelo glow ("Testa e me conta") |
| `gancho` | 1 | objeto 3D cai atrás da cabeça nos 0–3 s, ligado ao tema |
| `numero` | 0–1 | só se a pessoa FALAR um número que resume a ideia ("10 ideias") |
| `telas` | 2 | trechos de explicação abstrata → cena animada (seção 6) |
| `brolls` | 5–7 trechos | o que o usuário mandou, no momento em que a pessoa fala daquilo |
| `zooms` | ~6 takes | aproxima 1,00→1,12–1,15 ou afasta 1,13→1,00; nunca na tomada do gancho/número |
| `sticker` | 1 | objeto concreto do CTA ("direct" → avião de papel) |
| `presenca` | sempre (padrão) | a pessoa recortada no canto durante B-roll e telas; ajustar `rosto`/`escala` só se a cena ou o B-roll pedir |

Proporção de referência do estilo: pessoa falando ~50%, B-roll ~30%, telas pretas ~18%.
- Fala que é uma lista de entregáveis aguenta chaves mais densas (13 em 45 s).
- Sem número gigante quando o único número falado é a 1ª palavra e já bate com o gancho.
- CTA de comentário: `letra_a_letra` na palavra-CTA, sticker do objeto do CTA, `fecho` na última frase.
- CTA de link: letra a letra em "LINK", sticker = elo de corrente, fecho = "conheça o <produto do perfil>".
- CTA curto ("saiba mais e conheça o <produto>"): o `fecho` engole o "SAIBA MAIS" em 0,6 s. Usar duas
  chaves (SAIBA MAIS com pop; nome do produto letra a letra) e nenhum `fecho`.
- O nome do produto e o @ que aparecem no CTA vêm do perfil (`produto`, `instagram`), nunca inventados.

A aprovação do plano é no STORYBOARD (passo 4b), com os quadros reais. Não mandar tabela em texto antes.
Antes de gastar com objetos 3D, só a lista de objetos a gerar (custa) pede o "ok" do usuário.

## 4. Gerar, cortar, recortar, prévias
```bash
E="<pasta>/edit"
$PY $S/gerar_assets.py "$E"                 # objetos 3D (~US$0,04 cada); OLHAR cada PNG
$PY $S/cortar.py "$E" edl                    # bordas na voz, pausas internas viram corte
$PY $S/cortar.py "$E" base                   # ~8 min: trechos com N quadros exatos → base_preview.mov
$PY $S/mascaras.py "$E"                      # recorte da pessoa onde algo passa atrás da cabeça
$PY $S/compor.py "$E" --so-quadros 1.2,9.6,12.3,15.5,47,70,74   # prévias em verify/quadros/
```
Ler as prévias: legenda legível (inclusive sobre B-roll claro), objeto atrás do cabelo (não na
frente), cenas no tempo da palavra, recortes de B-roll sem menu/tela errada. Ajustar o mapa e
repetir só `compor.py --so-quadros` (segundos). Mudou tomada? refazer `edl` → `base` → `mascaras`.
- Julgar posição sempre no quadro em tamanho real: prévia lado a lado reduzida engana (a legenda
  parece cair no rosto quando no quadro inteiro está no queixo).
- Com a presença ligada, o `mascaras.py` recorta todos os quadros de B-roll e tela preta (~1 min
  pra 45 s de vídeo).

## 4b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~4 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por tomada (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(objeto do gancho, número, sticker, cada cena de tela preta e o empurrão entre elas, B-roll, gráfico acima
da cabeça, cada efeito da /reel-efeitos, zoom animado, blur, palavra-chave amarela), com código (4B), tempo,
o que entra em português e os avisos (buraco > 5 s parado, máscara ou arquivo faltando, item que entra
< 0,5 s antes de a cena sair). Cena sem nada novo aparece com um quadro só ("só a pessoa + legenda").
Arquivo que falta vira quadro com faixa vermelha "FALTA ARQUIVO", sem derrubar a página.
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~2-3 MB, imagens embutidas).
- Esperar o "aprovado" do usuário. Pedido por código ("4B: troca a cena", "7: tira o zoom") → mudar o
  `mapa.json`, `mascaras.py` de novo se mexeu em algo atrás da pessoa, `--storyboard` de novo e reenviar.
  Só o storyboard aprovado vai pro passo 4c.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos elementos,
  `NOMES_SB`; quadro pela mesma `quadro_previa()` do `--so-quadros`, então os dois mostram o mesmo quadro).

## 4c. Renderizar (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                        # ~1 min → preview_glow.mp4
$PY $S/conferir.py "$E" "$E/preview_glow.mp4"
```

## 5. Conferir antes de mostrar (não dá pra ouvir: medir)
`conferir.py` imprime e tem que dar:
1. maior silêncio na base ≈ 0,25 s;
2. nenhuma emenda com som no ponto de corte (RMS ±5 ms < -40 dB);
3. duração = soma dos trechos (±1 quadro), 1080×1920, **-14 LUFS**, pico real < -1 dB;
4. `verify/folha.jpg` (1 quadro/s): LER inteira. Procurar trecho de > 5 s sem nada mudando,
   legenda sumindo, B-roll errado, objeto cortado.
Mandar com SendUserFile. Arquivo > 30 MB não chega no celular: avisar e oferecer cópia comprimida
(720p a ~1,7 Mbps deixa um vídeo de 1:44 em ~24 MB).
Versão final depois do ok: `cortar.py base --final` → `mascaras.py --final` → `compor.py --final`
→ `final_glow.mp4`.

## 6. Telas pretas: as cenas
Fundo quase preto com luz no centro e granulado; a fala do trecho surge palavra por palavra no
alto (layout fixo; palavras de `amarelo` em glow); sem legenda no peito. Uma cena por tomada, ou
UMA cena pra tela inteira (lista com 1 item) quando a tela atravessa várias tomadas. `empurrao: true`
= troca de cena por empurrão lateral com desfoque.

| `tipo` | Ilustra | Parâmetros |
|---|---|---|
| `raiox` | "analisar / procurar em X, Y e Z" | `palavras` (1 coluna de mini-Reels cada), `rotulos`, `objeto` (lupa), `icones` (opcional: lista de objetos 3D, 1 cartão grande por coluna no lugar dos mini-Reels, bom pra "procurar em conversas, arquivos e anotações"). A lupa varre; cada coluna acende com a etiqueta na palavra |
| `ramos` | "faz uma vez e vira várias coisas" | `origem`, `centro`, `saidas` (lista), cada um `{objeto, rotulo, palavra\|null, tomada}`. Origem no alto liga no centro; o centro abre em curvas pras saídas embaixo. Linha corre 0,35 s antes da palavra, nó acende nela |
| `barras` | "o que está chamando atenção / crescendo" | `dispara` (palavra em que a barra de destaque sobe em glow + seta), `entra_objeto` (palavra em que o objeto aparece no topo), `objeto` |
| `fluxo` | passo a passo / recapitulação | `nos`: `{objeto, rotulo, palavra\|null, tomada}`; cada nó acende na palavra (ou no início da tomada), linha corre entre eles; `curva` `{palavra, tomada}` desenha crescimento exponencial com mini-Reels |
| `objeto` | metáfora simples | `objeto` sobe de baixo e flutua (a tela preta básica) |
| `memorial` | "a IA esquece / erra / inventa dados" | `titulo`, `linhas` (rótulos), `preenche` [palavra, tomada], `pedido` {palavra, tomada, texto} (balão digitando, opcional), `falta` {palavra, tomada, linhas}, `inventa` [{palavra, tomada, linha}]. Cartão entra 0,5 s antes de `preenche` (cartão vazio por 4 s fica morto) e o `pedido` ocupa o começo |

**Efeitos da /reel-efeitos:** `"efeitos": [{"nome", "tomada", "palavra"?, "dur"?, ...}]` no mapa
liga qualquer um dos 17 efeitos da biblioteca (órbita, mundo do app, checklist, capa de revista...)
na tomada de fala, com a legenda glow por cima. Regra: biblioteca, não catálogo; ~1 efeito a cada
10 s, cada um nascido da frase. Detalhes e parâmetros: `~/.claude/skills/reel-efeitos/SKILL.md`.
Cada efeito aparece no storyboard (passo 4b) como "Efeito: <nome>", com o quadro dele já montado.
Sem a chave, a saída é idêntica à de sem efeitos.

**Fora da tela preta (gráfico acima da cabeça):** `graficos: [{"tipo": "topo", "tomada", "y": 300, "raio": 88,
"nos": [{objeto, rotulo, palavra}]}]` desenha uma fileira de 3 nós (círculo escuro + objeto 3D + rótulo) no
espaço livre ACIMA da cabeça no take de fala, atrás do cabelo (recorte na frente; o `mascaras.py` já inclui
a tomada). A linha amarela corre 0,35 s antes de cada palavra e o nó acende nela; some nos últimos 0,3 s.
Medir antes onde fica o topo da cabeça no take e deixar o rótulo acabar acima disso. Combina com zoom
animado na mesma tomada (entra antes do zoom, como o gancho). Bom pra frase-lista falada olhando pra
câmera ("acessa os e-mails, identifica prioridade e organiza"), quando não vale tirar a pessoa da tela.

Cena nova: escrever `cena_<nome>(t, c, g)` em `compor.py` (desenha em camada RGBA 1080×1920;
traços/textos amarelos numa camada separada passada por `glow()`; tempos via `t_pal(palavra,
tomada)` e `OFF[tomada]`), registrar em `CENAS` e pôr o som dela em `trilha_sfx` (pop na palavra,
whoosh em linha que corre, whoosh_sobe em algo que sobe). Depois atualizar esta tabela.

## 7. mapa.json (modelo completo: `referencia/mapa-exemplo.json`)
```jsonc
{
  "fonte": "meu-video.mov",                        // relativo à pasta do projeto
  "tomadas": [[8.22, 11.02, "GANCHO"], ...],       // índice = tomada
  "corte": {"limiar_voz": -33},                    // opcional; sem ele o limiar é p90-22 dB da fonte
  "gancho": {"objeto": "celular"},                 // opcional: ini/pousa/fim/x/y/alt
  "numero": {"texto": "10", "palavra": "10", "tomada": 5},
  "sticker": {"objeto": "aviao", "palavra": "direct", "tomada": 28},   // opcional: x (540), y (300)
  "chaves": [["viral", 0, 1, 2], ...],             // [1ª palavra da chave, tomada, nº palavras da chave, nº palavras antes]
  "letra_a_letra": ["viral", 28],
  "fecho": ["Testa", 28],
  "telas": [{"tomadas": [3, 4], "empurrao": true, "amarelo": [["analise"], ["nicho","de","moda"]],
             "cenas": [{"tipo": "raiox", ...}, {"tipo": "barras", ...}]}],
  "brolls": [{"tomadas": [6, 7], "arquivo": "rec.mov", "inicio": 3.0, "recorte": [x, y, w, h]}],  // recorte null = clipe vertical
  "zooms": {"1": [1.0, 1.12], "9": [1.13, 1.0]},
  "ancora_rosto": [540, 900],
  "objetos": {"celular": "a modern smartphone ... (inglês)"},
  // opcionais p/ fonte já editada: "legenda": false, "blur": [[t0,t1,x,y,w,h]], "legenda_y": [[t0,t1,y]],
  // "corte": {"cor": false}, telas[].ate (seg. da saída), "presenca": {"tela": {"janelas": [[t0,t1]]}}
}
```
Palavras do mapa: sem pontuação, sem diferença de maiúscula, e têm que existir NAQUELA tomada
(o script para e mostra a fala da tomada se não achar).

**Recorte de gravação de tela 4K (3840×2160):** a coluna 9:16 mais larga que cabe é 1215×2160;
pra mostrar um detalhe, 900×1600. Achar o ponto com quadros em grade (`drawgrid`) e conferir os
segundos escolhidos: menu de botão direito aberto, tela de OBS e busca no Google costumam aparecer
no meio das gravações. Caixa de prompt (faixa horizontal fina) não funciona em 9:16: não usar.
Gravação de tela vertical com faixas pretas em cima e embaixo: medir a área útil e recortar só ela
(ex.: tela útil de y≈150 a 2040 → recorte 1063×1890 em y 150).

## Armadilhas (cada uma já custou uma rodada)
- `helpers/render.py` do video-use com ffprobe 6.0: `is_portrait_source` falha calado e o vertical
  sai 1920×3414. Por isso `cortar.py` tem extração própria com escala fixa.
- AAC por trecho + concat `-c copy` = 0,2–0,6 s de deriva entre voz, vídeo e legenda. Áudio é PCM
  por trecho, cortado por filtro (`apad,atrim=end_sample`); NUNCA `-frames:v` (corta o áudio junto).
- Legenda calculada pela duração do EDL desliza (vídeo arredonda pra quadro). Tudo usa a duração
  REAL de cada trecho (`base_info.json`).
- Fonte que não carrega cai em outra sem erro ("Avenir Next" + Bold virou BoldItalic). Aqui a
  Poppins vem da pasta da skill por caminho absoluto.
- Legenda branca/amarela some sobre B-roll claro (tela do Claude): o compositor põe uma faixa escura
  suave atrás quando a área da legenda tem luminância média > 120.
- Máscara do recorte é por número de quadro da base: base nova = rodar `mascaras.py` de novo.
- Zoom animado não pode cair na tomada do gancho ou do número (a máscara é do quadro sem zoom).
- Pico real acima de -1 dBTP depois do loudnorm (voz com estalo chegou a -0,7 dBTP): `segura_pico()`
  no fim do `compor.py` passa um limitador só quando passa de -1 (deu -14,1 LUFS / -1,3 dBTP); o
  `conferir.py` mostra o valor final, que tem que estar < -1.
- Fala contínua dividida em tomadas que se tocam (vão de 40 ms entre palavras): as folgas 40/60 ms
  se cruzavam (repetia até 40 ms de voz) e o fade de 30 ms de cada trecho abria um buraco no meio da
  frase. O `edl` marca `colado` e encontra os dois no meio do vão; o `base` começa o trecho colado
  exatamente no quadro onde o anterior acabou e não põe fade na junta. Não muda nada em vídeo com
  pausas entre as tomadas. Sem isso o `conferir` acusa emendas com voz no corte.
- Respiração antes da frase fica em -35/-40 dB: o limiar de voz (-33 numa gravação típica) deixa ela
  de fora. O "s" final que decai até -32 dB fica dentro (tolerância de 40 ms de queda).
- Legenda emenda tomadas ("e organizados e"): o bloco não quebra na troca de tomada. Contorno sem
  mexer no motor: pôr uma chave no começo da tomada seguinte.

**Posição do gancho e da presença**
- Gancho com objeto LARGO (~1,9:1, ex. maquete): `alt` 560 dá 1.000 px de largura e some atrás da
  cabeça. Usar `alt` 400 e subir pra `y` 250 (pousa no topo do cabelo).
- Rosto mais alto que o normal (olhos em y ~640): `ancora_rosto` [540, 680]; gancho em x 730 / y 300 /
  alt 420 passa atrás do topo do cabelo (em x 810 fica solto ao lado, sem tocar a cabeça).
- Fonte com título gravado no alto (caixa até y 520): objeto do gancho ao LADO da cabeça (x 880, y 760,
  alt 380), atrás do cabelo, em vez de em cima. Sticker com `x` deslocado se o centro estiver ocupado.
- Presença no B-roll: escala 0,6, rosto em (790, 1310), legenda desce pra y 1540 (peito do recorte).
  Na tela preta: escala 0,5, rosto em (800, 1650), e a cena encolhe pra 75% em direção ao texto do alto.
  Entra subindo de baixo em 0,3 s; a sombra suave existe porque fundo branco de documento engolia
  roupa branca; bordas laterais do recorte somem em 70 px.

**Fonte que já veio editada** (pessoa pequena no canto sobre cenas, legenda gravada, CapCut...)
- Sem corte nenhum: `"corte": {"pad_in": 0.5, "pad_out": 0.5, "split_gap": 99, "zoom_alternado": false,
  "cor": false}` deixa todas as tomadas `colado` e a saída = fonte quadro a quadro.
- `"corte": {"cor": false}` não regrada a cor; `"legenda_y": [[t0, t1, y]]` (segundos da saída) muda a
  altura da legenda nesse trecho, com faixa escura se o fundo for claro; `sticker.y` (padrão 300) e
  `sticker.x` (padrão 540) movem o sticker.
- Nas cenas compostas o rosto fica em ~y 1300: legenda em 1540 (a mesma do B-roll com presença) cai
  no peito e fica legível.
- Legenda palavra a palavra já gravada na imagem: perguntar ao usuário; manter a dele com
  `"legenda": false` (glow por cima duplicaria; os pops de chave somem junto).
- `"blur": [[t0, t1, x, y, w, h]]` (segundos da saída, px de 1080×1920) pixeliza + desfoca a caixa
  (chave de API, dado sensível) antes de qualquer camada. Achar o intervalo com quadros a 10 fps do
  trecho e conferir NO VÍDEO FINAL (folha das bordas). Deixar ~0,1 s de margem antes: blob sobre o
  quadro anterior é melhor que vazar.
- `telas[].ate` (segundos da saída): a tela preta dura além do fim da última tomada (texto parado).
  Resolve "a fonte troca de imagem no meio de uma frase" sem picotar a tomada.
- `presenca.tela.janelas: [[t0, t1]]`: a pessoa só aparece onde está de fato na fonte; a entrada sobe
  do início da janela. Sem isso o recorte pega o quadro de transição (light leak) e vira um FANTASMA
  amarelo; em trecho de notebook filmado não há pessoa.
- Pessoa já pequena no canto da fonte: `presenca.tela` com `escala` 1.0 e `rosto` = `ancora_rosto`
  deixa ela exatamente onde já estava.
- Achar as trocas de imagem da fonte medindo brilho por quadro (topo/base) em vez de chutar pela folha.
- Conferir pode acusar 2 quadros a menos que a "soma dos trechos" quando o último trecho pede mais do
  que a fonte tem (pad no fim). Não é erro: saída e fonte têm os mesmos quadros.

Estilo com todos os valores: `estilo.md`. Mapa de exemplo: `referencia/mapa-exemplo.json`.
