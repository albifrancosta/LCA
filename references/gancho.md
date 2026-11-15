# Etapa do gancho (0–3 s) — entre a entrevista e a amostra

O gancho decide se a pessoa fica. Ele é **três coisas juntas**: a **imagem do 1º quadro** (entendida sem som em 1 s), a **frase** falada e o **texto na tela**. Esta etapa gera opções, pontua e deixa o usuário escolher — e, se ele quiser, sai um 2º gancho para teste A/B.

## 1. Gere 6 ganchos, um por fórmula
Use a dor, o público e o gatilho de compartilhamento do briefing. Cada gancho: **imagem do 1º quadro** + **frase (≤ 3 s de fala)** + **texto na tela (≤ 6 palavras)**.

| Fórmula | Exemplo ("Cadê o técnico?") |
|---|---|
| **Horário + situação** (P05) | "10h40. As câmeras caíram às seis… e o técnico não chegou." · monitor SEM SINAL |
| **Pergunta ao espectador** | "Você sabe onde o seu técnico está agora?" · mapa com pino piscando |
| **Número chocante** (P02/P24) | "4 horas e 40 minutos com a portaria cega." · relógio + monitor apagado |
| **Resultado primeiro** | "O síndico recebeu a OS antes de você ligar." · WhatsApp com o PDF |
| **Contradição** | "O técnico mais rápido da equipe… é o que você nunca acha." |
| **POV / som** (P34/P36) | Celular vibrando em tela cheia, "TRIM!", nome do síndico na chamada |

## 2. Pontue cada um (0–3 por critério, total 12)
1. **Sem som em 1 s:** a imagem + texto explicam a situação sem ouvir nada?
2. **Curiosidade:** abre uma pergunta que só se responde assistindo?
3. **Dor do público / gatilho:** quem é do ramo pensa "isso sou eu" (P06)?
4. **Produção:** cabe no estilo, na referência e no orçamento (sem imagem nova cara)?

## 3. Mostre os 3 melhores (uma pergunta só)
Para cada um: fórmula, frase, texto na tela, descrição da imagem e a pontuação. Recomende o 1º.
Pergunte em seguida (outra mensagem, se o usuário prefere uma pergunta por vez): **"Quer um 2º gancho para teste A/B?"** → recomende o 2º colocado se ele usar fórmula diferente do 1º.

## 4. Amostra e A/B
- A amostra (Rodada 5 da entrevista) usa o gancho principal.
- Com A/B: renderize também os primeiros 3–7 s com o gancho B (composição com prop `variante: "B"`, como em `templates/remotion-comercial/src/Comercial.tsx`) e emende com o resto do vídeo A (`ffmpeg concat`, ver modo COMERCIAL). Custo: no máx. 1 imagem a mais.
- `scripts/kit_publicacao.py` inclui a versão B no kit e a ficha de métricas (`scripts/metricas.py`) compara retenção em 3 s das duas.

## 5. Registro
No `BRIEFING.md`: gancho escolhido (fórmula + frase + imagem + texto), pontuação e gancho B (se houver). No `historico.md`: fórmula usada — as métricas depois dizem qual fórmula funciona com este público.
