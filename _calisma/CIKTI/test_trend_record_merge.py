#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_trend_record_merge.py — trend kaydı birleştirme koruması.

Kök neden (koşum 35580855610 ve 37297101317): haftalık ölçüm bot dalına
force-push edilirken, dalda main'de olmayan kayıtlar üstüne yazılıyordu.
5 Ekim ölçümü main'e hiç giremedi (PR yetkisi kapalı) ve bir sonraki koşum
onu kalıcı olarak silecekti. Bu testler o kaybın her iki yarısını da
kilitleyecek biçimde yazıldı:
  - dal kaydı taşınır (kayıp yok, sıra korunur)
  - aynı satırlar tekrarlanmaz (churn yok)
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import trend_record_merge as trm  # noqa: E402

RECORD = ROOT / "docs" / "determinism_trend" / "determinism_trend.jsonl"


def rec(date, tag="a"):
    return '{"date": "%s", "gate": "PASS", "platform": "linux", "tag": "%s"}' % (date, tag)


def keyrec(date, platform="linux", family=None, mtime=1, tag="a"):
    row = {"date": date, "gate": "PASS", "platform": platform,
           "source_mtime": mtime, "tag": tag}
    if family is not None:
        row["family"] = family
    return json.dumps(row, sort_keys=True)


class TestMergeLines(unittest.TestCase):
    def test_stranded_branch_record_is_carried(self):
        branch = [rec("2026-09-28"), rec("2026-10-05", "stranded")]
        local = [rec("2026-09-28")]
        merged, carried = trm.merge_lines(branch, local)
        self.assertEqual(carried, [rec("2026-10-05", "stranded")])
        self.assertEqual(merged, branch)

    def test_identical_records_are_not_duplicated(self):
        lines = [rec("2026-09-21"), rec("2026-09-28")]
        merged, carried = trm.merge_lines(lines, list(lines))
        self.assertEqual(carried, [])
        self.assertEqual(merged, lines)

    def test_order_is_chronological_after_merge(self):
        branch = [rec("2026-10-05", "stranded")]
        local = [rec("2026-09-28")]
        merged, _ = trm.merge_lines(branch, local)
        self.assertEqual(merged, [rec("2026-09-28"), rec("2026-10-05", "stranded")])

    def test_duplicate_inside_one_side_is_collapsed(self):
        merged, _ = trm.merge_lines([rec("2026-09-28"), rec("2026-09-28")], [])
        self.assertEqual(merged, [rec("2026-09-28")])


class TestKeyDedupe(unittest.TestCase):
    """Kimlik (date, platform, family); source_mtime kimliğin parçası değil."""

    def test_same_key_different_mtime_is_not_carried(self):
        branch = [keyrec("2026-11-18", mtime=1795032788)]
        local = [keyrec("2026-11-18", mtime=1794999389)]
        merged, carried = trm.merge_lines(branch, local)
        self.assertEqual(carried, [])
        self.assertEqual(merged, local)

    def test_local_wins_even_if_branch_mtime_is_newer(self):
        branch = [keyrec("2026-11-18", mtime=99)]
        local = [keyrec("2026-11-18", mtime=1, tag="current")]
        merged, carried = trm.merge_lines(branch, local)
        self.assertEqual(carried, [])
        self.assertEqual(merged, local)

    def test_branch_only_key_is_carried_once_with_latest_mtime(self):
        branch = [keyrec("2026-10-05", mtime=1),
                  keyrec("2026-10-05", mtime=2)]
        local = [keyrec("2026-10-01", mtime=3)]
        merged, carried = trm.merge_lines(branch, local)
        self.assertEqual(carried, [keyrec("2026-10-05", mtime=2)])
        self.assertEqual(merged, [keyrec("2026-10-01", mtime=3),
                                  keyrec("2026-10-05", mtime=2)])

    def test_family_is_part_of_key(self):
        branch = [keyrec("2026-10-08", family="canvas", mtime=1)]
        local = [keyrec("2026-10-08", family="manuscript", mtime=2)]
        merged, carried = trm.merge_lines(branch, local)
        self.assertEqual(carried, branch)
        self.assertEqual(len(merged), 2)

    def test_missing_or_non_string_family_is_manuscript(self):
        local = [keyrec("2026-11-18", family="manuscript", mtime=1)]
        for family in (None, "", 42):
            branch = [keyrec("2026-11-18", family=family, mtime=2)]
            merged, carried = trm.merge_lines(branch, local)
            self.assertEqual(carried, [], "family=%r ayrı anahtar sayıldı" % (family,))
            self.assertEqual(merged, local)

    def test_invalid_json_fails_closed(self):
        with self.assertRaises(ValueError):
            trm.merge_lines(["bozuk satır"], [])

    def test_missing_date_or_platform_fails_closed(self):
        with self.assertRaises(ValueError):
            trm.merge_lines(['{"gate": "PASS"}'], [])
        with self.assertRaises(ValueError):
            trm.merge_lines(['{"date": "2026-11-18"}'], [])


class TestWriteAtomic(unittest.TestCase):
    def test_write_leaves_no_temp_file(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            target = tmp / "r.jsonl"
            trm.write_atomic(target, [rec("2026-09-28")])
            self.assertEqual(target.read_text(encoding="utf-8").splitlines(),
                             [rec("2026-09-28")])
            self.assertEqual([p.name for p in tmp.iterdir()], ["r.jsonl"])
        finally:
            shutil.rmtree(tmp)


class TestCli(unittest.TestCase):
    def _run(self, branch_lines, local_lines):
        tmp = pathlib.Path(tempfile.mkdtemp())
        branch = tmp / "branch.jsonl"
        target = tmp / "record.jsonl"
        branch.write_text("\n".join(branch_lines) + "\n", encoding="utf-8")
        target.write_text("\n".join(local_lines) + "\n", encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(HERE / "trend_record_merge.py"),
             "--branch-file", str(branch), "--record", str(target)],
            capture_output=True, text=True)
        return out, target, tmp

    def test_cli_merges_and_reports_carried_count(self):
        out, target, tmp = self._run(
            [rec("2026-09-28"), rec("2026-10-05", "stranded")], [rec("2026-09-28")])
        try:
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("tasinan kayit: 1", out.stdout)
            self.assertEqual(len(target.read_text().splitlines()), 2)
        finally:
            shutil.rmtree(tmp)

    def test_cli_is_noop_when_nothing_stranded(self):
        out, target, tmp = self._run([rec("2026-09-28")], [rec("2026-09-28")])
        try:
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.strip(), "0")
        finally:
            shutil.rmtree(tmp)

    def test_cli_does_not_append_same_key_with_different_mtime(self):
        out, target, tmp = self._run(
            [keyrec("2026-11-18", mtime=1795032788)],
            [keyrec("2026-11-18", mtime=1794999389)])
        try:
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.strip(), "0")
            self.assertEqual(target.read_text().splitlines(),
                             [keyrec("2026-11-18", mtime=1794999389)])
        finally:
            shutil.rmtree(tmp)

    def test_cli_fails_closed_on_malformed_record(self):
        out, _target, tmp = self._run(["bozuk satır"], [])
        try:
            self.assertEqual(out.returncode, 1)
            self.assertIn("FAIL:", out.stderr)
        finally:
            shutil.rmtree(tmp)

    def test_cli_tolerates_missing_branch_file(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            target = tmp / "record.jsonl"
            target.write_text(rec("2026-09-28") + "\n", encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(HERE / "trend_record_merge.py"),
                 "--branch-file", str(tmp / "yok.jsonl"), "--record", str(target)],
                capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.strip(), "0")
        finally:
            shutil.rmtree(tmp)


class TestRealRepositoryRecord(unittest.TestCase):
    def test_repo_record_is_sorted_and_unique(self):
        """Gerçek kayıt: sıra + tekilleştirme değişirse merge sessizce bozulur."""
        lines = trm.read_records(RECORD)
        self.assertTrue(lines, "trend kaydı boş — kanıt dosyası kaybolmuş")
        self.assertEqual(lines, sorted(set(lines)),
                         "kayıt sırasız veya tekrarlı: merge çıktısı kronolojik "
                         "olmayı kaybeder")


if __name__ == "__main__":
    unittest.main()
