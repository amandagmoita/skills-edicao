---
name: skill-iphone
description: >
  Edita um vídeo cru de cabeça falante no estilo "iPhone" (engenharia reversa de um tutorial de ajustes
  do Instagram): o logo da plataforma citada (Instagram, Claude, ChatGPT, WhatsApp...) acende em NEON
  atrás da cabeça da pessoa, ícones neon sobem e se encaixam no peito, título só de contorno com brilho e
  miolo transparente ("PASSO 1"), e a demonstração aparece dentro de um iPhone 3D que sobe do pé da tela,
  aproxima devagar, balança e mostra o toque marcado, com o fundo desfocado. Linha neon de crescimento,
  clarão laranja nas trocas de seção, cartão de perfil do Instagram no CTA, legenda pequena condensada na
  cor de destaque. Gatilhos: "/skill-iphone", "skill iPhone", "edita no estilo iPhone", "edita com o
  logo em neon atrás de mim", "edita mostrando no iPhone". Glow com gráficos em tela preta = /reel-glow;
  referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Skill iPhone

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @, cor de
destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal: o cartão de perfil
do CTA usa a foto e o @ do perfil, a legenda e o título usam a cor de destaque, o botão/CTA usa o
produto/link. Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher
o arquivo (modelo em `~/.claude/padroes-edicao/perfil.exemplo.json`).

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack. O vídeo da fala anterior sai 0,10 s antes da voz acabar, o áudio da fala anterior
continua ~0,16 s por baixo da tomada seguinte, a seguinte entra 0,04 s antes da própria voz.
Regra e código num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` + `corte_sobreposto.py`.
O `cortar.py` desta skill (cópia do compartilhado) já chama o módulo; o `conferir.py` mede. Nunca
reimplementar aqui.

## 0. Antes de começar
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo vai em `<pasta>/iphone/`. Nunca escrever na skill.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/skill-iphone/scripts
E="<pasta>/iphone"
```

## 1. Transcrever e escolher as tomadas
Igual às irmãs (/reels-nick seção 1). Se outra skill já cortou o vídeo, copiar
`edl.json base_info.json words_out.json medidas.json` e ligar `base_*.mov` (hard link). Ligar também o
arquivo que `base_info["base"]` aponta (pode ser `base_final.mov`), senão o `conferir.py` falha.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
$PY $S/cortar.py "$E" frases
```

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
Pergunta por frase: "o que a pessoa está nomeando ou demonstrando?"
- Nome de plataforma/app ("no Instagram", "o Claude") → `glows` (logo neon atrás da cabeça). Vários
  apps na mesma frase → `itens` (troca com piscada na palavra de cada um). SF Symbols
  (`logos.py sf:nome`) também viram bom logo neon de contorno (lupa, pasta, nota).
- Lista de coisas, "três ajustes", ferramentas → `icones` (SF Symbols neon, um por palavra; `gira` pra
  engrenagem).
- Passo, número da lista, virada → `titulos` ("PASSO 1", "DO ZERO"), 2-3 por vídeo. O título precisa de
  ~1,5 s na tela: ancorar 1-2 palavras antes da palavra-chave.
- "Faz assim", "clica em", "olha aqui" → `iphones` com a gravação de tela; `toques` no que a pessoa manda tocar,
  `focos` pra aproximar um detalhe da tela, `rolagem` em print comprido.
- Crescer, alcançar, mais resultado → `linhas` (onda neon verde no peito).
- Troca de seção (gancho → passo 1 → passo 2) → `claroes`.
- CTA de seguir/link → `cartao` (foto e @ do perfil; botão com o produto/link do perfil, ex. "Saiba mais").
Ritmo da referência: iPhone ~40% do tempo, logo neon ~19%, rosto limpo ~30%, algo novo a cada 1,5-3 s.
A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.
```bash
$PY $S/logos.py "$E" si:instagram si:claude si:whatsapp sf:gearshape.fill=engrenagem sf:doc.text.fill=doc
```
Gravação do iPhone (vertical, ~0,46) entra inteira, com a barra de status original. Gravação de computador:
recortar uma coluna vertical (largura/altura ~0,46) com `recorte` [x, y, w, h] em px da fonte, achada em
quadro com `drawgrid`; o motor desenha a barra de status (9:41, sinal, bateria).
- Recorte de ~950 px de largura (gravação 4K) × ~1800 de altura enche a tela do iPhone e o texto fica
  legível no tamanho real. Com 1300-1600 px de largura sobra ~40% de branco no pé.
- Chat (Claude, ChatGPT): `"alinha": "baixo"` (caixa de mensagem no pé, espaço livre em cima) parece app de chat.
- Olhar a gravação no trecho EXATO que vai pro iPhone (folha a 1 qps do recorte): janela do gravador de
  tela no começo, painel lateral abrindo (linha vertical no meio) ou quebra de página em branco estragam o
  trecho. Escolher `inicio`/`velocidade` pra cair só em conteúdo contínuo.

## 3. Cortar, medir, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl && $PY $S/cortar.py "$E" base
$PY $S/medir.py "$E"
$PY $S/mascaras.py "$E"            # recorte da pessoa nos trechos com logo neon atrás da cabeça
$PY $S/compor.py "$E" --so-quadros 0.3,3,8,12,20     # prévias em verify/quadros/
```

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~15 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(logo neon atrás da cabeça e cada troca, ícones neon, título de contorno, iPhone com a demonstração,
toque, foco, rolagem, linha neon, clarão, cartão de perfil e o toque no botão, aproximação de câmera),
com código (4B), tempo, o que entra em português e os avisos de ritmo (% de iPhone/logo/rosto limpo,
maior trecho sem nada novo, elemento curto demais, sobreposição). Cena sem nada novo aparece com um
quadro só ("Só você").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~2-3 MB, imagens embutidas).
- Esperar o "aprovado" do usuário. Pedido por código ("7B: troca o logo", "8B: o iPhone entra mais cedo") → mudar o
  `mapa.json`, `mascaras.py` de novo se mexeu no tempo de um glow, `--storyboard` de novo e reenviar. Só o
  storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos momentos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"              # → preview_iphone.mp4
$PY $S/conferir.py "$E" "$E/preview_iphone.mp4"
```
Tem que dar: maior silêncio ≈ 0,25 s, emendas certas, -14 LUFS, pico < -1 dBTP. Ler `verify/folha.jpg`.
Mudou o tempo de um glow → `mascaras.py` de novo. Mandar ao usuário o vídeo. Aprovado → tudo com `--final`.

## 5. mapa.json
Tempos: segundos da saída, `[palavra, tomada]` (0,12 s antes da palavra) ou `[palavra, tomada, atraso]`.
Sem `ate`, o elemento vai até o fim da tomada em que começa.
```jsonc
{
  "fonte": "meu-video.mov", "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "cor": "#FFC700",                       // legenda (padrão: cor de destaque do perfil); "cor_titulo" separado se quiser
  "zooms": {"1": [1.0, 1.06]},            // opcional, além do degrau alternado do cortar.py
  "glows": [{"logo": "claude", "em": ["inteligência", 8], "ate": ["essas", 8],
             "cores": ["#D97757", "#FFB38A"], "modo": "contorno", "tamanho": 0.70},   // cores/modo opcionais
            {"em": ["conversas", 6], "itens": [{"logo": "whatsapp", "em": ["conversas", 6]},
                                               {"logo": "notas", "em": ["anotações", 6]}]}],
  "icones": [{"em": ["proposta", 3], "ate": ["quando", 5], "gira": false,
              "itens": [{"simbolo": "doc", "em": ["proposta", 3], "cor": "#FF3EA5"}, ...]}],
  "titulos": [{"texto": "do zero", "em": ["zero", 5, -0.3], "ate": ["você", 6]}],
  "iphones": [{"arquivo": "../gravacao-tela.mov", "inicio": 5.8, "velocidade": 1.5, "recorte": [x, y, w, h],
               "em": ["mas", 2], "ate": ["criar", 3], "zoom": [0.62, 0.78],
               "toques": [{"caixa": [x, y, w, h], "em": ["briefing", 2]}],     // px da fonte
               "focos": [{"caixa": [x, y, w, h], "em": [...], "ate": [...]}],
               "rolagem": [[["organizado", 2], 0.4, 0.8]]}],                  // [quando, fração, duração]
  "linhas": [{"em": ["simples", 10], "cor": "#39FF14"}],
  "claroes": [0.0, ["quando", 5], ["mas", 7]],
  "cartao": {"em": ["clique", 12], "clique": ["saiba", 12], "arroba": "seuperfil",
             "botao": "Saiba mais", "botao_depois": "Saiba mais"},           // sem "arroba"/"foto": @ e foto do perfil
  "sfx": {"db": -24}, "musica": {"arquivo": "trilha.mp3", "db": -30}      // música opcional (com licença de uso)
}
```

## Regras do estilo (não mudar sem o usuário pedir)
- Logo SEMPRE o oficial (`logos.py`), virado contorno neon na cor da marca, atrás da cabeça, acendendo
  com piscadas. A pessoa fica inteira na frente.
- iPhone entra de baixo, cresce devagar e sai voando pra cima; fundo desfocado e escuro só enquanto ele está.
- Legenda condensada caixa alta, 1-2 palavras, mesmo lugar o vídeo todo (abaixo do queixo), por cima de tudo.
- Título: só contorno, miolo transparente. Um por seção, no máximo.
- Cor da legenda e do título: padrão = cor de destaque do perfil (padrão #FFC700). A referência usa
  amarelo-limão na legenda e verde-limão no título; trocar é escolha do usuário (`cor`, `cor_titulo`).
- Trilha: a referência tem batida contínua; padrão aqui sem música, só efeitos curtos (escolha do usuário).

## Armadilhas
- Base nova = `medir.py` e `mascaras.py` de novo.
- O `recorte` do iPhone é em px da fonte (4K na gravação de tela); `toques`/`focos` também.
- `toques`/`focos` são em px da gravação ORIGINAL: o motor desconta o `recorte` sozinho.
- Desenho no conteúdo da tela do iPhone é feito em RGB: em RGBA o ImageDraw substitui o pixel e o toque
  vira buraco preto (cuidado ao mexer no `compor.py`).
- Storyboard: o iPhone busca o quadro da gravação direto no tempo (o leitor do render é sequencial).
- Cartão de perfil sem foto no perfil cai na foto genérica do pack (`~/.claude/padroes-edicao/foto-perfil.png`).
