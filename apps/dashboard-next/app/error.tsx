"use client";

import { Button } from "@/components/ui/button";

// Hata sınırı — istemci bileşeni olması zorunlu (App Router sözleşmesi).
// İki veri kaynağı olduğu için iki ayrı çözüm yolu gösterilir: panellerin
// hangisinden beslendiği `TREND_SOURCE` ile seçilir (lib/preview.ts). Yalnız
// preview_server'ı işaret etmek, DB kaynaklı bir hatada yanlış yönlendirirdi.
// patterns-children-over-render-props: buton mevcut Button primitive'iyle
// kurulur (destructive variant repo-token'ina bond'lu) — raw className yok.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border border-err bg-tint-err-bg p-6">
      <h2 className="font-serif text-xl font-semibold text-err">
        Panoya ulaşılamadı
      </h2>
      <p className="mt-2 text-sm text-fg">{error.message}</p>
      <p className="mt-3 font-mono text-xs text-muted">
        veri kaynağı: Neon Postgres → apps/trend-db/.env (neon env pull)
        <br />
        alternatif: python3 _calisma/CIKTI/preview_server.py --port 8000 (ve
        TREND_SOURCE=preview)
      </p>
      <Button variant="destructive" className="mt-4" onClick={reset}>
        Tekrar dene
      </Button>
    </div>
  );
}
