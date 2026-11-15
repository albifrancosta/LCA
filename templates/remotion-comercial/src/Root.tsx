import { Composition } from "remotion";
import { Comercial } from "./Comercial";
import { ComercialIlustrado } from "./ComercialIlustrado";
import { FPS, H, W } from "./base";

export const RemotionRoot = () => (
  <>
    <Composition id="Comercial" component={Comercial} durationInFrames={60 * FPS} fps={FPS} width={W} height={H} defaultProps={{ variante: "A" as const }} />
    <Composition id="ComercialIlustrado" component={ComercialIlustrado} durationInFrames={60 * FPS} fps={FPS} width={W} height={H} />
  </>
);
