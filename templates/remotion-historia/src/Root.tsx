import { Composition } from "remotion";
import { Historia } from "./Historia";
import type { DadosHistoria } from "./Historia";
import dados from "./historia.json";

const historia = dados as unknown as DadosHistoria;

export const RemotionRoot = () => (
  <Composition
    id="Historia"
    component={Historia}
    durationInFrames={Math.max(1, Math.ceil(historia.duracao * historia.fps))}
    fps={historia.fps}
    width={historia.width}
    height={historia.height}
    defaultProps={{ dados: historia }}
  />
);
