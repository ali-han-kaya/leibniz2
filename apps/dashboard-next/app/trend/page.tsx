import { ViewTransition } from "react";

import RunsTableData from "@/components/RunsTableData";

export const metadata = { title: "Trend" };

// Trend penceresi her koşumda büyür; build anında dondurulamaz (app/page.tsx
// ile aynı gerekçe — DB kaynağında `no-store` fetch sinyali yok).
export const dynamic = "force-dynamic";

// Tam sayfa görünümü. Tablo markup'ı `@trend` slotuyla paylaşılır
// (components/RunsTable.tsx) — burada yalnız pencere ve başlık farklı.
// `RunsTableData` sunucuda ilk pencereyi basar, tablo canlıdır
// (`/api/events` ← preview_server SSE tüneli).
//
// <ViewTransition> YALIN sarmalayıcı (default crossfade): / <-> /trend
// yanal geçişi TARAFSIZDIR — transitionTypes (slide yönü) KULLANILMAZ
// (gezinme haritası: iki eşit panel arası sahte mekânsal derinlik yasak).
// Sarmalayıcı page.tsx'tedir, layout'ta DEĞİL: layout'lar navigasyonlar
// arasında kalıcıdır, enter/exit orada hiç ateşlenmez (guide sözleşmesi).
export default function TrendPage() {
  return (
    <ViewTransition>
      <RunsTableData title="Son 20 Koşum" limit={20} />
    </ViewTransition>
  );
}
