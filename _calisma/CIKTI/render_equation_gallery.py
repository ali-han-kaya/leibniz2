#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a curated gallery of display equations from the canonical article.

The pipeline deliberately reuses :mod:`render_z3_slides` rather than growing a
second TeX/PDF/PNG implementation:

    article display block -> standalone TeX -> PDF -> tight PNG

The source of every equation is the canonical formal section included by the
manuscript (``ingiliz_empirizmi_v3.tex``).  ``EQUATIONS`` is a small, explicit
selection manifest.  Each entry binds to one unique display anchor; missing or
ambiguous anchors are errors.  A manifest and an accessible, self-contained
HTML index are written beside the PNGs.

Examples::

    python3 _calisma/CIKTI/render_equation_gallery.py
    python3 _calisma/CIKTI/render_equation_gallery.py --check-sync
    python3 _calisma/CIKTI/render_equation_gallery.py --only grounding-atom

The default source-date epoch is fixed so repeated runs produce stable PNG
bytes.  ``SOURCE_DATE_EPOCH`` may be supplied explicitly by a caller.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import pathlib
import re
import struct
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterable

# The script directory is on sys.path when invoked as a script and is made
# explicit here for importlib-based tests and clean-checkout runners.
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from render_z3_slides import (  # noqa: E402  (path bootstrap above)
    compile_tex,
    find_pdf_to_png,
    find_tex_engine,
    pdf_to_png,
    strip_png_metadata,
)

ROOT = _HERE.parent
REPO_ROOT = _HERE.parents[1]
DEFAULT_SOURCE = ROOT / (
    "V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/"
    "Stoic_Hume_Formal_Section_2026-08-17/core_section.tex"
)
DEFAULT_OUT = _HERE / "equation_gallery"
DEFAULT_SOURCE_DATE_EPOCH = "1700000000"


@dataclass(frozen=True)
class EquationSpec:
    """One deliberately selected source display equation."""

    ident: str
    title: str
    anchor: str


# The selection follows the article's argument rather than dumping every
# display: language -> Stoic/Humean readings -> strength/bridge collapse ->
# reification -> underdetermination and definability failure.
EQUATIONS: tuple[EquationSpec, ...] = (
    EquationSpec("l0-sorts", "L0: the three core sorts", r"I \quad\text{(impressions)}"),
    EquationSpec("stoic-skeleton", "Stoic minimal dependency skeleton (S)", r"\tag{S}"),
    EquationSpec("mechanism-m0a", "Humean mechanism constraint M0a", r"\tag{M$_{0a}$}"),
    EquationSpec("mechanism-m0b", "Humean mechanism constraint M0b", r"\tag{M$_{0b}$}"),
    EquationSpec("hume-exclusion", "Strong exclusion reconstruction (H-I)", r"\tag{H-I}"),
    EquationSpec("direct-attachment", "Direct-attachment reading (T1)", r"\tag{T$_1$}"),
    EquationSpec("strength-valid", "Proposition 1: valid entailment", r"T_2\land M_0 \models T_1"),
    EquationSpec(
        "strength-counterexample",
        "Proposition 1: separating countermodel",
        r"T_1\land M_0 \not\models T_2",
    ),
    EquationSpec("bridge-axiom", "Bridge axiom B0", r"\tag{B$_0$}"),
    EquationSpec("bridge-collapse", "Proposition 1: bridge collapse", r"T_1\land B_0 \models T_2"),
    EquationSpec(
        "reification-bridges",
        "Reification bridge axioms O1-O3",
        r"\operatorname{Obtains}(\operatorname{custFact}(b))",
    ),
    EquationSpec("grounding-atom", "The grounding atom (G)", r"\tag{G}"),
    EquationSpec("language-enrichment", "The enriched language L+", r"L^+ \;=\; L_0"),
    EquationSpec(
        "underdetermination",
        "Underdetermination witness",
        r"\mathcal M_1^+\models",
    ),
    EquationSpec(
        "definability-failure",
        "Implicit definability failure",
        r"\theta(b,c)\leftrightarrow",
    ),
    EquationSpec(
        "enrichment-pair",
        "Two enrichments with one reduct",
        r"\mathcal M_1^+=\langle\mathcal M,\,G_1\rangle",
    ),
)


@dataclass(frozen=True)
class DisplayBlock:
    """A source display block with its original line span."""

    kind: str
    body: str
    start_line: int
    end_line: int

    def standalone(self) -> str:
        """Return a standalone-croppable inline math representation.

        The source delimiters are retained in the manifest/body hash, while
        the PNG renderer uses the same safe ``$...$`` strategy as
        ``render_z3_slides.py``.  Alignment rows are wrapped in ``aligned``;
        equation tags are omitted because ``standalone``'s preview shell does
        not accept ``\tag`` inside an inner math atom.
        """
        body = _strip_tags(self.body).strip("\n")
        if self.kind == "display":
            return "$\\displaystyle\n" + body + "\n$"
        return "$\\displaystyle\\begin{aligned}\n" + body + "\n\\end{aligned}$"

    def body_sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


_DISPLAY_START = re.compile(r"^\\begin\{(align\*?|equation\*?|gather\*?)\}$")
# ``standalone`` crops an inline math atom reliably; display environments themselves
# are not suitable inside its preview shell.  Tags are retained in the manifest
# but removed from the standalone image (the gallery caption carries the ID).
def _strip_tags(text: str) -> str:
    """Remove complete ``\\tag{...}`` commands, including nested braces."""
    out: list[str] = []
    cursor = 0
    while True:
        start = text.find(r"\tag{", cursor)
        if start < 0:
            out.append(text[cursor:])
            return "".join(out)
        out.append(text[cursor:start])
        index = start + len(r"\tag{")
        depth = 1
        while index < len(text) and depth:
            if text[index] == "{" and (index == 0 or text[index - 1] != "\\"):
                depth += 1
            elif text[index] == "}" and (index == 0 or text[index - 1] != "\\"):
                depth -= 1
            index += 1
        if depth:
            raise ValueError("unclosed \\tag{...} in source display")
        cursor = index


_DISPLAY_END = {
    "align": r"\end{align}",
    "align*": r"\end{align*}",
    "equation": r"\end{equation}",
    "equation*": r"\end{equation*}",
    "gather": r"\end{gather}",
    "gather*": r"\end{gather*}",
}


def _source_lines(source: pathlib.Path) -> list[str]:
    return source.read_text(encoding="utf-8").splitlines()


def extract_display_blocks(source: pathlib.Path) -> list[DisplayBlock]:
    """Extract balanced ``\\[...\\]`` and theorem-style display environments.

    The article uses each delimiter on its own line.  This small parser is
    intentionally strict: an opening delimiter without its exact closing
    delimiter raises instead of silently rendering a partial equation.
    """
    lines = _source_lines(source)
    blocks: list[DisplayBlock] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("%"):
            index += 1
            continue
        if stripped == r"\[":
            start = index
            index += 1
            while index < len(lines) and lines[index].strip() != r"\]":
                index += 1
            if index == len(lines):
                raise ValueError(f"unclosed \\[ display at line {start + 1}")
            blocks.append(DisplayBlock("display", "\n".join(lines[start + 1:index]),
                                       start + 1, index + 1))
            index += 1
            continue
        match = _DISPLAY_START.fullmatch(stripped)
        if match:
            kind = match.group(1)
            start = index
            index += 1
            end_marker = _DISPLAY_END[kind]
            while index < len(lines) and lines[index].strip() != end_marker:
                index += 1
            if index == len(lines):
                raise ValueError(f"unclosed {kind} display at line {start + 1}")
            blocks.append(DisplayBlock(kind, "\n".join(lines[start + 1:index]),
                                       start + 1, index + 1))
            index += 1
            continue
        index += 1
    return blocks


def select_equations(source: pathlib.Path, specs: Iterable[EquationSpec] = EQUATIONS) -> dict[str, DisplayBlock]:
    """Bind every manifest entry to exactly one source display block."""
    blocks = extract_display_blocks(source)
    selected: dict[str, DisplayBlock] = {}
    for spec in specs:
        matches = [block for block in blocks if spec.anchor in block.body]
        if len(matches) != 1:
            raise ValueError(
                f"{spec.ident}: anchor {spec.anchor!r} matched {len(matches)} display blocks"
            )
        selected[spec.ident] = matches[0]
    return selected


def _latex_document(ident: str, block: DisplayBlock, border: int, with_label: bool) -> str:
    body = block.standalone().rstrip()
    if with_label:
        body += "\n\\par\\smallskip{\\footnotesize\\texttt{" + ident + "}}"
    return (
        f"\\documentclass[border={border}pt]{{standalone}}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n"
    )


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_dimensions(path: pathlib.Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"PNG başlığı geçersiz: {path}")
    return struct.unpack(">II", data[16:24])


def _portable_path(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _source_record(
    source: pathlib.Path,
    selected: dict[str, DisplayBlock],
    specs: Iterable[EquationSpec] = EQUATIONS,
) -> dict:
    specs = tuple(specs)
    return {
        "path": _portable_path(source),
        "sha256": _sha256(source),
        "equations": [
            {
                "id": spec.ident,
                "title": spec.title,
                "anchor": spec.anchor,
                "source_lines": [selected[spec.ident].start_line, selected[spec.ident].end_line],
                "body_sha256": selected[spec.ident].body_sha256(),
            }
            for spec in specs
        ],
    }


def _index_html(source: pathlib.Path, records: list[dict], dpi: int) -> str:
    cards = []
    for record in records:
        ident = record["id"]
        title = html.escape(record["title"])
        lines = record["source_lines"]
        cards.append(
            "<figure class=\"equation\">"
            f"<img src=\"{html.escape(ident)}.png\" alt=\"{title}\" width=\"{record['pixel_width']}\" height=\"{record['pixel_height']}\" loading=\"lazy\">"
            f"<figcaption><strong>{html.escape(ident)}</strong> — {title}"
            f"<small>core_section.tex:{lines[0]}–{lines[1]}</small></figcaption>"
            "</figure>"
        )
    source_label = html.escape(_portable_path(source))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Article equation gallery</title>
<style>
:root {{ color-scheme: light dark; --bg: #f5f1e8; --fg: #1b2a41; --muted: #687386; --card: #fffdf7; --line: #d7d1c3; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #161b25; --fg: #edf0f4; --muted: #aab3c0; --card: #202733; --line: #3a4555; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 2rem; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 1200px; margin: auto; }}
h1 {{ margin-bottom: .25rem; }}
.meta {{ color: var(--muted); margin-top: 0; overflow-wrap: anywhere; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
figure {{ margin: 0; padding: 1rem; border: 1px solid var(--line); border-radius: 10px; background: var(--card); overflow: auto; }}
img {{ display: block; width: 100%; height: auto; min-height: 90px; object-fit: contain; }}
figcaption {{ margin-top: .75rem; color: var(--fg); }}
small {{ display: block; margin-top: .25rem; color: var(--muted); }}
</style>
</head>
<body><main>
<h1>Article equation gallery</h1>
<p class="meta">{len(records)} selected display equations · {dpi} DPI · source: <code>{source_label}</code></p>
<div class="grid">
{''.join(cards)}
</div>
</main></body></html>
"""


def _manifest_records(
    source: pathlib.Path,
    selected: dict[str, DisplayBlock],
    out: pathlib.Path,
    dpi: int,
    border: int,
    specs: Iterable[EquationSpec] = EQUATIONS,
) -> list[dict]:
    records = []
    for spec in specs:
        block = selected[spec.ident]
        png = out / f"{spec.ident}.png"
        png_width, png_height = _png_dimensions(png)
        records.append({
            "id": spec.ident,
            "title": spec.title,
            "anchor": spec.anchor,
            "source_lines": [block.start_line, block.end_line],
            "body_sha256": block.body_sha256(),
            "png": png.name,
            "png_sha256": _sha256(png),
            "pixel_width": png_width,
            "pixel_height": png_height,
        })
    return records


def check_sync(source: pathlib.Path, out: pathlib.Path) -> int:
    """Validate source anchors and, when present, generated artifact hashes."""
    try:
        selected = select_equations(source)
    except (OSError, ValueError) as exc:
        print(f"DENKLEM KAYNAK DRIFT: {exc}", file=sys.stderr)
        return 1
    manifest_path = out / "manifest.json"
    if not manifest_path.is_file():
        print(f"SYNC OK — {len(selected)} source display equations; manifest yok (ilk üretim bekleniyor)")
        return 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        by_id = {spec.ident: spec for spec in EQUATIONS}
        items = manifest.get("equations", [])
        ids = [item.get("id") for item in items]
        problems = []
        if manifest.get("source") != _portable_path(source):
            problems.append("source metadata")
        if manifest.get("source_sha256") != _sha256(source):
            problems.append("source hash")
        if len(ids) != len(set(ids)):
            problems.append("duplicate manifest id")
        if manifest.get("complete") is True and set(ids) != set(by_id):
            problems.append("incomplete full-gallery manifest")
        for item in items:
            ident = item.get("id")
            spec = by_id.get(ident)
            if spec is None:
                problems.append(f"unknown:{ident}")
                continue
            block = selected[ident]
            expected = {
                "id": ident,
                "title": spec.title,
                "anchor": spec.anchor,
                "source_lines": [block.start_line, block.end_line],
                "body_sha256": block.body_sha256(),
            }
            for key, value in expected.items():
                if item.get(key) != value:
                    problems.append(f"source:{ident}:{key}")
            png = out / item.get("png", "")
            if not png.is_file() or _sha256(png) != item.get("png_sha256"):
                problems.append(f"png:{ident}")
        if problems:
            print("SYNC DRIFT: " + ", ".join(problems), file=sys.stderr)
            return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MANIFEST OKUNAMADI: {exc}", file=sys.stderr)
        return 1
    print(f"SYNC OK — {len(items)} equation ve PNG hashleri eşleşti")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE,
                        help="canonical display-equation source")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT,
                        help="PNG gallery directory")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--border", type=int, default=4)
    parser.add_argument("--only", action="append", default=[],
                        help="render only this equation id (repeatable)")
    parser.add_argument("--with-label", action="store_true",
                        help="add the equation id below the rendered display")
    parser.add_argument("--source-date-epoch", default=os.environ.get(
        "SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH),
        help="fixed epoch passed to the TeX engine (default: 1700000000)")
    parser.add_argument("--check-sync", action="store_true",
                        help="validate source/manifest/PNG hashes without rendering")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if args.check_sync:
        return check_sync(source, out)
    try:
        selected = select_equations(source)
    except (OSError, ValueError) as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2

    requested = set(args.only)
    unknown = requested - set(selected)
    if unknown:
        print(f"HATA: bilinmeyen equation id: {sorted(unknown)}", file=sys.stderr)
        return 2
    chosen = [spec for spec in EQUATIONS if not requested or spec.ident in requested]
    if not chosen:
        print("HATA: --only ile seçim boş", file=sys.stderr)
        return 2

    engine = find_tex_engine()
    converter = find_pdf_to_png()
    if not engine:
        print("HATA: pdflatex/tectonic yok", file=sys.stderr)
        return 2
    if not converter:
        print("HATA: convert/pdftoppm/sips yok", file=sys.stderr)
        return 2

    out.mkdir(parents=True, exist_ok=True)
    epoch = str(args.source_date_epoch)
    if not re.fullmatch(r"\d+", epoch):
        print(f"HATA: SOURCE_DATE_EPOCH integer olmalı: {epoch!r}", file=sys.stderr)
        return 2
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    print(f"Araçlar: LaTeX={engine}, PDF→PNG={converter}, dpi={args.dpi}, epoch={epoch}")
    rendered = []
    failures = 0
    for spec in chosen:
        block = selected[spec.ident]
        png = out / f"{spec.ident}.png"
        try:
            with tempfile.TemporaryDirectory(prefix=f"equation_{spec.ident}_") as td:
                work = pathlib.Path(td)
                tex = work / f"{spec.ident}.tex"
                tex.write_text(_latex_document(spec.ident, block, args.border, args.with_label),
                               encoding="utf-8")
                if not compile_tex(engine, tex, work):
                    raise RuntimeError("TeX derlemesi başarısız")
                pdf = work / f"{spec.ident}.pdf"
                if not pdf_to_png(converter, pdf, png, args.dpi):
                    raise RuntimeError("PDF→PNG dönüşümü başarısız")
                strip_png_metadata(png)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[{spec.ident}] HATA: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"[{spec.ident}] OK → {png} ({png.stat().st_size} bayt)")
        rendered.append(spec)

    if failures or len(rendered) != len(chosen):
        return 1
    source_data = _source_record(source, selected, rendered)
    records = _manifest_records(source, selected, out, args.dpi, args.border, rendered)
    manifest = {
        "schema": 1,
        "source": source_data["path"],
        "source_sha256": source_data["sha256"],
        "dpi": args.dpi,
        "border": args.border,
        "with_label": args.with_label,
        "complete": len(rendered) == len(EQUATIONS),
        "equations": records,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    (out / "index.html").write_text(_index_html(source, records, args.dpi), encoding="utf-8")
    print(f"ÖZET: {len(rendered)} PNG + manifest.json + index.html → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
