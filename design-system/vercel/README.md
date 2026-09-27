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

`tokens.css` is the only file needed at runtime. Import it once in the global
stylesheet, then reference the original custom-property names:

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

With Tailwind, use arbitrary values such as
`text-[var(--develop-text)]` and `bg-[var(--color-background-100)]`. Do not
copy values from `raw.json` at runtime or rename the variables. The capture is
color-only: load **GeistSans / Geist Mono** separately if the consuming project
needs them, or use platform fallbacks.

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

## Verification

```bash
python3 design-system/vercel/scripts/check_vercel_tokens.py
# OK — 19 Vercel tokens verbatim against raw.json (tokens.css + tokens.json in sync)
python3 design-system/scripts/generate_mirror_tailwind.py --check
# OK — 4/4 marka köprüsü jeneratörle birebir (… vercel 19/19 yuva …)
```
