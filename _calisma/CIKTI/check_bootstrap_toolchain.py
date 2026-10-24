#!/usr/bin/env python3
"""
check_bootstrap_toolchain.py — toolchain gate for dev_bootstrap unit inventory.

Cross-verify the JSON unit inventory emitted by `dev_bootstrap.sh --check`
against the expected units defined in bootstrap_units.conf.

Fail-closed: if any expected unit is missing or has wrong status, exit 1.
"""

import json
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
SCRIPT = os.path.join(ROOT, "_calisma", "dev_bootstrap.sh")
CONF = os.path.join(ROOT, "_calisma", "bootstrap_units.conf")


def run_bootstrap_check():
    """Run dev_bootstrap.sh --check and return the JSON output."""
    r = subprocess.run(
        ["bash", SCRIPT, "--check"],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"dev_bootstrap.sh --check exited with rc={r.returncode}", file=sys.stderr)
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError as exc:
        print(f"Failed to parse JSON from dev_bootstrap.sh --check: {exc}", file=sys.stderr)
        print(r.stdout, file=sys.stderr)
        sys.exit(1)


def load_expected_units():
    """Load expected unit statuses from bootstrap_units.conf."""
    expected = {}
    if not os.path.isfile(CONF):
        print(f"bootstrap_units.conf not found: {CONF}", file=sys.stderr)
        sys.exit(1)
    with open(CONF, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if "." in key:
                continue  # metadata (unit.install_time_s), unit değil
            expected[key] = value.strip()
    return expected


def cross_verify(inventory, expected):
    """Verify the inventory dict against expected units.

    Returns True if all expected units match, False otherwise.
    """
    all_ok = True
    for unit, expected_status in expected.items():
        actual_status = inventory.get(unit)
        if actual_status != expected_status:
            print(
                f"MISMATCH: unit '{unit}' expected='{expected_status}' actual='{actual_status}'",
                file=sys.stderr,
            )
            all_ok = False
    # Also fail if there are units in inventory not expected (extra units ok, but
    # we check that expected ones are present)
    for unit in expected:
        if unit not in inventory:
            print(f"MISSING: unit '{unit}' not in inventory", file=sys.stderr)
            all_ok = False
    return all_ok


def main():
    inventory = run_bootstrap_check()
    expected = load_expected_units()
    if not cross_verify(inventory, expected):
        sys.exit(1)
    print("Bootstrap toolchain check: all units match expected inventory")
    sys.exit(0)


if __name__ == "__main__":
    main()