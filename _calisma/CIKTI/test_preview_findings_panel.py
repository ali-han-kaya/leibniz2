#!/usr/bin/env python3
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preview_server as ps


class K12FindingsPanelContractTests(unittest.TestCase):
    def test_k12_p0_survives_finalize_and_snapshot(self):
        old = dict(ps.LATEST)
        try:
            ps.LATEST = dict(old)
            ps._finalize_run(
                '{"verdict":"FAIL","counts":{"P0":1,"P1":0},'
                '"findings":[{"id":"K12-PLIST-EXTRA","priority":"P0",'
                '"label":"extra plist","message":"extra profile"}]}',
                "", 1, 0.01, None, HERE)
            finding = next(f for f in ps.snapshot_dict()["findings"]
                           if f.get("id") == "K12-PLIST-EXTRA")
            self.assertEqual(finding["priority"], "P0")
            self.assertEqual(finding["message"], "extra profile")
        finally:
            ps.LATEST = old

    def test_dashboard_panel_already_renders_p0_by_id(self):
        with open(os.path.join(HERE, "preview.html"), encoding="utf-8") as stream:
            html = stream.read()
        self.assertIn('id="findings-panel"', html)
        self.assertIn('f.id || f.label', html)
        self.assertIn('f.priority === "P0"', html)


if __name__ == "__main__":
    unittest.main()
