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
  value appear verbatim in the source).
- `scripts/generate_tailwind.py` — renders `tailwind.css` from `tokens.css`.
  No `tailwindcss` install needed to generate; validates the two `:root`
  blocks stay byte-identical.

## Keeping in sync

When `preview.html`'s `:root` (or the inline styles) change, update
`tokens.json` first, then `tokens.css`, then regenerate `tailwind.css`:

```bash
python3 design-system/scripts/check_tokens.py      # HTML → tokens.css drift
python3 design-system/scripts/generate_tailwind.py # tokens.css → tailwind.css
```

Both must exit `0`. Commit `tokens.json` + `tokens.css` + `tailwind.css`
 together so the three files never drift.

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
| `text-2xs` … `text-xl` / `leading-tight` / `tracking-caps` | font-size / line-height / letter-spacing |
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

## Verification

```bash
python3 design-system/scripts/check_tokens.py      # exit 0 = in sync
python3 design-system/scripts/generate_tailwind.py # exit 0 = tailwind in sync
```