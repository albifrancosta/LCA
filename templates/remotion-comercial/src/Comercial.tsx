import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import { C, Cena, Legenda, Logo, Onda, Selo, TextoGrande, amp, fontFamily, mola, prog, useT } from "./base";
import { CaixaFerramentas, LocalAtendimento, Tecnico, Van } from "./personagens";
import {
  Bolha, BolhaAudio, BolhaPdf, Celular, Digitando, Documento, Envelope, Etiqueta, Mao, Notificacao, alturaCelular, pontosCelular,
} from "./celular";

// "A nota já foi?" v2 — 60 s, 9:16. Sem mascote: a MinhaMarca aparece no próprio chat, no logo e em texto grande.
// O fluxo fiscal acontece dentro da conversa do WhatsApp, com a mão do técnico interagindo.
// Tempos amarrados às palavras da voz (src/falas.json): t01 8,0–14,8 · "MinhaMarca" 19,0 · WhatsApp 24,5 · texto 25,5 ·
// áudio 26,4 · "nota" 30,6 · "e-mail" 32,6 · "receber" 47,7 · "MinhaMarca" 56,5 · "Peça" 58,1.

const CAIXA = C.marinho;
const FUNDO_MARCA = `radial-gradient(120% 80% at 50% 25%, ${C.marinho2} 0%, ${C.marinho} 70%)`;
const FUNDO_CELULAR = `radial-gradient(110% 70% at 50% 40%, #F7EFE6 0%, #D9C7AE 100%)`;

const LARG = 600;
const TOPO = 230;
const K = LARG / 640;
const ALT = alturaCelular(LARG);
const P = pontosCelular(LARG);
const REPOUSO = { x: LARG * 0.99, y: ALT * 0.86 }; // polegar encostado na borda, sem cobrir a conversa
const PERGUNTA = "O que tenho pra receber hoje?";
const DIGITA = { de: 44.0, ate: 45.6 };

/** Mão levando o celular à boca: 0 = braço pendurado, 1 = celular na frente da boca. */
const bracoCelular = (p: number): [number, number] => [-30 * p, 170 * p];
const nivelT01 = (t: number) => amp("t01", t);
const replayT01 = (t: number) => amp("t01", 8.2 + ((t * 0.9) % 6.4));

type Ponto = { x: number; y: number };
const mistura = (a: Ponto, b: Ponto, p: number): Ponto => ({ x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p });
const ruido = (n: number) => {
  const s = Math.sin(n * 12.9898) * 43758.5453;
  return s - Math.floor(s);
};

/** Celular segurado pela mão do técnico; `desloc` move e encolhe o conjunto (celular vai para o lado). */
const CelularNaMao: React.FC<{
  contato: string; status: string; avatar: "marca" | "cliente"; polegar: Ponto; pressionando?: boolean;
  desloc?: { x: number; s: number }; campo?: string; teclado?: number; tremor?: number;
  gravando?: { de: number; nivel: (t: number) => number } | null; children?: React.ReactNode;
}> = ({ contato, status, avatar, polegar, pressionando, desloc = { x: 0, s: 1 }, campo, teclado = 0, tremor, gravando, children }) => (
  <div
    style={{
      position: "absolute", left: 540 - LARG / 2, top: TOPO, width: LARG, height: ALT,
      transform: `translateX(${desloc.x}px) scale(${desloc.s})`, transformOrigin: "50% 0%",
    }}
  >
    <Celular largura={LARG} x={LARG / 2} y={0} contato={contato} status={status} avatar={avatar} campo={campo} teclado={teclado} tremor={tremor} gravando={gravando}>
      {children}
    </Celular>
    <Mao largura={LARG} alvo={polegar} pressionando={pressionando} />
  </div>
);

// ---------------------------------------------------------------- 0–3,4 s · fecha a caixa, o celular vibra
const Abertura: React.FC = () => {
  const t = useT();
  const vibra = t >= 2.7 ? Math.max(0, Math.sin((t - 2.7) * 40)) : 0;
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + 0.05 * prog(t, 0, 3.4, Easing.linear)})` }}>
      <LocalAtendimento />
      <CaixaFerramentas x={120} y={1580} largura={330} fechada={prog(t, 0.5, 1.25, Easing.inOut(Easing.cubic))} />
      <Tecnico altura={1000} x={640} y={1580} bracoE={[38 * (1 - prog(t, 1.3, 1.9)), 0]} sorriso={t < 2.7} olhar={t > 2.9 ? 1 : 0} />
      {t >= 2.7 ? (
        <svg width={200} height={200} viewBox="-100 -100 200 200" style={{ position: "absolute", left: 640, top: 920, opacity: 0.4 + 0.6 * vibra }}>
          {[40, 66].map((r) => (
            <path key={r} d={`M${r * 0.6} ${-r * 0.8} A${r} ${r} 0 0 1 ${r * 0.6} ${r * 0.8}`} fill="none" stroke={C.ambar} strokeWidth={10} strokeLinecap="round" />
          ))}
        </svg>
      ) : null}
      <TextoGrande linhas={[{ t: "Serviço concluído ✓" }]} de={0.35} caixa={CAIXA} tamanho={72} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 3,4–7 s · a mensagem do cliente ocupa o quadro
const PedidoCliente: React.FC = () => {
  const t = useT();
  const aproxima = prog(t, 3.9, 4.6, Easing.inOut(Easing.cubic));
  return (
    <AbsoluteFill style={{ background: FUNDO_CELULAR }}>
      <AbsoluteFill style={{ transform: `scale(${1 + 0.4 * aproxima})`, transformOrigin: "50% 78%" }}>
        <CelularNaMao contato="Condomínio Bela Vista" status="cliente" avatar="cliente" polegar={REPOUSO} tremor={t < 3.9 ? 1 : 0}>
          <Bolha de={3.9} lado="esq" k={K} destaque>
            Consegue mandar a nota por e-mail?
          </Bolha>
        </CelularNaMao>
      </AbsoluteFill>
      <TextoGrande linhas={[{ t: "A nota já foi?", cor: C.marinho }]} de={4.6} caixa={C.ambar} topo={120} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- técnico em plano médio (pede por áudio / volta ao celular)
const TecnicoPlano: React.FC<{ de: number; texto: string; falando?: boolean }> = ({ de, texto, falando }) => {
  const t = useT();
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: "scale(1.7)", transformOrigin: "50% 30%" }}>
        <LocalAtendimento />
      </AbsoluteFill>
      <Tecnico
        altura={1900} x={500} y={2050} bracoD={bracoCelular(falando ? prog(t, de, de + 0.55, Easing.out(Easing.back(1.4))) : 0.6)}
        celular boca={falando ? nivelT01(t) : 0} sorriso={!falando} olhar={falando ? 0 : 0.8}
      />
      {falando && t > de + 0.6 ? (
        <div style={{ position: "absolute", left: 640, top: 470, background: "#fff", borderRadius: 40, padding: "26px 34px", boxShadow: "0 20px 50px rgba(0,0,0,.2)" }}>
          <Onda nivel={nivelT01} largura={300} altura={90} cor={C.ambar} barras={16} />
        </div>
      ) : null}
      <TextoGrande linhas={[{ t: texto }]} de={de + 0.2} caixa={CAIXA} tamanho={84} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 8,6–52 s · a conversa com a MinhaMarca (uma só, contínua)
const polegarNoChat = (t: number): { alvo: Ponto; pressionando: boolean } => {
  const pontos = pontosCelular(LARG, tecladoAberto(t));
  if (t < 15.0) {
    // segura o microfone enquanto fala (8,0–14,8)
    return { alvo: mistura(REPOUSO, pontos.mic, prog(t, 8.6, 8.9)), pressionando: t >= 8.9 };
  }
  if (t < 43.5) return { alvo: mistura(pontos.mic, REPOUSO, prog(t, 15.0, 15.4)), pressionando: false };
  if (t < DIGITA.de) return { alvo: mistura(REPOUSO, pontos.campo, prog(t, 43.5, 43.75)), pressionando: t > 43.7 };
  if (t < DIGITA.ate) {
    // pula de tecla em tecla
    const n = Math.floor(t * 9);
    const tk = pontos.teclado;
    return { alvo: { x: tk.x0 + ruido(n) * (tk.x1 - tk.x0), y: tk.y0 + ruido(n + 7) * (tk.y1 - tk.y0) }, pressionando: (t * 9) % 1 < 0.5 };
  }
  if (t < 45.8) return { alvo: pontos.mic, pressionando: t > 45.7 }; // botão enviar
  return { alvo: mistura(pontos.mic, REPOUSO, prog(t, 45.9, 46.3)), pressionando: false };
};
const tecladoAberto = (t: number) => prog(t, 43.75, 44.0) * (1 - prog(t, 45.85, 46.15));
const textoDigitado = (t: number) =>
  t < DIGITA.de || t >= 45.8 ? "" : PERGUNTA.slice(0, Math.ceil(PERGUNTA.length * prog(t, DIGITA.de, DIGITA.ate, Easing.linear)));

const ConversaMarca: React.FC = () => {
  const t = useT();
  const { alvo, pressionando } = polegarNoChat(t);
  // 18–28 s: o celular vai para o lado para a marca entrar
  const lado = prog(t, 18.0, 18.6, Easing.inOut(Easing.cubic)) * (1 - prog(t, 28.0, 28.5, Easing.inOut(Easing.cubic)));
  const zoomDoc = prog(t, 31.0, 31.4, Easing.out(Easing.cubic)) * (1 - prog(t, 32.3, 32.6, Easing.in(Easing.cubic)));
  const voa = prog(t, 32.7, 33.5, Easing.in(Easing.cubic));
  return (
    <AbsoluteFill style={{ background: lado > 0 ? FUNDO_MARCA : FUNDO_CELULAR }}>
      <CelularNaMao
        contato="MinhaMarca" status="assistente de IA do seu ERP" avatar="marca" polegar={alvo} pressionando={pressionando}
        desloc={{ x: -250 * lado, s: 1 - 0.38 * lado }} campo={textoDigitado(t)} teclado={tecladoAberto(t)}
        gravando={t >= 8.0 && t < 14.9 ? { de: 8.0, nivel: nivelT01 } : null}
      >
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
      </CelularNaMao>

      {/* 18–28 s: a marca no espaço livre (sem mascote) */}
      {lado > 0.01 ? <PainelMarca opacidade={lado} /> : null}

      {/* 31–32,6 s: aproxima o PDF para ler a nota */}
      {zoomDoc > 0 ? (
        <AbsoluteFill style={{ background: `rgba(11,27,63,${0.55 * zoomDoc})` }}>
          <div style={{ position: "absolute", top: 380, left: 0, right: 0, display: "flex", justifyContent: "center", transform: `scale(${0.4 + 0.6 * zoomDoc})`, opacity: zoomDoc }}>
            <Documento largura={640} carimbo={mola(t, 31.25, { damping: 10, stiffness: 220 })} />
          </div>
        </AbsoluteFill>
      ) : null}

      {/* 32,7 s: o envelope sai voando do chat */}
      {voa > 0 && voa < 1 ? (
        <div style={{ position: "absolute", left: 460, top: 1050, transform: `translate(${voa * 700}px, ${-voa * 1100}px) rotate(${-voa * 30}deg) scale(${1 - 0.4 * voa})` }}>
          <Envelope largura={180} aba={1} />
        </div>
      ) : null}

      {/* status grandes, cada um parado tempo suficiente para ler */}
      {t >= 30.6 && t < 37.5 ? (
        <div style={{ position: "absolute", top: 168, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
          {t < 32.7 ? <Etiqueta texto="NFS-e emitida" de={30.6} tamanho={46} /> : <Etiqueta texto="E-mail enviado" de={32.7} cor={C.azul} tamanho={46} />}
        </div>
      ) : null}
      <Notificacao de={37.6} ate={42.0} titulo="Condomínio Bela Vista" texto="Recebi a nota, obrigado!" largura={900} topo={250} />
    </AbsoluteFill>
  );
};

/** Logo + "assistente de IA do seu ERP" + canais, entrando conforme a narração. */
const PainelMarca: React.FC<{ opacidade: number }> = ({ opacidade }) => {
  const t = useT();
  const linha = (de: number) => mola(t, de, { damping: 14, stiffness: 180 });
  const canais = [
    { txt: "WhatsApp", de: 24.5, cor: "#1FA855" },
    { txt: "Texto", de: 25.5, cor: "rgba(255,255,255,.14)" },
    { txt: "Áudio", de: 26.4, cor: "rgba(255,255,255,.14)" },
  ];
  return (
    <div style={{ position: "absolute", left: 560, right: 40, top: 430, display: "flex", flexDirection: "column", gap: 26, opacity: opacidade, fontFamily }}>
      <div style={{ transform: `scale(${linha(19.0)})`, transformOrigin: "left center" }}>
        <Logo tamanho={110} />
      </div>
      <div style={{ color: "#fff", fontWeight: 900, fontSize: 58, lineHeight: 1.08, opacity: linha(19.8), transform: `translateY(${(1 - linha(19.8)) * 40}px)` }}>
        Assistente de IA <span style={{ color: "#7DB2FF" }}>do seu ERP</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 20 }}>
        {canais.map((c) => (
          <div
            key={c.txt}
            style={{
              alignSelf: "flex-start", background: c.cor, border: "3px solid rgba(255,255,255,.4)", borderRadius: 999, padding: "12px 34px",
              color: "#fff", fontWeight: 800, fontSize: 46, transform: `scale(${linha(c.de)})`, transformOrigin: "left center",
            }}
          >
            {c.txt}
          </div>
        ))}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- 52–56,3 s · guarda o celular e segue
const Saida: React.FC = () => {
  const t = useT();
  const guarda = prog(t, 52.0, 52.5);
  const anda = prog(t, 52.7, 56.0, Easing.inOut(Easing.quad));
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: "linear-gradient(180deg, #CFE6FA 0%, #EAF4FD 55%, #CBBFAE 55%, #B8AA96 100%)" }} />
      <Van x={430} y={1560} largura={640} />
      <Tecnico
        altura={1000} x={420 + anda * 700} y={1640} bracoD={bracoCelular(1 - guarda)} celular={guarda < 0.85}
        passo={anda > 0 && anda < 1 ? t * 11 : 0} sorriso
      />
      <TextoGrande linhas={[{ t: "Próximo atendimento" }]} de={52.3} caixa={CAIXA} tamanho={70} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 56,3–60 s · assinatura e CTA (sem mascote)
const Fechamento: React.FC = () => {
  const t = useT();
  const logo = mola(t, 56.5, { damping: 12, stiffness: 140 });
  const cta = mola(t, 58.1, { damping: 11, stiffness: 180 });
  const pulso = t > 58.6 ? 1 + 0.04 * Math.sin((t - 58.6) * 7) : 1;
  return (
    <AbsoluteFill style={{ background: FUNDO_MARCA }}>
      <div style={{ position: "absolute", top: 420, left: 0, right: 0, display: "flex", justifyContent: "center", transform: `scale(${logo})` }}>
        <Logo tamanho={180} />
      </div>
      <TextoGrande linhas={[{ t: "Menos operação." }]} de={57.0} topo={760} tamanho={96} />
      <TextoGrande linhas={[{ t: "Mais estratégia.", cor: "#7DB2FF" }]} de={57.4} topo={875} tamanho={96} />
      <div style={{ position: "absolute", top: 1080, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
        <div
          style={{
            background: C.azul, color: "#fff", borderRadius: 999, padding: "30px 60px", fontFamily, fontWeight: 900, fontSize: 64,
            transform: `scale(${cta * pulso})`, boxShadow: `0 0 0 ${10 * cta}px rgba(31,111,235,.3), 0 20px 60px rgba(0,0,0,.4)`,
          }}
        >
          Peça uma demonstração
        </div>
        <div style={{ fontFamily, fontWeight: 700, fontSize: 40, color: "rgba(255,255,255,.75)", opacity: prog(t, 58.4, 58.8) }}>minhamarca.com.br</div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- montagem
const NO_CHAT: [number, number][] = [[3.4, 7.0], [8.6, 42.0], [43.4, 52.0]];

export type PropsComercial = { variante: "A" | "B" };

export const Comercial: React.FC<PropsComercial> = () => {
  const t = useT();
  const noChat = NO_CHAT.some(([a, b]) => t >= a && t < b);
  return (
    <AbsoluteFill style={{ backgroundColor: C.marinho }}>
      <Cena de={0} ate={3.4}><Abertura /></Cena>
      <Cena de={3.4} ate={7.0}><PedidoCliente /></Cena>
      <Cena de={7.0} ate={8.6}><TecnicoPlano de={7.0} texto="Pede por áudio" falando /></Cena>
      <Cena de={8.6} ate={42.0}><ConversaMarca /></Cena>
      <Cena de={42.0} ate={43.4}><TecnicoPlano de={42.0} texto="E o financeiro?" /></Cena>
      <Cena de={43.4} ate={52.0}><ConversaMarca /></Cena>
      <Cena de={52.0} ate={56.3}><Saida /></Cena>
      <Cena de={56.3} ate={60.1}><Fechamento /></Cena>
      {/* selo obrigatório enquanto o fluxo fiscal aparece */}
      {t >= 14.95 && t < 42 ? <Selo texto="SIMULAÇÃO DO FLUXO" de={14.95} /> : null}
      {/* no chat a legenda desce para baixo do celular, para não cobrir a conversa */}
      <Legenda ocultarDe={56.3} topo={noChat ? 1478 : 1330} />
      <AbsoluteFill style={{ background: "#000", opacity: interpolate(t, [59.6, 60], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }} />
    </AbsoluteFill>
  );
};
