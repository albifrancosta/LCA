import React from "react";
import { AbsoluteFill } from "remotion";
import { useT } from "./base";
import { Balao, Carimbo, Contador, Faixa, FundoMotion, GraficoBarras, LinhaDoTempo, MapaRota, Notificacao, TextoCinetico, useTremor } from "./motion";

// Vitrine da biblioteca (14 s): cada peça em 2 s. Para conferir: npx remotion still MotionDemo out/m.png --frame=<s*30>
export const DURACAO_DEMO = 14;

const Bloco: React.FC<{ de: number; ate: number; children: React.ReactNode }> = ({ de, ate, children }) => {
  const t = useT();
  return t >= de && t < ate ? <AbsoluteFill>{children}</AbsoluteFill> : null;
};

export const MotionDemo: React.FC = () => {
  const tremor = useTremor(9.2);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <FundoMotion de={0} />
      <Bloco de={0} ate={2}>
        <TextoCinetico topo={640} palavras={[{ texto: "Cadê", t: 0.2 }, { texto: "o", t: 0.45 }, { texto: "técnico?", t: 0.7, cor: "#87C968" }]} />
      </Bloco>
      <Bloco de={2} ate={4}>
        <Contador ini={2.2} fim={3.4} para={280} formato={(n) => `${Math.floor(n / 60)} h ${String(Math.round(n) % 60).padStart(2, "0")} min`} rotulo="sem imagem" topo={640} tam={140} />
      </Bloco>
      <Bloco de={4} ate={6}>
        <MapaRota ini={4.2} fim={5.6} origem="Base" destino="Cond. Jardim das Palmeiras" eta="Chega em 12 min" />
      </Bloco>
      <Bloco de={6} ate={8}>
        <GraficoBarras de={6.1} unidade=" h" barras={[{ rotulo: "Antes", valor: 9, cor: "#EF4444" }, { rotulo: "Com a MinhaMarca", valor: 2 }]} />
      </Bloco>
      <Bloco de={8} ate={10}>
        <AbsoluteFill style={{ transform: tremor }}>
          <Balao de={8.1} texto="Saiu?" x={90} y={360} />
          <Balao de={8.5} texto="Esqueceu?" x={380} y={560} />
          <Carimbo de={9.2} texto="QUEM FICA MAL?" topo={1000} />
        </AbsoluteFill>
      </Bloco>
      <Bloco de={10} ate={12}>
        <Notificacao de={10.1} titulo="Saí para o atendimento" sub="Técnico · 10h12" y={500} />
        <Notificacao de={10.6} titulo="Câmeras de volta ✓" sub="Técnico · 11h05" y={710} destaque />
        <Faixa de={11.1} texto="SEM LIGAÇÃO" fundo="#16A34A" topo={1000} />
      </Bloco>
      <Bloco de={12} ate={14}>
        <LinhaDoTempo aparece={12} topo={560} etapas={[{ nome: "Agendada", hora: "08h05", t: 12.1 }, { nome: "A caminho", hora: "10h12", t: 12.4 }, { nome: "Em atendimento", hora: "10h31", t: 12.7 }, { nome: "Concluída", hora: "11h05", t: 13.1 }]} />
      </Bloco>
    </AbsoluteFill>
  );
};
