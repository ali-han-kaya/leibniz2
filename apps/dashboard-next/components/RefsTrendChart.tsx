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
import { formatTimestamp } from "@/lib/format";
import { refsCoverage, type RefsPoint } from "@/lib/refs-trend";

// Refs trend grafiği — SAF sunucu render'ı (istemciye JS gitmez).
//
// Neden elde SVG: depoda grafik kütüphanesi yok ve preview.html'in kanonik
// grafiği de elle çizilmiş SVG'dir; ikinci bir çizim dili eklemek aynı veriyi
// iki farklı görsel sözleşmeyle anlatırdı. Renkler YALNIZ repo token'larıdır
// (`stroke-ok` → --ok, `stroke-accent` → --accent, `stroke-err` → --err);
// çağrı yerinde hex yok.
//
// Erişilebilirlik: SVG `role="img"` + `<title>`/`<desc>` taşır ve altında
// SON 5 koşumun tablosu basılır — grafiği okuyamayan kullanıcı için metin
// alternatifi aynı ekranda, ayrı bir sayfada değil.
//
// Sıra sözleşmesi: `points` eskiden-yeniye gelir (kaynak `/api/trend` gibi);
// grafik soldan sağa zaman akışını çizer, tablo EN YENİYİ üstte basar.

const W = 720;
const H = 220;
const PL = 44; // sol eksen (y etiketleri)
const PR = 16;
const PT = 12;
const PB = 30; // x etiketleri
const TABLE_WINDOW = 5;

function line(
  points: RefsPoint[],
  value: (point: RefsPoint) => number,
  x: (index: number) => number,
  y: (value: number) => number
): string {
  return points
    .map(
      (point, index) => `${x(index).toFixed(1)},${y(value(point)).toFixed(1)}`
    )
    .join(" ");
}

export default function RefsTrendChart({ points }: { points: RefsPoint[] }) {
  const coverage = refsCoverage(points);

  if (!coverage) {
    return (
      <PanelCard>
        <PanelCardHeader>
          <PanelCardTitle>Refs Trend</PanelCardTitle>
        </PanelCardHeader>
        <PanelCardContent>
          <p className="text-sm text-muted">
            çevrimiçi referans verisi yok — bu koşumlarda{" "}
            <code className="font-mono text-xs">--check-references</code> veri
            üretmedi
          </p>
        </PanelCardContent>
      </PanelCard>
    );
  }

  const n = points.length;
  const iw = W - PL - PR;
  const ih = H - PT - PB;
  const maxTotal = Math.max(1, ...points.map((point) => point.total));
  const x = (index: number) => PL + (n === 1 ? iw / 2 : (iw * index) / (n - 1));
  const y = (value: number) =>
    PT + ih - (ih * Math.min(Math.max(value, 0), maxTotal)) / maxTotal;
  const steps = Math.min(maxTotal, 4);
  const gridValues = Array.from({ length: steps + 1 }, (_, index) =>
    Math.round((maxTotal * index) / steps)
  );
  const labelIndexes = Array.from(new Set([0, Math.floor((n - 1) / 2), n - 1]));
  const recent = points.slice(-TABLE_WINDOW).reverse();
  const description = `Son ${n} koşumda çevrimiçi doğrulanan referans sayısı. Son koşum ${coverage.last.verified}/${coverage.last.total} (%${coverage.pct}).`;

  return (
    <PanelCard>
      <PanelCardHeader>
        <PanelCardTitle>Refs Trend</PanelCardTitle>
        <Badge className={statBadge({ tone: coverage.full ? "pass" : "warn" })}>
          {coverage.last.verified}/{coverage.last.total} · %{coverage.pct}
          {coverage.streak > 1 ? ` · ${coverage.streak} run` : ""}
        </Badge>
      </PanelCardHeader>
      <PanelCardContent className={cardStack()}>
        <p className={microLabel()}>
          {n} koşum · yeşil = doğrulanan · mavi (kesikli) = toplam · kırmızı =
          mismatch
        </p>

        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-labelledby="refs-trend-chart-title"
          aria-describedby="refs-trend-chart-desc"
          className="h-auto w-full"
        >
          <title id="refs-trend-chart-title">
            Çevrimiçi referans kapsamı trendi
          </title>
          <desc id="refs-trend-chart-desc">{description}</desc>

          {gridValues.map((value) => (
            <g key={value}>
              <line
                x1={PL}
                y1={y(value)}
                x2={PL + iw}
                y2={y(value)}
                className="stroke-border"
                strokeWidth={1}
              />
              <text
                x={PL - 6}
                y={y(value) + 4}
                className="fill-muted"
                fontSize={10}
                textAnchor="end"
              >
                {value}
              </text>
            </g>
          ))}

          {n > 1 ? (
            <polyline
              className="fill-none stroke-accent"
              strokeDasharray="4 3"
              strokeWidth={2}
              points={line(points, (point) => point.total, x, y)}
            />
          ) : null}
          {n > 1 ? (
            <polyline
              className="fill-none stroke-ok"
              strokeWidth={2.5}
              points={line(points, (point) => point.verified, x, y)}
            />
          ) : null}
          {points.some((point) => point.mismatch > 0) && n > 1 ? (
            <polyline
              className="fill-none stroke-err"
              strokeWidth={2}
              points={line(points, (point) => point.mismatch, x, y)}
            />
          ) : null}

          {points.map((point, index) => (
            <circle
              key={`${point.ts}-${index}`}
              cx={x(index)}
              cy={y(point.verified)}
              r={2.5}
              className={
                point.verified === point.total ? "fill-ok" : "fill-warn"
              }
            />
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

        <PanelTable>
          <caption className="sr-only">
            Son {recent.length} koşumun çevrimiçi referans kapsamı
          </caption>
          <TableHeader>
            <TableRow>
              <TableHead className={tableHead}>ZAMAN</TableHead>
              <TableHead className={tableHead}>DOĞRULANAN</TableHead>
              <TableHead className={tableHead}>KAPSAM</TableHead>
              <TableHead className={tableHead}>MISMATCH</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recent.map((point, index) => (
              <TableRow key={`${point.ts}-${index}`}>
                <TableCell className={tableCell({ tone: "muted" })}>
                  <time dateTime={point.ts}>{formatTimestamp(point.ts)}</time>
                </TableCell>
                <TableCell className={tableCell()}>
                  {point.verified}/{point.total}
                </TableCell>
                <TableCell className={tableCell()}>
                  %
                  {point.total > 0
                    ? Math.round((100 * point.verified) / point.total)
                    : 0}
                </TableCell>
                <TableCell
                  className={tableCell({
                    tone: point.mismatch > 0 ? "error" : "neutral",
                  })}
                >
                  {point.mismatch}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </PanelTable>
      </PanelCardContent>
    </PanelCard>
  );
}
