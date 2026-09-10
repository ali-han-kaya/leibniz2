#!/usr/bin/env python3
"""Fail when the shipped manuscript PDF predates its TeX source."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_TEX = Path(__file__).resolve().parent.parent / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17" / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17" / "ingiliz_empirizmi_v3.tex"
DEFAULT_PDF = DEFAULT_TEX.with_suffix(".pdf")


def check_freshness(tex: Path, pdf: Path) -> tuple[bool, str]:
    if not tex.is_file():
        return False, f"source TeX not found: {tex}"
    if not pdf.is_file():
        return False, f"shipped PDF not found: {pdf}"
    tex_mtime = tex.stat().st_mtime_ns
    pdf_mtime = pdf.stat().st_mtime_ns
    if tex_mtime > pdf_mtime:
        return False, f"source TeX is newer than shipped PDF: {tex} > {pdf}"
    return True, f"source/PDF freshness: PASS ({tex.name} <= {pdf.name})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tex", type=Path, default=DEFAULT_TEX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args()
    ok, message = check_freshness(args.tex, args.pdf)
    print(("PASS: " if ok else "FAIL: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
