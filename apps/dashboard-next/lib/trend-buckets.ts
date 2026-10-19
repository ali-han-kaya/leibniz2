// Trend grafiği kovaları — SAF toplama (DB/React/Next importu YOK).
//
// Kaynak tasarım: `docs/TREND_CHART_READ_PATH.md` §2, §5, §9 adım 1.
//
// Sözleşme:
//   * Kovalar **UTC** sınırında: gün → `YYYY-MM-DD`, saat → `YYYY-MM-DDTHH`.
//     Anahtar `Date` nesnesi DEĞİL, `toISOString()` dilimidir — tasarım §5'te
//     ölçülen hata: `DATE` değerini yerel saatle `toISOString().slice(0,10)`
//     yapmak UTC+2 istemcisinde kovayı bir gün geriye kaydırıyordu.
//   * **Boş kova atlanmaz**: koşusuz gün 0 değerleriyle üretilir. Düşürmek
//     grafiği sıkıştırır ve "kesintisiz koşum" izlenimi verir.
//   * Çıktı **eskiden-yeniye** (mevcut `history` sözleşmesiyle aynı).
//   * `truncated` = sorgu satır sınırına (`rowCap`) DAYANDI; kırpılmış pencere
//     tam gibi gösterilmez.
//   * Bilinmeyen/`null` verdict `runs`a girer ama ne `pass` ne `fail` sayılır —
//     "PASS değilse FAIL'dir" varsayımı kanıt görünümüne aykırı.

/** Kova çözünürlüğü: span ≤ 48 saat → saatlik, üstü günlük (tasarım §2). */
export type TrendBucketGranularity = "hour" | "day";

export type TrendBucket = {
  /** UTC kova anahtarı: gün ise `YYYY-MM-DD`, saat ise `YYYY-MM-DDTHH`. */
  bucket: string;
  runs: number;
  pass: number;
  fail: number;
  p0: number;
  p1: number;
  z3_total: number;
};

export type TrendSeries = {
  buckets: TrendBucket[];
  /** İstenen pencerenin ISO-8601 (UTC) başlangıcı. */
  from: string;
  /** İstenen pencerenin ISO-8601 (UTC) bitişi. */
  to: string;
  granularity: TrendBucketGranularity;
  truncated: boolean;
};

/** Sorgudan gelen dar satır: yalnız kovalamaya giren alanlar. */
export type TrendSeriesRow = {
  ts: Date | string;
  verdict: string | null;
  p0: number | null;
  p1: number | null;
  z3Total: number | null;
};

export type BucketSeriesOptions = {
  from: Date | string;
  to: Date | string;
  /** Sorgunun `take` sınırı; satır sayısı buna dayandıysa `truncated`. */
  rowCap?: number;
  /** Verilmezse span'dan türetilir (≤ 48 saat → `hour`). */
  granularity?: TrendBucketGranularity;
};

/** Tasarım §5: başlangıç satır sınırı. */
export const ROW_CAP = 5000;
/** Saatlik çözünürlüğün üst sınırı (tasarım §2). */
export const HOUR_GRANULARITY_MAX_HOURS = 48;

const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

function toDate(value: Date | string, label: string): Date {
  const date =
    value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new TypeError(`${label}: geçersiz tarih (${String(value)})`);
  }
  return date;
}

/** UTC kova anahtarı — gün: 10 karakter, saat: 13 karakter (tasarım §5). */
export function bucketKey(
  ts: Date | string,
  granularity: TrendBucketGranularity
): string {
  const iso = toDate(ts, "bucketKey").toISOString();
  return granularity === "hour" ? iso.slice(0, 13) : iso.slice(0, 10);
}

function bucketStart(ts: Date, granularity: TrendBucketGranularity): number {
  const date = new Date(ts.getTime());
  if (granularity === "hour") {
    date.setUTCMinutes(0, 0, 0);
    return date.getTime();
  }
  date.setUTCHours(0, 0, 0, 0);
  return date.getTime();
}

/**
 * Span'a göre çözünürlük: ≤ 48 saat saatlik, üstü günlük.
 * Açık `granularity` verilirse o kullanılır (tasarım §2 "parametre olsun").
 */
export function chooseGranularity(
  from: Date | string,
  to: Date | string,
  override?: TrendBucketGranularity
): TrendBucketGranularity {
  if (override) {
    return override;
  }
  const span = toDate(to, "to").getTime() - toDate(from, "from").getTime();
  return span <= HOUR_GRANULARITY_MAX_HOURS * HOUR_MS ? "hour" : "day";
}

function emptyBucket(key: string): TrendBucket {
  return { bucket: key, runs: 0, pass: 0, fail: 0, p0: 0, p1: 0, z3_total: 0 };
}

function addNumber(total: number, value: number | null): number {
  return typeof value === "number" && Number.isFinite(value)
    ? total + value
    : total;
}

/**
 * Satırları UTC kovalara toplar. Pencere dışındaki satırlar (ts < from ya da
 * ts > to) YOK SAYILIR — sorgu `gte: from` filtreler, üst sınırı burada
 * uygulanır ki seri ile istenen pencere birbirini tutsun.
 */
export function bucketSeries(
  rows: readonly TrendSeriesRow[],
  options: BucketSeriesOptions
): TrendSeries {
  const from = toDate(options.from, "from");
  const to = toDate(options.to, "to");
  if (to.getTime() < from.getTime()) {
    throw new RangeError("bucketSeries: `to` < `from`");
  }
  const rowCap = options.rowCap ?? ROW_CAP;
  const granularity = chooseGranularity(from, to, options.granularity);
  const step = granularity === "hour" ? HOUR_MS : DAY_MS;

  const buckets = new Map<string, TrendBucket>();
  const firstStart = bucketStart(from, granularity);
  const lastStart = bucketStart(to, granularity);
  for (let at = firstStart; at <= lastStart; at += step) {
    const key = bucketKey(new Date(at), granularity);
    buckets.set(key, emptyBucket(key));
  }

  const lower = from.getTime();
  const upper = to.getTime();
  for (const row of rows) {
    const ts = toDate(row.ts, "ts");
    const at = ts.getTime();
    if (at < lower || at > upper) {
      continue;
    }
    const key = bucketKey(ts, granularity);
    // Pencere sınırları kova sınırına hizalı değilse (ör. from 10:30) ilk/son
    // kova yine de üretilir: anahtar aralığın içindeki bucketStart'tan gelir.
    const bucket = buckets.get(key);
    if (!bucket) {
      continue;
    }
    bucket.runs += 1;
    if (row.verdict === "PASS") {
      bucket.pass += 1;
    } else if (row.verdict === "FAIL") {
      bucket.fail += 1;
    }
    bucket.p0 = addNumber(bucket.p0, row.p0);
    bucket.p1 = addNumber(bucket.p1, row.p1);
    bucket.z3_total = addNumber(bucket.z3_total, row.z3Total);
  }

  return {
    buckets: [...buckets.values()],
    from: from.toISOString(),
    to: to.toISOString(),
    granularity,
    truncated: rows.length >= rowCap,
  };
}
