"""Espectador: o Gemini ASSISTE ao vídeo (imagem + som) no lugar do público e conta, segundo a segundo, o que sentiu —
onde riu, onde se confundiu, onde arrastaria para o próximo vídeo — e os problemas técnicos que viu ou ouviu.
Grátis dentro da cota do Gemini. Não substitui a aprovação do usuário: filtra antes de ele ver.

Uso:
  python espectador.py out/video.mp4 [--briefing BRIEFING.md] [--personas alvo,impaciente,critico] [-o entrega/espectador.md]
Personas (padrão as 3):
  alvo        — o público do briefing, rolando o feed no celular
  impaciente  — arrasta em 2 s se nada acontece; o teste de retenção
  critico     — diretor de animação: ritmo, tempo cômico, continuidade, som, legenda
Saída: relatório .md + .json ao lado (nota 0–10 por persona, curva de interesse, onde sairia, risos, confusões,
problemas técnicos com o segundo exato, 3 ajustes). Vídeo > 18 MB sobe pela API de arquivos do Gemini.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from tts_gemini import URL, chave  # noqa: E402

BASE = "https://generativelanguage.googleapis.com"
PERSONAS = {
    "alvo": "Você é o público-alvo deste vídeo ({publico}), rolando o feed do Instagram/TikTok no celular, com som ligado, "
            "sem pressa mas sem paciência para enrolação. Reaja com honestidade, como pessoa comum.",
    "impaciente": "Você é um espectador impaciente de vídeos curtos: se em 2 segundos nada novo acontece, você arrasta para o "
                  "próximo. Diga exatamente em que segundo você sairia e por quê.",
    "critico": "Você é diretor de animação e editor experiente. Avalie ritmo, tempo cômico/dramático, clareza da história, "
               "continuidade dos personagens, qualidade das imagens, mixagem (voz × música × ambiente), legenda e o final.",
}
PEDIDO = """{persona}
Contexto do vídeo (do briefing): {contexto}
Assista ao vídeo inteiro, com o som. Responda só JSON:
{{"nota": 0-10, "entendeu": "o que você entendeu da história, 1 frase", "sairia_em": segundo ou null,
"trechos": [{{"de": s, "ate": s, "interesse": 1-10, "emocao": "…", "pularia": true/false, "por_que": "…"}}],
"riu": [{{"tempo": s, "do_que": "…"}}], "confuso": [{{"tempo": s, "o_que": "…"}}],
"tecnico": [{{"tempo": s, "tipo": "legenda|audio|imagem|continuidade|sincronia|texto", "descricao": "…", "gravidade": "leve|media|grave"}}],
"compartilharia": "sim/não e para quem", "ajustes": ["3 mudanças concretas, a mais importante primeiro"]}}
Trechos de 2 a 5 s cobrindo o vídeo todo. Tempos em segundos do vídeo. Português do Brasil."""


def pedir(url, corpo=None, cabecalhos=None, metodo=None):
    req = urllib.request.Request(url, data=corpo, headers={"x-goog-api-key": chave(), **(cabecalhos or {})}, method=metodo)
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.headers, r.read()


def subir(arq):
    """API de arquivos (upload resumable) → file_uri, esperando ficar ACTIVE."""
    tam = os.path.getsize(arq)
    h, _ = pedir(f"{BASE}/upload/v1beta/files", json.dumps({"file": {"display_name": os.path.basename(arq)}}).encode(),
                 {"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                  "X-Goog-Upload-Header-Content-Length": str(tam), "X-Goog-Upload-Header-Content-Type": "video/mp4",
                  "Content-Type": "application/json"}, "POST")
    _, corpo = pedir(h["X-Goog-Upload-URL"], open(arq, "rb").read(),
                     {"X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0", "Content-Length": str(tam)}, "POST")
    f = json.loads(corpo)["file"]
    while f.get("state") == "PROCESSING":
        time.sleep(3)
        _, corpo = pedir(f"{BASE}/v1beta/{f['name']}")
        f = json.loads(corpo)
    if f.get("state") != "ACTIVE":
        sys.exit(f"o Gemini não conseguiu processar o vídeo: {f.get('state')}")
    return {"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}


def assistir(parte_video, persona, contexto, publico):
    texto = PEDIDO.format(persona=PERSONAS[persona].format(publico=publico), contexto=contexto)
    corpo = {"contents": [{"parts": [parte_video, {"text": texto}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}
    _, r = pedir(URL.format(m="gemini-3.8-flash"), json.dumps(corpo).encode(), {"Content-Type": "application/json"}, "POST")
    return json.loads(json.loads(r)["candidates"][0]["content"]["parts"][0]["text"])


def contexto_do_briefing(arq):
    if not arq or not os.path.exists(arq):
        return "vídeo curto para redes sociais", "público geral de redes sociais"
    t = open(arq, encoding="utf-8").read()
    publico = next((l.split(":", 1)[1].strip(" *") for l in t.splitlines() if "Público" in l and ":" in l), "público geral")
    return t[:2500], publico[:200]


def relatorio(video, res):
    L = [f"# Espectador — {os.path.basename(video)}", ""]
    L.append("| persona | nota | sairia em | entendeu | compartilharia |\n|---|---|---|---|---|")
    for p, r in res.items():
        L.append(f"| {p} | {r.get('nota')} | {r.get('sairia_em') if r.get('sairia_em') is not None else 'não saiu'} | "
                 f"{r.get('entendeu', '')} | {r.get('compartilharia', '')} |")
    for p, r in res.items():
        L += ["", f"## {p}", "", "Curva de interesse:", ""]
        for x in r.get("trechos", []):
            barra = "█" * int(x.get("interesse", 0))
            L.append(f"- {x.get('de', '?'):>5}–{x.get('ate', '?'):<5}s {barra:<10} {x.get('interesse')}/10 · {x.get('emocao', '')}"
                     f"{' · ⏭️ pularia' if x.get('pularia') else ''} — {x.get('por_que', '')}")
        if r.get("riu"):
            L += ["", "Riu: " + "; ".join(f"{x.get('tempo', '?')}s {x.get('do_que') or x.get('o_que') or x.get('descricao', '')}" for x in r["riu"])]
        if r.get("confuso"):
            L += ["", "Confuso: " + "; ".join(f"{x.get('tempo', '?')}s {x.get('o_que') or x.get('do_que') or x.get('descricao', '')}" for x in r["confuso"])]
        if r.get("tecnico"):
            L += ["", "Técnico:"] + [f"- {x.get('tempo', '?')}s [{x.get('tipo', '?')}, {x.get('gravidade', '?')}] {x.get('descricao', '')}" for x in r["tecnico"]]
        L += ["", "Ajustes:"] + [f"{i + 1}. {a}" for i, a in enumerate(r.get("ajustes", []))]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--briefing")
    ap.add_argument("--personas", default="alvo,impaciente,critico")
    ap.add_argument("-o", "--saida")
    a = ap.parse_args()
    contexto, publico = contexto_do_briefing(a.briefing)
    if os.path.getsize(a.video) <= 18 * 1024 * 1024:
        parte = {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(open(a.video, "rb").read()).decode()}}
    else:
        parte = subir(a.video)
    res = {}
    for p in [x.strip() for x in a.personas.split(",") if x.strip()]:
        if p not in PERSONAS:
            sys.exit(f"persona '{p}' não existe. Use: {', '.join(PERSONAS)}")
        print(f"  {p} assistindo…", file=sys.stderr)
        res[p] = assistir(parte, p, contexto, publico)
    saida = a.saida or os.path.join(os.path.dirname(os.path.abspath(a.video)), "espectador.md")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    json.dump({"video": a.video, "personas": res}, open(os.path.splitext(saida)[0] + ".json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)  # salva antes do relatório: nada se perde se o formato vier diferente
    open(saida, "w", encoding="utf-8").write(relatorio(a.video, res))
    for p, r in res.items():
        print(f"{p:11} nota {r.get('nota')}/10 · sairia em {r.get('sairia_em')} · {r.get('entendeu', '')[:80]}")
    print(f"Relatório: {saida}")


if __name__ == "__main__":
    main()
