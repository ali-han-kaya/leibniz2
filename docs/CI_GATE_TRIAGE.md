# CI Gate Triage — How to Diagnose a Failing Verify Run

**Audience:** maintainers of this repo.
**Goal:** turn a red `Delivery verification — K1-K19` or `CI-SIMULATE` check into its
root cause in minutes, using the diagnostic chain proven during the PR #42
investigation (2026-08-30).

## The failure chain to look for

CI failures in this repo rarely have one cause. The common cascade is:

```
untracked file that committed code needs
  → ModuleNotFoundError at unittest discovery (loader ERROR)
    → "Run CIKTI unit tests" step fails
      → non-always() install steps (pdfinfo, Z3, Lean) are SKIPPED
        → verify_delivery.py --full runs without pdfinfo
          → K11 P1 (page count uncomputable)
missing contract doc (e.g. docs/HOOK_ENV_MATRIX.md)
  → K17 P1 (mirror contract unsatisfiable on a fresh checkout)
both → CI-SIMULATE mirrors the same failures
```

Key insight: **the K-layer finding is a symptom, not the cause.** K11 saying
"pdfinfo missing" on a runner where the workflow installs pdfinfo means the
install step never executed — go up the chain.

## Step 1 — Identify the failing required checks

```bash
gh pr checks <PR-number> | grep -Ev "pass|skipping"
```

Required gates are `Delivery verification — K1-K19` and `CI-SIMULATE`.
Advisory jobs (named `advisory`) do not block the merge.

## Step 2 — Read the failed-job log

```bash
gh run view --job <job-id> --log-failed > /tmp/job.log
grep -nE "P0|P1|K[0-9]+" /tmp/job.log | head -20
```

Note the K-layers with P1 findings and their exact detail strings.

## Step 3 — Determine which steps actually ran

The GitHub API is ground truth for step execution:

```bash
gh api repos/<owner>/<repo>/actions/jobs/<job-id> --jq \
  '.steps[] | "\(.conclusion)\t\(.name)"'
```

If `Install pdfinfo` shows `skipped` while the workflow file contains it, the
unit-test step failed first and the install steps are gated behind its success
(they lack `if: always()`). Confirm with:

```bash
grep -n "ModuleNotFoundError\|loader ERROR" /tmp/job.log
```

## Step 4 — Find the untracked dependency

Committed code referencing files that were never committed is the dominant
root cause on this repo (115 untracked files existed at investigation time).
Scan for it with an absolute-path-based scan (relative-path scans silently
return nothing — a known trap):

```bash
python3 - <<'PYEOF'
import re, subprocess, os
root = subprocess.run(['git','rev-parse','--show-toplevel'],
                      capture_output=True, text=True).stdout.strip()
untracked = subprocess.run(['git','ls-files','--others','--exclude-standard'],
                           capture_output=True, text=True).stdout.splitlines()
untracked_py = {os.path.basename(f)[:-3] for f in untracked
                if f.startswith('_calisma/CIKTI/') and f.endswith('.py')
                and not os.path.basename(f).startswith('test_')}
tracked = subprocess.run(['git','ls-files'], capture_output=True,
                         text=True).stdout.splitlines()
for f in tracked:
    if not (f.startswith('_calisma/CIKTI/') and f.endswith('.py')):
        continue
    src = open(os.path.join(root, f), encoding='utf-8', errors='ignore').read()
    missing = sorted(set(re.findall(r'(?:from|import)\s+([a-z_][a-z0-9_]*)', src))
                     & untracked_py)
    if missing:
        print(os.path.basename(f), '->', ', '.join(missing))
PYEOF
```

At investigation time this printed:

```
audit_live_ci_sync.py -> ci_failure_pattern
consolidate_summary.py -> run_summary_k12
test_audit_live_ci_sync.py -> ci_failure_pattern
```

## Step 5 — Check the mirror contract files

K17 compares repo files against a macOS mirror. Any file in the mirror
contract that is untracked fails on a fresh CI checkout:

```bash
git ls-files docs/HOOK_ENV_MATRIX.md   # empty output = untracked
grep -n "HOOK_ENV_MATRIX" _calisma/CIKTI/sync_verify_mirror.sh
```

## Step 6 — Fix by committing the dependency-closed set

Stage only what committed code or the mirror contract needs:

- **Must commit:** untracked modules imported by tracked code, their test
  files, and contract docs (`docs/HOOK_ENV_MATRIX.md`).
- **Never commit:** local state and secrets (`.env.local`, `.vercel/`,
  `.agents/`), runtime logs, and generated `docs/ci_simulate/` reports.

Then re-run the failing modules locally before pushing:

```bash
cd _calisma/CIKTI && python3 -m unittest discover -s . -p "test_*.py"
```

## Known trap: relative-path scans return nothing silently

A dependency scan run with `cwd` inside `_calisma/CIKTI` that passes repo-root
relative paths to `open()` reads nothing and reports zero dependencies. Always
resolve paths against `git rev-parse --show-toplevel` (see the scan above).

## Out-of-scope hardening (reported, not part of triage)

- Make the pdfinfo/Z3/Lean install steps `if: always()` so tool absence fails
  loudly at the install step instead of surfacing as a distant K-layer P1.
- Make `refs_trend.py` write `refs-trend.json` atomically (`tmp` +
  `os.replace`), mirroring the history sidecar pattern.

## Environment-skip legitimacy — which environment-skipped suites count as legitimate in CI

Decision recorded 2026-10-25, audited against `verify-delivery` run
40236083284 (main @ 35c5e298). Enforcement lives in the unit-test hook's
vacuous classifier (`_calisma/CIKTI/check_zero_check_fail_open.py` +
`_calisma/CIKTI/check_unit_tests_hook.sh`).

The decision line is **step ordering in `.github/workflows/verify.yml`**:
`jsonschema`, `Pillow` and `PyYAML` are installed **before** the unit-test
battery (`if: always()` steps); `pdfinfo`/`qpdf`, Z3 and Lean are installed
**after** it (they only run when the battery is green), and tectonic/TeXLive
is installed only by `determinism-trend.yml`.

| Skip class | Legitimate in CI? | Enforcement |
|---|---|---|
| Whole-file **measured** skip (`Ran N>0 … OK (skipped=N)`) of a manifest suite pinned in `CI_FULL_SKIP_ALLOWANCE` — currently only `test_z3_slide_reproducibility.py` (reason: `tectonic yok`) | **Yes** | Classifier returns `ALLOWED` (rc 0) only when called with `--suite <name>`; the hook prints `izinli tam-skip (CI'da meşru)` visibly; allowlist contents pinned by `TestCiFullSkipAllowlist` |
| Whole-file skip of any other manifest suite | **No** | `vacuous` → hook prints `FAILED: <file> — … 0 gerçek test` and blocks the commit |
| Whole-file skip with no `Ran N` line (unmeasurable output) | **No — never allowlisted** | Measurement absence ≠ legitimate skip |
| Partial skips of tools the unit job does **not** install before running tests: playwright/Chromium, pdftotext (poppler), tectonic, lean/lake (`~/.elan`), plutil (Linux runner), safedriver/Xcode (macOS-only), `.venv_z3` provisioning, dashboard `node_modules` (tsc/prettier/pptx), prisma generate, live inputs (history.jsonl, K12 sidecar, experiment reports), daemon-HTTP (skipped by design in CI) | **Yes** | Reported per file and in totals (`N test, K skip`); the file must still execute ≥1 test — otherwise it becomes a whole-file skip and the rules above apply |
| Partial skips of `jsonschema` / Pillow / PyYAML | **No** | Installed before the battery with `if: always()` — a skip means the install step regressed; a full skip fails as vacuous, a partial skip stays visible in the counts |

**Counting rule:** executed-test counting prefers the per-test `... ok`
lines of a `-v` log — the hook (`run_one_file`) and the parallel runner
(`run_unit_tests_parallel.py`) both pass `-v`. The `Ran − skipped` summary
arithmetic is only the fallback for summary-only logs, because a class-level
`setUpClass` skip inflates `skipped=` without reducing `Ran`: that pairing
produced a false VACUOUS on `test_dashboard_webkit_smoke` even though its
static layer had executed (measured locally, 2026-10-25).

**Boundary:** suites excluded from the manifest (`sync_check_unit_tests.py`
`EXCLUDE` — `test_dashboard_playwright_smoke.py`, `test_lake_evidence_smoke.py`)
and suites outside `_calisma/CIKTI`
(`docs/branch-protection-guide/test_render_screens.py`) are never seen by the
classifier; the aggregate battery step and their own hooks cover them.

**Audit evidence** (run 40236083284, 184 manifest files): exactly **one**
manifest suite executed zero tests in CI — `test_z3_slide_reproducibility`
(`tectonic yok`, allowlisted above). 16 suites partially skipped, every
reason from the legitimate-partial list. No jsonschema/Pillow/PyYAML suite
skipped at all — those installs were healthy.

**Changing the decision:** edit `CI_FULL_SKIP_ALLOWANCE`, its pinning test
(`TestCiFullSkipAllowlist`) and this table in the same commit. Moving a
tool's install step *before* the battery (e.g. the hardening item above)
makes that tool's skips illegitimate — update the table and the allowlist
together.

**Triage note (advisory red ≠ gate red):** the
`Run check-unit-tests hook (separate)` step is `continue-on-error: true` —
a proof step, not a gate. A red there while the battery stays green is
nondeterminism, not a gate failure (observed 2026-10-25: one in-job
`test_consolidate_summary` FAILED out of three runs, never reproducible
locally; the HEAD hook at the time swallowed the traceback with
`>/dev/null` — the classifier hook keeps per-file output, so the next
occurrence is directly diagnosable).

## Advisory verdict loss — `Verify advisory exit sidecars (fail-closed)`

The four advisory steps in the `verify` job (`precommit`, K13, K12,
`check_unit_tests`) record their exit code in `logs/*.exit`.
`continue-on-error: true` keeps the job green, so when `errexit` swallows
`status=$?` (or the step crashes or is skipped) the sidecar is never
written and the verdict disappears without a red job. That happened before
(measured: `logs/precommit.exit` absent while the K12/K13 sidecars existed).

`check_advisory_exit_sidecars.py` closes that class:

- **runtime** (`--dir logs`): every registered sidecar must exist and hold an
  exit code (0–255). Missing/empty/unparseable = FAIL. The *value* is not
  judged here — that is the producing gate's own verdict.
- **static** (`--workflow …`): each registered sidecar must have exactly one
  writer step, the step must be advisory (`continue-on-error` + `if:
  always()`) and must catch the exit code errexit-safely (`set +e` …
  `status=$?`, or the K12/K13 `if … then status=0; else status=$?; fi`
  shape). Any `.exit` file written in the workflow must be registered in
  `SIDECARS`, so a new verdict cannot be added unmonitored.

When it goes red: fix the writer step's errexit shape or the missing step —
do **not** delete the registry entry. A genuinely retired sidecar is removed
from `SIDECARS` and from the workflow in the same commit; the static mode
fails a stale registry entry (`no-writer`).
## Workflow dosyası değiştiren PR'lar: `workflow` scope'u ne zaman gerekir

`.github/workflows/` altındaki bir dosyayı değiştirmek, taşıma yoluna göre
FARKLI yetki ister — bu ayrımı karıştırmak "yetki hatasını kod hatası sanma"
ile sonuçlanır:

| Yol | `workflow` scope'u | Ölçülen davranış |
|---|---|---|
| SSH anahtarıyla `git push` | **GEREKMEZ** | `gho_` token scope'ları `admin:public_key, gist, read:org, repo` (workflow YOK) iken `git push` workflow dosyasıyla başarılı |
| HTTPS + PAT/OAuth token ile `git push` | Gerekir | scope yoksa push reddedilir: `refusing to allow a Personal Access Token to create or update workflow` |
| GitHub API ile workflow dosyası yazma (`gh api .../contents/.github/workflows/...`, Contents/Git Data API, bot commit'leri) | Gerekir | `Resource not accessible by integration` / 403 |

Bu depo SSH ile push ediyor (`gh auth status` → `Git operations protocol:
ssh`), bu yüzden workflow değiştiren PR'lar normal akışla gönderilebilir.
Ama API üzerinden workflow dosyasına dokunan otomasyon (bot dalı + PR üreten
changelog/evidence işleri) için scope şart:

```bash
gh auth status                              # Scopes satırını kontrol et
gh auth refresh -h github.com -s workflow   # eksikse ekle (tarayıcı onayı ister)
```

- Classic PAT: `workflow` kutusu işaretli olmalı.
- Fine-grained PAT: "Workflows: Read and write".
- `main` branch-protected'tır: doğrudan push `GH006` ile döner; değişiklik
  dal + PR ile gönderilir.

Ölçülmüş örnek: `plist-p1` job'ını (P1 plist drift kapısı) ekleyen dilim
`verify.yml`'e dokunur; SSH ile push edildi, API tabanlı bir workflow yazımı
aynı token'la reddedilirdi.
