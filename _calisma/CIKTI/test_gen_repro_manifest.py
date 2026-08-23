#!/usr/bin/env python3
"""test_gen_repro_manifest.py — gen_repro_manifest.py regresyon kapısı.

Kapsanan bölümler:
  PROVENANCE — artifact → job kaynağı (precommit-logs/config prefixed indirme)
  BUNDLE/HASH/CONFIG — manifest.json'daki her SHA-256 gerçek dosyayla birebir
      eşleşmeli; hashlanan HER dosya bundle'a kopyalanmış olmalı; config/
      dosyaları ayrı bölümde işaretlenir ve config.combined_sha256 sıralı
      'rel\0hash\n' birleşiminden deterministik olarak yeniden hesaplanabilmeli
      (K10 bu değeri verify_delivery.py'de aynen yeniden hesaplar).
  WORKFLOW — merge pattern'i ARTIFACT_JOBS'ı eksiksiz kapsar, CLI senkron.
  SIDECAR — manifest.sha256: canonical sha256sum -c uyumu (CI'nın ayrı
      doğrulama adımıyla aynı sözleşme), kesin biçim, öz-tutarlılık, hash
      tablosu determinizmi (zaman damgası bilinçli provenance alanıdır —
      byte-determinizm sözü başlık için değil, files/config içindir),
      içerik değişikliğine duyarlılık, kurcalama → sha256sum FAIL.
  BUNDLE — tam içerik sözleşmesi (artifact kopyaları + manifest üçlüsü,
      fazla dosya yok), dizin yapısı korunumu, boş girdi, boş dosya hash'i
      (bilinen sabit), artifact kopyalarının run'lar arası byte determinizmi,
      üreticinin artifacts dizinini DEĞİŞTİRMEMESİ (yan etkisizlik).

stdlib unittest + subprocess — ek bağımlılık yok (sha256sum varsa kullanılır,
bulunamazsa o testler dürüstçe SKIP edilir).
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
GEN = CIKTI / "gen_repro_manifest.py"
sys.path.insert(0, str(CIKTI))

import gen_repro_manifest as gen_manifest  # noqa: E402


def _run_gen(artifacts_dir, out_dir):
    r = subprocess.run(
        ["python3", str(GEN), "--artifacts-dir", artifacts_dir,
         "--out-dir", out_dir],
        capture_output=True, text=True,
    )
    return r


class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        (self.artifacts / "config").mkdir(parents=True)
        (self.artifacts / "precommit-logs").mkdir(parents=True)
        (self.artifacts / "config" / "verify_delivery.config.json").write_text(
            "raw\n", encoding="utf-8")
        (self.artifacts / "precommit-logs" / "precommit.log").write_text(
            "log\n", encoding="utf-8")
        (self.artifacts / "precommit-logs" / "commit_msg_findings.json").write_text(
            json.dumps({"checked": 3, "violations": []}) + "\n", encoding="utf-8")
        (self.artifacts / "verify_report.txt").write_text(
            "flat\n", encoding="utf-8")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_manifest_json_has_artifact_jobs(self):
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["precommit-logs"], "verify")
        self.assertEqual(jobs["config"], "verify")
        self.assertEqual(jobs["budget"], "budget")
        self.assertEqual(jobs["repack-verify"], "repack-verify")

    def test_manifest_txt_provenance_section(self):
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PROVENANCE (artifact → job kaynağı)", txt)
        self.assertIn("precommit-logs", txt)
        self.assertIn("prefixed (2 dosya)", txt)  # precommit-logs: precommit.log + commit_msg_findings.json

    def test_prefixed_files_present_in_bundle(self):
        self._gen()
        # gen_repro_manifest.py bundle'a kopyalar → rel yol korunmalı.
        self.assertTrue(
            (self.out / "precommit-logs" / "precommit.log").is_file())
        self.assertTrue(
            (self.out / "precommit-logs" / "commit_msg_findings.json").is_file())
        self.assertTrue(
            (self.out / "config" / "verify_delivery.config.json").is_file())

    def test_precommit_logs_section(self):
        # PRECOMMIT_CACHE.md dahil precommit-logs/ dosyaları CONFIG gibi ayrı
        # bölümde işaretlenir + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "precommit-logs" / "PRECOMMIT_CACHE.md").write_text(
            "cache\n", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PRECOMMIT LOGS ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("precommit_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        pc = m["precommit_logs"]
        self.assertIn(
            "precommit-logs/PRECOMMIT_CACHE.md", pc["files"])
        self.assertTrue(len(pc["combined_sha256"]) == 64)

    def test_refs_trend_section(self):
        # refs-trend/ dosyaları (refs_trend.py çıktısı) CONFIG gibi ayrı
        # bölümde işaretlenir + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "refs-trend").mkdir(parents=True)
        (self.artifacts / "refs-trend" / "refs-trend.md").write_text(
            "trend\n", encoding="utf-8")
        (self.artifacts / "refs-trend" / "refs-trend.json").write_text(
            "{}", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("REFS TREND ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("refs_trend_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        rt = m["refs_trend"]
        self.assertIn("refs-trend/refs-trend.md", rt["files"])
        self.assertIn("refs-trend/refs-trend.json", rt["files"])
        self.assertTrue(len(rt["combined_sha256"]) == 64)

    def test_refs_trend_artifact_job_provenance(self):
        (self.artifacts / "refs-trend").mkdir(parents=True)
        (self.artifacts / "refs-trend" / "refs-trend.md").write_text(
            "trend\n", encoding="utf-8")
        (self.artifacts / "refs-trend" / "refs-trend.json").write_text(
            "{}", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["refs-trend"], "refs-trend")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("prefixed (2 dosya)", txt)  # refs-trend 2 dosya

    def test_lineage_section(self):
        # lineage-findings/ dosyaları CONFIG gibi ayrı bölümde işaretlenir
        # + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "lineage-findings").mkdir(parents=True)
        (self.artifacts / "lineage-findings" / "zip_lineage.json").write_text(
            '{"generations": []}', encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("LINEAGE ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("lineage_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ln = m["lineage"]
        self.assertIn(
            "lineage-findings/zip_lineage.json", ln["files"])
        self.assertTrue(len(ln["combined_sha256"]) == 64)

    def test_lineage_combined_recomputes_deterministically(self):
        (self.artifacts / "lineage-findings").mkdir(parents=True)
        (self.artifacts / "lineage-findings" / "zip_lineage.json").write_text(
            '{"generations": []}', encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ln = m["lineage"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{ln[rel]}\n" for rel in sorted(ln)).encode()
        ).hexdigest()
        self.assertEqual(m["lineage"]["combined_sha256"], expected)
        self.assertRegex(m["lineage"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_lineage_artifact_job_provenance(self):
        (self.artifacts / "lineage-findings").mkdir(parents=True)
        (self.artifacts / "lineage-findings" / "zip_lineage.json").write_text(
            '{"generations": []}', encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["lineage-findings"], "verify")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("köke düzleştirildi (1 dosya)", txt)  # lineage-findings merge ile köke düzleşti

    def test_no_lineage_section_when_absent(self):
        # lineage-findings/ hiç yoksa manifest.json'da 'lineage' anahtarı
        # da olmamalı (boş bölüm şişirmek yerine yok sayılır).
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("lineage", m)
        self.assertIn("a.txt", m["files"])

    def test_summary_section(self):
        # Run summary sidecar dosyaları (klayers.json, vb.) CONFIG gibi
        # ayrı bölümde işaretlenir + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "klayers.json").write_text(
            '{"layers": {}}', encoding="utf-8")
        (self.artifacts / "k0_findings.json").write_text(
            '{"count": 0}', encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("SUMMARY ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("summary_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        sm = m["summary"]
        self.assertIn("klayers.json", sm["files"])
        self.assertIn("k0_findings.json", sm["files"])
        self.assertTrue(len(sm["combined_sha256"]) == 64)

    def test_summary_combined_recomputes_deterministically(self):
        (self.artifacts / "klayers.json").write_text(
            '{"layers": {}}', encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        sm = m["summary"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{sm[rel]}\n" for rel in sorted(sm)).encode()
        ).hexdigest()
        self.assertEqual(m["summary"]["combined_sha256"], expected)
        self.assertRegex(m["summary"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_no_summary_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("summary", m)

    def test_precheck_report_section(self):
        # precheck-report/ dosyaları CONFIG gibi ayrı bölümde işaretlenir
        # + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "precheck-report").mkdir(parents=True)
        (self.artifacts / "precheck-report" / "precheck_report.txt").write_text(
            "SONUC: PASS\n", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PRECHECK REPORT ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("precheck_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        pr = m["precheck_report"]
        self.assertIn(
            "precheck-report/precheck_report.txt", pr["files"])
        self.assertTrue(len(pr["combined_sha256"]) == 64)

    def test_precheck_combined_recomputes_deterministically(self):
        (self.artifacts / "precheck-report").mkdir(parents=True)
        (self.artifacts / "precheck-report" / "precheck_report.txt").write_text(
            "SONUC: PASS\n", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        pr = m["precheck_report"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{pr[rel]}\n" for rel in sorted(pr)).encode()
        ).hexdigest()
        self.assertEqual(m["precheck_report"]["combined_sha256"], expected)
        self.assertRegex(m["precheck_report"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_precheck_artifact_job_provenance(self):
        (self.artifacts / "precheck-report").mkdir(parents=True)
        (self.artifacts / "precheck-report" / "precheck_report.txt").write_text(
            "SONUC: PASS\n", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["precheck-report"], "precheck")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("prefixed (1 dosya)", txt)  # precheck-report tek dosya

    def test_no_precheck_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("precheck_report", m)

    def test_python3_shell_section(self):
        # python3-shell/ dosyaları (check_python3_shell.py --json çıktısı)
        # CONFIG gibi ayrı bölümde işaretlenir + tek-hash combined_sha256.
        (self.artifacts / "python3-shell").mkdir(parents=True)
        (self.artifacts / "python3-shell" / "python3_shell_findings.json").write_text(
            json.dumps({"tool": "check_python3_shell.py", "verdict": "PASS",
                        "fail": 0}) + "\n", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PYTHON3 SHELL ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("python3_shell_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ps = m["python3_shell"]
        self.assertIn(
            "python3-shell/python3_shell_findings.json", ps["files"])
        self.assertTrue(len(ps["combined_sha256"]) == 64)

    def test_python3_shell_combined_recomputes_deterministically(self):
        (self.artifacts / "python3-shell").mkdir(parents=True)
        (self.artifacts / "python3-shell" / "python3_shell_findings.json").write_text(
            json.dumps({"tool": "check_python3_shell.py", "verdict": "PASS"})
            + "\n", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ps = m["python3_shell"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{ps[rel]}\n" for rel in sorted(ps)).encode()
        ).hexdigest()
        self.assertEqual(m["python3_shell"]["combined_sha256"], expected)
        self.assertRegex(m["python3_shell"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_python3_shell_artifact_job_provenance(self):
        (self.artifacts / "python3-shell").mkdir(parents=True)
        (self.artifacts / "python3-shell" / "python3_shell_findings.json").write_text(
            "{}", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["python3-shell"], "verify")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("prefixed (1 dosya)", txt)  # python3-shell tek dosya

    def test_no_python3_shell_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("python3_shell", m)

    # ── MIRROR CHECK section tests ───────────────────────────────────
    def test_mirror_check_section(self):
        # mirror-check/ dosyaları (K17 raporu + --mirror-out sidecar +
        # bootstrap smoke) CONFIG gibi ayrı bölümde işaretlenir +
        # tek-hash combined_sha256 özetlenir.
        (self.artifacts / "mirror-check").mkdir(parents=True)
        (self.artifacts / "mirror-check" / "mirror_check_report.txt").write_text(
            "[K17] mirror sync: PASS\n", encoding="utf-8")
        (self.artifacts / "mirror-check" / "mirror_report.json").write_text(
            json.dumps({"tool": "verify_delivery.py --check-mirror",
                        "exit": 0, "auto_synced": True}) + "\n",
            encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("MIRROR CHECK ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("mirror_check_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        mc = m["mirror_check"]
        self.assertIn("mirror-check/mirror_check_report.txt", mc["files"])
        self.assertIn("mirror-check/mirror_report.json", mc["files"])
        self.assertTrue(len(mc["combined_sha256"]) == 64)

    def test_mirror_check_combined_recomputes_deterministically(self):
        (self.artifacts / "mirror-check").mkdir(parents=True)
        (self.artifacts / "mirror-check" / "mirror_report.json").write_text(
            json.dumps({"exit": 0, "auto_synced": False}) + "\n",
            encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        mc = m["mirror_check"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{mc[rel]}\n" for rel in sorted(mc)).encode()
        ).hexdigest()
        self.assertEqual(m["mirror_check"]["combined_sha256"], expected)
        self.assertRegex(m["mirror_check"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_mirror_check_artifact_job_provenance(self):
        (self.artifacts / "mirror-check").mkdir(parents=True)
        (self.artifacts / "mirror-check" / "mirror_report.json").write_text(
            "{}", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["mirror-check"], "mirror-check")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("prefixed (1 dosya)", txt)  # mirror-check tek dosya

    def test_no_mirror_check_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("mirror_check", m)

    # ── DAEMON HTTP section tests ────────────────────────────────────
    def test_daemon_http_section(self):
        # daemon-http/ dosyaları (daemon_http_test.py raporu + K15 sidecar
        # + override report) CONFIG gibi ayrı bölümde işaretlenir +
        # tek-hash combined_sha256 özetlenir.
        (self.artifacts / "daemon-http").mkdir(parents=True)
        (self.artifacts / "daemon-http" / "daemon_http_report.json").write_text(
            json.dumps({"ok": True, "endpoints": {"/api/latest": 200},
                        "daemon_alive": True}) + "\n", encoding="utf-8")
        (self.artifacts / "daemon-http" / "daemon_http_report.txt").write_text(
            "daemon-http exit: 0\n", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("DAEMON HTTP ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("daemon_http_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        dh = m["daemon_http"]
        self.assertIn("daemon-http/daemon_http_report.json", dh["files"])
        self.assertIn("daemon-http/daemon_http_report.txt", dh["files"])
        self.assertTrue(len(dh["combined_sha256"]) == 64)

    def test_daemon_http_combined_recomputes_deterministically(self):
        (self.artifacts / "daemon-http").mkdir(parents=True)
        (self.artifacts / "daemon-http" / "daemon_http_report.json").write_text(
            json.dumps({"ok": True}) + "\n", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        dh = m["daemon_http"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{dh[rel]}\n" for rel in sorted(dh)).encode()
        ).hexdigest()
        self.assertEqual(m["daemon_http"]["combined_sha256"], expected)
        self.assertRegex(m["daemon_http"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_daemon_http_artifact_job_provenance(self):
        (self.artifacts / "daemon-http").mkdir(parents=True)
        (self.artifacts / "daemon-http" / "daemon_http_report.json").write_text(
            "{}", encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["daemon-http"], "daemon-http")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("prefixed (1 dosya)", txt)  # daemon-http tek dosya

    def test_no_daemon_http_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("daemon_http", m)

    # ── OVERRIDES section tests ──────────────────────────────────────
    def test_overrides_section(self):
        # cli_overrides_version.json (isimle tanınır — CONFIG gibi)
        # ayrı bölümde işaretlenir + tek-hash combined_sha256.
        (self.artifacts / "budget").mkdir(parents=True)
        (self.artifacts / "budget" / "cli_overrides_version.json").write_text(
            json.dumps({"override_count": 1, "warning": True,
                        "overrides": [{"key": "budget", "file_value": 30.0,
                                       "effective": 25}]}),
            encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("OVERRIDES ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("overrides_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ov = m["overrides"]
        self.assertIn("budget/cli_overrides_version.json", ov["files"])
        self.assertEqual(len(ov["combined_sha256"]), 64)

    def test_overrides_combined_recomputes_deterministically(self):
        (self.artifacts / "budget").mkdir(parents=True)
        (self.artifacts / "budget" / "cli_overrides_version.json").write_text(
            json.dumps({"override_count": 0, "warning": False,
                        "overrides": []}),
            encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ov = m["overrides"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{ov[rel]}\n" for rel in sorted(ov)).encode()
        ).hexdigest()
        self.assertEqual(m["overrides"]["combined_sha256"], expected)
        self.assertRegex(m["overrides"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_overrides_basename_recognition_flat(self):
        # merge-multiple köke düzleştirdiğinde alt dizin öneki kaybolur;
        # basename ile tanınır (CONFIG deseni).
        (self.artifacts / "cli_overrides_version.json").write_text(
            json.dumps({"override_count": 0, "warning": False}),
            encoding="utf-8")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        ov = m["overrides"]
        self.assertIn("cli_overrides_version.json", ov["files"])
        self.assertEqual(len(ov["combined_sha256"]), 64)

    def test_no_overrides_section_when_absent(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("overrides", m)

    def test_env_override_artifact_jobs(self):
        env = dict(os.environ)
        env["REPRO_ARTIFACT_JOBS"] = '{"precommit-logs": "custom-job"}'
        r = subprocess.run(
            ["python3", str(GEN), "--artifacts-dir", str(self.artifacts),
             "--out-dir", str(self.out)],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            m["provenance"]["artifact_jobs"]["precommit-logs"], "custom-job")


class TestWorkflowPatternCoverage(unittest.TestCase):
    """reproducibility merge pattern'i ARTIFACT_JOBS'ı eksiksiz kapsamalı.

    Prefixed ayrı indirilenler (config/precommit-logs/refs-trend) ve çıktı
    (reproducibility) pattern'e girmez; kalan HER artifact merge pattern'de
    olmalı — yoksa o artifact manifest'e girmeden sessizce düşer (ör. bugün
    budget-verify/lineage-findings/klayers eksikti).
    """
    EXCLUDED = {"precommit-logs", "refs-trend", "override-trend",
                "precheck-report", "python3-shell", "plist-check",
                "mirror-check", "daemon-http", "reproducibility"}

    def _workflow_merge_pattern(self):
        wf = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"
        text = wf.read_text(encoding="utf-8")
        m = re.search(
            r"merge-multiple:\s*true\s*\n\s*pattern:\s*'\{([^}]+)\}'\s*\n",
            text,
        )
        self.assertIsNotNone(m, "verify.yml'de brace merge pattern bulunamadı")
        return {s.strip() for s in m.group(1).split(",")}

    def test_pattern_covers_all_merge_artifacts(self):
        expected = set(gen_manifest.ARTIFACT_JOBS) - self.EXCLUDED
        pattern = self._workflow_merge_pattern()
        self.assertEqual(pattern, expected)

    def test_no_duplicate_artifacts_in_pattern(self):
        pattern = self._workflow_merge_pattern()
        self.assertEqual(len(pattern), len(set(pattern)))


class TestWorkflowCliConsistency(unittest.TestCase):
    """verify.yml'in reproducibility job'ı gen_repro_manifest.py CLI'sıyla senkron olmalı."""
    def _workflow(self):
        wf = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"
        return wf.read_text(encoding="utf-8")

    def test_job_uses_artifacts_dir_and_out_dir(self):
        text = self._workflow()
        self.assertIn("_calisma/CIKTI/gen_repro_manifest.py", text)
        self.assertIn("--artifacts-dir all_artifacts", text)
        self.assertIn("--out-dir reproducibility", text)


class TestManifestSections(unittest.TestCase):
    """bundle/hash/config bölümleri — deterministik üretim + fail-closed doğrulama.

    gen_repro_manifest.py'nin üç çekirdek sözü:
      (1) HASH:   manifest.json'daki her files[rel] = gerçek dosyanın SHA-256'sı
                  (yeniden hesaplanınca birebir eşleşmeli).
      (2) BUNDLE: hashlanan HER dosya out_dir'e kopyalanmış olmalı (eksik kopya
                  = manifest'te var ama bundle'da yok → reproducibility kırık).
      (3) CONFIG: config/ dosyaları ayrı bölümde işaretlenir ve
                  config.combined_sha256 sıralı 'rel\0hash\n' birleşiminden
                  DETERMINISTİK olarak yeniden hesaplanabilmeli.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        self.artifacts.mkdir(parents=True)
        # flat + alt dizin + config (2 dosya) + binary — tüm biçimler
        (self.artifacts / "verify_report.txt").write_text("flat\n", encoding="utf-8")
        (self.artifacts / "sub").mkdir(parents=True)
        (self.artifacts / "sub" / "nested.json").write_text(
            '{"n": 1}', encoding="utf-8")
        (self.artifacts / "config").mkdir(parents=True)
        # Gerçekçi config çifti: effective_config.json cli_overrides kaydı
        # dosya config'iyle (verify_delivery.config.json) tutarlı — K10'un
        # cli_overrides kapısı da üretilen manifest'i PASS etmeli (çapraz
        # doğrulama testleri bu çifte bağlıdır).
        (self.artifacts / "config" / "verify_delivery.config.json").write_text(
            '{"budget_usd": 30.0, "budget_method": "both"}',
            encoding="utf-8")
        (self.artifacts / "config" / "effective_config.json").write_text(
            json.dumps({
                "budget_usd": 30.0,
                "budget_method": "both",
                "cli_overrides": {
                    "budget": {"cli_given": False, "cli_value": None,
                                "file_value": 30.0, "effective": 30.0,
                                "override": False},
                    "budget_method": {"cli_given": False, "cli_value": None,
                                       "file_value": "both",
                                       "effective": "both",
                                       "override": False},
                },
            }),
            encoding="utf-8")
        (self.artifacts / "binary.bin").write_bytes(b"\x00\x01\x02\xff")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))

    # ── HASH bölümü ──────────────────────────────────────────────────────
    def test_every_hash_recomputes_to_actual_file(self):
        m = self._gen()
        for rel, h in m["files"].items():
            self.assertEqual(gen_manifest.sha256_file(self.out / rel), h,
                             f"hash sapması: {rel}")

    def test_hash_format(self):
        m = self._gen()
        for rel, h in m["files"].items():
            self.assertRegex(h, r"^[0-9a-f]{64}$", f"kötü hash formatı: {rel}")

    def test_files_count_matches_disk(self):
        m = self._gen()
        disk = [p for p in self.artifacts.rglob("*") if p.is_file()]
        self.assertEqual(len(m["files"]), len(disk))

    def test_manifest_sha256_sidecar(self):
        m = self._gen()  # noqa: F841
        sc = (self.out / "manifest.sha256").read_text(encoding="utf-8").strip()
        self.assertTrue(sc.endswith("  manifest.json"))
        self.assertEqual(sc.split()[0],
                         gen_manifest.sha256_file(self.out / "manifest.json"))

    # ── BUNDLE bölümü ────────────────────────────────────────────────────
    def test_bundle_contains_every_hashed_file(self):
        m = self._gen()
        for rel in m["files"]:
            self.assertTrue((self.out / rel).is_file(), f"bundle'da yok: {rel}")

    def test_bundle_bytes_identical(self):
        m = self._gen()
        for rel in m["files"]:
            self.assertEqual((self.out / rel).read_bytes(),
                             (self.artifacts / rel).read_bytes(),
                             f"bundle kopyası bozuk: {rel}")

    def test_bundle_has_manifest_triple(self):
        self._gen()
        for f in ("manifest.txt", "manifest.json", "manifest.sha256"):
            self.assertTrue((self.out / f).is_file(), f"eksik: {f}")

    # ── CONFIG bölümü ────────────────────────────────────────────────────
    def test_config_files_subset_of_files_with_same_hashes(self):
        m = self._gen()
        cfg = m["config"]["files"]
        self.assertEqual(set(cfg),
                         {rel for rel in m["files"] if gen_manifest._is_config_rel(rel)})
        for rel, h in cfg.items():
            self.assertEqual(m["files"][rel], h)

    def test_config_detection_accepts_known_basenames_anywhere(self):
        # merge-multiple'ın köke düzleştirmesi: config/ öneki olmasa bile
        # bilinen config basename'leri tanınmalı (isimle tanıma).
        for rel in ("verify_delivery.config.json",
                    "verify_delivery.config.schema.json",
                    "effective_config.json",
                    "action_pins.json",
                    "config.sha256",
                    "config-diff.txt",
                    "config-diff.json"):
            self.assertTrue(gen_manifest._is_config_rel(rel), rel)
            self.assertTrue(
                gen_manifest._is_config_rel("config/" + rel), "config/" + rel)
        # İlgisiz dosyalar yanlışlıkla config sanılmamalı.
        for rel in ("verify_report.txt", "a.txt", "sub/nested.json",
                    "effective_config.json.bak", "my_effective_config.json"):
            self.assertFalse(gen_manifest._is_config_rel(rel), rel)

    def test_config_combined_recomputes_deterministically(self):
        m = self._gen()
        cfg = m["config"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{cfg[rel]}\n" for rel in sorted(cfg)).encode()
        ).hexdigest()
        self.assertEqual(m["config"]["combined_sha256"], expected)
        self.assertRegex(m["config"]["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_config_combined_cross_validates_with_k10(self):
        """K10 çapraz doğrulama: AYNI config.files girdisinden üç formül de
        birebir aynı hash'i üretmeli — test formülü, K10
        (verify_delivery._config_combined_sha256) ve üreticinin kayıtlı
        config.combined_sha256. Biri saparsa çapraz doğrulama sessizce
        kayar (üretici drift'i / implementasyon ayrışması) → fail-closed."""
        import verify_delivery as vd
        m = self._gen()
        cfg = m["config"]["files"]
        test_formula = hashlib.sha256(
            "".join(f"{rel}\0{cfg[rel]}\n" for rel in sorted(cfg)).encode()
        ).hexdigest()
        k10 = vd._config_combined_sha256(cfg)
        stored = m["config"]["combined_sha256"]
        self.assertEqual(test_formula, k10,
                         "test formülü ↔ K10 formülü sapması (aynı girdi)")
        self.assertEqual(k10, stored,
                         "K10 formülü ↔ üretici kaydı sapması (aynı girdi)")

    def test_k10_gate_passes_on_produced_manifest(self):
        """Uçtan uca K10 çapraz doğrulama: üreticinin manifest'ini
        verify_manifest_digest (--verify-manifest çekirdeği) TAMAMEN PASS
        etmeli — config.combined_sha256 yeniden hesabı + cli_overrides dahil."""
        import verify_delivery as vd
        self._gen()
        findings = []
        ok, detail = vd.verify_manifest_digest(
            str(self.out / "manifest.json"),
            lambda pri, cid, cl, issue="", ev="":
                findings.append((pri, cid, issue)))
        self.assertTrue(ok, detail)
        self.assertIn("config.combined_sha256: PASS", detail)
        self.assertIn("cli_overrides: PASS", detail)
        self.assertEqual(findings, [], f"K10 bulgu üretti: {findings}")

    def test_k10_detects_config_combined_tamper(self):
        """Fail-closed çapraz: manifest'teki config.combined_sha256
        kurcalanınca K10 aynı formülle YENİDEN hesaplayıp uyuşmazlığı
        yakalamalı (kayıtlı değer güvenilir değil — yeniden hesap tek kanıt)."""
        import verify_delivery as vd
        m = self._gen()
        stored = m["config"]["combined_sha256"]
        m["config"]["combined_sha256"] = (
            "0" if stored[0] != "0" else "1") + stored[1:]
        (self.out / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        findings = []
        ok, detail = vd.verify_manifest_digest(
            str(self.out / "manifest.json"),
            lambda pri, cid, cl, issue="", ev="":
                findings.append((pri, cid, issue)))
        self.assertFalse(ok)
        self.assertIn("config.combined_sha256: FAIL", detail)
        self.assertTrue(
            any(i == "config.combined_sha256 uyuşmazlığı"
                for _, _, i in findings), findings)

    def test_config_combined_is_stable_across_runs(self):
        first = self._gen()["config"]["combined_sha256"]
        out2 = self.root / "reproducibility2"
        r = _run_gen(str(self.artifacts), str(out2))
        self.assertEqual(r.returncode, 0, r.stderr)
        m2 = json.loads((out2 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m2["config"]["combined_sha256"], first)

    def test_manifest_txt_config_section(self):
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("CONFIG ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("config_combined_sha256", txt)
        self.assertIn("config/verify_delivery.config.json", txt)
        self.assertIn("config/effective_config.json", txt)

    def test_no_config_section_when_config_absent(self):
        # config/ hiç yoksa manifest.json'da 'config' anahtarı da olmamalı
        # (boş bölüm şişirmek yerine yok sayılır).
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("config", m)
        self.assertIn("a.txt", m["files"])

    def test_action_pins_in_config_section(self):
        # action_pins.json (action pin baseline'ı) config/ önekiyle gelir ve
        # CONFIG bölümünde ayrıca hash'lenir — tek kaynak: verify.yml'deki
        # "Bundle config snapshot" adımı (cp action_pins.json config/).
        (self.artifacts / "config" / "action_pins.json").write_text(
            '{"actions/checkout": 7}', encoding="utf-8")
        m = self._gen()
        cfg = m["config"]["files"]
        self.assertIn("config/action_pins.json", cfg)
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("action_pins.json", txt)
        # combined_sha256 sıralı birleşimle deterministik yeniden hesaplanır.
        expected = hashlib.sha256(
            "".join(f"{rel}\0{cfg[rel]}\n" for rel in sorted(cfg)).encode()
        ).hexdigest()
        self.assertEqual(m["config"]["combined_sha256"], expected)

    # ── ACTION RUNTIMES bölümü ───────────────────────────────────────────
    def test_action_runtimes_section(self):
        # action_runtimes.json (action-runtimes job'ı) isimle tanınır — merge-
        # multiple köke düzleştirdiği için önek yoktur; ayrı bölümde işaretlenir
        # + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "action_runtimes.json").write_text(
            '{"target": ".github/workflows/verify.yml", "summary": {"pass": 6}}',
            encoding="utf-8")
        m = self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("ACTION RUNTIMES ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("action_runtimes_combined_sha256", txt)
        ar = m["action_runtimes"]
        self.assertIn("action_runtimes.json", ar["files"])
        self.assertRegex(ar["combined_sha256"], r"^[0-9a-f]{64}$")

    def test_action_runtimes_combined_recomputes_deterministically(self):
        (self.artifacts / "action_runtimes.json").write_text(
            '{"target": ".github/workflows/verify.yml", "summary": {"pass": 6}}',
            encoding="utf-8")
        m = self._gen()
        ar = m["action_runtimes"]["files"]
        expected = hashlib.sha256(
            "".join(f"{rel}\0{ar[rel]}\n" for rel in sorted(ar)).encode()
        ).hexdigest()
        self.assertEqual(m["action_runtimes"]["combined_sha256"], expected)

    def test_action_runtimes_artifact_job_provenance(self):
        (self.artifacts / "action_runtimes.json").write_text(
            '{"summary": {"pass": 6}}', encoding="utf-8")
        m = self._gen()
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["action-runtimes"], "action-runtimes")
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("köke düzleştirildi (1 dosya)", txt)  # action_runtimes merge ile köke düzleşti

    def test_no_action_runtimes_section_when_absent(self):
        m = self._gen()
        self.assertNotIn("action_runtimes", m)


class TestManifestSha256Sidecar(unittest.TestCase):
    """manifest.sha256 — canonical sha256sum biçimi + determinizm + duyarlılık.

    CI'da reproducibility job'ı sidecar'ı AYRI adımda `sha256sum -c` ile
    doğrular; bu testler sidecar'ın o sözleşmeyi (biçim, birebir eşleşme,
    kurcalamaya duyarlılık) her koşuda karşıladığını kanıtlar.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        self.artifacts.mkdir(parents=True)
        (self.artifacts / "verify_report.txt").write_text(
            "flat\n", encoding="utf-8")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.out / "manifest.sha256").read_text(encoding="utf-8")

    def test_sidecar_is_sha256sum_canonical(self):
        # CI adımı (`sha256sum -c manifest.sha256`) ile aynı sözleşme:
        # sidecar standart araçla birebir doğrulanabilmeli.
        if shutil.which("sha256sum") is None:
            self.skipTest("sha256sum yok")
        self._gen()
        r = subprocess.run(["sha256sum", "-c", "manifest.sha256"],
                           capture_output=True, text=True, cwd=self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("manifest.json: OK", r.stdout)

    def test_sidecar_exact_format(self):
        sc = self._gen()
        # tek satır, sha256sum metin biçimi: "{64 hex}  manifest.json\n"
        self.assertTrue(sc.endswith("  manifest.json\n"),
                        f"biçim bozuk: {sc!r}")
        self.assertEqual(len(sc.splitlines()), 1)
        h, name = sc.strip().split()
        self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertEqual(name, "manifest.json")

    def test_sidecar_matches_manifest_json_exactly(self):
        self._gen()
        sc = (self.out / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(
            sc.split()[0],
            gen_manifest.sha256_file(self.out / "manifest.json"))

    def test_sidecar_deterministic_across_runs(self):
        # Reproducibility sözü: aynı artifact'ler → aynı files hash tablosu
        # (+ config bölümü). manifest.json başlığındaki `generated:` zaman
        # damgası bilinçli provenance alanıdır ve run'lar arası değişir —
        # byte-determinizm sözü HASH TABLOSU içindir, başlık için değil.
        self._gen()
        first = json.loads(
            (self.out / "manifest.json").read_text(encoding="utf-8"))
        out2 = self.root / "reproducibility2"
        r = _run_gen(str(self.artifacts), str(out2))
        self.assertEqual(r.returncode, 0, r.stderr)
        second = json.loads(
            (out2 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(first["files"], second["files"])
        if "config" in first:
            self.assertEqual(first["config"], second["config"])
        # Her run'ın sidecar'ı KENDİ manifest.json'unu doğrular.
        for out in (self.out, out2):
            sc = (out / "manifest.sha256").read_text(encoding="utf-8")
            self.assertEqual(
                sc.split()[0],
                gen_manifest.sha256_file(out / "manifest.json"))

    def test_sidecar_sensitive_to_artifact_change(self):
        self._gen()
        first = json.loads(
            (self.out / "manifest.json").read_text(encoding="utf-8"))
        # İçerik değişince files hash tablosu değişmeli (gerçek duyarlılık
        # sinyali — zaman damgası her run'da zaten farklıdır, o yüzden
        # sidecar değil, hash tablosu karşılaştırılır).
        (self.artifacts / "verify_report.txt").write_text(
            "değişti\n", encoding="utf-8")
        out2 = self.root / "reproducibility2"
        r = _run_gen(str(self.artifacts), str(out2))
        self.assertEqual(r.returncode, 0, r.stderr)
        second = json.loads(
            (out2 / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first["files"]["verify_report.txt"],
                            second["files"]["verify_report.txt"])
        # Yeni run'ın sidecar'ı yeni manifest.json'u doğrular (öz-tutarlı).
        sc = (out2 / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(
            sc.split()[0],
            gen_manifest.sha256_file(out2 / "manifest.json"))

    def test_tampered_manifest_json_fails_sha256sum(self):
        # manifest.json'a boşluk kurcalaması → sha256sum -c FAIL (exit≠0).
        if shutil.which("sha256sum") is None:
            self.skipTest("sha256sum yok")
        self._gen()
        with open(self.out / "manifest.json", "a", encoding="utf-8") as f:
            f.write(" ")
        r = subprocess.run(["sha256sum", "-c", "manifest.sha256"],
                           capture_output=True, text=True, cwd=self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAILED", r.stdout)


class TestBundleBehavior(unittest.TestCase):
    """bundle — tam içerik sözleşmesi, yapı korunumu, kenar durumlar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        self.artifacts.mkdir(parents=True)
        (self.artifacts / "verify_report.txt").write_text(
            "flat\n", encoding="utf-8")
        (self.artifacts / "sub").mkdir(parents=True)
        (self.artifacts / "sub" / "nested.json").write_text(
            '{"n": 1}', encoding="utf-8")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def _bundle_rels(self):
        return {str(p.relative_to(self.out))
                for p in self.out.rglob("*") if p.is_file()}

    def _artifact_rels(self):
        return {str(p.relative_to(self.artifacts))
                for p in self.artifacts.rglob("*") if p.is_file()}

    def test_bundle_is_exactly_artifacts_plus_manifest_triple(self):
        self._gen()
        triple = {"manifest.txt", "manifest.json", "manifest.sha256"}
        self.assertEqual(self._bundle_rels(), self._artifact_rels() | triple)

    def test_bundle_preserves_directory_structure(self):
        self._gen()
        # manifest üçlüsü dışındaki her rel yol, artifacts'taki ile birebir
        # aynı olmalı (düzleştirme yok — sub/nested.json korunur).
        self.assertEqual(self._bundle_rels() - {"manifest.txt",
                                                "manifest.json",
                                                "manifest.sha256"},
                         self._artifact_rels())

    def test_empty_artifacts_dir_produces_valid_bundle(self):
        empty = self.root / "empty"
        empty.mkdir(parents=True)
        out = self.root / "empty-out"
        r = _run_gen(str(empty), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["files"], {})
        # Üçlü yine de üretilmeli ve sidecar boş manifest'i doğrulamalı.
        for f in ("manifest.txt", "manifest.json", "manifest.sha256"):
            self.assertTrue((out / f).is_file(), f"eksik: {f}")
        if shutil.which("sha256sum") is not None:
            r = subprocess.run(["sha256sum", "-c", "manifest.sha256"],
                               capture_output=True, text=True, cwd=out)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_file_hashed_with_known_sha256(self):
        (self.artifacts / "empty.txt").write_bytes(b"")
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(
            encoding="utf-8"))
        # sha256("") bilinen sabit — boş dosyalar atlanmamalı.
        self.assertEqual(
            m["files"]["empty.txt"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_bundle_bytes_deterministic_across_runs(self):
        # Bundle'daki ARTIFACT KOPYALARI run'lar arası byte-identical;
        # manifest.txt/json (zaman damgası başlığı) determinizm sözüne girmez.
        triple = {"manifest.txt", "manifest.json", "manifest.sha256"}
        self._gen()
        first = {rel: (self.out / rel).read_bytes()
                 for rel in self._bundle_rels() - triple}
        out2 = self.root / "reproducibility2"
        r = _run_gen(str(self.artifacts), str(out2))
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel, data in first.items():
            self.assertEqual((out2 / rel).read_bytes(), data,
                             f"run'lar arası byte sapması: {rel}")

    def test_generation_does_not_mutate_artifacts(self):
        before = {rel: (self.artifacts / rel).read_bytes()
                  for rel in self._artifact_rels()}
        self._gen()
        after = {rel: (self.artifacts / rel).read_bytes()
                 for rel in self._artifact_rels()}
        self.assertEqual(after, before)
        # Bundle kopyaları source'u değiştirmedi (byte-for-byte aynı kaldı).
        for rel in before:
            self.assertEqual((self.out / rel).read_bytes(), before[rel])


class TestFlattenedConfigMerge(unittest.TestCase):
    """merge-multiple köke düzleştirdiğinde config dosyaları isimle tanınmalı.

    Eski davranış yalnızca config/ ÖNEKİNİ arıyordu; config artifact'ı
    merge-multiple ile köke düzleşirse (önek kaybolur) config bölümü
    sessizce düşüyordu. Yeni davranış: config/ öneki VEYA CONFIG_BASENAMES
    ile isimle tanıma — düzleştirilmiş config dosyaları da config objesine
    girer, provenance "config" job'ına bağlanır.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        self.artifacts.mkdir(parents=True)
        # Config artifact'ı KÖKE düzleşmiş (config/ öneki YOK).
        (self.artifacts / "verify_report.txt").write_text("flat\n",
                                                           encoding="utf-8")
        (self.artifacts / "verify_delivery.config.json").write_text(
            '{"budget_usd": 30.0}', encoding="utf-8")
        (self.artifacts / "effective_config.json").write_text(
            '{"effective": true}', encoding="utf-8")
        (self.artifacts / "config-diff.json").write_text(
            '{"diffs": []}', encoding="utf-8")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def test_flattened_config_still_in_config_section(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        cfg = m["config"]["files"]
        # Önek yok ama isimle tanındılar.
        self.assertIn("verify_delivery.config.json", cfg)
        self.assertIn("effective_config.json", cfg)
        self.assertIn("config-diff.json", cfg)
        # İlgisiz dosya config sayılmaz.
        self.assertNotIn("verify_report.txt", cfg)
        for rel, h in cfg.items():
            self.assertEqual(m["files"][rel], h)
        # combined deterministik yeniden hesaplanabilir.
        expected = hashlib.sha256(
            "".join(f"{rel}\0{cfg[rel]}\n" for rel in sorted(cfg)).encode()
        ).hexdigest()
        self.assertEqual(m["config"]["combined_sha256"], expected)

    def test_flattened_config_maps_to_config_artifact_in_provenance(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        prov = m["provenance"]["artifact_jobs"]
        self.assertEqual(prov["config"], "verify")

    def test_no_config_section_when_only_unrelated_files(self):
        bare = self.root / "bare"
        bare.mkdir(parents=True)
        (bare / "a.txt").write_text("x", encoding="utf-8")
        (bare / "my_effective_config.json").write_text("y", encoding="utf-8")
        out = self.root / "bare-out"
        r = _run_gen(str(bare), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("config", m)



class TestCheckPatternConsistency(unittest.TestCase):
    """check_pattern_consistency.py bağımsız betiğinin testleri."""

    def _run_check(self, workflow_content=None):
        """Geçici workflow ile check_pattern_consistency.check() çalıştır."""
        import check_pattern_consistency as cpc
        tmp = pathlib.Path("/tmp") / f"test_pattern_{os.getpid()}"
        tmp.mkdir(exist_ok=True)
        if workflow_content is not None:
            wf = tmp / "verify.yml"
            wf.write_text(workflow_content, encoding="utf-8")
        else:
            # Varsayılan: gerçek workflow
            wf = pathlib.Path(cpc.DEFAULT_WORKFLOW)
        return cpc.check(str(wf)), tmp

    def test_consistent_pattern_passes(self):
        import check_pattern_consistency as cpc
        errors, tmp = self._run_check()
        self.assertEqual(errors, [])

    def test_missing_artifact_detected(self):
        import check_pattern_consistency as cpc
        wf = (pathlib.Path(cpc.DEFAULT_WORKFLOW).read_text(encoding="utf-8"))
        # budget-verify'ı pattern'den çıkar
        wf = wf.replace(
            "'{verify-report,budget,reports,refs-online,run-history,config-drift,repack-verify,config,k0-findings,budget-verify,lineage-findings,klayers,unit-tests,action-runtimes}'",
            "'{verify-report,budget,reports,refs-online,run-history,config-drift,repack-verify,k0-findings,lineage-findings,klayers,unit-tests,action-runtimes}'",
        )
        errors, _ = self._run_check(wf)
        self.assertTrue(any("budget-verify" in e for e in errors))
        self.assertTrue(any("Eksik" in e for e in errors))

    def test_extra_artifact_detected(self):
        import check_pattern_consistency as cpc
        wf = (pathlib.Path(cpc.DEFAULT_WORKFLOW).read_text(encoding="utf-8"))
        # Fazla bir artifact ekle
        wf = wf.replace(
            "'{verify-report,budget,reports,refs-online,run-history,config-drift,repack-verify,config,k0-findings,budget-verify,lineage-findings,klayers,unit-tests,action-runtimes}'",
            "'{verify-report,budget,reports,refs-online,run-history,config-drift,repack-verify,k0-findings,budget-verify,lineage-findings,klayers,unit-tests,action-runtimes,fake-artifact}'",
        )
        errors, _ = self._run_check(wf)
        self.assertTrue(any("fake-artifact" in e for e in errors))
        self.assertTrue(any("Fazla" in e for e in errors))

    def test_missing_pattern_not_found(self):
        import check_pattern_consistency as cpc
        wf = (pathlib.Path(cpc.DEFAULT_WORKFLOW).read_text(encoding="utf-8"))
        wf = wf.replace(
            "'{verify-report,budget,reports,refs-online,run-history,config-drift,repack-verify,config,k0-findings,budget-verify,lineage-findings,klayers,unit-tests,action-runtimes}'",
            "'{verify-report,budget,reports}'",
        )
        errors, _ = self._run_check(wf)
        self.assertTrue(len(errors) > 0)

    def test_no_pattern_returns_error(self):
        errors, _ = self._run_check("jobs:\n  foo:\n    runs-on: ubuntu-latest\n")
        self.assertTrue(any("bulunamadı" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
