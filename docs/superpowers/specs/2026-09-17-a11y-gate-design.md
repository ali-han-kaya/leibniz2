# A11y Gate Design (2026-09-17)

**Status:** Approved design, awaiting implementation
**Author:** Buffy (Codebuff) with ali-han-kaya
**Path:** Architectural — new subsystem

## Summary

Add a fail-closed automated accessibility gate for the Live CI Dashboard
(`_calisma/CIKTI/preview.html` + `preview.js`), integrated into the existing
`.github/workflows/verify.yml` as a new job (`a11y-gate`). The gate loads the
dashboard in a real headless browser, runs axe-core against the rendered page,
thresholds violations against repo config, and reports a machine-readable
verdict using the repo's gate language (`PASS`/`FAIL`).

Design decisions locked during brainstorming:

1. **Engine:** real browser + axe-core (Chromium via Python Playwright). No
   Node/npm runtime dependency — the repo has no package.json; browser
   automation is Python-first, matching repo convention.
2. **Fail policy:** impact-thresholded + config-driven. `critical` and
   `serious` violations block; `moderate`/`minor` warn; `incomplete` results
   are report-only. Unknown impact levels block (default-deny).
3. **CI placement:** a new `a11y-gate` job inside `verify.yml` (same
   required-check surface as the existing 27 jobs — no new workflow file).

## Architecture and Components

- `_calisma/CIKTI/a11y_gate.py` — single-file Python script (repo gate
  convention). Responsibilities:
  - connect to a running preview server (base URL argument),
  - load the dashboard page in headless Chromium (Playwright),
  - inject the vendored axe-core bundle and collect violations,
  - threshold results against `_calisma/CIKTI/a11y_gate_config.json`,
  - emit `verdict: PASS|FAIL`, a violation table, and a JSON report file
    (CI artifact).
- `_calisma/CIKTI/vendor/axe.min.js` — vendored axe-core, pinned by version
  and sha256. A checksum gate (fail-closed file-pin, same convention as the
  repo's pinned-value gates) fails the run if the bundle hash does not match
  the pinned value.
- `_calisma/CIKTI/a11y_gate_config.json` — thresholds and allowlist:
  `blocking: ["critical", "serious"]`, `warn: ["moderate", "minor"]`,
  `incomplete: "report-only"`, allowlist entries require a `reason` field.
- CI job (`a11y-gate` in `.github/workflows/verify.yml`): checkout →
  setup-python (existing pattern) → `pip install playwright==X.Y.Z` (exact
  version chosen at implementation time and recorded in the workflow; no
  floating pins) →
  `playwright install --with-deps chromium` (~3 min, cached via
  `actions/cache`) → start `preview_server.py` using the proven
  fresh-clone-smoke startup pattern → run `a11y_gate.py` → upload JSON report
  artifact + job-summary table.

## Data Flow and Contract

```
verify.yml (a11y-gate job)
  └─ preview_server.py (127.0.0.1, ephemeral port)
       └─ a11y_gate.py --base-url http://127.0.0.1:PORT
            ├─ Playwright (headless Chromium) loads /preview.html
            ├─ inject vendor/axe.min.js → run axe
            ├─ load a11y_gate_config.json → threshold
            ├─ stdout: verdict + violation table
            └─ writes a11y_report.json (artifact)
```

Exit codes: `0` PASS, `1` FAIL (blocking violation or fail-closed condition),
`2` usage/environment error. Unknown severity in axe results → treated as
blocking.

## Error Handling (fail-closed)

- Server not up in time → **FAIL** (never skip).
- axe bundle checksum mismatch → **FAIL**.
- Playwright/browser failure → **FAIL**.
- Missing/invalid config → **FAIL** (config-drift gate pattern).
- No silent-green path exists; every failure produces a diagnostic line in
  the job summary.

## Testing

- `test_a11y_gate.py` (unittest, browser-free): verdict logic as pure unit
  tests — impact filtering, config parsing, unknown-severity fail-closed,
  allowlist `reason` enforcement, report JSON shape.
- In-process `HTTPServer` contract test: server unreachable → FAIL verdict.
- Sync infrastructure auto-registers the new test file into
  `check_unit_tests.list` + `HOOK_COVERAGE` (proven flow).
- The CI job itself is the browser integration test; local full-browser runs
  are optional and manual.

## Scope (YAGNI)

- Single page only: the dashboard. `guide.html` coverage and a historical
  score trend (determinism-trend pattern) are possible follow-ups, explicitly
  out of scope for this spec.
- No PR annotation bot, no Lighthouse scoring, no per-element screenshots.
