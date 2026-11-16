"""Inspetor do filme (2026-11-07): decisão do diretor amarrada ao sha256 e com evidência.
Sem rede, sem crédito. Rodar: python tests/test_filme_inclui.py"""
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import runware_falso as F  # noqa: E402
import inspetor  # noqa: E402
import integridade as ig  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")



def projeto():
    d = tempfile.mkdtemp(prefix="fi-")
    os.makedirs(os.path.join(d, "entrega"))
    os.makedirs(os.path.join(d, "remotion", "public", "f"))
    clip = os.path.join(d, "remotion", "public", "f", "x.mp4")
    open(clip, "wb").write(F.mp4_real())
    return d, clip


def gravar(d, dec):
    json.dump(dec, open(os.path.join(d, "entrega", "decisoes-diretor.json"), "w"))


def test_decisao_vale_so_com_mesmo_sha_e_evidencia():
    d, clip = projeto()
    md = {"arquivo": "remotion/public/f/x.mp4"}
    dec = {"decisoes": [{"take": "x", "sha256": ig.sha256(clip), "evidencia": "folha: sorri", "decisao": "aprovado em off"}]}
    gravar(d, dec)
    assert inspetor.decisao_valida(inspetor.decisoes_diretor(d), "x", d, md)
    dec["decisoes"][0]["sha256"] = "0" * 64  # arquivo trocado depois da decisão → não vale
    gravar(d, dec)
    assert not inspetor.decisao_valida(inspetor.decisoes_diretor(d), "x", d, md)
    dec["decisoes"][0].update(sha256=ig.sha256(clip), evidencia="")  # sem evidência → não vale
    gravar(d, dec)
    assert not inspetor.decisao_valida(inspetor.decisoes_diretor(d), "x", d, md)


def test_sem_arquivo_de_decisoes_nada_muda():
    d, _ = projeto()
    assert inspetor.decisoes_diretor(d) == {}


if __name__ == "__main__":
    F.rodar(globals())
