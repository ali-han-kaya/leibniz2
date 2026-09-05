#!/bin/sh
# test_simulate_summary.sh — check_summary_writable.sh birim testi (POSIX).
#
# step_validate_summary'nin readonly assert'i check_summary_writable.sh'de
# TEK KAYNAK olarak durur (simulate_verify_job.sh çağırır). Bu test üç
# senaryoyu POSIX-uyumlu sabitler:
#   1. ok yazma  → dosya var + dolu + APPEND başarılı  → exit 0
#   2. read-only → chmod a-w (yazılamaz)              → exit 1
#   3. boş dosya → 0 bayt                             → exit 1
# Ayrıca eksik dosya → exit 1 ve kullanım hatası → exit 2.
#
# Kullanım: sh _calisma/CIKTI/test_simulate_summary.sh
# Exit: 0 = tüm senaryolar PASS; 1 = en az bir FAIL.
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CHECK="$SCRIPT_DIR/check_summary_writable.sh"
TMPDIR="${TMPDIR:-/tmp}"

pass=0
fail=0

# run_case <ad> <beklenen_exit> <hazırlık_kodu>
run_case() {
  name="$1"
  expected="$2"
  setup="$3"
  d=$(mktemp -d "$TMPDIR/simsum.XXXXXX") || { echo "FAIL: mktemp"; exit 1; }
  # shellcheck disable=SC2086
  eval "$setup"
  sh "$CHECK" "$d/summary.md" >/dev/null 2>&1
  rc=$?
  rm -rf "$d"
  if [ "$rc" -eq "$expected" ]; then
    echo "PASS: $name (exit $rc)"
    pass=$((pass + 1))
  else
    echo "FAIL: $name (beklenen $expected, alınan $rc)"
    fail=$((fail + 1))
  fi
}

# 1) ok yazma: var + dolu + APPEND edilebilir → 0
setup_ok='printf "📊 Durum panosu\n## Test\n" > "$d/summary.md"'
run_case "ok yazma (APPEND OK)" 0 "$setup_ok"

# 2) read-only: dosya var ama yazılamaz → 1
setup_ro='printf "📊 Durum panosu\n" > "$d/summary.md"; chmod a-w "$d/summary.md"'
run_case "read-only (chmod a-w)" 1 "$setup_ro"

# 3) boş dosya: 0 bayt → 1
setup_empty=': > "$d/summary.md"'
run_case "boş dosya (0 bayt)" 1 "$setup_empty"

# 4) eksik dosya: hiç yok → 1
run_case "eksik dosya" 1 "true"

# 5) kullanım hatası: argümansız → 2
sh "$CHECK" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 2 ]; then
  echo "PASS: kullanım hatası (exit $rc)"
  pass=$((pass + 1))
else
  echo "FAIL: kullanım hatası (beklenen 2, alınan $rc)"
  fail=$((fail + 1))
fi

echo ""
echo "ÖZET: $pass PASS, $fail FAIL"
if [ "$fail" -ne 0 ]; then
  exit 1
fi
exit 0
