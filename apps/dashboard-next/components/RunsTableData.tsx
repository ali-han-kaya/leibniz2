import RunsTable from "@/components/RunsTable";
import { getTrend } from "@/lib/preview";

// Koşum tablosunun SUNUCU YÜZÜ — veriyi çeker, canlı tabloya ilk pencereyi
// verir. Tablo gövdesi/başlığı `RunsTable`'ta (Client Component) yaşar; bu
// dosya yalnız "SSR ilk boya" işini yapar.
//
// Neden ikiye bölündü: `getTrend` React `cache()` + sunucu-yanı runtime env
// (`PREVIEW_API`, `NEXT_PUBLIC_` DEĞİL) kullanıyor — istemcide çalışmaz.
// Tablo ise canlı akış dinleyecek. Veri akışı sunucuda biter, gösterim
// istemcide yaşar; bu ayrım `RunsTable.tsx`'in MARKUP'ına dokunmadan yapıldı
// (bkz. o dosyadaki sözleşme notu).
//
// İki tüketici paylaşır:
//   app/(panel)/@trend/page.tsx → k��mpakt slot (limit 5)
//   app/trend/page.tsx          → tam sayfa (limit 20)
export default async function RunsTableData({
  title,
  limit,
}: {
  title: string;
  limit: number;
}) {
  const { history } = await getTrend(limit);
  // Sıra sözleşmesi: `history` eskiden-yeniye gelir; pencereyi tüketici kısar
  // ve en-yeni üstte göstermek için çevirir (DB ve HTTP kaynağı aynı sözleşme).
  // Canlı güncellemeler de AYNI dönüşümü uygular (RunsTable.windowRows), böylece
  // SSR ile canlı tablo aynı satır sırasını gösterir.
  const rows = history.slice(-limit).reverse();

  return <RunsTable title={title} rows={rows} limit={limit} />;
}
