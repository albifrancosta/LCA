"""Environment / Set Design — uma prancha por cenário com environment_id permanente.

Fonte: producao.json → cenarios[x] (descricao, luz, paleta, ambiente, ref e, quando houver, layout, moveis,
fontes_luz, horario, profundidade) + as tomadas no cenário (objetos importantes e posições de câmera usadas pelo
plano de câmera). Sem fonte → None; o supervisor aponta a lacuna.
"""
import re


def _fontes_luz(src):
    if src.get("fontes_luz"):
        return list(src["fontes_luz"])
    luz = src.get("luz") or ""
    return [x.strip() for x in re.split(r"[,;]", luz) if x.strip()] or None


def montar(env_id, src_id, src, tomadas, planos, ref_de, estilo=""):
    """`planos`: {tomada_id: plano de câmera} (shot_planner) para listar as posições de câmera reais do cenário."""
    minhas = [t for t in tomadas if t.get("cenario") == src_id]
    posicoes = []
    for t in minhas:
        pl = planos.get(t["id"]) or {}
        pos = {"enquadramento": pl.get("enquadramento"), "angulo": pl.get("angulo"), "lado_eixo": pl.get("lado_eixo"),
               "lente_mm": pl.get("lente_mm")}
        if pos not in posicoes:
            posicoes.append(pos)
    p = {
        "environment_id": env_id,
        "origem_id": src_id,
        "descricao": src.get("descricao", ""),
        "visao_geral": ref_de(src["ref"], "cenario") if src.get("ref") else None,
        "layout": src.get("layout"),
        "moveis": list(src.get("moveis") or []),
        "objetos_importantes": sorted({o for t in minhas for o in (t.get("objetos") or [])}),
        "fontes_luz": _fontes_luz(src),
        "luz": src.get("luz"),
        "horario": src.get("horario"),
        "paleta": list(src.get("paleta") or []),
        "atmosfera": src.get("atmosfera") or src.get("ambiente"),
        "profundidade_escala": src.get("profundidade"),
        "posicoes_camera": posicoes,
        "tomadas": [t["id"] for t in minhas],
    }
    p["prompt_prancha"] = ". ".join(x for x in [
        estilo, f"environment design sheet: {p['descricao']}",
        "establishing overview plus top-down floor plan of the same set",
        "furniture: " + ", ".join(p["moveis"]) if p["moveis"] else "",
        "light sources: " + ", ".join(p["fontes_luz"] or []) if p["fontes_luz"] else "",
        "palette " + ", ".join(p["paleta"]) if p["paleta"] else "",
        f"atmosphere: {p['atmosfera']}" if p["atmosfera"] else "",
        "empty set, no characters, no text, no letters, no logos"] if x)
    return p


def lacunas(p):
    out = []
    if not p["visao_geral"]:
        out.append(("media", "cenario_sem_referencia", f"{p['environment_id']}: sem imagem de referência do cenário"))
    elif p["visao_geral"].get("existe") is False:
        out.append(("grave", "referencia_ausente_no_disco", f"{p['environment_id']}: referência {p['visao_geral']['arquivo']} não existe"))
    if not p["luz"] and not p["fontes_luz"]:
        out.append(("media", "luz_indefinida", f"{p['environment_id']}: iluminação não definida"))
    if not p["paleta"]:
        out.append(("leve", "paleta_indefinida", f"{p['environment_id']}: sem paleta de cores"))
    return out
