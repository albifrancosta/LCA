# Padrões que funcionam (memória de aprendizado)

Como ler: **status** = Base (ponto de partida) · Teste (visto em 1–2 referências) · Confirmado (≥ 3 refs ou pontuação ≥ +3) · Evitar (pontuação ≤ −2).
**refs** = em quantos vídeos virais analisados apareceu. **pont.** = resultado nos vídeos do usuário (+1 funcionou, −1 não) — atualizado por `scripts/metricas.py`.
Ao criar: aplique Confirmado > Base > Teste (no máx. 2 de Teste por vídeo, para testar). Nunca aplique Evitar. Preferências fixas de `perfil.md` vencem qualquer padrão.

## Ângulo / compartilhamento
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P06 | Gatilho de compartilhamento explícito: o vídeo existe para alguém dizer "isso sou eu / manda pro sócio" (identificação com uma dor do dia a dia do público) | Base | 0 | 0 | — |

## Gancho
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P01 | Texto do gancho na tela já no frame 1, grande, ≤ 6 palavras | Base | 0 | 0 | — |
| P02 | Gancho com número concreto ("3 horas", "R$ 2 mil") | Base | 0 | 0 | — |
| P03 | 2–3 cortes/trocas visuais nos 3 primeiros segundos | Base | 0 | 0 | — |
| P04 | Imersão em 2ª pessoa: "Você está…" numa situação comum que vai dar errado | Base | 0 | 0 | — |
| P05 | Horário concreto como abertura e marcador de cada virada ("10h40…", "3h47…") | Base | 0 | 0 | — |
| P07 | Gancho visual que se entende sem som em 1 s (ex.: monitor "SEM SINAL") | Base | 0 | 0 | — |

## Ritmo / retenção
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P10 | Troca visual a cada 1,5–2,5 s (anúncio) ou ≤ 3,5 s (história) — checado por `verificar_retencao.py` | Base | 0 | 0 | — |
| P11 | Narração a ~2,6–3,0 palavras/s, sem pausas > 0,6 s | Base | 0 | 0 | — |
| P12 | Micro-revelação a cada 8–12 s (laço aberto que adia a resposta) | Base | 0 | 0 | — |
| P13 | Em história/suspense: ritmo lento intencional (plano ~8 s, fala ~2,3 palavras/s, pausas dramáticas) | Base | 0 | 0 | — |
| P14 | Re-gancho entre 40% e 50% do vídeo (virada, pergunta ou revelação) — onde a audiência mais cai | Base | 0 | 0 | — |

## Legenda / texto na tela
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P20 | Palavra a palavra, 2–3 por grupo, palavra atual destacada | Base | 0 | 0 | — |
| P21 | Palavra-chave maior e na cor da marca | Base | 0 | 0 | — |
| P22 | Caixa colorida arredondada atrás da palavra falada, texto branco, fonte pequena, meio da tela | Base | 0 | 0 | — |
| P23 | Sem legenda contínua: só textos-chave na tela, a narração conduz | Base | 0 | 0 | — |
| P24 | Número-chave na tela em amarelo/branco ("≈ 35 LITROS", "4 h 40 min") | Base | 0 | 0 | — |

## Movimento / visual
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P30 | Punch-in (zoom 1,0→1,08) no print quando a voz cita a função | Base | 0 | 0 | — |
| P31 | Número animado contando até o valor no tempo da palavra | Base | 0 | 0 | — |
| P32 | Transições contínuas (zoom-through / whip) em vez de fade | Base | 0 | 0 | — |
| P33 | Ilustração 2D por IA com personagem consistente em todas as cenas + câmera lenta em cada imagem | Base | 0 | 0 | — |
| P34 | POV de tela (celular/app/monitor) em tela cheia como parte da história | Base | 0 | 0 | — |
| P35 | Tela preta como pausa dramática antes da virada ou do fim | Base | 0 | 0 | — |
| P36 | Onomatopeia em quadrinho dentro da cena ("BIIIP!", "BZZZ!", "TRIM!") | Base | 0 | 0 | — |
| P37 | Camada gráfica no ritmo da fala a cada 2–4 s (contador, faixa, balão, notificação — `templates/remotion-motion/`) | Base | 0 | 0 | — |
| P38 | Golpe de impacto: instante parado + carimbo + tremida + som "hit" | Base | 0 | 0 | — |
| P39 | Sem dissolver cenas: corte seco, cartão que vira ou elemento que se transforma | Base | 0 | 0 | — |

## Áudio
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P40 | SFX curto em cada entrada grande de elemento | Base | 0 | 0 | — |
| P41 | Trilha com "drop"/troca na virada (problema → solução) | Base | 0 | 0 | — |
| P42 | Revelação no drop da música e trocas de cena no início do compasso (`batida.py`) | Base | 0 | 0 | — |
| P43 | Som com moderação: cada som tem causa visível, a maior parte do movimento fica sem som, ≤ 10 sons a cada 10 s, riser + golpe só na revelação (`som_pro.py`) | Base | 0 | 0 | — |

## Estrutura / CTA / final
| id | padrão | status | refs | pont. | evidências |
|----|--------|--------|------|-------|------------|
| P50 | Gancho → Problema → Virada → Prova → CTA | Base | 0 | 0 | — |
| P51 | CTA único, falado e escrito, últimos 3–5 s | Base | 0 | 0 | — |
| P52 | CTA interativo: escolha A ou B nos comentários + "próximo episódio" (série) | Base | 0 | 0 | — |
| P53 | Final que conversa com o começo (mesma imagem/frase resolvida) para incentivar reassistir | Base | 0 | 0 | — |

## Evitar
| id | padrão | motivo | evidências |
|----|--------|--------|------------|
