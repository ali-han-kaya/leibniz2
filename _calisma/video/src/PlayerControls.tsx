import React, { useCallback, useEffect, useRef, useState } from "react";
import type { PlayerRef } from "@remotion/player";

/**
 * Tarayıcı-içi oynatıcının kendi kontrol çubuğu.
 *
 * Neden @remotion/player'ın `controls` çubuğu DEĞİL: Remotion 4.0.530'un
 * etiketleri sabittir ve İngilizcedir ("Play video", "Mute sound",
 * "Enter Fullscreen") — sayfa `lang="tr"` olduğu için ekran okuyucu Türkçe
 * sayfada İngilizce düğme adları okur (WCAG 3.1.2). Kütüphane etiket
 * override'ı sunmadığı için (yalnız `renderCustomControls` ile EK kontrol)
 * çubuk bize ait: adlar, `aria-pressed` durumu ve odak halkası burada
 * tanımlanır, kontrast hesabı da opak zemin sayesinde axe tarafından
 * çözülebilir hale gelir.
 *
 * Sözleşmeler (test_preview_video_player.TestPlayerA11ySource pinler):
 *  - her düğme görünür Türkçe ad taşır; oynat/duraklat adı DURUMLA değişir,
 *  - ses/tam ekran düğmeleri `aria-pressed` ile açık/kapalı durumunu bildirir,
 *  - konum kaydırıcısı `aria-valuetext` ile "0:12 / 0:25" biçiminde okunur,
 *  - görünür süre metni ekran okuyucudan gizlenir (kaydırıcı zaten okur).
 */

const ICON_SIZE = 20;

function PlayIcon() {
  return (
    <svg
      width={ICON_SIZE}
      height={ICON_SIZE}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M8 5.5v13l11-6.5-11-6.5Z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg
      width={ICON_SIZE}
      height={ICON_SIZE}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" />
    </svg>
  );
}

function MuteIcon() {
  return (
    <svg
      width={ICON_SIZE}
      height={ICON_SIZE}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 9.5h3L12 5v14l-5-4.5H4v-5Z" fill="currentColor" />
      <path
        d="m16 9 5 6m0-6-5 6"
        stroke="currentColor"
        strokeWidth="1.8"
        fill="none"
      />
    </svg>
  );
}

function SoundIcon() {
  return (
    <svg
      width={ICON_SIZE}
      height={ICON_SIZE}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 9.5h3L12 5v14l-5-4.5H4v-5Z" fill="currentColor" />
      <path
        d="M15.5 9.2a4 4 0 0 1 0 5.6M17.8 6.9a7 7 0 0 1 0 10.2"
        stroke="currentColor"
        strokeWidth="1.8"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

function FullscreenIcon() {
  return (
    <svg
      width={ICON_SIZE}
      height={ICON_SIZE}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"
        stroke="currentColor"
        strokeWidth="1.8"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

export const formatTime = (frame: number, fps: number) => {
  const totalSeconds = Math.floor(frame / fps);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};

type Props = {
  playerRef: React.RefObject<PlayerRef | null>;
  durationInFrames: number;
  fps: number;
};

export const PlayerControls: React.FC<Props> = ({
  playerRef,
  durationInFrames,
  fps,
}) => {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  // Olaylar PlayerRef emitter'ından gelir; her olay tek bir state alanını
  // günceller. `null` ref (henüz mount olmadı) sessizce yok sayılır.
  useEffect(() => {
    const ref = playerRef.current;
    if (!ref) {
      return;
    }
    const onTime = (e: { detail: { frame: number } }) =>
      setFrame(e.detail.frame);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMute = (e: { detail: { isMuted: boolean } }) =>
      setMuted(e.detail.isMuted);
    const onFullscreen = (e: { detail: { isFullscreen: boolean } }) =>
      setFullscreen(e.detail.isFullscreen);

    ref.addEventListener("timeupdate", onTime);
    ref.addEventListener("seeked", onTime);
    ref.addEventListener("play", onPlay);
    ref.addEventListener("pause", onPause);
    ref.addEventListener("ended", onPause);
    ref.addEventListener("mutechange", onMute);
    ref.addEventListener("fullscreenchange", onFullscreen);
    return () => {
      ref.removeEventListener("timeupdate", onTime);
      ref.removeEventListener("seeked", onTime);
      ref.removeEventListener("play", onPlay);
      ref.removeEventListener("pause", onPause);
      ref.removeEventListener("ended", onPause);
      ref.removeEventListener("mutechange", onMute);
      ref.removeEventListener("fullscreenchange", onFullscreen);
    };
  }, [playerRef]);

  const togglePlay = useCallback(() => {
    playerRef.current?.toggle();
  }, [playerRef]);

  const toggleMute = useCallback(() => {
    const ref = playerRef.current;
    if (!ref) {
      return;
    }
    if (ref.isMuted()) {
      ref.unmute();
    } else {
      ref.mute();
    }
  }, [playerRef]);

  const toggleFullscreen = useCallback(() => {
    const ref = playerRef.current;
    if (!ref) {
      return;
    }
    if (ref.isFullscreen()) {
      ref.exitFullscreen();
    } else {
      ref.requestFullscreen();
    }
  }, [playerRef]);

  const seek = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const next = Number(e.currentTarget.value);
      setFrame(next);
      playerRef.current?.seekTo(next);
    },
    [playerRef]
  );

  const lastFrame = Math.max(0, durationInFrames - 1);
  const position = `${formatTime(frame, fps)} / ${formatTime(lastFrame, fps)}`;

  return (
    <div className="lc-controls" role="group" aria-label="Oynatıcı kontrolleri">
      <button
        type="button"
        className="lc-controls__button"
        aria-label={playing ? "Duraklat" : "Oynat"}
        onClick={togglePlay}
      >
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>

      <input
        className="lc-controls__seek"
        type="range"
        min={0}
        max={lastFrame}
        step={1}
        value={frame}
        aria-label="Oynatma konumu"
        aria-valuetext={position}
        onChange={seek}
      />

      <span className="lc-controls__time" aria-hidden="true">
        {position}
      </span>

      <button
        type="button"
        className="lc-controls__button"
        aria-label={muted ? "Sesi aç" : "Sesi kapat"}
        aria-pressed={muted}
        onClick={toggleMute}
      >
        {muted ? <MuteIcon /> : <SoundIcon />}
      </button>

      <button
        type="button"
        className="lc-controls__button"
        aria-label={fullscreen ? "Tam ekrandan çık" : "Tam ekran"}
        aria-pressed={fullscreen}
        onClick={toggleFullscreen}
      >
        <FullscreenIcon />
      </button>
    </div>
  );
};
