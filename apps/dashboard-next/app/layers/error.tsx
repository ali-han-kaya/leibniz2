"use client";

import PanelError from "@/components/PanelError";

// `/layers` segment sınırı — katman fotoğrafı okunamazsa sayfa düşer ama
// uygulama kabuğu (header/nav) ayakta kalır.
export default function LayersError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PanelError
      title="Katman görünümü yüklenemedi"
      message={error.message}
      hint="kaynak: trend_runs.layers (Neon) veya preview_server /api/latest."
      onRetry={reset}
    />
  );
}
