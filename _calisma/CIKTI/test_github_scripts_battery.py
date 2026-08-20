#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_github_scripts_battery.py — K16 (github-scripts self-test) kapısı.

github_scripts_battery.py'nin kendisini denetler (meta-kapı):
  - 15 senaryonun TAMAMI PASS (mock girdi + çıktı eşleşmesi) — çıkarılmış
    script'lerin davranışı donmuştur.
  - Belirli senaryoların REST çağrı kayıtları beklenenle birebir.
  - _check_expect matcher'ı gerçek bir sapmayı YAKALAR (negatif kontrol —
    matcher'ın kendisinin kör olmadığını kanıtlar).
  - node yoksa battery dürüstçe (False, 'node bulunamadı') raporlar.
  - Harness çıktısı geçerli JSON (anahtar şeması).

stdlib unittest + subprocess — ek bağımlılık yok. node yoksa senaryo
testleri dürüstçe SKIP edilir (test_github_scripts.py ile aynı kural).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import github_scripts_battery as battery  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NODE = shutil.which("node")

HAVE_NODE = NODE is not None


def _find_scenario(name):
    for s in battery.SCENARIOS:
        if s[0] == name:
            return s
    raise KeyError(name)


class TestBatteryAllPass(unittest.TestCase):
    @unittest.skipUnless(HAVE_NODE, "node kurulu değil")
    def test_all_15_scenarios_pass(self):
        results = battery.run_battery()
        self.assertEqual(len(results), len(battery.SCENARIOS))
        failed = [(n, d) for n, ok, d in results if not ok]
        self.assertEqual(failed, [], f"FAIL senaryolar: {failed}")

    @unittest.skipUnless(HAVE_NODE, "node kurulu değil")
    def test_every_scenario_reports_rest_matching(self):
        # Her PASS senaryosunun detayı REST çağrı eşleşmesini söylemeli
        # (yani battery gerçekten çıktıyı denetledi, koşulsuz PASS değil).
        for name, ok, detail in battery.run_battery():
            if ok:
                self.assertIn("REST çağrısı eşleşti", detail,
                              f"{name}: detay eşleşme kanıtı taşımıyor")


class TestCallRecords(unittest.TestCase):
    @unittest.skipUnless(HAVE_NODE, "node kurulu değil")
    def test_manifest_update_scenario_targets_correct_comment(self):
        # 'manifest_comment: K10 FAIL + mevcut yorum güncelle' senaryosu:
        # 777 id'li yorum GÜNCELLENMELİ, yeni yorum OLUŞTURULMAMALI.
        name, script, fixtures, ctx, labels, comments, expect = \
            _find_scenario("manifest_comment: K10 FAIL + mevcut yorum güncelle")
        with tempfile.TemporaryDirectory() as tmp:
            for rel, data in fixtures.items():
                fp = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(data)
            with open(os.path.join(tmp, "mock_comments.json"), "w",
                      encoding="utf-8") as f:
                json.dump(comments, f)
            r, rec = battery._run_scenario(
                NODE, os.path.join(HERE, "github_scripts", script), tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(rec["ok"], rec["error"])
        fns = [c["fn"] for c in rec["calls"]]
        self.assertIn("issues.updateComment", fns)
        self.assertNotIn("issues.createComment", fns)
        upd = next(c for c in rec["calls"]
                   if c["fn"] == "issues.updateComment")
        self.assertEqual(upd["args"]["comment_id"], 777)
        self.assertIn("K10 manifest digest: FAIL", upd["args"]["body"])
        self.assertIn(battery.MARKER_MANIFEST, upd["args"]["body"])

    @unittest.skipUnless(HAVE_NODE, "node kurulu değil")
    def test_config_diff_delete_scenario_removes_stale_comment(self):
        name, script, fixtures, ctx, labels, comments, expect = \
            _find_scenario("config_diff: fark yok + bayat yorum varsa SİLİNİR")
        with tempfile.TemporaryDirectory() as tmp:
            for rel, data in fixtures.items():
                fp = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(data)
            with open(os.path.join(tmp, "mock_comments.json"), "w",
                      encoding="utf-8") as f:
                json.dump(comments, f)
            r, rec = battery._run_scenario(
                NODE, os.path.join(HERE, "github_scripts", script), tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(rec["ok"], rec["error"])
        dels = [c for c in rec["calls"] if c["fn"] == "issues.deleteComment"]
        self.assertEqual(len(dels), 1)
        self.assertEqual(dels[0]["args"]["comment_id"], 888)
        self.assertFalse(any(c["fn"] == "issues.createComment"
                             for c in rec["calls"]))


class TestMatcher(unittest.TestCase):
    def test_check_expect_detects_body_regression(self):
        # Negatif kontrol: body'de marker kaybolursa matcher FAIL demeli.
        rec = {
            "ok": True,
            "setFailed": [],
            "calls": [{"fn": "issues.createComment",
                       "args": {"body": "eksik body"}}],
            "console": [],
        }
        ok, problems = battery._check_expect(
            rec, {"ok": True,
                  "body_contains": {"issues.createComment":
                                    [battery.MARKER_MANIFEST]}})
        self.assertFalse(ok)
        self.assertTrue(any("body" in p for p in problems))

    def test_check_expect_detects_set_failed_regression(self):
        rec = {"ok": True, "setFailed": [], "calls": [], "console": []}
        ok, _ = battery._check_expect(rec, {"set_failed": True})
        self.assertFalse(ok)

    def test_check_expect_detects_wrong_call_count(self):
        rec = {"ok": True, "setFailed": [],
               "calls": [{"fn": "issues.createComment", "args": {}}],
               "console": []}
        ok, _ = battery._check_expect(
            rec, {"call_counts": {"issues.createComment": 2}})
        self.assertFalse(ok)


class TestNoNode(unittest.TestCase):
    def test_battery_reports_node_missing(self):
        # PATH'te node yoksa her senaryo dürüstçe (False, 'node bulunamadı').
        # run_battery ayrıca bilinen konum fallback'ini dener (Homebrew
        # node) — onların da yok olduğunu simüle et (gerçek makinede node
        # /opt/homebrew/bin'de olabilir).
        with mock.patch("github_scripts_battery.shutil.which",
                        return_value=None), \
             mock.patch("github_scripts_battery.os.path.isfile",
                        return_value=False), \
             mock.patch("github_scripts_battery.os.access",
                        return_value=False):
            results = battery.run_battery()
        self.assertEqual(len(results), len(battery.SCENARIOS))
        for name, ok, detail in results:
            self.assertFalse(ok)
            self.assertEqual(detail, "node bulunamadı")


class TestHarnessJsonShape(unittest.TestCase):
    @unittest.skipUnless(HAVE_NODE, "node kurulu değil")
    def test_harness_dumps_valid_json_with_expected_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, rec = battery._run_scenario(
                NODE,
                os.path.join(HERE, "github_scripts", "label_gate.js"), tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        for key in ("script", "ok", "error", "setFailed", "calls", "console"):
            self.assertIn(key, rec, f"kayıtta '{key}' anahtarı yok")
        self.assertTrue(rec["ok"], rec["error"])
        self.assertIsInstance(rec["calls"], list)
        self.assertIsInstance(rec["setFailed"], list)


if __name__ == "__main__":
    unittest.main()
