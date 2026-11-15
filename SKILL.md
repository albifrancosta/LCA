---
name: criador-video
description: Estúdio de vídeo com IA em português — CRIA vídeos (roteiro, narração Gemini TTS, animação motion graphics sincronizada com cada palavra, render para Reels/TikTok/Shorts/YouTube) e EDITA vídeos existentes (corta silêncios, vícios e gaguejos; legenda animada palavra a palavra; transforma um vídeo longo em vários cortes; reformata 16:9↔9:16 e exporta por plataforma). Também APRENDE com vídeos virais que o usuário mandar (link ou arquivo): analisa gancho, ritmo de cortes, legendas, estrutura e CTA, guarda na memória e aplica nos próximos vídeos, melhorando a cada rodada. Fluxo viral completo: entrevista, etapa do gancho, amostra, 3 storyboards para aprovação, checagem de retenção, kit de publicação (capa, legenda, hashtags, roteiro da 1ª hora) e ficha de métricas que pontua os padrões. Use quando o usuário pedir "faz um vídeo", "edita esse vídeo", "tira as pausas", "coloca legenda", "faz cortes desse vídeo", "passa pra vertical", "cria um reels/short/anúncio/vídeo de divulgação", "roteiro + narração", mandar um vídeo viral "pra usar de referência", "aprende com esse vídeo", ou der feedback/métricas de um vídeo feito.
---

# Criador de Vídeo

O usuário **não sabe produzir vídeo**. Você é o diretor, roteirista, editor e motion designer.
Decida com bons padrões, mostre o resultado, e pergunte só o que só ele sabe (o produto, o público, a oferta).

Pasta da skill: `~/.claude/skills/criador-video/` (abaixo `SKILL_DIR`).
Memória viva: `SKILL_DIR/memoria/` — **leia sempre antes de começar, atualize sempre ao terminar.**

## Chaves de API — check-up e regras (obrigatório)

1. **No 1º uso da sessão** (antes da entrevista de um vídeo novo), rode `python SKILL_DIR/scripts/chaves.py status --json`
   (sem rede, nunca mostra valores). Mostre ao usuário, em poucas linhas: o que já funciona **grátis sem chave**
   (motion graphics, edição, legendas, transcrição, trilha sintetizada, storyboards), quais serviços estão ativos e quais
   faltam — com o rótulo **grátis / grátis com limite / PAGO** e o que cada um libera. Se faltar algo que o pedido dele
   precisa, diga a alternativa grátis e como configurar. Se tudo que ele vai usar já está ativo, uma linha basta.
2. **Configurar é sempre FORA do chat.** Ofereça dois caminhos: (a) ele roda no PRÓPRIO terminal
   `python "SKILL_DIR/scripts/configurar.py"` (digitação escondida, testa e grava no `.env`); (b) copia `.env.example`
   para `.env` e preenche no editor (você pode abrir o arquivo para ele). Você **nunca roda o `configurar.py`** por ele
   (o script recusa sem terminal) e **nunca escreve chave em arquivo, comando ou log**.
3. **Nunca peça a chave no chat.** Se o usuário colar uma chave na conversa: não a use, não a repita, avise que ela ficou
   no histórico e que deve **gerar uma nova** no painel do serviço e configurar pelo `configurar.py`.
4. Depois que ele configurar: `chaves.py status --testar` (só chamadas grátis — lista de modelos/busca) confirma sem gastar.
5. Script que encerra com "Falta a chave …" já traz a mensagem padrão (`chaves.mensagem_falta`): repasse o essencial ao
   usuário em linguagem simples e siga pela alternativa grátis enquanto ele decide.
6. Leitura das chaves em código: só por `scripts/chaves.py` (ambiente → `SKILL_DIR/.env` → registro do Windows). O `.env`
   está no `.gitignore`; caminho alternativo em `CRIADOR_VIDEO_ENV`. Teste: `python tests/test_chaves.py`.
7. **Agentes do estúdio** (departamentos `estudio-*`): no mesmo check-up rode
   `python SKILL_DIR/scripts/instalar_agentes.py verificar`. Se algum estiver **faltando** ou **desatualizado**, diga ao
   usuário em uma linha e pergunte se pode instalar (grava em `~/.claude/agents/`, configuração dele). Com o ok:
   `instalar_agentes.py instalar` — eles aparecem numa sessão NOVA. Até lá, faça o trabalho dos departamentos você mesmo
   (os agentes só aceleram lotes; nada depende deles). Os agentes seguem a mesma regra das chaves: devolvem
   `"precisa": "chave <NOME>"` e nunca tocam em chaves. Teste: `python tests/test_agentes.py`.

## O estúdio — departamentos (2026-11-06)

Cada vídeo é feito como um filme: **eu sou o Diretor Geral** (coordeno, escolho ferramenta, confiro e levo para aprovação) e cada departamento é um papel com ferramenta própria — não várias IAs conversando (custo). Sub-agentes só onde compensa (ex.: continuidade de muitas tomadas em paralelo). Todos leem e escrevem a **bíblia da produção** `<projeto>/producao.json` (`scripts/producao.py`): elenco, cenários, objetos e cada **tomada** com decupagem, versões (arquivo, prompt, modelo, custo, data), checagem de continuidade e status (rascunho → aguardando → aprovada | refazer).

| Departamento | Faz | Ferramenta |
|---|---|---|
| Produtor executivo | objetivo, duração, público, teto de custo | entrevista, `catalogo.py`, `roteador.py`, `custos.py` |
| Roteiro | história, falas, gancho, re-gancho, final | `references/roteiro.md`, `gancho.md`, `extrair_ativos.py` |
| Elenco | personagem: ficha (várias vistas), traços fixos, figurino com cores, voz | `ficha_grade.py ficha` → `producao.py personagem` |
| Atuação / voz | emoção, intensidade, ritmo, pausas por fala; ouve e refaz | `diretor_voz.py` |
| Fotografia (decupagem) | **contrato de direção de cada plano** (modo, ação em verbos, atuação, voz off/em quadro, enquadramento, ângulo, câmera com motivo, quadro inicial/final, efeitos, critérios) + regras de fotografia (variar plano, nada de 3 iguais seguidos, zoom ≤ 1 em 5, plano/contraplano) | `contrato.py rascunhar` → `validar` → `rotear` (orçamento) → `storyboard` · `producao.py decupar` |
| Direção de arte | **estilo visual** (catálogo de 21 estilos + técnicas, incl. live-action; comparativo do mesmo personagem em vários estilos), cenário (luz, paleta), objetos; prompt montado da bíblia | `estilos.py listar --genero …` · `comparar …` · `aplicar <id>` · `producao.py cenario/objeto` · `producao.py prompt <tomada>` → `gerar_imagem.py --ref …` |
| Animação / VFX | **atuação de verdade**: clipe para todo plano com ação/reação (Kling 2.6/3 Pro, 1º e último quadro); motion graphics só para título/tela | `gerar_clipe_fal.py`, `motion_control.py`, `templates/remotion-motion/` |
| **Lip-sync** | personagem que aparece falando mexe a boca no tempo da fala; narração em off = boca fechada | `lipsync.py avatar` (Kling Avatar, US$ 0,056/s) · `omnihuman` (fala + corpo) · `sincronizar` (boca sobre clipe pronto) |
| **Continuidade** | compara cada imagem/clipe com a bíblia (rosto, traços, figurino, objetos, cenário, luz, encaixe com a tomada anterior) — **obrigatório antes do ponto 2 e da montagem**; ❌ volta para refazer | `continuidade.py t001 …` / `--todas` |
| Colorista | iguala as cores de cada tomada à referência do cenário (LUT .cube) | `colorir.py cena <cenario>` / `todas` |
| Sound designer | efeitos com causa na tela (foley gerado do próprio clipe ou por descrição), riser + golpe | `foley.py pista` (do contrato) · `foley.py clipe/texto` · `som_pro.py` |
| Ambientação sonora | cama de fundo por cenário (chuva, rua, cantina, noite, vento, temporal), troca nos cortes | `ambiente.py` / `montar_historia.py --ambiente auto` |
| Diretor musical | trilha por blocos de clima, batida | `trilha_ia.py`, `trilha_gratis.py`, `batida.py` |
| Montagem e mixagem | cortes, legendas, mix voz/trilha/ambiente/efeitos | Remotion, `montar_historia.py`, `mixar_comercial.py` |
| **Diretor de atuação** | beats por plano (antecipação → ação → consequência → reação), partes do corpo exigidas, física causa → efeito; prompt com tempo por fase | `contrato.py prompt` · `validar` |
| **Supervisor de qualidade** | REPROVA o que não cumpre o contrato e manda refazer só aquele plano: movimento próprio × só câmera, duração, fala × roteiro (whisper), legenda × áudio, ação/identidade/mãos/boca | `movimento.py` · `atuacao.py` (personagem × cenário, partes do corpo, até o fim, proporções) · `inspetor.py planos` (cada clipe, nota 0–100) · `inspetor.py audio` (cada fala) · `inspetor.py filme` (montado) · `conferencia.py texto|lipsync|storyboard` |
| Pós | retenção, kit de publicação | `verificar_retencao.py`, `kit_publicacao.py` |
| **Espectador** | o Gemini ASSISTE ao vídeo com som no lugar de 3 públicos (alvo, impaciente, crítico): nota, curva de interesse, onde arrastaria, risos, confusões, problemas técnicos com o segundo exato, 3 ajustes. Roda **antes de toda amostra e do ponto 3**; eu corrijo o que ele achar e mando ao usuário o vídeo já filtrado + o resumo. Não aprova no lugar do usuário | `espectador.py <video.mp4> --briefing BRIEFING.md` |

**Fluxo de cada tomada:** decupagem → `producao.py prompt` → imagem (`--ref` ficha + cenário) → `producao.py versao` → `continuidade.py` → (clipe → versão → continuidade) → `colorir.py` → storyboard no chat → aprovada (`producao.py status <tomada> aprovada`). Nada vai para a montagem com continuidade ❌ ou sem aprovação. **Toda aprovação é pelo chat** (entrevista, amostras, pontos de conferência) — sem painel (pedido do usuário, 2026-11-06).

### Produção autônoma verificável, barata e previsível (2026-11-07 — lições da MinhaMarca "dois mundos")

Fluxo normal de todo vídeo novo (os scripts antigos continuam; sem `projeto.json` tudo funciona como antes):
1. **`projeto.py iniciar <pasta> --modo custo_zero|economico|teto [--teto 22] --job <id>`** → `projeto.json`: duração (s ↔ frames ↔ fps), formato, modo de autonomia, qualidade (bloqueios objetivos, `exigir_evidencia`), orçamento (teto autorizado, saldo por provedor, `licencas_confirmadas`), prazo, limites por plano (refações, US$, minutos), `uso` (publicidade ⇒ licença comercial). `projeto.py orcamento` mostra **teto · saldo no provedor · gasto confirmado · reservas abertas (órfãs listadas) · cobranças desconhecidas · livre** — tudo do livro do roteador, sem inventar cobrança.
   - `custo_zero`: nenhuma chamada paga (geração, voz, trilha, **análise multimodal**); imagens/análises viram trabalho do Claude (visão nativa pelas folhas) e rotas grátis. `economico`: menor custo por segundo aprovado. `teto`: melhor valor até o teto.
   - licença: catálogo com `commercial_use: "unknown"` + `uso: "publicidade"` ⇒ bloqueado. Libera só quando o usuário confirma no chat → id em `orcamento.licencas_confirmadas`.
   - **Vídeo grátis de banco (2026-11-11, ideia do MoneyPrinterTurbo):** cena "real" genérica (cidade aérea, prédio, rua à noite) → `buscar_stock.py roteiro cenas.json --saida <projeto>/assets/stock` (Pexels/Pixabay, chave grátis em `PEXELS_API_KEY`/`PIXABAY_API_KEY`) → mostrar a `grade.jpg` de cada cena no chat → **baixar só com o ok do usuário** (`baixar candidatos.json --ids 3,5`, grava `creditos.json`). Conferir rosto em destaque, marca e placa antes de usar em anúncio.
2. **`acervo.py buscar "…"`** antes de qualquer API: `reuso_direto` (aprovado, íntegro, sem ressalva) × `referencia` (inclui `referencia_negativa` = reprovados: o que não repetir). `acervo.py indexar <projeto>` ao fechar cada vídeo; `biblioteca.md` ganha o resumo entre marcadores.
3. **`animatic.py <projeto>`** → roteiro temporal + animatic com voz provisória/final e ativos existentes (grátis). Divergência de duração é decidida AQUI pelo briefing e registrada uma vez (`entrega/decisoes.json`).
4. **`autonomo.py rodar roteiro.json --job <id>`** (lê o projeto.json): inspeciona a **imagem-chave antes do clipe** (`inspetor.py imagens`); gera pelo roteador (reserva atômica antes do envio; job pago com timeout é **consultado/recuperado antes** de qualquer reenvio — `provedores.py pendentes|resolver`; mesmo pedido = reuso idempotente); reprovado → `correcoes.py` escolhe a correção de **menor custo total** (overlay → máscara → corte → recomposição → mudança editorial → edição localizada → regenerar imagem → regenerar clipe; defeito de montagem nunca regenera); limites esgotados → alternativa sem gasto ou `marcado` com ressalva. Bloqueio de orçamento é registrado uma vez e não trava o trabalho grátis dos outros planos.
5. **Inspeção visual** (uma chamada multimodal por arquivo, `qa_visual.py`): fichas por caminho explícito (`roteiro.elenco[q].ref` → `producao.json` do projeto; as refs enviadas ficam registradas com sha), anatomia (braços/mãos por pessoa), figurino × ficha, orientação dos aparelhos, textos/símbolos gerados, oclusão, continuidade temporal, identidade, boca. **Bloqueios objetivos** (membros extras, figurino involuntário, interface na traseira, texto/símbolo gerado, falha visual evidente, identidade) reprovam com qualquer nota; campo sem resposta = `nao_verificado`. Qualidade visual e completude do contrato são números separados. Cache por hash do arquivo + refs + contrato + versão das regras; custo da análise no mesmo livro (categoria `analise`).
6. **Montagem**: `inspetor.py filme` agora inclui `qa_montagem.py` (congelamento/repetição no início, meio e fim de cada plano, **cada lado da tela dividida separado**, pausa intencional via `direcao.pausa_intencional`, fim de clipe preenchido com Freeze, duração efetiva) e acusa **render desatualizado** (`estado_producao.py render --registrar` depois de cada render). Revisão densa só nos trechos de risco (`entrega/inspecao/montagem-<id>.jpg`); `qa_montagem.py comparar antes.mp4 depois.mp4 --plano X` prova a correção no arquivo final.
7. **Estado** (`estado_producao.py sincronizar <projeto>`): planejado → gerado → inspecionado → corrigido_no_codigo → renderizado → verificado_no_render, por hash de roteiro/contrato/refs/mídia/composição; mudar um contrato invalida só o clipe dele.
8. **Exceções**: `inspetor.py adaptar --planos X --mudanca '{"voz":"off"}' --nota "motivo"` revisa o contrato, guarda a reprovação original e exige nova inspeção; `revisar` por cima de reprovação vira `aprovado_com_excecao` (nunca aprovação limpa) e não derruba bloqueio objetivo. `revisar --imagem` = decisão do diretor sobre a imagem-chave.
9. **Avaliação**: `projeto.py avaliar <pasta> --nota 8 --fonte usuario --texto "…"` = nota EDITORIAL (arquivo próprio), separada das métricas de audiência (`metricas.py`).
10. **Progresso de tempos em tempos (pedido do usuário, 2026-11-07):** informe ao usuário o **tempo de execução e a %**. O `autonomo.py` imprime `⏱ [geração dos takes] 3/8 · 37% · 12min04s decorridos · ~20min restantes · projeto 52% · 1h03min desde o início` a cada take e a cada `--aviso-s` (60 s) enquanto um take demora; `progresso.py <projeto>` dá a linha do projeto a qualquer momento (`--vigiar 300` repete). Em tarefa longa em segundo plano, repasse a linha a cada etapa e a cada ~5 min. Estado em `entrega/progresso.json`.

### Roteador inteligente de vídeo — grátis primeiro, por pontuação (2026-11-07)
Doc completa: `docs/roteador-video-2026-11-07.md`. Antes de produzir: `provider_discovery.py` (consulta real, grátis) → `memoria/provedores-descoberta.json`.
- **Provedores** (`config/provedores.json`, interface `VideoProvider` em `provedores_video.py`): grátis por API (cota ZeroGPU da conta/IP, comum a todos os Spaces) — `hf-wan22-i2v` (0,5–5 s), `hf-ltx-distilled` (0,3–8,5 s, t2v/i2v), `hf-ltx2-turbo` (1º e último quadro; duração não exposta), `hf-wan21-fast` (0,3–3,4 s), `hf-wan22-lightning` (0,5–10 s, último quadro); pagos — Runware/fal (já existiam), `alibaba-wan22-i2v-flash` (US$ 0,015/s 480P · 0,036/s 720P), `ltx-23-fast` (US$ 0,03/s 720p), `ltx-23-pro` (0,04/s); `alibaba-wan22-i2v-plus` sem preço = bloqueado. Licença comercial de todos = `unknown` até o usuário confirmar (projeto.json `licencas_confirmadas`).
- **Seleção** (política `pontuacao`, padrão no modo `teto`): níveis grátis → crédito promocional → pago; dentro do nível, nota = 30 % qualidade (declarada × aprovação medida) · 25 % custo por segundo · 20 % compatibilidade com o tipo do take (`fala`, `cinematografico`, `i2v_personagem`, `simples`; `motion` = Remotion, não chama API) · 15 % disponibilidade · 10 % consistência. Pesos em `config/roteamento.json` → `api_router.pontuacao`. Grátis só entra se cumprir a qualidade mínima do take; um provedor grátis que passa no inspetor (≥ 4 takes, ≥ 75 %) sobe de nível sozinho.
- **Fallback**: indisponível/cota/erro recuperável/timeout → próximo; job pago com timeout = consultado na retomada (nunca reenviado por cima); disjuntor, backoff e limite de tentativas do roteador; pago só com orçamento configurado (`api_router.require_paid_approval`). Crédito promocional: `creditos_promocionais: {saldo, unidade, valido_ate}` no catálogo + contador local.
- **Continuidade**: contrato `continua_de: "<plano>"` (1º quadro = último quadro do take anterior aprovado), `quadro_final_img`, `evitar: [...]` (prompt negativo onde o modelo aceita).
- **Painel**: `resumo_execucao.py <projeto>` → takes por nível, custo (confirmado/desconhecido/reservas), economia vs referência documentada (fal Kling 2.6, US$ 0,07/s), tempo, aprovados/reprovados, provedores disponíveis.

Funções explícitas (`config/analise.json`): **Gemini 3.8 Flash** = análise visual (US$ 0,75/1M entrada, 3,75/1M saída até 2026-12-31; free tier usa os dados → não usar com material de cliente). **Gemini Omni Flash** (`gemini-omni-1.2-flash` Stable; `1.1` aponta para `1.2` em 2026-12-03; preview desligado) = geração/edição de vídeo — catalogado, **fora do roteador** até haver adaptador testado e preço por segundo confirmado na doc da API (só há preço por token). **Watch MCP**, quando estiver na sessão: o Claude usa para quadros e transcrição; os scripts usam cv2 + whisper local. Análise de áudio da mixagem continua local (LUFS, voz × trilha). `benchmark_provedores.py planejar|medir` (sem custo) compara anatomia, figurino, aparelhos, continuidade, latência e custo por segundo aprovado. `referencia_reversa.py onde|estrutura` usa o reverse-any-video da versão do HyperFrames registrada em `installed_plugins.json` (ritmo/cortes para o acervo; nada pago).

Exemplos com comandos e a execução real (sem custo) no MinhaMarca: `docs/exemplos-producao-2026-11-07.md`. Testes: `tests/test_regressao.py` (24 casos) + as 13 suítes antigas — todos sem rede.

### Roteamento inteligente de APIs — grátis primeiro, pago dentro do orçamento (2026-11-06)
Em cada etapa (voz, imagem, vídeo, lip-sync) use o roteador: `scripts/provedores.py` (spec em `docs/ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md`).
Descreva a tarefa num JSON (job_id = o vídeo, scene_id, task_type, mode preview|final, requirements) e rode
`provedores.py planejar tarefa.json` (mostra quem seria usado, por quê e quanto custa — nada é chamado) → `executar tarefa.json`.
- **Grátis primeiro só se servir:** provedor grátis entra apenas se cumpre a qualidade mínima (prévia = standard, final = high,
  comercial/cinema = premium), a licença (conteúdo comercial exige `allowed`) e as capacidades da tarefa.
- **Cota acabou → próximo grátis → pago** dentro do teto de `config/roteamento.json` (hoje: US$ 0,75 por operação, US$ 3,10 por
  vídeo — os valores que o usuário aprovou). Acima do teto, ou preço desconhecido = `waiting_approval`: **pergunte no chat** e,
  com o sim, registre `provedores.py aprovar --job <vídeo> --ate <US$>` (ou `--custo-desconhecido`, `--troca-voz`, `--troca-estilo`).
- **Voz não troca sozinha:** a 1ª voz usada no vídeo fica travada (provedor + perfil). **Estilo:** fallback só para quem usa as
  mesmas referências (imagem-chave/ficha).
- Erros: cota ≠ limite de taxa ≠ credencial (401/403 desliga a rota) ≠ payload ≠ saldo; timeout de job pago para em
  `pendente_verificacao` (recuperar com `gerar_clipe_fal.py --recuperar`), nunca gera outro pago por cima.
- `provedores.py status` = situação real de cada provedor; `relatorio --job <vídeo>` = previsto × cobrado confirmado × desconhecido.
- Catálogo `config/provedores.json`: só entra habilitado o que foi verificado (preço `null` = desconhecido, bloqueia). Rollback:
  `"ativo": false` em `config/roteamento.json` — os scripts antigos (`gerar_clipe_fal.py`, `lipsync.py`, `gerar_imagem.py`,
  `tts_gemini.py`) continuam funcionando direto.

### Portões de qualidade e custo (2026-11-06 — auditoria P01–P56, `docs/auditoria-2026-11-06-correcoes.md`)
Nada avança por omissão — **falha fechado**. Regras que valem em todos os scripts (módulo comum `scripts/integridade.py`):
- **QA tem 3 estados:** `aprovado` · `reprovado` · `nao_verificado`. Só `aprovado` entra na montagem final. Sem Gemini, a parte
  visual fica `nao_verificado` até EU olhar a folha de quadros e gravar: `inspetor.py revisar roteiro.json --planos d2 --estado
  aprovado --nota "o que vi"` (vale só para o mesmo arquivo; reprovação objetiva — congelado, só câmera — não se revisa, refaz).
- **Contrato estrito** (`contrato.py validar`, código ≠ 0 = não gera): plano com personagem precisa de `beats` com tempo em ordem,
  sem lacuna, cobrindo até o último quadro, fase válida (`antecipacao|acao|consequencia|reacao|pausa`), `en` não vazio, `exige`
  e `fisica` quando há consequência. Pausa dramática = beat `pausa` (não reprova). Plano > 15 s = dividir. `prompt_clipe.py`
  também exige o quadro inicial do plano seguinte igual ao final do anterior (ou `"transicao_intencional": true`).
- **Preço desconhecido nunca é US$ 0:** roteador/gerador recusam gastar; duração não suportada é recusada (não encurta);
  modelo abaixo do piso de qualidade = `sem_modelo_compativel`. `--orcamento` é o teto do LOTE (`--orcamento-por-clipe` o antigo).
  `gerar_imagem.py` só gasta com `--confirmar`. Grupos paralelos do orquestrador reservam saldo somado.
- **Bíblia versionada:** `producao.py versao` recusa arquivo ausente/vazio e grava `sha256`; clipe guarda a imagem de origem
  (imagem nova invalida o clipe velho); `producao.py qa <tomada> aprovado|reprovado` registra a inspeção na versão;
  `status aprovada` / `orquestrador.py aprovar` recusam tomada sem imagem válida + continuidade (decisão do usuário no chat
  apesar disso: `--forcar --nota`). Escrita com trava + revisão (dois agentes não se sobrescrevem).
- **Montagem** (`montar_historia.py`): o padrão é FINAL — para se plano de atuação não tiver clipe válido e aprovado, se houver
  rascunho, ou se uma voz existente não conferir com o texto (`--regravar-vozes` autoriza regravar; nunca regrava sozinho).
  `--preview` = rascunho permissivo com avisos. Projeto antigo sem inspeção: `--aceitar-sem-inspecao` (mídia válida continua
  obrigatória; `reprovado` continua bloqueando). Manifesto (`historia.json`/`video.json`) leva `midia{arquivo, sha256, qa_estado}`.
  `inspetor.py filme` confere 1:1: plano ausente, mídia trocada, legenda errada (2+ palavras no plano) = reprovado.
- **Template base:** cena `video` (MP4), imagem sem `zoom` fica parada, 1º quadro do gancho sem fade, tipo desconhecido vira
  quadro de erro visível; `preparar_remotion.py` dá nome único a cada mídia e resolve caminhos pela pasta do projeto.
- Testes (sem rede, sem gasto): `python tests/test_contrato_qa.py` · `tests/test_custos_roteamento.py` · `tests/test_montagem.py` ·
  `tests/test_roteador_apis.py`.
  Rodar os três depois de mexer em qualquer script.

### Runware — fornecedor principal de vídeo e lip-sync (2026-11-06, INTEGRACAO-RUNWARE.md)
- **Política padrão do roteador: `runware_primary`** (config/roteamento.json). Entre os provedores que cumprem
  capacidade/qualidade/licença/credencial, a Runware vem primeiro, pelo menor custo por tomada APROVADA (preço ÷ taxa de
  aprovação); fal.ai e os demais ficam de fallback. **Sem `RUNWARE_API_KEY` as entradas runware-* ficam de fora sozinhas
  e tudo segue no fal** (rollback natural). Rollback explícito: `policy: free_first` ou `enabled: false` nas runware-*
  (backups: config/*.antes-runware.json).
- Modelos validados (schema.json + x-pricing oficiais, 2026-11-06): Kling 2.6 Pro `klingai:kling-video@2.6-pro`
  (5/10 s, US$ 0,07/s) · Kling 3 Pro `klingai:kling-video@3-pro` (3–15 s inteiros, US$ 0,112/s) · Kling Avatar 2.0 std
  `klingai:avatar@2.0-standard` (US$ 0,044/s de áudio) · OmniHuman 1.5 `bytedance:5@2` (US$ 0,132/s). Imagem Runware
  DESLIGADA até verificar preço e campo de referência (falha fechado). `scripts/runware.py modelos`.
- `scripts/runware.py`: valida ANTES da rede (AIR, duração, último quadro, ≥ 300 px, proporção 0,4–2,5, áudio do
  lip-sync), grava o job (`<saida>.runware.json` com taskUUID) antes do envio, polling `getResponse` com backoff,
  **retomada sem reenvio** (`runware.py retomar <clipe>` / `gerar_clipe.py --retomar`), envio sem resposta =
  `unknown_billing` (bloqueia reenvio), download só HTTPS de *.runware.ai com tamanho máximo, áudio pelo `mediaStorage`
  (mediaUUID em cache), custo real por `includeCost` (sem ele = desconhecido), cache por hash da entrada (custo 0),
  chave nunca em log (nem o prompt). `runware.py conta` = saldo (não gera nada).
- CLI genérica: `scripts/gerar_clipe.py` (roteador; `--planejar` não gasta). `gerar_clipe_fal.py`, `lipsync.py` e
  `gerar_imagem.py` continuam iguais. O modo autônomo usa a política padrão.
- Inspeção por versão: `entrega/inspecao/<take>-<sha8>.json/.md`. Watch MCP não instalado (decisão do usuário): o
  inspetor visual é o Gemini; sem ele = `nao_verificado`, nunca aprovado.
- **Licença:** os Termos da Runware permitem uso comercial, mas listam "Use the Services to advertise or offer to sell
  goods and services" entre as proibições — confirmar com a Runware antes de usar em ANÚNCIO (catálogo: `nota_licenca`).
- MCP hospedado instalado (`claude mcp add --transport http runware https://mcp.runware.ai`): login OAuth pelo navegador
  (o usuário cola a chave na página de autorização). O MCP é para uso interativo; os scripts usam a API REST.
- Testes sem crédito: `tests/test_runware_provider.py` · `_router` · `_budget` · `_inspector` · `_regression` (roda as 7 antigas).

### Modo autônomo — o estúdio assiste e aprova cada take (2026-11-06, pedido do usuário)
O usuário não quer ficar aprovando take por take. Depois que ele aprova **roteiro + orçamento total** (ponto 1) e as
**imagens-chave** (ponto 2), a geração roda sozinha: `scripts/autonomo.py rodar roteiro.json --job <vídeo> [--teto US$]`.
- Para cada plano de atuação, na ordem: gera pelo roteador → `inspetor.py planos --registrar` (Gemini assiste com som +
  YOLO + whisper, nota ≥ 85) → **aprovado segue**; **reprovado refaz só ele** com a correção do inspetor no prompt
  (`--max-refacoes`, padrão 2; esgotou = `marcado`, não gasta mais); take reprovado fica em `assets/clips/rejeitados/`.
- **Nunca aprova sem inspeção:** sem Gemini o take vira `revisao_diretor` — EU olho `entrega/inspecao/<id>.jpg` e gravo
  `inspetor.py revisar`. Teto do roteador atingido = o laço PARA (`precisa_orcamento`) e eu pergunto no chat.
- Sem imagem/voz = `aguardando_imagem`/`aguardando_voz` (pula, não gasta). Job pago sem resposta = `pendente_verificacao`.
- `--simular` mostra quem geraria cada take e quanto custa, sem gastar. `autonomo.py status` / `entrega/autonomo-relatorio.md`.
- O usuário continua dono do **ponto 3** (filme montado + relatório dos takes). Watch MCP avaliado e descartado: só extrai
  quadros/transcrição, o inspetor já faz isso e o Gemini vê o vídeo inteiro com som (repo sem uso, sem teste no Windows).
- Testes: `tests/test_autonomo.py`.

### Conferências de texto, lip-sync e storyboard (2026-11-06, pedido do usuário)
`scripts/conferencia.py` cobre o que o inspetor não media (locais e grátis; Gemini só na ortografia/enquadramento):
- **texto** `roteiro.json filme.mp4` — EasyOCR lê 1 quadro a cada 0,5 s de cada plano: o que o roteiro manda escrever
  (`texto_tela[]`, `beneficio`, `texto_obrigatorio[]`) tem de aparecer; `termos_proibidos[]` (menu inexistente) = grave;
  Gemini aponta ortografia, texto cortado/ilegível/deformado e nome fora de `nomes_reais[]`. Sem Gemini = não verificado.
- **lipsync** `roteiro.json [--planos]` — boca pelo YOLO pose (nariz + olhos) × envelope da voz: atraso medido com precisão
  abaixo de 1 quadro (erro ≤ 4 ms no teste), reprova acima de ±120 ms ou boca parada em mais da metade da fala; rosto
  não achado = não verificado. O modo autônomo roda isso em TODO take com fala em quadro e refaz com a correção.
- **storyboard** `roteiro.json filme.mp4` — todos os planos, na ordem, duração por plano (±15 %) e por bloco (±1,5 s),
  quadro do filme × imagem-chave/clipe aprovado (SSIM + cor) e, com Gemini, quem aparece e tamanho do plano.
- **filme** = texto + storyboard. Roda antes do ponto 3, junto com `inspetor.py filme` e o espectador.
- Testes: `tests/test_conferencia.py` (lip-sync com vídeo sintético de atraso conhecido).

### Especialistas: trilha, atuação, figurino e atenção (2026-11-06, pedido do usuário)
`scripts/especialistas.py` (medição local + Gemini assistindo/escutando; sem Gemini = não verificado):
- **trilha** `roteiro.json filme.mp4 [--voz pista --trilha pista]` — −14 LUFS ±1, pico ≤ −1 dBTP, buraco de som, corte
  seco no fim, voz ≥ 9 dB acima da trilha (com `roteiro.mix`), cortes na batida (aviso) e escuta do clima por bloco
  (`roteiro.trilha_clima`), música brigando com a voz, troca brusca, efeito sem causa.
- **atuacao** `roteiro.json [--planos]` — diretor de atuação: emoção pedida × vista e intensidade 1–5 por beat; EXAGERO
  ou diferença ≥ 2 reprova (lição do café dramático), rosto congelado, tempo da reação/cômico, credibilidade; devolve
  `correcao_en` para o próximo take. Complementa `atuacao.py` (que mede se o corpo mexe).
- **figurino** `roteiro.json [--planos | filme.mp4]` — personagem × `roteiro.elenco` (ref + figurino + traços): item
  diferente/ausente (traço = grave), roupa/acessório fora da ficha, rosto; objeto de cena não é figurino; lado só conta
  se a ficha mostrar.
- **atencao** `roteiro.json [filme.mp4]` — especialista em neurociência da atenção e psicologia comportamental
  (`references/atencao.md`, agente `estudio-atencao`): no ROTEIRO antes de gastar (palavras/s, carga de texto, telas
  longas, gancho, re-gancho, CTA + nota 0–100 e curva prevista) e no FILME (novidade por segundo, vales > 3 s, 1ª mudança).
  É conselheiro: decisão do usuário vence o parecer.
- O **modo autônomo** roda atuação + figurino (e lip-sync nas falas) em todo take; reprovado refaz com a correção deles.
- Antes do ponto 3: `inspetor.py filme` + `conferencia.py filme` + `especialistas.py trilha` + `figurino … filme.mp4` +
  `atencao … filme.mp4` + espectador. Testes: `tests/test_especialistas.py`.

### Animação de verdade, não fotos com zoom (2026-11-06 — análise do Plano 47 pelo usuário)
O Ep. 1 do Plano 47 saiu com **65 % do tempo só com zoom/pan sobre foto** (medido por `movimento.py`) e 2 dos 10 clipes pagos sem movimento próprio; a 1ª fala saiu "Plano **corento** e sete" e passou na checagem. Regras desde então:
1. **Câmera em movimento não é animação.** Plano com personagem fazendo/reagindo (modo `acao`, `reacao`, `fala`) sai como clipe animado. Foto + câmera só para `insert`, `estabelecimento` e `titulo`, no máximo **25 % do tempo**.
2. **Fluxo novo:** roteiro → **contratos** (`contrato.py rascunhar` + `validar`) → **storyboard dos contratos** (grátis, ponto 1) → orçamento (`contrato.py rotear`) → imagens-chave por enquadramento (ponto 2) → clipes/lip-sync → **inspetor** (`inspetor.py planos --registrar`) → refazer só os reprovados → foley (`foley.py pista`) → montagem → `inspetor.py filme` + espectador → ponto 3.
3. **Rotas por plano** (`contrato.py rotear`): ação/reação → Kling 2.6 Pro (US$ 0,35 por 5 s) ou Kling 3 Pro (3–15 s); fala em quadro → Kling Avatar v2 (US$ 0,056/s) ou OmniHuman 1.5 com ação de corpo (US$ 0,16/s); título/cartão → código. O roteador não escolhe modelo q2 para personagem (Seedance Lite falhou 2 em 10).
4. **Cada plano tem imagem-chave própria no enquadramento do contrato** (PG, PM, close…) — nunca o mesmo quadro reaproveitado para planos diferentes.
5. **Nada é aprovado só porque a API devolveu.** `inspetor.py` reprova: só câmera em plano de atuação, fala com palavra errada/faltando (fala curta exige 100 %), início/fim cortado, legenda diferente do áudio, e — pela visão — ação que não acontece, personagem diferente da ficha, mãos/objetos deformados, boca parada quando ele fala. Sem cota do Gemini, a parte visual vira folha de quadros (`entrega/inspecao/<plano>.jpg`) que **eu** olho (Read) antes de aprovar.
6. **Teste antes de escalar:** projeto novo com essa técnica começa por **3 cenas de teste** (uma de corpo, uma de diálogo com lip-sync, uma de interação física + câmera). Só depois que as 3 passam no inspetor e no usuário o mesmo método vai para o filme inteiro.
7. **Atuação do 1º ao último quadro (2026-11-06, 2ª análise do usuário):** o modelo de vídeo começa a ação e congela; a lama se mexe e o rapaz não. Por isso:
   - **Diretor de atuação:** todo plano com personagem tem `beats` no contrato (antecipação → ação → consequência → reação, cada um com tempo, corpo, rosto e movimento secundário), `exige` (partes que têm de mexer) e `fisica` (causa → efeito). O prompt de vídeo sai de `contrato.py prompt` com o tempo de cada fase. Piada sempre fecha com um beat de **reação** (no plano ou no seguinte).
   - **Validador de atuação** (`atuacao.py`, YOLO pose + segmentação, local): personagem × cenário (congelado), cada parte do corpo, sustentação até o fim (último terço ≥ 30 %), proporções estáveis. Entra no `inspetor.py`.
   - **Nota 0–100 por plano:** atuação 25 · consistência 20 · física 20 · direção 15 · áudio/lip-sync 10 · ritmo 10. Aprova com ≥ 85 e sem falha grave; física e identidade só contam depois da revisão visual (Gemini ou eu pelas folhas).
   - **Imagem-chave só com quem atua no plano**: gente no fundo da imagem vira ator (d1 do teste: a Bia "mergulhou" na poça num insert de pneu).
   - Insert de objeto sem personagem pode ser foto + câmera (push-in, tremor, borrão) em código.
   - Mixagem: faixas separadas (voz, trilha, efeitos, ambiente), voz ≥ 9 dB acima do fundo, **−14 LUFS** no arquivo final.
   - **Rota grátis de vídeo** quando o fal está sem saldo: Space `zerogpu-aoti/wan2-2-fp8da-aoti-faster` (Wan 2.2) e `Wan-AI/Wan2.2-S2V` (fala), 3 clipes/dia sem token HF, mais com `hf auth login`.
8. Gemini com **teto de gasto mensal** atingido (erro "spending cap"): TTS, espectador, continuidade e `contrato.py rascunhar` param — avise o usuário (ele ajusta em ai.studio/spend); eu escrevo os contratos e reviso as folhas de quadros enquanto isso.

### Orquestração — como o Diretor Geral conduz (2026-11-06)
- **Agentes** (contratos em `agentes/estudio-*.md`, instalados em `~/.claude/agents/`, modelo sonnet para economizar): `estudio-roteirista`, `estudio-elenco`, `estudio-fotografia`, `estudio-arte` (inclui cor), `estudio-animacao`, `estudio-audio` (voz, ambiente, efeitos), `estudio-musical`, `estudio-editor`, `estudio-qualidade` (continuidade, voz, retenção). Cada um: responsabilidades, entradas, ferramentas, entrega em JSON padronizado, restrições (não muda roteiro, identidade nem estilo; gasta só dentro do saldo; não fala com o usuário — devolve `precisa`).
- **Orquestrador** (`scripts/orquestrador.py`) deduz tudo da bíblia — não há fila separada para desencontrar:
  1. `orquestrador.py proximos` → grupos liberados agora. **Cada grupo = 1 chamada do Agent tool com o `subagent_type` indicado; grupos diferentes vão na MESMA mensagem (paralelo).** No prompt do agente: pasta do projeto, tomadas, tarefa e saldo.
  2. Ao voltar: ler o JSON de cada agente, conferir arquivos (Read nas imagens), rodar `proximos` de novo.
  3. **Aprovação** (sempre no chat, nunca por painel): tomadas em "esperando sua aprovação" → storyboard com as imagens pelo chat → `orquestrador.py aprovar t001 t002 …`.
  4. **Orçamento**: antes do 1º gasto do projeto, total estimado no chat → `orquestrador.py orcamento --aprovar <US$>`. Grupo com ⚠️ "precisa orçamento" não roda até o usuário aprovar mais.
  5. **Refação seletiva**: problema numa tomada → `orquestrador.py invalidar <id> --etapa imagem|clipe|voz --motivo …`; só ela volta. Imagem refeita pede nova aprovação; clipe e voz não.
  6. Montagem liberada quando todas as tomadas estão prontas e as vozes feitas; trilha/ambiente/montagem registrados com `orquestrador.py registrar`.
- Agentes só onde rende: lotes de tomadas e tarefas independentes. Coisa de 1–2 comandos eu faço direto.

### AI Film Production Bible + Supervisor de continuidade (2026-11-08, `docs/production-bible-2026-11-08.md`)
Camada de **pré-produção visual derivada do `producao.json`** (não substitui nada), obrigatória em filme com personagem/cenário (modo A/B/D); dispensável em motion puro/gravação de tela. Saída em `<projeto>/production_bible/`.
1. **Pré-produção** — `python scripts/orquestrador.py biblia [--modo supervisionado|automatico]` (= construir + pranchas + checagem). Ou separado:
   - `scripts/cinematografia/production_bible.py construir` → `bible.json` com IDs estáveis `char_*`/`env_*`/`prop_*`, referências versionadas por sha256, tempos de cada take (tomada → `falas-timeline.json` → duração), plano de câmera por intenção (decupagem existente manda), registro de objetos/figurino/horário e contradições (objeto que some, figurino que muda na cena, eixo 180°). Campos opcionais na tomada: `emocao`, `objetos_estado {obj: "na mão de X"}`, `figurino {pers: {...}}` (troca), `horario`, `lado_eixo`, `cruza_eixo`, `pausas [[a,b]]`, `justificativa_continuidade`.
   - `cinematografia/board_generator.py` → `boards/overview.html|png|pdf` + `cena-NN.*` (8 seções: personagens, storyboard, cenários, shot list, blocking, props, luz/cor, timeline) com as imagens reais.
   - `supervisor_continuidade.py pre` → lacunas de referência e contradições (`continuity/pre_producao.json`).
2. **Aprovação** — supervisionado (padrão): envie `boards/overview.png` pelo chat (ponto de conferência 1/2) e só com o "ok" rode `production_bible.py aprovar --nota "…"`. Automático: `pre` sem grave aprova sozinho. Enquanto não aprovado, o `orquestrador.py proximos` marca todo grupo pago com ⛔ e põe "prancha" na fila de aprovação. Bíblia mudou (referência nova, figurino, tomada) → aprovação volta a pendente.
3. **Produção** — cada clipe novo: `supervisor_continuidade.py inspecionar <take> <video> --visual` (análise pelo caminho do `inspetor.analisar_visual`: fichas, cache, reserva de orçamento) → congelamento com intervalo, duração, sincronia (`--narracao a,b`), membros extras, figurino fora da ficha, interface atrás do aparelho, objeto ausente; folha de quadros como evidência. Sem análise/confiança < 0,6 = **não verificado → revisão humana** (nunca aprovado). `entre-takes` acusa objeto que some no corte.
4. **Correção** — `supervisor_continuidade.py corrigir <take>` → causa, estratégia (`regerar_trecho` só no intervalo, `regerar_take`, `regerar_com_referencia`, `refazer_imagem_chave`, `ajustar_na_montagem`), prompt de correção e custo pelo roteador. Gasta só se: preço conhecido, cabe no orçamento de correção (`bible.correcao` ou `projeto.json limites.max_gasto_plano`), não é `custo_zero` e cabe no saldo livre do projeto; até `max_refacoes_plano` tentativas, reinspeciona a cada uma; esgotou → revisão humana. Em código, `corrigir(..., regenerar=função)` roda o ciclo completo.
- Substituição manual de referência: `production_bible.py referencia char_x frontal arquivo.png`. Custos: `production_bible.py custos` (sempre estimativa; real só no livro do roteador).
- Testes: `python tests/test_production_bible.py` (A figurino · B anatomia · C interface · D congelamento/limites/custo_zero · E continuidade · F prancha) — sem rede, provedores mockados.

## Etapas da produção

| # | Etapa | Entrega |
| --- | --- | --- |
| 0 | **Entrevista + gancho + amostra** | `BRIEFING.md` (com gatilho de compartilhamento e gancho escolhido em `references/gancho.md`) + amostra de 5–8 s aprovada |
| 1 | **Análise e referências** | Memória carregada, referências estudadas, briefing fechado |
| 2 | **Roteiro** | `ROTEIRO.md` / falas com tom, abrindo com o gancho aprovado → storyboard do ponto 1 |
| 3 | **Narração e storyboard** | Narração em áudio + `BEATS.json` (cada cena e palavra-chave no tempo exato da voz) |
| 4 | **Geração das cenas** | Imagens-chave por enquadramento (ponto 2) + clipe/lip-sync para todo plano com atuação (contrato) + inspetor aprovando plano a plano; motion graphics para título/tela |
| 5 | **Montagem, revisão e entrega** | Vídeo montado + relatório de retenção (ponto 3) + kit de publicação (`entrega/kit/`) |
| 6 | **Aprendizado** | Métricas de 48 h e 7 dias (`metricas.py`) → pontuação dos padrões atualizada |

Ao trabalhar, diga ao usuário em qual etapa está ("Etapa 3 — Narração e storyboard").
Projetos ficam em `~/estudio-video/projetos/<data>-<slug>/`, salvo se o usuário indicar outra pasta.

## Etapa 0 — Entrevista (obrigatória em vídeo novo — pedido do usuário, 2026-11-04)

Antes de qualquer roteiro, entreviste o usuário com o método da skill **grilling** (rodadas de perguntas numeradas, cada uma com sua recomendação; fatos você busca, decisões são dele) seguindo a árvore de `references/entrevista.md`. Na 1ª rodada pergunte sempre se ele quer que você **leia o código do sistema** (leitura direta + REA para build/web) para tirar o conteúdo dos recursos reais. Pergunte também as **ferramentas**: tipo de animação (A ilustração + Kling · B ilustração com zoom · C motion graphics · D estilo artístico Lemo-Opuscar · E gravação de tela), **voz** (Google Gemini TTS com tom ou VoiceStudio com a voz clonada dele) e **quantos segundos**. Pergunte também **por que alguém mandaria o vídeo para outra pessoa** (gatilho de compartilhamento, P06). O gancho tem **etapa própria** (`references/gancho.md`): 6 ganchos com fórmulas diferentes, pontuados, os 3 melhores para ele escolher e, se quiser, um 2º para teste A/B. No fim, faça uma **amostra de 5–8 s do gancho** com essas escolhas e envie para aprovação (Rodada 5). Termina com `<projeto>/BRIEFING.md` + amostra aprovados. Pule só se o usuário disser que já está tudo definido (e registre o que ele definiu no briefing).

## Pontos de conferência com o usuário (obrigatório — pedido do usuário, 2026-11-04)

O usuário quer **ver o storytelling durante a criação**. Em cada ponto abaixo, monte o storyboard com `scripts/storyboard.py` (cada tomada: imagem, tipo, ação, fala, texto na tela), **envie a imagem pelo chat (SendUserFile)** e espere a aprovação antes de seguir:

| # | Quando | O que vai no storyboard | Antes de gastar com |
|---|---|---|---|
| 1 | Roteiro e falas prontos | Tomadas sem imagem (quadro cinza com a ação) + falas e textos de tela | imagens por IA |
| 2 | Imagens-chave geradas (ficha do personagem + cenas) | As imagens reais de cada tomada | clipes de vídeo (fal.ai) |
| 3 | Vídeo montado | Quadros tirados da composição (`remotion still`) + relatório de **retenção** (`scripts/verificar_retencao.py`: abertura, trechos parados, re-gancho aos 40–50%, final em loop) | entrega final / publicação |

Nunca pule um ponto por conta própria; se o usuário disser "pode seguir direto", anote em `memoria/perfil.md`.

## Escolha o modo

- **CRIAR** — pediu um vídeo novo → Etapas 1 a 6.
- **EDITAR** — mandou um vídeo gravado/pronto para cortar, limpar, legendar, fatiar em vários cortes ou mudar de formato → `references/editar.md` (usa a Etapa 5 e a 6).
- **APRENDER** — mandou link/arquivo de vídeo viral como referência → Etapa 1 com `references/aprender-viral.md`.
- **COMERCIAL** — pediu um comercial/anúncio de produto com duração e cenas definidas (ou briefing de campanha, código do produto) → `references/comercial.md` (timeline fixa, falas por personagem, modelo `templates/remotion-comercial/`, entrega MP4 + roteiro + legenda + abertura A/B).
- **HISTÓRIA** — pediu história/mistério/"imagina que…" em 2ª pessoa com escolha A/B nos comentários (série) → `references/historia-interativa.md` (`scripts/montar_historia.py` + `templates/remotion-historia/`; engenharia reversa de ref-2026-11-03-whatsapp).
- **FEEDBACK** — contou como o vídeo performou ou o que achou → Etapa 6.
- Mandou referência E pediu vídeo → APRENDER primeiro, depois CRIAR usando aquela ficha.

## Ferramentas que esta skill orquestra

| Papel | Ferramenta | Etapa |
| --- | --- | --- |
| Download de vídeo por link | `yt-dlp` (instalado) | 1 |
| Medir vídeo de referência | `scripts/analisar_referencia.py` | 1 |
| Narração (padrão) | **Gemini 3.8 Flash TTS** pelo motor de áudio do `/media-use` (`audio.mjs`, `provider: "gemini"`); chave em `GEMINI_API_KEY` | 3 |
| Narração/falas por arquivo, direto na API (modo COMERCIAL) | `scripts/tts_gemini.py` — troca "MinhaMarca"→"Minha Marca" na fala | 3 |
| **Diretor de voz**: lê as falas com o GÊNERO (comercial, humor, romance, suspense, drama, institucional, tutorial) → emoção, intensidade 1–5, ritmo, pausas e ênfase por fala → gera no Gemini → **ouve** o resultado (emotion2vec+ = emoção ouvida; Parselmouth = variação do tom, velocidade, volume) → refaz corrigindo a direção o que não bateu (até 2×) → `relatorio-voz.md`. Grátis/local (só o Gemini usa cota) | `scripts/diretor_voz.py plano\|dirigir falas.json --genero humor --contexto "…" -o assets/voz` · `medir assets/voz/*.wav --direcao direcao.json` | 3 |
| Timeline de falas (legenda alinhada + amplitude para onda/boca) | `scripts/timeline_comercial.py` | 3 |
| Mixagem de falas na timeline + efeitos sintetizados + trilha + export final | `scripts/mixar_comercial.py` | 5 |
| Modelo Remotion de comercial (técnico, mascote, celular, fluxo fiscal) | `templates/remotion-comercial/` | 4 |
| Entrevista inicial (rodadas de perguntas com recomendação) | skill `grilling` + `references/entrevista.md` → `BRIEFING.md` | 0 |
| Ler o código do sistema para tirar recursos reais | sub-agente com leitura direta; REA (`mcp__rea__*`) para build, bundle web ou app instalado | 0 |
| Storyboard em imagem para o usuário conferir (pontos 1–3) | `scripts/storyboard.py` | 1–5 |
| Etapa do gancho: 6 fórmulas, pontuação, 3 melhores, gancho B opcional | `references/gancho.md` | 0 |
| Cardápio pago × grátis das formas de edição (visual A–H, motion, voz, trilha, som, batida, motion blur) + total estimado | `references/entrevista.md` → "Cardápio" | 0 |
| Biblioteca de motion grátis: texto cinético, contador, faixa, carimbo + tremida, balão, notificação, linha do tempo, gráfico de barras, mapa com rota | `templates/remotion-motion/motion.tsx` (vitrine `Demo.tsx`, guia `LEIA.md`) | 4 |
| Som profissional: filtra os efeitos (1 som por gesto, ≤ 10 por 10 s, espaço mínimo), riser + golpe na revelação, música desce antes do golpe; relatório do que cortou | `scripts/som_pro.py --sfx sfx.json --trilha <música> --revelacao <s> --duracao <s>` → `assets/som/` | 5 |
| Batida da música: BPM, compassos, drop; cortes × compasso; alinhar o drop num segundo do vídeo | `scripts/batida.py <música> [--cortes …] [--drop-em <s> -o …]` | 3–5 |
| **Catálogo de modelos com preço oficial e data** (vídeo, imagem, música, voz, local; recursos: imagem→vídeo, último quadro, durações) | `scripts/catalogo.py` (atualiza `memoria/catalogo-modelos.json` pela API do fal) · `--listar video` | antes de gastar |
| **Roteador de custos por cena**: motion grátis quando dá; senão o menor custo esperado por cena APROVADA (preço ÷ taxa de aprovação do histórico); perfis econômico (padrão) / equilibrado / premium; teto `--orcamento`; registra o motivo | `scripts/roteador.py video --duracao 5 --cena personagem [--perfil …]` · aprende com `--resultado <modelo> <cena> aprovado\|reprovado` | 4 |
| Clipes com roteador, cache e A/B: `--modelo auto` (roteador escolhe), qualquer id do catálogo, `--ultimo-quadro`, **`--ab auto --orcamento-ab X`** (mesma cena em 2 modelos econômicos, folha de comparação, você escolhe) | `scripts/gerar_clipe_fal.py` | 4 |
| **Livro-caixa** (todo gasto pago e reaproveitado do cache por projeto; total, por etapa, "quanto custaria no modelo mais caro") e **cache** (mesma entrada nunca é paga duas vezes — imagens, clipes) | `scripts/custos.py relatorio [projeto]` · `custos.py geral` · cache em `%USERPROFILE%\estudio-video\cache\` | 4–6 |
| **Motion control** (vídeo → vídeo): **trocar o personagem** de um vídeo do usuário pelo da biblioteca (Wan 2.2 Animate Replace) ou fazer um personagem **copiar o movimento** do vídeo (Kling 2.6 Motion Control Std/Pro, Wan Animate Move); corta o trecho (preço por segundo), roteador, cache, livro-caixa. **Só oferecido na entrevista (18d) com a tabela de custos.** | `scripts/motion_control.py --custos --video v.mp4` · `--modo trocar\|mover --video v.mp4 --personagem img.png -o saida.mp4 [--confirmar]` | 0 e 4 |
| **Ficha em várias vistas** (rosto + corpo frente/lado/costas + 6 expressões, 1 imagem) e **grade 3×3** (9 ângulos do mesmo momento numa imagem, recorte automático) — ideia do AID Studio (MIT) | `scripts/ficha_grade.py ficha\|grade\|recortar … [--confirmar]` | 4 |
| **Prompt de clipe organizado** (quadro inicial → câmera em etapas → quadro final) + checagem da sequência (falta `fim`, movimento repetido entre vizinhos) | `scripts/prompt_clipe.py roteiro.json` (usado sozinho pelo `gerar_clipe_fal.py --roteiro`) | 4 |
| **Ativos do roteiro × biblioteca** (personagens, cenários, objetos; reaproveitar ou gerar, com custo) | `scripts/extrair_ativos.py ROTEIRO.md` → `ativos.json` | 2 |
| Kit de cenas reutilizáveis (tempos por palavra/batida, Cena, Ilustracao, Hora, Celular, Bolha, Toque, IconeRamo, CartoesUmPorVez, Virada, Robo, Assinatura, Legenda) | `templates/remotion-motion/kit.tsx` | 4 |
| Trilha GRÁTIS com clima por bloco (curioso, tensao, respiro, aberto, alegre, final), sintetizada no PC; cada bloco reinicia o compasso → revelação sempre na batida | `scripts/trilha_gratis.py --blocos "0:curioso,15.6:respiro,17.2:aberto" --duracao <s> -o assets/trilha.wav` (ou `--plano` do `trilha_ia.py`) | 3–5 |
| Vídeo sem a marca MinhaMarca (curiosidade/teste): kit sem "Peça uma demonstração" nem #MinhaMarca | `kit_publicacao.py … --sem-marca` | 5 |
| Trilha sonora por IA conforme o conteúdo (blocos de clima no tempo das falas; ElevenLabs Music ou ACE-Step no fal.ai; mostra o custo, `--confirmar`, `--recuperar`, `--opcoes N`) | `scripts/trilha_ia.py --falas falas.json --duracao <s> -o assets/trilha-ia.wav` → `mixar_comercial.py --trilha assets/trilha-ia.wav` | 3–5 |
| Checar retenção do vídeo pronto (P07, P10, P14, P53) | `scripts/verificar_retencao.py video.mp4 --falas falas.json --tipo anuncio\|historia -o retencao.md` | 5 (ponto 3) |
| Kit de publicação: capa, legenda, hashtags, comentário fixado, título do Shorts, roteiro da 1ª hora, versões | `scripts/kit_publicacao.py video.mp4 --briefing BRIEFING.md [--b video-B.mp4]` → `entrega/kit/` | 5 (entrega) |
| Ficha de métricas: anota 5 números (48h/7d) e ajusta a pontuação dos padrões usados | `scripts/metricas.py --video … --padroes P05,P07 --gancho horario` · `--listar` | 6 |
| Clipe animado por IA a partir da imagem da cena (pago, mostra o custo antes) | `scripts/gerar_clipe_fal.py` — fal.ai, Kling 2.5 Turbo Pro, chave `FAL_KEY` | 4 |
| Variações em lote de um vídeo pronto (abertura B, corte curto, 1:1/16:9, texto final) | `scripts/variantes_moviepy.py` — MoviePy | 5 |
| História interativa: roteiro.json → voz + imagens (rascunho grátis ou IA) + trilha de suspense + projeto | `scripts/montar_historia.py` + `templates/remotion-historia/` | 3–5 |
| Narração com a voz clonada do usuário (só se ele pedir) | VoiceStudio local (`http://localhost:3900/generate`, perfil da sua voz clonada) | 3 |
| Transcrição com tempo de cada palavra | `npx hyperframes transcribe <audio> --model small --language pt --json`, ou `editor.py transcrever` (faster-whisper local, aceita `--termos`) | 1, 3, 5 |
| Storyboard sincronizado | `scripts/beatmap.py` | 3 |
| **Motor de animação (padrão): Remotion** | Modelo `templates/remotion-base/` (6 tipos de cena + legenda + áudio) montado por `scripts/preparar_remotion.py`; regras em `/remotion-best-practices` | 4, 5 |
| Motor alternativo (só se o usuário pedir) | `/hyperframes` + `npx hyperframes` | 4, 5 |
| Imagens por IA (cenas, fundos, ilustrações, antes/depois) | **`scripts/gerar_imagem.py`** — API da OpenAI (GPT Image) com a chave do usuário em `OPENAI_API_KEY`; alternativa sem chave: `creative_generate_image` | 4 |
| Mídia: música, SFX, ícones, logos | `/media-use` | 4 |
| Estilos artísticos (óleo, aquarela, ukiyo-e…) | `/lemo-opuscar` — só se o usuário pedir um visual artístico | 4 |
| Editor local (cortar, limpar, legendar, vários cortes, reformatar) | `scripts/editor.py` com `python` (faster-whisper + ffmpeg) — guia em `references/editar.md` | 5 |
| Cortes, export, loudness, formatos | `/ffmpeg-skill` | 5 |
| Reconstruir um vídeo quadro a quadro | `/reverse-any-video` — só se pedir para *replicar* um vídeo (plano Pro); para aprender use o modo APRENDER | — |

---

## Etapa 1 — Análise e referências

1. **Carregue a memória (obrigatório):** `memoria/estado.md` (funções disponíveis e pendências), `memoria/perfil.md` (marca, voz, cores, público, termos, preferências fixas), `memoria/padroes.md` (o que funciona) e `memoria/historico.md` (o que já foi feito, notas recebidas).
   **Economia de tokens e dinheiro (2026-11-05):** leia `memoria/biblioteca.md` (personagens com ficha, cenas ilustradas, trilhas pagas, falas, composições de referência, dados fictícios) e o `RESUMO.md` (~20 linhas) do projeto parecido — **não** releia projetos inteiros. Reaproveite antes de gerar ou desenhar. Monte composições novas com `templates/remotion-motion/kit.tsx` + `motion.tsx` (só chamadas) em vez de escrever componentes do zero.
2. **Referências:** se o usuário mandou um vídeo viral, estude-o agora (`references/aprender-viral.md`). Se citou uma referência antiga, leia a ficha em `memoria/referencias/`. Sem referência, use os padrões Confirmados e Base de `padroes.md`.
3. **Material real:** levante o que existe (prints, logo, site, vídeos). Site: `npx hyperframes capture <url>`. Use sempre o real antes de desenhar.
4. **Briefing mínimo** — pergunte **numa só mensagem**, já com padrões sugeridos (ele só confirma):
   1. Sobre o quê / qual produto? 2. Para quem? 3. O que a pessoa deve fazer no fim (CTA)?
   4. Formato — padrão **vertical 9:16, 30–45 s** (Reels/TikTok/Shorts); 16:9 se for YouTube/site.
   Se `perfil.md` já responde, não pergunte de novo. "Faz do seu jeito" = siga os padrões.

## Etapa 2 — Roteiro e gancho

Siga `references/roteiro.md`.
1. **Gancho (0–3 s):** use o gancho aprovado na Etapa do gancho (`references/gancho.md` — 6 fórmulas pontuadas, o usuário escolhe entre as 3 melhores). Se a entrevista foi pulada, rode essa etapa agora. Ele aparece escrito na tela no frame 1 e se entende sem som (P07). Planeje também o **re-gancho aos 40–50%** (P14) e um **final que conversa com o começo** (P53).
2. **Linha narrativa:** 3 versões curtas só em texto; o usuário escolhe (ou você escolhe se ele pediu sem paradas).
3. **Roteiro final** em tabela `# | Fala | Tela | Dur.`, palavras-chave em `**negrito**` na Fala.
   Regra de tempo: PT-BR narrado ≈ **2,6 palavras/s** → 30 s ≈ 75–80 palavras.
   **Densidade dos cortes** (escolhida na entrevista, 18e): enxuto ≈ 65% dos cortes do padrão (planos longos, mais motion por cima) · padrão ≈ 1 corte a cada 2–3 s · detalhado ≈ 140% (corte a cada 1,5–2 s, ação quebrada em mais tomadas). Mais cortes = mais imagens; mostre quantas sobem.
4. Salve em `<projeto>/ROTEIRO.md`.
5. **Ativos do roteiro × biblioteca** (🆓): `python SKILL_DIR/scripts/extrair_ativos.py <projeto>/ROTEIRO.md` → lista personagens, cenários e objetos, marca o que reaproveitar da `memoria/biblioteca.md` e o custo só do que falta (`<projeto>/ativos.json`). Confira os "reaproveitar" e leve o total para o storyboard do ponto 1.

## Etapa 3 — Narração e storyboard

### 3a. Projeto
Pasta `<projeto>` com `ROTEIRO.md` e `assets/`. O projeto Remotion nasce na Etapa 4, em `<projeto>/remotion`.

### 3b. Narração (Gemini 3.8 Flash TTS — padrão)
1. Escreva `<projeto>/audio_request.json` (voz e estilo em `perfil.md` → Voz):
   ```json
   {
     "provider": "gemini",
     "tts_model": "gemini-3.8-flash-tts",
     "voice": "Puck",
     "lang": "pt",
     "style": "Locutor brasileiro de anúncio para redes sociais: animado, confiante, ritmo rápido, pausas curtas entre frases.",
     "lines": [{ "id": "narracao", "text": "<todas as falas do roteiro, sem **>" }],
     "bgm": { "mode": "none" }
   }
   ```
   Direções de voz vão em `style`, nunca no `text`. Não use `speed` (só 1). Uma única linha = áudio contínuo e natural.
2. Rode dentro do projeto:
   `node "<media-use>/audio/scripts/audio.mjs" --request ./audio_request.json --hyperframes . --out ./audio_meta.json --only tts`
   (`<media-use>` = `~/.claude/plugins/cache/hyperframes/hyperframes/<versão>/skills/media-use`; o `--hyperframes .` só indica a pasta onde salvar `assets/voice/` — o vídeo é feito no Remotion).
   Ainda não rodado neste computador: na 1ª vez confira se gerou o `.wav` e o `audio_meta.json`; se o motor de áudio falhar, chame a API do Gemini direto e transcreva com `editor.py transcrever`.
   Gera `assets/voice/narracao.wav` e `audio_meta.json` com `voices[].words` (tempo de cada palavra).
3. Confira: a linha tem áudio, `words` não está vazio, as direções do `style` não foram faladas. Erro de API = linha falha; nunca troque de voz sozinho.
4. Normalize: `ffmpeg -i assets/voice/narracao.wav -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 assets/narracao-norm.wav`.
- Voz clonada do usuário (só se pedir): VoiceStudio local — abra o app, `POST http://localhost:3900/generate` com `text`, `language=Portuguese (Brazil)`, `profile_id=<seu-perfil>` (CPU: ~3 min para 30 s); depois transcreva com `npx hyperframes transcribe ... --language pt` ou `editor.py transcrever`. **Sempre** português, senão o whisper traduz para inglês.

### 3c. Storyboard sincronizado com a voz
1. `python SKILL_DIR/scripts/beatmap.py audio_meta.json --roteiro ROTEIRO.md -o BEATS.json` (ou o `transcript.json` de outra fonte de áudio)
   → início/fim exato de cada cena, palavras-chave, pausas e grupos de legenda.
2. Monte o storyboard: para cada cena do `BEATS.json`, a coluna Tela do roteiro + a ação visual de cada palavra-chave no seu tempo. Regras em `references/sincronia.md`: cena entra na 1ª palavra da fala (−2 frames), palavra-chave ganha ação visual no tempo exato, cortes caem em pausas ≥ 150 ms.
3. Mostre o storyboard ao usuário em tabela curta (cena · tempo · o que aparece) antes de animar, se ele não pediu sem paradas.

## Etapa 4 — Geração das cenas (Remotion)

**Política de custo:** vídeo pago só com orçamento aprovado no chat (`contrato.py rotear` mostra o total). Anúncio/motion graphics: movimento em Remotion (grátis). **História com personagens: todo plano de atuação é animado de verdade** (ver "Animação de verdade"), nunca foto + zoom.

1. **Escolha o tipo de cada cena** (uma entrada por linha do roteiro, na mesma ordem do `BEATS.json`) e escreva `<projeto>/cenas.json`:
   | tipo | Para quê | Campos |
   | --- | --- | --- |
   | `titulo` | Gancho, frase de impacto, virada | `rotulo`, `linhas:[{texto, destaque}]` |
   | `imagem` | Ilustração/foto (IA ou real) com zoom lento | `src`, `zoom: in/out`, `pan: esquerda/direita/nenhum`, `escurecer`, `texto` |
   | `print` | Tela real do sistema numa janela, com punch-in | `src`, `texto`, `foco:{x, y, escala, na_palavra}` |
   | `celular` | POV de conversa no celular | `contato`, `mensagens:[{de, texto, na_palavra \| apos, alerta}]` |
   | `preto` | Pausa dramática | `texto` (opcional) |
   | `cta` | Chamada final, escolha A/B | `logo`, `titulo`, `opcoes:[{letra, texto}]`, `url` |
   - `na_palavra` amarra a mensagem ou o zoom ao momento exato em que a voz fala aquela palavra. Palavras em **negrito** no roteiro viram pulsos automáticos na cena.
   - Caminhos de `src`/`logo`: absolutos ou relativos ao `cenas.json` — o script copia para `public/`.
2. **Monte o projeto:**
   ```bash
   python SKILL_DIR/scripts/preparar_remotion.py <projeto>/remotion --beats BEATS.json --transcript <transcript ou audio_meta.json> --cenas cenas.json --voz assets/narracao-norm.wav --marca marca.json --legenda caixa
   ```
   1ª vez no projeto: `npm install` dentro de `<projeto>/remotion` (~3 min). `marca.json` = `{fundo, fundo2, primaria, texto, alerta}` (de `perfil.md`; sem ele usa azul-marinho + ciano do MinhaMarca).
3. **Precisa de algo que o modelo não tem** (gráfico, ícones animados, contador, transição especial): crie o componente em `<projeto>/remotion/src/` seguindo `/remotion-best-practices` (tudo por `useCurrentFrame()`, nada de animação CSS) e registre em `CENAS` no `Video.tsx`. Se ficar bom, leve para o modelo em `templates/remotion-base/` para os próximos vídeos.
4. Use o material real (prints, logo) em cada cena; desenhe só o que não existe. Visual artístico pedido → `/lemo-opuscar`.
5. **Imagens por IA** para o que não existe em print (cena de dor do gancho, pessoa/ambiente, ilustração, fundo da marca, antes/depois):
   ```bash
   python SKILL_DIR/scripts/gerar_imagem.py "<prompt>" -o assets/img/<cena>.png --formato vertical --qualidade medium            → só mostra o custo
   python SKILL_DIR/scripts/gerar_imagem.py "<prompt>" -o assets/img/<cena>.png --formato vertical --qualidade medium --confirmar  → gera (gasta)
   ```
   - Prompt em português, concreto: assunto, ambiente, luz, estilo (foto realista / ilustração 3D / flat), paleta da marca (`perfil.md` → Marca), "vertical". Sem texto dentro da imagem — o texto vem da animação.
   - `--modelo gpt-image-2` quando a imagem PRECISA de texto legível, tela de sistema ou infográfico.
   - `--ref <imagem>` (repita para várias) edita mantendo a cena: antes/depois, trocar fundo, manter o mesmo personagem entre cenas.
   - **Personagem novo → ficha em várias vistas** (rosto em close + corpo frente/lado/costas + 6 expressões, 1 imagem ~US$ 0,05): `scripts/ficha_grade.py ficha -o assets/ilustrado/ficha-<nome>.png --descricao "…" [--ref esboço.png] --confirmar`. Essa ficha é a única identidade nas imagens seguintes (`--ref`).
   - **Vários ângulos do mesmo momento → grade 3×3** (9 câmeras numa imagem ~US$ 0,05 em vez de 9 × 0,05, recorte automático): `scripts/ficha_grade.py grade -o assets/ilustrado/g1.png --ref ficha.png --momento "…" --confirmar` → `g1-01-geral.png … g1-09-plongee.png`. Quadros pequenos (~340×510): bons para storyboard, quadro inicial de clipe e fundo com zoom leve; plano "herói" em tela cheia → refazer só ele com `gerar_imagem.py --ref ficha --ref g1-0X.png --confirmar`.
   - **Clipes com prompt organizado**: no `roteiro.json`, `"clipe": {duracao, assunto, inicio, etapas:[{camera, acao, ate}], fim}` (vocabulário de câmera em `scripts/prompt_clipe.py`). O `fim` tem de bater com o quadro seguinte do storyboard; `gerar_clipe_fal.py --roteiro` recusa a sequência (sem gastar) se faltar `fim` ou se dois planos vizinhos repetirem o movimento. Conferir antes: `python scripts/prompt_clipe.py roteiro.json`.
   - `--fundo transparent` para recortes (objetos que entram animados por cima da cena).
   - Qualidade: `low` para testar ideias (centavos), `medium` padrão, `high` só para a imagem principal do gancho. `--n 2–4` quando o usuário quiser escolher.
   - Olhe cada imagem (Read) antes de usar: mãos, rostos, texto torto, logos inventados → gere de novo ou edite com `--ref`. Nunca use marca de terceiros.
   - Na cena, dê vida à imagem parada: zoom lento (Ken Burns), parallax em camadas, entrada de elementos recortados.
   - O `.json` ao lado de cada imagem guarda prompt e modelo — reaproveite para manter o estilo entre cenas.
6. Aplique os padrões de `memoria/padroes.md` (gancho visual, ritmo de trocas, movimento) — anote os ids aplicados.

## Etapa 5 — Montagem e revisão

1. **Legendas:** já vêm no projeto (palavra a palavra, grupos do `BEATS.json`). `--legenda caixa` = caixa na cor da marca atrás da palavra falada (P22); `cor` = só a palavra colorida; `nenhuma`. Altura: `--altura-legenda` (0,64 padrão; suba se cobrir o assunto).
2. **Áudio:** voz pelo `--voz`; trilha por `--musica` (volume `--volume-musica 0.12`); efeitos sonoros em `sfx:[{src, inicio}]` no `video.json` (arquivos em `public/`, via `/media-use` — só fontes gratuitas).
3. **Checagem:** dentro de `<projeto>/remotion`: `npx tsc --noEmit` (sem erros) → quadros-chave de cada cena:
   `npx remotion still Video out/f<N>.png --frame=<N> --scale=0.5` (N = segundo × 30), junte com `ffmpeg … hstack` e olhe (Read). Confira: gancho legível no 1º segundo, nada fora da área segura, legenda não cobre o assunto, cada palavra-chave tem sua ação, sem texto cortado.
4. **Prévia:** mostre a folha de quadros ao usuário; para ver em movimento: `npx remotion studio` (abre no navegador, dá para mexer nos tempos). **Antes do vídeo inteiro**, renderize só o começo para aprovar o estilo: `npx remotion render Video out/previa.mp4 --frames=0-150`.
5. **Render:** `npx remotion render Video out/<nome>.mp4` (~2 min para 30 s; longo → em background). Formatos de plataforma com `editor.py reformatar` (H.264, AAC, −14 LUFS). Entregue o caminho completo.
5b. **Trilha conforme o conteúdo** (se escolhida na entrevista, pergunta 16b): `python scripts/trilha_ia.py --falas falas.json --duracao <s> --contexto "<dor → solução, onde fica a virada>" -o assets/trilha-ia.wav` mostra o plano de blocos (clima, BPM, instrumentos) e o custo **sem gastar**; ajuste o `assets/trilha-ia.wav.plano.json` para que cada troca caia num corte (ex.: a virada no início da tela preta) e gere com `--plano … --confirmar` (padrão ElevenLabs; `--modelo ace --opcoes 3` para comparar barato). Mostre o custo e espere o ok antes do `--confirmar`. Envie a trilha ao usuário para ouvir junto com o ponto 3.
5c. **Som profissional + batida** (padrão, grátis): `python scripts/batida.py <trilha>` (com trilha de uma peça só, use `--cortes` para conferir as trocas de cena e `--drop-em <revelação>` para alinhar) → `python scripts/som_pro.py --sfx sfx.json --trilha <trilha> --revelacao <segundo da virada> --duracao <s>` → mixe com `mixar_comercial.py --sfx assets/som/sfx-pro.json --trilha assets/som/trilha-pro.wav --volume-trilha 0.25` (trilha por IA vem a −20 LUFS; a sintetizada usa 0.15). **Meça a margem da voz** (fala ≥ 9 dB acima das pausas — regra do usuário) e baixe o `--volume-trilha` até passar. Com ACE em blocos, cada bloco tem seu próprio andamento: só a revelação é conferida na batida.
5d. **Inspetor (antes do espectador):** `python scripts/inspetor.py filme roteiro.json entrega/<nome>.mp4` — fala × roteiro em cada plano, legenda × áudio, movimento × contrato. ❌ = refazer só aquele plano e remontar.
6. **Espectador + retenção (antes do ponto 3 e de toda amostra):** `python scripts/espectador.py out/<nome>.mp4 --briefing BRIEFING.md -o entrega/espectador.md` — corrija o que o impaciente e o crítico apontarem antes de mandar ao usuário. Depois: `python scripts/verificar_retencao.py out/<nome>.mp4 --falas <falas com palavras> --tipo anuncio|historia -o entrega/retencao.md`. Cada ⚠️ vira ajuste (corte, zoom mais forte, onomatopeia, elemento entrando) ou uma nota no storyboard do ponto 3 explicando por que fica assim.
7. **Kit de publicação (na entrega):** `python scripts/kit_publicacao.py entrega/<nome>.mp4 --briefing BRIEFING.md [--b <abertura B>]` → `entrega/kit/` (capa, `KIT.md` com legenda, hashtags, comentário fixado, título do Shorts e roteiro da 1ª hora). Mostre a capa e o `KIT.md` ao usuário; nada é postado por você.
8. **Alterar uma cena só** ("deixa a cena 3 mais dinâmica"): mude a entrada dela no `cenas.json` (ou o componente), rode `preparar_remotion.py` de novo e renderize — as outras cenas ficam iguais.
- Vídeo gravado ou pronto (modo EDITAR): cortar, limpar, legendar, vários cortes e reformatar em `references/editar.md`.

## Etapa 6 — Aprendizado (sempre melhorando)

**Ao entregar (obrigatório):** rode `custos.py relatorio` e coloque o total no recado ao usuário; escreva o `RESUMO.md` do projeto (~20 linhas: formato, estrutura, tempos-chave, arquivos, correções do usuário) e acrescente em `memoria/biblioteca.md` o que ficou reaproveitável (personagens, cenas, trilhas, componentes). Depois acrescente em `memoria/historico.md` (modelo no próprio arquivo): data, nome, objetivo, formato, duração, gancho, padrões aplicados (ids), referência usada, caminho do arquivo, "métricas: pendente". Peça ao usuário, em uma linha, para contar depois como foi (views, retenção, comentários).

**Quando o usuário der feedback ou números:**
1. Números (48 h e 7 dias depois de postar): rode `scripts/metricas.py` com os 5 números (views, retenção 3 s, % assistido, compartilhamentos, comentários), os ids dos padrões usados (do `historico.md`) e a fórmula do gancho. Ele grava em `memoria/metricas.json`, escreve no `historico.md` e, no número de 7 dias, ajusta a pontuação em `padroes.md` (+1 se ganhou em ≥ 2 de 3 sinais contra a mediana dos vídeos anteriores, −1 se perdeu). `--listar` mostra qual fórmula de gancho segura mais em 3 s. Pergunte os números um por vez.
2. Opinião sem números: registre em `historico.md` na entrada do vídeo e ajuste à mão a pontuação dos padrões que ele citou.
3. Feedback explícito ("não gostei da legenda amarela", "fala mais rápido") vira regra em `perfil.md` → **Preferências fixas** — essas vencem qualquer padrão.
4. Padrão com pontuação ≤ −2 vai para **Evitar**. Padrão visto em ≥ 3 referências virais ou com pontuação ≥ +3 vira **Confirmado**.
5. Diga ao usuário em 2–3 linhas o que aprendeu e o que muda no próximo vídeo.

## Regras

- Aprender com referências = extrair **estrutura e técnica** (tempo de gancho, ritmo, tipo de legenda, arco). Nunca copiar roteiro, marca, personagens ou imagens de terceiros.
- Mostre o produto real; desenhe só o que não existe.
- Não pergunte o que dá para decidir. Pergunte o que só o usuário sabe.
