"""Modo autônomo do estúdio: gera cada take, ASSISTE (inspetor), aprova ou refaz, e segue para o próximo — sem parar para
pedir aprovação a cada tomada (pedido do usuário, 2026-11-06). O usuário aprova o orçamento total UMA vez e o filme no fim.

Laço por plano de atuação (ordem do roteiro):
  imagem-chave? (assets/img/<id>.png)  → senão  aguardando_imagem   (pula, não gasta)
  fala em quadro? voz? (assets/voz/<id>.wav) → senão aguardando_voz
  gera pelo roteador (provedores.py executar — grátis primeiro, teto do vídeo, preço desconhecido bloqueia)
  inspetor.py planos --planos <id> --registrar   (Gemini assiste com som + YOLO + whisper + nota 0–100, mínimo 85)
     aprovado        → segue
     reprovado       → guarda o take em assets/clips/rejeitados/, refaz com a CORREÇÃO do inspetor no prompt,
                       até --max-refacoes (padrão 2); estourou → marcado (segue sem gastar mais)
     nao_verificado  → revisao_diretor: o Claude olha entrega/inspecao/<id>.jpg e grava `inspetor.py revisar` (nunca aprova sozinho)
  roteador pede aprovação (teto)      → precisa_orcamento UMA vez; os planos seguintes não chamam o roteador de novo (mesmo
                                        bloqueio, sem repetir a mensagem), mas o trabalho grátis/independente continua
                                        (inspecionar clipes e imagens que já existem)
  job pago sem resposta               → pendente_verificacao; ao retomar, o roteador CONSULTA/recupera o job antes de enviar outro
2026-11-07 (com projeto.json — o fluxo normal):
  - modo, teto, uso (licença), limites de refação/gasto/tempo por plano vêm do projeto.json (projeto.py)
  - imagem-chave é inspecionada ANTES do clipe (inspetor.py imagens): defeito na imagem não vira clipe pago
  - reprovado → correcoes.py escolhe a correção de menor custo; overlay/máscara/corte/recomposição/mudança editorial
    vira `corrigir_em_codigo` (registrado em entrega/correcoes.json, o take volta para assets/clips) e NÃO gasta;
    só regenera quando essa é a opção viável mais barata
  - limites esgotados → alternativa sem gasto ou `marcado` com ressalva
Telas, inserts e composições (rota foto_camera/motion/composicao) não entram: são feitas em código.

Uso:
  python autonomo.py rodar  roteiro.json --job <video> [--planos c02a,c02e] [--max-refacoes 2] [--teto 8] [--simular]
  python autonomo.py status roteiro.json
--simular: só planeja (provedores.py planejar) — mostra quem geraria cada take e quanto custaria. Nada é gasto.
Saída: entrega/autonomo.json (estado por plano) + entrega/autonomo-relatorio.md (o que foi aprovado, refeito, marcado).
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402
from contrato import ler, prompt_atuacao, rota_de  # noqa: E402

PY = sys.executable
GERA = {"clipe": "video", "avatar": "lipsync", "omnihuman": "lipsync"}
FINAIS = {"aprovado", "marcado"}


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rodar_cmd(cmd, timeout=1800):
    import chaves  # ambiente mínimo: sistema + chaves do estúdio (o pipeline usa várias); segredos alheios não passam
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       env=chaves.env_filho())
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def estado_arq(base):
    return os.path.join(base, "entrega", "autonomo.json")


def ler_estado(base):
    try:
        return json.load(io.open(estado_arq(base), encoding="utf-8"))
    except (OSError, ValueError):
        return {"planos": {}}


def gravar_estado(base, st):
    st["atualizado"] = agora()
    os.makedirs(os.path.join(base, "entrega"), exist_ok=True)
    ig.gravar_json_atomico(estado_arq(base), st)


def correcao(base, pid):
    """Texto de correção para o próximo take, tirado da inspeção reprovada (problemas + critérios que falharam)."""
    try:
        insp = json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    it = next((x for x in insp.get("itens", []) if x.get("id") == pid), None) or {}
    falhas = list(it.get("problemas") or [])
    for c in (it.get("revisao_visual") or {}).get("criterios") or []:
        if not isinstance(c, dict):  # revisão pendente (sem Gemini) lista os critérios como texto — não é falha vista
            continue
        if not c.get("ok"):
            falhas.append(f"{c.get('criterio')} (seen: {c.get('visto')})")
    for d in (it.get("revisao_visual") or {}).get("deformacoes") or []:
        falhas.append(f"avoid deformation: {d}")
    try:  # falha medida de lip-sync (conferencia.py) também vira correção
        ls = json.load(io.open(os.path.join(base, "entrega", "inspecao-lipsync.json"), encoding="utf-8"))
        li = next((x for x in ls.get("itens", []) if x.get("id") == pid), None) or {}
        if li.get("estado") == ig.REPROVADO:
            falhas += [f"lip-sync: {t}" for _, t in li.get("problemas") or []] + [
                "mouth must open and close on every syllable, exactly in time with the voice"]
    except (OSError, ValueError):
        pass
    for nome in ("atuacao", "figurino"):  # correções do diretor de atuação e do figurino
        try:
            esp = json.load(io.open(os.path.join(base, "entrega", f"inspecao-{nome}.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        it2 = next((x for x in esp.get("itens", []) if x.get("id") == pid), None) or {}
        if it2.get("estado") == ig.REPROVADO:
            if it2.get("correcao_en"):
                falhas.append(f"acting: {it2['correcao_en']}")
            falhas += [f"{nome}: {t}" for _, t in it2.get("problemas") or []][:4]
    return ("FIX FROM PREVIOUS TAKE (must not repeat): " + "; ".join(str(f) for f in falhas)[:700]) if falhas else ""


def tarefa(p, base, job, rota, tentativa, extra=""):
    c = p["direcao"]
    pid = p["id"]
    dur = float(c.get("duracao") or 5)
    req = {"imagem": os.path.join(base, "assets", "img", f"{pid}.png"), "duration_s": dur,
           "saida": os.path.join(base, "assets", "clips", f"{pid}.mp4")}
    prompt = prompt_atuacao(p)
    if extra:
        prompt = f"{prompt} {extra}"
    if GERA[rota] == "video":
        req.update(capabilities=["i2v", "atuacao"], direcao=c, prompt=prompt)
        # continuidade entre takes consecutivos (2026-11-07): 1º quadro = último quadro do take anterior APROVADO
        if c.get("continua_de"):
            ant = os.path.join(base, "assets", "clips", f"{c['continua_de']}.mp4")
            if os.path.isfile(ant) and ig.estado_inspecao(base, c["continua_de"], ant)[0] == ig.APROVADO:
                ini = os.path.join(base, "assets", "img", f"{pid}-continuidade.png")
                if not os.path.isfile(ini):
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", ant, "-frames:v", "1", ini], check=False)
                if os.path.isfile(ini):
                    req["imagem"] = ini
        if c.get("quadro_final_img"):  # quadro final pedido (modelos com 'ultimo_quadro' preservam o fim do plano)
            req["ultimo_quadro"] = os.path.join(base, c["quadro_final_img"])
        if c.get("evitar"):  # restrições como prompt negativo, onde o modelo aceita (descrever o certo continua no prompt)
            req["negativo"] = ", ".join(c["evitar"]) if isinstance(c["evitar"], list) else str(c["evitar"])
    else:
        req.update(capabilities=["lipsync", "fala_com_corpo" if rota == "omnihuman" else "fala_em_quadro"],
                   audio=os.path.join(base, "assets", "voz", f"{pid}.wav"), prompt=prompt)
    t = {"job_id": job, "scene_id": pid, "task_type": GERA[rota], "mode": "final", "requirements": req}
    if os.path.isfile(os.path.join(base, "projeto.json")):
        t["projeto"] = base  # modo/teto/uso (licença comercial) do projeto — provedores.aplicar_projeto
    else:
        t["commercial_use"] = False  # legado sem projeto.json: política = padrão do roteamento.json
    arq = os.path.join(base, "tarefas", f"{pid}-auto-{tentativa}.json")
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    ig.gravar_json_atomico(arq, t)
    return arq


def ler_resultado(txt):
    """O roteador imprime o JSON do resultado no fim da saída."""
    i = txt.rfind("\n{")
    i = 0 if i < 0 else i
    try:
        return json.loads(txt[i:].strip())
    except ValueError:
        return {"status": "erro", "motivo": txt[-400:]}


def inspecionar(roteiro, pid, run=rodar_cmd):
    cod, txt = run([PY, os.path.join(AQUI, "inspetor.py"), "planos", roteiro, "--planos", pid, "--registrar"])
    return {0: ig.APROVADO, 2: ig.REPROVADO, 3: ig.NAO_VERIFICADO}.get(cod, "erro"), txt


def nota_de(base, pid):
    try:
        insp = json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8"))
        n = next((x.get("nota") for x in insp.get("itens", []) if x.get("id") == pid), None)
        return n.get("valor") if isinstance(n, dict) else n  # inspetor grava {"valor": 0–100, "componentes": {…}}
    except (OSError, ValueError):
        return None


def candidatos(d, base, planos=None):
    alvo = set(planos.split(",")) if planos else None
    out = []
    for p in d["planos"]:
        c = p.get("direcao") or {}
        if alvo and p["id"] not in alvo:
            continue
        if not c.get("modo") or c.get("rota_fixa") or c.get("modo") not in ig.MODOS_ANIMADOS:
            continue
        rota = rota_de(p, base)["rota"]
        if rota in GERA:
            out.append((p, rota))
    return out


def checar_imagem(roteiro, base, pid, cfg, run):
    """Imagem-chave inspecionada (mesmo sha) antes de gastar com o clipe. (ok, estado, motivo)."""
    import inspetor
    est, it = inspetor.estado_imagem(base, pid)
    if it is None:
        run([PY, os.path.join(AQUI, "inspetor.py"), "imagens", roteiro, "--planos", pid])
        est, it = inspetor.estado_imagem(base, pid)
    if est == ig.REPROVADO:
        return False, "imagem_reprovada", "imagem-chave: " + "; ".join(t for _, t in (it or {}).get("problemas") or [])[:300]
    if est != ig.APROVADO and cfg["qualidade"].get("exigir_evidencia", True):
        return False, "revisao_imagem", f"imagem-chave sem verificação — olhar assets/img/{pid}.png e gravar `inspetor.py revisar --imagem`"
    return True, est, ""


def tentar_corrigir_barato(base, pid, d, cfg, e, minutos):
    """Depois de uma reprovação: a correção de menor custo. Devolve o plano se NÃO precisa gerar (corrigir em código/editorial)."""
    import correcoes
    try:
        insp = next(i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-planos.json"), encoding="utf-8"))["itens"] if i["id"] == pid)
    except (OSError, ValueError, StopIteration, KeyError):
        return None
    ctx = correcoes.contexto(base, pid, d, insp, cfg, gasto_plano=float(e.get("custo_estimado") or 0), tentativas=e["tentativas"], minutos=minutos)
    plano = correcoes.escolher(correcoes.classificar(insp.get("problemas") or [], insp.get("bloqueios") or []), ctx)
    e["correcao_plano"] = plano
    if correcoes.precisa_gerar(plano):
        return None
    return plano


def rodar(roteiro, job, planos=None, max_refacoes=None, teto=None, simular=False, run=rodar_cmd, aviso_s=60.0, saida=print):
    """aviso_s: de quanto em quanto tempo o progresso (tempo + %) é avisado enquanto um take demora (0 = só a cada take)."""
    import progresso as prog
    roteiro = os.path.abspath(roteiro)
    lista = candidatos(ler(roteiro), os.path.dirname(roteiro), planos)
    with prog.Progresso(os.path.dirname(roteiro), len(lista), "simulação dos takes" if simular else "geração dos takes",
                        intervalo=aviso_s, saida=saida) as pg:
        return _rodar(roteiro, job, planos, max_refacoes, teto, simular, run, pg)


def _rodar(roteiro, job, planos, max_refacoes, teto, simular, run, pg):
    import time
    import projeto as pj
    roteiro = os.path.abspath(roteiro)
    base = os.path.dirname(roteiro)
    d = ler(roteiro)
    st = ler_estado(base)
    novo_fluxo = os.path.isfile(os.path.join(base, "projeto.json"))
    cfg = pj.carregar(base)
    lim = cfg["limites"]
    if max_refacoes is None:
        max_refacoes = int(lim.get("max_refacoes_plano", 2)) if novo_fluxo else 2
    gasto = 0.0  # 2026-11-07: --teto é desta RODADA (o acumulado do vídeo é o teto do roteador, não este)
    parar = None
    bloqueio = None  # bloqueio de orçamento: registrado uma vez; planos seguintes não chamam o roteador de novo
    anterior = None
    for p, rota in candidatos(d, base, planos):
        if anterior:
            pg.passo(anterior)  # take anterior concluído (qualquer desfecho) → avisa tempo + %
        pid = anterior = p["id"]
        pg.atual = pid
        e = st["planos"].setdefault(pid, {"estado": "pendente", "tentativas": 0, "custo_estimado": 0.0, "motivos": [], "historico": []})
        e["rota"] = rota
        clip = os.path.join(base, "assets", "clips", f"{pid}.mp4")
        if os.path.exists(clip) and ig.estado_inspecao(base, pid, clip)[0] == ig.APROVADO:
            e["estado"] = "aprovado"  # clipe já aprovado (mesmo sha) vale mesmo sem a imagem-chave com o nome do plano
            continue
        if e["estado"] == "marcado":
            continue
        if not os.path.isfile(os.path.join(base, "assets", "img", f"{pid}.png")):
            e["estado"] = "aguardando_imagem"
            continue
        if GERA[rota] == "lipsync" and not os.path.isfile(os.path.join(base, "assets", "voz", f"{pid}.wav")):
            e["estado"] = "aguardando_voz"
            continue
        if e["estado"] == "corrigir_em_codigo" and os.path.exists(clip):
            continue  # correção barata pendente na montagem — não gasta com novo take
        # um clipe que já existe e ainda não foi inspecionado é assistido antes de gastar com outro
        if not simular and os.path.exists(clip) and ig.estado_inspecao(base, pid, clip)[0] != ig.REPROVADO:
            est, _ = inspecionar(roteiro, pid, run)
            if est == ig.APROVADO:
                e.update(estado="aprovado", nota=nota_de(base, pid))
                gravar_estado(base, st)
                continue
        if bloqueio and not simular:
            e["estado"] = "precisa_orcamento"
            e["bloqueio"] = f"mesmo bloqueio de {bloqueio[0]}"  # sem repetir a mensagem nem chamar o roteador
            continue
        if novo_fluxo and not simular:
            ok_img, est_img, motivo_img = checar_imagem(roteiro, base, pid, cfg, run)
            if not ok_img:
                e["estado"] = est_img
                if motivo_img and motivo_img not in e["motivos"]:
                    e["motivos"].append(motivo_img)
                gravar_estado(base, st)
                continue
        t0_plano = time.time() - float(e.get("minutos", 0)) * 60
        while True:
            extra = correcao(base, pid) if e["tentativas"] else ""
            arq = tarefa(p, base, job, rota, e["tentativas"] + 1, extra)
            if simular:
                cod, txt = run([PY, os.path.join(AQUI, "provedores.py"), "planejar", arq])
                e["estado"], e["plano"] = "simulado", txt.strip().splitlines()[-6:]
                break
            if teto is not None and gasto >= teto:
                parar = f"teto desta rodada (US$ {teto:.2f}) atingido"
                break
            cod, txt = run([PY, os.path.join(AQUI, "provedores.py"), "executar", arq])
            r = ler_resultado(txt)
            e["tentativas"] += 1
            custo = float(r.get("estimated_cost_usd") or 0)
            e["custo_estimado"] = round(float(e.get("custo_estimado") or 0) + custo, 4)
            gasto += custo
            e["historico"].append({"tentativa": e["tentativas"], "provedor": r.get("provider"), "resultado": r.get("status"),
                                   "custo": custo, "quando": agora()})
            if r.get("status") == "waiting_approval":
                e["tentativas"] -= 1  # nada foi gerado
                e["estado"], parar = "precisa_orcamento", r.get("motivo") or "teto do roteador"
                bloqueio = (pid, parar)
                break
            if r.get("status") == "pendente_verificacao":
                e["estado"] = "pendente_verificacao"
                e["motivos"].append(f"job pago sem resposta ({r.get('job_remoto')}) — recuperar, não gerar outro")
                break
            if r.get("status") != "success":
                e["estado"] = "erro"
                e["motivos"].append(str(r.get("motivo"))[:300])
                break
            est, _ = inspecionar(roteiro, pid, run)
            e["nota"] = nota_de(base, pid)
            if est == ig.APROVADO and GERA[rota] == "lipsync":  # fala em quadro: a boca também é MEDIDA (atraso, boca parada)
                lc, ltxt = run([PY, os.path.join(AQUI, "conferencia.py"), "lipsync", roteiro, "--planos", pid])
                if lc == 2:
                    est = ig.REPROVADO
                    e["motivos"].append("lip-sync medido reprovou: " + (ltxt.strip().splitlines() or [""])[-1][:160])
                elif lc != 0:
                    e["motivos"].append("lip-sync medido inconclusivo — vale a revisão visual da boca")
            if est == ig.APROVADO:  # diretor de atuação (emoção/intensidade/exagero) e figurino (ficha) assistem o take
                for esp in ("atuacao", "figurino"):
                    ec, etxt = run([PY, os.path.join(AQUI, "especialistas.py"), esp, roteiro, "--planos", pid])
                    graves = []
                    if ec == 2:  # o inspetor (contrato) é o portão; especialista só bloqueia com falha GRAVE (exagero, emoção, rosto, traço)
                        try:
                            esp_j = json.load(io.open(os.path.join(base, "entrega", f"inspecao-{esp}.json"), encoding="utf-8"))
                            it3 = next((x for x in esp_j.get("itens", []) if x.get("id") == pid), None) or {}
                            graves = [t for g, t in it3.get("problemas") or [] if g == "grave"]
                        except (OSError, ValueError):
                            graves = ["relatório ilegível"]
                    if graves:
                        est = ig.REPROVADO
                        e["motivos"].append(f"{esp} reprovou (grave): " + "; ".join(graves)[:200])
                    elif ec == 2:
                        e["motivos"].append(f"{esp}: só avisos médios — fica para a revisão do diretor")
                    elif ec != 0:
                        e["motivos"].append(f"{esp} não verificado (sem Gemini) — olhar a folha de quadros")
            try:  # o veredito do inspetor ensina o roteador (taxa de aproveitamento real por provedor)
                import provedores as _pv
                if est in (ig.APROVADO, ig.REPROVADO):
                    _pv.registrar_veredito(job, pid, r.get("provider"), est)
            except Exception:  # noqa: BLE001 — aprendizado nunca derruba a produção
                pass
            if est == ig.APROVADO:
                e["estado"] = "aprovado"
                break
            if est == ig.NAO_VERIFICADO:
                e["estado"] = "revisao_diretor"
                e["motivos"].append(f"sem revisão visual — olhar entrega/inspecao/{pid}.jpg e gravar `inspetor.py revisar`")
                break
            if est != ig.REPROVADO:
                e["estado"] = "erro"
                e["motivos"].append("inspetor falhou")
                break
            rej = os.path.join(base, "assets", "clips", "rejeitados")
            os.makedirs(rej, exist_ok=True)
            if os.path.exists(clip):
                shutil.move(clip, os.path.join(rej, f"{pid}-t{e['tentativas']}.mp4"))
            e["motivos"].append(f"take {e['tentativas']} reprovado (nota {e.get('nota')}): {correcao(base, pid)[:200]}")
            minutos = (time.time() - t0_plano) / 60
            e["minutos"] = round(minutos, 2)
            if novo_fluxo:  # correção de menor custo ANTES de pagar outro take
                barato = tentar_corrigir_barato(base, pid, d, cfg, e, minutos)
                if barato:
                    import correcoes
                    tomada = os.path.join(rej, f"{pid}-t{e['tentativas']}.mp4")
                    if os.path.exists(tomada) and not os.path.exists(clip):
                        shutil.copyfile(tomada, clip)  # o take volta: vai ser corrigido em código (cópia fica em rejeitados)
                    for x in barato:
                        correcoes.registrar(base, pid, x["opcao"], x["como"], estado="pendente", defeito=x["defeito"])
                    e["estado"] = "corrigir_em_codigo"
                    e["motivos"].append("correção sem gasto: " + "; ".join(f"{x['defeito']}→{x['opcao']}" for x in barato))
                    break
                gasto_plano = float(e.get("custo_estimado") or 0)
                if (lim.get("max_gasto_plano") is not None and gasto_plano >= float(lim["max_gasto_plano"])) or \
                        (lim.get("max_minutos_plano") is not None and minutos >= float(lim["max_minutos_plano"])):
                    e["estado"] = "marcado"
                    e["motivos"].append(f"limite do plano (US$ {gasto_plano:.2f} / {minutos:.0f} min) — mantido com ressalva")
                    break
            if e["tentativas"] > max_refacoes:
                e["estado"] = "marcado"
                break
        gravar_estado(base, st)
        if parar and not bloqueio:  # teto desta RODADA: para; bloqueio de orçamento: segue sem chamar o roteador
            break
    if anterior and not (parar and not bloqueio):
        pg.passo(anterior)
    gravar_estado(base, st)
    relatorio(base, st, parar)
    return st, parar


ROTULO = {"aprovado": "✅ aprovado", "marcado": "⚠️ marcado (refações esgotadas)", "revisao_diretor": "👁 revisão do diretor",
          "aguardando_imagem": "🖼 aguardando imagem", "aguardando_voz": "🎙 aguardando voz", "precisa_orcamento": "💰 precisa orçamento",
          "pendente_verificacao": "⏳ job pago sem resposta", "corrigir_em_codigo": "🛠 corrigir em código (sem gasto)",
          "imagem_reprovada": "🖼❌ imagem-chave reprovada", "revisao_imagem": "🖼👁 revisar imagem-chave", "erro": "❌ erro", "simulado": "🧪 simulado", "pendente": "· pendente"}


def relatorio(base, st, parar=None):
    linhas = ["# Modo autônomo — relatório dos takes", "", f"Atualizado: {st.get('atualizado', agora())}", ""]
    if parar:
        linhas += [f"**Parou:** {parar}", ""]
    linhas += ["| Plano | Rota | Estado | Tentativas | Nota | Custo est. |", "|---|---|---|---|---|---|"]
    total = 0.0
    for pid, e in st["planos"].items():
        total += float(e.get("custo_estimado") or 0)
        linhas.append(f"| {pid} | {e.get('rota', '')} | {ROTULO.get(e['estado'], e['estado'])} | {e.get('tentativas', 0)} | "
                      f"{e.get('nota') if e.get('nota') is not None else '—'} | US$ {float(e.get('custo_estimado') or 0):.2f} |")
    linhas += ["", f"**Total estimado:** US$ {total:.2f}", ""]
    for pid, e in st["planos"].items():
        if e.get("motivos"):
            linhas += [f"- **{pid}**: " + " · ".join(e["motivos"][-3:])]
    io.open(os.path.join(base, "entrega", "autonomo-relatorio.md"), "w", encoding="utf-8").write("\n".join(linhas) + "\n")


def status(roteiro):
    base = os.path.dirname(os.path.abspath(roteiro))
    st = ler_estado(base)
    for pid, e in st["planos"].items():
        print(f"  {pid:6s} {ROTULO.get(e['estado'], e['estado']):32s} tent. {e.get('tentativas', 0)}  nota {e.get('nota')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["rodar", "status"])
    ap.add_argument("roteiro")
    ap.add_argument("--job")
    ap.add_argument("--planos")
    ap.add_argument("--max-refacoes", type=int, default=None, help="padrão: limites.max_refacoes_plano do projeto.json (2)")
    ap.add_argument("--teto", type=float, help="teto desta rodada em US$ (além do teto do roteador)")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--aviso-s", type=float, default=60.0, help="progresso (tempo + %%) a cada N s enquanto um take demora (0 = só por take)")
    a = ap.parse_args()
    if a.acao == "status":
        return status(a.roteiro)
    if not a.job:
        sys.exit("rodar precisa de --job (o id do vídeo no roteador)")
    st, parar = rodar(a.roteiro, a.job, a.planos, a.max_refacoes, a.teto, a.simular, aviso_s=a.aviso_s)
    status(a.roteiro)
    print(f"\nrelatório: entrega/autonomo-relatorio.md{' · PAROU: ' + parar if parar else ''}")
    sys.exit(4 if parar else 0)


if __name__ == "__main__":
    main()
