#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_audit_live_ci_sync.py — audit_live_ci_sync.py parse/karşılaştırma.

Canlı GitHub'a BAĞIMLI DEĞİLDİR (offline): doc parse (job tablosu +
artifact bölümü) ve compare (eksik/fazla) mantığını mock metinle doğrular.
Ağ/gh çağrıları yok — unit-test CI'da koşar.
"""
import io
import json
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import audit_live_ci_sync as als  # noqa: E402

DOC = """\
**Job kategorileri (16 job = 8 required + 4 advisory + 3 PR-only + 1 manifest):**

| # | Kategori | Job | Beklenen sonuç |
|---|---|---|---|
| | **A — Required** | | |
| 1 | A | Delivery verification — K1-K9 (single entry point) | ✅ K0-K7 tek komutta |
| 2 | A | Action runtime check (node24) | ✅ node24 |
| | **B — Advisory** | | |
| 3 | B | Daemon mode HTTP 200 (advisory) | ✅ daemon smoke |
| | **C — PR-only** | | |
| 4 | C | Commit-msg gate | ✅ ihlal varsa FAIL |

**Artifact listesi (3):**
- `unit-tests` (CIKTI logu — `test_*.py` glob'u)
- `budget-verify` + `budget` (bütçe sidecar + aggregator)
- `daemon-http` (daemon smoke raporu)
"""


class TestParseDocJobs(unittest.TestCase):
    def test_extracts_category_and_name(self):
        jobs = als.parse_doc_jobs(DOC)
        self.assertEqual(
            jobs,
            [("A", "Delivery verification — K1-K9 (single entry point)"),
             ("A", "Action runtime check (node24)"),
             ("B", "Daemon mode HTTP 200 (advisory)"),
             ("C", "Commit-msg gate")])

    def test_empty_doc(self):
        self.assertEqual(als.parse_doc_jobs(""), [])

    def test_no_table_rows(self):
        self.assertEqual(als.parse_doc_jobs("just text\nno rows\n"), [])


class TestParseDocArtifacts(unittest.TestCase):
    def test_scoped_to_artifact_section(self):
        # Tüm dokümandaki backtick'ler toplanmamalı — yalnızca Artifact
        # listesi bölümündeki başlık backtick'leri (açıklama öncesi).
        arts = als.parse_doc_artifacts(DOC)
        self.assertEqual(arts, ["unit-tests", "budget-verify", "budget",
                                "daemon-http"])

    def test_description_backticks_excluded(self):
        # "- `unit-tests` (… `test_*.py` glob'u)" → test_*.py ad OLMAZ.
        self.assertNotIn("test_*.py", als.parse_doc_artifacts(DOC))

    def test_no_artifact_section(self):
        self.assertEqual(als.parse_doc_artifacts("no section here"), [])


class TestCompare(unittest.TestCase):
    def test_perfect_match(self):
        r = als.compare(["a", "b"], ["b", "a"], "jobs")
        self.assertTrue(r["ok"])
        self.assertEqual(r["missing"], [])
        self.assertEqual(r["extra"], [])

    def test_missing_and_extra(self):
        r = als.compare(["a", "b", "c"], ["a", "d"], "jobs")
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], ["b", "c"])
        self.assertEqual(r["extra"], ["d"])

    def test_duplicates_ignored(self):
        r = als.compare(["a"], ["a", "a"], "jobs")
        self.assertTrue(r["ok"])


class TestMainFailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(__file__).parent / ".audit_tmp_doc.md"
        self.tmp.write_text(DOC, encoding="utf-8")

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)

    def test_main_pass_exit_0(self):
        buf = io.StringIO()
        with mock.patch.object(als, "parse_doc_jobs",
                               return_value=[("A", "Job A")]), \
                mock.patch.object(als, "parse_doc_artifacts",
                                  return_value=["art1"]), \
                mock.patch.object(als, "get_repo", return_value="o/r"), \
                mock.patch.object(als, "get_latest_run",
                                  return_value={"databaseId": 1,
                                                "headSha": "abc"}), \
                mock.patch.object(als, "get_run_jobs",
                                  return_value=["Job A"]), \
                mock.patch.object(als, "get_run_artifacts",
                                  return_value=["art1"]), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = als.main(["--doc", str(self.tmp), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["verdict"], "PASS")

    def test_main_drift_exit_1(self):
        buf = io.StringIO()
        with mock.patch.object(als, "parse_doc_jobs",
                               return_value=[("A", "Job A")]), \
                mock.patch.object(als, "parse_doc_artifacts",
                                  return_value=["art1"]), \
                mock.patch.object(als, "get_repo", return_value="o/r"), \
                mock.patch.object(als, "get_latest_run",
                                  return_value={"databaseId": 1,
                                                "headSha": "abc"}), \
                mock.patch.object(als, "get_run_jobs",
                                  return_value=["Job A", "Fazla Job"]), \
                mock.patch.object(als, "get_run_artifacts",
                                  return_value=["art1"]), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = als.main(["--doc", str(self.tmp), "--json"])
        self.assertEqual(rc, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "FAIL")
        self.assertEqual(d["jobs"]["extra"], ["Fazla Job"])

    def test_main_missing_doc_exit_2(self):
        with mock.patch.object(sys, "stderr", new=io.StringIO()):
            rc = als.main(["--doc", "/nonexistent/doc.md"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
