# Findings

## Repo facts (verified 2026-09-04)
- Repo: leibniz2, branch `feat/plist-info-line`, public GitHub repo `ali-han-kaya/leibniz2`.
- PR #42 open, MERGEABLE; PR head `b82b412`; local branch 1 commit ahead (`e30f8ea`, status-checks
  lake-proof advisory fix, unpushed).
- The main checkout's uncommitted repair state (38 modified + ~28 untracked files) is what fixes
  the battery locally; CI tests the committed `b82b412` tree, which predates most of it.
- K9 Lean proofs (`_calisma/lean_reduct/`): `lake build --wfail` green, zero `sorry`,
  `#print axioms` → no axioms for reduct_invariance + Content.lean theorems.
- LaTeX: `ingiliz_empirizmi_v3.tex` (1537 LoC) + `core_section.tex`; no .bib (inline refs,
  64 expected, audited by K6).
- PDFs: delivery `ingiliz_empirizmi_v3.pdf` (33 pp), `original_manuscript.pdf` (19 pp);
  no Title/Author metadata on delivery PDF.

## CI status on PR head b82b412 (run 33548764812, 2026-09-01T19:18Z; fetched 2026-09-04)
- FAIL (required): `Delivery verification — K1-K19 (single entry point)` ×2 (runs 33548764812,
  33548759430) — ~2m; killed by the embedded check-unit-tests battery (see root causes below).
- FAIL (advisory): `CI-SIMULATE (advisory)` ×2 — simulated `--full` reports `SONUÇ: FAIL (P0=5, P1=0)`.
- FAIL (advisory): `Live CI doc↔GitHub sync audit` — `audit_live_ci_sync.py` exit 1 (doc↔live job drift).
- PASS: K9 Lake proof, Repack determinism, Mirror sync, Budget shield, Changelog/Merge-pattern drift,
  Action runtime (node24), Daemon HTTP, Plist drift, all PR-comment jobs.
- SKIPPED (needs: on failed verify): Config drift check, Static markdown reports, Config snapshot
  sync, P1/P0 label gates, Budget/Manifest PR comments.

## Root causes (run 33548764812, head b82b412)

### 1. K1-K19 (required): unit-test battery red on the committed tree
The job's battery (1669 tests / 123 files) fails on the **same 19-failure baseline** triaged
locally (see HANDOFF worktree baseline). CI-side evidence (exact FAIL ids in job log):
- `ci_stats` — committed module lacks `markdown_rows` / `stats_line` / `update_doc_block`
  (tests were committed ahead of the implementation).
- `classify_lean_error` — missing wiring symbols; `test_skill_mentions_detail_format` /
  `test_skill_priority_order_matches_code` expect the `[<class>]` detail format + priority table
  in `skills/verify-chain/SKILL.md` (skill doc not synced at b82b412).
- `check_lean_axioms` — `test_verify_delivery_imports_scanner` fails: verify_delivery does not
  import the axiom scanner; `test_admit_found` / `test_unsafe_declaration_found` fail on scan.
- `config_sync_badge.test_apply_snapshot_wired` — `preview.html` lacks
  `renderConfigSync(d.config_sync)` call.
- `check_bootstrap_start_smoke` — `--no-html` / `--no-mirror` not recognized by `bootstrap_all()`.
- `check_config_drift_summary.test_main_exit_codes` — fixture's Bundle step produced no
  `summary.txt` (fail-closed finding expected to surface).
- Plus: launchd_minimal_path, verify_manifest_sidecar, override_trend, diff_config_artifacts,
  dashboard_playwright_smoke, render_z3_slides, lake_evidence_smoke, fresh_clone_setup,
  coverage_report, gen_repro_manifest — all in the same 19-baseline.
Root cause: **committed HEAD is behind the local repair state**; the fixes exist only as
uncommitted work (main checkout) + the in-flight handoff worktree fix branch.
Note: the `check-unit-tests timeout: 10.001s > 10.000s` line in the log is a fixture's printed
output (check_unit_tests_timing test), not the killing gate.

### 2. CI-SIMULATE (advisory): 5 P0s in simulated --full
Simulate log (`SONUÇ: FAIL  (P0=5, P1=0)`):
- `[P0] Soy hattı: current nesil canlı dosya ile uyuşmuyor` — lineage record pins zip hash
  `918e0545…` but live committed zip is `0df21b5d…` (TESLIM_KLASOR_V5_2026-08-17.zip).
- `[P0] K14 cleanup: kanonik hash uyuşmuyor` ×2 — same zip pair + TESLIM_V5_FINAL zip
  (record `81a02448…` ≠ live `b39ea667…`).
- `[P0] K9 … lake bulunamadı` / `lean bulunamadı` — the CI-SIMULATE job has no lean/lake install
  steps, yet runs the K9 layer via --full → honest missing-tool P0s.
Root cause: **frozen lineage/K14 records predate the zip rebuild** (committed records ↔ committed
zips disagree), and **K9 tool installs are absent in the simulate job**. Related pre-commit
battery FAILED aggregates inside simulate: failures=2 / failures=6 / failures=3
(plist golden P1, K10 `audit_refs_trend` digest missing, pattern consistency).

### 3. Live CI doc↔GitHub sync audit (advisory)
`audit_live_ci_sync.json` (artifact `audit-live-ci`): verdict FAIL — `docs/PUBLISH_SCENARIO.md`
job table (24 jobs) is missing the live run's `K9 Lake proof (Lean 4.14.0)` job row
(`in live, not doc: ['K9 Lake proof (Lean 4.14.0)']`). Fix: add the K9 job row to the doc table.

## Unit-test gate state (check-unit-tests battery, venv python)
- ~25–26 failures remain after committing untracked sources; categories:
  1. `status_checks.py` (tracked) uses cwd-relative `.github/workflows/verify.yml`
     path; hook runs from `_calisma/CIKTI/` → 4 test failures
     (test_status_checks, test_status_checks_smoke, test_precheck_advisory_contract,
     test_gate_coverage_sync). Test-side fix landed; module still relative-path.
  2. Missing module symbols: ci_stats.markdown_rows, verify_delivery.write_json_sidecar,
     github_scripts_battery.find_launchd_tool, check_lean_axioms.check_sde,
     classify_lean_error.
  3. Dashboard HTML drift: preview.html edited, tests not updated (6 tests).
  4. Sync/manifest contract drift: K13/K9/m0/skill-layer/plist/gen-k-layer (6 tests).
  5. Misc genuine bugs: lean-statements, python3-shell, bootstrap-smoke
     (dirname/mktemp arg parsing), lean-override KeyError, repro-artifact-e2e,
     update-preview --sync-server.

## Performance audit (2026-08-30, localhost:8000 live)
- Freebuff preview server (Python 3.9, BaseHTTP) serves the CI dashboard on :8000.
- Dashboard HTML 96 KB (78 KB inline JS, 7 KB inline CSS), 0 external refs,
  0 images, 0 fonts, gzip-equivalent ~27 KB. All budgets pass with wide margins.
- TTFB 2–30 ms local; API TTFB 9–31 ms.
- Hypotheses (not measured regressions): no gzip/brotli anywhere (server ignores
  Accept-Encoding; /api/history ships 223 KB uncompressed per fetch); no caching
  headers on static HTML (meta no-cache only); HEAD returns 501 (BaseHTTP default);
  dashboard fetches /api/history (223 KB) on every page load.

## Skill activations this session (no-op unless task given)
orchestration (Orca not running; guide loaded via `orca skills get orchestration`),
pdf, performance, latex-skills, lean-proof, lean4, planning-with-files.
