#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pr_hygiene.py — PR board hijyeni sözleşmeleri (OFFLINE).

  1) Sınıflandırma: BEHIND / DIRTY / BLOCKED / taslak / bayat kümeleri
     birbirine karışmaz; DIRTY `mergeable=CONFLICTING` ile de yakalanır.
  2) Güncelleme seçimi: yalnız BEHIND + taslak-değil + `hold` etiketsiz;
     DIRTY asla otomatik rebase edilmez (çakışma insan kararıdır).
  3) Hüküm fail-closed: eşik aşımı rc=3, ölçüm imkânsız rc=2, temiz rc=0.
  4) Issue senkronu idempotent: PILEUP'ta aç/yorumla, temizde kapat; aynı
     başlık işaretçisiyle ikinci issue açılmaz.
  5) CLI `--from-json` ağa çıkmadan çalışır ve `--json-out` tek JSON belgesi
     yazar (stdout parse edilebilir kalır).

stdlib-only, OFFLINE.
"""
import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

CIKTI = Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))
import pr_hygiene as ph  # noqa: E402

NOW = datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.timezone.utc)


def _pr(number, state="CLEAN", mergeable="MERGEABLE", draft=False,
        labels=(), updated="2026-11-03T00:00:00Z", title=None):
    return {
        "number": number,
        "title": title or "PR %d" % number,
        "headRefName": "dal-%d" % number,
        "mergeable": mergeable,
        "mergeStateStatus": state,
        "isDraft": draft,
        "updatedAt": updated,
        "labels": [{"name": l} for l in labels],
        "author": {"login": "bot"},
    }


class TestClassify(unittest.TestCase):
    def test_sets_are_disjoint_and_complete(self):
        prs = ph.normalize([
            _pr(1),                                          # mergeable
            _pr(2, state="BEHIND"),                          # behind
            _pr(3, state="DIRTY", mergeable="CONFLICTING"),  # dirty
            _pr(4, state="BLOCKED"),                         # blocked
            _pr(5, draft=True),                              # draft
            _pr(6, updated="2026-10-01T00:00:00Z"),          # stale
        ])
        r = ph.classify(prs, now=NOW)
        self.assertEqual(r["open"], 6)
        self.assertEqual(r["behind"], [2])
        self.assertEqual(r["dirty"], [3])
        self.assertEqual(r["blocked"], [4])
        self.assertEqual(r["draft"], [5])
        self.assertEqual(r["stale"], [6])
        # `mergeable` ekseni diktir: taslak/bayat PR da mergeable olabilir.
        self.assertEqual(r["mergeable"], [1, 5, 6])

    def test_conflicting_mergeable_alone_counts_as_dirty(self):
        r = ph.classify(ph.normalize([
            _pr(9, state="UNKNOWN", mergeable="CONFLICTING")]), now=NOW)
        self.assertEqual(r["dirty"], [9])

    def test_stale_boundary_is_strict(self):
        # Tam 7 gün bayat SAYILMAZ; 8 gün sayılır.
        r = ph.classify(ph.normalize([
            _pr(1, updated="2026-10-28T12:00:00Z"),
            _pr(2, updated="2026-10-27T12:00:00Z")]), now=NOW, stale_days=7)
        self.assertEqual(r["stale"], [2])


class TestEligibility(unittest.TestCase):
    def test_only_behind_non_draft_non_hold(self):
        prs = ph.normalize([
            _pr(1, state="BEHIND"),
            _pr(2, state="BEHIND", draft=True),
            _pr(3, state="BEHIND", labels=("hold",)),
            _pr(4, state="DIRTY", mergeable="CONFLICTING"),
            _pr(5, state="CLEAN"),
        ])
        self.assertEqual(ph.eligible_for_update(prs, 10), [1])

    def test_max_updates_bounds_ci_cost(self):
        prs = ph.normalize([_pr(n, state="BEHIND") for n in (1, 2, 3, 4)])
        self.assertEqual(ph.eligible_for_update(prs, 2), [1, 2])


class TestVerdict(unittest.TestCase):
    def test_threshold_breach_is_red(self):
        r = ph.classify(ph.normalize([_pr(n) for n in range(1, 4)]), now=NOW)
        self.assertEqual(ph.verdict(r, threshold=2)[0], 3)
        self.assertEqual(ph.verdict(r, threshold=3)[0], 0)

    def test_report_names_the_operating_rule(self):
        r = ph.classify(ph.normalize([_pr(1, state="BEHIND")]), now=NOW)
        _, body = ph.render(r)
        self.assertIn("#1", body)
        self.assertIn("`hold`", body)


class FakeRunner:
    """`subprocess.run` yerine: çağrıları kaydeder, senaryolu stdout döner."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))

        class P:
            returncode = 0
            stderr = ""
            stdout = ""
        p = P()
        p.stdout = self.responses.pop(0) if self.responses else ""
        return p


class TestIssueSync(unittest.TestCase):
    def test_pileup_creates_once_then_comments(self):
        runner = FakeRunner([json.dumps([]),                 # list: yok
                             "https://github.com/o/r/issues/7\n",  # create
                             json.dumps([{"number": 7,
                                          "title": ph.ISSUE_MARKER + " x"}]),
                             ""])                       # comment
        self.assertIn("created", ph.sync_issue("gövde", True, runner=runner))
        self.assertIn("updated #7",
                      ph.sync_issue("gövde", True, runner=runner))
        subs = [c[2] for c in runner.calls]
        self.assertEqual(subs.count("create"), 1)
        self.assertEqual(subs.count("comment"), 1)

    def test_clean_board_closes_tracking_issue(self):
        runner = FakeRunner([
            json.dumps([{"number": 7, "title": ph.ISSUE_MARKER + " x"}]),
            ""])
        self.assertEqual(ph.sync_issue("gövde", False, runner=runner),
                         "closed 1")
        self.assertEqual(runner.calls[-1][2], "close")

    def test_measurement_failure_is_gh_error(self):
        def broken(argv, **kwargs):
            class P:
                returncode = 1
                stdout = ""
                stderr = "rate limit exceeded"
            return P()
        with self.assertRaises(ph.GhError):
            ph.fetch_prs(runner=broken)


class TestCliOffline(unittest.TestCase):
    def _run(self, prs, *extra):
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "prs.json")
        out = os.path.join(tmp, "board.json")
        with open(src, "w", encoding="utf-8") as fh:
            json.dump(prs, fh)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = ph.main(["--from-json", src, "--json-out", out] + list(extra))
        with open(out, encoding="utf-8") as fh:
            doc = json.load(fh)
        return rc, buf.getvalue(), doc

    def test_clean_board_rc0_and_single_json_document(self):
        rc, out, doc = self._run([_pr(1), _pr(2)])
        self.assertEqual(rc, 0)
        self.assertIn("OK: 2 açık PR", out)
        self.assertEqual(doc["report"]["open"], 2)
        self.assertEqual(doc["verdict_rc"], 0)

    def test_pileup_rc3(self):
        rc, out, doc = self._run(
            [_pr(n) for n in range(1, 5)], "--threshold", "3")
        self.assertEqual(rc, 3)
        self.assertIn("PILEUP", out)
        self.assertEqual(doc["report"]["open"], 4)

    def test_apply_is_ignored_offline(self):
        # --from-json ile ağa çıkılmaz: güncelleme listesi boş kalır.
        rc, _, doc = self._run([_pr(1, state="BEHIND")], "--apply")
        self.assertEqual(rc, 0)
        self.assertEqual(doc["updates"], [])


if __name__ == "__main__":
    unittest.main()
