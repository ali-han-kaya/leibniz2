#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_setup_branch_protection.py — setup_branch_protection.py birim kapısı.

Kurulum scriptini mock gh (gh_get/gh_put/verify_checks) ile doğrular — canlı
ağ yok. Kapsam:
  - build_body: sıfırdan kur / review+restrictions koruma / enforce kapatma
  - main: beklenen check'leri PUT'a taşır, dry-run PUT çalıştırmaz,
    404 (koruma yok) sıfırdan kurar, verify FAIL → exit 1 (fail-closed),
    PUT hatası → exit 1, boş beklenen liste → exit 2.

status_checks import'u PyYAML ister — yoksa bütünüyle SKIP (mevcut desen).
"""
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
    import setup_branch_protection as sbp  # noqa: E402


def _current_protection():
    return {
        "required_status_checks": {"strict": True, "contexts": ["Check A"]},
        "enforce_admins": {"enabled": True},
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 2,
            "dismissal_restrictions": {
                "users": [{"login": "alice"}],
                "teams": [{"slug": "core"}],
            },
        },
        "restrictions": {"users": [{"login": "alice"}], "teams": []},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestBuildBody(unittest.TestCase):
    def test_fresh_install(self):
        body = sbp.build_body(["Check A", "Check B"], None)
        self.assertEqual(body["required_status_checks"],
                         {"strict": True, "contexts": ["Check A", "Check B"]})
        self.assertTrue(body["enforce_admins"])
        self.assertIsNone(body["required_pull_request_reviews"])
        self.assertIsNone(body["restrictions"])
        self.assertFalse(body["allow_force_pushes"])
        self.assertFalse(body["allow_deletions"])

    def test_preserves_reviews_and_restrictions(self):
        body = sbp.build_body(["Check A", "Check B"], _current_protection())
        rpr = body["required_pull_request_reviews"]
        self.assertEqual(rpr["required_approving_review_count"], 2)
        self.assertTrue(rpr["dismiss_stale_reviews"])
        self.assertEqual(rpr["dismissal_restrictions"]["users"], ["alice"])
        self.assertEqual(rpr["dismissal_restrictions"]["teams"], ["core"])
        # restrictions GET şeması PUT'ta aynen korunur.
        self.assertEqual(body["restrictions"]["users"], [{"login": "alice"}])

    def test_no_enforce_admins(self):
        body = sbp.build_body(["A"], None, enforce_admins=False)
        self.assertFalse(body["enforce_admins"])

    def test_contexts_override_current(self):
        # Beklenen liste, mevcut contexts'i BİREBİR değiştirir (kurulum niyeti).
        body = sbp.build_body(["New One"], _current_protection())
        self.assertEqual(body["required_status_checks"]["contexts"], ["New One"])


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestMain(unittest.TestCase):
    EXPECTED = {"job-a": "Check A", "job-b": "Check B"}

    def _run(self, argv):
        return sbp.main(argv)

    def test_install_puts_expected_checks(self):
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  return_value=_current_protection()) as get, \
                mock.patch.object(sbp, "gh_put") as put:
            rc = self._run(["--repo", "owner/name", "--no-verify"])
        self.assertEqual(rc, 0)
        get.assert_called_once_with("owner/name")
        body = put.call_args.args[1]
        self.assertEqual(body["required_status_checks"]["contexts"],
                         ["Check A", "Check B"])
        self.assertTrue(body["enforce_admins"])
        self.assertFalse(body["allow_force_pushes"])

    def test_dry_run_does_not_put(self):
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  return_value=_current_protection()), \
                mock.patch.object(sbp, "gh_put") as put:
            rc = self._run(["--repo", "owner/name", "--dry-run"])
        self.assertEqual(rc, 0)
        put.assert_not_called()

    def test_fresh_404_installs_from_scratch(self):
        # Koruma yok (gh_get 404) → sıfırdan kur; PUT yine çağrılır.
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  side_effect=RuntimeError("HTTP 404: Not Found")), \
                mock.patch.object(sbp, "gh_put") as put:
            rc = self._run(["--repo", "owner/name", "--no-verify"])
        self.assertEqual(rc, 0)
        body = put.call_args.args[1]
        self.assertEqual(body["required_status_checks"]["contexts"],
                         ["Check A", "Check B"])
        self.assertIsNone(body["required_pull_request_reviews"])

    def test_verify_pass_returns_0(self):
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  return_value=_current_protection()), \
                mock.patch.object(sbp, "gh_put"), \
                mock.patch.object(sbp, "verify_checks",
                                  return_value=(0, "SONUÇ: PASS", "")) as v:
            rc = self._run(["--repo", "owner/name"])
        self.assertEqual(rc, 0)
        v.assert_called_once_with("owner/name")

    def test_verify_fail_returns_1(self):
        # Kurulum sonrası hâlâ drift → fail-closed exit 1.
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  return_value=_current_protection()), \
                mock.patch.object(sbp, "gh_put"), \
                mock.patch.object(sbp, "verify_checks",
                                  return_value=(1, "SONUÇ: FAIL", "")):
            rc = self._run(["--repo", "owner/name"])
        self.assertEqual(rc, 1)

    def test_put_failure_returns_1(self):
        with mock.patch.object(sbp.sc, "gate_jobs",
                               return_value=self.EXPECTED), \
                mock.patch.object(sbp, "gh_get",
                                  return_value=_current_protection()), \
                mock.patch.object(sbp, "gh_put",
                                  side_effect=RuntimeError("HTTP 403: no admin")):
            rc = self._run(["--repo", "owner/name", "--no-verify"])
        self.assertEqual(rc, 1)

    def test_empty_expected_returns_2(self):
        with mock.patch.object(sbp.sc, "gate_jobs", return_value={}):
            rc = self._run(["--repo", "owner/name"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
