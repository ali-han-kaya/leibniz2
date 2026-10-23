import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Closing, Evidence, GateChain, Seal, Timeline, Title } from "./scenes";
import { useLeibnizData } from "./useLeibnizData"; /**
 * Kare butcesi: 760 kare @ 30 fps = 25.33 sn.
 *  1 Title     0-89    (90f)
 *  2 Timeline  90-289  (200f)  verdict/çıkış kodu dagilim grafigi
 *  3 Evidence 290-399 (110f)  statik kartlar — kare harcamaz
 *  4 GateChain 400-609 (210f)  K0-K15 gerçek klayers.json zinciri
 *  5 Seal     610-709 (100f)
 *  6 Closing  710-759 (50f)
 *
 * Toplam 760 DEĞİŞMEZ (Root.tsx + check_render.py + CI sözleşmesi); yeni
 * sahne içeriğine kare, Evidence'ın statik kartlarından alındı.
 *
 * `dataUrl` verilirse (tarayici-ici oynatma) veri o adresten okunur; verilmezse
 * render varsayilani (`staticFile`) kullanilir. Boylece TEK sahne agaci hem
 * mp4 render'inda hem @remotion/player'da calisir — kopya sahne yok.
 */
export const LeibnizChainView: React.FC<{ dataUrl?: string }> = ({
  dataUrl,
}) => {
  const data = useLeibnizData(dataUrl);

  if (!data) {
    return <AbsoluteFill style={{ backgroundColor: "#0B0F14" }} />;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#0B0F14" }}>
      <Sequence from={0} durationInFrames={90} name="1 · Title">
        <Title data={data} lengthInFrames={90} />
      </Sequence>
      <Sequence from={90} durationInFrames={200} name="2 · Timeline">
        <Timeline data={data} lengthInFrames={200} />
      </Sequence>
      <Sequence from={290} durationInFrames={110} name="3 · Evidence">
        <Evidence data={data} lengthInFrames={110} />
      </Sequence>
      <Sequence from={400} durationInFrames={210} name="4 · GateChain">
        <GateChain data={data} lengthInFrames={210} />
      </Sequence>
      <Sequence from={610} durationInFrames={100} name="5 · Seal">
        <Seal data={data} lengthInFrames={100} />
      </Sequence>
      <Sequence from={710} durationInFrames={50} name="6 · Closing">
        <Closing data={data} lengthInFrames={50} />
      </Sequence>
    </AbsoluteFill>
  );
};
