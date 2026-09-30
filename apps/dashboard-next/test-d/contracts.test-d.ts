// Pozitif tip-testleri — panel sözleşmeleri.
//
// Her iddia bir KARAR kaydeder: "bu tip tam olarak şu kümedir". Amaç, tip
// sisteminin sessizce gevşemesini engellemek. tsc zaten "bu atama geçiyor mu"
// diye sorar; burada sorulan soru farklı: "sözleşme hâlâ AYNI mı". Fark
// önemli — bir alan adı değişse, bir union'a varyant eklenirse ya da bir
// dönüş `string`e genişlerse atamalar yine geçer, ama pano sessizce bozulur.
//
// Desen: `Assert<Equal<A, B>>` (bkz. ./assertions.ts — tek parça bir
// `AssertEqual<A, B>` takma adı tsc'de derlenmiyor, gerekçesi orada).
//
// Koşum: `python3 test-d/run_type_tests.py` (iki geçişli) veya doğrudan
// `tsc -p tsconfig.typetests.json`.

import type { VariantProps } from "class-variance-authority";
import {
  countTone,
  panelCard,
  statBadge,
  toneForVerdict,
  verdictTone,
  type PanelTone,
  type VerdictTone,
} from "@/components/panel-style";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
} from "@/components/PanelCard";
import type { ComponentProps, ReactNode } from "react";
import {
  API_BASE,
  getLatest,
  getTrend,
  type Latest,
  type TrendRow,
  type TrendSource,
} from "@/lib/preview";
import { isTheme, resolveTheme, THEMES, type Theme } from "@/lib/theme";
import type { Assert, Equal } from "./assertions";

// ── ton sözlüğü ─────────────────────────────────────────────────────────────

// 1) Ton kümesi KAPALI: dört değer, ne eksik ne fazla. `toneForVerdict` kararı
//    elle sayıyor (PASS→pass, FAIL/ERROR→fail, boş→none, gerisi→warn) ve
//    `defaultVariants`ı da "none". Yeni bir varyant eklenirse bu iddia düşer
//    ve eşlemenin yeniden düşünülmesini ZORUNLU kılar — aksi hâlde yeni ton
//    metinde basılır ama kararı hiç üretilmez.
type _ToneSetIsExact = Assert<
  Equal<VerdictTone, "pass" | "fail" | "warn" | "none">
>;

// 2) Metin tonu ile rozet tonu AYNI kümeyi taşımalı. İkisi ayrı cva tablosu;
//    ayrışırsa VerdictCard'ın bir tonu rozete geçtiği an derlenmez — ya da
//    daha kötüsü, rozet tonu metin tonuna atanabilir kalır ve panelin bir
//    yarısı sessizce farklı bir görsel dil konuşur.
type _BadgeAndTextShareToneSet = Assert<
  Equal<NonNullable<VariantProps<typeof statBadge>["tone"]>, VerdictTone>
>;

// 3) İki eşleyici de bir TON üretir, serbest metin değil. `string`e genişlerse
//    `verdictTone({ tone: ... })` ve `statBadge({ tone })` her şeyi kabul eder;
//    yani ton kararı çağrı yerine sızar (patterns-explicit-variants ihlali).
type _ToneForVerdictProducesTone = Assert<
  Equal<ReturnType<typeof toneForVerdict>, VerdictTone>
>;
type _CountToneProducesTone = Assert<
  Equal<ReturnType<typeof countTone>, VerdictTone>
>;

// 4) `countTone`un ikinci parametresi CİDDİYETtir, ton değil: "none" dışlanmış
//    olmalı. Dışlanmasaydı çağrı yeri sıfır sayıyı da zorla görünür
//    yapabilirdi; sözleşme "sıfır → sessiz" diyor ve bunu tip taşıyor.
type _CountToneSeverityExcludesNone = Assert<
  Equal<Parameters<typeof countTone>[1], "pass" | "fail" | "warn">
>;

// 5) Karar alanı opsiyonel bir tel alanıdır: çağrı yeri `latest.verdict`i
//    doğrudan geçebilmeli, yani `undefined` kabul edilmeli (yoksa her çağrı
//    `?? ""` yazmak zorunda kalırdı). Parametrenin kendisi zorunlu — bunun
//    negatif karşılığı negatives.test-d.ts'te.
type _ToneForVerdictAcceptsOptionalWireField = Assert<
  Equal<Parameters<typeof toneForVerdict>[0], string | undefined>
>;

// ── veri kaynağı seçimi ─────────────────────────────────────────────────────

// 6) Kaynak kümesi kapalı: "db" | "preview". `trendSource()` guard'ı elle
//    yazılmış (`explicit === "db" || explicit === "preview"`), yani kümeye
//    üçüncü bir kaynak eklenirse fonksiyon onu HİÇ döndüremez: `TREND_SOURCE`
//    ayarlansa bile sessizce fallback'e düşerdi. Bu iddia o boşluğu derleme
//    hatasına çevirir — tip genişlerse guard da elden geçmek zorunda.
type _TrendSourceIsExact = Assert<Equal<TrendSource, "db" | "preview">>;

// 7) `API_BASE` fallback'i yerinde olmalı. `?? "http://127.0.0.1:8000"`
//    düşerse tip `string | undefined` olur ve şablondaki her kullanım
//    (`${API_BASE}/preview.html`) sessizce "undefined/preview.html" üretir —
//    derleme hatası vermeden. Tipi `string`e sabitlemek fallback'i sözleşme
//    yapar.
type _ApiBaseHasFallback = Assert<Equal<typeof API_BASE, string>>;

// ── veri katmanının iki kapısı ──────────────────────────────────────────────

// 8) İki kapı da tel-sözleşmesini BİREBİR döndürür: ne fazladan alan sızdırır
//    ne alan gizler. `getLatest`/`getTrend` Server Component'lerin veriye
//    açılan tek kapısı; dönüş tipi kayarsa kartların beklediği alan sessizce
//    `undefined`a düşer ve pano "—" gösterir (hata değil, boşluk).
type _GetLatestSurface = Assert<
  Equal<Awaited<ReturnType<typeof getLatest>>, Latest>
>;
type _GetTrendSurface = Assert<
  Equal<Awaited<ReturnType<typeof getTrend>>, { history: TrendRow[] }>
>;

// 9) Pencere parametresi opsiyonel ve SAYISALdır. Sorgu dizesine çevrilirken
//    (`?limit=${limit}`) sayı olması bir varsayım değil, sözleşme.
type _GetTrendLimitIsOptionalNumber = Assert<
  Equal<Parameters<typeof getTrend>[0], number | undefined>
>;

// ── tel-sözleşmesinin alan kümeleri ─────────────────────────────────────────

// 10) Alan kümeleri preview_server'ın DÜZ JSON şeklidir (iç içe `z3` nesnesi
//     yok — bilinçli: iki yüzey aynı düz alanları yayınlar). Bir alan
//     eklenirse ya da adı değişirse burada durur; runtime'da fark edilmesi
//     gerekmez, çünkü eksik alan hata vermez, "—" basar.
type _LatestFields = Assert<
  Equal<
    keyof Latest,
    | "verdict"
    | "ts"
    | "p0"
    | "p1"
    | "stripped_sha256"
    | "z3_passed"
    | "z3_total"
    | "z3_failed"
    | "budget_usd"
    | "budget_limit"
  >
>;
type _TrendRowFields = Assert<
  Equal<
    keyof TrendRow,
    "ts" | "p0" | "p1" | "duration_s" | "budget_usd" | "z3_total"
  >
>;

// 11) Tüm tel alanları OPSİYONEL. Kısmi yanıt meşrudur (DB kaynağı bazı
//     alanları hiç göndermez, preview_server kısmi JSON basabilir); zorunlu
//     alan eklemek `{}` yanıtını tip hatasına çevirir ve panoyu kırılgan yapar.
type _LatestAllOptional = Assert<{} extends Latest ? true : false>;
type _TrendRowAllOptional = Assert<{} extends TrendRow ? true : false>;

// ── tema sözleşmesi (açık tema köprüsünün kapısı) ───────────────────────────

// 12) Tema kümesi KAPALI ve tam olarak {dark, light}. Köprüde karşılığı
//     olmayan bir ad eklenirse (`stripe` sheet'i burada import EDİLMEZ)
//     `data-theme` hiçbir bloğa düşmez: pano "açık tema" derken koyu kalır —
//     hata değil, sessiz boşluk. Kümeyi burada dondurmak o sessizliği kırar.
type _ThemeSetIsExact = Assert<
  Equal<(typeof THEMES)[number], "dark" | "light">
>;

// 13) Çözümleyicinin `theme` alanı `string`e genişlememeli: genişlerse
//     `dataset.theme` doğrulanmamış yazım hatalarını (`"strkpe"`) sessizce
//     kabul eder ve doğrulama yalnız çalışma anında, görünmeden kaybolur.
type _ResolveThemeReturn = Assert<
  Equal<ReturnType<typeof resolveTheme>, { theme: Theme; persist: boolean }>
>;

// 14) `isTheme` bir tip-koruyucusudur (type predicate), düz `boolean` değil.
//     Düz `boolean`'a düşerse çağrı yerlerindeki daralma kaybolur ve geçersiz
//     tema adları yine de `Theme` sanılır — kapının kendisi kanıtsız kalır.
type _IsThemeIsTypeGuard = Assert<
  Equal<typeof isTheme, (value: string | null | undefined) => value is Theme>
>;

// ── panel kabuğu (Card bileşimi) ────────────────────────────────────────

// 15) Yüzey tonu KAPALI: {default, error}. Hata yüzeyi bir ara çağrı yerinde
//     `cn(panelCard(), "border border-err …")` diye kuruluyordu; yani aynı
//     yüzey iki dosyada iki farklı dizge olabiliyordu. Kümeyi burada dondurmak
//     "üçüncü bir hata tonu"nun sessizce eklenmesini engeller.
type _PanelToneSetIsExact = Assert<Equal<PanelTone, "default" | "error">>;

// 16) Kabuk tonu OPSİYONELdir (verilmezse `default`) ve ton tam olarak
//     `PanelTone`tır: `string`e genişlerse tüm varyant tablosu anlamını
//     yitirir, çağrı yerleri serbest metin geçer.
type _PanelCardToneIsOptional = Assert<
  Equal<Parameters<typeof PanelCard>[0]["tone"], PanelTone | undefined>
>;

// 17) Başlık etiketi TAM olarak `<h2>` prop'larını alır ve `children`ı
//     düğümdür. Bir `div`e (shadcn `CardTitle` gibi) kayarsa bölüm
//     hiyerarşisi sessizce kaybolur — axe bunu "heading-order" ihlali olarak
//     değil, sadece başlıksız bölüm olarak görür.
type _PanelCardTitleIsAnH2 = Assert<
  Equal<Parameters<typeof PanelCardTitle>[0], ComponentProps<"h2">>
>;

// 18) Başlık satırı yalnız bir YERLEŞİM yuvasıdır: içeriği `children`dan
//     alır (iskeletler metin yerine nabız çubukları koyar). `title`/`meta`
//     gibi özel prop'ları olsaydı aynı yuva iki farklı yolla doldurulur ve
//     ikisi zamanla ayrışırdı.
type _PanelCardHeaderIsASlot = Assert<
  Equal<Parameters<typeof PanelCardHeader>[0]["children"], ReactNode>
>;

// 19) İçerik yuvası ek bir zorunlu prop İCAT ETMEZ: `children` standarttır,
//     çağrı yerleri `PanelCardContent`'i sarmalayıcı olarak kullanabilir.
type _PanelCardContentTakesChildren = Assert<
  Equal<Parameters<typeof PanelCardContent>[0]["children"], ReactNode>
>;

// 20) `panelCard` varyantlı çağrıyı ve varyantsız çağrıyı birlikte kabul eder
//     (mevcut çağrı yerleri `panelCard()` yazıyor; varsayılan ton `default`).
type _PanelCardStillCallableBare = Assert<
  Equal<ReturnType<typeof panelCard>, string>
>;
