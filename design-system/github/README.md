# design-system/github — GitHub homepage tokens (verbatim)

Extracted from the live homepage **https://github.com** on 2026-09-24 in the
**dark color scheme**. Values are copied verbatim — no remapping, renaming,
rounding, deduplication, or light-theme expansion.

> **Scope warning:** this is a runtime homepage capture, not the complete
> GitHub/Primer design system. The extractor exposed **304** computed custom
> properties. They are preserved exactly, but the capture is partial: core
> Primer variables referenced by component styles, including
> `--bgColor-default` and `--fgColor-default`, are not present in
> `colors.cssVariables`.

## GitHub homepage vs Primer docs

`design-system/github/` and `design-system/primer/` are separate source
snapshots and must not be treated as interchangeable token layers:

- `github/` is a 304-token dark-mode computed-DOM capture from
  `github.com`; no static stylesheet URLs were exposed.
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
- `raw.json` — lossless extractor output and audit source. It also contains
  computed palette evidence, typography observations, spacing observations,
  borders, shadows, component samples, and observed widths.
- `scripts/check_github_tokens.py` — fail-closed checker and explicit `--sync`
  generator. Default mode is read-only.
- `sample.html` — a larger local specimen composed from the GitHub capture;
  it demonstrates surfaces, controls, states, syntax, brand moments, and
  responsive density without changing any captured value.
- `scripts/check_github_primer_sample.py` — fail-closed cross-check for the
  specimen. It verifies the GitHub-only stylesheet boundary, the Primer
  comparison table, and the expected 304/2,051-token overlap metrics.

The tool's `normalized.json` is intentionally not retained. It reduced the
capture to two opaque computed colors and an empty `cssVariables` map, so it
would not preserve the verbatim source contract.

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

## Snapshot

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

## Using the capture

```css
@import "design-system/github/tokens.css";

.attention {
  color: var(--brand-color-text-emphasized);
  background: var(--bgColor-attention-muted);
}
```

This is a dark, partial runtime snapshot. Do not treat missing variables as
evidence that GitHub does not support light mode, full typography, motion, or
the complete Primer API. Do not co-import it with the Primer provider.

## Site specimen and Primer cross-check

Open `sample.html` as a local, dark-theme site study. It imports only
`./tokens.css`; the Primer snapshot is intentionally not loaded into the
same cascade. The page uses the GitHub capture for its product-like surfaces,
button states, labels, syntax signals, brand gradients, and responsive
composition. The `--sample-*` variables are page-local composition helpers,
not a second token provider.

The cross-validation table is deliberately explicit. Its five rows are checked
against both manifests: four exact values and one scope/theme difference. The
checker also recomputes the full overlap instead of trusting the table's
summary. Run it from the repository root:

```bash
python3 design-system/github/scripts/check_github_primer_sample.py
# OK — specimen uses 41 GitHub tokens and Primer remains comparison-only
# OK — crosswalk verified: 5 rows (4 exact, 1 different); GitHub 304 / Primer 2051 / common 289 / GitHub-only 15 / Primer-only 1762
```

This is a comparison gate, not an adapter. If a provider capture changes,
update the canonical manifests and review the specimen's displayed values
before changing the expected evidence.

## Keeping in sync

1. Re-run the same extractor command from `design-system/github/`.
2. Replace `raw.json` with the new `.extract-design-system/raw.json` capture.
3. Run `python3 design-system/github/scripts/check_github_tokens.py --sync` to
   regenerate `tokens.json` and `tokens.css` from the new source.
4. Review scope/theme changes and update the evidence in this README; do not
   silently turn newly observed values into additional canonical layers.
5. Commit the raw capture and both generated canonical files together.

## Verification

```bash
python3 design-system/github/scripts/check_github_tokens.py
# OK — 304 GitHub tokens verified against raw.json (tokens.css + tokens.json in sync)
```

The checker fails closed on missing, extra, changed, duplicated, unsorted, or
wrongly grouped tokens, and on canonical count/provenance drift.
