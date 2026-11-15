"""Transforma o transcript (tempo de cada palavra) em mapa de batidas para a animação.

Uso:
    python beatmap.py transcript.json [--roteiro ROTEIRO.md] [--fps 30] [-o BEATS.json]

Cenas = linhas da tabela do ROTEIRO.md (coluna Fala), casadas por posição das palavras.
Palavras-chave = trechos em **negrito** na Fala + números.
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PAUSA_GRUPO = 0.15
PAUSA_FRASE = 0.35
MAX_GRUPO = 3


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9%]+", "", t)


def carregar_palavras(path):
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(d, dict):
        if "words" in d:
            d = d["words"]
        elif "segments" in d:
            d = [w for s in d["segments"] for w in s.get("words", [])]
        elif "voices" in d:  # audio_meta.json do media-use
            d = [w for v in d["voices"] for w in v.get("words", [])]
    palavras = []
    for w in d:
        txt = (w.get("text") or w.get("word") or "").strip()
        if not txt or norm(txt) == "":
            continue
        palavras.append({"text": txt, "start": float(w["start"]), "end": float(w["end"])})
    return palavras


def ler_roteiro(path):
    """Retorna lista de cenas: {fala, tokens, keywords:[[tokens]]}."""
    cenas = []
    for linha in Path(path).read_text(encoding="utf-8-sig").splitlines():
        cols = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cols) < 2 or not re.fullmatch(r"\d+", cols[0]):
            continue
        fala = cols[1]
        kws = [[norm(x) for x in k.split() if norm(x)] for k in re.findall(r"\*\*(.+?)\*\*", fala)]
        limpa = fala.replace("**", "")
        tokens = [norm(x) for x in limpa.split() if norm(x)]
        if tokens:
            cenas.append({"fala": limpa, "tokens": tokens, "keywords": kws})
    return cenas


def alinhar(script_tokens, trans_tokens):
    """Mapeia cada token do roteiro para um índice do transcript."""
    sm = difflib.SequenceMatcher(None, script_tokens, trans_tokens, autojunk=False)
    ultimo = len(trans_tokens) - 1
    mapa = [None] * len(script_tokens)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal", "replace"):
            for k in range(i2 - i1):
                mapa[i1 + k] = min(j1 + int(k * (j2 - j1) / (i2 - i1)), j2 - 1)
        elif op == "delete":
            for k in range(i1, i2):
                mapa[k] = min(j1, ultimo)
    return mapa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--roteiro")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("-o", "--out", default="BEATS.json")
    a = ap.parse_args()

    ws = carregar_palavras(a.transcript)
    if not ws:
        sys.exit("transcript sem palavras")
    recuo = 2 / a.fps
    trans_tokens = [norm(w["text"]) for w in ws]

    pauses = [{"start": round(ws[i]["end"], 3), "end": round(ws[i + 1]["start"], 3)}
              for i in range(len(ws) - 1) if ws[i + 1]["start"] - ws[i]["end"] >= PAUSA_GRUPO]

    keyword_idx = set()
    keywords = []
    if a.roteiro:
        cenas = ler_roteiro(a.roteiro)
        if not cenas:
            sys.exit("nenhuma linha de cena encontrada na tabela do roteiro")
        script_tokens = [t for c in cenas for t in c["tokens"]]
        mapa = alinhar(script_tokens, trans_tokens)
        inicios, pos = [], 0
        for ci, c in enumerate(cenas):
            inicios.append(mapa[pos])
            for kw in c["keywords"]:
                for k in range(len(c["tokens"]) - len(kw) + 1):
                    if c["tokens"][k:k + len(kw)] == kw:
                        j1, j2 = mapa[pos + k], mapa[pos + k + len(kw) - 1]
                        keyword_idx.update(range(j1, j2 + 1))
                        keywords.append({"word": " ".join(w["text"] for w in ws[j1:j2 + 1]),
                                         "start": ws[j1]["start"], "end": ws[j2]["end"], "scene": f"s{ci + 1}"})
                        break
            pos += len(c["tokens"])
        textos = [c["fala"] for c in cenas]
    else:
        inicios, textos = [0], None
        for i in range(1, len(ws)):
            gap = ws[i]["start"] - ws[i - 1]["end"]
            if re.search(r"[.!?…]$", ws[i - 1]["text"]) or gap >= PAUSA_FRASE:
                inicios.append(i)

    # cada cena começa depois da anterior
    inicios[0] = 0
    for i in range(1, len(inicios)):
        inicios[i] = min(max(inicios[i], inicios[i - 1] + 1), len(ws) - 1)

    scenes = []
    for si, w0 in enumerate(inicios):
        prox = inicios[si + 1] if si + 1 < len(inicios) else None
        w1 = (prox - 1) if prox is not None else len(ws) - 1
        start = 0.0 if si == 0 else max(0.0, ws[w0]["start"] - recuo)
        end = max(0.0, ws[prox]["start"] - recuo) if prox is not None else ws[-1]["end"]
        texto = textos[si] if textos else " ".join(w["text"] for w in ws[w0:w1 + 1])
        scenes.append({"id": f"s{si + 1}", "start": round(start, 3), "end": round(end, 3),
                       "text": texto, "words": [w0, max(w0, w1)]})

    # números também são palavras-chave
    for i, w in enumerate(ws):
        if re.search(r"\d", w["text"]) and i not in keyword_idx:
            keyword_idx.add(i)
            sc = next((s["id"] for s in scenes if s["words"][0] <= i <= s["words"][1]), None)
            keywords.append({"word": w["text"], "start": w["start"], "end": w["end"], "scene": sc})
    keywords.sort(key=lambda k: k["start"])

    # grupos de legenda
    groups, atual = [], []
    for i, w in enumerate(ws):
        if atual:
            gap = w["start"] - ws[atual[-1]]["end"]
            fim_frase = re.search(r"[.!?…,;:]$", ws[atual[-1]]["text"])
            if len(atual) >= MAX_GRUPO or gap >= PAUSA_GRUPO or fim_frase:
                groups.append(atual)
                atual = []
        atual.append(i)
    if atual:
        groups.append(atual)
    groups = [{"start": round(ws[g[0]]["start"], 3), "end": round(ws[g[-1]]["end"], 3),
               "text": " ".join(ws[i]["text"] for i in g), "key": any(i in keyword_idx for i in g),
               "words": [g[0], g[-1]]} for g in groups]

    out = {"fps": a.fps, "duration": round(ws[-1]["end"], 3), "scenes": scenes,
           "keywords": keywords, "pauses": pauses, "groups": groups}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{a.out}: {len(scenes)} cenas · {len(keywords)} palavras-chave · "
          f"{len(groups)} grupos de legenda · {len(pauses)} pausas · {out['duration']} s")
    for s in scenes:
        print(f"  {s['id']}: {s['start']:6.2f} -> {s['end']:6.2f}  {s['text'][:60]}")


if __name__ == "__main__":
    main()
