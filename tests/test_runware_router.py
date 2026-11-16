"""Roteador com Runware (política runware_primary) — catálogo REAL da skill, provedores com transporte falso.
Sem rede, sem crédito. Rodar: python tests/test_runware_router.py"""
import io
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import runware_falso as F  # noqa: E402
import provedores as pv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


REAIS = {p["id"]: p for p in json.load(io.open(os.path.join(AQUI, "..", "config", "provedores.json"), encoding="utf-8"))["provedores"]}
IDS = ["runware-kling26-pro", "runware-kling3-pro", "fal-kling26-pro", "runware-avatar-std", "runware-omnihuman15", "fal-kling-avatar-std"]
REGRAS = {"ativo": True, "routing": {"policy": "runware_primary", "allow_paid_fallback": True,
                                     "politicas_validas": ["runware_primary", "free_first", "best_value", "lowest_cost", "premium", "manual"],
                                     "retry": {"max_attempts_per_provider": 1}, "circuit_breaker": {"falhas_para_abrir": 3, "esfriar_s": 600}},
          "budget": {"max_cost_per_operation": 1.0, "max_cost_per_video": 5.0, "default_unknown_cost_policy": "block", "margem_seguranca": 0},
          "quality": {"preview": "standard", "final": "high"}}
FAL_CHAMADAS = []


class FalFalso:
    def __init__(self, p):
        self.p = p

    def executar(self, t, tid):
        FAL_CHAMADAS.append(self.p["id"])
        open(t["requirements"]["saida"], "wb").write(F.mp4_real())
        return {"saida": t["requirements"]["saida"], "custo_real": None}


class Amb:
    def __init__(self, falso, regras=None):
        self.falso, self.regras = falso, regras or REGRAS

    def __enter__(self):
        self.td = tempfile.mkdtemp(prefix="rwr-")
        self.salvo = (pv.CFG_PROV, pv.CFG_ROT, pv.MEM, pv._Runware.cliente)
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = (os.path.join(self.td, "p.json"), os.path.join(self.td, "r.json"), os.path.join(self.td, "mem"))
        json.dump({"provedores": [REAIS[i] for i in IDS]}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        json.dump(self.regras, open(pv.CFG_ROT, "w", encoding="utf-8"))
        pv._Runware.cliente = F.cliente(self.falso, os.path.join(self.td, "rwmem"))
        FAL_CHAMADAS.clear()
        return self

    def __exit__(self, *a):
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM, pv._Runware.cliente = self.salvo


AD = dict(pv.ADAPTADORES, FalClipe=FalFalso, FalLipsync=FalFalso)


def tarefa(td, tipo="video", dur=5, caps=None, **req):
    r = {"capabilities": caps or (["video", "i2v"] if tipo == "video" else ["lipsync", "fala_em_quadro"]),
         "imagem": F.png(td), "duration_s": dur, "prompt": "ele pega o celular", "saida": os.path.join(td, "s.mp4")}
    r.update(req)
    return {"job_id": "job", "scene_id": "s", "task_type": tipo, "mode": "final", "requirements": r}


def cred(*envs):
    return lambda env: env in envs


def test_com_chave_runware_e_a_escolhida_e_custo_real_reconciliado():
    with Amb(F.Falso(imediato=True, custo=0.35)) as a:
        r = pv.executar(tarefa(a.td), AD, credencial=cred("RUNWARE_API_KEY", "FAL_KEY"))
        assert r["status"] == "success" and r["provider"] == "runware-kling26-pro" and r["actual_cost_usd"] == 0.35, r
        rs = json.load(open(os.path.join(pv.MEM, "reservas.json"), encoding="utf-8"))["reservas"]
        assert rs[-1]["real"] == 0.35 and rs[-1]["custo_confirmado"] is True and not FAL_CHAMADAS


def test_sem_chave_runware_cai_no_fal():
    with Amb(F.Falso(imediato=True)) as a:
        r = pv.executar(tarefa(a.td), AD, credencial=cred("FAL_KEY"))
        assert r["provider"] == "fal-kling26-pro" and FAL_CHAMADAS == ["fal-kling26-pro"], r
        assert any("RUNWARE_API_KEY" in x["motivo"] for x in r["rejeitados"])  # motivo de roteamento registrado


def test_saldo_runware_esgotado_vai_para_fal_e_libera_a_reserva():
    with Amb(F.Falso(erro_envio=pv_err("saldo"))) as a:
        r = pv.executar(tarefa(a.td), AD, credencial=cred("RUNWARE_API_KEY", "FAL_KEY"))
        assert r["provider"] == "fal-kling26-pro" and r["status"] == "success", r
        assert pv.estado_de("runware-kling26-pro").get("sem_saldo_ate")
        rs = json.load(open(os.path.join(pv.MEM, "reservas.json"), encoding="utf-8"))["reservas"]
        assert rs[0]["estado"] == "liberada"  # saldo recusado = não cobrado


def pv_err(tipo):
    from runware_falso import rw
    return rw.ErroRunware(tipo, "insufficient credits" if tipo == "saldo" else tipo)


def test_fala_com_corpo_escolhe_omnihuman_da_runware():
    with Amb(F.Falso(imediato=True, custo=0.4)) as a:
        r = pv.executar(tarefa(a.td, "lipsync", None, caps=["lipsync", "fala_com_corpo"], audio=F.wav(a.td)), AD,
                        credencial=cred("RUNWARE_API_KEY", "FAL_KEY"))
        assert r["provider"] == "runware-omnihuman15", r


def test_duracao_nunca_encurtada_e_modelo_mais_caro_pede_aprovacao():
    falso = F.Falso(imediato=True)
    with Amb(falso) as a:
        r = pv.executar(tarefa(a.td, dur=2.7), AD, credencial=cred("RUNWARE_API_KEY"))
        t = falso.tarefas[-1]
        assert t["duration"] >= 2.7 and r["estimated_cost_usd"] == 0.336  # Kling 3 em 3 s (US$ 0,336) < Kling 2.6 em 5 s (US$ 0,35)
        r = pv.executar(tarefa(a.td, dur=12, saida=os.path.join(a.td, "longo.mp4")), AD, credencial=cred("RUNWARE_API_KEY"))
        rej = {x["provedor"]: x["motivo"] for h in r["fallback_history"] if "rejeitados" in h for x in h["rejeitados"]}
        assert "10s" in rej["runware-kling26-pro"]                        # 2.6 não entrega 12 s (não corta o plano)
        assert r["status"] == "waiting_approval" and "teto" in r["motivo"]  # 3 Pro a US$ 1,34 passa do teto: pede aprovação


def test_politicas_antigas_continuam_valendo():
    with Amb(F.Falso(imediato=True)) as a:
        r = pv.executar(dict(tarefa(a.td), routing_policy="lowest_cost"), AD, credencial=cred("RUNWARE_API_KEY", "FAL_KEY"))
        assert r["status"] == "success" and r["estimated_cost_usd"] == 0.35
        r = pv.executar(dict(tarefa(a.td, saida=os.path.join(a.td, "m.mp4")), routing_policy="manual", provider="fal-kling26-pro"), AD,
                        credencial=cred("RUNWARE_API_KEY", "FAL_KEY"))
        assert r["provider"] == "fal-kling26-pro"


if __name__ == "__main__":
    F.rodar(globals())
