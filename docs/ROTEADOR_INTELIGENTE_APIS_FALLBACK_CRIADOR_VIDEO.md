# Roteador Inteligente de APIs — Free First + Fallback Pago

**Projeto:** `criador-video`  
**Tipo de documento:** especificação técnica + instruções de implementação para agente de programação  
**Versão:** 1.0  
**Objetivo:** aproveitar primeiro as cotas gratuitas de provedores de IA e recorrer a modelos pagos somente quando necessário, sem comprometer qualidade, consistência ou orçamento.

> **Instrução para o agente implementador:** antes de alterar qualquer arquivo, leia o `SKILL.md` e o código atual. Preserve funcionalidades existentes. Não substitua cegamente o `roteador.py`, o `custos.py` ou o `orquestrador.py`: evolua-os de modo incremental. Não presuma que endpoints, preços, níveis gratuitos ou permissões comerciais de qualquer provedor estão ativos sem confirmação.

---

## 1. Resultado esperado

Implementar um **roteador centralizado de provedores** consultado por todos os departamentos da produção audiovisual:

- **Roteiro e texto** (LLM): desenvolvimento, revisão e adaptação da narrativa.
- **TTS / narração:** vozes, emoção, idioma, clonagem autorizada e duração.
- **Imagens:** personagens, concept art, fichas de referência e keyframes.
- **Vídeo:** geração ou animação de clipes, início/fim de cena e image-to-video.
- **Trilha e efeitos sonoros:** música licenciada, efeitos e áudio ambiente.
- **Visão / inspeção:** análise de consistência, enquadramento e validação.

O roteador deve decidir automaticamente **qual provedor/modelo usar em cada operação**, obedecendo às regras de qualidade, privacidade, licença, disponibilidade, cotas e gastos.

### Fluxo macro

```text
Solicitação do orquestrador
           |
           v
   Contrato da tarefa
 (tipo, qualidade, requisitos)
           |
           v
     Roteador de APIs
           |
           +--> Filtrar provedores compatíveis (idioma, formato,
           |    duração, direitos de uso, voz, resolução etc.)
           |
           +--> Avaliar disponibilidade, cotas e preço estimado
           |
           +--> Ordenar conforme política: gratuito primeiro
           |
           v
  Tentar candidato elegível
           |
       +---+---+
       |       |
     Sucesso  Falha / cota esgotada / qualidade insuficiente
       |       |
       v       v
   Inspeção   Próximo candidato gratuito elegível
       |       |
       |       +--> Sem alternativas gratuitas?
       |                    |
       |                    v
       |             Verificar orçamento
       |                    |
       |             +------+------+
       |             |             |
       |          Permitido      Bloqueado
       |             |             |
       |             v             v
       |        API paga      Pedir aprovação
       v
  Registrar resultado, custo e provedor
```

**Importante:** “gratuito primeiro” não significa “qualquer modelo gratuito”. Um modelo grátis só pode entrar na fila se cumprir o **padrão mínimo exigido pela cena/produção**.

---

## 2. Políticas de seleção

Criar as estratégias configuráveis:

| Política | Comportamento |
|---|---|
| `free_first` **(padrão)** | Prioriza provedores com cota gratuita disponível e qualidade adequada; depois escolhe o pago mais econômico que atenda aos requisitos. |
| `best_value` | Equilibra qualidade, taxa histórica de sucesso, latência e custo dentro do teto. |
| `lowest_cost` | Seleciona a alternativa de menor custo total estimado, respeitando qualidade mínima. |
| `premium` | Prioriza qualidade para a entrega final, mesmo havendo opção gratuita inferior, respeitando aprovação e teto. |
| `manual` | Usuário escolhe o provedor/modelo explicitamente; não muda sem autorização. |

### Regras obrigatórias

1. Verificar **compatibilidade funcional** antes de comparar custo: texto para fala, idioma `pt-BR`, voz configurada, duração, resolução, formato, image-to-video, controle emocional etc.
2. Atribuir qualidade mínima por etapa: `standard`, `high` ou `premium`. Não pressupor pontuação real sem dados de testes.
3. Consultar limites disponíveis por API oficial sempre que houver endpoint confiável; caso contrário, trabalhar com **cotas declaradas + telemetria local** e marcar o saldo como `unknown` quando aplicável.
4. Não tratar “não foi possível consultar saldo” como “há crédito grátis”.
5. **Nunca consumir saldo pago de modo silencioso** se o custo ultrapassar o orçamento autorizado.
6. Não criar contas ou chaves adicionais para contornar limites, termos de serviço, restrições geográficas ou antifraude.
7. Utilizar apenas endpoints e modelos confirmados e autorizados para o tipo de produção; **teste gratuito e uso comercial não são sinônimos**.
8. Registrar sempre as razões de escolha, rejeição, fallback e custo.
9. Para operações de alto custo, reservar orçamento estimado **antes** da chamada e reconciliar depois com o custo efetivo.
10. Falhas de licença, falta de permissão ou credencial inválida não devem gerar tentativas infinitas.

---

## 3. Integração com os arquivos existentes

Adaptar a estrutura real do projeto após inspecioná-la. Os nomes abaixo refletem módulos já informados para a skill:

| Arquivo | Mudança sugerida |
|---|---|
| `SKILL.md` | Documentar a política `free_first`, opções do usuário e quando pedir aprovação. |
| `roteador.py` | Tornar o ponto central de seleção, fallback, tratamento de erros e políticas. |
| `custos.py` | Calcular orçamento previsto, reservar valores e registrar custo efetivo. |
| `orquestrador.py` | Enviar tarefas para o roteador; não selecionar provedores na mão. |
| `producao.py` | Consolidar execução, status e consumo por cena/etapa. |
| `gerar_imagem.py` | Invocar o roteador para geração/edição de imagem, quando compatível. |
| `gerar_clipe_fal.py` | Usar a interface genérica de vídeo, mantendo fal.ai como adaptador. |
| `atuacao.py` | Enviar exigências de voz, emoção, atuação e continuidade. |
| `inspetor.py` | Avaliar qualidade da saída e devolver critérios objetivos de reprovação. |
| `movimento.py` | Declarar capacidades necessárias para image-to-video e movimento. |
| `prompt_clipe.py` | Preservar prompts, referência visual, seed quando compatível e metadados. |
| `montar_historia.py` | Manter coerência global e continuidade de personagens/cenas. |
| `contrato.py` | Definir/validar esquema de tarefa e resultado se essa for sua responsabilidade atual. |
| `preparar_remotion.py`, `Video.tsx` | Manter montagem/renderização; só tocar se precisar exibir metadados ou decisões. |

**Não alterar tudo de uma vez.** Introduzir primeiro uma interface de adaptador e conectar gradualmente os módulos, com testes de regressão.

### Estrutura sugerida (adaptar ao projeto)

```text
criador-video/
  SKILL.md
  ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md
  roteador.py                   # seleção e fallback
  custos.py                     # orçamento e contabilidade
  orquestrador.py
  config/
    providers.yaml              # capacidades e preços verificáveis
    routing.yaml                # políticas e limites
  providers/
    base.py                     # interface padrão
    registry.py                 # registro de adaptadores
    [adaptadores_existentes]    # wrappers das APIs que já estão funcionando
  state/
    usage.sqlite               # exemplo de persistência local, se apropriado
  tests/
    test_routing.py
    test_quota.py
    test_budget.py
    test_fallback.py
    test_voice_consistency.py
```

> Pastas são sugestões; **não duplicar** estruturas equivalentes já existentes.

---

## 4. Contrato único para todas as chamadas

Cada departamento envia um objeto estruturado. Campos recomendados:

```json
{
  "job_id": "video_001",
  "scene_id": "scene_03",
  "task_type": "tts",
  "mode": "final",
  "routing_policy": "free_first",
  "quality_min": "high",
  "language": "pt-BR",
  "commercial_use": true,
  "requirements": {
    "voice_profile_id": "narrador_principal",
    "emotion": "energetic_commercial",
    "consistent_voice": true,
    "format": "wav"
  },
  "estimate": {
    "characters": 840,
    "duration_seconds": 60
  },
  "budget": {
    "currency": "USD",
    "max_cost_per_operation": 0.05,
    "max_cost_per_video": 1.00,
    "approval_required_above_limit": true
  },
  "payload_ref": "referencia_interna_ao_texto_e_assets"
}
```

Esse exemplo é um **contrato interno**, não o JSON exigido por provedores externos. Cada adaptador converte o contrato para a API correspondente. `payload_ref` deve apontar para dados do próprio projeto; não enviar segredos, tokens ou caminhos privados a terceiros sem necessidade.

### Resposta uniforme

```json
{
  "status": "success",
  "provider": "nome_do_provedor",
  "model": "id_do_modelo_verificado",
  "tier_used": "free",
  "output_ref": "caminho_ou_id_do_artefato",
  "estimated_cost_usd": 0.00,
  "actual_cost_usd": 0.00,
  "usage": {"unit": "characters", "quantity": 840},
  "attempt_count": 1,
  "latency_ms": 1234,
  "quality_status": "approved",
  "fallback_history": [],
  "pricing_source_checked_at": null
}
```

O campo `tier_used` deve indicar `free`, `paid` ou `unknown`. **Não registrar `free` sem evidência suficiente de gratuidade aplicável àquela chamada.** Se a cobrança real não for conhecida, reportar `actual_cost_usd: null` e não inventar zero.

---

## 5. Catálogo de provedores: recursos e cotas

Criar um registro que suporte múltiplos modelos por provedor, com capacidades e preços por unidade. Exemplo **ilustrativo, sem prometer gratuidade de nenhum serviço**:

```yaml
providers:
  - id: provider_tts_free_example
    enabled: false          # só habilitar após validar API e termos
    stage: tts
    model: MODEL_ID_VERIFICADO
    tier: free
    commercial_use: unknown # allowed | prohibited | unknown
    languages: [pt-BR]
    capabilities: [tts]
    quota:
      detection: local_counter   # provider_api | local_counter | manual | unknown
      period: monthly
      limit: null
      remaining: null
    price:
      currency: USD
      unit: characters
      amount_per_unit: null
      last_verified_at: null

  - id: provider_tts_paid_example
    enabled: false
    stage: tts
    model: MODEL_ID_VERIFICADO
    tier: paid
    commercial_use: unknown
    languages: [pt-BR]
    capabilities: [tts, voice_style]
    price:
      currency: USD
      unit: characters
      amount_per_unit: null
      last_verified_at: null
```

### Provedores candidatos a avaliar, não pré-aprovados

- **TTS:** Gemini TTS, Fish Audio, Inworld, ElevenLabs e outros conectados.
- **Imagem/vídeo:** fal.ai, APIs já conectadas e alternativas compatíveis com o formato requerido.
- **LLM/roteiro:** modelos dos serviços já contratados e eventuais níveis gratuitos permitidos.
- **Áudio/música:** serviços com licença de sincronização e utilização comercial adequadas.

**Obrigatório:** identificar nome oficial exato do modelo, endpoint, status da API, limites, moeda, unidade de cobrança, licença, data de verificação e restrições por região/conta **antes** de ativar no catálogo. Provedores não devem entrar em produção apenas porque foram mencionados em uma conversa.

### Fontes de verdade, em ordem

1. Resposta oficial do provedor para quota/usage/billing.
2. Telemetria confirmada de requisições e custos reais.
3. Configuração manual com validade e data de verificação.
4. Estimativa identificada explicitamente como estimativa.

Se uma API não publicar saldo de créditos, exibir **`saldo desconhecido`**; não tentar chamadas pagas só para descobrir disponibilidade sem orçamento autorizado.

---

## 6. Lógica de fallback

### Tipos de falhas e conduta

| Situação | Ação |
|---|---|
| Cota gratuita esgotada / `429` de quota | Marcar temporariamente indisponível; testar próximo provedor elegível. |
| `429` de taxa por segundo | Respeitar `Retry-After`, usar fila/backoff e tentar novamente quando fizer sentido. |
| Timeout, `502`, `503`, `504` | Retry limitado com backoff exponencial e jitter; depois fallback. |
| `401` / `403` | Desabilitar aquela credencial/rota até corrigir; não repetir com a mesma chave. |
| `402` / saldo insuficiente | Atualizar elegibilidade financeira; tentar outro elegível; nunca assumir cobrança zero. |
| `400` / payload inválido | Corrigir payload/contrato; fallback só se o outro provedor suportar o formato válido. |
| Resultado reprovado pelo inspetor | Repetir com parâmetros corrigidos ou escalar para um modelo mais adequado, respeitando orçamento. |
| Provedor sem permissão comercial | Remover da fila para vídeo comercial. |
| Falha irreversível / sem orçamento | Parar com erro claro ou solicitar aprovação; não gerar gastos inesperados. |

**Evitar dupla cobrança:** incluir idempotência quando o provedor suportar, consultar o estado da tarefa depois de timeout ambíguo e não disparar automaticamente outro vídeo caro enquanto a execução anterior pode continuar ativa. Toda tentativa deve ser registrada com ID próprio.

### Circuit breaker

Após falhas recorrentes, bloquear temporariamente o provedor e testar recuperação com limitação de chamadas. Tempo e limiares devem ser configuráveis, sem loops de retry.

### Pseudocódigo

```python
async def execute_with_fallback(task):
    candidates = registry.compatible_with(task)
    candidates = policy.rank(candidates, task)

    for candidate in candidates:
        if not candidate.is_allowed_for(task):
            continue
        if not health.can_call(candidate):
            continue
        if not quotas.is_eligible(candidate, task):
            continue

        estimate = pricing.estimate(candidate, task)
        authorization = budget.reserve_if_allowed(task, estimate)
        if not authorization.allowed:
            audit.log_blocked(candidate, authorization.reason)
            continue

        try:
            result = await candidate.generate(task)
            quality = await inspector.check(result, task)
            billing.reconcile(authorization, result.usage)
            if quality.accepted:
                return result
            audit.log_quality_rejection(candidate, quality)
        except RecoverableProviderError as error:
            billing.reconcile_unknown_or_partial(authorization, error)
            audit.log_attempt(candidate, error)
            continue
        except PermanentTaskError:
            billing.release_if_unspent(authorization)
            raise

    raise NoEligibleProvider("Sem opção compatível e autorizada")
```

O pseudocódigo exige implementação cuidadosa de reservas, execuções ainda pendentes e reconciliação. **Não presumir que chamada com erro teve custo zero.**

---

## 7. Controle de gastos e aprovação

### Limites configuráveis

- Custo máximo por operação, cena, vídeo e período (dia/mês).
- Custo máximo para **todas as tentativas**, incluindo falhas cobradas.
- Autorização explícita para uso de APIs pagas.
- Margem de segurança configurável para custo estimado.
- Regra `fail_closed`: se custo, licença ou saldo forem incertos, **não ultrapassar autorização**.

### Padrões sugeridos

```yaml
routing:
  policy: free_first
  default_quality_min: high
  commercial_use: true
  allow_paid_fallback: true
  require_approval_if_budget_exceeded: true
  require_approval_on_voice_change: true
  require_approval_on_visual_style_change: true
  auto_fallback_on_quota: true
  retry:
    max_attempts_per_provider: 2
    respect_retry_after: true
    exponential_backoff: true

budget:
  currency: USD
  max_cost_per_video: 1.00   # EXEMPLO: ajustar com aprovação do usuário
  max_cost_per_operation: 0.10
  max_cost_per_month: null  # sem teto mensal definido => exigir política explícita
  default_unknown_cost_policy: block

quality:
  preview: standard
  final: high
  ads_or_cinematic: premium
```

**Atenção:** os valores são exemplos, não autorização de gasto real. Antes de ligar produção, registrar os valores escolhidos pelo proprietário do projeto. Se não houver aprovação humana disponível no fluxo atual, **bloquear a operação**, registrar estado `waiting_approval` e permitir sua retomada; não presumir consentimento.

### Relatório por vídeo

```text
Vídeo: Comercial MinhaMarca 60s
- Narração: provedor A (cota grátis), US$ 0,00 confirmado
- Cena 01: provedor B, US$ 0,03
- Cena 02: provedor B, US$ 0,03
- Música: acervo com licença aprovada, custo incremental US$ 0,00
- Retries cobrados: US$ 0,01
- Custo estimado total: US$ 0,07
- Custo apurado: US$ 0,07
- Economia estimada vs baseline: US$ 0,04 (metodologia registrada)
```

Mostrar separadamente **valor estimado**, **valor cobrado confirmado**, **crédito promocional consumido** e **economia frente a uma alternativa de referência**. Não somar valor desconhecido como zero.

---

## 8. Continuidade de personagens, vozes e estilo

Evitar o erro de escolher modelos baratos cena a cena, mas perder a unidade da produção.

**Narração/TTS**
- Armazenar um `voice_profile_id` aprovado; vincular idioma, timbre, pronúncias, velocidade e emoção.
- Se não existir equivalência validada entre provedores, **não trocar automaticamente** a voz no meio do vídeo.
- Diante de falha de TTS, preferir reexecutar a narração completa com voz consistente ou solicitar aprovação para trocar.
- Clonagem de voz só mediante direitos/consentimento adequados.

**Imagem/vídeo**
- Preservar fichas de personagem, cenários, figurinos, objetos, referência de estilo, proporção e paleta.
- Manter `seed` quando suportado, sem pressupor equivalência de sementes entre modelos diferentes.
- Preferir o mesmo modelo para cenas conectadas; mudar apenas mediante inspeção ou confirmação.
- Guardar keyframes e versões aprovadas para reutilização.

**Trilha e som**
- Não substituir música por conteúdo de direitos desconhecidos.
- Manter nível, andamento, clima e direitos de sincronização.
- Se recurso gratuito não permitir uso comercial, classificá-lo como inelegível.

---

## 9. Painel de configuração / experiência no chat

Expor parâmetros sem obrigar usuário não técnico a editar YAML:

```text
ESTRATÉGIA DE APIS
(●) Gratuitas primeiro, depois pagas
( ) Menor custo
( ) Melhor custo-benefício
( ) Premium

QUALIDADE
Prévia: [Padrão]
Final: [Alta]
Comercial cinematográfico: [Premium]

ORÇAMENTO
Limite por vídeo (USD): [1.00]
[✓] Pedir aprovação antes de exceder
[✓] Não trocar voz automaticamente
[✓] Não trocar estilo visual sem validação

STATUS
Fish Audio: disponível / limite alcançado / desconhecido
Gemini: disponível / limite alcançado / desconhecido
fal.ai: disponível / limite alcançado / desconhecido

ESTIMATIVA ANTES DE GERAR
Custo previsto: US$ X
Cota gratuita possível: Y
Fallback pago previsto: Z
[Aprovar produção] [Alterar estratégia]
```

Esses nomes são só exemplos de visualização. **A UI deve mostrar exclusivamente dados efetivamente conhecidos ou explicitamente marcados como estimados.**

No fluxo conversacional do projeto, apresentar o provedor selecionado, o motivo, o custo estimado e qualquer troca material de voz/estilo antes da execução cara.

---

## 10. Observabilidade e segurança

Registrar (SQLite ou mecanismo existente):

- ID do vídeo, cena e tentativa; etapa e tipo de entrada/saída.
- Provedor, modelo exato, tier, preço/unidade e data de verificação.
- Latência, uso medido, custos previstos/reais e saldo de cota quando conhecido.
- Erros categorizados, duração, retry/fallback, reason code.
- Avaliação do inspetor e decisão humana.
- URL/ID do job remoto e estado para evitar pedidos duplicados.

**Segurança:** chaves em variáveis de ambiente ou cofre existente; nunca em YAML versionado, prints, prompts nem logs. Não registrar texto privado integral quando não for necessário. Definir política de retenção e verificar termos de tratamento de dados dos provedores antes de enviar materiais de clientes.

---

## 11. Plano de implementação em fases

### Fase A — Auditoria (sem alterações destrutivas)

1. Ler `SKILL.md` e identificar como `orquestrador.py`, `roteador.py` e `custos.py` operam hoje.
2. Inventariar APIs já funcionando, credenciais presentes (sem expô-las), etapas atendidas e tratamento de erro.
3. Detectar mecanismos de cache, inspeção, contratos, custos e histórico já existentes.
4. Confirmar API oficial, limites e licença de cada provedor a integrar.
5. Gerar lista de arquivos e mudanças propostas antes da codificação.

### Fase B — Núcleo do roteador

1. Definir interface de adaptador e contrato padronizado.
2. Adicionar registro de provedores e compatibilidade por etapa.
3. Implantar política `free_first` com ranking determinístico.
4. Implantar contabilidade de cota/orçamento, inclusive `unknown`.
5. Adicionar classificação de erros, retry/backoff e circuit breaker.
6. Criar logs e rastreamento de tentativas e jobs remotos.

### Fase C — Piloto TTS

1. Manter o TTS atual como baseline e preservar voz aprovada.
2. Integrar **um** candidato gratuito somente após verificação de licença/cota.
3. Integrar fallback pago já usado pelo projeto.
4. Comparar áudio do mesmo roteiro em `pt-BR` e qualidade alta: naturalidade, emoção, pronúncia, artefatos, duração e custo.
5. Ativar `free_first` apenas após testes bem-sucedidos e aprovação.

### Fase D — Expansão por modalidade

1. Imagens de referência e keyframes.
2. Vídeos/fragmentos e animação de imagens.
3. Música/efeitos sonoros com licença apropriada.
4. Roteiro/inspeção onde houver provedores substituíveis.
5. Painel de seleção, estado e custo por produção.

### Fase E — Homologação

Testar antes da publicação e preservar rollback para o comportamento atual.

---

## 12. Testes mínimos de aceite

Marcar como concluído apenas se todos os cenários aplicáveis forem aprovados:

- [ ] Com dois provedores igualmente compatíveis, a política `free_first` escolhe o gratuito.
- [ ] Modelo gratuito com qualidade insuficiente é rejeitado antes da chamada ou pelo inspetor.
- [ ] Cota gratuita esgotada provoca fallback para outra cota gratuita disponível.
- [ ] Sem opção gratuita, provedor pago só é utilizado dentro do orçamento autorizado.
- [ ] Custo previsto acima do teto suspende execução em `waiting_approval`.
- [ ] Custo/preço desconhecido não permite ultrapassar orçamento.
- [ ] Falha `429` de quota difere de `429` por limite de taxa.
- [ ] Erro `401/403` não gera loop; erro de payload não é tratado como esgotamento de quota.
- [ ] Timeout de operação remota não dispara dois jobs pagos sem verificação.
- [ ] TTS não troca a voz aprovada automaticamente durante o mesmo vídeo.
- [ ] Vídeo/imagem mantém referências visuais e estilo após fallback ou exige aprovação.
- [ ] Provedor com licença incompatível é rejeitado em conteúdo comercial.
- [ ] Nenhuma chave aparece em log, artefato gerado ou repositório.
- [ ] Relatório diferencia custo previsto, real, crédito grátis e valor desconhecido.
- [ ] APIs atuais continuam funcionando caso o roteador novo seja desativado.
- [ ] Existe opção de rollback e testes automatizados sem gastar créditos reais (mocks).

---

## 13. Critérios de conclusão (Definition of Done)

A implementação está pronta quando:

1. Todo estágio integrado consulta **uma única interface de roteamento**, sem seleção de provedores espalhada pelo código.
2. A política padrão é `free_first`, subordinada a requisitos, direitos e qualidade.
3. O sistema realiza fallback sem loops, gastos não autorizados nem perda silenciosa de consistência.
4. Cada produção gera relatório de provedor, tentativas, cota, custos e motivo de seleção.
5. Existem testes automatizados, logs operacionais e caminho de rollback.
6. O `SKILL.md` explica o comportamento ao usuário de modo simples.

---

## 14. Texto para adicionar ao `SKILL.md` principal

Copiar e adaptar este trecho no local apropriado do arquivo principal:

> **Roteamento inteligente de APIs:** em cada etapa (roteiro, TTS, imagem, vídeo, trilha e inspeção), utilize o roteador centralizado. Por padrão, priorize provedores com cota gratuita **apenas quando** forem compatíveis, estiverem autorizados para o uso e atingirem a qualidade exigida. Ao atingir cotas ou enfrentar indisponibilidade, tente outro provedor gratuito elegível; se não houver, selecione o provedor pago autorizado de melhor custo-benefício dentro do orçamento. Antes de ultrapassar qualquer teto, solicite aprovação explícita. Preserve a voz, os personagens, a estética e os assets já aprovados; informe quando um fallback provocar troca sensível. Registre todas as chamadas, custos, motivos e falhas. Para detalhes, consulte `ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md`.

---

## 15. Comando de implementação para outra IA

> Analise a skill `criador-video` instalada no projeto e leia primeiro o arquivo `ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md`, além de `SKILL.md` e dos módulos existentes. Implemente o roteador centralizado `free_first` com fallback gratuito → pago, compatibilidade, qualidade mínima, cotas, orçamento, inspeção, consistência de voz e identidade visual, logs e testes. Reutilize `roteador.py`, `custos.py` e o restante da arquitetura atual sem destruir funcionalidades. Trabalhe por fases, começando pela auditoria e pelo piloto de TTS. Não invente modelos, endpoints, créditos gratuitos, preços nem permissões comerciais: confirme os dados antes de ativar um provedor. Nenhum custo acima do orçamento poderá ser executado sem autorização. Entregue os arquivos completos modificados, os testes e um resumo de quais provedores realmente ficaram ativos.

---

**Nota:** esta especificação não configura nem executa APIs automaticamente. Ela orienta a implementação, que deve validar os serviços existentes e as regras comerciais atuais antes de entrar em produção.
