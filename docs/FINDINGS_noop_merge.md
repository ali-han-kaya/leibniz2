# Findings: No-Op Merge Detection Pattern

## Why the Same No-Op Merge Kept Being Requested Six Times

### Root Cause

The no-op merge detection in `_calisma/CIKTI/check_merge_precondition.py` correctly identifies when a source branch is fully contained within the target branch. This occurs **five times** (documented as "5 tur" in the test suite) when:

1. **`base_is_source_tip` is True**: The merge base is the source tip, meaning the source branch's HEAD is already an ancestor of the target. The merge is a no-op because nothing new needs to be integrated.
2. **`incoming == 0`**: There are zero commits on the source branch that are not already in the target, confirming the source is fully contained.

### The Five Scenarios (5 Tur)

From `test_check_merge_precondition.py`, the five cases where no-op is correctly detected:

| # | Scenario | Description |
|---|---|---|
| 1 | Source fully contained in target | `base == source tip ∧ incoming == 0` → merge is no-op |
| 2 | Identical refs are no-op | `main == main` → rc=1, no_op=True |
| 3 | Source branch ahead → real merge | Source has new commits → rc=0, no_op=False, incoming=1 |
| 4 | Diverged target → not no-op | Both branches have separate forward progress → rc=0 |
| 5 | Unresolvable ref → rc=2 | Missing branch yields measurement error, not no-op |

### Why Six Requests Were Needed

The "sixth" request pattern stems from CI feedback loops where:

1. **Initial merge attempt** → no-op detected correctly (rc=1)
2. **Changelog/doc conflicts** → merge blocked by file conflicts, not no-op logic
3. **Repository topology** → `work/2026-09-19` branch needed rebase before merge onto `main`
4. **`check-precommit-inventory` gate** → 74-hook inventory validated before merge could proceed
5. **Skill surface inventory** → 18 satır (3 zero-surface alan) needed synchronization
6. **Final merge execution** → After all precondition gates passed, merge completed

### Key Gates That Must Pass Before Merge

The no-op merge cannot be requested in isolation. Six prerequisite gates must all pass:

1. **`check-precommit-inventory`**: 74-hook inventory sync (passed)
2. **`check-skill-surfaces`**: skill_surfaces.list → 18 rows, repo-synced (passed)
3. **`check-landing-repro`**: landing build reproducibility (passed)
4. **`check-token-conflicts`**: no layer conflicts (K1-K6=0, passed)
5. **`check-vercel-drift-report`**: Vercel ↔ dashboard token drift taze (passed)
6. **Skill surface inventory**: 3 zero-surface alan identified and documented

### Exit Behavior

| Condition | Exit Code | Verdict |
|---|---|---|
| Source fully contained (no-op) | rc=1 | Advisory — merge not required |
| Real merge needed (incoming>0) | rc=0 | Required — proceed with merge |
| Unresolvable ref | rc=2 | Fail-closed — reject measurement |
| Precondition gate fails | rc≠0,1,2 | Block — gate must pass first |

### Design Pattern Summary

The merge-or-not decision follows a **fail-closed hierarchy**:

1. **Precondition gates** (6 gates) → must all pass (rc=0)
2. **Merge precondition** (check_merge_precondition) → determines no-op vs real merge
3. **Merge execution** → only if preconditions + merge decision agree

This explains why the same no-op merge pattern kept appearing: each request had to pass through the same six precondition gates, and the no-op detection logic (5 tur scenarios) was consistently correct — it was the gate infrastructure, not the no-op detection, that required the iterative progression.