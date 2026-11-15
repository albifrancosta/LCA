"""Catálogo de modelos com PREÇO OFICIAL e data — base do roteador de custos.

Uso:
  python catalogo.py                → atualiza memoria/catalogo-modelos.json (preços da API oficial do fal + recursos do schema)
  python catalogo.py --listar [tipo] → mostra o catálogo (tipo: video | imagem | musica | voz | local)

Fontes:
  - fal.ai: GET https://api.fal.ai/v1/models/pricing?endpoint_id=… (oficial, com a FAL_KEY) + schema OpenAPI de cada modelo
    (detecta: imagem→vídeo, primeiro/último quadro, durações e resoluções aceitas). Nunca inventa preço: sem resposta = "sem preço".
  - OpenAI imagens e Gemini TTS: sem API de preço → valores anotados com data e fonte (marcados "anotado").
  - Local (Remotion, trilha_gratis, som_pro, faster-whisper): custo 0.
`qualidade_base` (1 = econômico, 2 = bom, 3 = topo) é a estimativa inicial; o histórico de aprovações (roteador.py) corrige.
Para incluir um provedor novo: acrescente em CANDIDATOS (fal) ou ANOTADOS (outros) — o roteador lê tudo daqui.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memoria", "catalogo-modelos.json")

# id no fal → (tipo, qualidade_base, nota)
CANDIDATOS = {
    "fal-ai/minimax/hailuo-02/standard/image-to-video": ("video", 2, "Hailuo 02 Standard 768p — barato, bom em movimento simples"),
    "fal-ai/minimax/hailuo-02/pro/image-to-video": ("video", 3, "Hailuo 02 Pro 1080p"),
    "fal-ai/wan-25-preview/image-to-video": ("video", 2, "Wan 2.5 — barato"),
    "fal-ai/wan/v2.2-a14b/image-to-video": ("video", 2, "Wan 2.2 A14B"),
    "fal-ai/wan/v2.2-5b/image-to-video": ("video", 1, "Wan 2.2 5B — preço por vídeo, qualidade menor"),
    "fal-ai/kling-video/v2.1/standard/image-to-video": ("video", 2, "Kling 2.1 Standard"),
    "fal-ai/kling-video/v2.5-turbo/pro/image-to-video": ("video", 3, "Kling 2.5 Turbo Pro — usado e aprovado no 'Cadê o técnico?'"),
    "fal-ai/kling-video/v2.1/pro/image-to-video": ("video", 3, "Kling 2.1 Pro"),
    "fal-ai/kling-video/v2.6/pro/image-to-video": ("video", 3, "Kling 2.6 Pro — atuação corporal boa, 1º e último quadro, US$ 0,07/s (2026-11-06)"),
    "fal-ai/kling-video/v3/pro/image-to-video": ("video", 3, "Kling 3 Pro — 3–15 s, 1º/último quadro, elements (referência de personagem), US$ 0,14/s"),
    # fala em quadro (lip-sync) — lipsync.py
    "fal-ai/kling-video/ai-avatar/v2/standard": ("lipsync", 2, "Kling AI Avatar v2 Std — imagem + áudio → personagem falando com gestos, US$ 0,056/s"),
    "fal-ai/kling-video/ai-avatar/v2/pro": ("lipsync", 3, "Kling AI Avatar v2 Pro — idem, mais qualidade, US$ 0,115/s"),
    "fal-ai/bytedance/omnihuman/v1.5": ("lipsync", 3, "OmniHuman 1.5 — imagem + áudio + prompt de ação, aceita cartoon, US$ 0,16/s"),
    "fal-ai/sync-lipsync/v2": ("lipsync", 3, "sync lipsync-2 — re-sincroniza a boca de um CLIPE já animado, US$ 3/min"),
    # foley — foley.py
    "fal-ai/mmaudio-v2": ("efeito", 2, "MMAudio v2 — gera o som A PARTIR do clipe (passos, batida, violão no tempo da imagem), US$ 0,001/s"),
    "fal-ai/elevenlabs/sound-effects/v2": ("efeito", 3, "ElevenLabs SFX v2 — efeito por descrição, US$ 0,002/s"),
    "fal-ai/bytedance/seedance/v1/lite/image-to-video": ("video", 2, "Seedance Lite — cobra por tokens (estimado)"),
    "fal-ai/bytedance/seedance/v1/pro/image-to-video": ("video", 3, "Seedance Pro — cobra por tokens (estimado)"),
    "fal-ai/ltxv-13b-098-distilled/image-to-video": ("video", 1, "LTX Video — muito barato, qualidade menor"),
    # motion control: trocar o personagem de um vídeo / fazer um personagem copiar o movimento de um vídeo
    "fal-ai/wan/v2.2-14b/animate/replace": ("motion", 2, "Wan 2.2 Animate Replace — TROCA o personagem do vídeo, mantém cenário e movimento"),
    "fal-ai/wan/v2.2-14b/animate/move": ("motion", 2, "Wan 2.2 Animate Move — personagem da imagem copia o movimento do vídeo"),
    "fal-ai/kling-video/v2.6/standard/motion-control": ("motion", 2, "Kling 2.6 Motion Control Standard — personagem/cenário da imagem com os gestos do vídeo"),
    "fal-ai/kling-video/v2.6/pro/motion-control": ("motion", 3, "Kling 2.6 Motion Control Pro — idem, mais qualidade"),
    "fal-ai/elevenlabs/music": ("musica", 3, "ElevenLabs Music — partes com duração exata"),
    "fal-ai/ace-step": ("musica", 2, "ACE-Step — barato, um bloco por geração"),
    "fal-ai/lyria2": ("musica", 2, "Lyria 2 — 30 s fixos"),
    "cassetteai/music-generator": ("musica", 1, "CassetteAI"),
    "fal-ai/flux/schnell": ("imagem", 1, "FLUX schnell — rascunho barato"),
    "fal-ai/nano-banana/edit": ("imagem", 3, "Nano Banana edit — consistência com referência"),
    "fal-ai/bytedance/seedream/v4/text-to-image": ("imagem", 2, "Seedream 4"),
}

# Sem API de preço: anotados (sempre com data e fonte; trate como estimativa)
ANOTADOS = [
    {"id": "openai/gpt-image-2.5-sunburst (medium 1024x1536)", "provedor": "openai", "tipo": "imagem", "preco_unidade": 0.05, "unidade": "imagem",
     "qualidade_base": 3, "nota": "padrão aprovado das ilustrações (personagem consistente com --ref)", "fonte": "anotado no perfil (medição da conta, 2026-11-03)"},
    {"id": "google/gemini-3.8-flash-tts", "provedor": "google", "tipo": "voz", "preco_unidade": 0, "unidade": "fala (cota 100/dia no Tier 1)",
     "qualidade_base": 3, "nota": "tom por fala, PT-BR; reserva lite quando a cota acaba", "fonte": "cota da conta do usuário"},
    {"id": "local/voicestudio (voz clonada)", "provedor": "local", "tipo": "voz", "preco_unidade": 0, "unidade": "fala", "qualidade_base": 2, "nota": "lento, sem tom", "fonte": "local"},
    {"id": "local/remotion-motion", "provedor": "local", "tipo": "local", "preco_unidade": 0, "unidade": "cena", "qualidade_base": 3,
     "nota": "texto, telas, gráficos, ícones, transições — SEMPRE antes de vídeo pago", "fonte": "local"},
    {"id": "local/trilha_gratis", "provedor": "local", "tipo": "musica", "preco_unidade": 0, "unidade": "trilha", "qualidade_base": 1, "nota": "sintetizada por blocos, batida exata", "fonte": "local"},
]


def chave():
    from gerar_clipe_fal import chave as k
    return k()


def get(url, auth=True, tentativas=5):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Key {chave()}"} if auth else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(3 * (n + 1))
                continue
            return None
        except urllib.error.URLError:
            time.sleep(3 * (n + 1))
    return None


def recursos(eid):
    d = get(f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={eid}", auth=False)
    if not d:
        return {}
    s = d.get("components", {}).get("schemas", {})
    inp = next((v for k, v in s.items() if k.endswith("Input")), {})
    props = inp.get("properties", {})
    nomes = set(props)

    def enum(nome):
        p = props.get(nome, {})
        return p.get("enum") or [x.get("const") for x in p.get("anyOf", []) if isinstance(x, dict) and "const" in x] or ([p["default"]] if "default" in p else [])
    return {
        "i2v": bool(nomes & {"image_url", "image_urls", "start_image_url"}),  # Kling 2.6/3 usam start_image_url
        "primeiro_ultimo_quadro": bool(nomes & {"end_image_url", "tail_image_url", "last_frame_url", "last_image_url"}),
        "duracoes": [str(x) for x in enum("duration")] or None,
        "resolucoes": [str(x) for x in enum("resolution")] or None,
        "parametros": sorted(nomes)[:30],
    }


def custo_5s(unit_price, unidade, tipo):
    u = (unidade or "").lower()
    if tipo not in ("video", "motion"):
        return None
    if u.startswith("second"):
        return round(unit_price * 5, 4)
    if u.startswith("video"):
        return round(unit_price, 4)
    if "token" in u:  # Seedance: tokens ≈ largura·altura·fps·duração/1024 (720p, 24 fps, 5 s ≈ 108 mil tokens) — ESTIMATIVA
        return round(unit_price * (1280 * 720 * 24 * 5 / 1024) / 1e6, 4)
    return None


def atualizar():
    hoje = datetime.date.today().isoformat()
    modelos = []
    for eid, (tipo, q, nota) in CANDIDATOS.items():
        d = get(f"https://api.fal.ai/v1/models/pricing?endpoint_id={eid}")
        preco = (d or {}).get("prices", [None])[0] if d else None
        time.sleep(1.2)
        rec = recursos(eid)
        if tipo == "motion":
            rec["modos"] = ["trocar"] if eid.endswith("/replace") else ["mover"]
        time.sleep(0.6)
        m = {"id": eid, "provedor": "fal", "tipo": tipo, "qualidade_base": q, "nota": nota, "recursos": rec,
             "fonte": "fal API /v1/models/pricing", "atualizado": hoje}
        if preco:
            m.update(preco_unidade=preco["unit_price"], unidade=preco["unit"], custo_5s=custo_5s(preco["unit_price"], preco["unit"], tipo))
        else:
            m.update(preco_unidade=None, unidade=None, custo_5s=None, nota=nota + " · SEM PREÇO OFICIAL (não usar no roteador até ter preço)")
        modelos.append(m)
        print(f"  {eid:<55} {m['preco_unidade']} /{m['unidade']}  i2v={rec.get('i2v')} ultimo_quadro={rec.get('primeiro_ultimo_quadro')}")
    for a in ANOTADOS:
        modelos.append(dict(a, atualizado=hoje, custo_5s=None, recursos={}))
    json.dump({"atualizado": hoje, "fonte": "fal API oficial + anotados", "modelos": modelos}, open(ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {ARQ}")


def listar(tipo=None):
    d = json.load(open(ARQ, encoding="utf-8"))
    print(f"Catálogo de {d['atualizado']} ({d['fonte']})")
    for m in sorted(d["modelos"], key=lambda m: (m["tipo"], m.get("custo_5s") or m.get("preco_unidade") or 0)):
        if tipo and m["tipo"] != tipo:
            continue
        preco = "sem preço" if m.get("preco_unidade") is None else f"US$ {m['preco_unidade']} /{m['unidade']}"
        c5 = f" · 5 s ≈ US$ {m['custo_5s']:.3f}" if m.get("custo_5s") else ""
        print(f"  [{m['tipo']:<6}] q{m['qualidade_base']} {m['id']:<52} {preco}{c5}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", nargs="?", const="", default=None)
    a = ap.parse_args()
    if a.listar is not None:
        listar(a.listar or None)
    else:
        atualizar()
