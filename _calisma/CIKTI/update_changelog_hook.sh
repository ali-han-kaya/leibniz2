#!/usr/bin/env bash
# =============================================================================
# update_changelog_hook.sh — pre-commit hook: changelog tablolarını git log ile
# senkron eder (gen_changelog.py --update) ve değiştiyse stage eder.
#
# Rol: repo'nun İKİ YAZAN hook'undan biri (diğeri update-config, config'i
# yazar). Gecikmeli (lag-one) yazma zorunludur:
#
#   ÖLÇÜM (test_update_changelog_hook.py, gerçek gen_changelog + gerçek hook):
#   tablo commit hash'iyle anahtarlanır; hash ancak commit OLUŞTUKTAN SONRA
#   bilinir. --check (find_missing_commits) "tablodaki en yeni satırdan daha
#   yeni" commit'leri eksik sayar. Bu ikisi birleşince tablo, HER commit'ten
#   sonra tam olarak BİR commit geride kalır: okuma tarafı HEAD'i eksik sayar.
#   Dolayısıyla saf okuma kapısı + remedy YAPISAL OLARAK İMKÂNSIZDIR — bloklayan
#   satırın hash'i henüz var olmaz (remedy, aynı commit'te uygulanamaz).
#   Ölçüm: /tmp kanıtı yok; test her koşumda yeniden ölçer (tam-1-commit).
#
#   Model iki yazandır:
#     (1) BU hook: commit içinde eksik satırı onarır ve stage eder (yazar-1),
#     (2) `chore(changelog): <hash> satırını tabloya ekle` commit'i: kaydı
#         ayrı bir yazı olarak kapatır (yazar-2).
#   Elle remedy (okuma tarafı): python3 gen_changelog.py --update.
#
# Sıralama: .pre-commit-config.yaml'da commit-msg-style'den ÖNCE tanımlıdır;
# her commit'te koşar (always_run).
#
# Exit kodları:
#   0 = tablolar güncel (dokunmadı) VEYA güncellendi + stage edildi (commit devam)
#   1 = gen_changelog --update başarısız (bloke)
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

# DRIFT: git log'da tablolardan daha yeni commit'ler var → --update ile senkron et.
python3 "$SCRIPT_DIR/gen_changelog.py" --update >/dev/null 2>&1 || {
  echo "HATA: gen_changelog --update başarısız — changelog güncellenemedi." >&2
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
