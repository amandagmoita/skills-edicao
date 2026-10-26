---
name: reels-nick
description: >
  Edita um vídeo cru de cabeça falante no estilo "Nick" (mapeado de três Reels de ferramentas de IA):
  cada substantivo da fala vira imagem no mesmo segundo. Alterna três telas a cada 2-3 s: tela dividida
  (fundo claro em cima com o elemento, a pessoa num cartão de cantos arredondados embaixo e a cabeça
  passando por cima da borda), tela cheia (card do item da lista, logo grande, fluxo, janela no escuro) e
  close no rosto. Elementos: logos oficiais que se acumulam, card "O SEGUNDO" com ícone do app, janela de
  navegador com a página real (marca-texto, contorno no número, cursor clicando, contador rodando),
  contador, fluxo que se desenha, gráfico que cresce, antes x depois, foto da pessoa citada, órbita de
  logos, logo digitando e título do gancho com pílula. Legenda acumula palavra a palavra com
  palavra-chave em serifa itálica; CTA "comenta + PALAVRA" com brilho. Gatilhos: "/reels-nick", "edita no
  estilo Nick", "edita com tela dividida e logos", "edita igual aqueles reels de ferramentas", "edita
  mostrando os apps na tela". Para estilo telão ver /reel-telao; quadro branco ver /skill-remy; glow ver
  /reel-glow; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reels Nick

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @, cor de
destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (cor de destaque,
palavra/produto do CTA). Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou
preencher o arquivo (modelo em `~/.claude/padroes-edicao/perfil.exemplo.json`).

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack. O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê de cada
número) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem
fazer outro corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill: o `cortar.py ... base` já corta assim (imprime "N emendas sobrepostas, som de A por
  baixo X-Y ms"). O `conferir.py` mede na linha 2: som da fala anterior por baixo entre 120 e 200 ms,
  sem estalo, juntas coladas iguais à fonte. `words_out.json` segue o SOM: a última palavra de uma fala
  aparece quando é ouvida, mesmo com a imagem já na tomada seguinte. `base_info.json` traz o `plano`.

## 0. Antes de começar
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo vai em `<pasta>/nick/`.
  Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do vídeo antes de transcrever (nome com "edit" pode ser vídeo pronto).
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reels-nick/scripts
E="<pasta>/nick"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Se outra skill já cortou esse vídeo
(pasta `remy/`, `telao/`...), copiar `edl.json base_info.json words_out.json medidas.json` e ligar
`base_*.mov` em vez de refazer: mesmo corte, mesmas tomadas.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
echo '{"fonte":"<video>","tomadas":[]}' > "$E/mapa.json"
$PY $S/cortar.py "$E" frases
```
Fala contínua como na referência (maior pausa ~0,25 s). Uma tomada por frase.

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
O trabalho aqui é traduzir cada frase em imagem. Pergunta por frase: "o que a pessoa está NOMEANDO?"
- Nome de app, ferramenta, marca → `logos` (vários na mesma frase = acumulam) ou `item` (é um item da lista:
  "o primeiro é...", "o segundo..."). Logo/ícone OFICIAL sempre (`logos.py`).
- "Se chama X", produto, site → `janela` com a página/app real (print ou gravação de tela real). Número
  falado que está na página → `contornos` + `contador` no balão. Lista de categorias falada → `cliques`.
  Frase que está escrita na página → `marcas` (marca-texto correndo).
- Número solto ("mais de 600 modelos") → `contador`.
- Várias coisas que viram uma (ou uma que vira várias) → `fluxo` (`sentido` "entra" ou "sai").
- Crescimento, antes/depois em número → `grafico`; antes/depois visual → `comparacao`.
- Pessoa citada (CEO, criador, cliente) → `foto` na dividida (cobre o fundo, a cabeça da pessoa passa na frente).
- "X ferramentas", ecossistema → `orbita`. Marca que merece momento → `digitando`.
- Gancho → `dividida` com `titulo` (linha preta + pílula na cor de destaque) e a prova embaixo.
- Benefício, opinião, frase de efeito, CTA → `rosto` (close). No CTA, a palavra/produto vem do perfil. Não precisa cena: o que fica fora das cenas
  é close (`padrao`).

Ritmo da referência: troca de tela a cada 2-3 s, algo acontecendo a cada ~1 s dentro da cena; dividida
30-46%, cheia 36-48%, rosto 17-22% (o `compor.py` imprime as três). Card do item dura ~1 s.

A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.
```bash
$PY $S/logos.py "$E" app:Claude app:WhatsApp app:Notes=notas si:anthropic si:claude:#D97757=claude_logo
$PY $S/gerar_imagens.py "$E"      # foto ilustrativa (gpt-image, ~US$0,05) só quando não existir foto real
```
Prints de tela: extrair o quadro da gravação de tela com ffmpeg, recortar a área útil e medir as caixas
(marca-texto, contorno, clique) numa cópia com grade (`drawgrid`). Coordenadas em px da imagem recortada.

## 3. Cortar, medir, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K (segundo plano)
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada → medidas.json
$PY $S/mascaras.py "$E"             # recorte da pessoa nas telas divididas (~40 s); refazer se as cenas mudarem
$PY $S/compor.py "$E" --so-quadros 0.3,1.5,3.5,5,7,9.5,13.5,16,21,24,28,31,36,40,44
```
Ler as prévias em tamanho real: cabeça passando por cima do cartão sem cortar, legenda fora do rosto e
acima da cabeça na dividida, texto da janela legível, nada abaixo de 78% da altura, card do item com o
ordinal acima do ícone. `compor.py` avisa cena curta e item que acontece tarde.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~3 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(tela dividida/cheia/close com o elemento, título do gancho, logo ou item que entra numa frase seguinte,
volta pro close, CTA), com código (4B), tempo, o que entra em português e os avisos de ritmo (cena curta,
item tarde, close que pisca, tempo por tela fora da referência). Cena sem nada novo aparece com um quadro
só ("Só você").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~1,5-4 MB, imagens embutidas).
- Esperar o "aprovado" do usuário. Pedido por código ("4B: troca o logo", "7: tira o contador") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu no tempo de uma tela dividida, `--storyboard` de novo e reenviar. Só o
  storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes das telas e
  elementos, quando cada um está inteiro na tela).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~3-5 min → preview_nick.mp4
$PY $S/conferir.py "$E" "$E/preview_nick.mp4"          # silêncios, emendas, loudness, folha de contato
```
Tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP. Ler `verify/folha.jpg`.
Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `medir.py --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: `[palavra, tomada]` (cena entra 0,12 s antes; item acontece NA palavra), `[palavra, tomada, atraso]`
ou segundos da saída. Cena sem `ate` vai até a próxima cena ou o fim da tomada do `em`.
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "destaque": "#FFC700",                 // palavra-chave, contador, contorno, pílula, clique (padrão: cor do perfil; azul da referência #3188FD)
  "destaque2": "#E79786",                // ordinal do card do item
  "destaques": ["mesma", "zero"],        // palavras da legenda em serifa itálica na cor de destaque
  "padrao": {"layout": "rosto", "zoom": 1.15},   // fora das cenas: close
  "cenas": [
    {"layout": "dividida", "em": 0, "tipo": "janela", "titulo": ["Quanto tempo você perde", "organizando?"],
     "arquivo": "../gravacao-tela.mov", "inicio": 5.8, "velocidade": 2, "recorte": [x, y, w, h], "url": "claude.ai"},
    {"layout": "dividida", "em": ["cliente", 1], "tipo": "foto", "arquivo": "pessoa.png"},
    {"layout": "cheia", "em": ["mas", 2], "tipo": "janela", "arquivo": "print", "url": "claude.ai",
     "fundo": "desfocado",                                     // padrão da janela em tela cheia
     "marcas": [{"caixa": [x, y, w, h], "em": ["equipe", 2], "dur": 0.5}],
     "contornos": [{"caixa": [x, y, w, h], "em": ["briefing", 2]}],
     "cliques": [{"ponto": [x, y], "caixa": [x, y, w, h], "em": ["demos", 3]}],
     "contador": {"de": 0, "valor": 230, "rotulo": "exemplos reais", "em": ["230", 3], "ponto": [x, y]},
     "rolagem": [["organizado", 2, 0.22, 0.6]]},               // [palavra, tomada, fração, duração]
    {"layout": "dividida", "em": [...], "tipo": "logos", "itens": [
       {"arquivo": "claude", "em": [...]}, {"texto": "Google AI Studio", "arquivo": "gemini", "em": [...]}]},
    {"layout": "cheia", "em": [...], "tipo": "item", "arquivo": "strix", "ordem": "o segundo", "nome": "Strix",
     "fundo_icone": false},                                    // true = logo solto vira ícone branco
    {"layout": "cheia", "em": [...], "tipo": "fluxo", "sentido": "entra",   // "sai" = centro em cima
     "centro": {"rotulo": "briefing"}, "itens": [{"rotulo": "proposta\ncomercial", "em": [...]},
                                               {"arquivo": "linkedin", "em": [...]}]},
    {"layout": "dividida", "em": [...], "tipo": "contador", "valor": 600, "prefixo": "+", "rotulo": "modelos",
     "em_numero": ["600", 4]},
    {"layout": "dividida", "em": [...], "tipo": "grafico", "nome": "Estrelas no GitHub",
     "pontos": [0, 2, 5, 14, 30, 61], "eixo_x": ["jan", "abr", "jul"], "valor_final": "61 mil"},
    {"layout": "cheia", "em": [...], "tipo": "comparacao", "rotulos": ["original", "com IA"],
     "itens": [{"arquivo": "a.mp4"}, {"arquivo": "b.mp4"}], "fundo": "desfocado"},
    {"layout": "cheia", "em": [...], "tipo": "orbita", "centro": "google", "itens": [{"arquivo": "x"}, ...],
     "titulo": ["10 ferramentas", "de graça"]},
    {"layout": "cheia", "em": [...], "tipo": "digitando", "arquivo": "anthropic", "texto": "Anthropic",
     "em_texto": ["anthropic", 9]},
    {"layout": "cheia", "em": [...], "tipo": "imagem", "arquivo": "x.png"},          // ou "video"
    {"layout": "rosto", "em": [...], "ate": [...], "zoom": 1.32}
  ],
  "cta": {"texto": "comenta", "palavra": "CLAUDE", "em": ["comenta", 12], "palavra_em": ["claude", 12]},
  "layout": {"card_escala": 0.84, "cabeca": 0.50},         // opcional, ver LAY no compor.py
  "sfx": {"db": -26},                                       // false = sem efeito
  "musica": {"arquivo": "trilha.mp3", "db": -30}            // opcional (v2 tem trilha ~5 dB abaixo da voz)
}
```
Fundos: `branco` (padrão), `fosco` (o próprio vídeo borrado e lavado, v1), `escuro`, `preto`, `desfocado`
(vídeo borrado e escurecido, padrão da janela em tela cheia), `#hex` (cor da marca citada) ou arquivo.
Legenda da cheia: `"legenda": "serifa"` (padrão, caixa alta itálica) ou `"sans"`; `false` esconde.

## Regras do estilo (não mudar sem o usuário pedir)
- Material REAL: logo oficial, página verdadeira, gravação de tela real. Ilustração genérica só sem opção.
- Tudo entra por desfoque (nasce menor, borrado e transparente, assenta em ~0,2 s). Troca de tela é corte seco.
- Dividida: vídeo da pessoa num cartão de cantos arredondados com sombra e brilho fino; a cabeça passa por cima
  da borda; legenda preta logo acima da cabeça; elemento no espaço de cima.
- Legenda: SF Pro Bold, 1-3 palavras, acumulando palavra a palavra, cada uma entrando por desfoque; sem
  pontuação. Palavra-chave em New York Bold Italic na cor de destaque; número em sans na cor de destaque. Na cheia, serifa
  itálica caixa alta.
- CTA no close: "comenta" em serifa itálica + PALAVRA em SF Pro Heavy com degradê e brilho na cor de destaque.

### Cor de destaque
- Padrão = cor de destaque do perfil (`"destaque"` no mapa sobrescreve; o azul da referência é `#3188FD`).
  `"destaque2"` (#E79786, salmão) é o ordinal do card do item.
- Cor CLARA (luminância > 165, ex.: amarelo #FFC700) some em fundo branco, então o motor aplica sozinho
  (`ACENTO_CLARO`): texto preto em cima da pílula; palavra-chave em fundo claro vira texto preto sobre
  faixa da cor (marca-texto); contorno, clique e linha do fluxo na cor escurecida 12% e mais grossos (5
  px); número em fundo branco escurecido 22%; marca-texto da página na cor clareada; borda da janela na
  cor. No vídeo e no fundo escuro a cor vai direto no texto (lê bem com a sombra dupla). Cor escura (o
  azul) não muda nada disso.
- Escolhas do usuário (perguntar, não decidir): cor de destaque, trilha de fundo (só com licença de uso;
  padrão sem música), efeito sonoro (padrão: whoosh leve nas trocas de tela, pop nos itens, clique no
  cursor, -26 dB).

### Medidas que fazem a dividida funcionar
- Gravação em close (topo do cabelo em y≈200-270 de 1920, rosto ~440 px): vídeo a 0,84x no cartão
  (`card_escala`), cabelo em ~50% da altura (`cabeca`) e borda do cartão em ~67%. A proporção bate com a
  referência (v3).
- Roupa clara come a legenda branca no close: a sombra é dupla (justa + halo largo), e a palavra-chave
  no vídeo clareia 30% pra não sumir em roupa branca.

## Armadilhas
- Base nova = `medir.py` e `mascaras.py` de novo (o compor para se o número de tomadas não bater).
- Mudou o tempo de uma cena dividida → `mascaras.py` de novo (recorta só os quadros da dividida).
- Prévia `--so-quadros` lê UM quadro de cada vídeo por prévia; no vídeo final o leitor anda quadro a quadro.
- Caixas de marca-texto/contorno são medidas no print RECORTADO; se mudar o recorte, medir de novo.
- Gravação 4K do Claude: o texto só fica legível no celular com recorte de ~1400-1500 px de largura.
- Marca em texto comprida ("Programa de necessidades") estoura a largura: o motor encolhe pra 92% do
  palco e, na ida pra fileira, encolhe antes de andar (senão atravessa a tela).
- Ícone de app sai perfeito do próprio macOS (`logos.py app:Nome`); logo de marca vem do Simple Icons
  renderizado pelo Quick Look (o Mac não tem conversor de SVG nativo).
- Chave de elemento NÃO pode repetir chave de cena: `ate` (hora de sair) e `titulo` (título do gancho)
  são da cena. Por isso o número final do contador é `valor` e o título do gráfico é `nome`.
- Storyboard: vídeo dentro da janela/foto é lido por busca direta no tempo (como no `--so-quadros`);
  o leitor contínuo devolveria o quadro errado fora de ordem.
- Contador, gráfico, antes x depois, órbita, cliques e contador dentro da janela e foto em cartão foram
  conferidos só em prévia (`referencia/mapa-teste-elementos.json`); olhar com atenção na 1ª vez que forem
  pro vídeo final.
