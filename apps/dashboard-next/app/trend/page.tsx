import RunsTable from "@/components/RunsTable";

export const metadata = { title: "Trend" };

// Trend penceresi her koşumda büyür; build anında dondurulamaz (app/page.tsx
// ile aynı gerekçe — DB kaynağında `no-store` fetch sinyali yok).
export const dynamic = "force-dynamic";

// Tam sayfa görünümü. Tablo markup'ı `@trend` slotuyla paylaşılır
// (components/RunsTable.tsx) — burada yalnız pencere ve başlık farklı.
export default function TrendPage() {
  return <RunsTable title="Son 20 Koşum" limit={20} />;
}
