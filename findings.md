# Findings

## Session 2026-09-18 — new facts (multi-skill marathon)

Session surfaces (all verified live; see task_plan.md Phase 3): landing,
MCP server, security headers + CSP nonce, load_history cache, test-isolation
repairs, pptx pilot, trend-db Prisma-7 skeleton, reproducible-PDF re-audit,
pre-commit chain adaptation (47→49 hooks). Key lessons below.

### Working-tree revert incident + recovery (pre-commit tour)
- Out-of-session action reverted ALL tracked-file modifications to HEAD
  (preview_server.py lost cache+headers, test files lost isolation repairs,
  .gitignore lost ignore-entries, plan files reverted to Aug 30 state).
  Untracked surfaces and the staged set were untouched — signature of
  `git restore/checkout .`-style action, not a clean (our-session commands
  touched none of these files; branch/HEAD unchanged at e787e9a).
- Recovery: selective copy from /tmp/repack_reuse/calisma — the
  reproducible-pdf tour's full _calisma snapshot (taken AFTER all session
  work): preview_server.py (2022 lines, _history_cache + CSP present),
  preview.html, test_preview_server.py, test_coordinator_loop.py,
  test_z3_slide_gallery.py, check_unit_tests.list. .gitignore entries
  re-applied from session record; plan files re-written from session memory.
- Framework gotcha learned: `pre-commit run check-unit-tests` runs tests
  against the STAGED state (unstaged changes stashed away mid-hook) — a
  just-recovered unstaged tree fails the battery while direct runs pass
  (14/14). Stage session files before trusting battery results.
- LESSONS: (1) commit session work promptly in shared checkouts;
  (2) /tmp full-directory snapshots are a real recovery layer;
  (3) the failure surfaced THROUGH the new battery gate working as designed.

### Harness/runtime lessons
- Freebuff terminal harness reaps ALL child/detached processes when a SYNC
  command ends (nohup/setsid/double-fork/launchd/bg-node all reaped;
  Remotion Studio proved it). Only in-window validation works: representative
  stills (`npx remotion still --frame=N`), in-process HTTPServer profiling,
  sync probes. Orca PTY terminals are the sole persistent-process surface
  but their prompt-send path is mutation-blocked (below).
- launchctl note: `launchctl list | grep leibniz` matches
  `com.freebuff.preview-leibniz2` — Freebuff's own preview_server (pid 951,
  port 8000), not an agent label.
- Remotion tooling writes webpack dev-cache into CWD when launched from repo
  root; run it from the project dir. (Residue .cache/ found + removed.)

### Code-review dispatch feasibility (requesting-code-review tour)
- Orca orchestration mutation layer PERMANENTLY BROKEN in this runtime:
  run-create and terminal send fail with "Mutation receipt ledger metadata is
  missing"; documented recovery (--retry-request <id>) re-issues the exact
  mutation and returns the SAME error (self-closing loop). Read endpoints
  (status, terminal list/create/close) work.
- Agent-CLI attempts with the prepared brief (/tmp/review_brief.md):
  claude -p → not logged in; codex exec → default model gpt-6-astra needs
  newer CLI (0.151.0 latest installed, single self-managed release);
  gpt-5.1-codex rejected on ChatGPT accounts; default-model run hit usage
  limit (resets Sep 22 2026 07:42). Review dispatch UNAVAILABLE; brief
  reusable: `codex exec -s read-only -C <repo> --skip-git-repo-check - < /tmp/review_brief.md`

### Ruflo recon (ruflo skill)
- Machine-level state (~/.ruflo) but repo ruflo-free. Runtime probe in /tmp:
  ruflo v3.42.4 (skill says 3.31.0 — drift), doctor 10/18 warnings.
  Decision-relevant: "No API keys found" (agent_spawn reviewer dispatch has
  no credential); plugin registry signature verification FAILED → demo
  registry fallback (treat as untrusted). Command drift:
  discover-plugins → plugins list. Repo-init = user decision.

### Rust surface: zero (rust-async-patterns skill)
- Three-source proof: git-tracked (.rs/Cargo.toml/rust-toolchain) = 0;
  disk scan = 0; cargo/rustc/rustup absent. Skill unexercised-by-absence
  (pinokio-precedent). Tectonic is Rust-based but unrelated to async patterns.

### Remotion pilot (remotion-best-practices)
- /tmp/leibniz-chain-video: data-driven LeibnizChain comp (1280x720@30, 760f,
  6 scenes; history.jsonl dates + frozen evidence cards). tsc clean; 5
  stills rendered via real bundler (unique md5 mid-frames). Studio reachable
  (HTTP 200) but harness reaps it; user opens it themselves:
  `cd /tmp/leibniz-chain-video && npx remotion studio --no-open`

### Reproducible-PDF delivery chain re-audit
- verify_delivery verdict PASS (K0–K7, 0 findings); qpdf rerun 3/3 distinct
  (frozen NON-DETERMINISTIC verdict holds); repack reuse-rule proven in /tmp
  copy: consecutive repacks byte-identical (e30ae632…), --verify ALL PASS.
  Migration docs in place (TeXLive + SOURCE_DATE_EPOCH, sde_experiment/).
- Sidecar facts: raw 74b2cdbd… unchanged since V5l; frozen record byte-stable.

### Security review of session-touched surfaces
- Verdict: 0 high-confidence vulnerabilities (data-flow-researched):
  run-stdout ts-sanitization traversal-proof, argv-only subprocess,
  Host/Origin-allowlisted POSTs + timing-safe token, no CORS (same-origin),
  tight CSP (default-src none, no unsafe-inline/eval in script-src), no
  hardcoded secrets in changed surfaces, mcp urlopen target server-controlled.
- VERIFY-001 (fail-closed functional loss): CSP script-src lacks
  'unsafe-inline' and nonces do NOT cover inline event-handler attributes →
  SVG hover tooltips injected via innerHTML (preview.js ~652) blocked under
  CSP; fix = addEventListener migration or script-hash + browser check.
- LOW notes: escapeHTML omits quote chars (no attribute-context attacker
  data today); style-src 'unsafe-inline' deliberate.

### Perf/testing facts (early tours)
- load_history cache: mtime_ns+size key, atomic tuple swap, list-copy return;
  do_GET cumtime 0.051→0.019s (−63%); json.loads per request-window 1500→0.
- Shuffle-audit (test isolation): seeds 42/7/13 exposed 3 leak families
  (LATEST['layers'], GATES via _patch_commands, SSE/STREAM clients) — all
  repaired; seeds green; 2323-test suite OK (skipped=12).
- python3.11 lives at ~/.local/bin (validate.py QA-venv pattern).

## Repo facts (verified 2026-09-09, triage snapshot for 091635c)
- PR #42 era: 4 root causes closed at 5ab5196; battery gate history in
  docs/CI_GATE_TRIAGE.md; performance audit of 2026-08-30 unchanged.

### shadcn-ui tour (2026-09-18, dashboard-next)
- Real defect found+fixed: dashboard-next used Tailwind-style utility classes
  (space-y-6, rounded-lg, animate-pulse...) with NO Tailwind installed —
  build CSS was 279 B of :root vars only, zero utilities; pages rendered
  without spacing/borders/grid. Fix: tailwindcss@4 + @tailwindcss/postcss,
  postcss.config.mjs, `@import "tailwindcss"` in globals.css → build CSS
  9021 B with all consumed utilities present.
- shadcn init completed non-interactively (`-d` defaults = base-nova preset,
  Base-UI primitives; interactive preset prompt hangs the harness): produced
  components.json, components/ui/button.tsx, lib/utils.ts (cn), extended
  globals.css with full shadcn theme variables (@theme inline).
- Init side-effect CAUGHT: shadcn overwrote existing :root --muted/--accent/
  --border hex values with its neutral oklch defaults (--accent would have
  become near-white, breaking --accent consumers: selection color, links).
  Restored original hexes; shadcn namespace (--background, --primary...)
  kept separate alongside app tokens.
- First consumer wired: page.tsx links now use buttonVariants({variant:
  "ghost"}) via cn(); live smoke (next start + curl): home/trend 200,
  utility classes + inline-flex/buttonVariants classes present in served HTML.
- Gates: tsc 0, prettier clean, build green, check-prettier-format covers
  new shadcn files (OK), typecheck hook OK.
- Note: apps/dashboard-shadcn (tracked, e6572d1) does NOT use shadcn despite
  its name — hand-rolled semantic CSS + design-system/tokens.css import;
  no components.json/tailwind. README cross-reference in dashboard-next
  explains the two-dashboards split.

### stripe-best-practices tour (2026-09-19) — domain mismatch, mirror audited instead

- **"stripe" in this repo ≠ Stripe payments**: it is a design-token mirror,
  `design-system/stripe/` (verbatim HDS extraction from stripe.com,
  2026-09-08). Zero payment surface: no SDK (node/py/CLI not installed),
  no webhook/checkout/billing code, no `sk_`/`rk_` key patterns anywhere.
  Skill's payment-domain references (Checkout/Connect/Tax/Treasury) had no
  question to answer — none loaded, no code written.
- Mirror audited live and healthy: `check_stripe_tokens.py` → OK (710
  `--hds-*` tokens verbatim vs raw.css, tokens.css + tokens.json in sync;
  15 groups, `source` provenance present). Sibling mirrors linear (398) and
  primer (2051) also pass their own gates.
- **Consistency fact**: none of the four brand mirrors (stripe/linear/
  primer/vercel) is wired into the pre-commit chain — their check scripts
  exist but are not hooks. Stripe's absence from the chain is the existing
  design decision, not an omission introduced this session.
- **Zero consumers**: no `--hds-*` usage outside `design-system/` (repo-wide
  grep). The mirror is a dormant reference library. `dashboard-next` imports
  `shadcn/tailwind.css` (npm preset), NOT the repo's generated
  `design-system/tailwind.css` bridge — root `:root` copy drift vs
  tokens.css remains gate-free for dashboard-next (known open angle from
  shadcn tour).

### supabase-postgres-best-practices tour (2026-09-19) — trend-db rule audit

- Live surface: `apps/trend-db` skeleton (Prisma 7 + postgresql, Neon
  pooled/direct contract). Migrations intentionally absent — waiting on
  user `neon login`; rule fixes applied BEFORE first migration = free window.
- **schema-data-types fixes** (evidence-based, not theoretical): live
  history.jsonl ts values are offset-bearing microsecond ISO-8601
  (`2026-09-18T22:12:13.116918+00:00`) → `ts DateTime @db.Timestamptz(6)`
  (old `timestamp(3)` dropped the offset AND truncated microseconds — real
  loss). `budget_usd/limit` → `Decimal(10,2)` (money=numeric rule; live
  data max 2 decimals).
- **data-batch-inserts fix**: loader's per-row `await upsert` loop (1
  round-trip/row) → `createMany` chunks of 500 with `skipDuplicates: true`
  = `ON CONFLICT DO NOTHING` (skill data-upsert insert-or-ignore pattern;
  also covers ts-unique conflicts, not just sourceRowSha256). Counters now
  report actually-inserted rows, not processed.
- Already compliant (no change): composite index `(verdict, ts DESC)`
  equality-first column order; snake_case mapped identifiers; atomic
  conflict handling.
- Drift-guard contract preserved: loader keeps literal `row.<key>` reads
  (test_trend_db_contract requirement). Suite 8/8 OK; prisma validate +
  generate OK (client 7.10.0 regenerated; generated/ is gitignored by
  design); tsc strict single-file pass; battery 138/138.

### systematic-debugging tour (2026-09-19) — revert incident ROOT CAUSE proven

- **Prior diagnosis corrected.** The 2026-09-18 working-tree revert was NOT
  an out-of-session/other-thread action. Root cause (proven, not inferred):
  pre-commit `staged_files_only.py` stashes unstaged deltas to
  `~/.cache/pre-commit/patch<epoch>-<pid>`, runs `git checkout -- .`, and
  restores via `git apply` ONLY in a finally-block. Process death inside the
  window (SIGKILL / harness child-reaping) skips the finally → tracked
  worktree files reset to the INDEX. Signature matches exactly: staged set
  preserved, untracked untouched, no stash entry, no reflog entry.
- **Phase 3 proof** (scratch repo, control group included): kill at context
  enter → precious unstaged delta lost from tree, patch file intact carrying
  it; `git apply` → full recovery. Clean-exit control → self-restored; and
  pre-commit NEVER deletes its patch files (source has no unlink) → ~170
  orphans accumulated Aug 17 → Sep 19 (all sizes 4B–1.1MB).
- **Incident forensics**: loss-bearing patch = patch1789754982-84993
  (2026-09-18 20:09:42, 38 kB) + follow-up patch1789755439-10960
  (20:17:19) — timestamps match the setup-pre-commit battery runs during
  which the incident was discovered. Both archived at
  `_calisma/CIKTI/recovery_patches_20260918/` (patch #1 also carries the
  moment-snapshot of the reverted plan files — diff-auditable against the
  session-memory rewrite).
- **Cache hygiene**: all orphan patches deleted 2026-09-19 (only the two
  incident patches kept, then archived). LESSON for future incidents:
  check ~/.cache/pre-commit/patch* FIRST — newest patch = recovery
  artifact + incident timestamp; it is not evidence of an external actor.
- PROCESS RULE (permanent): never let the harness kill a pre-commit run
  mid-flight (generous timeouts); batch related `git add` + hook runs.
- Earlier "Restored changes from patch…" log lines are the NEXT run's own
  stash-restore, not self-healing of old orphans (source-verified).

### tailwind-design-system tour (2026-09-19) — token-chain wired + gate extended

- dashboard-next now imports the GENERATED bridge `design-system/tailwind.css`
  (Tailwind v4 @theme over tokens.css); its copied :root dashboard-namespace
  deleted (single source of truth); shadcn/UI oklch namespace kept separate
  (name-intersection with tokens.css :root verified EMPTY before deletion).
- Gate extension (check_tokens.py, contracts 5+6): (5) dashboard-next
  globals.css must carry a real `@import` of design-system/tailwind.css
  (comment-mention alone FAILS — caught and hardened during this tour) and
  must not shadow any tokens.css :root name; (6) bridge :root must equal
  tokens.css :root verbatim (regenerate message included). Five paths proven
  in tmp fixtures: OK + import-removal + comment-only + --bg shadow +
  hand-edited bridge → FAIL. test fixture (_tmp_repo) now copies the bridge.
- **Real defect found in the generator**: the bridge EMBEDDED
  `@import "tailwindcss"`; bare specifiers resolve from the bridge's own
  directory (design-system/ — no tailwindcss there), so every consumer
  following the README's two-import contract got
  "Can't resolve 'tailwindcss'" (Next build rc=1). Fixed in
  generate_tailwind.py (bridge = theme layer only) + regenerated
  (8.2 kB); globals.css now uses the documented two-import order
  (tailwindcss, then bridge).
- Chain proof: build 28.4 kB CSS with bridge vars (--paper-ink,
  --header-start, --tint-ok-bg) + animate-pulse + space-y-6; live smoke
  (next start :4321): home 200, served CSS 200 carrying bridge tokens.
  tsc clean, prettier clean, battery 138/138.

### tdd tour (2026-09-19) — check-precommit-orphans gate, red→green

- Seam (user-approved): the gate's CLI — exit code + stdout; subprocess
  tests via PRE_COMMIT_HOME fixture (real cache never touched by tests).
- Loop kept vertical: cycle 1 = one failing test (old patch → exit 1 +
  file named + recovery guidance) → minimal gate implementation → green;
  remaining contract slices pinned after (fresh/empty/missing → 0, strict
  24h+1s boundary, multiple orphans all named). 6/6 green.
- One harness defect during RED: py3.9 union syntax in the new test file
  (fixed in test, not implementation).
- Wired as hook 19 (49→50 hooks): always_run, read-only, fail-closed;
  header inventory + manifest via sync --update (EKLENDİ).
- Framework-level proof: clean cache → Passed; planted 32h-old patch →
  gate blocked with named file + recovery protocol; planted patch removed.
- Live justification already visible: 4 fresh orphan patches appeared in
  ~/.cache/pre-commit within ~40 min of yesterday's cleanup (today's
  pre-commit runs) — the window exists and re-arms; gate watches it.
- Battery: 139 test files PASS (was 138).

### test-driven-development tour (2026-09-19) — known-incident fingerprint, red→green

- Second red→green cycle on the approved CLI seam: orphan patch whose
  content is byte-identical to the archived 2026-09-18 incident patch now
  triggers a KNOWN-INCIDENT warning naming the archived file and the
  `git apply` recovery path. RED verified with the expected failure
  (marker missing, not error); GREEN 8/8. Counter-test pins that unknown
  orphans stay unmarked.
- Live-cache hygiene: both incident patches were still sitting in
  ~/.cache/pre-commit (a time-bomb: they would cross the 24h window in
  ~17h and start blocking commits while uncommitted work remains).
  sha256-verified identical to the repo archive copies → live copies
  deleted, archive remains as the fingerprint source.
- Battery: 139 files PASS (fingerprint suite runs inside
  test_check_precommit_orphans.py).

### typescript-advanced-types tour (2026-09-19) — escape hatches → real types

- Inventory: both session TS surfaces scanned; dashboard-next clean
  (zero any/as-casts outside generated ui/). trend-db loader had two
  escape hatches: `data: … as never[]` (createMany) and `json(): unknown`
  helper.
- Compiler-as-test (skill's type-testing spirit): annotated the batch with
  the GENERATED input type (`TrendRunCreateManyInput`) and removed the
  cast — tsc red (TS1361 Prisma-as-value, fixed by value-import), then
  green, proving structural compatibility: every loader field fits the
  generated contract, `InputJsonValue` allows null at member positions,
  only root-null needs `NullableJsonNullValueInput`.
- `json()` rewritten as a RECURSIVE TYPE GUARD (isJsonInput, skill rule
  "type guards instead of assertions"): root-null → `Prisma.DbNull`
  (behavior-faithful: old loader's JS null = SQL NULL; DbNull/JsonNull
  ambiguity documented in-file); non-JSON values now throw with kind info
  instead of flowing through unchecked; single residual `as` remains only
  on the post-guard narrowed value (structural assert, compiler-verified
  by the annotated batch).
- Runtime-semantics note: loader source is JSON.parse, so NaN/undefined/
  functions can never reach the guard; guard's accept-set is exactly the
  JSON value set (member-null included), verified against the generated
  InputJsonValue definition (client.d.ts:1462-1490).
- Gates: tsc strict green, prettier gate green on load.ts, prisma
  validate green, drift-guard suite 8/8, battery 139/139.

### using-git-worktrees tour (2026-09-19)
- Step-0 detection ran with commands (not eyeballing): normal checkout
  (GIT_DIR == GIT_COMMON, no superproject); 6 stale /private/tmp worktree
  records pruned.
- Decisions (user-confirmed): commit session work BEFORE branching (worktree
  from HEAD must contain it), then `.worktrees/work/2026-09-19`.
- Session work committed as 07e22aa (gates+recovery-archive+plan-files, 27
  files) and d1cbfb2 (apps surfaces+contract tests, 53 files).
- Commit attempts hit the pre-commit stash window twice: unstaged README
  delta made the battery run against the staged-only tree (2 test files
  failed there). Process rule re-proven: zero the unstaged-tracked delta
  before committing. Second window closed clean ("Restored changes" path
  OK; residue patch removed after reverse-check).
- Gates caught real residue in NEW files: absolute /Users/... paths in
  _calisma/mcp (server.py, README.md → ~/ rewritten) and prettier-noncompliant
  landing/refs/analysis.json — chain earned its keep on commit day.
