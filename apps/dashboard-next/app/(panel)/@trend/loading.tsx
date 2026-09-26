// `@trend` slotunun akış iskeleti — tablo satırlarını taklit eder.
// `@verdict` iskeletinden AYRI bir sınır: iki panel birbirini beklemez.
export default function TrendLoading() {
  return (
    <section
      className="rounded-lg border border-border bg-surface p-6"
      aria-busy="true"
      aria-label="Koşum geçmişi yükleniyor"
    >
      <div className="h-3 w-32 animate-pulse rounded bg-border" />
      <div className="mt-4 space-y-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-5 w-full animate-pulse rounded bg-bg" />
        ))}
      </div>
    </section>
  );
}
