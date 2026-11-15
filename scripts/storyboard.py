"""Monta o storyboard em imagem para o usuário conferir a história antes de cada gasto.

Uso:
  python storyboard.py storyboard.json -o storyboard.png [--colunas 4]

storyboard.json (caminhos relativos ao arquivo):
{
  "titulo": "MinhaMarca — A nota já foi?",
  "etapa": "1 · roteiro (rascunho)",
  "tomadas": [
    {"tempo": "0–3,4 s", "imagem": "assets/ilustrado/s1.png", "tipo": "clipe IA",
     "acao": "técnico fecha a caixa; o celular vibra", "fala": "NARR: Serviço concluído...", "tela": "—"}
  ]
}
Tomada sem imagem vira um quadro cinza com a ação escrita (útil na etapa de roteiro, sem custo).
"""
import argparse
import json
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

FONTES = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
FONTES_B = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
COR_TIPO = {"clipe IA": (31, 111, 235), "imagem": (100, 116, 139), "chat": (14, 122, 107), "marca": (245, 158, 11)}


def fonte(lista, tam):
    for f in lista:
        if os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def miniatura(caminho, w, h):
    if caminho and os.path.exists(caminho):
        im = Image.open(caminho).convert("RGB")
        esc = max(w / im.width, h / im.height)
        im = im.resize((int(im.width * esc), int(im.height * esc)))
        x, y = (im.width - w) // 2, (im.height - h) // 2
        return im.crop((x, y, x + w, y + h))
    return Image.new("RGB", (w, h), (226, 232, 240))


def escrever(d, xy, texto, f, cor, largura_chars, max_linhas, entre=6):
    x, y = xy
    linhas = []
    for par in texto.split("\n"):
        linhas += textwrap.wrap(par, largura_chars) or [""]
    for ln in linhas[:max_linhas]:
        d.text((x, y), ln, font=f, fill=cor)
        y += f.size + entre
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("-o", "--saida", required=True)
    ap.add_argument("--colunas", type=int, default=4)
    a = ap.parse_args()
    raiz = os.path.dirname(os.path.abspath(a.config))
    cfg = json.load(open(a.config, encoding="utf-8"))
    tomadas = cfg["tomadas"]
    col = a.colunas
    lin = (len(tomadas) + col - 1) // col
    tw, th = 300, 420  # miniatura vertical
    cw, ch = tw + 40, th + 330
    W, H = col * cw + 40, lin * ch + 170
    img = Image.new("RGB", (W, H), (248, 250, 252))
    d = ImageDraw.Draw(img)
    d.text((40, 36), cfg.get("titulo", "Storyboard"), font=fonte(FONTES_B, 44), fill=(15, 23, 42))
    d.text((40, 96), f"Etapa: {cfg.get('etapa', '')}  ·  {len(tomadas)} tomadas", font=fonte(FONTES, 28), fill=(71, 85, 105))
    fb, fn, fp = fonte(FONTES_B, 26), fonte(FONTES, 22), fonte(FONTES, 20)
    for i, tm in enumerate(tomadas):
        x = 40 + (i % col) * cw
        y = 160 + (i // col) * ch
        d.rounded_rectangle((x - 10, y - 10, x + tw + 10, y + ch - 30), 18, fill=(255, 255, 255), outline=(226, 232, 240), width=2)
        img.paste(miniatura(os.path.join(raiz, tm["imagem"]) if tm.get("imagem") else None, tw, th), (x, y))
        if not tm.get("imagem"):
            escrever(d, (x + 16, y + 60), tm.get("acao", ""), fn, (71, 85, 105), 24, 12)
        tipo = tm.get("tipo", "imagem")
        d.rounded_rectangle((x + 8, y + 8, x + 22 + 11 * len(tipo), y + 42), 10, fill=COR_TIPO.get(tipo, (100, 116, 139)))
        d.text((x + 14, y + 11), tipo, font=fp, fill=(255, 255, 255))
        yy = y + th + 12
        d.text((x, yy), f"{i + 1}.  {tm.get('tempo', '')}", font=fb, fill=(15, 23, 42))
        yy = escrever(d, (x, yy + 36), tm.get("acao", ""), fn, (30, 41, 59), 27, 4)
        if tm.get("fala"):
            yy = escrever(d, (x, yy + 6), "Fala: " + tm["fala"], fp, (30, 64, 175), 29, 5, 4)
        if tm.get("tela"):
            escrever(d, (x, yy + 6), "Tela: " + tm["tela"], fp, (15, 118, 110), 29, 3, 4)
    img.save(a.saida)
    print(a.saida, f"{W}x{H}")


if __name__ == "__main__":
    main()
