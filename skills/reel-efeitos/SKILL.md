---
name: reel-efeitos
description: >
  Biblioteca de 17 efeitos visuais para Reels, tirados da engenharia reversa do Reel
  "17 video effects claude can create" (@tenfoldmarc): órbita de cartões em 3D, parede
  de prints, mundo do app (cenário vira a interface do Claude com prompt digitando), saindo da
  moldura, zoom digital, celular com checklist, checklist no canto, mural de manchetes, zoom de
  passagem, gráfico subindo, recuo pra janela do Claude, fundo trocado, colagem de papel, rabisco
  vivo, vertigo, capa de revista e letra de vidro. Cada efeito é chamado pelo nome, com recorte da
  pessoa (Apple Vision) pra passar coisa atrás da cabeça e efeito sonoro próprio. Funciona em
  cima de qualquer vídeo vertical (aplicar.py) e dentro do /reel-glow (chave "efeitos" do mapa).
  Gatilhos: "/reel-efeitos", "põe o efeito órbita", "coloca o efeito X nesse vídeo", "usa os
  efeitos do tenfoldmarc", "aplica a capa de revista", "faz o catálogo de efeitos", "quais efeitos
  a gente tem". Para estilo completo de edição ver /reel-glow, /reel-telao, /reel-prova,
  /reel-numerado; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel Efeitos

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do
Instagram, cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado
pessoal. Se o arquivo não existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher
o arquivo. O código já lê sozinho: sem `"cor"` no `efeitos.json`, vale a `cor_destaque` do perfil;
o cartão de tweet do `manchetes` usa o nome e o @ do perfil quando o item não traz `nome`/`arroba`.

## ✂️ Corte das falas: sempre com sobreposição (padrão fixo, vale pra qualquer estilo)
Padrão do pack.
O estilo muda gráficos, legenda e efeitos. O corte das falas é sempre este:
- o **vídeo** da fala anterior sai **0,10 s antes** de a voz acabar;
- o **áudio** da fala anterior continua por baixo da tomada seguinte até 0,06 s depois da voz e some
  em 80 ms (as duas falas se sobrepõem ~0,16 s, somadas, sem baixar volume);
- a tomada seguinte entra **0,04 s antes** da própria voz (fade de 30 ms). Sem pausa vazia entre falas;
- fala contínua na fonte (tomadas que se tocam, troca de zoom sem pausa) junta exata, sem sobrepor.

Regra e código moram num lugar só: `~/.claude/padroes-edicao/corte-sobreposto.md` (o porquê de cada
número) e `~/.claude/padroes-edicao/corte_sobreposto.py`. Nunca mudar os números aqui nem
fazer outro corte: mudou o padrão, muda no módulo e vale pra todas as skills.
- Nesta skill: a skill não corta, aplica efeitos sobre um corte pronto, que já vem da skill de estilo com
  sobreposição. Se um dia for usada direto num vídeo cru com cortes, o corte sai do módulo, nunca de um ffmpeg à parte.
  Efeito ancorado em palavra: a última palavra de uma fala pode já estar sobre a imagem da tomada seguinte.

## 0. O que precisa estar instalado
- `PY=~/Developer/video-use/.venv/bin/python` (tem numpy, scipy, Pillow; o `python3` do sistema não serve).
- ffmpeg/ffprobe no PATH; `swiftc` (Xcode CLT): o binário do recorte `scripts/bin/mascara` é compilado
  sozinho do `mascara.swift` na 1ª execução (sem os dois, o `aplicar.py` usa o do /reel-glow).
- Fontes do sistema do Mac (Helvetica Neue, Didot, Georgia, Arial Black, Impact...) + Poppins Bold em `assets/fonts/`.
- `S=~/.claude/skills/reel-efeitos/scripts`

## 1. Os 17 efeitos

Coluna "recorte": precisa saber onde a pessoa está (algo passa atrás dela ou ela é movida).
Duração boa: 0,9 a 1,8 s. Todos têm efeito sonoro sintetizado; `"som": false` desliga.

| nome | rótulo | o que faz | recorte | parâmetros (todos opcionais) | usar quando a fala é... |
|---|---|---|---|---|---|
| `orbit` | órbita | cartões de Reels/prints girando em 3D em volta do corpo; os de trás passam atrás da pessoa | sim | `imagens` (pasta ou lista), `quantos` 6, `raio` 420, `inclina` 120, `vel` 1.4, `altura` 260, `largura` 200 | "olha o que eu já fiz", portfólio, volume de conteúdo |
| `parede` | parede de prints | a parede atrás da pessoa vai sendo coberta de prints, um a um | sim | `imagens`, `colunas` 4, `entra_em` 0.6, `ate` (y) | prova social, "recebi muitas mensagens", resultados |
| `ui` | mundo do app | a pessoa desce, o fundo vira a interface do Claude e o prompt se digita sozinho | sim | `texto`, `desce` 360 | "eu peço pro Claude...", qualquer comando falado |
| `moldura` | saindo da moldura | o vídeo encolhe pra um cartão e a cabeça escapa pela borda de cima | sim | `escala` 0.64, `corte` 40 (topo do cartão em relação aos olhos) | virada de assunto, "agora presta atenção" |
| `zoom` | zoom digital | punch-in rápido no rosto com tremidinha, volta no fim | não | `escala` 1.35, `tremor` 10, `volta` true | frase de impacto curta |
| `celular` | celular | iPhone escuro entra pela lateral com itens se marcando e botão Pronto | sim | `titulo`, `sub`, `itens`, `tempos`, `botao`, `lado` direita/esquerda, `x`, `y`, `giro`, `escala` 0.8, `atras` true | "do celular", app, automação que roda sozinha |
| `checklist` | checklist | cartão escuro no canto com barra de progresso e checks amarelos | não | `titulo`, `itens`, `tempos`, `lado`, `y` 230 | passo a passo, "são 3 coisas" |
| `manchetes` | mural de manchetes | notas de jornal, busca e tweet grudando atrás da cabeça | sim | `itens`: lista de `{tipo: nota/busca/tweet/tag, texto, destaque, fonte, largura}`, `posicoes` | notícia de IA, "todo mundo tá falando de" |
| `mergulho` | zoom de passagem | mergulha num ponto escuro até ficar preto e sai do preto | não | `alvo` [x, y] | transição entre blocos (pôr na emenda) |
| `grafico` | gráfico subindo | grade, linha branca e disparada amarela com brilho, passando atrás da cabeça | sim | `valor` ("+340%"), `y`, `pico` [x, y] | crescimento, número que subiu |
| `recuo` | recuo pra janela | o vídeo vira a prévia na janela do Claude, painel "Trabalhando em" e barra renderizando | não | `itens`, `tempos`, `titulo`, `escala` 0.58 | "a IA fez tudo isso sozinha", bastidor |
| `chroma` | fundo trocado | fundo escuro liso, a pessoa desce, cartão no alto com outro vídeo/imagem (ou o próprio quadro = antes) | sim | `midia` (imagem ou vídeo), `midia_ini`, `fundo` "#0E0F12", `desce` 300 | antes/depois, "olha esse outro vídeo" |
| `colagem` | colagem de papel | scrapbook: papel, giz, letras de bilhete; a pessoa vira adesivo com borda branca | sim | `titulo` ("RECORTE"), `escala` 0.82, `semente`, `y` | conteúdo leve, título de bloco |
| `rabisco` | rabisco vivo | contorno de giz tremendo em volta da pessoa + coração e brilhos desenhados | sim | `afasta` 270, `cor_coracao` | emoção, "eu amei", "isso mudou tudo" |
| `vertigo` | vertigo | dolly zoom: o fundo avança e a pessoa fica do mesmo tamanho | sim | `forca` 0.42 | revelação, tensão, "e aí eu percebi" |
| `capa` | capa de revista | título serifado gigante atrás da cabeça, moldura fina e chamada em itálico | sim | `titulo`, `fonte` (bodoni), `esq`, `dir`, `selo`, `chamada`, `y`, `y_chamada` | autoridade, "o caso", abertura de série |
| `vidro` | letra de vidro | palavra em 3D de vidro na parede atrás da cabeça, letra a letra, com reflexo | sim | `texto` ("CLAUDE"), `fonte`, `y` | nome de ferramenta, palavra-tema |

Parâmetros gerais de qualquer item: `ini`/`fim` (segundos), `rosto` [x, y] e `topo` (y da cabeça)
se a estimativa pelo recorte errar, `saida` (fusão de volta ao vídeo, padrão 0,15 s), `entrada`,
`rotulo` (texto do rótulo no modo catálogo), `rotulo_y`, `som`.
Itens de `checklist`, `celular` e `recuo` aceitam `tempos` (segundos desde o início do efeito) pra
cada check cair na palavra falada; sem isso eles se espalham por igual e não batem com a fala.
No `manchetes`, item `tweet` aceita `nome` e `arroba` (padrão: nome e @ do perfil).

Análise da referência (moldura de série, legenda, mockups, áudio): `referencia/analise-tenfoldmarc.md`.

## 2. Jeito A: em cima de qualquer vídeo (aplicar.py)
Serve pra vídeo cru, vídeo já editado por outra skill (sem legenda queimada no trecho, porque os
efeitos que trocam o fundo cobririam a legenda) ou pro catálogo.

1. Pasta do projeto com o vídeo; criar `efeitos.json` ao lado (modelo no cabeçalho do `aplicar.py`):
```json
{"video": "base.mov", "cor": "#F7E476", "efeitos": [
  {"nome": "ui", "ini": 3.2, "fim": 4.6, "texto": "Monta o roteiro desse vídeo"},
  {"nome": "capa", "ini": 9.0, "fim": 10.4, "titulo": "ROTEIRO", "chamada": "A IA leu tudo por mim"}]}
```
   Sem `"cor"`, vale a cor de destaque do perfil. Pasta do projeto e de trabalho com nome que não deixe
   dúvida de quem é (ex.: `~/Reels/meu-video/`, `reel-efeitos-teste/`; o `aplicar.py` usa `efeitos_work/`).
   Modo catálogo (igual à referência): `"rotulos": true`, `"serie": {"titulo": "...", "sub": "..."}`,
   `"saida_padrao": 0` e efeitos colados um no outro. `"ate": 20` renderiza só o começo.
2. Prévia em quadros (rápido, faz o recorte só desses quadros):
```bash
$PY $S/aplicar.py <projeto>/efeitos.json --so-quadros 3.5,4.3,9.4,10.2
```
   Olhar os JPGs em `<projeto>/efeitos_work/quadros/` em tamanho real. Conferir: cartões atrás da
   cabeça (não na frente), nada cortado na borda, rótulo fora do rosto.
2b. STORYBOARD pro usuário aprovar (obrigatório, antes do vídeo completo):
```bash
$PY $S/aplicar.py <projeto>/efeitos.json --storyboard     # ~5 s → <projeto>/storyboard.html
```
   Uma cena por efeito, com o quadro REAL do efeito montado, código (3A), tempo, parâmetros e avisos
   (efeitos sobrepostos, densidade acima de ~1 a cada 10 s); ~6 s pro catálogo de 17. Item com `"fala": "..."` mostra a frase
   na cena. Mandar com `SendUserFile` (`display: render`), esperar o "aprovado" do usuário; pedido por código →
   mudar o `efeitos.json` e gerar de novo. Gerador comum: `~/.claude/padroes-edicao/storyboard.py`.
   Pelo Jeito B (chave "efeitos" de outra skill), os efeitos entram no storyboard DAQUELA skill.
3. Vídeo completo (só com o storyboard aprovado) (~8 quadros/s; recorte das janelas antes, reaproveitado se nada mudou):
```bash
$PY $S/aplicar.py <projeto>/efeitos.json --saida nome.mp4
```
   Sai com o som original + efeitos sonoros, volume em -14 LUFS (`"normaliza": false` desliga).
   Referência de tempo: o catálogo dos 17 (19,6 s) renderiza em ~2,5 min e sai com -14,6 LUFS, pico -1,5.

## 3. Jeito B: dentro do /reel-glow
No `mapa.json` do glow, a chave `efeitos` (o compor e o mascaras do glow já leem):
```jsonc
"efeitos": [
  {"nome": "ui", "tomada": 3, "dur": 1.5, "texto": "Faz a proposta desse briefing"},   // começa na tomada
  {"nome": "manchetes", "tomada": 10, "palavra": "notícia", "dur": 1.8},              // começa 0,1 s antes da palavra
  {"nome": "vidro", "ini": 21.0, "fim": 22.4, "texto": "CLAUDE"}                       // segundos da saída
]
```
- Sem `dur` o efeito vai até o fim da tomada. Cor = a mesma do glow (amarelo glow, ou o derivado da
  cor de destaque do perfil).
- A chave é aditiva: sem `"efeitos"` no mapa, os quadros do glow saem idênticos byte a byte aos de antes.
- Depois de mexer: `mascaras.py` de novo (as janelas dos efeitos entram no recorte), depois `compor.py`.
- Não pôr zoom animado (`zooms`) na mesma tomada: o recorte é do quadro sem zoom.
- Só vale em tomada de fala (fora de tela preta e B-roll).
- A legenda do glow fica por cima do efeito, na altura de sempre (não acompanha a pessoa quando
  `ui` ou `chroma` descem ela). Conferir na prévia se não caiu no rosto.
- Pra achar os tempos: `words_out.json` do projeto tem cada palavra em segundos da saída; o efeito
  começa ~0,15 s antes da palavra e os `tempos` dos itens são (palavra − início do efeito).

Outras skills (/reel-telao, /reel-prova, /reel-autoridade, /reel-numerado) ainda não leem a chave.
Pra usar lá: renderizar a base sem legenda nesse trecho e rodar o Jeito A, ou portar as 4 linhas
do glow (procurar `FX_BANCO` no `compor.py` e no `mascaras.py` do glow).

## 4. Densidade e escolha (regra do estilo)
- **Biblioteca, não catálogo.** Num Reel de fala nunca usar os 17: os 17 seguidos ficam exagerados e
  confusos. Um efeito a cada ~10 s (ex.: 6 num vídeo de 65 s), cada um com 1,5 a 5 s, e pelo menos 3 s de vídeo limpo
  entre dois efeitos. Modo catálogo (`rotulos`/`serie`) só se o vídeo for SOBRE os efeitos.
- **O efeito nasce da frase.** Ler a transcrição e procurar a frase que pede uma imagem; o efeito
  tem que dizer a mesma coisa que a pessoa está falando (tabela, última coluna). Se nenhum efeito diz
  aquilo, não pôr efeito ali. Lista falada = `checklist`/`recuo`/`celular` com os itens DA FALA, e
  `tempos` batendo cada check na palavra.
  Exemplo de encaixe (65 s): capa "10 LIÇÕES" na abertura, recuo com "o processo / exemplos /
  visualizar" marcando na palavra, rabisco em "emoção", vertigo em "se destacar", checklist "atrair /
  confiança / vender" na palavra, gráfico em "mais sucesso no longo prazo".
- O plano (tempo, frase, efeito, por quê) vai pro usuário no storyboard (passo 2b) antes de renderizar.
- `ui`, `recuo`, `celular` e `checklist` são os que mais mostram a IA trabalhando.
- Efeito que precisa de imagens (`orbit`, `parede`) fica melhor com prints reais do usuário (quadros
  dos Reels dele, prints de resultado). Sem imagem, sai cartão colorido genérico: evitar.

## 5. Criar efeito novo
Função `fx_<nome>(c: Ctx) -> Image` em `efeitos.py` com o decorador `@efeito("nome", rotulo=...,
mascara=..., topo=..., rotulo_y=...)` e a lista de sons `@sons("nome")` devolvendo
`[(segundos, tipo, ganho)]` (tipos: whoosh, whoosh_curto, whoosh_longo, whoosh_sobe, pop, clique,
tecla, ding, vidro, impacto, papel, rabisco). No `Ctx`: `fr` quadro, `m` recorte (ou None), `u`
segundos desde o início, `d` duração, `p` parâmetros, `cache` (por item), `rosto`, `topo`, `cor`.
Helpers prontos: `caixa`, `texto`, `quebra`, `com_sombra`, `cola`, `brilho`, `transforma`,
`pessoa_na_frente`, `recorte`, `sem_pessoa`, `parcial`, `check`. Depois: entrar na tabela da seção 1
e rodar o catálogo de teste.

## Armadilhas
- Parâmetro de efeito com nome `rotulo` colide com o rótulo do catálogo: o do gráfico se chama `valor`.
- Sons de durações diferentes não se somam direto (numpy): usar `_mix`.
- Pasta de trabalho com nome genérico (`efeitos/`) já foi renomeada por outra sessão rodando ao mesmo
  tempo. Usar nome que não deixe dúvida de quem é.
- Capa: o Didot faz algarismo pequeno ("10" parecia "IO") e a cabeça cobria o meio do título. Padrão
  é Bodoni 72 Book (`fonte`), com o título subindo pra cabeça cobrir só a base das letras.
- Rótulo do catálogo em y 1300 cai no queixo (o rosto fica em ~y 1000 numa gravação típica). Padrão
  é y 1470 (peito); efeitos que movem a pessoa têm altura própria (`ui` 980, `chroma` 830).
- Efeitos que ocupam o alto da tela (`ui`, `checklist`, `chroma`, `colagem`, `capa`) escondem o
  título da série, como a referência faz do efeito 12 em diante.
- Recorte é por número de quadro: vídeo novo ou janela nova = recalcula (o `aplicar.py` faz sozinho
  pela chave em `efeitos_work/masks/chave.txt`).
