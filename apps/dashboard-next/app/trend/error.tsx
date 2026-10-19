"use client";

import PanelError from "@/components/PanelError";

// `/trend` sayfasının segment sınırı — sayfa düzeyi çöküşler için SON ağ.
//
// Normalde her bölüm kendi `PanelBoundary`siyle sarılıdır (tablo,
// karşılaştırma, refs). Bu dosya, sınırların KENDİSİ kurulamadan önce oluşan
// hataları (ör. sayfa iskeleti) yakalar; slot sınırları gibi panel bazında
// izolasyon sağlamaz, o yüzden birincil çözüm değildir.
export default function TrendError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PanelError
      title="Trend sayfası yüklenemedi"
      message={error.message}
      hint="veri kaynağı: trend_runs (Neon) veya preview_server; TREND_SOURCE ile seçilir."
      onRetry={reset}
    />
  );
}
