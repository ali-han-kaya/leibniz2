import type { Metadata } from "next";
import "./globals.css";
import { Geist } from "next/font/google";
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
      <body className="min-h-screen bg-[#0e1116] text-[#e6edf3] antialiased">
        <header className="border-b border-[#30363d] px-8 py-4">
          <div className="mx-auto flex max-w-4xl items-baseline gap-6">
            <span className="font-mono text-[13px] font-semibold tracking-[0.14em]">
              STOIC-HUME V5
            </span>
            <nav className="ml-auto flex gap-6 font-mono text-xs tracking-[0.12em] text-[#8b949e]">
              <a className="transition-colors hover:text-[#e6edf3]" href="/">
                ÖZET
              </a>
              <a
                className="transition-colors hover:text-[#e6edf3]"
                href="/trend"
              >
                TREND
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-4xl px-8 py-8">{children}</main>
        <footer className="border-t border-[#30363d] px-8 py-6 text-center font-mono text-[11px] tracking-[0.12em] text-[#8b949e]">
          HER KOŞUM, KENDİ DETERMİNİSTİK HASH&apos;İYLE İMZALANIR
        </footer>
      </body>
    </html>
  );
}
