#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_history_layers.py sözleşmesi.

Kilit iddia: arşiv satırı, kapı dökümünü YALNIZ kendi run kaydından alır;
kayıt yoksa/rapor yoksa satır dokunulmadan kalır, var olan `layers` ezilmez
ve yazım sonrası `history.jsonl.sha256` sidecar'ı K15'in beklediği biçimde
dosyayla eşleşir.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(HERE, "backfill_history_layers.py")
sys.path.insert(0, HERE)

import backfill_history_layers as bh  # noqa: E402


def _verify_blob(layers, verdict="FAIL", p0=1, p1=0):
    """verify_delivery.py --json çıktısının küçük bir örneği."""
    return json.dumps({"verdict": verdict, "counts": {"P0": p0, "P1": p1},
                       "layers": layers})


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.history = os.path.join(self._tmp.name, "history.jsonl")
        self.runs = os.path.join(self._tmp.name, "runs")
        os.makedirs(self.runs)

    # ---- yardımcılar ----------------------------------------------------
    def _row(self, ts, **extra):
        row = {"ts": ts, "verdict": "FAIL", "exit_code": 1}
        row.update(extra)
        return row

    def _write_history(self, rows):
        with open(self.history, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write((row if isinstance(row, str)
                          else json.dumps(row, ensure_ascii=False)) + "\n")

    def _write_record(self, ts, *, layers=None, stdout=None, exit_code=1):
        record = {"ts": ts, "exit_code": exit_code, "stdout": stdout or "",
                  "stderr": ""}
        if layers is not None:
            record["layers"] = layers
        name = "run-%s.json" % ts.replace(":", "").replace(".", "").replace("+", "")
        with open(os.path.join(self.runs, name), "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        return record

    def _rows(self):
        with open(self.history, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]

    @staticmethod
    def _read_bytes(path):
        with open(path, "rb") as fh:
            return fh.read()

    def _run_cli(self, *args):
        proc = subprocess.run([sys.executable, SCRIPT,
                               "--history", self.history,
                               "--runs-dir", self.runs] + list(args),
                              capture_output=True, text=True)
        return proc

    # ---- doldurma -------------------------------------------------------
    def test_fills_from_same_run_stdout(self):
        ts = "2026-10-06T03:22:47.220516+00:00"
        self._write_history([self._row(ts, status_board="K0 🔴 · K katmanları 🔴")])
        self._write_record(ts, stdout=_verify_blob({
            "K0": {"status": "FAIL", "label": "Bayat zip"},
            "K5": {"status": "PASS", "ran": True},
            "K8": {"status": "SKIP", "ran": False},
        }))

        rows, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["filled"], 1)
        self.assertEqual(report["filled_rows"][0]["failed"], ["K0"])
        self.assertEqual(rows[0]["row"]["layers"]["K0"]["status"], "FAIL")
        self.assertTrue(rows[0]["row"]["layers"]["K5"]["ran"])
        # dry-run dosyayı DEĞİŞTİRMEZ
        self.assertNotIn("layers", self._rows()[0])

    def test_unknown_statuses_are_dropped_not_promoted(self):
        """Durum doğrulaması preview_server ile AYNI olmalı (tek kaynak).

        Anahtar kümesi filtrelenmez: sunucu `UNREGISTERED` gibi sözleşmeli
        sözde-katmanları ve K16-K21'i de yazar; backfill onun yazacağı
        haritayı geri koyar. Tanınmayan DURUM ise düşer — uydurma PASS yok.
        """
        ts = "2026-10-06T02:54:11.276598+00:00"
        self._write_history([self._row(ts)])
        self._write_record(ts, stdout=_verify_blob({
            "K0": {"status": "???"},
            "K1": {"status": "pass"},
            "K16": {"status": "PASS"},
        }))
        rows, report = bh.plan(self.history, self.runs)
        layers = rows[0]["row"]["layers"]
        self.assertEqual(sorted(layers), ["K1", "K16"],
                         "geçersiz durum düşmeli, geçerli katman korunmalı")
        self.assertEqual(layers["K1"]["status"], "PASS")
        self.assertEqual(report["filled"], 1)

    def test_all_invalid_layers_leaves_row_untouched(self):
        ts = "2026-10-04T19:51:48.762614+00:00"
        self._write_history([self._row(ts)])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "UNKNOWN"}}))
        rows, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["filled"], 0)
        self.assertEqual(report["missing_report"], 1)
        self.assertNotIn("layers", rows[0]["row"])

    def test_record_layers_field_takes_precedence_over_stdout(self):
        ts = "2026-10-04T18:50:11.908262+00:00"
        self._write_history([self._row(ts)])
        self._write_record(ts, layers={"K2": {"status": "FAIL"}},
                           stdout=_verify_blob({"K3": {"status": "PASS"}}))
        rows, _ = bh.plan(self.history, self.runs)
        self.assertEqual(sorted(rows[0]["row"]["layers"]), ["K2"])

    # ---- koruma / çakışma ----------------------------------------------
    def test_existing_layers_are_never_overwritten(self):
        ts = "2026-10-04T17:08:07.588565+00:00"
        self._write_history([self._row(ts, layers={"K0": {"status": "PASS"}})])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "FAIL"}}))
        rows, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["conflict"], 1)
        self.assertEqual(report["filled"], 0)
        self.assertEqual(rows[0]["action"], "conflict")
        self.assertEqual(rows[0]["row"]["layers"]["K0"]["status"], "PASS")

    def test_identical_existing_layers_are_already(self):
        ts = "2026-10-04T15:04:00.719714+00:00"
        layers = {"K0": {"status": "PASS"}}
        self._write_history([self._row(ts, layers=layers)])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "PASS"}}))
        _, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["already"], 1)
        self.assertEqual(report["conflict"], 0)

    def test_missing_record_is_counted_not_filled(self):
        self._write_history([self._row("2026-09-29T15:42:12.317124+00:00")])
        rows, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["missing_record"], 1)
        self.assertEqual(report["filled"], 0)
        self.assertEqual(rows[0]["action"], "missing_record")

    def test_other_timestamp_record_is_not_used(self):
        self._write_history([self._row("2026-10-05T00:00:00+00:00")])
        self._write_record("2026-10-06T00:00:00+00:00",
                           stdout=_verify_blob({"K0": {"status": "FAIL"}}))
        _, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["filled"], 0)
        self.assertEqual(report["missing_record"], 1)

    # ---- yazım ----------------------------------------------------------
    def test_apply_writes_sidecar_and_is_idempotent(self):
        ts = "2026-10-06T03:22:47.220516+00:00"
        self._write_history([self._row(ts), self._row("2026-09-29T15:42:12.317124+00:00")])
        self._write_record(ts, stdout=_verify_blob({
            "K0": {"status": "FAIL"}, "K16": {"status": "PASS"}}))

        first = self._run_cli("--apply", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads(first.stdout)  # stdout TEK doküman
        self.assertTrue(report["applied"])
        self.assertEqual(report["filled"], 1)

        content = self._read_bytes(self.history)
        digest = hashlib.sha256(content).hexdigest()
        with open(self.history + ".sha256", encoding="utf-8") as fh:
            sidecar = fh.read().split()
        self.assertEqual(sidecar[0], digest)
        self.assertEqual(sidecar[1], "history.jsonl")

        rows = self._rows()
        self.assertEqual(rows[0]["layers"]["K0"]["status"], "FAIL")
        self.assertNotIn("layers", rows[1], "kaydı olmayan satır değişmemeli")

        second = self._run_cli("--apply", "--json")
        self.assertEqual(second.returncode, 0, second.stderr)
        report2 = json.loads(second.stdout)
        self.assertEqual(report2["filled"], 0)
        self.assertEqual(report2["already"], 1)
        self.assertFalse(report2["applied"])
        self.assertEqual(hashlib.sha256(self._read_bytes(self.history)).hexdigest(),
                         digest, "ikinci koşum baytları değiştirmemeli")

    def test_render_preserves_untouched_line_bytes(self):
        ts = "2026-10-06T03:22:47.220516+00:00"
        raw = '{"ts": "%s",  "verdict":"FAIL", "exit_code": 1}' % ts
        self._write_history([raw])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "FAIL"}}))
        rows, _ = bh.plan(self.history, self.runs)
        self.assertEqual(rows[0]["raw"], raw)
        rendered = bh.render(rows)
        self.assertTrue(rendered.startswith('{"ts": "%s", "verdict": "FAIL"' % ts))

    def test_json_mode_without_apply_is_read_only(self):
        ts = "2026-10-06T03:22:47.220516+00:00"
        self._write_history([self._row(ts)])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "FAIL"}}))
        before = self._read_bytes(self.history)
        proc = self._run_cli("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["filled"], 1)
        self.assertEqual(self._read_bytes(self.history), before)
        self.assertFalse(os.path.exists(self.history + ".sha256"))

    def test_apply_refuses_when_archive_changed_after_plan(self):
        """Plan anındaki anlık görüntü bayatsa yazMAZ (lost update guard).

        Sunucu arada yeni bir koşu satırı yazarsa körlemesine replace o satırı
        silerdi; araç fail-closed durur ve diskteki yeni satır korunur.
        """
        ts = "2026-10-06T03:22:47.220516+00:00"
        self._write_history([self._row(ts)])
        self._write_record(ts, stdout=_verify_blob({"K0": {"status": "FAIL"}}))
        rows, report = bh.plan(self.history, self.runs)
        self.assertEqual(report["filled"], 1)

        # Araya giren yeni koşu (sunucunun persist_history yazımı)
        with open(self.history, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(self._row("2026-10-07T00:00:00+00:00")) + "\n")
        with self.assertRaises(SystemExit) as ctx:
            bh.apply(self.history, rows, report)
        self.assertIn("değişti", str(ctx.exception))
        self.assertEqual(len(self._rows()), 2, "yeni satır korunmalı")
        self.assertFalse(os.path.exists(self.history + ".sha256"))

    def test_missing_archive_exits_nonzero(self):
        proc = self._run_cli("--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("error", json.loads(proc.stdout))


class RealArchiveShapeTests(unittest.TestCase):
    """Gerçek arşiv varsa: plan hiçbir koşulda satır SILMEZ/çakışma üretmez
    hesabı tutarsız kalmaz (doldurma + zaten dolu + eksik = satır sayısı)."""

    def test_counts_partition_rows(self):
        history = os.path.join(REPO, "_calisma", "CIKTI", "history.jsonl")
        runs = os.path.join(REPO, "_calisma", "CIKTI", "runs")
        if not os.path.isfile(history):
            self.skipTest("canlı history.jsonl yok")
        _, report = bh.plan(history, runs)
        self.assertEqual(
            report["rows"],
            report["filled"] + report["already"] + report["missing_record"]
            + report["missing_report"] + report["conflict"]
            + report["invalid_json"],
        )


if __name__ == "__main__":
    unittest.main()
