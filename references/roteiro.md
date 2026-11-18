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

## Técnicas que seguram a atenção (2026-11-17, do estudo de vídeos que fizeram 10× o tamanho do canal)

Vieram do pacote "Heist & Dark History Studio". Use as técnicas, nunca o texto de ninguém.

- **Precisão no lugar de adjetivo.** "Três minutos e vinte e quatro segundos" convence mais que "num instante". "R$ 0,93" convence mais que "quase nada". Cada número é exato e tem fonte, ou vem com "cerca de" (`references/verdade-direitos.md`). Se o vídeo afirma um fato, entregue o `FONTES.md` junto com o roteiro.
- **Descarte o que o espectador espera.** "Sem arma. Sem túnel. Sem hacker." Depois mostre o método comum, que surpreende justamente por ser simples. No comercial: "Não é mais um app. Não é planilha." e depois o que é.
- **Plante uma ideia sem anunciar.** Uma frase com uma comparação do dia a dia ("Câmera não impede nada. Quem impede é quem está olhando.") volta sozinha lá na frente. Nunca escreva "lembra disso".
- **Pergunta como transição.** Passe de um bloco ao outro respondendo a pergunta que o espectador já está fazendo ("Por que um elevador de mudança?"), com a resposta logo em seguida.
- **Todo número ganha uma escala.** "Cerca de quatro vezes o recorde anterior", "o salário de um ano inteiro".
- **Final que retoma o começo em três fragmentos curtos.** "Um elevador de mudança. Quatro minutos. Uma câmera que deu zoom tarde demais." Nada de frase genérica do canal depois disso. (Complementa o P53, final que conversa com o começo.)
- **Diga a incerteza em voz alta.** "Segundo a polícia", "a empresa não comentou", "ninguém sabe ainda". O que segue em aberto costuma virar o final.
- **No último terço, nada de desvio.** Depois do pico, cada frase leva ao final.
- **Números e horários escritos como se fala** ("nove e trinta e quatro", "oitenta e oito milhões"), para a voz ler certo. No `beatmap.py`, a batida visual cai na palavra, não no dígito.

**Frases proibidas** (apontam o efeito em vez de criá-lo): "agora vamos", "a seguir", "lembra disso", "pensa nisso", "aqui vem a virada", "mas não para por aí", "não é só X, é Y". Também nada de travessão na fala nem de enchimento.

### Vídeo informativo ou documental (60 s a 15 min)
Ordem que funcionou nos vídeos estudados:
1. Abertura no contraste entre um detalhe minúsculo e um número enorme.
2. Descarte do esperado e revelação do método comum.
3. Loop aberto ("prender foi a parte fácil").
4. Promessa de três coisas numa frase (como foi, quem foi, o que ninguém respondeu).
5. Ideia plantada.
6. Contexto em ~30 s, só o que importa.
7. Preparação com datas.
8. O fato minuto a minuto (o relógio dita o ritmo).
9. O momento em que devia ter acabado e não acabou.
10. Por que ninguém impediu, com fonte.
11. Os erros.
12. A consequência.
13. A pergunta em aberto.
14. A ironia em uma linha.
15. Final com os três fragmentos.

Num vídeo longo, ponha um **cartão de capítulo** (2 a 3 palavras, como "O PLANO" ou "A CAÇADA") a cada 2–3 min, com uma pausa de ~2 s na voz enquanto o cartão está na tela.

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
