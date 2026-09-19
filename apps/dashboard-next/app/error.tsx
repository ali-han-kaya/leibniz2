"use client";

import { Button } from "@/components/ui/button";

// Hata sınırı — istemci bileşeni olması zorunlu (App Router sözleşmesi).
// preview_server kapalıyken actioned mesaj: ne olduğu + nasıl düzeltilir.
// patterns-children-over-render-props: buton mevcut Button primitive'iyle
// kurulur (destructive variant repo-token'ina bond'lu) — raw className yok.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border border-err bg-tint-err-bg p-6">
      <h2 className="font-serif text-xl font-semibold text-err">
        Panoya ulaşılamadı
      </h2>
      <p className="mt-2 text-sm text-fg">{error.message}</p>
      <p className="mt-3 font-mono text-xs text-muted">
        Sunucuyu başlatın: python3 _calisma/CIKTI/preview_server.py
        --preview-dir _calisma/CIKTI --port 8000
      </p>
      <Button variant="destructive" className="mt-4" onClick={reset}>
        Tekrar dene
      </Button>
    </div>
  );
}
