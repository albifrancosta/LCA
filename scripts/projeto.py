"""Configuração ÚNICA do projeto (projeto.json na raiz do projeto) + orçamento por projeto + decisões registradas uma vez.

Tudo o que os outros scripts precisam saber sobre o projeto sai daqui (antes estava espalhado entre BRIEFING.md,
roteiro.json, config/roteamento.json e argumentos de linha de comando):
  duracao     {segundos, frames, fps, tolerancia_pct}   — frames = round(segundos × fps), sempre coerentes
  formato     "16:9" | "9:16" | "1:1"
  autonomia   {modo: custo_zero | economico | teto, job_id}
              custo_zero → NENHUMA chamada paga (geração, voz, trilha, análise multimodal, upload); só local/grátis
              economico  → política lowest_cost, teto obrigatório, preço desconhecido bloqueia
              teto       → política best_value até o teto autorizado
  qualidade   {nota_minima, bloqueios_objetivos: [...], exigir_evidencia: true}
  orcamento   {moeda, teto_autorizado, saldo_provedor: {prov: valor|null}, saldo_desde, custo_desconhecido_ate,
               licencas_confirmadas: [ids de provedores cujos termos o usuário confirmou NO CHAT para este uso]}
              gasto confirmado / reservas / cobranças desconhecidas NÃO ficam aqui: são calculados do livro
              (memoria/reservas.json, filtrado pelo job do projeto) — `projeto.py orcamento` mostra os cinco números
  prazo       {entrega: "AAAA-MM-DD", minutos_por_plano}
  limites     {max_refacoes_plano, max_gasto_plano, max_minutos_plano}
  uso         "publicidade" | "interno" — publicidade exige licença comercial confirmada no provedor
  imagens     {nativa: true|false} — o ambiente gera imagem nativamente? (senão: roteador, dentro do orçamento)

Decisões (entrega/decisoes.json): cada decisão tem uma CHAVE; registrar a mesma chave de novo não duplica a mensagem.
Divergência de duração: resolvida pelo briefing aprovado + contexto (registrada uma vez, não pergunta de novo).

Uso:
  python projeto.py iniciar <pasta> [--modo custo_zero|economico|teto] [--teto 22] [--job id]  → cria projeto.json
  python projeto.py mostrar <pasta>
  python projeto.py orcamento <pasta>          → teto · saldo no provedor · confirmado · reservado · desconhecido · livre
  python projeto.py duracao <pasta> [--video entrega/x.mp4]   → resolve/registra a divergência de duração
  python projeto.py avaliar <pasta> --nota 8 --fonte usuario --texto "…"  → nota EDITORIAL (≠ métricas de audiência)
"""
import argparse
import datetime
import io
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

ARQ = "projeto.json"
MODOS = ("custo_zero", "economico", "teto")
POLITICA_DO_MODO = {"custo_zero": "free_first", "economico": "lowest_cost", "teto": "pontuacao"}
BLOQUEIOS_PADRAO = ["membros_extras", "figurino_involuntario", "interface_traseira", "texto_simbolo_gerado",
                    "falha_visual_evidente", "identidade_diferente", "congelamento_nao_intencional"]
PADRAO = {
    "versao": 1,
    "duracao": {"segundos": None, "frames": None, "fps": 30, "tolerancia_pct": 5},
    "formato": "16:9",
    "autonomia": {"modo": "custo_zero", "job_id": None},
    "qualidade": {"nota_minima": 85, "bloqueios_objetivos": BLOQUEIOS_PADRAO, "exigir_evidencia": True, "piso_final": None},
    "orcamento": {"moeda": "USD", "teto_autorizado": 0.0, "saldo_provedor": {}, "saldo_desde": None, "custo_desconhecido_ate": None,
                  "licencas_confirmadas": []},
    "prazo": {"entrega": None, "minutos_por_plano": 30},
    "limites": {"max_refacoes_plano": 2, "max_gasto_plano": 2.0, "max_minutos_plano": 30},
    "uso": "publicidade",
    "imagens": {"nativa": False},
}


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def raiz(pasta):
    """Pasta do projeto a partir de qualquer arquivo/pasta dentro dele (sobe até achar projeto.json)."""
    p = os.path.abspath(pasta)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    q = p
    for _ in range(4):
        if os.path.exists(os.path.join(q, ARQ)):
            return q
        q = os.path.dirname(q)
    return p


def _mescla(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _mescla(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def coerente(cfg):
    """Garante segundos ↔ frames ↔ fps coerentes e modo válido. Devolve lista de problemas (vazia = ok)."""
    d, prob = cfg["duracao"], []
    fps = float(d.get("fps") or 30)
    if d.get("segundos") is not None and d.get("frames") is None:
        d["frames"] = int(round(float(d["segundos"]) * fps))
    elif d.get("frames") is not None and d.get("segundos") is None:
        d["segundos"] = round(int(d["frames"]) / fps, 3)
    elif d.get("frames") is not None and abs(int(d["frames"]) - float(d["segundos"]) * fps) > 1:
        prob.append(f"duração incoerente: {d['segundos']} s × {fps} fps ≠ {d['frames']} frames")
    if cfg["autonomia"].get("modo") not in MODOS:
        prob.append(f"modo de autonomia inválido: {cfg['autonomia'].get('modo')} (use {', '.join(MODOS)})")
    o = cfg["orcamento"]
    if cfg["autonomia"].get("modo") in ("economico", "teto") and not float(o.get("teto_autorizado") or 0):
        prob.append(f"modo {cfg['autonomia']['modo']} sem teto_autorizado")
    return prob


def carregar(pasta, exigir=False):
    base = raiz(pasta)
    arq = os.path.join(base, ARQ)
    if not os.path.exists(arq):
        if exigir:
            sys.exit(f"{arq} não existe — rode `projeto.py iniciar {base}`")
        cfg = _mescla(PADRAO, inferir(base))
    else:
        cfg = _mescla(PADRAO, json.load(io.open(arq, encoding="utf-8")))
    cfg["_base"] = base
    cfg["_existe"] = os.path.exists(arq)
    cfg["_problemas"] = coerente(cfg)
    return cfg


def inferir(base):
    """Valores iniciais a partir do BRIEFING.md/roteiro.json (nada é pago, nada é perguntado)."""
    out = {"duracao": {}, "autonomia": {}}
    rot = os.path.join(base, "roteiro.json")
    if os.path.exists(rot):
        d = json.load(io.open(rot, encoding="utf-8"))
        if d.get("formato"):
            out["formato"] = d["formato"]
    br = os.path.join(base, "BRIEFING.md")
    if os.path.exists(br):
        txt = io.open(br, encoding="utf-8").read()
        m = re.search(r"\|\s*Dura[cç][aã]o\s*\|\s*(\d+(?:[.,]\d+)?)\s*s", txt, re.I)
        if m:
            out["duracao"]["segundos"] = float(m.group(1).replace(",", "."))
        m = re.search(r"(\d{2,3})\s*fps", txt, re.I)
        if m:
            out["duracao"]["fps"] = int(m.group(1))
    out["autonomia"]["job_id"] = os.path.basename(base)
    return out


def gravar(base, cfg):
    limpo = {k: v for k, v in cfg.items() if not k.startswith("_")}
    ig.gravar_json_atomico(os.path.join(base, ARQ), limpo)


def politica(cfg):
    return POLITICA_DO_MODO[cfg["autonomia"]["modo"]]


def permite_pago(cfg):
    return cfg["autonomia"]["modo"] != "custo_zero"


def job_id(cfg):
    return cfg["autonomia"].get("job_id") or os.path.basename(cfg["_base"])


# ---------------------------------------------------------------- orçamento (cinco números, sem inventar cobrança)
def livro(cfg, reservas_arq=None):
    """Lê memoria/reservas.json (o livro do roteador) filtrando o job do projeto (e sub-jobs 'job:algo').
    confirmado  = reconciliada com custo real informado pelo provedor
    desconhecido= reconciliada SEM custo real (conta pelo valor reservado — desconhecido nunca é zero)
    reservado   = ainda aberta (job em andamento, ou órfã: conferir no provedor antes de liberar)
    liberado    = não cobrada (erro antes do envio, credencial, payload…) — não entra no gasto."""
    import provedores
    arq = reservas_arq or provedores.caminhos()["reservas"]
    rs = provedores.ler(arq, {"reservas": []}).get("reservas", [])
    j = job_id(cfg)
    meus = [r for r in rs if r.get("job_id") == j or str(r.get("job_id", "")).startswith(j + ":")]
    out = {"confirmado": 0.0, "desconhecido": 0.0, "reservado": 0.0, "liberado": 0.0, "n": len(meus), "orfas": [], "por_categoria": {}}
    for r in meus:
        cat = r.get("categoria") or "geracao"
        if r["estado"] == "reconciliada":
            k = "confirmado" if r.get("custo_confirmado") and r.get("real") is not None else "desconhecido"
            v = float(r["real"] if k == "confirmado" else r["valor"])
        elif r["estado"] == "reservada":
            k, v = "reservado", float(r["valor"])
            out["orfas"].append({"id": r["id"], "scene_id": r.get("scene_id"), "provedor": r.get("provedor"), "valor": v,
                                 "quando": r.get("quando")})
        else:
            k, v = "liberado", float(r["valor"])
        out[k] = round(out[k] + v, 4)
        if k != "liberado":
            out["por_categoria"][cat] = round(out["por_categoria"].get(cat, 0) + v, 4)
    return out


def orcamento(cfg, reservas_arq=None):
    o = cfg["orcamento"]
    lv = livro(cfg, reservas_arq)
    teto = float(o.get("teto_autorizado") or 0)
    comprometido = lv["confirmado"] + lv["desconhecido"] + lv["reservado"]
    return {"moeda": o.get("moeda", "USD"), "teto_autorizado": teto, "saldo_provedor": o.get("saldo_provedor") or {},
            "gasto_confirmado": lv["confirmado"], "cobrancas_desconhecidas": lv["desconhecido"], "reservas_abertas": lv["reservado"],
            "comprometido": round(comprometido, 4), "livre": round(max(0.0, teto - comprometido), 4),
            "orfas": lv["orfas"], "por_categoria": lv["por_categoria"], "modo": cfg["autonomia"]["modo"]}


def custos_legados(base):
    """custos.json antigo (custos.py) — mostrado à parte como 'registrado (estimado pelo catálogo)'; nunca somado ao
    livro do roteador (as mesmas chamadas aparecem nos dois) e nunca promovido a 'confirmado'."""
    arq = os.path.join(base, "custos.json")
    if not os.path.exists(arq):
        return None
    d = json.load(io.open(arq, encoding="utf-8"))
    tot = sum(float(x.get("valor_usd") or 0) for x in d if not x.get("cache"))
    return {"n": len(d), "total_estimado": round(tot, 3)}


# ---------------------------------------------------------------- decisões registradas uma vez
def decisoes_arq(base):
    return os.path.join(base, "entrega", "decisoes.json")


def decidir(base, chave, texto, dados=None):
    """Registra a decisão `chave` UMA vez. Devolve (decisao, nova). Chamar de novo com a mesma chave não repete."""
    res = {}

    def f(d):
        ds = d.setdefault("decisoes", {})
        if chave in ds:
            res.update(dec=ds[chave], nova=False)
            return
        ds[chave] = {"texto": texto, "dados": dados or {}, "quando": agora()}
        res.update(dec=ds[chave], nova=True)
    ig.atualizar_json(decisoes_arq(base), f, padrao={"decisoes": {}})
    return res["dec"], res["nova"]


def resolver_duracao(cfg, duracao_real=None):
    """Compara a duração alvo (projeto/briefing) com a real (render ou soma do roteiro). Dentro da tolerância: ok.
    Fora: decide pelo briefing aprovado (o alvo manda; o roteiro/edição é que se ajusta) e registra uma vez."""
    base, d = cfg["_base"], cfg["duracao"]
    alvo = d.get("segundos")
    if alvo is None:
        return {"estado": "sem_alvo", "texto": "projeto sem duração alvo — preencha projeto.json"}
    if duracao_real is None:
        rot = os.path.join(base, "roteiro.json")
        if os.path.exists(rot):
            ps = json.load(io.open(rot, encoding="utf-8")).get("planos", [])
            duracao_real = sum(float((p.get("direcao") or {}).get("duracao") or p.get("dur_alvo") or 0) for p in ps) or None
    if duracao_real is None:
        return {"estado": "sem_medida", "alvo": alvo}
    desvio = (duracao_real - float(alvo)) / float(alvo) * 100
    tol = float(d.get("tolerancia_pct") or 5)
    if abs(desvio) < 0.5:
        return {"estado": "dentro", "alvo": alvo, "medida": duracao_real, "desvio_pct": round(desvio, 2)}
    estado = "aceita_na_tolerancia" if abs(desvio) <= tol else "fora"
    chave = f"duracao:{alvo}:{round(duracao_real, 1)}"
    texto = (f"Duração alvo {alvo:.1f} s (briefing aprovado) × medida {duracao_real:.1f} s ({desvio:+.1f} %). "
             + (f"Dentro da tolerância de ±{tol:.0f} %: aceita com ressalva; a próxima versão mira o alvo." if estado != "fora" else
                "Fora da tolerância: o briefing manda — cortar respiros/planos de apoio até caber; não regenerar clipe para isso."))
    dec, nova = decidir(base, chave, texto, {"alvo": alvo, "medida": duracao_real, "desvio_pct": round(desvio, 2), "estado": estado})
    return {"estado": estado, "alvo": alvo, "medida": duracao_real, "desvio_pct": round(desvio, 2), "decisao": dec["texto"], "nova": nova}


def avaliar(base, nota, fonte, texto):
    """Nota EDITORIAL (quem assistiu: usuário/diretor) — arquivo próprio, separado de métricas de audiência (metricas.py)."""
    arq = os.path.join(base, "entrega", "avaliacao-editorial.json")

    def f(d):
        d.setdefault("avaliacoes", []).append({"nota": nota, "escala": 10, "fonte": fonte, "texto": texto, "quando": agora(),
                                               "tipo": "editorial", "_nao_e": "métrica de audiência (essas ficam em metricas.json)"})
    return ig.atualizar_json(arq, f, padrao={"avaliacoes": []})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["iniciar", "mostrar", "orcamento", "duracao", "avaliar"])
    ap.add_argument("pasta")
    ap.add_argument("--modo", choices=MODOS)
    ap.add_argument("--teto", type=float)
    ap.add_argument("--job")
    ap.add_argument("--video")
    ap.add_argument("--nota", type=float)
    ap.add_argument("--fonte", default="usuario")
    ap.add_argument("--texto", default="")
    a = ap.parse_args()
    cfg = carregar(a.pasta)
    base = cfg["_base"]
    if a.acao == "iniciar":
        if cfg["_existe"]:
            print(f"{os.path.join(base, ARQ)} já existe — mantido (edite o arquivo para mudar)")
            return
        if a.modo:
            cfg["autonomia"]["modo"] = a.modo
        if a.teto is not None:
            cfg["orcamento"]["teto_autorizado"] = a.teto
        if a.job:
            cfg["autonomia"]["job_id"] = a.job
        prob = coerente(cfg)
        gravar(base, cfg)
        print(f"{os.path.join(base, ARQ)} gravado" + (f" — ATENÇÃO: {'; '.join(prob)}" if prob else ""))
    elif a.acao == "mostrar":
        print(json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")}, ensure_ascii=False, indent=1))
        if cfg["_problemas"]:
            print("PROBLEMAS: " + "; ".join(cfg["_problemas"]))
    elif a.acao == "orcamento":
        print(json.dumps(orcamento(cfg), ensure_ascii=False, indent=1))
        leg = custos_legados(base)
        if leg:
            print(f"(custos.json legado: {leg['n']} registros, US$ {leg['total_estimado']:.2f} ESTIMADOS pelo catálogo — não somados)")
    elif a.acao == "duracao":
        real = None
        if a.video:
            s = ig.sonda(a.video if os.path.isabs(a.video) else os.path.join(base, a.video))
            real = s and s["duracao"]
        print(json.dumps(resolver_duracao(cfg, real), ensure_ascii=False, indent=1))
    elif a.acao == "avaliar":
        if a.nota is None:
            sys.exit("--nota é obrigatório")
        avaliar(base, a.nota, a.fonte, a.texto)
        print("avaliação editorial registrada em entrega/avaliacao-editorial.json")


if __name__ == "__main__":
    main()
