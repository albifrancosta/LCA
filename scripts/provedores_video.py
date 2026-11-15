"""Provedores de vídeo com interface PADRONIZADA (VideoProvider) — Spaces Gradio (grátis com cota ZeroGPU), Alibaba Model
Studio (Wan) e LTX API. Plugados no roteador existente (provedores.py) como adaptadores: o orçamento, a reserva atômica,
o fallback, o disjuntor, o log e a inspeção continuam sendo os do roteador — aqui só mora "como falar com cada API".

Interface (síncrona — os scripts da skill são síncronos; `aio_*` dá a versão assíncrona via asyncio.to_thread):
  check_availability() → {"ok", "estado", "motivo"}     get_capabilities() → {"t2v", "i2v", "duracoes", "resolucoes", …}
  estimate_cost(req)  → US$ ou None (desconhecido)     generate_video(req) → {"job_id", …} (só ENVIA)
  get_status(job_id)  → {"estado": pendente|processando|concluido|falhou, "url"?, "erro"?}
  download_result(job_id, saida) → caminho
Antes de esperar um job pago, o pedido é gravado em <saida>.<provedor>.json (job_id) → retomada consulta em vez de reenviar.
Fontes (2026-11-07): docs.ltx.io (pricing, v2/image-to-video, get-job-status, input-formats); alibabacloud.com/help
(image-to-video-guide, wan2-2-i2v-flash); Spaces lidos com huggingface.co/api/spaces + gradio_client.view_api.
Nada aqui foi chamado com custo durante o desenvolvimento.
"""
import asyncio
import base64
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

import integridade as ig
try:
    import chaves as _chaves  # .env / registro do Windows → os.environ (sem sobrescrever)
    _chaves.carregar()
except ImportError:
    pass

PENDENTE, PROCESSANDO, CONCLUIDO, FALHOU = "pendente", "processando", "concluido", "falhou"


class ErroVideo(Exception):
    """tipo segue provedores.ErroProvedor: cota | taxa | transitorio | credencial | saldo | payload | timeout_ambiguo | permanente."""

    def __init__(self, tipo, msg, job=None, cobrado=None):
        super().__init__(msg)
        self.tipo, self.job, self.cobrado = tipo, job, cobrado


class VideoProvider:
    nome = "base"

    def __init__(self, p, transporte=None, dormir=time.sleep):
        self.p, self.dormir = p, dormir
        self.transporte = transporte or self._http  # testes injetam um transporte falso

    # ---- interface
    def check_availability(self):
        raise NotImplementedError

    def get_capabilities(self):
        cap = self.p.get("capabilities") or []
        return {"t2v": "t2v" in cap, "i2v": "i2v" in cap, "duracoes": self.p.get("duracoes"), "faixa_duracao": self.p.get("faixa_duracao"),
                "resolucoes": self.p.get("resolucoes"), "ultimo_quadro": "ultimo_quadro" in cap, "fila": self.p.get("fila", True)}

    def estimate_cost(self, req):
        pr = self.p.get("price") or {}
        res = req.get("resolucao") or self.p.get("resolucao_padrao")
        por_res = (pr.get("por_resolucao") or {}).get(res) if res else None
        v = por_res if por_res is not None else pr.get("amount_per_unit")
        if v is None:
            return None
        if v == 0:
            return 0.0
        return round(float(v) * float(req.get("duration_s") or 5), 4) if pr.get("unit") == "second" else float(v)

    def generate_video(self, req):
        raise NotImplementedError

    def get_status(self, job_id):
        raise NotImplementedError

    def download_result(self, job_id, saida, st=None):
        raise NotImplementedError

    # ---- assíncrono (o roteador usa o síncrono)
    async def aio_check_availability(self):
        return await asyncio.to_thread(self.check_availability)

    async def aio_generate_video(self, req):
        return await asyncio.to_thread(self.generate_video, req)

    async def aio_get_status(self, job_id):
        return await asyncio.to_thread(self.get_status, job_id)

    # ---- utilitários
    def _http(self, metodo, url, corpo=None, cabecalhos=None, timeout=45):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo, headers=dict({"Content-Type": "application/json"}, **(cabecalhos or {})))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except ValueError:
                return e.code, {}
        except (urllib.error.URLError, TimeoutError) as e:
            raise ErroVideo("transitorio", f"rede: {e}")

    def _erro_http(self, cod, corpo, job=None):
        msg = json.dumps(corpo, ensure_ascii=False)[:300]
        tipo = {401: "credencial", 403: "credencial", 402: "saldo", 429: "taxa", 400: "payload", 413: "payload", 422: "payload"}.get(cod)
        if cod and cod >= 500:
            tipo = "transitorio"
        m = msg.lower()
        if "arrearage" in m or "insufficient" in m:
            tipo = "saldo"
        elif "free tier" in m or "quota" in m:
            tipo = "cota"
        return ErroVideo(tipo or "permanente", f"HTTP {cod}: {msg}", job=job,
                         cobrado=False if tipo in ("credencial", "payload", "saldo", "cota") else None)

    def chave(self):
        env = self.p.get("credencial_env")
        v = os.environ.get(env or "")
        if env and not v:
            raise ErroVideo("credencial", f"{env} não definida", cobrado=False)
        return v

    def _baixar(self, url, saida, hosts):
        u = urllib.parse.urlparse(url)
        if u.scheme != "https" or not any(u.hostname == h or (u.hostname or "").endswith("." + h) for h in hosts):
            raise ErroVideo("permanente", f"URL de resultado fora dos domínios esperados ({u.hostname})")
        tmp = saida + ".parcial"
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
            lido = 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                lido += len(b)
                if lido > 500 << 20:
                    raise ErroVideo("permanente", "resultado maior que 500 MB")
                f.write(b)
        os.replace(tmp, saida)
        return saida

    def _imagem_data_uri(self, img, limite_mb=7.0):
        ext = os.path.splitext(img)[1].lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "bmp": "image/bmp"}.get(ext)
        if not mime:
            raise ErroVideo("payload", f"formato de imagem não aceito: {ext}", cobrado=False)
        b64 = base64.b64encode(open(img, "rb").read()).decode()
        if len(b64) > limite_mb * 1024 * 1024:
            raise ErroVideo("payload", f"imagem passa de {limite_mb} MB em base64 — reduza antes de enviar", cobrado=False)
        return f"data:{mime};base64,{b64}"

    def gravar_job(self, saida, dados):
        ig.gravar_json_atomico(f"{saida}.{self.nome}.json", dict(dados, provedor=self.p["id"], quando=time.strftime("%Y-%m-%dT%H:%M:%S")))

    def ler_job(self, saida):
        try:
            return json.load(open(f"{saida}.{self.nome}.json", encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def esperar(self, job_id, saida, limite_s=1200, passo=5.0):
        """Polling com espera crescente; esgotou → timeout_ambiguo (o roteador NÃO reenvia; a retomada consulta este job)."""
        t0, espera = time.time(), passo
        while time.time() - t0 < limite_s:
            st = self.get_status(job_id)
            if st["estado"] == CONCLUIDO:
                return self.download_result(job_id, saida, st)
            if st["estado"] == FALHOU:
                raise ErroVideo("permanente", f"job {job_id} falhou: {st.get('erro')}", job=job_id, cobrado=False)
            self.dormir(espera)
            espera = min(20.0, espera * 1.5)
        raise ErroVideo("timeout_ambiguo", f"job {job_id} sem resposta em {limite_s}s", job=job_id)


# ---------------------------------------------------------------- Spaces Gradio (ZeroGPU)
class GradioSpace(VideoProvider):
    """Space público com API Gradio. O catálogo descreve o endpoint (`gradio.api_name`) e o NOME de cada parâmetro, lido com
    view_api (provider_discovery.py). Grátis = cota ZeroGPU da conta/IP; esgotou → erro de cota (o roteador passa adiante).
    Não contorna fila nem cota: uma chamada por vez, com a identidade do usuário (HF_TOKEN opcional)."""
    nome = "gradio"

    def __init__(self, p, cliente=None, **k):
        super().__init__(p, **k)
        self._cliente = cliente

    def cliente(self):
        if self._cliente is None:
            import httpx
            from gradio_client import Client
            self._cliente = Client(self.p["space"], verbose=False, token=os.environ.get("HF_TOKEN") or None,
                                   httpx_kwargs={"timeout": httpx.Timeout(900.0)})
        return self._cliente

    def check_availability(self):
        import provider_discovery as pd
        info = pd.hf_space(self.p["space"])
        return {"ok": info["estado"] == "RUNNING", "estado": info["estado"], "motivo": info.get("erro")}

    def _arquivo(self, caminho):
        if self.p["gradio"].get("imagem_caminho"):
            return caminho
        from gradio_client import handle_file
        return handle_file(caminho)

    def _argumentos(self, req):
        g = self.p["gradio"]
        kw = dict(g.get("fixos") or {})
        if g.get("prompt"):
            kw[g["prompt"]] = req.get("prompt") or ""
        if g.get("negativo") and req.get("negativo"):
            kw[g["negativo"]] = req["negativo"]
        if g.get("imagem"):
            if not req.get("imagem") or not os.path.isfile(req["imagem"]):
                raise ErroVideo("payload", "image-to-video sem imagem-chave", cobrado=False)
            kw[g["imagem"]] = self._arquivo(req["imagem"])
        if g.get("ultimo_quadro") and req.get("ultimo_quadro") and os.path.isfile(req["ultimo_quadro"]):
            kw[g["ultimo_quadro"]] = self._arquivo(req["ultimo_quadro"])
        if g.get("duracao") and req.get("duration_s"):
            lo, hi = self.p.get("faixa_duracao") or [None, None]
            d = float(req["duration_s"])
            if hi is not None and d > hi + 1e-6:
                raise ErroVideo("payload", f"{d}s passa do máximo do Space ({hi}s) — divida o plano", cobrado=False)
            kw[g["duracao"]] = max(lo or d, d)
        if g.get("largura") and req.get("largura"):
            kw[g["largura"]], kw[g["altura"]] = req["largura"], req["altura"]
        return kw

    def generate_video(self, req):
        """Para o cliente o Gradio é síncrono: envia e espera na fila do Space (o job é a própria chamada)."""
        try:
            r = self.cliente().predict(api_name=self.p["gradio"]["api_name"], **self._argumentos(req))
        except ErroVideo:
            raise
        except Exception as e:  # noqa: BLE001 — gradio levanta AppError/httpx: classificar pela mensagem
            import provedores as pv
            ep = pv.classificar_texto(str(e))
            raise ErroVideo(ep.tipo, str(e)[:300], cobrado=False if ep.tipo in ("cota", "payload", "credencial") else None)
        arq = r[0] if isinstance(r, (list, tuple)) else r
        arq = arq.get("video") if isinstance(arq, dict) else arq
        if not arq or not os.path.isfile(str(arq)):
            raise ErroVideo("permanente", f"Space não devolveu vídeo: {str(r)[:200]}")
        return {"job_id": None, "arquivo": arq}

    def get_status(self, job_id):
        return {"estado": CONCLUIDO}

    def download_result(self, job_id, saida, st=None):
        return saida


# ---------------------------------------------------------------- Alibaba Model Studio (Wan)
class AlibabaWan(VideoProvider):
    """POST {base}/api/v1/services/aigc/video-generation/video-synthesis (X-DashScope-Async: enable) → output.task_id;
    GET {base}/api/v1/tasks/{task_id} → output.task_status / output.video_url (válida por 24 h). Cobra por segundo de vídeo
    gerado com sucesso (falha não é cobrada). Base: DASHSCOPE_BASE_URL = https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com."""
    nome = "alibaba"
    HOSTS = ("aliyuncs.com",)

    def base(self):
        b = os.environ.get(self.p.get("base_env", "DASHSCOPE_BASE_URL")) or self.p.get("base_url")
        if not b:
            raise ErroVideo("credencial", "DASHSCOPE_BASE_URL não definida (endpoint do workspace)", cobrado=False)
        return b.rstrip("/")

    def check_availability(self):
        try:
            self.chave()
            self.base()
        except ErroVideo as e:
            return {"ok": False, "estado": "sem_credencial", "motivo": str(e)}
        return {"ok": True, "estado": "credencial_presente", "motivo": "disponibilidade real só se confirma numa chamada (paga)"}

    def generate_video(self, req):
        if not req.get("imagem") or not os.path.isfile(req["imagem"]):
            raise ErroVideo("payload", "image-to-video sem imagem-chave", cobrado=False)
        corpo = {"model": self.p["model"], "input": {"prompt": req.get("prompt") or "", "img_url": self._imagem_data_uri(req["imagem"], 10)},
                 "parameters": {"resolution": req.get("resolucao") or self.p.get("resolucao_padrao", "480P"),
                                "duration": int(round(float(req.get("duration_s") or 5))), "prompt_extend": False, "watermark": False}}
        if req.get("negativo"):
            corpo["input"]["negative_prompt"] = req["negativo"]
        cod, r = self.transporte("POST", f"{self.base()}/api/v1/services/aigc/video-generation/video-synthesis", corpo,
                                 {"Authorization": f"Bearer {self.chave()}", "X-DashScope-Async": "enable"})
        tid = ((r or {}).get("output") or {}).get("task_id")
        if cod >= 300 or not tid:
            raise self._erro_http(cod, r)
        return {"job_id": tid}

    def get_status(self, job_id):
        cod, r = self.transporte("GET", f"{self.base()}/api/v1/tasks/{job_id}", None, {"Authorization": f"Bearer {self.chave()}"})
        if cod >= 300:
            raise self._erro_http(cod, r, job=job_id)
        o = (r or {}).get("output") or {}
        st = str(o.get("task_status", "")).upper()
        estado = {"SUCCEEDED": CONCLUIDO, "FAILED": FALHOU, "CANCELED": FALHOU, "UNKNOWN": FALHOU, "RUNNING": PROCESSANDO}.get(st, PENDENTE)
        return {"estado": estado, "url": o.get("video_url"), "erro": o.get("message") or o.get("code"), "uso": (r or {}).get("usage")}

    def download_result(self, job_id, saida, st=None):
        st = st or self.get_status(job_id)
        if not st.get("url"):
            raise ErroVideo("permanente", f"task {job_id} concluída sem video_url")
        return self._baixar(st["url"], saida, self.HOSTS)


# ---------------------------------------------------------------- LTX API
class LTXApi(VideoProvider):
    """POST https://api.ltx.io/v2/image-to-video (Bearer) → id; GET /v2/image-to-video/{id} → status pending|processing|
    completed|failed, result.video_url. image_uri aceita data URI ≤ 7 MB. Cobra por segundo do vídeo gerado."""
    nome = "ltx"
    BASE = "https://api.ltx.io"
    HOSTS = ("ltx.io", "ltx.video", "googleapis.com", "cloudfront.net", "amazonaws.com")

    def check_availability(self):
        try:
            self.chave()
        except ErroVideo as e:
            return {"ok": False, "estado": "sem_credencial", "motivo": str(e)}
        return {"ok": True, "estado": "credencial_presente", "motivo": "disponibilidade real só se confirma numa chamada (paga)"}

    def generate_video(self, req):
        if not req.get("imagem") or not os.path.isfile(req["imagem"]):
            raise ErroVideo("payload", "image-to-video sem imagem-chave", cobrado=False)
        corpo = {"image_uri": self._imagem_data_uri(req["imagem"], 7), "prompt": req.get("prompt") or "", "model": self.p["model"],
                 "duration": int(round(float(req.get("duration_s") or 5))),
                 "resolution": req.get("resolucao") or self.p.get("resolucao_padrao", "1280x720"), "generate_audio": False}
        if req.get("ultimo_quadro") and os.path.isfile(req["ultimo_quadro"]):
            corpo["last_frame_uri"] = self._imagem_data_uri(req["ultimo_quadro"], 7)
        cod, r = self.transporte("POST", f"{self.BASE}/v2/image-to-video", corpo, {"Authorization": f"Bearer {self.chave()}"})
        if cod >= 300 or not (r or {}).get("id"):
            raise self._erro_http(cod, r)
        return {"job_id": r["id"]}

    def get_status(self, job_id):
        cod, r = self.transporte("GET", f"{self.BASE}/v2/image-to-video/{job_id}", None, {"Authorization": f"Bearer {self.chave()}"})
        if cod >= 300:
            raise self._erro_http(cod, r, job=job_id)
        st = {"completed": CONCLUIDO, "failed": FALHOU, "processing": PROCESSANDO}.get((r or {}).get("status"), PENDENTE)
        return {"estado": st, "url": ((r or {}).get("result") or {}).get("video_url"), "erro": (r or {}).get("error")}

    def download_result(self, job_id, saida, st=None):
        st = st or self.get_status(job_id)
        if not st.get("url"):
            raise ErroVideo("permanente", f"job {job_id} concluído sem result.video_url")
        return self._baixar(st["url"], saida, self.HOSTS)


PROVEDORES = {"GradioSpace": GradioSpace, "AlibabaWan": AlibabaWan, "LTXApi": LTXApi}


def requisicao(t):
    """Tarefa do roteador → requisição padronizada."""
    import provedores as pv
    req = t["requirements"]
    return {"prompt": pv._prompt(req), "imagem": req.get("imagem"), "ultimo_quadro": req.get("ultimo_quadro"),
            "duration_s": req.get("duration_s"), "resolucao": req.get("resolucao"), "negativo": req.get("negativo"),
            "largura": req.get("largura"), "altura": req.get("altura")}


FABRICAS = {}  # testes: FABRICAS["LTXApi"] = lambda p: LTXApi(p, transporte=falso)


def adaptador(nome, cls_provedor):
    """VideoProvider → adaptador do roteador (executar / recuperar). ErroVideo vira ErroProvedor com o mesmo tipo."""
    import provedores as pv

    class A(pv.Adaptador):
        def _vp(self):
            return (FABRICAS.get(nome) or cls_provedor)(self.p)

        def executar(self, t, tid):
            saida = self.saida(t)
            vp = self._vp()
            req = requisicao(t)
            t0 = time.time()
            try:
                r = vp.generate_video(req)
                if r.get("arquivo"):  # Gradio devolve o arquivo direto
                    shutil.copy(r["arquivo"], saida)
                else:
                    vp.gravar_job(saida, {"job_id": r["job_id"], "estado": "enviado"})  # antes de esperar: retomada não reenvia
                    vp.esperar(r["job_id"], saida, limite_s=float(self.p.get("timeout_s", 1200)))
                    vp.gravar_job(saida, {"job_id": r["job_id"], "estado": "baixado"})
            except ErroVideo as e:
                raise pv.ErroProvedor(e.tipo, str(e), cobrado=e.cobrado, job_remoto=e.job)
            if not ig.midia_valida(saida, "video")[0]:
                raise pv.ErroProvedor("permanente", "resultado não é um vídeo válido")
            json.dump({"modelo": self.p.get("model"), "provedor": self.p["id"], "prompt": req["prompt"], "duracao": req.get("duration_s"),
                       "resolucao": req.get("resolucao"), "tempo_s": round(time.time() - t0, 1), "tentativa": tid},
                      open(saida + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            est = vp.estimate_cost(req)
            return {"saida": saida, "custo_real": 0.0 if est == 0 else None, "uso": {"unit": "second", "quantity": req.get("duration_s")},
                    "job_remoto": (vp.ler_job(saida) or {}).get("job_id")}

        def recuperar(self, t, evento):
            saida = evento.get("saida_prevista") or t["requirements"].get("saida")
            vp = self._vp()
            job = (vp.ler_job(saida) or {}).get("job_id") or evento.get("job_remoto")
            if not job:
                return None
            try:
                st = vp.get_status(job)
                if st["estado"] != CONCLUIDO:
                    raise pv.ErroProvedor("permanente" if st["estado"] == FALHOU else "transitorio", f"job {job}: {st['estado']}")
                vp.download_result(job, saida, st)
            except ErroVideo as e:
                raise pv.ErroProvedor(e.tipo, str(e), job_remoto=job)
            return {"saida": saida, "custo_real": None}

    A.__name__ = nome
    return A


def registrar(adaptadores):
    for nome, cls in PROVEDORES.items():
        adaptadores.setdefault(nome, adaptador(nome, cls))
    return adaptadores
