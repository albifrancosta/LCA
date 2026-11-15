import React from "react";
import { AbsoluteFill } from "remotion";
import { Brilho, C, useT } from "./base";

// Todos os personagens são vetores em camadas: cada braço, olho e boca se move sozinho.

const PELE = "#B97A4E";
const PELE_SOMBRA = "#A0663F";
const UNIFORME = "#2B5BA8";
const UNIFORME_ESC = "#21477F";
const CALCA = "#26324A";

const piscando = (t: number, fase = 0) => ((t + fase) % 3.4) < 0.12;

/** Braço em dois segmentos. a1 = ombro, a2 = cotovelo (graus, horário; 0 = pendurado). */
const Braco: React.FC<{ x: number; y: number; a1: number; a2: number; celular?: boolean }> = ({ x, y, a1, a2, celular }) => (
  <g transform={`translate(${x} ${y}) rotate(${a1})`}>
    <rect x={-17} y={-10} width={34} height={104} rx={17} fill={UNIFORME} />
    <g transform={`translate(0 92) rotate(${a2})`}>
      <rect x={-14} y={-6} width={28} height={92} rx={14} fill={PELE} />
      <circle cy={92} r={19} fill={PELE} />
      {celular ? (
        <g transform="translate(-14 70) rotate(-10)">
          <rect width={30} height={56} rx={7} fill="#111827" />
          <rect x={3} y={4} width={24} height={46} rx={4} fill={C.azul} opacity={0.9} />
        </g>
      ) : null}
    </g>
  </g>
);

export type PoseTecnico = {
  bracoD?: [number, number]; // braço do lado direito da tela
  bracoE?: [number, number];
  celular?: boolean; // celular na mão direita da tela
  boca?: number; // 0..1 abertura (amplitude da voz)
  sorriso?: boolean;
  passo?: number; // fase da caminhada (0 = parado)
  olhar?: number; // -1..1 desvio dos olhos
};

/** Técnico de manutenção. viewBox 300×640, pés em (150, 625). */
export const Tecnico: React.FC<PoseTecnico & { altura: number; x: number; y: number }> = ({
  altura, x, y, bracoD = [0, 0], bracoE = [0, 0], celular, boca = 0, sorriso, passo = 0, olhar = 0,
}) => {
  const t = useT();
  const pisca = piscando(t);
  const perna = passo ? Math.sin(passo) * 22 : 0;
  const balanco = passo ? Math.abs(Math.sin(passo)) * -8 : Math.sin(t * 1.6) * 2;
  const escala = altura / 640;
  return (
    <svg
      width={300 * escala} height={640 * escala} viewBox="0 0 300 640"
      style={{ position: "absolute", left: x - 150 * escala, top: y - 625 * escala, overflow: "visible" }}
    >
      <ellipse cx={150} cy={628} rx={95} ry={14} fill="rgba(0,0,0,.18)" />
      <g transform={`translate(0 ${balanco})`}>
        {/* pernas */}
        <g transform={`rotate(${perna} 125 410)`}>
          <rect x={102} y={400} width={46} height={205} rx={18} fill={CALCA} />
          <ellipse cx={120} cy={612} rx={36} ry={16} fill="#1B1B1B" />
        </g>
        <g transform={`rotate(${-perna} 175 410)`}>
          <rect x={152} y={400} width={46} height={205} rx={18} fill={CALCA} />
          <ellipse cx={186} cy={612} rx={36} ry={16} fill="#1B1B1B" />
        </g>
        {/* braço de trás */}
        <Braco x={92} y={250} a1={bracoE[0]} a2={bracoE[1]} />
        {/* tronco */}
        <rect x={142} y={196} width={26} height={40} fill={PELE_SOMBRA} />
        <rect x={84} y={226} width={132} height={196} rx={40} fill={UNIFORME} />
        <path d="M150 230 L132 262 L150 282 L168 262 Z" fill={UNIFORME_ESC} />
        <rect x={84} y={330} width={132} height={14} fill="#F2C94C" opacity={0.95} />
        <rect x={180} y={262} width={26} height={30} rx={5} fill={UNIFORME_ESC} />
        {/* cinto de ferramentas */}
        <rect x={84} y={398} width={132} height={22} rx={6} fill="#6B4423" />
        <rect x={98} y={404} width={18} height={30} rx={4} fill="#8A5A2E" />
        <rect x={186} y={404} width={18} height={26} rx={4} fill="#8A5A2E" />
        {/* cabeça */}
        <g>
          <circle cx={98} cy={168} r={12} fill={PELE_SOMBRA} />
          <circle cx={202} cy={168} r={12} fill={PELE_SOMBRA} />
          <ellipse cx={150} cy={160} rx={54} ry={60} fill={PELE} />
          {/* boné */}
          <path d="M94 142 C96 92 204 92 206 142 Z" fill={C.azul} />
          <path d="M150 140 L238 146 C232 156 200 158 150 152 Z" fill={C.azulEsc} />
          <g transform="translate(150 118)">
            <Brilho r={11} />
          </g>
          {/* olhos */}
          <g transform={`translate(${olhar * 5} 0)`}>
            <ellipse cx={130} cy={166} rx={7} ry={pisca ? 1.2 : 8} fill="#1F1A17" />
            <ellipse cx={172} cy={166} rx={7} ry={pisca ? 1.2 : 8} fill="#1F1A17" />
          </g>
          <path d="M118 148 Q130 142 142 148" stroke="#3A2618" strokeWidth={5} fill="none" strokeLinecap="round" />
          <path d="M160 148 Q172 142 184 148" stroke="#3A2618" strokeWidth={5} fill="none" strokeLinecap="round" />
          <path d="M150 170 Q146 184 152 186" stroke={PELE_SOMBRA} strokeWidth={4} fill="none" strokeLinecap="round" />
          {/* barba curta */}
          <path d="M100 176 C108 222 192 222 200 176 C190 200 110 200 100 176 Z" fill="#3A2618" opacity={0.85} />
          {/* boca: abre com a amplitude da voz */}
          {boca > 0.05 ? (
            <ellipse cx={151} cy={200} rx={13} ry={3 + boca * 11} fill="#5A1F1A" />
          ) : sorriso ? (
            <path d="M134 196 Q151 214 168 196" stroke="#5A1F1A" strokeWidth={6} fill="none" strokeLinecap="round" />
          ) : (
            <path d="M138 200 Q151 206 164 200" stroke="#5A1F1A" strokeWidth={5} fill="none" strokeLinecap="round" />
          )}
        </g>
        {/* braço da frente */}
        <Braco x={208} y={250} a1={bracoD[0]} a2={bracoD[1]} celular={celular} />
      </g>
    </svg>
  );
};

/** Mascote MinhaMarca: robô azul com o brilho do Assistente como antena. viewBox 300×360. */
export const Mascote: React.FC<{ tamanho: number; x: number; y: number; aceno?: number; feliz?: boolean; fala?: number }> = ({
  tamanho, x, y, aceno = 0, feliz = true, fala = 0,
}) => {
  const t = useT();
  const pisca = piscando(t, 1.3);
  const flutua = Math.sin(t * 2.4) * 8;
  const s = tamanho / 360;
  return (
    <svg
      width={300 * s} height={360 * s} viewBox="0 0 300 360"
      style={{ position: "absolute", left: x - 150 * s, top: y - 180 * s, overflow: "visible" }}
    >
      <ellipse cx={150} cy={350} rx={80 - flutua} ry={10} fill="rgba(0,0,0,.2)" />
      <g transform={`translate(0 ${flutua})`}>
        {/* antena com brilho */}
        <line x1={150} y1={70} x2={150} y2={34} stroke={C.azulEsc} strokeWidth={8} strokeLinecap="round" />
        <circle cx={150} cy={22} r={26 + Math.sin(t * 5) * 3} fill={C.azul} opacity={0.25} />
        <Brilho x={150} y={22} r={20} cor="#FFD84D" giro={t * 40} />
        {/* bracinhos */}
        <g transform={`rotate(${-25 - aceno * 70 + Math.sin(t * 9) * aceno * 18} 248 250)`}>
          <ellipse cx={262} cy={282} rx={20} ry={40} fill={C.azulEsc} />
        </g>
        <ellipse cx={38} cy={282} rx={20} ry={40} fill={C.azulEsc} transform="rotate(20 38 282)" />
        {/* corpo */}
        <ellipse cx={150} cy={300} rx={84} ry={52} fill={C.azulEsc} />
        <g transform="translate(150 300)">
          <Brilho r={18} cor="#9CC3FF" />
        </g>
        {/* cabeça */}
        <rect x={34} y={64} width={232} height={196} rx={78} fill={C.azul} />
        <rect x={62} y={98} width={176} height={126} rx={54} fill="#EAF2FF" />
        <ellipse cx={116} cy={156} rx={15} ry={pisca ? 2 : 20} fill={C.marinho} />
        <ellipse cx={184} cy={156} rx={15} ry={pisca ? 2 : 20} fill={C.marinho} />
        <circle cx={121} cy={148} r={5} fill="#fff" opacity={pisca ? 0 : 1} />
        <circle cx={189} cy={148} r={5} fill="#fff" opacity={pisca ? 0 : 1} />
        <ellipse cx={92} cy={190} rx={13} ry={8} fill="#FF9DB0" opacity={0.6} />
        <ellipse cx={208} cy={190} rx={13} ry={8} fill="#FF9DB0" opacity={0.6} />
        {fala > 0.05 ? (
          <ellipse cx={150} cy={196} rx={16} ry={4 + fala * 10} fill={C.marinho} />
        ) : (
          <path d={feliz ? "M128 190 Q150 212 172 190" : "M132 198 Q150 204 168 198"} stroke={C.marinho} strokeWidth={7} fill="none" strokeLinecap="round" />
        )}
      </g>
    </svg>
  );
};

export const CaixaFerramentas: React.FC<{ x: number; y: number; largura: number; fechada: number }> = ({ x, y, largura, fechada }) => {
  const s = largura / 260;
  return (
    <svg width={260 * s} height={200 * s} viewBox="0 0 260 200" style={{ position: "absolute", left: x, top: y - 200 * s, overflow: "visible" }}>
      <ellipse cx={130} cy={196} rx={130} ry={10} fill="rgba(0,0,0,.18)" />
      <rect x={10} y={80} width={240} height={112} rx={14} fill="#D9412B" />
      <rect x={10} y={120} width={240} height={10} fill="#B23422" />
      <rect x={112} y={96} width={36} height={18} rx={4} fill="#9AA3AF" />
      {/* ferramentas aparecendo enquanto a tampa está aberta */}
      <g opacity={1 - fechada}>
        <rect x={50} y={40} width={14} height={60} rx={4} fill="#9AA3AF" transform="rotate(-12 57 70)" />
        <rect x={180} y={44} width={16} height={56} rx={4} fill="#F2C94C" transform="rotate(10 188 72)" />
      </g>
      {/* tampa gira pela dobradiça da esquerda */}
      <g transform={`rotate(${(1 - fechada) * -110} 10 80)`}>
        <rect x={10} y={56} width={240} height={30} rx={12} fill="#EF5B42" />
        <rect x={100} y={36} width={60} height={24} rx={10} fill="none" stroke="#2D2D2D" strokeWidth={9} />
      </g>
    </svg>
  );
};

/** Parede e piso do local do atendimento, com a condensadora do ar-condicionado. */
export const LocalAtendimento: React.FC<{ ventilador?: boolean }> = ({ ventilador = true }) => {
  const t = useT();
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: `linear-gradient(180deg, #F7EFE6 0%, ${C.parede} 62%, ${C.piso} 62%, #D6C2A6 100%)` }} />
      {/* janela */}
      <div style={{ position: "absolute", left: 640, top: 360, width: 330, height: 380, borderRadius: 16, background: "#BFDDF5", border: "16px solid #FFFFFF", boxShadow: "inset 0 0 0 6px #E9E2D8" }}>
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 12, background: "#fff", transform: "translateX(-50%)" }} />
        <div style={{ position: "absolute", left: 30, top: 40, width: 120, height: 36, borderRadius: 30, background: "rgba(255,255,255,.8)" }} />
      </div>
      {/* condensadora */}
      <svg width={420} height={330} viewBox="0 0 420 330" style={{ position: "absolute", left: 90, top: 470 }}>
        <rect x={20} y={300} width={380} height={14} fill="#9AA3AF" />
        <rect x={10} y={10} width={400} height={290} rx={18} fill="#E8EBEF" stroke="#C5CBD3" strokeWidth={6} />
        <circle cx={150} cy={155} r={110} fill="#C9CFD7" />
        <g transform={`rotate(${ventilador ? t * 400 : 0} 150 155)`}>
          {[0, 90, 180, 270].map((a) => (
            <ellipse key={a} cx={150} cy={105} rx={26} ry={50} fill="#9AA3AF" transform={`rotate(${a} 150 155)`} />
          ))}
        </g>
        {[0, 1, 2, 3, 4].map((i) => (
          <circle key={i} cx={150} cy={155} r={30 + i * 20} fill="none" stroke="#7D8794" strokeWidth={3} opacity={0.6} />
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <rect key={i} x={290} y={40 + i * 34} width={100} height={8} rx={4} fill="#C5CBD3" />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

export const Van: React.FC<{ x: number; y: number; largura: number }> = ({ x, y, largura }) => {
  const s = largura / 600;
  return (
    <svg width={600 * s} height={320 * s} viewBox="0 0 600 320" style={{ position: "absolute", left: x, top: y - 320 * s }}>
      <ellipse cx={300} cy={306} rx={300} ry={14} fill="rgba(0,0,0,.18)" />
      <path d="M20 90 Q20 40 70 40 L400 40 Q450 40 480 90 L560 170 Q580 190 580 220 L580 270 L20 270 Z" fill="#FFFFFF" stroke="#D8DEE6" strokeWidth={6} />
      <path d="M410 60 L470 60 L540 160 L410 160 Z" fill="#BFDDF5" />
      <rect x={20} y={180} width={560} height={30} fill={C.azul} />
      <g transform="translate(150 125)">
        <circle r={34} fill={C.azul} />
        <Brilho r={20} />
      </g>
      <circle cx={140} cy={272} r={44} fill="#1F2937" />
      <circle cx={140} cy={272} r={18} fill="#9AA3AF" />
      <circle cx={460} cy={272} r={44} fill="#1F2937" />
      <circle cx={460} cy={272} r={18} fill="#9AA3AF" />
    </svg>
  );
};
