#!/usr/bin/env python3
"""test_scan_stale_zips.py — K0 recursive bayat-zip taraması regresyon kapısı.

verify_delivery.scan_stale_zips, parent altındaki HER .zip'i (alt dizinler
dahil) bulur; CIKTI/TOOLKIT/.venv_z3 istisnalarını ve nokta ile başlayan
gizli dizinleri atlar. Bu test şu senaryoları kapsar:
  - CIKTI + TOOLKIT istisnaları (kanonik + toolkit kopyası yakalanmaz)
  - alt dizin yakalama (repack ara ürünü senaryosu: TESLIM/ V5_ICERIK/)
  - gizli dizin atlama (.venv_z3 + .hidden + .git)
  - kök-düzey başıboş kopya yakalama
  - büyük/küçük harf uzantı (.ZIP) + zip-olmayan dosya yoksayma
  - custom skip_dirs override + yok/boş parent
"""
import pathlib
import re
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


def _touch(path, content=b"zip"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _rels(parent):
    return sorted(f["rel"].replace("\\", "/")
                  for f in vd.scan_stale_zips(parent))


class TestScanStaleZips(unittest.TestCase):
    def test_exceptions_subdir_hidden_root(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            # istisnalar — yakalanmamalı
            _touch(parent / "CIKTI" / "canonical.zip")
            _touch(parent / "TOOLKIT" / "toolkit_copy.zip")
            # gizli dizinler — atlanmalı (.venv_z3 dahil)
            _touch(parent / ".venv_z3" / "env.zip")
            _touch(parent / ".hidden" / "hidden.zip")
            _touch(parent / ".git" / "objects.zip")
            # alt dizin — yakalanmalı (repack ara ürünü)
            _touch(parent / "TESLIM" / "stale.zip")
            _touch(parent / "V5_ICERIK" / "stale2.zip")
            # kök — yakalanmalı
            _touch(parent / "root_stale.zip")
            # zip olmayan — yoksayılmalı
            _touch(parent / "notes.txt")
            _touch(parent / "TESLIM" / "README.md")
            rels = _rels(parent)
        self.assertEqual(rels, [
            "TESLIM/stale.zip",
            "V5_ICERIK/stale2.zip",
            "root_stale.zip",
        ])

    def test_case_insensitive_extension(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            _touch(parent / "UPPER.ZIP")
            _touch(parent / "lower.zip")
            rels = _rels(parent)
        self.assertEqual(rels, ["UPPER.ZIP", "lower.zip"])

    def test_sha256_is_full_hash(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            p = parent / "x.zip"
            _touch(p, b"stale-content")
            (finding,) = vd.scan_stale_zips(parent)
            expected = vd.sha256_file(p)
        self.assertEqual(finding["rel"], "x.zip")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", finding["sha256"]))
        self.assertEqual(finding["sha256"], expected)

    def test_custom_skip_dirs_override(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            _touch(parent / "CUSTOM" / "a.zip")
            _touch(parent / "CIKTI" / "b.zip")
            # override: yalnızca CUSTOM atlanır; CIKTI artık yakalanır
            rels = sorted(
                f["rel"].replace("\\", "/")
                for f in vd.scan_stale_zips(parent, skip_dirs={"CUSTOM"})
            )
        self.assertEqual(rels, ["CIKTI/b.zip"])

    def test_missing_parent_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            missing = pathlib.Path(d) / "nope"
            self.assertEqual(vd.scan_stale_zips(missing), [])


if __name__ == "__main__":
    unittest.main()
