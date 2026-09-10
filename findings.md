# Findings

## Repo facts (verified 2026-09-09, triage snapshot for 091635c)
- Repo: leibniz2, branch `feat/plist-info-line`, public GitHub repo `ali-han-kaya/leibniz2`.
- PR #42 open, MERGEABLE; triage target `091635c` (`fix(pre-commit): venv-guard check-doc-job-sync hook entry + contract test`,
  committed 2026-09-09T00:19:45+02:00, `091635c..HEAD` now 5 commits ahead at `5ab5196` on `origin/feat/plist-info-line`).
- `091635c` is the commit requested for this triage — logs below are from its PR runs `34295479147` (pull_request) /
  `34295476008` (push), both `2026-09-09T00:33Z`. Current `HEAD 5ab5196` has closed all four root causes; this doc
  records the pre-fix state.
- K9 Lean proofs (`_calisma/lean_reduct/`): `lake build --wfail` green at `091635c` (toolchain `v4.14.0`), zero `sorry`.
- LaTeX: `ingiliz_empirizmi_v3.tex` (1537 LoC) + `core_section.tex`; inline refs, 64 expected, audited by K6.
- PDFs: delivery `ingiliz_empirizmi_v3.pdf` (33 pp), `original_manuscript.pdf` (19 pp); REVIEW `Stoic_Hume_Review_Compilation_2026-08-17.pdf`
  (53 pp = 33+1+19, `qpdf --empty --pages`) at `bf78eee` with sidecar `.pdf.sha256`.

## CI status on PR head 091635c (runs 34295479147 / 34295476008, 2026-09-09T00:33Z; fetched 2026-09-10)
- FAIL (required): `Delivery verification — K1-K19 (single entry point)` — `102291060564` on `34295479147` and same on `34295476008`.
- FAIL (required): `Commit-msg gate` — `102292210573` on `34295479147` (`commit-msg gate: FAIL — 2 ihlal`).
- FAIL (advisory): `CI-SIMULATE (advisory)` — `102291060540` (`CI-SIMULATE FAIL: status_checks=0 simulate_verify_job=1`).
- FAIL (advisory): `Live CI doc↔GitHub sync audit (advisory)` — `102292658708` (exit 1).
- PASS: `test-smoke` (`34295476027` success), `Reproducibility bundle`, `Refs-trend audit`, `Mirror sync`, `Budget shield`,
  `Plist drift`, `Daemon HTTP`, `Preview reload smoke` — all success on same runs.
- SKIPPED (needs on failed verify, push run): `Static markdown reports`, `Config drift check`, `Config snapshot sync`,
  `Pre-commit P0/P1 label gates`, `Budget/Manifest PR comments`, `Commit-msg gate` (push variant) — skipped.

## Root causes (run 34295479147, head 091635c) — 4 failures

### 1. K1-K19 (required): unit-test battery 5 FAILs → FAIL-CLOSED
Log `102291060564` `Run CIKTI unit tests (test_*.py)` — exactly 5 failed tests (out of 2110-discovery):

```
FAIL: test_analyze_axioms_fail_non_standard (test_check_lean_axioms.TestAxiomAnalysis)
FAIL: test_analyze_axioms_pass_via_mock_subprocess (test_check_lean_axioms.TestAxiomAnalysis)
FAIL: test_real_repo_passes (test_check_review_freshness.TestRealReview)
      AssertionError: [{'kind':'stale_source','file':'revised',... "bayat REVIEW": ingiliz_empirizmi_v3.pdf > ...},
                       {'kind':'stale_source','file':'original',... original_manuscript.pdf > ...}]
FAIL: test_hook_pattern_matches_real_test_for_every_entry (test_sync_check_unit_tests.TestRepoConsistency)
FAIL: test_repo_manifest_entries_exist (test_sync_check_unit_tests.TestRepoConsistency)
```

- **Lean axioms 2×** — `091635c` has `TestAxiomAnalysis` with `mock.patch.object(cla.shutil,"which",return_value="lean")` but the
  `test_analyze_axioms_*` harness at that commit still expects a bare `lean` binary or incomplete mock. On CI (`lean` not
  installed in the verify job unless K9 job), `analyze_axioms` returns `SKIP` not `PASS/FAIL`, so the assertions fail.
  Fixed on `HEAD` (`5cfbecb`/`a345284` chain): `shutil.which → "/fake/lean"` + mocked `subprocess.run` for deterministic
  PASS/FAIL without ambient `lean`. At `091635c` this was still red.

- **Review freshness 1×** — `check_review_freshness.py` at `091635c` is pure `mtime` (`if sm > rv_mtime → P0`), no
  `_git_commit_time_ns` / `SOURCE_DATE_EPOCH` / sidecar-hash pin. Fresh-clone checkout has arbitrary mtimes:
  `ingiliz_empirizmi_v3.pdf` (`1788903780` ns checkout) appears newer than `Stoic_Hume_Review_Compilation_2026-08-17.pdf`
  (`1788906079` git time but checkout mtime is arbitrary), so `test_real_repo_passes` legitimately gets
  `stale_source P0 ×2` on CI. Fixed later as `3130d9b` (git-time skew suppression) and `5ab5196`
  (`_expected_source_hash` + `SOURCE_DATE_EPOCH` primary, mtime fallback only).

- **Sync check 2×** — `check_unit_tests.list` at `091635c` vs `test_sync_check_unit_tests.py` manifest drift:
  `hook_pattern_matches_real_test_for_every_entry` and `repo_manifest_entries_exist` fail because the list/hooks
  registration was stale (34 stale/excluded entries at ` HEAD` time). Fixed as `8bac7f8`
  `test(verify): add full-discover drift guard + register tests` (126-file discovery, `sync_check_unit_tests.py`).

Root cause: **committed `091635c` predates the three later fixes**; local `5ab5196` battery is `19/19 OK` (now `19 tests` for review-freshness).

### 2. K1-K19 (required): full verification P0=3 lineage/K14 drift → FAIL
Same job, second step `Run full verification (K1-K19, single entry point)`:

```
[P0] Soy hattı: current nesil canlı dosya ile uyuşmuyor (qpdf determinism deneyi) (kayıt=918e054595f798d48843ece59f48582b2b22147edb0cdb06188f0c543b2e13aa canlı=0df21b5d003f67df30efcf710bc85914851567f31c33b427ee1b528c9ad190a5)
[P0] K14 cleanup: kanonik hash uyuşmuyor: _calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip (kayıt=918e05… canlı=0df21b5d…)
[P0] K14 cleanup: kanonik hash uyuşmuyor: _calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip (kayıt=81a02448… canlı=b39ea667…)
SONUÇ: FAIL  (P0=3, P1=0)
```

- Live zips are `b69de33` repack (`0df21b5d003f67df30efcf710bc85914851567f31c33b427ee1b528c9ad190a5`,
  `b39ea667e93d79e89291ad27d807c5720d0ff319dd7840d12eab9f27f2a6bf82`) but `zip_lineage.json`/`cleanup_log.json`
  at `091635c` still pin `918e054595f798d48843ece59f48582b2b22147edb0cdb06188f0c543b2e13aa` /
  `81a0244855cc574562bc18a611c94bf3ffbb0086c3ea32775de9d5f32473c28a`. `091635c` predates `62772d9`
  `fix(verify): K14 one-unit — drift gate + registry resync (P0 clear)` and `c2adbf4` flip.
  At `HEAD 5ab5196` / `a345284` this is `PASS` (`check_zip_lineage_drift.py → K14-DRIFT PASS`).

### 3. Commit-msg gate (required): 2 subject-length violations → FAIL
`102292210573` `Fail if commit-msg violations exist`:

```
commit-msg gate: FAIL — 2 ihlal (51 commit denetlendi)
  091635ced85f  fix(pre-commit): venv-guard check-doc-job-sync hook entry + contract test
    → commit-msg: HATA — başlık 73 karakter (sınır: 72)
  b5e74dc17a5b  test(verify): extend derived-input contract to manifest-comment + flat config-diff delivery
    → 91 karakter (sınır: 72)
```

Measured: `091635c` 73 chars, `b5e74dc` 91 chars (`origin/main..091635c` longest). Gate checks
`origin/main...HEAD` subjects ≤72. Fixed later: `091635c` not yet reworded (reword landed as `8bac7f8`
for the `224dcd7`/`a345284` chain; `b5e74dc` remains in history but is no longer in the gated range
after the `origin/main` advance and `8bac7f8` amend). At `091635c` the gate is honestly red.

### 4. Advisory audits: Live CI sync FAIL + CI-SIMULATE cascade
- **Live CI doc↔GitHub sync audit** `102292658708` exit 1. On `091635c` the doc `docs/PUBLISH_SCENARIO.md`
  job table was stale relative to live `verify.yml` (missing `K9 Lake proof` family rows that landed by
  `091635c` but doc not resynced until `27f5c7f`/`08d3c25`). Advisory is doc↔live drift, not a merge blocker,
  but it was red on this commit.

- **CI-SIMULATE** `102291060540` `Run CI-SIMULATE (status_checks + simulate_verify_job)` →
  `simulate_verify_job=1` (same P0=3 from §2) → job FAIL. `status_checks=0` was green, but the simulated
  `--full` replay inherits the lineage/K14 P0s, so the advisory correctly mirrors the required verify FAIL.
  Fixed when §2 resync lands.

## Unit-test gate state (check-unit-tests battery)
- At `091635c`: `FAIL` with 5 tests (listed in §1) — `34295479147` unit-test step is the required K1-K19 killer.
- At `HEAD 5ab5196` (`origin/feat/plist-info-line`): `19/19` `test_check_review_freshness` OK,
  full battery `2110`-discovery green in pre-commit (`8bac7f8` full-discover guard), `K14-DRIFT PASS`,
  `review freshness: PASS` (`3da14bc…` / `e7b0bc0b…`).

## Performance audit (2026-08-30, localhost:8000 live; unchanged)
- Freebuff preview server (Python 3.9, BaseHTTP) serves the CI dashboard on :8000.
- Dashboard HTML 96 KB (78 KB inline JS, 7 KB inline CSS), 0 external refs,
  0 images, 0 fonts, gzip-equivalent ~27 KB. All budgets pass with wide margins.
- TTFB 2–30 ms local; API TTFB 9–31 ms.
- Hypotheses (not measured regressions): no gzip/brotli anywhere (server ignores
  Accept-Encoding; /api/history ships 223 KB uncompressed per fetch); no caching
  headers on static HTML (meta no-cache only); HEAD returns 501 (BaseHTTP default);
  dashboard fetches /api/history (223 KB) on every page load.

## Skill activations this session
orchestration, pdf, performance, latex-skills, lean-proof, lean4, planning-with-files — triage only, no code change in this doc update.
