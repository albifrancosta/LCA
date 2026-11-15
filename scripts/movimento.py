"""Detector de movimento: separa CÂMERA se mexendo (zoom/pan numa foto) de PERSONAGEM/OBJETO se mexendo de verdade.

Regra do estúdio: câmera em movimento NÃO é animação. Um plano cujo contrato pede atuação (andar, falar, tocar,
reagir) e que só tem zoom/pan é REPROVADO e volta para geração.

Como mede (OpenCV, grátis, local):
  para cada par de quadros: rastreia ~400 pontos (Lucas-Kanade), ajusta UMA transformação de câmera
  (similaridade: zoom + deslocamento + giro, RANSAC). Depois desfaz essa câmera no quadro anterior e compara com o
  atual: o que ainda difere é movimento PRÓPRIO da cena (fração do quadro, sem as bordas).
  par → parado (nada muda) · camera (≥ 90 % dos pontos seguem a câmera e < 0,6 % do quadro se mexe sozinho) · animado.
  plano → estatico / so_camera / animado (animado = ≥ 35 % dos pares com movimento próprio).

Uso:
  python movimento.py clipe.mp4                         → veredito do arquivo inteiro
  python movimento.py filme.mp4 --cortes auto           → detecta os cortes e dá o veredito de cada plano
  python movimento.py filme.mp4 --janelas 1             → linha do tempo segundo a segundo
  python movimento.py clipe.mp4 --exige-acao            → sai com código 2 se não for "animado" (para o inspetor)
  --json saida.json grava tudo.
"""
import argparse
import json
import sys

import cv2
import numpy as np

LARG = 360


def quadros(video, fps_alvo=8, ini=0.0, fim=None):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    passo = max(1, round(fps / fps_alvo))
    cap.set(cv2.CAP_PROP_POS_MSEC, ini * 1000)
    i0 = i = int(ini * fps)
    while True:
        ok, q = cap.read()
        if not ok:
            break
        t = i / fps
        if fim is not None and t > fim:
            break
        if (i - i0) % passo == 0:
            h, w = q.shape[:2]
            yield t, cv2.cvtColor(cv2.resize(q, (LARG, int(h * LARG / w))), cv2.COLOR_BGR2GRAY)
        i += 1
    cap.release()


def casar_luz(a, b):
    """Ajusta média e desvio de b para os de a (compensação fotométrica global)."""
    ma, sa = float(a.mean()), float(a.std())
    mb, sb = float(b.mean()), float(b.std())
    if sb < 1.0 or sa < 1.0:  # quadro chapado (preto, cinza): só iguala a média
        return np.clip(b.astype(np.float32) - mb + ma, 0, 255).astype(np.uint8)
    return np.clip((b.astype(np.float32) - mb) * (sa / sb) + ma, 0, 255).astype(np.uint8)


def par(a, b):
    """Classifica a passagem a→b: classe, fração de pontos que seguem a câmera e fração do quadro com movimento próprio."""
    h, w = a.shape
    b = casar_luz(a, b)  # P08: fade/flash de luz não é movimento — iguala brilho e contraste antes de comparar
    pts = cv2.goodFeaturesToTrack(a, 400, 0.01, 6)
    dif_bruta = float(np.mean(cv2.absdiff(a, b) > 25))
    if pts is None or len(pts) < 12:
        return {"classe": "parado" if dif_bruta < 0.004 else "animado", "camera": 0.0, "proprio": round(dif_bruta, 4), "fluxo": 0.0}
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(21, 21), maxLevel=3)
    ok = st.ravel() == 1
    p0, p1 = pts[ok].reshape(-1, 2), nxt[ok].reshape(-1, 2)
    fluxo = float(np.median(np.linalg.norm(p1 - p0, axis=1))) if len(p0) else 0.0
    M, inl = (cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=1.0)
              if len(p0) >= 6 else (None, None))
    camera = float(inl.mean()) if inl is not None else 0.0
    if M is None:
        M = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
    desfeito = cv2.warpAffine(a, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    m = int(0.08 * min(h, w))
    d = cv2.absdiff(desfeito, b)[m:h - m, m:w - m]
    d = cv2.morphologyEx((d > 28).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # tira ruído de interpolação
    proprio = float(d.mean())
    if fluxo < 0.25 and proprio < 0.003:
        classe = "parado"
    elif proprio < 0.006:
        classe = "camera"
    else:
        classe = "animado"
    return {"classe": classe, "camera": round(camera, 3), "proprio": round(proprio, 4), "fluxo": round(fluxo, 2)}


def veredito(pares):
    # "animado" aqui é PRÉ-TRIAGEM (há movimento próprio na cena); não prova que o personagem fez a ação — isso é o atuacao.py
    if not pares:
        return {"veredito": "estatico", "parado": 1.0, "camera": 0.0, "animado": 0.0, "proprio_medio": 0.0}
    n = len(pares)
    frac = {c: sum(p["classe"] == c for p in pares) / n for c in ("parado", "camera", "animado")}
    v = "animado" if frac["animado"] >= 0.35 else "so_camera" if frac["camera"] >= 0.3 else "estatico"
    return {"veredito": v, **{c: round(x, 2) for c, x in frac.items()},
            "proprio_medio": round(float(np.mean([p["proprio"] for p in pares])), 4)}


def analisar(video, ini=0.0, fim=None, fps=8):
    qs = list(quadros(video, fps, ini, fim))
    pares = [dict(par(qs[i][1], qs[i + 1][1]), t=round(qs[i][0], 2)) for i in range(len(qs) - 1)]
    return veredito(pares), pares, qs


def cortes(qs, limiar=0.45):
    """Cortes: mais de 45 % dos pixels mudam de um quadro para o outro (calibrado no Plano 47; zoom e legenda ficam < 25 %)."""
    c = [qs[0][0]]
    for i in range(1, len(qs)):
        if float(np.mean(cv2.absdiff(qs[i - 1][1], qs[i][1]) > 40)) > limiar and qs[i][0] - c[-1] > 0.5:
            c.append(qs[i][0])
    return c


def por_plano(pares, qs, cs=None):
    cs = (cs or cortes(qs)) + [qs[-1][0] + 0.01]
    out = []
    for i in range(len(cs) - 1):
        pp = [p for p in pares if cs[i] <= p["t"] < cs[i + 1] - 0.13]  # o par que atravessa o corte não conta
        out.append({"de": round(cs[i], 2), "ate": round(cs[i + 1], 2), **veredito(pp)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--ini", type=float, default=0.0)
    ap.add_argument("--fim", type=float)
    ap.add_argument("--cortes", choices=["auto"])
    ap.add_argument("--janelas", type=float, help="tamanho da janela em segundos para a linha do tempo")
    ap.add_argument("--exige-acao", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    geral, pares, qs = analisar(a.video, a.ini, a.fim)
    saida = {"video": a.video, "geral": geral}
    if a.cortes:
        planos = saida["planos"] = por_plano(pares, qs)
        total = sum(p["ate"] - p["de"] for p in planos) or 1
        dur = lambda v: sum(p["ate"] - p["de"] for p in planos if p["veredito"] == v) / total
        print(f"{len(planos)} planos · animado {dur('animado'):.0%} do tempo · só câmera {dur('so_camera'):.0%} · "
              f"estático {dur('estatico'):.0%}")
        for p in planos:
            print(f"  {p['de']:6.1f}–{p['ate']:6.1f}s  {p['veredito']:9} (pares animados {p['animado']:.0%}, câmera {p['camera']:.0%}, "
                  f"movimento próprio {p['proprio_medio']:.2%})")
    elif a.janelas:
        t, fim = a.ini, (a.fim or qs[-1][0])
        while t < fim:
            print(f"  {t:6.1f}s {veredito([p for p in pares if t <= p['t'] < t + a.janelas])['veredito']}")
            t += a.janelas
    else:
        print(f"{geral['veredito']} · pares: animado {geral['animado']:.0%}, câmera {geral['camera']:.0%}, "
              f"parado {geral['parado']:.0%} · movimento próprio médio {geral['proprio_medio']:.2%} do quadro")
    if a.json:
        json.dump(dict(saida, pares=pares), open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.exige_acao and geral["veredito"] != "animado":
        sys.exit(2)


if __name__ == "__main__":
    main()
