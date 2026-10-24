# design-system/github — GitHub homepage tokens (verbatim)

Extracted from the live homepage **https://github.com** in both color schemes:

- `raw.json` → `tokens.css` / `tokens.json` — **dark**, captured 2026-09-24.
- `raw.light.json` → `tokens.light.css` / `tokens.light.json` — **light**,
  captured 2026-10-11. GitHub serves dark to logged-out visitors and the
  extractor CLI exposes no light switch, so the light layer pins the page's
  `data-color-mode` attribute (see "Source and extraction").

Values are copied verbatim — no remapping, renaming, rounding, deduplication, or
cross-theme expansion.

> **Scope warning:** this is a runtime homepage capture, not the complete
> GitHub/Primer design system. The extractor exposed **304** computed custom
> properties in the dark layer and **258** in the light layer. They are preserved
> exactly, but both captures are partial: core Primer variables referenced by
> component styles, including `--bgColor-default` and `--fgColor-default`, are
> not present in `colors.cssVariables`. That is why each capture records its
> theme as `pageState` (measured read-back of `data-color-mode` plus those two
> variables) instead of relying on the token list.

## GitHub homepage vs Primer docs

`design-system/github/` and `design-system/primer/` are separate source
snapshots and must not be treated as interchangeable token layers:

- `github/` is a computed-DOM capture from `github.com` — 304 tokens in the
  dark layer and 258 in the light layer; no static stylesheet URLs were
  exposed.
- `primer/` is a 2,051-token light-mode extraction from 30 CSS chunks on
  `primer.style`.
- Their current snapshots share 289 custom-property names: 131 values match,
  while 158 differ because scope and theme differ.

**Do not import `github/tokens.css` and `primer/tokens.css` into the same
cascade.** They would collide on 289 names. Pick the source that matches the
consumer, or build an explicit adapter rather than relying on import order.

## Files

- `tokens.json` — structured, grouped canonical manifest. It contains all 304
  raw computed custom properties under their first namespace segment, plus
  capture provenance and count.
- `tokens.css` — flat `:root` drop-in containing the same 304 variables in
  deterministic namespace/name order.
- `raw.json` — lossless extractor output and audit source (dark). It also
  contains computed palette evidence, typography observations, spacing
  observations, borders, shadows, component samples, and observed widths.
- `raw.light.json` — the same schema and the same extraction code path for the
  light scheme, plus `theme`, `captureNote` and `pageState` provenance.
- `tokens.light.json` / `tokens.light.css` — the light canonical layer (258
  variables), generated from `raw.light.json` exactly like the dark pair.
- `scripts/check_github_tokens.py` — fail-closed checker and explicit `--sync`
  generator for **both** layers. Default mode is read-only. It refuses a light
  layer whose `pageState.dataColorMode` is not `light`, and refuses a light
  layer that does not differ from the dark one on at least one shared name.
- `scripts/capture_theme.mjs` — the capture entry point for either scheme
  (evidence tooling, not a repo runtime dependency).
- `scripts/report_theme_diff.py` — generates and `--check`s the systematic
  dark/light diff report (`_calisma/CIKTI/GITHUB_TEMA_FARK_RAPORU.md`).

The tool's `normalized.json` is intentionally not retained. It reduced the
capture to two opaque computed colors and an empty `cssVariables` map, so it
would not preserve the verbatim source contract.

## Gate coverage and bridge scope

`design-system/scripts/check_brand_mirrors.py` (pre-commit hook
`check-brand-mirrors`) runs `scripts/check_github_tokens.py` as a **pinned**
roster entry:

```
github  raw.json  258   scripts/check_github_tokens.py
```

The checker prints two `OK — N` lines (dark 304 + light 258) and the driver
pins the **last** count (258); `rc=0` is what proves *both* layers are in sync
with their `raw*.json`. A refresh therefore requires a deliberate pin update in
`brand_mirrors.list`, and a silent upstream change blocks the commit.

This mirror deliberately has **no Tailwind bridge** — `brand_mirrors.list`
carries `# no-bridge: github — …`. The bridge generator prefixes every
precondition with `<marka>-` (B3 in `check_mirror_bridges.py`), so a
single-layer bridge built from `tokens.css` would freeze these tokens to the
dark capture: the light layer (`tokens.light.css`, unprefixed `:root` names)
could not reach the prefixed preconditions. A bridge stays out of scope until
the two layers get an explicit adapter decision.

## Source and extraction

Page: `https://github.com/`

Tool flow:

```bash
npx --yes playwright install chromium
npx --yes extract-design-system@0.1.11 https://github.com --extract-only
```

The extractor writes `.extract-design-system/raw.json`. Promote that file to
`raw.json`, remove the tool-normalized layer, then regenerate the canonical
files:

```bash
python3 design-system/github/scripts/check_github_tokens.py --sync
```

The source record uses `npx extract-design-system@0.1.11`, dembrandt 0.7.0,
playwright-core 1.63.0, and Chrome Headless Shell 153. The exact capture time
and source URL are stored in both `raw.json` and `tokens.json`.

### Light capture (2026-10-11)

github.com renders `data-color-mode="dark"` for logged-out visitors. Measured
levers that did **not** switch it to light: `prefers-color-scheme: light`,
cookies (`color_mode`, `preferred_color_mode`), localStorage (`color-mode`,
`color_mode`, `github-color-mode`, `preferred-color-mode`) and query parameters
(`?color_mode=light`, `?colorMode=light`, `?theme=light`). The flag the page
actually honours is the attribute GitHub's own theme switcher writes:
`data-color-mode="light"` alone turns the *same* DOM/CSS snapshot into the light
theme (`--bgColor-default` `#0d1117` → `#fff`, `--fgColor-default` `#f0f6fc` →
`#1f2328`, same 1990 computed custom properties).

`scripts/capture_theme.mjs` therefore drives dembrandt's **own** extraction
function (`dembrandt/lib/extractors.js` `extractBranding` — the code path behind
`raw.json`) and only pins the theme attribute before/while the page boots:

```bash
mkdir -p /tmp/gh-capture && cd /tmp/gh-capture
npm install --no-save playwright@1.63.0 dembrandt@0.7.3   # one command: --no-save prunes
./node_modules/.bin/playwright install chromium          # Chrome Headless Shell 153
cp <repo>/design-system/github/scripts/capture_theme.mjs .
node capture_theme.mjs light raw.light.json
node capture_theme.mjs dark  raw.redark.json             # rule-identity check
```

Evidence for rule identity: re-capturing the *dark* scheme with this script
reproduced the committed `raw.json` exactly — 304/304 names with 304/304
identical values (2026-10-11). Two independent light runs produced the same
258/258 names and values. Each capture fails loudly (`exit 3`) when the read-back
`dataColorMode` is not the requested scheme, and writes `pageState`
(`dataColorMode`, `bgColorDefault`, `fgColorDefault`, `prefersDark`,
`computedCustomProperties`) into the raw file.

## Snapshot — dark layer (`raw.json`)

- 304 custom properties, all with distinct captured values.
- 23 namespace groups.
- Dark canvas observed by the extractor: `rgb(13, 17, 23)` / `#0d1117`.
- Dominant opaque computed colors: white `#fff` (1,525 uses),
  `#a4aea6` (194), and `#21262d` (26). Transparent black appears 19 times.
- Typography observations: Mona Sans (25), Mona Sans VF (8), and Mona Sans
  Mono (5).
- Four button variants were detected; three use a 6px radius and one uses a
  48px pill radius.

### Namespace inventory

| Namespace | Count | Namespace | Count |
|---|---:|---|---:|
| `base` | 82 | `brand` | 65 |
| `label` | 38 | `color` | 24 |
| `data` | 20 | `display` | 18 |
| `bgColor` | 11 | `contribution` | 7 |
| `button` | 6 | `diffBlob` | 6 |
| `buttonCounter` | 5 | `buttonKeybindingHint` | 5 |
| `prettylights` | 4 | `control` | 3 |
| `progressBar` | 2 | `reactionButton` | 2 |
| `avatar` | 1 | `codeMirror` | 1 |
| `header` | 1 | `highlight` | 1 |
| `overlay` | 1 | `selection` | 1 |

## Inferred design principles

These are evidence-based inferences from one dark homepage snapshot, not
claims about GitHub's complete internal guidelines. The token files remain
verbatim; only this section interprets them.

### 1. Separate primitives, semantic roles, and component states

**Evidence:** 82 `base-*` primitives sit beside semantic groups such as
`bgColor-*`, `data-*`, `display-*`, `label-*`, and component/state groups such
as `button-*`, `control-*`, `diffBlob-*`, and `prettylights-*`.

**Principle:** keep raw palette values separate from product meaning. Product
UI should normally consume semantic or component roles; primitives exist to
support those roles, not to replace them.

### 2. Make interaction states explicit

**Evidence:** button, label, and control tokens encode `rest`, `hover`,
`active`, `disabled`, `muted`, `subtle`, and `emphasis` variants. The checked
control progression is `#1f6feb → #2a7aef → #3685f3`.

**Principle:** interaction feedback is designed as a state machine rather
than an ad-hoc hover color. Every interactive primitive should define visible
rest, hover, active, focus, and disabled behavior.

### 3. Build dark surfaces with layers and translucency

**Evidence:** the page background is `#0d1117`; the captured header surface is
`#151b23f2`, the overlay backdrop is `#21283066`, and many secondary states use
8-digit hex alpha values. Captured buttons use little or no box shadow.

**Principle:** depth comes from surface tone, borders, and translucent fills
before heavy shadows. This suits dense product UI and keeps controls legible
without a pronounced elevation stack.

### 4. Keep the product core stable and express brand separately

**Evidence:** 65 `brand-*` tokens cover gradients, labels, testimonials,
pricing, logo/video treatments, and text-cursor effects alongside the more
restrained product palette.

**Principle:** expressive brand moments belong in a separate semantic layer.
They can be rich and playful without leaking into generic controls, status
colors, or developer-facing content.

### 5. Optimize typography for dense developer workflows

**Evidence:** 14px and 16px are the most common observed sizes (23 of 38 type
samples); 27 of 38 use a 1.5 line height. Buttons and links commonly use weight
500, while display samples range from 425 to 800. Mona Sans Mono appears in
technical/caption contexts.

**Principle:** use a compact UI type scale for controls and body content, a
stronger display range for marketing hierarchy, and monospace only where
technical alignment or code semantics require it.

### 6. Use an 8px rhythm with a 4px half-step

**Evidence:** the extractor reports an 8px scale type. Common structural values
include 4, 8, 16, 24, 32, 48, 64, and 96px, with 6, 10, 20, 40, and 80px as
secondary steps.

**Principle:** prefer a small, regular spacing scale over promoting every
observed pixel value to a token. The frequently observed 2.1px and 2.4px values
also include typography tracking and should not be mistaken for spacing steps.

### 7. Use restrained geometry and elevation

**Evidence:** three of four sampled button variants use a 6px radius; the
remaining variant is a 48px pill. Borders are commonly 1px, often with low-alpha
white or neutral colors. Shadows are sparse and mostly reserved for overlays.

**Principle:** default controls need a compact 6px silhouette; pills are an
intentional variant. Use thin borders and shallow overlays before adding shadow.

### 8. Treat focus as a first-class visual state

**Evidence:** captured component states use a 2px focus outline, with
`--focus-outlineColor` and `--brand-color-focus` participating in the state
model.

**Principle:** keyboard focus should be explicit, high-contrast, and consistent
across controls. This capture provides focus evidence but no contrast audit;
WCAG conformance must be verified separately.

### 9. Adapt progressively across a wide viewport range

**Evidence:** observed widths span 320px to 1728px. Adjacent observed pairs at
543/544, 767/768, 875/876, 1011/1012, and 1279/1280px signal likely layout
boundaries; 320, 400, 600, 800, 1200, and 1600px are additional observed
container/viewport widths.

**Principle:** use a small set of major responsive transitions rather than a
new breakpoint for every component. The raw list is observational evidence,
not a canonical breakpoint token set.

## Typography observations

| Evidence | Observation |
|---|---|
| Families | Mona Sans, Mona Sans VF, Mona Sans Mono |
| Common UI sizes | 14px and 16px |
| Display sizes | 18, 22, 24, 40, 48, and 64px |
| Common line height | 1.5 |
| Common UI weights | 400 and 500; 600 for stronger actions/headings |
| Display weights | observed variable values from 425 through 800 |

Fonts are not bundled. Consumers must provide Mona Sans and Mona Sans Mono or
use their own fallback stack.

## Snapshot — light layer (`raw.light.json`)

- 258 custom properties, all with distinct captured values; 23 namespace
  groups.
- `pageState`: `dataColorMode` `light`, canvas `#fff`, ink `#1f2328`, 1990
  computed custom properties on the captured page.
- Element-census palette is nearly theme-invariant (white `#ffffff` 1528 uses vs
  1525 in dark; `#a4aea6` 194 vs 194; `#21262d` 26 vs 26) — the theme signal
  lives in `colors.cssVariables`, not in the palette census. The report derives
  this comparison; do not read theme differences out of the palette table alone.

## Using the capture

```css
/* dark layer */
@import "design-system/github/tokens.css";

/* or the light layer — pick ONE per cascade */
@import "design-system/github/tokens.light.css";

.attention {
  color: var(--brand-color-text-emphasized);
  background: var(--bgColor-attention-muted);
}
```

Both are partial runtime snapshots. Do not treat missing variables as evidence
that GitHub does not support the other theme, full typography, motion, or the
complete Primer API. Do not co-import either layer with the Primer provider.

**Do not import `tokens.css` and `tokens.light.css` into the same cascade.**
The two captures share 208 names and **195 of them carry different values**
(only 13 match); 96 names exist only in dark and 50 only in light, so an import
order would silently decide which theme wins and which tokens disappear. Pick the
layer that matches the consumer, or build an explicit adapter with per-mapping
justification. The measured breakdown, including the full differing-value table
and the `base-color-scale-*` structural shift, is in
`_calisma/CIKTI/GITHUB_TEMA_FARK_RAPORU.md` (generated by
`scripts/report_theme_diff.py`).

## Keeping in sync

1. Re-run the same extractor command from `design-system/github/` for the dark
   layer, or `scripts/capture_theme.mjs` for either scheme.
2. Replace `raw.json` (dark) or `raw.light.json` (light) with the new capture.
3. Run `python3 design-system/github/scripts/check_github_tokens.py --sync` to
   regenerate the canonical pair for **both** layers from their raw sources.
4. Regenerate `_calisma/CIKTI/GITHUB_TEMA_FARK_RAPORU.md` (same script family:
   `report_theme_diff.py`) so the diff report matches the new captures.
5. Review scope/theme changes and update the evidence in this README; do not
   silently turn newly observed values into additional canonical layers.
6. Commit the raw captures and the generated canonical files together.

## Verification

```bash
python3 design-system/github/scripts/check_github_tokens.py
# OK — 304 GitHub tokens verified against raw.json (tokens.css + tokens.json in sync)
# OK — 258 GitHub light tokens verified against raw.light.json (tokens.light.css + tokens.light.json in sync)
python3 design-system/github/scripts/report_theme_diff.py --check
# OK — GitHub tema fark raporu iki yakalamayla birebir (_calisma/CIKTI/GITHUB_TEMA_FARK_RAPORU.md)
```

The checker fails closed on missing, extra, changed, duplicated, unsorted, or
wrongly grouped tokens, canonical count/provenance drift, a light layer whose
`pageState.dataColorMode` is not `light`, and a light layer that repeats the
dark values instead of differing from them.
