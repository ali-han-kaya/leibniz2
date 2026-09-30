"use client";

import { Button } from "@/components/ui/button";
import { PanelCard, PanelCardContent } from "@/components/PanelCard";

// Hata sınırı — istemci bileşeni olması zorunlu (App Router sözleşmesi).
// İki veri kaynağı olduğu için iki ayrı çözüm yolu gösterilir: panellerin
// hangisinden beslendiği `TREND_SOURCE` ile seçilir (lib/preview.ts). Yalnız
// preview_server'ı işaret etmek, DB kaynaklı bir hatada yanlış yönlendirirdi.
// patterns-children-over-render-props: buton mevcut Button primitive'iyle
// kurulur (destructive variant repo-token'ına bond'lu) — raw className yok.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    // Kabuk diğer panellerle AYNI bileşim: `PanelCard`. Hata yüzeyi artık
    // çağrı yerinde sınıf dizgesiyle kurulmuyor — `tone="error"` varyantı
    // (panel-style.ts: tint zemin + --err kenarı, halka kapalı).
    //
    // İçerik `PanelCardContent` içinde: `Card` yalnız dikey dolgu verir, yatay
    // dolgu header/content yuvalarından gelir. Bu kart daha önce `Card`ı
    // doğrudan kullandığı için metin kartın yatay kenarına değiyordu.
    //
    // Başlık bilinçli olarak `PanelCardHeader` DEĞİL: o yuva mono büyük-harfli
    // bölüm etiketi basar; hata başlığı gerçek bir başlıktır (serif + --err).
    //
    // `role="alert"`: hata YÜZEYİNİN tamamı duyurulmalı (bulgular: hata
    // yüzeyinde role=alert yok). Kart bir canlı bölge olduğu için başlık,
    // mesaj ve kurtarma yolu tek seferde okunur; `role=alert` içeriği
    // etkileşimsiz yapmaz, "Tekrar dene" butonu çalışmaya devam eder.
    <PanelCard tone="error" role="alert">
      <PanelCardContent className="space-y-(--card-spacing)">
        <h2 className="font-serif text-xl font-semibold text-err">
          Panoya ulaşılamadı
        </h2>
        <p className="text-sm text-fg">{error.message}</p>
        <p className="font-mono text-xs text-muted">
          veri kaynağı: Neon Postgres → apps/trend-db/.env (neon env pull)
          <br />
          alternatif: python3 _calisma/CIKTI/preview_server.py --port 8000 (ve
          TREND_SOURCE=preview)
        </p>
        <Button variant="destructive" onClick={reset}>
          Tekrar dene
        </Button>
      </PanelCardContent>
    </PanelCard>
  );
}
