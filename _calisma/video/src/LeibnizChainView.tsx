import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Closing, Evidence, Gates, Seal, Timeline, Title } from "./scenes";
import { useLeibnizData } from "./useLeibnizData"; /**
 * Kare butcesi: 760 kare @ 30 fps = 25.33 sn.
 *  1 Title     0-89    (90f)
 *  2 Timeline  90-289  (200f)  verdict/çıkış kodu dagilim grafigi
 *  3 Evidence 290-409 (120f)  statik kartlar — kare harcamaz
 *  4 Gates     410-609 (200f)  kapi kirilmasi animasyonu + durum tahtasi
 *  5 Seal     610-709 (100f)
 *  6 Closing  710-759 (50f)
 *
 * Toplam 760 DEGİŞMEZ (Root.tsx + check_render.py + CI sözleşmesi); yeni
 * sahne içeriğine kare, Evidence/Closing gibi statik sahnelerden alındı.
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
      <Sequence from={290} durationInFrames={120} name="3 · Evidence">
        <Evidence data={data} lengthInFrames={120} />
      </Sequence>
      <Sequence from={410} durationInFrames={200} name="4 · Gates">
        <Gates data={data} lengthInFrames={200} />
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
