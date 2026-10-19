import RefsTrendChart from "@/components/RefsTrendChart";
import { getTrendBundle } from "@/lib/preview";
import { refsSeries } from "@/lib/refs-trend";

// `/trend` sayfasının refs grafiği paneli — veri çekmesi kendi içinde.
// Gerekçe `RunComparePanel` ile aynı: tek panelin kaynak hatası diğer iki
// paneli düşürmemeli. `getTrendBundle` cache'li olduğu için tablo/karşılaştırma
// ile AYNI yanıtı paylaşır (ikinci sorgu yok).
export default async function RefsTrendPanel({
  limit = 20,
}: {
  limit?: number;
}) {
  const { refs } = await getTrendBundle(limit);
  return <RefsTrendChart points={refsSeries(refs)} />;
}
