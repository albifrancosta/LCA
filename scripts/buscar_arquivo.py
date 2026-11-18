"""Imagens REAIS grátis com crédito: fotos do Wikimedia Commons e filmes de arquivo do Internet Archive. Custo zero.

Complementa o buscar_stock.py (Pexels/Pixabay, que tem imagem genérica e moderna). Use este para o que é real e
específico: o prédio, a pessoa pública, o objeto, a época. Ideia adaptada do "Heist & Dark History Studio"
(2026-11-17), código nosso. Regras de uso em references/verdade-direitos.md.

Fotos (Wikimedia Commons; só domínio público, CC0, CC BY e CC BY-SA):
  python buscar_arquivo.py fotos buscar "Teatro Amazonas" [--n 12] [--saida <projeto>/assets/arquivo]
  python buscar_arquivo.py fotos baixar "File:Teatro Amazonas.jpg" --saida <projeto>/assets/arquivo
      → baixa com 1920 px e grava <arquivo>.credito.txt (autor / Wikimedia Commons / licença + página).
        Licença fora da lista é recusada.

Filmes de arquivo (Internet Archive; só itens marcados domínio público/CC0 ou de coleções de governo):
  python buscar_arquivo.py filmes buscar "manaus 1950" [--n 30]
      LIVRE = coleção de governo/curada · MARCADO = quem enviou diz domínio público (muitas vezes falso: TV, estúdio)
      · CONFERIR = sem marca. Nos dois últimos, abra archive.org/details/<id> e confira quem é o dono antes
  python buscar_arquivo.py filmes baixar <identificador> --saida <projeto>/assets/arquivo/src [--max-mb 1500] [--conferido]
      (MARCADO/CONFERIR só baixam com --conferido, depois que o usuário conferiu os direitos na página)
  python buscar_arquivo.py filmes falas <filme> palavra [palavra …]   → transcreve (faster-whisper) e mostra onde as
      palavras são ditas + uma folha de quadros em volta de cada uma
  python buscar_arquivo.py filmes folha <filme> <início s> [<duração s>=30]   → 1 quadro por segundo numa folha .jpg
  python buscar_arquivo.py filmes cortes <filme> <início s> [<duração s>=20]  → trocas de cena (para recortar limpo)
  python buscar_arquivo.py filmes recortar <filme> <a s> <b s> <saida.mp4> [--credito "Filme do FBI, 1951 · Arquivo Nacional dos EUA"]
      → recorta sem som e grava <saida>.credito.txt (herda o crédito do filme se não for informado)

Sem chave de API. Downloads só por https e só dos domínios do Commons e do Archive.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = "criador-video/1.0 (estudio de video; uso individual)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
DOMINIOS = ("wikimedia.org", "archive.org")
EXT_VIDEO = (".mp4", ".mpeg", ".mpg", ".ogv", ".avi", ".mov", ".wmv", ".m4v")
COLECOES_LIVRES = ("prelinger", "fedflix", "universal_newsreels", "gov.archives.arc.films", "nasa", "militaryfilms",
                   "usgovernmentdocuments")
FF = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


# ---------- regras (puras, testadas em tests/test_buscar_arquivo.py) ----------

def url_segura(url):
    u = urllib.parse.urlparse(str(url))
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == d or h.endswith("." + d) for d in DOMINIOS)


def licenca_commons_ok(licenca):
    """Domínio público, CC0, CC BY e CC BY-SA. Recusa NC, ND, uso justo, não livre e o que não reconhecer."""
    s = re.sub(r"\s+", " ", (licenca or "").strip().lower())
    if not s or re.search(r"(^|[- ])n[cd]\b|fair use|non-?free|all rights", s):
        return False
    return bool(re.match(r"^(public domain|pd\b|pd-|cc0|cc[- ]zero|cc[- ]by([- ]sa)?($|[- ]\d))", s))


def item_archive_livre(doc):
    """LIVRE só para coleções curadas/de governo. A marca de domínio público que o próprio autor do envio põe NÃO
    basta: há séries da BBC e filmes da Disney marcados assim (visto em 2026-11-17)."""
    col = doc.get("collection") or []
    col = " ".join(col) if isinstance(col, list) else str(col)
    return any(c in col.lower().split() for c in COLECOES_LIVRES)


def situacao_archive(doc):
    """LIVRE (coleção confiável) · MARCADO (autor do envio diz domínio público: conferir) · CONFERIR."""
    if item_archive_livre(doc):
        return "LIVRE"
    lic = f"{doc.get('licenseurl') or ''} {doc.get('rights') or ''}".lower()
    if any(k in lic for k in ("publicdomain", "public domain", "/zero/", "no known copyright")):
        return "MARCADO"
    return "CONFERIR"


def nome_seguro(titulo):
    base = titulo.split(":", 1)[-1] if titulo.lower().startswith("file:") else titulo
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "arquivo"
    return base[:120]


def credito_commons(autor, licenca, pagina):
    return f"{autor or 'Autor desconhecido'} / Wikimedia Commons / {licenca}\n{pagina}\n"


# ---------- rede ----------

def _abrir(url, timeout=60):
    if not url_segura(url):
        raise ValueError(f"download recusado (só https do Commons/Archive): {url}")
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)
    if not url_segura(r.geturl()):
        r.close()
        raise ValueError(f"redirecionou para fora dos domínios aceitos: {r.geturl()}")
    return r


def _ler(url, tentativas=3):
    for k in range(tentativas):
        try:
            with _abrir(url) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and k < tentativas - 1:
                time.sleep(5 * (k + 1))
                continue
            raise


def _baixar(url, destino, max_bytes):
    tmp = destino + ".parcial"
    total = 0
    with _abrir(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            total += len(bloco)
            if total > max_bytes:
                f.close()
                os.remove(tmp)
                sys.exit(f"passou de {max_bytes // 1_000_000} MB; use --max-mb maior se for mesmo esse arquivo")
            f.write(bloco)
    os.replace(tmp, destino)
    return total


# ---------- fotos (Commons) ----------

def _info_commons(params):
    q = dict(action="query", format="json", prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=1920, **params)
    d = json.loads(_ler(COMMONS_API + "?" + urllib.parse.urlencode(q)))
    limpo = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()  # noqa: E731
    saida = []
    for p in (d.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = limpo(md.get("LicenseShortName", {}).get("value"))
        saida.append(dict(titulo=p.get("title"), url=ii.get("thumburl") or ii.get("url"), pagina=ii.get("descriptionurl"),
                          licenca=lic, autor=limpo(md.get("Artist", {}).get("value"))[:120], ok=licenca_commons_ok(lic)))
    return saida


def fotos_buscar(termo, n, saida):
    try:
        res = _info_commons(dict(generator="search", gsrsearch=f"filetype:bitmap {termo}", gsrnamespace=6, gsrlimit=n))
    except Exception as e:  # noqa: BLE001
        print(f"Não consegui falar com o Wikimedia Commons ({e}). Busque no navegador e anote autor e licença:")
        print("  https://commons.wikimedia.org/w/index.php?search=" + urllib.parse.quote(termo) + "&title=Special:MediaSearch&type=image")
        return 2
    for i, r in enumerate(res, 1):
        print(f"{i:2d} {'OK ' if r['ok'] else 'NÃO'} {r['titulo']}\n     licença: {r['licenca']} | autor: {r['autor'][:70]}\n     {r['pagina']}")
    if saida:
        os.makedirs(saida, exist_ok=True)
        with open(os.path.join(saida, "fotos-candidatas.json"), "w", encoding="utf-8") as f:
            json.dump(dict(termo=termo, candidatos=res), f, ensure_ascii=False, indent=2)
    print("\nOK = licença livre (baixar com `fotos baixar \"File:…\"`). NÃO = não use.")
    return 0


def fotos_baixar(titulo, saida):
    if not titulo.lower().startswith("file:"):
        titulo = "File:" + titulo
    res = _info_commons(dict(titles=titulo))
    if not res or not res[0].get("url"):
        sys.exit(f"não achei {titulo} no Commons")
    r = res[0]
    if not r["ok"]:
        sys.exit(f"Recusado: a licença é '{r['licenca'] or 'não informada'}'. Escolha domínio público, CC0, CC BY ou CC BY-SA.")
    os.makedirs(saida, exist_ok=True)
    nome = nome_seguro(r["titulo"])
    ext = os.path.splitext(urllib.parse.urlparse(r["url"]).path)[1].lower()
    if ext and not nome.lower().endswith(ext):
        nome = os.path.splitext(nome)[0] + ext
    caminho = os.path.join(saida, nome)
    _baixar(r["url"], caminho, 60_000_000)
    credito = credito_commons(r["autor"], r["licenca"], r["pagina"])
    with open(caminho + ".credito.txt", "w", encoding="utf-8") as f:
        f.write(credito)
    print("salvo", caminho, "\ncrédito:", credito.splitlines()[0])
    return 0


# ---------- filmes (Internet Archive) ----------

def filmes_buscar(termo, n):
    q = (f"(title:({termo}) OR subject:({termo}) OR description:({termo})) AND mediatype:(movies) AND "
         f"(licenseurl:*publicdomain* OR licenseurl:*zero* OR collection:({' OR '.join(COLECOES_LIVRES)}))")
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
        {"q": q, "fl[]": ["identifier", "title", "year", "licenseurl", "rights", "collection"],
         "sort[]": "downloads desc", "rows": n, "output": "json"}, doseq=True)
    try:
        docs = json.loads(_ler(url))["response"]["docs"]
    except Exception as e:  # noqa: BLE001
        print(f"Não consegui falar com o Internet Archive ({e}). Busque em https://archive.org no navegador.")
        return 2
    for d in docs:
        print(f"{situacao_archive(d):8s} {d['identifier'][:45]:45s} "
              f"{str(d.get('year', ''))[:4]:5s} {str(d.get('title', ''))[:70]}")
    print("\nLIVRE = coleção de governo/curada (Prelinger, FedFlix, Arquivo Nacional, NASA, militares)."
          "\nMARCADO = quem enviou diz que é domínio público; muitas vezes é falso (TV, estúdio). Confira quem é o dono."
          "\nCONFERIR = leia os direitos em https://archive.org/details/<id>. MARCADO/CONFERIR só baixam com --conferido.")
    print("Lembrete: um filme que ilustra a época não é filmagem do fato. Credite pelo que ele é.")
    return 0


def filmes_baixar(ident, saida, max_mb, conferido):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", ident):
        sys.exit("identificador inválido")
    meta = json.loads(_ler(f"https://archive.org/metadata/{ident}"))
    md = meta.get("metadata", {})
    if not item_archive_livre(md) and not conferido:
        sys.exit(f"O item não é de coleção confiável ({situacao_archive(md)}). Leia os direitos em https://archive.org/details/{ident} "
                 "e, se o usuário confirmar que pode usar, rode de novo com --conferido.")
    arqs = [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(EXT_VIDEO)]
    if not arqs:
        sys.exit("o item não tem arquivo de vídeo")
    arqs.sort(key=lambda f: (not f["name"].lower().endswith(".mp4"), -int(f.get("size", 0) or 0)))
    f = arqs[0]
    os.makedirs(saida, exist_ok=True)
    destino = os.path.join(saida, nome_seguro(os.path.basename(f["name"])))
    print("baixando", f["name"], f"({int(f.get('size', 0) or 0) / 1e6:.0f} MB)")
    _baixar(f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}", destino, max_mb * 1_000_000)
    lic = md.get("licenseurl") or md.get("rights") or ("coleção de governo/domínio público" if item_archive_livre(md) else "conferido pelo usuário")
    titulo = md.get("title") or ident
    titulo = titulo[0] if isinstance(titulo, list) else titulo
    with open(destino + ".credito.txt", "w", encoding="utf-8") as fh:
        fh.write(f"{titulo} / Internet Archive / {lic}\nhttps://archive.org/details/{ident}\n")
    print("salvo", destino, "\nlicença:", lic)
    return 0


def _mp4(src):
    if src.lower().endswith(".mp4"):
        return src
    out = os.path.splitext(src)[0] + ".mp4"
    if not os.path.exists(out):
        subprocess.run([FF, "-v", "error", "-y", "-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-c:a", "aac", out], check=True)
    return out


def filmes_folha(src, inicio, dur, colunas=6):
    src = _mp4(src)
    out = os.path.splitext(src)[0] + f"_folha_{int(inicio)}.jpg"
    linhas = max(1, (int(dur) + colunas - 1) // colunas)
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(inicio), "-t", str(dur), "-i", src, "-vf",
                    f"fps=1,scale=320:-1,tile={colunas}x{linhas}", "-frames:v", "1", out], check=True)
    print("folha", out, f"(quadro k = {inicio} + k segundos, da esquerda para a direita)")
    return out


def filmes_falas(src, palavras):
    src = _mp4(src)
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("precisa de faster-whisper (pip install faster-whisper)")
    bruto = subprocess.run([FF, "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                           capture_output=True).stdout
    audio = np.frombuffer(bruto, np.int16).astype(np.float32) / 32768
    segs, _ = WhisperModel("small", compute_type="int8").transcribe(audio)
    achados = []
    for s in segs:
        if any(p.lower() in s.text.lower() for p in palavras):
            print(f">> {s.start:7.1f}s  {s.text.strip()}")
            achados.append(s.start)
    for t in achados:
        filmes_folha(src, max(0, t - 5), 30)
    if not achados:
        print("nenhuma das palavras foi dita; olhe por folhas (`filmes folha`)")
    return 0


def filmes_cortes(src, inicio, dur):
    src = _mp4(src)
    r = subprocess.run([FF, "-ss", str(inicio), "-t", str(dur), "-i", src, "-vf", "select='gt(scene,0.25)',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, errors="replace").stderr
    for ln in r.splitlines():
        if "pts_time:" in ln:
            print(f"corte em {float(ln.split('pts_time:')[1].split()[0]) + float(inicio):.2f} s")
    return 0


def filmes_recortar(src, a, b, out, credito):
    src_mp4 = _mp4(src)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", src_mp4, "-an", "-c:v", "libx264",
                    "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p", out], check=True)
    if not credito:
        for cand in (src + ".credito.txt", src_mp4 + ".credito.txt"):
            if os.path.exists(cand):
                with open(cand, encoding="utf-8") as fh:
                    credito = fh.read().strip()
                break
    if credito:
        with open(out + ".credito.txt", "w", encoding="utf-8") as f:
            f.write(credito.strip() + f"\n(trecho {float(a):.1f}–{float(b):.1f} s de {os.path.basename(src)})\n")
    else:
        print("AVISO: sem crédito. Informe --credito antes de usar no filme.")
    print("clipe", out, f"{float(b) - float(a):.1f} s")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="tipo", required=True)

    fo = sub.add_parser("fotos").add_subparsers(dest="acao", required=True)
    b = fo.add_parser("buscar")
    b.add_argument("termo"); b.add_argument("--n", type=int, default=12); b.add_argument("--saida")
    d = fo.add_parser("baixar")
    d.add_argument("titulo"); d.add_argument("--saida", default="assets/arquivo")

    fi = sub.add_parser("filmes").add_subparsers(dest="acao", required=True)
    b = fi.add_parser("buscar")
    b.add_argument("termo"); b.add_argument("--n", type=int, default=30)
    d = fi.add_parser("baixar")
    d.add_argument("ident"); d.add_argument("--saida", default="assets/arquivo/src")
    d.add_argument("--max-mb", type=int, default=1500); d.add_argument("--conferido", action="store_true")
    f = fi.add_parser("falas")
    f.add_argument("filme"); f.add_argument("palavras", nargs="+")
    for nome, dur in (("folha", 30), ("cortes", 20)):
        f = fi.add_parser(nome)
        f.add_argument("filme"); f.add_argument("inicio", type=float); f.add_argument("dur", type=float, nargs="?", default=dur)
    f = fi.add_parser("recortar")
    f.add_argument("filme"); f.add_argument("a", type=float); f.add_argument("b", type=float)
    f.add_argument("saida"); f.add_argument("--credito")

    a = ap.parse_args(argv)
    if a.tipo == "fotos":
        return fotos_buscar(a.termo, a.n, a.saida) if a.acao == "buscar" else fotos_baixar(a.titulo, a.saida)
    if a.acao == "buscar":
        return filmes_buscar(a.termo, a.n)
    if a.acao == "baixar":
        return filmes_baixar(a.ident, a.saida, a.max_mb, a.conferido)
    if a.acao == "falas":
        return filmes_falas(a.filme, a.palavras)
    if a.acao == "folha":
        filmes_folha(a.filme, a.inicio, a.dur)
        return 0
    if a.acao == "cortes":
        return filmes_cortes(a.filme, a.inicio, a.dur)
    if a.b <= a.a:
        sys.exit("o fim do trecho precisa ser depois do início")
    return filmes_recortar(a.filme, a.a, a.b, a.saida, a.credito)


if __name__ == "__main__":
    sys.exit(main())
