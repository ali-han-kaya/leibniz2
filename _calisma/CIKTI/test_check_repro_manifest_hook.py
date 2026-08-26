#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_repro_manifest_hook.py — check-repro-manifest ön-kontrolü kapısı.

check_repro_manifest_hook.py: bağımlılık dosyalarının (verify.yml,
gen_repro_manifest.py, test_gen_repro_manifest.py) stage durumunu denetler;
untracked/unstaged dosyalar için NET uyarı basar (advisory) ve asıl unittest
kapısını aynı exit koduyla koşar. Bu testler git/UNITTEST'i gerçekten
çağırmaz — subprocess mock'lanır (deterministik, ağsız, OFFLINE).
"""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_repro_manifest_hook as hook  # noqa: E402


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class TestUnstagedDeps(unittest.TestCase):
    """git status --porcelain çıktısından stage durumu çıkarımı."""

    def test_clean_deps_no_warning(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_Proc(stdout="")):
            self.assertEqual(hook.unstaged_deps(), {})

    def test_unstaged_modified_warns(self):
        with mock.patch.object(subprocess, "run", return_value=_Proc(
                stdout=" M .github/workflows/verify.yml\n")):
            d = hook.unstaged_deps()
            self.assertIn(".github/workflows/verify.yml", d)
            self.assertIn("unstaged", d[".github/workflows/verify.yml"])

    def test_untracked_warns(self):
        with mock.patch.object(subprocess, "run", return_value=_Proc(
                stdout="?? _calisma/CIKTI/gen_repro_manifest.py\n")):
            d = hook.unstaged_deps()
            self.assertIn("_calisma/CIKTI/gen_repro_manifest.py", d)
            self.assertIn("untracked", d["_calisma/CIKTI/gen_repro_manifest.py"])

    def test_staged_plus_unstaged_warns(self):
        with mock.patch.object(subprocess, "run", return_value=_Proc(
                stdout="MM _calisma/CIKTI/test_gen_repro_manifest.py\n")):
            d = hook.unstaged_deps()
            self.assertIn("_calisma/CIKTI/test_gen_repro_manifest.py", d)
            self.assertIn("çift durum", d["_calisma/CIKTI/test_gen_repro_manifest.py"])

    def test_staged_only_is_clean(self):
        # 'M ' (yalnızca index'te) → commit'e girecek → uyarı yok.
        with mock.patch.object(subprocess, "run", return_value=_Proc(
                stdout="M  .github/workflows/verify.yml\n")):
            self.assertEqual(hook.unstaged_deps(), {})

    def test_all_deps_checked_in_one_call(self):
        args = {}

        def fake_run(cmd, **kw):
            args["cmd"] = cmd
            return _Proc(stdout="")
        with mock.patch.object(subprocess, "run", side_effect=fake_run):
            hook.unstaged_deps()
        self.assertIn("--", args["cmd"])
        for rel in hook.DEPS:
            self.assertIn(rel, args["cmd"], f"{rel} denetimde yok")


class TestMain(unittest.TestCase):
    """Uyarı basımı + asıl kapının exit kodunun korunması."""

    def test_warning_printed_and_tests_run(self):
        with mock.patch.object(hook, "unstaged_deps", return_value={
                ".github/workflows/verify.yml": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = hook.main()
        self.assertEqual(rc, 0)
        err = buf.getvalue()
        self.assertIn("ÖN-KONTROL", err)
        self.assertIn("STAGE EDİLMEMİŞ", err)
        self.assertIn(".github/workflows/verify.yml", err)
        self.assertIn("git add", err)

    def test_clean_deps_no_warning(self):
        with mock.patch.object(hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = hook.main()
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "")

    def test_test_failure_exit_code_propagates(self):
        with mock.patch.object(hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=1)):
            rc = hook.main()
        self.assertEqual(rc, 1)

    def test_unittest_invoked_with_discovery(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            hook.main()
        unittest_cmd = calls[-1]
        self.assertEqual(unittest_cmd[0], sys.executable)
        self.assertIn("-m", unittest_cmd)
        self.assertIn("unittest", unittest_cmd)
        self.assertIn("test_gen_repro_manifest.py", unittest_cmd)

    def test_strict_blocks_on_dirty(self):
        """--strict + kirli deps → exit 2, unittest KOŞMAZ."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(hook, "unstaged_deps", return_value={
                ".github/workflows/verify.yml": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = hook.main(["--strict"])
        self.assertEqual(rc, 2)
        err = buf.getvalue()
        self.assertIn("--strict", err)
        self.assertIn("HOOK BLOKE", err)
        self.assertEqual(calls, [], "strict blokta unittest çalışmamalı")

    def test_strict_clean_passes(self):
        """--strict + temiz deps → unittest koşar, exit 0."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            rc = hook.main(["--strict"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, "unittest bir kez koşmalı")


if __name__ == "__main__":
    unittest.main()
