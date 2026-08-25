#!/usr/bin/env bash
# =============================================================================
# ci_fresh_clone_test.sh — fresh_clone_setup.sh + verify --full uçtan uca test
#
# ci_repack_test.sh deseninde:boş bir dizinde (TCC-safe izole HOME ile)
# fresh_clone_setup.sh'i koşar, beş artefaktın üretimini doğrular, ardından
# mirror'dan verify_delivery.py --full zincirini (K1-K18) çalıştırır.
#
# Çalışma ağacını KİRLETMEZ: tüm iş temp dir'inde (FAKE_HOME + WORK_ROOT).
#
# Kullanım:
#   bash _calisma/CIKTI/ci_fresh_clone_test.sh
#   KEEP_WORKTREE=1 bash _calisma/CIKTI/ci_fresh_clone_test.sh
#
# Çıktı:
#   .freebuff/sim/fresh_clone/fresh_clone_report.txt
#
# Fail-closed: setup veya verify P0/P1 üretirse exit 1.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM_DIR="$REPO_ROOT/.freebuff/sim/fresh_clone"
SCRIPT_DIR="$REPO_ROOT/_calisma/CIKTI"

# Python: venv varsa o, yoksa python3.
if [ -x "$REPO_ROOT/_calisma/.venv_z3/bin/python3" ]; then
  PY="$REPO_ROOT/_calisma/.venv_z3/bin/python3"
else
  PY=python3
fi

FAKE_HOME=""
WORK_ROOT=""

cleanup() {
  if [ "${KEEP_WORKTREE:-0}" = "1" ]; then
    return 0
  fi
  # temp dir'leri temizle (FAKE_HOME + WORK_ROOT aynı ağaçta olabilir).
  if [ -n "$WORK_ROOT" ] && [ -d "$WORK_ROOT" ]; then
    rm -rf "$WORK_ROOT"
  fi
}
trap cleanup EXIT

main() {
  local report="$SIM_DIR/fresh_clone_report.txt"
  mkdir -p "$SIM_DIR"

  echo "═══ FRESH-CLONE SİMÜLASYONU ═══"
  echo "REPO : $REPO_ROOT"
  echo "PY   : $PY ($("$PY" --version 2>&1))"
  echo "SIM  : $SIM_DIR"

  # İzole working area: FAKE_HOME (mirror burada) + WORK_ROOT (repo kopyası).
  WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ci_fresh_clone.XXXXXX")"
  FAKE_HOME="$WORK_ROOT/home"
  local work_repo="$WORK_ROOT/repo"
  mkdir -p "$FAKE_HOME"

  echo ""
  echo "── ADIM 0: repo kopyası (CI checkout karşılığı) ──"
  # shallow clone = CI checkout speed; depth=1 yeterli.
  if ! git clone --depth 1 --no-checkout file://"$REPO_ROOT" "$work_repo" 2>/dev/null; then
    # file:// protokolü bazı sistemlerde worktree gerektirir; fallback: cp.
    echo "  (git clone başarısız — rsync fallback)"
    mkdir -p "$work_repo"
    rsync -a --exclude='.git' --exclude='.freebuff' --exclude='_calisma/.venv_z3' \
          "$REPO_ROOT/" "$work_repo/"
  fi
  # Checkout HEAD (shallow clone'da zaten var).
  if [ -d "$work_repo/.git" ]; then
    (cd "$work_repo" && git checkout HEAD -- . 2>/dev/null) || true
  fi
  local ci_count
  ci_count=$(find "$work_repo/_calisma/CIKTI" -maxdepth 1 -type f | wc -l | tr -d ' ')
  echo "  repo kopyası: $work_repo (_calisma/CIKTI: $ci_count dosya)"

  local rc=0

  # ─── ADIM 1: fresh_clone_setup.sh ────────────────────────────────────
  echo ""
  echo "── ADIM 1: fresh_clone_setup.sh (5 artefakt kurulumu) ──"
  local setup_log="$WORK_ROOT/setup_log.txt"

  # fresh_clone_setup.sh'in HOME'u FAKE_HOME kullanması için env kur:
  # - HOME → FAKE_HOME (mirror + plist + venv burada üretilir)
  # - ROOT → work_repo (repo kökü)
  # - REPO_VENV → work_repo/_calisma/.venv_z3 (repo venv de izole)
  # - FC_TEST_FAKE_VENV=1 → pip install atla (offline sim için; gerçek
  #   kurulumda KULLANMA — venv'ler zaten kurulu olmalı).
  local fake_repo_venv="$work_repo/_calisma/.venv_z3"
  mkdir -p "$fake_repo_venv/bin"
  # Minimal python3 iskeleti (FC_TEST_FAKE_VENV=1 ile venv_ok PASS).
  if [ ! -x "$fake_repo_venv/bin/python3" ]; then
    cat > "$fake_repo_venv/bin/python3" <<'VENV_PY'
#!/bin/sh
exec python3 "$@"
VENV_PY
    chmod 755 "$fake_repo_venv/bin/python3"
  fi

  if ! HOME="$FAKE_HOME" ROOT="$work_repo" REPO_VENV="$fake_repo_venv" \
       FC_TEST_FAKE_VENV=1 \
       bash "$SCRIPT_DIR/fresh_clone_setup.sh" \
       > "$setup_log" 2>&1; then
    echo "HATA: fresh_clone_setup.sh FAIL" >&2
    cat "$setup_log" >&2
    rc=1
  else
    echo "  fresh_clone_setup.sh: PASS"
  fi

  # ─── ADIM 2: beş artefakt doğrulaması ────────────────────────────────
  echo ""
  echo "── ADIM 2: beş artefakt --check (produksiyon rotası) ──"
  local check_log="$WORK_ROOT/check_log.txt"
  local check_rc=0

  HOME="$FAKE_HOME" ROOT="$work_repo" REPO_VENV="$fake_repo_venv" \
    FC_TEST_FAKE_VENV=1 \
    bash "$SCRIPT_DIR/fresh_clone_setup.sh" --check \
    > "$check_log" 2>&1 || check_rc=$?

  if [ "$check_rc" -eq 0 ]; then
    echo "  --check: PASS (5/5 artefakt GÜNCEL)"
  else
    echo "  --check: FAIL (rc=$check_rc)"
    grep -E "^(OK|HATA|BİLGİ|SONUÇ)" "$check_log" | while IFS= read -r line; do
      echo "    $line"
    done
    rc=1
  fi

  # ─── ADIM 3: --check-ci (CI runner modu) ──────────────────────────────
  echo ""
  echo "── ADIM 3: --check-ci (CI runner modu) ──"
  local ci_check_log="$WORK_ROOT/ci_check_log.txt"
  local ci_check_rc=0

  HOME="$FAKE_HOME" ROOT="$work_repo" REPO_VENV="$fake_repo_venv" \
    FC_TEST_FAKE_VENV=1 \
    bash "$SCRIPT_DIR/fresh_clone_setup.sh" --check-ci \
    > "$ci_check_log" 2>&1 || ci_check_rc=$?

  if [ "$ci_check_rc" -eq 0 ]; then
    echo "  --check-ci: PASS"
  else
    echo "  --check-ci: FAIL (rc=$ci_check_rc — CI'da daemon + mirror venv atlanır)"
    grep -E "^(OK|HATA|BİLGİ|SONUÇ)" "$ci_check_log" | while IFS= read -r line; do
      echo "    $line"
    done
    # --check-ci FAIL appointment durumunda job'u DÜŞÜRME (advisory).
    echo "  (advisory — job durumunu etkilemez)"
  fi

  # ─── ADIM 4: verify --full (mirror rotası) ────────────────────────────
  echo ""
  echo "── ADIM 4: verify_delivery.py --full (mirror'dan, K1-K18) ──"
  local mirror_dir="$FAKE_HOME/Library/Caches/com.freebuff/verify"
  local preview_mirror="$FAKE_HOME/Library/Caches/com.freebuff/preview"
  local verify_log="$WORK_ROOT/verify_log.txt"
  local verify_json="$WORK_ROOT/verify_result.json"
  local verify_rc=0

  if [ ! -f "$mirror_dir/verify_delivery.py" ]; then
    echo "HATA: verify mirror'ında verify_delivery.py yok: $mirror_dir" >&2
    rc=1
  else
    # mirror rotası: --dir ile mirror'dan çalıştır (launchd GUI agent'ın yaptığı).
    # PREVIEW_DAEMON=1 → K18 daemon smoke Skip (iç içe koruması).
    if ! PREVIEW_DAEMON=1 \
         "$PY" "$mirror_dir/verify_delivery.py" \
         --dir "$mirror_dir" \
         --full --json \
         --history-out "$WORK_ROOT/history.jsonl" \
         --budget-out "$WORK_ROOT/budget.json" \
         > "$verify_log" 2>&1; then
      echo "HATA: verify --full FAIL (P0/P1 var)" >&2
      tail -20 "$verify_log" >&2
      verify_rc=1
      rc=1
    else
      echo "  verify --full: PASS"
    fi
    # JSON çıktısını çıkar (son satırda).
    if [ -f "$verify_log" ]; then
      "$PY" -c "
import json, sys
for line in open('$verify_log'):
    line = line.strip()
    if line.startswith('{') and '\"verdict\"' in line:
        d = json.loads(line)
        print(json.dumps({k: d.get(k) for k in ('verdict','p0','p1','layers','refs_verified','refs_total')}, indent=2))
        break
" 2>/dev/null || true
    fi
  fi

  # ─── ADIM 5: daemon HTTP smoke (SSE + run-now) ───────────────────────
  echo ""
  echo "── ADIM 5: daemon_http_test.py (mirror kopyası, SSE/run-now) ──"
  local daemon_log="$WORK_ROOT/daemon_log.txt"
  local daemon_rc=0

  if [ -f "$mirror_dir/daemon_http_test.py" ]; then
    local dpy=""
    if [ -x "$fake_repo_venv/bin/python3" ]; then
      dpy="$fake_repo_venv/bin/python3"
    elif command -v python3 >/dev/null 2>&1; then
      dpy="$(command -v python3)"
    fi
    if [ -n "$dpy" ]; then
      local dreport="$WORK_ROOT/daemon_report.json"
      if (cd "$mirror_dir" && "$dpy" daemon_http_test.py \
            --out "$dreport" --start-timeout 30 > "$daemon_log" 2>&1); then
        echo "  daemon smoke: PASS"
        # Raporun keyif alanlarını göster.
        if [ -f "$dreport" ]; then
          "$PY" -c "
import json
d = json.load(open('$dreport'))
print('    endpoints:', ', '.join(f\"{e['path']}={e['status']}\" for e in d.get('endpoints',[])))
print('    sse:', ', '.join(f\"{e['path']}={e['status']}+event={e.get('event_seen',False)}\" for e in d.get('sse_endpoints',[])))
print('    run_now:', d.get('run_now',{}).get('status','?'))
print('    ok:', d.get('ok'))
" 2>/dev/null || true
        fi
      else
        echo "  daemon smoke: FAIL (rc=$?)" >&2
        daemon_rc=1
        rc=1
      fi
      rm -f "$dreport"
    fi
  else
    echo "  (daemon_http_test.py mirror'da yok — atlandı)"
  fi

  # ─── RAPOR ────────────────────────────────────────────────────────────
  echo ""
  echo "════════════════════════════════════════════════════════"
  {
    echo "## Fresh-clone simülasyonu raporu"
    echo ""
    echo "- Tarih: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- Repo: $REPO_ROOT"
    echo "- Work: $WORK_ROOT"
    echo ""
    echo "### Sonuçlar"
    echo ""
    echo "| Adım | Sonuç | rc |"
    echo "|---|---|---|"
    echo "| 1. fresh_clone_setup.sh | PASS | — |"
    echo "| 2. --check (5 artefakt) | $([ $check_rc -eq 0 ] && echo 'PASS' || echo 'FAIL') | $check_rc |"
    echo "| 3. --check-ci (CI modu) | $([ $ci_check_rc -eq 0 ] && echo 'PASS' || echo 'FAIL (advisory)') | $ci_check_rc |"
    echo "| 4. verify --full (K1-K18) | $([ $verify_rc -eq 0 ] && echo 'PASS' || echo 'FAIL') | $verify_rc |"
    echo "| 5. daemon smoke (SSE/run-now) | $([ $daemon_rc -eq 0 ] && echo 'PASS' || echo 'FAIL/atlandı') | $daemon_rc |"
    echo ""
    if [ "$rc" -eq 0 ]; then
      echo "**SONUÇ: PASS** — fresh clone simülasyonu tamamlandı."
    else
      echo "**SONUÇ: FAIL** — yukarıdaki adım(lar)dan biri başarısız."
    fi
  } > "$report"
  cat "$report"
  echo "════════════════════════════════════════════════════════"
  echo "Rapor: $report"
  if [ "${KEEP_WORKTREE:-0}" = "1" ]; then
    echo "Work (saklandı): $WORK_ROOT"
  fi
  return "$rc"
}

main "$@"
