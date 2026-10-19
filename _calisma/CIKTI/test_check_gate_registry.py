#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_gate_registry.py — kapı kaydı doğrulayıcısının birim testleri.

Faz 1 sözleşmesi: `_calisma/CIKTI/gate_registry.yaml` bir DEKLARASYONdur;
`check_gate_registry.py` onu üç gerçek kaynakla İKİ YÖNDE karşılaştırır ve
hiçbir şey YAZMAZ.

Katmanlar:

  1. STATİK (her ortamda koşar, PyYAML gerekmez): şema sabitlerinin
     tutarlılığı + "read-only" sözleşmesinin kaynak düzeyinde pinlenmesi
     (betikte yazma API'si yok).
  2. FİKSTÜR (PyYAML gerekir): minimal ağaç — 3 job (required/advisory/
     pr_only), 2 hook (biri varsayılan stage), 2 katman (biri core).
     Doğru kayıt → PASS; her yön ve her alan için ayrı mutasyon → FAIL.
     Mutasyonlar fixture üzerinde yapılır ki gerçek dosyalar hiç değişmesin.
  3. GERÇEK AĞAÇ (PyYAML gerekir): gerçek kayıt gerçek türetimle birebir;
     küme eşitliği iki yönde ayrıca pinlenir (bulgu listesi boş olsa bile
     sayaç kazası olmasın); CLI exit kodları ve `--json` şekli.
  4. READ-ONLY KANITI: dört dosyanın (3 kaynak + kayıt) sha256 ve
     st_mtime_ns'i `check()` ve CLI koşusundan önce/sonra ölçülür — kapı
     kendini onarmaya kalkarsa bu test kırmızı olur.
  5. GERÇEK VERİ MUTASYONU: gerçek kaynaklar geçici köke kopyalanıp bir
     gerçek job'un `runs-on`'u macos'a çevrilir → platform alanı yakalanır
     (fixture'a özgü sentetik veriyle değil, gerçek veriyle sınanır).

Kapı yeşil değilse bu modül de kırmızıdır (fail-closed; bilinçli skip yok).
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parent.parent
sys.path.insert(0, str(CIKTI))

import check_gate_registry as gate  # noqa: E402

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:  # pragma: no cover — PyYAML'sız ortam
    HAVE_YAML = False

needs_yaml = unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")


# ── 1) Statik sözleşme ─────────────────────────────────────────────────────

class StaticContractTest(unittest.TestCase):
    def test_sections_and_fields_are_consistent(self):
        self.assertEqual(set(gate.SECTIONS),
                         {"ci_jobs", "hooks", "layers"})
        for section in gate.SECTIONS:
            allowed = gate.FIELDS[section]
            self.assertTrue(allowed, f"{section}: alan kümesi boş")
            for field in gate.REQUIRED[section]:
                self.assertIn(field, allowed,
                              f"{section}: zorunlu alan `{field}` izinli "
                              "kümede değil")
        for field, allowed in gate.ENUMS.items():
            self.assertTrue(allowed, f"{field}: enum boş olamaz")

    def test_required_fields_are_compared_fields(self):
        """Zorunlu her alan türetimde de bulunmalı — yoksa 'zorunlu' boş."""
        for section, fields in gate.REQUIRED.items():
            for field in fields:
                self.assertIn(field, gate.FIELDS[section])

    def test_checker_has_no_write_api(self):
        """Read-only sözleşmesi kaynak düzeyinde: yazma çağrısı YOK."""
        import re

        source = (CIKTI / "check_gate_registry.py").read_text(encoding="utf-8")
        forbidden = (r"write_text\(", r"write_bytes\(", r"\.dump\(",
                     r"os\.replace\(", r"shutil\.copy", r"open\([^\n]*[\"']w")
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, source),
                              f"kapı yazma API'si kullanıyor: {pattern}")


# ── Fixture ────────────────────────────────────────────────────────────────

FIXTURE_WORKFLOW = """\
name: fixture
on: [push, pull_request]
jobs:
  verify:
    name: Delivery verification
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
  plist-check:
    name: Plist drift check (macOS, advisory)
    runs-on: macos-latest
    steps:
      - run: echo ok
  label-gate-p1:
    name: Pre-commit P1 label gate (optional)
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - run: echo ok
"""

FIXTURE_PRECOMMIT = """\
repos:
  - repo: local
    hooks:
      - id: hook-default
        name: default stage hook
        entry: "true"
        language: system
      - id: hook-commit-msg
        name: commit msg hook
        entry: "true"
        language: system
        stages: [commit-msg]
"""

FIXTURE_DELIVERY = """\
LAYER_LABELS = {
    "K0": "Core delivery integrity",
    "K21": "SDE determinism guard",
}
_CORE_LAYERS = frozenset({"K0"})
_OPTIONAL_LAYERS = {"K21": lambda a: True}
"""

FIXTURE_REGISTRY = {
    "version": 1,
    "ci_jobs": {
        # `verify` gerçek GATE_EXCLUDE'da değil → required
        "verify": {"severity": "required", "platform": "linux"},
        # gerçek GATE_EXCLUDE'da → advisory (macos)
        "plist-check": {"severity": "advisory", "platform": "macos"},
        # gerçek GATE_EXCLUDE'da + PR `if:` → pr_only
        "label-gate-p1": {"severity": "pr_only", "platform": "linux"},
    },
    "hooks": {
        "hook-default": {"stage": "pre-commit"},
        "hook-commit-msg": {"stage": "commit-msg"},
    },
    "layers": {
        "K0": {"label": "Core delivery integrity", "blocking": True},
        "K21": {"label": "SDE determinism guard", "blocking": False},
    },
}


def make_tree(tmp, registry=None, *, workflow=None, precommit=None,
              delivery=None):
    """Geçici kökte 3 gerçek kaynak + kayıt üret; yolu döndür."""
    root = pathlib.Path(tmp)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "_calisma" / "CIKTI").mkdir(parents=True, exist_ok=True)
    (root / gate.WORKFLOW).write_text(workflow or FIXTURE_WORKFLOW,
                                     encoding="utf-8")
    (root / gate.PRECOMMIT).write_text(precommit or FIXTURE_PRECOMMIT,
                                       encoding="utf-8")
    (root / gate.DELIVERY).write_text(delivery or FIXTURE_DELIVERY,
                                      encoding="utf-8")
    data = FIXTURE_REGISTRY if registry is None else registry
    (root / gate.REGISTRY).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    return root


def copy_real_tree(tmp):
    """Gerçek 3 kaynağı geçici köke kopyala (gerçek veriyle mutasyon için)."""
    root = pathlib.Path(tmp)
    for rel in (gate.WORKFLOW, gate.PRECOMMIT, gate.DELIVERY, gate.REGISTRY):
        src = ROOT / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return root


@needs_yaml
class FixtureTest(unittest.TestCase):
    """İki yön de ve her alan ayrı ayrı mutasyonla kanıtlanır."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _findings(self, registry=None, **kwargs):
        root = make_tree(self._tmp, registry, **kwargs)
        _derived, _registry, findings = gate.check(root)
        return findings

    def _ids(self, findings, kind):
        return {(f["section"], f["id"]) for f in findings if f["kind"] == kind}

    def test_fixture_passes(self):
        self.assertEqual(self._findings(), [])

    def test_phantom_entry_is_registry_to_reality(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["ci_jobs"]["ghost-job"] = {"severity": "required",
                                       "platform": "linux"}
        findings = self._findings(reg)
        phantom = [f for f in findings if f["kind"] == "phantom"]
        self.assertEqual(len(phantom), 1, findings)
        self.assertEqual(phantom[0]["direction"],
                         gate.DIR_REGISTRY_TO_REALITY)
        self.assertEqual(phantom[0]["id"], "ghost-job")

    def test_unregistered_gate_is_reality_to_registry(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        del reg["ci_jobs"]["verify"]
        findings = self._findings(reg)
        missing = [f for f in findings if f["kind"] == "unregistered"]
        self.assertEqual(len(missing), 1, findings)
        self.assertEqual(missing[0]["direction"],
                         gate.DIR_REALITY_TO_REGISTRY)
        self.assertEqual(missing[0]["id"], "verify")

    def test_hook_unregistered_is_caught(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        del reg["hooks"]["hook-commit-msg"]
        self.assertEqual(self._ids(self._findings(reg), "unregistered"),
                         {("hooks", "hook-commit-msg")})

    def test_layer_unregistered_is_caught(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        del reg["layers"]["K21"]
        self.assertEqual(self._ids(self._findings(reg), "unregistered"),
                         {("layers", "K21")})

    def test_phantom_layer_is_caught(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["layers"]["K99"] = {"label": "hayalet", "blocking": False}
        self.assertEqual(self._ids(self._findings(reg), "phantom"),
                         {("layers", "K99")})

    def test_severity_drift_is_field_finding(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["ci_jobs"]["verify"]["severity"] = "advisory"
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual(len(drift), 1, drift)
        self.assertEqual((drift[0]["field"], drift[0]["registry"],
                          drift[0]["derived"]),
                         ("severity", "advisory", "required"))

    def test_platform_drift_is_field_finding(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["ci_jobs"]["plist-check"]["platform"] = "linux"
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual([(f["id"], f["field"]) for f in drift],
                         [("plist-check", "platform")])

    def test_hook_stage_drift_is_field_finding(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["hooks"]["hook-commit-msg"]["stage"] = "pre-commit"
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual([(f["id"], f["field"]) for f in drift],
                         [("hook-commit-msg", "stage")])

    def test_layer_label_drift_is_field_finding(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["layers"]["K0"]["label"] = "yanlış etiket"
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual([(f["id"], f["field"]) for f in drift],
                         [("K0", "label")])

    def test_layer_blocking_drift_is_field_finding(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["layers"]["K21"]["blocking"] = True
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual([(f["id"], f["field"]) for f in drift],
                         [("K21", "blocking")])

    def test_default_stage_is_pre_commit(self):
        """`stages:` yoksa pre-commit varsayılanı — sessizce 'unknown' olmaz."""
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["hooks"]["hook-default"]["stage"] = "commit-msg"
        drift = [f for f in self._findings(reg) if f["kind"] == "field"]
        self.assertEqual([(f["id"], f["field"]) for f in drift],
                         [("hook-default", "stage")])

    # ── Şema (yanlış yazım fail-open olmamalı) ─────────────────────────────

    def test_unknown_field_fails_closed(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        # Yazım hatası: `severty` bilinmiyor, `severity` de eksik kalıyor.
        reg["ci_jobs"]["verify"] = {"severty": "required",
                                    "platform": "linux"}
        findings = self._findings(reg)
        schema = [f for f in findings if f["kind"] == "schema"]
        details = " | ".join(f["detail"] for f in schema)
        self.assertIn("severty", details, findings)
        self.assertIn("zorunlu alan eksik: severity", details, findings)

    def test_empty_section_fails_closed(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["hooks"] = {}
        findings = self._findings(reg)
        self.assertTrue(any(f["kind"] == "schema" and f["section"] == "hooks"
                            for f in findings), findings)

    def test_missing_section_fails_closed(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        del reg["layers"]
        findings = self._findings(reg)
        self.assertTrue(any(f["kind"] == "schema" and f["section"] == "layers"
                            for f in findings), findings)

    def test_bad_version_fails(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["version"] = 2
        self.assertTrue(any(f["kind"] == "schema" for f in self._findings(reg)))

    def test_invalid_enum_fails(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["ci_jobs"]["verify"]["platform"] = "windows"
        self.assertTrue(any(f["kind"] == "schema" for f in self._findings(reg)))

    def test_unknown_top_level_key_fails(self):
        reg = json.loads(json.dumps(FIXTURE_REGISTRY))
        reg["gates"] = {}
        self.assertTrue(any(f["kind"] == "schema" for f in self._findings(reg)))

    # ── Ölçüm imkânsız → exit 2 (sessiz PASS yok) ──────────────────────────

    def test_missing_registry_is_measurement_error(self):
        root = make_tree(self._tmp)
        (root / gate.REGISTRY).unlink()
        with self.assertRaises(gate.MeasurementError):
            gate.check(root)

    def test_unknown_runs_on_is_measurement_error(self):
        workflow = FIXTURE_WORKFLOW.replace("runs-on: macos-latest",
                                            "runs-on: windows-latest")
        root = make_tree(self._tmp, workflow=workflow)
        with self.assertRaises(gate.MeasurementError):
            gate.check(root)

    def test_empty_workflow_is_measurement_error(self):
        root = make_tree(self._tmp,
                         workflow="name: empty\non: [push]\njobs: {}\n")
        with self.assertRaises(gate.MeasurementError):
            gate.check(root)

    def test_duplicate_hook_ids_are_measurement_error(self):
        precommit = FIXTURE_PRECOMMIT + (
            "      - id: hook-default\n        name: dup\n"
            "        entry: \"true\"\n        language: system\n")
        root = make_tree(self._tmp, precommit=precommit)
        with self.assertRaises(gate.MeasurementError):
            gate.check(root)

    def test_missing_layer_table_is_measurement_error(self):
        root = make_tree(self._tmp, delivery="X = 1\n")
        with self.assertRaises(gate.MeasurementError):
            gate.check(root)


# ── 3) Gerçek ağaç ─────────────────────────────────────────────────────────

@needs_yaml
class RealTreeTest(unittest.TestCase):
    def test_real_tree_is_in_sync(self):
        _derived, _registry, findings = gate.check(ROOT)
        self.assertEqual(findings, [], f"kapı kaydı drift'i: {findings}")

    def test_both_directions_are_set_equal(self):
        derived = gate.derive(ROOT)
        registry = gate.load_registry(ROOT)
        for section in gate.SECTIONS:
            self.assertEqual(set(registry[section]), set(derived[section]),
                             f"{section}: kayıt ↔ türetim küme eşitliği bozuk")
        self.assertGreater(len(derived["ci_jobs"]), 0)
        self.assertGreater(len(derived["hooks"]), 0)
        self.assertGreater(len(derived["layers"]), 0)

    def test_cli_pass_and_json_shape(self):
        r = subprocess.run(
            [sys.executable, str(CIKTI / "check_gate_registry.py"), "--json"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(set(payload["counts"]), set(gate.SECTIONS))
        for value in payload["counts"].values():
            self.assertGreater(value, 0)

    def test_cli_measurement_error_is_exit_2(self):
        empty = pathlib.Path(tempfile.mkdtemp())
        try:
            r = subprocess.run(
                [sys.executable, str(CIKTI / "check_gate_registry.py"),
                 "--root", str(empty)], capture_output=True, text=True,
                cwd=ROOT)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("ÖLÇÜM İMKÂNSIZ", r.stderr)
            rj = subprocess.run(
                [sys.executable, str(CIKTI / "check_gate_registry.py"),
                 "--root", str(empty), "--json"],
                capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(rj.returncode, 2)
            self.assertEqual(json.loads(rj.stdout)["verdict"], "ERROR")
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_read_only_sources_and_registry_unchanged(self):
        """Kapı hiçbir şey yazmaz: sha256 + st_mtime_ns birebir kalmalı."""
        watched = [ROOT / rel for rel in (gate.WORKFLOW, gate.PRECOMMIT,
                                          gate.DELIVERY, gate.REGISTRY)]

        def snapshot():
            return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(),
                             p.stat().st_mtime_ns) for p in watched}

        before = snapshot()
        gate.derive(ROOT)
        gate.check(ROOT)
        subprocess.run([sys.executable, str(CIKTI / "check_gate_registry.py"),
                        "--json"], capture_output=True, text=True, cwd=ROOT,
                       check=False)
        self.assertEqual(snapshot(), before,
                         "kapı kaynak/kayıt dosyalarını değiştirdi (read-only "
                         "sözleşmesi ihlali)")

    def test_real_data_mutation_is_caught(self):
        """Gerçek kaynakların kopyasında platform mutasyonu yakalanır."""
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            root = copy_real_tree(tmp)
            text = (root / gate.WORKFLOW).read_text(encoding="utf-8")
            # İlk `runs-on: ubuntu-latest` → macos (platform alanı kırılır)
            mutated = text.replace("runs-on: ubuntu-latest",
                                   "runs-on: macos-latest", 1)
            self.assertNotEqual(mutated, text, "mutasyon uygulanamadı")
            (root / gate.WORKFLOW).write_text(mutated, encoding="utf-8")
            _derived, _registry, findings = gate.check(root)
            drift = [f for f in findings if f["kind"] == "field"
                     and f["field"] == "platform"]
            self.assertTrue(drift, f"platform mutasyonu yakalanmadı: {findings}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
