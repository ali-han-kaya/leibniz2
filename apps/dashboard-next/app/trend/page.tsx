import { ViewTransition } from "react";

import PanelAutoRefresh from "@/components/PanelAutoRefresh";
import PanelBoundary from "@/components/PanelBoundary";
import RefsTrendPanel from "@/components/RefsTrendPanel";
import RunComparePanel from "@/components/RunComparePanel";
import { panelStack } from "@/components/panel-style";
import RunsTableData from "@/components/RunsTableData";

export const metadata = { title: "Trend" };

// Trend penceresi her koşumda büyür; build anında dondurulamaz (app/page.tsx
// ile aynı gerekçe — DB kaynağında `no-store` fetch sinyali yok).
export const dynamic = "force-dynamic";

// Pencere sözleşmesi: 20 koşum. Sayfa artık veri ÇEKMEZ — her panel kendi
// verisini kendi server component'inde çeker (`RunComparePanel`,
// `RefsTrendPanel`, `RunsTableData`). Neden: sayfa gövdesinde `await` olsaydı
// kaynak hatası PanelBoundary'ler kurulmadan oluşur ve üç panoyu birden
// düşürürdü. `getTrendBundle` cache'li olduğu için üç çağrı tek yanıtı
// paylaşır; pencere kırpması JSX'te literal (20) durur.

// <ViewTransition> YALIN sarmalayıcı (default crossfade): / <-> /trend
// yanal geçişi TARAFSIZDIR — transitionTypes (slide yönü) KULLANILMAZ.
export default function TrendPage() {
  // Her sunucu turunda değişen anahtar: kaynak düştüğünde hata kartında
  // kalan sınır, TAZE veri geldiğinde kendini toparlar (yapışkan hata
  // yok). Aynı turdaki üç sınır aynı anahtarı paylaşır.
  const renderKey = Date.now();
  return (
    <ViewTransition>
      {/* Tek tazeleyici üç paneli de kapsar: SSE yeni koşum yayınladığında
          ya da görünür sekme aralığı dolduğunda rota RSC'si tazelenir.
          Sayfa yeniden yüklenmez — tablo kendi SSE aboneliğini ve satır
          penceresini korur (E2E: `performance.timeOrigin` sabit kalır). */}
      <PanelAutoRefresh>
        <div className={panelStack()}>
          <PanelBoundary
            resetKey={renderKey}
            title="Koşum tablosu yüklenemedi"
            hint="kaynak: trend_runs (Neon) veya preview_server; diğer paneller etkilenmez."
          >
            <RunsTableData title="Son 20 Koşum" limit={20} />
          </PanelBoundary>
          <PanelBoundary
            resetKey={renderKey}
            title="Koşum karşılaştırması yüklenemedi"
            hint="süre/bütçe penceresi okunamadı; tablo ve refs grafiği etkilenmez."
          >
            <RunComparePanel limit={20} />
          </PanelBoundary>
          <PanelBoundary
            resetKey={renderKey}
            title="Refs grafiği yüklenemedi"
            hint="referans serisi okunamadı; tablo ve karşılaştırma etkilenmez."
          >
            <RefsTrendPanel limit={20} />
          </PanelBoundary>
        </div>
      </PanelAutoRefresh>
    </ViewTransition>
  );
}
