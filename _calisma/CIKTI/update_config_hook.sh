#!/usr/bin/env bash
# =============================================================================
# update_config_hook.sh — pre-commit hook: config'i paket içeriğinden senkron et.
#
# Neden: repack (repack_delivery.py) paketi yeniden ürettiğinde sayfa/referans/
# manifest sayıları DEĞİŞEBİLİR. verify_delivery.config.json'daki
# expected_pages/expected_refs/expected_manifest değerleri bu sayılarla
# birebir eşleşmelidir (verify-delivery kapısı bunları denetler). Bu hook,
# gen_config.py ile config'i paketin GERÇEK içeriğinden yeniden hesaplar ve
# değiştiyse stage eder — böylece repack sonrası ilk commit'te config de
# otomatik güncellenir, verify kapısı yeşil kalır.
#
# Sıralama: .pre-commit-config.yaml'da verify-delivery'den ÖNCE tanımlıdır;
# böylece doğrulama kapısı her zaman güncel config'i görür.
#
# Mantık: önce --dry-run ile drift kontrolü. Drift YOKSA hiçbir şeye
# dokunmaz (gen_config yazma modu her zaman dosyayı yeniden yazar → byte
# farkı + gereksiz stage üretirdi). Yalnızca gerçek değer farkı varsa
# yazma modunda günceller ve stage eder.
#
# Exit kodları:
#   0 = drift yok (dokunmadı) VEYA drift güncellendi+stage edildi (commit devam)
#   1 = gen_config şema doğrulaması başarısız / beklenmedik hata (bloke)
#   2 = ortam eksik (pdfinfo/zip/tex) → UYARI ile geç; CI'daki config-drift
#       job'ı orada drift'i yakalar (verify-delivery hook'u da pdfinfo'yu
#       opsiyonel saydığından yerel makinede tutarlı davranış).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$ROOT/_calisma/CIKTI/verify_delivery.config.json"

# Önce DRY-RUN: değerler paket içeriğiyle eşleşiyor mu?
# gen_config --dry-run her zaman exit 0 döner ama DEĞERLER farklıysa exit 1.
# (Değer farkı yokken yazma moduna geçmeyiz — gen_config dosyayı yeniden
# yazar, byte-farkı üretir ve her commit'te gereksiz stage yaratırdı.)
set +e
python3 "$SCRIPT_DIR/gen_config.py" --dir "$ROOT/_calisma/CIKTI" --dry-run \
  >/dev/null 2>&1
rc=$?
set -e

case "$rc" in
  0)
    # Drift yok — config paket içeriğiyle güncel. Dokunma.
    exit 0
    ;;
  2)
    # Ortam eksik (pdfinfo/zip/tex) — verify hook'u gibi opsiyonel davran.
    # CI'daki config-drift job'ı drift'i orada yakalar (fail-closed korunur).
    echo "UYARI: gen_config ortam hatası (exit 2) — config güncellenemedi; CI config-drift kapısı denetler." >&2
    exit 0
    ;;
  1)
    # DRIFT: paket sayıları config'le uyuşmuyor → yazma modunda güncelle.
    python3 "$SCRIPT_DIR/gen_config.py" --dir "$ROOT/_calisma/CIKTI" \
      >/dev/null 2>&1 || {
      echo "HATA: gen_config yazma modunda başarısız — config güncellenemedi." >&2
      exit 1
    }
    git add "$CONFIG"
    echo "ℹ️ verify_delivery.config.json paket içeriğine göre güncellendi ve stage edildi."
    exit 0
    ;;
  *)
    echo "HATA: gen_config beklenmedik exit ($rc)." >&2
    exit 1
    ;;
esac
