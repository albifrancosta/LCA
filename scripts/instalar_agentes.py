"""Instala e confere os agentes do estúdio (estudio-*.md) que a skill usa como departamentos.

Os agentes moram em `<skill>/agentes/`, mas o Claude Code só os enxerga em `~/.claude/agents/`
(ou em `<projeto>/.claude/agents/`). Este script copia e avisa quando a cópia instalada está velha.

  python instalar_agentes.py verificar            → ok | faltando | desatualizado (não muda nada; código 1 se algo falta)
  python instalar_agentes.py instalar             → copia os que faltam ou mudaram (o antigo diferente vira .md.bak)
  python instalar_agentes.py remover              → apaga só os estudio-*.md que vieram desta skill
  --destino <pasta>                               → outra pasta de agentes (ex.: <projeto>/.claude/agents)
  --json                                          → saída em JSON

Instalar grava em ~/.claude/agents — é configuração do usuário: o Claude só roda `instalar` com o ok dele no chat.
Depois de instalar, os agentes aparecem numa sessão NOVA do Claude Code.
"""
import argparse
import glob
import json
import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEM = os.path.join(SKILL_DIR, "agentes")
DESTINO_PADRAO = os.path.join(os.path.expanduser("~"), ".claude", "agents")


def agentes():
    return sorted(glob.glob(os.path.join(ORIGEM, "estudio-*.md")))


def _ler(p):
    with open(p, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def verificar(destino=DESTINO_PADRAO):
    itens = []
    for src in agentes():
        nome = os.path.basename(src)
        alvo = os.path.join(destino, nome)
        if not os.path.exists(alvo):
            estado = "faltando"
        elif _ler(alvo) != _ler(src):
            estado = "desatualizado"
        else:
            estado = "ok"
        itens.append({"agente": nome[:-3], "estado": estado})
    pend = [i for i in itens if i["estado"] != "ok"]
    return {"destino": destino, "total": len(itens), "ok": len(itens) - len(pend), "pendentes": pend, "itens": itens}


def instalar(destino=DESTINO_PADRAO):
    os.makedirs(destino, exist_ok=True)
    feitos = []
    for src in agentes():
        nome = os.path.basename(src)
        alvo = os.path.join(destino, nome)
        if os.path.exists(alvo):
            if _ler(alvo) == _ler(src):
                continue
            shutil.copy2(alvo, alvo + ".bak")
            feitos.append({"agente": nome[:-3], "acao": "atualizado (anterior em .md.bak)"})
        else:
            feitos.append({"agente": nome[:-3], "acao": "instalado"})
        shutil.copy2(src, alvo)
    return {"destino": destino, "feitos": feitos, "obs": "abra uma sessão nova do Claude Code para os agentes aparecerem"}


def remover(destino=DESTINO_PADRAO):
    removidos = []
    for nome in sorted(os.path.basename(p) for p in agentes()):
        alvo = os.path.join(destino, nome)
        if os.path.exists(alvo):
            os.remove(alvo)
            removidos.append(nome[:-3])
    return {"destino": destino, "removidos": removidos}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Instala/confere os agentes do estúdio")
    ap.add_argument("acao", choices=["verificar", "instalar", "remover"])
    ap.add_argument("--destino", default=DESTINO_PADRAO)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = {"verificar": verificar, "instalar": instalar, "remover": remover}[a.acao](a.destino)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif a.acao == "verificar":
        print(f"Agentes do estúdio em {r['destino']}: {r['ok']}/{r['total']} em dia")
        for i in r["pendentes"]:
            print(f"  ⚪ {i['agente']}: {i['estado']}")
        if r["pendentes"]:
            print("Para instalar/atualizar: python \"" + os.path.abspath(__file__) + "\" instalar")
    elif a.acao == "instalar":
        print(f"Destino: {r['destino']}")
        for f in r["feitos"] or [{"agente": "—", "acao": "nada a fazer, tudo em dia"}]:
            print(f"  ✅ {f['agente']}: {f['acao']}")
        print(r["obs"])
    else:
        print(f"Removidos de {r['destino']}: {', '.join(r['removidos']) or 'nenhum'}")
    if a.acao == "verificar" and r["pendentes"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
