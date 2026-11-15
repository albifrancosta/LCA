"""Prompt de clipe organizado (quadro inicial → câmera em etapas → quadro final → estilo) + checagem da sequência.

Ideia adaptada do "diretor visual" do AID Studio (github.com/shijue-aid/aid-studio, MIT): cada clipe descreve
onde começa, como a câmera anda em etapas e onde termina; o quadro final tem de bater com o storyboard,
e dois planos vizinhos não repetem o mesmo movimento de câmera. Menos clipe reprovado = menos dinheiro jogado fora.

No roteiro.json, o plano pode ter o clipe no formato simples (antigo) ou organizado (novo):
  "clipe": {"movimento": "ele olha o celular"}                       ← simples (continua funcionando)
  "clipe": {                                                          ← organizado
    "duracao": 5,
    "assunto": "dono da empresa no escritório",
    "inicio": "plano médio, ele lê o celular apoiado na mesa",
    "etapas": [
      {"camera": "aproximar", "acao": "ele franze a testa", "ate": 2.5},
      {"camera": "parada",    "acao": "ele larga o celular e passa a mão no rosto"}
    ],
    "fim": "close no rosto preocupado, celular fora de quadro",     ← tem de bater com o storyboard
    "estilo": "opcional; padrão = mesmo estilo da imagem"
  }

Uso:
  python prompt_clipe.py roteiro.json          # mostra os prompts montados e os avisos (grátis)
`gerar_clipe_fal.py --roteiro` usa este módulo sozinho e recusa a sequência se houver erro.
"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# vocabulário de câmera: pt → en (modelos de vídeo entendem melhor em inglês)
CAMERA = {
    "parada": "static camera, locked off",
    "aproximar": "slow push-in (dolly in)",
    "afastar": "slow pull-out (dolly out)",
    "zoom": "slow zoom in",
    "panoramica esquerda": "slow pan left",
    "panoramica direita": "slow pan right",
    "subir": "tilt up",
    "descer": "tilt down",
    "orbitar": "slow orbit around the subject",
    "acompanhar": "tracking shot following the subject",
    "grua subindo": "crane up",
    "grua descendo": "crane down",
    "na mao": "subtle handheld movement",
    "travelling lateral": "lateral truck move",
}
SEM_ACENTO = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
FINAL_PADRAO = "Keep the exact same art style, character identity, outfit and lighting as the input image; smooth natural motion; no text, no new people."


def _cam(c):
    chave = (c or "parada").lower().translate(SEM_ACENTO).strip()
    return chave, CAMERA.get(chave, c)


def organizado(clipe):
    return isinstance(clipe, dict) and ("etapas" in clipe or "inicio" in clipe)


def montar(clipe, duracao=None):
    """Clipe (formato simples ou organizado) → prompt em texto."""
    if not organizado(clipe):
        return f"{clipe['movimento']}. {FINAL_PADRAO}"
    dur = float(duracao or clipe.get("duracao", 5))
    etapas = clipe.get("etapas") or [{"camera": "parada", "acao": clipe.get("acao", "")}]
    partes = []
    if clipe.get("assunto"):
        partes.append(f"Subject: {clipe['assunto']}.")
    if clipe.get("inicio"):
        partes.append(f"Opening frame: {clipe['inicio']}.")
    t0 = 0.0
    for i, e in enumerate(etapas):
        fim = float(e.get("ate", dur if i == len(etapas) - 1 else t0 + (dur - t0) / (len(etapas) - i)))
        _, cam = _cam(e.get("camera"))
        partes.append(f"{t0:g}-{fim:g}s: {cam}; {e.get('acao', '').strip()}.")
        t0 = fim
    if clipe.get("fim"):
        partes.append(f"Final frame (must end exactly like this): {clipe['fim']}.")
    partes.append(f"Style: {clipe['estilo']}." if clipe.get("estilo") else "")
    partes.append(FINAL_PADRAO)
    return " ".join(p for p in partes if p)


def checar(planos):
    """Avisos e erros da sequência de clipes. Retorna (erros, avisos)."""
    erros, avisos = [], []
    anterior = None  # (id, câmera principal)
    anterior_fim = None  # (id, quadro final, ambiente) do plano com clipe imediatamente anterior
    for p in planos:
        c = p.get("clipe")
        if not c:
            anterior = anterior_fim = None  # plano sem clipe (motion/ilustração parada) quebra a vizinhança
            continue
        pid = p.get("id", "?")
        if not organizado(c):
            if len(c.get("movimento", "")) < 12:
                avisos.append(f"{pid}: movimento muito vago — descreva ação + câmera (ou use o formato organizado)")
            anterior = anterior_fim = None
            continue
        if not c.get("fim"):
            erros.append(f"{pid}: falta 'fim' (quadro final) — sem ele o clipe termina onde quiser e não casa com o próximo plano")
        if not c.get("inicio"):
            avisos.append(f"{pid}: falta 'inicio' — o modelo vai partir só da imagem")
        etapas = c.get("etapas") or []
        try:
            dur = float(c.get("duracao", 5))
        except (TypeError, ValueError):
            dur = 0
        if dur <= 0:
            erros.append(f"{pid}: duração inválida")
        if not etapas:
            erros.append(f"{pid}: sem etapas — o modelo não recebe ação nenhuma com tempo")
        t0 = 0.0
        for i, e in enumerate(etapas, 1):  # timeline estrita (auditoria P30, P31, P33)
            ultimo = i == len(etapas)
            try:
                ate = float(e["ate"]) if "ate" in e else (dur if ultimo else None)
            except (TypeError, ValueError):
                ate = None
            if ate is None:
                erros.append(f"{pid} etapa {i}: falta 'ate' (só a última pode omitir: vai até o fim do plano)")
                continue
            if ate <= t0:
                erros.append(f"{pid} etapa {i}: tempo fora de ordem ({t0:g}→{ate:g}s)")
            if ate > dur + 0.05:
                erros.append(f"{pid} etapa {i}: termina em {ate:g}s, depois do fim do plano ({dur:g}s)")
            if not (e.get("acao") or "").strip() and not e.get("pausa"):
                erros.append(f"{pid} etapa {i}: ação vazia (pausa intencional = \"pausa\": true com a ação de respiração/olhar)")
            t0 = max(t0, ate)
        if etapas and t0 + 0.2 < dur:
            erros.append(f"{pid}: as etapas acabam em {t0:g}s e o plano dura {dur:g}s — o modelo não recebe ação para o fim")
        if len(etapas) > 3 and dur <= 5:
            avisos.append(f"{pid}: {len(etapas)} etapas em {c.get('duracao', 5)} s é muita coisa — no máximo 2–3")
        for e in etapas:
            k, _ = _cam(e.get("camera"))
            if k not in CAMERA:
                avisos.append(f"{pid}: câmera '{e.get('camera')}' fora do vocabulário ({', '.join(CAMERA)}) — vai como está")
        if anterior_fim and c.get("inicio") and not c.get("transicao_intencional"):  # continuidade (P32)
            mesmo_lugar = not (p.get("ambiente") and anterior_fim[2] and p.get("ambiente") != anterior_fim[2])
            if mesmo_lugar and _norm(c["inicio"]) != _norm(anterior_fim[1]):
                erros.append(f"{pid}: o quadro inicial não repete o final de {anterior_fim[0]} (\"{anterior_fim[1]}\") — copie o quadro "
                             "final do plano anterior ou marque \"transicao_intencional\": true (corte de propósito)")
        principal = next((_cam(e.get("camera"))[0] for e in etapas if _cam(e.get("camera"))[0] != "parada"), "parada")
        if anterior and principal == anterior[1] and principal != "parada":
            erros.append(f"{pid}: repete o movimento '{principal}' do plano vizinho {anterior[0]} — troque um dos dois")
        anterior = (pid, principal)
        anterior_fim = (pid, c.get("fim"), p.get("ambiente")) if c.get("fim") else None
    return erros, avisos


def _norm(t):
    return " ".join(str(t).lower().translate(SEM_ACENTO).replace(".", " ").replace(",", " ").split())


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    r = json.load(open(sys.argv[1], encoding="utf-8"))
    planos = r.get("planos", []) if isinstance(r, dict) else r
    for p in planos:
        if p.get("clipe"):
            print(f"[{p.get('id')}] {montar(p['clipe'])}\n")
    erros, avisos = checar(planos)
    for a in avisos:
        print("aviso:", a)
    for e in erros:
        print("ERRO:", e)
    print("sequência OK" if not erros else f"{len(erros)} erro(s) — corrija antes de gastar")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
