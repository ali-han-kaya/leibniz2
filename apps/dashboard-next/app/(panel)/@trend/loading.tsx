import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { panelCard } from "@/components/panel-style";

// `@trend` slotunun akış iskeleti — tablo satırlarını taklit eder.
// `@verdict` iskeletinden AYRI bir sınır: iki panel birbirini beklemez.
// Kabuk RunsTable ile aynı primitive (Card); satır yerine iskelet çubuklar
// çizilir ama dolgu/kenar ölçüleri tabloyla uyuşur.
//
// `role="region"`: göç öncesi `<section aria-label>` idi; rolsuz div'de
// `aria-label` yok sayılır (bkz. @verdict/loading.tsx).
export default function TrendLoading() {
  return (
    <Card
      className={panelCard()}
      role="region"
      aria-busy="true"
      aria-label="Koşum geçmişi yükleniyor"
    >
      <CardHeader>
        <div className="h-3 w-32 animate-pulse rounded bg-border" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-5 w-full animate-pulse rounded bg-bg" />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
