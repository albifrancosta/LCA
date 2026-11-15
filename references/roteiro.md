# Roteiro para vídeo curto narrado

Antes de escrever: leia `memoria/padroes.md` (seções Gancho e Estrutura) e use os padrões Confirmados primeiro.

## Estrutura padrão (30–45 s, vertical)

| Bloco | Tempo | Função | Palavras (≈2,6/s) |
| --- | --- | --- | --- |
| Gancho | 0–3 s | Parar o dedo. Uma dor, um número, uma promessa ou uma contradição. | 6–8 |
| Problema | 3–10 s | Mostrar que você entende a situação de quem assiste. | 15–20 |
| Virada | 10–14 s | "Até que…" / "Agora existe…" — apresenta a solução. | 8–10 |
| Prova / demonstração | 14–30 s | 2–3 benefícios concretos mostrados na tela (print real, número, antes/depois). | 35–40 |
| CTA | últimos 3–5 s | Uma ação só, clara. Repetida na tela. | 8–12 |

16:9 / YouTube (60–90 s): mesma ordem, prova com 4–5 benefícios e um caso real.

## Fórmulas de gancho (escolha 1, adapte)

- **Dor direta:** "Você ainda perde [tempo/dinheiro] com [problema]?"
- **Número:** "[X] horas por semana. É isso que [problema] te custa."
- **Contradição:** "Pare de [ação comum]. Ela está te fazendo [resultado ruim]."
- **Resultado primeiro:** mostrar o resultado final em 1 s, depois "veja como".
- **Segredo:** "O que [quem tem sucesso] faz e ninguém conta."
- **Pergunta-identificação:** "Se você é [público] e [situação], assiste até o fim."

O gancho aparece **escrito na tela no frame 1** (muita gente assiste sem som).

## Regras de escrita para voz

- Frases curtas (≤ 12 palavras). Uma ideia por frase.
- Fale como gente: "você", verbos no presente, sem jargão.
- Palavras-chave (números, nome do produto, benefício) no **fim da frase** — é onde a voz dá ênfase e onde a animação bate.
- Marque as palavras-chave com `**negrito**` na coluna Fala: o `beatmap.py` lê isso e cria batidas visuais.
- Pausa intencional = `…` ou ponto final: vira ponto de corte.
- CTA no imperativo: "Clica no link", "Chama no WhatsApp", "Testa grátis".

## Formato do ROTEIRO.md

```markdown
# <título> — <formato> <duração alvo>
Objetivo: … | Público: … | CTA: …
Padrões aplicados: P01, P04

| # | Fala | Tela | Dur. |
|---|------|------|------|
| 1 | Você ainda perde **3 horas** por dia com planilha? | Texto grande "3 HORAS" + planilha caótica tremendo | 3 s |
| 2 | … | … | … |
```

A coluna "Fala" é o texto exato que vai para a voz. Uma linha da tabela = uma cena.
Para gerar a narração, junte as falas sem os `**`.
