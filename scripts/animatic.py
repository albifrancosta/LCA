"""Roteiro temporal + animatic ANTES de gastar com clipes: monta o filme provisório com o que já existe (clipe → imagem-chave
→ cartão cinza) e a voz provisória ou final (assets/voz/<id>.wav; sem voz, silêncio). Custo zero, local.

Mostra cedo o que hoje só aparecia no render final: duração total × alvo do projeto.json, fala que não cabe no plano
(voz mais longa que o plano), planos sem imagem, ritmo. A duração é decidida aqui, não depois de pagar os takes.

Uso:
  python animatic.py <projeto> [--largura 640] [--sem-video]   → entrega/animatic.mp4 + entrega/roteiro-temporal.md/.json
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402


def dur_plano(p):
    c = p.get("direcao") or {}
    return float(c.get("duracao") or p.get("dur_alvo") or p.get("dur") or 3.0)


def temporal(base, d, cfg=None):
    """Tabela do roteiro temporal: início/fim, fonte visual, voz (duração) e se a fala cabe."""
    t, linhas = 0.0, []
    for p in d["planos"]:
        pid, du = p["id"], dur_plano(p)
        clip = os.path.join(base, "assets", "clips", f"{pid}.mp4")
        img = os.path.join(base, "assets", "img", f"{pid}.png")
        voz = os.path.join(base, "assets", "voz", f"{pid}.wav")
        s_voz = ig.sonda(voz) if os.path.isfile(voz) else None
        fonte = "clipe" if ig.midia_valida(clip, "video")[0] else "imagem" if os.path.isfile(img) else "cartao"
        lin = {"id": pid, "inicio": round(t, 3), "fim": round(t + du, 3), "dur": du, "fonte": fonte,
               "fala": p.get("fala") or "", "voz_s": round(s_voz["duracao"], 2) if s_voz else None, "avisos": []}
        if p.get("fala") and not s_voz:
            lin["avisos"].append("fala sem voz (silêncio no animatic)")
        if s_voz and s_voz["duracao"] > du + 0.15:
            lin["avisos"].append(f"voz {s_voz['duracao']:.2f}s não cabe no plano de {du:.2f}s")
        if fonte == "cartao":
            lin["avisos"].append("sem imagem-chave")
        linhas.append(lin)
        t += du
    alvo = ((cfg or {}).get("duracao") or {}).get("segundos")
    return {"planos": linhas, "total": round(t, 3), "alvo": alvo,
            "desvio_pct": round((t - alvo) / alvo * 100, 2) if alvo else None}


def _seg(base, lin, saida, largura, fps):
    altura = int(round(largura * 9 / 16 / 2)) * 2
    esc = (f"scale={largura}:{altura}:force_original_aspect_ratio=decrease,pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2,"
           f"setsar=1,fps={fps},format=yuv420p")
    pid, du = lin["id"], lin["dur"]
    if lin["fonte"] == "clipe":
        vin = ["-i", os.path.join(base, "assets", "clips", f"{pid}.mp4")]
        vf = f"tpad=stop_mode=clone:stop_duration={du},{esc}"
    elif lin["fonte"] == "imagem":
        vin = ["-loop", "1", "-i", os.path.join(base, "assets", "img", f"{pid}.png")]
        vf = esc
    else:
        vin = ["-f", "lavfi", "-i", f"color=c=0x444444:s={largura}x{altura}:r={fps}"]
        vf = "format=yuv420p"
    voz = os.path.join(base, "assets", "voz", f"{pid}.wav")
    ain = ["-i", voz] if lin["voz_s"] else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd = (["ffmpeg", "-v", "error", "-y"] + vin + ain +
           ["-t", f"{du:.3f}", "-vf", vf, "-af", "apad,aresample=48000,aformat=channel_layouts=stereo", "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "96k", saida])
    subprocess.run(cmd, check=True)


def montar(base, tab, saida, largura=640, fps=24):
    tmp = tempfile.mkdtemp(prefix="animatic-")
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for k, lin in enumerate(tab["planos"]):
            seg = os.path.join(tmp, f"{k:03d}.mp4")
            _seg(base, lin, seg, largura, fps)
            f.write(f"file '{seg.replace(os.sep, '/')}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", saida], check=True)
    return saida


def gravar(base, tab):
    ig.gravar_json_atomico(os.path.join(base, "entrega", "roteiro-temporal.json"), tab)
    L = ["# Roteiro temporal (animatic)", "", f"Total **{tab['total']:.2f} s** · alvo {tab['alvo']} s" +
         (f" ({tab['desvio_pct']:+.1f} %)" if tab["desvio_pct"] is not None else ""), "",
         "| Plano | Início | Fim | Dur | Visual | Voz | Avisos |", "|---|---|---|---|---|---|---|"]
    for x in tab["planos"]:
        L.append(f"| {x['id']} | {x['inicio']:.2f} | {x['fim']:.2f} | {x['dur']:.2f} | {x['fonte']} | {x['voz_s'] or '—'} | {'; '.join(x['avisos'])} |")
    io.open(os.path.join(base, "entrega", "roteiro-temporal.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projeto")
    ap.add_argument("--largura", type=int, default=640)
    ap.add_argument("--sem-video", action="store_true", help="só o roteiro temporal (sem montar o mp4)")
    a = ap.parse_args()
    base = os.path.abspath(a.projeto)
    import projeto as pj
    cfg = pj.carregar(base)
    d = json.load(io.open(os.path.join(base, "roteiro.json"), encoding="utf-8"))
    tab = temporal(base, d, cfg)
    gravar(base, tab)
    n_av = sum(1 for x in tab["planos"] if x["avisos"])
    print(f"roteiro temporal: {len(tab['planos'])} planos, {tab['total']:.2f}s (alvo {tab['alvo']}), {n_av} com aviso → entrega/roteiro-temporal.md")
    if not a.sem_video:
        saida = os.path.join(base, "entrega", "animatic.mp4")
        montar(base, tab, saida, a.largura)
        print(f"animatic: {saida} ({ig.sonda(saida)['duracao']:.2f}s)")
    dec = pj.resolver_duracao(cfg, tab["total"])
    if dec.get("decisao"):
        print(("NOVA decisão: " if dec.get("nova") else "decisão já registrada: ") + dec["decisao"])


if __name__ == "__main__":
    main()
