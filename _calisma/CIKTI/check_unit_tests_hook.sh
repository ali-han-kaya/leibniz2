#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --update ile test listesini _calisma/CIKTI
#    içindeki gerçek test_*.py dosyalarıyla senkron eder (yeni test dosyası
#    otomatik eklenir — elle liste bakımı yok) ve manifest'i stage eder.
# 2) Manifest listesindeki her test dosyasını venv python'la koşar; herhangi
#    bir başarısızlık commit'i BLOKE EDER (fail-closed).
#
# Neden ayrı script? Eski yapıda `for t in <17 isim>` hardcoded listesi
# .pre-commit-config.yaml entry'sine gömülüydü ve her yeni test dosyası elle
# eklenmek zorundaydı. Artık manifest tek kaynak: ~3s hedefi korunur, ortam-
# bağımlı testler EXCLUDE'da, yeni testler otomatik kapsanır.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$SCRIPT_DIR/check_unit_tests.list"

PY=python3
if [ -x "$ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$ROOT/_calisma/.venv_z3/bin/python"
fi

# 1) Senkron (auto-add yeni testler) — manifest değişirse stage edilir.
"$PY" "$SCRIPT_DIR/sync_check_unit_tests.py" --update >/dev/null 2>&1 || true

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