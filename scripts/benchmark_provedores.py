"""Benchmark OPCIONAL dos fornecedores de vídeo/lip-sync — preparado, NUNCA executado com custo por este script.
Compara anatomia, figurino, aparelhos, continuidade, latência e custo por segundo APROVADO.

Casos (os defeitos reais da MinhaMarca "dois mundos" viram a bateria):
  anatomia      pessoa segura tablet com uma mão e gesticula com a outra (Marina, c06c: 3 braços)
  figurino      camisa social de gola aberta em close falando (Marcos, c02e: gravata inventada)
  aparelhos     celular na mão com a tela voltada para a pessoa (c07a: tela nas costas)
  continuidade  pega o casaco e sai (c10d: objeto/peça some entre início e fim)
  simbolos      expressão de dúvida sem nenhum texto/símbolo no ar (c03a: cifrões desenhados)

Uso:
  python benchmark_provedores.py planejar [--provedores a,b] [--dur 5]  → matriz caso × provedor, custo estimado (nada é chamado)
  python benchmark_provedores.py medir                                  → métricas JÁ registradas (log do roteador): grátis
  python benchmark_provedores.py executar --projeto <pasta> --confirmar → recusa: a execução paga passa pelo autonomo/roteador
Saída: memoria/benchmark-plano.json · memoria/benchmark-metricas.json
"""
import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

CASOS = {
    "anatomia": {"prompt": "woman holds a tablet with ONE hand (screen facing her) and gestures with the other hand; exactly two arms",
                 "verifica": ["membros_extras"], "origem": "MinhaMarca c06c"},
    "figurino": {"prompt": "man in a lavender dress shirt, top two buttons undone, bare neck visible, talking to camera in close-up",
                 "verifica": ["figurino_involuntario"], "origem": "MinhaMarca c02e"},
    "aparelhos": {"prompt": "man looks at the smartphone in his hand; the screen faces him, the camera sees only the plain back",
                  "verifica": ["interface_traseira"], "origem": "MinhaMarca c07a"},
    "continuidade": {"prompt": "man closes the laptop, picks up his jacket from the chair and walks out smiling",
                     "verifica": ["continuidade_temporal"], "origem": "MinhaMarca c10d"},
    "simbolos": {"prompt": "man frowns thoughtfully, hand on chin, plain office background, no text or symbols anywhere",
                 "verifica": ["texto_simbolo_gerado"], "origem": "MinhaMarca c03a"},
}
PLANO = os.path.join(SKILL, "memoria", "benchmark-plano.json")
METRICAS = os.path.join(SKILL, "memoria", "benchmark-metricas.json")


def planejar(provedores=None, dur=5.0, gravar=True):
    import provedores as pv
    cat, _ = pv.config()
    alvo = set(provedores.split(",")) if provedores else None
    linhas = []
    for p in cat["provedores"]:
        if p.get("stage") not in ("video", "lipsync") or (alvo and p["id"] not in alvo):
            continue
        est = pv.estimar(p, {"task_type": p["stage"], "requirements": {"duration_s": dur}})
        for caso, c in CASOS.items():
            linhas.append({"caso": caso, "provedor": p["id"], "habilitado": bool(p.get("enabled")), "estimado_usd": est,
                           "uso_comercial": p.get("commercial_use"), "verifica": c["verifica"], "origem": c["origem"]})
    conhecidos = [x["estimado_usd"] for x in linhas if x["estimado_usd"] is not None and x["habilitado"]]
    plano = {"dur_s": dur, "linhas": linhas, "total_estimado_habilitados": round(sum(conhecidos), 2),
             "precos_desconhecidos": sorted({x["provedor"] for x in linhas if x["estimado_usd"] is None}),
             "_leia": "estimativa; nada foi chamado. Desconhecido NÃO é zero — bloqueia até ter preço ou teto aprovado."}
    if gravar:
        ig.gravar_json_atomico(PLANO, plano)
    return plano


def medir(gravar=True):
    """Métricas reais já registradas: aproveitamento, latência mediana, custo por segundo aprovado (sem gastar)."""
    import provedores as pv
    por = {}
    for e in pv.eventos(lambda e: e.get("tipo") == "tentativa"):
        x = por.setdefault(e["provedor"], {"n": 0, "ok": 0, "lat": [], "gasto": 0.0, "seg_ok": 0.0})
        x["n"] += 1
        x["gasto"] += float(e.get("real_usd") or e.get("estimado_usd") or 0)
        if e.get("resultado") == "sucesso":
            x["ok"] += 1
            if e.get("latencia_ms"):
                x["lat"].append(e["latencia_ms"] / 1000)
            s = ig.sonda(e["saida"]) if e.get("saida") and os.path.isfile(e["saida"]) else None
            x["seg_ok"] += s["duracao"] if s else 0
    out = {}
    for k, x in por.items():
        lat = sorted(x["lat"])
        out[k] = {"tentativas": x["n"], "aproveitamento_roteador": round(x["ok"] / x["n"], 2) if x["n"] else None,
                  "latencia_mediana_s": lat[len(lat) // 2] if lat else None, "gasto_usd": round(x["gasto"], 3),
                  "custo_por_segundo_aprovado": round(x["gasto"] / x["seg_ok"], 4) if x["seg_ok"] else None,
                  "_nota": "aprovado = passou na QA do roteador; a reprovação posterior do inspetor ainda não entra"}
    if gravar:
        ig.gravar_json_atomico(METRICAS, out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["planejar", "medir", "executar"])
    ap.add_argument("--provedores")
    ap.add_argument("--dur", type=float, default=5.0)
    ap.add_argument("--projeto")
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args()
    if a.acao == "planejar":
        p = planejar(a.provedores, a.dur)
        print(f"{len(p['linhas'])} combinações · total estimado (habilitados) US$ {p['total_estimado_habilitados']:.2f} · "
              f"preço desconhecido: {', '.join(p['precos_desconhecidos']) or '—'} → {PLANO}")
    elif a.acao == "medir":
        print(json.dumps(medir(), ensure_ascii=False, indent=1))
    else:
        sys.exit("execução paga do benchmark não roda por aqui, de propósito: gere cada caso com tarefas \"projeto\" no "
                 "`autonomo.py`/`provedores.py executar` (teto, reserva e inspeção valem) depois da autorização no chat, e rode `medir`")


if __name__ == "__main__":
    main()
