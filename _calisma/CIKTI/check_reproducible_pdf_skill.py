#!/usr/bin/env python3
"""K6-DETERM adapter for the reproducible PDF skill reuse contract."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import reproducible_pdf_skill as skill  # noqa: E402


def check():
    required = ("cached == raw", "return (\"reuse\", raw)",
                "return (\"regenerate\", raw)", "return (\"skip\", raw)")
    source = (HERE / "reproducible_pdf_skill.py").read_text(encoding="utf-8")
    missing = [token for token in required if token not in source]
    if missing:
        print("FAIL: K6-DETERM skill reuse contract missing: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("PASS: K6-DETERM skill reuse contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
