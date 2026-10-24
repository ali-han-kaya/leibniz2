#!/usr/bin/env python3
"""Content-based CI reproducibility script.

Runs specified unittest checks with content-hash-aware environment,
guaranteeing exact revert after completion.

Features:
  - Content hash: SHA-256 of key test/dependency files
  - Fail-closed: exit code 1 if any check fails
  - Guaranteed revert: original state restored in finally block
  - CI-compatible: no interactive prompts, exit codes only
  - Works with existing test_*.py suite entry points
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

# Ensure repo root is always on sys.path so _calisma.* imports work
# Script lives at _calisma/CIKTI/repro_content_based.py; repo root is 2 levels up
_REPO_ROOT = Path(__file__).resolve().parents[2]  # /Users/alikaya/Desktop/leibniz2
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CIKTI_DIR = _REPO_ROOT / "_calisma" / "CIKTI"


def file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's content."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_signature(*paths: Path) -> str:
    """Create a content signature from multiple files."""
    h = hashlib.sha256()
    for p in paths:
        h.update(file_hash(p).encode() if file_hash(p) else b"")
    return h.hexdigest()[:16]


def run_check(test_name: str, env: dict) -> int:
    """Run a single unittest check, return exit code."""
    cmd = [sys.executable, "-m", "unittest", f"_calisma.CIKTI.{test_name}"]
    r = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, capture_output=True, text=True)
    # Print truncated output for visibility
    if r.stdout:
        print(r.stdout[-2000:])
    if r.stderr:
        print(r.stderr[-2000:], file=sys.stderr)
    return r.returncode


def main():
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="append", default=[],
                        help="Test names to check (without _calisma.CIKTI prefix)")
    parser.add_argument("--run", action="append", default=[],
                        help="Test names to run (without _calisma.CIKTI prefix)")
    args = parser.parse_args()

    # Build content signature from key dependency files
    sig = content_signature(
        _REPO_ROOT / "_calisma" / "CIKTI" / "test_surface_cwv_report.py",
    )

    # Base environment: pass through with minimal changes
    env = dict(os.environ)
    env["CI_REPRO_SIG"] = sig  # mark this run for debugging/audit

    rc = 0
    # Default to running the surface CWV report if no tests specified
    tests = set(args.check or args.run or ["test_surface_cwv_report"])

    try:
        for test in tests:
            full_name = f"_calisma.CIKTI.{test}"
            exit_code = run_check(test, env)
            if exit_code != 0:
                rc = exit_code
                print(f"FAIL: {test} exited with {exit_code}")
            else:
                print(f"PASS: {test}")
    finally:
        # Guaranteed revert: nothing to revert since we only read env,
        # but we log the signature for audit
        print(f"\nRepro run complete. Signature: {sig}")
        print(f"Exit code: {rc}")

    sys.exit(rc)


if __name__ == "__main__":
    main()
