#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_review_freshness.py regresyon testleri — REVIEW taze + sidecar kapısı.

PASS yolu + fail-closed senaryoları:
- Gerçek repo üzerinde PASS (REVIEW tazeliği + sidecar hash eşleşmesi).
- Kaynak manuscripts'ten biri REVIEW'den daha yeni → stale_source P0.
- Sidecar hash uyuşmazlık → sidecar_mismatch P0.
- Sidecar boş / format hatası → sidecar_parse_error P0.
- Sidecar veya REVIEW eksik → missing P0.
- mtime atribüsü + CLI --json şekli.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_review_freshness as crf  # noqa: E402


def _h(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Fixture:
    """Minimal REVIEW quad (revised, original, review, sidecar) — temp dir üzerinde."""

    def __init__(self, td: pathlib.Path):
        self.td = td
        self.revised = td / "ingiliz_empirizmi_v3.pdf"
        self.original = td / "original_manuscript.pdf"
        self.review = td / "Stoic_Hume_Review_Compilation_2026-08-17.pdf"
        for p in (self.revised, self.original, self.review):
            p.write_bytes(b"%PDF-1.7 " + p.name.encode() + b"\n" + b"x" * 100)
        base = 1_700_000_000_000_000_000
        self.base = base
        os.utime(self.original, ns=(base, base))
        os.utime(self.revised, ns=(base + 1_000, base + 1_000))
        os.utime(self.review, ns=(base + 2_000, base + 2_000))
        self.sidecar = self.review.with_suffix(self.review.suffix + ".sha256")
        self.sidecar.write_text(f"{_h(self.review)}  {self.review.name}\n", encoding="utf-8")

    def stale_revised(self):
        os.utime(self.revised, ns=(self.base + 5_000, self.base + 5_000))

    def stale_original(self):
        os.utime(self.original, ns=(self.base + 5_000, self.base + 5_000))

    def corrupt_sidecar_hash(self):
        self.sidecar.write_text("0" * 64 + f"  {self.review.name}\n", encoding="utf-8")

    def empty_sidecar(self):
        self.sidecar.write_text("", encoding="utf-8")

    def remove_sidecar(self):
        self.sidecar.unlink(missing_ok=True)

    def check(self):
        return crf.check(self.review, self.revised, self.original, sidecar=self.sidecar)


class TestFixtureParity(unittest.TestCase):
    def test_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            ok, findings, meta = fx.check()
            self.assertTrue(ok, findings)
            self.assertEqual(meta["count"], 0)


class TestRealReview(unittest.TestCase):
    def test_real_repo_passes(self):
        ok, findings, meta = crf.check()
        self.assertTrue(ok, findings)
        self.assertEqual(meta["count"], 0)
        self.assertTrue(meta["review_exists"])
        self.assertTrue(meta["sidecar_exists"])
        self.assertEqual(len(meta["review_sha256"]), 64)


class TestFreshCloneSkew(unittest.TestCase):
    """Fresh-clone checkout mtime tersliği: git commit zamanı ile çürütülür.

    Gerçek depoda REVIEW, kaynaklardan YENİ commit'li geldiği halde checkout
    mtime'ları ters görünebilir → eski davranış hatalı P0 üretirdi. git commit
    zamanları REVIEW'in daha yeni olduğunu doğruladığında P0 bastırılmalı;
    git bilgisi yoksa mtime kararı fail-closed geçerli kalmalı.
    """

    def test_mtime_skew_suppressed_when_git_confirms_review_newer(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_revised()  # mtime: kaynak > REVIEW
            with mock.patch.object(crf, "_git_commit_time_ns", side_effect=[1, 2]):
                ok, findings, meta = fx.check()
            self.assertTrue(ok, findings)
            self.assertEqual(meta["fresh_clone_skew_ignored"], 1)
            self.assertFalse(any(f["kind"] == "stale_source" for f in findings))

    def test_mtime_skew_p0_when_no_git_info(self):
        # git commit zamanı alınamazsa (None) mtime kararı fail-closed kalır.
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_revised()
            with mock.patch.object(crf, "_git_commit_time_ns", return_value=None):
                ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "stale_source" for f in findings))


class TestStaleSources(unittest.TestCase):
    def test_stale_revised_is_p0(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_revised()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "stale_source" and f["file"] == "revised" for f in findings))
            self.assertTrue(all(f["priority"] == "P0" for f in findings))

    def test_stale_original_is_p0(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_original()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "stale_source" and f["file"] == "original" for f in findings))

    def test_both_stale_yields_two_findings(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_revised()
            fx.stale_original()
            ok, findings, meta = fx.check()
            self.assertFalse(ok)
            stale = [f for f in findings if f["kind"] == "stale_source"]
            self.assertEqual(len(stale), 2)
            self.assertEqual(meta["count"], 2)


class TestSidecar(unittest.TestCase):
    def test_sidecar_mismatch_is_p0(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.corrupt_sidecar_hash()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "sidecar_mismatch" for f in findings))

    def test_empty_sidecar_is_parse_error(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.empty_sidecar()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "sidecar_parse_error" for f in findings))

    def test_missing_sidecar_is_p0(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.remove_sidecar()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "missing" and f["file"] == "sidecar" for f in findings))

    def test_missing_review_is_p0(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.review.unlink()
            ok, findings, _ = fx.check()
            self.assertFalse(ok)
            self.assertTrue(any(f["kind"] == "missing" and f["file"] == "review" for f in findings))

    def test_sidecar_format_with_extra_fields(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            # real sidecar may have trailing name — _parse_sidecar only cares about first hex token
            h = _h(fx.review)
            fx.sidecar.write_text(f"{h}  {fx.review.name}\n# extra comment\n", encoding="utf-8")
            ok, findings, _ = fx.check()
            self.assertTrue(ok, findings)


class TestCli(unittest.TestCase):
    def test_cli_json_shape(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            buf = subprocess.run(
                [sys.executable, str(HERE / "check_review_freshness.py"),
                 "--review", str(fx.review), "--revised", str(fx.revised), "--original", str(fx.original),
                 "--sidecar", str(fx.sidecar), "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(buf.returncode, 0)
            data = json.loads(buf.stdout)
            self.assertTrue(data["ok"])
            self.assertEqual(data["meta"]["count"], 0)
            self.assertEqual(len(data["meta"]["review_sha256"]), 64)

    def test_cli_stale_reports_json_failure(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            fx.stale_revised()
            buf = subprocess.run(
                [sys.executable, str(HERE / "check_review_freshness.py"),
                 "--review", str(fx.review), "--revised", str(fx.revised), "--original", str(fx.original),
                 "--sidecar", str(fx.sidecar), "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(buf.returncode, 0)
            data = json.loads(buf.stdout)
            self.assertFalse(data["ok"])
            self.assertTrue(any(f["kind"] == "stale_source" for f in data["findings"]))

    def test_cli_plain_output(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(pathlib.Path(td))
            buf = subprocess.run(
                [sys.executable, str(HERE / "check_review_freshness.py"),
                 "--review", str(fx.review), "--revised", str(fx.revised), "--original", str(fx.original),
                 "--sidecar", str(fx.sidecar)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(buf.returncode, 0)
            self.assertIn("review freshness: PASS", buf.stdout)


if __name__ == "__main__":
    unittest.main()
