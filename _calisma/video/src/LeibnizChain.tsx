import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Closing, Evidence, Gates, Seal, Timeline, Title } from "./scenes";
import { useLeibnizData } from "./useLeibnizData";

/**
 * Frame budget: 760 frames @ 30 fps = 25.33 s.
 *  1 Title     0–89    (90f)
 *  2 Timeline  90–269  (180f)
 *  3 Evidence 270–449 (180f)
 *  4 Gates    450–589 (140f)
 *  5 Seal     590–699 (110f)
 *  6 Closing  700–759 (60f)
 */
export const LeibnizChain: React.FC = () => {
  const data = useLeibnizData();

  if (!data) {
    return <AbsoluteFill style={{ backgroundColor: "#0B0F14" }} />;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#0B0F14" }}>
      <Sequence from={0} durationInFrames={90} name="1 · Title">
        <Title data={data} lengthInFrames={90} />
      </Sequence>
      <Sequence from={90} durationInFrames={180} name="2 · Timeline">
        <Timeline data={data} lengthInFrames={180} />
      </Sequence>
      <Sequence from={270} durationInFrames={180} name="3 · Evidence">
        <Evidence data={data} lengthInFrames={180} />
      </Sequence>
      <Sequence from={450} durationInFrames={140} name="4 · Gates">
        <Gates data={data} lengthInFrames={140} />
      </Sequence>
      <Sequence from={590} durationInFrames={110} name="5 · Seal">
        <Seal data={data} lengthInFrames={110} />
      </Sequence>
      <Sequence from={700} durationInFrames={60} name="6 · Closing">
        <Closing data={data} lengthInFrames={60} />
      </Sequence>
    </AbsoluteFill>
  );
};
