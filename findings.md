# Findings

## Repo facts (verified 2026-08-30)
- Repo: leibniz2, branch `feat/plist-info-line`, public GitHub repo `ali-han-kaya/leibniz2`.
- PR #42 open; HEAD `26d7201` (clarity pass) after `835510b` (dependency-closed sources).
- K9 Lean proofs (`_calisma/lean_reduct/`): `lake build --wfail` green, zero `sorry`,
  `#print axioms` → no axioms for reduct_invariance + Content.lean theorems.
- LaTeX: `ingiliz_empirizmi_v3.tex` (1537 LoC) + `core_section.tex`; no .bib (inline refs,
  64 expected, audited by K6).
- PDFs: delivery `ingiliz_empirizmi_v3.pdf` (33 pp), `original_manuscript.pdf` (19 pp);
  no Title/Author metadata on delivery PDF.

## CI status on HEAD 26d7201 (gh pr checks 42, 2026-08-30)
- FAIL (required): `Delivery verification — K1-K19 (single entry point)` ~2m07s
- FAIL (advisory): `CI-SIMULATE` ~1m37s (two runs), `Live CI doc↔GitHub sync audit` 21s
- PASS: K9 Lake proof, Budget shield, Budget status PR comment, CLI override trend,
  Changelog drift check, Action runtime check (node24)

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
