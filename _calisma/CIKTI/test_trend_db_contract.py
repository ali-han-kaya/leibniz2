"""Trend-DB sözleşme testleri — preview_server HISTORY_KEYS ↔ Prisma şema ↔ loader.

Sürükleme (drift) koruması: preview_server.HISTORY_KEYS'teki her anahtar
(1) apps/trend-db/prisma/schema.prisma'da kolon olarak (map hedefi veya düz ad),
(2) apps/trend-db/scripts/load.ts'te `row.<anahtar>` okuması olarak
mevcut olmalıdır. Statik denetim — ağ/DB/node gerektirmez.
"""
import os
import pathlib
import re
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
SERVER = HERE / "preview_server.py"
TREND_DB = REPO_ROOT / "apps" / "trend-db"

# Şemada @map'siz duran (map hedefi == alan adı) alanlar
PLAIN_FIELDS = {"id", "ts", "verdict", "p0", "p1", "findings"}


def history_keys():
    """preview_server.HISTORY_KEYS tuple'ını kaynak-düzeyinde ayrıştırır."""
    src = SERVER.read_text(encoding="utf-8")
    m = re.search(r"HISTORY_KEYS = \((.*?)\)", src, re.S)
    return set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))


def schema_columns():
    """schema.prisma'daki kolon adları: @map hedefleri + düz alan adları."""
    schema = (TREND_DB / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    cols = set(re.findall(r'@map\("([a-z_0-9]+)"\)', schema)) - {"trend_runs"}
    cols |= PLAIN_FIELDS
    return cols


# Şema/loader dosyaları REPO_ROOT'ta; preview_server ise bu dizinde.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


class TestHistoryCacheCoherence(unittest.TestCase):
    """load_history mtime+size önbelleği doğruluğu (perf turu, 2026-09-18).

    Sözleşme: (1) dosya değişmedikçe önbellek döner (aynı dict kimlikleri),
    (2) dosya değişince (append/yeniden-yazım) yeni satırlar görünür, (3)
    döndürülen liste kopyasıdır — çağrıcı mutasyonu önbelleği bozamaz, (4)
    önbellek-anahtarı yol+mtime_ns+boyuttur.
    """

    def setUp(self):
        import preview_server as ps
        self.ps = ps
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "history.jsonl")
        self._old = (getattr(ps, "HISTORY_PATH", None), ps._history_cache)
        ps.HISTORY_PATH = self.path
        ps._history_cache = (None, ())
        self.addCleanup(self._restore)

    def _restore(self):
        self.ps.HISTORY_PATH = self._old[0]
        self.ps._history_cache = self._old[1]

    def test_cache_returns_same_objects_until_file_changes(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"ts": "t1", "verdict": "PASS"}\n')
        r1 = self.ps.load_history()
        r2 = self.ps.load_history()
        self.assertIs(r1[0], r2[0])  # önbellek: aynı dict
        self.assertIsNot(r1, r2)     # liste kopyası

    def test_append_invalidates_cache(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"ts": "t1", "verdict": "PASS"}\n')
        first = self.ps.load_history()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('{"ts": "t2", "verdict": "FAIL"}\n')
        os.utime(self.path, ns=(time.time_ns() + 1_000_000, time.time_ns() + 1_000_000))
        second = self.ps.load_history()
        self.assertEqual(len(second), len(first) + 1)
        self.assertEqual(second[-1]["ts"], "t2")

    def test_rewrite_invalidates_cache(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"ts": "t1", "verdict": "PASS"}\n')
        self.ps.load_history()
        # persist_history deseni: tam yeniden-yazım (atomik replace)
        content = '{"ts": "t9", "verdict": "PASS"}\n'
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)
        os.utime(self.path, ns=(time.time_ns() + 2_000_000, time.time_ns() + 2_000_000))
        rows = self.ps.load_history()
        self.assertEqual([r["ts"] for r in rows], ["t9"])

    def test_caller_list_mutation_cannot_poison_cache(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"ts": "t1", "verdict": "PASS"}\n')
        r1 = self.ps.load_history()
        r1.append({"ts": "x", "verdict": "BAD"})
        r1[0]["verdict"] = "MUTATED"  # dict-paylaşımı: bilinçli sözleşme
        r2 = self.ps.load_history()
        self.assertEqual(len(r2), 1)  # liste-kopyası: append sızmadı
        self.assertEqual(r2[0]["verdict"], "MUTATED")  # dict-paylaşımı belgeli

    def test_missing_file_returns_empty_and_no_crash(self):
        self.assertEqual(self.ps.load_history(), [])


class TestTrendDbContract(unittest.TestCase):
    def test_schema_covers_history_keys(self):
        missing = history_keys() - schema_columns()
        self.assertEqual(missing, set(), f"şemada eksik kolonlar: {sorted(missing)}")

    def test_loader_maps_every_history_key(self):
        loader = (TREND_DB / "scripts" / "load.ts").read_text(encoding="utf-8")
        missing = [k for k in sorted(history_keys()) if f"row.{k}" not in loader]
        self.assertEqual(missing, [], f"loader'da okunmayan anahtarlar: {missing}")

    def test_generated_client_exposes_trendrun(self):
        model = TREND_DB / "generated" / "models" / "TrendRun.ts"
        if not model.exists():
            self.skipTest("Prisma client üretilmemiş (prisma generate koşulmalı)")
        body = model.read_text(encoding="utf-8")
        for field in ("refsBySource", "sourceRowSha256", "rawSha256"):
            self.assertIn(field, body, f"üretilen modelde alan yok: {field}")


if __name__ == "__main__":
    unittest.main()
