---
name: verify-chain
description: "Fail-closed delivery verification chain (K0-K17): layered artifact-integrity gates, single-entry-point --full command, pre-commit wiring, and CI integration for reproducible academic/research deliveries. Use when extending or auditing a multi-layer verification pipeline that must fail closed (no silent PASS), when adding a new K-layer gate, or when wiring verification into pre-commit + GitHub Actions."
metadata:
  openclaw:
    emoji: "⛓️"
    category: "research"
    subcategory: "reproducibility"
    keywords: ["verification chain", "fail-closed", "K-layer", "delivery integrity", "pre-commit", "GitHub Actions", "sidecar hashes", "artifact verification"]
    source: "leibniz2"
---

# Verify Chain (K0–K17)

## Overview

A **fail-closed verification chain** for research/delivery repositories: a
stacked set of layered gates (K0…K17) that each produce findings (P0/P1/INFO)
against artifact integrity. A single entry point (`verify_delivery.py --full`)
runs the whole chain in one command; individual layers run standalone via
flags. Every layer fails closed: any P0/P1 finding → non-zero exit → commit
and CI are blocked. No silent PASS, no advisory-only drift on hard gates.

This skill documents the design so the chain can be:
- **Extended**: add a new K-layer without breaking the existing ones
- **Audited**: verify a layer actually does what its label claims
- **Reused**: replicate the pattern in another repo/package

## When to Use

- Adding a new integrity gate (a sidecar hash, a schema check, a drift
  detector) to an existing verification pipeline.
- Auditing whether a layer truly fails closed (a finding that does not block
  is a bug).
- Wiring the chain into pre-commit hooks and CI jobs consistently.
- Explaining the architecture to a reviewer: what each layer checks, what
  tools it needs, and why each finding is P0/P1/INFO.

## Architecture

### Single entry point

```bash
python3 verify_delivery.py --full   # tüm katmanlar: K1-K14 + referans + Z3 + Lean
```

`--full` activates: `--check-references` (K6 online) + `--symbolic-proof`
(K8 Z3) + `--lean-proof` (K9 Lean) + `--check-lineage` + `--check-config-drift`
(K11) + `--check-repro-manifest` (K13) + `--check-cleanup` (K14) +
`--check-github-scripts` (K16).

- Exit codes: `0` = PASS, `1` = FAIL (≥1 P0/P1), `2` = usage/environment error.
- Stdlib-only Python (hashlib, zipfile, subprocess, tempfile; urllib for
  online checks). No `unzip`/`shasum`/`diff` binaries required.
- Optional tools degrade honestly: `pdfinfo` missing → page check skipped
  (NOT FAIL); `node` missing → K16 reports P0 (fail-closed).

### Priority levels

| Level | Meaning | Gate behavior |
|---|---|---|
| P0 | Integrity breaker (hash mismatch, resurrected file) | Blocks: exit 1 |
| P1 | Drift / inconsistency (stale record, missing expected file) | Blocks: exit 1 |
| INFO | Informational (out-of-scope file, advisory drift) | Reported, does NOT block |

### The K-layer map

| Layer | Checks | Flag / tool | In `--full`? |
|---|---|---|---|
| K0 | Stale zip scan outside canonical dir (recursive; P1) | always | yes |
| K1 | Outer zip SHA-256 sidecar (tamper) | always | yes |
| K2 | Folder checksum file (all files) | always | yes |
| K3 | Inner zip SHA-256 sidecar (tamper) | always | yes |
| K4 | Manifest file count + size + MD5 | always | yes |
| K5 | N scripts byte-for-byte vs frozen outputs | always | yes |
| K6 | PDF page count (pdfinfo, optional) + References count + online DOI/URL audit | `--check-references` | yes |
| K7 | Hygiene: secret/key + artifact scan | always | yes |
| K8 | Z3 symbolic proof (12 checks) | `--symbolic-proof` (z3-solver) | yes |
| K9 | Lean 4 reduct-invariance (meta-theorem) + 8-theorem core `lake build --wfail` (v4.14.0) | `--lean-proof` (lean+lake) | yes |
| K10 | Reproducibility manifest digest: every SHA-256 vs real file + config.combined_sha256 recompute + cli_overrides consistency | `--verify-manifest PATH` | separately |
| K11 | Config drift: gen_config.py --dry-run recomputes expected values vs committed config | `--check-config-drift` | yes |
| K12 | LaunchAgent plist template drift (0=GÜNCEL, 1=BAYAT, 2=şablon yok) | `--check-plist` (macOS) | no |
| K13 | Repro-manifest producer self-test (mock artifacts) | `--check-repro-manifest` | yes |
| K14 | Cleanup log: delete/move records vs filesystem (resurrect P1, moved-from P1, canonical hash P0) | `--check-cleanup` | yes |
| K15 | History sidecar integrity (history.jsonl ↔ .sha256) | `--check-history PATH` (local) | no |
| K16 | GitHub-script self-test: 15 scenarios, mock inputs, real Node, output matching | `--check-github-scripts` (node) | yes |
| K17 | Mirror sync drift (repo ↔ TCC-safe mirror; 0/1/2 exit contract) | `--check-mirror` (macOS) | no |

## Procedure

### Adding a new K-layer

1. **Pick the next K number** and update BOTH sources (single-source rule):
   - the module docstring layer table
   - the `LAYER_LABELS` dict + `_OPTIONAL_LAYERS`/`_CORE_LAYERS` wiring
2. **Implement `check_<layer>(...)`**: return `(ok: bool, detail: str)`,
   append findings via the shared `add(priority, id, label, issue, evidence)`
   helper. Use finding IDs like `K17-LINEAGE` (layer prefix, dash, check).
3. **Wire the flag**: `--check-<layer>` argparse option; add to `--full` if
   it should run in the single entry point (macOS-only / local-only layers
   stay out of `--full`, documented as such).
4. **Update `build_layers_summary`** automatically picks it up via
   `LAYER_LABELS` — verify the run summary shows PASS/FAIL/SKIP correctly.
5. **Test**: a unit test file (`test_<layer>.py`) covering the exit contract
   (P0/P1/INFO), positive and negative scenarios, plus a fail-closed proof
   (a tampered input MUST produce a finding).
6. **Wire pre-commit + CI** (see below).

### Wiring into pre-commit

Add a hook per gate (local repo, `language: system`, `always_run: true`,
`pass_filenames: false`, `verbose: true`). Existing hook inventory:

```
update-config                  # gen_config.py: sync config from package content
verify-delivery                # K1-K7 core (stdlib-only, fast)
check-action-pins              # action major version pinning (no downgrade)
check-python3-shell            # block shell cmds under shell: python3 {0}
check-absolute-paths           # block /Users/…, /home/… absolute paths
actionlint                     # workflow YAML lint (fail-closed)
verify-delivery-symbolic       # K8 Z3
verify-delivery-lean           # K9 Lean
check-plist-drift              # K12 plist gate unit tests (fake HOME)
check-repro-manifest           # K13 repro manifest + pattern coverage
check-pattern-consistency      # merge pattern ↔ ARTIFACT_JOBS
verify-delivery-github-scripts # K16 (node required)
verify-delivery-repro-manifest # K13 layer via verify_delivery.py
shellcheck-hooks               # POSIX/bash lint of hook scripts
check-changelog-sync           # git log ↔ docs changelog auto-sync
check-dryrun-summary           # publish_wrapper --dry-run-summary regression
check-colorize-rules           # dashboard colorizeLine regex regression
check-unit-tests               # battery of unit test files (venv python)
commit-msg-style               # commit-msg stage: title rules
```

Rules that keep the chain honest:

- **Only one writing hook** (`update-config` stages the synced config). All
  other gates are read-only: they verify, never modify.
- **Unit tests run in pre-commit** (`check-unit-tests` + per-gate hooks) so a
  broken gate blocks the commit, not the CI run.
- **Optional tools degrade honestly**: `node` absent → K16 P0 (fail-closed,
  no silent skip); venv python absent → tests SKIP (documented, CI still
  runs the full suite).

### Wiring into GitHub Actions (verify.yml)

- Single `verify` job runs `verify_delivery.py --full`; every optional layer
  either runs in `--full` or as a dedicated job.
- Dependent jobs use `needs:` (budget needs verify, reproducibility needs the
  gate jobs, manifest-comment needs reproducibility).
- All jobs have `timeout-minutes`; the workflow has `concurrency` group +
  `cancel-in-progress: true`; `permissions: contents: read` + minimal write
  scope.
- Required checks are enforced via branch protection; `status_checks.py --gh`
  verifies the workflow↔GitHub required-check list matches exactly.
- Action versions are pinned; `check-action-pins` + `action-runtimes` gate
  downgrades and Node 24 runtime.

## Checklist

- [ ] Every P0/P1 finding blocks (exit 1) — no silent PASS
- [ ] New layer: docstring table + LAYER_LABELS + flags + `--full` decision
      updated together
- [ ] Unit test with tamper-proof (tampered input MUST produce finding)
- [ ] Pre-commit hook wired (read-only unless update-config)
- [ ] CI job wired with `needs:` + timeout + permissions
- [ ] K10 manifest digest includes the new artifact (if it ships one)
- [ ] Run summary (consolidate_summary.py) shows the layer
- [ ] Dashboard /api/latest `layers` shows PASS/FAIL/SKIP

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Layer shows SKIP unexpectedly | Flag not passed / not in `--full` | Check `_OPTIONAL_LAYERS` wiring + `--full` activation |
| Unit test passes but pre-commit fails | Hook uses system python3 without deps | Prefer venv python in hook entry (repo `.venv_z3/bin/python`) |
| CI green but commit blocked | A pre-commit-only gate found drift | Run `pre-commit run --all-files` locally; fix the finding |
| INFO finding does not block | By design (advisory) | Verify the layer returns P0/P1 for real integrity breaks |
| K10 digest mismatch after adding artifact | Manifest not regenerated | Run `gen_repro_manifest.py`; K10 re-verifies |

## References

- Field implementation (leibniz2): `verify_delivery.py` (single entry point +
  K0-K17), `.pre-commit-config.yaml` (19 gates), `.github/workflows/verify.yml`
  (CI wiring), `gen_repro_manifest.py` (K10/K13), `sync_verify_mirror.sh` (K17),
  `github_scripts_battery.py` (K16), `consolidate_summary.py` (run summary).
- Related skill: `reproducible-pdf-build` (byte-determinism sidecar pattern
  that K6-DETERM/K5 build on).
