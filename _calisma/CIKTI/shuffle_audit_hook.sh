#!/usr/bin/env bash
# =============================================================================
# shuffle_audit_hook.sh — shuffle-audit (shuffle_tests.py) kapısının sarmalayıcısı.
#
# TEK uygulama, iki bağlam:
#   * pre-commit (bayraksız): yalnız DEĞİŞEN test dosyaları. Amaç: yeni bir test
#     bir öncekinin bıraktığı duruma yaslanıyorsa commit anında yakalamak.
#   * CI / elle (--full): manifest kapsamı − shuffle_audit.exclude. Amaç:
#     tam ağaçta sıra bağımlılığı/sızıntı denetimi (bulgu JSON'u artifact).
#
# Ortam sözleşmesi (hepsi opsiyonel):
#   SHUFFLE_AUDIT_SEEDS      virgülle tohum listesi. Varsayılan: pre-commit "42",
#                            --full "42,7,13" (2026-09-18 turunun tohum kümesi).
#   SHUFFLE_AUDIT_BUDGET     duvar-saati bütçesi (s). Varsayılan: pre-commit 180,
#                            --full 2400. ÖLÇÜM (2026-10-18, bu ağaç): kapsam
#                            189 dosya × 4 geçiş = 756 koşum / 10.032 test;
#                            sakin makinede 536 s. Aynı kapsam EŞZAMANLI YÜK
#                            altında 1500 s'de 165 dosyada tükendi (24 dosya
#                            denetlenmedi → 'budget' bulgusu). 2400 s bu yükü ve
#                            daha yavaş runner'ı kapsar; bütçe güvencedir,
#                            hedef değil.
#                            Bütçe tükenmesi BULGUDUR (exit 1) — kırpılmış
#                            denetim "temiz" sayılmaz.
#   SHUFFLE_AUDIT_OUT        JSON sidecar yolu. Varsayılan logs/shuffle_audit.json
#                            (logs/ gitignored; CI bu dosyayı artifact yükler).
#   SHUFFLE_AUDIT_TIMEOUT    alt süreç tavanı (s), varsayılan 300.
#   SHUFFLE_AUDIT_MAX_FILES  pre-commit modunda değişen dosya tavanı (vars. 15).
#                            Tavan aşılırsa denetim SESSİZCE kırpılmaz: yüksek
#                            sesle ATLANDI der ve CI'ı işaret eder (0 test = PASS
#                            değildir; kırpılmış liste de öyle).
#
# Fail-closed ek kapı: koşumdan sonra JSON'daki `totals.tests` 0 ise exit 1.
# "0 test denetlendi" satırı kayıt eksikliğidir, temizlik kanıtı değildir.
#
# Exit: 0 = temiz · 1 = bulgu (sıra bağımlılığı/sızıntı/bütçe) veya okunamayan
#       JSON · 2 = kullanım/ortam hatası.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PY=python3
if [ -x "$ROOT/_calisma/.venv_z3/bin/python" ]; then
    PY="$ROOT/_calisma/.venv_z3/bin/python"
fi

MODE="changed"
FILES=()
for arg in "$@"; do
    case "$arg" in
        --full) MODE="full" ;;
        *) FILES+=("$arg") ;;
    esac
done

if [ "$MODE" = "full" ]; then
    SEEDS="${SHUFFLE_AUDIT_SEEDS:-42,7,13}"
    BUDGET="${SHUFFLE_AUDIT_BUDGET:-2400}"
else
    SEEDS="${SHUFFLE_AUDIT_SEEDS:-42}"
    BUDGET="${SHUFFLE_AUDIT_BUDGET:-180}"
fi
OUT="${SHUFFLE_AUDIT_OUT:-$ROOT/logs/shuffle_audit.json}"
TIMEOUT="${SHUFFLE_AUDIT_TIMEOUT:-300}"
MAX_FILES="${SHUFFLE_AUDIT_MAX_FILES:-15}"

ARGS=()
# Tohum listesi: virgül/boşluk ayrımlı → tekrarlı --seed (tek kaynak: tool CLI).
IFS=', ' read -r -a SEED_LIST <<< "$SEEDS"
for seed in "${SEED_LIST[@]}"; do
    [ -n "$seed" ] && ARGS+=(--seed "$seed")
done
ARGS+=(--budget "$BUDGET" --timeout "$TIMEOUT" --json "$OUT")

if [ "$MODE" = "full" ]; then
    ARGS+=(--scope manifest --exclude-from "$SCRIPT_DIR/shuffle_audit.exclude")
else
    # Yalnız test dosyaları; diğerlerini ayıkla (sessiz kapsam kaybı yok:
    # ayıklanan ad varsa yazılır).
    KEPT=()
    for f in "${FILES[@]:-}"; do
        [ -z "$f" ] && continue
        case "$(basename "$f")" in
            test_*.py) KEPT+=("$f") ;;
            *) echo "shuffle-audit: atlandı (test dosyası değil): $f" ;;
        esac
    done
    if [ "${#KEPT[@]}" -eq 0 ]; then
        echo "shuffle-audit: değişen test dosyası yok — atlandı."\
             "(Bu bir PASS değil; tam kapsam CI 'shuffle-audit' job'unda koşar.)"
        exit 0
    fi
    if [ "${#KEPT[@]}" -gt "$MAX_FILES" ]; then
        echo "shuffle-audit: ATLANDI — ${#KEPT[@]} değişen test dosyası >"\
             "$MAX_FILES (SHUFFLE_AUDIT_MAX_FILES). Kırpılmış liste PASS değildir;"\
             "tam denetim CI 'shuffle-audit' job'unda koşar."
        exit 0
    fi
    ARGS+=(--tests "${KEPT[@]}")
fi

mkdir -p "$(dirname "$OUT")"
set +e
"$PY" "$SCRIPT_DIR/shuffle_tests.py" "${ARGS[@]}"
RC=$?
set -e

# Fail-closed: 0 test denetlendi = kayıt/keşif hatası (sahte PASS yok).
TESTS=$("$PY" - "$OUT" <<'PY' || true
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    sys.exit(2)
print((data.get("totals") or {}).get("tests", 0))
PY
) || {
    echo "shuffle-audit: HATA — bulgu JSON okunamadı: $OUT" >&2
    exit 1
}
if [ "${TESTS:-0}" -eq 0 ]; then
    echo "shuffle-audit: HATA — 0 test denetlendi ($OUT, rc=$RC); sahte PASS yok." >&2
    # Araç zaten kullanım/ortam hatası verdiyse (rc=2) onu KORU: yoksa
    # "0 test" kuralı exit 2'yi 1'e düşürür ve kullanım hatası bulgu gibi
    # raporlanır. rc=0 + 0 test ASIL sahte-PASS vakasıdır → 1.
    if [ "$RC" -ne 0 ]; then
        exit "$RC"
    fi
    exit 1
fi

echo "shuffle-audit: $TESTS test denetlendi · bulgu JSON: $OUT (rc=$RC)"
exit "$RC"
