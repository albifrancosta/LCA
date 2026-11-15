# Exemplos de produção autônoma (2026-11-07)

Os dois roteiros abaixo usam só o fluxo normal da skill. Nenhum comando aqui foi rodado com gasto. A parte grátis (projeto, orçamento, duração, animatic, montagem, estado, acervo, benchmark) foi executada de verdade no projeto MinhaMarca, e os resultados estão no fim.

## A. Custo zero (`modo: custo_zero`)

```bash
S=~/.claude/skills/criador-video/scripts; P=~/estudio-video/projetos/<novo>
python $S/projeto.py iniciar $P --modo custo_zero --job meu-video   # nenhuma chamada paga daqui em diante
python $S/acervo.py buscar "personagem cenário ação"                # reuso direto antes de qualquer coisa
python $S/animatic.py $P                                             # roteiro temporal + animatic (voz local ou silêncio)
python $S/autonomo.py rodar $P/roteiro.json --job meu-video          # só rotas grátis (HF Wan 2.2 I2V/S2V, VoiceStudio)
#   imagem-chave sem análise paga → revisao_imagem: o Claude olha assets/img/<id>.png e grava
python $S/inspetor.py revisar $P/roteiro.json --planos c01 --estado aprovado --nota "2 braços, tela para ela, sem texto" --imagem
#   clipe sem Gemini → revisao_diretor: o Claude olha entrega/inspecao/<id>.jpg (a folha lista o que conferir)
python $S/inspetor.py filme $P/roteiro.json entrega/filme.mp4        # whisper + cv2 + qa_montagem, tudo local
python $S/estado_producao.py render $P --video entrega/filme.mp4 --registrar --verificado
python $S/projeto.py orcamento $P                                    # tudo zerado
python $S/acervo.py indexar $P
```

Limites: a cota grátis do HF ZeroGPU é de cerca de 3 clipes por janela, sem token. A licença comercial do Wan não foi conferida, então, com `uso: publicidade`, o roteador bloqueia o Wan até o usuário confirmar no chat. Em vídeo interno, use `uso: "interno"`.

## B. Teto definido (`modo: teto`, US$ 22 — caso MinhaMarca)

```bash
python $S/projeto.py iniciar $P --modo teto --teto 22 --job exemplo-dois-mundos
# o usuário confirma no chat os termos de cada provedor que pode entrar em publicidade → ids em orcamento.licencas_confirmadas
python $S/projeto.py orcamento $P          # teto · saldo · confirmado · reservas (órfãs) · desconhecido · livre
python $S/animatic.py $P                   # decide a duração ANTES dos takes (registrada uma vez)
python $S/autonomo.py rodar $P/roteiro.json --job exemplo-dois-mundos --simular   # quem geraria cada take e quanto (nada gasto)
python $S/autonomo.py rodar $P/roteiro.json --job exemplo-dois-mundos             # reserva antes de enviar; para no teto com 1 mensagem
python $S/correcoes.py sugerir $P --plano c02e                                 # correção mais barata antes de pagar outro take
python $S/inspetor.py filme $P/roteiro.json entrega/filme.mp4
python $S/qa_montagem.py comparar $P entrega/antes.mp4 entrega/filme.mp4 --plano c10
python $S/estado_producao.py render $P --video entrega/filme.mp4 --registrar --verificado
python $S/projeto.py orcamento $P
```

## Execução real (sem custo) no projeto MinhaMarca, em 2026-11-07

| Etapa | Resultado |
|---|---|
| `projeto.json` | 90 s / 2700 frames / 30 fps, modo teto, teto de US$ 22, saldo do fal = 0 desde 15:10, `uso: publicidade`, `licencas_confirmadas: []` |
| `projeto.py orcamento` | **confirmado US$ 0,00 · desconhecido US$ 20,98** (o fal não devolve custo real, então a reserva conta como gasto) · **reservas abertas US$ 0,57** (2 órfãs: c03c 0,19 e c02d 0,39, a conferir no fal antes de liberar) · **livre US$ 0,44**. O `custos.json` legado (US$ 18,48 estimados) aparece separado e não é somado |
| `provedores.py planejar` (c07a) | bloqueado: OmniHuman fal e Runware com `commercial_use: unknown` para publicidade. Os outros não têm `fala_com_corpo` |
| `projeto.py duracao` (MP4 final) | 94,2 s × 90 s = +4,7 %, dentro de ±5 %, aceito com ressalva. Registrado uma vez; a 2ª chamada devolveu `nova: false` |
| `animatic.py` | contratos do roteiro somam **110,6 s** (a montagem tem 94,2 s); 9 falas não cabem na duração do contrato (c02b, c02d, c02e, c03a, c09a…). Decisão "fora da tolerância" registrada. O animatic tem 110,7 s e levou 24 s |
| `qa_montagem.py` no MP4 final | 27 planos em 26 s. Tela dividida c10: os **dois lados estão desacelerados a 0,82× e não congelam** (a correção `minRate` foi confirmada no arquivo). Única ressalva: c06a congela 0,37 s no fim do plano (média) |
| `estado_producao.py sincronizar` | 11 clipes `inspecionado` (inspeção aprovada com o mesmo sha). Render `desconhecido`: o retrato não foi registrado de propósito, porque o render atual ainda tem o c07a antigo |
| `acervo.py indexar` | 116 ativos. Os clipes reprovados aparecem só como `referencia_negativa`, e as exceções do diretor como `aprovado_com_excecao` |
| `benchmark_provedores.py medir` | fal Kling 2.6: 26 tentativas, 69 % de aproveitamento no roteador, latência mediana de 165 s, US$ 0,10 por segundo aprovado. Kling 3: 50 %, 256 s, US$ 0,24/s |
| `projeto.py avaliar` | nota editorial 8/10 do usuário em `entrega/avaliacao-editorial.json`, separada de audiência |
