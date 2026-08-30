#!/usr/bin/env python3
import json
import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_delivery as vd


class SidecarGuaranteeTests(unittest.TestCase):
    def test_write_json_sidecar_writes_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "nested", "report.json")
            ok, _ = vd.write_json_sidecar(path, None, "not run")
            self.assertTrue(ok)
            with open(path, encoding="utf-8") as stream:
                report = json.load(stream)
            self.assertEqual(report, {"ok": False, "detail": "not run"})

    def test_lineage_writer_keeps_schema_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "lineage.json")
            ok, _ = vd.write_lineage_sidecar(path, None)
            self.assertTrue(ok)
            with open(path, encoding="utf-8") as stream:
                report = json.load(stream)
            self.assertFalse(report["ok"])
            self.assertEqual(report["generations"], [])


if __name__ == "__main__":
    unittest.main()
