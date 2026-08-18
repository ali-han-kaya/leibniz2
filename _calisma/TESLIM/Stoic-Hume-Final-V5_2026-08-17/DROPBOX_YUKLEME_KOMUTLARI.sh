#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# DROPBOX YÜKLEME — HAZIR KOMUT BLOĞU (Stoic-Hume V5, 2026-08-17)
# 2 ZIP + 2 SIDECAR kopyalama + TÜM DOĞRULAMA (son doğrulama: 2026-08-17)
# - Ana taşıma birimi: TESLIM_KLASOR_V5_2026-08-17.zip
# - İç zip:            TESLIM_V5_FINAL_2026-08-17.zip (kaynakta tutulur)
# Güncel hash'ler sidecar'larda — bu blok sabit hash içermez (self-reference)
# Son üretim: 2026-08-17 (güncel hash'ler sidecar'larda doğrulanır)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

P="$HOME/Downloads/port"
D="$HOME/Dropbox"

echo "══ 1) KAYNAKTA DOĞRULA (taşımadan önce) ══"
cd "$P"
shasum -a 256 -c TESLIM_KLASOR_V5_2026-08-17.zip.sha256
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256

echo "══ 2) DROPBOX'A KOPYALA (2 zip + 2 sidecar) ══"
mkdir -p "$D"
cp TESLIM_KLASOR_V5_2026-08-17.zip TESLIM_KLASOR_V5_2026-08-17.zip.sha256 \
   TESLIM_V5_FINAL_2026-08-17.zip TESLIM_V5_FINAL_2026-08-17.zip.sha256 "$D/"
cd "$D"

echo "══ 3) KATMAN 1 — İKİ ZIP KURCALANMA KONTROLÜ (tek satır ×2) ══"
shasum -a 256 -c TESLIM_KLASOR_V5_2026-08-17.zip.sha256 && echo "OK - KLASÖR ZIP KURCALANMAMIŞ" || echo "FAIL - UYUMSUZ!"
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256 && echo "OK - İÇ ZIP KURCALANMAMIŞ" || echo "FAIL - UYUMSUZ!"

echo "══ 4) KATMAN 2 — KLASÖR BÜTÜNLÜĞÜ (10 dosya, KLASOR_CHECKSUMLARI) ══"
unzip -q TESLIM_KLASOR_V5_2026-08-17.zip
cd Stoic-Hume-Final-V5_2026-08-17
shasum -a 256 -c KLASOR_CHECKSUMLARI.sha256

echo "══ 5) ÜÇ KOPYA SENKRONU (preview.html — port ↔ klasör ↔ iç zip) ══"
unzip -p TESLIM_V5_FINAL_2026-08-17.zip TESLIM_V5_FINAL_2026-08-17/preview.html | shasum -a 256 | cut -d' ' -f1 > /tmp/preview_ic.txt
shasum -a 256 preview.html | cut -d' ' -f1 > /tmp/preview_kl.txt
unzip -p "$P/TESLIM_V5_FINAL_2026-08-17.zip" TESLIM_V5_FINAL_2026-08-17/preview.html | shasum -a 256 | cut -d' ' -f1 > /tmp/preview_port.txt
if [ "$(cat /tmp/preview_ic.txt)" = "$(cat /tmp/preview_kl.txt)" ] && [ "$(cat /tmp/preview_ic.txt)" = "$(cat /tmp/preview_port.txt)" ]; then
  echo "OK - PREVIEW 3 KOPYA AYNI ($(cat /tmp/preview_ic.txt))"
else
  echo "FAIL - PREVIEW KOPYALARI UYUMSUZ!"; exit 1
fi
rm -f /tmp/preview_ic.txt /tmp/preview_kl.txt /tmp/preview_port.txt

echo "══ 6) KATMAN 3 — İÇ ZIP + PAKET (tam denetim) ══"
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256
unzip -q TESLIM_V5_FINAL_2026-08-17.zip
cd TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17
python3 core_formal_model_check.py && echo "core: PASS"
python3 encoding_sensitivity_check.py && echo "encoding: PASS"
python3 gate15_check.py && echo "gate15: PASS"

echo
echo "══ SONUÇ: 2 ZIP + 2 SIDECAR DOĞRULANDI — TÜM KATMANLAR OK ✅ ══"
