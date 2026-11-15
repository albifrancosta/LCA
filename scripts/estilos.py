"""Catálogo de técnicas de animação e ESTILOS VISUAIS (inclui live-action: filme com pessoas reais/fotorrealista).
Separa a TÉCNICA (como é produzido: 2D, 3D, stop motion, live-action…) do ESTILO (a cara: cartoon, anime, caricatura…).
Cada estilo traz o prefixo de prompt (descritivo, SEM nome de estúdio/filme/personagem de terceiros), o que evitar,
para que histórias funciona, como animar e o custo típico.

Uso:
  python estilos.py listar [--genero romance]        → tabela (com o gênero: os que mais combinam primeiro)
  python estilos.py tecnicas                         → técnicas de produção
  python estilos.py mostrar anime-romantico          → ficha completa do estilo
  python estilos.py comparar --personagem "rapaz de 19 anos, óculos redondos, moletom mostarda" \
        --cena "debaixo de um poste numa noite de chuva, escrevendo num caderninho" \
        --estilos cartoon-3d,anime,cartoon-2d-moderno,aquarela,caricatural,live-action [--qualidade low] [--confirmar]
        → o MESMO personagem e a MESMA cena em cada estilo + folha comparativa (assets/estilos/comparar.png).
          Sem --confirmar mostra só o custo. low ≈ US$ 0,012 por estilo (6 estilos ≈ US$ 0,07).
  python estilos.py aplicar ilustracao-2d --projeto .  → grava o estilo na bíblia (producao.json: estilo_id, estilo, tecnica)
Regras: personagens sempre ORIGINAIS; referências são só para o usuário entender o visual (nunca vão no prompt).
Live-action: só pessoas fictícias geradas por IA (ou gente real com autorização por escrito); nunca o rosto de alguém real
sem consentimento, nem celebridade; marcar "conteúdo gerado por IA" quando a plataforma pedir.
"""
import argparse
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

TECNICAS = {
    "2d-tradicional": "desenhado quadro a quadro (na IA: imagens 2D + clipes que mantêm o traço)",
    "2d-digital": "desenho produzido e animado digitalmente (imagens 2D + clipes IA ou zoom/camadas)",
    "3d-cgi": "personagens e cenários tridimensionais (imagens 3D + clipes IA — os modelos de vídeo animam 3D muito bem)",
    "2.5d": "elementos 2D em camadas com profundidade (parallax no Remotion, quase grátis)",
    "stop-motion": "bonecos/objetos fotografados quadro a quadro (na IA: imagem com textura física + clipe com 12 fps)",
    "claymation": "stop motion com massinha (textura de massa, digitais, 12 fps)",
    "cut-out": "personagens articulados por partes recortadas (papel/feltro; anima bem em Remotion por partes)",
    "rotoscopia": "desenho por cima de movimento filmado (motion control: vídeo seu → estilo desenhado)",
    "motion-graphics": "textos, formas e gráficos animados (Remotion, grátis)",
    "live-action": "filmagem real ou fotorrealista gerada por IA (pessoas e lugares com aparência real)",
    "hibrido": "combinação de técnicas (ex.: ilustração na dor + motion na solução; live-action + gráficos)",
}

# id: técnica, nome, prefixo do prompt (inglês, descritivo), negativo, bom para, animação, custo, referência (só para o usuário)
ESTILOS = {
    "ilustracao-2d": dict(tecnica="2d-digital", nome_en="a cinematic hand-drawn 2D illustration", nome="Ilustração 2D cinematográfica",
        prompt="cinematic 2D illustration, clean confident linework, soft painterly shading, dramatic film lighting, expressive original characters",
        evitar="3D render, photo, anime eyes", bom="comédia, romance, drama, anúncio — o padrão aprovado do estúdio",
        anima="clipes IA nos momentos de ação + zoom/camadas", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="o padrão dos vídeos da MinhaMarca e do Plano nº 47", generos=["comedia", "romance", "drama", "anuncio"]),
    "cartoon-3d": dict(tecnica="3d-cgi", nome_en="a 3D CGI animated movie frame", nome="Cartoon 3D cinematográfico",
        prompt="full 3D CGI render, a frame from a modern 3D animated feature film, rounded stylized 3D character with big expressive eyes, subsurface scattering skin, ray-traced global illumination, volumetric light, shallow depth of field, smooth plastic-free 3D materials",
        evitar="2D drawing, painting, line art, flat colors, realistic photo, uncanny realism", bom="romance, comédia, aventura, família",
        anima="clipes IA (3D anima muito bem)", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra os longas 3D de estúdio (tipo Enrolados, Frozen)", generos=["romance", "comedia", "aventura", "familia"]),
    "cartoon-2d-sitcom": dict(tecnica="2d-digital", nome_en="a flat 2D TV sitcom cartoon", nome="Cartoon 2D sitcom",
        prompt="flat 2D sitcom cartoon, simple bold outlines, flat saturated colors, exaggerated expressions, simple domestic backgrounds",
        evitar="shading, 3D, realism, any existing show's characters or yellow-skinned family", bom="humor cotidiano, diálogos, série com episódios",
        anima="motion por partes + poucos clipes; barato para série longa", custo="imagem US$ 0,05 · muito motion grátis",
        ref="lembra sitcoms animadas de TV (tipo Os Simpsons)", generos=["comedia", "serie"]),
    "cartoon-2d-moderno": dict(tecnica="2d-digital", nome_en="a flat vector 2D web cartoon", nome="Cartoon 2D moderno (web série)",
        prompt="modern flat 2D vector cartoon for a web series, flat solid colors with NO gradients and NO painterly texture, thick uniform outlines, simplified shapes, limited palette, minimal simple backgrounds",
        evitar="3D, photo, painterly texture", bom="diálogos rápidos, humor do dia a dia, personagens recorrentes",
        anima="motion graphics + cut-out; quase tudo grátis", custo="imagem US$ 0,05 · animação grátis",
        ref="séries animadas curtas de rede social", generos=["comedia", "serie", "romance"]),
    "anime": dict(tecnica="2d-digital", nome_en="a Japanese anime film frame", nome="Anime japonês",
        prompt="Japanese anime style, cel-shaded characters with large expressive eyes, detailed hair, atmospheric painted backgrounds, dramatic sky and light rays",
        evitar="3D render, western cartoon, photo, any existing anime character", bom="romance, drama, fantasia",
        anima="clipes IA curtos + zoom/parallax no cenário", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra longas de anime (tipo Your Name)", generos=["romance", "drama", "fantasia"]),
    "anime-romantico": dict(tecnica="2d-digital", nome_en="a romantic shoujo anime key visual", nome="Anime romântico (shoujo)",
        prompt="romantic shoujo anime, crisp anime line art, flat cel shading with hard shadow edges, big glossy anime eyes, blushing cheeks, soft pastel palette, floating sparkles and bloom, anime key visual",
        evitar="3D, dark gritty tone, photo", bom="romance emocional, constrangimentos engraçados, cenas delicadas",
        anima="clipes IA + efeitos (brilhos, corações) em motion grátis", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra animes de romance escolar", generos=["romance", "comedia"]),
    "chibi": dict(tecnica="2d-digital", nome_en="a chibi kawaii sticker illustration", nome="Chibi / Kawaii",
        prompt="chibi kawaii style, oversized heads and tiny bodies, huge sparkling eyes, cute rounded shapes, pastel colors, sticker-like clean outline",
        evitar="realistic proportions, 3D, photo", bom="comédia romântica leve, vídeos curtos, figurinhas",
        anima="motion grátis (pulos, squash) + poucos clipes", custo="imagem US$ 0,05", ref="estilo de figurinhas fofas",
        generos=["comedia", "romance", "curto"]),
    "aquarela": dict(tecnica="2d-tradicional", nome_en="a hand-painted watercolor animation background with characters", nome="Aquarela / Fantasia 2D",
        prompt="hand-painted watercolor and gouache animation look, soft edges, lush painted backgrounds, gentle natural light, delicate pastoral atmosphere",
        evitar="hard vector lines, 3D, photo, any existing studio character", bom="romance emocionante, histórias contemplativas, nostalgia",
        anima="zoom lento, parallax e clipes calmos", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra os filmes pintados à mão (tipo Studio Ghibli)", generos=["romance", "drama", "fantasia"]),
    "caricatural": dict(tecnica="3d-cgi", nome_en="an exaggerated caricature cartoon", nome="Cartoon caricatural",
        prompt="highly exaggerated caricature cartoon, squash and stretch proportions, rubbery faces, wild expressive poses, bold colors, comedic timing",
        evitar="realistic proportions, subtle expressions", bom="humor físico, situações absurdas, comédia romântica",
        anima="clipes IA com ação exagerada (o modelo de vídeo gosta)", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra comédias animadas exageradas (tipo Hotel Transilvânia)", generos=["comedia", "romance"]),
    "comic-cel": dict(tecnica="hibrido", nome_en="a comic book page panel with halftone", nome="Comic book / Cel shading",
        prompt="comic book cel-shaded style, bold ink outlines, halftone dots, offset print colors, dynamic angles, speed lines and graphic effects",
        evitar="soft painterly, photo, any existing superhero", bom="ação, narrativas dinâmicas, humor com ritmo",
        anima="clipes IA + onomatopeias e quadros em motion grátis", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra filmes com visual de quadrinhos (tipo Aranhaverso)", generos=["acao", "comedia"]),
    "rubber-hose": dict(tecnica="2d-tradicional", nome_en="a 1930s rubber hose cartoon", nome="Vintage / Rubber hose (anos 1930)",
        prompt="1930s rubber hose cartoon, black ink outlines, pie-cut eyes, noodle limbs, white gloves, aged film grain and sepia-tinted watercolor backgrounds",
        evitar="modern shading, 3D, any existing vintage character", bom="humor clássico, vídeos curtos de impacto",
        anima="clipes IA + granulação de filme e tremida em motion", custo="imagem US$ 0,05", ref="lembra desenhos dos anos 1930 (tipo Cuphead)",
        generos=["comedia", "curto"]),
    "claymation": dict(tecnica="claymation", nome_en="a claymation stop-motion photo", nome="Massinha (claymation)",
        prompt="claymation stop-motion look, handmade plasticine characters with visible fingerprints, miniature handcrafted set, soft studio lighting, tactile textures",
        evitar="smooth CGI, photo of real people, 2D", bom="comédia, família, histórias charmosas",
        anima="clipes IA reduzidos a 12 fps (efeito quadro a quadro)", custo="imagem US$ 0,05 · clipe ~US$ 0,11–0,35",
        ref="lembra animações de massinha (tipo Wallace & Gromit)", generos=["comedia", "familia"]),
    "papel-recortado": dict(tecnica="cut-out", nome_en="a paper cut-out diorama photo", nome="Papel recortado / feltro",
        prompt="paper cut-out stop-motion look, layered colored paper and felt, visible paper texture and edges, soft shadows between layers, handmade diorama",
        evitar="glossy 3D, photo, line art", bom="histórias infantis, explicativos, fábulas",
        anima="camadas recortadas animadas no Remotion (grátis)", custo="imagem US$ 0,05", ref="animação de recortes de papel",
        generos=["familia", "explicativo"]),
    "pixel-art": dict(tecnica="2d-digital", nome_en="16-bit pixel art", nome="Pixel art",
        prompt="detailed 16-bit pixel art, limited palette, crisp pixels, dithering, retro game scene composition",
        evitar="blur, anti-aliasing, 3D, photo", bom="humor nerd, nostalgia de jogos, vídeos curtos",
        anima="motion grátis quadro a quadro", custo="imagem US$ 0,05", ref="jogos dos anos 90", generos=["comedia", "curto"]),
    "low-poly": dict(tecnica="3d-cgi", nome_en="a low poly 3D render", nome="3D low poly",
        prompt="low poly 3D art, faceted geometric shapes, flat shaded colors, clean minimal lighting, toy-like diorama",
        evitar="high detail realism, 2D", bom="explicativos, tecnologia, vídeos institucionais leves",
        anima="clipes IA ou câmera em motion", custo="imagem US$ 0,05", ref="arte 3D geométrica", generos=["explicativo", "anuncio"]),
    "pintura-artistica": dict(tecnica="hibrido", nome_en="an oil painting", nome="Pintura artística (óleo, ukiyo-e…)",
        prompt="fine art oil painting look, visible brush strokes, rich impasto texture, dramatic chiaroscuro lighting",
        evitar="flat vector, photo, cartoon outlines", bom="vídeo de marca, institucional, poesia visual",
        anima="skill /lemo-opuscar (grátis, em código) ou zoom + clipes calmos", custo="grátis em código · imagem US$ 0,05",
        ref="ver /lemo-opuscar para os estilos", generos=["institucional", "drama"]),
    "motion-flat": dict(tecnica="motion-graphics", nome_en="flat vector motion graphics", nome="Motion graphics flat",
        prompt="flat vector motion graphics, geometric shapes, bold typography areas, brand color palette, clean icons",
        evitar="photo, painterly, 3D", bom="anúncio, explicativo, dados, tutorial",
        anima="tudo em Remotion (grátis)", custo="grátis", ref="vídeos explicativos e de marca", generos=["anuncio", "explicativo", "tutorial"]),
    "rotoscopia": dict(tecnica="rotoscopia", nome_en="rotoscoped animation", nome="Rotoscopia (desenho sobre filmagem)",
        prompt="rotoscoped animation look, hand-traced outlines over realistic human motion, flat painted colors with subtle gradients",
        evitar="stiff poses, 3D render", bom="drama, clipe musical, movimento humano realista",
        anima="motion control: você grava o gesto e a IA redesenha (US$ 0,07–0,112/s)", custo="~US$ 0,35–0,56 por 5 s",
        ref="filmes rotoscopados (tipo O Homem Duplo)", generos=["drama", "musical"]),
    "live-action": dict(tecnica="live-action", nome_en="a real photograph from a live-action movie", nome="Live-action cinematográfico (filme real)",
        prompt="real photograph, photorealistic live-action movie still shot on an ARRI cinema camera, 35mm anamorphic lens, a real-looking young man (fictional person, not a celebrity), natural skin pores and wet hair, real fabric, real rain drops, film grain, cinematic color grade",
        evitar="illustration, drawing, painting, cartoon, anime, 3D render, CGI, plastic skin, celebrity likeness, real identifiable people",
        bom="romance, drama, suspense, comercial de marca — visual de filme/série real",
        anima="clipes IA fotorrealistas em quase toda tomada (pessoa parada denuncia IA); lip-sync se houver fala na boca",
        custo="imagem US$ 0,05 · clipe ~US$ 0,27–0,49 por 5 s (mais clipes = mais caro)",
        ref="filmes e séries com atores", generos=["romance", "drama", "suspense", "anuncio"]),
    "live-action-ugc": dict(tecnica="live-action", nome_en="a real smartphone photo", nome="Live-action celular / UGC",
        prompt="realistic smartphone vertical video frame, handheld natural light, everyday real location, authentic candid people (fictional), slight grain",
        evitar="studio lighting, cartoon, celebrity likeness", bom="depoimento, anúncio de rede social, POV, humor do dia a dia",
        anima="clipes IA curtos + tremida de mão em motion", custo="clipe ~US$ 0,27–0,49 por 5 s",
        ref="vídeo gravado no celular (TikTok/Reels)", generos=["anuncio", "comedia", "curto"]),
    "documental": dict(tecnica="live-action", nome_en="a real documentary photograph", nome="Documentário realista",
        prompt="documentary photography style, natural available light, observational framing, realistic textures and people (fictional), muted natural color",
        evitar="glamour lighting, cartoon, celebrity likeness", bom="histórias reais (reencenadas), institucional, caso de cliente",
        anima="zoom lento (efeito Ken Burns) + poucos clipes", custo="imagem US$ 0,05 · clipe opcional", ref="documentários",
        generos=["institucional", "drama"]),
}
APELIDOS = {"cartoon-2d": "cartoon-2d-moderno", "3d": "cartoon-3d", "ghibli": "aquarela", "realista": "live-action",
            "filme": "live-action", "ugc": "live-action-ugc", "massinha": "claymation", "sitcom": "cartoon-2d-sitcom"}


def achar(eid):
    eid = APELIDOS.get(eid, eid)
    if eid not in ESTILOS:
        sys.exit(f"estilo '{eid}' não existe. Use: {', '.join(ESTILOS)}")
    return eid, ESTILOS[eid]


def prompt_completo(eid, personagem, cena):
    e = ESTILOS[eid]
    # o estilo vem primeiro E por último: senão a descrição da cena (luz, chuva) domina e todos saem iguais (2026-11-06)
    return (f"ART STYLE (the most important instruction, apply it to the whole image): {e['prompt']}. "
            f"Original character: {personagem}. Scene: {cena}. Vertical 9:16 composition. "
            f"The entire image, character and background, must clearly look like: {e['nome_en']}. "
            f"Do NOT use: {e['evitar']}. No text, no letters, no logos.")


def listar(genero=None):
    itens = list(ESTILOS.items())
    if genero:
        itens.sort(key=lambda kv: genero not in kv[1]["generos"])
    print("| id | estilo | técnica | bom para | como anima | custo |\n|---|---|---|---|---|---|")
    for k, e in itens:
        marca = " ⭐" if genero and genero in e["generos"] else ""
        print(f"| {k} | {e['nome']}{marca} | {e['tecnica']} | {e['bom']} | {e['anima']} | {e['custo']} |")


def comparar(a):
    ids = [achar(x)[0] for x in a.estilos.split(",")]
    preco = {"low": 0.012, "medium": 0.05, "high": 0.19}[a.qualidade]
    print(f"{len(ids)} estilos · {a.qualidade} · ~US$ {len(ids) * preco:.2f}")
    for k in ids:
        print(f"  {k:20} {ESTILOS[k]['nome']}")
    if not a.confirmar:
        print("Nada foi gerado. Rode de novo com --confirmar.")
        return
    pasta = os.path.join(a.projeto, "assets", "estilos")
    os.makedirs(pasta, exist_ok=True)
    arqs = []
    for k in ids:
        saida = os.path.join(pasta, f"{k}.png")
        if not os.path.exists(saida):
            subprocess.run([PY, os.path.join(AQUI, "gerar_imagem.py"), prompt_completo(k, a.personagem, a.cena), "-o", saida,
                            "--formato", "vertical", "--qualidade", a.qualidade, "--confirmar"], check=True)  # já confirmado acima
        arqs.append((k, saida))
    folha(arqs, os.path.join(pasta, "comparar.png"))


def folha(arqs, saida, larg=300):
    from PIL import Image, ImageDraw, ImageFont
    alt = int(larg * 1.5)
    col = min(4, len(arqs))
    lin = (len(arqs) + col - 1) // col
    W, H = col * larg + (col + 1) * 12, lin * (alt + 56) + 12
    img = Image.new("RGB", (W, H), (24, 28, 36))
    try:
        fonte = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    except OSError:
        fonte = ImageFont.load_default()
    d = ImageDraw.Draw(img)
    for i, (k, arq) in enumerate(arqs):
        x, y = 12 + (i % col) * (larg + 12), 12 + (i // col) * (alt + 56)
        im = Image.open(arq).convert("RGB").resize((larg, alt))
        img.paste(im, (x, y))
        d.text((x, y + alt + 8), f"{i + 1}. {ESTILOS[k]['nome']}", fill=(235, 238, 242), font=fonte)
    img.save(saida)
    print(saida)


def aplicar(eid, projeto):
    sys.path.insert(0, AQUI)
    from producao import carregar, salvar
    eid, e = achar(eid)
    arq, d = carregar(projeto)
    d.update({"estilo_id": eid, "tecnica": e["tecnica"], "estilo": e["prompt"], "estilo_evitar": e["evitar"]})
    salvar(arq, d, f"estilo visual: {e['nome']}")
    print(f"{arq}: {e['nome']} ({e['tecnica']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("listar"); s.add_argument("--genero")
    sub.add_parser("tecnicas")
    s = sub.add_parser("mostrar"); s.add_argument("id")
    s = sub.add_parser("comparar")
    s.add_argument("--personagem", required=True); s.add_argument("--cena", required=True)
    s.add_argument("--estilos", default="ilustracao-2d,cartoon-3d,anime-romantico,cartoon-2d-moderno,caricatural,live-action")
    s.add_argument("--qualidade", default="low", choices=["low", "medium", "high"])
    s.add_argument("--projeto", default="."); s.add_argument("--confirmar", action="store_true")
    s = sub.add_parser("aplicar"); s.add_argument("id"); s.add_argument("--projeto", default=".")
    a = ap.parse_args()
    if a.cmd == "listar":
        listar(a.genero)
    elif a.cmd == "tecnicas":
        for k, v in TECNICAS.items():
            print(f"{k:16} {v}")
    elif a.cmd == "mostrar":
        eid, e = achar(a.id)
        print(json.dumps({"id": eid, **e}, ensure_ascii=False, indent=1))
    elif a.cmd == "comparar":
        comparar(a)
    else:
        aplicar(a.id, a.projeto)


if __name__ == "__main__":
    main()
