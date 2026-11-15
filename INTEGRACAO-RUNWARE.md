# INTEGRAÇÃO RUNWARE — SKILL `criador-video`

**Versão:** 1.0 — 06/11/2026  
**Destino:** Codex / agente de desenvolvimento com acesso ao repositório local  
**Objetivo:** Adicionar a Runware como fornecedora PRINCIPAL de imagens e vídeos da skill `criador-video`, reaproveitando sua orquestração, roteador de custos, cache, bíblia de produção, inspeção de qualidade e montagem Remotion, sem quebrar os provedores anteriores.

> **INSTRUÇÃO AO CODEX:** Este documento é uma especificação de IMPLEMENTAÇÃO, não uma descrição para futura avaliação. Primeiro inspecione os arquivos locais e faça um plano de mudanças curto; depois implemente, execute testes automatizados SEM COBRANÇA e reporte os resultados. Não peça confirmação para decisões técnicas rotineiras. **Não execute gerações pagas sem orçamento/autorização do projeto e credenciais válidas.** Não diga que integrou algo que ainda não foi testado.

---

## 1. Contexto real e escopo

- Skill principal no Windows: `~/.claude\skills\criador-video\`. Em instalações alternativas, verificar `~/.agents\skills\criador-video\` e descobrir qual cópia está ativa. **Não modificar uma cópia inativa nem sobrescrever mudanças de outra instalação.**
- Projetos: `%USERPROFILE%\estudio-video\projetos\<data>-<slug>\` ou caminho indicado pelo usuário.
- A skill já tem, entre outros: `SKILL.md`, `scripts/catalogo.py`, `scripts/roteador.py`, `scripts/custos.py`, `scripts/orquestrador.py`, `scripts/producao.py`, `scripts/gerar_imagem.py`, `scripts/gerar_clipe_fal.py`, `scripts/contrato.py`, `scripts/prompt_clipe.py`, `scripts/inspetor.py`, `scripts/movimento.py`, `scripts/continuidade.py`, `scripts/storyboard.py`, `scripts/montar_historia.py` e templates Remotion. Verificar existência e nomes reais antes de alterar.
- A skill possui a bíblia `<projeto>/producao.json`: tomada, personagem, cenário, referências, versões de imagens/clipes, status e custos. **Preservar este contrato e migrá-lo de modo compatível**, não inventar uma segunda fonte de verdade.
- Existe proposta prévia `ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md` e auditoria consolidada `AUDITORIA_GERAL_CRIADOR_VIDEO.md`: localizar e observar, se presentes. Esta integração é um **adaptador adicional**, não substituição do roteador.
- Objetivo criativo: vídeo com **movimento de personagens** (ação, reação, corpo, fala), continuidade entre takes e storyboard, não mera animação de pan/zoom. Motion graphics são adequados a títulos, telas, dados e inserts.
- **Fora do escopo:** alterar TTS Gemini ou voz clonada sem necessidade; reescrever o projeto; criar painel; treinar modelo próprio; prometer uso ilimitado/gratuito; modificar MinhaMarca.

### Resultado desejado

Fluxo autônomo para escolhas técnicas: `roteiro → contrato e decupagem → storyboard → imagem-chave → continuidade → vídeo por Runware → Watch/inspetor → refação seletiva → cor/áudio → Remotion → inspeção do filme → entrega`. Aprovações explícitas e tetos financeiros já configurados no projeto continuam prevalecendo. O **Watch aprova tecnicamente apenas com evidência suficiente**, não substitui aprovação humana obrigatória na configuração existente.

---

## 2. API Runware: informações verificadas

**Endpoints/documentação oficiais (consultados em 06/11/2026):**

- Autenticação: https://runware.ai/docs/models-api/authentication
- Visão geral: https://runware.ai/docs/models-api/introduction
- Catálogo: https://runware.ai/docs/models
- Busca de modelos: https://runware.ai/docs/models-api/model-search
- Esquemas de cada modelo: https://runware.ai/docs/models-api/model-schemas
- Imagem para vídeo: https://runware.ai/docs/learn/image-to-video
- Polling: https://runware.ai/docs/models-api/task-polling
- Webhooks: https://runware.ai/docs/models-api/webhooks
- Preços/custos: https://runware.ai/docs/models-api/pricing
- Gestão de conta e saldo: https://runware.ai/docs/models-api/account-management
- Armazenamento de mídia: https://runware.ai/docs/models-api/media-storage
- SDK Python: https://runware.ai/docs/tools/python/models

**Transporte REST confirmado:** `POST https://api.runware.ai/v1` com `Authorization: Bearer <RUNWARE_API_KEY>`, `Content-Type: application/json`, corpo **array de objetos**, um por tarefa. Cada tarefa tem `taskType`, `taskUUID` (UUID v4) e seus parâmetros. O endpoint serve a `imageInference`, `videoInference`, `modelSearch`, `getResponse`, `accountManagement`, `mediaStorage` etc., conforme seus contratos. A Runware também recomenda WebSockets; neste projeto, começar pelo SDK Python ou REST conforme a arquitetura existente, sem criar ambas as integrações ao mesmo tempo.

**IMPORTANTE:** os modelos usam identificadores AIR exatos (`criador:modelo@versao`) e possuem **limites diferentes de duração, resolução, modo, entrada, áudio e preço**. Não transportar cegamente os parâmetros de um modelo para outro. Validar o schema e os modos (`x-modes`) correspondentes antes da chamada. O AIR usado no exemplo da API não é uma indicação automática do melhor modelo comercial.

### Exemplos de referência para o adaptador (não fazem chamadas reais)

Imagem por texto:

```json
[
  {
    "taskType": "imageInference",
    "taskUUID": "39d7207a-343e-4198-9c40-ef6d302cadb3",
    "model": "runware:z-image@0",
    "positivePrompt": "Uma sala de trabalho ilustrada, luz cinematográfica",
    "width": 1024,
    "height": 1024,
    "includeCost": true
  }
]
```

Vídeo com primeiro quadro, **modelo e parâmetros ilustrativos de documentação oficial, revalidar schema antes da execução**:

```json
[
  {
    "taskType": "videoInference",
    "taskUUID": "a770f077-f413-47de-9dac-be0b26a35da6",
    "model": "minimax:h3@0",
    "positivePrompt": "O personagem pega o celular, lê a mensagem, franze a testa e reage com preocupação; câmera estável.",
    "duration": 8,
    "resolution": "768p",
    "inputs": {
      "frameImages": [
        { "image": "UUID_OU_URL_VALIDO_DA_IMAGEM", "frame": "first" }
      ]
    },
    "deliveryMethod": "async",
    "includeCost": true
  }
]
```

- Para último quadro, incluir segundo item `frame: "last"` **somente** quando o modelo declarar suporte. Para algumas famílias, 2 imagens são primeiro/último automaticamente; preferir esquema explícito quando aceito.
- `inputs.referenceImages` é para referências gerais de aparência/estilo, **não** equivale ao primeiro quadro; `inputs.frameImages` fixa quadros. Alguns modelos proíbem misturar estes modos. Verificar `x-modes`.
- Alguns modelos exigem `width`/`height`; outros `resolution`. Não enviar ambos ou `settings` opcionais sem validar schema.
- Para vídeo, preferir `deliveryMethod: "async"`, guardar `taskUUID`, fazer polling por `getResponse` com backoff exponencial e/ou usar webhook em servidor acessível. **Nunca reenviar uma geração só porque uma resposta demorou:** primeiro consultar a tarefa original, pois reenviar pode cobrar duas vezes.
- Incluir `includeCost: true` para obter custo real quando disponibilizado; baixar o arquivo gerado imediatamente e armazenar localmente. URLs de mídia têm retenção padrão limitada (documentação menciona 7 dias); não tratá-las como armazenamento definitivo.
- Consultar `accountManagement` / `getDetails` para `balance.amount`, `balance.freeBalance` e moeda, quando disponíveis. Saldo não substitui autorização de gasto do projeto.

---

## 3. Arquitetura e mudanças esperadas

**Reaproveitar componentes já presentes.** Criar novas pastas apenas se não existir uma estrutura equivalente. Layout lógico proposto:

```text
criador-video/
  SKILL.md
  INTEGRACAO-RUNWARE.md
  scripts/
    catalogo.py                 # catálogo multi-provedor; modelos/capacidades Runware
    roteador.py                 # Runware preferencial; fal.ai e outros como fallback
    custos.py                   # reserva, gasto real, teto, relatórios, cache
    orquestrador.py             # coordena takes, jobs, reintentos e gates
    producao.py                 # versões, hashes e proveniência
    gerar_imagem.py             # usa provider genérico (Runware/fallback)
    gerar_clipe_fal.py          # manter CLI legada, delegar à interface genérica
    inspetor.py                 # integrar Watch sem aprovações falsas
    [demais arquivos existentes]
  providers/                    # somente se não existir pasta equivalente
    base.py                     # contratos comuns
    runware_provider.py         # NOVO: REST/SDK, validação, polling, download
    fal_provider.py             # encapsulamento legado, se necessário
    registry.py                 # seleção do provider
  config/
    providers.yaml              # AIRs e capacidades, preços com fonte/data
    routing.yaml                # política, limites, fallback
  tests/
    test_runware_provider.py
    test_runware_router.py
    test_runware_budget.py
    test_runware_inspector.py
    test_runware_regression.py
```

### Interfaces internas obrigatórias

Criar/reutilizar **interface única** entre gerador e provedor:

```python
# Exemplo conceitual; alinhar aos tipos atuais do projeto.
@dataclass
class GenerationRequest:
    project_id: str
    shot_id: str
    kind: str                # image | video
    mode: str                # text_to_image | image_to_image | text_to_video | image_to_video
    positive_prompt: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    resolution: str | None
    first_frame_path: str | None
    last_frame_path: str | None
    reference_paths: list[str]
    constraints: dict      # identidade, ação, beats, lip-sync, qualidade etc.
    max_cost_usd: float
    model_air: str | None

@dataclass
class GenerationResult:
    status: str            # success | failed | pending | uncertain
    provider: str
    model_air: str
    task_uuid: str | None
    local_path: str | None
    cost_usd: float | None
    input_hash: str
    output_hash: str | None
    error_code: str | None
```

A interface não pode confundir `pending/uncertain` com `failed` nem com `success`. `cost_usd=None` significa desconhecido, **não US$ 0**.

### Responsabilidade por arquivo

1. `providers/runware_provider.py`: autenticação via variável de ambiente, serialização validada, envio, polling, recuperação de jobs, download seguro, erros tipados, leitura de saldo/custos, gestão de mídias de entrada e telemetria.
2. `scripts/catalogo.py`: combinar catálogo histórico com Runware; manter cache de AIRs/modelos, capacidade de `first/last frame`, duração e resolução por modelo. Resolver preços por fontes oficiais e registro datado; falhar fechado quando desconhecidos ou não comprovados.
3. `scripts/roteador.py`: **Runware como preferido**, mas não obrigatório quando a cena exige capacidade ausente ou outro provedor oferece melhor custo total para igual qualidade. Suportar `runware_primary`, `best_value`, `lowest_cost`, `manual` e fallback. Histórico deve separar provedor e modelo.
4. `scripts/custos.py`: estimar com tarifa em vigor e multiplicadores (segundos cobrados, resolução, áudio, qualidade), registrar reserva atômica por geração/lote e reconciliar com `cost` do resultado. Usar saldo real de conta apenas como verificação adicional. **Não permitir overspend com jobs paralelos**.
5. `scripts/gerar_imagem.py` e `scripts/gerar_clipe_fal.py`: adaptadores que chamam a interface. CLI existente deve continuar funcional; eventual alias `gerar_clipe.py` pode ser criado sem remover o comando antigo.
6. `scripts/orquestrador.py`: retomar tarefas pendentes; jamais disparar duplicatas após timeout; registrar o status do Watch/continuidade e impedir montagem quando faltarem inspeções.
7. `scripts/producao.py`: versão/hash da referência de personagem, imagem, prompt, contrato, clipe e inspeção. Se a imagem trocar, invalidar clipe e verificações descendentes (sem apagar os originais).
8. `scripts/inspetor.py` e `scripts/movimento.py`: conectar o Watch como leitor semântico; movimento por pixel é só triagem e não prova ação correta.
9. `SKILL.md`: indicar Runware como principal, custos e política de autonomia, sem apagar as demais orientações atuais.

---

## 4. Roteador inteligente e seleção de modelos

**Não fixar como padrão um modelo porque ele apareceu em ranking/preço antigo.** Selecionar mediante critérios testáveis por tomada:

1. Compatibilidade de modalidade: imagem por texto, edição por referência, texto→vídeo, imagem→vídeo, primeiro/último quadro, video→video, lip-sync quando necessário.
2. Capacidade para **duração exata**, proporção `16:9` ou `9:16`, resolução, áudio, sem violar limites do modelo.
3. Qualidade mínima observada para `acao`, `reacao`, `fala`, `interacao_fisica`, `estabelecimento`, `titulo` (histórico de aprovação por tipo).
4. Estimativa de **custo por tomada APROVADA**, incluindo refações, e não apenas preço de uma tentativa.
5. Saldo e orçamento **reservado** disponível; disponibilidade/latência, taxa de erro e cache por entrada.
6. Escolher Runware por padrão dentro dos candidatos que satisfazem tudo; fallback fal.ai ou outro adaptador **somente** quando justificado, autorizado e dentro do teto.

**Custo esperado** (fórmula orientadora): `custo_unitário / max(taxa_de_aprovação_estimada, piso_estatístico)`. Com pouca amostra, usar taxa conservadora configurável e sinalizar `baixa_confianca`. Registrar preço por imagem, segundo, duração arredondada, resolução e fatores cobrados; nunca supor proporcionalidade linear quando a cobrança é por faixa de duração.

**Perfis:** `economico` (padrão: menor custo atendendo qualidade mínima), `equilibrado` e `premium`. Suportar políticas previamente existentes no roteador, inclusive `free_first`, **sem interpretar saldo promocional como gratuidade ilimitada**. Usar `model: "auto"` da Runware só quando política, restrições e verificação de custo forem compatíveis; para orçamento estrito preferir AIR explícito para previsibilidade.

### Regras anti-desperdício

- **Cache** pelo hash de: provider, AIR, schema/versão, prompt normalizado, parâmetros, duração, referências/arquivos, seed e identidade do personagem. Reutilizar resultado idêntico **sem consumir API**.
- **Preview primeiro:** storyboard local gratuito (quadros/contratos), imagens econômicas, e vídeo de teste compatível com a cena; gerar versão final só quando houver evidência de viabilidade.
- Limitar reiterações por take: padrão sugerido 2 refações automáticas após a primeira geração; teto configurável por projeto.
- Se erro for `auth`, `saldo insuficiente`, `modelo inválido`, `quota`, `schema` ou `orçamento`, não insistir cegamente; corrigir parâmetro ou bloquear com diagnóstico.
- Se erro for transitório, retry com backoff/jitter e **mesmo job lógico**, consultando status antes de novo envio.
- Não dividir take de 10 s em dois de 5 s sem avaliar continuidade/cortes; preservar quadro final/inicial entre segmentos quando escolhido.
- Animação real para personagem quando o contrato exige ação; zoom/pan sobre foto não pode aprovar take de atuação.

---

## 5. Orçamento, saldo e autorização

### Política obrigatória

- **Nenhuma geração paga sem teto de projeto previamente aprovado** conforme fluxo atual. A autorização é por projeto e cobre até o limite; não pedir permissão a cada take dentro dele.
- Criar reserva transacional **antes** de executar um lote paralelo. Saldo liberado = `teto_aprovado - valor_pago - reservas_ativas`. Conferir a soma dos jobs, não cada job isolado.
- Registrar `planned`, `reserved`, `submitted`, `processing`, `succeeded`, `failed`, `unknown_billing`, `reconciled` e evitar cobrança duplicada por reinício.
- Não liberar reserva diante de timeout com estado **desconhecido**. Consultar `getResponse` / estado remoto e, se necessário, conciliar consumo com `accountManagement` antes de reexecutar.
- Guardar `estimated_cost_usd`, `actual_cost_usd`, `source`, `price_checked_at`, `freeBalance` e `provider_task_uuid` por tomada/versão. Custo real vem de `includeCost` ou reconciliação oficial; se indisponível, manter como desconhecido.
- Se custo previsto superar teto da operação ou projeto, não trocar silenciosamente para um modelo mais caro: devolver `requires_budget_approval` com alternativas. Não ultrapassar teto sem consentimento.

### Exemplo de configuração inicial (valores SUGERIDOS; não representam preços de API)

```yaml
runware:
  enabled: true
  priority: 1
  key_env: RUNWARE_API_KEY
  transport: rest
  prefer_async_video: true
  request_timeout_seconds: 45
  poll_initial_seconds: 2
  poll_max_seconds: 20
  max_poll_minutes: 20
  include_cost: true
routing:
  strategy: runware_primary
  quality_profile: economico
  max_regenerations_per_shot: 2
  fallback_order: [runware, fal]
  unknown_price_policy: block
budget:
  require_project_authorization: true
  reserve_before_submit: true
  block_overspend: true
  max_parallel_paid_jobs: 2
inspection:
  preferred: watch_video
  fail_closed_when_visual_not_verified: true
  auto_retry_rejected_shot: true
```

**Atenção:** estes limites são parâmetros internos de implementação, não valores de mercado e nem garantia de que determinada geração termine em 20 minutos. Para polling, o timeout local deve persistir o job e possibilitar retomada posterior sem reenvio; não significa cancelamento remoto nem autorização para nova cobrança.

---

## 6. Watch + inspeção automática de cada take

**Não assumir que o servidor Watch está instalado/ligado ou que seu nome exato é conhecido.** Localizar configuração MCP e testar descoberta de ferramentas. Se `watch_video` estiver disponível, mapear a assinatura real, tipos de entrada e limites. Não fabricar chamadas ou resultados.

### Pipeline obrigatório por clipe

1. Verificar existência do MP4, integridade básica (`ffprobe`), duração, fps, dimensão, áudio, tamanho e hashes.
2. Rodar Watch (`watch_video`) com o **caminho real acessível ao servidor**; quando for aceito texto, usar português do Brasil na análise/transcrição. Inspecionar **take completo**, não apenas imagem isolada.
3. Exigir análise com timestamps: `inicio`, `fim`, `observado`, `esperado`, `gravidade`, `correcao`, `evidencia`.
4. Comparar contrato de direção e beats com o vídeo: movimentos de rosto/corpo, ações, reação, física, continuidade visual, mãos, objetos, enquadramento, identidade, sincronismo boca/voz, texto/legendas, quadros iniciais/finais.
5. Acrescentar `scripts/movimento.py`, `scripts/continuidade.py` e testes de áudio existentes; comparar resultado semântica × métricas objetivas.
6. Classificar como **`aprovado`**, **`reprovado`** ou **`nao_verificado`**. Resultado parcial, erro do Watch, falha de transcrição, ausência de quadro de referência ou falta de evidência => **`nao_verificado`**, nunca aprovação tácita.
7. Se `reprovado`, converter achados em **prompt de correção apenas daquele take**, salvar versão e refazer enquanto houver orçamento/tentativas. Se `nao_verificado`, tentar outro inspetor habilitado ou enviar ao ponto de revisão humana/configurado — sem gerar novamente só por indisponibilidade da inspeção.
8. Registrar relatório legível `<projeto>/entrega/inspecao/<shot_id>-<versao>.json` e resumo `.md` com timestamps e critérios.

### Critérios mínimos para aprovação automática técnica

- Todas as ações obrigatórias (`beats`) executadas no intervalo esperado, inclusive **reação após ação**.
- Identidade e figurino de personagens compatíveis com ficha + cena anterior; ausência de mudanças absurdas em objetos.
- Duração, orientação e resolução dentro do contrato; sem cortes prematuros/congelamentos indevidos.
- Se há diálogo em quadro: lip-sync e áudio verificados. Para narração off, não exigir boca sincronizada.
- Se há fala curta: transcrição deve corresponder integralmente ao texto obrigatório (normalização leve de pontuação é aceitável; palavras trocadas não).
- Problemas graves de anatomia, continuidade, legendas ou ação ausente bloqueiam a montagem.
- **Não classificar mera variação de pixels, zoom/pan ou mudança de luz como atuação real.**

### Relação com as aprovações do usuário

- **Autonomia técnica:** após aprovação de orçamento e definição da política de revisão do projeto, Watch e inspetor podem aprovar/refazer takes sem interromper o usuário.
- **Checkpoints do SKILL.md:** storyboard/pontos de conferência e autorizações explícitas permanecem obrigatórios nos projetos em que essa regra está ativa. Se o usuário já tiver optado expressamente por modo autônomo, registrar a escolha e usar `review_policy=automatic_internal` para inspeções técnicas, sem desativar proteções financeiras.
- **Fallback da inspeção:** se Watch não estiver disponível, usar outro analisador multimodal existente e/ou folha de quadros para revisão; marcar `nao_verificado` até inspeção suficiente. Informar falha concreta do servidor no relatório.

---

## 7. Segurança, dados e recuperação

- Obter chave no painel Runware: https://runware.ai/ . Usuário configura em variável de ambiente `RUNWARE_API_KEY`; **NUNCA** colocar chave em `SKILL.md`, exemplos, `producao.json`, histórico, commits, print ou mensagem de erro. `.env` local no `.gitignore`, permissões restritas.
- Não sincronizar credenciais ou anexos sigilosos entre projetos/tenants. Projetos MinhaMarca e da Exemplo não autorizam vazamento de dados ou uso de chave alheia.
- Não confiar em URLs arbitrárias retornadas ou recebidas de entradas: validar protocolo HTTPS, domínio/allowlist quando cabível, tamanho e MIME, restringir redirecionamentos, impedir SSRF e path traversal.
- Para entrada local, usar `mediaStorage` se necessário e guardar `mediaUUID`; evitar reupload das mesmas referências e excluir mídia temporária conforme política de retenção.
- Persistir job antes do envio, manter UUID e estado remoto, logs estruturados com `project_id`, `shot_id`, `task_uuid`, `provider`, `model_air`, `estimated_cost`, `actual_cost`, `attempt`, `status`, tempos e motivo; nunca logar prompt com dados sensíveis sem política explícita.
- Se ocorrer crash após submissão: **retomar o job existente** via UUID. Se cobrança/resultado ficar indeterminado, parar e reconciliar; não começar outra tarefa faturável automaticamente.
- Webhook é opcional para instalações com endpoint HTTPS acessível; em desktop local, usar polling. Caso use webhook, autenticar sua origem conforme a documentação e não supor cabeçalho de assinatura inexistente.

---

## 8. Testes mínimos e qualidade de regressão

**Primeira rodada sem consumo de créditos:** mocks de HTTP/SDK e fixtures gravadas, testes com `pytest` ou test runner já adotado. **Não executar API paga no CI.**

| Caso | Resultado exigido |
|---|---|
| Sem `RUNWARE_API_KEY` | Diagnóstico claro; nenhum request remoto pago |
| AIR inválido / resolução ou duração não suportada | Rejeição na validação prévia; custo zero por submissão |
| Imagem simples (mock) | Envia `imageInference`, salva asset e `cost` quando presente |
| Image-to-video com primeiro e último quadro | Só aceita os modos permitidos pelo schema do modelo |
| Job retorna `processing` | Persiste `taskUUID` e consulta `getResponse`; **não reenvia** |
| Timeout + reinício local | Retoma job; não duplica cobrança |
| Dois jobs paralelos ultrapassam o mesmo saldo | Reserva atômica bloqueia o segundo/lote |
| Cache idêntico | Retorna arquivo local e registra custo novo `0` por cache hit |
| Custo efetivo desconhecido | Nunca transforma `None` em zero nem libera saldo arbitrariamente |
| Saldo promocional esgotado | Não assume grátis; verifica limite de projeto antes de cobrar |
| Watch falha/está ausente | `nao_verificado`, não `aprovado` |
| Vídeo com zoom e personagem estático | Reprova quando contrato exige movimento de atuação |
| Nova imagem substitui a anterior | Invalida clipe, continuidade e inspeção derivados |
| Render tenta usar clipe não verificado | Montagem bloqueada com erro rastreável |
| CLI/skill atual com fal.ai | Continua operacional via fallback compatível |
| Logs com chave ou token | Teste de sanitização detecta e falha |

**Teste piloto com cobrança, somente após aprovação específica:** um projeto de 3 takes (1 ação/reação corporal, 1 fala em quadro/lip-sync, 1 interação física/objeto) + 2 imagens de referência por personagem. Registrar diferenças de qualidade/custo/latência entre Runware e fallback **na mesma duração, resolução, exigência e critério de avaliação**. Se um modelo não sustenta a cena, não promovê-lo como padrão apenas por preço baixo.

### Correções da auditoria anterior que são BLOQUEANTES para o rollout

Garantir que a integração não reintroduza nem ignore os problemas P01–P12 e os demais achados pertinentes: contrato incompleto, falso `aprovado` do inspetor, aprovação sem verificação, substituição de imagem sem invalidar clipe, soma incorreta de jobs paralelos, divergência de legenda ignorada e custos/duração incompatíveis. **Não declarar o sistema pronto se estes gates ainda puderem ser contornados.**

---

## 9. Implantação gradual — ordem exata

### Fase A — sem gastos

1. Identificar pasta ativa, ler `SKILL.md`, `ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md` e `AUDITORIA_GERAL_CRIADOR_VIDEO.md` quando presentes; inventariar chamadas a fal.ai e comandos CLI atuais.
2. Criar branch/backup e testes de comportamento existente. Confirmar Python/venv/dependências; não trocar versões globalmente sem necessidade.
3. Introduzir interface de providers e `runware_provider.py`; adicionar parser de resposta, validação de schema, controle assíncrono e download.
4. Integrar catálogo e roteador com Runware preferencial, preservando fal.ai. Adicionar custos e reservas transacionais.
5. Integrar `gerar_imagem.py` e `gerar_clipe_fal.py` sem quebrar interfaces. Testar todos os fluxos via mock.
6. Integrar Watch ao `inspetor.py` e corrigir gates (`aprovado/reprovado/nao_verificado`) e invalidação de versões. Rodar testes de regressão.
7. Atualizar `SKILL.md`, README/configuração e `.env.example` **sem segredo**. Apresentar diff e comandos de teste.

### Fase B — smoke test autorizado

8. Validar chave e saldo com operação não gerativa; buscar modelos/capacidades e estimativas atualizadas, sem gastar.
9. **Depois do teto financeiro explicitamente autorizado:** produzir 1 imagem e 1 take curto de teste; confirmar custos reais e salvamento local; inspecionar com Watch.
10. Executar piloto das 3 tomadas, comparar modelos e ajustar política de qualidade/preço.

### Fase C — ativação

11. Definir Runware como principal nos projetos novos; manter fallback, feature flag de rollback e logs.
12. Atualizar memória viva da skill somente depois de passar testes e registrar modelos/custos aprovados pelo piloto.

### Entregáveis obrigatórios do Codex

- Código alterado, testes e documentação funcional (não só este plano).
- Lista de arquivos modificados/criados, riscos e compatibilidade retroativa.
- Resultado dos testes (comando, contagem, falhas) e indicação explícita **se teste pago não foi executado**.
- Exemplo de projeto com `producao.json` mostrando AIR, versão do take, `taskUUID`, hashes, motivo de roteamento, custo previsto/real e status do Watch.
- `RUNWARE_API_KEY` explicada para configuração do usuário **sem mostrar seu valor**.
- Comandos de uso alinhados à CLI efetiva, por exemplo, geração de storyboard, image-to-video, retomada e relatório de custos. **Não inventar subcomandos sem implementar.**

---

## 10. Checklist de aceite

- [ ] Runware principal selecionada pelo roteador para tarefa compatível.
- [ ] AIR/parâmetros resolvidos pelo schema vigente; input de primeiro/último quadro validado.
- [ ] `RUNWARE_API_KEY` protegida; sem chaves em logs/commits.
- [ ] Gera imagem e vídeo por interface genérica; CLI legada continua funcionando.
- [ ] Vídeo assíncrono sem duplicar tarefas ao expirar conexão/reiniciar.
- [ ] Custo previsto, reserva, custo efetivo e reconciliação rastreáveis por take.
- [ ] Dois jobs paralelos não conseguem ultrapassar o orçamento.
- [ ] Cache reaproveita arquivos idênticos sem nova chamada.
- [ ] Watch analisa takes com timestamps; falha do Watch não aprova tomada.
- [ ] Atuação, lip-sync, continuidade e contratos são gates reais para a montagem.
- [ ] Troca de imagem invalida descendentes necessários sem perder histórico.
- [ ] Testes automatizados passaram sem cobrança; teste pago só com autorização.
- [ ] Fal.ai mantida como fallback e rollback documentado.

**Regra final:** entregar uma integração testada e reversível. Priorizar consistência de personagem, qualidade de movimento e custo por take aprovado; não otimizar apenas preço nominal e não afirmar sucesso sem evidência.
