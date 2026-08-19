#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_doc_wrapper_sync.py — check_doc_wrapper_sync.py regresyon kapısı.

check() saf bir fonksiyondur: iki metni alır, eksik çapaları döner.
Bu test dosyası gerçek doc/wrapper'a bağımlı DEĞİLDİR (sentetik çapalarla
check() mantığını doğrular) + gerçek dosyaların senkron olduğunu da kapı
olarak denetler. stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_doc_wrapper_sync as sync  # noqa: E402

DOC = "line a\n--public line\ngh run watch line\n"
WRAP = "wrapper --public here\nwatch via gh run watch\n"

ANCHORS = [
    ("bayrak", ["--public"]),
    ("ci izleme", ["gh run watch"]),
]


class TestCheck(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(sync.check(DOC, WRAP, ANCHORS), [])

    def test_missing_in_doc(self):
        missing = sync.check("", WRAP, ANCHORS)
        # Her iki parça da doc'ta eksik; wrapper'da mevcut.
        self.assertEqual(
            missing,
            [("bayrak", "--public", ("doc",)),
             ("ci izleme", "gh run watch", ("doc",))],
        )

    def test_missing_in_wrapper(self):
        missing = sync.check(DOC, "", ANCHORS)
        self.assertEqual(
            missing,
            [("bayrak", "--public", ("wrapper",)),
             ("ci izleme", "gh run watch", ("wrapper",))],
        )

    def test_missing_in_both(self):
        missing = sync.check("", "", ANCHORS)
        self.assertEqual(
            missing,
            [("bayrak", "--public", ("doc", "wrapper")),
             ("ci izleme", "gh run watch", ("doc", "wrapper"))],
        )

    def test_order_deterministic(self):
        # Konum tuple'ı her zaman doc→wrapper sırasında döner.
        a = sync.check("", "", ANCHORS)
        b = sync.check("", "", ANCHORS)
        self.assertEqual(a, b)
        self.assertEqual(a[0][2], ("doc", "wrapper"))


class TestRealFilesSynced(unittest.TestCase):
    """Gerçek doc ↔ wrapper çiftinin şu an senkron olduğunu kapılar."""

    def test_real_files_in_sync(self):
        doc = sync.DOC.read_text(encoding="utf-8")
        wrap = sync.WRAPPER.read_text(encoding="utf-8")
        missing = sync.check(doc, wrap)
        self.assertEqual(missing, [], f"drift: {missing}")


if __name__ == "__main__":
    unittest.main()
