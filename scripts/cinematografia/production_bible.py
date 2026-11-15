"""AI Film Production Bible — consolida a pré-produção visual do projeto em `<projeto>/production_bible/`.

Fonte única: a bíblia de produção existente (`producao.json`, scripts/producao.py). Esta camada é DERIVADA: atribui
IDs estáveis (char_*, env_*, prop_*), versiona as referências por sha256, sincroniza as tomadas com a narração,
planeja câmera, registra objetos/continuidade e gera o storyboard. Reconstruir preserva aprovação (se nada mudou),
substituições manuais de referência e o histórico de versões.

Uso (na pasta do projeto ou com --projeto):
  python production_bible.py construir [--entrada outro.json] [--modo supervisionado|automatico]
  python production_bible.py validar            → erros de estrutura (IDs, tempos, caminhos)
  python production_bible.py status             → resumo + estado da aprovação
  python production_bible.py custos             → estimativa por produção (referências, análise, clipes) — só estimativa
  python production_bible.py referencia char_tiago frontal assets/tiago-frente.png   → substituição manual (humano)
  python production_bible.py aprovar --nota "ok do usuário no chat"   → libera a produção (modo supervisionado)
Depois: board_generator.py (pranchas HTML/PNG/PDF) e supervisor_continuidade.py pre (checagem antes de gerar).
"""
import argparse
import datetime
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import integridade as ig  # noqa: E402
from cinematografia import PASTA  # noqa: E402
from cinematografia import character_reference as cref  # noqa: E402
from cinematografia import environment_reference as eref  # noqa: E402
from cinematografia import props_registry as preg  # noqa: E402
from cinematografia import shot_planner as sp  # noqa: E402
from cinematografia import storyboard_visual as sbv  # noqa: E402

SCHEMA = "production_bible/1"
MODOS = ("supervisionado", "automatico")
DUR_PADRAO = 3.0
ID_RX = re.compile(r"^(char|env|prop)_[a-z0-9][a-z0-9-]*$")


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def slug(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def pasta(base):
    return os.path.join(base, PASTA)


def arq_bible(base):
    return os.path.join(pasta(base), "bible.json")


def carregar(base):
    a = arq_bible(base)
    return json.load(open(a, encoding="utf-8")) if os.path.exists(a) else None


def fonte_arq(base, entrada=None):
    a = entrada or os.path.join(base, "producao.json")
    return a if os.path.isabs(a) else os.path.join(base, a)


def _rel(base, caminho):
    if not caminho:
        return None
    absoluto = caminho if os.path.isabs(caminho) else os.path.join(base, caminho)
    try:
        return os.path.relpath(absoluto, base).replace("\\", "/")
    except ValueError:  # outro disco no Windows: mantém absoluto
        return absoluto.replace("\\", "/")


class Referencias:
    """Registra referências com versão: mesma entidade+origem com sha diferente do build anterior → versão +1."""

    def __init__(self, base, anterior):
        self.base, self.ant = base, anterior or {}
        self.novo = {}

    def __call__(self, entidade):
        def ref_de(caminho, origem):
            rel = _rel(self.base, caminho)
            absoluto = rel if os.path.isabs(rel) else os.path.join(self.base, rel)
            existe = os.path.exists(absoluto)
            sha = ig.sha256(absoluto) if existe and os.path.isfile(absoluto) else None
            chave = f"{entidade}:{origem}"
            prev = self.ant.get(chave) or {}
            versao = prev.get("versao", 0)
            mudou = not prev or prev.get("sha256") != sha or prev.get("arquivo") != rel
            if mudou:
                versao += 1
            hist = list(prev.get("historico") or [])
            if prev and mudou:
                hist.append({"versao": prev["versao"], "arquivo": prev["arquivo"], "sha256": prev.get("sha256")})
            r = {"arquivo": rel, "sha256": sha, "versao": versao, "origem": origem, "existe": existe, "historico": hist}
            self.novo[chave] = {k: r[k] for k in ("arquivo", "sha256", "versao", "historico")}
            return r
        return ref_de


def _timeline(base):
    a = os.path.join(base, "falas-timeline.json")
    if not os.path.exists(a):
        return {}
    tl = json.load(open(a, encoding="utf-8"))
    return {x["id"]: x for x in tl if "id" in x and "inicio" in x}


def tempos(base, tomadas):
    """(inicio, fim, fonte) por tomada: explícito na tomada → narração (falas-timeline.json) → duração acumulada."""
    tl = _timeline(base)
    ids_tl = sorted(tl, key=lambda k: tl[k]["inicio"])
    out, cursor = {}, 0.0
    for t in tomadas:
        dur = (t.get("direcao") or {}).get("duracao") or (t.get("decupagem") or {}).get("duracao") or t.get("duracao")
        if t.get("inicio") is not None and t.get("fim") is not None:
            ini, fim, fonte = float(t["inicio"]), float(t["fim"]), "tomada"
        elif (t.get("fala_id") or t["id"]) in tl:
            k = t.get("fala_id") or t["id"]
            ini = float(tl[k]["inicio"])
            if tl[k].get("fim") is not None:
                fim = float(tl[k]["fim"])
            else:
                i = ids_tl.index(k)
                fim = float(tl[ids_tl[i + 1]]["inicio"]) if i + 1 < len(ids_tl) else ini + float(dur or DUR_PADRAO)
            fonte = "narracao"
        else:
            ini, fim, fonte = cursor, cursor + float(dur or DUR_PADRAO), "duracao" if dur else "padrao"
        out[t["id"]] = (round(ini, 3), round(fim, 3), fonte)
        cursor = fim
    return out


def _sem_volateis(o):
    if isinstance(o, dict):
        return {k: _sem_volateis(v) for k, v in o.items() if k not in ("existe", "historico", "status_producao")}
    if isinstance(o, list):
        return [_sem_volateis(v) for v in o]
    return o


def _hash_conteudo(b):
    nucleo = {k: b.get(k) for k in ("personagens", "cenarios", "objetos", "tomadas", "planos", "substituicoes")}
    return ig.sha256_texto(json.dumps(_sem_volateis(nucleo), ensure_ascii=False, sort_keys=True, default=str))


def construir(base, entrada=None, modo=None, gravar=True):
    base = os.path.abspath(base)
    fa = fonte_arq(base, entrada)
    if not os.path.exists(fa):
        raise FileNotFoundError(f"fonte da bíblia não encontrada: {fa} (rode producao.py iniciar ou passe --entrada)")
    d = json.load(open(fa, encoding="utf-8"))
    ant = carregar(base) or {}
    refs = Referencias(base, ant.get("_refs"))
    subst = ant.get("substituicoes") or {}
    estilo = d.get("estilo", "")
    tomadas = list(d.get("tomadas") or [])
    pers_src = d.get("personagens") or {}
    cid = {k: f"char_{slug(k)}" for k in pers_src}
    eid = {k: f"env_{slug(k)}" for k in d.get("cenarios") or {}}
    pid = {k: f"prop_{slug(k)}" for k in d.get("objetos") or {}}
    nomes = {k: v.get("nome", k) for k, v in pers_src.items()}

    planos = sp.planejar_todas(tomadas)
    chars = {}
    for k, src in pers_src.items():
        src = dict(src)
        for vista, arq in (subst.get(cid[k]) or {}).items():  # substituição manual vence a fonte
            if vista == "ficha":
                src["ficha"] = arq
            else:
                src["vistas"] = {**(src.get("vistas") or {}), vista: arq}
        chars[cid[k]] = cref.montar(cid[k], k, src, tomadas, refs(cid[k]), estilo)
    envs = {}
    for k, src in (d.get("cenarios") or {}).items():
        src = dict(src)
        if (subst.get(eid[k]) or {}).get("cenario"):
            src["ref"] = subst[eid[k]]["cenario"]
        envs[eid[k]] = eref.montar(eid[k], k, src, tomadas, planos, refs(eid[k]), estilo)
    props = preg.construir(tomadas, d.get("objetos") or {}, nomes, pid)
    for p in props.values():
        r = (subst.get(p["prop_id"]) or {}).get("ref") or p["ref"]
        p["ref"] = refs(p["prop_id"])(r, "ref") if r else None

    tem = tempos(base, tomadas)
    cenas, tomadas_b = [], []
    for t in tomadas:
        cena = t.get("cena") or t.get("cenario") or "cena"
        if not cenas or cenas[-1][0] != cena:
            cenas.append((cena, 0))
        cenas[-1] = (cena, cenas[-1][1] + 1)
        ini, fim, fonte = tem[t["id"]]
        tomadas_b.append({
            "take_id": t["id"], "cena": cena, "cena_num": len(cenas), "take_num": cenas[-1][1],
            "inicio": ini, "fim": fim, "duracao": round(fim - ini, 3), "tempo_fonte": fonte,
            "characters": [cid[p] for p in t.get("personagens") or [] if p in cid],
            "environment_id": eid.get(t.get("cenario")),
            "props": [pid[o] for o in t.get("objetos") or [] if o in pid],
            "props_estado": {pid[o]: e for o, e in (t.get("objetos_estado") or {}).items() if o in pid},
            "figurino": {cid[p]: cref.figurino_da_tomada(p, pers_src[p], t) for p in t.get("personagens") or [] if p in cid},
            "horario": t.get("horario") or (d.get("cenarios") or {}).get(t.get("cenario"), {}).get("horario"),
            "estado_emocional": t.get("emocao") or (t.get("direcao") or {}).get("emocao"),
            "acao": t.get("acao", ""), "narracao": t.get("fala") or t.get("narracao") or "",
            "status_producao": t.get("status"),
        })
    fontes = {t["id"]: t for t in tomadas}
    storyboard = sbv.montar(tomadas_b, fontes, planos, chars, envs, props)
    contradicoes = preg.checar(tomadas, d.get("objetos") or {}, nomes,
                               lambda p, t: cref.figurino_da_tomada(p, pers_src.get(p, {}), t))
    contradicoes += sp.checar_eixo(tomadas, planos)

    b = {
        "schema": SCHEMA, "gerado_em": agora(), "titulo": d.get("titulo", ""), "estilo": estilo, "formato": d.get("formato", "9:16"),
        "fonte": {"arquivo": _rel(base, fa), "sha256": ig.sha256(fa)},
        "modo_aprovacao": modo or ant.get("modo_aprovacao") or "supervisionado",
        "personagens": chars, "cenarios": envs, "objetos": props, "tomadas": tomadas_b, "planos": planos,
        "storyboard": storyboard,
        "continuidade": [{"gravidade": g, "codigo": c, "texto": x} for g, c, x in contradicoes],
        "duracao_total": round(max([x["fim"] for x in tomadas_b] or [0.0]), 3),
        "substituicoes": subst, "_refs": refs.novo,
    }
    b["hash"] = _hash_conteudo(b)
    ap = ant.get("aprovacao") or {}
    if ap.get("estado") in ("aprovada", "automatica") and ap.get("hash") == b["hash"]:
        b["aprovacao"] = ap
    else:
        b["aprovacao"] = {"estado": "pendente", "hash": b["hash"],
                          "motivo": "bíblia mudou desde a aprovação" if ap.get("estado") in ("aprovada", "automatica") else "ainda não aprovada"}
    b["custos_estimados"] = estimar_custos(b)
    if gravar:
        salvar(base, b)
    return b


def salvar(base, b):
    p = pasta(base)
    ig.gravar_json_atomico(arq_bible(base), b)
    for sub, itens in (("characters", b["personagens"]), ("environments", b["cenarios"]), ("props", b["objetos"])):
        os.makedirs(os.path.join(p, sub), exist_ok=True)
        for k, v in itens.items():
            ig.gravar_json_atomico(os.path.join(p, sub, f"{k}.json"), v)
    for sub, nome, dados in (("storyboards", "storyboard.json", b["storyboard"]),
                             ("shot_lists", "shot_list.json", [{"take_id": t, **pl} for t, pl in b["planos"].items()]),
                             ("continuity", "registro.json", {"objetos": {k: v["aparicoes"] for k, v in b["objetos"].items()},
                                                              "figurino": {t["take_id"]: t["figurino"] for t in b["tomadas"]},
                                                              "contradicoes_planejamento": b["continuidade"]})):
        os.makedirs(os.path.join(p, sub), exist_ok=True)
        ig.gravar_json_atomico(os.path.join(p, sub, nome), dados)


def validar(b):
    """Erros de estrutura (lista vazia = válida)."""
    erros = []
    if b.get("schema") != SCHEMA:
        erros.append(f"schema {b.get('schema')} ≠ {SCHEMA}")
    for grupo, chave in (("personagens", "character_id"), ("cenarios", "environment_id"), ("objetos", "prop_id")):
        for k, v in (b.get(grupo) or {}).items():
            if k != v.get(chave) or not ID_RX.match(k):
                erros.append(f"{grupo}: ID inválido {k}")
    vistos = set()
    for t in b.get("tomadas") or []:
        if t["take_id"] in vistos:
            erros.append(f"take duplicado {t['take_id']}")
        vistos.add(t["take_id"])
        if not (t["fim"] > t["inicio"] >= 0):
            erros.append(f"{t['take_id']}: tempo inválido {t['inicio']}–{t['fim']}")
        erros += [f"{t['take_id']}: personagem {c} fora da bíblia" for c in t["characters"] if c not in b["personagens"]]
        if t.get("environment_id") and t["environment_id"] not in b["cenarios"]:
            erros.append(f"{t['take_id']}: cenário {t['environment_id']} fora da bíblia")
        erros += [f"{t['take_id']}: objeto {p} fora da bíblia" for p in t["props"] if p not in b["objetos"]]
    tks = b.get("tomadas") or []
    for a, c in zip(tks, tks[1:]):
        if c["inicio"] + 1e-3 < a["inicio"]:
            erros.append(f"{c['take_id']} começa antes de {a['take_id']} (ordem temporal)")

    def caminhos(o):
        if isinstance(o, dict):
            if isinstance(o.get("arquivo"), str) and re.match(r"^[A-Za-z]:[\\/]|^/", o["arquivo"]):
                erros.append(f"caminho absoluto na bíblia: {o['arquivo']} (use relativo ao projeto)")
            for v in o.values():
                caminhos(v)
        elif isinstance(o, list):
            for v in o:
                caminhos(v)
    caminhos({k: b.get(k) for k in ("personagens", "cenarios", "objetos", "storyboard")})
    return erros


def estimar_custos(b):
    """Estimativa (NUNCA cobrança real) do que falta gerar. Preços do catálogo/config da skill; desconhecido = None."""
    try:
        import gerar_imagem
        p_img = gerar_imagem.PRECO_ESTIMADO["medium"]
    except Exception:  # noqa: BLE001
        p_img = None
    try:
        import qa_visual
        p_ana = sum(qa_visual.estimar_analise(t["duracao"]) or 0 for t in b["tomadas"])
    except Exception:  # noqa: BLE001
        p_ana = None
    pranchas_p = sum(1 for c in b["personagens"].values() if not c["ficha"])
    pranchas_e = sum(1 for e in b["cenarios"].values() if not e["visao_geral"])
    keyframes = sum(1 for s in b["storyboard"] if not s["imagem"] or s["imagem"]["fonte"] == "referência do cenário")
    n_img = pranchas_p + pranchas_e + keyframes
    clipes, desconhecido = 0.0, []
    try:
        import roteador
        for t in b["tomadas"]:
            if t["characters"]:
                dec, _ = roteador.escolher(tipo="video", duracao=max(3, round(t["duracao"])), cena="personagem", registrar=False)
                if dec.get("custo") is None:
                    desconhecido.append(t["take_id"])
                else:
                    clipes += float(dec["custo"])
    except Exception as e:  # noqa: BLE001
        desconhecido.append(f"roteador indisponível: {e}"[:120])
    imagens = round(n_img * p_img, 3) if p_img is not None else None
    total = round(sum(x for x in (imagens, p_ana, clipes) if x), 3)
    return {"tipo": "estimativa", "imagens_a_gerar": n_img, "pranchas_personagem": pranchas_p, "pranchas_cenario": pranchas_e,
            "keyframes": keyframes, "imagens_usd": imagens, "analise_visual_usd": round(p_ana, 4) if p_ana is not None else None,
            "clipes_usd": round(clipes, 3), "clipes_preco_desconhecido": desconhecido, "total_estimado_usd": total,
            "nota": "custo real só vem do livro do roteador (memoria/reservas.json); isto é planejamento"}


def aprovar(base, nota, modo=None, automatico=False):
    b = carregar(base)
    if not b:
        raise FileNotFoundError("bíblia não construída — rode `production_bible.py construir`")
    if modo:
        b["modo_aprovacao"] = modo
    b["aprovacao"] = {"estado": "automatica" if automatico else "aprovada", "hash": b["hash"], "quando": agora(), "nota": nota}
    ig.gravar_json_atomico(arq_bible(base), b)
    return b


def portao(base, d_producao=None):
    """Portão para o orquestrador: None se o projeto não usa a bíblia visual (comportamento antigo intacto); senão
    {"liberado": bool, "motivo": str, "tarefa": str|None}. Produção paga só segue com a prancha aprovada (supervisionado)
    ou validada tecnicamente pelo supervisor (automático)."""
    b = carregar(base)
    if b is None and not (d_producao or {}).get("biblia_visual"):
        return None
    if b is None:
        return {"liberado": False, "motivo": "bíblia visual ativada e ainda não construída", "tarefa": "construir_biblia"}
    ok = b["aprovacao"]["estado"] in ("aprovada", "automatica") and b["aprovacao"].get("hash") == b["hash"]
    fa = b["fonte"]["arquivo"] if os.path.isabs(b["fonte"]["arquivo"]) else os.path.join(base, b["fonte"]["arquivo"])
    if os.path.exists(fa) and ig.sha256(fa) != b["fonte"]["sha256"]:
        # versões/status de tomada também mudam o arquivo: reconstruir é barato e mantém a aprovação se o conteúdo é o mesmo
        return {"liberado": ok, "motivo": "producao.json mudou — reconstrua a bíblia", "tarefa": "construir_biblia"}
    if ok:
        return {"liberado": True, "motivo": f"prancha {b['aprovacao']['estado']}", "tarefa": None}
    if b["modo_aprovacao"] == "automatico":
        return {"liberado": False, "motivo": "modo automático: rode supervisor_continuidade.py pre (aprova se não houver grave)",
                "tarefa": "pre_producao"}
    return {"liberado": False, "motivo": "modo supervisionado: envie a prancha (boards/overview.png) e aprove no chat",
            "tarefa": "aprovar_prancha"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projeto", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("construir"); s.add_argument("--entrada"); s.add_argument("--modo", choices=MODOS)
    sub.add_parser("validar"); sub.add_parser("status"); sub.add_parser("custos")
    s = sub.add_parser("referencia"); s.add_argument("entidade"); s.add_argument("vista"); s.add_argument("arquivo")
    s = sub.add_parser("aprovar"); s.add_argument("--nota", required=True); s.add_argument("--modo", choices=MODOS)
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    if a.cmd == "construir":
        b = construir(base, a.entrada, a.modo)
        erros = validar(b)
        print(f"bíblia: {len(b['personagens'])} personagens · {len(b['cenarios'])} cenários · {len(b['objetos'])} objetos · "
              f"{len(b['tomadas'])} takes · {b['duracao_total']} s · aprovação {b['aprovacao']['estado']}")
        print(f"  {arq_bible(base)}")
        for c in b["continuidade"]:
            print(f"  [{c['gravidade']}] {c['texto']}")
        for e in erros:
            print(f"  ERRO: {e}")
        sys.exit(1 if erros else 0)
    b = carregar(base)
    if b is None:
        sys.exit("bíblia não construída — rode `production_bible.py construir`")
    if a.cmd == "validar":
        erros = validar(b)
        print("\n".join(erros) or "bíblia válida")
        sys.exit(1 if erros else 0)
    if a.cmd == "status":
        print(f"{b['titulo']} — {len(b['tomadas'])} takes, {b['duracao_total']} s, modo {b['modo_aprovacao']}, aprovação {b['aprovacao']['estado']}")
        print(json.dumps(portao(base), ensure_ascii=False))
    elif a.cmd == "custos":
        print(json.dumps(b["custos_estimados"], ensure_ascii=False, indent=1))
    elif a.cmd == "referencia":
        b.setdefault("substituicoes", {}).setdefault(a.entidade, {})[a.vista] = _rel(base, a.arquivo)
        ig.gravar_json_atomico(arq_bible(base), b)
        b = construir(base)
        print(f"{a.entidade}.{a.vista} → {a.arquivo} (manual); aprovação agora: {b['aprovacao']['estado']}")
    elif a.cmd == "aprovar":
        b = aprovar(base, a.nota, a.modo)
        print(f"prancha aprovada ({b['hash'][:12]}) — produção liberada")


if __name__ == "__main__":
    main()
