# Modo COMERCIAL — peça de venda com timeline fixa

Use quando o usuário pede um **comercial** (anúncio de produto com duração e cenas definidas), a partir de ideia, briefing, código do produto ou vídeo de referência. Diferente do modo CRIAR: aqui a **timeline manda** (cenas com segundos fixos) e a voz é encaixada nela, não o contrário.

Papel: estrategista comercial + roteirista + diretor de motion + editor. PT-BR.

## 0. Ferramentas antes de tudo
Verifique e diga o que há: `ffmpeg/ffprobe`, `node`, faster-whisper (`python -c "import faster_whisper"`), `GEMINI_API_KEY`, `OPENAI_API_KEY`, Playwright/navegador. Faltou algo → use o fallback e diga exatamente o que foi produzido e o que não foi.

## 1. Produto e campanha
- **Com código:** leia instruções do projeto, mapeie módulos, rastreie o fluxo UI → API → regra → persistência. Build/artefato: REA (`mcp__rea__*`). Registre evidência e lacuna por funcionalidade.
- **Com briefing:** público, dor, benefício, recursos, oferta, CTA — marque o que é *briefing*, *demonstrado* e *hipótese*.
- Feche: 1 dor concreta, 1 ganho que dá para **mostrar**, 1 ação final.
- Classifique cada recurso citado: **confirmado**, **depende de configuração**, **ilustrativo**. Recurso não validado no produto → cena com selo "Simulação do fluxo" e nada de afirmar na narração que já funciona.

## 2. Referência
`scripts/analisar_referencia.py` (ffprobe + cortes + quadros + transcrição). Entregue tabela `tempo · ação · enquadramento · texto · áudio · função`. Amostragem → tempos "≈". Adapte a estrutura; personagens, falas e imagens são próprios.

## 3. Roteiro e timeline
- 3 ganchos → escolha 1. Os primeiros segundos mostram a situação/problema.
- Arco: gancho → problema → ação → resultado → CTA.
- Por cena: início–fim, fala exata (quem fala), enquadramento, movimento, texto na tela, áudio.
- Separe **narração**, **falas de personagem**, **legendas** e **textos de interface**. Frases curtas; área segura de Reels/Shorts/TikTok (topo 12%, base 20% livres para a UI da plataforma).
- Locução aprovada pelo usuário → confira se cabe e reaproveite os trechos por cena.

## 4. Voz e visuais
- **Voz:** `scripts/tts_gemini.py` (Gemini `gemini-3.8-flash-tts`, `GEMINI_API_KEY`). Uma fala por arquivo, para encaixar cada uma no seu segundo. Texto falado separado da direção (`--estilo`). Confira duração com ffprobe.
  - Narrador: PT-BR, comercial animado, dicção clara. Personagem: **outra voz**.
  - Pronúncia: escreva **"Minha Marca"** no texto falado e **"MinhaMarca"** nas legendas (`tts_gemini.py` troca sozinho).
- **Ilustração:** personagens, mascote e cenários consistentes, **em camadas** quando precisam se mexer separados. Padrão sem custo: vetores SVG desenhados como componentes Remotion (ver `templates/remotion-comercial/`). Imagem por IA (`gerar_imagem.py`) só quando o desenho vetorial não basta. Texto e ícones sempre na edição, nunca dentro da imagem.
- **Animação:** Remotion (padrão, gratuito). Higgsfield/After Effects só se o usuário pedir e houver. Todo movimento tem função: **aproximar para revelar**, **deslocar para causa→efeito**, **pausar para ler**.
- **Captura real** (só se autorizado): um script de captura de tela do seu sistema grava rotas do ERP — desktop 1920×1080, zoom 150%. Sem acesso → captura do usuário ou interface ilustrativa.

## 4b. Pipeline (testado no comercial "A nota já foi?", 2026-11-03)
```bash
# 1. falas.json: [{id, quem: narrador|tecnico, inicio, voz, estilo, texto, legenda?}]
python SKILL_DIR/scripts/tts_gemini.py falas.json -o assets/voz        # confere vazamento da direção sozinho
# 2. timeline: tempo de cada palavra (legenda "MinhaMarca") + amplitude por quadro (onda e boca)
python SKILL_DIR/scripts/timeline_comercial.py falas.json --voz assets/voz -o remotion/src/falas.json
# 3. Remotion: copie templates/remotion-comercial/ para <projeto>/remotion, npm install, escreva as cenas em src/Comercial.tsx
npx tsc --noEmit && npx remotion render Comercial out/previa.mp4 --muted --scale=0.5   # revisar folha de quadros
npx remotion render Comercial out/animacao.mp4 --muted --crf=18
# 4. voz + efeitos + trilha
python SKILL_DIR/scripts/mixar_comercial.py --video remotion/out/animacao.mp4 --falas falas.json --voz assets/voz --sfx sfx.json --trilha sintetica --duracao 60 -o entrega/<nome>.mp4
```
- **Tom de voz** (desde 2026-11-04, formato oficial do Gemini 3.8 TTS: `speech_metadata.style` na Interactions API — a direção não é lida em voz alta): cada fala recebe `"tom"` do catálogo (`python tts_gemini.py --tons`): comercial, institucional, conversa, alegria, alivio, duvida, surpresa, suspense, medo, raiva, urgencia, tristeza, ironia — ou `"auto"` (o Gemini escolhe pelo texto + `--contexto`). **Comercial da MinhaMarca: narrador = `comercial`, personagem = `conversa`.** Momentos pontuais no texto, em inglês: `<short pause>`, `<long pause>`, `<sigh>`, `<laugh>`, `<breath>`, `<gasp>`; palavra em MAIÚSCULAS = ênfase.
- Cota: `gemini-3.8-flash-tts` tem 100 gerações/dia no Tier 1; ao esgotar, o script usa `gemini-3.8-flash-lite-tts` (cota separada, qualidade um pouco menor).
- Componentes prontos no modelo: `Tecnico` (braços em 2 segmentos, boca pela amplitude, caminhada), `Mascote` MinhaMarca, `CaixaFerramentas`, `LocalAtendimento`, `Van`, `Celular` (gravando com onda real), `Bolha`, `BolhaAudio`, `Digitando`, `Notificacao`, `Documento` (carimbo), `Envelope`, `Etiqueta`, `CartaoFinanceiro`, `Selo`, `TextoGrande`, `Legenda` (tag TÉCNICO nas falas de personagem).
- Abertura A/B: prop `variante` na composição; renderize só os 7 s da B e emende com a A (`ffmpeg concat`) antes de mixar.

## 5. Edição, validação e entrega
1. Renderize a animação **sem áudio de voz** primeiro; depois some voz + efeitos com ffmpeg (`scripts/mixar_comercial.py`): cada fala no seu `inicio`, loudnorm −14 LUFS.
2. Fala longa demais para a cena → encurte o texto ou regenere; nunca acelere a voz além de 1,1×.
3. Exporte **MP4 H.264 + AAC, 1080×1920**, duração pedida; confira com ffprobe.
4. Revise **com e sem som**: legibilidade no celular (quadros em escala 0,5), sincronia, cortes, pronúncia (transcreva o mix e procure "MinhaMarca/Minha Marca"), nenhum dado real. Onda sonora acompanha a fala do personagem (use a amplitude real do WAV).
5. Entregue: **MP4**, **roteiro com minutagem**, **legenda de publicação**, **abertura alternativa para teste A/B**. Etapa pendente → diga qual, exatamente.
