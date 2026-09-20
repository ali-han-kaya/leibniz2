#!/usr/bin/env bash
# check_dashboard_typecheck.sh — apps/dashboard-next için tsc --noEmit kapısı.
#
# setup-pre-commit skill'inin "commit-anı typecheck" hedefinin zincir-uyarlaması
# (Husky yerine mevcut pre-commit zinciri):
#   - node_modules/tsconfig yoksa SKIP (exit 0) — ortam-bağımlı kapı ortam
#     yoksa bloke etmez (zincirin SKIP-kültürü).
#   - node_modules + tsconfig VARSA fail-closed: herhangi bir tip-hatası
#     commit'i bloke eder (READ-ONLY: yalnızca --noEmit).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$REPO/apps/dashboard-next"

if [ ! -x "$APP/node_modules/.bin/tsc" ] || [ ! -f "$APP/tsconfig.json" ]; then
  echo "check-dashboard-typecheck: tsc/tsconfig yok — SKIP"
  exit 0
fi

cd "$APP"
node_modules/.bin/tsc --noEmit
echo "check-dashboard-typecheck: OK"
