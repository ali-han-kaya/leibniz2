# Review dispatch — PR #42 retrospective

<!-- Arşiv: çalışma tarihi 2026-08-31, depoya alındı 2026-09-27. Makineye özgü
     `/Users/<kullanıcı>/…` yolları taşınabilir karşılıklarına (`~…`, `<repo>…`)
     normalize edildi; içerik dışında bir şey değişmedi (check-absolute-paths). -->

**Revision 2 — 2026-09-13.** Range and known-issues corrected. Revision 1 targeted
base `7333a55…` → head `5e3211d…` and described "12 commits, 182 files"; both facts
were stale, and two of the premises it inherited had to be rejected before the range
could be written at all (below).

## Why this revision exists

- **PR #42's head is `9bcd753`, not `091635c`.** The PR merged on 2026-09-10T21:46:13Z
  as `e6572d1`; `headRefOid` is frozen at `9bcd753536c69064bdab343a8bb1eb16e0f3059e`.
  There is no future head to review — #42 is history, so this is a retrospective.
- **`091635c` is a dangling duplicate, not a head.** No branch contains it and it is
  not an ancestor of `origin/main`. Its content is fully subsumed: `origin/main`
  already carries the identical venv-guard entry (`check-doc-job-sync`,
  `.pre-commit-config.yaml:386-390`) and `test_doc_job_sync.py` is blob-identical
  (`21c6cf7f40`). Reviewing it would be a no-op.
- **The previously recorded head `5e3211d` was a worktree's detached HEAD**, never a
  PR head.

## REVIEW TARGET (verified)

| Field | Value |
|---|---|
| Base | `7333a55af4a2b965811fbe523e51f2d57df444f5` (origin/main at branch point) |
| Head | `9bcd753536c69064bdab343a8bb1eb16e0f3059e` (PR #42) |
| Merge commit | `e6572d1e713a5c6f17112fea112ca34d979bed78` |
| Size | 81 commits · 262 files · +32,570 / −2,428 |
| PR state | MERGED |

Live carriers of the same work, still open and reviewable (this is where a *forward*
review has value, since #42 is already in `main`):

| PR | Branch | State |
|---|---|---|
| #47 | `land/post42-residual` | CLEAN |
| #46 | `docs/coe-audit-table` | UNSTABLE |
| #45 | `feat/plist-info-line-followup` | CLEAN |
| #41 | `pr/bf506c0` | DIRTY (untouched since 2026-08-27) |

## DESCRIPTION

Verification-gate hardening, dashboard perf/security, and delivery-reproducibility
work for the leibniz2 formal-verification repo, delivered as PR #42:

1. **Reproducibility gates** — tectonic/`SOURCE_DATE_EPOCH` PDF workflow, K6 PDF-skill
   reuse, K21 SDE, delivery repack + zip-lineage drift gate (K14) and registry resync.
2. **verify_mcp server + image** — MCP server, Dockerfile, `response_format` enum.
3. **Live dashboard server** (`_calisma/CIKTI/preview_server.py`) — compact JSON
   payloads, bearer auth + Host/Origin guard, graceful shutdown, atomic sidecar writes,
   30 s trend cache, `/api/trend` merge, View Transitions.
4. **Dashboard API + atomicity tests** — `/api/*` method contract, persist-layer
   atomicity + 8-thread hammer, POST-only `/api/run-now`.
5. **Mirror sync atomicity** — same-dir tmp+mv, restored copy path, clone-safe
   `git ls-files` sourcing for `check_mirror_coverage.py`.
6. **Sidecar wiring + verdict binding** — gates consume required sidecars, PR-comment
   inputs, atomic sidecars, budget-gate fail-closed.
7. **CI hardening** — `if: always()` install steps, K12 plist scenario, plist
   self-heal, fresh-clone smoke job, K10 composite action, Lean gating.
8. **Repo-wide guard layer** — atomic-write guard, gate fail-closed meta-guards,
   dependency-closure meta-test for `check_unit_tests.list`.
9. **Docs/changelog** — `gen_changelog.py --prune`, review compilation + freshness.

## Known issues (verified at revision 2 — do not re-derive, confirm or refute)

Flagged for the reviewer as *candidate* findings with their evidence. None of these
blocked the #42 merge; the first four are the ones a forward fix would target.

1. **`_trusted_request()` is wired to exactly one route.**
   `preview_server.py:44` defines the Host/Origin guard; it has a single call site,
   `trigger_run_now()` at `:1364`. `do_GET` (`:1302`) dispatches straight into handlers,
   `_send` (`:1276`) adds no check, and there is no `handle`/`handle_one_request`
   override. Every read route — `/api/history`, `/api/latest`, `/api/run` (SSE),
   `/api/run-stdout`, `/api/trend`, `/api/refs-trend` — is unguarded, so the
   DNS-rebinding scenario the guard exists to stop applies to reads while the POST that
   merely *starts* a run is the protected one.
2. **`/api/run-now` TOCTOU.** `trigger_run_now` acquires `VERIFY_BUSY`
   non-blocking, releases, then spawns the thread (`:1359-1383`); `run_verify`
   (`:524`) re-acquires and silently returns `False` when busy. Two racing POSTs both
   get `200 {"status": "started"}` while only one run happens.
3. **Duplicated SSE keepalive loop, already drifted.** `serve_run_stream`
   (`:1460-1468`) and `serve_sse` (`:1762-1776`) hold near-identical
   `q.get(timeout=SSE_POLL_TIMEOUT)` loops. Loop B maintains `last_keep` (`:1763`) —
   assigned twice, never read.
4. **Compact-JSON contract only half-applied.** `separators=(",", ":")` is present at
   `:1188, :1482, :1520, :1591, :1738, :1756` but absent from `serve_refs_trend`
   (`:1496` and its `:1489` fallback), `serve_override_trend` (`:1535`) and
   `serve_run_history` (`:1563`) — the three largest payloads. Both trend docstrings
   claim "compact JSON olarak döndür" while calling plain `json.dumps`.
5. **`check-bibliography-sync` fails on any `origin/main`-based tree.**
   `.pre-commit-config.yaml:316`, `always_run: true`. Verified at this revision:
   on `origin/main` the gate exits **1** (entry 45 Popkin page range, entry 48 Priest
   subtitle); on this branch's tip `512be11` the same gate exits **0**. Consequence:
   a worktree based on `main` cannot commit through its own pre-commit chain until the
   corrected PDF lands. This is why landing branches are stacked on #45.
6. **Five PR-only jobs skip on `push` by construction** (guard
   `github.event_name == 'pull_request'`): `budget-comment`, `label-gate`,
   `label-gate-p1`, `commit-msg-gate`, `manifest-comment`. No push can turn them
   green; only a PR event can.
7. **Dispatch itself is blocked on this runtime** — see below. This is environmental,
   not a repository defect.

### Verified strengths (for the reviewer to test, not assume)

- `_write_atomic()` (`:343-365`): `mkstemp` in the destination directory, write
  through the fd, `os.replace`, unlink-on-failure — torn reads impossible.
- Bearer auth (`:1373`): `hmac.compare_digest`, scheme checked before token, 401 +
  `WWW-Authenticate`.
- Method contract: `do_GET` → `_reject_method()` (`:1318-1319`) gives 405 +
  `Allow: POST` for `/api/run-now`.
- SSE clients removed under `LOCK` in `finally` in both loops — no queue leak on
  disconnect.
- Commit-msg gate is genuinely fail-closed: eval'd exactly as the workflow does, a
  **missing sidecar calls `setFailed` once**, malformed JSON calls it once, violations
  call it once, and only a clean present sidecar passes.

### Out of scope

Stylistic preferences, and anything already recorded as fixed in the `main` changelog.

## Dispatch

Intended: a `general-purpose` code-reviewer subagent, read-only on this checkout, no
nested spawning, filling `~/.agents/skills/requesting-code-review/code-reviewer.md`
(the template is present on disk). Report shape: **Strengths / Issues (Critical /
Important / Minor) / Recommendations / Assessment (Ready to merge? Yes | No | With fixes)**.

**Current status: NOT DISPATCHED — blocked at three independent points** (verified
2026-09-13 on Orca 1.4.199, runtime `f8aa30d2-0977-41ac-9465-abaab6b88eeb`, `ready`
/ `connected`):

1. `orca orchestration run-create` → `runtime_error: Mutation receipt ledger metadata
   is missing` (attempt receipt `3df72704-ce02-40c0-b170-6b20ab0db68b`; the request
   never landed — `request-show` reports `state: "absent"`). No Run ⇒ no task ⇒ no
   dispatch.
2. `orca account list` → `claude.accounts: []`, `codex.accounts: []`. `worker-start
   --agent <id>` has no managed account to launch.
3. The only live terminal (`term_a8faa48a-…`, worktree `l2` @ master) is a **bare zsh
   prompt**, not an agent TUI — there is nothing to inject a review into.

Until 1–3 clear, the review has to be run **inline by the coordinating agent** against
the target above. Per `AGENTS.md:27`, this is an environment limitation, not evidence
that the repository launcher is broken.
