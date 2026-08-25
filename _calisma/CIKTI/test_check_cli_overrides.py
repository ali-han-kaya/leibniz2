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
    def _run(self, config_json=None, version_out=False):
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
            vpath = None
            if version_out:
                vpath = os.path.join(out, "cli_overrides_version.json")
                argv += ["--version-out", vpath]
            rc = co.main(argv)
            txt_path = os.path.join(out, "cli_overrides_warning.txt")
            with open(txt_path, encoding="utf-8") as f:
                txt = f.read()
            with open(index, encoding="utf-8") as f:
                idx = json.load(f)
            ver = None
            if vpath and os.path.isfile(vpath):
                with open(vpath, encoding="utf-8") as f:
                    ver = json.load(f)
            return rc, txt, idx, ver

    def test_no_override(self):
        rc, txt, idx, _ = self._run(_cfg({
            "budget": {"cli_given": False, "override": False},
        }))
        self.assertEqual(rc, 0)
        self.assertIn("YOK", txt)
        self.assertFalse(idx["cli_overrides"]["warning"])

    def test_override_written(self):
        rc, txt, idx, _ = self._run(_cfg({
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
        rc, txt, idx, _ = self._run(None)
        self.assertEqual(rc, 0)
        self.assertIn("bulunamadı", txt)
        self.assertFalse(idx["cli_overrides"]["warning"])


class TestVersionOut(unittest.TestCase):
    def _cfg(self, override=True):
        return {"cli_overrides": {
            "budget": {"cli_given": override, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0,
                       "override": override},
        }}

    def test_version_json_written_with_override(self):
        rc, _, _, ver = TestMainEndToEnd()._run(self._cfg(True),
                                                version_out=True)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(ver)
        self.assertIn("tool", ver)
        self.assertIn("ts", ver)
        self.assertTrue(ver["warning"])
        self.assertEqual(ver["override_count"], 1)
        self.assertEqual(ver["overrides"][0]["key"], "budget")
        self.assertTrue(ver["config_read"])
        self.assertIn("TESPİT EDİLDİ", ver["summary"])

    def test_version_json_written_no_override(self):
        rc, _, _, ver = TestMainEndToEnd()._run(self._cfg(False),
                                                version_out=True)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(ver)
        self.assertFalse(ver["warning"])
        self.assertEqual(ver["override_count"], 0)
        self.assertIn("YOK", ver["summary"])

    def test_version_json_written_config_missing(self):
        # config yoksa da VERSION JSON yazılır (denetim izi tam) — warning
        # false + config_read false (advisory).
        rc, _, _, ver = TestMainEndToEnd()._run(None, version_out=True)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(ver)
        self.assertFalse(ver["warning"])
        self.assertFalse(ver["config_read"])


class TestCrossCheck(unittest.TestCase):
    """cross_check(): iki kaynağın (index.json + VERSION JSON) tutarlılığı."""

    def _idx(self, warning, overrides):
        return json.dumps({
            "runs": [{"source": "verify", "estimated_usd": 1.0,
                      "limit": 30, "tokens_est": 330000}],
            "method": "weighted",
            "cli_overrides": {"warning": warning, "overrides": overrides,
                              "raw": {}},
        })

    def _ver(self, warning, overrides):
        return json.dumps({
            "tool": "check_cli_overrides.py", "warning": warning,
            "override_count": len(overrides), "overrides": overrides,
            "config_read": True,
            "summary": "CLI override VAR" if overrides else "CLI override YOK"})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.idx = os.path.join(self.tmp.name, "index.json")
        self.ver = os.path.join(self.tmp.name, "version.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, idx, vjson):
        if idx is not None:
            with open(self.idx, "w") as f:
                f.write(idx)
        if vjson is not None:
            with open(self.ver, "w") as f:
                f.write(vjson)
        ip = self.idx if (idx is not None and os.path.isfile(self.idx)) else "/nonexistent/index.json"
        return co.cross_check(ip, self.ver)

    def test_both_empty_consistent(self):
        ok, detail, problems = self._check(
            self._idx(False, []), self._ver(False, []))
        self.assertTrue(ok, detail)
        self.assertEqual([], problems)

    def test_both_with_override_consistent(self):
        ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0}]
        ok, detail, problems = self._check(
            self._idx(True, ov), self._ver(True, ov))
        self.assertTrue(ok, detail)
        self.assertEqual([], problems)

    def test_warning_flag_mismatch(self):
        ok, detail, problems = self._check(
            self._idx(True, []), self._ver(False, []))
        self.assertFalse(ok)
        self.assertTrue(any("warning" in p for p in problems))

    def test_override_count_mismatch(self):
        ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0}]
        ok, detail, problems = self._check(
            self._idx(True, ov), self._ver(True, []))
        self.assertFalse(ok)
        self.assertTrue(any("sayısı" in p for p in problems))

    def test_value_mismatch(self):
        idx_ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0}]
        ver_ov = [{"key": "budget", "file_value": 30.0, "effective": 20.0}]
        ok, detail, problems = self._check(
            self._idx(True, idx_ov), self._ver(True, ver_ov))
        self.assertFalse(ok)
        self.assertTrue(any("uyuşmaz" in p for p in problems))

    def test_key_only_in_index(self):
        idx_ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0},
                  {"key": "method", "file_value": "weighted",
                   "effective": "both"}]
        ver_ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0}]
        ok, detail, problems = self._check(
            self._idx(True, idx_ov), self._ver(True, ver_ov))
        self.assertFalse(ok)
        self.assertTrue(any("index'te var, version'da yok" in p
                           for p in problems))

    def test_index_missing(self):
        # index dosyası hiç oluşturulmadı — sadece version yaz.
        ok, detail, problems = self._check(
            None, self._ver(False, []))
        self.assertFalse(ok)
        self.assertIn("index.json bulunamadı", detail)

    def test_index_missing_but_version_has_overrides(self):
        ov = [{"key": "budget", "file_value": 30.0, "effective": 25.0}]
        # index yok, sadece version var
        ok, detail, problems = self._check(
            None, self._ver(True, ov))
        self.assertFalse(ok)
        # version'da override varken index yok → veri kaybı şüphesi
        self.assertTrue(any("veri kaybı" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
