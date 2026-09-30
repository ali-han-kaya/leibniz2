import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
} from "@/components/PanelCard";

// `@trend` slotunun akış iskeleti — tablo satırlarını taklit eder.
// `@verdict` iskeletinden AYRI bir sınır: iki panel birbirini beklemez.
// Kabuk RunsTable ile aynı bileşim (`PanelCard`); satır yerine iskelet
// çubuklar çizilir ama dolgu/kenar ölçüleri tabloyla uyuşur.
//
// Başlık metni yerine tek bir nabız çubuğu: satır yerleşimi
// `PanelCardHeader`tan gelir (bkz. @verdict/loading.tsx).
//
// `role="region"`: göç öncesi `<section aria-label>` idi; rolsuz div'de
// `aria-label` yok sayılır.
export default function TrendLoading() {
  return (
    <PanelCard
      role="region"
      aria-busy="true"
      aria-label="Koşum geçmişi yükleniyor"
    >
      <PanelCardHeader>
        <div className="h-3 w-32 animate-pulse rounded bg-border" />
      </PanelCardHeader>
      <PanelCardContent>
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-5 w-full animate-pulse rounded bg-bg" />
          ))}
        </div>
      </PanelCardContent>
    </PanelCard>
  );
}
