import { Badge } from "@/components/ui/badge";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
  PanelTable,
} from "@/components/PanelCard";
import {
  cardStack,
  insetWell,
  microLabel,
  statBadge,
  tableCell,
  tableHead,
} from "@/components/panel-style";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EMPTY_VALUE,
  formatDecimal,
  formatDuration,
  formatTimestamp,
  formatUsd,
} from "@/lib/format";
import type { CompareRow } from "@/lib/preview";
import {
  runCompare,
  type ComparePoint,
  type CompareSummary,
  type Delta,
} from "@/lib/run-compare";

// Koşumlar arası karşılaştırma + süre/bütçe grafiği — SAF sunucu render'ı.
//
// Neden elde SVG: depoda grafik kütüphanesi yok; `RefsTrendChart` ile aynı
// çizim dili (token sınıfları, `role="img"`, altında metin tablosu). İkinci
// bir grafik kütüphanesi aynı veriyi iki farklı görsel sözleşmeyle anlatırdı.
//
// İKİ EKSEN bilinçli: süre (saniye) ve bütçe (USD) farklı büyüklükler; tek
// eksene sıkıştırmak birini düz çizgiye indirirdi. Sol eksen süre, sağ eksen
// bütçe; renk eşlemesi lejantta yazılı (yalnız renge yaslanılmaz).
//
// Veri POSTGRES'ten gelir: sayfa `getTrendBundle(20)` çağırır, DB yolunda
// `getTrendFromDb` tek `findMany` satırından `compare` yarımını da üretir
// (`apps/dashboard-next/lib/trend-db.ts`). Preview kaynağında aynı alanlar
// `/api/trend` satırlarında zaten var — ikinci istek yok.
const W = 720;
const H = 240;
const PL = 48; // sol eksen (süre)
const PR = 56; // sağ eksen (bütçe)
const PT = 14;
const PB = 32; // x etiketleri
const TABLE_WINDOW = 5;

function segments(
  points: ComparePoint[],
  value: (point: ComparePoint) => number | null,
  x: (index: number) => number,
  y: (value: number) => number
): string[] {
  const out: string[] = [];
  let current: string[] = [];
  points.forEach((point, index) => {
    const raw = value(point);
    if (raw === null) {
      if (current.length) out.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${x(index).toFixed(1)},${y(raw).toFixed(1)}`);
  });
  if (current.length) out.push(current.join(" "));
  return out;
}

function formatDelta(value: Delta, unit: "s" | "usd"): string {
  if (value.absolute === null) return EMPTY_VALUE;
  const sign = value.absolute > 0 ? "+" : value.absolute < 0 ? "-" : "±";
  const amount =
    unit === "s"
      ? `${formatDecimal(Math.abs(value.absolute), 1)} s`
      : formatUsd(Math.abs(value.absolute));
  const pct = value.pct === null ? "" : ` · %${formatDecimal(value.pct, 1)}`;
  return `${sign}${amount}${pct}`;
}

function toneForDelta(value: Delta): "pass" | "warn" | "none" {
  // Süre/bütçe için AŞAĞI iyidir; yukarı hareket uyarı tonudur. Bilinmeyen
  // (eksik alan) nötr kalır — yeşile düşmez.
  if (value.direction === "down") return "pass";
  if (value.direction === "up") return "warn";
  return "none";
}

function ComparisonColumn({
  title,
  point,
}: {
  title: string;
  point: ComparePoint | null;
}) {
  return (
    <div className={insetWell()}>
      <p className={microLabel()}>{title}</p>
      <dl className="mt-(--panel-tight-gap) space-y-(--panel-tight-gap) font-mono text-sm tabular-nums text-fg">
        <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
          <dt className="text-muted">süre</dt>
          <dd>{formatDuration(point?.duration ?? null)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
          <dt className="text-muted">bütçe</dt>
          <dd>{formatUsd(point?.budget ?? null)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
          <dt className="text-muted">limit</dt>
          <dd>{formatUsd(point?.limit ?? null)}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function RunCompareCard({ rows }: { rows: CompareRow[] }) {
  const summary: CompareSummary = runCompare(rows);
  const { points, latest, previous } = summary;
  const measured = points.filter(
    (point) => point.duration !== null || point.budget !== null
  );

  if (!latest || !measured.length) {
    return (
      <PanelCard>
        <PanelCardHeader>
          <PanelCardTitle>Koşum Karşılaştırması</PanelCardTitle>
        </PanelCardHeader>
        <PanelCardContent>
          <p className="text-sm text-muted">
            süre/bütçe verisi yok — bu koşumlarda alanlar boş
          </p>
        </PanelCardContent>
      </PanelCard>
    );
  }

  const n = points.length;
  const iw = W - PL - PR;
  const ih = H - PT - PB;
  const durationValues = measured
    .map((point) => point.duration)
    .filter((value): value is number => value !== null);
  const budgetValues = measured.flatMap((point) =>
    [point.budget, point.limit].filter(
      (value): value is number => value !== null
    )
  );
  const maxDuration = Math.max(1, ...durationValues);
  const maxBudget = Math.max(1, ...budgetValues);
  const x = (index: number) => PL + (n === 1 ? iw / 2 : (iw * index) / (n - 1));
  const yDuration = (value: number) =>
    PT + ih - (ih * Math.min(Math.max(value, 0), maxDuration)) / maxDuration;
  const yBudget = (value: number) =>
    PT + ih - (ih * Math.min(Math.max(value, 0), maxBudget)) / maxBudget;
  const gridValues = Array.from({ length: 5 }, (_, index) => index / 4);
  const labelIndexes = Array.from(new Set([0, Math.floor((n - 1) / 2), n - 1]));
  const recent = points.slice(-TABLE_WINDOW).reverse();
  const description =
    `Son ${n} koşumun süresi ve bütçesi. Son koşum ` +
    `${formatDuration(latest.duration)}, bütçe ${formatUsd(latest.budget)}` +
    (previous
      ? `; önceki koşuma göre süre ${formatDelta(summary.duration, "s")}, ` +
        `bütçe ${formatDelta(summary.budget, "usd")}.`
      : ".");

  return (
    <PanelCard>
      <PanelCardHeader>
        <PanelCardTitle>Koşum Karşılaştırması</PanelCardTitle>
        <div className="flex flex-wrap items-center gap-(--panel-tight-gap)">
          <Badge
            className={statBadge({ tone: toneForDelta(summary.duration) })}
          >
            süre {formatDelta(summary.duration, "s")}
          </Badge>
          <Badge className={statBadge({ tone: toneForDelta(summary.budget) })}>
            bütçe {formatDelta(summary.budget, "usd")}
          </Badge>
        </div>
      </PanelCardHeader>

      <PanelCardContent className={cardStack()}>
        <p className={microLabel()}>
          {n} koşum · {summary.regressed ? "gerileme var" : "gerileme yok"} ·
          sol eksen süre (s), sağ eksen bütçe (USD)
        </p>

        {summary.regressed ? (
          <p role="status" className="text-sm text-warn">
            {summary.reasons.join(" · ")}
          </p>
        ) : null}

        <div className="grid grid-cols-1 gap-(--panel-block-gap) sm:grid-cols-3">
          <ComparisonColumn title="Son koşum" point={latest} />
          <ComparisonColumn title="Önceki koşum" point={previous} />
          <div className={insetWell()}>
            <p className={microLabel()}>
              pencere medyanı ({measured.length} ölçüm)
            </p>
            <dl className="mt-(--panel-tight-gap) space-y-(--panel-tight-gap) font-mono text-sm tabular-nums text-fg">
              <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
                <dt className="text-muted">süre</dt>
                <dd>
                  {formatDuration(summary.medianDuration)}{" "}
                  <span className="text-muted">
                    ({formatDelta(summary.durationVsMedian, "s")})
                  </span>
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
                <dt className="text-muted">bütçe</dt>
                <dd>
                  {formatUsd(summary.medianBudget)}{" "}
                  <span className="text-muted">
                    ({formatDelta(summary.budgetVsMedian, "usd")})
                  </span>
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-(--panel-tight-gap)">
                <dt className="text-muted">limit kullanımı</dt>
                <dd>
                  {summary.budgetUtilization === null
                    ? EMPTY_VALUE
                    : `%${formatDecimal(summary.budgetUtilization, 1)}`}
                </dd>
              </div>
            </dl>
          </div>
        </div>

        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-labelledby="run-compare-chart-title"
          aria-describedby="run-compare-chart-desc"
          className="h-auto w-full"
        >
          <title id="run-compare-chart-title">
            Koşum süresi ve bütçe trendi
          </title>
          <desc id="run-compare-chart-desc">{description}</desc>

          {gridValues.map((ratio) => {
            const y = PT + ih - ih * ratio;
            return (
              <g key={ratio}>
                <line
                  x1={PL}
                  y1={y}
                  x2={PL + iw}
                  y2={y}
                  className="stroke-border"
                  strokeWidth={1}
                />
                <text
                  x={PL - 6}
                  y={y + 4}
                  className="fill-accent"
                  fontSize={10}
                  textAnchor="end"
                >
                  {Math.round(maxDuration * ratio)}
                </text>
                <text
                  x={PL + iw + 6}
                  y={y + 4}
                  className="fill-ok"
                  fontSize={10}
                  textAnchor="start"
                >
                  {/* Eksen de aynı tr-TR para biçimini kullanır; "$7.5"
                      ile "$7,50" aynı sayfada iki dil olurdu. */}
                  {formatUsd(maxBudget * ratio)}
                </text>
              </g>
            );
          })}

          {points.some((point) => point.limit !== null)
            ? segments(points, (point) => point.limit, x, yBudget).map(
                (segment, index) => (
                  <polyline
                    key={`limit-${index}`}
                    className="fill-none stroke-err"
                    strokeDasharray="4 3"
                    strokeWidth={1.5}
                    points={segment}
                  />
                )
              )
            : null}

          {segments(points, (point) => point.budget, x, yBudget).map(
            (segment, index) => (
              <polyline
                key={`budget-${index}`}
                className="fill-none stroke-ok"
                strokeWidth={2.5}
                points={segment}
              />
            )
          )}

          {segments(points, (point) => point.duration, x, yDuration).map(
            (segment, index) => (
              <polyline
                key={`duration-${index}`}
                className="fill-none stroke-accent"
                strokeWidth={2.5}
                points={segment}
              />
            )
          )}

          {points.map((point, index) => (
            <g key={`${point.ts}-${index}`}>
              {point.duration !== null ? (
                <circle
                  cx={x(index)}
                  cy={yDuration(point.duration)}
                  r={2.5}
                  className="fill-accent"
                />
              ) : null}
              {point.budget !== null ? (
                <circle
                  cx={x(index)}
                  cy={yBudget(point.budget)}
                  r={2.5}
                  className="fill-ok"
                />
              ) : null}
            </g>
          ))}

          {labelIndexes.map((index, position) => (
            <text
              key={index}
              x={Math.min(Math.max(x(index), PL), W - PR)}
              y={H - 12}
              className="fill-muted"
              fontSize={10}
              textAnchor={
                position === 0
                  ? "start"
                  : position === labelIndexes.length - 1
                    ? "end"
                    : "middle"
              }
            >
              {formatTimestamp(points[index].ts)}
            </text>
          ))}
        </svg>

        <p className={microLabel()}>
          lejant: mavi = süre (sol eksen) · yeşil = bütçe (sağ eksen) · kırmızı
          kesikli = bütçe limiti
        </p>

        <PanelTable>
          <caption className="sr-only">
            Son {recent.length} koşumun süre, bütçe ve bütçe limiti kullanımı
          </caption>
          <TableHeader>
            <TableRow>
              <TableHead className={tableHead}>ZAMAN</TableHead>
              <TableHead className={tableHead}>SÜRE</TableHead>
              <TableHead className={tableHead}>BÜTÇE</TableHead>
              <TableHead className={tableHead}>LİMİT</TableHead>
              <TableHead className={tableHead}>SONUÇ</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recent.map((point, index) => {
              const usage =
                point.budget !== null && point.limit !== null && point.limit > 0
                  ? `%${Math.round((100 * point.budget) / point.limit)}`
                  : EMPTY_VALUE;
              return (
                <TableRow
                  key={`${point.ts}-${index}`}
                  className="hover:bg-surface-raised"
                >
                  <TableCell className={tableCell({ tone: "muted" })}>
                    <time dateTime={point.ts}>{formatTimestamp(point.ts)}</time>
                  </TableCell>
                  <TableCell className={tableCell()}>
                    {formatDuration(point.duration)}
                  </TableCell>
                  <TableCell className={tableCell()}>
                    {formatUsd(point.budget)}
                  </TableCell>
                  <TableCell className={tableCell()}>
                    {usage}
                    <span className="ml-(--panel-tight-gap) text-muted">
                      {formatUsd(point.limit)}
                    </span>
                  </TableCell>
                  <TableCell className={tableCell()}>
                    {(point.verdict ?? EMPTY_VALUE).toUpperCase()}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </PanelTable>
      </PanelCardContent>
    </PanelCard>
  );
}
