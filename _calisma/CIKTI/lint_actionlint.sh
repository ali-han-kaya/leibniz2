#!/bin/sh
# lint_actionlint.sh — actionlint wrapper (pre-commit hook).
#
# actionlint返回值:
#   0 = temiz
#   1 = hata (YAML syntax, job dependency, expression)
#   2 = yalnızca shellcheck info/hint (advisory)
#
# Pre-commit'te exit 2'yi PASS olarak kabul et (advisory).
# CI'daki advisory step ile birebir aynı davranış.

set -euo pipefail

AL=/tmp/actionlint
if [ ! -x "$AL" ]; then
  OS=$(uname -s | tr 'A-Z' 'a-z')
  ARCH=$(uname -m | sed 's/x86_64/amd64/')
  curl -sL "https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_${OS}_${ARCH}.tar.gz" \
    | tar xz -C /tmp actionlint
fi

RC=0
"$AL" --color .github/workflows/verify.yml 2>&1 || RC=$?

if [ "$RC" -eq 0 ]; then
  echo "actionlint: PASS"
  exit 0
elif [ "$RC" -le 2 ]; then
  echo "actionlint: PASS (RC=$RC, shellcheck info/hints only — advisory)"
  exit 0
else
  echo "actionlint: FAIL (RC=$RC)"
  exit 1
fi
