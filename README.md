# LCA — Light. Camera. Action. 🎬

**Um estúdio de vídeo com IA dentro do Claude Code, em português.** Você conta o que quer; o LCA entrevista, escreve o roteiro, monta o storyboard, gera ou dirige as imagens e as animações, grava a narração, escolhe a trilha, monta no Remotion e entrega o MP4 pronto para Reels, TikTok, Shorts ou YouTube — parando para a sua aprovação antes de cada gasto.

> *English summary:* LCA is a Claude Code skill (Portuguese-first) that works as an AI video studio: interview → script → storyboard → images/animation → TTS narration → music → Remotion edit → final MP4, with approval checkpoints and cost control. Free paths first; paid APIs only with explicit confirmation.

## O que ele faz

- **Cria** vídeos do zero: anúncio, institucional, história com personagens, motion graphics.
- **Edita** vídeos gravados: corta silêncios e vícios, legenda palavra a palavra, faz vários cortes de um vídeo longo, muda de formato (16:9 ↔ 9:16).
- **Aprende** com vídeos de referência que você mandar (gancho, ritmo, legenda, estrutura) e com o desempenho dos seus vídeos.
- Trabalha como um **estúdio com departamentos** (roteiro, fotografia, arte, animação, áudio, música, edição, qualidade, atenção do espectador), cada um um agente.
- **Três pontos de conferência** com você: roteiro → imagens → filme montado. Nada pago acontece sem o seu ok.

## Requisitos

| Obrigatório | Para quê |
|---|---|
| [Claude Code](https://claude.com/claude-code) | onde a skill roda |
| Python 3.11+ | os scripts |
| [ffmpeg](https://ffmpeg.org/) no PATH | áudio, vídeo, medições |
| Node.js 18+ | montagem no [Remotion](https://www.remotion.dev/) |

Opcionais (cada um liga uma função; sem eles a skill segue por outro caminho): `faster-whisper` (transcrição local), `easyocr`, `ultralytics` (pose/atuação), `opencv-python`, `scikit-image`, `librosa`, `praat-parselmouth`, `moviepy`, `gradio_client` (clipes grátis no Hugging Face). Veja `requirements.txt`.

## Instalação

```bash
git clone https://github.com/<seu-usuario>/LCA.git ~/.claude/skills/criador-video
cd ~/.claude/skills/criador-video
pip install -r requirements.txt
python scripts/instalar_agentes.py instalar     # copia os agentes do estúdio para ~/.claude/agents
python scripts/chaves.py status                 # mostra o que já funciona e o que falta
```

A pasta precisa se chamar `criador-video` (é o nome da skill). Abra uma sessão nova do Claude Code e peça: *"faz um vídeo de 30 segundos sobre…"*.

## Chaves de API — todas opcionais

Sem nenhuma chave você já tem: motion graphics e montagem (Remotion), edição (cortes, silêncios, legendas, formatos), transcrição local, trilha sintetizada, roteiro e storyboards.

| Chave | Serviço | Custo | Libera |
|---|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | grátis com limite | narração com IA, análise dos vídeos |
| `FAL_KEY` | fal.ai | **pago** | clipes animados (Kling, Wan), trilha por IA, lip-sync |
| `OPENAI_API_KEY` | OpenAI | **pago** | imagens geradas por IA |
| `RUNWARE_API_KEY` | Runware | **pago** | clipes e lip-sync (alternativa ao fal.ai) |
| `PIXABAY_API_KEY` | Pixabay | grátis | vídeos de banco para uso comercial |
| `PEXELS_API_KEY` | Pexels | grátis | vídeos de banco |
| `HF_TOKEN` | Hugging Face | grátis | mais clipes grátis por dia |

**Configure fora do chat** — nunca cole uma chave na conversa:

```bash
python scripts/configurar.py      # no seu terminal: digitação escondida, testa e grava em .env
```

ou copie `.env.example` para `.env` e preencha. O `.env` está no `.gitignore`. Os serviços pagos cobram na **sua** conta; a skill sempre mostra o custo estimado e pede confirmação antes de gastar.

## Sua marca

- `memoria/perfil.md` — sua marca, cores, voz, público e preferências (a skill preenche com você na primeira entrevista).
- `config/marca.json` (copie de `config/marca.example.json`) — como a narração deve **pronunciar** o nome da marca e como a transcrição costuma escrevê-lo.

## Estrutura

```
SKILL.md        instruções da skill (o "diretor")
agentes/        os departamentos do estúdio (instalados em ~/.claude/agents)
scripts/        ferramentas: roteiro, voz, imagens, clipes, mixagem, inspeção, custos
templates/      projetos Remotion reutilizáveis
references/     guias (entrevista, gancho, roteiro, edição, comercial…)
memoria/        o que a skill aprende com você (começa vazia)
config/         catálogo de provedores, roteamento, marca
tests/          testes sem rede e sem gasto
```

## Testes

```bash
for t in tests/test_*.py; do python "$t"; done
```

Rodam sem internet e sem gastar nada (provedores simulados).

## Avisos

- **Remotion** é grátis para pessoa física e empresas de até 3 funcionários; acima disso exige licença da Remotion.
- Imagens e clipes de pessoas reais: só com autorização de uso de imagem de cada pessoa.
- Músicas de bibliotecas grátis: confira a licença de cada faixa (algumas têm Content ID e podem gerar reivindicação no YouTube).
- Respeite os termos de cada serviço — nada de várias contas para driblar cotas grátis.

## Licença

[MIT](LICENSE)
