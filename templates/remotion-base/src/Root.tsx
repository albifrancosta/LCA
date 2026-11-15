import { Composition } from "remotion";
import { Video } from "./Video";
import type { DadosVideo } from "./Video";
import dados from "./video.json";

const video = dados as unknown as DadosVideo;

export const RemotionRoot = () => {
  return (
    <Composition
      id="Video"
      component={Video}
      durationInFrames={Math.max(1, Math.ceil(video.duracao * video.fps))}
      fps={video.fps}
      width={video.width}
      height={video.height}
      defaultProps={{ dados: video }}
    />
  );
};
