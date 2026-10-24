import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {
  GateHistory,
  GateHistoryGate,
  GateHistoryRun,
  GateHistoryStatus,
} from "./data";
import { Mono, palette, Reveal, Sans, stage } from "./ui";
import { useLeibnizData } from "./useLeibnizData";

/**
 * İkinci kompozisyon: GateChainRuns (K0–K15, koşu koşu).
 *
 * Birinci kompozisyon (LeibnizChain) klayers.runs.json'un SON 3 anlık
 * görüntüsünü gösterir. Bu kompozisyon başka bir soruyu cevaplar: tarih
 * boyunca HER koşuda 16 kapının durumu neydi? Kaynak yalnız
 * `_calisma/CIKTI/history.jsonl`; her satır kendi kaydıyla çizilir.
 *
 * Dürüstlük sözleşmesi (make_data.gate_states_for_run ile aynı):
 *   PASS / FAIL / SKIP → koşunun kendi `layers` haritası
 *   WARN / PASS / FAIL  → koşunun status_board'unda ADI GEÇEN kapı
 *   MISSING             → kayıt yok; "KAYIT YOK" çizilir, PASS'a yükseltilmez
 *
 * Kare bütçesi veriden okunur (make_data.GATE_HISTORY_*): intro +
 * runs × per_run + outro = 630. Sayı burada KOPYALANMAZ; Root.tsx'teki
 * durationInFrames ile eşleşmesini test_video_data_contract.py doğrular.
 */

const STATUS_TEXT: Record<GateHistoryStatus, string> = {
  PASS: "GEÇTİ",
  FAIL: "KALDI",
  SKIP: "KOŞMADI",
  WARN: "UYARI",
  MISSING: "KAYIT YOK",
};

const statusColor = (status: GateHistoryStatus): string => {
  switch (status) {
    case "PASS":
      return palette.accent2;
    case "FAIL":
      return palette.bad;
    case "SKIP":
      return palette.faint;
    case "WARN":
      return palette.warn;
    default:
      return palette.line;
  }
};

const StatusChip: React.FC<{ status: GateHistoryStatus; size?: number }> = ({
  status,
  size = 10,
}) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
    }}
  >
    <div
      style={{
        width: 7,
        height: 7,
        borderRadius: 7,
        backgroundColor: statusColor(status),
      }}
    />
    <Mono
      size={size}
      color={status === "MISSING" ? palette.faint : statusColor(status)}
      letter={1.2}
    >
      {STATUS_TEXT[status]}
    </Mono>
  </div>
);

const Shell: React.FC<{
  children: React.ReactNode;
  frames: number;
}> = ({ children, frames }) => {
  const f = useCurrentFrame();
  const alpha = interpolate(f, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        backgroundImage: `linear-gradient(180deg, ${palette.bg} 0%, ${palette.bgSoft} 100%)`,
        padding: "52px 76px 58px",
        boxSizing: "border-box",
        opacity: alpha,
        fontFeatureSettings: '"tnum" 1',
      }}
    >
      {children}
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          bottom: 40,
          height: 1,
          backgroundColor: palette.line,
        }}
      >
        <div
          style={{
            height: 1,
            backgroundColor: palette.accent,
            width: `${(100 * (f + 1)) / Math.max(1, frames)}%`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

const Legend: React.FC = () => (
  <div style={{ display: "flex", gap: 26, alignItems: "center" }}>
    {(["PASS", "WARN", "FAIL", "SKIP", "MISSING"] as GateHistoryStatus[]).map(
      (status) => (
        <div
          key={status}
          style={{ display: "flex", alignItems: "center", gap: 7 }}
        >
          <div
            style={{
              width: 9,
              height: 9,
              borderRadius: 9,
              backgroundColor: statusColor(status),
              border:
                status === "MISSING" ? `1px solid ${palette.faint}` : "none",
              boxSizing: "border-box",
            }}
          />
          <Mono size={11} color={palette.dim} letter={1}>
            {STATUS_TEXT[status]}
          </Mono>
        </div>
      )
    )}
  </div>
);

const GateTile: React.FC<{
  gate: GateHistoryGate;
  local: number;
  index: number;
}> = ({ gate, local, index }) => {
  const p = stage(local, 6 + index * 3.4, 8);
  const color = statusColor(gate.status);
  const missing = gate.status === "MISSING";
  return (
    <Reveal p={p} distance={12} style={{ flex: 1 }}>
      <div
        style={{
          border: `1px solid ${missing ? palette.line : color}`,
          borderRadius: 6,
          padding: "12px 12px 10px",
          backgroundColor: missing ? "transparent" : `${color}14`,
          minHeight: 92,
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <Sans
            size={18}
            weight={650}
            color={missing ? palette.faint : palette.text}
          >
            {gate.id}
          </Sans>
          <Mono size={9} color={palette.faint} letter={1}>
            {gate.from === "layers"
              ? "LAYERS"
              : gate.from === "board"
                ? "BOARD"
                : "—"}
          </Mono>
        </div>
        <Mono size={10} color={palette.dim} letter={0.6}>
          {gate.label}
        </Mono>
        <StatusChip status={gate.status} size={10} />
      </div>
    </Reveal>
  );
};

const RunRow: React.FC<{ run: GateHistoryRun }> = ({ run }) => (
  <div style={{ display: "flex", gap: 8 }}>
    {run.gates.map((gate) => (
      <div key={gate.id} style={{ flex: 1 }}>
        <div
          style={{
            height: 5,
            borderRadius: 5,
            backgroundColor: statusColor(gate.status),
            opacity: gate.status === "MISSING" ? 0.35 : 1,
          }}
        />
      </div>
    ))}
  </div>
);

const Intro: React.FC<{ gh: GateHistory }> = ({ gh }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Reveal p={stage(f, 2, 14)}>
        <Sans size={15} color={palette.accent} letter={3.6} weight={600}>
          KOMPOZİSYON 2 · KAPI ZİNCİRİ
        </Sans>
      </Reveal>
      <div style={{ height: 22 }} />
      <Reveal p={stage(f, 8, 18)}>
        <Sans size={62} weight={680} color={palette.text} letter={-1.4}>
          16 kapı, koşu koşu
        </Sans>
      </Reveal>
      <div style={{ height: 14 }} />
      <Reveal p={stage(f, 16, 16)}>
        <Mono size={18} color={palette.dim}>
          K0 – K15 · kaynak: {gh.source} · son {gh.run_capacity} koşu
        </Mono>
      </Reveal>
      <div style={{ height: 34 }} />
      <Reveal p={stage(f, 24, 16)}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Mono size={14} color={palette.dim}>
            her kapı YALNIZ o koşunun kendi kaydıyla çizilir
          </Mono>
          <Mono size={14} color={palette.dim}>
            kaydı olmayan kapı “KAYIT YOK” — yeşile çevrilmez
          </Mono>
          <div style={{ height: 8 }} />
          <Legend />
        </div>
      </Reveal>
    </div>
  );
};

const Outro: React.FC<{ gh: GateHistory }> = ({ gh }) => {
  const f = useCurrentFrame();
  const { totals, run_count: runCount, gate_count: gateCount } = gh;
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Reveal p={stage(f, 2, 14)}>
        <Sans size={15} color={palette.accent} letter={3.6} weight={600}>
          KAYIT KAPSAMI
        </Sans>
      </Reveal>
      <div style={{ height: 26 }} />
      <Reveal p={stage(f, 8, 18)}>
        <Sans size={44} weight={660} color={palette.text} letter={-0.8}>
          {totals.reported} / {totals.cells} hücre raporlandı
        </Sans>
      </Reveal>
      <div style={{ height: 12 }} />
      <Reveal p={stage(f, 14, 14)}>
        <Mono size={16} color={palette.dim}>
          {runCount} koşu × {gateCount} kapı · boşluk = arşivde kayıt yok
        </Mono>
      </Reveal>
      <div style={{ height: 28 }} />
      <Reveal p={stage(f, 20, 14)}>
        <Mono size={14} color={palette.warn}>
          KAYIT YOK ≠ PASS — bu video eksik kanıtı tamamlamaz, gösterir.
        </Mono>
      </Reveal>
      <div style={{ height: 10 }} />
      <Reveal p={stage(f, 26, 14)}>
        <Mono size={13} color={palette.faint}>
          yeni koşular koşu-başına “layers” haritası yazdıkça bu zincir dolar
        </Mono>
      </Reveal>
    </div>
  );
};

export const GateChainRuns: React.FC<{ dataUrl?: string }> = ({ dataUrl }) => {
  const data = useLeibnizData(dataUrl);
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  if (!data) {
    return <AbsoluteFill style={{ backgroundColor: palette.bg }} />;
  }

  const gh = data.gate_history;
  const total = durationInFrames;
  const intro = gh.intro_frames;
  const outro = gh.outro_frames;
  const perRun = gh.per_run_frames;
  const runs = gh.runs;
  const runsEnd = total - outro;

  const inIntro = frame < intro;
  const inOutro = frame >= runsEnd;
  const runIndex =
    runs.length === 0
      ? 0
      : Math.min(
          runs.length - 1,
          Math.max(0, Math.floor((frame - intro) / Math.max(1, perRun)))
        );
  const local = frame - intro - runIndex * perRun;
  const run = runs[runIndex];
  const rows = run ? [run.gates.slice(0, 8), run.gates.slice(8)] : [[], []];

  return (
    <Shell frames={total}>
      {inIntro ? (
        <Intro gh={gh} />
      ) : inOutro ? (
        <Outro gh={gh} />
      ) : run ? (
        <div
          style={{ display: "flex", flexDirection: "column", height: "100%" }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-end",
            }}
          >
            <Reveal p={stage(local, 0, 10)}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <Sans size={13} color={palette.accent} letter={3} weight={600}>
                  KOŞU {runIndex + 1}/{runs.length}
                </Sans>
                <Sans size={34} weight={650} color={palette.text} letter={-0.6}>
                  {run.ts}
                </Sans>
              </div>
            </Reveal>
            <Reveal p={stage(local, 2, 10)}>
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <Mono size={12} color={palette.faint} letter={1.2}>
                  {run.layers_reported
                    ? "LAYERS KAYDI VAR"
                    : "LAYERS KAYDI YOK"}
                </Mono>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Mono size={12} color={palette.faint} letter={1.2}>
                    VERDICT
                  </Mono>
                  <Mono
                    size={16}
                    color={
                      run.verdict === "PASS" ? palette.accent2 : palette.bad
                    }
                  >
                    {run.verdict}
                  </Mono>
                </div>
              </div>
            </Reveal>
          </div>

          <div style={{ height: 18 }} />
          {rows.map((row, rowIndex) => (
            <div
              key={rowIndex}
              style={{ display: "flex", gap: 8, marginBottom: 10 }}
            >
              {row.map((gate, index) => (
                <GateTile
                  key={gate.id}
                  gate={gate}
                  local={local}
                  index={rowIndex * 8 + index}
                />
              ))}
            </div>
          ))}

          <div style={{ flex: 1 }} />
          <Reveal p={stage(local, 64, 12)}>
            <RunRow run={run} />
          </Reveal>
          <div style={{ height: 12 }} />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Mono size={12} color={palette.dim}>
              RAPORLANAN {run.reported}/{run.gates.length} · KAYIT YOK{" "}
              {run.missing}
            </Mono>
            <Mono size={11} color={palette.faint}>
              {run.board_group_state
                ? `grup sinyali: ${run.board_group_state}`
                : "grup sinyali: yok"}
            </Mono>
          </div>
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            height: "100%",
            justifyContent: "center",
            gap: 18,
          }}
        >
          <Sans size={44} weight={650} color={palette.text}>
            KAPI GEÇMİŞİ YOK
          </Sans>
          <Mono size={16} color={palette.dim}>
            {gh.source} okunamadı — 16 kutu da “KAYIT YOK”, sahte yeşil yok
          </Mono>
        </div>
      )}
    </Shell>
  );
};
