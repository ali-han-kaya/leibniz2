#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --check (fail-closed): manifest + HOOK_COVERAGE
#    drift'ini BLOKLAR — sessiz auto-fix YOK. Repo invariant'ı:
#    repo'da üç yazan hook vardır (update-config, check-changelog-sync,
#    check-skills-index); bu kapı okuma-hook'tur. Gecikmeli (lag-one) changelog yazımı bu kapıya değil,
#    check-changelog-sync'a aittir — tablo hash'le anahtarlıdır ve hash ancak
#    commit sonrası bilinir (bkz. update_changelog_hook.sh başlığı). Drift
#    varsa remedy gösterilir (sync --update) ve commit engellenir.
# 2) Manifest listesindeki her test dosyası venv python'la koşar; herhangi
#    bir başarısızlık commit'i BLOKE EDER (fail-closed).
#    HIZLI YOL: run_unit_tests_parallel.py dosyaları EŞZAMANLI koşar, ama yine
#    her dosya KENDİ yorumlayıcısında (paylaşılan süreç YOK — izolasyon
#    sözleşmesi, test_select_affected_tests.TestHookPerFileIsolation). Hızlı
#    yol PARALLEL_BUDGET_S duvar-saati bütçesini aşarsa (rc=3), çalışmazsa ya
#    da CHECK_UNIT_TEST_JOBS=1 ise sarmalayıcı dosya-başına SIRALI koşuma
#    düşer; sıralı yol en katı yoldur (zaman aşımı yok, asılı süit yine koşar).
#    Hızlı yolda kırmızı çıkan dosya o süreçte KESİN değildir: eşzamanlı bir
#    komşu dosya ortak araç kümesini kısa süre oynatırsa sahte kırmızı doğar
#    (ölçüldü: test_dev_bootstrap gerçek .venv_z3'yü ~1 sn gizler → komşu dosya
#    ENOENT alır). Bu yüzden kırmızı, izole koşuda DOĞRULANIR; orada da
#    kırmızıysa rapor kırmızıdır, yeşile dönerse UYARI basılır. CHECK_UNIT_TEST_JOBS=1
#    bu doğrulamayı tümden atlar (tek-koşum sözleşmesi).
# 3) rc=0 tek başına PASS değildir: her dosyanın çıktısı geçici bir loga
#    alınır ve check_zero_check_fail_open.py --unittest-log ile sınıflanır.
#    Sınıflandırıcı sonucu vacuous (0 gerçek test) ise dosya PASS değil
#    FAILED'dır — süiti tamamen atlanan dosya sessizce yeşil kalamaz.
#    Kısmi skip PASS'tir, ama test/skip sayıları raporlanır: her dosya için
#    ve toplamda kaç test koştuğu, kaçının atlandığı görünür.
#    İSTİSNA (ölçümlü, kararlı): check_zero_check_fail_open.
#    CI_FULL_SKIP_ALLOWANCE kayıtlı dosyanın "Ran N + skipped=N" tam-skip'i
#    ALLOWED (rc=0) sayılır ve görünür notla basılır — karar tablosu:
#    docs/CI_GATE_TRIAGE.md "Environment-skip legitimacy". Kayıtsız tam-skip
#    ve ölçüm yokluğu (Ran satırı eksik) asla allowlist ile kurtarılmaz.
#    Ölçüm -v logundan test-başına "... ok" satırlarıyla yapılır: özet
#    "Ran - skipped" aritmetiği setUpClass sahte-skip'inde sahte vakuum
#    üretir (webkit smoke vakası); -v'siz (eski) loglarda aritmetiğe düşülür.
#
# Neden ayrı script? Eski yapıda `for t in <17 isim>` hardcoded listesi
# .pre-commit-config.yaml entry'sine gömülüydü; artık manifest tek kaynak.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$SCRIPT_DIR/check_unit_tests.list"
RUNNER="$SCRIPT_DIR/run_unit_tests_parallel.py"

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

# Sınıflandırıcı, çıktının "Ran N / OK (skipped=K)" özetini okur; eksik
# dosya = ölçülemez koşum = FAIL (fail-closed).
ZERO_GATE="$SCRIPT_DIR/check_zero_check_fail_open.py"
if [ ! -f "$ZERO_GATE" ]; then
  echo "HATA: check_zero_check_fail_open.py yok — rc=0 tek başına PASS sayılamaz." >&2
  exit 1
fi

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/check-unit-tests.XXXXXX")" || {
  echo "HATA: geçici log dizini açılamadı." >&2
  exit 1
}
trap 'rm -rf "$tmpdir"' EXIT

num_or_zero() {
  case "$1" in
    '' | *[!0-9]*) echo 0 ;;
    *) echo "$1" ;;
  esac
}

# Manifest girişi → dosya adı (`.py` bir kez sıyrılır) ve log/rc yolu.
entry_name() {
  printf '%s' "${1%.py}"
}

entry_slug() {
  local t
  t="$(entry_name "$1")"
  printf '%s' "${t//\//_}"
}

log_for() { printf '%s/%s.log' "$tmpdir" "$(entry_slug "$1")"; }
rc_for() { printf '%s/%s.rc' "$tmpdir" "$(entry_slug "$1")"; }

# Son "Ran N tests" satırı = bu koşumun test sayısı (iç içe unittest
# koşumları olabilir; özet her zaman sonuncusudur).
count_ran() {
  num_or_zero "$(sed -nE 's/^Ran ([0-9]+) tests? in .*/\1/p' "$1" | tail -1)"
}

# "OK (skipped=K)" / "FAILED (... skipped=K)" satırındaki skip sayısı.
count_skipped() {
  num_or_zero "$(sed -nE 's/^(OK|FAILED) \(.*skipped=([0-9]+).*/\2/p' "$1" | tail -1)"
}

# Tek dosyayı izole yorumlayıcıda koş; çıktı loga, çıkış kodu rc dosyasına.
# Manifest girişleri `.py` uzantılıdır; pattern'e bir kez daha `.py` eklemek
# `test_X.py.py` üretir → 0 test eşleşir. Python 3.12+ boş discovery'de exit 5
# döndürdüğünden hook CI'da 49/49 BAŞARISIZ olur; 3.9-3.11'de ise 0 testle
# "PASS" diye sessizce hiçbir şey koşmazdı. Uzantı sıyrılıp canonical
# `-p "$name.py"` pattern'i kullanılıyor.
run_one_file() {
  local entry="$1"
  local name log rc_file status
  name="$(entry_name "$entry")"
  log="$(log_for "$entry")"
  rc_file="$(rc_for "$entry")"
  # -v zorunlu: sınıflandırıcı test-başına "... ok" satırlarını sayar
  # (özet Ran-skipped aritmetiği setUpClass sahte-skip'inde sahte vakuum
  # üretir — bkz. check_zero_check_fail_open.classify_unittest_log).
  if "$PY" -m unittest discover -s _calisma/CIKTI -p "$name.py" -v >"$log" 2>&1; then
    status=0
  else
    status=$?
  fi
  printf '%s\n' "$status" >"$rc_file"
}

# Sıralı yol: rc dosyası olmayan her girişi (hızlı yolun tamamlayamadığı ya da
# hiç dokunmadığı dosyalar) kendi sürecinde koşar.
run_sequential_missing() {
  local t
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    case "$t" in \#*) continue ;; esac
    if [ ! -f "$(rc_for "$t")" ]; then
      run_one_file "$t"
    fi
  done < "$MANIFEST"
}

# 2a) Hızlı yol (bütçeli, dosya-başına izole süreç). CHECK_UNIT_TEST_JOBS=1
# bilinçli sıralı yoldur; sayı olmayan değer güvenli tarafa (1) düşer.
jobs_raw="${CHECK_UNIT_TEST_JOBS:-}"
jobs=0
case "$jobs_raw" in
  '') jobs=0 ;;
  *[!0-9]*) jobs=1 ;;
  *) jobs="$jobs_raw" ;;
esac

if [ "$jobs" -eq 1 ]; then
  echo "check-unit-tests: CHECK_UNIT_TEST_JOBS=1 — dosya-başına sıralı koşum." >&2
elif [ ! -f "$RUNNER" ]; then
  echo "check-unit-tests: hızlı yol yok (run_unit_tests_parallel.py) — dosya-başına sıralı koşum." >&2
else
  fast_ran=1
  set +e
  "$PY" "$RUNNER" --manifest "$MANIFEST" --logs-dir "$tmpdir" \
    --discover-dir _calisma/CIKTI --python "$PY" --jobs "$jobs" >&2
  runner_rc=$?
  set -e
  case "$runner_rc" in
    0) : ;;
    3) echo "check-unit-tests: hızlı yol tamamlanamadı (bütçe/başlatma) — kalan dosyalar sıralı koşuda." >&2 ;;
    *) echo "check-unit-tests: hızlı yol başarısız (rc=$runner_rc) — dosya-başına sıralı koşuma dönülüyor." >&2 ;;
  esac
fi

# 2b) Eksik kalan dosyalar: sıralı, zaman aşımı yok.
run_sequential_missing

# 2c) Hızlı yol kırmızısı = ön sonuç. İzole koşuda doğrulanır (sahte kırmızı:
# eşzamanlı komşu, ortak araç kümesini oynatmış olabilir). İzole sonuç
# geçerlidir; ilk rc sidecar'da saklanır, yeşile dönerse UYARI basılır.
if [ "${fast_ran:-0}" -eq 1 ]; then
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    case "$t" in \#*) continue ;; esac
    rc_file="$(rc_for "$t")"
    # Yalnız HIZLI YOLUN ürettiği sonuç doğrulanır; sıralı yolda koşan dosya
    # zaten izole koştu (ikinci kez koşmak yalnız süre kaybı olurdu).
    [ -f "$tmpdir/$(entry_slug "$t").fast" ] || continue
    [ -f "$rc_file" ] || continue
    fast_rc="$(tr -d '[:space:]' <"$rc_file")"
    [ "$fast_rc" = "0" ] && continue
    printf '%s\n' "$fast_rc" >"$tmpdir/$(entry_slug "$t").fastrc"
    echo "check-unit-tests: $(entry_name "$t") — hızlı yolda kırmızı, izole koşuda doğrulanıyor." >&2
    run_one_file "$t"
  done < "$MANIFEST"
fi

# 2d) Rapor + 3) sınıflandırma. rc dosyası yoksa dosya koşulmamıştır: PASS yok.
fails=0
total=0
tests=0
skipped_total=0
while IFS= read -r t; do
  [ -z "$t" ] && continue
  case "$t" in \#*) continue ;; esac
  total=$((total + 1))
  name="$(entry_name "$t")"
  log="$(log_for "$t")"
  rc_file="$(rc_for "$t")"

  reason=""
  rc=""
  cls_out=""
  if [ ! -f "$rc_file" ]; then
    reason="koşum kaydı yok — dosya hızlı/sıralı yolda koşmadı"
  else
    rc="$(tr -d '[:space:]' <"$rc_file")"
    case "$rc" in
      '' | *[!0-9]*) reason="koşum kaydı bozuk (rc='$rc')" ;;
    esac
  fi

  fastrc_file="$tmpdir/$(entry_slug "$t").fastrc"
  if [ -f "$fastrc_file" ] && [ "$rc" = "0" ]; then
    fast_rc="$(tr -d '[:space:]' <"$fastrc_file")"
    if [ "$fast_rc" != "0" ]; then
      echo "check-unit-tests: UYARI $name — hızlı yolda rc=$fast_rc, izole koşuda yeşil; izole sonuç geçerli." >&2
    fi
  fi

  ran=0
  skipped=0
  if [ -f "$log" ]; then
    ran="$(count_ran "$log")"
    skipped="$(count_skipped "$log")"
  fi
  tests=$((tests + ran))
  skipped_total=$((skipped_total + skipped))

  if [ -z "$reason" ] && [ "$rc" -ne 0 ]; then
    reason="unittest rc=$rc"
  fi
  if [ -z "$reason" ] && ! cls_out="$("$PY" "$ZERO_GATE" --unittest-log "$log" --suite "$t" 2>&1)"; then
    # Sınıflandırıcı rc=0'ı doğrulayamadı: vakuum / ölçüm yok / okunamaz log.
    reason="${cls_out%%$'\n'*}"
    [ -n "$reason" ] || reason="sınıflandırıcı doğrulamadı"
  fi

  if [ -n "$reason" ]; then
    fails=$((fails + 1))
    echo "FAILED: $name — $reason" >&2
    if [ -f "$log" ]; then
      cat "$log" >&2
    else
      echo "  (log yok: $log)" >&2
    fi
  elif [ "$skipped" -gt 0 ]; then
    echo "check-unit-tests: $name — $ran test, $skipped skip"
    case "$cls_out" in
      ALLOWED:*)
        echo "check-unit-tests: $name — izinli tam-skip (CI'da meşru): ${cls_out#ALLOWED: }"
        ;;
    esac
  fi
done < "$MANIFEST"

if [ "$fails" -gt 0 ]; then
  echo "check-unit-tests: $fails/$total test dosyası BAŞARISIZ — commit bloke." >&2
  echo "check-unit-tests: toplam $tests test, $skipped_total skip." >&2
  exit 1
fi
echo "check-unit-tests: $total test dosyası PASS — $tests test, $skipped_total skip."
exit 0