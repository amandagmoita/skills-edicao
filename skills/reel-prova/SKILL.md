---
name: reel-prova
description: >
  Edita um vídeo cru de cabeça falante no estilo "prova" (inspirado no Reel do @justyn.ai "I didn't
  edit a single second of this video. Claude did."): o vídeo PROVA o que a pessoa fala. Gancho com
  títulos animados sobre fundo chapado (a pessoa recortada na frente, letras passando atrás da cabeça,
  3 fontes alternando: Didot, Avenir Heavy, Didot itálico), ícone oficial do app aparecendo na palavra
  em que o app é citado (com risco e queda opcionais), caixas que abrem como persiana e digitam (comando
  "PARA O CLAUDE" → enviado → pronto ✓, conversa, comentário, link), prova do processo no alto da tela
  (gravação de tela num cartão, documentos gerados entrando um a um, relógio de virar) com a imagem da
  pessoa descendo pra abrir espaço, legenda karaokê serifada em caixa escura, borrão de movimento nas
  viradas e um efeito sonoro por evento. Usa o video-use pra transcrever.
  Gatilhos: "/reel-prova", "edita no estilo prova", "edita no estilo do Justyn", "estilo do Claude
  editou", "edita com os apps aparecendo", "edita com caixa de texto e prova do processo". Para estilo
  glow ver /reel-glow; autoridade ver /reel-autoridade; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel Prova

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (nome na
caixa de conversa, @ na resposta do comentário, produto e link no CTA). Se o arquivo não existir, pedir
ao usuário pra rodar o `instalar.sh` do pack ou preencher o arquivo.

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
- Nesta skill: o `cortar.py ... base` já corta assim (imprime "N emendas sobrepostas, som de A por
  baixo X-Y ms"). O `conferir.py` mede na linha 2: som da fala anterior por baixo entre 120 e 200 ms,
  sem estalo, juntas coladas iguais à fonte. `words_out.json` segue o SOM: a última palavra de uma fala
  aparece quando é ouvida, mesmo com a imagem já na tomada seguinte. `base_info.json` traz o `plano`.

## 0. Antes de começar
- Ler `estilo.md` (valores) e, se for a 1ª vez na sessão, `referencia/referencias-estilo.md`.
- Pasta do projeto = pasta do vídeo cru. Tudo que for gerado vai em `<pasta>/prova/` (o "edit").
  Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do arquivo antes de transcrever: nome com "edit" pode ser vídeo pronto.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reel-prova/scripts
E="<pasta>/prova"
```

## 1. Transcrever (custa crédito: só quando o usuário mandou o vídeo pra editar)
Se a pasta já tem transcrição do video-use (`edit/transcripts/<video>.json` de uma edição anterior),
copiar pra `$E/transcripts/` e não transcrever de novo.
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1   # grava em <pasta>/edit/transcripts
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
$PY $S/cortar.py "$E" frases
```
Escolher as **tomadas** como no /reel-glow (fica a tomada completa, fragmento e respiração saem; cada
tomada = `[início da 1ª palavra, fim da última, "BLOCO"]`). Vídeo de uma tomada só: tomada = oração.

## 2. Montar o mapa.json (o plano vai pra aprovação no storyboard, passo 3b)
O trabalho do Claude aqui é casar cada frase com uma prova visual. Perguntas por frase:
- A pessoa cita um app ou ferramenta? → `apps` (ícone na palavra). "Não precisa de X" → `risco`. "Espalhado,
  bagunçado, sumiu" → saída `cai`.
- A pessoa pede algo pra IA ou descreve um pedido? → `comando` (digita → enviado → pronto ✓).
- A pessoa fala de um resultado que existe (documento, site, planilha, vídeo)? → prova no palco: `video`
  com a gravação de tela, `imagem` com o print, ou `cartoes` com os documentos entrando um a um (✓ quando
  a pessoa diz que ficou pronto).
- A pessoa fala um tempo ou número de antes/depois? → `relogio` (só com número que ela FALOU).
- Frase-tese curta ("do zero", "nunca", "uma frase") → `titulos` gigante atrás da cabeça.
- Lista de qualidades no fim ("simples, rápido e organizado") → título com `faixa` (estilo "BIGGER captions.").
- CTA → `comentario` (palavra-chave) ou `link` (botão tocado).

Densidade que segue a referência (54 s): elemento novo a cada ~2 s, gancho com 3–5 títulos em ~3–4 s,
UM trecho limpo de ~3 s (normalmente a virada), borrão em 3–5 viradas de bloco.

| Elemento | Quando | Regra |
|---|---|---|
| `gancho.titulos` | 0–4 s | 3–5 títulos, um por pedaço de frase, alternando serifa → sans → itálico; última palavra em `destaque` |
| `apps` | ferramenta citada | ícone entra NA palavra; nome curto embaixo |
| `palco` | prova do que a pessoa fala | um por vez; elementos colados nascem um do outro |
| `titulos` | 1–3 por vídeo | frase-tese, atrás da cabeça; ou `faixa` na frente |
| `borrao` | viradas | índices das tomadas onde muda o bloco |

A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais (a lista de arquivos de prova sai
na mesma página). Não mandar tabela em texto antes. Gravação de tela do próprio usuário é prova melhor que imagem gerada.

Ícones: `$PY $S/icone_app.py "<nome do app>" <arquivo>` baixa da App Store BR pra `assets/icones/` (fica
pra sempre). Conferir o nome do app impresso. Já baixados: whatsapp, meet, drive, notas, claude, chatgpt.

Recorte de gravação de tela 4K (3840×2160): gravação de tela do Mac costuma ter faixas pretas (ex.: tela útil y≈152–2032).
Achar o pedaço com quadros em grade (`drawgrid`) e recortar só o documento/resultado (ex.: o artefato à
direita no Claude: `[1900, 160, 1420, 1000]`). Texto pequeno demais pro celular? recorte menor.

## 3. Cortar, recortar a pessoa, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~3–8 min em 4K HEVC (rodar em segundo plano)
$PY $S/mascaras.py "$E"             # recorte (Vision) do gancho e dos títulos atrás da cabeça
$PY $S/compor.py "$E" --so-quadros 0.4,1.0,1.8,2.7,3.6,9.0,16.5,20.5,23.5,32.5,37,44
```
Ler as prévias EM TAMANHO REAL (prévia lado a lado reduzida engana): título dentro da tela e passando
só pelo cabelo, texto legível, cartões sem cobrir o rosto, recorte da gravação mostrando o que importa.
Mudou tomada ou o tempo de um título "atras"? rodar `mascaras.py` de novo.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~5 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por frase (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(título do gancho, título atrás da cabeça ou com faixa, app citado, caixa de comando digitando e pronta,
prova no palco, a pessoa descendo pra abrir o palco, borrão), com código (4B), tempo, o que entra em português
e os avisos (ícone curto demais, "pronto ✓" curto, falta de máscara, buraco de ritmo, arquivo faltando).
Cena sem nada novo aparece com um quadro só ("só a pessoa + legenda").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~3 MB, imagens embutidas).
- Esperar "aprovado". Pedido por código ("4B: troca o título", "7: tira o app") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu no gancho ou num título atrás da pessoa, `--storyboard` de novo e reenviar.
  Só o storyboard aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos elementos).
- O `t0` de caixa/prova no storyboard é a palavra em que ela entra (a caixa abre 0,1–0,25 s antes e,
  contada desse começo, cairia na cena anterior). Prova com arquivo faltando não derruba o storyboard:
  sai da página e vira aviso.

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~2–4 min → preview_prova.mp4
$PY $S/conferir.py "$E" "$E/preview_prova.mp4"         # silêncios, emendas, loudness, folha de contato
```
`conferir.py` tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP.
Ler `verify/folha.jpg`. Mandar ao usuário o vídeo (e uma cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `mascaras.py --final`, `compor.py --final` (~4 min no total pra
um vídeo de 45 s; a prévia já mostra tudo, não precisa de ajuste entre uma e outra).
Tempos de referência: render da prévia de 45 s ~30 s (fora a base); prévia de 25 quadros ~3 s.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos de qualquer elemento: `[palavra, tomada]` ou `[palavra, tomada, atraso_s]` (palavra sem
pontuação, tem que existir NAQUELA tomada) ou segundos da saída. `ate` omitido = fim da tomada.
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.16, "GANCHO"], ...],
  "corte": {"zoom_alternado": true},               // opcional (igual reel-glow)
  "paleta": "cafe",                                // floresta | cafe | grafite | vinho | marinho | {"escuro","claro","destaque"}
  "layout": {"topo_cabeca": 260, "leg_y": 1180},   // MEDIR o topo do cabelo no quadro 1080x1920
  "gancho": {"ate": null, "fundo": true, "timecode": true, "titulos": [
     {"linhas": ["QUANTO", "TEMPO"], "fonte": "serifa", "anim": "letras", "em": ["quanto", 0]},
     {"linhas": ["UM DONO DE", "NEGÓCIO PERDE"], "fonte": "sans", "anim": "mascara", "em": ["dono", 0]},
     {"linhas": ["A MESMA", "INFORMAÇÃO"], "fonte": "sans", "anim": "rola", "em": ["mesma", 0]},
     {"linhas": ["várias vezes?"], "fonte": "italico", "anim": "seco", "em": ["várias", 0],
      "destaque": ["vezes?"], "destaque_em": ["vezes", 0]}]},
  "titulos": [{"linhas": ["DO ZERO"], "fonte": "serifa", "anim": "letras", "em": ["cada", 5]},
              {"linhas": ["SIMPLES,", "rápido e organizado."], "fonte": ["sans", "italico"], "faixa": true,
               "anim": "mascara", "em": ["simples", 10], "y": 330}],
  "apps": [{"icones": [{"arquivo": "whatsapp", "nome": "WhatsApp", "em": ["conversas", 6]}, ...],
            "risco": false, "sai": {"em": ["espalhadas", 6], "modo": "cai"}}],
  "palco": [
    {"tipo": "video", "arquivo": "../broll/gravacao-de-tela.mov", "inicio": 5.8, "velocidade": 2, "selo": "2x",
     "recorte": [1900, 160, 1420, 1000], "rotulo": "o *briefing* que a IA montou", "em": [...], "ate": [...]},
    {"tipo": "cartoes", "itens": [{"titulo": "Contrato", "sub": "DOCX", "em": [...], "ok_em": [...]}]},
    {"tipo": "comando", "texto": "Gera o briefing desta reunião", "em": [...], "feito": "Briefing pronto."},
    {"tipo": "conversa", "nome": "<nome do perfil>", "texto": "...", "resposta": "...", "em": [...]},
    {"tipo": "imagem", "arquivo": "print.png", "em": [...]},
    {"tipo": "relogio", "rotulo": "ANTES", "rotulo_final": "AGORA", "de": "3:00", "para": "0:45", "em": [...]},
    {"tipo": "comentario", "titulo": "Comenta BRIEFING que eu te mando", "texto": "BRIEFING",
     "resposta": "Te mandei no direct!", "em": [...]},
    {"tipo": "link", "titulo": "Meu Produto", "sub": "...", "monograma": "MP", "botao": "Saiba mais",
     "em": [...], "toque_em": [...]}],
  "borrao": [5, 7, 10],
  "legenda_cfg": {"tamanho": 52, "max_palavras": 4},  // "legenda": false desliga
  "musica": {"arquivo": "trilha.mp3", "db": -30}      // opcional; padrão é sem música
}
```
Opções por título: `anim` letras | mascara | rola | pop | seco; `fonte` serifa | sans | italico (ou
lista por linha); `atras` (padrão true sem faixa); `cor` auto | claro | escuro; `y` (base da última
linha); `tamanho`; `alinha` centro | esquerda; `saida` some | corte. No gancho, um `rola` faz o
título anterior subir e sair.
Palco: `y`, `largura`, `altura_max`, `espaco: false` (não desce a imagem), `nasce_do_anterior: false`.
Padrões que vêm do perfil: `conversa.nome` = nome do perfil; `comentario.perfil` = @ do perfil;
`link.titulo` = produto do perfil (o link do perfil vai na legenda do post).

## Armadilhas
- **Rosto alto no quadro.** Quem grava com a câmera mais baixa fica com o topo do cabelo bem alto (ex.:
  y≈260 de 1920, contra ≈630 na referência). Título na altura da referência some atrás da cabeça. Por
  isso o motor apoia a base da última linha no topo do cabelo (`topo_cabeca + 40`) e desce sozinho um
  bloco que passaria do alto da tela. MEDIR `layout.topo_cabeca` em todo vídeo novo.
- **Prova no alto sem cobrir o rosto.** Sempre que um elemento passa de `topo_cabeca - 40`, o motor DESCE
  a imagem da pessoa (0,3 s) e abre um palco na cor escura. Caixa de comando de 1 linha (150 px) cabe sem
  descer.
- **Cor automática do título.** Parede clara + teto escuro no mesmo título fazia a cor errar. A conta
  ignora a pessoa (máscara), só escurece o texto com fundo bem claro (média > 150), e todo título sobre o
  vídeo leva sombra suave.
- **Quadro 0 é a capa no feed.** O 1º título do gancho começa 0,25 s "antes" do vídeo, então a capa já
  tem letras. A Didot em tamanho gigante tem espaço entre palavras estreito: o motor alarga 14%.
- **"Pronto ✓" que some.** Caixa de comando que fecha cedo (`ate`) escondia o ✓ (ficava 0,25 s). A
  digitação acelera sozinha pra o ✓ ficar ~0,8 s; padrão 22 caracteres/s. Texto do comando curto
  (≤ 35 letras).
- **Elemento na última palavra da frase passa rápido demais.** Ícone que entra na última palavra some com
  a tomada (~0,4 s). Regra no motor: ícone de app fica NO MÍNIMO 2 s (`"minimo"` no grupo muda), mas sai
  antes da próxima prova do palco entrar. Pra qualquer elemento nessa posição, conferir a duração na
  tela, não só o momento de entrada.
- Todas as do /reel-glow sobre corte e áudio continuam valendo (o `cortar.py` e o `conferir.py` são os
  mesmos): escala fixa 1080×1920, áudio PCM por trecho, duração REAL de cada trecho.
- Fonte que não carrega cai em outra calada: o compor confere o nome de cada fonte no início e para.
- Máscara é por número de quadro da base: base nova = rodar `mascaras.py` de novo.
- Prévia `--so-quadros` lê UM quadro da gravação de tela por prévia; no vídeo final o leitor anda
  quadro a quadro. Se o recorte mostrar coisa errada no vídeo e não na prévia, conferir `inicio`.
