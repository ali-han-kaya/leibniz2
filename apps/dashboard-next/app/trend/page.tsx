import { cva, type VariantProps } from "class-variance-authority";
import { getTrend } from "@/lib/preview";

export const metadata = { title: "Trend" };

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

export default async function TrendPage() {
  const { history } = await getTrend(20);

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
        Son 20 Koşum
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
            {history.map((r, i) => (
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
