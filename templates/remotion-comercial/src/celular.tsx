import React from "react";
import { Brilho, C, Onda, fontFamily, mola, prog, useT } from "./base";

// Interface ilustrativa de mensageiro (desenhada, sem print real) + peças do fluxo fiscal.

const CABECALHO = "#0E7A6B";
const CHAT = "#EFE7DD";

export const Avatar: React.FC<{ tipo: "marca" | "cliente"; tamanho: number }> = ({ tipo, tamanho }) =>
  tipo === "marca" ? (
    <svg width={tamanho} height={tamanho} viewBox="-50 -50 100 100">
      <circle r={50} fill={C.azul} />
      <Brilho r={28} x={-3} y={3} />
      <Brilho r={10} x={23} y={-21} />
    </svg>
  ) : (
    <svg width={tamanho} height={tamanho} viewBox="-50 -50 100 100">
      <circle r={50} fill="#F2C94C" />
      <rect x={-24} y={-22} width={48} height={52} rx={4} fill="#fff" />
      {[-14, 0, 14].map((x) => [-12, 2].map((y) => <rect key={`${x}${y}`} x={x - 5} y={y} width={10} height={9} fill="#9AA3AF" />))}
    </svg>
  );

/** Celular ilustrado. `largura` define tudo; a tela recebe as bolhas como filhos. */
export const Celular: React.FC<{
  largura: number; x: number; y: number; contato: string; status?: string; avatar: "marca" | "cliente";
  tremor?: number; gravando?: { de: number; nivel: (t: number) => number } | null; children?: React.ReactNode; giro?: number;
  campo?: string; // texto sendo digitado no campo de mensagem
  teclado?: number; // 0 = escondido, 1 = aberto
  altura?: number; // para encaixar o chat na tela de uma ilustração (proporção diferente do padrão)
}> = ({ largura, x, y, contato, status = "online", avatar, tremor = 0, gravando, children, giro = 0, campo = "", teclado = 0, altura: alturaFixa }) => {
  const t = useT();
  const k = largura / 640;
  const altura = alturaFixa ?? alturaCelular(largura);
  const dx = tremor * Math.sin(t * 90) * 10;
  const segundos = gravando ? Math.max(0, Math.floor(t - gravando.de)) : 0;
  return (
    <div
      style={{
        position: "absolute", left: x - largura / 2 + dx, top: y, width: largura, height: altura, borderRadius: 86 * k,
        background: "#0F1115", padding: 18 * k, boxShadow: "0 50px 120px rgba(0,0,0,.45)", transform: `rotate(${giro + tremor * Math.sin(t * 70) * 1.5}deg)`,
      }}
    >
      <div style={{ width: "100%", height: "100%", borderRadius: 70 * k, overflow: "hidden", display: "flex", flexDirection: "column", background: CHAT }}>
        {/* barra de status */}
        <div style={{ background: CABECALHO, height: 56 * k, display: "flex", justifyContent: "space-between", alignItems: "flex-end", padding: `0 ${52 * k}px ${6 * k}px`, fontFamily, fontWeight: 700, fontSize: 24 * k, color: "#fff" }}>
          <span>18:02</span>
          <span>▮▮▮ 86%</span>
        </div>
        {/* cabeçalho da conversa */}
        <div style={{ background: CABECALHO, display: "flex", alignItems: "center", gap: 20 * k, padding: `${14 * k}px ${28 * k}px ${22 * k}px` }}>
          <div style={{ fontFamily, fontSize: 44 * k, color: "#fff", fontWeight: 700 }}>‹</div>
          <Avatar tipo={avatar} tamanho={78 * k} />
          <div>
            <div style={{ fontFamily, fontWeight: 800, fontSize: 36 * k, color: "#fff" }}>{contato}</div>
            <div style={{ fontFamily, fontWeight: 600, fontSize: 24 * k, color: "rgba(255,255,255,.8)" }}>{status}</div>
          </div>
        </div>
        {/* conversa: a mais nova fica embaixo, as antigas sobem e saem pelo topo */}
        <div style={{ flex: 1, minHeight: 0, overflow: "hidden", padding: `${30 * k}px ${24 * k}px`, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 18 * k }}>
          {children}
        </div>
        {/* campo de mensagem */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 * k, padding: `${16 * k}px ${20 * k}px ${34 * k}px` }}>
          <div
            style={{
              flex: 1, height: 88 * k, borderRadius: 44 * k, background: "#fff", display: "flex", alignItems: "center", gap: 18 * k,
              padding: `0 ${30 * k}px`, fontFamily, fontWeight: 600, fontSize: 30 * k, color: "#8A8F98",
            }}
          >
            {gravando ? (
              <>
                <div style={{ width: 20 * k, height: 20 * k, borderRadius: 99, background: C.vermelho, opacity: 0.5 + 0.5 * Math.abs(Math.sin(t * 6)) }} />
                <span style={{ color: C.texto, fontWeight: 700 }}>0:0{segundos}</span>
                <Onda nivel={gravando.nivel} largura={300 * k} altura={56 * k} cor={CABECALHO} barras={22} />
              </>
            ) : campo ? (
              <span style={{ color: C.texto, whiteSpace: "nowrap", overflow: "hidden" }}>
                {campo}
                <span style={{ opacity: Math.floor(t * 3) % 2 ? 0 : 1, color: CABECALHO }}>|</span>
              </span>
            ) : (
              <span>Mensagem</span>
            )}
          </div>
          <div
            style={{
              width: 88 * k, height: 88 * k, borderRadius: 99, background: CABECALHO, display: "flex", justifyContent: "center", alignItems: "center",
              transform: `scale(${gravando ? 1.25 : 1})`, boxShadow: gravando ? `0 0 0 ${10 * k}px rgba(14,122,107,.25)` : "none",
            }}
          >
            {campo ? (
              <svg width={40 * k} height={40 * k} viewBox="0 0 24 24">
                <path d="M3 20 L21 12 L3 4 L5 12 Z" fill="#fff" />
              </svg>
            ) : (
              <svg width={40 * k} height={40 * k} viewBox="0 0 24 24">
                <rect x={8} y={2} width={8} height={13} rx={4} fill="#fff" />
                <path d="M5 11 a7 7 0 0 0 14 0 M12 18 v4" stroke="#fff" strokeWidth={2.4} fill="none" strokeLinecap="round" />
              </svg>
            )}
          </div>
        </div>
        {teclado > 0 ? <Teclado k={k} altura={alturaTeclado(largura) * teclado} /> : null}
      </div>
    </div>
  );
};

export const alturaCelular = (largura: number) => largura * 2.02;
export const alturaTeclado = (largura: number) => alturaCelular(largura) * 0.3;

/** Pontos da tela (coordenadas locais do celular) para o polegar mirar. */
export const pontosCelular = (largura: number, teclado = 0) => {
  const k = largura / 640;
  const h = alturaCelular(largura);
  const kb = alturaTeclado(largura) * teclado;
  const yCampo = h - 18 * k - 34 * k - 44 * k - kb;
  return {
    mic: { x: largura - 82 * k, y: yCampo },
    campo: { x: largura * 0.42, y: yCampo },
    teclado: { x0: 40 * k, x1: largura - 40 * k, y0: h - 18 * k - kb + 20 * k, y1: h - 18 * k - 60 * k },
  };
};

const Teclado: React.FC<{ k: number; altura: number }> = ({ k, altura }) => (
  <div style={{ height: altura, overflow: "hidden", background: "#D1D5DB", padding: `${14 * k}px ${8 * k}px`, display: "flex", flexDirection: "column", gap: 12 * k }}>
    {["qwertyuiop", "asdfghjkl", "zxcvbnm"].map((linha) => (
      <div key={linha} style={{ display: "flex", justifyContent: "center", gap: 8 * k }}>
        {linha.split("").map((l) => (
          <div key={l} style={{ width: 52 * k, height: 70 * k, borderRadius: 10 * k, background: "#fff", boxShadow: "0 2px 0 #9CA3AF", display: "flex", justifyContent: "center", alignItems: "center", fontFamily, fontWeight: 600, fontSize: 30 * k, color: C.texto }}>
            {l}
          </div>
        ))}
      </div>
    ))}
    <div style={{ alignSelf: "center", width: "60%", height: 64 * k, borderRadius: 10 * k, background: "#fff", boxShadow: "0 2px 0 #9CA3AF" }} />
  </div>
);

/** Mão direita segurando o celular por baixo; o polegar vai até `alvo` (coordenadas locais do celular). */
export const Mao: React.FC<{ largura: number; alvo: { x: number; y: number }; pressionando?: boolean; pele?: string }> = ({
  largura, alvo, pressionando, pele = "#B97A4E",
}) => {
  const k = largura / 640;
  const h = alturaCelular(largura);
  const base = { x: largura * 0.98, y: h * 0.97 };
  const dx = alvo.x - base.x;
  const dy = alvo.y - base.y;
  const ang = (Math.atan2(dy, dx) * 180) / Math.PI;
  const comp = Math.hypot(dx, dy) + (pressionando ? 6 * k : 22 * k);
  return (
    <svg width={largura} height={h} style={{ position: "absolute", left: 0, top: 0, overflow: "visible", pointerEvents: "none" }}>
      {/* dedos aparecendo na borda esquerda */}
      {[0, 1, 2].map((i) => (
        <ellipse key={i} cx={-4 * k} cy={h * 0.6 + i * 78 * k} rx={34 * k} ry={26 * k} fill={pele} stroke="rgba(0,0,0,.15)" strokeWidth={2} />
      ))}
      {/* palma e punho do uniforme */}
      <ellipse cx={largura * 1.08} cy={h * 1.06} rx={largura * 0.2} ry={largura * 0.28} fill={pele} />
      <rect x={largura * 0.96} y={h * 1.12} width={largura * 0.4} height={largura * 0.36} rx={30 * k} fill="#2B5BA8" transform={`rotate(-18 ${largura} ${h * 1.2})`} />
      {/* polegar */}
      <g transform={`translate(${base.x} ${base.y}) rotate(${ang})`}>
        <rect x={0} y={-34 * k} width={comp} height={68 * k} rx={34 * k} fill={pele} stroke="rgba(0,0,0,.18)" strokeWidth={2} />
        <ellipse cx={comp - 26 * k} cy={0} rx={18 * k} ry={14 * k} fill="#D9A27A" />
      </g>
      {pressionando ? <circle cx={alvo.x} cy={alvo.y} r={60 * k} fill="none" stroke="rgba(14,122,107,.45)" strokeWidth={8 * k} /> : null}
    </svg>
  );
};

/** Anexo PDF no chat, com selo de status. */
export const BolhaPdf: React.FC<{ de: number; k: number; nome: string; selo: string }> = ({ de, k, nome, selo }) => (
  <Bolha de={de} lado="esq" k={k}>
    <div style={{ display: "flex", alignItems: "center", gap: 18 * k, background: "#F3F4F6", borderRadius: 18 * k, padding: `${16 * k}px ${18 * k}px`, marginBottom: 10 * k }}>
      <div style={{ width: 64 * k, height: 80 * k, borderRadius: 8 * k, background: C.vermelho, color: "#fff", display: "flex", justifyContent: "center", alignItems: "flex-end", paddingBottom: 10 * k, fontWeight: 900, fontSize: 20 * k }}>PDF</div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 30 * k }}>{nome}</div>
        <div style={{ fontWeight: 600, fontSize: 22 * k, color: "#6B7280" }}>1 página · 84 kB</div>
      </div>
    </div>
    <span style={{ display: "inline-block", background: C.verde, color: "#fff", borderRadius: 99, padding: `${6 * k}px ${18 * k}px`, fontWeight: 800, fontSize: 26 * k }}>✓ {selo}</span>
  </Bolha>
);

/** Bolha que aparece com mola no instante `de`. */
export const Bolha: React.FC<{ de: number; lado: "esq" | "dir"; k: number; children: React.ReactNode; hora?: string; destaque?: boolean }> = ({
  de, lado, k, children, hora = "18:02", destaque,
}) => {
  const t = useT();
  if (t < de) return null;
  const s = mola(t, de, { damping: 13, stiffness: 200 });
  const dir = lado === "dir";
  return (
    <div
      style={{
        alignSelf: dir ? "flex-end" : "flex-start", maxWidth: "84%", background: dir ? "#D9FDD3" : "#fff", borderRadius: 26 * k,
        borderTopRightRadius: dir ? 6 * k : 26 * k, borderTopLeftRadius: dir ? 26 * k : 6 * k, padding: `${18 * k}px ${24 * k}px ${12 * k}px`,
        boxShadow: destaque ? `0 0 0 ${5 * k}px ${C.ambar}` : "0 2px 4px rgba(0,0,0,.12)",
        fontFamily, fontWeight: 600, fontSize: 34 * k, lineHeight: 1.3, color: C.texto,
        transform: `scale(${0.5 + 0.5 * s})`, transformOrigin: dir ? "right bottom" : "left bottom", opacity: Math.min(1, s * 1.5),
      }}
    >
      {children}
      <div style={{ textAlign: "right", fontSize: 20 * k, color: "#7A8088", marginTop: 4 * k }}>{hora}{dir ? "  ✓✓" : ""}</div>
    </div>
  );
};

export const BolhaAudio: React.FC<{ de: number; k: number; duracao: string; nivel: (t: number) => number }> = ({ de, k, duracao, nivel }) => (
  <Bolha de={de} lado="dir" k={k}>
    <div style={{ display: "flex", alignItems: "center", gap: 18 * k }}>
      <div style={{ width: 0, height: 0, borderTop: `${16 * k}px solid transparent`, borderBottom: `${16 * k}px solid transparent`, borderLeft: `${26 * k}px solid ${CABECALHO}` }} />
      <Onda nivel={nivel} largura={300 * k} altura={50 * k} cor="#5E9C92" barras={24} />
      <span style={{ fontSize: 24 * k, color: "#5E6670" }}>{duracao}</span>
    </div>
  </Bolha>
);

export const Digitando: React.FC<{ de: number; ate: number; k: number }> = ({ de, ate, k }) => {
  const t = useT();
  if (t < de || t >= ate) return null;
  return (
    <div style={{ alignSelf: "flex-start", background: "#fff", borderRadius: 26 * k, padding: `${22 * k}px ${28 * k}px`, display: "flex", gap: 12 * k }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ width: 16 * k, height: 16 * k, borderRadius: 99, background: "#9AA3AF", transform: `translateY(${Math.sin(t * 10 - i) * 5 * k}px)` }} />
      ))}
    </div>
  );
};

/** Notificação que desce no topo da tela. */
export const Notificacao: React.FC<{ de: number; ate?: number; titulo: string; texto: string; largura: number; topo?: number }> = ({
  de, ate = Infinity, titulo, texto, largura, topo = 0,
}) => {
  const t = useT();
  if (t < de || t >= ate) return null;
  const s = mola(t, de, { damping: 16, stiffness: 170 });
  return (
    <div
      style={{
        position: "absolute", left: "50%", top: topo, width: largura, transform: `translate(-50%, ${-160 + s * 160}px)`, opacity: Math.min(1, s * 2),
        background: "rgba(255,255,255,.97)", borderRadius: 34, padding: "22px 28px", boxShadow: "0 20px 60px rgba(0,0,0,.3)",
        display: "flex", gap: 20, alignItems: "center", fontFamily,
      }}
    >
      <Avatar tipo="cliente" tamanho={76} />
      <div>
        <div style={{ fontWeight: 800, fontSize: 30, color: C.texto }}>{titulo}</div>
        <div style={{ fontWeight: 600, fontSize: 32, color: "#4B5563" }}>{texto}</div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- fluxo fiscal ilustrado
export const Documento: React.FC<{ largura: number; carimbo: number }> = ({ largura, carimbo }) => {
  const k = largura / 600;
  const linha = (w: number) => <div style={{ height: 18 * k, width: `${w}%`, borderRadius: 9, background: "#D5DBE3" }} />;
  return (
    <div style={{ width: largura, height: largura * 1.3, background: "#fff", borderRadius: 28 * k, boxShadow: "0 30px 80px rgba(11,27,63,.25)", padding: 44 * k, position: "relative", fontFamily }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 30 * k }}>
        <div style={{ fontWeight: 900, fontSize: 56 * k, color: C.azul }}>NFS-e</div>
        <div style={{ fontWeight: 700, fontSize: 26 * k, color: "#6B7280" }}>Nota fiscal de serviço</div>
      </div>
      <div style={{ fontWeight: 800, fontSize: 32 * k, color: C.texto, marginBottom: 8 * k }}>OS nº 1852</div>
      <div style={{ fontWeight: 600, fontSize: 28 * k, color: "#4B5563", marginBottom: 26 * k }}>Condomínio Bela Vista (fictício)</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 * k, marginBottom: 30 * k }}>
        {linha(92)}{linha(78)}{linha(85)}{linha(60)}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", borderTop: "3px dashed #D5DBE3", paddingTop: 22 * k, fontWeight: 800, fontSize: 34 * k, color: C.texto }}>
        <span>Total</span>
        <span>R$ 1.590,00</span>
      </div>
      {carimbo > 0 ? (
        <div
          style={{
            position: "absolute", right: 24 * k, bottom: 130 * k, transform: `rotate(-10deg) scale(${2 - carimbo})`, opacity: Math.min(1, carimbo * 1.4),
            border: `${7 * k}px solid ${C.verde}`, color: C.verde, borderRadius: 18 * k, padding: `${10 * k}px ${22 * k}px`,
            fontWeight: 900, fontSize: 46 * k, letterSpacing: 2, background: "rgba(255,255,255,.92)",
          }}
        >
          ✓ NFS-e EMITIDA
        </div>
      ) : null}
    </div>
  );
};

/** Envelope: `aba` 0 = aberto, 1 = fechado. */
export const Envelope: React.FC<{ largura: number; aba: number }> = ({ largura, aba }) => {
  const h = largura * 0.66;
  return (
    <svg width={largura} height={h} viewBox="0 0 300 200" style={{ overflow: "visible" }}>
      <rect x={0} y={0} width={300} height={200} rx={16} fill="#DCE8FF" />
      <path d="M0 16 L0 200 L300 200 L300 16 L150 120 Z" fill={C.azul} />
      <path d="M0 200 L150 100 L300 200 Z" fill={C.azulEsc} />
      {/* aba: espelha de aberta (para cima) a fechada (para baixo) */}
      <g transform={`translate(0 2) scale(1 ${-1 + 2 * aba})`}>
        <path d="M0 0 L150 110 L300 0 Z" fill="#4A8BF5" />
      </g>
    </svg>
  );
};

export const Etiqueta: React.FC<{ texto: string; de: number; cor?: string; tamanho?: number }> = ({ texto, de, cor = C.verde, tamanho = 54 }) => {
  const t = useT();
  const s = mola(t, de, { damping: 12, stiffness: 200 });
  if (s <= 0) return null;
  return (
    <div
      style={{
        display: "inline-flex", alignItems: "center", gap: 18, background: cor, color: "#fff", borderRadius: 999, padding: "18px 40px",
        fontFamily, fontWeight: 900, fontSize: tamanho, transform: `scale(${s})`, boxShadow: "0 18px 50px rgba(0,0,0,.25)",
      }}
    >
      <span style={{ width: tamanho * 0.9, height: tamanho * 0.9, borderRadius: 99, background: "rgba(255,255,255,.25)", display: "inline-flex", justifyContent: "center", alignItems: "center", fontSize: tamanho * 0.6 }}>✓</span>
      {texto}
    </div>
  );
};

export type Titulo = { nome: string; valor: string; de: number };
export const CartaoFinanceiro: React.FC<{ de: number; largura: number; total: string; titulos: Titulo[] }> = ({ de, largura, total, titulos }) => {
  const t = useT();
  const s = mola(t, de, { damping: 16, stiffness: 150 });
  const k = largura / 900;
  return (
    <div
      style={{
        width: largura, background: "#fff", borderRadius: 44 * k, padding: 48 * k, fontFamily, boxShadow: "0 40px 100px rgba(11,27,63,.35)",
        transform: `translateY(${(1 - s) * 500}px)`, opacity: Math.min(1, s * 1.5),
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 18 * k, fontWeight: 800, fontSize: 36 * k, color: "#4B5563" }}>
        <Avatar tipo="marca" tamanho={58 * k} /> A receber hoje
      </div>
      <div style={{ fontWeight: 900, fontSize: 112 * k, color: C.verde, margin: `${10 * k}px 0 ${26 * k}px`, letterSpacing: -2 }}>{total}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 * k }}>
        {titulos.map((x) => {
          const e = prog(t, x.de, x.de + 0.35);
          return (
            <div
              key={x.nome}
              style={{
                display: "flex", justifyContent: "space-between", alignItems: "center", background: C.azulClaro, borderRadius: 22 * k,
                padding: `${22 * k}px ${28 * k}px`, fontSize: 38 * k, fontWeight: 700, color: C.texto, opacity: e, transform: `translateX(${(1 - e) * 80}px)`,
              }}
            >
              <span>{x.nome}</span>
              <span style={{ fontWeight: 900 }}>{x.valor}</span>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 22 * k, fontWeight: 700, fontSize: 26 * k, color: "#9AA3AF", textAlign: "right" }}>Dados fictícios</div>
    </div>
  );
};
