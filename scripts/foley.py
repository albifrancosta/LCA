"""Foley e efeitos: o som acompanha o que ACONTECE na imagem (passos, ônibus, violão, risada, porta, chuva forte).

Duas fontes (fal, centavos):
  clipe     MMAudio v2 assiste ao CLIPE animado e gera o som no tempo exato da ação. US$ 0,001/s.
  texto     ElevenLabs SFX v2 gera um efeito por descrição ("ônibus freando na poça"). US$ 0,002/s.
E uma montagem local (grátis):
  pista     lê o contrato de cada plano (roteiro.json → planos[].direcao.som.efeitos) e os tempos reais da montagem
            (remotion/src/historia.json), gera o que faltar e mistura tudo numa pista só — por cima da ambiência, se
            você passar --ambiente. Entra no filme por `montar_historia.py --ambiente <pista>`.

Formato no contrato:  "som": {"efeitos": [{"som": "passos apressados no corredor", "em": 0.2, "dur": 2.0, "vol": 0.8},
                                          {"clipe": true, "som": "guitar strings snapping", "vol": 0.7}]}
  em = segundos depois do início do plano · clipe: true = MMAudio sobre o clipe do plano.

Uso:
  python foley.py clipe --video clips/p35.mp4 --prompt "acoustic guitar strings snapping, thunderstorm" -o sfx/p35.wav --confirmar
  python foley.py texto --prompt "city bus splashing through a puddle" --dur 2.5 -o sfx/onibus.mp3 --confirmar
  python foley.py pista --roteiro roteiro.json --historia remotion/src/historia.json [--ambiente amb.wav] -o assets/foley.wav --confirmar
"""
import argparse
import io
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lipsync import rodar_fal, video_uri  # noqa: E402

TAXA = 48000
PRECO = {"clipe": 0.001, "texto": 0.002}  # API oficial fal, 2026-11-06
MODELO = {"clipe": "fal-ai/mmaudio-v2", "texto": "fal-ai/elevenlabs/sound-effects/v2"}


def efeitos_de(c):
    """`som` pode vir como {"efeitos": [...]} ou direto como lista (rascunho do Gemini)."""
    som = c.get("som") or {}
    ef = som if isinstance(som, list) else som.get("efeitos") or []
    return [e if isinstance(e, dict) else {"som": str(e)} for e in ef]


def duracao(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def gerar_clipe(video, prompt, saida):
    d = duracao(video)
    corpo = {"video_url": video_uri(video), "prompt": prompt or "realistic foley sound effects matching the action",
             "negative_prompt": "music, speech, voice, singing", "duration": round(d, 2)}
    tmp = saida + ".mp4"
    rodar_fal(MODELO["clipe"], corpo, tmp, round(PRECO["clipe"] * d, 4), f"foley {os.path.basename(video)}", tipo="efeito")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-vn", "-ac", "1", "-ar", str(TAXA), saida], check=True)  # MMAudio devolve o vídeo com som
    os.remove(tmp)
    return saida


def gerar_texto(prompt, dur, saida):
    corpo = {"text": prompt, "duration_seconds": max(0.5, min(22, dur)), "prompt_influence": 0.5, "output_format": "mp3_44100_128"}
    return rodar_fal(MODELO["texto"], corpo, saida, round(PRECO["texto"] * dur, 4), f"sfx '{prompt[:40]}'",
                     chave_saida="audio", tipo="efeito")


def ler(arq):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", arq, "-f", "f32le", "-ac", "1", "-ar", str(TAXA), "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def pista(roteiro, historia, saida, ambiente=None, confirmar=False):
    d = json.load(io.open(roteiro, encoding="utf-8"))
    h = json.load(io.open(historia, encoding="utf-8"))
    tempos = {c["id"]: c for c in h.get("cenas", h.get("planos", []))}
    base = os.path.dirname(os.path.abspath(roteiro))
    sfx = os.path.join(base, "assets", "sfx")
    os.makedirs(sfx, exist_ok=True)
    pedidos, custo = [], 0.0
    for p in d["planos"]:
        if p["id"] not in tempos:
            continue
        for k, e in enumerate(efeitos_de(p.get("direcao") or {})):
            arq = os.path.join(sfx, f"{p['id']}-{k + 1}." + ("wav" if e.get("clipe") else "mp3"))
            clip = os.path.join(base, "assets", "clips", f"{p['id']}.mp4")
            if e.get("clipe") and not os.path.exists(clip):
                print(f"  {p['id']}: efeito do clipe pedido, mas o plano não tem clipe — pulei")
                continue
            dur = duracao(clip) if e.get("clipe") else float(e.get("dur", 2))
            if not os.path.exists(arq):
                custo += PRECO["clipe" if e.get("clipe") else "texto"] * dur
            pedidos.append((p, e, arq, clip, dur))
    print(f"{len(pedidos)} efeitos · a gerar ≈ US$ {custo:.3f}")
    if not confirmar:
        print("(só orçamento — acrescente --confirmar)")
        return
    total = max(c["fim"] for c in tempos.values()) + 1
    mix = np.zeros(int(total * TAXA), dtype=np.float32)
    if ambiente:
        a = ler(ambiente)[: len(mix)]
        mix[: len(a)] += a
    for p, e, arq, clip, dur in pedidos:
        if not os.path.exists(arq):
            gerar_clipe(clip, e.get("som", ""), arq) if e.get("clipe") else gerar_texto(e["som"], dur, arq)
        x = ler(arq)
        ini = int((tempos[p["id"]]["inicio"] + float(e.get("em", 0))) * TAXA)
        fim_plano = int((tempos[p["id"]]["fim"] + 0.4) * TAXA)  # efeito não vaza mais que 0,4 s no plano seguinte
        x = x[: max(0, min(len(x), fim_plano - ini, len(mix) - ini))]
        if len(x) > 2400:
            x[-2400:] *= np.linspace(1, 0, 2400)
        pico = float(np.max(np.abs(x))) if len(x) else 1.0
        mix[ini: ini + len(x)] += x / (pico or 1.0) * 0.5 * float(e.get("vol", 0.8))  # pico −6 dBFS × vol: fica sob a voz
    mix /= max(1.0, float(np.max(np.abs(mix))) / 0.9)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(TAXA), "-ac", "1", "-i", "-", saida],
                   input=mix.astype(np.float32).tobytes(), check=True)
    print(f"pista de efeitos{' + ambiência' if ambiente else ''} → {saida}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["clipe", "texto", "pista"])
    ap.add_argument("--video")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--dur", type=float, default=2.0)
    ap.add_argument("--roteiro")
    ap.add_argument("--historia")
    ap.add_argument("--ambiente")
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args()
    if a.modo == "pista":
        return pista(a.roteiro, a.historia, a.saida, a.ambiente, a.confirmar)
    d = duracao(a.video) if a.modo == "clipe" else a.dur
    print(f"{a.modo}: {MODELO[a.modo]} · {d:.1f}s → US$ {PRECO[a.modo] * d:.4f}")
    if not a.confirmar:
        print("(só orçamento — acrescente --confirmar)")
        return
    gerar_clipe(a.video, a.prompt, a.saida) if a.modo == "clipe" else gerar_texto(a.prompt, a.dur, a.saida)


if __name__ == "__main__":
    main()
