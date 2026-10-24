#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_token_delivery_contract.py — token_delivery.py exit-code kontrati.

rc haritasi (CI adimi bu kodlari bekler):
  0 PASS / 1 LEAK / 2 VACUITY / 3 ENV

Saf cekirdek `evaluate()` pin'lenir (sentetik kampanyalar — her rc yolu),
gercek integrasyon iki kip (rc=0 ve mutasyon rc=1) subprocess ile kosturulur,
air-gap guard'i modul seviyesinde dogrulanir (socket kapali).
"""
import json
import pathlib
import subprocess
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import token_delivery as td  # noqa: E402


def _campaign(**over):
    base = {
        "redact": True,
        "seeds": 120,
        "ops_per_seed": 45,
        "total_leaks": 0,
        "first_leak": None,
        "token_on_channel": True,
        "surfaces_seen": list(td.SURFACES),
        "issued_any": True,
        "probe_found_leak": True,
    }
    base.update(over)
    return base


class TestEvaluateExitCodes(unittest.TestCase):
    """Saf degerlendirme cekirdegi: her rc yolu pin'lenir."""

    def test_pass(self):
        rc, report = td.evaluate(_campaign())
        self.assertEqual(rc, td.RC_PASS)
        self.assertEqual(report["verdict"], "PASS")

    def test_leak(self):
        rc, report = td.evaluate(_campaign(total_leaks=3,
                                           first_leak={"seed": 5}))
        self.assertEqual(rc, td.RC_LEAK)
        self.assertEqual(report["verdict"], "LEAK")

    def test_vacuity_empty_seeds(self):
        rc, report = td.evaluate(_campaign(seeds=0))
        self.assertEqual(rc, td.RC_VACUITY)
        self.assertIn("tohum", report["reason"])

    def test_vacuity_no_token_issued(self):
        rc, report = td.evaluate(_campaign(issued_any=False))
        self.assertEqual(rc, td.RC_VACUITY)

    def test_vacuity_token_never_flowed(self):
        rc, report = td.evaluate(_campaign(token_on_channel=False))
        self.assertEqual(rc, td.RC_VACUITY)
        self.assertIn("kanalda", report["reason"])

    def test_vacuity_surface_not_covered(self):
        rc, report = td.evaluate(_campaign(
            surfaces_seen=["log", "metric", "status_api"]))
        self.assertEqual(rc, td.RC_VACUITY)
        self.assertIn("exception", report["reason"])
        self.assertIn("stdout", report["reason"])

    def test_vacuity_probe_broken(self):
        rc, report = td.evaluate(_campaign(probe_found_leak=False))
        self.assertEqual(rc, td.RC_VACUITY)
        self.assertIn("mutasyon", report["reason"])


class TestAirgapGuard(unittest.TestCase):
    def test_socket_blocked(self):
        import socket
        td.install_airgap_guard()
        with self.assertRaises(RuntimeError):
            socket.create_connection(("example.com", 80))
        with self.assertRaises(RuntimeError):
            socket.getaddrinfo("example.com", 80)


class TestCliIntegration(unittest.TestCase):
    """Gercek CLI kosumu: rc=0 (kontrat) ve rc=1 (mutasyon canary)."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(CIKTI / "token_delivery.py"), *args],
            capture_output=True, text=True, timeout=120)

    def test_cli_pass_rc0_json(self):
        p = self._run("--json", "--seeds", "30", "--probe-seeds", "10")
        self.assertEqual(p.returncode, 0,
                         f"stdout={p.stdout[:400]} stderr={p.stderr[:200]}")
        report = json.loads(p.stdout)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["total_leaks"], 0)
        self.assertIn("Sonuc: PASS", p.stderr)

    def test_cli_mutation_canary_rc1(self):
        p = self._run("--redact", "off", "--json", "--seeds", "30")
        self.assertEqual(p.returncode, 1,
                         f"canary rc!=1 stdout={p.stdout[:400]}")
        report = json.loads(p.stdout) if p.stdout.strip().startswith("{") \
            else {}
        self.assertEqual(report.get("verdict"), "LEAK")
        self.assertGreater(report.get("total_leaks", 0), 0)
        self.assertIsNotNone(report.get("first_leak"))
        self.assertIn("seed", report["first_leak"])

    def test_cli_usage_rc3(self):
        p = self._run("--seeds", "0")
        self.assertEqual(p.returncode, 3)


if __name__ == "__main__":
    unittest.main()
