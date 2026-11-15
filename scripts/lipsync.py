"""Fala em quadro: o personagem que aparece falando mexe a boca NO TEMPO da fala (lip-sync), com gestos.

Três rotas (escolha pelo contrato do plano — contrato.py rotear):
  avatar      imagem do personagem + áudio da fala → vídeo falando com cabeça/ombros/mãos (Kling AI Avatar v2).
              Melhor custo para close/plano médio de diálogo. US$ 0,056/s (std) · 0,115/s (--pro).
  omnihuman   imagem + áudio + PROMPT DE AÇÃO → fala e atua (anda, aponta, chora). Aceita cartoon. US$ 0,16/s.
  sincronizar clipe JÁ animado (Kling/Seedance) + áudio → re-sincroniza só a boca (sync lipsync-2). US$ 3/min.
Narração em off (diário, narrador) NÃO usa lip-sync: o personagem atua de boca fechada (prompt do clipe).

Uso:
  python lipsync.py avatar --imagem p12.png --audio voz/p12.wav --prompt "nervoso, coça a nuca, olha pro chão" -o clips/p12.mp4 [--pro] --confirmar
  python lipsync.py omnihuman --imagem p20.png --audio voz/p20.wav --prompt "she laughs and points at him" -o clips/p20.mp4 --confirmar
  python lipsync.py sincronizar --video clips/p20.mp4 --audio voz/p20.wav -o clips/p20-ls.mp4 --confirmar
Sem --confirmar só mostra o custo (nunca gasta sem você ver o preço). O pedido pago fica salvo em <saida>.json.
"""
import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gerar_clipe_fal import baixar, data_uri, pedir  # noqa: E402

MODELOS = {
    "avatar": "fal-ai/kling-video/ai-avatar/v2/standard",
    "avatar-pro": "fal-ai/kling-video/ai-avatar/v2/pro",
    "omnihuman": "fal-ai/bytedance/omnihuman/v1.5",
    "sincronizar": "fal-ai/sync-lipsync/v2",
}
PRECO_S = {"avatar": 0.0562, "avatar-pro": 0.115, "omnihuman": 0.16, "sincronizar": 0.05}  # API oficial fal, 2026-11-06
ESTILO_FALA = ("cartoon character speaking, clear mouth shapes matching the words, natural blinking, small head and hand "
               "gestures, same character design as the image, no text")


def duracao_audio(arq):
    if arq.lower().endswith(".wav"):
        with wave.open(arq) as w:
            return w.getnframes() / w.getframerate()
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def audio_uri(arq):
    """mp3 em data URI (o wav de 24 kHz fica 4× maior); 0,15 s de respiro no fim para a boca fechar."""
    tmp = os.path.join(tempfile.gettempdir(), f"ls-{os.getpid()}.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", arq, "-af", "apad=pad_dur=0.15", "-ac", "1", "-b:a", "96k", tmp], check=True)
    return f"data:audio/mpeg;base64,{base64.b64encode(open(tmp, 'rb').read()).decode()}"


def audio_mp3(arq):
    tmp = os.path.join(tempfile.gettempdir(), f"ls-up-{os.getpid()}.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", arq, "-af", "apad=pad_dur=0.15", "-ac", "1", "-b:a", "96k", tmp], check=True)
    return tmp


def fal_upload(arq, mime=None):
    """Sobe o arquivo para o storage do fal (CDN v3) e devolve a URL — para modelos que não aceitam data URI.
    Upload não é geração: não cobra."""
    import urllib.request
    from gerar_clipe_fal import chave
    mime = mime or mimetypes.guess_type(arq)[0] or "application/octet-stream"
    ini = urllib.request.Request("https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3", method="POST",
                                 data=json.dumps({"content_type": mime, "file_name": os.path.basename(arq)}).encode(),
                                 headers={"Authorization": f"Key {chave()}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(ini, timeout=60))
    put = urllib.request.Request(r["upload_url"], data=open(arq, "rb").read(), headers={"Content-Type": mime}, method="PUT")
    urllib.request.urlopen(put, timeout=300).read()
    return r["file_url"]


def video_uri(arq):
    return f"data:{mimetypes.guess_type(arq)[0] or 'video/mp4'};base64,{base64.b64encode(open(arq, 'rb').read()).decode()}"


def rodar_fal(modelo, corpo, saida, preco, detalhe, chave_saida="video", tipo="lipsync"):
    """Fila do fal: envia, guarda o pedido pago em <saida>.json, espera, baixa e registra o custo."""
    from custos import registrar
    os.makedirs(os.path.dirname(os.path.abspath(saida)) or ".", exist_ok=True)
    fila = pedir(f"https://queue.fal.run/{modelo}", corpo)
    json.dump({"modelo": modelo, "custo_estimado": preco, "request_id": fila.get("request_id"),
               "response_url": fila["response_url"], "detalhe": detalhe},
              open(saida + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  pedido {fila.get('request_id')} enviado ({modelo}); aguardando…")
    t0 = time.time()
    while pedir(fila["status_url"]).get("status") != "COMPLETED":
        if time.time() - t0 > 1200:
            sys.exit(f"tempo esgotado; o pedido continua no fal — resposta em {fila['response_url']}")
        time.sleep(5)
    r = pedir(fila["response_url"])
    item = r.get(chave_saida) or next((v for v in r.values() if isinstance(v, dict) and v.get("url")), None)
    if not item:
        sys.exit(f"resposta sem arquivo: {json.dumps(r)[:300]}")
    baixar(item["url"], saida)
    registrar(tipo, modelo, preco, detalhe, "API oficial fal (preço por segundo)")
    print(f"  pronto em {time.time() - t0:.0f}s → {saida} (US$ {preco:.3f})")
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rota", choices=["avatar", "omnihuman", "sincronizar"])
    ap.add_argument("--imagem")
    ap.add_argument("--video")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--pro", action="store_true", help="avatar: versão Pro")
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args()
    rota = "avatar-pro" if (a.rota == "avatar" and a.pro) else a.rota
    modelo, dur = MODELOS[rota], duracao_audio(a.audio) + 0.15
    preco = round(PRECO_S[rota] * dur, 3)
    print(f"{rota}: {modelo} · {dur:.1f}s de fala → US$ {preco:.3f}")
    if not a.confirmar:
        print("(só orçamento — acrescente --confirmar para gerar)")
        return
    prompt = f"{a.prompt}. {ESTILO_FALA}" if a.prompt else ESTILO_FALA
    if rota == "sincronizar":
        if not a.video:
            sys.exit("sincronizar precisa de --video (o clipe já animado)")
        corpo = {"video_url": video_uri(a.video), "audio_url": audio_uri(a.audio), "sync_mode": "cut_off", "model": "lipsync-2"}
    else:
        if not a.imagem:
            sys.exit(f"{rota} precisa de --imagem (o quadro do personagem)")
        corpo = {"image_url": data_uri(a.imagem), "audio_url": audio_uri(a.audio), "prompt": prompt}
        if rota == "omnihuman":
            # 2026-11-07: o OmniHuman (ByteDance) não lê data URI ("file_download_error") — sobe para o storage do fal
            corpo.update(image_url=fal_upload(a.imagem), audio_url=fal_upload(audio_mp3(a.audio), "audio/mpeg"), resolution="720p")
    rodar_fal(modelo, corpo, a.saida, preco, f"{os.path.basename(a.saida)} · {rota} · {dur:.1f}s")


if __name__ == "__main__":
    main()
