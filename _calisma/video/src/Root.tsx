import React from "react";
import { Composition } from "remotion";
import { LeibnizChain } from "./LeibnizChain";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="LeibnizChain"
      component={LeibnizChain}
      durationInFrames={760}
      fps={30}
      width={1280}
      height={720}
    />
  );
};
