"""Gera variações de um vídeo pronto com MoviePy, sem renderizar de novo no Remotion.

Uso:
  python variantes_moviepy.py variantes.json [--so nome1,nome2]

variantes.json (caminhos relativos ao próprio arquivo):
{
  "base": "entrega/video-A.mp4",
  "saida": "entrega/variantes",
  "variantes": [
    {"nome": "B", "abertura": "remotion/out/abertura-B.mp4", "ate": 7},        # troca só a imagem dos primeiros N s
    {"nome": "30s", "trechos": [[0, 18], [28, 37.4], [52.6, 60]]},           # recorta e emenda (dissolve curto)
    {"nome": "quadrado", "formato": "1:1"},                                    # 1:1 ou 16:9 (fundo escurecido)
    {"nome": "cta-whats", "texto_final": {"texto": "Chame no WhatsApp", "de": 57.8}}  # texto por cima no fim
  ]
}
Uma variante pode combinar campos (ex.: trechos + formato). Exporta H.264 + AAC, 30 fps.
"""
import argparse
import json
import os
import time

from moviepy import CompositeVideoClip, TextClip, VideoFileClip, concatenate_videoclips, vfx

FONTE = "C:/Windows/Fonts/arialbd.ttf"
DISSOLVE = 0.25


def trocar_abertura(base, arquivo, ate):
    abertura = VideoFileClip(arquivo).subclipped(0, ate).without_audio()
    resto = base.subclipped(ate).without_audio()
    return concatenate_videoclips([abertura, resto]).with_audio(base.audio)  # a voz da base segue igual


def recortar(base, trechos):
    partes = [base.subclipped(a, b) for a, b in trechos]
    # dissolve curto entre trechos para o corte não "pular"; o áudio acompanha cada trecho
    partes = [p if i == 0 else p.with_effects([vfx.CrossFadeIn(DISSOLVE)]) for i, p in enumerate(partes)]
    return concatenate_videoclips(partes, padding=-DISSOLVE, method="compose")


def reformatar(clip, formato):
    w, h = {"1:1": (1080, 1080), "16:9": (1920, 1080), "9:16": (1080, 1920)}[formato]
    frente = clip.resized(height=h) if clip.w / clip.h <= w / h else clip.resized(width=w)
    fundo = clip.resized((w, h)).with_effects([vfx.MultiplyColor(0.35)])  # fundo escurecido no lugar das tarjas
    return CompositeVideoClip([fundo, frente.with_position("center")], size=(w, h)).with_audio(clip.audio)


def texto_final(clip, cfg):
    t = (TextClip(font=FONTE, text=cfg["texto"], font_size=cfg.get("tamanho", 64), color="white",
                  bg_color=cfg.get("cor", "#1F6FEB"), margin=(40, 24), method="label")
         .with_start(cfg["de"]).with_duration(clip.duration - cfg["de"])
         .with_position(("center", cfg.get("altura", 0.78)), relative=True)
         .with_effects([vfx.CrossFadeIn(0.3)]))
    return CompositeVideoClip([clip, t]).with_audio(clip.audio)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--so")
    a = ap.parse_args()
    raiz = os.path.dirname(os.path.abspath(a.config))
    cfg = json.load(open(a.config, encoding="utf-8"))
    caminho = lambda p: os.path.join(raiz, p)
    pasta = caminho(cfg.get("saida", "variantes"))
    os.makedirs(pasta, exist_ok=True)
    so = set(a.so.split(",")) if a.so else None
    for v in cfg["variantes"]:
        if so and v["nome"] not in so:
            continue
        t0 = time.time()
        clip = VideoFileClip(caminho(cfg["base"]))
        if "abertura" in v:
            clip = trocar_abertura(clip, caminho(v["abertura"]), v.get("ate", 7))
        if "trechos" in v:
            clip = recortar(clip, v["trechos"])
        if "texto_final" in v:
            clip = texto_final(clip, v["texto_final"])
        if "formato" in v:
            clip = reformatar(clip, v["formato"])
        nome = os.path.splitext(os.path.basename(cfg["base"]))[0]
        out = os.path.join(pasta, f"{nome}-{v['nome']}.mp4")
        clip.write_videofile(out, fps=30, codec="libx264", audio_codec="aac", audio_bitrate="192k", preset="medium",
                             ffmpeg_params=["-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
                             threads=6, logger=None)
        print(f"{v['nome']:10} {clip.duration:5.1f}s  {clip.w}x{clip.h}  em {time.time() - t0:5.0f}s  -> {out}")
        clip.close()


if __name__ == "__main__":
    main()
