#!/usr/bin/env python3
"""check_stripe_tokens.py — verify design-system/stripe tokens match stripe raw.css.

Two contracts:
1. Every --hds-* in raw.css (first occurrence) exists in tokens.css/json with the same value.
2. tokens.css :root contains exactly the --hds-* set from raw.css (no extras, no missing).

Exit 0 on match, 1 on drift.
"""
import re, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
RAW = REPO / "design-system" / "stripe" / "raw.css"
CSS = REPO / "design-system" / "stripe" / "tokens.css"
JSON_PATH = REPO / "design-system" / "stripe" / "tokens.json"

def vars_in_file(path: Path):
    text = path.read_text(encoding="utf-8")
    pairs = re.findall(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;', text)
    seen = {}
    for k, v in pairs:
        if k not in seen:
            seen[k] = v.strip()
    return seen

def vars_in_root(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r':root\s*\{(.*?)\}', text, re.S)
    if not m:
        raise SystemExit(f"no :root block in {path}")
    return {n: v.strip() for n, v in re.findall(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;', m.group(1))}

def main() -> int:
    raw_all = vars_in_file(RAW)
    raw_hds = {k: v for k, v in raw_all.items() if k.startswith("--hds-")}
    css_root = vars_in_root(CSS)
    tokens = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    flat = {}
    for group, items in tokens.get("tokens", {}).items():
        flat.update(items)

    drift = []
    # 1. raw HDS must be in css + json with identical values
    for name, value in raw_hds.items():
        if name not in css_root:
            drift.append(f"{name} missing from tokens.css")
        elif css_root[name] != value:
            drift.append(f"{name}: tokens.css {css_root[name]!r} != raw {value!r}")
        if name not in flat:
            drift.append(f"{name} missing from tokens.json")
        elif flat[name] != value:
            drift.append(f"{name}: tokens.json {flat[name]!r} != raw {value!r}")
    # 2. css + json must not have extras beyond raw HDS
    for name in css_root:
        if name.startswith("--hds-") and name not in raw_hds:
            drift.append(f"{name} in tokens.css but not in raw.css (stale)")
    for name in flat:
        if name not in raw_hds:
            drift.append(f"{name} in tokens.json but not in raw.css (stale)")
    # 3. counts
    if len(raw_hds) != len(css_root) or len(raw_hds) != len(flat):
        drift.append(f"count mismatch: raw HDS {len(raw_hds)} vs css {len(css_root)} vs json {len(flat)}")

    if drift:
        print("STRIPE TOKEN DRIFT:")
        for line in drift[:80]:
            print(f"  {line}")
        if len(drift) > 80:
            print(f"  ... and {len(drift)-80} more")
        return 1
    print(f"OK — {len(raw_hds)} HDS tokens verbatim against raw.css (tokens.css + tokens.json in sync)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
