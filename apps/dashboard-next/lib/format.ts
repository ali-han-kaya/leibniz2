// Zaman damgası biçimlendirme — TEK kaynak.
//
// Neden `Intl`: ham `ts` (ör. `2026-09-21T11:42:06.778245+00:00`) makine
// sözleşmesidir, okunur değil. Panonun onu kullanıcıya gösterirken yerel
// biçime çevirmesi gerekir (web-interface-guidelines: `Intl.DateTimeFormat` —
// elle dilimleme hem yerel ayarı hem 12/24 saat kuralını ıskalar).
//
// NEDEN SABİT locale + timeZone: bu repo determinizm üzerine kurulu
// (deterministik hash'ler, tekrarlanabilir koşumlar). `Intl` varsayılanları
// ÇALIŞMA ORTAMINA göre değişir — sunucu (Node) ile tarayıcı, hatta
// `next build` ile `next start` ayrı sonuç verebilir; o zaman aynı veri iki
// farklı metne dönüşür ve "aynı girdi → aynı çıktı" sözleşmesi kırılır.
// `tr-TR` panonun dilidir, `UTC` verinin kendi dilimidir (`ts` daima +00:00).
export const TIMESTAMP_LOCALE = "tr-TR";
export const TIMESTAMP_TIME_ZONE = "UTC";

/** Veri yokken gösterilen yer tutucu (pano genelinde aynı işaret). */
export const EMPTY_VALUE = "—";

const timestampFormatter = new Intl.DateTimeFormat(TIMESTAMP_LOCALE, {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: TIMESTAMP_TIME_ZONE,
});

// Bütçe USD'dir (koşumun kendi para birimi), locale panonun dilidir — aynı
// sabit locale kuralı burada da geçerli (deterministik çıktı). `narrowSymbol`
// "US$" yerine "$" basar; sabit 2 hane tablo sütunlarını hizalar.
const usdFormatter = new Intl.NumberFormat(TIMESTAMP_LOCALE, {
  style: "currency",
  currency: "USD",
  currencyDisplay: "narrowSymbol",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * ISO damgasını okunur kısa biçime çevirir; veri yoksa/bozuksa `EMPTY_VALUE`.
 *
 * Bozuk değer sessizce "—"e düşer (uydurma bir tarih basmaz): kaynak kısmi
 * JSON dönebilir ve `Invalid Date` kullanıcıya gösterilmemelidir.
 */
export function formatTimestamp(ts: string | undefined | null): string {
  if (!ts) return EMPTY_VALUE;
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return EMPTY_VALUE;
  return timestampFormatter.format(parsed);
}

/** USD tutarını okunur biçime çevirir; alan yoksa/bozuksa `EMPTY_VALUE`. */
export function formatUsd(value: number | undefined | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return EMPTY_VALUE;
  return usdFormatter.format(value);
}

// Ondalıklı sayı biçimi — tablo/rozet metinleri de panonun diliyle aynı
// ayırıcıyı kullanır (\"-2.5\" değil \"-2,5\"). Sabit locale/UTC kuralı
// burada da geçerli: aynı girdi sunucu ve tarayıcıda aynı metni verir.
const decimalCache = new Map<number, Intl.NumberFormat>();

function decimalFormatter(digits: number): Intl.NumberFormat {
  const cached = decimalCache.get(digits);
  if (cached) return cached;
  const formatter = new Intl.NumberFormat(TIMESTAMP_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  decimalCache.set(digits, formatter);
  return formatter;
}

/** Sabit ondalıklı sayı; yoksa/bozuksa `EMPTY_VALUE`. */
export function formatDecimal(
  value: number | undefined | null,
  digits = 1
): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return decimalFormatter(digits).format(value);
}

/** Saniyeyi tam sayı olarak basar (karşılaştırma paneli); yoksa `EMPTY_VALUE`. */
export function formatDuration(seconds: number | undefined | null): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) {
    return EMPTY_VALUE;
  }
  return `${Math.round(seconds)} s`;
}
