"""Segunda etapa do modo COMERCIAL: põe voz, efeitos e trilha sobre a animação muda e exporta.

Uso:
  python mixar_comercial.py --video out/animacao.mp4 --falas falas.json --voz assets/voz \
      --sfx sfx.json --trilha sintetica -o entrega/comercial.mp4 --duracao 60

- Cada fala de falas.json entra no seu `inicio` (segundos).
- sfx.json: [{"som": "vibrar|pop|whoosh|ding|carimbo|clique|<arquivo.wav>", "inicio": 2.7, "volume": 0.6}]
  Os sons com nome são sintetizados na hora (gratuitos, sem licença) em SKILL_DIR/assets/sfx/.
- --trilha: caminho de um .wav/.mp3 livre de direitos, "sintetica" (trilha leve gerada aqui) ou "nenhuma".
  A trilha abaixa sozinha quando há voz (sidechain).
- Saída: H.264 + AAC 48 kHz, -14 LUFS, duração exata.
"""
import argparse
import json
import os
import subprocess
import wave

import numpy as np

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(SKILL_DIR, "assets", "sfx")
TAXA = 48000


def salvar(arq, x):
    x = np.clip(x, -1, 1)
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with wave.open(arq, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _t(seg):
    return np.arange(int(seg * TAXA)) / TAXA


def sintetizar_sfx(nome):
    rng = np.random.default_rng(7)
    if nome == "vibrar":  # dois zumbidos de celular
        t = _t(0.9)
        env = ((t % 0.45) < 0.32).astype(float)
        x = 0.6 * np.sign(np.sin(2 * np.pi * 165 * t)) * env * (0.6 + 0.4 * np.sin(2 * np.pi * 30 * t))
        x = np.convolve(x, np.ones(24) / 24, mode="same")
    elif nome == "pop":
        t = _t(0.18)
        f = 900 * np.exp(-t * 18) + 300
        x = 0.8 * np.sin(2 * np.pi * np.cumsum(f) / TAXA) * np.exp(-t * 30)
    elif nome == "whoosh":
        t = _t(0.7)
        ruido = rng.standard_normal(len(t))
        env = np.sin(np.pi * t / t[-1]) ** 2
        # passa-baixa que abre e fecha
        y, a = np.zeros_like(ruido), 0.0
        for i, r in enumerate(ruido):
            a += (0.02 + 0.25 * env[i]) * (r - a)
            y[i] = a
        x = y * env
    elif nome == "ding":
        t = _t(1.2)
        x = (0.5 * np.sin(2 * np.pi * 1318.5 * t) + 0.35 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t * 4)
        atraso = int(0.09 * TAXA)
        x[atraso:] += (0.4 * np.sin(2 * np.pi * 1760 * t) * np.exp(-t * 4))[: len(x) - atraso]
    elif nome == "carimbo":
        t = _t(0.35)
        x = 0.9 * np.sin(2 * np.pi * 90 * t) * np.exp(-t * 22) + 0.4 * rng.standard_normal(len(t)) * np.exp(-t * 60)
    elif nome == "telefone":  # toque de telefone fixo: 2 rajadas de 440+480 Hz moduladas
        t = _t(1.3)
        rajada = ((t % 0.6) < 0.4).astype(float)
        x = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * rajada * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 20 * t)))
    elif nome == "clique":
        t = _t(0.06)
        x = 0.6 * rng.standard_normal(len(t)) * np.exp(-t * 120)
    elif nome == "riser":  # tensão que sobe 1,5 s e termina NO golpe (posicione inicio = golpe − 1,5)
        t = _t(1.5)
        f = 180 * (2 ** (t / t[-1] * 2.5))  # sobe ~2,5 oitavas
        tom = np.sin(2 * np.pi * np.cumsum(f) / TAXA) + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / TAXA)
        ruido = rng.standard_normal(len(t))
        y, a = np.zeros_like(ruido), 0.0
        for i, r in enumerate(ruido):  # ruído que abre (passa-baixa subindo)
            a += (0.01 + 0.3 * (t[i] / t[-1]) ** 2) * (r - a)
            y[i] = a
        env = (t / t[-1]) ** 2.2
        x = (0.5 * tom + 0.8 * y) * env
        x[-int(0.02 * TAXA):] *= np.linspace(1, 0, int(0.02 * TAXA))
    elif nome == "hit":  # golpe da revelação: grave que cai + estalo + cauda curta
        t = _t(1.1)
        f = 40 + 90 * np.exp(-t * 9)
        x = 1.0 * np.sin(2 * np.pi * np.cumsum(f) / TAXA) * np.exp(-t * 3.2)
        x += 0.5 * rng.standard_normal(len(t)) * np.exp(-t * 40)
        x += 0.25 * np.sin(2 * np.pi * 523.3 * t) * np.exp(-t * 5)
    elif nome == "tick":  # contador travando no valor final
        t = _t(0.05)
        x = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 140)
    else:
        raise SystemExit(f"som desconhecido: {nome}")
    return x / (np.max(np.abs(x)) or 1) * 0.9


def arquivo_sfx(som):
    if os.path.splitext(som)[1]:
        return som
    arq = os.path.join(SFX_DIR, f"{som}.wav")
    if not os.path.exists(arq):
        salvar(arq, sintetizar_sfx(som))
    return arq


def trilha_sintetica(duracao, arq, bpm=104):
    """Trilha leve e otimista: pad + arpejo + bumbo suave. I–V–vi–IV em Dó."""
    t = _t(duracao)
    batida = 60 / bpm
    acordes = [[261.6, 329.6, 392.0], [196.0, 246.9, 293.7], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6]]
    compasso = batida * 4
    x = np.zeros_like(t)
    for i in range(int(duracao / compasso) + 1):
        ini, fim = int(i * compasso * TAXA), int(min(duracao, (i + 1) * compasso) * TAXA)
        if ini >= len(t):
            break
        tt = t[ini:fim] - t[ini]
        ac = acordes[i % 4]
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (compasso - tt) / 0.3)
        pad = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt) for f in ac) / 3
        x[ini:fim] += 0.18 * pad * env + 0.22 * np.sin(2 * np.pi * ac[0] / 2 * tt) * env
        for n in range(8):  # arpejo em colcheias
            a = ini + int(n * batida / 2 * TAXA)
            if a >= fim:
                break
            f = ac[n % 3] * (2 if n % 4 == 3 else 1)
            tn = t[a:fim] - t[a]
            x[a:fim] += 0.16 * np.sin(2 * np.pi * f * tn) * np.exp(-tn * 7)
    for b in range(int(duracao / batida)):
        a = int(b * batida * TAXA)
        tn = t[a:a + int(0.25 * TAXA)] - t[a]
        x[a:a + len(tn)] += 0.35 * np.sin(2 * np.pi * (55 + 60 * np.exp(-tn * 30)) * tn) * np.exp(-tn * 14)
    fade = np.minimum(1, np.minimum(t / 1.0, (duracao - t) / 1.5))
    salvar(arq, x / np.max(np.abs(x)) * 0.8 * fade)
    return arq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--falas", required=True)
    ap.add_argument("--voz", required=True)
    ap.add_argument("--sfx")
    ap.add_argument("--trilha", default="sintetica")
    ap.add_argument("--volume-trilha", type=float, default=0.16)
    ap.add_argument("--duracao", type=float, required=True)
    ap.add_argument("-o", "--saida", required=True)
    a = ap.parse_args()

    entradas, filtros, vozes, efeitos = ["-i", a.video], [], [], []
    n = 1
    for f in json.load(open(a.falas, encoding="utf-8")):
        entradas += ["-i", os.path.join(a.voz, f"{f['id']}.wav")]
        ms = int(f["inicio"] * 1000)
        filtros.append(f"[{n}:a]aresample={TAXA},aformat=channel_layouts=mono,adelay={ms},apad[v{n}]")
        vozes.append(f"[v{n}]")
        n += 1
    for s in json.load(open(a.sfx, encoding="utf-8")) if a.sfx else []:
        entradas += ["-i", arquivo_sfx(s["som"])]
        ms = int(s["inicio"] * 1000)
        filtros.append(f"[{n}:a]aresample={TAXA},aformat=channel_layouts=mono,volume={s.get('volume', 0.5)},adelay={ms},apad[s{n}]")
        efeitos.append(f"[s{n}]")
        n += 1
    if vozes:
        filtros.append(f"{''.join(vozes)}amix=inputs={len(vozes)}:normalize=0,atrim=0:{a.duracao},asplit=2[voz][chave]")
    else:  # 2026-11-07: vídeo sem voz (texto cinético) — silêncio no lugar da voz (amix=inputs=0 quebrava o ffmpeg)
        filtros.append(f"anullsrc=r={TAXA}:cl=mono,atrim=0:{a.duracao},asplit=2[voz][chave]")
    mix = ["[voz]"] + efeitos
    if a.trilha != "nenhuma":
        trilha = a.trilha
        if trilha == "sintetica":
            trilha = trilha_sintetica(a.duracao, os.path.join(os.path.dirname(os.path.abspath(a.saida)), "trilha-sintetica.wav"))
        entradas += ["-stream_loop", "-1", "-i", trilha]
        filtros.append(f"[{n}:a]aresample={TAXA},aformat=channel_layouts=mono,volume={a.volume_trilha},atrim=0:{a.duracao}[tr]")
        filtros.append("[tr][chave]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[trd]")
        mix.append("[trd]")
    else:
        filtros.append("[chave]anullsink")
    filtros.append(
        f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0,atrim=0:{a.duracao},"
        f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample={TAXA},aformat=channel_layouts=stereo[aout]"
    )
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", *entradas, "-filter_complex", ";".join(filtros),
           "-map", "0:v", "-map", "[aout]", "-t", str(a.duracao),
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "192k", "-ar", str(TAXA), "-movflags", "+faststart", a.saida]
    subprocess.run(cmd, check=True)
    print(a.saida)


if __name__ == "__main__":
    main()
