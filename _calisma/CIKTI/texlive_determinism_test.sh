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
# Ana .tex'in \input{...} bağımlılıkları (ör. core_section.tex) KAYNAK
# dizininde yaşar; -output-directory ile geçici dizinden derlenirken
# pdflatex onları bulamaz (tectonic ana dosyanın dizinini kendiliğinden
# arar). TEXINPUTS kaynak dizinini arama yoluna ekler — // alt dizinler,
# sondaki ':' varsayılan kpathsea yolunu korur.
TEXDIR="$(cd "$(dirname "$TEX")" && pwd)"
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

# canonical_sha FILE — trailer /ID çiftini nötrleyip SHA256 döner (64 hex).
# pdfTeX (SDE+FORCE_SOURCE_DATE ile bile) her koşumda RASTGELE /ID üretir;
# /CreationDate ve /ModDate sabitlenir ama /ID sabitlenmez (ölçüldü: iki
# koşum arasındaki TEK fark 64 baytlik /ID satırı). Kanonik görünüm /ID
# çiftini sabit değere indirger; içerik birebir aynıysa kanonik hash eşit.
# Desen eşleşmezse ham hash döner (fail-safe: hiçbir fark gizlenmez).
canonical_sha() {
  python3 - "$1" <<'PY'
import re, sys, hashlib
data = open(sys.argv[1], 'rb').read()
pat = re.compile(rb'/ID\s*\[\s*<[0-9a-fA-F]{32}>\s*<[0-9a-fA-F]{32}>\s*\]')
if pat.search(data):
    data = pat.sub(b'/ID [<00000000000000000000000000000000><00000000000000000000000000000000>]', data)
print(hashlib.sha256(data).hexdigest())
PY
}

printf '%s\n' "TeXLive determinism evidence" > "$OUT"
printf 'source=%s\n' "$TEX" >> "$OUT"
SDE="${SOURCE_DATE_EPOCH:-0}"
# SDE her iki motora da (tectonic + pdflatex) iletilir; aksi halde motor
# güncel zamanı gömer ve hash oturumdan oturuma değişir (ölçüldü: tectonic
# 4ad65b9b… → 6cfc6c0a…). Betik düz yaprak: alt süreçlere sızması zararsız.
export SOURCE_DATE_EPOCH="$SDE"
printf 'pdflatex=%s\ntectonic=%s\nsource_date_epoch=%s\n' "$PDFlatex" "$TECTONIC" "$SDE" >> "$OUT"

# ── Geçiş modu (Faz 0/2 sözleşmesi: docs/TEXLIVE_MIGRATION_PLAN.md) ─────
# DETERMINISM_PASSES=N: her koşum tam N pdflatex geçişi koşar (çapraz ref/
# bib çözümü ancak çok geçişte tamamlanır) ve son geçiş logunda 'Rerun to
# get' KALMADIĞI fail-closed denetlenir — K6 hizalama iddiası ancak o zaman
# yapılır. Default 1: mevcut tek-geçiş trend/hook sözleşmesi Faz 4'e dek
# korunur; Makefile.texlive target'ları PASSES=3 ile bu modu sürer.
PASSES="${DETERMINISM_PASSES:-1}"
case "$PASSES" in ''|*[!0-9]*|0)
  echo "FAIL: DETERMINISM_PASSES pozitif tam sayı olmalı: $PASSES" >&2
  exit 2 ;;
esac
printf 'passes=%s\n' "$PASSES" >> "$OUT"

mkdir -p "$tmp/tectonic" "$tmp/texlive1" "$tmp/texlive2"
# GÜVENLİK: tectonic/pdflatex'e explicit çıktı dizini verilir — gerçek
# araçlar aksi halde PDF'i KAYNAK yanına yazar ve teslim paketindeki
# kanonik PDF'i EZER. (tectonic V2 varsayılanı kaynak yanı;
# pdflatex mutlak kaynak yolunda aynısı.) -output-directory/--outdir ile
# çıktı yalnızca geçici dizine yazılır; stub testleri de uyumludur (stub
# aracı CWD'ye yazar, subshell zaten geçici dizindedir).
(
  cd "$tmp/tectonic"
  if ! "$TECTONIC" --outdir "$PWD" "$TEX" >/dev/null; then
    echo "FAIL: tectonic PDF üretemedi" >&2
    exit 1
  fi
)
pdf_name="$(basename "${TEX%.tex}.pdf")"
if [[ ! -f "$tmp/tectonic/$pdf_name" ]]; then
  echo "FAIL: tectonic PDF üretemedi (--outdir honor edilmedi: $tmp/tectonic/$pdf_name yok)" >&2
  exit 1
fi
printf 'tectonic_sha256=%s\n' "$(run_hash "$tmp/tectonic/$pdf_name")" >> "$OUT"

run_idx=0
for dir in texlive1 texlive2; do
  run_idx=$((run_idx + 1))
  (
    cd "$tmp/$dir"
    export TEXMFOUTPUT="$PWD"
    export TEXINPUTS="$TEXDIR//:"
    export TEXLIVE_RUN_INDEX="$run_idx" TEXLIVE_PASSES="$PASSES"
    i=0
    while [ "$i" -lt "$PASSES" ]; do
      i=$((i + 1))
      export TEXLIVE_PASS_INDEX="$i"
      "$PDFlatex" -interaction=nonstopmode -halt-on-error \
        -output-directory="$PWD" "$TEX" >/dev/null
    done
  )
done

# ── Rerun denetimi (yalnız çok-geçiş modunda; Faz 0) ────────────────────
# Hizalama iddiası: son geçiş logunda 'Rerun to get' YOK. Tek-geçiş modu bu
# denetimi yapmaz (hizalama iddiası üretmez); log yoksa da fail-closed —
# kanıt üretilemedi, hizalama kanıtlanamaz.
if [ "$PASSES" -gt 1 ]; then
  tex_base="$(basename "${TEX%.tex}")"
  run_idx=0
  for dir in texlive1 texlive2; do
    run_idx=$((run_idx + 1))
    logf="$tmp/$dir/$tex_base.log"
    if [[ ! -f "$logf" ]]; then
      printf 'texlive_run%s_rerun_left=unknown\n' "$run_idx" >> "$OUT"
      printf 'residual=unverifiable (run%s son-geçiş logu yok — hizalama kanıtlanamadı)\nverdict=FAIL\n' "$run_idx" >> "$OUT"
      exit 1
    fi
    rerun="$(grep -c 'Rerun to get' "$logf" || true)"
    if [ -z "$rerun" ]; then rerun=0; fi
    printf 'texlive_run%s_rerun_left=%s\n' "$run_idx" "$rerun" >> "$OUT"
    if [ "$rerun" -gt 0 ]; then
      printf 'residual=unconverged (run%s son geçiş logunda Rerun=%s — K6 hizalama iddiası üretilemez)\nverdict=FAIL\n' "$run_idx" "$rerun" >> "$OUT"
      exit 1
    fi
  done
fi

P1="$tmp/texlive1/$pdf_name"
P2="$tmp/texlive2/$pdf_name"
h1="$(run_hash "$P1")"
h2="$(run_hash "$P2")"
printf 'texlive_run1_sha256=%s\ntexlive_run2_sha256=%s\n' "$h1" "$h2" >> "$OUT"
if [[ "$h1" == "$h2" ]]; then
  printf 'residual=none\nverdict=PASS\n' >> "$OUT"
  exit 0
fi
# Ham hash farklı: kalıntı yalnızca rastgele /ID mü? Kanonik (/ID nötrlenmiş)
# karşılaştırma yapılır. python3 yoksa kanıt üretilemez → fail-closed FAIL.
if command -v python3 >/dev/null 2>&1; then
  c1="$(canonical_sha "$P1")"
  c2="$(canonical_sha "$P2")"
  printf 'texlive_canonical_run1_sha256=%s\ntexlive_canonical_run2_sha256=%s\n' "$c1" "$c2" >> "$OUT"
  id1="$(grep -ao '/ID \[[^]]*\]' "$P1" | head -1 || true)"
  id2="$(grep -ao '/ID \[[^]]*\]' "$P2" | head -1 || true)"
  printf 'texlive_run1_id=%s\ntexlive_run2_id=%s\n' "$id1" "$id2" >> "$OUT"
  if [[ "$c1" != "$c2" ]]; then
    printf 'residual=content\nverdict=FAIL\n' >> "$OUT"
    exit 1
  fi
  printf 'residual=/ID (pdfTeX rastgele belge kimligi; /ID haric baytlar birebir ayni)\nverdict=PASS\n' >> "$OUT"
else
  printf 'residual=unverifiable (python3 yok, kanonik karsilastirma yapilamadi)\nverdict=FAIL\n' >> "$OUT"
  exit 1
fi
