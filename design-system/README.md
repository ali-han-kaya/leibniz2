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
  almalı ve uygulama kaynağı preset-only yüzey
  (`data-open:`/`no-scrollbar`/`scroll-fade`/`shimmer`) kullanamaz. Contract 9
  ise Stripe HDS tema varyantını denetler: `stripe/theme.css` üreticinin
  (`stripe/scripts/generate_stripe_theme.py`) `render()` çıktısıyla **birebir**
  olmalı, yalnız `:root[data-theme="stripe"]` bloğu taşımalı, 32 yuvanın
  tamamını içermeli, HDS ön-koşulları aynayla aynı olmalı ve yuva değerlerinde
  renk literali bulunmamalı; ayrıca varyantı tüketen yüzeylerdeki
  (`preview.html`, `landing/landing_src.html`) `[data-theme="stripe"]`
  kurallarında her değer `var(` taşımalı.
- `stripe/theme.css` — **Generated** Stripe HDS tema varyantı: repo semantik
  yuvalarını (`--bg`, `--fg`, `--accent`, `--border`, `--paper`, …) mirror'daki
  `--hds-*` token'larına bağlar. Kaynak: `stripe/README.md` ("Tema varyantı").
  `python3 design-system/stripe/scripts/generate_stripe_theme.py` ile üretilir;
  elle düzenleme drift sayılır (contract 9).
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
  `github  raw.json  304  scripts/check_github_tokens.py` satırını ekleyin.
- Birim testleri: `_calisma/CIKTI/test_brand_mirror_gate.py` (R1-R5 + hook
  wiring; `check-unit-tests` bataryasında koşar).

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
python3 design-system/scripts/check_tokens.py      # exit 0 = in sync (contract 1-9)
python3 design-system/scripts/generate_tailwind.py # exit 0 = tailwind in sync
python3 design-system/stripe/scripts/generate_stripe_theme.py --check  # stripe varyantı
```