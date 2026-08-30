#!/usr/bin/env bash
# texlive_determinism_hook.sh — pre-commit hook: TeXLive+SDE PDF determinism
# deneyini HER COMMITTE yeniden üretir (fail-closed).
#
# texlive_determinism_test.sh'i koşar: ingiliz_empirizmi_v3.tex üzerinde
# ÖNCE (tectonic, tek derleme) / SONRA (TeXLive + SOURCE_DATE_EPOCH, 2
# bağımsız derleme) hash karşılaştırması. SONRA'nın iki run'ı byte-farklıysa
# deney exit 1 döner → commit BLOKE (tectonic→TeXLive göçü determinism
# getirmedi). Rapor: docs/ci_simulate/texlive_determinism/ (git takipli).
#
# Araç yoksa SKIP (exit 0) — kapı yalnızca araçların var olduğu ortamda
# iddia üretir (check-lake-evidence deseni). Hafif K21 self-testi
# (verify_delivery.py --check-sde) her ortamda koşar; bu uçtan uca deney
# TeXLive'ın kurulu olduğu makinede devreye girer. CI'da TeXLive yoksa bu
# hook atlanır (advisory yükü yok).
#
# TeXLive konumu: TEXLIVE_BIN env'i veya /usr/local/texlive/*/bin/* otomatik
# keşfi. tectonic: PATH'te (veya TECTONIC_BIN env'i — test script'ine geçer).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST="$REPO_ROOT/_calisma/CIKTI/texlive_determinism_test.sh"

# TeXLive: TEXLIVE_BIN env'i önceliklidir; yoksa yaygın kurulum dizinlerini dene.
TEXLIVE_BIN="${TEXLIVE_BIN:-}"
if [ -z "$TEXLIVE_BIN" ]; then
  for cand in /usr/local/texlive/*/bin/*; do
    if [ -x "$cand/pdflatex" ]; then
      TEXLIVE_BIN="$cand"
      break
    fi
  done
fi

if ! command -v tectonic >/dev/null 2>&1 && [ -z "${TECTONIC_BIN:-}" ]; then
  echo "SKIP: tectonic kurulu değil — TeXLive+SDE determinism deneyi atlandı"
  echo "      (fail-closed koruması K21 --check-sde + CI; deney TeXLive+tectonic ortamında koşar)"
  exit 0
fi
if [ -z "$TEXLIVE_BIN" ] || [ ! -x "$TEXLIVE_BIN/pdflatex" ]; then
  echo "SKIP: TeXLive pdflatex bulunamadı (TEXLIVE_BIN=/path/to/texbin verin veya"
  echo "      /usr/local/texlive kurun) — deney atlandı"
  exit 0
fi

echo "── TeXLive+SDE PDF determinism deneyi (tectonic→TeXLive göç kanıtı) ──"
echo "  tectonic = ${TECTONIC_BIN:-$(command -v tectonic)}"
echo "  pdflatex = $TEXLIVE_BIN/pdflatex"
TEXLIVE_BIN="$TEXLIVE_BIN" bash "$TEST"
