#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_audit_octokit_names.py — audit_octokit_names.py birim testleri.

fail-closed denetiminin:
  - İzin verilen metodları PASS ettiğini
  - İzinsiz metodları yakaladığını
  - Bozuk/eksik dosyayı yakaladığını
  - --json ve --check-only modlarının doğru çalıştığını
  doğrular.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_octokit_names as aon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(HERE, "github_scripts")


class TestAuditFile(unittest.TestCase):
    """Tek dosya denetimi."""

    def test_allowed_method_passes(self):
        """İzin verilen bir metod bulgu üretmez."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         delete=False) as f:
            f.write("await github.rest.issues.listComments({})\n")
            f.flush()
            try:
                findings = aon.audit_file(f.name)
                self.assertEqual(findings, [])
            finally:
                os.unlink(f.name)

    def test_unknown_method_fails(self):
        """İzin dışı bir metod FAIL üretir (fail-closed)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         delete=False) as f:
            f.write("await github.rest.repos.createCommitStatus({})\n")
            f.flush()
            try:
                findings = aon.audit_file(f.name)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0][0], "repos.createCommitStatus")
                self.assertEqual(findings[0][3], 1)  # line number
            finally:
                os.unlink(f.name)

    def test_mixed_allowed_and_unknown(self):
        """Karışık dosyada yalnızca izinsiz metodlar bulgu üretir."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         delete=False) as f:
            f.write("await github.rest.issues.listComments({})\n")
            f.write("await github.rest.pulls.listFiles({})\n")
            f.write("await github.rest.issues.createComment({})\n")
            f.flush()
            try:
                findings = aon.audit_file(f.name)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0][0], "pulls.listFiles")
            finally:
                os.unlink(f.name)

    def test_no_octokit_calls_passes(self):
        """Octokit çağrısı olmayan dosya temiz geçer."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         delete=False) as f:
            f.write("const x = 1;\nconsole.log(x);\n")
            f.flush()
            try:
                findings = aon.audit_file(f.name)
                self.assertEqual(findings, [])
            finally:
                os.unlink(f.name)

    def test_read_error_produces_finding(self):
        """Var olmayan dosya READ_ERROR bulgusu üretir."""
        findings = aon.audit_file("/nonexistent/file.js")
        self.assertEqual(len(findings), 1)
        self.assertIn("READ_ERROR", findings[0][0])

    def test_line_number_accurate(self):
        """Bulgu satır numarası doğru olmalı."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         delete=False) as f:
            f.write("// yorum\n")
            f.write("const x = 1;\n")
            f.write("await github.rest.pulls.get({})\n")  # satır 3
            f.flush()
            try:
                findings = aon.audit_file(f.name)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0][3], 3)
            finally:
                os.unlink(f.name)


class TestAuditDirectory(unittest.TestCase):
    """Dizin denetimi."""

    def test_real_scripts_dir_passes(self):
        """Gerçek github_scripts dizini tüm izinli metodlar PASS etmeli."""
        result = aon.audit_directory(SCRIPTS_DIR)
        self.assertTrue(result["ok"], f"Bulgu: {result['findings']}")
        self.assertGreater(result["files_scanned"], 0)
        self.assertGreater(result["total_calls"], 0)

    def test_empty_dir_passes(self):
        """Boş dizin PASS (çağrı yok → bulgu yok)."""
        with tempfile.TemporaryDirectory() as td:
            result = aon.audit_directory(td)
            self.assertTrue(result["ok"])
            self.assertEqual(result["files_scanned"], 0)
            self.assertEqual(result["total_calls"], 0)

    def test_unknown_in_subdir_fails(self):
        """Alt dizindeki izin dışı metod yakalanır."""
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, "sub")
            os.makedirs(sub)
            with open(os.path.join(sub, "bad.js"), "w") as f:
                f.write("await github.rest.gists.create({})\n")
            result = aon.audit_directory(td)
            self.assertFalse(result["ok"])
            self.assertEqual(len(result["findings"]), 1)
            self.assertEqual(result["findings"][0]["method"], "gists.create")

    def test_allowed_count_matches_definition(self):
        """allowed_count ALLOWED_METHODS uzunluğuyla eşleşmeli."""
        result = aon.audit_directory(SCRIPTS_DIR)
        self.assertEqual(result["allowed_count"], len(aon.ALLOWED_METHODS))


class TestAllAllowedMethods(unittest.TestCase):
    """Her izin verilen metod gerçekten kullanılıyor mu?"""

    def test_all_allowed_methods_appear_in_scripts(self):
        """ALLOWED_METHODS'taki her metod github_scripts'de en az bir kez
        kullanılıyor — bayat izin tespiti."""
        content = ""
        for fn in os.listdir(SCRIPTS_DIR):
            if fn.endswith(".js"):
                with open(os.path.join(SCRIPTS_DIR, fn),
                          encoding="utf-8") as f:
                    content += f.read()
        for name, _method, _route in aon.ALLOWED_METHODS:
            # namespace.method biçiminde ara
            self.assertIn(name, content,
                          f"İzin verilen '{name}' github_scripts'de "
                          f"kullanılmıyor — bayat izin olabilir")


class TestMainFunction(unittest.TestCase):
    """main() çıkış kodu ve mod parametreleri."""

    def test_main_pass_on_real_dir(self):
        """Gerçek dizinle main() 0 döner."""
        rc = aon.main(["--scripts-dir", SCRIPTS_DIR, "--check-only"])
        self.assertEqual(rc, 0)

    def test_main_json_output(self):
        """--json çıktısı geçerli JSON ve 'ok' anahtarı var."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            tmppath = f.name
        try:
            # stdout'u yakala
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                rc = aon.main(["--scripts-dir", SCRIPTS_DIR,
                               "--json"])
            finally:
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            data = json.loads(output)
            self.assertIn("ok", data)
            self.assertIn("files_scanned", data)
            self.assertIn("total_calls", data)
            self.assertIn("allowed_count", data)
        finally:
            os.unlink(tmppath)

    def test_main_fail_on_bad_script(self):
        """İzin dışı metod içeren dizinle main() 1 döner (fail-closed)."""
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "bad.js"), "w") as f:
                f.write("await github.rest.orgs.get({})\n")
            rc = aon.main(["--scripts-dir", td])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
