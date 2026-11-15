"""Kit de publicação de um vídeo pronto: capa, legenda do post, hashtags, roteiro da 1ª hora e versões por plataforma.

Uso (na pasta do projeto):
  python kit_publicacao.py entrega/video.mp4 --briefing BRIEFING.md [--capa-t 1.0] [--capa-texto "Cadê o técnico?"]
                           [--b entrega/video-B.mp4] [-o entrega/kit]

Gera em <saída>/:
  capa.jpg            1080×1920 — quadro do vídeo + título grande (≤ 6 palavras), área segura do Reels/TikTok
  capa-grade.jpg      1080×1350 (recorte 4:5 da capa, como aparece na grade do Instagram)
  reels-tiktok.mp4    cópia do vídeo (9:16)        · shorts.mp4 (cópia; avisa se passar de 60 s)
  video-B.mp4         abertura B, se houver (--b)  — publicar dias depois ou como teste do Reels
  KIT.md              legenda, hashtags, comentário fixado, título do Shorts, roteiro da 1ª hora, checklist
Textos: gemini-3.8-flash a partir do BRIEFING.md (sem a chave, usa um modelo pronto para editar).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
VERDE = (135, 201, 104)
FONTES = ["C:/Windows/Fonts/seguibl.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]


def duracao(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def fonte(tam):
    for f in FONTES:
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def quebrar(draw, texto, f, largura):
    linhas, atual = [], ""
    for p in texto.split():
        teste = (atual + " " + p).strip()
        if draw.textlength(teste, font=f) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    return linhas + ([atual] if atual else [])


def capa(video, t, texto, destino):
    quadro = destino + ".tmp.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", quadro], check=True)
    im = Image.open(quadro).convert("RGB")
    os.remove(quadro)
    # escurece a faixa do texto para leitura
    sombra = Image.new("L", im.size, 0)
    ds = ImageDraw.Draw(sombra)
    for y in range(500, 1300):
        ds.line([(0, y), (1080, y)], fill=int(200 * (1 - abs(y - 900) / 400) ** 0.5))
    im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, sombra)
    d = ImageDraw.Draw(im)
    tam = 130
    while True:
        f = fonte(tam)
        linhas = quebrar(d, texto.upper(), f, 900)
        if len(linhas) <= 3 or tam <= 70:
            break
        tam -= 10
    alt = tam * 1.15
    y0 = 900 - alt * len(linhas) / 2
    for i, ln in enumerate(linhas):
        w = d.textlength(ln, font=f)
        x, y = (1080 - w) / 2, y0 + i * alt
        cor = VERDE if i == len(linhas) - 1 else (255, 255, 255)
        d.text((x, y), ln, font=f, fill=cor, stroke_width=8, stroke_fill=(0, 0, 0))
    im.save(destino, quality=92)
    # recorte 4:5 central (a grade do Instagram mostra o centro da capa)
    im.crop((0, 285, 1080, 1635)).save(destino.replace("capa.jpg", "capa-grade.jpg"), quality=92)


PEDIDO = """Você é social media de uma empresa de software (MinhaMarca) que publica vídeos curtos no Reels, TikTok e Shorts.
A partir do briefing abaixo, escreva em português do Brasil, tom humano e direto (sem clichês de marketing, sem emojis em excesso):
- "capa": título da capa, no máximo 6 palavras, que se entende sem som
- "legenda": legenda do post, 3–5 linhas curtas: 1ª linha repete a dor como gancho; meio conta a virada; fim com CTA "Peça uma demonstração" (link na bio). Nunca peça "comente A ou B".
- "comentario_fixado": comentário do perfil para fixar, que puxa conversa de quem é do ramo (pergunta aberta sobre a rotina deles)
- "hashtags": lista de 5 a 8 hashtags: 2 amplas, 3–4 do nicho do público, 1 da marca (#MinhaMarca)
- "titulo_shorts": título do YouTube Shorts, até 60 caracteres
- "primeira_hora": lista de 4–6 ações para a 1ª hora depois de postar (responder comentários, enviar para quem, stories, grupos do ramo), específicas para este público
Responda só JSON com essas chaves.

BRIEFING:
"""


SEM_MARCA = {  # vídeo sem marca (curiosidade, teste, conteúdo): CTA = compartilhar/salvar, sem #MinhaMarca
    'fim com CTA "Peça uma demonstração" (link na bio)': 'fim convidando a mandar para alguém ou salvar (sem vender nada, sem link)',
    "puxa conversa de quem é do ramo (pergunta aberta sobre a rotina deles)": "puxa conversa sobre o assunto do vídeo (pergunta aberta e leve)",
    "3–4 do nicho do público, 1 da marca (#MinhaMarca)": "3–4 do assunto do vídeo; NENHUMA hashtag de marca",
    "(responder comentários, enviar para quem, stories, grupos do ramo), específicas para este público": "(responder comentários, stories, enviar para quem gosta do assunto)",
}


def textos(briefing, sem_marca=False):
    try:
        from tts_gemini import chave
        k = chave()
    except SystemExit:
        return None
    pedido = PEDIDO
    if sem_marca:
        pedido = pedido.replace("empresa de software (MinhaMarca)", "criador de conteúdo")
        for de, para in SEM_MARCA.items():
            pedido = pedido.replace(de, para)
    corpo = {"contents": [{"parts": [{"text": pedido + briefing}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": k})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.load(r)
        return json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:  # noqa: BLE001 — sem texto automático, o kit sai com modelo para editar
        print("aviso: textos automáticos falharam:", e)
        return None


MODELO = {"capa": "<título da capa>", "legenda": "<dor>\n<virada>\nPeça uma demonstração — link na bio.",
          "comentario_fixado": "<pergunta para quem é do ramo>", "hashtags": ["#empreendedorismo", "#gestao", "#MinhaMarca"],
          "titulo_shorts": "<título>", "primeira_hora": ["Responder todos os comentários na 1ª hora",
                                                        "Mandar no WhatsApp para 5 clientes do ramo", "Repostar nos stories com enquete"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--briefing", default="BRIEFING.md")
    ap.add_argument("--capa-t", type=float, default=1.0, help="segundo do quadro usado na capa")
    ap.add_argument("--capa-texto", help="título da capa (senão vem do Gemini)")
    ap.add_argument("--b", help="vídeo com a abertura B (teste A/B do gancho)")
    ap.add_argument("-o", "--saida", default="entrega/kit")
    ap.add_argument("--sem-marca", action="store_true", help="vídeo sem MinhaMarca: CTA de compartilhar, sem #MinhaMarca nem 'peça uma demonstração'")
    a = ap.parse_args()

    os.makedirs(a.saida, exist_ok=True)
    br = open(a.briefing, encoding="utf-8").read() if os.path.exists(a.briefing) else ""
    tx = textos(br, a.sem_marca) or MODELO
    titulo = a.capa_texto or tx.get("capa") or "Assista até o fim"
    capa(a.video, a.capa_t, titulo, os.path.join(a.saida, "capa.jpg"))

    dur = duracao(a.video)
    shutil.copy(a.video, os.path.join(a.saida, "reels-tiktok.mp4"))
    shutil.copy(a.video, os.path.join(a.saida, "shorts.mp4"))
    if a.b:
        shutil.copy(a.b, os.path.join(a.saida, "video-B.mp4"))

    hashtags = " ".join(tx.get("hashtags", []))
    md = [f"# Kit de publicação — {os.path.basename(a.video)}", "",
          f"Duração {dur:.1f} s · capa `capa.jpg` (quadro de {a.capa_t:.1f} s, título \"{titulo}\") · grade `capa-grade.jpg`", "",
          "## Legenda do post (Reels / TikTok)", "", tx.get("legenda", ""), "", hashtags, "",
          "## Comentário para fixar", "", tx.get("comentario_fixado", ""), "",
          "## YouTube Shorts", "", f"Título: **{tx.get('titulo_shorts', '')}**  ", "Descrição: a mesma legenda + hashtags.", ""]
    if dur > 60:
        md.append(f"⚠️ {dur:.0f} s: o Shorts aceita até 3 min, mas acima de 60 s perde alcance — considere um corte curto (`variantes_moviepy.py`).\n")
    md += ["## Primeira hora depois de postar", ""] + [f"- [ ] {p}" for p in tx.get("primeira_hora", [])] + [""]
    md += ["## Checklist por plataforma", "",
           "| | Reels | TikTok | Shorts |", "|---|---|---|---|",
           "| Arquivo | `reels-tiktok.mp4` | `reels-tiktok.mp4` | `shorts.mp4` |",
           "| Capa | `capa.jpg` (conferir recorte da grade) | escolher o quadro da capa no app | automática (quadro) |",
           "| Áudio | áudio original (a trilha já está no vídeo); se quiser alcance extra, adicione um som em alta do app com volume bem baixo (≤ 10%) | idem | — |",
           "| Horário sugerido | 11h–13h ou 18h–20h em dia útil (público dono de empresa) | idem | idem |", ""]
    if a.b:
        md += ["## Abertura B (teste do gancho)", "",
               "`video-B.mp4`: publique 3–7 dias depois com a mesma legenda, ou use o teste A/B do Reels se disponível.",
               "Compare a **retenção em 3 s** das duas em `metricas.py`.", ""]
    md += ["## Depois de 48 h e de 7 dias", "",
           "Anote os números com `python scripts/metricas.py` (views, retenção 3 s, % assistido, compartilhamentos, comentários) — ele atualiza a pontuação dos padrões usados.", ""]
    if tx is MODELO:
        md.insert(2, "⚠️ Textos automáticos indisponíveis (sem GEMINI_API_KEY ou erro): edite os campos entre < >.\n")
    open(os.path.join(a.saida, "KIT.md"), "w", encoding="utf-8").write("\n".join(md))
    json.dump(tx, open(os.path.join(a.saida, "textos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n".join(md))


if __name__ == "__main__":
    main()
