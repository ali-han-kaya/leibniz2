#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: envanterdeki araç-kümeleri + --full ile temel batarya.
# Idempotent: kurulu araca dokunmaz.
#
# Kapsam neden GENİŞ: her unit, bataryadaki testlerin ortam-yok diye SKIP
# etmemesi için var. Kurulu olmayan bir bağımlılık testi KIRMIZIYA düşürmez
# (repo kültürü: "skip" + gerekçede kurulum reçetesi), ama taze checkout'ta
# yeşil görünen batarya sessizce kapsam kaybeder. HANGİ unit'in HANGİ testi
# kurtardığı envanterin yorumunda yazılı; burada ve testlerde kopyalanmaz.
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
# Betiğin KENDİ mutlak yolu: önerilen kurtarma komutunda kullanılır.
# `$0` çağrıldığı yere göre göreli olabiliyor (`bash _calisma/dev_bootstrap.sh`
# → `_calisma/dev_bootstrap.sh`), o zaman kopyala-yapıştır komutu başka bir
# dizinden ÇALIŞMAZDI. Ölçüldü (2026-09-29): ipucu tam yol yazarken betik
# yolunu göreli basıyordu.
SELF="$ROOT/_calisma/dev_bootstrap.sh"

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

# ── Unit envanteri: TEK KAYNAK ───────────────────────────────────────────────
# Liste, sıra, görünen yol, check türü ve provision türü
# `_calisma/bootstrap_units.conf` içinde. Burada hiçbir unit ADI sabit
# yazılmaz; `test_dev_bootstrap.py` de AYNI dosyayı okur, böylece ikisi
# birbirinden kayamaz. Ölçülen sebep: liste `UNITS=(...)` dizisi,
# `unit_path()` case tablosu ve iki test sınıfında elle yazılmıştı.
UNITS_CONF="$ROOT/_calisma/bootstrap_units.conf"
[ -f "$UNITS_CONF" ] || die "unit envanteri yok: $UNITS_CONF"
UNITS=(); U_LABEL=(); U_CHECK=(); U_PROV=()
while read -r _u _label _check _prov _rest; do
  case "$_u" in ''|\#*) continue ;; esac
  [ -n "$_label" ] && [ -n "$_check" ] && [ -n "$_prov" ] \
    || die "eksik satır (ad yol check provision): $_u"
  # Beşinci alan boş OLMAK ZORUNDA: alanlar boşlukla ayrıldığı için bir
  # etiketteki boşluk ("venv_z3 + chromium") alan sayısını sessizce
  # bozuyordu — eksik alan denetimi onu yakalamıyordu. Ölçüldü.
  [ -z "$_rest" ] || die "fazladan alan var ($#$_u satırı): $_u"
  UNITS+=("$_u"); U_LABEL+=("$_label"); U_CHECK+=("$_check"); U_PROV+=("$_prov")
done < "$UNITS_CONF"
[ "${#UNITS[@]}" -gt 0 ] || die "unit envanteri boş: $UNITS_CONF"

# Paralel dizilerde alan arama (bash 3.2'de assoc dizi yok → doğrusal tarama;
# 9 birim maliyetsiz). Bilinmeyen ad = envanterle çelişki = fail-closed.
_unit_field() {  # <label|check|prov> <ad>
  _f="$1"; _n="$2"; _i=0
  while [ "$_i" -lt "${#UNITS[@]}" ]; do
    if [ "${UNITS[$_i]}" = "$_n" ]; then
      case "$_f" in
        label) printf '%s\n' "${U_LABEL[$_i]}" ;;
        check) printf '%s\n' "${U_CHECK[$_i]}" ;;
        prov)  printf '%s\n' "${U_PROV[$_i]}" ;;
        *) die "bilinmeyen alan: $_f" ;;
      esac
      return 0
    fi
    _i=$((_i + 1))
  done
  die "envanterde olmayan unit: $_n"
}

# Etiket: "<ad> (<görünen yol>)". Sipariş KORUNUR —
# `check_bootstrap_toolchain.py`'in UNIT_RE'si `^CHECK FAIL:\s*(\S+)` ile İLK
# token'ı, yani unit ADINI, yakalar. Yol parantez içinde geldiği için imza
# bozulmaz (ölçüldü: ayrıştırılan 'pptx').
unit_path() { printf '%s (%s)\n' "$1" "$(_unit_field label "$1")"; }

# Yol değişkenleri envanterden TÜRETİLİR; hiçbiri burada sabit yazılmaz.
VENV="$ROOT/$(_unit_field label venv_z3)"
VENV_PY="$VENV/bin/python"
PPTX="$ROOT/$(_unit_field label pptx)"
DOCX="$ROOT/$(_unit_field label docx)"
DASH="$ROOT/$(_unit_field label dashboard_next)"
TREND_DB="$ROOT/$(_unit_field label trend_db)"
VIDEO="$ROOT/$(_unit_field label video)"
# İki üretim birimi kendi üst DİZİNİNDE çalışır: `apps/trend-db/generated`
# → `apps/trend-db`, `apps/dashboard-next/.next` → `apps/dashboard-next`.
PRISMA_DIR="$ROOT/$(dirname "$(_unit_field label trend_db_codegen)")"
NEXT_DIR="$ROOT/$(dirname "$(_unit_field label dashboard_next_build)")"
# Sürümler TEK KAYNAKTAN okunur (aşağıdaki `_load_pins`); burada sabit
# dizi YOKTUR. Ölçülen gerekçe: sürüm 6 yerde kopyalanmıştı (bu script,
# test_dev_bootstrap.py, verify.yml'de 4 satır + 2 cache key) ve
# `verify.yml:2904` pre-commit/pyyaml/jsonschema'yı **pinsiz** kuruyordu —
# yani iki sürüm hattı sessizce birlikte yaşıyordu.
REQ_FILE="$ROOT/_calisma/requirements-z3.txt"
# Temel batarya = pre-commit check-unit-tests kapısının TA KENDİSİ (tek
# kaynak). Sözleşme testleri sahte batarya enjekte edebilsin diye ezilebilir.
BATTERY_SCRIPT="${LEIBNIZ2_BOOTSTRAP_BATTERY:-$ROOT/_calisma/CIKTI/check_unit_tests_hook.sh}"

# Pini tek kaynaktan yükle. Bölümler pip'e zarar vermeyen yorumlardır:
#   [venv]    → PINS          (`venv` türlü check birebir `pip freeze` eşitliği arar)
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
#
# Birim başına `check_<ad>` fonksiyonu YOK: tür envanterdeki 3. alanda
# durur ve `check_unit` ona bakar. Yeni araç-kümesi = envantere bir satır.
check_unit() {  # <ad>
  _spec="$(_unit_field check "$1")"
  case "$_spec" in
    venv)
      [ -x "$VENV_PY" ] || return 1
      _frozen="$($VENV_PY -m pip freeze 2>/dev/null)" || return 1
      for _pin in "${PINS[@]}"; do
        printf '%s\n' "$_frozen" | grep -qx "$_pin" || return 1
      done
      ;;
    # Tarayıcı katmanı iki adımlı bir bağımlılıktır (pip paketi + ayrı inen
    # chromium), bu yüzden ölçüm pin-karşılaştırması DEĞİL işlevsel:
    # gerçekten bir chromium başlatabiliyor muyuz? Çalışan bir tarayıcı,
    # sürüm etiketinden daha güçlü kanıt; ayrıca yerelde farklı ama
    # çalışan bir playwright sürümü kuruluysa gereksiz bir ~150 MB
    # indirme tetiklenmez.
    browser)
      "$VENV_PY" - >/dev/null 2>&1 <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch(headless=True).close()
PY
      ;;
    resolve:*)
      ( cd "$ROOT/$(_unit_field label "$1")" \
        && node -e "require.resolve('${_spec#resolve:}')" >/dev/null 2>&1 )
      ;;
    # Virgülle ayrılmış her yol çalıştırılabilir olmalı (dashboard_next
    # hem `tsc` hem `next` ister — ikisinden biri eksikse eksik sayılır).
    exec:*)
      _rest="${_spec#exec:}"; _ok=0
      while [ -n "$_rest" ]; do
        _p="${_rest%%,*}"; case "$_rest" in *,*) _rest="${_rest#*,}" ;; *) _rest="" ;; esac
        [ -x "$ROOT/$_p" ] || { _ok=1; break; }
      done
      return "$_ok"
      ;;
    # Varlık-olmayan ilke burada BİLEREK esniyor (prisma istemcisi ve
    # BUILD_ID): üretilen çıktı birer içerik imzasıdır, boş/eksik derleme
    # onu üretmez. Ölçülen boşluk 2026-09-28: `apps/trend-db/generated/`
    # ve `.next/` gitignore, CI'da üretiliyordu ama script ÇALIŞTIRMIYORDU →
    # taze checkout'ta bootstrap VE --check yeşilken 5 test kırmızıydı.
    artifact:*)
      [ -s "$ROOT/${_spec#artifact:}" ]
      ;;
    *) die "bilinmeyen check türü ($_spec): $1" ;;
  esac
}

provision_unit() {  # <ad>
  case "$(_unit_field prov "$1")" in
    venv)
      # Venv'i kuran yorumlayıcı, bu venv'e kurulan EN YÜKSEK tabanı da
      # sağlamalıdır. Buradaki tek ek taban `BROWSER_PIN_MIN_PY`'dir
      # (playwright `requires_python >=3.10`): aynı venv'e kuruluyor.
      #
      # Ölçülen kırılma (2026-09-29): venv daima `python3` ile kuruluyordu.
      # PATH'te `python3` 3.9.6 iken tabanı geçen bir yorumlayıcı (`python3.11`)
      # bulunduğunda bile venv 3.9 ile kuruluyor, `browsers` adımı ölüyor ve
      # kullanıcıya kurtarma turu yükleniyordu — üstelik önerilen komut da
      # ÇALIŞMIYORDU, çünkü `python3.11` dizinini PATH'e eklemek `python3`'ü
      # değiştirmiyor. Yani venv'i doğru yorumlayıcıyla kurmak, ölüp
      # reçeteyi çalıştırmaktan daha az iş.
      _vp="python3"
      if _sat="$(_satisfying_interpreter "$BROWSER_PIN_MIN_PY")"; then
        _vp="$_sat"
      fi
      say "$1: kuruluyor (python3=$(_vp_basename "$_vp"), pins: $REQ_FILE [venv])"
      "$_vp" -m venv "$VENV" || die "venv olusturma"
      "$VENV_PY" -m pip install --quiet "${PINS[@]}" || die "venv_z3 pip install"
      ;;
    npm)
      _d="$ROOT/$(_unit_field label "$1")"
      say "${_d#$ROOT/}: npm ci"
      npm ci --prefix "$_d" || die "${_d#$ROOT/} npm ci"
      ;;
    # docx jeneratörü de buradan kurulur: CI'da LibreOffice ile
    # açılabilirlik kontrolü yapılır, yerelde de aynı jeneratör koşabilsin.
    browser)
      # Pin, VENV'in YORUMLAYICISIYLA kurulur (python3 yalnızca venv'i
      # yaratır); bu yüzden taban denetimi de aynı yorumlayıcıya bakar.
      interp="$VENV_PY"
      [ -x "$interp" ] || interp="$(command -v python3 || true)"
      if ! python_floor_ok "$BROWSER_PIN_MIN_PY" "$interp"; then
        if [ -z "${LEIBNIZ2_BROWSER_PIN:-}" ]; then
          remedy_hint "$BROWSER_PIN_MIN_PY"
          die "tarayıcı pini $BROWSER_PIN Python >=$BROWSER_PIN_MIN_PY istiyor; kurulum yorumlayıcısı $("$interp" --version 2>&1 || echo 'bilinmiyor'). Yukarıdaki ÇÖZÜM ADIMI'nı uygula."
        fi
        say "UYARI: '$BROWSER_PIN' bu yorumlayıcıda kurulamaz (Python <$BROWSER_PIN_MIN_PY) — açık geçersiz kılmayla deneniyor; CI ile ayrışır"
      fi
      say "$1: ${LEIBNIZ2_BROWSER_PIN:-$BROWSER_PIN} + chromium (~150 MB)"
      "$VENV_PY" -m pip install --quiet "${LEIBNIZ2_BROWSER_PIN:-$BROWSER_PIN}" \
        || die "playwright pip install"
      "$VENV_PY" -m playwright install chromium || die "playwright install chromium"
      ;;
    # CI'ın dashboard-next job'ının birebir komutu (verify.yml).
    # `prisma.config.ts` URL'i env("DATABASE_URL") ile çözer; değişken yoksa
    # generate BAĞLANMAZ. Yer tutucu DSN gerçek kimlik bilgisi taşımaz ve
    # hiç kullanılmaz.
    prisma)
      say "$(_unit_field label trend_db_codegen | sed 's#/generated##'): prisma generate (kod üretimi — DB'ye bağlanmaz)"
      ( cd "$PRISMA_DIR" \
        && DATABASE_URL="${LEIBNIZ2_PRISMA_URL:-postgresql://ci:ci@127.0.0.1:5432/ci?sslmode=disable}" \
           npx prisma generate ) || die "prisma generate"
      ;;
    nextbuild)
      say "$(_unit_field label dashboard_next_build | sed 's#/.next##'): next build (üretim derlemesi)"
      npm run build --prefix "$NEXT_DIR" || die "next build"
      ;;
    *) die "bilinmeyen provision türü: $1" ;;
  esac
}
# Sürüm karşılaştırmasının TEK yolu: `python_floor_ok` (sebebiyle ölür) ve
# `_floor_probe` (sessizce sırf rc döner) aynı karşılaştırmayı paylaşır —
# iki yerde ayrı ayrı yazılırsa biri güncellenip diğeri eski kalır.
_py_at_least() {   # <taban> <bulunan-sürüm> <yorumlayıcı>
  "$3" -c 'import sys; raise SystemExit(0 if tuple(map(int, sys.argv[2].split("."))) >= tuple(map(int, sys.argv[1].split("."))) else 1)' \
    "$1" "$2" >/dev/null 2>&1
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
  _py_at_least "$floor" "$have" "$interp"
}
# ÖLÜMSÜZ ikizi: yalnız "tabanı geçiyor mu" sorusunu yanıtlar, sebep
# söylemez. Aday listeyi tararken kullanılır — orada "ölçülemeyen aday
# atlanır" demek doğru davranış, `python_floor_ok`'in fail-closed
# davranışı değil.
_floor_probe() {   # <taban> <yorumlayıcı>
  local floor="$1" interp="$2" have
  [ -n "$interp" ] && [ -x "$interp" ] || return 1
  have="$("$interp" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" \
    || return 1
  case "$have" in
    [0-9]*.[0-9]*) ;;
    *) return 1 ;;
  esac
  _py_at_least "$floor" "$have" "$interp"
}
# Yorumlayıcı yolundan yalnız ADı (log satırı okunur kalsın diye).
_vp_basename() { printf '%s\n' "${1##*/}"; }
# Tabanı geçen yorumlayıcıyı SİSTEMDE ARA ve tam yolunu yaz.
# Neden `python3` değil de isimli adaylar: ölçülen tuzak (2026-09-29) —
# kullanıcının PATH'inde `python3.11` vardı ama `python3` değildi, "PATH'e
# dizin ekle" reçetesi bu yüzden hiçbir şeyi değiştirmiyordu. Adı ne
# olursa olsun, tabanı gerçekten geçeni bulup O'nun dizinini vermek
# reçeteyi çalıştırılabilir kılıyor.
_satisfying_interpreter() {   # <taban>
  local floor="$1" c resolved
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    resolved="$(command -v "$c" 2>/dev/null)" || continue
    if _floor_probe "$floor" "$resolved"; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}
# Ölüm nedeni kadar KURTARMA YOLU da yazılır — ve yazılan yol ÖLÇÜLMÜŞTÜR,
# tahmin değil. Bulunan yorumlayıcının tam yolu + sürümü + kopyalanabilir
# tek satırlık komut verilir; hiçbiri bulunamazsa bu AÇIKÇA söylenir ve
# uydurma bir komut basılmaz ("ölçülemeyen yeşil sayılmaz" ilkesi).
remedy_hint() {   # <taban>
  local floor="$1" found dir ver
  hint() { printf '%s\n' "$*" >&2; }
  hint ""
  hint "ÇÖZÜM ADIMI:"
  hint "  1) '<$VENV>' bu yorumlayıcıyla zaten kuruldu; venv'i SİL —"
  hint "     silmezsen aynı hata anında geri döner (ölçüldü: 0 s)."
  hint "  2) Tabanı geçen yorumlayıcı:"
  if found="$(_satisfying_interpreter "$floor")"; then
    ver="$("$found" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo '?')"
    dir="$(dirname "$found")"
    hint "     bulundu: $found (Python $ver)"
    hint "  3) Bu komutu çalıştır:"
    hint "       rm -rf '$VENV' && PATH=$dir:\$PATH bash '$SELF'"
  else
    hint "     PATH'te Python >=$floor olan yorumlayıcı YÖK."
    hint "     (python3.11/3.12 gibi ADIYLA kurulu olanlar da aranır;"
    hint "      hiçbiri geçmiyorsa bu satır boş yazılmaz.)"
    hint "  3) Önce >=$floor bir Python kur, sonra 1-2. adımı tekrarla."
  fi
  # 3.9 kaçışı HER iki dalda da yazılır: uygun yorumlayıcı bulunmuş olsa
  # bile geçici geçersiz kılma geçerli bir seçenektir ve kullanıcıya
  # sunulmazsa bu, mesajı eskisinden daha eksik kılar.
  hint ""
  hint "  Alternatif (3.9'da geçici, CI ile ayrışır):"
  hint "       LEIBNIZ2_BROWSER_PIN=<uygun sürüm> bash '$SELF'"
  hint ""
  hint "  Not: ölçüm taban PATH'teki python3'e değil VENV'in yorumlayıcısına"
  hint "  bakar ve venv bu çağrıda kurulmuş olduğu için PATH'i değiştirmek"
  hint "  tek başına YETMEZ. Uygun sürüm $REQ_FILE içindeki [browser]"
  hint "  notunda yazılıdır; sürüm burada SABİTLENMEZ (tek kaynak)."
}
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
      check_unit "$u" || { say "CHECK FAIL: $(unit_path "$u") eksik veya paritesiz (kurulum: bash '$ROOT/_calisma/dev_bootstrap.sh')"; exit 1; }
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
  if check_unit "$u"; then
    say "$(unit_path "$u"): up to date"
  else
    provision_unit "$u"
  fi
done

if [ "$FULL" -eq 1 ]; then
  run_battery
fi

say "BOOTSTRAP OK"
