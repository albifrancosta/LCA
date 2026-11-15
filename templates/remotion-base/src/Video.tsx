import React from "react";
import {
  AbsoluteFill,
  Easing,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/google-fonts/Montserrat";

const { fontFamily } = loadFont("normal", { weights: ["600", "800", "900"], subsets: ["latin"] });

// ---------------------------------------------------------------- tipos (espelham src/video.json)
export type Palavra = { text: string; start: number; end: number };
export type Grupo = { start: number; end: number; words: [number, number]; key: boolean };
export type Marca = { fundo: string; fundo2: string; primaria: string; texto: string; alerta: string };
export type Batida = { texto: string; inicio: number };
export type Cena = {
  id: string;
  inicio: number;
  fim: number;
  tipo: "titulo" | "imagem" | "print" | "celular" | "preto" | "cta" | "video";
  batidas?: Batida[];
  entrada?: "fade" | "nenhuma"; // padrão: sem fade (corte seco); a 1ª cena nunca entra com fade (gancho visível no frame 0)
  // titulo
  rotulo?: string;
  linhas?: { texto: string; destaque?: boolean }[];
  // imagem / print
  src?: string;
  zoom?: "in" | "out" | "nenhum"; // padrão: nenhum (imagem parada)
  pulso?: boolean; // pulso nas palavras-chave sem zoom (padrão: só quando há zoom)
  pan?: "esquerda" | "direita" | "nenhum";
  escurecer?: number;
  texto?: string;
  foco?: { x: number; y: number; escala: number; inicio: number };
  // video (clipe MP4 em public/)
  de?: number; // segundo do clipe onde a cena começa
  videoDur?: number; // duração do clipe (preparar_remotion.py mede com ffprobe)
  som?: boolean; // padrão: mudo (a voz/música da composição não duplica)
  volume?: number;
  // celular
  contato?: string;
  mensagens?: { de: string; texto: string; inicio: number; alerta?: boolean }[];
  // cta
  logo?: string;
  titulo?: string;
  url?: string;
  opcoes?: { letra: string; texto: string }[];
};
export type DadosVideo = {
  fps: number;
  width: number;
  height: number;
  duracao: number;
  marca: Marca;
  audio: { voz?: string | null; musica?: string | null; volumeMusica?: number };
  cenas: Cena[];
  legenda: { estilo: "caixa" | "cor" | "nenhuma"; altura?: number; palavras: Palavra[]; grupos: Grupo[] };
  sfx?: { src: string; inicio: number; volume?: number }[];
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Pulso curto (0→1→0) em cada palavra-chave da cena; tempos absolutos em segundos.
const usePulso = (cena: Cena) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (cena.batidas ?? []).reduce((acc, b) => {
    const f = frame - Math.round((b.inicio - cena.inicio) * fps);
    if (f < -2 || f > 20) return acc;
    return acc + interpolate(f, [-2, 4, 20], [0, 1, 0], clamp);
  }, 0);
};

// Props comuns: `dur` = duração da Sequence em frames; `fe` = frame das animações de ENTRADA
// (na 1ª cena começa já concluída, para o gancho estar inteiro no frame 0).
type Props = { c: Cena; m: Marca; dur: number; fe: number };

const Entrada: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 5], [0, 1], clamp);
  const scale = interpolate(frame, [0, 8], [1.04, 1], { ...clamp, easing: Easing.out(Easing.quad) });
  return <AbsoluteFill style={{ opacity, transform: `scale(${scale})` }}>{children}</AbsoluteFill>;
};

const Fundo: React.FC<{ m: Marca }> = ({ m }) => (
  <AbsoluteFill style={{ background: `radial-gradient(120% 80% at 50% 20%, ${m.fundo2} 0%, ${m.fundo} 70%)` }} />
);

// ---------------------------------------------------------------- cenas
const CenaTitulo: React.FC<Props> = ({ c, m, fe }) => {
  const { fps, width } = useVideoConfig();
  const pulso = usePulso(c);
  const linhas = c.linhas ?? [];
  const maior = Math.max(8, ...linhas.map((l) => l.texto.length));
  const tamanho = Math.min(width * 0.12, (width * 1.55) / maior);
  return (
    <AbsoluteFill>
      <Fundo m={m} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: width * 0.08 }}>
        {c.rotulo ? (
          <div
            style={{
              fontFamily, fontWeight: 800, fontSize: width * 0.032, letterSpacing: 3, color: m.primaria,
              border: `3px solid ${m.primaria}`, borderRadius: 999, padding: "10px 28px", marginBottom: 36,
              opacity: interpolate(fe, [0, 8], [0, 1], clamp),
            }}
          >
            {c.rotulo.toUpperCase()}
          </div>
        ) : null}
        {linhas.map((l, i) => {
          const s = spring({ frame: fe - i * 6, fps, config: { damping: 18, stiffness: 160 } });
          return (
            <div
              key={i}
              style={{
                fontFamily, fontWeight: 900, fontSize: tamanho, lineHeight: 1.05, textAlign: "center",
                color: l.destaque ? m.primaria : m.texto,
                opacity: s, transform: `translateY(${(1 - s) * 70}px) scale(${1 + (l.destaque ? pulso * 0.06 : 0)})`,
              }}
            >
              {l.texto}
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const CenaImagem: React.FC<Props> = ({ c, m, dur, fe }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const p = interpolate(frame, [0, Math.max(1, dur)], [0, 1], clamp);
  const pulso = usePulso(c);
  const comZoom = c.zoom === "in" || c.zoom === "out";
  // sem "zoom" a imagem fica parada (P49); o pulso de palavra-chave só vale com zoom ou "pulso": true
  const base = c.zoom === "out" ? 1.14 - 0.12 * p : c.zoom === "in" ? 1 + 0.12 * p : 1;
  const escala = base + (comZoom || c.pulso ? pulso * 0.03 : 0);
  const desloc = c.pan === "esquerda" ? -3 * p : c.pan === "direita" ? 3 * p : 0;
  return (
    <AbsoluteFill style={{ backgroundColor: m.fundo, overflow: "hidden" }}>
      {c.src ? (
        <Img
          src={staticFile(c.src)}
          style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${escala}) translateX(${desloc}%)` }}
        />
      ) : null}
      <AbsoluteFill
        style={{ background: `linear-gradient(180deg, rgba(0,0,0,${c.escurecer ?? 0.15}) 0%, rgba(0,0,0,0) 35%, rgba(0,0,0,${(c.escurecer ?? 0.15) + 0.25}) 100%)` }}
      />
      {c.texto ? (
        <div
          style={{
            position: "absolute", top: "11%", left: "7%", right: "7%", textAlign: "center", fontFamily,
            fontWeight: 900, fontSize: width * 0.085, lineHeight: 1.05, color: m.texto,
            textShadow: "0 6px 30px rgba(0,0,0,.6)", opacity: interpolate(fe, [3, 12], [0, 1], clamp),
          }}
        >
          {c.texto}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const CenaPrint: React.FC<Props> = ({ c, m, fe }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const entra = spring({ frame: fe, fps, config: { damping: 200 }, durationInFrames: 18 });
  const pulso = usePulso(c);
  let escala = 1;
  let origem = "50% 50%";
  if (c.foco) {
    const f = spring({ frame: frame - Math.round((c.foco.inicio - c.inicio) * fps), fps, config: { damping: 200 }, durationInFrames: 20 });
    escala = 1 + (c.foco.escala - 1) * f;
    origem = `${c.foco.x * 100}% ${c.foco.y * 100}%`;
  }
  return (
    <AbsoluteFill>
      <Fundo m={m} />
      {c.texto ? (
        <div
          style={{
            position: "absolute", top: "9%", left: "7%", right: "7%", textAlign: "center", fontFamily,
            fontWeight: 900, fontSize: width * 0.08, lineHeight: 1.05, color: m.texto,
            opacity: interpolate(fe, [2, 10], [0, 1], clamp),
          }}
        >
          {c.texto}
        </div>
      ) : null}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div
          style={{
            width: "90%", borderRadius: 28, overflow: "hidden", backgroundColor: "#fff",
            boxShadow: `0 40px 120px rgba(0,0,0,.55), 0 0 0 2px ${m.primaria}33`,
            transform: `translateY(${(1 - entra) * 160}px) scale(${escala + pulso * 0.025})`, transformOrigin: origem,
            opacity: entra,
          }}
        >
          <div style={{ height: 44, background: "#EEF1F5", display: "flex", alignItems: "center", gap: 10, paddingLeft: 20 }}>
            {["#FF5F57", "#FEBC2E", "#28C840"].map((cor) => (
              <div key={cor} style={{ width: 14, height: 14, borderRadius: 7, background: cor }} />
            ))}
          </div>
          {c.src ? <Img src={staticFile(c.src)} style={{ width: "100%", display: "block" }} /> : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const CenaCelular: React.FC<Props> = ({ c, m, fe }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const entra = spring({ frame: fe, fps, config: { damping: 200 }, durationInFrames: 16 });
  const balanco = Math.sin(frame / 18) * 4;
  const w = width * 0.76;
  return (
    <AbsoluteFill>
      <Fundo m={m} />
      <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center", paddingTop: height * 0.07 }}>
        <div
          style={{
            width: w, height: height * 0.54, borderRadius: 70, background: "#0E1116",
            border: "14px solid #1C2230", boxShadow: "0 50px 140px rgba(0,0,0,.6)", overflow: "hidden",
            display: "flex", flexDirection: "column",
            transform: `translateY(${(1 - entra) * 260 + balanco}px) rotate(${(1 - entra) * -6}deg)`,
          }}
        >
          <div style={{ background: "#1F2C34", padding: "46px 32px 26px", display: "flex", alignItems: "center", gap: 22 }}>
            <div style={{ width: 70, height: 70, borderRadius: 35, background: m.primaria, opacity: 0.85 }} />
            <div style={{ fontFamily, fontWeight: 800, fontSize: 38, color: "#E9EDEF" }}>{c.contato ?? "Cliente"}</div>
          </div>
          <div style={{ flex: 1, background: "#0B141A", padding: "30px 26px", display: "flex", flexDirection: "column", gap: 22 }}>
            {(c.mensagens ?? []).map((msg, i) => {
              const s = spring({ frame: frame - Math.round((msg.inicio - c.inicio) * fps), fps, config: { damping: 14, stiffness: 180 } });
              if (s <= 0.001) return null;
              return (
                <div
                  key={i}
                  style={{
                    alignSelf: "flex-start", maxWidth: "86%", background: "#202C33", color: "#E9EDEF", borderRadius: 26,
                    borderTopLeftRadius: 6, padding: "22px 28px", fontFamily, fontWeight: 600, fontSize: 40, lineHeight: 1.25,
                    border: msg.alerta ? `4px solid ${m.alerta}` : "none",
                    transform: `scale(${0.6 + 0.4 * s})`, transformOrigin: "left top", opacity: s,
                  }}
                >
                  <div style={{ fontSize: 28, fontWeight: 800, color: msg.alerta ? m.alerta : m.primaria, marginBottom: 6 }}>{msg.de}</div>
                  {msg.texto}
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const CenaPreto: React.FC<Props> = ({ c, m, fe }) => {
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", justifyContent: "center", alignItems: "center" }}>
      {c.texto ? (
        <div
          style={{
            fontFamily, fontWeight: 900, fontSize: width * 0.07, color: m.texto, textAlign: "center", padding: "0 8%",
            opacity: interpolate(fe, [6, 18], [0, 1], clamp),
          }}
        >
          {c.texto}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const CenaCta: React.FC<Props> = ({ c, m, fe }) => {
  const { fps, width } = useVideoConfig();
  const pulso = usePulso(c);
  const s = (atraso: number) => spring({ frame: fe - atraso, fps, config: { damping: 16, stiffness: 150 } });
  return (
    <AbsoluteFill>
      <Fundo m={m} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 40, padding: "0 7%" }}>
        {c.logo ? <Img src={staticFile(c.logo)} style={{ height: width * 0.13, opacity: s(0), transform: `scale(${s(0)})` }} /> : null}
        {c.titulo ? (
          <div style={{ fontFamily, fontWeight: 900, fontSize: width * 0.075, color: m.texto, textAlign: "center", lineHeight: 1.08, opacity: s(4) }}>
            {c.titulo}
          </div>
        ) : null}
        {(c.opcoes ?? []).map((o, i) => (
          <div
            key={o.letra}
            style={{
              width: "100%", display: "flex", alignItems: "center", gap: 30, background: "rgba(255,255,255,.06)",
              border: `3px solid ${i === 1 ? m.primaria : "rgba(255,255,255,.25)"}`, borderRadius: 30, padding: "26px 32px",
              opacity: s(10 + i * 8), transform: `translateX(${(1 - s(10 + i * 8)) * (i ? 120 : -120)}px) scale(${i === 1 ? 1 + pulso * 0.04 : 1})`,
            }}
          >
            <div
              style={{
                width: 96, height: 96, borderRadius: 48, display: "flex", justifyContent: "center", alignItems: "center",
                background: i === 1 ? m.primaria : "rgba(255,255,255,.15)", color: i === 1 ? m.fundo : m.texto,
                fontFamily, fontWeight: 900, fontSize: 56,
              }}
            >
              {o.letra}
            </div>
            <div style={{ fontFamily, fontWeight: 800, fontSize: width * 0.05, color: m.texto }}>{o.texto}</div>
          </div>
        ))}
        {c.url ? (
          <div
            style={{
              fontFamily, fontWeight: 800, fontSize: width * 0.045, color: m.fundo, background: m.primaria,
              borderRadius: 999, padding: "18px 44px", opacity: s(26), transform: `scale(${s(26)})`,
            }}
          >
            {c.url}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Clipe MP4 (P45): toca a partir de `de` segundos; se o clipe acabar antes da cena, segura o último quadro. */
const CenaVideo: React.FC<Props> = ({ c, m, dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const de = Math.max(0, c.de ?? 0);
  const restante = c.videoDur !== undefined ? Math.floor((c.videoDur - de) * fps) - 1 : dur;
  const ultimo = Math.max(0, Math.min(dur, restante));
  if (!c.src) return <CenaErro c={c} m={m} dur={dur} fe={0} msg="cena video sem src" />;
  const video = (
    <OffthreadVideo
      src={staticFile(c.src)}
      muted={!c.som}
      volume={c.som ? c.volume ?? 1 : 0}
      trimBefore={de > 0 ? Math.round(de * fps) : undefined}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
    />
  );
  return (
    <AbsoluteFill style={{ backgroundColor: m.fundo, overflow: "hidden" }}>
      {frame < ultimo ? video : <Freeze frame={ultimo}>{video}</Freeze>}
    </AbsoluteFill>
  );
};

/** Tipo desconhecido: erro visível no quadro em vez de derrubar o render (P55). */
const CenaErro: React.FC<Props & { msg?: string }> = ({ c, msg }) => (
  <AbsoluteFill style={{ backgroundColor: "#7f1d1d", justifyContent: "center", alignItems: "center", padding: "0 8%" }}>
    <div style={{ fontFamily, fontWeight: 900, fontSize: 64, color: "#fff", textAlign: "center" }}>
      {msg ?? `ERRO: tipo de cena "${String(c.tipo)}" não suportado`}
      <div style={{ fontSize: 40, fontWeight: 600, marginTop: 24 }}>cena {c.id}</div>
    </div>
  </AbsoluteFill>
);

const CENAS: Record<Cena["tipo"], React.FC<Props>> = {
  titulo: CenaTitulo, imagem: CenaImagem, print: CenaPrint, celular: CenaCelular, preto: CenaPreto, cta: CenaCta, video: CenaVideo,
};

// ---------------------------------------------------------------- legenda palavra a palavra
const Legenda: React.FC<{ d: DadosVideo }> = ({ d }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const { legenda: l, marca: m } = d;
  if (l.estilo === "nenhuma") return null;
  const t = frame / fps;
  const g = l.grupos.find((x) => t >= x.start - 0.05 && t < x.end + 0.1);
  if (!g) return null;
  const pop = spring({ frame: frame - Math.round((g.start - 0.05) * fps), fps, config: { damping: 14, stiffness: 220 }, durationInFrames: 8 });
  const ids = Array.from({ length: Math.max(0, g.words[1] - g.words[0] + 1) }, (_, k) => g.words[0] + k).filter((i) => l.palavras[i]);
  if (!ids.length) return null;
  const ativa = ids.filter((i) => l.palavras[i].start <= t).pop() ?? ids[0];
  return (
    <div
      style={{
        position: "absolute", left: "7%", right: "7%", top: (l.altura ?? 0.64) * height, display: "flex",
        flexWrap: "wrap", justifyContent: "center", gap: "6px 14px", transform: `scale(${0.85 + 0.15 * pop})`,
      }}
    >
      {ids.map((i) => {
        const on = i === ativa;
        const caixa = l.estilo === "caixa" && on;
        return (
          <span
            key={i}
            style={{
              fontFamily, fontWeight: 800, fontSize: width * 0.058, lineHeight: 1.2, padding: "2px 14px", borderRadius: 14,
              color: caixa ? m.fundo : on ? m.primaria : m.texto, background: caixa ? m.primaria : "transparent",
              textShadow: caixa ? "none" : "0 4px 18px rgba(0,0,0,.85), 0 0 4px rgba(0,0,0,.9)",
            }}
          >
            {l.palavras[i].text.replace(/[.,;:…]+$/, "")}
          </span>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- composição
const ComFrameEntrada: React.FC<{ c: Cena; m: Marca; dur: number; primeira: boolean }> = ({ c, m, dur, primeira }) => {
  const frame = useCurrentFrame();
  const Comp = CENAS[c.tipo] ?? CenaErro;
  // 1ª cena: animações de entrada já concluídas no frame 0 (gancho inteiro visível — P50)
  return <Comp c={c} m={m} dur={dur} fe={primeira ? frame + 120 : frame} />;
};

const CenaNaTimeline: React.FC<{ c: Cena; m: Marca; primeira: boolean }> = ({ c, m, primeira }) => {
  const { fps } = useVideoConfig();
  const de = Math.round(c.inicio * fps);
  const dur = Math.max(1, Math.round(c.fim * fps) - de);
  const corpo = <ComFrameEntrada c={c} m={m} dur={dur} primeira={primeira} />;
  // fade só quando a cena pede ("entrada": "fade") e nunca na 1ª
  const comFade = c.entrada === "fade" && !primeira && c.tipo !== "preto";
  return (
    <Sequence from={de} durationInFrames={dur} premountFor={fps} name={`${c.id} · ${c.tipo}`}>
      {comFade ? <Entrada>{corpo}</Entrada> : corpo}
    </Sequence>
  );
};

export const Video: React.FC<{ dados: DadosVideo }> = ({ dados: d }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: d.marca.fundo }}>
      {d.cenas.map((c, i) => (
        <CenaNaTimeline key={c.id} c={c} m={d.marca} primeira={i === 0} />
      ))}
      <Legenda d={d} />
      {d.audio.voz ? <Audio src={staticFile(d.audio.voz)} /> : null}
      {d.audio.musica ? <Audio src={staticFile(d.audio.musica)} volume={d.audio.volumeMusica ?? 0.12} /> : null}
      {(d.sfx ?? []).map((s, i) => (
        <Sequence key={`sfx${i}`} from={Math.round(s.inicio * fps)} layout="none">
          <Audio src={staticFile(s.src)} volume={s.volume ?? 0.6} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
