"""Catálogo local ESTRUTURADO de ativos reutilizáveis (memoria/acervo.json) — `memoria/biblioteca.md` continua como
resumo legível (a seção entre os marcadores ACERVO é regenerada; o resto do arquivo, escrito à mão, fica intacto).

Cataloga: imagem, clipe, referencia, roteiro, prompt, audio, voz, cenario, objeto, musica, componente, tecnica.
Cada item: id, tipo, sha256, caminho (validado na hora do uso), modelo, parametros, versao, custo_usd, origem (projeto),
licenca, qualidade (aprovado | aprovado_com_excecao | reprovado | nao_verificado), restricoes, usos[], tags, descricao.
Regras:
  - busca LOCAL antes de chamar API (`buscar`); o resultado separa `reuso_direto` (aprovado, sem ressalva, arquivo íntegro)
    de `referencia` (inspiração/ref visual — não entra no filme como está);
  - clipe reprovado NUNCA vira ativo aprovado: fica como `referencia_negativa` (o que não repetir);
  - exceção do diretor é `aprovado_com_excecao`, com a ressalva nas restrições (não é aprovação limpa).

Uso:
  python acervo.py indexar <projeto>                 → cataloga os ativos do projeto (idempotente por sha256)
  python acervo.py buscar "marcos sorrindo notebook" [--tipo clipe] [--para uso|referencia]
  python acervo.py usar <id> --projeto <pasta> --plano c05a   → registra o uso (e confere sha/caminho)
  python acervo.py resumo                            → regenera a seção do biblioteca.md
  python acervo.py adicionar --tipo tecnica --descricao "…" [--origem …] [--licenca …] [--tags a,b] [--arquivo …]
"""
import argparse
import datetime
import glob
import io
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

ARQ = os.path.join(SKILL, "memoria", "acervo.json")
BIB = os.path.join(SKILL, "memoria", "biblioteca.md")
TIPOS = ("imagem", "clipe", "referencia", "roteiro", "prompt", "audio", "voz", "cenario", "objeto", "musica", "componente", "tecnica")
INI, FIM = "<!-- ACERVO:INICIO (gerado por acervo.py resumo — não edite aqui) -->", "<!-- ACERVO:FIM -->"


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def ler(arq=None):
    try:
        return json.load(io.open(arq or ARQ, encoding="utf-8"))
    except (OSError, ValueError):
        return {"versao": 1, "itens": {}}


def _meta(arq):
    try:
        return json.load(io.open(arq + ".json", encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _qa_clipes(base):
    """{pid: (estado, sha)} da inspeção + decisões do diretor (viram aprovado_com_excecao, nunca aprovado limpo)."""
    out = {}
    try:
        for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8")).get("itens", []):
            est = i.get("estado")
            if est == ig.APROVADO and (i.get("excecao_diretor") or i.get("veredito") == "aprovado_com_excecao"):
                est = "aprovado_com_excecao"
            out[i["id"]] = (est, i.get("sha256_clipe"))
    except (OSError, ValueError):
        pass
    try:
        for x in json.load(io.open(os.path.join(base, "entrega", "decisoes-diretor.json"), encoding="utf-8")).get("decisoes", []):
            if x.get("take") and x.get("sha256"):
                out[x["take"]] = ("aprovado_com_excecao", x["sha256"])
    except (OSError, ValueError):
        pass
    return out


def _item(tipo, arq, base, **k):
    sha = ig.sha256(arq)
    return dict({"id": f"{tipo}:{sha[:12]}", "tipo": tipo, "sha256": sha, "caminho": os.path.abspath(arq),
                 "origem": os.path.basename(base), "licenca": None, "qualidade": ig.NAO_VERIFICADO, "restricoes": [],
                 "usos": [], "tags": [], "modelo": None, "parametros": {}, "versao": sha[:8], "custo_usd": None, "descricao": ""}, **k)


def indexar(base, arq_acervo=None):
    """Cataloga o projeto. Mesmo sha = mesmo item (atualiza qualidade, não duplica; reprovado nunca sobe sozinho)."""
    base = os.path.abspath(base)
    d = {}
    rot = os.path.join(base, "roteiro.json")
    if os.path.exists(rot):
        d = json.load(io.open(rot, encoding="utf-8"))
    planos = {p["id"]: p for p in d.get("planos", [])}
    qa = _qa_clipes(base)
    lic = "uso no projeto de origem; reuso em publicidade exige licença comercial do provedor confirmada"
    novos = []
    clipes = sorted(glob.glob(os.path.join(base, "assets", "clips", "*.mp4")) + glob.glob(os.path.join(base, "assets", "clips", "rejeitados", "*.mp4")))
    for arq in clipes:
        pid = re.sub(r"(-t\d+|-v\d+.*|-reprovado.*|-split.*)$", "", os.path.splitext(os.path.basename(arq))[0])
        m = _meta(arq)
        p = planos.get(pid, {})
        sha = ig.sha256(arq)
        est, sha_qa = qa.get(pid, (ig.NAO_VERIFICADO, None))
        if "rejeitados" in arq or "reprovado" in os.path.basename(arq):
            qual = ig.REPROVADO
        elif sha_qa == sha:
            qual = est
        else:
            qual = ig.NAO_VERIFICADO  # a inspeção era de outro arquivo
        restr = ["reprovado: só como referência negativa (o que não repetir)"] if qual == ig.REPROVADO else []
        if qual == "aprovado_com_excecao":
            restr.append("aprovado por exceção do diretor (ver decisoes-diretor.json) — não é aprovação limpa")
        novos.append(_item("clipe", arq, base, modelo=m.get("modelo") or m.get("model"), custo_usd=m.get("custo_usd") or m.get("custo"),
                           parametros={k: m.get(k) for k in ("duracao", "prompt", "seed", "request_id") if m.get(k) is not None},
                           qualidade=qual, restricoes=restr, licenca=lic,
                           descricao=(p.get("o_que") or "")[:200], tags=list((p.get("direcao") or {}).get("quem") or p.get("quem") or []) + [pid]))
    for arq in sorted(glob.glob(os.path.join(base, "assets", "img", "*.png"))):
        pid = os.path.splitext(os.path.basename(arq))[0]
        p = planos.get(pid, {})
        novos.append(_item("imagem", arq, base, descricao=(p.get("o_que") or "")[:200], licenca=lic,
                           parametros={"prompt": (p.get("prompts") or [""])[0][:300]}, tags=list(p.get("quem") or []) + [pid]))
    for q, f in (d.get("elenco") or {}).items():
        ref = os.path.join(base, f.get("ref", ""))
        if f.get("ref") and os.path.isfile(ref):
            novos.append(_item("referencia", ref, base, descricao=f"ficha de {q}: " + "; ".join((f.get("figurino") or []) + (f.get("tracos") or [])),
                               qualidade=ig.APROVADO, tags=[q, "ficha"], licenca=lic))
    for arq in sorted(glob.glob(os.path.join(base, "assets", "voz", "*.wav"))):
        pid = os.path.splitext(os.path.basename(arq))[0]
        p = planos.get(pid, {})
        novos.append(_item("voz", arq, base, descricao=(p.get("fala") or "")[:200], tags=[p.get("voz_de") or "", pid], licenca=lic))
    for arq in sorted(glob.glob(os.path.join(base, "assets", "trilha*.wav"))):
        m = _meta(arq)
        novos.append(_item("musica", arq, base, modelo=m.get("modelo"), custo_usd=m.get("custo_usd"), tags=["trilha"], licenca=lic,
                           descricao=json.dumps(d.get("trilha_clima") or {}, ensure_ascii=False)[:200]))
    if os.path.exists(rot):
        novos.append(_item("roteiro", rot, base, descricao=d.get("titulo") or "", qualidade=ig.APROVADO, tags=["roteiro", d.get("formato") or ""]))
    for arq in sorted(glob.glob(os.path.join(base, "remotion", "src", "*.tsx"))):
        novos.append(_item("componente", arq, base, descricao=f"composição Remotion {os.path.basename(arq)}", tags=["remotion"], qualidade=ig.APROVADO))
    pr = os.path.join(base, "entrega", "prompts-imagens.md")
    if os.path.exists(pr):
        novos.append(_item("prompt", pr, base, descricao="prompts das imagens-chave", tags=["prompts"]))

    def f(cat):
        its = cat.setdefault("itens", {})
        for n in novos:
            velho = its.get(n["id"])
            if velho:
                n["usos"] = velho.get("usos", [])
                if velho.get("qualidade") == ig.REPROVADO:  # reprovado nunca sobe sozinho
                    n["qualidade"] = ig.REPROVADO
                    n["restricoes"] = velho.get("restricoes") or n["restricoes"]
            n["atualizado"] = agora()
            its[n["id"]] = n
    ig.atualizar_json(arq_acervo or ARQ, f, padrao={"versao": 1, "itens": {}})
    return novos


def _tokens(s):
    return {w for w in re.findall(r"\w+", (s or "").lower()) if len(w) > 2}


def buscar(texto, tipo=None, para=None, arq_acervo=None, limite=10):
    """{"reuso_direto": [...], "referencia": [...]}. Caminho/sha conferidos agora: arquivo sumido ou trocado sai do reuso."""
    q = _tokens(texto)
    res = []
    for it in ler(arq_acervo).get("itens", {}).values():
        if tipo and it["tipo"] != tipo:
            continue
        alvo = _tokens(" ".join([it.get("descricao") or "", " ".join(it.get("tags") or []), it.get("tipo"), json.dumps(it.get("parametros") or {}, ensure_ascii=False)]))
        score = len(q & alvo) / (len(q) or 1)
        if score > 0:
            res.append((score, it))
    res.sort(key=lambda x: -x[0])
    direto, ref = [], []
    for score, it in res[: limite * 3]:
        integro = bool(it.get("caminho")) and os.path.isfile(it["caminho"]) and ig.sha256(it["caminho"]) == it["sha256"]
        x = dict(it, score=round(score, 2), integro=integro)
        if it["qualidade"] == ig.APROVADO and integro and not it.get("restricoes"):
            direto.append(x)
        else:
            ref.append(dict(x, uso="referencia_negativa" if it["qualidade"] == ig.REPROVADO else "referencia"))
    return {"reuso_direto": direto[:limite], "referencia": [] if para == "uso" else ref[:limite]}


def usar(id_, projeto, plano, arq_acervo=None):
    res = {}

    def f(cat):
        it = cat.get("itens", {}).get(id_)
        if not it:
            raise SystemExit(f"{id_} não está no acervo")
        if it["qualidade"] == ig.REPROVADO:
            raise SystemExit(f"{id_} é reprovado — só serve como referência negativa, não como ativo")
        if not it.get("caminho") or not os.path.isfile(it["caminho"]) or ig.sha256(it["caminho"]) != it["sha256"]:
            raise SystemExit(f"{id_}: arquivo sumiu ou mudou ({it.get('caminho')}) — reindexe a origem")
        it.setdefault("usos", []).append({"projeto": os.path.basename(os.path.abspath(projeto)), "plano": plano, "quando": agora()})
        res.update(it)
    ig.atualizar_json(arq_acervo or ARQ, f, padrao={"versao": 1, "itens": {}})
    return res


def adicionar(tipo, descricao, origem="", licenca=None, tags=(), arquivo=None, arq_acervo=None, **extra):
    if tipo not in TIPOS:
        raise SystemExit(f"tipo inválido: {tipo} (use {', '.join(TIPOS)})")
    sha = ig.sha256(arquivo) if arquivo else ig.sha256_texto(tipo, descricao, origem)
    it = {"id": f"{tipo}:{sha[:12]}", "tipo": tipo, "sha256": sha, "caminho": os.path.abspath(arquivo) if arquivo else None,
          "origem": origem, "licenca": licenca, "qualidade": extra.pop("qualidade", ig.NAO_VERIFICADO),
          "restricoes": list(extra.pop("restricoes", [])), "usos": [], "tags": list(tags), "descricao": descricao, "atualizado": agora(), **extra}
    ig.atualizar_json(arq_acervo or ARQ, lambda cat: cat.setdefault("itens", {}).__setitem__(it["id"], it), padrao={"versao": 1, "itens": {}})
    return it


def resumo(arq_acervo=None, bib=None):
    cat = ler(arq_acervo)
    bib = bib or BIB
    por = {}
    for it in cat.get("itens", {}).values():
        por.setdefault(it["tipo"], []).append(it)
    marca = {ig.APROVADO: "✅", "aprovado_com_excecao": "⚠️", ig.NAO_VERIFICADO: "👁", ig.REPROVADO: "❌"}
    L = [INI, "", "## Acervo estruturado (resumo)", "", f"Atualizado {agora()} · {len(cat.get('itens', {}))} itens em `memoria/acervo.json` "
         "(busca: `acervo.py buscar \"…\"`). ✅ reuso direto · ⚠️ exceção/ressalva · 👁 não verificado · ❌ só referência negativa.", ""]
    for tipo in TIPOS:
        its = por.get(tipo) or []
        if its:
            cont = {}
            for it in its:
                cont[it["qualidade"]] = cont.get(it["qualidade"], 0) + 1
            L.append(f"- **{tipo}** ({len(its)}): " + " · ".join(f"{marca.get(k, k)} {v}" for k, v in sorted(cont.items())))
    L += ["", FIM]
    bloco = "\n".join(L)
    txt = io.open(bib, encoding="utf-8").read() if os.path.exists(bib) else "# Biblioteca\n"
    txt = re.sub(re.escape(INI) + r".*?" + re.escape(FIM), lambda _: bloco, txt, flags=re.S) if INI in txt else txt.rstrip() + "\n\n" + bloco + "\n"
    io.open(bib, "w", encoding="utf-8").write(txt)
    return bloco


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["indexar", "buscar", "usar", "resumo", "adicionar"])
    ap.add_argument("alvo", nargs="?")
    ap.add_argument("--tipo")
    ap.add_argument("--para", choices=["uso", "referencia"])
    ap.add_argument("--projeto")
    ap.add_argument("--plano")
    ap.add_argument("--descricao", default="")
    ap.add_argument("--origem", default="")
    ap.add_argument("--licenca")
    ap.add_argument("--tags", default="")
    ap.add_argument("--arquivo")
    a = ap.parse_args()
    if a.acao == "indexar":
        n = indexar(a.alvo)
        print(f"{len(n)} ativos catalogados de {a.alvo}")
        resumo()
    elif a.acao == "buscar":
        r = buscar(a.alvo or "", a.tipo, a.para)
        enx = lambda x: {k: x.get(k) for k in ("id", "tipo", "qualidade", "uso", "score", "integro", "caminho", "descricao", "restricoes")}  # noqa: E731
        print(json.dumps({k: [enx(x) for x in v] for k, v in r.items()}, ensure_ascii=False, indent=1, default=str))
    elif a.acao == "usar":
        it = usar(a.alvo, a.projeto, a.plano)
        print(f"uso registrado: {it['id']} → {a.projeto} {a.plano}")
    elif a.acao == "resumo":
        print(resumo())
    else:
        it = adicionar(a.tipo, a.descricao, a.origem, a.licenca, [t for t in a.tags.split(",") if t], a.arquivo)
        print(f"adicionado: {it['id']}")


if __name__ == "__main__":
    main()
