#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_hook_unstaged_deps.py — yeni hook wrapper'larının ön-kontrolü.

check_pattern_consistency_hook.py + verify_delivery_hook.py: bağımlılık
dosyalarının stage durumunu denetler; untracked/unstaged dosyalar için NET
uyarı basar (advisory) ve asıl kapıyı (check_pattern_consistency.py /
verify_delivery.py) aynı exit koduyla koşar. Bu testler git'i gerçekten
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

import check_pattern_consistency_hook as cpc_hook  # noqa: E402
import verify_delivery_hook as vd_hook  # noqa: E402


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class TestCheckPatternConsistencyHook(unittest.TestCase):
    """check_pattern_consistency_hook: DEPS + uyarı + kapı exit kodu."""

    def test_deps_cover_sources(self):
        self.assertIn(".github/workflows/verify.yml", cpc_hook.DEPS)
        self.assertIn("_calisma/CIKTI/check_pattern_consistency.py",
                      cpc_hook.DEPS)
        self.assertIn("_calisma/CIKTI/gen_repro_manifest.py", cpc_hook.DEPS)

    def test_unstaged_deps_passed_to_shared(self):
        args = {}

        def fake_run(cmd, **kw):
            args["cmd"] = cmd
            return _Proc(stdout=" M .github/workflows/verify.yml\n")
        with mock.patch.object(subprocess, "run", side_effect=fake_run):
            d = cpc_hook.unstaged_deps()
        self.assertIn("--", args["cmd"])
        self.assertIn(".github/workflows/verify.yml", args["cmd"])
        self.assertIn("unstaged", d[".github/workflows/verify.yml"])

    def test_main_warning_and_gate_runs(self):
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={
                ".github/workflows/verify.yml": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = cpc_hook.main()
        self.assertEqual(rc, 0)
        err = buf.getvalue()
        self.assertIn("check-pattern-consistency ÖN-KONTROL", err)
        self.assertIn("STAGE EDİLMEMİŞ", err)
        self.assertIn("git add", err)

    def test_main_clean_no_warning(self):
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = cpc_hook.main()
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "")

    def test_main_gate_failure_propagates(self):
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=1)):
            self.assertEqual(cpc_hook.main(), 1)

    def test_main_invokes_check_pattern_consistency(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            cpc_hook.main()
        gate = calls[-1]
        self.assertEqual(gate[0], sys.executable)
        self.assertTrue(gate[-1].endswith("check_pattern_consistency.py"))

    def test_main_strict_blocks_on_dirty(self):
        """--strict + kirli deps → exit 2, asıl kapı KOŞMAZ."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={
                ".github/workflows/verify.yml": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = cpc_hook.main(["--strict"])
        self.assertEqual(rc, 2)
        err = buf.getvalue()
        self.assertIn("--strict", err)
        self.assertIn("HOOK BLOKE", err)
        self.assertIn("git add", err)
        self.assertEqual(calls, [], "strict blokta asıl kapı çalışmamalı")

    def test_main_strict_clean_passes(self):
        """--strict + temiz deps → gate normal koşar, exit 0."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(cpc_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            rc = cpc_hook.main(["--strict"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, "gate bir kez koşmalı")


class TestVerifyDeliveryHook(unittest.TestCase):
    """verify_delivery_hook: DEPS + uyarı + kapı exit kodu."""

    def test_deps_cover_sources(self):
        self.assertIn("_calisma/CIKTI/verify_delivery.py", vd_hook.DEPS)
        self.assertIn("_calisma/CIKTI/verify_delivery.config.json",
                      vd_hook.DEPS)
        self.assertIn("_calisma/CIKTI/verify_delivery.config.schema.json",
                      vd_hook.DEPS)
        self.assertIn("_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip",
                      vd_hook.DEPS)
        self.assertIn("_calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip",
                      vd_hook.DEPS)

    def test_unstaged_deps_passed_to_shared(self):
        args = {}

        def fake_run(cmd, **kw):
            args["cmd"] = cmd
            return _Proc(stdout="?? _calisma/CIKTI/verify_delivery.py\n")
        with mock.patch.object(subprocess, "run", side_effect=fake_run):
            d = vd_hook.unstaged_deps()
        self.assertIn("--", args["cmd"])
        self.assertIn("_calisma/CIKTI/verify_delivery.py", args["cmd"])
        self.assertIn("untracked", d["_calisma/CIKTI/verify_delivery.py"])

    def test_main_warning_and_gate_runs(self):
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={
                "_calisma/CIKTI/verify_delivery.py": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = vd_hook.main()
        self.assertEqual(rc, 0)
        err = buf.getvalue()
        self.assertIn("verify-delivery ÖN-KONTROL", err)
        self.assertIn("STAGE EDİLMEMİŞ", err)
        self.assertIn("git add", err)

    def test_main_clean_no_warning(self):
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = vd_hook.main()
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "")

    def test_main_gate_failure_propagates(self):
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run",
                                  return_value=mock.Mock(returncode=1)):
            self.assertEqual(vd_hook.main(), 1)

    def test_main_invokes_verify_delivery(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            vd_hook.main()
        gate = calls[-1]
        self.assertEqual(gate[0], sys.executable)
        self.assertTrue(gate[1].endswith("verify_delivery.py"))
        self.assertIn("--dir", gate)
        self.assertIn("_calisma/CIKTI", gate)

    def test_main_strict_blocks_on_dirty(self):
        """--strict + kirli deps → exit 2, asıl kapı KOŞMAZ."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={
                "_calisma/CIKTI/verify_delivery.py": "unstaged değişiklik"}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = vd_hook.main(["--strict"])
        self.assertEqual(rc, 2)
        err = buf.getvalue()
        self.assertIn("--strict", err)
        self.assertIn("HOOK BLOKE", err)
        self.assertIn("git add", err)
        self.assertEqual(calls, [], "strict blokta asıl kapı çalışmamalı")

    def test_main_strict_clean_passes(self):
        """--strict + temiz deps → gate normal koşar, exit 0."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0)
        with mock.patch.object(vd_hook, "unstaged_deps", return_value={}), \
                mock.patch.object(subprocess, "run", side_effect=fake_run):
            rc = vd_hook.main(["--strict"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, "gate bir kez koşmalı")


if __name__ == "__main__":
    unittest.main()
