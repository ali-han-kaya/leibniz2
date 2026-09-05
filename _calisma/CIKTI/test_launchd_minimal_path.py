#!/usr/bin/env python3
"""test_launchd_minimal_path.py — launchd GUI agent minimal PATH fallback'leri.

launchd GUI agent'ı PATH=/usr/bin:/bin:… ile başlar — Homebrew araçlarına
PATH üzerinden ulaşamaz. verify_delivery.py K16 (node) ve K6 (pdfinfo)
bilinen mutlak konumlardan fallback yapar; hiçbiri yoksa fail-closed
(K16 node: P0; K6 pdfinfo: None → sayfa kontrolü atlanır, FAIL değil).

Bu test o ortamı SİMÜLE eder: PATH=/usr/bin:/bin iken fallback'in doğru
konumu bulduğunu ve hiçbir konum yokken None döndüğünü (fail-closed)
doğrular. Konum listeleri TEK KAYNAK github_scripts_battery.py'dedir
(NODE_KNOWN_PATHS / PDFINFO_KNOWN_PATHS / find_launchd_tool); verify_delivery
bunları import eder — iki kopya arasında drift olamaz.

Konak bağımsızlığı: gerçek /usr/bin/node (Linux CI) veya /opt/homebrew
(macOS) içeriği testi etkilemesin diye PATH taraması os.path.isfile
mock'lanır; test edilen şey ALGORİTMA + sabitler, makine kurulumu değil.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import github_scripts_battery as battery  # noqa: E402
import verify_delivery as vd  # noqa: E402

LAUNCHD_PATH = "/usr/bin:/bin"


def _fake_exe(path):
    """Belirtilen yolda çalıştırılabilir sahte bir araç yaratır."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    return path


class TestFindLaunchdTool(unittest.TestCase):
    """find_launchd_tool — tek kaynak github_scripts_battery.

    PATH=/usr/bin:/bin simülasyonu; PATH taraması isfile mock'lanarak
    konağın gerçek /usr/bin /bin içeriğinden yalıtılır.
    """

    def test_finds_node_at_known_location_under_minimal_path(self):
        """PATH=/usr/bin:/bin'de node yok; bilinen konumda varsa bulunur."""
        with tempfile.TemporaryDirectory(prefix="launchd-node-") as td:
            fake = _fake_exe(os.path.join(td, "node"))
            with mock.patch.object(battery.os.path, "isfile",
                                   side_effect=lambda p: p == fake), \
                 mock.patch.object(battery.os, "access",
                                   return_value=True):
                found = battery.find_launchd_tool(
                    "node", (fake,), path_env=LAUNCHD_PATH)
            self.assertEqual(found, fake)

    def test_finds_pdfinfo_at_known_location_under_minimal_path(self):
        """K6: pdfinfo bilinen konumda varsa bulunur (PATH'te yokken)."""
        with tempfile.TemporaryDirectory(prefix="launchd-pdfinfo-") as td:
            fake = _fake_exe(os.path.join(td, "pdfinfo"))
            with mock.patch.object(battery.os.path, "isfile",
                                   side_effect=lambda p: p == fake), \
                 mock.patch.object(battery.os, "access",
                                   return_value=True):
                found = battery.find_launchd_tool(
                    "pdfinfo", (fake,), path_env=LAUNCHD_PATH)
            self.assertEqual(found, fake)

    def test_fail_closed_when_no_known_location(self):
        """Hiçbir konumda yok → None (fail-closed; çağıran karar verir)."""
        with mock.patch.object(battery.os.path, "isfile",
                               return_value=False):
            self.assertIsNone(battery.find_launchd_tool(
                "node", ("/nonexistent/node",), path_env=LAUNCHD_PATH))

    def test_fail_closed_when_known_location_not_executable(self):
        """Konum dosyası var ama çalıştırılabilir değil → None."""
        with tempfile.TemporaryDirectory(prefix="launchd-noexec-") as td:
            p = os.path.join(td, "node")
            with open(p, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 0\n")  # chmod YOK → X_OK değil
            with mock.patch.object(battery.os.path, "isfile",
                                   return_value=True), \
                 mock.patch.object(battery.os, "access",
                                   return_value=False):
                self.assertIsNone(battery.find_launchd_tool(
                    "node", (p,), path_env=LAUNCHD_PATH))

    def test_path_precedence_over_known_paths(self):
        """PATH'teki araç, bilinen konumlardan ÖNCE kazanır (shutil.which
        davranışı korunur: PATH birincil, fallback ikincil)."""
        with tempfile.TemporaryDirectory(prefix="launchd-p1-") as td1, \
             tempfile.TemporaryDirectory(prefix="launchd-p2-") as td2:
            on_path = _fake_exe(os.path.join(td1, "node"))
            known = _fake_exe(os.path.join(td2, "node"))
            with mock.patch.object(battery.os.path, "isfile",
                                   side_effect=lambda p: p in (on_path,
                                                               known)), \
                 mock.patch.object(battery.os, "access",
                                   return_value=True):
                found = battery.find_launchd_tool(
                    "node", (known,),
                    path_env=td1 + os.pathsep + LAUNCHD_PATH)
            self.assertEqual(found, on_path)

    def test_mismatched_known_path_rejected(self):
        """Yanlış known_paths (basename eşleşmiyor) → None (fail-closed).

        NODE_KNOWN_PATHS'teki bir executable pdfinfo istenirken dönmemeli —
        adayın basename'i istenen aracın adıyla eşleşmeli.
        """
        with tempfile.TemporaryDirectory(prefix="launchd-mismatch-") as td:
            node_exe = _fake_exe(os.path.join(td, "node"))
            # PATH taraması boş (minimal PATH'te pdfinfo yok); yalnızca
            # known candidate var ama basename uyuşmuyor → None.
            with mock.patch.object(battery.os.path, "isfile",
                                   side_effect=lambda p: p == node_exe), \
                 mock.patch.object(battery.os, "access",
                                   return_value=True):
                self.assertIsNone(battery.find_launchd_tool(
                    "pdfinfo", (node_exe,), path_env=LAUNCHD_PATH))

    def test_real_constants_point_at_node_and_pdfinfo(self):
        """Sabitler gerçek araç adlarına işaret eder (syntax/amaç kapısı)."""
        self.assertTrue(all(p.endswith("node") for p in battery.NODE_KNOWN_PATHS))
        self.assertTrue(all(p.endswith("pdfinfo")
                            for p in battery.PDFINFO_KNOWN_PATHS))
        # verify_delivery TEK KAYNAKTAN beslenir — iki kopya yok.
        self.assertIs(vd._LAUNCHD_NODE_PATHS, battery.NODE_KNOWN_PATHS)
        self.assertIs(vd._LAUNCHD_PDFINFO_PATHS, battery.PDFINFO_KNOWN_PATHS)


class TestPdfPagesLaunchdFallback(unittest.TestCase):
    """K6 pdf_pages: fallback bulduğu pdfinfo'yu kullanır; yoksa atlanır."""

    def _fake_pdfinfo(self, pages):
        """`Pages: N` basan sahte pdfinfo script'i (tam yol) döner."""
        td = tempfile.mkdtemp(prefix="launchd-pdfinfo-exe-")
        self.addCleanup(lambda: __import__("shutil").rmtree(td, ignore_errors=True))
        exe = os.path.join(td, "pdfinfo")
        with open(exe, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\necho 'Pages: {pages}'\nexit 0\n")
        os.chmod(exe, 0o755)
        return exe

    def test_pdf_pages_uses_fallback_found_pdfinfo(self):
        """Fallback pdfinfo'yu buldu → sayfa sayısı döner (PASS yolu)."""
        exe = self._fake_pdfinfo(42)
        fake_pdf = os.path.join(os.path.dirname(exe), "x.pdf")
        with open(fake_pdf, "w", encoding="utf-8") as f:
            f.write("%PDF-1.4\n")
        with mock.patch.object(vd, "_launchd_find", return_value=exe):
            self.assertEqual(vd.pdf_pages(fake_pdf), 42)

    def test_pdf_pages_skips_when_pdfinfo_missing(self):
        """Fallback hiçbir yerde yok → None (atlanır, FAIL değil)."""
        with mock.patch.object(vd, "_launchd_find", return_value=None), \
             mock.patch.object(vd.subprocess, "run",
                               side_effect=FileNotFoundError):
            self.assertIsNone(vd.pdf_pages("/tmp/nonexistent.pdf"))


class TestK16LaunchdFailClosed(unittest.TestCase):
    """K16: launchd minimal PATH'te node bulunamazsa fail-closed P0."""

    def _collector(self):
        findings = []

        def add(priority, fid, check, message, detail=""):
            findings.append({"priority": priority, "id": fid,
                             "check": check, "message": message,
                             "detail": detail})

        return add, findings

    def test_k16_node_missing_is_p0_fail_closed(self):
        """node None → (False, 'node bulunamadı') + P0 bulgusu; battery
        çalıştırılmaz (fail-closed)."""
        add, findings = self._collector()
        with mock.patch.object(vd, "_launchd_find", return_value=None), \
             mock.patch.object(vd.subprocess, "run") as run:
            ok, detail = vd.check_github_scripts_self_test(add)
        run.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("node bulunamadı", detail)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["priority"], "P0")
        self.assertEqual(findings[0]["id"], "K16-GSCRIPTS")

    def test_k16_uses_resolved_node(self):
        """Fallback node'u buldu → battery o node'la koşulur (PASS yolu)."""
        add, findings = self._collector()
        with tempfile.TemporaryDirectory(prefix="launchd-k16-") as td:
            fake = _fake_exe(os.path.join(td, "node"))
            fake_res = mock.MagicMock(returncode=0,
                                      stdout="SONUÇ: PASS — 58/58 senaryo\n",
                                      stderr="")
            with mock.patch.object(vd, "_launchd_find", return_value=fake), \
                 mock.patch.object(vd.subprocess, "run",
                                   return_value=fake_res) as run:
                ok, detail = vd.check_github_scripts_self_test(add)
        run.assert_called_once()
        self.assertTrue(ok)
        self.assertIn("SONUÇ: PASS", detail)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
