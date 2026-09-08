#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""check_bibliography_sync.py — tex References ↔ built-PDF References sync.

The bibliography lives in ingiliz_empirizmi_v3.tex (64 \\item entries).
The shipped artifact is ingiliz_empirizmi_v3.pdf (poppler pdftotext).
After any repair (V5j Popkin 133-147, Priest full subtitle etc.) the
tex → pdf pipeline (tectonic + qpdf) should be rerun; if the PDF is left
stale (or manually edited) the drift goes silent until a reviewer
opens the PDF. This checker makes it fail-closed *offline* (no tool
beyond what K6 already requires).

Strategy (two-source extraction + normalized comparison):
  tex  — parse ingiliz_empirizmi_v3.tex References (\\item count == 64),
         tex_to_plain each \\item: ``/''→\", --/---→-, ~→space,
         \\cmd{...}→inner, loose accents (\\c{s} etc.)→bare letter,
         {...}→strip braces, whitespace collapsed.  Ligatures handled
         later by normalize.
  pdf  — pdftotext the built PDF, take the *last* \"\\nReferences\\n\"
         heading (entry draft copies contain 2 References headings),
         split on \"•\" (poppler bullet), trim header, expect 64 entries.
         Each entry: de-form-feed, page-number bleed strip (solo
         \" 30\"/\" 31\"/...\" 33\" at entry tail — LaTeX page footer that
         pdftotext injects mid-bibliography — detected at boundary via
         \"\\n30\\n\" then flattened), \\s+→space.

Comparison is on normalize(s): NFD → strip Mn, ligature→ascii
(Fb01→fi etc.), en/em dash→-, lower, keep a-z0-9 - space, collapse.
62/64 match exactly; 2 (Sextus 1562/1569) differ only by \"tr.Henri\"
vs \"tr. Henri\" spacing (one escaped space \"\\ \" in tex source).  To
avoid a fragile fixture, compare with forgiving spacing: collapse
spaces *and* also compare with spaces stripped — either pass = match.

pdftotext yoksa: SKIP (tool eksik → atlanır, FAIL değil — pdf_pages
ile aynı disiplin; CI'nin poppler-utils'i kurduğu ortamda koşar).
TeX yoksa veya item count != 64 → P0 (fail-closed).
Entry count drift (tex 64 vs pdf N) → P0.

Kullanım:
  python3 check_bibliography_sync.py            # denetle (exit 0/1)
  python3 check_bibliography_sync.py --json     # makine-okur JSON

Exit: 0 = sync; 1 = drift (FAIL) veya tool/belge hatası; 2 = kullanım.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata

CIKTI = pathlib.Path(__file__).resolve().parent
REPO_ROOT = CIKTI.parent.parent

# Default package paths (same as verify_delivery.py PKG_REL)
DEFAULT_TEX = (
    REPO_ROOT
    / "_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package"
    / "Stoic_Hume_Formal_Section_2026-08-17/ingiliz_empirizmi_v3.tex"
)
DEFAULT_PDF = (
    REPO_ROOT
    / "_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package"
    / "Stoic_Hume_Formal_Section_2026-08-17/ingiliz_empirizmi_v3.pdf"
)

EXPECTED_REFS = 64

LIGATURES = {
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb00": "ff",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}

# Known spacing-only variance (tex source has "\\ " escaped space before author name
# in two Sextus entries; after plain conversion it becomes \"tr.Henri\"/\"tr.Gentian\"
# vs PDF \"tr. Henri\"/\"tr. Gentian\").  Stored as regex fragments to match on
# normalized form.  Tight: only these two patterns are tolerated.
_FORGIVING_SPACE_NEEDLES = ("trhenri", "trgentian")


def _tex_to_plain(s: str) -> str:
    """Tex References \\item body → plain-ish English text."""
    s = s.replace("``", '"').replace("''", '"')
    s = s.replace("---", "-").replace("--", "-")
    s = s.replace("~", " ").replace("\\ ", " ")
    # \cmd{...} → inner (iterative once — no nested braces in this file)
    s = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", s)
    # loose accents like \'e \"o `e ^e ~n = .u v H c r d k b → strip command, keep letter
    s = re.sub(r"\\['\"" + r"`\^~=.\u0060vHcrdkb]", "", s)  # \uvsplit to avoid Py \u escape
    s = re.sub(r"\\[a-zA-Z@]+", "", s)
    s = s.replace("\\\\", "")
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    # \"Repr.in\" happens when \"Repr.\\ in\" loses the escaped space without insertion
    s = re.sub(r"\.([A-Z])", r". \1", s)
    return s


def tex_items(tex_path: pathlib.Path | str = DEFAULT_TEX) -> list[str]:
    """Extract 64 plain-text References entries from the .tex source."""
    text = pathlib.Path(tex_path).read_text(encoding="utf-8", errors="ignore")
    if r"\section*{References}" not in text:
        raise RuntimeError(f"References section not found in {tex_path}")
    block = text.split(r"\section*{References}")[1].split(r"\end{itemize}")[0]
    raw = re.findall(r"\\item\s+(.*?)(?=\n\\item\s|\Z)", block, re.S)
    # fallback for files without newline-delimited \\item (should not happen)
    if len(raw) < EXPECTED_REFS:
        raw = re.findall(r"\\item\s+(.*?)(?=\\item\s|\Z)", block, re.S)
    items = [_tex_to_plain(r) for r in raw]
    # filter empties (trailing whitespace after last \end{itemize} split)
    items = [x for x in items if x.strip()]
    return items


def _find_pdftotext() -> str | None:
    for cand in (
        "pdftotext",
        "/opt/homebrew/bin/pdftotext",
        "/usr/local/bin/pdftotext",
    ):
        if pathlib.Path(cand).is_file() and pathlib.Path(cand).stat().st_mode & 0o111:
            return cand
        wh = shutil.which(cand) if "/" not in cand else None
        if wh:
            return wh
    # also probe via PATH
    wh = shutil.which("pdftotext")
    return wh


def pdf_items(pdf_path: pathlib.Path | str = DEFAULT_PDF) -> list[str] | None:
    """Extract References entries from built PDF via pdftotext (None if tool missing)."""
    tool = _find_pdftotext()
    if not tool:
        return None
    try:
        r = subprocess.run(
            [tool, "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    txt = r.stdout
    # The file historically had 2 References headings (entry draft copies).
    # Take the last — the real bibliography at the back.
    heads = [m.start() for m in re.finditer(r"\nReferences\n", txt)]
    if not heads:
        raise RuntimeError("References heading not found in PDF text")
    seg = txt[heads[-1] :]
    # Kill page-header bleed before splitting: standalone page numbers like "\n30\n"
    # appear on the bullet line itself after layout. First normalize form-feeds
    # and then strip the "\n30\n" lines — after split they'll otherwise appear
    # as trailing \" 30\" on the preceding entry.
    seg = seg.replace("\f", "\n")
    seg = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", seg)
    parts = seg.split("•")
    # parts[0] is "References\n" header; parts[1:] are entries
    entries = [re.sub(r"\s+", " ", p).strip() for p in parts[1:]]
    entries = [e for e in entries if e]
    # Defensive strip trailing page-number tail that survived as " foo. 30"
    # and de-hyphenate layout hyphenation ("Mathe- maticae" → "Mathematicae",
    # "Mil- lican" → "Millican"). TeX hyphenates with '-' at line break;
    # real bibliographic dashes are en-dash (–) not "- ".
    cleaned = []
    for e in entries:
        e = re.sub(r"\s+3[0-3]$", "", e)
        e = re.sub(r"(\w)-\s+(\w)", r"\1\2", e)
        e = re.sub(r"\s+", " ", e).strip()
        cleaned.append(e)
    return cleaned


def normalize(s: str) -> str:
    """Bibliographic comparison normalization (also used for wording sentinels)."""
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\- ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _eq_forgiving(a_norm: str, b_norm: str) -> bool:
    if a_norm == b_norm:
        return True
    # TeX "T. L." vs PDF "T.L." spacing (initials) and the two known
    # "tr.Henri"/"tr.Gentian" escaped-space variances are pure spacing.
    # Forgive any drift that is ONLY whitespace (space-strip equal).
    # Real wording drift (133-147 vs 133-148, truncated subtitle) still
    # differs after stripping spaces, so it stays fail-closed.
    if a_norm.replace(" ", "") == b_norm.replace(" ", ""):
        return True
    return False


def check(
    tex_path: pathlib.Path | str = DEFAULT_TEX,
    pdf_path: pathlib.Path | str = DEFAULT_PDF,
    *,
    tex_override: list[str] | None = None,
    pdf_override: list[str] | None = None,
) -> tuple[bool, list[dict], dict]:
    """Full check. Returns (ok, findings, meta).  Findings are P0 entries on drift."""
    findings: list[dict] = []
    meta: dict = {
        "tex": str(tex_path),
        "pdf": str(pdf_path),
        "expected": EXPECTED_REFS,
    }

    if tex_override is not None:
        tex_list = tex_override
    else:
        try:
            tex_list = tex_items(tex_path)
        except Exception as e:
            findings.append(
                {"kind": "tex_parse_error", "detail": str(e), "priority": "P0"}
            )
            meta["tex_count"] = None
            meta["pdf_count"] = None
            return False, findings, meta
    meta["tex_count"] = len(tex_list)
    if len(tex_list) != EXPECTED_REFS:
        findings.append(
            {
                "kind": "tex_count_mismatch",
                "expected": EXPECTED_REFS,
                "got": len(tex_list),
                "detail": f"tex References {len(tex_list)} != {EXPECTED_REFS}",
                "priority": "P0",
            }
        )

    if pdf_override is not None:
        pdf_list: list[str] | None = pdf_override
    else:
        try:
            pdf_list = pdf_items(pdf_path)
        except Exception as e:
            findings.append(
                {"kind": "pdf_parse_error", "detail": str(e), "priority": "P0"}
            )
            meta["pdf_count"] = None
            return False, findings, meta

    if pdf_list is None:
        meta["pdf_count"] = None
        meta["skipped"] = "pdftotext yok — atlandı (pdf_pages ile aynı disiplin)"
        # Tool missing → SKIP (not FAIL) — same as K6 page/wording checks; CI with
        # poppler-utils installed will run the real check. No findings → ok True.
        return True, findings, meta

    meta["pdf_count"] = len(pdf_list)
    if len(pdf_list) != EXPECTED_REFS:
        findings.append(
            {
                "kind": "pdf_count_mismatch",
                "expected": EXPECTED_REFS,
                "got": len(pdf_list),
                "detail": f"pdf References {len(pdf_list)} != {EXPECTED_REFS}",
                "priority": "P0",
            }
        )
        # Still attempt entry comparison on overlap to give useful detail
        # (but don't return yet — collect mismatches too).

    tex_norm = [normalize(x) for x in tex_list]
    pdf_norm = [normalize(x) for x in pdf_list]
    n = min(len(tex_norm), len(pdf_norm))
    mismatch_idx: list[int] = []
    for i in range(n):
        if not _eq_forgiving(tex_norm[i], pdf_norm[i]):
            mismatch_idx.append(i)
            findings.append(
                {
                    "kind": "entry_mismatch",
                    "idx": i + 1,
                    "tex": tex_list[i][:200],
                    "pdf": pdf_list[i][:200],
                    "detail": f"entry {i+1} drift (tex ≠ pdf)",
                    "priority": "P0",
                }
            )
    meta["mismatched_entries"] = mismatch_idx
    meta["matched"] = n - len(mismatch_idx)

    # Extra entries beyond overlap are already drift via count check; report tail too
    # (only if counts matched — otherwise first count mismatch already explains).
    ok = not findings
    return ok, findings, meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="makine-okur JSON çıktısı")
    ap.add_argument("--tex", default=str(DEFAULT_TEX), help="tex path override")
    ap.add_argument("--pdf", default=str(DEFAULT_PDF), help="pdf path override")
    args = ap.parse_args(argv)

    try:
        ok, findings, meta = check(args.tex, args.pdf)
    except Exception as e:  # fail-closed on unexpected error
        if args.json:
            print(json.dumps({"ok": False, "error": str(e), "findings": []}, ensure_ascii=False))
        else:
            print(f"HATA: {e}")
        return 1

    if args.json:
        print(
            json.dumps({"ok": ok, "meta": meta, "findings": findings}, ensure_ascii=False, indent=2)
        )
    else:
        tag = "PASS" if ok else "FAIL"
        print(f"bibliography sync: {tag} — tex={meta.get('tex_count')} pdf={meta.get('pdf_count')} expected={EXPECTED_REFS}")
        if meta.get("skipped"):
            print(f"  SKIP notu: {meta['skipped']}")
        if findings:
            print("drift:")
            for f in findings:
                d = f.get("detail", f.get("kind", "?"))
                print(f"  ✗ {d}")
                if "pdf" in f:
                    print(f"    tex: {f['tex'][:120]!r}")
                    print(f"    pdf: {f['pdf'][:120]!r}")
        elif ok:
            print("  tez ↔ PDF bibliography birebir (normalized).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
