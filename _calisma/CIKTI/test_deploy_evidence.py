#!/usr/bin/env python3
"""test_deploy_evidence.py — deploy_evidence.py sözleşme-süiti.

Kalıcı dağıtım-kanıtı defteri (docs/DEPLOY_EVIDENCE.md) sözleşmesi:

  1) collect: her çekirdek workflow (verify/docker-security/test-smoke/
     determinism-trend) için main-dalındaki son koşum haritalanır;
     koşum-yok "koşum-yok" ile dürüstçe raporlanır.
  2) append: defter append-only — mevcut satırlar asla ezilmez; başlık/
     ayraç kolon-seti bu betiğin sözleşmesidir, eskimişse tazelenir.
  3) azure: resource-health tek kolonu (collect_azure, az rest) — okunamayan
     her durum açık damgayla yazılır (az-yok/rg-yok/oturum-yok/kaynak-yok/
     hata); sessiz-PASS yok. azure_proven gerçek okumayı damgadan ayırır.
  4) --check bayat-kanıt koruması: son satırın HEAD'i mevcut origin/main
     ucuyla aynıysa rc=0, farklıysa rc=1 (fail-closed); --require-azure
     ayrıca son satırda gerçek Azure okuması şart koşar.
  5) rc-kontratı: 0 güncel/eklendi, 1 bayat/eksik-azure, 2 kullanım/ortam.
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import deploy_evidence as de  # noqa: E402

# Defterin gemideki (2026-09-22 öncesi) kolon-seti: migration'ı kanıtlar.
OLD_HEADERS = ("| Tarih | HEAD (origin/main) | verify-delivery |"
               " docker-security | test-smoke | determinism-trend |")
OLD_SEP = "|---|---|---|---|---|---|"

APP_ID = ("/subscriptions/s1/resourceGroups/rg-x/providers/Microsoft.App/"
          "containerApps/app-verify-dashboard")


class TestCollect(unittest.TestCase):
    def test_collect_maps_latest_runs_per_workflow(self):
        def fake_gh(argv):
            joined = " ".join(argv)
            if "commits/main" in joined:
                # gh --jq .sha çıktısı bare JSON-string'tir (dict değil)
                return 0, de.json.dumps("a" * 40)
            if "run" in argv and "list" in argv:
                wf = argv[argv.index("--workflow") + 1]
                data = {
                    "verify.yml": [{"databaseId": 1, "conclusion": "success",
                                    "headSha": "a" * 40, "url": "u1"}],
                    "docker-security.yml": [{"databaseId": 2,
                                             "conclusion": "success",
                                             "headSha": "a" * 40,
                                             "url": "u2"}],
                }
                return 0, de.json.dumps(data.get(wf, []))
            return 1, "unexpected"
        ev, err = de.collect("main", fake_gh)
        self.assertEqual(err, "")
        self.assertEqual(ev["sha"], "a" * 40)
        self.assertEqual(ev["runs"]["verify.yml"]["databaseId"], 1)
        self.assertIsNone(ev["runs"]["test-smoke.yml"])  # dürüst yok-bildirimi

    def test_collect_gh_failure_is_usage_error(self):
        rc, msg = de.collect("main", lambda a: (1, "boom"))
        self.assertIsNone(rc)
        self.assertIn("boom", msg)

    def test_collect_accepts_bare_hex_sha(self):
        """Gerçek-gh şekli: --jq .sha çıktısı bare-hex (JSON-değil)."""
        def fake_gh(argv):
            if "commits/main" in " ".join(argv):
                return 0, "a" * 40  # bare-hex, tırnaksız
            return 0, "[]"
        ev, err = de.collect("main", fake_gh)
        self.assertEqual(err, "")
        self.assertEqual(ev["sha"], "a" * 40)


class TestAzureHealth(unittest.TestCase):
    """Azure kolonu: gerçek okuma linkli; her arıza açık damga (sessiz-PASS yok)."""

    def _az(self, payload, rc=0):
        def fake(argv):
            if argv[:2] == ["rest", "--method"]:
                return rc, payload
            return 1, "unexpected"
        return fake

    def _no_login(self):
        def fake(argv):
            if argv[:2] == ["account", "show"]:
                return 1, "ERROR: Please run 'az login' to setup account."
            return 1, "unexpected"
        return fake

    def test_available_maps_state_to_portal_link(self):
        payload = de.json.dumps({"id": APP_ID,
                                 "properties": {"availabilityState": "Available"}})
        ev = de.collect_azure(self._az(payload), "rg-x", subscription="s1")
        self.assertEqual(ev["state"], "Available")
        self.assertIn("portal.azure.com/#resource" + APP_ID, ev["cell"])
        self.assertTrue(de.azure_proven(ev["cell"]))

    def test_missing_resource_group_is_marked_not_measured(self):
        ev = de.collect_azure(self._az("{}"), "  ", subscription="s1")
        self.assertEqual(ev["cell"], "rg-yok")
        self.assertFalse(de.azure_proven(ev["cell"]))

    def test_no_login_is_marked_with_reason(self):
        with mock.patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": ""}):
            ev = de.collect_azure(self._no_login(), "rg-x")
        self.assertEqual(ev["cell"], "oturum-yok")
        self.assertIn("az login", ev["note"])
        self.assertFalse(de.azure_proven(ev["cell"]))

    def test_subscription_from_env_skips_account_show(self):
        def fake(argv):
            self.assertNotEqual(argv[:2], ["account", "show"])
            if argv[:2] == ["rest", "--method"]:
                return 0, de.json.dumps({"id": APP_ID, "properties": {
                    "availabilityState": "Degraded"}})
            return 1, "unexpected"
        with mock.patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": "env-sub"}):
            ev = de.collect_azure(fake, "rg-x")
        self.assertEqual(ev["state"], "Degraded")

    def test_not_found_is_marked_resource_missing(self):
        ev = de.collect_azure(self._az("ERROR: (ResourceNotFound) ...", rc=1),
                              "rg-x", subscription="s1")
        self.assertEqual(ev["cell"], "kaynak-yok")
        self.assertFalse(de.azure_proven(ev["cell"]))

    def test_other_error_is_marked_with_note(self):
        ev = de.collect_azure(self._az("ERROR: network unreachable", rc=1),
                              "rg-x", subscription="s1")
        self.assertEqual(ev["cell"], "hata")
        self.assertIn("network", ev["note"])

    def test_unparsable_payload_is_marked(self):
        ev = de.collect_azure(self._az("not-json"), "rg-x", subscription="s1")
        self.assertEqual(ev["cell"], "hata")

    def test_missing_state_field_is_marked(self):
        ev = de.collect_azure(self._az(de.json.dumps({"id": APP_ID})),
                              "rg-x", subscription="s1")
        self.assertEqual(ev["cell"], "hata")

    def test_azure_proven_separates_reads_from_markers(self):
        self.assertTrue(de.azure_proven("[Available](https://x)"))
        self.assertTrue(de.azure_proven("Available"))
        for marker in de.AZURE_MARKERS:
            self.assertFalse(de.azure_proven(marker), marker)

    def test_empty_cell_is_not_proof(self):
        """Boş hücre sessiz-PASS olamaz (kolon-öncesi satırlar)."""
        self.assertFalse(de.azure_proven(""))
        self.assertFalse(de.azure_proven("   "))

    def test_collect_azure_requests_resource_health_endpoint(self):
        seen = []

        def fake(argv):
            seen.append(" ".join(argv))
            return 0, de.json.dumps({"id": APP_ID,
                                     "properties": {
                                         "availabilityState": "Available"}})
        de.collect_azure(fake, "rg-x", subscription="s1")
        self.assertEqual(len(seen), 1)
        self.assertIn("Microsoft.ResourceHealth/availabilityStatuses/current",
                      seen[0])
        self.assertIn("api-version=" + de.AZURE_HEALTH_API, seen[0])
        self.assertIn(de.AZURE_APP, seen[0])


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dep_ev_")
        self.path = os.path.join(self.tmp, "DEPLOY_EVIDENCE.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# Defter\n\n## Kanıt-defteri\n\n" + OLD_HEADERS +
                    "\n" + OLD_SEP + "\n")

    def _rows(self):
        with open(self.path, encoding="utf-8") as f:
            return [ln for ln in f if ln.startswith("| 2")]

    def test_append_adds_row_and_keeps_old(self):
        ev = {"sha": "a" * 40, "runs": {"verify.yml": {
            "databaseId": 1, "conclusion": "success", "url": "u1"}}}
        de.append_entry(self.path, "2026-09-22", ev)
        de.append_entry(self.path, "2026-09-23", ev)
        rows = self._rows()
        self.assertEqual(len(rows), 2)  # append-only: eski satır duruyor
        self.assertIn("u1", rows[-1])
        self.assertIn("a" * 7, rows[-1])

    def test_last_sha_parse(self):
        ev = {"sha": "b" * 40, "runs": {}}
        de.append_entry(self.path, "2026-09-22", ev)
        # Defter-satırı 7-haneli kısa-SHA tutar (--check karşılaştırması)
        self.assertEqual(de.last_sha(self.path), "b" * 7)
        self.assertEqual(de.last_sha(os.path.join(self.tmp, "yok.md")), "")

    def test_append_migrates_old_header_to_new_column_set(self):
        de.append_entry(self.path, "2026-09-22", {"sha": "c" * 40, "runs": {}})
        with open(self.path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertIn(de.LEDGER_HEADERS, lines)
        self.assertIn(de.LEDGER_SEP, lines)
        self.assertNotIn(OLD_HEADERS, lines)
        self.assertEqual(lines.count(de.LEDGER_HEADERS), 1)

    def test_append_writes_azure_cell(self):
        ev = {"sha": "d" * 40, "runs": {},
              "azure": {"cell": "[Available](https://portal.azure.com/#resource/x)",
                        "state": "Available"}}
        de.append_entry(self.path, "2026-10-06", ev)
        row = self._rows()[-1]
        self.assertTrue(row.rstrip().endswith("[Available](https://portal.azure.com/#resource/x) |"))
        self.assertTrue(de.azure_proven(de.last_cell(self.path)))

    def test_append_without_azure_is_honest_not_silent(self):
        de.append_entry(self.path, "2026-09-22", {"sha": "e" * 40, "runs": {}})
        self.assertEqual(de.last_cell(self.path), "ölçülmedi")
        self.assertFalse(de.azure_proven(de.last_cell(self.path)))

    def test_last_cell_empty_for_missing_file(self):
        self.assertEqual(de.last_cell(os.path.join(self.tmp, "yok.md")), "")

    def test_last_cell_rejects_pre_column_row(self):
        """Eski 6-kolonlu satırın son hücresi azure-health SAYILMAZ."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("| 2026-09-22 | da58b14 | [success #1](u1) | [success #2](u2)"
                    " | [success #3](u3) | [failure #4](u4) |\n")
        self.assertEqual(de.LEDGER_COLUMNS, 7)
        self.assertEqual(de.last_cell(self.path), "")
        self.assertFalse(de.azure_proven(de.last_cell(self.path)))


class TestCheckGate(unittest.TestCase):
    """--check kapıları: tazelik + --require-azure kanıt şartı (fail-closed)."""

    SHA = "f" * 40

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dep_ev_check_")
        self.ledger = os.path.join(self.tmp, "DEPLOY_EVIDENCE.md")
        self._saved = (de.LEDGER, de.GH)
        de.LEDGER, de.GH = self.ledger, self._gh

    def tearDown(self):
        de.LEDGER, de.GH = self._saved

    def _gh(self, argv):
        if "commits/main" in " ".join(argv):
            return 0, self.SHA
        return 0, "[]"

    def _ledger(self, azure_cell):
        with open(self.ledger, "w", encoding="utf-8") as f:
            f.write("## Kanıt-defteri\n\n" + de.LEDGER_HEADERS + "\n" +
                    de.LEDGER_SEP + "\n")
            f.write(f"| 2026-10-06 | {self.SHA[:7]} | koşum-yok | koşum-yok |"
                    f" koşum-yok | koşum-yok | {azure_cell} |\n")

    def _run(self, argv):
        buf = io.StringIO()
        with mock.patch.object(de.shutil, "which", return_value="/usr/bin/gh"):
            with contextlib.redirect_stdout(buf):
                rc = de.main(argv)
        return rc, buf.getvalue()

    def test_fresh_ledger_with_azure_proof_passes(self):
        self._ledger("[Available](https://portal.azure.com/#resource/x)")
        rc, out = self._run(["--check", "--require-azure"])
        self.assertEqual(rc, 0)
        self.assertIn("GUNCEL", out)

    def test_fresh_ledger_with_marker_fails_required_azure(self):
        self._ledger("oturum-yok")
        rc, out = self._run(["--check", "--require-azure"])
        self.assertEqual(rc, 1)
        self.assertIn("AZURE-KANITI-YOK", out)

    def test_marker_allowed_without_require_flag(self):
        self._ledger("oturum-yok")
        rc, _ = self._run(["--check"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
