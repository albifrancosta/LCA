"""Testes das conferências (conferencia.py): texto na tela, lip-sync medido e filme × storyboard — sem rede, sem gasto.
O lip-sync é provado com um vídeo SINTÉTICO de atraso conhecido (boca desenhada seguindo a voz deslocada no tempo).
Rodar: python tests/test_conferencia.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "scripts"))
import conferencia as cf  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # ✅/❌ em qualquer console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Pulado(Exception):
    """Teste pulado: depende de um pacote opcional que não está instalado."""


PACOTE = {"skimage": "scikit-image", "gradio_client": "gradio-client"}


def requer(modulo):
    import importlib.util
    try:
        achou = importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        achou = False
    if not achou:
        raise Pulado(f"precisa de {modulo} (opcional: pip install {PACOTE.get(modulo, modulo)})")


FPS, DUR, SR = 25, 3.2, 16000
BOCA = (120, 140, 80, 50)  # x, y, w, h


def silabas(t):
    """Envelope de fala: sílabas a ~4 Hz entre 0,4 e 2,8 s, com intensidades diferentes."""
    rng = np.random.default_rng(7)
    base = np.arange(0.45, 2.8, 0.23)
    picos = base + rng.uniform(-0.04, 0.04, len(base))
    amp = rng.uniform(0.4, 1.0, len(picos))
    e = np.zeros_like(t, dtype=float)
    for p, a in zip(picos, amp):
        e += a * np.exp(-((t - p) / 0.05) ** 2)
    return np.clip(e, 0, 1)


def clipe_falando(pasta, atraso_s=0.0, parada=False):
    import cv2
    from scipy.io import wavfile
    n = int(DUR * FPS)
    vid = os.path.join(pasta, f"fala-{atraso_s}-{parada}.mp4")
    w = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (320, 240))
    for i in range(n):
        f = np.full((240, 320, 3), 200, np.uint8)
        cv2.circle(f, (160, 120), 90, (150, 180, 220), -1)
        abre = 0.0 if parada else float(silabas(np.array([i / FPS - atraso_s]))[0])
        cv2.ellipse(f, (160, 165), (28, int(2 + 20 * abre)), 0, 0, 360, (40, 20, 60), -1)
        w.write(f)
    w.release()
    t = np.arange(int(DUR * SR)) / SR
    wav = os.path.join(pasta, "voz.wav")
    wavfile.write(wav, SR, (0.6 * silabas(t) * np.sin(2 * np.pi * 180 * t)).astype(np.float32))
    return vid, wav


def caixa_fixa(quadros):
    return [BOCA] * len(quadros)


def test_lipsync_em_tempo_aprova():
    requer("librosa")
    p = tempfile.mkdtemp()
    vid, wav = clipe_falando(p, 0.0)
    r = cf.conferir_lipsync_clipe(vid, wav, caixa_fixa)
    assert r["estado"] == "aprovado", r
    assert abs(r["atraso_ms"]) <= 40 and r["fala_com_boca"] >= 0.5
    shutil.rmtree(p)


def test_lipsync_atrasado_200ms_reprova_e_mede_o_atraso():
    requer("librosa")
    p = tempfile.mkdtemp()
    vid, wav = clipe_falando(p, 0.2)
    r = cf.conferir_lipsync_clipe(vid, wav, caixa_fixa)
    assert r["estado"] == "reprovado", r
    assert 160 <= r["atraso_ms"] <= 240, r["atraso_ms"]
    assert any("fora de tempo" in t for _, t in r["problemas"])
    shutil.rmtree(p)


def test_lipsync_adiantado_tambem_reprova():
    requer("librosa")
    p = tempfile.mkdtemp()
    vid, wav = clipe_falando(p, -0.16)
    r = cf.conferir_lipsync_clipe(vid, wav, caixa_fixa)
    assert r["estado"] == "reprovado" and -200 <= r["atraso_ms"] <= -120, r
    shutil.rmtree(p)


def test_boca_parada_reprova():
    requer("librosa")
    p = tempfile.mkdtemp()
    vid, wav = clipe_falando(p, 0.0, parada=True)
    r = cf.conferir_lipsync_clipe(vid, wav, caixa_fixa)
    assert r["estado"] == "reprovado" and any("parada" in t for _, t in r["problemas"]), r
    shutil.rmtree(p)


def test_rosto_nao_encontrado_fica_nao_verificado():
    requer("librosa")
    p = tempfile.mkdtemp()
    vid, wav = clipe_falando(p, 0.0)
    r = cf.conferir_lipsync_clipe(vid, wav, lambda q: [None] * len(q))
    assert r["estado"] == "nao_verificado", r
    shutil.rmtree(p)


def test_contem_tolera_erro_de_ocr():
    assert cf.contem("Meu orcamento flcou pronto? SEM WALl", "Meu orçamento ficou pronto?")
    assert cf.contem("x SEM MARCA y", "SEM MARCA")
    assert not cf.contem("SEM MARCA", "Abrir chamado")


def video_cor(pasta, dur=6.0):
    v = os.path.join(pasta, "filme.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={dur}:size=320x180:rate=10", v], check=True)
    return v


def projeto(planos, extra=None):
    base = tempfile.mkdtemp(prefix="conf-")
    arq = os.path.join(base, "roteiro.json")
    json.dump(dict({"planos": planos}, **(extra or {})), io.open(arq, "w", encoding="utf-8"))
    return base, json.load(io.open(arq, encoding="utf-8"))


def test_texto_esperado_ausente_e_termo_proibido():
    base, d = projeto([{"id": "a", "dur_alvo": 3.0, "texto_tela": ["Menos trabalho manual"]},
                       {"id": "b", "dur_alvo": 3.0, "beneficio": "Equipe organizada"}], {"termos_proibidos": ["CRM"]})
    v = video_cor(base)
    lidos = {"a": "MinhaMarca · Menos trabalho manual", "b": "Módulo CRM integrado"}
    ler = lambda img: lidos[os.path.basename(img).split("-")[0]]  # noqa: E731
    rep, nv = cf.conferir_texto(base, d, v, pelo_roteiro=True, ler=ler, gemini=lambda *a: {"textos": [], "problemas": []})
    it = {i["id"]: i for i in json.load(io.open(os.path.join(base, "entrega", "inspecao-texto.json"), encoding="utf-8"))["itens"]}
    assert it["a"]["estado"] == "aprovado"
    assert it["b"]["estado"] == "reprovado"
    txt = " ".join(t for _, t in it["b"]["problemas"])
    assert "Equipe organizada" in txt and "CRM" in txt and rep == 1
    shutil.rmtree(base)


def test_texto_sem_gemini_nao_aprova_por_omissao():
    base, d = projeto([{"id": "a", "dur_alvo": 3.0, "texto_tela": ["Peça uma demonstração"]}])
    v = video_cor(base, 3.0)
    rep, nv = cf.conferir_texto(base, d, v, pelo_roteiro=True, ler=lambda i: "Peça uma demonstração", gemini=lambda *a: None)
    assert rep == 0 and nv == 1
    shutil.rmtree(base)


def test_texto_erro_de_ortografia_do_gemini_reprova():
    base, d = projeto([{"id": "a", "dur_alvo": 3.0}])
    v = video_cor(base, 3.0)
    g = lambda *a: {"textos": ["Orçamneto"], "problemas": [{"texto": "Orçamneto", "tipo": "ortografia", "detalhe": "Orçamento"}]}  # noqa: E731
    rep, _ = cf.conferir_texto(base, d, v, pelo_roteiro=True, ler=lambda i: "Orçamneto", gemini=g)
    assert rep == 1
    shutil.rmtree(base)


def test_storyboard_plano_faltando_ordem_duracao_e_quem_aparece():
    ps = [{"id": "a", "dur_alvo": 2.0, "direcao": {"quem": ["marcos"], "enquadramento": "PM"}},
          {"id": "b", "dur_alvo": 2.0, "direcao": {"quem": [], "enquadramento": "detalhe", "rota_fixa": "motion"}},
          {"id": "c", "dur_alvo": 2.0, "direcao": {"quem": ["marcos"], "enquadramento": "PP"}}]
    base, d = projeto(ps, {"blocos": {"tudo": [0, 6]}})
    v = video_cor(base)
    os.makedirs(os.path.join(base, "remotion", "src"))
    json.dump({"planos": [{"id": "b", "inicio": 0, "fim": 2}, {"id": "a", "inicio": 2, "fim": 5.5}]},  # c sumiu, ordem trocada, a longo
              io.open(os.path.join(base, "remotion", "src", "historia.json"), "w", encoding="utf-8"))
    g = lambda *a: {"pessoas": 2, "quem": ["homem", "mulher"], "enquadramento": "PM"}  # noqa: E731
    rep, nv = cf.conferir_storyboard(base, d, v, gemini=g, sim=lambda a, b: (0.9, 0.9))
    j = json.load(io.open(os.path.join(base, "entrega", "inspecao-storyboard.json"), encoding="utf-8"))
    it = {i["id"]: i for i in j["itens"]}
    assert it["c"]["estado"] == "reprovado"                                # plano aprovado não entrou
    assert any("ordem" in x for x in j["gerais"])                          # ordem trocada
    assert any("duração" in a for a in it["a"]["avisos"])                  # 3,5 s × 2 s
    assert any("personagens" in t for _, t in it["a"]["problemas"])        # 2 pessoas × 1 no contrato
    assert it["b"]["estado"] == "aprovado"                                 # tela em código: sem checagem de quem aparece
    assert rep >= 3
    shutil.rmtree(base)


def test_storyboard_quadro_diferente_do_take_aprovado():
    requer("skimage")
    base, d = projeto([{"id": "a", "dur_alvo": 3.0, "direcao": {"quem": ["marcos"], "enquadramento": "PM"}}])
    v = video_cor(base, 3.0)
    os.makedirs(os.path.join(base, "assets", "img"))
    shutil.copy(cf.quadro(v, 1.0, os.path.join(base, "q.png")), os.path.join(base, "assets", "img", "a.png"))
    g = lambda *a: {"pessoas": 1, "enquadramento": "PM"}  # noqa: E731
    rep, _ = cf.conferir_storyboard(base, d, v, pelo_roteiro=True, gemini=g, sim=lambda a, b: (0.1, 0.05))
    assert rep == 1
    rep, _ = cf.conferir_storyboard(base, d, v, pelo_roteiro=True, gemini=g)  # similaridade real: mesmo vídeo → parecido
    assert rep == 0
    shutil.rmtree(base)


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = pulados = 0
    for t in testes:
        try:
            t()
            ok += 1
            print("✅", t.__name__)
        except Pulado as e:
            pulados += 1
            print("⏭️ ", t.__name__, "— pulado:", e)
        except Exception as e:  # noqa: BLE001
            print("❌", t.__name__, repr(e))
    extra = f" · {pulados} pulados (pacote opcional ausente)" if pulados else ""
    print(f"\n{ok}/{len(testes) - pulados} passaram{extra}")
    sys.exit(0 if ok + pulados == len(testes) else 1)
