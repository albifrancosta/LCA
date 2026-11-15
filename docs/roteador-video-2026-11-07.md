# Roteador inteligente de vídeo: seleção, fallback e custo (2026-11-07)

Este trabalho estende o roteador que já existia (`scripts/provedores.py`). Nada foi reconstruído. O orçamento, a reserva atômica, o disjuntor, os erros tipados, a idempotência, a retomada de job pago e a inspeção continuam valendo para os provedores novos. A especificação original está em `ROTEADOR_INTELIGENTE_APIS_FALLBACK_CRIADOR_VIDEO.md`.

## 1. Diagnóstico da arquitetura existente
| Peça | Onde | O que já fazia |
|---|---|---|
| Roteador com fallback | `provedores.py` | compatibilidade antes do preço, grátis primeiro, preço desconhecido bloqueia, reserva sob trava, disjuntor, backoff, cota ≠ taxa ≠ saldo ≠ credencial, timeout pago vira `pendente_verificacao` |
| Adaptadores | `provedores.py` | HF Wan 2.2 I2V/S2V, fal Kling/Avatar/OmniHuman, Runware, OpenAI imagem, Gemini TTS |
| Orçamento por projeto | `projeto.py` | teto, saldo por provedor, confirmado × desconhecido × reservado, licenças confirmadas |
| Geração autônoma | `autonomo.py` | imagem-chave antes do clipe, inspeção, correção de menor custo, limites por plano |
| Inspeção | `inspetor.py`, `qa_visual.py`, `qa_montagem.py` | bloqueios objetivos (membros, figurino, tela nas costas, texto gerado), congelamento por lado, render desatualizado |

**Faltava:**
- descoberta real dos provedores;
- adaptador Gradio genérico, Alibaba e LTX;
- nota ponderada por tipo de take;
- crédito promocional;
- aprendizado pelo veredito do inspetor;
- painel de execução;
- progresso periódico.

**Bug encontrado:** o `gradio_client` 2.7 usa `token=`, não `hf_token=`. O adaptador antigo HFWan quebraria na próxima geração grátis.

## 2. Provedores integrados (verificados em 2026-11-07)
| id | Tipo | Verificação | Limites lidos | Preço |
|---|---|---|---|---|
| `hf-wan22-i2v` | grátis por API (ZeroGPU) | RUNNING, `/generate_video` | 0,5–5 s | US$ 0 (cota) |
| `hf-ltx-distilled` | grátis por API (ZeroGPU) | RUNNING, `/image_to_video` | 0,3–8,5 s, até 1280 px | US$ 0 (cota) |
| `hf-ltx2-turbo` | grátis por API (ZeroGPU) | RUNNING, `/generate_video` | 1º e último quadro; duração **não exposta** | US$ 0 (cota) |
| `hf-wan21-fast` | grátis por API (ZeroGPU) | RUNNING, `/generate_video` | 0,3–3,4 s, até 896 px | US$ 0 (cota) |
| `hf-wan22-lightning` | grátis por API (ZeroGPU) | RUNNING, `/generate_video`, Space declara apache-2.0 | 0,5–10 s, último quadro | US$ 0 (cota) |
| `alibaba-wan22-i2v-flash` | pago | doc oficial (Singapura) | 480P/720P; 120 RPM | US$ 0,015/s (480P) · 0,036/s (720P) |
| `ltx-23-fast` | pago | docs.ltx.io/pricing + referência v2 | 720p/1080p | US$ 0,03/s (720p) · 0,06/s (1080p) |
| `ltx-23-pro` | pago | docs.ltx.io/pricing | 720p/1080p | US$ 0,04/s (720p) · 0,08/s (1080p) |
| Runware / fal (já existiam) | pago | catálogo anterior | — | conforme catálogo |

Sobre a cota grátis dos Spaces:
- A cota ZeroGPU pertence à conta (com `HF_TOKEN`) ou ao IP, e vale para todos os Spaces ao mesmo tempo (`compartilha_cota_com`). O roteador não troca de identidade para fugir dela.
- Com a cota esgotada, o Space devolve erro de cota e o roteador passa ao próximo provedor.

## 3. Avaliados e NÃO integrados
- **`numanajmal0/wan-video-api`:** autor sem histórico, modelos expostos `nsfw-*` e só texto→vídeo. Impróprio para conteúdo de marca.
- **`Wan-AI/Wan2.2-S2V`:** o Space está em **CPU** (`cpu-basic`). A API responde, mas gerar vídeo é inviável, então fica como `nao_confirmado`.
- **`wan2.2-i2v-plus`:** o preço não foi encontrado nas páginas oficiais. Ficou catalogado com preço `null`, o que bloqueia gasto.
- **`wan2.1-turbo`:** id exato e preço não confirmados.
- **Franquia grátis da Alibaba:** removida para usuários novos em 2026-10-29. Quem já tinha mantém até expirar, e só entra se o usuário informar o saldo em `creditos_promocionais`.
- **Interfaces web:** nunca são automatizadas (`gratis_web` fica de fora).

## 4. Seleção (política `pontuacao`, padrão do modo `teto`)
1. **Compatibilidade:** etapa, capacidades, faixa de duração lida na API, licença, credencial, qualidade mínima, descoberta recente e disjuntor.
2. **Nível**, com `prefer_free` ligado: 0 = grátis comprovado · 1 = crédito promocional válido · 2 = pago.
3. **Nota** dentro do nível (`api_router.pontuacao.pesos`, valores INICIAIS configuráveis):

| Peso | Componente | Como é medido |
|---|---|---|
| 30% | qualidade | declarada (standard/high/premium) × taxa de aprovação medida |
| 25% | custo | 1 − (US$/s ÷ US$ 0,20/s); grátis = 1; desconhecido = 0 |
| 20% | compatibilidade | `perfil[tipo_take]` do provedor |
| 15% | disponibilidade | falhas seguidas e latência mediana |
| 10% | consistência | preserva referências e aceita o quadro final quando há continuidade |

4. **Tipo de take:**
   - `motion` (título, tela, cartão) vira Remotion e nunca chama API;
   - `fala` (voz em quadro ou lip-sync);
   - `i2v_personagem` (há personagem no plano);
   - `cinematografico` (câmera em movimento, sem personagem);
   - `simples`.
5. **Qualidade mínima** de take final: `high` por padrão.
   - O projeto pode mudar com `qualidade.piso_final`.
   - No modo `custo_zero` o piso é `standard`, porque não há alternativa paga e quem barra defeito é o inspetor.
   - Take declarado `tipo_take: "simples"` aceita `standard`.
   - Um provedor grátis com 4 ou mais takes inspecionados e pelo menos 75% de aprovação sobe para `high` por evidência.

## 5. Fallback
- **Quando troca de provedor:** indisponível, cota, saldo, credencial, erro recuperável (com backoff e limite de tentativas) ou qualidade reprovada.
- **Job pago com timeout:** vira `pendente_verificacao` e é consultado na retomada pelo `job_id` gravado em `<saida>.<provedor>.json` antes da espera. Nunca é reenviado por cima.
- **Pago exige orçamento configurado:** teto no `projeto.json`, `provedores.py aprovar` ou teto global. Com `require_paid_approval`, sem nenhum deles = `waiting_approval`.

## 6. Custos
Cada tentativa vai para `memoria/provedores-tentativas.jsonl` com os campos: provedor, modelo, `duracao_s`, `resolucao`, `estimado_usd`, `real_usd`, `creditos_usados`, `nivel`, resultado/erro, `tentativa_n`, `latencia_ms`, `job_remoto` e `saida`.

O dinheiro fica em `memoria/reservas.json`. O uso de crédito promocional também entra lá, com valor US$ 0 e categoria `credito_promocional`. O projeto enxerga o total separado em confirmado, desconhecido, reservado e livre.

Os limites ficam em `config/roteamento.json` → `api_router`. Os valores atuais (US$ 0,75 por take e US$ 3,10 por projeto) são os que o usuário já tinha aprovado, e o `projeto.json` vence.

## 7. Configuração (`.env`)
| Variável | Para quê |
|---|---|
| `HF_TOKEN` | opcional: usa a cota da sua conta |
| `DASHSCOPE_API_KEY` + `DASHSCOPE_BASE_URL` | endpoint `https://<WorkspaceId>.ap-southeast-1.maas.aliyuncs.com` |
| `LTX_API_KEY` | LTX API |
| `RUNWARE_API_KEY`, `FAL_KEY` | já existiam |

Nenhuma chave vai para código ou log (o `limpo()` do roteador mascara).

## 8. Uso
```bash
python scripts/provider_discovery.py                       # estado real dos provedores (grátis, sem gerar nada)
python scripts/provedores.py planejar tarefa.json          # quem seria escolhido, nota e custo (nada é chamado)
python scripts/autonomo.py rodar roteiro.json --job X      # gera com ⏱ de progresso a cada take e a cada 60 s
python scripts/progresso.py <projeto> [--vigiar 300]       # tempo de execução e % do projeto a qualquer momento
python scripts/resumo_execucao.py <projeto>                # painel: níveis, custo, economia, tempo, aprovações
```

Para um provedor promocional, acrescente no catálogo: `"creditos_promocionais": {"saldo": 50, "unidade": "segundos", "valido_ate": "AAAA-MM-DD", "fonte": "…"}`.

Para continuidade entre takes, o contrato aceita três campos:
- `continua_de: "<plano anterior>"`: o 1º quadro passa a ser o último quadro do take anterior aprovado;
- `quadro_final_img`: o quadro final do plano;
- `evitar: [...]`: vira prompt negativo nos modelos que aceitam.

## 9. Exemplo de execução com vários takes (simulado, sem custo, 2026-11-07)
O projeto de demonstração tinha 3 takes: t1 (personagem pega o celular), t2 (continua de t1, com `evitar` como prompt negativo) e t3 (escritório vazio com push-in).
```
⏱ [simulação dos takes] 0/3 · 0% · 0s decorridos · projeto 30% · 0s desde o início
⏱ [simulação dos takes] 1/3 · 33% · 0s decorridos · ~0s restantes · agora: t1 · projeto 30% · 1s desde o início
⏱ fim [simulação dos takes] 3/3 · 100% · 1s decorridos · projeto 30% · 2s desde o início
modo teto (take final, piso high):  1. runware-kling3-pro nota 0.75 · 2. runware-kling26-pro 0.64 · 3. fal-kling26-pro 0.53
                                    (Spaces grátis fora: qualidade standard ainda não comprovada pelo inspetor)
modo custo_zero (piso standard):    1. hf-wan22-i2v · 2. hf-wan22-lightning (os que declaram 'atuacao') · pagos bloqueados
take "simples":                     os 5 Spaces grátis primeiro (hf-ltx-distilled nota 0.71 …), depois os pagos
```

## 10. Custos e limitações conhecidas
- **Nenhuma chamada paga** foi feita no desenvolvimento. Alibaba e LTX estão sem chave no ambiente (`sem_credencial`), e os adaptadores deles foram testados só com transporte falso, seguindo a documentação oficial. **O primeiro uso real é o teste de verdade.**
- **Duração por modelo:** não é publicada para `wan2.2-i2v-flash` nem para LTX ("Supported Models" não foi lida). O provedor recusa o que não aceitar, e esse erro de payload não é cobrado.
- **LTX-2 Turbo:** não expõe a duração. O clipe sai com a duração padrão do Space e o inspetor confere.
- **Perfis por tipo de take:** são valores INICIAIS, não medidos. O veredito do inspetor (`aprovacao_final`) corrige a taxa com o uso.
- **Licença comercial:** é `unknown` em todos (Spaces sem licença declarada; termos Alibaba/LTX não conferidos). Com `uso: publicidade`, tudo fica bloqueado até o usuário confirmar no chat.
- **Economia** no `resumo_execucao.py`: calculada contra o preço documentado do fal Kling 2.6 (US$ 0,07/s). No MinhaMarca deu −US$ 2,58, porque houve muitas refações pagas. O número é honesto e não maquiado.
- **Watch MCP:** não está na sessão. A inspeção usa o pipeline próprio (cv2 + whisper + Gemini quando houver cota), e "sem análise" = `nao_verificado`.
