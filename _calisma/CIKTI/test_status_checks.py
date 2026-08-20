#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_status_checks.py — branch protection smoke kapısı.

status_checks.py'nin pure mantığını deterministik doğrular: gate_jobs
(required adayları), merge_block_smoke (strict/enforce_admins/force-push/
deletions) ve evaluate_protection (ad eşleşmesi + enforcement). Ayrıca
--gh entegrasyonu mock'lanmış run_gh ile (canlı ağ yok) doğrulanır.

PyYAML gerektirir (status_checks.py modül-seviyesi import). CI birim test
adımında pyyaml yoksa bu dosya bütünüyle SKIP olur (test_check_action_runtimes.py
ile aynı desen).
"""
import io
import json
import pathlib
import sys
import unittest
from unittest import mock

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

if HAVE_YAML:
    CIKTI = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(CIKTI))
    import status_checks as sc  # noqa: E402

    # gate_jobs cwd-göreli WORKFLOW okur — testler repo kökünden koşulur.
    _WORKFLOW = pathlib.Path(".github/workflows/verify.yml")


def _protection(contexts=None, strict=True, enforce_admins=True,
                force_pushes=False, deletions=False):
    return {
        "required_status_checks": {
            "contexts": contexts or [],
            "strict": strict,
        },
        "enforce_admins": {"enabled": enforce_admins},
        "allow_force_pushes": {"enabled": force_pushes},
        "allow_deletions": {"enabled": deletions},
    }


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestGateJobs(unittest.TestCase):
    def test_excludes_pr_only_and_advisory(self):
        gates = sc.gate_jobs()
        self.assertNotIn("manifest-comment", gates)
        self.assertNotIn("precheck", gates)
        # Node 24 yükseltmesiyle eklenen job required aday olmalı.
        self.assertIn("action-runtimes", gates)
        self.assertEqual(gates["action-runtimes"],
                         "Action runtime check (node24)")

    def test_count_matches_workflow_minus_excludes(self):
        # 14 job − 2 hariç = 12 required aday (tek kaynak: workflow).
        # (commit-msg-gate eklendi: commit-msg ihlali bloke gate)
        self.assertEqual(len(sc.gate_jobs()), 12)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestMergeBlockSmoke(unittest.TestCase):
    def test_all_pass_when_fully_enforced(self):
        smoke = sc.merge_block_smoke(
            _protection(["a"], strict=True, enforce_admins=True,
                        force_pushes=False, deletions=False))
        self.assertTrue(all(ok for (_l, ok, _n) in smoke))
        self.assertEqual(len(smoke), 4)

    def test_all_fail_when_bypass_open(self):
        smoke = sc.merge_block_smoke(
            _protection(["a"], strict=False, enforce_admins=False,
                        force_pushes=True, deletions=True))
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_empty_protection_fails_closed(self):
        # Alanlar eksikse enforcement KANITLANAMAZ → FAIL (yanlış PASS yok).
        smoke = sc.merge_block_smoke({})
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_labels_distinguish_merge_block(self):
        labels = [l for (l, _ok, _n) in sc.merge_block_smoke({})]
        self.assertIn("required_status_checks.strict (up-to-date zorunlu)",
                      labels)
        self.assertIn("enforce_admins.enabled (admin bypass kapalı)", labels)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestEvaluateProtection(unittest.TestCase):
    def test_names_and_enforcement_both_pass(self):
        r = sc.evaluate_protection(["a", "b"],
                                   _protection(["a", "b"]))
        self.assertTrue(r["names_ok"])
        self.assertTrue(r["enforcement_ok"])
        self.assertEqual(r["missing"], [])
        self.assertEqual(r["extra"], [])

    def test_names_drift_detected(self):
        r = sc.evaluate_protection(["a", "b", "c"],
                                   _protection(["a", "b"]))
        self.assertFalse(r["names_ok"])
        self.assertEqual(r["missing"], ["c"])
        self.assertEqual(r["extra"], [])

    def test_extra_check_detected(self):
        r = sc.evaluate_protection(["a"], _protection(["a", "b"]))
        self.assertFalse(r["names_ok"])
        self.assertEqual(r["extra"], ["b"])

    def test_enforcement_fail_independent_of_names(self):
        # Adlar birebir eşleşse bile strict kapalıysa enforcement FAIL.
        r = sc.evaluate_protection(["a"], _protection(["a"], strict=False))
        self.assertTrue(r["names_ok"])
        self.assertFalse(r["enforcement_ok"])

    def test_null_contexts_treated_as_empty(self):
        p = _protection(None)
        p["required_status_checks"]["contexts"] = None
        r = sc.evaluate_protection(["a"], p)
        self.assertEqual(r["configured"], [])
        self.assertFalse(r["names_ok"])


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestGhIntegration(unittest.TestCase):
    """--gh yolunu mock'lanmış run_gh ile test eder (canlı ağ yok)."""

    def _run_main(self, protection_obj):
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(protection_obj)):
            return sc.main(["--gh", "--repo", "owner/name"])

    def test_full_pass_returns_none(self):
        # Beklenen 9 ad + tam enforcement → exit 0 (return None, SystemExit yok).
        checks = list(sc.gate_jobs().values())
        rc = self._run_main(_protection(checks))
        self.assertIsNone(rc)

    def test_names_drift_exits_1(self):
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(_protection(["x"]))):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

    def test_enforcement_fail_exits_1(self):
        checks = list(sc.gate_jobs().values())
        bad = _protection(checks, strict=False, enforce_admins=False)
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(bad)):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

    def test_no_protection_warns_exit_0(self):
        # run_gh RuntimeError → "branch protection kurulu değil" → return (0).
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError("Branch not protected")):
            rc = sc.main(["--gh", "--repo", "owner/name"])
        self.assertIsNone(rc)

    def test_gh_json_pass(self):
        checks = list(sc.gate_jobs().values())
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(_protection(checks))), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertIsNone(rc)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "PASS")
        self.assertTrue(d["names_ok"])
        self.assertTrue(d["enforcement_ok"])

    def test_gh_json_fail_exits_1(self):
        checks = list(sc.gate_jobs().values())
        bad = _protection(checks, strict=False)
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(bad)), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "FAIL")
        self.assertFalse(d["enforcement_ok"])

    def test_gh_json_not_set_up(self):
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError("Branch not protected")), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertIsNone(rc)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "NOT_SET_UP")


if __name__ == "__main__":
    unittest.main()
