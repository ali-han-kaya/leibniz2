#!/usr/bin/env python3
import inspect
import json
import os
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_delivery as vd


class SidecarGuaranteeTests(unittest.TestCase):
    def test_lineage_writer_keeps_schema_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "lineage.json")
            ok, _ = vd.write_lineage_sidecar(path, None)
            self.assertTrue(ok)
            with open(path, encoding="utf-8") as stream:
                report = json.load(stream)
            self.assertFalse(report["ok"])
            self.assertEqual(report["generations"], [])


class AtomicVerifySidecarTests(unittest.TestCase):
    def test_atomic_writer_replaces_without_tmp_leftovers(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "klayers.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("old")
            vd._write_atomic(path, "new")
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "new")
            self.assertEqual(os.listdir(td), ["klayers.json"])

    def test_atomic_writer_failure_preserves_klayers_json(self):
        """klayers.json hedefi de JSONL history satırlarıyla aynı yazım
        yolundan geçer: başarısız yazım hedefi truncate ETMEZ ve dizinde
        tmp artığı bırakmaz.
        """
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "klayers.json")
            payload = '{"verdict": "PASS", "layers": {"K1": {"status": "PASS"}}}'
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(payload)
            with self.assertRaises(TypeError):
                vd._write_atomic(path, object())
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), payload)
            self.assertEqual(os.listdir(td), ["klayers.json"])

    def test_klayers_written_through_same_tmp_replace_path_as_history(self):
        """Açık kontrat satırı: klayers.json ve history.jsonl AYNI yardımcıdan
        (`_write_atomic`) geçer; yardımcı aynı dizinde `mkstemp` + `os.replace`
        uygular. klayers replace, history append semantiği taşır — ikisi de
        hedefi yerinde truncate etmez.
        """
        writer = inspect.getsource(vd._write_atomic)
        self.assertIn("tempfile.mkstemp(", writer)
        self.assertIn("os.replace(tmp, path)", writer)
        main_source = inspect.getsource(vd.main)
        self.assertIn("_write_atomic(args.klayers_out, klayers_payload)",
                      main_source)
        self.assertIn("_write_atomic(args.history_out, history_payload, append=True)",
                      main_source)
        # Aynı-dizin şartı davranışsal olarak pinlenir: tmp hedefle AYNI dizinde
        # açılmazsa os.replace atomik olmaz (farklı dosya sistemine düşebilir).
        # Kaynak metnine bağlı kalmadan, çağrının kendisi doğrulanır.
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "klayers.json")
            real_mkstemp = tempfile.mkstemp
            seen = {}

            def spy(*args, **kwargs):
                seen.update(kwargs)
                return real_mkstemp(*args, **kwargs)

            with mock.patch("tempfile.mkstemp", spy):
                vd._write_atomic(dest, "{}")
            self.assertEqual(seen.get("dir"),
                             os.path.dirname(os.path.abspath(dest)))
            self.assertTrue(seen.get("prefix", "").startswith("klayers.json"))

    def test_atomic_writer_append_preserves_history_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "history.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"run": 1}\n')
            vd._write_atomic(path, '{"run": 2}\n', append=True)
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), '{"run": 1}\n{"run": 2}\n')
            self.assertEqual(os.listdir(td), ["history.jsonl"])

    def test_atomic_writer_failure_preserves_destination(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "history.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("old\n")
            with self.assertRaises(TypeError):
                vd._write_atomic(path, object())
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "old\n")
            self.assertEqual(os.listdir(td), ["history.jsonl"])

    def test_main_routes_run_sidecars_through_atomic_writer(self):
        source = inspect.getsource(vd.main)
        self.assertIn("_write_atomic(args.klayers_out", source)
        self.assertIn("_write_atomic(args.history_out", source)


if __name__ == "__main__":
    unittest.main()
