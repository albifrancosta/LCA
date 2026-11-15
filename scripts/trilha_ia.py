"""Trilha sonora gerada por IA conforme o conteúdo do vídeo (fal.ai). Mostra o custo antes de gastar.

Uso (na pasta do projeto):
  # 1) plano (grátis): o Gemini lê as falas e divide a trilha em blocos de clima (dor, virada, solução, assinatura)
  python trilha_ia.py --falas falas.json --duracao 58 --contexto "anúncio MinhaMarca, dor → solução" -o assets/trilha-ia.wav
  # 2) revise/edite assets/trilha-ia.wav.plano.json se quiser e gere de verdade:
  python trilha_ia.py --plano assets/trilha-ia.wav.plano.json --duracao 58 --modelo elevenlabs --confirmar -o assets/trilha-ia.wav
  # opções para escolher (cada uma é uma geração paga):  --opcoes 3   → trilha-ia-1.wav, -2.wav, -3.wav
  # algo falhou depois de pagar:  python trilha_ia.py --recuperar -o assets/trilha-ia.wav

Modelos (preço oficial do fal, consultado em 2026-11-05):
  elevenlabs → fal-ai/elevenlabs/music · US$ 0,60/min · plano de composição com partes de duração exata (a virada cai no corte certo)
  ace        → fal-ai/ace-step         · US$ 0,0002/s  · uma geração por bloco, emendadas com crossfade — barato, bom para testar
Sempre instrumental (a narração manda). Saída: WAV 44,1 kHz estéreo, exatamente com a duração do vídeo, −20 LUFS,
pronto para `mixar_comercial.py --trilha <saída>` (que abaixa a música quando há fala).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gerar_clipe_fal import baixar, pedir  # noqa: E402  (mesma chave FAL_KEY, mesma proteção contra reenvio pago)

MODELOS = {
    "elevenlabs": ("fal-ai/elevenlabs/music", lambda seg: 0.60 * seg / 60),
    "ace": ("fal-ai/ace-step", lambda seg: 0.0002 * seg),
}
SOBRA = 2.0  # segundos a mais em cada bloco do ace, para o crossfade
MIN_BLOCO = 3.0  # limite do ElevenLabs por parte

PEDIDO_PLANO = """You are a music supervisor for short vertical social videos (Reels/TikTok) in Brazil.
Given the narration lines below (with start/end seconds and voice tone), split the BACKGROUND MUSIC of a {dur:.1f}-second video
into 2–5 contiguous blocks that follow the story (e.g. pain/tension → turning point → solution/confidence → brand ending).
Put block boundaries exactly at narrative turns (a long pause, a black screen, "Agora imagina…", the brand sign-off).
Rules: instrumental only; never compete with the voice (no busy leads, no vocals); each block ≥ 3 s; first block starts at 0,
last ends at {dur:.1f}; modern, commercial, not cheesy. Context: {ctx}
Return JSON only:
{{"estilo_global": ["english style tags for the whole track"], "negativo": ["vocals", "singing"],
  "blocos": [{{"nome": "short name", "de": 0.0, "ate": 22.4, "clima": "mood in Portuguese (2-4 words)",
              "estilos": ["english tags: instruments, energy, texture"], "bpm": 90}}]}}

LINES:
{falas}"""


def gemini_plano(falas, duracao, contexto):
    from tts_gemini import chave as chave_gemini
    falas = sorted(falas, key=lambda f: f.get("inicio", 0))
    for i, f in enumerate(falas):  # falas.json da timeline pode não ter "fim": usa o início da próxima
        if not f.get("fim"):
            f["fim"] = falas[i + 1]["inicio"] - 0.3 if i + 1 < len(falas) else duracao
    linhas ="\n".join(f'{f.get("inicio", 0):.1f}-{f.get("fim", 0):.1f}s [{f.get("tom") or "-"}] {f.get("quem", "narrador")}: {f.get("texto", "")}' for f in falas)
    corpo = {"contents": [{"parts": [{"text": PEDIDO_PLANO.format(dur=duracao, ctx=contexto or "-", falas=linhas)}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.6}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": chave_gemini()})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    return json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])


def ajustar(plano, duracao):
    """Garante blocos contíguos de 0 até a duração, cada um com ≥ 3 s."""
    b = sorted(plano["blocos"], key=lambda x: float(x["de"]))
    for i, x in enumerate(b):
        x["de"] = 0.0 if i == 0 else b[i - 1]["ate"]
        x["ate"] = float(duracao) if i == len(b) - 1 else max(float(x["ate"]), x["de"] + MIN_BLOCO)
    juntos = []
    for x in b:  # bloco curto demais se junta ao anterior
        if juntos and x["ate"] - x["de"] < MIN_BLOCO:
            juntos[-1]["ate"] = x["ate"]
        else:
            juntos.append(x)
    plano["blocos"] = juntos
    plano.setdefault("negativo", [])
    for n in ("vocals", "singing", "lyrics"):
        if n not in plano["negativo"]:
            plano["negativo"].append(n)
    return plano


def mostrar(plano):
    print("Plano da trilha:")
    for x in plano["blocos"]:
        print(f'  {x["de"]:5.1f}–{x["ate"]:5.1f} s  {x["nome"]:<14} {x.get("clima", ""):<24} {x.get("bpm", "")} bpm · {", ".join(x.get("estilos", []))}')
    print("  estilo geral:", ", ".join(plano.get("estilo_global", [])))


def esperar_e_baixar(fila, arquivo):
    t0 = time.time()
    while pedir(fila["status_url"]).get("status") != "COMPLETED":
        if time.time() - t0 > 900:
            sys.exit(f"tempo esgotado; pedido {fila.get('request_id')} continua no fal — use --recuperar")
        time.sleep(4)
    r = pedir(fila["response_url"])
    url = (r.get("audio") or r.get("audio_file") or {}).get("url")
    if not url:
        sys.exit(f"resposta sem áudio: {str(r)[:300]}")
    baixar(url, arquivo)


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def finalizar(entrada, saida, duracao):
    """Corta/estende para a duração exata, fade de entrada e saída, normaliza para −20 LUFS."""
    ff("-i", entrada, "-af", f"apad,atrim=0:{duracao},afade=t=in:d=0.3,afade=t=out:st={max(0, duracao - 2.0)}:d=2.0,loudnorm=I=-20:TP=-2:LRA=11",
       "-ar", "44100", "-ac", "2", saida)


def emendar(partes, plano, pasta):
    """Emenda os blocos do ace: cada um cortado no seu tempo + crossfade curto (0,6 s) na troca."""
    cortadas = []
    for i, (arq, x) in enumerate(zip(partes, plano["blocos"])):
        dur = x["ate"] - x["de"] + (0.6 if i < len(partes) - 1 else 0)
        c = os.path.join(pasta, f"corte{i}.wav")
        ff("-i", arq, "-af", f"atrim=0:{dur}", "-ar", "44100", "-ac", "2", c)
        cortadas.append(c)
    atual = cortadas[0]
    for i, c in enumerate(cortadas[1:], 1):
        prox = os.path.join(pasta, f"emenda{i}.wav")
        ff("-i", atual, "-i", c, "-filter_complex", "acrossfade=d=0.6:c1=tri:c2=tri", prox)
        atual = prox
    return atual


def registrar(manifesto, saida, n, parte, fila):
    # grava o pedido já pago ANTES de esperar: se algo cair, --recuperar baixa sem pagar de novo
    manifesto["pedidos"].append({"opcao": n, "parte": parte, "request_id": fila.get("request_id"), "status_url": fila["status_url"], "response_url": fila["response_url"]})
    json.dump(manifesto, open(saida + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def gerar_uma(plano, modelo, duracao, saida_base, destino, n, manifesto):
    modelo_id = MODELOS[modelo][0]
    tmp = tempfile.mkdtemp(prefix="trilha_")
    if modelo == "elevenlabs":
        corpo = {"composition_plan": {
            "positive_global_styles": plano.get("estilo_global", []) + ["instrumental"],
            "negative_global_styles": plano["negativo"],
            "sections": [{"section_name": x["nome"][:100], "duration_ms": int(round((x["ate"] - x["de"]) * 1000)), "lines": [],
                          "positive_local_styles": [s for s in x.get("estilos", []) + ([f'{x["bpm"]} bpm'] if x.get("bpm") else []) if s],
                          "negative_local_styles": []} for x in plano["blocos"]]},
            "respect_sections_durations": True, "output_format": "mp3_44100_128"}
        fila = pedir(f"https://queue.fal.run/{modelo_id}", corpo)
        registrar(manifesto, saida_base, n, 0, fila)
        bruto = os.path.join(tmp, "eleven.mp3")
        esperar_e_baixar(fila, bruto)
    else:
        partes = []
        for i, x in enumerate(plano["blocos"]):
            tags = ", ".join(plano.get("estilo_global", []) + x.get("estilos", []) + ([f'{x["bpm"]} bpm'] if x.get("bpm") else []) + ["instrumental"])
            corpo = {"tags": tags, "lyrics": "[inst]", "duration": round(x["ate"] - x["de"] + SOBRA, 1)}
            fila = pedir(f"https://queue.fal.run/{modelo_id}", corpo)
            registrar(manifesto, saida_base, n, i, fila)
            arq = os.path.join(tmp, f"parte{i}.wav")
            esperar_e_baixar(fila, arq)
            partes.append(arq)
        bruto = emendar(partes, plano, tmp)
    finalizar(bruto, destino, duracao)


def nome_opcao(saida, n, total):
    if total == 1:
        return saida
    raiz, ext = os.path.splitext(saida)
    return f"{raiz}-{n}{ext}"


def recuperar(saida):
    """Baixa de novo o que já foi pago (sem novo custo) e remonta as opções."""
    man = json.load(open(saida + ".json", encoding="utf-8"))
    plano, modelo, duracao, total = man["plano"], man["modelo"], man["duracao"], man["opcoes"]
    for n in range(1, total + 1):
        peds = sorted((p for p in man["pedidos"] if p["opcao"] == n), key=lambda p: p["parte"])
        if not peds:
            continue
        tmp = tempfile.mkdtemp(prefix="trilha_rec_")
        arqs = []
        for p in peds:
            arq = os.path.join(tmp, f"p{p['parte']}" + (".mp3" if modelo == "elevenlabs" else ".wav"))
            esperar_e_baixar(p, arq)
            arqs.append(arq)
        bruto = arqs[0] if modelo == "elevenlabs" else emendar(arqs, plano, tmp)
        finalizar(bruto, nome_opcao(saida, n, total), duracao)
        print("recuperado sem novo custo:", nome_opcao(saida, n, total))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--falas", help="falas.json com inicio, fim, texto e tom (para o Gemini montar o plano)")
    ap.add_argument("--plano", help="plano já pronto/editado (pula o Gemini)")
    ap.add_argument("--duracao", type=float)
    ap.add_argument("--contexto", default="")
    ap.add_argument("--modelo", default="elevenlabs", choices=list(MODELOS))
    ap.add_argument("--opcoes", type=int, default=1, help="quantas versões gerar para escolher")
    ap.add_argument("--confirmar", action="store_true", help="sem isto só mostra o plano e o custo")
    ap.add_argument("--recuperar", action="store_true")
    a = ap.parse_args()

    if a.recuperar:
        return recuperar(a.saida)
    if not a.duracao:
        sys.exit("informe --duracao (segundos do vídeo)")
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    if a.plano:
        plano = json.load(open(a.plano, encoding="utf-8"))
    elif a.falas:
        plano = gemini_plano(json.load(open(a.falas, encoding="utf-8")), a.duracao, a.contexto)
    else:
        sys.exit("informe --falas (plano automático) ou --plano")
    plano = ajustar(plano, a.duracao)
    caminho_plano = a.saida + ".plano.json"
    json.dump(plano, open(caminho_plano, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mostrar(plano)
    seg = a.duracao if a.modelo == "elevenlabs" else sum(x["ate"] - x["de"] + SOBRA for x in plano["blocos"])
    total = MODELOS[a.modelo][1](seg) * a.opcoes
    print(f"\nModelo {a.modelo} ({MODELOS[a.modelo][0]}) · {a.opcoes} opção(ões) · custo estimado US$ {total:.2f}")
    print(f"Plano salvo em {caminho_plano}")
    if not a.confirmar:
        print("Nada foi gerado. Para gerar de verdade, rode de novo com --confirmar.")
        return
    manifesto = {"modelo": a.modelo, "duracao": a.duracao, "opcoes": a.opcoes, "plano": plano, "custo_estimado": round(total, 4), "pedidos": []}
    for n in range(1, a.opcoes + 1):
        destino = nome_opcao(a.saida, n, a.opcoes)
        print(f"gerando opção {n}…")
        gerar_uma(plano, a.modelo, a.duracao, a.saida, destino, n, manifesto)
        from custos import registrar
        registrar("trilha", MODELOS[a.modelo][0], total / a.opcoes, os.path.basename(destino), "fal API (preço oficial)")
        print("  pronto:", destino)


if __name__ == "__main__":
    main()
