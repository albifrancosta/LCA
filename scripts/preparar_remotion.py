"""Monta o projeto Remotion de um vídeo: copia o modelo, junta BEATS + transcript + cenas.json em src/video.json
e copia voz, imagens e prints para public/.

Uso:
    python preparar_remotion.py <pasta-remotion> --beats BEATS.json --transcript transcript.json \
        --cenas cenas.json --voz assets/narracao-norm.wav [--marca marca.json] [--legenda caixa]

cenas.json = uma entrada por cena do BEATS (mesma ordem), com "tipo" e os campos do tipo (ver Video.tsx).
Âncoras na voz (em vez de tempo fixo):
  - mensagens[].na_palavra / foco.na_palavra: a mensagem/zoom acontece quando essa palavra é falada na cena
  - mensagens[].apos: segundos depois do início da cena
Depois: npm install (1ª vez) → npx remotion studio  (prévia)  → npx remotion render Video out/video.mp4

Cena "video" (clipe MP4): {"tipo": "video", "src": "assets/clips/c03.mp4", "de": 0.0 (s do clipe onde começa),
  "som": false, "volume": 1, "plano": "<id na inspeção, padrão = id da cena>"} — o arquivo precisa ser mídia válida.
Caminhos relativos (src, logo, --voz, --musica, --sfx) são da pasta do projeto = pasta do cenas.json (depois a do BEATS).
Arquivos vão para public/ com prefixo do sha256 (a/cena.png e b/cena.png não se sobrescrevem).
SFX: --sfx sfx.json ou cenas.json no formato {"cenas": [...], "sfx": [...]}; item {"src", "inicio" | "cena"+"apos", "volume"};
  ou "sfx": [{"src", "apos", "volume"}] dentro de uma cena.
--final: recusa cena "video" cuja inspeção (entrega/inspecao-planos.json, mesmo sha256) não esteja "aprovado" e qualquer
  ativo com marca .rascunho. Sem --final só avisa.
"""
import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from integridade import APROVADO, estado_inspecao, midia_valida, sha256, sonda  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODELO = Path(__file__).resolve().parent.parent / "templates" / "remotion-base"
TIPOS = {"titulo", "imagem", "print", "celular", "preto", "cta", "video"}  # espelha CENAS em Video.tsx
MARCA_PADRAO = {"fundo": "#071226", "fundo2": "#12305C", "primaria": "#38BDF8", "texto": "#FFFFFF", "alerta": "#F43F5E"}


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9%]+", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def ler(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def palavras(p):
    d = ler(p)
    if isinstance(d, dict):
        d = d.get("words") or [w for v in d.get("voices", []) for w in v.get("words", [])] \
            or [w for s in d.get("segments", []) for w in s.get("words", [])]
    return [{"text": (w.get("text") or w.get("word") or "").strip(), "start": round(float(w["start"]), 3),
             "end": round(float(w["end"]), 3)} for w in d if (w.get("text") or w.get("word") or "").strip()]


def tempo_da_palavra(ws, i0, i1, alvo, depois=0.0):
    n = norm(alvo)
    for i in range(i0, i1 + 1):
        if norm(ws[i]["text"]) == n and ws[i]["start"] >= depois:
            return ws[i]["start"]
    raise SystemExit(f'palavra "{alvo}" não encontrada na fala da cena ({" ".join(w["text"] for w in ws[i0:i1 + 1])})')


def resolver(src, bases):
    """Caminho relativo: procura nas pastas do projeto (em ordem); cwd só como último recurso, com aviso (P43)."""
    origem = Path(src)
    if origem.is_absolute():
        return origem
    for b in bases:
        if (b / src).exists():
            return (b / src).resolve()
    if origem.exists():
        print(f"  AVISO: {src} achado só a partir da pasta atual ({Path.cwd()}), não na pasta do projeto")
        return origem.resolve()
    return (bases[0] / src).resolve()


def copiar(src, public, bases, manifesto=None):
    """Copia para public/ com nome único <sha256[:12]>-<nome> (P40) e devolve o nome publicado."""
    if not src:
        return src
    origem = resolver(src, bases)
    if not origem.is_file():
        raise SystemExit(f"arquivo não encontrado: {origem}")
    h = sha256(origem)
    nome = f"{h[:12]}-{origem.name}"
    destino = public / nome
    if not destino.exists() or sha256(destino) != h:
        shutil.copy2(origem, destino)
    if manifesto is not None:
        manifesto[nome] = {"origem": str(origem), "sha256": h, "rascunho": Path(str(origem) + ".rascunho").exists()}
    return nome


def montar_sfx(itens, cenas, duracao, public, bases, manifesto, problemas):
    por_id = {c["id"]: c for c in cenas}
    saida = []
    for k, it in enumerate(itens or []):
        if not isinstance(it, dict) or not it.get("src"):
            problemas.append(f'sfx[{k}]: precisa de "src"')
            continue
        if "inicio" in it:
            inicio = float(it["inicio"])
        elif it.get("cena") in por_id:
            inicio = por_id[it["cena"]]["inicio"] + float(it.get("apos", 0))
        else:
            problemas.append(f'sfx[{k}] {it["src"]}: sem "inicio" nem "cena" válida ({it.get("cena")})')
            continue
        if not 0 <= inicio < duracao:
            problemas.append(f"sfx[{k}] {it['src']}: início {inicio:.2f}s fora do vídeo (0–{duracao}s)")
            continue
        arq = resolver(it["src"], bases)
        ok, motivo = midia_valida(str(arq), "audio")
        if not ok:
            problemas.append(f"sfx[{k}]: {motivo}")
            continue
        saida.append({"src": copiar(str(arq), public, bases, manifesto), "inicio": round(inicio, 3),
                      "volume": float(it.get("volume", 0.6))})
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--beats", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--cenas", required=True)
    ap.add_argument("--voz")
    ap.add_argument("--musica")
    ap.add_argument("--volume-musica", type=float, default=0.12)
    ap.add_argument("--sfx", help="JSON com lista de efeitos [{src, inicio | cena+apos, volume}]")
    ap.add_argument("--marca", help="arquivo JSON com fundo, fundo2, primaria, texto, alerta")
    ap.add_argument("--legenda", default="caixa", choices=["caixa", "cor", "nenhuma"])
    ap.add_argument("--altura-legenda", type=float, default=0.64)
    ap.add_argument("--largura", type=int, default=1080)
    ap.add_argument("--altura", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--folga-final", type=float, default=0.8)
    ap.add_argument("--final", action="store_true", help="exige inspeção aprovada dos clipes e nenhum ativo rascunho")
    ap.add_argument("--projeto", help="pasta com entrega/inspecao-planos.json (padrão: pasta do cenas.json)")
    a = ap.parse_args()

    pasta = Path(a.pasta).resolve()
    if not (pasta / "package.json").exists():
        shutil.copytree(MODELO, pasta, dirs_exist_ok=True)
        print(f"modelo copiado para {pasta} — rode: npm install")
    public = pasta / "public"
    public.mkdir(exist_ok=True)
    base = Path(a.cenas).resolve().parent
    pasta_beats = Path(a.beats).resolve().parent
    bases = [base] + ([pasta_beats] if pasta_beats != base else [])
    projeto = Path(a.projeto).resolve() if a.projeto else base

    beats = ler(a.beats)
    ws = palavras(a.transcript)
    specs = ler(a.cenas)
    sfx_cenas = []
    if isinstance(specs, dict):  # {"cenas": [...], "sfx": [...]}
        sfx_cenas = specs.get("sfx", [])
        specs = specs.get("cenas", [])
    cenas_b = beats["scenes"]
    if len(specs) != len(cenas_b):
        raise SystemExit(f"cenas.json tem {len(specs)} cenas e o BEATS tem {len(cenas_b)} — precisam ser iguais")
    # P55: tipo desconhecido para ANTES do render (Video.tsx também mostra erro visível, mas não deve chegar lá)
    ruins = [f"{b['id']}: tipo {s.get('tipo')!r}" for b, s in zip(cenas_b, specs) if s.get("tipo") not in TIPOS]
    if ruins:
        raise SystemExit("tipo de cena não suportado (válidos: " + ", ".join(sorted(TIPOS)) + "):\n  - " + "\n  - ".join(ruins))

    duracao = round(cenas_b[-1]["end"] + a.folga_final, 3)
    cenas, problemas, avisos, manifesto, sfx_locais = [], [], [], {}, []
    for i, (b, s) in enumerate(zip(cenas_b, specs)):
        i0, i1 = b["words"]
        c = dict(s)
        c["id"] = b["id"]
        c["inicio"] = b["start"]
        c["fim"] = duracao if i == len(cenas_b) - 1 else b["end"]
        c["batidas"] = [{"texto": k["word"], "inicio": k["start"]} for k in beats.get("keywords", []) if k.get("scene") == b["id"]]
        if c["tipo"] == "video":
            if not c.get("src"):
                raise SystemExit(f'{c["id"]}: cena video sem "src"')
            arq = resolver(c["src"], bases)
            ok, motivo = midia_valida(str(arq), "video")
            if not ok:
                raise SystemExit(f"{c['id']}: clipe inválido — {motivo}")
            c["videoDur"] = round(sonda(str(arq))["duracao"], 3)
            if float(c.get("de", 0)) >= c["videoDur"]:
                raise SystemExit(f'{c["id"]}: "de"={c.get("de")}s além do fim do clipe ({c["videoDur"]}s)')
            est, mot = estado_inspecao(str(projeto), c.get("plano", c["id"]), str(arq))
            if est != APROVADO:
                (problemas if a.final else avisos).append(f"{c['id']}: inspeção do clipe {c['src']} = {est}" + (f" ({mot})" if mot else ""))
            c["midia"] = {"tipo": "video", "arquivo": c["src"], "sha256": sha256(arq), "qa_estado": est}
        for campo in ("src", "logo"):
            if c.get(campo):
                c[campo] = copiar(c[campo], public, bases, manifesto)
                if manifesto[c[campo]]["rascunho"]:
                    (problemas if a.final else avisos).append(f"{c['id']}: {campo} {s[campo]} é rascunho")
        if c.get("src") and "midia" not in c:
            c["midia"] = {"tipo": "imagem", "arquivo": s["src"], "sha256": manifesto[c["src"]]["sha256"],
                          "qa_estado": estado_inspecao(str(projeto), c.get("plano", c["id"]))[0]}
        for k in c.pop("sfx", None) or []:  # sfx da cena: tempo relativo ao início dela
            sfx_locais.append({**k, "cena": c["id"]})
        ultimo = c["inicio"]
        for m in c.get("mensagens", []):
            if "na_palavra" in m:
                m["inicio"] = tempo_da_palavra(ws, i0, i1, m.pop("na_palavra"), ultimo)
            elif "apos" in m:
                m["inicio"] = round(c["inicio"] + m.pop("apos"), 3)
            m.setdefault("inicio", c["inicio"] + 0.3)
            ultimo = m["inicio"]
        if c.get("foco") and "na_palavra" in c["foco"]:
            c["foco"]["inicio"] = tempo_da_palavra(ws, i0, i1, c["foco"].pop("na_palavra")) - 0.3
        cenas.append(c)

    grupos = [{"start": g["start"], "end": g["end"], "words": g["words"], "key": g.get("key", False)} for g in beats["groups"]]
    for g in grupos:  # a Legenda indexa palavras[] por estes índices
        w0, w1 = g["words"]
        if not (0 <= w0 <= w1 < len(ws)):
            raise SystemExit(f"grupo de legenda {g['words']} fora da transcrição ({len(ws)} palavras)")
    itens_sfx = list(sfx_cenas) + (ler(resolver(a.sfx, bases)) if a.sfx else []) + sfx_locais
    sfx = montar_sfx(itens_sfx, cenas, duracao, public, bases, manifesto, problemas)
    for m in avisos:
        print(f"  AVISO: {m}")
    if problemas:
        raise SystemExit(f"montagem recusada — {len(problemas)} problema(s):\n  - " + "\n  - ".join(problemas))
    dados = {
        "fps": a.fps, "width": a.largura, "height": a.altura, "duracao": duracao,
        "marca": {**MARCA_PADRAO, **(ler(a.marca) if a.marca else {})},
        "audio": {"voz": copiar(a.voz, public, bases, manifesto) if a.voz else None,
                  "musica": copiar(a.musica, public, bases, manifesto) if a.musica else None,
                  "volumeMusica": a.volume_musica},
        "cenas": cenas,
        "legenda": {"estilo": a.legenda, "altura": a.altura_legenda, "palavras": ws, "grupos": grupos},
        "sfx": sfx,
        "montagem": {"modo": "final" if a.final else "preview", "arquivos": manifesto},
    }
    (pasta / "src" / "video.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{pasta / 'src' / 'video.json'}: {len(cenas)} cenas · {duracao}s · legenda {a.legenda} · {len(sfx)} sfx")
    for c in cenas:
        print(f"  {c['id']}: {c['inicio']:6.2f} -> {c['fim']:6.2f}  {c['tipo']}")


if __name__ == "__main__":
    main()
