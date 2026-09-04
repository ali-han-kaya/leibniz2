#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_one atomiklik sözleşmesi: mirror yazımları tmp + mv (rename) ile
olmalı — eşzamanlı okuyucu (preview sunucusu, K17 kontrolleri) asla yarım
(torn) dosya görmemeli. Aksi halde cp O_TRUNC ile hedefi sıfırlar ve okuyan
taraf bozuk JSON/zip/hash okur.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SYNC = HERE / "sync_verify_mirror.sh"


def _function_source(name: str) -> str:
    """Betikten <name>() { … } gövdesini BÜTÜN-AĞAÇ çıkarır (kopya yok).
    Betik kaynaklanmaz — son satırındaki `main "$@"` gerçek mirror'a
    dokunur; test yalnızca fonksiyonu izole ortamda koşturur."""
    text = SYNC.read_text(encoding="utf-8")
    m = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), text, re.S | re.M)
    if m is None:
        raise AssertionError(f"{name}() betikte bulunamadı")
    return m.group(0)


def _run_sync_one(src: pathlib.Path, dst: pathlib.Path, mode: str = "force"):
    """sync_one'u gerçek fonksiyon gövdesiyle (same_file + sync_one) izole
    bash'te, betiğin kendi set -euo pipefail ortamında koşturur."""
    script = (
        "set -euo pipefail\n"
        + _function_source("same_file") + "\n"
        + _function_source("sync_one") + "\n"
        'sync_one "$SRC" "$DST" "$MODE"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
        env={**os.environ,
             "SRC": str(src), "DST": str(dst), "MODE": mode},
        timeout=60,
    )


class SyncOneAtomicTests(unittest.TestCase):
    """sync_one: atomik yazım sözleşmesi (tmp + mv)."""

    @classmethod
    def setUpClass(cls):
        cls.sync_text = SYNC.read_text(encoding="utf-8")
        m = re.search(r"^sync_one\(\) \{(.*?)^\}", cls.sync_text,
                      re.S | re.M)
        cls.assertIsNotNone(cls, m, "sync_one() gövdesi bulunamadı")
        cls.body = m.group(1)

    def test_no_in_place_cp_to_destination(self):
        """Hedefe doğrudan cp YOK — her yazım tmp üstüne olur (torn-read
        penceresi kapanır)."""
        self.assertNotRegex(
            self.body, r'cp\s+"\$src"\s+"\$dst"',
            "sync_one hedefe in-place cp yapıyor — atomik değil")

    def test_atomic_tmp_then_mv_present(self):
        """mktemp (hedefle AYNI dizinde — rename garantisi) + mv deseni var;
        cp başarısızsa tmp temizlenir."""
        self.assertIn("mktemp", self.body, "mktemp ile tmp üretimi yok")
        self.assertIn("mv", self.body, "tmp→hedef mv yok")
        # tmp, hedef dizininde üretilmeli (cross-device mv rename'i bozar)
        self.assertRegex(
            self.body, r'mktemp\s+"\$\{dst\}\.tmp',
            "tmp hedefle aynı dizinde değil (mv rename garantisi kaybolur)")
        self.assertRegex(
            self.body, r"rm\s+-f\s+\"\$tmp\"",
            "cp başarısızında tmp temizliği yok (artık dosya bırakır)")

    def test_force_mode_replaces_content(self):
        """force: hedefin İÇERİĞİ atomik değişir, davranış korunur."""
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "a.json"
            dst = pathlib.Path(td) / "sub" / "a.json"
            dst.parent.mkdir()
            src.write_text('{"v": 1}')
            dst.write_text('{"v": 0}')
            r = _run_sync_one(src, dst, "force")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("GÜNCELLENDİ", r.stdout)
            self.assertEqual(dst.read_text(), '{"v": 1}')
            # tmp artığı kalmaz
            leftovers = [p.name for p in dst.parent.iterdir()
                         if p.name != "a.json"]
            self.assertEqual(leftovers, [], f"tmp artığı: {leftovers}")

    def test_sync_mode_unchanged_reports_guncel(self):
        """sync: içerik aynıysa GÜNCEL — hedefe yazma yapılmaz."""
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "a.json"
            dst = pathlib.Path(td) / "a.json"
            src.write_text('{"v": 1}')
            dst.write_text('{"v": 1}')
            r = _run_sync_one(src, dst, "sync")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("GÜNCEL", r.stdout)
            self.assertNotIn("GÜNCELLENDİ", r.stdout)
            self.assertEqual(dst.read_text(), '{"v": 1}')

    def test_failure_leaves_destination_intact(self):
        """Kaynak yoksa yazım başarısız olur ama mevcut hedef BOZULMAZ
        (atomiklik yarı yolda kalınan dosyayı hedefe taşımaz)."""
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "yok.json"
            dst = pathlib.Path(td) / "a.json"
            dst.write_text('{"v": 1}')
            r = _run_sync_one(src, dst, "force")
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(dst.read_text(), '{"v": 1}',
                             "başarısız sync hedefi bozdu")


class SyncScriptStructureTests(unittest.TestCase):
    """BETİK-YAPISI sözleşmesi (146943b kazası sonrası): sync_one'ın kopya
    yolu fonksiyonun İÇİNDE olmalı ve atomik blok başka fonksiyona
    sızdırılmamalı. 146943b'de parçalı yama sync_one'ın kopya yolunu sildi
    ve bloğu run_check'e serpti; local mirror dolu olduğundan testler
    geçti, fresh-runner'da mirror boş kaldı (fail-closed yakaladı).
    Yapı testleri bunu kaynak seviyesinde yakalar.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = SYNC.read_text(encoding="utf-8")

    def _body(self, name):
        m = re.search(r"^%s\(\) \{(.*?)^\}" % re.escape(name),
                      self.text, re.S | re.M)
        self.assertIsNotNone(m, f"{name}() bulunamadı")
        return m.group(1)

    def test_sync_one_body_contains_copy_path(self):
        """sync_one gövdesi kısa devreden SONRA kopya yolunu içermeli:
        mktemp + cp + mv + GÜNCELLENDİ. (146943b: gövde yalnızca
        short-circuit içeriyordu — fresh-runner'da hiçbir dosya
        kopyalanmıyordu.)"""
        body = self._body("sync_one")
        for token in ("mktemp", 'cp "$src" "$tmp"', 'mv -f "$tmp" "$dst"',
                      "GÜNCELLENDİ"):
            self.assertIn(token, body,
                          f"sync_one gövdesinde {token!r} yok — kopya yolu "
                          f"silinmiş olmalı (fresh-runner kırığı)")

    def test_atomic_block_not_spliced_into_other_functions(self):
        """Atomik yazım bloğu başka fonksiyonlara sızmış olmamalı
        (146943b: blok run_check'in başına yapışmıştı; run_check local
        bildirimlerinden ÖNCE mktemp çalıştırıyordu → 'dst: unbound
        variable' — --check tamamen kırık)."""
        rc = self._body("run_check")
        self.assertNotIn("mktemp", rc,
                         "run_check atomik yazım bloğu içeriyor — sızma")
        self.assertNotIn("GÜNCELLENDİ", rc)
        # run_check local bildirimleriyle BAŞLAMALI (ilk statement).
        first_stmt = rc.strip().splitlines()[0].strip()
        self.assertTrue(first_stmt.startswith("local "),
                        f"run_check ilk statement 'local' değil: {first_stmt!r}")


if __name__ == "__main__":
    unittest.main()
