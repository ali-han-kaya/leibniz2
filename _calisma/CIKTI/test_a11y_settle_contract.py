#!/usr/bin/env python3
"""R9 sozlesmesi: a11y kapisi veri ceken pano yuzeyini GORMESI.

OLCU 2026-10-03 (yerel Chromium, preview_server + gercek history.jsonl):
  kapinin yaptigi gibi `load` aninda  -> #trend <text> node = 0,
                                        #trend-count = "" (bos),
                                        axe color-contrast = 36 node,
                                        trend'e ait node = 0
  fetch'ler cozulduktan sonra           -> #trend <text> node = 14,
                                        #trend-count = "(4 run)",
                                        axe color-contrast = 43 node,
                                        trend'e ait node = 6
Yani 6 gercek node kapidan gorusuydu; yuzey buyutulmus gibi gorunurken
hicbir sey taranmamis oluyordu. Iki kosul birlikte duzeltildi:
  1) dashboard hazir isareti koyar (body[data-scan-ready="1"]),
  2) kapı o isareti bekler, gelmezse FAIL (fail-closed).
Tohumlama TEK BASINA yetmezdi: veri diskte olsa bile kapı fetch cozulmeden
taradigi icin ayni bosluk korunurdu (olcum yukarida).

networkidle ELENDI: preview.js iki EventSource ac-kapa (/api/run-stream,
/api/run) tutuyor -> `wait_for_load_state("networkidle")` 2 s'de TIMEOUT.

Bu dosya sozlesmeyi kilitler: config sekli, bekci davranisi, hazir isaretinin
preview.js'teki kaynagi ve workflow'un tohumlama adimi.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a11y_gate  # noqa: E402
import seed_a11y_history  # noqa: E402

CONFIG = HERE / "a11y_gate_config.json"
PREVIEW_JS = HERE / "preview.js"
WORKFLOW = HERE.parent.parent / ".github" / "workflows" / "verify.yml"

SETTLE_ATTRIBUTE = "scan-ready"


def base_cfg(pages=None):
    return {
        "blocking": ["critical"],
        "warn": ["serious"],
        "incomplete": "report-only",
        "pages": pages or [{"path": "/preview.html"}],
        "allowlist": [],
    }


def load_cfg(cfg):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cfg.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return a11y_gate.load_config(path)


# ------------------------------------------------------------- tohumlama


class SeedHistoryTests(unittest.TestCase):
    """Tohumlanan gecmis: deterministik, >=2 satir, dashboard alanlari dolu."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "history.jsonl")

    def seed(self, rows=8):
        return seed_a11y_history.write_history(self.out, rows)

    def test_rows_are_written(self):
        self.assertEqual(self.seed(6), 6)
        with open(self.out, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 6)

    def test_two_runs_are_byte_identical(self):
        """Ayni girdi -> ayni bayt. Kapinin girdisi kumeler arasinda
        degismesin (aksi halde a11y rozeti urunekadar oynar)."""
        first = os.path.join(self.tmp.name, "a.jsonl")
        second = os.path.join(self.tmp.name, "b.jsonl")
        seed_a11y_history.write_history(first, 5)
        seed_a11y_history.write_history(second, 5)
        with open(first, "rb") as f1, open(second, "rb") as f2:
            self.assertEqual(f1.read(), f2.read())

    def test_rows_carry_dashboard_fields(self):
        self.seed(4)
        with open(self.out, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
        for row in rows:
            for key in ("ts", "verdict", "p0", "p1", "duration_s",
                        "budget_usd", "budget_limit"):
                self.assertIn(key, row)
            self.assertIsInstance(row["p0"], int)
            self.assertIsInstance(row["p1"], int)
            self.assertRegex(row["ts"], r"^\d{4}-\d{2}-\d{2}T")

    def test_rows_ascend_in_time(self):
        self.seed(8)
        with open(self.out, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
        self.assertEqual(rows, sorted(rows, key=lambda r: r["ts"]))

    def test_single_row_rejected(self):
        """Tek nokta cizgi degil; eksik trend yuzeyi olusurdu."""
        with self.assertRaises(SystemExit):
            self.seed(1)

    def test_zero_rows_rejected(self):
        with self.assertRaises(SystemExit):
            self.seed(0)

    def test_cli_writes_and_prints(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "seed_a11y_history.py"),
             "--out", self.out, "--rows", "4"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("4", proc.stdout)
        self.assertTrue(os.path.isfile(self.out))

    def test_cli_rejects_single_row(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "seed_a11y_history.py"),
             "--out", self.out, "--rows", "1"],
            capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)


# --------------------------------------------------------------- config


class SettleConfigContractTests(unittest.TestCase):
    """`settle` sayfa bazli bir sozlesmedir: gecersizse config FAIL."""

    def assertRejects(self, page, needle):
        cfg = base_cfg(pages=[page])
        with self.assertRaises(ValueError) as ctx:
            load_cfg(cfg)
        self.assertIn(needle, str(ctx.exception))

    def test_shipped_config_declares_settle_for_preview(self):
        with CONFIG.open(encoding="utf-8") as f:
            cfg = json.load(f)
        page = [p for p in cfg["pages"] if p["path"] == "/preview.html"][0]
        self.assertEqual(page["settle"]["attribute"], SETTLE_ATTRIBUTE)
        self.assertIsInstance(page["settle"]["timeout_ms"], int)
        self.assertGreater(page["settle"]["timeout_ms"], 0)

    def test_shipped_config_guide_has_no_settle(self):
        """guide.html hazir isareti yaymiyor; bekci tanimlamak kapiyi
        gereksiz yere kirmiziya cevirirdi."""
        with CONFIG.open(encoding="utf-8") as f:
            cfg = json.load(f)
        page = [p for p in cfg["pages"] if p["path"] == "/guide.html"][0]
        self.assertIsNone(page.get("settle"))

    def test_settle_may_be_absent(self):
        self.assertEqual(load_cfg(base_cfg())["pages"][0].get("settle"), None)

    def test_settle_none_allowed(self):
        loaded = load_cfg(base_cfg(pages=[{"path": "/a", "settle": None}]))
        self.assertIsNone(loaded["pages"][0]["settle"])

    def test_settle_for_returns_none_without_config(self):
        cfg = load_cfg(base_cfg(pages=[{"path": "/a"}]))
        self.assertIsNone(a11y_gate.settle_for(cfg, "/a"))

    def test_settle_for_returns_declared_contract(self):
        page = {"path": "/a", "settle": {"attribute": "scan-ready",
                                         "timeout_ms": 1234}}
        cfg = load_cfg(base_cfg(pages=[page]))
        self.assertEqual(a11y_gate.settle_for(cfg, "/a"),
                         {"attribute": "scan-ready", "timeout_ms": 1234})

    def test_settle_for_unknown_page_raises(self):
        cfg = load_cfg(base_cfg(pages=[{"path": "/a"}]))
        with self.assertRaises(ValueError):
            a11y_gate.settle_for(cfg, "/b")

    def test_unknown_settle_key_rejected(self):
        self.assertRejects(
            {"path": "/a", "settle": {"attribute": "scan-ready",
                                      "timeout_ms": 1, "selector": "x"}},
            "bilinmeyen")

    def test_attribute_required(self):
        self.assertRejects({"path": "/a", "settle": {"timeout_ms": 1}},
                           "attribute")

    def test_timeout_required(self):
        """Sessiz varsayilan yok: bekci suresi config'in sözlesmesidir."""
        self.assertRejects({"path": "/a", "settle": {"attribute": "scan-ready"}},
                           "timeout_ms")

    def test_attribute_must_be_body_dataset_name(self):
        for bad in ("Scan Ready", "body[data-x]", "", "1ready"):
            with self.subTest(attribute=bad):
                self.assertRejects(
                    {"path": "/a",
                     "settle": {"attribute": bad, "timeout_ms": 1}},
                    "attribute")

    def test_timeout_must_be_positive_int(self):
        for bad in (0, -1, 1.5, "1000", True, None):
            with self.subTest(timeout=bad):
                self.assertRejects(
                    {"path": "/a",
                     "settle": {"attribute": "scan-ready", "timeout_ms": bad}},
                    "timeout_ms")

    def test_timeout_has_ceiling(self):
        self.assertRejects(
            {"path": "/a",
             "settle": {"attribute": "scan-ready", "timeout_ms": 10 ** 7}},
            "timeout_ms")

    def test_settle_must_be_object(self):
        self.assertRejects({"path": "/a", "settle": "scan-ready"}, "settle")


# --------------------------------------------------------- kapı davranışı


class _FakeResponse:
    def __init__(self, status):
        self.status = status


class _FakePage:
    """Cagri sirasi kaydeden sahte sayfa."""

    def __init__(self, status=200, wait_raises=None):
        self._status = status
        self._wait_raises = wait_raises
        self.calls = []
        self.waits = []

    def goto(self, url, wait_until=None):
        self.calls.append("goto")
        self.wait_until = wait_until
        return _FakeResponse(self._status)

    def wait_for_selector(self, selector, timeout=None, **kw):
        self.calls.append("wait_for_selector")
        # state KAYDEDILIR, yutulmaz: bu parametre yutuldugu icin
        # "visible" varsayilaninin yanlis FAIL urettigi kusur testten
        # kacmisti (olcum 2026-10-03). Sozlesme artik burada kilitli.
        self.waits.append((selector, timeout, kw.get("state")))
        self.states = getattr(self, "states", [])
        self.states.append(kw.get("state"))
        if self._wait_raises is not None:
            raise self._wait_raises

    def add_script_tag(self, content):
        self.calls.append("add_script_tag")

    def evaluate(self, script):
        self.calls.append("evaluate")
        return {"violations": [], "incomplete": []}


class _FakeBrowser:
    def __init__(self, page):
        self.page = page

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self.page

    def close(self):
        return None


class _FakePW:
    def __init__(self, page):
        self.chromium = types.SimpleNamespace(
            launch=lambda headless=True: _FakeBrowser(page))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakePlaywrightPatch:
    def __init__(self, page):
        self.page = page
        self._saved = {}

    def __enter__(self):
        pw = _FakePW(self.page)
        mod = types.ModuleType("playwright")
        api = types.ModuleType("playwright.sync_api")
        api.sync_playwright = lambda: pw
        mod.sync_api = api
        for name, m in (("playwright", mod), ("playwright.sync_api", api)):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = m
        return self

    def __exit__(self, *exc):
        for name, old in self._saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        return False


class SettleGateBehaviourTests(unittest.TestCase):
    """Kapı bekciyi bekler; gelmezse FAIL. once de tarar, sonra da."""

    SETTLE = {"attribute": SETTLE_ATTRIBUTE, "timeout_ms": 15000}

    def test_waits_for_declared_witness(self):
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            results, url, info = a11y_gate.playwright_connect(
                "http://127.0.0.1:1", "axe", "/preview.html",
                settle=self.SETTLE)
        self.assertEqual(page.waits,
                         [("body[data-scan-ready=\'1\']", 15000, "attached")])
        self.assertEqual(url, "http://127.0.0.1:1/preview.html")
        self.assertEqual(results, {"violations": [], "incomplete": []})
        self.assertIsNotNone(info)

    def test_axe_runs_after_the_wait(self):
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            a11y_gate.playwright_connect("http://127.0.0.1:1", "axe",
                                        "/preview.html", settle=self.SETTLE)
        self.assertEqual(page.calls,
                         ["goto", "wait_for_selector", "add_script_tag",
                          "evaluate"])

    def test_wait_matches_attachment_not_visibility(self):
        """Bekleme GÖRÜNÜRLÜK değil VARLIK ölçütü kullanmalı.

        Playwright `wait_for_selector` varsayılanı `state="visible"`. Gövde
        gizliyken (ör. bir tema/stil sayfayı gizledi) işaret kurulmuş olsa
        bile bekleme zaman aşımına düşer ve kapı HAZIR sayfayı FAIL eder.
        Ölçüm 2026-10-03: visibility:hidden + işaret VAR → default TIMEOUT
        4008 ms; `state="attached"` → OK 21 ms.
        """
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            a11y_gate.playwright_connect("http://127.0.0.1:1", "axe",
                                        "/preview.html", settle=self.SETTLE)
        self.assertEqual(page.states, ["attached"],
                         "bekleme state='attached' ile yapilmali; "
                         "varsayilan 'visible' yanlis FAIL uretir")

    def test_timeout_is_fail_closed(self):
        page = _FakePage(wait_raises=RuntimeError("Timeout 15000ms exceeded"))
        with _FakePlaywrightPatch(page):
            with self.assertRaises(a11y_gate.PageLoadError) as ctx:
                a11y_gate.playwright_connect("http://127.0.0.1:1", "axe",
                                             "/preview.html",
                                             settle=self.SETTLE)
        message = str(ctx.exception)
        self.assertIn(SETTLE_ATTRIBUTE, message)
        self.assertIn("/preview.html", message)
        self.assertNotIn("add_script_tag", page.calls,
                         "tarama yapilmadi; tarayici bosuna acilip kapandi mi?")

    def test_no_settle_means_no_wait(self):
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            _results, _url, info = a11y_gate.playwright_connect(
                "http://127.0.0.1:1", "axe", "/guide.html")
        self.assertNotIn("wait_for_selector", page.calls)
        self.assertIsNone(info)

    def test_load_state_stays_load(self):
        """networkidle iki EventSource yuzunden gelmiyor (olcu: 2 s TIMEOUT)."""
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            a11y_gate.playwright_connect("http://127.0.0.1:1", "axe",
                                        "/preview.html", settle=self.SETTLE)
        self.assertEqual(page.wait_until, "load")

    def test_measurement_recorded(self):
        page = _FakePage()
        with _FakePlaywrightPatch(page):
            _results, _url, info = a11y_gate.playwright_connect(
                "http://127.0.0.1:1", "axe", "/preview.html",
                settle=self.SETTLE)
        self.assertEqual(info["attribute"], SETTLE_ATTRIBUTE)
        self.assertEqual(info["timeout_ms"], 15000)
        self.assertIsInstance(info["waited_ms"], int)


# ------------------------------------------------------ preview.js kaynagi


class PreviewJsSettleContractTests(unittest.TestCase):
    """Hazir isareti dashboard'da dogar; kapinin uydurdugu bir sey degil."""

    @classmethod
    def setUpClass(cls):
        cls.src = PREVIEW_JS.read_text(encoding="utf-8")

    def body(self, func_name):
        match = re.search(
            r"function %s\([^)]*\) \{(.*?)\n\}" % func_name,
            self.src, re.S)
        self.assertIsNotNone(match, "%s bulunamadi" % func_name)
        return match.group(1)

    def test_counter_helpers_exist(self):
        self.assertIn("function scanPendingBegin(", self.src)
        self.assertIn("function scanPendingEnd(", self.src)

    def test_counter_floors_at_zero(self):
        """Iki kez end bir kez begin: negatif sayaç 'hazır' demeye
        devam ederdi (ya da tersi) — sessiz bir kayma."""
        body = self.body("scanPendingEnd")
        self.assertIn("Math.max(0", body)

    def test_ready_marker_written_at_zero(self):
        body = self.body("scanPendingEnd")
        self.assertRegex(body, r"dataset\.scanReady\s*=\s*[\"']1[\"']")

    def test_marker_attribute_matches_config(self):
        """preview.js'in yazdigi dataset ana == config'in bekledigi attribute.

        dashboard `dataset.scanReady`, kapı `body[data-scan-ready]` bekliyor;
        ikisi bir gün ayrışırsa kapı settle tavanı kadar bekleyip FAIL eder
        sessiz kalmaz, ama nedeni bulmak zor olur. Burada kilitliyoruz.
        """
        match = re.search(r"dataset\.(scanReady)\s*=\s*[\"']1[\"']", self.src)
        self.assertIsNotNone(match, "dataset.scanReady yazımı bulunamadı")
        camel = match.group(1)
        dashed = re.sub(r"(?<!^)(?=[A-Z])", "-", camel).lower()
        with CONFIG.open(encoding="utf-8") as f:
            cfg = json.load(f)
        page = [p for p in cfg["pages"] if p["path"] == "/preview.html"][0]
        self.assertEqual(page["settle"]["attribute"], dashed)

    def test_init_invokes_every_counted_loader(self):
        """Yükleyici tanimi degil, init CAGRISI sinyali yakalar.

        2026-10-09 kaniti: loadDeterminismTrend() hicbir zaman
        cagril-mamis — panel sonsuza dek "veri yok" (Vercel'de canli
        gozlemlendi: API 6 satir donerken badge hic yanmadi, fonksiyon
        elle cagrilinca aninda render etti). Sayac sozlesmesi yalniz
        CAGRILAN yukleyicileri sayar; hic cagrilmayan yuzey kapidan
        sessiz gecer (all-skip ailesi) — yuzey ile cagri ayni anda
        sabitlenmeli.
        """
        for func in ("loadTrend", "loadOverrideTrend",
                     "loadDeterminismTrend"):
            with self.subTest(func=func):
                self.assertRegex(
                    self.src,
                    r"(?m)^%s\(\);" % func,
                    "%s init'de top-level cagrilmiyor" % func)

    def test_every_data_fetch_is_counted(self):
        """Uc fetch ucu da sayilir: sayilmayan fetch, isaretin once
        yanmasi demektir (kapı yarim yuzeyi tarar)."""
        for func, endpoint in (("loadTrend", "/api/trend"),
                               ("loadOverrideTrend", "/api/override-trend"),
                               ("loadDeterminismTrend",
                                "/api/determinism-trend")):
            with self.subTest(func=func):
                body = self.body(func)
                self.assertIn(endpoint, body)
                self.assertIn("scanPendingBegin()", body)
                self.assertEqual(body.count("scanPendingBegin()"), 1,
                                 "%s: fetch basina tam bir begin" % func)

    def test_counter_closed_exactly_once_in_finally(self):
        """Sayac `finally` ile, TEK noktada kapanir.

        `then`/`catch` gövdesinin sonunda kapatmak iki ayri kapatma noktasi
        demekti; ama ikisi de render'dan sonra geldiği icin render
        istisna attiginda HICBIRI calismiyordu -> sayaç 1'de asili kalir,
        isaret hic yanmaz, kapı taradigi yuzeyi gormeden FAIL verir.
        `finally` render patlasa da calisir: hata sinifinin tamami kapali.
        """
        for func in ("loadTrend", "loadOverrideTrend", "loadDeterminismTrend"):
            with self.subTest(func=func):
                body = self.body(func)
                self.assertEqual(
                    body.count("scanPendingEnd()"), 1,
                    "%s: sayac tek noktada kapanmali (finally)" % func)
                self.assertRegex(body, r"\.finally\(\s*\(\)\s*=>\s*scanPendingEnd\(\)\s*\)",
                                 "%s: kapatma `.finally` icinde olmali" % func)

    def test_catch_body_cannot_throw_before_closing(self):
        """`catch` gövdesi de istisna atmamali: `then` ve `catch` ayni
        render'i cagirip ikisi de patlayabilirdi. `finally` bunu yine de
        kurtarir ama test, ilk savunma hattinin yerinde durdugunu sabitler."""
        body = self.body("loadTrend")
        self.assertIn("const el = $(\"trend-legend\");", body)
        self.assertIn("if (el) el.textContent", body)
        self.assertNotIn('$("trend-legend").textContent', body)

    def test_begin_precedes_fetch(self):
        for func in ("loadTrend", "loadOverrideTrend", "loadDeterminismTrend"):
            with self.subTest(func=func):
                body = self.body(func)
                self.assertLess(body.index("scanPendingBegin()"),
                                body.index("fetch("))

    def test_no_markup_attribute_smuggling(self):
        """Isaret innerHTML ile degil, DOM API ile yazilmali (CSP ve
        escaping: attribute degeri sayfa icinden geliyor)."""
        self.assertNotIn('innerHTML = "1"', self.src)


# ------------------------------------------------------------- workflow


class WorkflowSeedContractTests(unittest.TestCase):
    """a11y job'i kendi gecmisini uretir: artifact'a baglanmaz."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        start = cls.text.index("\n  a11y-gate:")
        end = cls.text.index("\n  #", start + 10)
        cls.job = cls.text[start:end]

    def test_job_seeds_history(self):
        self.assertIn("seed_a11y_history.py", self.job)

    def test_seed_targets_preview_dir(self):
        self.assertRegex(self.job,
                         r"seed_a11y_history\.py[\s\S]{0,200}--out\s+_calisma/CIKTI/history\.jsonl")

    def test_seed_declares_row_count(self):
        self.assertRegex(self.job, r"--rows\s+\d+")

    def test_seed_runs_before_server_start(self):
        self.assertLess(self.job.index("seed_a11y_history.py"),
                        self.job.index("preview_server.py"))

    def test_job_does_not_depend_on_run_history_artifact(self):
        """Capraz-job artifact bagimliligi kabul edilmedi: a11y kapisi tek
        basina, deterministik bir gecmisle calisir. Denetim yorum metnine
        degil, GERCEK indirme adimina bakar (yorumda 'run-history' gecmesi
        kasitlidir)."""
        self.assertNotIn("actions/download-artifact", self.job)
        self.assertNotIn("run-history/history.jsonl", self.job)
        self.assertNotIn("run-history/", self.job)

    def test_gate_step_passes_settle_config(self):
        self.assertIn("a11y_gate.py", self.job)
        self.assertIn("a11y_gate_config.json", self.job + "--base-url")


if __name__ == "__main__":
    unittest.main()
