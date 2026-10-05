#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_deploy_evidence.py — kanit-defteri bayatlık kapısının sözleşme testleri.

Kapsam: dört denetim ekseni (yapı / HEAD kapsamı / yaş / koşum gerçekliği) ve
CLI çıkış kodları. Canlı ağ YOK — `fetch_run` ve `git` sahte (fake) nesnelerle
değiştirilir; böylece testler hangi koşulun hangi ihlali ürettiğini izole eder.
Repo'nun GERÇEK defteri de yapısal denetime sokulur (bugün yeşil olmalı —
aksi halde kapi işlevsiz kalmış demektir).
"""
import datetime as dt
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import deploy_evidence as de  # noqa: E402

LEDGER = ROOT / "docs" / "DEPLOY_EVIDENCE.md"
LINK = "https://github.com/o/r/actions/runs/%s"


def ledger_text(rows):
    """Test fixture'ı: satırlar (tarih, head, [(conclusion, run_id), ...]).

    Hucre degerinin string olmasi halinde RAW yazilir — bozuk hucre bicimini
    test etmek icin (orn. "[success] #1", "yesil") fixture kendi hucresini
    kurabilir.
    """
    out = ["## Kanit-defteri", "",
           "| " + " | ".join(de.EXPECTED_HEADER) + " |",
           "|" + "---|" * len(de.EXPECTED_HEADER)]
    for date, head, runs in rows:
        cells = [date, head]
        for run in runs:
            if isinstance(run, str):
                cells.append(run)
            else:
                lbl, rid = run
                cells.append("[%s #%s](%s)" % (lbl, rid, LINK % rid))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def real_main_short():
    """Yerel main'in kisa sha'sı (yoksa test atlanır) — CLI testleri gerçek
    git'e bağlı olduğundan fixture HEAD'i main soyunda olmalı."""
    proc = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short",
                           "origin/main"], capture_output=True, text=True)
    if proc.returncode != 0:
        proc = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short",
                               "main"], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def fake_git(main_sha="a" * 40, gap=0, ancestor=True):
    """`git_runner` sözleşmesini taklit eden sahte git."""
    def _git(args):
        if args[0] == "rev-parse":
            return main_sha
        if args[:1] == ["merge-base"]:
            return "" if ancestor else None
        if args[:1] == ["rev-list"]:
            return str(gap)
        return None
    return _git


class TestParseStructure(unittest.TestCase):
    def test_real_ledger_parses_clean(self):
        rows, violations = de.parse_rows(LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(violations, [])
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row.runs), len(de.EXPECTED_HEADER) - 2)

    def test_missing_table_is_violation(self):
        _, violations = de.parse_rows("# bos\n")
        self.assertTrue(any("tablo basligi" in v for v in violations))

    def test_wrong_header_is_violation(self):
        text = ledger_text([("2026-10-05", "abc1234", [("success", "1")] * 4)])
        text = text.replace("| test-smoke |", "| baska |")
        _, violations = de.parse_rows(text)
        self.assertTrue(any("baslik" in v for v in violations))

    def test_bad_date_is_violation(self):
        text = ledger_text([("05.10.2026", "abc1234", [("success", "1")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("tarih ISO" in v for v in violations))

    def test_non_hex_head_is_violation(self):
        text = ledger_text([("2026-10-05", "ZZZZZZZ", [("success", "1")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("kisa-hex" in v for v in violations))

    def test_bad_run_cell_is_violation(self):
        text = ledger_text([("2026-10-05", "abc1234", ["yesil"] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("bicimi yanlis" in v for v in violations), violations)

    def test_unknown_conclusion_is_reported_per_cell(self):
        text = ledger_text([("2026-10-05", "abc1234", [("yesildi", "1")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertEqual(len(violations), 4)

    def test_unknown_conclusion_is_violation(self):
        text = ledger_text([("2026-10-05", "abc1234", [("yesil", "1")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("bilinmeyen conclusion" in v for v in violations))

    def test_duplicate_head_is_violation(self):
        text = ledger_text([("2026-10-05", "abc1234", [("success", "1")] * 4),
                            ("2026-10-06", "abc1234", [("success", "2")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("birden fazla satirda" in v for v in violations))

    def test_backwards_date_is_violation(self):
        text = ledger_text([("2026-10-06", "abc1234", [("success", "1")] * 4),
                            ("2026-10-05", "def5678", [("success", "2")] * 4)])
        _, violations = de.parse_rows(text)
        self.assertTrue(any("geriye gidiyor" in v for v in violations))

    def test_violation_reports_markdown_line_number(self):
        text = ledger_text([("2026-10-05", "abc1234", [("success", "1")] * 4),
                            ("2026-10-06", "def5678", [("yesildi", "2")] * 4)])
        _, violations = de.parse_rows(text)
        # baslik 3. satir, ayirici 4. satir, ilk veri satiri 5, ikinci 6
        self.assertTrue(any(v.startswith("satir 6:") for v in violations),
                        violations)


class TestHeadCoverage(unittest.TestCase):
    def setUp(self):
        self.rows, _ = de.parse_rows(
            ledger_text([("2026-10-05", "abc1234", [("success", "1")] * 4)]))

    def test_within_gap_is_ok(self):
        self.assertEqual(de.check_head_coverage(self.rows, fake_git(gap=2), 3), [])

    def test_gap_over_tolerance_is_violation(self):
        out = de.check_head_coverage(self.rows, fake_git(gap=9), 3)
        self.assertTrue(any("9 commit ileride" in v for v in out), out)

    def test_non_ancestor_head_is_violation(self):
        out = de.check_head_coverage(self.rows, fake_git(ancestor=False), 3)
        self.assertTrue(any("main soyunda degil" in v for v in out), out)

    def test_empty_ledger_is_violation(self):
        out = de.check_head_coverage([], fake_git(), 3)
        self.assertTrue(any("satir yok" in v for v in out), out)

    def test_unresolvable_main_is_violation(self):
        def broken(args):
            return None
        out = de.check_head_coverage(self.rows, broken, 3)
        self.assertTrue(any("cozulemedi" in v for v in out), out)


class TestAge(unittest.TestCase):
    today = dt.date(2026, 10, 20)

    def _rows(self, date):
        return de.parse_rows(
            ledger_text([(date, "abc1234", [("success", "1")] * 4)]))

    def test_fresh_row_is_ok(self):
        rows, _ = self._rows("2026-10-05")
        self.assertEqual(de.check_age(rows, self.today, 21), [])

    def test_old_row_is_violation(self):
        rows, _ = self._rows("2026-09-01")
        out = de.check_age(rows, self.today, 21)
        self.assertTrue(any("49 gun eski" in v for v in out), out)

    def test_future_date_is_violation(self):
        rows, _ = self._rows("2026-12-01")
        out = de.check_age(rows, self.today, 21)
        self.assertTrue(any("gelecek tarihli" in v for v in out), out)

    def test_empty_ledger_is_violation(self):
        out = de.check_age([], self.today, 21)
        self.assertTrue(any("satir yok" in v for v in out), out)


class TestRunReality(unittest.TestCase):
    def setUp(self):
        self.rows, _ = de.parse_rows(ledger_text([
            ("2026-10-01", "aaa1111", [("success", "11")] * 4),
            ("2026-10-05", "bbb2222", [("failure", "21"), ("success", "22"),
                                       ("success", "23"), ("success", "24")]),
        ]))

    def test_matching_conclusions_pass(self):
        live = {"21": "failure", "22": "success", "23": "success", "24": "success"}
        fetch = lambda rid: ({"conclusion": live[rid]} if rid in live else None)
        self.assertEqual(de.check_runs(self.rows, fetch, 1), [])

    def test_conclusion_drift_is_violation(self):
        live = {"21": "success", "22": "success", "23": "success", "24": "success"}
        fetch = lambda rid: {"conclusion": live[rid]}
        out = de.check_runs(self.rows, fetch, 1)
        self.assertTrue(any("sapmasi" in v and "#21" in v for v in out), out)

    def test_missing_run_is_violation(self):
        out = de.check_runs(self.rows, lambda rid: None, 1)
        self.assertEqual(len(out), 4)
        self.assertTrue(all("bulunamadi" in v for v in out), out)

    def test_only_newest_rows_are_queried(self):
        """Eski satırlar canlıya sorulmaz (saklama süresi → yanlış kırmızı)."""
        seen = []

        def spy(rid):
            seen.append(rid)
            return {"conclusion": "success"}
        de.check_runs(self.rows, spy, 1)
        self.assertEqual(sorted(seen), ["21", "22", "23", "24"])
        self.assertNotIn("11", seen)

    def test_verify_rows_zero_disables_network(self):
        self.assertEqual(de.check_runs(self.rows, lambda rid: None, 0), [])


class TestRunChecksAndCli(unittest.TestCase):
    def _env(self, live=None, gap=1, today=None):
        return de.Env(git=fake_git(gap=gap),
                      fetch_run=(live or {}).get,
                      today=today or dt.date(2026, 10, 20))

    def test_offline_run_skips_live_but_keeps_structure(self):
        import tempfile
        text = ledger_text([("2026-10-05", "abc1234", [("success", "1")] * 4)])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "DEPLOY_EVIDENCE.md"
            path.write_text(text, encoding="utf-8")
            rows, violations = de.run_checks(
                path, self._env(), 3, 21, 2, network=False)
            self.assertEqual(violations, [])
            self.assertEqual(len(rows), 1)

    def test_cli_exit_zero_when_fresh(self):
        head = real_main_short()
        if not head:
            self.skipTest("main cozulemedi (git gecmişi yok)")
        import tempfile
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        text = ledger_text([(today, head, [("success", "1")] * 4)])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ledger.md"
            path.write_text(text, encoding="utf-8")
            rc = de.main(["--check", "--no-network", "--ledger", str(path)])
            self.assertEqual(rc, 0)

    def test_cli_exit_one_when_stale(self):
        head = real_main_short()
        if not head:
            self.skipTest("main cozulemedi (git gecmişi yok)")
        import tempfile
        text = ledger_text([("2020-01-01", head, [("success", "1")] * 4)])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ledger.md"
            path.write_text(text, encoding="utf-8")
            rc = de.main(["--check", "--no-network", "--ledger", str(path)])
            self.assertEqual(rc, 1)

    def test_cli_accepts_repo_ledger_offline(self):
        """Repo'nun gercek defteri offline kapidan geçer (kendi bütünlüğü)."""
        rc = de.main(["--check", "--no-network", "--ledger", str(LEDGER)])
        self.assertEqual(rc, 0)

    def test_missing_ledger_is_error_exit_two(self):
        rc = de.main(["--check", "--no-network", "--ledger", "/nonexistent/x.md"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
