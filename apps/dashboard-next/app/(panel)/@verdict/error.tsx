"use client";

import PanelError from "@/components/PanelError";

// `@verdict` slotunun kendi hata sınırı.
//
// Neden slotta: App Router'da `error.tsx` yalnız kendi segmentini sarar.
// Bu dosya olmadan slotun veri hatası `(panel)` → kök `error.tsx`e tırmanır
// ve KOMPAKT KOŞUM TABLOSUNU da düşürürdü; iki panel birbirinden bağımsız
// akarken (ayrı `loading.tsx` sınırları) hata yolu da bağımsız olmalı.
export default function VerdictError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PanelError
      title="Verdict paneli yüklenemedi"
      message={error.message}
      hint="a11y-gate ucu yanıt vermedi; koşum tablosu ve diğer paneller etkilenmez."
      onRetry={reset}
    />
  );
}
