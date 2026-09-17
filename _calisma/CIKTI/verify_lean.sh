#!/bin/sh
# K9: Lean 4 reduct-invariance door — fail-closed.
# lean arama sırası: elan toolchain pin'i (lean-toolchain) → PATH →
# /opt/homebrew/bin → ~/.elan/bin. NOT: pİnsiz `lean --version` çağrısı
# elan'ı indirgeme moduna sokabilir (offline'da askıda kalır); bu yüzden
# pin'li toolchain bin'i ÖNCE denenir ve --version stdin kapalı koşar.
set -e

LEAN_DIR="$(dirname "$0")/../lean_reduct"
LEAN_TOOLCHAIN=""
if [ -f "$LEAN_DIR/lean-toolchain" ]; then
  LEAN_TOOLCHAIN="$(cat "$LEAN_DIR/lean-toolchain")"
fi

# 1) Repo pin'i: leanprover/lean4:v4.14.0 →
#    ~/.elan/toolchains/leanprover--lean4---v4.14.0/bin/lean
#    (elan dizin adı: '/' → '-', ':' → '---')
if [ -n "$LEAN_TOOLCHAIN" ]; then
  _tc_slug="$(echo "$LEAN_TOOLCHAIN" | sed 's/:/---/g; s/\//-/g; s/leanprover-/leanprover--/')"
  _candidate="$HOME/.elan/toolchains/$_tc_slug/bin/lean"
  if [ -x "$_candidate" ] && </dev/null "$_candidate" --version >/dev/null 2>&1; then
    LEAN="$_candidate"
  fi
fi

# 2) PATH + bilinen konumlar
if [ -z "${LEAN:-}" ]; then
  for _candidate in lean /opt/homebrew/bin/lean "$HOME/.elan/bin/lean"; do
    if [ -x "$_candidate" ] && </dev/null "$_candidate" --version >/dev/null 2>&1; then
      LEAN="$_candidate"
      break
    fi
  done
fi

if [ -z "${LEAN:-}" ]; then
  echo "lean kurulu değil — brew install elan-init && elan toolchain install leanprover/lean4:stable"
  exit 1
fi

"$LEAN" "$LEAN_DIR/ReductInvariance.lean"
