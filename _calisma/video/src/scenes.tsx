import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { BoardItem, LeibnizData, Run } from "./data";
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

/* ------------------------------------------------------------ grafik ortakları */

/** Çubuk genişliği — cetvel ve segmentler aynı sayıyı kullanmalı. */
const TRACK_W = 452;

/** verdict metnine göre renk: koşu satırı ile dağılım çubuğu aynı rengi paylaşır. */
const verdictColor = (v: string) =>
  v === "PASS" ? palette.accent2 : v === "FAIL" ? palette.bad : palette.warn;

/** Negatif çıkış kodu, sürecin sinyalle öldürüldüğü anlamına gelir (-15 = SIGTERM). */
const isSignalExit = (code: number | null) => code !== null && code < 0;

const stateColor = (s: BoardItem["state"]) =>
  s === "PASS"
    ? palette.accent2
    : s === "WARN"
      ? palette.warn
      : s === "FAIL"
        ? palette.bad
        : palette.faint;

const stateGlyph = (s: BoardItem["state"]) =>
  s === "PASS" ? "✓" : s === "WARN" ? "⚠" : s === "FAIL" ? "✕" : "?";

/** {FAIL: 7} + toplam 7 → "FAIL 7/7"; sentinel (toplam 0) → "—". */
const tally = (rec: Record<string, number>, total: number) =>
  total === 0
    ? "—"
    : Object.entries(rec)
        .map(([k, v]) => `${k} ${v}/${total}`)
        .join(" · ");

type BarSegment = { key: string; count: number; color: string };

/**
 * Yığılmış dağılım çubuğu: solda etiket, ortada yüzde şerit, sağda sayaç.
 * Segmentler sırayla `stage()` ile dolar. `total` 0 ise (sentinel) sıfıra bölme
 * yapılmaz — yalnız boş iskelet çizilir.
 */
const StackBar: React.FC<{
  label: string;
  segments: BarSegment[];
  total: number;
  frame: number;
  base: number;
  trail: string;
  trailColor: string;
}> = ({ label, segments, total, frame, base, trail, trailColor }) => {
  const safe = total > 0 ? total : 1;
  let cursor = 0;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 18,
        marginBottom: 11,
      }}
    >
      <div style={{ width: 100, flexShrink: 0 }}>
        <Mono size={12} color={palette.faint} letter={1.4}>
          {label}
        </Mono>
      </div>
      <div
        style={{
          width: TRACK_W,
          height: 22,
          position: "relative",
          backgroundColor: palette.bgSoft,
          flexShrink: 0,
        }}
      >
        {segments.map((s, i) => {
          const share = s.count / safe;
          const left = cursor;
          cursor += share;
          const p = stage(frame, base + i * 5, 12);
          return (
            <div
              key={s.key}
              style={{
                position: "absolute",
                left: `${left * 100}%`,
                top: 0,
                bottom: 0,
                width: `${share * 100}%`,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: p > 0 ? `${100 / p}%` : "0%",
                  backgroundColor: s.color,
                  opacity: 0.9,
                }}
              />
            </div>
          );
        })}
        {total === 0 ? (
          <div
            style={{
              position: "absolute",
              inset: 0,
              border: `1px solid ${palette.line}`,
            }}
          />
        ) : null}
      </div>
      <Mono size={14} color={trailColor}>
        {trail}
      </Mono>
    </div>
  );
};

/** 0–100% cetveli — çubukların altına, aynı hizada. */
const Ruler: React.FC = () => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <div style={{ width: 100, flexShrink: 0 }} />
    <div style={{ width: TRACK_W, position: "relative", height: 14 }}>
      {[0, 25, 50, 75, 100].map((t) => (
        <div
          key={t}
          style={{
            position: "absolute",
            left: `${t}%`,
            top: 0,
            transform:
              t === 0
                ? "none"
                : t === 100
                  ? "translateX(-100%)"
                  : "translateX(-50%)",
          }}
        >
          <Mono size={10} color={palette.faint}>
            {t}%
          </Mono>
        </div>
      ))}
    </div>
  </div>
);

/** status_board kalemi rozeti. */
const Chip: React.FC<{ label: string; state: BoardItem["state"] }> = ({
  label,
  state,
}) => {
  const c = stateColor(state);
  return (
    <div
      style={{
        border: `1px solid ${c}`,
        backgroundColor: palette.bgSoft,
        padding: "5px 11px",
        display: "flex",
        alignItems: "center",
        gap: 7,
      }}
    >
      <Mono size={13} color={c}>
        {stateGlyph(state)}
      </Mono>
      <Mono size={13} color={palette.text}>
        {label}
      </Mono>
    </div>
  );
};

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
  const p = stage(frame, 22 + index * 8, 14);
  const ms = (run.duration_s ?? 0) * 1000;
  const bar = Math.max(3, (ms / maxMs) * 340);
  const color = verdictColor(run.verdict);
  const signal = isSignalExit(run.exit_code);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 18,
        marginBottom: 10,
      }}
    >
      <div style={{ width: 24 }}>
        <Mono size={14} color={palette.faint}>
          {String(run.n).padStart(2, "0")}
        </Mono>
      </div>
      <div style={{ width: 96 }}>
        <Mono size={15} color={palette.dim}>
          {run.day}
        </Mono>
      </div>
      {/* Her sütun KENDI genişliğinde: süre etiketi mutlak konumlanırsa
          verdict sütununa biner ve iki satıra sarar (ölçüldü: 250. kare). */}
      <div
        style={{ width: 340, height: 16, position: "relative", flexShrink: 0 }}
      >
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
      </div>
      <div style={{ width: 70 }}>
        <Mono size={14} color={palette.dim}>
          {run.duration_s !== null ? `${run.duration_s.toFixed(2)} s` : "—"}
        </Mono>
      </div>
      <div style={{ width: 48 }}>
        <Mono size={14} color={color}>
          {run.verdict}
        </Mono>
      </div>
      <div style={{ width: 54 }}>
        <Mono size={14} color={signal ? palette.bad : palette.dim}>
          {run.exit_code === null
            ? "—"
            : signal
              ? `−${Math.abs(run.exit_code)}`
              : String(run.exit_code)}
        </Mono>
      </div>
      <Reveal p={p} distance={8}>
        <Mono size={12} color={palette.faint}>
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
  const span = data.run_span;
  const total = span.count;
  const sev = span.severity;
  const maxMs = Math.max(
    ...data.runs.map((r) => (r.duration_s ?? 0) * 1000),
    1
  );

  const verdictSegments: BarSegment[] = Object.entries(span.verdicts).map(
    ([k, v]) => ({ key: k, count: v, color: verdictColor(k) })
  );
  const exitSegments: BarSegment[] = span.exits.map((e) => ({
    key: String(e.code),
    count: e.count,
    color: isSignalExit(e.code) ? palette.bad : palette.warn,
  }));
  const verdictKeys = Object.keys(span.verdicts);

  const exitTrail =
    total === 0
      ? "—"
      : span.exits
          .map(
            (e) =>
              `${e.code === null ? "?" : e.code < 0 ? `−${Math.abs(e.code)}` : e.code}` +
              `${e.signal ? ` ${e.signal}` : ""} ${e.count}/${total}`
          )
          .join(" · ");
  const signalExit = span.exits.find((e) => isSignalExit(e.code));

  // Tek sonuçlu dağılımda grafik tek renkli olur; bu bir görsel hata değil,
  // verinin kendisi. Not bunu açıkça söyler ve yeşil koşu UYDURMAZ.
  const note = span.data_missing
    ? "veri yok (temiz klon / CI) — dağılım iskeleti doğrulandı"
    : verdictKeys.length === 1
      ? `tek sonuçlu dağılım: ${total}/${total} koşu ${verdictKeys[0]} — P0=P1=0, bulgu yok; hepsi exit=${signalExit?.code ?? "?"} (${signalExit?.signal ?? "sinyal yok"}) ile kesildi, geçen koşu KAYIT YOK.`
      : `toplam ${sev.findings} bulgu · P0=${sev.p0} P1=${sev.p1} · sapma ${tally(span.drift, total)}`;

  const metrics = [
    { k: "P0", v: `${sev.p0}` },
    { k: "P1", v: `${sev.p1}` },
    { k: "BULGU", v: `${sev.findings}` },
    { k: "SAPMA", v: tally(span.drift, total) },
    { k: "Z3", v: `${sev.z3_passed}/${sev.z3_total}` },
    {
      k: "KAPI TELEMETRISI",
      v: `${span.telemetry.reported.length}/${span.telemetry.columns}`,
    },
  ];

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
          {span.data_missing
            ? "veri yok (temiz klon / CI)"
            : `${span.count} kayıt · ${span.first} → ${span.last}`}
        </Mono>
      </Reveal>

      <div style={{ height: 30 }} />

      <div>
        {data.runs.map((run, i) => (
          <RunRow key={run.n} run={run} index={i} frame={f} maxMs={maxMs} />
        ))}
      </div>

      <div
        style={{
          marginTop: "auto",
          borderTop: `1px solid ${palette.line}`,
          paddingTop: 18,
        }}
      >
        <Reveal p={stage(f, 100, 16)}>
          <StackBar
            label="VERDICT"
            segments={verdictSegments}
            total={total}
            frame={f}
            base={102}
            trail={tally(span.verdicts, total)}
            trailColor={
              verdictKeys.length === 1
                ? verdictColor(verdictKeys[0])
                : palette.dim
            }
          />
          <StackBar
            label="ÇIKIŞ KODU"
            segments={exitSegments}
            total={total}
            frame={f}
            base={116}
            trail={exitTrail}
            trailColor={palette.bad}
          />
          <Ruler />
        </Reveal>

        <Reveal p={stage(f, 136, 16)}>
          <div style={{ display: "flex", gap: 26, marginTop: 18 }}>
            {metrics.map((m) => (
              <div
                key={m.k}
                style={{ display: "flex", alignItems: "baseline", gap: 8 }}
              >
                <Sans size={11} color={palette.faint} letter={1.4}>
                  {m.k}
                </Sans>
                <Mono size={14} color={palette.text}>
                  {m.v}
                </Mono>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal p={stage(f, 154, 16)}>
          <div style={{ height: 16 }} />
          <Mono size={12} color={palette.faint}>
            {note}
          </Mono>
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

      <Reveal p={stage(f, 84, 16)}>
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
  const bk = g.break;
  // Kırılma yalnızca history.jsonl'da sinyalle kesilmiş koşu varsa oynar.
  const broken = bk.kind === "signal";
  const perRow = 6;
  const rows = [
    g.all.slice(0, perRow),
    g.all.slice(perRow, perRow * 2),
    g.all.slice(perRow * 2),
  ];

  // Kırılma animasyonu: soldan sağa tarama çizgisi, ardından sönümlenen flaş.
  const sweep = broken
    ? interpolate(f, [112, 132], [-4, 104], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  const flash = broken
    ? interpolate(f, [112, 122, 154], [0, 0.8, 0.06], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  return (
    <Shell lengthInFrames={lengthInFrames}>
      <Reveal p={stage(f, 2, 14)}>
        <Kicker>SAHNE 4 / 6</Kicker>
      </Reveal>
      <div style={{ height: 10 }} />
      <Reveal p={stage(f, 6, 16)}>
        <Heading>Kapı zinciri {g.range}</Heading>
      </Reveal>
      <div style={{ height: 8 }} />
      <Reveal p={stage(f, 12, 16)}>
        <Mono size={14} color={palette.dim}>
          çekirdek K0–K7 · tam zincir {g.all.length} katman · durum tahtası{" "}
          {g.board.length > 0
            ? `${g.board.length} kalem (son koşu)`
            : "veri yok"}
        </Mono>
      </Reveal>

      <div style={{ marginTop: 20, position: "relative" }}>
        {rows.map((row, ri) => (
          <div
            key={ri}
            style={{
              display: "flex",
              gap: 11,
              marginBottom: ri < rows.length - 1 ? 11 : 0,
            }}
          >
            {row.map((k, ki) => {
              const idx = ri * perRow + ki;
              const p = stage(f, 18 + idx * 5, 12);
              const isCore = g.core.includes(k);
              const ok = g.ok_ids.includes(k);
              const mark = ok ? "✓" : broken ? "!" : "·";
              const markColor = ok
                ? palette.accent2
                : broken
                  ? palette.bad
                  : palette.faint;
              const tag = ok
                ? "GEÇTİ"
                : broken
                  ? "RAPOR YOK"
                  : isCore
                    ? "ÇEKİRDEK"
                    : "KAYIT YOK";
              const tagColor = ok
                ? palette.accent2
                : broken
                  ? palette.bad
                  : isCore
                    ? palette.accent
                    : palette.faint;
              return (
                <Reveal
                  key={k}
                  p={p}
                  distance={12}
                  style={{
                    flex: 1,
                    border: `1px solid ${
                      p <= 0.85
                        ? palette.bgSoft
                        : broken && !ok && flash > 0.25
                          ? palette.bad
                          : palette.line
                    }`,
                    backgroundColor: palette.bgSoft,
                    padding: "12px 14px",
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
                    <Mono size={17} color={palette.text} weight={600}>
                      {k}
                    </Mono>
                    <Mono size={14} color={p > 0.6 ? markColor : palette.faint}>
                      {p > 0.6 ? mark : ""}
                    </Mono>
                  </div>
                  <div style={{ height: 6 }} />
                  <Sans size={12} color={palette.dim}>
                    {g.names[k]}
                  </Sans>
                  <div style={{ height: 7 }} />
                  <Mono size={10} color={tagColor} letter={1.1}>
                    {tag}
                  </Mono>
                </Reveal>
              );
            })}
          </div>
        ))}
        {broken && flash > 0.02 ? (
          <div
            style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
          >
            <div
              style={{
                position: "absolute",
                left: `${sweep}%`,
                top: -8,
                bottom: -8,
                width: 2,
                backgroundColor: palette.bad,
                boxShadow: `0 0 16px 3px ${palette.bad}`,
                opacity: Math.min(1, flash * 1.4),
              }}
            />
          </div>
        ) : null}
      </div>

      <div style={{ marginTop: 20 }}>
        {broken ? (
          <Reveal p={stage(f, 126, 16)}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                border: `1px solid ${palette.bad}`,
                borderLeft: `3px solid ${palette.bad}`,
                backgroundColor: palette.bgSoft,
                padding: "13px 20px",
              }}
            >
              <Mono size={19} color={palette.bad} weight={600}>
                KIRILMA
              </Mono>
              <Mono size={15} color={palette.text}>
                exit={bk.exit_code} {bk.signal ?? ""} · {bk.runs}/{bk.of_runs}{" "}
                koşu · %{bk.share_pct} · en uzun{" "}
                {bk.max_duration_s !== null
                  ? `${bk.max_duration_s.toFixed(2)} sn`
                  : "—"}
              </Mono>
              <Mono size={13} color={palette.faint}>
                kapı telemetrisi {bk.telemetry_reported}/{bk.telemetry_columns}{" "}
                sütun · P0={bk.p0} P1={bk.p1}
              </Mono>
            </div>
          </Reveal>
        ) : (
          <Reveal p={stage(f, 126, 16)}>
            <div
              style={{
                border: `1px solid ${palette.line}`,
                borderLeft: `3px solid ${palette.accent2}`,
                backgroundColor: palette.bgSoft,
                padding: "13px 20px",
              }}
            >
              <Mono size={15} color={palette.dim}>
                {bk.kind === "no_data"
                  ? "kapı kırılma kaydı yok — history.jsonl bu ortamda yok (temiz klon / CI)"
                  : `kırılma yok · ${bk.of_runs} koşunun hiçbirinde sinyalle kesilme görülmedi`}
              </Mono>
            </div>
          </Reveal>
        )}
      </div>

      <div style={{ height: 16 }} />

      <Reveal p={stage(f, 148, 16)}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <Mono size={11} color={palette.faint} letter={1.6}>
            STATUS_BOARD · SON KOŞU
          </Mono>
          {g.board.length > 0 ? (
            g.board.map((item) => (
              <Chip key={item.label} label={item.label} state={item.state} />
            ))
          ) : (
            <Mono size={13} color={palette.faint}>
              tahta kaydı yok
            </Mono>
          )}
        </div>
      </Reveal>

      <div style={{ height: 14 }} />

      <Reveal p={stage(f, 164, 16)}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
          <Mono
            size={20}
            weight={600}
            color={
              g.verdict.warn === 0 && g.verdict.ok > 0
                ? palette.accent2
                : palette.warn
            }
          >
            {g.verdict.ok} ✓ · {g.verdict.warn} ⚠
            {g.verdict.other > 0 ? ` · ${g.verdict.other} ?` : ""}
          </Mono>
          <Mono size={12} color={palette.faint}>
            {g.group_warn.length > 0
              ? `grup sinyali: ${g.group_warn.join(" · ")}`
              : "grup sinyeli yok"}
            {broken ? " · kapı başına sonuç kaydı yok" : ""}
          </Mono>
        </div>
        <div style={{ height: 8 }} />
        <Mono size={10} color={palette.faint}>
          status_board: {g.board_raw || "—"} · tahta çeşitliliği{" "}
          {data.run_span.board_agreement.distinct}/
          {data.run_span.board_agreement.of_runs}
        </Mono>
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

      <Reveal p={stage(f, 72, 16)}>
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
