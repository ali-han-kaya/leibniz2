#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: UNITS'teki araç-kümeleri — venv_z3 (pinned) + _calisma/pptx +
# _calisma/docx + apps/dashboard-next node_modules. Idempotent: kurulu araca
# dokunmaz.
# Kullanım: dev_bootstrap.sh [--check|--help]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
PPTX="$ROOT/_calisma/pptx"
DOCX="$ROOT/_calisma/docx"
DASH="$ROOT/apps/dashboard-next"
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
UNITS=(venv_z3 pptx docx dashboard_next)

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
