# A11y Gate Design (2026-09-17)

**Status:** Implemented (local E2E evidence complete; uncommitted)

> **Yerel tarayıcı-E2E kanıtı (2026-10-06, Task 4 tamamlandı).** Playwright +
> Chromium bu makinede KURULU ve çalışıyor (`CHROMIUM_OK`); `preview_server`
> geçici portta, CI ile aynı mirror akışıyla ayağa kalktı. Altı gerçek tarama:
>
> | Yüzey | Tema | verdict | summary |
> |---|---|---|---|
> | `/preview.html` | dark | **PASS** | blocking 0 · incomplete 1 (3.6 sn) |
> | `/preview.html` | light | **PASS** | blocking 0 · incomplete 1 |
> | `/guide.html` | dark | **PASS** | 0 ihlal |
> | `/guide.html` | light | **PASS** | 0 ihlal |
> | `/landing.html` | dark | **FAIL** | witness bulunamadı (fail-closed) |
> | `/landing.html` | light | **FAIL** | aynı |
>
> **Bulunan ve düzeltilen gerçek ihlal:** ilk dashboard/dark taraması
> **FAIL** idi — `scrollable-region-focusable` (serious → blocking), düğüm
> `#runstream`: kaydırılabilir `<pre>` klavyeyle odağa alınamıyordu (WCAG 2.1.1).
> Allowlist'e yazılmadı; `preview.html` → `tabindex="0" role="region"
> aria-label="Run stdout akışı (kaydırılabilir)"` ile kapandı → yeniden tarama
> **PASS** (blocking 1 → 0). Kırmızı→yeşil döngüsü gerçek tarayıcıda ölçüldü.
>
> **Landing ölçülemedi (kusur değil):** `build_landing.py` "son koşum PASS
> değil" koşulunda landing'i üretmiyor; yerel verify `FAIL/exit 1` olduğu için
> `/landing.html` 404 → witness bulunamıyor → kapı fail-closed FAIL. CI'da
> `verify` PASS olduğu için üretilebilir. "PASS" diye yazılmadı.
>
> Kanıt dosyaları: `docs/ci_simulate/a11y_plan_2026-09-23/`
> (`plan_execution_evidence.md` + 6 rapor, `raw` alanı çıkarılmış).

> **Dashboard paneli (2026-10-06).** Aynı verdict/summary verisi artık canlı
> CI Dashboard'da da görünür: `preview.html#a11y-panel` (rozet şeridi) +
> `preview.js renderA11y()/loadA11y()`, veri kaynağı `/api/a11y`
> (`preview_server.load_a11y_reports`) — panel CI artifact JSON'larından
> (`a11y_<sayfa>_<tema>.json`) yalnız `verdict` + dört özet sayısını okur, ham
> `raw` axe payload'ı dışarı vermez. Fail-closed: artifact yoksa `available:
> false`, okunamayan/taşkın rapor `verdict: null` + gerekçe (panelde yeşil
> ASLA görünmez). Kapı: `_calisma/CIKTI/test_preview_a11y_panel.py` **32/32
> PASS** + canlı prob (6 rapor: 1 FAIL kırmızı, 1 bozuk amber, 4 PASS yeşil;
> artifact kaldırılınca "· a11y-gate: kanıt yok"). API sözleşmesi:
> `API_CONTRACT["/api/a11y"] = {"GET"}` + `openapi.json` yeniden üretildi
> (14 yol), referans: `docs/PREVIEW_API_REFERENCE.md`.
> İndirme kuralı: `gh run download … -D a11y-reports` (dizindeki alt klasör
> düzeni de aranır); dizin `.gitignore`'dadır.

> **Residual not (2026-10-06) — kapatma gerekçesi.** Spec, uygulama
> tamamlanmış hâliyle kapanır. Tek ertelenen parça **job-summary yüzeyinin
> canlı CI kanıtı**dır: yüzey kodda vardır ve sözleşme-testleriyle
> fail-closed çalıştığı doğrulanmıştır, ama gerçek bir CI koşumunda henüz
> *gözlenmemiştir*.
>
> Ölçüm (2026-10-06, `_calisma/CIKTI`):
>
> | Konu | Kanıt |
> |---|---|
> | report verdict alanı | `a11y_gate.py`: init default `"FAIL"`, hesaplanan değerle ezilir → `TestReportVerdictField` **2/2 PASS** |
> | job-summary yüzeyi | `verify.yml` → `a11y-gate` → `Write a11y job summary` (`if: always()`, `GITHUB_STEP_SUMMARY`) → `TestWorkflowSummaryStep` **4/4 PASS** (adım var · always+summary yazıyor · verdict'i okuyor · dashboard+guide+landing raporlarını kapsıyor) |
> | tam süit | `python3 -m unittest test_a11y_gate` → **60/60 PASS** |
>
> **Neden erteleniyor:** bu checkout'ta a11y üçlüsü (`a11y_gate.py`,
> `a11y_gate_config.json`, `test_a11y_gate.py`) hâlâ commit'lenmemiş
> durumdadır (HEAD ölçümü: `report["verdict"]` **yok**, `Write a11y job summary`
> **yok**). Tek-konu-commit'i (`feat(a11y): report verdict field + job
> summary surface`) üreten adım tamamlanmadan hiçbir CI koşumu bu yüzeyi
> göremez. Commit bu ortamda mümkün değil: `.git/config` → `bare = true`
> (`fatal: this operation must be run in a work tree`) ve tam batarya
> pre-commit zinciri, bu değişiklikten bağımsız olarak kırmızı
> (ölçüm: `unittest discover` → 3613 test / 54 failure; hiçbiri a11y yüzeyine
> ait değil).
>
> **Kapatma koşulu:** normal (bare olmayan) bir checkout'ta tek-konu-commit'i
> atmak ve `a11y-gate` job'ının `GITHUB_STEP_SUMMARY` çıktısını bir koşumda
> gözlemek. O gözlemden sonra Status satırından `(summary deferred)`
> ibaresi düşer ve belge kapanır.
>
> Bu not §Reporting-3 sözleşmesini değiştirmez: üçüncü yüzey zaten vardır;
> eksik olan yüzeyin kendisi değil, **canlı kanıtıdır** — ölçülmemiş bir
> PASS yazılmadığı için "deferred" bir tasarım kararı değil, kayıtlı bir
> çevre engelidir.

> **Local E2E evidence (2026-09-24):** gerçek preview_server (ephemeral port
> 54893) + gerçek headless Chromium (playwright 1.60.0 venv / chromium
> 148.0.7778.96) ile `a11y_gate.py` koşusu: `verdict: PASS`, rc=0; rapor
> `verdict` alanını taşıyor (summary: blocking 0, warn 0, allowlisted 0,
> incomplete 1 — color-contrast, report-only).
>
> **Guide expansion E2E evidence (2026-09-25):** fresh preview_server
> (ephemeral port 56252) + real headless Chromium (playwright 1.60.0 venv /
> chromium 148.0.7778.96) scanned both config targets: dashboard **PASS** and
> `/guide.html` **PASS**, rc=0 for each; both reports have blocking 0, warn 0,
> allowlisted 0, incomplete 0. The initial guide scan exposed 43 critical
> `label` violations; descriptive control names plus a single `main` landmark
> closed them and both moderate landmark findings.

**Author:** Buffy (Codebuff) with ali-han-kaya
**Path:** Architectural — new subsystem

## Summary

Add a fail-closed automated accessibility gate for the Live CI Dashboard
(`_calisma/CIKTI/preview.html` + `preview.js`) and the branch-protection visual
guide (`docs/branch-protection-guide/guide.html`), integrated into the existing
`.github/workflows/verify.yml` as a new job (`a11y-gate`). The gate loads each
configured page in a real headless browser, runs axe-core against the rendered
page, thresholds violations against repo config, and reports a machine-readable
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
4. **Page scope:** `pages[]` config is the allow-list of same-origin scan
   targets. Each target has a non-empty body-text `witness`; the gate fails
   before axe if the served page does not contain it. This keeps a 404/stale
   mirror or an accidental new URL from silently becoming a green scan.

## Architecture and Components

- `_calisma/CIKTI/a11y_gate.py` — single-file Python script (repo gate
  convention). Responsibilities:
  - connect to a running preview server (base URL argument),
  - select a config-declared page (`--page`, default `/preview.html`) and verify
    its body-text witness,
  - load that page in headless Chromium (Playwright),
  - inject the vendored axe-core bundle and collect violations,
  - threshold results against `_calisma/CIKTI/a11y_gate_config.json`,
  - emit `verdict: PASS|FAIL`, a violation table, and a JSON report file
    (CI artifact).
- `_calisma/CIKTI/vendor/axe.min.js` — vendored axe-core, pinned by version
  and sha256. Implemented as axe-core **4.10.3** (npm tarball), sha256 pin in
  the sibling `axe.min.js.sha256` file. A checksum gate (fail-closed file-pin, same convention as the
  repo's pinned-value gates) fails the run if the bundle hash does not match
  the pinned value.
- `_calisma/CIKTI/a11y_gate_config.json` — thresholds, page scope and
  allowlist: `blocking: ["critical", "serious"]`, `warn: ["moderate", "minor"]`,
  `incomplete: "report-only"`, allowlist entries require a `reason` field.
  `pages[]` has exactly two same-origin entries: `/preview.html` (witness:
  `Stoic-Hume V5 — Live CI Dashboard`) and `/guide.html` (witness:
  `Ayarlar → Branches — kural listesi boş`). A `--page` value outside this
  list is a config failure, not a free-form URL scan.
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
  30 × 1 s — then passes `--base-url http://127.0.0.1:PORT`) → copy the
  single-source `guide.html` and design tokens into its runner-local mirror →
  run `a11y_gate.py` once for `/preview.html` and once for `/guide.html` (the
  second run has `if: always()` so the first result never suppresses guide
  diagnostics) → upload the two JSON report artifacts + combined job-summary
  table.

## Data Flow and Contract

```
verify.yml (a11y-gate job)
  └─ preview_server.py (127.0.0.1, ephemeral port)
       ├─ a11y_gate.py --base-url http://127.0.0.1:PORT --page /preview.html
       │    ├─ witness: Stoic-Hume V5 — Live CI Dashboard
       │    ├─ Playwright (headless Chromium) loads /preview.html
       │    ├─ inject vendor/axe.min.js → run axe
       │    ├─ load a11y_gate_config.json → threshold
       │    └─ writes a11y_report.json (artifact)
       └─ a11y_gate.py --base-url http://127.0.0.1:PORT --page /guide.html
            ├─ witness: Ayarlar → Branches — kural listesi boş
            ├─ Playwright loads /guide.html → axe → threshold
            └─ writes a11y_guide_report.json (artifact)
```

Exit codes: `0` PASS, `1` FAIL (blocking violation or fail-closed condition),
`2` usage/environment error. Unknown severity in axe results → treated as
blocking.

## Reporting Surfaces

Every run writes three surfaces, in increasing richness:

1. **stdout** — one-line verdict (`verdict: PASS|FAIL`) plus the violation
   table (rule, impact, node count); `warn` and `incomplete` rows appear here
   with their level, never silently dropped.
2. **per-page JSON report** (CI artifacts) — `a11y_report.json` for the
   dashboard and `a11y_guide_report.json` for the guide. Each contains the full
   axe result payload, config echo (thresholds + allowlist with reasons), page
   path/URL, and a machine-readable verdict, so a failure can be replayed
   locally.
3. **job summary** — one table row per page plus its violation list and the
   config echo; `warn`/`incomplete` findings appear here too. Both reports are
   rendered even when the first scan fails. There are no PR annotations in
   scope (see YAGNI).

A `warn` never changes the exit code; it is a reporting level only.

## Error Handling (fail-closed)

- Server not up in time → **FAIL** (never skip). The readiness wait is
  bounded (30 × 1 s polls of `/api/health`); a browser crash mid-scan is a
  FAIL with no retry — transient browser flake must surface, not be masked.
- axe bundle checksum mismatch → **FAIL**.
- Playwright/browser failure → **FAIL**.
- Missing/invalid config, unlisted `--page`, or missing page witness →
  **FAIL** (config-drift / stale-mirror gate pattern).
- No silent-green path exists; every failure produces a diagnostic line in
  the job summary.

## Testing

- `test_a11y_gate.py` (unittest, browser-free): verdict logic as pure unit
  tests — impact filtering, config/page validation, witness requirements,
  unlisted-page fail-closed behavior, unknown-severity fail-closed, allowlist
  `reason` enforcement, report JSON shape, and the CI's two independent scan
  commands / artifacts.
- In-process `HTTPServer` contract test: server unreachable → FAIL verdict.
- Sync infrastructure auto-registers the new test file into
  `check_unit_tests.list` + `HOOK_COVERAGE` (proven flow).
- The CI job itself is the browser integration test; local full-browser runs
  are optional and manual.

### Follow-up: two-theme Lighthouse accessibility scan

The `a11y-gate` matrix also runs pinned Lighthouse 13.5.0 accessibility-only
against `/preview.html?theme=dark` and `/preview.html?theme=light`. The query
is a validated, non-persistent theme override used only to make the browser
context deterministic; each matrix child uploads its raw JSON report and
fails closed unless the accessibility category score is `1.0`.

## Scope (YAGNI)

- Exactly two server-rendered pages: the Live CI Dashboard and the
  branch-protection visual guide. Each is an explicit config entry with a
  witness; URL discovery, crawling, and arbitrary user-supplied scan targets
  are out of scope.
- A historical score trend (determinism-trend pattern), PR annotation bot,
  and per-element screenshots remain out of scope.
