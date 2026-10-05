#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preview mirror'ının import-closure sözleşmesi.

sync_verify_mirror.sh PREVIEW_FILES bloğu, PREVIEW_MIRROR'a kopyalanan
preview çalıştırıcı kümesini tanımlar. preview_server.py bu kümeden
modül import eder; import listesine eklenen ama manifest'e girmEYEN bir
modül, taze mirror'da ModuleNotFoundError üretir ve dashboard TCC/launchd
rotasında servis edilmeden düşer (regresyon: precommit_log).

Sözleşme:
  1) preview_server.py'nin CIKTI'ya göreli import kümesi ⊆ PREVIEW_FILES
     girdileri (manifest'te kaynağı bulunmayan import yok).
  2) PREVIEW_FILES girdileriyle kurulan taze bir mirror dizininde
     `import preview_server` temiz tamamlanır ve /api/health 200 döner.
"""
import ast
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC_SCRIPT = os.path.join(HERE, "sync_verify_mirror.sh")
PREVIEW_SERVER = os.path.join(HERE, "preview_server.py")
PYTHON = sys.executable


def _free_port():
    """OS'ten boş bir loopback portu ayır."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port, timeout=60):
    """Sunucu ayağa kalkana dek /api/health yoklar; son durum kodu döner."""
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            status = None
            time.sleep(0.5)
    return status


def preview_manifest_entries():
    """PREVIEW_FILES bloğundaki "kaynak|dest" girdilerini döndürür.

    Tek kaynak kuralı: liste yalnızca sync_verify_mirror.sh içinde
    tanımlıdır; test onu ayrıca hardcode etmez.
    """
    with open(SYNC_SCRIPT, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"^PREVIEW_FILES=\(\n(.*?)^\)$", text, re.S | re.M)
    if not match:
        raise AssertionError("sync_verify_mirror.sh içinde PREVIEW_FILES bulunamadı")
    entries = []
    for line in match.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip().strip('"').strip("'") for p in line.split("|", 1)]
        entries.append(tuple(parts))
    return entries


def local_imports(path):
    """preview_server.py'nin CIKTI'ya göreli (local) import modül adları.

    Yalnızca yanında .py dosyası BULUNAN modüller döner — stdlib ve
    üçüncü taraf paketler (json, os, urllib...) bu filtreyle elenir.
    Lazy (fonksiyon gövdesi) import'lar da kapsamdadır: preview_server
    bunları çalışma anında, CIKTI'ya eklenmiş sys.path üzerinden çözer.
    """
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level == 0 → mutlak (local) import; level > 0 → göreli paket
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return {n for n in names
            if os.path.isfile(os.path.join(os.path.dirname(path), n + ".py"))}


class PreviewMirrorImportClosureTest(unittest.TestCase):
    def test_local_imports_are_covered_by_manifest(self):
        """Her local import PREVIEW_FILES'te karşılık bulmalı."""
        # import adı modüldür ("precommit_log"); manifest girdisi dosya
        # yoludur ("precommit_log.py") — .py uzantısı atılır.
        manifest_sources = {src[:-3] if src.endswith(".py") else src
                            for src, _ in preview_manifest_entries()}
        missing = sorted(n for n in local_imports(PREVIEW_SERVER)
                         if n not in manifest_sources)
        self.assertEqual(
            [], missing,
            "preview_server.py local import'ları PREVIEW_FILES manifest'inde "
            f"yok — taze mirror'da ModuleNotFoundError: {missing}")

    def test_manifest_sources_all_exist(self):
        """Manifest girdileri CIKTI'da karşılık bulmalı (bayat girdi yok)."""
        absent = sorted(src for src, _ in preview_manifest_entries()
                        if not os.path.isfile(os.path.join(HERE, src)))
        self.assertEqual([], absent, f"PREVIEW_FILES girdileri diskte yok: {absent}")

    def test_fresh_mirror_imports_and_serves_health(self):
        """Taze mirror: import temiz, /api/health 200."""
        entries = preview_manifest_entries()
        workdir = tempfile.mkdtemp(prefix="preview-mirror-")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        for src, dest in entries:
            target = os.path.join(workdir, dest)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(HERE, src), target)

        probe = (
            "import preview_server as ps\n"
            "srv = ps.make_server() if hasattr(ps, 'make_server') else None\n"
            "print('IMPORT_OK')\n"
        )
        r = subprocess.run([PYTHON, "-c", probe], cwd=workdir,
                           capture_output=True, text=True, timeout=60)
        self.assertIn("IMPORT_OK", r.stdout,
                      f"taze mirror'da import başarısız: {r.stderr[-2000:]}")

        # /api/health — gerçek sunucuyu main() ile boş portta ayağa kaldır.
        # preview-dir ve --dir, mirror'da yeterli dosya bulunsun diye
        # ayrıca hazırlanır (preview.html + verify_delivery.py).
        preview_dir = os.path.join(workdir, "_preview")
        verify_dir = os.path.join(workdir, "_verify")
        os.makedirs(preview_dir, exist_ok=True)
        os.makedirs(verify_dir, exist_ok=True)
        shutil.copy2(os.path.join(HERE, "preview.html"),
                     os.path.join(preview_dir, "preview.html"))
        shutil.copy2(os.path.join(HERE, "verify_delivery.py"),
                     os.path.join(verify_dir, "verify_delivery.py"))

        port = _free_port()
        proc = subprocess.Popen(
            [PYTHON, os.path.join(workdir, "preview_server.py"),
             "--dir", verify_dir, "--preview-dir", preview_dir,
             "--port", str(port), "--interval", "3600"],
            cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True)
        try:
            status = _wait_for_health(port, timeout=60)
        finally:
            proc.terminate()
            try:
                out = proc.communicate(timeout=15)[0]
            except subprocess.TimeoutExpired:
                proc.kill()
                out = proc.communicate()[0]
        self.assertEqual(200, status,
                         f"taze mirror'da /api/health 200 vermedi "
                         f"(status={status})\n{out[-2000:]}")


if __name__ == "__main__":
    unittest.main()