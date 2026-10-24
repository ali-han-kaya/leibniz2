#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_screenshot_gate.py — dashboard YAKALANABİLİRLİK kapısı (Playwright, fail-closed).

İDDİA (üç parça, birlikte anlamlı):
  1. Dashboard açılışında akan SSE replay patlaması sürerken ve sonrasında
     sayfa KARE ÜRETMEYE DEVAM EDER: en uzun requestAnimationFrame boşluğu
     yakalama bütçesini AŞMAZ.
  2. Sayfa GERÇEKTEN PNG olarak yakalanabilir — `page.screenshot()` boş kare
     döndürmez (imza + boyut + DOM değişiminden sonra DEĞİŞEN baytlar).
  3. Replay patlaması sayfaya GERÇEKTEN ulaşmıştır ve client penceresine
     (STREAM_MAX) sığar — yani "ölçüm yapıldı ama sayfa boştu" yanılsaması yok.

Neden bu dosya var: PREVIEW-1 (docs/KNOWN_INCIDENTS.md) — canlı `preview_screenshot`
aracı "it produced no frames, which means the preview webview is not being
composited" ile düştü. Electron tarafında `capturePage` tazelenmiş bir
kompozitör karesi bekler; kare bütçesi dolduğunda çağrı asılı kalır ve
YUKARIDAKİ METİN üretilir (asar: SCREENSHOT_FRAME_ATTEMPT_MS = 2000 ms).
Yani arızanın sayfa tarafındaki bileşeni "ana iş parçacığı kare üretemiyor"
durumudur. Bu repoda o bileşeni ölçen hiçbir kapı yoktu: a11y/CLS/CWV
adımları erişilebilirlik ve layout ölçer, hiçbiri KARE ÜRETİMİNİ ölçmez.
Bu dosya o boşluğu kalıcı kapıya çevirir.

⚠️ SINIR (ölçülen, saklanmayan): bu kapı HEADLESS CHROMIUM'un kompozisyonunu
ölçer; arızanın Electron guest-webview tarafını (OS penceresi occlusion'ı,
GPU süreci, host compositor) KANITLAMAZ. Chromium'da yakalanamayan bir sayfa
burada da yakalanmaz olabilir; ama sayfa tarafı kare üretimini durduran
regresyon (ör. satır-başı DOM yazımına dönüş — QA bulgusu F4) burada kızar.
Electron tarafı için doğru araç `preview_screenshot`tır, bu dosya değil.

Fail-closed guard'lar (boş bir "PASS" yanılsamasına karşı):
  * CAPTURE_GATE_REQUIRE_LIVE=1 (CI) iken canlı katman ATLANAMAZ — Chromium
    kurulumu atlanırsa all-skip PASS değil FAIL.
  * Kare sayısı eşiğin altındaysa FAIL — "produced no frames" tam olarak budur.
  * Bütçe/ölçüm anlamsızsa (kare yok, zaman damgası NaN/geriye gidiyor,
    bütçe sayısal değil) FAIL.
  * Yakalama hata verirse (timeout/dahili hata) FAIL — yutulmaz.
  * PNG imzası/boyutu şüpheliyse FAIL (boş kare).
  * DOM değiştikten sonra yakalama DEĞİŞMEDİYSE FAIL — "kompozitör taze kare
    üretmiyor" iddiası; sabit/tek-renk kare bu iddiayı çürütür.
  * Replay patlaması sayfaya ulaşmadıysa FAIL (ölçüm boş sayfada yapılmış).
  * Negatif kontrol: ana iş parçacığı bilerek bütçeden uzun bloke edilir ve
    dedektörün bunu GÖRDÜĞÜ doğrulanır — yoksa "stall yok" sonucu ölü bir
    ölçümden de gelebilirdi.

Hedef sunucu (`test_dashboard_cls_budget.py` ile aynı sözleşme):
  - `DASHBOARD_BASE_URL` verilirse: o CANLI sunucu; erişilemezse FAIL.
  - Verilmezse: geçici bir preview dizini (preview.html + preview.js + token
    CSS kopyası + WORST-CASE run log fixture'ı) ile `preview_server.py`
    ücretsiz portta başlatılır — kendi kendine yeterli, CI-güvenli, kullanıcı
    önbelleğine YAZMAZ.

Env override'ları:
  DASHBOARD_BASE_URL      canlı sunucu tabanı (varsayılan: kendi sunucusunu başlat)
  DASHBOARD_THEME         dark | light (varsayılan: dark)
  CAPTURE_STALL_BUDGET_MS en uzun kare boşluğu bütçesi (varsayılan: 2000 —
                          uygulamanın kendi kare bütçesiyle aynı mertebe)
  CAPTURE_MIN_FRAMES      liveness tabanı (varsayılan: 20)
  CAPTURE_OBSERVE_MS      ölçüm penceresi (varsayılan: 6000)
  CAPTURE_REPORT_PATH     verilirse deterministik JSON rapor yazılır (CI artifact)

Çalıştırma:
  python3 _calisma/CIKTI/test_preview_screenshot_gate.py            # spawn
  DASHBOARD_BASE_URL=http://127.0.0.1:8010 \\
    python3 _calisma/CIKTI/test_preview_screenshot_gate.py          # canlı
  CAPTURE_GATE_REQUIRE_LIVE=1 python3 ...                           # CI (skip yok)
  CAPTURE_GATE_TIER=unit python3 ...   # hızlı iç döngü (saf hesap, ~0.1 sn)

Katmanlar (CAPTURE_GATE_TIER): unit = CaptureMathTest (saf hesap),
integration = ReplayFixtureContractTest (sunucu kontratı + fixture),
e2e = PreviewCaptureGateTest (Chromium + sunucu + screenshot), all = hepsi.
"""

import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")
sys.path.insert(0, HERE)
import preview_server as ps  # noqa: E402  (RUN_LOG_MAX + gerçek replay üreticisi)

LIVE_BASE = (os.environ.get("DASHBOARD_BASE_URL") or "").strip() or None

# Varsayılan bütçe = Electron `capturePage` kare bütçesiyle aynı mertebe
# (SCREENSHOT_FRAME_ATTEMPT_MS = 2000). İddia: kare üretimi bundan uzun
# süre durmaz; tam 2000 ms FAIL eder (kesin küçüktür).
STALL_BUDGET_MS_DEFAULT = 2000.0
MIN_FRAMES_DEFAULT = 20
OBSERVE_MS_DEFAULT = 6000
THEME_DEFAULT = "dark"
VALID_THEMES = ("dark", "light")
PAGE_PATH = "/preview.html"

# Client sözleşmesi (preview.js): akış panelinde tutulan satır penceresi.
# Kapı bunu ÇİVLER: replay ne kadar büyürse büyüsün DOM'da bu kadar satır kalır.
STREAM_MAX_EXPECTED = 600
STREAM_MAX_SLACK = 20

# Şüpheli derecede küçük PNG = boş kare (tek-renk 1280x900 PNG ~2 kB altı).
MIN_PNG_BYTES = 2048
# İki yakalama arasında beklenen asgari bayt farkı (DOM değişimi sonrası).
MIN_CAPTURE_DELTA_BYTES = 64
# Yakalama çağrısının kendi zaman aşımı: asılı kalırsa test FAIL eder, CI
# sonsuza kadar beklemez (arızanın kendisi de "asılı kalma" biçimindedir).
CAPTURE_TIMEOUT_MS = 10000
# Negatif kontrolün bloke süresi (bütçenin en az ~2 katı olmalı).
NEGATIVE_CONTROL_BLOCK_MS = 3000

# Ölçülen gerçek patlama (2026-10-14, ~/Library/Caches/com.freebuff run logları,
# RUN_LOG_MAX=20): 2.03 MB / 18.732 replay olayı. Fixture BUNUN ALTINA düşmez —
# "fixture küçük olduğu için yeşil" yanılsamasını engeller.
MEASURED_BURST_EVENTS = 18732
MEASURED_BURST_BYTES = 2030000
FIXTURE_LINES_PER_RUN = 1000
FIXTURE_RUNS = None  # None → preview_server.RUN_LOG_MAX


# --------------------------------------------------------------- ölçüm JS
# Sayfa yüklenmeden ÖNCE kurulur (CDP init script). rAF kare damgalarını,
# akış panelinin DOM mutasyonlarını ve satır sayısını toplar.
FRAME_PROBE = """
window.__captureGate = {
  frames: [], t0: (window.performance && performance.now()) || 0,
  visibility: null, mutations: 0, streamChars: 0, streamLines: -1,
  observerInstalled: false, probeError: null,
  stop: false,
};
try {
  const tick = (ts) => {
    const g = window.__captureGate;
    g.frames.push(ts);
    g.visibility = document.visibilityState;
    if (!g.stop) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  const install = () => {
    const el = document.getElementById('runstream');
    if (!el) return false;
    const s = () => {
      const g = window.__captureGate;
      const html = el.innerHTML || '';
      g.streamChars = html.length;
      g.streamLines = html.split('\\n').length;
    };
    new MutationObserver(() => {
      window.__captureGate.mutations += 1;
      s();
    }).observe(el, { childList: true, characterData: true, subtree: true });
    window.__captureGate.observerInstalled = true;
    s();
    return true;
  };
  if (!install()) {
    document.addEventListener('DOMContentLoaded', () => {
      if (!install()) setTimeout(install, 200);
    });
  }
} catch (e) {
  window.__captureGate.probeError = String(e);
}
"""

# Kare üretiminin "taze" olduğunu kanıtlayan görünür DOM değişimi: tam
# genişlikte opak bir şerit ekler (kare yenilenmezse PNG baytları aynı kalır).
INJECT_VISIBLE_MARKER = """
() => {
  const d = document.createElement('div');
  d.id = '__capture_gate_marker';
  d.style.cssText =
    'position:fixed;left:0;top:0;width:100%;height:120px;z-index:2147483647;' +
    'background:repeating-linear-gradient(90deg,#000 0 20px,#fff 20px 40px)';
  document.body.appendChild(d);
  return document.body.offsetHeight;
}
"""

# Negatif kontrol: ana iş parçacığını SENKRON bloke et (rAF damgası boşluğu
# üretmek zorunda). Date.now() yeterli; performance.now() de olur.
BLOCK_MAIN_THREAD = """
(ms) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { /* bilinçli meşgul bekleme */ }
  return Date.now();
}
"""

# Negatif kontrol sonrası probe'u kapat (ölçüm penceresini kirletmesin).
STOP_PROBE = "() => { window.__captureGate.stop = true; return true; }"


# ------------------------------------------------------- saf hesap (browser'sız)
def frame_gaps_ms(frames):
    """Kare damgaları arasındaki boşluklar (ms) — ilk kareden önceki bekleme dahil.

    frames: sayfa içi monoton artan `performance.now()` değerleri.
    Geçersiz girdi ValueError (fail-closed): sayısal olmayan/NaN/sonsuz/negatif
    ya da geriye giden damga "ölçüm yok" demektir, sessizce 0 döndürülemez.
    """
    if frames is None or not isinstance(frames, (list, tuple)):
        raise ValueError("kare listesi değil: %r" % (frames,))
    values = []
    for item in frames:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("kare damgası sayısal değil: %r" % (item,))
        if not math.isfinite(item):
            raise ValueError("kare damgası sonlu değil: %r" % (item,))
        if item < 0:
            raise ValueError("kare damgası negatif: %r" % (item,))
        values.append(float(item))
    for prev, cur in zip(values, values[1:]):
        if cur < prev:
            raise ValueError(
                "kare damgaları geriye gidiyor: %r → %r" % (prev, cur))
    if len(values) < 2:
        return []
    gaps = [values[0]] + [cur - prev for prev, cur in zip(values, values[1:])]
    return gaps


def longest_stall_ms(frames):
    """En uzun kare boşluğu; 2'den az kare varsa None (ölçülemez)."""
    gaps = frame_gaps_ms(frames)
    if not gaps:
        return None
    return max(gaps)


def evaluate_frames(frames, budget_ms=STALL_BUDGET_MS_DEFAULT,
                    min_frames=MIN_FRAMES_DEFAULT):
    """(ok, reason) — fail-closed kare üretimi kararı.

    Sıra önemlidir: önce "ölçüm var mı" (kare sayısı), sonra "bütçe geçerli mi",
    en son bütçe karşılaştırması. Böylece hiç kare üretilmeyen bir sayfa
    "boşluk yok" diye PASS olamaz.
    """
    if frames is None or not isinstance(frames, (list, tuple)):
        return False, "kare damgaları okunamadı: %r" % (frames,)
    if (isinstance(min_frames, bool) or not isinstance(min_frames, (int, float))
            or not math.isfinite(min_frames) or min_frames < 2):
        return False, "min_frames geçersiz: %r" % (min_frames,)
    if len(frames) < min_frames:
        return False, (
            "kare üretilmedi: %d < %d (\"produced no frames\") — sayfa hiç "
            "boyamadı ya da ölçüm penceresi çok kısa" % (len(frames), min_frames))
    if (isinstance(budget_ms, bool) or not isinstance(budget_ms, (int, float))
            or not math.isfinite(budget_ms) or budget_ms <= 0):
        return False, "bütçe sayısal/pozitif değil: %r" % (budget_ms,)
    try:
        stall = longest_stall_ms(frames)
    except ValueError as exc:
        return False, "kare ölçümü geçersiz: %s" % exc
    if stall is None:
        return False, "en uzun kare boşluğu ölçülemedi"
    if stall >= budget_ms:
        return False, (
            "kare üretimi %.1f ms durdu (bütçe %s ms) — ana iş parçacığı "
            "kare üretemiyor, yakalama \"no frames\" ile düşer" % (
                stall, budget_ms))
    return True, "en uzun kare boşluğu %.1f ms < bütçe %s ms (%d kare)" % (
        stall, budget_ms, len(frames))


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def evaluate_capture(info):
    """(ok, reason) — tek bir yakalamanın fail-closed değerlendirmesi.

    info: {"ok": bool, "bytes": int, "data": bytes|None, "error": str|None}
    """
    if not isinstance(info, dict):
        return False, "yakalama kaydı sözlük değil: %r" % (info,)
    if info.get("error"):
        return False, "yakalama hata verdi: %s" % info["error"]
    if not info.get("ok"):
        return False, "yakalama başarısız (kare dönmedi)"
    data = info.get("data")
    if not data or not isinstance(data, (bytes, bytearray)):
        return False, "yakalama boş kare döndürdü (\"produced no frames\")"
    if not bytes(data[:8]) == PNG_SIGNATURE:
        return False, "yakalama PNG döndürmedi (imza eksik: %r)" % (
            bytes(data[:8]),)
    if len(data) < MIN_PNG_BYTES:
        return False, (
            "yakalama şüpheli derecede küçük: %d B < %d B (boş/tek-renk kare?)"
            % (len(data), MIN_PNG_BYTES))
    return True, "yakalama geçerli PNG (%d B)" % len(data)


def png_delta_bytes(first, second):
    """İki PNG arasındaki farklı bayt konumu sayısı (uzunluk farkı dahil).

    Sabit/tek-renk bir kare DOM değişiminden sonra BİREBİR aynı baytları
    üretir; bu sayı o durumda 0'a yakın kalır.
    """
    if not first or not second:
        return 0
    limit = min(len(first), len(second))
    delta = sum(1 for i in range(limit) if first[i] != second[i])
    return delta + abs(len(first) - len(second))


def evaluate_freshness(first, second, min_delta=MIN_CAPTURE_DELTA_BYTES):
    """(ok, reason) — DOM değişiminden sonra yakalama GERÇEKTEN yenilendi mi?"""
    if not first or not second:
        return False, "karşılaştırılacak iki yakalama yok"
    if len(second) < MIN_PNG_BYTES:
        return False, "ikinci yakalama boş kare (\"produced no frames\")"
    delta = png_delta_bytes(first, second)
    if delta < min_delta:
        return False, (
            "DOM değişti ama yakalama değişmedi (%d bayt < %d) — kompozitör "
            "taze kare üretmiyor" % (delta, min_delta))
    return True, "kompozitör taze kare üretti (%d bayt fark)" % delta


def evaluate_stream_replay(state, expect_replay=True,
                           stream_max=STREAM_MAX_EXPECTED,
                           slack=STREAM_MAX_SLACK):
    """(ok, reason) — replay patlaması sayfaya ulaştı mı ve pencereye sığdı mı?

    expect_replay: kapı KENDİ fixture sunucusunu kurduysa True (replay kanıtı
    zorunlu). CANLI bir sunucuya bağlanıldıysa False — o sunucuda run logu
    olmayabilir ve "hiç replay yok" meşru bir durumdur; ama panel okunabilir
    olmalı ve pencere sınırı yine de geçerlidir (ölçüm boş sayfada yapılmış
    olabilir, bu yüzden rapor bu ayrımı `mode` alanıyla taşır).
    """
    lines = state.get("streamLines") if isinstance(state, dict) else None
    if lines is None or lines < 0:
        return False, "akış paneli (#runstream) bulunamadı/okunamadı"
    if lines <= 1 and expect_replay:
        return False, (
            "akış panelinde %r satır var — replay patlaması sayfaya ulaşmadı "
            "(ölçüm boş sayfada yapılmış)" % (lines,))
    if lines > stream_max + slack:
        return False, (
            "akış panelinde %d satır > client penceresi %d (+%d) — replay "
            "penceresi büyümüş, kare üretimini tehdit eder" % (
                lines, stream_max, slack))
    return True, "replay sayfaya ulaştı (%d satır, pencere %d)" % (
        lines, stream_max)


def resolve_stall_budget_ms(env=None):
    raw = (env if env is not None else os.environ.get(
        "CAPTURE_STALL_BUDGET_MS", "")).strip()
    if not raw:
        return STALL_BUDGET_MS_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("CAPTURE_STALL_BUDGET_MS sayısal değil: %r" % raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("CAPTURE_STALL_BUDGET_MS pozitif sonlu olmalı: %r" % raw)
    return value


def resolve_min_frames(env=None):
    raw = (env if env is not None else os.environ.get(
        "CAPTURE_MIN_FRAMES", "")).strip()
    if not raw:
        return MIN_FRAMES_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("CAPTURE_MIN_FRAMES sayısal değil: %r" % raw)
    if value < 2:
        raise ValueError("CAPTURE_MIN_FRAMES >= 2 olmalı: %r" % raw)
    return value


def resolve_observe_ms(env=None):
    raw = (env if env is not None else os.environ.get(
        "CAPTURE_OBSERVE_MS", "")).strip()
    if not raw:
        return OBSERVE_MS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("CAPTURE_OBSERVE_MS sayısal değil: %r" % raw)
    if value <= 0:
        raise ValueError("CAPTURE_OBSERVE_MS pozitif olmalı: %r" % raw)
    return value


def resolve_theme(env=None):
    raw = (env if env is not None else os.environ.get(
        "DASHBOARD_THEME", "")).strip()
    if not raw:
        return THEME_DEFAULT
    if raw not in VALID_THEMES:
        raise ValueError("DASHBOARD_THEME %s olmalı, alındı: %r" % (
            "/".join(VALID_THEMES), raw))
    return raw


def aggregate_verdict(checks):
    """Tüm kontroller PASS ise PASS; eksik/FAIL varsa FAIL (fail-closed)."""
    if not checks:
        return "FAIL"
    for name in sorted(checks):
        if checks[name].get("verdict") != "PASS":
            return "FAIL"
    return "PASS"


def build_report(checks, budget_ms, burst, fixture):
    """Deterministik JSON raporu (sıralı anahtarlar; zaman damgası YOK)."""
    return {
        "stall_budget_ms": budget_ms,
        "checks": checks,
        "replay_burst": burst,
        "fixture": fixture,
        "verdict": aggregate_verdict(checks),
    }


def write_report(path, report):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")


def safe_write_report(path, report):
    """Rapor yazımı FAIL-SOFT: (ok, error) döner; istisna sızdırmaz.

    Rapor bir KANIT yan ürünüdür, kapının kararı değil: dolu hacim
    (ENOSPC) yüzünden yazılamayan bir JSON, tüm iddiaları geçen bir koşumu
    kırmızıya çevirmemeli. Ama sessiz de kalmamalı — çağıran (tearDownClass)
    dönen hatayı stderr'e UYARI olarak basar.
    """
    try:
        write_report(path, report)
    except OSError as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    return True, None


# ------------------------------------------------------- replay fixture (gerçek)
def make_run_records(runs, lines_per_run):
    """WORST-CASE run log kayıtları (en eski → en yeni sıralı).

    Satır içeriği gerçek verify çıktısına benzer (K8/K16/K17 ilerleme
    satırları): ~110 B/satır. Ölçülen gerçek patlama ~937 satır/koşu ve
    ~108 B/satırdır; bu fixture ÖLÇÜLENDEN KÜÇÜK olamaz.
    """
    records = []
    for i in range(runs):
        lines = []
        for n in range(lines_per_run):
            lines.append(
                "[K%02d] hook %d/%d — taranan dosya %05d: "
                "_calisma/CIKTI/test_ornek_%05d.py · durum=PASS · sure=%dms"
                % (8 + (n % 12), n + 1, lines_per_run, n, i, 100 + (n % 900)))
        records.append({
            "ts": "2026-10-14T%02d:%02d:00+00:00" % (i % 24, n % 60),
            "verdict": "PASS",
            "exit_code": 0,
            "stdout": "\n".join(lines),
            "stderr": "\n".join("⟶ ilerleme satırı %d" % k
                                for k in range(lines_per_run // 10)),
            "p0": 0, "p1": 0,
            "budget_usd": 1.23 + i,
            "duration_s": 300 + i,
            "refs_verified": 61, "refs_total": 61, "pdf_pages": 33,
        })
    return records


def write_run_logs(runs_dir, records):
    """RUNS_DIR'e `run-<ts>.json` adlarıyla yaz (preview_server ile aynı ad)."""
    os.makedirs(runs_dir, exist_ok=True)
    for rec in records:
        safe = (rec["ts"].replace(":", "").replace("+", "").replace(".", ""))
        path = os.path.join(runs_dir, "run-%s.json" % safe)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)


def replay_burst(records):
    """Gerçek replay üreticisi + SUNUCUNUN tel formatı ile patlama boyutunu ölç.

    `preview_server.Handler._replay_runs` tek bir `write` ile şu formatı
    gönderir: "event: {ev}\\ndata: {data}\\n\\n". Format kayarsa ölçüm sessizce
    yanlış olur; bu yüzden `assert_replay_wire_format` ile çivilenir.
    """
    events = ps.build_replay_events_multi(records)
    payload = "".join("event: %s\ndata: %s\n\n" % (ev, data)
                      for ev, data in events)
    return {
        "events": len(events),
        "bytes": len(payload.encode("utf-8")),
        "lines": sum(1 for ev, _ in events if ev in ("stdout", "stderr")),
        "runs": len(records),
    }


def assert_replay_wire_format(source=None):
    """`_replay_runs` tel formatı ölçümle aynı mı? (kaynak ankoru, fail-closed)"""
    text = source
    if text is None:
        with open(SERVER_SCRIPT, encoding="utf-8") as f:
            text = f.read()
    expected = 'f"event: {ev}\\ndata: {data}\\n\\n"'
    if expected not in text:
        raise AssertionError(
            "_replay_runs tel formatı değişmiş: %r yok — replay patlaması "
            "ölçümü (replay_burst) artık sunucunun gönderdiğini ölçmüyor" % (
                expected,))


def _next_missing_reason():
    if sync_playwright is None:
        return "playwright kurulu değil"
    try:
        with sync_playwright() as p:
            executable = p.chromium.executable_path
    except Exception as exc:  # bozuk/eksik kurulum
        return "Chromium çözülemedi: %s" % exc
    if not os.path.isfile(executable):
        return "Chromium indirilmemiş (playwright install chromium)"
    return ""


CHROMIUM_MISSING = _next_missing_reason()

# CI strict modu: CAPTURE_GATE_REQUIRE_LIVE=1 iken Chromium/Playwright
# yokluğu SKIP değil FAIL'dir. Gerekçe: verify.yml'deki adım `if: always()`
# ile koşar — "Install Chromium" adımı bir üst adımda başarısız olup
# atlanırsa 6 canlı test sessizce skip olur ve kapı sıfırla yeşil döner
# (all-skip fail-open ailesi). Bu kapı o aileyi kapatır.
REQUIRE_LIVE_ENV = "CAPTURE_GATE_REQUIRE_LIVE"


def resolve_require_live(env=None):
    raw = (env if env is not None else os.environ.get(
        REQUIRE_LIVE_ENV, "")).strip().lower()
    if raw in ("", "0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    raise ValueError("%s 0/1 olmalı, alındı: %r" % (REQUIRE_LIVE_ENV, raw))


def live_tier_disposition(require_live, missing_reason):
    """Canlı katmanın akıbeti: ("run", None) | ("skip", msg) | ("fail", msg).

    require_live iken eksik kurulum atlanmaz — CI'da all-skip PASS üretmek
    yerine FAIL üretir. Tarayıcısız koşumda davranış eskisi gibidir (skip).
    """
    if not missing_reason:
        return "run", None
    msg = ("Chromium/Playwright yok (%s) — canlı yakalama ölçülemez"
           % missing_reason)
    if require_live:
        return "fail", ("%s=%s iken canlı katman atlanamaz: %s — kurulum "
                        "adımı atlanmış/bozulmuş (all-skip fail-open kapalı)"
                        % (REQUIRE_LIVE_ENV, "1", msg))
    return "skip", msg


# Katman sözleşmesi (ölçülen süreler, 2026-10-14): unit = saf hesap,
# tarayıcısız ~0.1 sn; integration = gerçek preview_server tel kontratı +
# replay fixture, ~0.2 sn; e2e = gerçek Chromium + gerçek sunucu + iki
# screenshot, ~14 sn. CAPTURE_GATE_TIER ile katman seçilir (varsayılan all);
# yerel iç döngü `unit` ile saniyeler, CI E2E maliyetini tek koşuya düşürür.
TIER_ENV = "CAPTURE_GATE_TIER"
TIER_DEFAULT = "all"
VALID_TIERS = ("unit", "integration", "e2e", "all")


def resolve_tier(env=None):
    raw = (env if env is not None else os.environ.get(
        TIER_ENV, "")).strip().lower()
    if not raw:
        return TIER_DEFAULT
    if raw not in VALID_TIERS:
        raise ValueError("%s %s olmalı, alındı: %r" % (
            TIER_ENV, "/".join(VALID_TIERS), raw))
    return raw


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(host, port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


def split_base(base):
    m = re.match(r"^https?://([^/:]+):(\d+)", base)
    if not m:
        raise RuntimeError(
            "DASHBOARD_BASE_URL ayrıştırılamadı (host:port yok): %s" % base)
    return m.group(1), int(m.group(2))


def dashboard_url(base, theme):
    return "%s%s?theme=%s" % (base.rstrip("/"), PAGE_PATH, theme)


def http_health_ok(base, timeout=3):
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/health",
                                    timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def build_preview_dir(root):
    """Geçici preview dizini: statik yüzey kopyası + WORST-CASE runs fixture.

    Kullanıcı önbelleğine (PREVIEW_DIR) YAZMAZ; `preview_server.py` run loglarını
    `PREVIEW_DIR/runs/` altından okur, bu yüzden fixture buraya yazılır.
    """
    runs = FIXTURE_RUNS if FIXTURE_RUNS is not None else ps.RUN_LOG_MAX
    for name in ("preview.html", "preview.js", "design-system-tokens.css"):
        src = os.path.join(HERE, name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(root, name))
    records = make_run_records(runs, FIXTURE_LINES_PER_RUN)
    write_run_logs(os.path.join(root, "runs"), records)
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    return records


# ------------------------------------------------------------- browser'sız süit
class CaptureMathTest(unittest.TestCase):
    """Browser'sız: kare matematiği + fail-closed kararlar + fixture sözleşmesi."""

    def test_gaps_include_wait_before_first_frame(self):
        self.assertEqual(frame_gaps_ms([100.0, 116.0, 132.0]),
                         [100.0, 16.0, 16.0])

    def test_longest_stall_is_the_max_gap(self):
        self.assertEqual(longest_stall_ms([0.0, 16.0, 2000.0, 2016.0]), 1984.0)

    def test_single_frame_is_unmeasurable(self):
        self.assertEqual(longest_stall_ms([5.0]), None)
        self.assertEqual(frame_gaps_ms([]), [])

    def test_bad_frame_samples_raise(self):
        for bad in (None, "abc", 5, [float("nan")], [-1.0], [10.0, 5.0],
                    ["1"], [True]):
            with self.assertRaises(ValueError):
                frame_gaps_ms(bad)

    def test_no_frames_fails_closed(self):
        ok, reason = evaluate_frames([], budget_ms=2000.0, min_frames=20)
        self.assertFalse(ok, "hiç kare üretilmeyen sayfa PASS olamaz")
        self.assertIn("produced no frames", reason)

    def test_below_min_frames_fails_closed(self):
        ok, _ = evaluate_frames([float(i) for i in range(19)],
                                budget_ms=2000.0, min_frames=20)
        self.assertFalse(ok)

    def test_stall_over_budget_fails(self):
        # Boşluk 16 → 2017 arasında 2001 ms: bütçe (2000) AŞILIR.
        ok, reason = evaluate_frames([0.0, 16.0, 2017.0, 2033.0],
                                     budget_ms=2000.0, min_frames=2)
        self.assertFalse(ok)
        self.assertIn("2001", reason)

    def test_stall_boundary_is_exclusive(self):
        frames = [0.0] + [float(i * 16) for i in range(1, 40)]
        frames.append(frames[-1] + 2000.0)  # tam bütçe → FAIL
        ok, _ = evaluate_frames(frames, budget_ms=2000.0, min_frames=2)
        self.assertFalse(ok, "tam bütçe değeri FAIL olmalı (kesin küçüktür)")
        frames[-1] = frames[-2] + 1999.0
        ok, _ = evaluate_frames(frames, budget_ms=2000.0, min_frames=2)
        self.assertTrue(ok)

    def test_healthy_frames_pass(self):
        frames = [float(i * 16) for i in range(60)]
        ok, reason = evaluate_frames(frames, budget_ms=2000.0, min_frames=20)
        self.assertTrue(ok, reason)

    def test_bad_budget_or_min_frames_fails_closed(self):
        frames = [float(i * 16) for i in range(30)]
        for bad in (0, -1, float("nan"), float("inf"), "2000", True):
            ok, _ = evaluate_frames(frames, budget_ms=bad, min_frames=20)
            self.assertFalse(ok, "bütçe %r geçersiz" % (bad,))
        for bad in (1, 0, -3, "20", True):
            ok, _ = evaluate_frames(frames, budget_ms=2000.0, min_frames=bad)
            self.assertFalse(ok, "min_frames %r geçersiz" % (bad,))

    def test_capture_missing_bytes_fails_closed(self):
        ok, reason = evaluate_capture(
            {"ok": True, "bytes": 0, "data": b"", "error": None})
        self.assertFalse(ok)
        self.assertIn("produced no frames", reason)

    def test_capture_error_is_not_swallowed(self):
        ok, reason = evaluate_capture(
            {"ok": False, "bytes": 0, "data": None,
             "error": "Target closed"})
        self.assertFalse(ok)
        self.assertIn("Target closed", reason)

    def test_capture_non_png_fails_closed(self):
        ok, reason = evaluate_capture(
            {"ok": True, "bytes": 100, "data": b"<html>" + b"x" * 4000})
        self.assertFalse(ok)
        self.assertIn("PNG", reason)

    def test_capture_tiny_png_fails_closed(self):
        ok, reason = evaluate_capture(
            {"ok": True, "bytes": 30, "data": PNG_SIGNATURE + b"\x00" * 30})
        self.assertFalse(ok)
        self.assertIn("küçük", reason)

    def test_capture_valid_png_passes(self):
        ok, reason = evaluate_capture(
            {"ok": True, "bytes": 4096, "data": PNG_SIGNATURE + b"\x01" * 4096})
        self.assertTrue(ok, reason)

    def test_identical_captures_are_not_fresh(self):
        png = PNG_SIGNATURE + b"\xab" * 4096
        ok, reason = evaluate_freshness(png, png)
        self.assertFalse(ok, "aynı baytlar taze kare kanıtı olamaz")
        self.assertIn("taze kare üretmiyor", reason)

    def test_changed_capture_is_fresh(self):
        first = PNG_SIGNATURE + b"\xab" * 4096
        second = PNG_SIGNATURE + b"\xcd" * 4096
        ok, reason = evaluate_freshness(first, second)
        self.assertTrue(ok, reason)
        self.assertEqual(png_delta_bytes(first, second), 4096)

    def test_live_mode_tolerates_absent_replay_but_not_unreadable_panel(self):
        # Canlı sunucuda run logu olmayabilir → replay kanıtı zorunlu değil.
        ok, _ = evaluate_stream_replay({"streamLines": 1}, expect_replay=False)
        self.assertTrue(ok)
        # Ama pencere sınırı ve okunabilirlik yine fail-closed.
        ok, _ = evaluate_stream_replay(
            {"streamLines": STREAM_MAX_EXPECTED + STREAM_MAX_SLACK + 1},
            expect_replay=False)
        self.assertFalse(ok)
        ok, reason = evaluate_stream_replay({"streamLines": -1},
                                            expect_replay=False)
        self.assertFalse(ok)
        self.assertIn("#runstream", reason)

    def test_stream_window_bounds(self):
        ok, reason = evaluate_stream_replay({"streamLines": 600})
        self.assertTrue(ok, reason)
        ok, _ = evaluate_stream_replay({"streamLines": 600 + STREAM_MAX_SLACK + 1})
        self.assertFalse(ok, "pencere büyürse FAIL (kare üretimini tehdit eder)")
        ok, reason = evaluate_stream_replay({"streamLines": 0})
        self.assertFalse(ok)
        self.assertIn("ulaşmadı", reason)
        ok, reason = evaluate_stream_replay({"streamLines": -1})
        self.assertFalse(ok)
        self.assertIn("#runstream", reason)

    def test_require_live_env_validates(self):
        self.assertFalse(resolve_require_live(""))
        self.assertFalse(resolve_require_live("0"))
        self.assertTrue(resolve_require_live("1"))
        with self.assertRaises(ValueError):
            resolve_require_live("evet")

    def test_live_disposition_is_fail_closed_under_require(self):
        self.assertEqual(live_tier_disposition(False, ""), ("run", None))
        action, msg = live_tier_disposition(True, "")
        self.assertEqual(action, "run")
        self.assertIsNone(msg)
        action, msg = live_tier_disposition(False, "playwright kurulu değil")
        self.assertEqual(action, "skip")
        self.assertIn("playwright kurulu değil", msg)
        action, msg = live_tier_disposition(True, "playwright kurulu değil")
        self.assertEqual(action, "fail")
        self.assertIn(REQUIRE_LIVE_ENV, msg)
        self.assertIn("playwright kurulu değil", msg)

    def test_live_tier_has_no_skip_decorator_and_ci_requires_live(self):
        # Çıpa: skipIf geri gelirse veya CI strict modu düşerse bu kırmızı olsun.
        with open(os.path.abspath(__file__), encoding="utf-8") as fh:
            src = fh.read()
        # Satır-başlı desen: bu assertion'ın kendi literal'i eşleşmesin diye
        # dekoratör kalıbı satır başı `@unittest.skipIf(CHROMIUM_MISSING` ile
        # çivilenir.
        self.assertIsNone(
            re.search(r"(?m)^@unittest\.skipIf\(CHROMIUM_MISSING", src),
            "canlı katman yeniden dekore edilmiş — CI'da all-skip "
            "fail-open geri geldi")
        self.assertIn("live_tier_disposition(resolve_require_live(),", src)
        with open(os.path.join(REPO_ROOT, ".github", "workflows",
                               "verify.yml"), encoding="utf-8") as fh:
            workflow = fh.read()
        # İki geçerli biçim: `env:` haritası (`CAPTURE_GATE_REQUIRE_LIVE: "1"`)
        # ya da adım içi önek (`CAPTURE_GATE_REQUIRE_LIVE=1`). verify.yml
        # ikincisini kullanıyor (test_browser_skip_audit bu tam dizgeyi çiviliyor);
        # kural değişmedi: adım strict modu 1'e SABİTLEMEK zorunda.
        self.assertRegex(
            workflow,
            r"CAPTURE_GATE_REQUIRE_LIVE(?::\s*['\"]?1['\"]?|=1\b)",
            "verify.yml capture gate adımı strict modu set etmiyor")

    def test_setupclass_registers_cleanup_before_resources(self):
        # Çıpa: sınıf temizliği kaydı, kaynaklar YARATILMADAN önce alınmalı;
        # aksi halde setUpClass hatasında spawn edilmiş sunucu/tmp sızar.
        with open(os.path.abspath(__file__), encoding="utf-8") as fh:
            src = fh.read()
        reg = src.index("cls.addClassCleanup(cls._cleanup_resources)")
        mkd = src.index('cls.tmp = tempfile.mkdtemp(prefix="capture-gate-")')
        pop = src.index("cls.proc = subprocess.Popen(")
        self.assertTrue(reg < mkd < pop,
                        "addClassCleanup kaydı kaynak yaratımından SONRA mı?")

    def test_class_cleanup_is_idempotent_and_removes_tmp(self):
        # Dummy alt sınıf: canlı sınıfın durumuna dokunmadan temizlik yolu.
        class Dummy(PreviewCaptureGateTest):
            pass
        tmp = tempfile.mkdtemp(prefix="capture-cleanup-probe-")
        Dummy.proc = None
        Dummy.tmp = tmp
        Dummy.base = "http://127.0.0.1:1"
        Dummy._cleanup_resources()
        self.assertFalse(os.path.isdir(tmp), "tmp dizin temizlenmedi")
        self.assertIsNone(Dummy.proc)
        self.assertIsNone(Dummy.tmp)
        self.assertIsNone(Dummy.base)
        Dummy._cleanup_resources()  # idempotent: ikinci çağrı zararsız

    def test_tier_env_validates(self):
        self.assertEqual(resolve_tier(""), "all")
        self.assertEqual(resolve_tier("unit"), "unit")
        self.assertEqual(resolve_tier("E2E"), "e2e")
        with self.assertRaises(ValueError):
            resolve_tier("smoke")

    def test_load_tests_selects_tier_classes(self):
        # env sızıntısız: eski değeri iade et (finally).
        old = os.environ.get(TIER_ENV)
        try:
            for tier, expected in (("unit", {"CaptureMathTest"}),
                                   ("integration",
                                    {"ReplayFixtureContractTest"}),
                                   ("e2e", {"PreviewCaptureGateTest"})):
                os.environ[TIER_ENV] = tier
                names = {t.__class__.__name__ for t in _iter_tests(
                    load_tests(unittest.TestLoader(), None, None))}
                self.assertEqual(names, expected,
                                 "katman %s sınıf seçimi kaymış: %r" % (
                                     tier, names))
            os.environ[TIER_ENV] = "all"
            expected_all = sum(
                unittest.defaultTestLoader.loadTestsFromTestCase(c)
                .countTestCases() for c in TIER_CLASSES["all"])
            self.assertEqual(
                len(list(_iter_tests(load_tests(unittest.TestLoader(),
                                                None, None)))),
                expected_all)
            os.environ[TIER_ENV] = "bozuk"
            with self.assertRaises(ValueError):
                load_tests(unittest.TestLoader(), None, None)
        finally:
            if old is None:
                os.environ.pop(TIER_ENV, None)
            else:
                os.environ[TIER_ENV] = old

    def test_env_overrides_validate(self):
        self.assertEqual(resolve_stall_budget_ms(""), STALL_BUDGET_MS_DEFAULT)
        self.assertEqual(resolve_stall_budget_ms("2000"), 2000.0)
        for bad in ("abc", "0", "-1", "nan", "inf"):
            with self.assertRaises(ValueError):
                resolve_stall_budget_ms(bad)
        self.assertEqual(resolve_min_frames(""), MIN_FRAMES_DEFAULT)
        for bad in ("1", "0", "x"):
            with self.assertRaises(ValueError):
                resolve_min_frames(bad)
        self.assertEqual(resolve_observe_ms(""), OBSERVE_MS_DEFAULT)
        with self.assertRaises(ValueError):
            resolve_observe_ms("0")
        self.assertEqual(resolve_theme(""), THEME_DEFAULT)
        self.assertEqual(resolve_theme("light"), "light")
        with self.assertRaises(ValueError):
            resolve_theme("vercel")

    def test_aggregate_verdict_is_fail_closed(self):
        ok = {"verdict": "PASS"}
        fail = {"verdict": "FAIL"}
        self.assertEqual(aggregate_verdict({"a": ok, "b": ok}), "PASS")
        self.assertEqual(aggregate_verdict({"a": ok, "b": fail}), "FAIL")
        self.assertEqual(aggregate_verdict({}), "FAIL")

    def test_report_write_failure_is_reported_not_raised(self):
        # Disksiz negatif vaka: ebeveyni bir DOSYA olan yol yazılamaz
        # (ENOTDIR) — kapı bunu yutmaz ama istisna da sızdırmaz.
        bad = os.path.join(os.path.abspath(__file__), "capture_report.json")
        ok, err = safe_write_report(bad, {"verdict": "PASS"})
        self.assertFalse(ok, "yazılamayan rapor sessizce başarılı sayılamaz")
        self.assertIn("capture_report.json", err or "")

    def test_report_write_success_path(self):
        # /dev/null: gerçek yazma yolu, sıfır disk kullanımı.
        ok, err = safe_write_report("/dev/null", {"verdict": "PASS"})
        self.assertTrue(ok, err)
        self.assertIsNone(err)

    def test_report_is_deterministic(self):
        checks = {"a": {"verdict": "PASS"}, "b": {"verdict": "PASS"}}
        burst = {"events": 1, "bytes": 2, "lines": 3, "runs": 1}
        first = json.dumps(build_report(checks, 2000.0, burst, {}),
                           sort_keys=True)
        second = json.dumps(build_report(dict(reversed(list(checks.items()))),
                                         2000.0, burst, {}), sort_keys=True)
        self.assertEqual(first, second)


class ReplayFixtureContractTest(unittest.TestCase):
    """Browser'sız: fixture GERÇEKTEN worst-case mi ve tel formatı kaymadı mı?"""

    def test_replay_wire_format_matches_server(self):
        assert_replay_wire_format()  # kayarsa AssertionError

    def test_wire_format_anchor_is_falsifiable(self):
        with self.assertRaises(AssertionError):
            assert_replay_wire_format("def _replay_runs(self, records): ...")

    def test_fixture_is_not_smaller_than_measured_worst_case(self):
        runs = ps.RUN_LOG_MAX
        records = make_run_records(runs, FIXTURE_LINES_PER_RUN)
        burst = replay_burst(records)
        self.assertEqual(burst["runs"], runs)
        # Fixture self-consistency: her run'ın satırları + sınır olayları
        # gerçekten replay listesine girmiş olmalı.
        self.assertGreaterEqual(burst["lines"], runs * FIXTURE_LINES_PER_RUN)
        # Ölçülen gerçek patlamanın ALTINA düşmesin (2.03 MB / 18.732 olay).
        self.assertGreaterEqual(
            burst["lines"], 18000,
            "fixture %d satır — ölçülen gerçek patlama 18.732 satırdı" %
            burst["lines"])
        self.assertGreaterEqual(
            burst["bytes"], 1800000,
            "fixture %d B — ölçülen gerçek patlama 2.03 MB'tı" % burst["bytes"])
        # Ölçüm ile ölçülen taban tutarlı (aşırı sapma = fixture kaymış).
        self.assertLess(burst["bytes"], MEASURED_BURST_BYTES * 3,
                        "fixture ölçülenden 3 kat büyük — tabanı güncelle")

    def test_empty_runs_dir_replays_nothing(self):
        # Sıra bağımsızlığı: ambient ps.RUNS_DIR'e GÜVENME — boş dizini kendimiz
        # kurar, koşum sonunda eski değere iade ederiz (round-trip ile aynı
        # desen). Aksi halde test, önce hangi sınıfın koştuğuna bağlı olarak
        # başka bir fixture'ın kalıntısına göre kararırdı.
        with tempfile.TemporaryDirectory(prefix="capture-empty-") as tmp:
            runs_dir = os.path.join(tmp, "runs")
            os.makedirs(runs_dir, exist_ok=True)
            old_runs = ps.RUNS_DIR
            ps.RUNS_DIR = runs_dir
            try:
                self.assertEqual(ps.load_run_logs(3), [])
            finally:
                ps.RUNS_DIR = old_runs
            self.assertEqual(replay_burst([])["events"], 0)

    def test_write_and_load_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="capture-runs-") as tmp:
            runs_dir = os.path.join(tmp, "runs")
            records = make_run_records(2, 5)
            write_run_logs(runs_dir, records)
            old_runs = ps.RUNS_DIR
            ps.RUNS_DIR = runs_dir
            try:
                loaded = ps.load_run_logs(5)
            finally:
                ps.RUNS_DIR = old_runs
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[-1]["verdict"], "PASS")
            self.assertIn("K08", loaded[-1]["stdout"])


# --------------------------------------------------------- canlı ölçüm süiti
class PreviewCaptureGateTest(unittest.TestCase):
    """Canlı dashboard'a karşı gerçek kare üretimi + gerçek PNG yakalama.

    Sınıf DEKORE edilmez (skipIf yok): akıbet kararı setUpClass'ta
    live_tier_disposition ile verilir — CAPTURE_GATE_REQUIRE_LIVE=1 iken
    eksik Chromium skip değil FAIL olur (CI all-skip fail-open kapalı).
    """

    base = None
    proc = None
    tmp = None
    _state = None
    _burst = None
    _fixture = None
    _first = None
    _second = None
    _negative = None
    _pageerrors = None

    @classmethod
    def _cleanup_resources(cls):
        """Idempotent sınıf temizliği — addClassCleanup ile çağrılır.

        Gerekçe (izolasyon): unittest, setUpClass bir exception ile düşerse
        tearDownClass'ı ÇAĞIRMAZ. Kaynaklar (tmp dizin, spawn edilmiş sunucu)
        yaratılmadan ÖNCE addClassCleanup ile kaydedilir; bu tek temizlik
        kaynağıdır, ikinci çağrı zararsızdır.
        """
        proc, cls.proc = cls.proc, None
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            except Exception:
                pass  # süreç zaten ölmüş olabilir — temizlik yine de sürsün
        tmp, cls.tmp = cls.tmp, None
        if tmp and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        cls.base = None

    @classmethod
    def setUpClass(cls):
        action, msg = live_tier_disposition(resolve_require_live(),
                                            CHROMIUM_MISSING)
        if action == "skip":
            raise unittest.SkipTest(msg)
        if action == "fail":
            raise AssertionError(msg)
        cls.budget = resolve_stall_budget_ms()
        cls.min_frames = resolve_min_frames()
        cls.observe_ms = resolve_observe_ms()
        cls.theme = resolve_theme()
        cls.proc = None
        # İzolasyon: setUpClass düşerse tearDownClass çağrılmaz — kaynaklar
        # yaratılmadan önce sınıf temizliğini kayda al (fail-safe).
        cls.addClassCleanup(cls._cleanup_resources)
        if LIVE_BASE:
            host, port = split_base(LIVE_BASE)
            cls.base = LIVE_BASE.rstrip("/")
            if not wait_for_port(host, port, timeout=10):
                raise RuntimeError(
                    "DASHBOARD_BASE_URL=%s erişilemedi (%s:%s dinlemiyor) — "
                    "canlı sunucu ayakta mı?" % (LIVE_BASE, host, port))
            # Canlı sunucuda fixture'ı biz kurmadık: patlama ölçümü rapor için
            # yine de hesaplanır, ama "fixture" alanı canlı olduğunu söyler.
            cls._burst = replay_burst(make_run_records(
                ps.RUN_LOG_MAX, FIXTURE_LINES_PER_RUN))
            cls._fixture = {"mode": "live", "base_url": cls.base}
            return

        cls.tmp = tempfile.mkdtemp(prefix="capture-gate-")
        records = build_preview_dir(cls.tmp)
        cls._burst = replay_burst(records)
        cls._fixture = {
            "mode": "spawned",
            "preview_dir": cls.tmp,
            "runs": len(records),
            "lines_per_run": FIXTURE_LINES_PER_RUN,
        }
        port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", cls.tmp,
             "--port", str(port),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port("127.0.0.1", port, timeout=15):
            # terminate gerekmez: sınıf temizliği (addClassCleanup) bu raise
            # sonrasında cls.proc'ı temizler.
            raise RuntimeError(
                "preview_server.py 127.0.0.1:%s üzerinde başlamadı (%s)" % (
                    port, SERVER_SCRIPT))
        cls.base = "http://127.0.0.1:%s" % port
        if not http_health_ok(cls.base):
            raise RuntimeError(
                "/api/health hazır değil: %s (spawn edilen fixture sunucusu)" %
                cls.base)

    @classmethod
    def tearDownClass(cls):
        try:
            if cls._state is not None:
                checks = cls._check_summary()
                report = build_report(checks, cls.budget, cls._burst,
                                      cls._fixture)
                print("Yakalama kapısı: bütçe=%s ms · %s · karar=%s" % (
                    cls.budget,
                    " · ".join("%s=%s" % (name, checks[name]["verdict"])
                               for name in sorted(checks)),
                    report["verdict"]), flush=True)
                path = (os.environ.get("CAPTURE_REPORT_PATH") or "").strip()
                if path:
                    # Rapor bir KANIT yan ürünüdür, kapının kendisi değil:
                    # yazılamazsa (ör. dolu hacim → ENOSPC) koşum gereksiz
                    # yere kırmızıya düşmez, ama kaybolduğu da sessiz kalmaz
                    # (stderr'e UYARI + özet satırı stdout'ta zaten var).
                    ok, err = safe_write_report(path, report)
                    if not ok:
                        sys.stderr.write(
                            "UYARI: %s yazılamadı (%s) — ölçüm yine de "
                            "stdout'ta\n" % (path, err))
                        sys.stderr.flush()
        finally:
            # Tek temizlik kaynağı sınıf temizliğidir (addClassCleanup);
            # buradan çağırmak idempotent ve zararsız.
            cls._cleanup_resources()

    # ------------------------------------------------------------- ölçüm
    @classmethod
    def _expect_replay(cls):
        """Replay kanıtı zorunlu mu? Yalnız fixture sunucusunda EVET."""
        return (cls._fixture or {}).get("mode") == "spawned"

    @classmethod
    def _capture(cls, page, label):
        """page.screenshot() — hata YUTULMAZ, kayda geçer (fail-closed)."""
        try:
            data = page.screenshot(timeout=CAPTURE_TIMEOUT_MS)
        except Exception as exc:
            return {"ok": False, "bytes": 0, "data": None, "label": label,
                    "error": "%s: %s" % (type(exc).__name__, exc)}
        return {"ok": True, "bytes": len(data), "data": data, "label": label,
                "error": None}

    @classmethod
    def measure(cls):
        """(1 kez) canlı ölçüm: kareler, replay, iki yakalama, negatif kontrol."""
        if cls._state is not None:
            return cls._state
        page_errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-background-timer-throttling",
                      "--disable-renderer-backgrounding",
                      "--disable-backgrounding-occluded-windows"])
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.route("/sw.js", lambda route: route.fulfill(body=""))
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                page.add_init_script(FRAME_PROBE)
                page.goto(dashboard_url(cls.base, cls.theme),
                          wait_until="domcontentloaded", timeout=30000)
                # Replay patlaması tam bu pencerede akar; yakalama ONUN İÇİNDE
                # yapılır (arızanın oluştuğu an).
                page.wait_for_timeout(400)
                cls._first = cls._capture(page, "during-replay")
                page.wait_for_timeout(cls.observe_ms)
                state = page.evaluate("() => window.__captureGate")
                page.evaluate(INJECT_VISIBLE_MARKER)
                page.wait_for_timeout(300)
                cls._second = cls._capture(page, "after-dom-change")
                # Negatif kontrol: ana iş parçacığını bloke et, dedektörün
                # bunu GÖRDÜĞÜNÜ doğrula (ölçüm hattı ölü olmasın).
                before = len(state.get("frames") or [])
                page.evaluate(BLOCK_MAIN_THREAD, NEGATIVE_CONTROL_BLOCK_MS)
                after_state = page.evaluate("() => window.__captureGate")
                page.evaluate(STOP_PROBE)
                cls._negative = {
                    "blocked_ms": NEGATIVE_CONTROL_BLOCK_MS,
                    "frames_before": before,
                    "frames_after": len(after_state.get("frames") or []),
                    "stall_after_ms": longest_stall_ms(
                        after_state.get("frames") or []),
                }
            finally:
                browser.close()
        cls._pageerrors = page_errors
        cls._state = state
        return cls._state

    @classmethod
    def _check_summary(cls):
        """Test kararlarının deterministik özeti (rapor + log ortak)."""
        state = cls._state or {}
        checks = {}
        checks["frames"] = {"verdict": "PASS" if evaluate_frames(
            state.get("frames"), cls.budget, cls.min_frames)[0] else "FAIL",
            "longest_stall_ms": longest_stall_ms(state.get("frames") or []),
            "count": len(state.get("frames") or []),
            "visibility": state.get("visibility")}
        checks["capture_during_replay"] = {
            "verdict": "PASS" if evaluate_capture(cls._first or {})[0]
                       else "FAIL",
            "bytes": (cls._first or {}).get("bytes", 0),
            "error": (cls._first or {}).get("error")}
        checks["capture_after_dom_change"] = {
            "verdict": "PASS" if evaluate_capture(cls._second or {})[0]
                       else "FAIL",
            "bytes": (cls._second or {}).get("bytes", 0),
            "error": (cls._second or {}).get("error")}
        checks["fresh_frames"] = {
            "verdict": "PASS" if evaluate_freshness(
                (cls._first or {}).get("data"),
                (cls._second or {}).get("data"))[0] else "FAIL",
            "delta_bytes": png_delta_bytes((cls._first or {}).get("data") or b"",
                                           (cls._second or {}).get("data") or b"")}
        checks["replay_reached_page"] = {
            "verdict": "PASS" if evaluate_stream_replay(
                state, cls._expect_replay())[0] else "FAIL",
            "stream_lines": state.get("streamLines"),
            "mutations": state.get("mutations")}
        return checks

    # ------------------------------------------------------------- testler
    def test_1_measurement_environment_is_live_and_fail_closed(self):
        state = self.measure()
        self.assertIsNone(
            state.get("probeError"),
            "kare probe'u kurulamadı: %r" % state.get("probeError"))
        self.assertTrue(
            state.get("observerInstalled"),
            "akış paneli gözlemcisi kurulamadı — replay kanıtı ölçülemez")
        self.assertIsInstance(
            state.get("frames"), list,
            "kare damgaları okunamadı: %r" % (state.get("frames"),))
        self.assertGreaterEqual(
            len(state.get("frames") or []), self.min_frames,
            "sayfa %.1f s'de %d kare üretti (< %d) — \"produced no frames\""
            % (self.observe_ms / 1000.0, len(state.get("frames") or []),
               self.min_frames))
        self.assertEqual(state.get("visibility"), "visible",
                         "sayfa görünür değil: %r" % state.get("visibility"))
        self.assertEqual(self._pageerrors, [],
                         "sayfa hatası: %s" % self._pageerrors)

    def test_2_frame_liveness_within_capture_budget(self):
        state = self.measure()
        ok, reason = evaluate_frames(state.get("frames"), self.budget,
                                     self.min_frames)
        self.assertTrue(ok, "kare üretimi bütçeyi aştı: %s" % reason)

    def test_3_dashboard_is_capturable_as_png(self):
        self.measure()
        for info in (self._first, self._second):
            ok, reason = evaluate_capture(info)
            self.assertTrue(
                ok, "%s yakalaması başarısız: %s" % (
                    (info or {}).get("label"), reason))

    def test_4_capture_reflects_fresh_frames(self):
        self.measure()
        ok, reason = evaluate_freshness(
            (self._first or {}).get("data"), (self._second or {}).get("data"))
        self.assertTrue(
            ok, "DOM değişimine rağmen kare yenilenmedi: %s" % reason)

    def test_5_replay_burst_reached_page_within_client_window(self):
        state = self.measure()
        ok, reason = evaluate_stream_replay(state, self._expect_replay())
        self.assertTrue(ok, reason)
        self.assertGreaterEqual(
            (self._burst or {}).get("events", 0), 18000,
            "fixture replay patlaması ölçülen gerçeğin altında: %r" % (
                self._burst,))

    def test_6_negative_control_stall_is_detected(self):
        self.measure()
        neg = self._negative or {}
        self.assertGreaterEqual(
            len(self._state.get("frames") or []), self.min_frames,
            "kare ölçümü yoksa negatif kontrol anlamsız")
        self.assertIsNotNone(
            neg.get("stall_after_ms"),
            "negatif kontrol sonrası kare boşluğu ölçülemedi")
        self.assertGreaterEqual(
            neg.get("stall_after_ms"), NEGATIVE_CONTROL_BLOCK_MS * 0.9,
            "ana iş parçacığı %s ms bloke edildi ama dedektör %.1f ms gördü — "
            "ölçüm hattı ölü, test-2'deki PASS güvenilmez" % (
                NEGATIVE_CONTROL_BLOCK_MS, neg.get("stall_after_ms") or 0.0))


# ----------------------------------------------------------- katman seçimi
TIER_CLASSES = {
    "unit": (CaptureMathTest,),
    "integration": (ReplayFixtureContractTest,),
    "e2e": (PreviewCaptureGateTest,),
    "all": (CaptureMathTest, ReplayFixtureContractTest,
            PreviewCaptureGateTest),
}


def _iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item


def load_tests(loader, tests, pattern):
    """CAPTURE_GATE_TIER ile katman seçimi (varsayılan: all).

    Sınıf adıyla SEÇİLEN koşular (python -m unittest modul.Sınıf) bu kancadan
    geçmez — kanca yalnız modül yüklemesinde çağrılır; bu bilinçli tercihtir
    (tek sınıf hedefli koşum filtrelenmez, ters sıra denemeleri çalışır).
    """
    suite = unittest.TestSuite()
    for cls in TIER_CLASSES[resolve_tier()]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
