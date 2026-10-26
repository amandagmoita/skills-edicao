"""perfil.py — os dados do criador que as skills de Reels usam no vídeo.

Fica em ~/.claude/padroes-edicao/perfil.json (o instalar.sh pergunta e grava; dá pra editar à mão
ou pedir ao Claude: "atualiza meu perfil das skills de Reels"). Campos:

  nome          nome que aparece em cartões de perfil e notificações
  instagram     @ sem o "@" (ex.: "seuperfil")
  cor_destaque  cor de destaque das legendas e títulos, em hex (ex.: "#FFC700")
  foto          caminho da sua foto de perfil (PNG/JPG quadrado), usada nos cartões de perfil
  produto       nome do produto/serviço do CTA (ex.: "Mentoria X"), opcional
  link          link do CTA, opcional

Uso no código:
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import perfil
    P = perfil.carregar()           # dict com todos os campos (padrões no lugar do que faltar)
    P["instagram"], P["cor_destaque"], perfil.foto()
"""

from __future__ import annotations

import json
from pathlib import Path

PASTA = Path.home() / ".claude" / "padroes-edicao"
ARQUIVO = PASTA / "perfil.json"
PADRAO = {
    "nome": "Seu Nome",
    "instagram": "seuperfil",
    "cor_destaque": "#FFC700",
    "foto": str(PASTA / "foto-perfil.png"),
    "produto": "",
    "link": "",
}


def carregar() -> dict:
    dados = dict(PADRAO)
    if ARQUIVO.exists():
        try:
            dados.update({k: v for k, v in json.loads(ARQUIVO.read_text(encoding="utf-8")).items() if v not in (None, "")})
        except json.JSONDecodeError:
            print(f"aviso: {ARQUIVO} está com erro de JSON; usando os padrões")
    dados["instagram"] = str(dados["instagram"]).lstrip("@")
    return dados


def foto() -> Path:
    """Caminho da foto de perfil (cai na foto genérica do pack se a do perfil não existir)."""
    p = Path(str(carregar()["foto"])).expanduser()
    return p if p.exists() else PASTA / "foto-perfil.png"
