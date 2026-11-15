"""Progresso do projeto de tempos em tempos: TEMPO DE EXECUÇÃO e PORCENTAGEM (pedido do usuário, 2026-11-07).

Duas medidas:
  etapa   — o laço que está rodando agora (ex.: geração dos takes no autonomo.py): feitos/total, %, tempo decorrido e
            estimativa do que falta (média por item × itens restantes). Uma linha a cada item concluído e, enquanto um item
            demora (fila do provedor), um "batimento" a cada `intervalo` segundos (padrão 60 s) — nunca fica mudo.
  projeto — o filme inteiro, pelo estado da produção (estado_producao.py): roteiro 10 % · imagens-chave 20 % · takes
            inspecionados 40 % · render atual 20 % · render verificado 10 %. Tempo desde o início do projeto (1ª medição
            ou criação do projeto.json/BRIEFING/roteiro).
Formato da linha (o Claude repete ao usuário de tempos em tempos):
  ⏱ [geração dos takes] 3/8 · 37% · 12min04s decorridos · ~20min restantes · projeto 52% · 1h03min desde o início
Arquivo: entrega/progresso.json (último estado + histórico curto).

Uso:
  python progresso.py <projeto>                 → linha de progresso do projeto agora
  python progresso.py <projeto> --vigiar 300    → repete a cada 300 s até chegar a 100 % (Ctrl+C para)
"""
import argparse
import datetime
import io
import json
import os
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

PESOS = {"roteiro": 10, "imagens": 20, "takes": 40, "render": 20, "verificado": 10}
FEITO = ("inspecionado", "corrigido_no_codigo", "renderizado", "verificado_no_render")


def fmt(s):
    s = int(max(0, s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}min" if h else (f"{m}min{s:02d}s" if m else f"{s}s")


def arq(base):
    return os.path.join(base, "entrega", "progresso.json")


def ler(base):
    try:
        return json.load(io.open(arq(base), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def inicio_projeto(base, relogio=time.time):
    d = ler(base)
    if d.get("inicio_projeto"):
        return datetime.datetime.fromisoformat(d["inicio_projeto"]).timestamp()
    cand = [os.path.getmtime(os.path.join(base, f)) for f in ("projeto.json", "BRIEFING.md", "roteiro.json") if os.path.exists(os.path.join(base, f))]
    return min(cand) if cand else relogio()


def projeto(base):
    """% do projeto inteiro pelo estado da produção (sem custo, sem rede)."""
    rot = os.path.join(base, "roteiro.json")
    if not os.path.exists(rot):
        return {"pct": 0.0, "partes": {}, "motivo": "sem roteiro.json"}
    import estado_producao as ep
    d = json.load(io.open(rot, encoding="utf-8"))
    nos = ep.sincronizar(base, d, gravar=False)["nos"]
    planos = d.get("planos", [])
    animados = [p for p in planos if (p.get("direcao") or {}).get("modo") in ig.MODOS_ANIMADOS]

    def frac(itens):
        itens = list(itens)
        return sum(itens) / len(itens) if itens else 1.0
    partes = {"roteiro": 1.0 if planos else 0.0,
              "imagens": frac(nos.get(f"img:{p['id']}", {}).get("estado") not in (None, "planejado") for p in animados),
              "takes": frac(nos.get(f"clipe:{p['id']}", {}).get("estado") in FEITO for p in animados), "render": 0.0, "verificado": 0.0}
    for rel, r in (ep._ler(base).get("renders") or {}).items():
        v = os.path.join(base, rel)
        if os.path.isfile(v) and ep.render_atual(base, v, d=d)["estado"] == "atual":
            partes["render"] = 1.0
            partes["verificado"] = max(partes["verificado"], 1.0 if r.get("verificado") else 0.0)
    if not animados:  # filme todo em código (motion graphics): imagens e takes não se aplicam
        partes["imagens"] = partes["takes"] = partes["roteiro"]
    return {"pct": round(sum(PESOS[k] * v for k, v in partes.items()), 1), "partes": {k: round(v, 2) for k, v in partes.items()}}


class Progresso:
    """Progresso de uma etapa com batimento periódico. Uso: with Progresso(base, total, "geração") as pg: pg.passo("c02a")."""

    def __init__(self, base, total, etapa, intervalo=60.0, saida=print, relogio=time.time, com_projeto=True):
        self.base, self.total, self.etapa = base, max(int(total), 0), etapa
        self.intervalo, self.saida, self.relogio, self.com_projeto = intervalo, saida, relogio, com_projeto
        self.feitos, self.atual = 0, None
        self.t0 = relogio()
        self._parar = threading.Event()
        self._th = None

    def pct(self):
        return 100.0 if self.total == 0 else round(100.0 * self.feitos / self.total, 1)

    def restante(self):
        if not self.feitos or self.feitos >= self.total:
            return None
        return (self.relogio() - self.t0) / self.feitos * (self.total - self.feitos)

    def linha(self):
        r = self.restante()
        txt = f"⏱ [{self.etapa}] {self.feitos}/{self.total} · {self.pct():.0f}% · {fmt(self.relogio() - self.t0)} decorridos"
        txt += f" · ~{fmt(r)} restantes" if r is not None else ""
        if self.atual:
            txt += f" · agora: {self.atual}"
        if self.com_projeto:
            try:
                txt += f" · projeto {projeto(self.base)['pct']:.0f}%"
            except Exception:  # noqa: BLE001 — progresso nunca derruba a produção
                pass
            txt += f" · {fmt(self.relogio() - inicio_projeto(self.base, self.relogio))} desde o início"
        return txt

    def gravar(self, linha=None):
        d = ler(self.base)
        d.setdefault("inicio_projeto", datetime.datetime.fromtimestamp(inicio_projeto(self.base, self.relogio)).isoformat(timespec="seconds"))
        r = self.restante()
        d.update(etapa=self.etapa, feitos=self.feitos, total=self.total, pct_etapa=self.pct(), decorrido_s=round(self.relogio() - self.t0, 1),
                 restante_s=None if r is None else round(r, 1), agora=self.atual,
                 atualizado=datetime.datetime.now().isoformat(timespec="seconds"), linha=linha or self.linha())
        d["historico"] = (d.get("historico") or [])[-49:] + [{"quando": d["atualizado"], "etapa": self.etapa, "pct": self.pct()}]
        try:
            ig.gravar_json_atomico(arq(self.base), d)
        except OSError:
            pass

    def _avisar(self, prefixo="⏱"):
        lin = self.linha().replace("⏱", prefixo, 1)
        self.saida(lin)
        self.gravar(lin)

    def comecar(self, item=None):
        self.atual = item
        self._avisar()

    def passo(self, item=None, n=1):
        self.feitos = min(self.total, self.feitos + n)
        self.atual = item
        self._avisar()

    def _batimento(self):
        while not self._parar.wait(self.intervalo):
            self._avisar()

    def __enter__(self):
        self.comecar()
        if self.intervalo and self.intervalo > 0:
            self._th = threading.Thread(target=self._batimento, daemon=True)
            self._th.start()
        return self

    def __exit__(self, *a):
        self._parar.set()
        self.atual = None
        self._avisar("⏱ fim")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projeto")
    ap.add_argument("--vigiar", type=float, help="segundos entre avisos (repete até 100%%)")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    while True:
        pj = projeto(base)
        st = ler(base)
        etapa = f" · etapa {st['etapa']} {st.get('pct_etapa', 0):.0f}%" if st.get("etapa") else ""
        print(f"⏱ projeto {pj['pct']:.0f}% · {fmt(time.time() - inicio_projeto(base))} desde o início{etapa} · partes {pj['partes']}", flush=True)
        if not a.vigiar or pj["pct"] >= 100:
            break
        time.sleep(a.vigiar)


if __name__ == "__main__":
    main()
