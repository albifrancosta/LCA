"""Supervisor de continuidade: compara cada imagem/clipe de tomada com a BÍBLIA (producao.json) antes da montagem.
Confere rosto, cabelo, óculos e traços, cores do figurino, objetos, cenário e luz — e o encaixe com a tomada anterior
do mesmo cenário. Usa a visão do Gemini (grátis dentro da cota). Grava o resultado na versão (`continuidade`).

Uso (na pasta do projeto):
  python continuidade.py t001 t002          → checa a última versão de imagem/clipe dessas tomadas
  python continuidade.py --todas            → todas as tomadas com imagem/clipe ainda não checadas (--refazer: todas)
  python continuidade.py t003 --arquivo assets/ilustrado/teste.png   → checa um arquivo avulso contra a tomada
Clipe: confere 3 quadros (início, meio, fim). Resultado: ✅ ok · ⚠️ detalhe leve · ❌ erro (refazer antes de montar).
Relatório: continuidade.md na pasta do projeto.
"""
import argparse
import base64
import datetime
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from producao import carregar, salvar, tomada  # noqa: E402
from tts_gemini import URL, chave  # noqa: E402

PEDIDO = """Você é supervisor de continuidade de um filme de animação. Compare as IMAGENS DA TOMADA com as REFERÊNCIAS
(fichas de personagem e cenário) e com a bíblia abaixo. Seja rigoroso com identidade e figurino; ignore diferenças
normais de ângulo, expressão, pose e iluminação dramática pedida pela cena.
Bíblia desta tomada:
{biblia}
Para cada item da lista de checagem, diga o que era esperado, o que você vê e se bate. gravidade: "leve" (detalhe que
ninguém nota), "media" (o público pode notar), "grave" (personagem/roupa/objeto errado ou faltando, cenário trocado).
Item que não aparece por causa do enquadramento (ex.: pés fora de um plano médio) NÃO é erro: ok=true, visto "fora de quadro".
Itens: {itens}
Também aponte problemas de IA visíveis (mãos deformadas, rosto distorcido, texto/letras inventadas, logotipos), cada um
com gravidade: "leve" (só se nota pausando o vídeo), "media" (nota-se assistindo), "grave" (estraga a tomada).
{nota_clipe}
Responda só JSON: {{"itens": [{{"item": "...", "esperado": "...", "visto": "...", "ok": true, "gravidade": "leve"}}],
"problemas_ia": [{{"problema": "...", "gravidade": "leve"}}], "resumo": "1 frase em português"}}"""


def b64(arq):
    return base64.b64encode(open(arq, "rb").read()).decode()


def mime(arq):
    return "image/png" if arq.lower().endswith(".png") else "image/jpeg"


def quadros_do_clipe(arq, pasta):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                               capture_output=True, text=True).stdout.strip() or 0)
    saida = []
    for i, t in enumerate((0.1, dur / 2, max(0, dur - 0.15))):
        q = os.path.join(pasta, f"q{i}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", arq, "-frames:v", "1", "-vf", "scale=640:-2", q], check=True)
        saida.append(q)
    return saida


def montar_checagem(d, t):
    linhas, itens = [], []
    for pid in t.get("personagens", []):
        p = d["personagens"].get(pid, {})
        linhas.append(f"- personagem {p.get('nome', pid)}: {p.get('descricao', '')}")
        itens += [f"{p.get('nome', pid)} — rosto igual à ficha"] + [f"{p.get('nome', pid)} — {x}" for x in p.get("tracos", [])]
        itens += [f"{p.get('nome', pid)} — {k}: {v}" for k, v in (p.get("figurino") or {}).items()]
    for oid in t.get("objetos", []):
        o = d["objetos"].get(oid, {})
        linhas.append(f"- objeto: {o.get('descricao', oid)}")
        itens.append(f"objeto: {o.get('descricao', oid)}")
    c = d["cenarios"].get(t.get("cenario", ""), {})
    if c:
        linhas.append(f"- cenário: {c.get('descricao', '')}; luz: {c.get('luz', '')}")
        itens += [f"cenário: {c.get('descricao', '')}", f"luz: {c.get('luz', '')}"]
    if t.get("acao"):
        linhas.append(f"- ação pedida: {t['acao']}")
        itens.append("a ação pedida aparece")
    return "\n".join(linhas), itens


def referencias(d, t, raiz, alvo):
    refs = []
    for pid in t.get("personagens", []):
        f = d["personagens"].get(pid, {}).get("ficha")
        if f:
            refs.append((f"ficha de {d['personagens'][pid].get('nome', pid)}", os.path.join(raiz, f)))
    c = d["cenarios"].get(t.get("cenario", ""), {})
    if c.get("ref") and os.path.abspath(os.path.join(raiz, c["ref"])) != os.path.abspath(alvo):
        refs.append(("referência do cenário", os.path.join(raiz, c["ref"])))
    # tomada anterior aprovada no mesmo cenário (encaixe entre cortes)
    anteriores = [x for x in d["tomadas"] if x["id"] < t["id"] and x.get("cenario") == t.get("cenario") and x["status"] == "aprovada"]
    for x in anteriores[-1:]:
        img = next((v["arquivo"] for v in reversed(x["versoes"]) if v["tipo"] == "imagem"), None)
        if img:
            refs.append((f"tomada anterior {x['id']} (mesmo cenário)", os.path.join(raiz, img)))
    return [(n, a) for n, a in refs if os.path.exists(a)]


def checar(d, t, raiz, arquivo):
    biblia, itens = montar_checagem(d, t)
    with tempfile.TemporaryDirectory() as tmp:
        imgs = quadros_do_clipe(arquivo, tmp) if arquivo.lower().endswith((".mp4", ".mov", ".webm")) else [arquivo]
        nota = ("As imagens da tomada são quadros CONGELADOS de um clipe que o público vê em movimento no celular: "
                "deformação pequena que aparece em um quadro só (dedos, cordas, fios) é 'leve'." if len(imgs) > 1 else "")
        partes = [{"text": PEDIDO.format(biblia=biblia, itens="; ".join(itens), nota_clipe=nota)}]
        for nome, ref in referencias(d, t, raiz, arquivo):
            partes += [{"text": f"REFERÊNCIA — {nome}:"}, {"inline_data": {"mime_type": mime(ref), "data": b64(ref)}}]
        for i, im in enumerate(imgs):
            partes += [{"text": f"IMAGEM DA TOMADA {t['id']} ({i + 1}/{len(imgs)}):"}, {"inline_data": {"mime_type": mime(im), "data": b64(im)}}]
        corpo = {"contents": [{"parts": partes}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}
        req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
    res["problemas_ia"] = [p if isinstance(p, dict) else {"problema": str(p), "gravidade": "media"} for p in res.get("problemas_ia", [])]
    erros = [i for i in res.get("itens", []) if not i.get("ok") and i.get("gravidade") in ("media", "grave")]
    erros += [p for p in res["problemas_ia"] if p.get("gravidade") in ("media", "grave")]
    res["ok"] = not erros
    res["quando"] = datetime.datetime.now().isoformat(timespec="seconds")
    return res


def linha(t, v, res):
    falhas = [f"{i['item']}: esperado {i['esperado']}, visto {i['visto']} ({i.get('gravidade')})"
              for i in res.get("itens", []) if not i.get("ok")]
    falhas += [f"IA: {p['problema']} ({p.get('gravidade')})" for p in res.get("problemas_ia", [])]
    marca = "✅" if not falhas else ("⚠️" if res.get("ok") else "❌")
    return f"| {t['id']} v{v.get('v', '—')} | {v.get('arquivo', '')} | {marca} {res.get('resumo', '')} | {'<br>'.join(falhas) or '—'} |"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tomadas", nargs="*")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--refazer", action="store_true", help="com --todas, checa de novo o que já foi checado")
    ap.add_argument("--arquivo", help="arquivo avulso (não grava na bíblia)")
    ap.add_argument("--projeto")
    a = ap.parse_args()
    arq, d = carregar(a.projeto)
    raiz = os.path.dirname(arq)
    alvos = [tomada(d, x) for x in a.tomadas] if a.tomadas else (d["tomadas"] if a.todas else [])
    if not alvos:
        ap.error("diga as tomadas (t001 …) ou --todas")
    linhas = ["| tomada | arquivo | resultado | o que não bateu |", "|---|---|---|---|"]
    for t in alvos:
        if a.arquivo:
            v = {"arquivo": a.arquivo}
        else:
            v = next((x for x in reversed(t["versoes"]) if x["tipo"] in ("imagem", "clipe")), None)
            if not v or (a.todas and v.get("continuidade") and not a.refazer):
                continue
        res = checar(d, t, raiz, os.path.join(raiz, v["arquivo"]))
        if not a.arquivo:
            v["continuidade"] = res
            if not res["ok"] and t["status"] != "aprovada":
                t["status"] = "refazer"
        linhas.append(linha(t, v, res))
        print(linhas[-1])
    if not a.arquivo:
        salvar(arq, d, f"continuidade: {len(linhas) - 2} checagens")
    rel = os.path.join(raiz, "continuidade.md")
    open(rel, "w", encoding="utf-8").write("# Continuidade\n\n" + "\n".join(linhas) + "\n")
    print(f"\nRelatório: {rel}")


if __name__ == "__main__":
    main()
