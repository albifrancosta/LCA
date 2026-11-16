"""Estado da produção por hashes e dependências (entrega/estado-producao.json) — uma alteração invalida SÓ o que depende dela.

Estados (em ordem): planejado → gerado → inspecionado → corrigido_no_codigo → renderizado → verificado_no_render
  planejado            existe no roteiro, sem arquivo
  gerado               arquivo existe (íntegro), sem inspeção válida para ESTE conteúdo
  inspecionado         inspeção aprovada do mesmo sha256
  corrigido_no_codigo  defeito resolvido na composição (overlay/máscara/corte/recomposição) — entrega/correcoes.json
  renderizado          entra num render cujo retrato de dependências bate com o atual
  verificado_no_render o render foi inspecionado (inspetor filme + montagem) com o mesmo sha256

Nós e dependências (cada nó guarda o hash de cada dependência no momento em que chegou ao estado):
  texto:<id>    fala + o_que do plano              contrato:<id>  direcao do plano
  ref:<pers>    ficha/referência do elenco          img:<id>       ← texto, contrato, ref:* de quem
  voz:<id>      ← texto                             clipe:<id>     ← img, contrato, (voz se fala em quadro)
  composicao    remotion/src/* (manifesto + código) render         ← composicao, audio_final, clipe:*, voz:*
Retomar = `sincronizar`: recalcula hashes, rebaixa só os nós cujo conteúdo ou dependência mudou e diz o motivo.

Uso:
  python estado_producao.py sincronizar <projeto> [--video entrega/x.mp4]
  python estado_producao.py render <projeto> --video entrega/x.mp4 [--registrar] [--verificado]
"""
import argparse
import datetime
import glob
import io
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

ORDEM = ["planejado", "gerado", "inspecionado", "corrigido_no_codigo", "renderizado", "verificado_no_render"]


from integridade import relativo as _rel  # noqa: E402  (relpath seguro entre discos)


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def arq_estado(base):
    return os.path.join(base, "entrega", "estado-producao.json")


def _h_arq(arq):
    return ig.sha256(arq) if arq and os.path.isfile(arq) and os.path.getsize(arq) else None


def _h_obj(o):
    return ig.sha256_texto(json.dumps(o, sort_keys=True, ensure_ascii=False, default=str))


def nos_atuais(base, d):
    """{no: {"hash", "deps": [nós], "arquivo"}} do projeto como está agora."""
    nos = {}
    for q, f in (d.get("elenco") or {}).items():
        ref = os.path.join(base, f["ref"]) if f.get("ref") else None
        nos[f"ref:{q}"] = {"hash": _h_obj({"arq": _h_arq(ref), "ficha": {k: v for k, v in f.items() if k != "ref"}}), "deps": [], "arquivo": ref}
    for p in d.get("planos", []):
        pid, c = p["id"], p.get("direcao") or {}
        nos[f"texto:{pid}"] = {"hash": _h_obj({"fala": p.get("fala"), "o_que": p.get("o_que")}), "deps": []}
        nos[f"contrato:{pid}"] = {"hash": _h_obj(c), "deps": []}
        quem = c.get("quem") or p.get("quem") or []
        img = os.path.join(base, "assets", "img", f"{pid}.png")
        nos[f"img:{pid}"] = {"hash": _h_arq(img), "arquivo": img,
                             "deps": [f"texto:{pid}", f"contrato:{pid}"] + [f"ref:{q}" for q in quem if f"ref:{q}" in nos]}
        if p.get("fala"):
            voz = os.path.join(base, "assets", "voz", f"{pid}.wav")
            nos[f"voz:{pid}"] = {"hash": _h_arq(voz), "arquivo": voz, "deps": [f"texto:{pid}"]}
        if c.get("modo") in ig.MODOS_ANIMADOS:
            clip = os.path.join(base, "assets", "clips", f"{pid}.mp4")
            deps = [f"img:{pid}", f"contrato:{pid}"] + ([f"voz:{pid}"] if c.get("voz") == "em_quadro" and p.get("fala") else [])
            nos[f"clipe:{pid}"] = {"hash": _h_arq(clip), "arquivo": clip, "deps": deps}
    src = sorted(x for x in glob.glob(os.path.join(base, "remotion", "src", "*")) if os.path.isfile(x))
    nos["composicao"] = {"hash": ig.sha256_texto(*[f"{os.path.basename(x)}:{_h_arq(x)}" for x in src]) if src else None, "deps": []}
    pub = sorted(glob.glob(os.path.join(base, "remotion", "public", "**", "*.*"), recursive=True))
    nos["audio_final"] = {"hash": ig.sha256_texto(*[_h_arq(x) for x in pub if x.endswith(".wav")]) if pub else None, "deps": []}
    nos["midia_publica"] = {"hash": ig.sha256_texto(*[f"{_rel(x, base)}:{_h_arq(x)}" for x in pub
                                                      if x.endswith((".mp4", ".png", ".jpg"))]) if pub else None, "deps": []}
    nos["render"] = {"hash": None, "deps": ["composicao", "audio_final", "midia_publica"] + [k for k in nos if k.startswith(("clipe:", "voz:"))]}
    return nos


def _ler(base):
    try:
        return json.load(io.open(arq_estado(base), encoding="utf-8"))
    except (OSError, ValueError):
        return {"nos": {}, "renders": {}}


def _insp_ok(base, pid, h):
    try:
        it = next(i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8"))["itens"] if i["id"] == pid)
    except (OSError, ValueError, StopIteration, KeyError):
        return False
    return it.get("estado") == ig.APROVADO and it.get("sha256_clipe") == h


def _corrigido(base, pid, h):
    try:
        cs = json.load(io.open(os.path.join(base, "entrega", "correcoes.json"), encoding="utf-8")).get("correcoes", [])
    except (OSError, ValueError):
        return None
    return next((c for c in cs if c.get("plano") == pid and c.get("sha256_clipe") == h and c.get("estado") == "aplicada"), None)


def sincronizar(base, d=None, video=None, gravar=True):
    """Recalcula e devolve {"nos": {no: {estado, hash, motivo}}, "invalidados": [...], "render": {...}}."""
    if d is None:
        d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    atual = nos_atuais(base, d)
    antes = _ler(base)
    velhos = antes.get("nos", {})
    out, invalidados = {}, []
    for no, n in atual.items():
        if no == "render":
            continue
        v = velhos.get(no) or {}
        mudou = []
        if v.get("hash") and v["hash"] != n["hash"]:
            mudou.append("conteúdo mudou")
        for dep in n["deps"]:
            hd = (atual.get(dep) or {}).get("hash")
            if (v.get("deps") or {}).get(dep) not in (None, hd):
                mudou.append(f"{dep} mudou")
        tipo = no.split(":")[0]
        estado = "planejado" if n["hash"] is None else "gerado"
        if tipo == "clipe" and n["hash"]:
            pid = no.split(":", 1)[1]
            contrato_mudou = any(m.startswith("contrato:") or m.startswith("img:") for m in mudou)
            if _insp_ok(base, pid, n["hash"]) and not contrato_mudou:
                estado = "inspecionado"
            if _corrigido(base, pid, n["hash"]) and not contrato_mudou:
                estado = "corrigido_no_codigo"
        if mudou and v.get("estado") in ORDEM and ORDEM.index(v["estado"]) > ORDEM.index(estado):
            invalidados.append({"no": no, "de": v["estado"], "para": estado, "motivo": "; ".join(mudou)})
        out[no] = {"estado": estado, "hash": n["hash"], "deps": {dep: (atual.get(dep) or {}).get("hash") for dep in n["deps"]},
                   "motivo": "; ".join(mudou) or None,
                   "quando": v.get("quando") if (not mudou and v.get("estado") == estado) else agora()}
    rend = None
    if video:
        rend = render_atual(base, video, atual=atual, registro=antes)
        if rend["estado"] == "atual":
            for no in out:
                if no.startswith(("clipe:", "voz:")) and out[no]["estado"] != "planejado":
                    out[no]["estado"] = "verificado_no_render" if rend.get("verificado") else "renderizado"
    if gravar:
        ig.gravar_json_atomico(arq_estado(base), {"nos": out, "renders": antes.get("renders", {}), "atualizado": agora(),
                                                 "invalidados_ultima": invalidados})
    return {"nos": out, "invalidados": invalidados, "render": rend}


def retrato(atual):
    return {dep: (atual.get(dep) or {}).get("hash") for dep in atual["render"]["deps"]}


def registrar_render(base, video, d=None, verificado=False):
    if d is None:
        d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    atual = nos_atuais(base, d)
    reg = _ler(base)
    reg.setdefault("renders", {})[_rel(os.path.abspath(video), base).replace("\\", "/")] = {
        "sha256": ig.sha256(video), "deps": retrato(atual), "quando": agora(), "verificado": verificado}
    ig.gravar_json_atomico(arq_estado(base), reg)
    return reg


def render_atual(base, video, atual=None, registro=None, d=None):
    """{"estado": atual|desatualizado|desconhecido, "mudou": [...], "verificado"}. Render desatualizado = algum clipe, voz,
    trilha, mídia pública ou código da composição mudou DEPOIS do render (ou o próprio mp4 foi trocado)."""
    if atual is None:
        if d is None:
            d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
        atual = nos_atuais(base, d)
    registro = registro or _ler(base)
    r = (registro.get("renders") or {}).get(_rel(os.path.abspath(video), base).replace("\\", "/"))
    if not r:
        return {"estado": "desconhecido", "mudou": ["render sem retrato registrado (rode `estado_producao.py render --registrar`)"]}
    if not os.path.isfile(video) or ig.sha256(video) != r["sha256"]:
        return {"estado": "desatualizado", "mudou": ["o arquivo do render mudou depois do registro"]}
    agora_ = retrato(atual)
    mudou = sorted(k for k in set(agora_) | set(r["deps"]) if agora_.get(k) != r["deps"].get(k))
    return {"estado": "desatualizado" if mudou else "atual", "mudou": mudou, "verificado": r.get("verificado", False)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["sincronizar", "render"])
    ap.add_argument("projeto")
    ap.add_argument("--video")
    ap.add_argument("--registrar", action="store_true")
    ap.add_argument("--verificado", action="store_true")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    video = a.video and (a.video if os.path.isabs(a.video) else os.path.join(base, a.video))
    if a.acao == "render":
        if not video:
            sys.exit("render precisa de --video")
        if a.registrar:
            registrar_render(base, video, verificado=a.verificado)
            print("retrato do render registrado")
        print(json.dumps(render_atual(base, video), ensure_ascii=False, indent=1))
        return
    r = sincronizar(base, video=video)
    cont = {}
    for n in r["nos"].values():
        cont[n["estado"]] = cont.get(n["estado"], 0) + 1
    print("estados:", json.dumps(cont, ensure_ascii=False))
    for i in r["invalidados"]:
        print(f"  ↓ {i['no']}: {i['de']} → {i['para']} ({i['motivo']})")
    if r["render"]:
        print("render:", json.dumps(r["render"], ensure_ascii=False))


if __name__ == "__main__":
    main()
