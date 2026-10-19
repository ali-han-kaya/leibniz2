"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { PanelCard, PanelCardContent } from "@/components/PanelCard";

// Panel hata yüzeyi — TEK görsel sözleşme.
//
// Neden ortak bileşen: her panelin kendi `error.tsx`i olsa da hata KARTI
// panel başına yeniden yazılırsa başlık/rol/buton dili ayrışır. Burada tek
// kez kurulur; sınır dosyaları yalnız başlık + ipucu metnini seçer.
//
// `role="alert"`: hata yüzeyinin tamamı (başlık, mesaj, kurtarma yolu) tek
// seferde duyurulmalı. Rol içeriği etkileşimsiz yapmaz — "Tekrar dene"
// butonu çalışmaya devam eder.
//
// `tone="error"` (panel-style): tint zemin + --err kenarı; halka kapalı.
// Renk kararı burada dizge olarak kurulmaz, varyanttan gelir.
//
// `message` ham `Error.message`dır: panonun kendi hata metnidir (fetch
// reddi, DB bağlantısı). Kullanıcıya Node yığını basılmaz; `digest` de
// gösterilmez — kullanıcı için eyleme dönük tek şey "Tekrar dene"dir.
//
// RETRY SÖZLEŞMESİ — neden `router.refresh()`:
// Hata, sunucu bileşeninin veri çekmesinde oluşuyor. `PanelBoundary.reset`
// yalnız kendi state'ini temizler; alt ağaç React cache'inden gelen ESKİ
// (hata vermiş) RSC ağacıdır, yeniden fetch etmez. `error.tsx`in `reset`i de
// segmenti yeniden render eder, upstream turunu garantilemez. Yani yalnız
// `reset` çağırmak "Tekrar dene"yi kozmetik yapardı: kaynak hâlâ düşükse
// aynı hatayı, kaynak düzeldiyse bile eski hatayı gösterirdi.
// `router.refresh()` sunucu bileşenlerini yeniden çalıştırır (yeni istek,
// taze fetch). İkisi birlikte gerekli: önce sınır state'i temizlenir (hata
// kartı kalksın), sonra RSC tazelenir (veri gelsin). Sayfa tam yeniden
// yüklenmez — sekme durumu, canlı SSE abonelikleri ve `ViewTransition`
// korunur.
export default function PanelError({
  title,
  message,
  hint,
  onRetry,
}: {
  title: string;
  message: string;
  hint?: string;
  /** Sınır state'ini temizler; yoksa yalnız RSC tazelenir. */
  onRetry?: () => void;
}) {
  const router = useRouter();

  const retry = () => {
    onRetry?.();
    router.refresh();
  };

  return (
    <PanelCard tone="error" role="alert">
      <PanelCardContent className="space-y-(--card-spacing)">
        <h2 className="font-verdict text-xl font-semibold text-err">{title}</h2>
        <p className="text-sm text-fg">{message}</p>
        {hint ? <p className="font-mono text-xs text-muted">{hint}</p> : null}
        <Button variant="destructive" onClick={retry}>
          Tekrar dene
        </Button>
      </PanelCardContent>
    </PanelCard>
  );
}
