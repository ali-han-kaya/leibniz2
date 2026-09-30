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
