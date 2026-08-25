#!/usr/bin/env bash
# check_absolute_paths.sh — commit öncesi mutlak yolları yakala.
#
# yakalanan kalıplar:
#   /Users/<kullanıcı-adı>/...  (/Users/ci hariç — kanonik portable yol)
#   /home/<kullanıcı-adı>/...  (/home/linuxbrew hariç — CI ortam yolu)
#
# Kullanım:
#   bash _calisma/CIKTI/check_absolute_paths.sh [dosya...]
#   (pre-commit pass_filenames ile çağrılır — staleness yoksa boş liste)
#
# Exit: 0 = temiz, 1 = mutlak yol bulundu (commit bloke).

set -euo pipefail

FAIL=0
CHECKED=0

# Harici/yanlış pozitif dosyalar: .freebuff/, .git/, _calisma/TOOLKIT/, test fixtures.
SKIP_PREFIXES=".freebuff/ .git/ _calisma/TOOLKIT/"
# Hook kendi açıklamasında /Users/username挂ける — bunu skip et.
SKIP_FILES=".pre-commit-config.yaml docs/PRE_PUSH_DENETIM_RAPORU.md"

is_skipped() {
  local f="$1"
  for prefix in $SKIP_PREFIXES; do
    case "$f" in
      "$prefix"*) return 0 ;;
    esac
  done
  for sf in $SKIP_FILES; do
    [ "$f" = "$sf" ] && return 0
  done
  # Test dosyaları: fixture verisi内ki /Users/x/ gerçek yol değil.
  case "$f" in
    *test_*|*_test.py) return 0 ;;
  esac
  return 1
}

check_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  is_skipped "$file" && return 0

  CHECKED=$((CHECKED + 1))

  # /Users/<gerçek kullanıcı> pattern (wildcard /Users/.../ hariç)
  local users_matches
  users_matches=$(grep -nE '/Users/[a-zA-Z][a-zA-Z0-9_-]+/' "$file" 2>/dev/null | \
    grep -v '/Users/ci/' | \
    grep -v '/Users/ci$' || true)

  # /home/<gerçek kullanıcı> pattern (wildcard /home/.../ hariç)
  local home_matches
  home_matches=$(grep -nE '/home/[a-zA-Z][a-zA-Z0-9_-]+/' "$file" 2>/dev/null | \
    grep -v '/home/linuxbrew/' | \
    grep -v '/home/linuxbrew$' || true)

  if [ -n "$users_matches" ] || [ -n "$home_matches" ]; then
    echo "❌ $file — mutlak yol bulundu:"
    if [ -n "$users_matches" ]; then
      echo "$users_matches" | while IFS= read -r line; do
        echo "   /Users/: $line"
      done
    fi
    if [ -n "$home_matches" ]; then
      echo "$home_matches" | while IFS= read -r line; do
        echo "   /home/:  $line"
      done
    fi
    FAIL=$((FAIL + 1))
  fi
}

if [ $# -eq 0 ]; then
  # pre-commit pass_filenames: tüm takip edilen dosyaları tara
  _TMP=$(mktemp)
  git ls-files 2>/dev/null > "$_TMP" || true
  while IFS= read -r file; do
    check_file "$file"
  done < "$_TMP"
  rm -f "$_TMP"
else
  for file in "$@"; do
    check_file "$file"
  done
fi

echo ""
echo "─── absolute path denetimi: $CHECKED dosya tarandı ───"

if [ "$FAIL" -gt 0 ]; then
  echo "SONUÇ: FAIL — $FAIL dosyada mutlak yol bulundu"
  echo "  Çözüm: ~/.Desktop/... gibi yolları ~/Desktop/... veya göreli yola çevirin"
  exit 1
fi

echo "SONUÇ: PASS — mutlak yol yok"
exit 0
