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
    def test_excludes_gates_and_advisory(self):
        gates = sc.gate_jobs()
        self.assertNotIn("manifest-comment", gates)
        self.assertNotIn("precheck", gates)
        self.assertIn("label-gate", gates)           # BİLEREK required (P0 gate)
        self.assertNotIn("label-gate-p1", gates)     # PR-only (opsiyonel)
        self.assertIn("commit-msg-gate", gates)      # PR-only ama required (2026-08-23)
        self.assertNotIn("plist-check", gates)       # macOS-advisory
        self.assertNotIn("mirror-check", gates)      # macOS fail-closed (advisory)
        self.assertNotIn("daemon-http", gates)       # advisory smoke
        self.assertIn("ci-simulate", gates)          # required: tam replay kapısı
        self.assertIn("config-sync", gates)          # required: üçlü senkron kapısı
        self.assertNotIn("audit-refs-trend", gates)  # advisory denetim
        self.assertNotIn("changelog-drift", gates)   # advisory: changelog drift
        # Node 24 yükseltmesiyle eklenen job required aday olmalı.
        self.assertIn("action-runtimes", gates)
        self.assertEqual(gates["action-runtimes"],
                         "Action runtime check (node24)")

    def test_count_matches_workflow_minus_excludes(self):
        # 22 job − 10 hariç = 12 required aday (tek kaynak: workflow).
        # Hariç: manifest-comment, precheck, label-gate-p1, plist-check,
        #        mirror-check, daemon-http, audit-live-ci, audit-refs-trend,
        #        override-trend, changelog-drift
        self.assertEqual(len(sc.gate_jobs()), 12)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestAdvisoryContract(unittest.TestCase):
    """Advisory kontratı: plist-check ve tüm exclude'lar required DEĞİL."""

    def test_real_workflow_passes(self):
        c = sc.advisory_contract()
        self.assertTrue(c["ok"], c["issues"])
        self.assertTrue(c["plist_check"]["ok"])
        self.assertEqual(c["plist_check"]["name"],
                         "Plist drift check (macOS, advisory)")
        self.assertFalse(c["plist_check"]["required"])
        self.assertIn("Plist drift check (macOS, advisory)", c["advisory"])
        # Fark = tüm adlar − required adlar; her exclude job advisory'de.
        self.assertEqual(len(c["advisory"]), len(sc.GATE_EXCLUDE))
        for jid in sc.GATE_EXCLUDE:
            self.assertNotIn(c["all_jobs"][jid], c["required"])

    def test_plist_check_required_fails(self):
        # GATE_EXCLUDE'dan plist-check düşerse (required'a girer) kontrat FAIL.
        with mock.patch.object(sc, "GATE_EXCLUDE",
                               sc.GATE_EXCLUDE - {"plist-check"}):
            c = sc.advisory_contract()
        self.assertFalse(c["ok"])
        self.assertFalse(c["plist_check"]["ok"])
        self.assertTrue(c["plist_check"]["required"])
        self.assertTrue(any("plist-check" in i for i in c["issues"]))

    def test_stale_exclude_fails(self):
        # Exclude edilen job workflow'dan silinirse bayat exclude → FAIL.
        data = {"jobs": {
            "verify": {"name": "Delivery verification — K1-K14 (single entry point)"}}}
        c = sc.advisory_contract(data)
        self.assertFalse(c["ok"])
        self.assertTrue(any("yok" in i for i in c["issues"]))
        self.assertFalse(c["plist_check"]["ok"])

    def test_name_collision_fails(self):
        # Required job, exclude edilen job'la AYNI ada sahipse → çakışma FAIL.
        data = {"jobs": {
            "plist-check": {"name": "Plist drift check (macOS, advisory)"},
            "other": {"name": "Plist drift check (macOS, advisory)"},
        }}
        c = sc.advisory_contract(data)
        self.assertFalse(c["ok"])
        self.assertTrue(any("çakışma" in i for i in c["issues"]))
        self.assertTrue(c["plist_check"]["required"])

    def test_main_exits_1_when_contract_broken(self):
        # main() fail-closed: kontrat ihlalinde JSON modunda da exit 1.
        with mock.patch.object(sc, "advisory_contract") as m:
            m.return_value = {
                "ok": False,
                "all_jobs": {"plist-check": "Plist drift check (macOS, advisory)"},
                "required": ["Plist drift check (macOS, advisory)"],
                "advisory": [],
                "plist_check": {"job_id": "plist-check",
                                 "name": "Plist drift check (macOS, advisory)",
                                 "required": True, "ok": False},
                "issues": ["'plist-check' required sette — advisory olmalı"],
            }
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--json"])
        self.assertEqual(cm.exception.code, 1)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestMergeBlockSmoke(unittest.TestCase):
    def test_all_pass_when_fully_enforced(self):
        smoke = sc.merge_block_smoke(
            _protection(["a"], strict=True, enforce_admins=True,
                        force_pushes=False, deletions=False))
        self.assertTrue(all(ok for (_l, ok, _n) in smoke))
        self.assertEqual(len(smoke), 4)

    def test_all_fail_when_bypass_open(self):
        # strict eksik + diğer bypass'lar açık → tümü FAIL.
        prot = _protection(["a"], enforce_admins=False,
                           force_pushes=True, deletions=True)
        prot["required_status_checks"]["strict"] = None
        smoke = sc.merge_block_smoke(prot)
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_empty_protection_fails_closed(self):
        # Alanlar eksikse enforcement KANITLANAMAZ → FAIL (yanlış PASS yok).
        smoke = sc.merge_block_smoke({})
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_labels_distinguish_merge_block(self):
        labels = [l for (l, _ok, _n) in sc.merge_block_smoke({})]
        self.assertIn("required_status_checks.strict", labels)
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

    def test_enforcement_fail_when_strict_missing(self):
        # strict alan tanımlı değilse enforcement FAIL.
        r = sc.evaluate_protection(["a"], {"required_status_checks": {"contexts": ["a"]},
                                             "enforce_admins": {"enabled": True},
                                             "allow_force_pushes": {"enabled": False},
                                             "allow_deletions": {"enabled": False}})
        self.assertTrue(r["names_ok"])
        self.assertFalse(r["enforcement_ok"])

    def test_strict_false_is_valid_for_direct_push(self):
        # strict=False: push izni var, PR-only engeli yok — geçerli.
        r = sc.evaluate_protection(["a"], _protection(["a"], strict=False))
        self.assertTrue(r["names_ok"])
        self.assertTrue(r["enforcement_ok"])

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
        # Beklenen 12 ad + tam enforcement → exit 0 (return None, SystemExit yok).
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

    def test_no_protection_exits_1(self):
        # run_gh RuntimeError → "branch protection kurulu değil" → exit 1 (fail-closed).
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError("Branch not protected")), \
                mock.patch.object(sys, "stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

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
        bad = _protection(checks, enforce_admins=False)
        bad["required_status_checks"]["strict"] = None
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

    def test_gh_json_not_set_up_exits_1(self):
        # Protection kurulu değilken (gh api 404) --gh exit 1 (fail-closed)
        # ve verdict NOT_SET_UP kalır.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 404: Not Found — branch not protected")), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "NOT_SET_UP")

    def test_gh_json_unreadable_not_set_up_same_verdict_exit(self):
        # 404 içermeyen hata (403 yetki yok / ağ) da fail-closed exit 1;
        # verdict UNREADABLE — "kurulu değil" ile karıştırılmaz.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 403: Resource not accessible by "
                                   "integration")), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "UNREADABLE")
        self.assertNotEqual(d["verdict"], "NOT_SET_UP")

    def test_gh_text_not_set_up_exits_1(self):
        # Text modunda da protection kurulu değilken exit 1.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 404: Not Found — branch not protected")), \
                mock.patch.object(sys, "stdout", new=buf), \
                mock.patch.object(sys, "stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
