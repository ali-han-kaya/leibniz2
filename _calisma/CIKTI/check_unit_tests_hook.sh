#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --check (fail-closed): manifest + HOOK_COVERAGE
#    drift'ini BLOKLAR — sessiz auto-fix YOK. Repo invariant'ı:
#    repo'da üç yazan hook vardır (update-config, check-changelog-sync,
#    check-skills-index); bu kapı okuma-hook'tur. Gecikmeli (lag-one) changelog yazımı bu kapıya değil,
#    check-changelog-sync'a aittir — tablo hash'le anahtarlıdır ve hash ancak
#    commit sonrası bilinir (bkz. update_changelog_hook.sh başlığı). Drift
#    varsa remedy gösterilir (sync --update) ve commit engellenir.
# 2) Manifest listesindeki her test dosyasını venv python'la koşar; herhangi
#    bir başarısızlık commit'i BLOKE EDER (fail-closed).
#
# Neden ayrı script? Eski yapıda `for t in <17 isim>` hardcoded listesi
# .pre-commit-config.yaml entry'sine gömülüydü; artık manifest tek kaynak.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$SCRIPT_DIR/check_unit_tests.list"

PY=python3
if [ -x "$ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$ROOT/_calisma/.venv_z3/bin/python"
fi

# 1) Senkron kapısı — fail-closed: drift commit'i bloklar (sessiz düzeltme yok).
if ! "$PY" "$SCRIPT_DIR/sync_check_unit_tests.py" --check >/dev/null; then
  echo "check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke." >&2
  echo "  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update" >&2
  exit 1
fi

# 2) Manifestten her test dosyasını koş — UZANTIYA GÖRE.
if [ ! -f "$MANIFEST" ]; then
  echo "HATA: check_unit_tests.list bulunamadı — sync çalıştırılamadı." >&2
  exit 1
fi

# Node yalnız `.js` girdisi varsa gerekli; yoksa hiç aranmaz (CI'da node
# kurulu değilken python-only koşu bozulmamalı).
NODE_BIN="${NODE:-$(command -v node 2>/dev/null || true)}"

fails=0
total=0
py_total=0
js_total=0
while IFS= read -r t; do
  [ -z "$t" ] && continue
  case "$t" in \#*) continue ;; esac
  total=$((total + 1))

  case "$t" in
    *.js)
      js_total=$((js_total + 1))
      # Bu dal YOKSA `.js` girdileri python yoluna düşer, pattern
      # "test_x.js.py" olur, 0 test eşleşir ve Python 3.9 "OK" deyip
      # sessizce hiçbir şey koşmadan geçerdi. Uzantı ayrımı bu yüzden zorunlu.
      if [ -z "$NODE_BIN" ]; then
        echo "FAILED: $t (node bulunamadı — .js testleri koşulamıyor)" >&2
        fails=$((fails + 1))
        continue
      fi
      if out="$("$NODE_BIN" "$SCRIPT_DIR/$t" 2>&1)"; then
        # Koştuğunu GÖSTER: pre-commit çıktısında kanıt görünsün.
        echo "  + node $t: $(printf '%s' "$out" | tail -n 1 | head -c 96)"
      else
        echo "FAILED: $t (node)" >&2
        printf '%s\n' "$out" | tail -n 6 >&2
        fails=$((fails + 1))
      fi
      ;;
    *.py)
      py_total=$((py_total + 1))
      # Pattern'e bir kez daha `.py` eklemek `test_X.py.py` üretir → 0 test
      # eşleşir. Python 3.12+ boş discovery'de exit 5 döndürdüğünden hook CI'da
      # 49/49 BAŞARISIZ olur; 3.9-3.11'de ise 0 testle "PASS" diye sessizce
      # hiçbir şey koşmazdı. Uzantıyı sıyırıp canonical `-p "$t.py"` kullanıyoruz.
      base="${t%.py}"
      if ! "$PY" -m unittest discover -s _calisma/CIKTI -p "$base.py" >/dev/null 2>&1; then
        echo "FAILED: $t" >&2
        fails=$((fails + 1))
      fi
      ;;
    *)
      echo "FAILED: $t (bilinmeyen uzantı — koşucu yok)" >&2
      fails=$((fails + 1))
      ;;
  esac
done < "$MANIFEST"

if [ "$fails" -gt 0 ]; then
  echo "check-unit-tests: $fails/$total test dosyası BAŞARISIZ — commit bloke." >&2
  exit 1
fi
echo "check-unit-tests: $total test dosyası PASS ($py_total python, $js_total node)."
exit 0
