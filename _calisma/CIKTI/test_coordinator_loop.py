#!/usr/bin/env python3
"""coordinator_loop.py birim testleri.

Mock modda (--mock) opencode çağrılmaz; her kapı komutu gerçekten koşar ve
script_rc'den deterministik gate_done sidecar'ı üretilir. Testler:
- decision-gate zinciri sırası (REPACK→VERIFY→MANIFEST→CI),
- ilk kapalı kapıda durma (sonraki kapılar koşmaz / sidecar yazılmaz),
- --iterations ile başa dönme (retry),
- CI readonly vs live komut seçimi,
- fail-closed rapor (herhangi bir kapı FAIL → exit 1).
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator_loop as cl  # noqa: E402


def _run(wt, done, **kw):
    argv = ["--worktree", str(wt), "--done-dir", str(done), "--mock"]
    for k, v in kw.items():
        argv += ["--%s" % k.replace("_", "-"), str(v)]
    rc = cl.main(argv)
    with open(os.path.join(done, cl.RAPOR_JSON), encoding="utf-8") as f:
        rep = json.load(f)
    return rc, rep


class TestStdinClosed(unittest.TestCase):
    def test_invoke_opencode_closes_stdin(self):
        with mock.patch.object(cl.subprocess, "run", return_value=mock.Mock(stdout="")) as run:
            cl._invoke_opencode("opencode", "prompt", ".", 5)
        self.assertIs(run.call_args.kwargs["stdin"], cl.subprocess.DEVNULL)


class TestGateChain(unittest.TestCase):
    def test_gate_order_is_repack_verify_manifest_ci(self):
        self.assertEqual(cl.GATE_ORDER,
                         ["REPACK", "VERIFY", "MANIFEST", "CI"])

    def test_ci_readonly_vs_live_command(self):
        spec = cl.GATES["CI"]
        self.assertIn("gh run list", spec["command_readonly"])
        self.assertIn("gh workflow run", spec["command_live"])
        self.assertIn("gh run watch", spec["command_live"])


class TestLoopFlow(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.wt = pathlib.Path(self.td.name, "wt")
        self.wt.mkdir()
        self.done = pathlib.Path(self.td.name, "done")

    def tearDown(self):
        self.td.cleanup()

    def _patch_commands(self, fail=()):
        """Kapı komutlarını no-op'a çevir; fail set'indekiler 'false' olur."""
        for gate in cl.GATE_ORDER:
            spec = cl.GATES[gate]
            val = "false" if gate in fail else "echo ok"
            if gate == "CI":
                spec["command_readonly"] = spec["command_live"] = val
            else:
                spec["command"] = val

    def test_all_gates_pass(self):
        self._patch_commands()
        rc, rep = _run(self.wt, self.done)
        self.assertEqual(rc, 0)
        self.assertEqual(rep["verdict"], "PASS")
        self.assertEqual(len(rep["iterations"]), 1)
        self.assertEqual(rep["iterations"][0]["opened"], cl.GATE_ORDER)
        self.assertEqual(rep["iterations"][0]["closed"], [])

    def test_first_closed_gate_stops_chain(self):
        # VERIFY kapanırsa MANIFEST ve CI koşmamalı (sidecar yazılmamalı)
        self._patch_commands(fail={"VERIFY"})
        rc, rep = _run(self.wt, self.done)
        self.assertEqual(rc, 1)
        rec = rep["iterations"][0]
        self.assertEqual(rec["opened"], ["REPACK"])
        self.assertEqual(rec["closed"], ["VERIFY"])
        self.assertEqual(rec["gates"]["VERIFY"]["status"], "FAIL")
        # zincir kırıldı: MANIFEST/CI sidecar'ı YOK
        for gate in ("MANIFEST", "CI"):
            self.assertFalse(
                (self.done / cl.DONE_FILENAME.format(gate=gate)).exists(),
                "%s koşmamalıydı" % gate)

    def test_retry_until_iterations_exhausted(self):
        # CI kapısı hep kapanır; --iterations 2 ile iki döngü dener
        self._patch_commands(fail={"CI"})
        rc, rep = _run(self.wt, self.done, iterations=2)
        self.assertEqual(rc, 1)
        self.assertEqual(len(rep["iterations"]), 2)
        for rec in rep["iterations"]:
            self.assertEqual(rec["closed"], ["CI"])

    def test_retry_stops_early_on_pass(self):
        # İlk iterasyonda CI FAIL, ikinciye geçmeden önce komutları düzelt —
        # ama tek main() çağrısında komutlar sabit; bunun yerine 1 iterasyon
        # PASS ile döngünün erken kırıldığını doğrula.
        self._patch_commands()
        rc, rep = _run(self.wt, self.done, iterations=3)
        self.assertEqual(rc, 0)
        self.assertEqual(len(rep["iterations"]), 1)  # PASS → erken çıkış

    def test_report_files_and_sidecars(self):
        self._patch_commands()
        rc, rep = _run(self.wt, self.done)
        self.assertEqual(rc, 0)
        md = (self.done / cl.RAPOR_MD).read_text()
        self.assertIn("# Coordinator Raporu", md)
        self.assertIn("| 1 | REPACK | PASS |", md)
        for gate in cl.GATE_ORDER:
            self.assertTrue(
                (self.done / cl.DONE_FILENAME.format(gate=gate)).is_file())
        s = json.loads((self.done / "gate_done_REPACK.json").read_text())
        for key in ("gate", "label", "status", "rc", "rationale"):
            self.assertIn(key, s)
        self.assertEqual(s["gate"], "REPACK")

    def test_readonly_ci_mentioned_in_report(self):
        self._patch_commands()
        _run(self.wt, self.done)
        md = (self.done / cl.RAPOR_MD).read_text()
        self.assertIn("readonly", md)


if __name__ == "__main__":
    unittest.main()
