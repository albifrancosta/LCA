"""Cliente Runware (REST) da skill criador-video — fornecedor PRINCIPAL de imagem/vídeo (INTEGRACAO-RUNWARE.md, 2026-11-06).

Entra pelo roteador (`provedores.py`, adaptadores RunwareVideo / RunwareLipsync / RunwareImagem): orçamento, reserva
atômica, fallback para o fal.ai, trava de voz/estilo e inspeção continuam lá. Este módulo só fala com a Runware:
  - chave na variável RUNWARE_API_KEY (ou no registro do Windows) — nunca em arquivo, log ou mensagem;
  - VALIDA contra o catálogo local de modelos (campos lidos dos schema.json oficiais) ANTES de qualquer rede: AIR
    desconhecido, duração fora do enum/faixa, último quadro sem suporte, imagem < 300 px ou proporção fora de 0,4–2,5,
    áudio ausente no lip-sync → erro `payload`, custo zero, nada é enviado;
  - grava o job (`<saida>.runware.json`, com o taskUUID) ANTES do envio; vídeo é assíncrono: consulta `getResponse`
    com backoff exponencial; tempo esgotado NÃO reenvia — o job fica `processing` e `retomar` continua do mesmo taskUUID;
  - cache pelo hash da entrada (AIR, versão do schema, prompt normalizado, parâmetros, sha256 das imagens/áudio, seed):
    resultado idêntico volta do disco, custo 0, sem API;
  - baixa só HTTPS de domínio permitido (*.runware.ai; extras em RUNWARE_HOSTS_EXTRA), redirecionamento conferido a
    cada salto, tamanho máximo, escrita atômica; URL da Runware expira (~7 dias): o arquivo fica no projeto;
  - áudio local sobe pelo `mediaStorage` (o schema do avatar/OmniHuman só aceita UUID/URL); mediaUUID em cache por sha256;
  - custo real = `cost` de `includeCost`; sem ele o custo fica DESCONHECIDO (None), nunca zero;
  - saldo pela `accountManagement`/`getDetails` (verificação extra — não substitui o teto aprovado do projeto).

CLI (nenhum comando abaixo gera nada pago):
  python runware.py modelos                       → modelos validados, modos, durações e preço com fonte/data
  python runware.py conta                         → saldo da conta (operação não gerativa)
  python runware.py validar --modelo klingai:kling-video@2.6-pro --duracao 5 --imagem img.png [--ultimo-quadro fim.png]
  python runware.py retomar assets/clips/c05a.mp4 → consulta o job já enviado (mesmo taskUUID) e baixa; não reenvia
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(AQUI)
MEM = os.path.join(SKILL, "memoria")
API = "https://api.runware.ai/v1"
KEY_ENV = "RUNWARE_API_KEY"
HOSTS_OK = (".runware.ai",)
MAX_BYTES = 600 * 1024 * 1024
CFG = {"request_timeout_seconds": 45, "poll_initial_seconds": 2, "poll_max_seconds": 20, "max_poll_minutes": 20}

# Catálogo local VALIDADO (schema.json + x-pricing de runware.ai/docs/models/<modelo>, lidos em 2026-11-06).
# Só entra aqui o que foi conferido; modelo fora da lista é recusado antes da rede.
MODELOS = {
    "klingai:kling-video@2.6-pro": {
        "tipo": "video", "modos": ["image_to_video"], "duracao": {"enum": [5, 10]}, "frames_max": 2, "ultimo_quadro": True,
        "sem_dimensoes_com_frames": True, "preco": {"unidade": "segundo", "valor": 0.07},
        "fonte": "runware.ai/docs/models/klingai-video-2-6-pro schema.json x-pricing 'without audio' $0.07/s", "verificado": "2026-11-06"},
    "klingai:kling-video@3-pro": {
        "tipo": "video", "modos": ["image_to_video"], "duracao": {"min": 3, "max": 15}, "frames_max": 2, "ultimo_quadro": True,
        "sem_dimensoes_com_frames": True, "min_lado": 300, "proporcao": [0.4, 2.5], "preco": {"unidade": "segundo", "valor": 0.112},
        "fonte": "runware.ai/docs/models/klingai-video-3-0-pro schema.json x-pricing '1080p without audio' $0.112/s", "verificado": "2026-11-06"},
    "klingai:avatar@2.0-standard": {
        "tipo": "lipsync", "modos": ["image_audio_to_video"], "min_lado": 300, "proporcao": [0.4, 2.5],
        "preco": {"unidade": "segundo_audio", "valor": 0.044},
        "fonte": "runware.ai/docs/models/klingai-avatar-2-0-standard schema.json x-pricing $0.044/s", "verificado": "2026-11-06"},
    "klingai:avatar@2.0-pro": {
        "tipo": "lipsync", "modos": ["image_audio_to_video"], "min_lado": 300, "proporcao": [0.4, 2.5],
        "preco": {"unidade": "segundo_audio", "valor": 0.087},
        "fonte": "runware.ai/docs/models/klingai-avatar-2-0-pro (página, 'Cost and speed') $0.087/s", "verificado": "2026-11-06"},
    "bytedance:5@2": {
        "tipo": "lipsync", "modos": ["image_audio_to_video"], "preco": {"unidade": "segundo_audio", "valor": 0.13247},
        "fonte": "runware.ai/docs/models/bytedance-omnihuman-1-5 schema.json x-pricing $0.132/s (OmniHuman 1.5)", "verificado": "2026-11-06"},
    "runware:z-image@0": {
        "tipo": "imagem", "modos": ["text_to_image"], "preco": None, "referencias": None,
        "fonte": "exemplo da doc da API; preço e campo de referência NÃO verificados → bloqueia até conferir", "verificado": None},
}


# ---------------------------------------------------------------- tipos
@dataclass
class GenerationRequest:
    project_id: str
    shot_id: str
    kind: str                      # image | video | lipsync
    mode: str                      # text_to_image | image_to_video | image_audio_to_video
    positive_prompt: str
    model_air: str
    saida: str
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    resolution: str | None = None
    first_frame_path: str | None = None
    last_frame_path: str | None = None
    audio_path: str | None = None
    reference_paths: list = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    max_cost_usd: float | None = None
    seed: int | None = None


@dataclass
class GenerationResult:
    status: str                    # success | failed | pending | uncertain
    provider: str
    model_air: str
    task_uuid: str | None
    local_path: str | None
    cost_usd: float | None         # None = desconhecido (NUNCA zero por omissão)
    input_hash: str
    output_hash: str | None = None
    error_code: str | None = None
    cache: bool = False
    estimated_cost_usd: float | None = None


class ErroRunware(Exception):
    """tipo: credencial | saldo | payload | taxa | transitorio | timeout_ambiguo | permanente (mesma taxonomia do roteador)."""

    def __init__(self, tipo, msg, cobrado=None, job_remoto=None):
        super().__init__(sanitizar(msg))
        self.tipo, self.cobrado, self.job_remoto = tipo, cobrado, job_remoto


# ---------------------------------------------------------------- segredo
def chave(obrigatoria=True):
    import chaves
    k = chaves.obter(KEY_ENV, obrigatoria=False)
    if not k and obrigatoria:
        raise ErroRunware("credencial", "(nada foi enviado) " + chaves.mensagem_falta(KEY_ENV, "clipes na Runware"), cobrado=False)
    return k


TOKEN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}|\b[A-Za-z0-9]{32,}\b")


def sanitizar(texto):
    s = str(texto)
    k = os.environ.get(KEY_ENV)
    if k and len(k) >= 6:
        s = s.replace(k, "***")
    return TOKEN.sub(lambda m: (m.group(1) or "") + "***", s)[:600]


# ---------------------------------------------------------------- utilidades
def agora_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def sha256_arq(arq):
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def ler_json(arq, padrao):
    try:
        return json.load(io.open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(arq, dados):
    os.makedirs(os.path.dirname(os.path.abspath(arq)) or ".", exist_ok=True)
    tmp = f"{arq}.{uuid.uuid4().hex[:6]}.tmp"
    json.dump(dados, io.open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, arq)


def data_uri(arq):
    mime = mimetypes.guess_type(arq)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(open(arq, "rb").read()).decode()


def duracao_midia(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def dimensoes(arq):
    try:
        from PIL import Image
        with Image.open(arq) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- validação (antes de qualquer rede)
def validar(req):
    spec = MODELOS.get(req.model_air)
    if not spec:
        raise ErroRunware("payload", f"modelo {req.model_air} fora do catálogo validado da Runware (runware.py modelos)", cobrado=False)
    tipo = {"image": "imagem", "video": "video", "lipsync": "lipsync"}.get(req.kind, req.kind)
    if spec["tipo"] != tipo:
        raise ErroRunware("payload", f"{req.model_air} é de {spec['tipo']}, não {tipo}", cobrado=False)
    if req.mode not in spec["modos"]:
        raise ErroRunware("payload", f"{req.model_air} não aceita o modo {req.mode} (aceita {', '.join(spec['modos'])})", cobrado=False)
    if spec["tipo"] == "video":
        d = req.duration_seconds
        regra = spec.get("duracao") or {}
        if d is None:
            raise ErroRunware("payload", "vídeo sem duração — o contrato define a duração", cobrado=False)
        if "enum" in regra and int(round(d)) not in regra["enum"] or abs(d - round(d)) > 1e-6:
            if "enum" in regra:
                raise ErroRunware("payload", f"{d}s não suportado por {req.model_air} (só {regra['enum']} s)", cobrado=False)
        if "min" in regra and not (regra["min"] <= d <= regra["max"]) or ("min" in regra and abs(d - round(d)) > 1e-6):
            raise ErroRunware("payload", f"{d}s fora da faixa {regra['min']}–{regra['max']} s inteiros de {req.model_air}", cobrado=False)
        if not req.first_frame_path:
            raise ErroRunware("payload", "image_to_video sem primeiro quadro", cobrado=False)
        if req.last_frame_path and not spec.get("ultimo_quadro"):
            raise ErroRunware("payload", f"{req.model_air} não declara suporte a último quadro", cobrado=False)
        if (req.width or req.height) and spec.get("sem_dimensoes_com_frames"):
            raise ErroRunware("payload", "este modelo proíbe width/height junto com frameImages (tamanho vem da imagem)", cobrado=False)
        imgs = [x for x in (req.first_frame_path, req.last_frame_path) if x]
    elif spec["tipo"] == "lipsync":
        if not req.first_frame_path or not req.audio_path:
            raise ErroRunware("payload", "lip-sync precisa de inputs.image (rosto) e inputs.audio (fala)", cobrado=False)
        if not os.path.isfile(req.audio_path):
            raise ErroRunware("payload", f"áudio não encontrado: {req.audio_path}", cobrado=False)
        imgs = [req.first_frame_path]
    else:
        if req.reference_paths and not spec.get("referencias"):
            raise ErroRunware("payload", f"{req.model_air}: campo de imagem de referência não verificado no schema — não envio", cobrado=False)
        imgs = list(req.reference_paths)
    for im in imgs:
        if not os.path.isfile(im):
            raise ErroRunware("payload", f"imagem não encontrada: {im}", cobrado=False)
        wh = dimensoes(im)
        if wh and spec.get("min_lado") and min(wh) < spec["min_lado"]:
            raise ErroRunware("payload", f"{os.path.basename(im)} {wh[0]}×{wh[1]}: mínimo {spec['min_lado']} px por lado", cobrado=False)
        if wh and spec.get("proporcao"):
            a, b = spec["proporcao"]
            if not (a <= wh[0] / wh[1] <= b):
                raise ErroRunware("payload", f"{os.path.basename(im)}: proporção {wh[0] / wh[1]:.2f} fora de {a}–{b}", cobrado=False)
    return spec


def estimar(req, spec=None):
    """US$ estimado ou None (desconhecido)."""
    spec = spec or MODELOS.get(req.model_air) or {}
    pr = spec.get("preco")
    if not pr:
        return None
    if pr["unidade"] == "segundo":
        return round(pr["valor"] * float(req.duration_seconds or 0), 4) if req.duration_seconds else None
    if pr["unidade"] == "segundo_audio":
        d = duracao_midia(req.audio_path) if req.audio_path else None
        return round(pr["valor"] * d, 4) if d else None
    if pr["unidade"] == "imagem":
        return pr["valor"]
    return None


def input_hash(req):
    arquivos = {k: sha256_arq(v) for k, v in (("first", req.first_frame_path), ("last", req.last_frame_path), ("audio", req.audio_path))
                if v and os.path.isfile(v)}
    arquivos["refs"] = [sha256_arq(r) for r in req.reference_paths if os.path.isfile(r)]
    spec = MODELOS.get(req.model_air) or {}
    corpo = {"provider": "runware", "air": req.model_air, "schema": spec.get("verificado"), "kind": req.kind, "mode": req.mode,
             "prompt": " ".join((req.positive_prompt or "").split()).strip().lower(), "dur": req.duration_seconds, "w": req.width,
             "h": req.height, "res": req.resolution, "seed": req.seed, "arquivos": arquivos,
             "identidade": (req.constraints or {}).get("identidade")}
    return hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------- transporte
def http_post(corpo, timeout=None):
    req = urllib.request.Request(API, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave()}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or CFG["request_timeout_seconds"]) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        texto = e.read().decode(errors="replace")
        try:
            return dict(json.loads(texto), _http=e.code)
        except ValueError:
            raise ErroRunware(classificar(texto, e.code), f"Runware HTTP {e.code}: {texto[:300]}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroRunware("transitorio", f"rede: {e}") from None


def classificar(texto, codigo=None):
    m = (texto or "").lower()
    if codigo == 402 or any(x in m for x in ("insufficient", "credit", "balance", "funds")):
        return "saldo"
    if codigo in (401, 403) or any(x in m for x in ("apikey", "api key", "unauthor", "authentication", "forbidden")):
        return "credencial"
    if codigo == 429 or "rate" in m or "too many" in m:
        return "taxa"
    if codigo in (400, 404, 422) or any(x in m for x in ("invalid", "unsupported", "validation", "schema", "not found", "required")):
        return "payload"
    if codigo in (500, 502, 503, 504) or any(x in m for x in ("timeout", "temporar", "unavailable")):
        return "transitorio"
    return "permanente"


def erros_de(resp):
    errs = resp.get("errors") or resp.get("error")
    if not errs:
        return None
    errs = errs if isinstance(errs, list) else [errs]
    texto = "; ".join(f"{e.get('code', '')}: {e.get('message', '')}" if isinstance(e, dict) else str(e) for e in errs)
    return ErroRunware(classificar(texto, resp.get("_http")), f"Runware: {texto}")


# ---------------------------------------------------------------- download seguro
class _Redir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host_ok(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def host_ok(url):
    u = urllib.parse.urlparse(url)
    extras = tuple("." + h.strip().lstrip(".") for h in os.environ.get("RUNWARE_HOSTS_EXTRA", "").split(",") if h.strip())
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host.endswith(s) or host == s.lstrip(".") for s in HOSTS_OK + extras):
        raise ErroRunware("permanente", f"URL de mídia recusada (só HTTPS de domínio permitido): {u.scheme}://{host}")
    return True


def baixar(url, saida, abrir=None):
    host_ok(url)
    abrir = abrir or urllib.request.build_opener(_Redir()).open
    pasta = os.path.dirname(os.path.abspath(saida)) or "."
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pasta, suffix=".part")
    total = 0
    try:
        with abrir(url, timeout=120) as r, os.fdopen(fd, "wb") as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                total += len(bloco)
                if total > MAX_BYTES:
                    raise ErroRunware("permanente", f"mídia passa de {MAX_BYTES // 2**20} MB — recusada")
                f.write(bloco)
        os.replace(tmp, saida)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return saida


# ---------------------------------------------------------------- cliente
class Cliente:
    """transporte(corpo:list) -> dict e abrir(url) são injetáveis (os testes usam falsos: nada vai para a rede)."""

    def __init__(self, transporte=None, dormir=time.sleep, relogio=time.time, abrir=None, mem=None, cfg=None):
        self.post = transporte or http_post
        self.dormir, self.relogio, self.abrir = dormir, relogio, abrir
        self.mem = mem or MEM
        rot = ler_json(os.path.join(SKILL, "config", "roteamento.json"), {}).get("runware") or {}
        self.cfg = {**CFG, **{k: v for k, v in rot.items() if k in CFG}, **(cfg or {})}

    # -- estado local
    def _arq(self, nome):
        return os.path.join(self.mem, nome)

    def log(self, evento):
        os.makedirs(self.mem, exist_ok=True)
        with open(self._arq("runware-log.jsonl"), "a", encoding="utf-8") as f:
            f.write(sanitizar(json.dumps(dict(evento, quando=agora_iso()), ensure_ascii=False, default=str)) + "\n")

    def _enviar(self, tarefas):
        resp = self.post(tarefas)
        e = erros_de(resp)
        if e:
            raise e
        return resp.get("data") or []

    # -- operações não gerativas
    def conta(self):
        d = self._enviar([{"taskType": "accountManagement", "taskUUID": str(uuid.uuid4()), "operation": "getDetails"}])
        return d[0] if d else {}

    def subir_midia(self, arq):
        idx = ler_json(self._arq("runware-midias.json"), {})
        h = sha256_arq(arq)
        if h in idx:
            return idx[h]
        d = self._enviar([{"taskType": "mediaStorage", "taskUUID": str(uuid.uuid4()), "operation": "upload", "media": data_uri(arq)}])
        mid = (d[0] if d else {}).get("mediaUUID")
        if not mid:
            raise ErroRunware("permanente", "mediaStorage não devolveu mediaUUID", cobrado=False)
        idx[h] = mid
        gravar_json(self._arq("runware-midias.json"), idx)
        return mid

    # -- montagem da tarefa
    def montar(self, req, spec, task_uuid):
        t = {"taskUUID": task_uuid, "model": req.model_air, "includeCost": True}
        if spec["tipo"] == "video":
            frames = [{"image": data_uri(req.first_frame_path), "frame": "first"}]
            if req.last_frame_path:
                frames.append({"image": data_uri(req.last_frame_path), "frame": "last"})
            t.update(taskType="videoInference", duration=int(round(req.duration_seconds)), inputs={"frameImages": frames},
                     deliveryMethod="async")
            if req.positive_prompt:
                t["positivePrompt"] = req.positive_prompt[:2500]
        elif spec["tipo"] == "lipsync":
            t.update(taskType="videoInference", deliveryMethod="async",
                     inputs={"image": data_uri(req.first_frame_path), "audio": self.subir_midia(req.audio_path)})
            if req.positive_prompt:
                t["positivePrompt"] = req.positive_prompt[:2500]
        else:
            t.update(taskType="imageInference", positivePrompt=req.positive_prompt, width=req.width or 1024, height=req.height or 1024)
        if req.seed is not None:
            t["seed"] = req.seed
        return t

    # -- geração
    def gerar(self, req):
        spec = validar(req)  # erro aqui = nada enviado, custo zero
        h = input_hash(req)
        est = estimar(req, spec)
        cache = ler_json(self._arq("runware-cache.json"), {})
        c = cache.get(h)
        if c and os.path.isfile(c["arquivo"]) and sha256_arq(c["arquivo"]) == c["sha256"]:
            if os.path.abspath(c["arquivo"]) != os.path.abspath(req.saida):
                shutil.copy(c["arquivo"], req.saida)
            self.log({"evento": "cache", "project_id": req.project_id, "shot_id": req.shot_id, "model_air": req.model_air,
                      "input_hash": h, "custo_usd": 0.0})
            return GenerationResult("success", "runware", req.model_air, c.get("taskUUID"), req.saida, 0.0, h, c["sha256"],
                                    cache=True, estimated_cost_usd=est)
        jarq = req.saida + ".runware.json"
        job = ler_json(jarq, None)
        if job and job.get("input_hash") == h:
            if job.get("estado") in ("submitted", "processing"):
                return self.retomar(req.saida)  # mesmo pedido já enviado: consulta, NÃO reenvia
            if job.get("estado") == "unknown_billing":
                raise ErroRunware("timeout_ambiguo", f"job {job['taskUUID']} ficou com cobrança indeterminada — reconcilie antes de gerar de novo",
                                  job_remoto=job["taskUUID"])
        tid = str(uuid.uuid4())
        tarefa = self.montar(req, spec, tid)
        job = {"taskUUID": tid, "model": req.model_air, "estado": "planned", "input_hash": h, "estimado_usd": est, "custo_usd": None,
               "project_id": req.project_id, "shot_id": req.shot_id, "criado": agora_iso(), "saida": req.saida}
        gravar_json(jarq, job)
        job["estado"] = "submitted"
        gravar_json(jarq, job)  # persistido ANTES do envio: crash depois daqui é retomável pelo taskUUID
        self.log({"evento": "envio", "project_id": req.project_id, "shot_id": req.shot_id, "task_uuid": tid, "model_air": req.model_air,
                  "estimado_usd": est, "input_hash": h})
        try:
            dados = self._enviar([tarefa])
        except ErroRunware as e:
            if e.tipo in ("transitorio",):  # não sabemos se a Runware recebeu: nunca reenviar às cegas
                job["estado"] = "unknown_billing"
                gravar_json(jarq, job)
                raise ErroRunware("timeout_ambiguo", f"envio sem resposta ({e}) — `runware.py retomar {req.saida}`", job_remoto=tid) from None
            job["estado"] = "failed"
            gravar_json(jarq, job)
            e.cobrado = False if e.tipo in ("payload", "credencial", "saldo") else e.cobrado
            raise
        linha = next((d for d in dados if d.get("taskUUID") == tid), dados[0] if dados else {})
        if linha.get("status") == "success" or linha.get("videoURL") or linha.get("imageURL"):
            return self._concluir(req.saida, job, linha)
        job["estado"] = "processing"
        gravar_json(jarq, job)
        return self._acompanhar(req.saida, job)

    def retomar(self, saida):
        job = ler_json(saida + ".runware.json", None)
        if not job:
            raise ErroRunware("permanente", f"sem job Runware gravado para {saida}", cobrado=False)
        if job.get("estado") == "succeeded" and os.path.isfile(saida):
            return GenerationResult("success", "runware", job["model"], job["taskUUID"], saida, job.get("custo_usd"), job["input_hash"],
                                    sha256_arq(saida), estimated_cost_usd=job.get("estimado_usd"))
        return self._acompanhar(saida, job)

    def _acompanhar(self, saida, job):
        jarq = saida + ".runware.json"
        espera, inicio = float(self.cfg["poll_initial_seconds"]), self.relogio()
        while True:
            try:
                dados = self._enviar([{"taskType": "getResponse", "taskUUID": job["taskUUID"]}])
            except ErroRunware as e:
                if e.tipo not in ("transitorio", "taxa"):
                    raise
                dados = []
            linha = next((d for d in dados if d.get("taskUUID") == job["taskUUID"]), None)
            if linha and (linha.get("status") == "success" or linha.get("videoURL") or linha.get("imageURL")):
                return self._concluir(saida, job, linha)
            if linha and linha.get("status") == "error":
                job["estado"] = "failed"
                gravar_json(jarq, job)
                raise ErroRunware(classificar(json.dumps(linha)), f"Runware falhou o job {job['taskUUID']}: {json.dumps(linha)[:300]}",
                                  cobrado=False, job_remoto=job["taskUUID"])  # "Failed generations are not charged"
            if self.relogio() - inicio > float(self.cfg["max_poll_minutes"]) * 60:
                job["estado"] = "processing"
                gravar_json(jarq, job)
                raise ErroRunware("timeout_ambiguo", f"job {job['taskUUID']} ainda processando — `runware.py retomar {saida}` (não reenvie)",
                                  job_remoto=job["taskUUID"])
            self.dormir(espera)
            espera = min(float(self.cfg["poll_max_seconds"]), espera * 2)

    def _concluir(self, saida, job, linha):
        url = linha.get("videoURL") or linha.get("imageURL") or linha.get("audioURL")
        if not url:
            raise ErroRunware("permanente", "resposta de sucesso sem URL de mídia", job_remoto=job["taskUUID"])
        baixar(url, saida, self.abrir)
        custo = linha.get("cost")
        job.update(estado="succeeded", custo_usd=float(custo) if custo is not None else None, sha256_saida=sha256_arq(saida),
                   concluido=agora_iso())
        gravar_json(saida + ".runware.json", job)
        cache = ler_json(self._arq("runware-cache.json"), {})
        cache[job["input_hash"]] = {"arquivo": os.path.abspath(saida), "sha256": job["sha256_saida"], "taskUUID": job["taskUUID"],
                                    "custo_usd": job["custo_usd"]}
        gravar_json(self._arq("runware-cache.json"), cache)
        self.log({"evento": "sucesso", "project_id": job.get("project_id"), "shot_id": job.get("shot_id"), "task_uuid": job["taskUUID"],
                  "model_air": job["model"], "estimado_usd": job.get("estimado_usd"), "custo_usd": job["custo_usd"]})
        return GenerationResult("success", "runware", job["model"], job["taskUUID"], saida, job["custo_usd"], job["input_hash"],
                                job["sha256_saida"], estimated_cost_usd=job.get("estimado_usd"))


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("modelos")
    sub.add_parser("conta")
    v = sub.add_parser("validar")
    v.add_argument("--modelo", required=True)
    v.add_argument("--duracao", type=float)
    v.add_argument("--imagem")
    v.add_argument("--ultimo-quadro")
    v.add_argument("--audio")
    r = sub.add_parser("retomar")
    r.add_argument("saida")
    a = ap.parse_args()
    try:
        if a.cmd == "modelos":
            for air, s in MODELOS.items():
                pr = s.get("preco")
                print(f"{air:30s} {s['tipo']:8s} {','.join(s['modos']):22s} dur {s.get('duracao', '—')!s:18s} "
                      f"{'US$ ' + str(pr['valor']) + '/' + pr['unidade'] if pr else 'PREÇO NÃO VERIFICADO (bloqueia)':28s} {s.get('verificado') or ''}")
        elif a.cmd == "conta":
            d = Cliente().conta()
            print(sanitizar(json.dumps({k: v for k, v in d.items() if "balance" in k.lower() or k in ("currency", "credits")},
                                       ensure_ascii=False, default=str)))
        elif a.cmd == "validar":
            spec = MODELOS.get(a.modelo) or {}
            tipo = spec.get("tipo", "video")
            req = GenerationRequest("cli", "cli", {"imagem": "image"}.get(tipo, tipo), spec.get("modos", ["image_to_video"])[0], "", a.modelo,
                                    "validar.mp4", a.duracao, first_frame_path=a.imagem, last_frame_path=a.ultimo_quadro, audio_path=a.audio)
            validar(req)
            print(f"ok: {a.modelo} aceita esta entrada · estimativa US$ {estimar(req)}")
        else:
            print(json.dumps(asdict(Cliente().retomar(a.saida)), ensure_ascii=False, indent=1))
    except ErroRunware as e:
        sys.exit(f"[{e.tipo}] {e}")


if __name__ == "__main__":
    main()
