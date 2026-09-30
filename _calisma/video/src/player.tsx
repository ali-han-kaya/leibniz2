import React from "react";
import { createRoot } from "react-dom/client";
import { Player } from "@remotion/player";
import { LeibnizChainView } from "./LeibnizChainView";

/**
 * Tarayici-ici oynatma giris noktasi (@remotion/player).
 *
 * Remotion Studio DEGIL: Studio ayri bir sunucu + webpack dev-cache ile gelir
 * ve arac tarafindan surekli olarak oldurulur. Player butun yuzeyi TEK bir
 * statik paket haline getirir; preview sunucusu yalnizca bu dosyayi ve
 * uretilen veriyi servis eder.
 *
 * Veri adresi gomulu script yerine `data-*` niteligiyle gelir: preview
 * sunucusunun CSP'si `script-src 'self' 'nonce-…'` — inline script'i yalnizca
 * nonce ile serbest birakilir, `data-src` ise script degildir.
 */
const mount = document.getElementById("root");

if (!mount) {
  // Sessiz bos sayfa yerine gorunur hata: mount noktasi sayfa sozlesmesinin
  // parcasidir (build/player.html ile eslesmezse burada durur).
  document.body.textContent =
    "LeibnizChain player: #root bulunamadi — player.html sayfasi bozulmus.";
} else {
  const dataUrl = mount.getAttribute("data-src") ?? undefined;
  createRoot(mount).render(
    <React.StrictMode>
      <div
        style={{
          backgroundColor: "#0B0F14",
          padding: 24,
          fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
          color: "#E6EDF3",
        }}
      >
        <Player
          component={LeibnizChainView}
          // Bilesene ozel proplar `inputProps` ile gecer; dogrudan
          // `dataUrl={...}` yazmak Player'in kendi proplari sanilir ve
          // yutulur (olculdu: "leibniz.json 404" — staticFile yedege dustu).
          inputProps={{ dataUrl }}
          durationInFrames={760}
          fps={30}
          compositionWidth={1280}
          compositionHeight={720}
          style={{ width: "100%", maxWidth: 1280 }}
          controls
          loop
          clickToPlay
          doubleClickToFullscreen
          spaceKeyToPlayOrPause
          acknowledgeRemotionLicense
        />
      </div>
    </React.StrictMode>
  );
}
