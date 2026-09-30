#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_next_live_stream.py — /trend sayfası YÜKLEMEDEN GÜNCELLENİR
mi? (ölçüm)

İddia: preview_server'ın SSE verisi panoya akarken verdict/kosu tablosu
yenileme olmadan değişir. Bu test iddiayı ÖLÇER, varsaymaz:

  1. SSE tüneli gerçekten akıyor mu?      (yoksa statik tablo sessizce
                                          "canlı" görünür — vakum riski)
  2. Upstream değişince DOM GERÇEKTEN değişiyor mu, YENİDEN YÜKLENMEDEN mi?
     → `window.__marker` + `performance.timeOrigin` korunuyor mu? Aynı
       teknik `test_soft_nav_preserves_window_marker_across_routes` ile.

Fixture = SAYAN + YAYINLAYAN upstream (stdlib). Gerçek preview_server
kullanılmaz: onun SSE'i kendi doğrulama döngüsüne bağlı ve bir test içinden
zamanlanamaz. Buradaki upstream preview_server'ın `/api/run` ÇERÇEVE
SÖZLEŞMESİNİ birebir taklit eder (ölçüldü, preview_server.py serve_sse):

    event: snapshot   → bağlantı anında tam `_public_snapshot(LATEST)`
    event: update     → her LATEST güncellemesinde
    : keepalive       → boşta kalınca periyodik yorum

Bu yüzden test, üretimde gerçekten kullanılan çerçeve biçimine bağlıdır:
biçim değişirse tünel sessizce bozulur ve test KIRMIZI olur.

Çalıştırma:
    python3 -m pytest _calisma/CIKTI/test_dashboard_next_live_stream.py
    python3 -m unittest _calisma.CIKTI.test_dashboard_next_live_stream

EXCLUDE'dadır (Next boot + Chromium). CI `dashboard-next` job'ında koşar.
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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

NEXT = os.path.join(REPO_ROOT, "apps", "dashboard-next")
NEXT_BIN = os.path.join(NEXT, "node_modules", ".bin", "next")
BUILD_ID = os.path.join(NEXT, ".next", "BUILD_ID")


def _next_missing():
    """`next start` için ön koşullar: binary + derlenmiş pano.

    Aynı sözleşme `test_dashboard_next_battery_smoke.py`de ölçülüyor; canlı
    katmanı olan her suite aynı "eksikse SKIP" kuralını paylaşmalı.
    """
    if not os.path.isfile(NEXT_BIN):
        return "apps/dashboard-next/node_modules yok (npm ci gerekli)"
    if not os.path.isfile(BUILD_ID):
        return "apps/dashboard-next/.next derlemesi yok (next build gerekli)"
    return ""


sys.path.insert(0, HERE)
import test_dashboard_cls_budget as cwv_core  # noqa: E402
import test_surface_cwv_report as cwv  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Chromium'sız ortam
    sync_playwright = None

# Sentetik koşum damgalarının tabanı — sabit, saat dilimi açık, tekrarsız.
_EPOCH = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _ts(index):
    """`index`'ten ARTFECA ve TEKIL bir koşum damgası üretir.

    Neden sentetik seri (eskiden `2026-09-2%d` + `index % 10` idi): o seri
    10 satırda bir DÖNÜYORDU. Pencere 20'yi aştığında "en yeni" satır
    göstergeceğine en eskiye sarıyor, yani pencere testi KENDİ ÖLÇTÜĞÜ
    hatayı gizliyordu (bkz. `windowRows`: `slice(-limit).reverse()`).
    Sıra sözleşmesi yalnız TEKIL ve ARTFECA damgalarla gözlenebilir.
    """
    return (_EPOCH + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(index):
    return {
        "ts": _ts(index),
        "p0": 0, "p1": 0, "duration_s": 300.0 + index,
        "budget_usd": 12.0, "z3_total": 5,
    }


class _QuietServer(ThreadingHTTPServer):
    """Tarayıcı SSE bağlantısını kapattığında `ConnectionResetError` yükselir.
    Bu GÜRÜLTÜDÜR (sözleşmenin ta kendisi: akış kesilince bağlantı düşer), ama
    iz bırakırsa süit çıktısı gerçek hatalardan ayırt edilemez."""

    def handle_error(self, request, client_address):
        pass


# Panel gözlem noktası — iki kartın durumunu TEK `evaluate`de okur.
#
# Seçici SINIF ADINA değil BÖLÜM BAŞLIĞINA dayanır (`PanelCardTitle` gerçek
# `<h2>` basar): bir kartın sınıfı yeniden adlandırılsa ölçüm sessizce
# başka kartı okumaz, semantik değişirse (başlık metni) KIRILIR. Kart, başlıktan
# yukarı doğru "içinde `p[role=status]` barındıran ilk ata"dır.
#
# `status` alanı canlılık göstergesidir: `RunsTable` bağlanınca
# "canlı · VERDICT", `VerdictCard` ise doğrudan verdict metnini basar — yani
# ikisi karşılaştırılabilir.
_PANEL_STATE_JS = """
({verdictTitle, trendTitle}) => {
  const cardOf = (title) => {
    if (title == null) return null;
    const h2 = [...document.querySelectorAll('h2')]
      .find(e => e.textContent.trim() === title);
    if (!h2) return null;
    let el = h2;
    while (el && !el.querySelector("p[role='status']")) el = el.parentElement;
    return el;
  };
  const pick = (card) => {
    if (!card) return null;
    const status = card.querySelector("p[role='status']");
    const rows = [...card.querySelectorAll('tbody tr')];
    return {
      status: status ? status.textContent.trim() : null,
      row_count: rows.length,
      row_stamps: rows.map(r => {
        const t = r.querySelector('time');
        return t ? t.getAttribute('datetime') : null;
      }),
    };
  };
  return {
    verdict: pick(cardOf(verdictTitle)),
    trend: pick(cardOf(trendTitle)),
  };
}
"""


class BroadcastUpstream:
    """preview_server'ın SSE sözleşmesini taklit eden, testten kumanda edilen
    upstream. `push()` hem trend geçmişini büyütür hem SSE yayınlar."""

    def __init__(self, rows=2):
        self._rows = [_row(i) for i in range(rows)]
        self._next = rows
        self._verdict = "PASS"
        self._lock = threading.Lock()
        self._sse_clients = []
        self.sse_connections = Counter()

        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path == "/api/run":
                    outer._serve_sse(self)
                    return
                if path == "/api/trend":
                    self._json({"history": outer.rows()})
                    return
                if path == "/api/latest":
                    self._json(outer.snapshot())
                    return
                self._json({}, status=404)

            def do_POST(self):  # noqa: N802 — TEST kumandası
                if self.path.split("?", 1)[0] == "/__test/push":
                    outer.push()
                    self._json({"ok": True})
                    return
                self._json({}, status=404)

            def _json(self, body, status=200):
                raw = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.port = cwv_core.free_port()
        self._server = _QuietServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def rows(self):
        with self._lock:
            return list(self._rows)

    def newest(self):
        with self._lock:
            return dict(self._rows[-1]) if self._rows else {}

    def count(self):
        with self._lock:
            return len(self._rows)

    def snapshot(self):
        """`/api/latest` — preview_server'ın `_public_snapshot(LATEST)` taklidi.

        ÖNEMLİ: snapshot EN YENİ trend satısını tarif eder. Gerçek sistemde
        `LATEST` ile `history`'nin son satırı AYNI koşumdur; sabit bir
        `ts`/`verdict` basmak fixture'ı kendi içinde tutarsız yapardı ve
        "verdict paritesi" ölçümü anlamını yitirirdi (her zaman "uyuşur",
        hiçbir şey ölçmez).
        """
        newest = self.newest()
        return {
            "verdict": self._verdict,
            "ts": newest.get("ts"),
            "p0": newest.get("p0", 0),
            "p1": newest.get("p1", 0),
            "budget_usd": newest.get("budget_usd", 12.0),
            "budget_limit": 30.0,
            "z3_passed": newest.get("z3_total", 5),
            "z3_total": newest.get("z3_total", 5),
        }

    def push(self):
        """Yeni koşum ekle + TÜM bağlı SSE istemcisine `event: update` yayınla."""
        with self._lock:
            self._rows.append(_row(self._next))
            self._next += 1
            # Verdict de değişir: sabit verdict ile parite testi "her zaman
            # uyuşuyor" sanabilirdi. Gerçek preview_server da LATEST'i her
            # koşumda yeniden türetir.
            self._verdict = "FAIL" if self._verdict == "PASS" else "PASS"
            clients = list(self._sse_clients)
        frame = ("event: update\ndata: %s\n\n"
                 % json.dumps(self.snapshot())).encode("utf-8")
        for wfile in clients:
            try:
                wfile.write(frame)
                wfile.flush()
            except OSError:
                pass

    def _serve_sse(self, handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        snapshot = ("event: snapshot\ndata: %s\n\n"
                    % json.dumps(self.snapshot())).encode("utf-8")
        handler.wfile.write(snapshot)
        handler.wfile.flush()
        with self._lock:
            self._sse_clients.append(handler.wfile)
            self.sse_connections["/api/run"] += 1
        try:
            # Test süresince açık tut; istemci ayrılınca yazma hata verir ve
            # döngü `finally` ile listeyi temizler.
            while True:
                threading.Event().wait(0.5)
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
        except OSError:
            pass
        finally:
            with self._lock:
                if handler.wfile in self._sse_clients:
                    self._sse_clients.remove(handler.wfile)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


@unittest.skipIf(sync_playwright is None, "Playwright/Chromium yok")
class _NextPanelE2E(unittest.TestCase):
    """Ortak kurulum: yayınlayan upstream + `next start` + panel gözlemi.

    Kablo TEK kaynaktan gelir (`cwv_core.free_port` / `cwv_core.wait_for_port`
    / `cwv.spawn_next_server` / `cwv.terminate`) — sunucu kablolaması ikinci
    kez yazılmaz. Somut sınıflar yalnız satır SAYISI ve pencere/panel
    iddiasını değiştirir.
    """

    # Upstream kaç satırla açılacak. Pencere ölçümü 20'den fazla ister
    # (aksi halde "kırpma" ölçülemez); canlı-akış ölçümü 2 ile yeter.
    UPSTREAM_ROWS = 2

    upstream = None
    next_proc = None

    @classmethod
    def setUpClass(cls):
        # `next start` yalnızca derlenmiş panoyla ayağa kalkar; CI'ın birim test
        # adımı `npm ci`/`next build` çalıştırmaz. Ön koşul yoksa SKIP —
        # setUpClass içinde RuntimeError raise etmek testi ERROR yapıyordu
        # (yani eksik ortam "kapı kırık" gibi görünüyordu).
        missing = _next_missing()
        if missing:
            raise unittest.SkipTest("canlı katman atlandı: %s" % missing)
        cls._tmp = tempfile.mkdtemp(prefix="next_live_")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, True)
        cls.upstream = BroadcastUpstream(rows=cls.UPSTREAM_ROWS)
        cls.addClassCleanup(cls.upstream.stop)
        port = cwv_core.free_port()
        cls.next_proc = cwv.spawn_next_server(
            port, cls.upstream.url, os.path.join(cls._tmp, "next_start.log"))
        cls.addClassCleanup(cwv.terminate, cls.next_proc)
        if not cwv_core.wait_for_port("127.0.0.1", port, timeout=30):
            raise RuntimeError("next start ayağa kalkmadı")
        cls.base = "http://127.0.0.1:%d" % port

    def _push(self, times=1):
        for _ in range(times):
            req = urllib.request.Request(
                self.upstream.url + "/__test/push", method="POST", data=b"")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()

    def _stamps(self, page):
        return page.eval_on_selector_all(
            "time", "els => els.map(e => e.getAttribute('datetime'))")

    def _panel(self, page, verdict_title, trend_title):
        """İki kartın durumunu TEK gözlemde oku (bkz. `_PANEL_STATE_JS`)."""
        return page.evaluate(_PANEL_STATE_JS, {
            "verdictTitle": verdict_title, "trendTitle": trend_title})

    def _wait_live(self, page, timeout=20000):
        """Akışın BAĞLANDIĞINI bekle.

        Tuzağa dikkat: eski ölçüm `/canlı/` diye bekliyordu. Bu desen
        BAĞLANMAMIŞ göstergenin kendi metniyle eşleşir —
        `RunsTable` bağlanmadan önce "canlı bağlantı bekleniyor" basar, o
        metinde "canlı" vardır. Yani bekleme "bağlandı" anını değil
        "bağlanmadı" anını yakalıyordu (ölçüldü 2026-09-28: verdict-parite
        testi bununla "canlı bağlantı bekleniyor"u okuyup düştü). Doğru
        ölçüt BAĞLI + verdict basılmış hâli: "canlı · VERDICT".
        """
        page.wait_for_function(
            "() => /canlı ·/.test(document.body.innerText)", timeout=timeout)


class LiveStreamTest(_NextPanelE2E):
    UPSTREAM_ROWS = 2


    def test_trend_updates_in_place_without_reload(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + "/trend", wait_until="domcontentloaded")

                # SSR ilk pencere dolu mu + canlılık göstergesi?
                page.wait_for_function(
                    "() => document.querySelectorAll('time').length >= 2",
                    timeout=20000)
                before = self._stamps(page)
                self.assertGreaterEqual(
                    len(before), 2,
                    "SSR ilk pencere boş — tablo sunucuda dolu basılmalı")

                # Yayınlayıcı bağlı mı? (tünel açılmazsa hiç güncelleme olmaz)
                self._wait_live(page)

                # YENİDEN YÜKLEME olmadığını kanıtlamak için işaret:
                # sayfa yaşamı boyunca korunmalı (aynı desen:
                # test_soft_nav_preserves_window_marker_across_routes).
                page.evaluate("() => { window.__liveMarker = 42; }")
                origin_before = page.evaluate("() => performance.timeOrigin")

                # Upstream'i değiştir + SSE yayınla.
                self._push()

                page.wait_for_function(
                    "n => document.querySelectorAll('time').length > n",
                    arg=len(before), timeout=20000)
                after = self._stamps(page)
                marker = page.evaluate("() => window.__liveMarker")
                origin_after = page.evaluate("() => performance.timeOrigin")

                self.assertGreater(
                    len(after), len(before),
                    "yayın sonrası satır sayısı artmadı — akış bağlı değil")
                self.assertNotEqual(after, before,
                                    "DOM güncellenmedi")
                self.assertEqual(
                    marker, 42,
                    "window.__liveMarker kayboldu → SAYFA YENİDEN YÜKLENDİ "
                    "(hedef: yenilemeden güncelleme)")
                self.assertEqual(
                    origin_after, origin_before,
                    "performance.timeOrigin değişti → tam sayfa yeniden yüklendi")
            finally:
                browser.close()

    def test_upstream_sse_was_actually_connected(self):
        """Vakum denetimi: tünel gerçekten upstream'e bağlandı mı?

        SSE bağlantısı hiç kurulmadıysa `test_trend_updates_in_place_*`
        sessizce "hiçbir şey değişmedi" diye geçebilir. Bu, ölçümün
        kendisinin çalıştığını sabitler.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + "/trend", wait_until="domcontentloaded")
                self._wait_live(page)
            finally:
                browser.close()
        self.assertGreaterEqual(
            self.upstream.sse_connections["/api/run"], 1,
            "upstream /api/run hiç bağlanmadı — tünel ölçülmüyor")

    def test_verdict_panel_and_live_trend_describe_the_same_run(self):
        """Panonun İKİ kartı aynı koşumu tarif etmeli.

        `VerdictCard` sunucu tarafında `/api/latest`'ten, `RunsTable`
        `/api/trend`'ten beslenir — İKİ AYRI uç. Parite bozulursa pano
        "Son Koşum: PASS" derken tabloda üç saat önceki koşumu gösterir;
        ve bu çelişki HİÇBİR mevcut katmanda görünmez, çünkü her kart
        ayrı ayrı doğrudur (statik sözleşme testleri de yeşil kalır).
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + "/", wait_until="domcontentloaded")
                self._wait_live(page)
                state = self._panel(page, "Son Koşum", "Son 5 Koşum")

                self.assertIsNotNone(state["verdict"],
                                     "verdict kartı (Son Koşum) bulunamadı")
                self.assertIsNotNone(state["trend"],
                                     "trend kartı (Son 5 Koşum) bulunamadı")
                self.assertGreater(
                    state["trend"]["row_count"], 0,
                    "trend tablosu boş — parite ölçülemiyor")

                # 1) KOŞUM KİMLİĞİ paritesi: verdict kartının damgası, tablonun
                #    EN YENİ satırıyla aynı olmalı. `history` eskiden-yeniye
                #    gelir, tablo ters çevirir → ilk satır en yenidir.
                newest = self.upstream.newest()["ts"]
                self.assertEqual(
                    newest, state["trend"]["row_stamps"][0],
                    "verdict kartı ile trend tablosu FARKLI koşumu tarif "
                    "ediyor (upstream'in en yenisi=%s, tablodaki en yeni=%s)"
                    % (newest, state["trend"]["row_stamps"][0]))

                # 2) VERDICT METNİ paritesi: canlı tablonun göstergesi
                #    "canlı · VERDICT" basar; kart doğrudan verdict'i basar.
                self.assertEqual(
                    state["trend"]["status"],
                    "canlı · %s" % state["verdict"]["status"],
                    "canlı göstergenin verdict'i kartla uyuşmuyor "
                    "(gösterge=%r kart=%r)"
                    % (state["trend"]["status"], state["verdict"]["status"]))

                # 3) AKIŞ İLERİYOR: yayın geldikten sonra tablo öne geçmeli.
                #    Geriye kayması, tekrarlanan/bayat bir olayın tünelden
                #    sızdığı anlamına gelir.
                before = state["trend"]["row_stamps"][0]
                self._push()
                page.wait_for_function(
                    "prev => { const r = document.querySelector('tbody tr "
                    "time'); return !!r && "
                    "r.getAttribute('datetime') !== prev; }",
                    arg=before, timeout=20000)
                after = self._panel(page, "Son Koşum", "Son 5 Koşum")
                self.assertGreater(
                    after["trend"]["row_stamps"][0], before,
                    "yayın sonrası tablo ÖNE GEÇMEDİ (akış geriye kaydı ya da "
                    "bağlı değil): %s → %s"
                    % (before, after["trend"]["row_stamps"][0]))
            finally:
                browser.close()


class TrendWindowTest(_NextPanelE2E):
    """`/trend` PENCERESİ: tam 20 satır, en yeniler — hem SSR hem canlı yolda.

    Ayrı sınıf + ayrı upstream ÇÜNKÜ ölçümün kendisi 20'den fazla satır
    ister. Aynı upstream'i paylaşsaydı canlı-akış sınıfının "yayın sonrası
    satır SAYISI arttı" ölçümü bozulurdu (pencere 20'de doyduğu için sayı
    artmaz). İki ölçüm birbirinin fixture'ını bozmamalı.
    """

    UPSTREAM_ROWS = 25  # 20'nin üstü: kırpma ancak burada GÖRÜNÜR

    def test_trend_page_renders_exactly_twenty_newest_rows(self):
        """Pencere `limit=20`'dir: 25 satırdan tam 20'si, en yenisi üstte.

        İki ayrı hata bu ölçümü kırar ve ikisi de SESSİZ'dir:
          * kırpma yok  → tablo upstream'in tamamını basar (limit ölü kod);
          * ters sıra   → "son 20" başlığı en ESKİ 20'yi gösterir.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + "/trend", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=20000)
                self._wait_live(page)

                state = self._panel(page, None, "Son 20 Koşum")
                self.assertIsNotNone(state["trend"], "trend kartı bulunamadı")
                self.assertEqual(
                    state["trend"]["row_count"], 20,
                    "upstream %d satır taşıyordu ama tablo %d satır basıyor — "
                    "pencere (limit=20) uygulanmıyor ya da yanlış uygulanıyor"
                    % (self.upstream.count(), state["trend"]["row_count"]))
                self.assertEqual(
                    state["trend"]["row_stamps"][0], self._newest_ts(),
                    "ilk satır upstream'in EN YENİSİ değil — sıra ters "
                    "(en eski 20 'son 20' diye gösteriliyor)")
                self._assert_descending(state["trend"]["row_stamps"],
                                        "SSR ilk boya")

                # Canlı yol da aynı pencere sözleşmesini tutmalı: yayın
                # geldikçe satır sayısı 20'de DOYMALI, en yeni kaydıp
                # yerine geçmeli.
                oldest_before = state["trend"]["row_stamps"][-1]
                self._push(times=3)
                page.wait_for_function(
                    "expected => { const r = document.querySelector('tbody tr "
                    "time'); return !!r && "
                    "r.getAttribute('datetime') === expected; }",
                    arg=self._newest_ts(), timeout=20000)

                live = self._panel(page, None, "Son 20 Koşum")
                self.assertEqual(
                    live["trend"]["row_count"], 20,
                    "canlı yolda pencere TAŞTI — 3 yayından sonra %d satır. "
                    "Tünel upstream'in tüm geçmişini gönderiyor, istemci "
                    "kırpmıyor." % live["trend"]["row_count"])
                self.assertEqual(
                    live["trend"]["row_stamps"][0], self._newest_ts(),
                    "canlı tabloda en yeni satır güncel değil")
                self._assert_descending(live["trend"]["row_stamps"],
                                        "canlı pencere")
                self.assertNotIn(
                    oldest_before, live["trend"]["row_stamps"],
                    "pencere KAYMADI — aynı 20 satır hâlâ basılıyor, yeni "
                    "koşumlar görünmüyor")
            finally:
                browser.close()

    def _newest_ts(self):
        return self.upstream.newest()["ts"]

    def _assert_descending(self, stamps, where):
        """Sıra sözleşmesi: en yeniden en eskiye, TEKİL ve ARTFECA."""
        self.assertGreater(len(stamps), 1, "%s: tek satır var" % where)
        for newer, older in zip(stamps, stamps[1:]):
            self.assertGreater(
                newer, older,
                "%s: sıra yeni→eski değil (veya damga tekrarlı): %s"
                % (where, stamps))


if __name__ == "__main__":
    unittest.main()
