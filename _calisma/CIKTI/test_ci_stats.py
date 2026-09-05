#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_stats.py — ci_stats.py §9 bağlantısının birim testleri.

Kapsanan sözleşmeler:
  - markdown_rows : §9 tablo satırları (linkli Run ID, backtick branch, durum
                    işaretleri, süre/job/title sütunları, | kaçışı)
  - stats_line    : success rate + avg duration tek satır özeti
  - update_doc_block : docs/PRE_PUSH_DENETIM_RAPORU.md §9 bloğunu değiştirme
                    (fail-closed: header/bitiş işareti yoksa ValueError + dosya
                    değişmez)
  - main() e2e    : --update-doc ile canlı akış (gh mock'lu) → eski satırlar
                    gider, istatistik satırı eklenir; --markdown çıktı sözleşmesi
"""
import pathlib
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import ci_stats  # noqa: E402


def _row(rid=111, status="completed", conclusion="success", branch="main",
         created="2026-08-26T10:00:00Z", dur=180, jobs=24,
         title="ci_stats §9 bağlantısı"):
    return {
        "id": rid,
        "createdAt": created,
        "status": status,
        "conclusion": conclusion,
        "duration_s": dur,
        "jobs": jobs,
        "branch": branch,
        "title": title,
    }


_DOC = """\
## 9. CI Run Trend Tablosu (son 10 run)

Canlı kaynak: `gh run list --limit 10` + `gh run view <id> --json jobs`.

| # | Run ID | Tarih (UTC) | Branch | Durum | Süre | Job | Özet |
|---|---|---|---|---|---|---|---|
| 1 | [999](https://github.com/o/r/actions/runs/999) | 2026-08-20 09:00 | `main` | 🔴 failure | 3m | 20 | eski satır |

**Kırılım analizi (özet):** eski açıklama.

## 10. Sonraki bölüm
"""


class TestMarkdownRows(unittest.TestCase):
    def test_basic_row(self):
        lines = ci_stats.markdown_rows([_row()], "o/r")
        self.assertEqual(lines[0], ci_stats.TABLE_HEADER)
        self.assertEqual(lines[1], "|---|---|---|---|---|---|---|---|")
        row = lines[2]
        self.assertIn("| 1 | [111](https://github.com/o/r/actions/runs/111) |", row)
        self.assertIn("2026-08-26 10:00", row)
        self.assertIn("`main`", row)
        self.assertIn("✅ success", row)
        self.assertIn("3m00s", row)
        self.assertIn("| 24 | ci_stats §9 bağlantısı |", row)

    def test_failure_and_in_progress_marks(self):
        rows = [_row(1, conclusion="failure"),
                _row(2, status="in_progress", conclusion="")]
        lines = ci_stats.markdown_rows(rows, "o/r")
        self.assertIn("🔴 failure", lines[2])
        self.assertIn("🔄 in_progress", lines[3])

    def test_pipe_escaped_in_title(self):
        r = _row(title="a|b|c")
        lines = ci_stats.markdown_rows([r], "o/r")
        self.assertIn("a\\|b\\|c", lines[2])

    def test_unknown_conclusion_shown_raw(self):
        r = _row(conclusion="cancelled")
        lines = ci_stats.markdown_rows([r], "o/r")
        self.assertIn("| cancelled |", lines[2])


class TestStatsLine(unittest.TestCase):
    def test_full_success_with_avg(self):
        s = {"success_rate": 1.0, "runs_success": 3, "runs_completed": 3,
             "avg_duration_min": 3.5, "avg_duration_s": 210.0}
        line = ci_stats.stats_line(s)
        self.assertIn("100% (3/3 tamamlanan run)", line)
        self.assertIn("3.5 dk (210 sn)", line)
        self.assertTrue(line.startswith("**İstatistik (ci_stats.py — otomatik):**"))

    def test_no_completed_runs(self):
        s = {"success_rate": None, "runs_success": 0, "runs_completed": 0,
             "avg_duration_min": None, "avg_duration_s": None}
        line = ci_stats.stats_line(s)
        self.assertIn("— (tamamlanan run yok)", line)
        self.assertIn("— (yeterli tamamlanmış run yok)", line)


class TestStats(unittest.TestCase):
    """stats() hesabı — mock gh verisiyle kenar durumlar sabitlenir."""

    def _mixed(self):
        """2 success + 1 failure (completed) + 1 in_progress."""
        return [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "failure"},
            {"status": "in_progress", "conclusion": None},
        ]

    def test_mixed_success_failure_in_progress(self):
        runs = self._mixed()
        durations = {1: (180, 24), 2: (240, 20), 3: (60, 10), 4: (0, 1)}
        s = ci_stats.stats(runs, durations)
        self.assertEqual(s["runs_total"], 4)
        self.assertEqual(s["runs_completed"], 3)
        self.assertEqual(s["runs_in_progress"], 1)
        self.assertEqual(s["runs_success"], 2)
        self.assertAlmostEqual(s["success_rate"], 2 / 3)
        # in_progress (4) + sıfır süreli (4) ortalamaya katılmaz: (180+240+60)/3
        self.assertAlmostEqual(s["avg_duration_s"], 160.0)
        self.assertAlmostEqual(s["avg_duration_min"], 160.0 / 60)

    def test_zero_duration_run_excluded_from_avg(self):
        """0 sn'lik 1 job'luk hızlı/düşen run ortalamayı çekmez (docstring)."""
        runs = [{"status": "completed", "conclusion": "success"}] * 3
        durations = {"a": (0, 1), "b": (0, 1), "c": (300, 24)}
        s = ci_stats.stats(runs, durations)
        self.assertEqual(s["avg_duration_s"], 300.0)
        self.assertAlmostEqual(s["avg_duration_min"], 5.0)
        self.assertEqual(s["success_rate"], 1.0)  # 0 süreli run yine başarı sayılır

    def test_none_duration_excluded_from_avg(self):
        """gh job zamanlarını doldurmamışsa (None) ortalama onu görmez."""
        runs = [{"status": "completed", "conclusion": "success"}] * 2
        durations = {"a": (None, 20), "b": (120, 24)}
        s = ci_stats.stats(runs, durations)
        self.assertEqual(s["avg_duration_s"], 120.0)

    def test_all_zero_or_none_avg_is_none(self):
        runs = [{"status": "completed", "conclusion": "success"}] * 2
        durations = {"a": (None, 1), "b": (0, 1)}
        s = ci_stats.stats(runs, durations)
        self.assertIsNone(s["avg_duration_s"])
        self.assertIsNone(s["avg_duration_min"])

    def test_no_completed_runs(self):
        runs = [{"status": "in_progress", "conclusion": None}] * 2
        s = ci_stats.stats(runs, {})
        self.assertEqual(s["runs_total"], 2)
        self.assertEqual(s["runs_in_progress"], 2)
        self.assertIsNone(s["success_rate"])
        self.assertIsNone(s["avg_duration_s"])

    def test_empty_durations(self):
        runs = [{"status": "completed", "conclusion": "success"}]
        s = ci_stats.stats(runs, {})
        self.assertEqual(s["success_rate"], 1.0)
        self.assertIsNone(s["avg_duration_s"])
        self.assertIsNone(s["avg_duration_min"])


class TestUpdateDocBlock(unittest.TestCase):
    def test_block_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "PRE_PUSH_DENETIM_RAPORU.md")
            doc.write_text(_DOC, encoding="utf-8")
            table = "\n".join(ci_stats.markdown_rows([_row()], "o/r"))
            stat = ci_stats.stats_line(
                {"success_rate": 1.0, "runs_success": 1, "runs_completed": 1,
                 "avg_duration_min": 3.0, "avg_duration_s": 180.0})
            ci_stats.update_doc_block(str(doc), table, stat)
            text = doc.read_text(encoding="utf-8")
            self.assertIn("| 1 | [111](https://github.com/o/r/actions/runs/111) |", text)
            self.assertNotIn("[999]", text)            # eski tablo satırı gitti
            self.assertIn("**İstatistik (ci_stats.py — otomatik):**", text)
            # Kırılım analizi paragrafı bitiş işaretinden SONRA kalır (elle yazılır)
            self.assertIn("**Kırılım analizi (özet):** eski açıklama.", text)
            self.assertIn("## 10. Sonraki bölüm", text)  # sonrası korunur

    def test_missing_table_header_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "doc.md")
            doc.write_text("## 9. Başlık\n\n**Kırılım analizi**\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ci_stats.update_doc_block(str(doc), "x", "y")
            self.assertEqual(doc.read_text(encoding="utf-8"),
                             "## 9. Başlık\n\n**Kırılım analizi**\n")

    def test_missing_end_marker_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "doc.md")
            doc.write_text(_DOC.replace("**Kırılım analizi", "**Başka bölüm**"),
                           encoding="utf-8")
            with self.assertRaises(ValueError):
                ci_stats.update_doc_block(str(doc), "x", "y")


class TestMainE2E(unittest.TestCase):
    _RUNS = [
        {"databaseId": 111, "status": "completed", "conclusion": "success",
         "createdAt": "2026-08-26T10:00:00Z", "headBranch": "main",
         "displayTitle": "ci_stats §9 bağlantısı"},
        {"databaseId": 222, "status": "completed", "conclusion": "failure",
         "createdAt": "2026-08-25T09:00:00Z", "headBranch": "main",
         "displayTitle": "eski kırık run"},
    ]

    @contextmanager
    def _patch(self):
        def _dur(repo, rid):
            if rid == 111:
                return (180, 24)
            return (240, 20)
        with mock.patch.object(ci_stats, "get_repo", return_value="o/r") as p1, \
                mock.patch.object(ci_stats, "list_runs",
                                  return_value=self._RUNS) as p2, \
                mock.patch.object(ci_stats, "run_duration",
                                  side_effect=_dur) as p3:
            yield p1, p2, p3

    def test_update_doc_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "PRE_PUSH_DENETIM_RAPORU.md")
            doc.write_text(_DOC, encoding="utf-8")
            with self._patch() as (p1, p2, p3):
                rc = ci_stats.main(["--update-doc", str(doc)])
            self.assertEqual(rc, 0)
            text = doc.read_text(encoding="utf-8")
            self.assertIn("| 1 | [111](https://github.com/o/r/actions/runs/111) |", text)
            self.assertIn("| 2 | [222](https://github.com/o/r/actions/runs/222) |", text)
            self.assertNotIn("[999]", text)
            self.assertIn("50% (1/2 tamamlanan run)", text)
            self.assertIn("3.5 dk (210 sn)", text)

    def test_update_doc_limit_defaults_to_10(self):
        # --limit verilmediğinde §9 sözleşmesi gereği 10 run istenir.
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "doc.md")
            doc.write_text(_DOC, encoding="utf-8")
            with self._patch() as (p1, p2, p3):
                rc = ci_stats.main(["--update-doc", str(doc)])
            self.assertEqual(rc, 0)
            self.assertEqual(p2.call_args[0][2], 10)

    def test_markdown_output_captured(self):
        import io
        buf = io.StringIO()
        with self._patch() as (p1, p2, p3), mock.patch("sys.stdout", buf):
            rc = ci_stats.main(["--markdown"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn(ci_stats.TABLE_HEADER, out)
        self.assertIn("✅ success", out)
        self.assertIn("**İstatistik (ci_stats.py — otomatik):**", out)
        self.assertIn("50% (1/2 tamamlanan run)", out)

    def test_update_doc_missing_block_returns_one(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td, "doc.md")
            doc.write_text("## 9. Başlık yok tablo\n", encoding="utf-8")
            with self._patch() as (p1, p2, p3):
                rc = ci_stats.main(["--update-doc", str(doc)])
            self.assertEqual(rc, 1)
            self.assertEqual(doc.read_text(encoding="utf-8"),
                             "## 9. Başlık yok tablo\n")


if __name__ == "__main__":
    unittest.main()
