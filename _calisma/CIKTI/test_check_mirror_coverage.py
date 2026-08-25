#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_mirror_coverage.py — mirror kapsam denetiminin birim testleri.

--list çıktısı mock'lanır (gerçek sync_verify_mirror.sh çalıştırılmaz), repo
dosya kümesi fake root altında kurulur. Sözleşme:
  0 = KAPSAM TAM (beklenen her runtime dosyası listede, bayat girdi yok)
  1 = KAPSAM EKSİK (mirror eksikliği / bayat girdi / beklenmeyen girdi)
  2 = hata (sync script yok / --list çalışmadı)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_mirror_coverage as cmc


def fake_repo(root):
    """Fake repo: beklenen kümeyi (runtime + zip + lean + guide) kurar."""
    cikti = os.path.join(root, "_calisma", "CIKTI")
    lean = os.path.join(root, "_calisma", "lean_reduct")
    os.makedirs(os.path.join(cikti, "github_scripts"), exist_ok=True)
    os.makedirs(os.path.join(lean, "Leibniz2Reduct"), exist_ok=True)
    for n in cmc.RUNTIME_REQUIRED + cmc.PREVIEW_RUNTIME:
        with open(os.path.join(cikti, n), "w", encoding="utf-8") as f:
            f.write("x\n")
    for n in ("a.js", "b.js"):
        with open(os.path.join(cikti, "github_scripts", n), "w",
                  encoding="utf-8") as f:
            f.write("x\n")
    for n in ("TESLIM_A.zip", "TESLIM_A.zip.sha256"):
        with open(os.path.join(cikti, n), "w", encoding="utf-8") as f:
            f.write("x\n")
    guide = os.path.join(root, "docs", "branch-protection-guide")
    os.makedirs(guide, exist_ok=True)
    with open(os.path.join(guide, "guide.html"), "w", encoding="utf-8") as f:
        f.write("x\n")
    for n in ("ReductInvariance.lean", "lean-toolchain", "lakefile.toml",
              "Leibniz2Reduct/Content.lean"):
        with open(os.path.join(lean, n), "w", encoding="utf-8") as f:
            f.write("x\n")
    return cikti, lean


def list_output(cikti, lean, root, *drop):
    """--list çıktısı: beklenen kümeyi `kaynak -> hedef` olarak basar.

    `drop`: çıkarılacak repo-göreli yollar (EKSİK senaryosu).
    `extra`: eklenecek repo-göreli yollar (bayat/beklenmeyen senaryosu).
    """
    lines = []
    exp = cmc.expected_repo_files(root, cikti, lean)
    for rel in sorted(exp):
        if rel in drop:
            continue
        src = os.path.join(root, rel)
        lines.append("%s -> %s" % (src, os.path.join(root, "mirror")))
    return "\n".join(lines) + "\n"


def run_main(root, fake_out, script_exists=True):
    script = os.path.join(root, "sync_verify_mirror.sh")
    if script_exists:
        with open(script, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\n")
        os.chmod(script, 0o755)
    fake = mock.Mock()
    fake.returncode = 0
    fake.stdout = fake_out
    fake.stderr = ""
    with mock.patch.object(cmc.subprocess, "run", return_value=fake):
        return cmc.main(["--sync-script", script, "--root", root])


class TestCoverageOk(unittest.TestCase):
    def test_scope_complete_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            rc = run_main(root, list_output(cikti, lean, root))
            self.assertEqual(rc, 0)
            exp = cmc.expected_repo_files(root, cikti, lean)
            # Fake repo'nun beklenen kümesi gerçek repo gibi dolu olmalı
            # (runtime + zips + lean + guide + github_scripts).
            self.assertGreater(len(exp), 20)
            self.assertIn("_calisma/CIKTI/verify_delivery.py", exp)
            self.assertIn("_calisma/lean_reduct/ReductInvariance.lean", exp)


class TestCoverageFailClosed(unittest.TestCase):
    def test_missing_runtime_file_exit_1(self):
        # Mirror eksikliği: beklenen dosya --list'te YOK → exit 1.
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            missing = "_calisma/CIKTI/verify_delivery.config.schema.json"
            rc = run_main(root, list_output(cikti, lean, root, missing))
            self.assertEqual(rc, 1)
            self.assertEqual(missing in cmc.expected_repo_files(root, cikti, lean),
                             True)

    def test_missing_lean_source_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            missing = "_calisma/lean_reduct/Leibniz2Reduct/Content.lean"
            rc = run_main(root, list_output(cikti, lean, root, missing))
            self.assertEqual(rc, 1)

    def test_missing_zip_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            missing = "_calisma/CIKTI/TESLIM_A.zip"
            rc = run_main(root, list_output(cikti, lean, root, missing))
            self.assertEqual(rc, 1)

    def test_dead_entry_exit_1(self):
        # Bayat girdi: listede repo'da OLMAYAN bir kaynak var → exit 1.
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            out = list_output(cikti, lean, root) + \
                  "%s -> %s\n" % (os.path.join(root, "_calisma", "CIKTI",
                                               "ghost.py"),
                                  os.path.join(root, "mirror"))
            rc = run_main(root, out)
            self.assertEqual(rc, 1)

    def test_unexpected_entry_exit_1(self):
        # Beklenmeyen girdi: listede var ama kapsam tanımında yok → exit 1.
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            p = os.path.join(root, "_calisma", "CIKTI", "surprise.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write("x\n")
            out = list_output(cikti, lean, root) + \
                  "%s -> %s\n" % (p, os.path.join(root, "mirror"))
            rc = run_main(root, out)
            self.assertEqual(rc, 1)

    def test_script_missing_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            rc = cmc.main(["--sync-script",
                           os.path.join(root, "nope.sh"), "--root", root])
            self.assertEqual(rc, 2)

    def test_json_output_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="cov-") as root:
            cikti, lean = fake_repo(root)
            script = os.path.join(root, "sync_verify_mirror.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
            fake = mock.Mock()
            fake.returncode = 0
            fake.stdout = list_output(cikti, lean, root)
            fake.stderr = ""
            with mock.patch.object(cmc.subprocess, "run", return_value=fake), \
                 mock.patch("sys.stdout") as m_out:
                rc = cmc.main(["--sync-script", script, "--root", root,
                               "--json"])
            self.assertEqual(rc, 0)
            written = "".join(c.args[0] for c in m_out.write.call_args_list)
            d = json.loads(written)
            self.assertTrue(d["ok"])


if __name__ == "__main__":
    unittest.main()
