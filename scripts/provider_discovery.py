"""Descoberta e validação dos provedores de vídeo — consulta REAL, sem gerar nada e sem custo.

Para cada provedor do catálogo (config/provedores.json, etapas video/lipsync):
  Spaces Hugging Face (adaptador GradioSpace/HFWan/HFS2V): huggingface.co/api/spaces/<id> (estado RUNNING/SLEEPING/…,
     hardware zero-a10g = cota ZeroGPU, licença declarada) + gradio_client.view_api (endpoint e parâmetros) + limites dos
     sliders da config (duração/resolução). Endpoint do catálogo ausente na API → não confirmado (o Space mudou).
  APIs pagas (fal, Runware, Alibaba, LTX): credencial presente? preço no catálogo com fonte e data? (a disponibilidade real
     de uma API paga só se confirma numa chamada paga — não fazemos isso aqui).
Categorias (nunca "grátis" sem evidência):
  gratis_api           API pública que não cobra (ZeroGPU: tem cota por conta/IP; esgotou → cota)
  gratis_web           só a interface web é grátis (sem endpoint de API) — NÃO automatizamos a interface
  credito_promocional  crédito/franquia válida registrada no catálogo (`creditos_promocionais` com saldo e validade)
  pago_api             API paga com preço confirmado e credencial presente
  sem_credencial       API paga sem a chave no ambiente (fica de fora)
  indisponivel         Space parado/erro, endpoint fora do ar
  nao_confirmado       preço, endpoint ou estado sem evidência suficiente
Licença comercial: só "allowed" com evidência; Space sem licença declarada = "unknown".

Uso:
  python provider_discovery.py [--sem-rede] [--provedores a,b]   → memoria/provedores-descoberta.json + tabela
O roteador lê esse arquivo: provedor `indisponivel` verificado há menos de 6 h fica de fora (sem gastar tentativa).
"""
import argparse
import datetime
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402
try:
    import chaves as _chaves  # .env / registro do Windows → os.environ (sem sobrescrever)
    _chaves.carregar()
except ImportError:
    pass

ARQ = os.path.join(SKILL, "memoria", "provedores-descoberta.json")
VALIDADE_H = 6
CATEGORIAS = ("gratis_api", "gratis_web", "credito_promocional", "pago_api", "sem_credencial", "indisponivel", "nao_confirmado")
# Avaliados e NÃO integrados (com o motivo) — consulta de 2026-11-07
NAO_INTEGRADOS = {
    "numanajmal0/wan-video-api": "Space de autor sem histórico; os modelos expostos são variantes 'nsfw-*' e só texto→vídeo — impróprio para "
                                 "conteúdo de marca e sem garantia de licença",
    "alibaba:wan2.2-i2v-plus": "preço não encontrado nas páginas oficiais em 2026-11-07 → catalogado com preço null (bloqueia gasto)",
    "alibaba:franquia-gratis": "a franquia grátis de wan2.2-i2v-flash/plus para usuários novos foi removida em 2026-10-29 (página 'Free quota "
                               "for new users'); quem já tinha mantém até expirar — só entra se o usuário informar o saldo",
    "alibaba:wan2.1-turbo": "id exato e preço não confirmados nas páginas oficiais consultadas — não catalogado",
}


def agora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "criador-video-discovery"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def hf_space(space, get=_get_json):
    """Metadados públicos do Space (sem token, sem acordar GPU)."""
    t0 = time.time()
    try:
        d = get(f"https://huggingface.co/api/spaces/{space}")
    except urllib.error.HTTPError as e:
        return {"estado": "NAO_ENCONTRADO" if e.code == 404 else f"HTTP_{e.code}", "erro": str(e)[:120]}
    except Exception as e:  # noqa: BLE001 — sem rede, DNS, timeout
        return {"estado": "SEM_REDE", "erro": str(e)[:120]}
    r = d.get("runtime") or {}
    return {"estado": r.get("stage") or "DESCONHECIDO", "hardware": (r.get("hardware") or {}).get("current"),
            "licenca": (d.get("cardData") or {}).get("license"), "desativado": bool(d.get("disabled")), "privado": bool(d.get("private")),
            "atualizado": (d.get("lastModified") or "")[:10], "latencia_ms": int((time.time() - t0) * 1000)}


def hf_api(space, cliente=None):
    """{"endpoints": {nome: [parametros]}, "limites": {rotulo: [min, max]}} via gradio_client (só lê a configuração)."""
    try:
        if cliente is None:
            from gradio_client import Client
            cliente = Client(space, verbose=False, token=os.environ.get("HF_TOKEN") or None)
        api = cliente.view_api(return_format="dict", print_info=False)
        eps = {n: [p.get("parameter_name") or p.get("label") for p in ep.get("parameters", [])]
               for n, ep in (api.get("named_endpoints") or {}).items()}
        lim = {}
        for co in (getattr(cliente, "config", None) or {}).get("components", []):
            pr = co.get("props", {})
            if co.get("type") in ("slider", "number") and pr.get("label") and re.search(r"dura|height|width|altura|largura", str(pr["label"]), re.I):
                lim[str(pr["label"])[:40]] = [pr.get("minimum"), pr.get("maximum")]
        return {"endpoints": eps, "limites": lim}
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)[:160]}


def promo_valida(p, ref=None):
    c = p.get("creditos_promocionais") or {}
    ref = ref or datetime.date.today().isoformat()
    return bool(c) and float(c.get("saldo") or 0) > 0 and (not c.get("valido_ate") or c["valido_ate"] >= ref)


def classificar(p, tem_credencial=None, get=_get_json, cliente_de=None, rede=True):
    """Ficha de descoberta de UM provedor do catálogo."""
    tem_credencial = tem_credencial or (lambda env: bool(os.environ.get(env)))
    f = {"id": p["id"], "adaptador": p.get("adaptador"), "modelo": p.get("model"), "stage": p.get("stage"),
         "licenca_comercial": p.get("commercial_use", "unknown"), "capacidades": p.get("capabilities"),
         "duracao": p.get("faixa_duracao") or p.get("duracoes"), "quando": agora()}
    if not p.get("enabled"):
        return dict(f, categoria="indisponivel", motivo=f"desabilitado no catálogo ({p.get('motivo_desabilitado', '—')})")
    if p.get("space"):
        if not rede:
            return dict(f, categoria="nao_confirmado", motivo="sem rede nesta verificação")
        info = hf_space(p["space"], get)
        f.update(space=p["space"], estado=info["estado"], hardware=info.get("hardware"), licenca_space=info.get("licenca"), latencia_ms=info.get("latencia_ms"))
        if info["estado"] != "RUNNING" or info.get("desativado"):
            cat = "nao_confirmado" if info["estado"] in ("SEM_REDE", "SLEEPING") else "indisponivel"
            return dict(f, categoria=cat, motivo=f"Space {info['estado']}" +
                        (" (acorda na 1ª chamada; a descoberta não acorda)" if info["estado"] == "SLEEPING" else ""))
        api = hf_api(p["space"], cliente_de(p) if cliente_de else None)
        if api.get("erro"):
            return dict(f, categoria="nao_confirmado", motivo=f"API não lida: {api['erro']}")
        f["endpoints"], f["limites"] = list(api["endpoints"]), api["limites"]
        if not api["endpoints"]:
            return dict(f, categoria="gratis_web", motivo="Space sem endpoint de API — só a interface web (não automatizamos)")
        alvo = (p.get("gradio") or {}).get("api_name") or {"HFWan": "/generate_video", "HFS2V": "/predict"}.get(p.get("adaptador"))
        if alvo and alvo not in api["endpoints"]:
            return dict(f, categoria="nao_confirmado", motivo=f"endpoint {alvo} não existe mais (há: {', '.join(api['endpoints'])[:120]})")
        faltam = [v for k, v in (p.get("gradio") or {}).items() if k in ("prompt", "imagem", "duracao", "ultimo_quadro", "negativo") and v
                  and alvo in api["endpoints"] and v not in api["endpoints"][alvo]]
        if faltam:
            return dict(f, categoria="nao_confirmado", motivo=f"parâmetros mudaram: {', '.join(faltam)}")
        gpu = "ZeroGPU (cota por conta/IP)" if str(info.get("hardware", "")).startswith("zero") else str(info.get("hardware"))
        if str(info.get("hardware") or "").startswith("cpu"):  # modelo de vídeo em CPU: a API responde, mas gerar é inviável
            return dict(f, categoria="nao_confirmado", motivo=f"Space RUNNING com API {alvo}, mas em {info.get('hardware')} (sem GPU) — geração inviável")
        return dict(f, categoria="gratis_api", motivo=f"Space RUNNING com API {alvo}; {gpu}")
    if promo_valida(p):
        return dict(f, categoria="credito_promocional", motivo=f"crédito registrado: {p['creditos_promocionais']}")
    env = p.get("credencial_env")
    if env and not p.get("credencial_opcional") and not tem_credencial(env):
        return dict(f, categoria="sem_credencial", motivo=f"{env} não definida")
    pr = p.get("price") or {}
    if pr.get("amount_per_unit") is None and not pr.get("por_resolucao"):
        return dict(f, categoria="nao_confirmado", motivo="preço desconhecido no catálogo (bloqueia gasto)")
    if pr.get("amount_per_unit") == 0 and p.get("tier") == "free":
        return dict(f, categoria="gratis_api", motivo=p.get("tier_evidencia") or "grátis com evidência no catálogo")
    return dict(f, categoria="pago_api", motivo=f"preço: {pr.get('fonte', '—')} ({pr.get('last_verified_at', '—')})")


def descobrir(catalogo=None, alvo=None, rede=True, get=_get_json, cliente_de=None, tem_credencial=None, gravar=True, arq=None):
    if catalogo is None:
        import provedores as pv
        catalogo, _ = pv.config()
    fichas = {}
    for p in catalogo["provedores"]:
        if p.get("stage") not in ("video", "lipsync") or (alvo and p["id"] not in alvo):
            continue
        fichas[p["id"]] = classificar(p, tem_credencial, get, cliente_de, rede)
    out = {"verificado_em": agora(), "provedores": fichas, "avaliados_nao_integrados": NAO_INTEGRADOS}
    if gravar:
        ig.gravar_json_atomico(arq or ARQ, out)
    return out


def ler(arq=None):
    try:
        return json.load(io.open(arq or ARQ, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def indisponivel_recente(pid, arq=None, horas=VALIDADE_H):
    """(True, motivo) se a última descoberta (< horas) marcou o provedor como indisponível."""
    f = (ler(arq).get("provedores") or {}).get(pid)
    if not f or f.get("categoria") != "indisponivel":
        return False, ""
    try:
        idade = datetime.datetime.now() - datetime.datetime.fromisoformat(f["quando"])
    except (KeyError, ValueError):
        return False, ""
    return idade.total_seconds() < horas * 3600, f.get("motivo", "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-rede", action="store_true")
    ap.add_argument("--provedores")
    a = ap.parse_args()
    out = descobrir(alvo=set(a.provedores.split(",")) if a.provedores else None, rede=not a.sem_rede)
    print(f"{'provedor':26} {'categoria':20} licença   motivo")
    for pid, f in out["provedores"].items():
        print(f"{pid:26} {f['categoria']:20} {str(f.get('licenca_comercial'))[:8]:9} {f.get('motivo', '')[:90]}")
    print("\nAvaliados e não integrados:")
    for k, v in NAO_INTEGRADOS.items():
        print(f"  - {k}: {v}")
    print(f"→ {ARQ}")


if __name__ == "__main__":
    main()
