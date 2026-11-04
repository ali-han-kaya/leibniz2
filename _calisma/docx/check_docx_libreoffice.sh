#!/usr/bin/env bash
# check_docx_libreoffice.sh — uretilen .docx gercekten acilabiliyor mu?
#
# Neden LibreOffice: docx bir zip+XML yigini; "dosya var" demek "belge
# acilabiliyor" demek DEGIL. Gercek bir ofis motoru belgeyi metne cevirebiliyorsa
# hem zip hem XML semasi tutarli demektir. Beklenen tanik metin(ler) ayni
# donusumde aranir — boylece belge "bos ama gecerli" olamaz.
#
# Fail-closed: donusum basarisiz, cikti yok ya da tanik metin eksikse FAIL.
# Ortam hatasi (soffice yok / girdi yok) ayri exit koduyla bildirilir — sessiz
# yesil yok, ama "arac yok" ile "belge bozuk" karistirilmaz.
#
# Kullanim:
#   check_docx_libreoffice.sh <docx> [beklenen metin ...]
# Exit: 0 PASS | 1 FAIL (belge/kontrol) | 2 ortam hatasi (girdi/arac eksik)
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "kullanim: check_docx_libreoffice.sh <docx> [beklenen metin ...]" >&2
  exit 2
fi

DOCX="$1"
shift
WITNESS=("$@")
if [ "${#WITNESS[@]}" -eq 0 ]; then
  WITNESS=("Final Release Candidate Report")
fi

[ -f "$DOCX" ] || { echo "FAIL: docx yok: $DOCX" >&2; exit 2; }

SOFFICE="$(command -v soffice || command -v libreoffice || true)"
if [ -z "$SOFFICE" ]; then
  echo "FAIL: soffice/libreoffice bulunamadi — LibreOffice kontrolu yapilamaz" >&2
  echo "(kurulum: apt-get install -y --no-install-recommends libreoffice-writer)" >&2
  exit 2
fi

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# -env:UserInstallation: paylasilan kullanici profili kilidine takilmadan
# headless kosar (CI'da es zamanli iki kosum ilk profili yaratirken cakilabilir).
if ! "$SOFFICE" --headless --norestore \
      -env:UserInstallation="file://$work/profile" \
      --convert-to txt:Text --outdir "$work" "$DOCX" >"$work/convert.log" 2>&1; then
  echo "FAIL: LibreOffice donusumu basarisiz" >&2
  sed -n '1,10p' "$work/convert.log" >&2 || true
  exit 1
fi

txt="$(find "$work" -maxdepth 1 -name '*.txt' | head -1)"
if [ -z "$txt" ]; then
  echo "FAIL: LibreOffice metin cikti uretmedi (belge acilmadi)" >&2
  exit 1
fi

missing=0
for w in "${WITNESS[@]}"; do
  if ! grep -qF -- "$w" "$txt"; then
    echo "FAIL: tanik metin bulunamadi: $w" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "verdict=FAIL"
  exit 1
fi

echo "docx=$DOCX"
echo "libreoffice=$SOFFICE"
echo "converted_txt=$(basename "$txt")"
echo "text_bytes=$(wc -c < "$txt" | tr -d ' ')"
echo "witness_count=${#WITNESS[@]}"
echo "docx_sha256=$(sha256_of "$DOCX")"
# Determinizm notu: docx paketi core.xml tarihlerini kendi zamanindan uretir;
# bu yuzden hash kosumdan kosuma DEGISIR (olculdu, 2026-09-24). Kontrol
# acilabilirlik + metin tanigi uzerinedir, byte-identity degil.
echo "verdict=PASS"
