#!/usr/bin/env python3
"""generate_tailwind.py — render design-system/tailwind.css from tokens.css.

The Tailwind v4 `@theme` block must stay in sync with tokens.css.
This is the single generator — edit tokens.json → tokens.css, run this,
commit both. stdlib-only, no tailwind install needed to generate.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
TOKENS_CSS = REPO / "design-system" / "tokens.css"
TAILWIND_CSS = REPO / "design-system" / "tailwind.css"

HEADER = """/*
 * design-system/tailwind.css — Tailwind CSS v4 theme bridge for the
 * dashboard tokens (design-system/tokens.json → tokens.css).
 *
 * This file is GENERATED from tokens.css (see scripts/generate_tailwind.py).
 * Do not edit by hand — run `python3 design-system/scripts/generate_tailwind.py`
 * after changing tokens.json/tokens.css and commit both files together.
 *
 * Usage (Tailwind v4, no tailwind.config.js):
 *   @import "tailwindcss";
 *   @import "./design-system/tailwind.css";
 *
 * The :root vars are the same values preview.html already consumes (no
 * extra runtime cost). The @theme block re-exposes them as Tailwind v4
 * theme variables so utilities like `bg-bg`, `text-fg`, `border-border`,
 * `rounded-6`, `p-6`, `animate-pulse`, etc. resolve to the dashboard
 * palette without a tailwind.config.js.
 *
 * Legacy aliases (--surface, --surface-raised, --header-*, --code-bg,
 * --paper) are kept verbatim so existing var(--surface) references work
 * in both the static dashboard and Tailwind utilities.
 */

@import "tailwindcss";
"""


def render() -> str:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    dark_m = re.search(r":root\s*\{.*?\}", css, re.S)
    light_m = re.search(r':root\[data-theme="light"\]\s*\{.*?\}', css, re.S)
    if not dark_m or not light_m:
        print("missing :root blocks in tokens.css", file=sys.stderr)
        sys.exit(1)

    dark_vars = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", dark_m.group(0)))

    # Group for readable @theme output (sorted within each group).
    groups: list[tuple[str, list[str]]] = [
        ("color", []),
        ("font", []),
        ("text", []),
        ("radius", []),
        ("spacing", []),
        ("animate / ease / container", []),
        ("layout (grid)", []),
    ]
    group_idx = {
        "color": 0, "font": 1, "text": 2, "radius": 3, "spacing": 4,
        "animate": 5, "layout": 6,
    }

    def add(group: str, line: str):
        groups[group_idx[group]][1].append(line)

    for name in sorted(dark_vars):
        val = dark_vars[name].strip()
        # Skip composition vars (multi-token `var(--...)` indirections) — they
        # live in :root for the static page but don't need a @theme alias
        # (Tailwind would see `var(--space-1) var(--space-4)` as invalid theme value).
        # Keep literal shadows like --shadow-tip "0 8px ..." — they are valid theme values.
        if val.startswith("var(") or ("var(" in val and " " in val):
            continue
        if name in ("--bg", "--fg", "--muted", "--accent", "--ok", "--warn", "--err",
                    "--border", "--budget", "--surface-1", "--surface-2", "--on-accent",
                    "--surface", "--surface-raised", "--header-start", "--header-end",
                    "--code-bg", "--paper", "--paper-ink") or name.startswith("--tint-") or name in ("--shadow-tip", "--backdrop-lightbox"):
            tw = "--color-" + name[2:]
            # --shadow-tip is "0 8px 24px rgba(...)" — Tailwind shadow token
            if name == "--shadow-tip":
                tw = "--shadow-tip"
            elif name == "--backdrop-lightbox":
                tw = "--color-backdrop-lightbox"
            add("color", f"  {tw}: var({name});")
        elif name in ("--font-sans", "--font-mono"):
            add("font", f"  {name}: var({name});")
        elif name.startswith("--text-"):
            add("text", f"  {name}: var({name});")
        elif name in ("--lh-base", "--lh-tight"):
            # Tailwind v4 canonical is --leading-* ; keep --lh-* alias for var(--lh-*) compat
            tw = name.replace("--lh-", "--leading-")
            add("text", f"  {tw}: var({name});")
            add("text", f"  {name}: var({name});")
        elif name == "--ls-caps":
            add("text", f"  --tracking-caps: var({name});")
            add("text", f"  {name}: var({name});")
        elif name.startswith("--radius-"):
            add("radius", f"  {name}: var({name});")
        elif name.startswith("--space-"):
            tw = name.replace("--space-", "--spacing-")
            add("spacing", f"  {tw}: var({name});")
        elif name.startswith("--ease"):
            add("animate", f"  {name}: var({name});")
        elif name.startswith("--dur-"):
            # Custom duration tokens — expose verbatim for var(--dur-*) and as --ease alias
            # so Tailwind's animation utilities can reference them if needed.
            add("animate", f"  {name}: var({name});")
        elif name.startswith("--main-"):
            add("animate", f"  --container-main: var({name});")
        elif name.startswith("--grid-") or name.startswith("--z3-"):
            add("layout", f"  {name}: var({name});")

    # Explicit derived animation shorthands (Tailwind v4 --animate-*)
    add("animate", "  --animate-pulse: pulse var(--dur-pulse) infinite;")
    add("animate", "  --animate-shake: failShake var(--dur-shake) var(--ease-in-out) 3;")
    add("animate", "  --animate-glow: failGlow var(--dur-glow) var(--ease-in-out) infinite;")

    # Deduplicate
    seen: set[str] = set()
    theme_parts: list[str] = []
    for title, lines in groups:
        if not lines:
            continue
        deduped = []
        for ln in sorted(set(lines)):
            key = ln.split(":")[0].strip()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ln)
        if deduped:
            theme_parts.append(f"  /* ── {title} ── */")
            theme_parts.extend(deduped)

    return (
        HEADER
        + "\n"
        + dark_m.group(0) + "\n\n"
        + light_m.group(0) + "\n\n"
        + "@theme {\n"
        + "\n".join(theme_parts) + "\n"
        + "}\n"
    )


def main() -> int:
    out = render()
    TAILWIND_CSS.write_text(out, encoding="utf-8")
    print(f"Wrote {TAILWIND_CSS} ({len(out)} bytes)")
    css = TOKENS_CSS.read_text(encoding="utf-8")
    tw = TAILWIND_CSS.read_text(encoding="utf-8")
    for pat in (r":root\s*\{.*?\}", r':root\[data-theme="light"\]\s*\{.*?\}'):
        a = re.search(pat, css, re.S).group(0)
        b = re.search(pat, tw, re.S).group(0)
        if a != b:
            print(f"DRIFT: {pat} differs between tokens.css and tailwind.css — regenerate", file=sys.stderr)
            return 1
    print("OK — tailwind.css :root blocks match tokens.css verbatim; @theme bridges Tailwind v4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
