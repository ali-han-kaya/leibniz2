#!/usr/bin/env bash
#
# publish_precheck.sh — docs/PUBLISH_SCENARIO.md AŞAMA 0 ön-kontrolü (tek komut).
#
# Kullanım:
#   bash docs/publish_precheck.sh                 # ilk publish (remote boş beklenir)
#   bash docs/publish_precheck.sh --allow-remote  # repo zaten GitHub'da (incremental push öncesi)
#   bash docs/publish_precheck.sh --skip-smoke    # smoke testi atla (commit oluşturmaz)
#   bash docs/publish_precheck.sh --ci            # CI advisory job: yerel-only kontrolleri INFO yapar
#   bash docs/publish_precheck.sh --verify-checks # YALNIZCA AŞAMA 1 doğrulaması:
#                                                 # wrapper --verify-checks ile AYNI kapı
#                                                 # (status_checks.py + --gh; tek kaynak
#                                                 # _calisma/CIKTI/verify_checks.sh). Diğer
#                                                 # kapılar çalışmaz, salt okunur, hızlı.
#
#   Not: çıktıyı repo içine yazacaksan gitignore'lu bir yola yönlendir
#        (ör. tee .freebuff/precheck_report.txt) — yoksa tree-temiz kontrolü FAIL olur.
#
# Her kontrol [PASS]/[FAIL] raporlanır; herhangi bir FAIL → exit 1 (fail-closed):
# senaryonun AŞAMA 1'ine ancak tüm kapılar yeşilse geçilir.
# AŞAMA 0'ın manuel karşılığı: docs/PUBLISH_SCENARIO.md → "AŞAMA 0".
set -uo pipefail

FAILED=0
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAILED=1; }
warn() { printf '  [UYARI] %s\n' "$*"; }
info() { printf '  [INFO] %s\n' "$*"; }

ALLOW_REMOTE=0
SKIP_SMOKE=0
CI_MODE=0
VERIFY_CHECKS=0
for a in "$@"; do
  case "$a" in
    --allow-remote) ALLOW_REMOTE=1 ;;
    --skip-smoke)   SKIP_SMOKE=1 ;;
    --ci)           CI_MODE=1 ;;
    --verify-checks) VERIFY_CHECKS=1 ;;
    *) echo "Bilinmeyen bayrak: $a (geçerli: --allow-remote, --skip-smoke, --ci, --verify-checks)" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# status_checks.py PyYAML ister — venv'de varsa onu kullan (yoksa python3).
if [ -x _calisma/.venv_z3/bin/python ]; then
  PY=_calisma/.venv_z3/bin/python
else
  PY=python3
fi

# ── VERIFY-CHECKS modu: wrapper --verify-checks ile AYNI kapı (tek kaynak) ──
# Yalnızca AŞAMA 1 doğrulaması: status_checks.py + --gh (workflow ↔ GitHub
# eşleşmesi + merge engeli smoke). Repo/tree/hook kapıları ÇALIŞTIRILMAZ —
# bağımsız, salt okunur bir kapıdır (geliştirme ortamında dahi çağrılabilir).
# Gerçek drift (eksik/fazla check) → FAIL (fail-closed); koruma kurulu
# değilse UYARI (publish öncesi normal).
if [ "$VERIFY_CHECKS" = "1" ]; then
  # precheck log() tanımlamaz — library'ye precheck [INFO] biçiminde log ver.
  log() { info "$*"; }
  # shellcheck source=/dev/null
  source _calisma/CIKTI/verify_checks.sh
  echo "════════════ AŞAMA 1 — VERIFY-CHECKS (required check doğrulaması) ════════════"
  if verify_checks; then
    echo ""
    echo "SONUÇ: PASS ✓ — required check adları workflow ile birebir eşleşiyor"
    exit 0
  else
    echo ""
    echo "SONUÇ: FAIL ✗ — yukarıdaki [FAIL] satırlarını düzelt, tekrar çalıştır"
    exit 1
  fi
fi

echo "════════════ AŞAMA 0 — Publish ön-kontrolü ════════════"

# ── (a) Repo + working tree + history ─────────────────────────────────────
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  pass "git repo mevcut: $REPO_ROOT"
else
  fail "git repo yok: $REPO_ROOT"
fi

DIRTY="$(git status --porcelain)"
if [ -z "$DIRTY" ]; then
  pass "working tree temiz"
else
  fail "working tree temiz değil — git status --porcelain: $(echo "$DIRTY" | head -5 | tr '\n' '; ')"
fi

# History'deki noise/marker başlıklar (commit-msg hook'uyla AYNI ölçüt).
if git log --oneline -5 | grep -qiE "test marker|^test:|^wip|^smoke"; then
  fail "son 5 commit'te noise/marker başlık var — temizle (docs/HISTORY_CLEANUP.md)"
else
  pass "son 5 commit temiz (noise/marker yok)"
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo "")"
if [ "$BRANCH" = "main" ]; then
  pass "branch: main"
elif [ "$CI_MODE" = "1" ]; then
  info "branch: '$BRANCH' (CI — event branch'i; main push'unda 'main' olur)"
else
  fail "branch '$BRANCH' — 'main' olmalı"
fi

# ── (a2) Commit mesaj kuralı kurulu (docs/HISTORY_CLEANUP.md) ──────────────
# CI modunda bu kontroller anlamsızdır: runner'da hook kurulu değildir ama 5
# kapı verify job'unda `pre-commit run --all-files` + commit-msg CI denetimi
# ile zaten koşar. Yerel-only olduklarından INFO ile işaretlenir (FAIL değil).
if [ "$CI_MODE" = "1" ]; then
  info "(CI) hook kurulum kontrolü atlandı — pre-commit verify job'unda koşar; commit.template kurulumu yerel içindir (setup_commit_hooks.sh)"
else
  # İlk doğrulama
  a2_failed=0
  TMPL="$(git config commit.template || true)"
  if [ "$TMPL" = ".gitmessage" ] && [ -f .gitmessage ]; then
    pass "commit.template = .gitmessage"
  else
    a2_failed=1
  fi
  if [ -x .git/hooks/commit-msg ]; then
    pass "commit-msg git hook'u kurulu"
  else
    a2_failed=1
  fi
  if [ -x .git/hooks/pre-commit ]; then
    pass "pre-commit git hook'u kurulu"
  else
    a2_failed=1
  fi

  # Otomatik onarım: eksik varsa setup_commit_hooks.sh çalıştır, sonra yeniden doğrula
  if [ "$a2_failed" -ne 0 ]; then
    SETUP_SCRIPT=""
    for candidate in "_calisma/CIKTI/setup_commit_hooks.sh" "$(dirname "${BASH_SOURCE[0]}")/../_calisma/CIKTI/setup_commit_hooks.sh"; do
      if [ -x "$candidate" ]; then
        SETUP_SCRIPT="$candidate"
        break
      fi
    done
    if [ -n "$SETUP_SCRIPT" ]; then
      warn "hook kurulum eksik — setup_commit_hooks.sh otomatik çalıştırılıyor"
      if bash "$SETUP_SCRIPT" >/dev/null 2>&1; then
        info "setup_commit_hooks.sh tamamlandı — yeniden doğrulanıyor"
      else
        warn "setup_commit_hooks.sh başarısız — manuel kurulum gerekli"
      fi
      # Yeniden doğrulama (aynı ölçüt)
      a2_failed=0
      TMPL="$(git config commit.template || true)"
      if [ "$TMPL" = ".gitmessage" ] && [ -f .gitmessage ]; then
        pass "commit.template = .gitmessage (otomatik onarım sonrası)"
      else
        fail "commit.template kurulu değil (onarım sonrası hâlâ eksik): git config commit.template .gitmessage"
        a2_failed=1
      fi
      if [ -x .git/hooks/commit-msg ]; then
        pass "commit-msg git hook'u kurulu (otomatik onarım sonrası)"
      else
        fail "commit-msg hook'u yok (onarım sonrası hâlâ eksik): pre-commit install --hook-type commit-msg"
        a2_failed=1
      fi
      if [ -x .git/hooks/pre-commit ]; then
        pass "pre-commit git hook'u kurulu (otomatik onarım sonrası)"
      else
        fail "pre-commit hook'u yok (onarım sonrası hâlâ eksik): pre-commit install"
        a2_failed=1
      fi
      if [ "$a2_failed" -ne 0 ]; then
        FAILED=1
      fi
    else
      fail "setup_commit_hooks.sh bulunamadı — manuel kurulum gerekli: bash _calisma/CIKTI/setup_commit_hooks.sh"
      FAILED=1
    fi
  fi
fi

# ── (b) Pre-commit smoke test — GÜVENLİ ───────────────────────────────────
# Yalnızca tree temizse ve daha önce FAIL yoksa koşar. Başarısızsa commit
# oluşmaz; başarılıysa SMOKE_BEFORE'a reset atılır (doc'taki `reset --hard
# HEAD^` hatasını tekrarlamaz — HEAD'i kendisi geri alır).
if [ "$CI_MODE" = "1" ]; then
  info "smoke testi CI modunda atlanır — 5 kapı verify job'unda koşuyor (pre-commit run --all-files + commit-msg CI denetimi)"
elif [ "$SKIP_SMOKE" = "1" ]; then
  warn "smoke testi --skip-smoke ile atlandı"
elif [ "$FAILED" -ne 0 ] || [ -n "$(git status --porcelain)" ]; then
  warn "smoke testi atlandı (önceki FAIL veya kirli tree)"
else
  SMOKE_BEFORE="$(git rev-parse HEAD)"
  if git commit --allow-empty -m "docs: pre-commit smoke test" >/dev/null 2>&1; then
    git reset --hard "$SMOKE_BEFORE" >/dev/null 2>&1
    if [ "$(git rev-parse HEAD)" = "$SMOKE_BEFORE" ]; then
      pass "pre-commit smoke: 5 kapı (update-config/verify-delivery/Z3/Lean/commit-msg)"
    else
      fail "smoke sonrası HEAD geri alınamadı"
    fi
  else
    fail "pre-commit smoke FAIL — kapı kırmızı; önce yeşile çevir"
  fi
fi

# ── (c) gh CLI + auth ─────────────────────────────────────────────────────
if command -v gh >/dev/null 2>&1; then
  pass "gh CLI kurulu ($(gh --version 2>/dev/null | head -1 | awk '{print $3}'))"
  if [ "$CI_MODE" = "1" ]; then
    # CI: GITHUB_TOKEN repo-kapsamlıdır — `gh api user` (GET /user) her token
    # tipiyle çalışmayabilir; repo-scoped çağrı (contents: read yeterli)
    # garantilidir. Workflow GITHUB_REPOSITORY + GH_TOKEN/GITHUB_TOKEN verir.
    if OUT="$(gh api "repos/${GITHUB_REPOSITORY:-_/none}" -q .full_name 2>&1)"; then
      pass "gh auth: $OUT"
    else
      fail "gh auth yok — gh api repos/${GITHUB_REPOSITORY:-?}: $(echo "$OUT" | head -1)"
    fi
  elif gh auth status >/dev/null 2>&1; then
    pass "gh auth: $(gh api user -q .login 2>/dev/null || echo '?')"
  else
    fail "gh auth yok — 'gh auth login' çalıştır"
  fi
else
  fail "gh CLI kurulu değil (brew install gh)"
fi

# ── (d) Remote + upstream durumu ──────────────────────────────────────────
REMOTE="$(git remote -v | head -1)"
if [ -n "$REMOTE" ]; then
  if [ "$ALLOW_REMOTE" = "1" ]; then
    pass "remote mevcut (--allow-remote): $REMOTE"
  else
    fail "remote zaten var — ilk publish için boş olmalı: $REMOTE"
  fi
else
  pass "remote yok"
fi

if git rev-parse --verify origin/main >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count origin/main..main 2>/dev/null || echo '?')"
  BEHIND="$(git rev-list --count main..origin/main 2>/dev/null || echo '?')"
  if [ "$AHEAD" = "0" ] && [ "$BEHIND" = "0" ]; then
    pass "origin/main ile eşit (push bekleyen yok)"
  else
    warn "origin/main: $BEHIND geride / $AHEAD önde (incremental push)"
  fi
else
  info "origin/main yok (henüz push edilmemiş)"
fi

# ── (e) Status check adları + PR-merge engeli — TEK KAYNAK ──────────────
# status_checks.py, verify.yml'deki job `name:` alanlarından required check
# adaylarını üretir (manifest-comment/precheck hariç). --gh --json ile GitHub
# branch protection'daki gerçek liste VE merge engeli (strict / enforce_admins
# / force-push / deletions smoke) AYRI doğrulanır; koruma kurulu değilse
# UYARI (publish öncesi normal). AŞAMA 1 tek komutla burada doğrulanır.
SC_OUT="$(mktemp)"
if "$PY" _calisma/CIKTI/status_checks.py >"$SC_OUT" 2>&1; then
  N="$(grep -cE '^  +[0-9]+\. ' "$SC_OUT")"
  pass "status check adları workflow'dan türetildi ($N kapı)"
else
  fail "status_checks.py çalışmadı — $(tail -1 "$SC_OUT")"
fi
if [ "$ALLOW_REMOTE" = "1" ] && command -v gh >/dev/null 2>&1; then
  GH_JSON="$(mktemp)"
  "$PY" _calisma/CIKTI/status_checks.py --gh --json >"$GH_JSON" 2>/dev/null
  SC_GH_RC=$?
  # JSON'u tek geçişte shell değişkenlerine ayrıştır (eval + heredoc).
  GH_VERDICT="ERROR"; GH_NAMES_OK="false"; GH_ENFORCEMENT_OK="false"
  GH_MISSING=""; GH_EXTRA=""; GH_SMOKE_FAIL=""
  eval "$(GH_JSON_PATH="$GH_JSON" "$PY" - <<'PYEOF'
import json, os
d = json.load(open(os.environ["GH_JSON_PATH"]))
def esc(s): return str(s).replace("'", "'\\''")
print("GH_VERDICT='%s'" % esc(d.get("verdict", "ERROR")))
print("GH_NAMES_OK='%s'" % ("true" if d.get("names_ok") else "false"))
print("GH_ENFORCEMENT_OK='%s'" % ("true" if d.get("enforcement_ok") else "false"))
print("GH_MISSING='%s'" % esc("; ".join(d.get("missing") or [])))
print("GH_EXTRA='%s'" % esc("; ".join(d.get("extra") or [])))
smoke_fail = "; ".join(s["label"] for s in d.get("smoke", []) if not s.get("ok"))
print("GH_SMOKE_FAIL='%s'" % esc(smoke_fail))
PYEOF
)"
  # Fail-closed: ERROR (rc≠0 VEYA JSON ayrıştırılamadı) → FAIL. Smoke
  # çalıştırılamıyorsa "denetlenemedi" PASS sayılmaz — AŞAMA 0 kapısıdır.
  if [ "$GH_VERDICT" = "ERROR" ]; then
    fail "status_checks --gh smoke çalıştırılamadı (rc=$SC_GH_RC) — JSON ayrıştırılamadı veya repo/gh API hatası; manuel: $PY _calisma/CIKTI/status_checks.py --gh --json"
  else
    case "$GH_VERDICT" in
      PASS)
        pass "branch protection: check adları birebir eşleşiyor (workflow ↔ GitHub)"
        pass "merge engeli: strict/enforce_admins/force-push/deletions etkin"
        ;;
      FAIL)
        if [ "$GH_NAMES_OK" = "true" ]; then
          pass "branch protection: check adları birebir eşleşiyor (workflow ↔ GitHub)"
        else
          fail "branch protection: check adları uyumsuz — eksik: $GH_MISSING; fazla: $GH_EXTRA"
        fi
        if [ "$GH_ENFORCEMENT_OK" = "true" ]; then
          pass "merge engeli: strict/enforce_admins/force-push/deletions etkin"
        else
          fail "merge engeli etkin değil — eksik: $GH_SMOKE_FAIL"
        fi
        ;;
      NOT_SET_UP)
        warn "branch protection kurulu değil — AŞAMA 1 (b) web UI'da kur (gh api 404)"
        ;;
      UNREADABLE)
        warn "branch protection okunamadı (yetki/ağ) — GITHUB_TOKEN'da admin scope'u yok; gerçek doğrulama yerelde gh auth ile yapılır (rc=$SC_GH_RC)"
        ;;
      *)
        fail "branch protection durumu bilinmiyor: $GH_VERDICT (rc=$SC_GH_RC)"
        ;;
    esac
  fi
  rm -f "$GH_JSON"
else
  info "branch protection GitHub doğrulaması atlandı (--allow-remote + gh gerekli)"
fi
rm -f "$SC_OUT"

# ── Sonuç ─────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "SONUÇ: PASS ✓ — AŞAMA 1'e geçilebilir"
  exit 0
else
  echo "SONUÇ: FAIL ✗ — yukarıdaki [FAIL] satırlarını düzelt, tekrar çalıştır"
  exit 1
fi
