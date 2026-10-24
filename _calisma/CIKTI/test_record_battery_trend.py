#!/usr/bin/env python3
"""test_record_battery_trend.py — battery-trend kayıt sözleşmesi (TDD).

determinism-trend deseni: `record_battery_trend.py` CI'ın kanonik unittest
komutunu (verify.yml `Run CIKTI unit tests` ile AYNI komut) zamanlar ve
ölçümü `docs/battery_trend/battery_trend.jsonl`'a ekler; `--check` haftalık
tazelik + yapısal geçerlilik kapısıdır (fail-closed).

Süit:
  1) --update: yeşil batarya eklenir (alanlar pinli); KIRMIZI batarya
     yazılmaz (rc=1); "Ran N tests" kanıtı yoksa ya da süre <= 0 ise
     fail-closed (rc=1, ekleme yok).
  2) --check: gençlik (<7 gün), yapısal (0 < süre <= 7200s, tests >= 1,
     son satırın scope'u kanonik) — ihlal = rc=1; bozuk/boş JSONL = rc=1.
     Medyan-sapma ve test-sayısı notları BİLGİLENDİRİCİDİR (rc=0 kalır).
  3) Workflow pinleri (battery-trend.yml): schedule + workflow_dispatch,
     top-level permissions, concurrency.group, timeout-minutes, --update ve
     --check `run:` adımları, trend dosyasının stage edilmesi, GATE_SCRIPTS
     üyeliği + `run:` ile çağrım (gated-schedules K1/K4 çapraz pini) ve
     keşif komutunun verify.yml ile TEK-KAYNAK eşitliği.
"""

import datetime
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import record_battery_trend as rbt  # noqa: E402
import test_gated_schedules as tgs  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "battery-trend.yml"
RECORDER = ROOT / "_calisma" / "CIKTI" / "record_battery_trend.py"
VERIFY = ROOT / ".github" / "workflows" / "verify.yml"

OK_OUTPUT = "Ran 42 tests in 1.234s\n\nOK\n"
GREEN = lambda: (0, 12.5, OK_OUTPUT)  # noqa: E731


def _record(date=None, duration=10.0, tests=42, scope=None, gate="PASS"):
    return {
        "date": date or datetime.date.today().isoformat(),
        "duration_s": duration,
        "tests": tests,
        "platform": "linux",
        "python": "3.11.9",
        "gate": gate,
        "scope": scope or rbt.SCOPE,
    }


class _RedirectMixin:
    """TREND dosyasını geçici dizine yönlendir; RUNNER'ı sakla/geri al."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="battery_trend_")
        self._trend = rbt.TREND
        rbt.TREND = os.path.join(self.tmp, "battery_trend.jsonl")
        self._runner = rbt.RUNNER

    def tearDown(self):
        rbt.TREND = self._trend
        rbt.RUNNER = self._runner

    def _read(self):
        with open(rbt.TREND, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]


class TestUpdate(_RedirectMixin, unittest.TestCase):
    def test_green_battery_appends_record(self):
        rbt.RUNNER = GREEN
        rc = rbt.main(["--update"])
        self.assertEqual(rc, 0)
        recs = self._read()
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["date"], datetime.date.today().isoformat())
        self.assertEqual(r["duration_s"], 12.5)
        self.assertEqual(r["tests"], 42)
        self.assertEqual(r["gate"], "PASS")
        self.assertEqual(r["scope"], rbt.SCOPE)
        self.assertIn(r["platform"], ("darwin", "linux"))
        self.assertRegex(r["python"], r"^\d+\.\d+")

    def test_red_battery_not_recorded(self):
        rbt.RUNNER = lambda: (1, 99.0, "FAILED (failures=3)")
        rc = rbt.main(["--update"])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(rbt.TREND),
                         "kırmızı batarya trende yazılmamalı")

    def test_missing_ran_line_fails_closed(self):
        rbt.RUNNER = lambda: (0, 5.0, "sessiz çıktı — Ran satırı yok")
        rc = rbt.main(["--update"])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(rbt.TREND))

    def test_zero_duration_fails_closed(self):
        rbt.RUNNER = lambda: (0, 0.0, OK_OUTPUT)
        rc = rbt.main(["--update"])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(rbt.TREND))


class TestCheck(_RedirectMixin, unittest.TestCase):
    def _write(self, records):
        os.makedirs(os.path.dirname(rbt.TREND), exist_ok=True)
        with open(rbt.TREND, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_fresh_records_ok(self):
        self._write([_record()])
        rc = rbt.main(["--check"])
        self.assertEqual(rc, 0)

    def test_missing_file_fails_closed(self):
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_empty_file_fails_closed(self):
        self._write([])
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_stale_latest_fails(self):
        old = (datetime.date.today()
               - datetime.timedelta(days=8)).isoformat()
        self._write([_record(date=old)])
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_zero_duration_record_fails(self):
        self._write([_record(duration=0.0)])
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_absurd_duration_record_fails(self):
        self._write([_record(duration=9000.0)])
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_scope_drift_on_latest_fails(self):
        self._write([_record(scope="farkli-kapsam")])
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_corrupt_jsonl_fails(self):
        os.makedirs(os.path.dirname(rbt.TREND), exist_ok=True)
        with open(rbt.TREND, "w", encoding="utf-8") as f:
            f.write("{bozuk json\n")
        self.assertEqual(rbt.main(["--check"]), 1)

    def test_median_spike_is_informational_not_fail(self):
        """2× medyan üstü süre notu basar ama rc=0 kalır (bilgilendirici)."""
        base = [_record(date=(datetime.date.today()
                              - datetime.timedelta(days=d)).isoformat(),
                        duration=10.0)
                for d in (6, 5, 4, 3, 2)]
        base.append(_record(duration=60.0))
        self._write(base)
        rc = rbt.main(["--check"])
        self.assertEqual(rc, 0, "medyan sapması FAIL olmamalı")


class TestWorkflowContract(unittest.TestCase):
    """battery-trend.yml desen pinleri (determinism-trend emsalі)."""

    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_and_dispatch(self):
        self.assertTrue(
            re.search(r'^\s+-\s+cron:\s*"', self.text, re.M),
            "schedule cron satırı yok")
        self.assertIn("workflow_dispatch", self.text)

    def test_ci_hygiene_k1_k2_k3(self):
        head = self.text.split("jobs:", 1)[0]
        self.assertIn("permissions:", head, "K1: top-level permissions")
        self.assertIn("concurrency:", head, "K3: top-level concurrency")
        self.assertIn("group:", head)
        self.assertRegex(self.text, r"timeout-minutes:\s*\d+",
                         "K2: job timeout-minutes")

    def test_runs_update_and_check_via_run_steps(self):
        bodies = tgs.run_bodies(self.text)
        joined = "\n".join(bodies)
        self.assertIn("record_battery_trend.py --update", joined)
        self.assertIn("record_battery_trend.py --check", joined)

    def test_stages_versioned_trend_file(self):
        self.assertIn(
            "git add docs/battery_trend/battery_trend.jsonl", self.text,
            "trend jsonl versiyonlu dosya — bot-dalı commit'i stage etmeli")

    def test_gate_registry_membership_and_run_invocation(self):
        """Gated-schedules çapraz pini: kayıt ÜYELİĞİ + run: ile çağrım."""
        self.assertIn("record_battery_trend.py", tgs.GATE_SCRIPTS)
        bodies = tgs.run_bodies(self.text)
        self.assertTrue(
            any("record_battery_trend.py" in b for b in bodies),
            "GATE_SCRIPTS üyesi bir `run:` adımında çağrılmalı (K4)")

    def test_recorder_scope_matches_ci_single_source(self):
        """Zamanlanan komut, verify.yml'in CI komutuyla tek kaynaktır."""
        rec = RECORDER.read_text(encoding="utf-8")
        self.assertIn('"discover"', rec)
        self.assertIn('"test_*.py"', rec)
        self.assertIn('os.path.join("_calisma", "CIKTI")', rec)
        verify = VERIFY.read_text(encoding="utf-8")
        self.assertRegex(
            verify, r"unittest discover -s _calisma/CIKTI -p [\"']test_\*\.py",
            "verify.yml kanonik keşif komutu değişti — SCOPE'u güncelle")


if __name__ == "__main__":
    unittest.main()
