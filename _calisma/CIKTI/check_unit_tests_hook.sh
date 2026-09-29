#!/usr/bin/env bash
# =============================================================================
# check_unit_tests_hook.sh — pre-commit check-unit-tests kapısının dış sarmalayıcısı.
#
# 1) sync_check_unit_tests.py --check (fail-closed): manifest + HOOK_COVERAGE
#    + glob-kapsam drift'ini BLOKLAR — sessiz auto-fix YOK. Repo invariant'ı:
#    yalnız update-config tek yazan hook'tur; bu kapı okuma-hook'tur.
# 2) Manifest listesindeki testleri koşar; herhangi bir başarısızlık commit'i
#    BLOKE EDER (fail-closed).
#
# ARTIRMLI KOŞUM (2026-09-29): adım 2 artık yalnız commit'in DOKUNDUĞU
# testleri koşar. Ölçülen boşluk: tam batarya 190 dosya / ~345-370 s idi ve
# bunun büyük kısmı dokunulmayan testlerdi. Seçim `select_affected_tests.py`
# ile yapılır; kapsam eşlemesi `test_coverage_report.py`'deki TEK kaynaktan
# gelir (türetilen import'lar ∪ bilinen kaynak glob'ları ∪ ALWAYS_RUN).
#
# FAIL-SAFE: seçim ÜRETİLEMEZSE tam batarya koşulur. Boş/hatalı seçim
# "0 test, commit geçti" olsaydı bu kapı tamamen işlevsiz hâle gelirdi;
# ölçülemeyen durumda geniş kapsam her zaman güvenli taraftır.
#
# Tam batarya hâlâ şu yollardan çalışır (sözleşmenin CI ayağı):
#   - pre-commit `pre-commit run check-unit-tests --all-files` → tüm dosyalar
#     "değişmiş" sayılır → seçim manifest'in TAMAMIDIR (testle sabitli).
#   - CI'ın fail-closed birim-test adımı doğrudan
#     `unittest discover -s _calisma/CIKTI -p "test_*.py"` koşar; bu yol bu
#     script'ten geçmez ve hiç değişmedi.
#   - `--full` bayrağı elle tam koşum verir.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$SCRIPT_DIR/check_unit_tests.list"
SELECTOR="$SCRIPT_DIR/select_affected_tests.py"

PY=python3
if [ -x "$ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$ROOT/_calisma/.venv_z3/bin/python"
fi

# 1) Senkron kapısı — fail-closed: drift commit'i bloklar (sessiz düzeltme yok).
# ⚠️ "manifest/HOOK_COVERAGE drift" ifadesi gh_run_rca.py'nin SINIFLANDIRMA
# imzasıdır (RULES[0]) — kelime kelime korunur, yoksa CI'da bu hata
# "bilinmeyen" diye sınıflanır. Ek kapsam notu sondan gelir.
# Senkron aracının çıktısı yutulmaz: `--update` yalnız manifest/HOOK_COVERAGE
# drift'ini çözer, glob-kapsam drift'ini ÇÖZMEZ — hangisi olduğunu söylemeden
# remedy göstermek yanlış yönlendirirdi.
if ! SYNC_OUT="$("$PY" "$SCRIPT_DIR/sync_check_unit_tests.py" --check 2>&1)"; then
    echo "check-unit-tests: manifest/HOOK_COVERAGE drift (veya glob-kapsam) — commit bloke." >&2
    printf '%s\n' "$SYNC_OUT" >&2
    echo "  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update" >&2
    exit 1
fi

# 2) Manifestten testleri koş.
if [ ! -f "$MANIFEST" ]; then
    echo "HATA: check_unit_tests.list bulunamadı — sync çalıştırılamadı." >&2
    exit 1
fi

# --- Seçim -------------------------------------------------------------------
# Bayraksız ve argümansız çağrı (elle koşum) daima tam bataryadır: "hiç
# dokunulmadı" demek, "hiç koşma" demek değildir.
FULL=0
CHANGED=()
for arg in "$@"; do
    case "$arg" in
        --full) FULL=1 ;;
        *) CHANGED+=("$arg") ;;
    esac
done

SELECTED=()
MODE="full"
if [ "$FULL" -eq 0 ] && [ "${#CHANGED[@]}" -gt 0 ]; then
    # Seçici kör kapı dönerse (rc≠0) seçim boş kalır → aşağıdaki kontrol
    # tam bataryaya düşer. `set -e` yüzünden rc'yi yutmamak için `|| true`.
    #
    # ⚠️ Burada `mapfile` KULLANILAMAZ: macOS'un /bin/bash'i 3.2'dir ve
    # `mapfile` bash 4 builtin'idır. 3.2'de "mapfile: command not found"
    # → seçim BOŞ kalır → fail-safe tam bataryaya düşer. Yani hata sessiz
    # ama pahalıdır: kapı çalışıyor görünür, artımlı hiç çalışmaz.
    # `$(...)` + here-string 3.2'de de çalışır ve diziyi korur.
    if SELECTED_RAW="$("$PY" "$SELECTOR" "${CHANGED[@]}" 2>/dev/null || true)" \
       && [ -n "$SELECTED_RAW" ]; then
        while IFS= read -r _t; do
            if [ -n "$_t" ]; then
                SELECTED+=("$_t")
            fi
        done <<< "$SELECTED_RAW"
    fi
    if [ "${#SELECTED[@]}" -gt 0 ]; then
        MODE="incremental"
    else
        SELECTED=()
    fi
fi

TOTAL=$(grep -vc -e '^#' -e '^[[:space:]]*$' "$MANIFEST" || true)
if [ "$MODE" = "incremental" ]; then
    echo "check-unit-tests: ${#SELECTED[@]}/$TOTAL test (artımlı — ${#CHANGED[@]} değişen dosya)."
else
    SELECTED=()
    while IFS= read -r t; do
        [ -z "$t" ] && continue
        case "$t" in \#*) continue ;; esac
        SELECTED+=("$t")
    done < "$MANIFEST"
    echo "check-unit-tests: tam batarya ($TOTAL test) — artımlı seçim yok."
fi

fails=0
total=0
for t in "${SELECTED[@]}"; do
    [ -z "$t" ] && continue
    total=$((total + 1))
    # Manifest girdileri `.py` uzantılıdır; pattern'e bir kez daha `.py`
    # eklemek `test_X.py.py` üretir → 0 test eşleşir. Python 3.12+ boş
    # discovery'de exit 5 döndürdüğünden hook CI'da 49/49 BAŞARISIZ olur;
    # 3.9-3.11'de ise 0 testle "PASS" diye sessizce hiçbir şey koşmazdı.
    # Uzantıyı sıyırıp canonical `-p "$t.py"` pattern'ini kullanıyoruz.
    t="${t%.py}"
    if ! "$PY" -m unittest discover -s _calisma/CIKTI -p "$t.py" >/dev/null 2>&1; then
        echo "FAILED: $t" >&2
        fails=$((fails + 1))
    fi
done

if [ "$fails" -gt 0 ]; then
    echo "check-unit-tests: $fails/$total test dosyası BAŞARISIZ — commit bloke." >&2
    exit 1
fi
echo "check-unit-tests: $total test dosyası PASS."
exit 0
