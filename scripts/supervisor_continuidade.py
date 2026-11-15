"""AI Continuity Supervisor — fiscaliza a produção contra a AI Film Production Bible (production_bible/bible.json).

Três etapas, reaproveitando o que a skill já tem (nada de chamada nova ao Gemini fora do caminho com cache e orçamento):
  1 ANTES   `pre`         — referências suficientes? contradições entre cenas (objeto que some, figurino que muda na
                            cena, eixo de 180°, horário)? tempos sem fonte? Modo automático: aprova a prancha se não há grave.
  2 DURANTE `inspecionar` — por take: mídia válida, duração vs. plano, CONGELAMENTO (qa_montagem.corridas) com o intervalo,
                            folha de quadros (evidência), análise visual (inspetor.analisar_visual: fichas reais, cache,
                            reserva de orçamento) julgada pelas regras objetivas de qa_visual (membros extras, figurino fora
                            da ficha, interface nas costas do aparelho, identidade, deformações), sincronia com a narração.
            `entre-takes` — objeto que estava na mão e some no corte seguinte sem justificativa.
  3 CORREÇÃO `corrigir`   — causa provável → estratégia → prompt de correção → regenera SÓ o trecho/take afetado →
                            reinspeciona → aprova ou manda para revisão humana. Limite de tentativas e orçamento de correção
                            (bible.correcao ou padrão), checagem de custo_zero e do saldo livre do projeto antes de qualquer gasto.
Sem análise visual (ou confiança baixa) o take fica NÃO VERIFICADO → revisão humana. Inspeção que "terminou sem erro"
não é aprovação.

Uso (na pasta do projeto):
  python supervisor_continuidade.py pre
  python supervisor_continuidade.py inspecionar t003 assets/clips/t003.mp4 [--visual] [--visual-json vis.json] [--narracao 3.1,6.0]
  python supervisor_continuidade.py entre-takes
  python supervisor_continuidade.py corrigir t003        → plano de correção (estratégia, prompt, custo, se cabe no orçamento)
  python supervisor_continuidade.py relatorio            → continuity/RELATORIO.md
"""
import argparse
import datetime
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402
import qa_visual as qv  # noqa: E402
from cinematografia import character_reference as cref  # noqa: E402
from cinematografia import environment_reference as eref  # noqa: E402
from cinematografia import production_bible as pb  # noqa: E402
from cinematografia import props_registry as preg  # noqa: E402

PADRAO_CORRECAO = {"max_tentativas": 2, "orcamento_correcao_usd": 1.0, "confianca_minima": 0.6,
                   "tolerancia_duracao_s": 0.5, "tolerancia_sincronia_s": 0.25, "congelamento_grave_s": 0.6}
GRAV = {"grave": 3, "media": 2, "leve": 1}

# código → (causa provável, estratégia, instrução de correção para o prompt)
CAUSAS = {
    "membros_extras": ("modelo de vídeo duplicou membros no movimento", "regerar_take",
                       "exactly two arms and two hands per person, anatomically correct, no extra limbs"),
    "maos_deformadas": ("mãos em movimento rápido", "regerar_take", "hands simple and readable, five fingers, slower hand motion"),
    "deformacao": ("instabilidade temporal do modelo", "regerar_take", "stable anatomy and objects through the whole shot"),
    "falha_visual_evidente": ("take corrompido", "regerar_take", "clean, stable, on-model animation"),
    "figurino_involuntario": ("o modelo inventou peça de roupa fora da ficha", "regerar_com_referencia",
                              "wardrobe exactly as the reference sheet: {figurino}; no {peca}"),
    "figurino_fora_da_ficha": ("peça fora da ficha", "regerar_com_referencia", "wardrobe exactly as the reference sheet: {figurino}"),
    "identidade_diferente": ("personagem derivou da ficha", "regerar_com_referencia", "same face and design as the character sheet {char}"),
    "interface_traseira": ("aparelho desenhado com a tela do lado errado", "refazer_imagem_chave",
                           "the device screen faces the user, back of the device plain with no interface; UI is composited later in code"),
    "texto_simbolo_gerado": ("o modelo desenhou texto/símbolo", "refazer_imagem_chave", "no text, no letters, no numbers, no symbols"),
    "oclusao": ("objeto atravessando corpo", "regerar_take", "objects never pass through bodies; correct occlusion"),
    "continuidade_temporal": ("objeto aparece/some dentro do take", "regerar_take", "props stay consistent from first to last frame: {props}"),
    "objeto_ausente": ("objeto da bíblia não aparece no take", "refazer_imagem_chave", "include {props} exactly as planned"),
    "objeto_sumiu_no_corte": ("objeto some entre takes", "refazer_imagem_chave", "the character still holds {props} as in the previous shot"),
    "congelamento": ("clipe mais curto que o plano / modelo travou", "regerar_trecho",
                     "continuous motion through the whole interval, no hold frames"),
    "duracao_divergente": ("duração gerada diferente da planejada", "ajustar_montagem", None),
    "dessincronia_audio": ("take fora do tempo da narração", "ajustar_montagem", None),
    "dessincronia_labial": ("boca fora do tempo da fala", "regerar_take", "lip movement synced to the dialogue audio"),
    "midia_invalida": ("arquivo corrompido ou vazio", "regerar_take", "same shot, valid render"),
}


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def pasta_cont(base):
    p = os.path.join(pb.pasta(base), "continuity")
    os.makedirs(os.path.join(p, "inspecoes"), exist_ok=True)
    return p


def log(base, take_id, evento, **dados):
    """Log de geração/inspeção/correção. Nunca recebe chave de API (só caminhos, códigos, custos)."""
    linha = {"quando": agora(), "take_id": take_id, "evento": evento, **dados}
    with open(os.path.join(pasta_cont(base), "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")


def cfg_correcao(b, base=None):
    """Padrão → limites do projeto.json (max_refacoes_plano, max_gasto_plano) → bible.correcao (mais específico vence)."""
    cfg = dict(PADRAO_CORRECAO)
    if base and os.path.exists(os.path.join(base, "projeto.json")):
        try:
            import projeto
            lim = projeto.carregar(base).get("limites") or {}
            if lim.get("max_refacoes_plano") is not None:
                cfg["max_tentativas"] = int(lim["max_refacoes_plano"])
            if lim.get("max_gasto_plano") is not None:
                cfg["orcamento_correcao_usd"] = float(lim["max_gasto_plano"])
        except Exception:  # noqa: BLE001
            pass
    return {**cfg, **(b.get("correcao") or {})}


def _take(b, tid):
    t = next((x for x in b["tomadas"] if x["take_id"] == tid), None)
    if not t:
        raise KeyError(f"take {tid} não está na bíblia")
    return t


def _prob(gravidade, codigo, texto, inicio=None, fim=None, evidencia=None):
    return {"gravidade": gravidade, "codigo": codigo, "texto": texto, "inicio": inicio, "fim": fim, "evidencia": evidencia}


# ------------------------------------------------------------------ etapa 1 — antes da geração
def pre_producao(base, b=None, aprovar_auto=True):
    b = b or pb.carregar(base)
    if b is None:
        raise FileNotFoundError("bíblia não construída — rode production_bible.py construir")
    probs = [_prob("grave", "estrutura", x) for x in pb.validar(b)]
    for c in b["personagens"].values():
        probs += [_prob(g, k, x) for g, k, x in cref.lacunas(c)]
    for e in b["cenarios"].values():
        probs += [_prob(g, k, x) for g, k, x in eref.lacunas(e)]
    probs += [_prob(c["gravidade"], c["codigo"], c["texto"]) for c in b["continuidade"]]
    for t in b["tomadas"]:
        if t["characters"] and not t.get("environment_id"):
            probs.append(_prob("media", "take_sem_cenario", f"{t['take_id']}: personagens sem cenário definido"))
        if t["tempo_fonte"] == "padrao":
            probs.append(_prob("media", "tempo_sem_fonte", f"{t['take_id']}: sem duração nem tempo da narração (usou {pb.DUR_PADRAO}s)"))
        if b["planos"][t["take_id"]]["enquadramento"] == "detalhe":
            probs += [_prob("leve", "objeto_em_detalhe_sem_ref", f"{t['take_id']}: {p} em plano detalhe sem imagem de referência")
                      for p in t["props"] if not b["objetos"][p].get("ref")]
    ok = not any(p["gravidade"] == "grave" for p in probs)
    res = {"quando": agora(), "bible_hash": b["hash"], "ok": ok, "problemas": sorted(probs, key=lambda p: -GRAV[p["gravidade"]])}
    ig.gravar_json_atomico(os.path.join(pasta_cont(base), "pre_producao.json"), res)
    log(base, None, "pre_producao", ok=ok, graves=sum(p["gravidade"] == "grave" for p in probs), total=len(probs))
    if ok and aprovar_auto and b["modo_aprovacao"] == "automatico" and b["aprovacao"]["estado"] != "aprovada":
        pb.aprovar(base, "validação técnica do supervisor (modo automático): sem problema grave", automatico=True)
        res["aprovacao"] = "automatica"
    return res


# ------------------------------------------------------------------ etapa 2 — durante a geração
def contrato_do_take(b, t):
    """(contrato no formato do qa_visual, elenco {origem_id: figurino/traços/ref}, nomes em quadro)."""
    nomes = [b["personagens"][c]["origem_id"] for c in t["characters"]]
    elenco = {}
    for c in t["characters"]:
        p = b["personagens"][c]
        elenco[p["origem_id"]] = {"figurino": [f"{k} {v}" for k, v in (t["figurino"].get(c) or {}).items()],
                                  "tracos": list(p["cabelo_acessorios"]), "ref": (p["ficha"] or {}).get("arquivo")}
    sb = next((s for s in b["storyboard"] if s["take_id"] == t["take_id"]), {})
    c = {"acao": t["acao"], "quem": nomes,
         "criterios": [f"objeto {b['objetos'][p]['descricao']}: {t['props_estado'].get(p, 'em cena')}" for p in t["props"]],
         "aparelho_tela_para": (b.get("aparelhos") or {}).get(t["take_id"]), "simbolos_permitidos": sb.get("efeitos") or []}
    return c, elenco, nomes


def _segundos(texto):
    m = re.search(r"\((\d+(?:\.\d+)?)s\)", texto or "")
    return float(m.group(1)) if m else None


def congelamentos(video, pausas=(), minimo=None):
    """Corridas de quadros parados fora das pausas planejadas: [(ini, fim, n_quadros)]."""
    import qa_montagem as qm
    quadros, fps = qm.ler_quadros(video)
    if len(quadros) < 3:
        return [], fps, len(quadros)
    runs = qm.corridas(qm.diferencas(quadros), fps, minimo=minimo or qm.MIN_CONGELADO_S)
    fora = [r for r in runs if not any(a - 0.05 <= r[0] and r[1] <= z + 0.05 for a, z in pausas)]
    return fora, fps, len(quadros)


def inspecionar_take(base, take_id, video, analisador=None, narracao=None, b=None, folha=True):
    """`analisador(video, contrato, elenco, nomes)` → dict no formato do qa_visual (anatomia, figurino, aparelhos…) ou None.
    `narracao` = (inicio, fim) reais da fala deste take no áudio final, para conferir sincronia."""
    b = b or pb.carregar(base)
    t = _take(b, take_id)
    cfg = cfg_correcao(b)
    video = video if os.path.isabs(video) else os.path.join(base, video)
    probs, ev, vis = [], None, None
    c, elenco, nomes = contrato_do_take(b, t)
    ok, motivo = ig.midia_valida(video, "video")
    if not ok:
        probs.append(_prob("grave", "midia_invalida", f"{take_id}: {motivo}"))
    else:
        dur = ig.sonda(video)["duracao"]
        if abs(dur - t["duracao"]) > max(cfg["tolerancia_duracao_s"], 0.15 * t["duracao"]):
            probs.append(_prob("media", "duracao_divergente", f"{take_id}: {dur:.2f}s gerados para {t['duracao']:.2f}s planejados", 0.0, dur))
        if folha:
            try:
                import inspetor
                ev = inspetor.folha(video, os.path.join(pasta_cont(base), "inspecoes", f"{take_id}-folha.jpg"))
                ev = os.path.relpath(ev, base).replace("\\", "/") if ev else None
            except Exception:  # noqa: BLE001 — a folha é evidência, não portão
                ev = None
        runs, _fps, _nq = congelamentos(video, [tuple(p) for p in (t.get("pausas") or [])])
        for a, z, n in runs:
            g = "grave" if z - a >= cfg["congelamento_grave_s"] else "media"
            probs.append(_prob(g, "congelamento", f"{take_id}: imagem congelada de {a:.2f}s a {z:.2f}s ({n} quadros)", a, z, ev))
        if narracao:
            off = max(abs(narracao[0] - t["inicio"]), abs(narracao[1] - t["fim"]))
            if off > cfg["tolerancia_sincronia_s"]:
                probs.append(_prob("media", "dessincronia_audio", f"{take_id}: narração {narracao[0]:.2f}–{narracao[1]:.2f}s vs. take "
                                                                 f"{t['inicio']:.2f}–{t['fim']:.2f}s (desvio {off:.2f}s)", narracao[0], narracao[1]))
        if analisador:
            vis = analisador(video, c, elenco, nomes)
        if vis and "indisponivel" not in vis:
            for g, cod, txt in qv.bloqueios(vis, c, elenco, nomes):
                probs.append(_prob(g, cod, f"{take_id}: {txt}", _segundos(txt), None, ev))
            if t["characters"] and vis.get("boca") == "fala_fora_de_tempo":
                probs.append(_prob("media", "dessincronia_labial", f"{take_id}: boca fora do tempo da fala", None, None, ev))
            vistos = vis.get("objetos_visiveis")
            if isinstance(vistos, list):
                ids_vistos = {str(o.get("objeto") if isinstance(o, dict) else o) for o in vistos}
                for p in t["props"]:
                    o = b["objetos"][p]
                    if not ids_vistos & {p, o["origem_id"], o["descricao"]}:
                        probs.append(_prob("media", "objeto_ausente", f"{take_id}: {p} ({o['descricao']}) previsto e não visto", None, None, ev))
    analisado = bool(vis) and "indisponivel" not in vis
    falta = qv.evidencia_faltando(vis, c, nomes) if analisado else ["análise visual" + (f" ({vis['indisponivel']})" if vis else "")]
    confianca = (vis or {}).get("confianca")
    baixa = isinstance(confianca, (int, float)) and confianca < cfg["confianca_minima"]
    if any(p["gravidade"] in ("grave", "media") for p in probs):
        estado = ig.REPROVADO
    elif falta or baixa:
        estado = ig.NAO_VERIFICADO
    else:
        estado = ig.APROVADO
    rel = {"take_id": take_id, "video": os.path.relpath(video, base).replace("\\", "/"), "sha256": ig.sha256(video) if ok else None,
           "estado": estado, "revisao_humana": estado == ig.NAO_VERIFICADO,
           "motivo_revisao": "; ".join(x for x in (("sem evidência: " + ", ".join(falta)) if falta else "",
                                                   f"confiança {confianca} < {cfg['confianca_minima']}" if baixa else "") if x),
           "problemas": sorted(probs, key=lambda p: -GRAV[p["gravidade"]]), "evidencia": ev,
           "visual": {k: v for k, v in vis.items() if not k.startswith("_")} if analisado else None, "quando": agora()}
    ig.gravar_json_atomico(os.path.join(pasta_cont(base), "inspecoes", f"{take_id}.json"), rel)
    log(base, take_id, "inspecao", estado=estado, problemas=[p["codigo"] for p in probs])
    return rel


def entre_takes(base, analises=None, b=None):
    """Objeto segurado no take A que some no take B (mesma cena, mesmo portador em quadro) sem justificativa.
    Usa o plano (bíblia) e, se houver, o que a análise viu (`objetos_visiveis` de cada inspeção)."""
    b = b or pb.carregar(base)
    if analises is None:
        analises = {}
        for t in b["tomadas"]:
            a = os.path.join(pasta_cont(base), "inspecoes", f"{t['take_id']}.json")
            if os.path.exists(a):
                analises[t["take_id"]] = json.load(open(a, encoding="utf-8")).get("visual") or {}
    nomes = {cid: c["nome"] for cid, c in b["personagens"].items()}
    out = [_prob(c["gravidade"], c["codigo"], c["texto"]) for c in b["continuidade"] if c["codigo"].startswith("objeto_")]
    for a, z in zip(b["tomadas"], b["tomadas"][1:]):
        if a["cena"] != z["cena"]:
            continue
        va, vz = analises.get(a["take_id"]) or {}, analises.get(z["take_id"]) or {}
        if not isinstance(va.get("objetos_visiveis"), list) or not isinstance(vz.get("objetos_visiveis"), list):
            continue
        vistos_z = {str(o.get("objeto")) for o in vz["objetos_visiveis"] if isinstance(o, dict)}
        justificado = bool(preg.SOLTA.search(a["acao"] or "")) or bool(preg.SOLTA.search(z["acao"] or ""))
        for o in va["objetos_visiveis"]:
            if not isinstance(o, dict) or not o.get("segurado_por"):
                continue
            quem = str(o["segurado_por"]).lower()
            portador = next((cid for cid, n in nomes.items() if n.lower() == quem or cid == quem or b["personagens"][cid]["origem_id"] == quem), None)
            if portador in z["characters"] and str(o.get("objeto")) not in vistos_z and not justificado:
                out.append(_prob("media", "objeto_sumiu_no_corte",
                                 f"{a['take_id']}→{z['take_id']}: {o['objeto']} estava na mão de {nomes[portador]} e some no corte "
                                 "sem justificativa narrativa", z["inicio"], z["inicio"]))
    res = {"quando": agora(), "problemas": out}
    ig.gravar_json_atomico(os.path.join(pasta_cont(base), "entre_takes.json"), res)
    log(base, None, "entre_takes", problemas=[p["codigo"] for p in out])
    return res


# ------------------------------------------------------------------ etapa 3 — correção localizada
def plano_correcao(b, rel):
    t = _take(b, rel["take_id"])
    relevantes = [p for p in rel["problemas"] if p["gravidade"] in ("grave", "media")]
    if not relevantes:
        return {"take_id": t["take_id"], "estrategia": "nenhuma", "problemas": [], "principal": None, "duracao": 0}
    principal = max(relevantes, key=lambda p: GRAV[p["gravidade"]])
    causa, estrategia, _ = CAUSAS.get(principal["codigo"], ("não mapeada", "revisao_humana", None))
    fig = "; ".join(f"{b['personagens'][c]['nome']}: " + ", ".join(f"{k} {v}" for k, v in f.items()) for c, f in t["figurino"].items())
    peca = re.search(r"'([^']+)'", principal["texto"])
    props = ", ".join(f"{b['objetos'][p]['descricao']} ({t['props_estado'].get(p, 'em cena')})" for p in t["props"]) or "the planned props"
    extras = []
    for p in relevantes:
        i = CAUSAS.get(p["codigo"], (None, None, None))[2]
        if i:
            extras.append(i.format(figurino=fig or "as reference", peca=peca.group(1) if peca else "extra garment",
                                   char=", ".join(t["characters"]), props=props))
    intervalo = None
    if estrategia == "regerar_trecho":
        cg = [p for p in relevantes if p["codigo"] == "congelamento"]
        intervalo = [round(max(0.0, min(p["inicio"] for p in cg) - 0.3), 3), round(max(p["fim"] for p in cg) + 0.3, 3)]
    pl = b["planos"][t["take_id"]]
    refs = next((s["referencias"] for s in b["storyboard"] if s["take_id"] == t["take_id"]), [])
    prompt = ". ".join(x for x in [t["acao"], f"camera: {pl['enquadramento']}, {pl['movimento']}", *dict.fromkeys(extras)] if x)
    return {"take_id": t["take_id"], "problemas": [p["codigo"] for p in relevantes], "principal": principal["codigo"],
            "causa_provavel": causa, "estrategia": estrategia, "intervalo": intervalo, "prompt_correcao": prompt,
            "referencias": refs, "duracao": round(intervalo[1] - intervalo[0], 3) if intervalo else t["duracao"]}


def estimar_correcao(plano, b):
    """(custo_usd | None, modelo, motivo). Ajuste de montagem é grátis; preço desconhecido = None (bloqueia gasto)."""
    est = plano["estrategia"]
    if est in ("ajustar_montagem", "nenhuma", "revisao_humana"):
        return 0.0, None, "sem geração"
    if est == "refazer_imagem_chave":
        try:
            import gerar_imagem
            return gerar_imagem.PRECO_ESTIMADO["medium"], "gerar_imagem", "imagem-chave + reinspeção"
        except Exception:  # noqa: BLE001
            return None, None, "preço de imagem desconhecido"
    try:
        import roteador
        caps = {"i2v", "identidade"} if est == "regerar_com_referencia" else None
        dec, _ = roteador.escolher(tipo="video", duracao=max(3, round(plano["duracao"])), cena="personagem", registrar=False,
                                   perfil="economico", capacidades=caps)
        return (float(dec["custo"]) if dec.get("custo") is not None else None), dec.get("modelo"), (dec.get("motivo") or "")[:160]
    except Exception as e:  # noqa: BLE001
        return None, None, f"roteador indisponível: {e}"[:160]


def _livre_projeto(base, custo):
    """None se pode gastar; senão o motivo do bloqueio (custo_zero ou sem saldo no teto do projeto)."""
    if custo <= 0:
        return None
    try:
        import projeto
        cfg = projeto.carregar(base)
    except Exception:  # noqa: BLE001
        return None
    if not cfg:
        return None
    if not projeto.permite_pago(cfg):
        return "projeto em modo custo_zero — regeneração paga bloqueada"
    livre = projeto.orcamento(cfg)["livre"]
    return None if custo <= livre + 1e-9 else f"sem saldo no projeto (livre US$ {livre:.3f} < US$ {custo:.3f})"


def corrigir(base, take_id, regenerar=None, analisador=None, narracao=None, b=None, rel=None, cfg=None, estimador=None):
    """Loop de correção de UM take. `regenerar(take_id, plano, tentativa)` → {"arquivo": caminho, "custo_real": float|None}
    ou None (falhou). Sem `regenerar`, devolve só o plano (o orquestrador entrega ao estudio-animacao/arte).
    `estimador(plano, b)` substitui estimar_correcao (testes)."""
    b = b or pb.carregar(base)
    cfg = {**cfg_correcao(b, base), **(cfg or {})}
    estimador = estimador or estimar_correcao
    if rel is None:
        rel = json.load(open(os.path.join(pasta_cont(base), "inspecoes", f"{take_id}.json"), encoding="utf-8"))
    hist, gasto_est, gasto_real = [], 0.0, 0.0
    if rel["estado"] == ig.APROVADO:
        return {"take_id": take_id, "estado": "aprovado", "tentativas": 0, "historico": []}
    if rel["estado"] == ig.NAO_VERIFICADO and not any(p["gravidade"] in ("grave", "media") for p in rel["problemas"]):
        return _fim(base, take_id, "revisao_humana", rel.get("motivo_revisao") or "sem evidência suficiente", hist, 0, 0)
    for tentativa in range(1, int(cfg["max_tentativas"]) + 1):
        plano = plano_correcao(b, rel)
        custo, modelo, motivo = estimador(plano, b)
        passo = {"tentativa": tentativa, "plano": plano, "custo_estimado_usd": custo, "modelo": modelo}
        log(base, take_id, "plano_correcao", estrategia=plano["estrategia"], problemas=plano["problemas"], custo_estimado_usd=custo, modelo=modelo)
        if plano["estrategia"] == "revisao_humana":
            hist.append(passo)
            return _fim(base, take_id, "revisao_humana", f"problema sem estratégia automática ({plano['principal']})", hist, gasto_est, gasto_real)
        if plano["estrategia"] == "ajustar_montagem":
            hist.append(passo)
            return _fim(base, take_id, "ajustar_na_montagem", "corrigir no código da montagem (corte/tempo), sem regerar", hist, gasto_est, gasto_real)
        if custo is None:
            hist.append(passo)
            return _fim(base, take_id, "revisao_humana", f"preço desconhecido — não gasto sem preço ({motivo})", hist, gasto_est, gasto_real)
        if gasto_est + custo > cfg["orcamento_correcao_usd"] + 1e-9:
            hist.append(passo)
            return _fim(base, take_id, "revisao_humana", f"orçamento de correção esgotado (US$ {gasto_est:.3f} + {custo:.3f} > "
                                                          f"{cfg['orcamento_correcao_usd']:.3f})", hist, gasto_est, gasto_real)
        bloq = _livre_projeto(base, custo)
        if bloq:
            hist.append(passo)
            return _fim(base, take_id, "bloqueado_orcamento", bloq, hist, gasto_est, gasto_real)
        if regenerar is None:
            hist.append(passo)
            return _fim(base, take_id, "aguardando_regeneracao", "plano pronto — regenerar só este take/trecho", hist, gasto_est, gasto_real)
        novo = regenerar(take_id, plano, tentativa)
        gasto_est += custo
        if not novo or not novo.get("arquivo"):
            passo["resultado"] = "falha_regeneracao"
            hist.append(passo)
            log(base, take_id, "regeneracao_falhou", tentativa=tentativa)
            continue
        if novo.get("custo_real") is not None:
            gasto_real += float(novo["custo_real"])
        log(base, take_id, "regenerado", tentativa=tentativa, arquivo=novo["arquivo"], custo_estimado_usd=custo,
            custo_real_usd=novo.get("custo_real"))
        antes = {p["codigo"] for p in rel["problemas"] if p["gravidade"] in ("grave", "media")}
        rel = inspecionar_take(base, take_id, novo["arquivo"], analisador, narracao, b)
        depois = {p["codigo"] for p in rel["problemas"] if p["gravidade"] in ("grave", "media")}
        passo.update({"arquivo": rel["video"], "custo_real_usd": novo.get("custo_real"), "estado_reinspecao": rel["estado"],
                      "resolvidos": sorted(antes - depois), "novos": sorted(depois - antes)})
        hist.append(passo)
        if rel["estado"] == ig.APROVADO:
            return _fim(base, take_id, "aprovado", "reinspeção aprovou e comparou com a bíblia", hist, gasto_est, gasto_real, rel["video"])
        if rel["estado"] == ig.NAO_VERIFICADO:
            return _fim(base, take_id, "revisao_humana", rel.get("motivo_revisao") or "reinspeção sem evidência", hist, gasto_est,
                        gasto_real, rel["video"])
    return _fim(base, take_id, "revisao_humana", f"limite de {cfg['max_tentativas']} tentativas atingido", hist, gasto_est, gasto_real)


def _fim(base, take_id, estado, motivo, hist, gasto_est, gasto_real, arquivo=None):
    res = {"take_id": take_id, "estado": estado, "motivo": motivo,
           "tentativas": sum(1 for h in hist if "arquivo" in h or "resultado" in h),
           "custo_estimado_usd": round(gasto_est, 4), "custo_real_usd": round(gasto_real, 4), "arquivo_final": arquivo, "historico": hist}
    ig.gravar_json_atomico(os.path.join(pasta_cont(base), "inspecoes", f"{take_id}-correcao.json"), res)
    log(base, take_id, "correcao_fim", estado=estado, motivo=motivo, custo_estimado_usd=res["custo_estimado_usd"],
        custo_real_usd=res["custo_real_usd"])
    return res


def analisador_gemini(base, take_id):
    """Análise visual REAL pelo caminho existente (inspetor.analisar_visual: fichas, cache por hash, reserva no orçamento).
    Sem cota/orçamento devolve {"indisponivel": …} → o take fica não verificado (revisão humana)."""
    import inspetor

    def chamar(video, c, elenco, nomes):
        vis, _refs, _falta = inspetor.analisar_visual(base, video, c, {"elenco": elenco}, nomes, take_id)
        return vis
    return chamar


def relatorio_md(base):
    b = pb.carregar(base)
    pc = pasta_cont(base)
    linhas = [f"# Continuidade — {b['titulo']}", "", f"Bíblia {b['hash'][:12]} · aprovação {b['aprovacao']['estado']}", ""]
    a = os.path.join(pc, "pre_producao.json")
    if os.path.exists(a):
        pre = json.load(open(a, encoding="utf-8"))
        linhas += [f"## Pré-produção — {'OK' if pre['ok'] else 'BLOQUEADA'}", ""]
        linhas += [f"- [{p['gravidade']}] {p['texto']}" for p in pre["problemas"]] + [""]
    linhas += ["## Takes", "", "| take | estado | problemas | evidência |", "|---|---|---|---|"]
    for t in b["tomadas"]:
        a = os.path.join(pc, "inspecoes", f"{t['take_id']}.json")
        if os.path.exists(a):
            r = json.load(open(a, encoding="utf-8"))
            probs = "<br>".join(f"[{p['gravidade']}] {p['texto']}" for p in r["problemas"]) or "—"
            linhas.append(f"| {t['take_id']} | {r['estado']}{' (revisão humana)' if r['revisao_humana'] else ''} | {probs} | {r.get('evidencia') or '—'} |")
        else:
            linhas.append(f"| {t['take_id']} | não inspecionado | — | — |")
    out = os.path.join(pc, "RELATORIO.md")
    open(out, "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projeto", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pre")
    s = sub.add_parser("inspecionar"); s.add_argument("take"); s.add_argument("video")
    s.add_argument("--visual", action="store_true", help="análise visual pelo Gemini (cache + orçamento do projeto)")
    s.add_argument("--visual-json", help="análise visual já feita (formato qa_visual), ex. revisão humana registrada")
    s.add_argument("--narracao", help="inicio,fim reais da fala no áudio final")
    sub.add_parser("entre-takes")
    s = sub.add_parser("corrigir"); s.add_argument("take")
    sub.add_parser("relatorio")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    if a.cmd == "pre":
        r = pre_producao(base)
        print(f"pré-produção: {'OK' if r['ok'] else 'BLOQUEADA'} ({len(r['problemas'])} apontamentos)"
              + (" · prancha aprovada (automático)" if r.get("aprovacao") else ""))
        for p in r["problemas"]:
            print(f"  [{p['gravidade']}] {p['texto']}")
        sys.exit(0 if r["ok"] else 1)
    if a.cmd == "inspecionar":
        an = None
        if a.visual_json:
            vis = json.load(open(a.visual_json, encoding="utf-8"))
            an = lambda *_: vis  # noqa: E731
        elif a.visual:
            an = analisador_gemini(base, a.take)
        nar = tuple(float(x) for x in a.narracao.split(",")) if a.narracao else None
        r = inspecionar_take(base, a.take, a.video, an, nar)
        print(f"{a.take}: {r['estado']}" + (f" — revisão humana ({r['motivo_revisao']})" if r["revisao_humana"] else ""))
        for p in r["problemas"]:
            print(f"  [{p['gravidade']}] {p['codigo']}: {p['texto']}")
    elif a.cmd == "entre-takes":
        r = entre_takes(base)
        print("\n".join(f"[{p['gravidade']}] {p['texto']}" for p in r["problemas"]) or "sem quebra de continuidade entre takes")
    elif a.cmd == "corrigir":
        r = corrigir(base, a.take)
        print(json.dumps({k: v for k, v in r.items() if k != "historico"}, ensure_ascii=False, indent=1))
        if r["historico"]:
            print("plano:", json.dumps(r["historico"][-1]["plano"], ensure_ascii=False, indent=1))
    elif a.cmd == "relatorio":
        print(relatorio_md(base))


if __name__ == "__main__":
    main()
