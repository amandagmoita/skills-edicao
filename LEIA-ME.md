# Pack de edição de Reels pro Claude Code

São 14 skills que editam vídeo de cabeça falante, cada uma num estilo. Você grava o vídeo cru e pede pro Claude editar. Ele transcreve, escolhe as melhores tomadas, corta as pausas, monta legendas e efeitos e te mostra um storyboard com os quadros de verdade. Só depois do seu "aprovado" ele renderiza.

## O que você precisa

- Um Mac. As skills usam o Apple Vision pra recortar você do fundo, e isso só existe no macOS.
- O Claude Code instalado e funcionando.
- Uma chave de API do ElevenLabs, que faz a transcrição palavra por palavra. É paga por minuto de áudio, então o Claude só transcreve cada vídeo uma vez.
- Opcional: uma chave da OpenAI, pra gerar imagens e objetos 3D quando você não tem material próprio (uns 5 centavos de dólar por imagem).
- Opcional: Node.js, só se for usar a reel-editor.

## Como instalar

Abra o Terminal nesta pasta e rode:

```bash
bash instalar.sh
```

O instalador confere o que falta no computador (ffmpeg, ferramentas do Xcode) e instala o video-use em `~/Developer/video-use`, que é a base de transcrição e corte. Depois ele pede as chaves e copia as skills pra `~/.claude/skills/`. Por último pergunta os dados que aparecem nos seus vídeos: nome, @ do Instagram, cor de destaque, foto de perfil, produto e link do CTA.

Se você já tinha alguma skill com o mesmo nome, ela vai pra uma pasta de backup em `~/.claude/skills-backup-<data>/`. Nada é apagado.

Pode rodar o instalador de novo quando sair uma versão nova do pack. Seu perfil e suas chaves ficam como estão.

## Como usar

1. Crie uma pasta pro vídeo, por exemplo `~/Reels/meu-video/`, e coloque o vídeo cru lá dentro.
2. Abra o Claude Code nessa pasta e peça a edição: "edita o video.mov no estilo glow" ou "/reels-kelsey edita esse vídeo".
3. O Claude transcreve, mostra as frases e escolhe as tomadas. Quando você repete uma frase, fica a última versão.
4. Ele corta e te manda o storyboard: uma página com uma cena por frase e o quadro real de cada coisa que entra na tela. Cada momento tem um código.
5. Responda "aprovado" ou peça mudança pelo código: "4B: troca o título por Tempo perdido", "7: tira o número", "2A: entra mais cedo".
6. Com o storyboard aprovado, ele renderiza uma prévia. Gostou, ele gera a versão final em qualidade máxima.

As imagens que você quiser usar (prints, fotos, gravações de tela) vão em `<pasta do vídeo>/<estilo>/assets/`. Se faltar alguma, o storyboard avisa.

## As skills

- reel-glow: legenda branca no peito com a palavra-chave brilhando na cor de destaque, telas pretas com gráficos que reagem à fala, B-roll das suas gravações de tela.
- reels-kelsey: cara de capa de revista. Título grande em serifa colado em você (desvia do rosto), números em neon, pílulas e prints em 3D.
- reels-nick: tela dividida que desenha o que você fala, com logos oficiais e janela com a página real.
- skill-remy: um quadro branco de interface no topo que vai se montando enquanto você fala.
- reels-jessi: cada benefício que você cita vira um objeto fazendo a ação, como pasta do Finder com cursor arrastando arquivos ou timeline de editor se enchendo.
- skill-iphone: o logo da plataforma que você cita acende em neon atrás da sua cabeça, e a demonstração aparece dentro de um iPhone 3D.
- reel-garrafal: o tipo de letra muda conforme o tipo de palavra, com abertura de cortes muito rápidos.
- reel-papel: tíquete numerado como fio da história e objetos de edição em papel.
- reel-prova: títulos em fundo chapado, o app citado aparecendo e a prova do processo em cima de você.
- reel-telao: imagens e reações em cima da sua cabeça por corte seco, e tela dividida com gravação de tela.
- reel-numerado: pra vídeo de lista. Selo "#1, #2..." no topo, um efeito por item e CTA de comentário.
- reel-autoridade: legenda curta com palavra-chave colorida, número gigante atrás da cabeça, títulos em Didot e zoom nas emendas.
- reel-efeitos: biblioteca de 17 efeitos chamados pelo nome (órbita, parede de prints, capa de revista, letra de vidro). Dá pra usar sozinha ou dentro da reel-glow.
- reel-editor: você manda um Reel de referência e ele copia a estrutura daquele vídeo. Usa HyperFrames pros gráficos.

## Duas regras que valem em todas

O corte das falas é sempre com sobreposição. O vídeo da frase anterior sai 0,10 s antes de você terminar de falar e o áudio dela continua uns 0,16 s por baixo da próxima tomada. Não sobra respiro vazio entre as frases e a emenda não aparece. O código fica num lugar só, `~/.claude/padroes-edicao/corte_sobreposto.py`.

O storyboard vem antes de qualquer render. Renderizar leva minutos, gerar o storyboard leva segundos, então você ajusta tudo antes de esperar.

## Seu perfil

Fica em `~/.claude/padroes-edicao/perfil.json`. Dá pra editar à mão ou pedir pro Claude: "muda a cor de destaque das minhas skills de Reels pra #FF2D8A". Os campos são `nome`, `instagram` (sem o @), `cor_destaque`, `foto`, `produto` e `link`.

## As skills aprendem com você

Cada skill tem no topo um bloco "Aprendizados acumulados". Quando você corrige alguma coisa ("prefiro sem música", "a legenda está alta demais"), o Claude registra ali e a próxima edição já sai do seu jeito.

## Quando der problema

- "não achei o arquivo X": a imagem tem que estar em `assets/` dentro da pasta do estilo, ou na pasta do vídeo.
- Na primeira vez, o recorte demora um pouco mais, porque o programa de recorte é compilado no seu Mac. Depois fica rápido.
- O macOS pode pedir permissão pro Terminal acessar a pasta de vídeos. É só aceitar.
- A reel-autoridade transcreve com o whisper no próprio computador, sem ElevenLabs. Na primeira vez, monte o whisper e baixe o modelo (uns 3 GB), uma vez só:

```bash
npx --yes hyperframes transcribe um-video-curto.mp4 --engine whisper
```

```bash
curl -L -o ~/.cache/hyperframes/whisper/models/ggml-large-v3.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin
```

Os estilos foram criados a partir da análise de Reels de outros criadores, citados nos arquivos `referencia/` de cada skill. A fonte Poppins incluída é livre (SIL Open Font License).
