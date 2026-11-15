"""Testes dos especialistas (especialistas.py): trilha, atuação, figurino e atenção — sem rede, sem gasto.
O Gemini é simulado; loudness, buracos de som, corte seco e vales de atenção são medidos de verdade em mídia sintética.
Rodar: python tests/test_especialistas.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import especialistas as es  # noqa: E402


def projeto(planos, extra=None):
    base = tempfile.mkdtemp(prefix="esp-")
    arq = os.path.join(base, "roteiro.json")
    json.dump(dict({"planos": planos}, **(extra or {})), io.open(arq, "w", encoding="utf-8"))
    return base, json.load(io.open(arq, encoding="utf-8"))


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def filme_som(pasta, nome, filtro_audio, dur=8):
    v = os.path.join(pasta, nome)
    ff("-f", "lavfi", "-i", f"testsrc=duration={dur}:size=320x180:rate=10", "-f", "lavfi", "-i", filtro_audio,
       "-shortest", "-c:v", "libx264", "-c:a", "aac", v)
    return v


def item(base, nome):
    return json.load(io.open(os.path.join(base, "entrega", f"inspecao-{nome}.json"), encoding="utf-8"))["itens"]


OUVIU_OK = lambda *a, **k: {"clima_por_bloco": {}, "problemas": [], "nota": 9}  # noqa: E731


# ---------------- trilha
def test_trilha_loudness_buraco_e_corte_seco():
    base, d = projeto([{"id": "a", "dur_alvo": 8}])
    # som alto e constante até o fim (corte seco), com um buraco de 1,5 s no meio
    v = filme_som(base, "f.mp4", "aevalsrc='if(between(t,3,4.5),0,0.9*sin(2*PI*220*t))':s=48000:d=8")
    rep, nv = es.conferir_trilha(base, d, v, ouvir=OUVIU_OK)
    txt = " ".join(t for _, t in item(base, "trilha")[0]["problemas"])
    assert rep == 1 and "buraco de som" in txt and "corte seco" in txt and "loudness" in txt, txt
    shutil.rmtree(base)


def test_trilha_voz_enterrada_na_musica():
    base, d = projeto([{"id": "a", "dur_alvo": 6}], {"mix": {"voz": 1.0, "trilha": 1.0}})
    voz, tri = os.path.join(base, "voz.wav"), os.path.join(base, "tri.wav")
    ff("-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-af", "volume=0.3", voz)
    ff("-f", "lavfi", "-i", "sine=frequency=90:duration=6", "-af", "volume=0.25", tri)
    v = filme_som(base, "f.mp4", "sine=frequency=300:duration=6", 6)
    es.conferir_trilha(base, d, v, voz=voz, trilha=tri, ouvir=OUVIU_OK)
    it = item(base, "trilha")[0]
    assert it["voz_sobre_trilha_db"]["mediana"] < 9 and any("voz menos de 9 dB" in t for _, t in it["problemas"]), it
    shutil.rmtree(base)


def test_trilha_sem_gemini_nao_aprova():
    base, d = projeto([{"id": "a", "dur_alvo": 6}])
    v = filme_som(base, "f.mp4", "sine=frequency=300:duration=6", 6)
    es.conferir_trilha(base, d, v, ouvir=lambda *a, **k: None)
    assert item(base, "trilha")[0]["estado"] != "aprovado"
    shutil.rmtree(base)


# ---------------- atuação
P_ATU = {"id": "c01e", "fala": "", "direcao": {"modo": "acao", "quem": ["marcos"], "acao": "susto leve", "atuacao": "contido",
                                              "beats": [{"ate": 2, "fase": "antecipacao"}, {"ate": 5, "fase": "acao"}]}}


def avaliacao(**mud):
    v = {"beats": [{"beat": 1, "fase": "antecipacao", "emocao_ok": True, "intensidade_pedida": 2, "intensidade_vista": 2},
                   {"beat": 2, "fase": "acao", "emocao_ok": True, "intensidade_pedida": 2, "intensidade_vista": 2, "tempo_ok": True}],
         "rosto_muda": True, "micro_movimentos": True, "crivel": True, "nota": 8.5, "correcao_en": ""}
    v.update(mud)
    return v


def clipe(base):
    os.makedirs(os.path.join(base, "assets", "clips"), exist_ok=True)
    c = os.path.join(base, "assets", "clips", "c01e.mp4")
    ff("-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", c)
    return c


def test_atuacao_contida_como_pedida_aprova():
    base, _ = projeto([P_ATU])
    r = es.conferir_atuacao_clipe(P_ATU, clipe(base), assistir=lambda *a, **k: avaliacao())
    assert r["estado"] == "aprovado", r
    shutil.rmtree(base)


def test_atuacao_exagerada_reprova_com_correcao():
    base, _ = projeto([P_ATU])
    v = avaliacao(correcao_en="smaller flinch, keep it subtle")
    v["beats"][1].update(intensidade_vista=5, exagerado=True, comentario="careta enorme")
    r = es.conferir_atuacao_clipe(P_ATU, clipe(base), assistir=lambda *a, **k: v)
    assert r["estado"] == "reprovado" and any("exagerado" in t for _, t in r["problemas"]) and r["correcao_en"]
    shutil.rmtree(base)


def test_atuacao_emocao_errada_e_rosto_congelado():
    base, _ = projeto([P_ATU])
    v = avaliacao(rosto_muda=False)
    v["beats"][0].update(emocao_ok=False, emocao_vista="feliz", emocao_pedida="cansado")
    r = es.conferir_atuacao_clipe(P_ATU, clipe(base), assistir=lambda *a, **k: v)
    txt = " ".join(t for _, t in r["problemas"])
    assert r["estado"] == "reprovado" and "feliz" in txt and "congelado" in txt
    shutil.rmtree(base)


def test_atuacao_sem_gemini_nao_verificado():
    base, _ = projeto([P_ATU])
    r = es.conferir_atuacao_clipe(P_ATU, clipe(base), assistir=lambda *a, **k: None)
    assert r["estado"] == "nao_verificado"
    shutil.rmtree(base)


# ---------------- figurino
ELENCO = {"elenco": {"marcos": {"tracos": ["barba curta"], "figurino": ["camisa lavanda", "smartwatch preto"]}}}


def test_figurino_traco_diferente_e_grave_fora_de_quadro_nao_e_erro():
    base, d = projeto([P_ATU], ELENCO)
    v = {"itens": [{"personagem": "marcos", "item": "barba curta", "estado": "ausente", "visto": "sem barba"},
                   {"personagem": "marcos", "item": "camisa lavanda", "estado": "ok"},
                   {"personagem": "marcos", "item": "smartwatch preto", "estado": "fora_de_quadro"}],
         "extras": [{"personagem": "marcos", "o_que": "óculos"}], "rosto_igual": {"marcos": True}}
    r = es.conferir_figurino_quadros(d, base, "c01e", ["marcos"], [], ver=lambda *a, **k: v)
    gr = [g for g, _ in r["problemas"]]
    assert r["estado"] == "reprovado" and "grave" in gr and len(r["problemas"]) == 1, r  # barba (traço) = grave; relógio fora de quadro ok
    assert any("óculos" in a for a in r["avisos"])  # peça fora da ficha = aviso (a ficha não é exaustiva)
    shutil.rmtree(base)


def test_figurino_sem_ficha_ou_sem_gemini_nao_verificado():
    base, d = projeto([P_ATU])
    assert es.conferir_figurino_quadros(d, base, "c01e", ["marcos"], [], ver=lambda *a, **k: {})["estado"] == "nao_verificado"
    base2, d2 = projeto([P_ATU], ELENCO)
    assert es.conferir_figurino_quadros(d2, base2, "c01e", ["marcos"], [], ver=lambda *a, **k: None)["estado"] == "nao_verificado"
    shutil.rmtree(base)
    shutil.rmtree(base2)


# ---------------- atenção
def test_atencao_roteiro_fala_rapida_sem_cta_e_nota_baixa():
    planos = [{"id": "a", "dur_alvo": 3, "fala": "um dois três quatro cinco seis sete oito nove dez onze doze"},
              {"id": "b", "dur_alvo": 3, "fala": "obrigado por assistir"}]
    base, d = projeto(planos)
    rep, _ = es.conferir_atencao(base, d, especialista=lambda *a, **k: {"nota": 55, "problemas": [], "tres_mudancas": ["x"]})
    txt = " ".join(t for _, t in item(base, "atencao")[0]["problemas"])
    assert rep == 1 and "palavras/s" in txt and "CTA" in txt and "55" in txt, txt
    shutil.rmtree(base)


def test_atencao_filme_parado_tem_vale():
    base, d = projeto([{"id": "a", "dur_alvo": 8, "fala": "Peça uma demonstração"}])
    v = os.path.join(base, "parado.mp4")
    ff("-f", "lavfi", "-i", "color=c=navy:s=320x180:d=8:r=10", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest",
       "-c:v", "libx264", "-c:a", "aac", v)
    es.conferir_atencao(base, d, filme=v, especialista=lambda *a, **k: {"nota": 80, "problemas": []})
    it = item(base, "atencao")[0]
    assert it["metricas_filme"]["vales"] and any("vale de atenção" in t for _, t in it["problemas"]), it["metricas_filme"]
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
            print("❌", t.__name__, repr(e)[:300])
    print(f"\n{ok}/{len(testes)} passaram")
    sys.exit(0 if ok == len(testes) else 1)
