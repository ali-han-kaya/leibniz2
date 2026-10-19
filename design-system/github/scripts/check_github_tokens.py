#!/usr/bin/env python3
"""Verify GitHub homepage tokens against the raw extractor captures.

The raw extractor stores computed CSS custom properties as
``colors.cssVariables.<name>.value`` rather than CSS text. This gate
normalizes that source shape, then enforces the same repository contract as
the other providers: tokens.css and grouped tokens.json contain exactly the
raw variables with identical values and canonical provenance/count.

Two theme layers are covered (2026-10-11):

* ``raw.json`` -> ``tokens.css`` / ``tokens.json`` — the original dark capture
  (2026-09-24). Its rendering contract is unchanged byte-for-byte.
* ``raw.light.json`` -> ``tokens.light.css`` / ``tokens.light.json`` — the light
  capture. github.com serves dark to logged-out visitors and the extractor CLI
  exposes no light switch, so the light layer is captured with the page's
  ``data-color-mode`` attribute pinned to ``light``
  (``scripts/capture_theme.mjs``, which drives dembrandt's own
  ``extractBranding``). The layer is only accepted when the capture's own
  ``pageState`` says the page really was in the light scheme, and the two
  layers must disagree on at least one shared name — a "light" capture that is
  silently a copy of the dark one is a FAIL, not a PASS.

Default mode is read-only and fails closed. ``--sync`` explicitly regenerates
the canonical files from the raw captures before verifying them.
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
RAW_LIGHT = GITHUB / "raw.light.json"
CSS_LIGHT = GITHUB / "tokens.light.css"
JSON_PATH_LIGHT = GITHUB / "tokens.light.json"
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
MANIFEST_COMMENT = (
    "Verbatim computed custom-property extraction from the GitHub "
    "homepage. Values are copied without remapping, renaming, rounding, "
    "or theme expansion. This is a homepage/root capture, not the full "
    "Primer design system."
)
TOOL_LIGHT = (
    "design-system/github/scripts/capture_theme.mjs "
    "(dembrandt 0.7.3 lib/extractors.js, playwright-core 1.63.0, "
    "Chrome Headless Shell 153)"
)
SOURCE_NOTE_LIGHT = (
    "No static stylesheet URLs were captured. Verbatim values come "
    "from raw.light.json colors.cssVariables, computed on the live DOM "
    "with documentElement's data-color-mode attribute pinned to "
    "\"light\" (github.com serves dark to logged-out visitors and the "
    "extractor CLI exposes no light switch); pageState in the manifest "
    "records the captured page state."
)
MANIFEST_COMMENT_LIGHT = (
    "Verbatim computed custom-property extraction from the GitHub "
    "homepage in the light color scheme. Values are copied without "
    "remapping, renaming, rounding, or cross-theme expansion. This is a "
    "homepage/root capture, not the full Primer design system."
)

LAYERS = (
    {
        "theme": "dark",
        "label": "GitHub tokens",
        "raw": RAW,
        "raw_label": "raw.json",
        "css": CSS,
        "css_label": "tokens.css",
        "manifest": JSON_PATH,
        "manifest_label": "tokens.json",
        "note": SOURCE_NOTE,
        "comment": MANIFEST_COMMENT,
        "tool": TOOL,
        # The dark layer predates pageState; it records no theme key at all.
        "require_page_state": False,
    },
    {
        "theme": "light",
        "label": "GitHub light tokens",
        "raw": RAW_LIGHT,
        "raw_label": "raw.light.json",
        "css": CSS_LIGHT,
        "css_label": "tokens.light.css",
        "manifest": JSON_PATH_LIGHT,
        "manifest_label": "tokens.light.json",
        "note": SOURCE_NOTE_LIGHT,
        "comment": MANIFEST_COMMENT_LIGHT,
        "tool": TOOL_LIGHT,
        "require_page_state": True,
    },
)

# Cross-layer invariant: the captures must disagree somewhere. Measured
# 2026-10-11: 208 shared names, 195 of them differ — 13 match. A threshold of 1
# is deliberate: the point is to reject a light layer that is a copy of the dark
# one, not to pin today's exact overlap (which changes when GitHub changes).
MIN_SHARED_VALUE_DIFFERENCES = 1


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
        raise ValueError("%s: colors.cssVariables map missing or empty" % path.name)

    tokens = {}
    for name, metadata in variables.items():
        if not TOKEN_NAME.fullmatch(name):
            raise ValueError(
                "%s: invalid custom property name: %s" % (path.name, name)
            )
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("value"), str
        ):
            raise ValueError(
                "%s: invalid cssVariables entry: %s" % (path.name, name)
            )
        value = metadata["value"].strip()
        if not value or any(character in value for character in ";{}"):
            raise ValueError(
                "%s: unsafe cssVariables value: %s" % (path.name, name)
            )
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


def source_record(layer, raw):
    source = {
        "page": raw.get("url"),
        "raw": layer["raw_label"],
        "tool": layer["tool"],
        "extractedAt": raw.get("extractedAt"),
        "assets": [],
        "note": layer["note"],
    }
    if layer["require_page_state"]:
        source["theme"] = raw.get("theme")
        source["pageState"] = raw.get("pageState")
    return source


def render_json(layer, raw, tokens) -> str:
    extracted_at = raw.get("extractedAt")
    if not isinstance(extracted_at, str) or "T" not in extracted_at:
        raise ValueError("%s: extractedAt missing or invalid" % layer["raw_label"])
    manifest = {
        "$comment": layer["comment"],
        "source": source_record(layer, raw),
        "extracted": extracted_at.split("T", 1)[0],
        "count": len(tokens),
        "tokens": grouped_tokens(tokens),
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def render_css(layer, raw, tokens) -> str:
    extracted_at = raw.get("extractedAt")
    if not isinstance(extracted_at, str) or "T" not in extracted_at:
        raise ValueError("%s: extractedAt missing or invalid" % layer["raw_label"])
    date = extracted_at.split("T", 1)[0]
    other = "light" if layer["theme"] == "dark" else "dark"
    lines = [
        "/*",
        " * design-system/github/%s — GitHub homepage custom properties"
        % layer["css_label"],
        " * (verbatim).",
        " *",
        " * Extracted from https://github.com/ on %s in the %s color" % (date, layer["theme"]),
        " * scheme. Scope warning: this is the computed root-variable capture,",
        " * not the complete GitHub/Primer design system. No remapping, no",
        " * renaming, no rounding, and no %s-theme expansion." % other,
        " *",
        " * Canonical source: %s -> %s / %s. Run"
        % (layer["raw_label"], layer["manifest_label"], layer["css_label"]),
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
            "duplicate %s declarations: %s" % (path.name, ", ".join(duplicates[:20]))
        )
    return {name: value.strip() for name, value in pairs}


def manifest_tokens(path: Path):
    data = load_json(path)
    groups = data.get("tokens")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("%s: tokens map missing or empty" % path.name)
    flat = {}
    for group, items in groups.items():
        if not isinstance(group, str) or not group:
            raise ValueError("%s: invalid group name" % path.name)
        if not isinstance(items, dict):
            raise ValueError(
                "%s: group is not an object: %s" % (path.name, group)
            )
        for name, value in items.items():
            if not isinstance(value, str):
                raise ValueError(
                    "%s: non-string value: %s" % (path.name, name)
                )
            if name in flat:
                raise ValueError("%s: duplicate token: %s" % (path.name, name))
            flat[name] = value
    return data, groups, flat


def page_state_drift(layer, raw):
    """The light layer must prove it was captured in the light scheme."""
    if not layer["require_page_state"]:
        return []
    drift = []
    if raw.get("theme") != layer["theme"]:
        drift.append(
            "%s theme %r != %r" % (layer["raw_label"], raw.get("theme"), layer["theme"])
        )
    state = raw.get("pageState")
    if not isinstance(state, dict):
        drift.append("%s pageState missing (cannot prove the captured scheme)" % layer["raw_label"])
        return drift
    if state.get("dataColorMode") != layer["theme"]:
        drift.append(
            "%s pageState.dataColorMode %r != %r"
            % (layer["raw_label"], state.get("dataColorMode"), layer["theme"])
        )
    for key in ("bgColorDefault", "fgColorDefault"):
        value = state.get(key)
        if not isinstance(value, str) or not value:
            drift.append("%s pageState.%s missing" % (layer["raw_label"], key))
    return drift


def check(layer, raw, raw_flat, css_text, json_text, css_root, manifest, groups, json_flat):
    drift = []
    if css_text != render_css(layer, raw, raw_flat):
        drift.append(
            "%s differs from deterministic %s rendering"
            % (layer["css_label"], layer["raw_label"])
        )
    if json_text != render_json(layer, raw, raw_flat):
        drift.append(
            "%s differs from deterministic %s rendering"
            % (layer["manifest_label"], layer["raw_label"])
        )
    for name, value in raw_flat.items():
        if name not in css_root:
            drift.append("%s missing from %s" % (name, layer["css_label"]))
        elif css_root[name] != value:
            drift.append(
                "%s: %s %r != raw %r"
                % (name, layer["css_label"], css_root[name], value)
            )
        if name not in json_flat:
            drift.append("%s missing from %s" % (name, layer["manifest_label"]))
        elif json_flat[name] != value:
            drift.append(
                "%s: %s %r != raw %r"
                % (name, layer["manifest_label"], json_flat[name], value)
            )

    for name in css_root:
        if name not in raw_flat:
            drift.append(
                "%s in %s but not in %s (stale)"
                % (name, layer["css_label"], layer["raw_label"])
            )
    for name in json_flat:
        if name not in raw_flat:
            drift.append(
                "%s in %s but not in %s (stale)"
                % (name, layer["manifest_label"], layer["raw_label"])
            )

    expected_count = len(raw_flat)
    if len(css_root) != expected_count or len(json_flat) != expected_count:
        drift.append(
            "count mismatch: raw %d vs css %d vs json %d"
            % (expected_count, len(css_root), len(json_flat))
        )
    if manifest.get("count") != expected_count:
        drift.append(
            "%s count %r != raw %d"
            % (layer["manifest_label"], manifest.get("count"), expected_count)
        )

    source = manifest.get("source") or {}
    provenance = source_record(layer, raw)
    for key, expected in provenance.items():
        if source.get(key) != expected:
            drift.append(
                "source.%s %r != expected %r" % (key, source.get(key), expected)
            )

    expected_groups = grouped_tokens(raw_flat)
    if groups != expected_groups:
        drift.append(
            "%s namespace groups or ordering differ from raw" % layer["manifest_label"]
        )

    drift.extend(page_state_drift(layer, raw))
    return drift


def verify_layer(layer, sync):
    """Returns (drift_lines, token_count) for one layer."""
    raw, raw_flat = raw_tokens(layer["raw"])
    if sync:
        layer["css"].write_text(render_css(layer, raw, raw_flat), encoding="utf-8")
        layer["manifest"].write_text(
            render_json(layer, raw, raw_flat), encoding="utf-8"
        )
    css_text = layer["css"].read_text(encoding="utf-8")
    json_text = layer["manifest"].read_text(encoding="utf-8")
    css_root = vars_in_root(layer["css"])
    manifest, groups, json_flat = manifest_tokens(layer["manifest"])
    return (
        check(
            layer,
            raw,
            raw_flat,
            css_text,
            json_text,
            css_root,
            manifest,
            groups,
            json_flat,
        ),
        raw_flat,
    )


def cross_layer_drift(theme_tokens):
    """A light layer that is a copy of the dark one is a FAIL, not a PASS."""
    dark = theme_tokens.get("dark")
    light = theme_tokens.get("light")
    if not dark or not light:
        return []
    shared = set(dark) & set(light)
    differing = sorted(name for name in shared if dark[name] != light[name])
    if len(differing) < MIN_SHARED_VALUE_DIFFERENCES:
        return [
            "light layer does not differ from the dark layer "
            "(%d shared names, %d with different values; need >= %d) — a light "
            "capture that repeats the dark values is not a light capture"
            % (len(shared), len(differing), MIN_SHARED_VALUE_DIFFERENCES)
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="regenerate the canonical files from the raw captures before checking",
    )
    args = parser.parse_args()

    theme_tokens = {}
    for layer in LAYERS:
        try:
            drift, raw_flat = verify_layer(layer, args.sync)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("GITHUB TOKEN DRIFT: %s" % exc)
            return 1
        if drift:
            print("GITHUB TOKEN DRIFT (%s layer, %s):" % (layer["theme"], layer["raw_label"]))
            for line in drift[:80]:
                print("  %s" % line)
            if len(drift) > 80:
                print("  ... and %d more" % (len(drift) - 80))
            return 1
        theme_tokens[layer["theme"]] = raw_flat

    drift = cross_layer_drift(theme_tokens)
    if drift:
        print("GITHUB TOKEN DRIFT (cross-layer):")
        for line in drift:
            print("  %s" % line)
        return 1

    action = "synced and verified" if args.sync else "verified"
    for layer in LAYERS:
        print(
            "OK — %d %s %s against %s (%s + %s in sync)"
            % (
                len(theme_tokens[layer["theme"]]),
                layer["label"],
                action,
                layer["raw_label"],
                layer["css_label"],
                layer["manifest_label"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
