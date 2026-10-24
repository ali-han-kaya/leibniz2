#!/usr/bin/env python3
"""Fail-closed skip budget for unittest logs.

Reads one or more unittest output logs, sums the `skipped=K` counts of every
`Ran N tests` summary block, and exits non-zero when the total exceeds the
budget. A log with no summary block is an error, not a pass: an empty or
truncated run must not look like zero skips.

Usage: check_skip_budget.py --budget-file FILE LOG [LOG ...]
Exit: 0 within budget, 1 over budget or no summary found, 2 usage error.
"""
import argparse
import re
import sys
from pathlib import Path

_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
_SUMMARY_RE = re.compile(r"^(OK|FAILED)(?: \(([^)]*)\))?$")
_SKIPPED_RE = re.compile(r"skipped=(\d+)")


def count_skips(text):
    """Return (summary_blocks, skipped_total) for one log text."""
    blocks = 0
    skipped = 0
    for m in _RAN_RE.finditer(text):
        rest = text[m.end():].split("\n", 1)
        rest = rest[1] if len(rest) > 1 else ""
        nxt = next((ln.strip() for ln in rest.splitlines() if ln.strip()), "")
        hit = _SUMMARY_RE.match(nxt)
        if hit is None:
            continue
        blocks += 1
        k = _SKIPPED_RE.search(hit.group(2) or "")
        skipped += int(k.group(1)) if k else 0
    return blocks, skipped


def read_budget(path):
    raw = Path(path).read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        raise ValueError("budget dosyası tek bir negatif olmayan tam sayı olmalı: %r" % raw)
    return int(raw)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--budget-file", required=True)
    ap.add_argument("logs", nargs="+")
    args = ap.parse_args(argv)
    try:
        budget = read_budget(args.budget_file)
    except (OSError, ValueError) as e:
        print("SKIP BUDGET FAIL: %s" % e, file=sys.stderr)
        return 2

    total_blocks = 0
    total_skipped = 0
    for log in args.logs:
        try:
            text = Path(log).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print("SKIP BUDGET FAIL: log okunamadı: %s" % e, file=sys.stderr)
            return 1
        blocks, skipped = count_skips(text)
        total_blocks += blocks
        total_skipped += skipped

    if total_blocks == 0:
        print("SKIP BUDGET FAIL: 'Ran N tests' özet bloğu yok — ölçüm yok", file=sys.stderr)
        return 1
    if total_skipped > budget:
        print(
            "SKIP BUDGET FAIL: %d atlanan test > bütçe %d (sayım %d özet bloğu)"
            % (total_skipped, budget, total_blocks),
            file=sys.stderr,
        )
        return 1
    print(
        "SKIP BUDGET OK: %d atlanan test <= bütçe %d (%d özet bloğu)"
        % (total_skipped, budget, total_blocks),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
