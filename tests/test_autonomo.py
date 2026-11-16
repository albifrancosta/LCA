"""Testes do modo autônomo (autonomo.py) — sem rede, sem gasto: o roteador e o inspetor são simulados.
Rodar: python tests/test_autonomo.py"""
import io
import json
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import autonomo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


BEATS = [{"ate": 2.0, "fase": "antecipacao", "en": "he looks at the phone"},
         {"ate": 4.0, "fase": "acao", "en": "he picks it up"},
         {"ate": 5.0, "fase": "reacao", "en": "he smiles"}]


def projeto(planos=("p1",), com_imagem=True):
    base = tempfile.mkdtemp(prefix="auto-")
    for d in ("assets/img", "assets/clips", "entrega", "tarefas"):
        os.makedirs(os.path.join(base, d))
    ps = []
    for pid in planos:
        ps.append({"id": pid, "quem": ["marcos"], "fala": "", "direcao": {
            "modo": "acao", "duracao": 5.0, "quem": ["marcos"], "acao": "pega o celular", "voz": "off", "camera": "fixa",
            "enquadramento": "PM", "exige": ["bracos"], "fisica": "mão → celular", "beats": BEATS}})
        if com_imagem:
            open(os.path.join(base, "assets", "img", f"{pid}.png"), "wb").write(b"png")
    arq = os.path.join(base, "roteiro.json")
    json.dump({"planos": ps}, io.open(arq, "w", encoding="utf-8"))
    return base, arq


class Falso:
    """Simula provedores.py executar/planejar e inspetor.py planos. `veredictos` = estados devolvidos em sequência."""

    def __init__(self, base, veredictos=("aprovado",), status="success"):
        self.base, self.veredictos, self.status = base, list(veredictos), status
        self.chamadas, self.prompts = [], []

    def __call__(self, cmd, timeout=None):
        nome = os.path.basename(cmd[1])
        self.chamadas.append((nome, cmd[2]))
        if nome == "especialistas.py":
            fila = getattr(self, cmd[2], None) or []  # self.atuacao / self.figurino = códigos em sequência
            cod = fila.pop(0) if fila else 0
            if cod == 2:
                json.dump({"itens": [{"id": cmd[cmd.index("--planos") + 1], "estado": "reprovado",
                                      "correcao_en": "restrained reaction, smaller gestures",
                                      "problemas": [["grave", "beat 2 (acao): exagerado (intensidade 5 × 2)"]]}]},
                          io.open(os.path.join(self.base, "entrega", f"inspecao-{cmd[2]}.json"), "w", encoding="utf-8"))
            return cod, f"{cmd[2]}: 0 ✅ · 1 ❌" if cod == 2 else ""
        if nome == "conferencia.py":
            cod = self.lip.pop(0) if getattr(self, "lip", None) else 0
            if cod == 2:
                json.dump({"itens": [{"id": cmd[cmd.index("--planos") + 1], "estado": "reprovado",
                                      "problemas": [["grave", "boca fora de tempo +200 ms"]]}]},
                          io.open(os.path.join(self.base, "entrega", "inspecao-lipsync.json"), "w", encoding="utf-8"))
            return cod, "Lip-sync medido: 0 ✅ · 1 ❌"
        if nome == "provedores.py":
            t = json.load(io.open(cmd[3], encoding="utf-8"))
            self.prompts.append(t["requirements"].get("prompt", ""))
            if cmd[2] == "planejar":
                return 0, "plano: fal-kling26-pro · US$ 0,35"
            if self.status != "success":
                return 4, json.dumps({"status": self.status, "motivo": "teto do vídeo"})
            open(t["requirements"]["saida"], "wb").write(b"mp4" * 10)
            return 0, "log\n" + json.dumps({"status": "success", "provider": "fal-kling26-pro", "estimated_cost_usd": 0.35})
        pid = cmd[cmd.index("--planos") + 1]
        est = self.veredictos.pop(0) if self.veredictos else "aprovado"
        item = {"id": pid, "estado": est, "nota": {"valor": 92 if est == "aprovado" else 60},
                "problemas": [] if est == "aprovado" else ["só a câmera se mexe"],
                "revisao_visual": {"criterios": [] if est == "aprovado" else [{"criterio": "pega o celular", "ok": False,
                                                                               "visto": "mão parada"}]}}
        rel = os.path.join(self.base, "entrega", "inspecao-planos.json")
        d = json.load(io.open(rel, encoding="utf-8")) if os.path.exists(rel) else {"itens": []}
        d["itens"] = [x for x in d["itens"] if x["id"] != pid] + [item]
        json.dump(d, io.open(rel, "w", encoding="utf-8"))
        return {"aprovado": 0, "reprovado": 2, "nao_verificado": 3}[est], ""


def execs(f):
    return [c for c in f.chamadas if c == ("provedores.py", "executar")]


def test_reprova_refaz_com_correcao_e_aprova():
    base, arq = projeto()
    f = Falso(base, ["reprovado", "aprovado"])
    st, parar = autonomo.rodar(arq, "job", run=f)
    e = st["planos"]["p1"]
    assert e["estado"] == "aprovado" and e["tentativas"] == 2 and parar is None, e
    assert e["nota"] == 92
    assert os.path.exists(os.path.join(base, "assets", "clips", "rejeitados", "p1-t1.mp4"))
    assert "FIX FROM PREVIOUS TAKE" in f.prompts[1] and "mão parada" in f.prompts[1]
    assert "FIX" not in f.prompts[0]
    assert abs(e["custo_estimado"] - 0.70) < 1e-9
    shutil.rmtree(base)


def test_refacoes_esgotadas_marca_e_para_de_gastar():
    base, arq = projeto()
    f = Falso(base, ["reprovado"] * 10)
    st, _ = autonomo.rodar(arq, "job", max_refacoes=2, run=f)
    assert st["planos"]["p1"]["estado"] == "marcado"
    assert len(execs(f)) == 3  # 1 take + 2 refações
    autonomo.rodar(arq, "job", run=f)  # rodar de novo não gasta com o marcado
    assert len(execs(f)) == 3
    shutil.rmtree(base)


def test_teto_do_roteador_bloqueia_uma_vez_sem_repetir_nem_travar_o_resto():
    # 2026-11-07: antes o laço inteiro parava; agora o bloqueio é registrado UMA vez (p1) e os outros planos ficam
    # "precisa_orcamento — mesmo bloqueio" sem chamar o roteador de novo (nada de mensagem repetida nem gasto)
    base, arq = projeto(("p1", "p2"))
    f = Falso(base, status="waiting_approval")
    st, parar = autonomo.rodar(arq, "job", run=f)
    assert st["planos"]["p1"]["estado"] == "precisa_orcamento" and st["planos"]["p1"]["tentativas"] == 0
    assert st["planos"]["p2"]["estado"] == "precisa_orcamento" and "mesmo bloqueio de p1" in st["planos"]["p2"]["bloqueio"]
    assert len(execs(f)) == 1 and parar
    shutil.rmtree(base)


def test_sem_imagem_nao_gasta():
    base, arq = projeto(com_imagem=False)
    f = Falso(base)
    st, _ = autonomo.rodar(arq, "job", run=f)
    assert st["planos"]["p1"]["estado"] == "aguardando_imagem" and not f.chamadas
    shutil.rmtree(base)


def test_nao_verificado_vai_para_o_diretor_nunca_aprova_sozinho():
    base, arq = projeto()
    f = Falso(base, ["nao_verificado"])
    st, _ = autonomo.rodar(arq, "job", run=f)
    assert st["planos"]["p1"]["estado"] == "revisao_diretor" and len(execs(f)) == 1
    shutil.rmtree(base)


def test_simular_nao_executa():
    base, arq = projeto(("p1", "p2"))
    f = Falso(base)
    st, _ = autonomo.rodar(arq, "job", simular=True, run=f)
    assert not execs(f) and all(e["estado"] == "simulado" for e in st["planos"].values())
    shutil.rmtree(base)


def test_teto_da_rodada():
    base, arq = projeto(("p1", "p2", "p3"))
    f = Falso(base)
    st, parar = autonomo.rodar(arq, "job", teto=0.5, run=f)
    assert len(execs(f)) == 2 and "teto" in parar  # p1 (0,35) e p2 (0,70 acumulado) — p3 não começa
    shutil.rmtree(base)


def test_clipe_existente_aprovado_nao_regera():
    base, arq = projeto()
    open(os.path.join(base, "assets", "clips", "p1.mp4"), "wb").write(b"mp4")
    f = Falso(base, ["aprovado"])
    st, _ = autonomo.rodar(arq, "job", run=f)
    assert st["planos"]["p1"]["estado"] == "aprovado" and not execs(f)
    assert os.path.exists(os.path.join(base, "entrega", "autonomo-relatorio.md"))
    shutil.rmtree(base)


def test_fala_em_quadro_reprovada_no_lipsync_medido_e_refeita():
    base, arq = projeto()
    d = json.load(io.open(arq, encoding="utf-8"))
    d["planos"][0].update(fala="MinhaMarca, quanto eu faturei?")
    d["planos"][0]["direcao"].update(modo="fala", voz="em_quadro")
    json.dump(d, io.open(arq, "w", encoding="utf-8"))
    os.makedirs(os.path.join(base, "assets", "voz"))
    open(os.path.join(base, "assets", "voz", "p1.wav"), "wb").write(b"wav")
    f = Falso(base, ["aprovado", "aprovado"])
    f.lip = [2, 0]  # 1º take: inspetor aprova mas a boca medida está fora de tempo → refaz
    st, _ = autonomo.rodar(arq, "job", run=f)
    e = st["planos"]["p1"]
    assert e["rota"] in ("avatar", "omnihuman") and e["estado"] == "aprovado" and e["tentativas"] == 2, e
    assert "lip-sync" in f.prompts[1] and "+200 ms" in f.prompts[1]
    shutil.rmtree(base)


def test_atuacao_exagerada_reprova_e_correcao_vai_no_proximo_take():
    base, arq = projeto()
    f = Falso(base, ["aprovado", "aprovado"])
    f.atuacao = [2, 0]
    st, _ = autonomo.rodar(arq, "job", run=f)
    e = st["planos"]["p1"]
    assert e["estado"] == "aprovado" and e["tentativas"] == 2, e
    assert "restrained reaction" in f.prompts[1] and "exagerado" in f.prompts[1]
    assert ("especialistas.py", "figurino") in f.chamadas
    shutil.rmtree(base)


def test_clipe_ja_aprovado_sem_imagem_conta_como_aprovado():
    base, arq = projeto(com_imagem=False)
    open(os.path.join(base, "assets", "clips", "p1.mp4"), "wb").write(b"mp4")
    json.dump({"itens": [{"id": "p1", "estado": "aprovado"}]},
              io.open(os.path.join(base, "entrega", "inspecao-planos.json"), "w", encoding="utf-8"))
    f = Falso(base)
    st, _ = autonomo.rodar(arq, "job", run=f)
    assert st["planos"]["p1"]["estado"] == "aprovado" and not f.chamadas
    shutil.rmtree(base)


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in testes:
        try:
            t()
            ok += 1
            print("✅", t.__name__)
        except Exception as e:  # noqa: BLE001
            print("❌", t.__name__, repr(e))
    print(f"\n{ok}/{len(testes)} passaram")
    sys.exit(0 if ok == len(testes) else 1)
