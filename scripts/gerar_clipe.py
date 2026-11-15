"""CLI genérica de clipe (imagem → vídeo) pelo ROTEADOR: Runware primeiro, fal.ai e outros como fallback, com orçamento,
reserva, trava de estilo e inspeção (INTEGRACAO-RUNWARE.md §3.5). A CLI legada `gerar_clipe_fal.py` continua igual.

Uso:
  python gerar_clipe.py --imagem cena.png --prompt "ele pega o celular e franze a testa" --duracao 5 -o clips/c05a.mp4 \
      --job exemplo-dois-mundos --cena c05a [--ultimo-quadro fim.png] [--politica runware_primary] [--provedor runware-kling26-pro]
  python gerar_clipe.py ... --planejar      → mostra quem geraria, por quê e quanto custa (nada é chamado)
  python gerar_clipe.py --retomar clips/c05a.mp4  → job já enviado: consulta o MESMO job (Runware) ou recupera (fal); não reenvia
Saída: JSON da resposta uniforme do roteador (status success | waiting_approval | pendente_verificacao | sem_provedor).
"""
import argparse
import io
import json
import os
import subprocess
import sys
from dataclasses import asdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagem")
    ap.add_argument("--ultimo-quadro")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--duracao", type=float, default=5)
    ap.add_argument("-o", "--saida")
    ap.add_argument("--job", default="avulso")
    ap.add_argument("--cena", default="")
    ap.add_argument("--modo", default="final", choices=["preview", "final"])
    ap.add_argument("--politica")
    ap.add_argument("--provedor", help="força um provedor do catálogo (política manual)")
    ap.add_argument("--planejar", action="store_true")
    ap.add_argument("--retomar", metavar="CLIPE.mp4")
    a = ap.parse_args()
    if a.retomar:
        if os.path.exists(a.retomar + ".runware.json"):
            import runware
            try:
                print(json.dumps(asdict(runware.Cliente().retomar(a.retomar)), ensure_ascii=False, indent=1))
            except runware.ErroRunware as e:
                sys.exit(f"[{e.tipo}] {e}")
            return
        sys.exit(subprocess.call([sys.executable, os.path.join(AQUI, "gerar_clipe_fal.py"), "--recuperar", a.retomar]))
    if not (a.imagem and a.saida):
        ap.error("--imagem e -o são obrigatórios")
    import provedores as pv
    t = {"job_id": a.job, "scene_id": a.cena or os.path.splitext(os.path.basename(a.saida))[0], "task_type": "video", "mode": a.modo,
         "requirements": {"capabilities": ["video", "i2v"] + (["ultimo_quadro"] if a.ultimo_quadro else []), "imagem": os.path.abspath(a.imagem),
                          "duration_s": a.duracao, "prompt": a.prompt, "saida": os.path.abspath(a.saida)}}
    if a.ultimo_quadro:
        t["requirements"]["ultimo_quadro"] = os.path.abspath(a.ultimo_quadro)
    if a.provedor:
        t.update(routing_policy="manual", provider=a.provedor)
    elif a.politica:
        t["routing_policy"] = a.politica
    arq = a.saida + ".tarefa.json"
    os.makedirs(os.path.dirname(os.path.abspath(arq)) or ".", exist_ok=True)
    json.dump(t, io.open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.planejar:
        return pv.planejar(t)
    r = pv.executar(t)
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    sys.exit(0 if r["status"] == "success" else 4 if r["status"] == "waiting_approval" else 2)


if __name__ == "__main__":
    main()
