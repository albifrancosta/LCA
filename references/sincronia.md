# Sincronizar animação com a voz

A voz manda no tempo. Nunca estime tempo de cena — meça no `transcript.json` / `BEATS.json`.

## BEATS.json (saída do beatmap.py)

```json
{
  "fps": 30,
  "duration": 31.42,
  "scenes":   [{"id": "s1", "start": 0.0, "end": 3.12, "text": "Você ainda perde 3 horas…", "words": [0, 7]}],
  "keywords": [{"word": "3 horas", "start": 1.84, "end": 2.40, "scene": "s1"}],
  "pauses":   [{"start": 3.12, "end": 3.41}],
  "groups":   [{"start": 0.0, "end": 0.62, "text": "Você ainda", "key": false}]
}
```

- `scenes` — uma por linha do roteiro, casadas pela posição das palavras (não pelo texto). Já vêm com o recuo de 2 frames.
- `keywords` — palavras em **negrito** no roteiro, mais números detectados.
- `groups` — grupos de legenda de 2–3 palavras, quebrando em pausa ≥ 150 ms ou fim de frase.
- Sem `--roteiro`, as cenas saem por frase (pontuação/pausa ≥ 350 ms).

## Regras de tempo

1. **Entrada da cena** = `start` da 1ª palavra − 2 frames. O visual chega um tiquinho antes da fala.
2. **Corte** só em pausa ≥ 150 ms ou fim de frase. Nunca no meio de uma palavra.
3. **Palavra-chave** → uma ação visual que *termina de chegar* no `start` da palavra: número contando, texto em punch-in, destaque de cor, zoom no print. Entrada de 8–12 frames, então começa ~0,3 s antes.
4. **Respiro**: depois de uma palavra-chave grande, segure 10–15 frames antes de mexer de novo.
5. **Ritmo**: troca visual a cada 1,5–2,5 s em vertical (corte, zoom, texto novo). Confira `padroes.md` → Ritmo.
6. **Silêncio > 0,6 s**: preencha com movimento lento de câmera ou SFX, nunca tela parada.
7. **Final**: CTA fica na tela até 0,8 s depois da última palavra.

## Legendas

- 2–3 palavras por grupo (alta energia). Palavra falada agora em cor de destaque; palavra-chave maior/negrito.
- Posição: vertical y ≈ 62–72% da altura, dentro da área segura; nunca em cima do print/rosto principal.
- Legenda é overlay por cima do filme (`captions-overlay`), não uma faixa reservada.
- Fonte e cor: `perfil.md` → Marca; senão `padroes.md` → Legenda.

## Áudio

- Voz −16 LUFS. Trilha 18–22 dB abaixo da voz.
- SFX curtos (whoosh, pop, click) **no frame** de cada movimento grande — via `/media-use`.
- Música desde o frame 0; um "drop" no início da Virada funciona bem.
