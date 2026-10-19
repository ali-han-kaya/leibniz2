#!/usr/bin/env python3
"""check_vercel_tokens.py — verify canonical Vercel tokens match raw.json.

The raw extractor stores computed CSS variables as
``colors.cssVariables.<name>.value`` rather than CSS text. This gate
normalizes that source shape, then enforces the same repository contract as
Linear/Stripe/Primer: tokens.css and grouped tokens.json contain exactly the
raw 19 variables with identical values and canonical provenance/count.

Exit 0 on match, 1 on drift.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
VERCEL = ROOT / "design-system" / "vercel"
RAW = VERCEL / "raw.json"
CSS = VERCEL / "tokens.css"
JSON_PATH = VERCEL / "tokens.json"


def raw_tokens(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    variables = data.get("colors", {}).get("cssVariables")
    if not isinstance(variables, dict) or not variables:
        raise ValueError("raw.json: colors.cssVariables map missing or empty")
    tokens = {}
    for name, metadata in variables.items():
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("value"), str
        ):
            raise ValueError("raw.json: invalid cssVariables entry: %s" % name)
        tokens[name] = metadata["value"]
    return data, tokens


def vars_in_root(path: Path):
    text = path.read_text(encoding="utf-8")
    match = re.search(r":root\s*\{(.*?)\}", text, re.S)
    if not match:
        raise ValueError("no :root block in %s" % path)
    pairs = re.findall(
        r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;", match.group(1)
    )
    return {name: value.strip() for name, value in pairs}


def grouped_tokens(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data.get("tokens")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("tokens.json: tokens map missing or empty")
    flat = {}
    for group, items in groups.items():
        if not isinstance(items, dict):
            raise ValueError("tokens.json: group is not an object: %s" % group)
        for name, value in items.items():
            if not isinstance(value, str):
                raise ValueError("tokens.json: non-string value: %s" % name)
            if name in flat:
                raise ValueError("tokens.json: duplicate token: %s" % name)
            flat[name] = value
    return data, groups, flat


def main() -> int:
    try:
        raw, raw_flat = raw_tokens(RAW)
        css_root = vars_in_root(CSS)
        manifest, groups, json_flat = grouped_tokens(JSON_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("VERCEL TOKEN DRIFT: %s" % exc)
        return 1

    drift = []
    for name, value in raw_flat.items():
        if name not in css_root:
            drift.append("%s missing from tokens.css" % name)
        elif css_root[name] != value:
            drift.append(
                "%s: tokens.css %r != raw %r" % (name, css_root[name], value)
            )
        if name not in json_flat:
            drift.append("%s missing from tokens.json" % name)
        elif json_flat[name] != value:
            drift.append(
                "%s: tokens.json %r != raw %r" % (name, json_flat[name], value)
            )

    for name in css_root:
        if name not in raw_flat:
            drift.append("%s in tokens.css but not in raw.json (stale)" % name)
    for name in json_flat:
        if name not in raw_flat:
            drift.append("%s in tokens.json but not in raw.json (stale)" % name)

    expected_count = len(raw_flat)
    if len(css_root) != expected_count or len(json_flat) != expected_count:
        drift.append(
            "count mismatch: raw %d vs css %d vs json %d"
            % (expected_count, len(css_root), len(json_flat))
        )
    if manifest.get("count") != expected_count:
        drift.append(
            "tokens.json count %r != raw %d"
            % (manifest.get("count"), expected_count)
        )

    source = manifest.get("source") or {}
    provenance = {
        "page": raw.get("url"),
        "extractedAt": raw.get("extractedAt"),
        "raw": "raw.json",
    }
    for key, expected in provenance.items():
        if source.get(key) != expected:
            drift.append(
                "source.%s %r != raw %r" % (key, source.get(key), expected)
            )

    for group, items in groups.items():
        if list(items) != sorted(items):
            drift.append("tokens.json group is not sorted: %s" % group)

    if drift:
        print("VERCEL TOKEN DRIFT:")
        for line in drift[:80]:
            print("  %s" % line)
        if len(drift) > 80:
            print("  ... and %d more" % (len(drift) - 80))
        return 1

    print(
        "OK — %d Vercel tokens verbatim against raw.json "
        "(tokens.css + tokens.json in sync)" % expected_count
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
