"""Diretor de voz: lê as falas com o GÊNERO do vídeo, planeja emoção + intensidade + ritmo + pausas + ênfase de cada
fala, gera a voz (Gemini TTS) e OUVE o resultado para conferir se a emoção saiu mesmo (emotion2vec+ e Parselmouth).
Tudo grátis e local, menos o Gemini (cota diária).

Uso:
  # 1) plano (Gemini lê o texto + gênero): emoção, intensidade 1–5, ritmo, pausas, ênfase, direção de voz
  python diretor_voz.py plano falas.json --genero humor --contexto "mini-história romântica, rapaz tímido" -o direcao.json
  # 2) medir áudios já gerados (contra o plano, se houver)
  python diretor_voz.py medir assets/voz/*.wav [--direcao direcao.json] [-o relatorio.md]
  # 3) dirigir: plano (ou --direcao pronto) → gera cada fala → mede → refaz até 2× o que não bateu → relatório
  python diretor_voz.py dirigir falas.json --genero humor --contexto "…" -o assets/voz [--direcao direcao.json]

Entrada: falas.json [{id, texto, quem?, voz?}] ou o roteiro.json do modo HISTÓRIA (usa planos[].fala).
Gêneros: comercial, humor, romance, suspense, drama, institucional, tutorial (cada um com sua curva — GENEROS abaixo).
Medição:
  - emotion2vec+ large (github.com/ddlBoJack/emotion2vec, via FunASR, ~1,2 GB no 1º uso): raiva, nojo, medo, feliz,
    neutro, triste, surpresa — treinado em fala de vários idiomas; é o "ouvido" que diz qual emoção a fala passa.
  - Parselmouth (Praat): tom médio (Hz), variação do tom (semitons p10–p90 = expressividade), volume (dB) e velocidade
    (palavras/s). Faixas calibradas na voz Gemini: tímido/cansado ≈ 6–7 st, desdenhoso/animado ≈ 9+ st.
  - Se a fala não bate, a tentativa seguinte CORRIGE a direção pelo que foi ouvido (CORRECOES), não repete o pedido.
  - direcao.json e relatorio-voz.md ficam na pasta acima da pasta de saída (ex.: -o assets/voz → assets/).
Saída do plano: direcao.json {genero, falas: [{id, texto, quem, emocao, intensidade, ritmo, pausa_antes, pausa_depois,
  enfase, direcao, esperado: {emocoes: [...], variacao: baixa|media|alta}}]} — editável à mão antes do dirigir.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from tts_gemini import URL, chave, sintetizar  # noqa: E402

# Curva de cada gênero: o que o Gemini deve seguir ao planejar (regras de direção de atores/locução).
GENEROS = {
    "comercial": "Energia alta e constante, sorriso na voz, intensidade 3–4 na dor e 4–5 na solução/CTA; ritmo rápido; "
                 "pausa curta (0,2 s) antes do nome do produto; ênfase no benefício e no número.",
    "humor": "Comédia: a graça está no TEMPO. Preparação em tom normal/confiante (intensidade 2–3), pausa de 0,4–0,7 s "
             "ANTES do desastre/piada, e a reação depois SECA e curta (intensidade 1–2, 'deadpan') ou exagerada (5) — "
             "nunca no meio-termo. Personagem tímido: voz baixa, hesitante, sorriso sem graça. Ironia = tom contido. "
             "Personagem SIMPÁTICO (o público torce por ele): deadpan é cansado e autodepreciativo, nunca sarcástico — "
             "não use 'irony', 'sarcastic', 'dry' nem 'contempt' na direção (o TTS soa desdenhoso, medido em 2026-11-05).",
    "romance": "Ternura e vulnerabilidade: ritmo lento, voz mais baixa e próxima (quase confidência), intensidade 2–3, "
               "pausas longas antes do que é difícil dizer; esperança sobe a intensidade, rejeição derruba para 1–2.",
    "suspense": "Baixa energia e tensão crescente: ritmo lento, pausas longas, sussurro nas revelações (intensidade sobe "
                "de 2 até 5 no clímax), frases curtas; nunca alegre.",
    "drama": "Emoção verdadeira e contida: tristeza/raiva com intensidade de 2 a 5 conforme a cena, ritmo lento nos "
             "momentos de dor, pausas antes das frases mais pesadas.",
    "institucional": "Calma, confiante e profissional: intensidade 2–3 constante, ritmo médio, poucas pausas.",
    "tutorial": "Didático e amigável: intensidade 2–3, ritmo médio, pausa curta entre passos, ênfase no número do passo.",
}
EMOCOES = ["comercial", "conversa", "alegria", "empolgacao", "alivio", "ternura", "timidez", "derrota", "teimosia",
           "duvida", "surpresa", "suspense", "medo", "raiva", "urgencia", "tristeza", "ironia", "deadpan", "institucional"]
# emoção planejada → rótulos aceitáveis do emotion2vec (o modelo só conhece 7 emoções básicas)
OUVIDO = {
    "comercial": ["happy"], "alegria": ["happy"], "empolgacao": ["happy", "surprised"], "alivio": ["happy", "neutral"],
    "ternura": ["happy", "neutral", "sad"], "timidez": ["neutral", "sad", "happy"], "derrota": ["sad", "neutral"],
    "teimosia": ["neutral", "happy"], "conversa": ["neutral", "happy"], "duvida": ["neutral", "fearful", "sad"],
    "surpresa": ["surprised", "happy", "fearful"], "suspense": ["neutral", "fearful", "sad"], "medo": ["fearful", "sad"],
    "raiva": ["angry", "disgusted"], "urgencia": ["angry", "fearful", "neutral"], "tristeza": ["sad"],
    "ironia": ["neutral", "disgusted", "happy"], "deadpan": ["neutral", "sad"], "institucional": ["neutral", "happy"],
}
RITMO = {"lento": (0, 2.2), "normal": (2.0, 3.1), "rapido": (2.9, 9)}  # palavras/s
# semitons p10–p90. Calibrado na voz Gemini (Puck) em 2026-11-05: tímido/cansado 6,4–6,8 st, desdenhoso 9,4 st.
VARIACAO = {"baixa": (0, 7.5), "media": (4.5, 10), "alta": (7.5, 40)}
ROTULOS = {"生气/angry": "angry", "厌恶/disgusted": "disgusted", "恐惧/fearful": "fearful", "开心/happy": "happy",
           "中立/neutral": "neutral", "其他/other": "other", "难过/sad": "sad", "吃惊/surprised": "surprised"}
# o que acrescentar à direção quando o ouvido escutou outra coisa (tentativas 2 e 3 corrigem em vez de repetir)
CORRECOES = {
    "disgusted": "warm and gentle, NO sarcasm, NO contempt, NO irony in the voice, self-deprecating and sweet",
    "angry": "calm and soft, no anger, relaxed throat",
    "happy": "less cheerful, no smile in the voice, more tired and low",
    "sad": "a bit brighter, a hint of a smile",
    "neutral": "more expressive and emotional",
    "fearful": "steady and secure, no trembling",
    "surprised": "no surprise, even and controlled",
}
VAR_CORRECAO = {"alta": "flatter and more monotone, less pitch movement", "baixa": "more melodic, more pitch movement"}
PT = {"angry": "raiva", "disgusted": "nojo", "fearful": "medo", "happy": "feliz", "neutral": "neutro", "other": "outro",
      "sad": "triste", "surprised": "surpresa"}

PEDIDO = """Você é diretor de voz/dublagem de vídeos curtos para redes sociais no Brasil.
Gênero: {genero}. Regras do gênero: {regras}
Contexto do vídeo: {contexto}
Para CADA fala abaixo (na ordem, considerando o arco da história), defina:
- emocao: UMA desta lista: {emocoes}
- intensidade: 1 (quase nada) a 5 (máxima)
- ritmo: lento | normal | rapido
- pausa_antes / pausa_depois: segundos de silêncio (0 a 1.2) — use para o tempo cômico/dramático
- enfase: 0 a 2 palavras EXATAS da fala que recebem ênfase
- direcao: direção de voz CURTA EM INGLÊS para um TTS (ex.: "shy and hesitant, quiet, embarrassed little laugh"),
  coerente com emoção, intensidade e ritmo; inclua o personagem (idade/jeito) quando for fala de personagem
- variacao: baixa | media | alta (o quanto o tom de voz sobe e desce)
- porque: 1 frase em português explicando a escolha
Responda só JSON: {{"falas": [{{"id": "...", "emocao": "...", "intensidade": 3, "ritmo": "...", "pausa_antes": 0.0,
"pausa_depois": 0.3, "enfase": ["..."], "direcao": "...", "variacao": "...", "porque": "..."}}]}}

FALAS:
{falas}"""


def carregar_falas(arq):
    d = json.load(open(arq, encoding="utf-8"))
    if isinstance(d, dict) and "planos" in d:  # roteiro.json do modo HISTÓRIA
        voz = (d.get("voz") or {}).get("nome")
        return [{"id": p["id"], "texto": p["fala"], "quem": p.get("quem", "narrador"), "voz": p.get("voz", voz)}
                for p in d["planos"] if p.get("fala")]
    return [{"id": f["id"], "texto": f["texto"], "quem": f.get("quem", "narrador"), "voz": f.get("voz")} for f in d]


def gemini_json(pedido):
    corpo = {"contents": [{"parts": [{"text": pedido}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.5}}
    req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])


def planejar(falas, genero, contexto):
    if genero not in GENEROS:
        sys.exit(f"gênero '{genero}' não existe. Use: {', '.join(GENEROS)}")
    lista = "\n".join(f'{f["id"]} ({f["quem"]}): {f["texto"]}' for f in falas)
    r = gemini_json(PEDIDO.format(genero=genero, regras=GENEROS[genero], contexto=contexto or "-",
                                  emocoes=", ".join(EMOCOES), falas=lista))
    por_id = {x["id"]: x for x in r.get("falas", [])}
    saida = []
    for f in falas:
        x = por_id.get(f["id"], {})
        emo = x.get("emocao") if x.get("emocao") in EMOCOES else "conversa"
        enf = [w for w in (x.get("enfase") or []) if w.lower() in f["texto"].lower()][:2]
        saida.append({**f, "emocao": emo, "intensidade": max(1, min(5, int(x.get("intensidade", 3)))),
                      "ritmo": x.get("ritmo") if x.get("ritmo") in RITMO else "normal",
                      "pausa_antes": round(float(x.get("pausa_antes", 0)), 2),
                      "pausa_depois": round(float(x.get("pausa_depois", 0.3)), 2), "enfase": enf,
                      "direcao": x.get("direcao", ""), "porque": x.get("porque", ""),
                      "esperado": {"emocoes": OUVIDO[emo],
                                   "variacao": x.get("variacao") if x.get("variacao") in VARIACAO else "media"}})
    return {"genero": genero, "contexto": contexto, "falas": saida}


def estilo_tts(f):
    """Direção final para o TTS: direção do plano + intensidade + ritmo + ênfase (curta, em inglês)."""
    forca = {1: "very subtle", 2: "subtle", 3: "moderate", 4: "strong", 5: "very intense, exaggerated"}[f["intensidade"]]
    ritmo = {"lento": "slow pace", "normal": "natural pace", "rapido": "fast pace"}[f["ritmo"]]
    partes = [f["direcao"] or f["emocao"], f"emotion intensity {forca}", ritmo]
    if f["enfase"]:
        partes.append("stress the words " + ", ".join(f'"{w}"' for w in f["enfase"]))
    return ", ".join(p for p in partes if p)


# ---------- ouvido ----------
_modelo = None


def ouvir_emocao(wav):
    global _modelo
    if _modelo is None:
        import logging
        logging.disable(logging.WARNING)
        from funasr import AutoModel
        print("  carregando emotion2vec+ (1º uso baixa ~1,2 GB)…", file=sys.stderr)
        _modelo = AutoModel(model="emotion2vec/emotion2vec_plus_large", hub="hf", disable_update=True,
                            disable_pbar=True, log_level="ERROR")
    r = _modelo.generate(wav, granularity="utterance", extract_embedding=False, disable_pbar=True)[0]
    notas = {ROTULOS[l]: float(s) for l, s in zip(r["labels"], r["scores"]) if l in ROTULOS}
    return dict(sorted(notas.items(), key=lambda kv: -kv[1]))


def prosodia(wav, texto=None):
    import numpy as np
    import parselmouth
    som = parselmouth.Sound(wav)
    f0 = som.to_pitch(time_step=0.01, pitch_floor=70, pitch_ceiling=500).selected_array["frequency"]
    f0 = f0[f0 > 0]
    inten = som.to_intensity(minimum_pitch=70, time_step=0.01).values.flatten()
    limiar = inten.max() - 25
    dur = som.get_total_duration()
    falado = inten[inten > limiar]
    p = {"duracao": round(dur, 2), "volume_db": round(float(np.mean(falado)), 1) if len(falado) else None}
    if len(f0) > 10:
        p["tom_hz"] = round(float(np.median(f0)))
        p["variacao_st"] = round(float(12 * np.log2(np.percentile(f0, 90) / np.percentile(f0, 10))), 1)
    if texto:
        # tempo de fala = duração − silêncios longos (> 0,25 s): mais justo que a duração bruta
        silencio, corrida = 0.0, 0
        for q in inten < limiar:
            corrida = corrida + 1 if q else 0
            if corrida > 25:
                silencio += 0.01
        p["palavras_s"] = round(len(texto.split()) / max(0.5, dur - silencio), 2)
    return p


def avaliar(f, emo, pros):
    """Compara o que se ouve com o que foi pedido. Retorna (ok, notas, pontuação)."""
    esp = f.get("esperado") or {"emocoes": OUVIDO.get(f.get("emocao", "conversa"), ["neutral"]), "variacao": "media"}
    aceitas = sum(emo.get(e, 0) for e in esp["emocoes"])
    topo = next(iter(emo))
    notas, ok = [], True
    if topo not in esp["emocoes"] and aceitas < 0.35:
        ok = False
        notas.append(f"soou {PT[topo]} ({emo[topo]:.0%}); pedido {f.get('emocao')} → aceito "
                     f"{'/'.join(PT[e] for e in esp['emocoes'])} = {aceitas:.0%}")
    lo, hi = VARIACAO[esp["variacao"]]
    v = pros.get("variacao_st")
    if v is not None and not lo <= v <= hi:
        notas.append(f"variação do tom {v} st (pedido {esp['variacao']}: {lo}–{hi})")
    lo, hi = RITMO.get(f.get("ritmo", "normal"), RITMO["normal"])
    r = pros.get("palavras_s")
    if r is not None and not lo <= r <= hi:
        notas.append(f"{r} palavras/s (pedido {f.get('ritmo')}: {lo}–{hi})")
    return ok, notas, round(aceitas - 0.1 * (len(notas) - (0 if ok else 1)), 3)


def linha_relatorio(f, emo, pros, ok, notas):
    top3 = ", ".join(f"{PT[k]} {v:.0%}" for k, v in list(emo.items())[:3])
    pedido = f"{f['emocao']} {f['intensidade']}/5 · {f['ritmo']}" if f.get("emocao") else "—"
    res = "✅" if ok and not notas else ("⚠️ " if ok else "❌ ") + "; ".join(notas)
    return (f"| {f['id']} | {pedido} | {top3} | {pros.get('variacao_st', '—')} st · {pros.get('palavras_s', '—')} p/s · "
            f"{pros.get('volume_db', '—')} dB | {res} |")


CABECALHO = "| fala | pedido | ouvido (emotion2vec+) | prosódia | resultado |\n|---|---|---|---|---|"


def mostrar_plano(d):
    print(f"Gênero: {d['genero']}")
    for f in d["falas"]:
        enf = f" · ênfase: {', '.join(f['enfase'])}" if f["enfase"] else ""
        print(f"  {f['id']:6} {f['emocao']:11} {f['intensidade']}/5 {f['ritmo']:6} "
              f"pausa {f['pausa_antes']:.1f}/{f['pausa_depois']:.1f}s{enf}")
        print(f"         “{f['texto'][:70]}” — {f['porque']}")


def cmd_plano(a):
    d = planejar(carregar_falas(a.falas), a.genero, a.contexto)
    json.dump(d, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mostrar_plano(d)
    print(f"\nPlano salvo em {a.saida} (edite à mão se quiser e rode `dirigir --direcao {a.saida}`)")


def cmd_medir(a):
    arqs = [x for p in a.wavs for x in glob.glob(p)]
    plano = {f["id"]: f for f in json.load(open(a.direcao, encoding="utf-8"))["falas"]} if a.direcao else {}
    linhas = [CABECALHO]
    for w in arqs:
        fid = os.path.splitext(os.path.basename(w))[0]
        f = plano.get(fid, {"id": fid})
        emo, pros = ouvir_emocao(w), prosodia(w, f.get("texto"))
        ok, notas, _ = avaliar(f, emo, pros) if f.get("emocao") else (True, [], 0)
        linhas.append(linha_relatorio(f, emo, pros, ok, notas))
    texto = "\n".join(linhas)
    print(texto)
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write("# Relatório de voz\n\n" + texto + "\n")


def cmd_dirigir(a):
    pasta_proj = os.path.dirname(os.path.abspath(a.saida.rstrip("/\\")))
    if a.direcao:
        d = json.load(open(a.direcao, encoding="utf-8"))
    else:
        d = planejar(carregar_falas(a.falas), a.genero, a.contexto)
        json.dump(d, open(os.path.join(pasta_proj, "direcao.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mostrar_plano(d)
    os.makedirs(a.saida, exist_ok=True)
    so = set(a.so.split(",")) if a.so else None
    linhas = [CABECALHO]
    for f in d["falas"]:
        if so and f["id"] not in so:
            continue
        voz = f.get("voz") or a.voz or "Puck"
        final = os.path.join(a.saida, f"{f['id']}.wav")
        if os.path.exists(final) and not a.forcar:  # retomar sem refazer o que já saiu
            continue
        melhor, extra = None, []
        for tent in range(1 + a.refazer):
            tmp = final + f".t{tent}.wav"
            estilo = estilo_tts(f) + (", " + ", ".join(extra) if extra else "")
            try:
                sintetizar(f["texto"], voz, estilo, tmp)
            except SystemExit as e:  # tom complicado demais: tenta a direção curta, depois sem direção
                print(f"  {f['id']}: {e} — tentando direção simples", file=sys.stderr)
                try:
                    sintetizar(f["texto"], voz, f.get("direcao") or "", tmp)
                except SystemExit:
                    sintetizar(f["texto"], voz, "", tmp)
            emo, pros = ouvir_emocao(tmp), prosodia(tmp, f["texto"])
            ok, notas, pont = avaliar(f, emo, pros)
            print(f"  {f['id']} tentativa {tent + 1}: {'ok' if ok else 'não bateu'} · "
                  f"{PT[next(iter(emo))]} {next(iter(emo.values())):.0%} {'; '.join(notas)}")
            if melhor is None or pont > melhor[0]:
                melhor = (pont, tmp, emo, pros, ok, notas)
            if ok and not notas:
                break
            # próxima tentativa: corrige a direção pelo que foi ouvido (em vez de repetir o mesmo pedido)
            topo = next(iter(emo))
            extra = []
            if not ok and topo in CORRECOES:
                extra.append(CORRECOES[topo])
            v, faixa = pros.get("variacao_st"), VARIACAO[f["esperado"]["variacao"]]
            if v is not None and v > faixa[1]:
                extra.append(VAR_CORRECAO["alta"])
            elif v is not None and v < faixa[0]:
                extra.append(VAR_CORRECAO["baixa"])
        shutil.copyfile(melhor[1], final)
        for t in glob.glob(final + ".t*.wav"):
            os.remove(t)
        linhas.append(linha_relatorio(f, *melhor[2:]))
    rel = os.path.join(pasta_proj, "relatorio-voz.md")
    open(rel, "w", encoding="utf-8").write(f"# Relatório de voz — {d['genero']}\n\n" + "\n".join(linhas) + "\n")
    print("\n".join(linhas))
    print(f"\nRelatório: {rel}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plano")
    p.add_argument("falas")
    p.add_argument("--genero", required=True, choices=list(GENEROS))
    p.add_argument("--contexto", default="")
    p.add_argument("-o", "--saida", default="direcao.json")
    m = sub.add_parser("medir")
    m.add_argument("wavs", nargs="+")
    m.add_argument("--direcao")
    m.add_argument("-o", "--saida")
    g = sub.add_parser("dirigir")
    g.add_argument("falas", nargs="?")
    g.add_argument("--genero", choices=list(GENEROS))
    g.add_argument("--contexto", default="")
    g.add_argument("--direcao", help="plano pronto (pula o Gemini)")
    g.add_argument("--voz", help="voz padrão quando a fala não traz a sua")
    g.add_argument("--so", help="só estes ids (vírgula)")
    g.add_argument("--refazer", type=int, default=2, help="quantas vezes refazer a fala que não bateu (padrão 2)")
    g.add_argument("-o", "--saida", required=True, help="pasta dos WAV")
    g.add_argument("--forcar", action="store_true", help="refaz também as falas que já existem")
    a = ap.parse_args()
    if a.cmd == "dirigir" and not a.direcao and not (a.falas and a.genero):
        ap.error("dirigir precisa de falas.json + --genero, ou --direcao")
    {"plano": cmd_plano, "medir": cmd_medir, "dirigir": cmd_dirigir}[a.cmd](a)


if __name__ == "__main__":
    main()
