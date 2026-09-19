# Task Plan — leibniz2 session (2026-08-30 → 2026-09-18)

## RECOVERY NOTE (2026-09-18, pre-commit tour) — ROOT CAUSE CORRECTED 2026-09-19
Working-tree tracked modifications from this session were REVERTED to HEAD
~2026-09-18 20:09 (only tracked files hit — untracked surfaces intact,
staged set intact). Recovered by selective copy from
/tmp/repack_reuse/calisma (post-session snapshot of _calisma): preview_server.py,
preview.html, test_preview_server.py, test_coordinator_loop.py,
test_z3_slide_gallery.py, check_unit_tests.list; .gitignore entries re-applied
from session record; plan files (this file, findings.md, progress.md) re-written
from session memory. Recovery proven: direct runs 14/14 in touched modules.

**ROOT CAUSE (systematic-debugging tour, 2026-09-19 — proven, not speculated):**
NOT an out-of-session/other-thread action. pre-commit's own
staged_files_only.py stashes unstaged deltas to a patch file and runs
`git checkout -- .`, restoring them only in a finally-block. A process death
inside that window (SIGKILL/harness child-reaping) skips the finally → tree
reverts exactly as observed: `checkout -- .` resets tracked worktree files to
the INDEX (staged set preserved ✓), untracked files untouched ✓. Reproduced
minimally in a scratch repo (kill at context-enter → loss; `git apply` of the
patch → full recovery). The loss-bearing patch (patch1789754982-84993,
2026-09-18 20:09:42) matches the incident window and carries the lost session
content incl. the moment-snapshot of the plan files — archived at
_calisma/CIKTI/recovery_patches_20260918/. Patch files are NEVER auto-deleted
by pre-commit (~170 orphans had accumulated since Aug 17; cache cleaned
2026-09-19, both incident patches kept).
PROCESS RULE: never let the harness kill a pre-commit run mid-flight; use
generous timeouts; if a revert is ever found, look for
~/.cache/pre-commit/patch* FIRST — it is the recovery artifact, not evidence
of an external actor.

## Goal
Persist session context for the leibniz2 repo (branch `reword-working`, PR #50
open, HEAD e787e9a); track this session's completed surfaces and open decision
items (commit, reviewer dispatch, Aday-1 grilling).

## Phases

### Phase 1: Restore/persist planning context — complete
### Phase 2: PR #42 CI triage + repair — complete (superseded; closed at 5ab5196)

### Phase 3: 2026-09-18 multi-skill session — complete
- Landing page (image-first, a11y 28 PASS) · MCP server (read-only, smoke E2E)
- Security headers + CSP nonce · load_history cache (do_GET −63%) ·
  test-isolation repairs (shuffle-audit 3 leak families, seeds 42/7/13 green) ·
  pptx pilot export (validate PASSED) · trend-db Prisma-7 skeleton
  (validate/generate PASS, 42-col model incl. refsBySource gap-fix) ·
  reproducible-PDF re-audit (verify PASS, repack reuse byte-identical) ·
  ruflo/rust/remotion/commit-request tours (findings recorded; no mutations) ·
  security review of session surfaces (0 high-confidence; VERIFY-001 CSP-hover)
- Post-tour: pre-commit chain adapted (setup-pre-commit): 47→49 hooks —
  check-prettier-format + check-dashboard-typecheck; .prettierrc (skill
  defaults) at repo root; prettier in dashboard-next devDeps; JS/TS/JSON
  surfaces normalized; both gates proven live (OK/FAIL/SKIP paths).

### Phase 4: Open decision items — in_progress
- (a) Commit decision: session surfaces still uncommitted (9 tracked-file
  changes + untracked surfaces; see progress.md). RECOVERY NOTE applies:
  stage/commit promptly to prevent repeat reverts.
- (b) Reviewer dispatch: prepared at /tmp/review_brief.md; blocked on
  codex quota (resets Sep 22 07:42) / claude login / ruflo API key.
- (c) VERIFY-001 (security review): CSP blocks SVG inline hover handlers —
  fix = addEventListener migration or script-hash; then real-browser check.
- (d) Architecture Candidate 1 grilling — needs user.

## Next Step
Commit decision (a) first: tree recovered but uncommitted; stage this
session's files and land grouped commits (staged test_coverage_report.py +
README.md belong to another session — coordinate before including).

## Decisions Made
- 2026-09-18: setup-pre-commit adapted to EXISTING chain (user-approved):
  no Husky (would seize core.hooksPath and silently bypass 47 hooks);
  format+typecheck added as local read-only fail-closed hooks with
  environment-missing SKIP semantics.
- 2026-08-30: keep _locate_opencode duplicated across the two modules.
- 2026-08-30: --no-verify only ever with explicit user authorization.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| check-unit-tests pre-commit 25/110 failures | commit ea4a1dc..835510b | documented in docs/CI_GATE_TRIAGE.md; --no-verify (user-approved) |
| Working-tree session edits reverted by out-of-session action | 2026-09-18 | recovered from /tmp snapshot; see RECOVERY NOTE |
| pre-commit battery "2 failed" after recovery | framework runs tests against STAGED state (unstaged stashed away) | stage session files before battery; direct runs 14/14 OK |
