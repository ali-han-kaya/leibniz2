// Kök akış iskeleti — Suspense fallback'i (panel slotlarının kendi
// `loading.tsx`leri ayrı sınırlardır; bkz. app/(panel)/layout.tsx).
//
// `role="status"`: iskelet bir yükleme DURUMU bildirir, adlandırılmış bir
// bölge değil. Bulgular: bu div rol'süzdü, yani `aria-label` yok sayılıyordu
// (axe `aria-prohibited-attr` — generic role etiket taşıyamaz). Panel
// iskeletleri `role="region"` kullanır çünkü orada adlandırılmış bölüm
// aranır; burada doğru eşleme durum rolüdür. `aria-busy="true"` yükleme
// sürerken duyuruyu erteler.
//
// Nabız animasyonu (`animate-pulse`) `prefers-reduced-motion` bloğunda
// global olarak sıfırlanır (app/globals.css) — her çağrı yerine
// `motion-reduce:` eklemek yerine tek kural, yeni animasyonlar da kapsanır.
export default function Loading() {
  return (
    <div
      className="h-44 animate-pulse rounded-lg border border-border bg-surface"
      role="status"
      aria-busy="true"
      aria-label="Yükleniyor"
    />
  );
}
