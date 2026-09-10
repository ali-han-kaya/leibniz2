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
