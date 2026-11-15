"""Props & Continuity Bible — prop_id para cada objeto importante, em quais tomadas aparece e em que ESTADO.

Estado por tomada vem de `tomada.objetos_estado = {objeto: "na mão de tiago" | "sobre a mesa" | "guardado" …}`;
sem declaração vale "em cena". Também acompanha figurino e horário dentro da mesma cena, para o supervisor de
continuidade apontar o que aparece/some entre cortes sem justificativa narrativa.
"""
import re

SOLTA = re.compile(r"\b(solta|larga|guarda|entrega|deixa|joga|coloca|p[õo]e|devolve|esconde|cai|perde|passa para)\b", re.I)
SEGURA = re.compile(r"\b(m[ãa]o|m[ãa]os|segura|segurando|carrega|carregando|empunha)\b", re.I)


def segurado_por(estado, nomes):
    """Quem segura o objeto, deduzido do texto do estado ('na mão de Tiago') — None se ninguém."""
    if not estado or not SEGURA.search(estado):
        return None
    e = estado.lower()
    for pid, nome in nomes.items():
        if pid.lower() in e or (nome and nome.lower() in e):
            return pid
    return "alguem"


def construir(tomadas, objetos_src, nomes, ids):
    """`nomes`: {personagem_origem: nome}; `ids`: {objeto_origem: prop_id}."""
    reg = {}
    for oid, o in (objetos_src or {}).items():
        reg[ids[oid]] = {"prop_id": ids[oid], "origem_id": oid, "descricao": o.get("descricao", oid), "ref": o.get("ref"),
                         "estado_inicial": o.get("estado"), "aparicoes": []}
    for t in tomadas:
        estados = t.get("objetos_estado") or {}
        for oid in t.get("objetos") or []:
            if oid not in ids:
                continue
            est = estados.get(oid) or "em cena"
            reg[ids[oid]]["aparicoes"].append({"tomada": t["id"], "estado": est, "segurado_por": segurado_por(est, nomes)})
    return reg


def checar(tomadas, objetos_src, nomes, figurino_de):
    """Contradições entre tomadas seguidas da MESMA cena. `figurino_de(personagem, tomada)` → dict do figurino."""
    out = []
    for a, b in zip(tomadas, tomadas[1:]):
        if (a.get("cena") or a.get("cenario")) != (b.get("cena") or b.get("cenario")):
            continue
        justificado = bool(b.get("justificativa_continuidade")) or bool(SOLTA.search(a.get("acao") or "")) \
            or bool(SOLTA.search(b.get("acao") or ""))
        ea, eb = a.get("objetos_estado") or {}, b.get("objetos_estado") or {}
        for oid in a.get("objetos") or []:
            quem = segurado_por(ea.get(oid) or "", nomes)
            if not quem:
                continue
            presente_b = quem == "alguem" or quem in (b.get("personagens") or [])
            if oid not in (b.get("objetos") or []) and presente_b and not justificado:
                out.append(("media", "objeto_sumiu", f"{a['id']}→{b['id']}: '{(objetos_src.get(oid) or {}).get('descricao', oid)}' estava "
                                                     f"{ea[oid]} e some no corte seguinte sem justificativa narrativa"))
            elif (oid in (b.get("objetos") or []) and eb.get(oid) and quem != "alguem" and quem in (b.get("personagens") or [])
                  and segurado_por(eb[oid], nomes) is None and not justificado):
                out.append(("leve", "objeto_mudou_estado", f"{a['id']}→{b['id']}: '{oid}' saiu da mão de {quem} ({eb[oid]}) sem ação que explique"))
        for pid in sorted(set(a.get("personagens") or []) & set(b.get("personagens") or [])):
            fa, fb = figurino_de(pid, a), figurino_de(pid, b)
            if fa != fb and not justificado:
                dif = sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))
                out.append(("grave", "figurino_mudou_na_cena", f"{a['id']}→{b['id']}: figurino de {nomes.get(pid, pid)} muda dentro da cena "
                                                               f"({', '.join(dif)})"))
        if a.get("horario") and b.get("horario") and a["horario"] != b["horario"] and not justificado:
            out.append(("media", "horario_mudou_na_cena", f"{a['id']}→{b['id']}: horário {a['horario']}→{b['horario']} na mesma cena"))
    for t in tomadas:
        et = t.get("objetos_estado") or {}
        for oid in t.get("objetos") or []:
            quem = segurado_por(et.get(oid) or "", nomes)
            if quem and quem != "alguem" and quem not in (t.get("personagens") or []):
                out.append(("media", "objeto_sem_portador", f"{t['id']}: '{oid}' {et[oid]}, mas {nomes.get(quem, quem)} não está na tomada"))
    return out
