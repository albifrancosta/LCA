"""Runware FALSA para os testes: transporte HTTP e download simulados no formato documentado da API
(POST array de tarefas → {"data": [...]}, getResponse com status processing|success|error). Nada vai para a rede."""
import io
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import runware as rw  # noqa: E402

_MP4 = {}


def mp4_real():
    """Um MP4 válido de 1 s (para a checagem de mídia do roteador)."""
    if "b" not in _MP4:
        arq = os.path.join(tempfile.mkdtemp(prefix="rwf-"), "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10", arq], check=True)
        _MP4["b"] = open(arq, "rb").read()
    return _MP4["b"]


def png(pasta, nome="img.png", w=640, h=360):
    from PIL import Image
    arq = os.path.join(pasta, nome)
    Image.new("RGB", (w, h), (40, 80, 160)).save(arq)
    return arq


def wav(pasta, nome="voz.wav", dur=1.0):
    arq = os.path.join(pasta, nome)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}", arq], check=True)
    return arq


class Falso:
    """estados: lista de status que o getResponse devolve em sequência ('processing'|'success'|'error').
    imediato=True: a submissão já volta com o resultado. custo=None simula resposta sem `cost`."""

    def __init__(self, estados=("processing", "success"), imediato=False, custo=0.35, erro_envio=None, url="https://vm.runware.ai/v/x.mp4"):
        self.estados, self.imediato, self.custo, self.erro_envio, self.url = list(estados), imediato, custo, erro_envio, url
        self.chamadas = []
        self.tarefas = []

    def n(self, tipo):
        return sum(1 for c in self.chamadas if c == tipo)

    def __call__(self, corpo):
        t = corpo[0]
        self.chamadas.append(t["taskType"])
        self.tarefas.append(t)
        if t["taskType"] in ("videoInference", "imageInference"):
            if self.erro_envio:
                raise self.erro_envio
            if self.imediato or t["taskType"] == "imageInference":
                return {"data": [self._ok(t["taskUUID"], imagem=t["taskType"] == "imageInference")]}
            return {"data": [{"taskUUID": t["taskUUID"], "status": "processing"}]}
        if t["taskType"] == "getResponse":
            st = self.estados.pop(0) if self.estados else "success"
            if st == "success":
                return {"data": [self._ok(t["taskUUID"])]}
            if st == "error":
                return {"data": [{"taskUUID": t["taskUUID"], "status": "error", "message": "content moderation"}]}
            return {"data": [{"taskUUID": t["taskUUID"], "status": "processing", "progress": 40}]}
        if t["taskType"] == "mediaStorage":
            return {"data": [{"taskUUID": t["taskUUID"], "mediaUUID": "11111111-2222-3333-4444-555555555555"}]}
        if t["taskType"] == "accountManagement":
            return {"data": [{"taskUUID": t["taskUUID"], "balance": {"amount": 1.5, "freeBalance": 2.0, "currency": "USD"}}]}
        return {"errors": [{"code": "unknownTask", "message": "invalid taskType"}], "_http": 400}

    def _ok(self, tid, imagem=False):
        d = {"taskUUID": tid, "status": "success", ("imageURL" if imagem else "videoURL"): self.url.replace(".mp4", ".png") if imagem else self.url}
        if self.custo is not None:
            d["cost"] = self.custo
        return d


def abrir_falso(conteudo=None):
    def abrir(url, timeout=None):
        rw.host_ok(url)
        return io.BytesIO(conteudo if conteudo is not None else mp4_real())
    return abrir


def cliente(falso, mem, **cfg):
    return rw.Cliente(transporte=falso, dormir=lambda s: None, abrir=abrir_falso(), mem=mem,
                      cfg=dict({"poll_initial_seconds": 0, "poll_max_seconds": 0, "max_poll_minutes": 5}, **cfg))


def pedido(pasta, **k):
    base = dict(project_id="p", shot_id="s1", kind="video", mode="image_to_video", positive_prompt="ele pega o celular e reage",
                model_air="klingai:kling-video@2.6-pro", saida=os.path.join(pasta, "s1.mp4"), duration_seconds=5,
                first_frame_path=png(pasta))
    base.update(k)
    return rw.GenerationRequest(**base)


def rodar(globais):
    testes = [v for k, v in sorted(globais.items()) if k.startswith("test_")]
    ok = 0
    for t in testes:
        try:
            t()
            ok += 1
            print("✅", t.__name__)
        except Exception as e:  # noqa: BLE001
            print("❌", t.__name__, repr(e)[:300])
    print(f"\n{ok}/{len(testes)} passaram")
    sys.exit(0 if ok == len(testes) else 1)
