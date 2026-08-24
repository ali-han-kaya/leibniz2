#!/usr/bin/env python3
"""test_cleanup.py — K14 (cleanup_log.json silme/taşıma kayıtları) regresyon kapısı.

verify_delivery.check_cleanup, M0 §10 CLEANUP LOG'un makine-okunur aynası
olan cleanup_log.json'u okuyup dosya sistemindeki gerçek durumla karşılaştırır.
Bu test her kayıt türü (expect_absent / moved / canonical) ve hata yolunu
(resurrect / move-from / hash uyuşmazlığı / eksik / bozuk JSON) kapsar.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


def _collector():
    findings = []

    def add(pri, cid, check, issue, evidence=""):
        findings.append({"priority": pri, "id": cid, "check": check,
                         "issue": issue, "evidence": evidence})
    return findings, add


def _write(root, rel, content=b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


class CleanupCheckTest(unittest.TestCase):
    def test_all_clean(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            to = _write(root, "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip", b"toolkit")
            to_h = vd.sha256_file(str(to))
            canon = _write(root, "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip", b"outer")
            canon_h = vd.sha256_file(str(canon))
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({
                "expect_absent": [
                    {"path": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip", "note": "moved away"},
                    {"path": "_calisma/TESLIM_KLASOR_V5_2026-08-17.zip", "note": "rm"},
                ],
                "moved": [
                    {"from": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip",
                     "to": "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip",
                     "hash": to_h, "note": "move"},
                ],
                "canonical": [
                    {"path": "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip",
                     "hash": canon_h, "note": "canon"},
                ],
            }))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertTrue(ok)
            self.assertEqual(findings, [])
            self.assertIn("PASS (yok)", detail)
            self.assertIn("PASS (hash eşleşti)", detail)

    def test_resurrected_absent_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write(root, "_calisma/ALI_KOMUT_TOOLKIT_v3.zip", b"resurrected")
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"expect_absent": [
                {"path": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip", "note": "moved"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-RESURRECT" for f in findings))
            self.assertIn("FAIL (yol var)", detail)

    def test_moved_from_still_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write(root, "_calisma/ALI_KOMUT_TOOLKIT_v3.zip", b"still here")
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"moved": [
                {"from": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip",
                 "to": "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip",
                 "hash": "0" * 64, "note": "move"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-MOVE-FROM" for f in findings))
            self.assertIn("FAIL (kaynak hâlâ var)", detail)

    def test_moved_to_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write(root, "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip", b"tampered")
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"moved": [
                {"from": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip",
                 "to": "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip",
                 "hash": "0" * 64, "note": "move"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-MOVE-HASH" for f in findings))
            self.assertIn("FAIL (hash uyuşmuyor)", detail)

    def test_moved_to_absent_is_info(self):
        # from yok + to yok → INFO (CI fresh clone); hata değil.
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"moved": [
                {"from": "_calisma/ALI_KOMUT_TOOLKIT_v3.zip",
                 "to": "_calisma/TOOLKIT/ALI_KOMUT_TOOLKIT_v3.zip",
                 "hash": "0" * 64, "note": "move"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertTrue(ok)
            self.assertEqual(findings, [])
            self.assertIn("INFO (yok — gitignore/CI)", detail)

    def test_canonical_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip",
                 "hash": "0" * 64, "note": "canon"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-CANON-MISSING" for f in findings))
            self.assertIn("FAIL (yok)", detail)

    def test_canonical_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write(root, "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip", b"tampered")
            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip",
                 "hash": "0" * 64, "note": "canon"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-CANON-HASH" for f in findings))
            self.assertIn("FAIL (hash uyuşmuyor)", detail)

    def test_missing_log_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(root / "nope.json"), add,
                                          repo_root=str(root))
            self.assertTrue(ok)
            self.assertEqual(findings, [])
            self.assertIn("atlandı", detail)

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            log = root / "cleanup_log.json"
            log.write_text("{ not json")
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add, repo_root=str(root))
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K14-LOAD" for f in findings))


class TestResolveCanon(unittest.TestCase):
    """K14 _resolve_canon (nested inside check_cleanup) 3 senaryosu:

    _resolve_canon canonical kayıtların (zip/artifakt) hash'lerini doğrulamak
    için dosya yolunu --dir'e göre çözer. Üç senaryo:

    1. mirror root — TCC-safe mirror'da dosyalar basename ile durur.
       dir_arg = ~/Library/Caches/…/verify/ gibi düz bir ayna.
    2. CIKTI subdir — CI'da veya local CIKTI/ altında koşarken
       dir_arg = _calisma/CIKTI. Dosya zaten orada (basename).
    3. repo root — dir_arg = repo kökü. Dosya rel yolunda (örn.
       _calisma/CIKTI/TESLIM_KLASOR_V5_…) bulunur (full_candidate).

    Her senaryoda canonical kayıt hash eşleşmesiyle doğrulanır —
    check_cleanup çağrısına dir_arg geçilir ve PASS/hash-eşleşti döner.
    """

    def _runner(self, add):
        return vd.check_cleanup

    def test_canon_resolve_via_mirror_root(self):
        """Senaryo 1: dir_arg = flat mirror — dosya mirror root'ta (basename).

        Mirror'da TESLIM_KLASOR_V5_…zip doğrudan mirror kökünde durur.
        _resolve_canon: full_candidate (dir + rel) bulunamaz → basename'e düşer.
        """
        with tempfile.TemporaryDirectory() as td:
            mirror = pathlib.Path(td) / "mirror"
            mirror.mkdir()
            rel = "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip"
            # Mirror root'ta basename: TESLIM_KLASOR_V5_2026-08-17.zip
            canon = mirror / os.path.basename(rel)
            canon.write_bytes(b"mirror-canon")
            canon_h = vd.sha256_file(str(canon))

            # cleanup_log.json repo_root'a konur (sadece canonical bölümü kullanılır)
            log = mirror / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": rel, "hash": canon_h, "note": "mirror-basename"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add,
                                          repo_root=str(mirror),
                                          dir_arg=str(mirror))
            self.assertTrue(ok, f"mirror kanonik hash eşleşmeli: {detail}")
            self.assertEqual(findings, [])
            self.assertIn("PASS (hash eşleşti)", detail)

    def test_canon_resolve_via_cikti_subdir(self):
        """Senaryo 2: dir_arg = _calisma/CIKTI — dosya subdir'de (basename).

        CI'da --dir _calisma/CIKTI olarak geçilir. full_candidate
        (dir_arg + rel) çift önek oluşturur (CIKTI/CIKTI/…) → bulunamaz;
        basename'e düşer: dir_arg + basename → CIKTI/TESLIM_…zip.
        """
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            cikti = root / "_calisma" / "CIKTI"
            cikti.mkdir(parents=True)
            rel = "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip"
            # Dosya CIKTI'da (basename): TESLIM_KLASOR_V5_2026-08-17.zip
            canon = cikti / os.path.basename(rel)
            canon.write_bytes(b"cikti-canon")
            canon_h = vd.sha256_file(str(canon))

            log = cikti / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": rel, "hash": canon_h, "note": "cikti-basename"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add,
                                          repo_root=str(root),
                                          dir_arg=str(cikti))
            self.assertTrue(ok,
                            f"CIKTI subdir kanonik hash eşleşmeli: {detail}")
            self.assertEqual(findings, [])
            self.assertIn("PASS (hash eşleşti)", detail)

    def test_canon_resolve_via_repo_root(self):
        """Senaryo 3: dir_arg = repo root — dosya tam rel yolunda bulunur.

        Yerel çalıştırmada --dir . veya repo kökü geçilir.
        _resolve_canon: full_candidate (dir_arg + rel) vardır → direkt döner.
        """
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            rel = "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip"
            # Dosya tam yolunda: root/_calisma/CIKTI/TESLIM_…zip
            canon = root / rel
            canon.parent.mkdir(parents=True, exist_ok=True)
            canon.write_bytes(b"repo-canon")
            canon_h = vd.sha256_file(str(canon))

            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": rel, "hash": canon_h, "note": "repo-full-path"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add,
                                          repo_root=str(root),
                                          dir_arg=str(root))
            self.assertTrue(ok,
                            f"repo root kanonik hash eşleşmeli: {detail}")
            self.assertEqual(findings, [])
            self.assertIn("PASS (hash eşleşti)", detail)

    def test_canon_resolve_no_dir_arg_falls_back_to_repo_root(self):
        """dir_arg verilmezse repo_root + rel kullanılır (eski davranış).

        Mevcut testlerin davranışı korunur: dir_arg=None → repo_root/rel.
        """
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            rel = "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip"
            canon = root / rel
            canon.parent.mkdir(parents=True, exist_ok=True)
            canon.write_bytes(b"default-canon")
            canon_h = vd.sha256_file(str(canon))

            log = root / "cleanup_log.json"
            log.write_text(json.dumps({"canonical": [
                {"path": rel, "hash": canon_h, "note": "repo-no-dir"},
            ]}))
            findings, add = _collector()
            ok, detail = vd.check_cleanup(str(log), add,
                                          repo_root=str(root))
            self.assertTrue(ok, f"dir_arg'sız kanonik eşleşmeli: {detail}")
            self.assertEqual(findings, [])
            self.assertIn("PASS (hash eşleşti)", detail)


if __name__ == "__main__":
    unittest.main()
