#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_history.py — K15 (history.jsonl ↔ .sha256 sidecar) regresyon kapısı.

verify_delivery.check_history_sidecar'ı fail-closed doğrular:
ekşik/geçersiz/uyuşmazlık → P1; dosya yok → atlanır.

persist sidecar testleri (persist_writes_sha256, sidecar_tracks_append)
test_preview_server.py PersistHistoryTests'e taşındı.
"""
import hashlib
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


def _collector():
    findings = []

    def add(pri, cid, check, issue, evidence=""):
        findings.append({"priority": pri, "id": cid, "check": check,
                         "issue": issue, "evidence": evidence})
    return findings, add


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
