#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_preview_mirror_stale.py — bayatlık probe'unun sözleşme kapısı.

İki katman:

  1. PROBE SEMANTİĞİ — sahte sync/verify scriptleriyle probe'un DÖRT adımı
     ölçmesi: temiz=0, bayat=1 + dosya adı, K17=1 + P1 + stale_files,
     geri=0. Negatif senaryolar (fail-open kapı, K17 zinciri düşmüyor,
     P1 üretilmiyor, stale_files eksik) probe'u KIRMIZI yapmalı — probe
     yalnızca yeşil senaryoda PASS diyorsa kapı değil, süs olurdu.
     Ayrıca İZOLASYON: gerçek PREVIEW_MIRROR'a dokunulmaz.

  2. CI KABLOLAMASI — `.github/workflows/verify.yml` `mirror-check` job'ında
     adım var mı, fail-closed mı (continue-on-error YOK, exit "$rc"), KAPSAM
     adımından SONRA ve rapor adımından ÖNCE mi, sidecar artifact'a giriyor
     mu, run summary'de exit görünüyor mu. Adım sessizce silinemez.

Sahte scriptler `bash <script>` / `<sys.executable> <script>` ile koşar —
gerçek araçlar gibi; probe kendi alt-süreçlerini temp env ile çağırır.

stdlib only — OFFLINE.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERIFY_YML = ROOT / ".github" / "workflows" / "verify.yml"
sys.path.insert(0, str(HERE))

import check_preview_mirror_stale as pm  # noqa: E402

PROBE_STEP = "Preview mirror stale probe (fail-closed)"
SIDECAR = "mirror_stale_probe.json"


FAKE_SYNC = """#!/usr/bin/env bash
set -u
SRC="{src}"
MODE="{mode}"
case "${{1:-sync}}" in
  --force|sync)
    mkdir -p "$PREVIEW_MIRROR" "$MIRROR_DIR" "$LEAN_MIRROR_DIR"
    cp "$SRC" "$PREVIEW_MIRROR/preview.js"
    exit 0 ;;
  --check)
    if [ "$MODE" = "always0" ]; then
      echo "GÜNCEL: preview/preview.js"; exit 0
    fi
    if cmp -s "$SRC" "$PREVIEW_MIRROR/preview.js"; then
      echo "GÜNCEL: preview/preview.js"; exit 0
    fi
    if [ "$MODE" = "wrongname" ]; then
      echo "BAYAT/EKSİK: preview/other.js"; exit 1
    fi
    echo "BAYAT/EKSİK: preview/preview.js"; exit 1 ;;
  *)
    echo "bilinmeyen mod: $1" >&2; exit 2 ;;
esac
"""

FAKE_VERIFY = """#!/usr/bin/env python3
import json
import subprocess
import sys

SYNC = {sync!r}
MODE = {mode!r}
args = sys.argv[1:]
out_path = args[args.index("--mirror-out") + 1] if "--mirror-out" in args else None
r = subprocess.run(["bash", SYNC, "--check"], capture_output=True, text=True)
stale = [ln.split("BAYAT/EKSİK:", 1)[1].strip()
         for ln in r.stdout.splitlines() if "BAYAT/EKSİK:" in ln]
if MODE == "always0":
    rc = 0
else:
    rc = r.returncode
if MODE == "no_p1":
    print("K17 başarısız ama P1 bulgusu yok")
elif MODE == "nostale":
    print("[P1] K17 mirror sync")
    stale = []
elif rc:
    print("[P1] K17 mirror sync")
else:
    print("[K17] mirror sync: PASS")
if out_path:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({{"ok": rc == 0, "exit": rc, "stale_files": stale}}, f)
sys.exit(rc)
"""


class ProbeCase(unittest.TestCase):
    """Sahte sync + verify ile probe'u uçtan uca koşturur."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="probe-test-")
        self.td = pathlib.Path(self._td.name)
        self.src = self.td / "repo_preview.js"
        self.src.write_text("console.log('v1');\n", encoding="utf-8")
        self.out = self.td / "probe.json"

    def tearDown(self):
        self._td.cleanup()

    def _fakes(self, sync_mode="ok", verify_mode="ok"):
        sync = self.td / "fake_sync.sh"
        sync.write_text(FAKE_SYNC.format(src=self.src, mode=sync_mode),
                        encoding="utf-8")
        vd = self.td / "fake_verify.py"
        vd.write_text(FAKE_VERIFY.format(sync=str(sync), mode=verify_mode),
                      encoding="utf-8")
        return sync, vd

    def _probe(self, sync, vd):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = pm.main(["--sync-script", str(sync), "--verify-delivery",
                          str(vd), "--json-out", str(self.out), "--quiet"])
        report = json.loads(self.out.read_text(encoding="utf-8"))
        return rc, report, buf.getvalue()

    def test_pass_proves_clean_stale_k17_and_restore(self):
        sync, vd = self._fakes()
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 0, out)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["clean_exit"], 0)
        self.assertEqual(report["stale_exit"], 1)
        self.assertTrue(report["stale_named"])
        self.assertEqual(report["k17_exit"], 1)
        self.assertEqual(report["k17_stale_files"], ["preview/preview.js"])
        self.assertEqual(report["restored_exit"], 0)
        self.assertIn("FAIL-CLOSED", out)
        # Kaynak dosya bozulmaz (yalnızca mirror kopyası bayatlatıldı).
        self.assertEqual(self.src.read_text(encoding="utf-8"),
                         "console.log('v1');\n")

    def test_real_mirror_is_not_touched(self):
        """Probe gerçek PREVIEW_MIRROR'ı okumaz/yazmaz — kendi temp'i."""
        sentinel = self.td / "real_mirror"
        sentinel.mkdir()
        (sentinel / "preview.js").write_text("CANLI\n", encoding="utf-8")
        sync, vd = self._fakes()
        old = os.environ.get("PREVIEW_MIRROR")
        os.environ["PREVIEW_MIRROR"] = str(sentinel)
        try:
            rc, _report, out = self._probe(sync, vd)
        finally:
            if old is None:
                os.environ.pop("PREVIEW_MIRROR", None)
            else:
                os.environ["PREVIEW_MIRROR"] = old
        self.assertEqual(rc, 0, out)
        self.assertEqual((sentinel / "preview.js").read_text(encoding="utf-8"),
                         "CANLI\n")

    def test_fail_open_checker_is_caught(self):
        """--check her zaman 0 diyorsa probe PASS diyemez (asıl regresyon)."""
        sync, vd = self._fakes(sync_mode="always0")
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 1, out)
        self.assertFalse(report["ok"])
        self.assertEqual(report["stale_exit"], 0)
        self.assertIn("1 beklenirdi", report["reason"])

    def test_wrong_filename_in_report_is_caught(self):
        sync, vd = self._fakes(sync_mode="wrongname")
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 1, out)
        self.assertFalse(report["stale_named"])
        self.assertIn("raporlanmadı", report["reason"])

    def test_k17_chain_must_fail_on_stale(self):
        """--check BAYAT derken K17 exit 0 dönerse zincir kopuk demektir."""
        sync, vd = self._fakes(verify_mode="always0")
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 1, out)
        self.assertEqual(report["k17_exit"], 0)
        self.assertIn("zincir düşmüyor", report["reason"])

    def test_k17_must_emit_p1(self):
        sync, vd = self._fakes(verify_mode="no_p1")
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 1, out)
        self.assertIn("P1", report["reason"])

    def test_k17_sidecar_must_name_the_preview_file(self):
        sync, vd = self._fakes(verify_mode="nostale")
        rc, report, out = self._probe(sync, vd)
        self.assertEqual(rc, 1, out)
        self.assertEqual(report["k17_stale_files"], [])
        self.assertIn("stale_files", report["reason"])

    def test_missing_sync_script_exits_2(self):
        _sync, vd = self._fakes()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = pm.main(["--sync-script", str(self.td / "yok.sh"),
                          "--verify-delivery", str(vd), "--json",
                          "--json-out", str(self.out)])
        self.assertEqual(rc, 2, buf.getvalue())
        report = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertFalse(report["ok"])
        self.assertIn("sync_verify_mirror.sh yok", report["reason"])


def _job_section(text, job):
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"^  %s:\s*$" % re.escape(job), ln)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def _steps(section):
    """(name, block) listesi — 6 boşluklu `- name:` blokları."""
    out, cur_name, cur = [], None, []
    for line in section.splitlines():
        m = re.match(r"^\s{6}- name:\s*(.+?)\s*$", line)
        if m:
            if cur_name is not None:
                out.append((cur_name, "\n".join(cur)))
            cur_name, cur = m.group(1), [line]
        elif cur_name is not None:
            cur.append(line)
    if cur_name is not None:
        out.append((cur_name, "\n".join(cur)))
    return out


class WorkflowWiring(unittest.TestCase):
    """CI kapısı kablolaması — adım sessizce silinemez/zayıflatılamaz."""

    @classmethod
    def setUpClass(cls):
        cls.text = VERIFY_YML.read_text(encoding="utf-8")
        cls.job = _job_section(cls.text, "mirror-check")
        cls.step = next((blk for nm, blk in _steps(cls.job)
                         if nm == PROBE_STEP), "")

    def test_probe_script_exists(self):
        self.assertTrue((HERE / "check_preview_mirror_stale.py").is_file())

    def test_step_runs_the_probe_and_is_fail_closed(self):
        self.assertTrue(self.step, "mirror-check job'ında probe adımı yok")
        self.assertIn("python3 _calisma/CIKTI/check_preview_mirror_stale.py",
                      self.step)
        self.assertIn('exit "$rc"', self.step)
        self.assertNotIn("continue-on-error", self.step,
                         "probe advisory'e düşürülmüş — bayat mirror merge'ü "
                         "bloke etmez")
        self.assertIn("id: stale", self.step)

    def test_step_order_after_coverage_before_summary(self):
        self.assertLess(self.job.index("Mirror coverage (--check-coverage, "
                                       "fail-closed)"),
                        self.job.index(PROBE_STEP))
        self.assertLess(self.job.index(PROBE_STEP),
                        self.job.index("Write mirror check to run summary"))

    def test_summary_and_artifact_carry_the_probe(self):
        self.assertIn("steps.stale.outputs.rc", self.job)
        upload = next((blk for nm, blk in _steps(self.job)
                       if nm.startswith("Upload mirror check report")), "")
        self.assertIn(SIDECAR, upload)

    def test_probe_sidecar_is_written_by_the_step(self):
        self.assertIn("--json-out " + SIDECAR, self.step)


if __name__ == "__main__":
    unittest.main()
