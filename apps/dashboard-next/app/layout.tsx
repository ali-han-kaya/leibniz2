import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Geist } from "next/font/google";
import { brandMark, footerNote } from "@/components/panel-style";
import { cn } from "@/lib/utils";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: {
    default: "Stoic-Hume V5 — Doğrulama Panosu",
    template: "%s | Stoic-Hume V5",
  },
  description:
    "2307 test, K1–K19 doğrulama katmanı ve Lean/Z3 ispat kanallarının canlı özeti.",
};

// Kök layout yalnız kabuktur (başlık/nav/footer). Panellerin paralel rota
// slotları `app/(panel)/layout.tsx`'te yaşar — oraya kapsanmaları `/trend`'in
// onları görmemesini sağlar (gerekçe o dosyada).
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="tr"
      suppressHydrationWarning
      className={cn("font-sans", geist.variable)}
    >
      <body className="min-h-screen bg-bg text-fg antialiased">
        <header className="border-b border-border px-8 py-4">
          <div className="mx-auto flex max-w-4xl items-baseline gap-6">
            <span className={brandMark()}>STOIC-HUME V5</span>
            <nav className="ml-auto flex gap-6 font-mono text-xs tracking-[0.12em] text-muted">
              <Link className="transition-colors hover:text-fg" href="/">
                ÖZET
              </Link>
              <Link className="transition-colors hover:text-fg" href="/trend">
                TREND
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-4xl px-8 py-8">{children}</main>
        <footer
          className={cn(
            "border-t border-border px-8 py-6 text-center",
            footerNote()
          )}
        >
          HER KOŞUM, KENDİ DETERMİNİSTİK HASH&apos;İYLE İMZALANIR
        </footer>
      </body>
    </html>
  );
}
