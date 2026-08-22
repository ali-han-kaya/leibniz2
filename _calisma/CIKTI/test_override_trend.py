#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_override_trend.py — override_trend.py birim testleri.

Kapsar:
  - parse_override_data: zip içinde düz / alt-dizinli / eksik dosya
  - stats: boş liste / tek değer / normal
  - short_date: ISO / boş / kısa
  - main() uçtan uca: mock artifact'larla markdown + JSON üretimi
"""

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

# Module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import override_trend as ot


# ── helpers ────────────────────────────────────────────────────────────────

def _make_zip(files):
    """files: {filename: content_str} — zip bytes döndürür."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def _override_json(warning=True, override_count=1,
                   overrides=None, generated_at=None):
    if overrides is None:
        overrides = [{"key": "budget", "file_value": 30.0,
                      "effective": 25.0}]
    d = {"warning": warning, "override_count": override_count,
         "overrides": overrides}
    if generated_at:
        d["generated_at"] = generated_at
    return json.dumps(d)


# ── tests ─────────────────────────────────────────────────────────────────

class TestParseOverrideData(unittest.TestCase):

    def test_root_level_json(self):
        blob = _make_zip({"cli_overrides_version.json":
                          _override_json(warning=True, override_count=1)})
        data = ot.parse_override_data(blob)
        self.assertTrue(data["warning"])
        self.assertEqual(data["override_count"], 1)

    def test_nested_in_budget_dir(self):
        blob = _make_zip({"budget/cli_overrides_version.json":
                          _override_json(warning=False, override_count=0)})
        data = ot.parse_override_data(blob)
        self.assertFalse(data["warning"])
        self.assertEqual(data["override_count"], 0)

    def test_picks_first_when_multiple(self):
        # İlk bulunan okunur (deterministik olmayan zip sıralamasına
        # rağmen).
        blob = _make_zip({
            "budget/cli_overrides_version.json":
                _override_json(warning=True, override_count=3),
            "cli_overrides_version.json":
                _override_json(warning=False, override_count=0),
        })
        data = ot.parse_override_data(blob)
        # zip namelist sırasına bağlı — her iki durumda da geçerli
        self.assertIn(data["override_count"], [0, 3])

    def test_missing_raises(self):
        blob = _make_zip({"index.json": "{}"})
        with self.assertRaises(ValueError):
            ot.parse_override_data(blob)

    def test_empty_zip_raises(self):
        with self.assertRaises(ValueError):
            ot.parse_override_data(_make_zip({}))

    def test_multiple_overrides(self):
        blob = _make_zip({"cli_overrides_version.json":
                          _override_json(
                              warning=True, override_count=2,
                              overrides=[
                                  {"key": "budget", "file_value": 30.0,
                                   "effective": 25.0},
                                  {"key": "method", "file_value": "weighted",
                                   "effective": "both"},
                              ])})
        data = ot.parse_override_data(blob)
        self.assertEqual(len(data["overrides"]), 2)
        self.assertEqual(data["overrides"][1]["key"], "method")


class TestStats(unittest.TestCase):

    def test_normal(self):
        s = ot.stats([1, 2, 3, 4, 5])
        self.assertEqual(s, {"count": 5, "min": 1, "max": 5, "avg": 3.0})

    def test_single_value(self):
        s = ot.stats([42])
        self.assertEqual(s, {"count": 1, "min": 42, "max": 42, "avg": 42.0})

    def test_empty(self):
        s = ot.stats([])
        self.assertEqual(s, {"count": 0, "min": None, "max": None, "avg": None})

    def test_filters_non_numeric(self):
        s = ot.stats([1, "a", None, 3, 2])
        self.assertEqual(s, {"count": 3, "min": 1, "max": 3, "avg": 2.0})


class TestShortDate(unittest.TestCase):

    def test_full_iso(self):
        self.assertEqual(ot.short_date("2026-08-21T12:34:56Z"),
                         "2026-08-21 12:34")

    def test_empty(self):
        self.assertEqual(ot.short_date(""), "")

    def test_garbage(self):
        self.assertEqual(ot.short_date("not-a-date")[:10], "not-a-date")


class TestMainEndToEnd(unittest.TestCase):
    """main()'in markdown + JSON üretimini mock API ile test eder.

    Not: Bu test gerçek GitHub API çağrısı yapmaz; api_get'i monkey-patch
    ile değiştirerek mock artifact listesi + zip blob'ları kullanır.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_main(self, artifacts, expect_rows, expect_warnings):
        """Monkey-patch api_get ile main()'i koş ve çıktıyı doğrula."""
        import override_trend
        real_api_get = override_trend.api_get
        real_main = override_trend.main

        call_count = [0]

        def mock_api_get(path, token, binary=False):
            call_count[0] += 1
            if "/actions/artifacts?name=budget" in path:
                return {"artifacts": artifacts}
            if "/zip" in path:
                # artifact id'yi path'ten çıkar
                aid = int(path.split("/")[-2])
                for a in artifacts:
                    if a["id"] == aid:
                        return a["_zip_blob"]
                raise RuntimeError(f"artifact {aid} not found")
            return {}

        override_trend.api_get = mock_api_get

        try:
            old_argv = sys.argv
            sys.argv = ["override_trend.py", "--repo", "test/repo",
                        "--out-dir", self.out, "--max-artifacts", "10"]
            # Patched env
            old_env = dict(os.environ)
            os.environ["GITHUB_TOKEN"] = "fake-token"
            try:
                override_trend.main()
            except SystemExit:
                pass
            finally:
                os.environ.clear()
                os.environ.update(old_env)
                sys.argv = old_argv
        finally:
            override_trend.api_get = real_api_get

        # Check markdown
        md_path = os.path.join(self.out, "override-trend.md")
        self.assertTrue(os.path.isfile(md_path),
                        f"override-trend.md üretilmedi; çağrı sayısı={call_count[0]}")
        md = open(md_path, encoding="utf-8").read()
        self.assertIn("# CLI Override Trendi", md)
        if expect_rows > 0:
            self.assertIn("| # | Tarih", md)

        # Check JSON
        json_path = os.path.join(self.out, "override-trend.json")
        self.assertTrue(os.path.isfile(json_path))
        js = json.load(open(json_path, encoding="utf-8"))
        self.assertEqual(js["repo"], "test/repo")
        self.assertEqual(js["run_count"], expect_rows)
        self.assertEqual(js["warning_run_count"], expect_warnings)
        self.assertIn("rows", js)
        self.assertIn("override_counts", js)
        return md, js

    def test_two_runs_one_warning(self):
        artifacts = [
            {"id": 1, "name": "budget",
             "created_at": "2026-08-20T10:00:00Z",
             "workflow_run": {"id": 100},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=False, override_count=0,
                                generated_at="2026-08-20T10:00:00Z"),
             })},
            {"id": 2, "name": "budget",
             "created_at": "2026-08-21T10:00:00Z",
             "workflow_run": {"id": 101},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=True, override_count=1,
                                generated_at="2026-08-21T10:00:00Z"),
             })},
        ]
        md, js = self._mock_main(artifacts, 2, 1)
        self.assertIn("⚠️", md)
        self.assertIn("—", md)  # warning=false satırında
        self.assertIn("50.0%", md)  # warning oranı

    def test_no_warnings(self):
        artifacts = [
            {"id": 1, "name": "budget",
             "created_at": "2026-08-21T10:00:00Z",
             "workflow_run": {"id": 100},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=False, override_count=0,
                                generated_at="2026-08-21T10:00:00Z"),
             })},
        ]
        md, js = self._mock_main(artifacts, 1, 0)
        self.assertNotIn("⚠️", md)

    def test_artifact_without_override_json_skipped(self):
        artifacts = [
            {"id": 1, "name": "budget",
             "created_at": "2026-08-21T10:00:00Z",
             "workflow_run": {"id": 100},
             "_zip_blob": _make_zip({"index.json": "{}"})},
            {"id": 2, "name": "budget",
             "created_at": "2026-08-21T11:00:00Z",
             "workflow_run": {"id": 101},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=True, override_count=1,
                                generated_at="2026-08-21T11:00:00Z"),
             })},
        ]
        md, js = self._mock_main(artifacts, 1, 1)
        # Yalnızca 1 satır (id=2), id=1 atlandı
        self.assertIn("⚠️", md)

    def test_empty_artifacts(self):
        artifacts = []
        md, js = self._mock_main(artifacts, 0, 0)
        self.assertIn("Veri yok", md)

    def test_key_distribution(self):
        artifacts = [
            {"id": 1, "name": "budget",
             "created_at": "2026-08-20T10:00:00Z",
             "workflow_run": {"id": 100},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=True, override_count=1,
                                overrides=[{"key": "budget",
                                            "file_value": 30.0,
                                            "effective": 25.0}],
                                generated_at="2026-08-20T10:00:00Z"),
             })},
            {"id": 2, "name": "budget",
             "created_at": "2026-08-21T10:00:00Z",
             "workflow_run": {"id": 101},
             "_zip_blob": _make_zip({
                 "cli_overrides_version.json":
                 _override_json(warning=True, override_count=2,
                                overrides=[
                                    {"key": "budget",
                                     "file_value": 30.0,
                                     "effective": 25.0},
                                    {"key": "method",
                                     "file_value": "weighted",
                                     "effective": "both"},
                                ],
                                generated_at="2026-08-21T10:00:00Z"),
             })},
        ]
        md, js = self._mock_main(artifacts, 2, 2)
        self.assertIn("### Override anahtarı dağılımı", md)
        self.assertIn("`budget`", md)
        self.assertIn("`method`", md)


class TestMainEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_main_without_token_uses_gh_api(self):
        import subprocess as sp
        # Token yok → gh api'ye düşer. gh yoksa veya
        # repo erişilemezse exception → exit 1.
        old_argv = sys.argv
        sys.argv = ["override_trend.py", "--repo", "nobody/nothing",
                    "--out-dir", self.out, "--max-artifacts", "1"]
        old_env = dict(os.environ)
        os.environ.pop("GITHUB_TOKEN", None)
        try:
            with self.assertRaises(SystemExit) as ctx:
                ot.main()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            sys.argv = old_argv

    def test_main_creates_out_dir(self):
        out_sub = os.path.join(self.out, "sub", "deep")
        self.assertFalse(os.path.isdir(out_sub))
        # Artifacts API çağrısı başarısız olacak ama out-dir oluşmalı
        old_argv = sys.argv
        sys.argv = ["override_trend.py", "--repo", "nobody/nothing",
                     "--out-dir", out_sub, "--max-artifacts", "1"]
        old_env = dict(os.environ)
        os.environ.pop("GITHUB_TOKEN", None)
        try:
            with self.assertRaises(SystemExit):
                ot.main()
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            sys.argv = old_argv
        self.assertTrue(os.path.isdir(out_sub))


if __name__ == "__main__":
    unittest.main()