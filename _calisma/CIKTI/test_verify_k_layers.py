#!/usr/bin/env python3
"""Focused contracts for the extracted K0-K7 verifier seams."""
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


class TestK0Seam(unittest.TestCase):
    def test_check_k0_returns_records_and_writes_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = pathlib.Path(tmp) / "CIKTI"
            canonical.mkdir()
            stale = pathlib.Path(tmp) / "stale.zip"
            stale.write_bytes(b"stale")
            sidecar = pathlib.Path(tmp) / "k0.json"
            findings = []

            records = vd.check_k0(
                str(canonical),
                types.SimpleNamespace(
                    k0_toolkit_tolerant=False,
                    k0_out=str(sidecar),
                    json=True,
                ),
                lambda *finding: findings.append(finding),
            )

            self.assertEqual([record["rel"] for record in records], ["stale.zip"])
            self.assertEqual(findings[0][0:2], ("P1", "K0-STALE"))
            self.assertEqual(json.loads(sidecar.read_text())["count"], 1)


if __name__ == "__main__":
    unittest.main()
