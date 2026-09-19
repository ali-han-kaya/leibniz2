import { getLatest } from "@/lib/preview";

// Server Component — veri burada toplanır, istemciye JS gitmez.
export default async function VerdictCard() {
  const latest = await getLatest();
  const pass = (latest.verdict ?? "").toUpperCase() === "PASS";
  const z3 = latest.z3;

  return (
    <section className="rounded-lg border border-[#30363d] bg-[#161b22] p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-[#8b949e]">
          Son Koşum
        </h2>
        {latest.ts && (
          <time className="font-mono text-[11px] text-[#8b949e]">
            {latest.ts}
          </time>
        )}
      </div>

      <p
        className={`mt-3 font-serif text-5xl font-semibold ${
          pass ? "text-[#3fb950]" : "text-[#ff7b72]"
        }`}
        aria-live="polite"
      >
        {(latest.verdict ?? "—").toUpperCase()}
      </p>

      <dl className="mt-6 grid grid-cols-2 gap-4 font-mono text-sm sm:grid-cols-4">
        <Stat label="P0" value={latest.p0 ?? "—"} />
        <Stat label="P1" value={latest.p1 ?? "—"} />
        <Stat
          label="Z3"
          value={z3 ? `${z3.pass ?? "—"}/${z3.total ?? "—"}` : "—"}
        />
        <Stat
          label="STRIPPED"
          value={latest.stripped_sha256?.slice(0, 12).toUpperCase() ?? "—"}
        />
      </dl>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-[10px] tracking-[0.14em] text-[#8b949e]">{label}</dt>
      <dd className="mt-1 font-semibold">{value}</dd>
    </div>
  );
}
