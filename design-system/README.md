# design-system/

Starter design tokens extracted from the live CI dashboard at
`_calisma/CIKTI/preview.html` (inline `<style>` block).

## Files

- `tokens.json` — single source of truth (machine-readable).
- `tokens.css` — CSS custom properties on `:root`; drop-in for any page,
  copy the block into a project or `@import` it. Includes dark `:root` and
  `:root[data-theme="light"]` override (single `@import` gives both themes).
- `tailwind.css` — Tailwind CSS v4 theme bridge. **Generated** from
  `tokens.css` — do not edit by hand. See `scripts/generate_tailwind.py`.
- `scripts/check_tokens.py` — drift gate: parses `preview.html` and asserts
  the extraction still matches (dashboard `:root` vars, surfaced literals
  `#161b22` / `#21262d` / `#fff`, all rgba tints, and every derived scale
  value appear verbatim in the source). Contract 7 dashboard-next kopya
  drift'ini (herhangi bir blokta token gölgelemesi / tokens.css değerinin
  yazıyla kopyası / renk literal'i), contract 8 ise preset bağımsızlığını
  ve referans kapanışını denetler: köprü importu zorunlu, dış shadcn preset
  sheet'i yasak, her yuva değeri `var()`/`calc()` referansı olmalı, her
  `var(--X)` çözülebilmeli, her yuva `@theme`'de `--color-<yuva>` alias'ı
  almalı, uygulama kaynağı preset-only yüzey
  (`data-open:`/`no-scrollbar`/`scroll-fade`/`shimmer`) kullanamaz ve
  uygulama kaynağında koda gömülü **renk** bulunamaz: arbitrary renk
  utility'si (`bg-[#0e1116]`), ham hex/rgb/hsl literali (inline stil dahil)
  ve Tailwind'ın varsayılan paleti (`bg-slate-900`, `text-white`) üçü de
  köprü token'ını baypas eder — `bg-bg`/`text-fg`/`border-border` ya da
  `var(--…)` tabanlı türetme kullanılmalı. Contract 9
  ise Stripe HDS tema varyantını denetler: `stripe/theme.css` üreticinin
  (`stripe/scripts/generate_stripe_theme.py`) `render()` çıktısıyla **birebir**
  olmalı, yalnız `:root[data-theme="stripe"]` bloğu taşımalı, 32 yuvanın
  tamamını içermeli, HDS ön-koşulları aynayla aynı olmalı ve yuva değerlerinde
  renk literali bulunmamalı; ayrıca varyantı tüketen yüzeylerdeki
  (`preview.html`, `landing/landing_src.html`) `[data-theme="stripe"]`
  kurallarında her değer `var(` taşımalı. Contract 9'un **Vercel ayağı**
  dashboard adapter varyantını (`vercel/theme.css`) denetler: jeneratör
  çıktısıyla birebir, yalnız `:root[data-theme="vercel"]` bloğu, 32 yuvanın
  28'i bağlı + 4'ü ilan edilmiş istisna (Vercel'in ışık yakalamasında
  success/warning tonu yok), ön-koşullar aynayla birebir, yuva değerlerinde
  renk literali yok ve tüketen yüzeydeki (`_calisma/CIKTI/preview.html`)
  `[data-theme="vercel"]` kurallarında her değer `var(` taşımalı.
- `stripe/theme.css` — **Generated** Stripe HDS tema varyantı: repo semantik
  yuvalarını (`--bg`, `--fg`, `--accent`, `--border`, `--paper`, …) mirror'daki
  `--hds-*` token'larına bağlar. Kaynak: `stripe/README.md` ("Tema varyantı").
  `python3 design-system/stripe/scripts/generate_stripe_theme.py` ile üretilir;
  elle düzenleme drift sayılır (contract 9).
- `vercel/theme.css` — **Generated** Vercel adapter tema varyantı: repo
  semantik yuvalarını (`--bg`, `--fg`, `--accent`, `--surface`, …) mirror'ın
  19-token ışık yakalamasına bağlar (`color-mix` türetmeleri dahil). Kaynak:
  `vercel/README.md` ("Tema varyantı"). Üretim:
  `python3 design-system/vercel/scripts/generate_vercel_theme.py`; elle
  düzenleme drift sayılır (contract 9).
- `scripts/generate_tailwind.py` — renders `tailwind.css` from `tokens.css`.
  No `tailwindcss` install needed to generate; validates the two `:root`
  blocks stay byte-identical.
- `{stripe,linear,primer,vercel}/tailwind.css` — **Generated** marka `@theme`
  köprüleri (bkz. "Marka @theme köprüleri"). Elle düzenlenemez; üretici
  `scripts/generate_mirror_tailwind.py`, kapı `scripts/check_mirror_bridges.py`.
- `scripts/generate_mirror_tailwind.py` — dört marka aynasının `@theme`
  köprüsünü üretir (kapsam/karar kuralları aşağıda). Değer sınıfına göre
  deterministik; ayna başına elle harita YOK.
- `scripts/check_mirror_bridges.py` — o köprülerin kapısı (fail-closed):
  **temel palet ayrıklığı**, ön-koşul birebirliği, `var()`-only değerler,
  sayım kilitleri ve blok disiplini.

## Keeping in sync

When `preview.html`'s `:root` (or the inline styles) change, update
`tokens.json` first, then `tokens.css`, then regenerate `tailwind.css`:

```bash
python3 design-system/scripts/check_tokens.py      # HTML → tokens.css drift
python3 design-system/scripts/generate_tailwind.py # tokens.css → tailwind.css
```

Both must exit `0`. Commit `tokens.json` + `tokens.css` + `tailwind.css`
 together so the three files never drift.

## Marka mirror drift kapısı (pre-commit)

`stripe/`, `linear/`, `primer/` ve `vercel/` mirror'larının kendi drift
kapıları (`scripts/check_<marka>_tokens.py`) pre-commit zincirinde
`check-brand-mirrors` hook'uyla koşar:

```bash
python3 design-system/scripts/check_brand_mirrors.py   # exit 0 = 4/4 PASS
```

- **Roster (tek kaynak):** `design-system/scripts/brand_mirrors.list` —
  `<dizin> <raw> <pin> <checker>`.
- **Pin:** checker'ın bastığı `OK — N` satırındaki N, pinlenen sayıya birebir
  eşit olmalı. Mirror upstream'de değişip `tokens.css`/`tokens.json`
  yenilendiğinde pin'i aynı commit'te **bilinçli** güncelleyin — kapı sessiz
  mirror değişimini bloke eder. `OK` satırı yoksa veya N=0 ise FAIL
  (vacuous PASS yasağı).
- **Tetikleme:** yalnız `design-system/` altından dosya stage'lendiğinde koşar
  (değişim-farkında; `always_run` yok).
- **Fail-closed sözleşmeleri:** roster bütünlüğü (roster yok / <4 giriş /
  kayıtlı dosya diskte yok → exit 2); kapsam (tokens.json + raw.* taşıyan
  kayıtsız mirror kalamaz; açık istisna `# exempt: <dizin> — <gerekçe>` →
  exit 2); checker rc != 0 ve pin uyuşmazlığı → exit 1.
- `github` mirror'ı gerekçeli exempt'tir (ayrı `--sync` yeniden-üretim akışı,
  bkz. `github/README.md`); kapsama almak için roster'a
  `github  raw.json  258  scripts/check_github_tokens.py` satırını ekleyin. Bu
  checker İKİ `OK — N` satırı basar (dark 304 + light 258) ve sürücü pin olarak
  **sonuncuyu** okur (`observed = counts[-1]`), yani pin 258'dir.
- Birim testleri: `_calisma/CIKTI/test_brand_mirror_gate.py` (R1-R5 + hook
  wiring; `check-unit-tests` bataryasında koşar).

## Marka @theme köprüleri (generated)

Her marka aynası `tokens.css` içinde ham token taşır ama Tailwind utility'si
üretmez. `generate_mirror_tailwind.py` ayna başına bir köprü üretir:

```css
@import "tailwindcss";
@import "./design-system/linear/tailwind.css";
/* → bg-linear-bg-panel  text-linear-accent  rounded-linear-12
     font-linear-regular  ease-linear-in-quad  p-linear-core-100 */
```

**Neden ön-ek zorunlu:** lineer/vercel token'ları `--color-*` adları taşır
(`--color-accent`, `--color-bg-*`). Ön-eksiz üretim, kök köprüyle yan yana
import edildiğinde `bg-bg`/`bg-accent`'i sessizce marka paletine kaydırırdı.
Bu yüzden ön-koşullar `<marka>-` ön-ekli, `@theme` anahtarları
`<namespace>-<marka>-*`; kapı bu ayrıklığı kök paletin 133 adına karşı
fail-closed doğrular.

| Karar | Kural |
|---|---|
| Değer sınıfı | Ada değil **değere** bakılır: `--color-alpha: 255` renk değildir |
| Hedef namespace | renk → `--color-*`, font ailesi → `--font-*`, `cubic-bezier` → `--ease-*`, gölge → `--shadow-*`, uzunluk → adında `radius` varsa `--radius-*`, `space\|spacing\|gap` varsa `--spacing-*` |
| Ada açık namespace | Adında tanınan namespace varsa o kazanır (`--font-weight-*` bilinçli kapsam dışı, `font`'a düşmez) |
| Marka katmanı | İlk segment namespace değil, ikincisi öyleyse düşülür: `--hds-color-surface-bg-quiet` → `--color-stripe-surface-bg-quiet` |
| Ön-koşul değeri | Aynadan **birebir**; yalnız ayna-içi `var()` referansları ön-eklenir |
| Çakışma | Anahtarı, adında namespace'i AÇIKÇA taşıyan token alır; kaybeden yuva almaz ama değeri ön-koşul olarak dosyada kalır (`skip:key-collision`) |
| Kapsam dışı | Sayı/süre/composite/url/dış-referans dosyada **sayılır** — `aliases + skipped = tokens` kapıyla kilitlidir (sessiz kayıp yok) |

Ölçüm (2026-09-27): stripe 556/710 · linear 168/398 · primer 1500/2051 ·
vercel 19/19 yuva; toplam 2243/3178 token. Kapsam dışı gerekçeleri köprünün
sonundaki sayım bloğunda (`skip:class-number`, `skip:no-namespace-length`, …)
listelenir.

Kapı sözleşmeleri (B1–B7): roster/köprü bütünlüğü (exit 2) · üretim birebirliği
· temel palet ayrıklığı · `var()`-only bağlantı · ön-koşulun aynayla birebirliği
· sayım/kapsama kilitleri · tek `:root` + tek `@theme` bloğu. READ-ONLY, OFFLINE,
stdlib-only, ~0.3s. Birim testleri: `_calisma/CIKTI/test_mirror_bridges.py`.

## Tailwind v4 usage (no tailwind.config.js)

```css
@import "tailwindcss";
@import "./design-system/tailwind.css";
```

`tailwind.css` re-exposes the same `:root` vars as Tailwind v4 `@theme`
variables, so utilities like `bg-bg`, `text-fg`, `border-border`,
`rounded-6`, `p-6`, `animate-pulse`, `leading-tight`, `tracking-caps`
resolve to the dashboard palette without a config file:

| Tailwind utility | Resolves to |
|---|---|
| `bg-bg` / `text-fg` / `border-border` / `text-accent` | `var(--bg)` / `var(--fg)` etc. |
| `bg-surface` / `bg-surface-1` / `bg-paper` | surface / paper tokens |
| `bg-tint-ok-bg` / `bg-tint-err-bg` | status tints (badge backgrounds) |
| `text-2xs` … `text-xl` / `text-display` | font-size (`--text-*`) |
| `leading-tight` / `leading-display` | line-height (`--lh-*` → `--leading-*`) |
| `tracking-caps` / `tracking-label` / `tracking-data` / `tracking-chrome` | letter-spacing (`--ls-*` → `--tracking-*`) |
| `font-sans` / `font-mono` / `font-verdict` | the three voices (`--font-*`) |
| `rounded-1` … `rounded-7` / `rounded-full` | `var(--radius-*)` |
| `p-1` … `p-10` (spacing scale) | `var(--space-*)` via `--spacing-*` |
| `shadow-tip` | `0 8px 24px rgba(...)` (tooltip shadow) |
| `animate-pulse` / `animate-shake` / `animate-glow` | dashboard keyframe animations |

Custom duration/easing stays as `var(--dur-*)` / `var(--ease*)` for direct
`var()` use; Tailwind's canonical `--leading-*`/`--tracking-*` aliases are
also exposed alongside the legacy `--lh-*`/`--ls-*` names for compat.
Composition vars (`--card-*`, `--badge-*`, `--table-*`, `--pre-*`,
`--button-*`) intentionally have no `@theme` alias — they are multi-token
`var(--space-1) var(--space-4)` shorthands invalid as single theme values.

Pano yüzeyinin **rol** katmanı (`--panel-gutter`, `--panel-section-gap`,
`--panel-block-gap`, `--panel-tight-gap`, `--panel-table-cell`) da `@theme`
alias'ı taşımaz: değerleri sayısal ölçeğe `var()` ile bağlanır ve bileşenler
themen bu adları tüketir (`space-y-(--panel-section-gap)`,
`p-(--panel-table-cell)`). Böylece "kartlar arası 18px" gibi bir karar tek
yerde durur; çağrı yerleri sayı değil rol yazar. `--panel-table-cell`
çok-token olduğu için (`6px 14px`) `padding` shorthand'i olarak kullanılır.

## Vercel ↔ dashboard fark raporu (generated, fail-closed)

`scripts/report_vercel_dashboard_drift.py` Vercel aynası ile kök dashboard
token katmanını karşılaştırır ve İKİ kopya üretir:
`_calisma/CIKTI/vercel_dashboard_drift.json` (makine-okunur;
`schema: vercel-dashboard-drift/1`) + `_calisma/CIKTI/VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md`
(insan-okunur). Rapor elle yazılmaz: `--check` iki kopyayı jeneratör
çıktısıyla BAYT karşılaştırır VE raporun yapısal invaryantlarını
(`status == ok`) doğrular — bozuk durumu yeniden üretip commit etmek kapıyı
yeşil bırakmaz. Kapılar: pre-commit `check-vercel-drift-report`, CI `verify`
işindeki aynı adlı adım (belge yeni artifact adı AÇMADAN mevcut `logs/`
yüklemesine girer). Ayrıntı: `vercel/README.md`.

## Token drift & çakışma kapısı (fail-closed)

Katman başına drift kapılarının (contract 1-9, marka checker'ları, `@theme`
köprüleri, Vercel ↔ dashboard raporu) görmediği İKİ boşluğu kapatır:
katmanlar ARASI çakışma ve ÜRETİLMİŞ kopyaların sessiz kayması. Katman rolleri
TEK KAYNAK `scripts/token_layers.list` roster'ındadır
(`canonical|bridge|variant|consumer|copy|capture`; `capture` satırı gerekçe
zorunludur — kayıtsız ve token tanımlayan bir dosya kapıyı kırar).

- **K1** aynı blokta aynı ad iki kez FARKLI değerle → sonuncusu sessizce kazanır.
- **K2** iki katman aynı kapsamda aynı adı FARKLI değerle tanımlıyor → kazananı
  import sırası belirler (AYNI değer serbest: üretilmiş kopyalar böyle çalışır).
- **K3** varyant kendi `:root[data-theme="…"]` kapsamı dışına taşıyor.
- **K4** üretilmiş kopya (`_calisma/landing/landing.html`) kanonik
  `:root` + light kümelerinden ad/değer olarak sapıyor → yeniden üret:
  `python3 _calisma/landing/build_landing.py`.
- **K5** token tanımlayan dosya roster'da yok ya da roster satırı ölü (iki yönlü
  kapsam kapısı: yeni katman sessizce giremez, silinen katman sessizce kalmaz).
- **K6** tüketici (globals.css/preview.html/landing_src.html) kanonik bir adı
  ÇIPLAK `:root`'ta farklı değerle gölgeliyor.

Fail-closed ölçüm: roster yok/bozuk, kanonik referans `canonical` değil,
ayrıştırılan tanımlar metindeki `--x: …;` çiftleriyle uyuşmuyor ya da tarama
kümesi boşsa **rc=2** (kör kapı PASS üretmez); bulgu varsa rc=1. Ölçüldü
(2026-10-13): 10 katman / 5.103 tanım / 5 kapsam · 0 bulgu · ~0,1s.
Yerelde `check-token-conflicts` pre-commit hook'u koşar; CI'da `verify`
işinin **Design-token drift & collision gate (fail-closed)** adımı bu kapıyı
contract 1-9, marka checker'ları, köprü kapısı ve Vercel drift raporuyla
birlikte BLOKE EDİCİ koşar (pre-commit zinciri CI'da advisory'dir — token
farkları orada merge'ü bloklamazdı). Test: `test_check_token_conflicts.py`
(23 sözleşme; her kural izole fixture'da kırmızıya düşürülür).

## Verification

```bash
python3 design-system/scripts/check_token_conflicts.py  # exit 0 = katmanlar arası drift/çakışma yok
python3 design-system/scripts/check_tokens.py      # exit 0 = in sync (contract 1-9)
python3 design-system/scripts/generate_tailwind.py # exit 0 = tailwind in sync
python3 design-system/scripts/report_vercel_dashboard_drift.py --check  # Vercel ↔ dashboard drift raporu
python3 design-system/stripe/scripts/generate_stripe_theme.py --check  # stripe varyantı
python3 design-system/vercel/scripts/generate_vercel_theme.py --check  # vercel adapter varyantı
python3 design-system/scripts/generate_mirror_tailwind.py --check  # 4 marka köprüsü
python3 design-system/scripts/check_mirror_bridges.py             # exit 0 = 4/4 PASS
```