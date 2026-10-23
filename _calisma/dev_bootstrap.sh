#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: UNITS'teki araç-kümeleri — venv_z3 (pinned) + _calisma/pptx +
# apps/dashboard-next node_modules. Idempotent: kurulu araca dokunmaz.
# Kullanım: dev_bootstrap.sh [--check|--help]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
PPTX="$ROOT/_calisma/pptx"
DASH="$ROOT/apps/dashboard-next"
VIDEO="$ROOT/_calisma/video"
SHADCN="$ROOT/apps/dashboard-shadcn"
TRENDDB="$ROOT/apps/trend-db"
PINS=(z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0)

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  say "Kullanım: dev_bootstrap.sh [--check|--help]"
  say "  (bayraksız) araç-kümesini kur (idempotent)"
  say "  --check     araç-kümesi tam mı? rc=0/1 (fail-closed)"
  say "  --help      bu yardım"
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
# Lock kapıları (her npm unit için ortak): (1) `npm ci --dry-run` lock eksik/
# bozuk/senkronsuz ise non-zero döner (node_modules'a dokunmaz); (2) npm dry-run,
# lock'un kök dep girişi silinmiş hâli için rc=0 döner, bu yüzden package.json
# dep adları (dependencies + devDependencies) lock kökü ile eşleştirilir.
lock_ok() {
  local dir="$1"
  (cd "$dir" && npm ci --dry-run --no-audit --no-fund >/dev/null 2>&1) || return 1
  (cd "$dir" && node -e '
    const p = require("./package.json"), l = require("./package-lock.json");
    const root = (l.packages || {})[""] || {};
    const need = Object.keys(p.dependencies || {}).concat(Object.keys(p.devDependencies || {}));
    for (const d of need)
      if (!(root.dependencies || {})[d] && !(root.devDependencies || {})[d]) process.exit(1);
  ' >/dev/null 2>&1)
}
check_pptx() {
  lock_ok "$PPTX" && (cd "$PPTX" && node -e "require.resolve('pptxgenjs')" >/dev/null 2>&1)
}
provision_pptx() {
  say "_calisma/pptx: npm ci"
  npm ci --prefix "$PPTX" || die "_calisma/pptx npm ci"
}
check_dashboard_next() {
  lock_ok "$DASH" && [ -x "$DASH/node_modules/.bin/tsc" ] \
    && [ -x "$DASH/node_modules/.bin/next" ]
}
provision_dashboard_next() {
  say "apps/dashboard-next: npm ci"
  npm ci --prefix "$DASH" || die "apps/dashboard-next npm ci"
}
# Aşağıdaki üç unit UNITS'e EKLENMEZ: --check'i bu checkout'ta kurulmamış
# unit'ler için kırmızıya çevirmemek adına. Bağımsız çağrılabilir kalırlar.
check_video() {
  lock_ok "$VIDEO" && [ -x "$VIDEO/node_modules/.bin/remotion" ] \
    && [ -x "$VIDEO/node_modules/.bin/tsc" ]
}
provision_video() {
  say "_calisma/video: npm ci"
  npm ci --prefix "$VIDEO" || die "_calisma/video npm ci"
}
check_dashboard_shadcn() {
  lock_ok "$SHADCN" && [ -x "$SHADCN/node_modules/.bin/vite" ]
}
provision_dashboard_shadcn() {
  say "apps/dashboard-shadcn: npm ci"
  npm ci --prefix "$SHADCN" || die "apps/dashboard-shadcn npm ci"
}
check_trend_db() {
  lock_ok "$TRENDDB" && [ -x "$TRENDDB/node_modules/.bin/prisma" ] \
    && [ -x "$TRENDDB/node_modules/.bin/tsx" ]
}
provision_trend_db() {
  say "apps/trend-db: npm ci"
  npm ci --prefix "$TRENDDB" || die "apps/trend-db npm ci"
}
UNITS=(venv_z3 pptx dashboard_next)

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

say "BOOTSTRAP OK"
