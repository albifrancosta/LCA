"""Camera & Shot Planning — enquadramento, ângulo, movimento, lente, profundidade de campo, transição e eixo por tomada.

Regra principal: a decupagem que já existe na bíblia (fotografia / contrato) MANDA; o planejador só preenche o que falta,
escolhendo pela INTENÇÃO narrativa da tomada (estabelecer, revelar, tensão, ação, diálogo, detalhe, conclusão) e
evitando movimento sem motivo (câmera parada é o padrão). Também confere continuidade de direção (regra dos 180°).
"""
import re

# intenção → (enquadramento, ângulo, movimento, lente mm, profundidade de campo, composição)
INTENCOES = {
    "estabelecer": ("aberto", "altura dos olhos", "pan lento", 24, "profunda", "regra dos terços, horizonte baixo, espaço para o cenário"),
    "revelar": ("fechado", "altura dos olhos", "dolly-in", 50, "rasa", "sujeito centralizado, fundo desfocado"),
    "tensao": ("fechado", "contra-plongée leve", "push-in lento", 85, "rasa", "rosto no terço superior, ar mínimo"),
    "acao": ("medio", "altura dos olhos", "tracking", 35, "média", "espaço à frente do movimento (lead room)"),
    "dialogo": ("medio", "altura dos olhos", "fixa", 50, "média", "plano e contraplano, olhar com espaço"),
    "detalhe": ("detalhe", "plongée", "fixa", 100, "rasa", "objeto preenchendo o quadro"),
    "emocao": ("fechado", "altura dos olhos", "fixa", 85, "rasa", "olhos no terço superior"),
    "conclusao": ("aberto", "altura dos olhos", "pull-back", 35, "profunda", "sujeito pequeno no quadro, respiro"),
}
PALAVRAS = [
    ("detalhe", r"\b(detalhe|tela do|close no|mostra o (celular|tablet|produto)|insert|digita)\b"),
    ("revelar", r"\b(revela|descobre|aparece|surge|mostra pela primeira|percebe)\b"),
    ("tensao", r"\b(tens[aã]o|medo|susto|preocupad|ansios|desespero|suspense)\b"),
    ("acao", r"\b(corre|anda|caminha|pega|entrega|levanta|pula|dirige|chega|sai)\b"),
    ("dialogo", r"\b(fala|diz|responde|pergunta|conversa)\b"),
    ("emocao", r"\b(sorri|chora|alivio|alívio|feliz|triste|orgulho)\b"),
    ("estabelecer", r"\b(abertura|estabelec|vista geral|fachada|cidade|rua)\b"),
    ("conclusao", r"\b(final|fim|encerra|conclus|assinatura)\b"),
]
DE_PRODUCAO = {"geral": "aberto", "plongee": "aberto", "medio": "medio", "americano": "medio", "dois": "medio", "pov": "medio",
               "contra": "medio", "close": "fechado", "detalhe": "detalhe",
               "PG": "aberto", "PC": "aberto", "PM": "medio", "PA": "medio", "PP": "fechado", "PD": "detalhe"}


def inferir_intencao(t):
    if t.get("intencao") in INTENCOES:
        return t["intencao"]
    txt = " ".join(str(x or "") for x in (t.get("acao"), t.get("emocao"), t.get("cena"), t.get("fala"))).lower()
    for nome, rx in PALAVRAS:
        if re.search(rx, txt):
            return nome
    return "dialogo" if t.get("fala") else "estabelecer"


def _lente_mm(v):
    m = re.search(r"(\d+)\s*mm", str(v or ""))
    return int(m.group(1)) if m else None


def planejar_tomada(t, anterior=None):
    dec = t.get("decupagem") or {}
    dire = t.get("direcao") or {}
    intencao = inferir_intencao(t)
    enq, ang, mov, lente, dof, comp = INTENCOES[intencao]
    fonte = "intencao"
    if dec.get("plano") or dire.get("plano"):
        enq = DE_PRODUCAO.get(dec.get("plano") or dire.get("plano"), enq)
        fonte = "decupagem"
    mov = dec.get("movimento") or dire.get("camera") or mov
    lente = _lente_mm(dec.get("lente")) or lente
    if t.get("personagens") and not (t.get("acao") or "").strip() and not dec.get("movimento"):
        mov = "fixa"  # sem ação descrita, movimento seria gratuito
    mesmo_cenario = anterior is not None and anterior.get("cenario") == t.get("cenario")
    transicao = t.get("transicao") or ("corte seco" if mesmo_cenario or anterior is None else "corte com respiro de som")
    mov_pers = f"{dec['inicio']} → {dec['fim']}" if dec.get("inicio") and dec.get("fim") else t.get("acao")
    return {
        "intencao": intencao, "enquadramento": enq, "angulo": dec.get("angulo") or ang, "movimento": mov,
        "lente_mm": lente, "profundidade_campo": "rasa" if (lente or 0) >= 85 else dof, "composicao": comp,
        "movimento_personagens": mov_pers, "transicao_entrada": transicao,
        "lado_eixo": t.get("lado_eixo") or dec.get("lado_eixo"),
        "direcao_tela": t.get("direcao_tela") or dec.get("direcao_tela"), "fonte": fonte,
    }


def planejar_todas(tomadas):
    out, ant = {}, None
    for t in tomadas:
        out[t["id"]] = planejar_tomada(t, ant)
        ant = t
    return out


def checar_eixo(tomadas, planos):
    """Regra dos 180°: tomadas seguidas no MESMO cenário com os mesmos personagens não trocam de lado do eixo nem invertem
    a direção de tela sem `cruza_eixo: true` (justificativa narrativa)."""
    out = []
    for a, b in zip(tomadas, tomadas[1:]):
        if a.get("cenario") != b.get("cenario") or not set(a.get("personagens") or []) & set(b.get("personagens") or []):
            continue
        if b.get("cruza_eixo"):
            continue
        pa, pb = planos.get(a["id"]) or {}, planos.get(b["id"]) or {}
        if pa.get("lado_eixo") and pb.get("lado_eixo") and pa["lado_eixo"] != pb["lado_eixo"]:
            out.append(("media", "quebra_eixo", f"{a['id']}→{b['id']}: câmera trocou de lado do eixo ({pa['lado_eixo']}→{pb['lado_eixo']}) "
                                                "sem justificativa — personagens vão parecer trocar de lugar"))
        if pa.get("direcao_tela") and pb.get("direcao_tela") and pa["direcao_tela"] != pb["direcao_tela"]:
            out.append(("media", "direcao_tela_invertida", f"{a['id']}→{b['id']}: direção de tela {pa['direcao_tela']}→{pb['direcao_tela']}"))
    return out
