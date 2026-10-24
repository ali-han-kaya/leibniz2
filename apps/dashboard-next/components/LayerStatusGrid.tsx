import { Badge } from "@/components/ui/badge";
import {
  insetWell,
  microLabel,
  statBadge,
  toneForVerdict,
} from "@/components/panel-style";
import { cn } from "@/lib/utils";
import { layerCounts, type LayerState, type LayerView } from "@/lib/layers";

// Katman ızgarası — K0-K21 durumunun TEK görsel bileşimi.
//
// Durum→ton eşlemesi KAPALI bir tablodur (patterns-explicit-variants):
//   PASS → yeşil, FAIL → kırmızı, SKIP → nötr, UNKNOWN → nötr.
// UNKNOWN asla yeşile düşmez: tanınmayan bir durumu "yolunda" diye boyamak
// panoyu yanlış okutur (güvenlik yüzeyi kartındaki aynı kural).
const STATE_TONE: Record<LayerState, "pass" | "fail" | "none"> = {
  PASS: "pass",
  FAIL: "fail",
  SKIP: "none",
  UNKNOWN: "none",
};

export default function LayerStatusGrid({
  rows,
  verdict,
}: {
  rows: LayerView[];
  verdict?: string | null;
}) {
  const counts = layerCounts(rows);

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-(--panel-block-gap)">
        <p className={microLabel()}>
          {rows.length} katman · PASS {counts.PASS} · FAIL {counts.FAIL} · SKIP{" "}
          {counts.SKIP} · BİLİNMEYEN {counts.UNKNOWN}
        </p>
        {verdict ? (
          <Badge
            className={statBadge({ tone: toneForVerdict(verdict) })}
            translate="no"
          >
            {verdict.toUpperCase()}
          </Badge>
        ) : null}
      </div>

      <ul className="mt-(--panel-block-gap) grid gap-(--panel-block-gap) sm:grid-cols-2">
        {rows.map((row) => (
          <li key={row.key} className={cn(insetWell(), "border border-border")}>
            <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
              <span className="font-mono text-xs tracking-data text-muted">
                {row.key}
              </span>
              <Badge className={statBadge({ tone: STATE_TONE[row.state] })}>
                {row.state}
              </Badge>
            </div>
            <p className="mt-(--panel-tight-gap) text-sm text-fg">
              {row.label}
            </p>
            {row.state === "FAIL" && row.issues.length > 0 ? (
              <p className="mt-(--panel-tight-gap) break-words font-mono text-xs text-err">
                {row.findings} bulgu · {row.issues[0]}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
