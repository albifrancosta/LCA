"""Testes das chaves de API (chaves.py / configurar.py) — sem rede, sem gasto, sem tocar no seu .env real.
Rodar: python tests/test_chaves.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AQUI, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import chaves  # noqa: E402
import configurar  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SEGREDO = "sk-teste-NAO-PODE-APARECER-1234567890"


class Isolado:
    """Ambiente sem nenhuma chave: limpa variáveis, desliga o registro do Windows e aponta o .env para uma pasta temporária."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="chaves-")
        self.env = os.path.join(self.dir, ".env")
        self.salvo = {k: os.environ.pop(k) for k in list(os.environ) if k in chaves.CHAVES or k.startswith("_CV_ORIGEM_")}
        self.antigo_env = os.environ.get("CRIADOR_VIDEO_ENV")
        os.environ["CRIADOR_VIDEO_ENV"] = self.env
        self.reg = chaves._registro_windows
        chaves._registro_windows = lambda n: None
        chaves._carregado = False
        return self

    def __exit__(self, *a):
        for k in [k for k in os.environ if k in chaves.CHAVES or k.startswith("_CV_ORIGEM_")]:
            os.environ.pop(k)
        os.environ.update(self.salvo)
        if self.antigo_env is None:
            os.environ.pop("CRIADOR_VIDEO_ENV", None)
        else:
            os.environ["CRIADOR_VIDEO_ENV"] = self.antigo_env
        chaves._registro_windows = self.reg
        chaves._carregado = False
        shutil.rmtree(self.dir)


def test_sem_nenhuma_chave_status_lista_tudo_como_faltando():
    with Isolado():
        s = chaves.status()
        assert all(not i["configurada"] for i in s["chaves"])
        assert s["sempre_gratis"], "tem de dizer o que funciona sem chave"
        custos = {i["chave"]: i["custo"] for i in s["chaves"]}
        assert custos["FAL_KEY"] == "pago" and custos["PIXABAY_API_KEY"] == "gratis"


def test_mensagem_padrao_tem_o_essencial_e_proibe_colar_no_chat():
    m = chaves.mensagem_falta("FAL_KEY", "clipes")
    for trecho in ("fal.ai", "PAGO", "Ela libera", "Custo", "https://fal.ai", "configurar.py", "Nunca cole", "Sem ela"):
        assert trecho in m, trecho


def test_obter_encerra_com_a_mensagem_quando_falta():
    with Isolado():
        try:
            chaves.obter("GEMINI_API_KEY", contexto="voz")
            raise AssertionError("devia encerrar")
        except SystemExit as e:
            assert "GEMINI_API_KEY" in str(e) and "aistudio" in str(e)
        assert chaves.obter("GEMINI_API_KEY", obrigatoria=False) is None


def test_le_do_env_sem_sobrescrever_variavel_existente():
    with Isolado() as iso:
        with open(iso.env, "w", encoding="utf-8") as f:
            f.write('# comentário\nexport FAL_KEY="do-env"\nPIXABAY_API_KEY=pix-env\nVAZIA=\n')
        os.environ["PIXABAY_API_KEY"] = "do-ambiente"
        chaves.carregar(forcar=True)
        assert os.environ["FAL_KEY"] == "do-env"
        assert os.environ["PIXABAY_API_KEY"] == "do-ambiente", "o .env não pode sobrescrever o ambiente"
        assert chaves.origem("FAL_KEY") == "arquivo .env"
        assert chaves.origem("PIXABAY_API_KEY") == "variável de ambiente"


def test_scripts_usam_o_modulo_central():
    with Isolado() as iso:
        with open(iso.env, "w", encoding="utf-8") as f:
            f.write(f"FAL_KEY={SEGREDO}\n")
        import gerar_clipe_fal
        assert gerar_clipe_fal.chave() == SEGREDO
        import tts_gemini
        try:
            tts_gemini.chave()
            raise AssertionError("sem GEMINI devia encerrar")
        except SystemExit as e:
            assert "Falta a chave GEMINI_API_KEY" in str(e)


def test_status_nunca_mostra_o_valor():
    with Isolado() as iso:
        with open(iso.env, "w", encoding="utf-8") as f:
            f.write(f"OPENAI_API_KEY={SEGREDO}\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            chaves.imprimir(chaves.status())
        saida = buf.getvalue()
        assert SEGREDO not in saida and SEGREDO not in json.dumps(chaves.status())
        assert "configurada" in saida


def test_configurar_grava_preserva_e_remove():
    with Isolado() as iso:
        with open(iso.env, "w", encoding="utf-8") as f:
            f.write("# minhas chaves\nFAL_KEY=velha\nOUTRA=1\n")
        configurar.gravar(iso.env, {"FAL_KEY": "nova", "PIXABAY_API_KEY": "pix"})
        txt = open(iso.env, encoding="utf-8").read()
        assert "# minhas chaves" in txt and "OUTRA=1" in txt and "FAL_KEY=nova" in txt and "velha" not in txt
        assert "PIXABAY_API_KEY=pix" in txt
        configurar.gravar(iso.env, {}, remover={"FAL_KEY"})
        assert "FAL_KEY" not in open(iso.env, encoding="utf-8").read()


def test_configurar_recusa_rodar_sem_terminal():
    with Isolado():
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "configurar.py")], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert r.returncode != 0 and "terminal interativo" in (r.stdout + r.stderr)


def test_teste_de_chave_ausente_e_sem_teste_gratis_nao_usa_rede():
    with Isolado():
        assert chaves.testar("GEMINI_API_KEY") == "ausente"
        os.environ["FAL_KEY"] = SEGREDO
        assert chaves.testar("FAL_KEY").startswith("sem teste grátis")


def test_env_example_lista_todas_as_chaves_vazias():
    ex = open(os.path.join(AQUI, "..", ".env.example"), encoding="utf-8").read()
    for nome in chaves.CHAVES:
        assert f"\n{nome}=\n" in ex, nome
    assert ".env" in open(os.path.join(AQUI, "..", ".gitignore"), encoding="utf-8").read().split()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
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
