#!/usr/bin/env bash
#
# publish_wrapper.sh — docs/PUBLISH_SCENARIO.md'yi TEK KOMUTLA, interaktif
# olmadan çalıştırır ve tüm çıktıyı loglar.
#
# Kullanım:
#   ./docs/publish_wrapper.sh                 # AŞAMA 0-3 (ana publish akışı)
#   ./docs/publish_wrapper.sh --with-stage4   # AŞAMA 0-4 (opsiyonel koruma testi)
#   ./docs/publish_wrapper.sh --dry-run       # GÜVENLİ PROVA: repo oluşturma,
#                                             # push, PR gibi kalıcı komutlar
#                                             # ÇALIŞTIRILMAZ; akış önizlenir
#   ./docs/publish_wrapper.sh --dry-run --with-stage4
#   ./docs/publish_wrapper.sh --dry-run-summary
#                           # = --dry-run + komut akışını tek markdown dosyasına
#                           #   özetle (logs/PUBLISH_DRY_RUN_SUMMARY.md)
#   ./docs/publish_wrapper.sh --verify-checks # YALNIZCA AŞAMA 1 doğrulaması:
#                                             # status_checks.py + --gh (workflow
#                                             # ↔ GitHub eşleşmesi + merge engeli
#                                             # smoke). Repo oluşturma/push/CI
#                                             # izleme ÇALIŞTIRILMAZ. --dry-run ile
#                                             # birleşince önizleme modunda koşar.
#                                             # Sonuç JSON sidecar'ına yazılır
#                                             # (logs/verify_checks.json; --verify-
#                                             # checks-out FILE ile değiştirilir).
#   ./docs/publish_wrapper.sh --incremental   # INCREMENTAL PUSH döngüsü (repo
#                                             # zaten canlı): precheck → push →
#                                             # CI izle → durum + status_checks
#                                             # --gh. Repo oluşturma/remote ekleme
#                                             # atlanır; enforce_admins push için
#                                             # geçici kapatılıp sonra geri açılır.
#
# DRY-RUN: her kalıcı komut "[DRY-RUN] çalıştırılacak: ..." olarak basılır;
# AŞAMA 0 precheck --skip-smoke --allow-remote ile koşar (fail olsa bile akış
# önizlenmeye devam eder — hiçbir yan etki yoktur). Çıkış 0 (önizleme).
#
# Log: logs/publish_<timestamp>.log  (hem stdout'a hem dosyaya yazılır).
#
# İDEMPOTENT RE-RUN (repo zaten yayındaysa):
#   - AŞAMA 0: origin varsa --allow-remote ile koşar (ilk publish'te düz koşar).
#   - AŞAMA 1: repo zaten varsa oluşturma atlanır.
#   - AŞAMA 2: origin eşleşiyorsa dokunulmaz; bekleyen commit yoksa push atlanır.
#   - AŞAMA 1: repo oluşturma/varolma sonrası status_checks.py otomatik koşar
#     (required check adları workflow'dan türetilir + --gh ile GitHub eşleşmesi).
#   - AŞAMA 3: push yoksa HEAD için MEVCUT run'ı izler (yeni run yoksa atlar).
#   - --incremental: yukarıdaki INCREMENTAL PUSH döngüsünün TEK KOMUT hali —
#     precheck → push → CI izle → durum + status_checks --gh; repo oluşturma /
#     remote ekleme atlanır (repo canlı olmalı); enforce_admins geçici kapatılıp
#     push sonrası geri açılır (manüel dansın otomatik karşılığı).
#
# GÜVENLİK:
#   - AŞAMA 0 kapıları (repo temiz, gh auth, remote yok, branch main) başarısız
#     olursa senaryo DURUR; `git push` yalnızca tüm kapılar yeşilse çalışır.
#   - Bu script'i çalıştırmak = publish senaryosunu onaylamak demektir
#     (GitHub'da PUBLIC repo oluşturur + push eder).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REPO_NAME="leibniz2"
DESCRIPTION="Stoic-Hume V5 — fail-closed academic delivery with Z3 + Lean 4 proofs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$REPO_ROOT/logs"
LOG="$LOG_DIR/publish_${TIMESTAMP}.log"
SUMMARY_MD="$LOG_DIR/PUBLISH_DRY_RUN_SUMMARY.md"

WITH_STAGE4=0
DRY_RUN=0
DRY_RUN_SUMMARY=0
CI_SIMULATE=0
VERIFY_CHECKS=0
VERIFY_CHECKS_OUT=""
INCREMENTAL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --with-stage4)     WITH_STAGE4=1; shift ;;
    --dry-run)         DRY_RUN=1; shift ;;
    --dry-run-summary) DRY_RUN=1; DRY_RUN_SUMMARY=1; shift ;;
    --ci-simulate)     CI_SIMULATE=1; shift ;;
    --verify-checks)   VERIFY_CHECKS=1; shift ;;
    --verify-checks-out)
        [ $# -ge 2 ] || { echo "--verify-checks-out FILE gerekli" >&2; exit 2; }
        VERIFY_CHECKS_OUT="$2"; shift 2 ;;
    --incremental)     INCREMENTAL=1; shift ;;
    *) echo "Bilinmeyen bayrak: $1 (geçerli: --with-stage4, --dry-run, --dry-run-summary, --ci-simulate, --verify-checks, --verify-checks-out FILE, --incremental)" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"

# Tüm stdout + stderr'i hem terminale hem log dosyasına yaz.
exec > >(tee -a "$LOG") 2>&1

log()  { echo "[$(date +%H:%M:%S)] $*"; }
warn() { log "UYARI: $*"; }
fail() { log "HATA: $*"; log "SONUÇ: FAIL — log: $LOG"; exit 1; }
step() { echo ""; log "===== $* ====="; }

# DRY-RUN'da komut ÇALIŞTIRILMAZ, yalnızca önizlenir (kalıcı etkisi yok).
run() {
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] çalıştırılacak: $*"
    return 0
  fi
  "$@"
}

# DRY-RUN dışında tamamlanma mesajı basar (önizlemede yalnızca run() yeter).
done_msg() { [ "$DRY_RUN" = "1" ] || log "$*"; }

# ── AŞAMA 1 doğrulaması — status_checks.py --gh (workflow ↔ GitHub eşleşmesi) ──
# TEK KAYNAK: workflow job `name:`'leri. Hem normal akış (AŞAMA 1) hem de
# bağımsız --verify-checks modu bu fonksiyonu çağırır (tek tanım, drift yok).
# Branch protection henüz kurulu değilse --gh UYARI basar (web UI'dan kurulur)
# — bu bir hata değil, "kapı henüz yok" demektir. Gerçek drift (eksik/fazla
# check) FAIL eder (fail-closed).
# verify_checks() TEK KAYNAK: _calisma/CIKTI/verify_checks.sh — precheck
# --verify-checks ile AYNI fonksiyon (iki giriş noktası arasında drift yok).
# log/warn/fail/DRY_RUN/REPO_NAME bu scriptte tanımlıdır; library eksikse
# yerel fallback kurar (test/sourcing güvenliği). Branch protection kurulu
# değilse UYARI basar ("kapı henüz yok" — hata değil); gerçek drift
# (eksik/fazla check) fail-closed FAIL eder.
# shellcheck source=/dev/null
source _calisma/CIKTI/verify_checks.sh

# ── enforce_admins dansı — doğrudan main push'u (admin) bloke edilmemeli ──
# enforce_admins=true iken GitHub, korumalı branch'e doğrudan push'u ADMIN dahil
# bloke eder. INCREMENTAL döngünün "push" adımı bu yüzden geçici kapatma → push
# → geri açma gerektirir. GET → modify → PUT: mevcut ayarlar korunur, yalnızca
# enforce_admins değişir. Koruma yoksa (ilk publish) 404 → dokunulmaz.
enforce_is_on() {
  # Koruma varsa ve enforce_admins=true ise 0 döner; yoksa/yanlışsa 1.
  gh api "repos/$OWNER/$REPO_NAME/branches/main/protection" \
    --jq '.enforce_admins.enabled' 2>/dev/null | grep -qx true || return 1
}

toggle_enforce() { # $1: "true"|"false" — mevcut koruma ayarlarını koruyarak tek alanı değiştirir
  local want="$1" tmp
  tmp="/tmp/pw_prot_$(date +%s%N).json"
  gh api "repos/$OWNER/$REPO_NAME/branches/main/protection" > "$tmp" || return 1
  local py="${SC_PY:-python3}"
  "$py" - "$want" "$tmp" <<'PY' || { rm -f "$tmp"; return 1; }
import json, os, subprocess, sys

def _bool(x):
    """GET yanıtı {enabled: bool} veya düz bool olabilir — PUT bool ister."""
    return bool(x.get("enabled")) if isinstance(x, dict) else bool(x)

want, tmp = sys.argv[1], sys.argv[2]
p = json.load(open(tmp))

# GET şeması ≠ PUT şeması: required_status_checks GET'te checks[]+contexts_url
# döner; PUT yalnızca strict + contexts (string listesi) kabul eder.
rsc = p.get("required_status_checks")
if rsc is None:
    rsc_body = None
else:
    ctx = [c.get("context") if isinstance(c, dict) else c
           for c in (rsc.get("contexts") or [])]
    rsc_body = {"strict": bool(rsc.get("strict", False)), "contexts": ctx}

rpr = p.get("required_pull_request_reviews")
if isinstance(rpr, dict):
    dr = rpr.get("dismissal_restrictions") or {}
    rpr_body = {
        "dismiss_stale_reviews": bool(rpr.get("dismiss_stale_reviews", False)),
        "require_code_owner_reviews": bool(rpr.get("require_code_owner_reviews", False)),
        "required_approving_review_count": int(rpr.get("required_approving_review_count", 1)),
        "dismissal_restrictions": {
            "users": [u.get("login") for u in (dr.get("users") or [])],
            "teams": [t.get("slug") for t in (dr.get("teams") or [])],
        } if dr else {},
    }
else:
    rpr_body = None

body = {
    "required_status_checks": rsc_body,
    "enforce_admins": want == "true",
    "required_pull_request_reviews": rpr_body,
    "restrictions": p.get("restrictions"),
    "allow_force_pushes": _bool(p.get("allow_force_pushes")),
    "allow_deletions": _bool(p.get("allow_deletions")),
}
repo = os.environ.get("PW_REPO", "") or (p.get("url", "").split("/repos/")[1].split("/branches")[0] if "/repos/" in p.get("url", "") else "")
r = subprocess.run(["gh", "api", "--method", "PUT",
                    f"repos/{repo}/branches/main/protection",
                    "--input", "-"],
                   input=json.dumps(body), capture_output=True, text=True)
if r.returncode != 0:
    sys.stderr.write(r.stderr)
    sys.exit(1)
PY
  rm -f "$tmp"
}

# --dry-run-summary: dry-run komut akışını TEK markdown dosyasında özetle.
# AŞAMA başlıkları + [DRY-RUN] komut önizlemeleri yapılandırılmış liste olur;
# tam çıktı da denetim için fenced blokta saklanır.
gen_dryrun_summary() {
  local log="$1" out="$2"
  {
    echo "# Publish Wrapper — Dry-Run Komut Akışı"
    echo ""
    echo "- **Tarih:** $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- **Repo:** $OWNER/$REPO_NAME"
    echo "- **Kaynak log:** $log"
    echo "- **Mod:** dry-run — hiçbir kalıcı komut çalıştırılmadı"
    echo ""
    echo "## Komut akışı"
    echo ""
    awk '
      /===== AŞAMA|===== SONUÇ/ {
        gsub(/^\[[^]]*\] /, ""); gsub(/^===== /, ""); gsub(/ =====$/, "");
        print ""; print "### " $0; next
      }
      /\[DRY-RUN\] çalıştırılacak:/ {
        gsub(/^\[[^]]*\] \[DRY-RUN\] çalıştırılacak: /, "");
        print "- `" $0 "`"; next
      }
      /\[DRY-RUN\] / {
        gsub(/^\[[^]]*\] \[DRY-RUN\] /, "");
        print "- " $0; next
      }
    ' "$log"
    echo ""
    echo "## Tam çıktı (denetim)"
    echo ""
    echo '```text'
    sed 's/^\[[0-9:]*\] //' "$log"
    echo '```'
  } > "$out"
}

if [ "$DRY_RUN" = "1" ]; then
  log "publish_wrapper.sh DRY-RUN modunda — hiçbir komut çalıştırılmayacak"
else
  log "publish_wrapper.sh başladı"
fi
log "repo_root: $REPO_ROOT · repo_name: $REPO_NAME · log: $LOG"

# ── VERIFY-CHECKS modu: yalnızca AŞAMA 1 doğrulaması ───────────────────────
# status_checks.py + --gh (workflow ↔ GitHub eşleşmesi + merge engeli smoke).
# Repo oluşturma / push / CI izleme ÇALIŞTIRILMAZ — bağımsız, hızlı bir kapı.
# AŞAMA 0 precheck (temiz tree + smoke) bu modda çalışmaz: doğrulama salt
# okunur (GitHub API sorgusu) ve temiz tree gerektirmez — geliştirme
# ortamında dahi çağrılabilir. gh auth yine de zorunludur (precheck içinde
# doğrulanmış olması gerekmez — burada kendisi denetler).
# --with-stage4 ile birleşimi anlamsızdır (stage4 zaten push gerektirir).
if [ "$VERIFY_CHECKS" = "1" ]; then
  if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
    fail "--verify-checks gh CLI + auth gerektirir (gh auth status)"
  fi
  OWNER="$(gh api user -q .login 2>/dev/null || true)"
  # Makine-okur JSON sidecar (verdict/rc + --gh --json detayı). Varsayılan
  # gitignore'lu logs/verify_checks.json — her koşulda denetim izinde kalır.
  VERIFY_CHECKS_OUT="${VERIFY_CHECKS_OUT:-logs/verify_checks.json}"
  step "AŞAMA 1 (VERIFY-CHECKS) — required check doğrulaması"
  verify_checks
  step "SONUÇ (VERIFY-CHECKS)"
  log "Repo:        https://github.com/$OWNER/$REPO_NAME"
  log "Log dosyası: $LOG"
  if [ "$DRY_RUN" = "1" ]; then
    log "SONUÇ: VERIFY-CHECKS ✓ (dry-run — yalnızca önizleme)"
  else
    log "SONUÇ: VERIFY-CHECKS ✓ — required check adları workflow ile birebir eşleşiyor"
  fi
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 0 — Ön-kontrol (publish_precheck.sh — tek komut)"

# AŞAMA 0'ın tamamı tek kaynak scriptte (docs/publish_precheck.sh): repo/tree/
# history temizliği + commit-msg kuralı + pre-commit smoke (5 kapı) + gh auth +
# branch/remote + status check adları. Herhangi bir FAIL → senaryo DURUR.
# Not: smoke testi artık commit-msg kuralına uygun mesajla koşar ("docs: ...");
# eski "smoke:" başlığı commit-msg-style hook'u tarafından reddedilir.
if [ "$DRY_RUN" = "1" ]; then
  log "[DRY-RUN] bash docs/publish_precheck.sh --skip-smoke --allow-remote"
  log "[DRY-RUN]   (dry-run'da smoke atlanır; remote zaten varsa toleranslı)"
  if bash docs/publish_precheck.sh --skip-smoke --allow-remote; then
    log "precheck: PASS ✓ (dry-run yine de devam ediyor)"
  else
    warn "precheck FAIL — dry-run olduğundan akış önizlenmeye devam ediyor"
  fi
else
  # İdempotent: origin zaten varsa (repo yayında) --allow-remote ile koş;
  # ilk publish'te (origin yok) düz koş. Smoke testi yerelde 5 kapıyı doğrular.
  PRECHECK_ARGS=""
  if [ -n "$(git remote -v | head -1)" ]; then
    PRECHECK_ARGS="--allow-remote"
  fi
  if ! bash docs/publish_precheck.sh $PRECHECK_ARGS; then
    fail "AŞAMA 0 kapıları geçilemedi — log: $LOG"
  fi
fi

# ── CI-SIMULATE modu: AŞAMA 1-3 yerine yerel simülasyon ──────────────────
# precheck + status_checks + simulate_verify_job.sh koşar;
# push/repo-create CI izleme ATLANIR. Aşağıdaki AŞAMA 1-3 blokları bu modda
# çalıştırılmaz.
if [ "$CI_SIMULATE" = "1" ]; then
  step "AŞAMA 1-3 (CI-SIMULATE) — yerel CI doğrulaması"

  # status_checks.py — workflow job adlarını listele (GitHub eşleşmesi atlanır).
  if [ -x _calisma/.venv_z3/bin/python ]; then
    SC_PY=_calisma/.venv_z3/bin/python
  else
    SC_PY=python3
  fi
  log "status_checks.py — beklenen required check adları:"
  "$SC_PY" _calisma/CIKTI/status_checks.py | sed 's/^/    /' || warn "status_checks.py çalışmadı"

  # simulate_verify_job.sh — CI job zincirini yerelde compose-style koş.
  # Bu, --full (K1-K14) + pre-commit + sha256 + config bundle + simulate'dır.
  log "simulate_verify_job.sh — yerel CI simülasyonu başlıyor..."
  SIM_DIR="$REPO_ROOT/.freebuff/sim/verify_job"
  rm -rf "$SIM_DIR"
  if bash _calisma/CIKTI/simulate_verify_job.sh; then
    log "CI-SIMULATE: PASS ✓ — tüm kapılar yeşil (yerel)"
    # Sonuç dosyalarını göster.
    if [ -f "$SIM_DIR/summary.md" ]; then
      log "Özet (summary.md — ilk 20 satır):"
      head -20 "$SIM_DIR/summary.md" | sed 's/^/    /'
    fi
    if [ -f "$SIM_DIR/verify_report.txt" ]; then
      log "verify_report.txt sonucu:"
      tail -5 "$SIM_DIR/verify_report.txt" | sed 's/^/    /'
    fi
  else
    CI_EXIT=$?
    fail "CI-SIMULATE: FAIL (exit $CI_EXIT) — simülasyon kapılarından biri başarısız"
  fi

  # AŞAMA 4 (opsiyonel) — branch protection smoke testi bu modda çalışmaz
  # (remote gerekli).
  if [ "$WITH_STAGE4" = "1" ]; then
    warn "--with-stage4 --ci-simulate birlikte kullanılamaz (remote gerekli)"
  fi

  sim_owner="$(git config user.name 2>/dev/null || echo 'OWNER-UNKNOWN')"
  step "SONUÇ (CI-SIMULATE)"
  # Markdown rapor — .freebuff/sim/ altına (denetim izi, tek bakışta özet).
  SIM_MD="$REPO_ROOT/.freebuff/sim/ci_simulate_report.md"
  mkdir -p "$(dirname "$SIM_MD")"
  {
    echo "# CI-SIMULATE Raporu — $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo ""
    echo "- Repo: https://github.com/$sim_owner/$REPO_NAME  (push yok)"
    echo "- Sim dizini: $REPO_ROOT/$SIM_DIR"
    echo "- Log: $LOG"
    echo ""
    echo "## status_checks.py — beklenen required check adları"
    echo '```'
    "$SC_PY" _calisma/CIKTI/status_checks.py 2>&1 | sed 's/^/    /'
    echo '```'
    echo ""
    echo "## simulate_verify_job.sh çıktısı"
    echo '```'
    if [ -f "$SIM_DIR/verify_report.txt" ]; then
      tail -30 "$SIM_DIR/verify_report.txt"
    else
      echo '(verify_report.txt yok)'
    fi
    echo '```'
    echo ""
    if [ -f "$SIM_DIR/summary.md" ]; then
      echo "## GITHUB_STEP_SUMMARY (simulate_verify_job.sh)"
      echo '```'
      cat "$SIM_DIR/summary.md"
      echo '```'
    fi
  } > "$SIM_MD"
  log "Rapor: $SIM_MD"
  log "SONUÇ: CI-SIMULATE ✓ — yerel doğrulama tamamlandı, push yapılmadı (rapor: $SIM_MD)"
  exit 0
fi

# gh kullanıcısı AŞAMA 1/2 için gerekli (precheck içinde doğrulandı).
OWNER="$(gh api user -q .login 2>/dev/null || true)"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 1 — GitHub repo oluştur (interaktif değil, idempotent)"

# gh repo create: isim + --public verildiğinde prompt sormaz (non-interactive).
# İdempotent: repo zaten varsa oluşturma atlanır (re-run / repo zaten yayında).
# --incremental: repo canlı sayılır — oluşturma hiç denenmez (doc INCREMENTAL
# döngüsü AŞAMA 1'i içermez; doğrulama AŞAMA 4'te yapılır).
if [ "$INCREMENTAL" = "1" ]; then
  log "repo oluşturma atlandı (--incremental — repo zaten canlı)"
else
  if gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
    log "repo zaten mevcut: $OWNER/$REPO_NAME (idempotent — oluşturulmuyor)"
  else
    run gh repo create "$REPO_NAME" \
      --description "$DESCRIPTION" \
      --public \
      --disable-issues=false \
      --disable-wiki=true \
      --disable-projects=true \
      --add-readme=false
    done_msg "repo oluşturuldu: $OWNER/$REPO_NAME ✓"
  fi
fi

# ── AŞAMA 1 doğrulaması — status_checks.py + --gh (tek fonksiyon; ayrıca
# --verify-checks modunda da çağrılır). Tek kaynak: workflow job `name:`'leri.
# --incremental: AŞAMA 4'te (CI sonrası) koşar — doc INCREMENTAL adım 4 ile aynı.
if [ "$INCREMENTAL" != "1" ]; then
  verify_checks
fi

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 2 — Remote ekle + push (idempotent)"

run gh repo set-default "$REPO_NAME" || true

# Remote: origin YOKSA ekle; VARSA repo adı eşleşiyorsa dokunma (idempotent),
# eşleşmiyorsa set-url ile düzelt. SSH/HTTPS farkı geçerli sayılır (ikisi de ok).
REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
# --incremental: origin ZORUNLU (repo canlı) — yoksa akışı durdur.
if [ "$INCREMENTAL" = "1" ] && [ -z "$REMOTE_URL" ]; then
  fail "--incremental origin remote gerektirir (repo zaten GitHub'da olmalı; ilk publish için normal akış kullan)"
fi
if [ -n "$REMOTE_URL" ]; then
  case "$REMOTE_URL" in
    *"$OWNER/$REPO_NAME"*)
      log "origin zaten doğru repo: $REMOTE_URL (idempotent — eklenmiyor)"
      ;;
    *)
      warn "origin beklenen repo değil: $REMOTE_URL → set-url ile düzeltiliyor"
      run git remote set-url origin "git@github.com:$OWNER/$REPO_NAME.git"
      ;;
  esac
else
  run git remote add origin "git@github.com:$OWNER/$REPO_NAME.git"
fi
log "remote -v: (güncel durum)"
git remote -v | sed 's/^/    /' || true

# Push: yalnızca bekleyen commit varsa (idempotent — up-to-date'te atlanır).
PUSHED=0
if git rev-parse --verify origin/main >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count origin/main..main 2>/dev/null || echo 0)"
  if [ "$AHEAD" -gt 0 ]; then
    # enforce_admins=true ise doğrudan push (admin) bloke edilir — geçici
    # kapat, push et, GERİ AÇ (her koşulda — push başarısız olsa bile).
    TOGGLED=0
    if [ "$DRY_RUN" != "1" ] && enforce_is_on; then
      log "enforce_admins=true — push için geçici kapatılıyor (sonra geri açılır)"
      if toggle_enforce false; then TOGGLED=1; else warn "enforce_admins kapatılamadı — push denenecek"; fi
    fi
    set +e
    run git push -u origin main
    PUSH_EXIT=$?
    set -e
    if [ "$TOGGLED" = "1" ]; then
      if toggle_enforce true; then
        log "enforce_admins geri açıldı ✓"
      else
        fail "enforce_admins GERİ AÇILAMADI — manuel düzelt: gh api --method PUT .../branches/main/protection (enforce_admins=true)"
      fi
    fi
    [ "$PUSH_EXIT" -eq 0 ] || fail "push başarısız (exit $PUSH_EXIT)"
    PUSHED=1
  else
    log "push gerekmiyor — origin/main ile eşit (idempotent)"
  fi
else
  run git push -u origin main
  PUSHED=1
fi
if [ "$PUSHED" = "1" ]; then
  done_msg "push tamamlandı: $OWNER/$REPO_NAME (main) ✓"
else
  log "AŞAMA 2: push atlandı (bekleyen commit yok)"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 3 — CI çalıştığını doğrula (5-15 dk)"

if [ "$DRY_RUN" = "1" ]; then
  log "[DRY-RUN] push sonrası otomatik tetiklenen CI run'ı şöyle izlenir (HEAD commit'ine göre):"
  log "[DRY-RUN]   gh run list --commit <HEAD_SHA> --limit 1 --json databaseId"
  log "[DRY-RUN]   gh run watch <RUN_ID> --exit-status   (5-15 dk bloklar)"
  log "[DRY-RUN]   gh run view <RUN_ID> --json artifacts \\"
  log "[DRY-RUN]     --jq '.artifacts[] | \"\\(.name) (\\(.size_in_bytes) B)\"'"
  RUN_ID="" ; CONCL="(dry-run — çalıştırılmadı)"
else
  HEAD_SHA="$(git rev-parse HEAD)"
  if [ "$PUSHED" = "1" ]; then
    # Push'un tetiklediği run'ı bekle — HEAD commit'iyle eşle (idempotent:
    # aynı HEAD daha önce koşmuşsa eski run'ı da kabul et).
    RUN_ID=""
    for _ in $(seq 1 12); do
      RUN_ID="$(gh run list --commit "$HEAD_SHA" --limit 1 --json databaseId \
        -q '.[0].databaseId' 2>/dev/null || true)"
      [ -n "$RUN_ID" ] && break
      sleep 5
    done
    [ -n "$RUN_ID" ] || fail "push yapıldı ama CI run listelenemedi (gh run list --commit $HEAD_SHA)"
  else
    # Push yapılmadı — HEAD için ÖNCEDEN var olan run'ı izle (idempotent).
    RUN_ID="$(gh run list --commit "$HEAD_SHA" --limit 1 --json databaseId \
      -q '.[0].databaseId' 2>/dev/null || true)"
    if [ -n "$RUN_ID" ]; then
      log "push yok; HEAD ($HEAD_SHA) için mevcut run izleniyor: $RUN_ID"
    else
      log "push yok ve HEAD için run yok — CI doğrulaması atlanıyor (idempotent)"
      CONCL="no-run"
    fi
  fi

  if [ -n "$RUN_ID" ]; then
    log "CI run ID: $RUN_ID"

    # Run bitene kadar izle (non-interactive). Sonuç FAIL olsa bile script'i
    # düşürmemek için exit kodu elle yakalanır (FAIL bir SONUÇ, script hatası değil).
    set +e
    gh run watch "$RUN_ID" --exit-status
    CI_EXIT=$?
    set -e
    CONCL="$(gh run view "$RUN_ID" --json conclusion -q '.conclusion' 2>/dev/null || echo "unknown")"
    log "CI sonucu: $CONCL (gh run watch exit=$CI_EXIT)"

    log "Artifact'lar:"
    gh run view "$RUN_ID" --json artifacts \
      --jq '.artifacts[] | "    \(.name) (\(.size_in_bytes) B)"' 2>/dev/null || true
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# INCREMENTAL mod — AŞAMA 4: durum + doğrulama (doc INCREMENTAL PUSH adım 4).
# CI sonrası: job durumları + status_checks --gh (8 check + merge engeli smoke).
# Repo oluşturma/remote ekleme atlandığından burası akışın kapanış doğrulamasıdır.
if [ "$INCREMENTAL" = "1" ]; then
  step "AŞAMA 4 (INCREMENTAL) — durum + doğrulama"

  if [ -n "$RUN_ID" ]; then
    log "Job durumları (canlı):"
    gh run view "$RUN_ID" --json jobs \
      --jq '.jobs[] | "    \(.name)\t\(.conclusion)"' 2>/dev/null || true
  else
    log "RUN_ID yok (push yok + HEAD için run yok) — job durumu atlandı"
  fi

  # AŞAMA 1 (b): branch protection eşleşmesi (8 check + merge engeli smoke).
  verify_checks

  step "SONUÇ (INCREMENTAL)"
  log "Repo:        https://github.com/$OWNER/$REPO_NAME"
  log "CI run:      ${RUN_ID:-yok}"
  log "Log dosyası: $LOG"
  if [ "$DRY_RUN" = "1" ]; then
    if [ "$DRY_RUN_SUMMARY" = "1" ]; then
      gen_dryrun_summary "$LOG" "$SUMMARY_MD"
      log "Dry-run özeti: $SUMMARY_MD"
    fi
    log "SONUÇ: INCREMENTAL ✓ (dry-run — yalnızca önizleme)"
    exit 0
  fi
  if [ "${CONCL:-unknown}" = "success" ] || [ "${CONCL:-unknown}" = "no-run" ]; then
    log "SONUÇ: PASS ✓ — precheck → push → CI izle → doğrulama tamamlandı"
  else
    log "SONUÇ: CI conclusion '$CONCL' — raporları incele (fail-closed kapı bir bulgu yakalamış olabilir)"
  fi
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
if [ "$WITH_STAGE4" = "1" ]; then
  step "AŞAMA 4 (opsiyonel) — Branch protection'ın çalıştığını kanıtla"

  run git checkout -b test/protection-check
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] marker dosyası oluşturulur + commit atılır:"
    log "[DRY-RUN]   printf '# protection smoke\\n' > _calisma/CIKTI/PROTECTION_SMOKE.md"
    log "[DRY-RUN]   git add _calisma/CIKTI/PROTECTION_SMOKE.md && git commit --no-verify"
  else
    # Doc ile aynı yol (PUBLISH_SCENARIO AŞAMA 4).
    printf '# protection smoke\n' > _calisma/CIKTI/PROTECTION_SMOKE.md
    git add _calisma/CIKTI/PROTECTION_SMOKE.md
    # --no-verify: bu test uzak branch korumasını denetler, yerel pre-commit
    # kapısını değil.
    git commit --no-verify -m "docs: protection smoke marker" || {
      git checkout main
      git branch -D test/protection-check >/dev/null 2>&1 || true
      rm -f _calisma/CIKTI/PROTECTION_SMOKE.md
      fail "AŞAMA 4 test commit'i oluşturulamadı"
    }
  fi
  run git push origin test/protection-check
  run gh pr create --base main --head test/protection-check \
    --title "docs: protection smoke" --body "otomatik wrapper testi"

  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] merge denenir: gh pr merge --squash --delete-branch"
    log "[DRY-RUN]   (beklenen: required check'ler TAMAMLANMADAN reddedilir)"
  else
    # Merge denenir; koruma aktifse reddedilmeli.
    set +e
    gh pr merge --squash --delete-branch >/dev/null 2>&1
    MERGE_EXIT=$?
    set -e
    if [ "$MERGE_EXIT" -eq 0 ]; then
      warn "PR merge EDİLDİ — branch protection ÇALIŞMIYOR olabilir"
    else
      log "branch protection çalışıyor ✓ (merge reddedildi, exit=$MERGE_EXIT)"
    fi
  fi

  run git checkout main
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] temizlik: branch -D + marker sil + PR kapat + uzak branch sil"
  else
    git branch -D test/protection-check >/dev/null 2>&1 || true
    rm -f _calisma/CIKTI/PROTECTION_SMOKE.md
    gh pr close test/protection-check --comment "protection smoke sonlandı" >/dev/null 2>&1 || true
    git push origin --delete test/protection-check >/dev/null 2>&1 || true
  fi
else
  step "AŞAMA 4 (opsiyonel) — atlandı (çalıştırmak için: --with-stage4)"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "SONUÇ"

if [ "$DRY_RUN" = "1" ]; then
  log "Repo:        https://github.com/$OWNER/$REPO_NAME  (dry-run — oluşturulmayacak)"
  log "CI run:      $RUN_ID (dry-run — çalıştırılmadı)"
  log "Log dosyası: $LOG"
  if [ "$DRY_RUN_SUMMARY" = "1" ]; then
    gen_dryrun_summary "$LOG" "$SUMMARY_MD"
    log "Dry-run özeti: $SUMMARY_MD"
  fi
  log "SONUÇ: DRY-RUN ✓ — hiçbir komut çalıştırılmadı (yalnızca önizleme)"
  exit 0
fi

log "Repo:        https://github.com/$OWNER/$REPO_NAME"
log "CI run:      $RUN_ID (sonuç: $CONCL)"
log "Artifacts:   https://github.com/$OWNER/$REPO_NAME/actions/runs/$RUN_ID"
log "Protection:  https://github.com/$OWNER/$REPO_NAME/settings/branches"
log "Log dosyası: $LOG"

if [ "${CONCL:-unknown}" = "success" ]; then
  log "SONUÇ: PASS ✓"
elif [ "${CONCL:-unknown}" = "no-run" ]; then
  log "SONUÇ: PASS ✓ (yeni run yok — bekleyen push yok, idempotent re-run)"
else
  log "SONUÇ: CI conclusion '$CONCL' — raporları incele (fail-closed kapı bir bulgu yakalamış olabilir)"
fi
