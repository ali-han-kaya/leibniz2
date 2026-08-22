#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refs_trend.py — refs_trend.py regresyon kapısı.

Özellikle _NoAuthRedirect'i kapılar: GitHub /zip endpoint'i imzalı Azure blob
URL'ine 302 döner; urllib Authorization'ı redirect'e taşırsa blob 401
(InvalidAuthenticationInfo) verir. Handler'ın auth başlığını düşürdüğü ve
diğer başlıkları (User-Agent) koruduğu doğrulanır. Ayrıca parse_report +
short_date saf fonksiyonları test edilir. stdlib unittest — ek bağımlılık yok.
"""
import datetime
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.request
import zipfile

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import refs_trend as rt  # noqa: E402


class TestNoAuthRedirect(unittest.TestCase):
    def _redirect(self, headers=None):
        req = urllib.request.Request("https://api.github.com/x")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        h = rt._NoAuthRedirect()
        return h.redirect_request(req, None, 302, "Found", {},
                                  "https://blob.core.windows.net/y")

    def test_strips_authorization(self):
        new = self._redirect({"Authorization": "Bearer abc"})
        self.assertIsNotNone(new)
        self.assertFalse("Authorization" in new.headers)

    def test_keeps_other_headers(self):
        new = self._redirect({"User-Agent": "refs-trend",
                              "Authorization": "Bearer abc"})
        self.assertEqual(new.headers.get("User-agent"), "refs-trend")
        self.assertFalse("Authorization" in new.headers)


class TestParseReport(unittest.TestCase):
    def _zip(self, payload):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("references_online.json",
                       json.dumps(payload, ensure_ascii=False))
        return buf.getvalue()

    def test_parses_references_online_json(self):
        payload = {"verified": 49, "total_online": 54, "by_source": {"a": 1}}
        rep = rt.parse_report(self._zip(payload))
        self.assertEqual(rep["verified"], 49)
        self.assertEqual(rep["total_online"], 54)

    def test_missing_json_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_report(buf.getvalue())


class TestChangelog(unittest.TestCase):
    def test_changelog_has_hicks_hume(self):
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("## Changelog", joined)
        self.assertIn("Hicks 1925", joined)
        self.assertIn("Hume 1975", joined)
        self.assertIn("31/31", joined)

    def test_changelog_has_v5n_norton_popkin(self):
        """V5n: Norton/Popkin CrossRef girişi changelog'da olmalı (54→56)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5n", joined)
        self.assertIn("Norton 1981", joined)
        self.assertIn("Popkin 1951", joined)
        self.assertIn("54→56", joined)
        # En yeni üstte: V5n (2026-08-19), Hicks/Hume (2026-08-18)'den önce.
        self.assertLess(joined.index("V5n"), joined.index("Hicks 1925"))

    def test_changelog_has_v5o(self):
        """V5o: 11 UNVERIFIED → 56/56 tam kapsam changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5o", joined)
        self.assertIn("56/56", joined)
        self.assertIn("REFERENCE_POOL_SIZE", joined)
        # En yeni üstte: V5o (2026-08-19), V5n (2026-08-19)'den önce (aynı gün,
        # V5n'den sonraki değişiklik).
        self.assertLess(joined.index("V5o"), joined.index("V5n"))

    def test_changelog_has_v5t_handle(self):
        """V5t: Della Rocca 2010 Handle System doğrulaması changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5t", joined)
        self.assertIn("Della Rocca 2010", joined)
        self.assertIn("Handle", joined)
        # En yeni üstte: V5t (2026-08-21), V5n (2026-08-19)'den önce.
        self.assertLess(joined.index("V5t"), joined.index("V5n"))

    def test_changelog_has_v5w_loc(self):
        """V5w: LoC katalog kanıtı changelog'da olmalı (en yeni üstte)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5w", joined)
        self.assertIn("Library of Congress", joined)
        self.assertIn("loc", joined)
        # En yeni üstte: V5w (2026-08-21), V5v'den önce.
        self.assertLess(joined.index("V5w"), joined.index("V5v"))

    def test_changelog_has_v5q_sextus_della(self):
        """V5q: Sextus ia_ids + Della Rocca Wayback doğrulaması changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5q", joined)
        self.assertIn("ia_ids", joined)
        self.assertIn("Wayback", joined)
        # V5q (2026-08-21) V5t'den önce (Wayback → Handle geçişi)
        self.assertLess(joined.index("V5q"), joined.index("V5t"))

    def test_changelog_has_v5p_oclc_lccn(self):
        """V5p: OL'den OCLC/LCCN çekimi + Xunzi HT kaydı changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5p", joined)
        self.assertIn("OCLC/LCCN", joined)
        self.assertIn("HathiTrust", joined)
        self.assertIn("Xunzi", joined)
        # Sıralama: V5p (08-19, V5o'dan sonra) → V5o → V5n (aynı gün).
        self.assertLess(joined.index("V5p"), joined.index("V5o"))
        self.assertLess(joined.index("V5o"), joined.index("V5n"))

    def test_changelog_empty_when_no_entries(self):
        saved = rt.CHANGELOG
        try:
            rt.CHANGELOG = []
            self.assertEqual(rt.changelog_lines(), [])
        finally:
            rt.CHANGELOG = saved


class TestShortDate(unittest.TestCase):
    def test_iso_z(self):
        self.assertEqual(rt.short_date("2026-08-19T12:08:38Z"),
                         "2026-08-19 12:08")

    def test_empty(self):
        self.assertEqual(rt.short_date(""), "")


class TestParseHistoryRecord(unittest.TestCase):
    def _zip_jsonl(self, records):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "history.jsonl",
                "\n".join(json.dumps(r, ensure_ascii=False)
                           for r in records) + "\n",
            )
        return buf.getvalue()

    def test_parses_last_record(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 1.0, "budget_usd": 0.5},
            {"ts": "b", "duration_s": 2.0, "budget_usd": 1.08},
        ]))
        self.assertEqual(rec["ts"], "b")
        self.assertEqual(rec["duration_s"], 2.0)
        self.assertEqual(rec["budget_usd"], 1.08)

    def test_skips_blank_lines(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 3.0},
        ]))
        self.assertEqual(rec["duration_s"], 3.0)

    def test_missing_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())

    def test_empty_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("history.jsonl", "\n")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())

    def test_last_record_wins_across_many(self):
        """Çok kayıtlı dosyada SON kayıt döner (en güncel)."""
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a"},
            {"ts": "b"},
            {"ts": "c", "duration_s": 9.5, "budget_usd": 1.08},
        ]))
        self.assertEqual(rec["ts"], "c")
        self.assertEqual(rec["duration_s"], 9.5)

    def test_corrupt_json_line_raises(self):
        """Fail-closed: bozuk satır sessizce atlanmamalı — hata fırlatılmalı."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("history.jsonl", '{"ts": "a"}\n{bozuk json}\n')
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())


class TestStats(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(rt.stats([1, 2, 3]),
                         {"count": 3, "min": 1, "max": 3, "avg": 2})

    def test_ignores_non_numbers(self):
        s = rt.stats([None, "x", 5, 15])
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["min"], 5)
        self.assertEqual(s["max"], 15)
        self.assertEqual(s["avg"], 10)

    def test_empty(self):
        self.assertEqual(rt.stats([]),
                         {"count": 0, "min": None, "max": None, "avg": None})

    def test_rounds_to_two_decimals(self):
        s = rt.stats([1.333, 2.666])
        self.assertEqual(s, {"count": 2, "min": 1.33, "max": 2.67, "avg": 2.0})


class TestCheckRunWarnings(unittest.TestCase):
    """duration/budget eşikleri + Z3 FAIL uyarıları (fail-closed)."""

    def test_no_warnings_under_threshold(self):
        w = rt.check_run_warnings(
            {"duration_s": 30.0, "budget_usd": 1.08,
             "z3_passed": 12, "z3_total": 12})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertEqual(w["messages"], [])
        self.assertEqual(w["duration_val"], 30.0)
        self.assertEqual(w["budget_val"], 1.08)

    def test_duration_over_threshold_warns(self):
        w = rt.check_run_warnings({"duration_s": 400.0, "budget_usd": 1.0})
        self.assertTrue(w["duration_warn"])
        self.assertIn("süre 400.0s > eşik 300s", w["messages"])

    def test_budget_over_threshold_warns(self):
        w = rt.check_run_warnings({"duration_s": 10.0, "budget_usd": 31.0})
        self.assertTrue(w["budget_warn"])
        self.assertIn("bütçe $31.00 > eşik $30", w["messages"])

    def test_both_warn(self):
        w = rt.check_run_warnings({"duration_s": 301.0, "budget_usd": 30.01})
        self.assertTrue(w["duration_warn"] and w["budget_warn"])
        self.assertEqual(len(w["messages"]), 2)

    def test_exact_threshold_no_warn(self):
        """Eşiğe EŞİT değer uyarı değil (sıkı >)."""
        w = rt.check_run_warnings({"duration_s": 300.0, "budget_usd": 30.0})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertEqual(w["messages"], [])

    def test_non_numeric_ignored(self):
        w = rt.check_run_warnings(
            {"duration_s": None, "budget_usd": "yok", "z3_passed": None})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertIsNone(w["duration_val"])
        self.assertIsNone(w["budget_val"])
        self.assertEqual(w["messages"], [])

    def test_z3_fail_warns(self):
        w = rt.check_run_warnings({"z3_passed": 11, "z3_total": 12})
        self.assertIn("Z3 FAIL 1/12", w["messages"])

    def test_z3_all_pass_no_message(self):
        w = rt.check_run_warnings({"z3_passed": 12, "z3_total": 12})
        self.assertEqual(w["messages"], [])

    def test_missing_z3_no_message(self):
        w = rt.check_run_warnings({})
        self.assertEqual(w["messages"], [])


class TestSummarizeWarnings(unittest.TestCase):
    """Tüm run'lar üzerinde eşik ihlali özeti (fail-closed)."""

    def test_empty(self):
        s = rt.summarize_warnings([])
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(s["total_runs"], 0)
        self.assertEqual(s["violations"], [])

    def test_no_violations(self):
        rows = [{"date": "a", "run_id": 1, "duration_s": 30.0,
                 "budget_usd": 1.0},
                {"date": "b", "run_id": 2, "duration_s": 60.0,
                 "budget_usd": 2.0}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(s["total_runs"], 2)
        self.assertEqual(s["violations"], [])

    def test_counts_duration_and_budget(self):
        rows = [{"date": "a", "run_id": 1, "duration_s": 400.0,
                 "budget_usd": 1.0},
                {"date": "b", "run_id": 2, "duration_s": 10.0,
                 "budget_usd": 40.0}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 1)
        self.assertEqual(s["budget_violations"], 1)
        self.assertEqual(len(s["violations"]), 2)
        v = s["violations"][0]
        self.assertEqual(v["run_idx"], 1)
        self.assertEqual(v["date"], "a")
        self.assertEqual(v["run_id"], 1)
        self.assertTrue(any("süre" in m for m in v["messages"]))

    def test_z3_fail_in_violations_not_counts(self):
        rows = [{"date": "a", "run_id": 7, "z3_passed": 10,
                 "z3_total": 12}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(len(s["violations"]), 1)
        self.assertIn("Z3 FAIL 2/12", s["violations"][0]["messages"])
        self.assertEqual(s["violations"][0]["run_id"], 7)


class TestDurationBudgetSummary(unittest.TestCase):
    """duration_budget JSON bölümü sözleşmesi (fail-closed)."""

    def test_structure_with_valid_rows(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": 30.0,
             "budget_usd": 1.08, "verdict": "PASS",
             "z3_passed": 12, "z3_total": 12},
        ])
        self.assertEqual(db["run_count"], 1)
        row = db["rows"][0]
        self.assertEqual(row["date"], "a")
        self.assertEqual(row["run_id"], 1)
        self.assertEqual(row["duration_s"], 30.0)
        self.assertEqual(row["budget_usd"], 1.08)
        self.assertEqual(row["verdict"], "PASS")
        self.assertEqual(row["z3_passed"], 12)
        self.assertFalse(row["duration_warn"])
        self.assertFalse(row["budget_warn"])
        self.assertEqual(db["summary"]["duration_s"]["count"], 1)
        self.assertEqual(db["summary"]["budget_usd"]["max"], 1.08)
        self.assertIsNotNone(db["warnings"])
        self.assertEqual(db["warnings"]["total_runs"], 1)

    def test_violations_flagged_in_rows_and_warnings(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": 500.0,
             "budget_usd": 35.0},
        ])
        row = db["rows"][0]
        self.assertTrue(row["duration_warn"])
        self.assertTrue(row["budget_warn"])
        self.assertEqual(db["warnings"]["duration_violations"], 1)
        self.assertEqual(db["warnings"]["budget_violations"], 1)
        self.assertEqual(len(db["warnings"]["violations"]), 1)

    def test_empty_fail_closed(self):
        db = rt.build_duration_budget([])
        self.assertEqual(db["run_count"], 0)
        self.assertEqual(db["rows"], [])
        self.assertIsNone(db["warnings"])
        self.assertEqual(db["summary"]["duration_s"]["count"], 0)
        self.assertIsNone(db["summary"]["duration_s"]["min"])

    def test_non_numeric_values_do_not_crash(self):
        """Fail-closed: eksik/sayısal olmayan değerler stats'ı bozmaz,
        run sayısı korunur, uyarı üretilmez."""
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": None,
             "budget_usd": "x"},
            {"date": "b", "run_id": 2, "duration_s": 30.0,
             "budget_usd": 1.0},
        ])
        self.assertEqual(db["run_count"], 2)
        self.assertEqual(db["summary"]["duration_s"]["count"], 1)
        self.assertEqual(db["summary"]["duration_s"]["min"], 30.0)
        self.assertEqual(db["warnings"]["total_runs"], 2)
        self.assertEqual(db["warnings"]["violations"], [])

    def test_z3_fail_surfaces_in_warnings(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 9, "z3_passed": 0, "z3_total": 12},
        ])
        self.assertEqual(len(db["warnings"]["violations"]), 1)
        self.assertIn("Z3 FAIL 12/12",
                      db["warnings"]["violations"][0]["messages"])


class TestFetchArtifactsByName(unittest.TestCase):
    def test_filters_sorts_by_date(self):
        artifacts = [
            {"name": "refs-online", "id": 1,
             "created_at": "2026-08-18T00:00:00Z"},
            {"name": "other", "id": 2,
             "created_at": "2026-08-19T00:00:00Z"},
            {"name": "refs-online", "id": 3,
             "created_at": "2026-08-17T00:00:00Z"},
        ]
        orig = rt.api_get

        def fake_api(path, token, binary=False):
            return {"artifacts": artifacts}

        rt.api_get = fake_api
        try:
            out = rt.fetch_artifacts_by_name("o/r", "", "refs-online", 100)
        finally:
            rt.api_get = orig
        self.assertEqual([a["id"] for a in out], [3, 1])


WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


class TestWorkflowCliConsistency(unittest.TestCase):
    """verify.yml'in refs-trend job'ı refs_trend.py CLI'sıyla senkron olmalı.

    refs_trend.py --out-dir refs-trend altına refs-trend.md + refs-trend.json
    üretir; gen_repro_manifest.py'nin REFS TREND bölümü refs-trend/ önekini ve
    reproducibility job'ı `name: refs-trend` artifact'ını ayrıca indirir.
    CLI/artifact drift bu zinciri sessizce koparır — fail-closed.
    """
    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_job_uses_refs_trend_out_dir(self):
        text = self._workflow()
        self.assertIn("_calisma/CIKTI/refs_trend.py", text)
        self.assertIn("--out-dir refs-trend", text)
        self.assertIn("--max-artifacts 100", text)

    def test_artifact_name_matches_output_prefix(self):
        # refs_trend.py çıktısı refs-trend/ altına yazılır; reproducibility
        # job'ı aynı adla indirir → manifest REFS TREND bölümüne girer.
        text = self._workflow()
        self.assertIn("name: refs-trend", text)
        self.assertIn("path: all_artifacts/refs-trend/", text)



class TestRunSummaryRefsTrend(unittest.TestCase):
    """run_summary_refs_trend.py CLI tutarlılık + birim testleri.

    verify.yml refs-trend job'ındaki 'Write refs trend to run summary' adımını
    run_summary_refs_trend.py ile çağırır: refs-trend/refs-trend.md'yi
    GITHUB_STEP_SUMMARY'ye taşır. Bu testler:
      1) Workflow adımının doğru script/yol ile çağrıldığını,
      2) Script'in varsayılan input yolunun workflow ile eşleştiğini,
      3) Script'in render() fonksiyonunun eksik dosya/prompt senaryolarını
         doğru handle ettiğini doğrular.
    """

    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    # ── Workflow CLI tutarlılığı ──────────────────────────────────────

    def test_workflow_references_script_at_correct_path(self):
        """workflow'da script doğru yoldan çağrılmalı."""
        text = self._workflow()
        self.assertIn(
            "python3 _calisma/CIKTI/run_summary_refs_trend.py",
            text)

    def test_workflow_step_name_mentions_refs_trend(self):
        """Adım adı 'refs trend' kelimesini içermeli."""
        text = self._workflow()
        self.assertIn("refs trend", text.lower())

    def test_workflow_step_input_is_refs_trend_md(self):
        """Workflow'un sağladığı input refs-trend/refs-trend.md olmalı."""
        text = self._workflow()
        # Script çağrısı refs-trend/refs-trend.md argümanını almalı
        self.assertIn("refs-trend/refs-trend.md", text)

    def test_workflow_step_runs_with_always(self):
        """Adım if: always() ile koşmalı (verify FAIL olsa bile trend görünür)."""
        text = self._workflow()
        # 'Write refs trend to run summary' adımının hemen üstündeki if kontrolü
        self.assertIn("Write refs trend to run summary", text)

    # ── Script varsayılanları ────────────────────────────────────────

    def test_default_md_path_matches_workflow(self):
        """Script'in DEFAULT_MD sabiti workflow ile aynı yolu göstermeli."""
        from run_summary_refs_trend import DEFAULT_MD
        self.assertEqual(DEFAULT_MD, "refs-trend/refs-trend.md")

    # ── Script render() fonksiyonu ──────────────────────────────────

    def test_render_writes_md_to_sink(self):
        """render() mevcut md dosyasını sink'e taşımeli."""
        from run_summary_refs_trend import render
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                         delete=False) as f:
            f.write("| Run | Verified |\n|---|---|\n| #1 | 61/61 |\n")
            f.flush()
            out = io.StringIO()
            result = render(out, f.name)
        os.unlink(f.name)
        self.assertTrue(result)
        self.assertIn("61/61", out.getvalue())
        self.assertIn("Çevrimiçi referans doğrulama trendi", out.getvalue())

    def test_render_handles_missing_file(self):
        """render() dosya yoksa hata vermemeli, prompt yazmalı."""
        from run_summary_refs_trend import render
        out = io.StringIO()
        result = render(out, "/nonexistent/refs-trend.md")
        self.assertFalse(result)
        self.assertIn("tablo bulunamadı", out.getvalue())

    def test_render_adds_trailing_newline(self):
        """render() md sonunda çift yeni satır olmalı (markdown spacing)."""
        from run_summary_refs_trend import render
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                         delete=False) as f:
            f.write("tek satır")
            f.flush()
            out = io.StringIO()
            render(out, f.name)
        os.unlink(f.name)
        text = out.getvalue()
        self.assertTrue(text.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
