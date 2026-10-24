#!/usr/bin/env bash
# docker_patch_build_args.sh — güvenlik-yama build-arg'larının TEK çözümleyicisi.
#
# Neden var: iki build yolu (CI image-scan job'ı ve smoke script'inin build'i)
# aynı override kapısından geçmeli. Floor'ların tek kopyası Dockerfile ARG
# default'udur; bu script onu okur, override varsa değiştirir, yoksa AYNEN
# taşır — workflow'da ikinci bir kopya yaşamaz (drift imkânsız).
#
# Boş override "yama katmanını kapat" demek DEĞİLDİR: Dockerfile'daki
# empty-guard zaten boş değeri "yama yok" kanıtı sayar; bu yüzden boş env
# değeri default'u ezmez. Default okunamazsa fail-closed (rc=1) — sessizce
# floorsuz build yapılmaz.
#
# Kullanım:
#   docker_patch_build_args.sh --github-output   # $GITHUB_OUTPUT: apt= / python=
#   docker_patch_build_args.sh --flags           # docker CLI: --build-arg=NAME=VALUE
#   docker_patch_build_args.sh --values          # NAME=VALUE (log/kanıt)
# Ortam:
#   SECURITY_PATCH_PACKAGES         apt katmanı override (boş → Dockerfile default)
#   PYTHON_SECURITY_PATCH_PACKAGES  pip katmanı override (boş → Dockerfile default)
#   DOCKERFILE                      varsayılan: $ROOT/Dockerfile
# Çıkış: 0 başarı · 1 default okunamadı (fail-closed) · 2 kullanım hatası
# Kanıt satırları (apt_source= / python_source=) stderr'e yazılır; --github-output
# modunda stdout yalnız key=value taşır (GITHUB_OUTPUT'a karışmasın).
set -euo pipefail

MODE="${1:---github-output}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${DOCKERFILE:-$ROOT/Dockerfile}"

[ -f "$DOCKERFILE" ] || { echo "ERROR: Dockerfile yok: $DOCKERFILE" >&2; exit 1; }

# Dockerfile'daki `ARG NAME="..."` default'unu okur (floor'ların tek kaynağı).
arg_default() {
  grep -m1 "^ARG $1=" "$DOCKERFILE" | sed "s/^ARG $1=//; s/^\"//; s/\"$//" || true
}

APT_DEFAULT="$(arg_default SECURITY_PATCH_PACKAGES)"
PY_DEFAULT="$(arg_default PYTHON_SECURITY_PATCH_PACKAGES)"
[ -n "$APT_DEFAULT" ] || { echo "ERROR: $DOCKERFILE içinde ARG SECURITY_PATCH_PACKAGES default'u yok" >&2; exit 1; }
[ -n "$PY_DEFAULT" ] || { echo "ERROR: $DOCKERFILE içinde ARG PYTHON_SECURITY_PATCH_PACKAGES default'u yok" >&2; exit 1; }

APT="${SECURITY_PATCH_PACKAGES:-$APT_DEFAULT}"
PY="${PYTHON_SECURITY_PATCH_PACKAGES:-$PY_DEFAULT}"
if [ -n "${SECURITY_PATCH_PACKAGES:-}" ]; then APT_SOURCE=override; else APT_SOURCE=dockerfile-default; fi
if [ -n "${PYTHON_SECURITY_PATCH_PACKAGES:-}" ]; then PY_SOURCE=override; else PY_SOURCE=dockerfile-default; fi

case "$MODE" in
  --github-output)
    printf 'apt_source=%s\npython_source=%s\n' "$APT_SOURCE" "$PY_SOURCE" >&2
    printf 'apt=%s\npython=%s\n' "$APT" "$PY"
    ;;
  --flags)
    printf -- '--build-arg=SECURITY_PATCH_PACKAGES=%s\n' "$APT"
    printf -- '--build-arg=PYTHON_SECURITY_PATCH_PACKAGES=%s\n' "$PY"
    ;;
  --values)
    printf 'apt_source=%s\npython_source=%s\n' "$APT_SOURCE" "$PY_SOURCE" >&2
    printf 'SECURITY_PATCH_PACKAGES=%s\nPYTHON_SECURITY_PATCH_PACKAGES=%s\n' "$APT" "$PY"
    ;;
  *)
    echo "KULLANIM: $0 [--github-output|--flags|--values]" >&2
    exit 2
    ;;
esac
