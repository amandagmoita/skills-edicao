"""storyboard.py — storyboard de aprovação de TODA edição de Reels do pack.

Antes de renderizar o vídeo, o usuário vê exatamente o que vai ser feito, cena a cena, com o quadro
de verdade, pra aprovar ou mudar. Vale pra todas as skills de Reels.

Como funciona:
  - o `compor.py` de cada skill sabe quando entra cada título, elemento, zoom e transição; ele monta
    a lista de `momentos` e renderiza o quadro de cada um com a edição REAL (o mesmo desenho do vídeo);
  - este módulo junta tudo numa página só, `<edit>/storyboard.html` (imagens embutidas, abre em
    qualquer lugar, inclusive no celular), e grava `<edit>/storyboard.json`.

Uma CENA = uma tomada (frase). Cada momento ganha um código (cena + letra: 4B) pro usuário pedir mudança
("4B: troca o título por X", "7: tira o número").

Uso dentro do compor.py (modelo: função storyboard() do compor.py da reels-kelsey):
    sys.path.insert(0, str(Path.home() / ".claude/padroes-edicao"))
    import storyboard as SB
    SB.gerar(EDIT, estilo="Kelsey", total=TOTAL, cenas=[...], momentos=[...],
             quadro=lambda t: <PIL.Image do quadro composto em t>, avisos=[...], arquivos=[...])
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
from datetime import datetime
from pathlib import Path

LARG_MINI = 720   # largura do quadro embutido (px): nítido no zoom do celular; a grade reduz


def limpa_marcacao(txt: str) -> str:
    """Tira as marcações de estilo dos títulos (*chave*, _ligação_, /itálico/, +segunda cor+)."""
    return re.sub(r"[*_/+]", "", txt).strip()


def textos_do_spec(spec: dict) -> str:
    """Texto legível de um elemento qualquer do mapa (vale pra todas as skills)."""
    partes = []
    for k in ("linhas", "titulo", "texto", "valor", "rotulo", "nome", "chamada", "selo", "esq", "dir"):
        v = spec.get(k)
        if isinstance(v, list):
            partes.append(" / ".join(limpa_marcacao(str(x.get("txt") or x.get("texto") or "") if isinstance(x, dict)
                                                    else str(x)) for x in v))
        elif v not in (None, ""):
            partes.append(limpa_marcacao(str(v)))
    if spec.get("de") not in (None, "") and spec.get("para") not in (None, ""):
        partes.append(f"{spec['de']} → {spec['para']}")
    itens = [(i.get("texto") or i.get("arquivo")) if isinstance(i, dict) else i for i in spec.get("itens", [])]
    itens = [str(i) for i in itens if i]
    if itens:
        partes.append(" · ".join(itens))
    arqs = spec.get("arquivos") or ([spec["arquivo"]] if spec.get("arquivo") else [])
    if arqs:
        partes.append("arquivos: " + ", ".join(Path(a).name for a in arqs))
    return " — ".join(p for p in partes if p)


def tempo_br(t: float) -> str:
    return f"{t:.1f}".replace(".", ",") + " s"


def _mini(im) -> str:
    im = im.convert("RGB")
    h = round(im.height * LARG_MINI / im.width)
    buf = io.BytesIO()
    im.resize((LARG_MINI, h)).save(buf, "JPEG", quality=80, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def gerar(edit: Path, estilo: str, total: float, cenas: list[dict], momentos: list[dict], quadro,
          avisos: list[str] | None = None, arquivos: list[tuple[str, bool]] | None = None,
          titulo: str | None = None) -> Path:
    """cenas:    [{"t0", "t1", "fala", "nome"?}] na ordem (uma por tomada; sem transcrição, "fala" vazia e "nome")
       momentos: [{"t0", "t1", "quadro" (instante do quadro), "tipo" (rótulo curto), "desc", "aviso"?}]
       quadro:   função t -> PIL.Image (quadro composto da edição real)
       arquivos: [(nome, existe)] imagens/vídeos que a edição usa"""
    edit = Path(edit)
    momentos = sorted(momentos, key=lambda m: (m["t0"], m["quadro"]))
    # cada momento cai na cena em que começa
    por_cena: list[list[dict]] = [[] for _ in cenas]
    for m in momentos:
        # o que começa até 0,15 s antes de uma cena (transição na emenda) já é da cena seguinte
        k = max([i for i, c in enumerate(cenas) if c["t0"] <= m["t0"] + 0.15] or [0])
        por_cena[k].append(m)
    cache: dict[float, str] = {}

    def img(t: float) -> str:
        t = round(min(max(0.0, t), total - 0.05), 2)
        if t not in cache:
            cache[t] = _mini(quadro(t))
        return cache[t]

    registro = []
    blocos = []
    for i, (c, ms) in enumerate(zip(cenas, por_cena), 1):
        tiles = []
        if not ms:   # cena sem nada novo: o que continua na tela da cena anterior, ou só a pessoa + legenda
            seguem = [m for m in momentos if m["t0"] < c["t0"] and m["t1"] > c["t0"] + 0.2]
            meio = (c["t0"] + c["t1"]) / 2
            if seguem:
                ms_show = [{"t0": c["t0"], "t1": c["t1"], "quadro": meio,
                            "tipo": "Continua: " + " + ".join(dict.fromkeys(m["tipo"] for m in seguem)),
                            "desc": "nada novo entra; segue na tela o que veio da cena anterior", "_vazio": True}]
            else:
                ms_show = [{"t0": c["t0"], "t1": c["t1"], "quadro": meio,
                            "tipo": "Só você", "desc": "sem elemento novo: você + legenda", "_vazio": True}]
        else:
            ms_show = ms
        for j, m in enumerate(ms_show):
            cod = f"{i}{chr(65 + j)}" if not m.get("_vazio") else f"{i}"
            registro.append({"codigo": cod, "cena": i, **{k: v for k, v in m.items() if not k.startswith("_")}})
            aviso = f'<p class="aviso">⚠ {html.escape(m["aviso"])}</p>' if m.get("aviso") else ""
            tiles.append(f"""
        <figure class="tile{' vazio' if m.get('_vazio') else ''}">
          <button class="thumb" aria-label="ampliar {cod}">
            <img src="data:image/jpeg;base64,{img(m['quadro'])}" alt="quadro {cod}" loading="lazy">
          </button>
          <figcaption>
            <div class="cod"><b>{cod}</b><span>{tempo_br(m['t0'])}{' – ' + tempo_br(m['t1']) if m['t1'] - m['t0'] > 0.3 else ''}</span></div>
            <div class="tipo">{html.escape(m['tipo'])}</div>
            <div class="desc">{html.escape(m['desc'])}</div>{aviso}
          </figcaption>
        </figure>""")
        blocos.append(f"""
    <section class="cena" id="cena-{i}">
      <header>
        <span class="n">Cena {i}</span>
        <span class="t">{html.escape(c["nome"]) + " · " if c.get("nome") else ""}{tempo_br(c['t0'])} – {tempo_br(c['t1'])}</span>
      </header>
      {f'<blockquote>“{html.escape(c["fala"])}”</blockquote>' if c.get("fala") else ""}
      <div class="tiles">{''.join(tiles)}
      </div>
    </section>""")

    # linha do tempo: cenas + marcas dos momentos
    faixas = "".join(f'<a class="faixa" href="#cena-{i}" style="left:{100 * c["t0"] / total:.2f}%;'
                     f'width:{100 * (c["t1"] - c["t0"]) / total:.2f}%" title="Cena {i}">{i}</a>'
                     for i, c in enumerate(cenas, 1))
    marcas = "".join(f'<i style="left:{100 * m["t0"] / total:.2f}%"></i>' for m in momentos)
    av = ""
    if avisos:
        av = '<section class="avisos"><h2>Pontos de atenção</h2><ul>' + "".join(
            f"<li>{html.escape(a)}</li>" for a in avisos) + "</ul></section>"
    arq = ""
    if arquivos:
        arq = '<section class="arquivos"><h2>Imagens e vídeos usados</h2><ul>' + "".join(
            f'<li class="{"ok" if ok else "falta"}">{html.escape(n)}{"" if ok else " — FALTA"}</li>'
            for n, ok in arquivos) + "</ul></section>"
    nome = titulo or edit.parent.name
    pagina = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Storyboard {html.escape(nome)}</title>
<style>
  :root {{
    --bg: #111113; --card: #1b1b1f; --linha: #2c2c33; --txt: #ececf1; --suave: #9a9aa6;
    --destaque: #FFC700; --aviso: #ff9f43; --falta: #ff5d6c; --ok: #4cd18a;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--txt);
         font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 28px 16px 64px; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 15px; margin: 0 0 10px; color: var(--suave); font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }}
  .meta {{ color: var(--suave); margin: 0 0 18px; }}
  .como {{ background: var(--card); border: 1px solid var(--linha); border-left: 4px solid var(--destaque);
          border-radius: 10px; padding: 14px 16px; margin-bottom: 18px; }}
  .como p {{ margin: 0; }}
  .como code {{ background: #26262c; padding: 1px 6px; border-radius: 5px; color: var(--destaque); }}
  .linha {{ position: relative; height: 34px; background: var(--card); border: 1px solid var(--linha);
           border-radius: 8px; margin: 6px 0 26px; overflow: hidden; }}
  .faixa {{ position: absolute; top: 0; bottom: 0; border-right: 1px solid var(--linha); color: var(--suave);
           font-size: 11px; text-decoration: none; padding: 3px 4px; overflow: hidden; }}
  .faixa:hover {{ background: #26262c; color: var(--txt); }}
  .linha i {{ position: absolute; bottom: 0; width: 2px; height: 10px; background: var(--destaque); }}
  .avisos, .arquivos {{ background: var(--card); border: 1px solid var(--linha); border-radius: 10px;
                       padding: 14px 16px; margin-bottom: 18px; }}
  .avisos li {{ color: var(--aviso); }}
  .arquivos ul {{ columns: 2 220px; margin: 0; padding-left: 18px; }}
  .arquivos .falta {{ color: var(--falta); font-weight: 600; }}
  .cena {{ border-top: 1px solid var(--linha); padding: 20px 0 8px; scroll-margin-top: 12px; }}
  .cena header {{ display: flex; gap: 12px; align-items: baseline; }}
  .cena .n {{ font-weight: 700; font-size: 18px; }}
  .cena .t {{ color: var(--suave); font-variant-numeric: tabular-nums; }}
  blockquote {{ margin: 6px 0 14px; color: #d6d6de; font-style: italic; max-width: 70ch; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; }}
  .tile {{ margin: 0; background: var(--card); border: 1px solid var(--linha); border-radius: 10px; overflow: hidden; }}
  .tile.vazio {{ opacity: .75; }}
  .thumb {{ display: block; width: 100%; padding: 0; border: 0; background: #000; cursor: zoom-in; }}
  .thumb img {{ display: block; width: 100%; aspect-ratio: 9 / 16; object-fit: cover; }}
  figcaption {{ padding: 9px 10px 11px; }}
  .cod {{ display: flex; justify-content: space-between; gap: 6px; font-variant-numeric: tabular-nums; }}
  .cod b {{ color: var(--destaque); font-size: 16px; }}
  .cod span {{ color: var(--suave); font-size: 12px; }}
  .tipo {{ font-weight: 600; margin-top: 2px; }}
  .desc {{ color: #c9c9d2; font-size: 13px; overflow-wrap: anywhere; }}
  .aviso {{ color: var(--aviso); font-size: 12px; margin: 6px 0 0; }}
  #zoom {{ position: fixed; inset: 0; background: rgba(0,0,0,.88); display: none; align-items: center;
          justify-content: center; z-index: 9; cursor: zoom-out; padding: 16px; }}
  #zoom.on {{ display: flex; }}
  #zoom img {{ max-height: 100%; max-width: 100%; border-radius: 8px; }}
  @media (max-width: 520px) {{ .tiles {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }} h1 {{ font-size: 21px; }} }}
</style>
</head>
<body>
<main>
  <h1>Storyboard · {html.escape(nome)}</h1>
  <p class="meta">Estilo {html.escape(estilo)} · {tempo_br(total)} · {len(cenas)} cenas · {len(momentos)} momentos ·
     gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
  <div class="como"><p><b>Nada foi renderizado ainda.</b> Cada quadro abaixo é a edição real naquele instante.
     Responda <code>aprovado</code> ou diga o código e o que mudar: <code>4B: troca o título por "..."</code>,
     <code>7: tira o número</code>, <code>2A: entra mais cedo</code>. Toque num quadro pra ampliar.</p></div>
  <div class="linha">{faixas}{marcas}</div>
  {av}
  {''.join(blocos)}
  {arq}
</main>
<div id="zoom"><img alt=""></div>
<script>
  const z = document.getElementById('zoom'), zi = z.querySelector('img');
  document.querySelectorAll('.thumb').forEach(b => b.addEventListener('click', () => {{
    zi.src = b.querySelector('img').src; z.classList.add('on'); }}));
  z.addEventListener('click', () => z.classList.remove('on'));
</script>
</body>
</html>"""
    out = edit / "storyboard.html"
    out.write_text(pagina, encoding="utf-8")
    (edit / "storyboard.json").write_text(json.dumps(
        {"estilo": estilo, "total": total, "cenas": cenas, "momentos": registro, "avisos": avisos or []},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return out
