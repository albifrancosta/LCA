"""Testes do roteador inteligente de vídeo (descoberta, pontuação, níveis grátis→crédito→pago, adaptadores padronizados,
retomada de job pago, aprendizado pelo inspetor, progresso e resumo). Sem rede e sem custo: HTTP, Gradio e relógio FALSOS.
Rodar:  python tests/test_roteador_video.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import progresso as prog  # noqa: E402
import provedores as pv  # noqa: E402
import provedores_video as pvv  # noqa: E402
import provider_discovery as pd  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Pulado(Exception):
    """Teste pulado: depende de um pacote opcional que não está instalado."""


def requer(modulo):
    import importlib.util
    try:
        achou = importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        achou = False
    if not achou:
        raise Pulado(f"precisa de {modulo} (opcional: pip install {modulo.replace('_', '-')})")


REGRAS = {"ativo": True, "routing": {"policy": "pontuacao", "politicas_validas": ["free_first", "pontuacao", "best_value", "lowest_cost", "manual"],
                                     "allow_paid_fallback": True, "retry": {"max_attempts_per_provider": 1, "backoff_base_s": 0.01, "backoff_max_s": 0.02},
                                     "circuit_breaker": {"falhas_para_abrir": 3, "esfriar_s": 600}},
          "budget": {"max_cost_per_operation": 5, "max_cost_per_video": 50, "default_unknown_cost_policy": "block", "margem_seguranca": 0},
          "quality": {"final": "high", "preview": "standard"},
          "api_router": {"prefer_free": True, "allow_promo_credits": True, "require_paid_approval": True,
                         "pontuacao": {"pesos": {"qualidade": 0.3, "custo": 0.25, "compatibilidade": 0.2, "disponibilidade": 0.15, "consistencia": 0.1},
                                       "custo_referencia_por_s": 0.2}}}


def mp4(arq, dur=1.0):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=160x90:rate=24:duration={dur}", "-pix_fmt", "yuv420p", arq], check=True)
    return arq


def png(arq):
    from PIL import Image
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    Image.new("RGB", (64, 64), (200, 100, 50)).save(arq)
    return arq


def prov(pid, preco, adaptador, quality="standard", perfil=None, **k):
    p = {"id": pid, "enabled": True, "stage": "video", "adaptador": adaptador, "model": pid, "tier": "free" if preco == 0 else "paid",
         "commercial_use": "allowed", "languages": ["*"], "capabilities": ["video", "i2v"], "quality": quality, "referencias_preservadas": True,
         "price": {"unit": "second", "amount_per_unit": preco}, "perfil": perfil or {}}
    p.update(k)
    return p


class Mem:
    def __init__(self, provs=(), regras=None):
        self.provs, self.regras = list(provs), regras or REGRAS

    def __enter__(self):
        self.td = tempfile.mkdtemp(prefix="rv-")
        self.salvo = (pv.CFG_PROV, pv.CFG_ROT, pv.MEM, pd.ARQ)
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = (os.path.join(self.td, "p.json"), os.path.join(self.td, "r.json"), os.path.join(self.td, "mem"))
        pd.ARQ = os.path.join(self.td, "descoberta.json")
        json.dump({"provedores": self.provs}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        json.dump(self.regras, open(pv.CFG_ROT, "w", encoding="utf-8"))
        pvv.FABRICAS.clear()
        return self

    def __exit__(self, *a):
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM, pd.ARQ = self.salvo
        pvv.FABRICAS.clear()


def executar(t):
    return pv.executar(t, adaptadores=pvv.registrar({}), inspecionar=lambda s, t: {"aceito": True, "estado": "aprovado", "motivo": "ok"},
                       dormir=lambda s: None, credencial=lambda e: True)


# ---------------------------------------------------------------- descoberta
class ClienteFalso:
    def __init__(self, endpoints, limites=None):
        self.endpoints = endpoints
        self.config = {"components": [{"type": "slider", "props": {"label": k, "minimum": a, "maximum": b}} for k, (a, b) in (limites or {}).items()]}

    def view_api(self, **k):
        return {"named_endpoints": {n: {"parameters": [{"parameter_name": x} for x in ps]} for n, ps in self.endpoints.items()}}


def _get(stage="RUNNING", hw="zero-a10g", lic=None):
    return lambda url: {"runtime": {"stage": stage, "hardware": {"current": hw}}, "cardData": {"license": lic}}


SPACE = prov("hf-x", 0, "GradioSpace", space="u/x", gradio={"api_name": "/generate_video", "prompt": "prompt", "imagem": "input_image",
                                                           "duracao": "duration_seconds"}, faixa_duracao=[0.5, 5.0])


def test_descoberta_classifica_sem_inventar():
    ok_cli = lambda p: ClienteFalso({"/generate_video": ["input_image", "prompt", "duration_seconds"]}, {"Duration (seconds)": (0.5, 5)})  # noqa: E731
    f = pd.classificar(SPACE, get=_get(), cliente_de=ok_cli)
    assert f["categoria"] == "gratis_api" and "ZeroGPU" in f["motivo"] and f["limites"]["Duration (seconds)"] == [0.5, 5]
    assert pd.classificar(SPACE, get=_get("SLEEPING"), cliente_de=ok_cli)["categoria"] == "nao_confirmado"  # não acordamos
    assert pd.classificar(SPACE, get=_get("RUNTIME_ERROR"), cliente_de=ok_cli)["categoria"] == "indisponivel"
    assert pd.classificar(SPACE, get=_get(hw="cpu-basic"), cliente_de=ok_cli)["categoria"] == "nao_confirmado"  # vídeo em CPU
    mudou = lambda p: ClienteFalso({"/generate_video": ["image", "prompt", "duration_seconds"]})  # noqa: E731
    assert "parâmetros mudaram" in pd.classificar(SPACE, get=_get(), cliente_de=mudou)["motivo"]
    assert pd.classificar(SPACE, get=_get(), cliente_de=lambda p: ClienteFalso({"/outro": ["x"]}))["categoria"] == "nao_confirmado"
    assert pd.classificar(SPACE, get=_get(), cliente_de=lambda p: ClienteFalso({}))["categoria"] == "gratis_web"
    pago = prov("ltx", 0.03, "LTXApi", credencial_env="LTX_API_KEY")
    assert pd.classificar(pago, tem_credencial=lambda e: False)["categoria"] == "sem_credencial"
    assert pd.classificar(pago, tem_credencial=lambda e: True)["categoria"] == "pago_api"
    assert pd.classificar(prov("plus", None, "AlibabaWan", credencial_env="K"), tem_credencial=lambda e: True)["categoria"] == "nao_confirmado"
    promo = prov("promo", 0.05, "AlibabaWan", credencial_env="K", creditos_promocionais={"saldo": 50, "valido_ate": "2099-01-01"})
    assert pd.classificar(promo, tem_credencial=lambda e: True)["categoria"] == "credito_promocional"


def test_indisponivel_na_descoberta_fica_de_fora_do_roteador():
    with Mem([SPACE, prov("pago", 0.07, "GradioSpace", quality="high")]):
        pd.descobrir({"provedores": [SPACE]}, get=_get("RUNTIME_ERROR"), cliente_de=lambda p: ClienteFalso({}))
        t = pv.normalizar({"job_id": "j", "scene_id": "s", "task_type": "video", "mode": "preview", "requirements": {"duration_s": 2}}, REGRAS)
        fila, rej = pv.candidatos(t, pv.config()[0], pvv.registrar({}), credencial=lambda e: True)
        assert [p["id"] for p, _ in fila] == ["pago"] and any("descoberta" in r["motivo"] for r in rej)


# ---------------------------------------------------------------- pontuação e níveis
def test_pontuacao_por_tipo_de_take_e_niveis():
    provs = [prov("gratis", 0, "GradioSpace", perfil={"simples": 0.8, "fala": 0.1}),
             prov("avatar", 0.056, "GradioSpace", quality="high", perfil={"fala": 0.95, "simples": 0.2}),
             prov("kling", 0.07, "GradioSpace", quality="high", perfil={"fala": 0.3, "simples": 0.6, "i2v_personagem": 0.8}),
             prov("promo", 0.10, "GradioSpace", quality="high", perfil={"simples": 0.5}, creditos_promocionais={"saldo": 30, "valido_ate": "2099-01-01"})]
    with Mem(provs):
        cat = pv.config()[0]

        def ordem(tipo):
            t = pv.normalizar({"job_id": "j", "scene_id": "s", "task_type": "video", "requirements": {"duration_s": 5, "tipo_take": tipo}}, REGRAS)
            return [p["id"] for p, _ in pv.candidatos(t, cat, pvv.registrar({}), credencial=lambda e: True)[0]]
        assert ordem("simples") == ["gratis", "promo", "kling", "avatar"]  # grátis → crédito → pago (a nota decide dentro do nível)
        assert ordem("fala")[:2] == ["promo", "avatar"] and "gratis" not in ordem("fala")  # standard não entra em take final
        t = pv.normalizar({"job_id": "j", "task_type": "video", "requirements": {"duration_s": 5, "tipo_take": "fala"}}, REGRAS)
        assert pv.pontuar(provs[1], 0.28, t) > pv.pontuar(provs[2], 0.35, t)  # perfil de fala pesa
        so_compat = {"qualidade": 0, "custo": 0, "compatibilidade": 1, "disponibilidade": 0, "consistencia": 0}
        t2 = pv.normalizar({"job_id": "j", "task_type": "video", "requirements": {"duration_s": 5, "tipo_take": "i2v_personagem"}}, REGRAS)
        assert pv.pontuar(provs[2], 0.35, t2, pesos=so_compat) > pv.pontuar(provs[1], 0.28, t2, pesos=so_compat)  # pesos configuráveis


def test_classificar_take():
    assert pv.classificar_take({"modo": "titulo"}) == "motion"
    assert pv.classificar_take({"voz": "em_quadro", "quem": ["a"]}) == "fala"
    assert pv.classificar_take({"modo": "acao", "quem": ["a"]}) == "i2v_personagem"
    assert pv.classificar_take({"camera": "travelling lateral (dolly)"}) == "cinematografico"
    assert pv.classificar_take({}) == "simples"


def test_piso_de_qualidade_vem_do_projeto():
    base = tempfile.mkdtemp(prefix="rv-piso-")
    json.dump({"autonomia": {"modo": "custo_zero", "job_id": "p"}}, open(os.path.join(base, "projeto.json"), "w"))
    with Mem([]):
        t = pv.normalizar({"job_id": "p", "task_type": "video", "projeto": base, "requirements": {}}, REGRAS)
        assert t["quality_min"] == "standard"  # custo_zero: pago não existe; quem barra defeito é o inspetor
        json.dump({"autonomia": {"modo": "teto", "job_id": "p"}, "orcamento": {"teto_autorizado": 3}}, open(os.path.join(base, "projeto.json"), "w"))
        assert pv.normalizar({"job_id": "p", "task_type": "video", "projeto": base, "requirements": {}}, REGRAS)["quality_min"] == "high"
        assert pv.normalizar({"job_id": "p", "task_type": "video", "projeto": base, "quality_min": "premium", "requirements": {}}, REGRAS)["quality_min"] == "premium"
    shutil.rmtree(base)


def test_pago_exige_orcamento_configurado():
    regras = json.loads(json.dumps(REGRAS))
    regras["budget"].pop("max_cost_per_video")
    with Mem([], regras):
        t = pv.normalizar({"job_id": "sem-teto", "task_type": "video", "requirements": {}}, regras)
        a = pv.autorizar(t, {"id": "x"}, 0.2, regras)
        assert a["estado"] == "waiting_approval" and "orçamento configurado" in a["motivo"]
        assert pv.autorizar(t, {"id": "x"}, 0.0, regras)["ok"]  # grátis não precisa


class _LTXFalso(pvv.LTXApi):
    def __init__(self, p, td, codigo=202):
        self.td, self.codigo, self.chamadas = td, codigo, []
        super().__init__(p, transporte=self._t, dormir=lambda s: None)

    def chave(self):
        return "teste-nao-real"

    def _t(self, metodo, url, corpo=None, cab=None, timeout=45):
        self.chamadas.append((metodo, url, corpo))
        if metodo == "POST":
            return (self.codigo, {"id": "job-9"}) if self.codigo < 300 else (self.codigo, {"error": {"type": "x", "message": "nope"}})
        return 200, {"status": "completed", "result": {"video_url": "https://storage.ltx.io/v.mp4"}}

    def _baixar(self, url, saida, hosts):
        return mp4(saida)


def test_credito_promocional_cobre_e_e_consumido():
    td = tempfile.mkdtemp(prefix="rv-promo-")
    p = prov("promo", 0.10, "LTXApi", quality="high", credencial_env="X", creditos_promocionais={"saldo": 6, "valido_ate": "2099-01-01", "unidade": "segundos"})
    with Mem([p]):
        pvv.FABRICAS["LTXApi"] = lambda pp: _LTXFalso(pp, td)
        t = {"job_id": "j", "scene_id": "s1", "task_type": "video",
             "requirements": {"duration_s": 5, "imagem": png(os.path.join(td, "i.png")), "saida": os.path.join(td, "a.mp4"), "prompt": "x"}}
        assert executar(t)["status"] == "success"
        rs = pv.ler(pv.caminhos()["reservas"], {})["reservas"]
        assert rs and rs[0]["valor"] == 0.0  # coberto pelo crédito: nada reservado em dinheiro
        assert abs(pv.promo_restante(p) - 1.0) < 1e-9  # 6 − 5 s
        assert not pv.promo_cobre(p, 0.5, pv.normalizar(t, REGRAS))  # sobrou 1 s: o próximo take de 5 s já é pago
    shutil.rmtree(td)


def test_provedor_gratis_sobe_de_nivel_por_evidencia_do_inspetor():
    p = prov("hf", 0, "GradioSpace", quality="standard")
    with Mem([p]):
        assert pv.qualidade_efetiva(p) == pv.QUALIDADE["standard"]
        for i, est in enumerate(["aprovado", "aprovado", "aprovado", "reprovado"]):
            pv.registrar_veredito("j", f"s{i}", "hf", est)
        assert pv.qualidade_efetiva(p) == pv.QUALIDADE["high"]  # 4 takes, 75 % → concorre em take final


# ---------------------------------------------------------------- adaptadores padronizados
class _CliGradio:
    def __init__(self, arquivo):
        self.arquivo, self.chamadas = arquivo, []

    def predict(self, **kw):
        self.chamadas.append(kw)
        return (self.arquivo, 42)


def test_gradio_space_gera_e_respeita_faixa_de_duracao():
    requer("gradio_client")
    td = tempfile.mkdtemp(prefix="rv-gr-")
    cli = _CliGradio(mp4(os.path.join(td, "out.mp4")))
    with Mem([SPACE]):
        pvv.FABRICAS["GradioSpace"] = lambda pp: pvv.GradioSpace(pp, cliente=cli)
        t = {"job_id": "j", "scene_id": "s", "task_type": "video", "mode": "preview",
             "requirements": {"duration_s": 3, "imagem": png(os.path.join(td, "i.png")), "saida": os.path.join(td, "s.mp4"), "prompt": "acena"}}
        r = executar(t)
        assert r["status"] == "success" and r["tier_used"] == "free" and os.path.isfile(os.path.join(td, "s.mp4"))
        kw = cli.chamadas[0]
        assert kw["api_name"] == "/generate_video" and kw["prompt"].startswith("acena") and kw["duration_seconds"] == 3.0
        t2 = dict(t, scene_id="s9", requirements=dict(t["requirements"], duration_s=8, saida=os.path.join(td, "s9.mp4")))
        assert executar(t2)["status"] == "sem_provedor" and len(cli.chamadas) == 1  # 8 s > 5 s lido na API: recusa antes de chamar
    shutil.rmtree(td)


class _AliFalso(pvv.AlibabaWan):
    def __init__(self, p, roteiro=("RUNNING", "SUCCEEDED")):
        self.chamadas, self.estados = [], list(roteiro)
        super().__init__(p, transporte=self._t, dormir=lambda s: None)

    def _t(self, metodo, url, corpo=None, cab=None, timeout=45):
        self.chamadas.append((metodo, url, corpo, cab))
        if metodo == "POST":
            return 200, {"output": {"task_id": "tid-1", "task_status": "PENDING"}}
        st = self.estados.pop(0) if self.estados else "RUNNING"
        return 200, {"output": {"task_status": st, "video_url": "https://dashscope-result.oss.aliyuncs.com/v.mp4" if st == "SUCCEEDED" else None}}

    def _baixar(self, url, saida, hosts):
        assert url.startswith("https://") and "aliyuncs.com" in url
        return mp4(saida)


def test_alibaba_assincrono_timeout_vira_pendente_e_retomada_recupera():
    td = tempfile.mkdtemp(prefix="rv-ali-")
    os.environ["DASHSCOPE_BASE_URL"] = "https://ws.ap-southeast-1.maas.aliyuncs.com"
    os.environ["DASHSCOPE_API_KEY"] = "teste-nao-real"
    p = prov("ali", 0.015, "AlibabaWan", quality="high", model="wan2.2-i2v-flash", credencial_env="DASHSCOPE_API_KEY", resolucao_padrao="480P",
             price={"unit": "second", "amount_per_unit": 0.015, "por_resolucao": {"480P": 0.015, "720P": 0.036}}, timeout_s=0)
    try:
        with Mem([p]):
            inst = {}
            pvv.FABRICAS["AlibabaWan"] = lambda pp: inst.setdefault("a", _AliFalso(pp, roteiro=()))
            t = {"job_id": "j", "scene_id": "c07a", "task_type": "video",
                 "requirements": {"duration_s": 5, "imagem": png(os.path.join(td, "i.png")), "saida": os.path.join(td, "c07a.mp4"), "prompt": "x"}}
            r = executar(t)  # timeout_s=0 → não espera: timeout ambíguo
            assert r["status"] == "pendente_verificacao" and r["job_remoto"] == "tid-1"
            post = [c for c in inst["a"].chamadas if c[0] == "POST"]
            assert len(post) == 1 and post[0][3]["X-DashScope-Async"] == "enable" and post[0][2]["model"] == "wan2.2-i2v-flash"
            assert post[0][2]["parameters"] == {"resolution": "480P", "duration": 5, "prompt_extend": False, "watermark": False}
            assert post[0][2]["input"]["img_url"].startswith("data:image/png;base64,")
            assert json.load(open(os.path.join(td, "c07a.mp4.alibaba.json")))["job_id"] == "tid-1"  # gravado ANTES de esperar
            rs = pv.ler(pv.caminhos()["reservas"], {})["reservas"]
            assert abs(rs[0]["valor"] - 0.075) < 1e-9 and rs[0]["estado"] == "reconciliada"  # 5 s × 0,015; desconhecido conta como gasto
            inst.clear()
            pvv.FABRICAS["AlibabaWan"] = lambda pp: inst.setdefault("a", _AliFalso(pp, roteiro=("SUCCEEDED",)))
            r2 = executar(t)  # retomada: consulta o task_id antigo e baixa — nenhum POST novo
            assert r2["status"] == "success" and r2.get("recuperado") and not [c for c in inst["a"].chamadas if c[0] == "POST"]
    finally:
        os.environ.pop("DASHSCOPE_BASE_URL", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)
        shutil.rmtree(td)


def test_ltx_gera_e_erro_de_credencial_nao_cobra():
    td = tempfile.mkdtemp(prefix="rv-ltx-")
    p = prov("ltx", 0.03, "LTXApi", quality="high", model="ltx-2-3-fast", resolucao_padrao="1280x720", credencial_env="X",
             price={"unit": "second", "amount_per_unit": 0.03, "por_resolucao": {"1280x720": 0.03}})
    with Mem([p]):
        pvv.FABRICAS["LTXApi"] = lambda pp: _LTXFalso(pp, td)
        img = png(os.path.join(td, "i.png"))
        t = {"job_id": "j", "scene_id": "s", "task_type": "video", "requirements": {"duration_s": 4, "imagem": img, "saida": os.path.join(td, "s.mp4"), "prompt": "x"}}
        r = executar(t)
        assert r["status"] == "success" and abs(r["estimated_cost_usd"] - 0.12) < 1e-9
        pvv.FABRICAS["LTXApi"] = lambda pp: _LTXFalso(pp, td, codigo=401)
        t2 = dict(t, scene_id="s2", requirements=dict(t["requirements"], saida=os.path.join(td, "s2.mp4"), prompt="y"))
        assert executar(t2)["status"] != "success"
        assert pv.ler(pv.caminhos()["reservas"], {})["reservas"][-1]["estado"] == "liberada"  # 401: nada cobrado
        assert pv.estado_de("ltx").get("credencial_invalida")
    shutil.rmtree(td)


# ---------------------------------------------------------------- progresso e resumo
def test_progresso_informa_tempo_e_porcentagem_de_tempos_em_tempos():
    base = tempfile.mkdtemp(prefix="rv-pg-")
    os.makedirs(os.path.join(base, "entrega"))
    json.dump({"planos": [{"id": "a", "direcao": {"modo": "titulo"}}]}, open(os.path.join(base, "roteiro.json"), "w"))
    agora, linhas = [1000.0], []
    pg = prog.Progresso(base, 4, "geração dos takes", intervalo=0, saida=linhas.append, relogio=lambda: agora[0])
    pg.comecar("c01")
    agora[0] += 120
    pg.passo("c01")
    assert "1/4 · 25%" in linhas[-1] and "2min00s decorridos" in linhas[-1] and "~6min00s restantes" in linhas[-1]
    assert "projeto" in linhas[-1] and "desde o início" in linhas[-1]
    st = json.load(open(os.path.join(base, "entrega", "progresso.json"), encoding="utf-8"))
    assert st["pct_etapa"] == 25.0 and st["restante_s"] == 360.0 and st["inicio_projeto"]
    batidas = []
    with prog.Progresso(base, 2, "teste", intervalo=0.05, saida=batidas.append, com_projeto=False):
        time.sleep(0.3)  # take demorando: o batimento continua avisando
    assert len(batidas) >= 4 and batidas[-1].startswith("⏱ fim")
    shutil.rmtree(base)


def test_resumo_execucao_conta_niveis_custo_e_economia_explicita():
    import resumo_execucao as rx
    base = tempfile.mkdtemp(prefix="rv-rx-")
    os.makedirs(os.path.join(base, "entrega"))
    json.dump({"planos": []}, open(os.path.join(base, "roteiro.json"), "w"))
    json.dump({"autonomia": {"modo": "teto", "job_id": "jx"}, "orcamento": {"teto_autorizado": 5}}, open(os.path.join(base, "projeto.json"), "w"))
    with Mem([prov("fal-kling26-pro", 0.07, "GradioSpace", price={"unit": "second", "amount_per_unit": 0.07, "fonte": "doc oficial"})]):
        v1, v2 = mp4(os.path.join(base, "v1.mp4"), 2.0), mp4(os.path.join(base, "v2.mp4"), 2.0)
        pv.registrar({"tipo": "tentativa", "job_id": "jx", "provedor": "hf", "resultado": "sucesso", "saida": v1, "nivel": "gratis", "estimado_usd": 0, "latencia_ms": 30000})
        pv.registrar({"tipo": "tentativa", "job_id": "jx", "provedor": "fal", "resultado": "sucesso", "saida": v2, "nivel": "pago", "estimado_usd": 0.14, "latencia_ms": 90000})
        pv.registrar({"tipo": "tentativa", "job_id": "jx", "provedor": "fal", "resultado": "erro", "erro_tipo": "cota", "latencia_ms": 1000})
        r = rx.resumo(base)
        assert r["takes_gerados"] == 2 and r["por_nivel"] == {"gratis": 1, "credito_promocional": 0, "pago": 1} and r["tentativas"] == 3
        assert r["falhas_por_tipo"] == {"cota": 1} and r["tempo_processamento_s"] == 121.0
        e = r["economia"]
        assert e["preco_por_s"] == 0.07 and abs(e["segundos"] - 4.0) < 0.2 and e["fonte"] == "doc oficial"
        assert "Economia" in rx.markdown(r)
    shutil.rmtree(base)


def rodar(ns):
    testes = [(k, v) for k, v in ns.items() if k.startswith("test_") and callable(v)]
    ok = 0
    for nome, f in testes:
        try:
            f()
            ok += 1
            print(f"✅ {nome}")
        except Pulado as e:
            ok += 1
            print(f"⏭️  {nome} — pulado: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"❌ {nome} {type(e).__name__}: {e}")
            traceback.print_exc(limit=4)
    print(f"\n{ok}/{len(testes)} passaram")
    sys.exit(0 if ok == len(testes) else 1)


if __name__ == "__main__":
    rodar(globals())
