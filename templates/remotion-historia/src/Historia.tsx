import React from "react";
import { AbsoluteFill, Easing, Freeze, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/google-fonts/Poppins";

// Modelo "história interativa" — engenharia reversa de ref-2026-11-03-whatsapp.
// Gramática: zoom em cadeia · plano com ação (camadas) · POV de celular · close → preto · troca de expressão · cartão final.

const { fontFamily } = loadFont("normal", { weights: ["700", "800"], subsets: ["latin"] });

type Par = [number, number];
export type Camada = {
  src: string;
  largura: number; // fração da largura do vídeo
  x: Par; // centro, fração da largura (início → fim do plano)
  y: Par;
  escala?: Par;
  opacidade?: Par;
  passo?: number; // balanço de caminhada (px)
};
export type Plano = {
  id: string;
  tipo: "cadeia" | "imagem" | "pov" | "expressoes" | "preto" | "cartao";
  inicio: number;
  fim: number;
  imagens?: string[];
  zoom?: Par; // escala no início → fim (cadeia: de cada imagem)
  foco?: Par; // ponto que a câmera persegue (0–1)
  tremor?: number; // câmera na mão (px)
  camadas?: Camada[];
  trocas?: number[]; // expressoes: segundos absolutos em que troca de imagem
  toque?: number; // pov: segundo absoluto em que o dedo toca a tela
  texto?: string; // cartao
  video?: string; // clipe animado por IA (gerar_clipe_fal.py) — substitui a imagem do plano
  videoDur?: number;
  clipeDe?: number;
  titulo?: string; // texto grande por cima do plano, visível desde o 1º quadro (gancho sem som)
};

const Titulo: React.FC<{ texto: string }> = ({ texto }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const s = interpolate(frame, [0, 4, 8], [1.25, 0.96, 1], clamp);
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: height * 0.1 }}>
      <div style={{
        fontFamily, fontWeight: 800, fontSize: width * 0.115, color: "#FFF4D6", letterSpacing: width * 0.004,
        transform: `scale(${s}) rotate(-3deg)`, textShadow: "0 6px 24px rgba(0,0,0,0.85), 0 2px 0 rgba(0,0,0,0.9)",
        borderBottom: `${width * 0.008}px solid #F2B23A`, paddingBottom: width * 0.01, opacity: interpolate(frame, [0, 2], [0.6, 1], clamp),
      }}>{texto}</div>
    </AbsoluteFill>
  );
};
export type Palavra = { text: string; start: number; end: number };
export type DadosHistoria = {
  fps: number;
  width: number;
  height: number;
  duracao: number;
  estilo: { corLegenda: string; alturaLegenda: number; tamanhoLegenda: number; palavrasPorGrupo: number };
  audio: { voz?: string; trilha?: string; volumeTrilha: number; ambiente?: string; volumeAmbiente?: number; silencios: { inicio: number; fim: number }[] };
  planos: Plano[];
  legenda: Palavra[];
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const entre = (par: Par | undefined, p: number, padrao: number) => (par ? par[0] + (par[1] - par[0]) * p : padrao);
const FADE = 0.5; // dissolve entre imagens da cadeia (s)

/** Uma imagem com câmera: zoom em direção ao foco + tremor opcional. */
const Quadro: React.FC<{ src: string; z: number; foco?: Par; tremor?: number; opacidade?: number }> = ({ src, z, foco = [0.5, 0.5], tremor = 0, opacidade = 1 }) => {
  const frame = useCurrentFrame();
  const tx = tremor ? Math.sin(frame / 7) * tremor + Math.sin(frame / 3.1) * tremor * 0.4 : 0;
  const ty = tremor ? Math.cos(frame / 9) * tremor : 0;
  return (
    <AbsoluteFill style={{ opacity: opacidade, overflow: "hidden" }}>
      <Img
        src={staticFile(src)}
        style={{
          width: "100%", height: "100%", objectFit: "cover",
          transform: `translate(${tx}px, ${ty}px) scale(${z})`, transformOrigin: `${foco[0] * 100}% ${foco[1] * 100}%`,
        }}
      />
    </AbsoluteFill>
  );
};

const Camadas: React.FC<{ camadas: Camada[]; p: number }> = ({ camadas, p }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <>
      {camadas.map((c, i) => {
        const w = c.largura * width;
        const passo = c.passo ? Math.abs(Math.sin(frame / 5)) * -c.passo : 0;
        return (
          <Img
            key={i}
            src={staticFile(c.src)}
            style={{
              position: "absolute", width: w, left: entre(c.x, p, 0.5) * width - w / 2, top: entre(c.y, p, 0.5) * height + passo,
              transform: `translateY(-50%) scale(${entre(c.escala, p, 1)})`, opacity: entre(c.opacidade, p, 1),
            }}
          />
        );
      })}
    </>
  );
};

// ---------------------------------------------------------------- tipos de plano
const PlanoCadeia: React.FC<{ c: Plano }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const imgs = c.imagens ?? [];
  const fatia = (c.fim - c.inicio) / Math.max(1, imgs.length);
  const t = frame / fps;
  const i = Math.min(imgs.length - 1, Math.floor(t / fatia));
  const p = (t - i * fatia) / fatia;
  const proxima = i + 1 < imgs.length && t > (i + 1) * fatia - FADE;
  const pp = proxima ? interpolate(t, [(i + 1) * fatia - FADE, (i + 1) * fatia], [0, 1], clamp) : 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Quadro src={imgs[i]} z={entre(c.zoom, p, 1)} foco={c.foco} tremor={c.tremor} />
      {proxima ? <Quadro src={imgs[i + 1]} z={entre(c.zoom, 0, 1)} foco={c.foco} tremor={c.tremor} opacidade={pp} /> : null}
      {c.camadas ? <Camadas camadas={c.camadas} p={t / (c.fim - c.inicio)} /> : null}
    </AbsoluteFill>
  );
};

const PlanoImagem: React.FC<{ c: Plano }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = frame / fps / (c.fim - c.inicio);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Quadro src={(c.imagens ?? [])[0]} z={entre(c.zoom, Easing.inOut(Easing.sin)(Math.min(1, p)), 1)} foco={c.foco} tremor={c.tremor} />
      {c.camadas ? <Camadas camadas={c.camadas} p={p} /> : null}
    </AbsoluteFill>
  );
};

/** POV: mãos segurando o celular; a tela mostra a imagem (ex.: câmera de segurança). */
const PlanoPov: React.FC<{ c: Plano }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const p = t / (c.fim - c.inicio);
  const [tela, fundo] = c.imagens ?? [];
  const z = entre(c.zoom, p, 1);
  const w = width * 0.78;
  const toque = c.toque !== undefined ? c.toque - c.inicio : -99;
  const dedo = interpolate(t, [toque - 0.4, toque, toque + 0.5, toque + 0.9], [0, 1, 1, 0], clamp);
  const balanco = Math.sin(frame / 25) * 6;
  return (
    <AbsoluteFill style={{ backgroundColor: "#05070d" }}>
      {fundo ? <Quadro src={fundo} z={1.1} opacidade={0.45} /> : null}
      <AbsoluteFill style={{ transform: `scale(${z}) rotate(${-4 + balanco * 0.1}deg) translateY(${balanco}px)`, transformOrigin: "50% 45%" }}>
        <div
          style={{
            position: "absolute", left: (width - w) / 2, top: height * 0.1, width: w, height: w * 1.95, borderRadius: w * 0.11,
            background: "#121418", padding: w * 0.035, boxShadow: "0 40px 120px rgba(0,0,0,.7)",
          }}
        >
          <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: w * 0.085, overflow: "hidden", background: "#0b0d12" }}>
            {tela ? <Img src={staticFile(tela)} style={{ position: "absolute", top: "12%", width: "100%", height: "62%", objectFit: "cover" }} /> : null}
            {/* interface do app de câmera */}
            <div style={{ position: "absolute", top: "4%", left: "7%", right: "7%", display: "flex", justifyContent: "space-between", color: "#cfd3dc", fontFamily, fontSize: w * 0.06 }}>
              <span>‹</span>
              <span style={{ fontSize: w * 0.035, alignSelf: "center", color: "#ff5a5a" }}>● REC</span>
              <span>⚙</span>
            </div>
            <div style={{ position: "absolute", bottom: "7%", left: 0, right: 0, display: "flex", justifyContent: "space-around" }}>
              {["▶", "◉", "▦"].map((s) => (
                <div key={s} style={{ width: w * 0.16, height: w * 0.16, borderRadius: 99, background: "#1f2430", color: "#cfd3dc", display: "flex", justifyContent: "center", alignItems: "center", fontSize: w * 0.06 }}>
                  {s}
                </div>
              ))}
            </div>
          </div>
        </div>
        {/* polegares nas laterais */}
        <div style={{ position: "absolute", left: (width - w) / 2 - w * 0.16, top: height * 0.7, width: w * 0.22, height: w * 0.36, borderRadius: "50%", background: "#F1D9C0", boxShadow: "inset -10px 0 0 rgba(0,0,0,.08)" }} />
        <div style={{ position: "absolute", right: (width - w) / 2 - w * 0.16, top: height * 0.66, width: w * 0.22, height: w * 0.36, borderRadius: "50%", background: "#F1D9C0", boxShadow: "inset 10px 0 0 rgba(0,0,0,.08)" }} />
        {dedo > 0 ? (
          <div
            style={{
              position: "absolute", left: width * 0.52, top: height * (0.62 - 0.12 * dedo), width: w * 0.2, height: w * 0.38, borderRadius: "45% 45% 40% 40%",
              background: "#F1D9C0", opacity: Math.min(1, dedo * 2), boxShadow: "0 10px 30px rgba(0,0,0,.4)",
            }}
          />
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Mesmo enquadramento, troca de expressão do personagem a cada marca de tempo. */
const PlanoExpressoes: React.FC<{ c: Plano }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = c.inicio + frame / fps;
  const imgs = c.imagens ?? [];
  const i = Math.min(imgs.length - 1, (c.trocas ?? []).filter((x) => t >= x).length);
  const p = frame / fps / (c.fim - c.inicio);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Quadro src={imgs[i]} z={entre(c.zoom ?? [1, 1.06], p, 1)} foco={c.foco} />
    </AbsoluteFill>
  );
};

const PlanoCartao: React.FC<{ c: Plano }> = ({ c }) => {
  // cartão final: imagem do plano escurecida ao fundo (opcional), 1ª linha = título em destaque,
  // linhas "A —"/"B —" viram botões que entram em sequência; a última linha é o chamado
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();
  const linhas = (c.texto ?? "DEIXE NOS COMENTÁRIOS.\nVOCÊ DECIDE!").toUpperCase().split("\n");
  const img = c.imagens?.[0];
  const entra = (i: number) => {
    const t = frame - (6 + i * 0.45 * fps);
    return { opacity: interpolate(t, [0, 6], [0, 1], clamp), transform: `translateY(${interpolate(t, [0, 8], [40, 0], clamp)}px) scale(${interpolate(t, [0, 5, 9], [0.85, 1.06, 1], clamp)})` };
  };
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", justifyContent: "center", alignItems: "center" }}>
      {img ? <Img src={staticFile(img)} style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover",
        transform: `scale(${interpolate(frame, [0, 8 * fps], [1.05, 1.15], clamp)})`, filter: "brightness(0.38) blur(2px)" }} /> : null}
      <div style={{ display: "flex", flexDirection: "column", gap: width * 0.035, alignItems: "center", width: "86%" }}>
        {linhas.map((l, i) => {
          const opcao = /^[AB] —/.test(l);
          const titulo = i === 0;
          return (
            <div key={i} style={{ ...entra(i), fontFamily, fontWeight: 800, textAlign: "center", color: titulo ? "#FFD24A" : "#fff",
              fontSize: width * (titulo ? 0.075 : opcao ? 0.06 : 0.05), lineHeight: 1.1, textShadow: "0 6px 24px rgba(0,0,0,.8)",
              ...(opcao ? { background: "rgba(255,255,255,0.12)", border: "4px solid #FFD24A", borderRadius: width * 0.03,
                padding: `${width * 0.025}px ${width * 0.05}px`, width: "100%" } : {}) }}>{l}</div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const PlanoPreto: React.FC<{ c: Plano }> = () => <AbsoluteFill style={{ backgroundColor: "#000" }} />;

/** Clipe de IA no lugar da imagem: desacelera até 0,6× para caber na frase e depois segura o último quadro. */
const PlanoClipe: React.FC<{ c: Plano }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const dur = c.fim - c.inicio;
  const de = c.clipeDe ?? 0; // começa o clipe deste segundo (reaproveita um clipe em 2 planos: geral → punch-in)
  const vd = (c.videoDur ?? dur) - de;
  const rate = Math.max(0.6, Math.min(1, vd / dur));
  const ultimo = Math.floor((vd / rate) * fps) - 2;
  const z = c.zoom ? interpolate(frame, [0, dur * fps], c.zoom, clamp) : 1; // punch-in / zoom lento sobre o clipe
  const [fx, fy] = c.foco ?? [0.5, 0.5];
  const video = <OffthreadVideo src={staticFile(c.video ?? "")} muted playbackRate={rate} trimBefore={de > 0 ? Math.round(de * fps) : undefined}
    style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${z})`, transformOrigin: `${fx * 100}% ${fy * 100}%` }} />;
  return <AbsoluteFill style={{ backgroundColor: "#000" }}>{frame < ultimo ? video : <Freeze frame={ultimo}>{video}</Freeze>}</AbsoluteFill>;
};

const PLANOS = { cadeia: PlanoCadeia, imagem: PlanoImagem, pov: PlanoPov, expressoes: PlanoExpressoes, preto: PlanoPreto, cartao: PlanoCartao };

// ---------------------------------------------------------------- legenda (medida no original)
const Legenda: React.FC<{ d: DadosHistoria }> = ({ d }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const ps = d.legenda;
  // grupos: até N palavras, quebra em pontuação ou pausa
  const grupos: [number, number][] = [];
  let ini = 0;
  ps.forEach((w, i) => {
    const fimFrase = /[.,?!:…]$/.test(w.text) || (ps[i + 1] !== undefined && ps[i + 1].start - w.end > 0.4);
    if (i - ini + 1 >= d.estilo.palavrasPorGrupo || fimFrase || i === ps.length - 1) {
      grupos.push([ini, i]);
      ini = i + 1;
    }
  });
  const g = grupos.find(([a, b], k) => t >= ps[a].start - 0.05 && t < Math.min(grupos[k + 1] ? ps[grupos[k + 1][0]].start : Infinity, ps[b].end + 0.6)); // some 0,6 s depois da última palavra (não fica parada em cena muda)
  if (!g) return null;
  const tam = height * d.estilo.tamanhoLegenda;
  return (
    <div
      style={{
        position: "absolute", left: width * 0.08, right: width * 0.08, top: height * d.estilo.alturaLegenda - tam * 0.7,
        display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `0 ${tam * 0.28}px`,
      }}
    >
      {ps.slice(g[0], g[1] + 1).map((w, k) => {
        const on = t >= w.start && t < (ps[g[0] + k + 1]?.start ?? w.end + 0.3);
        return (
          <span
            key={k}
            style={{
              fontFamily, fontWeight: 700, fontSize: tam, lineHeight: 1.3, color: "#fff", padding: `0 ${tam * 0.18}px`,
              borderRadius: tam * 0.22, background: on ? d.estilo.corLegenda : "transparent",
              textShadow: on ? "none" : "0 2px 6px rgba(0,0,0,.85)",
            }}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- composição
export const Historia: React.FC<{ dados: DadosHistoria }> = ({ dados: d }) => {
  const { fps } = useVideoConfig();
  const volumeTrilha = (f: number) => {
    const t = f / fps;
    // trilha alta o tempo todo (≈5 dB abaixo da voz) e some nas pausas dramáticas
    const corte = d.audio.silencios.reduce(
      (m, s) => Math.min(m, interpolate(t, [s.inicio - 0.15, s.inicio, s.fim, s.fim + 0.4], [1, 0.03, 0.03, 1], clamp)),
      1,
    );
    const fim = interpolate(t, [d.duracao - 4, d.duracao - 3], [1, 0], clamp);
    return d.audio.volumeTrilha * corte * fim;
  };
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {d.planos.map((c) => {
        const Comp = c.video ? PlanoClipe : PLANOS[c.tipo];
        const de = Math.round(c.inicio * fps);
        return (
          <Sequence key={c.id} from={de} durationInFrames={Math.max(1, Math.round(c.fim * fps) - de)} premountFor={fps} name={`${c.id} · ${c.tipo}`}>
            <Comp c={c} />
            {c.titulo ? <Titulo texto={c.titulo} /> : null}
          </Sequence>
        );
      })}
      <Legenda d={d} />
      {d.audio.voz ? <Audio src={staticFile(d.audio.voz)} /> : null}
      {d.audio.trilha ? <Audio src={staticFile(d.audio.trilha)} volume={volumeTrilha} /> : null}
      {d.audio.ambiente ? <Audio src={staticFile(d.audio.ambiente)} volume={d.audio.volumeAmbiente ?? 1} /> : null}
    </AbsoluteFill>
  );
};
