#!/usr/bin/env python3
"""check_tokens.py — verify design-system tokens match the dashboard.

Contracts (post-import):
1. preview.html must import design-system/tokens.css (link or @import).
2. Every custom property in tokens.css :root (dark) + [data-theme="light"]
   block appears verbatim in either the imported sheet or the HTML.
3. Every rgba tint in tokens.json must be resolvable via the token sheet
   (values kept verbatim — checked against tokens.css, not duplicated HTML).
4. The HTML must not contain a duplicate inline :root var block that would
   shadow the import (drift — two sources of truth).

Exit 0 on match, 1 on drift.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HTML = REPO / "_calisma" / "CIKTI" / "preview.html"
CSS = REPO / "design-system" / "tokens.css"


def vars_in_block(text: str, selector_pat: str) -> dict:
    m = re.search(selector_pat + r"\s*\{(.*?)\}", text, re.S)
    if not m:
        return {}
    return {n: v.strip() for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1))}


def main() -> int:
    html_text = HTML.read_text(encoding="utf-8")
    css_text = CSS.read_text(encoding="utf-8")

    drift = []

    # 1. import present
    has_link = bool(re.search(r'<link[^>]+href=["\'][^"\']*design-system/tokens\.css["\']', html_text))
    has_import = "design-system/tokens.css" in html_text
    if not (has_link or has_import):
        drift.append("preview.html does not import design-system/tokens.css (expected <link> or @import)")

    # Guard: no stray inline :root var block shadowing the import
    # Inline :root that defines --bg/--surface is now the single source in tokens.css
    inline_root = re.search(r"<style>.*?:root\s*\{[^}]*--bg\s*:", html_text, re.S)
    if inline_root:
        drift.append("preview.html contains an inline :root { --bg ... } block that shadows the imported tokens.css — keep vars in one place")

    # 2. tokens.css must contain both dark :root and light override
    css_dark = vars_in_block(css_text, r":root")
    css_light = vars_in_block(css_text, r':root\[data-theme="light"\]')
    if not css_dark:
        drift.append("no :root block found in design-system/tokens.css")
    if not css_light:
        drift.append('no :root[data-theme="light"] block found in design-system/tokens.css (light theme must live in tokens)')

    # Cross-check: tokens.json color keys all present in css_dark (and legacy aliases)
    import json
    tokens = json.loads((REPO / "design-system" / "tokens.json").read_text(encoding="utf-8"))
    for name, value in tokens.get("color", {}).items():
        if name == "tint":
            continue
        css_name = f"--{name}"
        if css_name not in css_dark:
            drift.append(f"tokens.json color.{name} ({value}) missing from tokens.css :root")
        elif css_dark.get(css_name) != value:
            drift.append(f"color.{name}: tokens.css {css_dark.get(css_name)!r} != tokens.json {value!r}")

    # 3. tints: values must be in tokens.css (verbatim source), not required inline in HTML
    # Normalize whitespace so "rgba(63,185,80,.15)" matches "rgba(63, 185, 80, .15)"
    def _norm_rgba(s: str) -> str:
        return re.sub(r"\s+", "", s)
    css_norm = _norm_rgba(css_text)
    for name, value in tokens.get("color", {}).get("tint", {}).items():
        if _norm_rgba(value) not in css_norm:
            drift.append(f"tint.{name} ({value}) not found in tokens.css")

    # 4. light block consistency: every preview.html var overridden in light mode must also be in tokens.css light
    # (prevents HTML light theme drifting from token sheet)
    # We compare the light block's keys against css_light
    html_light_vars = vars_in_block(html_text, r':root\[data-theme="light"\]')  # should be empty now after import
    for name in html_light_vars:
        if name not in css_light:
            drift.append(f"light var {name} present inline in preview.html but missing from tokens.css light block")

    if drift:
        print("TOKEN DRIFT:")
        for line in drift:
            print(f"  {line}")
        return 1
    print(f"OK — import present, tokens.css :root {len(css_dark)} + light {len(css_light)} vars, "
          f"{len(tokens['color']['tint'])} tints in sheet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
