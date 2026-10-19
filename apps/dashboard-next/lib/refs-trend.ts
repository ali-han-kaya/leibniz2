// Refs trend serisi — SAF hesaplama (React/Next importu yok).
//
// Kaynak: `/api/trend` yanıtındaki `history` satırlarının refs alanları
// (`refs_verified`, `refs_total`, `refs_mismatch`). preview.html'in
// `renderRefsTrend` grafiği de AYNI alanları çizer — iki yüzey aynı sayıyı
// anlatır, ikinci bir doğruluk kaynağı yok.
//
// Satırlarda refs alanı YOKSA nokta üretilmez (0 uydurulmaz): DB kaynağı bu
// alanları taşımıyor ve `--check-references` verisi olmayan koşumlarda alan
// null geliyor. "0/0" çizmek "tam kapsam" gibi okunurdu.

import type { RefsRow } from "./preview";

/** Grafiğin gösterdiği pencere — /trend tablosuyla aynı (20). */
export const REFS_WINDOW = 20;

export type RefsPoint = {
  ts: string;
  verified: number;
  total: number;
  mismatch: number;
};

/**
 * Satırları eskiden-yeniye refs noktalarına çevirir, son `limit` tanesini alır.
 *
 * Sıra KORUNUR (kaynak sözleşmesi eskiden-yeniye); sıralama burada
 * yapılmaz — yeniden sıralamak iki tüketiciyi ayrıştırırdı.
 */
export function refsSeries(rows: RefsRow[], limit = REFS_WINDOW): RefsPoint[] {
  const points: RefsPoint[] = [];
  for (const row of rows) {
    if (typeof row.ts !== "string") continue;
    const verified = row.refs_verified;
    const total = row.refs_total;
    if (typeof verified !== "number" || typeof total !== "number") continue;
    points.push({
      ts: row.ts,
      verified,
      total,
      mismatch: typeof row.refs_mismatch === "number" ? row.refs_mismatch : 0,
    });
  }
  return points.slice(-Math.max(1, limit));
}

export type RefsCoverage = {
  last: RefsPoint;
  /** Yüzde (0-100); toplam 0 ise 0. */
  pct: number;
  /** Son koşumda verified === total (tam kapsam). */
  full: boolean;
  /** Sondan geriye kesintisiz tam-kapsam koşum sayısı. */
  streak: number;
};

/** Son noktanın kapsam özeti; seri boşsa null (sıfır uydurulmaz). */
export function refsCoverage(points: RefsPoint[]): RefsCoverage | null {
  if (!points.length) return null;
  const last = points[points.length - 1];
  let streak = 0;
  for (let i = points.length - 1; i >= 0; i -= 1) {
    if (points[i].verified !== points[i].total) break;
    streak += 1;
  }
  return {
    last,
    pct: last.total > 0 ? Math.round((100 * last.verified) / last.total) : 0,
    full: last.total > 0 && last.verified === last.total,
    streak,
  };
}
