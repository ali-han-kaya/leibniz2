"""test_check_zip_lineage_drift.py — K14 commit-time drift gate regression tests.

Conventions follow the repo's check_*.py suites (stdlib unittest, tempdirs).
Covers: pass, lineage-current drift (P0), canonical drift (P0), UNVERIFIED
missing live files, and the live repo contract (currently drifted by design
until the registry resync lands).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_zip_lineage_drift as gate  # noqa: E402

ZIP = "TESLIM_KLASOR_V5_2026-08-17.zip"


def _mk_repo(tmp: str, zip_bytes: bytes, lineage_cur: str, canon: list) -> str:
    """Build a minimal fake repo root with CIKTI/ records + zips."""
    cikti = os.path.join(tmp, "_calisma", "CIKTI")
    os.makedirs(cikti, exist_ok=True)
    with open(os.path.join(cikti, ZIP), "wb") as f:
        f.write(zip_bytes)
    with open(os.path.join(cikti, "zip_lineage.json"), "w", encoding="utf-8") as f:
        json.dump({
            "path_in_repo": f"_calisma/CIKTI/{ZIP}",
            "generations": [
                {"note": "old", "hash": "0" * 64, "commit": None, "current": False},
                {"note": "gen", "hash": lineage_cur, "commit": None, "current": True},
            ],
        }, f)
    with open(os.path.join(cikti, "cleanup_log.json"), "w", encoding="utf-8") as f:
        json.dump({"canonical": canon}, f)
    return tmp


class TestLineageCurrent(unittest.TestCase):
    def test_pass_when_current_hash_matches_live_zip(self):
        data = b"zip-bytes"
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, data, h, [])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)

    def test_p0_when_current_hash_differs_from_live_zip(self):
        import hashlib
        h = hashlib.sha256(b"stale-generation").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"live-bytes", h, [])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 1)

    def test_p0_when_no_current_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", "0" * 64, [])
            with open(os.path.join(tmp, "_calisma", "CIKTI", "zip_lineage.json"), "w") as f:
                json.dump({"path_in_repo": f"_calisma/CIKTI/{ZIP}",
                           "generations": [{"note": "x", "hash": "0" * 64,
                                            "commit": None, "current": False}]}, f)
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 1)

    def test_unverified_when_live_zip_absent(self):
        import hashlib
        h = hashlib.sha256(b"anything").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", h, [])
            os.remove(os.path.join(tmp, "_calisma", "CIKTI", ZIP))
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)  # UNVERIFIED — blocks nothing (CI parity)


class TestCleanupCanonical(unittest.TestCase):
    def test_pass_when_canonical_hash_matches(self):
        data = b"canonical-bytes"
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        rec = {"path": f"_calisma/CIKTI/{ZIP}", "hash": h, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, data, h, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(0, rc)

    def test_p0_when_canonical_hash_differs(self):
        import hashlib
        live = hashlib.sha256(b"live-bytes").hexdigest()
        recorded = hashlib.sha256(b"recorded-elsewhere").hexdigest()
        rec = {"path": f"_calisma/CIKTI/{ZIP}", "hash": recorded, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"live-bytes", live, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(1, rc)

    def test_unverified_when_canonical_file_absent(self):
        import hashlib
        live = hashlib.sha256(b"zip").hexdigest()  # lineage must match live zip
        h = hashlib.sha256(b"x").hexdigest()       # canonical rec: file absent
        rec = {"path": "_calisma/CIKTI/does_not_exist.zip", "hash": h, "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            _mk_repo(tmp, b"zip", live, [rec])
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(0, rc)


class TestVerifyDeliveryConstantParity(unittest.TestCase):
    """K14 kapısı verify_delivery ile AYNI sidecar adını ve paket yolunu kullanır.

    check_zip_lineage_drift.py stdlib-only kalsın diye verify_delivery'yi
    import ETMEZ; bu yüzden drift'i burada fail-closed pinleriz (kanonik
    çekirdek id_canonical.py zaten ortak — tek kalan elle eşleşme bu iki
    sabittir).
    """

    @classmethod
    def setUpClass(cls):
        src = open(os.path.join(HERE, "verify_delivery.py"),
                   encoding="utf-8").read()
        cls.vd_pkg = re.search(r'^PKG_REL = "([^"]+)"', src,
                               re.M).group(1)
        cls.vd_sidecar = re.search(r'^PDF_METADATA_SIDECAR = "([^"]+)"',
                                   src, re.M).group(1)

    def test_sidecar_name_matches_verify_delivery(self):
        self.assertEqual(gate.SIDECAR_NAME, self.vd_sidecar)

    def test_pkg_rel_is_repo_relative_form_of_verify_delivery(self):
        # verify_delivery.PKG_REL ZIP-çıkarma köküne göre; kapınınki repo
        # köküne göre → V5_ICERIK önekiyle başlar, son ek birebir aynı.
        self.assertEqual(gate.PKG_REL, "_calisma/V5_ICERIK/" + self.vd_pkg)


class TestSidecarCanonical(unittest.TestCase):
    """Sidecar `# canonical:` referansı ↔ kabul defteri (Faz 4, P0).

    repack motor geçişinde sidecar'ı bilinçli yeniler ve yazma anında defterde
    arar (fail-closed). Bu kapı AYNI iki kaynağı commit anında karşılaştırır:
    referans defterde yoksa P0; `# canonical:` satırı YOKSA (henüz yenilenmemiş
    sidecar) INFO — engellemez. Defter `ID_RESIDUAL_LEDGER` env'i ile izole
    edilir.
    """

    def _mk_sidecar(self, tmp, text):
        d = os.path.join(tmp, gate.PKG_REL)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, gate.SIDECAR_NAME), "w",
                  encoding="utf-8") as f:
            f.write(text)

    def _mk_ledger(self, tmp, token):
        path = os.path.join(tmp, "ID_RESIDUAL_ACCEPTANCE.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{token}  ingiliz_empirizmi_v3.pdf\n")
        return path

    def _run(self, tmp, ledger):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ,
                             {gate.id_canonical.LEDGER_ENV: ledger}), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = gate.main(["--repo-root", tmp])
        return rc, out.getvalue(), err.getvalue()

    def test_pass_when_sidecar_canonical_in_ledger(self):
        token = "c" * 64
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._mk_ledger(tmp, token)
            self._mk_sidecar(tmp, "stripped  ingiliz_empirizmi_v3.pdf.metadata\n"
                                  f"# canonical: {token}  ingiliz_empirizmi_v3.pdf\n")
            rc, out, _ = self._run(tmp, ledger)
        self.assertEqual(rc, 0)
        self.assertIn("defterde kayıtlı", out)

    def test_p0_when_sidecar_canonical_not_in_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._mk_ledger(tmp, "a" * 64)
            self._mk_sidecar(tmp, "stripped  ingiliz_empirizmi_v3.pdf.metadata\n"
                                  f"# canonical: {'d' * 64}  ingiliz_empirizmi_v3.pdf\n")
            rc, _, err = self._run(tmp, ledger)
        self.assertEqual(rc, 1)
        self.assertIn("kabul defterinde yok", err)
        self.assertIn("LEDGER=update", err)  # uygulanabilir remedy

    def test_info_when_no_canonical_line(self):
        # Henüz yenilenmemiş sidecar (yalnız ham/stripped) → engellemez.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._mk_ledger(tmp, "a" * 64)
            self._mk_sidecar(tmp, "stripped  ingiliz_empirizmi_v3.pdf.metadata\n"
                                  "# raw: rrr  ingiliz_empirizmi_v3.pdf\n")
            rc, out, _ = self._run(tmp, ledger)
        self.assertEqual(rc, 0)
        self.assertIn("# canonical: referansı yok", out)


class TestMissingRegistries(unittest.TestCase):
    def test_missing_registries_are_info_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = gate.main(["--repo-root", tmp])
        self.assertEqual(rc, 0)


class TestLiveDriftContract(unittest.TestCase):
    def test_real_repo_is_in_sync_after_resync(self):
        """Live contract: after the 9507909 registry resync, the gate must PASS on the real repo."""
        rc = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_zip_lineage_drift.py")],
            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 0,
                         f"expected in-sync PASS (exit 0) after resync, got {rc.returncode}:\n{rc.stderr}")


class TestCleanupCanonicalLiveFailClosed(unittest.TestCase):
    """Fail-closed: cleanup_log.json canonical[].hash must equal live zip SHA-256.

    K14 drift was the release blocker (b69de33 repack left stale hashes).
    check_zip_lineage_drift.py's commit-time gate catches it, but this unit
    test pins the invariant directly: every canonical entry → live file exists
    and hash is byte-identical. Missing file or hash drift → hard FAIL (P0
    semantics), not UNVERIFIED. Uses stdlib only, no network.
    """

    def test_cleanup_canonical_hashes_match_live_zips(self):
        repo_root = getattr(gate, "REPO_ROOT", os.path.abspath(os.path.join(HERE, "..", "..")))
        cleanup_path = os.path.join(repo_root, "_calisma", "CIKTI", "cleanup_log.json")
        self.assertTrue(os.path.isfile(cleanup_path),
                        f"cleanup_log.json missing (fail-closed): {cleanup_path}")
        with open(cleanup_path, encoding="utf-8") as f:
            data = json.load(f)
        canonical = data.get("canonical", [])
        self.assertGreater(len(canonical), 0, "cleanup_log.json canonical list empty (fail-closed)")
        for rec in canonical:
            rel = rec.get("path", "")
            want = rec.get("hash", "")
            self.assertTrue(rel, f"canonical entry missing path: {rec}")
            self.assertTrue(want, f"canonical entry missing hash: {rel}")
            self.assertRegex(want, r"^[0-9a-f]{64}$", f"invalid hash for {rel}: {want!r}")
            live_path = os.path.join(repo_root, rel)
            self.assertTrue(os.path.isfile(live_path),
                            f"canonical live file missing (fail-closed P0): {rel} → {live_path}")
            got = gate.sha256_file(live_path)
            self.assertIsNotNone(got, f"sha256 failed for {live_path}")
            self.assertEqual(got, want,
                             f"canonical hash mismatch (fail-closed P0): {rel} "
                             f"want={want} got={got} — run repack_delivery.py + registry resync")


if __name__ == "__main__":
    unittest.main()
