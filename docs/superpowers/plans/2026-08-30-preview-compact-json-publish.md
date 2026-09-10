# Compact-JSON Publish Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and publish the already-implemented compact-JSON serialization patch (3 handlers in `preview_server.py` + 4-test contract class in `test_preview_server.py`) as one commit on `feat/plist-info-line`, pushed to `origin`.

**Architecture:** The work is already implemented and verified in the working tree (uncommitted, `MM` on both files — this session's turns profiled the hotspot, TDD'd the `serve_latest` leg red-green, and simplified the tests to a shared `_serve` contract). This is therefore a *verification-and-publish* plan: re-run the gates fresh, stage exactly two files, commit in the repo's style, push, and confirm the remote hash. No new production code is written by this plan.

**Tech Stack:** Python 3 stdlib (`unittest`), `git`. Repo gates: `py_compile` (no typechecker exists), the 5-module unittest suite, 79-column line convention (character count — Turkish text is multi-byte, so byte-based checks false-positive).

**Spec:** This session's performance turn (measured: `indent=2` pretty-printing ~2.5× slower, ~20–30% more bytes on every SSE-cycle fetch), TDD turn (red-green for `serve_latest`), and contract-simplification turn (shared `_serve` helper; dead `except→500` branch removed). The implemented working-tree diff is the spec; this plan publishes it.

## Global Constraints

- Only two files may be staged: `_calisma/CIKTI/preview_server.py`, `_calisma/CIKTI/test_preview_server.py`. Both are `MM` — other threads' staged work shares these files; `git add <file>` is additive and safe. Never `git add -A`.
- Repo has no external formatter/typechecker; gates are `py_compile`, `unittest`, and the 79-column convention.
- Push to existing branch `feat/plist-info-line` → `origin`. No PR, no force-push, no branch switch, no config changes.
- Pre-commit runs a 43-gate local battery; a hook failure is a real finding — read it, don't bypass it.
- Known-unrelated issue: last verify run in `~/Library/Caches/com.freebuff/preview/history.jsonl` shows `verdict=FAIL, duration_s=300.07` (a 300s timeout). Out of scope here.

---

### Task 1: Fresh verification of the uncommitted patch

**Files:**
- Verify only (no modifications): `_calisma/CIKTI/preview_server.py`, `_calisma/CIKTI/test_preview_server.py`

**Interfaces:**
- Consumes: module globals `ps.HISTORY_PATH`, `ps.REFS_TREND_PATH`, `ps.LATEST` (monkeypatched by `TestServeHistoryTrendCompact` at `test_preview_server.py:1348`).
- Produces: evidence — `py_compile` exit 0; `Ran 138 tests ... OK`; `CHARS>79: 0`.

- [ ] **Step 1: Confirm the working-tree delta is exactly the expected patch**

Run:
```bash
cd <repo-root> && git diff --stat -- _calisma/CIKTI/preview_server.py _calisma/CIKTI/test_preview_server.py
```
Expected: `preview_server.py | 19 ++++----` and `test_preview_server.py | 86 +++++++++...` (94 insertions, 11 deletions). If numbers differ, STOP — another thread moved the files; re-read the diff before proceeding.

- [ ] **Step 2: Compile check**

Run:
```bash
cd <repo-root>/_calisma/CIKTI && python3 -m py_compile preview_server.py test_preview_server.py && echo "PY_COMPILE: OK"
```
Expected: `PY_COMPILE: OK`, exit 0.

- [ ] **Step 3: Run the focused suite (5 gate modules)**

Run:
```bash
cd <repo-root>/_calisma/CIKTI && python3 -m unittest test_preview_server test_preview_reload_smoke test_daemon_http test_dashboard_smoke test_k18_daemon 2>&1 | tail -3
```
Expected:
```
Ran 138 tests in ~13s

OK
```

- [ ] **Step 4: Line-length convention (characters, not bytes)**

Run:
```bash
cd <repo-root> && git diff -U0 -- _calisma/CIKTI/preview_server.py _calisma/CIKTI/test_preview_server.py | python3 -c "
import sys
n = 0
for raw in sys.stdin:
    if raw.startswith('+') and not raw.startswith('+++'):
        line = raw[1:].rstrip('\n')
        if len(line) > 79:
            n += 1
            print(len(line), repr(line[:60]))
print('CHARS>79:', n)
"
```
Expected: `CHARS>79: 0`. (Use this char-count form; `awk length()` counts bytes and false-positives on Turkish multi-byte chars.)

---

### Task 2: Commit as one unit

**Files:**
- Stage: `_calisma/CIKTI/preview_server.py`, `_calisma/CIKTI/test_preview_server.py`

**Interfaces:**
- Consumes: verified state from Task 1.
- Produces: one commit on `feat/plist-info-line` containing the two files' unstaged deltas.

- [ ] **Step 1: Stage exactly the two files**

Run:
```bash
cd <repo-root> && git add _calisma/CIKTI/preview_server.py _calisma/CIKTI/test_preview_server.py
```
Expected: no output. Additive on top of other threads' staged content — safe by design here.

- [ ] **Step 2: Confirm staged scope**

Run:
```bash
cd <repo-root> && git status --short | grep -v '^ ' | head -20
```
Expected: only files that were already staged before your action plus your two `M ` entries. If a file you did not stage appears newly staged (`A ` or `M `), STOP and investigate — do not unstage other threads' work.

- [ ] **Step 3: Commit**

Run:
```bash
cd <repo-root> && git commit -m "$(cat <<'EOF'
perf: compact JSON for /api/history, /api/refs-trend, /api/latest

Drop indent=2 from the three SSE-cycle endpoints (measured: pretty-print
~2.5x slower, ~20-30% more bytes per snapshot). Add TestServeHistoryTrendCompact
pinning the compact contract (200 + application/json + no literal newline)
with content assertions for all three handlers; remove the unpinned
except->500 branch from serve_refs_trend as contract-dead machinery.

🤖 Generated with Codebuff
Co-Authored-By: Codebuff <noreply@codebuff.com>
EOF
)"
```
Expected: commit created; the 43-gate pre-commit battery runs and passes. If a hook fails, read the finding — it is a real gate. Do not use `--no-verify` unless the failure is proven to come from another thread's staged content, and state that explicitly if you do.

---

### Task 3: Push and confirm remote state

**Files:**
- None modified.

**Interfaces:**
- Consumes: the commit from Task 2.
- Produces: `origin/feat/plist-info-line` at the new commit hash.

- [ ] **Step 1: Push the current branch**

Run:
```bash
cd <repo-root> && git push origin feat/plist-info-line
```
Expected: fast-forward push succeeds. If rejected as non-fast-forward, STOP — another thread pushed; fetch and re-evaluate. Never force-push.

- [ ] **Step 2: Confirm remote branch reached the commit**

Run:
```bash
cd <repo-root> && git rev-parse HEAD && git ls-remote origin refs/heads/feat/plist-info-line
```
Expected: both hashes identical.

- [ ] **Step 3: Report**

Report the commit hash, branch, remote, and Task 1's verification numbers (138 tests OK, py_compile OK, CHARS>79: 0).
