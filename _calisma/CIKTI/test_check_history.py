#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_history.py — K15 (history.jsonl ↔ .sha256 sidecar) regresyon kapısı.

verify_delivery.check_history_sidecar'ı fail-closed doğrular:
ekşik/geçersiz/uyuşmazlık → P1; dosya yok → atlanır.

persist sidecar testleri (persist_writes_sha256, sidecar_tracks_append)
test_preview_server.py PersistHistoryTests'e taşındı.
"""
import argparse
import hashlib
import os
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


class TestFullFlags(unittest.TestCase):
    """--full, --check-history=True (boolean, auto-discover) ayarlar."""

    def _make_args(self, **kw):
        "apply_full_flags'in ihtiyaç duyduğu alanları olan bir namespace."
        ns = argparse.Namespace(
            full=False, check_history=None,
            check_references=False, symbolic_proof=False, lean_proof=False,
            check_lineage=False, check_repro_manifest=False,
            check_config_drift=False, check_cleanup=False,
            check_github_scripts=False, check_mirror=False,
            mirror_auto_sync=False, check_daemon=False,
            check_plist=False, coq_proof=False, check_launchd=False,
        )
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_apply_full_flags_sets_check_history(self):
        args = self._make_args(full=True)
        args = vd.apply_full_flags(args)
        self.assertTrue(args.check_history, "--full K15'i aktifleştirmeli")

    def test_apply_full_flags_does_not_overwrite_explicit_path(self):
        args = self._make_args(full=True, check_history="/explicit/path/h.jsonl")
        args = vd.apply_full_flags(args)
        self.assertEqual(args.check_history, "/explicit/path/h.jsonl",
                         "açık PATH --full ile ezilmemeli")

    def test_auto_discover_cwd_history_jsonl(self):
        """auto-discover: cwd'de history.jsonl varsa bulmalı."""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            h = root / "history.jsonl"
            h.write_text('{"ts":"test"}\n')
            digest = hashlib.sha256(h.read_bytes()).hexdigest()
            (root / "history.jsonl.sha256").write_text(
                f"{digest}  history.jsonl\n")
            # Test path resolution logic (candidates inline — main() içiyle aynı)
            candidates = [str(root / "history.jsonl")]
            hpath = None
            for c in candidates:
                if os.path.isfile(c):
                    hpath = c
                    break
            self.assertIsNotNone(hpath)
            findings, add = _collector()
            ok, detail = vd.check_history_sidecar(hpath, add)
            self.assertTrue(ok, detail)

    def test_auto_discover_all_missing_skips(self):
        """auto-discover: dosya hiçbir yerde yoksa döngü boş kalır."""
        with tempfile.TemporaryDirectory() as td:
            nonexistent = os.path.join(td, "nonexistent.jsonl")
            self.assertFalse(os.path.isfile(nonexistent))
            # Sidecar: dosya yok → findings boş, ok=True (skip)
            findings, add = _collector()
            ok, _ = vd.check_history_sidecar(nonexistent, add)
            self.assertTrue(ok)
            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
