"""Contrato de direção por plano + diretor de fotografia + rota de produção + orçamento.

Cada plano do roteiro.json ganha `direcao` — o contrato que diz o que o plano PRECISA mostrar e como será aprovado:
  {"modo": "acao|fala|reacao|insert|estabelecimento|titulo",
   "duracao": 4.0, "quem": ["tiago"], "acao": "o que o corpo faz, em verbos", "acao_en": "same, in English",
   "atuacao": "nervoso → decidido",
   "voz": "off|em_quadro|nenhuma",           ← em_quadro = personagem visível falando → lip-sync obrigatório
   "enquadramento": "PG|PC|PM|PA|PP|close|detalhe", "angulo": "normal|plongee|contra-plongee|holandes|ombro",
   "camera": "fixa|acompanha|travelling|pan|tilt|dolly-in|dolly-out|na-mao|zoom",
   "motivo_camera": "por que a câmera se mexe (ou não)",
   "quadro_inicial": "…", "quadro_final": "…",
   "som": {"efeitos": [{"som": "passos no corredor", "em": 0.2, "dur": 2}], "ambiente": "corredor"},
   "criterios": ["Tiago desvia o olhar", "mãos com 5 dedos, violão inteiro"],
   "beats": [                                ← DIRETOR DE ATUAÇÃO: a atuação do 1º ao último quadro, por fase
     {"ate": 1.0, "fase": "antecipacao|acao|consequencia|reacao", "pt": "o que acontece",
      "en": "same in English: body + face", "secundario": "hair/clothes/drops (en)"}],
   "exige": ["tronco", "bracos", "cabeca"],  ← partes do corpo que TÊM de se mexer (atuacao.py confere)
   "fisica": "causa → efeito: a roda bate na poça → a água sobe → acerta o rapaz → ele recua",
   "rota": {...preenchida por `rotear`}}

REGRA: câmera em movimento não é animação. modo acao/fala/reacao NUNCA sai como foto + zoom.
Foto + movimento de câmera só para insert/estabelecimento/título — e no máximo 25 % do tempo do filme.

Uso (na pasta filme/):
  python contrato.py rascunhar roteiro.json [--briefing ../BRIEFING.md] [--refazer]   → Gemini escreve os contratos (grátis)
  python contrato.py validar roteiro.json        → regras de direção e de fotografia (repetição de plano/câmera, zoom demais…)
  python contrato.py rotear roteiro.json         → escolhe a rota de cada plano e mostra o ORÇAMENTO (nada é gasto)
  python contrato.py storyboard roteiro.json -o storyboard.png   → folha de storyboard com os contratos (grátis)
  python contrato.py prompt roteiro.json --planos p17           → prompt de vídeo com tempo por fase (beats)
  --planos p05,p10 limita a alguns planos (cenas de teste).
"""
import argparse
import io
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from tts_gemini import URL, chave  # noqa: E402

MODOS_ANIMADOS = {"acao", "fala", "reacao"}
ESTATICOS_OK = {"insert", "estabelecimento", "titulo"}
TETO_ESTATICO = 0.25
# preços oficiais fal (API de preços, 2026-11-06), por segundo
ROTAS = {
    "motion": ("código (Remotion)", 0.0),
    "foto_camera": ("imagem + movimento de câmera", 0.0),
    "clipe": ("fal-ai/kling-video/v2.6/pro/image-to-video", 0.07),          # durações 5 ou 10 s, 1º e último quadro
    "clipe_longo": ("fal-ai/kling-video/v3/pro/image-to-video", 0.14),      # 3–15 s, elements p/ identidade
    "avatar": ("fal-ai/kling-video/ai-avatar/v2/standard", 0.0562),         # fala em quadro, gestos leves
    "omnihuman": ("fal-ai/bytedance/omnihuman/v1.5", 0.16),                 # fala + ação de corpo
}
TAXA_APROV = 0.85  # estimativa até o histórico do roteador ter dados; orçamento = preço ÷ taxa

PEDIDO = """Você é diretor de cena e diretor de fotografia de um curta de animação ({estilo}), vertical 9:16.
Briefing: {briefing}

Para CADA plano abaixo, escreva o contrato de direção. Regras:
- Personagem em cena com algo acontecendo = modo "acao" (corpo se mexe) ou "reacao" (rosto/expressão muda: piscar,
  hesitar, respirar, olhar para alguém). Ninguém fica congelado: descreva a atuação em VERBOS, com começo e fim.
- "fala" só quando o personagem aparece FALANDO a fala do plano (voz "em_quadro"). Narração de diário/narrador = voz "off":
  o personagem atua de boca fechada.
- "insert" (detalhe de objeto sem ação), "estabelecimento" (lugar) e "titulo" (texto) podem ser foto + câmera.
- Fotografia: varie o tamanho de plano (PG plano geral, PC conjunto, PM médio, PA americano, PP primeiro plano, close, detalhe)
  e o ângulo conforme a dramaturgia; nunca 3 planos seguidos com o mesmo enquadramento; diálogo usa plano/contraplano;
  movimento de câmera só com motivo (acompanhar quem anda, revelar, tensão). Zoom no máximo em 1 de cada 5 planos.
- Som: liste 1–3 efeitos concretos do que acontece (passos, porta, ônibus, violão, risada, chuva forte) com o segundo em que
  entram ("em", relativo ao início do plano) e duração. Use {{"clipe": true, "som": "…"}} quando o som nasce da ação animada.
- critérios: 2–4 coisas VERIFICÁVEIS no vídeo para aprovar o plano (a ação acontece, identidade, mãos/objetos íntegros).
- duracao: use a duração indicada (fala) ou 2–4 s para planos sem fala.
- beats (OBRIGATÓRIO em acao/reacao/fala com personagem): 2–4 fases cobrindo do 0 ao último segundo, cada uma
  {{"ate": segundos acumulados, "fase": "antecipacao|acao|consequencia|reacao|pausa", "pt": "o que acontece",
  "evidencia": "o que se VÊ acontecer", "en": "a mesma ação em inglês para o modelo de vídeo (corpo + rosto)",
  "secundario": "movimento secundário em inglês (cabelo, roupa, objetos)"}}. O último "ate" = duracao.
  Fala em quadro: inclua gestos e expressão enquanto fala; narração em off: personagem de boca fechada.
- exige: partes do corpo que TÊM de se mexer, entre cabeca, bracos, tronco, pernas, corpo.
- fisica: causa → efeito, obrigatório se algum beat for "consequencia".
Responda só JSON: {{"p01": {{contrato}}, ...}} com as chaves: modo, duracao, quem, acao, acao_en, atuacao, voz,
enquadramento, angulo, camera, motivo_camera, quadro_inicial, quadro_final, som, criterios, beats, exige, fisica.
Português do Brasil, exceto acao_en (a ação em inglês, 1 frase, para o modelo de vídeo).

Planos:
{planos}"""


def efeitos_de(c):
    """`som` pode vir como {"efeitos": [...]} ou direto como lista (rascunho do Gemini)."""
    som = c.get("som") or {}
    ef = som if isinstance(som, list) else som.get("efeitos") or []
    return [e if isinstance(e, dict) else {"som": str(e)} for e in ef]


def ler(arq):
    return json.load(io.open(arq, encoding="utf-8"))


def gravar(arq, d):
    json.dump(d, io.open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def gemini_json(texto):
    corpo = {"contents": [{"parts": [{"text": texto}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.5}}
    req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    import time
    for n in range(6):  # 429 = limite por minuto da cota grátis: espera e tenta de novo
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:
            corpo_err = e.read().decode(errors="replace")
            if "spending cap" in corpo_err or "spend cap" in corpo_err:
                sys.exit("Gemini: o projeto atingiu o TETO DE GASTO MENSAL (ai.studio/spend). Sem Gemini, os contratos são "
                         "escritos pelo Claude (agente estudio-fotografia) direto no roteiro.json; depois rode `validar`.")
            if e.code not in (429, 500, 503) or n == 5:
                raise
            print(f"  Gemini {e.code}; esperando {20 * (n + 1)} s…", file=sys.stderr)
            time.sleep(20 * (n + 1))


def dur_fala(base, p):
    arq = os.path.join(base, "assets", "voz", f"{p['id']}.wav")
    if not os.path.exists(arq):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True)
    return round(float(r.stdout.strip() or 0), 2)


def selecionar(d, planos):
    alvo = set(planos.split(",")) if planos else None
    return [p for p in d["planos"] if not alvo or p["id"] in alvo]


def rascunhar(arq, briefing=None, refazer=False, planos=None):
    d, base = ler(arq), os.path.dirname(os.path.abspath(arq))
    lista = [p for p in selecionar(d, planos) if refazer or not (p.get("direcao") or {}).get("modo")]
    if not lista:
        return print("todos os planos já têm contrato (use --refazer)")
    brief = io.open(briefing, encoding="utf-8").read()[:3000] if briefing and os.path.exists(briefing) else "curta de animação"
    feitos = {}
    for i in range(0, len(lista), 12):  # lotes de 12: respostas completas e coerentes entre vizinhos
        bloco = lista[i:i + 12]
        linhas = "\n".join(
            f"{p['id']} · tipo {p.get('tipo')} · quem {p.get('quem')} · cenário {p.get('ambiente')} · fala: {p.get('fala') or '—'}"
            f" · duração da fala {dur_fala(base, p) or '—'} s"
            + (f" · DURAÇÃO-ALVO DO PLANO {p['dur_alvo']} s (use exatamente esta em duracao e nos beats)" if p.get("dur_alvo") else "")
            + (f" · ação: {p['o_que'][:260]}" if p.get("o_que") else "")
            + f" · imagem: {(p.get('prompts') or [''])[0][:220]}"
            f" · movimento planejado: {(p.get('clipe') or {}).get('movimento', '—')}" for p in bloco)
        anteriores = ", ".join(f"{k}: {v.get('enquadramento')}/{v.get('camera')}" for k, v in list(feitos.items())[-3:])
        r = gemini_json(PEDIDO.format(estilo=d.get("estilo", "cartoon"), briefing=brief,
                                      planos=(f"(planos anteriores: {anteriores})\n" if anteriores else "") + linhas))
        feitos.update(r)
        print(f"  contratos {i + 1}–{i + len(bloco)} de {len(lista)}")
    for p in d["planos"]:
        if p["id"] in feitos:
            p["direcao"] = dict(feitos[p["id"]], **({"rota": p["direcao"]["rota"]} if (p.get("direcao") or {}).get("rota") else {}))
    gravar(arq, d)
    print(f"{len(feitos)} contratos gravados em {arq} — revise com `validar`")


FASES = {"antecipacao", "acao", "consequencia", "reacao", "pausa"}
PARTES = {"cabeca", "bracos", "tronco", "pernas", "corpo"}
MAX_DURACAO_CLIPE = 15.0  # maior duração entre as rotas de clipe (Kling 3 Pro); acima disso o plano tem de ser dividido


def normalizar_beats(bs):
    """Aceita beats com "ate" (fim acumulado) ou "inicio"/"fim". Devolve lista com inicio/fim/ate numéricos (ou erro no campo)."""
    out, t0 = [], 0.0
    for b in bs or []:
        b = dict(b)
        try:
            fim = float(b.get("fim", b.get("ate")))
        except (TypeError, ValueError):
            fim = None
        try:
            ini = float(b["inicio"]) if "inicio" in b else t0
        except (TypeError, ValueError):
            ini = None
        b["inicio"], b["fim"], b["ate"] = ini, fim, fim
        out.append(b)
        t0 = fim if fim is not None else t0
    return out


def validar_beats(p, c, fases_prox=()):
    """Regras do diretor de atuação (auditoria P01/P30/P31/P33). Devolve (erros, avisos) — erro bloqueia a geração paga."""
    erros, avisos = [], []
    pid = p["id"]
    com_gente = bool(p.get("quem") or c.get("quem"))
    try:
        dur = float(c.get("duracao") or 0)
    except (TypeError, ValueError):
        dur = 0
    if dur <= 0:
        erros.append(f"{pid}: duração ausente ou inválida")
    if dur > MAX_DURACAO_CLIPE:
        erros.append(f"{pid}: {dur}s passa do máximo de um clipe ({MAX_DURACAO_CLIPE:.0f}s) — divida em planos")
    bs = normalizar_beats(c.get("beats"))
    if not bs:
        (erros if com_gente else avisos).append(
            f"{pid}: sem beats de atuação — o modelo começa a ação e congela; escreva antecipação/ação/consequência/reação com tempo")
        if com_gente and not c.get("exige"):
            erros.append(f"{pid}: sem 'exige' (partes do corpo que precisam se mexer)")
        return erros, avisos
    if com_gente and len(bs) < 2:
        erros.append(f"{pid}: só {len(bs)} beat — atuação com personagem precisa de pelo menos 2 fases")
    ant = 0.0
    for i, b in enumerate(bs, 1):
        if b["fim"] is None or b["inicio"] is None:
            erros.append(f"{pid} beat {i}: tempo inválido")
            continue
        if b["fim"] <= b["inicio"] or b["fim"] <= ant - 1e-6:
            erros.append(f"{pid} beat {i}: tempo fora de ordem ({b['inicio']:.2f}→{b['fim']:.2f}s)")
        if abs(b["inicio"] - ant) > 0.05:
            erros.append(f"{pid} beat {i}: {'lacuna' if b['inicio'] > ant else 'sobreposição'} entre {ant:.2f}s e {b['inicio']:.2f}s"
                         " (pausa intencional = beat com fase 'pausa')")
        if dur and b["fim"] > dur + 0.05:
            erros.append(f"{pid} beat {i}: termina em {b['fim']:.2f}s, depois do fim do plano ({dur}s)")
        if b.get("fase") not in FASES:
            erros.append(f"{pid} beat {i}: fase '{b.get('fase')}' inválida (use {', '.join(sorted(FASES))})")
        if not (b.get("en") or "").strip():
            erros.append(f"{pid} beat {i}: sem 'en' — a ação observável que o modelo de vídeo vai receber")
        if not (b.get("evidencia") or b.get("pt") or "").strip():
            avisos.append(f"{pid} beat {i}: sem 'evidencia' (o que o inspetor deve VER acontecer)")
        ant = b["fim"]
    if dur and bs[-1]["fim"] is not None and bs[-1]["fim"] + 0.2 < dur:
        erros.append(f"{pid}: beats acabam em {bs[-1]['fim']:.2f}s e o plano dura {dur}s — o modelo não recebe ação para o fim"
                     " (personagem congela); cubra até o último quadro")
    fases = [b.get("fase") for b in bs]
    if com_gente:
        exige = c.get("exige") or []
        if not exige:
            erros.append(f"{pid}: sem 'exige' (partes do corpo que precisam se mexer)")
        elif set(exige) - PARTES:
            erros.append(f"{pid}: 'exige' com parte desconhecida {sorted(set(exige) - PARTES)} (use {', '.join(sorted(PARTES))})")
        if ("acao" in fases or "consequencia" in fases) and fases[-1] != "reacao" and "reacao" not in fases_prox:
            avisos.append(f"{pid}: a piada não fecha — o último beat (ou o 1º do plano seguinte) precisa ser 'reacao'")
    if "consequencia" in fases and not (c.get("fisica") or "").strip():
        erros.append(f"{pid}: há consequência física sem 'fisica' (causa → efeito que o inspetor vai conferir)")
    return erros, avisos


def validar(arq, planos=None):
    d = ler(arq)
    ps = selecionar(d, planos)
    erros, avisos = [], []
    campos = ("modo", "acao", "voz", "enquadramento", "camera", "quadro_inicial", "quadro_final", "criterios")
    for p in ps:
        c = p.get("direcao")
        if not c or not c.get("modo"):
            erros.append(f"{p['id']}: sem contrato de direção")
            continue
        falta = [k for k in campos if not c.get(k)]
        if falta:
            erros.append(f"{p['id']}: contrato incompleto ({', '.join(falta)})")
        if c.get("voz") == "em_quadro" and c.get("modo") != "fala":
            avisos.append(f"{p['id']}: voz em quadro mas modo '{c.get('modo')}' — vai precisar de lip-sync (modo fala)")
        if c.get("modo") in MODOS_ANIMADOS and not (c.get("acao") or "").strip():
            erros.append(f"{p['id']}: modo {c['modo']} sem ação descrita")
        if c.get("modo") in MODOS_ANIMADOS:
            prox = ps[ps.index(p) + 1] if ps.index(p) + 1 < len(ps) else None
            fases_prox = [b.get("fase") for b in normalizar_beats(((prox or {}).get("direcao") or {}).get("beats"))]
            e2, a2 = validar_beats(p, c, fases_prox)
            erros += e2
            avisos += a2
        if c.get("modo") in ESTATICOS_OK and p.get("quem") and c.get("atuacao") and not p.get("partes"):
            avisos.append(f"{p['id']}: '{c['modo']}' com personagem atuando ({c['atuacao']}) — deveria ser reacao/acao?")
    seq = [(p["id"], (p.get("direcao") or {})) for p in ps]
    for i in range(2, len(seq)):
        e = [s[1].get("enquadramento") for s in seq[i - 2:i + 1]]
        if e[0] and e[0] == e[1] == e[2]:
            avisos.append(f"{seq[i - 2][0]}–{seq[i][0]}: 3 planos seguidos em {e[0]} (fotografia repetitiva)")
        cm = [s[1].get("camera") for s in seq[i - 2:i + 1]]
        if cm[0] and cm[0] != "fixa" and cm[0] == cm[1] == cm[2]:
            avisos.append(f"{seq[i - 2][0]}–{seq[i][0]}: mesmo movimento de câmera ({cm[0]}) 3 vezes seguidas")
    tot = sum(float(c.get("duracao") or 3) for _, c in seq) or 1
    zoom = sum(1 for _, c in seq if c.get("camera") == "zoom")
    # foto + câmera é o que o teto limita; tela do sistema animada em código (rota_fixa motion) e composição não contam
    est = sum(float(c.get("duracao") or 3) for _, c in seq
              if c.get("modo") in ESTATICOS_OK and c.get("rota_fixa") not in ("motion", "composicao"))
    if zoom > len(seq) / 5:
        avisos.append(f"zoom em {zoom} de {len(seq)} planos (máx. 1 em 5)")
    if est / tot > TETO_ESTATICO:
        avisos.append(f"planos sem atuação somam {est / tot:.0%} do tempo (teto {TETO_ESTATICO:.0%}) — transforme alguns em reação/ação")
    tam = {}
    for _, c in seq:
        tam[c.get("enquadramento")] = tam.get(c.get("enquadramento"), 0) + 1
    print(f"{len(ps)} planos · enquadramentos {dict(sorted(tam.items(), key=lambda x: -x[1]))} · sem atuação {est / tot:.0%} do tempo")
    for e in erros:
        print("  ❌", e)
    for a in avisos:
        print("  ⚠️", a)
    if not erros and not avisos:
        print("  ✅ contratos completos e fotografia variada")
    return not erros


def rota_de(p, base):
    c = p.get("direcao") or {}
    modo = c.get("modo")
    dur = float(c.get("duracao") or dur_fala(base, p) or 3)
    if p.get("tipo") == "cartao" or modo == "titulo":
        return {"rota": "motion", "dur": dur}
    if modo in ESTATICOS_OK:
        return {"rota": "foto_camera", "dur": dur}
    if modo == "fala" or c.get("voz") == "em_quadro":
        if c.get("rota_preferida") in ("avatar", "omnihuman"):  # 2026-11-07: o diretor fixa a rota de fala (ex.: omnihuman inventou figurino)
            return {"rota": c["rota_preferida"], "dur": dur}
        corpo = any(v in (c.get("acao") or "").lower() for v in ("anda", "corre", "pula", "dança", "cai", "toca", "aponta", "chora",
                                                               "pega", "levanta", "folheia", "gesticula"))
        return {"rota": "omnihuman" if corpo else "avatar", "dur": dur}
    # ação/reação: Kling 2.6 (só 5 ou 10 s) ou Kling 3 (3–15 s) — o mais barato ENTRE OS QUE CABEM na duração (P09)
    if dur > MAX_DURACAO_CLIPE:
        return {"rota": "dividir", "dur": dur, "erro": f"{dur}s não cabe em nenhum modelo de clipe — divida o plano"}
    opcoes = []
    if dur <= 10:
        opcoes.append((ROTAS["clipe"][1] * (5 if dur <= 5 else 10), "clipe"))
    opcoes.append((ROTAS["clipe_longo"][1] * max(3, math.ceil(dur - 1e-6)), "clipe_longo"))
    return {"rota": min(opcoes)[1], "dur": dur}


CAMERA_EN = {"acompanha": "the camera tracks sideways alongside the character", "fixa": "static locked-off camera",
             "dolly-in": "slow dolly-in", "dolly-out": "slow dolly-out", "pan": "slow pan", "tilt": "slow tilt up",
             "travelling": "smooth travelling shot", "na-mao": "subtle handheld camera", "zoom": "slow zoom"}
PLANO_EN = {"PG": "wide shot", "PC": "full shot", "PM": "medium shot", "PA": "american shot", "PP": "medium close-up",
            "close": "close-up", "detalhe": "extreme close-up insert"}


def prompt_atuacao(p, estilo="exaggerated caricature cartoon animation, squash and stretch, same character design and art style as the image"):
    """Prompt com TEMPO por fase (diretor de atuação): o modelo de vídeo sustenta a atuação até o último quadro."""
    c = p.get("direcao") or {}
    cam = c.get("camera") or "fixa"
    partes = [f"{PLANO_EN.get(c.get('enquadramento'), 'medium shot')}, {CAMERA_EN.get(cam, 'camera: ' + cam)}."]  # câmera livre passa como está
    for b in normalizar_beats(c.get("beats")):
        sec = f" Secondary motion: {b['secundario']}." if b.get("secundario") else ""
        partes.append(f"{b['inicio']:.1f}-{b['fim']:.1f}s ({b.get('fase', '')}): {b.get('en', '')}.{sec}")
    if not c.get("beats"):
        partes.append(c.get("acao_en") or c.get("acao", ""))
    if c.get("voz") == "off":
        partes.append("He/she is not speaking: no lip movement except breathing and reactions.")
    partes.append("The character keeps acting until the very last frame and never freezes; keep body proportions and face "
                  f"geometry constant, natural weight and balance, stylized but coherent physics. {estilo}. No text.")
    return " ".join(partes)


def preco_rota(r):
    """Preço da rota para a duração; None se a rota não cobre a duração (nunca estima duração não suportada)."""
    if r["rota"] not in ROTAS:
        return None
    ps = ROTAS[r["rota"]][1]
    if r["rota"] == "clipe":
        return ps * (5 if r["dur"] <= 5 else 10) if r["dur"] <= 10 else None
    if r["rota"] == "clipe_longo":
        return ps * max(3, math.ceil(r["dur"] - 1e-6)) if r["dur"] <= MAX_DURACAO_CLIPE else None
    return ps * (r["dur"] + 0.15)


def rotear(arq, planos=None):
    d, base = ler(arq), os.path.dirname(os.path.abspath(arq))
    ps = selecionar(d, planos)
    total, linhas, tempo = 0.0, [], {"animado": 0.0, "estatico": 0.0}
    sem = [p["id"] for p in ps if not (p.get("direcao") or {}).get("modo")]
    if sem:
        sys.exit(f"planos sem contrato: {', '.join(sem)} — rode `rascunhar` antes de orçar")
    bloqueios = []
    for p in ps:
        r = rota_de(p, base)
        pago = preco_rota(r)
        if pago is None:
            bloqueios.append(f"{p['id']}: {r.get('erro') or 'rota sem preço para ' + str(r['dur']) + 's'}")
            continue
        efs = efeitos_de(p.get("direcao") or {})
        sfx = sum(0.001 * 5 if e.get("clipe") else 0.002 * float(e.get("dur", 2)) for e in efs)
        esperado = pago / TAXA_APROV + sfx
        r.update(modelo=ROTAS[r["rota"]][0], custo=round(pago, 3), esperado=round(esperado, 3), efeitos=len(efs))
        p.setdefault("direcao", {})["rota"] = r
        total += esperado
        tempo["estatico" if r["rota"] in ("foto_camera", "motion") else "animado"] += r["dur"]
        c = p.get("direcao") or {}
        linhas.append(f"  {p['id']:5} {str(c.get('modo', '?')):15} {str(c.get('enquadramento', '?')):7} {str(c.get('camera', '?')):11} "
                      f"→ {r['rota']:11} {r['dur']:4.1f}s  US$ {pago:5.2f}  (+{len(efs)} efeitos)")
    gravar(arq, d)
    print("\n".join(linhas))
    tt = sum(tempo.values()) or 1
    print(f"\n{len(ps)} planos · animado de verdade {tempo['animado'] / tt:.0%} do tempo · foto+câmera {tempo['estatico'] / tt:.0%}")
    if bloqueios:
        print("\n❌ sem orçamento possível para:\n  " + "\n  ".join(bloqueios))
        print("Corrija esses planos (dividir ou outra rota) antes de pedir aprovação de gasto.")
        sys.exit(1)
    print(f"ORÇAMENTO esperado (com {1 / TAXA_APROV - 1:.0%} de margem para refazer reprovados): US$ {total:.2f}")
    print("Nada foi gasto. Imagens-chave à parte (gerar_imagem.py, ~US$ 0,05 cada).")
    return total


def storyboard(arq, saida, planos=None):
    d, base = ler(arq), os.path.dirname(os.path.abspath(arq))
    tomadas = []
    for p in selecionar(d, planos):
        c = p.get("direcao") or {}
        img = next((x for x in (p.get("arquivos") or []) if os.path.exists(os.path.join(base, x))), None)
        voz = "(em quadro) " if c.get("voz") == "em_quadro" else "(off) " if c.get("voz") == "off" else ""
        tomadas.append({"tempo": f"{p['id']} · {c.get('duracao', '?')} s", "imagem": img,
                        "tipo": f"{c.get('modo', '?')} → {(c.get('rota') or {}).get('rota', '?')}",
                        "acao": f"[{c.get('enquadramento', '?')}/{c.get('angulo', 'normal')}/{c.get('camera', '?')}] {c.get('acao', '')}"
                                f" · início: {c.get('quadro_inicial', '')} · fim: {c.get('quadro_final', '')}",
                        "fala": f"{voz}{p.get('fala') or '—'}",
                        "tela": ", ".join(e.get("som", "som do clipe") for e in efeitos_de(c)) or "—"})
    sb = os.path.join(base, "storyboard-contratos.json")
    gravar(sb, {"titulo": d.get("titulo", "storyboard"), "etapa": "contratos de direção (antes de gastar)", "tomadas": tomadas})
    subprocess.run([sys.executable, os.path.join(AQUI, "storyboard.py"), sb, "-o", saida], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["rascunhar", "validar", "rotear", "storyboard", "prompt"])
    ap.add_argument("roteiro")
    ap.add_argument("--briefing")
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--planos")
    ap.add_argument("-o", "--saida", default="storyboard-contratos.png")
    a = ap.parse_args()
    if a.acao == "prompt":
        d = ler(a.roteiro)
        for p in selecionar(d, a.planos):
            print(f"{p['id']}: {prompt_atuacao(p)}" + chr(10))
        return
    if a.acao == "rascunhar":
        rascunhar(a.roteiro, a.briefing, a.refazer, a.planos)
    elif a.acao == "validar":
        sys.exit(0 if validar(a.roteiro, a.planos) else 1)
    elif a.acao == "rotear":
        rotear(a.roteiro, a.planos)
    else:
        storyboard(a.roteiro, a.saida, a.planos)


if __name__ == "__main__":
    main()
