"""Character Reference Sheet — uma prancha por personagem com character_id permanente.

Fonte: o personagem da bíblia de produção (producao.json → personagens[x]: nome, descricao, ficha, tracos, figurino,
voz e, quando houver, proporcoes/altura_cm/vistas/expressoes) + as tomadas em que ele aparece (figurino por cena,
emoções pedidas, objetos que usa). Nada é inventado: campo sem fonte fica None e o supervisor aponta a lacuna.

As vistas (frontal, lateral, traseira, três quartos) apontam para imagens reais quando existem. Uma `ficha` única
(turnaround) cobre as vistas como "na_ficha" — referência existe, mas a vista específica não foi verificada.
O prompt da prancha serve para gerar a referência por um provedor de imagem (via roteador, dentro do orçamento).
"""

VISTAS = ("frontal", "lateral", "traseira", "tres_quartos")
VISTAS_EN = {"frontal": "front view", "lateral": "side profile view", "traseira": "back view", "tres_quartos": "three-quarter view"}


def _figurino_txt(fig):
    return ", ".join(f"{k} {v}" for k, v in (fig or {}).items())


def figurino_da_tomada(src_id, src, tomada):
    """Figurino que vale nesta tomada: troca declarada na tomada (`figurino: {personagem: {peça: cor}}`) ou o padrão."""
    troca = (tomada.get("figurino") or {}).get(src_id)
    return dict(troca) if isinstance(troca, dict) else dict(src.get("figurino") or {})


def montar(char_id, src_id, src, tomadas, ref_de, estilo=""):
    """Dicionário da prancha. `ref_de(caminho, origem)` registra/versiona uma referência (production_bible.referencia)."""
    minhas = [t for t in tomadas if src_id in (t.get("personagens") or [])]
    vistas = {}
    ficha = src.get("ficha")
    explicitas = src.get("vistas") or {}
    for v in VISTAS:
        if explicitas.get(v):
            vistas[v] = {"status": "referencia", "ref": ref_de(explicitas[v], f"vista:{v}")}
        elif ficha:
            vistas[v] = {"status": "na_ficha", "ref": None, "nota": "coberta pela ficha (turnaround) — vista não verificada isoladamente"}
        else:
            vistas[v] = {"status": "ausente", "ref": None}
    expressoes = []
    for e in ["neutra"] + list(src.get("expressoes") or []) + [t.get("emocao") or (t.get("direcao") or {}).get("emocao") for t in minhas]:
        if e and e not in expressoes:
            expressoes.append(e)
    por_cena = {}
    for t in minhas:
        por_cena.setdefault(t.get("cena") or t["id"], figurino_da_tomada(src_id, src, t))
    objetos = sorted({o for t in minhas for o in (t.get("objetos") or [])})
    tracos = list(src.get("tracos") or [])
    prancha = {
        "character_id": char_id,
        "origem_id": src_id,
        "nome": src.get("nome", src_id),
        "descricao": src.get("descricao", ""),
        "voz": src.get("voz"),
        "ficha": ref_de(ficha, "ficha") if ficha else None,
        "vistas": vistas,
        "expressoes": expressoes,
        "figurino_padrao": dict(src.get("figurino") or {}),
        "figurino_por_cena": por_cena,
        "cabelo_acessorios": tracos,
        "objetos_usados": objetos,
        "proporcoes": src.get("proporcoes"),
        "escala": {"altura_cm": src.get("altura_cm")} if src.get("altura_cm") else None,
        "tomadas": [t["id"] for t in minhas],
    }
    prancha["prompt_prancha"] = prompt(prancha, estilo)
    return prancha


def prompt(p, estilo=""):
    exp = ", ".join(p["expressoes"][:6])
    partes = [estilo, f"character model sheet of {p['nome']}: {p['descricao']}",
              "turnaround with " + ", ".join(VISTAS_EN[v] for v in VISTAS) + " side by side, same scale, full body",
              f"expression row: {exp}" if exp else "",
              "always with " + "; ".join(p["cabelo_acessorios"]) if p["cabelo_acessorios"] else "",
              "outfit: " + _figurino_txt(p["figurino_padrao"]) if p["figurino_padrao"] else "",
              "props: " + ", ".join(p["objetos_usados"]) if p["objetos_usados"] else "",
              "height reference lines, neutral light grey background, flat even lighting, no text, no letters, no logos"]
    return ". ".join(x for x in partes if x)


def lacunas(p):
    """[(gravidade, codigo, texto)] do que falta para a prancha servir de referência."""
    out = []
    if not p["ficha"] and all(v["status"] == "ausente" for v in p["vistas"].values()):
        out.append(("grave", "personagem_sem_referencia", f"{p['character_id']}: sem ficha nem vistas — gere a prancha antes dos takes"))
    elif any(v["status"] == "ausente" for v in p["vistas"].values()):
        falta = [k for k, v in p["vistas"].items() if v["status"] == "ausente"]
        out.append(("media", "vistas_faltando", f"{p['character_id']}: faltam vistas {', '.join(falta)}"))
    if p["ficha"] and p["ficha"].get("existe") is False:
        out.append(("grave", "referencia_ausente_no_disco", f"{p['character_id']}: ficha {p['ficha']['arquivo']} não existe"))
    if not p["figurino_padrao"]:
        out.append(("media", "figurino_indefinido", f"{p['character_id']}: figurino não definido na bíblia"))
    if not p["proporcoes"] and not p["escala"]:
        out.append(("leve", "escala_indefinida", f"{p['character_id']}: sem proporções/altura de referência"))
    return out
