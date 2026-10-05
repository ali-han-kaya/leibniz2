#!/usr/bin/env bash
# =============================================================================
# update_changelog_hook.sh — pre-commit hook: changelog tablolarını git log ile
# senkron eder (gen_changelog.py --prune) ve değiştiyse stage eder.
#
# Neden: her yeni commit, changelog tablosuna bir satır ekler. Ama commit'in
# kendi hash'i ancak commit OLUŞTUKTAN SONRA bilinir — bu yüzden "check-only"
# bir kapı (--check) her zaman bir commit geride kalır ve sonraki commit'i
# haksız yere BLOKE EDER (chicken-and-egg). update-config deseni gibi bu hook
# da --prune ile tabloları senkron eder ve değiştiyse stage eder — böylece
# kapı hiç kırılmaz, tablolar her zaman HEAD'e kadar güncel olur.
#
# Sıralama: .pre-commit-config.yaml'da commit-msg-style'den ÖNCE tanımlıdır;
# her commit'te koşar (always_run).
#
# Exit kodları:
#   0 = tablolar güncel (dokunmadı) VEYA güncellendi + stage edildi (commit devam)
#   1 = gen_changelog --prune başarısız (bloke)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
README="$ROOT/README.md"
PUBLISH="$ROOT/docs/PUBLISH_SCENARIO.md"

# Önce --check: drift yoksa hiçbir şeye dokunma (byte-farkı + gereksiz stage
# üretme — update-config ile aynı mantık).
set +e
python3 "$SCRIPT_DIR/gen_changelog.py" --check >/dev/null 2>&1
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  # Drift yok — tablolar git log ile güncel. Dokunma.
  exit 0
fi

# DRIFT: eksik veya stale satırlar var → --prune ile güvenli biçimde senkron et.
# --prune hem eksik commit satırlarını ekler hem de git log'da bulunmayan
# (rewrite/rebase artığı) stale satırları temizler.
python3 "$SCRIPT_DIR/gen_changelog.py" --prune >/dev/null 2>&1 || {
  echo "HATA: gen_changelog --prune başarısız — changelog güncellenemedi." >&2
  exit 1
}

# Değişen tabloları stage et (yalnızca gerçekten değiştiyse).
changed=0
if ! git diff --quiet -- "$README"; then
  git add "$README"
  changed=1
fi
if ! git diff --quiet -- "$PUBLISH"; then
  git add "$PUBLISH"
  changed=1
fi

if [ "$changed" = "1" ]; then
  echo "ℹ️ changelog tabloları git log'a göre güncellendi ve stage edildi (README.md, docs/PUBLISH_SCENARIO.md)."
fi
exit 0
