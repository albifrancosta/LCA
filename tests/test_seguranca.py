"""Segurança (auditoria SEC-02 e SEC-04): ambiente mínimo nos subprocessos e downloads só de bancos conhecidos.
Sem rede, sem gasto. Rodar: python tests/test_seguranca.py"""
import json
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import buscar_stock  # noqa: E402
import chaves  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SENSIVEIS = lambda k: k in chaves.CHAVES or k.startswith(("_CV_ORIGEM_", "CRIADOR_VIDEO_")) or k == "GITHUB_TOKEN"  # noqa: E731


def _isolar():
    salvo = {k: os.environ.pop(k) for k in list(os.environ) if SENSIVEIS(k)}
    reg = chaves._registro_windows
    chaves._registro_windows = lambda n: None
    d = tempfile.mkdtemp(prefix="seg-")
    os.environ["CRIADOR_VIDEO_ENV"] = os.path.join(d, ".env")
    chaves._carregado = False
    return salvo, reg, d


def _restaurar(salvo, reg, d):
    for k in [k for k in os.environ if SENSIVEIS(k)]:
        os.environ.pop(k)
    os.environ.update(salvo)
    chaves._registro_windows = reg
    chaves._carregado = False
    shutil.rmtree(d)


def test_filho_recebe_so_a_chave_do_provedor():
    salvo, reg, d = _isolar()
    try:
        os.environ.update({"FAL_KEY": "f-123", "OPENAI_API_KEY": "o-456", "GITHUB_TOKEN": "gh-789"})
        env = chaves.env_filho(["FAL_KEY"])
        assert env.get("FAL_KEY") == "f-123"
        assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env
        assert env["CRIADOR_VIDEO_CHAVES"] == "FAL_KEY" and env["PYTHONIOENCODING"] == "utf-8"
        assert any(k.upper() == "PATH" for k in env), "o filho precisa do PATH para achar ffmpeg/node"
    finally:
        _restaurar(salvo, reg, d)


def test_filho_do_estudio_nao_recebe_segredos_alheios():
    salvo, reg, d = _isolar()
    try:
        os.environ.update({"GEMINI_API_KEY": "g-1", "GITHUB_TOKEN": "gh-2"})
        env = chaves.env_filho()
        assert env.get("GEMINI_API_KEY") == "g-1" and "GITHUB_TOKEN" not in env
    finally:
        _restaurar(salvo, reg, d)


def test_filho_so_recarrega_do_env_o_que_foi_permitido():
    salvo, reg, d = _isolar()
    try:
        with open(os.environ["CRIADOR_VIDEO_ENV"], "w", encoding="utf-8") as f:
            f.write("FAL_KEY=f-env\nOPENAI_API_KEY=o-env\n")
        os.environ["CRIADOR_VIDEO_CHAVES"] = "FAL_KEY"
        chaves.carregar(forcar=True)
        assert os.environ.get("FAL_KEY") == "f-env"
        assert "OPENAI_API_KEY" not in os.environ, "chave não permitida não pode voltar pelo .env"
    finally:
        _restaurar(salvo, reg, d)


def test_download_de_banco_so_https_e_dominios_conhecidos():
    ok = ["https://videos.pexels.com/video-files/1/a.mp4", "https://cdn.pixabay.com/video/2025/x.mp4",
          "https://assets.mixkit.co/videos/1.mp4", "https://player.vimeo.com/external/1.hd.mp4"]
    ruins = ["http://cdn.pixabay.com/x.mp4", "https://192.168.0.10/x.mp4", "https://localhost/x.mp4",
             "file:///C:/Windows/win.ini", "https://pixabay.com.malicioso.net/x.mp4", "https://evilpexels.com/x.mp4",
             "https://vimeo.com.exemplo.net/x.mp4"]
    for u in ok:
        assert buscar_stock.url_permitida(u), u
    for u in ruins:
        assert not buscar_stock.url_permitida(u), u


def test_baixar_recusa_candidato_fora_da_lista_sem_tocar_na_rede():
    d = tempfile.mkdtemp(prefix="stock-")
    try:
        cand = {"cena": "01", "candidatos": [{"n": 1, "fonte": "pixabay", "id": 9, "arquivo": "https://127.0.0.1/x.mp4",
                                              "largura": 1, "altura": 1, "duracao": 1, "autor": "a", "pagina": "p",
                                              "termo": "t"}]}
        arq = os.path.join(d, "candidatos.json")
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(cand, f)

        def proibido(*a, **k):
            raise AssertionError("não podia abrir conexão")
        original = buscar_stock.urllib.request.urlopen
        buscar_stock.urllib.request.urlopen = proibido
        try:
            buscar_stock.cmd_baixar(type("A", (), {"candidatos": arq, "ids": "1"})())
        finally:
            buscar_stock.urllib.request.urlopen = original
        assert not [f for f in os.listdir(d) if f.endswith(".mp4")]
    finally:
        shutil.rmtree(d)


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
