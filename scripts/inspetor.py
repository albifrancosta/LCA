"""Supervisor de qualidade: REPROVA o que não cumpre o contrato e manda refazer só aquele plano — nunca aprova
automaticamente o arquivo que a API devolveu.

Verificações (✅ objetivas e locais, grátis · 👁 visuais, Gemini se houver cota, senão folha de quadros para o Claude olhar):
  ✅ movimento   modo acao/fala/reacao precisa de movimento PRÓPRIO (movimento.py); zoom/pan sozinho = reprovado
  ✅ atuação     o PERSONAGEM se mexe (não só o cenário), cada parte exigida no contrato, até o fim do plano, sem
                 proporções pulando (atuacao.py)
  ✅ nota        0–100: atuação 25 · consistência 20 · física 20 · direção 15 · áudio/lip-sync 10 · ritmo 10; mínimo 85
                 sem falha grave. Componente sem medição (ex.: física sem revisão visual) = nota PARCIAL
  ✅ duração     o clipe cobre a duração do contrato
  ✅ fala        o áudio de cada fala bate com o roteiro (whisper local, números normalizados); sem início/fim cortado
  ✅ legenda     a palavra na tela é a palavra ouvida naquele instante
  👁 ação/identidade/mãos/lip-sync   critérios do contrato, ficha do personagem, deformações, boca no tempo da fala

Uso (na pasta filme/):
  python inspetor.py planos roteiro.json [--planos p05,p10] [--registrar]   → cada clipe contra o contrato
  python inspetor.py audio roteiro.json                                      → cada fala contra o roteiro
  python inspetor.py filme roteiro.json entrega/filme.mp4                     → o filme montado: falas, legenda e movimento por plano
  python inspetor.py revisar roteiro.json --planos d2 --estado aprovado --nota "recua e levanta os braços; mãos ok"
                                                       → decisão da revisão visual (folha de quadros), só para o mesmo arquivo
Estados: aprovado | reprovado | nao_verificado — só aprovado entra na montagem final (montar_historia lê
entrega/inspecao-planos.json → itens[{id, estado, sha256_clipe}]).
Saída: entrega/inspecao-<modo>.md + .json · folhas em entrega/inspecao/<plano>.jpg. Código: 2 reprovado · 3 não verificado.
--registrar ensina o roteador (aprovado/reprovado por modelo e tipo de cena). Reprovado → refazer só ele.
"""
import argparse
import base64
import io
import json
import re
import os
import subprocess
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402
import movimento  # noqa: E402
from tts_gemini import URL, _modelo_whisper, chave, cobertura  # noqa: E402

ANIMADOS = {"acao", "fala", "reacao"}
VISUAL = """Você é supervisor de qualidade de um estúdio de animação. Assista ao CLIPE (e veja as FICHAS de personagem
anexadas, se houver) e julgue com rigor se ele cumpre o contrato do plano:
{contrato}
Responda só JSON: {{"criterios": [{{"criterio": "…", "ok": true/false, "visto": "o que aparece", "gravidade": "leve|media|grave"}}],
"identidade_ok": true/false, "deformacoes": ["mãos, dedos, objetos ou rostos deformados, com o segundo"],
"boca": "fala_sincronizada|fala_fora_de_tempo|boca_parada|boca_mexendo_sem_fala|nao_se_aplica",
"atuacao": "o personagem atua (expressão muda, corpo se mexe) ou fica congelado?", "nota": 0-10}}
Marque grave: ação pedida não acontece; personagem diferente da ficha; deformação evidente; boca parada quando ele fala."""


def dur(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def folha(video, saida, n=6, ini=0.0, fim=None):
    """Folha com n quadros do trecho (revisão visual pelo Claude quando não há Gemini)."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(video)
    total = (fim if fim is not None else dur(video)) - ini
    qs = []
    for k in range(n):
        t = ini + total * (k + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, q = cap.read()
        if ok:
            h, w = q.shape[:2]
            q = cv2.resize(q, (300, int(h * 300 / w)))
            cv2.putText(q, f"{t:.1f}s", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            qs.append(q)
    cap.release()
    if not qs:
        return None
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    cv2.imwrite(saida, np.hstack(qs), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return saida


def _mime(arq):
    return {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        os.path.splitext(arq)[1].lower(), "application/octet-stream")


def gemini_visual(arquivo, texto, refs=(), modelo=None):
    """UMA chamada multimodal (fichas primeiro, depois o arquivo). Devolve o JSON visto + "_uso" (usageMetadata) ou
    {"indisponivel": motivo}. `texto` vem de qa_visual.pedido (contrato + figurino + anatomia + aparelhos + textos)."""
    import qa_visual as qv
    modelo = modelo or qv.modelo_analise()
    partes = [{"inline_data": {"mime_type": _mime(f), "data": base64.b64encode(open(f, "rb").read()).decode()}} for f in refs]
    partes.append({"inline_data": {"mime_type": _mime(arquivo), "data": base64.b64encode(open(arquivo, "rb").read()).decode()}})
    partes.append({"text": texto})
    corpo = {"contents": [{"parts": partes}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    try:
        req = urllib.request.Request(URL.format(m=modelo), data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.load(r)
        vis = json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
        vis["_uso"] = resp.get("usageMetadata")
        return vis
    except urllib.error.HTTPError as e:
        return {"indisponivel": f"Gemini {e.code}: {e.read().decode(errors='replace')[:120]}", "_cobrado": e.code not in (400, 401, 403, 429)}
    except urllib.error.URLError as e:
        return {"indisponivel": f"sem rede: {e.reason}", "_cobrado": False}
    except (SystemExit, KeyError, ValueError, IndexError) as e:  # sem chave / resposta sem JSON
        return {"indisponivel": f"resposta inválida/sem chave: {str(e)[:80]}", "_cobrado": False}


def analisar_visual(base, arquivo, c, d, quem, pid, tipo="clipe", chamar=None):
    """Inspeção visual com fichas REAIS, cache por hash e custo no livro do projeto. Devolve (vis, refs, faltando).
    vis = {"indisponivel": ...} quando não houve análise (sem cota, custo_zero, sem orçamento) → vira revisão pela folha."""
    import qa_visual as qv
    chamar = chamar or gemini_visual
    refs, faltando = qv.referencias(base, d, quem)
    modelo = qv.modelo_analise()
    chave_c = qv.chave_cache(ig.sha256(arquivo), refs, c, modelo, tipo)
    vis = qv.cache_ler(base, chave_c)
    if vis is not None:
        vis["_cache"] = True
        return vis, refs, faltando
    s = ig.sonda(arquivo) if tipo == "clipe" else None
    est = qv.estimar_analise(s["duracao"] if s else 0.0, len(refs) + (tipo != "clipe"), modelo)
    ok, rid, motivo = qv.reservar_analise(base, pid, est, modelo)
    if not ok:
        return {"indisponivel": f"análise não autorizada: {motivo}"}, refs, faltando
    vis = chamar(arquivo, qv.pedido(c, qv.fichas_texto(d, quem), tipo), [r["arquivo"] for r in refs], modelo)
    if "indisponivel" in vis:
        qv.confirmar_analise(rid, falhou=not vis.get("_cobrado"), modelo=modelo)
        return vis, refs, faltando
    qv.confirmar_analise(rid, uso=vis.get("_uso"), modelo=modelo)
    qv.cache_gravar(base, chave_c, vis)
    return vis, refs, faltando


PESOS = {"atuacao": 25, "consistencia": 20, "fisica": 20, "direcao": 15, "audio": 10, "ritmo": 10}
NOTA_MINIMA = 85
PENA = {"grave": 35, "media": 12, "leve": 4}


def nota(r, c):
    """Nota 0–100 do plano com os pesos da direção (2026-11-06). Componente sem medição fica de fora e a nota sai PARCIAL."""
    comp = {}
    if r.get("atuacao") and r["atuacao"].get("nota_atuacao") is not None:  # não verificado = fora da nota (nota PARCIAL)
        comp["atuacao"] = r["atuacao"]["nota_atuacao"]
    elif r.get("movimento"):
        comp["atuacao"] = 100 if r["movimento"]["veredito"] == "animado" else 20
    prop = [g for g, t in r["problemas"] if "proporção" in t or "some/aparece" in t]
    vis = r.get("revisao_visual") or {}
    if not vis.get("pendente") and vis:
        prop += ["grave"] * (vis.get("identidade_ok") is False) + ["media"] * len(vis.get("deformacoes") or [])
        fis = [k for k in vis.get("criterios", []) if not k.get("ok")]
        comp["fisica"] = max(0, 100 - sum(PENA.get(k.get("gravidade", "media"), 12) for k in fis))
        if c.get("voz") == "em_quadro":
            comp["audio"] = 100 if (vis.get("boca") == "fala_sincronizada" or vis.get("boca_medida") == "aprovada") else 30
    if (r.get("atuacao") or {}).get("nota_atuacao") is not None or (vis and not vis.get("pendente")):
        comp["consistencia"] = max(0, 100 - sum(PENA[g] for g in prop))
    campos = ("modo", "enquadramento", "camera", "quadro_inicial", "quadro_final", "criterios", "beats", "exige")
    comp["direcao"] = round(100 * sum(bool(c.get(k)) for k in campos) / len(campos))
    if c.get("voz") != "em_quadro":
        comp.setdefault("audio", 100 if not any("fala" in t for g, t in r["problemas"]) else 50)
    if c.get("duracao") and r.get("duracao_clipe"):
        comp["ritmo"] = 100 if r["duracao_clipe"] + 0.05 >= float(c["duracao"]) else 60
    peso = sum(PESOS[k] for k in comp)
    valor = round(sum(PESOS[k] * v for k, v in comp.items()) / peso) if peso else None
    faltam = [k for k in PESOS if k not in comp]
    return {"valor": valor, "componentes": comp, "parcial": bool(faltam), "faltam": faltam}


def fichas_de(base, quem, d=None):
    """2026-11-07: CORRIGIDO — procurava ../producao.json (a pasta de TODOS os projetos) e nunca achava as fichas do
    projeto; o Gemini inspecionou um filme inteiro sem ficha. Agora: roteiro.elenco[q].ref → producao.json do projeto."""
    import qa_visual as qv
    if d is None:
        rot = os.path.join(base, "roteiro.json")
        d = json.load(io.open(rot, encoding="utf-8")) if os.path.exists(rot) else {}
    return [r["arquivo"] for r in qv.referencias(base, d, quem)[0]]


def aplicar_visual(r, vis, c, d, quem, refs, faltando):
    """Junta a resposta visual ao resultado: completude do contrato (critérios) separada da qualidade visual; bloqueios
    objetivos sempre graves; campo sem resposta = pendência (não verificado)."""
    import qa_visual as qv
    r["revisao_visual"] = {k: v for k, v in vis.items() if k != "_uso"}
    r["refs_enviadas"] = [{"personagem": x["personagem"], "sha256": x["sha256"][:12], "origem": x["origem"]} for x in refs]
    if faltando:
        r["pendencias"].append(f"sem ficha de {', '.join(faltando)} — identidade/figurino não verificáveis")
    crit = vis.get("criterios") or []
    for k in crit:
        if not k.get("ok"):
            r["problemas"].append((k.get("gravidade", "media"), f"{k.get('criterio')}: {k.get('visto')}"))
    r["completude_contrato"] = round(100 * sum(1 for k in crit if k.get("ok")) / len(crit)) if crit else None
    r["qualidade_visual"] = vis.get("qualidade_visual")
    bl = qv.bloqueios(vis, c, (d or {}).get("elenco") or {}, quem)
    r["bloqueios"] = [cod for g, cod, _ in bl if g == "grave"]
    r["problemas"] += [(g, t) for g, _, t in bl]
    for falta in qv.evidencia_faltando(vis, c, quem, tem_refs=bool(refs)):
        r["pendencias"].append(f"sem evidência: {falta}")


def inspecionar_plano(base, p, registrar=False, d=None, visual=None):
    c = p.get("direcao") or {}
    if d is None:
        rot = os.path.join(base, "roteiro.json")
        d = json.load(io.open(rot, encoding="utf-8")) if os.path.exists(rot) else {}
    clip = os.path.join(base, "assets", "clips", f"{p['id']}.mp4")
    r = {"id": p["id"], "modo": c.get("modo"), "problemas": [], "revisao_visual": None, "pendencias": []}
    ok_midia, motivo_midia = ig.midia_valida(clip, "video")
    if not ok_midia:
        if c.get("modo") in ANIMADOS:
            r["problemas"].append(("grave", f"modo {c.get('modo')} sem clipe válido ({motivo_midia}) — foto + zoom não vale como atuação"))
            r["estado"], r["veredito"] = ig.REPROVADO, "reprovado"
        else:
            r["estado"], r["veredito"] = ig.APROVADO, "sem_clipe_ok"  # insert/estabelecimento/título: imagem permitida
        return r
    r["sha256_clipe"] = ig.sha256(clip)
    v, _, _ = movimento.analisar(clip)
    r["movimento"] = v
    r["duracao_clipe"] = round(dur(clip), 2)
    if c.get("modo") in ANIMADOS and v["veredito"] != "animado":
        r["problemas"].append(("grave", f"{v['veredito'].replace('_', ' ')}: movimento próprio em {v['animado']:.0%} dos quadros "
                                        f"(precisa ≥ 35 %) — câmera se mexendo não é atuação"))
    if c.get("modo") in ANIMADOS:
        import atuacao
        n_pers = max(1, len(c.get("quem") or p.get("quem") or []))  # o contrato manda (p["quem"] pode ser herdado de outro plano)
        at, _ = atuacao.analisar(clip, exige=c.get("exige") or [], beats=c.get("beats"), n_personagens=n_pers)
        r["atuacao"] = {k: at[k] for k in ("estado", "veredito", "nota_atuacao", "mov_personagem", "mov_cenario", "energia_tercos",
                                           "beats", "regioes") if k in at}
        r["problemas"] += [(g, f"atuação: {t}") for g, t in at["problemas"]]
        if at["estado"] == ig.NAO_VERIFICADO and (c.get("quem") or p.get("quem")):
            r["pendencias"].append("atuação (YOLO não conseguiu medir o personagem do contrato)")
    # 2026-11-06: avatar de fala (Kling Avatar: cabeça e boca) não é take de corpo — "quase parado"/"só câmera" ali não é
    # defeito; a atuação desse plano é rosto + boca (lip-sync medido e revisão visual). Vira aviso, registrado.
    if c.get("modo") == "fala" and ((c.get("rota") or {}).get("rota") == "avatar"):
        corpo = [x for x in r["problemas"] if re.search(r"movimento próprio|quase parado|congelad|sem atuação|parte .* parada", x[1])]
        for x in corpo:
            r["problemas"].remove(x)
            r.setdefault("avisos", []).append(f"avatar de fala (corpo não se avalia): {x[1][:120]}")
    if c.get("duracao") and dur(clip) + 0.05 < float(c["duracao"]):
        r["problemas"].append(("media", f"clipe de {dur(clip):.1f}s, contrato pede {c['duracao']}s"))
    quem = c.get("quem") or p.get("quem") or []
    vis, refs, faltando = analisar_visual(base, clip, c, d, quem, p["id"], "clipe", chamar=visual)
    if "indisponivel" in vis:
        f = folha(clip, os.path.join(base, "entrega", "inspecao", f"{p['id']}.jpg"))
        r["revisao_visual"] = {"pendente": True, "motivo": vis["indisponivel"], "folha": f, "criterios": c.get("criterios", []),
                               "fisica": c.get("fisica"), "beats": [b.get("evidencia") or b.get("pt") for b in c.get("beats") or []],
                               "conferir": ["braços/mãos por pessoa (2 cada)", "peças no corpo × ficha (gravata!)",
                                            "tela dos aparelhos voltada para quem usa (nada nas costas)", "texto/símbolo desenhado pelo clipe"]}
        r["refs_enviadas"] = [{"personagem": x["personagem"], "sha256": x["sha256"][:12], "origem": x["origem"]} for x in refs]
        r["pendencias"].append("revisão visual (ação, física, identidade, anatomia, figurino, aparelhos, textos, boca)")
        if faltando:
            r["pendencias"].append(f"sem ficha de {', '.join(faltando)} — identidade/figurino não verificáveis")
    else:
        aplicar_visual(r, vis, c, d, quem, refs, faltando)
        if c.get("voz") == "em_quadro" and vis.get("boca") != "fala_sincronizada":
            r["problemas"].append(("grave", f"lip-sync: {vis.get('boca')}"))
        # 2026-11-06: a MEDIÇÃO (conferencia.py lipsync: atraso boca × voz, boca parada) do MESMO arquivo vence a opinião
        # visual do Gemini sobre a boca, que oscilou entre takes (fechada / fora de tempo / ok). Medição reprovada ou
        # ausente: nada muda. Vira aviso, registrado.
        try:
            med = next((i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-lipsync.json"), encoding="utf-8")).get("itens", [])
                        if i.get("id") == p["id"]), None)
        except (OSError, ValueError):
            med = None
        if med and med.get("estado") == ig.APROVADO and med.get("sha256_clipe") == r["sha256_clipe"]:
            vis["boca_medida"] = "aprovada"
            labios = [x for x in r["problemas"] if re.search(r"lip-?sync|boca|lábio|labio", x[1], re.I)]
            for x in labios:
                r["problemas"].remove(x)
                r.setdefault("avisos", []).append(f"medição aprovou (atraso {med.get('atraso_ms')} ms) — Gemini viu: {x[1][:120]}")
    r["nota"] = nota(r, c)
    if r["nota"]["valor"] is not None and r["nota"]["valor"] < NOTA_MINIMA and not r["nota"]["parcial"]:
        r["problemas"].append(("grave", f"nota {r['nota']['valor']}/100 abaixo de {NOTA_MINIMA}"))
    graves = [x for x in r["problemas"] if x[0] == "grave"]
    pendente = bool(r["pendencias"])
    r["estado"] = ig.estado_qa(r["problemas"], verificado=not pendente)  # P02: pendente NUNCA é aprovado
    r["veredito"] = {ig.REPROVADO: "reprovado", ig.NAO_VERIFICADO: "nao_verificado"}.get(
        r["estado"], "aprovado_com_ressalvas" if r["problemas"] else "aprovado")
    if registrar and r["estado"] != ig.NAO_VERIFICADO:
        meta = clip + ".json"
        modelo = json.load(open(meta, encoding="utf-8")).get("modelo") if os.path.exists(meta) else None
        if modelo:
            subprocess.run([sys.executable, os.path.join(AQUI, "roteador.py"), "--resultado", modelo, "personagem",
                            "reprovado" if graves else "aprovado"], check=False)
    return r


def inspecionar_imagem(base, p, d=None, visual=None):
    """Imagem-chave ANTES de gastar com o clipe (c06c/c07a: a tela já estava nas costas do aparelho na imagem).
    Mesmos bloqueios objetivos do clipe; resultado vale só para o mesmo sha256 (entrega/inspecao-imagens.json)."""
    c = p.get("direcao") or {}
    if d is None:
        d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    img = os.path.join(base, "assets", "img", f"{p['id']}.png")
    r = {"id": p["id"], "problemas": [], "pendencias": [], "tipo": "imagem"}
    ok, motivo = ig.midia_valida(img, "imagem")
    if not ok:
        r.update(estado=ig.NAO_VERIFICADO, motivo=motivo)
        return r
    r["sha256_imagem"] = ig.sha256(img)
    quem = c.get("quem") or p.get("quem") or []
    vis, refs, faltando = analisar_visual(base, img, c, d, quem, p["id"], "imagem", chamar=visual)
    if "indisponivel" in vis:
        r["refs_enviadas"] = [{"personagem": x["personagem"], "sha256": x["sha256"][:12], "origem": x["origem"]} for x in refs]
        r["pendencias"].append(f"revisão visual da imagem ({vis['indisponivel'][:80]}) — olhar {os.path.relpath(img, base)}: braços, peças × ficha, "
                               "tela dos aparelhos voltada para quem usa, texto desenhado")
    else:
        aplicar_visual(r, vis, {k: v for k, v in c.items() if k != "criterios"}, d, quem, refs, faltando)  # critérios são de movimento
    r["estado"] = ig.estado_qa(r["problemas"], verificado=not r["pendencias"])
    return r


def estado_imagem(base, pid):
    """Estado da inspeção da imagem-chave atual (mesmo sha) — nao_verificado se não houver."""
    img = os.path.join(base, "assets", "img", f"{pid}.png")
    try:
        it = next(i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-imagens.json"), encoding="utf-8"))["itens"] if i["id"] == pid)
    except (OSError, ValueError, StopIteration, KeyError):
        return ig.NAO_VERIFICADO, None
    if not os.path.isfile(img) or it.get("sha256_imagem") != ig.sha256(img):
        return ig.NAO_VERIFICADO, None
    return it.get("estado", ig.NAO_VERIFICADO), it


def adaptar(roteiro, pid, mudanca, motivo):
    """Adaptação editorial (ex.: fala em quadro → voz em off): revisa o CONTRATO, guarda a versão anterior do roteiro e a
    reprovação original, e derruba a inspeção para nao_verificado — o take tem de passar de novo, agora contra o contrato
    revisado. Nunca vira aprovação limpa automática."""
    import datetime
    import shutil as sh
    base = os.path.dirname(os.path.abspath(roteiro))
    d = json.load(io.open(roteiro, encoding="utf-8"))
    p = next((x for x in d["planos"] if x["id"] == pid), None)
    if not p:
        sys.exit(f"{pid} não está no roteiro")
    quando = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    sh.copyfile(roteiro, os.path.join(base, f"roteiro-antes-adaptacao-{pid}-{quando}.json"))
    antes = json.loads(json.dumps(p.get("direcao") or {}))
    p.setdefault("direcao", {}).update(mudanca)
    p["direcao"].setdefault("adaptacoes", []).append({"mudanca": mudanca, "motivo": motivo, "quando": quando})
    ig.gravar_json_atomico(roteiro, d)
    jarq = os.path.join(base, "entrega", "inspecao-planos.json")
    original = None
    if os.path.exists(jarq):
        ins = json.load(io.open(jarq, encoding="utf-8"))
        it = next((i for i in ins.get("itens", []) if i.get("id") == pid), None)
        if it:
            original = {k: it.get(k) for k in ("estado", "veredito", "problemas", "nota", "sha256_clipe")}
            it.setdefault("reprovacoes_originais", []).append(original)
            it.update(estado=ig.NAO_VERIFICADO, veredito="nao_verificado", adaptacao={"motivo": motivo, "mudanca": mudanca},
                      pendencias=["contrato revisado por adaptação editorial — inspecionar de novo contra o contrato novo"])
            ig.gravar_json_atomico(jarq, ins)

    def f(reg):
        reg.setdefault("adaptacoes", []).append({"plano": pid, "contrato_antes": antes, "contrato_depois": p["direcao"], "motivo": motivo,
                                                 "reprovacao_original": original, "quando": quando})
    ig.atualizar_json(os.path.join(base, "entrega", "adaptacoes.json"), f, padrao={"adaptacoes": []})
    print(f"{pid}: contrato revisado ({motivo}); inspeção → nao_verificado. Rode `inspetor.py planos --planos {pid}`.")


def palavras(arq, ini=0.0, fim=None):
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"insp-{os.getpid()}.wav")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(ini)] + (["-to", str(fim)] if fim else []) + ["-i", arq, "-ac", "1", "-ar", "16000", tmp]
    subprocess.run(cmd, check=True)
    # vocabulário da marca (config/marca.json, o mesmo do tts_gemini): sem ele o whisper erra nomes próprios
    segs, _ = _modelo_whisper().transcribe(tmp, language="pt", word_timestamps=True, initial_prompt=__import__("marca").vocabulario())
    return [(w.start + ini, w.end + ini, w.word.strip()) for s in segs for w in s.words]


def minimo(texto):
    return 0.85 if len(texto.split()) > 5 else 1.0


def checar_fala(arq, texto):
    import wave

    import numpy as np
    ws = palavras(arq)
    cob = cobertura(texto, [w[2] for w in ws])
    prob = []
    if cob < minimo(texto):
        prob.append(("grave", f"só {cob:.0%} do texto reconhecido — ouvido: \"{' '.join(w[2] for w in ws)}\""))
    if os.path.exists(arq + ".suspeita"):
        prob.append(("media", "marcada como suspeita na geração"))
    if arq.endswith(".wav"):
        with wave.open(arq) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
            taxa = w.getframerate()
        borda = int(0.02 * taxa)
        pico = float(np.max(np.abs(x))) or 1
        if float(np.sqrt(np.mean(x[:borda] ** 2))) / pico > 0.12:
            prob.append(("media", "começa já no meio do som (início cortado)"))
        if float(np.sqrt(np.mean(x[-borda:] ** 2))) / pico > 0.12:
            prob.append(("media", "termina no meio do som (fim cortado)"))
    return cob, prob


def inspecionar_audio(base, d):
    out = []
    for p in d["planos"]:
        arq = os.path.join(base, "assets", "voz", f"{p['id']}.wav")
        if p.get("fala") and not os.path.exists(arq):
            out.append({"id": p["id"], "fala": p["fala"], "cobertura": 0, "estado": ig.REPROVADO, "veredito": "reprovado",
                        "problemas": [("grave", f"fala no roteiro sem áudio ({os.path.relpath(arq, base)})")]})
            print(f"  {p['id']} ❌ sem áudio: {p['fala'][:50]}")
            continue
        if p.get("fala"):
            cob, prob = checar_fala(arq, p["fala"])
            est = ig.estado_qa(prob, verificado=True)
            out.append({"id": p["id"], "fala": p["fala"], "cobertura": round(cob, 2), "problemas": prob, "estado": est,
                        "veredito": "reprovado" if est == ig.REPROVADO else "aprovado", "sha256_voz": ig.sha256(arq),
                        "texto_sha256": ig.sha256_texto(p["fala"])})
            print(f"  {p['id']} {'❌' if out[-1]['veredito'] == 'reprovado' else '✅'} {cob:.0%} {p['fala'][:50]}")
    return out


def manifesto(base):
    """Manifesto da montagem — historia.json (modo História, chave planos) ou video.json (base/comercial, chave cenas).
    Devolve (nome, itens com id/inicio/fim, palavras da legenda, json)."""
    for nome, chave in (("historia.json", "planos"), ("video.json", "cenas")):
        arq = os.path.join(base, "remotion", "src", nome)
        if os.path.exists(arq):
            h = json.load(io.open(arq, encoding="utf-8"))
            itens = [dict(c, id=c.get("id") or f"cena{i + 1}") for i, c in enumerate(h.get(chave, []))]
            leg = h.get("legenda", [])
            if isinstance(leg, dict):
                leg = leg.get("palavras") or leg.get("words") or []
            return nome, itens, leg, h
    sys.exit("sem manifesto de montagem (remotion/src/historia.json ou video.json) — monte antes de inspecionar o filme")


def decisoes_diretor(base):
    """entrega/decisoes-diretor.json: takes aprovados pelo diretor por cima do inspetor, cada um com sha256 e evidência."""
    arq = os.path.join(base, "entrega", "decisoes-diretor.json")
    if not os.path.isfile(arq):
        return {}
    return {x.get("take"): x for x in json.load(io.open(arq, encoding="utf-8")).get("decisoes", []) if x.get("take")}


def decisao_valida(decisoes, pid, base, md):
    """Vale só se o arquivo montado é o MESMO da decisão (sha256) e há evidência escrita."""
    dec = decisoes.get(pid)
    if not dec or not dec.get("sha256") or not dec.get("evidencia") or not md.get("arquivo"):
        return None
    arq = next((x for x in (os.path.join(base, md["arquivo"]), os.path.join(base, "remotion", "public", md["arquivo"])) if os.path.isfile(x)), None)
    return dec if arq and ig.sha256(arq) == dec["sha256"] else None


def inspecionar_filme(base, d, video, montagem=True):
    nome, itens, legenda, h = manifesto(base)
    tempos = {c["id"]: c for c in itens}
    for c in itens:  # 2026-11-07: plano composto dentro de outro (gancho, tela dividida) — confere no intervalo do que o contém
        for sub in c.get("inclui") or []:
            sid = sub if isinstance(sub, str) else sub.get("id")
            if sid and sid not in tempos:
                tempos[sid] = dict({} if isinstance(sub, str) else sub, id=sid, inicio=(sub.get("inicio") if isinstance(sub, dict) else None) or c["inicio"],
                                   fim=(sub.get("fim") if isinstance(sub, dict) else None) or c["fim"], dentro_de=c["id"])
    decisoes = decisoes_diretor(base)
    ws = palavras(video)
    _, pares, _ = movimento.analisar(video)
    res = []
    ids_roteiro = [p["id"] for p in d["planos"]]
    for extra in [i for i in tempos if i not in ids_roteiro and nome == "historia.json"]:
        res.append({"id": extra, "problemas": [("media", f"está no {nome} mas não no roteiro")], "estado": ig.NAO_VERIFICADO})
    for p in d["planos"]:
        t = tempos.get(p["id"])
        if not t:  # P11/P56: plano do roteiro que não entrou na montagem é falha, nunca "continue" silencioso
            res.append({"id": p["id"], "problemas": [("grave", f"plano do roteiro ausente na montagem ({nome})")],
                        "estado": ig.REPROVADO, "veredito": "reprovado"})
            continue
        r = {"id": p["id"], "de": t["inicio"], "ate": t["fim"], "problemas": []}
        md = t.get("midia") or {}
        if md.get("arquivo"):  # a mídia montada é a mesma que foi inspecionada?
            cand = [os.path.join(base, md["arquivo"]), os.path.join(base, "remotion", "public", md["arquivo"])]
            arq_m = next((x for x in cand if os.path.isfile(x)), None)
            if not arq_m:
                r["problemas"].append(("grave", f"mídia do manifesto não existe: {md['arquivo']}"))
            elif md.get("sha256") and ig.sha256(arq_m) != md["sha256"]:
                r["problemas"].append(("grave", "mídia trocada depois da montagem (sha256 diferente do manifesto)"))
        modo = (p.get("direcao") or {}).get("modo") or p.get("modo")
        if modo in ANIMADOS and md and md.get("qa_estado") not in (None, ig.APROVADO):
            r["problemas"].append(("grave", f"clipe montado com QA '{md.get('qa_estado')}' (só 'aprovado' entra no filme final)"))
        if p.get("fala"):
            ouvidas = [w[2] for w in ws if t["inicio"] - 0.25 <= (w[0] + w[1]) / 2 <= t["fim"] + 0.25]
            cob = cobertura(p["fala"], ouvidas)
            r["fala"] = round(cob, 2)
            if cob < minimo(p["fala"]):
                r["problemas"].append(("grave", f"fala {cob:.0%}: roteiro \"{p['fala']}\" × ouvido \"{' '.join(ouvidas)}\""))
        c = p.get("direcao") or {}
        v = movimento.veredito([x for x in pares if t["inicio"] <= x["t"] < t["fim"] - 0.13])
        r["movimento"] = v["veredito"]
        if c.get("modo") in ANIMADOS and v["veredito"] != "animado":
            dec = decisao_valida(decisoes, p["id"], base, md)
            if dec:  # decisão do diretor com o mesmo arquivo (sha256) e evidência: vira aviso registrado, não aprovação tácita
                r.setdefault("avisos", []).append(f"movimento {v['veredito']} aceito por decisão do diretor: {dec.get('decisao')} — {dec.get('contrapartida', '')[:100]}")
                r["excecao_diretor"] = {"decisao": dec.get("decisao"), "evidencia": dec.get("evidencia"), "sha256": dec.get("sha256")}
                r["reprovacao_original"] = dec.get("inspetor") or f"contrato {c.get('modo')}, mas na tela: {v['veredito']}"
            else:
                r["problemas"].append(("grave", f"contrato {c.get('modo')}, mas na tela: {v['veredito'].replace('_', ' ')}"))
        res.append(r)
    if montagem:  # 2026-11-07: congelamento/repetição por plano e por LADO da tela dividida, no MP4 final
        import qa_montagem
        import projeto as pj
        mres, mdur, mprob = qa_montagem.analisar_filme(base, video, cfg_duracao=pj.carregar(base)["duracao"], d=d)
        qa_montagem.gravar(base, mres, mdur, mprob)
        por_id = {x["id"]: x for x in res}
        for m in mres:
            alvos = [m["id"]] + [rg["id"] for rg in m["regioes"]]
            for g, txt in m["problemas"]:
                dono = next((por_id[a] for a in alvos[::-1] if a in por_id and a in txt), None) or next((por_id[a] for a in alvos if a in por_id), None)
                if dono is not None:
                    dono["problemas"].append((g, f"montagem: {txt}"))
        for g, txt in mprob:
            res.append({"id": "duracao", "problemas": [(g, txt)]})
        import estado_producao as ep
        ra = ep.render_atual(base, video, d=d)
        if ra["estado"] == "desatualizado":
            res.append({"id": "render", "problemas": [("grave", "render desatualizado — mudou depois do render: " + ", ".join(ra["mudou"][:6]))]})
        elif ra["estado"] == "desconhecido":
            res.append({"id": "render", "problemas": [], "pendencias": ra["mudou"], "estado": ig.NAO_VERIFICADO})
    erradas = []  # legenda × áudio: a palavra na tela precisa ser ouvida perto do instante em que aparece (P06)
    from tts_gemini import _UNID, _norm
    por_plano = {}
    for lw in legenda:
        txt, ini = lw.get("text") or lw.get("texto", ""), float(lw.get("start", lw.get("inicio", 0)))
        n = _norm(txt)
        if len(n) <= 2 or n in _UNID or n in ("mil", "e"):  # número por extenso × dígitos e palavrinhas = falso alarme
            continue
        perto = [w[2] for w in ws if abs(w[0] - ini) < 0.6]
        if perto and cobertura(txt, perto) < 1.0:
            msg = f"{ini:.1f}s legenda \"{txt}\" × ouvido \"{' '.join(perto)}\""
            erradas.append(msg)
            dono = next((x for x in res if x.get("de") is not None and x["de"] <= ini < x["ate"]), None)
            if dono:
                por_plano.setdefault(dono["id"], []).append(msg)
    for x in res:  # 1 palavra divergente pode ser erro do whisper; 2+ no mesmo plano = legenda errada
        msgs = por_plano.get(x["id"], [])
        if msgs:
            x["problemas"].append(("grave" if len(msgs) >= 2 else "media", f"legenda × áudio: {'; '.join(msgs)}"))
    for x in res:
        x.setdefault("estado", ig.estado_qa(x["problemas"], verificado=True))
        x["veredito"] = {ig.REPROVADO: "reprovado", ig.NAO_VERIFICADO: "nao_verificado"}.get(x["estado"], "aprovado")
        if x["estado"] == ig.APROVADO and x.get("excecao_diretor"):
            x["veredito"] = "aprovado_com_excecao"  # nunca "aprovado" limpo: a reprovação original continua no registro
    return res, erradas


def estado_de(i):
    if i.get("estado") in ig.ESTADOS:
        return i["estado"]
    return ig.REPROVADO if any(x[0] == "grave" for x in i.get("problemas", [])) else ig.NAO_VERIFICADO


def relatorio(arq, titulo, itens, extra=None, mesclar=False):
    jarq = os.path.splitext(arq)[0] + ".json"
    if mesclar and os.path.exists(jarq):  # reinspecionar 1 plano não apaga a inspeção dos outros
        antigos = json.load(io.open(jarq, encoding="utf-8")).get("itens", [])
        novos = {i["id"] for i in itens}
        itens = [i for i in antigos if i.get("id") not in novos] + itens
    for i in itens:
        i["estado"] = estado_de(i)
    rep = [i for i in itens if i["estado"] == ig.REPROVADO]
    nv = [i for i in itens if i["estado"] == ig.NAO_VERIFICADO]
    ap = [i for i in itens if i["estado"] == ig.APROVADO]
    L = [f"# Inspeção — {titulo}", "",
         f"**{len(ap)} aprovados · {len(rep)} reprovados · {len(nv)} não verificados** "
         f"(refazer: {', '.join(i['id'] for i in rep) or '—'} · revisar: {', '.join(i['id'] for i in nv) or '—'})",
         "Só 'aprovado' entra na montagem final. Não verificado = falta revisão visual (Gemini ou o diretor pela folha: "
         "`inspetor.py revisar`).", ""]
    for i in itens:
        marca = {ig.REPROVADO: "❌", ig.NAO_VERIFICADO: "👁"}.get(i["estado"], "⚠️" if i.get("problemas") else "✅")
        n = i.get("nota") or {}
        nt = f"nota {n['valor']}/100{' parcial' if n.get('parcial') else ''} " if n.get("valor") is not None else ""
        L.append(f"- {marca} **{i['id']}** {i.get('veredito', '')} {nt}" + " · ".join(f"[{g}] {t}" for g, t in i.get("problemas", [])))
        rv = i.get("revisao_visual") or {}
        if rv.get("pendente"):
            L.append(f"  - 👁 revisão visual pendente ({rv['motivo'][:60]}): folha `{rv.get('folha')}` · critérios: {'; '.join(rv.get('criterios', []))}")
    if extra:
        L += ["", f"## Legenda × áudio ({len(extra)} palavras divergentes)", ""] + [f"- {e}" for e in extra]
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    io.open(arq, "w", encoding="utf-8").write("\n".join(L) + "\n")
    ig.gravar_json_atomico(jarq, json.loads(json.dumps({"itens": itens, "legenda": extra or []}, ensure_ascii=False, default=str)))
    if os.path.basename(arq).startswith("inspecao-planos"):  # INTEGRACAO-RUNWARE.md §6.8: relatório por take E versão
        pasta = os.path.join(os.path.dirname(arq), "inspecao")
        os.makedirs(pasta, exist_ok=True)
        for i in itens:
            if not i.get("sha256_clipe"):
                continue
            nome = os.path.join(pasta, f"{i['id']}-{i['sha256_clipe'][:8]}")
            rv = i.get("revisao_visual") or {}
            reg = {"id": i["id"], "versao": i["sha256_clipe"][:8], "sha256_clipe": i["sha256_clipe"], "estado": i["estado"],
                   "nota": i.get("nota"), "problemas": i.get("problemas", []), "pendencias": i.get("pendencias", []),
                   "avisos": i.get("avisos", []), "inspetor_visual": "gemini" if rv and not rv.get("pendente") else "nenhum (pendente)",
                   "movimento": i.get("movimento"), "atuacao": (i.get("atuacao") or {}).get("estado"), "revisao": i.get("revisao")}
            ig.gravar_json_atomico(nome + ".json", json.loads(json.dumps(reg, ensure_ascii=False, default=str)))
            io.open(nome + ".md", "w", encoding="utf-8").write(
                f"# {i['id']} · versão {reg['versao']} · {reg['estado']}\n\n- inspetor visual: {reg['inspetor_visual']}\n"
                + "".join(f"- [{g}] {t}\n" for g, t in reg["problemas"]) + "".join(f"- pendente: {x}\n" for x in reg["pendencias"]))
    print(f"{len(ap)} aprovados · {len(rep)} reprovados: {', '.join(i['id'] for i in rep) or '—'} · "
          f"{len(nv)} não verificados: {', '.join(i['id'] for i in nv) or '—'} → {arq}")
    return rep, nv


def revisar(base, ids, estado, nota, imagem=False):
    """Decisão da revisão visual (diretor olhando a folha de quadros, ou o usuário no chat) gravada na inspeção — vale só
    para o MESMO arquivo inspecionado. Não derruba reprovação objetiva (congelado, só câmera): essa é refeita, não revisada."""
    import datetime
    jarq = os.path.join(base, "entrega", "inspecao-imagens.json" if imagem else "inspecao-planos.json")
    if not os.path.exists(jarq):
        sys.exit("sem inspeção registrada — rode `inspetor.py " + ("imagens" if imagem else "planos") + "` antes")
    d = json.load(io.open(jarq, encoding="utf-8"))
    for pid in ids:
        it = next((i for i in d["itens"] if i.get("id") == pid), None)
        if not it:
            sys.exit(f"{pid} não foi inspecionado")
        clip = os.path.join(base, "assets", "img", f"{pid}.png") if imagem else os.path.join(base, "assets", "clips", f"{pid}.mp4")
        sha_k = "sha256_imagem" if imagem else "sha256_clipe"
        if it.get(sha_k) and (not os.path.isfile(clip) or ig.sha256(clip) != it[sha_k]):
            sys.exit(f"{pid}: o arquivo mudou depois da inspeção — inspecione de novo")
        graves = [t for g, t in it.get("problemas", []) if g == "grave"]
        if estado == ig.APROVADO and graves:
            sys.exit(f"{pid}: tem reprovação objetiva ({graves[0][:90]}…) — refaça o plano em vez de aprovar na revisão")
        if estado == ig.APROVADO and it.get("bloqueios"):
            sys.exit(f"{pid}: bloqueio objetivo ({', '.join(it['bloqueios'])}) — corrigir/refazer, não se aprova na revisão")
        if estado == ig.APROVADO and (it.get("estado") == ig.REPROVADO or it.get("problemas")):
            # aprovar por cima de reprovação/ressalva = EXCEÇÃO registrada (a reprovação original fica), nunca aprovação limpa
            it.setdefault("reprovacoes_originais", []).append({k: it.get(k) for k in ("estado", "veredito", "problemas", "nota")})
            it["excecao_diretor"] = {"nota": nota}
        it["estado"] = estado
        it["veredito"] = ("aprovado_com_excecao" if it.get("excecao_diretor") else "aprovado") if estado == ig.APROVADO else "reprovado"
        it["pendencias"] = []
        if estado == ig.REPROVADO:
            it.setdefault("problemas", []).append(["grave", f"revisão visual: {nota}"])
        it["revisao"] = {"estado": estado, "nota": nota, "quando": datetime.datetime.now().isoformat(timespec="seconds")}
        print(f"{pid} → {estado} ({nota})")
    ig.gravar_json_atomico(jarq, d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["planos", "imagens", "audio", "filme", "revisar", "adaptar"])
    ap.add_argument("--mudanca", help="adaptar: JSON com os campos do contrato que mudam, ex.: '{\"voz\": \"off\"}'")
    ap.add_argument("--imagem", action="store_true", help="revisar: decisão sobre a IMAGEM-CHAVE (inspecao-imagens.json)")
    ap.add_argument("--sem-montagem", action="store_true", help="filme: pula a inspeção de congelamento/telas divididas")
    ap.add_argument("roteiro")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--planos")
    ap.add_argument("--registrar", action="store_true")
    ap.add_argument("--estado", choices=[ig.APROVADO, ig.REPROVADO], help="revisar: decisão da revisão visual")
    ap.add_argument("--nota", default="", help="revisar: o que foi visto (obrigatório)")
    a = ap.parse_args()
    if a.modo == "revisar":
        if not (a.planos and a.estado and a.nota):
            sys.exit("revisar precisa de --planos, --estado e --nota")
        return revisar(os.path.dirname(os.path.abspath(a.roteiro)), a.planos.split(","), a.estado, a.nota, imagem=a.imagem)
    if a.modo == "adaptar":
        if not (a.planos and a.mudanca and a.nota):
            sys.exit("adaptar precisa de --planos <id>, --mudanca '<json>' e --nota '<motivo editorial>'")
        for pid in a.planos.split(","):
            adaptar(a.roteiro, pid, json.loads(a.mudanca), a.nota)
        return
    base = os.path.dirname(os.path.abspath(a.roteiro))
    d = json.load(io.open(a.roteiro, encoding="utf-8"))
    if a.planos:
        alvo = set(a.planos.split(","))
        d["planos"] = [p for p in d["planos"] if p["id"] in alvo]
    saida = os.path.join(base, "entrega", f"inspecao-{a.modo}.md")
    if a.modo == "planos":
        itens = []
        for p in d["planos"]:
            r = inspecionar_plano(base, p, a.registrar)
            n = r.get("nota") or {}
            print(f"  {p['id']} {r['veredito']} · nota {n.get('valor')}/100{' (parcial: faltam ' + ', '.join(n.get('faltam', [])) + ')' if n.get('parcial') else ''}" + "".join(f"\n     [{g}] {t}" for g, t in r["problemas"]))
            itens.append(r)
        rep, nv = relatorio(saida, "planos", itens, mesclar=bool(a.planos))
    elif a.modo == "imagens":
        itens = []
        for p in d["planos"]:
            if (p.get("direcao") or {}).get("modo") not in ANIMADOS:
                continue
            r = inspecionar_imagem(base, p, json.load(io.open(a.roteiro, encoding="utf-8")))
            print(f"  {p['id']} {r['estado']}" + "".join(f"\n     [{g}] {t}" for g, t in r["problemas"]) + "".join(f"\n     👁 {x}" for x in r["pendencias"]))
            itens.append(r)
        rep, nv = relatorio(saida, "imagens-chave", itens, mesclar=bool(a.planos))
    elif a.modo == "audio":
        rep, nv = relatorio(saida, "falas", inspecionar_audio(base, d), mesclar=bool(a.planos))
    else:
        if not a.video:
            sys.exit("modo filme precisa do vídeo montado")
        itens, legenda = inspecionar_filme(base, d, a.video, montagem=not a.sem_montagem)
        rep, nv = relatorio(saida, os.path.basename(a.video), itens, legenda)
    sys.exit(2 if rep else 3 if nv else 0)  # 2 = refazer · 3 = falta revisão · 0 = tudo aprovado


if __name__ == "__main__":
    main()
