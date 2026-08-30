#!/usr/bin/env bash
# Local one-command verification: load opam's environment, then run --full + K19.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v opam >/dev/null 2>&1; then
  printf 'HATA: opam bulunamadı; Coq K19 için opam kurulumu gerekli\n' >&2
  exit 2
fi

# `opam env` yalnızca mevcut shell'e eval edilir; kalıcı profil değiştirilmez.
eval "$(opam env)"

exec python3 "$SCRIPT_DIR/verify_delivery.py" \
  --dir "$SCRIPT_DIR" \
  --full \
  --coq-proof \
  "$@"
