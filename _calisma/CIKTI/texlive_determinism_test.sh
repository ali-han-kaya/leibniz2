#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEX="${TEX_SOURCE:-$ROOT/_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17/ingiliz_empirizmi_v3.tex}"
OUT="${DETERMINISM_OUT:-$ROOT/docs/ci_simulate/texlive_determinism/texlive_determinism_report.txt}"
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

printf '%s\n' "TeXLive determinism evidence" > "$OUT"
printf 'source=%s\n' "$TEX" >> "$OUT"
SDE="${SOURCE_DATE_EPOCH:-0}"
printf 'pdflatex=%s\ntectonic=%s\nsource_date_epoch=%s\n' "$PDFlatex" "$TECTONIC" "$SDE" >> "$OUT"

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
printf 'tectonic_sha256=%s\n' "$(run_hash "$tmp/tectonic/$pdf_name")" >> "$OUT"

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
printf 'texlive_run1_sha256=%s\ntexlive_run2_sha256=%s\n' "$h1" "$h2" >> "$OUT"
if [[ "$h1" != "$h2" ]]; then
  printf 'verdict=FAIL\n' >> "$OUT"
  exit 1
fi
printf 'verdict=PASS\n' >> "$OUT"
