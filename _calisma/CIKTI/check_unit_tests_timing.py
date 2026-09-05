#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=float, default=10.0)
    parser.add_argument("--out", default="check_unit_tests.json")
    args = parser.parse_args(argv)

    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pre_commit", "run", "check-unit-tests",
         "--all-files", "--show-diff-on-failure", "--color=never"],
        check=False,
    )
    duration = time.monotonic() - started
    report = {
        "hook": "check-unit-tests",
        "exit_code": result.returncode,
        "duration_s": round(duration, 3),
        "timeout_limit_s": args.limit,
        "timeout_exceeded": duration > args.limit,
        "ok": result.returncode == 0 and duration <= args.limit,
    }
    parent = os.path.dirname(os.path.abspath(args.out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    if report["timeout_exceeded"]:
        print(f"check-unit-tests timeout: {duration:.3f}s > {args.limit:.3f}s")
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
