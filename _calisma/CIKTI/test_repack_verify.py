#!/usr/bin/env python3
"""test_repack_verify.py — repack_delivery.verify_sidecars birim testleri.

Kapsam:
  - PASS  : zip ile sidecar hash'i eşleşir (her iki zip)
  - FAIL  : sidecar hash'i zip'le uyuşmaz
  - EKSİK : zip yok / sidecar yok → FAIL
  - boş sidecar → FAIL
  - sidecar'daki name alanı hash'ten bağımsız (format "hash  name"; denetim
    hash'e bakar — repack'in write_sidecar çıktısıyla birebir)

stdlib `unittest` kullanır — ek bağımlılık yok. CI'da test_*.py discover
ile otomatik koşar (verify.yml "Run CIKTI unit tests" adımı).
"""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
PARENT = os.path.dirname(HERE)   # _calisma/ — repack_delivery.py burada
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import repack_delivery as rd


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class CheckLedgerEntryTests(unittest.TestCase):
    """repack determinizm kapısı (Faz 4): yeni kanonik hash defterde olmalı.

    Motor geçişi sidecar'ı bilinçli yeniler; referansı (kabul defteri satırı)
    olmayan kanonik hash yazılırsa strict K6-DETERM ilk koşuda P1 verir —
    yani repack kanıtsız teslim üretmiş olur. `check_ledger_entry` bu yüzden
    fail-closed durur. Defter `ID_RESIDUAL_LEDGER` env'i ile izole edilir;
    okunamayan defter de aynı şekilde fail-closed'dır.
    """

    TOKEN_IN = "a" * 64
    TOKEN_OUT = "b" * 64

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self._tmp.name, "ID_RESIDUAL_ACCEPTANCE.md")
        with open(self.ledger, "w", encoding="utf-8") as f:
            f.write(f"# defter\n{self.TOKEN_IN}  ingiliz_empirizmi_v3.pdf\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_true_when_canonical_recorded(self):
        with mock.patch.dict(os.environ,
                             {rd.id_canonical.LEDGER_ENV: self.ledger}):
            ok, detail = rd.check_ledger_entry(self.TOKEN_IN)
        self.assertTrue(ok)
        self.assertIn(self.TOKEN_IN[:16], detail)

    def test_false_when_canonical_absent_with_remedy(self):
        with mock.patch.dict(os.environ,
                             {rd.id_canonical.LEDGER_ENV: self.ledger}):
            ok, detail = rd.check_ledger_entry(self.TOKEN_OUT)
        self.assertFalse(ok)
        self.assertIn("defterinde yok", detail)
        self.assertIn("LEDGER=update", detail)  # uygulanabilir remedy
        self.assertIn(rd.id_canonical.LEDGER_DOC, detail)

    def test_fail_closed_when_ledger_unreadable(self):
        with mock.patch.object(rd.id_canonical, "ledger_candidates",
                               return_value=["/nonexistent/defter.md"]):
            ok, detail = rd.check_ledger_entry(self.TOKEN_IN)
        self.assertFalse(ok)
        self.assertIn("okunamadı", detail)


class VerifySidecarTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.inner = os.path.join(self.dir, rd.INNER_ZIP)
        self.outer = os.path.join(self.dir, rd.OUTER_ZIP)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_pair(self, zip_path, data, name):
        _write(zip_path, data)
        _write(zip_path + ".sha256",
               f"{_sha256(zip_path)}  {name}\n".encode())

    def test_pass_both_match(self):
        self._write_pair(self.inner, b"inner-data", rd.INNER_ZIP)
        self._write_pair(self.outer, b"outer-data", rd.OUTER_ZIP)
        self.assertTrue(rd.verify_sidecars(self.dir))

    def test_fail_hash_mismatch(self):
        self._write_pair(self.inner, b"inner-data", rd.INNER_ZIP)
        _write(self.outer, b"outer-data")
        _write(self.outer + ".sha256",
               ("0" * 64 + "  " + rd.OUTER_ZIP + "\n").encode())
        self.assertFalse(rd.verify_sidecars(self.dir))

    def test_missing_zip(self):
        self._write_pair(self.inner, b"inner-data", rd.INNER_ZIP)
        # outer zip yok ama sidecar'ı var → EKSİK zip
        _write(self.outer + ".sha256",
               ("0" * 64 + "  " + rd.OUTER_ZIP + "\n").encode())
        self.assertFalse(rd.verify_sidecars(self.dir))

    def test_missing_sidecar(self):
        self._write_pair(self.inner, b"inner-data", rd.INNER_ZIP)
        _write(self.outer, b"outer-data")
        self.assertFalse(rd.verify_sidecars(self.dir))

    def test_empty_sidecar(self):
        self._write_pair(self.inner, b"inner-data", rd.INNER_ZIP)
        _write(self.outer, b"outer-data")
        _write(self.outer + ".sha256", b"")
        self.assertFalse(rd.verify_sidecars(self.dir))

    def test_name_field_ignored(self):
        # hash doğru ama sidecar name farklı → PASS (denetim hash'e bakar)
        _write(self.inner, b"inner-data")
        _write(self.inner + ".sha256",
               f"{_sha256(self.inner)}  wrong_name.zip\n".encode())
        self._write_pair(self.outer, b"outer-data", rd.OUTER_ZIP)
        self.assertTrue(rd.verify_sidecars(self.dir))


if __name__ == "__main__":
    unittest.main()
