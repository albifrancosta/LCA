"""Visual Storyboard — uma linha por take, sincronizada com a narração, apontando para as referências da bíblia.

Imagem do take: a última versão VÁLIDA de imagem da tomada (producao.json → versoes), senão a referência do cenário,
senão None (a prancha desenha o quadro cinza com a ação — ponto de conferência 1, antes de gastar com imagem).
"""


def imagem_do_take(t, cenario_ref):
    v = next((v for v in reversed(t.get("versoes") or []) if v.get("tipo") == "imagem" and not v.get("invalida")), None)
    if v:
        return {"arquivo": v["arquivo"], "fonte": f"imagem v{v.get('v', '?')}"}
    if cenario_ref:
        return {"arquivo": cenario_ref, "fonte": "referência do cenário"}
    return None


def montar(tomadas_bible, fontes, planos, chars, envs, props):
    """`fontes`: {take_id: tomada original de producao.json}. Devolve a lista de linhas do storyboard."""
    linhas = []
    for tb in tomadas_bible:
        t = fontes[tb["take_id"]]
        pl = planos.get(tb["take_id"]) or {}
        env = envs.get(tb["environment_id"]) if tb.get("environment_id") else None
        env_ref = ((env or {}).get("visao_geral") or {}).get("arquivo")
        refs = []
        for cid in tb["characters"]:
            c = chars[cid]
            if c.get("ficha"):
                refs.append({"tipo": "personagem", "id": cid, "arquivo": c["ficha"]["arquivo"], "versao": c["ficha"]["versao"]})
        if env_ref:
            refs.append({"tipo": "cenario", "id": tb["environment_id"], "arquivo": env_ref, "versao": env["visao_geral"]["versao"]})
        for pid in tb["props"]:
            if props[pid].get("ref"):
                refs.append({"tipo": "objeto", "id": pid, "arquivo": props[pid]["ref"]["arquivo"], "versao": props[pid]["ref"]["versao"]})
        linhas.append({
            "take_id": tb["take_id"], "cena_num": tb["cena_num"], "take_num": tb["take_num"], "cena": tb["cena"],
            "rotulo": f"C{tb['cena_num']:02d}·T{tb['take_num']:02d}",
            "imagem": imagem_do_take(t, env_ref),
            "inicio": tb["inicio"], "fim": tb["fim"], "duracao": tb["duracao"], "tempo_fonte": tb["tempo_fonte"],
            "personagens": [{"id": cid, "nome": chars[cid]["nome"]} for cid in tb["characters"]],
            "acao": t.get("acao", ""), "emocao": t.get("emocao") or (t.get("direcao") or {}).get("emocao"),
            "narracao": t.get("fala") or t.get("narracao") or "",
            "enquadramento": pl.get("enquadramento"), "movimento_camera": pl.get("movimento"), "lente_mm": pl.get("lente_mm"),
            "objetos": [{"id": pid, "estado": tb["props_estado"].get(pid, "em cena")} for pid in tb["props"]],
            "efeitos": list(t.get("efeitos") or (t.get("direcao") or {}).get("efeitos") or []),
            "referencias": refs,
        })
    return linhas
