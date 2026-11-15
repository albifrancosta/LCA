# LCA — Light. Camera. Action. 🎬

**Um estúdio de vídeo com IA dentro do Claude Code, em português.**

Você diz o vídeo que quer — *"um comercial de 30 segundos para a minha loja"*, *"um vídeo de Natal agradecendo os clientes"*, *"corta as pausas desse vídeo e coloca legenda"* — e o LCA faz o trabalho de uma produtora inteira: entrevista você, escreve o roteiro, desenha o storyboard, dirige as imagens e as animações, grava a narração, escolhe a trilha, monta no Remotion, confere tudo e entrega o MP4 pronto para Reels, TikTok, Shorts ou YouTube.

Você não precisa saber produzir vídeo. Você aprova; o LCA faz.

> **English summary:** LCA is a Portuguese-first Claude Code skill that works as a full AI video studio — interview → script → storyboard → images → animation → TTS narration → music → Remotion edit → QA → final MP4 — with three approval checkpoints and strict cost control (free paths first; paid APIs only with explicit confirmation).

---

## Sumário

- [Como funciona](#como-funciona)
- [O que dá para fazer](#o-que-dá-para-fazer)
- [O estúdio: os departamentos](#o-estúdio-os-departamentos)
- [Grátis × pago](#grátis--pago)
- [Instalação](#instalação)
- [Chaves de API](#chaves-de-api--todas-opcionais)
- [Primeiro vídeo](#seu-primeiro-vídeo)
- [Sua marca e a memória](#sua-marca-e-a-memória)
- [Qualidade: o que o LCA confere sozinho](#qualidade-o-que-o-lca-confere-sozinho)
- [Perguntas frequentes](#perguntas-frequentes)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Avisos e licença](#avisos)

---

## Como funciona

Todo vídeo novo passa pelas mesmas etapas. Nas marcadas com ✋ o LCA **para e espera a sua aprovação** — nada pago acontece antes disso.

```
 0. Entrevista ........ perguntas curtas, uma por vez, cada uma com a recomendação dele
 1. Gancho ............ 6 aberturas diferentes, pontuadas; você escolhe
 2. Roteiro ........... falas, tempo de cada cena, re-gancho no meio, final que fecha o começo
 ✋ Ponto 1 — storyboard do roteiro (quadros com a ação e a fala de cada cena)
 3. Imagens ........... geradas pela API ou por você em outra IA, com os prompts prontos
 ✋ Ponto 2 — storyboard com as imagens reais
 4. Animação .......... cada imagem vira clipe (IA paga, IA grátis que você roda, ou código)
 5. Narração .......... voz com tom definido, conferida palavra por palavra
 6. Trilha ............ 3–4 opções com licença conferida; alinhada ao arco do vídeo
 7. Montagem .......... Remotion: cortes na fala, legendas, textos, mixagem no padrão
 8. Conferência ....... folha de quadros, volume (−14 LUFS), voz × música, texto cortado
 ✋ Ponto 3 — o vídeo montado
 9. Entrega ........... MP4 + legenda do post, hashtags, capa, comentário fixado
10. Aprendizado ....... você conta como o vídeo foi; ele ajusta os padrões para o próximo
```

### Um exemplo real (resumido)

> **Você:** quero um vídeo de Natal da minha empresa: um técnico acorda, pega a farda da gaveta como se fosse um traje de super-herói, e no final agradece aos clientes.
>
> **LCA:** escreve o roteiro "A farda" (60 s, 10 cenas), mostra o storyboard e explica uma escolha: trocou "estamos à disposição em todos os momentos" por "ao seu lado, em cada chamado", porque o contrato é em horário comercial.
>
> **Você:** muda para 7h da manhã · tira a chuva · usa as fotos dos 4 técnicos · não quero protagonista, todos são.
>
> **LCA:** ajusta roteiro, narração (agora no plural) e os 17 prompts; manda um por vez; confere cada imagem que você gera ("o rosto não parece o T3 — tenta este prompt") e cada clipe animado ("ótimo, uso de 0 a 4 s"); quando a cota grátis acaba, anima o resto em código; grava a voz, propõe 4 trilhas, alinha a parte suave da música com a cena da noite de Natal e entrega o MP4 com a legenda do post pronta.

---

## O que dá para fazer

| Modo | Você pede | O LCA entrega |
|---|---|---|
| **Criar** | "faz um vídeo de 45 s sobre…" | roteiro → imagens → animação → voz → trilha → MP4 |
| **Comercial** | "anúncio de 30 s do meu produto" | estrutura dor → virada → solução → chamada, com cenas e falas no tempo |
| **História** | "uma novela de Natal com escolha A ou B no final" | episódio com personagens fixos, gancho e votação nos comentários |
| **Editar** | "tira as pausas e coloca legenda nesse vídeo" | cortes de silêncio e vícios, legenda palavra a palavra, vários cortes, 16:9 ↔ 9:16 |
| **Aprender** | manda um vídeo viral "pra usar de referência" | ficha com gancho, ritmo de cortes, legenda e estrutura — aplicada nos próximos |
| **Feedback** | "teve 3 mil views e 40% de retenção" | ajusta a pontuação dos padrões que funcionaram ou não |

Formatos: vertical 9:16 (padrão), 16:9, 1:1. Duração: de 15 s a alguns minutos.

---

## O estúdio: os departamentos

O LCA trabalha como uma produtora. A sessão principal é o **Diretor Geral**: conversa com você, decide e confere. Os departamentos são **agentes** do Claude Code que fazem lotes de trabalho em paralelo e devolvem o resultado para o Diretor — eles nunca falam com você nem gastam sem orçamento aprovado.

| Agente | Faz |
|---|---|
| `estudio-roteirista` | roteiro, falas, gancho, re-gancho e final |
| `estudio-fotografia` | decupagem: plano, câmera, duração, o que cada cena precisa mostrar |
| `estudio-elenco` | ficha de cada personagem (rosto, figurino, cores, voz) |
| `estudio-arte` | imagens de cada cena (pela API ou dirigindo você) e correção de cor |
| `estudio-animacao` | transforma imagem em clipe com atuação de verdade, não só zoom |
| `estudio-audio` | vozes dirigidas por emoção, ambiente e efeitos sonoros |
| `estudio-musical` | escolhe e prepara a trilha (biblioteca grátis, IA ou sintetizada) |
| `estudio-editor` | montagem no Remotion, mixagem e conferência por folha de quadros |
| `estudio-qualidade` | reprova o que não cumpre o roteiro: rosto errado, mão deformada, fala trocada |
| `estudio-atencao` | onde o espectador vai perder o interesse e o que mudar |

Os agentes são opcionais: sem eles o Diretor faz tudo sozinho, só mais devagar.

---

## Grátis × pago

O LCA sempre tenta o caminho grátis primeiro e **mostra o custo antes de qualquer gasto**.

| Etapa | Grátis | Pago (só com o seu ok) |
|---|---|---|
| Roteiro, storyboard, montagem, legendas, edição | ✅ sempre | — |
| Narração | voz do Gemini (cota grátis diária) ou sua voz gravada | — |
| Imagens | você gera em qualquer IA com os prompts prontos | OpenAI GPT Image (~US$ 0,05 por imagem) |
| Animação | você anima em outra IA com os prompts prontos · Hugging Face (poucos por dia) · zoom e efeitos em código | fal.ai / Runware — Kling (~US$ 0,35 por clipe de 5 s) |
| Trilha | Pixabay (licença comercial) ou trilha sintetizada | trilha por IA (ElevenLabs / ACE no fal.ai) |
| Vídeos de banco | Pixabay / Pexels | — |

Exemplo: o vídeo de Natal de 66 s do exemplo acima custou **centavos** (só a voz), porque as imagens e os clipes foram gerados pelo usuário em ferramentas grátis e o que faltou foi animado em código.

Tudo o que é pago fica registrado num livro-caixa por projeto (`scripts/custos.py relatorio`).

---

## Instalação

### Requisitos

| | Para quê |
|---|---|
| [Claude Code](https://claude.com/claude-code) | onde o LCA roda |
| Python 3.11+ | os scripts |
| [ffmpeg](https://ffmpeg.org/) no PATH | áudio, vídeo e medições |
| Node.js 18+ | montagem no [Remotion](https://www.remotion.dev/) |

### Passo a passo

```bash
git clone https://github.com/albifrancosta/LCA.git ~/.claude/skills/criador-video
cd ~/.claude/skills/criador-video
pip install -r requirements.txt
python scripts/instalar_agentes.py instalar
python scripts/chaves.py status
```

- A pasta **precisa** se chamar `criador-video` — é o nome interno da skill.
- `instalar_agentes.py` copia os departamentos para `~/.claude/agents/`.
- `chaves.py status` mostra o que já funciona e o que falta (sem mostrar nenhuma chave).
- Depois, **abra uma sessão nova** do Claude Code.

Os pacotes opcionais do `requirements.txt` ligam funções extras (transcrição local, análise de pose, batida da música). Sem eles o LCA segue por outro caminho.

---

## Chaves de API — todas opcionais

Sem nenhuma chave você já tem: roteiro, storyboards, montagem e motion graphics no Remotion, edição (cortes, silêncios, legendas, formatos), transcrição local e trilha sintetizada.

| Chave | Serviço | Custo | Libera |
|---|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | grátis com limite | narração com IA, análise dos vídeos |
| `FAL_KEY` | fal.ai | **pago** | clipes animados, trilha por IA, lip-sync |
| `OPENAI_API_KEY` | OpenAI | **pago** | imagens geradas por IA |
| `RUNWARE_API_KEY` | Runware | **pago** | clipes e lip-sync (alternativa ao fal.ai) |
| `PIXABAY_API_KEY` | Pixabay | grátis | busca de vídeos de banco |
| `PEXELS_API_KEY` | Pexels | grátis | busca de vídeos de banco |
| `HF_TOKEN` | Hugging Face | grátis | mais clipes grátis por dia |

**Configure fora do chat — nunca cole uma chave na conversa** (o que você digita no chat fica no histórico):

```bash
python scripts/configurar.py
```

Roda no seu terminal: a digitação fica escondida, a chave é testada e gravada no `.env` (que nunca vai para o Git). Ou copie `.env.example` para `.env` e preencha.

---

## Seu primeiro vídeo

Numa sessão nova do Claude Code, peça em linguagem normal:

```
faz um vídeo vertical de 30 segundos apresentando a minha padaria
```

O LCA vai:
1. conferir o que está configurado e dizer o que é grátis e o que é pago;
2. fazer algumas perguntas (público, objetivo, tom da voz, estilo visual);
3. propor 3 ganchos para você escolher;
4. mostrar o roteiro em storyboard e esperar o seu ok.

Outros pedidos que funcionam:

```
corta as pausas e os "é…" desse vídeo e coloca legenda: C:\videos\aula.mp4
transforma esse vídeo de 10 minutos em 5 cortes para o Reels
analisa esse vídeo viral e usa como referência: https://…
faz os prompts das imagens que eu gero no Gemini e você monta
troca a trilha por algo mais épico
```

---

## Sua marca e a memória

O LCA aprende com você e guarda isso em `memoria/` (começa vazia):

| Arquivo | O que guarda |
|---|---|
| `perfil.md` | sua marca, cores, contato, voz, formato padrão e **preferências fixas** ("não use legenda amarela", "música sempre audível") |
| `padroes.md` | o que prende atenção (gancho, ritmo, re-gancho…), com pontuação que sobe ou desce conforme os seus resultados |
| `historico.md` | cada vídeo feito, com gancho, padrões usados e métricas |
| `biblioteca.md` | personagens, cenas, trilhas e componentes que valem reaproveitar (economiza tempo e dinheiro) |

Para o nome da sua marca ser **pronunciado** certo pela voz e **reconhecido** na transcrição, copie `config/marca.example.json` para `config/marca.json` e ajuste.

---

## Qualidade: o que o LCA confere sozinho

Antes de mostrar qualquer coisa para você, o LCA confere:

- **Roteiro:** palavras por segundo, gancho nos 3 primeiros segundos, re-gancho no meio, número na tela igual ao número falado, promessas que a marca não pode fazer.
- **Imagens:** rosto igual à referência, figurino igual à ficha, mãos e objetos sem deformação, texto ou logotipo inventado pela IA, resolução.
- **Clipes:** a ação aconteceu de verdade (não é só zoom), o personagem não "derrete", nada novo surgindo, vídeo emendado com o anterior.
- **Voz:** cada fala transcrita e comparada com o roteiro (palavra trocada = refaz).
- **Montagem:** folha com um quadro de cada cena, legenda sobre o rosto, texto cortado, volume final em −14 LUFS, voz 9–11 dB acima da música.
- **Atenção:** trechos parados, onde o espectador tende a sair, e o que mudar.

Nada é aprovado só porque a IA devolveu um arquivo.

---

## Perguntas frequentes

**Preciso pagar alguma coisa?**
Não. Dá para fazer vídeos completos só com caminhos grátis. As APIs pagas aceleram e ampliam (clipes animados por IA, imagens), sempre com o custo mostrado antes.

**Funciona com a minha voz?**
Sim: você grava as falas e o LCA usa, ou configura uma voz clonada local (VoiceStudio) em `config/provedores.json`.

**Posso usar pessoas reais nas imagens?**
Pode, a partir de fotos que você mandar — e só com a autorização de uso de imagem de cada pessoa.

**E as músicas?**
O LCA usa bibliotecas com licença comercial (Pixabay), confere a licença de cada faixa e avisa quando a faixa tem Content ID (pode gerar reivindicação automática no YouTube).

**Funciona em Mac e Linux?**
Sim. Os scripts são Python + ffmpeg + Node; as chaves ficam num `.env`. No Windows, também lê as variáveis de ambiente do usuário.

**É só em português?**
As instruções e a conversa são em português do Brasil. A narração pode ser em outro idioma se você pedir.

---

## Estrutura do projeto

```
SKILL.md        as instruções do Diretor Geral (o "cérebro" da skill)
agentes/        os 10 departamentos (instalados em ~/.claude/agents)
scripts/        as ferramentas: voz, imagens, clipes, mixagem, inspeção, custos, chaves
templates/      projetos Remotion prontos (comercial, história, motion graphics)
references/     guias: entrevista, gancho, roteiro, sincronia, edição, comercial, atenção
memoria/        o que o LCA aprende com você (começa vazia)
config/         catálogo de provedores e preços, roteamento, marca
assets/sfx/     efeitos sonoros sintetizados
tests/          testes sem internet e sem gasto
docs/           documentação técnica (roteador, produção, exemplos)
```

### Testes

```bash
for t in tests/test_*.py; do python "$t"; done
```

Rodam sem internet e sem gastar nada (os provedores pagos são simulados).

---

## Avisos

- **Remotion** é grátis para pessoa física e empresas com até 3 funcionários; acima disso exige [licença da Remotion](https://www.remotion.dev/license).
- Os serviços pagos cobram na **sua** conta; acompanhe o saldo de cada um.
- Respeite os termos de cada serviço — nada de várias contas para driblar cotas grátis.
- Não use marcas, personagens ou músicas de terceiros sem licença.

## Contribuindo

Issues e pull requests são bem-vindos. Antes de enviar, rode os testes e confira que nenhum dado pessoal (chave, telefone, caminho da sua máquina) entrou no commit.

## Licença

[MIT](LICENSE) © 2026 Albifran ([github.com/albifrancosta](https://github.com/albifrancosta))
