#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_next_request_dedup.py — istek-basi dedup SÖZLEŞMESİ.

`b156cb4` (perf: per-request dedup via React.cache) iddiası "proven live: 2
consumers -> 1 upstream hit with a counting probe" idi ve o prob TEK ATILDIK
bir ölçümdü. Bu dosya onu kalıcı sözleşmeye çevirir: SAYAN upstream ayağa
kalkar, derlenmiş pano `next start` ile sunulur, render başına upstream istek
sayısı ÖLÇÜLÜR.

=====================================================================
ÖLÇÜM İKİ ŞEYİ DÜZELTTİ — TEST BUNDAN SONRA YAZILDI
=====================================================================

(1) "2 tüketici" BUGÜN PANODA YOK.
    `getLatest` → tek tüketici: `app/VerdictCard.tsx` (yalnız `@verdict`).
    `getTrend`  → iki çağrı yeri VAR ama ARGÜMAN FARKLI: `getTrend(20)`
    (`app/trend/page.tsx`) ve `getTrend(5)` (`@trend/page.tsx`). React
    `cache()` argümana göre anahtarlandığı için bunlar AYRI girdidir —
    dedup örneği değildir.

(2) ÖNEMLİ: `cache()` DEDUP'IN MEKANİZMA DEĞİL — ÖLÇÜLDÜ, ÇÜRÜTÜLDÜ.
    b156cb4'ün gerekçesi: "fetch request-memoization cache:no-store
    istekleri kapsamaz; cache() bu boşluğu kapatır."
    Bu, Next 16.3.6 ÜZERİNDE YANLIŞ. Mutasyon deneyi (ölçüldü):

        2 × <VerdictCard />  +  cache() VAR    → /api/latest : 1  ✔
        2 × <VerdictCard />  +  cache() YOK    → /api/latest : 1  ✔  ← !!

    Yani `cache()` olmasa da upstream'e TEK istek gidiyor; çerçeve kendi
    `fetch` ini istek kapsamında birleştiriyor. Sonuç: "2 tüketici → 1
    istek" gözlemi DOĞRU, ama ona atfedilen mekanizma DEĞİL.

    Testin tasarımını bu BELİRLER:
      * Test, `cache()` varlığını DENETLEMEZ. Yokluğu davranışı değiştirmediği
        için onu "sözleşme" diye yazmak yanlış güvence verirdi — kaldırıldığında
        kırılırken hiçbir şey bozulmamış olurdu (ölçüldü: kırıldı, davranış
        aynı kaldı).
      * Test, ölçülen DAVRANIŞI tutar: render başına istek sayısı, istek
        kapsamı, ve dikiş kümesi. Bunlar gerçekten kırılabilir.

Çalıştırma (dosya hem pytest hem unittest tarafından toplanır):
    python3 -m pytest _calisma/CIKTI/test_dashboard_next_request_dedup.py
    python3 -m unittest _calisma.CIKTI.test_dashboard_next_request_dedup

Sunucu kablosu TEK kaynaktan: `free_port` / `spawn_next_server` /
`terminate` `test_dashboard_cls_budget` + `test_surface_cwv_report`'ten
import edilir (ikinci bir başlatma hattı drift üretirdi).

Dosya `check_unit_tests.list` DIŞINDA (sync_check_unit_tests.EXCLUDE):
`next start` boot'u dosya başına bütçeyi aşar; CI'da derlemenin zaten
yapıldığı `dashboard-next` job'ı koşar. Tarayıcı GEREKMEZ — yalnız HTTP.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

sys.path.insert(0, HERE)
import test_dashboard_cls_budget as cwv_core  # noqa: E402
import test_surface_cwv_report as cwv  # noqa: E402

# Panonun upstream'e okuduğu veri dikişleri. Test bunları isim sabitiyle
# değil, ÖLÇÜMLE doğrular: upstream'e giden isteklerin yol kümesi sayılır.
# Yeni bir dikiş eklenirse küme değişir ve `test_panel_touches_exactly_the_
# expected_upstream_seams` kırılır — sessiz upstream yükü artışı yakalanır.
EXPECTED_SEAMS = frozenset({"/api/latest", "/api/trend"})

LATEST_PAYLOAD = {
    "verdict": "PASS", "ts": "2026-09-28T16:00:00Z", "p0": 0, "p1": 0,
    "z3_passed": 5, "z3_total": 5, "z3_failed": 0,
    "budget_usd": 12.4, "budget_limit": 30.0, "stripped_sha256": "a" * 64,
}
TREND_PAYLOAD = {"history": [
    {"ts": "2026-09-2%dT10:00:00Z" % i, "p0": 0, "p1": 0,
     "duration_s": 300.0 + i, "budget_usd": 12.0, "z3_total": 5}
    for i in range(1, 6)]}


class CountingUpstream:
    """İstek SAYAN upstream. stdlib; ağ dışına çıkmaz.

    Sayım `(path, query)` çiftinde tutulur: React `cache()` argümana göre
    anahtarlandığı için sorgu dizesi ayrımı önemlidir
    (`/api/trend?limit=5` ile `?limit=20` FARKLI önbellek girdisidir).
    `seam_totals()` dikiş başına toplar, `paths()` ham çiftleri verir.
    """

    def __init__(self):
        self._hits = Counter()
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802 — stdlib arayüz adı
                outer.record(self.path)
                body = (LATEST_PAYLOAD if self.path.startswith("/api/latest")
                        else TREND_PAYLOAD if self.path.startswith("/api/trend")
                        else {})
                raw = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass  # test çıktısını gürültüyle doldurma

        self.port = cwv_core.free_port()
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def record(self, raw_path):
        with self._lock:
            self._hits[raw_path] += 1

    def reset(self):
        with self._lock:
            self._hits.clear()

    def counts(self):
        with self._lock:
            return Counter(self._hits)

    def seam_totals(self):
        """{seam yolu: toplam istek}."""
        totals = Counter()
        for raw, n in self.counts().items():
            totals[raw.split("?", 1)[0]] += n
        return totals

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


class RequestDedupTest(unittest.TestCase):
    """Canlı: sayan upstream + derlenmiş `next start`."""

    upstream = None
    next_proc = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="next_dedup_")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, True)
        cls.upstream = CountingUpstream()
        cls.addClassCleanup(cls.upstream.stop)
        next_port = cwv_core.free_port()
        log = os.path.join(cls._tmp, "next_start.log")
        cls.next_proc = cwv.spawn_next_server(next_port, cls.upstream.url, log)
        cls.addClassCleanup(cwv.terminate, cls.next_proc)
        if not cwv_core.wait_for_port("127.0.0.1", next_port, timeout=30):
            raise RuntimeError(
                "next start 30 sn içinde ayağa kalkmadı — log: %s" % log)
        cls.base = "http://127.0.0.1:%d" % next_port

    def _render(self, path):
        """Sayfayı GET eder; (http_kodu, dikiş_sayıları) döner."""
        self.upstream.reset()
        with urllib.request.urlopen(self.base + path, timeout=30) as resp:
            code = resp.status
            resp.read()
        return code, self.upstream.seam_totals()

    def test_panel_render_hits_each_data_seam_exactly_once(self):
        """Ana sözleşme: `/` render'ı her dikiş için TAM BİR upstream isteği.

        Render'da `@verdict` slotu `getLatest()`, `@trend` slotu `getTrend()`
        çağırır. Panoda N+1 (bileşen sayısıyla orantılı istek) başlarsa bu
        test kırılır — tüketici sayısı bugün 1 olsa bile yakaladığı gerçek
        regresyon sınıfı budur.
        """
        code, seams = self._render("/")
        self.assertEqual(code, 200, "panel 200 dönmeli")
        self.assertIn("/api/latest", seams, "verdict dikişi hiç çağrılmadı")
        self.assertIn("/api/trend", seams, "trend dikişi hiç çağrılmadı")
        self.assertEqual(seams["/api/latest"], 1,
                         "getLatest için 1 upstream isteği beklenir, "
                         "ölçülen: %s" % dict(seams))
        self.assertEqual(seams["/api/trend"], 1,
                         "getTrend için 1 upstream isteği beklenir, "
                         "ölçülen: %s" % dict(seams))
        self.assertEqual(sum(seams.values()), 2,
                         "panel render'ı toplamda tam 2 upstream isteği "
                         "atmalı (her dikiş 1): %s" % dict(seams))

    def test_dedup_is_per_request_not_per_process(self):
        """Önbellek İSTEK-BAŞINADIR — süreç geneli değil.

        İki ayrı render iki ayrı upstream isteği ÜRETMELİDİR. Tek istek
        görülürse biri süreç geneli (ve bu yüzden bayatlayan) önbellek
        koymuş olabilir — pano uygulama yeniden başlatılana kadar eski
        verdict'i göstermeye devam eder. Sessiz bir doğruluk hatasıdır ve
        yalnız bu test yakalar.
        """
        self._render("/")
        code, second = self._render("/")
        self.assertEqual(code, 200)
        self.assertEqual(second["/api/latest"], 1,
                         "ikinci render kendi isteğini atmalı (süreç geneli "
                         "önbellek olsaydı 0 olurdu): %s" % dict(second))

    def test_panel_touches_exactly_the_expected_upstream_seams(self):
        """Dikiş KÜMESİ sabittir — beklenmeyen upstream trafiği yok.

        Yeni bir veri dikişi eklenirse (ör. ikinci bir API, bir sayfa URL'si)
        upstream yükü sessizce artar ve istek-sayısı testleri onu tek tek
        yakalamaz. Küme denetimi genişlemeyi görünür kılar.
        """
        self._render("/")
        seen = set(self.upstream.seam_totals())
        self.assertEqual(seen, set(EXPECTED_SEAMS),
                         "panel upstream'e beklenmeyen bir yüzeye dokunuyor "
                         "(ya da bir dikiş kayboldu): gözlenen=%s beklenen=%s"
                         % (sorted(seen), sorted(EXPECTED_SEAMS)))

    def test_counting_upstream_saw_real_traffic(self):
        """Vakum (anti-boşluk) denetimi: sayaç gerçekten trafik gördü mü?

        Sayaç sessizce sıfır kalırsa "1 istek" iddiası hiçbir şey ÖLÇMEZ
        (ör. pano upstream'i hiç çağırmıyorsa, ya da render hata sınırında
        kalıp kartı basmıyorsa). Bu test sayacın boş kalmadığını sabitler —
        aksi halde bu dosyadaki üç test de sahte yeşil olurdu.
        """
        code, _ = self._render("/")
        self.assertEqual(code, 200)
        counts = self.upstream.counts()
        self.assertTrue(counts,
                        "upstream hiç istek almadı — ölçüm geçersiz (sayaç "
                        "kolu çalışmıyor ya da pano veri çekmiyor)")
        for raw in counts:
            self.assertTrue(raw.startswith("/api/"),
                            "sayılan istek beklenen API yüzeyinde değil: %s"
                            % raw)


if __name__ == "__main__":
    unittest.main()
