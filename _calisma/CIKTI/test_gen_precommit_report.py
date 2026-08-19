#!/usr/bin/env python3
"""test_gen_precommit_report.py — gen_precommit_report.py regresyon kapısı.

build_data() pre-commit verbose çıktısından hook sonuçları (Passed/Failed),
update-config durumu/çıktısı ve P0/P1 bulgularını tek kaynak bir sözlüğe
toplar; main() bu sözlükten hem PRECOMMIT_RAPORU.md hem makine-okunur
PRECOMMIT_RAPORU.json yazar. stdlib unittest — ek bağımlılık yok.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import gen_precommit_report as gpr  # noqa: E402

LOG_PASS = """\
Sync config from package content (gen_config.py).........................Passed
- hook id: update-config
- duration: 0.13s
Verify Stoic-Hume V5 delivery (fail-closed)..............................Passed
- hook id: verify-delivery
- duration: 0.23s
Verify formal core symbolically (Z3, fail-closed)........................Passed
- hook id: verify-delivery-symbolic
- duration: 0.12s
Verify Lean 4 reduct-invariance (fail-closed)............................Passed
- hook id: verify-delivery-lean
- duration: 2.08s
"""

LOG_FAIL = """\
Sync config from package content (gen_config.py).........................Failed
- hook id: update-config
- duration: 0.13s
config paket içeriğiyle senkronlanamadı: expected_pages 33 != 34
Verify Stoic-Hume V5 delivery (fail-closed)..............................Failed
- hook id: verify-delivery
- duration: 0.23s
[P1] MANIFEST MD5 uyuşmazlığı: dosya X
"""


class TestBuildData(unittest.TestCase):
    def test_pass_hooks(self):
        data = gpr.build_data(LOG_PASS, 0)
        self.assertEqual(data["verdict"], "PASS")
        self.assertEqual(len(data["hooks"]), 4)
        self.assertTrue(all(h["status"] == "Passed" for h in data["hooks"]))
        self.assertEqual(data["counts"], {"hooks": 4, "passed": 4,
                                          "failed": 0, "p0": 0, "p1": 0})
        self.assertEqual(data["update_config"]["status"], "Passed")
        self.assertEqual(data["update_config"]["output"], [])
        self.assertEqual(data["findings"], [])

    def test_fail_hooks_and_findings(self):
        data = gpr.build_data(LOG_FAIL, 1)
        self.assertEqual(data["verdict"], "FAIL")
        statuses = {h["name"]: h["status"] for h in data["hooks"]}
        self.assertEqual(statuses.get(
            "Sync config from package content (gen_config.py)"), "Failed")
        self.assertEqual(statuses.get(
            "Verify Stoic-Hume V5 delivery (fail-closed)"), "Failed")
        self.assertEqual(data["counts"]["failed"], 2)
        self.assertEqual(data["counts"]["p1"], 2)  # [P1] satırı + update-config FAIL

        # [P1] satırı doğrudan findings'e girer.
        prios = [f["priority"] for f in data["findings"]]
        self.assertEqual(prios.count("P1"), 2)
        msgs = " ".join(f["message"] for f in data["findings"])
        self.assertIn("MANIFEST MD5 uyuşmazlığı", msgs)
        self.assertIn("update-config FAIL", msgs)

    def test_update_config_output_captured(self):
        data = gpr.build_data(LOG_FAIL, 1)
        out = data["update_config"]["output"]
        self.assertIn("config paket içeriğiyle senkronlanamadı: "
                      "expected_pages 33 != 34", out)
        # hook id / duration satırları çıktıdan filtrelenir.
        self.assertFalse(any(s.startswith("- hook id") for s in out))


class TestMain(unittest.TestCase):
    def test_writes_md_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "logs"))
            with open(os.path.join(d, "logs", "precommit.log"),
                      "w", encoding="utf-8") as f:
                f.write(LOG_PASS)
            with open(os.path.join(d, "logs", "precommit.exit"),
                      "w", encoding="utf-8") as f:
                f.write("0")
            cwd = os.getcwd()
            try:
                os.chdir(d)
                gpr.main()
            finally:
                os.chdir(cwd)

            md = pathlib.Path(d, "logs", "PRECOMMIT_RAPORU.md").read_text(
                encoding="utf-8")
            js = pathlib.Path(d, "logs", "PRECOMMIT_RAPORU.json").read_text(
                encoding="utf-8")
        self.assertIn("## Hook sonuçları", md)
        self.assertIn("Verify Stoic-Hume V5 delivery", md)
        data = json.loads(js)
        self.assertEqual(data["counts"]["hooks"], 4)
        self.assertEqual(data["counts"]["passed"], 4)
        self.assertEqual(data["verdict"], "PASS")
        # MD + JSON aynı tek kaynaktan (hooks birebir).
        md_hooks = [h["name"] for h in data["hooks"]]
        self.assertIn("Verify Stoic-Hume V5 delivery (fail-closed)", md_hooks)


if __name__ == "__main__":
    unittest.main()
