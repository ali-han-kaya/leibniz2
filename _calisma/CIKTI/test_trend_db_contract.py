"""Trend-DB sözleşme testleri — preview_server ↔ Prisma şema ↔ loader ↔ dashboard.

Sürükleme (drift) koruması: preview_server.HISTORY_KEYS'teki her anahtar
(1) apps/trend-db/prisma/schema.prisma'da kolon olarak (map hedefi veya düz ad),
(2) apps/trend-db/scripts/load.ts'te `row.<anahtar>` okuması olarak
mevcut olmalıdır. Statik denetim — ağ/DB/node gerektirmez.

**Okuma yolu da kapsamda** (2026-10-17): `apps/dashboard-next/lib/trend-db.ts`
şemayı üretilmiş Prisma istemcisiyle okur ve alanları tel sözleşmesine
(`preview_contract.schema.json` → `preview-contract.generated.ts`) çevirir.
Üçüncü bir tüketici olduğu için guard onu da kilitler:

  - okunan her Prisma alanı şemada VAR olmalı (tsc `node_modules` yokken
    atlandığı için derleme kanıt değildir),
  - üretilen `Latest` / `history` / `refs` anahtarları tel sözleşmesinde
    yayınlanan alanlardan olmalı,
  - `history`/`refs` anahtar kümeleri `preview.ts`'teki DONMUŞ `TrendRow` /
    `RefsRow` Pick listeleriyle BİREBİR eşleşmeli (sessiz genişleme yok),
  - sorgu `ts desc` + `reverse()` sırasını korumalı (aksi halde sayfa en eski
    N'i "son N" diye gösterir).
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
DASHBOARD = REPO_ROOT / "apps" / "dashboard-next"
DB_READ = DASHBOARD / "lib" / "trend-db.ts"
PREVIEW_FACADE = DASHBOARD / "lib" / "preview.ts"
WIRE_CONTRACT = DASHBOARD / "lib" / "preview-contract.generated.ts"

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


def model_fields():
    """schema.prisma `model TrendRun` alan adları (camelCase, Prisma adı)."""
    schema = (TREND_DB / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    m = re.search(r"model TrendRun \{(.*?)\n\}", schema, re.S)
    assert m, "schema.prisma'da model TrendRun bulunamadı"
    fields = set()
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("@@"):
            continue
        fields.add(line.split()[0])
    return fields


def wire_type_fields(type_name):
    """`preview-contract.generated.ts` içindeki bir tipin alan kümesi."""
    src = WIRE_CONTRACT.read_text(encoding="utf-8")
    m = re.search(r"export type %s = \{(.*?)\n\};" % type_name, src, re.S)
    assert m, f"tel sözleşmesinde {type_name} tipi yok"
    return set(re.findall(r"^\s{2}([a-z_0-9]+)\??:", m.group(1), re.M))


def frozen_pick_keys(type_name):
    """`preview.ts`'teki `export type X = Pick<HistoryRow, ...>` anahtarları."""
    src = PREVIEW_FACADE.read_text(encoding="utf-8")
    m = re.search(
        r"export type %s = Pick<\s*HistoryRow,\s*([^>]+)>" % type_name,
        src, re.S)
    assert m, f"preview.ts'te {type_name} Pick tanımı yok"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _db_read_source():
    if not DB_READ.exists():
        raise AssertionError(
            "apps/dashboard-next/lib/trend-db.ts yok — DB okuma katmanı "
            "sözleşmesi denetlenemez (dosya commit edilmeli)")
    return DB_READ.read_text(encoding="utf-8")


def _block(src, start_marker, end_marker):
    start = src.index(start_marker)
    return src[start:src.index(end_marker, start)]


def _object_keys(src, anchor, terminator):
    """`anchor`dan SONRAKİ ilk nesne literal'inin anahtarları."""
    start = src.index(anchor) + len(anchor)
    return set(re.findall(r"^\s+([a-z_0-9]+):",
                          src[start:src.index(terminator, start)], re.M))


def db_latest_keys():
    """`getLatestFromDb` dönüş nesnesinin anahtarları.

    Fonksiyonun başında `if (!row) return { verdict: "UNKNOWN" };` var — bu
    yüzden SON `return {` alınır (ilk değil).
    """
    src = _db_read_source()
    block = _block(src, "export const getLatestFromDb",
                   "export const getTrendFromDb")
    return _object_keys(block[block.rindex("return {"):], "return {", "};")


def db_history_keys():
    """`getTrendFromDb` içindeki `history` map anahtarları."""
    src = _db_read_source()
    block = _block(src, "const history: TrendRow[] = rows.map",
                   "const refs: RefsRow[] = rows.map")
    return _object_keys(block, "rows.map((r) => ({", "}));")


def db_refs_keys():
    """`getTrendFromDb` içindeki `refs` map anahtarları."""
    src = _db_read_source()
    block = _block(src, "const refs: RefsRow[] = rows.map",
                   "const compare: CompareRow[] = rows.map")
    return _object_keys(block, "rows.map((r) => ({", "}));")


def db_compare_keys():
    """`getTrendFromDb` içindeki `compare` map anahtarları (süre/bütçe paneli)."""
    src = _db_read_source()
    block = _block(src, "const compare: CompareRow[] = rows.map",
                   "return { history, refs, compare };")
    return _object_keys(block, "rows.map((r) => ({", "}));")


def db_prisma_fields():
    """Okuma katmanının Prisma satırından okuduğu alanlar (camelCase)."""
    src = _db_read_source()
    accessed = set(re.findall(r"\b(?:row|r)\.([A-Za-z]\w*)", src))
    # Metot/yardımcı çağrıları alan değil.
    return accessed - {"toISOString", "toNumber"}


class TestDashboardDbReadContract(unittest.TestCase):
    """`lib/trend-db.ts` — şema → üretilmiş istemci → tel sözleşmesi zinciri.

    Neden statik: `test_dashboard_next_contract.py` gerçek `tsc`yi yalnız
    `node_modules` varsa koşar (fresh checkout'ta atlar) ve `trend-db.ts`
    tsc kapsamı dışında kalabilir. Tip hatası ancak derlemede görünür; bu
    sınıf alan/anahtar sürüklenmesini derlemesiz yakalar.
    """

    def test_read_layer_prisma_fields_exist_in_schema(self):
        missing = db_prisma_fields() - model_fields()
        self.assertEqual(
            missing, set(),
            f"okuma katmanı şemada olmayan alanlar okuyor: {sorted(missing)}")

    def test_latest_mapping_keys_are_published_by_wire_contract(self):
        extra = db_latest_keys() - wire_type_fields("Latest")
        self.assertEqual(
            extra, set(),
            f"getLatestFromDb tel sözleşmesinde olmayan alan üretiyor: "
            f"{sorted(extra)}")
        # Tersi yön: sözleşmedeki her Latest alanı DB yolunda üretilmeli —
        # üretilmeyen alan panoda daima "—" olur (sessiz boşluk).
        missing = wire_type_fields("Latest") - db_latest_keys()
        self.assertEqual(
            missing, set(),
            f"Latest sözleşme alanları DB yolunda üretilmiyor: {sorted(missing)}")

    def test_history_mapping_matches_frozen_trend_row(self):
        produced = db_history_keys()
        self.assertEqual(
            produced, frozen_pick_keys("TrendRow"),
            "DB history eşlemesi ile preview.ts TrendRow Pick listesi ayrıştı "
            "— biri güncellenmeden diğeri değişmemeli")
        extra = produced - wire_type_fields("HistoryRow")
        self.assertEqual(
            extra, set(),
            f"DB history tel sözleşmesinde olmayan alan üretiyor: {sorted(extra)}")

    def test_refs_mapping_matches_frozen_refs_row(self):
        produced = db_refs_keys()
        self.assertEqual(
            produced, frozen_pick_keys("RefsRow"),
            "DB refs eşlemesi ile preview.ts RefsRow Pick listesi ayrıştı")
        extra = produced - wire_type_fields("HistoryRow")
        self.assertEqual(
            extra, set(),
            f"DB refs tel sözleşmesinde olmayan alan üretiyor: {sorted(extra)}")

    def test_trend_query_is_desc_then_reversed(self):
        """Sıra sözleşmesi: `desc + take` → `reverse()` → artan dizi.

        `reverse()` düşerse sayfa EN ESKİ `limit` satırı "son N" diye
        gösterir; hata vermez, sadece yanlış pencere çizer.
        """
        src = _db_read_source()
        body = _block(src, "getTrendFromDb = cache(",
                      "return { history, refs, compare };")
        self.assertIn('orderBy: { ts: "desc" }', body)
        self.assertIn("take: limit", body)
        self.assertIn(
            "rows.reverse()", body,
            "reverse() kayboldu — sayfa EN ESKİ `limit` satırı 'son N' diye "
            "gösterir (hata vermez, yanlış pencere çizer)")
        find_pos = body.index("findMany(")
        reverse_pos = body.index("rows.reverse()")
        self.assertLess(find_pos, reverse_pos,
                        "reverse() findMany'dan sonra olmalı")
        self.assertLess(reverse_pos, body.index("rows.map"),
                        "reverse() eşlemeden ÖNCE olmalı")

    def test_compare_mapping_is_published_by_wire_contract(self):
        """Süre/bütçe paneli yeni bir yüzey: sözleşme dışına alan sızmamalı.

        `compare` DONMUŞ bir Pick değil (yeni tüketici), ama her anahtarı tel
        sözleşmesinde yayınlanmalı ve panelin okuduğu zorunlu alanlar eksik
        olmamalı — eksik alan grafikte sessiz boşluk demektir.
        """
        produced = db_compare_keys()
        extra = produced - wire_type_fields("HistoryRow")
        self.assertEqual(
            extra, set(),
            f"DB compare tel sözleşmesinde olmayan alan üretiyor: {sorted(extra)}")
        required = {"ts", "duration_s", "budget_usd", "budget_limit",
                    "verdict", "p0", "p1"}
        self.assertEqual(required - produced, set(),
                         "compare eşlemesi panelin okuduğu alanları üretmiyor")

    def test_refs_by_source_is_read_from_schema_column(self):
        """Json kolonu okunmasa grafik sessizce nokta üretmez."""
        self.assertIn("refsBySource", db_prisma_fields())
        self.assertIn("refsBySource", model_fields())


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

    def test_dry_run_client_only_constructed_for_explicit_check_db(self):
        """Yapısal sözleşme: dry-run'ın client'ı YALNIZ `--check-db` ile kurulur.

        Düz `--dry-run` DB'ye dokunmaz (davranışsal kanıt: JSON'da
        `dbConnected: false`). `--check-db` bilinçli bir SALT-OKUNUR istisnadır,
        bu yüzden kaynakta client kurulumu o bayrağın guard'ının ALTINDA olmalı:
        guard silinirse her dry-run kimliksiz koşamaz hâle gelir.
        """
        src = (TREND_DB / "scripts" / "load.ts").read_text(encoding="utf-8")
        self.assertIn("if (dryRun)", src)
        self.assertIn("KNOWN_FLAGS", src, "bayrak whitelist'i kayboldu")
        self.assertLess(src.index("else if (checkDb)"),
                        src.index("new PrismaClient("),
                        "--check-db guard'ı client kurulumundan önce olmalı")

    # ── 3. tur: çakışma ölçümü (`--check-db` / `--keys-file`) ──────────────

    def _snapshot(self, name, lines):
        path = pathlib.Path(self.tmp.name) / name
        path.write_text("\n".join(lines) + ("\n" if lines else ""),
                        encoding="utf-8")
        return path

    def test_keys_file_snapshot_makes_counts_exact(self):
        """`--keys-file`: kimliksiz KESİN ölçüm — "en çok" değil, gerçek sayı.

        JS tarafı (check-db.test.mjs) aynı seam'i kilitler; buradaki kopya
        kasıtlı: repo kökündeki tek kapı Python testlerini koşar, JS koşucusu
        yalnız `npm test` ile çalışır — iki yüz birden kaybolmasın.
        """
        fixture = self._fixture()
        snap = self._snapshot(
            "keys.jsonl", ['{"ts": "2026-09-27T10:00:00.000000+00:00"}'])
        res = self._run(str(fixture), "--dry-run", "--json",
                        "--keys-file=%s" % snap)
        self.assertEqual(res.returncode, 0, res.stderr)
        j = json.loads(res.stdout.strip())
        self.assertEqual(j["conflictSource"], "snapshot")
        self.assertEqual(j["conflictRows"], 1)
        self.assertEqual(j["alreadyPresent"], 1)
        self.assertEqual(j["insert"], 1, "3. satır dosya-içi çakışma → 1 aday")
        self.assertEqual(j["skip"], 4,
                         "2 doğrulama-dışı + 1 dosya-içi + 1 zaten var")
        self.assertIs(j["dbConnected"], False, "snapshot ağ kurmamalı")
        prose = self._run(str(fixture), "--dry-run", "--keys-file=%s" % snap)
        self.assertIn("çakışma kaynağı: snapshot (1 satır)", prose.stdout)
        self.assertNotIn("bu raporda YOK", prose.stdout,
                         "ölçülmüş sayı varken \"yok\" denemez")

    def test_keys_file_requires_equals_form_and_dry_run(self):
        fixture = self._fixture()
        snap = self._snapshot("keys2.jsonl", [])
        spaced = self._run(str(fixture), "--dry-run", "--keys-file", str(snap))
        self.assertEqual(spaced.returncode, 2, spaced.stdout)
        self.assertIn("--keys-file=<yol>", spaced.stderr)
        nodry = self._run(str(fixture), "--keys-file=%s" % snap)
        self.assertEqual(nodry.returncode, 2, nodry.stdout)
        self.assertIn("--keys-file yalnız --dry-run ile", nodry.stderr)

    def test_check_db_without_credentials_exits_1_without_report(self):
        """Kesin sayı isteyen çağıran, sınır raporunu KESİN sanmasın."""
        fixture = self._fixture()
        res = self._run(str(fixture), "--dry-run", "--check-db")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("DATABASE_URL", res.stderr)
        self.assertNotIn("[DRY-RUN]", res.stdout, "belirsiz rapor basılmamalı")
        self.assertNotIn("bilinmeyen bayrak", res.stderr,
                         "--check-db bilinen bayrak olmalı")


if __name__ == "__main__":
    unittest.main()
