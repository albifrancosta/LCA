# Biblioteca de motion (grátis) — `motion.tsx`

Camadas de motion graphics prontas para qualquer vídeo da skill. Tudo em código (Remotion), sem custo.
Nasceram no "Cadê o técnico?" híbrido (2026-11-05). Vitrine: `Demo.tsx` (14 s, uma peça a cada 2 s).

## Como usar
1. Copie `motion.tsx` (e `Demo.tsx` se quiser a vitrine) para `<projeto>/remotion/src/` — precisa do `base.tsx` do projeto (`fontFamily`, `mola`, `prog`, `useT`).
2. Importe: `import { Faixa, Contador, MapaRota } from "./motion";`
3. **Tempos absolutos em segundos, sempre amarrados à voz**: `palavra("n03", "mal", 20.5)` (ver `CadeTecnico.tsx`).

| Peça | Para quê | Exemplo |
|---|---|---|
| `FundoMotion` | fundo dos trechos em motion (grade azul-escura + brilho verde) | `<FundoMotion de={27.6} />` |
| `TextoCinetico` | gancho/frase forte, palavra por palavra batendo | `palavras=[{texto:"Cadê", t:0.2}, …]` |
| `Contador` | número da dor ou do ganho correndo e travando (som `tick` no `fim`) | `ini fim para formato rotulo` |
| `Faixa` | aviso/alarme ("3 CHAMADAS PERDIDAS"), `treme` para urgência | `de texto fundo topo` |
| `Carimbo` + `useTremor` | golpe de impacto ("QUEM FICA MAL?") com tremida da cena (som `hit`) | `de texto` / `transform: useTremor(t)` |
| `Balao` | dúvidas/pensamentos estourando ("Saiu?") | `de texto x y` |
| `Notificacao` | aviso de celular deslizando | `de titulo sub y destaque` |
| `LinhaDoTempo` | status que acendem (OS: Agendada → Concluída) | `etapas=[{nome, hora, t}]` |
| `GraficoBarras` | antes × depois, comparação | `barras=[{rotulo, valor, cor}]` |
| `MapaRota` | técnico a caminho: rota se desenha, pino anda, "Chegou ✓" | `ini fim origem destino eta` |

## Regras de movimento
- Chegada com mola (`mola`), saída rápida; nunca linear, exceto contagem e trajeto.
- Um instante parado antes do golpe; o golpe vem com `Carimbo` + `useTremor` + som `hit`.
- Nada de dissolver uma cena na outra: corte seco, cartão que vira, ou o elemento se transforma.
- Várias coisas pequenas se movem juntas (contador + barra + ícone), nunca só uma.
- Uma camada nova a cada 2–4 s nos trechos sem clipe (`verificar_retencao.py` confere).
- Legenda na altura 1450 quando há camadas no meio da tela.
- Som: cada camada que ENTRA pode ter um som; o que só se move (barra enchendo, pino andando) fica sem som — `som_pro.py` aplica.

## Kit de cenas (`kit.tsx`) — monte um vídeo só com chamadas
Copie `kit.tsx` + `motion.tsx` para `src/`. Exemplo (testado em 2026-11-05 no projeto da campanha, `KitTeste.tsx`):
```tsx
import falasJson from "./falas.json"; import batidaJson from "./batida.json";
import { Assinatura, Cena, CartoesUmPorVez, Legenda, Virada, criarTempos, gruposDe } from "./kit";
const { FALAS, fala, p, naBatida } = criarTempos(falasJson, batidaJson.batidas);
const G = gruposDe(FALAS);
// <Cena de={19.7} ate={naBatida(fala("n05").inicio - 0.4)}><Virada de={fala("n04").inicio} frase="Agora imagina o mesmo dia…" pilula="com a MinhaMarca" pilulaDe={p("n04","com",22.8)} revelacao={p("n04","marca",23.6)} /></Cena>
// <CartoesUmPorVez itens={[{ titulo: "Estoque", sub: "baixa sozinha na OS", t: p("n11","estoque",67) }]} />
// <Assinatura de={80.6} logo={p("n13","marca",81)} menos={p("n13","menos",82.7)} mais={p("n13","mais",83.9)} peca={p("n13","peca",85.3)} />  ← já inclui o robô
// <Legenda grupos={G} />
```
Peças: `criarTempos` (p, fala, naBatida), `Cena`, `Ilustracao`, `Hora`, `Celular`, `Bolha`, `Toque`, `IconeRamo`, `CartoesUmPorVez`, `Virada`, `Robo`, `Assinatura`, `gruposDe` + `Legenda`.
