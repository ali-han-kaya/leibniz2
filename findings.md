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
