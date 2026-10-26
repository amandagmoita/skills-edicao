---
name: reels-kelsey
description: >
  Edita um vídeo cru de cabeça falante no estilo "Kelsey" (mapeado de 4 Reels da corretora Kelsie
  Blevins, @_k.elsie): capa de revista em movimento. As palavras fortes viram TÍTULO em serifa grande
  (Bodoni) colado na pessoa, montado palavra por palavra na fala: desvia só do rosto e passa por cima do
  cabelo e do corpo como vidro; palavra-chave em rosa vivo e segunda palavra em azul-prata, os dois com
  metalizado sutil e halo escuro. Legenda em Helvetica Neue itálica no peito, que some quando entra
  título. Dados viram objetos neon (número enchendo, arco em volta da cabeça, barra que conta); itens
  viram pílulas que nascem de um ponto (pretas com borda neon ou de vidro roxo); material real em 3D
  (dois prints em livro aberto atrás da pessoa, cards girando na cintura, muro de fotos atrás, print em
  tela cheia com caneta vermelha). Notificação de vidro, balões de chat, ícones pulando, lista em
  pílulas de vidro, cronômetro. Câmera: degraus de zoom por corte seco, aproximação suave, flash branco
  com zoom out, desfoque de passagem. Sem música. Gatilhos: "/reels-kelsey", "edita no estilo Kelsey",
  "edita com título de revista", "edita estilo revista", "edita igual a corretora". Para tela dividida
  com logos ver /reels-nick; quadro branco ver /skill-remy; glow ver /reel-glow; referência NOVA =
  analisar do zero. Idioma: PT-BR.
---

# Reels Kelsey

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @, cor de
destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (nome na
notificação, @ e produto/link no CTA). Se o arquivo não existir, pedir ao usuário pra rodar o
`instalar.sh` do pack ou preencher o arquivo (modelo em `~/.claude/padroes-edicao/perfil.exemplo.json`).

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

## 0. Antes de começar
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo vai em `<pasta>/kelsey/`.
  Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do vídeo antes de transcrever (nome com "edit" pode ser vídeo pronto).
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reels-kelsey/scripts
E="<pasta>/kelsey"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Se outra skill já cortou esse
vídeo (pasta `remy/`, `nick/`, `telao/`...), copiar `edl.json base_info.json words_out.json medidas.json`
e ligar `base_*.mov` em vez de refazer: mesmo corte, mesmas tomadas.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
```
Fala colada como na referência (nenhuma pausa acima de ~0,15-0,25 s). Uma tomada por frase.

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
Pergunta por frase: "qual é a palavra que eu poria na capa da revista?" e "a pessoa está citando um
dado, uma lista ou uma prova?"
- Gancho, virada, frase de efeito, CTA → `titulos` (2-4 palavras, até 3 linhas). Um a cada 4-8 s.
  Palavra-chave entre `*asteriscos*` (material principal, rosa), segunda palavra entre `+mais+`
  (segundo material, azul-prata), palavra de ligação entre `_sublinhado_` (sans pequena encostada),
  itálico entre `/barras/`. Cada palavra entra NA fala; palavra que a pessoa não fala entra junto com a
  anterior. No CTA, usar o produto e o @ do perfil.
- Número falado → `numero` (neon enchendo; `"de": 0` conta subindo; `"atras": true` = atrás da cabeça).
  Crescimento de A pra B → `arco` (pílula com A, arco desenha em volta da cabeça, pílula com B).
  Porcentagem/progresso → `barra`.
- 2-3 itens falados → `pilulas` (`"estilo": "neon"` pretas com borda, ou `"vidro"` roxas). Lista mais
  longa → `lista` (pílulas de vidro empilhadas à esquerda).
- "O cliente disse...", mensagem → `notificacao` (vidro, desce do topo; sem `nome` usa o nome do perfil,
  sem `avatar` usa o rosto da pessoa tirado do vídeo). Cobrança repetida → `baloes`.
- Ferramentas/redes citadas → `icones` (logo oficial: `logos.py`, pulam um por um na palavra).
- Prova com material real da pessoa: prints/Reels → `cards` (girando na cintura) ou `livro` (dois prints
  em V atrás da pessoa); bagunça/volume → `muro` (fotos atrás da pessoa, entra com flash); print com
  detalhe a apontar → `tela` (tela cheia, caneta vermelha circula na palavra).
- Metáfora literal (chave, ampulheta) → `objeto` (png voando e flutuando; gerar com `gerar_imagens.py`).
  "Em 30 segundos" → `cronometro`.
- Câmera (o ritmo do estilo): `degraus` (corte seco pra mais perto, ~1,12-1,18x) no começo de frase ou
  na palavra forte; `aproxima` (suave, 0,5 s) no dado ou na frase de impacto; `transicoes` `flash` na
  virada do roteiro ("Mas e se..."), `desfoque` pra ir/voltar de um detalhe.

Ritmo da referência: algo novo na tela a cada ~1-1,5 s; o `compor.py` avisa buraco de 3 s sem nada.
A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.
```bash
$PY $S/logos.py "$E" app:Claude app:WhatsApp app:Notes=notas si:instagram
$PY $S/gerar_imagens.py "$E"      # objeto/foto ilustrativa (gpt-image, ~US$0,05) só quando não existir real
```

## 3. Cortar, medir, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K (segundo plano)
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada → medidas.json
$PY $S/mascaras.py "$E"             # recorte da pessoa nos trechos com algo ATRÁS (~45 s); refazer se o mapa mudar
$PY $S/compor.py "$E" --so-quadros 0.5,1.5,3.5,5,7,9.5,13.5,16,21,24,28,31,36,40,44
```
Ler as prévias em tamanho real: título legível (inclusive a parte em vidro sobre a pessoa), nada sobre o
rosto, nada vazando pela borda, legenda fora do rosto, nada abaixo de 76% da altura, pílula sem bater na legenda.
`mascaras.py` precisa rodar de novo sempre que mudar o tempo de título/muro/livro/cards/arco/número atrás.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~5 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(título, elemento, degrau, aproximação, transição), com código (4B), tempo, o que entra em português e
os avisos de ritmo. Cena sem nada novo aparece com um quadro só ("Só você").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~3-4 MB, imagens embutidas).
- Esperar o "aprovado" do usuário. Pedido por código ("4B: troca o título", "7: tira o número") → mudar
  o `mapa.json`, `mascaras.py` de novo se mexeu em algo atrás da pessoa, `--storyboard` de novo e
  reenviar. Só o storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos elementos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~4-6 min → preview_kelsey.mp4
$PY $S/conferir.py "$E" "$E/preview_kelsey.mp4"        # silêncios, emendas, loudness, folha de contato
```
Tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP. Ler `verify/folha.jpg`.
Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `medir.py --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`; todos os elementos:
`referencia/mapa-teste-elementos.json`)
Tempos: `[palavra, tomada]` (entra 0,06 s antes), `[palavra, tomada, atraso]` ou segundos da saída.
Sem `ate`, vai até o fim da tomada do `em`.
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "material": "rosa", "material2": "cromo",         // *palavra* e +palavra+ (rosa lilas cromo cobre vinho azul dourado)
  "opacidade_titulo": 0.96, "vidro_titulo": 0.86,   // letra translúcida; quanto do título aparece por cima da pessoa
  "neon": "#FC49C2", "borda_pilula": "#FF2D55", "vidro": "#7A4FD8", "caneta": "#EC280B",
  "legenda_estilo": "italico",                    // "italico" (v1, Helvetica Neue Medium Italic) | "fino" (v4)
  "halo_titulo": 0.45,                              // halo escuro atrás das letras (fundo claro pede mais)
  "variacao_metal": 0.30,                           // 0 = cor chapada, 1 = metal líquido forte (difícil de ler)
  "zoom_tomadas": [1.0],                            // ciclo por tomada; [1.0, 1.1] alterna
  "degraus":  [{"em": ["organizando", 0], "z": 1.16}],
  "aproxima": [{"em": ["várias", 0], "z": 1.34, "dur": 0.6}],
  "transicoes": [{"tipo": "flash", "em": ["mas", 7, -0.05]}, {"tipo": "desfoque", "em": ["o", 10, -0.05]}],
  "titulos": [
    {"em": ["quanto", 0], "ate": ["organizando", 0], "linhas": ["Quanto *tempo*", "_um_ +empreendedor+", "perde?"]},
    {"em": ["meu", 12], "linhas": ["Meu *Produto*"], "material": "dourado", "material2": "cobre",
     "material_base": null, "y": 0.2, "frente": false, "centro": false, "tamanho": 180}
  ],
  "elementos": [
    {"tipo": "pilulas", "estilo": "neon|vidro", "em": [...], "itens": [{"texto": "Equipe", "em": [...],
      "lado": "esq|dir", "pos": [0.5, 0.53]}]},
    {"tipo": "lista", "em": [...], "itens": [{"texto": "...", "em": [...]}], "x": 0.06, "y": 0.40},
    {"tipo": "notificacao", "em": [...], "nome": "Cliente", "texto": "...", "avatar": "cliente.png"},
    {"tipo": "baloes", "em": [...], "texto": "Alguma novidade?", "rotulo": "Cliente", "itens": [{"em": [...]}]},
    {"tipo": "icones", "em": [...], "itens": [{"arquivo": "whatsapp.png", "em": [...], "pos": [0.2, 0.4]}]},
    {"tipo": "numero", "em": [...], "valor": "74%", "de": 0, "atras": false, "y": null, "tam": 330},
    {"tipo": "arco", "em": [...], "em_para": [...], "de": "6 mil", "para": "260 mil"},
    {"tipo": "barra", "em": [...], "valor": 403, "de": 0, "sufixo": "%", "rotulo": "mais pedidos"},
    {"tipo": "cronometro", "em": [...], "de": 30, "pos": [0.18, 0.62]},
    {"tipo": "objeto", "em": [...], "arquivo": "chave.png", "pos": [0.8, 0.3], "tam": 300, "card": false, "atras": false},
    {"tipo": "cards", "em": [...], "arquivos": ["a.png", "b.png", ...], "voltas_por_s": 0.22},
    {"tipo": "muro", "em": [...], "ate": [...], "arquivos": [...], "transicao": true},
    {"tipo": "livro", "em": [...], "arquivos": ["antes.png", "depois.png"]},
    {"tipo": "tela", "em": [...], "ate": [...], "arquivo": "print.png", "altura": 0.48,
     "circulos": [{"caixa": [x, y, w, h], "em": [...]}]}
  ],
  "layout": {"tit_largura": 0.94, "tit_max": 300, "tit_encosta": 22, "leg_tam": 60},   // ver LAY no compor.py
  "sfx": {"db": -27},                                 // false = sem efeito
  "musica": {"arquivo": "trilha.mp3", "db": -30}      // a referência não tem; só com licença de uso
}
```
Caixas da caneta: px do print original (abrir uma cópia com grade pra medir).

## Regras do estilo (não mudar sem o usuário pedir)
- Título em serifa de revista, GRANDE e colado na pessoa, palavra por palavra na fala, entrando ~1,35x
  maior e desfocada; sai com desfoque e rastro curto. Nunca sobre o rosto; sobre cabelo e corpo vira vidro.
  Palavra-chave em rosa vivo e claro com metalizado sutil (nada de faixa escura dentro da letra) e um
  brilho que corre uma vez; segunda cor azul-prata.
- Legenda da fala em Helvetica Neue (itálica encorpada, letras coladas), branca, 1-2 palavras trocando
  (não acumula), no peito; some com título e com tela cheia.
- Tudo que é dado brilha (neon). Pílula nasce de um ponto e estica. Ícone pula passando do tamanho.
- Prova = material real da pessoa (prints, Reels, fotos de cliente). Ilustração só pra metáfora (`objeto`).
- Câmera faz o ritmo: degrau seco, aproximação suave, flash branco na virada. Sem trilha.

### Padrão visual fechado (já é o padrão do `compor.py`; um mapa novo não repete nenhum valor)
Títulos em Bodoni 72 Bold grandes e colados na pessoa; palavra-chave `material` "rosa"; segunda palavra
`material2` "cromo" (azul-prata gelado); `variacao_metal` 0,30; letra 96% opaca (`opacidade_titulo`),
vidro 86% sobre a pessoa (`vidro_titulo`), halo escuro `halo_titulo` 0,45; legenda Helvetica Neue
Medium Italic 60 px, tracking -0,045. Mudar algum só quando o usuário pedir. Escolhas que são do
usuário (perguntar, não decidir): trocar o material da palavra-chave num vídeo específico (ex.:
`"material": "dourado"`, perto da cor de destaque do perfil, padrão #FFC700), cor neon dos dados (padrão
rosa #FC49C2), trilha (padrão sem música), legenda fina `"legenda_estilo": "fino"` (Light reta, v4).

### Título: como fica legível e "premium" (números que fazem o estilo funcionar)
- **Material, não cor chapada:** metal com faixas de reflexo leves, medido dentro das letras
  (`MATERIAIS` no compor: rosa, lilas, cromo, cobre, vinho, azul, dourado). `*palavra*` = material
  principal, `+palavra+` = segundo material, resto branco liso com sombra macia. Bisel de luz fina no
  alto da letra.
- **Metalizado sutil:** toda rampa de `MATERIAIS` usa só tons vivos e claros (rosa #C2288E → #FFA6DC;
  cromo #3E8FD0 → #DDF1FF, brilho 0,67-0,69). Com `variacao_metal` 0,30 o brilho dentro da letra varia
  com desvio ~0,10-0,12 e não desce de ~0,45; o miolo fica quase liso. Variação forte (desvio 0,16-0,19,
  faixas quase pretas até 0,22) atrapalha a leitura. Material novo entra com o tom mais escuro da rampa
  ainda vivo (brilho ≥ 0,45). Brilho branco só fraco.
- **Contraste vem do halo escuro atrás da letra, NUNCA de faixa escura dentro dela.** Fundo bege/claro
  come tom pastel: letra 96% opaca + halo largo 0,45 separam da parede. Conferir com número: saturação
  média do título ≥ 0,33 sobre o fundo (a referência mede ~0,35, pico 0,52-0,60).
- **Cromado claro some em roupa branca:** por isso o cromo é azul-prata vivo, não cinza.
- **Só o ROSTO é proibido.** Cabelo e corpo podem ficar por baixo das letras; a parte que passa por cima
  da pessoa aparece como vidro (86%), como "agent." no peito da referência (v2).
- **Escala:** linha ocupa até 94% da largura (`tit_largura`), corpo até 300 px (`tit_max`). A largura é
  medida no que foi desenhado (com sombra), senão a palavra vaza pela borda.
- **Gravação em close** (cabelo em y≈200-260 de 1920, rosto ~440 px): título centralizado atrás da cabeça
  some no meio. Cada linha que cai na altura do corpo se divide e contorna a cabeça, medindo a largura
  dela na máscara do Vision nessa faixa (como "You [cabeça] should" na v2). A largura é a UNIÃO de 5
  máscaras do trecho do título (a pessoa mexe a cabeça depois que a palavra entra).
- Linha que contorna a cabeça fica menor (cabe ~250 px de cada lado): títulos curtos, 2-4 palavras,
  palavra comprida sozinha na linha. Linha que não cabe dos lados do rosto pula pro peito em vez de encolher.

## Armadilhas
- Base nova = `medir.py` e `mascaras.py` de novo (o compor para se o número de tomadas não bater).
- Mudou o tempo de algo atrás da pessoa → `mascaras.py` de novo (só recorta os trechos com algo atrás).
- Prévia `--so-quadros` lê UM quadro da base por prévia; o título usa máscaras de 5 quadros do trecho,
  então a prévia já mostra a posição final.
- Elemento com chave repetida da cena: `em`, `ate` são do elemento; o número final da barra é `valor`.
- Bodoni 72 Bold é o título. Playfair (a da referência) não está no Mac: baixar só com o ok do usuário.
- Roupa branca come a legenda branca fina: a legenda tem sombra dupla (a referência quase não tem).
- Pílulas, número e barra se posicionam a partir da altura da legenda, não do rosto (senão batem nela).
- Transição do mapa vence a transição automática do muro/tela no mesmo instante (senão o flash some).
- Print largo de tela de computador fica pequeno na tela cheia: o motor amplia até 48% da altura
  (`"altura"` da `tela`) e centraliza nos círculos da caneta.
- A referência v3 (corte de pódcast, itálico rosa com rastro) é de outro editor e não entrou no motor;
  o estilo vem de v1, v2 e v4.
