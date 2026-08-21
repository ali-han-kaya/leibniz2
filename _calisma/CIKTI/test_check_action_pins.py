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

    def test_scriptpath_usage_fails_closed(self):
        # github-script@v8 scriptPath input'unu desteklemez — kullanımı
        # fail-closed yakalanmalı (runtime'da "Input required: script" ile
        # patlar). Dosya 'script' input'uyla eval edilmelidir.
        wf = ("jobs:\n  a:\n    steps:\n"
              "      - uses: actions/github-script@v8\n"
              "        with:\n"
              "          scriptPath: _calisma/CIKTI/github_scripts/label_gate.js\n")
        rows = cap.check(wf, PINS)
        fails = [r for r in rows if r["verdict"] == "FAIL"]
        self.assertTrue(fails, "scriptPath kullanımı FAIL üretmeli")
        self.assertTrue(any("scriptPath" in r["note"] for r in fails))

    def test_script_plain_ok(self):
        # 'script' input'u kuralı tetiklemez (scriptPath regex'i eşleşmez).
        wf = ("jobs:\n  a:\n    steps:\n"
              "      - uses: actions/github-script@v8\n"
              "        with:\n"
              "          script: |\n"
              "            const body = fs.readFileSync('x.js', 'utf8');\n")
        rows = cap.check(wf, PINS)
        self.assertFalse(any("scriptPath" in r["note"] for r in rows))


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


class TestBump(unittest.TestCase):
    """--bump: WARN (upgrade) pin'lerini otomatik yükseltir — fail-closed."""

    def _setup(self, d, pins, *uses):
        pins_path = pathlib.Path(d) / "pins.json"
        pins_path.write_text(json.dumps(pins), encoding="utf-8")
        wf_path = pathlib.Path(d) / "wf.yml"
        wf_path.write_text(_wf(*uses), encoding="utf-8")
        return pins_path, wf_path

    def test_bump_upgrades_warn_pins_keeps_others(self):
        with tempfile.TemporaryDirectory() as d:
            pins_path, wf_path = self._setup(
                d, {"actions/checkout": 7, "actions/setup-python": 6},
                "actions/checkout@v8",      # WARN → v8'e yükseltilmeli
                "actions/setup-python@v6")  # PASS → korunmalı
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path), "--bump"])
            self.assertEqual(rc, 0)
            data = json.loads(pins_path.read_text(encoding="utf-8"))
            self.assertEqual(data["actions/checkout"], 8)       # yükseltildi
            self.assertEqual(data["actions/setup-python"], 6)   # korundu

    def test_bump_no_warns_does_not_touch_file(self):
        with tempfile.TemporaryDirectory() as d:
            pins_path, wf_path = self._setup(
                d, {"actions/checkout": 7},
                "actions/checkout@v7")  # PASS — WARN yok
            before = pins_path.read_text(encoding="utf-8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path), "--bump"])
            self.assertEqual(rc, 0)
            self.assertEqual(pins_path.read_text(encoding="utf-8"), before)

    def test_bump_fail_closed_on_downgrade(self):
        # FAIL varken bump hiçbir şey yazmamalı — düzeltme maskelenemez.
        with tempfile.TemporaryDirectory() as d:
            pins_path, wf_path = self._setup(
                d, {"actions/checkout": 7, "actions/setup-python": 6},
                "actions/checkout@v6",      # FAIL (downgrade)
                "actions/setup-python@v7")  # WARN — yazılmamalı
            before = pins_path.read_text(encoding="utf-8")
            rc, out = run_main(["--workflow", str(wf_path),
                                "--pins", str(pins_path), "--bump"])
            self.assertEqual(rc, 1)
            self.assertEqual(pins_path.read_text(encoding="utf-8"), before)
            self.assertIn("HAYIR", out)

    def test_bump_never_adds_new_actions(self):
        # --bump yeni action EKLEMEZ (o iş --update'te); pin'siz action
        # FAIL üretir ve bump'ı bloke eder.
        with tempfile.TemporaryDirectory() as d:
            pins_path, wf_path = self._setup(
                d, {"actions/checkout": 7},
                "actions/checkout@v8",
                "actions/cache@v5")  # pin'siz → FAIL
            before = pins_path.read_text(encoding="utf-8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path), "--bump"])
            self.assertEqual(rc, 1)
            data = json.loads(before)
            self.assertNotIn("actions/cache", data)

    def test_bump_then_check_passes(self):
        # bump sonrası yeniden check → tümü PASS (WARN'lar kapandı).
        with tempfile.TemporaryDirectory() as d:
            pins_path, wf_path = self._setup(
                d, {"actions/checkout": 7},
                "actions/checkout@v8")
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path), "--bump"])
            self.assertEqual(rc, 0)
            rc = cap.main(["--workflow", str(wf_path),
                           "--pins", str(pins_path)])
            self.assertEqual(rc, 0)
            rows = cap.check(_wf("actions/checkout@v8"),
                             json.loads(pins_path.read_text(encoding="utf-8")))
            self.assertEqual(rows[0]["verdict"], "PASS")


def run_main(argv):
    """cap.main'i stdout+stderr'ı yakalayarak çalıştırır → (rc, çıktı)."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cap.main(argv)
    return rc, buf.getvalue()


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
