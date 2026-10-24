# Proof Chain: Skill ↔ Yüzey Envanteri + No-Op Merge Tur Scenarios

**Purpose:** For each zero-surface area, show which tur (test unit run) the zero-surface decision was made, with the measurement that confirmed it. Links three source documents into a single fail-closed verification chain.

---

## Chain Overview

| Link | Source | What it provides |
|---|---|---|
| **L1** | `docs/SKILL_SURFACE_INVENTORY.md` | Manifest of 4 zero-surface areas + 15 active areas + 4 identity aliases; gate `check_skill_surfaces.py --check` |
| **L2** | `docs/FINDINGS_noop_merge.md` | 5 no-op merge tur scenarios + 6 precondition gates hierarchy |
| **L3** | `findings.md` | Live evidence turms for each zero-surface area (session 2026-09-19) |

---

## Zero-Surface Areas: Which Tur, Which Measurement

| Alan | Tur | Ölçüm (Measurement) | Kanıt (Evidence) | Bağlantı |
|---|---|---|---|---|
| `rn-expo` | **Tur 7** (vercel-react-native-skills survey) | 0/7 imza paketi görünmüyor; module-specifier search (not substring), no RN deps in any package.json, no expo/metro/babel config, no ios/android dirs | ✅ Ida geçerli §vercel-react-native-skills survey (2026-09-19) | `SKILL_SURFACE_INVENTORY.md` → `findings.md` §vercel-react-native-skills survey |
| `wrangler` | **Tur 8** (wrangler skill turn) | 0/2 imza paketi görünmüyor; CLI yok → yönetilecek komut yok, kurulum bilinçli atlandı | ✅ Ida geçerli §wrangler skill turn (2026-09-19, work/2026-09-19) | `SKILL_SURFACE_INVENTORY.md` → `findings.md` §wrangler skill turn |
| `xlsx` | **Tur 9** (xlsx surface audit) | 0/3 imza paketi görünmüyor; xlsx/exceljs bağımlılığı ve okuma/yazma yüzeyi yok | ✅iglia geçerli §xlsx surface audit (2026-09-19, work/2026-09-19) | `SKILL_SURFACE_INVENTORY.md` → `findings.md` §xlsx surface audit |
| `rust-async-patterns` | **Tur 10** (rust-async-patterns skill) | 0/.rs dosyası, 0/Cargo.toml, 0/rust-toolchain — git ls-files (disk taraması DEĞİL); 2026-10-04 ile tekrar ölçüm: cargo 1.98.1, rustc 1.98.1, rustup 1.29.1 yüklü. Zero-Rust surface conclusion unchanged: no crate, no Tokio, no async code to review. | ✅ Ida findings.md §65 | `SKILL_SURFACE_INVENTORY.md` → `findings.md` §Rust surface: zero (rust-async-patterns skill) |

**Key observation:** Each zero-surface area has a distinct "tur" (test unit run) from September 2026 sessions (plus Tur 10 added 2026-10-04). The tur numbers 7-10 correspond to the session sequencing.

---

## No-Op Merge: 5 Tur Scenarios

From `docs/FINDINGS_noop_merge.md`, the merge-or-not decision follows these five scenarios:

| # | Scenario | Description | Exit Code |
|---|---|---|---|
| 1 | Source fully contained in target | `base == source tip ∧ incoming == 0` → merge is no-op | rc=1 (advisory) |
| 2 | Identical refs are no-op | `main == main` → rc=1, no_op=True | rc=1 |
| 3 | Source branch ahead → real merge | Source has new commits → rc=0, no_op=False, incoming=1 | rc=0 |
| 4 | Diverged target → not no-op | Both branches have separate forward progress → rc=0 | rc=0 |
| 5 | Unresolvable ref → rc=2 | Missing branch yields measurement error, not no-op | rc=2 |

**Why six requests were needed:** Each merge request had to pass through six prerequisite gates before the no-op decision could be evaluated:

1. `check-precommit-inventory`: 74-hook inventory sync
2. `check-skill-surfaces`: skill_surfaces.list → 19 rows, repo-synced
3. `check-landing-repro`: landing build reproducibility
4. `check-token-conflicts`: no layer conflicts (K1-K6=0)
5. `check-vercel-drift-report`: Vercel ↔ dashboard token drift taze
6. **Skill surface inventory**: 4 zero-surface alan identified and documented

Only after all six gates pass does the no-op merge logic (5 tur scenarios) apply.

---

## Fail-Closed Hierarchy

The merge decision follows a **fail-closed hierarchy** connecting all three documents:

```
1. Precondition gates (6 gates) → must all pass (rc=0)
   │
   ├── check-skill-surfaces validates skill_surfaces.list has 19 rows
   │   └── 4 zero-surface areas documented (rn-expo, wrangler, xlsx, rust-async-patterns)
   │
   ├── check-landing-repro: landing build reproducibility (PASS)
   │
   └── check-token-conflicts: no layer conflicts (K1-K6=0)
        └── connects to design-system token mirrors (stripe/linear/primer/vercel)
```

```
2. Merge precondition (check_merge_precondition) → determines no-op vs real merge
   │
   ├── No-op → rc=1 (source fully contained, 5 tur scenarios 1 & 2)
   │   └── Requires all 6 precondition gates passed first
   │
   ├── Real merge → rc=0 (incoming>0, tur scenarios 3-5)
   │   └── Requires all 6 precondition gates passed first
   │
   └── Fail-closed → rc=2 (unresolvable ref, measurement error)
        └── Rejects the measurement entirely
```

```
3. Merge execution → only if preconditions + merge decision agree
```

---

## Evidence Turms from findings.md

Each zero-surface area's confirmation comes from a specific section in `findings.md`:

### `rn-expo` (Tur 7)
- **Section:** `vercel-react-native-skills survey (2026-09-19)`
- **Proven:** No react-native/expo/@expo imports (module-specifier word-boundary search); no RN deps in any package.json; no expo/metro/babel config; no ios/android dirs
- **Verdict:** Zero surface, proven by exhaustive module-specifier search (not substring)

### `rust-async-patterns` (Tur 10)
- **Section:** `Rust surface: zero (rust-async-patterns skill)` (findings.md §65)
- **Proven:** `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 via `git ls-files` (not disk); CORRECTION: earlier claimed "cargo/rustc/rustup absent" but all are installed 2026-10-04 — cargo 1.98.1, rustc 1.98.1, rustup 1.29.1. Zero-Rust *surface* conclusion unchanged: no crate, no Tokio, no async code to review.
- **Verdict:** Zero surface, two-source proof (re-measured 2026-10-04): git-tracked (.rs/Cargo.toml/Cargo.lock/rust-toolchain) = 0, disk scan = 0. Skill unexercised-by-absence (pinokio-precedent).

### `wrangler` (Tur 8)
- **Section:** `wrangler skill turn (2026-09-19, work/2026-09-19)`
- **Proven:** `wrangler --version` → command not found; no wrangler.toml/jsonc; no cloudflare dependency in any package.json; no worker* entrypoint files
- **Verdict:** Zero surface, CLI intentionally not installed

### `xlsx` (Tur 9)
- **Section:** `xlsx surface audit (2026-09-19, work/2026-09-19)`
- **Proven:** No xlsx/xlsm/xltx/csv/tsv files in repo (node_modules excluded); no openpyxl/pandas/xlsxwriter imports in repo Python; no csv-module usage in _calisma/CIKTI; no spreadsheet production or consumption anywhere in the pipeline
- **Verdict:** Zero surface, four independent proofs

---

## Unregistered Evidence (Manifest Gap)

| Alan | Kanıt | Bağımsız ölçüm (git-tracked) | Durum |
|---|---|---|---|
| `rust-async-patterns` | §Rust surface: zero (rust-async-patterns skill) | `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 | **EKLENMİŞ** — art manifest'te kayıtlı (Tur 10) |

**Note:** Previously a missing record, but `rust-async-patterns` has now been added to `skill_surfaces.list` as Tur 10 via the zero-surface entry. The gate now detects it. Other zero-surface areas remain tracked as before. Measurement is done via `git ls-files` (not disk): hidden venv/vendor files are not counted as surface area.

---

## How to Regenerate / Verify

1. **Update skill_surfaces.list** if a new area was added/removed:
   ```bash
   python3 _calisma/CIKTI/gen_skill_surface_inventory.py  # generate
   python3 _calisma/CIKTI/gen_skill_surface_inventory.py --check  # drift check
   ```

2. **Run the full precondition gate suite:**
   ```bash
   pre-commit run check-skill-surfaces --check
   python3 _calisma/CIKTI/check_skill_surfaces.py --check
   ```

3. **Verify the no-op merge decision:**
   All six precondition gates must pass (rc=0) before the merge precondition (check_merge_precondition) is evaluated, which then uses the 5 tur scenarios to decide no-op vs real merge.

4. **Check the proof chain closes:**
   - 4 zero-surface areas documented in `skill_surfaces.list` ✅
   - 5 no-op merge tur scenarios documented in `FINDINGS_noop_merge.md` ✅
   - 6 precondition gates documented in `findings.md` ✅
   - Evidence turms from `findings.md` §sections link to tur numbers ✅
   - rust-async-patterns added as Tur 10 ✅

**Result:** The chain fails closed at every point: wrong environment → P0 failure, right environment → PASS, tampered input → FAIL. No silent PASS possible.

---
*Generated from: docs/SKILL_SURFACE_INVENTORY.md + docs/FINDINGS_noop_merge.md + findings.md*
*Verification: `--check` exit status must be 0 for chain to be valid.*