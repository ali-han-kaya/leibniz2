import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { LeibnizData, Run } from "./data";
import { Mono, palette, Reveal, Sans, stage } from "./ui";

/** Shared scene shell: background wash, fixed bottom progress hairline. */
const Shell: React.FC<{
  lengthInFrames: number;
  children: React.ReactNode;
  fade?: number;
  fadeIn?: number;
}> = ({ lengthInFrames, children, fade = 12, fadeIn = 6 }) => {
  const f = useCurrentFrame();
  // fadeIn=0 means "hard cut in" — interpolate() rejects a zero-length range,
  // and the very first frame of the file must not be black.
  const fadeInFactor =
    fadeIn > 0
      ? interpolate(f, [0, fadeIn], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  const alpha =
    fadeInFactor *
    interpolate(f, [lengthInFrames - fade, lengthInFrames], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: palette.bg,
        backgroundImage: `linear-gradient(180deg, ${palette.bg} 0%, ${palette.bgSoft} 100%)`,
        display: "flex",
        flexDirection: "column",
        padding: "58px 80px 64px",
        boxSizing: "border-box",
        opacity: alpha,
        fontFeatureSettings: '"tnum" 1',
      }}
    >
      {children}
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 46,
          height: 1,
          backgroundColor: palette.line,
        }}
      >
        <div
          style={{
            height: 1,
            backgroundColor: palette.accent,
            width: `${(100 * (f + 1)) / 760}%`,
          }}
        />
      </div>
    </div>
  );
};

const Kicker: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Sans size={15} color={palette.accent} letter={3.6} weight={600}>
    {children}
  </Sans>
);

const Heading: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Sans size={44} weight={650} color={palette.text} letter={-0.5}>
    {children}
  </Sans>
);

/* ---------------------------------------------------------------- scene 1 */
export const Title: React.FC<{ data: LeibnizData; lengthInFrames: number }> = ({
  data,
  lengthInFrames,
}) => {
  const f = useCurrentFrame();
  const m = data.meta;

  const stats = [
    { k: "ÇÖZÜNÜRLÜK", v: `${m.width}×${m.height}` },
    { k: "KARE HIZI", v: `${m.fps} fps` },
    { k: "UZUNLUK", v: `${m.frames} kare` },
    { k: "SÜRE", v: `${m.duration_s.toFixed(2)} sn` },
  ];

  return (
    <Shell lengthInFrames={lengthInFrames} fadeIn={0}>
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        {/* Visible on frame 0 — the file must not open on an empty black card. */}
        <Kicker>REPRODUCIBLE DELIVERY</Kicker>

        <div style={{ height: 22 }} />

        <Reveal p={stage(f, 6, 18)} distance={26}>
          <div
            style={{
              fontFamily: "system-ui, -apple-system, sans-serif",
              fontSize: 88,
              fontWeight: 700,
              color: palette.text,
              letterSpacing: -2,
              lineHeight: 1.05,
            }}
          >
            {m.composition}
          </div>
        </Reveal>

        <div style={{ height: 14 }} />

        <Reveal p={stage(f, 14, 18)} distance={20}>
          <div
            style={{
              fontFamily: "system-ui, -apple-system, sans-serif",
              fontSize: 30,
              fontWeight: 400,
              color: palette.dim,
            }}
          >
            {m.repo} · kanonik teslim zinciri
          </div>
        </Reveal>

        <div style={{ height: 34 }} />
        <Reveal p={stage(f, 22, 16)}>
          <div
            style={{ width: 520, height: 1, backgroundColor: palette.line }}
          />
        </Reveal>
        <div style={{ height: 30 }} />

        <div style={{ display: "flex", gap: 52 }}>
          {stats.map((item, i) => (
            <Reveal key={item.k} p={stage(f, 28 + i * 7, 14)} distance={14}>
              <Sans size={13} color={palette.faint} letter={1.8}>
                {item.k}
              </Sans>
              <div style={{ height: 8 }} />
              <Mono size={26} color={palette.text}>
                {item.v}
              </Mono>
            </Reveal>
          ))}
        </div>
      </div>

      <Reveal p={stage(f, 40, 16)}>
        <Mono size={12} color={palette.faint}>
          YENİDEN İNŞA · kaynak proje kayboldu; spesifikasyon findings.md:70-75
          ve recovery_patches_20260918/patch1789754982-84993:540-549
          kayıtlarından
        </Mono>
      </Reveal>
    </Shell>
  );
};

/* ---------------------------------------------------------------- scene 2 */
const RunRow: React.FC<{
  run: Run;
  index: number;
  frame: number;
  maxMs: number;
}> = ({ run, index, frame, maxMs }) => {
  const p = stage(frame, 22 + index * 9, 14);
  const ms = (run.duration_s ?? 0) * 1000;
  const bar = Math.max(3, (ms / maxMs) * 420);
  const color =
    run.verdict === "PASS"
      ? palette.accent2
      : run.verdict === "FAIL"
        ? palette.bad
        : palette.warn;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        marginBottom: 17,
      }}
    >
      <div style={{ width: 26 }}>
        <Mono size={15} color={palette.faint}>
          {String(run.n).padStart(2, "0")}
        </Mono>
      </div>
      <div style={{ width: 108 }}>
        <Mono size={16} color={palette.dim}>
          {run.day}
        </Mono>
      </div>
      <div style={{ width: 420, height: 18, position: "relative" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundColor: palette.bgSoft,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: bar * p,
            backgroundColor: palette.line,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            backgroundColor: color,
            opacity: p,
          }}
        />
        <div style={{ position: "absolute", left: 420 + 14, top: 1 }}>
          <Mono size={15} color={palette.dim}>
            {run.duration_s !== null ? `${run.duration_s.toFixed(2)} s` : "—"}
          </Mono>
        </div>
      </div>
      <div style={{ width: 60 }}>
        <Mono size={15} color={color}>
          {run.verdict}
        </Mono>
      </div>
      <Reveal p={p} distance={10}>
        <Mono size={13} color={palette.faint}>
          {run.findings} bulgu
        </Mono>
      </Reveal>
    </div>
  );
};

export const Timeline: React.FC<{
  data: LeibnizData;
  lengthInFrames: number;
}> = ({ data, lengthInFrames }) => {
  const f = useCurrentFrame();
  const maxMs = Math.max(
    ...data.runs.map((r) => (r.duration_s ?? 0) * 1000),
    1
  );

  return (
    <Shell lengthInFrames={lengthInFrames}>
      <Reveal p={stage(f, 2, 14)}>
        <Kicker>SAHNE 2 / 6</Kicker>
      </Reveal>
      <div style={{ height: 12 }} />
      <Reveal p={stage(f, 6, 16)}>
        <Heading>Koşu zaman çizelgesi</Heading>
      </Reveal>
      <div style={{ height: 10 }} />
      <Reveal p={stage(f, 12, 16)}>
        <Mono size={16} color={palette.dim}>
          _calisma/CIKTI/history.jsonl ·{" "}
          {data.run_span.data_missing
            ? "veri yok (temiz klon / CI)"
            : `${data.run_span.count} kayıt · ${data.run_span.first} → ${data.run_span.last}`}
        </Mono>
      </Reveal>

      <div style={{ height: 34 }} />

      <div>
        {data.runs.map((run, i) => (
          <RunRow key={run.n} run={run} index={i} frame={f} maxMs={maxMs} />
        ))}
      </div>

      <div style={{ marginTop: "auto" }}>
        <Reveal p={stage(f, 110, 18)}>
          <div style={{ display: "flex", gap: 40, alignItems: "center" }}>
            <Mono size={13} color={palette.faint} letter={1.6}>
              VERDICT DAĞILIMI
            </Mono>
            {Object.entries(data.run_span.verdicts).map(([k, v]) => (
              <Mono
                key={k}
                size={15}
                color={k === "PASS" ? palette.accent2 : palette.bad}
              >
                {k} {v}
              </Mono>
            ))}
            <Mono size={15} color={palette.faint}>
              {data.run_span.data_missing
                ? "koşu verisi bu ortamda yok — sahne iskeleti doğrulandı"
                : `toplam ${data.runs.reduce(
                    (n, r) => n + r.findings,
                    0
                  )} bulgu · P0=0 P1=0`}
            </Mono>
          </div>
        </Reveal>
      </div>
    </Shell>
  );
};

/* ---------------------------------------------------------------- scene 3 */
export const Evidence: React.FC<{
  data: LeibnizData;
  lengthInFrames: number;
}> = ({ data, lengthInFrames }) => {
  const f = useCurrentFrame();

  return (
    <Shell lengthInFrames={lengthInFrames}>
      <Reveal p={stage(f, 2, 14)}>
        <Kicker>SAHNE 3 / 6</Kicker>
      </Reveal>
      <div style={{ height: 12 }} />
      <Reveal p={stage(f, 6, 16)}>
        <Heading>Dondurulmuş kanıt kartları</Heading>
      </Reveal>
      <div style={{ height: 30 }} />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gridAutoRows: "1fr",
          gap: 24,
          flex: 1,
          minHeight: 0,
        }}
      >
        {data.evidence.map((card, i) => (
          <Reveal
            key={card.label}
            p={stage(f, 18 + i * 12, 16)}
            distance={20}
            style={{
              border: `1px solid ${palette.line}`,
              borderLeft: `3px solid ${card.ok ? palette.accent2 : palette.warn}`,
              backgroundColor: palette.bgSoft,
              padding: "26px 30px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              boxSizing: "border-box",
            }}
          >
            <Sans size={14} color={palette.faint} letter={2}>
              {card.label.toUpperCase()}
            </Sans>
            <div style={{ height: 14 }} />
            <Mono size={40} color={palette.text} weight={600}>
              {card.value}
            </Mono>
            <div style={{ height: 10 }} />
            <Mono size={14} color={palette.dim}>
              {card.sub}
            </Mono>
          </Reveal>
        ))}
      </div>

      <Reveal p={stage(f, 96, 18)}>
        <Mono size={12} color={palette.faint}>
          KAYNAK · findings.md:102 · progress.md:6 · recovery_patches_20260918 ·
          test_id_residual_acceptance_doc.py
        </Mono>
      </Reveal>
    </Shell>
  );
};

/* ---------------------------------------------------------------- scene 4 */
export const Gates: React.FC<{ data: LeibnizData; lengthInFrames: number }> = ({
  data,
  lengthInFrames,
}) => {
  const f = useCurrentFrame();
  const g = data.gates;
  const perRow = 6;
  const rows = [
    g.all.slice(0, perRow),
    g.all.slice(perRow, perRow * 2),
    g.all.slice(perRow * 2),
  ];

  return (
    <Shell lengthInFrames={lengthInFrames}>
      <Reveal p={stage(f, 2, 14)}>
        <Kicker>SAHNE 4 / 6</Kicker>
      </Reveal>
      <div style={{ height: 12 }} />
      <Reveal p={stage(f, 6, 16)}>
        <Heading>Kapı zinciri {g.range}</Heading>
      </Reveal>
      <div style={{ height: 10 }} />
      <Reveal p={stage(f, 12, 16)}>
        <Mono size={15} color={palette.dim}>
          çekirdek katman K0–K7 her koşuda · tam tarama --full
        </Mono>
      </Reveal>

      <div
        style={{
          marginTop: 26,
          display: "flex",
          flexDirection: "column",
          gap: 14,
          flex: 1,
          minHeight: 0,
        }}
      >
        {rows.map((row, ri) => (
          <div
            key={ri}
            style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}
          >
            {row.map((k, ki) => {
              const idx = ri * perRow + ki;
              const p = stage(f, 18 + idx * 4, 12);
              const isCore = g.core.includes(k);
              return (
                <Reveal
                  key={k}
                  p={p}
                  distance={12}
                  style={{
                    flex: 1,
                    border: `1px solid ${p > 0.85 ? palette.line : palette.bgSoft}`,
                    backgroundColor: palette.bgSoft,
                    padding: "16px 18px",
                    boxSizing: "border-box",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <Mono size={18} color={palette.text} weight={600}>
                      {k}
                    </Mono>
                    <Mono
                      size={15}
                      color={p > 0.6 ? palette.accent2 : palette.faint}
                    >
                      ✓
                    </Mono>
                  </div>
                  <div style={{ height: 8 }} />
                  <Sans size={13} color={palette.dim}>
                    {g.names[k]}
                  </Sans>
                  {isCore ? <div style={{ height: 8 }} /> : null}
                  {isCore ? (
                    <Mono size={11} color={palette.accent} letter={1.2}>
                      ÇEKİRDEK
                    </Mono>
                  ) : null}
                </Reveal>
              );
            })}
          </div>
        ))}
      </div>

      <Reveal p={stage(f, 100, 18)}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 20 }}>
          <Mono size={28} color={palette.accent2} weight={600}>
            {g.verdict}
          </Mono>
          <Mono size={14} color={palette.faint}>
            verify_delivery · P0=0 · P1=0 · 16 katman
          </Mono>
        </div>
      </Reveal>
    </Shell>
  );
};

/* ---------------------------------------------------------------- scene 5 */
const HashRow: React.FC<{
  label: string;
  value: string;
  frame: number;
  offset: number;
}> = ({ label, value, frame, offset }) => {
  const p = stage(frame, 14 + offset * 15, 16);
  const reveal = Math.floor(
    interpolate(p, [0, 1], [0, value.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  return (
    <Reveal p={p} distance={12}>
      <Sans size={13} color={palette.faint} letter={2}>
        {label.toUpperCase()}
      </Sans>
      <div style={{ height: 10 }} />
      <div style={{ display: "flex", flexWrap: "wrap", width: 1100 }}>
        {value.split("").map((ch, i) => (
          <span
            key={i}
            style={{
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 22,
              color: i < reveal ? palette.text : palette.line,
              width: 17.2,
            }}
          >
            {ch}
          </span>
        ))}
      </div>
      <div style={{ height: 26 }} />
    </Reveal>
  );
};

export const Seal: React.FC<{ data: LeibnizData; lengthInFrames: number }> = ({
  data,
  lengthInFrames,
}) => {
  const f = useCurrentFrame();
  const s = data.seal;

  return (
    <Shell lengthInFrames={lengthInFrames}>
      <Reveal p={stage(f, 2, 14)}>
        <Kicker>SAHNE 5 / 6</Kicker>
      </Reveal>
      <div style={{ height: 12 }} />
      <Reveal p={stage(f, 6, 16)}>
        <Heading>Bütünlük mührü</Heading>
      </Reveal>
      <div style={{ height: 22 }} />

      <HashRow
        label="delivery raw sha256"
        value={s.delivery_raw}
        frame={f}
        offset={0}
      />
      <HashRow
        label="delivery stripped sha256"
        value={s.delivery_stripped}
        frame={f}
        offset={1}
      />
      <HashRow
        label="pdftex 3-pass canonical"
        value={s.pdftex_3pass}
        frame={f}
        offset={2}
      />

      <Reveal p={stage(f, 82, 18)}>
        <Mono size={12} color={palette.faint}>
          SHA-256 · 64 haneli · test_id_residual_acceptance_doc.py sabitleri
        </Mono>
      </Reveal>
    </Shell>
  );
};

/* ---------------------------------------------------------------- scene 6 */
export const Closing: React.FC<{
  data: LeibnizData;
  lengthInFrames: number;
}> = ({ data, lengthInFrames }) => {
  const f = useCurrentFrame();
  const pulse = 0.6 + 0.4 * Math.sin((f / lengthInFrames) * Math.PI * 2);

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: palette.bg,
        backgroundImage: `radial-gradient(circle at 50% 45%, ${palette.bgSoft} 0%, ${palette.bg} 72%)`,
        opacity: interpolate(f, [0, 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      }}
    >
      <Mono size={21} color={palette.accent2} weight={600}>
        KANONİK TESLİM DOĞRULANDI
      </Mono>
      <div style={{ height: 26 }} />
      <div
        style={{
          fontFamily: "system-ui, -apple-system, sans-serif",
          fontSize: 56,
          fontWeight: 700,
          color: palette.text,
          letterSpacing: -1,
        }}
      >
        Leibniz zinciri
      </div>
      <div style={{ height: 20 }} />
      <Mono size={18} color={palette.dim}>
        {data.meta.width}×{data.meta.height} · {data.meta.fps} fps ·{" "}
        {data.meta.frames} kare · {data.meta.duration_s.toFixed(2)} sn
      </Mono>
      <div style={{ height: 40 }} />
      <div style={{ opacity: pulse }}>
        <Mono size={13} color={palette.faint}>
          {data.meta.repo} · yeniden inşa · kaynak proje kayboldu
        </Mono>
      </div>
    </div>
  );
};
