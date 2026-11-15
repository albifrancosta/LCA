"""Roteador de APIs — grátis primeiro, fallback pago dentro do orçamento (spec ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md).

Uma interface só para TTS, imagem, vídeo e lip-sync: o orquestrador/agentes descrevem a TAREFA (contrato) e o roteador
escolhe o provedor. Catálogo verificável em config/provedores.json; políticas e tetos em config/roteamento.json.

Regras (todas falham FECHADO):
  - compatibilidade antes de preço: etapa, capacidades, idioma, qualidade mínima, licença comercial, credencial, duração,
    perfil de voz, referências visuais preservadas;
  - grátis só entra se cumprir a qualidade mínima; preço desconhecido NUNCA é US$ 0 — bloqueia (ou usa o teto que o
    usuário aprovou para custo desconhecido); gasto pago reserva o valor ANTES da chamada e reconcilia depois;
  - acima do teto → estado `waiting_approval` (memoria/aprovacoes-pendentes.json), nada é gasto;
  - erros: cota (429 de cota) ≠ limite de taxa (429/"sem GPU": espera e tenta de novo) ≠ transitório (5xx/timeout:
    backoff) ≠ credencial (401/403: desabilita a rota, sem repetir) ≠ saldo (402/"Exhausted balance") ≠ payload (400/422:
    não é cota) ≠ timeout ambíguo de job pago (NÃO dispara outro job pago; fica `pendente_verificacao` com o id remoto);
  - disjuntor: N falhas seguidas → provedor fora por um tempo; depois 1 chamada de teste;
  - consistência: a 1ª voz usada num vídeo (perfil + provedor) fica travada — trocar exige aprovação; vídeo/imagem só
    cai para provedor que preserva as referências (mesma imagem-chave/ficha) ou com aprovação.
Registro de tudo em memoria/provedores-tentativas.jsonl (sem chaves). Estado de cota/disjuntor em memoria/provedores-estado.json.

Uso:
  python provedores.py status                          → provedores, credencial (só se existe), cota, disjuntor, saldo
  python provedores.py planejar tarefa.json            → quem seria escolhido, por quê, e quanto custaria (nada é chamado)
  python provedores.py executar tarefa.json            → executa com fallback; imprime a resposta uniforme (JSON)
  python provedores.py aprovar --job video_001 --ate 1.50 [--custo-desconhecido 0.05] [--troca-voz] [--troca-estilo]
                                                       → registra a aprovação que o usuário deu NO CHAT
  python provedores.py relatorio --job video_001       → custo previsto × confirmado × desconhecido, por provedor
  python provedores.py resetar <provedor>              → limpa credencial inválida/disjuntor/saldo depois de corrigir
Tarefa (JSON): {"job_id", "scene_id", "task_type": "tts|video|lipsync|imagem", "mode": "preview|final", "routing_policy",
  "quality_min", "language", "commercial_use", "provider" (só policy manual), "requirements": {"capabilities": [...],
  "voice_profile_id", "duration_s", "imagem", "audio", "texto", "estilo", "tom", "prompt", "direcao": {contrato},
  "saida", "refs": [...]}, "budget": {...}}
"""
import argparse
import datetime
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402
try:
    import chaves as _chaves  # .env / registro do Windows → os.environ (sem sobrescrever)
    _chaves.carregar()
except ImportError:
    pass

CFG_PROV = os.path.join(SKILL, "config", "provedores.json")
CFG_ROT = os.path.join(SKILL, "config", "roteamento.json")
MEM = os.path.join(SKILL, "memoria")
QUALIDADE = {"standard": 1, "high": 2, "premium": 3}


def caminhos():
    """Arquivos de estado (funções, para os testes apontarem para uma pasta temporária via MEM)."""
    return {k: os.path.join(MEM, v) for k, v in {
        "estado": "provedores-estado.json", "reservas": "reservas.json", "aprovacoes": "aprovacoes.json",
        "pendentes": "aprovacoes-pendentes.json", "consist": "consistencia.json", "log": "provedores-tentativas.jsonl"}.items()}


# ---------------------------------------------------------------- erros
class ErroProvedor(Exception):
    """tipo: cota | taxa | transitorio | credencial | saldo | payload | licenca | timeout_ambiguo | permanente."""

    def __init__(self, tipo, msg, retry_after=None, cobrado=None, job_remoto=None):
        super().__init__(msg)
        self.tipo, self.retry_after, self.cobrado, self.job_remoto = tipo, retry_after, cobrado, job_remoto


SEGREDO = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|hf_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_\-]{20,}|Key [A-Za-z0-9:_\-]{16,})")


def limpo(texto):
    """Mensagem de erro sem nada que pareça chave (nunca vai segredo para o log)."""
    s = str(texto)
    for k, v in os.environ.items():
        if any(x in k.upper() for x in ("KEY", "TOKEN", "SECRET")) and v and len(v) >= 8:
            s = s.replace(v, "***")
    return SEGREDO.sub("***", s)[:400]


def classificar_texto(msg, codigo=None):
    """Erro genérico (HTTP/stdout) → ErroProvedor com o tipo certo. Cota ≠ taxa ≠ payload ≠ credencial."""
    m = (msg or "").lower()
    if any(x in m for x in ("exhausted balance", "insufficient", "user is locked", "spending cap", "spend cap")) or codigo == 402:
        return ErroProvedor("saldo", msg)
    if "exceeded your zerogpu" in m or ("quota" in m and "exceed" in m) or ("resource_exhausted" in m and "per day" in m):
        return ErroProvedor("cota", msg)
    if codigo == 429 or "rate limit" in m or "too many requests" in m or "no gpu was available" in m:
        return ErroProvedor("taxa", msg, retry_after=60 if "gpu" in m else None)
    if codigo in (401, 403) or "unauthorized" in m or "invalid api key" in m or "permission denied" in m:
        return ErroProvedor("credencial", msg)
    if codigo in (400, 422) or "validation" in m or "invalid input" in m:
        return ErroProvedor("payload", msg)
    if "license" in m or "licença" in m:
        return ErroProvedor("licenca", msg)
    if codigo in (500, 502, 503, 504) or any(x in m for x in ("timed out", "timeout", "connection", "temporarily")):
        return ErroProvedor("transitorio", msg)
    return ErroProvedor("permanente", msg)


# ---------------------------------------------------------------- config / estado
def ler(arq, padrao):
    try:
        return json.load(io.open(arq, encoding="utf-8")) if os.path.exists(arq) else padrao
    except ValueError:
        return padrao


def config():
    return ler(CFG_PROV, {"provedores": []}), ler(CFG_ROT, {})


def agora():
    return datetime.datetime.now()


def iso(t):
    return t.isoformat(timespec="seconds")


def futuro(s, ref=None):
    return bool(s) and datetime.datetime.fromisoformat(s) > (ref or agora())


def periodo(p, ref=None):
    ref = ref or agora()
    return {"daily": ref.strftime("%Y-%m-%d"), "monthly": ref.strftime("%Y-%m")}.get(p or "", "sempre")


def registrar(evento):
    arq = caminhos()["log"]
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with ig.trava(arq):
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(evento, quando=iso(agora())), ensure_ascii=False, default=str) + "\n")


def estado_de(pid, est=None):
    est = est if est is not None else ler(caminhos()["estado"], {})
    return est.get(pid, {})


def mexer_estado(pid, func):
    def f(d):
        func(d.setdefault(pid, {}))
    ig.atualizar_json(caminhos()["estado"], f)


def aprovacao(job):
    return ler(caminhos()["aprovacoes"], {}).get(job, {})


# ---------------------------------------------------------------- tarefa
def normalizar(tarefa, regras):
    t = json.loads(json.dumps(tarefa))
    if not t.get("job_id") or not t.get("task_type"):
        raise ErroProvedor("payload", "tarefa sem job_id ou task_type")
    rt = regras.get("routing", {})
    t["_politica_explicita"] = bool(t.get("routing_policy"))
    t["_quality_explicita"] = "quality_min" in t
    t.setdefault("routing_policy", rt.get("policy", "free_first"))
    t.setdefault("mode", "final")
    t.setdefault("quality_min", regras.get("quality", {}).get(t["mode"], "high"))
    t.setdefault("language", "pt-BR")
    t.setdefault("commercial_use", False)
    t.setdefault("requirements", {})
    t.setdefault("budget", {})
    t["_api_router"] = regras.get("api_router") or {}
    req = t["requirements"]
    declarado = (tarefa.get("requirements") or {}).get("tipo_take")
    if t["task_type"] in ("video", "lipsync") and not req.get("tipo_take"):
        req["tipo_take"] = classificar_take(req.get("direcao") or {}, t["task_type"])
    if declarado == "simples" and "quality_min" not in tarefa:
        t["quality_min"] = "standard"  # cena simples DECLARADA no contrato: modelo rápido/barato serve (inferido não baixa o piso)
    if t["routing_policy"] not in rt.get("politicas_validas", ["free_first", "best_value", "lowest_cost", "premium", "manual", "runware_primary"]):
        raise ErroProvedor("payload", f"política desconhecida: {t['routing_policy']}")
    return aplicar_projeto(t)


CAMERA_MOVE = ("travelling", "dolly", "pan ", "panor", "grua", "crane", "drone", "orbit", "órbita", "orbita", "tracking", "steadicam",
               "push-in", "push in", "zoom", "tilt", "aproxima", "afasta")


def classificar_take(c, task_type="video"):
    """Tipo do take para a pontuação: fala | cinematografico | motion | i2v_personagem | simples (contrato do plano)."""
    rota = (c.get("rota") or {}).get("rota") if isinstance(c.get("rota"), dict) else c.get("rota_fixa")
    if rota in ("motion", "composicao", "foto_camera", "codigo") or c.get("modo") in ("titulo", "tela", "cartao"):
        return "motion"
    if task_type == "lipsync" or c.get("voz") == "em_quadro":
        return "fala"
    cam = " ".join(str(c.get(k) or "") for k in ("camera", "motivo_camera")).lower()
    if c.get("quem"):
        return "i2v_personagem"
    if any(m in cam for m in CAMERA_MOVE):
        return "cinematografico"  # cenário/objeto com câmera em movimento
    return "simples"


def aplicar_projeto(t):
    """2026-11-07: tarefa com "projeto": <pasta> herda do projeto.json o modo de autonomia, o teto POR PROJETO, o uso
    (publicidade ⇒ commercial_use) e a política do modo — a tarefa não precisa repetir nada disso."""
    if not t.get("projeto"):
        return t
    import projeto as pj
    cfg = pj.carregar(t["projeto"])
    t["_projeto"] = {"modo": cfg["autonomia"]["modo"], "teto": float(cfg["orcamento"].get("teto_autorizado") or 0),
                     "saldo_provedor": cfg["orcamento"].get("saldo_provedor") or {},
                     "saldo_desde": cfg["orcamento"].get("saldo_desde"),
                     "licencas_confirmadas": cfg["orcamento"].get("licencas_confirmadas") or [],
                     "custo_desconhecido_ate": cfg["orcamento"].get("custo_desconhecido_ate"), "job": pj.job_id(cfg)}
    if not t.get("_politica_explicita"):
        t["routing_policy"] = pj.politica(cfg)
    if cfg.get("uso") == "publicidade":
        t["commercial_use"] = True
    # piso de qualidade do take final: o projeto decide (custo_zero → standard, porque pago não existe; o INSPETOR barra defeito)
    piso = (cfg.get("qualidade") or {}).get("piso_final") or ("standard" if cfg["autonomia"]["modo"] == "custo_zero" else None)
    if piso and not t.get("_quality_explicita") and t.get("mode", "final") == "final":
        t["quality_min"] = piso
    return t


def chave_idempotencia(t):
    """Mesma tarefa (etapa, cena, requisitos de entrada com os HASHES dos arquivos) = mesma chave. Usada para não pagar
    duas vezes pelo mesmo pedido (reenvio depois de queda, retomada, dois processos)."""
    req = dict(t.get("requirements") or {})
    req.pop("saida", None)
    for k in ("imagem", "audio", "ultimo_quadro"):
        if req.get(k) and os.path.isfile(req[k]):
            req[k] = ig.sha256(req[k])
    req["refs"] = [ig.sha256(r) if os.path.isfile(r) else r for r in req.get("refs") or []]
    fixo = t.get("provider") if t.get("routing_policy") == "manual" else ""
    return ig.sha256_texto(t["task_type"], t.get("scene_id"), fixo, json.dumps(req, sort_keys=True, ensure_ascii=False, default=str))


def eventos(filtro=None):
    arq = caminhos()["log"]
    if not os.path.exists(arq):
        return []
    out = []
    for linha in open(arq, encoding="utf-8"):
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        if filtro is None or filtro(e):
            out.append(e)
    return out


def ja_feito(t, chave):
    """Sucesso anterior com a MESMA chave e o arquivo de saída ainda íntegro (mesmo sha) → reaproveita sem pagar."""
    for e in reversed(eventos(lambda e: e.get("tipo") == "tentativa" and e.get("chave") == chave and e.get("resultado") == "sucesso")):
        s = e.get("saida")
        if s and os.path.isfile(s) and e.get("sha_saida") and ig.sha256(s) == e["sha_saida"]:
            return e
    return None


def jobs_pendentes(job_id, scene_id):
    """Jobs pagos que deram timeout ambíguo (pode ter sido cobrado / pode ainda estar rodando) e ainda não foram
    resolvidos (recuperado, ou confirmado como falho). Ao retomar, eles são consultados ANTES de qualquer envio novo."""
    pend = {}
    for e in eventos(lambda e: e.get("job_id") == job_id and e.get("scene_id") == scene_id):
        k = e.get("job_remoto") or e.get("id")
        if e.get("tipo") == "tentativa" and e.get("erro_tipo") == "timeout_ambiguo":
            pend[k] = e
        elif e.get("tipo") == "recuperacao" and e.get("resultado") in ("recuperado", "falhou_no_provedor", "descartado"):
            pend.pop(k, None)
    return list(pend.values())


# ---------------------------------------------------------------- compatibilidade
def compativel(p, t, est, consist, tem_credencial=None):
    """(ok, motivo). Tudo que NÃO depende de dinheiro (preço vem depois)."""
    req = t["requirements"]
    tem_credencial = tem_credencial or (lambda env: bool(os.environ.get(env)))
    if not p.get("enabled"):
        return False, f"desabilitado ({p.get('motivo_desabilitado', 'catálogo')})"
    if p.get("stage") != t["task_type"]:
        return False, "outra etapa"
    if not p.get("adaptador"):
        return False, "sem adaptador no roteador"
    if t["routing_policy"] == "manual" and p["id"] != t.get("provider"):
        return False, "política manual: só o provedor escolhido"
    langs = p.get("languages") or ["*"]
    if "*" not in langs and t.get("language") not in langs:
        return False, f"idioma {t.get('language')} não suportado"
    falta = set(req.get("capabilities") or []) - set(p.get("capabilities") or [])
    if falta:
        return False, f"sem capacidade: {', '.join(sorted(falta))}"
    if qualidade_efetiva(p, t.get("_hist")) < QUALIDADE.get(t["quality_min"], 2):
        return False, f"qualidade {p.get('quality')} abaixo de {t['quality_min']}"
    confirmadas = (t.get("_projeto") or {}).get("licencas_confirmadas") or []
    if t.get("commercial_use") and p.get("commercial_use") != "allowed" and p["id"] not in confirmadas:
        return False, (f"uso comercial '{p.get('commercial_use')}' (conteúdo comercial exige 'allowed' — ou o usuário confirma os "
                       f"termos no chat e o id entra em projeto.json orcamento.licencas_confirmadas)")
    if p.get("credencial_env") and not p.get("credencial_opcional") and not tem_credencial(p["credencial_env"]):
        return False, f"sem credencial ({p['credencial_env']} não definida)"
    if estado_de(p["id"], est).get("credencial_invalida"):
        return False, "credencial recusada pelo provedor (401/403) — corrija e rode `provedores.py resetar`"
    d = req.get("duration_s")
    if d and p.get("duracoes") and float(d) > max(p["duracoes"]) + 1e-6:
        return False, f"{d}s passa do máximo do modelo ({max(p['duracoes'])}s) — divida o plano"
    fx = p.get("faixa_duracao")
    if d and fx and fx[1] is not None and float(d) > float(fx[1]) + 1e-6:
        return False, f"{d}s passa do máximo do provedor ({fx[1]}s, lido na API) — divida o plano"
    if req.get("exige_ultimo_quadro") and "ultimo_quadro" not in (p.get("capabilities") or []):
        return False, "não aceita o quadro final (continuidade exigida)"
    if t["task_type"] == "tts":
        vp = req.get("voice_profile_id")
        if not vp:
            return False, "tarefa de voz sem voice_profile_id (a voz aprovada)"
        if vp not in (p.get("voice_profiles") or []):
            return False, f"não tem a voz {vp}"
        trava = (consist.get(t["job_id"]) or {}).get(f"voz:{vp}")
        if trava and trava != p["id"] and not aprovacao(t["job_id"]).get("troca_voz"):
            return False, f"a voz {vp} deste vídeo foi feita em {trava} — trocar de provedor exige aprovação"
    if t["task_type"] in ("video", "imagem", "lipsync"):
        trava = (consist.get(t["job_id"]) or {}).get("estilo")
        if trava and trava != p["id"] and not p.get("referencias_preservadas") and not aprovacao(t["job_id"]).get("troca_estilo"):
            return False, f"vídeo começou em {trava}; este provedor não preserva as referências — exige aprovação"
    return True, ""


def disponibilidade(p, est, ref=None):
    """(ok, motivo) — cota, saldo e disjuntor pelo estado local (fontes: erros do provedor e contador local)."""
    e = estado_de(p["id"], est)
    try:
        import provider_discovery as pdisc
        fora, motivo = pdisc.indisponivel_recente(p["id"])
        if fora:
            return False, f"descoberta: {motivo} (provider_discovery.py)"
    except Exception:  # noqa: BLE001 — sem arquivo de descoberta não é erro
        pass
    if futuro(e.get("aberto_ate"), ref):
        return False, f"disjuntor aberto até {e['aberto_ate']} ({e.get('ultimo_erro', '')[:80]})"
    if futuro(e.get("esgotado_ate"), ref):
        return False, f"cota esgotada até {e['esgotado_ate']}"
    if futuro(e.get("sem_saldo_ate"), ref):
        return False, f"sem saldo (desde {e.get('sem_saldo_desde')}) — recarregue e rode `provedores.py resetar {p['id']}`"
    q = p.get("quota") or {}
    dono = q.get("compartilha_cota_com") or p["id"]
    if dono != p["id"] and futuro(estado_de(dono, est).get("esgotado_ate"), ref):
        return False, f"cota compartilhada com {dono} esgotada"
    lim = q.get("limit")
    if q.get("detection") == "local_counter" and lim and not (p.get("credencial_env") and os.environ.get(p["credencial_env"])):
        usadas = (estado_de(dono, est).get("cota") or {}).get(periodo(q.get("period"), ref), 0)
        if usadas >= lim:
            return False, f"cota local {usadas}/{lim} no período"
    return True, ""


def estimar(p, t):
    """Custo estimado em US$ ou None (desconhecido). Grátis comprovado (preço 0 no catálogo) = 0."""
    pr = p.get("price") or {}
    v = pr.get("amount_per_unit")
    res = (t.get("requirements") or {}).get("resolucao") or p.get("resolucao_padrao")
    if res and (pr.get("por_resolucao") or {}).get(res) is not None:
        v = pr["por_resolucao"][res]
    if v is None:
        return None
    if v == 0:
        return 0.0
    u = pr.get("unit")
    req = t["requirements"]
    if u == "second":
        d = float(req.get("duration_s") or 0)
        if not d and t["task_type"] == "lipsync" and req.get("audio") and os.path.isfile(req["audio"]):
            d = ig.duracao_midia(req["audio"]) if hasattr(ig, "duracao_midia") else _dur_audio(req["audio"])  # cobrado pelo áudio
        if p.get("duracoes"):
            ok = [x for x in p["duracoes"] if x >= d - 1e-6]
            if not ok:
                return None
            d = min(ok)
        return round(v * d, 4) if d else None
    if u in ("call", "clip", "image", "track"):
        return round(v * int(req.get("n", 1)), 4)
    return None


def _dur_audio(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def ordenar(cands, t, hist):
    pol = t["routing_policy"]
    taxa = lambda p: hist.get(p["id"], {}).get("taxa", 0.8)
    q = lambda p: QUALIDADE.get(p.get("quality"), 0)
    custo = lambda e: 9e9 if e is None else e
    if pol in ("free_first", "manual"):
        return sorted(cands, key=lambda c: (0 if c[1] == 0 else 1, custo(c[1]), -q(c[0]), -taxa(c[0])))
    if pol == "runware_primary":
        # INTEGRACAO-RUNWARE.md §4: entre os candidatos que JÁ cumprem capacidade/qualidade/licença/credencial, Runware
        # primeiro, ordenado pelo custo por tomada APROVADA (preço ÷ taxa de aprovação); fal.ai e outros como fallback.
        # Grátis comprovado continua na frente (saldo promocional NÃO é grátis: tem preço no catálogo).
        rw = lambda p: 0 if (p.get("fornecedor") == "runware" or p["id"].startswith("runware-")) else 1  # noqa: E731
        return sorted(cands, key=lambda c: (0 if c[1] == 0 else 1, rw(c[0]), custo(c[1]) / max(taxa(c[0]), 0.35), -q(c[0])))
    # 2026-11-07: custo total ESPERADO por segundo APROVADO (preço ÷ taxa de aproveitamento ÷ segundos) — um modelo
    # barato que reprova metade dos takes sai mais caro que um um pouco mais caro que passa de primeira.
    dur = max(float(t["requirements"].get("duration_s") or 1), 0.1)
    por_seg = lambda c: custo(c[1]) / max(taxa(c[0]), 0.2) / dur  # noqa: E731
    lat = lambda p: hist.get(p["id"], {}).get("latencia_s") or 120.0  # noqa: E731
    if pol == "pontuacao":
        return sorted(cands, key=lambda c: (nivel(c[0], c[1], t) if (t.get("_api_router") or {}).get("prefer_free", True) else 0,
                                            -pontuar(c[0], c[1], t, hist)))
    if pol == "lowest_cost":
        return sorted(cands, key=lambda c: (por_seg(c), -q(c[0]), lat(c[0])))
    if pol == "premium":
        return sorted(cands, key=lambda c: (-q(c[0]), por_seg(c)))
    # best_value: qualidade por dólar aprovado; o tempo entra como desempate suave (cada 10 min ≈ +5 % no custo)
    return sorted(cands, key=lambda c: (por_seg(c) + 0.005 * lat(c[0]) / 60 * (c[1] or 0)) / max(q(c[0]), 1))


PESOS_PADRAO = {"qualidade": 0.30, "custo": 0.25, "compatibilidade": 0.20, "disponibilidade": 0.15, "consistencia": 0.10}


def nivel(p, est, t):
    """0 = grátis comprovado · 1 = crédito promocional válido · 2 = pago."""
    if est == 0:
        return 0
    if (t.get("_api_router") or {}).get("allow_promo_credits", True) and promo_cobre(p, est, t):
        return 1
    return 2


def pontuar(p, est, t, hist=None, pesos=None):
    """Nota 0–1 = Σ peso × componente. Pesos de config/roteamento.json api_router.pontuacao (valores INICIAIS configuráveis).
    qualidade: nível declarado × taxa de aprovação medida · custo: 1 − (US$/s ÷ referência), grátis = 1, desconhecido = 0 ·
    compatibilidade: perfil do provedor para o tipo do take · disponibilidade: saúde (falhas seguidas) e latência mediana ·
    consistência: preserva referências + aceita o quadro final quando o take pede continuidade."""
    hist = hist if hist is not None else historico()
    cfg = (t.get("_api_router") or {}).get("pontuacao") or {}
    w = dict(PESOS_PADRAO, **(pesos or cfg.get("pesos") or {}))
    req = t.get("requirements") or {}
    h = hist.get(p["id"], {})
    qual = QUALIDADE.get(p.get("quality"), 1) / 3 * h.get("taxa", 0.8)
    dur = max(float(req.get("duration_s") or 5), 0.1)
    ref = float(cfg.get("custo_referencia_por_s") or 0.20)
    custo = 1.0 if est == 0 else (0.0 if est is None else max(0.0, 1 - (est / dur) / ref))
    if est and promo_cobre(p, est, t):
        custo = max(custo, 0.9)
    compat = float((p.get("perfil") or {}).get(req.get("tipo_take") or "simples", 0.5))
    e = estado_de(p["id"])
    disp = max(0.0, 1 - 0.3 * int(e.get("falhas_seguidas", 0))) * (1 - min(1.0, (h.get("latencia_s") or 120) / 900) * 0.5)
    cons = (0.8 if p.get("referencias_preservadas") else 0.4) + (0.2 if req.get("ultimo_quadro") and "ultimo_quadro" in (p.get("capabilities") or []) else 0)
    return round(w["qualidade"] * qual + w["custo"] * custo + w["compatibilidade"] * compat + w["disponibilidade"] * disp
                 + w["consistencia"] * min(1.0, cons), 4)


def promo_arq():
    return os.path.join(MEM, "creditos-promocionais.json")


def promo_restante(p):
    """Saldo promocional (na unidade do crédito) = saldo registrado no catálogo − uso contado localmente; 0 se vencido."""
    c = p.get("creditos_promocionais") or {}
    if not c or (c.get("valido_ate") and c["valido_ate"] < agora().strftime("%Y-%m-%d")):
        return 0.0
    usado = float((ler(promo_arq(), {}).get(p["id"]) or {}).get("usado", 0))
    return max(0.0, float(c.get("saldo") or 0) - usado)


def promo_cobre(p, est, t):
    c = p.get("creditos_promocionais") or {}
    if not c:
        return False
    precisa = float((t.get("requirements") or {}).get("duration_s") or 5) if c.get("unidade", "segundos") == "segundos" else float(est or 0)
    return promo_restante(p) >= precisa - 1e-9


def promo_consumir(p, t, est):
    c = p.get("creditos_promocionais") or {}
    qtd = float((t.get("requirements") or {}).get("duration_s") or 5) if c.get("unidade", "segundos") == "segundos" else float(est or 0)

    def f(d):
        x = d.setdefault(p["id"], {"usado": 0.0})
        x["usado"] = round(float(x["usado"]) + qtd, 4)
    ig.atualizar_json(promo_arq(), f)
    return qtd


def historico():
    h, arq = {}, caminhos()["log"]
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            try:
                e = json.loads(linha)
            except ValueError:
                continue
            if e.get("tipo") == "tentativa":
                x = h.setdefault(e["provedor"], {"ok": 0, "n": 0, "lat": []})
                x["n"] += 1
                x["ok"] += e.get("resultado") == "sucesso"
                if e.get("resultado") == "sucesso" and e.get("latencia_ms"):
                    x["lat"].append(e["latencia_ms"] / 1000)
            elif e.get("tipo") == "aprovacao_final" and e.get("provedor"):  # veredito do INSPETOR depois do roteador
                x = h.setdefault(e["provedor"], {"ok": 0, "n": 0, "lat": []})
                x["ok"] -= e.get("estado") == "reprovado"
                x["fin_n"] = x.get("fin_n", 0) + 1
                x["fin_ok"] = x.get("fin_ok", 0) + (e.get("estado") == "aprovado")
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None  # noqa: E731
    return {k: {"taxa": max(0.05, (v["ok"] + 1.6) / (v["n"] + 2)) if v["n"] else 0.8, "latencia_s": med(v["lat"]),
                "inspecionados": v.get("fin_n", 0), "aprovacao_inspetor": (v["fin_ok"] / v["fin_n"]) if v.get("fin_n") else None}
            for k, v in h.items()}


PROMOVE = {"min_takes": 4, "min_aprovacao": 0.75}


def qualidade_efetiva(p, hist=None):
    """Nível declarado; um provedor que provou no INSPETOR (≥ 4 takes, ≥ 75 % aprovados) sobe para 'high' — é assim que um
    Space grátis 'standard' passa a concorrer em take final, por evidência e não por ser grátis."""
    q = QUALIDADE.get(p.get("quality"), 0)
    h = (hist if hist is not None else historico()).get(p["id"], {})
    if h.get("inspecionados", 0) >= PROMOVE["min_takes"] and (h.get("aprovacao_inspetor") or 0) >= PROMOVE["min_aprovacao"]:
        q = max(q, QUALIDADE["high"])
    return q


def registrar_veredito(job_id, scene_id, provedor, estado):
    """O modo autônomo chama isto com o veredito do inspetor — alimenta a taxa de aproveitamento real por provedor."""
    if provedor:
        registrar({"tipo": "aprovacao_final", "job_id": job_id, "scene_id": scene_id, "provedor": provedor, "estado": estado})


# ---------------------------------------------------------------- orçamento
def autorizar(t, p, estimativa, regras, reservar=True):
    """{"ok", "estado": livre|reservado|cabe|waiting_approval|bloqueado, "motivo", "reserva_id", "valor"}.
    A reserva é feita sob trava: dois processos não gastam o mesmo saldo."""
    b = dict(regras.get("budget", {}), **(t.get("budget") or {}))
    ap = aprovacao(t["job_id"])
    proj = t.get("_projeto") or {}
    if estimativa == 0:
        return {"ok": True, "estado": "livre", "valor": 0.0}
    if proj.get("modo") == "custo_zero":  # nenhuma chamada paga (nem de preço desconhecido); não vira pedido de aprovação
        return {"ok": False, "estado": "bloqueado", "motivo": f"{p['id']}: projeto em modo custo_zero — só rotas grátis/locais"}
    if not regras.get("routing", {}).get("allow_paid_fallback", True) or (regras.get("api_router") or {}).get("allow_paid_fallback") is False:
        return {"ok": False, "estado": "bloqueado", "motivo": f"{p['id']}: fallback pago desligado (allow_paid_fallback=false)"}
    if (regras.get("api_router") or {}).get("require_paid_approval") and not (proj.get("teto") or ap.get("ate") or b.get("max_cost_per_video")):
        return {"ok": False, "estado": "waiting_approval",
                "motivo": f"{p['id']}: gasto pago exige orçamento configurado (projeto.json teto, `provedores.py aprovar` ou teto global)"}
    valor = estimativa
    if valor is None:
        teto_desc = ap.get("custo_desconhecido_ate") or proj.get("custo_desconhecido_ate")
        if b.get("default_unknown_cost_policy", "block") == "block" and not teto_desc:
            return {"ok": False, "estado": "waiting_approval",
                    "motivo": f"{p['id']}: preço desconhecido — preencha o preço no catálogo ou aprove um teto para custo "
                              "desconhecido (`provedores.py aprovar --custo-desconhecido`)"}
        valor = float(teto_desc)
    valor = round(valor * (1 + float(b.get("margem_seguranca", 0))), 4)
    teto_op = ap.get("max_por_operacao") or b.get("max_cost_per_operation")
    teto_video = ap.get("ate") or proj.get("teto") or b.get("max_cost_per_video")  # teto POR PROJETO quando há projeto.json
    teto_mes = b.get("max_cost_per_month")
    job_raiz = proj.get("job") or t["job_id"]
    saldo_prov = (proj.get("saldo_provedor") or {}).get(p["id"])
    res = {"ok": False}

    def f(d):
        rs = d.setdefault("reservas", [])
        soma = lambda filtro: sum((r["real"] if r.get("real") is not None else r["valor"]) for r in rs
                                  if filtro(r) and r["estado"] in ("reservada", "reconciliada"))
        gasto_job = soma(lambda r: r["job_id"] == job_raiz or str(r["job_id"]).startswith(job_raiz + ":"))
        gasto_mes = soma(lambda r: r["quando"][:7] == agora().strftime("%Y-%m"))
        gasto_prov = soma(lambda r: r.get("provedor") == p["id"] and r.get("quando", "") >= str(proj.get("saldo_desde") or ""))
        if saldo_prov is not None and gasto_prov + valor > float(saldo_prov) + 1e-9:
            res.update(estado="bloqueado", motivo=f"{p['id']}: saldo informado no provedor US$ {float(saldo_prov):.2f} não cobre "
                       f"US$ {valor:.2f} (já comprometido US$ {gasto_prov:.2f}) — recarregar ou usar outro provedor")
        elif teto_op is not None and valor > float(teto_op) + 1e-9:
            res.update(estado="waiting_approval", motivo=f"{p['id']}: US$ {valor:.2f} por operação passa do teto US$ {float(teto_op):.2f}")
        elif teto_video is not None and gasto_job + valor > float(teto_video) + 1e-9:
            res.update(estado="waiting_approval", motivo=f"{p['id']}: o vídeo iria a US$ {gasto_job + valor:.2f} (teto US$ "
                       f"{float(teto_video):.2f}; já reservado/gasto US$ {gasto_job:.2f})")
        elif teto_mes is not None and gasto_mes + valor > float(teto_mes) + 1e-9:
            res.update(estado="waiting_approval", motivo=f"teto do mês US$ {float(teto_mes):.2f} seria passado")
        elif not reservar:
            res.update(ok=True, estado="cabe", valor=valor, gasto_job=gasto_job)
        else:
            rid = uuid.uuid4().hex[:12]
            rs.append({"id": rid, "job_id": t["job_id"], "scene_id": t.get("scene_id"), "provedor": p["id"], "valor": valor,
                       "estimado": estimativa, "estado": "reservada", "real": None, "quando": iso(agora()),
                       "categoria": t.get("categoria") or {"tts": "voz", "imagem": "imagem"}.get(t["task_type"], "geracao")})
            res.update(ok=True, estado="reservado", reserva_id=rid, valor=valor)
    if reservar:
        ig.atualizar_json(caminhos()["reservas"], f, padrao={"reservas": []})
    else:
        f(ler(caminhos()["reservas"], {"reservas": []}))
    return res


def reconciliar(reserva_id, real=None, liberar=False):
    """real=None mantém o valor reservado como gasto (desconhecido conta como gasto, nunca como zero)."""
    if not reserva_id:
        return

    def f(d):
        for r in d.get("reservas", []):
            if r["id"] == reserva_id:
                r["estado"] = "liberada" if liberar else "reconciliada"
                r["real"] = None if liberar else real
                r["custo_confirmado"] = real is not None and not liberar
    ig.atualizar_json(caminhos()["reservas"], f, padrao={"reservas": []})


def pendente_aprovacao(t, motivos):
    """Bloqueio pendente é registrado UMA vez por (job, cena, etapa, motivo): repetir o pedido só soma `repeticoes`."""
    chave = ig.sha256_texto(t["job_id"], t.get("scene_id"), t["task_type"], *sorted(re.sub(r"[\d.,]+", "#", m) for m in motivos))
    res = {"nova": True}

    def f(d):
        ps = d.setdefault("pendentes", [])
        for x in ps:
            if x.get("chave") == chave and x.get("estado") == "waiting_approval":
                x["repeticoes"] = int(x.get("repeticoes", 1)) + 1
                x["ultima"] = iso(agora())
                res["nova"] = False
                return
        ps.append({"job_id": t["job_id"], "scene_id": t.get("scene_id"), "task_type": t["task_type"], "chave": chave,
                   "motivos": motivos, "quando": iso(agora()), "estado": "waiting_approval", "repeticoes": 1})
    ig.atualizar_json(caminhos()["pendentes"], f, padrao={"pendentes": []})


# ---------------------------------------------------------------- saúde / cota / consistência
def sucesso_saude(p):
    q = p.get("quota") or {}
    dono = q.get("compartilha_cota_com") or p["id"]

    def ok(e):
        e["falhas_seguidas"] = 0
        e.pop("aberto_ate", None)
    mexer_estado(p["id"], ok)
    if q.get("detection") == "local_counter":
        per = periodo(q.get("period"))

        def conta(e):
            c = e.setdefault("cota", {})
            c[per] = c.get(per, 0) + 1
        mexer_estado(dono, conta)


def falha_saude(p, regras, erro):
    cb = regras.get("routing", {}).get("circuit_breaker", {})

    def f(e):
        e["falhas_seguidas"] = e.get("falhas_seguidas", 0) + 1
        e["ultimo_erro"] = limpo(erro)
        if e["falhas_seguidas"] >= int(cb.get("falhas_para_abrir", 3)):
            e["aberto_ate"] = iso(agora() + datetime.timedelta(seconds=int(cb.get("esfriar_s", 600))))
            e["falhas_seguidas"] = 0  # meio-aberto depois de esfriar: 1 chamada de teste
    mexer_estado(p["id"], f)


def marcar(p, tipo, erro):
    q = p.get("quota") or {}
    dono = q.get("compartilha_cota_com") or p["id"]
    if tipo == "cota":
        horas = q.get("reset_horas") or (24 if q.get("period") == "daily" else 1)
        ate = iso(agora() + datetime.timedelta(hours=horas))
        for pid in {p["id"], dono}:
            mexer_estado(pid, lambda e: e.update(esgotado_ate=ate, ultimo_erro=limpo(erro)))
    elif tipo == "saldo":
        mexer_estado(p["id"], lambda e: e.update(sem_saldo_ate=iso(agora() + datetime.timedelta(days=3650)),
                                                 sem_saldo_desde=iso(agora()), ultimo_erro=limpo(erro)))
    elif tipo == "credencial":
        mexer_estado(p["id"], lambda e: e.update(credencial_invalida=True, ultimo_erro=limpo(erro)))


def travar_consistencia(t, p):
    def f(d):
        j = d.setdefault(t["job_id"], {})
        vp = t["requirements"].get("voice_profile_id")
        if t["task_type"] == "tts" and vp:
            j.setdefault(f"voz:{vp}", p["id"])
        if t["task_type"] in ("video", "imagem", "lipsync"):
            j.setdefault("estilo", p["id"])
    ig.atualizar_json(caminhos()["consist"], f)


# ---------------------------------------------------------------- inspeção da saída
def inspecionar_padrao(saida, t):
    """{"aceito", "estado", "motivo"}: mídia válida + checagem por etapa. Não verificado ≠ reprovado."""
    tipo = {"tts": "audio", "video": "video", "lipsync": "video", "imagem": "imagem"}[t["task_type"]]
    ok, m = ig.midia_valida(saida, tipo)
    if not ok:
        return {"aceito": False, "estado": ig.REPROVADO, "motivo": m}
    req = t["requirements"]
    if t["task_type"] == "tts" and req.get("texto"):
        from inspetor import checar_fala
        cob, prob = checar_fala(saida, req["texto"])
        if any(g == "grave" for g, _ in prob):
            return {"aceito": False, "estado": ig.REPROVADO, "motivo": "; ".join(x for _, x in prob)}
        return {"aceito": True, "estado": ig.APROVADO, "motivo": f"fala {cob:.0%}"}
    if t["task_type"] == "video" and (req.get("direcao") or {}).get("modo") in ig.MODOS_ANIMADOS:
        import atuacao
        c = req["direcao"]
        r, _ = atuacao.analisar(saida, exige=c.get("exige") or [], beats=c.get("beats"), n_personagens=max(1, len(c.get("quem") or [1])))
        if r["estado"] == ig.REPROVADO:
            return {"aceito": False, "estado": ig.REPROVADO, "motivo": "; ".join(x for g, x in r["problemas"] if g == "grave")[:300]}
        return {"aceito": True, "estado": r["estado"], "motivo": "atuação medida" if r["estado"] == ig.APROVADO else "falta revisão visual"}
    return {"aceito": True, "estado": ig.NAO_VERIFICADO, "motivo": "mídia válida; revisão visual pendente"}


# ---------------------------------------------------------------- execução com fallback
def candidatos(t, catalogo, adaptadores, credencial=None):
    est, consist = ler(caminhos()["estado"], {}), ler(caminhos()["consist"], {})
    t["_hist"] = historico()
    rejeitados, cands = [], []
    for p in catalogo["provedores"]:
        ok, motivo = compativel(p, t, est, consist, credencial)
        if ok:
            ok, motivo = disponibilidade(p, est)
        if ok and p["adaptador"] not in adaptadores:
            ok, motivo = False, f"adaptador {p['adaptador']} não carregado"
        if not ok:
            if p.get("stage") == t["task_type"]:
                rejeitados.append({"provedor": p["id"], "motivo": motivo})
            continue
        cands.append((p, estimar(p, t)))
    return ordenar(cands, t, historico()), rejeitados


def executar(tarefa, adaptadores=None, inspecionar=None, dormir=time.sleep, credencial=None):
    """Resposta uniforme: status success | waiting_approval | pendente_verificacao | sem_provedor."""
    catalogo, regras = config()
    t = normalizar(tarefa, regras)
    adaptadores = adaptadores or ADAPTADORES
    inspecionar = inspecionar or inspecionar_padrao
    chave = chave_idempotencia(t)
    feito = ja_feito(t, chave)
    if feito:  # idempotência: o mesmo pedido já foi pago e o arquivo está íntegro — não paga de novo
        saida = t["requirements"].get("saida") or feito["saida"]
        if os.path.abspath(saida) != os.path.abspath(feito["saida"]):
            os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
            shutil.copyfile(feito["saida"], saida)
        def f(d):  # o livro registra o reuso com custo real 0 (rastro completo: nenhuma chamada saiu)
            d.setdefault("reservas", []).append({"id": uuid.uuid4().hex[:12], "job_id": t["job_id"], "scene_id": t.get("scene_id"),
                                                 "provedor": feito["provedor"], "valor": 0.0, "estimado": 0.0, "estado": "reconciliada",
                                                 "real": 0.0, "custo_confirmado": True, "quando": iso(agora()), "categoria": "reuso"})
        ig.atualizar_json(caminhos()["reservas"], f, padrao={"reservas": []})
        registrar({"tipo": "reuso_idempotente", "job_id": t["job_id"], "scene_id": t.get("scene_id"), "chave": chave, "saida": saida,
                   "de": feito["saida"]})
        return dict(resposta(t, "success", {"id": feito["provedor"], "tier": feito.get("tier")}, [], 0, saida=saida, estimado=0.0,
                             real=0.0, qa=feito.get("qa")), cache=True, reuso_de=feito.get("id"))
    pend = jobs_pendentes(t["job_id"], t.get("scene_id"))
    if pend:  # retomada: job pago sem resposta é CONSULTADO antes de qualquer envio novo
        rec = recuperar_pendentes(t, pend, adaptadores, catalogo)
        if rec:
            return rec
        return resposta(t, "pendente_verificacao", None, [{"pendentes": [e.get("job_remoto") for e in pend]}], 0,
                        job_remoto=pend[-1].get("job_remoto"),
                        motivo="job pago anterior sem resposta e sem recuperação automática — confira no provedor e registre "
                               "`provedores.py resolver --job … --cena … --remoto … --resultado falhou_no_provedor|recuperado`")
    fila, rejeitados = candidatos(t, catalogo, adaptadores, credencial)
    historia, aguardando = [], []
    rt = regras.get("routing", {}).get("retry", {})
    max_t = int(rt.get("max_attempts_per_provider", 2))
    t0_job = time.time()
    for p, estimativa in fila:
        usa_promo = bool(estimativa) and t["_api_router"].get("allow_promo_credits", True) and promo_cobre(p, estimativa, t)
        aut = autorizar(t, p, 0.0 if usa_promo else estimativa, regras)
        if not aut["ok"]:
            historia.append({"provedor": p["id"], "resultado": aut["estado"], "motivo": aut["motivo"]})
            registrar({"tipo": "bloqueio", "job_id": t["job_id"], "provedor": p["id"], "estado": aut["estado"], "motivo": aut["motivo"]})
            if aut["estado"] == "waiting_approval":
                aguardando.append(aut["motivo"])
            continue
        ad = adaptadores[p["adaptador"]](p)
        for n in range(max_t):
            tid = uuid.uuid4().hex[:12]
            ini = time.time()
            base = {"tipo": "tentativa", "id": tid, "job_id": t["job_id"], "scene_id": t.get("scene_id"), "task_type": t["task_type"],
                    "provedor": p["id"], "modelo": p.get("model"), "tier": p.get("tier"), "estimado_usd": estimativa,
                    "chave": chave, "reserva_id": aut.get("reserva_id"), "saida_prevista": t["requirements"].get("saida"),
                    "tentativa_n": n + 1, "duracao_s": t["requirements"].get("duration_s"), "resolucao": t["requirements"].get("resolucao"),
                    "tipo_take": t["requirements"].get("tipo_take"), "nivel": ["gratis", "credito_promocional", "pago"][nivel(p, estimativa, t)],
                    "creditos_usados": None}
            try:
                r = ad.executar(t, tid)
            except ErroProvedor as e:
                lat = int((time.time() - ini) * 1000)
                registrar(dict(base, resultado="erro", erro_tipo=e.tipo, erro=limpo(e), latencia_ms=lat, job_remoto=e.job_remoto))
                historia.append({"provedor": p["id"], "resultado": "erro", "erro_tipo": e.tipo, "motivo": limpo(e)[:160]})
                if e.tipo == "timeout_ambiguo":
                    reconciliar(aut.get("reserva_id"))  # pode ter sido cobrado: o reservado conta como gasto
                    if p.get("tier") != "free" or estimativa:  # nunca dispara outro job pago com o primeiro talvez rodando
                        return resposta(t, "pendente_verificacao", p, historia, n + 1, job_remoto=e.job_remoto,
                                        motivo="timeout ambíguo — confira/recupere o job remoto antes de gerar de novo")
                    break
                if e.tipo in ("taxa", "transitorio") and n + 1 < max_t:
                    if e.retry_after and rt.get("respect_retry_after", True):
                        espera = e.retry_after
                    else:
                        espera = min(float(rt.get("backoff_max_s", 30)), float(rt.get("backoff_base_s", 2)) * 2 ** n) * (0.5 + random.random())
                    dormir(espera)
                    continue
                if e.tipo in ("taxa", "transitorio"):
                    falha_saude(p, regras, e)
                if e.tipo in ("cota", "saldo", "credencial"):
                    marcar(p, e.tipo, e)
                nao_cobrado = e.cobrado is False or e.tipo in ("credencial", "payload", "saldo", "cota", "licenca")
                reconciliar(aut.get("reserva_id"), liberar=nao_cobrado)
                break
            lat = int((time.time() - ini) * 1000)
            if usa_promo:
                base["creditos_usados"] = promo_consumir(p, t, estimativa)

                def _livro(d, qtd=base["creditos_usados"]):  # rastro no livro: crédito usado, dinheiro 0
                    d.setdefault("reservas", []).append({"id": uuid.uuid4().hex[:12], "job_id": t["job_id"], "scene_id": t.get("scene_id"),
                                                         "provedor": p["id"], "valor": 0.0, "estimado": estimativa, "estado": "reconciliada",
                                                         "real": 0.0, "custo_confirmado": True, "quando": iso(agora()),
                                                         "categoria": "credito_promocional", "creditos": qtd})
                ig.atualizar_json(caminhos()["reservas"], _livro, padrao={"reservas": []})
            sucesso_saude(p)
            reconciliar(aut.get("reserva_id"), real=r.get("custo_real"))
            q = inspecionar(r["saida"], t)
            registrar(dict(base, resultado="sucesso" if q["aceito"] else "reprovado_qualidade", latencia_ms=lat, saida=r["saida"],
                           sha_saida=ig.sha256(r["saida"]) if os.path.isfile(r["saida"]) else None,
                           real_usd=r.get("custo_real"), qa=q["estado"], qa_motivo=q["motivo"], job_remoto=r.get("job_remoto"),
                           model_air=r.get("model_air"), input_hash=r.get("input_hash"), cache=r.get("cache"),
                           politica=t["routing_policy"]))
            if not q["aceito"]:
                historia.append({"provedor": p["id"], "resultado": "reprovado_qualidade", "motivo": q["motivo"]})
                break  # escala para o próximo candidato (o custo desta tentativa já ficou registrado)
            travar_consistencia(t, p)
            ok = resposta(t, "success", p, historia, n + 1, saida=r["saida"], estimado=estimativa, real=r.get("custo_real"),
                          qa=q["estado"], uso=r.get("uso"), latencia=int((time.time() - t0_job) * 1000), job_remoto=r.get("job_remoto"))
            # motivo do roteamento rastreável (INTEGRACAO-RUNWARE.md): política, modelo exato e quem ficou de fora e por quê
            ok.update(routing_policy=t["routing_policy"], model_air=r.get("model_air") or p.get("model"), input_hash=r.get("input_hash"),
                      cache=r.get("cache"), rejeitados=rejeitados)
            return ok
    if aguardando:
        pendente_aprovacao(t, aguardando)
        return resposta(t, "waiting_approval", None, historia + [{"rejeitados": rejeitados}], 0, motivo="; ".join(aguardando))
    return resposta(t, "sem_provedor", None, historia + [{"rejeitados": rejeitados}], 0, motivo="sem opção compatível, disponível e autorizada")


def recuperar_pendentes(t, pend, adaptadores, catalogo):
    """Tenta recuperar (baixar sem pagar de novo) cada job pago pendente. O adaptador precisa ter `recuperar(t, evento)`;
    sem isso, nada é reenviado — o job continua pendente até alguém conferir no provedor."""
    por_id = {p["id"]: p for p in catalogo["provedores"]}
    for e in pend:
        p = por_id.get(e.get("provedor"))
        cls = p and adaptadores.get(p.get("adaptador"))
        if not cls or not hasattr(cls, "recuperar"):
            continue
        try:
            r = cls(p).recuperar(t, e)
        except ErroProvedor as erro:
            registrar({"tipo": "recuperacao", "job_id": t["job_id"], "scene_id": t.get("scene_id"), "job_remoto": e.get("job_remoto"),
                       "resultado": "falhou_no_provedor" if erro.tipo in ("permanente", "payload") else "ainda_pendente", "erro": limpo(erro)})
            continue
        if r and r.get("saida") and ig.midia_valida(r["saida"], {"tts": "audio", "imagem": "imagem"}.get(t["task_type"], "video"))[0]:
            registrar({"tipo": "recuperacao", "job_id": t["job_id"], "scene_id": t.get("scene_id"), "job_remoto": e.get("job_remoto"),
                       "resultado": "recuperado", "saida": r["saida"], "sha_saida": ig.sha256(r["saida"])})
            return dict(resposta(t, "success", p, [{"recuperado": e.get("job_remoto")}], 0, saida=r["saida"], estimado=e.get("estimado_usd"),
                                 real=r.get("custo_real"), job_remoto=e.get("job_remoto")), recuperado=True)
    return None


def resolver_pendente(job_id, scene_id, job_remoto, resultado, nota=""):
    """Registro manual (depois de conferir no painel do provedor) de que um job pendente foi recuperado/falhou/descartado."""
    registrar({"tipo": "recuperacao", "job_id": job_id, "scene_id": scene_id, "job_remoto": job_remoto, "resultado": resultado,
               "nota": nota, "manual": True})


def resposta(t, status, p, historia, tentativas, saida=None, estimado=None, real=None, qa=None, uso=None, latencia=None,
             job_remoto=None, motivo=None):
    tier = (p or {}).get("tier") if p else None
    if tier == "free" and estimado != 0:
        tier = "unknown"  # "free" só com evidência de preço 0
    return {"status": status, "job_id": t["job_id"], "scene_id": t.get("scene_id"), "provider": (p or {}).get("id"),
            "model": (p or {}).get("model"), "tier_used": tier, "output_ref": saida, "estimated_cost_usd": estimado,
            "actual_cost_usd": real, "usage": uso, "attempt_count": tentativas, "latency_ms": latencia, "quality_status": qa,
            "fallback_history": historia, "job_remoto": job_remoto, "motivo": motivo,
            "pricing_source_checked_at": ((p or {}).get("price") or {}).get("last_verified_at")}


# ---------------------------------------------------------------- adaptadores reais
class Adaptador:
    def __init__(self, p):
        self.p = p

    def saida(self, t):
        s = t["requirements"].get("saida")
        if not s:
            raise ErroProvedor("payload", "tarefa sem requirements.saida", cobrado=False)
        os.makedirs(os.path.dirname(os.path.abspath(s)) or ".", exist_ok=True)
        return s

    def rodar(self, cmd, timeout=1200):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired as e:
            raise ErroProvedor("timeout_ambiguo", f"processo passou de {timeout}s") from e
        return r.returncode, (r.stdout or "") + (r.stderr or "")


class GeminiTTS(Adaptador):
    """tts_gemini SEM a troca silenciosa para o Lite (o roteador decide; trocar a voz exige aprovação)."""

    def executar(self, t, tid):
        import urllib.error

        import tts_gemini as tg
        req = t["requirements"]
        saida = self.saida(t)
        voz = req["voice_profile_id"].split(":", 1)[1]
        estilo, tom = req.get("estilo", ""), req.get("tom")
        if tom and tom in tg.TONS:
            estilo = f"{tg.TONS[tom][1]}, {estilo}" if estilo else tg.TONS[tom][1]
        try:
            tg._sintetizar_tentando(req["texto"], voz, estilo, saida, self.p["model"], 3)
        except tg.CotaEsgotada as e:
            raise (classificar_texto(str(e)) if "spend" in str(e).lower() else ErroProvedor("cota", str(e))) from e
        except urllib.error.HTTPError as e:
            raise classificar_texto(e.read().decode(errors="replace"), e.code) from e
        except urllib.error.URLError as e:
            raise ErroProvedor("transitorio", str(e.reason)) from e
        except SystemExit as e:  # o texto não saiu completo nas 3 tentativas: qualidade, não cota
            raise ErroProvedor("permanente", f"TTS não reproduziu o texto: {e}", cobrado=True) from e
        return {"saida": saida, "custo_real": None, "uso": {"unit": "call", "quantity": 1}}


class VoiceStudio(Adaptador):
    URL = "http://localhost:3900"

    def executar(self, t, tid):
        import urllib.error
        import urllib.request
        req = t["requirements"]
        saida = self.saida(t)
        corpo = json.dumps({"text": req["texto"], "language": "Portuguese (Brazil)",
                            "profile_id": req["voice_profile_id"].split(":", 1)[1]}).encode()
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.URL + "/generate", data=corpo,
                                                              headers={"Content-Type": "application/json"}), timeout=900)
            tipo, dados = r.headers.get("Content-Type", ""), r.read()
        except urllib.error.URLError as e:
            raise ErroProvedor("transitorio", f"VoiceStudio fora do ar ({e.reason}) — abra o app", cobrado=False) from e
        if "audio" in tipo:
            open(saida, "wb").write(dados)
        else:
            d = json.loads(dados or b"{}")
            src = d.get("path") or d.get("audio_path") or d.get("file")
            if not src or not os.path.isfile(src):
                raise ErroProvedor("permanente", f"VoiceStudio respondeu sem áudio reconhecível ({list(d)[:6]})", cobrado=False)
            shutil.copy(src, saida)
        return {"saida": saida, "custo_real": 0.0, "uso": {"unit": "call", "quantity": 1}}


def _prompt(req):
    if req.get("prompt"):
        return req["prompt"]
    if req.get("direcao"):
        from contrato import prompt_atuacao
        return prompt_atuacao({"direcao": req["direcao"]})
    return ""


class HFWan(Adaptador):
    """Space Wan 2.2 I2V (grátis, cota ZeroGPU). Com HF_TOKEN usa a cota da conta."""

    def executar(self, t, tid):
        req = t["requirements"]
        saida = self.saida(t)
        img = req.get("imagem")
        if not img or not os.path.isfile(img):
            raise ErroProvedor("payload", "vídeo i2v sem imagem-chave (requirements.imagem)", cobrado=False)
        prompt = _prompt(req)
        dur = max(2.0, min(5.0, float(req.get("duration_s") or 3) + 0.4))
        try:
            import httpx
            from gradio_client import Client, handle_file
            c = Client(self.p["space"], verbose=False, token=os.environ.get("HF_TOKEN") or None,
                       httpx_kwargs={"timeout": httpx.Timeout(600.0)})
            vid, seed = c.predict(handle_file(img), prompt, 6, "static, frozen, still image, blurry, deformed hands, extra fingers, text",
                                  dur, 1, 1, 42, True, api_name="/generate_video")
        except ErroProvedor:
            raise
        except Exception as e:  # noqa: BLE001 — gradio levanta AppError/httpx/etc.: classificar pela mensagem
            raise classificar_texto(str(e)) from e
        shutil.copy(vid["video"] if isinstance(vid, dict) else vid, saida)
        json.dump({"modelo": self.p["model"], "space": self.p["space"], "prompt": prompt, "seed": seed, "custo_estimado": 0, "tentativa": tid},
                  open(saida + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return {"saida": saida, "custo_real": 0.0, "uso": {"unit": "clip", "quantity": 1}}


class HFS2V(Adaptador):
    def executar(self, t, tid):
        req = t["requirements"]
        saida = self.saida(t)
        for k in ("imagem", "audio"):
            if not req.get(k) or not os.path.isfile(req[k]):
                raise ErroProvedor("payload", f"lip-sync sem {k}", cobrado=False)
        try:
            import httpx
            from gradio_client import Client, handle_file
            c = Client(self.p["space"], verbose=False, token=os.environ.get("HF_TOKEN") or None,
                       httpx_kwargs={"timeout": httpx.Timeout(900.0)})
            r = c.predict(handle_file(req["imagem"]), handle_file(req["audio"]), "480P", api_name="/predict")
        except Exception as e:  # noqa: BLE001
            raise classificar_texto(str(e)) from e
        shutil.copy(r["video"] if isinstance(r, dict) else r, saida)
        return {"saida": saida, "custo_real": 0.0, "uso": {"unit": "clip", "quantity": 1}}


def _erro_cli(texto, arquivo_json=None):
    m = texto or ""
    cod = re.search(r"fal\.ai (\d{3})", m)
    if "tempo esgotado" in m.lower():
        jr = (ler(arquivo_json, {}) or {}).get("request_id") if arquivo_json else None
        return ErroProvedor("timeout_ambiguo", m[-300:], job_remoto=jr)
    if "preço desconhecido" in m.lower() or "recusado (nada foi gasto)" in m.lower():
        return ErroProvedor("permanente", m[-300:], cobrado=False)
    return classificar_texto(m[-400:], int(cod.group(1)) if cod else None)


class FalClipe(Adaptador):
    def executar(self, t, tid):
        req = t["requirements"]
        saida = self.saida(t)
        img = req.get("imagem")
        if not img or not os.path.isfile(img):
            raise ErroProvedor("payload", "vídeo i2v sem imagem-chave", cobrado=False)
        d = float(req.get("duration_s") or 5)
        ok = [x for x in self.p.get("duracoes") or [5] if x >= d - 1e-6]
        if not ok:
            raise ErroProvedor("payload", f"{d}s não cabe no modelo", cobrado=False)
        cmd = [sys.executable, os.path.join(AQUI, "gerar_clipe_fal.py"), "--imagem", img, "--prompt", _prompt(req),
               "--modelo", self.p["model"], "--duracao", str(min(ok)), "-o", saida, "--confirmar"]
        if req.get("ultimo_quadro"):
            cmd += ["--ultimo-quadro", req["ultimo_quadro"]]
        cod, txt = self.rodar(cmd)
        if cod != 0 or not ig.midia_valida(saida, "video")[0]:
            raise _erro_cli(txt, saida + ".json")
        return {"saida": saida, "custo_real": None, "custo_base": "tabela oficial × duração (cobrança real não consultável)",
                "uso": {"unit": "second", "quantity": min(ok)}, "job_remoto": (ler(saida + ".json", {}) or {}).get("request_id")}


class FalLipsync(Adaptador):
    def executar(self, t, tid):
        req = t["requirements"]
        saida = self.saida(t)
        cmd = [sys.executable, os.path.join(AQUI, "lipsync.py"), self.p.get("rota", "avatar"), "--imagem", req.get("imagem", ""),
               "--audio", req.get("audio", ""), "--prompt", req.get("prompt", ""), "-o", saida, "--confirmar"]
        cod, txt = self.rodar(cmd)
        if cod != 0 or not ig.midia_valida(saida, "video")[0]:
            raise _erro_cli(txt, saida + ".json")
        return {"saida": saida, "custo_real": None, "uso": {"unit": "second", "quantity": req.get("duration_s")},
                "job_remoto": (ler(saida + ".json", {}) or {}).get("request_id")}


def _recuperar_fal(self, t, evento):
    """Recupera um job do fal que deu timeout: o pedido pago ficou salvo em <saida>.json (request_id/response_url);
    `gerar_clipe_fal.py --recuperar` baixa sem pagar de novo. Sem o .json, não há o que recuperar (fica pendente)."""
    saida = evento.get("saida_prevista") or t["requirements"].get("saida")
    if not saida or not os.path.isfile(saida + ".json"):
        return None
    cod, txt = self.rodar([sys.executable, os.path.join(AQUI, "gerar_clipe_fal.py"), "--recuperar", saida], timeout=600)
    if cod != 0:
        raise classificar_texto(txt[-300:]) if "terminou com" not in txt else ErroProvedor("permanente", txt[-300:])
    return {"saida": saida, "custo_real": None}


FalClipe.recuperar = _recuperar_fal
FalLipsync.recuperar = _recuperar_fal


class OpenAIImagem(Adaptador):
    def executar(self, t, tid):
        req = t["requirements"]
        saida = self.saida(t)
        cmd = [sys.executable, os.path.join(AQUI, "gerar_imagem.py"), req.get("prompt", ""), "-o", saida,
               "--formato", req.get("formato", "vertical"), "--qualidade", req.get("qualidade", "medium"), "--confirmar"]
        for r in req.get("refs") or []:
            cmd += ["--ref", r]
        cod, txt = self.rodar(cmd, timeout=600)
        if cod != 0 or not ig.midia_valida(saida, "imagem")[0]:
            raise classificar_texto(txt[-400:])
        return {"saida": saida, "custo_real": None, "uso": {"unit": "image", "quantity": 1}}


class _Runware(Adaptador):
    """Base dos adaptadores Runware (INTEGRACAO-RUNWARE.md): validação local, job persistido, polling, retomada sem
    reenvio, cache e custo real (`cost`). ErroRunware → ErroProvedor com o mesmo tipo (o roteador decide fallback)."""
    cliente = None  # os testes injetam um runware.Cliente com transporte falso

    def _cli(self):
        import runware
        return self.cliente or runware.Cliente()

    def _duracao(self, d):
        """Duração do contrato → a menor que o modelo aceita (enum) ou inteiro dentro da faixa — nunca encurta o plano."""
        import runware
        regra = (runware.MODELOS.get(self.p["model"]) or {}).get("duracao") or {}
        if "enum" in regra:
            ok = [x for x in regra["enum"] if x >= float(d) - 1e-6]
            if not ok:
                raise ErroProvedor("payload", f"{d}s não cabe no modelo {self.p['model']}", cobrado=False)
            return min(ok)
        if "min" in regra:
            import math
            v = max(regra["min"], math.ceil(float(d) - 1e-6))
            if v > regra["max"]:
                raise ErroProvedor("payload", f"{d}s passa do máximo {regra['max']}s de {self.p['model']}", cobrado=False)
            return v
        return d

    def _rodar(self, t, req):
        import runware
        try:
            r = self._cli().gerar(req)
        except runware.ErroRunware as e:
            raise ErroProvedor(e.tipo, str(e), cobrado=e.cobrado, job_remoto=e.job_remoto) from None
        return {"saida": r.local_path, "custo_real": r.cost_usd, "job_remoto": r.task_uuid, "model_air": r.model_air,
                "input_hash": r.input_hash, "cache": r.cache,
                "uso": {"unit": "second" if req.kind != "image" else "image", "quantity": req.duration_seconds or 1}}

    def _pedido(self, t, kind, mode, **k):
        import runware
        req = t["requirements"]
        return runware.GenerationRequest(project_id=t["job_id"], shot_id=t.get("scene_id") or "", kind=kind, mode=mode,
                                         positive_prompt=_prompt(req), model_air=self.p["model"], saida=self.saida(t),
                                         constraints={"identidade": req.get("identidade")}, **k)


class RunwareVideo(_Runware):
    def executar(self, t, tid):
        req = t["requirements"]
        img = req.get("imagem")
        if not img or not os.path.isfile(img):
            raise ErroProvedor("payload", "vídeo i2v sem imagem-chave", cobrado=False)
        return self._rodar(t, self._pedido(t, "video", "image_to_video", duration_seconds=self._duracao(req.get("duration_s") or 5),
                                           first_frame_path=img, last_frame_path=req.get("ultimo_quadro")))


class RunwareLipsync(_Runware):
    def executar(self, t, tid):
        req = t["requirements"]
        return self._rodar(t, self._pedido(t, "lipsync", "image_audio_to_video", first_frame_path=req.get("imagem"),
                                           audio_path=req.get("audio"), duration_seconds=req.get("duration_s")))


class RunwareImagem(_Runware):
    def executar(self, t, tid):
        req = t["requirements"]
        w, h = {"horizontal": (1536, 1024), "vertical": (1024, 1536), "quadrado": (1024, 1024)}.get(req.get("formato", "horizontal"), (1536, 1024))
        return self._rodar(t, self._pedido(t, "image", "text_to_image", width=w, height=h, reference_paths=list(req.get("refs") or [])))


ADAPTADORES = {c.__name__: c for c in (GeminiTTS, VoiceStudio, HFWan, HFS2V, FalClipe, FalLipsync, OpenAIImagem,
                                       RunwareVideo, RunwareLipsync, RunwareImagem)}


# ---------------------------------------------------------------- CLI
try:  # provedores de vídeo padronizados (Spaces Gradio, Alibaba, LTX) — provedores_video.py
    import provedores_video as _pvv
    _pvv.registrar(ADAPTADORES)
except Exception:  # noqa: BLE001 — sem o módulo, o roteador segue com os adaptadores antigos
    pass


def planejar(tarefa):
    catalogo, regras = config()
    t = normalizar(tarefa, regras)
    fila, rejeitados = candidatos(t, catalogo, ADAPTADORES)
    print(f"Tarefa {t['job_id']} · {t['task_type']} · política {t['routing_policy']} · qualidade ≥ {t['quality_min']} · "
          f"comercial {'sim' if t['commercial_use'] else 'não'}")
    for i, (p, e) in enumerate(fila, 1):
        aut = autorizar(t, p, e, regras, reservar=False)
        custo = "US$ 0 (grátis)" if e == 0 else ("preço desconhecido" if e is None else f"≈ US$ {e:.2f}")
        nota = f"nota {pontuar(p, e, t):.2f} " if t["routing_policy"] == "pontuacao" else ""
        print(f"  {i}. {p['id']:22} {p.get('tier', ''):7} {p.get('quality', ''):8} {custo:20} {nota}→ "
              f"{'pode rodar' if aut['ok'] else aut['estado'] + ': ' + aut['motivo']}")
    for r in rejeitados:
        print(f"  ✗ {r['provedor']:22} {r['motivo']}")


def status():
    catalogo, regras = config()
    est = ler(caminhos()["estado"], {})
    b = regras.get("budget", {})
    print(f"roteador {'ATIVO' if regras.get('ativo', True) else 'DESLIGADO (rollback)'} · política {regras.get('routing', {}).get('policy')} · "
          f"teto por vídeo US$ {b.get('max_cost_per_video')} · por operação US$ {b.get('max_cost_per_operation')} · "
          f"custo desconhecido: {b.get('default_unknown_cost_policy')}")
    for p in catalogo["provedores"]:
        cred = p.get("credencial_env")
        tem = ("sim" if os.environ.get(cred) else ("opcional, não definida" if p.get("credencial_opcional") else "NÃO")) if cred else "—"
        ok, m = disponibilidade(p, est) if p.get("enabled") else (False, p.get("motivo_desabilitado", "desabilitado"))
        if estado_de(p["id"], est).get("credencial_invalida"):
            ok, m = False, "credencial recusada"
        q = p.get("quota") or {}
        cota = "desconhecida"
        if q.get("detection") == "local_counter" and q.get("limit"):
            dono = q.get("compartilha_cota_com") or p["id"]
            cota = f"{(estado_de(dono, est).get('cota') or {}).get(periodo(q.get('period')), 0)}/{q['limit']} hoje"
        elif q.get("detection") == "local":
            cota = "local"
        preco = (p.get("price") or {}).get("amount_per_unit")
        print(f"  {'✅' if ok else '⛔'} {p['id']:22} {p.get('stage', ''):8} {p.get('tier', ''):7} q:{p.get('quality', ''):8} "
              f"comercial:{p.get('commercial_use', ''):8} credencial:{tem:22} cota:{cota:14} preço:{'?' if preco is None else preco}"
              f"{'' if ok else '  · ' + m}")


def relatorio(job):
    rs = [r for r in ler(caminhos()["reservas"], {"reservas": []})["reservas"] if r["job_id"] == job]
    arq = caminhos()["log"]
    tent = [json.loads(x) for x in open(arq, encoding="utf-8")] if os.path.exists(arq) else []
    tent = [x for x in tent if x.get("job_id") == job]
    print(f"Vídeo/job: {job}")
    for x in tent:
        if x.get("tipo") == "tentativa":
            custo = "US$ 0,00 (grátis)" if x.get("estimado_usd") == 0 else (
                f"estimado US$ {x['estimado_usd']:.2f}" if x.get("estimado_usd") is not None else "custo DESCONHECIDO")
            print(f"  - {x.get('scene_id') or ''} {x['task_type']}: {x['provedor']} · {x['resultado']}"
                  f"{' (' + x['erro_tipo'] + ')' if x.get('erro_tipo') else ''} · {custo}")
        elif x.get("tipo") == "bloqueio":
            print(f"  - bloqueado {x['provedor']}: {x['estado']} — {x['motivo'][:100]}")
    prev = sum(r["valor"] for r in rs if r["estado"] != "liberada")
    conf = sum(r["real"] for r in rs if r.get("custo_confirmado") and r.get("real") is not None)
    desc = [r for r in rs if r["estado"] == "reconciliada" and not r.get("custo_confirmado")]
    print(f"  Previsto/reservado (com margem): US$ {prev:.2f} · cobrado CONFIRMADO: US$ {conf:.2f} · {len(desc)} lançamento(s) com "
          "cobrança não confirmada (contados pelo valor reservado, nunca como zero)")
    gratis = sum(1 for x in tent if x.get("tipo") == "tentativa" and x.get("resultado") == "sucesso" and x.get("estimado_usd") == 0)
    print(f"  Execuções grátis com sucesso: {gratis}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("planejar"); s.add_argument("tarefa")
    s = sub.add_parser("executar"); s.add_argument("tarefa")
    s = sub.add_parser("aprovar"); s.add_argument("--job", required=True); s.add_argument("--ate", type=float)
    s.add_argument("--por-operacao", type=float); s.add_argument("--custo-desconhecido", type=float)
    s.add_argument("--troca-voz", action="store_true"); s.add_argument("--troca-estilo", action="store_true")
    s = sub.add_parser("relatorio"); s.add_argument("--job", required=True)
    s = sub.add_parser("resetar"); s.add_argument("provedor")
    s = sub.add_parser("resolver"); s.add_argument("--job", required=True); s.add_argument("--cena", required=True)
    s.add_argument("--remoto", required=True); s.add_argument("--resultado", required=True, choices=["recuperado", "falhou_no_provedor", "descartado"])
    s.add_argument("--nota", default="")
    s = sub.add_parser("pendentes"); s.add_argument("--job", required=True); s.add_argument("--cena")
    a = ap.parse_args()
    _, regras = config()
    if a.cmd == "executar" and not regras.get("ativo", True):
        sys.exit("roteador desligado (config/roteamento.json ativo=false) — use os scripts diretamente")
    if a.cmd == "status":
        status()
    elif a.cmd == "planejar":
        planejar(json.load(io.open(a.tarefa, encoding="utf-8")))
    elif a.cmd == "executar":
        r = executar(json.load(io.open(a.tarefa, encoding="utf-8")))
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        sys.exit(0 if r["status"] == "success" else 4 if r["status"] == "waiting_approval" else 2)
    elif a.cmd == "aprovar":
        def f(d):
            j = d.setdefault(a.job, {})
            for k, v in (("ate", a.ate), ("max_por_operacao", a.por_operacao), ("custo_desconhecido_ate", a.custo_desconhecido)):
                if v is not None:
                    j[k] = v
            if a.troca_voz:
                j["troca_voz"] = True
            if a.troca_estilo:
                j["troca_estilo"] = True
            j["quando"] = iso(agora())
        ig.atualizar_json(caminhos()["aprovacoes"], f)
        print(f"aprovação registrada para {a.job}: {aprovacao(a.job)}")
    elif a.cmd == "relatorio":
        relatorio(a.job)
    elif a.cmd == "resetar":
        mexer_estado(a.provedor, lambda e: [e.pop(k, None) for k in ("credencial_invalida", "aberto_ate", "falhas_seguidas",
                                                                      "sem_saldo_ate", "sem_saldo_desde", "esgotado_ate")])
        print(f"{a.provedor}: estado limpo")
    elif a.cmd == "resolver":
        resolver_pendente(a.job, a.cena, a.remoto, a.resultado, a.nota)
        print(f"{a.cena}: job {a.remoto} marcado como {a.resultado}")
    elif a.cmd == "pendentes":
        cenas = [a.cena] if a.cena else sorted({e.get("scene_id") for e in eventos(lambda e: e.get("job_id") == a.job)} - {None})
        for c in cenas:
            for e in jobs_pendentes(a.job, c):
                print(f"{c}: {e.get('provedor')} job_remoto={e.get('job_remoto')} desde {e.get('quando')} (reserva {e.get('reserva_id')})")


if __name__ == "__main__":
    main()
