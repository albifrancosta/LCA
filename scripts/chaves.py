"""Chaves de API do estúdio — um lugar só para ler, conferir e explicar.

Regras (valem para todos os scripts):
  - a chave NUNCA é pedida, mostrada nem registrada no chat ou em log; só se diz se ela existe/funciona;
  - ordem de leitura: variável de ambiente → arquivo .env → registro do Windows (HKCU\\Environment);
  - .env: `<pasta da skill>/.env` (ou o caminho em CRIADOR_VIDEO_ENV); nunca sobrescreve variável já definida;
  - chave ausente = mensagem padrão: o que ela libera, se é grátis ou paga, onde criar, como configurar
    e qual a alternativa grátis. Nada é enviado a nenhum serviço.

Uso:
  python chaves.py status            → check-up: o que já funciona, o que falta, grátis × pago (sem rede)
  python chaves.py status --testar   → também testa cada chave existente numa chamada GRÁTIS (lista de modelos etc.)
  python chaves.py status --json     → mesmo resultado em JSON (para o Claude ler)
  python configurar.py               → assistente no terminal para salvar as chaves no .env (digitação escondida)

Em código:
  import chaves
  chaves.carregar()                  # põe as chaves do .env/registro em os.environ (sem sobrescrever)
  k = chaves.obter("FAL_KEY")        # devolve a chave ou encerra com a mensagem padrão
  k = chaves.obter("FAL_KEY", obrigatoria=False)  # None se faltar
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# O que cada chave libera. custo: "gratis" | "gratis_com_limite" | "pago"
CHAVES = {
    "GEMINI_API_KEY": {
        "nome": "Google Gemini", "custo": "gratis_com_limite",
        "libera": "narração com IA (voz), análise dos vídeos (espectador/inspetor), roteiros por contrato",
        "criar": "https://aistudio.google.com/apikey",
        "preco": "tem cota grátis diária; acima dela cobra por uso (no plano grátis o Google pode usar os dados — evite material de cliente)",
        "sem_ela": "narração com a sua própria voz gravada ou voz local; revisão visual feita pelo Claude nas folhas de quadros",
        "teste": "gemini",
    },
    "FAL_KEY": {
        "nome": "fal.ai", "custo": "pago",
        "libera": "clipes animados por IA (Kling, Wan…), trilha por IA, lip-sync, motion control",
        "criar": "https://fal.ai/dashboard/keys",
        "preco": "pré-pago; ex.: clipe Kling 2.6 Pro de 5 s ≈ US$ 0,35 — a skill sempre mostra o custo e pede ok antes",
        "sem_ela": "animação em Remotion (zoom, parallax, motion graphics) ou clipes grátis pelo Hugging Face (Wan 2.2, poucos por dia)",
        "teste": None,  # não há chamada grátis que confirme a chave sem risco de gasto
    },
    "OPENAI_API_KEY": {
        "nome": "OpenAI (GPT Image)", "custo": "pago",
        "libera": "imagens geradas por IA (cenas, personagens, fundos)",
        "criar": "https://platform.openai.com/api-keys",
        "preco": "por imagem; ex.: 1024×1536 qualidade média ≈ US$ 0,05 — custo mostrado antes, só gera com --confirmar",
        "sem_ela": "você gera as imagens em outra ferramenta (a skill entrega os prompts prontos) ou usa vídeos grátis de banco",
        "teste": "openai",
    },
    "RUNWARE_API_KEY": {
        "nome": "Runware", "custo": "pago",
        "libera": "clipes animados e lip-sync (alternativa ao fal.ai)",
        "criar": "https://my.runware.ai/signup",
        "preco": "pré-pago por segundo de vídeo; custo mostrado antes",
        "sem_ela": "fal.ai ou as rotas grátis (Remotion / Hugging Face)",
        "teste": None,
    },
    "PIXABAY_API_KEY": {
        "nome": "Pixabay", "custo": "gratis",
        "libera": "busca de vídeos de banco grátis para uso comercial (sem crédito obrigatório)",
        "criar": "https://pixabay.com/api/docs/  (faça login: a chave aparece na própria página)",
        "preco": "grátis",
        "sem_ela": "baixe vídeos à mão em pixabay.com, pexels.com ou mixkit.co e coloque em assets/stock/",
        "teste": "pixabay",
    },
    "PEXELS_API_KEY": {
        "nome": "Pexels", "custo": "gratis",
        "libera": "busca de vídeos de banco grátis (soma com o Pixabay)",
        "criar": "https://www.pexels.com/api/  (a emissão de chaves novas pode estar pausada)",
        "preco": "grátis",
        "sem_ela": "Pixabay, ou download manual no site",
        "teste": "pexels",
    },
    "HF_TOKEN": {
        "nome": "Hugging Face", "custo": "gratis",
        "libera": "mais clipes grátis por dia nos Spaces (Wan 2.2, LTX) — sem token também funciona, com cota menor",
        "criar": "https://huggingface.co/settings/tokens  (token de leitura)",
        "preco": "grátis",
        "sem_ela": "funciona sem token, com menos clipes por dia",
        "teste": None,
    },
}
ROTULO = {"gratis": "grátis", "gratis_com_limite": "grátis com limite", "pago": "PAGO"}
_carregado = False


def caminho_env():
    return os.environ.get("CRIADOR_VIDEO_ENV") or os.path.join(SKILL_DIR, ".env")


def ler_env(caminho=None):
    """Lê NOME=valor de um .env (aceita aspas, comentários e 'export ')."""
    caminho = caminho or caminho_env()
    valores = {}
    if not os.path.exists(caminho):
        return valores
    with open(caminho, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.startswith("export "):
                linha = linha[7:]
            k, v = linha.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() and v:
                valores[k.strip()] = v
    return valores


def _registro_windows(nome):
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            return winreg.QueryValueEx(reg, nome)[0] or None
    except OSError:
        return None


def origem(nome):
    """'variável de ambiente' | 'arquivo .env' | 'registro do Windows' | None — sem revelar o valor."""
    marcada = os.environ.get(f"_CV_ORIGEM_{nome}")
    if marcada:
        return marcada
    if os.environ.get(nome):
        return "variável de ambiente"
    if ler_env().get(nome):
        return "arquivo .env"
    if _registro_windows(nome):
        return "registro do Windows"
    return None


def carregar(forcar=False):
    """Põe em os.environ as chaves do .env e do registro do Windows, sem sobrescrever o que já existe."""
    global _carregado
    if _carregado and not forcar:
        return
    env = ler_env()
    for nome in sorted(set(CHAVES) | set(env)):
        if os.environ.get(nome):
            continue
        v, fonte = env.get(nome), "arquivo .env"
        if not v:
            v, fonte = _registro_windows(nome), "registro do Windows"
        if v:
            os.environ[nome] = v
            os.environ[f"_CV_ORIGEM_{nome}"] = fonte
    _carregado = True


def mensagem_falta(nome, contexto=None):
    """Texto padrão quando falta uma chave — o que libera, custo, onde criar, como configurar, alternativa."""
    c = CHAVES.get(nome, {"nome": nome, "custo": "pago", "libera": "esta função", "criar": "", "preco": "", "sem_ela": ""})
    linhas = [f"Falta a chave {nome} ({c['nome']}, {ROTULO.get(c['custo'], c['custo'])})"
              + (f" — necessária para: {contexto}" if contexto else "") + ".",
              f"  Ela libera: {c['libera']}."]
    if c.get("preco"):
        linhas.append(f"  Custo: {c['preco']}.")
    if c.get("criar"):
        linhas.append(f"  Crie em: {c['criar']}")
    linhas.append(f"  Configure FORA do chat: rode `python \"{os.path.join(SKILL_DIR, 'scripts', 'configurar.py')}\"` no seu"
                  f" terminal, ou escreva {nome}=... no arquivo {caminho_env()} (modelo: .env.example).")
    linhas.append("  Nunca cole a chave na conversa: o que é digitado no chat fica no histórico.")
    if c.get("sem_ela"):
        linhas.append(f"  Sem ela: {c['sem_ela']}.")
    return "\n".join(linhas)


def obter(nome, obrigatoria=True, contexto=None):
    carregar()
    k = os.environ.get(nome)
    if not k and obrigatoria:
        sys.exit(mensagem_falta(nome, contexto))
    return k or None


# ---------------------------------------------------------------- testes grátis (sem gasto)
def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "criador-video", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def testar(nome, valor=None):
    """'ok' | 'recusada …' | 'erro …' | 'sem teste grátis …' | 'ausente' — nunca gasta crédito."""
    k = valor or os.environ.get(nome)
    tipo = CHAVES.get(nome, {}).get("teste")
    if not k:
        return "ausente"
    if not tipo:
        return "sem teste grátis (é confirmada no 1º uso, sempre com o custo mostrado antes)"
    try:
        if tipo == "gemini":
            _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", {"x-goog-api-key": k})
        elif tipo == "openai":
            _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {k}"})
        elif tipo == "pixabay":
            _get("https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": k, "q": "sky", "per_page": 3}))
        elif tipo == "pexels":
            _get("https://api.pexels.com/videos/search?query=sky&per_page=1", {"Authorization": k})
        return "ok"
    except urllib.error.HTTPError as e:
        return "recusada (chave inválida ou sem permissão)" if e.code in (400, 401, 403) else f"erro HTTP {e.code}"
    except Exception as e:  # rede, timeout
        return f"erro de rede ({type(e).__name__})"


def status(testar_rede=False):
    carregar()
    itens = []
    for nome, c in CHAVES.items():
        tem = bool(os.environ.get(nome))
        item = {"chave": nome, "servico": c["nome"], "custo": c["custo"], "libera": c["libera"], "configurada": tem,
                "origem": origem(nome) if tem else None, "criar": c["criar"], "sem_ela": c["sem_ela"]}
        if testar_rede and tem:
            item["teste"] = testar(nome)
        itens.append(item)
    return {"arquivo_env": caminho_env(), "env_existe": os.path.exists(caminho_env()), "chaves": itens,
            "sempre_gratis": ["motion graphics e montagem (Remotion)", "edição: cortes, silêncios, legendas e formatos (ffmpeg)",
                              "transcrição local (faster-whisper)", "trilha sintetizada", "roteiro e storyboards"]}


def imprimir(s):
    print("Check-up das chaves de API (os valores nunca são mostrados)\n")
    print("✅ Sempre grátis, sem chave: " + "; ".join(s["sempre_gratis"]) + ".\n")
    for i in s["chaves"]:
        if not i["configurada"]:
            marca = "⚪"
        elif "teste" in i and i["teste"] != "ok" and not i["teste"].startswith("sem teste"):
            marca = "⚠️"
        else:
            marca = "✅"
        linha = f"{marca} {i['servico']} ({ROTULO.get(i['custo'], i['custo'])}) — {i['libera']}"
        if i["configurada"]:
            linha += f"\n     configurada ({i['origem']})" + (f" · teste: {i['teste']}" if "teste" in i else "")
        else:
            linha += f"\n     falta {i['chave']} → crie em {i['criar']}\n     sem ela: {i['sem_ela']}"
        print(linha)
    print(f"\nArquivo de chaves: {s['arquivo_env']}" + ("" if s["env_existe"] else " (ainda não existe)"))
    print("Para configurar, rode no SEU terminal (fora do chat):  python \"" + os.path.join(SKILL_DIR, "scripts", "configurar.py") + "\"")


if __name__ == "__main__":
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Check-up das chaves de API (sem mostrar valores)")
    ap.add_argument("acao", nargs="?", default="status", choices=["status"])
    ap.add_argument("--testar", action="store_true", help="testa cada chave existente numa chamada grátis")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = status(a.testar)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        imprimir(s)
