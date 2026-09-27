"""Trend-DB sözleşme testleri — preview_server HISTORY_KEYS ↔ Prisma şema ↔ loader.

Sürükleme (drift) koruması: preview_server.HISTORY_KEYS'teki her anahtar
(1) apps/trend-db/prisma/schema.prisma'da kolon olarak (map hedefi veya düz ad),
(2) apps/trend-db/scripts/load.ts'te `row.<anahtar>` okuması olarak
mevcut olmalıdır. Statik denetim — ağ/DB/node gerektirmez.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
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


class TestTrendDbDryRun(unittest.TestCase):
    """`--dry-run` sözleşmesi: DB'ye dokunmadan sayaç + kaynak SHA-256 raporu.

    Ön-uçuş, gerçek koşuyla AYNI eşleme yolundan (`prepare`) geçtiği için
    rapor ile yükleme ayrışamaz. Test bunu gerçek `tsx` koşusuyla kanıtlar;
    node/tsx yoksa atlanır (test_github_scripts/test_pptx_export deseni).
    Kimlik bilgisi verilmez: DATABASE_URL temizlenir ve cwd geçici dizindir
    (dotenv `.env` bulamaz) — dry-run'ın bağlantısız koştuğunun kanıtı.
    """

    NODE = shutil.which("node")
    TSX = TREND_DB / "node_modules" / ".bin" / "tsx"
    LOADER = TREND_DB / "scripts" / "load.ts"

    def setUp(self):
        if self.NODE is None or not self.TSX.exists():
            self.skipTest("node/tsx yok (apps/trend-db/node_modules kurulmalı)")
        self.tmp = tempfile.TemporaryDirectory(prefix="trend-dry-")
        self.addCleanup(self.tmp.cleanup)

    def _run(self, *args):
        """Loader'ı kimlik bilgisi OLMADAN koşar (cwd: geçici dizin)."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_URL", "DATABASE_URL_UNPOOLED")}
        return subprocess.run(
            [self.NODE, str(self.TSX), str(self.LOADER), *args],
            cwd=self.tmp.name, env=env, capture_output=True, text=True,
            timeout=120)

    def _fixture(self, name="history.jsonl"):
        """5 dolu satır: 2 aday, 1 dosya-içi ts tekrarı, 2 doğrulama-dışı."""
        lines = [
            '{"ts": "2026-09-27T10:00:00.000000+00:00", "verdict": "PASS",'
            ' "p0": 0, "p1": 0}',
            '{"ts": "2026-09-27T10:05:00.000000+00:00", "verdict": "FAIL",'
            ' "p0": 1, "p1": 2}',
            '{"ts": "2026-09-27T10:05:00.000000+00:00", "verdict": "PASS",'
            ' "p0": 0, "p1": 0}',
            '{"verdict": "PASS"}',   # ts yok → doğrulama-dışı
            "null",                    # JSON nesnesi değil → doğrulama-dışı
        ]
        path = pathlib.Path(self.tmp.name) / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_dry_run_reports_sha256_and_insert_skip_counts(self):
        fixture = self._fixture()
        raw = fixture.read_bytes()
        res = self._run(str(fixture), "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(
            "[DRY-RUN] sha256: %s" % hashlib.sha256(raw).hexdigest(),
            res.stdout, "kaynak SHA-256 raporlanmadı")
        self.assertIn("(%d bayt)" % len(raw), res.stdout)
        self.assertIn("satır: 5 dolu / 6 fiziksel (boş atlanan: 1)", res.stdout)
        self.assertIn("aday: 2 · doğrulama-dışı atlanan: 2", res.stdout)
        self.assertIn("dosya-içi çakışma: 1", res.stdout)
        self.assertIn("eklenecek (en çok): 2", res.stdout)
        self.assertIn("atlanacak (en az): 3", res.stdout)
        self.assertNotIn("bitti:", res.stdout, "dry-run yükleme yapmamalı")

    def test_dry_run_needs_no_database_url(self):
        fixture = self._fixture()
        res = self._run(str(fixture), "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("DB bağlantısı kurulmadı", res.stdout)
        self.assertNotIn("DATABASE_URL yok", res.stdout + res.stderr)

    def test_real_run_still_requires_database_url(self):
        fixture = self._fixture()
        res = self._run(str(fixture))
        self.assertEqual(res.returncode, 1)
        self.assertIn("DATABASE_URL yok", res.stderr)

    def test_unknown_flag_exits_2(self):
        res = self._run("--dri-run")
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("bilinmeyen bayrak: --dri-run", res.stderr)

    def test_malformed_json_exits_1_with_line_number(self):
        path = pathlib.Path(self.tmp.name) / "bad.jsonl"
        path.write_text('{"ts": "2026-09-27T10:00:00Z", "verdict": "PASS"}\n'
                        "{bozuk\n", encoding="utf-8")
        res = self._run(str(path), "--dry-run")
        self.assertEqual(res.returncode, 1)
        self.assertIn("satır 2: JSON ayrıştırılamadı", res.stderr)

    def test_json_flag_emits_single_line_machine_summary(self):
        """`--json`: prose'in yerine TEK satır JSON — betikler için sözleşme.

        JS tarafı (apps/trend-db/test/dry-run.test.mjs) aynı seam'i kendi
        koşucusuyla kilitler; buradaki kopya kasıtlı: repo kökünde tek kapı
        (check_unit_tests) Python testlerini koşar, JS koşucusu yalnız
        `npm test` ile çalışır — iki yüz birden kaybolmasın.
        """
        fixture = self._fixture()
        raw = fixture.read_bytes()
        res = self._run(str(fixture), "--dry-run", "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.strip().split("\n")
        self.assertEqual(len(lines), 1, "tek satır JSON beklenir: %r" % res.stdout)
        self.assertNotIn("[DRY-RUN]", res.stdout, "--json prose basmamalı")
        j = json.loads(lines[0])
        self.assertEqual(j["mode"], "dry-run")
        self.assertEqual(j["source"], str(fixture))
        self.assertEqual(j["sourceSha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(j["bytes"], len(raw))
        self.assertEqual(
            (j["linesFull"], j["linesPhysical"], j["blankSkipped"]),
            (5, 6, 1), "satır sayaçları prose ile aynı olmalı")
        self.assertEqual(
            (j["candidates"], j["invalidSkipped"], j["duplicatesInFile"]),
            (2, 2, 1), "aday/doğrulama-dışı/çakışma prose ile aynı olmalı")
        self.assertEqual((j["insertAtMost"], j["skipAtLeast"]), (2, 3))
        self.assertIs(j["dbConnected"], False, "dry-run DB'ye bağlanmamalı")

    def test_json_numbers_match_prose_numbers(self):
        """İki yüzey AYNI sayıları söyler — çapraz-kapı (drift yok)."""
        fixture = self._fixture()
        prose = self._run(str(fixture), "--dry-run").stdout
        j = json.loads(
            self._run(str(fixture), "--dry-run", "--json").stdout.strip())
        m = re.search(r"eklenecek \(en çok\): (\d+) · atlanacak \(en az\): (\d+)", prose)
        self.assertIsNotNone(m, "prose sayaç etiketi kayboldu: %r" % prose)
        self.assertEqual(j["insertAtMost"], int(m.group(1)))
        self.assertEqual(j["skipAtLeast"], int(m.group(2)))

    def test_json_without_dry_run_exits_2(self):
        """`--json` tek başına anlamsız: gerçek koşuda sayı ancak yazdıktan
        sonra bilinir → kullanım hatası (2), sessizce prose'e düşmez."""
        fixture = self._fixture()
        res = self._run(str(fixture), "--json")
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("--json", res.stderr)
        self.assertIn("--dry-run", res.stderr)
        self.assertNotIn("bilinmeyen bayrak", res.stderr,
                         "--json bilinen bayrak olmalı (KNOWN_FLAGS)")
        self.assertNotIn("[DRY-RUN]", res.stdout, "rapor basılmamalı")

    def test_missing_source_reports_clean_error(self):
        """Eksik kaynak: ham Node/ENOENT yığını DEĞİL, tek satır mesaj."""
        missing = pathlib.Path(self.tmp.name) / "yok.jsonl"
        res = self._run(str(missing), "--dry-run")
        self.assertEqual(res.returncode, 1)
        self.assertIn("kaynak okunamadı", res.stderr)
        self.assertIn("yok.jsonl", res.stderr, "hata yolu söylemeli")
        self.assertNotIn("Error: ENOENT", res.stderr, "ham Node hatası sızmamalı")
        self.assertNotRegex(res.stderr, r"\n\s+at\s", "yığın çerçevesi basılmamalı")

    def test_dry_run_branch_precedes_client_construction(self):
        """Yapısal sözleşme: dry-run erken döner — client ONDAN SONRA kurulur."""
        src = (TREND_DB / "scripts" / "load.ts").read_text(encoding="utf-8")
        self.assertIn("if (dryRun)", src)
        self.assertLess(src.index("if (dryRun)"),
                        src.index("new PrismaClient("),
                        "dry-run bloğu client kurulumundan önce olmalı")
        self.assertIn("KNOWN_FLAGS", src, "bayrak whitelist'i kayboldu")


if __name__ == "__main__":
    unittest.main()
