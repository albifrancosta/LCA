"""Cinematic Production Board Generator — pranchas de pré-produção em HTML navegável + PNG + PDF.

Lê `production_bible/bible.json` (production_bible.py) e monta, com imagens REAIS do projeto quando existem:
  1 Character Reference · 2 Storyboard · 3 Environment / Set Design · 4 Shot List · 5 Camera Blocking (esquema)
  6 Props & Continuity · 7 Lighting & Color · 8 Scene Timeline
Saída em production_bible/boards/: overview.html|png|pdf (produção inteira) e cena-NN.html|png|pdf (uma por cena).
Os dados continuam no JSON; o HTML só apresenta. PNG/PDF via Playwright (Chromium da Playwright → Chrome → Edge);
sem navegador, fica o HTML e a limitação é registrada em boards/export.json.

Uso (na pasta do projeto):  python board_generator.py [--projeto .] [--cena 2] [--sem-exportar]
"""
import argparse
import datetime
import html
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import integridade as ig  # noqa: E402
from cinematografia import SKILL  # noqa: E402
from cinematografia import production_bible as pb  # noqa: E402

TEMPLATE = os.path.join(SKILL, "templates", "cinematic_board.html")
CORES_CENA = ["#1f6feb", "#0e7a6b", "#9333ea", "#c2410c", "#be185d", "#4d7c0f", "#0369a1", "#a16207"]
SECOES = [("personagens", "Character Reference"), ("storyboard", "Storyboard"), ("cenarios", "Environment / Set Design"),
          ("shots", "Shot List"), ("blocking", "Camera Blocking"), ("props", "Props & Continuity"),
          ("luz", "Lighting & Color"), ("timeline", "Scene Timeline")]
e = html.escape


def _src(base, rel):
    """Caminho da imagem relativo à pasta boards/ (o HTML continua navegável se a pasta do projeto mudar de lugar)."""
    if not rel:
        return None
    absoluto = rel if os.path.isabs(rel) else os.path.join(base, rel)
    if not os.path.exists(absoluto):
        return None
    return os.path.relpath(absoluto, os.path.join(pb.pasta(base), "boards")).replace("\\", "/")


def _img(base, rel, alt, larga=False, vazio="", ficha=False):
    s = _src(base, rel)
    if s:
        cls = "img ficha" if ficha else ("img larga" if larga else "img")
        return f'<img class="{cls}" src="{e(s)}" alt="{e(alt)}">'
    return f'<div class="vazio{" larga" if larga else ""}">{e(vazio or "sem imagem — " + alt)}</div>'


def _chips(itens):
    return '<div class="chips">' + "".join(f"<span>{e(str(x))}</span>" for x in itens if x) + "</div>"


def _fig(f):
    return ", ".join(f"{k} {v}" for k, v in (f or {}).items())


def sec_personagens(b, base, takes):
    ids = {c for t in takes for c in t["characters"]} if takes is not None else set(b["personagens"])
    out = []
    for cid in sorted(ids):
        c = b["personagens"][cid]
        vistas = "".join(f'<div class="{v["status"]}">{e(k.replace("_", " "))}<br>{e(v["status"])}</div>' for k, v in c["vistas"].items())
        por_cena = "<br>".join(f"<b>{e(str(k))}</b>: {e(_fig(v))}" for k, v in c["figurino_por_cena"].items())
        escala = c["proporcoes"] or c["escala"]
        out.append(f'''<div class="cartao">{_img(base, (c["ficha"] or {}).get("arquivo"), c["nome"], vazio="prancha não gerada — prompt no JSON", ficha=True)}
<div class="corpo"><h3>{e(c["nome"])}</h3><div class="id">{e(cid)} · ficha v{(c["ficha"] or {}).get("versao", "—")}</div>
<div class="vistas">{vistas}</div>
<div class="rot"><b>Expressões</b></div>{_chips(c["expressoes"])}
<div class="rot"><b>Figurino</b> {e(_fig(c["figurino_padrao"]) or "—")}</div><div class="rot">{por_cena}</div>
<div class="rot"><b>Cabelo/acessórios</b></div>{_chips(c["cabelo_acessorios"])}
<div class="rot"><b>Objetos</b></div>{_chips(c["objetos_usados"])}
<div class="rot"><b>Escala</b> {e(json.dumps(escala, ensure_ascii=False) if escala else "não definida")}</div>
</div></div>''')
    return '<div class="grade">' + "".join(out) + "</div>" if out else '<p class="rot">sem personagens</p>'


def sec_storyboard(b, base, takes):
    tk = {t["take_id"] for t in takes}
    out = []
    for s in [s for s in b["storyboard"] if s["take_id"] in tk]:
        img = (s["imagem"] or {}).get("arquivo")
        extras = [p["nome"] for p in s["personagens"]] + [f'{o["id"]}: {o["estado"]}' for o in s["objetos"]] + s["efeitos"]
        refs = ", ".join(f'{r["id"]} v{r["versao"]}' for r in s["referencias"]) or "—"
        out.append(f'''<div class="cartao">{_img(base, img, s["rotulo"], vazio=s["acao"] or s["narracao"])}
<div class="corpo"><h3>{e(s["rotulo"])} <span class="id">{e(s["take_id"])}</span></h3>
<div class="rot"><b>{s["inicio"]:.2f}–{s["fim"]:.2f}s</b> ({s["duracao"]:.2f}s, {e(s["tempo_fonte"])}) · {e(s["enquadramento"] or "")} · {e(str(s["movimento_camera"] or ""))}</div>
<div class="rot"><b>Ação</b> {e(s["acao"])}</div><div class="rot"><b>Emoção</b> {e(s["emocao"] or "—")}</div>
<div class="rot"><b>Narração</b> “{e(s["narracao"])}”</div>{_chips(extras)}
<div class="rot"><b>Refs</b> {e(refs)} · imagem: {e((s["imagem"] or {}).get("fonte", "nenhuma"))}</div>
</div></div>''')
    return '<div class="grade">' + "".join(out) + "</div>"


def sec_cenarios(b, base, takes):
    out = []
    for eid in sorted({t["environment_id"] for t in takes if t.get("environment_id")}):
        c = b["cenarios"][eid]
        cams = "; ".join(f'{p["enquadramento"]} {p["lente_mm"]}mm {p["lado_eixo"] or ""}'.strip() for p in c["posicoes_camera"])
        out.append(f'''<div class="cartao">{_img(base, (c["visao_geral"] or {}).get("arquivo"), eid, larga=True, vazio="referência do cenário não gerada")}
<div class="corpo"><h3>{e(c["descricao"][:80] or eid)}</h3><div class="id">{e(eid)}</div>
<div class="rot"><b>Layout</b> {e(str(c["layout"] or "—"))}</div><div class="rot"><b>Móveis</b></div>{_chips(c["moveis"])}
<div class="rot"><b>Objetos importantes</b></div>{_chips(c["objetos_importantes"])}
<div class="rot"><b>Atmosfera</b> {e(str(c["atmosfera"] or "—"))} · <b>Profundidade</b> {e(str(c["profundidade_escala"] or "—"))}</div>
<div class="rot"><b>Câmeras</b> {e(cams)}</div>
</div></div>''')
    return '<div class="grade">' + "".join(out) + "</div>" if out else '<p class="rot">sem cenários</p>'


def sec_shots(b, takes):
    linhas = []
    for t in takes:
        p = b["planos"][t["take_id"]]
        linhas.append(f'<tr><td class="id">{e(t["take_id"])}</td><td>C{t["cena_num"]:02d}·T{t["take_num"]:02d}</td><td>{e(p["intencao"])}</td>'
                      f'<td>{e(p["enquadramento"])}</td><td>{e(str(p["angulo"]))}</td><td>{e(str(p["movimento"]))}</td><td>{p["lente_mm"] or "—"}mm</td>'
                      f'<td>{e(p["profundidade_campo"])}</td><td>{e(p["transicao_entrada"])}</td><td>{e(p["composicao"])}</td><td>{e(p["fonte"])}</td></tr>')
    return ("<table><tr><th>take</th><th>cena·take</th><th>intenção</th><th>enquadr.</th><th>ângulo</th><th>movimento</th><th>lente</th>"
            "<th>prof. campo</th><th>transição</th><th>composição</th><th>fonte</th></tr>" + "".join(linhas) + "</table>")


def _svg_blocking(b, take):
    """Esquema de planta: eixo de ação, personagens e posição da câmera (lado do eixo, distância pelo enquadramento)."""
    p = b["planos"][take["take_id"]]
    dist = {"aberto": 90, "medio": 70, "fechado": 48, "detalhe": 32}.get(p["enquadramento"], 70)
    cy = 110 + dist if (p.get("lado_eixo") or "baixo") not in ("dir", "direita", "b", "cima") else 110 - dist
    n = len(take["characters"])
    pessoas = []
    for i, c in enumerate(take["characters"]):
        x = 160 if n == 1 else 80 + i * 160 / (n - 1)
        pessoas.append(f'<circle cx="{x:.0f}" cy="110" r="11" fill="#f5b942"/><text x="{x:.0f}" y="94" fill="#e8eaf0" font-size="10" '
                       f'text-anchor="middle">{e(b["personagens"][c]["nome"][:10])}</text>')
    return (f'<svg viewBox="0 0 320 220"><line x1="20" y1="110" x2="300" y2="110" stroke="#475569" stroke-dasharray="6 5"/>'
            f'<text x="24" y="104" fill="#64748b" font-size="9">eixo 180°</text>'
            f'<polygon points="160,{cy} 120,110 200,110" fill="#1f6feb22" stroke="#1f6feb66"/>{"".join(pessoas)}'
            f'<rect x="148" y="{cy - 9}" width="24" height="18" rx="3" fill="#1f6feb"/>'
            f'<text x="178" y="{cy + 4}" fill="#9aa3b2" font-size="10">{e(str(p["movimento"]))} · {p["lente_mm"]}mm</text></svg>')


def sec_blocking(b, takes):
    cards = "".join(f'<div class="cartao"><div class="corpo"><h3>{e(t["take_id"])} <span class="id">C{t["cena_num"]:02d}·T{t["take_num"]:02d}</span></h3>'
                    f'{_svg_blocking(b, t)}<div class="rot">{e(str(b["planos"][t["take_id"]]["movimento_personagens"] or ""))}</div></div></div>'
                    for t in takes)
    return (f'<div class="grade esquema">{cards}</div><p class="rot">Esquema de planta (não é render): câmera do lado do eixo planejado; '
            "distância pelo enquadramento.</p>")


def sec_props(b, takes, problemas):
    tk = {t["take_id"] for t in takes}
    linhas = []
    for pid in sorted({p for t in takes for p in t["props"]}):
        p = b["objetos"][pid]
        ap = ", ".join(a["tomada"] + ": " + a["estado"] for a in p["aparicoes"] if a["tomada"] in tk)
        linhas.append(f'<tr><td class="id">{e(pid)}</td><td>{e(p["descricao"])}</td><td>{e(ap)}</td>'
                      f'<td>{"v" + str(p["ref"]["versao"]) if p.get("ref") else "—"}</td></tr>')
    for t in takes:
        fig = "; ".join(b["personagens"][c]["nome"] + ": " + _fig(f) for c, f in t["figurino"].items())
        linhas.append(f'<tr><td class="id">{e(t["take_id"])}</td><td colspan="3">{e(fig or "sem personagens")} · horário '
                      f'{e(str(t["horario"] or "—"))} · emoção {e(str(t["estado_emocional"] or "—"))}</td></tr>')
    probs = "".join(f'<div class="problema {e(x["gravidade"])}">[{e(x["gravidade"])}] {e(x["codigo"])} — {e(x["texto"])}</div>' for x in problemas)
    return ("<table><tr><th>prop_id / take</th><th>objeto</th><th>tomadas: estado</th><th>ref</th></tr>" + "".join(linhas) + "</table>"
            + (f"<h3>Contradições apontadas</h3>{probs}" if probs else '<p class="rot">Nenhuma contradição de continuidade no planejamento.</p>'))


def sec_luz(b, takes):
    cards = []
    for i in sorted({t["environment_id"] for t in takes if t.get("environment_id")}):
        c = b["cenarios"][i]
        cores = "".join(f'<i style="background:{e(x)}" title="{e(x)}"></i>' for x in c["paleta"])
        cards.append(f'<div class="cartao"><div class="corpo"><h3 class="id">{e(i)}</h3><div class="paleta">{cores}</div>'
                     f'<div class="rot"><b>Luz</b> {e(str(c["luz"] or "—"))}</div><div class="rot"><b>Fontes</b></div>{_chips(c["fontes_luz"] or [])}'
                     f'<div class="rot"><b>Horário</b> {e(str(c["horario"] or "—"))}</div></div></div>')
    return '<div class="grade">' + "".join(cards) + "</div>"


def sec_timeline(b, takes):
    if not takes:
        return ""
    t0, t1 = takes[0]["inicio"], max(t["fim"] for t in takes)
    total = max(0.001, t1 - t0)
    blocos = "".join(f'<div style="left:{(t["inicio"] - t0) / total * 100:.3f}%;width:{t["duracao"] / total * 100:.3f}%;'
                     f'background:{CORES_CENA[(t["cena_num"] - 1) % len(CORES_CENA)]}" title="{e(t["take_id"])} {t["inicio"]:.2f}–{t["fim"]:.2f}s">'
                     f'{e(t["take_id"])}<br>{t["duracao"]:.1f}s</div>' for t in takes)
    cenas = []
    for t in takes:
        if not cenas or cenas[-1][0] != t["cena_num"]:
            cenas.append([t["cena_num"], t["cena"], t["inicio"], t["fim"]])
        cenas[-1][3] = t["fim"]
    tab = "".join(f"<tr><td>C{c[0]:02d}</td><td>{e(str(c[1]))}</td><td>{c[2]:.2f}–{c[3]:.2f}s</td><td>{c[3] - c[2]:.2f}s</td></tr>" for c in cenas)
    return f'<div class="linha-tempo">{blocos}</div><table><tr><th>cena</th><th>nome</th><th>tempo</th><th>duração</th></tr>{tab}</table>'


def renderizar(b, base, cena=None):
    takes = [t for t in b["tomadas"] if cena is None or t["cena_num"] == cena]
    tk = {t["take_id"] for t in takes}
    problemas = [c for c in b["continuidade"] if any(x in c["texto"] for x in tk)] if cena else b["continuidade"]
    corpo = {"personagens": sec_personagens(b, base, takes if cena else None), "storyboard": sec_storyboard(b, base, takes),
             "cenarios": sec_cenarios(b, base, takes), "shots": sec_shots(b, takes), "blocking": sec_blocking(b, takes),
             "props": sec_props(b, takes, problemas), "luz": sec_luz(b, takes), "timeline": sec_timeline(b, takes)}
    secoes = "\n".join(f'<section id="{k}"><h2><span class="n">{i + 1:02d}</span>{e(nome)}</h2>{corpo[k]}</section>'
                       for i, (k, nome) in enumerate(SECOES))
    ap = b["aprovacao"]
    custos = b.get("custos_estimados") or {}
    meta = (f'<span class="selo {e(ap["estado"])}">{e(ap["estado"].upper())}</span> · modo {e(b["modo_aprovacao"])}<br>'
            f'{len(takes)} takes · {sum(t["duracao"] for t in takes):.1f}s · formato {e(b["formato"])}<br>'
            f'bíblia {e(b["hash"][:12])} · custo estimado US$ {custos.get("total_estimado_usd", "—")} (estimativa)')
    sub = f"Cena {cena:02d} — {takes[0]['cena']}" if cena and takes else "Prancha geral da produção"
    nav = " ".join(f'<a href="#{k}">{i + 1:02d} {e(n)}</a>' for i, (k, n) in enumerate(SECOES))
    if cena is None:
        nav += " · " + " ".join(f'<a href="cena-{n:02d}.html">cena {n:02d}</a>' for n in sorted({t["cena_num"] for t in b["tomadas"]}))
    else:
        nav += ' · <a href="overview.html">prancha geral</a>'
    rodape = (f"Gerado em {datetime.datetime.now().isoformat(timespec='seconds')} a partir de production_bible/bible.json "
              f"(fonte {b['fonte']['arquivo']}). Dados estruturados no JSON; este HTML só apresenta.")
    tpl = open(TEMPLATE, encoding="utf-8").read()
    for k, v in {"titulo": e(b["titulo"] or "Produção"), "subtitulo": e(sub), "meta": meta, "nav": nav, "secoes": secoes,
                 "rodape": e(rodape)}.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def exportar(html_arq, png, pdf, largura=1600):
    """PNG (página inteira, 1.5x) e PDF (A3 deitado). Devolve (feitos, limitacoes)."""
    feitos, lim = [], []
    url = "file:///" + os.path.abspath(html_arq).replace("\\", "/")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            nav, erro = None, None
            for canal in (None, "chrome", "msedge"):
                try:
                    nav = p.chromium.launch(channel=canal) if canal else p.chromium.launch()
                    break
                except Exception as ex:  # noqa: BLE001
                    erro = ex
            if nav is None:
                raise RuntimeError(f"nenhum Chromium disponível: {erro}")
            pg = nav.new_page(viewport={"width": largura, "height": 1000}, device_scale_factor=1.5)
            pg.goto(url, wait_until="load")
            pg.wait_for_timeout(300)
            pg.screenshot(path=png, full_page=True)
            feitos.append(png)
            pg.emulate_media(media="screen")
            pg.pdf(path=pdf, format="A3", landscape=True, print_background=True,
                   margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"})
            feitos.append(pdf)
            nav.close()
        return feitos, lim
    except Exception as ex:  # noqa: BLE001
        lim.append(f"playwright: {ex}"[:300])
    exe = next((x for x in (shutil.which("chrome"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if x and os.path.exists(x)), None)
    if not exe:
        lim.append("sem Chrome/Edge para exportar PNG/PDF — use o HTML")
        return feitos, lim
    for args, saida in (([f"--screenshot={png}", f"--window-size={largura},6000"], png), ([f"--print-to-pdf={pdf}", "--no-pdf-header-footer"], pdf)):
        r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", *args, url], capture_output=True, timeout=120)
        if os.path.exists(saida):
            feitos.append(saida)
        else:
            lim.append(f"{os.path.basename(exe)} não gerou {os.path.basename(saida)}: {r.stderr[-200:]!r}")
    return feitos, lim


def gerar(base, cena=None, exportar_midia=True, todas_cenas=True):
    base = os.path.abspath(base)
    b = pb.carregar(base)
    if b is None:
        raise FileNotFoundError("bíblia não construída — rode production_bible.py construir")
    pasta = os.path.join(pb.pasta(base), "boards")
    os.makedirs(pasta, exist_ok=True)
    alvos = [cena] if cena else [None] + (sorted({t["cena_num"] for t in b["tomadas"]}) if todas_cenas else [])
    feitos, lim = [], []
    for c in alvos:
        nome = "overview" if c is None else f"cena-{c:02d}"
        h = os.path.join(pasta, nome + ".html")
        open(h, "w", encoding="utf-8").write(renderizar(b, base, c))
        feitos.append(h)
        if exportar_midia:
            f, li = exportar(h, os.path.join(pasta, nome + ".png"), os.path.join(pasta, nome + ".pdf"))
            feitos += f
            lim += li
    rel = [os.path.relpath(x, base).replace("\\", "/") for x in feitos]
    ig.gravar_json_atomico(os.path.join(pasta, "export.json"),
                           {"gerado_em": datetime.datetime.now().isoformat(timespec="seconds"), "bible_hash": b["hash"],
                            "arquivos": rel, "limitacoes": lim})
    return rel, lim


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projeto", default=".")
    ap.add_argument("--cena", type=int)
    ap.add_argument("--sem-exportar", action="store_true", help="só HTML")
    a = ap.parse_args()
    feitos, lim = gerar(a.projeto, a.cena, not a.sem_exportar)
    print("\n".join(feitos))
    for x in lim:
        print("LIMITAÇÃO:", x)


if __name__ == "__main__":
    main()
