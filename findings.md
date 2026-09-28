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

### Remotion pilot repoya taşındı (2026-09-26)
- **Pilot kayboldu**: `/tmp` macOS temizliğinde silinmiş — `ls /tmp/leibniz-chain-video`
  → No such file; `find /tmp /var/folders ~/Downloads ~/Documents -iname '*leibniz-chain*'`
  → boş; `~/.npm/_npx` + npm cache'te remotion paketi yok. Hayatta kalan tek iz
  prose kaydıydı (bu dosya + `recovery_patches_20260918/patch1789754982-84993:540-549`).
  Ders: repo dışında tutulan jeneratör, temizlikte kanıt zincirini de siler.
- **Yeniden inşa (uydurma değil)**: spesifikasyon kayıttan birebir kuruldu
  (1280x720@30, 760 kare, aynı 6 sahne sırası). Sayılar gömülmedi:
  `_calisma/video/make_data.py` her koşuda `history.jsonl` +
  `test_id_residual_acceptance_doc.py` sabitlerinden `public/data/leibniz.json`
  üretir. Ölçülen ilk render: 1.893.303 B, 25.3870 sn kap, 760 kare, 1280x720,
  avc1 — 14,7 sn'de (Chromium headless shell).
- **Ölçülen iki gerçek hata** (görsel denetimde yakalandı, koddan görünmüyordu):
  (1) `rise()` bir `<div height={…}>` değerine konunca her sahne başlığını 0'a
  çökertiyor, koşu satırlarını/kanıt kartlarını ekran dışına sıkıştırıyordu —
  4 karttan 1'i görünüyordu. Çözüm: `Reveal` (opacity + transform, doğal yükseklik).
  (2) `interpolate` sıfır uzunluklu aralığı reddettiği için ilk kare tamamen
  siyahtı; Title artık `fadeIn=0` ile sert kesişle açılıyor. İkisi de regression
  testi değil, görsel denetimle bulundu — tip kapısı ikisini de sessizce geçti.
- **CI'da history.jsonl yok** (gitignore'daki çalışma zamanı verisi) → üretici
  fail-closed kalırsa render job'ı her push'ta kırmızı olurdu. `--allow-missing-data`
  sentinel modu eklendi: koşu listesi boş + `data_missing` işareti, mühürler ve
  kare bütçesi yine üretilir (sahne "veri yok (temiz klon / CI)" der). Sentinel
  kare ile render ölçüldü — düz render kırılmıyor.
- **ffprobe ölçülemiyor**: paketlenmiş `node_modules/@remotion/compositor-darwin-arm64/ffprobe`
  macOS'ta `libavdevice.dylib` bulamıyor (Abort trap 6). Ölçüm stdlib mp4 kutu
  ayrıştırmasıyla yapıldı (mvhd/mdhd/stsd/stts/stsz) — CI probe'u da aynısını
  kullanıyor, ffprobe'ye bağımlılık yok.
- **prettier kapısı gerçekten koşuyor**: `_calisma/video` için `apps/dashboard-next`
  prettier'ı kullanıldı (kök `.prettierrc`; singleQuote=false, printWidth=80) —
  ilk yazım singleQuote/uzun satır idi, kapı 7 dosyayı yeniden biçimlendirdi.

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
- VERIFY-001 (fail-closed functional loss) — **ÇÖZÜLDÜ 2026-09-26, kanıtlı**:
  CSP script-src lacks 'unsafe-inline' ve nonce'ler inline event-handler
  NİTELİKLERİNİ kapsamaz → SVG hover tooltip'ları (refs-trend) sessizce
  ölüydü. Düzeltme kaynakta zaten vardı (`2fee44f`: `data-tip` + SVG-düzeyi
  delege) ama **koruyan kapı yoktu**; durum/kanıt aşağıda.
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

### Tarayıcı içi oynatma: @remotion/player → preview sunucusu
- Studio yerine Player: Studio ayrı sunucu + webpack dev-cache ve Freebuff
  harness'i her komut sonunda child process'leri reap ediyor (5 keepalive
  yöntemi de denendi, hepsi öldü — 2026-09-18 kaydı). `@remotion/player`
  tek statik dosyada toplanıp preview sunucusundan servis ediliyor.
- **Ölçülen hata**: Remotion `<Player>` bilesene özel propları `inputProps`
  ile geçiriyor; doğrudan `dataUrl={…}` yazmak Player'ın kendi propları
  sanılıp yutuluyor ve `useLeibnizData` `staticFile` yedeğine düşüyordu →
  tarayıcıda "leibniz.json 404". `inputProps={{dataUrl}}` ile düzeldi.
  Ölçüm: konsol hatası + sayfa metni (0:00/0:25 kontrolleri görünmüyordu).
- **CSP**: sunucu `default-src 'none'; script-src 'self' 'nonce-…'` uyguluyor.
  Sayfa **inline script içermiyor**; paket `/video/player.js` harici dosyadan
  geliyor, veri `data-src` niteliğiyle taşınıyor (`data-*` script değildir).
  `test_preview_video_player.py` her `<script>` satırını denetliyor.
- **Tarayıcıda doğrulandı** (Chromium): başlık sahnesi gerçek veriyle çizildi
  (1280×720 / 30 fps / 760 kare / 25,33 sn), oynatma başladı, 3 sn'de 0:07 +
  sahne 2, ardından sahne 3 → 4 → döngü; konsol hatasız, ağ hatasız.
  Sahne 5/6'yı tarayıcıda ayrıca ölçülmedi — mp4 render'ı altı sahneyi de
  kanıtlıyor ve oynatma aynı bileşen ağacını kullanıyor.
- **Yol kacisi kapatıldı**: `/video/*` üç adlık ACIK allowlist ile servis
  ediliyor (`VIDEO_ASSETS`); `..`, alt dizin, `.map`, bilinmeyen uzantı →
  404. Ölçüldü: 6/6 404.
- Dist kökü `PREVIEW_DIR` mirror'ından BAGIMSIZ (repo checkout'undan), böylece
  CI'da da çalışır; paket `.gitignore`'da (yeniden üretilebilir çıktı).

### Ortam kaybı: Playwright tarayıcı önbelleği silinmiş (2026-09-26)
- **Belirti**: `~/Library/Caches/ms-playwright/` dizini oturum ortasında TAMAMEN
  silinmişti (oturum başında 10 dizin vardı: chromium/headless_shell 1208, 1223,
  1234, 1243, ffmpeg-1011, webkit-2287). Aynı turda `/tmp` de temizlenmişti —
  aynı olayın iki yüzü: bu makinede cache'ler arac duraklamalarında toplanıyor.
- **Ölçülen hata değil, ortam hatası**: `chromium_headless_shell-1223` yürütülebiliri
  yok → `BrowserType.launch: Executable doesn't exist`. Üç test fail-closed düştü
  (`test_dashboard_cls_budget` 5 hata, `test_dashboard_keyboard_nav` 14 hata,
  `test_surface_cwv_report` 6 hata) ve `check-unit-tests` commit'i blokladı.
- **Kapının doğru çalıştığı nokta**: dört Playwright testi SKIP ediyordu
  (dürüst SKIP), üçü ise ortam yoksa düşüyor — yani eksik ortam GİZLENMEDİ.
  `test_dashboard_playwright_smoke` zaten EXCLUDE'da.
- **Onarım**: `python3 -m playwright install chromium` → Chrome Headless Shell
  148.0.7778.96 (chromium-headless-shell v1223, 92,4 MiB). Üç test de yeşile
  döndü. Ölçüm: 92,4 MiB, kurulum ~2 dk.
- **Tuzak**: öldürülen kurulum `__dirlock` dizini bırakıyor; sonraki kurulumu
  kilitliyor (`rm -rf ~/Library/Caches/ms-playwright/__dirlock` gerekir).
  Kısmi indirme de tutulmuyor — iki 600 sn'lik deneme boşa gitti, sonra ağ
  düzeldi (curl 0,18 sn) ve tek denemede tamamlandı. Ağ takılırken
  `curl --max-time` bile komutu kilitleyebiliyor; `timeout` sarmalayıcı gerekli.
- **Sonuç dışa aktarılabilir kural**: tarayıcıya bağlı bir test kırmızıysa
  ÖNCE `~/Library/Caches/ms-playwright/` ve `node_modules` varlığını denetle;
  kod değişikliği sanma. Playwright/ffprobe/paket kurulumları bu makinede
  kalıcı sayılmaz — CI'da kurulum adımını adım olarak yaz.

### LeibnizChain sahnelerinin zenginleştirilmesi (2026-09-26)
- **İstenen**: `history.jsonl`'den verdict-dağılımı grafiği ve kapı-kırılma
  animasyonu. Ölçülen veri 7 koşu, **hepsi** `verdict=FAIL`, `exit_code=-15`
  (SIGTERM), `p0=p1=0`, `findings=[]`, `duration_s` 1,02–13,99.
- **Veri yetersizliği ölçüldü, uydurma yapılmadı**: `z3_passed/total=0/0` ve
  `lean_ok`, `lineage_ok`, `refs_verified`, `flaky_count` … **null**. Yani
  kapı telemetrisinin 12 sütunundan 9'u HİÇ dolmadı; dolu görünen 3 sütun
  z3 ailesi ve değerleri 0. Bu yüzden "kaç kapı kırıldı" sayısı **verilemez**;
  üretilen şey kırılmanın kendisi: 7/7 koşu SIGTERM ile kesilmiş.
- **Dürüstlük kararı (bilinçli)**: dağılım tek sonuçlu olduğu için grafik tek
  renkli çizildi ve sahne bunu açıkça yazdı ("geçen koşu KAYIT YOK"). Tek
  renkli grafik görsel hata değil, verinin kendisidir.
- **İki ayrım kapatıldı** (ikisi de önce sessizce yanlış sayılıyordu):
  1. `0` ≠ `null` — z3 `0/0` "raporlandı" sayılmaz; "kanıt yükümlülüğü yok".
  2. `K katmanları ⚠️` bir kapı numarası DEĞİLDİR — 15 kapıya kırmızı
     dağıtılmadı, grup sinyali olarak ayrıldı. Yeşil işaret yalnız `K0` alır
     (tahtada adı geçen tek kapı). `gates.ok_ids` yalnız `GATE_NAMES` içinde
     olan etiketleri kabul eder; test bunu zorlar.
- **Ölçülen çizim hatası**: koşu satırında süre etiketi mutlak konumlanınca
  `FAIL` sütununa biniyordu (250. karede "2.98 s" iki satıra sarıyordu).
  Düzeltme: her sütun kendi sabit genişliğinde, etiket akış içinde.
  Ayrıca "13.99 s" 58 px sütunda sardi → 70 px.
- **Kare bütçesi 760 DEĞİŞMEDİ**: yeni içerik için kare, statik sahnelerden
  alındı (Evidence 180→120, Closing 60→50; Timeline 180→200, Gates 140→200).
  760 sayısı `Root.tsx` + `check_render.py` + CI adında + testlerde yaşıyor;
  büyütmek dört yeri birden kırmak demekti. Yeniden ölçüldü: 760 kare /
  25,387 sn / 1280×720 → `check_render` PASS.
- **Bulunan gerçek hata (bu işle bağlantılı)**: `video-render` CI adımının
  yorumu "sentinel JSON üretir" diyordu ama komut bayrat vermiyordu; üretici
  fail-closed olduğu için CI'da 1 ile çıkıp advisory işi kırıyordu. Adım
  `--allow-missing-data` ile düzeltildi (sentinel'in CI'da istenen yol bu).
- **Tuzak (shell)**: paralel `run_terminal_command` çağrıları cwd'de yarışıyor
  — biri `_calisma/CIKTI`'yi görürken diğeri "No such file or directory"
  diyordu. Çağrıları sıraya koy. `cd` birleşik komutta sonraki satırlara da
  sızıyor (`cd _calisma/video` sonrası göreli yol `_calisma/video/...` olur).
- **Tuzak (biçim)**: `prettier --write` .md/.yml dosyalarını da yeniden
  biçimlendirip **ilgisiz** satırları değiştiriyor (verify.yml'de 94 satır).
  `check-prettier-format` hook'u yalnız stage'li JS/TS/JSON'a bakar; .md/.yml
  elle korunmalı. Aynı sebeple `git checkout --` ile geri alındı.
- **Görsel doğrulama**: `remotion still` tek kare ~9 sn; 9 kare render edilip
  base64 gömülü HTML olarak önizlemede incelendi. Tarayıcı önizlemesi yalnız
  HTML'yi servis eder — kardeş dosyalar (png) 404 olur, base64 gömmek gerekir.

### VERIFY-001 çözümü ve kanıtı (2026-09-26)

**Teşhis (varsayım değil, ölçüm):** bulgu `preview.js ~652` diyordu; gerçek
yer başka. Handler'lar `_calisma/CIKTI/preview.js` içindeki **şablon
stringlerinde** (`svg.innerHTML` ile basılan hit-alanları) duruyordu ve
`design_preview.html` DIŞINDA hiçbir yerde değildi. Yani bulgu doğru
sınıfı tarif ediyor, işaret ettiği satırı değil.

**Zaten düzeltilmişmişti, kapısı yoktu:**
- `2fee44f fix(a11y): CSP-compliant event delegation + keyboard nav suite`
  üç yüzeyin de `onmousemove/onmouseleave` → `data-tip`+`data-i` + SVG-düzeyi
  `addEventListener` delege geçişini yapmış.
- Ölçülen boşluk: hiçbir test "inline handler geri gelmez" demiyordu.
  Yarım düzeltme (sadece refs) de sessizce geçerdi.
- `design_preview.html` (gitignore'da, üretilmiş) **2fee44f'ten ÖNCE**
  üretilmişti: 14 inline handler içeriyordu. Kaynak düzeltilmiş olsa bile
  inceleme/ demo yüzeyi bayat kopyayı gösteriyordu → yeniden üretildi.

**Eklenen iki kapı (ikisi de fail-closed, ikisi de kendini kanıtladı):**
1. `test_preview_server.py → InlineEventHandlerContractTests` (6 test, her
   yerde çalışır, tarayıcı gerektirmez): preview.html + preview.js +
   üretilmiş artifact'te `\son[a-z]+=` deseniyle inline handler yok; sunucunun
   **gerçekten gönderdiği** CSP başlığında script-src'de `unsafe-inline` yok
   (kaynak metin değil `ps.Handler._SECURITY_HEADERS` okunur — yorum
   satırına takılıp yanlış yeşil vermesin diye); üç yüzey de delege
   haritasında. Ayrıca **kapının kendisi** sentetik bir ihlalle sınanır
   (köre regex sessizce kalırsa yakalansın).
2. `test_preview_hover_tooltip.py` (8 test, Playwright, CI'da çalışır):
   gerçek preview_server + gerçek Chromium. Sırası ölçüldü:
   - önce kapı: yanıtta CSP var, script-src `'self' 'nonce-…'`, unsafe-inline
     yok — yoksa "CSP altında çalışıyor" iddiası boş olurdu;
   - refs-trend hit-alanları `data-tip`/`data-i` taşıyor, `onmousemove` null;
   - **gerçek `page.hover()`** (CDP Input) → `#tip` `none`→`block`, içerik O
     SÜTUNUN verisi (data-i 3 → refs 39/60);
   - başka sütun → içerik DEĞİŞİR (delege indeksi çalışıyor);
   - grafikten çıkınca gizlenir;
   - konsolda **0** CSP ihlali / "Refused to execute inline event handler";
   - trend + hook-env grafikleri de aynı sınıf → üçü de sınandı.

**Kanıtın kendisi ters yönde de sınandı:** `preview.js` geçici olarak
`2fee44f^`'a (düzeltme öncesi) çekildi → **7 hata, 0 skip**; düzeltmeli
sürüm → 8/8 yeşil. İlk yazımda iki test "veri yok" sanıp **skip** ediyordu
ve CSP-konsol testi 0 hit-alanı gezdiği için **boş** geçiyordu: kapının
kendisi boştu. Hit-alanı sayısı artık testin içinde zorlanıyor.

**Yeni ölçüm (2026-09-27) — demo artifact denetimi taze klonda BOŞLUKTA'ydı:**
`design_preview.html` commit dışı (`.gitignore:35`) ve
`build_design_preview.py` **hiçbir CI/hook'tan çağrılmıyor**; dosya yoksa
`test_built_design_preview_has_no_inline_event_handlers` `skipTest` ile
atlıyordu. Yani inceleme/demo yüzeyinin VERIFY-001 koruması "dosya varsa"
çalışıyordu; `2fee44f`'ten önceki 14 inline handler'lı bayat kopya senaryosu
sessizce geri dönebilirdi. Düzeltme: üretici çıktı yolunu argümandan alıyor
(`build_design_preview.py [ÇIKTI]`), kapı artifact'ı geçici dizine **üretip**
denetliyor (her koşuda, skip yok; 0.077 sn) ve yerel kopyayı taze üretimle
karşılaştırıp **bayatlığı FAIL** ediyor. Ölçüm: üretim deterministik (iki
koşu birebir aynı, 153 766 bayt), taze artifact'ta 0 inline handler /
6 `data-tip` / 22 `addEventListener`. Mutasyon kanıtı: `preview.js`'e bir
`onmousemove` geri konunca **üç** denetim de kızdı (kaynak taraması, üretilen
artifact taraması, bayat-kopya denetimi). Ayrıca `verify.yml` başarı
mesajındaki sabit "8/8" kaldırıldı: sayaç artık logdan okunuyor ve 0 test
koşarsa adım FAIL ediyor.

**Ölçülen araç tuzağı:** önizleme panelindeki `preview_click` bu webview'a
**gerçek fare girdisi teslim etmiyor** — SVG'ye capture dinleyici asılsa
bile 0 mousemove ulaştı (ölçüldü). Bu yüzden kanıt Playwright'ın kendi
Chromium'uyla alındı; panel içindeki görsel deneme araç kaynaklı başarısız
denemeydi, kodun değil.

**Yol üstünde bulunan AYRI hata (düzeltildi):** `connectStream()` içinde
`el` yalnız `flushStream()`'in yerel `const`'ıydı; aynı fonksiyondaki
`replay-start` / `replay-end` / `end` dinleyicileri de `el.innerHTML` +
`el.scrollTop` yazıyordu → her run özetinde **ReferenceError "el is not
defined"** (kanıt koşusunda 18 kez ölçüldü) ve akış paneli güncellenmiyordu.
Kapsam `connectStream()`'a taşındı; yazma davranışı değişmedi. Düzeltmeden
sonra kanıt koşusu: CSP ihlali 0, konsol hatası 0, sayfa hatası 0.

**Ölçülen ön koşul:** `check-prettier-format` `preview.js`'i HEAD'de de
kırmızı gösteriyordu (tek bir satır, 313: `tp.textContent = …`). Yeni
regresyondan değil; küçük olduğu için bu turda `--write` ile düzeltildi,
böylece kapı yeşil. (`.md`/`.yml` dosyalarında prettier hâlâ elde
değil — o hook kapsamı dışında.)

---

## escapeHTML nitelik bağlamı için güçlendirildi (HTML enjeksiyon yüzeyi)

**Bulgu:** `escapeHTML` yalnız `& < >` kaçırıyordu — `title="…"`,
`class="…"`, `data-ts="…"` gibi **nitelik değerleri** için yetersiz.
Sunucudan gelen serbest dizgi (`run.source`, `lean_detail`, `ts`, hook adı,
bulgu metni) tırnağı kapatıp **yeni nitelik** enjekte edebilirdi.

**Ölçülen iki açık yuva** (tarama sonucu, 26 `escapeHTML` çağrısı içinde):
`lean_detail` → `title="Lean FAIL${ld}"` ve `source` → `class="source-badge
${srcBadge}"`; ayrıca `data-ts` elle kaçırılıyordu. Üçü de `escapeHTML`'e
bağlandı. Fonksiyon artık beş karakteri de kaçırıyor (`& < > " '`), `&`
ÖNCE — sıra tersine dönerse kendi kaçışımız bozulur.

**Tarama (tüm havuzlar):** `preview.js`'te 135 template literal havuzu,
237 interpolasyon tarandı. Nitelik bağlamındakiler: 137'nin tamamı ya
`escapeHTML` ile kaçırılmış ya da **sayı** üreten yardımcı
(`x`/`xAt`/`yP`/`yD`/`yB`/`yZ`/`yL`/`y`, `fmtLimit`…). Kalan 8 veri
türetli interpolasyon **metin** bağlamında. **Nitelik bağlamında kaçışsız
veri interpolasyonu: 0.**

**Sayı yardımcılarının güvenliği isim listesine değil tanıma dayandırıldı:**
`x = PL + (n === 1 ? iw/2 : (iw*i)/(n-1))`, `y = PT + ih - (ih*v)/maxN`
gibi tamamen aritmetik. Düşman girdi (`" onmouseover="alert(1)`) verildiğinde
sonuç `NaN` olur — tırnak işareti hiçbir yolla sonuca taşınamaz.
`fmtLimit/fmtTs/fmtDuration` ise `isFinite()` elemesiyle dizgiyi ya sabit
("—") döndürür ya da sayıya indirir.

**Bulunan ikinci açık: tarayıcının kendisi körleşmişti.** İlk statik kapı
**satır tabanlıydı**; `title="x ${…}` açılışı ile kapanış tırnağı ayrı
satırlarda olduğunda hiçbir satırda `="…"` kalıbı oluşmuyor ve ihlal
**görünmüyordu** (ölçüldü: satır taraması 0 buldu, havuz taraması 1 buldu).
Kapı **havuz tabanlı** tarama ile değiştirildi; çok satırlı şablonlar da
kapsanıyor. Ayrıca ölü bir yardımcı adı (`colorFor` — dosyada hiç yok)
güvenli listesinde kalmıştı; silindi ve listenin ölü giriş taşımadığı
ayrıca sınanıyor.

**Düzeltilen test kusuru:** `assertIn` hata mesajına `preview.js`'in tamamını
döküyordu (3000 satır gürültü). Varoluş denetimine çevrildi, mesaj sabit.

**Kapının boş olmadığı kanıtlandı** — 6 mutasyon, hepsi yakalandı:

| # | mutasyon | sonuç |
|---|---|---|
| M1 | `escapeHTML` tırnak kaçırmaz | FAIL |
| M2 | `srcBadge` yuvası kaçışsız | FAIL |
| M3 | **çok satırlı** nitelik enjeksiyonu | FAIL |
| M4 | tek satırlı nitelik enjeksiyonu | FAIL |
| M5 | `data-ts` elle kaçırılıyor | FAIL |
| M6 | `escapeHTML` HTML parçasına uygulanıyor | FAIL |
| — | temiz sürüm | 6/6 OK |

**Tarayıcı kanıtı** (`test_preview_escaping.py`, 7 test): kötü veri gerçek
`/api/run-history` render yolundan geçirilip gerçek DOM ayrıştırıcısına
veriliyor — `class`/`title` üzerinden nitelik enjeksiyonu yok, metin
bağlamında etiket açılmıyor, `data-ts` birebir geri dönüyor, kaçırma
metni **bozmuyor** (kullanıcı aynı metni görüyor). Düzeltme öncesi sürümde
bu testler 3 hata veriyor.
---

## Güvenlik-duruşu kalıcılaştırıldı: başlık matrisi + CSP + izolasyon

**Ölçümle başlandı, varsayımla değil.** 25 rotanın tamamı gerçek bir
in-process sunucuya istek atılarak tarandı: üç başlığın (`X-Content-Type-
Options`, `Referrer-Policy`, `Content-Security-Policy`) hepsini her rota
taşıyor. Boşluk sunucuda değil **testlerin kapsamındaydı**.

**Ölçülen dört gerçek boşluk:**

1. **Testler `_route()`'tan türetilmiyordu.** `test_security_headers.py`
   404/405/statik kök/HEAD'i tek tek ölçüyor — ama rota listesini elle
   tutuyor. `_route()`'a yeni bir `return "x"` eklenince kapsam
   BÜYÜMÜYOR, sessizce küçük kalıyor. Yeni modül rota listesini
   **kaynak koddan** çıkarıyor; karşılığı yoksa test fail-closed.
2. **SSE hiç ölçülmemişti.** `/api/run` ve `/api/run-stream` kendi
   `send_header` blogunu taşıyor (övülü: `end_headers()` hunisi onları
   da kapsıyor — ham soketle ölçüldü, 0.0 sn'de üç başlık geliyor).
3. **`serve_slides` / `serve_landing_assets` korumaları test edilmemişti.**
   Dört katman uygulanmış (tek segment · gizli dosya · `.png` + karakter
   beyaz listesi · realpath+commonpath) ama sıfır testi vardı.
4. **CSP'nin tamamı tek yerde sabitlenmemişti.** Yalnız
   `frame-ancestors 'none'` ve nonce kapsaması ölçülüyordu.

**Yeni üç modül (36 test):** `test_security_header_matrix.py` (9),
`test_csp_directives.py` (13), `test_static_isolation.py` (14).

### Kırılan iki test altyapısı

**Tarayıcı sınıfı üretimden sapmıştı.** İlk yazımda `HTTPServer` (tek
iş parçacıklı) kullandım; SSE sonsuz akış olduğu için test kilitlendi.
Üretim `ThreadingHTTPServer` kullanıyor (`main()` satır 2440) — yani
ölçtüğüm şey üretim değildi. Düzeltildi. Not: `test_security_headers.py`
hâlâ `HTTPServer` kullanıyor; SSE'e dokunmadığı için çalışıyor ama
aynı sapmayı taşıyor.

**Boşluk karakterleri ham gönderilemiyor.** `urllib` boşluk/kontrol
karakteri içeren isteği istemci tarafında reddediyor. Test istemciyi
suçlamak yerine **tarayıcının gerçekte gönderdiği** yüzde-kodlanmış
hale baktı — ham metni sınamak gerçeği ölçmezdi.

### Kapının kendisi ölçüldü: 12 mutasyon

| mutasyon | sonuç |
|---|---|
| realpath+commonpath katmanı kaldırıldı | FAIL |
| `script-src`'a `'unsafe-inline'` | FAIL (2) |
| `default-src` `'none'`→`'self'` | FAIL (3) |
| `frame-ancestors` kaldırıldı | FAIL (2) |
| nonce sabit literal yapıldı | FAIL |
| nonce başlıktan ayrıldı | FAIL |
| bir başlık tablodan silindi | FAIL (6) |
| `_route()`'a yeni rota eklendi (matrise girmemiş) | FAIL (2) |
| karakter / uzantı / gizli dosya filtresi kaldırıldı | **PASS** |

Son satır bilinçli bir bulgu: **dört koruma katmanından yalnız
`realpath`+`commonpath` davranışsal olarak yük taşıyor.** Diğer üçü tek
tek devre dışı bırakıldığında sunucu yine de 404 dönüyor (o adlar diskte
zaten yok). Yani onlar bugün savunma derinliği. Davranış testleri
sessizce silinmelerine izin veriyordu; `test_guard_stack_is_still_
present_in_source` artık dört katmanı **iki handler'da da** yapısal
olarak sabitliyor ve kaldıran birinin önce testi güncellemesini zorunlu
kılıyor. Katmanları silmedim — savunma derinliği meşrudur.

**Pozitif kontrol zorunluydu:** korumalar "her şeyi reddet" haline
gelirse tüm saldırı testleri sessizce geçer. Her modül geçerli dosya
senaryosuyla da sınandı (200 + bayt bayt gövde) — yalnız 404 döndüren bir
kapı bu testleri geçemez.

### En tehlikeli bulgu: atlanan test, geçen gibi görünüyordu

Yeni kapıyı tek roster ile yazmıştım. Tarayıcı modülleri
`skipIf(playwright yok)` ile **ATLANIYOR** — hata değil. CI'ın birim-test
adımında Chromium kurulu değil. Yani kapı CI'da "9/9 PASS" derken
gerçekte iki güvenlik kanıtı hiç koşmamış olacaktı. Atlanmış bir kanıt
kanıt değildir; sayımı yok sayan bir kapı onu yeşile çevirir.

Çözüm iki kademe:
- `check_security_posture.list` — 7 statik modül, tarayıcı bağımlılığı
  yok, **her ortamda** koşar (yerel pre-commit + CI `precheck`).
- `check_security_browser.list` — 2 tarayıcı modülü, yalnız Chromium'un
  kurulu olduğu yerde koşar (CI `a11y-gate`).

Kapı **atlanan test sayısını da reddediyor**. Chromium yokluğu
simüle edilerek ölçüldü: iki modül `SKIP (8/7 test atlandi)` → kapı
`rc=1` ve hangi kanıtın koşmadığını adıyla yazdı.

### Kapı kendisi de boş olamaz

| senaryo | rc |
|---|---|
| roster dosyası yok | 1 |
| roster boşaltıldı (0 giriş) | 1 |
| roster'da diskte olmayan dosya | 1 |
| gerçekten kırılmış modül | 1 (modülün adı stderr'de) |
| temiz | 0 |

### Wiring

- pre-commit: `check-security-posture` hook'u (57. hook) — yerelde
  commit'i bloklar.
- CI `precheck`: statik kademe **fail-closed** adım.
- CI `a11y-gate`: tarayıcı kademe **fail-closed** adım (Chromium zaten
  kurulu). Yeni *iş* değil, mevcut işlere adım — iş sayısı 31'de sabit,
  required/advisory sözleşmesi değişmedi.
- `shellcheck_hooks.sh` listesine yeni betik eklendi (kapı da linte girer).

## Session 2026-09-27 — dashboard-next preset bağımsızlığı (contract 8)

2026-09-19 notundaki açık açı kapandı: dashboard-next artık shadcn npm
preset sheet'ine bağlı değil.

- **Kaldırılan bağ:** `apps/dashboard-next/app/globals.css` içindeki
  `@import "shadcn/tailwind.css"` (629 satırlık preset: `data-*`
  variant'ları, `no-scrollbar`/`scroll-fade`/`shimmer` utility'leri +
  kendi `@property`/`@theme` blokları). Repo kaynağında bu yüzeylerin
  HİÇBİRİ kullanılmıyordu (kaynak grep: 0 eşleşme) — yani ikinci bir tema
  kaynağı, kullanılmayan stil yükü ve habersiz renk enjekte etme riski.
- **Kanıt (yeniden derleme):** `npm run build` yeşil, BUILD_ID
  `Ca5LNsJqJ0dIWdrZifvhL`, rotalar değişmedi (`/` ve `/trend` ƒ Dynamic,
  `_not-found` ○ Static); üretilen tek CSS 33.623 B ve içinde
  `shimmer`/`scroll-fade`/`no-scrollbar`/`data-open` geçmiyor (grep 0),
  repo token'ları (`#0e1116`, `var(--accent)`, `var(--card)`,
  `var(--radius)`) yerinde. Tema zinciri artık: tailwindcss çekirdeği +
  `design-system/tailwind.css` GENERATED köprüsü + globals.css'teki
  repo-içi shadcn yuva eşlemesi (her değer `var()` referansı).
- **Kapı kapatması (check-design-tokens contract 8):** dış preset importu,
  yazıyla verilmiş yuva değeri, çözülemeyen `var(--X)`, `@theme`'de
  alias'sız yuva ve uygulama kaynağında preset-only yüzey kullanımı
  fail-closed BLOKE. Negatif kanıt: `test_check_design_tokens.py` 20 vaka
  (yedisi yeni contract 8; yorumdaki yüzey adının bloke etmediği vaka
  dahil) — hepsi OK.
- **Kalan açı:** `tw-animate-css` hâlâ import ediliyor ama kaynakta hiç
  kullanılmıyor; yeni bir shadcn bileşeni preset-only yüzey getirirse
  contract 8(e) onu commit anında yakalar ve karşılığının repo CSS'ine
  eklenmesini zorlar.

## Session 2026-09-27 — Stripe HDS tema varyantı (contract 9)

2026-09-19 notundaki "mirror'lar zincirde değil" açığı `eab61e1` ile
(`check-brand-mirrors`), mirror'ın **yüzeye** bağlanması ise bu oturumla
kapandı: `design-system/stripe/` artık kendi başına duran bir arşiv değil,
panonun ve landing'in gerçek bir tema varyantını besliyor.

- **Üretici (`stripe/scripts/generate_stripe_theme.py` →`stripe/theme.css`,
  GENERATED):** `SLOT_MAP` 32 repo yuvasını (`--bg`, `--fg`, `--muted`,
  `--ok/--warn/--err/--budget`, `--accent/--on-accent`, `--surface*`,
  `--code-bg`, `--paper/--paper-ink`, `--tint-*`, `--shadow-tip`,
  `--backdrop-lightbox`) HDS token'larına bağlar; `closure()` `var()`
  transitif kapanışını aynadan **birebir** kopyalar (24 HDS token),
  `REQUIRED_SLOTS` eksikse `SystemExit`. Çıktı yalnız
  `:root[data-theme="stripe"]` bloğu; `--check` modu drift'i yazar.
  Docstring `r"""` yapıldı (`\s` invalid escape → DeprecationWarning).
- **Kapı (check-design-tokens contract 9):** `theme.css` üreticinin
  `render()` çıktısıyla bayt-bayt eşleşmeli; kapsam sızıntısı (tek blok
  dışında stripe kuralı), eksik yuva, renk literali, çürük HDS referansı ve
  aynadan farklı HDS değeri fail-closed BLOKE. Ayrıca varyantı **tüketen**
  yüzeyler taranır: `preview.html` + `landing/landing_src.html` içinde
  `[data-theme="stripe"]` kapsamlı kural yoksa hata, her değerde `var(`
  şart, renk literali yasak.
- **Yüzey kablolaması:** pano tema döngüsü `dark → light → stripe` oldu
  (`?theme=stripe`, `localStorage` doğrulamalı, `aria-label` theme adını
  yazıyor); `preview_server.py` `/design-system/stripe-theme.css` rotası
  (mirror'da yoksa fail-closed 404), `sync_verify_mirror.sh` guide listesi ve
  `check_mirror_coverage.py` kapsamı 77/77. Landing tarafı `--theme
  dark|light|stripe`: stripe varyantı `<style>` olarak gömülür ve `<html
  data-theme="stripe">` yazılır; **varsayılan dark çıktısı bayt-bayt
  değişmez** (nitelik yazılmaz), bilinmeyen tema `SnapshotInvalid`.
- **Krema arındırması (ölçülmüş):** arşiv/kâğıt motifinin literalleri
  (`#f4efe5`, `#fffdf8`, `#d6cbb9`, `#e2d7c6`, `#8b7355`, `#c9b18e`,
  `#b8874a`, `#ebe3d4`, …) yalnız dark/light varsayılanlarında kalır;
  stripe kapsamında yerlerini `var(--paper)`, `var(--paper-ink)`,
  `var(--border)`, `var(--surface*)`, `var(--accent)`,
  `var(--backdrop-lightbox)`, `color-mix(... var(--fg) …)` alır. Canlı
  Chromium ölçümü (sunucu :8123): `dataset.theme="stripe"`, `--accent:
  #533afd`, `--paper:#fff`, gövde `rgb(255,255,255)`, galeri/karo/lightbox
  içinde tespit edilen krema-literal sayısı **0**; dark ve light
  varyantları eskisi gibi (galeri `rgb(244,239,229)` / `rgb(255,253,248)`,
  eyebrow `rgb(139,115,85)`). Landing'in stripe derlemesi de aynı ölçümle
  temiz (arşiv panosu beyaz + lacivert, CTA `#533afd`).
- **Kanıt:** `check_tokens.py` rc 0 ("stripe HDS varyantı 32 yuva
  jeneratörle birebir"), `generate_stripe_theme.py --check` OK,
  `test_check_design_tokens.py` 28 vaka, `test_build_landing.py` 16 vaka,
  `test_preview_server.py` 166 vaka, `check_mirror_coverage.py` 77/77,
  `check_seal_hash.py` temiz (mühür 74b2cdbdb18f ↔ committed PDF; landing
  yeniden derlemesi mühürü değiştirmedi, yalnız +12 satır varyant eklendi).
- **Kalan açı:** varyant yalnız `[data-theme]` seçicisiyle devreye giriyor —
  otomatik "sistem teması" eşlemesi yok; ayrıca HDS font ailesi
  (`sohne-var`/`SourceCodePro`) bundle edilmediği için stripe varyantı
  tipografiyi değiştirmiyor, yalnız renk yüzeylerini değiştiriyor.

### gate-audit tour (2026-09-27) — check-precommit-orphans: arşiv parmak-izi kapsamı

- **İstek:** "24s+ patch-kalıntısında engelleyen + recovery_patches arşivini
  kontrol eden fail-closed hook". Kapı 2026-09-19 tdd turunda zaten kurulmuş
  (`check_precommit_orphans.py`, hook 19, always_run, PRE_COMMIT_HOME
  fixture'lı 8 sözleşme); **gerçek eksik arşiv tarafındaydı.**
- **Bulgu:** parmak-izi kaynağı `recovery_patches_20260918` diye SABİTTİ.
  Diskte üç arşiv var (`_20260918` 2, `_20260920` 14, `_20260926` 24 patch =
  **40 patch**) → arşivlenen deltaların **38'i kapıya görünmezdi**: aynı
  içerik yeniden yetim kalsa `KNOWN-INCIDENT` etiketi üretilemez, kurtarma
  yolu tek bir tarihe bağlı kalırdı. Sınıf: "tek örnekten genellenmiş
  sabitleme" — arşiv deseni büyüdükçe sessizce körleşen kapı.
- **Düzeltme:** `ARCHIVE_GLOB = "recovery_patches_*"` (glob; yeni arşiv
  eklendiğinde kaynak kendiliğinden genişler), aynı içerik birden çok arşivde
  varsa hepsi adıyla listelenir, yetim raporu kaynağın kapsamını yazar
  (`arşiv parmak-izleri: 3 dizin / 40 patch`; arşiv boşsa "etiket üretilemedi
  — kontrol körleşti" uyarısı). Arşivsizlik tek başına blok değil.
- **Yeni sözleşme — taze tekrar:** <24s patch kurtarma penceresindedir ve
  bloklamaz, ama içeriği arşivle birebir aynıysa `PRE-COMMIT PATCH RECURRENCE`
  + `KNOWN-INCIDENT` satırı basılır (exit 0). Yani "aynı delta yine yetim
  kaldı" sinyali görünür olur, commit bloke olmaz.
- **Test:** `test_check_precommit_orphans.py` 8 → **13** (glob sabitlemesi
  yasaklandı statik olarak, her arşivin parmak-izi yüklediği dinamik olarak,
  09-26 kopyasının etiketlendiği, taze tekrarın bloklamadığı, raporda arşiv
  kapsamının yazıldığı); 13/13 PASS.
- **Canlı çerçeve kanıtı** (yapay dosyalar sonrası silindi): gerçek cache
  rc 0; 32h'lik yapay patch → hook **Failed** + dosya adı + `3 dizin / 40
  patch`; 09-26 arşiv kopyası (taze) → iki arşiv kopyası adıyla RECURRENCE,
  blok yok; temizlik sonrası rc 0.
- **Süre-sınırı notu (eylem bekliyor):** `~/.cache/pre-commit`'te
  2026-09-26 20:01 ve 20:06 tarihli iki 185 kB'lik patch (V5 teslim-zip
   çalışması, 8 dosya) 24s penceresini **2026-09-27 20:01/20:06'da** aşıyor ve
  o saatten sonraki commit'leri bloklayacak. İkisi de `git apply --reverse
  --check` ile TERS-uygulanabilir → delta ağaçta zaten var (artık, kurtarma
  değeri yok).

### archive-audit turu (2026-09-27) — olay-patch'i plan dosyaları ↔ bugünkü sürüm

- **Soru:** revert olayının arşiv patch'i (`recovery_patches_20260918/`
  `patch1789754982-84993`) `findings.md`/`progress.md`/`task_plan.md`'nin
  olay-anı snapshot'ını taşıyor; bu delta "oturum-belleğinden yeniden
  yazılırken" içerik kaçırıldı mı?
- **Yöntem:** patch'in `+` satırları üç kademede denetlendi: (1) bugünkü
  dosyada birebir/normalize var mı, (2) yoksa git TARİHİNDE hiç commit
  edilmiş mi, (3) hiç commit edilmemişse teknik belirteçleri (yol/hash/sayı/
  bayrak) bugünkü repo metninde izlenebiliyor mu. Ayrıca yeniden-yazımın ilk
  commit'i (`07e22aa`, 2026-09-19 09:02) ayrı taban alındı ve ters yön
  (patch'te silinen satır bugün geri gelmiş mi) kontrol edildi.
- **Sonuç 1 — hiç commit edilmemiş satırlar: 247** (findings 140, progress
  61, task_plan 46). 132'si teknik belirteç taşıyor ve tamamı bugün repoda
  izlenebilir; 115'i belirteçsiz düzyazı — yalnız arşivde kalıyor (09-18
  oturum günlüğü sonradan Türkçe yeniden yazıldı, bu beklenen).
- **Sonuç 2 — yeniden-yazım anı:** `07e22aa`'da snapshot'ın teknik
  belirteçlerinin 57/101 (findings), 30/46 (progress), 22/41 (task_plan)'i
  dosyalarda YOKTU (birebir satır: 5/145, 0/61, 0/46). Bugün bu **109
  belirtecin tamamı başka yüzeylerde yaşıyor**: `74b2cdbdb18fafbf`
  (verdict-seal testi + PDF metadata), `0.2555` (preview.html CLS ölçümü),
  `0.0005` (progress.md), `end_headers` / `do_head` / `build_ts`
  (preview_server + testler), `ingiliz_empirizmi_v3.pdf`
  (.pre-commit-config + M0 raporu) → **kayıp 0**.
- **Sonuç 3 — yalnız arşivde kalan izler:** tek-seferlik scratch/env
  dizgileri (`/tmp/leibniz-chain-video`, `/tmp/review_brief.md`,
  `--skip-claude/--only-claude/--no-global`, `~/.local/bin`,
  `~/.cargo/bin`) — olguları bugün başka dosyalarda (video pilotu
  `_calisma/video/`'ya taşındı, `skip-claude` `.gitignore`'da). Tüm repoda
  **hiç iz bırakmayan tek dizgi:** Orca sürümü `1.4.205` (Orca bulgusunun
  kendisi AGENTS.md + findings.md'de duruyor).
- **Sonuç 4 — ters yön:** patch'in silinen satırlarından bugün geri gelen
  yok → olay-öncesi metin dirilmemiş.
- **Sınıf notu:** "bellekten yeniden yazım" iddiasının doğrulanabilir tek
  yolu bu üçlü karşılaştırma (patch = olay-anı snapshot'ı ↔ yazım commit'i ↔
  bugünkü yüzeyler). Sonuç: arşivin kurtarma değeri kanıtlı, olgu kaybı yok;
  kaybolan şey satır düzeni ve İngilizce düzyazı.

### verify-001 turu (2026-09-27) — CSP altında hover + tıklama kanıtı

- **Düzeltme zaten kodda:** ana ağaçta inline `on*` nitelik handler **0**
  (statik tarama); üç grafik (`trend`, `refs-trend`, `he-trend`) rect'leri
  `data-tip`/`data-i` taşıyor ve SVG düzeyinde
  `addEventListener("mousemove"/"mouseleave")` ile delege; tıklama/klavye
  yüzeyleri (`budget-toggle`, `rh-filter`, `load-stdout`) document-düzeyi
  `data-act` delege. Yani VERIFY-001'in kod yarısı kapanmıştı.
- **Kanıt canlı koştu (yerel Chromium 148 + gerçek preview_server):**
  `test_preview_hover_tooltip.py` **8/8** — sayfa gerçekten sıkı CSP ile
  servis ediliyor (`script-src 'self'` + nonce, `unsafe-inline` YOK), hover →
  tooltip O run'ın değerini gösteriyor (10/17/24/31), mouseleave → gizleniyor,
  üç grafikte de aynı, konsolda **0 CSP ihlali**. Statik eşdeğer
  `test_preview_server.py` **166** (candidate handler sözleşmeleri).
- **Bulunan gerçek boşluk (aynı sınıfın ikinci yarısı):**
  `test_dashboard_keyboard_nav.py` (14 canlı test: delege TIKLAMA/KLAVYE
  yüzeyleri + tema döngüsü) yalnız `check_unit_tests.list`'teydi; Playwright
  yalnız `a11y-gate` işinde kurulduğu için `verify` birim adımında
  module-level `skipIf` yüzünden **14 test sessizce atlanıyordu**. Üstelik
  süitte **CSP-ihlali sayacı yoktu** → "delege çalışıyor" kanıtı, "konsolda
  CSP reddi yok" iddiasını kanıtlamıyordu. Hover yarısındaki boşluğun birebir
  tekrarı.
- **Kapatma:** (1) süit `_calisma/CIKTI/check_security_browser.list`
  roster'ına alındı — tarayıcı-tier kapısı SKIP'i reddediyor (artık
  Chromium'lu işte koşar); (2) taban sınıfa console/pageerror toplama +
  `_csp_violations()` ve sıkı-CSP kapı testi eklendi; (3) canlı DOM'da
  (runtime-üretilen `<rect>`'ler dahil) inline-handler taraması ve gerçek
  fare tıklamasıyla delege kanıtı (filtre `.active` taşır, banner toggle
  `aria-expanded` açar) + sıfır CSP ihlali. 14 → **18 test**.
- **Doğrulanmış koşular:** hover 8/8, klavye 18/18, tarayıcı-tier
  `check_security_posture.sh check_security_browser.list` → **3 modül PASS,
  0 SKIP**; `actionlint` PASS; YAML parse OK. CI'da tarayıcı-tier adımı
  roster'ı okuduğu için ek adım gerekmedi; VERIFY-001 adımının yorumu
  tıklama yarısının nerede koştuğunu yazacak şekilde güncellendi.
- **Kalan açı:** `test_dashboard_keyboard_nav.py` hâlâ manifestte olduğu için
  Playwright'sız işte SKIP ediyor; bu artık *sessiz* değil çünkü aynı süit
  skip-reddeden roster'da da koşuyor. Aynı desen başka Playwright süitleri
  için de taranmalı (roster dışında kalan canlı kanıt = sessiz boşluk).

### arbitrary-renk sızması turu (2026-09-27) — taşınacak sınıf yok, kapı var

- **Ölçüm (önce):** `apps/dashboard-next` kaynağında **arbitrary-hex utility
  0**. Tarama kapsamı: tüm `*.tsx/*.ts/*.css` (node_modules/.next hariç) +
  `components/ui/`; hex/rgb/hsl/oklch literali **0**, `style={{` **0**.
  Tailwind varsayılan paleti (`bg-slate-900`, `text-white`, …) da **0**.
  Tek `#…` eşleşmesi `app/globals.css` içindeki bir **yorum** satırı
  (`--muted`'un `#8b949e` olduğunu anlatan Türkçe not) — yorum-boşaltma
  bunu zaten ele alıyor.
- **Yani taşıma 2026-09-19 tailwind-design-system turunda bitmişti;**
  eksik olan **regresyon kapısıydı** (kapı olmadığı için sınıf sessizce
  geri gelebilirdi).
- **Kapı (contract 8f):** `check_tokens.py` `_color_literal_findings()` üç
  kural denetler — (1) arbitrary renk utility'si (`bg-[#0e1116]`), (2) ham
  hex/rgb/hsl literali (inline `style={{…}}` ve globals.css dahil;
  `@theme`/`@utility`/`@layer` direktif blokları muaf), (3) Tailwind
  varsayılan paleti (renk ailesi + ton şartı → `border-0`/`ring-3` gibi
  ölçü utility'leri ve `text-current`/`border-transparent` girmiyor).
  Yorumlar **boşlukla** silinir, satır numaraları kaymaz. Meşru arbitrary
  değerler (harf aralığı, `text-[11px]`, `rounded-[min(var(--radius-md),10px)]`,
  `shadow-[…rgba(0,0,0,.5)]`, `bg-[color-mix(…var(--secondary)…)]`,
  `&#8212;`) karşı-testle korunuyor.
- **Görsel QA (canlı, gerçek build):** `npm run build` temiz (3/3 statik,
  First Load JS 102 kB) → `next start :3210` → Playwright/DevTools ile
  hesaplanmış stiller: `bg-bg` → `rgb(14,17,22)` = `#0e1116`,
  `text-fg` → `rgb(230,237,243)` = `#e6edf3`, `border-border` →
  `rgb(48,54,61)` = `#30363d`, `text-muted` → `rgb(139,148,158)` = `#8b949e`,
  `bg-card` → `rgb(22,27,34)` = `#161b22`; `/` ve `/trend` sayfalarının
  TÜM çizili düğümlerinde ölçülen renk kümesi yalnız token değerleri
  (+ Next.js route-announcer ve tarayıcı rozeti gibi uygulama-dışı yüzeyler).
  Sayfada arbitrary sınıf **0**.
- **Sessiz stil kaybı taraması (ek kanıt):** kaynaktaki **66** farklı
  renk-ailesi utility'sinin tamamı derlenmiş CSS'te gerçek kural olarak
  var → köprü kopukluğu yok (`bg-secondary`, `text-secondary-foreground`,
  `dark:bg-input/30`, `aria-invalid:ring-destructive/20` dahil).
- **Test:** `test_check_design_tokens.py` 33 → **35** (palet-pozitif +
  ölçü/`current`/`transparent` karşı-testi); gerçek ağaçta kapı rc 0.

### mirror-@theme turu (2026-09-27) — dört marka aynasının kendi köprüsü

- **Başlangıç ölçümü:** aynalar `tokens.css` + `tokens.json` + `raw.*` +
  kendi checker'ına sahip ve `check-brand-mirrors` roster'ında pinli
  (710/398/2051/19), ama köprüden yalnız `stripe` vardı ve o da `@theme`
  değil `:root[data-theme="stripe"]` semantik varyantıydı. Diğer üçü ve
  stripe'in kendisi Tailwind utility'si üretmiyordu.
- **Tasarım kararı (ölçümden çıktı, varsayılmadı):** linear ve vercel
  token'ları `--color-*` adları taşıyor (`--color-accent`, `--color-bg-*`) ve
  kök köprü de `@theme` içinde `--color-accent` tanımlıyor → ön-eksiz üretim,
  köprüler yan yana import edildiğinde temel `bg-accent`'i sessizce marka
  paletine kaydırırdı. Kullanıcıya iki karar soruldu; seçilen model
  "mirror-prefixli `@theme` köprüsü" + "değer sınıfına göre kapsam".
- **Kapsam kuralı:** renk → `--color-*`, font ailesi → `--font-*`,
  `cubic-bezier` → `--ease-*`, gölge → `--shadow-*`, uzunluk → adında
  `radius` varsa `--radius-*`, `space|spacing|gap` varsa `--spacing-*`. Sınıf
  **DEĞERDEN** çözülür (ada değil): `--color-alpha: 255` renk değildir, bu
  yüzden `--font-weight-*` gibi bilinçli kapsam dışı namespace'ler `font`'a
  düşmez, gerekçeyle atlanır. Marka katmanı (`hds-`) ilk segment namespace
  değil ikincisi öyleyse düşülür; düşürme yuva üretmezse düşürülmemiş hâli
  denenir (sıra sabit → deterministik).
- **Çakışma bulundu ve çözüldü:** linear'da 3, primer'de 39 çakışma
  (`--blue` ↔ `--color-blue`, `--ansi-black` ↔ `--color-ansi-black`).
  Hakem kuralı: kısa anahtarı adında namespace'i AÇIKÇA taşıyan token alır;
  kaybeden yuva almaz ama DEĞERİ ön-koşul olarak dosyada kalır
  (`skip:key-collision`) — ölçülen değer kaybolmaz.
- **Sonuç (ölçülen):** stripe 556/710 · linear 168/398 · primer 1500/2051 ·
  vercel 19/19 = **2243/3178** yuva; dosyalar 40 kB / 9.5 kB / 100 kB / 2.3 kB.
  Kapsam dışı her token dosyanın sonundaki sayım bloğunda gerekçesiyle
  yazılır (`aliases + skipped = tokens` kapıyla kilitli → sessiz kayıp yok).
- **Kapı (B1–B7, fail-closed):** roster/köprü bütünlüğü (exit 2) · üretim
  birebirliği · **temel palet ayrıklığı** (kötü `bg-bg` senaryosunun sınıfı
  bu) · `var()`-only bağlantı · ön-koşulun aynayla birebirliği · sayım
  kilitleri · tek `:root` + tek `@theme` bloğu. pre-commit'te
  `check-mirror-bridges` (değişim-farkında, `files: ^design-system/`).
- **Canlı doğrulama (statik değil):** (1) gerçek Tailwind v4 derlemesi
  (postcss + `@tailwindcss/postcss`, kök köprü + dört ayna köprüsü yan yana
  import) — 20 probe sınıfının **20'si** üretildi, `--color-bg` çıktıda
  **tek** tanımla kaldı; (2) derlenmiş CSS tarayıcıda açıldı, hesaplanmış
  stiller: `bg-bg` → `rgb(14,17,22)` (temel `#0e1116` DEĞİŞMEDİ),
  `bg-accent` → `rgb(88,166,255)` (Linear'ın `#7170ff`'i kazanmadı),
  `text-linear-accent` → `rgb(113,112,255)`, `bg-stripe-accent-border-quiet`
  → `rgb(214,217,252)`, `bg-primer-accent-primary` → `rgb(13,103,49)`,
  `bg-vercel-background-100` → `rgb(255,255,255)`,
  `rounded-linear-12` → `12px`, `font-stripe-family` → `sohne-var,…`,
  `ease-primer-base-easing-ease` → `cubic-bezier(.25,.1,.25,1)`,
  `shadow-primer-avatar-shadow` → `rgb(13,17,23) 0 0 0 2px` (ayna
  değeriyle birebir).
- **Test:** `_calisma/CIKTI/test_mirror_bridges.py` **25** vaka — gerçek ağaç
  (kapı + `--check` + ayrıklık yeniden hesabı + `aliases` sayım kilidi +
  wiring) ve sahte ağaç (köprü yok → exit 2, elle düzenleme → exit 1,
  rostera yeni ayna → exit 2) + sentetik aynada kapsam/ad kuralları.
- **Yakalanan gerçek hata (öğrenme notu):** ilk üretimde `@theme` bloğu
  BOŞ çıktı — gruplama `tn.split("-")[1]` ile yapılıyordu ve `--color-…`
  adının `[1]`'i  boş string'dir. Gözle yakalandı; sayım kilidi (theme satır
  sayısı = `aliases`) artık bunu teste bağlıyor (`test_theme_line_count_…`).

### trend-db loader TDD turu 2 (2026-09-27) — dry-run'un makine-okunur yüzü + JS koşucusu

- **Başlangıç ölçümü:** 1. tur (`8a82cf8`) `--dry-run`'u prose kilitlemişti
  (Python 6 vaka), ama `apps/trend-db` içinde **tek bir test dosyası/koşucu
  yoktu** ve rapor `[DRY-RUN] etiket: değer` Türkçe **prose**'di → makine
  tarafında sözleşme değil, insan metni. Üstelik eksik kaynakta
  `fs.readFileSync`'in ENOENT'i `main().catch → console.error(e)` ile **ham
  Node yığını** olarak basılıyordu (`Error: ENOENT` + 9 çerçeve).
- **TDD kanıtı ÖNCE alındı (8/11 kırmızı):** 8. vaka yığını birebir gösterdi,
  9. vaka `bilinmeyen bayrak: --json` ile exit 2 verdi, 10. vaka ise
  **yanlış-sahte yeşil** çıktı. Kırmızı görülmeden uygulamaya geçilmedi.
- **Karar (1) — framework yok:** tek seam (CLI stdout/stderr/çıkış kodu) için
  jest/vitest eklemek denenecek yüzeyden büyük olurdu → `test/mini.mjs`
  (~80 satır, bağımlılık sıfır): `test/eq/ok/match/notMatch`, TAP-benzeri
  `ok N - ad (Xms)` / `not ok` + `--- mesaj`, sonra `# X/Y geçti`.
- **Karar (2) — `--json`:** prose insan içindir; tüketen sözleşme JSON'dur.
  `--json` prose'in **yerine** geçer (ikisi birden basılmaz) ve tek satır
  verir. Sayılar bir `DryRunSummary` nesnesinde **bir kez** hesaplanır, iki
  yüzey de ona bakar → ayrışma yapısal olarak imkânsız; çapraz-kapı testi
  (`test_json_numbers_match_prose_numbers`) bunu sayısal olarak da bağlar.
- **Karar (3) — `--json` tek başına anlamsız:** gerçek koşuda "eklenecek"
  ancak `ON CONFLICT DO NOTHING` sonrası bilinir → exit 2 +
  `yalnız --dry-run ile birlikte` (bilinmeyen-bayrak reddi DEĞİL, ikisi
  farklı gerekçe). Alan `insertedCount` değil **`insertAtMost`** diye adlandırıldı.
- **Karar (4) — `CliError`:** girdi/kullanım hatası → üst düzey yakalayıcı
  yalnız `message` basar; beklenmeyen hata `Error` kalır ve **yığınıyla**
  basılır. "Temiz hata" böylece tek yerde uygulanır (okunamayan kaynak, bozuk
  JSON satırı) ve program hatası sessizce yutulmaz. `errno` → Türkçe tek
  cümle (`dosya bulunamadı`); ham errno metni yığınla birlikte sızmıyor.
- **Kapsam kaybı kapandı (asıl risk):** `.mjs` dosyaları
  `test_coverage_report.py` keşfine girmiyor (yalnız `test_*.py`/`test_*.js`
  glob) ve `check-prettier-format` da `.mjs`'yi kapsam dışı bırakıyor
  (`.(js|jsx|ts|tsx|json)$`) → JS koşucusu `npm test`'e bağlı kalıp sessizce
  çürüyebilirdi (kimse koşmaz, kırılır, fark edilmez). Yeni pre-commit hook
  yerine **`_calisma/CIKTI/test_trend_db_js_runner.py`** mevcut fail-closed
  manifest'e alındı: (a) JS koşucusunu koşar ve yeşil değilse bloklar,
  (b) `MIN_KURULU_VAKA` eşiği boş/eksik koşuyu "hepsi geçti" göstermez,
  (c) yeni `*.test.mjs` eklenip `run.mjs` MODULES'e yazılmazsa bloklar,
  (d) TMP temizliğinin kaybolmasını görür (/tmp şişmesi).
  `sync_check_unit_tests.py --update` manifest + HOOK_COVERAGE'yi senkronladı.
- **Sonuç (ölçülen):** JS **11/11** yeşil (~3.1 s, 11 tsx alt süreci),
  Python `test_trend_db_contract` **18/18** (`TestTrendDbDryRun` 6 → 10 vaka),
  sarmalayıcı 3/3 (4.2 s). `prettier --check` dört dosyada da temiz.
- **Öğrenme (yanlış-sahte yeşil):** 10. vaka uygulama olmadan da geçiyordu —
  `--json` zaten "bilinmeyen bayrak" olarak exit 2 veriyordu. **Aynı çıkış
  kodu iki farklı gerekçeyi karşılayabilir.** Exit kodu + mesaj eşleşmesi
  yetmez; gerekçe de kilitlenmeli (`notMatch(/bilinmeyen bayrak/)`).
- **Öğrenme (prose sözleşme tuzağı):** prose'in sözleşme gibi davranması
  sessiz kırılma üretir (kelime/noktalama/sıra). Bu yüzden çift yüzey
  yazıldı ve ayrışma teste bağlandı — tip zaten ayrışmayı engellemez,
  engelleyen şey **testtir**.
- **Bekleyen:** RLS (`20260927193000`) + query-index (`20260927194500`)
  migration'ları hâlâ `prisma migrate deploy` bekliyor.

### precommit-orphans turu (2026-09-27) — yetim patch'e çift parmak-izi + özel uyarı

- **Başlangıç ölçümü:** kapı (`check_precommit_orphans.py`, hook 19) olay
  arşivini (`recovery_patches_*`, 4 dizin / 42 patch) **sha256 ile** tarıyor ve
  eşleşmeyi yetim listesinin **içine gömülü bir satır** olarak basıyordu.
  İki zayıf nokta: (1) gömülü satır scroll'lanıp geçilebilir — bir uyarı
  ancak görüldüğünde işe yarar; (2) tek özet yalnız "birebir aynı" sorusuna
  cevap veriyor, "özet aynı ama içerik farklı" durumunu (kısmi kopya / arşiv
  bozulması) hiç göstermiyor.
- **Karar (1) — md5 ikinci sinyal, oracle DEĞİL:** istenen md5 karşılaştırması
  eşleşmeyi güçlendirmek için değil, **ikinci sinyâl** olarak eklendi. Temel
  kural: bilinen-olay etiketi **yalnız sha256 birebir eşleşmesinden** doğar.
  md5 çakışabildiği için (bilinen saldırı yüzeyi) onu ikinci otorite yapmak
  kapıyı zayıflatırdı; bunun yerine sha256 düştüğünde ayrı bir tanı
  (`ZAYIF-PARMAK-İZİ ÇAKIŞMASI`) üretiyor: "özet aynı, içerik farklı". Yani
  ikinci özet hiçbir zaman birincinin yerine geçmiyor, sadece onun göremediği
  durumu görünür kılıyor. Sıra `classify()` içinde tek yerde yazılı.
- **Karar (2) — özel uyarı bloğu çıktının en üstünde:** taze/yetim ayrımı
  kaldırıldı, iki eşleşme TEK `BİLİNEN OLAY PARMAK-İZİ (KNOWN-INCIDENT)`
  bloğunda toplandı; her eşleşme için patch adı + arşiv konumu + **sha256 ve
  md5** yazılıyor (elle doğrulanabilirlik: olay notlarına kısa md5
  yapıştırılabilir). Taze olanların altında "bloklamaz" gerekçesi duruyor —
  kurtarma penceresi felsefesi korundu (exit 0).
- **Karar (3) — tek okuma, iki hesap:** `archive_fingerprints()` artık
  `Fingerprints(sha256, md5, archives, patch_count)` döndürüyor. İki ayrı okuma
  olsaydı dosya arada değişseydi haritalar birbirini tutmaz ve "birebir aynı"
  yargısı sessizce yanlışlaşırdı.
- **Eşleşme yokken gürültü yasağı:** digest'ler yalnız iki özel blokta basılıyor.
  Yeni test, bilinmeyen bir yetimde 32-hex bile görünmediğini kilitliyor —
  kırmızı çıktıda her satır anlam taşımalı, yoksa operatör alışkanlığı
  kaybedilir.
- **md5 ve FIPS:** `hashlib.md5(data, usedforsecurity=False)` — kimlik etiketi
  üretir, bütünlük güvencesi sağlamaz; FIPS çekirdeklerde düz `md5()` reddedilir.
- **TDD (kırmızı önce):** 13 var olan yeşil + 5 yeni kırmızı (özel blok yok,
  md5 basılmıyor, `Fingerprints`/`classify` yok, boş arşiv uyarısı yok).
  Sonra 18/18 yeşil. Çarpışma dalı gerçek md5 çakışması gerektirdiği için
  (üretim-dışı) **saf `classify()` seam'i** üzerinden kilitlendi; CLI aynı
  sınıflandırmayı kullandığı için ayrışma yok. CLI'de de canlı blok çıktısı
  elle denetlendi (birebir kopya + sahte zayıf eşleşme birlikte).
- **Test:** `test_check_precommit_orphans.py` **13 → 18** (özel blok, çift
  digest, md5'in etiket üretmemesi, gürültü yasağı, iki haritanın da her
  arşivi görmesi + patch sayımı tutarlılığı, boş arşiv iki haritayı da
  körleştirir). `AGENTS.md` operatör kuralı güncellendi.

### commit'lenmemiş iş envanteri (2026-09-27) — risk ölçüldü, commit'lenmedi

- **İstek:** "bekleyen tüm oturum işini mantıksal gruplara ayırıp commit'le
  (tip-güvenli loader, 50 hook'lu zincir, parmak-izi kapısı dahil)". Adı
  geçen üç kalemin **üçü de zaten commit'liydi**: `07e22aa` (tip-güvenli
  loader'ın `InputJsonValue` guard'ı + chain 47→50; bugün 59 hook),
  `a624cdb` + `11ea4c1` (parmak-izi kapısının üç turu). Ana çalışma ağacı
  `git status --porcelain -uall` → **boş**. Yani commit'lenecek kendi işimiz
  yoktu; commit üretmek iş değil **uydurma** olurdu.
- **Ölçüm yöntemi (varsayım değil):** (1) `git worktree list` + her
  worktree'nin `status -uall`; (2) `git stash list` + her stash'in `^3`
  (gizli untracked) ağacı; (3) **blob geçmişi testi** — `git log --all
  --find-object=<blob>`: içerik depoda daha önce commit'lenmiş mi?; (4)
  `git diff --numstat HEAD stash@{N}` (+ = stash'ta yeni satır).
- **Bulgu 1 (uncommitted iş gerçek, ama başka thread'lerde):**
  `feat/github-site-sample` worktree'sinde 8 untracked dosya; 3'ü depoda
  **hiç yok** (`sample.html`, `check_github_primer_sample.py`, ADR-0001) —
  worktree silinirse kalıcı kaybolurlar. Sahiplik belirsiz → dokunulmadı.
- **Bulgu 2 (tehlike ters yöndeydi):** iki stash "commit'lenmemiş iş" gibi
  görünüyor ama tabanları HEAD'den yüzlerce commit geride. `numstat`
  **hiçbir dosyada saf ekleme göstermiyor**: `verify.yml` −892,
  `.pre-commit-config.yaml` −276 (**50 hook'lu zincir**), `README.md` −244,
  `check_unit_tests.list` −51 ve **+0**. Gizli untracked ağaç da yeni iş
  değil: `.venv_z3/`, `__pycache__/`, `.build/`, `TOOLKIT/` → hepsi
  `.gitignore`'da (18/68/140) ve yeniden üretilebilir; `rc-review` arşivi
  ise `028d744`'ten **önceki** (normalize edilmemiş) sürüm. Yani "kaybedelim
  diye commit'le" tersi olurdu: ~1 700 satır silinirdi.
- **Bulgu 3 (commit'lenmemiş değil, uygulanmamış):** RLS + query-index
  migration'ları dosya olarak commit'li ama `prisma migrate deploy`
  çalıştırılmamış — "RLS hazır" iddiası canlı DB'de henüz doğru değil.
- **Çıktı:** `docs/UNCOMMITTED-INVENTORY.md` — üç kalem, kanıt tablolarıyla
  (numstat, blob geçmişi, worktree sahipliği) ve bekleyen kararların sahibi
  belirtilerek. Risk silinmedi, **görünür hâle geldi**; envanter de
  commit'lendiği için unutulamaz. Kayıt, kapının kendisi kadar değerlidir.

### oturum kapanışı (2026-09-28) — kararlar uygulandı, kapı teşhis edildi

- **Kararlar (kullanıcıya soruldu):** P1 → worktree dosyalarını kendi dalında
  commit'le; P2 → stash'lere dokunma; P3 → migration'ları canlıya uygula.
  Üçü de yürütüldü. P1 = `2ef1821` (`feat/github-site-sample`, 9 dosya,
  51 hook yeşil, 0 Failed, worktree artık tümüyle temiz). P3 = aşağıda.
  P2 = tek dosya değişmedi; kanıt envanterde §B.
- **Kapı teşhisi — ileri sürülen hipotez çürütüldü.** `check-precommit-orphans`
  exit 1'in kaynağı "kapsanmamış 24. patch" DEĞİL, kapının **tasarımı**ydı:
  `main()` her patch'in yaşını `WINDOW_HOURS = 24` ile karşılaştırır ve eskiyi
  yetim sayar; `KNOWN` etiketi yalnız uyarı bloğu üretir, **muafiyet
  üretmez**. İki test bunu açıkça sabitler
  (`test_known_incident_fingerprint_gets_recovery_warning`,
  `test_known_incident_prints_dedicated_warning_block` → `returncode == 1`).
  Ölçüm: cache'te 24 patch; 23'ü arşivle sha256 birebir (11 benzersiz
  içerik), 1'i (`patch1790561449-4597`, 5.8 saatlik) taze ve eşleşmesiz.
  Yani **arşivlemek kapıyı açmıyor**; cache temizlenmedikçe kırmızı kalıyor.
- **Çözüm: karantina, silme değil.** Kural tek: sha256 arşivle birebir
  eşleşen dosya taşınır, eşleşmeyen dokunulmaz. 23 patch
  `~/.cache/pre-commit-orphans-quarantine-20260928/` altına gitti (MANIFEST
  ile geri-alma kaydı), taze olan cache'te kaldı → kapı `exit 0`, 18 test
  `OK`, cache'te tek dosya. Bilgi kaybı yok: her taşınan dosyanın arşivde
  byte-eşdeğeri var.
- **Genel ders:** kapıyı yeşile çevirmenin yanlış refleksi kapıyı gevşetmek.
  Önce "kapı haklı mı" ölçülür — burada haklıydı; eksik olan kapı değil,
  **ortamın durumu**ydu. Düzeltme ortamda yapıldı, sözleşmede değil.
- **`raw.json` (P1) — beklenmedik sonuç:** worktree'deki kopya
  prettier-uyumsuzdu. `--write` sonrası kanonik JSON sha256 **değişmedi**
  (`efb36bca…`) ve dosya 88 589 → 87 689 bayt ile main'deki sürümle
  **byte-eşit** çıktı. Yani "iki dalda farklı raw.json" bir içerik
  ayrışması değilmiş, yalnız bu dalda biçimin uygulanmamış olmasıymış;
  main'in sürümünü kopyalamak gereksizdi.
- **Çalışma-zamanı artefaktları:** worktree'de `history.jsonl`, `.sha256`,
  `runs/` untracked görünüyordu; sebep dalın `.gitignore`'unun 85-87
  satırlarından **önce** olması. `.gitignore` onları zaten repo dışı veri
  sayıyor → commit'e alınmadı, **silinmedi**, `/tmp/worktree-artifacts-20260928/`
  altına taşındı.
- **`klayers.json`:** `verify_delivery.py --klayers-out` üretimi bir koşum
  sidecar'ı; tüketicisi (`verify_mcp/server.py`) onu bir *preview dir*'den
  okuyor, `CIKTI/`'den değil; zaman damgası/provenance yok → commit'lenmedi,
  gerekçesi envanterde §F'ye yazıldı.
- **Araç tuzağı (yeni, AGENTS.md'ye yazıldı):** uzun hook zincirini (7-10 dk)
  ön planda koşmak araç zaman-aşımına takılıyor ve **süreç grubunu
  öldürüyor**. `nohup … &` YETMİYOR (aynı süreç grubunda kalır) — ilk deneme
  tam da böyle yarıda öldü. Çözüm: `subprocess.Popen(...,
  start_new_session=True, stdin=DEVNULL)` + log dosyası, sonra kısa
  yoklamalar; mesajı da `git commit -F <dosya>` ile vermek heredoc/tırnak
  hasarını tümden eliyor. Ölü koşum yeni yetim patch bırakmadı (ölçüldü).

### dashboard-next tip-test katmanı (2026-09-28) — "sözleşme hâlâ aynı mı?"

- **Sorun:** `tsc --noEmit` "bu atama geçiyor mu" diye sorar, "sözleşme AYNI mı"
  diye sormaz. Atanabilirlik eşitlikten gevşek olduğu için bir union'a varyant
  eklenmesi, bir alan adının değişmesi ya da `API_BASE` fallback'inin düşmesi
  derlemeden GEÇİYORDU ve panoyu sessizce bozuyordu (eksik alan hata vermez,
  "—" basar). Commit `0ecc884` (14 dosya, 55 hook yeşil, 0 Failed): `test-d/`
  altında 11 pozitif iddia + 14 negatif direktif + iki geçişli koşucu.
- **Neden iki geçiş:** `@ts-expect-error` yalnız "bir hata var" der. `countTone`
  ikinci parametresi `string`e gevşetilseydi `countTone(1, "none")` yine hata
  verirdi — ama BAŞKA bir hata. Koşucu `test-d/`yi kopyalayıp direktifleri
  kapatıyor ve tsc'nin bastığı tanı KODUNU etiketle karşılaştırıyor. Üç ihlal
  fail-closed: etiketsiz direktif, eşleşmeyen kod, İDDİA EDİLMEYEN tanı.
  Bağımlılık yok (stdlib + yerel tsc).
- **`AssertEqual` tek parça YAZILAMAZ (ölçüldü):** generic bir takma adın
  gövdesi çözülmemiş parametrelerle denetlenir, `Equal<A, B>` o anda `boolean`a
  düşer ve `true` kısıtını ihlal eder → `TS2344`. Kısıt denetimi çağrı yerinde
  olmak zorunda; desen `Assert<Equal<A, B>>`. Gerekçe `test-d/assertions.ts`
  başlığında, derleyicinin bastığı hata metniyle birlikte yazılı.
- **İnşa sırasında dört altyapı hatası bulundu (hepsi kilitlendi):**
  1. `@ts-expect-error-disabled` YETMİYOR — tsc direktifi alt-dize olarak
     arıyor, "kapatılmış" sanılan biçim susturmaya devam ediyordu (geçiş 2
     sıfır tanı bastı). Çözüm: `@`i düşürmek.
  2. `re.MULTILINE` olmadan satır-başı çapası yalnız metnin ilk karakterinde
     eşleşiyordu → `strip_directives` sessiz no-op. Üstelik zayıf kontrol
     (`"ts-expect-error" in metin`) her zaman doğru olduğu için yeşil kaldı;
     kontrol `@`in YOKLUĞUNA çevrildi.
  3. Yorum ön-eki (`//`) yutulunca satır yorum olmaktan çıkıp sözdizimi
     bozuluyordu (TS1005/TS1127 yağmuru) → yakalama grubu ön-eki korur.
  4. İddia anahtarı direktif satırı sanıldı; direktif BİR SONRAKİ satırı
     susturduğu için tüm iddialar tek satır kaydı → çeviri tek yerde
     (`parse_annotations`).
- **Etiketler ölçümle yazıldı, varsayımla değil:** 14 koddan üçü düzeltildi —
  `"PASS"` → TS2322 değil **TS2820** ("did you mean 'pass'?"), `verdicts`
  → TS2339 değil **TS2551** ("did you mean 'verdict'?"), bilinmeyen rozet tonu
  → TS2353 değil **TS2322**. Tip sistemi typo'yu yakalamakla kalmıyor,
  doğrusunu da öneriyor.
- **Mutasyon sondası (fail-closed kanıtı):** sözleşmeyi gevşet → pozitif iddia
  düştü; yasağı kaldır → TS2578; `countTone`a zorunlu 3. parametre ekle →
  **geçiş 1 yeşil kaldı**, yalnız geçiş 2 "kod uyuşmuyor: beklenen TS2345,
  gelen TS2554" diyerek yakaladı. Üçünde de ağaç sha256 ile geri yüklendi.
- **Kablolama:** `check-dashboard-typecheck` iki katmanlı ve önce koşucunun
  kendi selftest'ini (18 vaka) koşuyor — parser sessizce bozulursa iddialar
  denetlenmeden "yeşil" görünmesin. Modül testleri 18 → 26 (sahte tsc ile
  hermetik boru hattı vakaları). `test-d` app tsconfig'inden dışlandı ki
  üretilen `stripped/` kopyası `tsc --noEmit`i kirletemesin.

### "Commit'lenmemiş iş" thread'i kapandı (2026-09-28 son ölçüm)

- **Dört worktree de tertemiz**; ana ağaçta tek untracked `klayers.json`
  (bilinçli, envanterde §F). Yani commit'lenmemiş oturum işi **kalmadı** —
  `git status --porcelain -uall` ana ağaçta ve üç worktree'de de boş.
- Koruma kalemleri commit'li: 59 hook'lu zincir (son dokunuş `0ecc884`),
  parmak-izi kapısı + 18 testi (`11ea4c1`). Kapı `exit 0`; cache'te yalnız
  taze ve eşleşmesiz 1 patch (`patch1790561449-4597`, karantina kuralı gereği
  dokunulmadı).
- **Kalan risk sınıfı artık FARKLI:** üç dal main'e merge değil
  (`codex/ci-cache6-setup-python7-20260925` 5, `feat/github-site-sample` 7,
  `feat/plist-info-line` 20 commit ileride). Bunlar *commit'li* iş: "kaybolma"
  değil "teslim edilmedi" riski. Bu thread'in konusu değil, karar gerektirir.
- **Ders:** "en büyük risk commit'lenmemiş iş" çerçevesi doğruydu ve artık
  ölçülebilir biçimde YOK. Aynı istek tekrar geldiğinde cevap iş uydurmak
  değil, ölçümü ve kararı tazelemek: `status` × 4 ağaç + kapı + stash listesi.

### trend-db loader TDD turu 3 (2026-09-28) — "en çok" sınırı kesin sayıya çevrildi

- **Sorun:** dry-run "eklenecek (en çok): 36" diyordu; GERÇEK ise **0**'dı.
  Sınır dili yanlış değildi ama karar için işe yaramazdı: 269 satırlık arşive
  karşı mirrored 36-satırlık pencere tamamen zaten yüklüydü. Loader'ın kendi
  docstring'i itiraf ediyordu: *"Mevcut satırlarla çakışma bağlantısız
  ÖLÇÜLEMEZ"*. Boşluğu `--check-db` (salt-okunur DB okuması) ve
  `--keys-file=<yol>` (kimliksiz JSONL anlık görüntüsü) kapatır.
- **Kırmızı önce yazıldı:** `test/check-db.test.mjs` **18 vaka** (bayrak
  sözleşmeleri, `--keys-file` kesin sayıları, prose/JSON, iki canlı
  `--check-db`), `test/helpers.mjs` paylaşılan harness, `mini.mjs`e `Skip`
  (ortam yokluğu "geçti" sayılmaz, ayrı sayılır), `run.mjs` MODULES kaydı,
  `dry-run.test.mjs` helpers'a bağlandı. Kırmızı doğru sebeplerle düştü
  (`bilinmeyen bayrak: --check-db`, `beklenen "none", gelen undefined`).
- **Ölçüm: 12/29 → 29/29.** `load.ts`te: iki bayrak `KNOWN_FLAGS`/ön-ek
  eşleşmesiyle tanınır; ikisi de **yalnız `--dry-run`** (aksi çıkış 2), ikisi
  **birlikte verilemez** (tek kaynak), `--keys-file` **`=` biçimi şart**
  (boşluklu yazım yolu konum argümanı sanardı → çıkış 2).
- **Değişmezler sözleşmeye yazıldı:** `insert + alreadyPresent = candidates`;
  `skip = invalidSkipped + duplicatesInFile + alreadyPresent`;
  `insert ≤ insertAtMost`; `skip ≥ skipAtLeast`. Ölçüsüz modda
  `alreadyPresent = 0` olduğu için kesin değerler sınırlara **eşit** çıkar —
  yeni alanlar geri uyumludur. Eşleşme `ts` VEYA `source_row_sha256`
  kümesinden; aday dosya-içi çakışmalardan arınmış olduğu için bir aday
  birden çok satırla eşleşse bile **bir kez** sayılır.
- **İki sessiz yeşil yakalandı:** (1) determinizm vakası iki koşu da aynı
  HATAYI verse stdout eşit olurdu → `eq(a.code, 0)`/`eq(b.code, 0)` eklendi;
  (2) `liveCredentials()` `.env`teki **tırnaklı** değeri ham geçiriyordu →
  host `base` gibi anlamsız bir parçaya düşüp `P1001` verdi; dotenv
  sözleşmesi gereği tırnaklar sadeleştirildi (ham değer geçirmek bağlantı
  dizesini bozar).
- **Canlı ölçüm (salt-okunur, kalıcı iz yok):** `--dry-run --check-db` →
  `çakışma kaynağı: db (269 satır) · zaten var olan aday: 36 ·`
  `eklenecek (kesin): 0 · atlanacak (kesin): 36`. İki ardışık koşu AYNI
  sayıları görüyor — dry-run'ın yazmadığının kanıtı. Yani eski raporun
  "en çok 36" dediği iş aslında **sıfır**dı.
- **Diller ayrıldı:** ölçülmüş modda "(en çok)"/"(en az)" ve "bu raporda
  YOK" bilinçli olarak kaybolur — kesin sayı varken sınır dili yanıltıcıdır.
  `--check-db` kimlik yokken belirsiz rapora düşmez: **çıkış 1** + stderr'de
  `DATABASE_URL`, stdout'a hiç `[DRY-RUN]` basılmaz.
- **Kapılar:** `npm test` **29/29** (kimlik yoksa 27 + 2 `skip`),
  `test_trend_db_contract` **21/21** (yapısal test `--check-db` guard'ına
  sıkılaştırıldı, +3 yeni vaka), `test_trend_db_js_runner` 3/3,
  `sync_check_unit_tests --check` temiz. README'ye kesin-ölçüm bölümü +
  JSON alan tablosu (yeni 5 alan) eklendi.

### dev_bootstrap uçtan uca `--full` (2026-09-28) — kurulum + temel batarya

- **Boşluk:** `dev_bootstrap.sh` başlığında "fresh-checkout'u yeşil-**bataryaya**
  taşıyan tek komut" diyordu ama yalnız araç-kümelerini kuruyordu; batarya ayrı
  bir işti. Kapanan tur: uçtan uca `--full` (pinli venv + 3 node ağacı + batarya).
- **Neden `--full`, neden varsayılan değil (ölçülmüş tuzak):** batarya manifesti
  (`check_unit_tests.list`) `test_dev_bootstrap.py`yi de içerir ve o test betiği
  **bayraksız** koşar. Batarya varsayılan yola konsaydı: test → betik → batarya →
  test **özyinelemesi** olurdu. İkinci savunma: batarya `LEIBNIZ2_IN_BATTERY=1`
  ile başlatılır, içerideki `--full` reddedilir (test edilmiş davranış).
- **Ölçüm (yerel macOS):** `bash _calisma/dev_bootstrap.sh --full` → 4 unit
  "up to date" → `check-unit-tests: 181 test dosyası PASS` → `BOOTSTRAP OK`,
  **rc=0, 394 sn**. Batarya tek başına 346 sn (≈6 dk) — varsayılan akışın
  (kurulum-only) hızlı kalması bu yüzden bilinçli bir tasarım, gecikme değil.
- **Seam:** `LEIBNIZ2_BOOTSTRAP_BATTERY` batarya betiğini ezer → sözleşme
  testleri **sahte** batarya enjekte eder (gerçek batarya dakikalar sürer ve
  kendini içerir). Sözleşme **kablolamadır**, bataryanın kendisi değil:
  yeşil → `BOOTSTRAP OK` son satır; kırmızı → `BOOTSTRAP FAIL`, `BOOTSTRAP OK`
  basılmaz (fail-closed); batarya-içi → ret.
- **Kapılar:** `test_dev_bootstrap.py` 6 → **12 vaka** (yeşil), shellcheck
  temiz, `sync_check_unit_tests --check` temiz. README "Fresh checkout
  bootstrap" üç adımlı tablo + `--full` ile güncellendi ("üç" → "dört"
  araç-kümesi: venv_z3 + 3 node ağacı — `.gitignore` ile doğrulandı).

### unstaged-delta kapısı (2026-09-28) — yazılı kural artık ZORLANIYOR

- **Kural → kapı:** yalnız belge olan "commit öncesi sıfır unstaged izlenen
  delta" kuralı artık fail-closed bir kapı: `check-unstaged-delta`
  (`_calisma/CIKTI/check_unstaged_delta.py`), zincirin İLK hook'u.
- **Naif yazım İŞE YARAMAZ (ölçüldü):** pre-commit 4.3.0 `run.py` →
  `stash = not args.all_files and not args.files`. Gerçek `git commit`'te stash
  AÇIKTIR: kapı çalışırken ağaç index'e eşitlenir ve `git diff --name-only`
  **BOŞ** döner. İzole scratch repo'da kanıtlandı: karışık ağaçta commit
  GEÇTİ, hook'un gördüğü diff boştu — saf `git diff` kontrolü sessiz yeşil verir.
- **Gerçek sinyal:** stash patch'i YALNIZ unstaged delta varsa yazılır
  (`_unstaged_changes_cleared`: retcode 0 → erken dönüş), adı
  `patch<epoch>-<pid>`; buradaki pid pre-commit sürecidir ve kapının ATA
  zincirindedir (ölçüldü: zincirde `-72274` eşleşti). Kapı bu yüzden iki
  sinyali BİRLEŞTİRİR: görünür `git diff` (manuel `--all-files`/`--files`,
  pre-commit dışı çağrı) + ATA-pid'li stash patch'i. **Ada göre eşleştirme
  yapılmaz:** pre-commit patch'leri hiç silmez, aynı dizinde yetimler birikir
  (ölçümde 3 patch vardı, ikisi yetim) → yabancı pid'ler yanlış-pozitif üretirdi.
- **Kapsam:** yalnız İZLENEN dosyalar; untracked dosyalar stash'e girmez
  (test edildi — spec dışı bırakıldı).
- **Çürüme-guard'ı:** `test_check_unstaged_delta.py::
  test_mixed_tree_commit_is_blocked_and_delta_survives` gerçek bir
  `git commit` koşar: commit BLOKE olmalı VE unstaged delta stash'ten geri
  gelmeli (kayıp yok). pre-commit patch adlandırmasını değiştirirse bu test
  kırmızıya düşer — kapı sessizce çürüyemez.
- **Ölçüm:** 14 vaka (sinyal / kirlilik / yanlış-pozitif / entegrasyon /
  gerçek-repo tutarlılığı), hepsi yeşil. Canlı doğrulama: gerçek repoda kirli
  ağaçta `pre-commit run check-unstaged-delta --all-files` → `Failed`, bekleyen
  4 dosyayı adlar ve `git add` / `git stash` çözümünü söyler.
- **Düzeltilen iddia:** "ilk sırada koşar → dakikalar süren zincir başlamaz"
  YANLIŞ — `fail_fast` kapalı, pre-commit tüm hook'ları koşar. Gerekçe "hata
  ilk görünür + karar sonraki hook'ların stage'lemesinden kirlenmez" olarak
  düzeltildi; süre kazancı iddia edilmiyor.
- **Kablolama:** kapı zincirin ilk hook'u + başlık dokümantasyonu;
  `sync_check_unit_tests.py --update` testi manifest + HOOK_COVERAGE'a ekledi;
  `test_gate_coverage_sync` / `test_test_coverage_report` /
  `test_gen_precommit_report` / `test_sync_check_unit_tests` yeşil (dokümana
  yazılmadı: hiçbiri kirli ağaçta yan etki üretmedi).

### dashboard-next açık tema smoke'u (2026-09-28) — palet artık ÖLÇÜLÜYOR

- **Boşluk (ölçüldü):** `apps/dashboard-next` panosunun AÇIK TEMASI hiçbir
  gate tarafından ölçülmüyordu. `test_dashboard_playwright_smoke.py` ile
  a11y-gate/CWV job'ları YALNIZ `preview.html` yüzeyini (preview_server)
  tarar; `test_surface_cwv_report.py` dashboard-next'i ölçer ama tema
  parametresiz → yalnız varsayılan koyu palete bakar. Köprüdeki
  `:root[data-theme="light"]` bloğu silinse, gölgelense ya da yalnız
  tüketilmeyen bir sheet'te kalsa HİÇBİR şey kırmızıya düşmezdi: pano
  "açık tema" derken koyu kalırdı (hata yok, sessiz boşluk).
- **Ön koşul doğrulandı:** dashboard-next kaynağında koda gömülü renk
  literali YOK (ölçüm: 0 eşleşme; `check-design-tokens` contract 5/8 bunu
  zaten fail-closed kilitler) → tema anahtarı çevrilince paletin dönmesi
  *beklenir*. Bu tur o beklentiyi ölçüye çevirir.
- **Kablolama:** `dataset.theme` hiç yazılmıyordu. Eklenen: `lib/theme.ts`
  (saf çözümleyici), `components/ThemeInit.tsx` (istemci `useEffect`),
  `app/layout.tsx` (bağlama). Sözleşme `preview.js`'in AYNISI: geçerli
  `?theme=` sorgusu saklı tercihi EZER ve KALICI OLMAZ; yoksa
  `localStorage[dashboard-theme]`; o da yoksa `dark` (CSS `:root` ile aynı →
  ilk boyamada kayma yok). Küme `dark|light` ile sınırlı: `stripe` varyantı
  ayrı sheet'tir, dashboard-next onu import ETMEZ.
- **Neden istemci tarafı:** App Router'da kök layout `searchParams` görmez
  (yalnız sayfalar görür) ve "override kalıcı olmasın" zaten istemci
  sözleşmesidir. Sunucuda çözmek için middleware/inline script gerekirdi;
  inline script ayrıca nonce/CSP yüzeyi doğururdu.
- **Beklenen renkler koda GÖMÜLMEDİ:** `design-system/tailwind.css`'ten
  okunur (koyu `:root` + `:root[data-theme="light"]`, `--bg`/`--fg`) ve
  `css_rgb()` ile `getComputedStyle` biçimine çevrilip karşılaştırılır.
  Sabit ton yazsaydık test "panonun rengi şu" derdi; ölçülen iddia
  "panonun rengi TOKEN'ın değeri" — sheet değişince test takip eder.
- **İki katman:** (a) sözleşme (tarayıcısız, her yerde koşar): tüketilen
  sheet'te açık blok var mı, açık/koyu palet GERÇEKTEN FARKLI mı (yoksa
  canlı smoke vakum olur), köprü ↔ tokens.css ayrışmış mı, `data-theme`
  kablosu takılı mı, `dashboard-theme` anahtarı `preview.js` ile aynı mı,
  `hex_to_rgb` bozuk token'da sessizce 0'a düşmek yerine yükseliyor mu;
  (b) canlı (Playwright): `/` koyu token'ları, `/?theme=light` açık
  token'ları uygular; override KALICI OLMAZ; konsol hatası yok; pano kabuğu
  (marka) görünür — yani hata sayfası ölçülmüyor.
- **Drift önleme:** sunucu kablosu KOPYALANMADI — `preview_server.py` +
  `next start` başlatma sırası, argümanları ve `terminate`
  `test_surface_cwv_report.py`'den import edilir. İkinci bir başlatma hattı
  yazsaydık biri sessizce sürüklenir ve bu smoke "panoyu" ölçmezdi.
- **Ölçüm hatası bir kez GERÇEKTEN kırmızıya düştü ve doğru teşhisi verdi:**
  ilk koşumda 3 canlı vaka düştü — `.next` derlemesi `ThemeInit`'ten eskiydi,
  yani `next start` önceden derlenmiş bundle'ı sundu ve `data-theme` hiç
  yazılmadı. `npm run build --prefix apps/dashboard-next` sonrası 9/9 yeşil
  (13,3 sn). Bu yüzden timeout artık stale-build teşhisi içeren adı konmuş
  bir hata basıyor, sessiz 15 sn bekleme değil.
- **Kablolama/CI:** dosya `check_unit_tests.list` DIŞINDA
  (`sync_check_unit_tests.EXCLUDE`) — Next boot'u pre-commit'in dosya başına
  bütçesini aşar. `CHECK_EXEMPT`'e eklendi (kardeşleri
  `test_dashboard_playwright_smoke.py` / `test_dashboard_csp_nonce.py` gibi,
  çünkü `--check` YALNIZ pre-commit hook kapsamına bakar) ve
  `CI_JOB_COVERAGE["dashboard-next"]` ile kayıtlı. verify.yml'in
  `dashboard-next` job'ına (panoyu ZATEN derleyen tek job) pinli Playwright +
  Chromium + `Light-theme smoke — dashboard-next (fail-closed)` adımı eklendi;
  derleme aynı job'da yapıldığı için smoke bu commit'in artefaktını ölçer.
- **Yeşil bırakılanlar:** `check-design-tokens` (OK — açık tema 20 var,
  köprü+copy-drift temiz), `check-dashboard-typecheck` + tip-testleri
  (14 direktif; tema sözleşmesi için 3 yeni tip iddiası), prettier (3 dosya
  --write), actionlint (4 workflow RC=0), `check-action-pins`,
  `sync_check_unit_tests --check`, `test_coverage_report --check`,
  `test_gate_coverage_sync`, `test_test_coverage_report`,
  `test_gen_precommit_report`, `test_sync_check_unit_tests`.
- **Kapsam dışı bırakılan:** başlığa bir TEMA DÜĞMESİ eklemek (kullanıcı
  etkileşimi + durum yönetimi ister; smoke'un iddiası paletin dönmesi,
  düğmenin varlığı değil) ve `stripe` varyantını dashboard-next'e taşımak
  (ayrı sheet importu + köprü kararı gerektirir).

### PanelCard bileşimi (2026-09-28) — yüzey dizgesi beş dosyadan tek bileşime

- **Ölçülen tekrar:** `panelCard()` + başlık dizgesi + `CardHeader`/
  `CardContent` BEŞ dosyada elle kuruluyordu: `VerdictCard`, `RunsTable`
  (trend sayfası ve `@trend` slotu ondan beslenir), hata sınırı
  (`app/error.tsx`) ve iki akış iskeleti (`@verdict/loading.tsx`,
  `@trend/loading.tsx`). Başlık satırı yerleşimi
  (`flex flex-row items-baseline justify-between`) ayrıca VerdictCard ile
  verdict iskeletinde kopyalanmıştı. `panel-style.ts` kuruluş gerekçesinin
  ("aynı dizge üç dosyada") bileşen tarafındaki karşılığı.
- **Somut bedeli (ölçüldü):** hata sınırı `Card`ı doğrudan kullandığı için
  `CardHeader`/`CardContent`in `px-(--card-spacing)` dolgusunu atlıyordu.
  Tarayıcı ölçümü: kabuğun `padding-left/right = 0px`, `padding-top = 14px`
  (`Card` yalnız `py` verir) → içerik kartın yan kenarına değiyordu. Bileşime
  geçtikten sonraki ölçüm: `contentPaddingLeft = 14px`, `contentInsetLeft = 1`
  (1px `--err` kenarı).
- **Yeni bileşim:** `components/PanelCard.tsx` — dört parça, her birinin TEK
  işi: `PanelCard` (kabuk; `tone: default | error`), `PanelCardHeader` (yalnız
  başlık SATIRI yerleşimi), `PanelCardTitle` (gerçek `<h2>`, `panelLabel()`
  stilinde), `PanelCardContent` (yatay dolgunun tek kaynağı). Desen shadcn
  `Card` ailesinin aynısı; iki sapma bilinçli: ton repo token'larına bağlı bir
  varyant, başlık `div` değil `<h2>` (bölüm hiyerarşisi — a11y).
- **`title`/`meta` prop'u bilinçli olarak YOK.** İlk taslakta vardı; iskeletler
  başlık yuvasına metin yerine nabız çubukları koyduğu için `title`ı
  opsiyonel yapmak gerekiyordu, bu da aynı yuvayı iki farklı yolla
  doldurulabilir kılıyordu. Yerleşim yuvası + `children` tek yol bırakır.
- **Hata yüzeyi artık varyant:** `panelCard` cva tablosuna `tone` eklendi
  (`error: "border border-err bg-tint-err-bg ring-0"`). Çağrı yerindeki
  `cn(panelCard(), "border border-err …")` dizgesi kalktı — aynı yüzey iki
  dosyada iki farklı dizge olabiliyordu.
- **Kapı ısırdı (beklenen):** `test-d/negatives.test-d.ts` `panelCard({ tone:
  "pass" })` için TS2353 bekliyordu ("varyantı yok"); ton eklendiği için hata
  TS2322'ye döndü. Test KOD EŞLEŞMESİNİ pinladığı için kırmızıya düştü ve
  sözleşme bilinçli güncellendi — iddia artık daha güçlü: "yüzey tonu ile
  KARAR tonu ayrı sözlüklerdir" (`"pass"` bir `PanelTone` değil).
  `contracts.test-d.ts`'e 6 iddia eklendi (PanelTone kümesi, ton
  opsiyonelliği, başlığın tam `<h2>` prop'ları olması, header'ın yuva olması,
  içeriğin children alması, `panelCard()`nin varyantsız çağrılabilirliği).
- **Çalışma anı kanıtı — üç yol da ölçüldü:**
  * mutlu yol (smoke): `/` iki başlığı basar — "Son Koşum", "Son 5 Koşum",
  * hata sınırı (ölü port): `cardBg = rgba(248,81,73,.15)` (`--tint-err-bg`),
    `borderLeftColor = rgb(255,123,114)` (`--err`), içerik 14px içeride,
  * iskeletler (ASILI API — kabul edip yanıt vermeyen soket): 2 kart, 2
    `aria-busy` bölgesi (`Son koşum yükleniyor`, `Koşum geçmişi yükleniyor`),
    `<h2>` YOK (yuva metin değil çubuk taşır), konsol hatası yok.
  * Ölçüm notu: kapalı port iskeleti GÖSTERMEZ (fetch hemen düşer → hata
    sınırı); asılı sunucu şart. Ayrıca HTML akışı açık kaldığı için
    `domcontentloaded` hiç ateşlenmez — `wait_until="commit"` gerekir.
- **Yeşil:** `check-dashboard-typecheck` + tip-testleri (14 direktif, iki
  geçiş), prettier, `check-design-tokens`, `next build`, açık-tema smoke'u
  10/10, `test_dashboard_next_style_gates` 26/26, `test_check_design_tokens`
  35/35, `test_brand_mirror_gate` 20/20, `test_mirror_bridges` 25/25,
  `sync_check_unit_tests --check`.
- **Kapsam dışı:** iskelet ÇUBUK dizgesini (`animate-pulse rounded
  bg-border`) de adlandırmak — bu tur kart BİLEŞİMİNİ topladı, yuva içi çubuk
  ölçülerini değil.

### hex-literal kapısı: premise çürütüldü, ölçülen tek delik kapatıldı (2026-09-28)

- **İstenen zaten VARDI.** "dashboard-next tsx'lerinde hex literal çıkarsa
  check-design-tokens kırmızı olsun" iddiası kapının MEVCUT sözleşmesidir:
  `check_tokens.py` contract 8(f) — "uygulama kaynağında koda gömülü RENK
  OLAMAZ" — `_color_literal_findings()` ile `apps/dashboard-next` altındaki
  `.tsx .ts .jsx .js` dosyalarını tarar ve `_RAW_COLOR_LITERAL` (hex/rgb/hsl),
  `_ARBITRARY_COLOR_UTIL` (`bg-[#0e1116]`) ve `_NON_BRIDGE_PALETTE_UTIL`
  (`bg-slate-900`) desenleriyle reddeder. **Ölçüm:** beş varyantı (hex string,
  arbitrary utility, inline stil hex, kısa hex, `rgb()`) taşıyan geçici bir
  `.tsx` → kapı rc=1, satır satır bulgu.
- **Testlerle PİNLİ:** `test_arbitrary_hex_utility_fails`,
  `test_inline_style_hex_fails`, `test_raw_hex_in_globals_css_fails`,
  `test_tailwind_palette_colour_fails`, iki karşı-test (ölçü/`var()`
  türetmeleri gölge içi rgba kırmızı OLMAMALI) ve
  `test_colour_literal_gate_is_wired` (kabloyu kaynak metninde arar). Yani
  kural hem koşuyor hem çürümeye karşı bağlı.
- **AMA ölçülen gerçek bir delik vardı:** CSS dalı yalnız `app/globals.css`e
  sabitlenmişti ve `_SOURCE_SUFFIXES` `.css` içermiyordu → pano altına YENİ
  bir `.css` dosyası açıp içine `#ff0000` yazmak kapıyı **YEŞİL**
  bırakıyordu (ölçüldü: rc=0). Kural vardı ama yeni bir dosyayla sessizce
  atlatılabiliyordu.
- **Kapatıldı (contract 8(g)):** globals.css dışındaki her `.css` aynı
  ham-renk taramasından geçer; `@theme`/`@utility` blokları orada da muaftır
  (onlar utility EŞLEMESİdir, belge custom property'si değil). Ölçüm: aynı
  probe artık rc=1 ve `…__probe_tmp.css:1` diye ad veriyor.
- **Bulunan ikinci kusur — denetim maliyeti:** `Path.rglob` hem uygulama
  kaynağı hem preset-only taramasında `node_modules`/`.next` içine giriyordu
  (ölçüldü: node_modules altında tek başına 24.917 dosya, kapı ~1,4s) ve
  CSS taraması eklenince maliyet katlandı. Gezinme `os.walk` + dizin
  budamasıyla tek yardımcıya (`_app_source_files`) taşındı: **~1,45s →
  ~0,13s** — yani yeni kural eklendiği hâlde kapı eskisinden hızlı. Sessiz
  yan kazanç: sonuç artık kurulu paketlerin içeriğinden bağımsız (aksi halde
  her `npm ci` sonrası node_modules'teki hex'ler kapıyı kirletirdi). Yeni
  test: `test_source_walk_prunes_installed_trees`.
- **Yanlış iddia düzeltildi:** hook açıklaması ve test docstring'i "~0.05s"
  diyordu; ölçüm ~0,15s (budama öncesi ~1,4s) — yani iddia zaten yanlıştı.
  Değerler ölçülenle değiştirildi.
- **Keşfedilebilirlik — talebin asıl nedeni:** `check-design-tokens` hook
  açıklaması YALNIZ globals.css'i anlatıyordu; uygulama KAYNAĞI (ts/tsx)
  taraması, arbitrary utility ve varsayılan palet kuralları yazmıyordu, bu
  yüzden kural "yok" sanılıyor. Açıklama artık 8f/8g'yi, MEŞRU istisnaları
  (ölçü/harf-aralığı arbitrary değerleri, `var()` türetmeleri, gölge içi
  rgba) ve budama notunu içeriyor. Kuralı eklemek yetmez; görünür olmalı.
- **Yeşil:** `test_check_design_tokens` 39/39 (35 → 39: 2 yeni kural vakası +
  2 karşı-test), `check-design-tokens` hook'u (0,13s),
  `pre-commit validate-config`, `sync_check_unit_tests --check`,
  `test_coverage_report --check`, `test_gate_coverage_sync`,
  `test_dashboard_next_style_gates` 26/26. Geçici probe dosyaları silindi
  (`git status`'ta iz yok).

### 13 UI bulgusu kapatıldı — statik sözleşme + canlı kanıt (2026-09-28)

- **Kaynak:** §"web-design-guidelines review (2026-09-19)" (5779ab0) — 13
  bulgu; inceleme turu yalnız dokümandı, düzeltmeler bu turda uygulandı. Her
  bulgu İKİ katmanla kilitlendi: **statik** `test_dashboard_next_ui_contract.py`
  (36/36, tarayıcısız, 0,06 sn — bataryada) ve **canlı**
  `test_dashboard_next_surface_smoke.py` (16/16, Chromium + `next start`).
- **Uygulanan düzeltmeler.** `globals.css`: `:root { color-scheme: dark }` +
  `:root[data-theme="light"] { color-scheme: light }` (bir renk değil anahtar
  sözcük — `var()` ile türetilemez, jeneratör kopyalamaz, bu yüzden elle
  yazılan sheet'te) ve preview.html'inkinin AYNISI olan global
  `@media (prefers-reduced-motion: reduce)` bloğu. Yeni `lib/format.ts`:
  `Intl.DateTimeFormat` sabit `tr-TR` + `UTC` ile (varsayılanlar ortama göre
  değişir; aynı veri sunucuda ve tarayıcıda farklı metne dönerdi),
  bozuk/boş değer uydurma tarih yerine `EMPTY_VALUE`. `ThemeInit`:
  `applyThemeColor()` meta `theme-color`ı computed `--bg`den yazar — hex
  gömülseydi check-design-tokens 8(f) kırmızı olurdu. `layout.tsx`: marka
  `<span>` → **`<h1 translate="no">`** (kök layout → tüm rotalar).
  `ui/button.tsx`: `transition-all` → tek arbitrary liste. `VerdictCard`:
  `role="status"` (`aria-live` yinelemesi kaldırıldı), `tabular-nums`,
  `<time dateTime>` + `formatTimestamp`. `RunsTable`: `tabular-nums`
  `cellVariants` TABANINDA (gövde hücrelerinin hepsi sayı/damga; yeni bir
  sayı sütunu sessizce muaf kalamaz), `<time dateTime>`. `error.tsx`:
  `role="alert"`. `app/loading.tsx`: rol'süz div'deki `aria-label` →
  `role="status" + aria-busy` — bu ÜÇÜNCÜ iskeletti; PanelCard turu yalnız
  iki paralel-rota slotunu düzeltmişti, kök `loading.tsx` açık kalmıştı.
- **Ölçüm dersi 1 (harness düzeltmesi).** `/` sayfası `domcontentloaded` +
  `data-theme` beklendiğinde HÂLÂ iskeleti gösteriyordu; ölçüldü: 13 GÖRÜNÜR
  `animate-pulse` düğümü, iki `aria-busy` bölgesi, İKİ `<dl>` (ilki
  iskeletin — `font-variant-numeric: normal`), gerçek içerik ise akış
  konteynerinde (`div[hidden]`). Yani eski smoke iddiaları (ör. `<h2>`
  listesi) gizli içeriği okuyordu ve "yeşil" olması ekranın doğru olduğunu
  kanıtlamıyordu. `_measure` artık iskelet kalkana kadar bekliyor
  (`[aria-busy="true"]` sayısı 0) → tüm vakalar GERÇEK panoyu ölçer; mevcut
  10 vakanın kapsamı da bu beklemeden kazandı.
- **Ölçüm dersi 2 (birim normalizasyonu).** `0.001ms` Chromium'da `1e-06s`
  olarak serileşir; metin karşılaştırması kırılgan. `css_seconds()` saniyeye
  çevirip EŞİK karşılaştırıyor (tercih yokken `2s` > 0,01 sn; reduce'da
  ≤ 0,001 sn) ve ayrıştırılamayan değer sessizce 0 sayılmıyor, FAIL ediyor.
- **Yeniden adlandırma.** `test_dashboard_next_light_theme.py` →
  `test_dashboard_next_surface_smoke.py`: dosya artık tema değil YÜZEY
  sözleşmesini taşıyor. Dört referans aynı turda güncellendi (EXCLUDE,
  CHECK_EXEMPT, `CI_JOB_COVERAGE["dashboard-next"]`, verify.yml adımı:
  "Surface smoke — dashboard-next (fail-closed)") ve yeni statik süit eski
  adın hiçbir yerde kalmadığını test ediyor. İkinci bir Playwright boot'u
  açmak yerine aynı sunucu kablosu kullanıldı (drift + ~10 sn).
- **Anti-vakum karşı-testleri.** Nabız azaltma kuralı üç iskelette hedef
  arar; `tabular-nums` iddiası sayı sütunlarının (p0/p1/duration_s/z3_total)
  varlığını; `<time>` kuralı ≥2 düğüm; `aria-label` kuralı ≥3 etiket;
  `color-scheme`/`theme-color` ölçümü açık/koyu token'ın gerçekten FARKLI
  olmasını; canlı reduce ölçümü de "utility yüklü mü"yü (reduce öncesi süre
  > 0,01 sn) şart koşar. `theme-color` beklenen değeri sabit hex değil,
  köprüdeki `--bg` token'ıdır.
- **Yeşil:** yeni statik süit 36/36, yüzey smoke'u 16/16 (rebuild sonrası),
  `check-dashboard-typecheck` + tip-testleri (iki geçiş), prettier,
  `check-design-tokens` (rc=0), `check_tokens.py` OK, `next build`,
  `sync_check_unit_tests --check` 22/22 (yeni süit bataryaya eklendi),
  `test_coverage_report --check`, `test_gate_coverage_sync`,
  `test_test_coverage_report` 15/15, `test_dashboard_next_style_gates` OK,
  `test_brand_mirror_gate` 20/20, `test_mirror_bridges` 25/25,
  `test_actionlint_gate` 5/5.
- **Kapsam dışı:** azaltma kuralını `motion-reduce:` utility'lerine dağıtmak
  (global kural yeni animasyonları da kapsar), `transition-[…]`ı token'a
  bağlamak ve panoya tema DÜĞMESİ eklemek (etkileşim + durum yönetimi;
  `?theme=`/localStorage kablosu zaten var).

### transition-all ailesi tamamlandı + odak halkası nav'a taşındı (2026-09-28)

- **Aynı kusur ikinci primitive'de:** buton tabanındaki düzeltmeden sonra
  arama yapıldığında `components/ui/badge.tsx` tabanı da `transition-all`
  taşıyordu ve rozet panoda CANLI (VerdictCard P0/P1 istatistikleri
  `statBadge` ile bu primitive'i kullanır). Liste rozetin GERÇEKTEN
  değiştirdiği özelliklerden kuruldu: `color, background-color,
  border-color, box-shadow`. Butondaki `transform`/`opacity` rozette YOK
  (işaret de yok — olmayan özelliği listeye yazmak sözleşmeyi süslerdi) ve
  `link` varyantındaki `hover:underline` bilinçli dışarıda:
  `text-decoration-line` ayrık (discrete) bir özellik, geçiş üretmez.
- **Statik sözleşme genelleştirildi** (`PrimitiveTransitionTest`, tek
  primitive'e değil ikisine birden bakıyor): (a) hiçbir tabanda
  `transition-all` yok, (b) primitive başına tek `transition-*` utility
  (birden fazlası birbirini ezer), (c) liste HER primitive'in KENDİ
  işaretlerini kapsıyor (işaret→özellik tablosu dosya başına; işaretin
  kendisi de doğrulanır, yani iddia vakum değil), (d) ortak dört aile
  ikisinde de bulunur (drift kilidi), (e) karşı-test: `text-decoration`
  listede değil — birinin "eksik" sanıp eklememesi için karar pinlendi.
- **Odak halkası nav'a taşındı.** `layout.tsx`'teki iki nav bağlantısı
  `transition-colors hover:text-fg` dizgesini birebir kopyalıyordu ve ODAK
  işareti hiç yoktu (halka yalnız primitive tabanlarındaydı). Dizge
  `panel-style.ts`e `navLink` cva'sı olarak alındı: hover + halka sözleşmesi
  buton tabanıyla AYNI (`focus-visible:ring-3` + `ring-ring/50`), yarıçap
  `rounded-sm` token'ıyla yumuşatılır ve `focus-visible:outline-none`
  bilinçli olarak butonun çıplak `outline-none`ından daha DAR (bağlantı
  zaten odaklanabilir; yalnız klavye odağında yerleşik halka kapatılır).
  `/` sayfasındaki iki satır-içi bağlantı zaten
  `buttonVariants({variant:"ghost"})` kullandığı için halkayı taşıyordu.
- **Genel kural (statik):** her `<Link>`/`<a>` ya `navLink(`, ya
  `buttonVariants(`, ya açık `focus-visible:` taşır — yeni bir bağlantı
  sessizce işaretsiz kalamaz (4 bağlantı + anti-vakum eşiği).
- **Canlı kanıt (yüzey smoke'u, yeni vaka):** ilk TAB nav'ın ilk
  bağlantısına (`ÖZET`) gider — sekme sırası da bu vakayla kilitlenir — ve
  hesaplanan `box-shadow` 3px halka taşır. Beklenen RENK sabit yazılmaz:
  sayfada `color-mix(in oklab, var(--ring) 50%, transparent)` ile çözülür
  ve bileşenler sayısal karşılaştırılır, `--ring` = `--accent` (%50
  saydamlık da alfanın 0,5 olmasıyla ölçülür). **Ölçüm dersi:**
  Chromium'un `/50` saydamlığı `rgba()` değil `oklab(… / 0.5)` olarak
  serileşiyor; rgb üçlüsü arayan ilk sürüm bu yüzden düştü (hata mesajı
  beklenen değeri gösterdi) ve iddia renk uzayından bağımsız hâle getirildi.
- **Yeşil:** statik süit 40/40 (36 → 40), yüzey smoke'u 17/17 (16 → 17),
  prettier, `check_dashboard_typecheck.sh` + tip-testleri (iki geçiş),
  `check_tokens.py`, `next build`.
- **Kapsam dışı:** `ring-[3px]` (rozet, arbitrary) ile `ring-3` (buton,
  token ölçeği) yazımını birleştirmek — aynı 3px'i verir;  ölçü arbitrary
  değerleri kapının renk taramasına girmediği için acil değil, ama iki
  primitive arasında yazım farkı olarak duruyor.

### Fresh-checkout bootstrap: kapsam ÖLÇÜLEREK genişletildi (2026-09-28)

- **İstenen çekirdek zaten VARDI:** `_calisma/dev_bootstrap.sh` venv_z3'ü
  pinli kuruyor ve `_calisma/pptx` npm ci'sini bağlıyordu; README'nin
  "Fresh checkout bootstrap" bölümü de bunu belgeliyordu (ikisi de
  commit'lenmemiş, README tarafı stage'li). Bu tur **açığı ölçüp** kapattı:
  kapsam iddiası ile bataryanın gerçekte istediği ortam arasındaki fark.
- **Ölçüm yöntemi:** manifestteki 183 test dosyası AST ile tarandı, üçüncü
  taraf importler VENV python'uyla çözüldü (`site-packages` → üçüncü taraf)
  ve her import'un korumalı mı (`try/except` + `skipIf`) olduğu denetlendi.
  Ayrıca ortam-duyarlı 12 test dosyası venv python'uyla koşuldu: hepsi
  yeşil, yani eksik bağımlılık KIRMIZI değil SKIP üretir.
- **Bulunan açık (ölçüldü):** kurulu olmayan bağımlılık testi düşürmüyor,
  sessizce ATLIYOR — taze checkout'ta `--full` yeşil görünüp 9 manifest test
  dosyası kapsam dışı kalırdı: `jsonschema` → `test_validate_config_schema`
  (doğrulama yolu), `pillow` → üç `*_deck` süiti (`HAS_PIL` kapısı),
  playwright+chromium → `test_dashboard_keyboard_nav`, `test_preview_escaping`,
  `test_preview_hover_tooltip`, `test_dashboard_cls_budget`,
  `test_surface_cwv_report`, ve iki npm ağacı → `test_trend_db_js_runner`
  (`node_modules/.bin/tsx`), `test_check_video_typecheck` (`…/.bin/tsc`).
  Pin listesi 3 paket iddia ediyordu, venv'de 21 paket vardı.
- **Kapatıldı:** PINS'e `jsonschema==4.25.1` + `pillow==11.3.0` eklendi
  (değerler yerelde yeşil olan venv'in `pip freeze` satırları), iki yeni npm
  unit'i geldi (`apps/trend-db`, `_calisma/video`) ve yedinci unit **tarayıcı
  katmanı** oldu: `playwright==1.63.0` (CI pini) + `playwright install
  chromium`.
- **Tarayıcı katmanının ölçümü İŞLEVSEL, pin-paritesi değil:** başsız bir
  chromium gerçekten başlatılıyor — çalışan tarayıcı sürüm etiketinden daha
  güçlü kanıt ve yerelde farklı ama çalışan bir playwright (1.60.0) varsa
  gereksiz ~150 MB indirme tetiklenmiyor. Pin YALNIZ kurulumda kullanılır ve
  CI'daki piniyle eşitliği sözleşme testiyle bağlandı (ikinci kaynak yok).
- **Kanıt:** `--check` CHECK OK (2,0 sn; gerçek chromium başlatma dahil),
  her yeni unit için fail-closed ölçümü — sentinel gizlenince rc=1
  (`CHECK FAIL: trend_db` / `video`) ve tarayıcı için boş
  `PLAYWRIGHT_BROWSERS_PATH` ile rc=1 (`CHECK FAIL: browsers`) · bu yol
  paketi gizlemediği için paralel bir tarayıcı testini bozmuyor. Yeni
  hermetik sahte-kök testi `--full`un pin+chromium kurulumunu AĞA ÇIKMADAN
  koşuyor ve çalışan tarayıcıda indirme TETİKLENMEDİĞİNİ (idempotence)
  kanıtlıyor. Sözleşme süiti 18/18 (12 → 18), shellcheck temiz.
- **Belgeleme:** README tablosu 7 unit'e çıktı ve her satıra "Bataryada
  karşılığı" sütunu eklendi (kapsam gerekçesi artık görünür); pin/tarayıcı
  notları ve `docs/HOOK_ENV_MATRIX.md` ile ilişki (yalnız z3/pre_commit
  paylaşılır, jsonschema/pillow hook-ortamı değil batarya bağımlılığıdır)
  yazıldı.
- **Kapsam dışı / sınırlar:** `--full`un GERÇEK bataryası bu tur koşulmadı
  (dakikalar; kablolama sahte bataryayla + önceki turun canlı koşumuyla
  ölçüldü). Repo dışına kurulan araçlar (`lean`, `qpdf`, `pdfinfo`)
  bootstrap kapsamında DEĞİL — onlar `docs/HOOK_ENV_MATRIX.md`/K-katmanı
  job'larının konusu. `.vercel/output/static` altındaki eski script kopyası
  bilinçli olarak güncellenmedi (gitignore'lu derleme artefaktı).
- **Not:** README bu turda hem stage'li (önceki turun hunk'ı) hem
  değiştirilmiş (bu turun hunk'ı) durumda — stage'e dokunulmadı.

### work/2026-09-19 → reword-working ff-merge: koşuldu, no-op çıktı (2026-09-28)

- **Dal yoktu:** `work/2026-09-19` ref'i daha önce (fully-merged olduğu için)
  silinmişti; istek üzerine `dd913c8`'te geri kuruldu — uç commit'i
  "fix(dev): bootstrap pin list as array, shellcheck-clean".
- **7 commit'in kimliği ölçüldü:** `git log -7 dd913c8` = `81a0f82` (workers
  audit) · `98b5acd` (wrangler) · `e286779` (dev-bootstrap planı) ·
  `ef0b6dc` (dev_bootstrap.sh) · `0d4196e` (README quickstart) · `11a673b`
  (xlsx audit) · `dd913c8` (pin listesi diziye). Yedisi de `reword-working`
  ve `main` içinde: `git rev-list --count reword-working..dd913c8` = 0.
- **Merge gerçekten koşuldu**, `main` ağacı (34 değişik dosya) ve çalışan
  thread'ler rahatsız edilmeden: geçici bir worktree'de
  (`git worktree add /tmp/ff-merge-check reword-working`) `git merge --ff-only
  work/2026-09-19` → **"Already up to date."** rc=0; `reword-working` ucu
  `1b93467`'de kaldı, merge commit'i doğmadı, hiçbir şey push edilmedi.
  Worktree iş bitince kaldırıldı (`git worktree list` orijinal 3 kayda döndü).
- **İçerik kanıtı (commit grafiği yeterli değildi):** `reword-working`
  ağacında `_calisma/dev_bootstrap.sh`, `_calisma/CIKTI/test_dev_bootstrap.py`,
  `docs/superpowers/plans/2026-09-19-dev-bootstrap.md` VAR; `findings.md`
  workers/wrangler/xlsx kayıtlarını, `README.md` "Fresh checkout bootstrap"
  bölümünü, `dev_bootstrap.sh` `PINS=(` dizisini taşıyor.
- **Gerçek eksik başka yönde:** yerel `reword-working`, `origin/reword-working`
  in **6 commit gerisinde** (uzak uç: `a24c4db` "fix(ci): paginate live audit
  artifacts"). Yani bu dal için anlamlı iş "work dalını almak" değil,
  uzakla hizalanmak.
- **Kalan ref:** `work/2026-09-19` bu turda geri kuruldu ve bırakıldı (istenen
  merge'in konusuydu, içeriği zaten `main`/`reword-working`'de). Zararsız —
  ölçüldü: dal listesini denetleyen bir kapı yok. İstenirse tek satır:
  `git branch -d work/2026-09-19`.

### pre-commit envanter kapısı: doküman ↔ config hook seti (2026-09-28)

- **İstek:** "pre-commit doc envanteri ile gerçek `.pre-commit-config.yaml`
  hook sayısını karşılaştırıp bayat-ise uyarı versin".
- **Hedef yüzey ÖLÇÜMLE seçildi:** repoda envanter bloğu zaten var —
  `skills/verify-chain/SKILL.md` §"Wiring into pre-commit" içinde "Existing
  hook inventory:" işaretini izleyen kod bloğu. Ölçüm: blok **19** hook
  listelerken config'te **60** hook vardı (41 kapı belgesiz); 2026-09-19 turu
  bu bayatlığı zaten not etmişti ("says 19 pre-commit gates; live config has
  50").
- **Sayı yerine KÜME karşılaştırıldı:** naif "her doküman 61 demeli" kuralı
  yanlış-pozitif üretirdi — `docs/PRE_PUSH_DENETIM_RAPORU.md` (14 hook),
  `docs/PUBLISH_SCENARIO.md` (13/13), `docs/FINAL_RC_REPORT.md` (27/27),
  `docs/AI_SERVICE_EVAL.md` (53), `docs/FULL_SCOPE_AUDIT_2026-09-17.md` (~70),
  `docs/UNCOMMITTED-INVENTORY.md` (50/51/59) TARİHSEL/tur-spesifik kayıtlardır.
  Bu yüzden TEK kanonik envanter yüzeyi seçildi ve karşılaştırma iki yönlü id
  kümesi üzerinden yapıldı.
- **Kapı:** `_calisma/CIKTI/check_precommit_inventory.py` (stdlib-only —
  PyYAML gerekmez, OFFLINE, ~0.02s). `repos:` sonrası `- id:` kümesi ↔ işaret
  sonrası ilk kod bloğunun id kümesi.
  - `eksik` = config'te var, envanterde yok (kapsam sessizce daralmış).
  - `fazla` = envanterde var, config'te yok (kaldırılmış/yeniden
    adlandırılmış kapı).
  - Varsayılan **ADVISORY**: `BAYAT:` uyarısı basar, exit 0 (istek: "uyarı
    versin"); `--strict` ile exit 1; `--json` makine-okunur.
  - **Kör kapı exit 2:** `repos:` yok / işaret yok / blok yok / config yok.
    Yeniden adlandırılmış bir bölüm kapıyı sessizce PASS'a çeviremez.
- **Bayatlık DÜZELTİLDİ, sonra kilitlendi:** blok 19 → 60 satıra çıkarıldı
  (config `repos:` sırası, kısa İngilizce yorumlarla), sonra yeni hook eklendiği
  için ikisi de **61**'de senkron. Kapı yeşil başlangıçla açılıyor; bundan
  sonra hook eklenip blok güncellenmezse uyarı gelir.
- **Kablolama:** zincire `check-precommit-inventory` eklendi
  (`files: ^(\.pre-commit-config\.yaml|skills/verify-chain/SKILL\.md)$` —
  değişim-farkında/nedensel; `pass_filenames: false`, `verbose: true`).
  `HOOK_COVERAGE["check-precommit-inventory"]` eklendi; test dosyası
  `check_unit_tests.list`e + `check-unit-tests` kapsam bloğuna otomatik girdi
  (`sync_check_unit_tests.py --update`), `test_all_hooks_smoke.HOOKS`a eklendi.
- **Test:** `test_check_precommit_inventory.py` 27/27 (0.011s) — ayrıştırıcı
  disiplini (yorum-içi id, başlık-yorumu `# - id:`, blok-dışı satır, tekrar),
  iki yönlü fark, advisory/`--strict`/kör (exit 2) ve gerçek-ağaç değişmezi
  (envanter kümesi == config kümesi).
- **Doğrulama:** yeni süit 27/27 · `test_gate_scripts_meta_guard` 15/15 ·
  `test_test_coverage_report` 15/15 · `test_gate_coverage_sync` 4/4 ·
  `test_sync_check_unit_tests` OK · `test_coverage_report.py --check` rc=0 ·
  `sync_check_unit_tests.py --check` rc=0 ·
  `pre-commit run check-precommit-inventory --all-files` → Passed ·
  all-hooks smoke (tek id) 1/1 PASS · YAML `yaml.safe_load` → 61 hook.
- **Kapsam dışı:** `AGENTS.md` hâlâ "59-hook"/"50-hook" sayılarını taşıyor —
  bu turda DOKUNULMADI (dosyada başka bir thread'in unstaged değişikliği var,
  `M AGENTS.md`); tarihsel raporlardaki sayılar bilinçli olarak hedef dışı.
  Commit yapılmadı.

### work/2026-09-19 → reword-working ff + batarya (2026-09-28, 3. koşum)

- **İstenen:** ff-merge ("verified possible") → birleşmiş HEAD'de tam batarya →
  worktree'yi prune et.
- **Öncül ÖLÇÜMLE çürütüldü:** ff-merge bir no-op'tur, çakışma yüzünden
  değil, kaynak dal hedefin ATASI olduğu için. `git merge-base --is-ancestor
  work/2026-09-19 reword-working` → EVET; `git rev-list --count
  reword-working..work/2026-09-19` = **0**; ters yön (=work..reword) = **60**.
  Yani `reword-working` zaten `work/2026-09-19`'ı İÇİYOR; ff mümkün değil,
  gereksiz. (`work/2026-09-19` ayrıca `main`'in de atasıdır → içeriği aktif
  ağaçta fazlasıyla var.)
- **Merge yine de GERÇEKTEN koşuldu** (kanıt için, main ağacına dokunmadan):
  `git worktree add /tmp/ff-merge-check reword-working` → `git merge --ff-only
  work/2026-09-19` → **"Already up to date."** rc=0; HEAD `1b93467`'de
  sabit kaldı, dal İLERLEMEDİ, çalışma ağacı temiz.
- **Birleşmiş HEAD = `1b93467`** (merge no-op olduğu için). Batarya BU HEAD'de
  koşuldu. Sonuç: **158/158 PASS** (2m49s) — `check_unit_tests_hook.sh`,
  manifest'in 160 satırından 2'si yorum başlığı.
- **İlk koşum 156/158 verdi; İKİ hata da ortam kaynaklıydı, regresyon değil:**
  - `test_dev_bootstrap` → `CHECK FAIL: docx eksik veya paritesiz`: taze
    worktree'de `_calisma/docx/node_modules` yok (gitignore'lu). Bu tek
    girdi sağlanınca `bash dev_bootstrap.sh --check` → **CHECK OK** ve süit
    **7/7 OK**.
  - `test_dashboard_keyboard_nav` → Playwright `.rh-row` / `#trend
    rect[data-tip]` bulamıyor: test kendi `preview_server.py`'sini
    `--dir <worktree>/_calisma/CIKTI` ile başlatır, ama CANLI VERİ
    (`history.jsonl`, `runs/`) gitignore'ludur → taze worktree'de boş pano.
    Veri symlink'lenince **14/14 OK** (68.6s).
- **Yöntem notu (tekrar kullanılabilir):** taze bir worktree'de tam batarya
  koşmak için gitignore'lu toolchain + canlı veri ana checkout'tan
  symlink'lenir (`_calisma/.venv_z3`, `*/node_modules`, `_calisma/docx|
  pptx|video/node_modules`, `_calisma/CIKTI/{history.jsonl,runs,logs}`).
  Aksi halde hatalar ortam-kaynaklıdır ve "branch kırmızı" diye YANLIŞ
  okunur — iki vaka da tam olarak böyle çıktı.
- **Yan etki (dürüstçe):** canlı veri symlink'lendiği için worktree'nin
  sunucusu ana checkout'un gitignore'lu `runs/`+`history.jsonl`'ini PAYLAŞIR.
  Ölçüldü: `runs/` en yeni kaydı 13:47 (277s'lik gerçek bir `verify_delivery
  --full` kaydı, `pdf_pages=33`+`ref_count=64`; 3 dakikalık unittest
  bataryasından gelmiş OLAMAZ) — yani bu kayıt benim koşumumun ürettiği bir
  şey değil. İzlenen dosya değişmedi: ana checkout `git status` sayısı
  baştan sona **38** kaldı.
- **Temizlik:** `git worktree remove --force /tmp/ff-merge-check` rc=0 →
  `git worktree prune -v` rc=0 (sessiz: budanacak yetim kayıt YOK — nitekim
  prune iş öncesi `--dry-run -v` de boş dönmüştü). `git worktree list`
  orijinal 3 kayda döndü; `/tmp/ff-merge-check` silindi. `work/2026-09-19`
  dalı dokunulmadan bırakıldı (`dd913c8`).
- **Gerçek eksik hâlâ aynı yönde:** yerel `reword-working`,
  `origin/reword-working`'in **6 commit gerisinde**. Push/commit YAPILMADI.

### Doğrulama süpürmesi: tek komut, tek verdict (2026-09-28)

- **İstek:** "verification sweep habit"ı kalıcılaştır — batarya + token kapısı
  + build + cache-clean'ı tek komutta, TEK verdict'le koşan bir giriş noktası.
- **Kararlar (kullanıcıya soruldu):** git commit YOK (ağaçta 38 kirli dosya,
  bir kısmı başka thread'lerin); cache-clean = pre-commit yetim patch'leri +
  K14 cleanup; build = dashboard-next `next build`.
- **Yeni giriş noktası:** kök `Makefile` (`make verify`, `make verify-list`,
  `make verify DRY=1`, `make verify ONLY=tokens,build`) — repo'nun İLK kök
  Makefile'ı (şimdiye dek yalnız `docs/Makefile.texlive|tectonic` vardı;
  `test_makefile_texlive.py` o dosyaya bakar, etkilenmedi). Makefile ince
  giriş noktasıdır: mantık `_calisma/CIKTI/verify_sweep.py`'de (stdlib-only).
  Ayrılma gerekçesi: adım eklemek Makefile'a dokunmayı gerektirmesin ve
  süpürme birim-test edilebilsin.
- **Adımlar ve sıra (nedensel):** `cache-precommit` (yetim patch, 0.1s) →
  `cache-cleanup-log` (K14, 0.5s) → `tokens` (0.1s) → `build` (10s) →
  `battery` (325s). Cache en başta çünkü kirli cache SONRAKİ ölçümü yanıltır;
  en yavaş adım en sonda (erken kırıklar dakika beklemeden görünür). Zincir
  sözleşmesiyle aynı: **fail-fast KAPALI** — bir adım kırılsa da süpürme
  sonuna kadar koşar, tek turda TÜM kırıkları gösterir.
- **Kapsam dışı (bilinçli):** `verify_delivery.py --full` (K-katman zinciri)
  süpürmeye DAHİL EDİLMEDİ — dakikalar sürer, Z3/Lean ister; dahil edilse
  `make verify` commit-öncesi alışkanlık olamayacak kadar yavaşlardı.
- **Koşucu seam'i (gerçek hata yakalandı):** `run_sweep(steps, runner=…)`
  varsayılanı ÖNCE `runner=subprocess_runner` diye bağlanmıştı → varsayılan
  parametre ÇAĞRI ANINDA değil TANIM ANINDA çözülür, bu yüzden testteki
  `sweep.subprocess_runner` monkeypatch'i ETKİSİZDİ ve testler npm build +
  bataryayı GERÇEKTEN koştu (ölçüldü: 19 test 83.9s). Düzeltme: varsayılan
  `None`, gövdede çözülür → 20 test 0.003s.
- **CLI/exit sözleşmesi:** `--list`, `--dry-run` (hiçbir adımı koşmaz),
  `--only a,b`, `--json` (tek JSON belgesi), `--verbose`. Exit: 0 PASS,
  1 ≥1 adım FAIL, 2 kullanım hatası. Adımlar argv listesidir (kabuk yok).
  **Make notu:** kırık recipe'de make KENDİ koduyla **2** döndürür (0=PASS
  korunur; fail-closed bozulmaz) — 2, koşucunun "kullanım hatası" 2'siyle
  karıştırılmasın diye Makefile başlığında ve testte çivilendi.
- **Kanıt:** `make verify` → `SWEEP: PASS — 5/5 adım yeşil (336.1s)` rc=0
  (gerçek koşum, batarya 325.6s). FAIL yolu TEORİK DEĞİL, ölçüldü:
  `PRE_COMMIT_HOME=/tmp/ff_orphan_cache` (24s+ yaşlı sahte patch) ile
  `make verify ONLY=cache-precommit` → `SWEEP: FAIL — 1/1 adım başarısız` ve
  make Error 1; kırılan adımın çıktı kuyruğu rapora gömüldü. `--only nope`
  → rc=2. Kullanım hatası rc=2.
- **Test:** `test_verify_sweep.py` **20/20** (0.003s) — adım tablosu (dört
  alan, sıra, argv-liste, benzersizlik, hedef yollarının varlığı), verdict
  mantığı (PASS/FAIL, fail-fast kapalı, çıktı kuyruğu, OSError = kırık adım),
  CLI (dry-run koşmaz, --only filtre/usage, --json şekli) ve Makefile pin'i
  (delegasyon, TAB recipe, .PHONY).
- **Kablolama:** test dosyası `check_unit_tests.list`e + `check-unit-tests`
  HOOK_COVERAGE bloğuna otomatik girdi (`sync --update`). Süpürme bir
  pre-commit HOOK'u DEĞİLDİR (bilinçli): batarya zaten commit'te koşuyor;
  `make verify` elle/CI kullanımı için.
- **Yan etkisizlik:** yeni kök dosya mevcut kapıları bozmadı —
  `test_coverage_report.py --check` rc=0; `test_gate_coverage_sync`,
  `test_test_coverage_report`, `test_gate_scripts_meta_guard`,
  `test_static_isolation` OK; pre-commit `check-mirror-coverage`,
  `check-absolute-paths`, `check-skills-index`, `check-doc-job-sync` PASS.
- **Commit YAPILMADI** (kullanıcı kararı); yeni üç dosya untracked:
  `Makefile`, `_calisma/CIKTI/verify_sweep.py`, `_calisma/CIKTI/test_verify_sweep.py`.

### check-precommit-orphans: kanıta-dayalı otomatik karantina (2026-09-28)

- **İstek:** kapıyı genişlet — `+` satırları ağaçta kanıtlanan kalıntıyı
  otomatik temizle, yalnız içeriği bilinmeyenleri elle incelemeye bırak.
- **Karar (kullanıcıya soruldu):** SİLME değil, **KARANTİNA** —
  `<cache>-orphans-quarantine-<tarih>/` altına taşı + `MANIFEST.md`
  (sha256+md5+kanıt+yaş+arşiv eşleşmesi). Gerekçe: AGENTS.md'nin kendi
  kuralı ("silme yerine karantina") ve taşımanın geri alınabilirliği.
- **KRİTİK BAĞLAM:** mevcut kapı 24s+ yetimde exit 1 ile commit'i BLOKE
  ediyor ve AGENTS.md "kapıyı geçirmek için ASLA gevşetme" diyor. Bu tur
  kapıyı GEVŞETMİYOR: tespit değişmedi, kanıtlanamayan kalıntı bloklamaya
  devam ediyor. Yalnız içeriği AĞAÇTA KANITLI olan kalıntı için blok
  kalkıyor — "sessiz revert" riski tam da o vakada yok.
- **İki kanıt sinyali (53 arşiv patch'inde ÖLÇÜLDÜ):**
  - `rev-apply`: `git apply --reverse --check` temiz = ağaç patch'in
    sonrası durumda → **12/53**.
  - `+lines`: patch'in anlamlı `+` satırlarının TÜMÜ hedef dosyada
    (çokluk-farkında, dosya-başına) → **23/53**.
  - İkisi İKİ YÖNDE ayrışır (ağaç sürüklenince `+lines` daha bağışlayıcı;
    satır-eklemeyen patch'te `rev-apply` daha güçlü) → birlikte kullanılır.
- **Guard'lar (hepsi ölçümle gerekçeli, hepsi test edildi):**
  - **Hunk şartı:** `@@` yoksa ASLA taşınmaz. Ölçüldü: `git apply --check`
    hunk'sız/boş diff'te **0** döndürür (uygulanacak değişiklik yok) →
    guard olmadan "kanıtlanmış gereksiz" sanılırdı. Kapının KENDİ eski
    fixture'ı tam olarak `diff --git a/x b/x` (hunksız) — yani guard
    olmadan mevcut 18 testin bir kısmı da kırılırdı.
  - **Önem eşiği:** <4 anlamlı karakter (`}`, `#`, boş) kanıt SAYILMAZ;
    yoksa "satır zaten dosyada var" tesadüfü yanlış-pozitif üretirdi.
  - **Etiket koruması:** KNOWN-INCIDENT ve ZAYIF-PARMAK-İZİ ASLA taşınmaz.
    Etiket UYARI'dır, muafiyet değil (AGENTS.md) — ve bu kayıtlar olayın
    **tekrar ettiğinin** kanıtıdır; otomatik taşımak tekrar-sinyalini
    silerdi. (Yan sonuç: mevcut `test_later_archive_fingerprint_is_recognised`
    fixture'ı aslında KANITLI idi — bu koruma onu da yeşil tutuyor.)
  - **Taze patch'e dokunulmaz:** yalnız >24h yetimler; taze patch uçuş-içi
    pre-commit stash'i olabilir.
- **Kısmi temizlik semantiği:** kanıtlılar taşınır, kanıtsızlar KALIR ve
  kapı **exit 1** verir (tek turda tüm kalan kırıkları gösterir); hiç
  incelenecek yetim kalmadıysa exit 0.
- **Özet sızıntısı yok:** sha256/md5 YALNIZ `MANIFEST.md`'ye yazılır;
  stdout'a basılırsa mevcut "eşleşme yokken özet gürültüsü yok" sözleşmesi
  kırılırdı (o test bilinçli).
- **Test:** `test_check_precommit_orphans.py` **18 → 31** (+13 sözleşme):
  karantina+unblock, bayt-birebir taşıma, MANIFEST içeriği, stdout'a özet
  sızmaması, kanıtsız kalır+bloklar, KISMİ temizlik, hunk'sız ASLA,
  önemsiz satır kanıt değil, taze patch dokunulmaz, `--no-clean`, bilinen-olay
  taşınmaz (+dinamik fixture kurulamazsa kod-pini), karantina dizini kardeş.
- **Gerçek-veri E2E (ünite testi değil):** geçici worktree'de GERÇEK bir
  `git diff` üretildi → `rev-apply` kanıtıyla karantinaya alındı; aynı koşumda
  ağaçta olmayan satır ekleyen ikinci patch YERİNDE kaldı ve kapı exit 1 verdi.
  `cmp` ile taşımanın bayt-birebir olduğu doğrulandı. Geçici worktree ve
  dizinler silindi; ana ağaç etkilenmedi (`README.md` durumu değişmedi).
- **Kablolama:** `check-precommit-orphans` hook açıklaması güncellendi
  (otomatik karantina + `--no-clean`); `entry` değişmedi (öntanımlı temizler).
  Yeni test dosyası YOK → manifest/coverage senkronu zaten temiz.
- **Doğrulama:** `sync --check` rc=0 · `coverage --check` rc=0 ·
  `make verify` → **SWEEP: PASS 5/5 (339.9s)** (batarya 31'lik orphan süitini
  içeriyor) · `pre-commit run check-precommit-orphans` → Passed.
- **Not:** AGENTS.md'deki `check-precommit-orphans` paragrafı hâlâ eski
  davranışı anlatıyor (dosyada başka thread'in unstaged değişikliği var →
  dokunulmadı). Commit YAPILMADI.

### work/2026-09-19 → reword-working (4. koşum): "6 stacked commit" öncülü
yanlış-refliydi (2026-09-28)

- **İstek öncülü:** dalda "pptx fix, composition pass, perf dedup, RN survey,
  client-side nav" diye 6 üst-üste commit var, bunlar merge edilecek.
  **Bu betimleme mevcut git durumunda YANLIŞ:** `work/2026-09-19`'ın ucu
  `dd913c8` — 7 commit'lik dev-bootstrap yığını (workers audit → bootstrap
  → pin listesi); pptx/composition/nav temaları bu dalda DEĞİL.
- **Öznelerin gerçek ref'i ölçüldü (hepsi eski tarih):** composition pass =
  `9ce6e32`, perf dedup = `b156cb4`, client-side nav = `41e1f48`, RN survey =
  `f0e21fe` (2026-09-19 "record zero RN/Expo surface survey findings"),
  pptx fix = `d396b8c`. `git branch -a --contains` → hepsi `reword-working`
  VE `main` içinde; `merge-base --is-ancestor` ile üçü de teyitli. Yani
  özneler yeni bir yığın değil, zaten iki dalda da olan tarih.
- **Kapsayıcılık invariyantı:** `rev-list --count reword-working..work/2026-09-19`
  = **0** → merge no-op (bu dal için 4. koşum; öncekiler 2026-09-28'de 2× ve
  bugün). Yine de kanıt için geçici worktree'de `git merge --ff-only
  work/2026-09-19` → **"Already up to date."** rc=0; HEAD `1b93467` sabit.
- **Prune:** `git worktree remove --force /tmp/ff-merge-check` rc=0 →
  `git worktree prune -v` sessiz (budanacak yetim yok — iş öncesi
  `--dry-run -v` de boştu). Worktree listesi 3 kayda döndü; iki ref de
  çözülüyor (`reword-working`=`1b93467`, `work/2026-09-19`=`dd913c8`),
  atanlık invariyantı sürüyor; ana ağaç 43 kirli dosyayla dokunulmadan
  kaldı; stash 2.
- **Ders:** bu istek zincirinde aynı merge artık 4 kez istendi ve 4 kez
  no-op çıktı. "X dalını Y'ye merge et" isteklerinde ÖNCE
  `rev-list --count Y..X` + konu öznelerinin hangi ref'te olduğu ölçülmeli;
  özneler hedef dala `--contains` ile aranmalı (isim eşleşmesi yeterli
  değil — tarih yerine geçmez). Push/commit YAPILMADI.

### dashboard-next Next 16 yükseltmesi + ertelenmiş VT desenleri (2026-09-28)

- **İstek:** Next 16'ya yükselt, 2026-09-19 turunun ETELEDİĞİ VT desenlerini
  yanal crossfade, Suspense reveal, loading.tsx, header izolasyonu
  rayına oturtsun.
- **Ön koşul zaten ölçülmüştü:** eski turda tüm iç bağlantılar next/link'e
  çevrilmişti (soft-nav kanıtlı, marker before=42 after=42) — VT'nin tetik
  ön koşulu hazırdı; "ViewTransition YALNIZ Next 15.5.4'ün vendored
  react-experimental kanalında" tespiti de aynı kayıtta.
- **Sürüm ÖLÇÜLDÜ:** npm dist-tags → `latest` **16.3.6** (canary 16.4.0-51,
  preview 16.3.0-10; kullanıcı stable'ı seçti). `npm install next@16.3.6`
  → 15.5.15 → 16.3.6, react/react-dom 19.2.0'da kaldı (next 16 peer
  `^18.2.0 || ^19.0.0`).
- **Kritik API gerçeği (vendor'da KANITLANDI):** Next 16'nın vendored
  react'ı `exports.ViewTransition`'ı hem istemci
  (`cjs/react.development.js:878`) hem react-server
  (`cjs/react.react-server.development.js:596`) girişinde DIŞA AKTARIYOR ve
  config-schema'da `experimental.viewTransition` YOK — guide'ın "no
  configuration" sözü yerinde doğrulandı. Bayrak eklenmedi.
- **Yükseltme molası #1 (ölçüldü):** Turbopack (16'da varsayılan derleyici)
  çalışma alanı kökünü lockfile'dan çıkarıyor: dashboard-next'in kendi
  `package-lock.json`u kökü o pakete kilitliyor → `lib/trend-db.ts`'in
  `../../trend-db/generated/client` import'u (kardeş paket, gitignored)
  "Module not found" düşüyor. Next 15'te webpack bu geçişi izliyordu.
  Çözüm: `next.config.js`'e `turbopack: { root: repo-kökü }` — CI yerleşimi
  aynı olduğu için yerel/CI aynı kökten çözer. Ayrıca yerelde CI
  sözleşmesindeki `prisma generate` adımı yeniden koşuldu (generated/
  gitignored; tip kapısı da ona bakıyor).
- **Yükseltme molası #2 (next'in kendisi mutate etti):** `tsconfig.json`
  (`jsx: preserve` → **react-jsx** Next 16'da zorunlu; include'a
  `.next/dev/types`) ve `next-env.d.ts` (`import "./.next/types/routes.d.ts"`
  + `root-params.d.ts` — reference → import dönüşümü). İkisi de next build
  tarafından yazıldı; elle düzenleme değil, sürüm sözleşmesi.
- **İsim pinleri senkron:** verify.yml job adı + PUBLISH_SCENARIO satır 30
  "Next 15" → "Next 16" (`test_doc_job_sync` 10/10 OK — ad değişimi iki
  kaynakta birden yapılmadığında kapı kırılardı).
- **VT uygulaması (harita sözleşmesiyle):**
  - **Yanal crossfade YALIN:** `(panel)/page.tsx` ve `trend/page.tsx`
    içeriklerini `import { ViewTransition } from "react"` sarmalayıcısı
    örter — prop YOK (default crossfade). `transitionTypes`/`nav-*`
    KASITLI OLARAK hiçbir yerde yok (iki eşit panel arası sahte mekânsal
    derinlik yasak; guide'daki Step 3'ün tersi bilinçli).
  - **Header çapası:** `viewTransitionName: "site-header"` (inline) + CSS
    `::view-transition-group(site-header){animation:none;z-index:100}`,
    `-old{display:none}` (çift-basım flaşı yok), `-new{animation:none}`.
  - **Suspense reveal (kullanıcı slotlara istedi):** `@verdict`/`@trend`
    slot sayfaları `enter:{"slot-enter":…,default:"none"}` /
    `exit:{"slot-exit":…,default:"none"}` sarmalayıcı aldı; CSS asimetrisi
    guide'dan: çıkış 150ms, giriş 210ms + 150ms gecikme + 400ms kayma.
    `default:"none"` slotu navigasyon crossfade'inden İZOLE eder.
  - **CSS:** `::view-transition{pointer-events:none}` (overlay tıklama
    yutmaz); root crossfade 200ms ease-in-out. Süre sabitleri KODA
    GÖMÜLMEDİ (token-kapısı disiplini); `prefers-reduced-motion` bloğu
    zaten evrensel `*` seçiciyle VT pseudo-element'lerini de sıfırlar —
    yeni kural eklenmedi (tek kural iki yüzey).
- **Kapı genişledi:** `test_dashboard_next_ui_contract.py` **40 → 50** (+10
  ViewTransitionTest): yalın sarmalayıcılar, import kaynağı `react` (shim/
  react-experimental yasak), header adı + üç çapa kuralı, crossfade yönsüz
  (nav-* VE translateX yasak), pointer-events guard, slot reveal çifti,
  slot/default izolasyonu, yön-yasağı taraması YALNIZ JSX özniteliklerinde
  (ilk sürüm yasağı ANLATAN kendi yorumuma yakalandı — tarayıcı,
  iddianın spesifikliğini kanıtladı).
- **Prodüksiyon-derleme kuralı (kullanıcı kararı):** VT kanıtı YALNIZ
  `next start` (production build) üzerinden; `next dev` VT'yi
  desteklemediği için dev-sunucu kanıtı ölçüt OLAMAZ. Statik kapı kaynağı
  denetler; canlı iddia smoke'un prod-derlemesinden gelir.
- **Canlı kanıt (production build, 9 iddia):** SSR `/` h1 + header VT adı;
  `/trend` tablo akış sonrası render (Suspense template — iskelet yalnız
  akış içinde); bundle CSS'te VT guard + header çapası + slot reveal
  kuralları + nav-* YOK + reduced-motion bloğu. **ALL PASS.**
- **Süit kanıtı:** ui-contract 50/50 · tip kapısı (tsc + 14 direktif iki
  geçiş) OK · check_tokens rc=0 · prettier temiz · `next build` yeşil
  (Next.js 16.3.6 Turbopack) · surface smoke **17/17** (19.7s) ·
  doc_job_sync 10/10 · sync/coverage `--check` rc=0.
- **Kapsam dışı:** `next dev` altında VT (kural gereği ölçülmez);
  Safari/Firefox'ta animasyon farklılıkları (guide'ın belirttiği degrade
  — uygulama düşmez, animasyon oynmaz). CI `dashboard-next` job'ı bir sonraki
  push'ta "Next 16" adıyla koşacak. Commit YAPILMADI.

### Soft-nav kanıtı bataryaya alındı (2026-09-28)

- **İstek:** "window-marker survival across / -> /trend" iddiası KALICI bir
  Playwright testi olsun — bugüne kadar yalnız 2026-09-19 turunun (work/
  2026-09-19)一次性 E2E kanıtındaydı (before=42 after=42); betik repoya
  girmemişti, tek kanıt findings.md notuydu.
- **Yer:** YENİ dosya DEĞİL — `test_dashboard_next_surface_smoke.py`e eklendi
  (17 → 19 test). Gerekçe: sunucu kablosu (preview_server + `next start` +
  log dizinleri) `test_surface_cwv_report`'tan TEK kaynak olarak import
  ediliyor; ikinci dosya ikinci boot hattı = drift (dosyanın kendi
  başlığındaki sözleşme). Dosya zaten CI `dashboard-next` job'ında,
  manifest DIŞINDA (Next boot pre-commit bütçesine sığmaz — aynı kural).
- **Ölçüm dili (iki sinyal, tek değerle yetinmemek):**
  - `window.__softNavProbe = 42` — probe UYGULAMA özelliği DEĞİL, testin
    kendisinin koyduğu işaret. Soru "uygulama onu tanıyor mu" değil
    "window nesnesi gezinmeden hayatta mı".
  - `performance.timeOrigin` — BELGE doğum zamanı. Soft navda SABİT kalır
    (aynı belge), tam yenilemede DEĞİŞİR. Marker tek başına yetmezdi:
    bozuk bir senaryoda kalıntı bellek "kalıcı" gibi görünebilirdi.
- **İki test, birbirinin karşıtı (vakum koruması):**
  - `test_soft_nav_preserves_window_marker_across_routes`: / üzerinde probe
    kurulur → GERÇEK Link tıklaması (`page.click`, `page.goto` DEĞİL —
    goto ile gitmek iddiayı vakum ederdi) → `/trend`te marker=42 VE
    timeOrigin aynı → geri dönüş (nav ÖZET linki) aynı iki iddia. Konsol/
    pageerror da boş olmalı.
  - `test_full_reload_resets_the_marker_counter_proof`: `page.reload`
    sonrası marker SIFIRLANMALI ve timeOrigin DEĞİŞMELİ. Soft-nav testinin
    "ayrım gücü"nü ölçer — reload marker'ı koruyabilseydi ilk test
    ayrım yapamıyor demekti.
- **Teşhis edilen iki gerçek (test yazılırken yakalandı, ölçümle):**
  1. `main a[href='/']` yok: panel sayfasının Link'i yalnız /trend'e GİDER;
     köke dönen bağlantı nav'dadır → dönüş de nav linkiyle ölçülür.
  2. `/trend` tam sayfasında `aria-busy` iskeleti BEKLENMEZ: panel slotları
     `(panel)` grubunda; `/trend` slotun DIŞINDA (bu yüzden gruba kondu).
     `_wait_panels(path=...)` kalktı, dönüş için yalnız URL bekleme +
     iddiası kaldı.
- **Kanıt:** izole teşhis koşumu → tıklama sonrası path=/trend, marker=42
  (aynı belge); tam süit **19/19** (22.6s) — 17 eski test bozulmadı.
  ui-contract 50/50 · sync/coverage `--check` rc=0 · prettier temiz.
- **Not:** VT turunun "soft-nav ön koşulu" iddiası artık sürekli ölçülüyor:
  Next 16 yükseltmesi Link davranışını bozarsa (ya da ileride bir refactor
  tam yenilemeye döndürürse) yüzey smoke'u kırmızıya düşer. Commit
  YAPILMADI.

### Skill-surface envanteri: manifest + fail-closed kapı (2026-09-28)

- **İstek:** skill alanlarının (RN/Expo, Stripe payments, Prisma,
  Postgres, …) repo yüzeylerini DENETLENEN bir manifest'e bağla; hook-coverage
  manifest gibi kapıyla senkron tut.
- **Temel ÖLÇÜM (tahmin değil):** budanmış os.walk → **6 package.json**, 29
  bağımlılık adı (0.01s). Alan imzaları ağaçta ölçüldü: rn-expo ve stripe
  SDK **SIFIR** yüzey; prisma=2 paket, postgres=2, next=1, react=3,
  remotion/pptx/docx/tailwind=1'er. Sıfır-yüzey iddialarının kaynakları
  2026-09-19 tur kayıtları (RN/Expo, Workers/wrangler, xlsx) — findings.md
  §"vercel-react-native-skills survey" ve workers/wrangler turları.
- **Manifest:** `_calisma/CIKTI/skill_surfaces.list` (checked-in, TEK
  KAYNAK) — 18 satır: 11 aktif (alan + paket imzası + yüzey yolu) + 4
  identity (marka-token mirror'ları) + 3 zero-surface (rn-expo, wrangler,
  xlsx). brand_mirrors.list roster deseni izlenir (o sözleşmeden farkı:
  mirror driftni değil SKILL KAPSAMINI denetler).
- **Kapı:** `check_skill_surfaces.py` (stdlib-only, OFFLINE, ~0.05s) —
  beş denetim: biçim, yol varlığı, İKİ YÖNLÜ paket denetimi (hayalet satır
  VE kayıtsız paket), zero-surface ihlali (imza paketi görünürse bloke),
  duplicate satır. `--check` fail-closed rc=1, `--json` makine-okunur,
  `--update` ÖNERİ üretir ama YAZMAZ (alan kararı insana aittir — paketi
  betik görür, alanı elle atarsın).
- **İlk koşum kapının KENDİ manifest hatalarımı YAKALADI (özellikle bu):**
  4 mirror satırı yanlış yolda (theme.css yerine tokens.css/raw.json)
  hayalet sanıldı + 13 arç paketi kayıtsız çıktı. İki sözleşme ölçümden
  doğdu: (1) **IDENTITY_ALIASES** — snapshot mirror'lar bağımlılık
  taşımaz (raw.css KOD değildir, paket kaydıdır), takma ad satırları yalnız
  yol varlığıyla denetlenir; (2) **TOOLCHAIN_NOISE** — prettier/typescript/
  esbuild/vite/tsx/dotenv/shadcn/cn/cva/lucide/@base-ui/tw-animate alan
  yüzeyi DEĞİLDİR, kayıtsız ihlali üretmez (küme KAPALI: yeni girdi testte
  gerekçelenir — kör genişleme yok). Ayrıca zero-surface imzaları çift
  rapordan muaf (kayıtsız + ihlal birlikte gürültü olurdu).
- **Test:** `test_check_skill_surfaces.py` **24/24** (0.040s) — hermetik
  FakeRepo fixture'ları (parse, iki yönlü paket, zero-surface üç dalı,
  identity muafiyet, arç-gürültüsü, @types muafiyeti, yol/duplicate, CLI
  --json/--update-yazmaz/usage-rc=2) + gerçek-repo invariint'ları (senkron,
  zero alanlar, KEŞİF haritası ↔ manifest tutarlılığı — harita alanı
  bilmezse satır kayıtsız sanılır). İlk koşum 8 hata verdi ve hepsi
  fixture/işlev hatalarıydı: SystemExit(2) rc'ye çevrildi, fixture'lar
  gerçek-repo 'zero alanlar TAMAMı kayıtlı' invariintını miras almasın diye
  `require_zero_domains` parametresi eklendi.
- **Kablolama:** zincire `check-skill-surfaces` hook'u **always_run: true**
  (envanter AĞAÇ-ÇAPRAZ: bağımlılık ekleyip manifest'e dokunmayan commit'i
  yakalamak istiyorsak kapı her committe koşmalı — files-only kalsaydı tam
  da o commit atlatırdı; ölçüldü: untracked manifest'le `--all-files` bile
  skip ediyordu). SKILL.md envanter bloğu 62 satıra çıktı +
  `check-precommit-inventory` sayı pini 61→62 güncellendi (iki taraf birlikte)
  + `HOOK_COVERAGE["check-skill-surfaces"]` + manifest satırı
  (`sync --update`).
- **Kanıt:** gerçek repo PASS (18 satır/3 zero alan/29 manifest tarandı) ·
  negatif kanıt fixture repo'da rc=1 + 'kayıtsız paket' bulgusu ·
  `pre-commit run check-skill-surfaces --all-files` → Passed ·
  precommit-inventory --strict PASS (62/62) · sync/coverage `--check` rc=0 ·
  doc_job_sync 10/10.
- **Kapsam dışı:** Python tarafı bağımlılıklar (requirements/venv) bu
  manifestte DEĞİL — kapsamı package.json yüzeyleridir (Python alan envanteri
  ayrı bir sözleşme olur). Commit YAPILMADI.

### work/2026-09-19 → reword-working ff-merge: 5. koşum, yine no-op (2026-09-28)

- **İstek (5 kez tekrarlanan):** "work/2026-09-19'ı reword-working'e merge
  et — beş commit üst üste (pptx fix, composition pass, perf dedup, survey
  docs) — sonra worktree'yi budak."
- **Bu turda ölçülen EN KESİN kanıt (önceki 4 turdan daha güçlü):**
  `git merge-base reword-working work/2026-09-19` = **`dd913c8`** — yani
  merge-base'in kendisi `work/2026-09-19`'ın UCU. Bu, "fark 0" sayımından
  daha güçlü bir kanıttır: dalın ucu aynı zamanda ortak tabandır, dolayısıyla
  hiçbir şey getirilecek durumda değildir. `merge-base --is-ancestor
  work/2026-09-19 reword-working` → **exit 0 (DOĞRU)**. Karşı yön 60 commit.
- **Beş öznelenin tamamı (5/5, önceki turda "üçü teyitli" idi):**
  `d396b8c` pptx fix · `9ce6e32` composition pass · `b156cb4` perf dedup ·
  `f0e21fe` RN survey · `41e1f48` client-side nav → `--is-ancestor` ile
  `reword-working` **ve** `main` İKİSİNDE de doğru. Yani beş özne yeni bir
  yığın değil, çoktan iki dalda da taşınan tarih.
- **Çalıştırılabilir kanıt (aynen, 5. kez):** `git worktree add --detach
  /tmp/ff-merge-check reword-working` (HEAD `1b93467`) → `git merge --ff-only
  work/2026-09-19` → **"Already up to date."** rc=0 → HEAD yine `1b93467` →
  `git worktree remove --force` rc=0 → `git worktree prune -v` **sessiz**
  (budanacak yetim yok). `git worktree list` = 3 kayda döndü; iki ref de
  çözülüyor. Ana ağaç **57 kirli dosyayla dokunulmadan** kaldı (43→57 artış
  bu turun işi değil, başka thread'lerin unstaged değişiklikleri); stash 2.
- **Kapatılmadı: `--strict` YANLIŞ bayraktı.** `check_skill_surfaces.py
  --strict` → argparse **rc=2** ("unrecognized arguments"); `--strict`
  `check_precommit_inventory.py`'nin bayrağı (advisory varsayılan, strict
  → rc=1). Skill-surfaces kapısının gerçek bayrağı **`--check`** (fail-closed
  rc=1, köre usage rc=2). Kapı adı "fail-closed" ve entry'si çıplak
  `python3 ...check_skill_surfaces.py` — yani varsayılan zaten gate
  modunda. İki kapı farklı eşleşme (envanter↔SKILL.md vs alan↔repo) olduğu
  için bayrağın karışması kolay; ikisi de ölçülüp doğrulandı.
- **Kapatılan boşluk — skill-surfaces kapısı TAM BATARYAYLA İLK KEZ koştu:**
  `make verify` → **`SWEEP: PASS — 5/5 adım yeşil (342.5s)`**. Batarya
  `check_unit_tests.list`'i okuyor ve `test_check_skill_surfaces.py` 39.
  satırda kayıtlı (grep ile doğrulandı — "geçmiş gibi görünüp aslında
  koşmamış" boşluğu kapatıldı); `sync_check_unit_tests.py --check` rc=0.
  Ayrıca doğrudan: kapı `--check` → PASS 18 satır/3 zero-surface/29
  package.json taranan · sözleşme **24/24** (0.038s) · envanter kapısı
  `--strict` → PASS **62/62** hook.
- **Ders (5. tur için güncel):** aynı merge 5 kez istendi, 5 kez no-op.
  "X dalını Y'ye merge et" isteğinde ilk ölçüm artık ucuz ve kesin olmalı:
  `git merge-base Y X` — ucu verirse iş yok (burada öyle çıktı). Özneler
  `--is-ancestor` ile hedef danda aranmalı; isim eşleşmesi yeterli değil.
  Gerçek fark yine aynı: yerel `reword-working` (1b93467),
  `origin/reword-working`'in **6 commit gerisinde** — bu, push/commit
  gerektiren iş; kullanıcı kararı gerektirdiği için YAPILMADI (commit,
  push, PR yok).

### Gerçek fark kapandı: reword-working ff + merge ön-ölçüm kapısı (2026-09-28)

- **Karar (kullanıcı):** (1) yerel `reword-working` origin'e
  fast-forward edilsin, (2) aynı no-op isteğin 6.'sını beklemeden yakalayan
  kalıcı kapı eklensin.
- **Fast-forward ÖLÇÜMLE güvenceye alındı:** `git fetch origin
  reword-working` sonrası yerel `1b93467`, uzak `a24c4db`. Üç koşul tek tek
  doğrulandı: (a) `merge-base --is-ancestor reword-working
  origin/reword-working` → **DOĞRU** (gerçek ff; hiçbir commit kaybolmaz),
  (b) `reword-working` hiçbir worktree'de **checked out DEĞİL** (hareket
  güvenli), (c) gelen 6 commit gerçek iş: a11y contrast gate, CI artifact
  sayfalama, vercel token sözleşmesi, branch-protection rehberi (22 dosya,
  +819/−361). `git branch -f` → `reword-working = a24c4db`, behind **0** /
  ahead **0**. ESKİ UÇ KAYBEDİLMEDİ: `reword-working@{1}` = `1b93467`
  (reflog). `main` `75b1b88`'de dokunulmadı, worktree listesi 3 kayıt,
  stash 2.
- **Kapı: `_calisma/CIKTI/check_merge_precondition.py`** (stdlib-only,
  OFFLINE, ~0.2s) — iki hatanın ikisini de ÖNCÜL olarak ölçer:
  * **ÇİFT modu** (`TARGET SOURCE`): gelen commit sayısı, ters yön, ve
    **KESİN no-op kanıtı**: `merge-base == kaynak ucu` → "Already up to
    date" beklenir. İki bağımsız kanıt (incoming==0 ve base==uc) aynı
    sonuca varması testte kilitli.
  * **`--subject`**: istekteki "pptx fix / composition / perf dedup"
    gibi özne adlarını arar ve her eşleşme için `target:VAR/yok`,
    `source:VAR/yok` raporlar. **"Yeni yığın" iddiası ölçülebilir** —
    isim eşleşmesi tek başına tarihin yerine geçmez.
  * **Audit modu** (argümansız): yerel dallar × upstream senkronluk.
- **Ölçülen çıktı — 5 turun senaryosu TEK komutta yanıtlandı:**
  `check_merge_precondition.py reword-working work/2026-09-19 --subject
  pptx --subject composition --subject per-request --subject "RN/Expo"
  --subject "client-side navigation"` → `gelen commit: 0`,
  `merge-base: dd913c8` (kaynak ucu), NO-OP; özneler: `composition
  9ce6e32 [target:VAR source:VAR]`, `per-request b156cb4`, `RN/Expo
  f0e21fe`, `client-side navigation 41e1f48` — yani beş özneden dördü
  **iki dalda da mevcut**. `--strict` → rc 1.
- **Tasarım hatası ÖLÇÜMDE YAKALANDI ve düzeltildi (kapı yazıldıktan sonra):
  audit'in ilk sürümü `behind == 0`'ı "no-op merge adayı" sayıyordu.
  Gerçek depoda koşturulunca 18 dalın **7'si** — `main` ve tam senkron
  `docs/coe-audit-table`, `pr/bf506c0` dahil — "bulgu" diye işaretlendi.
  Sebep ÖLÇÜMÜ: `behind == 0` **sağlıklı halin** işaretidir. Bu, kapıyı
  `make verify`'a bağlamadan önce görüldü; bağlansaydı her süpürmede
  sahte ağlama üretirdi. Düzeltme: no-op tespiti **yalnız çift modunda**
  yaşar; audit iki EYLEME DÖNÜŞEN sinyal ölçer — `stale_local`
  (ff-only ile ilerletilir; ÖLÇÜLEN gerçek: reword-working 6 gerideydi)
  ve `unpushed` (push edilmemiş commit). Senkron dal artık **sessiz** —
  bu bir regresyon testiyle kilitli (`test_in_sync_branch_is_not_reported`).
- **Test: `test_check_merge_precondition.py` 23/23** (4.8s). Fixture
  **GERÇEK geçici git deposu** (`git init -b main` + mktemp), sahte git
  çıktısı DEĞİL: kapının tamamı topolojiden besleniyor; sahte çıktı
  üreten fake, kapının yanlış olduğu yerde yeşil kalırdı.
  İlk koşum **20 test / 6 kırık** çıktı ve kırıkların HEPSİ iş/fixture
  hatasıydı, kapı hatası değil:
  - `FakeRepo` dokümanı `git init` vaat ediyordu, çağırmıyordu (hepsi).
  - **ÖNEMLİ:** `commit()` ÇALIŞILAN dala yazıyor; testler "kaynak
    ileride" senaryosunu `checkout` yapmadan kuruyordu → kaynak geride
    kalıyordu ve kapı doğru şekilde "no-op" diyordu (hata testteydi).
  - audit yönü karışmıştı (`behind = branch..upstream`).
  - Boş `--subject` girdisi `continue` ile entry'yi hiç eklemiyordu.
  - `argparse` fazla konumsalda SystemExit(2) atıyor; test `return`
    bekliyordu.
  - **ÖLÇÜLEN git kısıtı:** senkron dal fixture'ı kendini upstream
    yapamıyor — git reddediyor ("not setting branch as its own upstream",
    rc=0 ama upstream BOŞ; ölçüldü). Aynı commit'te duran AYRI ref
    upstream olarak kullanıldı.
- **Kablolama:** `verify_sweep.py`'ye **[3/6] merge-pre** adımı (cache
  adımlarından sonra, hepsi ~0.1-0.4s; build/batarya'dan önce).
  **ADVISORY kastı** — `--strict` DEĞİL: dalların upstream'in gerisinde
  olması günlük gerçek (ölçüldü: 18 dalın 6'sı geride, `main` dahil) ve
  `make verify`'ı kırmak bu adımın işi değil. Yalnız ölçüm hatasında
  (rc 2) fail-closed; ayrıntılı rapor betiğin doğrudan koşumunda.
  `test_verify_sweep.py` EXPECTED_STEPS 5→6 güncellendi (20/20).
  Test manifesti `sync_check_unit_tests.py --update --**no-stage**`
  ile senkronlandı (satır 31 + `HOOK_COVERAGE`); `--no-stage` seçildi
  çünkü `--update` `git add` yapıyor ve index'te başka thread'in işi
  var — dokunulmadı. Yeni **pre-commit hook EKLENMEDİ** (ölçüm dosya
  değil git topolojisi üzerine; hook eklemek 62→63 sayı pinini ve
  SKILL.md envanterini gereksizce genişletirdi) → envanter kapısı
  **62/62** kaldı.
- **Kanıt:** `make verify` → **`SWEEP: PASS — 6/6 adım yeşil (321.3s)**
  (battery 317.0s; `test_check_merge_precondition.py` manifest satır 31'de
  olduğu için batarya İÇİNDE koştu) · kapı tek başına 23/23 ·
  `verify_sweep.py` 20/20 · envanter `--strict` 62/62 · skill-surfaces
  PASS (18 satır) · `sync --check` rc=0 · coverage `--check` rc=0.
  Commit/push/PR YAPILMADI (yalnız kullanıcı onayıyla branch ref'i
  fast-forward edildi).

### Dedup probu → kalıcı test; ve `React.cache()` gerekçesinin ÇÜRÜTÜLMESİ (2026-09-28)

- **İstek:** "dedup probu"nu kalıcı teste çevir — sayan upstream'i ayağa
  kaldıran, derlenmiş pano sunucusunu çalıştıran, iki tüketici için TEK
  upstream isteğini denetleyen pytest.
- **Önce ÖLÇÜDÜM (tahmin değil) — ve ölçüm İDDİAYI DÜZELTTİ:**
  * `getLatest` → **tek** tüketici (`app/VerdictCard.tsx`, yalnız `@verdict`).
    Yani panoda "iki tüketici" YOK.
  * `getTrend` → iki çağrı yeri var ama **argüman farklı**: `getTrend(20)`
    (`app/trend/page.tsx`) ve `getTrend(5)` (`@trend/page.tsx`). React
    `cache()` argümana göre anahtarlandığı için bunlar AYRI önbellek girdisi —
    dedup örneği değil.
  * Canlı ölçüm (sayan upstream + `next start`, Next 16.3.6):
    `GET /` → `{'/api/latest': 1, '/api/trend': 1}` · `GET /trend` →
    `{'/api/trend': 1}`.
- **MUTASYON DENEYİ — asıl bulgu (b156cb4'ün gerekçesi ÇÜRÜTÜLDÜ):**
  Commit'in gerekçesi: "fetch request-memoization `cache:no-store` istekleri
  kapsamaz; `cache()` bu boşluğu kapatır." Next 16.3.6 üzerinde ölçüldü:

  | durum | `@verdict` içindeki `<VerdictCard/>` | `/api/latest` isteği |
  |---|---|---|
  | A | 1  + `cache()` VAR | 1 |
  | B | 2  + `cache()` VAR | **1** ← "2 tüketici → 1 istek" DOĞRULANDI |
  | C | 2  + `cache()` YOK | **1** ← !!

  Yani **gözlem doğru, atfedilen mekanizma yanlış**: `cache()` olmasa da
  upstream'e TEK istek gidiyor; çerçeve kendi `fetch`'ini istek kapsamında
  birleştiriyor. HTML kontrolü ikinci kartın da gerçekten render olduğunu
  doğruladı ("Son Koşum" 2→4; her kart HTML + uçuş (RSC) yükünde bir kez).
  **Bu yüzden test `cache()` varlığını DENETLEMEZ** — yokluğu davranışı
  değiştirmediği için onu sözleşme diye yazmak yanlış güvence verirdi
  (Mutasyon A'da kırıldı, davranış aynı kaldı).
- **Test: `test_dashboard_next_request_dedup.py`** (4 sözleşme, ~1.6s):
  1. `test_panel_render_hits_each_data_seam_exactly_once` — `/` render'ı her
     dikiş için tam 1, toplam 2 istek.
  2. `test_dedup_is_per_request_not_per_process` — iki render iki istek;
     süreç geneli (bayatlatıcı) önbellek sessiz doğruluk hatasıdır.
  3. `test_panel_touches_exactly_the_expected_upstream_seams` — dikiş KÜMESİ
     sabit; yeni bir fetch dikişi eklenirse upstream yükü sessiz artar.
  4. `test_counting_upstream_saw_real_traffic` — VAKUM denetimi: sayaç boş
     kalırsa bu dosyanın üç testi de sahte yeşil olurdu.
- **pytest talebi, repo gerçeği:** venv'de pytest **YOK** (`ModuleNotFoundError`;
  PATH'te homebrew pytest var). Dosya `unittest.TestCase` olarak yazıldı —
  pytest `unittest.TestCase`'i doğal topladığı için **İKİ koşucuda da** çalışır:
  ölçüldü → `python3 -m unittest` 4/4 OK, `pytest` 4 passed. Yani pytest'e
  özel altyapı (conftest/pytest.ini) gerekmedi ve repo koşucu geleneği bozulmadı.
- **Sunucu kablosu TEK kaynaktan:** `free_port`/`spawn_next_server`/`terminate`
  `test_dashboard_cls_budget` + `test_surface_cwv_report`'ten import edildi
  (surface smoke'un deseni). Playwright iki modülde de korumalı `try:` içinde
  olduğu için bu teste tarayıcı GEREKMİYOR.
- **Kablolama:** `sync_check_unit_tests.EXCLUDE` (Next boot'u bütçeyi aşar) +
  `test_coverage_report` içindeki `CI_JOB_COVERAGE["dashboard-next"]` ve
  `CHECK_EXEMPT` (metin biçimi `CHECK_EXEMPT = frozenset({` parse ile
  uyumlu korundu) + `.github/workflows/verify.yml`'de `dashboard-next`
  job'ına yeni adım — **Chromium kurulumundan ÖNCE**, derlemenin hemen
  ardından (daha hızlı geri bildirim, sıf��r ek bağımlılık).
- **Ölçülen yan etki (istenen davranış):** kapı ilk koşumda **kırmızıydı** —
  `make verify` battery `test_coverage_report` + `test_test_coverage_report`
  FAIL verdi (yeni dosya hiçbir hook'ta kapsanmadı). İki kayıt noktasına
  eklenince yeşile döndü; `dashboard-next` job test sayısı **19 → 23** ölçüldü.
- **Kanıt:** `make verify` → **`SWEEP: PASS — 6/6 (356.9s)** · yeni test
  unittest 4/4 + pytest 4 passed · kapsam kapıları (`test_coverage_report`,
  `test_test_coverage_report`, `test_gate_coverage_sync`,
  `test_sync_check_unit_tests`) OK · `sync --check` rc=0 · coverage `--check`
  rc=0 · workflow YAML parse + 13 adım doğru sırada.
- **Depo temizliği:** mutasyonlarda değişen iki dosya (`lib/preview.ts`,
  `@verdict/page.tsx`) yedekten geri alındı ve  `next build` yeniden koşuldu.
  `git diff` yalnızca Next 16 turlarının **commit'lenmemiş** ViewTransition
  işini gösteriyor; mutasyon izi YOK. Commit/push/PR YAPILMADI.

### /trend canlı: preview_server SSE → pano (yeniden yükleme yok) (2026-09-28)

- **İstek:** "/api/events'i preview_server'dan dashboard-next'e akıt ki
  verdict'ler yeniden yüklemeden güncellensin."
- **DÜZELTME — `/api/events` YOK.** preview_server'ın rota tablosunda böyle
  bir yol yok (ölçüldü: `_route()` içinde `api/events` eşleşmesi 0). Tek
  `/api/events` geçişi bir **test fixture'ı** (`test_repro_artifact_sections_e2e.py`
  içinde sahte bir HTTP haritası). Gerçek SSE ucu **`/api/run`**. Çerçeve
  sözleşmesi (`serve_sse`, ölçülüp okundu):
    * bağlantı anında `event: snapshot` (tam `_public_snapshot(LATEST)`)
    * her LATEST güncellemesinde `event: update`
    * boşta kalınca `: keepalive` yorum satırı (SSE_POLL_TIMEOUT=15sn)
  Adı `/api/events` tutmak istendiği için **pano tarafında** `/api/events`
  adıyla bir route handler açıldı; yani istenen ad yüzeyde mevcut.
- **TASIMA İÇİN SUNUCU DEĞİŞTİRİLMEDİ — neden ölçüldü:** preview_server
  **hiçbir** `Access-Control-*` başlığı göndermiyor (grep: 0). Pano başka
  bir origin'de (localhost:3000) → tarayıcı preview_server'a doğrudan
  bağlanamaz; `EventSource` açılsa bile ilk `message` gelmez. Bu yüzden akış
  SUNUCU TARAFINDA tünellendi (`app/api/events/route.ts`): tarayıcı aynı
  origin'deki `/api/events`'e bağlanır, Next upstream'e bağlanır. Sınır
  tarayıcıda değil sunucuda kalır; preview_server'a dokunulmadı.
- **Zenginleştirme:** upstream olayı yalnız verdict snapshot'ı taşır; trend
  geçmişi ayrı uçtan gelir. İstemci iki istek yapmasın diye her olayda
  `/api/trend?limit=N` SUNUCU TARAFINDA bir kez okunup zarfla birleştirilir
  (trend okunamazsa snapshot YİNE gönderilir — canlılık tek dikişin geçici
  kaybına bağlı değil). `limit` sorgu dizesine gittiği için 1..200 aralığına
  kırpıldı (serbest bırakılırsa beklenmedik pencere talebi çıkar).
- **Sunucu/istemci ayrımı markup'a dokunmadan yapıldı:**
  `test_dashboard_next_ui_contract.py` bu dosyayı ÜÇ sözleşmeye bağlıyor
  (`formatTimestamp` tüketicisi satır 653, `<time dateTime>`, `tabular-nums`
  satır 706). Tablo markup'ı `components/RunsTable.tsx`'te **birebir** kaldı;
  veri çekme yeni bir Server Component'e (`RunsTableData.tsx`) taşındı,
  `RunsTable.tsx` `'use client'` oldu ve `{rows, limit}` aldı. İki sayfa da
  `RunsTableData` kullanıyor. Sonuç: **50/50 UI sözleşmesi değişmeden yeşil**,
  SSR ilk boya korundu (JS gelmeden dolu ekran).
- **Kanıt (ölçüm, varsayım değil):** `test_dashboard_next_live_stream.py`
  yayınlayan upstream + `next start` + Chromium ile:
  1. SSR ilk pencere `>= 2` satır (sunucuda dolu basılıyor)
  2. canlılık göstergesi `role="status"` ile "canlı" görünüyor
  3. upstream değişti → satır sayısı ARTTI, DOM değişti
  4. **yeniden yükleme YOK**: `window.__liveMarker === 42` ve
     `performance.timeOrigin` DEĞİŞMEDİ (aynı desen:
     `test_soft_nav_preserves_window_marker_across_routes`)
  5. vakum denetimi: upstream'e `/api/run` bağlantısı gerçekten kuruldu
- **MUTASYON (testin dişi var mı):** `EventSource` aboneliği devre dışı
  bırakılıp yeniden derlendi → süit KIRMIZI: "`/api/run` hiç bağlanmadı —
  tünel ölçülmüyor" + ana test hata (23.6sn zaman aşımı). Yani ölçüm
  özelliğin yokluğunu GERÇEKTEN yakalıyor; yeşil bir "canlı" etiketine
  güvenilemezdi. Geri alındı, yeniden derlendi, mutasyon izi YOK.
- **Kablolama:** EXCLUDE (Next boot + Chromium, pre-commit bütçesine sığmaz)
  + `CI_JOB_COVERAGE["dashboard-next"]` + `CHECK_EXEMPT` + CI job'ında
  **Chromium KURULUMUNDAN SONRA** yeni adım (dedup adımı ise tarayıcısız
  olduğu için kurulumdan ÖNCE çalışır). Job test sayısı 19 → **25**.
- **Kanıt (toplam):** `make verify` → **`SWEEP: PASS — 6/6 (360.6s)** ·
  tip kapısı OK · `next build` yeşil (`ƒ /api/events` dinamik rota) ·
  ui_contract **50/50** · dedup sözleşmesi 4/4 · canlı akış 2/2 ·
  kapsam kapıları (`test_coverage_report`, `test_test_coverage_report`,
  `test_gate_coverage_sync`, `test_sync_check_unit_tests`, `test_doc_job_sync`)
  OK · `sync --check` rc=0 · coverage `--check` rc=0. Commit/push/PR YAPILMADI.

### Aynı no-op merge: 6. koşum (2026-09-28) — ve BOZUK BİR ÖLÇÜM YAKALANDI

- İstek yine aynı ("work/2026-09-19'ı reword-working'e merge et, sonra
  worktree'yi budak"). 6. kez ÖLÇÜLDÜ: `rev-list --count
  reword-working..work/2026-09-19` = **0**, `merge-base` = `dd913c8` =
  **kaynağın kendi ucu**, `merge-base --is-ancestor` → EVET. `git fetch
  --all` sonrası da değişmedi: dal **yerel-only** (uzak karşılığı yok), yani
  uzaktan da gelmiş olamaz. İstekte adı geçen üç commit (`9ce6e32`
  composition, `b156cb4` perf, `d396b8c` pptx fix) **reword-working VE main
  içinde**, `work` dalında da var ama çoktan taşınmış tarih — yığın değil.
  Çalıştırılabilir kanıt: `Already up to date.` rc=0, HEAD `a24c4db`'de sabit;
  `worktree prune -v` sessiz, liste 3 kayıt, ana ağaç 63 kirli dosyayla
  dokunulmadan.
- **ÖLÇÜM HATASI YAKALANDI (kendi yazdığım komut):** "work dalında tek başına
  duran commit var mı?" diye
  `git rev-list work/2026-09-19 --not main --not reword-working --not work/2026-09-19`
  çalıştırdım → **6** çıktı ve bu, "merge boş değil" izlenimi verdi — ki
  ÖYLE DEĞİL. Komut DEGENERE: aynı ref hem pozitif hem negatif verilmiş
  (`--not` toggle'ı), sonuç anlamsız. Doğru ölçüm
  `git rev-list work/2026-09-19 --not reword-working` = **0**.
  Ders: "X'te özgün kaç commit var" sorusu ASLA `--not X` ile birlikte X'i
  pozitif vermekle sorulmaz; pozitif taraf yalnız kaynak, negatif taraf yalnız
  karşılaştırılan ref olmalı. Çelişen iki ölçümü görünce (atası mı? / fark
  sayısı) BİRİNİ DOĞRULAMADAN raporlamak yanlış güvence üretir — buradaki gibi
  ciddi sonuçları çarpıtabilir.

### work/2026-09-19 dalı SİLİNDİ (2026-09-28, kullanıcı kararı)

- **Karar:** 6 no-op ölçümden sonra "dalı sil" seçildi. Silme **`git branch
  -d`** ile yapıldı (zorlayıcı `-D` DEĞİL): git'in kendi "tamamen merge
  edilmiş" kuralını uygulamasına izin verildi, yani "zararsız" iddiası bana
  değil git'e emanet edildi.
- **Silme öncesi beş güvenlik ölçümü:**
  * özgün commit: `work/2026-09-19 --not reword-working` = **0**
    (aynı ölçüm `--not main` ile de **0**)
  * hiçbir worktree'de değil (kayıt sayısı 0)
  * **uzak karşılığı yok** — dal yerel-only, yani silme hiçbir uzak
    referansı tutarsız bırakmaz
  * `merge-base --is-ancestor work/2026-09-19 HEAD` → **EVET** (HEAD=main)
  * dal ucu kayda geçti: `dd913c8`
- **Sonuç:** `Deleted branch work/2026-09-19 (was dd913c8)` rc=0. `main`
  `75b1b88`, `reword-working` `a24c4db` DEĞİŞMEDİ; worktree listesi 3 kayıt;
  kirli dosya 63, stash 2 — hiçbiri değişmedi. **İçerik kaybolmadı:**
  `dd913c8` ve tüm 7 commit'i her iki ana dalda mevcut.
- **Yan etki taraması:** dal adına referans arandı (py/yaml/json/md/sh/
  ts/tsx, node_modules + .worktrees + .vercel hariç). 5 eşleşmenin HİÇBİRİ
  işlevsel bağ değil:
  * `check_merge_precondition.py` docstring'i — 6 turun DERSİ (tarihsel
    gerekçe; KORUNDU, silinmesi kanıt izini bozardı)
  * aynı dosyanın `--help` örneği — **düzeltildi** (`ör. work/2026-09-19` →
    `ör. feature/yeni-is`; ölü dal kopyalanıp hata verse diye)
  * `test_dashboard_next_ui_contract.py` docstring'i — tarihsel commit
    bağlamı (KORUNDU)
  * `progress.md` — geçmiş oturum kaydı (KORUNDU)
  * `docs/UNCOMMITTED-INVENTORY.md:153` — **`work/2026-09-19` worktree |
    temiz** satırı. DOKUNULMADI ve bu bilinçli: dosya başlığında kendini
    "2026-09-27 → kapanış 2026-09-28" diye **kapanmış ölçüm kaydı** olarak
    tanımlıyor; o anda satır doğruydu. Kapanmış bir kanıt kaydını bugünün
    gerçeğiyle yeniden yazmak kaydı YANLIŞLAŞTIRIR. Aynı ilke: geçmiş
    ölçümünü düzeltme, gerekiyorsa YENİ kayıt ekle.
- **Kanıt:** `test_check_merge_precondition` **23/23** OK · `make verify
  ONLY=merge-pre` → `SWEEP: PASS 1/1 (0.4s)`. Tam süpürme bu turda
  koşulmadı (dal silme çalışma ağacına dokunmuyor; yalnız yardım metni
  değişti ve onun kapısı koşuldu). Commit/push/PR YAPILMADI.

### Silinen dalı merge etme isteği + merge-pre kapısında FAIL-OPEN (2026-09-28)

- **İstek:** "work/2026-09-19 dalındaki **11 commit**'i reword-working'e
  fast-forward merge et, sonra batarya+build ile doğrula." İki öncül de
  ölçümle ÇÜRÜTÜLDÜ:
  1. **Dal yok** — bir önceki turda KULLANICININ KARARIYLA silindi
     (`git branch -d`, "tamamen merge edilmiş" kuralı git tarafından
     doğrulandı). Kurtarma tek komut: `git branch work/2026-09-19 dd913c8`
     (uç her iki ana dalda mevcut, içerik kaybolmadı).
  2. **11 commit hiçbir yerde yok.** TÜM yerel dallar reword-working'e göre
     tarandı: öne sıra sayıları 1, 2, 2, 3, 5, 20, 85, 210 — 11 YOK.
     (Bu dal zaten 7 commit'likti ve tamamı merge'liydi; belki "7 + 4 geçmiş
     commit" gibi bir karışım.)
- **DOĞRULAMA İSTENEN KISIM YAPILDI:** `make verify` → **`SWEEP: PASS — 6/6
  (388.8s)** — build 4.7s PASS, battery 382.9s PASS. Bu turda tam süpürme
  koşuldu (önceki turda kasıtlı olarak koşulmamıştı).
- **KAPIDA FAIL-OPEN BULUNDU VE DÜZELTİLDİ (gerçek kusur):** doğrulama
  komutu silinmiş dalı denedi ve kapı şunu bastı:
      `PASS: birleşim işe yarar (None commit geliyor).`
  Sonra ölçüldü: **çıkış kodu aslında DOĞRUYDU (rc=2)**, önceki gördüğüm
  `RC=0` **benim ölçüm hatamdı** — `... | head; echo $?` deseninde `$?` son
  komutun (`head`) kodu verir, kapının değil. Bu, oturumun İKİNCİ kez kabuk
  yapısının bana yanlış sayı verdirmesi (birincisi `--not` ile aynı ref'i
  hem pozitif hem negatif vermekti). Ders: kapı rc'si boruya
  SOKULMAZ — `cmd > dosya 2>&1; echo $?` kullan.
  **Kusur yine de gerçekti:** rc=2 iken render "PASS" basıyordu. Fail-closed
  bir kapının günlüğünde ÖLÇÜLEMEN iş BAŞARILI görünürdü — tam da rc=2'nin
  var olma sebebi. Çıkış kodu yetmez, insan-okunur yüz de aynı sözleşmeye
  bağlı olmalı.
  Düzeltme: `render()` rc==2'de artık verdict basmaz; "ÖLÇÜLEMEDİ … Bu bir
  PASS/FAIL DEĞİLDİR" der. İki regresyon testi eklendi: (a) çıktıda
  `"PASS:"` YER ALMAZ, (b) çözülemeyen çift `no_op` sayılmaz (ölçüm yoksa
  iddia da yok). Süit **23 → 25**, ikisi de yeşil.
- **Kanıt:** `test_check_merge_precondition` **25/25** OK · silinmiş dal için
  GERÇEK rc=2 + "ÖLÇÜLEMEDİ" · geçerli çift bozulmadı
  (`reword-working ← main`: 85 commit, PASS, rc=0). Tam süpürme yeşil.
  Commit/push/PR YAPILMADI.


### Skill↔yüzey envanter dokümanı — "maratonda sıfır çıkanlar" (2026-09-28)

- **İstek:** "Maratonda sıfır-yüzey çıkan skill'leri tek bakışta gösteren bir
  skill↔yüzey envanteri dokümanı üret (findings.md turlarından derle)."
  Cevap **3 alan** ve hepsi KANITLANMIŞ iddia, eksik değil:
  `rn-expo` (0/7 imza paketi), `wrangler` (0/2), `xlsx` (0/3).
  Kanıt bölümleri: §vercel-react-native-skills survey (2026-09-19),
  §wrangler skill turn (2026-09-19), §xlsx surface audit (2026-09-19).
  Kalan **15** alan (18 satır) kod yüzeyi taşıyor; 4'ü "kimlik aynası"
  (paket imzası değil, snapshot `raw.css`/`raw.json` token yüzeyi).
- **Doküman ELLE yazılmadı — ÜRETİLDİ:** `docs/SKILL_SURFACE_INVENTORY.md`
  `gen_skill_surface_inventory.py` ile `skill_surfaces.list` + canlı
  `package.json` taramasından türetilir. Gerekçe ölçülmüş bir çürüme:
  `SKILL.md` envanteri 19 hook derken config'te 60 hook vardı, **41 kapı
  belgesiz** kalmıştı. Elle yazılan bir envanter kaçınılmaz olarak bayatlar;
  aynı hastalık bu alanda da tekrarlanmasın diye üretilir ve `--check` ile
  kendi kendini denetler (bayaltsa exit 1), `check-skill-surface-inventory-doc`
  pre-commit hook'u olarak bağlandı. 63. hook.
- **SIFIR-YÜZEY iddiasının ikinci kanıtı — kanıt bağlantısı canlılık testi:**
  doküman findings.md'ye atıf yapıyor; atıf ölürse doküman var olmayan
  kanıta güvence verirdi (yanlış güvence, en kötü hata). 4 test her
  `EVIDENCE`/`UNREGISTERED_EVIDENCE` başlığının findings.md'de HÂLÂ
  bulunduğunu pinliyor; bölüm yeniden adlanırsa kırılır. Ayrıca
  "her zero-surface alanın kanıt bağlantısı olmalı" ve "kanıt haritası
  yalnız GERÇEKTEN sıfır-yüzey alanları için olmalı" çift yönü.
  Süit **17 test**, tamamı yeşil.
- **⚠️ BULUNAN BOŞLUK — kanıt var, KAYIT yok:** findings.md 65. satırda
  `rust-async-patterns` için "Rust surface: zero" kanıtı var, ama bu alan
  `skill_surfaces.list`'te **YOK**. Bağımsız ölçüm: `git ls-files '*.rs'`
  = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 → **iddia bugün de geçerli**.
  Ama envanter kapısı yalnız MANIFEST'te yazılı alanları denetlediği için
  bu alan denetlenmiyor: yarın bir `Cargo.toml` eklenirse kapı sessizce
  geçecek. **Denetlenmeyen alan = denetlenmeyen yüzey.** Dokümanın en
  dürüst bölümü bunu "⚠️ Manifest'te olmayan kanıt" başlığıyla yayımlar
  (`UNREGISTERED_EVIDENCE`, git-tracked ölçümü `= 0` rakamlarıyla).
  → **`rust-async-patterns` + `ZERO_SIGNATURES` manifest'e EKLENMELİ.**
  Kullanıcı kararı bekliyor; bu turda manifest'e DOKUNULMADI.
- **DERS (üretilen çıktı kendi kendini bayatlatıyordu):** doküman başına
  ilk yazımda `generated_at` **duvar-saati damgası** konmuştu. Bu, kendi
  koyduğumuz kapıyı **kalıcı kırmızı** yapacaktı: her yeniden üretim farklı
  metin üretir → `--check` ASLA yeşile dönemez → insan susturur. Kırmızı
  kapı, hiç kapı olmayan durumdan daha kötüdür. Yerine girdinin **içerik
  özeti** kondu: `sha256(skill_surfaces.list)[:12]` = `c403f9b57d6d`.
  Doküman artık NEDEN üretildiğini (hangi girdi) gösteriyor, NE ZAMAN
  üretildiğini değil. `--json` çıktısındaki `generated_at` da aynı
  nedenle `manifest_digest` oldu. Ölçüldü: arka arkaya iki üretim
  birebir aynı (`IDEMPOTENT`).
- **DERS (sabit sayı dağınık halde çürüyor):** 63. hook eklendiğinde
  `make verify` battı: `test_check_precommit_inventory` **62** bekliyordu
  (3 ayrı assert'te). Kapının kendisi yeşildi (envanter senkron, 63) —
  çürüyen KAPI değil, TESTİN donmuş literal'iydi. Düzeltme yalnız sayıyı
  yükseltmek DEĞİL: dört ayrı yere dağılmış `62`'ler tek
  `REAL_HOOK_COUNT` sabitine toplandı (`62→63` artık tek satır). TÜretilmedi
  — türetilseydi "envanter 62 hook" gerçeği hiçbir yerde sabit kalmaz,
  sayı sessizce kayabilirdi. Süit **27/27** OK.
- **Kanıt:** `gen_skill_surface_inventory.py --check` → `PASS (18 alan,
  3 sıfır-yüzey)` · süit **17/17** · hook `Passed` · `make verify`
  → `SWEEP: PASS — 6/6` (battery 360.8s, 188 test dosyası). Commit/push/PR
  YAPILMADI; `AGENTS.md`/`README.md`'ye dokunulmadı.
### trend_rows=20 + verdict-parite E2E; hayalet "dashboard-smoke" job'ı (2026-09-28)

- **İstek:** "trend_rows=20 ve verdict-parite assert'lerini
  `test_dashboard_playwright_smoke.py` süitine ekle ki E2E-artığı
  commit-kapısında yakalansın." Ölçüm isteğin **üç ayrı yerini** yanlış
  buldu; kullanıcı kararıyla katman düzeltildi (aşağıda).
- **⚠️ ÖLÇÜM — hedef suite HİÇBİR YERDE KOŞMUYOR:**
  * `check_unit_tests.list`'te **YOK** → pre-commit `check-unit-tests`
    bataryası koşmaz (`sync_check_unit_tests.py:100` EXCLUDE).
  * `verify` job'ı `python3 -m unittest discover -s _calisma/CIKTI` ile
    dosyayı **keşfediyor**, ama o job'da Playwright **kurulu değil**
    (ölçüldü: `pip install playwright` yalnız 3139 `a11y-gate` ve 3631
    `dashboard-next` satırlarında) → `skipIf` ile **sessizce ATLANIYOR**.
  * `CI_JOB_COVERAGE["dashboard-smoke"]` bir CI job'ı adıyordu;
    `verify.yml`'de **böyle bir job YOK** ve hiçbir workflow bu dosyayı
    çalıştırmıyor. Yani kayıt, koşan bir kapı varmış gibi rapor veriyordu
    — fail-open'ın kardeşi: **kayıt var, koşum yok.**
  * Düzeltme (kullanıcı kararı: "hayalet kaydı düzelt"): `dashboard-smoke`
    girdisi `CI_JOB_COVERAGE`'dan **kaldırıldı**, gerekçesi kodda yazılı;
    `CHECK_EXEMPT` yorumu "CI'da ayrı job" yerine "hiçbir job'da koşmuyor,
    keşfedilip atlanıyor" diye düzeltildi. Dosya kapsam dışı kalıyor;
    gerçek bir job eklenirse kayıt geri gelmeli. `check_coverage_report
    --check` rc=0, kardeş süitler (`test_test_coverage_report`,
    `test_gate_coverage_sync`, `test_summary_pattern_drift`) yeşil.
  * **Doğru katman:** `test_dashboard_next_live_stream.py` — CI'da
    `dashboard-next` job'ında FİİLEN koşuyor (verify.yml:3650). Yakalama
    commit kapısında değil CI'da olur; commit kapısında koşabilen tek
    dashboard-next katmanı tarayıcısız `test_dashboard_next_ui_contract.py`.
- **Üretilen ölçüm (bu dosyaya eklendi, 2 → 4 test):**
  * `TrendWindowTest.test_trend_page_renders_exactly_twenty_newest_rows` —
    upstream **25** satırla açılır, `/trend` tablosu **tam 20** satır basmalı,
    ilk satır upstream'in **en yenisi** olmalı (sıra tekil ve artan), 3
    yayından sonra hâlâ 20 ve pencere **kaymış** (eski en yeni satır
    düşmüş) olmalı. İki ayrı sessiz hata bu ölçümü kırar: kırpma yok (limit
    ölü kod) ve ters sıra ("son 20" başlığı en ESKİ 20'yi gösterir).
    Ayrı sınıf + ayrı upstream **zorunluydu**: canlı-akış testi "yayın
    sonrası satır sayısı arttı" diye ölçtüğü için 25 satırlık ortak
    upstream onu bozardı (pencere 20'de doyardı).
  * `LiveStreamTest.test_verdict_panel_and_live_trend_describe_the_same_run`
    — pano (`/`) üzerinde `VerdictCard` (`/api/latest`) ile `RunsTable`
    (`/api/trend`) **iki ayrı uçtan** beslenir; parite bozulursa pano
    "Son Koşum: FAIL" derken tabloda üç saat önceki koşumu gösterir ve bu
    çelişki **hiçbir mevcut katmanda görünmez** (her kart ayrı ayrı
    doğrudur, statik sözleşme testleri yeşil kalır). Üç ölçüt: (a) verdict
    kartının damgası == tablodaki en yeni satır, (b) canlı göstergenin
    verdict'i == kartın verdict metni, (c) yayın sonrası tablo **öne
    geçer** (geriye kayma = tekrarlanan/bayat olay sızıntısı).
- **Fixture düzeltmesi (pariteyi ANLAMLI kıldı):** upstream `snapshot()`
  önce sabit `ts`/`verdict` basıyordu; "parite" ölçümü o zaman **her zaman
  "uyuşur"**, yani hiçbir şey ölçmezdi. Artık `snapshot()` **en yeni trend
  satısını** tarif ediyor (`/api/latest` = `LATEST` = history'nin son
  satırı, gerçek sözleşme) ve `push()` verdict'i de değiştiriyor. Damgalar
  `_ts(index)` ile **tekil ve artan**; eski `2026-09-2%d` + `index % 10`
  dizisi 10 satırda bir döndüğü için pencere 20'yi aşınca **en yeni
  sanılan satır en eskiydi** — yani ölçüm kendi ölçtüğü hatayı gizliyordu.
- **DERS — var olmayan testin bekleyişi BAĞLANMAMIŞ olmanın anlamını
  yakalıyordu:** eski ölçüm `/canlı/` diye bekliyordu; bu desen
  `RunsTable`'ın **bağlanmamış** göstergesinin kendi metniyle eşleşir
  ("canlı bağlantı bekleniyor" — içinde "canlı" var). Yani bekleme "bağlı"
  anını değil "bağlı değil" anını yakalıyordu; ilk koşuda verdict-parite
  testi tam olarak bununla `"canlı bağlantı bekleniyor"` okuyup düştü.
  Doğru ölçüt bağlı **ve** verdict basılmış hâli: `/canlı ·/`. Dört
  testin dördünde de bu ölçüte geçildi.
- **DERS (kendi assert'im yanlıştı, uygulama doğruydu):** sıra kontrolünü
  `for older, newer in zip(stamps, stamps[1:])` ile yazmış, değişkenleri
  ters adlandırmışım → "en yeni en eskiden büyük" kontrolü YANLIŞ yönde
  çalıştı ve ilk koşuda kırmızı verdi. Ölçüm **ilk çalıştırmada** kırıldı
  (yeşil'e ayarlanmadı), tablo fiilen yeni→eski basıyordu. Doğrulama: üç
  MUTASYONla testlerin boş olmadığı kanıtlandı —
  (1) `windowRows`'ta `slice(-limit)` → `slice()`: pencere testi
      `25 != 20` ile KIRMIZI; (2) `.reverse()` silindi: "ilk satır en yeni
      değil" (`00:05 != 00:24`) KIRMIZI; (3) `setVerdict("BOGUS")`:
      `'canlı · BOGUS' != 'canlı · PASS'` KIRMIZI. Uygulama kodu
      `cp /tmp/RunsTable.tsx.bak` ile **birebir** geri alındı (diff yok,
      `slice(-limit).reverse()` ve `setVerdict(payload…)` yerinde).
- **Kanıt:** süit **4/4** OK (yerelde gerçek Chromium ile; `Ran 4 tests in
  6.3s`) · 3/3 mutasyon yakalandı · `make verify` → `SWEEP: PASS — 6/6`
  (battery 359.1s) · `check_coverage_report --check` rc=0. Commit/push/PR
  YAPILMADI.
### `/api/trend?limit=N` — sunucu-tarafı pencere (refs_trend ile tutarlı) (2026-09-28)

- **İstek:** "/api/trend'e sunucu-tarafı limit desteği ekle (query-string
  okuyan, refs_trend ile tutarlı pencere) ve testle."
- **ÖLÇÜLEN BOŞLUK — parametre zaten VARDI, sunucu YOK SAYIYORDU.**
  `?limit=` belgelenmiş bir sözleşmeydi ve **iki canlı tüketici** onu
  gönderiyordu:
  * MCP `leibniz2_trend` → `_calisma/mcp/server.py:135`
    `/api/trend?limit={params.limit}`; `_calisma/mcp/README.md` tablosu
    bunu "?limit=N → **Son N koşumun** trend kayıtları" diye belgeliyor.
  * dashboard-next `lib/preview.ts` `getTrend(limit)` →
    `/api/trend?limit=${limit}` (pano slotu 5, `/trend` sayfası 20).
  `serve_trend` parametreyi hiç okumuyordu → ikisi de **İSTEDİKLERİ PENCEREYİ
  ALAMIYORDU**, `HISTORY_MAX=100` kaydın tamamını alıyordu. Yani bir model
  "son 5 koşumu getir" dediğinde 100 kayıt alıyordu ve farkı **sessizce**
  yok oluyordu.
- **Uygulanan sözleşme:**
  * `?limit=N` → **en yeni N** koşum; sıra korunur (eski → yeni). Yani
    `rows[-limit:]`; `rows[:limit]` en ESKİ N'yi döndürürdü.
  * **Parametre yoksa tüm geçmiş** (geriye uyum): `preview.js` `/api/trend`'i
    parametresiz çağırır; zorunlu olsaydı pano boşalırdı.
  * **Boş değer (`?limit=`) "penceresiz"**, 0 değil (`parse_qs` boş değeri
    düşürür). 0 ise 1'e kırpılır.
  * Kırpma **dashboard-next SSE tüneliyle birebir aynı**: `Math.trunc`
    (5.9 → 5), 1..200 sıkıştırma, sayıya çevrilemeyen → 20. Aynı değer
    tünolden geçerken ve doğrudan gelirken farklı pencere üretmemeli; iki
    katman ayrı kural uygularsa "hangi katmana göre?" belirsizleşir.
  * Bozuk parametre **400 değil** tanımlı pencere: okuma ucu, hata sayfası
    üretse pano sessizce boş kalırdı; pencere zaten sınırlı, güvenlik
    kazancı yok.
- **"refs_trend ile tutarlı pencere" = gövdenin İKİ yarısı aynı pencereyi
  anlatmalı.** `/api/trend` iki zaman serisini birleştirir ve `preview.js`
  ikisini **yan yana** basar (trend grafiği + refs-trend + duration/budget).
  Yalnız `history` kırpılırsa ekranda iki ayrı "son" görünür. Bu yüzden
  pencere `refs_trend.rows` **ve** `refs_trend.duration_budget.rows`
  listelerine de uygulanır.
  *Dokunulmayan:* satır listesi olmayan payload'lar, hata nesnesi
  (`{"error": ...}` — refs-trend.json okunamazsa 200 içinde gelir) ve
  `summary`/`totals`/`warnings`. Özetler `refs_trend.py`'nin TÜM artifact
  üzerindeki hesabıdır; burada yeniden hesaplamak **ikinci bir doğruluk
  kaynağı** doğururdu. "Özet 100 koşumu, satırlar 20'yi anlatıyor" farkı
  gizli kalmasın diye pencere uygulandığında gövdeye `limit` alanı eklendi —
  pencere yoksa alan da YOK (tüketici "tüm geçmiş" sanmalı).
- **Testler:** `test_preview_server.py` → yeni `TestTrendLimitWindow`
  (**11 test**): pencere + sıra, geçmişten büyük limit, parametresiz geriye
  uyum, boş değer, **iki yarının birlikte pencerelenmesi**, hata/eksik
  payload dayanıklılığı, kırpma sınırları, `Math.trunc` ayrışmaması,
  `window_tail` birim sözleşmesi ve **cross-layer drift guard** (`route.ts`
  kaynağındaki tavan/yedek sabitler Python sabitleriyle eşleşmeli).
- **Mutasyonla kanıtlandı (testler boş değil):** (1) kırpma kaldırıldı → 4
  test kırmızı; (2) `rows[:limit]` (en eski N) → 3 test kırmızı; (3)
  `window_refs_trend` çağrısı kaldırıldı → **yalnız** "iki yarı" testi
  kırmızı (tutarlılık sözleşmesinin tek sahibi o). Uygulama `cp` ile birebir
  geri alındı.
- **Canlı doğrulama (gerçek sunucu, 8 satırlık fixture + sunucunun kendi
  koşumu = 9):** parametresiz `history=9 refs=8 dur=8` ve `limit` anahtarı
  YOK · `?limit=3` → 3/3/3 · `?limit=0` → 1/1/1 · `?limit=9999` → 9/8/8
  (`limit=200`) · `?limit=abc` → tamamı (`limit=20`) · `?limit=2.9` → 2/2/2
  (`limit=2`) · `?limit=` → tamamı, `limit` anahtarı yok.
- **Yan etki taraması:** `/api/trend` gövdesine `limit` alanı eklendi;
  tüketiciler alan bazında okuyor (`preview.js` `data.history` +
  `refs_trend.duration_budget.rows`; Next `getJson<{history}>`; MCP ham JSON),
  gövde eşitliği kullanan tüketici yok. `docs/RUN_DASHBOARD.md` güncellendi.
- **Kapsam dışı bırakılan (ölçüldü, kullanıcı kararı gerektiriyor):** MCP
  README'si **dört** uçta da `?limit=N` belgeliyor — `/api/history`,
  `/api/refs-trend`, `/api/run-history` **hiçbiri** limit okumuyor
  (`serve_run_history` `load_run_logs(15)`'i sabit kullanıyor). Bu tur
  yalnız istenen `/api/trend` değişti; komşu uçlar **ayrı bir iş**.
- **Kanıt:** `TestTrendLimitWindow` **11/11** · `test_preview_server` +
  `test_api_method_contract` + `test_security_header_matrix` +
  `test_vercel_adapter` **206 test OK** · canlı sunucu ölçümü yukarıda ·
  `make verify` → `SWEEP: PASS — 6/6` (battery 320.9s). Commit/push/PR
  YAPILMADI.
### "work/2026-09-19'un 9 commit'ini merge et" — ÜÇÜNCÜ ÖLÇÜM (2026-09-28)

- **İstek (3. kez):** "work/2026-09-19 dalındaki 9 commit'i reword-working'e
  fast-forward merge et ve sonrasını batarya+build ile doğrula." Önceki iki
  turda 11 ve 7 denmişti; **9** yeni bir sayı olduğu için durum DEĞİŞMİŞ
  olabilirdi — ölçüldü, DEĞİŞMEMİŞ.
- **ÖLÇÜM (üç bağımsız kanıt):**
  1. **Dal yok.** `git rev-parse --verify refs/heads/work/2026-09-19` → yok.
     `git for-each-ref` ile TÜM ref'ler tarandı: 16 yerel dal + remote ref'ler
     arasında `work/*` **hiçbir** dal yok, `work/2026-09-19` uzak karşılığı da
     yok. Bu dal iki tur önce **KULLANICI KARARIYLA** silinmişti
     (`git branch -d`, "was dd913c8"; içeriği tamamen merge'liydi, 0 özgün
     commit, remote karşılığı yok).
  2. **9 commit'li dal yok.** Her yerel dal için
     `git rev-list <dal> --not reword-working` (DEJENERE olmayan biçim —
     aynı ref'i pozitif+negatif vermek anlamsız sayı üretir): 0,0,0,0,0,1,2,2,
     2,3,5,20,85,210. **9'a düşen dal YOK.**
  3. **Kayıtlı dal ucu hâlâ okunabilir ve içeriği KAYIP DEĞİL.**
     `dd913c8` nesne olarak duruyor ve `reword-working'in ATASI**
     (`merge-base --is-ancestor` → EVET). Yani `git rev-list dd913c8 --not
     reword-working` = **0**: dalın taşıdığı her şey zaten hedefte.
     7 commit'in (`dd913c8 11a673b 0d4196e ef0b6dc e286779 98b5acd 81a0f82`)
     YEDİSİ DE `reword-working` içinde, tek bir "EKSİK" yok.
- **Kapı doğru davrandı (fail-closed, önceki turun düzeltmesi kanıtlandı):**
  `check_merge_precondition.py reword-working work/2026-09-19 --subject "9
  commit fast-forward merge"` → **rc=2** ve insan-okunur yüz "PASS" değil
  "**ÖLÇÜLEMEDİ: hedef veya kaynak ref çözülemedi. Bu bir PASS/FAIL DEĞİLDİR
  — karar yok**" diyor. Merge denenmedi. Özne araştırması da `9 commit
  fast-forward merge → eşleşme yok` dedi. Bu, iki tur önce düzeltilen
  fail-open render hatasının **artık çalıştığının** kanıtı: aynı durum o
  zaman "PASS: birleşim işe yarar (None commit geliyor)" basıyordu.
- **NE YAPILDI:** Merge **YAPILMADI** — çünkü yapılacak bir şey yok; fast-forward
  boş bir merge olurdu ve `--allow-empty`-e ihtiyaç duyardı. İçerik zaten
  hedefte olduğu için birleştirmek hiçbir şeyi değiştirmezdi. Talep edilen
  doğrulama yine de **koşuldu** (aşağıda).
- **Doğrulama (istenen kısım YAPILDI):** `make verify` → **`SWEEP: PASS — 6/6`**
  (build 3.3s PASS, battery 305.3s PASS, merge-pre advisory PASS). Ayrıca
  `test_preview_server` + `test_api_method_contract` +
  `test_security_header_matrix` + `test_vercel_adapter` **206 test OK** ve
  `TestTrendLimitWindow` 11/11 (önceki turun işi). Commit/push/PR YAPILMADI.
- **Kurtarma (yine tek komut, hâlâ geçerli):** `git branch work/2026-09-19
  dd913c8` — dalı 7 commit'iyle geri getirir; içeriği zaten `reword-working`
  ve `main` içinde olduğu için merge yine 0 commit üretir. Bu dalı geri
  getirmek isteyen bir SEY varsa (9 commit'lik başka bir dal mı kastedildi,
  farklı bir repo mu), adını/commit'ini ver — ölçüm tekrar yapılır.
### Push isteği → commit (main) + iki ölçüm boşluğu (2026-09-28)

- **İstek:** "Push reword-working to origin so CI verifies the merge … and the
  branch has a remote backup." Ölçüldü ve **push'un hiçbir amacını
  gerçekleştiremeyeceği** çıktı:
  1. `reword-working` == `origin/reword-working` == `a24c4dba7afc…`;
     `git push --dry-run origin reword-working` → **"Everything up-to-date"**.
     ahead=0 · behind=0 · upstream zaten `origin/reword-working`. Gönderilecek
     commit YOK.
  2. Doğrulanacak **merge yok** (aynı gün 3. kez ölçüldü: `work/2026-09-19`
     hiçbir ref'te yok). Üstelik push olsaydı **hiçbir workflow tetiklenmezdi**:
     ref güncellenmediği için push event'i oluşmaz.
  3. **Bu oturumun işi `reword-working`'te değildi:** 69 değişiklik (27 yeni
     dosya) `main` üzerinde ve COMMIT EDİLMEMİŞTİ. Yani o dalı push etmek
     yedeklenmesi gereken şeyin **sıfırını** yedeklerdi.
  Kullanıcı kararı: **commit `main` üzerine, push sonra konuşulacak.**
- **Commit:** `da998b2` — 67 dosya, +10624/-268. 64 pre-commit hook
  Passed/Skipped, **0 Failed**; `check-unit-tests: 188 test dosyası PASS`.
  `reword-working` **DOKUNULMADI**. Başka thread'lerin iki stash'i
  (`pre-reword-stash: dirty entries from other threads`) **dokunulmadan**
  bırakıldı.
- **Commit sırasında ölçülen iki gerçek kusur:**
  * **1) `test_dashboard_keyboard_nav` tam bataryada FLAKY.** İlk commit
    denemesinde 343s'lik `check-unit-tests` koşusunda düştü
    (`1/188 BAŞARISIZ — commit bloke`); **tek başına 18/18 geçiyor (85.8s)**,
    ikinci denemede 188/188 PASS oldu. Yani test canlı preview_server +
    Chromium kullanıyor ve yük altında kararsız. Bu tür bir kapı, insanı
    `--no-verify`'ya iten tam olarak "gürültüye dönen kapı"dır; `--no-verify`
    **kullanılmadı**. Sonraki adım: süre bütçesi/koşu sırası incelenmeli.
  * **2) Prettier kapısı 2 dosyada geçmiş işi yakaladı**
    (`apps/dashboard-next/tsconfig.json`, `app/api/events/route.ts`).
    `npx prettier --write` ile düzeltildi; fark **tamamen biçimsel**
    (dizi tek satıra indirme, satır kaydırma, sondaki virgül) — anlamsal
    değişiklik YOK, `tsc --noEmit` yeşil.
- **Commit'ten BİLEREK çıkarılan iki untracked artefakt:**
  * `_calisma/CIKTI/_calisma/` — preview_server'ın **yanlış kökten**
    çalışmasından kalmış iç içe runtime ağacı (`logs/server_events.jsonl`,
    `history.jsonl`, `runs/run-*.json`, `history.jsonl.sha256`, 16 KB).
    Silinmedi (başka sürecin çıktısı olabilir), sadece commit'e alınmadı.
  * `_calisma/CIKTI/klayers.json` — `verify_delivery.py --klayers-out`
    **üretimi** CI sidecar'ı. **HİJYEN BOŞLUĞU:** kardeş runtime
    artefaktlarının hepsi gitignore'da (`_calisma/CIKTI/logs/`, `runs/`,
    `history.jsonl`, `history.jsonl.sha256`) ama `klayers.json` **yok** —
    `make verify` her koşuda onu üretip çalışma ağacını kirletiyor.
    Commit'e almak yanlış olurdu; `.gitignore`'a eklenmeli (ayrı iş).
- **Doğrulama:** `make verify` → `SWEEP: PASS — 6/6` (commit öncesi) ·
  commit sonrası 64 hook yeşil, `check-unit-tests` 188/188 PASS ·
  `check-skill-surfaces` 18 satır · `check-skill-surface-inventory-doc`
  güncel · `check-precommit-inventory` 63/63 senkron. **PUSH YAPILMADI**
  (`main` vs `origin/main`: ahead=138, **behind=4** → push zaten
  reddedilirdi; önce `da58b14 3f043bc c78dc67 fa1809b` alınmalı).
