#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_enforce_is_on.py — publish_wrapper.sh enforce_is_on smoke kapısı.

`enforce_is_on()` bash fonksiyonu, GitHub branch protection'ın enforce_admins
durumunu `gh api` ile sorgular. İlk publish'te koruma YOKSA 404 döner —
fonksiyon bunu güvenle 1 (false) olarak yorumlar; push dansı (geçici kapatma)
ATLANIR. Bu test 3 senaryoyu mock gh ile deterministik doğrular:

  S1: koruma yok (404)      → exit 1 (enforce kapalı; first-publish güvenli)
  S2: enforce_admins=true   → exit 0 (enforce açık; toggle gerekecek)
  S3: enforce_admins=false  → exit 1 (enforce kapalı; toggle gerekmez)

Ayrıca wrapper'daki push akışının (enforce_is_on → toggle_enforce false → push
→ toggle_enforce true) sıralı yapısını kaynak metin üzerinde statik doğrular.

stdlib unittest — ağ/git yok; mock gh PATH override ile çalışır.
"""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "docs" / "publish_wrapper.sh"

# enforce_is_on fonksiyon gövdesi — publish_wrapper.sh'den birebir kopya.
# Kaynak: docs/publish_wrapper.sh satır 131-135.
ENFORCE_IS_ON_SRC = """\
enforce_is_on() {
  # Koruma varsa ve enforce_admins=true ise 0 döner; yoksa/yanlışsa 1.
  gh api "repos/$OWNER/$REPO_NAME/branches/main/protection" \\
    --jq '.enforce_admins.enabled' 2>/dev/null | grep -qx true || return 1
}
"""


def _write_mock_gh(bin_dir, behavior):
    """Mock gh binary'si yazar. behavior: 'true'|'false'|'404'.

    'true': enforce_admins.enabled=true yazar
    'false': enforce_admins.enabled=false yazar
    '404': "Not Found" stderr + exit 1
    """
    gh = bin_dir / "gh"
    if behavior == "404":
        gh.write_text(
            "#!/usr/bin/env bash\n"
            'echo "gh: Not Found (HTTP 404)" >&2\n'
            "exit 1\n")
    else:
        gh.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "{behavior}"\n'
            "exit 0\n")
    gh.chmod(0o755)


class TestEnforceIsOn(unittest.TestCase):
    """enforce_is_on() birim kapısı — mock gh'dan okur."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="eio_test_"))
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self):
        """enforce_is_on()'u mock gh ile çağırır; returncode döner."""
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["OWNER"] = "test-owner"
        env["REPO_NAME"] = "test-repo"
        env["SC_PY"] = sys.executable
        script = ENFORCE_IS_ON_SRC + "\nenforce_is_on\n"
        r = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True,
            env=env, timeout=10)
        return r.returncode

    def test_404_no_protection_returns_1(self):
        """İlk publish: koruma yok → gh api 404 → exit 1 (push dansı atlanır)."""
        _write_mock_gh(self.bin, "404")
        rc = self._run()
        self.assertEqual(rc, 1,
                         "404 (ilk publish) enforce_is_on exit 1 olmalı")

    def test_enforce_true_returns_0(self):
        """Koruma var + enforce true → exit 0 (toggle gerekecek)."""
        _write_mock_gh(self.bin, "true")
        rc = self._run()
        self.assertEqual(rc, 0,
                         "enforce_admins=true ise exit 0 olmalı")

    def test_enforce_false_returns_1(self):
        """Koruma var + enforce false → exit 1 (toggle gerekmez)."""
        _write_mock_gh(self.bin, "false")
        rc = self._run()
        self.assertEqual(rc, 1,
                         "enforce_admins=false ise exit 1 olmalı")

    def test_stderr_missing_does_not_break(self):
        """stderr yok (2>/dev/null) senaryosu — false gibi davranır."""
        gh = self.bin / "gh"
        gh.write_text(
            "#!/usr/bin/env bash\n"
            "echo ''\n"
            "exit 0\n")
        gh.chmod(0o755)
        rc = self._run()
        self.assertEqual(rc, 1,
                         "boş çıktı (stderr kapalı) exit 1 olmalı")


class TestEnforceIsOnSourcePresence(unittest.TestCase):
    """Wrapper kaynağında fonksiyonun varlığı + sıralama denetimi."""

    @classmethod
    def setUpClass(cls):
        cls.wrap = WRAPPER.read_text(encoding="utf-8")

    def test_function_defined(self):
        self.assertIn("enforce_is_on()", self.wrap)
        self.assertIn("gh api", self.wrap)
        self.assertIn(".enforce_admins.enabled", self.wrap)

    def test_toggle_enforce_defined(self):
        """toggle_enforce da tanımlı olmalı — push dansının diğer yarısı."""
        self.assertIn("toggle_enforce()", self.wrap)
        self.assertIn("gh api", self.wrap)  # toggle içinde de gh api var

    def test_push_flow_checks_before_toggle(self):
        """Push akışı: enforce_is_on kontrolü toggle'dan önce."""
        ei = self.wrap.find("enforce_is_on;")
        te = self.wrap.find("toggle_enforce false")
        self.assertNotEqual(ei, -1, "enforce_is_on; çağrısı bulunamadı")
        self.assertNotEqual(te, -1, "toggle_enforce false bulunamadı")
        self.assertLess(ei, te,
                        "enforce_is_on çağrısı toggle'dan önce olmalı")

    def test_push_flow_reopens_after(self):
        """Push sonrası toggle_enforce true ile geri açılır."""
        push = self.wrap.find("run git push -u origin main")
        reopen = self.wrap.find("toggle_enforce true;")
        self.assertNotEqual(push, -1)
        self.assertNotEqual(reopen, -1)
        self.assertLess(push, reopen,
                        "push tamamlandıktan sonra enforce geri açılmalı")

    def test_404_comment_exists(self):
        """'404 → dokunulmaz' yorumu (güvenle atlama belgesi)."""
        self.assertIn("404", self.wrap)
        self.assertIn("dokunulmaz", self.wrap)

    def test_dry_run_skips_toggle(self):
        """DRY_RUN != 1 kontrolü ile dry-run'da toggle atlanır."""
        self.assertIn("DRY_RUN", self.wrap)
        self.assertIn("enforce_is_on;", self.wrap)

    def test_toggle_false_on_failure_warns_not_fatal(self):
        """toggle_enforce false başarısızsa push denemeye devam eder."""
        self.assertIn("kapatılamadı", self.wrap)
        self.assertIn("push denenecek", self.wrap)

    def test_toggle_true_on_failure_is_fatal(self):
        """enforce_admins GERİ AÇILAMAZSA fail (manuel düzeltme gerekir)."""
        self.assertIn("GERİ AÇILAMADI", self.wrap)
        self.assertIn("manuel düzelt", self.wrap)


if __name__ == "__main__":
    unittest.main()