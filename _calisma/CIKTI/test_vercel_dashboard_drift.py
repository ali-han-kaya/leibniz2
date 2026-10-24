#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_vercel_dashboard_drift.py — Vercel↔dashboard token drift raporu kapısı.

Kapı: design-system/scripts/report_vercel_dashboard_drift.py (`--check`) +
commit'li makine-okunur kopya `_calisma/CIKTI/vercel_dashboard_drift.json`.

Sözleşmeler (hepsi fail-closed):
  T1 TAZELİK       : commit'li iki kopya (JSON + markdown) jeneratör çıktısıyla
                     birebir; `--check` rc=0 ve "OK —" satırı basar.
  T2 ŞEMA/ÖLÇÜM    : JSON belgesi şemalı, `status=ok`, ve raporun SAYILARI
                     dosyalardan bağımsız türetilebilir (kategori toplamı ==
                     temel token sayısı, distinct == birleşim boyu, light
                     override adları temel kümenin alt kümesi).
  T3 DETERMİNİZM   : `--json` iki koşumda BAYT aynı; stdout TEK bir JSON
                     belgesidir (diagnostik stderr'de).
  T4 STALE GATE    : bayat bir kopya rc=1 verir (mutasyonla kanıtlanır; commit'li
                     dosyaya DOKUNULMAZ — geçici kopyalar üzerinde çalışılır).
  T5 BOZUK-DURUM   : `status=blocked` iken TAZE olsa bile `--check` rc=1 verir
                     (vacuous PASS yasağı: bozuk durumu yeniden üretip commit
                     etmek kapıyı yeşil bırakamaz).
  T6 KABLOLAMA     : CI adımı gerçekten `--check` koşar ve makine-okunur belgeyi
                     MEVCUT `logs/` artifact'ına yazar (yeni artifact adı yok);
                     pre-commit hook'u + kapsam eşlemesi bu testi işaret eder.

Koşum: `python3 -m unittest _calisma.CIKTI.test_vercel_dashboard_drift`
"""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "design-system" / "scripts" / "report_vercel_dashboard_drift.py"
JSON_OUT = REPO_ROOT / "_calisma" / "CIKTI" / "vercel_dashboard_drift.json"
MD_OUT = REPO_ROOT / "_calisma" / "CIKTI" / "VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md"
DASH_CSS = REPO_ROOT / "design-system" / "tokens.css"
VERCEL_RAW = REPO_ROOT / "design-system" / "vercel" / "raw.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "verify.yml"
PRECOMMIT = REPO_ROOT / ".pre-commit-config.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("vercel_drift_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MOD = load_module()


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def vars_in_root(text):
    match = re.search(r":root\s*\{(.*?)\}", text, re.S)
    assert match, "design-system/tokens.css: :root bloğu yok"
    return [n for n, _v in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+?)\s*;",
                                      match.group(1))]


class TestReportFreshness(unittest.TestCase):

    def test_t1_check_is_green_and_reports_counts(self):
        proc = run("--check")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK —", proc.stderr)
        self.assertEqual(proc.stdout, "",
                         "check modu stdout'a belge basmamalı (diagnostik stderr)")

    def test_t2_committed_json_schema_and_measured_numbers(self):
        payload = read_json(JSON_OUT)
        self.assertEqual(payload["schema"], "vercel-dashboard-drift/1")
        self.assertEqual(payload["status"], "ok", payload.get("findings"))
        for key in ("sources", "vercel_tokens", "dashboard_base_tokens",
                    "dashboard_light_overrides", "categories", "overlap",
                    "nearest_role", "findings"):
            self.assertIn(key, payload)

        counts = payload["categories"]["counts"]
        base = payload["dashboard_base_tokens"]
        self.assertEqual(sum(counts.values()), len(base),
                         "kategori toplamı temel token sayısına eşit değil")
        self.assertEqual(payload["categories"]["uncategorized"], [])

        overlap = payload["overlap"]
        self.assertEqual(
            overlap["distinct_css_names"],
            len(set(base) | set(payload["vercel_tokens"])))
        self.assertEqual(overlap["shared_names"],
                         sorted(set(base) & set(payload["vercel_tokens"])))
        self.assertTrue(set(payload["dashboard_light_overrides"]) <= set(base),
                        "light override adları temel kümenin alt kümesi değil")

        # Rapor SAYILARI dosyalardan bağımsız da doğrulanabilir olmalı.
        css_names = vars_in_root(DASH_CSS.read_text(encoding="utf-8"))
        self.assertEqual(sorted(css_names), base)
        raw = read_json(VERCEL_RAW)
        self.assertEqual(sorted(raw["colors"]["cssVariables"]),
                         payload["vercel_tokens"])
        self.assertEqual(payload["sources"]["vercel"]["count"],
                         len(payload["vercel_tokens"]))

        severities = {f["severity"] for f in payload["findings"]}
        self.assertTrue(severities <= {"block", "warn", "info"}, severities)
        role_names = sorted(r["vercel"] for r in payload["nearest_role"])
        self.assertEqual(role_names, payload["vercel_tokens"])

    def test_t3_json_mode_is_deterministic_and_single_document(self):
        first = run("--json")
        second = run("--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout, "JSON çıktısı deterministik değil")
        document = json.loads(first.stdout)  # tek belge: fazladan satır olsa patlar
        self.assertEqual(document["schema"], "vercel-dashboard-drift/1")
        self.assertEqual(first.stdout.count("\n"), first.stdout.rstrip("\n").count("\n") + 1)


class TestDriftGateIsNotVacuous(unittest.TestCase):
    """`--check` iki yarısı da (tazelik + yapısal sağlık) ÇÜRÜTÜLEREK kanıtlanır.

    Commit'li dosyalara DOKUNULMAZ: OUT_JSON/OUT_MD geçici kopyalara
    yönlendirilir, mutasyon orada yapılır.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.json_path = root / "vercel_dashboard_drift.json"
        self.md_path = root / "VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md"
        self.patches = [
            mock.patch.object(MOD, "OUT_JSON", self.json_path),
            mock.patch.object(MOD, "OUT_MD", self.md_path),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_t4_stale_copy_fails_closed(self):
        self.assertEqual(MOD.main([]), 0)
        self.assertTrue(self.json_path.exists())
        original = self.json_path.read_text(encoding="utf-8")
        self.assertEqual(MOD.main(["--check"]), 0, "taze kopya rc=0 olmalı")

        # Tek baytlık sapma (ör. elle düzenleme) drift sayılmalı.
        self.json_path.write_text(original + "\n", encoding="utf-8")
        self.assertEqual(MOD.main(["--check"]), 1)
        self.json_path.write_text(original, encoding="utf-8")

        # Markdown kopyası da ayrı kanaldan kilitli.
        md_original = self.md_path.read_text(encoding="utf-8")
        self.md_path.write_text(md_original.replace("19", "20", 1), encoding="utf-8")
        self.assertEqual(MOD.main(["--check"]), 1)
        self.md_path.write_text(md_original, encoding="utf-8")
        self.assertEqual(MOD.main(["--check"]), 0)

    def test_t5_blocked_status_fails_even_when_fresh(self):
        """Bozuk kaynak: kurala uymayan yeni token → kategori envanteri eksik.

        Rapor bu durumda `blocked` olur; jeneratörle yeniden üretilip commit
        edilse bile kapı rc=1 vermelidir.
        """
        broken = pathlib.Path(self.tmp.name) / "tokens.broken.css"
        text = DASH_CSS.read_text(encoding="utf-8")
        broken.write_text(
            text.replace(":root {", ":root {\n  --mystery-token: 3px;", 1),
            encoding="utf-8")

        with mock.patch.object(MOD, "DASH_CSS", broken):
            self.assertEqual(MOD.main([]), 0)
            payload = read_json(self.json_path)
            self.assertEqual(payload["status"], "blocked")
            ids = {f["id"] for f in payload["findings"]
                   if f["severity"] == "block"}
            self.assertIn("dashboard-token-uncategorized", ids)
            self.assertIn("--mystery-token", payload["categories"]["uncategorized"])
            # TAZE ama BOZUK → yine kırmızı.
            self.assertEqual(MOD.main(["--check"]), 1)
        # Patch kalkınca aynı geçici kopyalar yeniden yeşil olmalı
        # (kırmızının kaynağı fixture'ın kendisiydi).
        self.assertEqual(MOD.main([]), 0)
        self.assertEqual(MOD.main(["--check"]), 0)

    def test_t6_category_rules_cover_every_categorizable_name(self):
        """Kural kümesi boşluksuz mu: her kural en az bir adı yakalar."""
        base = read_json(JSON_OUT)["dashboard_base_tokens"]
        for key, _label, pattern in MOD.CATEGORY_RULES:
            hit = [n for n in base if re.search(pattern, n)]
            self.assertTrue(hit, "kural hiçbir token'ı yakalamıyor: %s" % key)


class TestWiring(unittest.TestCase):
    """Kapı dosyalarda GERÇEKTEN kablolu mu (metin düzeyinde pin)."""

    def test_t7_ci_step_runs_check_and_writes_into_existing_logs_artifact(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = re.search(
            r"- name: [^\n]*design-token drift[^\n]*\n(?:.*\n)*?"
            r"[^\n]*report_vercel_dashboard_drift\.py\s*\\?\s*--check",
            workflow)
        self.assertIsNotNone(
            step, "verify.yml'de raporu --check ile koşan adım yok")
        self.assertIn("logs/vercel_dashboard_drift.json", workflow)
        # Belge yeni bir artifact ADI açmadan mevcut logs/ yüklemesine girer.
        self.assertIn("name: precommit-logs", workflow)
        self.assertIn("path: logs/", workflow)
        self.assertIsNone(
            re.search(r"- name: Upload[^\n]*design[^\n]*drift", workflow),
            "ayrı bir drift artifact'ı açılmamalı — mevcut logs/ kullanılır")

    def test_t8_precommit_hook_and_coverage_mapping(self):
        config = PRECOMMIT.read_text(encoding="utf-8")
        self.assertIn("- id: check-vercel-drift-report", config)
        self.assertIn(
            "python3 design-system/scripts/report_vercel_dashboard_drift.py --check",
            config)
        sys.path.insert(0, str(REPO_ROOT / "_calisma" / "CIKTI"))
        import test_coverage_report as coverage
        self.assertEqual(
            coverage.HOOK_COVERAGE.get("check-vercel-drift-report"),
            ["test_vercel_dashboard_drift.py"],
            "HOOK_COVERAGE kaydı yok/yanlış — test hiçbir hook'ta koşmaz sayılır")


class TestConsumerDetection(unittest.TestCase):
    """Tüketim kanıtı iki biçimi tanır; boş yüzey yanlış-pozitif üretmez.

    Genişletme nedeni: preview.html artık ham katmanı değil GENERATED adapter
    varyantını (`/design-system/vercel-theme.css`) yükler; rapor tüketiciyi
    yok sayarsa `vercel-not-consumed` bulgusu bayat bir iddia olur.
    """

    def test_adapter_route_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="vercel-consumer-") as tmp:
            adapter = pathlib.Path(tmp) / "adapter.html"
            adapter.write_text(
                '<link rel="stylesheet" href="/design-system/vercel-theme.css">',
                encoding="utf-8")
            self.assertTrue(MOD.consumer_imports(adapter))
            raw = pathlib.Path(tmp) / "raw.html"
            raw.write_text('@import "design-system/vercel/tokens.css";',
                           encoding="utf-8")
            self.assertTrue(MOD.consumer_imports(raw))
            plain = pathlib.Path(tmp) / "plain.html"
            plain.write_text("<html></html>", encoding="utf-8")
            self.assertFalse(MOD.consumer_imports(plain))

    def test_committed_report_names_the_consuming_surface(self):
        payload = read_json(JSON_OUT)
        rows = {c["path"]: c["imports_vercel"]
                for c in payload["sources"]["consumers"]}
        self.assertTrue(
            rows.get("_calisma/CIKTI/preview.html"),
            "preview.html adapter varyantını yüklüyor ama rapor tüketici "
            "saymıyor: %s" % rows)
        self.assertNotIn(
            "vercel-not-consumed",
            {f["id"] for f in payload["findings"]},
            "tüketici varken 'tüketilmiyor' bulgusu kalamaz")


if __name__ == "__main__":
    unittest.main()
