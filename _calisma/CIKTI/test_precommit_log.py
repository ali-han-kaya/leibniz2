#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_precommit_log.py — hook raporu seam sözleşmesi (precommit_log).

Bu test modülün ARAYÜZÜNÜ test eder (kaynak-metin taraması değil —
test_precommit_hooks_source.py'nin `assertIn`-kaynak testleri bu yüzden
emekliye ayrıldı). Sözleşme:

  1) Kayıt şekli: {name, id, status, source} — PRECOMMIT_RAPORU.schema.json
     ile kilitli (items.additionalProperties: false + required: source).
  2) Kaynak önceliği TEK yerde: stderr -> stdout -> sidecar. Öncelik
     PARSE bazlıdır (metin dolu olsa bile hooksuzsa sonraki kaynak denenir).
  3) Sidecar toleranstır: bozuk/eksik -> None -> panel placeholder korunur
     (katı doğrulama run_summary_precommit.py'nin ayrı sözleşmesi).

Kanıt (2026-10-02, modül docstring'inde taşınır): pre-commit çıktısının
52 hook satırının TAMAMI stdout'ta, stderr 0 bayt; iki çağrı sitesi farklı
kural okuyordu ve panel "⏳ hook verisi bekleniyor…"da takılmıştı.

OFFLINE, stdlib-only.
"""
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import precommit_log as pl  # noqa: E402

LOG_TWO = (
    "Verify Stoic-Hume V5 delivery (fail-closed)........................Passed\n"
    "- hook id: verify-delivery\n"
    "- duration: 0.36s\n"
    "Budget shield (aggregated)........................................Failed\n"
    "- hook id: budget\n"
    "- duration: 0.42s\n"
)


class TestParseHooks(unittest.TestCase):
    """Saf ayrıştırıcı: metin + kaynak -> kayıt."""

    def test_record_shape_is_locked(self):
        hooks = pl.parse_hooks(LOG_TWO, "log")
        self.assertEqual(hooks[0], {
            "name": "Verify Stoic-Hume V5 delivery (fail-closed)",
            "id": "verify-delivery",
            "status": "Passed",
            "source": "log",
        })
        self.assertEqual(hooks[1]["status"], "Failed")
        self.assertEqual(hooks[1]["id"], "budget")

    def test_parses_names_with_colons_and_parens(self):
        # Gerçek isimlerde iki nokta üst üste ve parantez var; gözdesi olmayan
        # bir desen burada sessizce boş dönerdi.
        name = "Sync config from package content (gen_config.py)"
        hooks = pl.parse_hooks(name + "....Passed\n", "stderr")
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["name"], name)
        self.assertIsNone(hooks[0]["id"])

    def test_empty_and_none_return_empty_list(self):
        self.assertEqual(pl.parse_hooks("", "stderr"), [])
        self.assertEqual(pl.parse_hooks(None, "stdout"), [])

    def test_sources_match_schema_enum(self):
        # Schema enum ile kümesi burada kilitli: enum değişirse bu kırmızı olur.
        self.assertEqual(
            set(pl.SOURCES), {"stderr", "stdout", "sidecar", "log"})


class TestCollectPriority(unittest.TestCase):
    """Toplayıcı: tek kaynak kuralı — stderr -> stdout -> sidecar."""

    def test_stderr_wins_over_stdout(self):
        hooks = pl.collect(stderr=LOG_TWO,
                           stdout="Lean proof................................Passed\n")
        self.assertIsNotNone(hooks)
        self.assertEqual(len(hooks), 2)
        self.assertEqual(hooks[0]["source"], "stderr")

    def test_stdout_fallback_when_stderr_has_no_hooks(self):
        # 2026-10-02 hata sınıfı: stderr metin dolu ama hooksuz — öncelik
        # metin doluluğuna değil PARSE sonucuna göre ilerlemeli.
        hooks = pl.collect(stderr="INFO: calisma basladi\n",
                           stdout=LOG_TWO)
        self.assertIsNotNone(hooks)
        self.assertEqual(hooks[0]["source"], "stdout")
        self.assertEqual(len(hooks), 2)

    def test_no_sources_returns_none(self):
        # None (panel placeholder'ının hâli): boşta hiçbir şey yoksa None.
        self.assertIsNone(pl.collect())
        self.assertIsNone(pl.collect(stderr="", stdout=""))

    def test_streams_win_over_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "PRECOMMIT_RAPORU.json")
            sidecar.write_text(json.dumps({"hooks": [
                {"name": "eski", "id": None, "status": "Passed",
                 "source": "log"}]}), encoding="utf-8")
            hooks = pl.collect(stderr="", stdout=LOG_TWO,
                               sidecar_paths=(str(sidecar),))
            self.assertEqual(hooks[0]["source"], "stdout")

    def test_sidecar_fallback_stamps_source_and_keeps_id(self):
        # Sidecar adayı: kayıt şekli KORUNUR (id dahil — eski finalize yolu
        # id'yi düşürüyordu) ve source bu okumayı anlatır: "sidecar".
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "PRECOMMIT_RAPORU.json")
            sidecar.write_text(json.dumps({"hooks": [
                {"name": "eski-run", "id": "old-id", "status": "Passed",
                 "source": "log"}]}), encoding="utf-8")
            hooks = pl.collect(stderr=None, stdout="",
                               sidecar_paths=(str(sidecar),))
            self.assertIsNotNone(hooks)
            self.assertEqual(hooks[0]["source"], "sidecar")
            self.assertEqual(hooks[0]["id"], "old-id")

    def test_corrupt_sidecar_is_tolerated(self):
        # Toleranslı okuma: bozuk sidecar -> None (panel düşmez, katı
        # doğrulama run_summary'nin işi).
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "PRECOMMIT_RAPORU.json")
            sidecar.write_text("{bozuk json", encoding="utf-8")
            self.assertIsNone(pl.collect(stderr="", stdout="",
                                         sidecar_paths=(str(sidecar),)))

    def test_sidecar_only_checked_when_opted_in(self):
        # Sidecar yolu yalnız çağıran ister: arka plan yolu taze çıktı
        # üretir, eski sidecar'dan veri göstermez.
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "PRECOMMIT_RAPORU.json")
            sidecar.write_text(json.dumps({"hooks": [
                {"name": "eski", "id": None, "status": "Passed",
                 "source": "log"}]}), encoding="utf-8")
            self.assertIsNone(pl.collect(stderr="", stdout=""))


class TestUpdateConfigAndFindings(unittest.TestCase):
    """Rapor üreticisinin kullandığı diğer iki saf ayrıştırıcı."""

    LOG_UC_FAIL = (
        "Sync config from package content (gen_config.py).................Failed\n"
        "- hook id: update-config\n"
        "- duration: 0.15s\n"
        "expected_pages 33 != 34\n"
        "[P0] teslim kilidi kirildi\n"
    )

    def test_update_config_fail_becomes_p1(self):
        uc_status, uc_output = pl.parse_update_config(self.LOG_UC_FAIL)
        self.assertEqual(uc_status, "Failed")
        self.assertIn("expected_pages 33 != 34", uc_output)
        findings = pl.parse_findings(self.LOG_UC_FAIL, uc_status, uc_output)
        self.assertIn(("P0", "teslim kilidi kirildi"), findings)
        p1 = [f for f in findings if f[0] == "P1"]
        self.assertEqual(len(p1), 1)
        self.assertIn("update-config FAIL", p1[0][1])

    def test_empty_log_yields_nothing(self):
        self.assertEqual(pl.parse_findings("", None, []), [])
        self.assertEqual(pl.parse_update_config(""), (None, []))


class TestPanelContract(unittest.TestCase):
    """Panelin takildigi metin: duzeltilmemis hali bu yaziyi gosteriyordu."""

    def test_stuck_placeholder_text_survives(self):
        js = (HERE / "preview.js").read_text(encoding="utf-8")
        self.assertIn("hook verisi bekleniyor", js)


if __name__ == "__main__":
    unittest.main()
