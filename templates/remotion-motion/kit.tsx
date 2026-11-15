import React from "react";
import { AbsoluteFill, Easing, Img, staticFile } from "remotion";
import { Logo, fontFamily, mola, prog, useT } from "./base";
import { COR, FundoMotion } from "./motion";

// KIT DE CENAS — peças prontas tiradas das composições aprovadas (Campanha "Um dia", Cadê o técnico híbrido, Espelho).
// Use-as para montar um vídeo novo só com chamadas, sem reescrever componentes (economiza tokens).
// Tudo em tempo ABSOLUTO (segundos), amarrado às palavras da voz pelo helper `criarTempos`.

export type Palavra = { text: string; start: number; end: number };
export type Fala = { id: string; inicio: number; fim: number; palavras: Palavra[] };

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");

/**
 * Tempos amarrados à voz.
 *   const { fala, p, naBatida } = criarTempos(falasJson, batidaJson?.batidas);
 *   p("n03", "seguranca", 13.3)  → início da 1ª palavra que começa com "seguranca" na fala n03 (padrão se não achar)
 *   p("n03", "voce", 17.7, 2)    → 2ª ocorrência
 *   naBatida(t)                   → encaixa um corte na batida mais próxima (≤ 0,25 s), senão devolve t
 */
export const criarTempos = (falasJson: unknown, batidas: number[] = []) => {
  const FALAS = falasJson as Fala[];
  const fala = (id: string) => FALAS.find((f) => f.id === id) as Fala;
  const p = (id: string, txt: string, padrao: number, n = 1) => {
    const ws = fala(id)?.palavras.filter((w) => norm(w.text).startsWith(norm(txt))) ?? [];
    return ws[n - 1]?.start ?? padrao;
  };
  const naBatida = (t: number, tolerancia = 0.25) => {
    if (!batidas.length) return t;
    const b = batidas.reduce((m, x) => (Math.abs(x - t) < Math.abs(m - t) ? x : m), batidas[0]);
    return Math.abs(b - t) <= tolerancia ? b : t;
  };
  return { FALAS, fala, p, naBatida };
};

/** Cena visível entre `de` e `ate` (entrada rápida). */
export const Cena: React.FC<{ de: number; ate: number; children: React.ReactNode }> = ({ de, ate, children }) => {
  const t = useT();
  if (t < de || t >= ate) return null;
  return <AbsoluteFill style={{ opacity: Math.min(1, 0.4 + prog(t, de, de + 0.2)) }}>{children}</AbsoluteFill>;
};

/** Ilustração em tela cheia com zoom lento (Ken Burns) e escurecimento em cima/embaixo para texto e legenda. */
export const Ilustracao: React.FC<{ src: string; de: number; ate: number; z?: [number, number]; foco?: [number, number] }> = ({ src, de, ate, z = [1, 1.08], foco = [0.5, 0.4] }) => {
  const t = useT();
  const e = z[0] + (z[1] - z[0]) * prog(t, de, ate, Easing.inOut(Easing.sin));
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#000" }}>
      <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${e})`, transformOrigin: `${foco[0] * 100}% ${foco[1] * 100}%` }} />
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,.35) 0%, transparent 25%, transparent 60%, rgba(0,0,0,.55) 100%)" }} />
    </AbsoluteFill>
  );
};

/** Horário grande no topo (marca cada virada do dia: "7h02", "18h"). */
export const Hora: React.FC<{ de: number; texto: string; cor?: string; topo?: number }> = ({ de, texto, cor = COR.amar, topo = 210 }) => {
  const t = useT();
  const s = mola(t, de, { damping: 10, stiffness: 220 });
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
      <div style={{ background: "rgba(0,0,0,.85)", borderRadius: 30, padding: "4px 40px", transform: `scale(${s})`, fontFamily, fontWeight: 900, fontSize: 120, color: cor, letterSpacing: 2 }}>{texto}</div>
    </div>
  );
};

/** Celular desenhado (moldura + cabeçalho). cor "#075E54" = estilo WhatsApp (fundo bege). */
export const Celular: React.FC<{ de: number; titulo: string; sub?: string; cor?: string; topo?: number; altura?: number; children: React.ReactNode }> = ({
  de, titulo, sub, cor = COR.card, topo = 360, altura = 1060, children,
}) => {
  const t = useT();
  const s = mola(t, de, { damping: 15, stiffness: 160 });
  return (
    <div style={{ position: "absolute", left: 150, top: topo, width: 780, height: altura, borderRadius: 70, background: "#020617", border: "12px solid #334155", overflow: "hidden", transform: `translateY(${(1 - s) * 900}px)`, boxShadow: "0 40px 90px rgba(0,0,0,.6)", fontFamily }}>
      <div style={{ height: 150, background: cor, display: "flex", flexDirection: "column", justifyContent: "flex-end", padding: "0 40px 22px" }}>
        <div style={{ fontWeight: 900, fontSize: 44, color: "#fff" }}>{titulo}</div>
        {sub ? <div style={{ fontWeight: 600, fontSize: 28, color: "rgba(255,255,255,.75)" }}>{sub}</div> : null}
      </div>
      <div style={{ position: "relative", height: altura - 150, background: cor === "#075E54" ? "#ECE5DD" : "#0B1220", padding: 30, boxSizing: "border-box" }}>{children}</div>
    </div>
  );
};

/** Balão de mensagem que estoura no tempo `de` (lado "dir" = enviado, verde). */
export const Bolha: React.FC<{ de: number; lado?: "esq" | "dir"; children: React.ReactNode; cor?: string }> = ({ de, lado = "esq", children, cor }) => {
  const t = useT();
  if (t < de) return null;
  const s = mola(t, de, { damping: 13, stiffness: 220 });
  const dir = lado === "dir";
  return (
    <div style={{ display: "flex", justifyContent: dir ? "flex-end" : "flex-start", marginBottom: 18 }}>
      <div style={{ maxWidth: "82%", background: cor ?? (dir ? "#DCF8C6" : "#fff"), color: "#111", borderRadius: 26, padding: "18px 26px", fontSize: 38, fontWeight: 600, transform: `scale(${s})`, transformOrigin: dir ? "right top" : "left top", boxShadow: "0 2px 4px rgba(0,0,0,.15)" }}>
        {children}
      </div>
    </div>
  );
};

/** Círculo de toque do dedo (botão "Aprovar", "Iniciar"...). */
export const Toque: React.FC<{ x: number; y: number; de: number }> = ({ x, y, de }) => {
  const t = useT();
  const q = prog(t, de, de + 0.45);
  if (t < de || q >= 1) return null;
  return <div style={{ position: "absolute", left: x - 45, top: y - 45, width: 90, height: 90, borderRadius: 99, border: `${9 * (1 - q)}px solid rgba(255,255,255,.95)`, transform: `scale(${0.6 + q})` }} />;
};

/** Ícones de ramo desenhados em código: "cftv" | "ar" | "predial" | "ti". */
export const IconeRamo: React.FC<{ tipo: string; tamanho?: number }> = ({ tipo, tamanho = 150 }) => (
  <svg width={tamanho} height={tamanho} viewBox="0 0 100 100" fill="none" stroke="#fff" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round">
    {tipo === "cftv" && (<><rect x={18} y={30} width={50} height={26} rx={6} /><circle cx={58} cy={43} r={7} /><path d="M30 56 L30 74 L16 74" /><path d="M68 40 L84 34 L84 52 L68 48" /></>)}
    {tipo === "ar" && (<><rect x={12} y={22} width={76} height={30} rx={8} /><path d="M20 42 L80 42" /><path d="M30 62 L26 80 M50 62 L50 82 M70 62 L74 80" /></>)}
    {tipo === "predial" && (<><rect x={24} y={14} width={52} height={72} rx={4} /><path d="M36 28 h8 M56 28 h8 M36 44 h8 M56 44 h8 M36 60 h8 M56 60 h8" /><path d="M44 86 L44 72 L56 72 L56 86" /></>)}
    {tipo === "ti" && (<><rect x={14} y={20} width={72} height={46} rx={6} /><path d="M40 80 L60 80 M50 66 L50 80" /><path d="M36 44 a20 20 0 0 1 28 0 M42 52 a10 10 0 0 1 16 0" /></>)}
  </svg>
);

/** Cartão grande em tela cheia, um por vez (o "vou resumir"): itens trocam no tempo de cada um. */
export const CartoesUmPorVez: React.FC<{ itens: { titulo: string; sub?: string; t: number; selo?: boolean; icone?: React.ReactNode }[]; topo?: number }> = ({ itens, topo = 470 }) => {
  const t = useT();
  const i = itens.reduce((acc, it, k) => (t >= it.t ? k : acc), -1);
  if (i < 0) return null;
  const it = itens[i];
  const s = mola(t, it.t, { damping: 12, stiffness: 240 });
  return (
    <div key={it.titulo} style={{ position: "absolute", left: 100, right: 100, top: topo, height: 720, borderRadius: 50, background: COR.card, borderTop: `16px solid ${COR.verde}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 26, transform: `translateY(${(1 - s) * 800}px) scale(${0.9 + 0.1 * s})`, fontFamily }}>
      {it.icone ?? <div style={{ width: 170, height: 170, borderRadius: 99, background: COR.verde, color: COR.navy, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 900, fontSize: 110 }}>✓</div>}
      <div style={{ fontWeight: 900, fontSize: 88, color: "#fff", textAlign: "center", padding: "0 30px" }}>{it.titulo}</div>
      {it.sub ? <div style={{ fontWeight: 700, fontSize: 46, color: COR.cinza, textAlign: "center" }}>{it.sub}</div> : null}
      {it.selo ? <div style={{ fontWeight: 700, fontSize: 28, color: COR.amar, letterSpacing: 3 }}>SIMULAÇÃO DO FLUXO</div> : null}
      <div style={{ position: "absolute", bottom: 30, display: "flex", gap: 16 }}>
        {itens.map((_, k) => <div key={k} style={{ width: 22, height: 22, borderRadius: 99, background: k <= i ? COR.verde : "#475569" }} />)}
      </div>
    </div>
  );
};

/** Virada: tela preta, frase digitando, pílula verde estoura na revelação (som: riser antes + golpe em `revelacao`). */
export const Virada: React.FC<{ de: number; frase: string; pilula: string; pilulaDe: number; revelacao: number }> = ({ de, frase, pilula, pilulaDe, revelacao }) => {
  const t = useT();
  const n = Math.round(frase.length * prog(t, de, de + 1.8));
  const s = mola(t, revelacao, { damping: 9, stiffness: 220 });
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ opacity: prog(t, revelacao, revelacao + 0.4) }}><FundoMotion de={revelacao} /></AbsoluteFill>
      <div style={{ position: "absolute", top: 560, left: 60, right: 60, textAlign: "center", fontFamily, fontWeight: 900, fontSize: 88, color: "#fff" }}>{frase.slice(0, n)}</div>
      {t >= pilulaDe ? (
        <div style={{ position: "absolute", top: 900, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
          <div style={{ background: COR.verde, color: COR.navy, borderRadius: 70, padding: "18px 60px", fontFamily, fontWeight: 900, fontSize: 100, transform: `scale(${t < revelacao ? 0.85 : s})`, opacity: t < revelacao ? prog(t, pilulaDe, pilulaDe + 0.3) : 1, boxShadow: `0 0 ${70 * (1 - prog(t, revelacao, revelacao + 0.8))}px 24px rgba(135,201,104,.6)` }}>{pilula}</div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Robô oficial da MinhaMarca (copie `robo-aceno.png` e `robo-joinha.png` para public/robo/): sobe acenando, joinha no CTA. */
export const Robo: React.FC<{ de: number; joinha: number; largura?: number }> = ({ de, joinha, largura = 530 }) => {
  const t = useT();
  if (t < de - 0.1) return null;
  const sobe = mola(t, de, { damping: 13, stiffness: 120 });
  const ok = t >= joinha;
  const pulo = ok ? mola(t, joinha, { damping: 7, stiffness: 300 }) : 1;
  const balanco = Math.sin((t - de) * 2.4) * 2.5;
  const aceno = ok ? 0 : Math.sin((t - de) * 9) * 4;
  return (
    <div style={{ position: "absolute", left: "50%", bottom: -90, width: largura, marginLeft: -largura / 2, transform: `translateY(${(1 - sobe) * 700 - (ok ? 30 * (pulo - 1) : 0)}px) rotate(${balanco + aceno}deg) scale(${ok ? 0.96 + 0.04 * pulo : 1})`, transformOrigin: "50% 100%" }}>
      <Img src={staticFile(ok ? "robo/robo-joinha.png" : "robo/robo-aceno.png")} style={{ width: "100%", filter: "drop-shadow(0 20px 40px rgba(0,0,0,.5))" }} />
    </div>
  );
};

/** Assinatura padrão da MinhaMarca: logo → "Menos operação." → "Mais estratégia." → botão CTA pulsando → site, com o robô. */
export const Assinatura: React.FC<{ de: number; logo: number; menos: number; mais: number; peca: number; site?: string; robo?: boolean; cta?: string }> = ({
  de, logo, menos, mais, peca, site = "Teste grátis · www.minhamarca.com.br", robo = true, cta = "Peça uma demonstração",
}) => {
  const t = useT();
  const sl = mola(t, logo, { damping: 12, stiffness: 140 });
  const s1 = mola(t, menos);
  const s2 = mola(t, mais);
  const pulso = t > peca + 0.6 ? 1 + 0.04 * Math.sin((t - peca) * 6) : mola(t, peca, { damping: 11, stiffness: 180 });
  return (
    <>
      <FundoMotion de={de} />
      <div style={{ position: "absolute", top: 520, left: 0, right: 0, display: "flex", justifyContent: "center", transform: `scale(${sl}) translateY(${(1 - sl) * 60}px)` }}><Logo tamanho={170} /></div>
      <div style={{ position: "absolute", top: 790, left: 0, right: 0, textAlign: "center", fontFamily, fontWeight: 900, fontSize: 90, lineHeight: 1.15 }}>
        <div style={{ color: "#E2E8F0", opacity: s1, transform: `translateY(${(1 - s1) * 40}px)` }}>Menos operação.</div>
        <div style={{ color: COR.verde, opacity: s2, transform: `translateY(${(1 - s2) * 40}px)` }}>Mais estratégia.</div>
      </div>
      <div style={{ position: "absolute", top: 1100, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 26 }}>
        <div style={{ background: COR.verde, color: COR.navy, borderRadius: 999, padding: "28px 60px", fontFamily, fontWeight: 900, fontSize: 62, transform: `scale(${t < peca ? 0 : pulso})`, boxShadow: "0 0 0 12px rgba(135,201,104,.25), 0 20px 60px rgba(0,0,0,.4)" }}>{cta}</div>
        <div style={{ fontFamily, fontWeight: 800, fontSize: 40, color: "#fff", opacity: prog(t, peca + 0.8, peca + 1.2) }}>{site}</div>
      </div>
      {robo ? <Robo de={logo} joinha={peca} /> : null}
    </>
  );
};

/** Legenda verde palavra por palavra (grupos de até 4 palavras; quebra em pausa > 0,35 s ou pontuação). */
export const gruposDe = (FALAS: Fala[]) => {
  const out: { palavras: Palavra[]; start: number; end: number }[] = [];
  for (const f of FALAS) {
    let atual: Palavra[] = [];
    const fecha = () => {
      if (atual.length) out.push({ palavras: atual, start: atual[0].start, end: atual[atual.length - 1].end });
      atual = [];
    };
    f.palavras.forEach((w, i) => {
      const ant = f.palavras[i - 1];
      if (atual.length >= 4 || (ant && w.start - ant.end > 0.35)) fecha();
      atual.push(w);
      if (/[.,?!:…]$/.test(w.text)) fecha();
    });
    fecha();
  }
  return out;
};
export const Legenda: React.FC<{ grupos: ReturnType<typeof gruposDe>; topo?: number }> = ({ grupos, topo = 1500 }) => {
  const t = useT();
  const i = grupos.findIndex((g, k) => t >= g.start - 0.05 && t < Math.min(g.end + 0.25, grupos[k + 1]?.start ?? Infinity));
  if (i < 0) return null;
  const g = grupos[i];
  return (
    <div style={{ position: "absolute", top: topo, left: 80, right: 80, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 12px" }}>
      {g.palavras.map((w, k) => {
        const on = t >= w.start && (k === g.palavras.length - 1 || t < g.palavras[k + 1].start);
        return (
          <span key={k} style={{ fontFamily, fontWeight: 800, fontSize: 50, lineHeight: 1.3, padding: "0 9px", borderRadius: 11, color: "#fff", background: on ? COR.verde : "transparent", textShadow: on ? "none" : "0 2px 8px rgba(0,0,0,.95)" }}>
            {w.text}
          </span>
        );
      })}
    </div>
  );
};
