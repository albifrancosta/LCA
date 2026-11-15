"""Gera falas com o Gemini TTS, uma fala por arquivo WAV.

Uso:
  python tts_gemini.py falas.json -o assets/voz
  python tts_gemini.py --texto "Olá" --voz Puck -o assets/voz/teste.wav

falas.json: [{"id": "n01", "voz": "Puck", "estilo": "animado...", "texto": "..."}]
Chave: variável GEMINI_API_KEY (lida também do registro do Windows).
O texto falado usa a pronúncia de config/marca.json (a legenda mantém a grafia escrita).
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

import numpy as np

MODELO = "gemini-3.8-flash-tts"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def chave():
    import chaves
    return chaves.obter("GEMINI_API_KEY", contexto="voz e análise com o Gemini")


def falado(texto):
    """Pronúncia da marca configurada em config/marca.json (ex.: um nome estrangeiro dito em português)."""
    import marca
    return marca.falado(texto)


# ---------------------------------------------------------------- tons de voz
# Cada tom = direção para o modelo + voz sugerida. Uso: "tom": "comercial" na fala, --tom, ou "auto" (detecta pelo texto).
# Direções curtas e em inglês, como recomenda a documentação do Gemini 3.8 TTS (a fala continua em português).
# Medido em 2026-11-04 com speech_metadata.style: comercial → entonação 50→77 de variação; medo → sussurro
# (−5 dB, 30% mais lento); raiva → +47 Hz e mais forte. Nenhuma direção lida em voz alta.
TONS = {
    "comercial": ("Zephyr", "upbeat and confident TV commercial announcer, smiling, energetic"),
    "institucional": ("Kore", "calm, confident and professional"),
    "conversa": ("Puck", "casual and friendly"),
    "alegria": ("Puck", "cheerful and excited"),
    "alivio": ("Zephyr", "relieved and warm"),
    "duvida": ("Kore", "hesitant and unsure, questioning"),
    "surpresa": ("Puck", "surprised and amazed"),
    "suspense": ("Charon", "low and slow, suspenseful"),
    "medo": ("Charon", "whispered, scared and trembling"),
    "raiva": ("Fenrir", "angry and irritated, sharp"),
    "urgencia": ("Fenrir", "urgent and tense, speaking rapidly"),
    "tristeza": ("Charon", "sad and melancholic, speaking slowly"),
    "ironia": ("Puck", "sarcastic"),
}
RESERVA = "gemini-3.8-flash-lite-tts"  # cota separada (o principal tem 100 gerações/dia no Tier 1)


class CotaEsgotada(Exception):
    pass

# Rede de segurança: transcreve e corta o que vier antes da 1ª e depois da última palavra do texto, caso algum
# modelo/formato volte a ler a direção em voz alta (aconteceu com "notas de diretor" no texto, 2026-11-03).
_whisper = None


def _modelo_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("small", compute_type="int8")
    return _whisper


_NUMEROS = {"zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4", "cinco": "5",
             "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10", "onze": "11", "doze": "12", "vinte": "20", "trinta": "30"}


def _norm(s):
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]", "", s)
    return _NUMEROS.get(s, s)  # o whisper escreve "6" onde o texto diz "seis"


_UNID = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
         "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
         "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
         "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300, "quatrocentos": 400,
         "quinhentos": 500, "seiscentos": 600, "setecentos": 700, "oitocentos": 800, "novecentos": 900}


def _tokens(texto):
    """Palavras normalizadas do texto, com números por extenso agrupados em dígitos ("três mil e duzentos" → "3200")
    e "reais/real" → "r" — porque o whisper escreve "R$ 3.200"."""
    import unicodedata
    out = []
    num, parcial, aberto, ultimo = 0, 0, False, 10 ** 9
    for p in texto.split():
        base = re.sub(r"[^a-z]", "", "".join(c for c in unicodedata.normalize("NFD", p.lower()) if unicodedata.category(c) != "Mn"))
        if base in _UNID:
            v = _UNID[base]
            casa = lambda x: 4 if x >= 1000 else 3 if x >= 100 else 2 if x >= 10 else 1
            if aberto and casa(v) >= casa(ultimo):  # "sete e dois" (horário) = 7 e 2, não 9: só soma enquanto a casa desce (centena → dezena → unidade)
                out.append(str(num + parcial))
                num, parcial = 0, 0
            parcial += v
            aberto, ultimo = True, v
            continue
        if base == "mil":
            num += (parcial or 1) * 1000
            parcial, aberto, ultimo = 0, True, 1000
            continue
        if base == "e" and aberto:
            continue
        if aberto:
            out.append(str(num + parcial))
            num, parcial, aberto, ultimo = 0, 0, False, 10 ** 9
        if base in ("reais", "real"):
            out.append("r")
        elif _norm(p):
            out.append(_norm(p))
    if aberto:
        out.append(str(num + parcial))
    return out


def parecido(a, b):
    """Mesma palavra apesar da grafia do whisper: prefixo de 4 letras, número dentro de número ("1,85m"), ~80 % igual."""
    from difflib import SequenceMatcher
    if a == b or (len(a) > 3 and len(b) > 3 and a[:4] == b[:4]):
        return True
    if a.isdigit() and any(ch.isdigit() for ch in b):
        return a in re.sub(r"\D", "", b)
    if a in ("metro", "metros") and re.fullmatch(r"\d+m", b or ""):
        return True
    return len(a) > 3 and len(b) > 3 and SequenceMatcher(None, a, b).ratio() >= 0.8


def cobertura(texto, palavras):
    """Fração das palavras do texto (normalizadas, números em dígitos) que aparecem nas palavras transcritas."""
    alvo = _tokens(falado(texto))
    if not alvo:
        return 1.0
    ditas = [_norm(w) for w in palavras] + _tokens(" ".join(palavras))
    # variantes da marca que o whisper escreve contam como a mesma palavra (config/marca.json)
    import marca
    ditas = marca.unificar(ditas)
    alvo = marca.unificar(alvo)
    return sum(1 for p in alvo if any(parecido(p, d) for d in ditas)) / len(alvo)


def cortar_direcao(arq, texto):
    """Corta a direção lida em voz alta. Devolve (segundos cortados no início, fração do texto encontrada)."""
    segs, _ = _modelo_whisper().transcribe(arq, language="pt", word_timestamps=True, initial_prompt=__import__("marca").vocabulario())
    ws = [w for s in segs for w in s.words]
    alvo = _tokens(falado(texto))
    if not ws or not alvo:
        return 0.0, 0.0
    ditas = [_norm(w.word) for w in ws]
    from difflib import SequenceMatcher

    def parecido(a, b):
        if a == b or (len(a) > 3 and len(b) > 3 and a[:4] == b[:4]):
            return True
        if a.isdigit() and any(ch.isdigit() for ch in b):  # "1,85m" → "185m" contém o 1 e o 85
            return a in re.sub(r"\D", "", b)
        if a in ("metro", "metros") and re.fullmatch(r"\d+m", b or ""):
            return True
        return len(a) > 3 and len(b) > 3 and SequenceMatcher(None, a, b).ratio() >= 0.8  # Thiago × Tiago
    ini = next((i for i in range(len(ditas)) if parecido(ditas[i], alvo[0]) and (len(alvo) < 2 or i + 1 >= len(ditas) or parecido(ditas[i + 1], alvo[1]) or parecido(ditas[i + 1][:3], alvo[1][:3]))), 0)
    fim = max((i for i in range(len(ditas)) if parecido(ditas[i], alvo[-1])), default=len(ditas) - 1)
    # o whisper escreve números por extenso OU em dígitos: compara também a transcrição normalizada ("quarenta e sete" → "47")
    ditas_n = ditas[ini:fim + 1] + _tokens(" ".join(w.word for w in ws[ini:fim + 1]))
    achadas = sum(1 for p in alvo if any(parecido(p, d) for d in ditas_n)) / len(alvo)
    with wave.open(arq) as w:
        taxa, x = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    a = max(0, int((ws[ini].start - 0.08) * taxa)) if ini > 0 else 0
    b = min(len(x), int((ws[fim].end + 0.25) * taxa)) if fim < len(ws) - 1 else len(x)
    if a or b < len(x):
        y = limpar_cauda(x[a:b], taxa)
        with wave.open(arq, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(y.tobytes())
    return a / taxa, achadas


def detectar_tons(falas, contexto=""):
    """Pergunta ao Gemini qual tom do catálogo combina com cada fala. falas: [{id, texto, quem?}] → {id: tom}."""
    lista = "\n".join(f'{f["id"]} ({f.get("quem", "narrador")}): {f["texto"]}' for f in falas)
    pedido = (f"Vídeo: {contexto or 'vídeo curto para redes sociais'}.\nPara cada fala abaixo, escolha UM tom de voz desta lista: "
              f"{', '.join(TONS)}.\nNarração de anúncio de produto = comercial; personagem falando no dia a dia = conversa; "
              f"use medo/raiva/dúvida/surpresa etc. quando o texto pedir.\nResponda só JSON {{id: tom}}.\n\n{lista}")
    corpo = {"contents": [{"parts": [{"text": pedido}]}], "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(URL.format(m="gemini-3.8-flash"), data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    tons = json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
    return {k: (v if v in TONS else "conversa") for k, v in tons.items()}


def sintetizar(texto, voz, estilo, saida, modelo=MODELO, tentativas=3, tom=None):
    """Gera a fala. `tom` (do catálogo TONS) ou `estilo` (texto livre curto, em inglês) definem a entonação.
    Esgotou a cota do modelo principal → usa a reserva (Lite) automaticamente."""
    if tom:
        voz = voz or TONS[tom][0]
        estilo = f"{TONS[tom][1]}, {estilo}" if estilo else TONS[tom][1]
    try:
        return _sintetizar_tentando(texto, voz, estilo, saida, modelo, tentativas)
    except CotaEsgotada as e:
        if modelo == RESERVA:
            sys.exit(f"cota esgotada também na reserva: {e}")
        print(f"  cota do {modelo} esgotada — usando {RESERVA}", file=sys.stderr)
        return _sintetizar_tentando(texto, voz, estilo, saida, RESERVA, tentativas)


def _sintetizar_tentando(texto, voz, estilo, saida, modelo, tentativas):
    if not estilo:
        limite = len(falado(texto).split()) / 2.0 * 1.5 + 1.5
        for _ in range(tentativas + 1):
            d = _sintetizar(texto, voz, "", saida, modelo)
            if d <= limite:
                return d
            print(f"  {os.path.basename(saida)}: {d:.1f}s > {limite:.1f}s (leu algo a mais?) — gerando de novo", file=sys.stderr)
        sys.exit(f"{saida}: duração fora do esperado")
    melhor = (0.0, b"")
    for _ in range(tentativas):
        _sintetizar_com_tom(texto, voz, estilo, saida, modelo)
        cortado, achadas = cortar_direcao(saida, texto)  # rede de segurança
        if cortado:
            print(f"  {os.path.basename(saida)}: cortei {cortado:.1f}s lidos a mais no início", file=sys.stderr)
        # Plano 47 (2026-11-06): com mínimo de 50 % em fala curta, "Plano quarenta e sete" saiu "Plano corento e sete" e passou.
        # Fala curta agora exige TODAS as palavras; números já comparados normalizados.
        minimo = 0.85 if len(_tokens(texto)) > 5 else 1.0
        if achadas >= minimo:
            if os.path.exists(saida + ".suspeita"):
                os.remove(saida + ".suspeita")
            return duracao_wav(saida)
        if achadas > melhor[0]:
            melhor = (achadas, open(saida, "rb").read())
        print(f"  {os.path.basename(saida)}: só {achadas:.0%} do texto reconhecido — gerando de novo", file=sys.stderr)
    if melhor[1] and len(_tokens(texto)) <= 5 and melhor[0] >= 0.5:
        # fala curta: fica a melhor tentativa, MARCADA — o inspetor (inspetor.py audio) e você conferem de ouvido
        open(saida, "wb").write(melhor[1])
        open(saida + ".suspeita", "w", encoding="utf-8").write(f"{melhor[0]:.0%} reconhecido: {texto}")
        print(f"  ⚠️ {os.path.basename(saida)}: SUSPEITA ({melhor[0]:.0%} reconhecido) — confira de ouvido", file=sys.stderr)
        return duracao_wav(saida)
    sys.exit(f"{saida}: o texto não saiu completo com o tom pedido; revise o texto ou use outro tom")


def duracao_wav(arq):
    with wave.open(arq) as w:
        return w.getnframes() / w.getframerate()


def _sintetizar(texto, voz, estilo, saida, modelo, tentativas=3):
    # Direção em seções separadas da transcrição: "estilo: texto" faz o modelo ler a direção em voz alta,
    # e systemInstruction não é aceito pelo modelo de TTS.
    prompt = falado(texto)
    if estilo:
        prompt = f"### DIRECTOR'S NOTES\n{estilo}\n\n### TRANSCRIPT (leia somente isto)\n{prompt}"
    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }
    req = urllib.request.Request(
        URL.format(m=modelo), data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave()},
    )
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code == 429 and ("per day" in msg or "requests per day" in msg):
                raise CotaEsgotada(msg)  # cota diária: não adianta esperar segundos
            if e.code in (429, 500, 503) and n < tentativas - 1:
                time.sleep(5 * (n + 1))
                continue
            sys.exit(f"Gemini TTS {e.code}: {msg}")
    parte = resp["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
    taxa = int(m.group(1)) if m else 24000
    x = limpar_cauda(np.frombuffer(base64.b64decode(parte["data"]), dtype=np.int16), taxa)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(x.tobytes())
    return len(x) / taxa


def _sintetizar_com_tom(texto, voz, estilo, saida, modelo, tentativas=3):
    """Formato oficial do Gemini 3.8 TTS (docs speech-generation, 2026-11): o tom vai em speech_metadata.style,
    separado do texto, pela Interactions API — assim o modelo não lê a direção em voz alta.
    Tags pontuais vão no próprio texto, em inglês: <short pause>, <long pause>, <sigh>, <laugh>, <breath>, <gasp>."""
    import io
    corpo = {
        "model": modelo,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": falado(texto),
                                                       "annotations": [{"type": "speech_metadata", "style": estilo}]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voz}]},
    }
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions", data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code == 429 and ("per day" in msg or "requests per day" in msg):
                raise CotaEsgotada(msg)  # cota diária: não adianta esperar segundos
            if e.code in (429, 500, 503) and n < tentativas - 1:
                time.sleep(5 * (n + 1))
                continue
            sys.exit(f"Gemini TTS {e.code}: {msg}")
    audios = [c for s in resp.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
    if not audios:
        sys.exit(f"Gemini TTS sem áudio na resposta: {json.dumps(resp)[:300]}")
    dados = base64.b64decode(audios[-1]["data"])
    if dados[:4] == b"RIFF":  # unário: WAV completo
        with wave.open(io.BytesIO(dados)) as w:
            taxa, x = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    else:
        taxa, x = 24000, np.frombuffer(dados, dtype=np.int16)
    x = limpar_cauda(x, taxa)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(x.tobytes())
    return len(x) / taxa


def limpar_cauda(x, taxa, janela=0.02):
    """Corta o estouro de chiado que o Gemini TTS põe no fim de todo áudio.

    Medido em 2026-11-03 (17 arquivos, 4 vozes): depois da fala vem um silêncio (< -45 dB) e, nos últimos
    0,1–0,3 s, um ruído a -3/-10 dB — mais alto que a própria voz. Corta a partir do silêncio que o antecede,
    deixa 0,12 s de silêncio e aplica fade de 15 ms nas pontas.
    """
    y = x.astype(np.float32) / 32768
    n = int(janela * taxa)
    db = [20 * np.log10(np.sqrt(np.mean(y[i:i + n] ** 2)) + 1e-9) for i in range(0, len(y), n)]
    k = len(db) - 1
    while k > 0 and db[k] > -25:  # o estouro (de trás para frente)
        k -= 1
    estouro = (len(db) - 1 - k) * janela
    # 2026-11-06: "de mil e… duzentos reais" — a última palavra depois de uma pausa curta era cortada como se fosse o
    # estouro. O estouro medido é MAIS ALTO que a voz (−3/−10 dB); uma palavra final tem o nível da fala. Só corta trecho
    # final curto (≤ 0,4 s) que esteja ≥ 2 dB acima do nível da fala (percentil 90 dos quadros antes do silêncio).
    antes = [v for v in db[: max(1, k)] if v > -45]
    nivel_fala = float(np.percentile(antes, 90)) if antes else -20.0
    pico_cauda = max(db[k + 1:]) if k + 1 < len(db) else -99.0
    if 0 < estouro <= 0.4 and db[k] < -45 and pico_cauda >= nivel_fala + 2:  # estouro, não palavra — nunca come fala
        while k > 0 and db[k] < -45:  # recua o silêncio até o fim da fala
            k -= 1
        y = y[: min(len(y), (k + 1) * n + int(0.12 * taxa))]
    f = int(0.015 * taxa)
    rampa = np.linspace(0, 1, f)
    y[:f] *= rampa
    y[-f:] *= rampa[::-1]
    return (y * 32767).astype(np.int16)


def duracao(arq):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("falas", nargs="?")
    ap.add_argument("--texto")
    ap.add_argument("--voz", default=None, help="voz; sem ela usa a sugerida pelo tom (ou Puck)")
    ap.add_argument("--estilo", default="", help="direção livre curta em inglês (ex.: 'warm and enthusiastic')")
    ap.add_argument("--tom", help=f"tom de voz: {', '.join(TONS)} ou 'auto' (detecta pelo texto de cada fala)")
    ap.add_argument("--contexto", default="", help="tipo de vídeo, para o --tom auto (ex.: 'comercial de ERP')")
    ap.add_argument("--tons", action="store_true", help="lista os tons disponíveis")
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--so", help="gera só estes ids (vírgula)")
    ap.add_argument("--limpar", nargs="+", help="só corta o estouro final de WAVs já gerados (sobrescreve)")
    ap.add_argument("-o", "--saida")
    a = ap.parse_args()
    if a.tons:
        for nome, (voz, est) in TONS.items():
            print(f"{nome:14} voz {voz:7}  {est}")
        return
    if a.limpar:
        for arq in a.limpar:
            with wave.open(arq) as w:
                taxa = w.getframerate()
                x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            y = limpar_cauda(x, taxa)
            with wave.open(arq, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(taxa)
                w.writeframes(y.tobytes())
            print(f"{arq}: {len(x) / taxa:.2f}s -> {len(y) / taxa:.2f}s")
        return
    if not a.saida:
        ap.error("-o/--saida é obrigatório")
    if a.texto:
        tom = detectar_tons([{"id": "x", "texto": a.texto}], a.contexto)["x"] if a.tom == "auto" else a.tom
        d = sintetizar(a.texto, a.voz or (TONS[tom][0] if tom else "Puck"), a.estilo, a.saida, a.modelo, tom=tom)
        print(f"{a.saida}  {d:.2f}s  tom={tom or '—'}")
        return
    falas = json.load(open(a.falas, encoding="utf-8"))
    so = set(a.so.split(",")) if a.so else None
    alvo = [f for f in falas if not so or f["id"] in so]
    # tom por fala: campo "tom" da fala > --tom > nenhum; "auto" pede ao Gemini (texto + contexto do vídeo)
    pedir_auto = [f for f in alvo if (f.get("tom") or a.tom) == "auto"]
    auto = detectar_tons(pedir_auto, a.contexto) if pedir_auto else {}
    for f in alvo:
        tom = f.get("tom") or a.tom
        tom = auto.get(f["id"], "conversa") if tom == "auto" else tom
        if tom and tom not in TONS:
            sys.exit(f"{f['id']}: tom '{tom}' não existe. Use: {', '.join(TONS)}")
        voz = f.get("voz") or a.voz or (TONS[tom][0] if tom else "Puck")
        arq = os.path.join(a.saida, f"{f['id']}.wav")
        sintetizar(f["texto"], voz, f.get("estilo", a.estilo), arq, a.modelo, tom=tom)
        print(f"{f['id']:6} {duracao(arq):5.2f}s  {voz:8} tom={tom or '—':13} {f['texto'][:55]}")


if __name__ == "__main__":
    main()
