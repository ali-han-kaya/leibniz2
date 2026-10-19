import * as React from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  panelCard,
  panelLabel,
  panelTableBleed,
  type PanelTone,
} from "@/components/panel-style";
import { Table } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Panel kabuğu — panodaki kartların TEK bileşimi (shadcn `Card` ailesinin
// repo kabuğu). Dört yuva, dört isim; her parçanın TEK işi var:
//
//   PanelCard         kabuk; yüzey tonu `default | error`
//   PanelCardHeader   başlık SATIRI (tek satır, uçlara yaslı)
//   PanelCardTitle    bölüm etiketi — gerçek `<h2>`
//   PanelCardContent  içerik; yatay dolgunun geldiği tek yer
//
// Neden var: `panelCard()` + başlık dizgesi + `CardHeader`/`CardContent` BEŞ
// ayrı dosyada elle kuruluyordu (VerdictCard, RunsTable, hata sınırı ve iki
// akış iskeleti) ve biri değiştiğinde diğerleri sessizce geride kalıyordu —
// `panel-style.ts`'in kuruluş gerekçesinin bileşen tarafındaki karşılığı.
// Somut bedeli vardı: hata sınırı `Card`ı doğrudan kullandığı için
// `CardHeader`/`CardContent`in yatay dolgusunu atlıyordu ve içerik kartın
// yan kenarına değiyordu (ölçüldü: kabuğun `padding-left/right` değeri
// 0px — `Card` yalnız `py` verir, `px` yuvalardan gelir).
//
// `title`/`meta` gibi prop'lar bilinçli olarak YOK: başlık satırı bir
// YERLEŞİM yuvası, içeriği çağrı yerinde yazılır (children). İskeletler o
// yuvaya metin yerine nabız çubuklarını koyar; `title` prop'u olsaydı aynı
// yuva iki farklı yolla doldurulurdu (children-over-render-props'un
// kardeşi kural: tek yol).
//
// Desen de shadcn ailesinin aynısıdır (`Card`/`CardHeader`/`CardTitle`/
// `CardContent`), yalnız iki sapmayla: (1) yüzey tonu repo token'larına
// bağlı bir varyanttır (patterns-explicit-variants), (2) `PanelCardTitle`
// bir `div` değil gerçek `<h2>` basar — pano bölüm hiyerarşisini başlık
// etiketiyle kurar (a11y).

/** Kabuk. `tone` yüzeyi seçer (bkz. `panel-style.ts` → `panelCard`). */
export function PanelCard({
  tone = "default",
  className,
  ...props
}: React.ComponentProps<typeof Card> & { tone?: PanelTone }) {
  return <Card className={cn(panelCard({ tone }), className)} {...props} />;
}

/**
 * Başlık satırı: tek satır, uçlara yaslı. İçerik çağrı yerinden gelir
 * (normalde bir `PanelCardTitle`, gerekiyorsa yanında bir meta düğümü).
 * Satır yerleşimi yalnız burada tanımlıdır — çağrı yerleri flex dizgesini
 * tekrar yazmaz.
 */
export function PanelCardHeader({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <CardHeader
      className={cn(
        "flex flex-row items-baseline justify-between gap-x-(--panel-block-gap)",
        className
      )}
      {...props}
    />
  );
}

/**
 * Bölüm etiketi. Gerçek bir `<h2>` basar (shadcn `CardTitle` bir `div`'dir;
 * pano bölüm hiyerarşisini başlık etiketiyle kurar — a11y), böylece başlık
 * düzeyi çağrı yerine göre kaymaz ve stil tek kaynaktan (`panelLabel`) gelir.
 */
export function PanelCardTitle({
  className,
  ...props
}: React.ComponentProps<"h2">) {
  return <h2 className={cn(panelLabel(), className)} {...props} />;
}

/**
 * İçerik yuvası. Yatay dolgu (`px-(--card-spacing)`) yalnız buradan gelir:
 * kabuğun içine doğrudan çocuk koymak içeriği kart kenarına yapıştırır.
 */
export function PanelCardContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return <CardContent className={className} {...props} />;
}

/**
 * Kart içi veri tablosu — pano tablolarının TEK kabı.
 *
 * Neden `Table` doğrudan kullanılmıyor: hücre metni kart başlığıyla
 * hizalanmıyordu (kart dolgusu 14px + hücre dolgusu 10px = 24px). Burada
 * tablo kartın yatay dolgusunun dışına taşar (`panelTableBleed`) ve hücre
 * dolgusu `--panel-table-cell` (6px 14px) olur; böylece ilk sütun 14px'te,
 * yani başlıkla aynı hizada başlar, satır çizgileri de kart kenarına kadar
 * uzanır. `className` dış div'e gider (örn. `mt-(--panel-block-gap)`),
 * çünkü margin taşmanın kendisinde olmalı.
 */
export function PanelTable({
  className,
  ...props
}: React.ComponentProps<typeof Table>) {
  return (
    <div className={cn(panelTableBleed(), className)}>
      <Table className="font-mono" {...props} />
    </div>
  );
}
