"""Integridade do estúdio: estados de qualidade, hashes, mídia válida, trava de escrita e preço conhecido.

Um só lugar para as regras que todos os scripts precisam seguir (auditoria 2026-11-06, P01–P56):
  - QA tem TRÊS estados: aprovado | reprovado | nao_verificado. Só "aprovado" libera montagem e aprendizado.
  - Arquivo de mídia só conta se existe, não está vazio e o ffprobe lê duração > 0 (vídeo/áudio) — nada de mp4 de 0 byte.
  - Toda versão de ativo guarda sha256; derivados guardam o sha256 de quem os originou (para invalidar quando mudar).
  - JSON compartilhado (producao.json, custos.json) é escrito com trava + gravação atômica.
  - Preço desconhecido NUNCA é US$ 0: é None, e quem for gastar tem de parar.
"""
import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
import time

APROVADO, REPROVADO, NAO_VERIFICADO = "aprovado", "reprovado", "nao_verificado"
ESTADOS = (APROVADO, REPROVADO, NAO_VERIFICADO)
MODOS_ANIMADOS = {"acao", "fala", "reacao"}


class PrecoDesconhecido(Exception):
    """Modelo sem preço confiável: bloquear o gasto até o catálogo ter o preço."""


class FalhaIntegridade(Exception):
    pass


def sha256(arq, bloco=1 << 20):
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        for parte in iter(lambda: f.read(bloco), b""):
            h.update(parte)
    return h.hexdigest()


def sha256_texto(*partes):
    return hashlib.sha256("␟".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def sonda(arq):
    """ffprobe → {"duracao", "video", "audio", "largura", "altura", "fps"} ou None se não for mídia legível."""
    if not arq or not os.path.isfile(arq) or os.path.getsize(arq) == 0:
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
                        "-of", "json", arq], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout or "{}")
        dur = float(d.get("format", {}).get("duration") or 0)
    except (ValueError, TypeError):
        return None
    sts = d.get("streams", [])
    v = next((s for s in sts if s.get("codec_type") == "video"), None)
    fps = None
    if v and v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        a, b = v["r_frame_rate"].split("/")
        fps = float(a) / float(b) if float(b) else None
    return {"duracao": dur, "video": bool(v), "audio": any(s.get("codec_type") == "audio" for s in sts),
            "largura": (v or {}).get("width"), "altura": (v or {}).get("height"), "fps": fps}


def midia_valida(arq, tipo="video", duracao_min=0.04):
    """(ok, motivo). tipo: video | audio | imagem."""
    if not arq or not os.path.isfile(arq):
        return False, f"arquivo ausente: {arq}"
    if os.path.getsize(arq) == 0:
        return False, f"arquivo vazio (0 byte): {arq}"
    if tipo == "imagem":
        try:
            from PIL import Image
            with Image.open(arq) as im:
                im.verify()
            return True, ""
        except Exception as e:  # noqa: BLE001
            return False, f"imagem ilegível: {arq} ({e})"
    s = sonda(arq)
    if not s:
        return False, f"mídia ilegível pelo ffprobe: {arq}"
    if tipo == "video" and not s["video"]:
        return False, f"sem faixa de vídeo: {arq}"
    if tipo == "audio" and not (s["audio"] or arq.lower().endswith(".wav")):
        return False, f"sem faixa de áudio: {arq}"
    if s["duracao"] < duracao_min:
        return False, f"duração {s['duracao']:.2f}s: {arq}"
    return True, ""


@contextlib.contextmanager
def trava(arq, espera=30.0):
    """Trava exclusiva por arquivo (<arq>.lock, criado com O_EXCL). Evita que dois agentes percam a escrita um do outro."""
    lock = arq + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock)), exist_ok=True)  # 1º uso numa pasta nova
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):  # Windows: trava sendo apagada dá PermissionError — está ocupada, espere
            with contextlib.suppress(OSError):
                if time.time() - os.path.getmtime(lock) > 120:  # trava órfã (processo morreu)
                    os.remove(lock)
                    continue
            if time.time() - t0 > espera:
                raise FalhaIntegridade(f"{arq} está travado por outro processo há mais de {espera:.0f}s")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(lock)


def gravar_json_atomico(arq, dados):
    pasta = os.path.dirname(os.path.abspath(arq))
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    for n in range(20):  # Windows: antivírus/leitor com o arquivo aberto faz o replace falhar por instantes
        try:
            os.replace(tmp, arq)
            return
        except PermissionError:
            if n == 19:
                raise
            time.sleep(0.05 * (n + 1))


def atualizar_json(arq, funcao, padrao=None):
    """Lê-modifica-grava sob trava. `funcao(dados)` altera no lugar e/ou devolve o novo objeto."""
    with trava(arq):
        dados = json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else (padrao if padrao is not None else {})
        novo = funcao(dados)
        dados = dados if novo is None else novo
        if isinstance(dados, dict):
            dados["_revisao"] = int(dados.get("_revisao", 0)) + 1
        gravar_json_atomico(arq, dados)
        return dados


def estado_qa(problemas, verificado):
    """problemas: [(gravidade, texto)]. verificado=False → nao_verificado (nunca vira aprovado)."""
    if any(g == "grave" for g, _ in problemas):
        return REPROVADO
    return APROVADO if verificado else NAO_VERIFICADO


def estado_inspecao(base, plano_id, arquivo=None):
    """Estado de QA de um plano segundo a última inspeção gravada pelo inspetor.py
    (<base>/entrega/inspecao-planos.json → itens[{id, estado, sha256_clipe}]).
    Se `arquivo` for dado, a inspeção só vale para o MESMO conteúdo (sha256 do clipe inspecionado).
    Sem inspeção registrada = nao_verificado."""
    rel = os.path.join(base, "entrega", "inspecao-planos.json")
    if not os.path.exists(rel):
        return NAO_VERIFICADO, "sem inspeção registrada"
    try:
        itens = json.load(open(rel, encoding="utf-8")).get("itens", [])
    except (ValueError, OSError):
        return NAO_VERIFICADO, "inspecao-planos.json ilegível"
    it = next((i for i in itens if i.get("id") == plano_id), None)
    if not it:
        return NAO_VERIFICADO, "plano não inspecionado"
    est = it.get("estado") or NAO_VERIFICADO
    if arquivo and it.get("sha256_clipe") and os.path.isfile(arquivo) and sha256(arquivo) != it["sha256_clipe"]:
        return NAO_VERIFICADO, "o clipe mudou depois da inspeção"
    return est, it.get("motivo", "")
