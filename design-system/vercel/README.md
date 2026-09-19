# design-system/vercel — Vercel (vercel.com) tokens (starter + verbatim)

Extracted from the live homepage **https://vercel.com** on 2026-09-18
(light theme).

**Scope warning:** this is a **partial** extraction. Unlike Linear/Stripe,
Vercel inlines most of its styling and ships few custom properties to
computed style — the homepage exposes only **19** `--*` variables. Treat
this folder as initialization material, not the full Vercel design system
(Geist).

## Files

- `tokens.verbatim.css` / `tokens.verbatim.json` — verbatim layer: the 19
  CSS variables the page actually exposed (`--color-gray-*` scale,
  ship/develop/preview accent triad, geist console/selection, ds focus),
  copied without remapping/renaming/rounding. JSON adds provenance,
  count-ranked palette and derived typography/spacing/radius/shadow
  summaries from the tool's raw capture.
- `tokens.starter.css` / `tokens.starter.json` — **unmodified** output of
  `npx extract-design-system@0.1.11 init` (tool-normalized layer: 2
  semantic colors, GeistSans, 15-step space scale; no radius/shadow).
  Kept verbatim as tool evidence.
- `raw.json` — the tool's full raw capture (29 kB: computed palette with
  counts, typography styles, borders, shadows, buttons/links, breakpoints,
  framework hints). Audit source for the two layers above.
- `normalized.json` — the tool's summary layer (input that `init` consumed).

## Source

Page `https://vercel.com/` via Chrome Headless Shell 153
(`playwright-core 1.63.0`, through `dembrandt 0.7.0` /
`extract-design-system 0.1.11`). No static CSS chunk URLs were captured —
the verbatim values come from `getComputedStyle` on the live DOM
(`raw.json → colors.cssVariables`).

Notable verbatim values:

```
--color-gray-1000: hsla(0, 0%, 9%, 1)     --ship-text: #ff5b4f
--color-background-100: hsla(0, 0%, 100%, 1)  --develop-text: #0a72ef
--geist-console-text-color-blue: #0070f3  --preview-text: #de1d8d
--ds-focus-color: hsla(212, 100%, 48%, 1) --color-gray-alpha-400: #00000014
```

Palette by computed-style count: `#ebebeb` (537×, dividers) · `#171717`
(301×, ink) · `#4d4d4d` (186×) · `#8f8f8f` (28×) · `#ffffff` (22×).

Typography: **GeistSans** (headings 64px/1.00/−3.84px w400; body 16px/1.50)
+ **Geist Mono** (uppercase captions). Spacing hugs a 2/6/8/12/16/24px core;
radius scale is **6px dominant** with 4/8/12 and 128px pills; borders are
1px `#ebebeb` / `rgba(0,0,0,0.08)`; shadows are mostly 1px rings plus
layered elevation on cards.

## Extraction

```bash
npx playwright install chromium   # tool's playwright needs its own build
npx extract-design-system https://vercel.com --extract-only
npx extract-design-system init    # starter files from .extract-design-system/
```

## Using

```css
@import "design-system/vercel/tokens.verbatim.css";
.ink   { color: var(--color-gray-1000); }
.link  { color: var(--geist-console-text-color-blue); } /* #0070f3 */
.accent{ color: var(--ship-text); }                      /* #ff5b4f */
```

Fonts expect **GeistSans / Geist Mono** (Vercel's own Geist family — load
via your font pipeline; fallbacks are plain system stacks).

## Limits (explicit)

- Homepage is a single page — this is **not** proof of the whole product
  design system (app surfaces use Geist's full token set, not exposed here).
- The tool's semantic "primary/secondary" colors are trivial
  (white/transparent) — use the verbatim layer, not `starter`'s semantic
  pair.
- `3.35544e+07px` radius values in raw.json are Tailwind `rounded-full`
  artifacts, not a real token.
- Framework hints in raw.json (PrimeReact/Fluent counts) are class-name
  heuristics; Vercel is Next.js + Tailwind.

## Keeping in sync

Re-run the extraction commands above on a deploy that changes the homepage
(Vercel ships content-hashed assets; values may drift), then diff
`tokens.verbatim.*` against the new `raw.json`.
