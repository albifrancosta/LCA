"""Engenharia reversa de uma referência AUTORIZADA, sob demanda, com o reverse-any-video do HyperFrames INSTALADO.

Não copia o plugin nem fixa versão: lê ~/.claude/plugins/installed_plugins.json (o mecanismo de atualização do plugin)
e usa o installPath/versão que estiver registrado lá. As regras do próprio plugin valem (plugin-installation.md,
"Reverse é recurso do HyperFrames Pro", só vídeos que a pessoa tem direito de usar).

O que aproveitamos para o estúdio (local): ESTRUTURA e RITMO — cortes (`npx hyperframes measure cuts`), duração por
plano, densidade de cortes — guardados no acervo (tipo "tecnica") para orientar roteiro e montagem. O que tem custo
(refilmagem de pessoas com HeyGen, cloud render) só com orçamento no projeto.json e autorização no chat: este script
NUNCA dispara isso.

Uso:
  python referencia_reversa.py onde                                → versão e caminho instalados
  python referencia_reversa.py estrutura <video> --autorizado "<de quem é / por que pode>"
       → roda `npx hyperframes measure cuts` (local) e grava ritmo/cortes no acervo
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import integridade as ig  # noqa: E402

REG = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json")


def instalado(reg=REG):
    """{"versao", "caminho", "skill", "commit"} do hyperframes registrado pelo gerenciador de plugins, ou None."""
    try:
        d = json.load(io.open(reg, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    plugins = d.get("plugins", d)
    for nome, entradas in plugins.items():
        if not str(nome).startswith("hyperframes@"):
            continue
        e = sorted(entradas if isinstance(entradas, list) else [entradas], key=lambda x: x.get("lastUpdated", ""))[-1]
        skill = os.path.join(e["installPath"], "skills", "reverse-any-video", "SKILL.md")
        return {"versao": e.get("version"), "caminho": e["installPath"], "skill": skill if os.path.isfile(skill) else None,
                "commit": e.get("gitCommitSha"), "atualizado": e.get("lastUpdated")}
    return None


def ritmo(cortes, duracao):
    """Cortes (s) → durações por plano, média, mediana, cortes por 10 s."""
    pts = [0.0] + sorted(c for c in cortes if 0 < c < duracao) + [duracao]
    durs = [round(b - a, 3) for a, b in zip(pts, pts[1:]) if b - a > 0.01]
    s = sorted(durs)
    return {"planos": len(durs), "duracoes": durs, "media_s": round(sum(durs) / len(durs), 2) if durs else None,
            "mediana_s": s[len(s) // 2] if s else None, "cortes_por_10s": round(10 * (len(durs) - 1) / duracao, 2) if duracao else None}


def medir_cortes(video):
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx não encontrado — o HyperFrames CLI roda via Node (npx hyperframes …)")
    r = subprocess.run([npx, "hyperframes", "measure", "cuts", video], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"hyperframes measure cuts falhou (plano Pro/auth? veja a mensagem do CLI): {(r.stderr or r.stdout)[-300:]}")
    return sorted({float(x) for x in re.findall(r"(\d+\.\d+)\s*s?\b", r.stdout)}), r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["onde", "estrutura"])
    ap.add_argument("video", nargs="?")
    ap.add_argument("--autorizado", help="de quem é a referência e por que pode ser usada (obrigatório)")
    a = ap.parse_args()
    info = instalado()
    if a.acao == "onde":
        print(json.dumps(info, ensure_ascii=False, indent=1) if info else "hyperframes não está instalado (installed_plugins.json)")
        return
    if not info or not info.get("skill"):
        sys.exit("reverse-any-video não encontrado na versão instalada do HyperFrames")
    if not a.video or not a.autorizado:
        sys.exit("estrutura precisa do vídeo e de --autorizado (só referências que a pessoa tem direito de usar)")
    s = ig.sonda(a.video)
    if not s:
        sys.exit(f"vídeo ilegível: {a.video}")
    cortes, _ = medir_cortes(a.video)
    r = ritmo(cortes, s["duracao"])
    import acervo
    it = acervo.adicionar("tecnica", f"ritmo de referência: {r['planos']} planos em {s['duracao']:.1f}s, média {r['media_s']}s, "
                          f"{r['cortes_por_10s']} cortes/10s", origem=os.path.basename(a.video), licenca=a.autorizado,
                          tags=["ritmo", "referencia", f"hyperframes-{info['versao']}"], arquivo=a.video, qualidade="aprovado",
                          parametros={"ritmo": r, "hyperframes": info["versao"]},
                          restricoes=["referência: estrutura e ritmo apenas — não copiar imagens, personagens ou som"])
    print(f"estrutura gravada no acervo ({it['id']}) com HyperFrames {info['versao']}: {json.dumps(r, ensure_ascii=False)[:300]}")


if __name__ == "__main__":
    main()
