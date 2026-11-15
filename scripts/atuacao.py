"""Validador de atuação: o PERSONAGEM executa a ação — não basta haver pixels se mexendo no quadro.

Complementa `movimento.py` (câmera × movimento próprio da cena inteira, só pré-triagem). Aqui, cada personagem:
  - acha e RASTREIA cada pessoa nos quadros (YOLO pose + segmentação, local e grátis; funciona em cartoon) — o sujeito do
    contrato não é "o maior do quadro": com 2+ pessoas de tamanho parecido a identidade fica `nao_verificado` (P17)
  - personagem × cenário: movimento dentro da silhueta × fora (lama e ônibus se mexendo com o rapaz parado = CONGELADO)
  - por parte do corpo: cabeça, tronco, braços, pernas (pontos do esqueleto relativos ao tronco, só contando quando a
    silhueta também mexeu) + deslocamento do corpo
  - POR BEAT do contrato (P18): cada fase precisa ter atuação; beat com fase "pausa" pode ficar parado (pausa dramática).
    Sem beats, cai na regra dos terços (último terço ≥ 30 % da energia do melhor)
  - consistência temporal: proporções do corpo e preenchimento da silhueta pulando ou fugindo da mediana = deformação
  - dados insuficientes (personagem não encontrado, sem silhueta, poucos pares) = `nao_verificado`, NUNCA aprovado (P15/P16)

Estados: aprovado | reprovado | nao_verificado (integridade.py). `veredito` mantém também "ressalvas" (aprovado com avisos).

Uso:
  python atuacao.py clipe.mp4 [--exige cabeca,bracos] [--personagens 1] [--roteiro roteiro.json --plano d2] [--json out.json]
  python atuacao.py filme.mp4 --ini 6.05 --fim 9.55 --exige tronco,bracos,cabeca
  (--roteiro/--plano lê exige, beats e o número de personagens do contrato)
Código de saída: 2 = reprovado · 3 = não verificado. Pesos do YOLO em ~/.cache/yolo (baixados uma vez, ~12 MB).
"""
import argparse
import io
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integridade as ig  # noqa: E402
import movimento  # noqa: E402

PESOS = os.path.join(os.path.expanduser("~"), ".cache", "yolo")
REGIOES = {"cabeca": [0, 1, 2, 3, 4], "bracos": [7, 8, 9, 10], "tronco": [5, 6, 11, 12], "pernas": [13, 14, 15, 16]}
LIMIAR_REGIAO = 0.006     # deslocamento por par (1/8 s) relativo à altura do corpo
LIMIAR_PROPRIO = 0.012    # fração da silhueta que muda sozinha (sem a câmera)
MIN_PARES = 3             # menos que isso medido = não dá para afirmar nada
_modelos = {}


def modelos():
    if not _modelos:
        from ultralytics import YOLO
        os.makedirs(PESOS, exist_ok=True)
        aqui = os.getcwd()
        os.chdir(PESOS)  # o ultralytics baixa os pesos na pasta atual
        try:
            _modelos["pose"], _modelos["seg"] = YOLO("yolo11n-pose.pt"), YOLO("yolo11n-seg.pt")
        finally:
            os.chdir(aqui)
    return _modelos["pose"], _modelos["seg"]


def quadros_cor(video, fps=8, ini=0.0, fim=None):
    cap = cv2.VideoCapture(video)
    f = cap.get(cv2.CAP_PROP_FPS) or 30
    passo = max(1, round(f / fps))
    cap.set(cv2.CAP_PROP_POS_MSEC, ini * 1000)
    i0 = i = int(ini * f)
    while True:
        ok, q = cap.read()
        if not ok or (fim is not None and i / f > fim):
            break
        if (i - i0) % passo == 0:
            h, w = q.shape[:2]
            yield i / f, cv2.resize(q, (movimento.LARG * 2, int(h * movimento.LARG * 2 / w)))
        i += 1
    cap.release()


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-6)


def detectar_todos(q):
    """Todas as pessoas do quadro: [{caixa, kp, kc, mask, conf}]."""
    pose, seg = modelos()
    rp = pose(q, verbose=False, conf=0.25)[0]
    rs = seg(q, verbose=False, conf=0.25, classes=[0], retina_masks=True)[0]
    if not len(rp.boxes):
        return []
    caixas = rp.boxes.xyxy.cpu().numpy()
    kps = rp.keypoints.xy.cpu().numpy()
    kcs = rp.keypoints.conf.cpu().numpy() if rp.keypoints.conf is not None else np.ones((len(caixas), 17))
    sc = rs.boxes.xyxy.cpu().numpy() if rs.masks is not None and len(rs.boxes) else []
    out = []
    for k, cx in enumerate(caixas):
        mask = None
        if len(sc):
            j = int(np.argmax([iou(c, cx) for c in sc]))
            if iou(sc[j], cx) > 0.3:
                mask = rs.masks.data.cpu().numpy()[j] > 0.5
                if mask.shape != q.shape[:2]:
                    mask = cv2.resize(mask.astype(np.uint8), (q.shape[1], q.shape[0])) > 0
        out.append({"caixa": cx, "kp": kps[k], "kc": kcs[k], "mask": mask, "conf": float(rp.boxes.conf[k])})
    return out


def rastrear(dets_por_quadro, iou_min=0.2):
    """Liga as detecções quadro a quadro (IoU guloso). Devolve trilhas [{id, quadros: {i: det}}]."""
    trilhas = []
    for i, dets in enumerate(dets_por_quadro):
        livres = list(range(len(dets)))
        for t in sorted(trilhas, key=lambda x: -len(x["quadros"])):
            ult = max(t["quadros"])
            if i - ult > 3 or not livres:  # some por mais de 3 quadros = trilha encerrada
                continue
            j = max(livres, key=lambda k: iou(dets[k]["caixa"], t["quadros"][ult]["caixa"]))
            if iou(dets[j]["caixa"], t["quadros"][ult]["caixa"]) >= iou_min:
                t["quadros"][i] = dets[j]
                livres.remove(j)
        for j in livres:
            trilhas.append({"id": len(trilhas), "quadros": {i: dets[j]}})
    return trilhas


def peso_trilha(t):
    return sum((d["caixa"][2] - d["caixa"][0]) * (d["caixa"][3] - d["caixa"][1]) for d in t["quadros"].values())


def proporcoes(d):
    kp, kc = d["kp"], d["kc"]
    ok = lambda *i: all(kc[x] > 0.45 for x in i)
    dist = lambda a, b: float(np.linalg.norm(kp[a] - kp[b]))
    r = {}
    if ok(5, 6, 11, 12):
        tronco = (dist(5, 11) + dist(6, 12)) / 2
        if tronco > 5:
            r["ombros/tronco"] = dist(5, 6) / tronco
            if ok(13, 14):
                r["coxa/tronco"] = (dist(11, 13) + dist(12, 14)) / 2 / tronco
            if ok(15, 16, 13, 14):
                r["canela/tronco"] = (dist(13, 15) + dist(14, 16)) / 2 / tronco
    if d["mask"] is not None:
        x1, y1, x2, y2 = d["caixa"]
        r["preenchimento"] = float(d["mask"].sum()) / max(1.0, (x2 - x1) * (y2 - y1))
    return r


def camera(g0, g1):
    M = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
    pts = cv2.goodFeaturesToTrack(g0, 400, 0.01, 6)
    if pts is not None and len(pts) >= 12:
        nx, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, pts, None, winSize=(21, 21), maxLevel=3)
        ok = st.ravel() == 1
        if ok.sum() >= 6:
            M2, _ = cv2.estimateAffinePartial2D(pts[ok].reshape(-1, 2), nx[ok].reshape(-1, 2), method=cv2.RANSAC, ransacReprojThreshold=1.0)
            M = M2 if M2 is not None else M
    return M


def medir_par(a, b, dif, M, t):
    p = {"t": t}
    mk = np.zeros_like(dif)
    for x in (a["mask"], b["mask"]):
        if x is not None:
            mk = mk | x
    if mk.sum() > 50:
        borda = cv2.dilate(mk.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        p["dentro"] = float(dif[mk].mean())
        p["fora"] = float(dif[~borda].mean()) if (~borda).sum() else 0.0
    alt = max(1.0, a["caixa"][3] - a["caixa"][1])
    kpa = cv2.transform(a["kp"].reshape(-1, 1, 2).astype(np.float64), M).reshape(-1, 2)
    boa = (a["kc"] > 0.45) & (b["kc"] > 0.45)
    ct = [x for x in (5, 6, 11, 12) if boa[x]]
    if len(ct) >= 2:
        ca, cb = kpa[ct].mean(0), b["kp"][ct].mean(0)
        p["corpo"] = float(np.linalg.norm(cb - ca)) / alt
        for nome, idx in REGIOES.items():
            ix = [x for x in idx if boa[x]]
            if ix:
                p[nome] = float(np.mean(np.linalg.norm((b["kp"][ix] - cb) - (kpa[ix] - ca), axis=1))) / alt
    return p


def analisar(video, ini=0.0, fim=None, exige=(), beats=None, n_personagens=1):
    qs = list(quadros_cor(video, 8, ini, fim))
    dets = [detectar_todos(q) for _, q in qs]
    trilhas = sorted(rastrear(dets), key=peso_trilha, reverse=True)
    difs = []
    for i in range(len(qs) - 1):
        g0, g1 = cv2.cvtColor(qs[i][1], cv2.COLOR_BGR2GRAY), cv2.cvtColor(qs[i + 1][1], cv2.COLOR_BGR2GRAY)
        g1 = movimento.casar_luz(g0, g1)  # fade/flash não conta como atuação
        M = camera(g0, g1)
        h, w = g0.shape
        dif = cv2.absdiff(cv2.warpAffine(g0, M, (w, h), borderMode=cv2.BORDER_REFLECT), g1) > 28
        difs.append((cv2.morphologyEx(dif.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0, M))
    n = max(1, int(n_personagens or 1))
    sujeitos = trilhas[:n]
    res = []
    for t in sujeitos:
        pares = [medir_par(t["quadros"][i], t["quadros"][i + 1], difs[i][0], difs[i][1], round(qs[i][0], 2))
                 for i in range(len(qs) - 1) if i in t["quadros"] and i + 1 in t["quadros"]]
        res.append(resumo(pares, [t["quadros"].get(i) for i in range(len(qs))], [len(x) for x in dets], exige, beats, ini, len(qs)))
    if not res:  # ninguém encontrado
        res = [resumo([], [None] * len(qs), [len(x) for x in dets], exige, beats, ini, len(qs))]
    r = combinar(res, trilhas, n, len(qs))
    return r, res


def combinar(res, trilhas, n, nq):
    """Junta o resultado dos sujeitos: o pior manda. Ambiguidade de identidade = não verificado (P17)."""
    r = dict(res[0])
    r["problemas"] = [p for x in res for p in x["problemas"]]
    r["sujeitos"] = len(res)
    if len(trilhas) > n and peso_trilha(trilhas[n]) >= 0.5 * peso_trilha(trilhas[n - 1]):
        r["problemas"].append(("media", f"{len(trilhas)} pessoas no quadro e a {n + 1}ª tem tamanho parecido com o sujeito — "
                                        "confirme na revisão visual que o medido é o personagem do contrato"))
        r["identidade_ambigua"] = True
    estados = [x["estado"] for x in res]
    verificado = all(e != ig.NAO_VERIFICADO for e in estados) and not r.get("identidade_ambigua")
    r["estado"] = ig.estado_qa(r["problemas"], verificado)
    notas = [x["nota_atuacao"] for x in res if x["nota_atuacao"] is not None]
    r["nota_atuacao"] = min(notas) if notas and verificado else None
    r["veredito"] = {"reprovado": "reprovado", "nao_verificado": "nao_verificado"}.get(
        r["estado"], "ressalvas" if r["problemas"] else "aprovado")
    return r


def resumo(pares, dets, contagem, exige, beats=None, ini=0.0, nq=None):
    nq = nq or len(dets)
    r = {"quadros": nq, "personagem_visivel": round(sum(d is not None for d in dets) / max(1, nq), 2), "problemas": []}
    den = [p["dentro"] for p in pares if "dentro" in p]
    fo = [p["fora"] for p in pares if "fora" in p]
    r["mov_personagem"] = round(float(np.median(den)), 4) if den else None
    r["mov_cenario"] = round(float(np.median(fo)), 4) if fo else None
    insuficiente = []
    if r["personagem_visivel"] < 0.5:
        insuficiente.append(f"personagem encontrado em só {r['personagem_visivel']:.0%} dos quadros")
    if len(den) < max(MIN_PARES, int(0.4 * max(0, nq - 1))):
        insuficiente.append(f"silhueta medida em só {len(den)} de {max(0, nq - 1)} pares")
    if den:
        if r["mov_personagem"] < LIMIAR_PROPRIO and (r["mov_cenario"] or 0) > 2 * max(r["mov_personagem"], 0.002):
            r["problemas"].append(("grave", f"CONGELADO: o cenário se mexe ({r['mov_cenario']:.1%}) e o personagem não ({r['mov_personagem']:.1%})"))
        elif r["mov_personagem"] < LIMIAR_PROPRIO and not beats_so_pausa(beats):
            r["problemas"].append(("grave", f"personagem quase parado ({r['mov_personagem']:.1%} da silhueta se mexe)"))
        bs = [b for b in _beats(beats) if b["fim"] is not None]
        if bs:  # P18: energia por janela de beat; pausa planejada pode ficar parada
            r["beats"] = []
            for k, b in enumerate(bs, 1):
                v = [p["dentro"] for p in pares if "dentro" in p and ini + b["inicio"] <= p["t"] < ini + b["fim"]]
                e = float(np.mean(v)) if v else None
                r["beats"].append({"beat": k, "fase": b.get("fase"), "energia": None if e is None else round(e, 4), "pares": len(v)})
            ativos = [x["energia"] for x in r["beats"] if x["fase"] != "pausa" and x["energia"] is not None]
            ref = float(np.median(ativos)) if ativos else 0.0
            for x in r["beats"]:
                if x["fase"] == "pausa":
                    continue
                if x["energia"] is None:
                    r["problemas"].append(("media", f"beat {x['beat']} ({x['fase']}): sem quadros medidos nessa janela"))
                elif x["energia"] < max(LIMIAR_PROPRIO, (0.1 if x["fase"] == "antecipacao" else 0.3) * ref):
                    # antecipação é sutil por natureza (levar a xícara à boca × café explodindo): régua menor (2026-11-06, c01e)
                    r["problemas"].append(("grave", f"beat {x['beat']} ({x['fase']}): sem atuação nessa janela "
                                                    f"({x['energia']:.1%} da silhueta) — a ação pedida não acontece"))
        else:
            en = [float(np.mean(x)) if len(x) else 0.0 for x in np.array_split(np.array(den), 3)]
            r["energia_tercos"] = [round(x, 4) for x in en]
            if max(en) > 0 and en[-1] < 0.3 * max(en):
                r["problemas"].append(("grave", f"a atuação morre no fim: último terço com {en[-1] / max(en):.0%} da energia do melhor"))
    reg = {}
    for nome in list(REGIOES) + ["corpo"]:
        pp = [p for p in pares if nome in p]  # ponto do esqueleto treme com lama/água: só conta se a silhueta mexeu
        if pp:
            ativos = sum(p[nome] > LIMIAR_REGIAO and p.get("dentro", 1) >= LIMIAR_PROPRIO for p in pp)
            reg[nome] = {"ativo": round(ativos / len(pp), 2), "medio": round(float(np.mean([p[nome] for p in pp])), 4)}
    r["regioes"] = reg
    for e in exige or []:
        if e not in reg:
            insuficiente.append(f"{e}: não visível (o contrato pede movimento)")
        elif reg[e]["ativo"] < 0.3:
            r["problemas"].append(("grave", f"{e} parado(s): ativo só em {reg[e]['ativo']:.0%} dos quadros (o contrato pede movimento)"))
    props = [proporcoes(d) for d in dets if d is not None]
    for chave in ("ombros/tronco", "coxa/tronco", "canela/tronco", "preenchimento"):
        serie = [p[chave] for p in props if chave in p]
        if len(serie) >= 4:
            med = float(np.median(serie))
            fora_med = sum(abs(x - med) / med > 0.35 for x in serie) / len(serie)
            saltos = sum(abs(serie[i + 1] - serie[i]) / max(1e-6, serie[i]) > 0.25 for i in range(len(serie) - 1))
            if fora_med > 0.2 or saltos >= 2:
                g = "grave" if fora_med > 0.35 else "media"
                r["problemas"].append((g, f"proporção instável ({chave}): {fora_med:.0%} dos quadros fogem da mediana, {saltos} saltos"))
    trocas = sum(1 for i in range(len(contagem) - 1) if contagem[i] != contagem[i + 1])
    if trocas > max(2, len(contagem) // 4):
        r["problemas"].append(("leve", f"número de pessoas muda {trocas}× no plano (alguém some/aparece?)"))
    for m in insuficiente:
        r["problemas"].append(("media", f"não verificável: {m}"))
    r["insuficiente"] = insuficiente
    r["estado"] = ig.estado_qa(r["problemas"], verificado=not insuficiente)
    if r["estado"] == ig.NAO_VERIFICADO:
        r["nota_atuacao"] = None  # P15: ausência de dado nunca vira nota 100
    else:
        base = min(100.0, 40 + 60 * min(1.0, (r["mov_personagem"] or 0) / 0.04))
        for g, _ in r["problemas"]:
            base -= {"grave": 35, "media": 12, "leve": 4}[g]
        r["nota_atuacao"] = max(0, round(base))
    r["veredito"] = {"reprovado": "reprovado", "nao_verificado": "nao_verificado"}.get(
        r["estado"], "ressalvas" if r["problemas"] else "aprovado")
    return r


def _beats(beats):
    if not beats:
        return []
    from contrato import normalizar_beats
    return normalizar_beats(beats)


def beats_so_pausa(beats):
    bs = _beats(beats)
    return bool(bs) and all(b.get("fase") == "pausa" for b in bs)


def do_contrato(roteiro, plano):
    d = json.load(io.open(roteiro, encoding="utf-8"))
    p = next((x for x in d["planos"] if x["id"] == plano), None)
    if not p:
        sys.exit(f"plano {plano} não está em {roteiro}")
    c = p.get("direcao") or {}
    return c.get("exige") or [], c.get("beats"), max(1, len(c.get("quem") or p.get("quem") or [1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--ini", type=float, default=0.0)
    ap.add_argument("--fim", type=float)
    ap.add_argument("--exige", default="", help="partes que o contrato manda mexer: cabeca,bracos,tronco,pernas,corpo")
    ap.add_argument("--personagens", type=int, default=1)
    ap.add_argument("--roteiro")
    ap.add_argument("--plano")
    ap.add_argument("--json")
    a = ap.parse_args()
    exige, beats, n = [x for x in a.exige.split(",") if x], None, a.personagens
    if a.roteiro and a.plano:
        exige, beats, n = do_contrato(a.roteiro, a.plano)
    r, sujeitos = analisar(a.video, a.ini, a.fim, exige, beats, n)
    nota = f"{r['nota_atuacao']}/100" if r["nota_atuacao"] is not None else "—"
    print(f"{r['estado'].upper()} · nota de atuação {nota} · personagem visível {r['personagem_visivel']:.0%} · "
          f"silhueta se mexe {r['mov_personagem'] or 0:.1%} × cenário {r['mov_cenario'] or 0:.1%}"
          + (f" · terços {r.get('energia_tercos')}" if r.get("energia_tercos") else ""))
    if r.get("beats"):
        print("  beats: " + " · ".join(f"{x['beat']}:{x['fase']} {x['energia'] if x['energia'] is not None else '—'}" for x in r["beats"]))
    print("  partes: " + " · ".join(f"{k} {v['ativo']:.0%}" for k, v in r["regioes"].items()))
    for g, t in r["problemas"]:
        print(f"  [{g}] {t}")
    if a.json:
        json.dump({"resumo": r, "sujeitos": sujeitos}, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    sys.exit({ig.REPROVADO: 2, ig.NAO_VERIFICADO: 3}.get(r["estado"], 0))


if __name__ == "__main__":
    main()
