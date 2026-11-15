"""Conferências que o inspetor não fazia (pedido do usuário, 2026-11-06): TEXTO NA TELA, LIP-SYNC MEDIDO e FILME × STORYBOARD.
Locais e grátis (EasyOCR, YOLO pose, librosa, SSIM); o Gemini entra só na ortografia/enquadramento e, sem ele, o item fica
`nao_verificado` (nunca aprovado por omissão).

  texto       lê o texto de cada plano do filme montado (EasyOCR pt/en, 4 quadros por plano) e confere:
              · o que o roteiro manda escrever (planos[].texto_tela[], beneficio, texto_obrigatorio[]) aparece   → senão reprovado
              · nenhum termo proibido (roteiro.termos_proibidos[], ex.: menu que não existe no sistema)        → grave
              · ortografia, texto cortado/ilegível, palavra de interface inventada (Gemini nos quadros)       → reprovado
  lipsync     para cada fala em quadro (direcao.voz em_quadro / modo fala): acha a boca (YOLO pose: nariz + olhos),
              mede o movimento da boca quadro a quadro e cruza com o envelope da voz:
              · atraso boca × voz > 120 ms (correlação confiável)            → reprovado ("fora de tempo +180 ms")
              · boca parada em mais da metade da fala                        → reprovado
              · rosto não encontrado / sinal fraco                           → nao_verificado (fica a revisão visual)
  storyboard  o filme montado segue o que foi aprovado: todos os planos, na ordem do roteiro, duração de cada plano e
              de cada bloco (roteiro.blocos), quadro do filme parecido com a imagem-chave/clipe aprovado (SSIM + cor) e,
              com Gemini, quem aparece e o tamanho do plano (PG…detalhe) iguais ao contrato.
  filme       texto + storyboard de uma vez (antes do ponto 3).

Uso (na pasta do projeto):
  python conferencia.py texto      roteiro.json entrega/filme.mp4
  python conferencia.py lipsync    roteiro.json [--planos c02b,c07a]          (assets/clips/<id>.mp4 + o áudio dele ou assets/voz/<id>.wav)
  python conferencia.py storyboard roteiro.json entrega/filme.mp4
  python conferencia.py filme      roteiro.json entrega/filme.mp4
Tempos dos planos: remotion/src/historia.json|video.json; sem manifesto, `--pelo-roteiro` soma dur_alvo na ordem.
Código de saída: 0 aprovado · 2 reprovado · 3 falta verificação.
"""
import argparse
import base64
import difflib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

MAX_ATRASO_MS = 120     # acima disso o público percebe a boca fora do tempo
MIN_FALA_COM_BOCA = 0.5
ENQ = ["PG", "PC", "PA", "PM", "PP", "close", "detalhe"]


# ---------------------------------------------------------------- comum
def ler_json(arq, padrao=None):
    try:
        return json.load(io.open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def contem(texto_ocr, frase, limiar=0.8):
    """A frase aparece no texto lido? Tolerante a erro de OCR (janela de palavras + similaridade)."""
    a, f = norm(texto_ocr).split(), norm(frase).split()
    if not f:
        return True
    if " ".join(f) in " ".join(a):
        return True
    n, alvo, melhor = len(f), " ".join(f), 0.0
    for i in range(max(1, len(a) - n + 1)):
        melhor = max(melhor, difflib.SequenceMatcher(None, " ".join(a[i:i + n]), alvo).ratio())
    return melhor >= limiar


def partes_de(d):
    """Planos que são metade de uma composição (ex.: c10e/c10d dentro do c10) não aparecem sozinhos no filme."""
    ps = set()
    for p in d["planos"]:
        v = p.get("partes")
        if isinstance(v, dict):
            ps |= set(v.values())
        elif isinstance(v, list):
            ps |= {x if isinstance(x, str) else x.get("id") for x in v}
    return ps


def tempos(base, d, pelo_roteiro=False):
    """([{id, inicio, fim}], origem) do filme montado."""
    if not pelo_roteiro:
        for nome, chave in (("historia.json", "planos"), ("video.json", "cenas")):
            h = ler_json(os.path.join(base, "remotion", "src", nome))
            if h:
                return [dict(c, id=c.get("id") or f"cena{i + 1}") for i, c in enumerate(h.get(chave, []))], nome
    t, out, fora = 0.0, [], partes_de(d)
    for p in d["planos"]:
        if p["id"] in fora:
            continue
        dur = float(p.get("dur_alvo") or (p.get("direcao") or {}).get("duracao") or 0)
        out.append({"id": p["id"], "inicio": round(t, 3), "fim": round(t + dur, 3)})
        t += dur
    return out, "roteiro (dur_alvo somado)"


def quadro(video, t, saida):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1", saida], check=True)
    return saida


def gemini_imagens(pedido, imagens):
    """JSON do Gemini sobre imagens; None se não houver chave/cota (o chamador marca nao_verificado)."""
    try:
        import urllib.request
        from tts_gemini import URL, chave
        partes = [{"text": pedido}] + [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(f, "rb").read()).decode()}}
                                         for f in imagens]
        corpo = {"contents": [{"parts": partes}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}
        req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:  # noqa: BLE001 — sem Gemini = não verificado, nunca aprovado
        print(f"  (Gemini indisponível: {str(e)[:90]})", file=sys.stderr)
        return None


def estado(problemas, pendencias):
    if problemas:
        return ig.REPROVADO
    return ig.NAO_VERIFICADO if pendencias else ig.APROVADO


def gravar(base, nome, itens, titulo, extra=None):
    os.makedirs(os.path.join(base, "entrega"), exist_ok=True)
    corpo = {"itens": itens, **(extra or {})}
    ig.gravar_json_atomico(os.path.join(base, "entrega", f"inspecao-{nome}.json"), json.loads(json.dumps(corpo, default=str)))
    ic = {ig.APROVADO: "✅", ig.REPROVADO: "❌", ig.NAO_VERIFICADO: "👁"}
    linhas = [f"# {titulo}", ""]
    for k, v in (extra or {}).items():
        if isinstance(v, list) and v:
            linhas += [f"**{k}:**"] + [f"- {x}" for x in v] + [""]
    for it in itens:
        linhas.append(f"- {ic.get(it['estado'], '?')} **{it['id']}** " + " · ".join(
            [f"{g}: {t}" for g, t in it.get("problemas", [])] + [f"aviso: {x}" for x in it.get("avisos", [])]
            + [f"pendente: {x}" for x in it.get("pendencias", [])]))
    io.open(os.path.join(base, "entrega", f"inspecao-{nome}.md"), "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    rep = sum(i["estado"] == ig.REPROVADO for i in itens)
    nv = sum(i["estado"] == ig.NAO_VERIFICADO for i in itens)
    print(f"{titulo}: {len(itens) - rep - nv} ✅ · {rep} ❌ · {nv} 👁 → entrega/inspecao-{nome}.md")
    return rep, nv


# ---------------------------------------------------------------- texto na tela
_leitor = {}


def ocr(img):
    if "r" not in _leitor:
        import easyocr
        _leitor["r"] = easyocr.Reader(["pt", "en"], gpu=False, verbose=False, download_enabled=False)
    return " ".join(t for _, t, c in _leitor["r"].readtext(img) if c >= 0.3)


PEDIDO_TEXTO = """Você é revisor de texto de um comercial em português do Brasil. Nas imagens (quadros de um mesmo plano), liste
TODO texto visível e aponte só problemas reais: erro de ortografia/acentuação, palavra cortada pela borda, texto ilegível
(pequeno/baixo contraste), letras deformadas/inventadas (comum em imagem de IA), nome de menu/recurso que não está na
lista de nomes reais. Nomes reais do sistema: {reais}. Textos que o roteiro manda ter: {esperado}.
Responda JSON: {{"textos": ["..."], "problemas": [{{"texto": "...", "tipo": "ortografia|cortado|ilegivel|deformado|nome_inexistente", "detalhe": "..."}}]}}"""


def conferir_texto(base, d, video, pelo_roteiro=False, ler=ocr, gemini=gemini_imagens):
    ts, origem = tempos(base, d, pelo_roteiro)
    planos = {p["id"]: p for p in d["planos"]}
    proibidos, reais = d.get("termos_proibidos") or [], d.get("nomes_reais") or []
    itens, tmp = [], tempfile.mkdtemp(prefix="txt-")
    for t in ts:
        p = planos.get(t["id"], {})
        esperado = list(p.get("texto_tela") or []) + list(p.get("texto_obrigatorio") or []) + ([p["beneficio"]] if p.get("beneficio") else [])
        dur = float(t["fim"]) - float(t["inicio"])
        # um quadro a cada 0,5 s desde o início do plano: título que fica 1–2 s na tela não pode escapar
        instantes = [float(t["inicio"]) + min(dur - 0.05, 0.15 + 0.5 * k) for k in range(max(1, min(40, int(dur / 0.5) + 1)))]
        imgs = [quadro(video, x, os.path.join(tmp, f"{t['id']}-{k}.png")) for k, x in enumerate(instantes)]
        lido = " ".join(ler(i) for i in imgs)
        imgs = imgs[:: max(1, len(imgs) // 6)][:6]  # para o Gemini: até 6 quadros espalhados
        r = {"id": t["id"], "lido": lido[:600], "esperado": esperado, "problemas": [], "pendencias": []}
        for e in esperado:
            for pedaco in [x for x in re.split(r"[·|]", e) if norm(x)]:
                if not contem(lido, pedaco):
                    r["problemas"].append(("media", f"texto do roteiro não aparece na tela: \"{pedaco.strip()}\""))
        for proib in proibidos:
            if re.search(rf"\b{re.escape(norm(proib))}\b", norm(lido)):
                r["problemas"].append(("grave", f"termo proibido na tela: \"{proib}\""))
        if norm(lido) or esperado:
            v = gemini(PEDIDO_TEXTO.format(reais=", ".join(reais) or "—", esperado=" | ".join(esperado) or "—"), imgs)
            if v is None:
                r["pendencias"].append("ortografia/legibilidade (sem Gemini) — olhar os quadros")
            else:
                r["textos_gemini"] = v.get("textos", [])
                for x in v.get("problemas") or []:
                    r["problemas"].append(("media", f"{x.get('tipo')}: \"{x.get('texto')}\" — {x.get('detalhe', '')}"[:200]))
        r["estado"] = estado(r["problemas"], r["pendencias"])
        itens.append(r)
    return gravar(base, "texto", itens, f"Texto na tela ({origem})")


# ---------------------------------------------------------------- lip-sync medido
def ler_quadros(video):
    import cv2
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    quadros = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        quadros.append(f)
    cap.release()
    return quadros, float(fps)


def caixas_boca_yolo(quadros):
    """Caixa da boca por quadro a partir de nariz (0) e olhos (1, 2) do YOLO pose; None quando não acha o rosto."""
    from ultralytics import YOLO
    peso = os.path.expanduser("~/.cache/yolo/yolo11n-pose.pt")
    m = YOLO(peso if os.path.exists(peso) else "yolo11n-pose.pt")  # cópia local; o nome curto faz o ultralytics baixar de novo
    out = []
    for f in quadros:
        r = m.predict(f, verbose=False)[0]
        if r.keypoints is None or not len(r.keypoints.xy) or r.keypoints.conf is None:
            out.append(None)
            continue
        kp, kc = r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()
        wh = r.boxes.xywh.cpu().numpy()
        i = int(np.argmax(wh[:, 2] * wh[:, 3]))  # o maior = quem fala
        if min(kc[i][0], kc[i][1], kc[i][2]) < 0.4:
            out.append(None)
            continue
        nariz, oe, od = kp[i][0], kp[i][1], kp[i][2]
        olhos = float(np.linalg.norm(oe - od)) or 1.0
        cx, cy = float(nariz[0]), float(nariz[1]) + 0.75 * olhos
        out.append((int(cx - 0.9 * olhos), int(cy - 0.5 * olhos), int(1.8 * olhos), int(1.1 * olhos)))
    return out


def sinal_boca(quadros, caixas):
    """Energia da boca por quadro: diferença do recorte da boca com o quadro anterior (abre/fecha)."""
    import cv2
    sinal, ant = [], None
    for f, c in zip(quadros, caixas):
        if c is None:
            sinal.append(np.nan)
            ant = None
            continue
        x, y, w, h = c
        H, W = f.shape[:2]
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
        if x1 - x0 < 4 or y1 - y0 < 4:
            sinal.append(np.nan)
            ant = None
            continue
        g = cv2.resize(cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY), (48, 32)).astype(np.float32)
        sinal.append(float(np.mean(np.abs(g - ant))) if ant is not None else np.nan)
        ant = g
    return np.array(sinal)


def audio_mono(audio, sr=16000):
    """librosa daqui não abre MP4 (take de lip-sync traz a fala dentro do vídeo): extrai com ffmpeg."""
    import librosa
    if not audio.lower().endswith((".wav", ".flac", ".ogg")):
        tmp = os.path.join(tempfile.gettempdir(), f"lip-{os.getpid()}-{abs(hash(audio))}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-vn", "-ac", "1", "-ar", str(sr), tmp], check=True)
        audio = tmp
    return librosa.load(audio, sr=sr, mono=True)


def envelope_voz(audio, fps, n):
    import librosa
    y, sr = audio_mono(audio)
    hop = int(round(sr / fps))
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop, center=True)[0]
    rms = np.pad(rms, (0, max(0, n - len(rms))))[:n]
    return np.abs(np.diff(rms, prepend=rms[0])) + 0.25 * rms  # a boca mexe quando a voz MUDA (sílabas), não só quando soa


def medir_sync(boca, voz, fps, max_lag_ms=330, nivel=None):
    """(atraso_ms, correlação, fala_com_boca, boca_sem_fala). atraso > 0 = a boca vem DEPOIS da voz."""
    ok = ~np.isnan(boca)
    if ok.sum() < max(8, 0.5 * len(boca)) or float(np.max(voz)) <= 0:
        return None
    b = np.where(ok, boca, np.nanmedian(boca))
    nv = voz if nivel is None else nivel
    fala = nv > 0.25 * float(np.max(nv))
    z = lambda x: (x - x.mean()) / (x.std() or 1.0)  # noqa: E731
    bz, vz = z(b), z(voz.astype(float))
    L = int(round(max_lag_ms * fps / 1000))
    cs = {}
    for k in range(-L, L + 1):
        a1, a2 = (bz[k:], vz[:len(vz) - k]) if k >= 0 else (bz[:k], vz[-k:])
        if len(a1) >= 8:
            cs[k] = float(np.mean(a1 * a2))
    if not cs:
        return None
    k0 = max(cs, key=cs.get)
    melhor, lag = cs[k0], float(k0)
    if k0 - 1 in cs and k0 + 1 in cs:  # pico entre quadros (interpolação parabólica): precisão abaixo de 1 quadro
        y0, y1, y2 = cs[k0 - 1], cs[k0], cs[k0 + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            lag = k0 + 0.5 * (y0 - y2) / den
    calmo = b[~fala] if (~fala).sum() >= 3 else np.array([np.percentile(b, 10)])
    limiar = float(np.median(calmo)) + 0.5 * (float(np.percentile(b, 90)) - float(np.median(calmo)))
    ativo = b > limiar
    # a boca de quem fala abre e fecha: conta quadros ativos numa janela de ±2 quadros dentro da fala
    janela = np.convolve(ativo.astype(float), np.ones(5), mode="same") > 0
    com = float(np.mean(janela[fala])) if fala.sum() else 0.0
    sem = float(np.mean(ativo[~fala])) if (~fala).sum() else 0.0
    return int(round(lag * 1000.0 / fps)), round(melhor, 3), round(com, 3), round(sem, 3)


def nivel_voz(audio, fps, n):
    import librosa
    y, sr = audio_mono(audio)
    hop = int(round(sr / fps))
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop, center=True)[0]
    return np.pad(rms, (0, max(0, n - len(rms))))[:n]


def tem_audio(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def conferir_lipsync_clipe(clip, audio=None, caixas=None):
    quadros, fps = ler_quadros(clip)
    if not quadros:
        return {"estado": ig.NAO_VERIFICADO, "pendencias": ["clipe ilegível"], "problemas": []}
    if audio is None:
        audio = clip if tem_audio(clip) else None
    if not audio:
        return {"estado": ig.NAO_VERIFICADO, "pendencias": ["sem áudio da fala"], "problemas": []}
    cx = caixas if caixas is not None else caixas_boca_yolo
    if callable(cx):
        cx = cx(quadros)
    m = medir_sync(sinal_boca(quadros, cx), envelope_voz(audio, fps, len(quadros)), fps, nivel=nivel_voz(audio, fps, len(quadros)))
    r = {"problemas": [], "pendencias": [], "fps": fps}
    if m is None:
        r["pendencias"].append("rosto/boca não encontrado na maior parte do clipe — fica a revisão visual")
    else:
        r.update(atraso_ms=m[0], correlacao=m[1], fala_com_boca=m[2], boca_sem_fala=m[3])
        if abs(m[0]) >= 290 and m[2] >= MIN_FALA_COM_BOCA:  # (boca parada é reprovação, vem antes) o pico caiu na borda da busca (±330 ms): não é atraso medido, é sinal sujo (mão na boca, corte)
            r["pendencias"].append(f"atraso no limite da busca ({m[0]} ms) — medição não confiável, fica a revisão visual")
            r["estado"] = cf_estado = estado([], r["pendencias"])
            return r
        if m[2] < MIN_FALA_COM_BOCA:
            r["problemas"].append(("grave", f"boca parada em {1 - m[2]:.0%} da fala"))
        if m[1] >= 0.25 and abs(m[0]) > MAX_ATRASO_MS:
            r["problemas"].append(("grave", f"boca fora de tempo {m[0]:+d} ms (limite ±{MAX_ATRASO_MS})"))
        elif m[1] < 0.25 and not r["problemas"]:
            r["pendencias"].append(f"sinal fraco (correlação {m[1]}) — atraso não confirmado, fica a revisão visual")
    r["estado"] = estado(r["problemas"], r["pendencias"])
    return r


def fala_em_quadro(p):
    c = p.get("direcao") or {}
    return bool(p.get("fala")) and (c.get("voz") == "em_quadro" or c.get("modo") == "fala")


def conferir_lipsync(base, d, planos=None):
    alvo = set(planos.split(",")) if planos else None
    itens = []
    for p in d["planos"]:
        if (alvo and p["id"] not in alvo) or not fala_em_quadro(p):
            continue
        clip = os.path.join(base, "assets", "clips", f"{p['id']}.mp4")
        if not os.path.exists(clip):
            itens.append({"id": p["id"], "estado": ig.NAO_VERIFICADO, "problemas": [], "pendencias": ["clipe ainda não existe"]})
            continue
        wav = os.path.join(base, "assets", "voz", f"{p['id']}.wav")
        r = conferir_lipsync_clipe(clip, None if tem_audio(clip) else (wav if os.path.exists(wav) else None))
        r.update(id=p["id"], sha256_clipe=ig.sha256(clip))
        itens.append(r)
    anteriores = {i["id"]: i for i in (ler_json(os.path.join(base, "entrega", "inspecao-lipsync.json"), {}) or {}).get("itens", [])}
    anteriores.update({i["id"]: i for i in itens})
    gravar(base, "lipsync", list(anteriores.values()), "Lip-sync medido")
    return itens


# ---------------------------------------------------------------- filme × storyboard
def similaridade(a, b):
    import cv2
    from skimage.metrics import structural_similarity
    ia, ib = cv2.imread(a), cv2.imread(b)
    if ia is None or ib is None:
        return None
    ga = cv2.resize(cv2.cvtColor(ia, cv2.COLOR_BGR2GRAY), (160, 90))
    gb = cv2.resize(cv2.cvtColor(ib, cv2.COLOR_BGR2GRAY), (160, 90))
    ssim = float(structural_similarity(ga, gb, data_range=255))
    ha = cv2.calcHist([cv2.cvtColor(ia, cv2.COLOR_BGR2HSV)], [0, 1], None, [30, 32], [0, 180, 0, 256])
    hb = cv2.calcHist([cv2.cvtColor(ib, cv2.COLOR_BGR2HSV)], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cor = float(cv2.compareHist(cv2.normalize(ha, ha), cv2.normalize(hb, hb), cv2.HISTCMP_CORREL))
    return round(ssim, 3), round(cor, 3)


PEDIDO_PLANO = """Quadro de um comercial animado. Responda JSON: {"pessoas": <nº de personagens visíveis, contando robô>,
"quem": ["descrição curta de cada um"], "enquadramento": "PG|PC|PA|PM|PP|close|detalhe"}.
PG=geral, PC=conjunto (corpo inteiro), PA=joelhos p/ cima, PM=cintura p/ cima, PP=peito p/ cima, close=rosto, detalhe=objeto/tela."""


def conferir_storyboard(base, d, video, pelo_roteiro=False, gemini=gemini_imagens, sim=similaridade):
    ts, origem = tempos(base, d, pelo_roteiro)
    fora = partes_de(d)
    ordem_rot = [p["id"] for p in d["planos"] if p["id"] not in fora]
    ordem_filme = [t["id"] for t in ts]
    planos = {p["id"]: p for p in d["planos"]}
    tmp = tempfile.mkdtemp(prefix="sb-")
    gerais, itens = [], []
    no_filme = [i for i in ordem_filme if i in ordem_rot]
    if no_filme != [i for i in ordem_rot if i in ordem_filme]:
        gerais.append(f"ordem diferente do roteiro: {' '.join(no_filme)}")
    for pid in ordem_rot:
        if pid not in ordem_filme:
            itens.append({"id": pid, "estado": ig.REPROVADO, "problemas": [("grave", "plano aprovado não entrou no filme")], "pendencias": []})
    for t in ts:
        p = planos.get(t["id"])
        r = {"id": t["id"], "problemas": [], "pendencias": [], "avisos": []}
        if not p:
            r["problemas"].append(("grave", "plano no filme que não está no roteiro aprovado"))
            r["estado"] = ig.REPROVADO
            itens.append(r)
            continue
        c = p.get("direcao") or {}
        dur, alvo = float(t["fim"]) - float(t["inicio"]), float(p.get("dur_alvo") or c.get("duracao") or 0)
        r.update(duracao=round(dur, 2), dur_alvo=alvo)
        if alvo and abs(dur - alvo) > max(0.4, 0.15 * alvo):
            r["avisos"].append(f"duração {dur:.1f}s × {alvo:.1f}s aprovada")
        meio = quadro(video, float(t["inicio"]) + dur * 0.5, os.path.join(tmp, f"{t['id']}.png"))
        ref = os.path.join(base, "assets", "img", f"{t['id']}.png")
        clip = os.path.join(base, "assets", "clips", f"{t['id']}.mp4")
        if not os.path.exists(ref) and os.path.exists(clip):
            ref = quadro(clip, 0.5, os.path.join(tmp, f"{t['id']}-ref.png"))
        if os.path.exists(ref) and not c.get("rota_fixa"):
            s = sim(meio, ref)
            if s:
                r["semelhanca"] = {"ssim": s[0], "cor": s[1]}
                if s[0] < 0.25 and s[1] < 0.3:
                    r["problemas"].append(("media", f"o quadro montado não parece o take aprovado (SSIM {s[0]}, cor {s[1]})"))
        if c.get("quem") is not None and c.get("enquadramento") and not c.get("rota_fixa"):
            v = gemini(PEDIDO_PLANO, [meio])
            if v is None:
                r["pendencias"].append("quem aparece / enquadramento (sem Gemini)")
            else:
                r["visto"] = v
                n = len(c.get("quem") or [])
                if n and int(v.get("pessoas") or 0) != n:
                    r["problemas"].append(("media", f"aparecem {v.get('pessoas')} personagens; o contrato pede {n} ({', '.join(c['quem'])})"))
                e1, e2 = c.get("enquadramento"), v.get("enquadramento")
                if e1 in ENQ and e2 in ENQ and abs(ENQ.index(e1) - ENQ.index(e2)) > 1:
                    r["avisos"].append(f"enquadramento {e2} × {e1} do contrato")
        r["estado"] = estado(r["problemas"], r["pendencias"])
        itens.append(r)
    for nome, (ini, fim) in (d.get("blocos") or {}).items():
        dentro = [t for t in ts if ini - 0.05 <= float(t["inicio"]) < fim - 0.05]
        if dentro:
            real = float(dentro[-1]["fim"]) - float(dentro[0]["inicio"])
            if abs(real - (fim - ini)) > 1.5:
                gerais.append(f"bloco {nome}: {real:.1f}s × {fim - ini:.1f}s aprovado")
    total = max((float(t["fim"]) for t in ts), default=0)
    rep, nv = gravar(base, "storyboard", itens, f"Filme × storyboard ({origem}, {total:.1f}s)", {"gerais": gerais})
    return rep + (1 if any(g.startswith("ordem") for g in gerais) else 0), nv


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["texto", "lipsync", "storyboard", "filme"])
    ap.add_argument("roteiro")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--planos")
    ap.add_argument("--pelo-roteiro", action="store_true")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.roteiro))
    d = json.load(io.open(a.roteiro, encoding="utf-8"))
    if a.modo == "lipsync":
        its = conferir_lipsync(base, d, a.planos)
        rep = sum(i["estado"] == ig.REPROVADO for i in its)
        nv = sum(i["estado"] == ig.NAO_VERIFICADO for i in its)
    else:
        if not a.video or not os.path.exists(a.video):
            sys.exit(f"{a.modo} precisa do vídeo montado")
        rep = nv = 0
        if a.modo in ("texto", "filme"):
            r, n = conferir_texto(base, d, a.video, a.pelo_roteiro)
            rep, nv = rep + r, nv + n
        if a.modo in ("storyboard", "filme"):
            r, n = conferir_storyboard(base, d, a.video, a.pelo_roteiro)
            rep, nv = rep + r, nv + n
    sys.exit(2 if rep else 3 if nv else 0)


if __name__ == "__main__":
    main()
