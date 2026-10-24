#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_generated_surfaces.py — "üret + tara" kapısının sözleşmesi.

Sınıf garantisi: commit dışı üretilmiş bir yüzeyi denetleyen kapı "dosya yok"
diye SKIP edemez; kapı yüzeyi ÜRETİR ve TARAR. Bu süit kapının kendisini
kırmızıya düşürebildiğini kanıtlar (boş/yanlış kanıt üretmediğini):

  1. envanter bütünlüğü (üretici/çıktı/tarayıcı beyanları tutarlı),
  2. gerçek üretim + tarama yeşil (design_preview),
  3. tarayıcı MUTASYONLA kırmızıya düşüyor (inline handler enjekte edilince),
  4. üretici patlarsa / çıktı yazılmazsa kapı FAIL (SKIP değil),
  5. `--strict` araç yokluğunda SKIP'i FAIL'e çeviriyor,
  6. beyan edilen üretici/tarayıcı metni yoksa "hayalet kayıt" FAIL,
  7. kapsam denetimi sınıflandırılmamış gitignore'lu yolu YAKALIYOR.

stdlib-only, OFFLINE. Yazma hedefleri geçici dizinlerdir; repo kirlenmez.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import generated_surfaces as registry  # noqa: E402
import check_generated_surfaces as gate  # noqa: E402

GIT = shutil.which("git")


class TestRegistryIntegrity(unittest.TestCase):
    def test_ids_unique_and_scanners_known(self):
        ids = [s.id for s in registry.BUILD] + [c.id for c in registry.CLASSIFIED]
        self.assertEqual(len(ids), len(set(ids)), "envanterde çift id: %r" % ids)
        for surface in registry.BUILD:
            self.assertIn(surface.scan, registry.SCANS,
                          "%s: bilinmeyen tarayıcı" % surface.id)
            self.assertTrue(surface.outputs, "%s: çıktı beyanı yok" % surface.id)
            self.assertTrue(pathlib.Path(surface.generator[0]).exists()
                            or shutil.which(surface.generator[0]),
                            "%s: üretici bulunamadı: %r"
                            % (surface.id, surface.generator[0]))

    def test_classified_claims_point_at_real_text(self):
        for entry in registry.CLASSIFIED:
            self.assertEqual(registry.verify_classified(entry), [],
                             "%s: beyan edilen üretici/tarayıcı gerçek değil"
                             % entry.id)

    def test_phantom_claim_is_reported(self):
        """Kayıt var, yürütme yok → fail-open; kapı bunu yakalamalı."""
        bogus = dataclasses.replace(registry.CLASSIFIED[0],
                                    owner_snippet="!!bu metin hicbir dosyada yok!!")
        problems = registry.verify_classified(bogus)
        self.assertTrue(problems, "hayalet üretici beyanı yakalanmadı")
        self.assertIn("hayalet", " ".join(problems))

    def test_design_preview_is_a_build_surface(self):
        """design_preview.html bu sınıfın kaynak örneği: BUILD olarak kalmalı."""
        entry = next(s for s in registry.BUILD
                     if s.id == "design_preview_html")
        self.assertTrue(entry.fast, "pre-commit hızlı yolunda olmalı")
        self.assertEqual(entry.outputs, ("{out}",))


class TestBuildAndScan(unittest.TestCase):
    def test_design_preview_builds_and_scans_clean(self):
        surface = next(s for s in registry.BUILD if s.id == "design_preview_html")
        row = gate.run_build(surface, strict=True)
        self.assertEqual(row["status"], "PASS", row["problems"])
        self.assertGreaterEqual(row["outputs"]["design_preview.html"], 50_000,
                                "artifact beklenmedik derecede küçük")
        self.assertEqual(row["problems"], [])

    def test_scan_detects_injected_inline_handler(self):
        """Tarayıcı boş değil: gerçek VERIFY-001 ihlalini yakalar."""
        surface = next(s for s in registry.BUILD if s.id == "design_preview_html")
        with tempfile.TemporaryDirectory(prefix="gen-surface-mut-") as td:
            out = pathlib.Path(td) / "design_preview.html"
            proc = registry.generate(surface, out=out)
            self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
            html = out.read_text(encoding="utf-8")
            mutated = html.replace(
                '<div id="tip"',
                '<rect x="0" y="0" width="1" height="1" '
                'onmousemove="showRefsTrendTip(0, event)"/><div id="tip"', 1)
            self.assertNotEqual(mutated, html, "mutasyon çapası bulunamadı")
            out.write_text(mutated, encoding="utf-8")
            problems = registry.scan(surface, registry.output_paths(surface, out))
        self.assertTrue(any("inline event-handler" in p for p in problems),
                        "enjekte edilen handler yakalanmadı: %r" % problems)

    def test_scan_detects_missing_output(self):
        surface = next(s for s in registry.BUILD if s.id == "design_preview_html")
        with tempfile.TemporaryDirectory(prefix="gen-surface-miss-") as td:
            out = pathlib.Path(td) / "design_preview.html"
            problems = registry.scan(surface, registry.output_paths(surface, out))
        self.assertTrue(any("üretilmedi" in p for p in problems), problems)

    def test_broken_generator_fails_the_gate(self):
        broken = registry.Surface(
            id="broken_producer",
            generator=(sys.executable, "-c", "raise SystemExit(3)"),
            cwd=HERE, outputs=("{out}",), scan="design_preview")
        row = gate.run_build(broken, strict=True)
        self.assertEqual(row["status"], "FAIL")
        self.assertTrue(any("rc=3" in p for p in row["problems"]), row)

    def test_generator_without_output_fails_the_gate(self):
        silent = registry.Surface(
            id="silent_producer",
            generator=(sys.executable, "-c", "pass"),
            cwd=HERE, outputs=("{out}",), scan="design_preview")
        row = gate.run_build(silent, strict=True)
        self.assertEqual(row["status"], "FAIL")
        self.assertTrue(any("beyan edilen çıktı yok" in p
                           for p in row["problems"]), row)


class TestStrictSemantics(unittest.TestCase):
    def test_missing_tools_skip_without_strict_and_fail_with_strict(self):
        surface = next(s for s in registry.BUILD
                       if s.id == "video_player_bundle")
        with mock.patch.object(registry, "unmet_requirements",
                              return_value=["node"]):
            lenient = gate.run_build(surface, strict=False)
            strict = gate.run_build(surface, strict=True)
        self.assertEqual(lenient["status"], "SKIP")
        self.assertEqual(strict["status"], "FAIL",
                         "--strict SKIP'i kabul etmemeli (CI fail-closed)")


class TestCoverageAudit(unittest.TestCase):
    def test_real_repo_has_no_unclassified_surface(self):
        problems = registry.audit_unclassified(registry.REPO)
        self.assertEqual(problems, [],
                         "sınıflandırılmamış gitignore'lu yüzey(ler) — "
                         "generated_surfaces.py'ye ekle: %r" % (problems,))

    def test_known_and_unknown_paths(self):
        self.assertTrue(registry.covers("design_preview.html"))
        self.assertTrue(registry.covers("_calisma/CIKTI/demo.json")
                        is False, "rastgele yol kapsanmamalı")
        self.assertTrue(registry.covers("logs/k12_repro_manifest.json"))
        self.assertTrue(registry.covers("_calisma/CIKTI/history.jsonl"))
        # Bare adla referanslanan gitignore'lu sidecar'lar (kök .gitignore
        # `/player_routes.json` + `/a11y_*.json`) kapsanır; aksi halde
        # --audit bunları "sınıflandırılmamış" diye kırmızıya düşürürdü.
        for path in ("player_routes.json", "trend_sync.json",
                     "a11y_dashboard_dark.json",
                     "_calisma/CIKTI/trend_sync.json"):
            self.assertTrue(registry.covers(path), "%s kapsanmıyor" % path)

    @unittest.skipUnless(GIT, "git yok")
    def test_unclassified_literal_is_detected_end_to_end(self):
        """Kapsam denetimi gerçekten kırmızıya düşebiliyor mu? (sentetik repo)"""
        with tempfile.TemporaryDirectory(prefix="gen-audit-") as td:
            root = pathlib.Path(td)
            (root / "_calisma" / "CIKTI").mkdir(parents=True)
            (root / ".gitignore").write_text(
                "_calisma/CIKTI/synthetic_orphan_sidecar.json\nlogs/\n",
                encoding="utf-8")
            subprocess.run([GIT, "init", "-q", "."], cwd=str(root), check=True)
            (root / "_calisma" / "CIKTI" / "gate.py").write_text(
                'ARTIFACT = "_calisma/CIKTI/synthetic_orphan_sidecar.json"\n'
                'LOGS = "logs/report.json"\n', encoding="utf-8")
            # JS kapı/test kaynakları da taranır: sınıf garantisi yalnız
            # Python'a daralırsa .js tarafındaki yüzey görünmez kalır.
            (root / "_calisma" / "CIKTI" / "gate.js").write_text(
                'const bundle = "_calisma/CIKTI/synthetic_orphan_bundle.js";\n',
                encoding="utf-8")
            (root / ".gitignore").write_text(
                "_calisma/CIKTI/synthetic_orphan_sidecar.json\n"
                "_calisma/CIKTI/synthetic_orphan_bundle.js\nlogs/\n",
                encoding="utf-8")
            problems = registry.audit_unclassified(root)
        found = [p for p, _ in problems]
        self.assertIn("_calisma/CIKTI/synthetic_orphan_sidecar.json", found,
                      "sınıflandırılmamış yol yakalanmadı: %r" % (problems,))
        self.assertIn("_calisma/CIKTI/synthetic_orphan_bundle.js", found,
                      ".js kaynağındaki sınıflandırılmamış yol yakalanmadı: %r"
                      % (problems,))
        self.assertNotIn("logs/report.json", found,
                         "sınıflandırılmış `logs/` yanlış-pozitif üretti")


class TestCli(unittest.TestCase):
    def _run(self, *args, timeout=300):
        return subprocess.run(
            [sys.executable, str(HERE / "check_generated_surfaces.py"), *args],
            capture_output=True, text=True, timeout=timeout, cwd=str(HERE))

    def test_fast_run_passes_on_real_repo(self):
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("design_preview_html", res.stdout)

    def test_audit_mode_passes(self):
        res = self._run("--audit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("coverage_audit", res.stdout)

    def test_json_is_single_document(self):
        res = self._run("--list", "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)  # tek JSON belgesi (stdout kirlenmemiş)
        ids = [row["id"] for row in payload["surfaces"]]
        self.assertIn("design_preview_html", ids)
        self.assertIn("video_player_bundle", ids)
        self.assertIn("dashboard_next_build", ids)

    def test_help_and_bad_flag(self):
        self.assertEqual(self._run("--help").returncode, 0)
        self.assertEqual(self._run("--nope").returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
