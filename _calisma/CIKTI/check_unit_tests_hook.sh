#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --check (fail-closed): manifest + HOOK_COVERAGE
#    drift'ini BLOKLAR — sessiz auto-fix YOK. Repo invariant'ı:
#    repo'da üç yazan hook vardır (update-config, check-changelog-sync,
#    check-skills-index); bu kapı okuma-hook'tur. Gecikmeli (lag-one) changelog yazımı
#    bu kapıya değil, check-changelog-sync'a aittir — tablo hash'le anahtarlıdır ve hash
#    ancak commit sonrası bilinir (bkz. update_changelog_hook.sh başlığı). Drift
#    varsa remedy gösterilir (sync --update) ve commit engellenir.
# 2) Manifest listesindeki her test dosyasını venv python'la koşar; herhangi
#    bir başarısızlık commit'i BLOKE EDER (fail-closed).
#    GÜNCELLEME: Her dosya için test sayısı, atlanan test sayısı ve tamamen atlanan
#    dosyalar raporlanır. Sessiz atlama (skip-all) fark edilmezse kapıya girdiler.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$SCRIPT_DIR/check_unit_tests.list"

PY=python3
if [ -x "$ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$ROOT/_calisma/.venv_z3/bin/python"
fi

# 1) Senkron kapısı — fail-closed: drift commit'i bloklar (sessiz düzeltme yok).
if ! "$PY" "$SCRIPT_DIR/sync_check_unit_tests.py" --check >/dev/null 2>&1; then
  echo "check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke." >&2
  echo "  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update" >&2
  exit 1
fi

# 2) Manifestten her test dosyasını koş.
if [ ! -f "$MANIFEST" ]; then
  echo "HATA: check_unit_tests.list bulunamadı — sync çalıştırılamadı." >&2
  exit 1
fi

passes=0
fails=0
skipped=0
total=0
fully_skipped_files=""

while IFS= read -r t; do
  [ -z "$t" ] && continue
  case "$t" in \#*) continue ;; esac
  total=$((total + 1))

  # Manifest girdileri .py uzantılıdır; pattern'e bir kez daha .py eklemek
  # test_X.py.pattern'ini üretir → 0 test eşleşir. Python 3.12+ boş
  # discovery'de exit 5 döndürdüğünden hook CI'da 49/49 BAŞARISIZ olur;
  # 3.9-3.11'de ise 0 testle "PASS" diye sessizce hiçbir şey koşmazdı.
  # Uzantıyı sıyırıp canonical -p "test_X.py" pattern'ini kullanıyoruz.
  t_clean="${t%.py}"

  # Test dosyasını çalıştır ve test/atla sayısını topla
  output="$("$PY" -m unittest discover -s _calisma/CIKTI -p "${t_clean}.py" 2>&1 || true)"
  exit_code=$?

  # Test result parsing: extract test count and skip count from unittest output
  # Format: 'Ran N tests in M.ss' or similar
  if echo "$output" | grep -q 'Ran [0-9]* tests'; then
    # Extract numbers: "Ran X tests in Y.ss" or "Ran X tests in Ys"
    test_count=$(echo "$output" | grep 'Ran [0-9]* tests' | sed 's/.*Ran //' | sed 's/ tests.*//' | head -1)
    skip_count=$(echo "$output" | grep -i 'skipped' | sed -E 's/.*\(([0-9]+)\).*/\1/' | head -1 || echo "0")
    if [ -z "$test_count" ]; then
      test_count=0
    fi
    if [ -z "$skip_count" ]; then
      skip_count=0
    fi
  else
    test_count=0
    skip_count=0
  fi

  # Determine if tests passed, failed, or were skipped
  # unittest exit codes: 0 = all tests passed, 1 = some failures, 2 = error, 5 = no tests found
  if [ "$exit_code" -eq 0 ]; then
    # Exit 0 means all tests passed
    passes=$((passes + 1))
    status="PASS"
  elif [ "$exit_code" -eq 5 ] || [ "$exit_code" -eq 2 ]; then
    # Exit 5 = no tests found (e.g., file doesn't match pattern)
    # Exit 2 = error
    fails=$((fails + 1))
    status="FAIL"
  else
    # Exit 1 = some tests failed
    fails=$((fails + 1))
    status="FAIL"
  fi

  # Report per-file status
  if [ "$test_count" -gt 0 ]; then
    skip_str="$skip_count atlandı"
    if [ "$test_count" -ne 1 ]; then
      test_word="test"
    else
      test_word="test"
    fi
    echo "  [$status] $t_clean: $test_count $test_word — $skip_str"
  else
    # File was fully skipped (no tests found or all skipped)
    fully_skipped_files="${fully_skipped_files:+$fully_skipped_files } $t_clean"
    skipped=$((skipped + 1))
    echo "  [SKIP]  $t_clean: 0 test (tamamen atlandı/ortam yok) — $skip_count atlandı"
  fi

done < "$MANIFEST"

echo ""
echo "check-unit-tests: $passes/$total test dosyası PASS, $fails/$total BAŞARISIZ, $skipped/$total tamamen atlandı"

if [ "$fails" -gt 0 ] || [ "$skipped" -gt 0 ]; then
  echo "check-unit-tests: $fails/$total test dosyası BAŞARISIZ — commit bloke." >&2
  if [ -n "$fully_skipped_files" ]; then
    echo "  Tamamen atlanan dosyalar (ortam bağımlı/bulunamıyor): $fully_skipped_files" >&2
  fi
  exit 1
fi

echo "check-unit-tests: $total test dosyası PASS."
exit 0
