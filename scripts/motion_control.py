"""Motion control (fal.ai, vídeo → vídeo): TROCAR o personagem de um vídeo ou fazer um personagem COPIAR o movimento de um vídeo.

Uso:
  # tabela de custos para a entrevista (nada é gerado): quanto custa cada modelo para este trecho
  python motion_control.py --custos --video meu-video.mp4 [--inicio 2 --duracao 5]
  # trocar o personagem (mantém cenário, câmera e movimento do vídeo) — você grava, vira o dono/técnico da biblioteca
  python motion_control.py --modo trocar --video eu-atendendo.mp4 --personagem ficha-dono.png -o assets/clips/m1.mp4 [--duracao 5] --confirmar
  # copiar o movimento (personagem e cenário vêm da IMAGEM; os gestos vêm do vídeo)
  python motion_control.py --modo mover --video eu-apontando.mp4 --personagem robo-joinha.png -o assets/clips/m2.mp4 [--modelo auto|<id>] --confirmar
  # algo falhou depois de pagar
  python motion_control.py --recuperar assets/clips/m1.mp4

Modelos (catálogo oficial, `catalogo.py`): trocar = Wan 2.2 Animate Replace · mover = Wan 2.2 Animate Move, Kling 2.6 Motion Control Standard/Pro.
Preço por segundo do trecho enviado → o script CORTA o vídeo (`--inicio`, `--duracao`, máx. 10 s) e reduz para 720p antes de enviar.
Sem --confirmar só mostra modelo, motivo e custo. Cache: o mesmo vídeo + personagem + trecho + modelo não é pago duas vezes. Gasto vai para `custos.py`.
Regras: só vídeos do próprio usuário ou com autorização de quem aparece; uma pessoa por vez, corpo visível, fundo simples funciona melhor.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gerar_clipe_fal import baixar, data_uri, pedir  # noqa: E402

MODOS = {"trocar": "trocar o personagem do vídeo", "mover": "personagem da imagem copia o movimento do vídeo"}


def duracao_video(arq):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def preparar(video, inicio, dur):
    """Corta o trecho e reduz (720p no lado menor, H.264) — o preço é por segundo e o envio vai em data URI."""
    tmp = os.path.join(tempfile.mkdtemp(prefix="motion_"), "trecho.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(inicio), "-t", str(dur), "-i", video,
                    "-vf", "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'", "-c:v", "libx264", "-crf", "26", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "96k", tmp], check=True)
    return tmp


def video_uri(arq):
    return f"data:video/mp4;base64,{base64.b64encode(open(arq, 'rb').read()).decode()}"


def tabela(modo, dur):
    from roteador import escolher
    linhas = []
    for md in ([modo] if modo else list(MODOS)):
        _, cands = escolher("motion", dur, "personagem", False, "economico", None, registrar=False, modo=md)
        linhas += [(md, c) for c in cands]
    return linhas


def corpo_para(modelo, imagem, trecho, orientacao, manter_som, resolucao):
    corpo = {"image_url": data_uri(imagem), "video_url": video_uri(trecho)}
    if "kling" in modelo:
        corpo["character_orientation"] = orientacao
        corpo["keep_original_sound"] = manter_som
    else:  # Wan Animate
        corpo["resolution"] = resolucao
        corpo["video_quality"] = "high"
    return corpo


def recuperar(saida):
    meta = json.load(open(saida + ".json", encoding="utf-8"))
    baixar(pedir(meta["response_url"])["video"]["url"], saida)
    if meta.get("cache_chave"):
        from custos import cache_guardar
        cache_guardar("motion", meta["cache_chave"], saida)
    print(f"recuperado sem novo custo: {saida}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="vídeo de referência (seu, ou com autorização de quem aparece)")
    ap.add_argument("--personagem", help="imagem do personagem (ex.: ficha da biblioteca, robô)")
    ap.add_argument("--modo", choices=list(MODOS))
    ap.add_argument("-o", "--saida")
    ap.add_argument("--modelo", default="auto", help="'auto' (roteador) ou id do catálogo")
    ap.add_argument("--perfil", default="economico", choices=["economico", "equilibrado", "premium"])
    ap.add_argument("--orcamento", type=float)
    ap.add_argument("--inicio", type=float, default=0.0)
    ap.add_argument("--duracao", type=float, help="segundos do trecho (padrão: o vídeo todo, máx. 10)")
    ap.add_argument("--orientacao", default="video", choices=["video", "image"], help="Kling: personagem vira para onde o vídeo/imagem manda")
    ap.add_argument("--manter-som", action="store_true", help="Kling: mantém o som original do vídeo")
    ap.add_argument("--resolucao", default="720p", choices=["480p", "580p", "720p"], help="Wan Animate")
    ap.add_argument("--custos", action="store_true", help="só a tabela de custos (para a entrevista)")
    ap.add_argument("--confirmar", action="store_true")
    ap.add_argument("--recuperar", metavar="SAIDA.mp4")
    a = ap.parse_args()
    if a.recuperar:
        return recuperar(a.recuperar)
    if not a.video:
        ap.error("informe --video")
    total = duracao_video(a.video)
    dur = round(min(a.duracao or (total - a.inicio), 10.0, total - a.inicio), 2)

    if a.custos:
        print(f"Motion control · trecho de {dur:.1f} s (a partir de {a.inicio:.1f} s) · preços oficiais do catálogo")
        for md, c in tabela(a.modo, dur):
            print(f"  {MODOS[md]:<48} {c['modelo']:<48} US$ {c['preco']:.2f}  (q{c['q']})")
        return
    if not (a.personagem and a.modo and a.saida):
        ap.error("informe --personagem, --modo e -o (ou use --custos)")

    from roteador import escolher, preco_duracao
    from gerar_clipe_fal import modelo_catalogo
    if a.modelo == "auto":
        dec, _ = escolher("motion", dur, "personagem", False, a.perfil, a.orcamento, modo=a.modo)
        if not dec["modelo"]:
            sys.exit(f"roteador: {dec['motivo']}")
        modelo, motivo = dec["modelo"], dec["motivo"]
    else:
        modelo, motivo = a.modelo, "modelo fixo"
    m = modelo_catalogo(modelo)
    if not m or m.get("tipo") != "motion" or a.modo not in (m.get("recursos") or {}).get("modos", []):
        sys.exit(f"{modelo} não faz '{a.modo}' — veja --custos")
    preco = preco_duracao(m, dur)[0]
    if preco is None:
        sys.exit(f"{modelo}: preço desconhecido para {dur:.1f} s (ou duração não suportada) — nada foi gasto; atualize o catálogo (catalogo.py)")
    preco = round(preco, 4)
    if a.orcamento is not None and preco > a.orcamento:
        sys.exit(f"US$ {preco:.2f} passa do teto de US$ {a.orcamento}")
    print(f"{MODOS[a.modo]} · {dur:.1f} s · {modelo} · US$ {preco:.2f}\n  {motivo}")
    if not a.confirmar:
        print("Nada foi gerado. Rode de novo com --confirmar para gastar os créditos.")
        return

    from custos import cache_buscar, cache_chave, cache_guardar, registrar
    k = cache_chave("motion", modelo=modelo, modo=a.modo, video=a.video, personagem=a.personagem, inicio=a.inicio, duracao=dur,
                    orientacao=a.orientacao, som=a.manter_som, resolucao=a.resolucao)
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    achado = cache_buscar("motion", k, ".mp4")
    if achado:
        shutil.copyfile(achado, a.saida)
        registrar("motion", modelo, preco, f"{os.path.basename(a.saida)} (cache)", "catálogo fal", cache=True)
        print(f"cache: já gerado antes → {a.saida} (US$ 0)")
        return
    trecho = preparar(a.video, a.inicio, dur)
    fila = pedir(f"https://queue.fal.run/{modelo}", corpo_para(modelo, a.personagem, trecho, a.orientacao, a.manter_som, a.resolucao))
    json.dump({"modelo": modelo, "modo": a.modo, "video": a.video, "personagem": a.personagem, "inicio": a.inicio, "duracao": dur,
               "custo_estimado": preco, "request_id": fila.get("request_id"), "response_url": fila["response_url"], "cache_chave": k},
              open(a.saida + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  pedido {fila.get('request_id')} enviado; aguardando…")
    t0 = time.time()
    while pedir(fila["status_url"]).get("status") != "COMPLETED":
        if time.time() - t0 > 1200:
            sys.exit("tempo esgotado; o pedido continua no fal — use --recuperar")
        time.sleep(6)
    baixar(pedir(fila["response_url"])["video"]["url"], a.saida)
    cache_guardar("motion", k, a.saida)
    registrar("motion", modelo, preco, f"{os.path.basename(a.saida)} · {a.modo} · {dur:.1f} s", "catálogo fal (API oficial)")
    print(f"pronto em {time.time() - t0:.0f}s → {a.saida}")


if __name__ == "__main__":
    main()
