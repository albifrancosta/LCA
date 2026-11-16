"""Orçamento com Runware: reserva atômica em paralelo, preço desconhecido, custo None, saldo promocional, cache.
Sem rede, sem crédito. Rodar: python tests/test_runware_budget.py"""
import json
import os
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import runware_falso as F  # noqa: E402
import test_runware_router as R  # noqa: E402
import provedores as pv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")



def reservas():
    return json.load(open(os.path.join(pv.MEM, "reservas.json"), encoding="utf-8"))["reservas"]


def test_dois_jobs_paralelos_nao_passam_do_teto():
    regras = json.loads(json.dumps(R.REGRAS))
    regras["budget"].update(max_cost_per_video=0.9, max_cost_per_operation=1.0)
    with R.Amb(F.Falso(imediato=True), regras) as a:
        p = R.REAIS["runware-kling3-pro"]
        t = pv.normalizar(R.tarefa(a.td, dur=5), regras)  # 0,56 cada; 2 × 0,56 > 0,90
        res = []
        ths = [threading.Thread(target=lambda: res.append(pv.autorizar(t, p, 0.56, regras))) for _ in range(2)]
        [x.start() for x in ths]
        [x.join() for x in ths]
        assert sorted(r["estado"] for r in res) == ["reservado", "waiting_approval"], res
        assert len([r for r in reservas() if r["estado"] == "reservada"]) == 1


def test_preco_desconhecido_bloqueia_sem_chamar():
    falso = F.Falso(imediato=True)
    img = dict(R.REAIS["runware-imagem"], enabled=True)  # entrada com preço None
    with R.Amb(falso) as a:
        json.dump({"provedores": [img]}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        t = {"job_id": "job", "scene_id": "i", "task_type": "imagem", "mode": "final",
             "requirements": {"capabilities": ["imagem"], "prompt": "x", "saida": os.path.join(a.td, "i.png")}}
        r = pv.executar(t, R.AD, credencial=R.cred("RUNWARE_API_KEY"))
        assert r["status"] == "waiting_approval" and "desconhecido" in r["motivo"] and falso.chamadas == []


def test_custo_none_conta_como_gasto_reservado_nunca_zero():
    with R.Amb(F.Falso(imediato=True, custo=None)) as a:
        r = pv.executar(R.tarefa(a.td), R.AD, credencial=R.cred("RUNWARE_API_KEY"))
        assert r["status"] == "success" and r["actual_cost_usd"] is None
        rr = reservas()[-1]
        assert rr["estado"] == "reconciliada" and rr["real"] is None and rr["valor"] > 0 and rr["custo_confirmado"] is False


def test_saldo_promocional_nao_vira_gratis_nem_passa_o_teto():
    regras = json.loads(json.dumps(R.REGRAS))
    regras["budget"].update(max_cost_per_video=0.10)
    falso = F.Falso(imediato=True)
    with R.Amb(falso, regras) as a:
        assert pv._Runware.cliente.conta()["balance"]["freeBalance"] == 2.0  # a conta tem crédito grátis…
        r = pv.executar(R.tarefa(a.td), R.AD, credencial=R.cred("RUNWARE_API_KEY"))
        assert r["status"] == "waiting_approval"  # …mas o teto do PROJETO manda; preço > 0 não vira grátis
        assert falso.n("videoInference") == 0


def test_cache_hit_registra_custo_zero_na_reserva():
    falso = F.Falso(imediato=True, custo=0.35)
    with R.Amb(falso) as a:
        t = R.tarefa(a.td)
        pv.executar(t, R.AD, credencial=R.cred("RUNWARE_API_KEY"))
        t2 = json.loads(json.dumps(t))
        t2["requirements"]["saida"] = os.path.join(a.td, "de-novo.mp4")
        r = pv.executar(t2, R.AD, credencial=R.cred("RUNWARE_API_KEY"))
        assert r["cache"] is True and r["actual_cost_usd"] == 0.0 and falso.n("videoInference") == 1
        assert reservas()[-1]["real"] == 0.0


if __name__ == "__main__":
    F.rodar(globals())
