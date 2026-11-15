"""Ficha de métricas: anota os números de um vídeo publicado e ajusta a pontuação dos padrões usados.

Uso (pergunta o que faltar, um número por vez):
  python metricas.py --video "Cadê o técnico?" --padroes P05,P07,P14,P24,P36,P53 --gancho horario
                     [--plataforma reels] [--momento 48h|7d] [--views 3200 --ret3s 64 --assistido 38 --compart 21 --coment 9]
  python metricas.py --listar        → tabela comparando todos os vídeos anotados

Como pontua (só no momento "7d", para não contar o mesmo vídeo duas vezes):
  3 sinais — retenção em 3 s, % assistido e compartilhamentos por 1.000 views.
  Comparação com a mediana dos vídeos anteriores da mesma plataforma; sem histórico, com referências gerais
  (ret. 3 s ≥ 60%, assistido ≥ 40%, ≥ 5 compart./1.000 views — aproximadas, só para começar).
  Ganhou em ≥ 2 sinais → +1 em cada padrão usado · perdeu em ≥ 2 → −1 · empate → 0.
  Status em padroes.md: pont. ≥ +3 → Confirmado · ≤ −2 → Evitar.
Grava: memoria/metricas.json, colunas pont./status de memoria/padroes.md e uma linha em memoria/historico.md.
"""
import argparse
import datetime
import json
import os
import statistics

MEM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memoria")
ARQ = os.path.join(MEM, "metricas.json")
REF = {"ret3s": 60.0, "assistido": 40.0, "compart_mil": 5.0}
CAMPOS = [("views", "Visualizações"), ("ret3s", "Retenção em 3 s (%)"),
          ("assistido", "% médio assistido"), ("compart", "Compartilhamentos/envios"), ("coment", "Comentários")]


def carregar():
    return json.load(open(ARQ, encoding="utf-8")) if os.path.exists(ARQ) else []


def sinais(r):
    return {"ret3s": r["ret3s"], "assistido": r["assistido"], "compart_mil": 1000 * r["compart"] / max(r["views"], 1)}


def comparar(novo, anteriores):
    base = [sinais(r) for r in anteriores if r["plataforma"] == novo["plataforma"] and r["momento"] == novo["momento"]]
    alvo = {k: statistics.median(b[k] for b in base) for k in REF} if base else REF
    s = sinais(novo)
    res = {k: (1 if s[k] > alvo[k] else -1 if s[k] < alvo[k] else 0) for k in REF}
    ganhou, perdeu = sum(v > 0 for v in res.values()), sum(v < 0 for v in res.values())
    nota = 1 if ganhou >= 2 else -1 if perdeu >= 2 else 0
    return nota, res, alvo, s, bool(base)


def pontuar_padroes(ids, nota, video):
    caminho = os.path.join(MEM, "padroes.md")
    linhas = open(caminho, encoding="utf-8").read().split("\n")
    mudou = []
    for i, ln in enumerate(linhas):
        partes = [p.strip() for p in ln.strip().strip("|").split(" | ")]
        if len(partes) == 6 and partes[0] in ids:
            pid, txt, status, refs, pont, evid = partes
            novo = int(pont.replace("+", "")) + nota
            if novo >= 3:
                status = "Confirmado"
            elif novo <= -2:
                status = "Evitar"
            elif status in ("Confirmado", "Evitar"):
                status = "Teste"
            sinal = f"{nota:+d}" if nota else "0"
            evid = f"{evid} · {video}: {sinal}" if evid and evid != "—" else f"{video}: {sinal}"
            pont_txt = f"{novo:+d}" if novo else "0"
            linhas[i] = f"| {pid} | {txt} | {status} | {refs} | {pont_txt} | {evid} |"
            mudou.append(f"{pid} → {pont_txt} ({status})")
    open(caminho, "w", encoding="utf-8").write("\n".join(linhas))
    return mudou


def listar(dados):
    print("| Vídeo | Data | Plataforma | Momento | Views | Ret. 3 s | Assistido | Compart./1.000 | Coment. | Gancho |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in dados:
        s = sinais(r)
        print(f"| {r['video']} | {r['data']} | {r['plataforma']} | {r['momento']} | {r['views']} | {r['ret3s']:.0f}% | "
              f"{r['assistido']:.0f}% | {s['compart_mil']:.1f} | {r['coment']} | {r.get('gancho') or '—'} |")
    ganchos = {}
    for r in dados:
        if r.get("gancho") and r["momento"] == "7d":
            ganchos.setdefault(r["gancho"], []).append(r["ret3s"])
    if ganchos:
        print("\nRetenção em 3 s por fórmula de gancho (7d):")
        for g, v in sorted(ganchos.items(), key=lambda x: -statistics.mean(x[1])):
            print(f"- {g}: {statistics.mean(v):.0f}% ({len(v)} vídeo(s))")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--padroes", default="", help="ids usados no vídeo, separados por vírgula (ver BRIEFING/historico)")
    ap.add_argument("--gancho", help="fórmula do gancho (horario, pergunta, numero, resultado, contradicao, pov)")
    ap.add_argument("--plataforma", default="reels", choices=["reels", "tiktok", "shorts"])
    ap.add_argument("--momento", default="7d", choices=["48h", "7d"])
    for c, _ in CAMPOS:
        ap.add_argument(f"--{c}", type=float)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--simular", action="store_true", help="mostra o resultado sem gravar nada")
    a = ap.parse_args()

    dados = carregar()
    if a.listar:
        return listar(dados)
    if not a.video:
        a.video = input("Nome do vídeo: ").strip()
    reg = {"video": a.video, "data": datetime.date.today().isoformat(), "plataforma": a.plataforma, "momento": a.momento,
           "padroes": [p.strip().upper() for p in a.padroes.split(",") if p.strip()], "gancho": a.gancho}
    for c, rotulo in CAMPOS:
        v = getattr(a, c)
        reg[c] = v if v is not None else float(input(f"{rotulo}: ").replace("%", "").replace(",", ".").strip())
    reg["views"], reg["compart"], reg["coment"] = int(reg["views"]), int(reg["compart"]), int(reg["coment"])

    nota, res, alvo, s, tem_base = comparar(reg, dados)
    reg["nota"] = nota
    seta = {1: "acima", -1: "abaixo", 0: "igual"}
    origem = "mediana dos seus vídeos anteriores" if tem_base else "referência geral (sem histórico ainda)"
    print(f"# Métricas — {a.video} ({a.plataforma}, {a.momento})\n\nComparado com: {origem}\n")
    for k, nome in [("ret3s", "Retenção 3 s"), ("assistido", "% assistido"), ("compart_mil", "Compart./1.000 views")]:
        print(f"- {nome}: {s[k]:.1f} vs {alvo[k]:.1f} → {seta[res[k]]}")
    print(f"\nResultado do vídeo: {nota:+d}")
    if a.simular:
        print("(simulação — nada gravado)")
        return

    dados.append(reg)
    json.dump(dados, open(ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    mudou = []
    if a.momento == "7d" and reg["padroes"]:
        mudou = pontuar_padroes(set(reg["padroes"]), nota, a.video)
        print("Padrões: " + (", ".join(mudou) or "nenhum id encontrado em padroes.md"))
    elif a.momento == "48h":
        print("48h anotado — a pontuação dos padrões só muda com o número de 7 dias.")
    with open(os.path.join(MEM, "historico.md"), "a", encoding="utf-8") as h:
        h.write(f"\n- Métricas {reg['data']} · {a.video} · {a.plataforma} {a.momento}: {reg['views']} views, ret. 3 s {reg['ret3s']:.0f}%, "
                f"assistido {reg['assistido']:.0f}%, {reg['compart']} compart., {reg['coment']} coment. → {nota:+d}"
                + (f" ({', '.join(mudou)})" if mudou else "") + "\n")


if __name__ == "__main__":
    main()
