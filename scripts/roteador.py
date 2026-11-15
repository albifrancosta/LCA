"""Roteador de custos: escolhe o modelo com MENOR CUSTO ESPERADO POR RESULTADO APROVADO para cada cena.

Uso:
  python roteador.py video --duracao 5 --cena personagem [--ultimo-quadro] [--perfil economico|equilibrado|premium] [--orcamento 0.5]
  python roteador.py video --duracao 8 --cena rosto --capacidades lip_sync,audio   → só modelos de lip-sync que cobrem 8 s
  python roteador.py video --cena interface          → manda para motion graphics (US$ 0) e não paga vídeo
  python roteador.py --resultado <modelo> <tipo_cena> aprovado|reprovado [--custo 0.23]   → aprende com o resultado
  python roteador.py --historico                       → taxa de aprovação por modelo e tipo de cena

Como decide (registrado em memoria/roteador-log.jsonl):
  1. Cenas de texto, tela, interface, gráfico, ícone, logo, transição → **motion em código, US$ 0** (nunca vídeo pago).
  2. Filtra modelos do catálogo (`catalogo.py`) com preço oficial e os recursos pedidos (imagem→vídeo, último quadro, lip-sync,
     duração). Modelo que não COBRE a duração pedida sai da lista; preço desconhecido (ex.: tokens sem custo_5s) nunca vira US$ 0.
  3. custo esperado = preço da duração ÷ taxa de aprovação  (taxa = histórico real do modelo naquele tipo de cena;
     sem histórico, estimativa pela qualidade: q1 50 %, q2 70 %, q3 85 %, com peso de 2 tentativas).
  4. Perfil: **econômico** (padrão) = menor custo esperado com qualidade ≥ 2 · **equilibrado** = melhor custo ÷ qualidade ·
     **premium** = maior qualidade dentro do orçamento. Nunca passa do `--orcamento`.
  Cenas de personagem/ação complexa sobem o piso de qualidade para 3 em todos os perfis (motion control: piso 2); sem modelo
  acima do piso o roteador devolve modelo=None e motivo "sem_modelo_compativel" (nunca rebaixa calado).
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MEM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memoria")
CAT = os.path.join(MEM, "catalogo-modelos.json")
HIST = os.path.join(MEM, "modelos-historico.json")
LOG = os.path.join(MEM, "roteador-log.jsonl")
MOTION = {"texto", "tela", "interface", "grafico", "icone", "logo", "transicao", "numero", "lista", "assinatura"}
COMPLEXAS = {"personagem", "acao", "rosto", "multidao", "maos"}
TAXA_BASE = {1: 0.5, 2: 0.7, 3: 0.85}


def carregar(arq, padrao):
    return json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else padrao


def taxa(modelo, cena, q, hist):
    h = hist.get(modelo, {}).get(cena, {})
    a, r = h.get("aprovados", 0), h.get("reprovados", 0)
    base = TAXA_BASE.get(q, 0.6)
    return (a + 2 * base) / (a + r + 2)  # média com 2 tentativas "imaginárias" na taxa-base


def duracoes_do(m):
    """Durações aceitas pelo modelo (lista ordenada) ou None quando o catálogo não restringe."""
    durs = (m.get("recursos") or {}).get("duracoes") or []
    nums = sorted(float(x) for x in durs if str(x).replace(".", "", 1).isdigit())
    return nums or None


def duracao_real(m, dur):
    """Menor duração aceita que COBRE o pedido; None se o modelo não entrega essa duração (nunca encurta calado)."""
    nums = duracoes_do(m)
    if not nums:
        return float(dur)
    return next((d for d in nums if d >= float(dur) - 1e-6), None)


def preco_duracao(m, dur):
    """(preço US$ | None, duração cobrada | None). Preço desconhecido é None — NUNCA US$ 0 (P36/P19).
    Duração None = o modelo não cobre a duração pedida (P34): divida o plano ou troque de modelo."""
    real = duracao_real(m, dur)
    if real is None:
        return None, None
    pu = m.get("preco_unidade")
    u = (m.get("unidade") or "").lower()
    if "token" in u:  # preço por tokens: só vale a estimativa por 5 s anotada no catálogo
        c5 = m.get("custo_5s")
        return (c5 * real / 5 if c5 else None), real
    if pu is None:
        return None, real
    if u.startswith("second"):
        return pu * real, real
    if u.startswith("minute"):
        return pu * real / 60, real
    if u.startswith("video") or u in ("", "per video", "unit", "units"):
        return pu, real  # por vídeo
    return None, real  # unidade desconhecida: não adivinhar


def preco_conhecido(m, dur):
    """Igual a preco_duracao, mas levanta PrecoDesconhecido (para quem vai gastar)."""
    from integridade import PrecoDesconhecido
    preco, real = preco_duracao(m, dur)
    if real is None:
        raise PrecoDesconhecido(f"{m.get('id')} não entrega {float(dur):g} s (aceita {duracoes_do(m)}) — divida o plano ou troque de modelo")
    if preco is None:
        raise PrecoDesconhecido(f"{m.get('id')}: preço desconhecido no catálogo (unidade '{m.get('unidade')}') — atualize catalogo.py antes de gastar")
    return preco, real


def tem_capacidade(m, cap):
    """Capacidade pedida → como o catálogo mostra que o modelo a tem."""
    rec = m.get("recursos") or {}
    params = rec.get("parametros") or []
    if cap in ("lip_sync", "lipsync"):
        return m.get("tipo") == "lipsync"
    if cap in ("ultimo_quadro", "primeiro_ultimo_quadro", "first_last"):
        return bool(rec.get("primeiro_ultimo_quadro"))
    if cap == "i2v":
        return bool(rec.get("i2v"))
    if cap == "audio":
        return "audio_url" in params
    if cap == "identidade":
        return "elements" in params
    return bool(rec.get(cap)) or cap in params  # capacidade desconhecida só passa se o catálogo a declarar


def _log(dec, tipo, cena, perfil):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(dec, data=datetime.date.today().isoformat(), tipo=tipo, cena=cena, perfil=perfil), ensure_ascii=False) + "\n")


SEM_MODELO = "sem_modelo_compativel"


def _sem_modelo(detalhe, registrar, tipo, cena, perfil, cands=()):
    dec = {"modelo": None, "custo": None, "motivo": SEM_MODELO, "detalhe": detalhe}
    if registrar:
        _log(dec, tipo, cena, perfil)
    return dec, list(cands)


def escolher(tipo="video", duracao=5, cena="geral", ultimo_quadro=False, perfil="economico", orcamento=None, registrar=True, modo=None,
             capacidades=None):
    """capacidades: conjunto exigido, ex. {"i2v", "ultimo_quadro", "lip_sync", "audio", "identidade"}.
    Sem modelo que cubra duração + capacidades + piso de qualidade → modelo=None, motivo="sem_modelo_compativel" (nunca rebaixa)."""
    cena = (cena or "geral").lower()
    caps = set(capacidades or ())
    if ultimo_quadro:
        caps.add("ultimo_quadro")
    lip = bool(caps & {"lip_sync", "lipsync"})
    if tipo == "video" and not lip and "i2v" not in caps and capacidades is None:
        caps.add("i2v")  # comportamento antigo: vídeo = imagem → vídeo
    if tipo == "video" and cena in MOTION and not lip:
        dec = {"modelo": "local/remotion-motion", "custo": 0.0, "motivo": f"cena de {cena}: motion graphics em código entrega igual por US$ 0 — não pagar vídeo"}
        if registrar:
            _log(dec, tipo, cena, perfil)
        return dec, []
    tipo_cat = "lipsync" if lip else tipo
    temporal = tipo_cat in ("video", "motion", "lipsync")
    cat = carregar(CAT, {"modelos": []})["modelos"]
    hist = carregar(HIST, {})
    cands, fora = [], {"duração": 0, "preço desconhecido": 0, "capacidade": 0}
    for m in cat:
        if m.get("tipo") != tipo_cat or m.get("provedor") == "local":
            continue
        rec = m.get("recursos") or {}
        if any(not tem_capacidade(m, c) for c in caps):
            fora["capacidade"] += 1
            continue
        if tipo == "motion" and modo and modo not in rec.get("modos", []):
            continue
        preco, dur_real = preco_duracao(m, duracao) if temporal else (m.get("preco_unidade"), None)
        if temporal and dur_real is None:
            fora["duração"] += 1  # P34: não cobre a duração pedida → fora (nada de 15 s virar 10 s calado)
            continue
        if preco is None:
            fora["preço desconhecido"] += 1  # P36: preço desconhecido não concorre como "grátis"
            continue
        q = m.get("qualidade_base") or 1
        tx = taxa(m["id"], cena, q, hist)
        cands.append({"modelo": m["id"], "q": q, "preco": round(preco, 4), "duracao": dur_real, "taxa": round(tx, 2),
                      "esperado": round(preco / tx, 4), "nota": m.get("nota", ""), "estimado": "token" in (m.get("unidade") or "").lower()})
    descarte = ", ".join(f"{n} por {k}" for k, n in fora.items() if n)
    req_txt = f"{tipo_cat}, {float(duracao):g} s" + (f", capacidades {sorted(caps)}" if caps else "")
    if not cands:
        return _sem_modelo(f"nenhum modelo do catálogo atende a {req_txt}" + (f" (descartados: {descarte})" if descarte else ""),
                           registrar, tipo, cena, perfil)
    # Plano 47: Seedance Lite (q2) no perfil econômico devolveu 2 de 10 clipes só com câmera → atuação pede q3 sempre.
    # Motion control copia o movimento de um vídeo de referência (não inventa atuação): piso 2.
    piso = 3 if (cena in COMPLEXAS and tipo != "motion") else 2
    dentro = [c for c in cands if orcamento is None or c["preco"] <= orcamento]
    if not dentro:
        return {"modelo": None, "custo": None, "motivo": f"nada cabe no orçamento de US$ {orcamento}"}, sorted(cands, key=lambda c: c["esperado"])
    aptos = [c for c in dentro if c["q"] >= piso]  # P35: nunca recorre a modelo abaixo do piso
    if not aptos:
        return _sem_modelo(f"nenhum modelo com qualidade ≥ {piso} para cena '{cena}' ({req_txt}"
                           + (f", até US$ {orcamento}" if orcamento is not None else "")
                           + ") — mude o plano ou aprove outro modelo explicitamente com --modelo",
                           registrar, tipo, cena, perfil, sorted(cands, key=lambda c: c["esperado"]))
    if perfil == "premium":
        el = sorted(aptos, key=lambda c: (-c["q"], c["esperado"]))
    elif perfil == "equilibrado":
        el = sorted(aptos, key=lambda c: c["esperado"] / c["q"])
    else:
        el = sorted(aptos, key=lambda c: c["esperado"])
    e = el[0]
    if tipo == "video":
        req = f"{'lip-sync' if lip else 'imagem→vídeo'}, {e['duracao']:g} s" + (", com último quadro" if "ultimo_quadro" in caps else "")
    elif tipo == "motion":
        req = f"motion control ({modo or 'qualquer modo'}), {e['duracao']:g} s"
    else:
        req = tipo
    aviso = " · ATENÇÃO: preço por tokens, ESTIMADO pela fórmula de resolução×fps×duração — confirme no painel do fal" if e.get("estimado") else ""
    motivo = (f"{e['modelo']} — menor custo esperado por cena aprovada (US$ {e['preco']:.3f} ÷ {e['taxa']:.0%} de aprovação ≈ US$ {e['esperado']:.3f}) "
              f"entre os modelos com {req}, qualidade ≥ {piso}, perfil {perfil}{aviso}")
    dec = {"modelo": e["modelo"], "custo": e["preco"], "esperado": e["esperado"], "duracao": e["duracao"], "motivo": motivo}
    if registrar:
        _log(dec, tipo, cena, perfil)
    return dec, sorted(cands, key=lambda c: c["esperado"])


def resultado(modelo, cena, status, custo=None):
    hist = carregar(HIST, {})
    h = hist.setdefault(modelo, {}).setdefault(cena, {"aprovados": 0, "reprovados": 0, "custo_real": 0.0})
    h["aprovados" if status.startswith("aprov") else "reprovados"] += 1
    if custo:
        h["custo_real"] = round(h.get("custo_real", 0) + custo, 4)
    json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{modelo} · {cena}: {h['aprovados']} aprovados / {h['reprovados']} reprovados")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tipo", nargs="?", default="video", choices=["video", "motion", "imagem", "musica", "voz"])
    ap.add_argument("--modo", choices=["trocar", "mover"], help="motion control: trocar o personagem ou copiar o movimento")
    ap.add_argument("--duracao", type=float, default=5)
    ap.add_argument("--cena", default="geral", help="personagem, acao, paisagem, produto, interface, texto, grafico…")
    ap.add_argument("--ultimo-quadro", action="store_true")
    ap.add_argument("--capacidades", help="exigências separadas por vírgula: i2v, ultimo_quadro, lip_sync, audio, identidade")
    ap.add_argument("--perfil", default="economico", choices=["economico", "equilibrado", "premium"])
    ap.add_argument("--orcamento", type=float)
    ap.add_argument("--resultado", nargs=3, metavar=("MODELO", "CENA", "STATUS"))
    ap.add_argument("--custo", type=float)
    ap.add_argument("--historico", action="store_true")
    a = ap.parse_args()
    if a.resultado:
        return resultado(*a.resultado, custo=a.custo)
    if a.historico:
        for mod, cenas in carregar(HIST, {}).items():
            for c, h in cenas.items():
                print(f"  {mod:<55} {c:<12} {h['aprovados']}✓ {h['reprovados']}✕  gasto US$ {h.get('custo_real', 0):.2f}")
        return
    caps = {c.strip() for c in a.capacidades.split(",") if c.strip()} if a.capacidades else None
    dec, cands = escolher(a.tipo, a.duracao, a.cena, a.ultimo_quadro, a.perfil, a.orcamento, modo=a.modo, capacidades=caps)
    print(f"ESCOLHA: {dec['modelo']}  (US$ {dec['custo']})\nMotivo: {dec['motivo']}" + (f" — {dec['detalhe']}" if dec.get("detalhe") else ""))
    if cands:
        print("\nAlternativas (custo esperado por cena aprovada):")
        for c in cands[:8]:
            print(f"  q{c['q']} {c['modelo']:<55} US$ {c['preco']:.3f}{'*' if c.get('estimado') else ' '} aprov. {c['taxa']:.0%}  esperado US$ {c['esperado']:.3f}")
        print("  (* preço por tokens, estimado)")


if __name__ == "__main__":
    main()
