#!/usr/bin/env python3
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SYNC = (HERE / "sync_verify_mirror.sh").read_text(encoding="utf-8")
VERIFY = (HERE / "verify_delivery.py").read_text(encoding="utf-8")


class K9LeanFileSourceSyncTests(unittest.TestCase):
    def test_mirror_has_single_discovery_function_for_lean_files(self):
        self.assertIn("def lean_project_files(project_dir):", VERIFY)
        self.assertIn("lean_project_files() {", SYNC)
        self.assertIn("--sync-lean-files", SYNC)
        self.assertIn("sync_lean_files.py", SYNC)
        self.assertIn('"ReductInvariance.lean|ReductInvariance.lean"', SYNC)

    def test_sync_mode_is_exposed_and_rebuilds_block(self):
        self.assertIn("--sync-lean-files", SYNC)
        self.assertIn("sync_lean_files() {", SYNC)
        self.assertIn("LEAN_FILES=(", SYNC)

    def test_both_contracts_exclude_build_metadata(self):
        self.assertIn('d != ".lake"', VERIFY)
        self.assertIn('! -name "lake-manifest.json"', SYNC)
        self.assertIn('! -path "$LEAN_SRC/.lake/*"', SYNC)


if __name__ == "__main__":
    unittest.main()
