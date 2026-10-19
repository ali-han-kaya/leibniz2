# design-system/vercel — Vercel (vercel.com) tokens (verbatim)

Extracted from the live homepage **https://vercel.com** on 2026-09-18
(light theme).

**Scope warning:** this is a **partial** extraction. Vercel inlines most of
its styling and exposes few custom properties to computed style; this capture
contains **19** `--*` variables. It is not the full Vercel/Geist design
system.

## Files

- `tokens.json` — structured tokens grouped by namespace (`color`, `geist`,
  `ship`, `develop`, `preview`, `ds`). Single source of truth for tooling;
  includes capture provenance and count.
- `tokens.css` — flat `:root` drop-in containing the same 19 variables.
  `@import "design-system/vercel/tokens.css"` and use `var(--…)` directly.
- `raw.json` — full extractor capture: computed palette, CSS-variable map,
  typography, spacing, borders, shadows, breakpoints, and framework hints.
  This is the audit source for the canonical token files.
- `tailwind.css` — **GENERATED** Tailwind v4 `@theme` köprüsü: 19/19 yuva
  (`bg-vercel-gray-900`, `bg-vercel-background-100`, …). Üretici
  `design-system/scripts/generate_mirror_tailwind.py`, kapı
  `check_mirror_bridges.py`. Vercel'in `--color-*` adları ön-eksiz
  üretilseydi kök paleti gölgelerdi.
- `scripts/check_vercel_tokens.py` — fail-closed drift gate. It derives the
  expected token map from `raw.json → colors.cssVariables`, then requires
  `tokens.css` and grouped `tokens.json` to match exactly.
- `theme.css` — **GENERATED** dashboard adapter varyantı: tek
  `:root[data-theme="vercel"]` bloğu, repo semantik yuvalarını (`--bg`,
  `--fg`, `--accent`, `--surface`, …) bu aynanın token'larına bağlar.
  Üretici `scripts/generate_vercel_theme.py`; kapı contract 9
  (`design-system/scripts/check_tokens.py`).
- `scripts/generate_vercel_theme.py` — varyantın üreticisi; `--check` iki
  kopyayı (dosya ↔ `render()` çıktısı) karşılaştırır. Kapsam/yuva/istisna
  sözleşmeleri aşağıda.

Unlike Linear/Stripe/Primer, the raw source is JSON rather than CSS because
Vercel did not expose static stylesheet chunks to the extractor. The
repository-facing contract is the same: one raw capture, one canonical
`tokens.json`, one drop-in `tokens.css`, and one drift checker. Do not add a
second tool-generated starter layer.

## Source

Page `https://vercel.com/` via Chrome Headless Shell 153
(`playwright-core 1.63.0`, through `dembrandt 0.7.0` /
`extract-design-system 0.1.11`). No static CSS chunk URLs were captured;
values come from `getComputedStyle` on the live DOM.

Notable verbatim values:

```text
--color-gray-1000: hsla(0, 0%, 9%, 1)       --ship-text: #ff5b4f
--color-background-100: hsla(0, 0%, 100%, 1) --develop-text: #0a72ef
--geist-console-text-color-blue: #0070f3     --preview-text: #de1d8d
--ds-focus-color: hsla(212, 100%, 48%, 1)   --color-gray-alpha-400: #00000014
```

Palette by computed-style count: `#ebebeb` (537×, dividers) · `#171717`
(301×, ink) · `#4d4d4d` (186×) · `#8f8f8f` (28×) · `#ffffff` (22×).

Typography: **GeistSans** (headings 64px/1.00/−3.84px w400; body
16px/1.50) + **Geist Mono** (uppercase captions). Spacing uses a
2/6/8/12/16/24px core; radius is **6px dominant**, with 4/8/12 and 128px
pills.

## Extraction

Run from this directory so the tool's raw capture is written beside the
canonical files:

```bash
npx --yes playwright install chromium
npx --yes extract-design-system@0.1.11 https://vercel.com --extract-only
```

The extractor is evidence tooling, not a repo runtime dependency. Preserve
`raw.json`; update `tokens.json` and `tokens.css` from its
`colors.cssVariables` map without remapping, renaming, or rounding.

## How to use

Without Tailwind, `tokens.css` is the only file needed at runtime: import it
once in the global stylesheet, then reference the original custom-property
names:

```css
@import "design-system/vercel/tokens.css";

.cta {
  color: var(--develop-text);
  border-color: var(--color-gray-500);
}

.selected { background: var(--geist-selection-text-color); }

.focus-ring:focus-visible {
  outline: 2px solid var(--ds-focus-color);
}
```

With Tailwind, import the generated bridge rather than writing arbitrary
values — all 19 slots have a utility (`aliases=19`, `skipped=0`):

```css
@import "tailwindcss";
@import "../../design-system/vercel/tailwind.css";
/* → bg-vercel-gray-900  text-vercel-develop-text  border-vercel-gray-500 */
```

Arbitrary values such as `text-[var(--develop-text)]` still work for anything
outside the bridge. Do not copy values from `raw.json` at runtime or rename the
variables.

### Next.js (App Router)

A real `app/globals.css` — the same shape this repository's dashboard uses
(`apps/dashboard-next/app/globals.css`, pulled in by `app/layout.tsx` through
`import "./globals.css"`):

```css
/* app/globals.css */
@import "tailwindcss";
@import "../../../design-system/vercel/tailwind.css";
```

The order is a contract, not style. The bridge re-exposes the mirror as Tailwind
v4 `@theme` slots but deliberately does not import `tailwindcss` itself: a bare
specifier inside the bridge resolves from the bridge's own directory and breaks
the consumer's build (observed as Next.js `Can't resolve 'tailwindcss'`, which is
why the generator is written this way). Core first, bridge second. The specifier
resolves relative to the stylesheet, so its depth follows the app's location —
`../../../` is the dashboard's depth under `apps/`.

With Tailwind, the bridge is the only import needed: it carries its own `:root`
preconditions, so `tokens.css` is not added alongside it. Every slot is
prefixed, so the mirror sits next to the root palette without shadowing it —
`bg-bg`, `bg-accent` and `rounded-6` still come from
`design-system/tailwind.css`. No `tailwind.config.js` and no arbitrary values are
needed:

```tsx
// app/page.tsx
export default function Page() {
  return (
    <main className="bg-vercel-background-100 text-vercel-gray-1000">
      <a
        className="border-b border-vercel-gray-500 text-vercel-develop-text"
        href="/deploy"
      >
        Deploy
      </a>
      <span className="text-vercel-ship-text">● ship</span>
      <span className="text-vercel-preview-text">● preview</span>
    </main>
  );
}
```

Focus and selection stay on the mirror's own names instead of a renamed token —
the preconditions are global once the bridge is imported:

```css
:focus-visible {
  outline: 2px solid var(--vercel-ds-focus-color);
}

::selection {
  background: var(--vercel-geist-selection-text-color);
}
```

The capture is color-only, so type stays the app's job: load **GeistSans /
Geist Mono** yourself, or keep a platform fallback. With `next/font`:

```tsx
// app/layout.tsx
import "./globals.css";
import { Geist, Geist_Mono } from "next/font/google";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

The capture is light-theme only, so a dark surface has nothing to import: dark
values are the consumer's own contract, written against these names — never by
pasting values out of `raw.json`.

## Limits

- One homepage is not proof of the whole Vercel product design system; app
  surfaces use a larger token set that this capture did not expose.
- The tool's normalized semantic pair (white/transparent) is intentionally
  absent from the canonical layer because it does not represent the useful
  computed palette.
- `3.35544e+07px` radius values in `raw.json` are Tailwind `rounded-full`
  artifacts, not real tokens.
- Framework hints in `raw.json` are class-name heuristics; Vercel itself is
  Next.js + Tailwind.

## Keeping in sync

Vercel ships content-hashed assets and can change without notice. Re-capture
`raw.json`, regenerate the grouped entries in `tokens.json`, update the flat
`:root` block in `tokens.css`, then run the drift gate. The checker is
offline and deterministic; it never contacts vercel.com.

## Tema varyantı (`theme.css`)

Ayna token'ları doğrudan kullanıma hazırdır ama panonun anladığı dil repo
semantik yuvalarıdır. Varyant bu iki dili bağlar: kaynakta hiçbir renk
literal'i yoktur, yalnız `var(--color-*)` / `var(--develop-text)` … ve
`color-mix(... var(--ship-text) ...)` türetmeleri.

```bash
python3 design-system/vercel/scripts/generate_vercel_theme.py         # yeniden üret
python3 design-system/vercel/scripts/generate_vercel_theme.py --check  # drift denetimi
# OK — vercel adapter varyantı jeneratörle birebir (28/32 yuva, 4 ilan edilmiş istisna, 11/19 ayna token'ı)
```

- **Kapsam:** yalnız `:root[data-theme="vercel"]` bloğu; başka seçici yasak
  (kapsam sızıntısı = contract 9 FAIL). Koyu/açık varsayılanlar değişmez.
- **Yuvalar:** `SLOT_MAP` 32 yuva; 28'i bağlı. `REQUIRED_SLOTS`'un tamamı
  ya bağlı ya da `EXCEPTIONS`'ta **ilan edilmiş** olmalı — eksik yuva
  üreticiyi `SystemExit` ile düşürür (sessiz kısmi varyant yok). Vercel'in
  19-token ışık yakalaması success/warning tonu taşımadığı için dört yuva
  (`--ok`, `--warn`, `--tint-ok-bg`, `--tint-warn-bg`) istisnadır ve taban
  paletten gelir.
- **Değerler:** her yuva en az bir ayna token'ına bağlanır **veya** ilan
  edilmiş istisnadır (literal yasak) ve referans verdiği ön-koşullar aynadan
  **birebir** kopyalanır (`closure()` ile `var()` transitif kapanışı; 19
  token'ın 11'i varyantta ön-koşul olarak taşınır).
- **Tema geçişi:** yakalama yalnız ışık; varyant panonun **varsayılan koyu**
  temasının üzerine `data-theme="vercel"` ile biner — koyu tema
  `tokens.css`'ten etkilenmez, Vercel varyantı ışık rolleriyle okunur.

### Tüketen yüzeyler

| Yüzey | Kullanım |
|---|---|
| `_calisma/CIKTI/preview.html` | `<link rel="stylesheet" href="/design-system/vercel-theme.css?v=1">` + tema döngüsü `dark → light → stripe → vercel` (`?theme=vercel`, `localStorage`) |
| `_calisma/CIKTI/preview_server.py` | `/design-system/vercel-theme.css` rotası (`PREVIEW_DIR/design-system-vercel-theme.css`; yoksa fail-closed 404) |
| `_calisma/CIKTI/sync_verify_mirror.sh` | `GUIDE_FILES` satırı `design-system/vercel/theme.css|design-system-vercel-theme.css` (mirror kopyası) |
| `vercel.json` + `.vercelignore` | route `^/design-system/vercel-theme\\.css$` → `design-system/vercel/theme.css`; `design-system/*` dışlamasının negasyonu yalnız bu dosyayı upload'a alır |
| `design-system/scripts/report_vercel_dashboard_drift.py` | `sources.consumers[].imports_vercel` — "Vercel token'ları bir tüketici tarafından import ediliyor" kanıtı bu linkten okunur |

## Vercel ↔ kök dashboard fark raporu (generated)

Bu mirror'ın kök dashboard token katmanıyla karşılaştırması artık elle
YAZILMAZ: `design-system/scripts/report_vercel_dashboard_drift.py` iki
girdiyi okur, raporu üretir ve iki kopya yazar —

- `_calisma/CIKTI/vercel_dashboard_drift.json` — makine-okunur belge
  (`schema: vercel-dashboard-drift/1`; sayımlar, kategori envanteri,
  paylaşılan/tek-taraflı adlar, değer kimliği, bulgular).
- `_calisma/CIKTI/VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md` — insan-okunur kopya.

`--check` hem TAZELİĞİ (iki kopya jeneratör çıktısıyla birebir mi) hem YAPISAL
SAĞLIĞI (`status == ok`: kategori envanteri tam, light override'lar temel
kümenin alt kümesi, sayı pinleri ve editoryel eşleme kaynakla tutarlı)
fail-closed doğrular. Yerelde `check-vercel-drift-report` pre-commit hook'u,
CI'da `verify` işindeki "Vercel ↔ dashboard design-token drift report" adımı
koşar; belge yeni bir artifact adı açmadan mevcut `logs/` yüklemesine girer.

## Verification

```bash
python3 design-system/vercel/scripts/check_vercel_tokens.py
# OK — 19 Vercel tokens verbatim against raw.json (tokens.css + tokens.json in sync)
python3 design-system/scripts/report_vercel_dashboard_drift.py --check
# OK — Vercel↔dashboard drift raporu taze ve yapısal olarak sağlıklı (19 Vercel + 86 dashboard token, paylaşılan ad 0)
python3 design-system/vercel/scripts/generate_vercel_theme.py --check
# OK — vercel adapter varyantı jeneratörle birebir (28/32 yuva, 4 ilan edilmiş istisna, 11/19 ayna token'ı)
python3 design-system/scripts/generate_mirror_tailwind.py --check
# OK — 4/4 marka köprüsü jeneratörle birebir (… vercel 19/19 yuva …)
```
