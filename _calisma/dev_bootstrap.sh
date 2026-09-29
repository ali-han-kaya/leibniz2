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
#   trend_db_codegen    → prisma generate (üretilen istemci; gitignored)
#   dashboard_next_build → next build (BUILD_ID; gitignored)
#
# KAPSAM DIŞI (ölçüldü 2026-09-28, dürüst sınır): script ARAÇ-KÜMESİ + ÜRETİM
# ARTEFAKTI sağlar, RUNTIME VERİSİ sağlamaz. `_calisma/CIKTI/history.jsonl` ve
# `runs/` gitignored'tır ve yalnız gerçek koşumlarla oluşur; `test_surface_cwv_report`
# ve `test_dashboard_keyboard_nav` bunları ölçtüğü için taze checkout'ta
# yeşile dönmezler. --check bu yüzden "yeşil batarya" DEĞİLDİR: unit eksikliğini
# ölçer, koşum geçmişini değil.
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
# Sürümler TEK KAYNAKTAN okunur (aşağıdaki `_load_pins`); burada sabit
# dizi YOKTUR. Ölçülen gerekçe: sürüm 6 yerde kopyalanmıştı (bu script,
# test_dev_bootstrap.py, verify.yml'de 4 satır + 2 cache key) ve
# `verify.yml:2904` pre-commit/pyyaml/jsonschema'yı **pinsiz** kuruyordu —
# yani iki sürüm hattı sessizce birlikte yaşıyordu.
REQ_FILE="$ROOT/_calisma/requirements-z3.txt"
# Temel batarya = pre-commit check-unit-tests kapısının TA KENDİSİ (tek
# kaynak). Sözleşme testleri sahte batarya enjekte edebilsin diye ezilebilir.
BATTERY_SCRIPT="${LEIBNIZ2_BOOTSTRAP_BATTERY:-$ROOT/_calisma/CIKTI/check_unit_tests_hook.sh}"

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

# Pini tek kaynaktan yükle. Bölümler pip'e zarar vermeyen yorumlardır:
#   [venv]    → PINS          (check_venv_z3 birebir `pip freeze` eşitliği arar)
#   [browser] → BROWSER_PIN   (işlevsel denetim: chromium gerçekten açılıyor mu)
# Sürüm bump = requirements dosyasında tek satır; burada, CI'da ve testte
# kopya kalmaz (kapsam dışı kopyayı `test_dev_bootstrap.py` kırmızıya düşürür).
_load_pins() {
  [ -f "$REQ_FILE" ] || die "requirements dosyası yok: $REQ_FILE"
  PINS=()
  BROWSER_PIN=""
  local in_browser=0 line
  while IFS= read -r line; do
    case "$line" in
      "# [browser]"*) in_browser=1; continue ;;
    esac
    case "$line" in
      \#*|"") continue ;;
    esac
    if [ "$in_browser" = "1" ]; then
      [ -z "$BROWSER_PIN" ] || die "[browser] bölümünde tek pin olmalı: $REQ_FILE"
      BROWSER_PIN="$line"
    else
      PINS+=("$line")
    fi
  done < "$REQ_FILE"
  [ "${#PINS[@]}" -gt 0 ] || die "[venv] pini yok: $REQ_FILE"
  [ -n "$BROWSER_PIN" ] || die "[browser] pini yok: $REQ_FILE"
}
_load_pins
# Pini taşıyan yorumlayıcı tabanı (PyPI `requires_python`): playwright 1.61+
# >=3.10 istiyor. Altındaki bir yorumlayıcıda pip "No matching distribution"
# der — 5 npm kurulumundan SONRA ve sebebi YANLIŞ göstererek (pin yok değil,
# yorumlayıcı eski). Ölçüldü 2026-09-28: bu deponun varsayılan python3'ü
# 3.9.6 iken CI 3.12 kullanıyor, yani script CI'da değil yerelde ölüyordu.
# Sürüm DEĞİLDİR, bu yüzden requirements dosyasında değil burada durur:
# kaynak sürümün taşıyıcı şartıdır, paketin özelliği değil.
BROWSER_PIN_MIN_PY="3.10"

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
  say "venv_z3: kuruluyor (pins: $REQ_FILE [venv])"
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
  # Pin, VENV'in YORUMLAYICISIYLA kurulur (python3 yalnızca venv'i yaratır);
  # bu yüzden taban denetimi de aynı yorumlayıcıya bakar.
  local interp="$VENV_PY"
  [ -x "$interp" ] || interp="$(command -v python3 || true)"
  if ! python_floor_ok "$BROWSER_PIN_MIN_PY" "$interp"; then
    if [ -z "${LEIBNIZ2_BROWSER_PIN:-}" ]; then
      die "tarayıcı pini $BROWSER_PIN Python >=$BROWSER_PIN_MIN_PY istiyor; kurulum yorumlayıcısı $("$interp" --version 2>&1 || echo 'bilinmiyor'). ÖNEMLİ: taban PATH'teki python3'e değil VENV'in yorumlayıcısına bakılır ve venv bu çağrıda zaten kurulmuş olduğu için PATH'i değiştirmek tek başına YETMEZ — ölçüldü (2026-09-29 taze-worktree kanıtı): o komut aynı hatayı anında yeniden döndürdü. Çözüm: venv'i silip >=$BROWSER_PIN_MIN_PY bir python3 ile YENİDEN kur: rm -rf '$VENV' && PATH=<python3'ün bulunduğu dizin>:\$PATH bash $0  (örn. python3.11 — CI 3.12 çalıştırıyor). 3.9 için geçici çözüm: LEIBNIZ2_BROWSER_PIN=<sürüm> bash $0; uygun sürüm ve tam komut $REQ_FILE içindeki [browser] notunda yazılı (sürüm burada SABİTLENMEZ — tek kaynak). O seçenek CI ile ayrışır, o yüzden --check'in işlevsel tarayıcı probu SESSİZCE kabul eder."
    fi
    say "UYARI: '$BROWSER_PIN' bu yorumlayıcıda kurulamaz (Python <$BROWSER_PIN_MIN_PY) — açık geçersiz kılmayla deneniyor; CI ile ayrışır"
  fi
  say "browsers: ${LEIBNIZ2_BROWSER_PIN:-$BROWSER_PIN} + chromium (~150 MB)"
  "$VENV_PY" -m pip install --quiet "${LEIBNIZ2_BROWSER_PIN:-$BROWSER_PIN}" \
    || die "playwright pip install"
  "$VENV_PY" -m playwright install chromium || die "playwright install chromium"
}
# Yorumlayıcı tabanı denetimi (fail-closed): ölçülemiyorsa da kurulum DURUR —
# "bilmiyorum" sessizce geçmemeli, çünkü tam olarak o sessiz geçiş 3.9'da
# beş dakikalık kurulumun sonunda pip hatasına dönüşmüştü.
python_floor_ok() {   # <taban> <yorumlayıcı>
  local floor="$1" interp="$2" have
  [ -n "$interp" ] && [ -x "$interp" ] \
    || die "python tabanı denetlenemedi: yorumlayıcı yok ($interp)"
  have="$("$interp" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" \
    || die "python sürümü okunamadı: $interp"
  case "$have" in
    [0-9]*.[0-9]*) ;;
    *) die "python sürümü çözümlenemedi: '$have'" ;;
  esac
  "$interp" -c 'import sys; raise SystemExit(0 if tuple(map(int, sys.argv[2].split("."))) >= tuple(map(int, sys.argv[1].split("."))) else 1)' \
    "$floor" "$have" >/dev/null 2>&1
}
check_trend_db_codegen() {
  # Varlık-değil ilkesi burada BİLİNÇLİ esniyor: üretilen Prisma istemcisi
  # sözleşmenin kendisidir (dashboard-next `lib/trend-db.ts` onu içe aktarır).
  # Ölçülen boşluk 2026-09-28: `apps/trend-db/generated/` gitignored, CI
  # `prisma generate` çalıştırıyor, bu script ÇALIŞTIRMIYORDU → taze
  # checkout'ta tip kapısı ve 3 trend-db testi kırmızıydı.
  [ -s "$TREND_DB/generated/client.ts" ]
}
provision_trend_db_codegen() {
  say "apps/trend-db: prisma generate (kod üretimi — DB'ye bağlanmaz)"
  # CI'ın dashboard-next job'ının birebir komutu (verify.yml). `prisma.config.ts`
  # URL'i env("DATABASE_URL") ile çözer; değişken yoksa generate BAĞLANMAZ.
  # Yer tutucu DSN gerçek kimlik bilgisi taşımaz ve hiç kullanılmaz.
  ( cd "$TREND_DB" \
    && DATABASE_URL="${LEIBNIZ2_PRISMA_URL:-postgresql://ci:ci@127.0.0.1:5432/ci?sslmode=disable}" \
       npx prisma generate ) || die "prisma generate"
}
check_dashboard_next_build() {
  # Aynı esneme: BUILD_ID bir içerik imzasıdır; boş/eksik derleme onu
  # üretmez. Tarayıcı ve CWV testleri ÖNCEDEN derlenmiş bundle'ı sunan
  # `next start` bekler (ölçülen boşluk: taze worktree'de 2 test kırmızıydı).
  [ -s "$DASH/.next/BUILD_ID" ]
}
provision_dashboard_next_build() {
  say "apps/dashboard-next: next build (üretim derlemesi)"
  npm run build --prefix "$DASH" || die "next build"
}
# Sıra önemli: codegen `trend_db` node_modules'ına, build ise `dashboard_next`
# node_modules'ına VE üretilen istemciye ihtiyaç duyar.
#
# `unit_path`: etiket TEK başına "pptx" derken, kullanıcı `ls` ile bakacağı
# yeri bilmez. Ölçülen boşluk: `--check` kırmızısı ve "up to date" satırları
# yalnız unit ADIYDI (pptx, dashboard_next), gerçek yer `_calisma/pptx`,
# `apps/dashboard-next`. Yani "hangi dizini açmam lazım" sorusu ekran
# dışında kalıyordu. Etiket artık "unit-adı (gerçek/yol)" biçiminde.
# Sipariş KORUNUR: `check_bootstrap_toolchain.py`'in UNIT_RE'si
# `^CHECK FAIL:\s*(\S+)` ile İLK token'ı (unit adını) yakalar — yol
# parantez içinde gelir, bu yüzden imza bozulmaz. `test_units_are_not_
# duplicated_in_the_gate` da `CHECK FAIL:\s*<unit>\b` aradığı için aynı
# düzen korunur.
unit_path() {  # <unit-adı> → "<unit-adı> (<görünen yol>)"
  case "$1" in
    venv_z3)            printf '%s (%s)\n' "$1" "${VENV#$ROOT/}" ;;
    pptx)               printf '%s (%s)\n' "$1" "${PPTX#$ROOT/}" ;;
    docx)               printf '%s (%s)\n' "$1" "${DOCX#$ROOT/}" ;;
    dashboard_next)     printf '%s (%s)\n' "$1" "${DASH#$ROOT/}" ;;
    trend_db)           printf '%s (%s)\n' "$1" "${TREND_DB#$ROOT/}" ;;
    video)              printf '%s (%s)\n' "$1" "${VIDEO#$ROOT/}" ;;
    browsers)           printf '%s (%s)\n' "$1" "venv_z3 + chromium" ;;
    trend_db_codegen)   printf '%s (%s)\n' "$1" "${TREND_DB#$ROOT/}/generated" ;;
    dashboard_next_build) printf '%s (%s)\n' "$1" "${DASH#$ROOT/}/.next" ;;
    *)                  printf '%s\n' "$1" ;;
  esac
}

UNITS=(venv_z3 pptx docx dashboard_next trend_db video browsers
       trend_db_codegen dashboard_next_build)

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
    # rc=2 kuralı TÜM bayraklarda aynı: `--help extra` de "fazladan argüman
    # kuruluma girmedi" demek değil, kullanıcı yazım hatası yapmıştır ve
    # sessizce yutulursa hangi bayrağı gerçekten kastettiği bellidir.
    # Ölçüldü (2026-09-29): `--check extra` ve `--full extra` rc=2 verirken
    # `--help extra` rc=0 dönüyordu — üçü de tek bayrak bekleyen bir
    # komut, üçü de aynı yanlışı aynı şekilde cezalandırmalı.
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    usage
    exit 0
    ;;
  --check)
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    for u in "${UNITS[@]}"; do
      "check_$u" || { say "CHECK FAIL: $(unit_path "$u") eksik veya paritesiz (kurulum: bash '$ROOT/_calisma/dev_bootstrap.sh')"; exit 1; }
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
    say "$(unit_path "$u"): up to date"
  else
    "provision_$u"
  fi
done

if [ "$FULL" -eq 1 ]; then
  run_battery
fi

say "BOOTSTRAP OK"
