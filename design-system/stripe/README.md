# design-system/stripe — Stripe HDS tokens (verbatim)

Extracted from the live marketing site **https://stripe.com** on 2026-09-08.

Values are copied **verbatim** — no remapping, no renaming, no rounding.

## Files

- `tokens.json` — structured HDS tokens (`--hds-*`), grouped by prefix (`color`, `space`, `font`, `shadow`, `canary`, …). Single source of truth for tooling. Includes `source` with page + exact asset URLs and extraction note.
- `tokens.css` — flat `:root` drop-in with all 710 HDS tokens grouped and sorted. `@import "design-system/stripe/tokens.css";` then use `var(--hds-…)` directly.
- `raw.css` — concatenated verbatim source stylesheets (478 kB) for audit/diff. Not for import — `tokens.css` is the curated `--hds-*` subset.
- `theme.css` — **GENERATED** tema varyantı: `:root[data-theme="stripe"]` altında
  repo semantik yuvalarını (`--bg`, `--fg`, `--accent`, `--paper`, `--border`, …)
  710 HDS token'ının bir alt kümesine bağlar. Elle düzenlemeyin.
- `scripts/generate_stripe_theme.py` — `theme.css`'i `tokens.css` aynasından
  üretir (`SLOT_MAP`, 32 yuva) + `--check` modu.

## Tema varyantı (`theme.css`)

Ayna token'ları doğrudan kullanıma hazırdır ama panonun/landing'in anladığı dil
repo semantik yuvalarıdır. Varyant bu iki dili bağlar: kaynakta hiçbir renk
literal'i yoktur, yalnız `var(--hds-*)` ve `color-mix(... var(--hds-*) ...)`.

```bash
python3 design-system/stripe/scripts/generate_stripe_theme.py         # yeniden üret
python3 design-system/stripe/scripts/generate_stripe_theme.py --check  # drift denetimi
# OK — stripe tema varyantı jeneratörle birebir (32 yuva, 24 HDS token)
```

- **Kapsam:** yalnız `:root[data-theme="stripe"]` bloğu; başka seçici yasak
  (kapsam sızıntısı = contract 9 FAIL). Koyu/açık varsayılanlar değişmez.
- **Yuvalar:** `SLOT_MAP` 32 yuva. `REQUIRED_SLOTS`'un tamamı çıktıda olmalı;
  eksik yuva üreticiyi `SystemExit` ile düşürür (sessiz kısmi varyant yok).
- **Değerler:** her yuva en az bir `var(--hds-*)` taşır (literal yasak) ve
  referans verdiği HDS ön-koşulları aynadan **birebir** kopyalanır
  (`closure()` ile `var()` transitif kapanışı; ör. `--accent` →
  `--hds-color-action-bg-solid` → `--hds-color-core-brand-600` = `#533afd`).
- **Pin:** varyanttaki HDS değerleri mirror'ın pinli `OK — 710` sayısıyla aynı
  `tokens.css`'ten gelir; upstream yenilenip mirror commit edilirse varyant da
  **aynı commit'te** yeniden üretilmelidir (`check-brand-mirrors` +
  `check-design-tokens` ikisi de drift'i yakalar).

### Tüketen yüzeyler

| Yüzey | Kullanım |
|---|---|
| `_calisma/CIKTI/preview.html` | `<link rel="stylesheet" href="/design-system/stripe-theme.css?v=1">` + tema döngüsü `dark → light → stripe` (`?theme=stripe`, `localStorage`) |
| `_calisma/CIKTI/preview_server.py` | `/design-system/stripe-theme.css` rotası (`PREVIEW_DIR/design-system-stripe-theme.css`; yoksa fail-closed 404) |
| `_calisma/landing/build_landing.py` | `--theme stripe` varyantı `<style>` olarak gömer ve `<html data-theme="stripe">` yazar (varsayılan `dark` çıktısı dokunulmaz) |

Kapsam içindeki yüzey kuralları da renk literali kullanamaz: contract 9
`preview.html`/`landing_src.html` içindeki `[data-theme="stripe"]` kurallarını
`var(` zorunluluğuyla tarar (arşiv panosu krema literallerinden arındırılır).

## Source

Page `https://stripe.com` (de-DE variant at fetch time) loads:

```
https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/5f8c822d1f0f2d3e.css   (2.7 kB)
https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/3194942a3bd6eca4.css (32 kB)
https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/f5d7a0708b41b5bf.css  (304 kB — main HDS)
https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/a1c84e4fb55f87e2.css  (61 kB)
https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/c3ca6e08b62a6ac3.css  (79 kB)
```

## Extraction

```bash
# All --*: value; assignments via regex /--[A-Za-z0-9_-]+\s*:\s*[^;{}]+;/
# on the concatenated stylesheets. First occurrence per name kept
# (light-mode :root); .hds-mode--dark overrides are not flattened.
python3 design-system/stripe/scripts/check_stripe_tokens.py   # drift gate
```

710 `--hds-*` tokens of 864 total `--*` assignments in the page.

Namespaces:

- `--hds-color-core-*` (107) — raw palette: `brand`/`brandDark`/`neutral`/`neutralDark`/`error`/`lemon`/`magenta`/`orange`/`ruby`/`success` (+ `A` alpha variants)
- `--hds-color-*` (324 remaps/util/accent/action/surface/input/shadow)
- `--hds-space-*` (91) — `core` scale `0–2500` (0–200px, 8px base), `layout`, `input`, `section`, `button`, `tab`, …
- `--hds-font-*` (116) — `family` (`sohne-var`, `SourceCodePro`), heading/text/quote/input groups with `size/weight/lineHeight/letterSpacing`
- `--hds-shadow-*` (45) — `xs/sm/md/lg/xl` + color tokens
- `--hds-color-util-*`, `--hds-canary-*`, `accordion`/`button`/`dialog`/`focus`/…

Dark mode lives in `.hds-mode--dark` — not flattened into `tokens.css`; compare `raw.css` for overrides.

## Using

```css
@import "design-system/stripe/tokens.css";
.card { background: var(--hds-color-surface-bg-quiet); color: var(--hds-color-text-solid); }
```

Fonts are not bundled — preload `Sohne`/`SourceCodePro` as the page does:

```html
<link rel="preload" href="https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/media/Sohne.cb178166.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/media/SourceCodePro-Medium.f5ba3e6a.woff2" as="font" type="font/woff2" crossorigin>
```

`--hds-font-family: "sohne-var","SF Pro Display",sans-serif` + `--hds-font-family-code: "SourceCodePro","SFMono-Regular",monospace`.

## Keeping in sync

Re-fetch the 5 assets, re-run the extractor in `tokens.json`'s `source.note`, diff `tokens.css`/`tokens.json` and `raw.css`.

## Verification

```bash
python3 design-system/stripe/scripts/check_stripe_tokens.py
# OK — 710 HDS tokens verbatim against raw.css
python3 design-system/stripe/scripts/generate_stripe_theme.py --check
# OK — stripe tema varyantı jeneratörle birebir (32 yuva, 24 HDS token)
python3 design-system/scripts/check_tokens.py       # contract 9: varyant + yüzeyler
# exit 0 = drift yok (elle düzenleme / literal / eksik yuva = FAIL)
```

Birim testleri: `_calisma/CIKTI/test_check_design_tokens.py`
