"""Lê o roteiro, lista personagens, cenários e objetos, e compara com a biblioteca: o que já existe é reaproveitado,
só o que falta vai para a fila de geração (com custo estimado). Grátis (Gemini texto).

Ideia adaptada da "extração de ativos" do AID Studio (github.com/shijue-aid/aid-studio, MIT).

Uso:
  python extrair_ativos.py <projeto>/ROTEIRO.md            # ou roteiro.json / falas.json / .txt
  → <projeto>/ativos.json + tabela na tela (reaproveitar × gerar novo × custo)
"""
import json
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = Path(__file__).parent
BIBLIOTECA = AQUI.parent / "memoria" / "biblioteca.md"
CUSTO = {"personagem": ("ficha_grade.py ficha", 0.05), "cenario": ("gerar_imagem.py (ou grade 3×3 se precisar de vários ângulos)", 0.05),
         "objeto": ("desenhar em motion (grátis) ou gerar_imagem.py --fundo transparent", 0.0)}

PEDIDO = """Você é o diretor de arte de um estúdio de vídeos curtos. Leia o ROTEIRO e liste tudo que precisa aparecer na tela.
Depois compare com a BIBLIOTECA de ativos já prontos e diga o que pode ser reaproveitado.

Regras:
- personagens: só quem aparece na imagem (narrador em off não conta). Descrição física curta e fixa (idade, pele, cabelo, roupa).
- cenarios: lugares distintos (mesmo lugar em horários diferentes = um cenário, cite os horários).
- objetos: só objetos que a história depende deles (celular com a tela X, agenda de papel, monitor...). Telas/interfaces do sistema são "objeto" com tipo "interface" e sempre são feitas em motion (grátis).
- reaproveitar: caminho EXATO copiado da biblioteca quando o ativo serve como está ou como referência (--ref); senão null. Não invente caminhos.
- aparece_em: ids dos planos/falas onde aparece (se o roteiro tiver ids) ou um trecho curto.
Responda só JSON:
{"personagens":[{"nome":"","descricao":"","aparece_em":[],"reaproveitar":null,"motivo":""}],
 "cenarios":[{"nome":"","descricao":"","horarios":[],"aparece_em":[],"reaproveitar":null,"motivo":"","varios_angulos":false}],
 "objetos":[{"nome":"","tipo":"objeto|interface","aparece_em":[],"reaproveitar":null,"motivo":""}]}

BIBLIOTECA:
"""


def perguntar(texto):
    from tts_gemini import chave
    corpo = {"contents": [{"parts": [{"text": texto}]}],
             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": chave()})
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    roteiro = Path(sys.argv[1])
    sys.path.insert(0, str(AQUI))
    bib = BIBLIOTECA.read_text(encoding="utf-8")
    d = perguntar(PEDIDO + bib + "\n\nROTEIRO:\n" + roteiro.read_text(encoding="utf-8"))

    total, linhas = 0.0, []
    for grupo, tipo in (("personagens", "personagem"), ("cenarios", "cenario"), ("objetos", "objeto")):
        for it in d.get(grupo, []):
            r = it.get("reaproveitar")
            if r and Path(r.replace("\\", "/")).name not in bib:  # caminho citado tem de estar na biblioteca (evita invenção)
                it["motivo"] = f"(caminho '{r}' não está na biblioteca — descartado) " + it.get("motivo", "")
                it["reaproveitar"] = r = None
            if r:
                acao, preco = "reaproveitar", 0.0
            elif it.get("tipo") == "interface":
                acao, preco = "motion (grátis)", 0.0
            else:
                ferramenta, preco = CUSTO[tipo]
                if tipo == "cenario" and it.get("varios_angulos"):
                    ferramenta = "ficha_grade.py grade (9 ângulos numa imagem)"
                acao = f"gerar: {ferramenta}"
            it["acao"], it["custo_estimado"] = acao, preco
            total += preco
            linhas.append((tipo, it.get("nome", "?"), acao, preco, r or it.get("descricao", "")))

    destino = roteiro.parent / "ativos.json"
    d["custo_estimado_total"] = round(total, 3)
    destino.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    for tipo, nome, acao, preco, extra in linhas:
        print(f"  {tipo:10} {nome[:28]:28} {acao[:52]:52} US$ {preco:.2f}\n             {str(extra)[:100]}")
    reap = sum(1 for x in linhas if x[2] == "reaproveitar")
    print(f"\n{len(linhas)} ativos · {reap} reaproveitados · custo estimado do que falta US$ {total:.2f} → {destino}")
    print("Confira os 'reaproveitar' (a IA pode errar a semelhança) antes de pular a geração.")


if __name__ == "__main__":
    main()
