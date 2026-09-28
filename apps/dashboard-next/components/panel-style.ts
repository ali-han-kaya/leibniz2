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
// HARF ARALIĞI hâlâ arbitrary ve bilinçli: repo'nun `--ls-caps` token'ı
// 0.05em (preview.html'in h2leri), panonun mono büyük-harfli etiketleri
// ise 0.12–0.22em arasında — farklı bir ses. Yeni token üretmek
// tokens.json → tokens.css → GENERATED tailwind.css zincirini ve
// check-design-tokens sözleşmesini değiştirirdi; o yüzden değerler burada
// adlandırılmış tek kaynakta duruyor.
//
// Renk tarafında arbitrary değer YOK: tüm tonlar repo token'larıdır
// (globals.css shadcn yuvası → design-system). Renk kararları
// cva-variant'ta durur (patterns-explicit-variants) — bileşende ternary değil.

// Mono büyük harfli bölüm etiketi (panel başlığı, "Son Koşum" satırı).
export const panelLabel = cva(
  "font-mono text-xs uppercase tracking-[0.22em] text-muted"
);

// Küçük veri etiketi (istatistik etiketleri, tablo başlık satırı).
export const microLabel = cva(
  "font-mono text-2xs tracking-[0.14em] text-muted"
);

// Üst kavuzdaki marka işareti.
export const brandMark = cva(
  "font-mono text-md font-semibold tracking-[0.14em]"
);

// Dipnot satırı.
export const footerNote = cva("font-mono text-xs tracking-[0.12em] text-muted");

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
  "rounded-sm transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
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
export const verdictTone = cva("mt-3 font-serif text-5xl font-semibold", {
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
});

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
export const statBadge = cva("h-auto px-4 py-1 text-sm font-mono", {
  variants: {
    tone: {
      pass: "border-ok bg-tint-ok-bg text-ok",
      fail: "border-err bg-tint-err-bg text-err",
      warn: "border-warn bg-tint-warn-bg text-warn",
      none: "border-border bg-tint-unknown-bg text-muted",
    },
  },
  defaultVariants: { tone: "none" },
});

// Tablo başlık hücresi: repo'nun `th` reçetesi (preview.html: renk muted,
// 10px mono büyük harf, 6px/10px dolgu). shadcn'ın `h-10 px-2`'si yatay
// dolguyu 6px'te bırakıyor; `px-4` (10px) kanonik değere yetiyor, yükseklik
// zaten 28px = --spacing-10 ile uyuşuyor.
export const tableHead = cn(microLabel(), "px-4");
