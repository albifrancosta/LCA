"""Vocabulário da marca do usuário: como o TTS deve PRONUNCIAR o nome e como o whisper costuma ESCREVER o que ouviu.

Arquivo: `<skill>/config/marca.json` (opcional; sem ele nada é trocado). Exemplo:
{
  "pronuncia": {"MinhaMarca": "Minha Márca"},
  "variantes": {"minhamarca": ["minha marca", "mina marca"]},
  "vocabulario": "MinhaMarca, nome do produto, termos do ramo"
}
  pronuncia   → texto escrito → como a voz deve falar (só no áudio; a legenda mantém a grafia)
  variantes   → o que o whisper pode escrever → contam como a mesma palavra na conferência da fala
  vocabulario → dica para a transcrição (initial_prompt do whisper)
"""
import json
import os
import re
import unicodedata

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cache = None


def carregar():
    global _cache
    if _cache is None:
        caminho = os.environ.get("CRIADOR_VIDEO_MARCA") or os.path.join(SKILL_DIR, "config", "marca.json")
        try:
            with open(caminho, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _norm(p):
    p = unicodedata.normalize("NFKD", p.lower())
    return "".join(c for c in p if not unicodedata.combining(c))


def falado(texto):
    """Troca o nome escrito pela pronúncia configurada."""
    for escrito, dito in carregar().get("pronuncia", {}).items():
        texto = re.sub(rf"\b{re.escape(escrito)}\b", dito, texto)
    return texto


def unificar(palavras_normalizadas):
    """Variantes que o whisper escreve para a marca viram a forma canônica."""
    mapa = {}
    for canonica, vs in carregar().get("variantes", {}).items():
        for v in [canonica, *vs]:
            mapa[_norm(v)] = _norm(canonica)
    return [mapa.get(p, p) for p in palavras_normalizadas]


def vocabulario(extra=""):
    v = carregar().get("vocabulario", "")
    return ", ".join(x for x in (v, extra) if x) or None
