#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_action_pins.py — action major pin kapısı.

check_action_pins.py'nin pure mantığını deterministik doğrular: regex ile
uses çıkarımı (heredoc JS yanlış-pozitif yok), split_action, check kararları
(downgrade FAIL / yeni action FAIL / upgrade WARN / lokal SKIP / bozuk ref
FAIL) ve collect_pins. stdlib unittest — ağ/PyYAML yok.
"""
import json
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_action_pins as cap  # noqa: E402


def _wf(*uses):
    steps = "".join(f"      - uses: {u}\n" for u in uses)
    return f"jobs:\n  a:\n    steps:\n{steps}\n"


PINS = {
    "actions/checkout": 7,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
}


class TestExtractUses(unittest.TestCase):
    def test_extracts_unique_ordered(self):
        txt = ("jobs:\n  a:\n    steps:\n"
               "      - uses: actions/checkout@v7\n"
               "      - uses: actions/setup-python@v6\n"
               "      - uses: actions/checkout@v7\n")  # duplicate
        self.assertEqual(cap.extract_uses(txt),
                         ["actions/checkout@v7", "actions/setup-python@v6"])

    def test_ignores_heredoc_js_and_comments(self):
        txt = (
            "#   action-runtimes: her uses: action'ın ...\n"
            "jobs:\n  a:\n    steps:\n"
            "      - name: x\n"
            "        uses: actions/github-script@v8\n"
            "        with:\n"
            "          script: |\n"
            "            // 'uses:' JS stringi degil\n"
            "            const u = 'uses: actions/checkout@v1';\n")
        self.assertEqual(cap.extract_uses(txt), ["actions/github-script@v8"])

    def test_ignores_inline_comment_after_value(self):
        txt = _wf("actions/checkout@v7  # tam major")
        self.assertEqual(cap.extract_uses(txt), ["actions/checkout@v7"])


class TestSplitAction(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(cap.split_action("actions/checkout@v7"),
                         ("actions/checkout", "v7", 7))

    def test_no_ref(self):
        owner, ref, major = cap.split_action("actions/checkout")
        self.assertEqual(owner, "actions/checkout")
        self.assertEqual(ref, "")
        self.assertIsNone(major)

    def test_non_v_ref(self):
        _owner, ref, major = cap.split_action("actions/checkout@main")
        self.assertEqual(ref, "main")
        self.assertIsNone(major)


class TestCheck(unittest.TestCase):
    def test_pass_exact_pin(self):
        rows = cap.check(_wf("actions/checkout@v7"), PINS)
        self.assertEqual(rows[0]["verdict"], "PASS")

    def test_downgrade_fail(self):
        rows = cap.check(_wf("actions/checkout@v6"), PINS)
        self.assertEqual(rows[0]["verdict"], "FAIL")
        self.assertIn("downgrade", rows[0]["note"])

    def test_upgrade_warn(self):
        rows = cap.check(_wf("actions/checkout@v8"), PINS)
        self.assertEqual(rows[0]["verdict"], "WARN")

    def test_new_action_fail(self):
        rows = cap.check(_wf("actions/cache@v5"), PINS)
        self.assertEqual(rows[0]["verdict"], "FAIL")
        self.assertIn("pin yok", rows[0]["note"])

    def test_local_action_skip(self):
        rows = cap.check(_wf("./.github/actions/foo"), PINS)
        self.assertEqual(rows[0]["verdict"], "SKIP")

    def test_unparseable_ref_on_pinned_fail(self):
        # pin'li bir action @main'e çekilirse major ayrıştırılamaz → FAIL.
        rows = cap.check(_wf("actions/checkout@main"), PINS)
        self.assertEqual(rows[0]["verdict"], "FAIL")
        self.assertIn("major ayrıştırılamadı", rows[0]["note"])


class TestCollectPins(unittest.TestCase):
    def test_collects_only_vn(self):
        pins = cap.collect_pins(
            _wf("actions/checkout@v7", "actions/setup-python@v6",
                "actions/foo@main"))
        self.assertEqual(pins, {"actions/checkout": 7,
                                "actions/setup-python": 6})

    def test_update_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            pins_path = pathlib.Path(d) / "pins.json"
            wf_path = pathlib.Path(d) / "wf.yml"
            wf_path.write_text(_wf("actions/checkout@v7"), encoding="utf-8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path), "--update"])
            self.assertEqual(rc, 0)
            data = json.loads(pins_path.read_text(encoding="utf-8"))
            self.assertEqual(data, {"actions/checkout": 7})


class TestMain(unittest.TestCase):
    def test_main_fail_on_downgrade(self):
        with tempfile.TemporaryDirectory() as d:
            pins_path = pathlib.Path(d) / "pins.json"
            pins_path.write_text(json.dumps({"actions/checkout": 7}),
                                 encoding="utf-8")
            wf_path = pathlib.Path(d) / "wf.yml"
            wf_path.write_text(_wf("actions/checkout@v6"), encoding="utf-8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path)])
            self.assertEqual(rc, 1)

    def test_main_pass_on_pin(self):
        with tempfile.TemporaryDirectory() as d:
            pins_path = pathlib.Path(d) / "pins.json"
            pins_path.write_text(json.dumps({"actions/checkout": 7}),
                                 encoding="utf-8")
            wf_path = pathlib.Path(d) / "wf.yml"
            wf_path.write_text(_wf("actions/checkout@v7"), encoding="utf-8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
