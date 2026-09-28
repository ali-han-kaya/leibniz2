#!/usr/bin/env python3
"""Verify GitHub homepage tokens against the raw extractor capture.

The raw extractor stores computed CSS custom properties as
``colors.cssVariables.<name>.value`` rather than CSS text. This gate
normalizes that source shape, then enforces the same repository contract as
the other providers: tokens.css and grouped tokens.json contain exactly the
raw variables with identical values and canonical provenance/count.

Default mode is read-only and fails closed. ``--sync`` explicitly regenerates
the two canonical files from raw.json before verifying them.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
GITHUB = ROOT / "design-system" / "github"
RAW = GITHUB / "raw.json"
CSS = GITHUB / "tokens.css"
JSON_PATH = GITHUB / "tokens.json"
TOKEN_NAME = re.compile(r"--[A-Za-z0-9_-]+\Z")
TOOL = (
    "npx extract-design-system@0.1.11 (dembrandt 0.7.0, "
    "playwright-core 1.63.0, Chrome Headless Shell 153)"
)
SOURCE_NOTE = (
    "No static stylesheet URLs were captured. Verbatim values come "
    "from raw.json colors.cssVariables, computed on the live DOM in "
    "the dark color scheme."
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=unique_object
    )


def raw_tokens(path: Path):
    data = load_json(path)
    variables = data.get("colors", {}).get("cssVariables")
    if not isinstance(variables, dict) or not variables:
        raise ValueError("raw.json: colors.cssVariables map missing or empty")

    tokens = {}
    for name, metadata in variables.items():
        if not TOKEN_NAME.fullmatch(name):
            raise ValueError("raw.json: invalid custom property name: %s" % name)
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("value"), str
        ):
            raise ValueError("raw.json: invalid cssVariables entry: %s" % name)
        value = metadata["value"].strip()
        if not value or any(character in value for character in ";{}"):
            raise ValueError("raw.json: unsafe cssVariables value: %s" % name)
        tokens[name] = value
    return data, tokens


def namespace(name: str) -> str:
    return name[2:].split("-", 1)[0] or "ungrouped"


def grouped_tokens(tokens):
    groups = defaultdict(dict)
    for name in sorted(tokens, key=lambda item: (item.lower(), item)):
        groups[namespace(name)][name] = tokens[name]
    return {
        group: groups[group]
        for group in sorted(groups, key=lambda item: (item.lower(), item))
    }


def render_json(raw, tokens) -> str:
    extracted_at = raw.get("extractedAt")
    if not isinstance(extracted_at, str) or "T" not in extracted_at:
        raise ValueError("raw.json: extractedAt missing or invalid")
    manifest = {
        "$comment": (
            "Verbatim computed custom-property extraction from the GitHub "
            "homepage. Values are copied without remapping, renaming, rounding, "
            "or theme expansion. This is a homepage/root capture, not the full "
            "Primer design system."
        ),
        "source": {
            "page": raw.get("url"),
            "raw": "raw.json",
            "tool": TOOL,
            "extractedAt": extracted_at,
            "assets": [],
            "note": SOURCE_NOTE,
        },
        "extracted": extracted_at.split("T", 1)[0],
        "count": len(tokens),
        "tokens": grouped_tokens(tokens),
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def render_css(raw, tokens) -> str:
    extracted_at = raw.get("extractedAt")
    if not isinstance(extracted_at, str) or "T" not in extracted_at:
        raise ValueError("raw.json: extractedAt missing or invalid")
    date = extracted_at.split("T", 1)[0]
    lines = [
        "/*",
        " * design-system/github/tokens.css — GitHub homepage custom properties",
        " * (verbatim).",
        " *",
        " * Extracted from https://github.com/ on %s in the dark color"
        % date,
        " * scheme. Scope warning: this is the computed root-variable capture,",
        " * not the complete GitHub/Primer design system. No remapping, no",
        " * renaming, no rounding, and no light-theme expansion.",
        " *",
        " * Canonical source: raw.json -> tokens.json / tokens.css. Run",
        " * `python3 design-system/github/scripts/check_github_tokens.py` to check.",
        " */",
        ":root {",
    ]
    for group, items in grouped_tokens(tokens).items():
        lines.append("  /* ── %s ── */" % group)
        lines.extend("  %s: %s;" % (name, value) for name, value in items.items())
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines.append("}")
    return "\n".join(lines) + "\n"


def vars_in_root(path: Path):
    text = path.read_text(encoding="utf-8")
    match = re.search(r":root\s*\{(.*?)\}", text, re.S)
    if not match:
        raise ValueError("no :root block in %s" % path)
    pairs = re.findall(
        r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;", match.group(1)
    )
    names = [name for name, _ in pairs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            "duplicate tokens.css declarations: %s" % ", ".join(duplicates[:20])
        )
    return {name: value.strip() for name, value in pairs}


def manifest_tokens(path: Path):
    data = load_json(path)
    groups = data.get("tokens")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("tokens.json: tokens map missing or empty")
    flat = {}
    for group, items in groups.items():
        if not isinstance(group, str) or not group:
            raise ValueError("tokens.json: invalid group name")
        if not isinstance(items, dict):
            raise ValueError("tokens.json: group is not an object: %s" % group)
        for name, value in items.items():
            if not isinstance(value, str):
                raise ValueError("tokens.json: non-string value: %s" % name)
            if name in flat:
                raise ValueError("tokens.json: duplicate token: %s" % name)
            flat[name] = value
    return data, groups, flat


def check(
    raw,
    raw_flat,
    css_text,
    json_text,
    css_root,
    manifest,
    groups,
    json_flat,
):
    drift = []
    if css_text != render_css(raw, raw_flat):
        drift.append("tokens.css differs from deterministic raw.json rendering")
    if json_text != render_json(raw, raw_flat):
        drift.append("tokens.json differs from deterministic raw.json rendering")
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
        "tool": TOOL,
        "assets": [],
        "note": SOURCE_NOTE,
    }
    for key, expected in provenance.items():
        if source.get(key) != expected:
            drift.append(
                "source.%s %r != expected %r" % (key, source.get(key), expected)
            )

    expected_groups = grouped_tokens(raw_flat)
    if groups != expected_groups:
        drift.append("tokens.json namespace groups or ordering differ from raw")

    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="regenerate tokens.css and tokens.json from raw.json before checking",
    )
    args = parser.parse_args()

    try:
        raw, raw_flat = raw_tokens(RAW)
        if args.sync:
            CSS.write_text(render_css(raw, raw_flat), encoding="utf-8")
            JSON_PATH.write_text(render_json(raw, raw_flat), encoding="utf-8")
        css_text = CSS.read_text(encoding="utf-8")
        json_text = JSON_PATH.read_text(encoding="utf-8")
        css_root = vars_in_root(CSS)
        manifest, groups, json_flat = manifest_tokens(JSON_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("GITHUB TOKEN DRIFT: %s" % exc)
        return 1

    drift = check(
        raw,
        raw_flat,
        css_text,
        json_text,
        css_root,
        manifest,
        groups,
        json_flat,
    )
    if drift:
        print("GITHUB TOKEN DRIFT:")
        for line in drift[:80]:
            print("  %s" % line)
        if len(drift) > 80:
            print("  ... and %d more" % (len(drift) - 80))
        return 1

    action = "synced and verified" if args.sync else "verified"
    print(
        "OK — %d GitHub tokens %s against raw.json "
        "(tokens.css + tokens.json in sync)" % (len(raw_flat), action)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
