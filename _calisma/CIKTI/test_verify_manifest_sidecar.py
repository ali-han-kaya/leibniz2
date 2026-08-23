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


def _with_python3_shell_section(d, mpath, tamper_combined=None):
    """manifest'e python3_shell bölümü ekler (files + combined_sha256).

    gen_repro_manifest.py'nin PYTHON3 SHELL bölümüyle birebir aynı formül:
    sorted '{rel}\0{hash}\n' birleşiminin SHA-256'sı. tamper_combined verilirse
    kayıtlı combined'ı bozar (K10 kurcalamayı yakalamalı).
    """
    with open(mpath, encoding="utf-8") as mf:
        m = json.load(mf)
    rel = "python3-shell/python3_shell_findings.json"
    ps_files = {rel: m["files"][rel]}
    combined = hashlib.sha256(
        "".join(f"{r}\0{ps_files[r]}\n" for r in sorted(ps_files)).encode()
    ).hexdigest()
    m["python3_shell"] = {
        "files": ps_files,
        "combined_sha256": (tamper_combined if tamper_combined else combined),
    }
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(m, f)
    # Sidecar'ı manifest'in yeni haline göre yeniden hesapla (K10'un diğer
    # bölüm denetimlerini gölgelememek için).
    real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
    with open(os.path.join(d, "manifest.sha256"), "w",
              encoding="utf-8") as f:
        f.write(f"{real}  manifest.json\n")
    return mpath


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
    """K13 repro self-testi artık sidecar'ı da denetliyor (K10 ile ortak).

    Sertleştirme: negatif senaryolar (eksik dosya, bozuk hash, config/ alt
    dizin) fail-closed yakalanmalı; eksik dosya kilitlenme yerine temiz
    'bundle dosyası yok' problemi üretmeli.
    """

    def test_self_test_includes_sidecar_pass(self):
        collector = _Collector()
        ok, detail = vd.check_repro_manifest_self_consistency(collector)
        self.assertTrue(ok, detail)
        self.assertIn("manifest.sha256: PASS", detail)
        self.assertEqual(collector.findings, [])

    def test_self_test_reports_negative_scenarios(self):
        """Happy path sağlamken 3 kurcalama senaryosu da yakalanmalı."""
        collector = _Collector()
        ok, detail = vd.check_repro_manifest_self_consistency(collector)
        self.assertTrue(ok, detail)
        self.assertIn("senaryolar: eksik-dosya PASS, bozuk-hash PASS, "
                      "config-alt-dizin PASS", detail)
        self.assertEqual(collector.findings, [])

    def _produce_once(self):
        """Mock artifact'ları üretip manifest'i yükler; (tmp, out, m) döner."""
        d = tempfile.mkdtemp(prefix="k13_sc_")
        art, out = vd._k13_write_mock(d)
        script = os.path.join(HERE, "gen_repro_manifest.py")
        rc, so, se = vd._k13_produce(script, art, out)
        self.assertEqual(rc, 0, so + se)
        with open(os.path.join(out, "manifest.json"), encoding="utf-8") as mf:
            m = json.load(mf)
        return d, out, m

    def test_verify_detects_missing_bundle_file(self):
        """Eksik dosya: kilitlenme DEĞİL, 'bundle dosyası yok' problemi."""
        d, out, m = self._produce_once()
        try:
            os.remove(os.path.join(out, "sub/b.bin"))
            ok, problems = vd._k13_verify_manifest(m, out)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("bundle dosyası yok: sub/b.bin", problems)

    def test_verify_detects_bad_hash(self):
        """Bozuk hash: manifest'teki SHA-256 gerçek dosyayla uyuşmazsa yakalanır."""
        d, out, m = self._produce_once()
        try:
            h = m["files"]["a.txt"]
            m["files"]["a.txt"] = ("0" if h[0] != "0" else "1") + h[1:]
            ok, problems = vd._k13_verify_manifest(m, out)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertTrue(any(p.startswith("SHA-256 uyuşmazlığı: a.txt")
                            for p in problems), problems)

    def test_verify_detects_config_subdir_removal(self):
        """config/ alt dizin dosyası config objesinden düşerse yakalanır."""
        d, out, m = self._produce_once()
        try:
            m["config"]["files"].pop("config/deep/extra.json")
            ok, problems = vd._k13_verify_manifest(m, out)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertTrue(any("config objesi" in p for p in problems), problems)

    def test_missing_bundle_file_does_not_crash(self):
        """Sertleştirme regresyonu: eksik dosya FileNotFoundError ile
        patlamamalı — problems listesine temiz girmeli."""
        d, out, m = self._produce_once()
        try:
            os.remove(os.path.join(out, "a.txt"))
            ok, problems = vd._k13_verify_manifest(m, out)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("bundle dosyası yok: a.txt", problems)

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


class TestPython3ShellSection(unittest.TestCase):
    """K10: python3_shell bölümünün combined_sha256'sı yeniden hesaplanıp
    doğrulanır; kurcalama → P1 (fail-closed)."""

    def test_pass_with_valid_python3_shell_section(self):
        files = {"a.txt": b"hello\n",
                 "python3-shell/python3_shell_findings.json": b'{"v": 1}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            _with_python3_shell_section(d, mpath)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertIn("python3_shell_combined_sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_tampered_combined_is_p1(self):
        files = {"a.txt": b"hello\n",
                 "python3-shell/python3_shell_findings.json": b'{"v": 1}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            _with_python3_shell_section(d, mpath, tamper_combined="0" * 64)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("python3_shell_combined_sha256: FAIL", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "python3_shell" in f[2]
            for f in findings))

    def test_missing_section_with_files_is_p1(self):
        # files'ta python3-shell/ dosyası var ama manifest'te python3_shell
        # objesi yok → üretici drift'i K10 tarafından yakalanmalı.
        files = {"a.txt": b"hello\n",
                 "python3-shell/python3_shell_findings.json": b'{"v": 1}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("python3_shell objesi eksik", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "python3_shell" in f[2]
            for f in findings))


def _with_overrides_section(d, mpath, tamper_combined=None):
    """manifest'e OVERRIDES bölümü ekler (files + combined_sha256).

    gen_repro_manifest.py'nin OVERRIDES bölümüyle birebir aynı formül:
    sorted '{rel}\0{hash}\n' birleşiminin SHA-256'sı. tamper_combined
    verilirse kayıtlı combined'ı bozar (K10 kurcalamayı yakalamalı).
    """
    with open(mpath, encoding="utf-8") as mf:
        m = json.load(mf)
    rel = "cli_overrides_version.json"
    ov_files = {rel: m["files"][rel]}
    combined = hashlib.sha256(
        "".join(f"{r}\0{ov_files[r]}\n" for r in sorted(ov_files)).encode()
    ).hexdigest()
    m["overrides"] = {
        "files": ov_files,
        "combined_sha256": (tamper_combined if tamper_combined else combined),
    }
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(m, f)
    # Sidecar'ı manifest'in yeni haline göre yeniden hesapla (K10'un diğer
    # bölüm denetimlerini gölgelememek için).
    real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
    with open(os.path.join(d, "manifest.sha256"), "w",
              encoding="utf-8") as f:
        f.write(f"{real}  manifest.json\n")
    return mpath


class TestOverridesSection(unittest.TestCase):
    """K10: OVERRIDES bölümünün combined_sha256'sı yeniden hesaplanıp
    doğrulanır; kurcalama → P1 (fail-closed). cli_overrides_version.json'un
    hash'i (dollar-sign içermeyen 64-hex SHA-256) manifest'te sabitlenir."""

    def test_pass_with_valid_overrides_section(self):
        files = {"a.txt": b"hello\n",
                 "cli_overrides_version.json": b'{"warning": false}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            _with_overrides_section(d, mpath)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertIn("overrides_combined_sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_tampered_combined_is_p1(self):
        files = {"a.txt": b"hello\n",
                 "cli_overrides_version.json": b'{"warning": false}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            _with_overrides_section(d, mpath, tamper_combined="0" * 64)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("overrides_combined_sha256: FAIL", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "overrides" in f[2]
            for f in findings))

    def test_section_hash_mismatch_with_files_is_p1(self):
        # overrides.files'taki hash, files'taki gerçek hash'ten farklı → P1.
        files = {"a.txt": b"hello\n",
                 "cli_overrides_version.json": b'{"warning": true}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            _with_overrides_section(d, mpath)
            with open(mpath, encoding="utf-8") as mf:
                m = json.load(mf)
            m["overrides"]["files"]["cli_overrides_version.json"] = "0" * 64
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(m, f)
            real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
            with open(os.path.join(d, "manifest.sha256"), "w",
                      encoding="utf-8") as f:
                f.write(f"{real}  manifest.json\n")
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("(hash farklı)", detail)
        self.assertIn("overrides_combined_sha256: FAIL", detail)

    def test_missing_section_with_files_is_p1(self):
        # files'ta cli_overrides_version.json var ama manifest'te overrides
        # objesi yok → üretici drift'i K10 tarafından yakalanmalı.
        files = {"a.txt": b"hello\n",
                 "cli_overrides_version.json": b'{"warning": false}\n'}
        d, mpath = _build_bundle(files=files)
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("overrides objesi eksik", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "overrides" in f[2]
            for f in findings))


def _with_precheck_section(d, mpath, tamper_combined=None):
    """manifest'e PRECHECK REPORT bölümü ekler (files + combined_sha256).

    gen_repro_manifest.py'nin PRECHECK REPORT bölümüyle birebir aynı formül:
    sorted '{rel}\0{hash}\n' birleşiminin SHA-256'sı. tamper_combined
    verilirse kayıtlı combined'ı bozar (K10 kurcalamayı yakalamalı).
    """
    with open(mpath, encoding="utf-8") as mf:
        m = json.load(mf)
    rel = "precheck-report/precheck_report.txt"
    pr_files = {rel: m["files"][rel]}
    combined = hashlib.sha256(
        "".join(f"{r}\0{pr_files[r]}\n" for r in sorted(pr_files)).encode()
    ).hexdigest()
    m["precheck_report"] = {
        "files": pr_files,
        "combined_sha256": (tamper_combined if tamper_combined else combined),
    }
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(m, f)
    real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
    with open(os.path.join(d, "manifest.sha256"), "w",
              encoding="utf-8") as f:
        f.write(f"{real}  manifest.json\n")
    return mpath


class TestPrecheckReportSection(unittest.TestCase):
    """K0O: precheck_report.combined_sha256 yeniden hesaplanıp doğrulanır;
    kurcalama → P1 (fail-closed). publish_precheck.sh AŞAMA 0 çıktısı
    manifest'te sabitlenir."""

    def test_pass_with_valid_precheck_section(self):
        files = {"a.txt": b"hello\n",
                 "precheck-report/precheck_report.txt": b"ADIM SONUCU: PASS\n"}
        d, mpath = _build_bundle(files=files)
        try:
            _with_precheck_section(d, mpath)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertIn("precheck_report_combined_sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_tampered_combined_is_p1(self):
        files = {"a.txt": b"hello\n",
                 "precheck-report/precheck_report.txt": b"ADIM SONUCU: PASS\n"}
        d, mpath = _build_bundle(files=files)
        try:
            _with_precheck_section(d, mpath, tamper_combined="0" * 64)
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("precheck_report_combined_sha256: FAIL", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "precheck_report" in f[2]
            for f in findings))

    def test_section_hash_mismatch_with_files_is_p1(self):
        # precheck_report.files'taki hash, files'taki gerçek hash'ten farklı → P1.
        files = {"a.txt": b"hello\n",
                 "precheck-report/precheck_report.txt": b"ADIM SONUCU: FAIL\n"}
        d, mpath = _build_bundle(files=files)
        try:
            _with_precheck_section(d, mpath)
            with open(mpath, encoding="utf-8") as mf:
                m = json.load(mf)
            m["precheck_report"]["files"]["precheck-report/precheck_report.txt"] = "0" * 64
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(m, f)
            real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
            with open(os.path.join(d, "manifest.sha256"), "w",
                      encoding="utf-8") as f:
                f.write(f"{real}  manifest.json\n")
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("(hash farklı)", detail)
        self.assertIn("precheck_report_combined_sha256: FAIL", detail)

    def test_missing_section_with_files_is_p1(self):
        # files'ta precheck dosyası var ama manifest'te precheck_report
        # objesi yok → üretici drift'i K10 tarafından yakalanmalı.
        files = {"a.txt": b"hello\n",
                 "precheck-report/precheck_report.txt": b"ADIM SONUCU: PASS\n"}
        d, mpath = _build_bundle(files=files)
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("precheck_report objesi eksik", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "precheck_report" in f[2]
            for f in findings))

    def test_absent_precheck_bundle_passes_k10(self):
        # precheck-report artifact'ı hiç üretilmedi (advisory — macOS'te
        # push'ta çalışmayabilir): manifest'te precheck_report anahtarı da
        # OLMAMALI. Bundlesız + anahtarsız → K10 PASS (sorun değil).
        files = {"a.txt": b"hello\n"}
        d, mpath = _build_bundle(files=files)
        try:
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertTrue(ok, detail)
        self.assertIn("precheck_report_combined_sha256: PASS", detail)
        self.assertEqual(findings, [])

    def test_phantom_empty_section_is_p1(self):
        # Absent durumda manifest'te precheck_report anahtarı OLMAMALI.
        # Üretici drift: anahtar var ama files boş (bundle'da dosya yok) →
        # K10 P1 vermeli (fail-closed).
        files = {"a.txt": b"hello\n"}
        d, mpath = _build_bundle(files=files)
        try:
            with open(mpath, encoding="utf-8") as mf:
                m = json.load(mf)
            m["precheck_report"] = {"files": {},
                                    "combined_sha256": "0" * 64}
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(m, f)
            real = hashlib.sha256(open(mpath, "rb").read()).hexdigest()
            with open(os.path.join(d, "manifest.sha256"), "w",
                      encoding="utf-8") as f:
                f.write(f"{real}  manifest.json\n")
            ok, detail, findings = _run(d, mpath)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("precheck_report_combined_sha256: FAIL", detail)
        self.assertTrue(any(
            f[1] == "K10-MANIFEST" and "precheck_report" in f[2]
            for f in findings))


if __name__ == "__main__":
    unittest.main()
