"""Regras OBJETIVAS da inspeção visual (clipes e imagens-chave), separadas da chamada ao modelo — testáveis sem rede.

Casos reais que o inspetor deixou passar na MinhaMarca "dois mundos" (2026-11-07) e que viraram regra aqui:
  - gravata inventada pelo OmniHuman (c02e) → figurino_involuntario: peça no CORPO que a ficha não tem
  - cifrões desenhados pelo próprio clipe quando a fala pedia dúvida (c03a) → texto_simbolo_gerado
  - Marina com 3 braços (c06c) → membros_extras: contagem por pessoa > 2 braços/mãos
  - tela desenhada nas COSTAS do tablet/celular (c06c, c07a — já na imagem-chave) → interface_traseira
  - fichas nunca enviadas: inspetor procurava ../producao.json fora do projeto → referencias() por caminho explícito
Qualidade visual (deformação, nitidez, estilo) ≠ completude do contrato (critérios, beats): nota alta não compensa
bloqueio objetivo; sem evidência (o modelo não respondeu o campo) = nao_verificado, nunca aprovado.

Funções:
  referencias(base, d, quem)            → (refs [{personagem, arquivo, sha256, origem}], faltando [personagem])
  pedido(contrato, fichas_txt, tipo)    → texto da chamada multimodal ÚNICA (contrato + figurino + anatomia + aparelhos…)
  bloqueios(vis, contrato, elenco, quem)→ [(gravidade, codigo, texto)]
  evidencia_faltando(vis, contrato, quem) → [campo] que o modelo não respondeu
  chave_cache(...)                      → hash de (arquivo, refs, contrato, versão das regras, modelo)
  reservar_analise / confirmar_analise  → custo da análise multimodal no MESMO livro do roteador (categoria analise)
"""
import io
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

REGRAS_VERSAO = "2026-11-07.1"
APARELHOS = re.compile(r"\b(celular|telefone|smartphone|phone|tablet|ipad|notebook|laptop|monitor|tela|screen|portal)\b", re.I)
PECAS_CORPO = re.compile(r"\b(gravata|tie|necktie|óculos|oculos|glasses|chap[eé]u|hat|bon[eé]|cap|cachecol|scarf|colete|vest|"
                         r"blazer|palet[oó]|jacket|casaco|brinco|earring|colar|necklace|rel[oó]gio|watch|crach[aá]|badge|luva|glove)\b", re.I)

PEDIDO = """Você é supervisor de continuidade e qualidade de um estúdio de animação. Analise {o_que} com rigor e responda
SÓ JSON. As primeiras imagens anexadas são as FICHAS de personagem (referência de rosto e figurino), quando houver.
CONTRATO DO PLANO:
{contrato}
FICHAS (figurino e traços que DEVEM aparecer; qualquer peça no corpo fora desta lista é involuntária):
{fichas}
Responda:
{{"criterios": [{{"criterio": "…", "ok": true/false, "visto": "o que aparece", "gravidade": "leve|media|grave"}}],
 "identidade": [{{"personagem": "…", "rosto_igual_ficha": true/false, "visto": "…"}}],
 "anatomia": [{{"personagem": "…", "bracos": N, "maos": N, "pernas_visiveis": N, "dedos_ok": true/false, "segundo": s, "visto": "…"}}],
 "figurino": [{{"personagem": "…", "peca": "…", "na_ficha": true/false, "no_corpo": true/false, "segundo": s}}],
 "aparelhos": [{{"objeto": "celular|tablet|notebook|monitor|…", "quem_usa": "…", "tela_voltada_para": "usuario|camera|lado",
                "interface_desenhada_na_traseira": true/false, "segundo": s}}],
 "textos_simbolos": [{{"conteudo": "…", "onde": "no ar|na tela do aparelho|no cenário", "legivel": true/false, "segundo": s}}],
 "oclusao": ["objeto atravessando corpo/mão, membro sumindo atrás de nada, com o segundo"],
 "continuidade_temporal": ["objeto/peça que aparece ou some sem motivo entre o início e o fim, com o segundo"],
 "deformacoes": ["mãos, dedos, rosto ou objeto deformado, com o segundo"],
 "boca": "fala_sincronizada|fala_fora_de_tempo|boca_parada|boca_mexendo_sem_fala|nao_se_aplica",
 "qualidade_visual": 0-10, "nota": 0-10}}
Conte braços e mãos de CADA pessoa em quadro (um braço escondido atrás do corpo conta como 1 se o ombro mostra).
Liste TODA peça no corpo (gravata, óculos, chapéu, crachá, relógio) e diga se está na ficha. Objetos que a pessoa
segura ou do cenário NÃO são figurino. Liste todo texto, número ou símbolo desenhado pela imagem (inclusive na tela de
aparelhos). Para cada aparelho, diga para onde a TELA está voltada e se há interface desenhada nas COSTAS dele."""


def referencias(base, d, quem):
    """Fichas por CAMINHO EXPLÍCITO: roteiro.elenco[q].ref (relativo à pasta do projeto) → producao.json do projeto
    (a própria pasta e até 2 acima, ficha relativa ao producao.json). Devolve (refs, faltando)."""
    refs, faltando = [], []
    el = (d or {}).get("elenco") or {}
    prod, prod_dir = None, None
    for cand in (base, os.path.dirname(base), os.path.dirname(os.path.dirname(base))):
        arq = os.path.join(cand, "producao.json")
        if os.path.isfile(arq):
            prod, prod_dir = json.load(io.open(arq, encoding="utf-8")), cand
            break
    for q in quem or []:
        f = el.get(q) or next((v for k, v in el.items() if k.lower() == str(q).lower()), None)
        cam, origem = None, None
        if f and f.get("ref"):
            cam, origem = os.path.normpath(os.path.join(base, f["ref"])), "roteiro.elenco"
        elif prod:
            pers = prod.get("personagens", {})
            pf = pers.get(q) or next((v for k, v in pers.items() if k.lower().startswith(str(q).lower())), None)
            if pf and pf.get("ficha"):
                cam, origem = os.path.normpath(os.path.join(prod_dir, pf["ficha"])), "producao.json"
        if cam and os.path.isfile(cam) and ig.midia_valida(cam, "imagem")[0]:
            refs.append({"personagem": q, "arquivo": cam, "sha256": ig.sha256(cam), "origem": origem})
        else:
            faltando.append(q)
    return refs, faltando


def fichas_texto(d, quem):
    el = (d or {}).get("elenco") or {}
    linhas = []
    for q in quem or []:
        f = el.get(q) or {}
        if f:
            linhas.append(f"- {q}: figurino {', '.join(f.get('figurino') or []) or '—'}; traços {', '.join(f.get('tracos') or []) or '—'}")
    return "\n".join(linhas) or "(sem ficha)"


def usa_aparelho(c):
    txt = " ".join(str(c.get(k) or "") for k in ("acao", "acao_en", "atuacao", "quadro_inicial", "quadro_final"))
    txt += " ".join(str(b.get("en") or b.get("pt") or "") for b in c.get("beats") or [])
    return bool(APARELHOS.search(txt))


def pedido(c, fichas_txt, tipo="clipe"):
    sub = {k: c.get(k) for k in ("acao", "atuacao", "voz", "quadro_inicial", "quadro_final", "criterios", "simbolos_permitidos")}
    o_que = "o CLIPE (vídeo com som)" if tipo == "clipe" else "a IMAGEM-CHAVE (primeiro quadro do plano)"
    return PEDIDO.format(o_que=o_que, contrato=json.dumps(sub, ensure_ascii=False), fichas=fichas_txt)


def _na_ficha(peca, elenco, quem):
    fig = " ".join(" ".join((elenco.get(q) or {}).get("figurino") or []) + " " + " ".join((elenco.get(q) or {}).get("tracos") or [])
                   for q in quem or []).lower()
    palavras = [w for w in re.findall(r"\w+", peca.lower()) if len(w) > 3]
    return bool(palavras) and palavras[0] in fig  # o substantivo da peça (1ª palavra); cor/adjetivo não basta ("azul" ≠ gravata)


def bloqueios(vis, c, elenco=None, quem=None):
    """Bloqueios OBJETIVOS e avisos. [(gravidade, codigo, texto)] — os 'grave' reprovam independentemente da nota."""
    elenco, quem = elenco or {}, quem or c.get("quem") or []
    out = []
    for a in vis.get("anatomia") or []:
        b, m = a.get("bracos"), a.get("maos")
        if (isinstance(b, (int, float)) and b > 2) or (isinstance(m, (int, float)) and m > 2):
            out.append(("grave", "membros_extras", f"{a.get('personagem')}: {b} braços / {m} mãos ({a.get('segundo')}s) — {a.get('visto', '')}"[:200]))
        if a.get("dedos_ok") is False:
            out.append(("media", "maos_deformadas", f"{a.get('personagem')}: dedos deformados ({a.get('segundo')}s)"))
    for f in vis.get("figurino") or []:
        if f.get("no_corpo") is False:
            continue
        peca = str(f.get("peca") or "")
        fora = f.get("na_ficha") is False and not _na_ficha(peca, elenco, quem)
        if fora and PECAS_CORPO.search(peca):
            out.append(("grave", "figurino_involuntario", f"{f.get('personagem')}: '{peca}' no corpo e fora da ficha ({f.get('segundo')}s)"))
        elif fora:
            out.append(("media", "figurino_fora_da_ficha", f"{f.get('personagem')}: '{peca}' fora da ficha ({f.get('segundo')}s)"))
    for ap in vis.get("aparelhos") or []:
        para_camera = ap.get("tela_voltada_para") == "camera" and ap.get("quem_usa") and c.get("aparelho_tela_para") != "camera"
        if ap.get("interface_desenhada_na_traseira") or para_camera:
            out.append(("grave", "interface_traseira", f"{ap.get('objeto')} de {ap.get('quem_usa')}: interface nas costas / tela para a câmera "
                                                       f"enquanto a pessoa usa ({ap.get('segundo')}s)"))
    permitidos = [str(s).lower() for s in c.get("simbolos_permitidos") or []]
    for t in vis.get("textos_simbolos") or []:
        cont = str(t.get("conteudo") or "")
        if any(p and p in cont.lower() for p in permitidos):
            continue
        out.append(("grave", "texto_simbolo_gerado", f"o próprio clipe desenhou '{cont[:40]}' ({t.get('onde')}, {t.get('segundo')}s) — "
                                                     "texto/símbolo vai em código, não no modelo de vídeo"))
    for i in vis.get("identidade") or []:
        if i.get("rosto_igual_ficha") is False:
            out.append(("grave", "identidade_diferente", f"{i.get('personagem')}: rosto diferente da ficha — {i.get('visto', '')}"[:200]))
    if vis.get("identidade_ok") is False:  # formato antigo
        out.append(("grave", "identidade_diferente", "personagem diferente da ficha"))
    for o in vis.get("oclusao") or []:
        out.append(("media", "oclusao", f"oclusão: {o}"[:200]))
    for o in vis.get("continuidade_temporal") or []:
        out.append(("media", "continuidade_temporal", f"continuidade: {o}"[:200]))
    defs = vis.get("deformacoes") or []
    for dfm in defs:
        out.append(("media", "deformacao", f"deformação: {dfm}"[:200]))
    if len(defs) >= 3 or (isinstance(vis.get("qualidade_visual"), (int, float)) and vis["qualidade_visual"] <= 3):
        out.append(("grave", "falha_visual_evidente", f"falha visual evidente ({len(defs)} deformações, qualidade {vis.get('qualidade_visual')}/10)"))
    return out


def evidencia_faltando(vis, c, quem=None, tem_refs=True):
    """Campos sem resposta = não verificado (a ausência de prova não é aprovação)."""
    quem = quem or c.get("quem") or []
    falta = []
    if quem and not isinstance(vis.get("anatomia"), list):
        falta.append("anatomia (contagem de membros)")
    if quem and not isinstance(vis.get("figurino"), list):
        falta.append("figurino")
    if quem and tem_refs and not isinstance(vis.get("identidade"), list) and "identidade_ok" not in vis:
        falta.append("identidade")
    if usa_aparelho(c) and not isinstance(vis.get("aparelhos"), list):
        falta.append("orientação dos aparelhos")
    if not isinstance(vis.get("textos_simbolos"), list):
        falta.append("textos e símbolos")
    return falta


def chave_cache(arquivo_sha, refs, c, modelo, tipo="clipe"):
    sub = {k: c.get(k) for k in sorted(c) if k not in ("som", "rota")}
    return ig.sha256_texto(tipo, arquivo_sha, *[r["sha256"] for r in refs], json.dumps(sub, sort_keys=True, ensure_ascii=False, default=str),
                           REGRAS_VERSAO, modelo)


def cache_ler(base, chave):
    try:
        return json.load(io.open(os.path.join(base, "entrega", "cache-analise", f"{chave}.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_gravar(base, chave, vis):
    ig.gravar_json_atomico(os.path.join(base, "entrega", "cache-analise", f"{chave}.json"), vis)


# ---------------------------------------------------------------- custo da análise multimodal (mesmo livro do roteador)
def cfg_analise():
    arq = os.path.join(os.path.dirname(AQUI), "config", "analise.json")
    try:
        return json.load(io.open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def modelo_analise():
    return ((cfg_analise().get("funcoes") or {}).get("analise_visual") or {}).get("modelo") or "gemini-3.8-flash"


def estimar_analise(segundos_video=0.0, n_imagens=0, modelo=None):
    """US$ estimado (conservador) ou None se o preço do modelo não está confirmado."""
    cfg = cfg_analise()
    m = (cfg.get("modelos") or {}).get(modelo or modelo_analise(), {})
    pin, pout = m.get("preco_entrada_por_1m"), m.get("preco_saida_por_1m")
    if pin is None or pout is None:
        return None
    est = cfg.get("estimativa_tokens") or {}
    tin = segundos_video * float(est.get("video_por_s", 300)) + n_imagens * float(est.get("por_imagem", 1300)) + float(est.get("texto", 1500))
    return round((tin * pin + float(est.get("saida", 2500)) * pout) / 1e6, 5)


def reservar_analise(base, pid, estimativa, modelo):
    """(ok, reserva_id, motivo). provedores.autorizar com categoria 'analise' — mesmo teto do projeto, mesma trava.
    Modo custo_zero bloqueia (a revisão vira folha de quadros para o diretor). Preço desconhecido = waiting_approval."""
    import provedores as pv
    _, regras = pv.config()
    t = pv.aplicar_projeto({"job_id": "?", "scene_id": pid, "task_type": "analise", "categoria": "analise", "projeto": base,
                            "requirements": {}, "budget": {}})
    if not os.path.isfile(os.path.join(base, "projeto.json")):
        return True, None, "sem projeto.json — análise fora do livro (modo legado)"
    t["job_id"] = t["_projeto"]["job"]
    aut = pv.autorizar(t, {"id": f"analise:{modelo}"}, estimativa, regras)
    return aut["ok"], aut.get("reserva_id"), aut.get("motivo")


def confirmar_analise(reserva_id, uso=None, modelo=None, falhou=False):
    """Concilia: falha antes de cobrar → libera; uso (usageMetadata) × preço oficial → confirmado; sem uso → fica o reservado."""
    import provedores as pv
    if not reserva_id:
        return
    if falhou:
        return pv.reconciliar(reserva_id, liberar=True)
    real = None
    m = (cfg_analise().get("modelos") or {}).get(modelo or modelo_analise(), {})
    if uso and m.get("preco_entrada_por_1m") is not None:
        real = round((uso.get("promptTokenCount", 0) * m["preco_entrada_por_1m"]
                      + (uso.get("candidatesTokenCount", 0) + uso.get("thoughtsTokenCount", 0)) * m["preco_saida_por_1m"]) / 1e6, 6)
    pv.reconciliar(reserva_id, real=real)
