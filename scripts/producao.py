"""Bíblia da produção: um arquivo só por projeto (`<projeto>/producao.json`) que todos os departamentos leem e escrevem.
Guarda elenco (ficha, voz, traços, figurino), cenários (luz, paleta, som ambiente, referência), objetos e cada TOMADA com
decupagem (fotografia), versões (arquivo, prompt, modelo, custo, data, checagem de continuidade) e status de aprovação.

Uso (rode dentro da pasta do projeto ou passe --projeto):
  python producao.py iniciar --titulo "Plano nº 47" --estilo "Ilustração 2D cinematográfica…" [--formato 9:16]
  python producao.py personagem tiago --nome Tiago --descricao "…" --ficha assets/ilustrado/ficha-tiago.png --voz Puck \
         --tracos "óculos redondos de armação preta;cabelo castanho bagunçado" --figurino "moletom=mostarda;calça=jeans escura"
  python producao.py cenario poste-noite --descricao "rua de bairro sob poste" --luz "noite chuvosa azul-marinho, luz quente do poste" \
         --ambiente chuva [--ref assets/ilustrado/gancho.png] [--paleta "#1B2A44,#F2B23A"]
  python producao.py objeto caderno --descricao "caderninho de capa azul" [--ref img.png]
  python producao.py tomada t001 --cena gancho --cenario poste-noite --personagens tiago --objetos caderno \
         --acao "escreve no caderno, ergue o rosto sorrindo" --fala "Plano quarenta e sete…" \
         --plano medio --lente 35mm --movimento "push-in lento" --inicio "olhando o caderno" --fim "olhando para cima, sorriso"
  python producao.py versao t001 assets/clips/p01.mp4 --tipo clipe --modelo fal-ai/… --custo 0.27 --prompt "…"
  python producao.py status t001 aprovada [--nota "ok do usuário"]
  python producao.py prompt t001            → prompt de imagem (arte + fotografia) e de clipe, montados da bíblia
  python producao.py decupar ROTEIRO.md     → o Gemini propõe a decupagem de cada tomada (entra como rascunho)
  python producao.py resumo                 → tabela de tomadas, status, versões e custo
Status: rascunho → aguardando (precisa do ok) → aprovada | refazer.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integridade as ig  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQ = "producao.json"
PLANOS = {"geral": "wide establishing shot", "medio": "medium shot", "americano": "medium-long shot (knees up)",
          "close": "close-up", "detalhe": "extreme close-up detail", "plongee": "high-angle shot", "contra": "low-angle shot",
          "pov": "point-of-view shot", "dois": "two-shot"}
LENTES = {"24mm": "24mm wide lens", "35mm": "35mm lens", "50mm": "50mm lens", "85mm": "85mm portrait lens, shallow depth of field"}


from integridade import relativo as _rel  # noqa: E402  (relpath seguro entre discos)


def achar(pasta=None):
    p = os.path.abspath(pasta or os.getcwd())
    for _ in range(5):
        if os.path.exists(os.path.join(p, ARQ)):
            return os.path.join(p, ARQ)
        p = os.path.dirname(p)
    return None


def carregar(pasta=None, criar=False):
    arq = achar(pasta)
    if not arq:
        if not criar:
            sys.exit("producao.json não encontrado — rode `producao.py iniciar` na pasta do projeto")
        arq = os.path.join(os.path.abspath(pasta or os.getcwd()), ARQ)
        return arq, {"titulo": "", "estilo": "", "formato": "9:16", "personagens": {}, "cenarios": {}, "objetos": {},
                     "tomadas": [], "historico": []}
    return arq, json.load(open(arq, encoding="utf-8"))


class Conflito(SystemExit):
    pass


def salvar(arq, d, evento=None):
    """Grava com trava + revisão otimista (P26): se outro agente gravou depois que você carregou, NÃO sobrescreve."""
    if evento:
        d.setdefault("historico", []).append({"quando": datetime.datetime.now().isoformat(timespec="seconds"), "o_que": evento})
    with ig.trava(arq):
        if os.path.exists(arq):
            atual = json.load(open(arq, encoding="utf-8"))
            if int(atual.get("_revisao", 0)) != int(d.get("_revisao", 0)):
                raise Conflito(f"conflito: producao.json mudou (rev {atual.get('_revisao', 0)}) desde que foi lido "
                               f"(rev {d.get('_revisao', 0)}) — outro agente gravou; carregue de novo e repita o comando")
        d["_revisao"] = int(d.get("_revisao", 0)) + 1
        ig.gravar_json_atomico(arq, d)


def tomada(d, tid, criar=False):
    for t in d["tomadas"]:
        if t["id"] == tid:
            return t
    if not criar:
        sys.exit(f"tomada {tid} não existe")
    t = {"id": tid, "status": "rascunho", "personagens": [], "objetos": [], "decupagem": {}, "versoes": []}
    d["tomadas"].append(t)
    return t


def lista(s, sep=";"):
    return [x.strip() for x in (s or "").split(sep) if x.strip()]


def pares(s):
    return dict(x.split("=", 1) for x in lista(s)) if s else {}


# ---------- prompts montados da bíblia (direção de arte + fotografia) ----------
def prompt_imagem(d, t):
    partes = [d.get("estilo", "")]
    c = d["cenarios"].get(t.get("cenario", ""), {})
    for pid in t.get("personagens", []):
        p = d["personagens"].get(pid, {})
        fig = ", ".join(f"{k} {v}" for k, v in (p.get("figurino") or {}).items())
        partes.append(f"{p.get('nome', pid)}: {p.get('descricao', '')}; sempre com {'; '.join(p.get('tracos', []))}; roupa: {fig}")
    for oid in t.get("objetos", []):
        partes.append(f"objeto: {d['objetos'].get(oid, {}).get('descricao', oid)}")
    if c:
        partes.append(f"cenário: {c.get('descricao', '')}; luz: {c.get('luz', '')}")
        if c.get("paleta"):
            partes.append(f"paleta {', '.join(c['paleta'])}")
    if t.get("acao"):
        partes.append(f"ação: {t['acao']}")
    dec = t.get("decupagem") or {}
    cam = [PLANOS.get(dec.get("plano"), dec.get("plano")), LENTES.get(dec.get("lente"), dec.get("lente"))]
    partes.append("câmera: " + ", ".join(x for x in cam if x))
    partes.append("enquadramento vertical 9:16" if d.get("formato", "9:16") == "9:16" else "enquadramento horizontal 16:9")
    if d.get("estilo_evitar"):
        partes.append("evitar: " + d["estilo_evitar"])
    partes.append("sem texto, sem letras, sem logotipos")
    return ". ".join(x for x in partes if x)


def refs_imagem(d, t, raiz):
    r = [d["personagens"][p]["ficha"] for p in t.get("personagens", []) if d["personagens"].get(p, {}).get("ficha")]
    r += [d["objetos"][o]["ref"] for o in t.get("objetos", []) if d["objetos"].get(o, {}).get("ref")]
    c = d["cenarios"].get(t.get("cenario", ""), {})
    if c.get("ref"):
        r.append(c["ref"])
    return [os.path.join(raiz, x) if not os.path.isabs(x) else x for x in r]


def clipe_roteiro(t):
    """Formato do prompt_clipe.py: quadro inicial → etapas com TEMPO (uma por beat do contrato) → quadro final (P13)."""
    dec = t.get("decupagem") or {}
    c = t.get("direcao") or {}
    dur = c.get("duracao") or dec.get("duracao", 5)
    cam = dec.get("movimento") or c.get("camera") or "static"
    beats = c.get("beats") or dec.get("beats") or []
    if beats:
        from contrato import normalizar_beats
        etapas = [{"camera": cam, "acao": b.get("en") or b.get("acao") or b.get("pt", ""), "ate": b["fim"], "fase": b.get("fase"),
                   "evidencia": b.get("evidencia") or b.get("pt", ""), "pausa": b.get("fase") == "pausa"}
                  for b in normalizar_beats(beats)]
    else:  # sem beats o contrato.validar já bloqueia atuação; aqui fica a etapa única
        etapas = [{"camera": cam, "acao": t.get("acao", ""), "ate": dur}]
    return {"duracao": dur, "assunto": t.get("acao", ""), "inicio": dec.get("inicio") or c.get("quadro_inicial", ""),
            "etapas": etapas, "fim": dec.get("fim") or c.get("quadro_final", "")}


def bloqueios_aprovacao(d, t, raiz):
    """Motivos que IMPEDEM aprovar a tomada (P03/P25). Vazio = pode aprovar. Aprovação do usuário no chat não substitui
    a prova técnica, e vice-versa."""
    m = []
    if not (t.get("decupagem") or {}).get("plano") and not (t.get("direcao") or {}).get("modo"):
        m.append("sem decupagem/contrato")
    img = next((v for v in reversed(t.get("versoes", [])) if v["tipo"] == "imagem" and not v.get("invalida")), None)
    if not img:
        return m + ["sem imagem válida"]
    caminho = os.path.join(raiz, img["arquivo"])
    ok, motivo = ig.midia_valida(caminho, "imagem")
    if not ok:
        m.append(motivo)
    elif img.get("sha256") and ig.sha256(caminho) != img["sha256"]:
        m.append("a imagem no disco mudou depois de registrada — registre uma nova versão")
    cont = img.get("continuidade") or {}
    if cont.get("ok") is not True:
        m.append("continuidade da imagem " + ("reprovada" if cont.get("ok") is False else "não verificada"))
    return m


# ---------- decupagem pelo Gemini ----------
PEDIDO_DECUPAGEM = """Você é diretor de fotografia de um curta vertical 9:16 em ilustração 2D cinematográfica.
Bíblia: personagens {pers}; cenários {cens}; objetos {objs}.
Divida o roteiro abaixo em TOMADAS (um corte a cada 2–3 s; ação física quebrada em mais tomadas) e decupe cada uma.
Para cada tomada: id (t001, t002…), cena (nome curto do bloco), cenario (id da bíblia), personagens (ids), objetos (ids),
acao (o que se vê, em português, concreto), fala (trecho falado ou ""), plano ({planos}), lente ({lentes}),
movimento (movimento de câmera curto em inglês: static, slow push-in, pan left, handheld shake, tilt up…),
inicio (descrição do primeiro quadro), fim (descrição do último quadro, que deve encaixar no início da próxima),
duracao (s), modo (acao | reacao | fala | insert | estabelecimento | titulo), clipe (true SEMPRE que houver personagem
agindo, reagindo — mesmo só piscar, respirar, olhar — ou falando em quadro; false só para insert/estabelecimento/título
sem atuação: personagem atuando nunca é foto com zoom).
Varie plano e movimento entre tomadas vizinhas. Responda só JSON: {{"tomadas": [...]}}

ROTEIRO:
{roteiro}"""


def decupar(d, texto):
    sys.path.insert(0, AQUI)
    from tts_gemini import URL, chave
    pedido = PEDIDO_DECUPAGEM.format(pers=list(d["personagens"]), cens=list(d["cenarios"]), objs=list(d["objetos"]),
                                     planos=", ".join(PLANOS), lentes=", ".join(LENTES), roteiro=texto)
    corpo = {"contents": [{"parts": [{"text": pedido}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}
    req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])["tomadas"]


def custo_total(d):
    return round(sum(v.get("custo") or 0 for t in d["tomadas"] for v in t["versoes"]), 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projeto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("iniciar"); s.add_argument("--titulo", required=True); s.add_argument("--estilo", default="")
    s.add_argument("--formato", default="9:16")
    s = sub.add_parser("personagem"); s.add_argument("id")
    for k in ("nome", "descricao", "ficha", "voz", "tracos", "figurino", "estilo_voz"):
        s.add_argument("--" + k)
    s = sub.add_parser("cenario"); s.add_argument("id")
    for k in ("descricao", "luz", "ambiente", "ref", "paleta"):
        s.add_argument("--" + k)
    s = sub.add_parser("objeto"); s.add_argument("id"); s.add_argument("--descricao"); s.add_argument("--ref")
    s = sub.add_parser("tomada"); s.add_argument("id")
    for k in ("cena", "cenario", "personagens", "objetos", "acao", "fala", "plano", "lente", "movimento", "inicio", "fim",
              "duracao", "clipe"):
        s.add_argument("--" + k)
    s = sub.add_parser("versao"); s.add_argument("id"); s.add_argument("arquivo")
    s.add_argument("--tipo", default="imagem", choices=["imagem", "clipe", "voz", "som"])
    s.add_argument("--prompt", default=""); s.add_argument("--modelo", default=""); s.add_argument("--custo", type=float, default=0)
    s = sub.add_parser("status"); s.add_argument("id"); s.add_argument("valor", choices=["rascunho", "aguardando", "aprovada", "refazer"])
    s.add_argument("--nota", default=""); s.add_argument("--forcar", action="store_true", help="aprovar mesmo com bloqueio (exige --nota)")
    s = sub.add_parser("qa", help="registra o resultado do inspetor na última versão de clipe/voz")
    s.add_argument("id"); s.add_argument("estado", choices=list(ig.ESTADOS)); s.add_argument("--tipo", default="clipe", choices=["clipe", "voz"])
    s.add_argument("--relatorio", default=""); s.add_argument("--nota", default="")
    s = sub.add_parser("prompt"); s.add_argument("id")
    s = sub.add_parser("decupar"); s.add_argument("roteiro")
    sub.add_parser("resumo")
    a = ap.parse_args()

    arq, d = carregar(a.projeto, criar=a.cmd == "iniciar")
    raiz = os.path.dirname(arq)
    if a.cmd == "iniciar":
        d.update({"titulo": a.titulo, "estilo": a.estilo or d.get("estilo", ""), "formato": a.formato})
        salvar(arq, d, "projeto iniciado")
        print(arq)
    elif a.cmd == "personagem":
        p = d["personagens"].setdefault(a.id, {})
        for k in ("nome", "descricao", "ficha", "voz", "estilo_voz"):
            if getattr(a, k):
                p[k] = getattr(a, k)
        if a.tracos:
            p["tracos"] = lista(a.tracos)
        if a.figurino:
            p["figurino"] = pares(a.figurino)
        salvar(arq, d, f"personagem {a.id}")
        print(json.dumps(p, ensure_ascii=False, indent=1))
    elif a.cmd == "cenario":
        c = d["cenarios"].setdefault(a.id, {})
        for k in ("descricao", "luz", "ambiente", "ref"):
            if getattr(a, k):
                c[k] = getattr(a, k)
        if a.paleta:
            c["paleta"] = lista(a.paleta, ",")
        salvar(arq, d, f"cenário {a.id}")
        print(json.dumps(c, ensure_ascii=False, indent=1))
    elif a.cmd == "objeto":
        o = d["objetos"].setdefault(a.id, {})
        for k in ("descricao", "ref"):
            if getattr(a, k):
                o[k] = getattr(a, k)
        salvar(arq, d, f"objeto {a.id}")
    elif a.cmd == "tomada":
        t = tomada(d, a.id, criar=True)
        for k in ("cena", "cenario", "acao", "fala"):
            if getattr(a, k) is not None:
                t[k] = getattr(a, k)
        for k in ("personagens", "objetos"):
            if getattr(a, k) is not None:
                t[k] = lista(getattr(a, k), ",")
        for k in ("plano", "lente", "movimento", "inicio", "fim"):
            if getattr(a, k) is not None:
                t["decupagem"][k] = getattr(a, k)
        if a.duracao:
            t["decupagem"]["duracao"] = float(a.duracao)
        if a.clipe is not None:
            t["clipe"] = a.clipe.lower() in ("1", "sim", "true", "s")
        salvar(arq, d, f"tomada {a.id}")
        print(json.dumps(t, ensure_ascii=False, indent=1))
    elif a.cmd == "versao":
        t = tomada(d, a.id)
        rel = _rel(os.path.abspath(a.arquivo), raiz).replace("\\", "/")
        tipo_midia = {"imagem": "imagem", "clipe": "video", "voz": "audio", "som": "audio"}[a.tipo]
        ok, motivo = ig.midia_valida(os.path.abspath(a.arquivo), tipo_midia)
        if not ok:
            sys.exit(f"versão recusada: {motivo}")  # P29: não registra arquivo ausente, vazio ou ilegível
        if a.custo < 0:
            sys.exit("custo negativo não é válido")
        v = {"v": len(t["versoes"]) + 1, "tipo": a.tipo, "arquivo": rel, "prompt": a.prompt, "modelo": a.modelo,
             "custo": a.custo, "quando": datetime.datetime.now().isoformat(timespec="seconds"),
             "sha256": ig.sha256(os.path.abspath(a.arquivo))}
        if a.tipo == "clipe":  # P04/P27: o clipe nasce de UMA imagem; se a imagem mudar, ele deixa de valer
            img = next((x for x in reversed(t["versoes"]) if x["tipo"] == "imagem" and not x.get("invalida")), None)
            if not img:
                sys.exit("versão de clipe recusada: a tomada não tem imagem válida de origem")
            v["origem"] = {"imagem_v": img["v"], "imagem_sha256": img.get("sha256")}
            v["qa"] = ig.NAO_VERIFICADO
        if a.tipo == "voz":
            v["texto_sha256"] = ig.sha256_texto(t.get("fala", ""))
            v["qa"] = ig.NAO_VERIFICADO
        t["versoes"].append(v)
        if t["status"] in ("rascunho", "refazer"):
            t["status"] = "aguardando"
        salvar(arq, d, f"{a.id} v{v['v']} ({a.tipo})")
        print(f"{a.id} v{v['v']} → {rel}")
    elif a.cmd == "status":
        t = tomada(d, a.id)
        if a.valor == "aprovada":
            bl = bloqueios_aprovacao(d, t, raiz)
            if bl and not (a.forcar and a.nota):
                sys.exit(f"{a.id} não pode ser aprovada: " + "; ".join(bl) + "  (decisão do diretor no chat: --forcar --nota 'motivo')")
            if bl:
                t.setdefault("notas", []).append(f"aprovada À FORÇA ({'; '.join(bl)}): {a.nota}")
        t["status"] = a.valor
        if a.nota:
            t.setdefault("notas", []).append(a.nota)
        salvar(arq, d, f"{a.id} → {a.valor} {a.nota}".strip())
        print(f"{a.id}: {a.valor}")
    elif a.cmd == "qa":
        t = tomada(d, a.id)
        v = next((x for x in reversed(t["versoes"]) if x["tipo"] == a.tipo and not x.get("invalida")), None)
        if not v:
            sys.exit(f"{a.id}: não há versão válida de {a.tipo} para registrar QA")
        caminho = os.path.join(raiz, v["arquivo"])
        if v.get("sha256") and (not os.path.isfile(caminho) or ig.sha256(caminho) != v["sha256"]):
            sys.exit(f"{a.id}: o arquivo de {a.tipo} mudou depois de registrado — QA não vale para outro conteúdo")
        v["qa"], v["qa_relatorio"], v["qa_quando"] = a.estado, a.relatorio, datetime.datetime.now().isoformat(timespec="seconds")
        if a.nota:
            v["qa_nota"] = a.nota
        salvar(arq, d, f"{a.id}: QA {a.tipo} v{v['v']} = {a.estado}")
        print(f"{a.id}: {a.tipo} v{v['v']} → {a.estado}")
    elif a.cmd == "prompt":
        t = tomada(d, a.id)
        print("IMAGEM:\n" + prompt_imagem(d, t))
        print("\nREFERÊNCIAS (--ref):\n" + "\n".join(refs_imagem(d, t, raiz)))
        print("\nCLIPE (prompt_clipe.py):\n" + json.dumps(clipe_roteiro(t), ensure_ascii=False, indent=1))
    elif a.cmd == "decupar":
        novas = decupar(d, open(a.roteiro, encoding="utf-8").read())
        for n in novas:
            t = tomada(d, n["id"], criar=True)
            if t["status"] == "aprovada":
                continue  # não mexe no que você já aprovou
            for k in ("cena", "cenario", "acao", "fala", "clipe", "modo"):
                if k in n:
                    t[k] = n[k]
            if t.get("modo") in ig.MODOS_ANIMADOS and t.get("personagens"):
                t["clipe"] = True  # P14: atuação/reação/fala nunca vira imagem parada
            t["personagens"], t["objetos"] = n.get("personagens", []), n.get("objetos", [])
            t["decupagem"] = {k: n.get(k) for k in ("plano", "lente", "movimento", "inicio", "fim", "duracao") if n.get(k) is not None}
        salvar(arq, d, f"decupagem: {len(novas)} tomadas")
        for n in novas:
            print(f"{n['id']}  {n.get('plano', ''):9} {n.get('lente', ''):5} {str(n.get('movimento', ''))[:18]:18} "
                  f"{'🎬' if n.get('clipe') else '  '} {n.get('acao', '')[:60]}")
    elif a.cmd == "resumo":
        print(f"{d['titulo']} — {len(d['tomadas'])} tomadas · {len(d['personagens'])} personagens · "
              f"{len(d['cenarios'])} cenários · custo US$ {custo_total(d)}")
        cont = {}
        for t in d["tomadas"]:
            cont[t["status"]] = cont.get(t["status"], 0) + 1
            ult = next((v for v in reversed(t["versoes"]) if v["tipo"] in ("imagem", "clipe")), {})
            chk = (ult.get("continuidade") or {}).get("ok")
            print(f"  {t['id']}  {t['status']:10} v{len(t['versoes'])}  continuidade {'✅' if chk else ('❌' if chk is False else '—')}  "
                  f"{t.get('cena', '')[:14]:14} {t.get('acao', '')[:50]}")
        print("  " + " · ".join(f"{k}: {v}" for k, v in cont.items()))


if __name__ == "__main__":
    main()
