#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_manifest_sidecar.py — K10 manifest.sha256 ↔ manifest.json kapısı.

verify_delivery.verify_manifest_digest'in (K10) sidecar denetimini kapsar:
gen_repro_manifest.py manifest.json'un yanına sha256sum biçiminde
"{hex}  manifest.json" sidecar'ı yazar; K10, manifest dosyasının KENDİ
hash'ini bu sidecar'la fail-closed eşleştirir.

Kapsanan durumlar:
  - eşleşen sidecar (metin biçimi `  ` ve ikili biçim ` *`) → PASS
  - sidecar YOK → P1 (fail-closed)
  - manifest.json'a JSON boşluk kurcalaması (dosya hash'leri DEĞİŞMEZ ama
    manifest.json hash'i değişir) → sidecar uyuşmazlığı → P1 — sidecar'ın
    varlık nedeni tam olarak budur
  - dosya adı alanı 'manifest.json' değil → P1
  - sha256sum biçiminde olmayan içerik → P1
  - uçtan uca: gen_repro_manifest.py ile üret → K10 PASS; kurcala → FAIL

stdlib unittest; ek bağımlılık yok — CI `test_*.py` deseniyle otomatik koşar.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_delivery as vd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class _Collector:
    def __init__(self):
        self.findings = []

    def __call__(self, pri, cid, check, issue, evidence=""):
        self.findings.append((pri, cid, issue))


def _build_bundle(files=None, sidecar=None, tamper_json=None):
    """tmp dizinde manifest bundle'ı kur; (dir, manifest_path) döndür.

    files: {rel: bytes}. sidecar: None → üret (doğru), str → ham içerik,
    False → sidecar hiç yazma. tamper_json: str → manifest.json sonuna ekle.
    """
    d = tempfile.mkdtemp(prefix="k10_sc_")
    files = files or {"a.txt": b"hello\n", "sub/b.bin": b"\x00\x01\x02"}
    for rel, data in files.items():
        fp = os.path.join(d, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(data)
    m = {"files": {rel: hashlib.sha256(data).hexdigest()
                   for rel, data in files.items()}}
    mpath = os.path.join(d, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(m, f)
    # Sidecar'ı ÖNCE yaz (pre-tamper içerik üzerinden hesaplanır) — böylece
    # tamper senaryosu gerçek kurcalamayı modeller: sidecar eski, içerik yeni.
    if sidecar is not False:
        with open(mpath, "rb") as mf:
            real = hashlib.sha256(mf.read()).hexdigest()
        content = (sidecar if isinstance(sidecar, str)
                   else f"{real}  manifest.json\n")
        with open(os.path.join(d, "manifest.sha256"), "w",
                  encoding="utf-8") as f:
            f.write(content)
    if tamper_json:
        with open(mpath, "a", encoding="utf-8") as f:
            f.write(tamper_json)
    return d, mpath


def _run(d, mpath):
    collector = _Collector()
    ok, detail = vd.verify_manifest_digest(mpath, collector)
    return ok, detail, collector.findings


class TestSidecarPass(unittest.TestCase):
    def test_matching_text_format(self):
        d, mpath = _build_bundle()
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertIn("manifest.sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_matching_binary_format(self):
        # sha256sum -b çıktısı: "{hex} *manifest.json" — tolerans.
        d, mpath = _build_bundle()
        real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
        with open(os.path.join(d, "manifest.sha256"), "w",
                  encoding="utf-8") as f:
            f.write(f"{real} *manifest.json\n")
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertEqual(findings, [])


class TestSidecarFail(unittest.TestCase):
    def test_missing_sidecar_is_p1(self):
        d, mpath = _build_bundle(sidecar=False)
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("manifest.sha256: FAIL", detail)
        self.assertTrue(any(f[1] == "K10-MANIFEST" and "sidecar" in f[2]
                            for f in findings))

    def test_json_tamper_breaks_sidecar_even_when_file_hashes_intact(self):
        # manifest.json'a boşluk ekle: içindeki files hash'leri AYNI kalır
        # (K10'un dosya denetimi PASS der) ama manifest.json'un kendi hash'i
        # değişir → sidecar uyuşmazlığı yakalanmalı. Sidecar'ın varoluş nedeni.
        d, mpath = _build_bundle(tamper_json=" ")
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("hash uyuşmazlığı", detail)
        # Dosya hash'leri bozulmadı — yalnızca sidecar FAIL.
        self.assertIn("0 uyuşmazlık / 0 eksik", detail)
        self.assertTrue(any("uyuşmuyor" in f[2] for f in findings))

    def test_wrong_filename_field_is_p1(self):
        d, mpath = _build_bundle()
        real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
        with open(os.path.join(d, "manifest.sha256"), "w",
                  encoding="utf-8") as f:
            f.write(f"{real}  manifest.txt\n")
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("dosya adı", detail)
        self.assertTrue(any("dosya adı" in f[2] for f in findings))

    def test_unparseable_sidecar_is_p1(self):
        d, mpath = _build_bundle(sidecar="bu bir sha256sum değil")
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("biçim geçersiz", detail)
        self.assertTrue(any("biçim" in f[2] for f in findings))

    def test_bad_hex_sidecar_is_p1(self):
        # 64 hex değil (63) → biçim geçersiz.
        d, mpath = _build_bundle(sidecar="a" * 63 + "  manifest.json\n")
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)


class TestK13SelfTest(unittest.TestCase):
    """K13 repro self-testi artık sidecar'ı da denetliyor (K10 ile ortak)."""

    def test_self_test_includes_sidecar_pass(self):
        collector = _Collector()
        ok, detail = vd.check_repro_manifest_self_consistency(collector)
        self.assertTrue(ok, detail)
        self.assertIn("manifest.sha256: PASS", detail)
        self.assertEqual(collector.findings, [])

    def test_self_test_fails_on_sidecar_mismatch(self):
        # Üretici yanlış sidecar yazarsa K13 fail-closed patlamalı:
        # helper'ı, gerçek helper'ın add() yan etkisiyle birlikte sahte bozuk
        # sonuçla taklit et (üretici içeride çalıştığı için gerçek bundle'a
        # müdahale edemeyiz — helper kontratını test eder).
        real = vd._check_manifest_sidecar

        def fake(mpath, add, cid, cl):
            add("P1", cid, cl, "manifest.sha256 manifest.json ile uyuşmuyor",
                "hash uyuşmazlığı")
            return False, ["hash uyuşmazlığı"]
        vd._check_manifest_sidecar = fake
        try:
            collector = _Collector()
            ok, detail = vd.check_repro_manifest_self_consistency(collector)
        finally:
            vd._check_manifest_sidecar = real
        self.assertFalse(ok)
        self.assertIn("manifest.sha256: FAIL — hash uyuşmazlığı", detail)
        self.assertTrue(any(f[1] == "K13-REPRO" for f in collector.findings))

    def test_self_test_reports_missing_sidecar(self):
        # Helper'ın 'eksik' dalı K13'te de P1 üretmeli.
        real = vd._check_manifest_sidecar
        vd._check_manifest_sidecar = lambda mpath, add, cid, cl: \
            (False, ["eksik"])
        try:
            collector = _Collector()
            ok, detail = vd.check_repro_manifest_self_consistency(collector)
        finally:
            vd._check_manifest_sidecar = real
        self.assertFalse(ok)
        self.assertIn("manifest.sha256: FAIL — eksik", detail)


class TestEndToEnd(unittest.TestCase):
    """gen_repro_manifest.py üretimi → K10 PASS; kurcalama → K10 FAIL."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="k10_e2e_")
        cls.art = os.path.join(cls.tmp, "artifacts")
        cls.out = os.path.join(cls.tmp, "out")
        file_cfg = b'{"budget_usd": 30.0, "budget_method": "both"}'
        eff_cfg = (b'{"budget_usd": 30.0, "budget_method": "both", '
                   b'"cli_overrides": {'
                   b'"budget": {"cli_given": false, "cli_value": null, '
                   b'"file_value": 30.0, "effective": 30.0, "override": false}, '
                   b'"budget_method": {"cli_given": false, "cli_value": null, '
                   b'"file_value": "both", "effective": "both", '
                   b'"override": false}}}')
        for rel, data in (("a.txt", b"hello A\n"),
                          ("sub/b.bin", b"\x00\x01\x02\x03"),
                          ("config/cfg.json", b'{"k": 1}'),
                          # merge-multiple düzleştirmesi: config dosyaları
                          # KÖKTE (config/ öneki yok) — isimle tanınmalı.
                          ("effective_config.json", eff_cfg),
                          ("verify_delivery.config.json", file_cfg),
                          ("config-diff.json", b'{"diffs": []}')):
            fp = os.path.join(cls.art, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(data)
        env = dict(os.environ)
        env.update({"GITHUB_RUN_ID": "k10-e2e",
                    "GITHUB_SHA": "mock", "GITHUB_REF": "refs/heads/test"})
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "gen_repro_manifest.py"),
             "--artifacts-dir", cls.art, "--out-dir", cls.out],
            capture_output=True, text=True, env=env, timeout=60)
        cls.gen_rc = r.returncode

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_generated_bundle_passes_k10(self):
        self.assertEqual(self.gen_rc, 0, "gen_repro_manifest.py başarısız")
        ok, detail, findings = _run(self.out,
                                    os.path.join(self.out, "manifest.json"))
        self.assertTrue(ok, detail)
        self.assertIn("manifest.sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_tampered_bundle_fails_k10(self):
        mpath = os.path.join(self.out, "manifest.json")
        with open(mpath, "a", encoding="utf-8") as f:
            f.write("\n")
        ok, detail, _ = _run(self.out, mpath)
        self.assertFalse(ok)
        self.assertIn("manifest.sha256: FAIL", detail)


if __name__ == "__main__":
    unittest.main()
