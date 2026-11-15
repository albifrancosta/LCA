"""Ficha de personagem em várias vistas + grade de 9 câmeras (3×3) numa única imagem.

Ideia adaptada do guia de prompts do AID Studio (github.com/shijue-aid/aid-studio, licença MIT).
Usa `gerar_imagem.py` por baixo (mesmo cache, mesmo livro-caixa). Sem --confirmar só mostra o prompt e o custo.

Uso:
  # 1) ficha: rosto em close + corpo de frente/lado/costas + 6 expressões, tudo numa imagem horizontal
  python ficha_grade.py ficha -o assets/ilustrado/ficha-cliente.png --descricao "mulher ~35, cabelo cacheado preso, blusa verde-água" [--ref foto-ou-esboço.png] --confirmar
  # 2) grade: o mesmo momento em 9 ângulos de câmera (1 imagem ≈ US$ 0,05 em vez de 9 ≈ US$ 0,45) e recorte automático
  python ficha_grade.py grade -o assets/ilustrado/g1.png --ref assets/ilustrado/ficha-cliente.png \
      --momento "ela aprova o orçamento no celular, atrás do balcão da loja de roupas, fim de tarde" --confirmar
  # 3) só recortar uma grade já gerada (grátis)
  python ficha_grade.py recortar assets/ilustrado/g1.png [--ampliar 2]

Saída da grade: g1.png (a grade), g1-01-geral.png … g1-09-plongee.png e g1.angulos.json.
Atenção: cada quadro tem ~340×510 px. Serve para storyboard, quadro inicial de clipe (o modelo de vídeo refaz em 720p)
e fundo com desfoque/zoom leve. Para um plano "herói" em tela cheia, refaça só ele com
`gerar_imagem.py "<mesmo momento, ângulo X>" --ref ficha.png --ref g1-0X.png` (US$ 0,05).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = Path(__file__).parent
ESTILO = ("cinematic 2D illustration, clean confident linework, soft painterly shading, "
          "warm natural light, Brazilian small-business setting")
PRECO = {"low": 0.012, "medium": 0.05, "high": 0.19}

# (rótulo do arquivo, nome em pt, descrição para o prompt)
ANGULOS = [
    ("geral", "plano geral (ambiente)", "extreme wide establishing shot, whole environment visible, subject small"),
    ("inteiro", "plano inteiro", "wide shot, full body head to toe"),
    ("medio", "plano médio", "medium shot, waist up"),
    ("americano", "plano próximo", "medium close-up, chest up"),
    ("close", "close no rosto", "close-up on the face, emotion readable"),
    ("detalhe", "detalhe (mãos/objeto)", "extreme close-up on the hands or the key object of the moment"),
    ("ombro", "sobre o ombro", "over-the-shoulder shot from behind the subject, looking at what they look at"),
    ("contra", "contra-plongée", "low angle looking up at the subject, heroic"),
    ("plongee", "plongée (de cima)", "high angle looking down at the subject"),
]


def prompt_ficha(descricao, estilo, tem_ref):
    identidade = ("The attached reference image is the ONLY source of identity: copy exactly the face, hair, skin tone, "
                  "body type and outfit. " if tem_ref else "")
    return (
        f"Character model sheet of ONE person: {descricao}. {identidade}"
        "Wide horizontal sheet on a plain light-grey background, three zones from left to right: "
        "(1) LEFT: large head-and-shoulders portrait, front view, neutral expression; "
        "(2) CENTER: the same person full body in three poses side by side: front view, side view, back view, "
        "standing straight, same scale, feet visible; "
        "(3) RIGHT: a 2x3 grid of the same face with six expressions: happy, worried, surprised, angry, relieved, thinking. "
        "The person must be identical in every view (same face, hair, clothes, colors, proportions). "
        f"Style: {estilo}. Even studio light, no shadows on the background. "
        "Absolutely no text, no labels, no numbers, no arrows, no watermark."
    )


def prompt_grade(momento, estilo):
    lista = "; ".join(f"panel {i} ({['top-left','top-center','top-right','middle-left','center','middle-right','bottom-left','bottom-center','bottom-right'][i-1]}): {a[2]}"
                      for i, a in enumerate(ANGULOS, 1))
    return (
        f"A 3x3 storyboard grid of nine panels showing the SAME moment from nine different camera angles: {momento}. "
        "The attached reference image is the ONLY source of identity for the character(s): same face, hair, clothes and colors in all panels. "
        "Same location, same props, same time of day and lighting in every panel; only the camera changes. "
        f"Panels in reading order — {lista}. "
        "Each panel is a vertical 2:3 frame. Panels separated by thin, straight, uniform white gutters; no border around the whole grid. "
        f"Style: {estilo}. Absolutely no text, no captions, no panel numbers, no speech balloons, no watermark."
    )


def gerar(prompt, saida, formato, refs, qualidade, confirmar):
    preco = PRECO[qualidade]
    print(f"custo: ~US$ {preco:.3f} (1 imagem gpt-image, {qualidade}, {formato}) · cache evita pagar 2× o mesmo pedido")
    print(f"prompt:\n  {prompt}\n")
    if not confirmar:
        print("Nada foi gerado. Rode de novo com --confirmar para gastar.")
        return False
    cmd = [sys.executable, str(AQUI / "gerar_imagem.py"), prompt, "-o", str(saida), "--formato", formato, "--qualidade", qualidade,
           "--confirmar"]  # o usuário já confirmou o gasto neste script
    for r in refs:
        cmd += ["--ref", r]
    subprocess.run(cmd, check=True)
    return True


def _cortes(perfil, n):
    """Posições das 2 calhas (divisões) perto de 1/3 e 2/3, onde a faixa é mais clara e uniforme."""
    import numpy as np
    cortes = []
    for frac in (1 / 3, 2 / 3):
        c, janela = int(n * frac), max(4, int(n * 0.06))
        trecho = perfil[c - janela:c + janela]
        cortes.append(c - janela + int(np.argmax(trecho)))
    return cortes


def recortar(grade, ampliar=1):
    import numpy as np
    from PIL import Image
    img = Image.open(grade).convert("RGB")
    a = np.asarray(img).astype(float)
    # calha branca = brilho alto e pouca variação ao longo da linha/coluna
    col = a.mean(axis=(0, 2)) - a.std(axis=(0, 2))
    lin = a.mean(axis=(1, 2)) - a.std(axis=(1, 2))
    xs = [0, *_cortes(col, a.shape[1]), a.shape[1]]
    ys = [0, *_cortes(lin, a.shape[0]), a.shape[0]]
    margem = max(3, int(min(a.shape[:2]) * 0.008))
    base = Path(grade)
    saidas = []
    for i, (rot, nome, _) in enumerate(ANGULOS):
        r, c = divmod(i, 3)
        caixa = (xs[c] + margem, ys[r] + margem, xs[c + 1] - margem, ys[r + 1] - margem)
        q = img.crop(caixa)
        if ampliar > 1:  # ampliação grátis (Lanczos) — melhora pouco; para plano herói, refaça a imagem
            q = q.resize((q.width * ampliar, q.height * ampliar), Image.LANCZOS)
        destino = base.with_name(f"{base.stem}-{i + 1:02d}-{rot}.png")
        q.save(destino)
        saidas.append({"arquivo": destino.name, "angulo": nome, "tamanho": list(q.size)})
    base.with_suffix(".angulos.json").write_text(json.dumps(saidas, ensure_ascii=False, indent=1), encoding="utf-8")
    for s in saidas:
        print(f"  {s['arquivo']:28} {s['angulo']:24} {s['tamanho'][0]}×{s['tamanho'][1]}")
    print(f"9 quadros em {base.parent} (confira se o recorte não pegou a calha; se pegou, recorte à mão)")
    return saidas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modo", required=True)
    f = sub.add_parser("ficha")
    f.add_argument("-o", "--out", required=True)
    f.add_argument("--descricao", required=True)
    f.add_argument("--ref", action="append", default=[], help="foto/esboço do personagem (vira a única identidade)")
    g = sub.add_parser("grade")
    g.add_argument("-o", "--out", required=True)
    g.add_argument("--ref", action="append", required=True, help="ficha do personagem (repita para 2 personagens / cenário)")
    g.add_argument("--momento", required=True, help="o que acontece, onde e quando (1 frase)")
    g.add_argument("--ampliar", type=int, default=1)
    for p in (f, g):
        p.add_argument("--estilo", default=ESTILO)
        p.add_argument("--qualidade", default="medium", choices=list(PRECO))
        p.add_argument("--confirmar", action="store_true")
    r = sub.add_parser("recortar")
    r.add_argument("grade")
    r.add_argument("--ampliar", type=int, default=1)
    a = ap.parse_args()

    if a.modo == "recortar":
        recortar(a.grade, a.ampliar)
        return
    for ref in a.ref:
        if not Path(ref).exists():
            sys.exit(f"referência não encontrada: {ref}")
    if a.modo == "ficha":
        gerar(prompt_ficha(a.descricao, a.estilo, bool(a.ref)), a.out, "horizontal", a.ref, a.qualidade, a.confirmar)
    else:
        if gerar(prompt_grade(a.momento, a.estilo), a.out, "vertical", a.ref, a.qualidade, a.confirmar):
            recortar(a.out, a.ampliar)


if __name__ == "__main__":
    main()
