#!/usr/bin/env python3
"""test_check_cli_overrides.py — check_cli_overrides.py regresyon kapısı.

Kapsam: cli_overrides bloğundan override==true kayıtlarının ayrıştırılması,
insan-okur uyarı satırlarının üretimi ve main()'in dosya/index yazma
davranışı (override yok / var / config eksik). stdlib unittest; ek bağımlılık
yok — CI'da `test_*.py` deseniyle otomatik koşar.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cli_overrides as co  # noqa: E402


def _cfg(overrides):
    return {"cli_overrides": overrides}


class TestCollectOverrides(unittest.TestCase):
    def test_no_overrides(self):
        cfg = _cfg({
            "budget": {"cli_given": False, "cli_value": None,
                       "file_value": 30.0, "effective": 30.0,
                       "override": False},
        })
        overrides, raw = co.collect_overrides(cfg)
        self.assertEqual(overrides, [])
        self.assertEqual(raw, cfg["cli_overrides"])

    def test_override_true(self):
        cfg = _cfg({
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0,
                       "override": True},
        })
        overrides, _ = co.collect_overrides(cfg)
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0]["key"], "budget")
        self.assertEqual(overrides[0]["file_value"], 30.0)
        self.assertEqual(overrides[0]["effective"], 25.0)

    def test_missing_or_malformed_cli_overrides(self):
        self.assertEqual(co.collect_overrides({}), ([], {}))
        # cli_overrides dict değilse override yok sayılır (savunmacı).
        self.assertEqual(co.collect_overrides({"cli_overrides": 7}), ([], {}))
        # Kayıt dict değilse atlanır.
        self.assertEqual(
            co.collect_overrides({"cli_overrides": {"budget": "x"}}),
            ([], {"budget": "x"}),
        )


class TestRenderLines(unittest.TestCase):
    def test_no_override_line(self):
        lines = co.render_lines([], {})
        self.assertTrue(any("YOK" in l for l in lines))

    def test_override_lines(self):
        overrides = [{"key": "budget", "file_value": 30.0,
                      "effective": 25.0}]
        lines = co.render_lines(overrides, {})
        joined = "\n".join(lines)
        self.assertIn("TESPİT EDİLDİ", joined)
        self.assertIn("30.0 → 25.0", joined)


class TestMainEndToEnd(unittest.TestCase):
    def _run(self, config_json=None):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "budget")
            os.makedirs(out, exist_ok=True)
            index = os.path.join(out, "index.json")
            with open(index, "w", encoding="utf-8") as f:
                json.dump({"runs": [], "failures": []}, f)
            cfg_path = None
            if config_json is not None:
                cfg_path = os.path.join(d, "effective_config.json")
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(config_json, f)
            argv = ["--config", cfg_path or "",
                    "--index", index, "--out-dir", out]
            rc = co.main(argv)
            txt_path = os.path.join(out, "cli_overrides_warning.txt")
            with open(txt_path, encoding="utf-8") as f:
                txt = f.read()
            with open(index, encoding="utf-8") as f:
                idx = json.load(f)
            return rc, txt, idx

    def test_no_override(self):
        rc, txt, idx = self._run(_cfg({
            "budget": {"cli_given": False, "override": False},
        }))
        self.assertEqual(rc, 0)
        self.assertIn("YOK", txt)
        self.assertFalse(idx["cli_overrides"]["warning"])

    def test_override_written(self):
        rc, txt, idx = self._run(_cfg({
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0,
                       "override": True},
        }))
        self.assertEqual(rc, 0)
        self.assertIn("TESPİT EDİLDİ", txt)
        self.assertTrue(idx["cli_overrides"]["warning"])
        self.assertEqual(idx["cli_overrides"]["overrides"][0]["key"], "budget")

    def test_missing_config_advisory(self):
        # config yok → UYARI, exit 0 (advisory; fail-closed değil).
        rc, txt, idx = self._run(None)
        self.assertEqual(rc, 0)
        self.assertIn("bulunamadı", txt)
        self.assertFalse(idx["cli_overrides"]["warning"])


if __name__ == "__main__":
    unittest.main()
