# Modelo Remotion — modo COMERCIAL

Copiado do comercial "A nota já foi?" (MinhaMarca, aprovado em 2026-11-04). Duas composições:

- **`ComercialIlustrado.tsx` — PADRÃO.** Ilustração 2D cinematográfica (imagens OpenAI) + clipes Kling (fal.ai) com `<Clipe>` +
  chat do WhatsApp desenhado sobre a **tela verde** de uma ilustração da mão segurando o celular (`<MaoNoCelular>`, posição da tela
  em `src/tela.json`, medida pela cor verde) + `LegendaHistoria` (caixa verde `#87C968`, letra pequena). Sem mascote.
- `Comercial.tsx` — versão vetorial antiga (motion graphics SVG); use só se o usuário pedir esse estilo.

Peças reaproveitáveis: `celular.tsx` (Celular com `altura` livre, Bolha, BolhaAudio, BolhaPdf, Digitando, teclado + digitação,
Notificacao, Documento com carimbo, Envelope, Etiqueta, CartaoFinanceiro, Mao), `base.tsx` (tempo, molas, Logo, TextoGrande, Selo,
Onda pela amplitude real da voz, legendas), `personagens.tsx` (vetores antigos).

Para um vídeo novo: copie a pasta, rode `npm install`, gere `src/falas.json` com `scripts/timeline_comercial.py`, meça a tela verde da
nova ilustração do celular (ver `ComercialIlustrado.tsx`) e reescreva as cenas.
