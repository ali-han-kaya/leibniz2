import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const palette = {
  bg: "#0B0F14",
  bgSoft: "#111823",
  line: "#1E2A38",
  text: "#E6EDF3",
  dim: "#8B9AAB",
  faint: "#4A5A6B",
  accent: "#5EC8D8",
  accent2: "#9AD1A4",
  warn: "#E0B354",
  bad: "#D98A7B",
};

export const ease = Easing.bezier(0.42, 0, 0.18, 1);

/** 0 -> 1 across the first `span` frames, eased, for staged reveals. */
export const stage = (frame: number, start: number, span = 14) =>
  interpolate(frame, [start, start + span], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

/** Fade in, hold, fade out across the whole scene. */
export const sceneAlpha = (
  frame: number,
  lengthInFrames: number,
  fade = 12
) => {
  const out = interpolate(
    frame,
    [lengthInFrames - fade, lengthInFrames],
    [1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: ease,
    }
  );
  const inn = interpolate(frame, [0, fade], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  return Math.min(inn, out);
};

/**
 * Staged reveal: fades and lifts a block into place.
 * Keeps natural layout height — the block must never be collapsed to a
 * pixel value, or its text is clipped away entirely.
 */
export const Reveal: React.FC<{
  p: number;
  distance?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ p, distance = 18, children, style }) => (
  <div
    style={{
      opacity: p,
      transform: `translateY(${interpolate(p, [0, 1], [distance, 0], { easing: ease })}px)`,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Mono: React.FC<{
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: number;
  letter?: number;
}> = ({
  children,
  size = 20,
  color = palette.text,
  weight = 500,
  letter = 0,
}) => (
  <div
    style={{
      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
      fontSize: size,
      color,
      fontWeight: weight,
      letterSpacing: letter,
    }}
  >
    {children}
  </div>
);

export const Sans: React.FC<{
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: number;
  letter?: number;
}> = ({
  children,
  size = 20,
  color = palette.text,
  weight = 500,
  letter = 0,
}) => (
  <div
    style={{
      fontFamily:
        'system-ui, -apple-system, "Segoe UI", Inter, Helvetica, Arial, sans-serif',
      fontSize: size,
      color,
      fontWeight: weight,
      letterSpacing: letter,
    }}
  >
    {children}
  </div>
);

/** Full-bleed scene shell: background wash, frame number, fixed baseline grid. */
export const Slide: React.FC<{
  children: React.ReactNode;
  kicker: string;
  lengthInFrames: number;
}> = ({ children, kicker, lengthInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const alpha = sceneAlpha(frame, lengthInFrames);
  const t = frame / fps;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: palette.bg,
        opacity: alpha,
        display: "flex",
        flexDirection: "column",
        padding: "64px 80px",
        boxSizing: "border-box",
        fontFeatureSettings: '"tnum" 1',
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `linear-gradient(180deg, ${palette.bg} 0%, ${palette.bgSoft} 100%)`,
          zIndex: -1,
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Sans size={16} color={palette.faint} letter={2.4}>
          {kicker}
        </Sans>
        <Mono size={15} color={palette.faint}>
          {t.toFixed(2)}s / {(760 / fps).toFixed(2)}s
        </Mono>
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {children}
      </div>
    </div>
  );
};

export const Rule: React.FC<{
  width: number;
  color?: string;
  thickness?: number;
}> = ({ width, color = palette.line, thickness = 1 }) => (
  <div
    style={{ width, height: thickness, backgroundColor: color, marginTop: 18 }}
  />
);
