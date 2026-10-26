---
name: reel-numerado
description: >
  Edita um vídeo cru de cabeça falante no estilo "numerado" (mapeado do Reel "7 video effects" do
  @tenfoldmarc): selo branco fixo no topo com o item da lista ("#3 Marketing é educação"), um efeito por
  item que acontece NA palavra que combina com ele (prévia numerada dos itens no gancho, parede de
  manchetes atrás da cabeça, órbita de Reels em 3D, zoom em degraus com puxão de volta, holofote que
  apaga a sala, congelar e rotular com linha, antes e depois com barra deslizante, checklist que se
  preenche), legenda minúscula numa linha com palavra-chave sozinha maior e amarela, CTA de comentário
  animado e um whoosh grave repetido em tudo que se move. Feito pra vídeo em LISTA ("10 coisas que
  aprendi", "5 erros", "7 ferramentas"). Usa o video-use pra transcrever. Gatilhos: "/reel-numerado",
  "edita no estilo numerado", "edita no estilo dos 7 efeitos", "edita com selo no topo", "edita esse
  vídeo de lista". Biblioteca solta de efeitos (catálogo de 17) é a /reel-efeitos; glow ver /reel-glow;
  telão ver /reel-telao; prova ver /reel-prova; referência NOVA = analisar do zero. Idioma: PT-BR.
---

# Reel Numerado

## 🔄 Auto-aperfeiçoamento (ler primeiro)
Esta skill evolui. Sempre que surgir um aprendizado novo durante o uso
(um formato que performou, uma preferência do usuário, um erro a não repetir,
um ajuste de tom/estratégia), ATUALIZE este arquivo imediatamente para
incorporá-lo. A cada execução, comece revisando esta seção.

### Aprendizados acumulados
- (registrar aqui novos aprendizados, com data)

**Perfil do criador:** antes de tudo, ler `~/.claude/padroes-edicao/perfil.json` (nome, @ do Instagram,
cor de destaque, foto, produto, link) e usar esses dados no lugar de qualquer dado pessoal (palavra do
CTA, texto do botão de link = produto/link do perfil). O amarelo da legenda é parte do estilo (medido na
referência); só troca pela cor do perfil se o usuário pedir (`"destaque"` no mapa). Se o arquivo não
existir, pedir ao usuário pra rodar o `instalar.sh` do pack ou preencher o arquivo.

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
- Pasta do projeto = pasta do vídeo cru (ex.: `~/Reels/meu-video/`). Tudo que for gerado vai em
  `<pasta>/numerado/`. Nunca escrever dentro da skill nem do video-use. Não usar `efeitos/` como nome
  da pasta de projeto (colide com a /reel-efeitos, que é outra skill).
- Olhar uma folha de quadros do arquivo antes de transcrever: nome com "edit" pode ser vídeo pronto.
- O estilo pede vídeo em lista (cada item vira um selo). Vídeo sem itens: avisar o usuário antes.
```bash
PY=~/Developer/video-use/.venv/bin/python
S=~/.claude/skills/reel-numerado/scripts
E="<pasta>/numerado"
```

## 1. Transcrever e escolher as tomadas
Transcrição custa crédito: só quando o usuário mandou o vídeo pra editar. Reaproveitar se já existir
(`<pasta>/edit/transcripts/` ou a pasta de outra skill).
```bash
$PY ~/Developer/video-use/helpers/transcribe.py "<pasta>/<video>" --num-speakers 1
mkdir -p "$E/transcripts" && cp "<pasta>/edit/transcripts/<video>.json" "$E/transcripts/"
$PY $S/cortar.py "$E" frases
```
Uma tomada por item da lista, mais o gancho (tomada 0). O `cortar.py` alterna o enquadramento (zoom de
corte) entre tomadas, igual à referência, que troca de tomada a cada efeito.

## 2. Montar o mapa e MOSTRAR o plano antes de renderizar
O trabalho do Claude é casar cada item com UM efeito e achar a palavra em que ele acontece. A regra
que mais vale: o efeito bate na palavra que o descreve. Guia por tipo de frase:
- Gancho com número ("10 coisas", "5 erros") → `previa`: miniaturas numeradas dos itens (quadros do
  próprio vídeo) em arco acima da cabeça; `destaque_em` na palavra que promete o melhor ("a última").
- "Todo mundo fala de X", "informação em todo lugar", tendência → `parede` de manchetes atrás da cabeça.
- "Mostrar", "exemplos", resultado do usuário → `orbita` com Reels prontos do usuário girando.
- Frase de impacto curta que precisa bater ("é escutar", "ninguém liga") → `holofote` na palavra.
- Duas ideias pra apontar no corpo da pessoa (emoção x razão, "eu não sabia editar") → `congela` com 1-2 rótulos.
- Frase em degraus ("gancho... curiosidade... parar de rolar") → `zoom` com um degrau por palavra e
  `volta` na virada ("O meio").
- Comparação ruim x bom, "se destacar", transformação → `antes_depois` com `palavra` atrás da cabeça.
- Passos ou tipos enumerados ("alguns servem pra X, outros Y, outros Z") → `checklist`.
- Item sem encaixe bom → só o selo (limpo). A referência tem um respiro limpo antes do CTA.

Cada efeito no máximo uma vez, se der. A aprovação do plano é no STORYBOARD (passo 3b), com os quadros
reais. Não mandar tabela em texto antes. A palavra do CTA e o que vai no link são decisão do usuário
(padrão: o produto do perfil); se o vídeo não tem CTA falado, perguntar se quer o CTA animado mesmo assim.

## 3. Cortar, recortar, prévias
```bash
$PY $S/cortar.py "$E" edl
$PY $S/cortar.py "$E" base          # ~2-5 min em 4K (rodar em segundo plano)
$PY $S/compor.py "$E" --linha       # linha do tempo + ATENÇÃO (efeito colado no corte, checklist tarde)
$PY $S/mascaras.py "$E"             # recorte da pessoa só onde precisa (~2-4 min)
$PY $S/compor.py "$E" --so-quadros 1.0,3.0,5.6,13.5,22.5,28.9,33.0,45.5,53.7,64.6
```
Ler as prévias em tamanho real: selo sem cobrir o cabelo, legenda fora do rosto, cartões atrás da
cabeça (não na frente), rótulos sem cobrir o rosto, checklist sem encostar no cabelo, CTA legível.
Base mudou → `mascaras.py` de novo.

## 3b. STORYBOARD pro usuário aprovar (obrigatório, antes de qualquer render)
```bash
$PY $S/compor.py "$E" --storyboard     # ~20-30 s → "$E/storyboard.html" + storyboard.json
```
Uma página com uma cena por tomada (a fala entre aspas) e, em cada cena, o QUADRO REAL de cada momento
(selo do topo, efeito do item, degrau de zoom, rótulo, item do checklist, legenda grande amarela, CTA),
com código (4B), tempo, o que entra em português e os ATENÇÃO do `--linha` no próprio momento.
- Rodar depois do `mascaras.py`: sem recorte, o que fica atrás da pessoa sai na frente (a página avisa).
- Mandar com `SendUserFile` (`display: render`): abre no app e no celular (~5 MB, imagens embutidas).
- Esperar "aprovado". Pedido por código ("4B: troca o efeito", "7: tira o zoom") → mudar o `mapa.json`,
  `mascaras.py` de novo se mexeu em algo atrás da pessoa, `--storyboard` de novo e reenviar. Só o storyboard
  aprovado vai pro passo 4.
- Gerador comum a todas as skills de Reels: `~/.claude/padroes-edicao/storyboard.py` (layout, códigos,
  linha do tempo). A parte desta skill é a função `storyboard()` do `compor.py` (nomes dos momentos).

## 4. Renderizar e conferir (só com o storyboard aprovado)
```bash
$PY $S/compor.py "$E"                                    # ~3-6 min → preview_numerado.mp4
$PY $S/conferir.py "$E" "$E/preview_numerado.mp4"        # silêncios, emendas, loudness, folha
```
`conferir.py` tem que dar: maior silêncio ≈ 0,25 s, emendas < -40 dB, -14 LUFS, pico < -1 dBTP.
Ler `verify/folha.jpg`. Mandar ao usuário o vídeo (e cópia 720p se passar de ~25 MB).
Aprovado → `cortar.py base --final`, `mascaras.py --final`, `compor.py --final`.

## 5. mapa.json (modelo real completo: `referencia/mapa-exemplo.json`)
Tempos: segundos da saída, `[palavra, tomada]` ou `[palavra, tomada, atraso]`. Palavra sem pontuação;
várias palavras valem ("ponto de vista"); `"outros#2"` = 2ª ocorrência na tomada. `ate` omitido = fim da tomada.
```jsonc
{
  "fonte": "meu-video.mov",
  "tomadas": [[0.1, 4.14, "GANCHO"], [4.24, 8.66, "1"], ...],
  "selos": {"1": "#1 Ponto de vista", "2": "#2 Mostre o processo", ...},   // tomada → texto do selo
  "chave": [["dez coisas", 0, "grande"], ["informação", 1], ...],          // amarelo; "grande" = bloco sozinho maior
  "efeitos": [
    {"tipo": "previa", "em": 0.15, "n": 10, "destaque_em": ["última", 0]},
    {"tipo": "parede", "em": ["informação", 1, -0.1], "ate": ["O", 1], "cartoes": [
       {"estilo": "manchete" | "reel" | "post", "texto": "O FUNIL PERFEITO EM 2026"}, ...]},   // até 6
    {"tipo": "orbita", "em": ["exemplos", 2], "videos": [{"arquivo": "../reel-anterior/final.mp4",
       "inicio": 2.0}, ...], "volta_s": 4.0, "raio": 400, "altura": 470},
    {"tipo": "holofote", "em": ["escutar", 4], "ate": ["cliente", 4, 0.25]},   // sem ate = escuro até o corte
    {"tipo": "congela", "em": ["compram", 5], "ate": ["pra", 5], "rotulos": [
       {"texto": "emoção", "em": ["emoção", 5], "alvo": "peito" | "cabeca"}]},
    {"tipo": "zoom", "passos": [[["gancho", 6], 1.15, "suave"], [["curiosidade", 6], 1.32, "seco"], [["parar", 6], 1.5, "seco"]],
       "volta": ["meio", 6, -0.2]},
    {"tipo": "antes_depois", "em": ["mas", 7], "barra": ["destacar", 7], "palavra": "destaque", "segura": 1.5},
    {"tipo": "checklist", "em": ["função", 8], "titulo": "Função de cada conteúdo", "itens": [
       {"texto": "Atrair gente nova", "destaque": "Atrair", "em": ["atrair", 8], "ok": ["nova", 8]}, ...]}
  ],
  "cta": {"em": ["clientes", 10], "palavra": "LISTA", "resposta": "Te mandei o link", "link": "10 lições de marketing"},   // link = texto do botão
  "destaque": "#F0E478",                                   // opcional (amarelo medido na referência)
  "legenda_cfg": {"tamanho": 64, "tamanho_grande": 88, "y": 1390, "y_cta": 560},   // opcional
  "sfx": false                                            // opcional: sem efeitos sonoros
}
```

## Regras do estilo (medidas na referência; não mudar sem o usuário pedir)
- Selo: pílula branca, texto preto SF Pro Bold, centralizada, de y=234 a 317 (12% da altura). Entra com
  fade de 0,25 s a cada corte. Some no gancho (a prévia ocupa o lugar) e no CTA.
- Legenda: minúscula, sem pontuação, uma linha centralizada, SF Pro Bold branca com
  sombra difusa, 1 a 4 palavras por bloco, cada palavra entra desfocada e firma em ~0,1 s. Palavra-chave
  amarela #F0E478; bloco que é só palavra-chave sai sozinho e ~1,4x maior. No CTA sobe pra parede.
  Altura: a referência usa y≈1167 (61%), mas quem é enquadrado mais baixo fica com a boca ali; padrão
  do motor y=1390 (72%), logo abaixo do queixo. Pílulas do antes e depois vão em LEG_Y+100.
- Efeito começa na palavra, nunca no corte. Troca de efeito = corte seco pra tomada nova.
- Zoom: a referência chega a 2,4x num plano aberto; num enquadramento já fechado 2x corta a cabeça.
  Degraus bons pra plano fechado: 1,15 suave → 1,32 seco → 1,5 seco.
- Rótulo "peito" do congela: ponto no ombro (cx-200, topo+700), senão o ponto cai na legenda.
- Som: sem música. Um whoosh grave curto (~0,2 s) em tudo que se move, pancada na parede, clique agudo
  nos tiques, acorde no checklist completo, teclas e "ding" no CTA. O holofote apaga em silêncio.
- CTA: degradê escuro sobe, caixa de comentário escura, palavra digitada, comentário postado com
  coração, resposta com o rosto da pessoa (recortado do próprio vídeo) e botão amarelo com o link. CTA
  centrado em y≈1330 (peito): na altura da referência o comentário cai no rosto. Termina com o link na
  tela (≥ 0,9 s).

## Armadilhas
- Borrão do zoom com poucas amostras (5) vira cópias do rosto no puxão de volta. O motor usa uma amostra
  a cada 0,005 de escala (até 48) + desfoque 2,2. Não reduzir.
- ImageDraw em RGBA TROCA o alfa em vez de misturar: elemento translúcido dentro de cartão vai numa
  camada própria com `alpha_composite` (senão vira buraco branco depois do arredondamento).
- As do /reel-glow sobre corte e áudio continuam valendo (`cortar.py` e `conferir.py` são os mesmos).
- Quadro congelado, prévia e CTA leem quadros fora de ordem (ffmpeg com -ss): ok no preview, mais lento.
- A prévia monta as miniaturas compondo o quadro de cada item: rodar `mascaras.py` antes, senão as
  miniaturas de parede/órbita/antes e depois saem sem recorte (cartões na frente da cabeça).
- `cabeca()` mede o topo do cabelo e o centro da cabeça no recorte; sem recorte usa (540, 720) e avisa.
