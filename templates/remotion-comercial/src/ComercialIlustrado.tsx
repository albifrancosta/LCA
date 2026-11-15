import React from "react";
import { AbsoluteFill, Easing, Freeze, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, FPS, LegendaHistoria, Logo, Selo, amp, fontFamily, mola, prog, useT } from "./base";
import { Bolha, BolhaAudio, BolhaPdf, Celular, Digitando, Documento, Envelope, Etiqueta, alturaTeclado } from "./celular";
import tela from "./tela.json";

// "A nota já foi?" — versão ilustrada (padrão visual da MinhaMarca desde 2026-11-04):
// ilustração 2D cinematográfica + clipes Kling nos momentos de ação + chat desenhado na tela verde do celular da s2.
// Mesmo roteiro, vozes e tempos da v2 (src/falas.json).

const W = 1080;
const H = 1920;
// a ilustração (1024×1536) cobre o quadro 1080×1920: escala 1,25, sobra 100 px de cada lado
const ESC = Math.max(W / tela.imgW, H / tela.imgH);
const OFF_X = (W - tela.imgW * ESC) / 2;
const OFF_Y = (H - tela.imgH * ESC) / 2;
const TELA = { x: OFF_X + tela.x * ESC, y: OFF_Y + tela.y * ESC, w: tela.w * ESC, h: tela.h * ESC };
// o componente Celular tem moldura; ela fica fora do recorte da tela
const LARG = TELA.w / (1 - 36 / 640);
const K = LARG / 640;
const MOLDURA = 18 * K;
const ALT = TELA.h + 2 * MOLDURA;

const PERGUNTA = "O que tenho pra receber hoje?";
const DIGITA = { de: 44.0, ate: 45.6 };
const nivelT01 = (t: number) => amp("t01", t);
const replayT01 = (t: number) => amp("t01", 8.2 + ((t * 0.9) % 6.4));
const ruido = (n: number) => {
  const s = Math.sin(n * 12.9898) * 43758.5453;
  return s - Math.floor(s);
};
const tecladoAberto = (t: number) => prog(t, 43.75, 44.0) * (1 - prog(t, 45.85, 46.15));
const textoDigitado = (t: number) =>
  t < DIGITA.de || t >= 45.8 ? "" : PERGUNTA.slice(0, Math.ceil(PERGUNTA.length * prog(t, DIGITA.de, DIGITA.ate, Easing.linear)));

/** Pontos da tela (coordenadas do recorte da tela) onde o polegar toca. */
const pontos = (t: number) => {
  const kb = alturaTeclado(LARG) * tecladoAberto(t);
  const y = ALT - 96 * K - kb - MOLDURA;
  return {
    mic: { x: LARG - 82 * K - MOLDURA, y },
    campo: { x: LARG * 0.42 - MOLDURA, y },
    tecla: (n: number) => ({ x: 40 * K + ruido(n) * (LARG - 80 * K) - MOLDURA, y: ALT - 18 * K - kb + 20 * K + ruido(n + 7) * Math.max(0, kb - 80 * K) - MOLDURA }),
  };
};

// ---------------------------------------------------------------- peças
const Ilustracao: React.FC<{ src: string; z?: [number, number]; de: number; ate: number; foco?: [number, number]; escurecer?: number; desfoque?: number }> = ({
  src, z = [1, 1.06], de, ate, foco = [0.5, 0.45], escurecer = 0, desfoque = 0,
}) => {
  const t = useT();
  const e = z[0] + (z[1] - z[0]) * prog(t, de, ate, Easing.inOut(Easing.sin));
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <Img
        src={staticFile(src)}
        style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${e})`, transformOrigin: `${foco[0] * 100}% ${foco[1] * 100}%`, filter: desfoque ? `blur(${desfoque}px)` : undefined }}
      />
      {escurecer ? <AbsoluteFill style={{ background: `rgba(6,12,30,${escurecer})` }} /> : null}
    </AbsoluteFill>
  );
};

const VideoAjustado: React.FC<{ src: string; rate: number; ultimo: number }> = ({ src, rate, ultimo }) => {
  const f = useCurrentFrame();
  const v = <OffthreadVideo src={staticFile(src)} muted playbackRate={rate} style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
  return f < ultimo ? v : <Freeze frame={ultimo}>{v}</Freeze>;
};

/** Clipe de IA tocando a partir de `de`; desacelera até 0,6× para caber e segura o último quadro. */
const Clipe: React.FC<{ src: string; de: number; ate: number; dur: number }> = ({ src, de, ate, dur }) => {
  const rate = Math.max(0.6, Math.min(1, dur / (ate - de)));
  return (
    <Sequence from={Math.round(de * FPS)} durationInFrames={Math.round((ate - de) * FPS)} premountFor={FPS}>
      <AbsoluteFill style={{ backgroundColor: "#000" }}>
        <VideoAjustado src={src} rate={rate} ultimo={Math.floor((dur / rate) * FPS) - 2} />
      </AbsoluteFill>
    </Sequence>
  );
};

const Toque: React.FC<{ x: number; y: number; forca: number }> = ({ x, y, forca }) =>
  forca > 0 ? (
    <div
      style={{
        position: "absolute", left: x - 34, top: y - 34, width: 68, height: 68, borderRadius: 99,
        background: `rgba(255,255,255,${0.35 * forca})`, boxShadow: `0 0 0 ${10 + 14 * forca}px rgba(14,122,107,${0.35 * forca})`,
      }}
    />
  ) : null;

/** A mão da ilustração s2 segurando o celular, com o chat animado na tela verde. */
const MaoNoCelular: React.FC<{
  contato: string; status: string; avatar: "marca" | "cliente"; zoom?: { de: number; ate: number; s: number; origem: string };
  children?: React.ReactNode;
}> = ({ contato, status, avatar, zoom, children }) => {
  const t = useT();
  // 1,12×: aproxima o celular para o texto do chat ficar legível no telefone de quem assiste
  const s = 1.12 * (zoom ? 1 + (zoom.s - 1) * prog(t, zoom.de, zoom.ate, Easing.inOut(Easing.cubic)) : 1 + 0.015 * Math.sin(t * 0.6));
  const p = pontos(t);
  // onde o polegar está tocando agora
  let toque: { x: number; y: number; f: number } | null = null;
  if (avatar === "marca") {
    if (t >= 9.6 && t < 14.9) toque = { ...p.mic, f: 0.7 + 0.3 * Math.sin(t * 8) }; // segura o microfone
    else if (t >= 43.55 && t < 43.85) toque = { ...p.campo, f: 1 };
    else if (t >= DIGITA.de && t < DIGITA.ate) toque = { ...p.tecla(Math.floor(t * 9)), f: (t * 9) % 1 < 0.6 ? 1 : 0 };
    else if (t >= 45.65 && t < 45.9) toque = { ...p.mic, f: 1 }; // enviar
  }
  return (
    <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: zoom?.origem ?? "50% 20%" }}>
      <Img src={staticFile("ilustrado/s2.png")} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <div style={{ position: "absolute", left: TELA.x, top: TELA.y, width: TELA.w, height: TELA.h, overflow: "hidden", borderRadius: 34 }}>
        <Celular
          largura={LARG} altura={ALT} x={LARG / 2 - MOLDURA} y={-MOLDURA} contato={contato} status={status} avatar={avatar}
          campo={avatar === "marca" ? textoDigitado(t) : ""} teclado={avatar === "marca" ? tecladoAberto(t) : 0}
          gravando={avatar === "marca" && t >= 8.0 && t < 14.9 ? { de: 8.0, nivel: nivelT01 } : null}
        >
          {children}
        </Celular>
        {toque ? <Toque x={toque.x} y={toque.y} forca={toque.f} /> : null}
      </div>
    </AbsoluteFill>
  );
};

/** A conversa inteira com a MinhaMarca; cada bolha aparece no seu segundo. */
const ConversaMarca: React.FC = () => {
  const t = useT();
  return (
    <>
      <BolhaAudio de={14.95} k={K} duracao="0:07" nivel={t < 16.2 ? replayT01 : () => 0.35} />
      <Digitando de={15.4} ate={16.5} k={K} />
      <Bolha de={16.5} lado="esq" k={K}>
        Certo! Gerando a <b>NFS-e da OS 1852</b> e enviando para o e-mail do cliente.
      </Bolha>
      <Digitando de={17.2} ate={30.6} k={K} />
      <BolhaPdf de={30.6} k={K} nome="NFS-e_OS1852.pdf" selo="NFS-e emitida" />
      <Bolha de={32.6} lado="esq" k={K} destaque>
        ✓ E-mail enviado para <b style={{ overflowWrap: "anywhere" }}>nf@belavista.exemplo</b>
      </Bolha>
      <Bolha de={45.8} lado="dir" k={K}>{PERGUNTA}</Bolha>
      <Digitando de={46.0} ate={47.0} k={K} />
      <Bolha de={47.0} lado="esq" k={K}>
        <div style={{ fontWeight: 700, fontSize: 28 * K, color: "#4B5563" }}>A receber hoje</div>
        <div style={{ fontWeight: 900, fontSize: 64 * K, color: C.verde, letterSpacing: -1 }}>R$ 4.320,00</div>
        <div style={{ fontWeight: 600, fontSize: 24 * K, color: "#6B7280" }}>3 recebimentos · dados fictícios</div>
      </Bolha>
    </>
  );
};

/** 18–28 s: logo + "assistente de IA do seu ERP" + canais, à direita do técnico. */
const PainelMarca: React.FC = () => {
  const t = useT();
  const linha = (de: number) => mola(t, de, { damping: 14, stiffness: 180 });
  const canais = [
    { txt: "WhatsApp", de: 24.5, cor: "#1FA855" },
    { txt: "Texto", de: 25.5, cor: "rgba(255,255,255,.16)" },
    { txt: "Áudio", de: 26.4, cor: "rgba(255,255,255,.16)" },
  ];
  return (
    <>
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(6,12,30,0) 35%, rgba(6,12,30,.55) 60%, rgba(6,12,30,.7) 100%)", opacity: prog(t, 18.6, 19.2) }} />
      <div style={{ position: "absolute", left: 660, right: 30, top: 300, display: "flex", flexDirection: "column", gap: 22, fontFamily }}>
        <div style={{ transform: `scale(${linha(19.0)})`, transformOrigin: "left center" }}>
          <Logo tamanho={84} />
        </div>
        <div style={{ color: "#fff", fontWeight: 900, fontSize: 50, lineHeight: 1.08, opacity: linha(19.8), transform: `translateY(${(1 - linha(19.8)) * 40}px)`, textShadow: "0 4px 18px rgba(0,0,0,.5)" }}>
          Assistente de IA <span style={{ color: "#7DB2FF" }}>do seu ERP</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 16 }}>
          {canais.map((c) => (
            <div
              key={c.txt}
              style={{
                alignSelf: "flex-start", background: c.cor, border: "3px solid rgba(255,255,255,.45)", borderRadius: 999, padding: "10px 32px",
                color: "#fff", fontWeight: 800, fontSize: 40, transform: `scale(${linha(c.de)})`, transformOrigin: "left center",
              }}
            >
              {c.txt}
            </div>
          ))}
        </div>
      </div>
    </>
  );
};

const Cena: React.FC<{ de: number; ate: number; children: React.ReactNode }> = ({ de, ate, children }) => {
  const t = useT();
  if (t < de || t >= ate) return null;
  const e = prog(t, de, de + 0.25);
  return <AbsoluteFill style={{ opacity: Math.min(1, 0.4 + e), transform: `scale(${1.03 - 0.03 * e})` }}>{children}</AbsoluteFill>;
};

// ---------------------------------------------------------------- montagem
export const ComercialIlustrado: React.FC = () => {
  const t = useT();
  const zoomDoc = prog(t, 31.0, 31.4, Easing.out(Easing.cubic)) * (1 - prog(t, 32.3, 32.6, Easing.in(Easing.cubic)));
  const voa = prog(t, 32.7, 33.5, Easing.in(Easing.cubic));
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* clipes de IA (cada um no seu Sequence) */}
      <Clipe src="clips/c1.mp4" de={0} ate={3.4} dur={5} />
      <Clipe src="clips/c2.mp4" de={7.0} ate={9.6} dur={5} />
      {/* c3 só no começo: depois de ~4 s o Kling aproxima a câmera e o técnico invade o espaço do painel */}
      <Clipe src="clips/c3.mp4" de={18.0} ate={21.5} dur={10} />
      <Cena de={21.5} ate={28.0}>
        <Ilustracao src="ilustrado/s4.png" de={21.5} ate={28.0} z={[1.0, 1.05]} foco={[0.25, 0.4]} />
      </Cena>
      <Clipe src="clips/c4.mp4" de={37.6} ate={42.0} dur={5} />
      <Clipe src="clips/c5.mp4" de={52.0} ate={56.3} dur={5} />

      {/* 3,4–7 s: a mensagem do cliente cresce no quadro */}
      <Cena de={3.4} ate={7.0}>
        <MaoNoCelular contato="Condomínio Bela Vista" status="cliente" avatar="cliente" zoom={{ de: 4.0, ate: 4.7, s: 1.45, origem: "50% 62%" }}>
          <Bolha de={3.9} lado="esq" k={K} destaque>
            Consegue mandar a nota por e-mail?
          </Bolha>
        </MaoNoCelular>
      </Cena>

      {/* a conversa com a MinhaMarca: 9,6–18 · 28–37,6 · 43,4–52 */}
      {[[9.6, 18.0], [28.0, 37.6], [43.4, 52.0]].map(([a, b]) => (
        <Cena key={a} de={a} ate={b}>
          <MaoNoCelular contato="MinhaMarca" status="assistente de IA do seu ERP" avatar="marca">
            <ConversaMarca />
          </MaoNoCelular>
        </Cena>
      ))}

      {/* 18–28 s: a marca entra ao lado do técnico */}
      {t >= 18.0 && t < 28.0 ? <PainelMarca /> : null}

      {/* 31–32,6 s: aproxima o PDF para ler a nota */}
      {zoomDoc > 0 ? (
        <AbsoluteFill style={{ background: `rgba(6,12,30,${0.6 * zoomDoc})` }}>
          <div style={{ position: "absolute", top: 380, left: 0, right: 0, display: "flex", justifyContent: "center", transform: `scale(${0.4 + 0.6 * zoomDoc})`, opacity: zoomDoc }}>
            <Documento largura={640} carimbo={mola(t, 31.25, { damping: 10, stiffness: 220 })} />
          </div>
        </AbsoluteFill>
      ) : null}
      {voa > 0 && voa < 1 ? (
        <div style={{ position: "absolute", left: 470, top: 1000, transform: `translate(${voa * 700}px, ${-voa * 1100}px) rotate(${-voa * 30}deg) scale(${1 - 0.4 * voa})` }}>
          <Envelope largura={170} aba={1} />
        </div>
      ) : null}
      {t >= 30.6 && t < 37.5 ? (
        <div style={{ position: "absolute", top: 196, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
          {t < 32.7 ? <Etiqueta texto="NFS-e emitida" de={30.6} tamanho={44} /> : <Etiqueta texto="E-mail enviado" de={32.7} cor={C.azul} tamanho={44} />}
        </div>
      ) : null}

      {/* 37,6–42 s: a síndica recebe a nota (cartão de e-mail sobre o clipe) */}
      {t >= 38.0 && t < 42.0 ? (
        <div
          style={{
            position: "absolute", left: 90, right: 90, top: 210, background: "rgba(255,255,255,.97)", borderRadius: 30, padding: "24px 30px",
            display: "flex", gap: 22, alignItems: "center", fontFamily, boxShadow: "0 20px 60px rgba(0,0,0,.4)",
            transform: `translateY(${(1 - mola(t, 38.0)) * -60}px)`, opacity: mola(t, 38.0),
          }}
        >
          <div style={{ width: 70, height: 84, borderRadius: 10, background: C.vermelho, color: "#fff", fontWeight: 900, fontSize: 22, display: "flex", alignItems: "flex-end", justifyContent: "center", paddingBottom: 10 }}>PDF</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 32, color: C.texto }}>Nova mensagem · NFS-e OS 1852</div>
            <div style={{ fontWeight: 600, fontSize: 28, color: "#4B5563" }}>Nota fiscal de serviço em anexo</div>
          </div>
        </div>
      ) : null}

      {/* 42–43,4 s: de volta ao técnico, sorrindo para o celular */}
      <Cena de={42.0} ate={43.4}>
        <Ilustracao src="ilustrado/s4.png" de={42.0} ate={43.4} z={[1.15, 1.25]} foco={[0.3, 0.25]} />
      </Cena>

      {/* 56,3–60 s: assinatura sobre a última cena desfocada */}
      <Cena de={56.3} ate={60.1}>
        <Ilustracao src="ilustrado/s6.png" de={56.3} ate={60} z={[1.08, 1.14]} escurecer={0.62} desfoque={10} />
        <div style={{ position: "absolute", top: 520, left: 0, right: 0, display: "flex", justifyContent: "center", transform: `scale(${mola(t, 56.5, { damping: 12, stiffness: 140 })})` }}>
          <Logo tamanho={170} />
        </div>
        <div style={{ position: "absolute", top: 780, left: 0, right: 0, textAlign: "center", fontFamily, fontWeight: 900, fontSize: 90, lineHeight: 1.1, color: "#fff" }}>
          <div style={{ opacity: mola(t, 57.0) }}>Menos operação.</div>
          <div style={{ opacity: mola(t, 57.4), color: "#7DB2FF" }}>Mais estratégia.</div>
        </div>
        <div style={{ position: "absolute", top: 1060, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 22 }}>
          <div
            style={{
              background: C.azul, color: "#fff", borderRadius: 999, padding: "28px 56px", fontFamily, fontWeight: 900, fontSize: 60,
              transform: `scale(${mola(t, 58.1, { damping: 11, stiffness: 180 }) * (t > 58.6 ? 1 + 0.04 * Math.sin((t - 58.6) * 7) : 1)})`,
              boxShadow: "0 0 0 10px rgba(31,111,235,.3), 0 20px 60px rgba(0,0,0,.4)",
            }}
          >
            Peça uma demonstração
          </div>
          <div style={{ fontFamily, fontWeight: 700, fontSize: 38, color: "rgba(255,255,255,.8)", opacity: prog(t, 58.4, 58.8) }}>minhamarca.com.br</div>
        </div>
      </Cena>

      {t >= 14.95 && t < 42 ? <Selo texto="SIMULAÇÃO DO FLUXO" de={14.95} /> : null}
      {/* nas cenas do celular a legenda desce para baixo da tela, sem cobrir o chat */}
      <LegendaHistoria ocultarDe={56.3} topo={[[3.4, 7.0], [9.6, 18.0], [28.0, 37.6], [43.4, 52.0]].some(([a, b]) => t >= a && t < b) ? 1400 : 1300} />
      <AbsoluteFill style={{ background: "#000", opacity: interpolate(t, [59.6, 60], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }} />
    </AbsoluteFill>
  );
};
