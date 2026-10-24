"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

// Panel otomatik tazeleme — "canlı koşum sürerken kart kendini güncellesin".
//
// İKİ TETİKLEYİCİ, tek sözleşme:
//   1. SSE (`/api/events` — aynı tüneli koşum tablosu da kullanır): yeni bir
//      snapshot geldiğinde `ts` değişmişse RSC tazelenir. Koşum biter bitmez
//      verdict kartı yenileme gerektirmeden döner.
//   2. GÖRÜNÜR SEKME ARALIĞI (varsayılan 45 sn): SSE düşse, kaynak `db`
//      olsa (tünel preview_server'ı dinler, DB yazımını değil) ya da olay
//      bağlantı kurulmadan önce kaçırılsa bile kart kendini toparlar.
//      `document.hidden` iken HİÇ istek atılmaz — arka plandaki sekmeler
//      sunucuyu boşuna yormaz; sekme geri gelince aralık geçmişse hemen
//      tazelenir.
//
// Neden `router.refresh()` (yeniden yükleme değil): yalnız geçerli rotanın
// RSC ağacını yeniden çalıştırır. Sayfa yeniden yüklenmez → koşum tablosunun
// SSE aboneliği, `window.__liveMarker` benzeri istemci durumu ve geçiş
// animasyonları korunur (E2E bu ayrımı `performance.timeOrigin` ile ölçer).
//
// `baselineTs`: SSR'in bastığı en yeni koşum damgası. Verilirse ilk SSE
// snapshot'ı AYNI damgayı taşıdığında gereksiz tur atılmaz. Verilmezse
// ("bilinmiyor") ilk snapshot bir kez doğrulanır — eski veriyi taze sanmak
// yerine bir fazla render'ı seçiyoruz (fail-closed).
//
// Not: bu bileşen KENDİ hata yüzeyini kurmaz. Tazeleme başarısız olursa
// sunucu tarafı zaten panelin kendi sınırına (PanelBoundary / error.tsx)
// düşer; burada ikinci bir hata katmanı açmak hata kartını iki kez basardı.
const MIN_REFRESH_GAP_MS = 5_000;
export const AUTO_REFRESH_INTERVAL_MS = 45_000;

/** Yalnız ihtiyacımız olan alan: zarf `ts` taşır (diğer alanlar panellere). */
type LiveEnvelope = { ts?: unknown };

export default function PanelAutoRefresh({
  baselineTs = null,
  intervalMs = AUTO_REFRESH_INTERVAL_MS,
  children,
}: {
  baselineTs?: string | null;
  intervalMs?: number;
  children: ReactNode;
}) {
  const router = useRouter();
  // `ref` (state değil): tazeleme kararı render'a yansımaz, yeniden render
  // tetiklememeli. Aksi halde her snapshot yeni bir render + effect döngüsü
  // açardı.
  const lastTs = useRef<string | null>(baselineTs);
  const lastRefreshAt = useRef(0);

  const refresh = useRef(() => {
    const now = Date.now();
    // Fırtına koruması: bir snapshot, kendi RSC turunu tetiklediğinde yeni
    // bir `getLatest` okuması yapar; upstream aynı `ts`i birkaç kez
    // yayınlarsa (yeniden bağlanma, çoklu istemci) her olayda tur atmayalım.
    if (now - lastRefreshAt.current < MIN_REFRESH_GAP_MS) return;
    lastRefreshAt.current = now;
    router.refresh();
  });

  useEffect(() => {
    refresh.current = () => {
      const now = Date.now();
      if (now - lastRefreshAt.current < MIN_REFRESH_GAP_MS) return;
      lastRefreshAt.current = now;
      router.refresh();
    };
  }, [router]);

  // 1) SSE — koşum bittiği an verdict tazelenir.
  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    // `limit=1`: bu tüketici trend geçmişini kullanmaz (tablo kendi
    // penceresini ayrı bir tünelden alır); yalnız zarfın `ts`i gerekli.
    const source = new EventSource("/api/events?limit=1");
    const onSnapshot = (event: Event) => {
      let payload: LiveEnvelope | null = null;
      try {
        payload = JSON.parse((event as MessageEvent).data) as LiveEnvelope;
      } catch {
        return; // bozuk çerçeve: ekranı bozmadan yoksay
      }
      const ts = typeof payload?.ts === "string" ? payload.ts : "";
      if (!ts) return; // koşum kimliği yoksa tazelik iddiası da yok
      if (lastTs.current === ts) return;
      // Baseline bilinmiyorsa ilk snapshot tek doğrulama turudur; biliniyorsa
      // yalnız damga DEĞİŞTİĞİNDE tazelenir.
      lastTs.current = ts;
      refresh.current();
    };
    // `error` hem ağ düşmesi hem yeniden bağlanmadır; EventSource kendi
    // yeniden dener, burada kapatmıyoruz (tablo bileşenindeki aynı desen).
    source.addEventListener("snapshot", onSnapshot);
    return () => {
      source.removeEventListener("snapshot", onSnapshot);
      source.close();
    };
  }, []);

  // 2) Görünür sekme aralığı — SSE'ye bağımlı olmayan güvenlik ağı.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastRefreshAt.current < intervalMs) return;
      refresh.current();
    };
    const timer = window.setInterval(tick, intervalMs);
    // Sekme arka plandayken aralık kaçtıysa dönüşte telafi et.
    const onVisible = () => tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [intervalMs]);

  return <>{children}</>;
}
