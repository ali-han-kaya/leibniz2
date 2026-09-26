// `@verdict` slotunun akış iskeleti. Kartın son yerleşimini (başlık satırı,
// büyük verdict, 4 istatistik) taklit eder ki veri gelince yükseklik
// zıplamasın. Renkler repo-token'ları; animasyon tw-animate-css'ten.
export default function VerdictLoading() {
  return (
    <section
      className="rounded-lg border border-border bg-surface p-6"
      aria-busy="true"
      aria-label="Son koşum yükleniyor"
    >
      <div className="flex items-baseline justify-between">
        <div className="h-3 w-24 animate-pulse rounded bg-border" />
        <div className="h-3 w-48 animate-pulse rounded bg-border" />
      </div>
      <div className="mt-5 h-12 w-44 animate-pulse rounded bg-border" />
      <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {["P0", "P1", "Z3", "STRIPPED"].map((label) => (
          <div key={label} className="bg-bg">
            <dt className="text-[10px] tracking-[0.14em] text-muted">
              {label}
            </dt>
            <dd className="mt-1">
              <div className="h-4 w-full animate-pulse rounded bg-border" />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
