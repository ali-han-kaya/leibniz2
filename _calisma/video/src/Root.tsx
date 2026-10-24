import React from "react";
import { Composition } from "remotion";
import { LeibnizChain } from "./LeibnizChain";
import { GateChainRuns } from "./GateChainRuns";

/**
 * İki kompozisyon, tek sahne ağacı kaynağı:
 *
 *  1. LeibnizChain  — 760 kare (25.33 sn): kanonik teslim zincirinin 6 sahneli
 *                     anlatımı; 4. sahnede klayers.runs.json'un son 3 anlık
 *                     görüntüsü.
 *  2. GateChainRuns — 630 kare (21.00 sn): history.jsonl'den koşu-başına
 *                     16 kapı (K0–K15) zinciri; kaydı olmayan kapı KAYIT YOK.
 *
 * Kare sayıları make_data.py'de TEK yerde yaşar (FRAMES / GATE_HISTORY_FRAMES);
 * test_video_data_contract.py Root.tsx ile o sabitlerin eşleştiğini doğrular.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="LeibnizChain"
        component={LeibnizChain}
        durationInFrames={760}
        fps={30}
        width={1280}
        height={720}
      />
      <Composition
        id="GateChainRuns"
        component={GateChainRuns}
        durationInFrames={630}
        fps={30}
        width={1280}
        height={720}
      />
    </>
  );
};
