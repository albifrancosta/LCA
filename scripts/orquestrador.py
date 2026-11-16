"""Orquestrador do estúdio: deduz da BÍBLIA (producao.json) o estado de cada tomada e do projeto, diz o que cada
departamento (agente estudio-*) pode fazer AGORA, o que roda em paralelo, onde parar para aprovação no chat e se o
orçamento aprovado cobre o gasto. Refazer uma tomada não mexe nas outras.

Uso (na pasta do projeto):
  python orquestrador.py status                 → estado de cada tomada + do projeto (elenco, voz, trilha, montagem)
  python orquestrador.py proximos [--json]      → tarefas liberadas agora, agrupadas por agente (cada grupo = 1 agente,
                                                  grupos diferentes rodam em paralelo) + o que espera aprovação
  python orquestrador.py orcamento [--aprovar 6.5]   → aprovado, gasto, saldo (agentes conferem antes de gastar)
  python orquestrador.py aprovar t001 t002 [--nota "…"]  → aprovação do usuário (dada no chat) — libera os clipes
  python orquestrador.py invalidar t005 --etapa imagem|clipe|voz --motivo "boca fora de sincronia"
                                                → só essa tomada volta para refazer (as outras ficam como estão)
  python orquestrador.py registrar trilha|ambiente|montagem <arquivo> [--custo 1.8]
  python orquestrador.py biblia [--modo supervisionado|automatico] [--sem-exportar]
                                                → AI Film Production Bible: bible.json + pranchas + checagem pré-produção.
                                                  Com a bíblia ativa, grupos pagos ficam ⛔ até a prancha ser aprovada.
Etapas da tomada: decupar → imagem → checar imagem → APROVAÇÃO (chat) → clipe (se clipe) → checar clipe → cor → pronta.
A voz de cada fala corre em paralelo às imagens. Montagem só quando todas as tomadas estão prontas e as vozes feitas.
"""
import argparse
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from producao import bloqueios_aprovacao, carregar, salvar, tomada  # noqa: E402
import integridade as ig  # noqa: E402

CUSTO = {"gerar_imagem": 0.05, "refazer_imagem": 0.05, "gerar_clipe": 0.27, "refazer_clipe": 0.27, "ficha": 0.05}


from integridade import relativo as _rel  # noqa: E402  (relpath seguro entre discos)


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def valida(t, tipo):
    v = next((v for v in reversed(t["versoes"]) if v["tipo"] == tipo and not v.get("invalida")), None)
    if v and tipo == "clipe":  # P04: clipe só vale se nasceu da imagem válida ATUAL
        img = next((x for x in reversed(t["versoes"]) if x["tipo"] == "imagem" and not x.get("invalida")), None)
        org = v.get("origem") or {}
        if not img or (org and (org.get("imagem_v") != img["v"] or org.get("imagem_sha256") != img.get("sha256"))):
            return None
    if v and tipo == "voz" and v.get("texto_sha256") and v["texto_sha256"] != ig.sha256_texto(t.get("fala", "")):
        return None  # P48: a fala mudou depois da gravação
    return v


def invalidar_derivados(t, etapa, motivo):
    """Cascata (P04): imagem → clipe; voz → clipes com lip-sync. Não apaga histórico nem custo."""
    feitos = []
    alvos = {"imagem": lambda v: v["tipo"] == "clipe",
             "voz": lambda v: v["tipo"] == "clipe" and v.get("lipsync"),
             "clipe": lambda v: False}[etapa]
    for v in t["versoes"]:
        if not v.get("invalida") and alvos(v):
            v["invalida"], v["motivo"] = True, f"origem invalidada ({etapa}): {motivo}"
            feitos.append(f"{v['tipo']} v{v['v']}")
    return feitos


def etapa(d, t):
    """(agente, tarefa, custo) da próxima coisa a fazer nesta tomada — ou ('diretor', 'aprovacao', 0) / ('—', 'pronta', 0)."""
    dec = t.get("decupagem") or {}
    if not dec.get("plano"):
        return "fotografia", "decupar", 0
    faltam = [p for p in t.get("personagens", []) if not d["personagens"].get(p, {}).get("ficha")]
    if faltam:
        return "elenco", "ficha:" + ",".join(faltam), CUSTO["ficha"] * len(faltam)
    img, clip = valida(t, "imagem"), valida(t, "clipe")
    if not img:
        return "arte", "gerar_imagem", CUSTO["gerar_imagem"]
    if not clip:
        if not img.get("continuidade"):
            return "qualidade", "checar_imagem", 0
        if not img["continuidade"].get("ok"):
            return "arte", "refazer_imagem", CUSTO["refazer_imagem"]
    if t["status"] != "aprovada":
        return "diretor", "aprovacao", 0
    if t.get("clipe") or t.get("modo") in ig.MODOS_ANIMADOS:
        if not clip:
            return "animacao", "gerar_clipe", CUSTO["gerar_clipe"]
        if not clip.get("continuidade"):
            return "qualidade", "checar_clipe", 0
        if not clip["continuidade"].get("ok"):
            return "animacao", "refazer_clipe", CUSTO["refazer_clipe"]
        qa = clip.get("qa", ig.NAO_VERIFICADO)  # P10: inspeção do clipe é etapa obrigatória
        if qa == ig.REPROVADO:
            return "animacao", "refazer_clipe", CUSTO["refazer_clipe"]
        if qa != ig.APROVADO:
            return "qualidade", "inspecionar_clipe", 0
        if not clip.get("cor"):
            return "arte", "colorir", 0
    elif not img.get("cor") and d["cenarios"].get(t.get("cenario", ""), {}).get("ref") not in (None, img["arquivo"]):
        return "arte", "colorir", 0
    return "—", "pronta", 0


def voz_pendente(t):
    return bool(t.get("fala")) and not valida(t, "voz")


def voz_sem_qa(t):
    """Voz gravada com o fluxo novo (tem campo qa) precisa da inspeção de áudio aprovada; versões antigas sem o campo passam."""
    v = valida(t, "voz")
    return bool(t.get("fala")) and v is not None and "qa" in v and v["qa"] != ig.APROVADO


def gasto(d):
    g = sum(v.get("custo") or 0 for t in d["tomadas"] for v in t["versoes"])
    g += sum(x.get("custo") or 0 for x in (d.get("orcamento") or {}).get("gasto_extra", []))
    return round(g, 3)


def saldo(d):
    ap = (d.get("orcamento") or {}).get("aprovado")
    return None if ap is None else round(ap - gasto(d), 3)


def portao_biblia(base, d):
    """AI Film Production Bible (cinematografia/production_bible.py). None = projeto não usa (fluxo antigo intacto)."""
    if not base:
        return None
    try:
        from cinematografia import production_bible as pb
        return pb.portao(base, d)
    except Exception as e:  # noqa: BLE001 — bíblia ilegível bloqueia o gasto em vez de passar calada
        return {"liberado": False, "motivo": f"bíblia visual ilegível: {e}", "tarefa": "construir_biblia"}


def takes_sem_supervisao(base, d):
    """Clipes válidos ainda sem relatório do supervisor de continuidade para ESTE arquivo (sha) — só com a bíblia ativa."""
    pasta = os.path.join(base, "production_bible", "continuity", "inspecoes")
    faltam = []
    for t in d["tomadas"]:
        clip = valida(t, "clipe")
        if not clip:
            continue
        rel = os.path.join(pasta, f"{t['id']}.json")
        r = json.load(open(rel, encoding="utf-8")) if os.path.exists(rel) else {}
        if not clip.get("sha256") or r.get("sha256") != clip.get("sha256"):
            faltam.append(t["id"])
    return faltam


def planejar(d, base=None):
    grupos, espera, prontas = {}, [], []
    for t in d["tomadas"]:
        ag, tarefa, custo = etapa(d, t)
        if ag == "diretor":
            espera.append(t["id"])
        elif ag == "—":
            prontas.append(t["id"])
        else:
            nome = tarefa.split(":")[0]
            g = grupos.setdefault((ag, nome), {"agente": f"estudio-{ag}", "tarefa": nome, "tomadas": [], "custo": 0.0})
            g["tomadas"].append(t["id"])
            g["custo"] = round(g["custo"] + custo, 3)
    vozes = [t["id"] for t in d["tomadas"] if voz_pendente(t)]
    if vozes:
        grupos[("audio", "voz")] = {"agente": "estudio-audio", "tarefa": "voz", "tomadas": vozes, "custo": 0.0}
    sem_qa = [t["id"] for t in d["tomadas"] if voz_sem_qa(t)]
    if sem_qa:
        grupos[("qualidade", "inspecionar_voz")] = {"agente": "estudio-qualidade", "tarefa": "inspecionar_voz", "tomadas": sem_qa, "custo": 0.0}
    vozes = vozes + sem_qa
    proj = d.get("projeto_arquivos") or {}
    tudo_pronto = bool(d["tomadas"]) and len(prontas) == len(d["tomadas"]) and not vozes
    if tudo_pronto and not proj.get("trilha"):
        grupos[("musical", "trilha")] = {"agente": "estudio-musical", "tarefa": "trilha", "tomadas": [], "custo": 0.0}
    if tudo_pronto and not proj.get("ambiente"):
        grupos[("audio", "ambiente")] = {"agente": "estudio-audio", "tarefa": "ambiente", "tomadas": [], "custo": 0.0}
    if tudo_pronto and proj.get("trilha") and proj.get("ambiente") and not proj.get("montagem"):
        grupos[("editor", "montagem")] = {"agente": "estudio-editor", "tarefa": "montagem", "tomadas": [], "custo": 0.0}
    gate = portao_biblia(base, d)
    if gate:
        if gate.get("tarefa") == "aprovar_prancha":
            espera.insert(0, "prancha")
        elif gate.get("tarefa"):
            ag = "estudio-qualidade" if gate["tarefa"] == "pre_producao" else "estudio-fotografia"
            grupos[("biblia", gate["tarefa"])] = {"agente": ag, "tarefa": gate["tarefa"], "tomadas": [], "custo": 0.0, "motivo": gate["motivo"]}
        if not gate["liberado"]:
            for g in grupos.values():  # supervisionado: nada pago antes da prancha aprovada
                if g["custo"] > 0:
                    g["bloqueado_biblia"] = gate["motivo"]
        sem_sup = takes_sem_supervisao(base, d)
        if sem_sup:
            grupos[("qualidade", "supervisionar_take")] = {"agente": "estudio-qualidade", "tarefa": "supervisionar_take",
                                                           "tomadas": sem_sup, "custo": 0.0}
    s = saldo(d)
    reservado = 0.0  # P05: grupos que rodam JUNTOS dividem o mesmo saldo — reserva cumulativa, mais baratos primeiro
    for g in sorted(grupos.values(), key=lambda x: x["custo"]):
        if g["custo"] <= 0 or g.get("bloqueado_biblia"):
            g["precisa_orcamento"] = False
            continue
        cabe = s is not None and reservado + g["custo"] <= s + 1e-9
        g["precisa_orcamento"] = not cabe
        if cabe:
            reservado += g["custo"]
            g["reserva"] = round(g["custo"], 3)
    return list(grupos.values()), espera, prontas


def cmd_status(d):
    o = d.get("orcamento") or {}
    print(f"{d['titulo']} — gasto US$ {gasto(d)}" + (f" de {o['aprovado']} aprovados" if o.get("aprovado") is not None else " (sem orçamento aprovado)"))
    for t in d["tomadas"]:
        ag, tarefa, _ = etapa(d, t)
        quem = "→ você (chat)" if ag == "diretor" else ("" if ag == "—" else f"→ estudio-{ag}")
        voz = "voz ✅" if valida(t, "voz") else ("voz ⏳" if t.get("fala") else "sem fala")
        print(f"  {t['id']}  {tarefa:16} {quem:22} {voz:8} {t.get('cena', '')[:20]}")
    proj = d.get("projeto_arquivos") or {}
    print("  projeto: " + " · ".join(f"{k} {'✅' if proj.get(k) else '—'}" for k in ("trilha", "ambiente", "montagem")))


def cmd_proximos(d, como_json, base=None):
    grupos, espera, prontas = planejar(d, base)
    if como_json:
        print(json.dumps({"paralelo": grupos, "aguardando_aprovacao": espera, "prontas": prontas, "saldo": saldo(d)},
                         ensure_ascii=False, indent=1))
        return
    if grupos:
        print("Pode rodar agora (cada linha = 1 agente; linhas diferentes em paralelo):")
        for g in grupos:
            alerta = f"  ⛔ {g['bloqueado_biblia']}" if g.get("bloqueado_biblia") else ("  ⚠️ precisa orçamento" if g["precisa_orcamento"] else "")
            print(f"  {g['agente']:20} {g['tarefa']:15} {', '.join(g['tomadas']) or '(projeto)':30} US$ {g['custo']:.2f}{alerta}")
    if espera:
        print(f"Esperando sua aprovação no chat: {', '.join(espera)}")
    s = saldo(d)
    print(f"Prontas: {len(prontas)}/{len(d['tomadas'])} · saldo: {s if s is not None else 'sem orçamento aprovado'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projeto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("proximos"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("orcamento"); s.add_argument("--aprovar", type=float)
    s = sub.add_parser("aprovar"); s.add_argument("ids", nargs="+"); s.add_argument("--nota", default="")
    s.add_argument("--forcar", action="store_true", help="decisão do diretor no chat apesar do bloqueio técnico (exige --nota)")
    s = sub.add_parser("invalidar"); s.add_argument("id"); s.add_argument("--etapa", required=True, choices=["imagem", "clipe", "voz"])
    s.add_argument("--motivo", required=True)
    s = sub.add_parser("registrar"); s.add_argument("item", choices=["trilha", "ambiente", "montagem"]); s.add_argument("arquivo")
    s.add_argument("--custo", type=float, default=0)
    s = sub.add_parser("biblia", help="AI Film Production Bible: constrói, gera as pranchas e roda a checagem de pré-produção")
    s.add_argument("--modo", choices=["supervisionado", "automatico"]); s.add_argument("--sem-exportar", action="store_true")
    a = ap.parse_args()
    arq, d = carregar(a.projeto)
    raiz = os.path.dirname(arq)
    if a.cmd == "status":
        cmd_status(d)
    elif a.cmd == "proximos":
        cmd_proximos(d, a.json, raiz)
    elif a.cmd == "biblia":
        from cinematografia import board_generator as bg
        from cinematografia import production_bible as pb
        import supervisor_continuidade as sup
        b = pb.construir(raiz, modo=a.modo)
        erros = pb.validar(b)
        feitos, lim = bg.gerar(raiz, exportar_midia=not a.sem_exportar)
        pre = sup.pre_producao(raiz)
        print(f"bíblia {b['hash'][:12]}: {len(b['tomadas'])} takes · pré-produção {'OK' if pre['ok'] else 'BLOQUEADA'} · "
              f"aprovação {pb.carregar(raiz)['aprovacao']['estado']} · custo estimado US$ {b['custos_estimados']['total_estimado_usd']}")
        for x in erros + [f"[{p['gravidade']}] {p['texto']}" for p in pre["problemas"]] + [f"LIMITAÇÃO: {x}" for x in lim]:
            print("  " + x)
        print("\n".join("  " + f for f in feitos if f.endswith(("overview.png", "overview.html"))))
    elif a.cmd == "orcamento":
        if a.aprovar is not None:
            d.setdefault("orcamento", {})["aprovado"] = a.aprovar
            salvar(arq, d, f"orçamento aprovado: US$ {a.aprovar}")
        o = d.get("orcamento") or {}
        s = saldo(d)
        print(f"aprovado: {o.get('aprovado', '—')} · gasto: {gasto(d)} · saldo: {s if s is not None else '—'}")
    elif a.cmd == "aprovar":
        recusadas = {}
        for tid in a.ids:  # P03: só aprova tomada com prova técnica; o resto fica como está
            t = tomada(d, tid)
            bl = bloqueios_aprovacao(d, t, raiz)
            if bl and not (a.forcar and a.nota):
                recusadas[tid] = bl
                continue
            img = valida(t, "imagem")
            t["status"], t["aprovada_em"] = "aprovada", agora()
            t["aprovada_versao"] = {"imagem_v": img["v"], "imagem_sha256": img.get("sha256")} if img else None
            if a.nota:
                t.setdefault("notas", []).append(("À FORÇA: " if bl else "") + a.nota)
        a.ids = [i for i in a.ids if i not in recusadas]
        for tid, bl in recusadas.items():
            print(f"RECUSADA {tid}: {'; '.join(bl)}")
        if not a.ids:
            sys.exit(1)
        salvar(arq, d, f"aprovadas no chat: {', '.join(a.ids)} {a.nota}".strip())
        print(f"aprovadas: {', '.join(a.ids)}")
    elif a.cmd == "invalidar":
        t = tomada(d, a.id)
        v = valida(t, a.etapa)
        if not v:
            sys.exit(f"{a.id} não tem versão válida de {a.etapa}")
        v["invalida"], v["motivo"] = True, a.motivo
        derivados = invalidar_derivados(t, a.etapa, a.motivo)
        if a.etapa == "imagem":
            t["status"] = "refazer"  # imagem nova precisa de nova aprovação; clipe/voz não
        if derivados:
            print(f"  também invalidados (dependiam dessa {a.etapa}): {', '.join(derivados)}")
        salvar(arq, d, f"{a.id}: {a.etapa} v{v['v']} invalidada — {a.motivo}")
        print(f"{a.id}: {a.etapa} v{v['v']} vai ser refeita ({a.motivo}); as outras tomadas não mudam")
    elif a.cmd == "registrar":
        d.setdefault("projeto_arquivos", {})[a.item] = _rel(os.path.abspath(a.arquivo), raiz).replace("\\", "/")
        if a.custo:
            d.setdefault("orcamento", {}).setdefault("gasto_extra", []).append({"item": a.item, "custo": a.custo, "quando": agora()})
        salvar(arq, d, f"{a.item}: {a.arquivo}")
        print(f"{a.item} registrado")


if __name__ == "__main__":
    main()
