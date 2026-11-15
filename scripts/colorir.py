"""Colorista: iguala as cores de cada tomada a um quadro de referência da cena (transferência de cor em Lab, Reinhard),
gravada como LUT 3D (.cube) — a mesma LUT vale para imagem (numpy) e clipe (ffmpeg lut3d). Grátis e local.

Uso:
  python colorir.py lut REF.png ALVO.(png|mp4) -o assets/cor/look.cube [--forca 0.7]
  python colorir.py aplicar ALVO.(png|mp4) --lut assets/cor/look.cube -o saida.(png|mp4)
  python colorir.py cena poste-noite [--forca 0.7]   → na bíblia: referência do cenário (ou 1ª tomada aprovada dele),
        corrige a última imagem/clipe de cada tomada desse cenário em assets/cor/<tomada>.* e grava em versoes[].cor
  python colorir.py todas                            → todos os cenários
--forca: 0 = nada, 1 = cópia total das cores da referência (padrão 0,7: aproxima sem achatar a luz de cada tomada).
"""
import argparse
import os
import subprocess
import sys
import tempfile

import warnings

import numpy as np
from PIL import Image
from skimage.color import lab2rgb, rgb2lab

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
N = 33  # pontos por eixo da LUT
warnings.filterwarnings("ignore", message="Conversion from CIE-LAB")
VIDEO = (".mp4", ".mov", ".webm")


def amostra_rgb(arq):
    """Pixels RGB 0–1 (reduzidos) de uma imagem ou de 5 quadros de um clipe."""
    if arq.lower().endswith(VIDEO):
        with tempfile.TemporaryDirectory() as tmp:
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                                       capture_output=True, text=True).stdout.strip() or 1)
            fotos = []
            for i, t in enumerate(np.linspace(0.1, max(0.1, dur - 0.2), 5)):
                q = os.path.join(tmp, f"{i}.png")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", arq, "-frames:v", "1", "-vf", "scale=320:-2", q], check=True)
                fotos.append(np.asarray(Image.open(q).convert("RGB"), dtype=np.float64) / 255)
            return np.concatenate([f.reshape(-1, 3) for f in fotos])
    im = Image.open(arq).convert("RGB")
    im.thumbnail((480, 480))
    return np.asarray(im, dtype=np.float64).reshape(-1, 3) / 255


def estat(rgb):
    lab = rgb2lab(rgb.reshape(-1, 1, 3)).reshape(-1, 3)
    return lab.mean(0), lab.std(0) + 1e-6


def transferir(rgb, alvo, ref, forca):
    lab = rgb2lab(rgb.reshape(-1, 1, 3)).reshape(-1, 3)
    novo = (lab - alvo[0]) / alvo[1] * ref[1] + ref[0]
    lab = lab + forca * (novo - lab)
    return np.clip(lab2rgb(lab.reshape(-1, 1, 3)).reshape(-1, 3), 0, 1)


def gerar_lut(ref, alvo, saida, forca=0.7):
    s_ref, s_alvo = estat(amostra_rgb(ref)), estat(amostra_rgb(alvo))
    g = np.linspace(0, 1, N)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # .cube: R varia mais rápido
    grade = np.stack([r.ravel(), gg.ravel(), b.ravel()], 1)
    out = transferir(grade, s_alvo, s_ref, forca)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, "w") as f:
        f.write(f'TITLE "colorir {os.path.basename(alvo)} -> {os.path.basename(ref)}"\nLUT_3D_SIZE {N}\n')
        f.writelines(f"{x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in out)
    return saida


def ler_lut(arq):
    linhas = [l.split() for l in open(arq) if l.strip() and l[0] in "0123456789.-"]
    return np.array(linhas, dtype=np.float64).reshape(N, N, N, 3)  # [b][g][r]


def aplicar(alvo, lut, saida):
    os.makedirs(os.path.dirname(os.path.abspath(saida)) or ".", exist_ok=True)
    if alvo.lower().endswith(VIDEO):
        caminho = os.path.abspath(lut).replace("\\", "/").replace(":", "\\:")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", alvo, "-vf", f"lut3d=file='{caminho}'", "-c:v", "libx264",
                        "-crf", "16", "-pix_fmt", "yuv420p", "-an", saida], check=True)
        return saida
    from scipy.ndimage import map_coordinates
    tab = ler_lut(lut)
    im = np.asarray(Image.open(alvo).convert("RGB"), dtype=np.float64) / 255
    coords = (im * (N - 1)).reshape(-1, 3)
    canais = [map_coordinates(tab[..., c], [coords[:, 2], coords[:, 1], coords[:, 0]], order=1) for c in range(3)]
    out = np.clip(np.stack(canais, 1).reshape(im.shape), 0, 1)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(saida)
    return saida


def cena(cid, forca):
    from producao import carregar, salvar
    arq, d = carregar()
    raiz = os.path.dirname(arq)
    c = d["cenarios"].get(cid) or sys.exit(f"cenário {cid} não existe")
    tomadas = [t for t in d["tomadas"] if t.get("cenario") == cid]
    ref = c.get("ref")
    if not ref:
        aprov = [t for t in tomadas if t["status"] == "aprovada" and any(v["tipo"] == "imagem" for v in t["versoes"])]
        ref = next((v["arquivo"] for v in reversed(aprov[0]["versoes"]) if v["tipo"] == "imagem"), None) if aprov else None
    if not ref:
        sys.exit(f"{cid}: sem referência — dê `producao.py cenario {cid} --ref <imagem aprovada>`")
    ref = os.path.join(raiz, ref)
    for t in tomadas:
        v = next((x for x in reversed(t["versoes"]) if x["tipo"] in ("imagem", "clipe")), None)
        if not v:
            continue
        alvo = os.path.join(raiz, v["arquivo"])
        if os.path.abspath(alvo) == os.path.abspath(ref):
            print(f"  {t['id']}: é a própria referência — fica como está")
            continue
        ext = os.path.splitext(alvo)[1]
        lut = gerar_lut(ref, alvo, os.path.join(raiz, "assets", "cor", f"{t['id']}.cube"), forca)
        saida = aplicar(alvo, lut, os.path.join(raiz, "assets", "cor", f"{t['id']}{ext}"))
        v["cor"] = os.path.relpath(saida, raiz).replace("\\", "/")
        print(f"  {t['id']}: {v['arquivo']} → {v['cor']}")
    salvar(arq, d, f"colorista: cenário {cid}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lut"); s.add_argument("ref"); s.add_argument("alvo"); s.add_argument("-o", "--saida", required=True)
    s.add_argument("--forca", type=float, default=0.7)
    s = sub.add_parser("aplicar"); s.add_argument("alvo"); s.add_argument("--lut", required=True); s.add_argument("-o", "--saida", required=True)
    s = sub.add_parser("cena"); s.add_argument("cenario"); s.add_argument("--forca", type=float, default=0.7)
    s = sub.add_parser("todas"); s.add_argument("--forca", type=float, default=0.7)
    a = ap.parse_args()
    if a.cmd == "lut":
        print(gerar_lut(a.ref, a.alvo, a.saida, a.forca))
    elif a.cmd == "aplicar":
        print(aplicar(a.alvo, a.lut, a.saida))
    elif a.cmd == "cena":
        cena(a.cenario, a.forca)
    else:
        from producao import carregar
        for cid in carregar()[1]["cenarios"]:
            print(cid)
            try:
                cena(cid, a.forca)
            except SystemExit as e:
                print(f"  {e}")


if __name__ == "__main__":
    main()
