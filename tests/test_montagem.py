"""Testes do portão de montagem (auditoria P40–P55) — sem rede, sem APIs pagas.

TTS (tts_gemini), alinhamento (timeline_comercial) e Whisper (faster_whisper) são simulados; mp4/wav/png de teste
são criados com ffmpeg/PIL em pastas temporárias. Requer ffmpeg/ffprobe no PATH.
Uso: PYTHONIOENCODING=utf-8 python tests/test_montagem.py   (sai ≠ 0 se algum teste falhar)
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
import types
import wave
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

# ------------------------------------------------------------------ dublês (antes de importar montar_historia)
chamadas_tts = []


def wav(path, seg=0.3):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x10\x00" * int(24000 * seg))


def sintetizar(texto, voz, estilo, saida, **kw):
    chamadas_tts.append(texto)
    wav(saida)


mock_tts = types.ModuleType("tts_gemini")
mock_tts.sintetizar = sintetizar
sys.modules["tts_gemini"] = mock_tts
mock_tl = types.ModuleType("timeline_comercial")
mock_tl.alinhar = lambda escritas, faladas: [(0.0, 0.15) for _ in escritas]
sys.modules["timeline_comercial"] = mock_tl
mock_fw = types.ModuleType("faster_whisper")


class WhisperModel:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, *a, **k):
        return [types.SimpleNamespace(words=[types.SimpleNamespace(word="x", start=0.0, end=0.15)])], None


mock_fw.WhisperModel = WhisperModel
sys.modules["faster_whisper"] = mock_fw


def carregar(nome):
    spec = importlib.util.spec_from_file_location(nome + "_teste", SCRIPTS / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mh = carregar("montar_historia")
pr = carregar("preparar_remotion")
from integridade import sha256, sha256_texto  # noqa: E402

# ------------------------------------------------------------------ utilitários


def mp4(path, dur=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=160x284:rate=30:duration={dur}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def png(path, cor=(200, 30, 30)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (90, 160), cor).save(path)


def novo(root, nome, planos):
    proj = root / nome
    (proj / "remotion" / "src").mkdir(parents=True)
    (proj / "remotion" / "public").mkdir()
    (proj / "remotion" / "package.json").write_text("{}")  # evita copiar o modelo
    (proj / "roteiro.json").write_text(json.dumps({"planos": planos}, ensure_ascii=False), encoding="utf-8")
    return proj


def inspecao(proj, itens):
    (proj / "entrega").mkdir(exist_ok=True)
    (proj / "entrega" / "inspecao-planos.json").write_text(json.dumps({"itens": itens}), encoding="utf-8")


def rodar(mod, argv):
    """Roda main() → (saida_stdout, erro SystemExit ou None)."""
    buf, prev = io.StringIO(), sys.argv
    erro = None
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit as e:
        erro = str(e.code)
    finally:
        sys.argv = prev
    return buf.getvalue(), erro


def montar(proj, *extra):
    return rodar(mh, ["montar_historia.py", str(proj / "roteiro.json"), "--trilha", "nenhuma", *extra])


def historia(proj):
    return json.loads((proj / "remotion" / "src" / "historia.json").read_text(encoding="utf-8"))


def plano_img(pid="p01", **kw):
    return {"id": pid, "tipo": "imagem", "dur": 1.0, "prompts": ["cena"], **kw}


# ------------------------------------------------------------------ testes
TESTES = []


def teste(f):
    TESTES.append(f)
    return f


@teste
def final_falha_sem_clipe(root):
    proj = novo(root, "sem_clipe", [plano_img(modo="acao")])
    png(proj / "assets/img/p01-1.png")
    _, erro = montar(proj)
    assert erro and "p01" in erro and "exige clipe" in erro, erro
    assert not (proj / "remotion/src/historia.json").exists()


@teste
def final_falha_modo_em_direcao(root):
    proj = novo(root, "sem_clipe_direcao", [plano_img(direcao={"modo": "fala"})])
    png(proj / "assets/img/p01-1.png")
    _, erro = montar(proj)
    assert erro and "exige clipe" in erro, erro


@teste
def final_falha_mp4_vazio(root):
    proj = novo(root, "vazio", [plano_img(modo="acao")])
    png(proj / "assets/img/p01-1.png")
    (proj / "assets/clips").mkdir(parents=True)
    (proj / "assets/clips/p01.mp4").write_bytes(b"")
    _, erro = montar(proj)
    assert erro and "vazio" in erro, erro


@teste
def final_falha_rascunho(root):
    proj = novo(root, "rascunho", [plano_img()])
    png(proj / "assets/img/p01-1.png")
    (proj / "assets/img/p01-1.png.rascunho").write_text("")
    _, erro = montar(proj)
    assert erro and "rascunho" in erro, erro


@teste
def final_falha_rascunho_que_seria_criado(root):
    proj = novo(root, "rascunho_novo", [plano_img()])  # imagem não existe e --imagens rascunho (padrão)
    _, erro = montar(proj)
    assert erro and "seria rascunho" in erro, erro


@teste
def final_falha_clipe_nao_inspecionado(root):
    proj = novo(root, "sem_inspecao", [plano_img(modo="acao")])
    mp4(proj / "assets/clips/p01.mp4")
    _, erro = montar(proj)
    assert erro and "nao_verificado" in erro, erro


@teste
def final_falha_clipe_mudou_apos_inspecao(root):
    proj = novo(root, "mudou", [plano_img(modo="acao")])
    mp4(proj / "assets/clips/p01.mp4")
    inspecao(proj, [{"id": "p01", "estado": "aprovado", "sha256_clipe": "0" * 64}])
    _, erro = montar(proj)
    assert erro and "mudou depois da inspeção" in erro, erro


@teste
def preview_passa_com_avisos(root):
    proj = novo(root, "preview", [plano_img(modo="acao")])
    (proj / "assets/clips").mkdir(parents=True)
    (proj / "assets/clips/p01.mp4").write_bytes(b"")
    out, erro = montar(proj, "--preview")
    assert erro is None, erro
    assert "AVISO" in out and "p01" in out, out
    h = historia(proj)
    assert "video" not in h["planos"][0]  # mp4 vazio nunca entra, nem no preview
    assert (proj / "assets/img/p01-1.png.rascunho").exists()
    assert h["montagem"]["modo"] == "preview"


@teste
def aprovado_passa_com_midia(root):
    proj = novo(root, "aprovado", [plano_img(modo="acao")])
    clipe = proj / "assets/clips/p01.mp4"
    mp4(clipe)
    inspecao(proj, [{"id": "p01", "estado": "aprovado", "sha256_clipe": sha256(clipe)}])
    out, erro = montar(proj)
    assert erro is None, erro + out
    p = historia(proj)["planos"][0]
    assert p["video"] == "assets/clips/p01.mp4" and p["videoDur"] > 0
    assert p["midia"]["sha256"] == sha256(clipe) and p["midia"]["qa_estado"] == "aprovado", p["midia"]
    assert p["midia"]["arquivo"] == "assets/clips/p01.mp4"


@teste
def aceitar_sem_inspecao(root):
    proj = novo(root, "antigo", [plano_img(modo="acao")])
    mp4(proj / "assets/clips/p01.mp4")
    out, erro = montar(proj, "--aceitar-sem-inspecao")
    assert erro is None, erro
    assert "aceito por --aceitar-sem-inspecao" in out
    assert historia(proj)["planos"][0]["midia"]["qa_estado"] == "nao_verificado"
    inspecao(proj, [{"id": "p01", "estado": "reprovado"}])
    _, erro = montar(proj, "--aceitar-sem-inspecao")
    assert erro and "reprovado" in erro, erro  # reprovado continua bloqueando


@teste
def video_de_exige_aceite(root):
    proj = novo(root, "reuso", [plano_img("p01", modo="acao"), plano_img("p02", modo="acao", video_de="p01")])
    clipe = proj / "assets/clips/p01.mp4"
    mp4(clipe)
    inspecao(proj, [{"id": "p01", "estado": "aprovado", "sha256_clipe": sha256(clipe)}])
    _, erro = montar(proj)
    assert erro and "p02" in erro and "video_de" in erro, erro
    r = json.loads((proj / "roteiro.json").read_text(encoding="utf-8"))
    r["planos"][1]["video_de_aprovado"] = True
    (proj / "roteiro.json").write_text(json.dumps(r), encoding="utf-8")
    _, erro = montar(proj)
    assert erro is None, erro
    p2 = historia(proj)["planos"][1]
    assert p2["midia"]["origem"] == "p01" and "video_de_aprovado" not in p2


@teste
def voz_regenera_quando_texto_muda(root):
    proj = novo(root, "voz", [plano_img(fala="frase nova")])
    png(proj / "assets/img/p01-1.png")
    arq = proj / "assets/voz/p01.wav"
    wav(arq)
    (Path(str(arq) + ".json")).write_text(json.dumps({"texto_sha": sha256_texto("frase velha", "Charon", "suspense")}))
    antes = len(chamadas_tts)
    _, erro = montar(proj)  # final sem autorização: para e NÃO gasta TTS
    assert erro is not None and "regravar" in str(erro) and len(chamadas_tts) == antes, (erro, chamadas_tts[antes:])
    _, erro = montar(proj, "--regravar-vozes")
    assert erro is None, erro
    assert chamadas_tts[antes:] == ["frase nova"], chamadas_tts[antes:]
    lado = json.loads(Path(str(arq) + ".json").read_text(encoding="utf-8"))
    assert lado["texto_sha"] == sha256_texto("frase nova", "Charon", "suspense")
    assert any((proj / "assets/voz/_antigas").iterdir())  # voz anterior preservada
    antes = len(chamadas_tts)
    _, erro = montar(proj)  # mesmo texto → reaproveita
    assert erro is None and len(chamadas_tts) == antes


@teste
def voz_sem_registro(root):
    proj = novo(root, "voz_sem_registro", [plano_img(fala="texto atual")])
    png(proj / "assets/img/p01-1.png")
    arq = proj / "assets/voz/p01.wav"
    wav(arq)
    antes = len(chamadas_tts)
    out, erro = montar(proj, "--preview")  # preview adota o WAV (voz externa) e grava o registro
    assert erro is None and len(chamadas_tts) == antes, (erro, out)
    assert Path(str(arq) + ".json").exists()
    os.remove(str(arq) + ".json")
    _, erro = montar(proj)  # final: sem registro = desatualizado → para sem gastar
    assert erro is not None and len(chamadas_tts) == antes, (erro, chamadas_tts[antes:])
    _, erro = montar(proj, "--regravar-vozes")  # com autorização: regenera
    assert erro is None and chamadas_tts[antes:] == ["texto atual"], chamadas_tts[antes:]


def projeto_base(root, nome, cenas):
    proj = root / nome
    proj.mkdir()
    (proj / "BEATS.json").write_text(json.dumps({
        "scenes": [{"id": f"c{i + 1}", "start": i * 1.0, "end": (i + 1) * 1.0, "words": [i, i]} for i in range(len(cenas))],
        "groups": [{"start": i * 1.0, "end": (i + 1) * 1.0, "words": [i, i]} for i in range(len(cenas))]}))
    (proj / "transcript.json").write_text(json.dumps(
        {"words": [{"text": f"w{i}", "start": i + 0.1, "end": i + 0.5} for i in range(len(cenas))]}))
    (proj / "cenas.json").write_text(json.dumps(cenas), encoding="utf-8")
    rem = proj / "remotion"
    (rem / "src").mkdir(parents=True)
    (rem / "package.json").write_text("{}")
    return proj


def preparar(proj, *extra, cwd=None):
    velho = os.getcwd()
    try:
        os.chdir(cwd or velho)
        return rodar(pr, ["preparar_remotion.py", str(proj / "remotion"), "--beats", str(proj / "BEATS.json"),
                          "--transcript", str(proj / "transcript.json"), "--cenas", str(proj / "cenas.json"), *extra])
    finally:
        os.chdir(velho)


@teste
def preparar_nomes_distintos_e_caminho_do_projeto(root):
    proj = projeto_base(root, "base", [{"tipo": "imagem", "src": "a/cena.png"}, {"tipo": "imagem", "src": "b/cena.png"}])
    png(proj / "a/cena.png", (255, 0, 0))
    png(proj / "b/cena.png", (0, 0, 255))
    wav(proj / "assets/voz.wav")
    _, erro = preparar(proj, "--voz", "assets/voz.wav", cwd=root)  # cwd ≠ projeto: voz resolvida pela pasta do projeto
    assert erro is None, erro
    v = json.loads((proj / "remotion/src/video.json").read_text(encoding="utf-8"))
    a, b = v["cenas"][0]["src"], v["cenas"][1]["src"]
    assert a != b, (a, b)
    pub = proj / "remotion/public"
    assert sha256(pub / a) == sha256(proj / "a/cena.png") and sha256(pub / b) == sha256(proj / "b/cena.png")
    assert v["audio"]["voz"] and (pub / v["audio"]["voz"]).is_file()
    assert v["cenas"][0]["midia"]["sha256"] == sha256(proj / "a/cena.png")


@teste
def preparar_video_sfx_e_portao(root):
    cenas = {"cenas": [{"tipo": "video", "src": "clips/c1.mp4", "de": 0.2},
                       {"tipo": "imagem", "src": "img.png", "sfx": [{"src": "bip.wav", "apos": 0.1}]}],
             "sfx": [{"src": "bip.wav", "inicio": 0.05}]}
    proj = projeto_base(root, "base_video", cenas["cenas"])
    (proj / "cenas.json").write_text(json.dumps(cenas), encoding="utf-8")
    mp4(proj / "clips/c1.mp4")
    png(proj / "img.png")
    wav(proj / "bip.wav", 0.2)
    _, erro = preparar(proj)
    assert erro is None, erro
    v = json.loads((proj / "remotion/src/video.json").read_text(encoding="utf-8"))
    assert v["cenas"][0]["tipo"] == "video" and v["cenas"][0]["videoDur"] > 0
    assert len(v["sfx"]) == 2 and abs(v["sfx"][1]["inicio"] - 1.1) < 1e-6, v["sfx"]
    _, erro = preparar(proj, "--final")
    assert erro and "nao_verificado" in erro, erro
    inspecao(proj, [{"id": "c1", "estado": "aprovado", "sha256_clipe": sha256(proj / "clips/c1.mp4")}])
    _, erro = preparar(proj, "--final")
    assert erro is None, erro


@teste
def preparar_recusa_tipo_e_video_invalidos(root):
    proj = projeto_base(root, "base_ruim", [{"tipo": "clipe_magico"}])
    _, erro = preparar(proj)
    assert erro and "não suportado" in erro, erro
    proj = projeto_base(root, "base_vazio", [{"tipo": "video", "src": "v.mp4"}])
    (proj / "v.mp4").write_bytes(b"")
    _, erro = preparar(proj)
    assert erro and "clipe inválido" in erro, erro


@teste
def video_tsx_estatico(root):
    s = (SKILL / "templates/remotion-base/src/Video.tsx").read_text(encoding="utf-8")
    assert "video: CenaVideo" in s and "OffthreadVideo" in s  # P45
    assert 'c.zoom === "in" ? 1 + 0.12 * p : 1' in s  # P49: sem zoom = parado
    assert "<Entrada><Comp" not in s and 'c.entrada === "fade" && !primeira' in s  # P50
    assert "CENAS[c.tipo] ?? CenaErro" in s  # P55


def main():
    falhas = 0
    with tempfile.TemporaryDirectory(prefix="teste-montagem-") as tmp:
        for f in TESTES:
            pasta = Path(tmp) / f.__name__
            pasta.mkdir()
            try:
                f(pasta)
                print(f"PASS  {f.__name__}")
            except Exception:  # noqa: BLE001
                falhas += 1
                print(f"FAIL  {f.__name__}")
                traceback.print_exc()
    print(f"\n{len(TESTES) - falhas}/{len(TESTES)} passaram")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
