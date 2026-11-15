"""Ambientação sonora: uma cama de som de fundo por cenário (chuva, rua, interior, noite, vento, temporal), sintetizada
no PC (grátis), que troca junto com os cortes (crossfade curto) e fica baixa embaixo da voz e da trilha.

Uso:
  python ambiente.py --historia remotion/src/historia.json -o assets/ambiente.wav
        → lê os planos (inicio/fim) e o ambiente de cada um: plano.ambiente > cenário da tomada na bíblia
          (plano.tomada ou --mapa p01=t001,p02=t002) > --padrao
  python ambiente.py --blocos "0:chuva,12.5:interior,30:rua" --duracao 45 -o assets/ambiente.wav
  python ambiente.py --ouvir chuva -o teste.wav      → 8 s de um ambiente para conferir
Tipos: chuva, temporal, rua, interior, cantina (= interior com murmúrio), noite, vento, nenhum.
Saída: WAV 48 kHz estéreo a ~−34 LUFS (fundo); no template de história entra com `--ambiente` no montar_historia.py.
"""
import argparse
import json
import os
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

TAXA = 48000
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
TIPOS = ["chuva", "temporal", "rua", "interior", "cantina", "noite", "vento", "nenhum"]
SINONIMOS = {"rain": "chuva", "street": "rua", "indoor": "interior"}


def ruido(n, rng, cor="rosa"):
    b = rng.standard_normal(n)
    if cor == "branco":
        return b
    f = np.fft.rfft(b)
    k = np.arange(len(f)) + 1
    f /= np.sqrt(k) if cor == "rosa" else k  # rosa 1/f · marrom 1/f²
    x = np.fft.irfft(f, n)
    return x / (np.abs(x).max() + 1e-9)


def banda(x, lo, hi):
    if lo and hi:
        sos = butter(2, [lo, hi], btype="band", fs=TAXA, output="sos")
    elif hi:
        sos = butter(2, hi, btype="low", fs=TAXA, output="sos")
    else:
        sos = butter(2, lo, btype="high", fs=TAXA, output="sos")
    return sosfilt(sos, x)


def lento(n, rng, hz=0.15, prof=0.35):
    """Modulação lenta (rajadas/respiração do ambiente)."""
    t = np.arange(n) / TAXA
    return 1 - prof + prof * (0.5 + 0.5 * np.sin(2 * np.pi * hz * t + rng.uniform(0, 6)))


def gotas(n, rng, por_s=18, lo=1800, hi=7000):
    x = np.zeros(n)
    for p in rng.integers(0, max(1, n - 2000), int(por_s * n / TAXA)):
        d = int(rng.integers(300, 1500))
        x[p:p + d] += rng.uniform(0.2, 1) * np.exp(-np.arange(d) / (d / 5)) * rng.standard_normal(d)
    return banda(x, lo, hi)


def gerar(tipo, seg, seed=0):
    tipo = SINONIMOS.get(tipo, tipo)
    n = int(seg * TAXA)
    canais = []
    for c in range(2):  # dois canais levemente diferentes = espaço estéreo
        r = np.random.default_rng(seed * 7 + c)
        if tipo in ("chuva", "temporal"):
            x = banda(ruido(n, r), 400, 9000) * lento(n, r, 0.08, 0.3) + 0.5 * gotas(n, r, 40 if tipo == "temporal" else 18)
            if tipo == "temporal":
                x = x * 1.6 + 0.8 * banda(ruido(n, r, "marrom"), 30, 250) * lento(n, r, 0.05, 0.8)
        elif tipo == "rua":
            x = 0.8 * banda(ruido(n, r, "marrom"), 30, 300)
            for p in r.integers(0, max(1, n - 5 * TAXA), max(1, int(seg / 6))):  # carros passando ao longe
                d = int(r.uniform(2.5, 4.5) * TAXA)
                env = np.sin(np.linspace(0, np.pi, d)) ** 2
                trecho = x[p:p + d]
                trecho += 0.6 * (env * banda(r.standard_normal(d), 150, 1200))[: len(trecho)]
        elif tipo in ("interior", "cantina"):
            x = 0.5 * banda(ruido(n, r), 60, 1800)
            if tipo == "cantina":
                t = np.arange(n) / TAXA
                silabas = 0.5 + 0.5 * np.sin(2 * np.pi * (3.5 + np.sin(2 * np.pi * 0.2 * t)) * t)
                x += 0.9 * banda(r.standard_normal(n), 300, 1400) * silabas * lento(n, r, 0.3, 0.5)
                x += 0.25 * gotas(n, r, 2, 2500, 6000)  # talheres/louça
        elif tipo == "noite":
            t = np.arange(n) / TAXA
            x = 0.4 * banda(ruido(n, r), 80, 1200) * lento(n, r, 0.1, 0.5)
            grilo = np.sin(2 * np.pi * 4600 * t) * (np.sin(2 * np.pi * 28 * t) > 0.6) * (np.sin(2 * np.pi * 0.7 * t + c) > 0.2)
            x += 0.08 * grilo
        elif tipo == "vento":
            x = banda(ruido(n, r), 150, 1400) * lento(n, r, 0.12, 0.7)
        else:
            x = np.zeros(n)
        canais.append(x)
    s = np.stack(canais, 1)
    rms = np.sqrt(np.mean(s ** 2)) + 1e-9
    return s * (10 ** (-36 / 20) / rms) if rms > 1e-8 else s  # ~ −36 dBFS RMS ≈ −34 LUFS: fundo


def montar(blocos, duracao, xfade=0.25):
    n = int(duracao * TAXA)
    out = np.zeros((n, 2))
    for i, (ini, tipo) in enumerate(blocos):
        fim = blocos[i + 1][0] if i + 1 < len(blocos) else duracao
        a, b = max(0, int((ini - xfade) * TAXA)), min(n, int((fim + xfade) * TAXA))
        if tipo == "nenhum" or b <= a:
            continue
        x = gerar(tipo, (b - a) / TAXA, seed=i + 1)[: b - a]
        f = min(int(2 * xfade * TAXA), len(x) // 2)
        env = np.ones(len(x))
        if i > 0:
            env[:f] = np.linspace(0, 1, f)
        if i + 1 < len(blocos):
            env[-f:] = np.linspace(1, 0, f)
        out[a:a + len(x)] += x * env[:, None]
    fade = min(int(0.6 * TAXA), n // 4)  # entra e sai suave no começo/fim do vídeo
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out


def escrever(s, arq):
    os.makedirs(os.path.dirname(os.path.abspath(arq)) or ".", exist_ok=True)
    pcm = (np.clip(s, -1, 1) * 32767).astype(np.int16)
    with wave.open(arq, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm.tobytes())


def blocos_da_historia(arq, mapa, padrao):
    h = json.load(open(arq, encoding="utf-8"))
    bib = {}
    try:
        from producao import carregar
        _, d = carregar(os.path.dirname(os.path.abspath(arq)))
        bib = {t["id"]: d["cenarios"].get(t.get("cenario", ""), {}).get("ambiente") for t in d["tomadas"]}
    except SystemExit:
        pass
    blocos = []
    for p in h["planos"]:
        tid = p.get("tomada") or mapa.get(p["id"]) or p["id"]
        tipo = p.get("ambiente") or bib.get(tid) or padrao
        if not blocos or blocos[-1][1] != tipo:
            blocos.append((float(p["inicio"]), tipo))
    return blocos, float(h["duracao"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--historia")
    ap.add_argument("--mapa", default="", help="plano=tomada,… (quando os ids diferem)")
    ap.add_argument("--padrao", default="nenhum")
    ap.add_argument("--blocos")
    ap.add_argument("--duracao", type=float)
    ap.add_argument("--ouvir", choices=TIPOS)
    a = ap.parse_args()
    if a.ouvir:
        escrever(montar([(0, a.ouvir)], 8), a.saida)
    elif a.historia:
        mapa = dict(x.split("=") for x in a.mapa.split(",") if "=" in x)
        blocos, dur = blocos_da_historia(a.historia, mapa, a.padrao)
        escrever(montar(blocos, dur), a.saida)
        print("  " + " → ".join(f"{t} ({s:.1f}s)" for s, t in blocos))
    elif a.blocos and a.duracao:
        blocos = [(float(x.split(":")[0]), x.split(":")[1]) for x in a.blocos.split(",")]
        escrever(montar(blocos, a.duracao), a.saida)
    else:
        ap.error("use --historia, --blocos + --duracao, ou --ouvir")
    print(a.saida)


if __name__ == "__main__":
    main()
