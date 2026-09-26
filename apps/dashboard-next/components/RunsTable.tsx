import { cva } from "class-variance-authority";
import { getTrend } from "@/lib/preview";

// Koşum geçmişi tablosu — iki tüketici paylaşır:
//   app/@trend/page.tsx  → ana panonun kompakt slotu (küçük pencere)
//   app/trend/page.tsx   → tam sayfa görünümü (20 satır)
// İkisi de aynı sözleşmeyi okur; markup tek yerde kalır ki pencere/başlık
// dışındaki her şey sürüklenemesin.
//
// patterns-explicit-variants: hucre-rengi kararlari (p0>0 kirmizi, p1>0 sari)
// cva-variant'ta — sira-bileseninde ternary-degil. Renkler repo-token'lari.
const cellVariants = cva("py-2", {
  variants: {
    tone: {
      neutral: "",
      error: "text-err",
      warn: "text-warn",
      muted: "text-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});

// Server Component — veri burada toplanır (VerdictCard ile aynı örüntü).
export default async function RunsTable({
  title,
  limit,
}: {
  title: string;
  limit: number;
}) {
  const { history } = await getTrend(limit);
  // Sıra sözleşmesi: `history` eskiden-yeniye gelir; pencereyi tüketici kısar
  // ve en-yeni üstte göstermek için çevirir (DB ve HTTP kaynağı aynı sözleşme).
  const rows = history.slice(-limit).reverse();

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
        {title}
      </h2>
      {history.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          henüz veri yok — ilk run bekleniyor
        </p>
      ) : (
        <table className="mt-4 w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[10px] tracking-[0.14em] text-muted">
              <th className="py-2">ZAMAN</th>
              <th className="py-2">P0</th>
              <th className="py-2">P1</th>
              <th className="py-2">SÜRE</th>
              <th className="py-2">Z3</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-surface-raised">
                <td className="py-2 text-muted">{r.ts ?? "—"}</td>
                <td
                  className={cellVariants({
                    tone: (r.p0 ?? 0) > 0 ? "error" : "neutral",
                  })}
                >
                  {r.p0 ?? "—"}
                </td>
                <td
                  className={cellVariants({
                    tone: (r.p1 ?? 0) > 0 ? "warn" : "neutral",
                  })}
                >
                  {r.p1 ?? "—"}
                </td>
                <td className={cellVariants()}>
                  {r.duration_s != null ? `${r.duration_s}s` : "—"}
                </td>
                <td className={cellVariants()}>{r.z3_total ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
