---
name: skill-remy
description: >
  Edita um vídeo cru de cabeça falante no estilo "Remy" (quadro branco que pensa junto), medido do Reel
  "Skill of the Week: Content Principles": a metade de cima vira um quadro branco de software que
  desenha o argumento na palavra exata (lista que ganha um item por fala, risco vermelho à mão, saídas
  iguais descendo do card, leque de cards com foco por desfoque, mapa mental, caixa de chat recebendo
  arquivos, gravação de tela), a pessoa embaixo. Fora do quadro: pasta com os resultados cobrindo o
  rosto, print com marca-texto no número, pilha de prints, título na parede com fita escrita à mão,
  colagem de recortes de papel em primeiro plano. A cabeça da pessoa passa NA FRENTE do quadro (recorte
  pelo Apple Vision). Imagens geradas por IA desenham a frase (foto no quadro, recorte na colagem). Tudo
  nasce do desfoque ou em cascata; troca de cena no quadro é por desfoque. Legenda Poppins Bold branca
  em blocos de 2-3 palavras, CTA com a palavra grande na cor de destaque do perfil (padrão #FFC700).
  Sem música, efeito curto nas entradas. Gatilhos: "/skill-remy", "edita no estilo Remy", "edita com
  quadro branco", "edita no estilo skill of the week", "edita com cards e mapa mental". Para outros
  estilos ver /reel-glow, /reel-telao, /reel-prova, /reel-papel; referência NOVA = analisar do zero.
  Idioma: PT-BR.
---

# Skill Remy

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (CTA, título
de produto, cor). Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou
preencher o arquivo. O motor já lê a cor de destaque de lá (`"destaque"` no mapa sobrescreve).

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
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo que for gerado vai em
  `<pasta>/remy/`. Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do arquivo antes de transcrever: nome com "edit" pode ser vídeo pronto.
- Se o vídeo já foi editado por outra skill, reaproveitar a transcrição (`<pasta>/<skill>/transcripts/`).
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/skill-remy/scripts
E="<pasta>/remy"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Reaproveitar se já existir.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
```
Tomadas como no /reel-glow (fica a tomada completa; fragmento e respiração saem). Cada tomada troca de
enquadramento (zoom alternado do `cortar.py`): é a variação de escala da referência, que não usa zoom
animado.

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
O trabalho do Claude aqui é transformar o argumento em diagrama. Perguntas por trecho:
- A fala lista coisas ("briefing, proposta, programa")? → `quadro` `lista`, um item por palavra.
- A fala diz que algo se repete / sai igual? → `lista` com `saidas` (cards iguais descendo).
- A fala vira o jogo ("mas e se…", "pare de…")? → a mesma lista volta com `riscar` e sai por desfoque.
- A fala tem uma cena concreta ("o cliente explicou na reunião")? → `quadro` `imagens` com 1-4 fotos geradas.
- A fala nomeia 3-5 conceitos paralelos? → `cards` (leque, cada um acende no nome; com `arquivo` vira card
  com foto) + `titulo` de 2 linhas.
- Gancho → foto-meme no topo (`quadro` `imagem`, estilo `meme`) e, logo depois, recorte em primeiro plano
  (`adesivo`, estilo `recorte`) na frase seguinte. Objeto/metáfora concreta no meio do vídeo ("tempo" →
  ampulheta) também vira `adesivo`.
- A fala explica que uma coisa gera várias? → `mapa` (centro + nós).
- A fala fala de "jogar/mandar/dar" informação pra IA? → `chat` com `enviar` na palavra.
- Prova do processo (gravação de tela do usuário)? → `quadro` `video`.
- Resultado / entregáveis prontos? → `painel` `pasta` (cobre o rosto 2-4 s).
- Número de resultado (views, vendas)? → `painel` `print` com `marcas` na palavra do número.
- Nome de série ou produto (o `produto` do perfil)? → `titulo` (texto grande + etiqueta na cor de destaque).
- Frase de opinião forte? → DEIXAR LIMPO, em close. É o respiro que faz o rosto pesar.
Meta: elemento na tela em ~60-70% do vídeo; nenhum trecho limpo passando de ~6 s.
A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.

## 3. Cortar, medir, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K HEVC (rodar em segundo plano)
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada (Vision) → medidas.json
$PY $S/gerar_imagens.py "$E"        # imagens do mapa["imagens"] → assets/ (~US$0,05 cada; pula as que existem)
$PY $S/mascaras.py "$E"             # recorte da pessoa nos trechos de quadro (~4-6 min p/ 900 quadros, 2º plano)
$PY $S/compor.py "$E" --so-quadros 0.5,3.9,10.9,20.6,23.2,25.9,27.6,32.9,35.0,43.6
```
`compor.py` imprime a altura do quadro, a linha do tempo, a hora de cada item e os ATENÇÃO (item que
surge tarde demais, cena curta). Mudou tempo de quadro ou a base → rodar `mascaras.py` de novo. Ler as prévias em tamanho real: texto dentro dos cards, legenda fora do rosto, nada
embaixo de 78% da altura. Base mudou → rodar `medir.py` de novo.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~10 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(cena do quadro branco com a forma de entrada, itens que entram numa frase seguinte, painel, recorte de
papel, título na parede, volta pra pessoa em tela cheia, CTA), com código (4B), tempo, o que entra em
português e os avisos (item que surge tarde, elemento curto, elemento na tela fora de 60-70%, trecho só
com a pessoa passando de ~6 s). Cena sem nada novo aparece com um quadro só ("só a pessoa + legenda").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~2-4 MB, imagens embutidas).
- Esperar "aprovado". Pedido por código ("4B: troca a foto", "7: tira o recorte") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu no tempo de um quadro, `--storyboard` de novo e reenviar. Só o
  storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos elementos,
  quando cada um está inteiro na tela).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~2-4 min → preview_remy.mp4
$PY $S/conferir.py "$E" "$E/preview_remy.mp4"          # silêncios, emendas, loudness, folha de contato
```
`conferir.py` tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP.
Ler `verify/folha.jpg`. Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final` → `medir.py --final` → `mascaras.py --final` → `compor.py --final` →
`conferir.py` (~6 min no total; a final não precisa de ajuste além dos da prévia).

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: `[palavra, tomada]` (cena entra 0,12 s antes da palavra; ITEM acontece na palavra),
`[palavra, tomada, atraso]` ou segundos. `ate` omitido = fim da tomada do `em`. Palavra sem pontuação,
tem que existir NAQUELA tomada (a 1ª ocorrência vale). Assets em `<edit>/assets/` (nome sem extensão).
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "imagens": [                                  // gerar_imagens.py → assets/<nome>.png; descricao em inglês
    {"nome": "gancho_meme", "estilo": "meme", "descricao": "an exhausted architect buried under ..."},
    {"nome": "copiadora", "estilo": "recorte", "descricao": "a vintage office photocopier spitting ..."},
    {"nome": "reuniao", "estilo": "foto", "descricao": "a female architect explaining a floor plan ..."}],
  "quadro": [                                   // um por vez; cenas coladas trocam por desfoque
    {"tipo": "lista", "em": 0, "titulo": "informação do cliente",
     "itens": [{"texto": "o que a família precisa", "em": ["organizando", 0]}, ...],
     "saidas": {"n": 4, "em": ["várias", 0], "rotulo": "CÓPIA"}},
    {"tipo": "lista", "em": ["mas", 7], "ate": ["briefing", 7], "titulo": "você refaz", "nota": "tudo de novo?",
     "riscar": ["se", 7], "itens": [{"texto": "briefing pra equipe"}, ...]},   // item sem "em" = já está lá
    {"tipo": "cards", "em": ["você", 6], "itens": [{"texto": "conversas", "em": ["conversas", 6]}, ...],
     "titulo": ["informação", "espalhada"], "titulo_em": ["procurando", 6]},
    {"tipo": "chat", "em": ["briefing", 7], "ate": ["inteligência", 8], "placeholder": "Pergunte ao Claude",
     "itens": [{"rotulo": "reunião.m4a", "icone": "audio"}, {"rotulo": "anotações", "icone": "doc"},
               {"rotulo": "WhatsApp", "icone": "chat"}], "enviar": ["única", 7]},   // icone: audio|doc|chat|imagem(+arquivo)
    {"tipo": "video", "em": ["inteligência", 8], "arquivo": "gravacao-de-tela.mov", "inicio": 5.8,
     "velocidade": 2, "recorte": [1860, 300, 1450, 1160]},
    {"tipo": "mapa", "em": ["em", 9, 0], "centro": "briefing", "angulos": [-150, -30, 90],
     "itens": [{"texto": "proposta comercial", "em": ["proposta", 9]}, ...]},
    {"tipo": "imagem", "em": 0, "ate": ["organizando", 0], "arquivo": "gancho_meme"},  // cobre o quadro
    {"tipo": "imagens", "em": ["cliente", 1], "proporcao": "3:2", "girar": false,
     "itens": [{"arquivo": "reuniao", "em": ["cliente", 1], "rotulo": "opcional"}]}
    // todo quadro aceita "na_frente": false (cabeça fica embaixo da borda) e "divisao" (altura própria)
  ],
  "painel": [                                   // fora do quadro; nunca junto com quadro
    {"tipo": "pasta", "em": ["processo", 10], "rotulo": "residência-ana", "selo": "✓ PRONTO",
     "itens": [{"arquivo": "doc_briefing", "em": ["fica", 10]}, ...]},          // até ~5 miniaturas
    {"tipo": "print", "em": [...], "arquivo": "insights", "largura": 0.86,
     "marcas": [{"em": ["milhão", 11], "caixa": [x, y, w, h]}]},              // caixa em px da imagem original
    {"tipo": "pilha", "em": [...], "itens": ["perfil1", "perfil2"], "passo": 0.4, "degrau": 210}
  ],
  "titulo": [{"texto": "MEU PRODUTO", "etiqueta": "NOVO", "em": ["conheça", 12]}],   // texto = produto do perfil
  "adesivo": [                                  // colagem na frente da pessoa; vários ao mesmo tempo
    {"arquivo": "copiadora", "em": ["organizando", 0], "largura": 0.6, "x": 0.7, "giro": -4},
    {"arquivo": "ampulheta", "em": ["economizar", 11], "largura": 0.42, "x": 0.76, "giro": 5, "entra": "pop"}],
  "cta": {"texto": "clica em", "palavra": "SAIBA MAIS", "aspas": false, "em": ["clique", 12],
          "palavra_em": ["saiba", 12]},          // comentário: "texto": "comenta", "palavra": "SKILL" (aspas true)
  "layout": {"divisao": 0.55, "sobe": 190, "leg_peito": 330},   // opcional, ver LAY no compor.py
  "destaque": "#FFC700",                          // opcional; sem ele vale a cor_destaque do perfil
  "sfx": true,                                    // opcional; false desliga, {"db": -24} muda o volume
  "musica": {"arquivo": "trilha.mp3", "db": -30}  // opcional; a referência NÃO tem música
}
```

## Regras do estilo (não mudar sem o usuário pedir)
- Abertura: o vídeo começa LIMPO (só a pessoa); a 1ª tela dividida surge em ~0,3 s. Nunca começar com o
  quadro já montado no quadro 0. Medido na referência a 25 qps: quadro 0 limpo, de 0,04 a 0,20 s a imagem
  de cima dissolve saindo maior e assenta. No motor: a 1ª cena do vídeo (`em` ≈ 0) entra com
  `"entra": "surge"` (automático; 0,3 s, `dur_entra`): painel 8% maior → 100%, desfoque → nítido,
  transparente → opaco, a imagem da pessoa desce junto e a legenda viaja do peito pro lugar dela. No meio
  do vídeo continua corte seco (como na referência).
- Quadro branco: do topo até a borda (até 55%, a borda da referência; a conta PH_QUADRO, boca até 80% da altura, baixa pro rosto caber), fundo
  quase branco com grade pontilhada, borda reta. A CABEÇA DA PESSOA PASSA NA FRENTE da borda (`sobe` 190 px,
  medido no ponto mais alto da tomada; com 130 quase não aparece), recortada pelo Vision (`mascaras.py`).
  Sombra leve só no quadro (vazando abaixo da borda ela desenha uma linha no cabelo). A altura do quadro
  é a MESMA em todas as cenas (conta feita com o maior rosto do vídeo): altura variando entre cenas
  coladas faz a borda pular. Os componentes se arrumam na altura útil `uh` (acima da cabeça e da
  legenda). Entra por corte seco; dentro dele, troca de cena por desfoque (~0,3 s).
- Imagem desenha a frase: foto no quadro, foto-meme no gancho, recorte de papel em primeiro plano.
  Gancho no molde da referência: foto-meme no topo (`quadro` `imagem`) → tela cheia com recorte em
  primeiro plano (`adesivo`). Colagem = recorte com borda branca de papel cortado, preso na base da tela,
  vários ao mesmo tempo, gerado com `gerar_imagens.py` estilo `recorte` (o fundo transparente do
  gpt-image-1.5 funciona de primeira). Dentro do quadro: cena `imagens` (grade de fotos entrando na
  palavra), card com foto (`arquivo` no item dos `cards`) e chat recebendo as mesmas fotos. Custo:
  ~US$0,05 por imagem (7 imagens ≈ US$0,35).
- Título na parede (e `print`) sem espaço acima da cabeça: a imagem da pessoa DESCE em 0,3 s (o espaço de
  cima vira continuação da parede, borrada) e volta quando o título sai.
- Tamanho dos componentes: os da referência (720p) ficam miúdos no 1080, então tudo é ~35% maior que a
  medida × 1,5. A lista calcula a largura pelo item mais longo e encolhe a letra se não couber com o
  post-it ao lado.
- Nada aparece pronto: entra do desfoque (0,15-0,2 s), em cascata ou desenhando a linha. Item acontece
  NA palavra falada.
- Cor de interface: a cor de destaque do perfil, padrão #FFC700, no lugar do azul elétrico da referência (pílula central, borda do card ativo, pasta, fita, marca-texto).
  Linhas em cinza-escuro (amarelo em fundo branco não lê). Risco à mão em vermelho #CC422A.
- Letras: interface Avenir Next; números/rótulos Menlo; anotação à mão Noteworthy Bold; títulos e
  legenda Poppins Bold.
- Legenda: blocos de 2-3 palavras, Poppins Bold 66 branca (no lugar da fonte pixelada da referência,
  que é a assinatura daquele criador), sombra + contorno escuro fino, sem pontuação.
  Com quadro branco: vira texto PRETO escrito no quadro, numa faixa logo acima da cabeça (`faixa_leg`),
  porque com a cabeça encostada no quadro e rosto grande a legenda no peito cai na boca (a referência
  faz o mesmo em 31,9 s). Em cima de foto ou gravação de tela continua branca; na pasta fica preta.
  Em tela cheia: 330 px abaixo do "rosto" do Vision (`leg_peito`; o retângulo do Vision termina na boca,
  não no queixo), nunca abaixo de 78% da altura.
- CTA: linha pequena + palavra grande na cor de destaque na 2ª linha (entra com mola na palavra falada).
- Som: sem música; whoosh nas entradas grandes, pop nas miniaturas/etiqueta/CTA, risco de caneta no
  risco e no marca-texto, tudo baixo (-24 dB).

## Armadilhas
- As do /reel-glow sobre corte e áudio continuam valendo (`cortar.py` e `conferir.py` são os mesmos).
- Base nova = `medir.py` de novo (o compor para se o número de tomadas não bater).
- Prévia `--so-quadros` lê UM quadro de cada vídeo por prévia; no vídeo final o leitor anda quadro a quadro.
- `pilha` e `print` ainda não foram testados num vídeo real: conferir as prévias com cuidado na 1ª vez.
- Sem `masks/out/` o compor para (quadro com a cabeça na frente precisa do recorte).
- Enquadramento fechado (topo do cabelo em y≈200-270 de 1920, rosto grande): legenda abaixo do queixo
  cai na boca. É por isso que no quadro ela vira texto preto na `faixa_leg` e, em tela cheia, desce pelo
  `leg_peito` medido a partir da boca.
- Cena que entra com a antecipação (0,12 s, `antecipa`) antes do fim da tomada anterior: a de trás cede o
  lugar sozinha, só quando ela não tem `ate` explícito.
- Storyboard: a gravação de tela no quadro é lida por busca direta no tempo (como no `--so-quadros`); com
  o leitor contínuo ela devolve o quadro errado fora de ordem.
- Imagem gerada com texto embutido ou mão deformada passa despercebida na folha pequena: abrir cada uma.
