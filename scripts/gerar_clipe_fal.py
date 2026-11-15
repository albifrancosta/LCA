"""Anima a imagem de uma cena com IA (fal.ai, imagem → vídeo). Cobra créditos do fal: mostra o custo antes.

Uso:
  # um clipe (modelo escolhido pelo roteador de custos)
  python gerar_clipe_fal.py --imagem cena.png --prompt "ele olha o celular e franze a testa" -o clipe.mp4 --modelo auto --cena personagem [--perfil economico] --confirmar
  # modelo fixo (qualquer id do catálogo)
  python gerar_clipe_fal.py --imagem cena.png --prompt "..." -o clipe.mp4 --modelo fal-ai/minimax/hailuo-02/standard/image-to-video --confirmar
  # A/B: a mesma cena em 2 modelos econômicos, com orçamento próprio → você escolhe → o roteador aprende
  python gerar_clipe_fal.py --imagem cena.png --prompt "..." -o clipe.mp4 --ab auto --cena personagem --orcamento-ab 0.6 --confirmar
  # todos os planos de um roteiro.json que tenham "clipe" — simples {"movimento"} ou organizado
  # {inicio, etapas[{camera, acao}], fim} (ver prompt_clipe.py; a sequência é checada antes de gastar)
  python gerar_clipe_fal.py --roteiro roteiro.json [--so p02,p06] [--modelo auto] [--orcamento 2.00] [--confirmar]
  # no lote, sem --modelo, cada plano usa a rota do contrato (direcao.rota.modelo, de contrato.py rotear); sem rota, o padrão.
  # planos com "clipe": false / sem clipe são pulados; rotas motion/foto_camera (US$ 0) e avatar/omnihuman (lipsync.py) também.
  # algo falhou depois de pagar
  python gerar_clipe_fal.py --recuperar clipe.mp4

Sem --confirmar só mostra o que seria gerado, o modelo escolhido, o motivo e quanto custa.
Orçamento: --orcamento = teto TOTAL do lote (soma); --orcamento-por-clipe = teto de cada clipe.
Recusa gastar (com --confirmar) se algum clipe tiver PREÇO DESCONHECIDO ou duração que o modelo não entrega (nunca US$ 0,
nunca 15 s viram 10 s calados). Pedido que termina FAILED/CANCELLED/ERROR no fal para na hora, com o request_id no .json.
Preços: catálogo oficial (`catalogo.py`, API do fal). Cache: a mesma cena (imagem + prompt + modelo + duração) não é paga duas vezes.
Todo gasto vai para o livro-caixa (`custos.py relatorio`). Chave: variável FAL_KEY (lida também do registro do Windows).
"""
import argparse
import base64
import functools
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from integridade import gravar_json_atomico  # noqa: E402

PADRAO = "fal-ai/kling-video/v2.5-turbo/pro/image-to-video"  # aprovado no "Cadê o técnico?" (4/4)
NEGATIVO = "blur, distort, low quality, text, watermark, extra fingers, deformed face"
ULTIMO = ("end_image_url", "tail_image_url", "last_frame_url", "last_image_url")
FALHAS = {"FAILED", "FAILURE", "CANCELLED", "CANCELED", "ERROR", "ERRORED", "TIMEOUT"}
ROTAS_SEM_CLIPE = {"motion": "sai em código (Remotion), US$ 0", "foto_camera": "imagem + movimento de câmera, US$ 0",
                   "avatar": "fala em quadro — gere com lipsync.py", "omnihuman": "fala + corpo — gere com lipsync.py"}


def chave():
    import chaves
    return chaves.obter("FAL_KEY", contexto="clipes animados no fal.ai")


def modelo_catalogo(modelo):
    try:
        from roteador import CAT, carregar
        return next((m for m in carregar(CAT, {"modelos": []})["modelos"] if m["id"] == modelo), None)
    except ImportError:
        return None


def custo(modelo, duracao):
    """US$ do clipe pelo catálogo, ou None (modelo fora do catálogo, preço desconhecido ou duração que ele não entrega).
    None NUNCA é tratado como US$ 0: com --confirmar o gasto é recusado (P19)."""
    m = modelo_catalogo(modelo)
    if not m:
        return None
    from roteador import preco_duracao
    preco, _ = preco_duracao(m, float(duracao))
    return None if preco is None else round(preco, 4)


def problema_preco(modelo, duracao):
    """Texto do motivo quando custo() é None; '' se o preço é conhecido."""
    m = modelo_catalogo(modelo)
    if not m:
        return f"{modelo} não está no catálogo — rode catalogo.py ou escolha um id do catálogo"
    from roteador import duracao_real, duracoes_do, preco_duracao
    if duracao_real(m, float(duracao)) is None:
        return (f"{modelo} não entrega {float(duracao):g} s (aceita {', '.join(f'{d:g}' for d in duracoes_do(m))} s) — "
                "divida o plano ou troque de modelo")
    if preco_duracao(m, float(duracao))[0] is None:
        return f"{modelo}: preço desconhecido no catálogo (unidade '{m.get('unidade')}', sem custo_5s) — atualize o catálogo"
    return ""


def fmt_preco(p):
    return f"US$ {p:.3f}" if p is not None else "preço desconhecido"


def pedir(url, corpo=None, tentativas=6):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Key {chave()}", "Content-Type": "application/json"})
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"fal.ai {e.code}: {e.read().decode(errors='replace')[:500]}")
        except urllib.error.URLError as e:
            # queda rápida de internet/DNS (aconteceu em 2026-11-04 no meio da espera): tenta de novo
            if n == tentativas - 1 or corpo is not None:  # nunca reenvia o pedido pago; só a consulta
                raise
            print(f"  rede instável ({e.reason}); tentando de novo…", file=sys.stderr)
            time.sleep(10 * (n + 1))


@functools.lru_cache(maxsize=None)
def esquema(modelo):
    """Parâmetros aceitos pelo modelo (schema público do fal): nomes e valores de duração/resolução no tipo certo."""
    try:
        with urllib.request.urlopen(f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={modelo}", timeout=60) as r:
            d = json.load(r)
        s = d["components"]["schemas"]
        return next(v for k, v in s.items() if k.endswith("Input"))["properties"]
    except Exception:  # noqa: BLE001 — sem schema, manda o mínimo (prompt + imagem)
        return {}


def valores(prop):
    if not prop:
        return []
    return prop.get("enum") or [x["const"] for x in prop.get("anyOf", []) if isinstance(x, dict) and "const" in x]


def duracao_do_esquema(modelo, duracao):
    """(valor para 'duration' | None, erro | ''). Erro quando o modelo não entrega a duração pedida (P20)."""
    props = esquema(modelo)
    if "duration" not in props:
        return None, ""
    ops = valores(props["duration"])
    if ops:
        nums = sorted(ops, key=lambda v: float(v))
        cabe = next((v for v in nums if float(v) >= float(duracao) - 1e-6), None)
        if cabe is None:
            return None, (f"{modelo} não entrega {float(duracao):g} s (aceita {', '.join(str(v) for v in nums)} s) — divida o plano "
                          f"em partes menores ou escolha outro modelo (roteador.py --duracao {float(duracao):g})")
        return cabe, ""
    return (duracao if props["duration"].get("type") == "string" else int(float(duracao))), ""


def corpo_para(modelo, prompt, imagem_uri, duracao, ultimo_uri=None):
    props = esquema(modelo)
    # Kling 2.6/3 chamam a imagem de start_image_url; os outros, image_url
    corpo = {"prompt": prompt, ("start_image_url" if "start_image_url" in props else "image_url"): imagem_uri}
    if "generate_audio" in props:
        corpo["generate_audio"] = False  # som sai do nosso foley/mixagem; áudio nativo encarece e briga com a trilha
    if "duration" in props:
        valor, erro = duracao_do_esquema(modelo, duracao)
        if erro:
            sys.exit(erro)  # nunca escolhe a maior duração calado (15 s pedidos ≠ 10 s entregues)
        corpo["duration"] = valor
    if "negative_prompt" in props:
        corpo["negative_prompt"] = NEGATIVO
    if "cfg_scale" in props and "kling" in modelo:
        corpo["cfg_scale"] = 0.5
    if "resolution" in props:
        ops = [str(v) for v in valores(props["resolution"])]
        alvo = next((r for r in ("720p", "768P", "768p") if r in ops), None)
        if alvo:
            corpo["resolution"] = alvo
    if ultimo_uri:
        nome = next((n for n in ULTIMO if n in props), None)
        if not nome:
            sys.exit(f"{modelo} não aceita último quadro — escolha outro (roteador.py --ultimo-quadro)")
        corpo[nome] = ultimo_uri
    return corpo


def data_uri(img):
    tipo = mimetypes.guess_type(img)[0] or "image/png"
    return f"data:{tipo};base64,{base64.b64encode(open(img, 'rb').read()).decode()}"


def gerar(imagem, prompt, saida, modelo=PADRAO, duracao="5", ultimo_quadro=None, detalhe=""):
    from custos import cache_buscar, cache_chave, cache_guardar, registrar
    preco = custo(modelo, duracao)
    k = cache_chave("clipe", modelo=modelo, prompt=prompt, imagem=imagem, duracao=str(duracao), ultimo=ultimo_quadro or "")
    achado = cache_buscar("clipe", k, ".mp4")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    if achado:
        shutil.copyfile(achado, saida)
        registrar("clipe", modelo, preco, f"{os.path.basename(saida)} (cache)", "catálogo fal", cache=True)
        print(f"  cache: clipe idêntico já pago antes → {saida} (US$ 0)")
        return 0.0
    if preco is None:  # P19: preço desconhecido nunca é US$ 0 — não gasta
        sys.exit(f"recusado (nada foi gasto): {problema_preco(modelo, duracao) or 'preço desconhecido'}")
    corpo = corpo_para(modelo, prompt, data_uri(imagem), duracao, data_uri(ultimo_quadro) if ultimo_quadro else None)
    fila = pedir(f"https://queue.fal.run/{modelo}", corpo)
    status_url, resposta_url = fila["status_url"], fila["response_url"]
    # salva o pedido já pago antes de esperar: se algo falhar depois, `--recuperar <saida>` baixa sem pagar de novo
    meta = {"modelo": modelo, "prompt": prompt, "imagem": imagem, "duracao": duracao, "custo_estimado": preco,
            "request_id": fila.get("request_id"), "response_url": resposta_url, "status_url": status_url, "cache_chave": k,
            "status": "enviado"}
    gravar_json_atomico(saida + ".json", meta)
    print(f"  pedido {fila.get('request_id')} enviado ({modelo}); aguardando…")
    t0 = time.time()
    while True:  # geração leva ~1–5 min
        st = pedir(status_url) or {}
        status = str(st.get("status") or "").upper()
        if status == "COMPLETED":
            break
        if status in FALHAS or st.get("error"):  # P28: falha é terminal — não espera 15 min à toa
            meta.update(status=status or "ERROR", erro=str(st.get("error") or st.get("detail") or "")[:500])
            gravar_json_atomico(saida + ".json", meta)
            sys.exit(f"pedido {fila.get('request_id')} terminou com {meta['status']} no fal ({meta['erro'] or 'sem detalhe'}). "
                     f"Registro em {saida}.json — confira no painel do fal se houve cobrança antes de refazer.")
        if time.time() - t0 > 900:
            meta["status"] = "tempo_esgotado"
            gravar_json_atomico(saida + ".json", meta)
            sys.exit(f"tempo esgotado; pedido {fila.get('request_id')} continua no fal (consulte {status_url}) — use --recuperar")
        time.sleep(5)
    resp = pedir(resposta_url) or {}
    url = (resp.get("video") or {}).get("url") if isinstance(resp, dict) else None
    if not url:
        meta.update(status="sem_video", erro=json.dumps(resp, ensure_ascii=False)[:500])
        gravar_json_atomico(saida + ".json", meta)
        sys.exit(f"pedido {fila.get('request_id')} COMPLETED sem vídeo na resposta — registro em {saida}.json")
    baixar(url, saida)
    meta["status"] = "baixado"
    gravar_json_atomico(saida + ".json", meta)
    cache_guardar("clipe", k, saida)
    registrar("clipe", modelo, preco, detalhe or f"{os.path.basename(saida)} · {duracao} s", "catálogo fal (API oficial)")
    return time.time() - t0


def baixar(url, saida):
    # curl do Windows usa os certificados do sistema; o Python 3.14 local não reconhece o do fal.media
    subprocess.run(["curl", "-sS", "-L", "--fail", "-o", saida, url], check=True)


def recuperar(saida):
    meta = json.load(open(saida + ".json", encoding="utf-8"))
    if str(meta.get("status", "")).upper() in FALHAS:
        sys.exit(f"o pedido {meta.get('request_id')} terminou com {meta['status']} no fal — não há vídeo para recuperar")
    baixar(pedir(meta["response_url"])["video"]["url"], saida)
    if meta.get("cache_chave"):
        from custos import cache_guardar
        cache_guardar("clipe", meta["cache_chave"], saida)
    print(f"recuperado sem novo custo: {saida}")


def teto_clipe(a):
    """Teto por clipe para o roteador: --orcamento-por-clipe; senão o teto total (um clipe nunca passa do lote)."""
    return a.orcamento_por_clipe if a.orcamento_por_clipe is not None else a.orcamento


def escolher_modelo(a, duracao, rota=None):
    if a.modelo and a.modelo != "auto":
        return a.modelo, f"modelo fixo: {a.modelo}"
    if a.modelo is None:  # sem --modelo: rota do contrato (P23) ou o padrão aprovado
        if rota and rota.get("modelo") and "/" in str(rota["modelo"]):
            return rota["modelo"], f"rota do contrato ({rota.get('rota', '?')}): {rota['modelo']}"
        return PADRAO, f"modelo padrão: {PADRAO}"
    from roteador import escolher
    dec, _ = escolher("video", float(duracao), a.cena, bool(a.ultimo_quadro), a.perfil, teto_clipe(a))
    if not dec["modelo"] or dec["modelo"].startswith("local/"):
        sys.exit(f"roteador: {dec['motivo']}" + (f" — {dec['detalhe']}" if dec.get("detalhe") else ""))
    return dec["modelo"], dec["motivo"]


def modelos_ab(a, duracao):
    if a.ab != "auto":
        return [m.strip() for m in a.ab.split(",")][:2]
    from roteador import escolher
    _, cands = escolher("video", float(duracao), a.cena, bool(a.ultimo_quadro), "economico", teto_clipe(a), registrar=False)
    escolhidos, familias = [], set()
    for c in cands:  # os 2 mais baratos por resultado aprovado, de famílias diferentes, qualidade ≥ 2
        fam = c["modelo"].split("/")[1]
        if c["q"] >= 2 and fam not in familias:
            escolhidos.append(c["modelo"])
            familias.add(fam)
        if len(escolhidos) == 2:
            break
    return escolhidos


def folha_ab(saidas, destino):
    """Quadros lado a lado (A em cima, B embaixo) para comparar sem abrir os vídeos."""
    tiras = []
    for s in saidas:
        t = destino + f".{len(tiras)}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", s, "-vf", "fps=1,scale=240:-1,tile=6x1", "-frames:v", "1", t], check=True)
        tiras.append(t)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sum([["-i", t] for t in tiras], []), "-filter_complex", f"vstack={len(tiras)}", destino], check=True)
    for t in tiras:
        os.remove(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imagem")
    ap.add_argument("--prompt")
    ap.add_argument("-o", "--saida")
    ap.add_argument("--roteiro")
    ap.add_argument("--so", help="só estes planos (vírgula)")
    ap.add_argument("--modelo", help=f"id do catálogo ou 'auto' (roteador escolhe). Sem ele: rota do contrato no lote, senão {PADRAO}")
    ap.add_argument("--cena", default="geral", help="tipo da cena para o roteador: personagem, acao, paisagem, produto…")
    ap.add_argument("--perfil", default="economico", choices=["economico", "equilibrado", "premium"])
    ap.add_argument("--orcamento", type=float, help="teto TOTAL do lote (US$, soma de todos os clipes)")
    ap.add_argument("--orcamento-por-clipe", type=float, help="teto de cada clipe (US$); também limita a escolha do roteador")
    ap.add_argument("--ultimo-quadro", help="imagem do último quadro (só modelos que aceitam)")
    ap.add_argument("--ab", help="A/B: 'auto' ou 'modeloA,modeloB' — gera a mesma cena nos dois")
    ap.add_argument("--orcamento-ab", type=float, help="teto do teste A/B somado (obrigatório com --ab)")
    ap.add_argument("--duracao", default="5")
    ap.add_argument("--confirmar", action="store_true", help="gera de verdade (gasta créditos)")
    ap.add_argument("--recuperar", metavar="CLIPE.mp4", help="baixa de novo um clipe já pago (usa o .json ao lado)")
    a = ap.parse_args()
    if a.recuperar:
        return recuperar(a.recuperar)

    if a.ab:
        if not (a.imagem and a.prompt and a.saida):
            ap.error("--ab precisa de --imagem, --prompt e -o")
        if a.orcamento_ab is None:
            ap.error("--ab precisa de --orcamento-ab (o teste também gasta créditos)")
        mods = modelos_ab(a, a.duracao)
        if len(mods) < 2:
            sys.exit("A/B: não há 2 modelos compatíveis (duração/qualidade/orçamento) — escolha os dois com --ab modeloA,modeloB")
        precos = [custo(m, a.duracao) for m in mods]
        print(f"A/B · cena '{a.cena}' · {a.duracao} s")
        for rot, m, p in zip("AB", mods, precos):
            print(f"  {rot}: {m}  {fmt_preco(p)}" + (f"  ({problema_preco(m, a.duracao)})" if p is None else ""))
        conhecidos = sum(p for p in precos if p is not None)
        print(f"  total US$ {conhecidos:.3f}{' + preço desconhecido' if None in precos else ''} · orçamento do teste US$ {a.orcamento_ab:.2f}")
        if conhecidos > a.orcamento_ab:
            sys.exit("passa do orçamento do A/B — aumente --orcamento-ab ou escolha modelos mais baratos")
        if None in precos and a.confirmar:
            sys.exit("recusado (nada foi gasto): há modelo com preço desconhecido ou duração incompatível no A/B")
        if not a.confirmar:
            print("Nada foi gerado. Rode de novo com --confirmar para gastar os créditos.")
            return
        raiz, ext = os.path.splitext(a.saida)
        saidas = []
        for rot, m in zip("AB", mods):
            s = f"{raiz}-{rot}{ext or '.mp4'}"
            gerar(a.imagem, a.prompt, s, m, a.duracao, a.ultimo_quadro, f"A/B {rot} · {os.path.basename(s)}")
            saidas.append(s)
        folha_ab(saidas, raiz + "-AB.png")
        print(f"\nCompare: {saidas[0]} × {saidas[1]} (quadros em {raiz}-AB.png). Depois registre o vencedor:")
        for m in mods:
            print(f"  python roteador.py --resultado {m} {a.cena} aprovado|reprovado")
        return

    tarefas = []
    if a.roteiro:
        proj = os.path.dirname(os.path.abspath(a.roteiro))
        r = json.load(open(a.roteiro, encoding="utf-8"))
        from prompt_clipe import checar, montar
        # P22: "clipe": false / true (marcador) / ausente não é contrato de movimento — não vai para checar/montar
        erros, avisos = checar([p if isinstance(p.get("clipe"), dict) else dict(p, clipe=None) for p in r["planos"]])
        for x in avisos:
            print("aviso:", x)
        if erros:
            sys.exit("sequência de clipes com erro (nada foi gasto):\n  " + "\n  ".join(erros))
        so = set(a.so.split(",")) if a.so else None
        for p in r["planos"]:
            c = p.get("clipe")
            if not isinstance(c, dict) or (so and p.get("id") not in so):
                if c and not isinstance(c, dict) and (not so or p.get("id") in so):
                    print(f"aviso: {p.get('id')}: 'clipe' = {c!r} sem contrato de movimento ({{movimento}} ou etapas) — pulado")
                continue
            rota = (p.get("direcao") or {}).get("rota") or {}
            if rota.get("rota") in ROTAS_SEM_CLIPE and a.modelo in (None, "auto"):
                print(f"  {p['id']}: rota '{rota['rota']}' — {ROTAS_SEM_CLIPE[rota['rota']]}; não gera clipe aqui")
                continue
            saida = os.path.join(proj, "assets", "clips", f"{p['id']}.mp4")
            if os.path.exists(saida):
                continue  # já gerado (apague para refazer)
            img = os.path.join(proj, "assets", "img", f"{p['id']}-1.png")
            if os.path.exists(img + ".rascunho"):
                sys.exit(f"{p['id']}: a imagem ainda é rascunho — gere a imagem final antes de animar")
            prompt = montar(p["clipe"])  # simples ({movimento}) ou organizado (inicio → etapas → fim)
            dur = c.get("duracao") or rota.get("dur") or a.duracao
            tarefas.append((p["id"], img, prompt, saida, str(dur), rota))
    else:
        if not (a.imagem and a.prompt and a.saida):
            ap.error("use --imagem, --prompt e -o, ou --roteiro")
        tarefas.append(("clipe", a.imagem, a.prompt, a.saida, a.duracao, None))

    plano = []
    for nome, img, prompt, saida, d, rota in tarefas:
        mod, motivo = escolher_modelo(a, d, rota)
        plano.append((nome, img, prompt, saida, d, mod, motivo, custo(mod, d)))
    desconhecidos = [x for x in plano if x[-1] is None]
    total = sum(x[-1] for x in plano if x[-1] is not None)
    print(f"{len(plano)} clipe(s) · custo estimado US$ {total:.2f}"
          + (f" + {len(desconhecidos)} com PREÇO DESCONHECIDO" if desconhecidos else "") + " (preços do catálogo oficial)"
          + (f" · teto do lote US$ {a.orcamento:.2f}" if a.orcamento is not None else ""))
    for nome, img, prompt, saida, d, mod, motivo, p in plano:
        print(f"  {nome:6} {d}s  {fmt_preco(p)}  {mod}\n         {motivo}\n         \"{prompt[:70]}\"")
        if p is None:
            print(f"         preço desconhecido: {problema_preco(mod, d)}")
    if a.orcamento_por_clipe is not None and any(x[-1] is not None and x[-1] > a.orcamento_por_clipe for x in plano):
        sys.exit(f"algum clipe passa do teto de US$ {a.orcamento_por_clipe} por clipe — ajuste --orcamento-por-clipe ou o perfil")
    if a.orcamento is not None and total > a.orcamento + 1e-9:  # P21: teto do LOTE inteiro, não por clipe
        sys.exit(f"o lote soma US$ {total:.2f} e passa do teto total de US$ {a.orcamento:.2f} — reduza os planos (--so) ou aumente --orcamento")
    if not a.confirmar:
        print("Nada foi gerado. Rode de novo com --confirmar para gastar os créditos.")
        return
    if desconhecidos:
        sys.exit("recusado (nada foi gasto): " + "; ".join(f"{x[0]}: {problema_preco(x[5], x[4]) or 'preço desconhecido'}" for x in desconhecidos))
    # P20: duração conferida no schema do modelo ANTES do primeiro gasto (não no meio do lote)
    ruins = [f"{x[0]}: {e}" for x in plano for _, e in [duracao_do_esquema(x[5], x[4])] if e]
    if ruins:
        sys.exit("recusado (nada foi gasto):\n  " + "\n  ".join(ruins))
    for nome, img, prompt, saida, d, mod, motivo, p in plano:
        seg = gerar(img, prompt, saida, mod, d, a.ultimo_quadro, f"{nome} · {d} s")
        print(f"  {nome}: pronto em {seg:.0f}s -> {saida}")


if __name__ == "__main__":
    main()
