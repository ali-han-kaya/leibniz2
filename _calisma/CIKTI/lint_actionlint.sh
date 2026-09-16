#!/usr/bin/env bash
# lint_actionlint.sh — actionlint wrapper (pre-commit hook).
#
# actionlint çıkış kodları (v1.7.7, ölçülerek doğrulandı 2026-09-16):
#   0 = temiz → PASS
#   1 = lint bulgusu (shellcheck hint/info DAHİL — ayrı exit kodu yok) → FAIL
#   2/3 = runtime/fatal hata (dosya okunamadı, şablon hatası) → FAIL
#
# NOT: Eski "RC≤2 PASS (shellcheck info advisory)" sözleşmesi yanlış
# okumaya dayanıyordu — hint'ler RC=1 üretir, RC=2 fatal koddur. Fail-closed
# doğru kontrat: RC≠0 → FAIL. Hint görürsen ya düzelt ya da -ignore'u
# görünür şekilde kontrata ekle.
#
# TÜM .github/workflows/*.yml'ı (glob) denetler — yeni workflow dosyaları
# kapıya otomatik girer (verify.yml CI adımıyla aynı tek kaynak glob ve
# aynı kontrat).

set -euo pipefail

AL=/tmp/actionlint
if [ ! -x "$AL" ]; then
  OS=$(uname -s | tr 'A-Z' 'a-z')
  ARCH=$(uname -m | sed 's/x86_64/amd64/')
  curl -sL "https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_${OS}_${ARCH}.tar.gz" \
    | tar xz -C /tmp actionlint
fi

RC=0
for WF in .github/workflows/*.yml; do
  WF_RC=0
  "$AL" --color "$WF" 2>&1 || WF_RC=$?
  if [ "$WF_RC" -gt "$RC" ]; then RC=$WF_RC; fi
  echo "actionlint: $WF → RC=$WF_RC"
done

if [ "$RC" -eq 0 ]; then
  echo "actionlint: PASS — tüm workflow'lar temiz"
  exit 0
else
  echo "actionlint: FAIL (RC=$RC) — RC=1 lint bulgusu (shellcheck hint dahil),"
  echo "  RC≥2 runtime/fatal hata. Hint'leri kalıcı geçmek istersen -ignore'u"
  echo "  bu betikte VE CI adımında görünür şekilde kontratla."
  exit 1
fi
