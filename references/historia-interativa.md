# Modo HISTÓRIA — template "história interativa em 2ª pessoa"

Engenharia reversa de `memoria/referencias/ref-2026-11-03-whatsapp.md` (suspense "O homem no armário", 156 s, viral).
Use quando o usuário quiser um vídeo **narrativo** (história, mistério, "imagina que…", dia a dia do cliente) que termine em **escolha A/B nos comentários**. Para anúncio direto de produto use o modo COMERCIAL.

## 1. A fórmula (o que faz reter)
1. **2ª pessoa desde a 1ª frase**: "Você está…", "Você tem…". Situação comum, sem título na tela.
2. **Laço aberto**: a cada 8–12 s (≈ 4–6 s num vídeo de 60 s) uma micro-revelação que levanta outra pergunta. Nunca responda antes da hora.
3. **Um aparelho vira testemunha**: celular, câmera, planilha, sistema — a descoberta grande vem por uma tela (POV).
4. **Escalada → corte para preto** antes do clímax.
5. **Escolha A/B** + "a mais votada decide o próximo episódio" (gera comentário e série).

## 2. Estrutura (proporções medidas — escale para a duração pedida)

| Bloco | % | em 60 s | em 90 s | Plano típico |
|---|---|---|---|---|
| Gancho em 2ª pessoa | 5% | 0–3 s | 0–5 s | `cadeia` de fora para dentro (lugar → janela → pessoa) |
| Rotina + 1ª anomalia | 10% | 3–9 s | 5–14 s | `cadeia` no ambiente + close de reação |
| Pistas (2–3) | 18% | 9–20 s | 14–30 s | `cadeia` em objetos (cada pista = um close) |
| Descoberta pelo aparelho | 30% | 20–38 s | 30–57 s | `pov` (celular) + `imagem` parada com ação (`camadas`) |
| Escalada | 25% | 38–53 s | 57–80 s | push-in rápido, `tremor`, close extremo → `preto` (`silencio_antes`) |
| Escolha A/B | 12% | 53–60 s | 80–90 s | `expressoes` (mesmo quadro, rosto muda a cada opção) + `cartao` |

## 3. Narração
- ~2,3–2,5 palavras/s (60 s ≈ 135–145 palavras). Frases curtas, presente do indicativo, detalhes concretos (hora, objeto, número).
- Voz padrão: Gemini `Charon`, "narrador grave e calmo, mistério crescente" (`montar_historia.py` já usa). Uma fala por plano.
- Termine com: "Opção A — … Ou opção B — …? Comente A ou B. A mais votada decide o próximo episódio."
- Produto (ex.: MinhaMarca) só entra como **uma das opções** ou como a virada — nunca vira propaganda no meio da história.
- **Variante "dor → solução" (padrão para a MinhaMarca — ver `perfil.md`)**: troque o bloco "Escolha A/B" por: virada "Agora imagina…" → solução mostrada (2–3 benefícios curtos) → mesma cena do início, agora resolvida → assinatura da marca + CTA. Cartão final com a marca e o CTA, sem "comente".

## 4. Visual
- **Estilo de imagem (prefixo fixo em `estilo`)**: "Ilustração 2D estilo cartoon plano, traço limpo, cores chapadas, iluminação cinematográfica noturna azul-marinho com pontos de luz quente, sem texto" — troque a luz conforme o clima.
- **Personagem consistente**: descreva uma vez em `personagem` (ex.: "homem de cabeça redonda careca, pele clara, moletom azul com faixa vermelha e branca no peito"). Gere primeiro um retrato e use em `personagem_ref` — todo prompt com a palavra "personagem" recebe a descrição e a referência.
- **Câmera** (medida): cadeia 4–16%/s (`zoom: [1, 1.3]` por imagem de 2–3 s); parado com ação `zoom: [1, 1.02]` + `camadas`; tensão `tremor: 3`.
- Plano com ação sem vídeo pago: imagem de fundo **sem** o elemento + PNG transparente do elemento (`gerar_imagem.py --fundo transparent`) em `camadas` com `x/y/escala` de início→fim (andar, aproximar, lanterna).
- Imagem pronta (print **fictício**, foto) no lugar de prompt: `"arquivos": ["caminho.png"]`. Nunca print com dados reais de cliente.
- **Clipe animado por IA (pago, fal.ai)**: só nos 3–5 momentos-chave. No plano, `"clipe": {"movimento": "he looks at the phone and frowns, camera slowly pushes in"}` (movimento em inglês, curto, uma ação). Depois de ter a imagem final do plano:
  `python SKILL_DIR/scripts/gerar_clipe_fal.py --roteiro roteiro.json` → mostra quantos clipes e o custo (Kling 2.5 Turbo Pro: US$ 0,35 por 5 s); com `--confirmar` gera em `assets/clips/<id>.mp4`. Rode `montar_historia.py` de novo: o plano passa a usar o clipe (sem som; desacelera até 0,6× para caber na frase e segura o último quadro). Chave: variável `FAL_KEY`.

## 5. Legenda e áudio (medidos)
- Caixa `#87C968` atrás só da palavra falada, texto branco negrito 2,6% da altura, centro em y = 68%, 4 palavras por grupo, pontuação mantida.
- Trilha **alta** (≈5 dB abaixo da voz, `--volume-trilha 0.45`), corta em `silencio_antes` (pausa dramática de 0,7 s), some nos 3 s finais com o cartão.
- `--trilha suspense` gera drone + pulso grátis; troque por trilha livre de direitos se tiver.

## 6. Passo a passo
```bash
# 1. escreva <projeto>/roteiro.json (exemplo: projetos/2026-11-03-exemplo/roteiro.json)
python SKILL_DIR/scripts/montar_historia.py <projeto>/roteiro.json --so-voz      # confere duração e ritmo
python SKILL_DIR/scripts/montar_historia.py <projeto>/roteiro.json                 # rascunho grátis (quadros com o prompt)
cd <projeto>/remotion && npm install && npx remotion render Historia out/rascunho.mp4 --scale=0.5   # aprovar ritmo
python SKILL_DIR/scripts/montar_historia.py <projeto>/roteiro.json --imagens gerar --qualidade medium   # custo: mostre antes (≈ nº de prompts)
npx remotion render Historia out/final.mp4
```
Regerar uma fala: apague `assets/voz/<id>.wav` e rode de novo. Regerar uma imagem: apague `assets/img/<id>-<n>.png`.

## 7. Checklist antes de entregar
- Gancho em 2ª pessoa no 1º segundo; nenhum título no quadro 1.
- Uma revelação nova a cada ≤ 6 s (60 s) / ≤ 10 s (2 min).
- O mesmo personagem em todas as imagens (olhe uma a uma).
- Pausa dramática antes da virada; cartão final preto "DEIXE NOS COMENTÁRIOS. VOCÊ DECIDE!".
- Sem dados reais em telas; sem marca de terceiros.
