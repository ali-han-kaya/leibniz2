"use client";

import PanelError from "@/components/PanelError";

// `@trend` slotunun kendi hata sınırı — verdict paneli sağlam kalır.
//
// Veri kaynağı (DB veya preview_server) düştüğünde iki panel AYNI kaynağı
// kullansa bile her biri kendi kartında hata gösterir: ortak hata sınırı
// olsaydı tek bir source hatası tüm ana panoyu boşaltırdı.
export default function TrendPanelError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PanelError
      title="Koşum geçmişi yüklenemedi"
      message={error.message}
      hint="kaynak: trend_runs (Neon) veya preview_server; diğer paneller etkilenmez."
      onRetry={reset}
    />
  );
}
