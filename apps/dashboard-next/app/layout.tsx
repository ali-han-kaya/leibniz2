import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { brandMark, footerNote, navLink } from "@/components/panel-style";
import { ThemeInit } from "@/components/ThemeInit";
import { cn } from "@/lib/utils";

// Tipografi TEK kaynaktan: design-system/tokens.css'teki `--font-sans`
// (kâtip sesi). Öncesinde `next/font/google`dan Geist yüklenip
// `--font-sans`a bağlanıyordu — köprü token'ını gölgeleyen ikinci bir
// font kaynağıydı ve `@theme`teki aile hiç devreye girmiyordu. Google
// Fonts ağ bağımlılığı da kalktı (build offline kalabilir).

export const metadata: Metadata = {
  title: {
    default: "Stoic-Hume V5 — Doğrulama Panosu",
    template: "%s | Stoic-Hume V5",
  },
  description:
    "2307 test, K0–K21 doğrulama katmanı ve Lean/Z3 ispat kanallarının canlı özeti.",
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
    <html lang="tr" suppressHydrationWarning className="font-sans">
      <body className="min-h-screen bg-bg text-fg antialiased">
        {/* `?theme=` / localStorage tercihini `data-theme`'e uygular; açık
            tema köprüsü (`:root[data-theme="light"]`) böylece devreye girer.
            Görsel çıktısı yoktur — yan etki yalnız documentElement'te. */}
        <ThemeInit />
        {/* VT uzamsal çapa: header geçiş boyunca SABİT kalır (gezinme
            haritası — kayan header yönsüz geçişte sahte hareket üretir).
            Ad, globals.css'teki ::view-transition-group(site-header)
            kuralıyla eşleşir; CSS satır-içi stili ezer (animation: none). */}
        <header
          className="border-b border-border px-(--panel-gutter) py-(--panel-block-gap)"
          style={{ viewTransitionName: "site-header" }}
        >
          <div className="mx-auto flex max-w-4xl items-baseline gap-(--panel-block-gap)">
            {/* Sayfa başlığı gerçek bir `<h1>` (bulgular: "no h1 on
                pages"): marka yalnız bir `<span>`di, yani her sayfa
                başlıksız kalıyordu ve bölüm `<h2>`leri hiyerarşide
                köksüzdü. Kök layout'ta durduğu için tüm rotaları kapsar.
                `translate="no"`: marka bir ürün adıdır, makine çevirisi
                onu bozmamalı. */}
            <h1 className={brandMark()} translate="no">
              STOIC-HUME V5
            </h1>
            {/* Nav bağlantıları `navLink`ten beslenir: hover rengi ve
                ODAK halkası buton tabanıyla aynı sözleşmeden gelir.
                Dizge ikisinde kopyalanmıştı ve odak işareti yoktu; kök
                layout'ta durduğu için her rota kapsanır. */}
            <nav className="ml-auto flex gap-(--panel-block-gap) font-mono text-xs tracking-chrome text-muted">
              <Link className={navLink()} href="/">
                ÖZET
              </Link>
              <Link className={navLink()} href="/trend">
                TREND
              </Link>
              <Link className={navLink()} href="/layers">
                KATMANLAR
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-4xl px-(--panel-gutter) py-(--panel-gutter)">
          {children}
        </main>
        <footer
          className={cn(
            "border-t border-border px-(--panel-gutter) py-(--panel-block-gap) text-center",
            footerNote()
          )}
        >
          HER KOŞUM, KENDİ DETERMİNİSTİK HASH&apos;İYLE İMZALANIR
        </footer>
      </body>
    </html>
  );
}
