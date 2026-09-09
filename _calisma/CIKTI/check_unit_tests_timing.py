#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile
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
    _dir = os.path.dirname(os.path.abspath(args.out)) or "."
    _fd, _tmp = tempfile.mkstemp(dir=_dir, prefix=os.path.basename(args.out) + ".tmp.")
    try:
        with os.fdopen(_fd, "w", encoding="utf-8") as _f:
            _f.write(json.dumps(report, indent=2) + "\n")
        os.replace(_tmp, args.out)
    except BaseException:
        try:
            os.unlink(_tmp)
        except OSError:
            pass
        raise
    if report["timeout_exceeded"]:
        print(f"check-unit-tests timeout: {duration:.3f}s > {args.limit:.3f}s")
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
