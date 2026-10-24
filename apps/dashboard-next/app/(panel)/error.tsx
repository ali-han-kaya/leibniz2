"use client";

import PanelError from "@/components/PanelError";

// `(panel)` grubunun sınırı — LAYOUT düzeyi hatalar için.
//
// Slotların kendi `error.tsx`leri vardır; bu dosya yalnız panel layout'u
// çöktüğünde devreye girer (o durumda iki slot da render edilemez).
export default function PanelGroupError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PanelError
      title="Panel grubu yüklenemedi"
      message={error.message}
      hint="panel düzeni kurulamadı; header ve diğer rotalar çalışmaya devam eder."
      onRetry={reset}
    />
  );
}
