#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_ci_trend.py — gen_ci_trend.py sarmalayıcısının birim testleri.

Sözleşmeler:
  - başarı: ci_stats.main 0 dönerse gen_ci_trend 0 + \"güncellendi\" mesajı
  - advisory: ci_stats.main 1 (gh hatası/doc bloğu yok) → varsayılan exit 0
    + stderr'de UYARI (commit bloke edilmez)
  - --strict: aynı hata → exit 1 (fail-closed)
  - --limit/--doc passthrough'u ci_stats.main argv'sine birebir aktarılır
  - DEFAULT_DOC repo kökü docs/PRE_PUSH_DENETIM_RAPORU.md'yi gösterir
"""
import contextlib
import io
import pathlib
import sys
import unittest
from pathlib import Path
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import gen_ci_trend as g  # noqa: E402


class TestGenCiTrend(unittest.TestCase):
    def test_default_doc_path(self):
        self.assertEqual(
            g.DEFAULT_DOC,
            Path(__file__).resolve().parents[2] / "docs" / "PRE_PUSH_DENETIM_RAPORU.md")

    def test_success_returns_zero_and_prints(self):
        with mock.patch.object(g.ci_stats, "main", return_value=0) as m:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = g.main(["--doc", "x.md"])
        self.assertEqual(rc, 0)
        self.assertIn("güncellendi", buf.getvalue())
        self.assertEqual(m.call_args[0][0], ["--update-doc", "x.md"])

    def test_gh_failure_advisory_returns_zero(self):
        # gh verisi alınamadı → advisory: exit 0, stderr'de UYARI.
        with mock.patch.object(g.ci_stats, "main", return_value=1):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = g.main(["--doc", "x.md"])
        self.assertEqual(rc, 0)
        self.assertIn("UYARI", err.getvalue())
        self.assertIn("güncellenemedi", err.getvalue())

    def test_strict_failure_returns_one(self):
        with mock.patch.object(g.ci_stats, "main", return_value=1):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = g.main(["--doc", "x.md", "--strict"])
        self.assertEqual(rc, 1)
        self.assertIn("UYARI", err.getvalue())

    def test_limit_passthrough(self):
        with mock.patch.object(g.ci_stats, "main", return_value=0) as m, \
                mock.patch("sys.stdout", new=io.StringIO()):
            rc = g.main(["--doc", "x.md", "--limit", "7"])
        self.assertEqual(rc, 0)
        self.assertEqual(m.call_args[0][0],
                         ["--update-doc", "x.md", "--limit", "7"])

    def test_limit_absent_not_passed(self):
        with mock.patch.object(g.ci_stats, "main", return_value=0) as m, \
                mock.patch("sys.stdout", new=io.StringIO()):
            rc = g.main(["--doc", "x.md"])
        self.assertEqual(rc, 0)
        self.assertNotIn("--limit", m.call_args[0][0])

    def test_system_exit_guard(self):
        # ci_stats.main SystemExit fırlatırsa kod yakalanır; fail-closed
        # sözleşmesi gereği --strict → exit 1.
        with mock.patch.object(g.ci_stats, "main", side_effect=SystemExit(3)):
            rc = g.main(["--doc", "x.md", "--strict"])
        self.assertEqual(rc, 1)

    def test_error_detail_relayed(self):
        # ci_stats hata mesajı UYARI'ya eklenir (teşhis).
        def _fail(argv):
            import sys
            sys.stderr.write("HATA: canlı veri çekilemedi (x)")
            return 1
        with mock.patch.object(g.ci_stats, "main", side_effect=_fail):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = g.main(["--doc", "x.md"])
        self.assertEqual(rc, 0)
        self.assertIn("HATA: canlı veri çekilemedi", err.getvalue())


if __name__ == "__main__":
    unittest.main()
