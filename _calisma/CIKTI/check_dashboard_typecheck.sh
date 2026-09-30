#!/usr/bin/env bash
# check_dashboard_typecheck.sh — apps/dashboard-next için tip kapıları.
#
# setup-pre-commit skill'inin "commit-anı typecheck" hedefinin zincir-uyarlaması
# (Husky yerine mevcut pre-commit zinciri). İki katman var:
#
#   1) `tsc --noEmit`  — GÖNDERİLEN kodun tip denetimi (READ-ONLY: emit yok).
#      node_modules/tsconfig yoksa SKIP (exit 0) — ortam-bağımlı kapı ortam
#      yoksa bloke etmez (zincirin SKIP-kültürü).
#
#   2) `test-d/run_type_tests.py` — SÖZLEŞME denetimi: pozitif `Assert<Equal<..>>`
#      iddiaları + `@ts-expect-error` negatif iddialar. İlk katman "bu atama
#      geçiyor mu" diye sorar; bu katman "sözleşme hâlâ AYNI mı" diye sorar.
#      İkincisi olmadan bir union'a varyant eklenmesi, bir alan adı değişmesi ya
#      da bir fallback'in düşmesi derlemeden geçer ve sessizce runtime'a sızar.
#      Koşucu kendi ön-koşullarını denetler: tsc/tsconfig yoksa SKIP eder.
#
# İkisi de fail-closed: bulgu varsa commit bloke olur.
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

if [ ! -f "$APP/test-d/run_type_tests.py" ]; then
  echo "check-dashboard-typecheck: tip-test koşucusu yok — SKIP (tip katmanı)"
  exit 0
fi

# Koşucunun kendi ayrıştırıcısı önce doğrulanır: parser sessizce bozulursa
# (örn. direktifleri hiç bulamazsa) iddialar denetlenmeden "yeşil" görünürdü.
python3 test-d/run_type_tests.py --selftest
python3 test-d/run_type_tests.py
echo "check-dashboard-typecheck: tip-testleri OK"
