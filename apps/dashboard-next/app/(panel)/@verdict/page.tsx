import { ViewTransition } from "react";

import VerdictCard from "@/app/VerdictCard";
import PanelAutoRefresh from "@/components/PanelAutoRefresh";
import { getLatest } from "@/lib/preview";

// `@verdict` paralel rota slotu — son koşumun verdict kartı.
//
// Bu dosya bir ZAMANLAR `/api/a11y` yanıtını JSON olarak basan bir yer
// tutucuydu: PanelCard kullanmıyor, `role="status"` bölgesi taşımıyor ve
// doğru veri kaynağına (`getLatest` → DB/preview) bağlı değildi. Kartın
// kendisi `app/VerdictCard.tsx`te yaşar; slot yalnız onu yerleştirir.
//
// `force-dynamic` gerekçesi: verdict her koşumda tazelenir; build anında
// dondurulursa pano bayat karar gösterir (bkz. app/trend/page.tsx).
export const dynamic = "force-dynamic";

// `baselineTs` slotta okunur: `getLatest` React `cache()` ile sarılı olduğu
// için `VerdictCard`in aynı isteği paylaşılır — ikinci upstream turu YOK.
// Amaç, sayfa açılışında SSE'nin ilk snapshot'ının SSR ile aynı damgayı
// taşıdığını bilmek: gereksiz bir tazeleme turu atılmaz.
export default async function VerdictSlot() {
  const latest = await getLatest();
  // Suspense reveal sözleşmesi @trend slotuyla AYNI (tek kural, iki slot):
  // sınıf adları globals.css'teki .slot-exit/.slot-enter pseudo-element
  // kurallarıyla eşleşir. Next her slotu ayrı Suspense sınırına alır.
  return (
    // Otomatik tazeleme: canlı koşum bittiğinde SSE yeni bir `ts` yayınlar,
    // bu sarmalayıcı `router.refresh()` ile sunucu bileşenlerini yeniden
    // çalıştırır → verdict kartı yenileme gerektirmeden döner. Görünür sekme
    // aralığı, SSE düşse ya da kaynak `db` olsa da kartı toparlar.
    <PanelAutoRefresh baselineTs={latest.ts ?? null}>
      <ViewTransition
        enter={{ "slot-enter": "slot-enter", default: "none" }}
        exit={{ "slot-exit": "slot-exit", default: "none" }}
        default="none"
      >
        <VerdictCard />
      </ViewTransition>
    </PanelAutoRefresh>
  );
}
