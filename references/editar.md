# Modo EDITAR — editar vídeos que já existem

Para vídeos gravados (fala para a câmera, live, aula, podcast, tela gravada) ou vídeos prontos que precisam virar outro formato.
Tudo roda local: `scripts/editor.py` (faster-whisper + ffmpeg). Use **`python`** (é o que tem faster-whisper).

```bash
PY=python
ED="SKILL_DIR/scripts/editor.py"
```

Pasta de trabalho: `%USERPROFILE%\estudio-video\edicoes\<data>-<slug>\`. Nunca sobrescreva o vídeo original.

## Sempre primeiro: transcrever

```bash
$PY $ED transcrever video.mp4 -o transcript.json --termos "MinhaMarca, orçamento, fluxo de caixa"
```
- Gera `transcript.json` (cada palavra com início/fim) e `transcript-frases.txt` (frases com tempo — **leia este** para entender o vídeo).
- `--termos`: nomes de marca/produto/jargão que aparecem na fala (puxe de `perfil.md` → Termos). Sem isso o whisper erra nomes.
- `--corrigir Olí=MinhaMarca stock=estoque`: trocas depois da transcrição, para erros que sobrarem. Anote os erros recorrentes em `perfil.md` → Termos.
- `--modelo`: `small` (padrão, bom) · `medium` (fala sobre música, sotaque forte) · `base` (rápido, para testes).
- Leia as frases. Mais de 20% de palavras sem sentido = transcrição ruim → modelo maior.

## 1. Cortar e limpar

```bash
$PY $ED limpar video.mp4 transcript.json -o limpo.mp4
```
- Corta pausas maiores que `--max-pausa` (padrão 0,35 s), vícios ("éé", "hum", "ahn") e gaguejos (palavra repetida em sequência).
- Gera também `limpo.transcript.json` (tempos já ajustados ao vídeo novo — use este para legendar) e `limpo.limpeza.json` (o que saiu).
- Ritmo mais calmo (aula, depoimento): `--max-pausa 0.6`. Ritmo de Reels: `0.25–0.35`.
- Trechos ruins inteiros (erro, take repetido): leia `transcript-frases.txt`, apague as palavras desse trecho do `transcript.json` e rode `limpar` — o que não está no transcript sai do vídeo.
- Confira: extraia frames/assista ao começo, a um corte do meio e ao fim. Corte "comendo" sílaba → aumente `--margem` (padrão 0,08).

## 2. Legendas automáticas

```bash
$PY $ED legendar limpo.mp4 limpo.transcript.json -o legendado.mp4 --titulo "Seu gancho aqui" --maiusculas
```
- Palavra a palavra, grupos de `--palavras 3`, palavra falada em `--cor-destaque` (padrão amarelo `#FFE600`; use a cor da marca do `perfil.md`) e levemente maior. Cada grupo entra com um "pop". Vírgula/ponto final somem (`--pontuacao` mantém).
- `--titulo`: texto de gancho no topo, numa caixa, nos primeiros `--titulo-ate 3` s (padrão P01).
- Posição: `--altura 0.70` (70% da altura; suba para 0,60 se a legenda cobrir algo importante). Tamanho: `--tamanho 0.052`.
- Fonte: `--fonte Arial` (instaladas e boas: Arial, Impact, Bahnschrift, Verdana, Tahoma).
- `--somente-ass`: gera só o arquivo `.ass` (legenda editável) sem queimar no vídeo.
- Confira um frame de cada parte: legenda legível, não cobre rosto/print principal, palavra destacada certa.

## 3. Virar vários cortes (vídeo longo → Reels/Shorts)

1. Transcreva o vídeo longo e **leia** `transcript-frases.txt` inteiro.
2. Escolha de 3 a 8 trechos de **20–60 s**. Um bom trecho:
   - começa numa frase que funciona como gancho sozinha (pergunta, número, afirmação forte, polêmica), nunca no meio de um raciocínio;
   - tem uma ideia completa e termina numa conclusão ou frase de efeito;
   - não depende de algo dito antes.
   Aplique os padrões de Gancho de `padroes.md`.
3. Escreva `cortes.json` (início da 1ª palavra − 0,1 s e fim da última + 0,1 s):
   ```json
   [
     {"nome": "corte-1-planilha", "start": 12.4, "end": 41.0, "titulo": "Pare de usar planilha"},
     {"nome": "corte-2-caixa", "start": 95.2, "end": 128.7, "titulo": "Seu caixa no azul", "x": 0.35}
   ]
   ```
   `x` (opcional) = onde está a pessoa/assunto na horizontal (0 esquerda, 1 direita) para `--modo crop`.
4. Rode:
   ```bash
   $PY $ED cortes video.mp4 transcript.json cortes.json -d cortes --modo crop --maiusculas
   ```
   Cada corte sai pronto: recortado, vertical, volume normalizado e legendado (`cortes/<nome>.mp4`).
5. Mostre ao usuário a lista: nome, duração, gancho e por que escolheu cada trecho.
6. Quer tirar as pausas também: `cortes --sem-legenda`, depois `limpar` e `legendar` em cada um (o `<nome>.transcript.json` de cada corte já vem pronto).

## 4. Reformatar e exportar

```bash
$PY $ED reformatar video.mp4 -o final.mp4 --formato 9:16 --modo blur
```
- `--formato`: `9:16` (Reels/TikTok/Shorts) · `4:5` (feed Instagram) · `1:1` · `16:9` (YouTube) · `original` (só reexporta).
- `--modo blur`: o vídeo inteiro no centro com ele mesmo desfocado de fundo (nada é cortado — ideal para tela gravada e prints).
- `--modo crop --x 0.5`: preenche a tela cortando as laterais (ideal para pessoa falando; ajuste `x` para onde ela está).
- Sempre exporta H.264 + AAC 48 kHz, 30 fps, `faststart`, volume em `--lufs -14` (padrão das redes).

## Ordem recomendada para um vídeo gravado

`transcrever` → `limpar` → (`reformatar` se não for 9:16) → `legendar` com o `limpo.transcript.json`.
Vários cortes: `transcrever` → escolher trechos → `cortes`.
Legende por último: reformatar em blur depois de legendar deixa a legenda pequena.

## Combinar com o modo CRIAR

Um vídeo editado pode virar cena de um vídeo animado: coloque o `.mp4` em `assets/` do projeto HyperFrames e use como `<video>` numa cena; o `transcript.json` serve de mapa de tempos (`beatmap.py` aceita o mesmo formato).

## Registrar

Ao terminar, anote em `memoria/historico.md` (tipo: edição, comandos usados, opções aprovadas — cor, fonte, pausa). Preferências que o usuário confirmar (ex.: "gostei da legenda em maiúsculas") vão para `perfil.md` → Preferências fixas e viram o padrão das próximas edições.
