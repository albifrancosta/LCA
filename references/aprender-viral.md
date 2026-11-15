# Modo APRENDER — estudar um vídeo viral e guardar na memória

Objetivo: entender **como** o vídeo foi feito (técnica e estrutura) e transformar em padrões reutilizáveis. Não copiar o conteúdo.

## 1. Obter o vídeo

- Link (TikTok, Instagram, YouTube, X): o script baixa com `yt-dlp`.
- Arquivo local: passe o caminho.
- Download falhou (login, privado): peça ao usuário para salvar o vídeo e mandar o arquivo.

## 2. Medir (automático)

```bash
python "SKILL_DIR/scripts/analisar_referencia.py" "<link-ou-arquivo>" --slug <nome-curto>
```

Cria `%USERPROFILE%\estudio-video\referencias\<slug>\` com:
- `video.mp4`, `audio.wav` (16 kHz mono)
- `analise.json` — duração, resolução, fps, cortes, plano médio, cortes nos 3 primeiros segundos, trocas por segundo, volume, silêncios
- `frames/` — a cada 0,5 s nos primeiros 3 s + 1 frame no meio de cada plano
- `folha-gancho.jpg` (primeiros 3 s em grade) e `folha-planos.jpg` (1 frame por plano, até 24)

Depois transcreva (dentro da pasta da referência):
```bash
npx hyperframes transcribe audio.wav --model small --language pt --json
```
Outro idioma: troque `--language`; fala sobre música alta: `--model medium`. Leia o JSON que ele devolve para achar o caminho do transcript e copie para a pasta da referência como `transcript.json`.

## 3. Assistir (você, com os olhos)

Abra com Read `folha-gancho.jpg`, `folha-planos.jpg` e alguns frames. Responda:

- **Gancho (0–3 s)** — o que tem no frame 1? Texto na tela? Qual fórmula (dor, número, contradição, resultado primeiro…)? Quantos cortes até 3 s?
- **Ritmo** — trocas por segundo; acelera ou desacelera? Plano mais longo e por quê?
- **Legenda** — palavra a palavra ou frase? Palavras por grupo, posição, fonte, cor, destaque, emoji?
- **Movimento** — transições (corte seco, zoom-through, whip, máscara), punch-ins, elementos entrando/saindo.
- **Visual** — paleta, fundo, motion graphics vs. filmagem vs. tela gravada, densidade de texto.
- **Áudio** — palavras/s (palavras do transcript ÷ tempo falado), trilha, SFX, onde está o "drop".
- **Estrutura** — blocos (gancho / problema / virada / prova / CTA) com tempos.
- **CTA** — qual, quando, como aparece.
- **Por que viralizou (hipótese)** — 1–3 motivos concretos.

## 4. Guardar a ficha

Escreva `SKILL_DIR/memoria/referencias/<slug>.md`:

```markdown
# <slug>
Fonte: <link ou arquivo> | Plataforma: … | Analisado em: AAAA-MM-DD
Formato: 1080x1920 · 30 fps · 27,4 s · Nicho: …
Métricas públicas (se informadas): …

## Números
cortes: 18 · plano médio: 1,5 s · cortes em 0–3 s: 3 · fala: 2,9 palavras/s

## Gancho
## Estrutura (tempos)
## Legenda
## Movimento
## Visual
## Áudio
## CTA
## Hipótese do porquê funcionou
## Padrões extraídos
- P0X (novo | reforçado): …
```

Acrescente uma linha em `memoria/referencias/INDEX.md`.

## 5. Atualizar padrões (o aprendizado)

Para cada técnica observada, em `memoria/padroes.md`:
- Já existe padrão igual → refs +1 e cite o slug.
- Não existe → crie `Pnn` na seção certa, status **Teste**, refs = 1.
- refs ≥ 3 ou pontuação ≥ +3 → **Confirmado**.
- Contradiz uma preferência fixa do `perfil.md` → registre, mas não aplique.

## 6. Responder ao usuário

Curto: 3–5 bullets do que esse vídeo faz de especial, quais padrões foram guardados e "no próximo vídeo vou aplicar X e Y". Se ele também pediu um vídeo, siga para o Fluxo CRIAR com a ficha aberta.
