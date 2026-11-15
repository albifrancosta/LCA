"""Livro-caixa de custos + cache de gerações (nunca pagar duas vezes pela mesma coisa).

Uso:
  python custos.py relatorio [pasta-do-projeto]   → gasto por etapa e modelo, total, economia com cache, alternativa mais cara
  python custos.py adicionar <etapa> <modelo> <valor> ["detalhe"] [--projeto PASTA]   → lançamento manual (ex.: gasto antigo)
  python custos.py geral                          → total de todos os projetos (memoria/custos-geral.jsonl)

Como biblioteca (os scripts pagos usam):
  from custos import registrar, cache_chave, cache_buscar, cache_guardar
  k = cache_chave("clipe", modelo=..., prompt=..., imagem="caminho.png", duracao="5")   # arquivos entram pelo conteúdo (sha256)
  achado = cache_buscar("clipe", k, ".mp4")      → caminho já pago (copie e NÃO gere)
  cache_guardar("clipe", k, "saida.mp4")
  registrar("clipe", modelo, 0.35, "c1 · 5 s", fonte_preco="fal API 2026-11-05", cache=False)

O projeto é a pasta atual quando ela tem producao.json, BRIEFING.md ou falas.json (ou a variável CV_PROJETO).
Cache em %USERPROFILE%/estudio-video/cache/: cada artefato guarda o sha256 ao lado (<chave>.sha256); na busca, arquivo vazio,
ilegível (ffprobe/PIL) ou com sha256 diferente é apagado e conta como "não achado" (P39).
custos.json e custos-geral.jsonl são gravados sob trava (integridade.atualizar_json / trava): agentes em paralelo não perdem
lançamentos (P44). Valor desconhecido fica None no livro-caixa (aparece como "?"), nunca US$ 0.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from integridade import atualizar_json, midia_valida, sha256, trava  # noqa: E402

MEM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memoria")
GERAL = os.path.join(MEM, "custos-geral.jsonl")
CACHE = os.path.join(os.path.expanduser("~"), "estudio-video", "cache")


def projeto_atual(pasta=None):
    p = os.path.abspath(pasta or os.environ.get("CV_PROJETO") or os.getcwd())
    for _ in range(4):  # sobe até achar a raiz do projeto (rodando de dentro de remotion/ ou assets/)
        if any(os.path.exists(os.path.join(p, n)) for n in ("producao.json", "BRIEFING.md", "falas.json")):
            return p
        p = os.path.dirname(p)
    return None


def registrar(etapa, modelo, valor, detalhe="", fonte_preco="", cache=False, projeto=None):
    """Lança um gasto. valor=None = preço desconhecido (fica None, nunca vira US$ 0)."""
    proj = projeto_atual(projeto)
    item = {"data": datetime.date.today().isoformat(), "etapa": etapa, "modelo": modelo,
            "valor_usd": None if valor is None else round(float(valor), 4),
            "detalhe": detalhe, "fonte_preco": fonte_preco, "cache": bool(cache)}
    if valor is None:
        item["preco_desconhecido"] = True
    if proj:
        arq = os.path.join(proj, "custos.json")

        def anexar(dados):
            if not isinstance(dados, list):  # arquivo inesperado: não apaga, guarda dentro
                dados = [dados] if dados else []
            dados.append(item)
            return dados

        atualizar_json(arq, anexar, padrao=[])
    os.makedirs(os.path.dirname(os.path.abspath(GERAL)), exist_ok=True)
    with trava(GERAL):
        with open(GERAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(item, projeto=os.path.basename(proj) if proj else "(sem projeto)"), ensure_ascii=False) + "\n")
    return item


def _hash_arquivo(caminho):
    return sha256(caminho)


def _norm(v):
    if isinstance(v, os.PathLike):
        v = os.fspath(v)
    if isinstance(v, str) and len(v) < 400 and os.path.isfile(v):
        return "arquivo:" + _hash_arquivo(v)  # arquivo entra pelo CONTEÚDO, não pelo caminho
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in sorted(v.items())}
    return v


def cache_chave(tipo, **params):
    norm = {k: _norm(v) for k, v in sorted(params.items())}
    return hashlib.sha256(json.dumps([tipo, norm], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:32]


TIPO_MIDIA = {".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
              ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".aac": "audio", ".ogg": "audio", ".flac": "audio",
              ".png": "imagem", ".jpg": "imagem", ".jpeg": "imagem", ".webp": "imagem"}


def _apagar(*arqs):
    for a in arqs:
        with contextlib.suppress(OSError):
            os.remove(a)


def cache_buscar(tipo, chave, ext):
    """Caminho do artefato já pago, ou None. Entrada vazia, ilegível ou adulterada é apagada (P39)."""
    p = os.path.join(CACHE, tipo, chave + ext)
    if not os.path.exists(p):
        return None
    marca = p + ".sha256"
    if os.path.getsize(p) == 0:
        _apagar(p, marca)
        print(f"  cache: entrada vazia (0 byte) descartada: {p}", file=sys.stderr)
        return None
    if os.path.exists(marca):
        try:
            esperado = open(marca, encoding="utf-8").read().strip()
        except OSError:
            esperado = ""
        if esperado and sha256(p) != esperado:
            _apagar(p, marca)
            print(f"  cache: sha256 não confere (arquivo corrompido) — descartado: {p}", file=sys.stderr)
            return None
    tm = TIPO_MIDIA.get(ext.lower())
    if tm:
        try:
            ok, motivo = midia_valida(p, tm)
        except FileNotFoundError:  # sem ffprobe instalado: fica só com tamanho + sha256
            ok, motivo = True, ""
        if not ok:
            _apagar(p, marca)
            print(f"  cache: {motivo} — descartado", file=sys.stderr)
            return None
    return p


def cache_guardar(tipo, chave, arquivo):
    """Copia para o cache de forma atômica e anota o sha256. Não guarda arquivo vazio."""
    if not os.path.isfile(arquivo) or os.path.getsize(arquivo) == 0:
        print(f"  cache: {arquivo} vazio/ausente — não guardado", file=sys.stderr)
        return None
    pasta = os.path.join(CACHE, tipo)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, chave + os.path.splitext(arquivo)[1])
    fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".tmp-")
    os.close(fd)
    try:
        shutil.copyfile(arquivo, tmp)
        h = sha256(tmp)
        os.replace(tmp, destino)
    finally:
        _apagar(tmp)
    with open(destino + ".sha256", "w", encoding="utf-8") as f:
        f.write(h)
    return destino


def _v(d):
    return d.get("valor_usd")


def relatorio(pasta=None):
    proj = projeto_atual(pasta)
    if not proj or not os.path.exists(os.path.join(proj, "custos.json")):
        sys.exit("sem custos.json neste projeto (nada pago registrado)")
    dados = json.load(open(os.path.join(proj, "custos.json"), encoding="utf-8"))
    pagos = [d for d in dados if not d.get("cache")]
    sem_preco = [d for d in pagos if _v(d) is None]
    total = sum(_v(d) or 0 for d in pagos)
    economia = sum(_v(d) or 0 for d in dados if d.get("cache"))
    print(f"Custos — {os.path.basename(proj)}")
    print(f"{'etapa':<10} {'modelo':<52} {'US$':>7}  detalhe")
    for d in dados:
        val = f"{_v(d):>7.3f}" if _v(d) is not None else f"{'?':>7}"
        print(f"{d['etapa']:<10} {d['modelo'][:52]:<52} {val}  {d['detalhe']}{'  (cache: não pago)' if d.get('cache') else ''}")
    por = {}
    for d in pagos:
        por[d["etapa"]] = por.get(d["etapa"], 0) + (_v(d) or 0)
    print("\nPor etapa: " + " · ".join(f"{k} US$ {v:.2f}" for k, v in por.items()))
    print(f"TOTAL PAGO: US$ {total:.2f}" + (f" + {len(sem_preco)} lançamento(s) com PREÇO DESCONHECIDO" if sem_preco else "")
          + (f" · economizado com cache: US$ {economia:.2f}" if economia else ""))
    clipes = [d for d in pagos if d["etapa"] == "clipe"]
    if clipes:
        try:
            cat = json.load(open(os.path.join(MEM, "catalogo-modelos.json"), encoding="utf-8"))["modelos"]
            caro = max((m for m in cat if m["tipo"] == "video" and m.get("custo_5s")), key=lambda m: m["custo_5s"])
            print(f"Se todos os {len(clipes)} clipes fossem no mais caro do catálogo ({caro['id']}): ~US$ {caro['custo_5s'] * len(clipes):.2f}")
        except (OSError, ValueError, KeyError):
            pass


def geral():
    if not os.path.exists(GERAL):
        sys.exit("nada registrado ainda")
    por = {}
    for ln in open(GERAL, encoding="utf-8"):
        d = json.loads(ln)
        if not d.get("cache"):
            por[d["projeto"]] = por.get(d["projeto"], 0) + (d.get("valor_usd") or 0)
    for k, v in sorted(por.items()):
        print(f"  {k:<45} US$ {v:.2f}")
    print(f"TOTAL: US$ {sum(por.values()):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["relatorio", "adicionar", "geral"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--projeto")
    a = ap.parse_args()
    if a.acao == "relatorio":
        relatorio(a.args[0] if a.args else a.projeto)
    elif a.acao == "geral":
        geral()
    else:
        if len(a.args) < 3:
            sys.exit("uso: adicionar <etapa> <modelo> <valor> [detalhe]")
        print(registrar(a.args[0], a.args[1], a.args[2], a.args[3] if len(a.args) > 3 else "", "lançamento manual", projeto=a.projeto))
