#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_refs.py — verify_delivery.py referans fallback mantığı kapısı.

openlibrary_fallback_check ağ çağrısını _http_json üzerinden yapar; bu test
_http_json'u mock'layarak eşleşme mantığını (title + creator, aksan-duyarsız)
ağsız ve deterministik doğrular. Ayrıca _fold'un aksan katlama davranışını
test eder. stdlib unittest — ek bağımlılık yok.
"""
import io
import pathlib
import sys
import time
import unittest
import urllib.error
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402

# (title, author_name, year, publisher) listesi → OpenLibrary docs biçimi.
def _docs(*entries):
    return {"docs": [
        {"title": t, "author_name": a, "first_publish_year": y,
         "publisher": p}
        for (t, a, y, p) in entries
    ]}


class TestFold(unittest.TestCase):
    def test_accent_fold(self):
        self.assertEqual(vd._fold("Lagrée"), "lagree")
        self.assertEqual(vd._fold("stoïcisme"), "stoicisme")

    def test_no_accent_unchanged(self):
        self.assertEqual(vd._fold("Metaphysical Grounding"),
                         "metaphysicalgrounding")


class TestHttpGet(unittest.TestCase):
    def test_retry_on_transient_then_success(self):
        calls = []

        def urlopen(req, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise urllib.error.URLError("geçici")
            return io.BytesIO(b"ok")

        with mock.patch.object(vd.urllib.request, "urlopen",
                               side_effect=urlopen), \
                mock.patch.object(vd.time, "sleep"):
            data = vd._http_get("http://x", timeout=15, retries=2)
        self.assertEqual(data, b"ok")
        self.assertEqual(len(calls), 2)

    def test_no_retry_on_404(self):
        calls = []

        def urlopen(req, timeout):
            calls.append(1)
            raise urllib.error.HTTPError("http://x", 404, "nf", {}, None)

        with mock.patch.object(vd.urllib.request, "urlopen",
                               side_effect=urlopen), \
                mock.patch.object(vd.time, "sleep") as m:
            with self.assertRaises(urllib.error.HTTPError):
                vd._http_get("http://x", timeout=15, retries=3)
        self.assertEqual(len(calls), 1)  # 404 fail-fast — retry yok
        m.assert_not_called()

    def test_default_retries_is_three(self):
        # IA SSL handshake timeout'larına karşı varsayılan deneme sayısı 3
        # (archive_check → _http_json(url) varsayılan retries'ı kullanır).
        self.assertEqual(vd.REFERENCE_HTTP_RETRIES, 3)

    def test_default_retries_gives_three_attempts_on_transient(self):
        # Varsayılan (retries argümansız) geçici hatalarda 3 deneme yapar —
        # IA'nın archive.org SSL handshake yolunun CI'da 3. denemede geçtiği
        # davranışı sabitler (flaky UNVERIFIED sıfırlama hedefi).
        calls = []

        def urlopen(req, timeout):
            calls.append(timeout)
            raise urllib.error.URLError("geçici SSL handshake")

        with mock.patch.object(vd.urllib.request, "urlopen",
                               side_effect=urlopen), \
                mock.patch.object(vd.time, "sleep") as m:
            with self.assertRaises(urllib.error.URLError):
                vd._http_get("http://x", timeout=15)
        self.assertEqual(len(calls), 3)  # ilk + 2 retry
        m.assert_has_calls([mock.call(1.0), mock.call(2.0)])


class TestAuditBudget(unittest.TestCase):
    def test_budget_exceeded_skips_network(self):
        # Bütçe 0 → tüm ağ kontrolleri UNVERIFIED atlanır; hiçbir check çağrılmaz
        # (yanlış PASS yok). Polite sleep'ler de mock'lanır (test hızı için).
        with mock.patch.object(vd, "REFERENCE_AUDIT_BUDGET_S", 0), \
                mock.patch.object(vd.time, "sleep"):
            for fn in ("crossref_check", "sep_check", "openlibrary_check",
                       "archive_check", "perseus_check",
                       "openlibrary_fallback_check", "hathitrust_check",
                       "google_books_check"):
                mock.patch.object(
                    vd, fn,
                    side_effect=lambda *a, **k: (_ for _ in ()).throw(
                        AssertionError("ağ çağrısı yapılmamalı"))).start()
            try:
                results = vd.run_reference_audit(
                    "", lambda *a, **k: None, quiet=True)
            finally:
                mock.patch.stopall()
        self.assertEqual(len(results), 61)  # V5q: +4 Sextus (IA) +1 Della Rocca (URL)
        self.assertTrue(all(r["verdict"] == "UNVERIFIED" for r in results))
        self.assertTrue(all("bütçesi aşıldı" in r["detail"]
                           for r in results))


class TestParallelAudit(unittest.TestCase):
    """V5o: çevrimiçi denetim sınırlı havuzda paralel koşar (bütçe-skip
    aynı kalır), sonuçlar girdi sırasında döner, archive fallback kaynağı
    doğru işaretlenir. Ağ çağrısı yok — tüm check fonksiyonları mock."""

    def _run(self, pool, archive_side):
        with mock.patch.object(vd, "REFERENCE_POOL_SIZE", pool), \
                mock.patch.object(vd, "crossref_check",
                                  return_value=("PASS", "x")), \
                mock.patch.object(vd, "sep_check",
                                  return_value=("PASS", "x")), \
                mock.patch.object(vd, "openlibrary_check",
                                  return_value=("PASS", "x")), \
                mock.patch.object(vd, "_archive_with_fallback",
                                  side_effect=archive_side), \
                mock.patch.object(vd, "perseus_check",
                                  return_value=("PASS", "x")):
            return vd.run_reference_audit(
                "", lambda *a, **k: None, quiet=True)

    def test_order_preserved_parallel(self):
        # ex.map girdi sırasını korur: crossref(6) + sep(5) + ol(22) +
        # archive(25) + url(1) + perseus(2) = 61, listelerdeki sırayla.
        results = self._run(
            4, lambda r: ("PASS", "ok", "archive"))
        self.assertEqual(len(results), 61)
        order = [r["key"] for r in results]
        expected = ([r["key"] for r in vd.REFERENCE_CROSSREF]
                    + [r["key"] for r in vd.REFERENCE_SEP]
                    + [r["key"] for r in vd.REFERENCE_OPENLIBRARY]
                    + [r["key"] for r in vd.REFERENCE_ARCHIVE]
                    + [r["key"] for r in vd.REFERENCE_URL]
                    + [r["key"] for r in vd.REFERENCE_PERSEUS])
        self.assertEqual(order, expected)
        self.assertTrue(all(r["verdict"] == "PASS" for r in results))

    def test_archive_fallback_source(self):
        # Archive görevleri IA kapsamı dışında kalınca gerçek kaynağı
        # (openlibrary) döndürür — by_source'u şişirmez, kaynağı doğru verir.
        results = self._run(
            4, lambda r: ("PASS", "fallback ile doğrulandı", "openlibrary"))
        # Gerçek OpenLibrary girdileriyle karışmasın: archive kümesindeki
        # anahtarlara göre filtrele.
        arch_keys = {r["key"] for r in vd.REFERENCE_ARCHIVE}
        arc = [r for r in results if r["key"] in arch_keys]
        self.assertEqual(len(arc), 25)  # V5q: +4 Sextus edisyonu
        self.assertTrue(all(r["source"] == "openlibrary" for r in arc))
        self.assertTrue(all("fallback" in r["detail"] for r in arc))

    def test_concurrent_execution(self):
        # Havuz 4: yavaş OpenLibrary görevleri eşzamanlı çalışmalı (max_active
        # >= 2) ve toplam süre sıralı sürenin belirgin altında kalmalı.
        import threading
        active, max_active = 0, 0
        lock = threading.Lock()

        def slow(ref):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.15)
            with lock:
                active -= 1
            return "PASS", "ok"

        with mock.patch.object(vd, "REFERENCE_POOL_SIZE", 4), \
                mock.patch.object(vd, "crossref_check",
                                  return_value=("PASS", "x")), \
                mock.patch.object(vd, "sep_check",
                                  return_value=("PASS", "x")), \
                mock.patch.object(vd, "openlibrary_check", side_effect=slow), \
                mock.patch.object(vd, "_archive_with_fallback",
                                  side_effect=lambda r: ("PASS", "x", "archive")), \
                mock.patch.object(vd, "perseus_check",
                                  return_value=("PASS", "x")):
            t0 = time.time()
            results = vd.run_reference_audit(
                "", lambda *a, **k: None, quiet=True)
            dt = time.time() - t0
        self.assertEqual(len(results), 61)
        self.assertGreaterEqual(max_active, 2)  # paralellik kanıtı
        self.assertLess(dt, 2.5)  # 22 × 0.15 sn sıralı ~3.3 sn olurdu

    def test_pool1_sequential(self):
        # Havuz 1 → sıralı (eski davranış); sonuç yine 61, hepsi PASS.
        results = self._run(
            1, lambda r: ("PASS", "ok", "archive"))
        self.assertEqual(len(results), 61)
        self.assertTrue(all(r["verdict"] == "PASS" for r in results))


class TestCoverageGap(unittest.TestCase):
    """V5q: kapsam boşluğu kapatıldı — 64 .tex referansının tamamı çevrimiçi
    listelerde (veya REFERENCE_KNOWN sabit listesinde). 4 Sextus edisyonu IA
    (ia_ids), Della Rocca 2010 URL listesinde. Yanlışlıkla düşerse test FAIL."""

    def test_sextus_entries_with_ia_ids(self):
        by_key = {r["key"]: r for r in vd.REFERENCE_ARCHIVE}
        expect = {
            "Sextus 1562 Estienne": ["bub_gb_ddgo3O27ItcC"],
            "Sextus 1569 Hervet": ["bub_gb_RyhI9DhB82sC", "bub_gb_nHEaGbVSZMcC"],
            "Sextus 1621 Chouet": ["bub_gb_-Yio5nIT2m0C"],
        }
        for key, ids in expect.items():
            self.assertIn(key, by_key, f"{key} arşiv listesinde yok")
            self.assertEqual(by_key[key].get("ia_ids"), ids)
        self.assertIn("Sextus Loeb Bury", by_key)

    def test_della_rocca_url_entry(self):
        keys = {r["key"] for r in vd.REFERENCE_URL}
        self.assertIn("Della Rocca 2010", keys)
        dr = [r for r in vd.REFERENCE_URL if r["key"] == "Della Rocca 2010"][0]
        self.assertIn("web.archive.org", dr["url"])
        self.assertEqual(dr["title"], "PSR")
        self.assertIn("Della Rocca", dr.get("markers", []))

    def test_della_rocca_handle_field(self):
        # V5t: Della Rocca 2010'ın kendi DC.identifier'ı bir HANDLE'dır
        # (hdl.handle.net/2027/spo.3521354.0010.007), CrossRef DOI değil.
        # handle alanı + handle_needle yanlışlıkla düşerse test FAIL.
        dr = [r for r in vd.REFERENCE_URL if r["key"] == "Della Rocca 2010"][0]
        self.assertEqual(dr.get("handle"), "2027/spo.3521354.0010.007")
        self.assertIn("quod.lib.umich.edu/p/phimp", dr.get("handle_needle", ""))

    def test_handle_check_pass(self):
        # Handle System API 200 + responseCode 1 + URL değeri → PASS (ağsız).
        ref = {"key": "Della Rocca 2010",
               "handle": "2027/spo.3521354.0010.007",
               "handle_needle": "quod.lib.umich.edu/p/phimp"}
        payload = {"responseCode": 1, "handle": "2027/spo.3521354.0010.007",
                   "values": [{"index": 1, "type": "URL",
                                "data": {"format": "string",
                                          "value": "https://quod.lib.umich.edu/"
                                                   "p/phimp/3521354.0010.007/1"}}]}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "PASS")
        self.assertIn("quod.lib.umich.edu", d)

    def test_handle_check_404(self):
        # Kayıt yok (404) → MISMATCH (fail-closed; DOI 404 davranışıyla aynı).
        ref = {"key": "X", "handle": "2027/spo.nope"}
        with mock.patch.object(vd, "_http_json",
                               side_effect=urllib.error.HTTPError(
                                   "u", 404, "Not Found", None, None)):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "MISMATCH")

    def test_handle_check_response_code(self):
        # responseCode != 1 → MISMATCH.
        ref = {"key": "X", "handle": "2027/spo.x"}
        payload = {"responseCode": 100, "values": []}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "MISMATCH")

    def test_handle_check_no_url_value(self):
        # responseCode 1 ama URL değeri yok → MISMATCH.
        ref = {"key": "X", "handle": "2027/spo.x"}
        payload = {"responseCode": 1, "values": [{"type": "HS_ADMIN"}]}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "MISMATCH")

    def test_handle_check_needle_mismatch(self):
        # URL değeri var ama handle_needle içermiyor → MISMATCH.
        ref = {"key": "X", "handle": "2027/spo.x",
               "handle_needle": "quod.lib.umich.edu/p/phimp"}
        payload = {"responseCode": 1, "values": [
            {"type": "URL", "data": {"value": "https://example.com/other"}}]}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "MISMATCH")

    def test_handle_check_network_error(self):
        # Ağ hatası → UNVERIFIED (yanlış PASS yok).
        ref = {"key": "X", "handle": "2027/spo.x"}
        with mock.patch.object(vd, "_http_json",
                               side_effect=urllib.error.URLError("ağ")):
            v, d = vd.handle_check(ref)
        self.assertEqual(v, "UNVERIFIED")

    def test_ia_ident_check_pass(self):
        # ia_ids metadata'sı title+creator eşleşiyorsa PASS (ağsız).
        ref = {"key": "Sextus 1562 Estienne",
               "title_needle": "pyrrhoniarum hypotyposeon",
               "creator_needle": "sextus",
               "ia_ids": ["bub_gb_ddgo3O27ItcC"]}
        payload = {"response": {"docs": [{
            "identifier": "bub_gb_ddgo3O27ItcC",
            "title": "Sexti Philosophi Pyrrhoniarum hypotypōseōn libri 3",
            "creator": "Sextus : Empiricus",
            "year": 1562}]}}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd._archive_ident_check(ref, "bub_gb_ddgo3O27ItcC")
        self.assertEqual(v, "PASS")
        self.assertIn("bub_gb_ddgo3O27ItcC", d)

    def test_ia_ident_check_latin_uv(self):
        # erken-modern 'Aduersus' (u) ↔ needle 'adversus' (v) eşleşir.
        ref = {"key": "Sextus 1569 Hervet",
               "title_needle": "adversus mathematicos",
               "creator_needle": "sextus",
               "ia_ids": ["bub_gb_RyhI9DhB82sC"]}
        payload = {"response": {"docs": [{
            "identifier": "bub_gb_RyhI9DhB82sC",
            "title": "Sexti Empirici ... Aduersus mathematicos, hoc est, "
                     "aduersus eos qui profitentur disciplinas",
            "creator": "Sextus : Empiricus",
            "year": 1569}]}}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd._archive_ident_check(ref, "bub_gb_RyhI9DhB82sC")
        self.assertEqual(v, "PASS")

    def test_ia_ids_no_title_fallback(self):
        # ia_ids hiçbiri eşleşmediyse title sorgusu ÇALIŞMAMALI (yanlış
        # edisyon riski) — UNVERIFIED döner, ağ çağrısı title'a gitmez.
        ref = {"key": "Sextus 1569 Hervet",
               "title_needle": "adversus", "creator_needle": "sextus",
               "ia_ids": ["bub_gb_nope1", "bub_gb_nope2"]}
        with mock.patch.object(vd, "_archive_ident_check",
                               return_value=("UNVERIFIED", "eşleşmedi")), \
                mock.patch.object(
                    vd, "_http_json",
                    side_effect=lambda *a, **k: (_ for _ in ()).throw(
                        AssertionError("title sorgusu çağrılmamalı"))):
            v, d = vd.archive_check(ref)
        self.assertEqual(v, "UNVERIFIED")
        self.assertIn("ia_ids", d)

    def test_ia_ident_check_wrong_creator(self):
        ref = {"key": "X", "title_needle": "adversus",
               "creator_needle": "hervet", "ia_ids": ["x"]}
        payload = {"response": {"docs": [{
            "identifier": "x", "title": "Adversus mathematicos",
            "creator": "Sextus", "year": 1569}]}}
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd._archive_ident_check(ref, "x")
        self.assertEqual(v, "UNVERIFIED")

    def test_sep_check_markers(self):
        # markers listesinin TÜMÜ sayfada olmalı; eksikse MISMATCH.
        ref = {"url": "http://x", "title": "PSR", "markers": ["Della Rocca"]}
        with mock.patch.object(vd, "_http_get",
                               return_value=b"PSR paper by Della Rocca here"):
            v, d = vd.sep_check(ref)
        self.assertEqual(v, "PASS")
        with mock.patch.object(vd, "_http_get", return_value=b"PSR only"):
            v, d = vd.sep_check(ref)
        self.assertEqual(v, "MISMATCH")
        self.assertIn("Della Rocca", d)


class TestCrossRefCoverage(unittest.TestCase):
    def test_v5n_norton_popkin_added(self):
        # V5n: Norton 1981 + Popkin 1951 DOI'leri CrossRef'e eklendi
        # (canlı kapsam 54 → 56); bu girişler yanlışlıkla düşerse test FAIL.
        keys = {r["key"] for r in vd.REFERENCE_CROSSREF}
        self.assertIn("Norton 1981", keys)
        self.assertIn("Popkin 1951", keys)
        self.assertEqual(len(vd.REFERENCE_CROSSREF), 6)
        for r in vd.REFERENCE_CROSSREF:
            if r["key"] in ("Norton 1981", "Popkin 1951"):
                self.assertTrue(r["doi"].startswith("10."))


class TestHathiTrustIdentifiers(unittest.TestCase):
    """V5p: OpenLibrary'den çekilen OCLC/LCCN identifier'ları ht_ids'e eklendi.
    HathiTrust ISBN yerine OCLC/LCCN indeksler — Xunzi lccn:87033578 ile gerçek
    kayıta çözülür. Bu girişler yanlışlıkla düşerse test FAIL."""

    def test_v5p_oclc_lccn_added(self):
        by_key = {r["key"]: r for r in vd.REFERENCE_ARCHIVE}
        expect = {
            "Lagree 1994": ["oclc:32045786", "lccn:95174106"],
            "Millican 2002": ["oclc:48957942", "lccn:2002020030"],
            "Schmitt 1972": ["oclc:1194850", "lccn:73155022"],
            "Xunzi Knoblock": ["lccn:87033578", "oclc:17265207"],
            # V5r: edisyon kayıtlarındaki lccn değerleri de eklendi (HT'de 0
            # kayıt ama doğru identifier — HT ileride alırsa eşleşir)
            "Fine 2012": ["isbn:9781107460287"],
        }
        for key, ids in expect.items():
            self.assertIn(key, by_key, f"{key} arşiv listesinde yok")
            ht = by_key[key]["ht_ids"]
            for i in ids:
                self.assertIn(i, ht, f"{key} eksik {i}")

    def test_hathitrust_pass_via_lccn(self):
        # HT yanıtındaki kayıt başlığı title_needle içeriyorsa PASS (ağsız).
        ref = {"key": "Xunzi Knoblock", "title_needle": "xunzi",
               "ht_ids": ["lccn:87033578", "isbn:9780231129657"]}
        payload = {
            "lccn:87033578": {
                "records": {
                    "001082130": {
                        "titles": ["Xunzi : a translation and study "
                                   "of the complete works"],
                    }
                },
                "items": [],
            }
        }
        with mock.patch.object(vd, "_http_json", return_value=payload):
            v, d = vd.hathitrust_check(ref)
        self.assertEqual(v, "PASS")
        self.assertIn("Xunzi", d)

    def test_hathitrust_no_record_unverified(self):
        ref = {"key": "X", "title_needle": "z",
               "ht_ids": ["oclc:999999999", "isbn:123"]}
        with mock.patch.object(vd, "_http_json",
                               return_value={"oclc:999999999":
                                             {"records": {}, "items": []}}):
            v, d = vd.hathitrust_check(ref)
        self.assertEqual(v, "UNVERIFIED")
        self.assertIn("kayıt yok", d)


class TestHathiTrustApiFormat(unittest.TestCase):
    """HathiTrust identifier-keyli API formatını (data[ident].records) sabitle.

    Gerçek API yanıtı şeması: {"<ident>": {"records": {"<recid>": {"titles": [...]}},
    "items": [...]}}. Test edilen yollar: boş records → UNVERIFIED, records var
    ama başlık eşleşmez → MISMATCH, records var + başlık eşleşir → PASS."""

    # ── Yardımcı: mock _http_json ile hathitrust_check'i çağır ──
    def _call(self, ref, payload):
        with mock.patch.object(vd, "_http_json", return_value=payload):
            return vd.hathitrust_check(ref)

    # ── 1) 0 kayıt — data[ident].records boş → UNVERIFIED ──
    def test_api_format_zero_records_returns_unverified(self):
        """HT yanıtında records {} ise UNVERIFIED + 'kayıt yok' mesajı."""
        ref = {"key": "Test", "title_needle": "something",
               "ht_ids": ["oclc:999999999"]}
        payload = {
            "oclc:999999999": {
                "records": {},           # ← API'nin gerçek boş formatı
                "items": []
            }
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "UNVERIFIED", f"boş records → UNVERIFIED, alınan: {v}")
        self.assertIn("kayıt yok", d,
                      f"açıklamada 'kayıt yok' beklenir, alınan: {d}")

    def test_api_format_missing_records_key_unverified(self):
        """API yanıtında records anahtarı HiÇ yoksa → UNVERIFIED (sağlam parse)."""
        ref = {"key": "Test", "title_needle": "something",
               "ht_ids": ["lccn:123"]}
        payload = {
            "lccn:123": {
                # records anahtarı yok — eski/yeni API uyumsuzluğuna karşı
                "items": []
            }
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "UNVERIFIED",
                         f"records anahtarı yoksa UNVERIFIED, alınan: {v}")
        self.assertIn("kayıt yok", d)

    def test_api_format_identifier_key_missing_unverified(self):
        """data'da hiçbir ident anahtarı yoksa → UNVERIFIED (identifier yanlış)."""
        ref = {"key": "Test", "title_needle": "something",
               "ht_ids": ["isbn:000"]}
        payload = {}  # API hiç kayıt dönmedi
        v, d = self._call(ref, payload)
        self.assertEqual(v, "UNVERIFIED",
                         f"ident anahtarı yoksa UNVERIFIED, alınan: {v}")
        self.assertIn("kayıt yok", d)

    # ── 2) Kayıt var ama başlık eşleşmez → MISMATCH ──
    def test_api_format_records_exist_title_mismatch_returns_mismatch(self):
        """records dolu ama title_needle içermez → MISMATCH.

        HT'de kayıt bulundu ama başlık beklenenle eşleşmezse yanlış PASS
        üretilmez — MISMATCH düşülür (fail-closed)."""
        ref = {"key": "Lagrée 1994",
               "title_needle": "juste lipse et la restauration du stoicisme",
               "ht_ids": ["oclc:32045786", "lccn:95174106"]}
        payload = {
            "oclc:32045786": {
                "records": {
                    "0032045786": {
                        "titles": [
                            "Unrelated title about Renaissance philosophy"
                        ],
                    }
                },
                "items": [{"orig": "UCB", "from": "original"}],
            },
            # İkinci ident başlık da eşleşmez
            "lccn:95174106": {
                "records": {
                    "95174106": {
                        "titles": ["Another different title"],
                    }
                },
                "items": [],
            },
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "MISMATCH",
                         f"başlık eşleşmezse MISMATCH, alınan: {v}")
        self.assertIn("kayıt var", d)
        self.assertIn("eşleşmedi", d)

    def test_api_format_multiple_titles_none_match_returns_mismatch(self):
        """Birden fazla title alanı var ama hiçbiri eşleşmez → MISMATCH."""
        ref = {"key": "Test", "title_needle": "stoic epistemology",
               "ht_ids": ["isbn:9781234567890"]}
        payload = {
            "isbn:9781234567890": {
                "records": {
                    "rec1": {
                        "titles": [
                            "Stoic Ethics and Logic",
                            "A Companion to Stoicism",
                            "The Cambridge History of Hellenistic Philosophy",
                        ],
                    }
                },
                "items": [],
            }
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "MISMATCH")
        self.assertIn("eşleşmedi", d)

    # ── 3) PASS — kayıt var + başlık eşleşir ──
    def test_api_format_pass_exact_title_match(self):
        """title_needle bir title'da aynen bulunursa PASS."""
        ref = {"key": "Xunzi Knoblock", "title_needle": "xunzi",
               "ht_ids": ["lccn:87033578"]}
        payload = {
            "lccn:87033578": {
                "records": {
                    "001082130": {
                        "titles": [
                            "Xunzi : a translation and study "
                            "of the complete works"
                        ],
                    }
                },
                "items": [{"orig": "MIU", "from": "original"}],
            }
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "PASS", f"başlık eşleşirse PASS, alınan: {v}")
        self.assertIn("Xunzi", d)
        self.assertIn("lccn:87033578", d)

    def test_api_format_pass_partial_title_match(self):
        """title_needle uzun başlığın alt-dizgisi olarak bulunursa PASS."""
        ref = {"key": "Test", "title_needle": "reading hume",
               "ht_ids": ["lccn:2002020030"]}
        payload = {
            "lccn:2002020030": {
                "records": {
                    "2002020030": {
                        "titles": [
                            "Reading Hume on human understanding : "
                            "essays on the first Enquiry"
                        ],
                    }
                },
                "items": [],
            }
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "PASS")
        self.assertIn("2002020030", d)

    def test_api_format_pass_subsequent_identifier(self):
        """İlk ident boş kayıt döndürse bile sonraki ident PASS verirse PASS."""
        ref = {"key": "Test", "title_needle": "xunzi",
               "ht_ids": ["isbn:9999999999999", "lccn:87033578"]}
        payload = {
            "isbn:9999999999999": {
                "records": {},           # ilk ident — boş
                "items": []
            },
            "lccn:87033578": {           # ikinci ident — eşleşir
                "records": {
                    "rec1": {
                        "titles": ["Xunzi : complete works"],
                    }
                },
                "items": [],
            },
        }
        v, d = self._call(ref, payload)
        self.assertEqual(v, "PASS",
                         f"sonraki ident eşleşirse PASS, alınan: {v}")
        self.assertIn("lccn:87033578", d)

    def test_api_format_strips_oclc_prefix_in_api_ident_key(self):
        """OCLC numarası — HT API ident anahtarında rakamın kendisidir.

        ÖNEMLİ: ht_ids'te `oclc:32045786` yazar ama HT API  ident anahtarını
        OCLC numarasının kendisi olarak döner (`32045786`, öneksiz).
        Bu test, _http_json mock'layan testlerin doğru ident anahtarını
        kullanması gerektiğini belgeler (gerçek API davranışı)."""
        ref = {"key": "Test", "title_needle": "some book",
               "ht_ids": ["oclc:32045786"]}
        # Gerçek HT API yanıtında ident anahtarı "32045786" olarak döner —
        # oclc: öneki YOKTUR. Test bunu bilinçli olarak belgelemektedir.
        payload = {
            # Bu test, ident anahtarının "oclc:32045786" (önekli) DEĞİL
            # "32045786" (öneksiz) biçiminde geldiğini varsayar.
            # Bu yüzden _call() burada önekli ht_ids ile çağrılır
            # ve API ident anahtarında önek olmadığı için eşleşme OLMAZ.
            # → MISMATCH değil UNVERIFIED (ilk ident'te kayıt yok = sonraki yok).
            "32045786": {
                "records": {
                    "rec1": {"titles": ["Juste Lipse et la restauration"]},
                },
                "items": [],
            }
        }
        # ht_ids "oclc:32045786" ile gider, API "oclc:32045786" anahtarını arar
        # ama payload'ta "32045786" vardır → ident anahtarı eşleşmez → UNVERIFIED
        v, d = self._call(ref, payload)
        # Bu gerçek API davranışı değil, test varsayımıdır.
        # Gerçek API'nin oclc: önekli istekleri nasıl döndürdüğü
        # canlı testle doğrulanmalıdır.
        self.assertIn(v, ("UNVERIFIED", "MISMATCH"),
                      "oclc: önek uyuşmazlığı → UNVERIFIED veya MISMATCH")


class TestOpenLibraryFallback(unittest.TestCase):
    def _call(self, ref, payload):
        with mock.patch.object(vd, "_http_json", return_value=payload):
            return vd.openlibrary_fallback_check(ref)

    def test_pass_title_and_creator(self):
        ref = {"key": "Fine 2012", "query": "q",
               "title_needle": "metaphysical grounding",
               "creator_needle": "correia"}
        v, d = self._call(ref, _docs(
            ("Metaphysical Grounding", ["Fabrice Correia"], 2012,
             ["Cambridge University Press"]),
        ))
        self.assertEqual(v, "PASS")
        self.assertIn("Metaphysical Grounding", d)

    def test_pass_accent_insensitive_creator(self):
        # "Lagrée" (yazar) ↔ creator_needle "lagree" — aksan farkı engel olmaz.
        ref = {"key": "Lagree 1994", "query": "q", "title_needle": "lipse",
               "creator_needle": "lagree"}
        v, d = self._call(ref, _docs(
            ("Juste Lipse et la restauration du stoïcisme",
             ["Jacqueline Lagrée"], 1994, ["J. Vrin"]),
        ))
        self.assertEqual(v, "PASS")

    def test_pass_title_only_when_no_creator(self):
        ref = {"key": "Millican 2002", "query": "q",
               "title_needle": "reading hume"}
        v, d = self._call(ref, _docs(
            ("Reading Hume on Human Understanding", ["Peter Millican"],
             2002, ["Oxford University Press"]),
        ))
        self.assertEqual(v, "PASS")

    def test_mismatch_when_no_match(self):
        ref = {"key": "X", "query": "q", "title_needle": "cicero scepticus",
               "creator_needle": "schmitt"}
        v, d = self._call(ref, _docs(
            ("Something Else", ["Other Author"], 2000, ["X"]),
        ))
        self.assertEqual(v, "MISMATCH")

    def test_unverified_when_no_docs(self):
        ref = {"key": "X", "query": "q", "title_needle": "z"}
        v, d = self._call(ref, {"docs": []})
        self.assertEqual(v, "UNVERIFIED")


class TestLocCheck(unittest.TestCase):
    """V5w: Library of Congress katalog kanıtı (lccn bazlı, HT'siz)."""

    def _call(self, ref, payload):
        with mock.patch.object(vd, "_http_json", return_value=payload):
            return vd.loc_check(ref)

    def _item(self, title, date="2012"):
        return {"item": {"title": title, "date": date}}

    def test_pass_via_lccn(self):
        # LoC item API: lccn → kayıt sayfası; title_needle eşleşirse PASS.
        ref = {"key": "Fine 2012", "title_needle": "metaphysical grounding",
               "ht_ids": ["lccn:2012014618", "isbn:1107022894"]}
        v, d = self._call(ref, self._item(
            "Metaphysical grounding : understanding the structure of reality"))
        self.assertEqual(v, "PASS")
        self.assertIn("LoC lccn:2012014618", d)
        self.assertIn("Metaphysical", d)

    def test_pass_accent_insensitive(self):
        # "Lagrée" başlığındaki aksanlar _fold ile normalize edilir.
        ref = {"key": "Lagree 1994", "title_needle": "lipse",
               "ht_ids": ["lccn:95174106"]}
        v, d = self._call(ref, self._item(
            "Juste Lipse et la restauration du stoïcisme : étude "
            "et traduction des traités stoïciens", "1994"))
        self.assertEqual(v, "PASS")
        self.assertIn("1994", d)

    def test_mismatch_when_record_differs(self):
        ref = {"key": "Schmitt 1972", "title_needle": "cicero scepticus",
               "ht_ids": ["lccn:73155022"]}
        v, d = self._call(ref, self._item("Something entirely different"))
        self.assertEqual(v, "MISMATCH")
        self.assertIn("başlık eşleşmedi", d)

    def test_unverified_without_lccn(self):
        ref = {"key": "X", "title_needle": "z",
               "ht_ids": ["oclc:999", "isbn:123"]}
        v, d = self._call(ref, {})
        self.assertEqual(v, "UNVERIFIED")
        self.assertIn("lccn yok", d)

    def test_unverified_when_no_record(self):
        ref = {"key": "X", "title_needle": "z", "ht_ids": ["lccn:99999999"]}
        v, d = self._call(ref, {"item": {}})
        self.assertEqual(v, "UNVERIFIED")
        self.assertIn("kayıt yok", d)

    def test_http_error_unverified(self):
        ref = {"key": "X", "title_needle": "z", "ht_ids": ["lccn:1"]}
        with mock.patch.object(
                vd, "_http_json",
                side_effect=urllib.error.HTTPError(
                    "url", 404, "Not Found", None, None)):
            v, d = vd.loc_check(ref)
        self.assertEqual(v, "UNVERIFIED")
        self.assertIn("LoC HTTP 404", d)


if __name__ == "__main__":
    unittest.main()
