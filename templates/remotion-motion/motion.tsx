import React from "react";
import { AbsoluteFill } from "remotion";
import { fontFamily, mola, prog, useT } from "./base";

// Biblioteca de camadas de motion graphics (grátis, tudo em código). Tempos SEMPRE absolutos em segundos,
// amarrados às palavras da voz (palavra("n03", "mal", 20.5)). Copie este arquivo para <projeto>/remotion/src/
// junto com base.tsx. Peças nascidas no "Cadê o técnico?" híbrido (2026-11-05).

export const COR = { navy: "#0F172A", card: "#1E293B", verde: "#87C968", cinza: "#94A3B8", verm: "#EF4444", amar: "#FACC15", branco: "#FFFFFF" };
const W = 1080;

/** Fundo dos trechos em motion: azul-escuro com grade que desliza e um brilho verde suave. */
export const FundoMotion: React.FC<{ de: number; brilho?: string }> = ({ de, brilho = "rgba(135,201,104,.18)" }) => {
  const t = useT();
  const off = ((t - de) * 30) % 60;
  return (
    <AbsoluteFill style={{ background: COR.navy, overflow: "hidden" }}>
      <AbsoluteFill style={{ backgroundImage: "linear-gradient(#1a2540 2px, transparent 2px), linear-gradient(90deg, #1a2540 2px, transparent 2px)", backgroundSize: "60px 60px", backgroundPosition: `0 ${off}px` }} />
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 38%, ${brilho}, transparent 55%)` }} />
    </AbsoluteFill>
  );
};

/** Faixa de destaque (ex.: "3 CHAMADAS PERDIDAS"). Abre na horizontal; `treme` para alarme. */
export const Faixa: React.FC<{ de: number; texto: React.ReactNode; fundo?: string; cor?: string; topo?: number; tam?: number; treme?: boolean }> = ({
  de, texto, fundo = COR.verm, cor = COR.branco, topo = 1200, tam = 80, treme,
}) => {
  const t = useT();
  if (t < de) return null;
  const s = mola(t, de, { damping: 11, stiffness: 220 });
  const dx = treme ? Math.sin((t - de) * 55) * 7 * (1 - prog(t, de, de + 1.2)) : 0;
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
      <div style={{ background: fundo, color: cor, fontFamily, fontWeight: 900, fontSize: tam, padding: "14px 44px", borderRadius: 26, transform: `translateX(${dx}px) scaleX(${s})`, boxShadow: "0 12px 40px rgba(0,0,0,.45)", whiteSpace: "nowrap" }}>
        {texto}
      </div>
    </div>
  );
};

/** Texto cinético: cada palavra BATE no seu tempo (escala 1,6 → 1). Use os tempos das palavras da voz. */
export const TextoCinetico: React.FC<{ palavras: { texto: string; t: number; cor?: string }[]; topo?: number; tam?: number; largura?: number }> = ({
  palavras, topo = 700, tam = 120, largura = 940,
}) => {
  const t = useT();
  return (
    <div style={{ position: "absolute", top: topo, left: (W - largura) / 2, width: largura, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 26px", fontFamily, fontWeight: 900, fontSize: tam, lineHeight: 1.05, textTransform: "uppercase" }}>
      {palavras.map((p, i) => {
        if (t < p.t) return <span key={i} style={{ opacity: 0 }}>{p.texto}</span>;
        const s = mola(t, p.t, { damping: 12, stiffness: 320 });
        return <span key={i} style={{ color: p.cor ?? COR.branco, transform: `scale(${1.6 - 0.6 * s})`, opacity: Math.min(1, s * 2), display: "inline-block", textShadow: "0 6px 24px rgba(0,0,0,.5)" }}>{p.texto}</span>;
      })}
    </div>
  );
};

/** Contador que corre de `de_` até `para` entre `ini` e `fim` (som "tick" no `fim`, quando trava). */
export const Contador: React.FC<{ ini: number; fim: number; de_?: number; para: number; formato?: (n: number) => string; rotulo?: string; topo?: number; tam?: number; cor?: string; caixa?: boolean }> = ({
  ini, fim, de_ = 0, para, formato = (n) => String(Math.round(n)), rotulo, topo = 600, tam = 170, cor = COR.verde, caixa = true,
}) => {
  const t = useT();
  if (t < ini) return null;
  const s = mola(t, ini, { damping: 12, stiffness: 220 });
  const v = de_ + (para - de_) * prog(t, ini, fim);
  const trava = t >= fim ? prog(t, fim, fim + 0.25) : 0;
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
      <div style={{ background: caixa ? "rgba(15,23,42,.94)" : "transparent", borderRadius: 34, padding: "24px 60px", transform: `scale(${s * (1 + 0.08 * Math.sin(trava * Math.PI))})`, textAlign: "center", fontFamily, boxShadow: caixa ? "0 14px 40px rgba(0,0,0,.45)" : "none" }}>
        <div style={{ fontWeight: 900, fontSize: tam, lineHeight: 1, color: cor, fontVariantNumeric: "tabular-nums" }}>{formato(v)}</div>
        {rotulo ? <div style={{ fontWeight: 600, fontSize: tam * 0.32, color: COR.branco, marginTop: 8 }}>{rotulo}</div> : null}
      </div>
    </div>
  );
};

/** Carimbo que bate do alto (escala 2,4 → 1). Combine com useTremor e som "hit"/"carimbo". */
export const Carimbo: React.FC<{ de: number; texto: string; cor?: string; topo?: number; giro?: number; tam?: number }> = ({ de, texto, cor = COR.verm, topo = 1150, giro = -6, tam = 96 }) => {
  const t = useT();
  if (t < de) return null;
  const p = prog(t, de, de + 0.18);
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: Math.min(1, p * 2) }}>
      <div style={{ transform: `rotate(${giro}deg) scale(${2.4 - 1.4 * p})`, border: `14px solid ${cor}`, borderRadius: 24, padding: "10px 40px", background: "rgba(0,0,0,.6)", color: cor, fontFamily, fontWeight: 900, fontSize: tam, letterSpacing: 2, whiteSpace: "nowrap" }}>{texto}</div>
    </div>
  );
};

/** Tremida de câmera: use o retorno como `transform` da cena; `impacto` = segundo do golpe. */
export const useTremor = (impacto: number, forca = 14, dur = 0.35) => {
  const t = useT();
  if (t < impacto || t > impacto + dur) return "none";
  const k = Math.sin((t - impacto) * 90) * forca * (1 - prog(t, impacto, impacto + dur));
  return `translate(${k}px, ${k * 0.6}px)`;
};

/** Balão de pensamento/fala que estoura (ex.: "Saiu?" "No trânsito?"). */
export const Balao: React.FC<{ de: number; texto: string; x: number; y: number; tam?: number }> = ({ de, texto, x, y, tam = 72 }) => {
  const t = useT();
  if (t < de) return null;
  const s = mola(t, de, { damping: 9, stiffness: 240 });
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: `scale(${s})`, transformOrigin: "left bottom", background: COR.branco, color: COR.navy, fontFamily, fontWeight: 900, fontSize: tam, padding: "14px 42px", borderRadius: 70, boxShadow: "0 10px 30px rgba(0,0,0,.35)", whiteSpace: "nowrap" }}>
      {texto}
      <div style={{ position: "absolute", left: 50, bottom: -22, width: 0, height: 0, borderLeft: "18px solid transparent", borderRight: "18px solid transparent", borderTop: `26px solid ${COR.branco}` }} />
    </div>
  );
};

/** Notificação de celular que desliza da direita. */
export const Notificacao: React.FC<{ de: number; titulo: string; sub?: string; x?: number; y: number; largura?: number; destaque?: boolean }> = ({ de, titulo, sub, x = 190, y, largura = 700, destaque }) => {
  const t = useT();
  if (t < de) return null;
  const s = mola(t, de, { damping: 15, stiffness: 170 });
  return (
    <div style={{ position: "absolute", left: x, top: y, width: largura, borderRadius: 32, background: destaque ? COR.verde : COR.branco, padding: "26px 36px", transform: `translateX(${(1 - s) * 520}px)`, opacity: s, boxShadow: "0 14px 40px rgba(0,0,0,.45)", fontFamily }}>
      <div style={{ fontWeight: 900, fontSize: 46, color: COR.navy, whiteSpace: "nowrap" }}>{titulo}</div>
      {sub ? <div style={{ fontWeight: 600, fontSize: 38, color: "#475569", marginTop: 8 }}>{sub}</div> : null}
    </div>
  );
};

/** Linha do tempo de status: cada etapa acende (✓ verde) no seu tempo; a linha entre elas enche. */
export const LinhaDoTempo: React.FC<{ etapas: { nome: string; hora?: string; t: number }[]; topo?: number; passo?: number; aparece?: number }> = ({ etapas, topo = 660, passo = 170, aparece = 0 }) => {
  const t = useT();
  const vis = mola(t, aparece, { damping: 15, stiffness: 170 });
  return (
    <>
      {etapas.map((e, i) => {
        const on = t >= e.t;
        const y = topo + i * passo;
        const s = on ? mola(t, e.t, { damping: 9, stiffness: 260 }) : 0;
        const ult = i === etapas.length - 1;
        return (
          <React.Fragment key={e.nome}>
            {!ult ? (
              <div style={{ position: "absolute", left: 175, top: y + 100, width: 10, height: passo - 100, background: "#334155", opacity: vis }}>
                <div style={{ width: "100%", height: `${100 * prog(t, e.t, etapas[i + 1].t)}%`, background: COR.verde }} />
              </div>
            ) : null}
            <div style={{ position: "absolute", left: 130, top: y, width: 100, height: 100, borderRadius: 99, background: "#334155", opacity: vis }} />
            <div style={{ position: "absolute", left: 130, top: y, width: 100, height: 100, borderRadius: 99, background: COR.verde, transform: `scale(${s})`, display: "flex", alignItems: "center", justifyContent: "center", color: COR.navy, fontWeight: 900, fontSize: 64 }}>✓</div>
            <div style={{ position: "absolute", left: 270, top: y + 14, fontFamily, fontWeight: 900, fontSize: 56, color: on ? (ult ? COR.verde : COR.branco) : "#475569", opacity: vis }}>{e.nome}</div>
            {e.hora ? <div style={{ position: "absolute", right: 80, top: y + 28, fontFamily, fontWeight: 700, fontSize: 46, color: on ? COR.verde : "#475569", opacity: vis }}>{on ? e.hora : "—"}</div> : null}
          </React.Fragment>
        );
      })}
    </>
  );
};

/** Gráfico de barras que cresce (ex.: "antes × depois", horas por semana). Valores no topo contam junto. */
export const GraficoBarras: React.FC<{ de: number; barras: { rotulo: string; valor: number; cor?: string }[]; max?: number; topo?: number; altura?: number; unidade?: string; escalonar?: number }> = ({
  de, barras, max, topo = 500, altura = 700, unidade = "", escalonar = 0.35,
}) => {
  const t = useT();
  const m = max ?? Math.max(...barras.map((b) => b.valor));
  const larg = Math.min(220, 820 / barras.length - 40);
  return (
    <div style={{ position: "absolute", top: topo, left: 0, right: 0, height: altura, display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 40, fontFamily }}>
      {barras.map((b, i) => {
        const ini = de + i * escalonar;
        const p = prog(t, ini, ini + 0.8);
        const h = (altura - 160) * (b.valor / m) * p;
        return (
          <div key={b.rotulo} style={{ width: larg, display: "flex", flexDirection: "column", alignItems: "center", opacity: t >= ini ? 1 : 0 }}>
            <div style={{ fontWeight: 900, fontSize: 54, color: COR.branco, marginBottom: 10 }}>{Math.round(b.valor * p)}{unidade}</div>
            <div style={{ width: "100%", height: h, background: b.cor ?? COR.verde, borderRadius: "18px 18px 6px 6px" }} />
            <div style={{ fontWeight: 700, fontSize: 38, color: COR.cinza, marginTop: 14, textAlign: "center" }}>{b.rotulo}</div>
          </div>
        );
      })}
    </div>
  );
};

/** Mapa estilizado com rota que se desenha e um pino (técnico) que anda até o destino. ETA opcional. */
export const MapaRota: React.FC<{ ini: number; fim: number; topo?: number; altura?: number; origem?: string; destino?: string; eta?: string; rota?: [number, number][] }> = ({
  ini, fim, topo = 300, altura = 900, origem = "Base", destino = "Cliente", eta,
  rota = [[140, 760], [140, 520], [430, 520], [430, 300], [760, 300], [760, 160], [900, 160]],
}) => {
  const t = useT();
  const vis = mola(t, ini - 0.3, { damping: 15, stiffness: 170 });
  const seg = rota.slice(1).map((p, i) => Math.hypot(p[0] - rota[i][0], p[1] - rota[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  const anda = prog(t, ini, fim) * total;
  let acc = 0;
  let px = rota[rota.length - 1][0];
  let py = rota[rota.length - 1][1];
  for (let i = 0; i < seg.length; i++) {
    if (anda <= acc + seg[i]) {
      const f = seg[i] ? (anda - acc) / seg[i] : 0;
      px = rota[i][0] + (rota[i + 1][0] - rota[i][0]) * f;
      py = rota[i][1] + (rota[i + 1][1] - rota[i][1]) * f;
      break;
    }
    acc += seg[i];
  }
  const d = rota.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
  const chegou = t >= fim;
  const fimP = rota[rota.length - 1];
  return (
    <div style={{ position: "absolute", left: 40, top: topo, width: 1000, height: altura, borderRadius: 40, overflow: "hidden", background: "#E8EEF5", opacity: vis, transform: `scale(${0.92 + 0.08 * vis})`, boxShadow: "0 30px 80px rgba(0,0,0,.5)", fontFamily }}>
      <svg width={1000} height={altura} viewBox="0 0 1000 900" preserveAspectRatio="none">
        {[...Array(9)].map((_, i) => <rect key={i} x={(i % 3) * 330 + 30} y={Math.floor(i / 3) * 300 + 30} width={270} height={240} rx={18} fill="#D5DEE9" />)}
        <path d="M0,640 C250,600 420,720 1000,670" stroke="#BFD8F2" strokeWidth={46} fill="none" />
        <path d={d} stroke="#94A3B8" strokeWidth={14} fill="none" strokeDasharray="2 22" strokeLinecap="round" />
        <path d={d} stroke={COR.verde} strokeWidth={16} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={total} strokeDashoffset={total - anda} />
        <circle cx={rota[0][0]} cy={rota[0][1]} r={18} fill={COR.navy} />
        <circle cx={fimP[0]} cy={fimP[1]} r={chegou ? 34 + 6 * Math.sin(t * 8) : 28} fill={chegou ? COR.verde : COR.verm} opacity={0.35} />
        <circle cx={fimP[0]} cy={fimP[1]} r={16} fill={chegou ? COR.verde : COR.verm} />
        <circle cx={px} cy={py} r={34} fill={COR.navy} stroke={COR.branco} strokeWidth={6} />
        <circle cx={px} cy={py} r={12} fill={COR.verde} />
      </svg>
      <div style={{ position: "absolute", left: 30, bottom: 26, fontWeight: 800, fontSize: 36, color: COR.navy }}>● {origem}</div>
      <div style={{ position: "absolute", right: 30, bottom: 26, fontWeight: 800, fontSize: 36, color: COR.navy }}>{destino} ●</div>
      {eta ? (
        <div style={{ position: "absolute", left: 30, top: 24, background: chegou ? COR.verde : COR.navy, color: chegou ? COR.navy : COR.branco, borderRadius: 999, padding: "10px 28px", fontWeight: 900, fontSize: 38 }}>
          {chegou ? "Chegou ✓" : eta}
        </div>
      ) : null}
    </div>
  );
};
