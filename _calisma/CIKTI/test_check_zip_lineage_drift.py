"""test_check_zip_lineage_drift.py — K14 commit-time drift gate regression tests.

Conventions follow the repo's check_*.py suites (stdlib unittest, tempdirs).
Covers: pass, lineage-current drift (P0), canonical drift (P0), UNVERIFIED
missing live files, and the live repo contract (currently drifted by design
until the registry resync lands).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_zip_lineage_drift as gate  # noqa: E402

ZIP = "TESLIM_KLASOR_V5_2026-08-17.zip"


def _mk_repo(tmp: str, zip_bytes: bytes, lineage_cur: str, canon: list) -> str:
    """Build a minimal fake repo root with CIKTI/ records + zips."""
    cikti = os.path.join(tmp, "_calisma", "CIKTI")
    os.makedirs(cikti, exist_ok=True)
    with open(os.path.join(cikti, ZIP), "wb") as f:
        f.write(zip_bytes)
    with open(os.path.join(cikti, "zip_lineage.json"), "w", encoding="utf-8") as f:
        json.dump({
            "path_in_repo": f"_calisma/CIKTI/{ZIP}",
            "generations": [
                {"note": "old", "hash": "0" * 64, "commit": None, "current": False},
                {"note": "gen", "hash": lineage_cur, "commit": None, "current": True},
            ],
        }, f)
    with open(os.path.join(cikti, "cleanup_log.json"), "w", encoding="utf-8") as f:
        json.dump({"canonical": canon}, f)
    return tmp


class TestLineageCurrent(unittest.TestCase):
    def test_pass_when_current_hash_matches_live_zip(self):
        data = b"zip-bytes"
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, data, h, [])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)

    def test_p0_when_current_hash_differs_from_live_zip(self):
        import hashlib
        h = hashlib.sha256(b"stale-generation").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"live-bytes", h, [])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 1)

    def test_p0_when_no_current_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", "0" * 64, [])
            with open(os.path.join(tmp, "_calisma", "CIKTI", "zip_lineage.json"), "w") as f:
                json.dump({"path_in_repo": f"_calisma/CIKTI/{ZIP}",
                           "generations": [{"note": "x", "hash": "0" * 64,
                                            "commit": None, "current": False}]}, f)
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 1)

    def test_unverified_when_live_zip_absent(self):
        import hashlib
        h = hashlib.sha256(b"anything").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", h, [])
            os.remove(os.path.join(tmp, "_calisma", "CIKTI", ZIP))
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)  # UNVERIFIED — blocks nothing (CI parity)


class TestCleanupCanonical(unittest.TestCase):
    def test_pass_when_canonical_hash_matches(self):
        data = b"canonical-bytes"
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        rec = {"path": f"_calisma/CIKTI/{ZIP}", "hash": h, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, data, h, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(0, rc)

    def test_p0_when_canonical_hash_differs(self):
        import hashlib
        live = hashlib.sha256(b"live-bytes").hexdigest()
        recorded = hashlib.sha256(b"recorded-elsewhere").hexdigest()
        rec = {"path": f"_calisma/CIKTI/{ZIP}", "hash": recorded, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"live-bytes", live, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(1, rc)

    def test_unverified_when_canonical_file_absent(self):
        import hashlib
        live = hashlib.sha256(b"zip").hexdigest()  # lineage must match live zip
        h = hashlib.sha256(b"x").hexdigest()       # canonical rec: file absent
        rec = {"path": "_calisma/CIKTI/does_not_exist.zip", "hash": h, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", live, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(0, rc)


class TestMissingRegistries(unittest.TestCase):
    def test_missing_registries_are_info_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)


class TestLiveDriftContract(unittest.TestCase):
    def test_gate_catches_the_real_k14_drift(self):
        """Live contract: the real repo currently has stale registry hashes.

        Until the registry resync lands, the gate MUST fail here (exit 1) —
        this is the regression pin proving the gate catches the exact P0
        class that broke CI-SIMULATE. Flip this expectation when the resync
        commit lands.
        """
        rc = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_zip_lineage_drift.py")],
            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 1,
                         f"expected drift to be caught (exit 1), got {rc.returncode}:\n{rc.stderr}")
        self.assertIn("uyuşmuyor", rc.stderr)


if __name__ == "__main__":
    unittest.main()
