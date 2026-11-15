"""Testes da AI Film Production Bible + AI Continuity Supervisor — sem rede, sem API paga (provedores e análise visual
são MOCKS; vídeos sintéticos gerados com OpenCV). Cobre os testes A–F do pedido + integração com o orquestrador.
Rodar:  python tests/test_production_bible.py        (também roda com pytest)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import integridade as ig  # noqa: E402
import orquestrador  # noqa: E402
import supervisor_continuidade as sup  # noqa: E402
from cinematografia import board_generator as bg  # noqa: E402
from cinematografia import production_bible as pb  # noqa: E402

ANALISE_LIMPA = {"criterios": [], "identidade": [{"personagem": "ana", "rosto_igual_ficha": True}],
                 "anatomia": [{"personagem": "ana", "bracos": 2, "maos": 2, "dedos_ok": True, "segundo": 1.0}],
                 "figurino": [{"personagem": "ana", "peca": "blusa azul", "na_ficha": True, "no_corpo": True}],
                 "aparelhos": [], "textos_simbolos": [], "oclusao": [], "continuidade_temporal": [], "deformacoes": [],
                 "boca": "nao_se_aplica", "qualidade_visual": 8, "nota": 8, "confianca": 0.9}


def _png(caminho, cor, tam=(512, 768), texto=None):
    from PIL import Image, ImageDraw
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    im = Image.new("RGB", tam, cor)
    d = ImageDraw.Draw(im)
    d.ellipse([tam[0] * 0.3, tam[1] * 0.1, tam[0] * 0.7, tam[1] * 0.35], fill=(240, 200, 170))
    d.rectangle([tam[0] * 0.25, tam[1] * 0.36, tam[0] * 0.75, tam[1] * 0.8], fill=(40, 90, 200))
    if texto:
        d.text((10, 10), texto, fill=(255, 255, 255))
    im.save(caminho)


def _video(caminho, dur=3.0, fps=24, congela=None):
    """Quadrado andando; `congela=(a, b)` repete o mesmo quadro nesse intervalo (imagem parada)."""
    import cv2
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    w = cv2.VideoWriter(caminho, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 568))
    ultimo = None
    for i in range(int(dur * fps)):
        t = i / fps
        if congela and congela[0] <= t < congela[1] and ultimo is not None:
            w.write(ultimo)
            continue
        q = np.full((568, 320, 3), 30, np.uint8)
        x = int(20 + 260 * (t / dur))
        cv2.rectangle(q, (x, 250), (x + 40, 320), (0, 200, 255), -1)
        cv2.circle(q, (160, 100 + int(30 * np.sin(t * 6))), 25, (200, 200, 200), -1)
        w.write(q)
        ultimo = q
    w.release()
    return caminho


def projeto_teste(raiz):
    base = os.path.join(raiz, "proj")
    _png(os.path.join(base, "assets", "ficha-ana.png"), (90, 60, 120), texto="ficha Ana")
    _png(os.path.join(base, "assets", "escritorio.png"), (60, 80, 70), (768, 432), texto="escritorio")
    _png(os.path.join(base, "assets", "img", "t001.png"), (70, 70, 90), texto="t001")
    d = {"titulo": "Teste Bíblia", "estilo": "ilustração 2D cinematográfica", "formato": "9:16",
         "personagens": {"ana": {"nome": "Ana", "descricao": "dona de oficina, 40 anos", "ficha": "assets/ficha-ana.png",
                                 "tracos": ["cabelo preto curto", "brinco de argola"], "figurino": {"blusa": "azul", "calça": "jeans"},
                                 "altura_cm": 165, "voz": "Kore"}},
         "cenarios": {"escritorio": {"descricao": "escritório da oficina", "luz": "janela lateral, luminária quente",
                                     "paleta": ["#1B2A44", "#F2B23A", "#E9EEF6"], "ref": "assets/escritorio.png", "horario": "manhã",
                                     "moveis": ["mesa", "cadeira", "estante"]}},
         "objetos": {"caneca": {"descricao": "caneca branca"}, "tablet": {"descricao": "tablet preto"}},
         "tomadas": [
             {"id": "t001", "cena": "abertura", "cenario": "escritorio", "personagens": ["ana"], "objetos": ["caneca"],
              "objetos_estado": {"caneca": "na mão de Ana"}, "acao": "Ana caminha até a mesa", "emocao": "cansada",
              "fala": "Segunda-feira de novo.", "decupagem": {"plano": "geral", "duracao": 3}, "status": "rascunho",
              "versoes": [{"v": 1, "tipo": "imagem", "arquivo": "assets/img/t001.png"}]},
             {"id": "t002", "cena": "abertura", "cenario": "escritorio", "personagens": ["ana"], "objetos": ["tablet"],
              "acao": "Ana olha o tablet preocupada", "emocao": "preocupada", "fala": "Cadê o dinheiro?",
              "decupagem": {"duracao": 2.5}, "status": "rascunho", "versoes": []},
             {"id": "t003", "cena": "solucao", "cenario": "escritorio", "personagens": ["ana"], "objetos": ["tablet"],
              "objetos_estado": {"tablet": "na mão de Ana"}, "acao": "Ana mostra o tablet sorrindo", "emocao": "alívio",
              "fala": "Agora está tudo num lugar só.", "decupagem": {"plano": "medio", "lente": "50mm", "duracao": 3},
              "status": "rascunho", "versoes": []}]}
    os.makedirs(base, exist_ok=True)
    ig.gravar_json_atomico(os.path.join(base, "producao.json"), d)
    # projeto em modo econômico com teto (job único: não esbarra em reservas reais do livro do roteador)
    ig.gravar_json_atomico(os.path.join(base, "projeto.json"), {
        "autonomia": {"modo": "economico", "job_id": f"teste-bible-{os.path.basename(raiz)}"},
        "orcamento": {"teto_autorizado": 5.0}, "limites": {"max_refacoes_plano": 2, "max_gasto_plano": 2.0}})
    return base


def _mock_custo(custo=0.2):
    return lambda plano, b: (custo, "mock-video", "estimativa de teste")


# ---------------------------------------------------------------- Teste A — figurino
def test_a_figurino_gravata():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        video = _video(os.path.join(base, "takes", "t001.mp4"))
        vis = {**ANALISE_LIMPA, "figurino": ANALISE_LIMPA["figurino"] + [
            {"personagem": "ana", "peca": "gravata vermelha", "na_ficha": False, "no_corpo": True, "segundo": 1.2}]}
        r = sup.inspecionar_take(base, "t001", video, analisador=lambda *_: vis)
        assert r["estado"] == ig.REPROVADO, r
        p = next(p for p in r["problemas"] if p["codigo"] == "figurino_involuntario")
        assert p["inicio"] == 1.2 and "gravata" in p["texto"]
        c = sup.corrigir(base, "t001", estimador=_mock_custo())
        assert c["estado"] == "aguardando_regeneracao", c
        plano = c["historico"][-1]["plano"]
        assert plano["estrategia"] == "regerar_com_referencia"
        assert "no gravata vermelha" in plano["prompt_correcao"] and "blusa azul" in plano["prompt_correcao"]
        assert any(r_["id"] == "char_ana" for r_ in plano["referencias"])


# ---------------------------------------------------------------- Teste B — anatomia
def test_b_tres_bracos():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        video = _video(os.path.join(base, "takes", "t001.mp4"))
        vis = {**ANALISE_LIMPA, "anatomia": [{"personagem": "ana", "bracos": 3, "maos": 3, "dedos_ok": True, "segundo": 1.5,
                                              "visto": "terceiro braço saindo do ombro"}]}
        r = sup.inspecionar_take(base, "t001", video, analisador=lambda *_: vis)
        p = next(p for p in r["problemas"] if p["codigo"] == "membros_extras")
        assert p["gravidade"] == "grave" and p["inicio"] == 1.5
        assert r["evidencia"] and os.path.exists(os.path.join(base, r["evidencia"])), "folha de quadros suspeitos"
        assert sup.plano_correcao(pb.carregar(base), r)["estrategia"] == "regerar_take"


# ---------------------------------------------------------------- Teste C — interface atrás do aparelho
def test_c_interface_atras_do_tablet():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        video = _video(os.path.join(base, "takes", "t003.mp4"))
        vis = {**ANALISE_LIMPA, "aparelhos": [{"objeto": "tablet", "quem_usa": "ana", "tela_voltada_para": "usuario",
                                               "interface_desenhada_na_traseira": True, "segundo": 0.8}],
               "objetos_visiveis": [{"objeto": "tablet", "segurado_por": "Ana"}]}
        r = sup.inspecionar_take(base, "t003", video, analisador=lambda *_: vis)
        p = next(p for p in r["problemas"] if p["codigo"] == "interface_traseira")
        assert p["gravidade"] == "grave" and p["inicio"] == 0.8
        assert sup.plano_correcao(pb.carregar(base), r)["estrategia"] == "refazer_imagem_chave"


# ---------------------------------------------------------------- Teste D — congelamento + correção localizada
def test_d_congelamento_e_correcao():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        ruim = _video(os.path.join(base, "takes", "t001.mp4"), congela=(1.0, 2.2))
        r = sup.inspecionar_take(base, "t001", ruim, analisador=lambda *_: ANALISE_LIMPA)
        cg = [p for p in r["problemas"] if p["codigo"] == "congelamento"]
        assert cg and 0.9 <= cg[0]["inicio"] <= 1.1 and 2.0 <= cg[0]["fim"] <= 2.25 and cg[0]["gravidade"] == "grave", cg
        chamadas = []

        def regenerar(tid, plano, tentativa):
            chamadas.append((tid, plano["estrategia"], plano["intervalo"]))
            return {"arquivo": _video(os.path.join(base, "takes", f"{tid}-v{tentativa + 1}.mp4")), "custo_real": 0.18}
        c = sup.corrigir(base, "t001", regenerar=regenerar, analisador=lambda *_: ANALISE_LIMPA, estimador=_mock_custo(0.2))
        assert c["estado"] == "aprovado" and c["tentativas"] == 1, c
        assert chamadas[0][0] == "t001" and chamadas[0][1] == "regerar_trecho"
        a, z = chamadas[0][2]
        assert a < 1.0 and z > 2.0 and z - a < 3.0, "só o trecho congelado (com margem), não o take inteiro"
        assert c["custo_real_usd"] == 0.18 and c["custo_estimado_usd"] == 0.2
        assert c["historico"][0]["resolvidos"] == ["congelamento"]
        log = Path(base, "production_bible", "continuity", "log.jsonl").read_text(encoding="utf-8")
        assert "regenerado" in log and "key" not in log.lower()


def test_d2_limite_de_tentativas_e_orcamento():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        ruim = _video(os.path.join(base, "takes", "t001.mp4"), congela=(1.0, 2.2))
        sup.inspecionar_take(base, "t001", ruim, analisador=lambda *_: ANALISE_LIMPA)
        n = []

        def sempre_ruim(tid, plano, tentativa):
            n.append(tentativa)
            return {"arquivo": _video(os.path.join(base, "takes", f"r{len(n)}.mp4"), congela=(1.0, 2.2)), "custo_real": 0.1}
        c = sup.corrigir(base, "t001", regenerar=sempre_ruim, analisador=lambda *_: ANALISE_LIMPA, estimador=_mock_custo(0.1),
                         cfg={"max_tentativas": 3, "orcamento_correcao_usd": 5})
        assert c["estado"] == "revisao_humana" and len(n) == 3 and "limite" in c["motivo"], c
        sup.inspecionar_take(base, "t001", ruim, analisador=lambda *_: ANALISE_LIMPA)
        n.clear()
        c = sup.corrigir(base, "t001", regenerar=sempre_ruim, analisador=lambda *_: ANALISE_LIMPA, estimador=_mock_custo(0.2),
                         cfg={"max_tentativas": 5, "orcamento_correcao_usd": 0.3})
        assert c["estado"] == "revisao_humana" and len(n) == 1 and "orçamento" in c["motivo"], c
        sup.inspecionar_take(base, "t001", ruim, analisador=lambda *_: ANALISE_LIMPA)
        c = sup.corrigir(base, "t001", regenerar=sempre_ruim, estimador=lambda p, b: (None, None, "sem preço"))
        assert c["estado"] == "revisao_humana" and "preço desconhecido" in c["motivo"]


def test_d4_custo_zero_bloqueia_regeneracao_paga():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        os.remove(os.path.join(base, "projeto.json"))  # sem projeto.json o padrão é custo_zero
        pb.construir(base)
        ruim = _video(os.path.join(base, "takes", "t001.mp4"), congela=(1.0, 2.2))
        sup.inspecionar_take(base, "t001", ruim, analisador=lambda *_: ANALISE_LIMPA)
        chamou = []
        c = sup.corrigir(base, "t001", regenerar=lambda *a: chamou.append(a), estimador=_mock_custo(0.2))
        assert c["estado"] == "bloqueado_orcamento" and "custo_zero" in c["motivo"] and not chamou
        # limites do projeto.json viram o padrão do supervisor
        projeto_teste(tmp)
        assert sup.cfg_correcao(pb.carregar(base), base)["max_tentativas"] == 2


def test_d3_sem_analise_nao_aprova():
    """Inspeção que terminou sem erro mas sem análise visual = não verificado (revisão humana), nunca aprovado."""
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        pb.construir(base)
        bom = _video(os.path.join(base, "takes", "t001.mp4"))
        r = sup.inspecionar_take(base, "t001", bom)
        assert r["estado"] == ig.NAO_VERIFICADO and r["revisao_humana"]
        r = sup.inspecionar_take(base, "t001", bom, analisador=lambda *_: {"indisponivel": "sem cota"})
        assert r["estado"] == ig.NAO_VERIFICADO
        r = sup.inspecionar_take(base, "t001", bom, analisador=lambda *_: {**ANALISE_LIMPA, "confianca": 0.3})
        assert r["estado"] == ig.NAO_VERIFICADO and "confiança" in r["motivo_revisao"]
        r = sup.inspecionar_take(base, "t001", bom, analisador=lambda *_: ANALISE_LIMPA)
        assert r["estado"] == ig.APROVADO, r
        assert sup.corrigir(base, "t001")["estado"] == "aprovado"


# ---------------------------------------------------------------- Teste E — continuidade entre tomadas
def test_e_objeto_some_no_corte():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        b = pb.construir(base)
        plano = [c for c in b["continuidade"] if c["codigo"] == "objeto_sumiu"]
        assert plano and "t001→t002" in plano[0]["texto"] and "caneca" in plano[0]["texto"]
        analises = {"t001": {"objetos_visiveis": [{"objeto": "caneca", "segurado_por": "Ana"}]},
                    "t002": {"objetos_visiveis": [{"objeto": "tablet", "segurado_por": "Ana"}]}}
        r = sup.entre_takes(base, analises)
        assert any(p["codigo"] == "objeto_sumiu_no_corte" and "caneca" in p["texto"] for p in r["problemas"])
        # com justificativa narrativa ("deixa a caneca") não acusa
        d = json.load(open(os.path.join(base, "producao.json"), encoding="utf-8"))
        d["tomadas"][1]["acao"] = "Ana deixa a caneca na mesa e olha o tablet"
        ig.gravar_json_atomico(os.path.join(base, "producao.json"), d)
        b = pb.construir(base)
        assert not [c for c in b["continuidade"] if c["codigo"] == "objeto_sumiu"]
        assert not [p for p in sup.entre_takes(base, analises)["problemas"] if p["codigo"] == "objeto_sumiu_no_corte"]


# ---------------------------------------------------------------- Teste F — bíblia completa + prancha
def test_f_biblia_e_prancha():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        b = pb.construir(base)
        assert pb.validar(b) == []
        json.loads(Path(pb.arq_bible(base)).read_text(encoding="utf-8"))
        assert set(b["personagens"]) == {"char_ana"} and set(b["cenarios"]) == {"env_escritorio"}
        assert set(b["objetos"]) == {"prop_caneca", "prop_tablet"}
        ana = b["personagens"]["char_ana"]
        assert set(ana["vistas"]) == {"frontal", "lateral", "traseira", "tres_quartos"}
        assert {"cansada", "preocupada", "alívio"} <= set(ana["expressoes"]) and ana["escala"] == {"altura_cm": 165}
        assert [t["tempo_fonte"] for t in b["tomadas"]] == ["duracao"] * 3 and b["tomadas"][2]["inicio"] == 5.5
        sb = b["storyboard"][0]
        assert sb["rotulo"] == "C01·T01" and sb["imagem"]["arquivo"] == "assets/img/t001.png"
        assert {r["id"] for r in sb["referencias"]} == {"char_ana", "env_escritorio"}
        assert b["planos"]["t003"]["lente_mm"] == 50 and b["planos"]["t001"]["enquadramento"] == "aberto"
        for sub in ("characters/char_ana.json", "environments/env_escritorio.json", "props/prop_tablet.json",
                    "storyboards/storyboard.json", "shot_lists/shot_list.json", "continuity/registro.json"):
            assert os.path.exists(os.path.join(pb.pasta(base), sub)), sub
        feitos, lim = bg.gerar(base)
        boards = os.path.join(pb.pasta(base), "boards")
        html = Path(boards, "overview.html").read_text(encoding="utf-8")
        for titulo in ("Character Reference", "Storyboard", "Environment / Set Design", "Shot List", "Camera Blocking",
                       "Props &amp; Continuity", "Lighting &amp; Color", "Scene Timeline"):
            assert titulo in html, titulo
        assert "../../assets/ficha-ana.png" in html and "char_ana" in html and "cena-02.html" in html
        assert os.path.exists(os.path.join(boards, "cena-01.html")) and os.path.exists(os.path.join(boards, "cena-02.html"))
        assert not lim, lim
        png, pdf = Path(boards, "overview.png").read_bytes(), Path(boards, "overview.pdf").read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 50_000 and pdf[:4] == b"%PDF"
        from PIL import Image
        with Image.open(os.path.join(boards, "overview.png")) as im:
            assert im.width >= 2000, "alta resolução (1.5x)"


def test_f2_ids_estaveis_versoes_e_aprovacao():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        b1 = pb.construir(base)
        b2 = pb.construir(base)
        assert b1["hash"] == b2["hash"] and b2["personagens"]["char_ana"]["ficha"]["versao"] == 1
        assert pb.portao(base)["tarefa"] == "aprovar_prancha" and not pb.portao(base)["liberado"]
        pb.aprovar(base, "ok do usuário no chat")
        assert pb.portao(base)["liberado"]
        assert pb.construir(base)["aprovacao"]["estado"] == "aprovada", "rebuild sem mudança mantém a aprovação"
        _png(os.path.join(base, "assets", "ficha-ana.png"), (10, 200, 10), texto="ficha nova")
        b3 = pb.construir(base)
        f = b3["personagens"]["char_ana"]["ficha"]
        assert f["versao"] == 2 and f["historico"][0]["versao"] == 1
        assert b3["aprovacao"]["estado"] == "pendente", "referência nova invalida a aprovação"
        # substituição manual de referência (humano) sobrevive ao rebuild
        _png(os.path.join(base, "assets", "ana-frente.png"), (200, 10, 10))
        b = pb.carregar(base)
        b["substituicoes"] = {"char_ana": {"frontal": "assets/ana-frente.png"}}
        ig.gravar_json_atomico(pb.arq_bible(base), b)
        b4 = pb.construir(base)
        assert b4["personagens"]["char_ana"]["vistas"]["frontal"]["status"] == "referencia"
        assert pb.construir(base)["personagens"]["char_ana"]["vistas"]["frontal"]["ref"]["arquivo"] == "assets/ana-frente.png"


def test_pre_producao_e_modo_automatico():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        d = json.load(open(os.path.join(base, "producao.json"), encoding="utf-8"))
        d["personagens"]["beto"] = {"nome": "Beto", "descricao": "técnico"}
        d["tomadas"][1]["personagens"].append("beto")
        ig.gravar_json_atomico(os.path.join(base, "producao.json"), d)
        pb.construir(base, modo="automatico")
        r = sup.pre_producao(base)
        assert not r["ok"] and any(p["codigo"] == "personagem_sem_referencia" for p in r["problemas"])
        assert pb.carregar(base)["aprovacao"]["estado"] == "pendente", "automático não aprova com problema grave"
        _png(os.path.join(base, "assets", "ficha-beto.png"), (20, 20, 20))
        d["personagens"]["beto"].update({"ficha": "assets/ficha-beto.png", "figurino": {"macacão": "cinza"}})
        ig.gravar_json_atomico(os.path.join(base, "producao.json"), d)
        pb.construir(base)
        r = sup.pre_producao(base)
        assert r["ok"] and r.get("aprovacao") == "automatica" and pb.portao(base)["liberado"]


def test_orquestrador_portao_da_biblia():
    with tempfile.TemporaryDirectory() as tmp:
        base = projeto_teste(tmp)
        d = json.load(open(os.path.join(base, "producao.json"), encoding="utf-8"))
        d["orcamento"] = {"aprovado": 10}
        antigo, _, _ = orquestrador.planejar(d)  # sem base: comportamento antigo, sem portão
        assert not any(g.get("bloqueado_biblia") for g in antigo)
        pb.construir(base)
        grupos, espera, _ = orquestrador.planejar(d, base)
        pagos = [g for g in grupos if g["custo"] > 0]
        assert pagos and all(g.get("bloqueado_biblia") and not g.get("reserva") for g in pagos)
        assert espera[0] == "prancha"
        pb.aprovar(base, "ok do usuário")
        grupos, espera, _ = orquestrador.planejar(d, base)
        assert "prancha" not in espera and not any(g.get("bloqueado_biblia") for g in grupos)
        d2 = {**d, "biblia_visual": True}
        g2, _, _ = orquestrador.planejar(d2, os.path.join(tmp, "outro"))
        assert any(g["tarefa"] == "construir_biblia" for g in g2)


if __name__ == "__main__":
    falhas = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_") and callable(f):
            try:
                f()
                print(f"ok   {nome}")
            except Exception as e:  # noqa: BLE001
                falhas += 1
                import traceback
                traceback.print_exc()
                print(f"FALHA {nome}: {e}")
    print(f"{'TUDO OK' if not falhas else f'{falhas} FALHA(S)'}")
    sys.exit(1 if falhas else 0)
