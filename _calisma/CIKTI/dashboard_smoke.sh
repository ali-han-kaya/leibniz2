#!/usr/bin/env bash
# =============================================================================
# dashboard_smoke.sh — canlı dashboard PASS'ini TEK KOMUTTA tekrarlanabilir kılar.
#
# launchd GUI agent rotasının (preview_server.py --dir <verify-mirror>) birebir
# yerel karşılığı — fresh_clone_setup.sh 3+4. adımının minimal karşılığı:
#
#   1. sync_verify_mirror.sh ile TCC-safe mirror'ı repo ile senkronla (K17
#      ön-koşulu: mirror bayatsa dashboard zaten FAIL üretir).
#   2. MİNİMAL PATH'te (launchd GUI agent PATH'i: /usr/bin:/bin:/usr/sbin:/sbin)
#      verify_delivery.py --dir <mirror> --full --json koş. Homebrew araçları
#      (node, pdfinfo, qpdf, lean, lake) PATH'te YOK — K16/K6 fallback'leri
#      (/opt/homebrew/bin, ~/.elan/bin) bu ortamda gerçekten devreye girmeli.
#   3. JSON verdict == "PASS" ve counts P0=0/P1=0 doğrula → exit 0/1.
#
# Exit: 0 = PASS (dashboard yeşil), 1 = FAIL (verdict, bulgu veya senkron hatası).
# Rapor + ham JSON gitignored sim dizinine yazılır:
#   <repo>/.freebuff/sim/dashboard_smoke/dashboard_smoke_report.txt
#   <repo>/.freebuff/sim/dashboard_smoke/verify.json
#
# Env override'ları (test/CI için):
#   ROOT             repo kökü (varsayılan: script'in ../../)
#   MIRROR_DIR       verify mirror (sync_verify_mirror.sh'e geçer)
#   PREVIEW_MIRROR   preview mirror (sync_verify_mirror.sh'e geçer)
#   LEAN_MIRROR_DIR  lean mirror (sync_verify_mirror.sh'e geçer)
#   MINIMAL_PATH     minimal PATH (varsayılan: /usr/bin:/bin:/usr/sbin:/sbin)
#   PY               verify'yi koşacak python (varsayılan: _find_python
#                    önceliği — mirror venv → repo venv → python3)
#   SMOKE_SYNC=0     TEST-ONLY: senkron adımını atla (stub mirror kullanır;
#                    gerçek kurulumda KULLANMA)
#   VERIFY_EXTRA     verify'ye eklenecek ek bayraklar (boşlukla ayrılmış)
#   SIM_DIR          rapor dizini (varsayılan: <repo>/.freebuff/sim/dashboard_smoke)
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CIKTI="$ROOT/_calisma/CIKTI"
SIM_DIR="${SIM_DIR:-$ROOT/.freebuff/sim/dashboard_smoke}"
MINIMAL_PATH="${MINIMAL_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"

say() { printf '%s\n' "$*"; }
err() { printf 'HATA: %s\n' "$*" >&2; }

# Python çözümü — preview_server.py _find_python önceliğiyle birebir:
#   1. TCC-safe mirror venv    (~/Library/Caches/com.freebuff/venv_z3/bin/python3)
#   2. repo venv               (_calisma/.venv_z3/bin/python3)
#   3. repo venv fallback      (_calisma/.venv/bin/python3)
#   4. system python3
resolve_python() {
  if [ -n "${PY:-}" ]; then printf '%s' "$PY"; return 0; fi
  local mirror_venv="$HOME/Library/Caches/com.freebuff/venv_z3/bin/python3"
  if [ -x "$mirror_venv" ]; then printf '%s' "$mirror_venv"; return 0; fi
  if [ -x "$ROOT/_calisma/.venv_z3/bin/python3" ]; then
    printf '%s' "$ROOT/_calisma/.venv_z3/bin/python3"; return 0
  fi
  if [ -x "$ROOT/_calisma/.venv/bin/python3" ]; then
    printf '%s' "$ROOT/_calisma/.venv/bin/python3"; return 0
  fi
  if command -v python3 >/dev/null 2>&1; then printf '%s' "$(command -v python3)"; return 0; fi
  return 1
}

PY="$(resolve_python)" || { err "python3 bulunamadı"; exit 1; }

# ── 1) Mirror senkron (SMOKE_SYNC=0 ise atlanır — test-only stub) ──────────
step_sync() {
  if [ "${SMOKE_SYNC:-1}" = "0" ]; then
    say "── ADIM 1: sync_verify_mirror.sh (SMOKE_SYNC=0 — atlandı, stub mirror)"
    return 0
  fi
  say "── ADIM 1: sync_verify_mirror.sh (adım 2+4 tek komut)"
  # macOS bash 3.2'de boş dizi "${arr[@]}" set -u ile unbound verir;
  # ${arr[@]+...} guard'ı boş diziyi yok sayar (yaygın uyumluluk deseni).
  local env_args=()
  [ -n "${MIRROR_DIR:-}" ]     && env_args+=(MIRROR_DIR="$MIRROR_DIR")
  [ -n "${PREVIEW_MIRROR:-}" ] && env_args+=(PREVIEW_MIRROR="$PREVIEW_MIRROR")
  [ -n "${LEAN_MIRROR_DIR:-}" ] && env_args+=(LEAN_MIRROR_DIR="$LEAN_MIRROR_DIR")
  if ! env "${env_args[@]+\"${env_args[@]}\"}" bash "$CIKTI/sync_verify_mirror.sh"; then
    err "mirror senkronu başarısız — dashboard PASS'i üretilemez (K17 ön-koşulu)"
    return 1
  fi
  return 0
}

# ── 2) Minimal PATH'te --full (launchd GUI agent ortamı) ───────────────────
# verify mirror konumu: sync env'den, yoksa varsayılan cache.
VERIFY_DIR="${MIRROR_DIR:-$HOME/Library/Caches/com.freebuff/verify}"

step_verify() {
  say "── ADIM 2: verify_delivery.py --full --json  (MINIMAL_PATH=$MINIMAL_PATH)"
  say "   python: $PY"
  say "   dir:    $VERIFY_DIR"
  mkdir -p "$SIM_DIR"
  # launchd GUI agent'ı /usr/bin:/bin:/usr/sbin:/sbin PATH'iyle çalışır;
  # verify'yi O ortamda koşarak node/pdfinfo/qpdf/lean/lake fallback'lerinin
  # gerçekten devreye girdiği kanıtlanır. PY mutlak yol olduğundan venv
  # minimal PATH'te de çalışır (z3 import dahil).
  local extra=""
  [ -n "${VERIFY_EXTRA:-}" ] && extra=" $VERIFY_EXTRA"
  # shellcheck disable=SC2086
  if ! (cd "$VERIFY_DIR" && \
        PATH="$MINIMAL_PATH" "$PY" "$VERIFY_DIR/verify_delivery.py" \
          --dir "$VERIFY_DIR" --full --json $extra \
        > "$SIM_DIR/verify.json" 2> "$SIM_DIR/verify.stderr"); then
    err "verify_delivery.py exit != 0 — çıktı: $SIM_DIR/verify.stderr"
    return 1
  fi
  return 0
}

# ── 3) Verdict + P0/P1 + K6/K16/K17 katman durumu doğrula ──────────────────
step_check() {
  say "── ADIM 3: verdict doğrulaması"
  local json="$SIM_DIR/verify.json"
  if [ ! -s "$json" ]; then
    err "verify.json boş/yok — verify çıktısı alınamadı"
    return 1
  fi
  # JSON'dan: verdict, P0, P1 ve (varsa) K6/K16/K17 katman durumları.
  local verdict p0 p1 k6 k16 k17
  verdict=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$json" 2>/dev/null || echo "PARSE_ERR")
  p0=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["P0"])' "$json" 2>/dev/null || echo "?")
  p1=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["P1"])' "$json" 2>/dev/null || echo "?")
  k6=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])).get("layers",{}); print(d.get("K6",{}).get("status","N/A"))' "$json" 2>/dev/null || echo "N/A")
  k16=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])).get("layers",{}); print(d.get("K16",{}).get("status","N/A"))' "$json" 2>/dev/null || echo "N/A")
  k17=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])).get("layers",{}); print(d.get("K17",{}).get("status","N/A"))' "$json" 2>/dev/null || echo "N/A")

  say "   verdict=$verdict  P0=$p0  P1=$p1"
  say "   katmanlar: K6(pdfinfo)=$k6  K16(node)=$k16  K17(mirror)=$k17"
  {
    echo "--- dashboard_smoke — $(date -u +%Y-%m-%dT%H:%M:%SZ) ---"
    echo "python: $PY"
    echo "dir:    $VERIFY_DIR"
    echo "PATH:   $MINIMAL_PATH"
    echo ""
    echo "verdict=$verdict  P0=$p0  P1=$p1"
    echo "katmanlar: K6(pdfinfo)=$k6  K16(node)=$k16  K17(mirror)=$k17"
  } > "$SIM_DIR/dashboard_smoke_report.txt"

  if [ "$verdict" = "PASS" ] && [ "$p0" = "0" ] && [ "$p1" = "0" ]; then
    echo "SONUÇ: PASS — dashboard yeşil (verdict=PASS, P0=0, P1=0, minimal PATH'te)"
    echo "SONUÇ: PASS" >> "$SIM_DIR/dashboard_smoke_report.txt"
    return 0
  fi
  echo "SONUÇ: FAIL — verdict=$verdict P0=$p0 P1=$p1 (beklenen PASS/0/0)"
  err "dashboard PASS'i üretilemedi (verdict=$verdict P0=$p0 P1=$p1)"
  echo "SONUÇ: FAIL" >> "$SIM_DIR/dashboard_smoke_report.txt"
  return 1
}

main() {
  step_sync || return 1
  step_verify || return 1
  step_check || return 1
}

main
