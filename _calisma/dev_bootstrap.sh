#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: UNITS'teki araç-kümeleri (aşağıda) + --full ile temel batarya.
# Idempotent: kurulu araca dokunmaz.
#
# Kapsam neden GENİŞ: her unit, bataryadaki testlerin ortam-yok diye SKIP
# etmemesi için var. Kurulu olmayan bir bağımlılık testi KIRMIZIYA düşürmez
# (repo kültürü: "skip" + gerekçede kurulum reçetesi), ama taze checkout'ta
# yeşil görünen batarya sessizce kapsam kaybeder. Ölçülen eşleme:
#   venv_z3      → PIL/jsonschema/yaml isteyen testler (deck üretimi,
#                  config şema doğrulaması) — pin listesi aşağıda
#   pptx         → test_pptx_export
#   docx         → docx jeneratör/SKILL testleri
#   dashboard_next → style/typecheck/ui-contract süitleri
#   trend_db     → test_trend_db_js_runner (`node_modules/.bin/tsx`)
#   video        → test_check_video_typecheck (`node_modules/.bin/tsc`)
#   browsers     → 5 manifest test dosyası (keyboard-nav, escaping,
#                  hover-tooltip, cls-budget, cwv-report) playwright+chromium
#
# Neden batarya `--full`a bağlı, varsayılana değil: batarya manifesti bu
# betiğin sözleşme-testini (test_dev_bootstrap.py) de içerir; o test betiği
# no-args koşar. Batarya no-args yolunda olsaydı test → betik → batarya →
# test özyinelemesi olurdu. Varsayılan bu yüzden hızlı/kalıcı kalır
# (provision-only), uçtan-uca yeşil koşum `--full`dur.
# Kullanım: dev_bootstrap.sh [--full|--check|--help]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
PPTX="$ROOT/_calisma/pptx"
DOCX="$ROOT/_calisma/docx"
DASH="$ROOT/apps/dashboard-next"
TREND_DB="$ROOT/apps/trend-db"
VIDEO="$ROOT/_calisma/video"
# Pin listesi = bataryanın venv python'undan İSTEDİĞİ paketler (ölçülerek
# eşlendi): z3 (K8 kanalları) + pre_commit (hook zinciri) + yaml (kapı
# testleri) + jsonschema (`test_validate_config_schema` doğrulama yolu) +
# pillow (*_deck testleri `HAS_PIL` kapısı). Sürümler yereldeki yeşil
# venv'in `pip freeze` satırlarıdır; `check_venv_z3` birebir-eşitlik arar.
PINS=(z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0
      jsonschema==4.25.1 pillow==11.3.0)
# Tarayıcı katmanı pin'i: YALNIZ kurulumda kullanılır (ölçüm işlevsel, bkz.
# check_browsers). Sürüm CI'daki pinle aynı tutulur — sözleşme testi
# (test_dev_bootstrap.py → TestBrowserLayer) bu iki kaynağın ayrışmasını
# yakalar; ayrıca ikinci bir kaynak yaratmamak için bilinçli olarak
# verify.yml'deki `playwright==` pini ile eşitlenir.
BROWSER_PIN="playwright==1.63.0"
# Temel batarya = pre-commit check-unit-tests kapısının TA KENDİSİ (tek
# kaynak). Sözleşme testleri sahte batarya enjekte edebilsin diye ezilebilir.
BATTERY_SCRIPT="${LEIBNIZ2_BOOTSTRAP_BATTERY:-$ROOT/_calisma/CIKTI/check_unit_tests_hook.sh}"

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  say "Kullanım: dev_bootstrap.sh [--full|--check|--help]"
  say "  (bayraksız) araç-kümesini kur (idempotent, hızlı)"
  say "  --full      kur + temel bataryayı koş (uçtan uca, fail-closed)"
  say "  --check     araç-kümesi tam mı? rc=0/1 (fail-closed)"
  say "  --help      bu yardım"
  say "Not: tarayıcı katmanı (chromium) eksikse ilk kurulumda ~150 MB iner."
}

# check_ = işlev-ölçümü, varlık-değil: venv pin-paritesi, npm unit'leri
# kendi-sözleşmeleri (library çözümü / kapı-binary'leri) — node_modules
# yoksa probe doğal-fail eder, ayrıca varlık-kontrolü gerekmez.
# Yeni araç-kümesi = bir check_ + bir provision_ + UNITS'e bir giriş.
check_venv_z3() {
  [ -x "$VENV_PY" ] || return 1
  local frozen pin
  frozen="$($VENV_PY -m pip freeze 2>/dev/null)" || return 1
  for pin in "${PINS[@]}"; do
    printf '%s\n' "$frozen" | grep -qx "$pin" || return 1
  done
}
provision_venv_z3() {
  say "venv_z3: kuruluyor (pinned: ${PINS[*]})"
  python3 -m venv "$VENV" || die "venv olusturma"
  "$VENV_PY" -m pip install --quiet "${PINS[@]}" || die "venv_z3 pip install"
}
check_pptx() {
  (cd "$PPTX" && node -e "require.resolve('pptxgenjs')" >/dev/null 2>&1)
}
provision_pptx() {
  say "_calisma/pptx: npm ci"
  npm ci --prefix "$PPTX" || die "_calisma/pptx npm ci"
}
# docx jeneratoru (markdown → .docx): CI'da LibreOffice ile acilabilirlik
# kontrolu yapilir; yerelde de ayni jenerator kosabilsin diye burada kurulur.
check_docx() {
  (cd "$DOCX" && node -e "require.resolve('docx')" >/dev/null 2>&1)
}
provision_docx() {
  say "_calisma/docx: npm ci"
  npm ci --prefix "$DOCX" || die "_calisma/docx npm ci"
}
check_dashboard_next() {
  [ -x "$DASH/node_modules/.bin/tsc" ] \
    && [ -x "$DASH/node_modules/.bin/next" ]
}
provision_dashboard_next() {
  say "apps/dashboard-next: npm ci"
  npm ci --prefix "$DASH" || die "apps/dashboard-next npm ci"
}
check_trend_db() {
  [ -x "$TREND_DB/node_modules/.bin/tsx" ]
}
provision_trend_db() {
  say "apps/trend-db: npm ci"
  npm ci --prefix "$TREND_DB" || die "apps/trend-db npm ci"
}
check_video() {
  [ -x "$VIDEO/node_modules/.bin/tsc" ]
}
provision_video() {
  say "_calisma/video: npm ci"
  npm ci --prefix "$VIDEO" || die "_calisma/video npm ci"
}
# Tarayıcı katmanı iki adımlı bir bağımlılıktır (pip paketi + ayrı inen
# chromium), bu yüzden ölçüm pin-karşılaştırması DEĞİL işlevsel: gerçekten
# bir chromium başlatabiliyor muyuz? Çalışan bir tarayıcı, sürüm etiketinden
# daha güçlü kanıt; ayrıca yerelde farklı ama çalışan bir playwright sürümü
# kuruluysa gereksiz bir ~150 MB indirme tetiklenmez.
check_browsers() {
  "$VENV_PY" - >/dev/null 2>&1 <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch(headless=True).close()
PY
}
provision_browsers() {
  say "browsers: $BROWSER_PIN + chromium (~150 MB)"
  "$VENV_PY" -m pip install --quiet "$BROWSER_PIN" || die "playwright pip install"
  "$VENV_PY" -m playwright install chromium || die "playwright install chromium"
}
UNITS=(venv_z3 pptx docx dashboard_next trend_db video browsers)

# Temel batarya: tüm test dosyaları + manifest drift denetimi, venv python'la.
# Çıktı akışı KISILMAZ (kırmızı satırlar kullanıcıya görünür), sonuç `die` ile
# fail-closed tek koda indirilir.
run_battery() {
  if [ "${LEIBNIZ2_IN_BATTERY:-0}" = "1" ]; then
    die "temel batarya zaten koşuyor (LEIBNIZ2_IN_BATTERY=1) — özyineleme reddedildi"
  fi
  [ -f "$BATTERY_SCRIPT" ] || die "temel batarya betiği yok: $BATTERY_SCRIPT"
  say "temel batarya: $BATTERY_SCRIPT"
  ( cd "$ROOT" && LEIBNIZ2_IN_BATTERY=1 bash "$BATTERY_SCRIPT" ) \
    || die "temel batarya kırmızı — yukarıdaki FAILED satırlarına bak"
}

FULL=0
case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --check)
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    for u in "${UNITS[@]}"; do
      "check_$u" || { say "CHECK FAIL: $u eksik veya paritesiz (kurulum: bash '$ROOT/_calisma/dev_bootstrap.sh')"; exit 1; }
    done
    say "CHECK OK"
    exit 0
    ;;
  --full)
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    FULL=1
    ;;
  "") ;;
  *)
    usage >&2
    exit 2
    ;;
esac

for u in "${UNITS[@]}"; do
  if "check_$u"; then
    say "$u: up to date"
  else
    "provision_$u"
  fi
done

if [ "$FULL" -eq 1 ]; then
  run_battery
fi

say "BOOTSTRAP OK"
