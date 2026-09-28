#!/usr/bin/env python3
"""Cross-check the GitHub site specimen against both provider snapshots.

The page may load the GitHub token stylesheet only. Primer is an offline
comparison source: shared names and the values shown in the crosswalk table
must match the two manifests, but Primer must never enter the page cascade.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
GITHUB = ROOT / "design-system" / "github"
PRIMER = ROOT / "design-system" / "primer"
SAMPLE = GITHUB / "sample.html"

EXPECTED = {
    "github": 304,
    "primer": 2051,
    "common": 289,
    "exact": 131,
    "different": 158,
    "github_only": 15,
    "primer_only": 1762,
}
MIN_GITHUB_REFERENCES = 30
MIN_CROSSWALK_ROWS = 5
TOKEN_NAME = re.compile(r"--[A-Za-z0-9_-]+\Z")
CSS_REFERENCE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
CSS_DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")


class SpecimenParser(HTMLParser):
    """Collect CSS references and the crosswalk table without dependencies."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.styles = []
        self.style_attributes = []
        self.stylesheets = []
        self.data_tokens = set()
        self.crosswalk_tokens = set()
        self.crosswalk_rows = []
        self.in_style = False
        self.in_tbody = False
        self.in_row = False
        self.row_attrs = {}
        self.cells = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "style":
            self.in_style = True
        elif tag == "link":
            rel = (attributes.get("rel") or "").lower().split()
            if "stylesheet" in rel:
                self.stylesheets.append(attributes.get("href") or "")
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_row = True
            self.row_attrs = attributes
            self.cells = []
        elif tag == "td" and self.in_row:
            self.cell = []
        if "style" in attributes:
            self.style_attributes.append(attributes["style"])

        if "data-token" in attributes:
            self.data_tokens.add(attributes["data-token"])
        if "data-crosswalk-token" in attributes:
            self.crosswalk_tokens.add(attributes["data-crosswalk-token"])

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        elif tag == "td" and self.in_row and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.in_row:
            self.crosswalk_rows.append((self.row_attrs, self.cells))
            self.in_row = False
            self.row_attrs = {}
            self.cells = []
        elif tag == "tbody":
            self.in_tbody = False


def manifest_tokens(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data.get("tokens")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("%s: tokens map missing or empty" % path)
    result = {}
    for group, items in groups.items():
        if not isinstance(group, str) or not group or not isinstance(items, dict):
            raise ValueError("%s: invalid token namespace" % path)
        for name, value in items.items():
            if not TOKEN_NAME.fullmatch(name) or not isinstance(value, str):
                raise ValueError("%s: invalid token %r" % (path, name))
            if name in result:
                raise ValueError("%s: duplicate token %s" % (path, name))
            result[name] = value
    return result


def normalized_text(value):
    return " ".join(value.split())


def add_count_drift(drift, label, actual, expected):
    if actual != expected:
        drift.append("%s count %d != expected %d" % (label, actual, expected))


def main() -> int:
    try:
        github = manifest_tokens(GITHUB / "tokens.json")
        primer = manifest_tokens(PRIMER / "tokens.json")
        sample_text = SAMPLE.read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("GITHUB/PRIMER SPECIMEN DRIFT: %s" % exc)
        return 1

    parser = SpecimenParser()
    try:
        parser.feed(sample_text)
        parser.close()
    except Exception as exc:  # HTMLParser can surface malformed markup this way.
        print("GITHUB/PRIMER SPECIMEN DRIFT: cannot parse sample.html: %s" % exc)
        return 1

    style_text = "\n".join(parser.styles + parser.style_attributes)
    local_definitions = [
        name
        for name in CSS_DECLARATION.findall(style_text)
        if name.startswith("--sample-")
    ]
    local_names = set(local_definitions)
    css_references = set(CSS_REFERENCE.findall(style_text))
    github_references = (css_references - local_names) | parser.data_tokens

    common = set(github) & set(primer)
    exact = {name for name in common if github[name] == primer[name]}
    different = common - exact
    github_only = set(github) - set(primer)
    primer_only = set(primer) - set(github)

    drift = []
    add_count_drift(drift, "GitHub", len(github), EXPECTED["github"])
    add_count_drift(drift, "Primer", len(primer), EXPECTED["primer"])
    add_count_drift(drift, "common", len(common), EXPECTED["common"])
    add_count_drift(drift, "exact", len(exact), EXPECTED["exact"])
    add_count_drift(drift, "different", len(different), EXPECTED["different"])
    add_count_drift(drift, "GitHub-only", len(github_only), EXPECTED["github_only"])
    add_count_drift(drift, "Primer-only", len(primer_only), EXPECTED["primer_only"])

    if parser.stylesheets != ["./tokens.css"]:
        drift.append(
            "stylesheet imports %r; expected only GitHub './tokens.css'"
            % parser.stylesheets
        )
    if re.search(r"@import\b", style_text, re.IGNORECASE):
        drift.append("CSS @import found; link the single GitHub stylesheet instead")
    if any("primer" in href.lower() for href in parser.stylesheets):
        drift.append("Primer stylesheet co-import detected")
    if parser.crosswalk_tokens != {attrs.get("data-crosswalk-token") for attrs, _ in parser.crosswalk_rows}:
        drift.append("data-crosswalk-token attributes do not match crosswalk rows")

    unknown = sorted(github_references - set(github))
    if unknown:
        drift.append("sample references non-GitHub tokens: %s" % ", ".join(unknown))
    referenced_local = {
        name for name in css_references if name.startswith("--sample-")
    }
    missing_definitions = sorted(referenced_local - local_names)
    if missing_definitions:
        drift.append("local sample variables are not defined: %s" % ", ".join(missing_definitions))
    if len(local_definitions) != len(local_names):
        drift.append("local sample variables must each be declared once")
    if len(github_references) < MIN_GITHUB_REFERENCES:
        drift.append(
            "sample uses only %d GitHub tokens; expected at least %d"
            % (len(github_references), MIN_GITHUB_REFERENCES)
        )

    for name in sorted(parser.data_tokens - css_references):
        drift.append("data-token has no matching CSS var() reference: %s" % name)

    row_relations = []
    seen_rows = set()
    for attrs, cells in parser.crosswalk_rows:
        name = attrs.get("data-crosswalk-token")
        if not name:
            drift.append("crosswalk row is missing data-crosswalk-token")
            continue
        if name in seen_rows:
            drift.append("duplicate crosswalk row: %s" % name)
            continue
        seen_rows.add(name)
        if name not in common:
            drift.append("crosswalk token is not shared by both providers: %s" % name)
            continue
        if len(cells) != 4:
            drift.append("crosswalk row %s has %d cells; expected 4" % (name, len(cells)))
            continue
        relation = "exact" if name in exact else "different"
        row_relations.append(relation)
        if normalized_text(cells[1]) != normalized_text(github[name]):
            drift.append("%s GitHub value %r != specimen %r" % (name, github[name], cells[1]))
        if normalized_text(cells[2]) != normalized_text(primer[name]):
            drift.append("%s Primer value %r != specimen %r" % (name, primer[name], cells[2]))
        if cells[3] != relation:
            drift.append("%s relation %r != %r" % (name, cells[3], relation))

    if len(parser.crosswalk_rows) < MIN_CROSSWALK_ROWS:
        drift.append(
            "crosswalk has %d rows; expected at least %d"
            % (len(parser.crosswalk_rows), MIN_CROSSWALK_ROWS)
        )
    if "exact" not in row_relations or "different" not in row_relations:
        drift.append("crosswalk must demonstrate both exact and different relations")

    if drift:
        print("GITHUB/PRIMER SPECIMEN DRIFT:")
        for line in drift[:100]:
            print("  %s" % line)
        if len(drift) > 100:
            print("  ... and %d more" % (len(drift) - 100))
        return 1

    print(
        "OK — specimen uses %d GitHub tokens and Primer remains comparison-only"
        % len(github_references)
    )
    print(
        "OK — crosswalk verified: %d rows (%d exact, %d different); "
        "GitHub %d / Primer %d / common %d / GitHub-only %d / Primer-only %d"
        % (
            len(parser.crosswalk_rows),
            row_relations.count("exact"),
            row_relations.count("different"),
            len(github),
            len(primer),
            len(common),
            len(github_only),
            len(primer_only),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
