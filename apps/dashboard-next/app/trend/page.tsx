import { getTrend } from "@/lib/preview";

export const metadata = { title: "Trend" };

export default async function TrendPage() {
  const { history } = await getTrend(20);

  return (
    <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-6">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-[#8b949e]">
        Son 20 Koşum
      </h2>
      {history.length === 0 ? (
        <p className="mt-4 text-sm text-[#8b949e]">
          henüz veri yok — ilk run bekleniyor
        </p>
      ) : (
        <table className="mt-4 w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-[#30363d] text-left text-[10px] tracking-[0.14em] text-[#8b949e]">
              <th className="py-2">ZAMAN</th>
              <th className="py-2">P0</th>
              <th className="py-2">P1</th>
              <th className="py-2">SÜRE</th>
              <th className="py-2">Z3</th>
            </tr>
          </thead>
          <tbody>
            {history.map((r, i) => (
              <tr key={i} className="border-b border-[#21262d]">
                <td className="py-2 text-[#8b949e]">{r.ts ?? "—"}</td>
                <td
                  className={`py-2 ${(r.p0 ?? 0) > 0 ? "text-[#ff7b72]" : ""}`}
                >
                  {r.p0 ?? "—"}
                </td>
                <td
                  className={`py-2 ${(r.p1 ?? 0) > 0 ? "text-[#d29922]" : ""}`}
                >
                  {r.p1 ?? "—"}
                </td>
                <td className="py-2">
                  {r.duration_s != null ? `${r.duration_s}s` : "—"}
                </td>
                <td className="py-2">{r.z3_total ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
