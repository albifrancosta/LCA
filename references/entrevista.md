# Etapa 0 — Entrevista (antes de qualquer roteiro)

Método: skill **grilling** (instalada em `~/.claude/skills/grilling`, de mattpocock/skills, MIT). Resumo do método aplicado a vídeo:

- A entrevista é uma **árvore de decisões**. Pergunte em **rodadas**: em cada rodada, faça **todas** as perguntas cujos pré-requisitos já estão decididos (a "fronteira"), numeradas, cada uma com a **sua resposta recomendada**. Escreva a pergunta de modo que "sim" aceite a recomendação.
- Pergunta que depende de outra ainda aberta vai para a **rodada seguinte**.
- **Fatos são trabalho seu, decisões são do usuário.** O que dá para descobrir sozinho (código do sistema, prints, vídeos anteriores, `memoria/perfil.md`, `memoria/historico.md`) você busca — com um sub-agente, sem travar as outras perguntas. Nunca pergunte o que já está no perfil: use como recomendação.
- **Com este usuário: UMA pergunta por mensagem** (pedido dele, 2026-11-04). Siga a ordem da árvore abaixo, sempre com a sua recomendação e opções curtas; espere a resposta antes da próxima. Pule as que o perfil ou respostas anteriores já decidiram.
- Termina quando todos os ramos foram visitados e o usuário **confirma** o entendimento. Só então escreva o `BRIEFING.md` e passe ao ponto de conferência 1 (storyboard do roteiro).

Formato de cada rodada (em português):

```
❓ **P1** — **<título>**: <pergunta, com as opções>

➡️ <sua recomendação>

---
```

## Cardápio de formas de edição — 💰 pago × 🆓 grátis (pedido do usuário, 2026-11-05)

Toda pergunta de ferramenta mostra a etiqueta **💰 pago (com valor)** ou **🆓 grátis** em cada opção. Antes da Rodada 4, some o que foi escolhido e mostre o **total estimado** ("Seu vídeo: US$ 0,62 — trilha ElevenLabs 0,58 + 1 imagem 0,04; o resto é grátis").

| Camada | Opções | Custo |
|---|---|---|
| Visual base (P12) | A ilustração + clipes Kling · B ilustração com zoom · C motion graphics · D Lemo-Opuscar · E gravação de tela · **F híbrido** (ilustração na dor + motion na solução) · **G explicativo em passos** (cartão + trilha de etapas) · **H tipografia cinética** | A 💰 ~US$ 2–3 · B 💰 ~US$ 0,50–1 · F 💰 só as imagens/clipes da dor (ou 🆓 reaproveitando) · C, D, E, G, H 🆓 |
| Camadas de motion (P17b) | texto cinético, contador, gráfico, mapa com rota, linha do tempo, notificação, carimbo, balões | 🆓 (`templates/remotion-motion/`) |
| Voz (P16) | Gemini TTS com tom · VoiceStudio (voz clonada) | 🆓 (cota diária do Gemini) |
| Trilha (P16b) | IA ElevenLabs · IA ACE-Step · sintetizada · arquivo próprio · nenhuma | ElevenLabs 💰 US$ 0,60/min · ACE 💰 ~US$ 0,01/min · resto 🆓 |
| Efeitos sonoros (P16c) | som profissional (regras + riser/golpe) · simples · nenhum | 🆓 |
| Batida (P16c) | trocas de cena e revelação no tempo da música | 🆓 |
| Acabamento (P18b) | motion blur no render final | 🆓 (render ~2× mais lento) |
| Densidade dos cortes (P18e) | enxuto · padrão · detalhado | 🆓 em motion · 💰 mais imagens quando ilustrado (US$ 0,05 cada) |
| Ficha / grade 3×3 (P18f) | ficha do personagem em várias vistas · 9 ângulos do mesmo momento numa imagem | 💰 ~US$ 0,05 cada (grade = 9 ângulos pelo preço de 1) |
| Motion control (P18d) | trocar o personagem de um vídeo seu · copiar o seu movimento para um personagem | 💰 US$ 0,07–0,112 por segundo (5 s ≈ US$ 0,35–0,56) — tabela com `motion_control.py --custos` |

## Árvore de decisões de um vídeo

### Rodada 1 — sem pré-requisitos
1. **Objetivo**: o que a pessoa deve fazer depois de assistir? (pedir demonstração, comentar, visitar o site, conhecer um recurso novo…)
2. **Público**: quem é exatamente? (dono de empresa de manutenção, condomínio, varejo, contador…)
3. **Formato do vídeo**: comercial direto (modo COMERCIAL, ex.: "A nota já foi?") · história em 2ª pessoa (modo HISTÓRIA, ex.: "Sexta-feira, 18h") · tutorial/demonstração · outro. → recomendação conforme o objetivo.
4. **Plataforma, proporção e quantos segundos**: Reels/TikTok/Shorts 9:16 · YouTube/site 16:9; **15, 30, 45, 60 ou 90 s** (pergunte o número exato). → padrão do perfil: 9:16, 60 s.
5. **Fonte do conteúdo — ler o código do sistema?** "Quer que eu leia a pasta do projeto do sistema para tirar o conteúdo direto do código (quais telas, recursos e fluxos existem de verdade)?" Se sim: **qual pasta** (ou eu procuro). Leitura feita por um sub-agente: código-fonte com leitura direta (Glob/Grep/Read); build, bundle web ou app instalado com o **REA** (`mcp__rea__*`, ex.: `analyze_web_bundle`, `analyze_javascript_application`, `inspect_web_page`). Resultado: lista de recursos com status **confirmado no código / depende de configuração / não encontrado** — vira a base do roteiro e decide onde vai o selo "Simulação do fluxo". → recomendação: sim, quando o vídeo mostra um recurso do produto.
6. **Referência**: tem um vídeo que gostou e quer seguir o estilo? (arquivo ou link → modo APRENDER antes) · usar as fichas que já existem em `memoria/referencias/`?
7. **Orçamento máximo de geração**: imagens (OpenAI) + clipes (fal.ai). → recomendação: até US$ 3 por vídeo de 60 s; mostrar o valor exato no ponto 2.

### Rodada 2 — depende de objetivo, público e formato
8. **Dor concreta**: qual situação real do dia a dia o vídeo mostra? (2–3 opções escritas como cena: "o serviço acabou, o cliente pediu a nota e você ainda tá na rua")
8b. **Por que alguém mandaria este vídeo para outra pessoa?** (gatilho de compartilhamento — padrão P06): (a) **identificação**: "isso sou eu / acontece toda semana aqui" · (b) **marcar alguém**: o sócio, o técnico, o colega do ramo · (c) **utilidade**: salvar para mostrar depois · (d) **humor/indignação**. → recomendação: (a) para história de dor; a cena da dor tem que ser reconhecível por quem é do ramo (detalhes reais: nomes de equipamento, horários, frases que o cliente fala).
9. **Recurso / solução mostrada**: qual parte do produto resolve essa dor? (se a leitura do código rodou, ofereça só recursos **confirmados**; os não confirmados entram como simulação ou ficam de fora)
10. **Personagem**: quem vive a cena? (técnico, dono, síndica, vendedor…) Aparência, roupa, idade aproximada — vai virar a ficha do personagem.
11. **Ambiente e luz**: onde acontece e a que hora (laje ao pôr do sol, loja à noite, escritório de manhã…).
12. **Tipo de animação = TÉCNICA + ESTILO VISUAL** (2026-11-06) — pergunte em duas partes, uma por mensagem:
    - **12a. Estilo visual** — mostre a tabela de `python scripts/estilos.py listar --genero <gênero do vídeo>` (⭐ = combina com o gênero). São 21 estilos: ilustração 2D cinematográfica (padrão do estúdio), cartoon 3D cinematográfico, cartoon 2D sitcom, cartoon 2D moderno, anime, anime romântico, chibi, aquarela/fantasia 2D, caricatural, comic/cel shading, rubber hose (anos 30), massinha, papel recortado, pixel art, low poly, pintura artística, motion flat, rotoscopia e **live-action** (filme com pessoas reais/fotorrealista, celular/UGC, documentário). Recomende 3 pelo gênero.
    - **12b. Comparar antes de decidir?** — `estilos.py comparar --personagem "…" --cena "<cena do gancho>" --estilos a,b,c,d,e,f` gera o MESMO personagem na MESMA cena em até 8 estilos + folha comparativa (low ≈ US$ 0,012 por estilo; 6 ≈ US$ 0,07). Mande a folha pelo chat; o escolhido vai para a bíblia com `estilos.py aplicar <id>` e todo prompt passa a usar o prefixo dele. → recomendação: comparar sempre que o vídeo for longo ou série.
    - **12c. Como animar** (decorre do estilo; mostre o custo): 
    - **A. Ilustração 2D cinematográfica + clipes Kling** — padrão aprovado; imagens OpenAI (~US$ 0,05 cada) + 3–5 clipes fal.ai (US$ 0,35 cada); ≈ US$ 2–3 por 60 s.
    - **B. Ilustração com zoom e camadas, sem clipes** — mesmo visual, movimento só de câmera (Ken Burns, parallax); ≈ US$ 0,50–1.
    - **C. Motion graphics vetorial** (personagens e telas desenhados em código, Remotion) — grátis; visual chapado (estilo da v1 do "A nota já foi?").
    - **D. Estilo artístico Lemo-Opuscar** (óleo, aquarela, ukiyo-e, satélite, produto explodido…) — filme feito em código pela skill `/lemo-opuscar`; grátis, mais lento; bom para vídeo de marca/institucional.
    - **E. Gravação real da tela do sistema** (`capturar-video.mjs`, conta de demonstração) — 🆓; só com autorização e dados fictícios.
    - **F. Híbrido** — ilustração + clipes com camadas gráficas na dor, motion graphics puro na solução e na assinatura (referência: `CadeHibrido.tsx`, aprovado 2026-11-05) — 💰 só as imagens/clipes da parte da dor (~US$ 1–1,50) ou 🆓 reaproveitando ilustrações.
    - **G. Explicativo em passos** — uma ilustração-âncora fixa, cartão com número grande que vira a cada passo, trilha de etapas com ✓ (bom para tutorial: "NFS-e em 3 passos") — 🆓, feito em código.
    - **H. Tipografia cinética** — palavras grandes entrando no ritmo da fala, cortes laterais, carimbos (bom para gancho e vídeo curto de 15–20 s) — 🆓.
    - **Live-action**: quase toda tomada precisa de clipe (pessoa parada denuncia IA) → mais caro (~US$ 0,27–0,49 por 5 s); só pessoas fictícias ou com autorização por escrito, nunca rosto de alguém real/celebridade sem consentimento.
    → recomendação: F para anúncio de dor → solução (o usuário gosta de motion graphics); A se a história pedir muita ação física; G para tutorial; B/C/H se o orçamento for zero; D se pedirem algo artístico.
13. **CTA final**: padrão da MinhaMarca = "MinhaMarca. Menos operação. Mais estratégia." + "Peça uma demonstração". Mudar?

### Rodada 3 — depende da dor, da solução e do personagem
14. **Gancho (0–3 s)** — siga a **Etapa do gancho** (`references/gancho.md`): gere 6 ganchos com fórmulas diferentes, pontue nos 4 critérios, mostre os 3 melhores (frase + imagem do 1º quadro + texto na tela) → o usuário escolhe o principal e, se quiser, um 2º para teste A/B.
15. **Tom de voz por bloco**: narração (padrão `comercial` em anúncio da MinhaMarca), falas de personagem (`conversa`), momentos de tensão (`duvida`, `urgencia`, `raiva`, `medo`, `suspense`…). Use `tts_gemini.py --tons` para listar e `--tom auto` para sugerir. **Padrão desde 2026-11-05: `diretor_voz.py`** — pergunte o **gênero** (comercial, humor, romance, suspense, drama, institucional, tutorial); ele planeja emoção + intensidade + ritmo + pausas por fala, gera, ouve e refaz o que não bateu. Mostre a tabela do plano no storyboard do ponto 1 e o `relatorio-voz.md` no ponto 3.
16. **Ferramenta de voz**:
    - **Google Gemini TTS** (`tts_gemini.py`) — rápido, 30 vozes, **controle de tom por fala** (comercial, medo, dúvida…), pausas e suspiros no texto; cota de 100 falas/dia no Tier 1 (reserva Lite). Vozes: narradora/narrador (Zephyr, Kore, Charon…), personagem (Puck, Fenrir…).
    - **VoiceStudio — voz clonada do usuário** (local, `http://localhost:3900`, perfil da sua voz clonada) — grátis e com a voz dele, mas lento (~3 min por 30 s de fala, na CPU) e sem controle de tom; o app precisa estar aberto (confira com `curl http://localhost:3900` antes de oferecer).
    - Misturar: narração com a voz clonada e personagens no Gemini, ou o contrário.
    → recomendação: Gemini com tom `comercial` na narração; VoiceStudio se ele quiser a própria voz assinando o vídeo.
16b. **Trilha sonora de fundo**:
    - **IA conforme o conteúdo** (`scripts/trilha_ia.py`) — o Gemini lê as falas e divide a música em blocos de clima (dor → virada → solução → assinatura), com a troca caindo no corte; sempre instrumental. ElevenLabs Music (≈ US$ 0,60/min, troca no tempo exato) ou ACE-Step (≈ US$ 0,01/min, para testar ou gerar 2–3 opções).
    - **Sintetizada grátis com clima por bloco** (`scripts/trilha_gratis.py`) — 🆓, segue o plano dor/curioso → respiro → revelação → final, revelação sempre na batida (testada no vídeo do espelho, 2026-11-05).
    - **Sintetizada simples** (`mixar_comercial.py --trilha sintetica`) — 🆓, um clima só.
    - **Arquivo do usuário** (música própria ou de biblioteca livre, com licença).
    - **Sem trilha** (só voz e efeitos).
    → recomendação: IA conforme o conteúdo, ElevenLabs no vídeo final; a trilha entra já na amostra (Rodada 5). Lembrete: música "em alta" do Instagram/TikTok não vai no arquivo (direitos) — o kit sugere adicionar no app, baixinho.
16c. **Efeitos sonoros e batida** (🆓):
    - **Som profissional** (`scripts/som_pro.py`) — poucos sons e certeiros (cada som tem uma causa na tela; a maior parte do movimento fica sem som; ≤ 10 sons a cada 10 s), **riser + golpe na revelação** com a música descendo antes, relatório do que foi cortado e por quê.
    - **Simples** — todos os efeitos marcados, sem filtro (como antes de 2026-11-05).
    - **Nenhum** — só voz e trilha.
    - **Batida** (`scripts/batida.py`): revelação no drop e trocas de cena no início do compasso — funciona melhor com trilha de uma peça só (ElevenLabs, arquivo próprio); com ACE em blocos só a revelação é conferida.
    → recomendação: som profissional + batida; pergunte **qual é o momento da revelação** (ex.: "com a MinhaMarca").
17. **Interfaces na tela**: o que precisa aparecer legível (chat do WhatsApp, tela do ERP, nota, cartão financeiro)? Sempre com dados fictícios.
17b. **Camadas de motion** (🆓, `templates/remotion-motion/`): quais destas entram e em que fala? texto cinético · contador (horas, R$, %) · gráfico de barras/linha · mapa com rota (ex.: técnico a caminho) · linha do tempo de status · notificação de celular · carimbo · balões de pensamento. → recomendação: 1 camada a cada 2–4 s nos trechos sem clipe; números da dor em contador (P24).
18. **Momentos animados por IA**: quais 3–5 tomadas merecem clipe (ação física, reação)? O resto fica em imagem com zoom ou motion. O **roteador** (`roteador.py`) escolhe o modelo de cada clipe pelo menor custo por cena aprovada (catálogo oficial do fal: ~US$ 0,10–0,49 por 5 s); interface/texto/gráfico vai sempre para motion grátis.
18d. **Motion control — usar um vídeo seu para dirigir o personagem?** (só pergunte se a história tem gesto/ação de personagem). **Antes de perguntar, rode `python scripts/motion_control.py --custos --video <vídeo dele> --duracao <s>`** (ou, sem vídeo ainda, a tabela por 5 s abaixo) e **mande os custos junto com a pergunta**:
    - (a) **Não** — clipes por imagem→vídeo como sempre (roteador) ou motion graphics. 🆓 / preço do clipe
    - (b) **Trocar o personagem** do seu vídeo pelo da biblioteca (você grava atendendo o telefone, vira o "dono"): Wan 2.2 Animate Replace — 💰 US$ 0,08/s (5 s ≈ US$ 0,40)
    - (c) **Copiar o seu movimento** para o personagem/cenário de uma imagem (ex.: o robô MinhaMarca faz o seu gesto): Kling 2.6 Motion Control Standard 💰 US$ 0,07/s (5 s ≈ US$ 0,35) · Wan Animate Move US$ 0,08/s · Kling Pro US$ 0,112/s (5 s ≈ US$ 0,56)
    → recomendação: (a) por padrão; (b)/(c) quando o gesto precisa ser exato ou o clipe por imagem errou. Regras: vídeo dele (ou com autorização de quem aparece), 1 pessoa, corpo visível, 3–10 s. Preços do catálogo oficial (confira a data em `catalogo.py --listar motion`).
18c. **Perfil de custo dos clipes**: (a) **econômico** — o mais barato que costuma ser aprovado (padrão) · (b) **equilibrado** — sobe a qualidade em cenas de personagem · (c) **premium** — a melhor qualidade dentro do orçamento. E **teste A/B** numa cena estratégica? (gera a mesma cena em 2 modelos econômicos com orçamento próprio, ~US$ 0,30–0,60; o vencedor ensina o roteador). → recomendação: econômico; A/B só no primeiro vídeo de um tipo de cena novo.
18b. **Acabamento — motion blur** (🆓): movimento mais suave no render final, com render ~2× mais lento. → recomendação: sim no vídeo final, não nas prévias.
18e. **Densidade dos cortes do storyboard**: (a) **enxuto** — ~65% dos cortes, planos mais longos com motion por cima (menos imagens = mais barato) · (b) **padrão** — 1 corte a cada 2–3 s · (c) **detalhado** — ~140% dos cortes, corte a cada 1,5–2 s (mais ritmo, mais imagens). Mostre quantas imagens cada um pede e o custo (ex.: "enxuto 6 imagens US$ 0,30 · padrão 9 US$ 0,45 · detalhado 13 US$ 0,65; com grade 3×3 o detalhado cai para ~US$ 0,25"). → recomendação: padrão para anúncio de 30–60 s; detalhado no gancho e na virada; enxuto em vídeo 100% motion.
18f. **Ângulos com grade 3×3** (💰 ~US$ 0,05 por grade de 9 ângulos): para cenas em que o mesmo momento aparece em vários cortes (reação, conversa). → recomendação: sim quando a densidade for detalhada ou houver 3+ cortes no mesmo cenário.

### Rodada 4 — fechamento
19. **Estrutura com tempos**: mostre a linha do tempo (blocos e segundos) e, junto, o **total estimado** das escolhas pagas do cardápio (o resto marcado 🆓); pergunte se aprova.
20. **Pontos de atenção**: recursos marcados como simulação, nomes e números fictícios, trilha (sintetizada ou arquivo do usuário).

### Rodada 5 — amostra para aprovação (depois de todas as respostas)
Antes de produzir o vídeo inteiro, faça uma **amostra de 5–8 s do gancho** com as escolhas da entrevista e **envie pelo chat (SendUserFile)** para aprovar:
- 1 imagem da cena do gancho (no estilo escolhido; tipo C/D/E: um quadro feito na própria ferramenta) + o personagem.
- A 1ª fala com a **ferramenta de voz e o tom escolhidos** (Gemini: `tts_gemini.py --tom ...`; VoiceStudio: gere o WAV e salve em `amostra/assets/voz/<id>.wav` — o `montar_historia.py` reaproveita o arquivo e não chama o Gemini).
- A legenda no estilo do vídeo e o movimento do tipo escolhido (tipo A: **1 clipe Kling**; B: zoom; C/D: animação em código).
- Monte com `scripts/montar_historia.py` num `amostra/roteiro.json` de 1–2 planos (gancho + cartão) e renderize; mostre o custo antes (tipo A ≈ US$ 0,40; B ≈ US$ 0,05; C/D/E grátis).
Só depois do "aprovado" na amostra o briefing vale e começa o vídeo completo. Mudanças pedidas na amostra voltam para as respostas da entrevista.

## Saída: `<projeto>/BRIEFING.md`

```markdown
# Briefing — <título> (<data>)
Objetivo · Público · Formato (modo, proporção, duração) · Orçamento
Fonte de conteúdo: <código lido? pasta? recursos confirmados / simulados>
Dor · Solução · Personagem (ficha) · Ambiente · Estilo visual
Gancho escolhido · Tipo de animação (A–E) · Ferramenta de voz (Gemini/VoiceStudio) · Tons por bloco · Vozes · Interfaces · Tomadas animadas · Duração em segundos
Amostra aprovada: <caminho do MP4 da amostra>
Linha do tempo aprovada
Decisões que mudaram o perfil (levar para memoria/perfil.md)
```

Depois do briefing: roteiro + falas com tom → **ponto de conferência 1** (storyboard sem custo).
