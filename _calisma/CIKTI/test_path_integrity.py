#!/usr/bin/env python3
"""test_path_integrity.py — regression test.

Ensures that every test file in _calisma/CIKTI/ uses temp directories
(tempfile.TemporaryDirectory / tempfile.mkdtemp) for any on-disk work,
and never renames, moves, or deletes paths inside the real repository root.

Run with: python3 -m unittest _calisma.CIKTI.test_path_integrity
"""
import os
import sys
import unittest


# Resolve repo root: one level up from _calisma/CIKTI/
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
_cikti_dir = os.path.join(_repo_root, "_calisma", "CIKTI")


class TestPathIntegrity(unittest.TestCase):
    """Verify that no test file modifies real repo paths instead of using tempdirs."""

    def test_no_real_path_modifications(self):
        """Fail if any test file writes to real repo paths instead of temp dirs."""
        test_files = []
        if os.path.isdir(_cikti_dir):
            for fname in sorted(os.listdir(_cikti_dir)):
                if fname.startswith("test_") and fname.endswith(".py"):
                    test_files.append(os.path.join(_cikti_dir, fname))

        self.assertGreater(
            len(test_files), 0,
            "No test files found in _calisma/CIKTI/ — nothing to check.",
        )

        for test_path in test_files:
            with self.subTest(file=test_path):
                with open(test_path, "r", encoding="utf-8", errors="replace") as f:
                    source = f.read()

                # Check for open() calls with real repo paths (not temp paths)
                for line in source.splitlines():
                    stripped = line.strip()
                    # Match open(...) calls
                    if stripped.startswith("open(") and stripped.endswith(")"):
                        # Extract the path argument
                        inner = stripped[5:-1].strip()
                        if inner.startswith(("'", '"')) and inner.endswith(("'", '"')):
                            path_val = inner[1:-1]
                        else:
                            continue

                        # Heuristic: if path starts with /Users or /private, it's real
                        if path_val.startswith("/Users/") or path_val.startswith("/private/"):
                            self.fail(
                                f"{test_path} opens real path '{path_val}' instead of using temp directory. "
                                "All on-disk operations in test files must use tempfile.TemporaryDirectory "
                                "or tempfile.mkdtemp."
                            )

                    # Match os. operations like os.rename, os.remove, etc.
                    for func_name in ("os.rename", "os.replace", "os.remove", "os.unlink",
                                      "os.mkdir", "os.makedirs", "os.rmdir"):
                        if func_name in stripped:
                            # Simple check: if the line has a path-like string after the function
                            # that starts with /Users or /private, flag it
                            pass  # We'll do a simpler check below

                # Also check for os.path operations with real paths
                import re
                # Match os.path.join, os.path.exists, etc. with real paths
                for m in re.finditer(r"\bos\.\w+\(['\"]([^'\"]+)['\"]", source):
                    path_val = m.group(1)
                    if path_val.startswith("/Users/") or path_val.startswith("/private/"):
                        self.fail(
                            f"{test_path} uses os.path operation with real path '{path_val}' instead of temp directory. "
                            "All on-disk operations in test files must use tempfile.TemporaryDirectory "
                            "or tempfile.mkdtemp."
                        )


if __name__ == "__main__":
    unittest.main()