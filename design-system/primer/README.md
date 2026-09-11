# design-system/primer — GitHub Primer tokens (verbatim)

Extracted from the live docs site **https://primer.style** on 2026-09-08.

Values are copied **verbatim** — no remapping, no renaming, no rounding.

## Files

- `tokens.json` — structured tokens, grouped by first segment (`base`, `brand`, `bgColor`, `fgColor`, `borderColor`, `control`, `button`, `text`, …). Single source of truth for tooling. Includes `source` with page + exact asset URLs and extraction note.
- `tokens.css` — flat `:root` drop-in with all 2051 tokens grouped and sorted. `@import "design-system/primer/tokens.css";` then use `var(--…)` directly.
- `raw.css` — concatenated verbatim source stylesheets (1.2 MB, 30 `_next/static/chunks/*.css` files) for audit/diff. Not for import — `tokens.css` is the curated subset.

## Source

Page `https://primer.style` (light theme, `data-color-mode="light"`) loads 30 hashed chunks:

```
https://primer.style/_next/static/chunks/<hash>.css  ×30  (1,228,360 bytes total)
```

Canonical package is `@primer/primitives` + `@primer/brand` — the site bundles their compiled `--base-*` / `--brand-*` / `--bgColor-*` etc. CSS vars into those chunks. This extraction captures the **rendered site's computed vars**, not the npm package's source layout.

## Extraction

```bash
# All --*: value; assignments via regex /--[A-Za-z0-9_-]+\s*:\s*[^;{}]+;/
# on the concatenated stylesheets. First occurrence per name kept
# (light-mode value where duplicated); dark-mode overrides ([data-color-mode=dark]) not flattened.
python3 design-system/primer/scripts/check_primer_tokens.py   # drift gate
```

2051 unique `--*` of which ~2051 are kept (light-mode first occurrence).

Notable namespaces (size-sorted):

- `brand` (657) — `--brand-color-*`, `--brand-text-*`, `--brand-fontStack-*`, layout/spacing for marketing UI
- `display` (285) — `--display-*` responsive type scale (brand)
- `base` (202) — primitives: `--base-color-scale-*` (gray/blue/green/yellow/orange/red/purple… 0–9), `--base-size-*` (2–128), `--base-text-*`
- `label` (138) — label tokens
- `control` (71), `button` (68), `bgColor`/`fgColor`/`borderColor` (33/20/30), `text` (40), `prettylights` (42), `ansi` (17), …

Raw palette sample (verbatim):

```
--base-color-scale-gray-0: #f2f5f3   --base-color-scale-blue-5: #0377ff
--bgColor-accent-emphasis: #1f6feb   --fgColor-accent: #4493f8
--borderWidth-thin: .0625rem         --text-body-size-medium: var(--base-text-size-sm)
```

Dark mode lives in `[data-color-mode=dark]` — not flattened into `tokens.css`; compare `raw.css` for overrides.

## Using

```css
@import "design-system/primer/tokens.css";
.card { background: var(--bgColor-default); color: var(--fgColor-default); border: 1px solid var(--borderColor-default); }
.hero { font-family: var(--brand-fontStack-sans); }
```

`--brand-fontStack-*` expects `Mona Sans` / `Hubot Sans` — preload as the page does (MonaSansVF, Hubot-Sans woff2).

## Keeping in sync

Re-fetch the 30 chunk URLs from the live page (they are content-hashed, so URLs change on deploy), re-run the extractor in `tokens.json`'s `source.note`, diff `tokens.css`/`tokens.json` and `raw.css`.

## Verification

```bash
python3 design-system/primer/scripts/check_primer_tokens.py
# OK — 2051 tokens verbatim against raw.css
```
