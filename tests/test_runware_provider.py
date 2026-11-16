"""Cliente Runware (scripts/runware.py) — sem rede, sem crédito (INTEGRACAO-RUNWARE.md §8).
Rodar: python tests/test_runware_provider.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runware_falso as F  # noqa: E402
from runware_falso import rw  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")



def tmp():
    return tempfile.mkdtemp(prefix="rwp-")


def erro(func):
    try:
        func()
    except rw.ErroRunware as e:
        return e
    raise AssertionError("esperava ErroRunware")


def test_sem_chave_diagnostico_claro_e_nada_enviado():
    import chaves  # leitura central: isola ambiente, .env e registro do Windows
    salvo_env = os.environ.pop(rw.KEY_ENV, None)
    salvo_origem = os.environ.pop(f"_CV_ORIGEM_{rw.KEY_ENV}", None)
    salvo_reg, salvo_arq = chaves._registro_windows, os.environ.get("CRIADOR_VIDEO_ENV")
    chaves._registro_windows = lambda n: None
    os.environ["CRIADOR_VIDEO_ENV"] = os.path.join(tmp(), "nao-existe.env")
    chaves._carregado = False
    try:
        e = erro(lambda: rw.http_post([{"taskType": "accountManagement"}]))
        assert e.tipo == "credencial" and "RUNWARE_API_KEY" in str(e) and "nada foi enviado" in str(e) and e.cobrado is False
    finally:
        chaves._registro_windows = salvo_reg
        if salvo_arq is None:
            os.environ.pop("CRIADOR_VIDEO_ENV", None)
        else:
            os.environ["CRIADOR_VIDEO_ENV"] = salvo_arq
        chaves._carregado = False
        if salvo_env:
            os.environ[rw.KEY_ENV] = salvo_env
        if salvo_origem:
            os.environ[f"_CV_ORIGEM_{rw.KEY_ENV}"] = salvo_origem


def test_air_invalido_duracao_e_quadros_rejeitados_antes_da_rede():
    d = tmp()
    f = F.Falso()
    c = F.cliente(f, d)
    casos = [F.pedido(d, model_air="klingai:nao-existe@1"),
             F.pedido(d, duration_seconds=7),                                  # 2.6 só aceita 5 ou 10
             F.pedido(d, model_air="klingai:kling-video@3-pro", duration_seconds=20),
             F.pedido(d, model_air="klingai:kling-video@3-pro", first_frame_path=F.png(d, "p.png", 200, 200)),  # < 300 px
             F.pedido(d, width=1920, height=1080),                             # proibido com frameImages
             F.pedido(d, kind="lipsync", mode="image_audio_to_video", model_air="klingai:avatar@2.0-standard", audio_path=None)]
    for r in casos:
        e = erro(lambda r=r: c.gerar(r))
        assert e.tipo == "payload" and e.cobrado is False, e
    assert f.chamadas == [], f.chamadas  # nenhuma submissão, custo zero


def test_imagem_simples_salva_arquivo_e_custo():
    d = tmp()
    f = F.Falso(custo=0.012)
    c = F.cliente(f, d)
    r = c.gerar(F.pedido(d, kind="image", mode="text_to_image", model_air="runware:z-image@0", first_frame_path=None,
                         duration_seconds=None, saida=os.path.join(d, "i.png"), width=1024, height=1024))
    assert f.chamadas == ["imageInference"] and f.tarefas[0]["includeCost"] is True
    assert r.status == "success" and os.path.isfile(r.local_path) and r.cost_usd == 0.012 and r.output_hash


def test_i2v_primeiro_e_ultimo_quadro_so_onde_o_schema_aceita():
    d = tmp()
    f = F.Falso(imediato=True)
    c = F.cliente(f, d)
    c.gerar(F.pedido(d, last_frame_path=F.png(d, "fim.png")))
    fr = f.tarefas[0]["inputs"]["frameImages"]
    assert [x["frame"] for x in fr] == ["first", "last"] and "width" not in f.tarefas[0] and f.tarefas[0]["duration"] == 5
    assert f.tarefas[0]["deliveryMethod"] == "async"


def test_processing_consulta_getresponse_e_nao_reenvia():
    d = tmp()
    f = F.Falso(estados=["processing", "processing", "success"])
    r = F.cliente(f, d).gerar(F.pedido(d))
    assert r.status == "success" and f.n("videoInference") == 1 and f.n("getResponse") == 3
    job = json.load(open(r.local_path + ".runware.json", encoding="utf-8"))
    assert job["estado"] == "succeeded" and job["taskUUID"] == r.task_uuid and job["custo_usd"] == 0.35


def test_timeout_e_reinicio_retomam_o_mesmo_job_sem_cobrar_de_novo():
    d = tmp()
    relogio = iter([0, 0, 400, 400, 400, 400])
    f = F.Falso(estados=["processing"] * 3 + ["success"])
    c = rw.Cliente(transporte=f, dormir=lambda s: None, relogio=lambda: next(relogio), abrir=F.abrir_falso(), mem=d,
                   cfg={"poll_initial_seconds": 0, "poll_max_seconds": 0, "max_poll_minutes": 5})
    req = F.pedido(d)
    e = erro(lambda: c.gerar(req))
    assert e.tipo == "timeout_ambiguo" and e.job_remoto
    job = json.load(open(req.saida + ".runware.json", encoding="utf-8"))
    assert job["estado"] == "processing"
    r = F.cliente(f, d).gerar(req)  # "reinício": novo cliente, mesmo pedido
    assert r.status == "success" and r.task_uuid == e.job_remoto and f.n("videoInference") == 1


def test_cache_identico_volta_do_disco_com_custo_zero():
    d = tmp()
    f = F.Falso(imediato=True)
    c = F.cliente(f, d)
    req = F.pedido(d)
    c.gerar(req)
    req2 = F.pedido(d, saida=os.path.join(d, "copia.mp4"), first_frame_path=req.first_frame_path)
    r = c.gerar(req2)
    assert r.cache and r.cost_usd == 0.0 and os.path.isfile(r.local_path) and f.n("videoInference") == 1


def test_custo_desconhecido_fica_none_nunca_zero():
    d = tmp()
    r = F.cliente(F.Falso(imediato=True, custo=None), d).gerar(F.pedido(d))
    assert r.status == "success" and r.cost_usd is None


def test_envio_sem_resposta_vira_cobranca_indeterminada_e_bloqueia_reenvio():
    d = tmp()
    f = F.Falso(erro_envio=rw.ErroRunware("transitorio", "rede: timed out"))
    c = F.cliente(f, d)
    req = F.pedido(d)
    e = erro(lambda: c.gerar(req))
    assert e.tipo == "timeout_ambiguo"
    assert json.load(open(req.saida + ".runware.json", encoding="utf-8"))["estado"] == "unknown_billing"
    f.erro_envio = None
    e2 = erro(lambda: c.gerar(req))
    assert e2.tipo == "timeout_ambiguo" and f.n("videoInference") == 1  # não reenviou


def test_job_com_erro_nao_cobra_e_tipifica():
    d = tmp()
    e = erro(lambda: F.cliente(F.Falso(estados=["error"]), d).gerar(F.pedido(d)))
    assert e.cobrado is False and e.job_remoto


def test_download_so_https_de_dominio_permitido():
    for url in ("http://vm.runware.ai/x.mp4", "https://evil.example.com/x.mp4", "file:///C:/Windows/win.ini", "https://runware.ai.evil.com/x"):
        try:
            rw.host_ok(url)
            raise AssertionError(f"aceitou {url}")
        except rw.ErroRunware:
            pass
    assert rw.host_ok("https://vm.runware.ai/v/x.mp4") and rw.host_ok("https://im.runware.ai/i.png")


def test_lipsync_sobe_audio_por_mediastorage_uma_vez():
    d = tmp()
    f = F.Falso(imediato=True)
    c = F.cliente(f, d)
    a = F.wav(d)
    img = F.png(d)
    for k in range(2):
        c.gerar(F.pedido(d, kind="lipsync", mode="image_audio_to_video", model_air="klingai:avatar@2.0-standard", audio_path=a,
                         first_frame_path=img, duration_seconds=None, positive_prompt=f"fala {k}", saida=os.path.join(d, f"l{k}.mp4")))
    assert f.n("mediaStorage") == 1  # mediaUUID em cache por sha256
    t = [x for x in f.tarefas if x["taskType"] == "videoInference"][0]
    assert t["inputs"]["audio"] == "11111111-2222-3333-4444-555555555555" and t["inputs"]["image"].startswith("data:image/png;base64,")


def test_chave_nunca_aparece_em_erro_nem_log():
    d = tmp()
    os.environ[rw.KEY_ENV] = "rwkTESTE1234567890abcdefXYZ"
    try:
        e = rw.ErroRunware("credencial", "falhou com rwkTESTE1234567890abcdefXYZ e Bearer rwkTESTE1234567890abcdefXYZ")
        assert "rwkTESTE" not in str(e)
        c = F.cliente(F.Falso(imediato=True), d)
        c.log({"evento": "teste", "detalhe": "chave rwkTESTE1234567890abcdefXYZ"})
        c.gerar(F.pedido(d))
        txt = open(os.path.join(d, "runware-log.jsonl"), encoding="utf-8").read()
        assert "rwkTESTE" not in txt and "positivePrompt" not in txt  # prompt também não vai para o log
    finally:
        os.environ.pop(rw.KEY_ENV, None)


def test_saldo_operacao_nao_gerativa():
    d = tmp()
    f = F.Falso()
    r = F.cliente(f, d).conta()
    assert f.chamadas == ["accountManagement"] and r["balance"]["freeBalance"] == 2.0


if __name__ == "__main__":
    F.rodar(globals())
