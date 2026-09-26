import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
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

  return (
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
  );
}
