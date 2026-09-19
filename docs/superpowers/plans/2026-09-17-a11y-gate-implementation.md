# A11y-Gate Implementation Plan (2026-09-17)

**Spec:** `docs/superpowers/specs/2026-09-17-a11y-gate-design.md` (approved, reader-tested)
**Branch:** `reword-working` (current, clean — isolated workspace OK)
**Executor:** Buffy via executing-plans. Subagents not available in this environment.

## Reconnaissance results (constraints discovered)

- `preview_server.py --bind 127.0.0.1 --port N --interval 3600`; `GET /api/health` → `ok`.
- fresh-clone-http job (verify.yml ~2890) is the proven startup pattern: pid file + bounded health poll (30×1s).
- CI standard: `actions/setup-python@v6`, `python-version: '3.12'`; artifact steps `upload-artifact@v6`.
- axe-core 4.10.3 fetchable: `https://registry.npmjs.org/axe-core/-/axe-core-4.10.3.tgz` → `package/axe.min.js`.
- `_calisma/CIKTI/vendor/` is NOT gitignored → vendored file is committable.
- sync CLI: `sync_check_unit_tests.py --update|--check|--no-stage` auto-registers new test files.

## Tasks

### T1 — Vendor axe-core (pinned)
1. `mkdir -p _calisma/CIKTI/vendor`
2. Download tgz, extract `package/axe.min.js` → `_calisma/CIKTI/vendor/axe.min.js`
3. `shasum -a 256 axe.min.js > axe.min.js.sha256` (pin file, repo gate convention)
4. Append "Vendored assets" note to spec (version + sha).
**Verify:** `(cd _calisma/CIKTI/vendor && shasum -a 256 -c axe.min.js.sha256)` exits 0; file ≥ 400 KB.

### T2 — Gate config
Create `_calisma/CIKTI/a11y_gate_config.json`:
```json
{
  "blocking": ["critical", "serious"],
  "warn": ["moderate", "minor"],
  "incomplete": "report-only",
  "allowlist": []
}
```
**Verify:** `python3 -c` json.load + key assertions.

### T3 — Implement `a11y_gate.py` (stdlib-only until browser step)
Single file, argparse: `--base-url`, `--config`, `--axe`, `--output` (default `a11y_report.json`).
Flow: load+validate config (invalid → FAIL) → checksum gate on axe bundle (mismatch → FAIL) →
Playwright **imported lazily** (missing playwright = exit 2, usage/environment error) →
goto `<base-url>/preview.html` (wait until load) → inject axe source → `axe.run()` →
threshold: unknown impact → blocking (default-deny); allowlist matches rule id + optional
target substring; allowlisted rows reported as `allowlisted`, never hidden →
verdict = any blocking ? FAIL : PASS → write report JSON (axe payload, config echo,
page url, ts) → stdout verdict line + violation table (warn/incomplete rows included).
Exit codes: 0 PASS · 1 FAIL · 2 usage/environment.
**Verify:** `python3 a11y_gate.py --help`; import compiles; no-playwright path exits 2 with clear line.

### T4 — `test_a11y_gate.py` (unittest, browser-free)
Pure-unit: threshold filtering, unknown-severity fail-closed, allowlist rule-level +
target-scoped + `reason` enforcement, report JSON shape. Contract: in-process
`HTTPServer` unreachable/dead port → FAIL verdict path; checksum mismatch → FAIL;
invalid config → FAIL.
**Verify:** `python3 -m unittest _calisma/CIKTI.test_a11y_gate` (or path-run) all green.

### T5 — Sync registration
`python3 _calisma/CIKTI/sync_check_unit_tests.py --update` then `--check`.
**Verify:** `--check` exits 0; new test file present in `check_unit_tests.list` + coverage.

### T6 — CI job `a11y-gate` in verify.yml
Steps: checkout@v7 → setup-python@v6 (3.12) →
`pip install playwright==<PIN>` (query PyPI for newest published version; record pin;
cache key includes it) → `actions/cache` (key `playwright-<pin>`, path
`~/.cache/ms-playwright`) → `playwright install --with-deps chromium` →
start server with fresh-clone-http pattern (ephemeral port from Python, setsid+pid,
health poll 30×1s, fail if not ready) → run `a11y_gate.py --base-url … --output a11y_report.json`
→ always() upload artifact. Required-check surface = verify.yml jobs (no new workflow).
**Verify:** `bash _calisma/CIKTI/lint_actionlint.sh` PASS (all workflows incl. new job).

### T7 — Local end-to-end smoke (best effort)
Start real `preview_server.py` on ephemeral port; run `a11y_gate.py --base-url …`.
If local Playwright is installed → full scan (expect verdict line + report JSON).
If not installed → install locally (`pip install playwright`, `playwright install chromium`);
if that fails/slow, document: browser integration is proven by the CI job itself (per spec).
**Verify:** report JSON exists with `verdict` field; exit code matches verdict.

### T8 — Full local gate run
`python3 -m unittest discover -s _calisma/CIKTI` (whole suite) + actionlint + `sync --check`.
**Verify:** no new failures vs. pre-change baseline (4 known pre-existing
`test_check_python3_shell` dirts were proven on HEAD earlier).

## Out of scope (per spec YAGNI)
guide.html coverage, score trend, PR annotations, Lighthouse scores, retries.

## Finishing
After T8: use finishing-a-development-branch behavior — verify tests, then present
options (commit / PR / leave) to the human partner.
