#!/usr/bin/env python3
"""rascunho_mapa.py — monta o RASCUNHO do mapa de edição a partir das palavras do corte.

Uso:
  python3 rascunho_mapa.py <pasta_projeto> [--cor "#RRGGBB"]   # padrão: cor de destaque do perfil

Lê palavras_corte.json e grava mapa.json com:
  - legendas já quebradas em blocos de 2 a 4 palavras (quebra em pontuação e pausa)
  - listas vazias de números, telas pretas, stickers e o objeto do gancho
Também imprime a transcrição do corte com tempos, pra o Claude decidir os efeitos.

O Claude EDITA o mapa.json depois (ver SKILL.md, etapa 4): marca a "chave" de cada bloco,
os blocos inteiros na cor de destaque (campo "rosa") e preenche os efeitos.
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "padroes-edicao"))
import perfil  # noqa: E402

PERFIL = perfil.carregar()   # cor de destaque do criador (~/.claude/padroes-edicao/perfil.json)

MAX_PALAVRAS, MAX_CHARS = 4, 22


def limpa(w):
    return re.sub(r"[^\wÀ-ÿ%$]", "", w.lower())


# bloco não termina em palavra de ligação: ela desce pro bloco seguinte
LIGACAO = set("a o as os um uma uns umas e ou de da do das dos em no na nos nas com por pra para "
              "que se seu sua seus suas meu minha te me lhe ao à é eu você".split())


def blocos(palavras):
    out, atual = [], []
    for k, p in enumerate(palavras):
        atual.append(p)
        prox = palavras[k + 1] if k + 1 < len(palavras) else None
        texto = " ".join(x["w"] for x in atual)
        quebra = (
            prox is None
            or len(atual) >= MAX_PALAVRAS
            or len(texto) + 1 + len(prox["w"]) > MAX_CHARS
            or p["w"][-1] in ".!?;:"
            or (p["w"][-1] == "," and len(atual) >= 2)
            or prox["s"] - p["e"] > 0.25
        )
        if quebra:
            sobra = []
            while (prox is not None and len(atual) > 1 and atual[-1]["w"][-1].isalnum()
                   and limpa(atual[-1]["w"]) in LIGACAO):
                sobra.insert(0, atual.pop())
            out.append(atual); atual = sobra
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto"); ap.add_argument("--cor", default=PERFIL["cor_destaque"])
    a = ap.parse_args()
    palavras = json.load(open(os.path.join(a.projeto, "palavras_corte.json")))
    corte = json.load(open(os.path.join(a.projeto, "corte.json")))

    legs = []
    bs = blocos(palavras)
    for k, b in enumerate(bs):
        ini = b[0]["s"]
        fim = bs[k + 1][0]["s"] if k + 1 < len(bs) else corte["total"]
        fim = min(fim, b[-1]["e"] + 0.6)  # pausa longa: a legenda some
        legs.append({"ini": round(ini, 3), "fim": round(fim, 3),
                     "texto": " ".join(p["w"] for p in b), "chave": "", "rosa": False})

    mapa = {
        "cor": a.cor,
        "total": corte["total"],
        "legendas": legs,
        "numeros": [],        # {"ini","fim","texto":"4s"}
        "telas_pretas": [],   # {"ini","fim","destaques":["palavra"],"objeto":"assets/x.png"}
        "stickers": [],       # {"ini","fim","imagem":"assets/x.png"}
        "objeto_gancho": None,  # {"ini","fim","imagem","lado":"direita|esquerda|acima","tamanho":0.4,"giro":-15}
        "objetos_ia": [],     # {"nome":"ampulheta","descricao":"an antique wooden hourglass"}
        "musica": None,       # caminho opcional
    }
    destino = os.path.join(a.projeto, "mapa.json")
    if os.path.exists(destino):
        destino = os.path.join(a.projeto, "mapa.rascunho.json")
        print("mapa.json já existe; rascunho salvo em mapa.rascunho.json")
    json.dump(mapa, open(destino, "w"), ensure_ascii=False, indent=1)
    print(f"{len(legs)} blocos de legenda -> {destino}\n")
    for l in legs:
        print(f"{l['ini']:6.2f}–{l['fim']:6.2f}  {l['texto']}")


if __name__ == "__main__":
    sys.exit(main())
