# AI Film Production Bible + AI Continuity Supervisor — 2026-11-08

## 1. Diagnóstico do que já existia
| Peça | Situação antes | Uso na implementação |
|---|---|---|
| `producao.py` / `producao.json` | Bíblia-fonte: elenco (ficha, traços, figurino), cenários, objetos e tomadas com decupagem e versões | **Fonte única**; a bíblia visual é derivada dela (nada duplicado) |
| `continuidade.py` | Gemini compara imagem/clipe com as fichas | Intacto |
| `qa_visual.py` | Regras objetivas: membros extras, figurino fora da ficha, interface na traseira, texto gerado, identidade | Reutilizado pelo supervisor (`bloqueios`, `evidencia_faltando`) |
| `qa_montagem.py` | Congelamento por diferença de quadros | Reutilizado (`ler_quadros`, `corridas`) |
| `inspetor.py` | `analisar_visual` (fichas reais, cache, reserva de orçamento), `folha` de quadros | Reutilizado como analisador real e como evidência |
| `roteador.py`, `projeto.py`, `custos.py` | Escolha de modelo por custo esperado, teto/saldo do projeto, `custo_zero` | Estimativa e portão de gasto da correção |
| `orquestrador.py` | Fila por tomada, aprovação no chat, orçamento | Ganhou o portão da bíblia, a tarefa `supervisionar_take` e o comando `biblia` |
| `storyboard.py` | PNG simples | Intacto (a prancha nova é outra coisa) |
| Faltava | IDs estáveis, referências versionadas, plano de câmera, registro de props/estado, prancha HTML/PNG/PDF, ciclo de correção com limites | Criado |

Dos arquivos citados no pedido, `gerar_clipe_fal.py`, `prompt_clipe.py`, `montar_historia.py`, `preparar_remotion.py`, `atuacao.py`, `movimento.py`, `contrato.py` e `Video.tsx` existem e **não foram alterados**.

## 2. Arquivos
Novos:
- `scripts/cinematografia/`: `__init__.py`, `production_bible.py`, `character_reference.py`, `environment_reference.py`, `storyboard_visual.py`, `shot_planner.py`, `props_registry.py` e `board_generator.py`
- `scripts/supervisor_continuidade.py`
- `templates/cinematic_board.html`
- `tests/test_production_bible.py`
- este documento

Alterados:
- `scripts/orquestrador.py`: `planejar(d, base=None)` e `cmd_proximos(..., base=None)`; sem `base`, o comportamento é idêntico ao anterior. Funções novas: `portao_biblia`, `takes_sem_supervisao` e o comando `biblia`.
- `SKILL.md`: seção nova.

Backup completo antes da mudança: `~/estudio-video/backups/criador-video-2026-11-08-antes-bible/`.

## 3. Saída por projeto
```
production_bible/
  bible.json                 fonte(sha), modo/aprovação(hash), personagens, cenarios, objetos, tomadas, planos, storyboard, continuidade, custos_estimados, _refs (versões)
  characters/char_*.json     environments/env_*.json     props/prop_*.json
  storyboards/storyboard.json   shot_lists/shot_list.json   continuity/registro.json
  continuity/pre_producao.json  continuity/inspecoes/<take>.json (+ -folha.jpg, -correcao.json)  continuity/entre_takes.json  continuity/log.jsonl  continuity/RELATORIO.md
  boards/overview.html|png|pdf  boards/cena-NN.html|png|pdf  boards/export.json
```

## 4. Fluxo
1. `producao.py iniciar / personagem / cenario / objeto / tomada` (como antes), com os campos opcionais novos na tomada:
   - `emocao`;
   - `objetos_estado`;
   - `figurino` (troca);
   - `horario`;
   - `lado_eixo` / `cruza_eixo`;
   - `pausas`;
   - `justificativa_continuidade`.
2. `orquestrador.py biblia`: bíblia, pranchas e checagem de pré-produção.
3. Supervisionado: enviar `boards/overview.png` no chat. Depois do "ok", rodar `production_bible.py aprovar --nota "…"`. No automático, a checagem `pre` sem problema grave já aprova.
4. `orquestrador.py proximos`: imagens, clipes e vozes como antes. Nenhum gasto antes da prancha aprovada.
5. Clipe gerado:
   - `supervisor_continuidade.py inspecionar <take> <video> --visual [--narracao a,b]`;
   - se reprovado, `corrigir <take>` (o plano diz o que regenerar e quanto custa);
   - depois do clipe novo, reinspecionar.
6. `entre-takes` e `relatorio` antes da montagem. A montagem segue o fluxo atual (`qa_montagem`, `inspetor filme`).

## 5. Exemplo real
O projeto `2026-11-05-plano-47` (3 personagens, 5 cenários, 2 objetos, 1 tomada) gerou `production_bible/boards/overview.png` (2400 px de largura), mais o PDF e a página por cena. A checagem `pre` deu OK, com 11 apontamentos não graves: 4 cenários sem referência, sem paleta e sem escala. O orquestrador passou a pedir `prancha` antes dos gastos.

## 6. Testes (`python tests/test_production_bible.py` → 12/12 OK)
- **A.** Gravata fora da ficha vira `figurino_involuntario` grave, com o timestamp. O plano `regerar_com_referencia` gera um prompt "no gravata vermelha" e usa a ficha char_ana.
- **B.** Três braços viram `membros_extras` grave em 1,5 s, com a folha de quadros como evidência; a estratégia é `regerar_take`.
- **C.** Interface nas costas do tablet vira `interface_traseira` grave; a estratégia é `refazer_imagem_chave`.
- **D.** Congelamento de 1,0 a 2,2 s é detectado no vídeo sintético. Só o trecho ±0,3 s é regenerado, a reinspeção aprova e o log registra o custo estimado e o custo real em separado.
  - D2: o limite de tentativas leva à revisão humana; o orçamento de correção estoura e leva à revisão humana; preço desconhecido não gera gasto.
  - D3: sem análise, com análise indisponível ou com confiança baixa, o take fica não verificado, nunca aprovado.
  - D4: `custo_zero` bloqueia a regeneração paga, e os limites do `projeto.json` viram o padrão.
- **E.** Caneca na mão em t001 que some em t002: o problema é apontado no planejamento e na análise observada. Com "deixa a caneca" na ação, não é apontado.
- **F.** JSON válido, IDs estáveis, versão da ficha 1→2 com histórico, aprovação invalidada quando a referência muda, substituição manual preservada, HTML com as 8 seções e imagens reais, PNG ≥ 2000 px e PDF.
- Extra: portão do orquestrador e modo automático.

Suíte completa (pytest): 172 passam. Três testes falham e um dá erro, **pré-existentes**: o backup sem esta mudança dá exatamente as mesmas falhas. A causa é um mock de `tts_gemini` que vaza entre arquivos no pytest. Cada um passa isolado, e `python tests/test_contrato_qa.py` dá 23/23.

## 7. Integrações que dependem de configuração
- Análise visual real (`--visual`): Gemini com cota e orçamento do projeto (`projeto.json`, modo ≠ `custo_zero`, teto). Sem isso, o take fica não verificado.
- Regeneração automática: o ciclo `corrigir(..., regenerar=f)` está pronto, mas o `f` concreto, que chama o provedor escolhido pelo roteador com as referências, ainda é feito pelo agente estudio-animacao/arte a partir do plano. Não há ligação automática com o fal/Runware, para não gastar sem aprovação.
- Geração das pranchas de referência por IA: os prompts (`prompt_prancha`) ficam no JSON; a geração passa pelo roteador e pelo orçamento como qualquer imagem.
- PNG/PDF: Playwright, depois Chrome, depois Edge. Sem navegador, sai só o HTML, e a limitação fica em `boards/export.json`.

## 8. Custos (estimativa, `production_bible.py custos`)
- Bíblia, prancha, checagem `pre` e inspeção local (congelamento, duração, sincronia): **US$ 0**.
- Imagens que faltam: cerca de US$ 0,05 por imagem (pranchas de personagem e cenário e keyframes; preço `medium` de `gerar_imagem`).
- Análise visual: fração de centavo por take (`qa_visual.estimar_analise`).
- Correção: preço do modelo escolhido pelo roteador, limitado por `max_gasto_plano` (padrão US$ 2) e pelo teto do projeto.
- Plano 47: US$ 0,70 estimados para o que falta.

## 9. Limitações e próximos passos
- As vistas de uma ficha única (turnaround) ficam como "na_ficha (não verificada)": não recorto vistas automaticamente.
- O camera blocking é um esquema de planta, não um render 3D.
- A detecção de "objeto atrás do celular" depende da análise visual, que precisa de cota do Gemini.
- Próximos passos:
  - ligar o `regenerar` ao `gerar_clipe_fal`/Runware com aprovação de orçamento;
  - gerar as vistas que faltam com referência da ficha;
  - corrigir o isolamento de mocks da suíte pytest.
