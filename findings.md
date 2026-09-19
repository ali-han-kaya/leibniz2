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

### worktree baseline (2026-09-19, work/2026-09-19)
- Fresh-worktree battery caught a clone-consistency gap the main checkout
  hid: test_pptx_export crashed at module level (setUpClass check=True)
  because _calisma/pptx/node_modules is gitignored. Hardened: failed
  generator run records a skip reason (rc!=0 → SKIP with last stderr
  line) instead of a module-level error; structural test skips cleanly.
  Both paths proven live: pre-npm-ci SKIP (1 skipped), post-npm-ci real
  build (160 kB pptx) + structural OK. Battery 139/139 PASS in worktree.

### vercel-composition-patterns tour (2026-09-19, work/2026-09-19)
- Surface: dashboard-next on React 19.2 → react19 rules in scope; inventory
  clean of forwardRef/boolean-props/render-props. Two real findings applied:
  1) patterns-explicit-variants: PASS/FAIL verdict and p0>0/p1>0 cell tones
     moved from boolean ternaries to cva variants (verdictVariants,
     cellVariants).
  2) Token bond: every hex literal in app/ (10 distinct, all byte-equal to
     bridge tokens) replaced with semantic utilities (text-ok/err/warn/
     accent/muted, bg-surface/surface-raised/bg, border-border,
     bg-tint-err-bg); shadcn slots --primary/--primary-foreground/
     --destructive now reference repo tokens (--accent/--on-accent/--err)
     in :root and .dark — Button variants inherit single-source colors.
     error.tsx raw button replaced with Button primitive (destructive).
- Gates: tsc OK, prettier OK, build OK (28,378 B CSS, 7/7 semantic
  utilities present), live smoke home+trend 200, check-design-tokens OK
  (dashboard-next bridge contract included). tsx hex literals: 0.

### vercel-react-best-practices tour (2026-09-19, work/2026-09-19)
- 8-category pass over dashboard-next: bundle (direct imports, no barrels),
  async (single-await pages, existing Suspense boundary), rerender/client
  (single hookless client component) already clean.
- Applied server-cache-react: getLatest/getTrend wrapped in React.cache().
  Rationale: fetch request-memoization does not apply to cache:no-store
  requests; the wrapper gives per-request dedup for shared seams. Proven
  live: two VerdictCard consumers on one page + no-store fetches produced
  exactly 1 upstream /api/latest hit (counting upstream server probe);
  probe page edit reverted, processes cleaned.
- Applied rendering-conditional-render: {latest.ts && (...)} -> explicit
  ternary in VerdictCard.
- Gates: prettier, tsc, final build all green.

### vercel-react-native-skills survey (2026-09-19)
- Zero RN/Expo surface, proven: no react-native/expo/@expo imports
  (module-specifier word-boundary search; an earlier broad substring
  scan false-positived on "export" in 3 files — lesson: search module
  specifiers, not substrings), no RN deps in any package.json
  (inventory: next/react-dom web, vite web, none), no expo/metro/
  babel config, no ios/android dirs, no capacitor/ionic/tauri/native
  -script neighbors. Skill rules (FlashList, Reanimated, expo-image,
  native-stack) have no applicable target; no work manufactured
  (same discipline as the stripe-token-mirror tour). Web dashboard
  performance already covered by the vercel-react-best-practices tour.

### vercel-react-view-transitions tour (2026-09-19, work/2026-09-19)
- Availability audit first: ViewTransition exists ONLY in Next 15.5.4's
  vendored react-experimental channel; the stable compiled/react channel
  (what App Router actually runs) exports 0 — import would fail the build;
  transitionTypes prop is Next 16.2+. View-transition PATTERNS therefore
  deferred until a Next 16 upgrade, documented in the navigation map.
- Step-1 audit still paid off: all internal links were raw <a> tags
  (layout nav + page link) — every internal navigation was a full page
  reload, so view transitions could never trigger in ANY Next version.
  Converted internal links to next/link (client nav + prefetch);
  external-origin preview.html link stays <a>.
- Navigation map recorded: /<->/trend lateral (bare-VT crossfade when on
  Next 16; directional slides FORBIDDEN — false spatial depth), Suspense
  reveal + loading.tsx skeleton + persistent-header isolation as the
  Next-16 checklist. Reduced-motion CSS required at that time.
- Soft-nav proven live with headless Chromium: window marker survived
  / -> /trend navigation (before=42 after=42) — client-side routing
  confirmed, the VT trigger precondition now holds.
- Harness lesson: Freebuff terminal reaps background children after SYNC
  commands; register_preview needs a harness-managed process (BACKGROUND
  process_type not implemented in this build). Probes must start servers
  inside the same command that exercises them.

### verify-chain audit (2026-09-19, work/2026-09-19)
- Skill-doc (source: leibniz2) inventory is stale: says 19 pre-commit
  gates; live config has 50 (this session grew 47->50). 12 check_
  functions, 41 unique K-finding-ids in verify_delivery.py (284 kB).
- Live audit of the fail-closed contract, fresh runs:
  1. verify_delivery.py --full with SYSTEM python: rc=1, P0=1
     "z3-solver kurulu değil" — honest hard failure, no silent skip
     (K8 gate degrades closed). Matches the skill troubleshooting line
     "prefer venv python (repo .venv_z3/bin/python)".
  2. Same command with repo venv: rc=0, PASS (P0=0, P1=0); K8 12/12,
     K9 8 theorems lake build --wfail, K16 58/58, K6 61/61 online refs.
  3. Tamper-proof (K15): copied history.jsonl + sidecar to /tmp,
     flipped last record verdict to TAMPERED -> --check-history returns
     FAIL, rc=1. Probe artifacts removed.
- Conclusion: the chain fails closed at all three audited points
  (wrong env -> P0, right env -> PASS, tampered input -> FAIL).

### web-design-guidelines review (2026-09-19, work/2026-09-19)
- Source: vercel-labs/web-interface-guidelines command.md (fetched fresh).
- Scope: dashboard-next app/ (layout, page, VerdictCard, trend, error,
  loading) + components/ui/button.tsx. 13 findings, 0 blocker-class:
  dark-theme gaps (color-scheme, theme-color), animate-pulse without
  prefers-reduced-motion (loading + Suspense fallback), transition-all
  in button base, aria-label on role-less div (loading), no h1 on
  pages, raw ts strings instead of Intl.DateTimeFormat, missing
  tabular-nums on number columns, missing role=alert on error surface,
  brand span without translate=no. Anti-patterns clean: outline-none
  has focus-visible replacement, no autoFocus/onPaste/img/svg, hover
  states present, semantic table/dl/time in use.
- Review-only turn; fixes not applied (offered as follow-up).

### webapp-testing E2E (2026-09-19, work/2026-09-19)
- Toolkit: skill with_server.py managed BOTH servers (next :4321 via
  `npm run start -- --port 4321`; live Freebuff preview :8000 reused —
  real data source, pid untouched).
- E2E (headless chromium, networkidle): verdict/4-stat parity with
  /api/latest; soft-nav Link / -> /trend and back keep a window marker
  (42); zero console errors/pageerrors; screenshots /tmp/dash_*.png.
- DEFECT caught by E2E and fixed: trend page rendered ALL 100 history
  rows under a "Son 20 Koşum" heading. Root cause: serve_trend never
  reads the query string (full-list contract, "same as /api/history"),
  getTrend(limit=20) only encodes the wish. Fix: consumer-side window
  history.slice(-20).reverse() — newest 20, newest first.
  Playwright proof: rows 100 -> 20, first-row ts = newest, last-row
  20th-newest; tsc + build green.
- Harness lessons: helper runs commands as-is (flags must be inside
  the command string: `npm run start -- --port 4321`, port arg alone
  times out); :8000 is Freebuff's own preview server — reuse, do not
  kill.

### workers-best-practices surface audit (2026-09-19, work/2026-09-19)
- Zero Cloudflare-Workers surface, five independent proofs:
  1. wrangler.toml/jsonc/json (root + apps/*): absent.
  2. package.json inventory (all, node_modules excluded): no
     cloudflare/wrangler dependency or specifier.
  3. Import scan (module-specifier discipline, not substring):
     `@cloudflare/` / `cloudflare:` — 0 hits in app/apps/lib.
  4. .github/workflows: no workers.dev/pages.dev/cloudflare deploy.
  5. No worker* entrypoint files, no `new Worker(` usage.
- Discipline (same as stripe/RN turns): skill's review workflow has no
  target here — no invented work; zero-surface finding recorded with
  command evidence. Retrieval step intentionally skipped (no code to
  review against the fetched rules).

### wrangler skill turn (2026-09-19, work/2026-09-19)
- Skill FIRST-step executed: `wrangler --version` -> command not found;
  node v22.23.2 / npm 10.9.8 available.
- Installation intentionally skipped: no wrangler command exists to
  govern (scripts/CI/doc inventory: 0 calls; zero Workers surface
  re-verified: no wrangler.toml/jsonc). Installing -D wrangler would
  be invented work with no consumer — same discipline as the
  workers-best-practices turn (81a0f82).
- Skill knowledge stays retrieval-ready if a Worker surface ever
  lands: init/types/deploy contract is documented in the skill itself.

### writing-plans execution (2026-09-19, work/2026-09-19)
- Plan docs/superpowers/plans/2026-09-19-dev-bootstrap.md executed
  subagent-discipline inline (no dispatch tool in this harness; two-
  stage review replaced by gate evidence per task).
- Task 1 (ef0b6dc): dev_bootstrap.sh + 6-test contract suite. Red
  phase right-reason (script absent, unguarded class); green 6/6;
  hidden-venv fail-closed proof with finally-restore; live --check
  rc=0. Battery auto-synced to 140 files and HOOK_COVERAGE during the
  commit (two auto-sync hooks own those lists).
- Chain lessons recorded: coverage gate ran mid-staging once (race,
  fail-closed worked as designed); commit-msg title limit 72 chars
  (enforced); harness mangles apostrophes in heredoc commit messages
  (use message files).
- Task 2: README "Fresh checkout bootstrap" quickstart added after
  the "Doğrulama (tek komut)" section.

### xlsx surface audit (2026-09-19, work/2026-09-19)
- Zero spreadsheet surface, four proofs: (1) xlsx/xlsm/xltx/csv/tsv
  files in repo: 0 (node_modules excluded; main checkout identical);
  (2) no openpyxl/pandas/xlsxwriter imports in repo Python (only grep
  hit is setuptools-vendored more_itertools inside .venv_z3 — not repo
  code); (3) no csv-module usage in _calisma/CIKTI; (4) no spreadsheet
  production or consumption anywhere in the pipeline.
- Skill trigger requires a spreadsheet as PRIMARY input/output; the
  tabular history.jsonl does not qualify without a user request.
  No work invented; the xlsx contract (openpyxl formulas + mandatory
  recalc.py, LibreOffice function limits) stays retrieval-ready.
