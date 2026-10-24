import { ViewTransition } from "react";
import Link from "next/link";
import PanelBoundary from "@/components/PanelBoundary";
import SecuritySurfaceCard from "@/components/SecuritySurfaceCard";
import { buttonVariants } from "@/components/ui/button";
import { panelStack } from "@/components/panel-style";
import { API_BASE, trendSource } from "@/lib/preview";
import { cn } from "@/lib/utils";

// Bu dosya `/` rotasının `children` slotudur: sayfaya ÖZEL içerik.
// Paneller (verdict kartı + koşum tablosu) artık `app/@verdict` ve
// `app/@trend` paralel rotalarında yaşar; her birinin kendi `loading.tsx`'i
// olduğu için bağımsız akarlar. Burada Suspense/verdict kodu kalmadı —
// aksi halde iki yerde iki farklı akış sınırı olurdu.
export const dynamic = "force-dynamic";

export default function HomePage() {
  const source = trendSource();
  // Tazeleme turunda güvenlik kartı da hata durumundan çıkabilsin
  // (`PanelBoundary` resetKey sözleşmesi).
  const renderKey = Date.now();

  return (
    <ViewTransition>
      <div className={panelStack()}>
        <p className="text-sm text-muted">
          Trend görünümü:{" "}
          <Link
            className={cn(buttonVariants({ variant: "ghost" }), "text-accent")}
            href="/trend"
          >
            /trend
          </Link>{" "}
          · Canlı pano:{" "}
          <a
            className={cn(buttonVariants({ variant: "ghost" }), "text-accent")}
            href={`${API_BASE}/preview.html`}
          >
            preview.html
          </a>{" "}
          {/* Veri kaynağını panoda görünür kıl: aynı ekran DB'den de
          preview_server'dan da beslenebiliyor, karıştırılmasın. */}
          <span className="font-mono text-xs">
            · kaynak: <span className="text-fg">{source}</span>
          </span>
        </p>
        {/* Güvenlik yüzeyi kartı sayfaya özel içerikte (children slotu)
            durur: paneller (`@verdict`/`@trend`) canlı koşum verisidir, bu
            kart ise koşumdan bağımsız — kendi ucu `/api/health`.
            `<ViewTransition>` TEK sarmalayıcı olarak kalır (sözleşme: sayfa
            başına bir tane; `default` özniteliği yasak). */}
        {/* Güvenlik kartı kendi sınırında: `/api/health` yanıtı bozulsa da
            paneller (verdict + trend) ve bağlantı satırı ayakta kalır. */}
        <PanelBoundary
          resetKey={renderKey}
          title="Güvenlik yüzeyi yüklenemedi"
          hint="/api/health okunamadı; paneller etkilenmez."
        >
          <SecuritySurfaceCard />
        </PanelBoundary>
      </div>
    </ViewTransition>
  );
}
