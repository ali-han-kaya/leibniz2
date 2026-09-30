#!/usr/bin/env python3
"""test_deploy_evidence.py — deploy_evidence.py sözleşme-süiti.

Kalıcı dağıtım-kanıtı defteri (docs/DEPLOY_EVIDENCE.md) sözleşmesi:

  1) collect: her çekirdek workflow (verify/docker-security/test-smoke/
     determinism-trend) için main-dalındaki son koşum haritalanır;
     koşum-yok "-" ile dürüstçe raporlanır.
  2) append: defter append-only — mevcut satırlar asla ezilmez.
  3) --check bayat-kanıt koruması: son satırın HEAD'i mevcut origin/main
     ucuyla aynıysa rc=0, farklıysa rc=1 (fail-closed).
  4) rc-kontratı: 0 güncel/eklendi, 1 bayat, 2 kullanım/ortam (gh yok).
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import deploy_evidence as de  # noqa: E402

HEADERS = ("| Tarih | HEAD (origin/main) | verify-delivery | docker-security |"
           " test-smoke | determinism-trend |")


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


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dep_ev_")
        self.path = os.path.join(self.tmp, "DEPLOY_EVIDENCE.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# Defter\n\n## Kanıt-defteri\n\n" + HEADERS +
                    "\n|---|---|---|---|---|---|\n")

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


if __name__ == "__main__":
    unittest.main()
