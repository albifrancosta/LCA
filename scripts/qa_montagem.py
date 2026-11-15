"""Inspeção do MP4 FINAL (a montagem, não os clipes): congelamento, repetição de quadros, telas divididas por lado,
cobertura do clipe no plano, duração efetiva e trechos de risco para revisão densa. Local, grátis, sem rede.

Por que existe: na MinhaMarca "dois mundos" o lado direito da tela dividida das 18h (c10d) congelou ~1 s no fim — o clipe era
mais curto que o plano e o Remotion segurou o último quadro. O inspetor do filme media movimento do quadro INTEIRO
(o lado esquerdo mexia) e passou. Aqui cada lado é medido separado e o fim de cada plano é olhado de perto.

O que mede, por plano (e por região em composições divididas):
  congelamento   corrida de quadros quase idênticos (diferença média < LIMIAR) ≥ MIN_CONGELADO_S, com posição
                 início | meio | fim do plano
  fim_preenchido congelamento que encosta no fim do plano E o clipe montado não cobre o plano nem desacelerado (ou a
                 corrida cobre exatamente a sobra) → "fim de clipe preenchido com Freeze" (grave — corrige na montagem)
  pausa          congelamento coberto por `direcao.pausa_intencional: [[ini, fim], …]` (s, relativos ao plano) ou plano
                 que não é de atuação (tela/insert estático) → não é defeito
  repeticao      quadros duplicados periódicos (desaceleração tipo minRate) → aviso; sequência que volta a um quadro
                 já visto ≥ 0,4 s antes depois de mudar (loop/ping-pong) → média
  cobertura      duração do clipe ÷ duração do plano: < DESACEL_MAX → vai congelar; < 1 → vai desacelerar
  duracao        duração efetiva do MP4 × fim do manifesto × alvo do projeto.json
Saída: entrega/inspecao-montagem.json/.md, folhas densas em entrega/inspecao/montagem-<id>.jpg só nos trechos de risco.

Uso:
  python qa_montagem.py filme <projeto> entrega/filme.mp4 [--planos c10,c06c]
  python qa_montagem.py comparar <projeto> antes.mp4 depois.mp4 --plano c10   → defeito antes × depois da correção
"""
import argparse
import io
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

LIMIAR = 0.35           # diferença média (0–255, imagem 160 px cinza) abaixo disso = mesmo quadro
MIN_CONGELADO_S = 0.30  # corrida mínima para contar como congelamento
BORDA_FIM_S = 0.12      # corrida que termina até aqui antes do fim do plano "encosta no fim"
DESACEL_MAX = 0.75      # Filme.tsx Video minRate: abaixo disso o Remotion segura o último quadro
REGIOES = {"inteiro": (0.0, 1.0), "esq": (0.0, 0.5), "dir": (0.5, 1.0)}


def ler_quadros(video, ini=0.0, fim=None, largura=160):
    """([(t, cinza_pequeno)], fps) do trecho. Lê em sequência (seek em mp4 é impreciso por quadro)."""
    import cv2
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if ini > 0.6:
        cap.set(cv2.CAP_PROP_POS_MSEC, (ini - 0.5) * 1000)
    out = []
    while True:
        ok, q = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if t + 1e-6 < ini:
            continue
        if fim is not None and t >= fim:
            break
        h, w = q.shape[:2]
        g = cv2.cvtColor(cv2.resize(q, (largura, max(2, int(h * largura / w)))), cv2.COLOR_BGR2GRAY)
        out.append((t, g))
    cap.release()
    return out, fps


def recorte(g, regiao):
    a, b = REGIOES.get(regiao, (0.0, 1.0)) if isinstance(regiao, str) else regiao
    w = g.shape[1]
    return g[:, int(a * w):max(int(a * w) + 1, int(b * w))]


def diferencas(quadros, regiao="inteiro"):
    import numpy as np
    return [(t1, float(np.mean(np.abs(recorte(a, regiao).astype("int16") - recorte(b, regiao).astype("int16")))))
            for (_, a), (t1, b) in zip(quadros, quadros[1:])]


def corridas(ds, fps, limiar=LIMIAR, minimo=MIN_CONGELADO_S):
    """Corridas de quadros parados: [(ini, fim, n_quadros)]."""
    out, ini, n = [], None, 0
    passo = 1.0 / fps
    for t, d in ds:
        if d < limiar:
            if ini is None:
                ini, n = t - passo, 1
            n += 1
        else:
            if ini is not None and (n - 1) * passo >= minimo:
                out.append((round(ini, 3), round(t - passo, 3), n))
            ini, n = None, 0
    if ini is not None and (n - 1) * passo >= minimo:
        out.append((round(ini, 3), round(ds[-1][0], 3), n))
    return out


def duplicados_periodicos(ds, limiar=LIMIAR):
    """Fração de quadros isolados repetidos (1 quadro igual entre quadros que mudam): sinal de desaceleração."""
    if len(ds) < 6:
        return 0.0
    iso = sum(1 for i in range(1, len(ds) - 1) if ds[i][1] < limiar and ds[i - 1][1] >= limiar and ds[i + 1][1] >= limiar)
    return iso / len(ds)


def volta_ao_passado(quadros, regiao, fps, janela_s=0.4, limiar=LIMIAR):
    """Quadro que repete um quadro de ≥ janela_s atrás, depois de ter mudado no meio (loop/ping-pong). [(t, t_original)]."""
    import numpy as np
    k = max(2, int(janela_s * fps))
    passo = max(1, int(fps // 6))
    peq = [(t, recorte(g, regiao)[::2, ::2].astype("int16")) for t, g in quadros]
    out = []
    for i in range(k, len(peq), passo):
        t, g = peq[i]
        for j in range(0, i - k, passo):
            if float(np.mean(np.abs(g - peq[j][1]))) < limiar:
                meio = peq[(i + j) // 2][1]
                if float(np.mean(np.abs(g - meio))) > 6 * limiar:
                    out.append((round(t, 2), round(peq[j][0], 2)))
                break
    return out


def classificar(run, ini_p, fim_p, pausas, animado, dur_clipe=None):
    a, b, _ = run
    dur_p = fim_p - ini_p
    rel = (a - ini_p) / dur_p if dur_p else 0
    pos = "fim" if b >= fim_p - BORDA_FIM_S - 1.0 / 30 else ("inicio" if rel < 0.15 else "meio")
    if any(ini_p + p0 - 0.05 <= a and b <= ini_p + p1 + 0.05 for p0, p1 in pausas or []):
        return pos, "pausa_intencional", None
    if not animado:
        return pos, "estatico_permitido", None
    if pos == "fim" and dur_clipe is not None and (dur_clipe < dur_p - 0.05 or abs((b - a) - (dur_p - dur_clipe)) < 0.2):
        return pos, "fim_preenchido", "grave"  # parado no fim + clipe mais curto que o plano = último quadro segurado
    return pos, "congelamento", ("grave" if (b - a) >= 0.6 else "media")


def regioes_do_plano(item):
    """[(id, regiao, midia)] — composição dividida mede cada lado; sub com `regiao` explícita ([a, b] em fração da
    largura ou 'esq'/'dir') manda; 2 subs sem regiao = esquerda/direita na ordem."""
    subs = [s for s in item.get("inclui") or [] if isinstance(s, dict)]
    if len(subs) >= 2:
        return [(s["id"], s.get("regiao") or s.get("lado") or ("esq" if k == 0 else "dir"), s.get("midia") or {}) for k, s in enumerate(subs)]
    if len(subs) == 1:
        return [(subs[0]["id"], subs[0].get("regiao") or "inteiro", subs[0].get("midia") or {})]
    return [(item["id"], "inteiro", item.get("midia") or {})]


def _dur_midia(base, md):
    if not md.get("arquivo"):
        return None
    for c in (os.path.join(base, md["arquivo"]), os.path.join(base, "remotion", "public", md["arquivo"])):
        s = ig.sonda(c) if os.path.isfile(c) else None
        if s:
            return s["duracao"]
    return None


def analisar_plano(quadros, fps, item, plano, base):
    """Mede um plano do manifesto (todas as suas regiões). {"id", "regioes", "problemas", "avisos", "risco", "estado"}."""
    ini_p, fim_p = float(item["inicio"]), float(item["fim"])
    qs = [(t, g) for t, g in quadros if ini_p - 1e-6 <= t < fim_p]
    r = {"id": item["id"], "de": ini_p, "ate": fim_p, "regioes": [], "problemas": [], "avisos": [], "risco": []}
    if len(qs) < 3:
        r["avisos"].append("trecho curto demais para medir")
        r["estado"] = ig.NAO_VERIFICADO
        return r
    for sid, reg, md in regioes_do_plano(item):
        pl = plano.get(sid) or plano.get(item["id"]) or {}
        c = pl.get("direcao") or {}
        animado = c.get("modo") in ig.MODOS_ANIMADOS
        dur_clipe = _dur_midia(base, md)
        ds = diferencas(qs, reg)
        rr = {"id": sid, "regiao": reg if isinstance(reg, str) else list(reg), "dur_clipe": dur_clipe, "congelamentos": []}
        if dur_clipe and animado:
            cob = dur_clipe / (fim_p - ini_p)
            rr["cobertura"] = round(cob, 3)
            if cob < DESACEL_MAX - 0.01:  # previsão (o sub pode ocupar só parte do plano): risco; o que reprova é o congelamento MEDIDO
                r["avisos"].append(f"{sid} ({reg}): clipe {dur_clipe:.2f}s num plano de {fim_p - ini_p:.2f}s — nem desacelerando a "
                                   f"{DESACEL_MAX} cobre o plano inteiro (conferir o fim)")
                r["risco"].append((max(ini_p, ini_p + dur_clipe / DESACEL_MAX - 0.3), fim_p))
            elif cob < 0.999:
                r["avisos"].append(f"{sid} ({reg}): clipe desacelerado a {cob:.2f}× para cobrir o plano")
        for run in corridas(ds, fps):
            pos, tipo, grav = classificar(run, ini_p, fim_p, c.get("pausa_intencional"), animado, dur_clipe)
            rr["congelamentos"].append({"de": run[0], "ate": run[1], "s": round(run[1] - run[0], 2), "posicao": pos, "tipo": tipo})
            if grav:
                txt = {"fim_preenchido": "fim de clipe preenchido com Freeze", "congelamento": "congelamento não intencional"}[tipo]
                r["problemas"].append((grav, f"{sid} ({reg}): {txt} {run[0]:.2f}–{run[1]:.2f}s ({run[1] - run[0]:.2f}s, {pos} do plano)"))
                r["risco"].append((max(ini_p, run[0] - 0.4), min(fim_p, run[1] + 0.2)))
        dup = duplicados_periodicos(ds)
        rr["duplicados_periodicos"] = round(dup, 3)
        if animado and dup > 0.12:
            r["avisos"].append(f"{sid} ({reg}): {dup:.0%} de quadros duplicados (desaceleração visível)")
        voltas = volta_ao_passado(qs, reg, fps) if animado else []
        if voltas:
            rr["voltas"] = voltas[:5]
            r["problemas"].append(("media", f"{sid} ({reg}): repetição de quadros (volta ao quadro de {voltas[0][1]:.2f}s em {voltas[0][0]:.2f}s)"))
            r["risco"].append((max(ini_p, voltas[0][1] - 0.2), min(fim_p, voltas[0][0] + 0.2)))
        r["regioes"].append(rr)
    if len(r["regioes"]) > 1:
        r["risco"].append((ini_p, fim_p))  # tela dividida é sempre trecho de risco (revisão densa por lado)
    r["risco"].append((max(ini_p, fim_p - 0.6), fim_p))  # fim do plano: onde o Freeze aparece
    r["estado"] = ig.estado_qa(r["problemas"], verificado=True)
    return r


def analisar_filme(base, video, planos=None, cfg_duracao=None, folhas=True, d=None):
    from inspetor import folha, manifesto
    _, itens, _, _ = manifesto(base)
    if d is None:
        d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    plano = {p["id"]: p for p in d["planos"]}
    alvo = set(planos.split(",")) if planos else None
    quadros, fps = ler_quadros(video)
    res = []
    for it in itens:
        if alvo and it["id"] not in alvo and not any((s if isinstance(s, str) else s.get("id")) in alvo for s in it.get("inclui") or []):
            continue
        r = analisar_plano(quadros, fps, it, plano, base)
        if folhas and r["problemas"]:  # revisão densa SÓ nos trechos de risco
            a, b = min(x[0] for x in r["risco"]), max(x[1] for x in r["risco"])
            r["folha"] = folha(video, os.path.join(base, "entrega", "inspecao", f"montagem-{it['id']}.jpg"), n=12, ini=a, fim=b)
        res.append(r)
    s = ig.sonda(video) or {}
    dur = {"mp4": round(s.get("duracao", 0), 3), "manifesto": round(max((float(i["fim"]) for i in itens), default=0), 3)}
    probs_dur = []
    if abs(dur["mp4"] - dur["manifesto"]) > 0.2:
        probs_dur.append(("grave", f"MP4 tem {dur['mp4']:.2f}s, manifesto termina em {dur['manifesto']:.2f}s"))
    if cfg_duracao and cfg_duracao.get("segundos"):
        alvo_s = float(cfg_duracao["segundos"])
        desvio = (dur["mp4"] - alvo_s) / alvo_s * 100
        dur.update(alvo=alvo_s, desvio_pct=round(desvio, 2))
        if abs(desvio) > float(cfg_duracao.get("tolerancia_pct") or 5):
            probs_dur.append(("media", f"duração {dur['mp4']:.1f}s fora da tolerância do alvo {alvo_s:.0f}s ({desvio:+.1f} %)"))
    return res, dur, probs_dur


def comparar(base, antes, depois, plano_id):
    """Mesmo plano medido nos dois renders — prova de que a correção resolveu (ou não) no arquivo final."""
    from inspetor import manifesto
    _, itens, _, _ = manifesto(base)
    it = next((i for i in itens if i["id"] == plano_id), None)
    if not it:
        sys.exit(f"{plano_id} não está no manifesto")
    d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    plano = {p["id"]: p for p in d["planos"]}
    out = {}
    for nome, v in (("antes", antes), ("depois", depois)):
        qs, fps = ler_quadros(v, float(it["inicio"]) - 0.1, float(it["fim"]) + 0.1)
        out[nome] = analisar_plano(qs, fps, it, plano, base)
    graves = lambda r: [p for p in r["problemas"] if p[0] == "grave"]  # noqa: E731
    out["resolvido"] = bool(graves(out["antes"])) and not graves(out["depois"])
    return out


def gravar(base, res, dur, probs_dur):
    grave = any(p[0] == "grave" for r in res for p in r["problemas"]) or any(p[0] == "grave" for p in probs_dur)
    rel = {"itens": res, "duracao": dur, "problemas_duracao": probs_dur, "estado": ig.REPROVADO if grave else ig.APROVADO}
    ig.gravar_json_atomico(os.path.join(base, "entrega", "inspecao-montagem.json"), rel)
    linhas = ["# Inspeção da montagem (MP4 final)", "", f"Duração: {json.dumps(dur, ensure_ascii=False)}", ""]
    linhas += [f"- ❗ {t}" for _, t in probs_dur]
    for r in res:
        if r["problemas"] or r["avisos"]:
            linhas.append(f"- **{r['id']}** ({r['de']:.2f}–{r['ate']:.2f}s): " + " · ".join([t for _, t in r["problemas"]] + r["avisos"]))
    io.open(os.path.join(base, "entrega", "inspecao-montagem.md"), "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    return rel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["filme", "comparar"])
    ap.add_argument("projeto")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--planos")
    ap.add_argument("--plano")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    vs = [v if os.path.isabs(v) else os.path.join(base, v) for v in a.videos]
    if a.acao == "comparar":
        if len(vs) != 2 or not a.plano:
            sys.exit("comparar precisa de antes.mp4 depois.mp4 --plano <id>")
        out = comparar(base, vs[0], vs[1], a.plano)
        print(json.dumps({k: (v if k == "resolvido" else {"problemas": v["problemas"], "regioes": v["regioes"]}) for k, v in out.items()},
                         ensure_ascii=False, indent=1))
        sys.exit(0 if out["resolvido"] else 2)
    import projeto as pj
    res, dur, probs = analisar_filme(base, vs[0], a.planos, pj.carregar(base)["duracao"])
    rel = gravar(base, res, dur, probs)
    print(f"montagem: {len(res)} planos medidos, {sum(1 for r in res if r['problemas'])} com problema · duração {dur} → entrega/inspecao-montagem.md")
    for r in res:
        for g, t in r["problemas"]:
            print(f"  {'❌' if g == 'grave' else '⚠️'} {r['id']}: {t}")
    for g, t in probs:
        print(f"  {'❌' if g == 'grave' else '⚠️'} duração: {t}")
    sys.exit(2 if rel["estado"] == ig.REPROVADO else 0)


if __name__ == "__main__":
    main()
