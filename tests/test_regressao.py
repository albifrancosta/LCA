"""Regressão dos defeitos REAIS da MinhaMarca "O mesmo empresário em dois mundos" (2026-11-07) e das garantias novas da skill.
Sem rede, sem geração paga: vídeos sintéticos (ffmpeg testsrc), modelo visual e provedores FALSOS, memória temporária.
Rodar:  python tests/test_regressao.py

Casos: ausência de fichas · gravata involuntária · membros extras · interface na traseira · cifrões gerados ·
nota alta não compensa bloqueio · Freeze não intencional (por lado da tela dividida) · pausa intencional · antes × depois ·
orçamento concorrente · custo_zero · saldo do provedor · timeout pago não reenvia · recuperação na retomada ·
idempotência · invalidação seletiva · render desatualizado · decisão de duração uma vez · bloqueio sem repetir ·
correção de menor custo · acervo (reprovado nunca aprovado) · análise no livro + cache · benchmark sem custo ·
HyperFrames instalado · exceção do diretor nunca é aprovação limpa · adaptação editorial reinspeciona.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import integridade as ig  # noqa: E402
import provedores as pv  # noqa: E402
import projeto as pj  # noqa: E402
import qa_visual as qv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ELENCO = {"marcos": {"ref": "assets/referencia/ref-marcos.png", "tracos": ["cabelo castanho ondulado", "barba curta castanha"],
                     "figurino": ["camisa social lavanda, gola aberta com os dois primeiros botões abertos, pescoço à mostra",
                                  "calça jeans azul-escura", "smartwatch preto"]},
          "marina": {"ref": "assets/referencia/ref-marina.png", "tracos": ["cabelo castanho longo"], "figurino": ["blusa rosa", "brinco de argola dourado"]}}
REGRAS = {"ativo": True, "routing": {"policy": "free_first", "politicas_validas": ["free_first", "best_value", "lowest_cost", "premium", "manual"],
                                     "allow_paid_fallback": True, "retry": {"max_attempts_per_provider": 1, "backoff_base_s": 0.01, "backoff_max_s": 0.02},
                                     "circuit_breaker": {"falhas_para_abrir": 3, "esfriar_s": 600}},
          "budget": {"max_cost_per_operation": 5, "max_cost_per_video": 100, "default_unknown_cost_policy": "block", "margem_seguranca": 0},
          "quality": {"final": "high"}}
VIS_OK = {"criterios": [{"criterio": "sorri", "ok": True}], "identidade": [{"personagem": "marina", "rosto_igual_ficha": True}],
          "anatomia": [{"personagem": "marina", "bracos": 2, "maos": 2, "dedos_ok": True}], "figurino": [], "aparelhos": [],
          "textos_simbolos": [], "deformacoes": [], "qualidade_visual": 9, "nota": 9}
ACEITA = lambda s, t: {"aceito": True, "estado": "aprovado", "motivo": "ok"}  # noqa: E731


def png(arq, cor=(200, 120, 90)):
    from PIL import Image
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    Image.new("RGB", (64, 64), cor).save(arq)


def mp4(arq, dur=3.0, congela=0.0, tam="320x180", src="testsrc2"):
    """Clipe sintético que se mexe por `dur` s e (opcional) fica parado mais `congela` s (último quadro segurado)."""
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    vf = f"tpad=stop_mode=clone:stop_duration={congela}" if congela else "null"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size={tam}:rate=30:duration={dur}", "-vf", vf,
                    "-pix_fmt", "yuv420p", arq], check=True)


def projeto_base(planos=None, cfg=None):
    base = tempfile.mkdtemp(prefix="marca-reg-")
    for d in ("assets/img", "assets/clips", "assets/voz", "assets/referencia", "entrega", "remotion/src", "remotion/public/f"):
        os.makedirs(os.path.join(base, d))
    png(os.path.join(base, "assets/referencia/ref-marcos.png"))
    png(os.path.join(base, "assets/referencia/ref-marina.png"), (230, 150, 170))
    ps = planos or [{"id": "c06c", "quem": ["marina"], "fala": "", "direcao": {"modo": "reacao", "duracao": 3.0, "quem": ["marina"],
                                                                             "acao": "Marina segura o tablet e sorri", "voz": "off"}}]
    json.dump({"titulo": "teste", "formato": "16:9", "elenco": ELENCO, "planos": ps}, io.open(os.path.join(base, "roteiro.json"), "w", encoding="utf-8"))
    if cfg is not None:
        json.dump(cfg, io.open(os.path.join(base, "projeto.json"), "w", encoding="utf-8"))
    return base


def roteiro(base):
    return json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))


class Mem:
    """Catálogo/regras/memória do roteador numa pasta temporária."""

    def __init__(self, provs=(), regras=None):
        self.provs, self.regras = list(provs), regras or REGRAS

    def __enter__(self):
        self.td = tempfile.mkdtemp(prefix="marca-mem-")
        self.salvo = (pv.CFG_PROV, pv.CFG_ROT, pv.MEM)
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = (os.path.join(self.td, "p.json"), os.path.join(self.td, "r.json"), os.path.join(self.td, "mem"))
        json.dump({"provedores": self.provs}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        json.dump(self.regras, open(pv.CFG_ROT, "w", encoding="utf-8"))
        return self

    def __exit__(self, *a):
        pv.CFG_PROV, pv.CFG_ROT, pv.MEM = self.salvo


def prov(pid, preco=0.35, adaptador="Falso", stage="video"):
    return {"id": pid, "enabled": True, "stage": stage, "adaptador": adaptador, "model": pid, "tier": "paid" if preco else "free",
            "commercial_use": "allowed", "languages": ["*"], "capabilities": [stage, "i2v"], "quality": "high", "referencias_preservadas": True,
            "price": {"unit": "clip", "amount_per_unit": preco}}


def executar(t, cls):
    return pv.executar(t, adaptadores={cls.__name__: cls}, inspecionar=ACEITA, dormir=lambda s: None, credencial=lambda e: True)


# ---------------------------------------------------------------- continuidade / inspeção visual
def test_fichas_por_caminho_explicito_e_ausencia_vira_pendencia():
    import inspetor
    base = projeto_base()
    # bug real: procurava ../producao.json (pasta de TODOS os projetos) e nunca mandava ficha — agora vem do roteiro.elenco
    assert inspetor.fichas_de(base, ["marina"]) == [os.path.normpath(os.path.join(base, "assets/referencia/ref-marina.png"))]
    refs, falt = qv.referencias(base, roteiro(base), ["marina", "joao"])
    assert [r["personagem"] for r in refs] == ["marina"] and falt == ["joao"] and refs[0]["origem"] == "roteiro.elenco"
    os.remove(os.path.join(base, "assets/referencia/ref-marina.png"))  # ficha sumiu → identidade nunca é aprovada
    d = roteiro(base)
    refs, falt = qv.referencias(base, d, ["marina"])
    r = {"problemas": [], "pendencias": []}
    inspetor.aplicar_visual(r, VIS_OK, d["planos"][0]["direcao"], d, ["marina"], refs, falt)
    assert any("sem ficha de marina" in p for p in r["pendencias"])
    assert ig.estado_qa(r["problemas"], verificado=not r["pendencias"]) == ig.NAO_VERIFICADO
    shutil.rmtree(base)


def test_producao_json_do_projeto_e_achado():
    base = projeto_base()
    json.dump({"personagens": {"marcos": {"ficha": "assets/referencia/ref-marcos.png"}}}, io.open(os.path.join(base, "producao.json"), "w", encoding="utf-8"))
    refs, falt = qv.referencias(base, {"planos": []}, ["marcos"])
    assert refs and refs[0]["origem"] == "producao.json" and not falt
    shutil.rmtree(base)


def test_gravata_involuntaria_bloqueia_e_ficha_nao_e_falso_positivo():
    c = {"quem": ["marcos"], "acao": "Marcos fala com a câmera"}
    vis = dict(VIS_OK, figurino=[{"personagem": "marcos", "peca": "gravata azul", "na_ficha": False, "no_corpo": True, "segundo": 3.4},
                                 {"personagem": "marcos", "peca": "smartwatch preto", "na_ficha": True, "no_corpo": True}])
    assert [cod for g, cod, _ in qv.bloqueios(vis, c, ELENCO, ["marcos"]) if g == "grave"] == ["figurino_involuntario"]
    # o modelo às vezes diz na_ficha=false para o que ESTÁ na ficha: o texto da ficha decide
    vis2 = dict(VIS_OK, figurino=[{"personagem": "marcos", "peca": "smartwatch", "na_ficha": False, "no_corpo": True}])
    assert not [x for x in qv.bloqueios(vis2, c, ELENCO, ["marcos"]) if x[0] == "grave"]


def test_membros_extras_bloqueiam_mesmo_com_nota_alta():
    import inspetor
    c = {"quem": ["marina"], "acao": "Marina segura o tablet e gesticula", "criterios": ["sorri"]}
    vis = dict(VIS_OK, anatomia=[{"personagem": "marina", "bracos": 3, "maos": 3, "segundo": 1.2, "visto": "terceiro braço no tablet"}],
               nota=10, qualidade_visual=10, aparelhos=[{"objeto": "tablet", "quem_usa": "marina", "tela_voltada_para": "usuario"}])
    r = {"problemas": [], "pendencias": []}
    inspetor.aplicar_visual(r, vis, c, {"elenco": ELENCO}, ["marina"], [{"personagem": "marina", "sha256": "x" * 64, "origem": "t"}], [])
    assert "membros_extras" in r["bloqueios"] and r["completude_contrato"] == 100 and r["qualidade_visual"] == 10
    assert ig.estado_qa(r["problemas"], verificado=True) == ig.REPROVADO  # nota 10 não compensa defeito grave


def test_interface_na_traseira_e_sem_evidencia_de_aparelho():
    c = {"quem": ["marcos"], "acao": "Marcos olha o celular"}
    vis = dict(VIS_OK, aparelhos=[{"objeto": "celular", "quem_usa": "marcos", "tela_voltada_para": "camera", "interface_desenhada_na_traseira": True}])
    assert any(cod == "interface_traseira" for g, cod, _ in qv.bloqueios(vis, c, ELENCO, ["marcos"]) if g == "grave")
    sem = {k: v for k, v in VIS_OK.items() if k != "aparelhos"}
    assert "orientação dos aparelhos" in qv.evidencia_faltando(sem, c, ["marcos"])  # sem resposta = não verificado


def test_cifroes_gerados_pelo_clipe_bloqueiam_e_simbolo_permitido_passa():
    c = {"quem": ["marcos"], "acao": "Marcos fica em dúvida"}
    vis = dict(VIS_OK, textos_simbolos=[{"conteudo": "$ $ $", "onde": "no ar", "segundo": 1.0}])
    assert any(cod == "texto_simbolo_gerado" for g, cod, _ in qv.bloqueios(vis, c, ELENCO, ["marcos"]) if g == "grave")
    vis2 = dict(VIS_OK, textos_simbolos=[{"conteudo": "?", "onde": "no ar"}])
    assert not qv.bloqueios(vis2, dict(c, simbolos_permitidos=["?"]), ELENCO, ["marcos"])


def test_analise_visual_usa_cache_e_cobra_no_livro_do_projeto():
    import inspetor
    base = projeto_base(cfg={"autonomia": {"modo": "teto", "job_id": "marca-teste"}, "orcamento": {"teto_autorizado": 1.0}})
    img = os.path.join(base, "assets/img/c06c.png")
    png(img)
    chamadas = []

    def falso(arquivo, texto, refs, modelo):
        chamadas.append((arquivo, list(refs)))
        assert "Conte braços e mãos" in texto and refs  # pedido único com anatomia + as fichas reais
        return dict(VIS_OK, _uso={"promptTokenCount": 2000, "candidatesTokenCount": 500})
    with Mem():
        d = roteiro(base)
        c = d["planos"][0]["direcao"]
        inspetor.analisar_visual(base, img, c, d, ["marina"], "c06c", "imagem", chamar=falso)
        v2, _, _ = inspetor.analisar_visual(base, img, c, d, ["marina"], "c06c", "imagem", chamar=falso)
        assert len(chamadas) == 1 and v2.get("_cache")  # mesmo hash + mesma versão das regras = não paga de novo
        o = pj.orcamento(pj.carregar(base))
        assert o["por_categoria"].get("analise", 0) > 0 and o["gasto_confirmado"] > 0  # custo real = uso × preço oficial
        json.dump({"autonomia": {"modo": "custo_zero", "job_id": "marca-teste"}}, io.open(os.path.join(base, "projeto.json"), "w", encoding="utf-8"))
        png(img, (10, 10, 10))  # imagem nova; modo custo_zero → análise paga bloqueada, vira revisão pela folha
        v3, _, _ = inspetor.analisar_visual(base, img, c, d, ["marina"], "c06c", "imagem", chamar=falso)
        assert "indisponivel" in v3 and len(chamadas) == 1
    shutil.rmtree(base)


# ---------------------------------------------------------------- montagem (MP4 final)
def _split(base, dir_dur, dir_congela, saida):
    esq, dir_ = os.path.join(base, "remotion/public/f/c10e.mp4"), os.path.join(base, "remotion/public/f/c10d.mp4")
    mp4(esq, 4.0)
    mp4(dir_, dir_dur)
    filme_dir = os.path.join(base, "tmp-dir.mp4")
    mp4(filme_dir, dir_dur, congela=dir_congela)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", esq, "-i", filme_dir, "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]",
                    "-t", "4", "-pix_fmt", "yuv420p", saida], check=True)


def projeto_split(pausa=None):
    ps = [{"id": "c10e", "quem": ["marcos"], "direcao": {"modo": "acao", "duracao": 4.0, "quem": ["marcos"]}},
          {"id": "c10d", "quem": ["marcos"], "direcao": dict({"modo": "acao", "duracao": 4.0, "quem": ["marcos"]},
                                                           **({"pausa_intencional": pausa} if pausa else {}))}]
    base = projeto_base(ps)
    json.dump({"planos": [{"id": "c10", "inicio": 0.0, "fim": 4.0, "tipo": "dividida",
                           "inclui": [{"id": "c10e", "midia": {"arquivo": "remotion/public/f/c10e.mp4"}},
                                      {"id": "c10d", "midia": {"arquivo": "remotion/public/f/c10d.mp4"}}]}], "legenda": []},
              io.open(os.path.join(base, "remotion/src/historia.json"), "w", encoding="utf-8"))
    return base


def test_freeze_no_fim_de_um_lado_da_tela_dividida():
    import movimento
    import qa_montagem as qm
    base = projeto_split()
    filme = os.path.join(base, "entrega/filme.mp4")
    _split(base, 3.0, 1.0, filme)  # c10d: clipe de 3 s num plano de 4 s → último quadro segurado 1 s (o caso real)
    v, _, _ = movimento.analisar(filme)
    assert v["veredito"] == "animado"  # o quadro INTEIRO se mexe (lado esquerdo): o inspetor antigo passava
    res, dur, _ = qm.analisar_filme(base, filme, folhas=False)
    r = res[0]
    lado = {rg["id"]: rg for rg in r["regioes"]}
    assert lado["c10d"]["regiao"] == "dir" and lado["c10e"]["regiao"] == "esq"
    assert any(c["tipo"] == "fim_preenchido" and c["posicao"] == "fim" for c in lado["c10d"]["congelamentos"]), lado["c10d"]
    assert not lado["c10e"]["congelamentos"]
    assert r["estado"] == ig.REPROVADO and any("c10d (dir): fim de clipe preenchido com Freeze" in t for g, t in r["problemas"] if g == "grave")
    assert abs(dur["mp4"] - 4.0) < 0.1
    shutil.rmtree(base)


def test_pausa_intencional_nao_e_defeito():
    import qa_montagem as qm
    base = projeto_split(pausa=[[2.9, 4.0]])
    filme = os.path.join(base, "entrega/filme.mp4")
    _split(base, 3.0, 1.0, filme)
    r = qm.analisar_filme(base, filme, folhas=False)[0][0]
    assert not [p for p in r["problemas"] if p[0] == "grave"], r["problemas"]
    assert any(c["tipo"] == "pausa_intencional" for rg in r["regioes"] for c in rg["congelamentos"])
    shutil.rmtree(base)


def test_comparar_antes_e_depois_da_correcao_no_render():
    import qa_montagem as qm
    base = projeto_split()
    antes, depois = os.path.join(base, "entrega/antes.mp4"), os.path.join(base, "entrega/depois.mp4")
    _split(base, 3.0, 1.0, antes)
    _split(base, 4.0, 0.0, depois)  # correção: clipe cobre o plano inteiro
    assert qm.comparar(base, antes, depois, "c10")["resolvido"] is True
    shutil.rmtree(base)


# ---------------------------------------------------------------- orçamento / custos
def _t(base_proj=None, cena="s1", job="marca-teste"):
    t = {"job_id": job, "scene_id": cena, "task_type": "video", "requirements": {"duration_s": 5}, "budget": {}}
    if base_proj:
        t["projeto"] = base_proj
    return pv.normalizar(t, REGRAS)


def test_orcamento_concorrente_nunca_passa_do_teto():
    base = projeto_base(cfg={"autonomia": {"modo": "teto", "job_id": "marca-teste"}, "orcamento": {"teto_autorizado": 1.0}})
    with Mem():
        t = _t(base)
        oks = []

        def um():
            oks.append(pv.autorizar(t, {"id": "fal"}, 0.15, REGRAS)["ok"])
        th = [threading.Thread(target=um) for _ in range(20)]
        [x.start() for x in th]
        [x.join() for x in th]
        assert sum(oks) == 6, sum(oks)  # 6 × 0,15 = 0,90 ≤ 1,00; o 7º passaria
        o = pj.orcamento(pj.carregar(base))
        assert abs(o["reservas_abertas"] - 0.90) < 1e-9 and o["livre"] <= 0.10 + 1e-9
    shutil.rmtree(base)


def test_custo_zero_e_saldo_do_provedor_bloqueiam():
    base = projeto_base(cfg={"autonomia": {"modo": "custo_zero", "job_id": "marca-teste"}})
    with Mem():
        a = pv.autorizar(_t(base), {"id": "fal"}, 0.35, REGRAS)
        assert not a["ok"] and a["estado"] == "bloqueado" and "custo_zero" in a["motivo"]
        assert pv.autorizar(_t(base), {"id": "fal"}, None, REGRAS)["estado"] == "bloqueado"  # desconhecido também
        assert pv.autorizar(_t(base), {"id": "hf"}, 0.0, REGRAS)["ok"]  # grátis comprovado passa
        assert _t(base)["commercial_use"] is True  # uso padrão = publicidade → licença comercial exigida
    json.dump({"autonomia": {"modo": "teto", "job_id": "marca-teste"}, "orcamento": {"teto_autorizado": 22, "saldo_provedor": {"fal": 0.0}}},
              io.open(os.path.join(base, "projeto.json"), "w", encoding="utf-8"))
    with Mem():
        a = pv.autorizar(_t(base), {"id": "fal"}, 0.35, REGRAS)
        assert not a["ok"] and "saldo informado" in a["motivo"]  # saldo do fal acabou: nem tenta
    shutil.rmtree(base)


class Timeout:
    n = 0

    def __init__(self, p):
        self.p = p

    def executar(self, t, tid):
        Timeout.n += 1
        raise pv.ErroProvedor("timeout_ambiguo", "tempo esgotado", job_remoto="req-123")


class Recupera(Timeout):
    def recuperar(self, t, evento):
        assert evento.get("job_remoto") == "req-123"
        mp4(t["requirements"]["saida"], 1.0)
        return {"saida": t["requirements"]["saida"], "custo_real": None}


def test_timeout_pago_nao_reenvia_e_retomada_recupera_antes():
    td = tempfile.mkdtemp(prefix="marca-to-")
    with Mem([prov("fal-pago", 0.35, "Timeout")]):
        t = {"job_id": "v", "scene_id": "c07a", "task_type": "video", "requirements": {"duration_s": 5, "saida": os.path.join(td, "c07a.mp4")}}
        Timeout.n = 0
        assert executar(t, Timeout)["status"] == "pendente_verificacao" and Timeout.n == 1
        assert executar(t, Timeout)["status"] == "pendente_verificacao" and Timeout.n == 1  # retomada: NÃO envia outro job pago
        assert len(pv.jobs_pendentes("v", "c07a")) == 1
        provs = [dict(prov("fal-pago", 0.35, "Recupera"))]
        json.dump({"provedores": provs}, open(pv.CFG_PROV, "w", encoding="utf-8"))
        r3 = executar(t, Recupera)
        assert r3["status"] == "success" and r3.get("recuperado") and Timeout.n == 1  # baixou o job antigo, sem pagar de novo
        assert not pv.jobs_pendentes("v", "c07a")
        rs = pv.ler(pv.caminhos()["reservas"], {})["reservas"]
        assert len(rs) == 1 and rs[0]["estado"] == "reconciliada" and rs[0]["real"] is None  # cobrança desconhecida conta pelo reservado
    shutil.rmtree(td)


class Gera:
    n = 0

    def __init__(self, p):
        self.p = p

    def executar(self, t, tid):
        Gera.n += 1
        mp4(t["requirements"]["saida"], 1.0)
        return {"saida": t["requirements"]["saida"], "custo_real": 0.35}


def test_idempotencia_mesmo_pedido_nao_paga_duas_vezes():
    td = tempfile.mkdtemp(prefix="marca-id-")
    png(os.path.join(td, "img.png"))
    with Mem([prov("fal-pago", 0.35, "Gera")]):
        t = {"job_id": "v", "scene_id": "c05a", "task_type": "video",
             "requirements": {"duration_s": 5, "imagem": os.path.join(td, "img.png"), "prompt": "x", "saida": os.path.join(td, "a.mp4")}}
        Gera.n = 0
        executar(t, Gera)
        t2 = json.loads(json.dumps(t))
        t2["requirements"]["saida"] = os.path.join(td, "b.mp4")
        r = executar(t2, Gera)
        assert Gera.n == 1 and r["cache"] and os.path.isfile(os.path.join(td, "b.mp4"))
        png(os.path.join(td, "img.png"), (1, 2, 3))  # imagem-chave mudou → é outro pedido
        t2["requirements"]["saida"] = os.path.join(td, "c.mp4")
        executar(t2, Gera)
        assert Gera.n == 2
    shutil.rmtree(td)


def test_bloqueio_pendente_nao_repete_a_mensagem():
    with Mem():
        t = _t()
        pv.pendente_aprovacao(t, ["fal: o vídeo iria a US$ 3.20 (teto US$ 3.10)"])
        pv.pendente_aprovacao(t, ["fal: o vídeo iria a US$ 3.45 (teto US$ 3.10)"])
        ps = pv.ler(pv.caminhos()["pendentes"], {})["pendentes"]
        assert len(ps) == 1 and ps[0]["repeticoes"] == 2


# ---------------------------------------------------------------- estado da produção
def test_invalidacao_seletiva_e_render_desatualizado():
    import estado_producao as ep
    ps = [{"id": "c06c", "quem": ["marina"], "direcao": {"modo": "reacao", "duracao": 1.0, "quem": ["marina"]}},
          {"id": "c07a", "quem": ["marcos"], "direcao": {"modo": "acao", "duracao": 1.0, "quem": ["marcos"]}}]
    base = projeto_base(ps)
    for pid in ("c06c", "c07a"):
        png(os.path.join(base, f"assets/img/{pid}.png"))
        mp4(os.path.join(base, f"assets/clips/{pid}.mp4"), 1.0)
    open(os.path.join(base, "remotion/src/Filme.tsx"), "w").write("// v1")
    itens = [{"id": pid, "estado": "aprovado", "sha256_clipe": ig.sha256(os.path.join(base, f"assets/clips/{pid}.mp4"))} for pid in ("c06c", "c07a")]
    json.dump({"itens": itens}, io.open(os.path.join(base, "entrega/inspecao-planos.json"), "w", encoding="utf-8"))
    r = ep.sincronizar(base)
    assert r["nos"]["clipe:c06c"]["estado"] == "inspecionado" and r["nos"]["clipe:c07a"]["estado"] == "inspecionado"
    filme = os.path.join(base, "entrega/filme.mp4")
    mp4(filme, 1.0)
    ep.registrar_render(base, filme)
    assert ep.render_atual(base, filme)["estado"] == "atual"
    d = roteiro(base)
    d["planos"][0]["direcao"]["acao"] = "Marina segura o tablet com UMA mão"  # contrato de c06c mudou
    json.dump(d, io.open(os.path.join(base, "roteiro.json"), "w", encoding="utf-8"))
    r = ep.sincronizar(base)
    assert r["nos"]["clipe:c06c"]["estado"] == "gerado"  # precisa reinspecionar
    assert r["nos"]["clipe:c07a"]["estado"] == "inspecionado"  # o resto não muda
    assert any(i["no"] == "clipe:c06c" for i in r["invalidados"]) and not any(i["no"] == "clipe:c07a" for i in r["invalidados"])
    mp4(os.path.join(base, "assets/clips/c07a.mp4"), 1.2)  # clipe trocado depois do render
    ra = ep.render_atual(base, filme)
    assert ra["estado"] == "desatualizado" and "clipe:c07a" in ra["mudou"]
    shutil.rmtree(base)


def test_inspetor_filme_acusa_render_desatualizado():
    import estado_producao as ep
    import inspetor
    base = projeto_split()
    filme = os.path.join(base, "entrega/filme.mp4")
    _split(base, 4.0, 0.0, filme)
    ep.registrar_render(base, filme)
    open(os.path.join(base, "remotion/src/Filme.tsx"), "w").write("// mudou depois do render")
    salvo = inspetor.palavras
    inspetor.palavras = lambda *a, **k: []
    try:
        res, _ = inspetor.inspecionar_filme(base, roteiro(base), filme)
    finally:
        inspetor.palavras = salvo
    rend = next(x for x in res if x["id"] == "render")
    assert rend["estado"] == ig.REPROVADO and "composicao" in rend["problemas"][0][1]
    shutil.rmtree(base)


def test_decisao_de_duracao_registrada_uma_vez_e_frames_coerentes():
    base = projeto_base(cfg={"duracao": {"segundos": 90, "fps": 30, "tolerancia_pct": 5}})
    cfg = pj.carregar(base)
    assert cfg["duracao"]["frames"] == 2700 and not cfg["_problemas"]
    a = pj.resolver_duracao(cfg, 94.2)
    b = pj.resolver_duracao(cfg, 94.2)
    assert a["estado"] == "aceita_na_tolerancia" and a["nova"] and not b["nova"]
    assert len(json.load(io.open(pj.decisoes_arq(base), encoding="utf-8"))["decisoes"]) == 1
    assert pj.resolver_duracao(cfg, 100.0)["estado"] == "fora"
    pj.avaliar(base, 8, "usuario", "assistiu e apontou 5 defeitos")
    av = json.load(io.open(os.path.join(base, "entrega/avaliacao-editorial.json"), encoding="utf-8"))["avaliacoes"][0]
    assert av["nota"] == 8 and av["tipo"] == "editorial"
    shutil.rmtree(base)


# ---------------------------------------------------------------- correções de menor custo / exceções
def test_correcao_mais_barata_e_montagem_nunca_regenera():
    import correcoes as cr
    ctx = {"custo_clipe": 0.35, "custo_imagem": 0.05, "taxa": 0.6, "tentativas_restantes": 2, "gasto_restante": 2.0, "minutos_restantes": 30}
    assert cr.escolher(["texto_simbolo_gerado"], ctx)[0]["opcao"] == "overlay"  # c03a cifrões
    p = cr.escolher(["fim_preenchido"], ctx)[0]
    assert p["opcao"] == "recomposicao" and not p["gasta"]  # c10d Freeze: é montagem
    assert all(not x["opcao"].startswith("regenerar") for x in cr.escolher(["congelamento", "repeticao", "legenda"], ctx))
    g = cr.escolher(["figurino_involuntario"], dict(ctx, defeito_em=3.6, dur_clipe=5.0, dur_plano=4.0))[0]
    assert g["opcao"] == "corte"  # c02e: gravata só no fim → usa o trecho limpo
    assert cr.escolher(["interface_traseira"], dict(ctx, defeito_na_imagem=True))[0]["opcao"] == "regenerar_imagem"  # c06c/c07a
    esgotado = cr.escolher(["membros_extras"], dict(ctx, tentativas_restantes=0))[0]
    assert esgotado["opcao"] == "ressalva" and not esgotado["gasta"]
    assert cr.classificar([("grave", "c10d (dir): fim de clipe preenchido com Freeze 3.0–4.0s")]) == ["fim_preenchido"]


def test_excecao_do_diretor_nunca_vira_aprovacao_limpa_e_adaptacao_reinspeciona():
    import inspetor
    base = projeto_base([{"id": "c03c", "quem": ["marcos"], "fala": "quanto eu faturei?",
                          "direcao": {"modo": "fala", "duracao": 3.0, "quem": ["marcos"], "voz": "em_quadro"}}])
    clip = os.path.join(base, "assets/clips/c03c.mp4")
    mp4(clip, 3.0)
    item = {"id": "c03c", "estado": "reprovado", "veredito": "reprovado", "sha256_clipe": ig.sha256(clip), "problemas": [["grave", "lip-sync: boca_parada"]]}
    json.dump({"itens": [item]}, io.open(os.path.join(base, "entrega/inspecao-planos.json"), "w", encoding="utf-8"))
    inspetor.adaptar(os.path.join(base, "roteiro.json"), "c03c", {"voz": "off"}, "fala vira pensamento em off")
    ins = json.load(io.open(os.path.join(base, "entrega/inspecao-planos.json"), encoding="utf-8"))["itens"][0]
    assert ins["estado"] == ig.NAO_VERIFICADO and ins["reprovacoes_originais"][0]["estado"] == "reprovado"
    assert roteiro(base)["planos"][0]["direcao"]["voz"] == "off" and any(f.startswith("roteiro-antes-adaptacao-c03c") for f in os.listdir(base))
    ad = json.load(io.open(os.path.join(base, "entrega/adaptacoes.json"), encoding="utf-8"))["adaptacoes"][0]
    assert ad["reprovacao_original"]["problemas"] and ad["contrato_antes"]["voz"] == "em_quadro"
    ins.update(estado="nao_verificado", problemas=[["media", "boca pouco ativa"]], pendencias=["x"])
    json.dump({"itens": [ins]}, io.open(os.path.join(base, "entrega/inspecao-planos.json"), "w", encoding="utf-8"))
    inspetor.revisar(base, ["c03c"], ig.APROVADO, "pensamento em off: boca fechada é correta")
    fim = json.load(io.open(os.path.join(base, "entrega/inspecao-planos.json"), encoding="utf-8"))["itens"][0]
    assert fim["veredito"] == "aprovado_com_excecao" and fim["excecao_diretor"] and len(fim["reprovacoes_originais"]) == 2
    shutil.rmtree(base)


def test_revisao_nao_derruba_bloqueio_objetivo():
    import inspetor
    base = projeto_base()
    clip = os.path.join(base, "assets/clips/c06c.mp4")
    mp4(clip, 1.0)
    json.dump({"itens": [{"id": "c06c", "estado": "nao_verificado", "sha256_clipe": ig.sha256(clip), "problemas": [],
                          "bloqueios": ["membros_extras"]}]}, io.open(os.path.join(base, "entrega/inspecao-planos.json"), "w", encoding="utf-8"))
    try:
        inspetor.revisar(base, ["c06c"], ig.APROVADO, "parece ok")
        raise AssertionError("deveria recusar")
    except SystemExit as e:
        assert "bloqueio objetivo" in str(e)
    shutil.rmtree(base)


# ---------------------------------------------------------------- catálogo / benchmark / hyperframes
def test_acervo_reprovado_nunca_entra_como_aprovado():
    import acervo
    base = projeto_base()
    mp4(os.path.join(base, "assets/clips/c06c.mp4"), 1.0)
    mp4(os.path.join(base, "assets/clips/rejeitados/c06c-t1.mp4"), 1.0, src="testsrc")
    json.dump({"itens": [{"id": "c06c", "estado": "aprovado", "sha256_clipe": ig.sha256(os.path.join(base, "assets/clips/c06c.mp4"))}]},
              io.open(os.path.join(base, "entrega/inspecao-planos.json"), "w", encoding="utf-8"))
    arq = os.path.join(base, "acervo.json")
    acervo.indexar(base, arq)
    r = acervo.buscar("c06c marina", "clipe", arq_acervo=arq)
    assert len(r["reuso_direto"]) == 1 and r["reuso_direto"][0]["qualidade"] == "aprovado"
    assert [x["uso"] for x in r["referencia"]] == ["referencia_negativa"]
    try:
        acervo.usar(r["referencia"][0]["id"], base, "c99", arq)
        raise AssertionError("deveria recusar")
    except SystemExit as e:
        assert "reprovado" in str(e)
    n = len(acervo.ler(arq)["itens"])
    acervo.indexar(base, arq)  # reindexar não duplica
    assert len(acervo.ler(arq)["itens"]) == n
    bib = os.path.join(base, "bib.md")
    open(bib, "w", encoding="utf-8").write("# Biblioteca\n\ntexto manual\n")
    acervo.resumo(arq, bib)
    acervo.resumo(arq, bib)
    txt = open(bib, encoding="utf-8").read()
    assert "texto manual" in txt and txt.count("ACERVO:INICIO") == 1
    shutil.rmtree(base)


def test_benchmark_so_planeja_e_desconhecido_nao_e_zero():
    import benchmark_provedores as bp
    with Mem([prov("a", 0.35), dict(prov("b", 0.0), price={"unit": "clip", "amount_per_unit": None})]):
        p = bp.planejar(gravar=False)
        assert p["precos_desconhecidos"] == ["b"] and abs(p["total_estimado_habilitados"] - 0.35 * len(bp.CASOS)) < 1e-9


def test_hyperframes_instalado_pela_versao_registrada():
    import referencia_reversa as rr
    td = tempfile.mkdtemp(prefix="marca-hf-")
    inst = os.path.join(td, "cache", "hyperframes", "0.9.5")
    os.makedirs(os.path.join(inst, "skills", "reverse-any-video"))
    open(os.path.join(inst, "skills", "reverse-any-video", "SKILL.md"), "w").write("x")
    reg = os.path.join(td, "installed_plugins.json")
    json.dump({"plugins": {"hyperframes@hyperframes": [{"installPath": inst, "version": "0.9.5", "lastUpdated": "2026-11-02"}]}}, open(reg, "w"))
    info = rr.instalado(reg)
    assert info["versao"] == "0.9.5" and info["skill"]
    r = rr.ritmo([1.0, 2.5, 4.0], 6.0)
    assert r["planos"] == 4 and r["media_s"] == 1.5
    shutil.rmtree(td)


def rodar(ns):
    testes = [(k, v) for k, v in ns.items() if k.startswith("test_") and callable(v)]
    ok = 0
    for nome, f in testes:
        try:
            f()
            ok += 1
            print(f"✅ {nome}")
        except Exception as e:  # noqa: BLE001
            print(f"❌ {nome} {type(e).__name__}: {e}")
            traceback.print_exc(limit=4)
    print(f"\n{ok}/{len(testes)} passaram")
    sys.exit(0 if ok == len(testes) else 1)


if __name__ == "__main__":
    rodar(globals())
