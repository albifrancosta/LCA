"""buscar_arquivo.py: licenças aceitas/recusadas, domínios de download e nomes de arquivo seguros.
Sem rede, sem gasto. Rodar: python tests/test_buscar_arquivo.py"""
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import buscar_arquivo as ba  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def test_licencas_livres_do_commons_passam():
    for lic in ("Public domain", "PD-US", "CC0", "CC BY 2.0", "CC BY-SA 4.0", "CC BY-SA 3.0 de", "cc-by-sa", "CC BY"):
        assert ba.licenca_commons_ok(lic), lic


def test_licencas_restritas_do_commons_sao_recusadas():
    for lic in ("CC BY-NC 2.0", "CC BY-ND 4.0", "CC BY-NC-SA 3.0", "Fair use", "Non-free", "All rights reserved",
                "GFDL", "", None, "Copyrighted"):
        assert not ba.licenca_commons_ok(lic), lic


def test_item_do_archive_livre_so_por_colecao_confiavel():
    assert ba.item_archive_livre({"collection": ["fedflix", "movies"]})
    assert ba.item_archive_livre({"collection": "prelinger"})
    assert not ba.item_archive_livre({"collection": ["opensource_movies"], "licenseurl": ""})
    assert not ba.item_archive_livre({"licenseurl": "http://creativecommons.org/licenses/by-nc/3.0/"})
    # nome parecido não basta: precisa ser a coleção exata
    assert not ba.item_archive_livre({"collection": ["nasa_fanclub"]})


def test_marca_de_dominio_publico_do_autor_do_envio_nao_libera():
    # caso real de 2026-11-17: série da BBC enviada por usuário com a marca de domínio público
    bbc = {"collection": ["opensource_movies"], "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/"}
    assert not ba.item_archive_livre(bbc)
    assert ba.situacao_archive(bbc) == "MARCADO"
    assert ba.situacao_archive({"collection": ["fedflix"]}) == "LIVRE"
    assert ba.situacao_archive({"collection": ["opensource_movies"]}) == "CONFERIR"


def test_download_so_https_dos_dominios_do_commons_e_archive():
    assert ba.url_segura("https://upload.wikimedia.org/wikipedia/commons/a/ab/x.jpg")
    assert ba.url_segura("https://archive.org/download/id/x.mp4")
    assert ba.url_segura("https://ia800300.us.archive.org/1/items/id/x.mp4")
    assert not ba.url_segura("http://archive.org/download/id/x.mp4")
    assert not ba.url_segura("https://archive.org.evil.com/x.mp4")
    assert not ba.url_segura("https://evilarchive.org/x.mp4")
    assert not ba.url_segura("file:///C:/Windows/win.ini")


def test_abrir_recusa_url_fora_da_lista_sem_tocar_na_rede():
    try:
        ba._abrir("https://exemplo.com/x.jpg")
    except ValueError as e:
        assert "recusado" in str(e)
    else:
        raise AssertionError("deveria recusar")


def test_nome_seguro_nao_sai_da_pasta():
    assert ba.nome_seguro("File:Teatro Amazonas (Manaus).jpg") == "Teatro_Amazonas_Manaus_.jpg"
    n = ba.nome_seguro("File:../../Windows/system32/x.dll")
    assert "/" not in n and "\\" not in n and not n.startswith(".")
    assert ba.nome_seguro("File:...") == "arquivo"
    assert len(ba.nome_seguro("File:" + "a" * 500 + ".jpg")) <= 120


def test_credito_tem_autor_licenca_e_pagina():
    c = ba.credito_commons("", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:X.jpg")
    assert c.startswith("Autor desconhecido / Wikimedia Commons / CC BY-SA 4.0")
    assert "https://commons.wikimedia.org/wiki/File:X.jpg" in c


def test_recortar_herda_o_credito_do_filme():
    if not shutil.which(ba.FF) and not os.path.exists(ba.FF):
        print("  (sem ffmpeg; pulado)")
        return
    d = tempfile.mkdtemp(prefix="arq-")
    try:
        filme = os.path.join(d, "filme.mp4")
        subprocess.run([ba.FF, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "3",
                        "-pix_fmt", "yuv420p", filme], check=True)
        with open(filme + ".credito.txt", "w", encoding="utf-8") as f:
            f.write("Filme de teste / Internet Archive / publicdomain\nhttps://archive.org/details/teste\n")
        saida = os.path.join(d, "clipes", "c1.mp4")
        ba.filmes_recortar(filme, 0.5, 2.0, saida, None)
        assert os.path.getsize(saida) > 0
        with open(saida + ".credito.txt", encoding="utf-8") as f:
            txt = f.read()
        assert "Filme de teste / Internet Archive" in txt and "trecho 0.5–2.0 s de filme.mp4" in txt
    finally:
        shutil.rmtree(d)


def test_recortar_recusa_trecho_invertido():
    try:
        ba.main(["filmes", "recortar", "x.mp4", "5", "2", "y.mp4"])
    except SystemExit as e:
        assert "depois do início" in str(e.code)
    else:
        raise AssertionError("deveria recusar")


if __name__ == "__main__":
    falhas = 0
    for nome, fn in [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]:
        try:
            fn()
            print("✅", nome)
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print("❌", nome, "→", repr(e))
    sys.exit(1 if falhas else 0)
