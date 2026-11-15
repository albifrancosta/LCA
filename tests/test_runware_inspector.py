"""Inspeção dos takes vindos da Runware: sem inspetor visual = não verificado (nunca aprovado), mídia inválida reprova,
zoom sobre foto não é atuação, relatório por take e versão, montagem bloqueia clipe não verificado.
Sem rede, sem crédito. Rodar: python tests/test_runware_inspector.py"""
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import runware_falso as F  # noqa: E402
import provedores as pv  # noqa: E402
import integridade as ig  # noqa: E402
import inspetor  # noqa: E402
import movimento  # noqa: E402


def tmp():
    return tempfile.mkdtemp(prefix="rwi-")


def test_sem_inspetor_visual_fica_nao_verificado():
    d = tmp()
    clip = os.path.join(d, "c.mp4")
    open(clip, "wb").write(F.mp4_real())
    q = pv.inspecionar_padrao(clip, {"task_type": "video", "requirements": {}})
    assert q["estado"] == ig.NAO_VERIFICADO and q["estado"] != ig.APROVADO


def test_midia_invalida_reprova():
    d = tmp()
    ruim = os.path.join(d, "ruim.mp4")
    open(ruim, "wb").write(b"<html>erro</html>")
    q = pv.inspecionar_padrao(ruim, {"task_type": "video", "requirements": {}})
    assert q["aceito"] is False and q["estado"] == ig.REPROVADO


def test_zoom_sobre_foto_nao_e_atuacao():
    d = tmp()
    foto = F.png(d, "foto.png", 640, 360)
    zoom = os.path.join(d, "zoom.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", foto, "-vf",
                    "zoompan=z='min(zoom+0.004,1.3)':d=75:s=640x360,format=yuv420p", "-t", "3", "-r", "25", zoom], check=True)
    v, _, _ = movimento.analisar(zoom)
    assert v.get("veredito") != "animado", v  # só câmera/parado: o inspetor reprova plano de atuação com isso


def test_relatorio_por_take_e_versao():
    d = tmp()
    arq = os.path.join(d, "entrega", "inspecao-planos.md")
    item = {"id": "c05a", "sha256_clipe": "abcdef1234567890" * 4, "problemas": [["grave", "boca parada"]], "pendencias": [],
            "veredito": "reprovado", "revisao_visual": {"pendente": True, "motivo": "sem Gemini"}}
    inspetor.relatorio(arq, "teste", [item])
    j = json.load(open(os.path.join(d, "entrega", "inspecao", "c05a-abcdef12.json"), encoding="utf-8"))
    assert j["versao"] == "abcdef12" and j["estado"] == ig.REPROVADO and j["inspetor_visual"].startswith("nenhum")
    assert os.path.isfile(os.path.join(d, "entrega", "inspecao", "c05a-abcdef12.md"))


def test_clipe_sem_inspecao_nao_esta_aprovado_para_montagem():
    d = tmp()
    clip = os.path.join(d, "assets", "clips", "x.mp4")
    os.makedirs(os.path.dirname(clip))
    open(clip, "wb").write(F.mp4_real())
    assert ig.estado_inspecao(d, "x", clip)[0] == ig.NAO_VERIFICADO


def test_watch_ausente_e_registrado_sem_aprovacao_tacita():
    # o Watch MCP não está instalado (o usuário optou por não instalar, 2026-11-06); o inspetor usa o Gemini e, sem ele,
    # a revisão visual fica pendente → não verificado. Nunca há aprovação por omissão.
    q = pv.inspecionar_padrao(F.png(tmp()), {"task_type": "imagem", "requirements": {}})
    assert q["estado"] == ig.NAO_VERIFICADO


if __name__ == "__main__":
    F.rodar(globals())
