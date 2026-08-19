#!/usr/bin/env bash
# setup_commit_hooks.sh — commit-msg + pre-commit kapılarını TEK komutla kur.
#
# Yaptıkları (idempotent — her koşumda aynı sonucu verir, güvenle tekrarlanır):
#   1. git config commit.template .gitmessage    (başlık şablonu, repo kökünden)
#   2. pre-commit install                        (pre-commit stage kapısı)
#   3. pre-commit install --hook-type commit-msg (commit-msg stage kapısı)
#
# Bu üçü, docs/publish_precheck.sh'in (a2) adımında DENETLEDİĞİ kurulumun
# birebir aynısıdır — betik kurar, precheck doğrular (tek ölçüt).
#
# Kullanım (repo kökünden veya herhangi bir yerden):
#   bash _calisma/CIKTI/setup_commit_hooks.sh
#
# Ön koşul: pre-commit kurulu (PATH'te veya _calisma/.venv_z3/bin altında).
#   pip install pre-commit
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; }

# pre-commit çözümle: venv → PATH (simulate_verify_job.sh ile aynı desen).
if [ -x "$REPO_ROOT/_calisma/.venv_z3/bin/pre-commit" ]; then
  PC="$REPO_ROOT/_calisma/.venv_z3/bin/pre-commit"
elif command -v pre-commit >/dev/null 2>&1; then
  PC="pre-commit"
else
  echo "HATA: pre-commit bulunamadı."
  echo "  Kurulum: pip install pre-commit"
  echo "  (veya repo venv'i: _calisma/.venv_z3/bin/python -m pip install pre-commit)"
  exit 2
fi

echo "=== commit-msg + pre-commit kurulumu ==="
echo "repo      : $REPO_ROOT"
echo "pre-commit: $PC ($("$PC" --version 2>/dev/null))"
echo ""

cd "$REPO_ROOT" || exit 2
FAILED=0

# 1) commit.template — şablon başlık (commit_msg_hook.sh ile aynı kural).
git config commit.template .gitmessage
if [ "$(git config commit.template)" = ".gitmessage" ] && [ -f .gitmessage ]; then
  pass "commit.template = .gitmessage"
else
  fail "commit.template kurulamadı (.gitmessage kökte olmalı)"
  FAILED=1
fi

# 2) pre-commit stage (update-config + verify-delivery + Z3 + Lean kapıları).
if "$PC" install >/dev/null 2>&1; then
  pass "pre-commit stage kuruldu (.git/hooks/pre-commit)"
else
  fail "pre-commit install başarısız"
  FAILED=1
fi

# 3) commit-msg stage (commit_msg_hook.sh — başlık denetimi).
if "$PC" install --hook-type commit-msg >/dev/null 2>&1; then
  pass "commit-msg stage kuruldu (.git/hooks/commit-msg)"
else
  fail "pre-commit install --hook-type commit-msg başarısız"
  FAILED=1
fi

# ── Doğrulama (docs/publish_precheck.sh (a2) ile AYNI ölçüt) ─────────────
echo ""
echo "=== doğrulama (publish_precheck.sh (a2) ile aynı ölçüt) ==="
TMPL="$(git config commit.template || true)"
if [ "$TMPL" = ".gitmessage" ]; then
  pass "commit.template = $TMPL"
else
  fail "commit.template = '$TMPL' (beklenen: .gitmessage)"
  FAILED=1
fi
[ -x .git/hooks/pre-commit ] && pass ".git/hooks/pre-commit" || { fail ".git/hooks/pre-commit yok"; FAILED=1; }
[ -x .git/hooks/commit-msg ] && pass ".git/hooks/commit-msg" || { fail ".git/hooks/commit-msg yok"; FAILED=1; }

echo ""
if [ "$FAILED" -ne 0 ]; then
  echo "SONUÇ: FAIL — eksik adımları yukarıda gör."
  exit 1
fi
echo "SONUÇ: PASS — commit-msg + pre-commit kapıları kurulu."
exit 0
