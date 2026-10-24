# Task Plan — leibniz2 session (2026-08-30 → 2026-10-04)

## ⚠️ STALE-PLAN NOTICE (2026-10-04, planning-with-files activation)
Phases 1–4 below were written for branch `reword-working` and the session that
ended 2026-09-19. **Phase 4 is marked `in_progress` but is two weeks stale** — its
decision items (a)–(d) refer to that session and were never carried forward. The
work they describe (PR #42/#50, reviewer dispatch, Candidate-1 grilling) is not
this branch's work. Read Phases 5+ for current state; treat Phase 4 as history,
not as an open work queue. `session-catchup.py` reported no unsynced context,
and all three plan files were clean against HEAD before this edit.

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

### Phase 1: Restore/persist planning context
**Status:** complete
### Phase 2: PR #42 CI triage + repair (superseded; closed at 5ab5196)
**Status:** complete

### Phase 3: 2026-09-18 multi-skill session
**Status:** complete
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

### Phase 4: Open decision items — SUPERSEDED (stale; see STALE-PLAN NOTICE)
**Status:** complete
- (a) Commit decision: **RESOLVED** — that session's surfaces landed.
- (b) Reviewer dispatch: **DROPPED** — not pursued on this branch.
- (c) VERIFY-001 (security review): **UNRESOLVED, deferred** — CSP still blocks
  SVG inline hover handlers; fix = addEventListener migration or script-hash.
- (d) Architecture Candidate 1 grilling: **SUPERSEDED** by the precommit_log
  seam work (commit 5ee5555) on this branch.

### Phase 5: Neon/Postgres live-state documentation
**Status:** complete
6 commits: 60f002e (live roles), 448cbc1 (migrate-dev data-loss warning),
287ccdf (restore-proven backup + 3 migration checksums). Backup verified by
restore onto a disposable branch; main untouched throughout.

### Phase 6: Neon pooled/direct split corrected for Prisma 7
**Status:** complete
Commit 923bfdc. `directUrl` is rejected by Prisma 7 (P1012, measured); split
moved into prisma.config.ts (CLI=direct) vs load.ts (runtime=pooled). Host
actually contacted proven live. Gate: test_trend_db_connection.py (10).

### Phase 7: dashboard-next dead-code purge
**Status:** complete
Commit 097b683. `noUnusedLocals`/`noUnusedParameters` were OFF, so 3 TS6133
defects (2 unused VariantProps, 1 dead `revalidate` param) accumulated while
`tsc --noEmit` stayed green. Flags enabled; gate test_dashboard_next_contract.py
(10 tests, mutation-verified).

### Phase 8: trend-db loader hardening
**Status:** complete
Commit ca118f9. Input validation, line-numbered parse errors, fail-closed before
any write, SIGINT/SIGTERM cleanup, message-not-stack errors.

### Phase 9: Open items
**Status:** in_progress
- (a) **Migration history still unrepaired.** Backup unblocks it; needs a user
  decision: single baseline + `migrate resolve` vs three faithful files.
  Rehearse on a throwaway branch, never main.
- (b) **`README.md` changelog row for ca118f9 is staged but uncommitted**
  (auto-staged by a pre-commit hook). Legitimate; needs landing.
- (c) `trend_service` / `trend_anon` still `rolcanlogin=false` — user deferred.
- (d) `trend_runs_daily` has no PK → Prisma rejects it as a model (P1012);
  deliberately hand-managed, documented.
- (e) **Orca cannot place agents on this worktree.** Registered as a folder
  workspace, but macOS TCC blocks Orca from reading `~/Desktop`, where the bare
  repo's gitlink points. Git is dead inside Orca terminals here. Needs a human
  permission grant; not fixable from the CLI.

## Next Step
Phase 9(a): decide the migration-history recovery shape (baseline vs three
files), then rehearse `prisma migrate resolve` on a throwaway Neon branch.
Everything else in Phase 9 is either a deferred user decision or a documented
environmental blocker.

## Decisions Made
- 2026-10-04: prettier must be run via `apps/dashboard-next/node_modules/.bin/prettier`
  (3.6.2), NOT root `npx prettier` (3.9.9) — the two disagree and the gate uses
  the former. Formatting with npx produced a file the gate rejected.
- 2026-10-04: Prisma 7 dropped `directUrl`; pooled/direct split implemented by
  consumer (config=CLI=direct, load.ts=runtime=pooled) rather than by two URLs
  in the schema. Verified by observing which host the CLI actually dialled.
- 2026-10-04: performance audit of preview.html produced NO code changes — every
  budget measured green (TTFB 1ms/800ms, 222KB/1.5MB). Skill forbids editing
  without a measured bottleneck.
- 2026-10-04: initial "13 image 404s" finding was DISCARDED as a measurement
  artifact — port 8000 was a stale Sep-29 server from `~/Desktop/leibniz2`; my
  own server never bound. Correct server returns 200 for all12.
- 2026-09-18: setup-pre-commit adapted to EXISTING chain (user-approved):
  no Husky (would seize core.hooksPath and silently bypass 47 hooks);
  format+typecheck added as local read-only fail-closed hooks with
  environment-missing SKIP semantics.
- 2026-08-30: keep _locate_opencode duplicated across the two modules.
- 2026-08-30: --no-verify only ever with explicit user authorization.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `orca worker-start --worktree new-child` → selector_not_found | 2 (incl. with `--repo`) | Documented in `--help` but rejected at runtime. Not a usage error. Worked around with an exact `id:<repo>::<path>` selector. |
| Orca terminal: `git` → "not a git repository" inside `/private/tmp/wtfaz4` | diagnosed | macOS TCC: `ls ~/Desktop` → "Operation not permitted" for the Orca app. Linked-worktree gitlink points into `~/Desktop`. Needs human permission grant. |
| Worker placed in wrong checkout (Orca clone on `feat/plist-info-line`, no `apps/`) | 1 | Worker asked a question instead of guessing; coordinator verified independently, replied with `/private/tmp/wtfaz4`. |
| Browser `preview_evaluate` timed out on every expression incl. `1+1` | ~6 | Machine load average 8–21. Abandoned browser-side CWV; reported server-side measurements only and declared CWV unmeasured rather than fabricating. |
| preview_server bind failed: `Address already in use` (port 8000) | 1 | A stale Sep-29 server owned 8000. All first-round measurements were invalid; re-measured on 8123. |
| `pterm run leibniz2 --default start.js` ran `install.js` instead | 3 | Selector ignored; `default_script` is `pinokio/install.js`. `pterm run` also blocked >240s, leaving a session with `ended_at: null`. Control plane then stopped answering (HTTP 000). Escalated to user. |
| pterm "not found" on the documented path | 1 | `~/.pinokio/config.json` has an absolute `home` (a real `/Users` path), NOT `~/.pinokio`. Config-derived path resolved pterm v0.0.25 correctly. |
| check-unit-tests pre-commit 25/110 failures | commit ea4a1dc..835510b | documented in docs/CI_GATE_TRIAGE.md; --no-verify (user-approved) |
| Working-tree session edits reverted by out-of-session action | 2026-09-18 | recovered from /tmp snapshot; see RECOVERY NOTE |
| pre-commit battery "2 failed" after recovery | framework runs tests against STAGED state (unstaged stashed away) | stage session files before battery; direct runs 14/14 OK |
