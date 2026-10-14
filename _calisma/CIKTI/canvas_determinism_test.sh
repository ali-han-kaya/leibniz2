#!/usr/bin/env bash
# canvas_determinism_test.sh — Incidental Proof (canvas ailesi) determinizm deneyi.
#
# Sözleşme (tek çağıran: docs/Makefile.texlive `plate-book-check`):
#   ortam girişi:
#     TEX_SOURCE         (zorunlu) canvas .tex yolu — kitap ya da bir levha
#     DETERMINISM_OUT    (ops.)    rapor yolu
#     TECTONIC_BIN       (ops.)    tectonic ikili yolu (yoksa PATH)
#     SOURCE_DATE_EPOCH  (ops.)    aile sabiti; varsayılan 1700000000
#   çıkış: 0 verdict=PASS · 1 fail-closed (kaynak yok / determinizm kırığı,
#          rapor verdict=FAIL yazılır) · 2 motor yok
#
# Rapor (key=value; Makefile kanıt echo'su bu satırları grep'ler):
#   source, tectonic, source_date_epoch, hash_form, id_form,
#   tectonic_raw_run1_sha256, tectonic_raw_run2_sha256,
#   tectonic_run1_sha256, tectonic_run2_sha256, residual, verdict
#   `tectonic_run*_sha256` KANONİK (/ID nötr) hash'lerdir; tek uygulama
#   _calisma/CIKTI/pdf_id_canonical.py (ham hash'ler de raporlanır — hiçbir
#   fark gizlenmez). Raporda hash_form/id_form bulunur ki "kanonik" iddiası
#   denetlenebilir olsun (desen tutmazsa canonical == raw, id_form=id_absent).
#
# Neden tectonic (pdfTeX değil): canvas kaynakları fontspec + yerel .ttf ve
# TikZ kullanır — XeTeX sözleşmesi; pdfTeX bu kaynağı derleyemez (ölçüldü,
# el yazması ailesi ayrı bir Makefile hattında yaşar).
#
# SDE AİLE SABİTİ: kaynaklar gömülü /CreationDate taşır. SDE verilmezse
# varsayılan aile sabitidir (1700000000); böylece unset bir çağrı motorun
# içine GÜNCEL zamanı gömdürüp her koşumda farklı hash üretmez.
#
# İki BAĞIMSIZ koşum: her koşum kendi boş dizinine derler; aynı SDE ile
# kanonik hash'ler eşit olmalıdır. Değilse verdict=FAIL ve rc=1 (fail-closed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CIKTI="$ROOT/_calisma/CIKTI"

SRC="${TEX_SOURCE:-}"
SDE="${SOURCE_DATE_EPOCH:-1700000000}"
TECTONIC="${TECTONIC_BIN:-$(command -v tectonic 2>/dev/null || true)}"
OUT="${DETERMINISM_OUT:-$ROOT/docs/ci_simulate/canvas_determinism/$(basename "${SRC%.tex}").determinism.txt}"

if [[ -z "$SRC" ]]; then
  echo "FAIL: TEX_SOURCE verilmedi — canvas kaynağı gerekli" >&2
  exit 1
fi
if [[ ! -f "$SRC" ]]; then
  echo "FAIL: canvas kaynağı yok: $SRC" >&2
  exit 1
fi
if [[ -z "$TECTONIC" || ! -x "$TECTONIC" ]]; then
  echo "FAIL: tectonic bulunamadı (TECTONIC_BIN= veya PATH) — canvas ailesi XeTeX sözleşmesi, pdfTeX derleyemez" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 yok — kanonik hash üretilemez (kanıt yoksa PASS yok)" >&2
  exit 1
fi

# Derleme KAYNAK DİZİNİNDE koşar: fontspec Path= yerel .ttf'leri, kitap ise
# \includegraphics ile kanonik levha PDF'lerini orada arar. Yazma yalnız
# --outdir'e gider (kaynak dizinine asla).
SRCDIR="$(cd "$(dirname "$SRC")" && pwd)"
BASE="$(basename "$SRC")"
PDF="$(basename "${BASE%.tex}").pdf"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/r1" "$tmp/r2"

run_engine() {  # run_engine <outdir> <log>
  ( cd "$SRCDIR" && SOURCE_DATE_EPOCH="$SDE" "$TECTONIC" --outdir "$1" "$BASE" ) >"$2" 2>&1
}

if ! run_engine "$tmp/r1" "$tmp/r1.log"; then
  echo "FAIL: tectonic run1 düştü ($BASE) — log kuyruğu:" >&2
  tail -20 "$tmp/r1.log" >&2
  exit 1
fi
if ! run_engine "$tmp/r2" "$tmp/r2.log"; then
  echo "FAIL: tectonic run2 düştü ($BASE) — log kuyruğu:" >&2
  tail -20 "$tmp/r2.log" >&2
  exit 1
fi

for d in r1 r2; do
  if [[ ! -f "$tmp/$d/$PDF" ]]; then
    echo "FAIL: tectonic --outdir honor edilmedi: $tmp/$d/$PDF yok" >&2
    exit 1
  fi
done

raw_sha() { sha256sum "$1" | awk '{print $1}'; }

# canonical_sha FILE → "<64-hex> <id_found|id_absent>"; tek uygulama
# pdf_id_canonical.py (buradaki regex ikinci bir gerçeklik olurdu).
canonical_sha() {
  python3 - "$1" "$CIKTI" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
import pdf_id_canonical as c
digest, found = c.canonical_sha256_path(sys.argv[1])
if digest is None:
    sys.exit("kanonik hash okunamadı: %s" % sys.argv[1])
print("%s %s" % (digest, "id_found" if found else "id_absent"))
PY
}

read -r c1 id1 <<<"$(canonical_sha "$tmp/r1/$PDF")"
read -r c2 id2 <<<"$(canonical_sha "$tmp/r2/$PDF")"
r1="$(raw_sha "$tmp/r1/$PDF")"
r2="$(raw_sha "$tmp/r2/$PDF")"

# Koşumlar arasında /ID biçimi tutarsızsa karşılaştırma geçersizdir (bir yan
# kanonik, öteki ham) — fail-closed.
if [[ "$id1" != "$id2" ]]; then
  echo "FAIL: /ID biçimi koşumlar arasında tutarsız ($id1 vs $id2) — kanonik karşılaştırma geçersiz" >&2
  exit 1
fi
# /ID deseni bulunamazsa canonical == raw düşer (modülün fail-safe'i); o
# durumda "kanonik hash" iddiası KANITLANAMAZ — trende ham hash'i kanonik
# diye yazmaktansa burada kırmızı ver.
if [[ "$id1" != "id_found" ]]; then
  echo "FAIL: /ID deseni bulunamadı ($id1) — kanonik hash iddiası kanıtlanamaz" >&2
  exit 1
fi

if [[ "$c1" == "$c2" ]]; then
  verdict=PASS
  if [[ "$r1" == "$r2" ]]; then
    residual=none
  else
    residual="/ID (yalnız /ID farklı; /ID haric baytlar birebir aynı, kanonik hash eşit)"
  fi
else
  verdict=FAIL
  residual=content
fi

mkdir -p "$(dirname "$OUT")"
{
  printf 'Canvas (Incidental Proof) determinism evidence\n'
  printf 'source=%s\n' "$SRC"
  printf 'tectonic=%s\n' "$TECTONIC"
  printf 'source_date_epoch=%s\n' "$SDE"
  printf 'hash_form=canonical (/ID notr; tek uygulama pdf_id_canonical.py)\n'
  printf 'id_form=%s\n' "$id1"
  printf 'tectonic_raw_run1_sha256=%s\ntectonic_raw_run2_sha256=%s\n' "$r1" "$r2"
  printf 'tectonic_run1_sha256=%s\ntectonic_run2_sha256=%s\n' "$c1" "$c2"
  printf 'residual=%s\n' "$residual"
  printf 'verdict=%s\n' "$verdict"
} > "$OUT.tmp-$$"
mv "$OUT.tmp-$$" "$OUT"

echo "canvas determinism: $BASE verdict=$verdict residual=${residual%% *} canonical=${c1:0:12}… (rapor: $OUT)"
if [[ "$verdict" != "PASS" ]]; then
  echo "FAIL: canvas determinizm kırığı ($BASE): $c1 != $c2" >&2
  exit 1
fi
