#!/usr/bin/env bash
# lint_actionlint.sh — actionlint wrapper (pre-commit hook).
#
# actionlint返回值:
#   0 = temiz
#   1 = hata (YAML syntax, job dependency, expression)
#   2 = yalnızca shellcheck info/hint (advisory)
#
# TÜM .github/workflows/*.yml'ı (glob) denetler — yeni workflow dosyaları
# kapıya otomatik girer (verify.yml CI adımıyla aynı tek kaynak glob).
# Pre-commit'te RC≤2 PASS (advisory), RC>2 FAIL. CI'daki advisory step ile
# birebir aynı davranış.

set -euo pipefail

AL=/tmp/actionlint
if [ ! -x "$AL" ]; then
  OS=$(uname -s | tr 'A-Z' 'a-z')
  ARCH=$(uname -m | sed 's/x86_64/amd64/')
  curl -sL "https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_${OS}_${ARCH}.tar.gz" \
    | tar xz -C /tmp actionlint
fi

RC=0
for WF in .github/workflows/*.yml; do
  WF_RC=0
  "$AL" --color "$WF" 2>&1 || WF_RC=$?
  if [ "$WF_RC" -gt "$RC" ]; then RC=$WF_RC; fi
  echo "actionlint: $WF → RC=$WF_RC"
done

if [ "$RC" -eq 0 ]; then
  echo "actionlint: PASS — tüm workflow'lar temiz"
  exit 0
elif [ "$RC" -le 2 ]; then
  echo "actionlint: PASS (RC=$RC, shellcheck info/hints only — advisory)"
  exit 0
else
  echo "actionlint: FAIL (RC=$RC)"
  exit 1
fi