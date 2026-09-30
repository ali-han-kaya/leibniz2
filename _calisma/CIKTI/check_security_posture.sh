#!/usr/bin/env bash
# =============================================================================
# check_security_posture.sh — güvenlik-duruşu kapısı (fail-closed).
#
# Kullanım:
#   check_security_posture.sh [roster.list]
# Varsayılan roster: check_security_posture.list (statik tier).
# Tarayıcı tier: check_security_browser.list (Chromium kurulu olmalı).
#
# Neden ayrı kapı? check_unit_tests.list "diskteki HER test dosyasını
# koşar" — güvenlik modülleri de orada koşar ama bir güvenlik regresyonu
# "unit test kırıldı" diye görünür. Bu kapı aynı modülleri ADIYLA koşar:
# kırılan modülün adı stderr'de tek tek yazılır.
#
# KAPININ BOŞ OLABİLEMEYECEĞİ DÖRT KURAL (fail-closed):
#   1) roster dosyası yoksa/okunamazsa        → hata
#   2) roster'da MIN_ENTRY'ten az giriş varsa → hata (toplu silme koruması)
#   3) roster'daki dosya diskte yoksa          → hata (sessiz "0 test")
#   4) BİR MODÜL SKIP EDİLDİYSE              → hata  ← en önemlisi
#
# (4) neden var: bu repodaki tarayıcı modülleri `skipIf(playwright yok)`
# ile ATLANIR. Skip, "yeşil" değil "koşmadı" demektir. Sayımı görmezden
# gelen bir kapı "2/2 PASS" deyip gerçekte hiç tarayıcı açmamış olur —
# güvenlik kanıtının sessizce kaybolması. Bu yüzden skip sayısı stderr'e
# yazılır ve kapı kapatılır.
#
# Dış ağa çıkmaz, dosya YAZMAZ (read-only gate).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROSTER="${1:-$SCRIPT_DIR/check_security_posture.list}"
ROSTER_NAME="$(basename "$ROSTER")"

MIN_ENTRY=2

PY=python3
if [ -x "$SCRIPT_DIR/../.venv_z3/bin/python" ]; then
  PY="$SCRIPT_DIR/../.venv_z3/bin/python"
fi

fail() { echo "check-security-posture: $*" >&2; exit 1; }

[ -f "$ROSTER" ] || fail "roster bulunamadi: $ROSTER (remedy: git checkout)"

entries=()
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  entries+=("$line")
done < "$ROSTER"

[ "${#entries[@]}" -ge "$MIN_ENTRY" ] || \
  fail "[$ROSTER_NAME] roster yetersiz: ${#entries[@]} giriş (en az $MIN_ENTRY). Toplu silme korumasi."

missing=()
for t in "${entries[@]}"; do
  [ -f "$SCRIPT_DIR/$t" ] || missing+=("$t")
done
[ "${#missing[@]}" -eq 0 ] || \
  fail "[$ROSTER_NAME] roster'daki dosya diskte yok: ${missing[*]}"

fails=()
skips=()
for t in "${entries[@]}"; do
  stem="${t%.py}"
  out="$("$PY" -m unittest discover -s "$SCRIPT_DIR" -p "$stem.py" 2>&1)" && rc=0 || rc=$?
  # unittest son satırda SKIP sayısını bildirir: "OK (skipped=2)",
  # "FAILED (failures=1, skipped=1)".
  skipped="$(printf '%s\n' "$out" \
    | sed -n 's/.*skipped=\([0-9]\{1,\}\).*/\1/p' | tail -1)"
  skipped="${skipped:-0}"
  if [ "$rc" -ne 0 ]; then
    echo "  FAIL  $t" >&2
    printf '%s\n' "$out" | tail -25 >&2
    fails+=("$t")
  elif [ "$skipped" -ne 0 ]; then
    echo "  SKIP  $t ($skipped test atlandi — kanit KOSMADI)" >&2
    skips+=("$t")
  else
    echo "  PASS  $t"
  fi
done

if [ "${#fails[@]}" -gt 0 ]; then
  echo "check-security-posture: ${#fails[@]}/${#entries[@]} modul BASARISIZ —" \
       "guvenlik durusu kirik. Kirilanlar: ${fails[*]}" >&2
  exit 1
fi

if [ "${#skips[@]}" -gt 0 ]; then
  echo "check-security-posture: ${#skips[@]} modul SKIP ETTI — kanit kosunmadi," \
       "dogrulanmis sayilmaz. Atlananlar: ${skips[*]}" >&2
  echo "  Browser tier icin Chromium gerekir:" >&2
  echo "    pip install playwright && playwright install chromium" >&2
  exit 1
fi

echo "check-security-posture [$ROSTER_NAME]: ${#entries[@]} modul PASS."
