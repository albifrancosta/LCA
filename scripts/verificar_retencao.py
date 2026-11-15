"""Confere a retenção de um vídeo pronto (padrões P07, P10, P14, P53) antes da entrega.

Uso:
  python verificar_retencao.py video.mp4 --falas remotion/src/falas.json [--tipo anuncio|historia] [-o retencao.md]

Mede, quadro a quadro (10 por segundo, em miniatura cinza):
- trechos parados: tempo sem mudança visual relevante (corte, clipe com ação, tela trocando) acima do limite
  (anúncio 2,5 s · história 3,5 s); zoom lento e legenda não contam como mudança;
- abertura: cortes nos 3 primeiros segundos;
- re-gancho: o que acontece entre 40% e 50% do vídeo (mudança forte + fala de virada/pergunta);
- final em loop: o quadro final parece com o começo? as últimas falas retomam palavras da 1ª?
Gera um relatório em markdown com ✅ / ⚠️ e o que fazer.
"""
import argparse
import json
import re
import subprocess
import unicodedata

import numpy as np

FPS = 10
W, H = 54, 96
VIRADA = {"agora", "mas", "imagina", "entao", "porem", "so", "quando", "derepente", "ate"}


def quadros(video):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--falas", help="falas com tempo de cada palavra (timeline_comercial.py)")
    ap.add_argument("--tipo", default="historia", choices=["anuncio", "historia"])
    ap.add_argument("-o", "--saida", default="retencao.md")
    a = ap.parse_args()

    q = quadros(a.video)
    dur = len(q) / FPS
    dif = np.abs(np.diff(q, axis=0)).mean(axis=(1, 2))  # 0–255 por passo de 0,1 s
    corte = dif > 18  # troca de plano
    acao = dif > 4.5  # movimento visível (clipe, tela animando, elemento entrando)
    mudou = corte | acao
    limite = 2.5 if a.tipo == "anuncio" else 3.5

    # trechos parados
    parados, ini = [], None
    for i, m in enumerate(list(mudou) + [True]):
        t = (i + 1) / FPS
        if not m and ini is None:
            ini = t
        elif m and ini is not None:
            if t - ini > limite:
                parados.append((ini, t))
            ini = None
    cortes = [(i + 1) / FPS for i in np.nonzero(corte)[0]]
    cortes_3s = [c for c in cortes if c <= 3]

    # falas
    palavras = []
    if a.falas:
        for f in json.load(open(a.falas, encoding="utf-8")):
            palavras += f.get("palavras", [])
    janela = (0.4 * dur, 0.5 * dur)
    no_meio = [w["text"] for w in palavras if janela[0] - 1 <= w["start"] <= janela[1]]
    corte_meio = [c for c in cortes if janela[0] - 1 <= c <= janela[1]]
    pausa_meio = any(w2["start"] - w1["end"] > 0.8 and janela[0] - 1 <= w1["end"] <= janela[1] for w1, w2 in zip(palavras, palavras[1:]))
    palavra_virada = any(norm(t) in VIRADA or t.endswith("?") for t in no_meio)
    regancho = bool(corte_meio) and (pausa_meio or palavra_virada)

    # loop: quadro final x começo (histograma) e palavras repetidas
    def hist(x):
        h, _ = np.histogram(x, bins=32, range=(0, 255))
        return h / (h.sum() or 1)
    ini_h = hist(q[int(0.5 * FPS):int(2 * FPS)])
    melhor = max((1 - 0.5 * np.abs(hist(q[i:i + FPS]) - ini_h).sum(), i / FPS) for i in range(max(0, int((dur - 12) * FPS)), len(q) - FPS, FPS // 2))
    prim = {norm(w["text"]) for w in palavras[:15] if len(norm(w["text"])) > 3}
    fim = {norm(w["text"]) for w in palavras[-25:] if len(norm(w["text"])) > 3}
    eco = sorted(prim & fim)

    ok, alerta = "✅", "⚠️"
    nome = a.video.replace("\\", "/").split("/")[-1]
    linhas = [f"# Retenção — {nome}", "",
              f"Duração {dur:.1f} s · tipo **{a.tipo}** · limite sem mudança visual {limite} s · {len(cortes)} cortes", "",
              "| Checagem | Resultado | Detalhe |", "|---|---|---|"]
    linhas.append(f"| Abertura (P03/P07) | {ok if cortes_3s or mudou[:3 * FPS].mean() > 0.3 else alerta} | {len(cortes_3s)} corte(s) e {mudou[:3 * FPS].mean():.0%} do tempo com movimento nos 3 s iniciais |")
    if parados:
        det = "; ".join(f"{s:.1f}–{e:.1f} s ({e - s:.1f} s)" for s, e in parados)
        linhas.append(f"| Trechos parados (P10) | {alerta} | {det} — adicione um corte, zoom mais forte, elemento entrando ou onomatopeia |")
    else:
        linhas.append(f"| Trechos parados (P10) | {ok} | nenhum trecho acima de {limite} s |")
    linhas.append(f"| Re-gancho 40–50% (P14) | {ok if regancho else alerta} | {janela[0]:.1f}–{janela[1]:.1f} s · corte: {'sim' if corte_meio else 'não'} · pausa/virada: {'sim' if (pausa_meio or palavra_virada) else 'não'} · fala: \"{' '.join(no_meio)[:90]}\" |")
    linhas.append(f"| Final em loop (P53) | {ok if melhor[0] > 0.8 or eco else alerta} | quadro mais parecido com o começo em {melhor[1]:.1f} s (semelhança {melhor[0]:.0%}); palavras do início que voltam no fim: {', '.join(eco) or '—'} |")
    linhas += ["", "_Movimento medido por diferença entre quadros (miniatura cinza, 10/s). Zoom lento e troca de legenda ficam abaixo do limiar de propósito._"]
    open(a.saida, "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
