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
import types
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


class TestK0SkipDirs(unittest.TestCase):
    def test_canonical_basename_always_skipped(self):
        # Repo: --dir .../_calisma/CIKTI → "CIKTI" atlanır.
        self.assertIn("CIKTI", vd.k0_skip_dirs("/x/_calisma/CIKTI"))
        # TCC-safe mirror: --dir .../verify → "verify" atlanır (K0 false-P1
        # önlenir — mirror kendi zip'lerini bayat sanmaz).
        self.assertIn("verify",
                      vd.k0_skip_dirs("/Users/x/Library/Caches/com.freebuff/verify"))
        # Yine de CIKTI/TOOLKIT/.venv_z3 sabit istisnaları korunur.
        self.assertTrue({"CIKTI", "TOOLKIT", ".venv_z3"}
                        .issubset(vd.k0_skip_dirs("/x/_calisma/CIKTI")))

    def test_toolkit_tolerant_drops_toolkit(self):
        self.assertIn("TOOLKIT", vd.k0_skip_dirs("/x/_calisma/CIKTI"))
        self.assertNotIn("TOOLKIT",
                         vd.k0_skip_dirs("/x/_calisma/CIKTI", True))
        # kanonik basename tolerant modda da korunur
        self.assertIn("CIKTI", vd.k0_skip_dirs("/x/_calisma/CIKTI", True))

    def test_mirror_dir_not_flagged_by_scan(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            canonical = parent / "verify"  # TCC-safe mirror senaryosu
            _touch(canonical / "TESLIM_KLASOR_V5_2026-08-17.zip")
            _touch(canonical / "TESLIM_V5_FINAL_2026-08-17.zip")
            # parent altında başka gerçek bayat kopya da olsun
            _touch(parent / "stale_root.zip")
            rels = sorted(
                f["rel"].replace("\\", "/")
                for f in vd.scan_stale_zips(parent, skip_dirs=vd.k0_skip_dirs(canonical))
            )
        # mirror'ın kendi zip'leri atlanır; yalnızca gerçek bayat kopya kalır
        self.assertEqual(rels, ["stale_root.zip"])


class TestToolkitTolerant(unittest.TestCase):
    def test_is_toolkit_rel(self):
        self.assertTrue(vd.is_toolkit_rel("TOOLKIT/x.zip"))
        self.assertTrue(vd.is_toolkit_rel("TOOLKIT/sub/y.zip"))
        self.assertFalse(vd.is_toolkit_rel("TOOLKIT2/x.zip"))
        self.assertFalse(vd.is_toolkit_rel("TESLIM/x.zip"))
        self.assertFalse(vd.is_toolkit_rel("x.zip"))

    def test_tolerant_skip_set_scans_toolkit(self):
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d)
            _touch(parent / "TOOLKIT" / "toolkit.zip")
            _touch(parent / "TESLIM" / "stale.zip")
            _touch(parent / "CIKTI" / "canonical.zip")
            # varsayılan skip → TOOLKIT atlanır
            default_rels = _rels(parent)
            # --k0-toolkit-tolerant skip kümesi → TOOLKIT taranır
            tolerant_rels = sorted(
                f["rel"].replace("\\", "/")
                for f in vd.scan_stale_zips(
                    parent, skip_dirs={"CIKTI", ".venv_z3"})
            )
        self.assertEqual(default_rels, ["TESLIM/stale.zip"])
        self.assertEqual(tolerant_rels,
                         ["TESLIM/stale.zip", "TOOLKIT/toolkit.zip"])

    def test_build_layers_summary_info_not_fail(self):
        args = types.SimpleNamespace(
            symbolic_proof=False, lean_proof=False, verify_manifest=None,
            check_config_drift=False, check_plist=False,
            check_repro_manifest=False, check_cleanup=False,
            check_history=None, check_github_scripts=False,
            check_mirror=False)
        findings = [{"id": "K0-TOOLKIT", "priority": "INFO",
                     "check": "K0-TOOLKIT", "issue": "toolkit", "evidence": ""}]
        layers = vd.build_layers_summary(args, findings)
        self.assertEqual(layers["K0"]["status"], "PASS")
        self.assertEqual(layers["K0"]["findings"], [])


if __name__ == "__main__":
    unittest.main()
