#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_atomic_write_guard.py — repo-wide guard for preview-served files.

Preview-served files (dashboard reads them) are subject to torn-read races
if written with plain `open(path, "w")` + write.  The safe path is the
same-directory `mkstemp` + `os.replace` helper (`_write_atomic`).

This guard fails when any production module that writes a preview-served
file uses `open(..., "w")` directly instead of delegating to its
`_write_atomic` helper.  It is intentionally narrow:

* Only production files (not test_*) are scanned.
* Only writes whose enclosing scope mentions a preview-served indicator are
  considered.  A helper that writes `manifest.json` or `lineage_findings.json`
  via `open("w")` is not flagged.
* Writes inside a function named `_write_atomic` are allowed (the helper
  itself uses `os.fdopen(fd, "w")`).
"""

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CIKTI = REPO_ROOT / "_calisma" / "CIKTI"

# File-name / variable substrings that identify a preview-served destination.
# Keep in sync with preview_server.py's served paths and verify_delivery's
# preview sidecars.
PREVIEW_FILE_INDICATORS = (
    "history.jsonl",
    "history.jsonl.sha256",
    "refs-trend.json",
    "refs-trend.md",
    "override-trend.json",
    "override-trend.md",
    "klayers.json",
    "OVERRIDE_RAPORU.json",
)
PREVIEW_VAR_INDICATORS = (
    "HISTORY_PATH",
    "REFS_TREND_PATH",
    "OVERRIDE_TREND_PATH",
    "RUNS_DIR",
    "klayers_out",
    "history_out",
)
PREVIEW_INDICATORS = PREVIEW_FILE_INDICATORS + PREVIEW_VAR_INDICATORS
# Functions known to write preview-served files even when the open() arg is
# a generic `path` variable (taint would be needed otherwise).
PREVIEW_WRITER_FUNCS = frozenset({
    "persist_history",
    "persist_run_log",
    "_write_override_report",
    "load_cached_latest",  # not a writer, but keep set explicit
})

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".venv_z3",
    "__pycache__",
    ".freebuff",
    "node_modules",
    ".agents",
    ".build",
    ".lake",
    "slides_z3",
    "_calisma/CIKTI/.build",
}

# Production files that are allowed to use open("w") for non-preview writes
# are still scanned — we only flag when the enclosing scope is preview-relevant.


def _is_write_mode(call: ast.Call) -> bool:
    """Return True if `open(...)` call opens for writing (mode contains 'w')."""
    # positional: open(path, "w") or open(path, "w", ...)
    if len(call.args) >= 2:
        mode_arg = call.args[1]
        if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
            if "w" in mode_arg.value:
                return True
    # keyword: open(path, mode="w")
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            if "w" in kw.value.value:
                return True
    # No explicit mode -> read, not a truncating write.
    return False


def _is_open_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(getattr(node, "func", None), ast.Name)
        and getattr(node.func, "id", None) == "open"
    )


class _Visitor(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self.violations: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node):
        self.stack.append(node)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.stack.append(node)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node):
        if _is_open_call(node) and _is_write_mode(node):
            # Allow the helper itself.
            if self.stack and self.stack[-1].name == "_write_atomic":
                pass
            else:
                # Preview relevance is determined from the open() call's own
                # argument source, not the whole enclosing function.  The old
                # scope-based check flagged unrelated sidecars (config_out,
                # k0_out, ...) merely because main() also mentions
                # history.jsonl elsewhere.
                try:
                    seg = ast.get_source_segment(self.source, node) or ""
                except Exception:
                    seg = ""
                is_preview = any(ind in seg for ind in PREVIEW_INDICATORS)
                # Generic `open(path, "w")` inside a known preview writer
                # (e.g. persist_history) is also a violation — taint the
                # generic path via the function name.
                if not is_preview and self.stack and self.stack[-1].name in PREVIEW_WRITER_FUNCS:
                    is_preview = True
                    seg = seg or "open(path, 'w')"
                if is_preview:
                    try:
                        disp = ast.get_source_segment(self.source, node) or "open(...)"
                    except Exception:
                        disp = "open(...)"
                    self.violations.append((getattr(node, "lineno", 0), disp.strip()))
        self.generic_visit(node)


def _collect_production_py_files():
    out = []
    for p in REPO_ROOT.rglob("*.py"):
        # Skip excluded directories
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        # Skip tests and this guard itself
        if p.name.startswith("test_") or p.name == "test_atomic_write_guard.py":
            # Allow scanning production files that happen to be named test_? No,
            # test files intentionally use open("w") for fixtures — exclude.
            continue
        # Only consider files that are part of the repo's preview delivery
        # surface: _calisma/** and top-level scripts.  This keeps the guard
        # fast and avoids scanning .venv or unrelated tooling.
        try:
            rel = p.relative_to(REPO_ROOT)
        except ValueError:
            continue
        # Limit to _calisma and repo-root python files (repack_delivery, etc.)
        if not (str(rel).startswith("_calisma/") or "/" not in str(rel)):
            continue
        out.append(p)
    return sorted(out)


def find_violations():
    violations = []
    for py in _collect_production_py_files():
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Quick pre-filter: file must mention a preview indicator at all.
        if not any(ind in text for ind in PREVIEW_INDICATORS):
            continue
        # Also skip files that don't contain a write open at all.
        if 'open(' not in text or '"w"' not in text and "'w'" not in text:
            # Still need to handle 'w' via keyword or "wb" etc. — rough filter
            # is not critical; let AST do the precise check.  Keep file.
            pass
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue
        v = _Visitor(text)
        v.visit(tree)
        for lineno, seg in v.violations:
            violations.append(f"{py.relative_to(REPO_ROOT)}:{lineno}: {seg}")
        # Also flag fixed ".tmp" concatenation for preview paths (stale pattern
        # that reintroduces the race even when _write_atomic exists).
        for ind in PREVIEW_INDICATORS:
            # e.g. HISTORY_PATH + ".tmp"  or  path + ".tmp" inside a preview scope
            if f'{ind} + ".tmp"' in text or f"{ind} + '.tmp'" in text or f'{ind} + \".tmp\"' in text:
                violations.append(f"{py.relative_to(REPO_ROOT)}: fixed .tmp with {ind}")
    return sorted(violations)


class AtomicWriteGuardTests(unittest.TestCase):
    def test_no_direct_open_w_for_preview_served_files(self):
        violations = find_violations()
        self.assertEqual(
            violations,
            [],
            "preview-served files must be written via _write_atomic (same-dir mkstemp + os.replace), "
            "not open(path, 'w') — violations:\n" + "\n".join(violations),
        )

    def test_guard_catches_direct_write(self):
        """Self-test: the guard must flag a direct open in a preview scope."""
        src = '''
def persist_history(rec):
    HISTORY_PATH = "history.jsonl"
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write("hi")

def _write_atomic(path, data):
    import tempfile, os
    fd, tmp = tempfile.mkstemp(dir=".", prefix="x.tmp.")
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.replace(tmp, path)

def persist_ok(rec):
    HISTORY_PATH = "history.jsonl"
    _write_atomic(HISTORY_PATH, "hi")
'''
        tree = ast.parse(src)
        v = _Visitor(src)
        v.visit(tree)
        self.assertEqual(len(v.violations), 1)
        self.assertIn("HISTORY_PATH", v.violations[0][1])

    def test_guard_allows_non_preview_writes(self):
        """open('w') for manifest/lineage must not be flagged."""
        src = '''
def write_lineage_sidecar(path, report):
    with open(path, "w", encoding="utf-8") as f:
        import json; json.dump(report, f)

def tamper(m, out):
    import os, json
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as mf:
        json.dump(m, mf)
'''
        tree = ast.parse(src)
        v = _Visitor(tree)
        v.visit(tree)
        self.assertEqual(v.violations, [])


if __name__ == "__main__":
    unittest.main()
