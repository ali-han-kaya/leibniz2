#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_extract_unstaged_deps.py — extract_unstaged_deps.py ayrıştırma testleri.

precommit.log'daki unstaged-deps ön-kontrol bloklarının (advisory ⚠️ / strict
⛔ marker'ları) doğru ayrıştırıldığını doğrular: hook adı, strict bayrağı,
kirli dosya listesi ve JSON sidecar çıktısı. Gerçek dosya IO'su ile koşar
(tempfile) — OFFLINE, deterministik.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_unstaged_deps as ex  # noqa: E402

# pre-commit run çıktısındaki gerçek blok biçimi (--color=never).
STRICT_BLOCK = (
    "Verify Stoic-Hume V5 delivery (fail-closed)..............................Failed\n"
    "- hook id: verify-delivery\n"
    "- exit code: 2\n"
    "\n"
    "⛔  verify-delivery ÖN-KONTROL (--strict): bağımlılık dosyası "
    "STAGE EDİLMEMİŞ — HOOK BLOKE\n"
    "    • _calisma/CIKTI/verify_delivery.py  (unstaged değişiklik)\n"
    "    • _calisma/CIKTI/verify_delivery.config.json  (staged + unstaged (çift durum))\n"
    "  Strict modda unstaged/untracked bağımlılık commit'i bloke eder:\n"
    "  hook, stage edilen sürümle aynı içeriği test edemez.\n"
    "  Stage'lemek için: git add <dosya>  (sonra commit'i tekrarla)\n"
    "\n"
)

ADVISORY_BLOCK = (
    "check-repro-manifest...................................................Passed\n"
    "⚠️  check-pattern-consistency ÖN-KONTROL: bağımlılık dosyası "
    "STAGE EDİLMEMİŞ\n"
    "    • .github/workflows/verify.yml  (unstaged değişiklik)\n"
    "  Hook testleri ÇALIŞMA AĞACINI koşar; `git commit` stage'lenen içeriği alır.\n"
    "\n"
)

CLEAN_LOG = "verify-delivery...................................................Passed\n"


class TestParseLog(unittest.TestCase):
    def test_strict_block_parsed(self):
        blocks = ex.parse_log(STRICT_BLOCK)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["hook"], "verify-delivery")
        self.assertTrue(b["strict"])
        rels = [f["rel"] for f in b["files"]]
        self.assertEqual(rels,
                         ["_calisma/CIKTI/verify_delivery.py",
                          "_calisma/CIKTI/verify_delivery.config.json"])
        self.assertEqual(b["files"][0]["status"], "unstaged değişiklik")
        self.assertIn("çift durum", b["files"][1]["status"])

    def test_advisory_block_parsed_as_non_strict(self):
        blocks = ex.parse_log(ADVISORY_BLOCK)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["hook"], "check-pattern-consistency")
        self.assertFalse(b["strict"])
        self.assertEqual([f["rel"] for f in b["files"]],
                         [".github/workflows/verify.yml"])

    def test_multiple_blocks(self):
        blocks = ex.parse_log(STRICT_BLOCK + "\n" + ADVISORY_BLOCK)
        self.assertEqual(len(blocks), 2)
        self.assertEqual([b["hook"] for b in blocks],
                         ["verify-delivery", "check-pattern-consistency"])

    def test_clean_log_no_blocks(self):
        self.assertEqual(ex.parse_log(CLEAN_LOG), [])
        self.assertEqual(ex.parse_log(""), [])

    def test_file_line_extra_whitespace(self):
        # Status parantezi içinde fazla boşluk/baştaki boşluklar tolere edilir.
        txt = ("⛔  verify-delivery ÖN-KONTROL (--strict): bağımlılık dosyası "
               "STAGE EDİLMEMİŞ — HOOK BLOKE\n"
               "    •  _calisma/CIKTI/x.py   ( unstaged değişiklik )\n")
        blocks = ex.parse_log(txt)
        self.assertEqual(len(blocks), 1)
        f0 = blocks[0]["files"][0]
        self.assertEqual(f0["rel"], "_calisma/CIKTI/x.py")
        self.assertIn("unstaged", f0["status"])


class TestMain(unittest.TestCase):
    def _run(self, log_text):
        with tempfile.TemporaryDirectory(prefix="unstaged-extract-") as td:
            log = os.path.join(td, "precommit.log")
            with open(log, "w", encoding="utf-8") as f:
                f.write(log_text)
            out_json = os.path.join(td, "findings.json")
            out_txt = os.path.join(td, "findings.txt")
            r = subprocess.run(
                [sys.executable, os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "extract_unstaged_deps.py"),
                 "--log", log, "--out-json", out_json, "--out-txt", out_txt],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out_json, encoding="utf-8") as f:
                d = json.load(f)
            with open(out_txt, encoding="utf-8") as f:
                txt = f.read()
            return d, txt

    def test_strict_findings_written(self):
        d, txt = self._run(STRICT_BLOCK)
        self.assertTrue(d["found"])
        self.assertEqual(d["count"], 1)
        self.assertIn("_calisma/CIKTI/verify_delivery.py", d["files"])
        self.assertEqual(d["hooks"][0]["hook"], "verify-delivery")
        self.assertTrue(d["hooks"][0]["strict"])
        self.assertIn("STRICT (--strict)", txt)
        self.assertIn("verify_delivery.py", txt)

    def test_clean_log_finds_nothing(self):
        d, txt = self._run(CLEAN_LOG)
        self.assertFalse(d["found"])
        self.assertEqual(d["count"], 0)
        self.assertEqual(d["files"], [])
        self.assertIn("uyarısı yok", txt)

    def test_missing_log_is_honest_empty(self):
        with tempfile.TemporaryDirectory(prefix="unstaged-extract-") as td:
            out_json = os.path.join(td, "findings.json")
            r = subprocess.run(
                [sys.executable, os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "extract_unstaged_deps.py"),
                 "--log", os.path.join(td, "yok.log"),
                 "--out-json", out_json],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out_json, encoding="utf-8") as f:
                d = json.load(f)
            self.assertFalse(d["found"])
            self.assertIn("yok", d["error"])


if __name__ == "__main__":
    unittest.main()
