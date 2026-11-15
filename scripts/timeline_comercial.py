"""Monta a timeline de um comercial (modo COMERCIAL) a partir das falas geradas.

Uso:
  python timeline_comercial.py falas.json --voz assets/voz -o remotion/src/falas.json [--fps 30]

Para cada fala de falas.json ({id, quem, inicio, texto, legenda?}) com <voz>/<id>.wav:
- transcreve com faster-whisper (tempo de cada palavra);
- alinha as palavras da LEGENDA (grafia escrita da marca) aos tempos da fala (pronúncia de config/marca.json);
- calcula a amplitude por quadro (para a onda sonora acompanhar a voz).
Saída: [{id, quem, inicio, fim, palavras:[{text,start,end}], amplitude:[0..1 por quadro]}], tempos absolutos.
"""
import argparse
import difflib
import json
import os
import re
import unicodedata
import wave

import numpy as np


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]", "", t)
    import marca  # variantes que a transcrição escreve para a marca (config/marca.json)
    return marca.unificar([t])[0]


def amplitude(arq, fps):
    with wave.open(arq) as w:
        taxa, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    passo = int(taxa / fps)
    rms = [float(np.sqrt(np.mean(x[i:i + passo] ** 2))) for i in range(0, len(x), passo)]
    topo = max(rms) or 1
    return [round(min(1, r / topo), 3) for r in rms], len(x) / taxa


def alinhar(escritas, faladas):
    """escritas: tokens da legenda; faladas: [(palavra, ini, fim)] do whisper. Devolve tempos por token escrito."""
    a = [norm(t) for t in escritas]
    b = [norm(w[0]) for w in faladas]
    tempos = [None] * len(escritas)
    for bloco in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(bloco.size):
            tempos[bloco.a + k] = faladas[bloco.b + k][1:]
    # tokens sem par: distribui entre os vizinhos conhecidos
    fim_total = faladas[-1][2] if faladas else 0
    i = 0
    while i < len(tempos):
        if tempos[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tempos) and tempos[j] is None:
            j += 1
        ini = tempos[i - 1][1] if i > 0 else 0.0
        fim = tempos[j][0] if j < len(tempos) else fim_total
        passo = (fim - ini) / (j - i)
        for k in range(i, j):
            tempos[k] = (ini + passo * (k - i), ini + passo * (k - i + 1))
        i = j
    return tempos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("falas")
    ap.add_argument("--voz", required=True)
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--modelo", default="small")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    m = WhisperModel(a.modelo, compute_type="int8")
    saida = []
    for f in json.load(open(a.falas, encoding="utf-8")):
        arq = os.path.join(a.voz, f"{f['id']}.wav")
        segs, _ = m.transcribe(arq, language="pt", word_timestamps=True, initial_prompt=__import__("marca").vocabulario())
        faladas = [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]
        escritas = f.get("legenda", f["texto"]).split()
        amp, dur = amplitude(arq, a.fps)
        t0 = f["inicio"]
        palavras = [{"text": t, "start": round(t0 + s, 3), "end": round(t0 + e, 3)}
                    for t, (s, e) in zip(escritas, alinhar(escritas, faladas))]
        saida.append({"id": f["id"], "quem": f.get("quem", "narrador"), "inicio": t0, "fim": round(t0 + dur, 3),
                      "palavras": palavras, "amplitude": amp})
        print(f"{f['id']:5} {t0:6.2f}-{t0 + dur:6.2f}s  {len(palavras)} palavras")
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    json.dump(saida, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False)
    # sobreposição entre falas = erro de timeline
    for x, y in zip(saida, saida[1:]):
        if x["fim"] > y["inicio"]:
            print(f"ATENCAO: {x['id']} termina em {x['fim']:.2f}s e {y['id']} comeca em {y['inicio']:.2f}s")


if __name__ == "__main__":
    main()
