"""Shared artifact coverage definitions."""

from __future__ import annotations


REPRODUCIBILITY_EXCLUDED = frozenset({
    "precommit-logs",
    "refs-trend",
    "override-trend",
    "precheck-report",
    "python3-shell",
    "plist-check",
    "mirror-check",
    "daemon-http",
    "audit-refs-trend",
    "reproducibility",
})

REPRODUCIBILITY_MERGED = frozenset({
    "verify-report",
    "budget-verify",
    "config",
    "k0-findings",
    "lineage-findings",
    "klayers",
    "unit-tests",
    "refs-online",
    "run-history",
    "budget",
    "reports",
    "config-drift",
    "repack-verify",
    "action-runtimes",
    "changelog-drift",
    "ci-simulate",
})

DOC_ONLY_ADVISORY = frozenset({
    "audit-live-ci",
    "pattern-drift",
    "preview-reload-smoke",
})
