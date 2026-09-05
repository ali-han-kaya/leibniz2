#!/usr/bin/env python3
"""Run the plist gate and emit a compact, artifact-friendly summary."""
import contextlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(HERE, "test_plist_gate_exit.py")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    result = subprocess.run([sys.executable, "-m", "unittest", TEST],
                            capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output, end="")
    summary = next((line.strip() for line in output.splitlines()
                    if line.startswith("Ran ")), "tests unavailable")
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[PLIST-SUMMARY] check-plist-drift {status} — {summary}; "
          "TestPlistOutSidecar dahil", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
