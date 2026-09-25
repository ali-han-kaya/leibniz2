# A11y Gate Design (2026-09-17)

**Status:** Implemented (2026-09-24; report verdict field, job summary, local E2E evidence complete)

> **Local E2E evidence (2026-09-24):** gerçek preview_server (ephemeral port
> 54893) + gerçek headless Chromium (playwright 1.60.0 venv / chromium
> 148.0.7778.96) ile `a11y_gate.py` koşusu: `verdict: PASS`, rc=0; rapor
> `verdict` alanını taşıyor (summary: blocking 0, warn 0, allowlisted 0,
> incomplete 1 — color-contrast, report-only).
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
  and sha256. Implemented as axe-core **4.10.3** (npm tarball), sha256 pin in
  the sibling `axe.min.js.sha256` file. A checksum gate (fail-closed file-pin, same convention as the
  repo's pinned-value gates) fails the run if the bundle hash does not match
  the pinned value.
- `_calisma/CIKTI/a11y_gate_config.json` — thresholds and allowlist:
  `blocking: ["critical", "serious"]`, `warn: ["moderate", "minor"]`,
  `incomplete: "report-only"`, allowlist entries require a `reason` field.
  Allowlist semantics: entries match on axe `rule id` plus an optional
  `target` selector substring — a rule-level entry silences that rule
  everywhere; a target-scoped entry silences it only on matching nodes.
  Every allowlisted violation is still printed in the report marked
  `allowlisted`, so the table never hides debt silently.
- CI job (`a11y-gate` in `.github/workflows/verify.yml`): checkout →
  setup-python (existing pattern) → `pip install playwright==X.Y.Z` (exact
  version chosen at implementation time and recorded in the workflow; no
  floating pins) →
  `playwright install --with-deps chromium` (~3 min, cached via
  `actions/cache`; cache key includes the pinned Playwright version so an
  upgrade invalidates the browser cache) → start `preview_server.py` using
  the proven fresh-clone-smoke startup pattern (the job assigns an ephemeral
  port, waits for `GET /api/health` to return 200 with a bounded poll —
  30 × 1 s — then passes `--base-url http://127.0.0.1:PORT`) → run
  `a11y_gate.py` → upload JSON report artifact + job-summary table.

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

## Reporting Surfaces

Every run writes three surfaces, in increasing richness:

1. **stdout** — one-line verdict (`verdict: PASS|FAIL`) plus the violation
   table (rule, impact, node count); `warn` and `incomplete` rows appear here
   with their level, never silently dropped.
2. **`a11y_report.json`** (CI artifact) — full axe result payload, config
   echo (thresholds + allowlist with reasons), timestamps, and page URL, so a
   failure can be replayed locally.
3. **job summary** — a short markdown table of violations and the config
   echo; `warn`/`incomplete` findings appear here too. There are no PR
   annotations in scope (see YAGNI).

A `warn` never changes the exit code; it is a reporting level only.

## Error Handling (fail-closed)

- Server not up in time → **FAIL** (never skip). The readiness wait is
  bounded (30 × 1 s polls of `/api/health`); a browser crash mid-scan is a
  FAIL with no retry — transient browser flake must surface, not be masked.
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
