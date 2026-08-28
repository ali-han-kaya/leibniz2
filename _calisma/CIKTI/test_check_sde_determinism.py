#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_sde_determinism.py — K21 SDE determinism guard birim testleri.

Skill prosedürü (skills/verify-chain/SKILL.md "Adding a new K-layer") adım 5'e
göre: exit contract (P0/P1/INFO), pozitif + negatif senaryo, fail-closed kanıt.

Kapı sözleşmesi (check_sde_determinism):
  * Aynı SDE + aynı girdiler → iki zip üretimi BİREBİR aynı SHA-256 (determinizm).
  * Farklı SDE → farklı hash (SDE etkili — wall-clock'a kaymıyor).
  * Girdi sırası değişimi hash'i değiştirmeli (üretici sıra-bağımlı).
  * Bu üçü ihlal edilirse P0 (fail-closed) + K21 katmanı FAIL.
  * check_sde_determinism dışsal durum kullanmaz — her ortamda aynı sonucu
    verir (deterministik test).
"""
import hashlib
import os
import sys
import tempfile
import pathlib
import unittest
from unittest import mock

CIKTI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CIKTI)
import verify_delivery as vd  # noqa: E402

ENTRIES = [(b"a.txt", b"hello\n"), (b"sub/b.txt", b"world\n")]
SDE = 1700000000


def _run_check(add=None):
    """check_sde_determinism'i çalıştır; (ok, detail, findings) döner."""
    findings = []
    add = add or (lambda *a: findings.append(a))
    ok, detail = vd.check_sde_determinism(add)
    return ok, detail, findings


class TestDeterminism(unittest.TestCase):
    def test_same_sde_same_hash(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="k21-") as td:
            z1 = os.path.join(td, "z1.zip")
            z2 = os.path.join(td, "z2.zip")
            vd._sde_zip(ENTRIES, z1, SDE)
            vd._sde_zip(ENTRIES, z2, SDE)
            self.assertEqual(_sha256(z1), _sha256(z2),
                             "aynı SDE iki üretim aynı hash üretmeli")

    def test_sde_change_changes_hash(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="k21-") as td:
            z1 = os.path.join(td, "z1.zip")
            z3 = os.path.join(td, "z3.zip")
            vd._sde_zip(ENTRIES, z1, SDE)
            vd._sde_zip(ENTRIES, z3, SDE + 3600)
            self.assertNotEqual(_sha256(z1), _sha256(z3),
                                "farklı SDE farklı hash üretmeli (SDE etkili)")

    def test_order_change_changes_hash(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="k21-") as td:
            z1 = os.path.join(td, "z1.zip")
            z4 = os.path.join(td, "z4.zip")
            vd._sde_zip(ENTRIES, z1, SDE)
            vd._sde_zip(list(reversed(ENTRIES)), z4, SDE)
            self.assertNotEqual(_sha256(z1), _sha256(z4),
                                "girdi sırası hash'i değiştirmeli (sıra-bağımlılık)")


class TestFrozenRecord(unittest.TestCase):
    def test_frozen_record_is_checked_by_k21(self):
        findings = []
        ok, detail = vd.check_sde_frozen_record(lambda *a: findings.append(a))
        self.assertFalse(ok)
        self.assertIn("PENDING", detail)
        self.assertTrue(any(item[1] == "K21-SDE-RECORD" for item in findings))

    def test_frozen_record_contract_passes_without_pending(self):
        with tempfile.TemporaryDirectory(prefix="k21-record-") as td:
            root = pathlib.Path(td)
            experiment = root / "sde_determinism_experiment.py"
            record = root / "sde_determinism_output.txt"
            experiment.write_text("FROZEN_RECORD SOURCE_DATE_EPOCH --rerun DETERMINISTIC NON-DETERMINISTIC")
            record.write_text("FROZEN_RECORD SOURCE_DATE_EPOCH --rerun DETERMINISTIC NON-DETERMINISTIC\\n")
            with mock.patch.object(vd, "_sde_experiment_paths", return_value=(str(experiment), str(record))):
                ok, detail = vd.check_sde_frozen_record(lambda *a: self.fail(a))
            self.assertTrue(ok, detail)


class TestCheckSde(unittest.TestCase):
    def test_pass(self):
        ok, detail, findings = _run_check()
        self.assertTrue(ok, detail)
        self.assertEqual(findings, [])
        self.assertIn("aynı SDE → aynı hash", detail)
        self.assertIn("SDE etkili", detail)

    def test_fail_when_same_sde_differs(self):
        # Bozuk üretici: her çağrıda farklı byte üret (aynı SDE'ye rağmen).
        calls = {"n": 0}

        def broken_zip(entries, out_zip, sde):
            calls["n"] += 1
            with __import__("zipfile").ZipFile(
                    out_zip, "w", __import__("zipfile").ZIP_DEFLATED) as zf:
                for rel, data in entries:
                    info = __import__("zipfile").ZipInfo(
                        rel.decode("utf-8"), date_time=__import__("time").gmtime(sde)[:6])
                    info.compress_type = __import__("zipfile").ZIP_DEFLATED
                    zf.writestr(info, data + bytes([calls["n"]]))  # drift!

        findings = []
        with mock.patch.object(vd, "_sde_zip", side_effect=broken_zip):
            ok, detail = vd.check_sde_determinism(
                lambda *a: findings.append(a))
        self.assertFalse(ok)
        self.assertIn("fail-closed", detail)
        self.assertTrue(any(f[0] == "P0" and f[1] == "K21-SDE" for f in findings))

    def test_fail_when_sde_inert(self):
        # SDE'yi yoksayan üretici: farklı SDE aynı hash → P0.
        real_zip = vd._sde_zip

        def inert_zip(entries, out_zip, sde):
            # sde argümanını yoksay — hep aynı SDE (etkisiz); 1980 öncesi
            # ZIP tarafından reddedildiği için sabit geçerli değer kullan.
            real_zip(entries, out_zip, SDE)

        findings = []
        with mock.patch.object(vd, "_sde_zip", side_effect=inert_zip):
            ok, detail = vd.check_sde_determinism(
                lambda *a: findings.append(a))
        self.assertFalse(ok)
        self.assertIn("SDE etkisiz", detail)
        self.assertTrue(any(f[1] == "K21-SDE" for f in findings))

    def test_deterministic_across_runs(self):
        # Aynı girdi → iki ayrı koşum aynı hash üretmeli (self-test tekrarı).
        import tempfile
        hashes = []
        for _ in range(2):
            with tempfile.TemporaryDirectory(prefix="k21-") as td:
                z = os.path.join(td, "z.zip")
                vd._sde_zip(ENTRIES, z, SDE)
                hashes.append(_sha256(z))
        self.assertEqual(hashes[0], hashes[1])


def _full_ns(**kw):
    """build_layers_summary için tüm getter alanlarını taşıyan namespace."""
    import argparse
    ns = argparse.Namespace(
        symbolic_proof=False, lean_proof=False, verify_manifest=None,
        check_config_drift=False, check_plist=False, check_repro_manifest=False,
        check_cleanup=False, check_history=None, check_github_scripts=False,
        check_mirror=False, check_daemon=False, coq_proof=False,
        check_launchd=False, check_sde=False)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class TestK21Wiring(unittest.TestCase):
    def test_layer_label(self):
        self.assertEqual(vd.LAYER_LABELS["K21"], "SDE determinism guard")

    def test_optional_getter(self):
        import argparse
        ns = argparse.Namespace(check_sde=True)
        self.assertTrue(vd._OPTIONAL_LAYERS["K21"](ns))
        ns.check_sde = False
        self.assertFalse(vd._OPTIONAL_LAYERS["K21"](ns))

    def test_full_enables_k21(self):
        import argparse
        ns = argparse.Namespace(
            full=True, check_references=False, symbolic_proof=False,
            lean_proof=False, check_lineage=False, check_repro_manifest=False,
            check_config_drift=False, check_cleanup=False,
            check_github_scripts=False, check_mirror=False,
            mirror_auto_sync=False, check_daemon=False, coq_proof=False,
            check_history=None, check_sde=False)
        ns = vd.apply_full_flags(ns)
        self.assertTrue(ns.check_sde, "--full K21'i aktifleştirmeli")

    def test_klayers_k21_pass(self):
        layers = vd.build_layers_summary(_full_ns(check_sde=True), [])
        self.assertEqual(layers["K21"]["status"], "PASS")
        self.assertTrue(layers["K21"]["ran"])

    def test_klayers_k21_skip_when_disabled(self):
        layers = vd.build_layers_summary(_full_ns(check_sde=False), [])
        self.assertEqual(layers["K21"]["status"], "SKIP")

    def test_klayers_k21_fail_on_finding(self):
        ns = _full_ns(check_sde=True)
        findings = [{"priority": "P0", "id": "K21-SDE",
                     "check": "K21 SDE determinism",
                     "message": "aynı SDE deterministik değil",
                     "detail": "fail-closed"}]
        layers = vd.build_layers_summary(ns, findings)
        self.assertEqual(layers["K21"]["status"], "FAIL")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    unittest.main()
