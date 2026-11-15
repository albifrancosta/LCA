"""Mede um vídeo de referência (link ou arquivo) para o modo APRENDER do criador-video.

Uso:
    python analisar_referencia.py <link-ou-arquivo> --slug nome-curto [--out-root PASTA] [--limiar 0.3]

Gera na pasta da referência: video.*, audio.wav, analise.json, frames/, folha-gancho.jpg, folha-planos.jpg
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_ROOT = Path(os.path.expanduser("~")) / "estudio-video" / "referencias"


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"falhou: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "referencia"


def obter_video(fonte, pasta):
    if re.match(r"^https?://", fonte):
        run([
            "yt-dlp", "--no-playlist", "--write-info-json",
            "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", str(pasta / "video.%(ext)s"), fonte,
        ])
        videos = [p for p in pasta.glob("video.*") if p.suffix not in (".json", ".part")]
        if not videos:
            raise RuntimeError("yt-dlp não gerou o vídeo")
        info = {}
        info_file = pasta / "video.info.json"
        if info_file.exists():
            raw = json.loads(info_file.read_text(encoding="utf-8-sig"))
            info = {k: raw.get(k) for k in (
                "title", "uploader", "upload_date", "view_count", "like_count",
                "comment_count", "webpage_url", "extractor")}
        return videos[0], info
    origem = Path(fonte)
    if not origem.exists():
        raise FileNotFoundError(fonte)
    destino = pasta / f"video{origem.suffix.lower()}"
    if origem.resolve() != destino.resolve():
        shutil.copy2(origem, destino)
    return destino, {"arquivo_original": str(origem)}


def probe(video):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)])
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return {
        "duracao": round(float(d["format"]["duration"]), 3),
        "largura": v["width"], "altura": v["height"],
        "fps": round(fps, 3), "tem_audio": a is not None,
    }


def detectar_cortes(video, limiar):
    r = run(["ffmpeg", "-hide_banner", "-i", str(video), "-an",
             "-vf", f"select='gt(scene,{limiar})',showinfo", "-f", "null", "-"], check=False)
    tempos = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    cortes = []
    for t in tempos:
        if not cortes or t - cortes[-1] >= 0.2:
            cortes.append(round(t, 3))
    return cortes


def medir_audio(video, pasta):
    wav = pasta / "audio.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    r = run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af",
             "ebur128,silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"], check=False)
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    inicios = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    fins = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    silencios = [{"start": round(max(s, 0), 2), "end": round(e, 2)} for s, e in zip(inicios, fins)]
    return {"lufs": float(lufs[-1]) if lufs else None, "silencios": silencios}


def extrair_frame(video, t, destino):
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "3", str(destino)], check=False)


def folha(padrao, saida, cols, n):
    rows = max(1, -(-n // cols))
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", "1", "-i", padrao,
         "-vf", f"tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", str(saida)], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fonte")
    ap.add_argument("--slug")
    ap.add_argument("--out-root", default=str(DEFAULT_ROOT))
    ap.add_argument("--limiar", type=float, default=0.3, help="sensibilidade do detector de cortes (0-1)")
    a = ap.parse_args()

    slug = a.slug or slugify(Path(a.fonte).stem if not a.fonte.startswith("http") else a.fonte.split("/")[-1])
    pasta = Path(a.out_root) / slug
    (pasta / "frames").mkdir(parents=True, exist_ok=True)

    video, meta = obter_video(a.fonte, pasta)
    info = probe(video)
    cortes = detectar_cortes(video, a.limiar)
    limites = [0.0] + cortes + [info["duracao"]]
    planos = [round(limites[i + 1] - limites[i], 3) for i in range(len(limites) - 1)]
    audio = medir_audio(video, pasta) if info["tem_audio"] else {"lufs": None, "silencios": []}

    for f in (pasta / "frames").glob("*.jpg"):
        f.unlink()
    # frames do gancho (0-3 s, a cada 0,5 s)
    ts_gancho = [x / 2 for x in range(0, 7) if x / 2 < info["duracao"]]
    for i, t in enumerate(ts_gancho, 1):
        extrair_frame(video, t, pasta / "frames" / f"gancho_{i:02d}.jpg")
    # 1 frame no meio de cada plano (no máximo 24, amostrados por igual)
    meios = [(limites[i] + limites[i + 1]) / 2 for i in range(len(limites) - 1)]
    if len(meios) > 24:
        passo = len(meios) / 24
        meios = [meios[int(i * passo)] for i in range(24)]
    for i, t in enumerate(meios, 1):
        extrair_frame(video, t, pasta / "frames" / f"plano_{i:03d}.jpg")

    folha(str(pasta / "frames" / "gancho_%02d.jpg"), pasta / "folha-gancho.jpg", 4, len(ts_gancho))
    folha(str(pasta / "frames" / "plano_%03d.jpg"), pasta / "folha-planos.jpg", 6, len(meios))

    analise = {
        "slug": slug,
        "fonte": a.fonte,
        "meta": meta,
        **info,
        "cortes": cortes,
        "n_planos": len(planos),
        "planos_s": planos,
        "plano_medio_s": round(sum(planos) / len(planos), 3) if planos else None,
        "plano_mais_longo_s": max(planos) if planos else None,
        "cortes_0_3s": sum(1 for c in cortes if c < 3.0),
        "trocas_por_s": round(len(cortes) / info["duracao"], 3) if info["duracao"] else None,
        "audio": audio,
        "arquivos": {
            "video": video.name, "audio": "audio.wav" if info["tem_audio"] else None,
            "folha_gancho": "folha-gancho.jpg", "folha_planos": "folha-planos.jpg",
        },
    }
    (pasta / "analise.json").write_text(json.dumps(analise, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Pasta: {pasta}")
    print(f"{info['largura']}x{info['altura']} · {info['fps']} fps · {info['duracao']} s")
    print(f"planos: {len(planos)} · plano médio: {analise['plano_medio_s']} s · "
          f"cortes em 0-3 s: {analise['cortes_0_3s']} · trocas/s: {analise['trocas_por_s']}")
    print(f"loudness: {audio['lufs']} LUFS · silêncios: {len(audio['silencios'])}")
    if meta.get("view_count") is not None:
        print(f"views: {meta['view_count']} · likes: {meta.get('like_count')}")
    print("Próximo: transcrever audio.wav e olhar folha-gancho.jpg / folha-planos.jpg")


if __name__ == "__main__":
    main()
