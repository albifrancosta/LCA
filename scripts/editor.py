"""Editor de vídeo com IA do criador-video (local: faster-whisper + ffmpeg).

Subcomandos:
  transcrever  video -o transcript.json            fala -> palavras com tempo (+ frases.txt para leitura)
  limpar       video transcript.json -o limpo.mp4   tira silêncios, vícios ("éé", "hum") e gaguejos
  legendar     video transcript.json -o leg.mp4     legenda animada palavra a palavra (+ título de gancho)
  reformatar   video -o final.mp4 --formato 9:16    enquadra (blur/crop), normaliza volume, exporta
  cortes       video transcript.json cortes.json -d pasta   vários Reels/Shorts de um vídeo longo

Rode com o Python que tem faster-whisper (python).
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VICIOS = {"ee", "eee", "eeee", "ehh", "eh", "ha", "aa", "ah", "ahh", "ahn", "hum", "humm", "hmm", "hm", "uhm", "um", "uh", "an"}
FORMATOS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}


# ---------------------------------------------------------------- utilidades
def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(map(str, cmd))[:400]}\n{r.stderr[-2500:]}")
    return r


def probe(video):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)])
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    return {"w": v["width"], "h": v["height"], "fps": float(num) / float(den) if float(den) else 30.0,
            "dur": float(d["format"]["duration"]), "audio": a is not None}


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9%]+", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def ler_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def ler_palavras(p):
    d = ler_json(p)
    if isinstance(d, dict):
        d = d.get("words") or [w for v in d.get("voices", []) for w in v.get("words", [])] \
            or [w for s in d.get("segments", []) for w in s.get("words", [])]
    out = []
    for w in d:
        txt = (w.get("text") or w.get("word") or "").strip()
        if txt:
            out.append({"text": txt, "start": float(w["start"]), "end": float(w["end"])})
    return out


def salvar_palavras(ws, p):
    data = [{"id": f"w{i}", "text": w["text"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
            for i, w in enumerate(ws)]
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def enc_video(crf=20):
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def enc_audio():
    return ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]


# ---------------------------------------------------------------- transcrever
def transcrever(a):
    from faster_whisper import WhisperModel
    modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8")
    termos = a.termos or None
    segs, info = modelo.transcribe(str(a.video), language=a.idioma, word_timestamps=True, vad_filter=True,
                                   condition_on_previous_text=False, initial_prompt=termos, hotwords=termos)
    trocas = {}
    for par in a.corrigir or []:
        errado, certo = par.split("=", 1)
        trocas[norm(errado)] = certo
    ws, frases = [], []
    for s in segs:
        texto = []
        for w in s.words or []:
            txt = w.word.strip()
            if not txt:
                continue
            m = re.match(r"^(.*?)([.,!?;:…]*)$", txt)
            if norm(m.group(1)) in trocas:
                txt = trocas[norm(m.group(1))] + m.group(2)
            ws.append({"text": txt, "start": w.start, "end": w.end})
            texto.append(txt)
        frases.append(f"[{s.start:7.2f} - {s.end:7.2f}] {' '.join(texto)}")
    salvar_palavras(ws, a.out)
    Path(a.out).with_name(Path(a.out).stem + "-frases.txt").write_text("\n".join(frases), encoding="utf-8")
    print(f"{a.out}: {len(ws)} palavras · {len(frases)} frases · idioma {info.language}")


# ---------------------------------------------------------------- limpar
def intervalos_mantidos(ws, dur, max_pausa, margem, tirar_vicios):
    removidos = {"vicios": [], "repeticoes": [], "pausas": 0}
    keep = []
    for i, w in enumerate(ws):
        n = norm(w["text"])
        if tirar_vicios and n in VICIOS:
            removidos["vicios"].append(w["text"])
            continue
        prox = ws[i + 1] if i + 1 < len(ws) else None
        if prox and n and norm(prox["text"]) == n and prox["start"] - w["end"] < 0.6:
            removidos["repeticoes"].append(w["text"])
            continue
        keep.append(w)
    segs = []
    for w in keep:
        a, b = max(0.0, w["start"] - margem), min(dur, w["end"] + margem)
        if segs and a - segs[-1][1] <= max_pausa:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            if segs:
                removidos["pausas"] += 1
            segs.append([a, b])
    return segs, keep, removidos


def remapear(ws, segs):
    """Leva os tempos das palavras para a linha do tempo depois dos cortes."""
    out, base, offs = [], 0.0, []
    for a, b in segs:
        offs.append((a, b, base))
        base += b - a
    for w in ws:
        for a, b, o in offs:
            if a <= w["start"] < b:
                out.append({"text": w["text"], "start": w["start"] - a + o, "end": min(w["end"], b) - a + o})
                break
    return out


def limpar(a):
    info = probe(a.video)
    ws = ler_palavras(a.transcript)
    segs, keep, rem = intervalos_mantidos(ws, info["dur"], a.max_pausa, a.margem, not a.manter_vicios)
    if not segs:
        raise SystemExit("nenhuma fala encontrada para manter")
    expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segs)
    filtros = f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[v]"
    mapas = ["-map", "[v]"]
    if info["audio"]:
        filtros += f";[0:a]aselect='{expr}',asetpts=N/SR/TB[a]"
        mapas += ["-map", "[a]"]
    script = Path(a.out).with_suffix(".filtro.txt")
    script.write_text(filtros, encoding="utf-8")
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(a.video), "-filter_complex_script", str(script), *mapas,
         *enc_video(18), *(enc_audio() if info["audio"] else []), str(a.out)])
    script.unlink(missing_ok=True)
    tpath = Path(a.out).with_suffix(".transcript.json")
    salvar_palavras(remapear(keep, segs), tpath)
    depois = sum(e - s for s, e in segs)
    rel = {"manter": [[round(s, 3), round(e, 3)] for s, e in segs], "removidos": rem,
           "duracao_antes": round(info["dur"], 2), "duracao_depois": round(depois, 2)}
    Path(a.out).with_suffix(".limpeza.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.out}: {info['dur']:.1f}s -> {depois:.1f}s · pausas cortadas {rem['pausas']} · "
          f"vícios {len(rem['vicios'])} · gaguejos {len(rem['repeticoes'])}")
    print(f"transcript novo: {tpath}")


# ---------------------------------------------------------------- legendar
def cor_ass(hexcor, alpha="00"):
    h = hexcor.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def grupos(ws, maximo, pausa=0.15):
    gs, atual = [], []
    for i, w in enumerate(ws):
        if atual:
            ult = ws[atual[-1]]
            if len(atual) >= maximo or w["start"] - ult["end"] >= pausa or re.search(r"[.!?,;:…]$", ult["text"]):
                gs.append(atual)
                atual = []
        atual.append(i)
    if atual:
        gs.append(atual)
    return gs


def escrever_ass(ws, w, h, a, destino):
    tam = int(h * a.tamanho)
    margem_v = int(h * (1 - a.altura))
    def limpo(t):
        t = t.replace("{", "").replace("}", "")
        return t if a.pontuacao else re.sub(r"[.,;:…]+$", "", t)
    caixa = (lambda t: t.upper()) if a.maiusculas else (lambda t: t)
    branco = cor_ass(a.cor)
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Leg,{a.fonte},{tam},{branco},{branco},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, tam // 12)},{max(1, tam // 30)},2,{int(w * .08)},{int(w * .08)},{margem_v},1",
        f"Style: Titulo,{a.fonte},{int(tam * 1.2)},{branco},{branco},{cor_ass(a.cor_titulo)},{cor_ass(a.cor_titulo)},-1,0,0,0,100,100,0,0,3,"
        f"{max(8, tam // 4)},0,8,{int(w * .07)},{int(w * .07)},{int(h * .12)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if a.titulo:
        linhas.append(f"Dialogue: 1,{ts(0)},{ts(a.titulo_ate)},Titulo,,0,0,0,,{{\\fad(0,200)}}{caixa(limpo(a.titulo))}")
    destaque = cor_ass(a.cor_destaque)
    gs = grupos(ws, a.palavras)
    for gi, g in enumerate(gs):
        fim_grupo = ws[g[-1]]["end"] + 0.12
        if gi + 1 < len(gs):
            fim_grupo = min(fim_grupo, ws[gs[gi + 1][0]]["start"])
        for k, i in enumerate(g):
            ini = ws[i]["start"] if k else max(0.0, ws[i]["start"] - 0.05)
            fim = ws[g[k + 1]]["start"] if k + 1 < len(g) else fim_grupo
            if fim <= ini:
                continue
            partes = []
            for j in g:
                t = caixa(limpo(ws[j]["text"]))
                partes.append(f"{{\\c{destaque}\\fscx112\\fscy112}}{t}{{\\c{branco}\\fscx100\\fscy100}}" if j == i else t)
            pop = "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            linhas.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},Leg,,0,0,0,,{pop}{' '.join(partes)}")
    Path(destino).write_text("\n".join(linhas) + "\n", encoding="utf-8-sig")
    return len(gs)


def legendar(a):
    info = probe(a.video)
    ws = ler_palavras(a.transcript)
    out = Path(a.out).resolve()
    ass = out.with_suffix(".ass")
    n = escrever_ass(ws, info["w"], info["h"], a, ass)
    if a.somente_ass:
        print(f"{ass}: {n} grupos")
        return
    # o filtro ass roda com cwd na pasta do .ass para evitar o escape de "C:" no Windows
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(Path(a.video).resolve()), "-vf", f"ass={ass.name}",
         *enc_video(19), *(["-c:a", "copy"] if info["audio"] else []), str(out)], cwd=str(ass.parent))
    print(f"{out}: {n} grupos de legenda · arquivo de legenda {ass}")


# ---------------------------------------------------------------- reformatar / exportar
def filtro_formato(formato, modo, x):
    if formato == "original":
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    W, H = FORMATOS[formato]
    if modo == "crop":
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(iw-{W})*{x}:(ih-{H})*0.5,setsar=1")
    return (f"split[o1][o2];[o1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=25:2,eq=brightness=-0.08[bg];[o2]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def reformatar_arquivo(video, out, formato="9:16", modo="blur", x=0.5, lufs=-14.0, fps=30):
    info = probe(video)
    vf = filtro_formato(formato, modo, x) + f",fps={fps}"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(video), "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
    if info["audio"]:
        cmd += ["-map", "0:a:0", "-af", f"loudnorm=I={lufs}:TP=-1.0:LRA=11", *enc_audio()]
    run(cmd + enc_video(20) + [str(out)])


def reformatar(a):
    reformatar_arquivo(a.video, a.out, a.formato, a.modo, a.x, a.lufs, a.fps)
    i = probe(a.out)
    print(f"{a.out}: {i['w']}x{i['h']} · {i['fps']:.0f} fps · {i['dur']:.1f}s · {a.lufs} LUFS")


# ---------------------------------------------------------------- cortes
def cortes(a):
    ws = ler_palavras(a.transcript)
    lista = ler_json(a.cortes)
    pasta = Path(a.dir)
    pasta.mkdir(parents=True, exist_ok=True)
    for c in lista:
        nome, s, e = c["nome"], float(c["start"]), float(c["end"])
        bruto = pasta / f"{nome}-bruto.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{s:.3f}", "-to", f"{e:.3f}", "-i", str(a.video),
             *enc_video(16), *enc_audio(), str(bruto)])
        palavras = [{"text": w["text"], "start": w["start"] - s, "end": min(w["end"], e) - s}
                    for w in ws if s <= w["start"] < e]
        tjson = pasta / f"{nome}.transcript.json"
        salvar_palavras(palavras, tjson)
        fmt = pasta / f"{nome}-formato.mp4"
        reformatar_arquivo(bruto, fmt, a.formato, a.modo, c.get("x", a.x))
        final = pasta / f"{nome}.mp4"
        if a.sem_legenda:
            fmt.replace(final)
        else:
            args = argparse.Namespace(video=str(fmt), transcript=str(tjson), out=str(final), somente_ass=False,
                                      titulo=c.get("titulo"), titulo_ate=a.titulo_ate, **estilo_padrao(a))
            legendar(args)
            fmt.unlink(missing_ok=True)
        bruto.unlink(missing_ok=True)
        print(f"  {nome}: {s:.1f}-{e:.1f}s -> {final}")


# ---------------------------------------------------------------- CLI
def add_estilo(p):
    p.add_argument("--fonte", default="Arial")
    p.add_argument("--tamanho", type=float, default=0.052, help="altura da letra em fração da altura do vídeo")
    p.add_argument("--altura", type=float, default=0.70, help="posição vertical da legenda (0 topo, 1 base)")
    p.add_argument("--palavras", type=int, default=3, help="palavras por grupo")
    p.add_argument("--cor", default="#FFFFFF")
    p.add_argument("--cor-destaque", default="#FFE600")
    p.add_argument("--cor-titulo", default="#000000", help="cor da caixa atrás do título")
    p.add_argument("--maiusculas", action="store_true")
    p.add_argument("--pontuacao", action="store_true", help="manter vírgulas e pontos finais na legenda")


def estilo_padrao(a):
    return {k: getattr(a, k) for k in ("fonte", "tamanho", "altura", "palavras", "cor", "cor_destaque",
                                       "cor_titulo", "maiusculas", "pontuacao")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("transcrever")
    p.add_argument("video")
    p.add_argument("-o", "--out", default="transcript.json")
    p.add_argument("--modelo", default="small", help="tiny|base|small|medium|large-v3")
    p.add_argument("--idioma", default="pt")
    p.add_argument("--termos", help='nomes que a fala usa, ex.: "MinhaMarca, orçamento, fluxo de caixa"')
    p.add_argument("--corrigir", nargs="*", help='trocas pós-transcrição, ex.: Olí=MinhaMarca')
    p.set_defaults(f=transcrever)

    p = sub.add_parser("limpar")
    p.add_argument("video")
    p.add_argument("transcript")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--max-pausa", type=float, default=0.35, help="pausas maiores que isso são cortadas (s)")
    p.add_argument("--margem", type=float, default=0.08, help="folga antes/depois de cada palavra (s)")
    p.add_argument("--manter-vicios", action="store_true")
    p.set_defaults(f=limpar)

    p = sub.add_parser("legendar")
    p.add_argument("video")
    p.add_argument("transcript")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--titulo", help="texto do gancho no topo nos primeiros segundos")
    p.add_argument("--titulo-ate", type=float, default=3.0)
    p.add_argument("--somente-ass", action="store_true")
    add_estilo(p)
    p.set_defaults(f=legendar)

    p = sub.add_parser("reformatar")
    p.add_argument("video")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--formato", default="9:16", choices=[*FORMATOS, "original"])
    p.add_argument("--modo", default="blur", choices=["blur", "crop"])
    p.add_argument("--x", type=float, default=0.5, help="crop: posição horizontal 0 (esq.) a 1 (dir.)")
    p.add_argument("--lufs", type=float, default=-14.0)
    p.add_argument("--fps", type=int, default=30)
    p.set_defaults(f=reformatar)

    p = sub.add_parser("cortes")
    p.add_argument("video")
    p.add_argument("transcript")
    p.add_argument("cortes")
    p.add_argument("-d", "--dir", required=True)
    p.add_argument("--formato", default="9:16", choices=[*FORMATOS, "original"])
    p.add_argument("--modo", default="blur", choices=["blur", "crop"])
    p.add_argument("--x", type=float, default=0.5)
    p.add_argument("--titulo-ate", type=float, default=3.0)
    p.add_argument("--sem-legenda", action="store_true")
    add_estilo(p)
    p.set_defaults(f=cortes)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
