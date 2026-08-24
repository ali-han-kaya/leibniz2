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
import re
import sys
import tempfile
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
| 1 | A | Delivery verification — K1-K14 (single entry point) | ✅ K0-K7 tek komutta |
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
            [("A", "Delivery verification — K1-K14 (single entry point)"),
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


class TestExcludeSelf(unittest.TestCase):
    def test_removes_own_job_and_artifact(self):
        jobs, arts = als.exclude_self(
            ["Job A", als.SELF_JOB], ["art1", als.SELF_ARTIFACT])
        self.assertEqual(jobs, ["Job A"])
        self.assertEqual(arts, ["art1"])

    def test_absent_self_is_noop(self):
        jobs, arts = als.exclude_self(["Job A"], ["art1"])
        self.assertEqual(jobs, ["Job A"])
        self.assertEqual(arts, ["art1"])


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


class TestExtractWorkflowUploadNames(unittest.TestCase):
    def test_extracts_name_from_upload_block(self):
        wf = ("      - name: Upload log\n"
              "        uses: actions/upload-artifact@v6\n"
              "        with:\n"
              "          name: unit-tests\n"
              "          path: unit_tests.log\n")
        self.assertEqual(als.extract_workflow_upload_names(wf),
                         ["unit-tests"])

    def test_multiple_and_ordered(self):
        wf = (
            "        uses: actions/upload-artifact@v6\n"
            "        with:\n"
            "          name: b-art\n"
            "          path: x\n"
            "        uses: actions/upload-artifact@v6\n"
            "        with:\n"
            "          name: a-art\n"
            "          path: y\n")
        self.assertEqual(als.extract_workflow_upload_names(wf),
                         ["b-art", "a-art"])

    def test_non_upload_artifact_ignored(self):
        wf = ("      - name: Download\n"
              "        uses: actions/download-artifact@v7\n"
              "        with:\n"
              "          name: refs-trend\n")
        self.assertEqual(als.extract_workflow_upload_names(wf), [])

    def test_duplicates_removed(self):
        wf = ("      - name: Up1\n"
              "        uses: actions/upload-artifact@v6\n"
              "        with:\n"
              "          name: dup\n"
              "      - name: Up2\n"
              "        uses: actions/upload-artifact@v6\n"
              "        with:\n"
              "          name: dup\n")
        self.assertEqual(als.extract_workflow_upload_names(wf), ["dup"])


class TestE2EArtifactDocSync(unittest.TestCase):
    """Uçtan uca (offline) artifact-doc senkron kapısı — python3-shell drift
    regression'ı (2026-08-21, `845206a`).

    Gerçek `.github/workflows/verify.yml` upload-artifact `name:` değerleri
    ↔ gerçek `docs/PUBLISH_SCENARIO.md` artifact listesi. Yeni bir
    `actions/upload-artifact` eklendiğinde doc güncellenmezse bu test FAIL
    eder (exit 1 mantığıyla BİREBİR aynı ekstra/fazla seti) — canlı CI'daki
    audit-live-ci'yi beklemeden commit'te yakalar.
    """

    @classmethod
    def setUpClass(cls):
        cls.wf_path = als.REPO_ROOT / ".github" / "workflows" / "verify.yml"
        cls.doc_path = als.REPO_ROOT / "docs" / "PUBLISH_SCENARIO.md"
        cls.wf_text = cls.wf_path.read_text(encoding="utf-8")
        cls.doc_text = cls.doc_path.read_text(encoding="utf-8")

    def _live(self):
        return als.extract_workflow_upload_names(self.wf_text)

    def _doc(self, text):
        return als.parse_doc_artifacts(text)

    @staticmethod
    def _drop_bullet(text, name):
        return re.sub(rf"^[ \t]*-[ \t]*`{re.escape(name)}`[^\n]*\n",
                      "", text, flags=re.M)

    def test_current_state_matches(self):
        cmp = als.compare(self._doc(self.doc_text), self._live(), "artifacts")
        self.assertTrue(
            cmp["ok"],
            "DRIFT: doc↔workflow artifact eşleşmiyor — eksik="
            f"{cmp['missing']!r} fazla={cmp['extra']!r}. Yeni bir "
            "upload-artifact eklendiyse PUBLISH_SCENARIO.md 'Artifact "
            "listesi'ni YALNIZCA aynı commit'te güncelle.")

    def test_python3_shell_drift_caught(self):
        """Tarihsel drift'in birebir provası: doc'ta python3-shell bullet'i
        yokken canlıda VAR → audit fazla artifact olarak yakalamalı."""
        historic = self._drop_bullet(self.doc_text, "python3-shell")
        doc, live = self._doc(historic), self._live()
        cmp = als.compare(doc, live, "artifacts")
        self.assertFalse(cmp["ok"])
        self.assertEqual(cmp["extra"], ["python3-shell"])
        self.assertEqual(cmp["missing"], [])

    def test_new_upload_without_doc_update_fails(self):
        """Gelecek-proof: workflow'a FAKE bir upload-artifact eklenirse
        extractor onu bulur ve doc'a karşı fazla olarak FAIL üretir."""
        fake = ("      - name: Upload fake\n"
                "        uses: actions/upload-artifact@v6\n"
                "        with:\n"
                "          name: yarin-yeni-artifact\n"
                "          path: x\n")
        live = als.extract_workflow_upload_names(self.wf_text + fake)
        cmp = als.compare(self._doc(self.doc_text), live, "artifacts")
        self.assertFalse(cmp["ok"])
        self.assertEqual(cmp["extra"], ["yarin-yeni-artifact"])

    def _run_main(self, doc_text, live_artifacts):
        doc_jobs = [n for (_c, n) in als.parse_doc_jobs(doc_text)]
        live_jobs = list(dict.fromkeys(doc_jobs + [als.SELF_JOB]))
        live = list(dict.fromkeys(live_artifacts + [als.SELF_ARTIFACT]))
        with tempfile.TemporaryDirectory() as td:
            doc = pathlib.Path(td) / "PUBLISH_SCENARIO.md"
            doc.write_text(doc_text, encoding="utf-8")
            buf = io.StringIO()
            with mock.patch.object(als, "get_repo", return_value="o/r"), \
                    mock.patch.object(als, "get_latest_run",
                                      return_value={"databaseId": 1,
                                                    "headSha": "abc"}), \
                    mock.patch.object(als, "get_run_jobs", return_value=live_jobs), \
                    mock.patch.object(als, "get_run_artifacts",
                                      return_value=live), \
                    mock.patch.object(sys, "stdout", new=buf):
                rc = als.main(["--doc", str(doc), "--json"])
            d = json.loads(buf.getvalue())
        return rc, d

    def test_main_current_state_pass(self):
        rc, d = self._run_main(self.doc_text, self._live())
        self.assertEqual(rc, 0)
        self.assertEqual(d["verdict"], "PASS")

    def test_main_python3_shell_drift_exit_1(self):
        historic = self._drop_bullet(self.doc_text, "python3-shell")
        rc, d = self._run_main(historic, self._live())
        self.assertEqual(rc, 1)
        self.assertEqual(d["verdict"], "FAIL")
        self.assertEqual(d["artifacts"]["extra"], ["python3-shell"])


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
