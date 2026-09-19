#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: _calisma/.venv_z3 (pinned) + _calisma/pptx/node_modules +
# apps/dashboard-next/node_modules. Idempotent: kurulu araca dokunmaz.
# Kullanım: dev_bootstrap.sh [--check|--help]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
PINS=(z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0)

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  say "Kullanım: dev_bootstrap.sh [--check|--help]"
  say "  (bayraksız) araç-kümesini kur (idempotent)"
  say "  --check     araç-kümesi tam mı? rc=0/1 (fail-closed)"
  say "  --help      bu yardım"
}

node_modules_ok() {
  [ -d "$1/node_modules" ] && [ -f "$1/package.json" ]
}

venv_ok() {
  [ -x "$VENV_PY" ] || return 1
  local frozen
  frozen="$("$VENV_PY" -m pip freeze 2>/dev/null)" || return 1
  printf '%s\n' "$frozen" | grep -qx 'z3-solver==5.1.0.0' || return 1
  printf '%s\n' "$frozen" | grep -qx 'PyYAML==6.0.3' || return 1
  printf '%s\n' "$frozen" | grep -qx 'pre_commit==4.3.0' || return 1
}

case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --check)
    venv_ok || { say "CHECK FAIL: venv_z3 eksik veya pin-paritesiz"; exit 1; }
    node_modules_ok "$ROOT/_calisma/pptx" || { say "CHECK FAIL: _calisma/pptx/node_modules eksik"; exit 1; }
    node_modules_ok "$ROOT/apps/dashboard-next" || { say "CHECK FAIL: apps/dashboard-next/node_modules eksik"; exit 1; }
    say "CHECK OK"
    exit 0
    ;;
  "") ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if venv_ok; then
  say "venv_z3: up to date"
else
  say "venv_z3: kuruluyor (pinned: ${PINS[*]})"
  python3 -m venv "$VENV"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet "${PINS[@]}" || die "venv_z3 pip install"
fi

if node_modules_ok "$ROOT/_calisma/pptx"; then
  say "_calisma/pptx: up to date"
else
  say "_calisma/pptx: npm ci"
  npm ci --prefix "$ROOT/_calisma/pptx" || die "_calisma/pptx npm ci"
fi

if node_modules_ok "$ROOT/apps/dashboard-next"; then
  say "apps/dashboard-next: up to date"
else
  say "apps/dashboard-next: npm ci"
  npm ci --prefix "$ROOT/apps/dashboard-next" || die "apps/dashboard-next npm ci"
fi

say "BOOTSTRAP OK"
