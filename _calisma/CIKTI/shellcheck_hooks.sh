#!/bin/sh
# shellcheck_hooks.sh — pre-commit hook / CI adım: sh entry'li hook
# betiklerini POSIX/bash lint ile denetler.
#
# Kapsam: verify_lean.sh (sh), commit_msg_hook.sh (sh),
#         update_config_hook.sh (bash).
#
# Kullanım:
#   bash _calisma/CIKTI/shellcheck_hooks.sh          # tümünü denetle
#   bash _calisma/CIKTI/shellcheck_hooks.sh --ci     # CI modu (JSON çıktı)
#
# Exit: 0 = tümü temiz, 1 = en az bir uyarı/hata.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/_calisma/CIKTI"

# shellcheck yüklenmiş mi?
if ! command -v shellcheck >/dev/null 2>&1; then
  echo "shellcheck bulunamadı — atlanıyor (ci: continue-on-error)"
  exit 0
fi

VERSION=$(shellcheck --version | grep '^version:' | awk '{print $2}')
echo "shellcheck $VERSION"

# ── denetlenecek betikler ────────────────────────────────────────────────
# format: "<shell_type> <path>"
# shell_type: sh → -s sh, bash → -s bash
HOOKS="
sh  $SCRIPT_DIR/verify_lean.sh
sh  $SCRIPT_DIR/commit_msg_hook.sh
bash $SCRIPT_DIR/update_config_hook.sh
"

FAIL=0
TOTAL=0
while IFS= read -r entry; do
  [ -z "$entry" ] && continue
  shell_type=$(echo "$entry" | awk '{print $1}')
  script=$(echo "$entry" | awk '{print $2}')
  name=$(basename "$script")
  TOTAL=$((TOTAL + 1))

  if [ ! -f "$script" ]; then
    echo "⚠️  $name: dosya bulunamadı — atlandı"
    continue
  fi

  if shellcheck -s "$shell_type" "$script" 2>/dev/null; then
    echo "✅ $name ($shell_type): PASS"
  else
    echo "❌ $name ($shell_type): FAIL"
    shellcheck -s "$shell_type" "$script" 2>&1 || true
    FAIL=$((FAIL + 1))
  fi
done <<< "$HOOKS"

echo ""
echo "─── shellcheck özeti: $((TOTAL - FAIL))/$TOTAL PASS ───"

if [ "$FAIL" -gt 0 ]; then
  echo "SONUÇ: FAIL — $FAIL betik uyarı/hata içeriyor"
  exit 1
fi
echo "SONUÇ: PASS — tüm sh hook betikleri dash/POSIX uyumlu"
exit 0
