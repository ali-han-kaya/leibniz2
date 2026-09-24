#!/usr/bin/env bash
# canvas_determinism_test.sh — canvas (Incidental Proof) TeX kaynağının
# determinizm deneyi: TEK motor (tectonic/XeTeX), iki bağımsız SDE-koşumu,
# kanonik (/ID-nötr) hash karşılaştırması.
#
# Neden ayrı betik: canvas fontspec + yerel fontlar kullanır (XeTeX sözleşmesi
# — TeXLive migration planının engine-stratification bulgusu); pdfTeX zinciri
# (texlive_determinism_test.sh) bu kaynağı derleyemez. Kanonik /ID fallback'i
# ve SDE-semantiği ana betikten aynen taşındı (iki betik tek sözleşmeyi
# paylaşıyor — test_determinism_trend_canvas.py bunu pinliyor).
#
# Kullanım:
#   bash canvas_determinism_test.sh                    # default kaynak: plate01
#   TEX_SOURCE=... TECTONIC_BIN=... bash canvas_determinism_test.sh
#
# Çıkış: DETERMINISM_OUT rapor dosyasına makine-okur key=value satırları;
#   verdict=PASS|FAIL. Exit: 0 PASS (ya da SKIP: araç yok — K3 SKIP
#   sözleşmesi), 1 FAIL (fail-closed), 2 usage.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEX="${TEX_SOURCE:-$ROOT/_calisma/CIKTI/canvas/incidental_proof_canvas.tex}"
OUT="${DETERMINISM_OUT:-$ROOT/docs/ci_simulate/canvas_determinism/canvas_determinism_report.txt}"
TECTONIC="${TECTONIC_BIN:-$(command -v tectonic 2>/dev/null || true)}"

if [[ ! -f "$TEX" ]]; then
  echo "FAIL: TeX source not found: $TEX" >&2
  exit 1
fi
if [[ -z "$TECTONIC" ]]; then
  echo "SKIP: tectonic not found (K3 SKIP sözleşmesi: cron job'ı runner araçlarıyla uyumlu)" >&2
  exit 0
fi

mkdir -p "$(dirname "$OUT")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

run_hash() { sha256sum "$1" | awk '{print $1}'; }

# canonical_sha — trailer /ID çiftini nötrleyip SHA256 döner. pdfTeX/tectonic
# her koşumda rastgele /ID üretebilir; içerik birebir aynıysa kanonik hash
# eşit. Desen eşleşmezse ham hash döner (fail-safe: hiçbir fark gizlenmez).
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

printf '%s\n' "Canvas (Incidental Proof) determinism evidence" > "$OUT"
printf 'source=%s\n' "$TEX" >> "$OUT"
SDE="${SOURCE_DATE_EPOCH:-0}"
# SDE motor'a explicit iletilir; aksi halde motor güncel zamanı gömer
# (texlive_determinism_test.sh'de ölçülen sapma: tectonic 4ad65b9b→6cfc6c0a).
export SOURCE_DATE_EPOCH="$SDE"
printf 'tectonic=%s\nsource_date_epoch=%s\n' "$TECTONIC" "$SDE" >> "$OUT"

mkdir -p "$tmp/run1" "$tmp/run2"
TEXDIR="$(cd "$(dirname "$TEX")" && pwd)"
run_idx=0
for dir in run1 run2; do
  run_idx=$((run_idx + 1))
  # GÜVENLİK: --outdir tmp — kaynak dizinine asla yazma (ana zincir sözleşmesi)
  # CWD=TEXDIR şart: tex'in fontspec Path= yolu TEXDIR'a göredir
  # (ölçüldü: başka CWD'den "font cannot be found" — Path= kpathsea-wd'siz,
  # CWD-göreli çözülür).
  if ! (cd "$TEXDIR" && "$TECTONIC" --outdir "$tmp/$dir" "$TEX" >/dev/null); then
    echo "FAIL: tectonic PDF üretemedi (run$run_idx)" >&2
    exit 1
  fi
done

pdf_name="$(basename "${TEX%.tex}.pdf")"
P1="$tmp/run1/$pdf_name"
P2="$tmp/run2/$pdf_name"
if [[ ! -f "$P1" || ! -f "$P2" ]]; then
  echo "FAIL: tectonic --outdir honor edilmedi ($tmp/run1/$pdf_name yok)" >&2
  exit 1
fi

h1="$(run_hash "$P1")"
h2="$(run_hash "$P2")"
printf 'tectonic_run1_sha256=%s\ntectonic_run2_sha256=%s\n' "$h1" "$h2" >> "$OUT"
if [[ "$h1" == "$h2" ]]; then
  printf 'residual=none\nverdict=PASS\n' >> "$OUT"
  exit 0
fi

# Ham hash farklı: kalıntı yalnız rastgele /ID mü? Kanonik karşılaştırma.
# python3 yoksa kanıt üretilemez → fail-closed.
if command -v python3 >/dev/null 2>&1; then
  c1="$(canonical_sha "$P1")"
  c2="$(canonical_sha "$P2")"
  printf 'tectonic_canonical_run1_sha256=%s\ntectonic_canonical_run2_sha256=%s\n' "$c1" "$c2" >> "$OUT"
  id1="$(grep -ao '/ID \[[^]]*\]' "$P1" | head -1 || true)"
  id2="$(grep -ao '/ID \[[^]]*\]' "$P2" | head -1 || true)"
  printf 'tectonic_run1_id=%s\ntectonic_run2_id=%s\n' "$id1" "$id2" >> "$OUT"
  if [[ "$c1" != "$c2" ]]; then
    printf 'residual=content\nverdict=FAIL\n' >> "$OUT"
    exit 1
  fi
  printf 'residual=/ID (tectonic rastgele belge kimligi; /ID haric baytlar birebir ayni)\nverdict=PASS\n' >> "$OUT"
else
  printf 'residual=unverifiable (python3 yok, kanonik karsilastirma yapilamadi)\nverdict=FAIL\n' >> "$OUT"
  exit 1
fi
