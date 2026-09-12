#!/usr/bin/env python3
"""check_primer_tokens.py — verify design-system/primer tokens match raw.css.

Two contracts:
1. Every --* in raw.css (first occurrence) exists in tokens.css/json with the same value.
2. tokens.css :root contains exactly the --* set from raw.css (no extras, no missing).

Exit 0 on match, 1 on drift.
"""
import re, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
RAW = REPO / "design-system" / "primer" / "raw.css"
CSS = REPO / "design-system" / "primer" / "tokens.css"
JSON_PATH = REPO / "design-system" / "primer" / "tokens.json"

def vars_in_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    pairs = re.findall(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;', text)
    seen = {}
    for k, v in pairs:
        if k not in seen:
            seen[k] = v.strip()
    return seen

def vars_in_root(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r':root\s*\{(.*?)\}', text, re.S)
    if not m:
        raise SystemExit(f"no :root block in {path}")
    return {n: v.strip() for n, v in re.findall(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;', m.group(1))}

def main() -> int:
    raw_all = vars_in_file(RAW)
    css_root = vars_in_root(CSS)
    tokens = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    flat = {}
    for group, items in tokens.get("tokens", {}).items():
        flat.update(items)

    drift = []
    for name, value in raw_all.items():
        if name not in css_root:
            drift.append(f"{name} missing from tokens.css")
        elif css_root[name] != value:
            drift.append(f"{name}: tokens.css {css_root[name]!r} != raw {value!r}")
        if name not in flat:
            drift.append(f"{name} missing from tokens.json")
        elif flat[name] != value:
            drift.append(f"{name}: tokens.json {flat[name]!r} != raw {value!r}")
    for name in css_root:
        if name not in raw_all:
            drift.append(f"{name} in tokens.css but not in raw.css (stale)")
    for name in flat:
        if name not in raw_all:
            drift.append(f"{name} in tokens.json but not in raw.css (stale)")
    if len(raw_all) != len(css_root) or len(raw_all) != len(flat):
        drift.append(f"count mismatch: raw {len(raw_all)} vs css {len(css_root)} vs json {len(flat)}")

    if drift:
        print("PRIMER TOKEN DRIFT:")
        for line in drift[:80]:
            print(f"  {line}")
        if len(drift) > 80:
            print(f"  ... and {len(drift)-80} more")
        return 1
    print(f"OK — {len(raw_all)} Primer tokens verbatim against raw.css (tokens.css + tokens.json in sync)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
