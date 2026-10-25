#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: UNITS'teki araç-kümeleri — venv_z3 (pinned) + _calisma/pptx +
# apps/dashboard-next node_modules. Idempotent: kurulu araca dokunmaz.
# Kullanım: dev_bootstrap.sh [--check|--validate|--help]
set -eu

# ROOT çözümü PATH'e bağlı OLMAMALI: `dirname` minimal bir PATH'te (ör. /bin)
# yoktur ve ROOT boş kalır → tüm script yanlış yolu arar. Saf shell
# parameter-expansion + `cd`/`pwd` builtin'leri: dış komut gerekmez.
case "$0" in
  */*) _SCRIPT_DIR="${0%/*}" ;;
  *)   _SCRIPT_DIR="." ;;
esac
ROOT="$(cd "$_SCRIPT_DIR/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
PPTX="$ROOT/_calisma/pptx"
DASH="$ROOT/apps/dashboard-next"
VIDEO="$ROOT/_calisma/video"
SHADCN="$ROOT/apps/dashboard-shadcn"
TRENDDB="$ROOT/apps/trend-db"
PINS=(z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0)
CONF="$ROOT/_calisma/bootstrap_units.conf"

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  say "Kullanım: dev_bootstrap.sh [--check|--validate|--help]"
  say "  (bayraksız) eksiği kur; önce conf ölçümlerinden maliyet tablosu basar"
  say "  --check     araç-kümesi tam mı? rc=0/1 (fail-closed)"
  say "  --check --plan kurulum öncesi tahmin tablosu (kurulum yapmaz)"
  say "  --validate  bootstrap_units.conf bütünlük doğrulaması (fail-closed)"
  say "  --validate --json  aynı, JSON sidecar çıktısı"
  say "  --help      bu yardım"
  say "  NOT: tarayıcı tabanı altındaki venv otomatik yeniden kurulur;"
  say "       kapatmak için: DEV_BOOTSTRAP_NO_REBUILD=1"
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
venv_creator() { # venv'i kuracak yorumlayıcı: override yoksa PATH'teki python3
  if [ -n "${DEV_BOOTSTRAP_PYTHON3:-}" ]; then
    printf '%s' "$DEV_BOOTSTRAP_PYTHON3"
  else
    command -v python3 2>/dev/null || true
  fi
}
python3_bin() { # --validate için: TABAN ŞARTI YOK; override → PATH → bilinen konum
  local cand resolved hbin
  hbin="${HOME:-/nonexistent}"
  if [ -n "${DEV_BOOTSTRAP_PYTHON3:-}" ] && [ -x "${DEV_BOOTSTRAP_PYTHON3:-}" ]; then
    printf '%s' "$DEV_BOOTSTRAP_PYTHON3"
    return 0
  fi
  resolved=$(command -v python3 2>/dev/null || true)
  if [ -n "$resolved" ]; then
    printf '%s' "$resolved"
    return 0
  fi
  # Kullanıcı-yerel kurulum sisteminkinden önce gelir (nvm/pyenv benzeri
  # kurulumlar HOME altındadır); sıra sabit ve test edilebilir.
  for cand in "$hbin/.local/bin" /opt/homebrew/bin /usr/local/bin /usr/bin; do
    if [ -x "$cand/python3" ]; then
      printf '%s' "$cand/python3"
      return 0
    fi
  done
  return 1
}
provision_venv_z3() {
  say "venv_z3: kuruluyor (pinned: ${PINS[*]})"
  _creator="$(venv_creator)"
  [ -n "$_creator" ] || die "venv olusturma (python3 bulunamadı)"
  "$_creator" -m venv "$VENV" || die "venv olusturma"
  "$VENV_PY" -m pip install --quiet "${PINS[@]}" || die "venv_z3 pip install"
}
# ── Node araçları (npm/node) ────────────────────────────────────────────
# Tarayıcı tabanıyla AYNI desen: araç PATH'te olmayabilir (nvm/homebrew
# profili yüklenmemiş kabuk, cron/launchd, minimal CI PATH). Sıra: override →
# PATH → bilinen konumlar; hiçbiri yoksa fail-closed ve EYLEME DÖNÜK die.
# Override: DEV_BOOTSTRAP_NPM / DEV_BOOTSTRAP_NODE (tam yol),
#           DEV_BOOTSTRAP_NODE_DIRS (boşlukla ayrılmış aday dizinler).
NPM_BIN=""
NODE_BIN=""

node_candidate_dirs() { # aday dizinler: tek satır, boşlukla ayrılmış
  local hbin
  hbin="${HOME:-/nonexistent}"
  if [ -n "${DEV_BOOTSTRAP_NODE_DIRS:-}" ]; then
    printf '%s' "$DEV_BOOTSTRAP_NODE_DIRS"
  else
    printf '%s' "/opt/homebrew/bin /usr/local/bin $hbin/.local/bin $hbin/.volta/bin $hbin/.nvm/versions/node/*/bin"
  fi
}
node_tools() { # npm+node tam yollarını çöz → NPM_BIN/NODE_BIN; rc=1: eksik
  local dirs dir resolved same_dir
  if [ -z "$NPM_BIN" ] && [ -n "${DEV_BOOTSTRAP_NPM:-}" ] \
     && [ -x "${DEV_BOOTSTRAP_NPM:-}" ]; then
    NPM_BIN="$DEV_BOOTSTRAP_NPM"
  fi
  if [ -z "$NPM_BIN" ]; then
    resolved=$(command -v npm 2>/dev/null || true)
    if [ -n "$resolved" ]; then
      NPM_BIN="$resolved"
    fi
  fi
  if [ -z "$NPM_BIN" ]; then
    dirs=$(node_candidate_dirs)
    # shellcheck disable=SC2086 # aday listesi bilinçli split+glob (nvm glob'u)
    for dir in $dirs; do
      if [ -x "$dir/npm" ]; then
        NPM_BIN="$dir/npm"
        break
      fi
    done
  fi
  [ -n "$NPM_BIN" ] || return 1
  if [ -z "$NODE_BIN" ]; then
    # `dirname` dış komutuna güvenme (minimal PATH): parameter expansion.
    same_dir="${NPM_BIN%/*}"
    if [ "$same_dir" = "$NPM_BIN" ]; then
      same_dir=""   # NPM_BIN'de / yok → kardeş node araması anlamsız
    fi
    if [ -n "${DEV_BOOTSTRAP_NODE:-}" ] && [ -x "${DEV_BOOTSTRAP_NODE:-}" ]; then
      NODE_BIN="$DEV_BOOTSTRAP_NODE"
    elif [ -x "$same_dir/node" ]; then
      NODE_BIN="$same_dir/node"   # npm ile AYNI kurulum → sürüm uyumlu
    else
      resolved=$(command -v node 2>/dev/null || true)
      if [ -n "$resolved" ]; then
        NODE_BIN="$resolved"
      fi
    fi
  fi
  if [ -z "$NODE_BIN" ]; then
    dirs=$(node_candidate_dirs)
    for dir in $dirs; do
      if [ -x "$dir/node" ]; then
        NODE_BIN="$dir/node"
        break
      fi
    done
  fi
  # npm bir node betiğidir (#!/usr/bin/env node): kendi dizinini PATH'e ekle,
  # yoksa `env node` bulamaz — nvm/homebrew profili yüklenmemişken tipik hata.
  same_dir="${NPM_BIN%/*}"
  if [ "$same_dir" != "$NPM_BIN" ]; then
    case ":$PATH:" in
      *":$same_dir:"*) ;;
      *) PATH="$same_dir:$PATH"; export PATH ;;
    esac
  fi
  [ -n "$NODE_BIN" ]
}
node_missing_die() { # $1 = bağlam (unit ya da dizin)
  local dirs
  dirs=$(node_candidate_dirs)
  die "npm/node bulunamadı ($1): PATH'te ve şu aday dizinlerde yok → $dirs. Node kur ya da DEV_BOOTSTRAP_NPM=/tam/yol/npm (gerekirse DEV_BOOTSTRAP_NODE=/tam/yol/node) ver."
}
# Lock kapıları (her npm unit için ortak): (1) `npm ci --dry-run` lock eksik/
# bozuk/senkronsuz ise non-zero döner (node_modules'a dokunmaz); (2) npm dry-run,
# lock'un kök dep girişi silinmiş hâli için rc=0 döner, bu yüzden package.json
# dep adları (dependencies + devDependencies) lock kökü ile eşleştirilir.
lock_ok() {
  local dir="$1"
  node_tools || return 1
  (cd "$dir" && "$NPM_BIN" ci --dry-run --no-audit --no-fund >/dev/null 2>&1) || return 1
  (cd "$dir" && "$NODE_BIN" -e '
    const p = require("./package.json"), l = require("./package-lock.json");
    const root = (l.packages || {})[""] || {};
    const need = Object.keys(p.dependencies || {}).concat(Object.keys(p.devDependencies || {}));
    for (const d of need)
      if (!(root.dependencies || {})[d] && !(root.devDependencies || {})[d]) process.exit(1);
  ' >/dev/null 2>&1)
}
check_pptx() {
  lock_ok "$PPTX" || return 1
  (cd "$PPTX" && "$NODE_BIN" -e "require.resolve('pptxgenjs')" >/dev/null 2>&1)
}
provision_pptx() {
  say "_calisma/pptx: npm ci"
  node_tools || node_missing_die "_calisma/pptx"
  "$NPM_BIN" ci --prefix "$PPTX" || die "_calisma/pptx npm ci"
}
check_dashboard_next() {
  lock_ok "$DASH" && [ -x "$DASH/node_modules/.bin/tsc" ] \
    && [ -x "$DASH/node_modules/.bin/next" ]
}
provision_dashboard_next() {
  say "apps/dashboard-next: npm ci"
  node_tools || node_missing_die "apps/dashboard-next"
  "$NPM_BIN" ci --prefix "$DASH" || die "apps/dashboard-next npm ci"
}
# Aşağıdaki üç unit UNITS'e EKLENMEZ: --check'i bu checkout'ta kurulmamış
# unit'ler için kırmızıya çevirmemek adına. Bağımsız çağrılabilir kalırlar.
check_video() {
  lock_ok "$VIDEO" && [ -x "$VIDEO/node_modules/.bin/remotion" ] \
    && [ -x "$VIDEO/node_modules/.bin/tsc" ]
}
provision_video() {
  say "_calisma/video: npm ci"
  node_tools || node_missing_die "_calisma/video"
  "$NPM_BIN" ci --prefix "$VIDEO" || die "_calisma/video npm ci"
}
check_dashboard_shadcn() {
  lock_ok "$SHADCN" && [ -x "$SHADCN/node_modules/.bin/vite" ]
}
provision_dashboard_shadcn() {
  say "apps/dashboard-shadcn: npm ci"
  node_tools || node_missing_die "apps/dashboard-shadcn"
  "$NPM_BIN" ci --prefix "$SHADCN" || die "apps/dashboard-shadcn npm ci"
}
check_trend_db() {
  lock_ok "$TRENDDB" && [ -x "$TRENDDB/node_modules/.bin/prisma" ] \
    && [ -x "$TRENDDB/node_modules/.bin/tsx" ]
}
provision_trend_db() {
  say "apps/trend-db: npm ci"
  node_tools || node_missing_die "apps/trend-db"
  "$NPM_BIN" ci --prefix "$TRENDDB" || die "apps/trend-db npm ci"
}
# ── Tarayıcı tabanı ─────────────────────────────────────────────────────
# Pin'li playwright'ın istediği en-düşük Python (BROWSER floor).
#   Pin'in TEK KAYNAĞI: .github/workflows/verify.yml (a11y-gate adımı:
#     `pip install playwright==X.Y.Z`).
#   Taban kuralının TEK KAYNAĞI: _calisma/CIKTI/check_requirements_drift.py
#     (playwright>=1.61 → Python>=3.10; Python 3.9'da en-fazla 1.60.x).
# Venv yorumlayıcısı creation anında sabitlenir; taban-altı bir venv PATH
# oyunuyla DÜZELTİLEMEZ (venv yeniden kurulmalı) → fail-closed die.
# Die mesajı yer-tutucu tarif DEĞİL, sistemde SAPTANAN yorumlayıcıyı
# (tam yol + tam sürüm) ve çalışan TAM KOMUTU verir.
BROWSER_MIN_PY_MAJOR=3
BROWSER_MIN_PY_MINOR=10

py_mm() { # py_mm <yorumlayıcı> → "maj.min" (çalışmazsa boş)
  "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true
}
py_full_version() { # py_full_version <yorumlayıcı> → "Python X.Y.Z" (çalışmazsa boş)
  "$1" --version 2>&1 | head -n 1 || true
}
py_ge_floor() { # py_ge_floor <maj.min> → rc=0 (tabanı sağlar)
  case "$1" in
    [0-9]*.[0-9]*) ;;
    *) return 1 ;;
  esac
  local maj=${1%%.*} min=${1#*.}
  maj=${maj#0}; min=${min#0}
  [ -z "$maj" ] && maj=0
  [ -z "$min" ] && min=0
  case "$maj$min" in *[!0-9]*) return 1;; esac
  if [ "$maj" -gt "$BROWSER_MIN_PY_MAJOR" ]; then
    return 0
  fi
  if [ "$maj" -eq "$BROWSER_MIN_PY_MAJOR" ] && [ "$min" -ge "$BROWSER_MIN_PY_MINOR" ]; then
    return 0
  fi
  return 1
}
mm_less() { # mm_less <a-maj.min> <b-maj.min> → rc=0 (a<b)
  local amaj=${1%%.*} amin=${1#*.} bmaj=${2%%.*} bmin=${2#*.}
  amaj=${amaj#0}; amin=${amin#0}; bmaj=${bmaj#0}; bmin=${bmin#0}
  [ -z "$amaj" ] && amaj=0
  [ -z "$amin" ] && amin=0
  [ -z "$bmaj" ] && bmaj=0
  [ -z "$bmin" ] && bmin=0
  case "$amaj$amin$bmaj$bmin" in *[!0-9]*) return 1;; esac
  if [ "$amaj" -lt "$bmaj" ]; then
    return 0
  fi
  if [ "$amaj" -gt "$bmaj" ]; then
    return 1
  fi
  [ "$amin" -lt "$bmin" ]
}
find_browser_python() { # tabanı sağlayan EN-DÜŞÜK yorumlayıcının yolu; yoksa boş
  local cand resolved mm best best_mm seen hbin dirs
  hbin="${HOME:-/nonexistent}"
  if [ -n "${DEV_BOOTSTRAP_PYTHON_DIRS:-}" ]; then
    dirs=$DEV_BOOTSTRAP_PYTHON_DIRS
  else
    dirs="python3 python3.10 python3.11 python3.12 python3.13 python3.14 /opt/homebrew/bin/python3 /opt/homebrew/bin/python3.* /usr/local/bin/python3 /usr/local/bin/python3.* $hbin/.local/bin/python3* /usr/bin/python3 /usr/bin/python3.*"
  fi
  best=""; best_mm=""; seen=" "
  # shellcheck disable=SC2086 # dirs bilinçli split+glob (boşluklu yol yok)
  for cand in $dirs; do
    case "$cand" in
      python3|python3.*)
        resolved=$(command -v "$cand" 2>/dev/null || true) ;;
      *)
        resolved=$cand ;;
    esac
    [ -n "$resolved" ] && [ -x "$resolved" ] || continue
    case "$seen" in *" $resolved "*) continue;; esac
    seen="$seen$resolved "
    mm=$(py_mm "$resolved")
    py_ge_floor "$mm" || continue
    if [ -z "$best" ]; then
      best=$resolved; best_mm=$mm; continue
    fi
    if mm_less "$mm" "$best_mm"; then
      best=$resolved; best_mm=$mm
    fi
  done
  printf '%s' "$best"
}
browser_floor_die() { # $1 = yetersiz yorumlayıcı; $2 = aday (boş: yok) — KOMUT basmaz
  local interp="$1" cand="$2" have_full floor scanned
  floor="$BROWSER_MIN_PY_MAJOR.$BROWSER_MIN_PY_MINOR"
  have_full=$(py_full_version "$interp")
  [ -n "$have_full" ] || have_full="bilinmiyor"
  if [ -n "$cand" ]; then
    die "tarayıcı tabanı: pin'li playwright Python >=$floor ister; $interp ($have_full) yetersiz. Otomatik yeniden kurma kapalı (DEV_BOOTSTRAP_NO_REBUILD) — uygun yorumlayıcı hazır: $cand. Bu değişkeni kaldırıp betiği yeniden çalıştır."
  fi
  if [ -n "${DEV_BOOTSTRAP_PYTHON_DIRS:-}" ]; then
    scanned="DEV_BOOTSTRAP_PYTHON_DIRS ($DEV_BOOTSTRAP_PYTHON_DIRS)"
  else
    scanned="PATH'teki python3.10+ ile /opt/homebrew/bin, /usr/local/bin, ~/.local/bin, /usr/bin altındaki python3.*"
  fi
  die "tarayıcı tabanı: pin'li playwright Python >=$floor ister; $interp ($have_full) yetersiz ve tabanı sağlayan python3 bulunamadı (aranan: $scanned). Python >=$floor kurup betiği yeniden çalıştır."
}
browser_floor_rebuild() { # $1 = yetersiz yorumlayıcı, $2 = tabanı sağlayan yorumlayıcı
  local interp="$1" cand="$2" floor stage
  floor="$BROWSER_MIN_PY_MAJOR.$BROWSER_MIN_PY_MINOR"
  stage="$VENV.rebuild.$$"
  if [ -d "$VENV" ]; then
    say "tarayıcı tabanı: $interp (>= $floor gerekir) yetersiz → venv $cand ile YENİDEN kuruluyor"
  else
    say "tarayıcı tabanı: venv yok → $cand ile kuruluyor"
  fi
  # provision_venv_z3 bu override'ı tek kaynak olarak kullanır.
  DEV_BOOTSTRAP_PYTHON3="$cand"
  export DEV_BOOTSTRAP_PYTHON3
  # ATOMİK: yeni venv YAN yolda kurulur, başarılıysa eskisinin yerine geçer.
  # Böylece kurulum yarıda ölürse kullanıcı venvsiz kalmaz.
  rm -rf "$stage"
  VENV="$stage" VENV_PY="$stage/bin/python" provision_venv_z3 || \
    die "venv yeniden kurulamadı ($cand) — eski venv korundu"
  rm -rf "$VENV"
  mv "$stage" "$VENV" || die "venv taşınamadı: $VENV"
  say "tarayıcı tabanı: venv hazır ($cand)"
}
browser_floor_gate() { # kurulum-yolunda tabanı UYGULA: gerekirse venv'i kendisi kurar
  local interp mm cand
  interp="$VENV_PY"
  if [ ! -x "$interp" ]; then
    interp=$(venv_creator)
  fi
  mm=""
  if [ -n "$interp" ]; then
    mm=$(py_mm "$interp")
  fi
  if py_ge_floor "$mm"; then
    return 0
  fi
  cand=$(find_browser_python)
  if [ -n "${DEV_BOOTSTRAP_NO_REBUILD:-}" ]; then
    browser_floor_die "${interp:-python3}" "$cand"
  fi
  if [ -z "$cand" ]; then
    browser_floor_die "${interp:-python3}" ""
  fi
  browser_floor_rebuild "${interp:-python3}" "$cand"
}
# Plan-modu yardımcıları: conf'taki `unit.anahtar=değer` metadata'sını okur.
meta() {  # meta <unit> <anahtar> → değer ya da ?
  local v
  v=$(grep -E "^$1\.$2=" "$CONF" 2>/dev/null | cut -d= -f2 | tail -n 1) || true
  [ -n "$v" ] || v="?"
  printf '%s' "$v"
}
fmt_cost() {  # fmt_cost <değer> <ek> → sayıysa ekli, değilse çıplak
  case "$1" in
    *[!0-9]*) printf '%s' "$1" ;;
    *) printf '%s%s' "$1" "$2" ;;
  esac
}
print_plan() {  # $1 = "unit=sonuç" satırları; $2 = başlık (varsayılan: tahmin)
  # Kurulum YAPMAZ, exit kararı vermez; ölçümler conf'tan (unit.install_time_s/disk_mb).
  say "${2:-PROVISION PLAN (tahmin: 2026-10-23 tek ölçüm, sıcak önbellek)}"
  printf '%-14s %-7s %-10s %-10s\n' "unit" "status" "est_time" "est_disk"
  local tot_t=0 tot_d=0 miss_t=0 miss_d=0 line u r t d
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    u=${line%%=*}
    r=${line##*=}
    t=$(meta "$u" install_time_s)
    d=$(meta "$u" disk_mb)
    printf '%-14s %-7s %-10s %-10s\n' "$u" "$r" "$(fmt_cost "$t" s)" "$(fmt_cost "$d" MB)"
    case "$t" in *[!0-9]*) ;; *) tot_t=$((tot_t + t));; esac
    case "$d" in *[!0-9]*) ;; *) tot_d=$((tot_d + d));; esac
    if [ "$r" = "fail" ]; then
      case "$t" in *[!0-9]*) ;; *) miss_t=$((miss_t + t));; esac
      case "$d" in *[!0-9]*) ;; *) miss_d=$((miss_d + d));; esac
    fi
  done < <(printf '%s\n' "$1")
  printf 'TOTAL (all units): ~%ss, ~%sMB\n' "$tot_t" "$tot_d"
  printf 'TO-PROVISION (fail only): ~%ss, ~%sMB\n' "$miss_t" "$miss_d"
}
UNITS=(dashboard_next venv_z3 pptx)

case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --check)
    plan=0
    if [ "$#" -eq 2 ]; then
      [ "$2" = "--plan" ] || { usage >&2; exit 2; }
      plan=1
    elif [ "$#" -ne 1 ]; then
      usage >&2
      exit 2
    fi
    # Emit JSON unit inventory, collecting results first
    first=1
    failures=0
    results=""
    printf '{\n'
    for u in "${UNITS[@]}"; do
      result="ok"
      if ! "check_$u"; then
        result="fail"
        failures=$((failures + 1))
      fi
      results="$results$u=$result"$'\n'
      if [ "$first" -eq 1 ]; then
        first=0
      else
        printf ',\n'
      fi
      printf '      "%s": "%s"' "$u" "$result"
    done
    printf '\n}\n'
    if [ "$plan" -eq 1 ]; then
      print_plan "$results"
      exit 0
    fi
    if [ "$failures" -gt 0 ]; then
      exit 1
    fi
    exit 0
    ;;
  --validate)
    # bootstrap_units.conf satırlarının gerçek yol/paketlere çözüldüğünü
    # doğrular; yazım hatasında fail-closed. --json: manifest sidecar çıktısı.
    [ "$#" -le 2 ] || { usage >&2; exit 2; }
    if [ "$#" -eq 2 ] && [ "$2" != "--json" ]; then
      usage >&2
      exit 2
    fi
    VALIDATE_PY=$(python3_bin) || VALIDATE_PY=""
    if [ -z "$VALIDATE_PY" ]; then
      die "--validate için python3 bulunamadı: PATH'te ve /opt/homebrew/bin, /usr/local/bin, ~/.local/bin, /usr/bin altında yok. DEV_BOOTSTRAP_PYTHON3=/tam/yol/python3 ver."
    fi
    "$VALIDATE_PY" "$ROOT/_calisma/CIKTI/check_bootstrap_units.py" ${2:+"$2"}
    exit $?
    ;;
  "") ;;
  *)
    usage >&2
    exit 2
    ;;
esac

# Taban kapısı yalnız kurulum-yolunda (bayraksız): --check raporlar, öldürmez.
if [ -z "${1:-}" ]; then
  browser_floor_gate
fi

# Kurulum YOLU: önce durumları TEK geçişte ölç (npm dry-run pahalı), gereken
# varsa maliyet tablosunu (conf'taki install_time_s/disk_mb) BAS, sonra kur.
results=""
NEEDS=()
for u in "${UNITS[@]}"; do
  if "check_$u"; then
    results="$results$u=ok"$'\n'
  else
    results="$results$u=fail"$'\n'
    NEEDS[${#NEEDS[@]}]=$u
  fi
done

# Her şey kuruluysa tablo gürültü olur; yalnız kurulacak bir şey varsa bas.
if [ "${#NEEDS[@]}" -gt 0 ]; then
  print_plan "$results" "PROVISION PLAN — kurulum ÖNCESİ (conf ölçümleri: install_time_s/disk_mb)"
fi

while IFS= read -r line; do
  [ -n "$line" ] || continue
  u=${line%%=*}
  r=${line##*=}
  if [ "$r" = "ok" ]; then
    say "$u: up to date"
  else
    "provision_$u"
  fi
done <<PLAN_ROWS
$results
PLAN_ROWS

say "BOOTSTRAP OK"
