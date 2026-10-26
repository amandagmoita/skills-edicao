#!/usr/bin/env bash
# Instalador do pack de skills de edição de Reels pro Claude Code (macOS).
# Uso: bash instalar.sh
# Variáveis opcionais: SEM_PERGUNTAS=1 (não pergunta nada; útil pra reinstalar), DESTINO_HOME=/outro/home (teste).
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
H="${DESTINO_HOME:-$HOME}"
SKILLS="$H/.claude/skills"
PADROES="$H/.claude/padroes-edicao"
VIDEO_USE="$H/Developer/video-use"
SEM_PERGUNTAS="${SEM_PERGUNTAS:-0}"
DATA="$(date +%Y-%m-%d-%H%M)"

ok()    { printf "  \033[32mok\033[0m  %s\n" "$1"; }
aviso() { printf "  \033[33m!!\033[0m  %s\n" "$1"; }
passo() { printf "\n\033[1m%s\033[0m\n" "$1"; }
pergunta() {  # pergunta "texto" "padrão" -> resposta em $RESP
  RESP="$2"
  if [ "$SEM_PERGUNTAS" != "1" ]; then
    read -r -p "  $1 ${2:+[$2] }" RESP || true
    RESP="${RESP:-$2}"
  fi
}

passo "1/6  Conferindo o computador"
[ "$(uname)" = "Darwin" ] || { echo "Este pack só funciona no macOS (usa o Apple Vision pra recortar a pessoa)."; exit 1; }
ok "macOS"
command -v git >/dev/null && ok "git" || { aviso "falta o git: rode  xcode-select --install  e depois este instalador de novo"; exit 1; }
command -v python3 >/dev/null && ok "python3" || { aviso "falta o python3: rode  xcode-select --install"; exit 1; }
if command -v swiftc >/dev/null; then ok "swiftc (recorte da pessoa)"; else
  aviso "falta o swiftc: rode  xcode-select --install  (sem ele não dá pra recortar a pessoa nos efeitos atrás da cabeça)"; fi
if command -v ffmpeg >/dev/null; then ok "ffmpeg ($(ffmpeg -version | head -1 | cut -d' ' -f3))"
elif command -v brew >/dev/null; then
  pergunta "O ffmpeg não está instalado. Instalar agora com o Homebrew? (s/n)" "s"
  [ "$RESP" = "s" ] && brew install ffmpeg && ok "ffmpeg instalado"
else aviso "falta o ffmpeg. Instale o Homebrew (brew.sh) e rode  brew install ffmpeg"; fi
command -v node >/dev/null && ok "node (só a reel-editor usa)" || aviso "sem node: só a reel-editor precisa (HyperFrames). Dá pra instalar depois em nodejs.org"

passo "2/6  video-use (transcrição e base do corte)"
if [ -x "$VIDEO_USE/.venv/bin/python" ]; then ok "já instalado em $VIDEO_USE"
else
  pergunta "Instalar o video-use em $VIDEO_USE? (s/n)" "s"
  if [ "$RESP" = "s" ]; then
    mkdir -p "$H/Developer"
    [ -d "$VIDEO_USE" ] || git clone --depth 1 https://github.com/browser-use/video-use "$VIDEO_USE"
    if command -v uv >/dev/null; then (cd "$VIDEO_USE" && uv sync)
    else (cd "$VIDEO_USE" && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e .); fi
    "$VIDEO_USE/.venv/bin/python" -c "import numpy, PIL, scipy" && ok "video-use instalado"
  else aviso "sem o video-use as skills não rodam. Dá pra rodar este instalador de novo depois."; fi
fi

passo "3/6  Chaves de API (ficam só no seu computador)"
if [ -f "$VIDEO_USE/.env" ] && grep -q "^ELEVENLABS_API_KEY=." "$VIDEO_USE/.env"; then ok "ElevenLabs já configurada"
elif [ "$SEM_PERGUNTAS" != "1" ] && [ -d "$VIDEO_USE" ]; then
  echo "  A transcrição usa o ElevenLabs (Scribe). Crie a chave em elevenlabs.io > Developers > API Keys."
  read -r -s -p "  Cole a chave do ElevenLabs (Enter pula): " K || true; echo
  if [ -n "${K:-}" ]; then echo "ELEVENLABS_API_KEY=$K" >> "$VIDEO_USE/.env"; chmod 600 "$VIDEO_USE/.env"; ok "ElevenLabs salva em $VIDEO_USE/.env"
  else aviso "sem chave do ElevenLabs: as skills não conseguem transcrever. Ponha depois em $VIDEO_USE/.env"; fi
fi
mkdir -p "$H/.claude"
if [ -f "$H/.claude/env" ] && grep -q "^OPENAI_API_KEY=." "$H/.claude/env"; then ok "OpenAI já configurada"
elif [ "$SEM_PERGUNTAS" != "1" ]; then
  echo "  Opcional: a OpenAI gera imagens e objetos 3D quando você não tem material próprio (~US\$0,05 cada)."
  read -r -s -p "  Cole a chave da OpenAI (Enter pula): " K || true; echo
  if [ -n "${K:-}" ]; then echo "OPENAI_API_KEY=$K" >> "$H/.claude/env"; chmod 600 "$H/.claude/env"; ok "OpenAI salva em ~/.claude/env"
  else ok "sem OpenAI (dá pra pôr depois em ~/.claude/env)"; fi
fi

passo "4/6  Copiando as skills"
mkdir -p "$SKILLS"
BACKUP="$H/.claude/skills-backup-$DATA"
for d in "$AQUI"/skills/*/; do
  nome="$(basename "$d")"
  if [ -e "$SKILLS/$nome" ]; then mkdir -p "$BACKUP"; mv "$SKILLS/$nome" "$BACKUP/"; fi
  cp -R "$d" "$SKILLS/$nome"
  ok "$nome"
done
[ -d "$BACKUP" ] && aviso "versões antigas com o mesmo nome foram guardadas em $BACKUP"

passo "5/6  Pasta comum (corte com sobreposição, storyboard, perfil)"
mkdir -p "$PADROES"
for f in corte_sobreposto.py corte-sobreposto.md storyboard.py perfil.py perfil.exemplo.json foto-perfil.png; do
  cp "$AQUI/padroes-edicao/$f" "$PADROES/$f"
done
ok "$PADROES"

passo "6/6  Seu perfil (nome, @, cor e foto que aparecem nos vídeos)"
if [ -f "$PADROES/perfil.json" ]; then
  ok "já existe $PADROES/perfil.json (mantido; pra mudar, edite o arquivo ou peça ao Claude)"
else
  pergunta "Seu nome:" "Seu Nome"; NOME="$RESP"
  pergunta "Seu @ do Instagram (sem o @):" "seuperfil"; IG="${RESP#@}"
  pergunta "Cor de destaque das legendas, em hex:" "#FFC700"; COR="$RESP"
  pergunta "Caminho da sua foto de perfil (arraste o arquivo aqui; Enter usa uma genérica):" ""; FOTO_ORIG="${RESP//\'/}"
  FOTO="$PADROES/foto-perfil.png"
  FOTO_ORIG="$(echo "$FOTO_ORIG" | sed 's/\\ / /g; s/[[:space:]]*$//')"
  if [ -n "$FOTO_ORIG" ] && [ -f "$FOTO_ORIG" ]; then
    EXT="${FOTO_ORIG##*.}"; FOTO="$PADROES/minha-foto.$EXT"; cp "$FOTO_ORIG" "$FOTO"
  fi
  pergunta "Produto ou serviço do CTA (Enter pula):" ""; PROD="$RESP"
  pergunta "Link do CTA (Enter pula):" ""; LINK="$RESP"
  NOME="$NOME" IG="$IG" COR="$COR" FOTO="$FOTO" PROD="$PROD" LINK="$LINK" python3 - "$PADROES/perfil.json" <<'EOF'
import json, os, sys
d = {"nome": os.environ["NOME"], "instagram": os.environ["IG"], "cor_destaque": os.environ["COR"],
     "foto": os.environ["FOTO"], "produto": os.environ["PROD"], "link": os.environ["LINK"]}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
EOF
  ok "perfil salvo em $PADROES/perfil.json"
fi

printf "\n\033[1mPronto.\033[0m Abra o Claude Code numa pasta com o seu vídeo cru e peça, por exemplo:\n"
printf "  \"/reel-glow edita o video.mov\"   ou   \"edita esse vídeo no estilo Kelsey\"\n"
printf "Antes de renderizar, o Claude te manda o storyboard com os quadros pra você aprovar.\n\n"
