// Koşumlar arası karşılaştırma — SAF hesaplama (React/Next/DB importu YOK).
//
// Kaynak: `/trend` sayfasının zaten çektiği `CompareRow` penceresi
// (DB yolunda `getTrendFromDb`, preview yolunda `/api/trend` satırları — aynı
// tel sözleşmesi). Bu modül yalnız ÖLÇER: eksik alan `null` kalır, sıfır
// uydurulmaz; böylece grafikte boşluk ile "$0" aynı şey sayılmaz.
//
// Sıra sözleşmesi: satırlar eskiden-yeniye gelir (preview_server `/api/trend`
// ve `getTrendFromDb` aynı sırayı verir). `runCompare` sıralamayı DEĞİŞTİRMEZ;
// "son koşum" daima dizinin son elemanıdır.

import type { CompareRow } from "./preview";

/** Grafiğin gösterdiği pencere — /trend tablosuyla aynı (20). */
export const COMPARE_WINDOW = 20;

export type ComparePoint = {
  ts: string;
  /** Saniye; alan yoksa null (0 değil — "ölçülmedi" ile "0 sn" farklı). */
  duration: number | null;
  /** USD; alan yoksa null. */
  budget: number | null;
  /** Etkin bütçe limiti (USD); yoksa null. */
  limit: number | null;
  verdict: string | null;
  p0: number;
  p1: number;
  z3: number | null;
};

export type DeltaDirection = "up" | "down" | "flat" | "unknown";

export type Delta = {
  absolute: number | null;
  /** Yüzde değişim; taban 0/eksikse null (bölme uydurulmaz). */
  pct: number | null;
  direction: DeltaDirection;
};

export type CompareSummary = {
  /** Eskiden-yeniye, `limit` ile kırpılmış pencere. */
  points: ComparePoint[];
  latest: ComparePoint | null;
  previous: ComparePoint | null;
  medianDuration: number | null;
  medianBudget: number | null;
  /** Son koşum − önceki koşum. */
  duration: Delta;
  budget: Delta;
  /** Son koşum − pencere medyanı. */
  durationVsMedian: Delta;
  budgetVsMedian: Delta;
  /** Son koşumun bütçe kullanımı (0-100); limit yoksa null. */
  budgetUtilization: number | null;
  /** Görünür gerileme var mı (süre/bütçe artışı, P0/P1 artışı, PASS→FAIL). */
  regressed: boolean;
  reasons: string[];
};

const UNKNOWN_DELTA: Delta = {
  absolute: null,
  pct: null,
  direction: "unknown",
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toPoint(row: CompareRow): ComparePoint | null {
  if (typeof row.ts !== "string" || !row.ts) return null;
  return {
    ts: row.ts,
    duration: asNumber(row.duration_s),
    budget: asNumber(row.budget_usd),
    limit: asNumber(row.budget_limit),
    verdict: typeof row.verdict === "string" ? row.verdict : null,
    p0: asNumber(row.p0) ?? 0,
    p1: asNumber(row.p1) ?? 0,
    z3: asNumber(row.z3_total),
  };
}

/** Medyan (çift sayıda iki ortalamanın ortası); boş kümede null. */
export function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** `current − base`; iki değerden biri yoksa "unknown" (0 varsayılmaz). */
export function delta(current: number | null, base: number | null): Delta {
  if (current === null || base === null) return UNKNOWN_DELTA;
  // Kayan nokta artığı ekranda "0.19999999999999996" olarak görünmesin:
  // fark 2 haneye yuvarlanır (bütçe sent, süre 0,01 s hassasiyeti).
  const absolute = Math.round((current - base) * 100) / 100;
  const pct = base === 0 ? null : (100 * absolute) / base;
  const direction: DeltaDirection =
    absolute === 0 ? "flat" : absolute > 0 ? "up" : "down";
  return {
    absolute,
    pct: pct === null ? null : Math.round(pct * 10) / 10,
    direction,
  };
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * Pencereyi özetler. Eksik alanlar deltayı `unknown` yapar; medyan yalnız
 * ÖLÇÜLMÜŞ değerlerden hesaplanır (null'lar medyanı kaydırmaz).
 */
export function runCompare(
  rows: CompareRow[],
  limit = COMPARE_WINDOW
): CompareSummary {
  const points = rows
    .map(toPoint)
    .filter((point): point is ComparePoint => point !== null)
    .slice(-Math.max(1, limit));

  const latest = points.length ? points[points.length - 1] : null;
  const previous = points.length > 1 ? points[points.length - 2] : null;
  const durations = points
    .map((point) => point.duration)
    .filter((value): value is number => value !== null);
  const budgets = points
    .map((point) => point.budget)
    .filter((value): value is number => value !== null);
  const medianDuration = median(durations);
  const medianBudget = median(budgets);

  const duration = delta(latest?.duration ?? null, previous?.duration ?? null);
  const budget = delta(latest?.budget ?? null, previous?.budget ?? null);
  const durationVsMedian = delta(latest?.duration ?? null, medianDuration);
  const budgetVsMedian = delta(latest?.budget ?? null, medianBudget);
  const budgetUtilization =
    latest?.budget != null && latest.limit != null && latest.limit > 0
      ? round1((100 * latest.budget) / latest.limit)
      : null;

  const reasons: string[] = [];
  if (
    duration.direction === "up" &&
    duration.pct !== null &&
    duration.pct > 10
  ) {
    reasons.push(`süre %${round1(duration.pct)} arttı`);
  }
  if (budget.direction === "up" && budget.pct !== null && budget.pct > 10) {
    reasons.push(`bütçe %${round1(budget.pct)} arttı`);
  }
  if (latest && previous && latest.p0 > previous.p0) {
    reasons.push(`P0 ${previous.p0} → ${latest.p0}`);
  }
  if (latest && previous && latest.p1 > previous.p1) {
    reasons.push(`P1 ${previous.p1} → ${latest.p1}`);
  }
  const latestVerdict = (latest?.verdict ?? "").toUpperCase();
  const previousVerdict = (previous?.verdict ?? "").toUpperCase();
  if (previous && previousVerdict === "PASS" && latestVerdict === "FAIL") {
    reasons.push("karar PASS → FAIL");
  }

  return {
    points,
    latest,
    previous,
    medianDuration,
    medianBudget,
    duration,
    budget,
    durationVsMedian,
    budgetVsMedian,
    budgetUtilization,
    regressed: reasons.length > 0,
    reasons,
  };
}
