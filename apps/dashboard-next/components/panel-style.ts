import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Pano yüzeyinin paylaşılan stil token'ları.
//
// Neden ayrı modül: Tailwind'in arbitrary değerleri (`text-[11px]`,
// `tracking-[0.22em]`) çağrı yerinde yazılınca her seferinde yeniden
// üretilir; üç ayrı dosyada aynı `font-mono text-[11px] uppercase
// tracking-[0.22em] text-muted` dizisi vardı ve biri değişince diğer ikisi
// sessizce geride kalıyordu. Burada HER arbitrary değer tek yerde, adıyla ve
// gerekçesiyle tanımlıdır; çağrı yerleri isim kullanır.
//
// Ölçü notu: punto tarafında arbitrary değer KALMADI. Repo token'ları
// zaten Tailwind'in isim alanında (`design-system/tailwind.css` →
// `--text-xs: 11px`, `--text-2xs: 10px`, `--text-md: 13px`), yani
// `text-[11px]` yerine `text-xs`, `text-[13px]` yerine `text-md` — ölçülen
// çözümleme birebir aynı pikseli veriyor (Tailwind çıktısı: `font-size:
// var(--text-xs)` → 11px).
//
// HARF ARALIĞI da artık token: design-system'de `--ls-label/.22em`
// (bölüm etiketi), `--ls-data/.14em` (veri etiketi + marka) ve
// `--ls-chrome/.12em` (nav/dipnot) rolleri var; köprü bunları
// `tracking-label|data|chrome` utility'lerine bağlar. Öncesinde aynı
// değerler çağrı yerlerinde `tracking-[0.22em]` gibi arbitrary
// yazılıyordu — yani tek kaynak design-system değil, üç dosyaydı.
//
// Renk tarafında arbitrary değer YOK: tüm tonlar repo token'larıdır
// (globals.css shadcn yuvası → design-system). Renk kararları
// cva-variant'ta durur (patterns-explicit-variants) — bileşende ternary değil.

// Mono büyük harfli bölüm etiketi (panel başlığı, "Son Koşum" satırı).
export const panelLabel = cva(
  "font-mono text-xs uppercase tracking-label text-muted"
);

// Küçük veri etiketi (istatistik etiketleri, tablo başlık satırı).
export const microLabel = cva("font-mono text-2xs tracking-data text-muted");

// Üst kavuzdaki marka işareti.
export const brandMark = cva("font-mono text-md font-semibold tracking-data");

// Dipnot satırı.
export const footerNote = cva("font-mono text-xs tracking-chrome text-muted");

// Üst kabuktaki nav bağlantısı (ÖZET / TREND).
//
// Neden burada: aynı dizge (`transition-colors hover:text-fg`) iki bağlantıda
// birebir kopyalanmıştı ve ODAK işareti hiç yoktu — klavyeyle gezen kullanıcı
// nav'da nerede olduğunu göremiyordu (bulgu ailesi: odak halkası yalnız
// primitive tabanlarındaydı). Halka sözleşmesi buton tabanıyla AYNIdır
// (`focus-visible:ring-3` + `ring-ring/50`): iki yüzey iki farklı odak
// işareti göstermemeli.
//
// `focus-visible:outline-none` bilinçli olarak butondaki çıplak
// `outline-none`dan daha DAR: bağlantı tarayıcı varsayılanıyla zaten
// odaklanabilir bir öğe, yerleşik halkayı yalnız klavye odağında kapatıp
// yerine token'lı halkayı koymak yeterli. `rounded-sm` halkayı metnin
// etrafında dikdörtgen yerine yumuşak gösterir (--radius-sm token'ı).
export const navLink = cva(
  "rounded-sm transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-[var(--focus-ring-width)] focus-visible:ring-ring/50"
);

// Card örneğini repo paletine bağlar. shadcn `Card` yapıyı (kabuk,
// başlık/içerik slotları, halka kenarı) verir; bu iki ölçü panonun kanonik
// `.card` reçetesine (preview.html: 8px yarıçap, 14px dolgu) oturtur:
//   `rounded-lg` → `--radius` (globals.css: --radius-6 = 8px)
//   `--card-spacing` → `--card-padding` (= --space-6 = 14px); shadcn
//     varsayılanı `--spacing(4)` = 10px, aynı dolguyu header/content/gap
//     için üç yerden taşıyan değişken.
//
// `tone` KAPALI bir kümedir (patterns-explicit-variants): hata yüzeyi çağrı
// yerinde `cn(panelCard(), "border border-err …")` diye kuruluyordu, yani
// yüzey kararı iki dosyada iki farklı dizge olabiliyordu. Artık tek varyant:
//   `default` → shadcn halkası (`ring-1 ring-foreground/10`)
//   `error`   → repo token'larıyla tint zemin + --err kenarı; halka KAPALI
//               (`ring-0`), aksi halde iki ayrı kenar üst üste biner.
export const panelCard = cva(
  "rounded-lg [--card-spacing:var(--card-padding)]",
  {
    variants: {
      tone: {
        default: "",
        error: "border border-err bg-tint-err-bg ring-0",
      },
    },
    defaultVariants: { tone: "default" },
  }
);

export type PanelTone = NonNullable<VariantProps<typeof panelCard>["tone"]>;

// Verdict tonu → repo token'ı. Kullanım yerinde ternary DEĞİL: karar
// varyant tablosunda (patterns-explicit-variants).
// Hüküm sesi: design-system'deki üçüncü ses (`--font-verdict`) + rol
// ölçeği (`--text-display` / `--lh-display`). Önce `font-serif text-5xl`
// idi — ikisi de köprünün dışındaydı: `font-serif` Tailwind'in kendi
// yığınına, `text-5xl` Tailwind'in 30px ölçeğine düşüyordu.
export const verdictTone = cva(
  "mt-(--panel-block-gap) font-verdict text-display leading-display font-semibold",
  {
    variants: {
      tone: {
        // PASS yeşil, FAIL/ERROR kırmızı, "bilinmeyen ama dolu" karar sarı
        // (fail ile karıştırılmasın), yoksa nötr (yanlışlıkla yeşil görünmesin).
        pass: "text-ok",
        fail: "text-err",
        warn: "text-warn",
        none: "text-muted",
      },
    },
    defaultVariants: { tone: "none" },
  }
);

export type VerdictTone = NonNullable<VariantProps<typeof verdictTone>["tone"]>;

// Koşum ham verisindeki PASS/FAIL kararını tona çevirir. Tek giriş noktası:
// hem VerdictCard hem tablo aynı eşlemeyi kullanır, ayrışamaz.
export function toneForVerdict(verdict: string | undefined): VerdictTone {
  const v = (verdict ?? "").toUpperCase();
  if (v === "PASS") return "pass";
  if (v === "FAIL" || v === "ERROR") return "fail";
  if (v === "") return "none";
  return "warn";
}

// P0/P1 gibi sayısal bulguların rozet tonu: sıfır sessiz ("none"), sıfır
// dışı çağrılan ciddiyet tonu (P0→fail, P1→warn). Eşik kararı çağrı yerinde
// verilir ki aynı sayı farklı bağlamda farklı ciddiyet taşıyabilsin.
export function countTone(
  value: number | undefined,
  when: Exclude<VerdictTone, "none">
): VerdictTone {
  return (value ?? 0) > 0 ? when : "none";
}

// Rozet (Badge) örneği: shadcn'ın `badgeVariants` tonları yerine repo'nun
// tint'leri. Renk/kenar çiftleri preview.html'in `.ok/.warn/.err/.unknown`
// sınıflarının birebir karşılığı (tint arka plan + ton metni + ton kenarı).
//
// Badge'in kendi taban sınıfları (h-5, px-2, py-0.5, text-xs, rounded-4xl)
// shadcn'ın varsayılan ölçeğidir; burada ölçülen değerler kanonik rozet
// ölçüsüne (--badge-padding 4px/10px, punto 12px) çekilir. `cn`
// (tailwind-merge uyumlu) çakışanları sona göre ayıklar — teyit edildi.
// Rozet ölçüsü: `--badge-padding` (4px/10px) + `--badge-radius` (12px).
// shadcn tabanı `h-5 rounded-4xl px-2 py-0.5`; yarıçap `--radius`tan türeyen
// 20.8px'e düşüyordu, yani kanonik rozet 12px değildi. Yükseklik artık
// `h-auto` + 4px dikey dolgu + 12px punto (26px) — tablo satırıyla (30px)
// aynı ritimde, kart başlığındaki 11px etiketten bir kademe iri.
export const statBadge = cva(
  "h-auto rounded-(--badge-radius) px-4 py-1 text-sm font-mono",
  {
    variants: {
      tone: {
        pass: "border-ok bg-tint-ok-bg text-ok",
        fail: "border-err bg-tint-err-bg text-err",
        warn: "border-warn bg-tint-warn-bg text-warn",
        none: "border-border bg-tint-unknown-bg text-muted",
      },
    },
    defaultVariants: { tone: "none" },
  }
);

// Güvenlik yüzeyi rozeti: kapı DURUMU → ton. `statBadge`in ton değil
// `DefenseState` alan kardeşi; karar yine varyant tablosunda
// (patterns-explicit-variants), çağrı yerinde ternary değil.
//
// Renk sözleşmesi TEK yönlüdür: yalnız `active` yeşildir. `fail-closed` ve
// `widened` uyarı sarısıdır — birincisi kapının devrede olmadığını (uç
// kapalı ama token yok), ikincisi izin kümesinin genişletildiğini söyler.
// İkisini yeşile boyamak panoyu "her şey yolunda" diye okuturdu; tanınmayan
// durum nötr kalır (`none`), asla yeşile düşmez.
export const defenseBadge = cva(
  "h-auto rounded-(--badge-radius) px-4 py-1 text-sm font-mono",
  {
    variants: {
      state: {
        active: "border-ok bg-tint-ok-bg text-ok",
        "fail-closed": "border-warn bg-tint-warn-bg text-warn",
        widened: "border-warn bg-tint-warn-bg text-warn",
        unknown: "border-border bg-tint-unknown-bg text-muted",
      },
    },
    defaultVariants: { state: "unknown" },
  }
);

// Bulgu öncelik rozeti (P0/P1). Renk kararı çağrı yerinde ternary DEĞİL —
// kapalı küme (P0/P1/UNKNOWN) burada varyant olarak durur; tanınmayan
// öncelik nötr kalır (sessizce kırmızıya/warna terfi etmez).
export const findingBadge = cva(
  "h-auto rounded-(--badge-radius) px-4 py-1 text-sm font-mono",
  {
    variants: {
      priority: {
        P0: "border-err bg-tint-err-bg text-err",
        P1: "border-warn bg-tint-warn-bg text-warn",
        UNKNOWN: "border-border bg-tint-unknown-bg text-muted",
      },
    },
    defaultVariants: { priority: "UNKNOWN" },
  }
);

// ── kart ↔ tablo armonisi ────────────────────────────────────────────────
//
// Pano tabloları kartın İÇİNDE yaşar. Üç ölçü tek yerden gelir:
//
//  1. `panelTableBleed`: tablo, kartın yatay dolgusunun DIŞINA taşar. Aksi
//     halde hücre metni `kart-padding + hücre-padding` (= 14+10=24px) ile
//     başlarken kart başlığı 14px'te kalıyordu; ilk sütun başlıkla
//     hizalanmıyordu. Taşma, satır çizgilerinin/hover'ının da kart kenarına
//     kadar uzanmasını sağlar — tablo kartın parçası gibi okunur.
//  2. `tableCell`: dolgu `--panel-table-cell` (6px 14px). Yatay ucu kart
//     dolgusuna eşit olduğu için bleed'den sonra metin yine 14px'te durur.
//  3. `tableHead`: aynı dolgu + `h-auto`. shadcn'ın `h-10` (28px) sabiti
//     gövde satırıyla (6+6+18=30px) 2px oynuyordu; dolgu eşit olunca
//     başlık satırı 27px, gövde 30px — fark tipografiden gelir, sabit bir
//     yükseklik dayatmasından değil.
export const panelTableBleed = cva(
  "[margin-inline:calc(var(--card-padding)*-1)]"
);

export const tableHead = cn(
  microLabel(),
  "h-auto p-(--panel-table-cell) font-medium"
);

// Hücre reçetesi. TON kapalı kümedir (patterns-explicit-variants);
// `tabular-nums` tabanda çünkü tablo gövdesindeki her hücre sayı ya da
// zaman damgasıdır (RunsTable'ın eski yerel `cellVariants`ının genelleşmiş
// hâli — üç tablo artık aynı ölçüyü paylaşır).
export const tableCell = cva(
  "p-(--panel-table-cell) align-middle tabular-nums",
  {
    variants: {
      tone: {
        neutral: "",
        error: "text-err",
        warn: "text-warn",
        muted: "text-muted",
      },
    },
    defaultVariants: { tone: "neutral" },
  }
);

// Kartlar arası dikey ritim (sayfa), kart İÇİ blok ritmi ve etiket↔değer
// aralığı — hepsi design-system'deki `--panel-*` rollerinden. Sayısal
// utility (`space-y-6`) dolaylı olarak doğru pikseli veriyordu ama ROL
// taşımıyordu: kartlar arasına 18px, kart içine 12px koymak isteyen
// geliştirici hangi sayının hangi role ait olduğunu bilemiyordu.
export const panelStack = cva("space-y-(--panel-section-gap)");
export const cardStack = cva("space-y-(--panel-block-gap)");

// Kart içindeki "iç kuyu": istatistik/karşılaştırma kolonları. Öncesinde
// yalnız `bg-bg` idi — dolgusuz ve yarıçapsız, metin kutunun kenarına
// değiyordu. Aynı rol, üç yüzeyde (VerdictCard istatistikleri, koşum
// karşılaştırma kolonları, tablo dışı veri blokları) tek ölçü verir.
export const insetWell = cva(
  "rounded-(--radius-4) bg-bg p-(--panel-block-gap)"
);
