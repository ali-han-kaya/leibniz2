#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEX="${TEX_SOURCE:-$ROOT/_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17/ingiliz_empirizmi_v3.tex}"
# Rapor yolu: varsayılan logs/ — CI'da precommit-logs artifact'ı (path: logs/)
# bütünüyle yüklenir, yani kanıt (3 sha256 + verdict) runner'da ölmez.
# Eski varsayılan docs/ci_simulate/ YOLU GITIGNORE'LUYDU ve hiçbir upload
# kapsamında değildi → PASS kanıtı görünmez oluyordu (coe A sınıfı maskeleme).
OUT="${DETERMINISM_OUT:-$ROOT/logs/texlive_determinism_report.txt}"
PDFlatex="${TEXLIVE_BIN:-}/pdflatex"
TECTONIC="${TECTONIC_BIN:-$(command -v tectonic 2>/dev/null || true)}"

if [[ ! -f "$TEX" ]]; then
  echo "FAIL: TeX source not found: $TEX" >&2
  exit 1
fi
if [[ ! -x "$PDFlatex" || -z "$TECTONIC" ]]; then
  echo "SKIP: tectonic and TeXLive pdflatex are required" >&2
  exit 0
fi

mkdir -p "$(dirname "$OUT")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

run_hash() {
  sha256sum "$1" | awk '{print $1}'
}

# Kanıt hem stdout'a hem rapor dosyasına yazılır: artifact indirilmese bile
# pre-commit log'unda (logs/precommit.log) görünür — ikinci yüzeyleme yolu.
record() { printf '%s\n' "$1" | tee -a "$OUT"; }

: > "$OUT"
record "TeXLive determinism evidence"
record "source=$TEX"
SDE="${SOURCE_DATE_EPOCH:-0}"
printf 'pdflatex=%s\ntectonic=%s\nsource_date_epoch=%s\n' "$PDFlatex" "$TECTONIC" "$SDE" | tee -a "$OUT"

mkdir -p "$tmp/tectonic" "$tmp/texlive1" "$tmp/texlive2"
(
  cd "$tmp/tectonic"
  if ! "$TECTONIC" "$TEX" >/dev/null; then
    echo "FAIL: tectonic PDF üretemedi" >&2
    exit 1
  fi
)
pdf_name="$(basename "${TEX%.tex}.pdf")"
if [[ ! -f "$tmp/tectonic/$pdf_name" ]]; then
  echo "FAIL: tectonic PDF üretemedi" >&2
  exit 1
fi
record "tectonic_sha256=$(run_hash "$tmp/tectonic/$pdf_name")"

for dir in texlive1 texlive2; do
  (
    cd "$tmp/$dir"
    export SOURCE_DATE_EPOCH="$SDE"
    export TEXMFOUTPUT="$PWD"
    "$PDFlatex" -interaction=nonstopmode -halt-on-error "$TEX" >/dev/null
  )
done
h1="$(run_hash "$tmp/texlive1/$(basename "${TEX%.tex}.pdf")")"
h2="$(run_hash "$tmp/texlive2/$(basename "${TEX%.tex}.pdf")")"
printf 'texlive_run1_sha256=%s\ntexlive_run2_sha256=%s\n' "$h1" "$h2" | tee -a "$OUT"
if [[ "$h1" != "$h2" ]]; then
  record "verdict=FAIL"
  exit 1
fi
record "verdict=PASS"
