# Dev-Bootstrap Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command (`_calisma/dev_bootstrap.sh`) takes a fresh checkout/worktree from clone to a green battery: venv_z3 + pptx + dashboard-next toolchains provisioned, contract-tested, README-documented.

**Architecture:** A single idempotent POSIX/bash script provisions the three gitignored toolchains that a fresh clone lacks (`_calisma/.venv_z3` python-venv with pinned deps, `_calisma/pptx/node_modules`, `apps/dashboard-next/node_modules`) with a fail-closed `--check` mode. Contract tests pin the rc behavior; the script is then added to the unit-test battery so the commit chain itself proves a fresh checkout can reach green.

**Tech Stack:** bash 3.2 (macOS system bash), stdlib-only Python (unittest), npm ci (both package-lock.json files are tracked), pre-commit chain (50 hooks).

**Spec:** `findings.md` (repo root), sections "using-git-worktrees" and "verification-before-completion" (session 2026-09-19): the fresh-worktree baseline failed at `_calisma/pptx/node_modules` (test_pptx_export module crash, hardened in commit `d396b8c`) and at `_calisma/.venv_z3` (9 hook entries need it; installed manually with pinned versions). The third gap — `apps/dashboard-next/node_modules` (366 packages) — was also installed manually during that turn. This plan closes all three with one script.

## Global Constraints

- `_calisma/` runtime output: Turkish comments/messages; commit messages: English.
- Bash 3.2 compatible: no `mapfile`, no associative arrays, no `${var,,}`.
- All battery-imported Python is stdlib-only (`check-unit-tests` runs under `.venv_z3`).
- Battery stays green at every commit (currently 139 test files; 140 after Task 2).
- Pin parity is single-sourced in `docs/HOOK_ENV_MATRIX.md`: `z3-solver==5.1.0.0`, `PyYAML==6.0.3`, `pre_commit==4.3.0` (verified live against the working venv during the using-git-worktrees turn).
- Fail-closed: `--check` exits 1 on any missing toolchain; the script exits 1 on any step failure.
- rc contract: `--check` → 0 (complete) / 1 (missing) / 2 (usage); bare run → 0 with last line `BOOTSTRAP OK`, or 1 with last line `BOOTSTRAP FAIL: <step>`.

---

### Task 1: `dev_bootstrap.sh` + contract tests (red → green → commit)

**Files:**
- Create: `_calisma/dev_bootstrap.sh` (executable)
- Test: `_calisma/CIKTI/test_dev_bootstrap.py`

**Interfaces:**
- Consumes: system `python3 -m venv`, `npm ci` (lockfiles tracked), pins from `docs/HOOK_ENV_MATRIX.md` (parity enforced by the `check-hook-env-matrix` gate, not at runtime).
- Produces: `_calisma/.venv_z3/bin/python` with the three pins importable; both `node_modules` dirs populated; the rc contract above. Task 2 relies on `--check` rc=0 after a bare run.

- [ ] **Step 1: Write the failing test**

Create `_calisma/CIKTI/test_dev_bootstrap.py` with exactly this content:

```python
"""test_dev_bootstrap.py — dev_bootstrap.sh sözleşme-testleri (stdlib-only).

Kapsam: varlık+çalıştırılabilirlik (kırmızı-faz: script yokken fail),
--check exit-kontratı (fail-closed), --help rc=0, idempotence, pin-paritesi.
Çalıştırma: venv_z3 python ile (battery listesine girer).

Not: fail-closed testi gerçek .venv_z3'ü geçici-adla gizler; finally bloğu
her durumda geri koyar. Test venv'in kendi yorumlayıcısı altında koştuğu
için rename çalışan süreci bozmaz (açık dosya-tutamaçları inode-bağlıdır).
"""
import os
import stat
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
SCRIPT = os.path.join(ROOT, "_calisma", "dev_bootstrap.sh")
VENV = os.path.join(ROOT, "_calisma", ".venv_z3")
VENV_PY = os.path.join(VENV, "bin", "python")

PINS = ("z3-solver==5.1.0.0", "PyYAML==6.0.3", "pre_commit==4.3.0")


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


class TestScriptExists(unittest.TestCase):
    def test_script_exists_and_executable(self):
        self.assertTrue(os.path.isfile(SCRIPT), "dev_bootstrap.sh henüz yok")
        mode = os.stat(SCRIPT).st_mode if os.path.isfile(SCRIPT) else 0
        self.assertTrue(mode & stat.S_IXUSR, "dev_bootstrap.sh çalıştırılabilir değil")


@unittest.skipUnless(
    os.path.isfile(SCRIPT), "dev_bootstrap.sh henüz yok (TDD kırmızı-fazı)"
)
class TestCheckContract(unittest.TestCase):
    def test_check_passes_on_provisioned_checkout(self):
        r = _run(["bash", SCRIPT, "--check"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_fail_closed_when_venv_hidden(self):
        if not os.path.isdir(VENV):
            self.skipTest("venv_z3 kurulu değil — fail-closed kanıtı tam-kurulumda koşar")
        hidden = VENV + ".hidden_by_test"
        try:
            os.rename(VENV, hidden)
            r = _run(["bash", SCRIPT, "--check"])
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        finally:
            if os.path.isdir(hidden):
                os.rename(hidden, VENV)


@unittest.skipUnless(
    os.path.isfile(SCRIPT), "dev_bootstrap.sh henüz yok (TDD kırmızı-fazı)"
)
class TestHelpAndIdempotence(unittest.TestCase):
    def test_help_exits_zero(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)

    def test_bootstrap_twice_is_noop_second_run(self):
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik — idempotence tam-kurulumda koşar")
        r = _run(["bash", SCRIPT])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("up to date", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"))


@unittest.skipUnless(os.path.isfile(VENV_PY), "venv_z3 kurulu değil")
class TestPinParity(unittest.TestCase):
    def test_venv_pins_match_matrix(self):
        r = _run([VENV_PY, "-m", "pip", "freeze"])
        frozen = set(r.stdout.splitlines())
        for pin in PINS:
            self.assertIn(pin, frozen, "pin eksik: " + pin)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd _calisma/CIKTI && python3 -m unittest test_dev_bootstrap -v`
Expected: exactly one FAIL — `test_script_exists_and_executable` with "dev_bootstrap.sh henüz yok" (unguarded class = the red phase: feature missing, not a syntax artifact); all other classes SKIP.

- [ ] **Step 3: Write minimal implementation**

Create `_calisma/dev_bootstrap.sh` with exactly this content, then `chmod +x _calisma/dev_bootstrap.sh`:

```bash
#!/bin/bash
# dev_bootstrap.sh — fresh-checkout'u yeşil-bataryaya taşıyan tek komut.
# Kapsam: _calisma/.venv_z3 (pinned) + _calisma/pptx/node_modules +
# apps/dashboard-next/node_modules. Idempotent: kurulu araca dokunmaz.
# Kullanım: dev_bootstrap.sh [--check|--help]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/_calisma/.venv_z3"
VENV_PY="$VENV/bin/python"
# shellcheck disable=SC2086 — pin listesi bilinçli kelime-ayrışmalı
PINS="z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0"

say() { printf '%s\n' "$*"; }
die() { printf 'BOOTSTRAP FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  say "Kullanım: dev_bootstrap.sh [--check|--help]"
  say "  (bayraksız) araç-kümesini kur (idempotent)"
  say "  --check     araç-kümesi tam mı? rc=0/1 (fail-closed)"
  say "  --help      bu yardım"
}

node_modules_ok() {
  [ -d "$1/node_modules" ] && [ -f "$1/package.json" ]
}

venv_ok() {
  [ -x "$VENV_PY" ] || return 1
  local frozen
  frozen="$("$VENV_PY" -m pip freeze 2>/dev/null)" || return 1
  printf '%s\n' "$frozen" | grep -qx 'z3-solver==5.1.0.0' || return 1
  printf '%s\n' "$frozen" | grep -qx 'PyYAML==6.0.3' || return 1
  printf '%s\n' "$frozen" | grep -qx 'pre_commit==4.3.0' || return 1
}

case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --check)
    venv_ok || { say "CHECK FAIL: venv_z3 eksik veya pin-paritesiz"; exit 1; }
    node_modules_ok "$ROOT/_calisma/pptx" || { say "CHECK FAIL: _calisma/pptx/node_modules eksik"; exit 1; }
    node_modules_ok "$ROOT/apps/dashboard-next" || { say "CHECK FAIL: apps/dashboard-next/node_modules eksik"; exit 1; }
    say "CHECK OK"
    exit 0
    ;;
  "") ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if venv_ok; then
  say "venv_z3: up to date"
else
  say "venv_z3: kuruluyor (pinned: $PINS)"
  python3 -m venv "$VENV"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet $PINS || die "venv_z3 pip install"
fi

if node_modules_ok "$ROOT/_calisma/pptx"; then
  say "_calisma/pptx: up to date"
else
  say "_calisma/pptx: npm ci"
  npm ci --prefix "$ROOT/_calisma/pptx" || die "_calisma/pptx npm ci"
fi

if node_modules_ok "$ROOT/apps/dashboard-next"; then
  say "apps/dashboard-next: up to date"
else
  say "apps/dashboard-next: npm ci"
  npm ci --prefix "$ROOT/apps/dashboard-next" || die "apps/dashboard-next npm ci"
fi

say "BOOTSTRAP OK"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd _calisma/CIKTI && python3 -m unittest test_dev_bootstrap -v`
Expected: 7 tests — 6 PASS + 0 unexpected SKIP (the hidden-venv test runs because the venv exists; idempotence runs because `--check` is now green). Then `bash _calisma/dev_bootstrap.sh --check` → prints `CHECK OK`, rc=0.

- [ ] **Step 5: Commit**

```bash
git add _calisma/dev_bootstrap.sh _calisma/CIKTI/test_dev_bootstrap.py
git commit -m "feat(dev): dev_bootstrap.sh — fresh-checkout'tan yeşil-bataryaya tek komut"
```

Expected: the 50-hook chain runs and passes (the new test file is not yet in the battery list, so the battery count stays 139 this commit).

---

### Task 2: Battery list + README + chain proof (red-free; wiring task)

**Files:**
- Modify: `_calisma/CIKTI/check_unit_tests.list` (append one entry)
- Modify: `README.md` (new "Fresh checkout bootstrap" section)
- Modify: `findings.md` (turn record, appended at execution end)

**Interfaces:**
- Consumes: Task 1's script (must pass `--check` rc=0 before this task starts) and its test file.
- Produces: battery of 140 test files; a fresh clone can reach a green commit chain with `bash _calisma/dev_bootstrap.sh` followed by the normal commit flow.

- [ ] **Step 1: Append the test to the battery list**

The list's entry format is derived from its own last line (entries are bare module names or `.py`-suffixed; match whichever exists):

```bash
LAST=$(tail -n 1 _calisma/CIKTI/check_unit_tests.list)
case "$LAST" in
  *.py) ENTRY="test_dev_bootstrap.py" ;;
  *)    ENTRY="test_dev_bootstrap" ;;
esac
printf '%s\n' "$ENTRY" >> _calisma/CIKTI/check_unit_tests.list
tail -n 2 _calisma/CIKTI/check_unit_tests.list
```

Expected: the new entry prints as the last line, in the same format as existing entries.

- [ ] **Step 2: Run the battery to verify 140 files green**

Run: `_calisma/.venv_z3/bin/python -m unittest _calisma/CIKTI.test_dev_bootstrap -v`
Expected: PASS (7 tests). The full battery runs at commit time via the `check-unit-tests` hook — that run is the 140-file proof.

- [ ] **Step 3: Add the README section**

Insert this block after the README's setup/prerequisites section (locate the heading that documents local setup; if none exists, insert before the first `## ` heading after the title):

```markdown
## Fresh checkout bootstrap

Yeni bir clone/worktree'de üç araç-kümesi gitignore'ludur ve tek komutla kurulur
(her adım idempotent — kurulu araca dokunmaz):

```bash
bash _calisma/dev_bootstrap.sh           # venv_z3 (pinned) + pptx + dashboard-next
bash _calisma/dev_bootstrap.sh --check   # fail-closed doğrulama (rc=0/1)
```

Pinler `docs/HOOK_ENV_MATRIX.md` ile tek-kaynaklıdır; `--check` eksik araçta
rc=1 ile düşer (fail-closed).
```

- [ ] **Step 4: Commit (the chain itself is the proof)**

```bash
git add _calisma/CIKTI/check_unit_tests.list README.md
git commit -m "docs: dev-bootstrap battery'de (139->140) ve README quickstart"
```

Expected: the pre-commit chain runs `check-unit-tests` over 140 files — all green; commit lands. If any hook fails, fix the finding (do not skip hooks) and re-commit.

- [ ] **Step 5: Record the turn**

Append to `findings.md` a short section "dev-bootstrap plan executed" listing: the two commits' hashes, the battery count 139→140, and the fresh-clone contract (`bash _calisma/dev_bootstrap.sh &&` normal commit flow). Commit:

```bash
git add findings.md
git commit -m "docs: dev-bootstrap turu kaydi — fresh-clone kontrati kapali"
```

---

## Self-Review Record

- **Spec coverage:** three documented gaps (venv_z3, pptx, dashboard-next node_modules) → Task 1 provisions all three; smoke-test playwright guard already exists (`d396b8c` hardened the node-side crash) — no task needed for it; battery wiring + docs → Task 2.
- **Placeholder scan:** every code step carries complete file content or an exact command; no TBD/TODO/similar-to-task references.
- **Type consistency:** rc contract (0/1/2; `BOOTSTRAP OK|FAIL`) identical in constraints, Task 1 tests, and Task 1 script; pin strings byte-identical across test, script, and constraints.
