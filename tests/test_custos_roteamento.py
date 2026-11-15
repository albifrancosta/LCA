"""Testes de custo, roteamento e cache (auditoria P19–P24, P27, P28, P34–P39, P44).
Sem rede, sem API paga: catálogo, cache, livro-caixa e chamadas do fal/OpenAI são trocados por temporários/mocks.

Rodar:  python tests/test_custos_roteamento.py      (ou pytest, se houver)
"""
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import threading
import zlib

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))

import custos  # noqa: E402
import gerar_clipe_fal as gcf  # noqa: E402
import gerar_imagem  # noqa: E402
import roteador  # noqa: E402

MOD = {"id": "fake/mod", "tipo": "video", "provedor": "fal", "preco_unidade": 0.1, "unidade": "seconds", "qualidade_base": 3,
       "recursos": {"i2v": True, "duracoes": [5, 10]}}


def png_valido(arq):
    def bloco(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00\x00\x00\x00"
    dados = b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + \
        bloco(b"IDAT", zlib.compress(raw)) + bloco(b"IEND", b"")
    with open(arq, "wb") as f:
        f.write(dados)


@contextlib.contextmanager
def ambiente(modelos):
    """Catálogo/histórico/log do roteador + cache/livro-caixa do custos, tudo em pasta temporária."""
    with tempfile.TemporaryDirectory() as td:
        salvo = (roteador.CAT, roteador.HIST, roteador.LOG, custos.CACHE, custos.GERAL, os.environ.get("CV_PROJETO"))
        roteador.CAT = os.path.join(td, "catalogo.json")
        roteador.HIST = os.path.join(td, "hist.json")
        roteador.LOG = os.path.join(td, "log.jsonl")
        custos.CACHE = os.path.join(td, "cache")
        custos.GERAL = os.path.join(td, "custos-geral.jsonl")
        proj = os.path.join(td, "proj")
        os.makedirs(proj)
        open(os.path.join(proj, "producao.json"), "w").write("{}")
        os.environ["CV_PROJETO"] = proj
        with open(roteador.CAT, "w", encoding="utf-8") as f:
            json.dump({"modelos": modelos}, f)
        try:
            yield td, proj
        finally:
            roteador.CAT, roteador.HIST, roteador.LOG, custos.CACHE, custos.GERAL, cv = salvo
            if cv is None:
                os.environ.pop("CV_PROJETO", None)
            else:
                os.environ["CV_PROJETO"] = cv


def sem_rede(*a, **k):
    raise AssertionError("chamada de rede/pagamento não deveria acontecer")


def roda_main(modulo, argv):
    """Roda main() com argv; devolve (codigo_saida, saida_texto)."""
    velho = sys.argv
    sys.argv = [modulo.__name__ + ".py"] + argv
    out = io.StringIO()
    codigo = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            modulo.main()
    except SystemExit as e:
        codigo = e.code
    finally:
        sys.argv = velho
    return codigo, out.getvalue()


# ---------------- roteador ----------------

def test_p34_duracao_nao_coberta():
    preco, dur = roteador.preco_duracao(MOD, 15)
    assert (preco, dur) == (None, None), (preco, dur)
    assert roteador.preco_duracao(MOD, 6) == (1.0, 10.0)  # cobre para cima, não encurta
    with ambiente([MOD]):
        dec, _ = roteador.escolher("video", 15, "geral", registrar=False)
        assert dec["modelo"] is None and dec["motivo"] == roteador.SEM_MODELO, dec


def test_p35_piso_qualidade():
    with ambiente([dict(MOD, qualidade_base=1)]):
        for perfil in ("economico", "equilibrado", "premium"):
            dec, cands = roteador.escolher("video", 5, "acao", perfil=perfil, registrar=False)
            assert dec["modelo"] is None and dec["motivo"] == "sem_modelo_compativel", (perfil, dec)
            assert cands, "alternativas continuam listadas"
        dec, _ = roteador.escolher("video", 5, "paisagem", registrar=False)
        assert dec["modelo"] is None  # q1 < piso 2 também


def test_p36_token_sem_custo5s():
    tok = {"id": "fake/token", "tipo": "video", "provedor": "fal", "preco_unidade": 1.0, "unidade": "1m tokens",
           "qualidade_base": 3, "recursos": {"i2v": True, "duracoes": [5]}}
    assert roteador.preco_duracao(tok, 5) == (None, 5.0)
    assert roteador.preco_duracao(dict(tok, custo_5s=0.27), 5)[0] == 0.27
    from integridade import PrecoDesconhecido
    try:
        roteador.preco_conhecido(tok, 5)
        raise AssertionError("deveria levantar PrecoDesconhecido")
    except PrecoDesconhecido:
        pass
    with ambiente([tok]):
        dec, _ = roteador.escolher("video", 5, "geral", registrar=False)
        assert dec["modelo"] is None and "preço desconhecido" in dec["detalhe"], dec


def test_p37_capacidades():
    lip = {"id": "fake/avatar", "tipo": "lipsync", "provedor": "fal", "preco_unidade": 0.1, "unidade": "seconds", "qualidade_base": 3,
           "recursos": {"i2v": True, "parametros": ["audio_url", "image_url"]}}
    sem_uq = dict(MOD, id="fake/sem-uq")
    com_uq = dict(MOD, id="fake/com-uq", preco_unidade=0.2, recursos={"i2v": True, "primeiro_ultimo_quadro": True, "duracoes": [5, 10]})
    with ambiente([lip, sem_uq, com_uq]):
        dec, _ = roteador.escolher("video", 5, "rosto", capacidades={"i2v", "lip_sync"}, registrar=False)
        assert dec["modelo"] == "fake/avatar", dec
        dec, _ = roteador.escolher("video", 5, "geral", ultimo_quadro=True, registrar=False)
        assert dec["modelo"] == "fake/com-uq", dec
        dec, _ = roteador.escolher("video", 5, "geral", capacidades={"i2v", "ultimo_quadro"}, registrar=False)
        assert dec["modelo"] == "fake/com-uq", dec
        dec, _ = roteador.escolher("video", 5, "geral", registrar=False)
        assert dec["modelo"] == "fake/sem-uq", dec  # sem exigência: o mais barato
        dec, _ = roteador.escolher("video", 5, "geral", capacidades={"lip_sync", "identidade"}, registrar=False)
        assert dec["modelo"] is None and dec["motivo"] == "sem_modelo_compativel"
        dec, _ = roteador.escolher("video", 5, "texto", registrar=False)
        assert dec["modelo"] == "local/remotion-motion"  # CLI antigo continua


# ---------------- custos ----------------

def test_p38_projeto_producao_json():
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "producao.json"), "w").write("{}")
        sub = os.path.join(td, "remotion", "src")
        os.makedirs(sub)
        velho = os.environ.pop("CV_PROJETO", None)
        try:
            assert custos.projeto_atual(td) == os.path.abspath(td)
            assert custos.projeto_atual(sub) == os.path.abspath(td)
        finally:
            if velho is not None:
                os.environ["CV_PROJETO"] = velho


def test_p39_cache_vazio_e_corrompido():
    with ambiente([]) as (td, _):
        pasta = os.path.join(custos.CACHE, "clipe")
        os.makedirs(pasta)
        vazio = os.path.join(pasta, "abc.mp4")
        open(vazio, "wb").close()
        with contextlib.redirect_stderr(io.StringIO()):
            assert custos.cache_buscar("clipe", "abc", ".mp4") is None
        assert not os.path.exists(vazio), "entrada vazia deve ser apagada"
        lixo = os.path.join(pasta, "lixo.mp4")
        open(lixo, "wb").write(b"isto nao e um mp4")
        with contextlib.redirect_stderr(io.StringIO()):
            assert custos.cache_buscar("clipe", "lixo", ".mp4") is None
        assert not os.path.exists(lixo)
        # imagem válida: guarda (com sha256) e acha
        src = os.path.join(td, "a.png")
        png_valido(src)
        dest = custos.cache_guardar("imagem", "k1", src)
        assert dest and os.path.exists(dest + ".sha256")
        assert custos.cache_buscar("imagem", "k1", ".png") == dest
        # adulterada depois de guardada: sha256 não confere → descartada
        with open(dest, "ab") as f:
            f.write(b"x")
        with contextlib.redirect_stderr(io.StringIO()):
            assert custos.cache_buscar("imagem", "k1", ".png") is None
        assert not os.path.exists(dest)
        # não guarda arquivo vazio
        z = os.path.join(td, "z.png")
        open(z, "wb").close()
        with contextlib.redirect_stderr(io.StringIO()):
            assert custos.cache_guardar("imagem", "k2", z) is None


def test_p27_chave_por_conteudo():
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "base.png")
        open(f, "wb").write(b"v1")
        k1 = custos.cache_chave("clipe", imagem=f, refs=[f])
        from pathlib import Path
        assert custos.cache_chave("clipe", imagem=Path(f), refs=[f]) == k1  # Path conta como arquivo
        open(f, "wb").write(b"v2")
        assert custos.cache_chave("clipe", imagem=f, refs=[f]) != k1
        g = os.path.join(td, "outro.png")
        open(g, "wb").write(b"v2")
        assert custos.cache_chave("clipe", imagem=g, refs=[g]) == custos.cache_chave("clipe", imagem=f, refs=[f])  # conteúdo, não caminho


def test_p44_registrar_paralelo():
    with ambiente([]) as (td, proj):
        n = 24
        ths = [threading.Thread(target=custos.registrar, args=("clipe", "m", 0.01, f"c{i}")) for i in range(n)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        dados = json.load(open(os.path.join(proj, "custos.json"), encoding="utf-8"))
        assert len(dados) == n, len(dados)
        assert len(open(custos.GERAL, encoding="utf-8").read().splitlines()) == n
        item = custos.registrar("clipe", "m", None, "sem preço")
        assert item["valor_usd"] is None and item["preco_desconhecido"]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            custos.relatorio(proj)
        assert "PREÇO DESCONHECIDO" in out.getvalue()


# ---------------- gerar_clipe_fal ----------------

@contextlib.contextmanager
def fal_mockado(esquema_props=None):
    salvo = (gcf.pedir, gcf.esquema, gcf.baixar)
    gcf.pedir = sem_rede
    gcf.esquema = (lambda m: esquema_props or {})
    gcf.baixar = sem_rede
    try:
        yield
    finally:
        gcf.pedir, gcf.esquema, gcf.baixar = salvo


def test_p19_preco_desconhecido_bloqueia():
    with ambiente([MOD]) as (td, _), fal_mockado():
        assert gcf.custo("fake/nao-existe", 5) is None
        img = os.path.join(td, "i.png")
        png_valido(img)
        cod, out = roda_main(gcf, ["--imagem", img, "--prompt", "x", "-o", os.path.join(td, "c.mp4"), "--modelo", "fake/nao-existe"])
        assert cod in (0, None) and "preço desconhecido" in out, out
        cod, out = roda_main(gcf, ["--imagem", img, "--prompt", "x", "-o", os.path.join(td, "c.mp4"), "--modelo", "fake/nao-existe", "--confirmar"])
        assert cod and "recusado" in str(cod) + out, (cod, out)


def test_p20_corpo_para_rejeita_duracao():
    with fal_mockado({"prompt": {}, "image_url": {}, "duration": {"enum": ["5", "10"]}}):
        assert gcf.corpo_para("fake/mod", "p", "data:", "6")["duration"] == "10"
        try:
            gcf.corpo_para("fake/mod", "p", "data:", "15")
            raise AssertionError("deveria recusar 15 s")
        except SystemExit as e:
            assert "não entrega 15" in str(e.code) and "divida" in str(e.code)


def test_p21_orcamento_total_do_lote():
    with ambiente([MOD]) as (td, _), fal_mockado():
        proj = os.path.join(td, "lote")
        os.makedirs(os.path.join(proj, "assets", "img"))
        planos = [{"id": f"p0{i}", "clipe": {"movimento": "ele caminha devagar até a porta", "duracao": 5}} for i in (1, 2)]
        rot = os.path.join(proj, "roteiro.json")
        json.dump({"planos": planos}, open(rot, "w", encoding="utf-8"))
        cod, out = roda_main(gcf, ["--roteiro", rot, "--modelo", "fake/mod", "--orcamento", "0.6"])  # 2 × 0.50 = 1.00
        assert cod and "teto total" in str(cod), (cod, out)
        cod, out = roda_main(gcf, ["--roteiro", rot, "--modelo", "fake/mod", "--orcamento-por-clipe", "0.6"])
        assert cod in (0, None) and "Nada foi gerado" in out, (cod, out)
        cod, out = roda_main(gcf, ["--roteiro", rot, "--modelo", "fake/mod", "--orcamento-por-clipe", "0.4"])
        assert cod and "por clipe" in str(cod), (cod, out)


def test_p22_p23_lote_clipe_false_e_rota():
    rota_mod = dict(MOD, id="fake/rota", preco_unidade=0.05)
    with ambiente([MOD, rota_mod]) as (td, _), fal_mockado():
        proj = os.path.join(td, "lote")
        os.makedirs(os.path.join(proj, "assets", "img"))
        planos = [
            {"id": "p01", "clipe": False},
            {"id": "p02"},
            {"id": "p03", "clipe": {"movimento": "ela vira o rosto para a janela"},
             "direcao": {"rota": {"rota": "clipe", "modelo": "fake/rota", "dur": 5}}},
            {"id": "p04", "clipe": {"movimento": "ele fala olhando para a câmera"},
             "direcao": {"rota": {"rota": "avatar", "modelo": "fal-ai/kling-video/ai-avatar/v2/standard", "dur": 4}}},
            {"id": "p05", "clipe": {"movimento": "tela do celular com o app aberto"},
             "direcao": {"rota": {"rota": "motion", "modelo": "código (Remotion)", "dur": 3}}},
        ]
        rot = os.path.join(proj, "roteiro.json")
        json.dump({"planos": planos}, open(rot, "w", encoding="utf-8"))
        cod, out = roda_main(gcf, ["--roteiro", rot])
        assert cod in (0, None), (cod, out)
        assert "1 clipe(s)" in out and "fake/rota" in out and "rota do contrato" in out, out
        assert "lipsync.py" in out and "Remotion" in out, out


def test_p28_status_falha_terminal():
    with ambiente([MOD]) as (td, _), fal_mockado({"prompt": {}, "image_url": {}, "duration": {"enum": ["5", "10"]}}):
        respostas = iter([{"status_url": "https://q/status", "response_url": "https://q/resp", "request_id": "req-123"},
                          {"status": "IN_PROGRESS"}, {"status": "FAILED", "error": "nsfw"}])
        gcf.pedir = lambda url, corpo=None, tentativas=6: next(respostas)
        velho_sleep = gcf.time.sleep
        gcf.time.sleep = lambda s: None
        img = os.path.join(td, "i.png")
        png_valido(img)
        saida = os.path.join(td, "c.mp4")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                gcf.gerar(img, "prompt", saida, "fake/mod", "5")
            raise AssertionError("deveria parar no FAILED")
        except SystemExit as e:
            assert "FAILED" in str(e.code), e.code
        finally:
            gcf.time.sleep = velho_sleep
        meta = json.load(open(saida + ".json", encoding="utf-8"))
        assert meta["status"] == "FAILED" and meta["request_id"] == "req-123", meta
        assert not os.path.exists(os.path.join(os.environ["CV_PROJETO"], "custos.json"))  # nada lançado como pago


# ---------------- gerar_imagem ----------------

def test_p24_imagem_sem_confirmar():
    with ambiente([]) as (td, _):
        salvo = gerar_imagem.chamar
        gerar_imagem.chamar = sem_rede
        try:
            out = os.path.join(td, "a.png")
            cod, txt = roda_main(gerar_imagem, ["um gato", "-o", out])
            assert cod == 3 and "custo estimado" in txt and not os.path.exists(out), (cod, txt)
            # cache hit continua grátis e sem --confirmar
            campos = {"model": "gpt-image-2.5-sunburst", "prompt": "um gato", "size": "1024x1536", "quality": "medium", "n": 1}
            k = custos.cache_chave("imagem", **campos, refs=[])
            src = os.path.join(td, "src.png")
            png_valido(src)
            custos.cache_guardar("imagem", k, src)
            cod, txt = roda_main(gerar_imagem, ["um gato", "-o", out])
            assert cod in (0, None) and os.path.exists(out) and "cache" in txt, (cod, txt)
        finally:
            gerar_imagem.chamar = salvo


def main():
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    falhas = 0
    for nome, f in testes:
        try:
            f()
            print(f"PASS {nome}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"FAIL {nome}: {type(e).__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
