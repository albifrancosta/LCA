"""Regressão da integração Runware: nada do que existia quebrou (INTEGRACAO-RUNWARE.md §8 / §10).
- as 7 suítes anteriores passam;  - CLIs legadas (gerar_clipe_fal, gerar_imagem, lipsync, provedores) respondem;
- sem RUNWARE_API_KEY o roteador segue no fal (rollback natural);  - adaptadores fal continuam registrados.
Sem rede, sem crédito. Rodar: python tests/test_runware_regression.py"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AQUI, "..", "scripts")
sys.path.insert(0, AQUI)
import runware_falso as F  # noqa: E402
import provedores as pv  # noqa: E402

ANTIGAS = ["test_contrato_qa.py", "test_custos_roteamento.py", "test_montagem.py", "test_roteador_apis.py", "test_autonomo.py",
           "test_conferencia.py", "test_especialistas.py"]
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def test_suites_anteriores_passam():
    falhas = []
    for s in ANTIGAS:
        r = subprocess.run([sys.executable, os.path.join(AQUI, s)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=ENV, timeout=900)
        if r.returncode != 0:
            falhas.append(f"{s}: {(r.stdout + r.stderr).strip().splitlines()[-1]}")
    assert not falhas, falhas


def test_clis_legadas_respondem():
    for cli in ("gerar_clipe_fal.py", "gerar_imagem.py", "lipsync.py", "provedores.py", "gerar_clipe.py", "runware.py"):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, cli), "--help"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=ENV, timeout=120)
        assert r.returncode == 0, (cli, r.stderr[-300:])


def test_adaptadores_antigos_continuam_registrados():
    for a in ("FalClipe", "FalLipsync", "OpenAIImagem", "GeminiTTS", "HFWan", "HFS2V", "VoiceStudio"):
        assert a in pv.ADAPTADORES


def test_sem_chave_runware_o_catalogo_real_segue_no_fal():
    import test_runware_router as R
    with R.Amb(F.Falso(imediato=True)) as a:
        fila, rej = pv.candidatos(pv.normalizar(R.tarefa(a.td), R.REGRAS), {"provedores": [R.REAIS[i] for i in R.IDS]}, pv.ADAPTADORES,
                                  credencial=R.cred("FAL_KEY"))
        assert fila and fila[0][0]["id"].startswith("fal-"), [p["id"] for p, _ in fila]
        assert all("RUNWARE_API_KEY" in x["motivo"] for x in rej if x["provedor"].startswith("runware-"))


if __name__ == "__main__":
    F.rodar(globals())
