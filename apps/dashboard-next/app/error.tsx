"use client";

// Hata sınırı — istemci bileşeni olması zorunlu (App Router sözleşmesi).
// preview_server kapalıyken actioned mesaj: ne olduğu + nasıl düzeltilir.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border border-[#ff7b72] bg-[#2a1416] p-6">
      <h2 className="font-serif text-xl font-semibold text-[#ff7b72]">
        Panoya ulaşılamadı
      </h2>
      <p className="mt-2 text-sm text-[#e6edf3]">{error.message}</p>
      <p className="mt-3 font-mono text-xs text-[#8b949e]">
        Sunucuyu başlatın: python3 _calisma/CIKTI/preview_server.py
        --preview-dir _calisma/CIKTI --port 8000
      </p>
      <button
        className="mt-4 rounded-md bg-[#58a6ff] px-4 py-2 text-sm font-semibold text-[#0e1116] hover:opacity-85"
        onClick={reset}
      >
        Tekrar dene
      </button>
    </div>
  );
}
