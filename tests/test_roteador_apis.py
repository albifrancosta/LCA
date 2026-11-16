"""Testes de aceite do roteador de APIs (spec ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md, seção 12).
Provedores FALSOS, catálogo e estado em pasta temporária — sem rede, sem gasto.
Rodar:  python tests/test_roteador_apis.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import provedores as pv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


REGRAS = {"ativo": True,
          "routing": {"policy": "free_first", "politicas_validas": ["free_first", "best_value", "lowest_cost", "premium", "manual"],
                      "allow_paid_fallback": True, "retry": {"max_attempts_per_provider": 2, "respect_retry_after": True,
                                                              "backoff_base_s": 0.01, "backoff_max_s": 0.02},
                      "circuit_breaker": {"falhas_para_abrir": 3, "esfriar_s": 600}},
          "budget": {"max_cost_per_operation": 0.5, "max_cost_per_video": 1.0, "default_unknown_cost_policy": "block", "margem_seguranca": 0},
          "quality": {"preview": "standard", "final": "high"}}
CHAMADAS = []


def prov(pid, tier="free", preco=0, quality="high", stage="video", adaptador="Ok", **k):
    p = {"id": pid, "enabled": True, "stage": stage, "adaptador": adaptador, "model": pid, "tier": tier, "commercial_use": "allowed",
         "languages": ["*"], "capabilities": [stage, "i2v"], "quality": quality, "referencias_preservadas": True,
         "voice_profiles": ["gemini:Puck"], "price": {"unit": "clip", "amount_per_unit": preco}}
    p.update(k)
    return p


class Ambiente:
    """Catálogo + regras + memória temporários; restaura no fim."""

    def __init__(self, provs, regras=None):
        self.provs, self.regras = provs, regras or REGRAS

    def __enter__(self):
        self.td = tempfile.mkdtemp(prefix="t-rot-")
        self.salvo = (pv.CFG_PROV, pv.CFG_ROT, pv.MEM)
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = (os.path.join(self.td, "p.json"), os.path.join(self.td, "r.json"), os.path.join(self.td, "mem"))
        json.dump({"provedores": self.provs}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        json.dump(self.regras, open(pv.CFG_ROT, "w", encoding="utf-8"))
        CHAMADAS.clear()
        return self

    def __exit__(self, *a):
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = self.salvo


def adaptador(comportamento):
    """comportamento(pid, n) → None (sucesso) ou ErroProvedor a levantar."""
    class A:
        def __init__(self, p):
            self.p = p

        def executar(self, t, tid):
            n = sum(1 for c in CHAMADAS if c == self.p["id"])
            CHAMADAS.append(self.p["id"])
            e = comportamento(self.p["id"], n)
            if e:
                raise e
            return {"saida": f"{self.p['id']}.mp4", "custo_real": None if self.p["tier"] != "free" else 0.0}
    return {"Ok": A}


ACEITA = lambda s, t: {"aceito": True, "estado": "aprovado", "motivo": "ok"}  # noqa: E731
SEMPRE_OK = adaptador(lambda pid, n: None)
TAREFA = {"job_id": "v1", "scene_id": "s1", "task_type": "video", "requirements": {"duration_s": 3}}


def rodar(tarefa=None, ad=SEMPRE_OK, insp=ACEITA, cred=lambda env: True):
    return pv.executar(tarefa or TAREFA, adaptadores=ad, inspecionar=insp, dormir=lambda s: None, credencial=cred)


def aprovar(*args):
    with redirect_stdout(io.StringIO()):
        sys.argv = ["provedores.py", "aprovar", *args]
        pv.main()


def test_01_free_first_escolhe_gratis():
    with Ambiente([prov("pago", "paid", 0.3), prov("gratis")]):
        r = rodar()
        assert r["provider"] == "gratis" and r["tier_used"] == "free" and r["estimated_cost_usd"] == 0, r


def test_02_gratis_de_qualidade_baixa_rejeitado_antes_e_pelo_inspetor():
    with Ambiente([prov("gratis_ruim", quality="standard"), prov("pago", "paid", 0.3)]):
        r = rodar()
        assert r["provider"] == "pago" and "gratis_ruim" not in CHAMADAS, (r, CHAMADAS)
    with Ambiente([prov("gratis"), prov("pago", "paid", 0.3)]):
        insp = lambda s, t: {"aceito": not s.startswith("gratis"), "estado": "x", "motivo": "x"}  # noqa: E731
        r = rodar(insp=insp)
        assert r["provider"] == "pago" and CHAMADAS == ["gratis", "pago"], (r, CHAMADAS)


def test_03_cota_esgotada_cai_para_outra_gratis():
    with Ambiente([prov("g1"), prov("g2"), prov("pago", "paid", 0.3)]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("cota", "exceeded your ZeroGPU runs limit") if pid == "g1" else None)
        r = rodar(ad=ad)
        assert r["provider"] == "g2" and CHAMADAS == ["g1", "g2"], (r, CHAMADAS)
        r2 = rodar(ad=ad)  # g1 ficou marcado como esgotado: nem é chamado
        assert r2["provider"] == "g2" and CHAMADAS.count("g1") == 1


def test_04_sem_gratis_usa_pago_dentro_do_orcamento_e_reserva():
    with Ambiente([prov("pago", "paid", 0.3)]):
        r = rodar()
        assert r["status"] == "success" and r["provider"] == "pago"
        rs = json.load(open(pv.caminhos()["reservas"], encoding="utf-8"))["reservas"]
        assert len(rs) == 1 and rs[0]["estado"] == "reconciliada" and rs[0]["real"] is None and not rs[0]["custo_confirmado"]


def test_05_acima_do_teto_waiting_approval_sem_chamar():
    with Ambiente([prov("caro", "paid", 0.9)]):
        r = rodar()
        assert r["status"] == "waiting_approval" and CHAMADAS == [], r
        assert json.load(open(pv.caminhos()["pendentes"], encoding="utf-8"))["pendentes"][0]["job_id"] == "v1"


def test_05b_teto_do_video_soma_operacoes():
    with Ambiente([prov("pago", "paid", 0.4)]):
        assert rodar()["status"] == "success"
        assert rodar()["status"] == "success"
        r = rodar()  # 0,4 + 0,4 + 0,4 > 1,0
        assert r["status"] == "waiting_approval" and len(CHAMADAS) == 2, (r, CHAMADAS)


def test_06_preco_desconhecido_bloqueia_ate_aprovar():
    with Ambiente([prov("misterio", "paid", None)]):
        r = rodar()
        assert r["status"] == "waiting_approval" and not CHAMADAS
        aprovar("--job", "v1", "--custo-desconhecido", "0.05")
        r = rodar()
        assert r["status"] == "success" and r["actual_cost_usd"] is None and r["tier_used"] == "paid"
        rs = json.load(open(pv.caminhos()["reservas"], encoding="utf-8"))["reservas"]
        assert rs[-1]["valor"] == 0.05  # custo desconhecido conta pelo teto aprovado, nunca como zero


def test_07_cota_429_difere_de_taxa_429():
    assert pv.classificar_texto("You have exceeded your ZeroGPU runs limit").tipo == "cota"
    assert pv.classificar_texto("Too Many Requests", 429).tipo == "taxa"
    assert pv.classificar_texto("No GPU was available after 60s").tipo == "taxa"
    assert pv.classificar_texto("Your project has exceeded its monthly spending cap", 429).tipo == "saldo"
    assert pv.classificar_texto('{"detail":"User is locked. Reason: Exhausted balance."}', 403).tipo == "saldo"
    with Ambiente([prov("g1"), prov("g2")]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("taxa", "429", retry_after=1) if pid == "g1" and n == 0 else None)
        r = rodar(ad=ad)
        assert r["provider"] == "g1" and CHAMADAS == ["g1", "g1"]  # taxa: espera e tenta de novo no mesmo


def test_08_401_sem_loop_e_payload_nao_e_cota():
    with Ambiente([prov("p1", "paid", 0.1), prov("p2", "paid", 0.2)]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("credencial", "401 Unauthorized") if pid == "p1" else None)
        assert rodar(ad=ad)["provider"] == "p2" and CHAMADAS.count("p1") == 1
        rodar(ad=ad)
        assert CHAMADAS.count("p1") == 1 and pv.estado_de("p1").get("credencial_invalida")
    with Ambiente([prov("p1", "paid", 0.1), prov("p2", "paid", 0.2)]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("payload", "422 invalid input", cobrado=False) if pid == "p1" else None)
        rodar(ad=ad)
        e = pv.estado_de("p1")
        assert not e.get("esgotado_ate") and not e.get("credencial_invalida") and CHAMADAS.count("p1") == 1
        rs = json.load(open(pv.caminhos()["reservas"], encoding="utf-8"))["reservas"]
        assert rs[0]["estado"] == "liberada"  # payload recusado não foi cobrado


def test_09_timeout_ambiguo_nao_dispara_segundo_job_pago():
    with Ambiente([prov("p1", "paid", 0.1), prov("p2", "paid", 0.2)]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("timeout_ambiguo", "tempo esgotado", job_remoto="req-123") if pid == "p1" else None)
        r = rodar(ad=ad)
        assert r["status"] == "pendente_verificacao" and r["job_remoto"] == "req-123" and CHAMADAS == ["p1"], (r, CHAMADAS)


def test_10_voz_aprovada_nao_troca_sozinha():
    voz = {"job_id": "v9", "task_type": "tts", "requirements": {"voice_profile_id": "gemini:Puck", "texto": "oi"}}
    a, b = prov("tts_a", "paid", 0.01, stage="tts"), prov("tts_b", "paid", 0.02, stage="tts")
    a["capabilities"] = b["capabilities"] = ["tts"]
    with Ambiente([a, b]):
        assert rodar(voz)["provider"] == "tts_a"
        ad = adaptador(lambda pid, n: pv.ErroProvedor("cota", "quota exceeded") if pid == "tts_a" else None)
        r = rodar(voz, ad=ad)
        assert r["status"] != "success" and "tts_b" not in CHAMADAS, (r, CHAMADAS)
        aprovar("--job", "v9", "--troca-voz")
        assert rodar(voz, ad=ad)["provider"] == "tts_b"


def test_11_estilo_so_cai_para_quem_preserva_referencias():
    with Ambiente([prov("v1_ok", "paid", 0.1), prov("sem_ref", "paid", 0.05, referencias_preservadas=False)]):
        assert rodar(dict(TAREFA, job_id="v7", routing_policy="manual", provider="v1_ok"))["provider"] == "v1_ok"
        r = rodar(dict(TAREFA, job_id="v7"))
        assert r["provider"] == "v1_ok" and "sem_ref" not in CHAMADAS, (r, CHAMADAS)


def test_12_licenca_incompativel_rejeitada_em_comercial():
    with Ambiente([prov("gratis_sem_licenca", commercial_use="unknown"), prov("pago", "paid", 0.3)]):
        r = rodar(dict(TAREFA, commercial_use=True))
        assert r["provider"] == "pago" and "gratis_sem_licenca" not in CHAMADAS


def test_13_nenhuma_chave_no_log():
    os.environ["FAKE_API_KEY"] = "sk-segredo-1234567890abcdef"
    try:
        with Ambiente([prov("p1", "paid", 0.1), prov("p2", "paid", 0.2)]):
            ad = adaptador(lambda pid, n: pv.ErroProvedor("credencial", "401 bad key sk-segredo-1234567890abcdef") if pid == "p1" else None)
            r = rodar(ad=ad)
            todo = (open(pv.caminhos()["log"], encoding="utf-8").read() + json.dumps(r) +
                    open(pv.caminhos()["estado"], encoding="utf-8").read())
            assert "sk-segredo" not in todo
    finally:
        del os.environ["FAKE_API_KEY"]


def test_14_relatorio_separa_previsto_confirmado_desconhecido():
    with Ambiente([prov("g"), prov("pago", "paid", 0.3)]):
        rodar()
        rodar(dict(TAREFA, routing_policy="manual", provider="pago"))
        out = io.StringIO()
        with redirect_stdout(out):
            pv.relatorio("v1")
        s = out.getvalue()
        assert "US$ 0,00 (grátis)" in s and "cobrado CONFIRMADO: US$ 0.00" in s and "1 lançamento(s) com" in s, s


def test_15_rollback_roteador_desligado_e_scripts_antigos_intactos():
    with Ambiente([prov("g")], dict(REGRAS, ativo=False)):
        tarefa = pv.MEM + "-t.json"
        json.dump(TAREFA, open(tarefa, "w"))
        sys.argv = ["provedores.py", "executar", tarefa]
        try:
            pv.main()
            raise AssertionError("executou com o roteador desligado")
        except SystemExit as e:
            assert "desligado" in str(e)
    for s in ("gerar_clipe_fal.py", "lipsync.py", "gerar_imagem.py", "tts_gemini.py"):
        r = subprocess.run([sys.executable, str(SCRIPTS / s), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0, s


def test_16_disjuntor_abre_depois_de_falhas_seguidas():
    with Ambiente([prov("instavel"), prov("reserva", "paid", 0.1)]):
        ad = adaptador(lambda pid, n: pv.ErroProvedor("transitorio", "503") if pid == "instavel" else None)
        for _ in range(3):
            rodar(ad=ad)
        assert pv.estado_de("instavel").get("aberto_ate"), pv.estado_de("instavel")
        antes = CHAMADAS.count("instavel")
        rodar(ad=ad)
        assert CHAMADAS.count("instavel") == antes  # disjuntor aberto: nem chama


def test_17_reserva_paralela_nao_estoura_teto():
    with Ambiente([prov("pago", "paid", 0.45)]):
        t = pv.normalizar(TAREFA, REGRAS)
        p = json.load(open(pv.CFG_PROV, encoding="utf-8"))["provedores"][0]
        res = []
        ths = [threading.Thread(target=lambda: res.append(pv.autorizar(t, p, 0.45, REGRAS))) for _ in range(4)]
        [x.start() for x in ths]
        [x.join() for x in ths]
        assert sum(r["ok"] for r in res) == 2, res  # teto do vídeo 1,00: só 2 reservas de 0,45 cabem, mesmo em paralelo


def test_18_catalogo_real_valido():
    cat = json.load(open(SCRIPTS.parent / "config" / "provedores.json", encoding="utf-8"))
    for p in cat["provedores"]:
        assert p["tier"] in ("free", "paid", "unknown") and p.get("commercial_use") in ("allowed", "prohibited", "unknown"), p["id"]
        if p["tier"] == "free":
            assert (p.get("price") or {}).get("amount_per_unit") == 0, f"{p['id']}: grátis sem preço 0 comprovado"
        if p.get("enabled") and p.get("adaptador"):
            assert p["adaptador"] in pv.ADAPTADORES, p["id"]
    texto = open(SCRIPTS.parent / "config" / "provedores.json", encoding="utf-8").read()
    assert not pv.SEGREDO.search(texto), "parece haver uma chave no catálogo"


def main():
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    falhas = 0
    for n, f in testes:
        try:
            f()
            print(f"PASS {n}")
        except BaseException as e:  # noqa: BLE001
            falhas += 1
            print(f"FAIL {n}: {type(e).__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
