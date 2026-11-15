"""Batida da trilha: andamento (BPM), batidas, inícios de compasso e o "drop" — e alinha a trilha ao vídeo.

Uso:
  python batida.py assets/trilha.wav                              → mostra BPM, compassos, drop; grava assets/trilha.wav.batida.json
  python batida.py assets/trilha.wav --cortes 6.6,11.9,22.4       → diz a distância de cada corte ao compasso mais próximo
  python batida.py assets/trilha.wav --drop-em 25.7 -o assets/trilha-alinhada.wav
        → desloca a música (silêncio no começo ou corte do início) para o drop cair no segundo 25,7 (ex.: "com a MinhaMarca")

Só numpy/scipy + ffmpeg (nada para instalar). Regras de uso (padrão P42):
  - a revelação (virada/produto) cai no DROP; trocas de cena caem no início de compasso (tolerância ±0,12 s);
  - trilha gerada por IA com plano de blocos (trilha_ia.py) já troca no tempo certo: aqui só confira.
"""
import argparse
import json
import subprocess

import numpy as np
from scipy.signal import stft

SR = 22050
HOP = 512


def carregar(arq):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", arq, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def analisar(y):
    f, _, Z = stft(y, fs=SR, nperseg=2048, noverlap=2048 - HOP)
    S = np.log1p(np.abs(Z))
    fluxo = np.maximum(0, np.diff(S, axis=1)).sum(0)  # força de início de nota
    fluxo = (fluxo - fluxo.mean()) / (fluxo.std() or 1)
    fps = SR / HOP
    # andamento: autocorrelação do fluxo entre 70 e 180 BPM, com preferência suave por ~110
    ac = np.correlate(fluxo, fluxo, mode="full")[len(fluxo) - 1:]
    lags = np.arange(len(ac))
    bpm = 60 * fps / np.maximum(lags, 1)
    ok = (bpm >= 70) & (bpm <= 180)
    peso = ac * np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 110) / 0.9) ** 2)
    lag = int(lags[ok][np.argmax(peso[ok])])
    tempo = 60 * fps / lag
    # fase: deslocamento da grade que mais coincide com os inícios
    fase = int(np.argmax([fluxo[p::lag].sum() for p in range(lag)]))
    batidas = np.arange(fase, len(fluxo), lag) / fps
    # energia (RMS) por janela e graves (bumbo) por batida
    rms = np.sqrt(np.convolve(y ** 2, np.ones(HOP) / HOP, mode="same"))[::HOP]
    t_rms = np.arange(len(rms)) * HOP / SR
    graves = np.abs(Z[f < 150]).sum(0)
    t_g = np.arange(len(graves)) * HOP / SR
    e = np.array([rms[(t_rms >= b) & (t_rms < b + 0.25)].mean() if np.any((t_rms >= b) & (t_rms < b + 0.25)) else 0 for b in batidas])
    k = np.array([graves[(t_g >= b - 0.03) & (t_g < b + 0.08)].max() if np.any((t_g >= b - 0.03) & (t_g < b + 0.08)) else 0 for b in batidas])
    # drop: batida em que a energia dos 2 s seguintes mais salta em relação aos 2 s anteriores
    melhor, drop = 0.0, None
    dur = len(y) / SR
    for i, b in enumerate(batidas):
        if b < 3 or b > dur - 3:  # entrada e saída em fade não contam como drop
            continue
        a_ = rms[(t_rms >= b - 2) & (t_rms < b)]
        c_ = rms[(t_rms >= b) & (t_rms < b + 2)]
        if len(a_) and len(c_) and a_.mean() > 1e-6:
            r = c_.mean() / a_.mean()
            if r > melhor:
                melhor, drop = r, i
    if drop is not None:
        lo, hi = max(1, drop - 3), min(len(e) - 1, drop + 3)
        drop = max(range(lo, hi + 1), key=lambda i: e[i] - e[i - 1])
    tem_drop = drop is not None and melhor > 1.4
    fase4 = drop % 4 if tem_drop else int(np.argmax([k[p::4].mean() if len(k[p::4]) else 0 for p in range(4)]))
    compassos = batidas[fase4::4]
    return {"bpm": round(float(tempo), 1), "batida_s": round(60 / tempo, 4), "duracao": round(len(y) / SR, 2),
            "batidas": [round(float(b), 3) for b in batidas], "compassos": [round(float(b), 3) for b in compassos],
            "drop": round(float(batidas[drop]), 3) if tem_drop else None, "forca_drop": round(float(melhor), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trilha")
    ap.add_argument("--cortes", help="tempos de corte do vídeo, separados por vírgula")
    ap.add_argument("--drop-em", type=float, help="segundo do vídeo onde o drop deve cair")
    ap.add_argument("-o", "--saida", help="trilha alinhada (com --drop-em)")
    a = ap.parse_args()

    y = carregar(a.trilha)
    d = analisar(y)
    json.dump(d, open(a.trilha + ".batida.json", "w", encoding="utf-8"), indent=1)
    print(f"{d['bpm']} BPM · batida {d['batida_s']} s · {d['duracao']} s")
    print(f"drop: {d['drop']} s (energia ×{d['forca_drop']})" if d["drop"] is not None else f"drop: nenhum claro (energia ×{d['forca_drop']}; trilha constante)")
    print("compassos:", ", ".join(f"{b:.2f}" for b in d["compassos"][:24]), "…" if len(d["compassos"]) > 24 else "")
    if a.cortes:
        comp = np.array(d["compassos"])
        print("\nCortes × compasso mais próximo (±0,12 s = no tempo):")
        for c in (float(x) for x in a.cortes.split(",")):
            m = comp[np.argmin(np.abs(comp - c))] if len(comp) else c
            dif = c - m
            print(f"  {c:6.2f} s → compasso {m:6.2f} s ({dif:+.2f} s) {'✅' if abs(dif) <= 0.12 else '⚠️ mova o corte ou a trilha'}")
    if a.drop_em is not None:
        if d["drop"] is None:
            raise SystemExit("sem drop claro nesta trilha: escolha um compasso com --cortes ou use outra trilha")
        desloc = a.drop_em - d["drop"]
        saida = a.saida or a.trilha.rsplit(".", 1)[0] + "-alinhada.wav"
        filtro = f"adelay={int(desloc * 1000)}:all=1" if desloc >= 0 else f"atrim=start={-desloc},asetpts=PTS-STARTPTS"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.trilha, "-af", filtro, saida], check=True)
        print(f"\ntrilha deslocada {desloc:+.2f} s → drop em {a.drop_em:.2f} s: {saida}")


if __name__ == "__main__":
    main()
