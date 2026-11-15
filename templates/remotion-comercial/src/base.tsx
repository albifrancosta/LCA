import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame } from "remotion";
import { loadFont } from "@remotion/google-fonts/Montserrat";
import falas from "./falas.json";

export const { fontFamily } = loadFont("normal", { weights: ["600", "700", "800", "900"], subsets: ["latin"] });

export const FPS = 30;
export const W = 1080;
export const H = 1920;

// Identidade tirada da tela do Assistente MinhaMarca (azul do botão, lateral azul-marinho).
export const C = {
  azul: "#1F6FEB",
  azulEsc: "#1557C9",
  azulClaro: "#EAF2FF",
  marinho: "#0B1B3F",
  marinho2: "#16306B",
  texto: "#0F172A",
  branco: "#FFFFFF",
  verde: "#16A34A",
  ambar: "#F59E0B",
  vermelho: "#E5484D",
  parede: "#F4EADF",
  piso: "#E0CFB8",
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Tempo absoluto em segundos (as cenas não usam Sequence, então o quadro é sempre absoluto). */
export const useT = () => useCurrentFrame() / FPS;

export const prog = (t: number, a: number, b: number, easing = Easing.out(Easing.cubic)) =>
  interpolate(t, [a, b], [0, 1], { ...clamp, easing });

export const mola = (t: number, a: number, config = { damping: 14, stiffness: 160 }) =>
  t < a ? 0 : spring({ frame: (t - a) * FPS, fps: FPS, config });

// ---------------------------------------------------------------- falas (geradas por timeline_comercial.py)
export type Palavra = { text: string; start: number; end: number };
export type Fala = { id: string; quem: string; inicio: number; fim: number; palavras: Palavra[]; amplitude: number[] };
export const FALAS = falas as Fala[];

export const amp = (id: string, t: number) => {
  const f = FALAS.find((x) => x.id === id);
  if (!f) return 0;
  const i = Math.floor((t - f.inicio) * FPS);
  return i >= 0 && i < f.amplitude.length ? f.amplitude[i] : 0;
};

/** Amplitude de quem está falando agora (para a boca e a onda acompanharem a voz real). */
export const vozDe = (quem: string, t: number) =>
  FALAS.filter((f) => f.quem === quem).reduce((m, f) => Math.max(m, amp(f.id, t)), 0);

// ---------------------------------------------------------------- cena com corte seco + leve assentamento
export const Cena: React.FC<{ de: number; ate: number; fundo?: string; children: React.ReactNode }> = ({ de, ate, fundo, children }) => {
  const t = useT();
  if (t < de || t >= ate) return null;
  const e = prog(t, de, de + 0.3);
  return <AbsoluteFill style={{ background: fundo, transform: `scale(${1.05 - 0.05 * e})` }}>{children}</AbsoluteFill>;
};

// ---------------------------------------------------------------- brilho do Assistente MinhaMarca
export const Brilho: React.FC<{ x?: number; y?: number; r: number; cor?: string; giro?: number }> = ({ x = 0, y = 0, r, cor = C.branco, giro = 0 }) => (
  <path
    transform={`translate(${x} ${y}) rotate(${giro}) scale(${r})`}
    d="M0 -1 C0.13 -0.13 0.13 -0.13 1 0 C0.13 0.13 0.13 0.13 0 1 C-0.13 0.13 -0.13 0.13 -1 0 C-0.13 -0.13 -0.13 -0.13 0 -1Z"
    fill={cor}
  />
);

export const Logo: React.FC<{ tamanho: number; cor?: string }> = ({ tamanho, cor = C.branco }) => (
  <div style={{ display: "flex", alignItems: "center", gap: tamanho * 0.28 }}>
    <svg width={tamanho} height={tamanho} viewBox="-50 -50 100 100">
      <circle r={50} fill={C.azul} />
      <Brilho r={30} x={-4} y={4} />
      <Brilho r={11} x={24} y={-22} />
    </svg>
    <div style={{ fontFamily, fontWeight: 900, fontSize: tamanho * 0.62, color: cor, letterSpacing: -1 }}>
      MinhaMarca <span style={{ fontWeight: 700, opacity: 0.85 }}>ERP</span>
    </div>
  </div>
);

// ---------------------------------------------------------------- texto grande (informação que precisa ser lida)
export type Linha = { t: string; cor?: string };
export const TextoGrande: React.FC<{ linhas: Linha[]; de: number; topo?: number; tamanho?: number; caixa?: string; corTexto?: string }> = ({
  linhas, de, topo = 230, tamanho = 92, caixa, corTexto = C.branco,
}) => {
  const t = useT();
  return (
    <div style={{ position: "absolute", top: topo, left: 60, right: 60, display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
      {linhas.map((l, i) => {
        const s = mola(t, de + i * 0.18, { damping: 15, stiffness: 190 });
        return (
          <div
            key={i}
            style={{
              fontFamily, fontWeight: 900, fontSize: tamanho, lineHeight: 1.04, textAlign: "center",
              color: l.cor ?? corTexto, background: caixa, padding: caixa ? "8px 30px 14px" : 0, borderRadius: 22,
              opacity: Math.min(1, s * 1.4), transform: `translateY(${(1 - s) * 60}px) scale(${0.9 + 0.1 * s})`,
              textShadow: caixa ? "none" : "0 6px 28px rgba(0,0,0,.25)",
            }}
          >
            {l.t}
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- selo de simulação
export const Selo: React.FC<{ texto: string; de: number; topo?: number }> = ({ texto, de, topo = 110 }) => {
  const t = useT();
  const s = mola(t, de);
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: s }}>
      <div
        style={{
          fontFamily, fontWeight: 800, fontSize: 34, letterSpacing: 4, color: "#7A4B00", background: "#FFF4D6",
          border: `4px dashed ${C.ambar}`, borderRadius: 999, padding: "10px 34px", transform: `scale(${0.8 + 0.2 * s})`,
        }}
      >
        {texto}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- onda sonora (segue a amplitude real da voz)
export const Onda: React.FC<{ nivel: (t: number) => number; largura: number; altura: number; cor: string; barras?: number }> = ({
  nivel, largura, altura, cor, barras = 30,
}) => {
  const t = useT();
  const passo = largura / barras;
  return (
    <div style={{ width: largura, height: altura, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      {Array.from({ length: barras }, (_, k) => {
        const v = nivel(t - (k % 9) * 0.035) * (0.45 + 0.55 * Math.abs(Math.sin(k * 1.9 + t * 7)));
        return <div key={k} style={{ width: passo * 0.55, height: Math.max(passo * 0.55, v * altura), borderRadius: 99, background: cor }} />;
      })}
    </div>
  );
};

// ---------------------------------------------------------------- legenda palavra a palavra
type Grupo = { quem: string; palavras: Palavra[]; start: number; end: number };
const GRUPOS: Grupo[] = (() => {
  const out: Grupo[] = [];
  for (const f of FALAS) {
    let atual: Palavra[] = [];
    const fecha = () => {
      if (atual.length) out.push({ quem: f.quem, palavras: atual, start: atual[0].start, end: atual[atual.length - 1].end });
      atual = [];
    };
    f.palavras.forEach((p, i) => {
      const ant = f.palavras[i - 1];
      if (atual.length >= 4 || (ant && p.start - ant.end > 0.35)) fecha();
      atual.push(p);
      if (/[.,?!:…]$/.test(p.text)) fecha();
    });
    fecha();
  }
  return out;
})();

/** Legenda do padrão ilustrado (medida na referência viral): caixa verde só na palavra falada, letra pequena. */
export const LegendaHistoria: React.FC<{ ocultarDe?: number; topo?: number }> = ({ ocultarDe = Infinity, topo = 1300 }) => {
  const t = useT();
  if (t >= ocultarDe) return null;
  const i = GRUPOS.findIndex((g, k) => t >= g.start - 0.05 && t < Math.min(g.end + 0.25, GRUPOS[k + 1]?.start ?? Infinity));
  if (i < 0) return null;
  const g = GRUPOS[i];
  return (
    <div style={{ position: "absolute", top: topo, left: 90, right: 90, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 12px" }}>
      {g.palavras.map((p, k) => {
        const on = t >= p.start && (k === g.palavras.length - 1 || t < g.palavras[k + 1].start);
        return (
          <span
            key={k}
            style={{
              fontFamily, fontWeight: 800, fontSize: 52, lineHeight: 1.3, padding: "0 9px", borderRadius: 11, color: C.branco,
              background: on ? "#87C968" : "transparent", textShadow: on ? "none" : "0 2px 8px rgba(0,0,0,.9), 0 0 3px rgba(0,0,0,.9)",
            }}
          >
            {p.text}
          </span>
        );
      })}
    </div>
  );
};

export const Legenda: React.FC<{ ocultarDe?: number; topo?: number }> = ({ ocultarDe = Infinity, topo = 1330 }) => {
  const t = useT();
  if (t >= ocultarDe) return null;
  const i = GRUPOS.findIndex((g, k) => t >= g.start - 0.05 && t < Math.min(g.end + 0.25, GRUPOS[k + 1]?.start ?? Infinity));
  if (i < 0) return null;
  const g = GRUPOS[i];
  const pop = mola(t, g.start - 0.05, { damping: 14, stiffness: 240 });
  const tecnico = g.quem === "tecnico";
  return (
    <div style={{ position: "absolute", top: topo, left: 60, right: 60, display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      {tecnico ? (
        <div style={{ fontFamily, fontWeight: 800, fontSize: 28, letterSpacing: 3, color: C.marinho, background: C.ambar, borderRadius: 10, padding: "4px 16px" }}>
          TÉCNICO
        </div>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "4px 14px", transform: `scale(${0.85 + 0.15 * pop})` }}>
        {g.palavras.map((p, k) => {
          const on = t >= p.start && (k === g.palavras.length - 1 || t < g.palavras[k + 1].start);
          return (
            <span
              key={k}
              style={{
                fontFamily, fontWeight: 900, fontSize: 66, lineHeight: 1.15, padding: "0 14px 4px", borderRadius: 14,
                color: C.branco, background: on ? (tecnico ? C.ambar : C.azul) : "transparent",
                textShadow: on ? "none" : "0 0 6px rgba(0,0,0,.95), 0 4px 18px rgba(0,0,0,.9)",
              }}
            >
              {p.text.replace(/[.,;:…]+$/, "")}
            </span>
          );
        })}
      </div>
    </div>
  );
};
