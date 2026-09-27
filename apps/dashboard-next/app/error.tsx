"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { panelCard } from "@/components/panel-style";
import { cn } from "@/lib/utils";

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
    // Kabuk da diğer paneller gibi `Card`; hata yüzeyi repo-token'larıyla
    // (tint-err-bg + err kenarı) Card'ın varsayılan yüzeyini/halkanını ezer.
    <Card
      className={cn(panelCard(), "border border-err bg-tint-err-bg ring-0")}
    >
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
    </Card>
  );
}
