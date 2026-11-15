"""Gera ou edita imagens com a API de imagens da OpenAI (GPT Image) para as cenas do criador-video.

Uso:
    python gerar_imagem.py "prompt" -o assets/cena1.png [--formato vertical] [--qualidade medium] [--n 1] --confirmar
    python gerar_imagem.py "troque o fundo por ..." -o assets/cena1b.png --ref assets/cena1.png [--ref logo.png] --confirmar

Sem --confirmar NÃO chama a API: só mostra o custo estimado e sai com código 3 (nada gerado), para quem chama em
subprocess não seguir achando que a imagem existe. Imagem idêntica já paga (cache) é copiada de graça, com ou sem --confirmar.

Chave: variável OPENAI_API_KEY (lida também do registro do Windows, caso o app ainda não tenha reiniciado).
Só biblioteca padrão. Nunca imprime a chave.
"""
import argparse
import base64
import datetime
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://api.openai.com/v1/images"
PRECO_ESTIMADO = {"low": 0.012, "medium": 0.05, "high": 0.19, "auto": 0.05}  # US$ por imagem 1024x1536 (medium medido na conta; low/high estimados)
FORMATOS = {"vertical": "1024x1536", "horizontal": "1536x1024", "quadrado": "1024x1024", "auto": "auto"}


def chave():
    import chaves
    return chaves.obter("OPENAI_API_KEY", contexto="imagens com a OpenAI")


def multipart(campos, arquivos):
    limite = uuid.uuid4().hex
    partes = []
    for nome, valor in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    for nome, caminho in arquivos:
        tipo = mimetypes.guess_type(caminho)[0] or "image/png"
        cab = (f'--{limite}\r\nContent-Disposition: form-data; name="{nome}"; filename="{Path(caminho).name}"\r\n'
               f"Content-Type: {tipo}\r\n\r\n").encode()
        partes.append(cab + Path(caminho).read_bytes() + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def chamar(url, corpo, tipo):
    req = urllib.request.Request(url, data=corpo, method="POST",
                                 headers={"Authorization": f"Bearer {chave()}", "Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        try:
            detalhe = json.loads(detalhe)["error"]["message"]
        except Exception:
            pass
        sys.exit(f"erro da OpenAI ({e.code}): {detalhe}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("-o", "--out", required=True, help="arquivo .png (com --n > 1 vira nome-1.png, nome-2.png…)")
    ap.add_argument("--modelo", default="gpt-image-2.5-sunburst",
                    help="gpt-image-2.5-sunburst (padrão) · gpt-image-2 (texto legível, telas, infográfico) · gpt-image-1-mini (barato)")
    ap.add_argument("--formato", default="vertical", help="vertical | horizontal | quadrado | auto | LxA (ex.: 1024x1536)")
    ap.add_argument("--qualidade", default="medium", choices=["low", "medium", "high", "auto"])
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--ref", action="append", default=[], help="imagem de referência (repita para várias) → modo edição")
    ap.add_argument("--fundo", choices=["auto", "transparent", "opaque"], help="transparent = PNG sem fundo")
    ap.add_argument("--confirmar", action="store_true", help="gera de verdade (gasta créditos da OpenAI)")
    a = ap.parse_args()

    tamanho = FORMATOS.get(a.formato, a.formato)
    campos = {"model": a.modelo, "prompt": a.prompt, "size": tamanho, "quality": a.qualidade, "n": a.n}
    if a.fundo:
        campos["background"] = a.fundo

    # cache: mesma imagem (prompt + modelo + tamanho + qualidade + referências) já paga? reaproveita sem gastar
    sys.path.insert(0, str(Path(__file__).parent))
    from custos import cache_buscar, cache_chave, cache_guardar, registrar
    preco = PRECO_ESTIMADO.get(a.qualidade, 0.05) * a.n
    chave_c = cache_chave("imagem", **campos, refs=list(a.ref))
    achado = cache_buscar("imagem", chave_c, ".png") if a.n == 1 else None
    if achado:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(Path(achado).read_bytes())
        registrar("imagem", a.modelo, preco, f"{out.name} (reaproveitada do cache)", "estimado", cache=True)
        print(f"{out}\ncache: imagem idêntica já gerada antes — nada foi pago")
        return

    if a.ref:
        for r in a.ref:
            if not Path(r).exists():
                sys.exit(f"referência não encontrada: {r}")
    if not a.confirmar:  # P24: sem autorização explícita, nenhuma chamada paga
        print(f"custo estimado: US$ {preco:.3f} ({a.n} imagem(ns) {a.modelo}, {a.qualidade}, {tamanho}) → {a.out}")
        print("Nada foi gerado. Rode de novo com --confirmar para gastar os créditos.")
        sys.exit(3)

    if a.ref:
        corpo, tipo = multipart({k: str(v) for k, v in campos.items()}, [("image[]", r) for r in a.ref])
        resp = chamar(f"{API}/edits", corpo, tipo)
    else:
        resp = chamar(f"{API}/generations", json.dumps(campos, ensure_ascii=False).encode("utf-8"), "application/json")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    salvos = []
    for i, item in enumerate(resp.get("data", []), 1):
        destino = out if len(resp["data"]) == 1 else out.with_name(f"{out.stem}-{i}{out.suffix or '.png'}")
        destino.write_bytes(base64.b64decode(item["b64_json"]))
        salvos.append(str(destino))
    if not salvos:
        sys.exit("a OpenAI não devolveu imagem")
    meta = {"modelo": a.modelo, "tamanho": tamanho, "qualidade": a.qualidade, "prompt": a.prompt,
            "refs": a.ref, "uso": resp.get("usage"), "data": datetime.date.today().isoformat(), "arquivos": salvos}
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(salvos) == 1:
        cache_guardar("imagem", chave_c, salvos[0])
    registrar("imagem", a.modelo, preco, ", ".join(Path(s).name for s in salvos), f"estimado ({a.qualidade}, anotado 2026-11-03)")
    for s in salvos:
        print(s)
    uso = resp.get("usage") or {}
    print(f"modelo {a.modelo} · {tamanho} · {a.qualidade} · tokens de imagem {uso.get('output_tokens', '?')}")


if __name__ == "__main__":
    main()
