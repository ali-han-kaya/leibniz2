"use client";

import { useEffect, useState } from "react";

import { cva } from "class-variance-authority";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
} from "@/components/PanelCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { tableHead } from "@/components/panel-style";
import { EMPTY_VALUE, formatTimestamp } from "@/lib/format";

// Koşum geçmişi tablosu — CANLI. Veri iki yerden gelir:
//
//   1. SSR  : `RunsTableData` (Server Component) `getTrend(limit)` ile ilk
//             pencereyi basar → ilk boya sunucuda, JS gelmeden dolu ekran.
//   2. CANLI: `/api/events` (bu uygulamanın route handler'ı) preview_server'ın
//             SSE akışını tünelliyor. Her olayda taze `trend` gelir.
//
// Neden doğrudan preview_server'a `EventSource` ile bağlanılmıyor: sunucu
// CORS başlığı GÖNDERMİYOR (ölçüldü: 0 `Access-Control-*`), pano başka
// origin'de — tarayıcı akışı açsa da okuyamaz. Tünel sunucu tarafında; aynı
// origin; preview_server'a dokunulmuyor. Ayrıntı: app/api/events/route.ts.
//
// MARKUP DEĞİŞMEDİ. Bu bileşen 'use client' olmadan ÖNCE de Server
// Component idi ve veriyi kendisi çekiyordu; veri çekme bir Server
// Component'e (`RunsTableData`) taşındı, İSKELET BURADA BİREBİR Aynı. Neden:
// `test_dashboard_next_ui_contract.py` bu dosyayı üç ayrı sözleşmeye bağlıyor
// (`formatTimestamp` tüketicisi, `<time dateTime>`, `tabular-nums`); markup
// taşınsaydı o üç tarama boş kalırdı. Sunucu/istemci ayrımı veri AKIŞINDA,
// işaretlemede değil — taranan sözleşme değişmez.
//
// Kabuk `PanelCard` bileşiminden gelir (kabuk + bölüm başlığı + içerik);
// tablo yapısı shadcn ailesinden kurulur: `Table`/`TableHeader`/`TableBody`/
// `TableRow`/`TableHead`/`TableCell`. Satır kenarı ve hücre dolgusu
// primitive'in varsayılanlarından gelir (`border-b` → --border, `p-2` +
// `px-4` → 6px/10px = preview.html'in `th, td` değerleri).
//
// patterns-explicit-variants: hucre-rengi kararlari (p0>0 kirmizi, p1>0 sari)
// cva-variant'ta — sira-bileseninde ternary-degil. Renkler repo-token'lari.
//
// `tabular-nums` taban sınıfta: gövdedeki HER hücre sayı ya da zaman
// damgasıdır (P0/P1 sayaç, süre, Z3 toplamı, biçimlenmiş zaman). Rakamlar
// aynı genişlikte olmazsa sütunlar satır satır titrer ve ölçü
// karşılaştırılamaz hale gelir. Tek yerde durduğu için yeni bir sayı sütunu
// sessizce tabular-nums'sız kalamaz (web-interface-guidelines: sayı
// sütunları tabular-nums kullanmalı).
const cellVariants = cva("px-4 tabular-nums", {
  variants: {
    tone: {
      neutral: "",
      error: "text-err",
      warn: "text-warn",
      muted: "text-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});

/** `lib/preview`'nin `TrendRow` sözleşmesinin istemci kopyası (yalnız okuma). */
type TrendRow = {
  ts?: string;
  p0?: number;
  p1?: number;
  duration_s?: number;
  budget_usd?: number;
  z3_total?: number;
};

/** `/api/events` akışının istemciye giden zarfı. */
type LiveEvent = Snapshot & { trend?: { history?: TrendRow[] } };
type Snapshot = Record<string, unknown>;

/** Sunucu ile aynı pencere/ters sıra sözleşmesi — sapma olursa görünür. */
function windowRows(history: TrendRow[], limit: number): TrendRow[] {
  return history.slice(-limit).reverse();
}

export default function RunsTable({
  title,
  rows,
  limit,
}: {
  title: string;
  rows: TrendRow[];
  limit: number;
}) {
  const [live, setLive] = useState<TrendRow[]>(rows);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  // SSR verisi sunucudan gelir; ilk canlı olaydan önce gösterilir. `rows`
  // kimliği değişirse (yeni render) tablo SSR'e döner — canlı akış kendi
  // durumunu korur, çünkü akış `limit` ile bir kez kurulur.
  useEffect(() => {
    setLive(rows);
  }, [rows]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    const source = new EventSource(`/api/events?limit=${limit}`);
    const onSnapshot = (event: Event) => {
      let payload: LiveEvent | null = null;
      try {
        payload = JSON.parse((event as MessageEvent).data) as LiveEvent;
      } catch {
        return; // bozuk çerçeve: ekranı bozmadan yoksay
      }
      const history = payload?.trend?.history;
      if (Array.isArray(history)) {
        setLive(windowRows(history, limit));
      }
      if (typeof payload?.verdict === "string") {
        setVerdict(payload.verdict.toUpperCase());
      }
      setConnected(true);
    };
    // `error` olayı hem ağ düşmesinde hem de normal yeniden bağlanmada
    // gelir; bağlantı durumu "kapalı" diye okunur, akış kendi kendine
    // yeniden dener (EventSource sözleşmesi).
    const onError = () => setConnected(false);

    source.addEventListener("snapshot", onSnapshot);
    source.addEventListener("error", onError);
    return () => {
      source.removeEventListener("snapshot", onSnapshot);
      source.removeEventListener("error", onError);
      source.close();
    };
  }, [limit]);

  return (
    <PanelCard>
      <PanelCardHeader>
        <PanelCardTitle>{title}</PanelCardTitle>
      </PanelCardHeader>
      <PanelCardContent>
        {/* Canlılık göstergesi `role="status"` (polite): ekran okuyucuya
            verdict değişimini duyurur. `aria-live` AYRICA yazılmaz —
            yinelemeli olurdu (verdict yüzeyindeki sözleşmenin aynısı). */}
        <p role="status" className="mb-2 font-mono text-xs text-muted">
          {connected
            ? `canlı${verdict ? ` · ${verdict}` : ""}`
            : "canlı bağlantı bekleniyor"}
        </p>
        {live.length === 0 ? (
          <p className="text-sm text-muted">
            henüz veri yok — ilk run bekleniyor
          </p>
        ) : (
          <Table className="font-mono text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className={tableHead}>ZAMAN</TableHead>
                <TableHead className={tableHead}>P0</TableHead>
                <TableHead className={tableHead}>P1</TableHead>
                <TableHead className={tableHead}>SÜRE</TableHead>
                <TableHead className={tableHead}>Z3</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {live.map((r, i) => (
                // Satır vurgusu `bg-surface-raised`: shadcn'ın `bg-muted/50`
                // gölgesi bu depoda yanlış çalışır — `--color-muted` pano
                // token'larında bir METİN rengi (globals.css notu).
                <TableRow key={i} className="hover:bg-surface-raised">
                  {/* Zaman hücresi: ham `ts` (ISO, makine sözleşmesi)
                      `dateTime` olarak korunur, görünen metin Intl ile
                      biçimlenir — elle dilimleme yerel ayarı ve 12/24
                      saat kuralını ıskalardı (bkz. lib/format.ts). */}
                  <TableCell className={cellVariants({ tone: "muted" })}>
                    {r.ts ? (
                      <time dateTime={r.ts}>{formatTimestamp(r.ts)}</time>
                    ) : (
                      EMPTY_VALUE
                    )}
                  </TableCell>
                  <TableCell
                    className={cellVariants({
                      tone: (r.p0 ?? 0) > 0 ? "error" : "neutral",
                    })}
                  >
                    {r.p0 ?? EMPTY_VALUE}
                  </TableCell>
                  <TableCell
                    className={cellVariants({
                      tone: (r.p1 ?? 0) > 0 ? "warn" : "neutral",
                    })}
                  >
                    {r.p1 ?? EMPTY_VALUE}
                  </TableCell>
                  <TableCell className={cellVariants()}>
                    {r.duration_s != null ? `${r.duration_s}s` : EMPTY_VALUE}
                  </TableCell>
                  <TableCell className={cellVariants()}>
                    {r.z3_total ?? EMPTY_VALUE}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </PanelCardContent>
    </PanelCard>
  );
}
