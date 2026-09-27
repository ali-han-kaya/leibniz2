import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  countTone,
  microLabel,
  panelCard,
  panelLabel,
  statBadge,
  toneForVerdict,
  verdictTone,
  type VerdictTone,
} from "@/components/panel-style";
import { getLatest } from "@/lib/preview";

// patterns-explicit-variants: PASS/FAIL kararı ve P0/P1 rozet tonları
// cva-variant'ta (components/panel-style.ts) — bileşende ternary değil.
// Renkler repo-token'ları (tek-kaynak: design-system).
//
// Kabuk shadcn `Card` + `CardHeader`/`CardContent`: panel ölçüleri
// (yarıçap/dolgu) ve metin stilleri primitive'in üstüne tek yerde
// (`panelCard`/`panelLabel`) bağlanır. Başlık bilinçli olarak `CardTitle`
// DEĞİL: `CardTitle` bir `div` basar, pano ise gerçek `<h2>` ile bölüm
// hiyerarşisi kuruyor (a11y).
// Server Component — veri burada toplanır, istemciye JS gitmez.
export default async function VerdictCard() {
  const latest = await getLatest();
  const verdict = (latest.verdict ?? "").toUpperCase();
  // Sunucu düz alan yayınlıyor: z3_passed/z3_total (iç içe `z3` nesnesi yok).
  const z3 =
    latest.z3_total === undefined && latest.z3_passed === undefined
      ? "—"
      : `${latest.z3_passed ?? "—"}/${latest.z3_total ?? "—"}`;

  return (
    <Card className={panelCard()}>
      <CardHeader className="flex flex-row items-baseline justify-between">
        <h2 className={panelLabel()}>Son Koşum</h2>
        {latest.ts ? (
          <time className="font-mono text-xs text-muted">{latest.ts}</time>
        ) : null}
      </CardHeader>

      <CardContent>
        <p
          className={verdictTone({ tone: toneForVerdict(latest.verdict) })}
          aria-live="polite"
        >
          {verdict || "—"}
        </p>

        <dl className="mt-6 grid grid-cols-2 gap-4 font-mono text-sm sm:grid-cols-4">
          <Stat
            label="P0"
            value={latest.p0 ?? "—"}
            tone={countTone(latest.p0, "fail")}
          />
          <Stat
            label="P1"
            value={latest.p1 ?? "—"}
            tone={countTone(latest.p1, "warn")}
          />
          <Stat label="Z3" value={z3} />
          <Stat
            label="STRIPPED"
            value={latest.stripped_sha256?.slice(0, 12).toUpperCase() ?? "—"}
          />
        </dl>
      </CardContent>
    </Card>
  );
}

// `tone` verilmişse değer rozet olarak basılır (P0/P1: sıfır sessiz, sıfır
// dışı vurgulu); verilmemişse düz değer kalır (Z3/STRIPPED — kimlik/hash
// rozeti değil, metin). Ton seçimi bileşende değil varyant tablosunda.
function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: VerdictTone;
}) {
  return (
    <div className="bg-bg">
      <dt className={microLabel()}>{label}</dt>
      <dd className="mt-1 font-semibold text-fg">
        {tone ? <Badge className={statBadge({ tone })}>{value}</Badge> : value}
      </dd>
    </div>
  );
}
