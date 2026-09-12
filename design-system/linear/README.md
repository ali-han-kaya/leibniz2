# design-system/linear — Linear (linear.app) tokens (verbatim)

Extracted from the live marketing site **https://linear.app** on 2026-09-08.

Values are copied **verbatim** — no remapping, no renaming, no rounding.

## Files

- `tokens.json` — structured tokens, grouped by first segment (`color`, `title`, `text`, `font`, `radius`, `ease`, `layer`, `editor`, …). Single source of truth for tooling. Includes `source` with page + exact asset URLs and extraction note.
- `tokens.css` — flat `:root` drop-in with all 398 tokens grouped and sorted. `@import "design-system/linear/tokens.css";` then use `var(--…)` directly.
- `raw.css` — concatenated verbatim source stylesheets (335 kB, 54 `static.linear.app/web/_next/static/css/*.css` files) for audit/diff. Not for import — `tokens.css` is the curated subset (internal `--sx-*` excluded).

## Source

Page `https://linear.app` (dark theme, `data-theme="dark"`) loads:

```
https://static.linear.app/web/_next/static/css/*.css  ×54  (335,138 bytes total)
```

Linear uses `styled-components` — the page also injects transient `--sx-*` hashed vars at runtime; those are excluded (138 removed) as implementation artifacts, not design tokens. The curated 398 are the stable design system.

## Extraction

```bash
# All --*: value; assignments via regex /--[A-Za-z0-9_-]+\s*:\s*[^;{}]+;/
# on the concatenated stylesheets. First occurrence per name kept
# (dark theme where the page was fetched); internal --sx-* excluded.
python3 design-system/linear/scripts/check_linear_tokens.py   # drift gate
```

536 ` --*` assignments total → 398 kept after `--sx-*` filter.

Notable namespaces (size-sorted):

- `color` (58) — `--color-bg-*` (level 0–3, marketing/panel/quinary), `--color-fg-*` (primary/secondary/tertiary/quaternary), `--color-border-*`, `--color-brand-bg: #5e6ad2`, `--color-accent: #7170ff`, line/border tints (`#ffffff0d`, `#ffffff14`)
- `title` (36) — `--title-1…9` composite (`var(--font-weight-semibold) var(--title-N-size) / var(--title-N-line-height) var(--font-regular)`), each with `size`/`line-height`/`letter-spacing` (9: `4.5rem / 1 / -.022em` down to 1: `1.0625rem / 1.4 / -.012em`)
- `font` (24) — `--font-regular: "Inter Variable", "SF Pro Display", …`, `--font-monospace: "Berkeley Mono"`, `--font-serif-display: "Tiempos Headline"`, weights `300/400/510/590/680`, sizes `micro…title1–3`
- `text` (24) — `--text-micro…large` composites + `size`/`line-height`/`letter-spacing` (e.g. `regular: .9375rem / 1.6 / -.011em`)
- `editor` (18) — block spacing/radius/list inset
- `ease` (18) — `in/out/inOut` × `quad/cubic/quart/quint/expo/circ` `cubic-bezier(...)`
- `layer` (17) — `debug 11000` down to `1` (`header 100`, `tooltip 1100`, `dialog 700`)
- `radius` (9) — `4/6/8/12/16/24/…9999px`, `bg` (2), `graph`/`scrollbar`/`page`/`button`/…

Raw palette sample (verbatim, dark):

```
--color-bg-primary: #08090a     --color-bg-marketing: #010102
--color-brand-bg: #5e6ad2       --color-accent: #7170ff
--font-size-regular: 1rem       --title-8-size: 4rem / 1.06 / -.022em
--radius-12: 12px               --ease-in-quad: cubic-bezier(.55,.085,.68,.53)
--layer-header: 100
```

## Using

```css
@import "design-system/linear/tokens.css";
.card { background: var(--color-bg-secondary); color: var(--color-fg-primary); border: 1px solid var(--color-border-tertiary); border-radius: var(--radius-12); }
.hero { font: var(--title-8); } /* 4rem / 1.06 Inter */
```

Fonts expect `Inter Variable` / `Tiempos Headline` / `Berkeley Mono` — preload as the page does.

## Keeping in sync

Re-fetch the 54 chunk URLs from the live page (they are content-hashed, so URLs change on deploy), re-run the extractor in `tokens.json`'s `source.note`, diff `tokens.css`/`tokens.json` and `raw.css`.

## Verification

```bash
python3 design-system/linear/scripts/check_linear_tokens.py
# OK — 398 Linear tokens verbatim against raw.css
```
