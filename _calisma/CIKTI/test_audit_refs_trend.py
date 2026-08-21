#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_audit_refs_trend.py — audit_refs_trend.py karşılaştırma mantığı.

Saf fonksiyonları (load_trend, compare_row, audit) deterministik doğrular:
birebir eşleşme, sahte satır (kaynak yok), sayı drift'i, by_source drift'i,
kapsam eksikliği (kaynakta var trendde yok), run_id yerine date anahtarı.
Canlı ağ YOK — refs_trend.fetch_refs_online_artifacts/api_get mock'lanır.

stdlib unittest — ek bağımlılık yok.
"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import audit_refs_trend as art  # noqa: E402


DEFAULT_BY_SOURCE = {"openlibrary": 26, "crossref": 6}


def _source(verified=61, total=61, unverified=0, mismatch=0,
            by_source=DEFAULT_BY_SOURCE):
    return {
        "total_online": total,
        "verified": verified,
        "unverified": unverified,
        "mismatch": mismatch,
        "by_source": dict(by_source),
    }


def _row(run_id="111", verified=61, total=61, unverified=0, mismatch=0,
         by_source=DEFAULT_BY_SOURCE, date="2026-08-20T10:00:00+00:00"):
    return {
        "date": date,
        "run_id": run_id,
        "total_online": total,
        "verified": verified,
        "unverified": unverified,
        "mismatch": mismatch,
        "by_source": dict(by_source),
    }


class TestCompareRow(unittest.TestCase):
    def test_identical_row_no_findings(self):
        row = _row()
        src = _source()
        self.assertEqual(art.compare_row(row, src), [])

    def test_count_drift_detected(self):
        row = _row(verified=49, total=54)
        src = _source(verified=61, total=61)
        findings = art.compare_row(row, src)
        kinds = {f["kind"] for f in findings}
        self.assertIn("count", kinds)
        # verified + total_online uyuşmaz → 2 bulgu
        self.assertEqual(sum(1 for f in findings if f["kind"] == "count"), 2)
        self.assertIn("verified", {f["field"] for f in findings})

    def test_by_source_drift_detected(self):
        row = _row(by_source={"openlibrary": 26, "crossref": 5})
        src = _source(by_source={"openlibrary": 26, "crossref": 6})
        findings = art.compare_row(row, src)
        self.assertTrue(any(f["kind"] == "by_source" for f in findings))

    def test_by_source_none_treated_as_empty(self):
        # row'da by_source yok (None) + kaynakta boş {} → ikisi de {} → uyum.
        row = _row()
        row["by_source"] = None
        src = _source(by_source={})
        findings = art.compare_row(row, src)
        self.assertFalse(any(f["kind"] == "by_source" for f in findings))

    def test_by_source_none_vs_nonempty_fails(self):
        # row'da by_source yok ama kaynakta dolu → uyumsuz (drift).
        row = _row()
        row["by_source"] = None
        src = _source(by_source={"openlibrary": 26})
        findings = art.compare_row(row, src)
        self.assertTrue(any(f["kind"] == "by_source" for f in findings))

    def test_unverified_and_mismatch_checked(self):
        row = _row(unverified=5, mismatch=0)
        src = _source(unverified=0, mismatch=1)
        findings = art.compare_row(row, src)
        fields = {f["field"] for f in findings}
        self.assertIn("unverified", fields)
        self.assertIn("mismatch", fields)


class TestAudit(unittest.TestCase):
    def test_full_match_pass(self):
        trend = {"rows": [_row("111"), _row("222")]}
        src = {"111": _source(), "222": _source()}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["ok"])
        self.assertEqual(r["findings"], [])
        self.assertEqual(r["coverage"]["matched"], 2)
        self.assertEqual(r["extra_sources"], [])

    def test_fabricated_row_fails(self):
        # Trend'de run 333 var ama kaynakta yok → sahte satır.
        trend = {"rows": [_row("111"), _row("333")]}
        src = {"111": _source()}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing_sources"], ["333"])

    def test_stale_trend_fails_missing_row(self):
        # Kaynakta 222 var, trendde yok → trend bayat.
        trend = {"rows": [_row("111")]}
        src = {"111": _source(), "222": _source()}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["extra_sources"], ["222"])
        self.assertEqual(r["coverage"]["missing_in_trend"], ["222"])

    def test_count_drift_fails(self):
        trend = {"rows": [_row("111", verified=49, total=54)]}
        src = {"111": _source(verified=61, total=61)}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(any(f["kind"] == "count" for f in r["findings"]))

    def test_by_source_drift_fails(self):
        trend = {"rows": [_row("111", by_source={"a": 1})]}
        src = {"111": _source(by_source={"b": 1})}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(any(f["kind"] == "by_source" for f in r["findings"]))

    def test_date_keyed_rows_match(self):
        # run_id yoksa date anahtarı kullanılır — aynı date kaynakla eşleşir.
        trend = {"rows": [_row(run_id=None, date="2026-08-20T10:00:00+00:00")]}
        src = {"2026-08-20T10:00:00+00:00": _source()}
        r = art.audit(trend, src)
        self.assertEqual(r["verdict"], "PASS")

    def test_empty_trend_and_sources_pass(self):
        r = art.audit({"rows": []}, {})
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["ok"])
        self.assertEqual(r["coverage"]["trend_rows"], 0)

    def test_empty_rows_but_sources_fail(self):
        # Trend boş ama kaynak var → bayat trend.
        r = art.audit({"rows": []}, {"111": _source()})
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["extra_sources"], ["111"])


class TestLoadTrend(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(RuntimeError):
            art.load_trend("/nonexistent/refs-trend.json")

    def test_invalid_json_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as tf:
            tf.write("{not json")
            path = tf.name
        try:
            with self.assertRaises(RuntimeError):
                art.load_trend(path)
        finally:
            pathlib.Path(path).unlink()

    def test_valid_json_loaded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as tf:
            json.dump({"rows": [], "generated": "x"}, tf)
            path = tf.name
        try:
            trend = art.load_trend(path)
            self.assertEqual(trend["generated"], "x")
        finally:
            pathlib.Path(path).unlink()


class TestMain(unittest.TestCase):
    """main() çıkış kodları: mock'lu API ile (canlı ağ yok)."""

    def _run_main(self, trend_rows, source_reports, json_out=False):
        """trend.json'i geçici dosyaya yazar, API'yi mock'lar, main() koşar."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as tf:
            json.dump({"rows": trend_rows}, tf)
            trend_path = tf.name
        try:
            artifacts = []
            for rid in source_reports:
                artifacts.append({
                    "id": int(rid) if str(rid).isdigit() else abs(hash(rid)) % 10**6,
                    "workflow_run": {"id": rid},
                    "created_at": "2026-08-20T10:00:00Z",
                })

            def fake_fetch(repo, token, max_artifacts):
                return artifacts

            def fake_api(path, token, binary=False):
                # path .../artifacts/{id}/zip biçiminde
                aid = int(path.split("/")[-2])
                rid = next(r for r in source_reports
                           if (int(r) if str(r).isdigit() else
                               abs(hash(r)) % 10**6) == aid)
                return _zip_blob(source_reports[rid])

            with mock.patch.object(art.rt, "fetch_refs_online_artifacts",
                                   side_effect=fake_fetch), \
                    mock.patch.object(art.rt, "api_get", side_effect=fake_api), \
                    mock.patch.object(sys, "stdout", new=io.StringIO()):
                rc = art.main(["--repo", "owner/name",
                               "--trend-json", trend_path] +
                              (["--json"] if json_out else []))
            return rc
        finally:
            pathlib.Path(trend_path).unlink()

    def test_pass_returns_0(self):
        rc = self._run_main([_row("111")], {"111": _source()})
        self.assertEqual(rc, 0)

    def test_drift_returns_1(self):
        rc = self._run_main([_row("111", verified=49)], {"111": _source()})
        self.assertEqual(rc, 1)

    def test_fabricated_returns_1(self):
        rc = self._run_main([_row("111"), _row("999")], {"111": _source()})
        self.assertEqual(rc, 1)

    def test_missing_trend_returns_2(self):
        with mock.patch.object(sys, "stderr", new=io.StringIO()):
            rc = art.main(["--repo", "owner/name",
                           "--trend-json", "/nonexistent/x.json"])
        self.assertEqual(rc, 2)

    def test_json_output_has_verdict(self):
        buf = io.StringIO()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as tf:
            json.dump({"rows": [_row("111")]}, tf)
            trend_path = tf.name
        try:
            artifacts = [{"id": 1, "workflow_run": {"id": "111"},
                          "created_at": "2026-08-20T10:00:00Z"}]
            with mock.patch.object(art.rt, "fetch_refs_online_artifacts",
                                   return_value=artifacts), \
                    mock.patch.object(art.rt, "api_get",
                                      return_value=_zip_blob(_source())), \
                    mock.patch.object(sys, "stdout", new=buf):
                rc = art.main(["--repo", "owner/name",
                               "--trend-json", trend_path, "--json"])
            self.assertEqual(rc, 0)
            d = json.loads(buf.getvalue())
            self.assertEqual(d["verdict"], "PASS")
            self.assertEqual(d["rows_checked"], 1)
        finally:
            pathlib.Path(trend_path).unlink()


def _zip_blob(payload):
    """references_online.json içeren zip bytes'i üretir (parse_report için)."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("references_online.json",
                   json.dumps(payload, ensure_ascii=False))
    return buf.getvalue()


if __name__ == "__main__":
    unittest.main()
