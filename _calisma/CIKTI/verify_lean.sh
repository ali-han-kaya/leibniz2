#!/bin/sh
# K9: Lean 4 reduct-invariance door — fail-closed.
# Finds lean via PATH, /opt/homebrew/bin, or ~/.elan/bin.
set -e

for _candidate in lean /opt/homebrew/bin/lean "$HOME/.elan/bin/lean"; do
  if [ -x "$_candidate" ] && "$_candidate" --version >/dev/null 2>&1; then
    LEAN="$_candidate"
    break
  fi
done

if [ -z "$LEAN" ]; then
  echo "lean kurulu değil — brew install elan-init && elan toolchain install leanprover/lean4:stable"
  exit 1
fi

LEAN_DIR="$(dirname "$0")/../lean_reduct"
"$LEAN" "$LEAN_DIR/ReductInvariance.lean"
