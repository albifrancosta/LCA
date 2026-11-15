"""Resumo da execução de um projeto (painel em texto/Markdown): takes, grátis × crédito × pago, custo, economia, tempo,
aprovados/reprovados e provedores disponíveis — tudo dos registros reais, sem rede e sem custo.

Fontes: memoria/provedores-tentativas.jsonl (cada tentativa do roteador, filtrada pelo job do projeto) · memoria/reservas.json
(via projeto.orcamento: confirmado/desconhecido/reservado) · entrega/autonomo.json · entrega/inspecao-planos.json ·
memoria/provedores-descoberta.json · entrega/progresso.json.
Economia: base EXPLÍCITA e comparável = segundos gerados × preço por segundo de um provedor de referência DOCUMENTADO no
catálogo (padrão: fal-kling26-pro, US$ 0,07/s, "API oficial de preços do fal"), menos o comprometido real. Sem segundos
medidos → economia "não calculável" (não inventa).

Uso:  python resumo_execucao.py <projeto> [--referencia fal-kling26-pro]   → entrega/resumo-execucao.md + .json
"""
import argparse
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

DISPONIVEIS = ("gratis_api", "pago_api", "credito_promocional")


def _ler(arq, padrao):
    try:
        return json.load(io.open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def resumo(base, referencia="fal-kling26-pro"):
    import progresso as prog
    import projeto as pj
    import provedores as pv
    import provider_discovery as pd
    cfg = pj.carregar(base)
    job = pj.job_id(cfg)
    tent = pv.eventos(lambda e: e.get("tipo") == "tentativa" and (e.get("job_id") == job or str(e.get("job_id", "")).startswith(job + ":")))
    ok = [e for e in tent if e.get("resultado") == "sucesso"]
    nivel = lambda e: e.get("nivel") or ("gratis" if e.get("estimado_usd") == 0 else "pago")  # noqa: E731
    por_nivel = {k: sum(1 for e in ok if nivel(e) == k) for k in ("gratis", "credito_promocional", "pago")}
    seg = 0.0
    for e in ok:
        s = ig.sonda(e["saida"]) if e.get("saida") and os.path.isfile(e["saida"]) else None
        seg += s["duracao"] if s else float(e.get("duracao_s") or 0)
    orc = pj.orcamento(cfg)
    cat, _ = pv.config()
    ref = next((p for p in cat["provedores"] if p["id"] == referencia), None) or {}
    pr = ref.get("price") or {}
    preco_ref = pr.get("amount_per_unit") if pr.get("unit") == "second" else None
    if preco_ref and seg:
        custaria = round(seg * preco_ref, 2)
        economia = {"referencia": referencia, "preco_por_s": preco_ref, "fonte": pr.get("fonte"), "segundos": round(seg, 1),
                    "custaria_usd": custaria, "comprometido_usd": orc["comprometido"], "economia_usd": round(custaria - orc["comprometido"], 2)}
    else:
        economia = {"referencia": referencia, "nao_calculavel": "sem preço por segundo documentado na referência ou sem segundos gerados"}
    estados = {}
    for e in _ler(os.path.join(base, "entrega", "autonomo.json"), {}).get("planos", {}).values():
        estados[e.get("estado")] = estados.get(e.get("estado"), 0) + 1
    insp = _ler(os.path.join(base, "entrega", "inspecao-planos.json"), {}).get("itens", [])
    disc = pd.ler()
    fichas = disc.get("provedores", {})
    return {"projeto": os.path.basename(base), "job": job, "modo": cfg["autonomia"]["modo"],
            "takes_gerados": len(ok), "tentativas": len(tent), "por_nivel": por_nivel,
            "falhas_por_tipo": {t: sum(1 for e in tent if e.get("erro_tipo") == t) for t in sorted({e.get("erro_tipo") for e in tent if e.get("erro_tipo")})},
            "custo": {k: orc[k] for k in ("teto_autorizado", "gasto_confirmado", "cobrancas_desconhecidas", "reservas_abertas", "comprometido", "livre")},
            "economia": economia, "tempo_processamento_s": round(sum((e.get("latencia_ms") or 0) for e in tent) / 1000, 1),
            "tempo_projeto": prog.fmt(time.time() - prog.inicio_projeto(base)), "progresso_projeto_pct": prog.projeto(base)["pct"],
            "ultima_etapa": prog.ler(base).get("linha"), "estados_takes": estados,
            "inspecao": {"aprovados": sum(1 for i in insp if i.get("estado") == ig.APROVADO),
                         "reprovados": sum(1 for i in insp if i.get("estado") == ig.REPROVADO),
                         "nao_verificados": sum(1 for i in insp if i.get("estado") == ig.NAO_VERIFICADO)},
            "provedores_disponiveis": sorted(k for k, f in fichas.items() if f.get("categoria") in DISPONIVEIS),
            "provedores_indisponiveis": sorted(f"{k} ({f.get('categoria')})" for k, f in fichas.items() if f.get("categoria") not in DISPONIVEIS),
            "descoberta_em": disc.get("verificado_em")}


def markdown(r):
    c, e, i = r["custo"], r["economia"], r["inspecao"]
    L = [f"# Resumo da execução — {r['projeto']}", "", f"Modo **{r['modo']}** · progresso do projeto **{r['progresso_projeto_pct']:.0f}%** · "
         f"{r['tempo_projeto']} desde o início · processamento nos provedores {r['tempo_processamento_s']:.0f} s", "",
         "| Takes gerados | Grátis | Crédito promocional | Pago | Tentativas |", "|---|---|---|---|---|",
         f"| {r['takes_gerados']} | {r['por_nivel']['gratis']} | {r['por_nivel']['credito_promocional']} | {r['por_nivel']['pago']} | {r['tentativas']} |", "",
         f"**Custo:** teto US$ {c['teto_autorizado']:.2f} · confirmado US$ {c['gasto_confirmado']:.2f} · desconhecido US$ {c['cobrancas_desconhecidas']:.2f} · "
         f"reservas abertas US$ {c['reservas_abertas']:.2f} · livre US$ {c['livre']:.2f}", ""]
    if e.get("nao_calculavel"):
        L.append(f"**Economia:** não calculável ({e['nao_calculavel']}).")
    else:
        L.append(f"**Economia** vs {e['referencia']} (US$ {e['preco_por_s']}/s — {e['fonte']}): {e['segundos']} s custariam US$ {e['custaria_usd']:.2f}; "
                 f"comprometido US$ {e['comprometido_usd']:.2f} → economia **US$ {e['economia_usd']:.2f}**.")
    L += ["", f"**Inspeção:** {i['aprovados']} aprovados · {i['reprovados']} reprovados · {i['nao_verificados']} não verificados · estados dos takes: "
          f"{json.dumps(r['estados_takes'], ensure_ascii=False)}", f"**Falhas por tipo:** {json.dumps(r['falhas_por_tipo'], ensure_ascii=False)}", "",
          f"**Provedores disponíveis** (descoberta {r['descoberta_em'] or '—'}): {', '.join(r['provedores_disponiveis']) or '—'}",
          f"**Fora:** {', '.join(r['provedores_indisponiveis']) or '—'}"]
    if r.get("ultima_etapa"):
        L += ["", f"Última linha de progresso: `{r['ultima_etapa']}`"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projeto")
    ap.add_argument("--referencia", default="fal-kling26-pro")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    r = resumo(base, a.referencia)
    ig.gravar_json_atomico(os.path.join(base, "entrega", "resumo-execucao.json"), r)
    md = markdown(r)
    io.open(os.path.join(base, "entrega", "resumo-execucao.md"), "w", encoding="utf-8").write(md)
    print(md)


if __name__ == "__main__":
    main()
