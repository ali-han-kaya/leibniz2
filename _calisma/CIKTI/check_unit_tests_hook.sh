#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --check (fail-closed): manifest + HOOK_COVERAGE
#    drift'ini BLOKLAR — sessiz auto-fix YOK. Repo invariant'ı: yalnız
#    update-config tek yazan hook'tur; bu kapı okuma-hook'tur. Drift varsa
#    remedy gösterilir (sync --update) ve commit engellenir.
# 2) Manifest listesindeki her test dosyasını venv python'la koşar; herhangi
#    bir başarısızlık commit'i BLOKE EDER (fail-closed).
#
# Neden ayrı script? Eski yapıda `for t in <17 isim>` hardcoded listesi
# .pre-commit-config.yaml entry'sine gömülüydü; artık manifest tek kaynak.
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
if ! "$PY" "$SCRIPT_DIR/sync_check_unit_tests.py" --check >/dev/null; then
  echo "check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke." >&2
  echo "  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update" >&2
  exit 1
fi

# 2) Manifestten her test dosyasını koş.
if [ ! -f "$MANIFEST" ]; then
  echo "HATA: check_unit_tests.list bulunamadı — sync çalıştırılamadı." >&2
  exit 1
fi

fails=0
total=0
while IFS= read -r t; do
  [ -z "$t" ] && continue
  case "$t" in \#*) continue ;; esac
  total=$((total + 1))
  # Manifest girişleri `.py` uzantılıdır; pattern'e bir kez daha `.py`
  # eklemek `test_X.py.py` üretir → 0 test eşleşir. Python 3.12+ boş
  # discovery'de exit 5 döndürdüğünden hook CI'da 49/49 BAŞARISIZ olur;
  # 3.9-3.11'de ise 0 testle "PASS" diye sessizce hiçbir şey koşmazdı.
  # Uzantıyı sıyırıp canonical `-p "$t.py"` pattern'ini kullanıyoruz.
  t="${t%.py}"
  if ! "$PY" -m unittest discover -s _calisma/CIKTI -p "$t.py" >/dev/null 2>&1; then
    echo "FAILED: $t" >&2
    fails=$((fails + 1))
  fi
done < "$MANIFEST"

if [ "$fails" -gt 0 ]; then
  echo "check-unit-tests: $fails/$total test dosyası BAŞARISIZ — commit bloke." >&2
  exit 1
fi
echo "check-unit-tests: $total test dosyası PASS."
exit 0
