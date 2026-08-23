#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_k18_daemon.py — K18 (daemon HTTP smoke) katmanının birim testleri.

verify_delivery.py --check-daemon (K18) → daemon_http_test.py'yi alt süreç
olarak koşar ve raporunu fail-closed doğrular. Kapsanan davranışlar:

  1. PASS: alt süreç exit 0 + rapor ok=True → ok, bulgu yok
  2. FAIL: exit 1 veya rapor ok=False → P1 (fail-closed)
  3. Script yok → P1
  4. PREVIEW_DAEMON=1 (iç içe koşum) → PASS-durumlu SKIP (sonsuz özyineleme
     koruması — daemon smoke'un başlattığı sunucunun verify_loop'u da --full
     koşar ve K18'i tetikler)
  5. --full → check_daemon=True (apply_full_flags)
  6. Katman haritası: K18=Daemon, K20=Launchctl (renumbering)
  7. build_layers_summary: check_daemon=True → K18 ran, P1 bulgu varsa FAIL

stdlib unittest — ek bağımlılık yok.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verify_delivery as vd  # noqa: E402


def _report(ok=True, endpoints=None, daemon_alive=True, error=None):
    return {"ok": ok,
            "endpoints": endpoints or {"/preview.html": 200,
                                       "/api/latest": 200,
                                       "/api/history": 200},
            "daemon_alive": daemon_alive, "error": error}


def _fake_run(rc, report):
    """subprocess.run döndürüsünü taklit eder; --out raporunu dosyaya yazar.

    check_daemon_smoke, raporu report_path'ten okur — mock alt süreç bu
    dosyayı gerçek daemon_http_test.py gibi yazar (rapor okuma yolu test
    edilebilsin diye).
    """
    def _side_effect(cmd, **kwargs):
        out = None
        for i, part in enumerate(cmd):
            if part == "--out" and i + 1 < len(cmd):
                out = cmd[i + 1]
        if out:
            pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(out).write_text(
                json.dumps(report), encoding="utf-8")
        fake = mock.Mock()
        fake.returncode = rc
        fake.stdout = "PASS\n" if rc == 0 else "FAIL\n"
        fake.stderr = ""
        return fake

    return mock.Mock(side_effect=_side_effect)


class TestCheckDaemonSmoke(unittest.TestCase):
    """check_daemon_smoke — mock subprocess ile fail-closed davranışı."""

    def _call(self, env_extra=None, out_path=None, run_fake=None):
        env = dict(os.environ)
        env.pop("PREVIEW_DAEMON", None)
        if env_extra:
            env.update(env_extra)
        findings = []
        add = lambda prio, cid, label, issue, evidence="": findings.append(
            {"priority": prio, "check": cid, "issue": issue,
             "evidence": evidence})
        with mock.patch.object(vd.os, "environ", env), \
             mock.patch.object(vd.subprocess, "run", run_fake):
            ok, detail, report = vd.check_daemon_smoke(add, out_path=out_path)
        return ok, detail, report, findings

    def test_pass_exit0_report_ok(self):
        fake = _fake_run(0, _report())
        fake.returncode = 0
        ok, detail, report, findings = self._call(run_fake=fake)
        self.assertTrue(ok)
        self.assertIn("PASS", detail)
        self.assertTrue(report["ok"])
        self.assertEqual(findings, [])

    def test_fail_exit1_p1(self):
        fake = _fake_run(1, _report(ok=False, error="timeout"))
        fake.returncode = 1
        ok, detail, report, findings = self._call(run_fake=fake)
        self.assertFalse(ok)
        self.assertIn("FAIL", detail)
        self.assertTrue(any(f["check"] == "K18-DAEMON" for f in findings))

    def test_fail_report_ok_false_even_exit0_p1(self):
        # exit 0 ama rapor ok=False → yine P1 (fail-closed: rapor tek kaynak).
        fake = _fake_run(0, _report(ok=False, error="daemon öldü"))
        fake.returncode = 0
        ok, detail, report, findings = self._call(run_fake=fake)
        self.assertFalse(ok)
        self.assertTrue(any(f["priority"] == "P1" for f in findings))

    def test_nested_preview_daemon_skips(self):
        # İç içe koşum: PREVIEW_DAEMON=1 → PASS-durumlu SKIP (özyineleme yok).
        fake = _fake_run(0, _report())
        fake.returncode = 0
        ok, detail, report, findings = self._call(
            env_extra={"PREVIEW_DAEMON": "1"}, run_fake=fake)
        self.assertTrue(ok)
        self.assertIn("atlandı", detail)
        self.assertEqual(findings, [])

    def test_script_yok_p1(self):
        # daemon_http_test.py yoksa P1 (fail-closed).
        real_isfile = os.path.isfile
        script = os.path.join(str(HERE), "daemon_http_test.py")
        fake = _fake_run(1, _report(ok=False))
        with mock.patch.object(vd.os.path, "isfile",
                               side_effect=lambda p: False if p == script
                               else real_isfile(p)):
            ok, detail, report, findings = self._call(run_fake=fake)
        self.assertFalse(ok)
        self.assertIn("yok", detail)
        self.assertTrue(any(f["check"] == "K18-DAEMON" for f in findings))

    def test_sidecar_out_written(self):
        # --daemon-out verilirse rapor o yola yazılır (sidecar) ve mock alt
        # süreç --out olarak o yolu alır (sözleşme: rapor orada üretilir).
        with tempfile.TemporaryDirectory(prefix="k18-") as tmp:
            out = os.path.join(tmp, "daemon_http_report.json")
            fake = _fake_run(0, _report())
            ok, detail, report, _ = self._call(out_path=out, run_fake=fake)
            self.assertTrue(ok)
            # Mock --out olarak out_path'i aldı → rapor o yola yazıldı.
            self.assertTrue(os.path.isfile(out))
            with open(out, encoding="utf-8") as f:
                self.assertTrue(json.load(f)["ok"])


class TestK18Wiring(unittest.TestCase):
    """Katman numaralandırması + --full bağlantısı."""

    def test_layer_labels_renumbered(self):
        self.assertIn("Daemon", vd.LAYER_LABELS["K18"])
        self.assertIn("Launchctl", vd.LAYER_LABELS["K20"])
        self.assertIn("Coq", vd.LAYER_LABELS["K19"])

    def test_optional_layer_getters(self):
        args = types.SimpleNamespace(check_daemon=False, check_launchd=False,
                                     coq_proof=False)
        self.assertFalse(vd._OPTIONAL_LAYERS["K18"](args))
        args.check_daemon = True
        self.assertTrue(vd._OPTIONAL_LAYERS["K18"](args))
        args.check_launchd = True
        self.assertTrue(vd._OPTIONAL_LAYERS["K20"](args))

    def test_full_enables_daemon(self):
        args = types.SimpleNamespace(full=True)
        # apply_full_flags tüm bayrakları set eder; yalnızca K18'i doğrula.
        args.check_references = args.symbolic_proof = args.lean_proof = False
        args.check_lineage = args.check_repro_manifest = False
        args.check_config_drift = args.check_cleanup = False
        args.check_github_scripts = False
        args.check_mirror = False
        args.mirror_auto_sync = False
        args = vd.apply_full_flags(args)
        self.assertTrue(args.check_daemon)

    def test_build_layers_k18_ran_when_enabled(self):
        args = types.SimpleNamespace(
            symbolic_proof=False, lean_proof=False, verify_manifest=None,
            check_config_drift=False, check_plist=False,
            check_repro_manifest=False, check_cleanup=False,
            check_history=None, check_github_scripts=False,
            check_mirror=False, check_daemon=True, check_launchd=False,
            coq_proof=False)
        findings = [{"id": "K18-DAEMON", "priority": "P1",
                     "check": "K18-DAEMON", "issue": "smoke başarısız",
                     "evidence": ""}]
        layers = vd.build_layers_summary(args, findings)
        self.assertEqual(layers["K18"]["status"], "FAIL")
        self.assertTrue(layers["K18"]["ran"])
        self.assertEqual(layers["K20"]["status"], "SKIP")

    def test_main_json_has_daemon_key(self):
        text = pathlib.Path(vd.__file__).read_text(encoding="utf-8")
        self.assertIn('"daemon": daemon_report', text)


if __name__ == "__main__":
    unittest.main()
