import { Badge } from "@/components/ui/badge";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
} from "@/components/PanelCard";
import {
  countTone,
  microLabel,
  statBadge,
  toneForVerdict,
  verdictTone,
  type VerdictTone,
} from "@/components/panel-style";
import { EMPTY_VALUE, formatTimestamp } from "@/lib/format";
import { getLatest } from "@/lib/preview";

// patterns-explicit-variants: PASS/FAIL kararı ve P0/P1 rozet tonları
// cva-variant'ta (components/panel-style.ts) — bileşende ternary değil.
// Renkler repo-token'ları (tek-kaynak: design-system).
//
// Kabuk `PanelCard` bileşimidir: hangi shadcn primitive'lerinin hangi sırayla
// kullanıldığı (ve panel ölçüleri) orada tek yerde durur; burada yalnız
// içerik yazılır. Başlık `<h2>` basar — `CardTitle` bir `div` olduğu için
// bölüm hiyerarşisini kuramazdı (a11y).
// Server Component — veri burada toplanır, istemciye JS gitmez.
export default async function VerdictCard() {
  const latest = await getLatest();
  const verdict = (latest.verdict ?? "").toUpperCase();
  // Sunucu düz alan yayınlıyor: z3_passed/z3_total (iç içe `z3` nesnesi yok).
  const z3 =
    latest.z3_total === undefined && latest.z3_passed === undefined
      ? EMPTY_VALUE
      : `${latest.z3_passed ?? EMPTY_VALUE}/${latest.z3_total ?? EMPTY_VALUE}`;

  return (
    <PanelCard>
      <PanelCardHeader>
        <PanelCardTitle>Son Koşum</PanelCardTitle>
        {/* Zaman damgası: `dateTime` makine-okunur ISO değeri KORUR, görünen
            metni Intl biçimler (lib/format.ts) — ham damgayı basmak hem
            okunmaz hem de "raw ts instead of Intl" bulgusudur.
            `tabular-nums` mono rakamları hizalar. */}
        {latest.ts ? (
          <time
            className="font-mono text-xs text-muted tabular-nums"
            dateTime={latest.ts}
          >
            {formatTimestamp(latest.ts)}
          </time>
        ) : null}
      </PanelCardHeader>

      <PanelCardContent>
        {/* `role="status"` — verdict bir DURUM mesajıdır
            (web-interface-guidelines). `role="status"` zaten
            `aria-live="polite"` demektir; ikisini birden yazmak yinelemeli
            olurdu — bu yüzden eski `aria-live` özniteliği rolle değişti. */}
        <p
          className={verdictTone({ tone: toneForVerdict(latest.verdict) })}
          role="status"
        >
          {verdict || EMPTY_VALUE}
        </p>

        <dl className="mt-6 grid grid-cols-2 gap-4 font-mono text-sm tabular-nums sm:grid-cols-4">
          <Stat
            label="P0"
            value={latest.p0 ?? EMPTY_VALUE}
            tone={countTone(latest.p0, "fail")}
          />
          <Stat
            label="P1"
            value={latest.p1 ?? EMPTY_VALUE}
            tone={countTone(latest.p1, "warn")}
          />
          <Stat label="Z3" value={z3} />
          <Stat
            label="STRIPPED"
            value={
              latest.stripped_sha256?.slice(0, 12).toUpperCase() ?? EMPTY_VALUE
            }
          />
        </dl>
      </PanelCardContent>
    </PanelCard>
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
