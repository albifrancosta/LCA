"""Testes de aceite da auditoria (P01–P18, P25–P33, P41/P56 lado do inspetor) — sem rede, sem API paga, em pastas temporárias.
Rodar:  python tests/test_contrato_qa.py        (também roda com pytest)
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import types
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
PY = sys.executable
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

import contrato  # noqa: E402
import integridade as ig  # noqa: E402
import movimento  # noqa: E402
import prompt_clipe  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")



def silencioso(f, *a, **k):
    with redirect_stdout(io.StringIO()):
        return f(*a, **k)


def plano(pid="p1", **direcao):
    c = {"modo": "acao", "duracao": 3.0, "quem": ["tiago"], "acao": "recua", "voz": "off", "enquadramento": "PM", "camera": "fixa",
         "quadro_inicial": "a", "quadro_final": "b", "criterios": ["x"]}
    c.update(direcao)
    return {"id": pid, "quem": ["tiago"], "direcao": c}


BEATS_OK = [{"ate": 1.0, "fase": "acao", "en": "he flinches", "evidencia": "recua"},
            {"ate": 2.0, "fase": "consequencia", "en": "water hits him", "evidencia": "molha"},
            {"ate": 3.0, "fase": "reacao", "en": "he blinks", "evidencia": "pisca"}]


def roteiro_tmp(planos):
    td = tempfile.mkdtemp(prefix="t-contrato-")
    arq = os.path.join(td, "roteiro.json")
    json.dump({"planos": planos}, open(arq, "w", encoding="utf-8"))
    return arq


def mp4(arq, segundos=1.0, cor="testsrc"):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{cor}=size=160x284:rate=8:duration={segundos}",
                    "-pix_fmt", "yuv420p", arq], check=True)


def png(arq, cor=(200, 100, 50)):
    from PIL import Image
    os.makedirs(os.path.dirname(arq) or ".", exist_ok=True)
    Image.new("RGB", (64, 96), cor).save(arq)


# ---------------- contrato (P01, P09) ----------------
def test_p01_acao_sem_beats_falha():
    arq = roteiro_tmp([plano()])
    assert silencioso(contrato.validar, arq) is False
    r = subprocess.run([PY, str(SCRIPTS / "contrato.py"), "validar", arq], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    assert r.returncode != 0


def test_p01_beats_validos_passam():
    arq = roteiro_tmp([plano(beats=BEATS_OK, exige=["tronco", "bracos"], fisica="água → recuo")])
    assert silencioso(contrato.validar, arq) is True


def test_p01_beats_regressivos_lacuna_e_curtos_falham():
    for bs in ([{"ate": 2.5, "fase": "acao", "en": "a"}, {"ate": 1.0, "fase": "reacao", "en": "b"}],    # regressivo
               [{"ate": 1.0, "fase": "acao", "en": "a"}, {"ate": 1.5, "fase": "reacao", "en": "b"}],    # acaba antes do fim
               [{"inicio": 0, "fim": 1, "fase": "acao", "en": "a"}, {"inicio": 2, "fim": 3, "fase": "reacao", "en": "b"}],  # lacuna
               [{"ate": 1.5, "fase": "acao", "en": ""}, {"ate": 3, "fase": "reacao", "en": "b"}],       # ação vazia
               [{"ate": 1.5, "fase": "voar", "en": "a"}, {"ate": 3, "fase": "reacao", "en": "b"}]):     # fase inválida
        arq = roteiro_tmp([plano(beats=bs, exige=["tronco"])])
        assert silencioso(contrato.validar, arq) is False, bs


def test_antecipacao_sutil_nao_reprova():
    import atuacao
    pares = [{"t": i / 8, "dentro": (0.11 if i < 8 else 0.45), "fora": 0.01} for i in range(24)]
    bs = [{"ate": 1, "fase": "antecipacao", "en": "a"}, {"ate": 2, "fase": "acao", "en": "b"}, {"ate": 3, "fase": "reacao", "en": "c"}]
    r = atuacao.resumo(pares, [_det()] * 25, [1] * 25, [], bs)
    assert r["estado"] == ig.APROVADO, r["problemas"]
    pares[0:8] = [{"t": i / 8, "dentro": 0.0, "fora": 0.01} for i in range(8)]  # parada de verdade continua reprovando
    assert atuacao.resumo(pares, [_det()] * 25, [1] * 25, [], bs)["estado"] == ig.REPROVADO


def test_p18_pausa_explicita_e_aceita():
    bs = [{"ate": 1.0, "fase": "acao", "en": "a"}, {"ate": 2.0, "fase": "pausa", "en": "holds still, breathing"},
          {"ate": 3.0, "fase": "reacao", "en": "b"}]
    assert silencioso(contrato.validar, roteiro_tmp([plano(beats=bs, exige=["cabeca"])])) is True


def test_p09_rota_respeita_duracao():
    r = contrato.rota_de(plano(duracao=10.2), ".")
    assert r["rota"] == "clipe_longo" and contrato.preco_rota(r) is not None
    r = contrato.rota_de(plano(duracao=16), ".")
    assert r["rota"] == "dividir" and contrato.preco_rota(r) is None
    assert contrato.preco_rota({"rota": "clipe", "dur": 10.2}) is None  # 2.6 não faz 10,2 s


# ---------------- prompt_clipe (P30–P33) ----------------
def clipe(etapas, dur=3):
    return {"id": "p1", "clipe": {"duracao": dur, "inicio": "i", "fim": "f", "etapas": etapas}}


def test_p30_p31_p33_timeline_estrita():
    assert prompt_clipe.checar([clipe([{"camera": "parada", "acao": "olha", "ate": 2.5}, {"camera": "parada", "acao": "reage", "ate": 1.0}])])[0]
    assert prompt_clipe.checar([clipe([{"camera": "parada", "acao": "", "ate": 3}])])[0]
    assert prompt_clipe.checar([clipe([{"camera": "parada", "acao": "caminha", "ate": 1}], dur=5)])[0]
    assert not prompt_clipe.checar([clipe([{"camera": "parada", "acao": "caminha", "ate": 3}])])[0]


def test_p32_continuidade_entre_planos():
    a = {"id": "p1", "clipe": {"duracao": 2, "inicio": "na sala", "fim": "rapaz sai da sala", "etapas": [{"camera": "parada", "acao": "anda", "ate": 2}]}}
    b = {"id": "p2", "clipe": {"duracao": 2, "inicio": "rapaz dentro da sala", "fim": "senta", "etapas": [{"camera": "dolly-in", "acao": "senta", "ate": 2}]}}
    assert prompt_clipe.checar([a, b])[0]
    b["clipe"]["transicao_intencional"] = True
    assert not prompt_clipe.checar([a, b])[0]


# ---------------- movimento / atuação (P08, P15, P16, P18) ----------------
def test_p08_fade_de_luz_nao_e_animacao():
    a = np.zeros((200, 200), np.uint8)
    b = np.full((200, 200), 128, np.uint8)
    assert movimento.par(a, b)["classe"] != "animado"


def _det():
    return {"caixa": np.array([0, 0, 10, 20]), "kp": np.zeros((17, 2)), "kc": np.zeros(17), "mask": None}


def test_p15_p16_sem_dados_e_nao_verificado():
    import atuacao
    r = atuacao.resumo([], [None] * 8, [0] * 8, ["cabeca", "bracos"])
    assert r["estado"] == ig.NAO_VERIFICADO and r["nota_atuacao"] is None
    r = atuacao.resumo([{"t": i / 8} for i in range(7)], [_det()] * 8, [1] * 8, [])
    assert r["estado"] == ig.NAO_VERIFICADO and r["nota_atuacao"] is None


def test_p18_beat_parado_reprova_pausa_nao():
    import atuacao
    pares = [{"t": i / 8, "dentro": (0.2 if i < 8 or i >= 16 else 0.0), "fora": 0.01} for i in range(24)]
    bs_acao = [{"ate": 1, "fase": "acao", "en": "a"}, {"ate": 2, "fase": "acao", "en": "b"}, {"ate": 3, "fase": "reacao", "en": "c"}]
    r = atuacao.resumo(pares, [_det()] * 25, [1] * 25, [], bs_acao)
    assert r["estado"] == ig.REPROVADO, r["problemas"]
    bs_pausa = [{"ate": 1, "fase": "acao", "en": "a"}, {"ate": 2, "fase": "pausa", "en": "b"}, {"ate": 3, "fase": "reacao", "en": "c"}]
    r = atuacao.resumo(pares, [_det()] * 25, [1] * 25, [], bs_pausa)
    assert r["estado"] == ig.APROVADO, r["problemas"]


# ---------------- inspetor (P02, P06, P07, P11, P41, P56) ----------------
def test_p02_visual_pendente_nao_aprova():
    import inspetor
    td = tempfile.mkdtemp()
    itens = [{"id": "p1", "problemas": [], "pendencias": ["revisão visual"], "estado": ig.NAO_VERIFICADO}]
    rep, nv = silencioso(inspetor.relatorio, os.path.join(td, "entrega", "inspecao-planos.md"), "x", itens)
    assert not rep and [i["id"] for i in nv] == ["p1"]
    assert ig.estado_inspecao(td, "p1")[0] == ig.NAO_VERIFICADO


def test_p02_revisar_nao_derruba_reprovacao_objetiva():
    import inspetor
    td = tempfile.mkdtemp()
    c1, c2 = os.path.join(td, "assets", "clips", "p1.mp4"), os.path.join(td, "assets", "clips", "p2.mp4")
    mp4(c1)
    mp4(c2, cor="testsrc2")
    itens = [{"id": "p1", "problemas": [("grave", "CONGELADO")], "estado": ig.REPROVADO, "sha256_clipe": ig.sha256(c1)},
             {"id": "p2", "problemas": [], "pendencias": ["visual"], "estado": ig.NAO_VERIFICADO, "sha256_clipe": ig.sha256(c2)}]
    silencioso(inspetor.relatorio, os.path.join(td, "entrega", "inspecao-planos.md"), "x", itens)
    try:
        silencioso(inspetor.revisar, td, ["p1"], ig.APROVADO, "parece ok")
        raise AssertionError("aprovou plano com reprovação objetiva")
    except SystemExit:
        pass
    silencioso(inspetor.revisar, td, ["p2"], ig.APROVADO, "ação confere na folha")
    assert ig.estado_inspecao(td, "p2", c2)[0] == ig.APROVADO
    mp4(c2, segundos=2.0)  # clipe trocado depois da revisão → não vale mais
    assert ig.estado_inspecao(td, "p2", c2)[0] == ig.NAO_VERIFICADO


def test_p07_fala_sem_wav_reprova():
    import inspetor
    out = silencioso(inspetor.inspecionar_audio, tempfile.mkdtemp(), {"planos": [{"id": "p1", "fala": "oi tudo bem"}]})
    assert out and out[0]["estado"] == ig.REPROVADO


def _filme(inspetor, ouvidas):
    inspetor.palavras = lambda arq, ini=0.0, fim=None: ouvidas
    inspetor.movimento = types.SimpleNamespace(analisar=lambda v: ({}, [], []), veredito=lambda pares: {"veredito": "animado"})


def test_p06_p11_p56_plano_ausente_e_legenda_errada():
    import importlib
    import inspetor
    importlib.reload(inspetor)
    td = tempfile.mkdtemp()
    os.makedirs(os.path.join(td, "remotion", "src"))
    h = {"planos": [{"id": "p1", "inicio": 0, "fim": 2}], "legenda": [{"text": "cachorro", "start": 0.2}, {"text": "amarelo", "start": 1.0}]}
    json.dump(h, open(os.path.join(td, "remotion", "src", "historia.json"), "w", encoding="utf-8"))
    _filme(inspetor, [(0.2, 0.5, "gato"), (1.0, 1.3, "azul")])
    res, err = inspetor.inspecionar_filme(td, {"planos": [{"id": "p1"}, {"id": "p2"}]}, "x.mp4")
    por = {r["id"]: r for r in res}
    assert por["p2"]["estado"] == ig.REPROVADO                       # plano fora da montagem
    assert por["p1"]["estado"] == ig.REPROVADO and len(err) == 2     # 2 palavras erradas no mesmo plano


def test_p41_inspetor_le_video_json():
    import importlib
    import inspetor
    importlib.reload(inspetor)
    td = tempfile.mkdtemp()
    os.makedirs(os.path.join(td, "remotion", "src"))
    json.dump({"cenas": [{"id": "s1", "inicio": 0, "fim": 1}], "legenda": {"palavras": []}},
              open(os.path.join(td, "remotion", "src", "video.json"), "w", encoding="utf-8"))
    _filme(inspetor, [])
    res, _ = inspetor.inspecionar_filme(td, {"planos": [{"id": "s1"}]}, "x.mp4")
    assert res[0]["estado"] == ig.APROVADO


# ---------------- bíblia / orquestrador (P03, P04, P05, P10, P13, P25, P26, P29) ----------------
def projeto_tmp():
    td = tempfile.mkdtemp(prefix="t-prod-")
    d = {"titulo": "t", "estilo": "", "formato": "9:16", "personagens": {}, "cenarios": {}, "objetos": {}, "historico": [],
         "tomadas": [{"id": "t01", "status": "aguardando", "personagens": [], "objetos": [], "clipe": True,
                      "decupagem": {"plano": "medio"}, "versoes": []}]}
    json.dump(d, open(os.path.join(td, "producao.json"), "w", encoding="utf-8"))
    return td


def cli(td, *args):
    return subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, cwd=td)


def test_p25_p03_aprovar_sem_imagem_recusa():
    td = projeto_tmp()
    assert cli(td, str(SCRIPTS / "producao.py"), "status", "t01", "aprovada").returncode != 0
    assert cli(td, str(SCRIPTS / "orquestrador.py"), "aprovar", "t01").returncode != 0
    assert json.load(open(os.path.join(td, "producao.json"), encoding="utf-8"))["tomadas"][0]["status"] != "aprovada"


def test_p29_versao_vazia_recusada():
    td = projeto_tmp()
    Path(td, "vazio.png").write_bytes(b"")
    assert cli(td, str(SCRIPTS / "producao.py"), "versao", "t01", "vazio.png").returncode != 0


def test_p04_p10_imagem_nova_invalida_clipe_e_exige_inspecao():
    import orquestrador
    td = projeto_tmp()
    png(os.path.join(td, "i1.png"))
    mp4(os.path.join(td, "c1.mp4"))
    assert cli(td, str(SCRIPTS / "producao.py"), "versao", "t01", "i1.png").returncode == 0
    assert cli(td, str(SCRIPTS / "producao.py"), "versao", "t01", "c1.mp4", "--tipo", "clipe").returncode == 0
    d = json.load(open(os.path.join(td, "producao.json"), encoding="utf-8"))
    assert orquestrador.valida(d["tomadas"][0], "clipe") is not None
    png(os.path.join(td, "i2.png"), (10, 200, 10))
    assert cli(td, str(SCRIPTS / "producao.py"), "versao", "t01", "i2.png").returncode == 0
    d = json.load(open(os.path.join(td, "producao.json"), encoding="utf-8"))
    t = d["tomadas"][0]
    assert orquestrador.valida(t, "clipe") is None  # clipe da imagem v1 não vale para a v2
    img = t["versoes"][-1]
    img["continuidade"] = {"ok": True}
    t["status"] = "aprovada"
    t["versoes"].append({"v": 9, "tipo": "clipe", "arquivo": "c1.mp4", "continuidade": {"ok": True}, "cor": True, "qa": ig.NAO_VERIFICADO,
                         "origem": {"imagem_v": img["v"], "imagem_sha256": img["sha256"]}})
    assert orquestrador.etapa(d, t)[1] == "inspecionar_clipe"  # sem QA aprovado nunca fica "pronta"


def test_p05_orcamento_reserva_cumulativa():
    import orquestrador
    d = {"titulo": "t", "personagens": {"a": {}, "b": {}}, "cenarios": {}, "objetos": {}, "orcamento": {"aprovado": 0.07},
         "tomadas": [{"id": "t1", "status": "x", "decupagem": {"plano": "m"}, "personagens": ["a"], "versoes": []},
                     {"id": "t2", "status": "x", "decupagem": {"plano": "m"}, "personagens": [], "versoes": []}]}
    pagos = [g for g in orquestrador.planejar(d)[0] if g["custo"] > 0]
    assert len(pagos) == 2 and sum(not g["precisa_orcamento"] for g in pagos) == 1


def test_p26_conflito_de_escrita():
    import producao
    td = projeto_tmp()
    arq = os.path.join(td, "producao.json")
    a = json.load(open(arq, encoding="utf-8"))
    b = json.load(open(arq, encoding="utf-8"))
    producao.salvar(arq, a, "agente A")
    try:
        producao.salvar(arq, b, "agente B")
        raise AssertionError("sobrescreveu a gravação do agente A")
    except SystemExit:
        pass


def test_p13_beats_viram_etapas():
    import producao
    t = {"acao": "recua", "decupagem": {"movimento": "static", "inicio": "a", "fim": "b"}, "direcao": {"duracao": 3, "beats": BEATS_OK}}
    c = producao.clipe_roteiro(t)
    assert [e["ate"] for e in c["etapas"]] == [1.0, 2.0, 3.0]
    assert not prompt_clipe.checar([{"id": "t", "clipe": c}])[0]


def test_midia_vazia_invalida():
    td = tempfile.mkdtemp()
    Path(td, "x.mp4").write_bytes(b"")
    assert not ig.midia_valida(os.path.join(td, "x.mp4"))[0]
    mp4(os.path.join(td, "y.mp4"))
    assert ig.midia_valida(os.path.join(td, "y.mp4"))[0]


def main():
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    falhas = 0
    for n, f in testes:
        try:
            f()
            print(f"PASS {n}")
        except BaseException as e:  # noqa: BLE001 — SystemExit inesperado também é falha
            falhas += 1
            print(f"FAIL {n}: {type(e).__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
