#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_doc_protection_count.py — doküman ↔ canlı koruma sayı kapısının testleri.

Kapı (`check_doc_protection_count.py`) iki ayrı gerçeği karşılaştırır:
PUBLISH_SCENARIO.md'de YAZAN required-check sayısı ile GitHub branch
protection API'sinin DÖNDÜRDÜĞÜ context sayısı. İkisi ayrışırsa operatör
dokümanı doğru sanıp eksik seçim yapar — bu yüzden uyuşmazlık rc=1, ölçüm
imkânsızlığı rc=2'dir (sessiz yeşil yok).

Katmanlar:
  1. SAF SAYIM: GET şeması (`checks[].context`) ve PUT şeması (`contexts[]`)
     aynı sayıyı vermeli; `required_status_checks: null` gerçek bir cevap (0),
     eksik/bozuk alan ise ölçümsüzlük (MeasurementError).
  2. BEYAN OKUMA: çapalar `check_status_check_doc_sync.SITES`'ten gelir;
     mutasyon (9 yazılmış doküman) yakalanmalı, kayıp/çift çapa fail-closed.
  3. CLI: eşleşme rc=0, uyuşmazlık rc=1 (her beyan için doküman↔API),
     token yok / bozuk dosya / okunamayan API rc=2. `--json` tek doküman.

stdlib unittest — ağ/gh gerekmez (fetch mock'lanır, dosya yolu kullanılır).
"""

import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import check_doc_protection_count as gate   # noqa: E402
import check_status_check_doc_sync as docs  # noqa: E402

SCRIPT = HERE / "check_doc_protection_count.py"


def _protection(contexts=None, checks=None, strict=True):
    sc = {"strict": strict}
    if contexts is not None:
        sc["contexts"] = contexts
    if checks is not None:
        sc["checks"] = [{"context": c} for c in checks]
    return {"required_status_checks": sc, "enforce_admins": {"enabled": True}}


class ApiCountTests(unittest.TestCase):
    """GET (`checks`) ve PUT (`contexts`) şemaları aynı sayıyı vermeli."""

    def test_contexts_are_counted(self):
        self.assertEqual(
            gate.api_required_count(_protection(contexts=["a", "b", "c"])), 3)

    def test_checks_fallback_is_counted(self):
        self.assertEqual(
            gate.api_required_count(_protection(checks=["a", "b"])), 2)

    def test_empty_list_is_zero_not_unreadable(self):
        self.assertEqual(gate.api_required_count(_protection(contexts=[])), 0)

    def test_null_required_status_checks_is_zero(self):
        """Kural kurulu değil = gerçek cevap 0 (uyuşmazlık olarak raporlanır)."""
        self.assertEqual(
            gate.api_required_count({"required_status_checks": None}), 0)

    def test_missing_key_is_unreadable(self):
        with self.assertRaises(gate.MeasurementError):
            gate.api_required_count({"enforce_admins": {"enabled": True}})

    def test_malformed_shape_is_unreadable(self):
        for body in ({"required_status_checks": "yok"},
                     {"required_status_checks": {"strict": True}},
                     ["liste"]):
            with self.assertRaises(gate.MeasurementError, msg=repr(body)):
                gate.api_required_count(body)


class DocClaimsTests(unittest.TestCase):
    """Doküman beyanları tek kaynaktan (SITES) ve fail-closed okunmalı."""

    @classmethod
    def setUpClass(cls):
        cls.claims = gate.doc_claims(ROOT)

    def test_every_required_site_is_read(self):
        expected = [s["id"] for s in docs.SITES
                    if s["file"] == docs.PUBLISH and "required" in s["fields"]]
        self.assertEqual([c["site"] for c in self.claims], expected,
                         "SITES'teki required çapaları eksik/fazla okundu")

    def test_real_doc_claims_one_number(self):
        """Dokümanın tüm required beyanları aynı sayıyı söylemeli."""
        self.assertTrue(self.claims)
        self.assertEqual(sorted({c["doc"] for c in self.claims}),
                         [self.claims[0]["doc"]],
                         "PUBLISH_SCENARIO.md kendi içinde tutarsız")

    def test_mutated_doc_is_read_not_hardcoded(self):
        text = (ROOT / docs.PUBLISH).read_text(encoding="utf-8")
        site = "ps-webui-heading"
        pattern = [s for s in docs.SITES if s["id"] == site][0]["pattern"]
        m = re.search(pattern, text, re.M)
        self.assertIsNotNone(m)
        mutant = text[:m.start(1)] + "9" + text[m.end(1):]
        claims = {c["site"]: c["doc"] for c in gate.doc_claims(text=mutant)}
        self.assertEqual(claims[site], 9, "mutant değer okunmadı")

    def test_lost_anchor_fails_closed(self):
        text = (ROOT / docs.PUBLISH).read_text(encoding="utf-8")
        stripped = "\n".join(line for line in text.splitlines()
                             if "web UI adım adım" not in line)
        self.assertNotIn("web UI adım adım", stripped)
        with self.assertRaises(gate.MeasurementError):
            gate.doc_claims(text=stripped)

    def test_ambiguous_anchor_fails_closed(self):
        text = (ROOT / docs.PUBLISH).read_text(encoding="utf-8")
        anchor = [s for s in docs.SITES
                  if s["id"] == "ps-webui-heading"][0]["pattern"]
        line = re.search(anchor, text, re.M).group(0)
        with self.assertRaises(gate.MeasurementError):
            gate.doc_claims(text=text + "\n" + line + "\n")


class CompareTests(unittest.TestCase):
    def test_match_has_no_findings(self):
        self.assertEqual(gate.compare([{"site": "a", "doc": 3}], 3), [])

    def test_mismatch_names_every_site(self):
        claims = [{"site": "a", "doc": 3}, {"site": "b", "doc": 3}]
        self.assertEqual(
            [f["site"] for f in gate.compare(claims, 2)], ["a", "b"])


class CliTests(unittest.TestCase):
    """Gerçek giriş noktası: rc + JSON sözleşmesi."""

    def _run(self, *argv, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *argv],
                              capture_output=True, text=True, cwd=ROOT,
                              env=env)

    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _file(self, body, name="protection.json"):
        path = self.td / name
        path.write_text(json.dumps(body), encoding="utf-8")
        return str(path)

    def _expected(self):
        return gate.doc_claims(ROOT)[0]["doc"]

    def test_match_is_rc0(self):
        path = self._file(_protection(contexts=["x"] * self._expected()))
        r = self._run("--protection-file", path, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["api_required"], self._expected())
        self.assertEqual(payload["findings"], [])

    def test_mismatch_is_rc1_and_names_doc_and_api(self):
        path = self._file(_protection(contexts=["x"] * (self._expected() - 2)))
        r = self._run("--protection-file", path, "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertTrue(payload["findings"])
        self.assertTrue(all(f["api"] == self._expected() - 2
                            for f in payload["findings"]))
        self.assertTrue(all(f["doc"] == self._expected()
                            for f in payload["findings"]))

    def test_unset_protection_rule_is_a_failure_not_a_pass(self):
        path = self._file({"required_status_checks": None})
        r = self._run("--protection-file", path)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("API 0", r.stdout)

    def test_broken_json_is_rc2(self):
        path = self.td / "broken.json"
        path.write_text("{oops", encoding="utf-8")
        r = self._run("--protection-file", str(path))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("ÖLÇÜM İMKÂNSIZ", r.stderr)

    def test_missing_file_is_rc2(self):
        r = self._run("--protection-file", str(self.td / "yok.json"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_missing_token_is_rc2_not_pass(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PROTECTION_PAT", "GH_ADMIN_TOKEN")}
        r = self._run("--json", env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "ERROR")


class ApiPathTests(unittest.TestCase):
    """`gh` yolu (fetch) mock'lanır: hata rc2, başarı rc0 olmalı."""

    def _main(self, protection, token="tok"):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(gate.cpd, "token_from_env", return_value=token), \
             mock.patch.object(gate.cpd, "repo_slug",
                               return_value=("owner/name", None)), \
             mock.patch.object(gate.cpd, "fetch_protection",
                               return_value=protection):
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = out, err
            try:
                rc = gate.main(["--json"])
            finally:
                sys.stdout, sys.stderr = old_out, old_err
        text = out.getvalue()
        return rc, (json.loads(text) if text.strip() else None), err.getvalue()

    def test_api_match_passes(self):
        need = gate.doc_claims(ROOT)[0]["doc"]
        rc, payload, _ = self._main((_protection(contexts=["x"] * need), None))
        self.assertEqual(rc, 0)
        self.assertEqual(payload["verdict"], "PASS")

    def test_unreadable_api_is_rc2(self):
        rc, payload, _ = self._main((None, "HTTP 403: Resource not accessible"))
        self.assertEqual(rc, 2)
        self.assertEqual(payload["verdict"], "ERROR")
        self.assertIn("403", payload["error"])

    def test_branch_is_forwarded(self):
        called = {}

        def _fetch(repo, token, branch=gate.BRANCH):
            called.update(repo=repo, branch=branch)
            return _protection(contexts=["x"] * gate.doc_claims(ROOT)[0]["doc"]), None

        with mock.patch.object(gate.cpd, "token_from_env", return_value="t"), \
             mock.patch.object(gate.cpd, "repo_slug",
                               return_value=("owner/name", None)), \
             mock.patch.object(gate.cpd, "fetch_protection", side_effect=_fetch):
            with mock.patch("sys.stdout", new=io.StringIO()):
                rc = gate.main(["--branch", "release"])
        self.assertEqual(rc, 0)
        self.assertEqual(called, {"repo": "owner/name", "branch": "release"})


if __name__ == "__main__":
    unittest.main()
