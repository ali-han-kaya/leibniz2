import React from "react";
import { LeibnizChainView } from "./LeibnizChainView";

/**
 * Render giris noktasi. Sahne agaci LeibnizChainView'da yasar; boylece
 * mp4 render'i ile @remotion/player ayni bilesenleri kullanir.
 */
export const LeibnizChain: React.FC = () => <LeibnizChainView />;
