import { cva, type VariantProps } from "class-variance-authority";
import { getLatest } from "@/lib/preview";

// patterns-explicit-variants: PASS/FAIL karari cva-variant'ta — bilesende
// boolean-ternary degil. Renkler repo-token'lari (tek-kaynak: design-system).
const verdictVariants = cva("mt-3 font-serif text-5xl font-semibold", {
  variants: {
    verdict: {
      pass: "text-ok",
      fail: "text-err",
      none: "text-muted",
    },
  },
  defaultVariants: { verdict: "none" },
});

// Server Component — veri burada toplanır, istemciye JS gitmez.
export default async function VerdictCard() {
  const latest = await getLatest();
  const verdict = (latest.verdict ?? "").toUpperCase();
  const z3 = latest.z3;

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
          Son Koşum
        </h2>
        {latest.ts ? (
          <time className="font-mono text-[11px] text-muted">{latest.ts}</time>
        ) : null}
      </div>

      <p
        className={verdictVariants({
          verdict:
            verdict === "PASS" ? "pass" : verdict === "" ? "none" : "fail",
        })}
        aria-live="polite"
      >
        {verdict || "—"}
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
    <div className="bg-bg">
      <dt className="text-[10px] tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-1 font-semibold text-fg">{value}</dd>
    </div>
  );
}
