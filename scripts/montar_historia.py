"""Modo HISTÓRIA: transforma roteiro.json em projeto Remotion pronto (modelo templates/remotion-historia).

Uso:
  python montar_historia.py <projeto>/roteiro.json [--imagens rascunho|gerar] [--trilha suspense|<arquivo>|nenhuma]
                            [--qualidade low|medium|high] [--so-voz]

roteiro.json:
{
  "titulo": "...", "personagem": "descrição fixa do protagonista (vai em todo prompt que o cite)",
  "personagem_ref": "assets/personagem.png (opcional: mantém o mesmo rosto em todas as imagens)",
  "estilo": "prefixo de estilo das imagens",
  "voz": {"nome": "Charon", "estilo": "direção de voz"},
  "planos": [
    {"id": "p01", "tipo": "cadeia|imagem|pov|expressoes|preto|cartao", "fala": "texto narrado",
     "prompts": ["geral...", "médio...", "close..."], "zoom": [1, 1.35], "foco": [0.5, 0.45],
     "camadas": [...], "toque": 0.6, "silencio_antes": true, "dur": 1.0, "texto": "cartão",
     "titulo": "PLANO Nº 47 (texto grande por cima do plano, desde o 1º quadro)"}
  ],
  "legenda": {"alturaLegenda": 0.82}  (opcional: muda posição/cor/tamanho da legenda)
}
- Cada plano dura a sua fala + respiro; plano sem fala usa "dur". "toque" (pov) e "trocas" (expressoes) são
  relativos ao início do plano (fração 0–1); o script converte para segundos absolutos.
- `--imagens rascunho` (padrão) cria quadros provisórios grátis com o prompt escrito — para aprovar ritmo e roteiro.
  `--imagens gerar` chama gerar_imagem.py (custo na conta OpenAI) para os prompts que ainda não têm imagem.

Portão de montagem (auditoria P46–P54):
- Padrão = montagem FINAL, que falha fechado (SystemExit com id do plano e motivo) se: plano animado
  (modo acao/fala/reacao) sem clipe válido; clipe com inspeção diferente de "aprovado"
  (entrega/inspecao-planos.json, mesmo sha256); qualquer ativo usado ainda `.rascunho`; `video_de` sem aprovação do
  reuso (inspeção aprovada do próprio plano, ou clipe de origem aprovado + "video_de_aprovado": true no plano).
- `--preview`: comportamento permissivo antigo (rascunhos, clipes ausentes/não inspecionados) com lista de AVISOS.
- `--aceitar-sem-inspecao`: final para projetos anteriores ao inspetor — mídia continua obrigatória e válida, mas
  clipe "nao_verificado" vira aviso (clipe "reprovado" continua bloqueando).
- Voz: cada WAV tem um <wav>.json {"texto_sha"}; texto/voz/tom mudou → regenera (o WAV antigo vai para
  assets/voz/_antigas/). WAV sem .json: no --preview é adotado (grava o .json); no final é regenerado.
- historia.json recebe, por plano, `midia` {tipo, arquivo, sha256, qa_estado} para o inspetor conferir 1:1.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
import wave

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
from tts_gemini import sintetizar  # noqa: E402
from timeline_comercial import alinhar  # noqa: E402
from integridade import (APROVADO, MODOS_ANIMADOS, NAO_VERIFICADO, estado_inspecao,  # noqa: E402
                         gravar_json_atomico, midia_valida, sha256, sha256_texto, sonda)

PY = sys.executable
TAXA = 24000
RESPIRO = 0.35  # pausa entre frases (medida no original: 0,4–1,0 s)
PAUSA_DRAMATICA = 0.7
ESTILO_LEGENDA = {"corLegenda": "#87C968", "alturaLegenda": 0.68, "tamanhoLegenda": 0.026, "palavrasPorGrupo": 4}
# Tom do catálogo de tts_gemini.TONS (estilo curto em inglês, formato oficial); "tom" por plano vence o do roteiro.
VOZ_PADRAO = {"nome": "Charon", "tom": "suspense", "estilo": ""}


from integridade import relativo as _rel  # noqa: E402  (relpath seguro entre discos)


def ler_wav(arq):
    with wave.open(arq) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        taxa = w.getframerate()
    if taxa != TAXA:
        x = np.interp(np.arange(0, len(x), taxa / TAXA), np.arange(len(x)), x)
    return x


def salvar_wav(arq, x, taxa=TAXA):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with wave.open(arq, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def trilha_suspense(duracao, arq, taxa=44100):
    """Drone grave + ruído filtrado + pulso lento (batida de coração). Gratuita, gerada aqui."""
    t = np.arange(int(duracao * taxa)) / taxa
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t)
    x = 0.35 * np.sin(2 * np.pi * 55 * t) * lfo + 0.22 * np.sin(2 * np.pi * 82.4 * t + np.sin(2 * np.pi * 0.11 * t))
    x += 0.12 * np.sin(2 * np.pi * 116.5 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))  # trítono leve
    ruido, acc = np.random.default_rng(3).standard_normal(len(t)), 0.0
    filtrado = np.empty_like(ruido)
    for i, r in enumerate(ruido):
        acc += 0.015 * (r - acc)
        filtrado[i] = acc
    # chiado de "vento" bem baixo: mais alto que isso soa como ruído entre as falas (feedback do usuário, 2026-11-03)
    x += 0.3 * filtrado * (0.5 + 0.5 * np.sin(2 * np.pi * 0.03 * t))
    for b in np.arange(1.0, duracao, 1.6):  # pulso "tum-tum"
        for d in (0, 0.28):
            i0 = int((b + d) * taxa)
            tn = t[i0:i0 + int(0.3 * taxa)] - t[i0]
            x[i0:i0 + len(tn)] += 0.5 * np.sin(2 * np.pi * 48 * tn) * np.exp(-tn * 16)
    fade = np.minimum(1, np.minimum(t / 2, (duracao - t) / 2))
    salvar_wav(arq, x / np.max(np.abs(x)) * 0.85 * fade, taxa)
    return arq


def rascunho(arq, prompt, idx):
    """Quadro provisório 1080x1920 com o prompt escrito (sem custo)."""
    from PIL import Image, ImageDraw, ImageFont
    cores = [((18, 28, 58), (44, 70, 130)), ((30, 22, 40), (90, 60, 110)), ((15, 40, 45), (40, 110, 120))]
    a, b = cores[idx % len(cores)]
    grad = np.linspace(0, 1, 1920)[:, None, None]
    img = Image.fromarray((np.array(a) + (np.array(b) - np.array(a)) * grad).repeat(1080, axis=1).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for r in range(6):  # anéis para ver o zoom
        d.ellipse([540 - 120 * r - 60, 860 - 120 * r - 60, 540 + 120 * r + 60, 860 + 120 * r + 60], outline=(120, 140, 190), width=3)
    try:
        f = ImageFont.truetype("arial.ttf", 46)
    except OSError:
        f = ImageFont.load_default()
    d.text((80, 300), "RASCUNHO", fill=(255, 200, 80), font=f)
    d.multiline_text((80, 380), "\n".join(textwrap.wrap(prompt, 34)[:10]), fill=(235, 235, 235), font=f, spacing=12)
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    img.save(arq)


def no_projeto(arq, proj):
    """Caminho relativo é do projeto (pasta do roteiro.json); cai no cwd só se não existir lá."""
    if os.path.isabs(arq) or os.path.exists(os.path.join(proj, arq)):
        return os.path.join(proj, arq)
    return arq


def modo_do_plano(p):
    return (p.get("direcao") or {}).get("modo") or p.get("modo")


def eh_rascunho(arq):
    return os.path.exists(arq + ".rascunho")


def avaliar_clipe(p, proj, final, aceitar_sem_inspecao):
    """Decide se o plano entra com clipe. → (clipe_info | None, problemas, avisos).
    clipe_info = {"rel", "abs", "dur", "sha256", "qa_estado", "origem"}."""
    pid = p["id"]
    origem = p.get("video_de", pid)  # video_de: reusa o clipe de outro plano
    rel = f"assets/clips/{origem}.mp4"
    clipe = os.path.join(proj, "assets", "clips", f"{origem}.mp4")
    animado = modo_do_plano(p) in MODOS_ANIMADOS
    problemas, avisos = [], []
    if not os.path.exists(clipe):
        if animado:
            (problemas if final else avisos).append(f"{pid}: modo {modo_do_plano(p)} exige clipe e não há {rel}")
        return None, problemas, avisos
    ok, motivo = midia_valida(clipe, "video")
    s = sonda(clipe) if ok else None
    if ok and not (s and s["duracao"] > 0):
        ok, motivo = False, f"duração 0: {clipe}"
    if not ok:  # nunca entra no filme um mp4 vazio/ilegível — nem no preview (quebraria o render)
        msg = f"{pid}: clipe inválido ({motivo})"
        if final:
            problemas.append(msg)
        else:
            avisos.append(msg + " — plano fica com a imagem")
        return None, problemas, avisos
    # QA: a inspeção do próprio plano vale; para reuso (video_de), vale a do plano de origem + aceite explícito
    est, mot = estado_inspecao(proj, pid, clipe)
    if origem != pid and est != APROVADO:
        est_o, mot_o = estado_inspecao(proj, origem, clipe)
        if not p.get("video_de_aprovado"):
            msg = (f"{pid}: reusa o clipe de {origem} (video_de) sem aprovação do reuso — inspecione {pid} com esse clipe "
                   f"ou marque \"video_de_aprovado\": true depois de conferir ação/identidade (origem: {est_o})")
            (problemas if final else avisos).append(msg)
        est, mot = est_o, mot_o
    if est != APROVADO:
        msg = f"{pid}: inspeção do clipe {rel} = {est}" + (f" ({mot})" if mot else "")
        if not final:
            avisos.append(msg)
        elif est == NAO_VERIFICADO and aceitar_sem_inspecao:
            avisos.append(msg + " — aceito por --aceitar-sem-inspecao")
        else:
            problemas.append(msg)
    info = {"rel": rel, "abs": clipe, "dur": round(s["duracao"], 3), "sha256": sha256(clipe), "qa_estado": est}
    if origem != pid:
        info["origem"] = origem
    return info, problemas, avisos


def falhar_ou_avisar(problemas, avisos, etapa):
    for m in avisos:
        print(f"  AVISO: {m}")
    if problemas:
        raise SystemExit(f"Montagem final bloqueada ({etapa}) — {len(problemas)} problema(s):\n  - " + "\n  - ".join(problemas)
                         + "\nCorrija, ou rode com --preview (rascunho de ritmo) / --aceitar-sem-inspecao (projeto antigo).")


def preparar_voz(p, voz, arq, preview, regravar=False):
    """Garante que o WAV corresponde ao texto atual (P48). Regenera quando o texto/voz/tom mudou."""
    nome, tom = p.get("voz") or voz["nome"], p.get("tom") or voz.get("tom")
    texto_sha = sha256_texto(p["fala"], nome, tom)
    lado = arq + ".json"
    motivo = None
    if not os.path.exists(arq):
        motivo = "novo"
    elif not midia_valida(arq, "audio")[0]:
        motivo = "WAV inválido"
    elif os.path.exists(lado):
        try:
            if json.load(open(lado, encoding="utf-8")).get("texto_sha") != texto_sha:
                motivo = "texto/voz/tom mudou"
        except (ValueError, OSError):
            motivo = "sidecar ilegível"
    elif preview:
        # WAV sem registro (ex.: voz clonada do VoiceStudio): no preview é adotado para o texto atual
        print(f"  AVISO: {p['id']}: {os.path.basename(arq)} sem registro de texto — adotado para a fala atual (--preview)")
    else:
        motivo = "WAV sem registro do texto (rode --preview uma vez para adotar uma voz externa)"
    if motivo and os.path.exists(arq) and not regravar:
        # regravar voz existente gasta TTS e troca uma voz que o usuário pode ter aprovado: só com pedido explícito
        raise SystemExit(f"{p['id']}: voz existente não confere ({motivo}). Nada foi regravado. Opções: --regravar-vozes "
                         "(gera de novo; a antiga vai para _antigas/) ou --preview (adota o WAV atual para a fala atual)")
    if motivo:
        if os.path.exists(arq):  # nunca destruir uma voz (pode ser clonada): guarda a antiga
            antigas = os.path.join(os.path.dirname(arq), "_antigas")
            os.makedirs(antigas, exist_ok=True)
            n = len([f for f in os.listdir(antigas) if f.startswith(p["id"] + "-")]) + 1
            shutil.move(arq, os.path.join(antigas, f"{p['id']}-{n}.wav"))
            print(f"  voz {p['id']}: {motivo} — regenerando (anterior em _antigas/)")
        sintetizar(p["fala"], nome, voz.get("estilo", ""), arq, tom=tom)
        ok, m = midia_valida(arq, "audio")
        if not ok:
            raise SystemExit(f"{p['id']}: TTS não produziu áudio válido ({m})")
    with open(lado, "w", encoding="utf-8") as f:
        json.dump({"texto_sha": texto_sha, "texto": p["fala"], "voz": nome, "tom": tom}, f, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roteiro")
    ap.add_argument("--imagens", default="rascunho", choices=["rascunho", "gerar"])
    ap.add_argument("--qualidade", default="medium")
    ap.add_argument("--trilha", default="suspense")
    ap.add_argument("--volume-trilha", type=float, default=0.28)
    ap.add_argument("--ambiente", help="WAV de ambientação (ambiente.py); 'auto' = gera da bíblia (producao.json)")
    ap.add_argument("--volume-ambiente", type=float, default=1.0)
    ap.add_argument("--so-voz", action="store_true", help="gera só as falas e mostra a duração")
    ap.add_argument("--regravar-vozes", action="store_true",
                    help="autoriza regravar (TTS) vozes existentes cujo texto/voz/tom não confere — sem isso o final para e avisa")
    ap.add_argument("--preview", action="store_true",
                    help="montagem de rascunho: aceita imagens .rascunho e clipes ausentes/não inspecionados (só avisa)")
    ap.add_argument("--aceitar-sem-inspecao", action="store_true",
                    help="final de projeto antigo: exige mídia válida, mas clipe nao_verificado vira aviso")
    a = ap.parse_args()
    final = not a.preview and not a.so_voz

    proj = os.path.dirname(os.path.abspath(a.roteiro))
    r = json.load(open(a.roteiro, encoding="utf-8"))
    voz = {**VOZ_PADRAO, **r.get("voz", {})}
    pv = os.path.join(proj, "assets", "voz")
    pi = os.path.join(proj, "assets", "img")
    print("Montagem:", "PREVIEW (rascunho)" if a.preview else "FINAL" + (" (sem inspeção aceita)" if a.aceitar_sem_inspecao else ""))

    # 0. portão ANTES de gastar com voz/imagem: clipes (P46/P47/P51/P54) e ativos que ficariam rascunho (P52)
    problemas, avisos, clipes = [], [], {}
    for p in r["planos"]:
        info, pr, av = avaliar_clipe(p, proj, final, a.aceitar_sem_inspecao)
        problemas += pr
        avisos += av
        clipes[p["id"]] = info
        if info:  # o clipe substitui a imagem no filme — imagens do plano não são usadas
            continue
        for src in p.get("arquivos", []):
            if not os.path.isfile(os.path.join(proj, src)):
                problemas.append(f"{p['id']}: arquivo de imagem ausente: {src}")
            elif eh_rascunho(os.path.join(proj, src)):
                (problemas if final else avisos).append(f"{p['id']}: imagem {src} é rascunho")
        for k, _ in enumerate([] if p.get("arquivos") else p.get("prompts", [])):
            arq = os.path.join(pi, f"{p['id']}-{k + 1}.png")
            if a.imagens != "gerar" and (not os.path.exists(arq) or eh_rascunho(arq)):
                (problemas if final else avisos).append(
                    f"{p['id']}: imagem {p['id']}-{k + 1}.png seria rascunho (use --imagens gerar, ou --preview)")
        for cam in p.get("camadas") or []:
            arq = os.path.join(proj, cam.get("src", ""))
            if not os.path.isfile(arq):
                problemas.append(f"{p['id']}: camada ausente: {cam.get('src')}")
            elif eh_rascunho(arq):
                (problemas if final else avisos).append(f"{p['id']}: camada {cam['src']} é rascunho")
    if not a.so_voz:
        falhar_ou_avisar(problemas, avisos, "clipes e imagens")

    # 1. voz por plano: reaproveita só o WAV que corresponde ao texto atual (sidecar <wav>.json)
    for p in r["planos"]:
        if p.get("fala"):
            preparar_voz(p, voz, os.path.join(pv, f"{p['id']}.wav"), preview=a.preview, regravar=a.regravar_vozes)
    # 2. timeline
    from faster_whisper import WhisperModel
    modelo = WhisperModel("small", compute_type="int8")
    t, trilha_voz, palavras, silencios, planos = 0.3, [np.zeros(int(0.3 * TAXA))], [], [], []
    for p in r["planos"]:
        if p.get("silencio_antes"):
            silencios.append({"inicio": round(t, 3), "fim": round(t + PAUSA_DRAMATICA, 3)})
            trilha_voz.append(np.zeros(int(PAUSA_DRAMATICA * TAXA)))
            t += PAUSA_DRAMATICA
        ini = t
        if p.get("fala"):
            arq = os.path.join(pv, f"{p['id']}.wav")
            x = ler_wav(arq)
            segs, _ = modelo.transcribe(arq, language="pt", word_timestamps=True, initial_prompt=__import__("marca").vocabulario())
            faladas = [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]
            escritas = p["fala"].split()
            palavras += [{"text": e, "start": round(ini + s, 3), "end": round(ini + f, 3)} for e, (s, f) in zip(escritas, alinhar(escritas, faladas))]
            dur = len(x) / TAXA + RESPIRO
            trilha_voz += [x, np.zeros(int(RESPIRO * TAXA))]
        else:
            dur = p.get("dur", 3.0 if p["tipo"] == "cartao" else 1.0)
            trilha_voz.append(np.zeros(int(dur * TAXA)))
        t += dur
        planos.append((p, ini, t))
    duracao = round(t, 3)
    print(f"Duração: {duracao:.1f}s · {len(palavras)} palavras ({len(palavras) / duracao:.2f}/s) · alvo {r.get('duracao_alvo', '—')}s")
    for p, i0, i1 in planos:
        print(f"  {p['id']:5} {p['tipo']:10} {i0:6.1f}-{i1:6.1f}  {(p.get('fala') or p.get('texto') or '')[:60]}")
    if a.so_voz:
        return
    salvar_wav(os.path.join(proj, "assets", "narracao.wav"), np.concatenate(trilha_voz))

    # 3. imagens
    gerar = []
    for p in r["planos"]:
        for k, src in enumerate(p.get("arquivos", [])):  # imagem pronta (print fictício, foto) no lugar de prompt
            os.makedirs(pi, exist_ok=True)
            dest = os.path.join(pi, f"{p['id']}-{k + 1}.png")
            shutil.copy(os.path.join(proj, src), dest)
            if eh_rascunho(dest) and not eh_rascunho(os.path.join(proj, src)):
                os.remove(dest + ".rascunho")  # marca velha de um rascunho que esta imagem real substituiu
        for k, prompt in enumerate([] if p.get("arquivos") else p.get("prompts", [])):
            arq = os.path.join(pi, f"{p['id']}-{k + 1}.png")
            if os.path.exists(arq) and not os.path.exists(arq + ".rascunho"):
                continue
            if a.imagens == "gerar":
                gerar.append((arq, prompt))
            else:
                rascunho(arq, prompt, k)
                open(arq + ".rascunho", "w").close()
    if gerar:
        print(f"Gerando {len(gerar)} imagens ({a.qualidade}) na conta OpenAI…")
        for arq, prompt in gerar:
            com_personagem = "personagem" in prompt.lower()
            texto = f"{r.get('estilo', '')} "
            if com_personagem and r.get("personagem"):
                texto += f"Personagem: {r['personagem']}. "
            texto += f"{prompt}. Sem texto na imagem. Vertical 9:16."
            cmd = [PY, os.path.join(AQUI, "gerar_imagem.py"), texto, "-o", arq, "--formato", "vertical", "--qualidade", a.qualidade]
            if com_personagem and r.get("personagem_ref"):
                cmd += ["--ref", os.path.join(proj, r["personagem_ref"])]
            subprocess.run(cmd, check=True)
            if os.path.exists(arq + ".rascunho"):
                os.remove(arq + ".rascunho")

    # 4. projeto Remotion
    rem = os.path.join(proj, "remotion")
    if not os.path.exists(os.path.join(rem, "package.json")):
        shutil.copytree(os.path.join(SKILL_DIR, "templates", "remotion-historia"), rem, dirs_exist_ok=True)
        print("Projeto Remotion criado — rode `npm install` em", rem)
    pub = os.path.join(rem, "public")
    shutil.copytree(os.path.join(proj, "assets"), os.path.join(pub, "assets"), dirs_exist_ok=True)
    trilha = None
    if a.trilha == "suspense":
        trilha = "assets/trilha-suspense.wav"
        trilha_suspense(duracao, os.path.join(pub, trilha))
    elif a.trilha != "nenhuma":
        trilha = "assets/" + os.path.basename(a.trilha)
        shutil.copy(no_projeto(a.trilha, proj), os.path.join(pub, trilha))

    ambiente = None
    if a.ambiente and a.ambiente != "auto":
        ambiente = "assets/" + os.path.basename(a.ambiente)
        shutil.copy(no_projeto(a.ambiente, proj), os.path.join(pub, ambiente))

    saida, problemas, avisos = [], [], []
    for p, i0, i1 in planos:
        n = len(p.get("arquivos") or p.get("prompts", []))
        c = {k: v for k, v in p.items() if k not in ("fala", "prompts", "arquivos", "silencio_antes", "dur", "clipe", "video_de",
                                                     "video_de_aprovado")}
        imagens = [f"assets/img/{p['id']}-{k + 1}.png" for k in range(n)]
        info = clipes.get(p["id"])  # validado no portão (passo 0); sem clipe o plano fica com a imagem
        if info:
            c["video"] = info["rel"]
            c["videoDur"] = info["dur"]
            c["midia"] = {"tipo": "video", "arquivo": info["rel"], "sha256": info["sha256"], "qa_estado": info["qa_estado"],
                          **({"origem": info["origem"]} if info.get("origem") else {})}
        else:
            usados = [os.path.join(proj, x) for x in imagens]
            for arq in usados:  # 2ª checagem, depois da geração: o que vai para o filme (P52)
                ok, motivo = midia_valida(arq, "imagem") if os.path.exists(arq) else (p["tipo"] in ("preto", "cartao"), f"ausente: {arq}")
                if not ok:
                    problemas.append(f"{p['id']}: imagem inválida ({motivo})")
                elif eh_rascunho(arq):
                    (problemas if final else avisos).append(f"{p['id']}: {os.path.basename(arq)} é rascunho")
            principal = next((x for x in usados if os.path.isfile(x)), None)
            c["midia"] = {"tipo": "imagem" if principal else "nenhuma",
                          "arquivo": _rel(principal, proj).replace(os.sep, "/") if principal else None,
                          "sha256": sha256(principal) if principal else None,
                          "qa_estado": estado_inspecao(proj, p["id"])[0],
                          "imagens": [{"arquivo": _rel(x, proj).replace(os.sep, "/"), "sha256": sha256(x),
                                       "rascunho": eh_rascunho(x)} for x in usados if os.path.isfile(x)]}
        if not saida:  # 1º plano cobre o quadro 0 (gancho visível sem som, P07) — a voz segue no seu tempo
            i0 = 0.0
        c.update({"inicio": round(i0, 3), "fim": round(i1, 3), "imagens": imagens})
        if "toque" in p:
            c["toque"] = round(i0 + p["toque"] * (i1 - i0), 3)
        if "trocas" in p:
            c["trocas"] = [round(i0 + x * (i1 - i0), 3) for x in p["trocas"]]
        elif p["tipo"] == "expressoes" and n > 1:
            c["trocas"] = [round(i0 + (k + 1) * (i1 - i0) / n, 3) for k in range(n - 1)]
        saida.append(c)
    falhar_ou_avisar(problemas, avisos, "ativos usados")
    for c, prox in zip(saida, saida[1:]):  # sem tela preta entre planos: o plano segura até o próximo (pausa dramática incluída)
        if prox["inicio"] - c["fim"] > 0.04:
            c["fim"] = prox["inicio"]
    dados = {"fps": 30, "width": 1080, "height": 1920, "duracao": duracao, "estilo": {**ESTILO_LEGENDA, **(r.get("legenda") or {})},
             "audio": {"voz": "assets/narracao.wav", "trilha": trilha, "volumeTrilha": a.volume_trilha, "silencios": silencios,
                       "ambiente": ambiente, "volumeAmbiente": a.volume_ambiente},
             "planos": saida, "legenda": palavras,
             "montagem": {"modo": "preview" if a.preview else ("final-sem-inspecao" if a.aceitar_sem_inspecao else "final"),
                          "roteiro_sha256": sha256(os.path.abspath(a.roteiro))}}
    gravar_json_atomico(os.path.join(rem, "src", "historia.json"), dados)
    if a.ambiente == "auto":  # ambientação a partir dos cenários da bíblia, nos tempos reais dos planos
        from ambiente import blocos_da_historia, escrever, montar
        hj = os.path.join(rem, "src", "historia.json")
        blocos, dur = blocos_da_historia(hj, {}, "nenhum")
        escrever(montar(blocos, dur), os.path.join(pub, "assets", "ambiente.wav"))
        dados["audio"]["ambiente"] = "assets/ambiente.wav"
        gravar_json_atomico(hj, dados)
        print("  ambiente:", " → ".join(f"{t} ({s:.1f}s)" for s, t in blocos))
    print("Pronto:", os.path.join(rem, "src", "historia.json"))


if __name__ == "__main__":
    main()
