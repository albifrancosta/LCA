"""Busca de VÍDEOS GRÁTIS de banco (Pexels + Pixabay) por cena — custo zero.

Ideia aproveitada do MoneyPrinterTurbo (MIT): termos por cena → busca no banco → candidatos.
Aqui o fluxo é com aprovação: busca e mostra uma GRADE de miniaturas; só baixa o que o usuário escolher.

Chaves (grátis, só por variável de ambiente — nunca no código):
  PEXELS_API_KEY   → https://www.pexels.com/api/  (200 req/h, 20 mil/mês)
  PIXABAY_API_KEY  → https://pixabay.com/api/docs/ (logado, a chave aparece na página)
Licença: Pexels e Pixabay permitem uso comercial sem crédito obrigatório. Mesmo assim CONFERIR na grade:
  rosto reconhecível em destaque, marca/logo de terceiros, placa de carro legível → evitar em anúncio.

Uso:
  python buscar_stock.py buscar "aerial city skyline" --cena 01 --saida <projeto>/assets/stock
  python buscar_stock.py roteiro cenas.json --saida <projeto>/assets/stock
      cenas.json = [{"cena": "01", "termos": ["aerial city skyline", "river city sunset"], "orientacao": "landscape"}, ...]
  python buscar_stock.py baixar <projeto>/assets/stock/01/candidatos.json --ids 3,5
      (baixa só os números escolhidos na grade; grava creditos.json com fonte, autor, página e licença)

Opções de busca: --fonte pexels|pixabay|todas (padrão: as que tiverem chave) · --orientacao landscape|portrait|square
  · --n 8 por termo e fonte · --min-dur 4 · --max-dur 60 · --min-largura 1920 (1080 para vertical)
Saída da busca: <saida>/<cena>/candidatos.json + grade.jpg (miniaturas numeradas com fonte, duração e resolução).
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

UA = "estudio-video-stock/1.0"
LICENCA = {
    "pexels": "Pexels License — uso comercial livre, crédito opcional (pexels.com/license)",
    "pixabay": "Pixabay Content License — uso comercial livre, crédito opcional (pixabay.com/service/license-summary)",
}


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _chave_windows(nome):
    """Carrega as chaves pelo módulo central (.env, ambiente, registro do Windows)."""
    import chaves
    chaves.carregar()


def fontes_disponiveis(pedido):
    for nome in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        _chave_windows(nome)
    tem = {"pexels": bool(os.environ.get("PEXELS_API_KEY")), "pixabay": bool(os.environ.get("PIXABAY_API_KEY"))}
    if pedido in ("pexels", "pixabay"):
        if not tem[pedido]:
            import chaves
            sys.exit(chaves.mensagem_falta(f"{pedido.upper()}_API_KEY", "busca de vídeos de banco"))
        return [pedido]
    lista = [f for f, ok in tem.items() if ok]
    if not lista:
        import chaves
        sys.exit("Nenhuma chave de banco de vídeo (as duas são grátis; basta uma).\n\n"
                 + chaves.mensagem_falta("PIXABAY_API_KEY", "busca de vídeos de banco") + "\n\n"
                 + chaves.mensagem_falta("PEXELS_API_KEY", "busca de vídeos de banco"))
    return lista


def _melhor_arquivo(arquivos, min_largura, vertical):
    """Escolhe o menor arquivo que ainda cumpre a resolução mínima (lado relevante); senão o maior."""
    def lado(a):
        return (a.get("height") or 0) if vertical else (a.get("width") or 0)
    ok = [a for a in arquivos if lado(a) >= min_largura]
    if ok:
        return min(ok, key=lado)
    return max(arquivos, key=lado) if arquivos else None


def buscar_pexels(termo, orientacao, n, min_largura):
    q = urllib.parse.urlencode({"query": termo, "orientation": orientacao, "per_page": n, "size": "medium"})
    dados = _get_json(f"https://api.pexels.com/videos/search?{q}", {"Authorization": os.environ["PEXELS_API_KEY"]})
    out = []
    for v in dados.get("videos", []):
        arqs = [{"width": f.get("width"), "height": f.get("height"), "url": f.get("link"), "fps": f.get("fps")}
                for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
        a = _melhor_arquivo(arqs, min_largura, orientacao == "portrait")
        if not a:
            continue
        out.append({"fonte": "pexels", "id": v["id"], "pagina": v.get("url"), "autor": (v.get("user") or {}).get("name"),
                    "duracao": v.get("duration"), "largura": a["width"], "altura": a["height"], "fps": a.get("fps"),
                    "arquivo": a["url"], "tamanho_bytes": None, "miniatura": v.get("image"), "termo": termo})
    return out


def buscar_pixabay(termo, orientacao, n, min_largura):
    q = urllib.parse.urlencode({"key": os.environ["PIXABAY_API_KEY"], "q": termo[:100], "per_page": max(3, n),
                                "video_type": "film", "safesearch": "true"})
    dados = _get_json(f"https://pixabay.com/api/videos/?{q}")
    out = []
    for h in dados.get("hits", []):
        arqs = [{**vv, "nome": k} for k, vv in (h.get("videos") or {}).items() if vv.get("url")]
        if not arqs:
            continue
        w0, h0 = arqs[0].get("width") or 0, arqs[0].get("height") or 0
        orient = "portrait" if h0 > w0 else ("square" if h0 == w0 else "landscape")
        if orient != orientacao:
            continue
        a = _melhor_arquivo(arqs, min_largura, orientacao == "portrait")
        out.append({"fonte": "pixabay", "id": h["id"], "pagina": h.get("pageURL"), "autor": h.get("user"),
                    "duracao": h.get("duration"), "largura": a.get("width"), "altura": a.get("height"), "fps": None,
                    "arquivo": a["url"], "tamanho_bytes": a.get("size"), "miniatura": a.get("thumbnail"), "termo": termo})
    return out


BUSCA = {"pexels": buscar_pexels, "pixabay": buscar_pixabay}


def filtrar(cands, min_dur, max_dur, min_largura, vertical):
    vistos, out = set(), []
    for c in cands:
        chave = (c["fonte"], c["id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        lado = (c["altura"] if vertical else c["largura"]) or 0
        if (c["duracao"] or 0) < min_dur or (c["duracao"] or 0) > max_dur or lado < min_largura:
            continue
        out.append(c)
    return out


def grade(cands, destino):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  (sem Pillow: grade não gerada; veja as miniaturas no candidatos.json)")
        return
    cel_w, cel_h, cols = 480, 270, 4
    linhas = (len(cands) + cols - 1) // cols
    folha = Image.new("RGB", (cel_w * cols, (cel_h + 34) * max(1, linhas)), (18, 18, 22))
    d = ImageDraw.Draw(folha)
    try:
        fonte = ImageFont.truetype("arialbd.ttf", 22)
    except OSError:
        fonte = ImageFont.load_default()
    for i, c in enumerate(cands):
        x, y = (i % cols) * cel_w, (i // cols) * (cel_h + 34)
        try:
            im = Image.open(io.BytesIO(_get_bytes(c["miniatura"]))).convert("RGB")
            im.thumbnail((cel_w - 6, cel_h - 6))
            folha.paste(im, (x + (cel_w - im.width) // 2, y + (cel_h - im.height) // 2))
        except Exception as e:  # miniatura indisponível não derruba a busca
            d.text((x + 10, y + 120), f"sem miniatura ({type(e).__name__})", fill=(200, 80, 80), font=fonte)
        d.rectangle([x + 6, y + 6, x + 56, y + 40], fill=(0, 120, 215))
        d.text((x + 14, y + 10), str(c["n"]), fill="white", font=fonte)
        rot = f"{c['fonte']} · {c['duracao']}s · {c['largura']}x{c['altura']}"
        d.text((x + 8, y + cel_h + 4), rot, fill=(220, 220, 220), font=fonte)
    folha.save(destino, quality=88)


def cmd_buscar(cena, termos, a):
    fontes = fontes_disponiveis(a.fonte)
    vertical = a.orientacao == "portrait"
    min_larg = a.min_largura or (1080 if vertical else 1920)
    brutos = []
    for termo in termos:
        for f in fontes:
            try:
                brutos += BUSCA[f](termo, a.orientacao, a.n, min_larg)
            except Exception as e:
                print(f"  ! {f} falhou para '{termo}': {e}")
            time.sleep(0.3)
    cands = filtrar(brutos, a.min_dur, a.max_dur, min_larg, vertical)
    for i, c in enumerate(cands, 1):
        c["n"] = i
    pasta = os.path.join(a.saida, cena)
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "candidatos.json"), "w", encoding="utf-8") as fh:
        json.dump({"cena": cena, "termos": termos, "orientacao": a.orientacao, "candidatos": cands}, fh,
                  ensure_ascii=False, indent=2)
    if cands:
        grade(cands, os.path.join(pasta, "grade.jpg"))
    print(f"cena {cena}: {len(cands)} candidatos ({len(brutos)} brutos) -> {pasta}")
    return cands


def cmd_baixar(a):
    with open(a.candidatos, encoding="utf-8") as fh:
        dados = json.load(fh)
    pasta = os.path.dirname(os.path.abspath(a.candidatos))
    ids = {int(x) for x in a.ids.split(",") if x.strip()}
    cred_path = os.path.join(pasta, "creditos.json")
    creditos = json.load(open(cred_path, encoding="utf-8")) if os.path.exists(cred_path) else []
    for c in dados["candidatos"]:
        if c["n"] not in ids:
            continue
        nome = f"cena{dados['cena']}_{c['n']:02d}_{c['fonte']}{c['id']}.mp4"
        destino = os.path.join(pasta, nome)
        if not (os.path.exists(destino) and os.path.getsize(destino) > 0):
            req = urllib.request.Request(c["arquivo"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(destino + ".part", "wb") as out:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    out.write(bloco)
            os.replace(destino + ".part", destino)
        mb = os.path.getsize(destino) / 1e6
        print(f"  ok {nome} ({mb:.1f} MB, {c['largura']}x{c['altura']}, {c['duracao']}s)")
        creditos = [k for k in creditos if k.get("arquivo") != nome]
        creditos.append({"arquivo": nome, "fonte": c["fonte"], "id": c["id"], "autor": c["autor"], "pagina": c["pagina"],
                         "licenca": LICENCA[c["fonte"]], "termo": c["termo"]})
    with open(cred_path, "w", encoding="utf-8") as fh:
        json.dump(creditos, fh, ensure_ascii=False, indent=2)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def opcoes(sp):
        sp.add_argument("--saida", required=True)
        sp.add_argument("--fonte", default="todas", choices=["todas", "pexels", "pixabay"])
        sp.add_argument("--orientacao", default="landscape", choices=["landscape", "portrait", "square"])
        sp.add_argument("--n", type=int, default=8)
        sp.add_argument("--min-dur", type=float, default=4)
        sp.add_argument("--max-dur", type=float, default=60)
        sp.add_argument("--min-largura", type=int, default=0)

    b = sub.add_parser("buscar")
    b.add_argument("termos", nargs="+")
    b.add_argument("--cena", default="00")
    opcoes(b)
    r = sub.add_parser("roteiro")
    r.add_argument("cenas")
    opcoes(r)
    d = sub.add_parser("baixar")
    d.add_argument("candidatos")
    d.add_argument("--ids", required=True)
    a = p.parse_args()

    if a.cmd == "buscar":
        cmd_buscar(a.cena, a.termos, a)
    elif a.cmd == "roteiro":
        with open(a.cenas, encoding="utf-8") as fh:
            cenas = json.load(fh)
        padrao = a.orientacao
        for c in cenas:
            a.orientacao = c.get("orientacao", padrao)
            cmd_buscar(str(c["cena"]), c["termos"], a)
    else:
        cmd_baixar(a)


if __name__ == "__main__":
    main()
