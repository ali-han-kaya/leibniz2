#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_history.py — K15 (history.jsonl ↔ .sha256 sidecar) regresyon kapısı.

İki yarıyı birlikte kapılar:
  - preview_server.persist_history her yazımda history.jsonl.sha256 üretir
    (sha256sum formatı, içerikle birebir).
  - verify_delivery.check_history_sidecar bu sidecar'ı fail-closed doğrular
    (eksik/geçersiz/uyuşmazlık → P1; dosya yok → atlanır).
"""
import hashlib
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402
import verify_delivery as vd  # noqa: E402


def _rec(ts="2026-01-01T00:00:00Z", **kw):
    rec = {"ts": ts, "verdict": "PASS", "p0": 0, "p1": 0}
    rec.update(kw)
    return rec


def _collector():
    findings = []

    def add(pri, cid, check, issue, evidence=""):
        findings.append({"priority": pri, "id": cid, "check": check,
                         "issue": issue, "evidence": evidence})
    return findings, add


class PreviewSidecarWriteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = pathlib.Path(self._tmp.name) / "history.jsonl"
        self._old_path = ps.HISTORY_PATH
        self._old_max = ps.HISTORY_MAX
        ps.HISTORY_PATH = str(self._path)
        ps.HISTORY_MAX = 100

    def tearDown(self):
        ps.HISTORY_PATH = self._old_path
        ps.HISTORY_MAX = self._old_max
        self._tmp.cleanup()

    def test_persist_writes_sha256_sidecar(self):
        ps.persist_history(_rec())
        sidecar = pathlib.Path(str(self._path) + ".sha256")
        self.assertTrue(sidecar.is_file())
        content = self._path.read_text(encoding="utf-8")
        want = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw = sidecar.read_text(encoding="utf-8").strip()
        self.assertEqual(raw.split()[0], want)
        self.assertIn("history.jsonl", raw)

    def test_sidecar_tracks_append(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        ps.persist_history(_rec("2026-01-01T00:01:00Z"))
        content = self._path.read_text(encoding="utf-8")
        want = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sidecar = pathlib.Path(str(self._path) + ".sha256")
        self.assertEqual(sidecar.read_text(encoding="utf-8").split()[0], want)


class CheckHistorySidecarTest(unittest.TestCase):
    def _write(self, root, rel, content):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_pass_when_sidecar_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            h = self._write(root, "history.jsonl", b'{"ts":"x"}\n')
            digest = hashlib.sha256(h.read_bytes()).hexdigest()
            self._write(root, "history.jsonl.sha256",
                        f"{digest}  history.jsonl\n".encode())
            findings, add = _collector()
            ok, detail = vd.check_history_sidecar(str(h), add)
            self.assertTrue(ok, detail)
            self.assertEqual(findings, [])

    def test_missing_history_is_skip(self):
        with tempfile.TemporaryDirectory() as td:
            findings, add = _collector()
            ok, _ = vd.check_history_sidecar(
                str(pathlib.Path(td) / "history.jsonl"), add)
            self.assertTrue(ok)
            self.assertEqual(findings, [])

    def test_missing_sidecar_is_p1(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            h = self._write(root, "history.jsonl", b'{"ts":"x"}\n')
            findings, add = _collector()
            ok, _ = vd.check_history_sidecar(str(h), add)
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K15-HISTORY" for f in findings))

    def test_mismatch_is_p1(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            h = self._write(root, "history.jsonl", b'{"ts":"x"}\n')
            self._write(root, "history.jsonl.sha256", b"0" * 64 + b"\n")
            findings, add = _collector()
            ok, _ = vd.check_history_sidecar(str(h), add)
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K15-HISTORY" for f in findings))

    def test_invalid_format_is_p1(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            h = self._write(root, "history.jsonl", b'{"ts":"x"}\n')
            self._write(root, "history.jsonl.sha256", b"not-a-hash\n")
            findings, add = _collector()
            ok, _ = vd.check_history_sidecar(str(h), add)
            self.assertFalse(ok)
            self.assertTrue(any(f["id"] == "K15-HISTORY" for f in findings))


if __name__ == "__main__":
    unittest.main()
