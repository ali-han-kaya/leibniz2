#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_protection_drift.py — haftalık branch-protection drift kapısı.

Neden bu testler var: bu kapı CI'da KOŞABİLEN tek koruma denetimidir
(`status_checks.py --gh` CI'da koşamaz — admin scope'u Actions'ta geçersiz).
Bir kapının sessizce ölmesi, hiç var olmamasıyla aynıdır; bu yüzden üç
rapor dalı (SKIP / DOĞRULANAMADI / FAIL) ve her drift ayarı ayrı ayrı
ölçülür.

stdlib unittest — ek bağımlılık yok.
"""

import io
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import check_protection_drift as cpd      # noqa: E402
import status_checks as sc                # noqa: E402
import verify_delivery as vd              # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"


def _protection(contexts=None, strict=True, enforce_admins=True,
                force_pushes=False, deletions=False):
    return {
        "required_status_checks": {"strict": strict,
                                   "contexts": contexts if contexts is not None
                                   else ["alpha", "beta"]},
        "enforce_admins": {"enabled": enforce_admins},
        "allow_force_pushes": {"enabled": force_pushes},
        "allow_deletions": {"enabled": deletions},
    }


EXPECTED = ["alpha", "beta"]


def _run(protection, expected=EXPECTED, token="tok", argv=("--json",)):
    """main()'i sahte fetch ile koşar. Döner: (rc, payload|None, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    patches = [mock.patch.object(cpd, "token_from_env", return_value=token),
               mock.patch.object(cpd, "repo_slug",
                                 return_value=("owner/name", None)),
               mock.patch.object(cpd.sc, "gate_jobs",
                                 return_value={"a": "alpha", "b": "beta"}
                                 if expected is None else
                                 {str(i): n for i, n in enumerate(expected)})]
    if isinstance(protection, tuple):
        # (None, "HTTP 403") gibi "okunamadı" şekli — fetch_protection'ın
        # gerçek hata dönüşü (yükseltmez, DÖNER).
        patches.append(mock.patch.object(cpd, "fetch_protection",
                                         return_value=protection))
    else:
        patches.append(mock.patch.object(cpd, "fetch_protection",
                                         return_value=(protection, None)))
    for p in patches:
        p.start()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        rc = cpd.main(list(argv))
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        for p in patches:
            p.stop()
    text = out.getvalue()
    payload = json.loads(text) if text.strip().startswith("{") else None
    return rc, payload, err.getvalue()


class TokenLookupTests(unittest.TestCase):
    def test_no_token_is_none(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in cpd.TOKEN_ENVS:
                os.environ.pop(name, None)
            self.assertIsNone(cpd.token_from_env())

    def test_prefers_protection_pat_and_strips(self):
        env = {"PROTECTION_PAT": "  pat-value  ", "GH_ADMIN_TOKEN": "other"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(cpd.token_from_env(), "pat-value")

    def test_falls_back_to_gh_admin_token(self):
        with mock.patch.dict(os.environ, {"GH_ADMIN_TOKEN": "fallback"},
                             clear=False):
            os.environ.pop("PROTECTION_PAT", None)
            self.assertEqual(cpd.token_from_env(), "fallback")


class SkipAndUnverifiableTests(unittest.TestCase):
    """SKIP ≠ temiz, DOĞRULANAMADI ≠ yeşil."""

    def test_missing_token_skips_with_zero_and_no_findings(self):
        with mock.patch.object(cpd, "fetch_protection") as fetch:
            rc, payload, _ = _run(_protection(), token=None)
        self.assertEqual(rc, 0, "secret yokken gürültü yapılmamalı")
        self.assertEqual(payload["status"], "SKIP")
        self.assertEqual(payload["p1"], [])
        fetch.assert_not_called()          # okumaya hiç kalkışmaz

    def test_present_but_unreadable_token_is_not_green(self):
        """Süresi geçmiş PAT sessiz SKIP'e düşmemeli — kapı ölürdü."""
        rc, payload, _ = _run((None, "HTTP 403: Resource not accessible"))
        self.assertEqual(rc, 2, "okunamayan token KIRMIZI olmalı")
        self.assertEqual(payload["status"], "UNVERIFIABLE")
        self.assertEqual(payload["p1"], [], "drift yok — P1 üretilmemeli")
        self.assertIn("DOĞRULANAMADI", payload["message"])
        # --json'suz koşumda aynı gerekçe stderr'e düşmeli (CI logunda görünür).
        rc2, _, err = _run((None, "HTTP 403"), argv=())
        self.assertEqual(rc2, 2)
        self.assertIn("DOĞRULANAMADI", err)

    def test_fetch_survives_missing_gh_binary(self):
        """`gh` kurulu değilse yükseltmemeli — hata DÖNMELİ (rc=2)."""
        with mock.patch.object(cpd.subprocess, "run",
                               side_effect=FileNotFoundError("gh yok")):
            protection, err = cpd.fetch_protection("owner/name", "tok")
        self.assertIsNone(protection)
        self.assertIn("gh çalıştırılamadı", err)

    def test_empty_protection_object_is_skipped_not_flagged(self):
        rc, payload, _ = _run({})
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["p1"], [])


class CleanProtectionTests(unittest.TestCase):
    def test_fully_enforced_protection_passes(self):
        rc, payload, _ = _run(_protection())
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["p1"], [])
        self.assertEqual(payload["expected_checks"], len(EXPECTED))


class DriftIsP1Tests(unittest.TestCase):
    """Her ayar ayrı ayrı: kapanması P1 üretmeli."""

    def _ids(self, payload):
        return {f["id"] for f in payload["p1"]}

    def _p1(self, **kw):
        rc, payload, _ = _run(_protection(**kw))
        self.assertEqual(rc, 1, "drift rc=1 olmalı")
        self.assertEqual(payload["status"], "FAIL")
        for f in payload["p1"]:
            self.assertEqual(f["priority"], "P1")
            self.assertTrue(f["evidence"], "kanıt alanı boş olmamalı")
        return self._ids(payload)

    def test_strict_off_is_p1(self):
        self.assertIn("PROT-STRICT", self._p1(strict=False))

    def test_admin_bypass_open_is_p1(self):
        self.assertIn("PROT-ENFORCE-ADMINS", self._p1(enforce_admins=False))

    def test_force_push_enabled_is_p1(self):
        self.assertIn("PROT-FORCE-PUSH", self._p1(force_pushes=True))

    def test_deletions_enabled_is_p1(self):
        self.assertIn("PROT-DELETIONS", self._p1(deletions=True))

    def test_missing_required_check_is_p1(self):
        ids = self._p1(contexts=["alpha"])
        self.assertIn("PROT-ADLAR-EKSIK", ids)

    def test_extra_required_check_is_p1(self):
        ids = self._p1(contexts=["alpha", "beta", "gamma"])
        self.assertIn("PROT-ADLAR-FAZLA", ids)

    def test_missing_field_treated_as_drift_not_as_unknown(self):
        """Alan hiç yoksa değer None → `is not True` FAIL verir (fail-closed)."""
        prot = _protection()
        prot["required_status_checks"].pop("strict")
        ids = self._p1_via(prot)
        self.assertIn("PROT-STRICT", ids)

    def _p1_via(self, protection):
        rc, payload, _ = _run(protection)
        self.assertEqual(rc, 1)
        return self._ids(payload)

    def test_all_five_drift_at_once_reports_each(self):
        ids = self._p1(contexts=["alpha"], strict=False, enforce_admins=False,
                       force_pushes=True, deletions=True)
        self.assertEqual(ids, {"PROT-STRICT", "PROT-ENFORCE-ADMINS",
                               "PROT-FORCE-PUSH", "PROT-DELETIONS",
                               "PROT-ADLAR-EKSIK"})


class VerifyDeliveryVocabularyTests(unittest.TestCase):
    """P1 bulguları repo'nun mevcut bulgu sözlüğünü kullanmalı."""

    def test_findings_match_verify_delivery_shape(self):
        got = []
        ok, _ = vd.check_protection_drift(
            lambda pri, cid, check, issue, evidence="": got.append(
                {"id": cid, "priority": pri, "check": check,
                 "issue": issue, "evidence": evidence}),
            _protection(strict=False), EXPECTED)
        self.assertFalse(ok)
        self.assertEqual(len(got), 1)
        self.assertEqual(set(got[0]), {"id", "priority", "check", "issue",
                                       "evidence"})

    def test_no_expected_skips_name_comparison(self):
        got = []
        ok, detail = vd.check_protection_drift(
            lambda *a, **kw: got.append(a), _protection(), expected=None)
        self.assertTrue(ok, detail)
        self.assertEqual(got, [])


class WorkflowAndReadOnlyTests(unittest.TestCase):
    """Yapısal: geçersiz scope geri gelmesin, kapı salt-okunur kalsın."""

    def test_no_workflow_declares_the_invalid_administration_scope(self):
        """`administration` Actions'ta GEÇERSİZ — eklenirse workflow 0 job üretir."""
        bad = []
        for wf in sorted(WORKFLOWS.glob("*.yml")):
            for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("administration:"):
                    bad.append("%s:%d" % (wf.name, i))
        self.assertEqual(bad, [], "geçersiz permission scope (`administration`) "
                                  "workflow'u parse hatasıyla öldürür: %s" % bad)

    def test_weekly_workflow_exists_and_is_scheduled(self):
        wf = WORKFLOWS / "protection-drift.yml"
        self.assertTrue(wf.is_file(), "haftalık drift workflow'u yok")
        text = wf.read_text(encoding="utf-8")
        self.assertIn("cron:", text)
        self.assertIn("check_protection_drift.py", text)
        self.assertIn("secrets.PROTECTION_PAT", text,
                      "okuma yetkisi secret'tan gelmeli")

    def test_gate_is_read_only(self):
        """Kapı API'ye YAZMAZ (yalnızca GET) — korumayı değiştirme yetkisi yok."""
        src = pathlib.Path(cpd.__file__).read_text(encoding="utf-8")
        for verb in ("-X POST", "-X PUT", "-X PATCH", "-X DELETE",
                     "--method POST", "--method PUT", "--method PATCH",
                     "--method DELETE"):
            self.assertNotIn(verb, src, "drift kapısı yazma çağrısı içeriyor")

    def test_reads_branch_protection_endpoint(self):
        src = pathlib.Path(cpd.__file__).read_text(encoding="utf-8")
        self.assertIn("branches/%s/protection", src)


if __name__ == "__main__":
    unittest.main()
