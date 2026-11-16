"""Testes dos agentes do estúdio e do instalador — sem rede, sem tocar em ~/.claude/agents (usa pasta temporária).
Rodar: python tests/test_agentes.py"""
import glob
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(AQUI, "..")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import instalar_agentes as ia  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


AGENTES = sorted(glob.glob(os.path.join(SKILL, "agentes", "estudio-*.md")))


def _txt(p):
    return open(p, encoding="utf-8").read()


def test_todo_agente_tem_frontmatter_nome_e_descricao():
    assert AGENTES, "pasta agentes/ vazia"
    for p in AGENTES:
        t = _txt(p)
        assert t.startswith("---"), p
        cab = t.split("---")[1]
        assert f"name: {os.path.basename(p)[:-3]}" in cab and "description:" in cab, p


def test_cabecalho_e_yaml_valido():
    """Descrição com 'texto: texto' sem aspas quebra o YAML e o Claude Code não carrega o agente."""
    import json
    import re
    for p in AGENTES:
        t = _txt(p)
        assert "\r" not in t, f"{os.path.basename(p)} com quebra de linha do Windows"
        m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
        assert m, p
        campos = {}
        for linha in m.group(1).split("\n"):
            k, v = linha.split(":", 1)
            campos[k.strip()] = v.strip()
        d = campos["description"]
        assert d.startswith('"') and d.endswith('"'), f"{os.path.basename(p)}: descrição precisa de aspas"
        assert len(json.loads(d)) > 60
        assert campos.get("tools") and campos.get("model"), p
        try:
            import yaml
        except ImportError:
            continue
        assert yaml.safe_load(m.group(1))["name"] == os.path.basename(p)[:-3]


def test_scripts_citados_existem():
    import re
    for p in AGENTES:
        for nome in set(re.findall(r"scripts/([a-z_]+\.py)", _txt(p))):
            assert os.path.exists(os.path.join(SKILL, "scripts", nome)), f"{os.path.basename(p)} cita {nome}"


def test_todo_agente_tem_a_regra_das_chaves():
    for p in AGENTES:
        t = _txt(p)
        assert "**Chaves de API**" in t, p
        assert "chaves.py status" in t and "precisa" in t and "configurar.py" in t, p


def test_nenhum_agente_tem_caminho_fixo_ou_dado_pessoal():
    proibidos = ("Python314", "C:/Users/", "C:\\Users\\", "D:\\")  # caminhos fixos de uma máquina
    for p in AGENTES:
        t = _txt(p)
        for x in proibidos:
            assert x not in t, f"{os.path.basename(p)} contém {x}"
        import re
        assert not re.search(r"\(\d{2}\) ?9?\d{4}-\d{4}", t), f"{os.path.basename(p)} tem telefone"


def test_instalador_verifica_instala_atualiza_e_remove():
    d = tempfile.mkdtemp(prefix="agentes-")
    try:
        v = ia.verificar(d)
        assert v["ok"] == 0 and all(i["estado"] == "faltando" for i in v["itens"])
        assert len(ia.instalar(d)["feitos"]) == len(AGENTES)
        assert ia.verificar(d)["ok"] == len(AGENTES)
        assert ia.instalar(d)["feitos"] == [], "segunda instalação não deve mexer em nada"
        alvo = os.path.join(d, os.path.basename(AGENTES[0]))
        with open(alvo, "a", encoding="utf-8") as f:
            f.write("\nmexido\n")
        assert ia.verificar(d)["pendentes"][0]["estado"] == "desatualizado"
        r = ia.instalar(d)
        assert r["feitos"][0]["acao"].startswith("atualizado") and os.path.exists(alvo + ".bak")
        outro = os.path.join(d, "meu-agente.md")
        with open(outro, "w") as f:
            f.write("x")
        rm = ia.remover(d)
        assert len(rm["removidos"]) == len(AGENTES) and os.path.exists(outro), "só remove os agentes desta skill"
    finally:
        shutil.rmtree(d)


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
