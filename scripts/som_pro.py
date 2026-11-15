"""Som profissional: aplica as regras de sound design de filmes de lançamento aos efeitos e à trilha, antes da mixagem.

Uso (na pasta do projeto):
  python som_pro.py --sfx sfx.json --trilha assets/trilha.wav --revelacao 25.7 --duracao 58 \
                    [--budget 10] [--sem-riser] [-o assets/som]
  → assets/som/sfx-pro.json, assets/som/trilha-pro.wav, assets/som/som-relatorio.txt
  depois: python mixar_comercial.py ... --sfx assets/som/sfx-pro.json --trilha assets/som/trilha-pro.wav

Regras (o bom som quase não aparece; todo som tem uma causa visível; a maior parte do movimento NÃO tem som):
  1. Revelação (a virada / o produto): um "riser" de 1,5 s que termina NELA e um "hit" (golpe) nela.
     A música desce ~10 dB nos 0,45 s antes do golpe e volta no golpe. Só 1 riser por vídeo.
  2. Um som por gesto: sons a menos de 0,12 s um do outro → fica o mais importante.
  3. Silêncio antes do golpe: nada (além do riser) na janela do riser; nada pequeno até 0,25 s depois do golpe.
  4. Espaço mínimo: whoosh a cada ≥ 2 s · ding a cada ≥ 1 s · pop/clique a cada ≥ 0,18 s.
  5. Orçamento: no máximo --budget gestos a cada 10 s (tick não conta); corta primeiro os pequenos.
  Para forçar um som a ficar: "manter": true no sfx.json.
Nada para instalar: efeitos sintetizados de mixar_comercial.py (pop, clique, whoosh, ding, vibrar, telefone, carimbo,
riser, hit, tick) — um kit só, mesma "família" de som.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batida import analisar  # noqa: E402

PRIORIDADE = {"hit": 100, "riser": 95, "telefone": 70, "vibrar": 65, "carimbo": 60, "ding": 50, "whoosh": 40, "pop": 20, "clique": 15, "tick": 10}
PEQUENOS = {"pop", "clique", "tick"}
ESPACO = {"whoosh": 2.0, "ding": 1.0, "pop": 0.18, "clique": 0.18}
RISER = 1.5
SR = 48000


def regras(cues, revelacao, budget, com_riser):
    rel = []  # relatório: (tempo, som, motivo)
    cues = [dict(c, manter=bool(c.get("manter"))) for c in cues if c.get("som") not in ("hit", "riser")]
    if revelacao is not None:
        cues.append({"som": "hit", "inicio": round(revelacao, 3), "volume": 0.7, "manter": True})
        if com_riser:
            cues.append({"som": "riser", "inicio": round(revelacao - RISER, 3), "volume": 0.45, "manter": True})
    cues.sort(key=lambda c: c["inicio"])

    def pri(c):
        return PRIORIDADE.get(c["som"], 30) + (1000 if c["manter"] else 0)

    vivos = []
    for c in cues:  # 2. um som por gesto
        conflito = next((v for v in vivos if abs(v["inicio"] - c["inicio"]) < 0.12 and {v["som"], c["som"]} != {"hit", "riser"}), None)
        if conflito is None:
            vivos.append(c)
        elif pri(c) > pri(conflito):
            rel.append((conflito["inicio"], conflito["som"], f"mesmo gesto que {c['som']}"))
            vivos[vivos.index(conflito)] = c
        else:
            rel.append((c["inicio"], c["som"], f"mesmo gesto que {conflito['som']}"))
    cues = vivos

    if revelacao is not None:  # 3. silêncio antes do golpe / nada pequeno logo depois
        ini = revelacao - (RISER if com_riser else 0.6)
        fica = []
        for c in cues:
            if not c["manter"] and ini <= c["inicio"] < revelacao:
                rel.append((c["inicio"], c["som"], "dentro da subida antes da revelação (silêncio antes do golpe)"))
            elif not c["manter"] and c["som"] in PEQUENOS and revelacao <= c["inicio"] < revelacao + 0.25:
                rel.append((c["inicio"], c["som"], "pequeno logo depois do golpe"))
            else:
                fica.append(c)
        cues = fica

    fica, ultimo = [], {}
    for c in cues:  # 4. espaço mínimo por tipo
        gap = ESPACO.get(c["som"])
        if gap and not c["manter"] and c["som"] in ultimo and c["inicio"] - ultimo[c["som"]] < gap:
            rel.append((c["inicio"], c["som"], f"menos de {gap} s depois do anterior igual"))
            continue
        ultimo[c["som"]] = c["inicio"]
        fica.append(c)
    cues = fica

    while True:  # 5. orçamento por 10 s
        estouro = None
        for c in cues:
            janela = [x for x in cues if c["inicio"] <= x["inicio"] < c["inicio"] + 10 and x["som"] != "tick"]
            if len(janela) > budget:
                estouro = min((x for x in janela if not x["manter"]), key=pri, default=None)
                break
        if estouro is None:
            break
        rel.append((estouro["inicio"], estouro["som"], f"acima do orçamento de {budget} sons por 10 s"))
        cues.remove(estouro)

    for c in cues:  # pequenos ficam discretos
        if c["som"] in PEQUENOS and not c["manter"]:
            c["volume"] = min(c.get("volume", 0.4), 0.35)
    return cues, sorted(rel)


def carregar(arq, duracao):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", arq, "-t", str(duracao), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def degrau(trilha, revelacao, desce_db=10.0):
    """Música desce antes do golpe (0,45 s, rampa de 0,15 s) e volta NO golpe (rampa de 0,08 s)."""
    t = np.arange(len(trilha)) / SR
    a, b = revelacao - 0.45, revelacao
    g = np.ones_like(t)
    baixo = 10 ** (-desce_db / 20)
    desce = (t >= a) & (t < a + 0.15)
    g[desce] = 1 - (1 - baixo) * (t[desce] - a) / 0.15
    g[(t >= a + 0.15) & (t < b)] = baixo
    volta = (t >= b) & (t < b + 0.08)
    g[volta] = baixo + (1 - baixo) * (t[volta] - b) / 0.08
    return trilha * g[:, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx", required=True)
    ap.add_argument("--trilha", help="música de fundo (sem ela, só os efeitos são arrumados)")
    ap.add_argument("--revelacao", type=float, help="segundo da virada/revelação (riser + golpe + degrau da música)")
    ap.add_argument("--duracao", type=float, required=True)
    ap.add_argument("--budget", type=int, default=10)
    ap.add_argument("--sem-riser", action="store_true")
    ap.add_argument("-o", "--saida", default="assets/som")
    a = ap.parse_args()

    os.makedirs(a.saida, exist_ok=True)
    originais = json.load(open(a.sfx, encoding="utf-8"))
    cues, rel = regras(originais, a.revelacao, a.budget, not a.sem_riser)
    json.dump([{k: v for k, v in c.items() if k != "manter" or v} for c in cues],
              open(os.path.join(a.saida, "sfx-pro.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    linhas = [f"Som profissional — {len(originais)} efeitos pedidos → {len(cues)} ficaram ({len(cues) / a.duracao * 10:.1f} por 10 s)"]
    if a.revelacao is not None:
        linhas.append(f"Revelação em {a.revelacao:.2f} s: " + ("riser 1,5 s + " if not a.sem_riser else "") + "golpe + música desce 10 dB por 0,45 s antes")
    if a.trilha:
        tr = carregar(a.trilha, a.duracao)
        if a.revelacao is not None:
            tr = degrau(tr, a.revelacao)
        wavfile.write(os.path.join(a.saida, "trilha-pro.wav"), SR, np.clip(tr, -1, 1).astype(np.float32))
        b = analisar(resample_poly(tr.mean(1), 147, 320).astype(np.float32))
        linhas.append(f"Trilha: {b['bpm']} BPM · drop {b['drop'] if b['drop'] is not None else 'nenhum claro'}")
        if a.revelacao is not None and b["batidas"]:
            bt = np.array(b["batidas"])
            m = bt[np.argmin(np.abs(bt - a.revelacao))]
            linhas.append(f"  revelação × batida mais próxima: {a.revelacao - m:+.2f} s " + ("✅ no tempo" if abs(a.revelacao - m) <= 0.12 else "⚠️ use batida.py --drop-em para alinhar"))
    linhas.append("\nCortados (motivo):")
    linhas += [f"  {t:6.2f} s  {s:<9} {m}" for t, s, m in rel] or ["  nenhum"]
    linhas.append("\nFicaram:")
    linhas += [f"  {c['inicio']:6.2f} s  {c['som']:<9} vol {c.get('volume', 0.5):.2f}" + ("  (manter)" if c["manter"] else "") for c in cues]
    txt = "\n".join(linhas)
    open(os.path.join(a.saida, "som-relatorio.txt"), "w", encoding="utf-8").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
