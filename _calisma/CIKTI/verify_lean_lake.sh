#!/bin/sh
# K9: standalone Lean project build gate.
#
# This is intentionally separate from verify_lean.sh (which checks the
# reduct-invariance file) and from verify_delivery.py's combined K9 report.
# The orchestration DAG and GitHub Actions invoke this same script so a lake
# failure has one command-level source of truth.
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LEAN_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../lean_reduct" && pwd)"

if [ ! -f "$LEAN_DIR/lean-toolchain" ]; then
    echo "[K9-LAKE] FAIL — lean-toolchain yok: $LEAN_DIR/lean-toolchain" >&2
    exit 1
fi
if [ ! -f "$LEAN_DIR/lakefile.toml" ]; then
    echo "[K9-LAKE] FAIL — lakefile.toml yok: $LEAN_DIR/lakefile.toml" >&2
    exit 1
fi

# CI installs elan into ~/.elan/bin and adds it to GITHUB_PATH.  The fallback
# keeps the wrapper usable from a local shell without duplicating toolchain
# discovery logic in the workflow and DAG.
if ! command -v lake >/dev/null 2>&1 && [ -x "$HOME/.elan/bin/lake" ]; then
    PATH="$HOME/.elan/bin:$PATH"
    export PATH
fi
if ! command -v lake >/dev/null 2>&1; then
    echo "[K9-LAKE] FAIL — lake bulunamadı (elan kurulu olmalı)" >&2
    exit 1
fi

cd "$LEAN_DIR"
echo "[K9-LAKE] START — lake clean && lake build --wfail"
lake clean
lake build --wfail
echo "[K9-LAKE] PASS — Lean project build completed"
