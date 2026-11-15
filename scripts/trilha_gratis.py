"""Trilha GRÁTIS com clima por bloco, sintetizada no computador (sem IA, sem direitos autorais).

Mesmo plano de blocos da trilha por IA (`trilha_ia.py`), só que tocado aqui por um sintetizador simples.
Andamento ÚNICO no vídeo inteiro → a batida (`batida.py`) e os cortes no compasso funcionam em todos os blocos.

Uso:
  python trilha_gratis.py --plano plano.json --duracao 32.6 [--bpm 100] -o assets/trilha.wav
  python trilha_gratis.py --blocos "0:curioso,15.6:respiro,17.2:aberto,25.8:final" --duracao 32.6 -o assets/trilha.wav
  (plano.json = {"blocos": [{"de": 0, "ate": 15.6, "clima": "curioso"}, ...]} — o "clima" escolhe o timbre)

Climas:
  curioso  — marimba em colcheias (Lá menor: Am F C G), chimbal leve, bumbo nos tempos 1 e 3
  tensao   — pulso grave em semínimas, pad escuro, sem melodia
  respiro  — só um pad baixo segurando (pausa antes da revelação; som_pro.py põe o riser)
  aberto   — maior e cheio (C G Am F): pad + arpejo em semicolcheias + bumbo em todo tempo + palma no 2 e 4
  alegre   — como aberto, mais agudo e saltitante
  final    — aberto mais leve e um acorde final segurando até o fim
Saída: WAV 48 kHz estéreo a −20 LUFS (como a trilha por IA): mixe com `--volume-trilha 0.25` e meça a margem da voz.
"""
import argparse
import json
import os
import subprocess
import tempfile

import numpy as np
from scipy.io import wavfile

SR = 48000
NOTA = {"A2": 110.0, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F2": 87.31, "F3": 174.61, "G2": 98.0, "G3": 196.0, "A3": 220.0, "B3": 246.94,
        "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.0, "A4": 440.0, "B4": 493.88, "C5": 523.25}
MENOR = [("A2", ["A3", "C4", "E4"]), ("F2", ["F3", "A3", "C4"]), ("C3", ["C4", "E4", "G4"]), ("G2", ["G3", "B3", "D4"])]
MAIOR = [("C3", ["C4", "E4", "G4"]), ("G2", ["G3", "B3", "D4"]), ("A2", ["A3", "C4", "E4"]), ("F2", ["F3", "A3", "C4"])]
ESCUROS = ("curioso", "tensao", "respiro")


def env(n, ataque, queda):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t * queda)


def marimba(f, dur, vol):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return vol * (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 30)) * env(n, 0.003, 9)


def pad(fs, dur, vol, brilho=0.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t) + brilho * np.sin(2 * np.pi * 2 * f * t + 0.3) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t) for f in fs) / len(fs)
    a = np.minimum(1, t / 0.35) * np.minimum(1, (dur - t) / 0.3)
    return vol * x * np.clip(a, 0, 1)


def bumbo(vol):
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    return vol * np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-t * 32)) / SR) * np.exp(-t * 13)


def ruido(dur, queda, vol, seed):
    n = int(dur * SR)
    r = np.random.default_rng(seed).standard_normal(n)
    r = np.diff(r, prepend=0)  # mais agudo
    return vol * r * env(n, 0.001, queda)


def somar(x, y, ini):
    a = int(ini * SR)
    if a >= len(x):
        return
    b = min(len(x), a + len(y))
    x[a:b] += y[: b - a]


def gerar(blocos, duracao, bpm):
    x = np.zeros(int(duracao * SR) + SR)
    batida = 60 / bpm
    compasso = 4 * batida

    def bloco(t):
        for b in blocos:
            if b["de"] <= t < b["ate"]:
                return b
        return blocos[-1]

    def clima(t):
        return bloco(t)["clima"].lower()

    # cada bloco REINICIA o compasso: toda troca de bloco (a revelação inclusive) cai num tempo 1
    cortes = {0.0, duracao}
    for b in blocos:
        n = 0
        while b["de"] + n * compasso < b["ate"]:
            cortes.add(round(b["de"] + n * compasso, 4))
            n += 1
    cortes = sorted(cortes)
    for a, b in zip(cortes, cortes[1:]):
        if b - a < 0.05:
            continue
        c = clima(a)
        baixo, acorde = (MENOR if c in ESCUROS else MAIOR)[int(round((a - bloco(a)["de"]) / compasso)) % 4]
        fs = [NOTA[n] for n in acorde]
        if c == "respiro":
            somar(x, pad([NOTA["A2"]] + fs[:2], b - a, 0.10, 0.05), a)
            continue
        if c == "tensao":
            somar(x, pad([f / 2 for f in fs], b - a, 0.14, 0.1), a)
        else:
            somar(x, pad(fs, b - a, 0.10 if c == "curioso" else 0.16, 0.2 if c == "curioso" else 0.4), a)
        somar(x, pad([NOTA[baixo]], b - a, 0.16, 0.0), a)

    # notas e bateria na grade de semicolcheias (grade recomeça em cada bloco)
    passo = batida / 4
    eventos = []
    for b in blocos:
        n = 0
        while b["de"] + n * passo < b["ate"] - 1e-6:
            eventos.append((b["de"] + n * passo, n))
            n += 1
    for k, (t, n) in enumerate(eventos):
        c = clima(t)
        _, acorde = (MENOR if c in ESCUROS else MAIOR)[(n // 16) % 4]
        fs = [NOTA[x] for x in acorde]
        sub = n % 16  # posição no compasso do bloco
        if c == "curioso":
            if sub % 2 == 0:
                f = fs[(sub // 2) % 3] * (2 if (sub // 2) % 4 == 3 else 1)
                somar(x, marimba(f, 0.5, 0.20), t)
            if sub % 4 == 2:
                somar(x, ruido(0.06, 70, 0.05, k), t)
            if sub in (0, 8):
                somar(x, bumbo(0.45), t)
        elif c == "tensao":
            if sub % 4 == 0:
                somar(x, bumbo(0.5), t)
        elif c in ("aberto", "alegre", "final"):
            leve = 0.6 if c == "final" else 1.0
            oit = 2 if c == "alegre" else 1
            f = fs[[0, 1, 2, 1][sub % 4]] * (2 if sub % 8 >= 4 else 1) * oit
            somar(x, marimba(f, 0.35, 0.15 * leve), t)
            if sub % 4 == 0:
                somar(x, bumbo(0.55 * leve), t)
            if sub in (4, 12):
                somar(x, ruido(0.18, 22, 0.16 * leve, k), t)  # palma
            if sub % 2 == 1:
                somar(x, ruido(0.04, 90, 0.04 * leve, k + 7), t)
    if blocos[-1]["clima"].lower() == "final":  # acorde final segurando
        somar(x, pad([NOTA["C4"], NOTA["E4"], NOTA["G4"], NOTA["C5"]], 2.2, 0.18, 0.4), duracao - 2.2)
    x = x[: int(duracao * SR)]
    return x / (np.max(np.abs(x)) or 1) * 0.89


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plano", help="plano.json com blocos {de, ate, clima}")
    ap.add_argument("--blocos", help='atalho: "0:curioso,15.6:respiro,17.2:aberto"')
    ap.add_argument("--duracao", type=float, required=True)
    ap.add_argument("--bpm", type=float, default=100)
    ap.add_argument("-o", "--saida", required=True)
    a = ap.parse_args()

    if a.plano:
        blocos = json.load(open(a.plano, encoding="utf-8"))["blocos"]
    elif a.blocos:
        blocos = [{"de": float(d), "clima": c} for d, c in (p.split(":") for p in a.blocos.split(","))]
    else:
        raise SystemExit("informe --plano ou --blocos")
    blocos = sorted(blocos, key=lambda b: float(b["de"]))
    for i, b in enumerate(blocos):
        b["de"] = float(b["de"])
        b["ate"] = float(blocos[i + 1]["de"]) if i + 1 < len(blocos) else a.duracao
    x = gerar(blocos, a.duracao, a.bpm)
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    tmp = os.path.join(tempfile.mkdtemp(), "bruto.wav")
    wavfile.write(tmp, SR, np.stack([x, x], 1).astype(np.float32))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", "afade=t=in:d=0.2,loudnorm=I=-20:TP=-2:LRA=11", "-ar", str(SR), a.saida], check=True)
    for b in blocos:
        print(f"  {b['de']:5.1f}–{b['ate']:5.1f} s  {b['clima']}")
    print(f"{a.bpm:.0f} BPM · {a.duracao:.1f} s → {a.saida} (grátis)")


if __name__ == "__main__":
    main()
