"""Especialistas do estúdio (pedido do usuário, 2026-11-06): TRILHA SONORA, ATUAÇÃO, FIGURINO e ATENÇÃO (neurociência +
psicologia comportamental). Medições locais e grátis (ffmpeg ebur128, librosa, OpenCV); o Gemini assiste/escuta onde
é preciso julgar. Sem Gemini, o que depende dele fica `nao_verificado` — nunca aprovado por omissão.

  trilha   filme.mp4   loudness −14 LUFS (±1), pico real ≤ −1 dBTP, buraco de som (silêncio ≥ 0,7 s no meio), corte seco no
                       fim, voz ≥ 9 dB acima da trilha (com as pistas separadas: --voz/--trilha e roteiro.mix), cortes no
                       tempo da música (aviso), e o Gemini ESCUTA: clima por bloco (roteiro.trilha_clima), música brigando
                       com a voz, troca brusca, efeito sem causa na tela.
  atuacao  [--planos]  cada take de atuação (assets/clips/<id>.mp4) contra os beats do contrato: emoção pedida × vista,
                       intensidade 1–5 (pedida × vista; diferença ≥ 2 ou EXAGERO reprova — "não precisa forçar tanto"),
                       tempo de reação, olhar, rosto que muda, micro-movimentos, credibilidade, tempo cômico. Devolve a
                       correção em inglês para o próximo take (o modo autônomo usa).
  figurino [--planos | filme.mp4]  personagem × ficha (roteiro.elenco: ref + figurino + traços): cada item fixo presente
                       e igual (cor da roupa, acessórios, cabelo, barba), nada que não está na ficha (óculos, chapéu…),
                       rosto igual. Nos takes (3 quadros) ou no filme montado (janela de cada plano).
  atencao  roteiro.json [filme.mp4]  especialista em atenção (references/atencao.md):
                       ROTEIRO (antes de gastar): velocidade de fala, carga de texto, 1 ideia por plano, gancho 0–3 s,
                       re-gancho 40–55 %, CTA único + parecer do Gemini com a rubrica (nota 0–100, curva prevista,
                       problemas por plano com princípio e mudança concreta).
                       FILME: novidade por segundo (cortes, movimento, sons novos), vales de atenção (> 3 s sem novidade),
                       duração dos planos, 1ª mudança, fala por segundo + parecer do Gemini assistindo.

Uso (na pasta do projeto):
  python especialistas.py trilha   roteiro.json entrega/filme.mp4 [--voz assets/voz-pista.wav --trilha assets/trilha.wav]
  python especialistas.py atuacao  roteiro.json [--planos c02a,c02e]
  python especialistas.py figurino roteiro.json [--planos …] [entrega/filme.mp4]
  python especialistas.py atencao  roteiro.json [entrega/filme.mp4]
Saída: entrega/inspecao-<especialista>.md + .json. Código: 0 aprovado · 2 reprovado · 3 falta verificação.
"""
import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import conferencia as cf  # noqa: E402
import integridade as ig  # noqa: E402

ALVO_LUFS, TOL_LUFS, MAX_PICO = -14.0, 1.0, -1.0
MARGEM_VOZ_DB = 9.0
VALE_S = 3.0
MAX_PAL_S = 3.2
REF_ATENCAO = os.path.join(os.path.dirname(AQUI), "references", "atencao.md")


# ---------------------------------------------------------------- comum
def gemini(pedido, imagens=(), video=None, audio=None, temperatura=0.2):
    """JSON do Gemini vendo imagens e/ou um vídeo (com som) e/ou um áudio. None sem chave/cota."""
    try:
        import urllib.request
        from tts_gemini import URL, chave
        partes = [{"text": pedido}]
        for f in imagens:
            partes.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(f, "rb").read()).decode()}})
        for arq, mime in ((video, "video/mp4"), (audio, "audio/wav")):
            if arq:
                partes.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(open(leve(arq, mime), "rb").read()).decode()}})
        corpo = {"contents": [{"parts": partes}], "generationConfig": {"responseMimeType": "application/json", "temperature": temperatura}}
        req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:  # noqa: BLE001 — sem Gemini = não verificado
        print(f"  (Gemini indisponível: {str(e)[:100]})", file=sys.stderr)
        return None


def leve(arq, mime):
    """Vídeo/áudio > 15 MB vira uma cópia leve (480p / 64 kbps) para caber no envio direto ao Gemini."""
    if os.path.getsize(arq) <= 15 * 1024 * 1024:
        return arq
    saida = os.path.join(tempfile.gettempdir(), f"leve-{os.getpid()}-{os.path.basename(arq)}")
    if mime.startswith("video"):
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", arq, "-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "32", "-preset", "veryfast",
               "-c:a", "aac", "-b:a", "64k", saida]
    else:
        saida = saida.rsplit(".", 1)[0] + ".wav"
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", arq, "-ac", "1", "-ar", "16000", saida]
    subprocess.run(cmd, check=True)
    return saida


def mesclar_gravar(base, nome, itens, titulo, extra=None):
    """Mantém os itens já inspecionados de outros planos (um take por vez no modo autônomo)."""
    ant = (cf.ler_json(os.path.join(base, "entrega", f"inspecao-{nome}.json"), {}) or {}).get("itens", [])
    por_id = {i["id"]: i for i in ant}
    por_id.update({i["id"]: i for i in itens})
    return cf.gravar(base, nome, list(por_id.values()), titulo, extra)


def quadros_clipe(clip, n=3, pasta=None):
    pasta = pasta or tempfile.mkdtemp(prefix="esp-")
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
                             capture_output=True, text=True).stdout.strip() or 0)
    return [cf.quadro(clip, d * (k + 0.5) / n, os.path.join(pasta, f"{os.path.basename(clip)}-{k}.png")) for k in range(n)]


def planos_alvo(d, planos=None, so_atuacao=True):
    alvo = set(planos.split(",")) if planos else None
    for p in d["planos"]:
        c = p.get("direcao") or {}
        if alvo and p["id"] not in alvo:
            continue
        if so_atuacao and (c.get("rota_fixa") or c.get("modo") not in ig.MODOS_ANIMADOS):
            continue
        yield p


# ---------------------------------------------------------------- trilha sonora
def loudness(arq):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", arq, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    resumo = r.stderr[r.stderr.rfind("Summary:"):]
    pega = lambda rx: float(m.group(1)) if (m := re.search(rx, resumo)) else None  # noqa: E731
    return {"lufs": pega(r"I:\s+(-?[\d.]+) LUFS"), "lra": pega(r"LRA:\s+(-?[\d.]+) LU"), "pico_dbtp": pega(r"Peak:\s+(-?[\d.]+) dBFS")}


def silencios(arq, limiar_db=-50, minimo=0.7):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", arq, "-af", f"silencedetect=n={limiar_db}dB:d={minimo}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ini = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    fim = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", r.stderr)]
    return list(zip(ini, fim + [None] * (len(ini) - len(fim))))


def carregar(arq, sr=22050):
    """Áudio mono de wav/mp3 ou de dentro de um vídeo (o librosa daqui não abre MP4: extrai com ffmpeg)."""
    import librosa
    if not arq.lower().endswith((".wav", ".flac", ".ogg")):
        tmp = os.path.join(tempfile.gettempdir(), f"aud-{os.getpid()}-{abs(hash(arq))}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", arq, "-vn", "-ac", "1", "-ar", str(sr), tmp], check=True)
        arq = tmp
    y, _ = librosa.load(arq, sr=sr, mono=True)
    return y, sr


def db_janelas(y, sr, jan=0.4):
    n = int(sr * jan)
    k = len(y) // n if n else 0
    if k == 0:
        return np.array([])
    rms = np.sqrt(np.mean(y[: k * n].reshape(k, n) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def conferir_trilha(base, d, filme, voz=None, trilha=None, ouvir=gemini):
    r = {"id": "filme", "problemas": [], "pendencias": [], "avisos": []}
    lo = loudness(filme)
    r["loudness"] = lo
    if lo["lufs"] is None:
        r["pendencias"].append("não consegui medir o loudness")
    elif abs(lo["lufs"] - ALVO_LUFS) > TOL_LUFS:
        r["problemas"].append(("media", f"loudness {lo['lufs']:.1f} LUFS (alvo {ALVO_LUFS:.0f} ±{TOL_LUFS:.0f})"))
    if lo["pico_dbtp"] is not None:
        if lo["pico_dbtp"] >= -0.1:
            r["problemas"].append(("grave", f"clipando: pico {lo['pico_dbtp']:.1f} dBTP"))
        elif lo["pico_dbtp"] > MAX_PICO:
            r["problemas"].append(("media", f"pico real {lo['pico_dbtp']:.1f} dBTP (máx. {MAX_PICO:.0f})"))
    y, sr = carregar(filme)
    dur = len(y) / sr
    for a, b in [(a, b) for a, b in silencios(filme) if a > 0.3 and (b is None or b < dur - 0.5)]:
        r["problemas"].append(("media", f"buraco de som {a:.1f}–{(b if b is not None else dur):.1f} s"))
    fim_db = db_janelas(y[-int(0.15 * sr):], sr, 0.15)
    antes_db = db_janelas(y[-int(1.15 * sr):-int(0.15 * sr)], sr, 1.0)
    if len(fim_db) and len(antes_db) and fim_db[-1] > -35 and fim_db[-1] > antes_db[-1] - 6:
        r["problemas"].append(("media", f"corte seco no final ({fim_db[-1]:.0f} dBFS no último 0,15 s) — termine com fade ou golpe final"))
    mix = d.get("mix") or {}
    if voz and trilha and os.path.exists(voz) and os.path.exists(trilha):
        yv, _ = carregar(voz, sr)
        yt, _ = carregar(trilha, sr)
        n = min(len(yv), len(yt))
        dv = db_janelas(yv[:n] * float(mix.get("voz", 1.0)), sr)
        dt = db_janelas(yt[:n] * float(mix.get("trilha", 1.0)), sr)
        fala = dv > (dv.max() - 30) if len(dv) else np.array([], bool)
        if fala.any():
            margem = dv[fala] - dt[fala]
            r["voz_sobre_trilha_db"] = {"mediana": round(float(np.median(margem)), 1), "pior": round(float(np.min(margem)), 1),
                                        "abaixo_de_9db": round(float(np.mean(margem < MARGEM_VOZ_DB)), 2)}
            if np.mean(margem < MARGEM_VOZ_DB) > 0.1:
                r["problemas"].append(("media", f"voz menos de {MARGEM_VOZ_DB:.0f} dB acima da trilha em "
                                                f"{np.mean(margem < MARGEM_VOZ_DB):.0%} da fala (pior {np.min(margem):.1f} dB)"))
    else:
        r["avisos"].append("voz × trilha não medida (passe --voz e --trilha, as pistas separadas)")
    try:
        import librosa
        yb, srb = carregar(trilha, 22050) if trilha and os.path.exists(trilha) else (y, sr)
        tempo, batidas = librosa.beat.beat_track(y=yb, sr=srb)
        bt = librosa.frames_to_time(batidas, sr=srb)
        ts, _ = cf.tempos(base, d)
        cortes = [float(t["inicio"]) for t in ts[1:]]
        if len(bt) > 4 and len(cortes) >= 4:
            no_tempo = float(np.mean([np.min(np.abs(bt - c)) <= 0.09 for c in cortes]))
            r["batida"] = {"bpm": round(float(np.atleast_1d(tempo)[0]), 1), "cortes_no_tempo": round(no_tempo, 2)}
            if no_tempo < 0.5:
                r["avisos"].append(f"só {no_tempo:.0%} dos cortes caem na batida da música ({r['batida']['bpm']} BPM)")
    except Exception as e:  # noqa: BLE001
        r["avisos"].append(f"batida não medida: {str(e)[:80]}")
    clima = d.get("trilha_clima") or {}
    pedido = ("Você é supervisor de trilha sonora de comerciais. Escute o vídeo (imagem + som). Blocos (segundos): "
              f"{json.dumps(d.get('blocos') or {}, ensure_ascii=False)}. Clima pedido por bloco: "
              f"{json.dumps(clima, ensure_ascii=False) if clima else 'conforme a imagem'}. "
              "Aponte só problemas reais, com o segundo: música que não combina com o clima do bloco, música brigando com a voz "
              "(atrapalha entender), troca/entrada brusca, música que some sem motivo, efeito sonoro sem causa na tela ou fora de "
              "sincronia, ruído/chiado/estalo. Responda JSON: {\"clima_por_bloco\": {\"bloco\": \"o que ouviu\"}, "
              "\"problemas\": [{\"segundo\": 0, \"tipo\": \"clima|briga_com_voz|troca_brusca|sumiu|efeito|ruido\", \"detalhe\": \"...\"}], \"nota\": 0}")
    v = ouvir(pedido, video=filme)
    if v is None:
        r["pendencias"].append("escuta do clima e da mixagem (sem Gemini)")
    else:
        r["escuta"] = v
        for x in v.get("problemas") or []:
            r["problemas"].append(("media", f"{x.get('segundo')} s · {x.get('tipo')}: {x.get('detalhe')}"[:220]))
    r["estado"] = cf.estado(r["problemas"], r["pendencias"])
    return cf.gravar(base, "trilha", [r], "Trilha sonora")


# ---------------------------------------------------------------- atuação
PEDIDO_ATUACAO = """Você é diretor de atuação de animação 2D. Assista ao take (imagem e som) e compare com o CONTRATO.
Personagem(ns): {quem}. Ação: {acao}. Atuação pedida: {atuacao}. Fala: {fala}.
Beats do contrato (tempo em s): {beats}
Para CADA beat avalie: emoção pedida × vista, intensidade pedida e vista (1 = contida … 5 = extrema/caricata), se o
tempo da reação está certo, se o olhar vai para onde deve, se está exagerado (careta, gesto grande demais, drama além do
pedido) ou apagado. Avalie também: o rosto MUDA de expressão ao longo do take? há micro-movimentos (respiração, piscar)?
é crível? se é piada, o tempo cômico funciona e fecha com reação?
Responda JSON: {{"beats": [{{"beat": 1, "fase": "...", "emocao_pedida": "...", "emocao_vista": "...", "emocao_ok": true,
"intensidade_pedida": 3, "intensidade_vista": 3, "tempo_ok": true, "olhar_ok": true, "exagerado": false, "apagado": false,
"comentario": "..."}}], "rosto_muda": true, "micro_movimentos": true, "crivel": true, "tempo_comico_ok": null,
"nota": 0, "correcao_en": "one short instruction in English to fix the acting in the next take, or empty"}}"""


def conferir_atuacao_clipe(p, clip, assistir=gemini):
    c = p.get("direcao") or {}
    beats = [{"ate": b.get("ate") or b.get("fim"), "fase": b.get("fase"), "pt": b.get("pt"), "en": b.get("en")} for b in c.get("beats") or []]
    r = {"id": p["id"], "problemas": [], "pendencias": [], "avisos": []}
    v = assistir(PEDIDO_ATUACAO.format(quem=", ".join(c.get("quem") or p.get("quem") or []) or "—", acao=c.get("acao", ""),
                                       atuacao=c.get("atuacao", ""), fala=p.get("fala") or "—",
                                       beats=json.dumps(beats, ensure_ascii=False)), video=clip)
    if v is None:
        r["pendencias"].append("avaliação de atuação (sem Gemini) — olhar a folha de quadros")
        r["estado"] = ig.NAO_VERIFICADO
        return r
    r["avaliacao"] = v
    for b in v.get("beats") or []:
        rot = f"beat {b.get('beat')} ({b.get('fase')})"
        if b.get("emocao_ok") is False:
            r["problemas"].append(("grave", f"{rot}: emoção {b.get('emocao_vista')} × pedida {b.get('emocao_pedida')}"))
        try:
            dif = int(b.get("intensidade_vista")) - int(b.get("intensidade_pedida"))
        except (TypeError, ValueError):
            dif = 0
        if b.get("exagerado") or dif >= 2:
            r["problemas"].append(("grave", f"{rot}: exagerado (intensidade {b.get('intensidade_vista')} × {b.get('intensidade_pedida')}) — {b.get('comentario', '')}"[:200]))
        elif b.get("apagado") or dif <= -2:
            r["problemas"].append(("media", f"{rot}: apagado (intensidade {b.get('intensidade_vista')} × {b.get('intensidade_pedida')})"))
        if b.get("tempo_ok") is False and b.get("fase") in ("acao", "reacao", "consequencia"):
            r["problemas"].append(("media", f"{rot}: tempo da reação errado — {b.get('comentario', '')}"[:200]))
        if b.get("olhar_ok") is False:
            r["avisos"].append(f"{rot}: olhar fora do alvo")
    if v.get("crivel") is False:
        r["problemas"].append(("grave", "atuação não crível"))
    if v.get("rosto_muda") is False:
        r["problemas"].append(("media", "rosto congelado: a expressão não muda no take"))
    if v.get("micro_movimentos") is False:
        r["avisos"].append("sem micro-movimentos (respiração/piscar) — parece boneco")
    if v.get("tempo_comico_ok") is False:
        r["problemas"].append(("media", "tempo cômico não funciona"))
    try:
        if float(v.get("nota")) < 7:
            r["problemas"].append(("media", f"nota de atuação {v.get('nota')}/10"))
    except (TypeError, ValueError):
        pass
    r["correcao_en"] = v.get("correcao_en") or ""
    r["sha256_clipe"] = ig.sha256(clip)
    r["estado"] = cf.estado(r["problemas"], r["pendencias"])
    return r


def conferir_atuacao(base, d, planos=None, assistir=gemini):
    itens = []
    for p in planos_alvo(d, planos):
        clip = os.path.join(base, "assets", "clips", f"{p['id']}.mp4")
        if os.path.exists(clip):
            itens.append(conferir_atuacao_clipe(p, clip, assistir))
    return mesclar_gravar(base, "atuacao", itens, "Atuação dos personagens")


# ---------------------------------------------------------------- figurino
PEDIDO_FIGURINO = """Você é supervisor de figurino e continuidade de animação. Compare os personagens nos QUADROS com as
REFERÊNCIAS (ficha). Itens fixos de cada personagem:
{fichas}
Para cada item diga se está presente e igual (mesma cor, mesmo objeto). Lado (esquerdo/direito) só conta se a ficha
mostrar claramente; imagem espelhada não é erro. Liste também o que o personagem VESTE e NÃO está na ficha (óculos,
chapéu, roupa trocada, outra cor, acessório novo no corpo) — objetos de cena que ele segura ou que estão no cenário
(caneca, celular, papel, notebook) NÃO são figurino e não entram. Diga se o rosto é o mesmo. Item fora do quadro (corte
do enquadramento) = "fora_de_quadro", não é erro.
Responda JSON: {{"itens": [{{"personagem": "...", "item": "...", "estado": "ok|diferente|ausente|fora_de_quadro", "visto": "..."}}],
"extras": [{{"personagem": "...", "o_que": "..."}}], "rosto_igual": {{"<personagem>": true}}}}"""


def fichas_de(d, base, quem):
    el = d.get("elenco") or {}
    out, refs = [], []
    for q in quem:
        f = el.get(q)
        if not f:
            continue
        out.append(f"- {q}: figurino {', '.join(f.get('figurino') or [])}; traços {', '.join(f.get('tracos') or [])}")
        ref = os.path.join(base, f["ref"]) if f.get("ref") else None
        if ref and os.path.exists(ref):
            refs.append(ref)
    return "\n".join(out), refs


def conferir_figurino_quadros(d, base, pid, quem, quadros, ver=gemini):
    r = {"id": pid, "problemas": [], "pendencias": [], "avisos": []}
    texto, refs = fichas_de(d, base, quem)
    if not texto:
        r["pendencias"].append(f"sem ficha no roteiro.elenco para {', '.join(quem) or '—'}")
        r["estado"] = ig.NAO_VERIFICADO
        return r
    v = ver(PEDIDO_FIGURINO.format(fichas=texto) + "\n(As primeiras imagens são as REFERÊNCIAS; as últimas, os QUADROS.)",
            imagens=list(refs) + list(quadros))
    if v is None:
        r["pendencias"].append("figurino (sem Gemini) — comparar quadros × ficha")
        r["estado"] = ig.NAO_VERIFICADO
        return r
    r["visto"] = v
    tracos = {q: set((d.get("elenco") or {}).get(q, {}).get("tracos") or []) for q in quem}
    for it in v.get("itens") or []:
        if it.get("estado") in ("diferente", "ausente"):
            grave = it.get("item") in tracos.get(it.get("personagem"), set())
            r["problemas"].append(("grave" if grave else "media",
                                   f"{it.get('personagem')}: {it.get('item')} {it.get('estado')} — {it.get('visto', '')}"[:200]))
    for x in v.get("extras") or []:  # a ficha não é exaustiva (jeans/relógio da imagem-chave aprovada): extra é aviso
        r["avisos"].append(f"{x.get('personagem')}: fora da ficha — {x.get('o_que')}"[:200])
    for q, ok in (v.get("rosto_igual") or {}).items():
        if ok is False:
            r["problemas"].append(("grave", f"{q}: rosto diferente da ficha"))
    r["estado"] = cf.estado(r["problemas"], r["pendencias"])
    return r


def conferir_figurino(base, d, planos=None, filme=None, ver=gemini):
    itens, tmp = [], tempfile.mkdtemp(prefix="fig-")
    janelas = {t["id"]: t for t in cf.tempos(base, d)[0]} if filme else {}
    for p in planos_alvo(d, planos, so_atuacao=not filme):
        quem = (p.get("direcao") or {}).get("quem") or p.get("quem") or []
        if not quem:
            continue
        if filme:
            t = janelas.get(p["id"])
            if not t:
                continue
            a, b = float(t["inicio"]), float(t["fim"])
            qs = [cf.quadro(filme, a + (b - a) * f, os.path.join(tmp, f"{p['id']}-{k}.png")) for k, f in enumerate((0.2, 0.5, 0.8))]
        else:
            clip = os.path.join(base, "assets", "clips", f"{p['id']}.mp4")
            if not os.path.exists(clip):
                continue
            qs = quadros_clipe(clip, 3, tmp)
        r = conferir_figurino_quadros(d, base, p["id"], quem, qs, ver)
        if not filme:
            r["sha256_clipe"] = ig.sha256(os.path.join(base, "assets", "clips", f"{p['id']}.mp4"))
        itens.append(r)
    return mesclar_gravar(base, "figurino", itens, "Figurino e continuidade" + (" (filme)" if filme else " (takes)"))


# ---------------------------------------------------------------- atenção (neurociência + psicologia comportamental)
CTA = re.compile(r"\b(pe[cç]a|acesse|baixe|fale|agende|teste|experimente|demonstra[cç][aã]o|clique|chame)\b", re.I)
VIRADA = re.compile(r"\b(agora|mas|imagina|ent[aã]o|por[eé]m|e se|de repente|at[eé] que)\b", re.I)


def metricas_roteiro(d):
    fora = cf.partes_de(d)
    planos = [p for p in d["planos"] if p["id"] not in fora]
    total = sum(float(p.get("dur_alvo") or (p.get("direcao") or {}).get("duracao") or 0) for p in planos)
    t, achados, linha = 0.0, [], []
    for p in planos:
        dur = float(p.get("dur_alvo") or (p.get("direcao") or {}).get("duracao") or 0)
        fala = p.get("fala") or ""
        pal = len(fala.split())
        if dur and pal / dur > MAX_PAL_S:
            achados.append(("media", p["id"], "carga cognitiva", f"{pal / dur:.1f} palavras/s (máx. {MAX_PAL_S}) — encurte a fala ou estique o plano"))
        for tx in p.get("texto_tela") or []:
            if len(str(tx).split()) > 8:
                achados.append(("aviso", p["id"], "carga cognitiva", f"texto de tela com {len(str(tx).split())} palavras: \"{str(tx)[:50]}…\" — use a palavra-chave da fala"))
        if dur > 5 and (p.get("tipo") == "tela" or (p.get("direcao") or {}).get("rota_fixa")):
            achados.append(("aviso", p["id"], "habituação", f"tela de {dur:.1f} s: garanta uma mudança visual a cada ~2 s (entrada de item, zoom no detalhe, selo)"))
        linha.append({"id": p["id"], "ini": round(t, 1), "dur": dur, "fala": fala})
        t += dur
    abertura = " ".join(x["fala"] for x in linha if x["ini"] < 3.0)
    if linha and not abertura.strip():
        achados.append(("media", linha[0]["id"], "gancho", "nada é dito nos 3 primeiros segundos — a relevância pessoal precisa vir já"))
    meio = [x for x in linha if 0.40 * total <= x["ini"] <= 0.55 * total]
    if total > 20 and not any(VIRADA.search(x["fala"]) for x in meio):
        achados.append(("aviso", meio[0]["id"] if meio else "-", "re-gancho", "sem virada/pergunta entre 40 % e 55 % do vídeo"))
    fim = " ".join(x["fala"] for x in linha if x["ini"] >= total - 8) + " " + " ".join(
        " ".join(p.get("texto_obrigatorio") or []) for p in planos[-2:])
    if linha and not CTA.search(fim):
        achados.append(("media", linha[-1]["id"], "CTA", "o final não tem um pedido claro (ex.: 'Peça uma demonstração')"))
    return {"duracao": round(total, 1), "planos": len(linha), "achados": achados}


PEDIDO_ATENCAO = """Você é especialista em neurociência da atenção e psicologia comportamental aplicadas a vídeo publicitário.
Use APENAS a rubrica e os princípios abaixo (com o grau de evidência) e não use pseudociência ("dopamina" não é métrica).
Briefing: {briefing}
{material}
=== RUBRICA E PRINCÍPIOS ===
{rubrica}
=== TAREFA ===
Avalie como o espectador-alvo vai prestar atenção, segundo a segundo. Para cada problema diga o PLANO (id) ou o segundo, o
PRINCÍPIO violado, o problema e a mudança CONCRETA (o que dizer/mostrar/cortar). Não sugira nada que exija prometer o que o
produto não faz. Responda JSON: {{"nota": 0, "por_bloco": {{"Gancho": 0, "Ritmo de novidade": 0, "Carga cognitiva": 0,
"Emoção e arco": 0, "Persuasão": 0, "CTA e memória": 0}}, "curva_prevista": [{{"t": 0, "atencao": 0, "porque": "..."}}],
"problemas": [{{"onde": "c02e ou 12 s", "principio": "...", "problema": "...", "mudanca": "..."}}],
"pontos_fortes": ["..."], "tres_mudancas": ["...", "...", "..."]}}"""


def metricas_filme(filme, ts):
    """Novidade por segundo: cortes/movimento forte (imagem) + sons novos; vales = intervalos sem novidade."""
    import cv2
    import librosa
    cap = cv2.VideoCapture(filme)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    passo = max(1, int(round(fps / 10)))
    dif, ant, i = [], None, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % passo == 0:
            g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (64, 36)).astype(np.float32)
            dif.append(float(np.mean(np.abs(g - ant))) if ant is not None else 0.0)
            ant = g
        i += 1
    cap.release()
    dif = np.array(dif)
    t_img = np.arange(len(dif)) * passo / fps
    limiar = max(6.0, float(np.percentile(dif, 85))) if len(dif) else 6.0
    ev_img = list(t_img[dif > limiar])
    y, sr = carregar(filme, 22050)
    forca = librosa.onset.onset_strength(y=y, sr=sr)
    on = librosa.onset.onset_detect(onset_envelope=forca, sr=sr, units="frames", delta=0.25)
    corte_forca = float(np.percentile(forca, 90)) if len(forca) else 0
    fortes = [float(t) for t in librosa.frames_to_time([k for k in on if forca[k] > corte_forca], sr=sr)]
    cortes = [float(t["inicio"]) for t in ts[1:]]
    eventos = sorted(set(round(x, 1) for x in ev_img + fortes + cortes))
    dur = len(y) / sr
    marcos = [0.0] + eventos + [dur]
    vales = [(round(a, 1), round(b, 1)) for a, b in zip(marcos, marcos[1:]) if b - a > VALE_S]
    planos = [float(t["fim"]) - float(t["inicio"]) for t in ts]
    return {"duracao": round(dur, 1), "novidades_por_10s": round(10 * len(eventos) / max(dur, 1), 1),
            "primeira_mudanca_s": round(eventos[0], 1) if eventos else None, "vales": vales,
            "plano_mediano_s": round(float(np.median(planos)), 1) if planos else None,
            "planos_maiores_4s": int(sum(x > 4 for x in planos))}


def conferir_atencao(base, d, filme=None, especialista=gemini):
    bf = os.path.join(base, "BRIEFING.md")
    briefing = io.open(bf, encoding="utf-8").read()[:2500] if os.path.exists(bf) else ""
    rubrica = io.open(REF_ATENCAO, encoding="utf-8").read() if os.path.exists(REF_ATENCAO) else ""
    mr = metricas_roteiro(d)
    r = {"id": "filme" if filme else "roteiro", "problemas": [], "pendencias": [], "avisos": [], "metricas_roteiro": mr}
    for g, pid, princ, txt in mr["achados"]:
        if g == "media":
            r["problemas"].append(("media", f"{pid} · {princ}: {txt}"))
        else:
            r["avisos"].append(f"{pid} · {princ}: {txt}")
    if filme:
        ts, _ = cf.tempos(base, d)
        mf = metricas_filme(filme, ts)
        r["metricas_filme"] = mf
        for a, b in mf["vales"]:
            r["problemas"].append(("media", f"vale de atenção {a}–{b} s ({b - a:.1f} s sem novidade) — habituação"))
        if mf["primeira_mudanca_s"] is None or mf["primeira_mudanca_s"] > 1.0:
            r["problemas"].append(("media", f"1ª mudança só em {mf['primeira_mudanca_s']} s — a orientação precisa vir no 1º segundo"))
        esp = cf.ler_json(os.path.join(base, "entrega", "espectador.json"))
        material = f"Métricas medidas do filme: {json.dumps(mf, ensure_ascii=False)}" + (
            f"\nRelatório do espectador simulado: {json.dumps(esp, ensure_ascii=False)[:2500]}" if esp else "") + "\nO VÍDEO segue anexo."
        v = especialista(PEDIDO_ATENCAO.format(briefing=briefing, material=material, rubrica=rubrica), video=filme, temperatura=0.4)
    else:
        linhas = "\n".join(f"{p['id']} · {p.get('dur_alvo')} s · fala: {p.get('fala') or '—'} · tela: {p.get('texto_tela') or p.get('beneficio') or '—'}"
                           f" · ação: {(p.get('o_que') or '')[:160]}" for p in d["planos"] if p["id"] not in cf.partes_de(d))
        material = (f"ROTEIRO (antes de produzir), blocos {json.dumps(d.get('blocos') or {}, ensure_ascii=False)}:\n{linhas}\n"
                    f"Métricas: {json.dumps({k: v for k, v in mr.items() if k != 'achados'})}")
        v = especialista(PEDIDO_ATENCAO.format(briefing=briefing, material=material, rubrica=rubrica), temperatura=0.4)
    if v is None:
        r["pendencias"].append("parecer do especialista (sem Gemini)")
    else:
        r["parecer"] = v
        try:
            r["nota"] = float(v.get("nota"))
            if r["nota"] < 70:
                r["problemas"].append(("media", f"nota de atenção {r['nota']:.0f}/100 (mínimo 70)"))
        except (TypeError, ValueError):
            pass
        for x in v.get("problemas") or []:
            r["avisos"].append(f"{x.get('onde')} · {x.get('principio')}: {x.get('problema')} → {x.get('mudanca')}"[:300])
    r["estado"] = cf.estado(r["problemas"], r["pendencias"])
    extra = {"tres_mudancas": (v or {}).get("tres_mudancas") or [], "pontos_fortes": (v or {}).get("pontos_fortes") or []}
    return cf.gravar(base, "atencao", [r], f"Atenção do espectador ({'filme' if filme else 'roteiro'})"
                     + (f" — nota {r['nota']:.0f}/100" if r.get("nota") is not None else ""), extra)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["trilha", "atuacao", "figurino", "atencao"])
    ap.add_argument("roteiro")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--planos")
    ap.add_argument("--voz")
    ap.add_argument("--trilha")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.roteiro))
    d = json.load(io.open(a.roteiro, encoding="utf-8"))
    if a.modo == "trilha":
        if not a.video:
            sys.exit("trilha precisa do vídeo montado")
        rep, nv = conferir_trilha(base, d, a.video, a.voz, a.trilha)
    elif a.modo == "atuacao":
        rep, nv = conferir_atuacao(base, d, a.planos)
    elif a.modo == "figurino":
        rep, nv = conferir_figurino(base, d, a.planos, a.video)
    else:
        rep, nv = conferir_atencao(base, d, a.video)
    sys.exit(2 if rep else 3 if nv else 0)


if __name__ == "__main__":
    main()
