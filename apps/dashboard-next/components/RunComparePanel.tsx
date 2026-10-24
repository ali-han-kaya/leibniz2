import RunCompareCard from "@/components/RunCompareCard";
import { getTrendBundle } from "@/lib/preview";

// `/trend` sayfasının karşılaştırma paneli — VERİ ÇEKMESİ BURADA.
//
// Neden sayfada değil: sayfa `await` ettiği anda hata tüm rotayı düşürür ve
// tek bir `PanelBoundary` bile kurtaramaz (hata, sınırlar kurulmadan önce
// oluşur). Veri çekmeyi her panelin kendi server component'ine taşımak,
// paneli kendi hata sınırının ALTINA sokar.
//
// `getTrendBundle` React `cache()` ile sarılı: üç panel de aynı `limit` ile
// çağırsa bile istek başına TEK upstream turu olur (DB'de tek `findMany`).
export default async function RunComparePanel({
  limit = 20,
}: {
  limit?: number;
}) {
  const { compare } = await getTrendBundle(limit);
  return <RunCompareCard rows={compare} />;
}
