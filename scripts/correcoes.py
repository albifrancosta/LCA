"""Para cada defeito, a correção COMPATÍVEL de menor custo total (dinheiro + tempo + risco) — regenerar é o último recurso.

Escada (do mais barato ao mais caro): overlay → mascara → corte → recomposicao → mudanca_editorial → edicao_localizada →
regenerar_imagem (+ clipe) → regenerar_clipe. Telas, textos e símbolos vão em CÓDIGO (mais preciso e de graça); defeito de
MONTAGEM (congelamento, repetição, Freeze no fim, legenda, duração) NUNCA se resolve regenerando clipe.

Casos da MinhaMarca "dois mundos" que motivaram a escada:
  c03a cifrões no ar          → overlay do "?" em código por cima (custo 0) — regenerar não garante que o modelo pare
  c07c card ilegível          → overlay do card em código (foi o que funcionou)
  c02e gravata no último terço→ corte (usa os 2/3 sem gravata, desacelera até 0,75) antes de pagar outro take
  c10d Freeze no fim (split)  → recomposição (minRate / encurtar o plano) — nunca regenerar
  c06c/c07a tela nas costas   → o defeito está NA IMAGEM-CHAVE: corrigir a imagem (US$ ~0,05) antes do clipe
  c03c/c06a boca fora         → mudança editorial (fala em off) — revisa o contrato e passa por nova inspeção

Uso:
  python correcoes.py sugerir <projeto> --plano c02e        → opções ordenadas a partir da última inspeção do plano
  python correcoes.py registrar <projeto> --plano c07c --opcao overlay --nota "card em código" [--estado aplicada]
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

ESCADA = ["overlay", "mascara", "corte", "recomposicao", "mudanca_editorial", "edicao_localizada", "regenerar_imagem", "regenerar_clipe"]
MINUTOS = {"overlay": 10, "mascara": 20, "corte": 5, "recomposicao": 10, "mudanca_editorial": 10, "edicao_localizada": 15,
           "regenerar_imagem": 8, "regenerar_clipe": 12}
VALOR_MINUTO = 0.01  # US$ por minuto de trabalho/fila — só desempata; dinheiro de API pesa mais
MONTAGEM = {"fim_preenchido", "congelamento", "repeticao", "legenda", "duracao", "render_desatualizado", "cobertura"}
OPCOES = {
    "texto_simbolo_gerado": ["overlay", "mascara", "corte", "regenerar_clipe"],
    "texto_ilegivel": ["overlay", "mascara", "regenerar_clipe"],
    "interface_traseira": ["mascara", "corte", "regenerar_imagem", "regenerar_clipe"],
    "membros_extras": ["corte", "edicao_localizada", "regenerar_imagem", "regenerar_clipe"],
    "figurino_involuntario": ["corte", "mascara", "edicao_localizada", "regenerar_clipe"],
    "identidade_diferente": ["corte", "regenerar_imagem", "regenerar_clipe"],
    "falha_visual_evidente": ["corte", "regenerar_clipe"],
    "maos_deformadas": ["corte", "mascara", "regenerar_clipe"],
    "lipsync": ["mudanca_editorial", "regenerar_clipe"],
    "estatico": ["mudanca_editorial", "regenerar_clipe"],
    "criterio_contrato": ["mudanca_editorial", "regenerar_clipe"],
    "fim_preenchido": ["recomposicao", "corte"],
    "congelamento": ["recomposicao", "corte"],
    "repeticao": ["recomposicao", "corte"],
    "legenda": ["recomposicao"],
    "duracao": ["recomposicao", "corte"],
    "render_desatualizado": ["recomposicao"],
}
COMO = {
    "overlay": "desenhar em código (Remotion) por cima do trecho: texto/símbolo/tela corretos cobrindo o que o modelo fez",
    "mascara": "cobrir a região do defeito com máscara/forma da cor do objeto (costas lisas do aparelho, peça de roupa) no trecho",
    "corte": "usar só o trecho limpo do clipe (antes/depois do defeito) e completar o tempo com desaceleração ≤ 0,75× ou plano vizinho",
    "recomposicao": "ajustar a montagem: minRate/encurtar o plano, corte em J, trocar a ordem, segurar o plano vizinho — sem gerar nada",
    "mudanca_editorial": "mudar o contrato (ex.: fala em quadro → voz em off) com `inspetor.py adaptar`; a reprovação original fica registrada",
    "edicao_localizada": "edição localizada no provedor (vídeo-para-vídeo/inpainting) só no trecho — exige provedor com essa capacidade no catálogo",
    "regenerar_imagem": "o defeito nasce na imagem-chave: corrigir o prompt (descrever o que DEVE aparecer) e gerar a imagem; depois o clipe",
    "regenerar_clipe": "novo take com a correção do inspetor no prompt (último recurso)",
}


def classificar(problemas, bloqueios=()):
    """Texto dos problemas → códigos de defeito. Bloqueios objetivos já vêm com código."""
    cods = list(bloqueios)
    regras = [("fim de clipe preenchido", "fim_preenchido"), ("congelamento", "congelamento"), ("repetição de quadros", "repeticao"),
              ("render desatualizado", "render_desatualizado"), ("legenda", "legenda"), ("duração", "duracao"),
              ("lip-sync", "lipsync"), ("boca", "lipsync"), ("ilegível", "texto_ilegivel"), ("desenhou", "texto_simbolo_gerado"),
              ("braços", "membros_extras"), ("fora da ficha", "figurino_involuntario"), ("costas", "interface_traseira"),
              ("rosto diferente", "identidade_diferente"), ("movimento próprio", "estatico"), ("só câmera", "estatico"),
              ("deforma", "maos_deformadas")]
    for _, t in problemas:
        tl = t.lower()
        cods.append(next((c for k, c in regras if k in tl), "criterio_contrato"))
    return list(dict.fromkeys(cods))


def janela_limpa(ctx):
    """Corte viável? Precisa do instante do defeito e de trecho limpo que cubra o plano com desaceleração ≤ 0,75×."""
    seg, dur_c, dur_p = ctx.get("defeito_em"), ctx.get("dur_clipe"), ctx.get("dur_plano")
    if seg is None or not dur_c or not dur_p:
        return False
    limpo = max(float(seg) - 0.15, dur_c - float(seg) - 0.15)
    return limpo >= dur_p * 0.75 and not ctx.get("beat_essencial_no_defeito")


def viavel(opcao, cod, ctx):
    if opcao == "corte":
        return janela_limpa(ctx) or (cod in MONTAGEM and cod != "legenda")
    if opcao == "mascara":
        return bool(ctx.get("regiao_estatica")) or cod in ("texto_simbolo_gerado", "texto_ilegivel")
    if opcao == "overlay":
        return cod in ("texto_simbolo_gerado", "texto_ilegivel") or bool(ctx.get("cabe_overlay"))
    if opcao == "edicao_localizada":
        return bool(ctx.get("tem_edicao_localizada"))
    if opcao == "regenerar_imagem":
        return bool(ctx.get("defeito_na_imagem"))
    if opcao == "regenerar_clipe" and ctx.get("defeito_na_imagem"):
        return False  # o defeito nasce na imagem-chave: outro take da mesma imagem repete o defeito
    if opcao == "mudanca_editorial":
        return cod in ("lipsync", "criterio_contrato") or bool(ctx.get("editorial_ok"))
    return True


def custo(opcao, ctx):
    """US$ esperado (÷ taxa de aproveitamento) + tempo convertido. Regeneração usa o preço do catálogo; None = desconhecido."""
    if opcao in ("regenerar_clipe", "edicao_localizada"):
        p = ctx.get("custo_clipe")
        return None if p is None else p / max(ctx.get("taxa", 0.6), 0.2) + MINUTOS[opcao] * VALOR_MINUTO
    if opcao == "regenerar_imagem":
        pi, pc = ctx.get("custo_imagem"), ctx.get("custo_clipe")
        return None if pi is None or pc is None else pi + pc / max(ctx.get("taxa", 0.6), 0.2) + MINUTOS[opcao] * VALOR_MINUTO
    return MINUTOS[opcao] * VALOR_MINUTO


def escolher(codigos, ctx):
    """Plano de correção: [{"defeito", "opcao", "custo_usd", "como", "gasta"}] — a opção viável mais barata por defeito.
    Limites esgotados (tentativas/gasto/tempo) → só opções sem gasto; nada viável → "ressalva" (mantém, documentado)."""
    sem_gasto = (ctx.get("tentativas_restantes", 1) <= 0 or (ctx.get("gasto_restante") is not None and ctx["gasto_restante"] <= 0)
                 or (ctx.get("minutos_restantes") is not None and ctx["minutos_restantes"] <= 0))
    plano = []
    for cod in codigos:
        ops = [o for o in OPCOES.get(cod, ["regenerar_clipe"]) if viavel(o, cod, ctx)]
        if cod in MONTAGEM:
            ops = [o for o in ops if not o.startswith("regenerar")]  # defeito de montagem nunca regenera clipe
        cands = []
        for o in ops:
            c = custo(o, ctx)
            gasta = o.startswith("regenerar") or o == "edicao_localizada"
            if gasta and (sem_gasto or c is None):
                continue
            if gasta and ctx.get("gasto_restante") is not None and c - MINUTOS[o] * VALOR_MINUTO > ctx["gasto_restante"] + 1e-9:
                continue
            dinheiro = c - MINUTOS[o] * VALOR_MINUTO
            cands.append((round(dinheiro, 6), OPCOES.get(cod, ["regenerar_clipe"]).index(o), o, gasta, c))
        if not cands:
            plano.append({"defeito": cod, "opcao": "ressalva", "custo_usd": 0.0, "gasta": False,
                          "como": "nenhuma correção viável dentro dos limites — manter com ressalva documentada no relatório"})
            continue
        _, _, o, gasta, c = sorted(cands)[0]  # menor dinheiro; empate (sem gasto) → preferência do defeito
        plano.append({"defeito": cod, "opcao": o, "custo_usd": round(c, 4), "gasta": gasta, "como": COMO[o]})
    return plano


def precisa_gerar(plano):
    return any(x["gasta"] for x in plano)


def contexto(base, pid, d, insp=None, cfg=None, gasto_plano=0.0, tentativas=0, minutos=0.0):
    """Contexto da decisão a partir da inspeção, do roteiro, do projeto e do catálogo (preço de regenerar)."""
    p = next((x for x in d["planos"] if x["id"] == pid), {})
    c = p.get("direcao") or {}
    insp = insp or {}
    lim = (cfg or {}).get("limites") or {}
    seg = None
    for _, t in insp.get("problemas") or []:
        m = re.search(r"\((\d+(?:\.\d+)?)s\)", t)
        if m:
            seg = float(m.group(1))
            break
    ctx = {"dur_plano": float(c.get("duracao") or p.get("dur_alvo") or 0) or None, "dur_clipe": insp.get("duracao_clipe"),
           "defeito_em": seg, "taxa": 0.6, "custo_clipe": None, "custo_imagem": None,
           "tentativas_restantes": int(lim.get("max_refacoes_plano", 2)) - max(0, tentativas - 1),
           "gasto_restante": (float(lim["max_gasto_plano"]) - gasto_plano) if lim.get("max_gasto_plano") is not None else None,
           "minutos_restantes": (float(lim["max_minutos_plano"]) - minutos) if lim.get("max_minutos_plano") is not None else None,
           "defeito_na_imagem": False, "editorial_ok": c.get("voz") == "em_quadro"}
    try:
        import inspetor
        ctx["defeito_na_imagem"] = inspetor.estado_imagem(base, pid)[0] == ig.REPROVADO
    except Exception:  # noqa: BLE001 — sem inspeção de imagem não é erro
        pass
    try:
        import provedores as pv
        cat, _ = pv.config()
        dur = ctx["dur_plano"] or 5
        precos = [pv.estimar(x, {"task_type": x["stage"], "requirements": {"duration_s": dur}}) for x in cat["provedores"]
                  if x.get("enabled") and x.get("stage") in ("video", "lipsync")]
        precos = [x for x in precos if x]
        ctx["custo_clipe"] = min(precos) if precos else None
        pi = [pv.estimar(x, {"task_type": "imagem", "requirements": {}}) for x in cat["provedores"] if x.get("enabled") and x.get("stage") == "imagem"]
        pi = [x for x in pi if x]
        ctx["custo_imagem"] = min(pi) if pi else None
        tx = [v["taxa"] for v in pv.historico().values()]
        if tx:
            ctx["taxa"] = sum(tx) / len(tx)
    except Exception:  # noqa: BLE001
        pass
    return ctx


def registrar(base, pid, opcao, nota, estado="pendente", defeito=None):
    clip = os.path.join(base, "assets", "clips", f"{pid}.mp4")

    def f(d):
        d.setdefault("correcoes", []).append({"plano": pid, "opcao": opcao, "defeito": defeito, "nota": nota, "estado": estado,
                                              "sha256_clipe": ig.sha256(clip) if os.path.isfile(clip) else None,
                                              "quando": datetime.datetime.now().isoformat(timespec="seconds")})
    return ig.atualizar_json(os.path.join(base, "entrega", "correcoes.json"), f, padrao={"correcoes": []})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["sugerir", "registrar"])
    ap.add_argument("projeto")
    ap.add_argument("--plano", required=True)
    ap.add_argument("--opcao", choices=ESCADA + ["ressalva"])
    ap.add_argument("--nota", default="")
    ap.add_argument("--estado", default="aplicada", choices=["pendente", "aplicada"])
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    if a.acao == "registrar":
        if not a.opcao:
            sys.exit("registrar precisa de --opcao")
        registrar(base, a.plano, a.opcao, a.nota, a.estado)
        print(f"{a.plano}: correção '{a.opcao}' registrada ({a.estado})")
        return
    d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    try:
        insp = next(i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8"))["itens"] if i["id"] == a.plano)
    except (OSError, ValueError, StopIteration, KeyError):
        sys.exit(f"{a.plano}: sem inspeção registrada")
    import projeto as pj
    ctx = contexto(base, a.plano, d, insp, pj.carregar(base))
    plano = escolher(classificar(insp.get("problemas") or [], insp.get("bloqueios") or []), ctx)
    print(json.dumps({"contexto": ctx, "plano": plano}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
