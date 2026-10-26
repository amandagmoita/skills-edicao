---
name: reel-telao
description: >
  Edita um vídeo cru de cabeça falante no estilo "telão" (mapeado de um Reel de 81 s sobre sistema de
  agentes de conteúdo): a parede acima da cabeça vira telão. Em cima da cabeça entram, por corte seco e
  sem borda, imagens geradas por IA que desenham a metáfora da frase, fotos de reação estilo meme,
  colagem de Reels rodando mudos (prova social) e prova pessoal; quando o assunto é processo ou sistema,
  a tela se divide e a metade de cima mostra a gravação de tela, um gráfico de passos que acendem ou uma
  constelação de nós que acende na palavra falada. Legenda uma palavra por vez, branca, que pula pra
  parede quando não tem nada em cima da cabeça; CTA no estilo de texto nativo do Instagram; troca de
  enquadramento a cada item. Usa o video-use pra transcrever e gpt-image pras imagens. Gatilhos:
  "/reel-telao", "edita no estilo telão", "edita com imagem em cima da cabeça", "edita com meme em cima da
  cabeça", "edita com tela dividida", "estilo b-roll em cima da cabeça". Para estilo glow ver /reel-glow;
  prova ver /reel-prova; autoridade ver /reel-autoridade; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel Telão

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (a cor de
destaque do passo em evidência vem dele; prova pessoal = o perfil do usuário). Se o arquivo não existir,
pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher o arquivo.

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
- Ler `referencia/referencias-estilo.md` se for a 1ª vez na sessão (o porquê de cada regra).
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`, com o vídeo ligado por `ln`).
  Tudo que for gerado vai em `<pasta>/telao/`. Nunca escrever dentro da skill nem do video-use.
- Olhar uma folha de quadros do arquivo antes de transcrever: nome com "edit" pode ser vídeo pronto.
  Conferir também se sobra parede acima da cabeça (o estilo depende disso): o ideal é o topo do cabelo
  em y≈700-745 de 1920 (~37% de parede livre). Cabeça mais alta que y≈550: o telão encolhe sozinho
  (limite `topo_min`); abaixo de y≈450 não cabe, avisar o usuário.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reel-telao/scripts
E="<pasta>/telao"
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
uma tomada por item/ideia. Cada tomada troca de enquadramento (zoom alternado), igual à referência.

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
O trabalho do Claude aqui é casar cada frase com UM elemento. Perguntas por frase:
- A frase tem uma metáfora ou imagem mental ("peças que se encaixam", "emoção x razão")? →
  `telao` `imagem` com imagem `ilustrativa` gerada. Metáfora em dois passos = duas imagens seguidas
  (problema → solução), troca seca entre elas.
- A frase tem uma emoção forte (desespero, confusão, tédio, choque, "pensa comigo")? → `telao` `imagem`
  com foto de `reacao`. Meme de verdade que o usuário tiver (arquivo em `assets/`) vale mais que reação gerada.
- Gancho com "todo mundo fala de X" / "coisas que aprendi"? → `colagem` de 3 Reels rodando mudos (do
  usuário ou de outros criadores sobre o tema).
- Prova de que a pessoa faz (perfil, vendas, time, números)? → `telao` `video`/`imagem` com print ou gravação.
- Processo, sistema, "como funciona por dentro"? → `dividida`: `video` (gravação de tela do usuário, a
  melhor prova: a tela da IA gerando o resultado; texto legível no celular com recorte de ~1450 px de
  largura da tela 4K), `passos` (sequência linear acendendo) ou `nos` (partes de um sistema acendendo no
  nome falado).
- Frase emocional, virada, fecho humano → LIMPO (sem elemento). O fim fica limpo, só com CTA.

Densidade da referência: ~2/3 do vídeo com elemento (o `compor.py` imprime a %), troca a cada ~5 s,
elemento entre ~1,5 e 3 s (dividida pode durar 5-20 s), trecho limpo mais longo no fim.

A aprovação do plano é no STORYBOARD (passo 3b), com os quadros reais. Não mandar tabela em texto antes.
As imagens precisam existir pra aparecer no storyboard (elemento sem arquivo fica fora e a página marca
FALTA). Gerar imagens custa ~US$0,05 cada; imagem reprovada no storyboard é refeita e o storyboard, gerado de novo:
```bash
$PY $S/gerar_imagens.py "$E"            # tudo de mapa["imagens"] que ainda não existe em assets/
```
Ler a folha das imagens antes de usar (imagem com texto, dedo a mais ou rosto estranho: refazer).

## 3. Cortar, medir, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K HEVC (rodar em segundo plano)
$PY $S/medir.py "$E"                # topo da cabeça e rosto por tomada (Vision) → medidas.json
$PY $S/compor.py "$E" --so-quadros 0.5,3,5.5,8,10,12.5,16.5,22.5,28,33,42.5,49,55,64
```
`compor.py` imprime a linha do tempo e os ATENÇÃO (elemento curto demais, item que acende tarde).
Ler as prévias em tamanho real: telão encostando no cabelo sem cobrir a testa, legenda fora do rosto,
recorte da gravação de tela legível, nada embaixo de 78% da altura.
Base mudou → rodar `medir.py` de novo.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~5 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por tomada (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(imagem/reação/vídeo no telão, colagem, tela dividida, cada passo ou nó que acende, CTA), com código (4B),
tempo, o que entra em português, os ATENÇÃO (elemento curto, item que acende tarde) e a % do vídeo com
elemento. Cena sem nada novo aparece com um quadro só ("só a pessoa + legenda").
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~2-3 MB, imagens embutidas).
- Esperar "aprovado". Pedido por código ("4B: troca a imagem", "7: tira o telão") → mudar o `mapa.json`
  (e `gerar_imagens.py` se for imagem nova), `--storyboard` de novo e reenviar. Só o storyboard aprovado
  vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos momentos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                  # ~1-2 min → preview_telao.mp4
$PY $S/conferir.py "$E" "$E/preview_telao.mp4"         # silêncios, emendas, loudness, folha de contato
```
`conferir.py` tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP.
Ler `verify/folha.jpg`. Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `medir.py --final`, `compor.py --final` (poucos minutos; a
prévia já mostra tudo, não precisa de ajuste entre uma e outra). Entregar também uma cópia 720p pro celular.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: `[palavra, tomada]` (entra `antecipa` = 0,15 s antes da palavra, como na referência),
`[palavra, tomada, atraso]` (atraso explícito) ou segundos da saída. `ate` omitido = fim da tomada do `em`.
Palavra sem pontuação, tem que existir NAQUELA tomada (a 1ª ocorrência vale).
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.10, 4.14, "GANCHO"], [4.24, 8.66, "1"], ...],
  "imagens": [                                            // geradas por gerar_imagens.py → assets/<nome>.png
    {"nome": "razao", "estilo": "ilustrativa", "fundo": "deep teal", "descricao": "a golden balance scale ..."},
    {"nome": "ninguem", "estilo": "reacao", "descricao": "a bored man slumped on an office chair, yawning ..."}],
  "telao": [                                              // um por vez, em cima da cabeça
    {"tipo": "colagem", "em": 0, "ate": ["pra", 0, -0.1], "itens": [
       {"arquivo": "../outro-reel/final.mp4", "inicio": 1.0}, ...]},
    {"tipo": "imagem", "arquivo": "emocao", "em": ["compram", 5], "ate": ["razão", 5]},
    {"tipo": "video", "arquivo": "../x.mov", "inicio": 3, "recorte": [x, y, w, h], "em": [...], "ate": [...]}],
  "dividida": [                                           // um por vez; enquanto ativa, o telão some
    {"tipo": "video", "arquivo": "../broll/gravacao-de-tela.mov", "inicio": 5.8, "velocidade": 2,
     "recorte": [1860, 300, 1450, 1160], "em": ["mostrar", 2]},
    {"tipo": "passos", "divisao": 0.4, "em": ["gancho", 6], "itens": [
       {"rotulo": "gancho", "em": ["gancho", 6]}, {"rotulo": "meio", "em": ["meio", 6], "destaque": true},
       {"rotulo": "final"}]},                             // sem "em" = fica apagado
    {"tipo": "nos", "em": ["conteúdo", 8], "ate": ["ninguém", 9], "centro": "conteúdo", "itens": [
       {"rotulo": "atrair", "cor": "#7C9CFF", "em": ["atrair", 8]}, ...]},
    {"tipo": "imagem", "arquivo": "x", "em": [...]}],     // imagem cobrindo o painel de cima
  "cta": {"texto": "salva pra rever depois", "em": ["realizado", 10]},
  "layout": {"divisao": 0.45, "leg_tam": 86, "sobra": 14},   // opcional, ver LAY no compor.py
  "destaque": "#RRGGBB", "fundo_dividida": "#060710",        // opcional; sem "destaque" = cor do perfil
  "musica": {"arquivo": "trilha.mp3", "db": -30},            // opcional; a referência tem música baixa
  "sfx": false                                               // opcional; true = pop discreto em cada entrada
}
```
Opções do telão: `largura` (fração da tela), `recorte`, `inicio`, `velocidade`. Colagem: `largura_item`.
Dividida: `divisao`, `angulos` (nos), `recorte`/`inicio`/`velocidade` (video).

## Regras do estilo (não mudar sem o usuário pedir)
- Tudo entra e sai por corte seco. Sem fade, zoom, deslize, borda, sombra ou canto arredondado.
- Telão: base encosta no topo do cabelo, centralizado, ~62% da largura, proporção original.
- Legenda: uma palavra por vez, Avenir Next Demi Bold branca com sombra suave, sem pontuação, minúscula
  no começo de frase. Com telão: no peito. Sem nada: na parede, acima da cabeça. Dividida: abaixo do queixo.
- CTA: caixa branca de cantos arredondados, texto preto em negrito; a legenda sobe pra parede.
- Tela dividida: padrão 0,45 (painel de cima). 50/50 joga o rosto pra baixo demais e a legenda cairia em
  ~86% da altura, embaixo da interface do Instagram. Gráfico simples pode usar 0,40.
- Fotos de reação geradas funcionam no lugar de memes reais; meme real é opcional, por vídeo.
- Música: a referência tem trilha baixa (~10-15 dB abaixo da voz). Só usar trilha com licença que o
  usuário tenha; sem trilha, sai só voz (decisão do usuário por vídeo). Sem trilha o estilo funciona bem.

## Armadilhas
- Item que acende na ÚLTIMA palavra da tomada fica ~0,25 s na tela. O `compor.py` avisa na linha do tempo;
  a solução é acender numa palavra anterior da mesma frase e estender o `ate` até a 1ª palavra da tomada
  seguinte.
- As do /reel-glow sobre corte e áudio continuam valendo (`cortar.py` e `conferir.py` são os mesmos).
- Base nova = `medir.py` de novo (o compor para se o número de tomadas não bater).
- Prévia `--so-quadros` lê UM quadro de cada vídeo por prévia; no vídeo final o leitor anda quadro a quadro.
- Imagem gerada com texto embutido ou mão deformada passa despercebida na folha pequena: abrir cada uma.
