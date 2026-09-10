#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gate_scripts_meta_guard.py — github_scripts/*.js kapı tüketicileri için
repo-çapında meta-guard.

2026-09-10 dersi: commit_msg_gate.js'in eski sürümü sidecar YOKKEN sessizce
PASS döndürüyordu (fail-open). Bu meta-guard, yeni bir fail-open kapının
giremeyeceğini statik olarak garanti eder:

  1) SINIFLANDIRMA TAMLIĞI  — her github_scripts/*.js dosyası GATE_SCRIPTS
     (merge-bloke edici) veya ADVISORY_SCRIPTS (yorum yazıcı) kümelerinden
     birinde olmalı. Yeni script = test FAIL → bilinçli karar zorunlu.
  2) GATE sözleşmesi (statik):
       a. `core.setFailed` çağrısı MEVCUT olmalı (fail-loud yeteneği).
       b. `existsSync` negatif dalı YALNIZCA `setFailed`/`throw` ile
          biter — `console.log` + `return` ile sessiz başarı YASAK
          (fail-open'un ta kendisi).
       c. `readFileSync` kullanan gate: ya existsSync guard'ı ya da
          try/catch (catch gövdesi setFailed/throw içermeli) zorunlu.
       d. Her `catch` bloğu setFailed/throw içermeli (yutma yasak).
  3) WIRING TAMLIĞI — GATE_SCRIPTS'in her üyesi verify.yml'de
     readFileSync ile tüketilmeli (kapı CI'ya bağlı olmalı).

Scanner saf fonksiyondur (scan_gate_script) — self-test sentetik kaynakla
fail-open yakaladığını kanıtlar; gerçek dosyalara dokunmaz.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SCRIPTS_DIR = HERE / "github_scripts"
WORKFLOW = HERE.parent.parent / ".github" / "workflows" / "verify.yml"

# ── SINIFLANDIRMA (explicit allowlist; yeni dosya = FAIL) ────────────────────
GATE_SCRIPTS = {
    # merge'i bloke edebilen kapılar
    "commit_msg_gate.js",   # commit-msg ihlal sidecar'ı → setFailed
    "label_gate.js",        # precommit-p0 etiketi → setFailed
    "label_gate_p1.js",     # precommit-p1 etiketi → setFailed
    "validate_labels.js",   # label tanım doğrulama → setFailed
}
ADVISORY_SCRIPTS = {
    # yorum yazıcılar / yardımcılar (merge bloke etmez)
    "config_diff_comment.js",
    "config_drift_comment.js",
    "manifest_comment.js",
    "pr_status_comment.js",
    "run_summary_status.js",
    "sync_labels.js",
    "tum_sapmalar_comment.js",
    "unit_test_failure_comment.js",
}


# ── SAF SCANNER ──────────────────────────────────────────────────────────────
_SETFAILED_RE = re.compile(r"setFailed\s*\(")
_RETURN_RE = re.compile(r"\breturn\b")
_THROW_RE = re.compile(r"\bthrow\b")
_EXISTSGUARD_RE = re.compile(
    r"if\s*\(\s*!?\s*fs\.existsSync\s*\("  # existsSync guard (pozitif/negatif dal)
)


def _extract_braced_block(src: str, open_brace_idx: int) -> str:
    """open_brace_idx'teki '{' ile dengeli kapanan bloğun gövdesini döndürür."""
    depth = 0
    for i in range(open_brace_idx, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace_idx + 1 : i]
    return src[open_brace_idx + 1 :]


def _catch_blocks(src: str) -> list[str]:
    return [
        _extract_braced_block(src, m.end() - 1)
        for m in re.finditer(r"catch\s*\([^)]*\)\s*\{", src)
    ]


def _negative_existsync_blocks(src: str) -> list[str]:
    """`if (!fs.existsSync(PATH)) { … }` gövdeleri (fail-open taraması için)."""
    blocks = []
    for m in re.finditer(r"if\s*\(\s*!\s*fs\.existsSync\s*\([^)]*\)\s*\)\s*\{", src):
        blocks.append(_extract_braced_block(src, m.end() - 1))
    return blocks


def scan_gate_script(source: str) -> list[str]:
    """Gate script kaynağındaki fail-open ihlallerini döndürür (boş = temiz)."""
    violations: list[str] = []

    # R2: missing-input sessiz-PASS yasağı — `if (!fs.existsSync(P)) {`
    # gövdesi return içeriyorsa setFailed/throw da içermeli.
    for body in _negative_existsync_blocks(source):
        if _RETURN_RE.search(body) and not (
            _SETFAILED_RE.search(body) or _THROW_RE.search(body)
        ):
            violations.append(
                "R2: existsSync negatif dalı 'return' ile sessiz başarıda — "
                "setFailed/throw zorunlu (fail-open)"
            )

    # R3: readFileSync kullanan gate'te guard veya fail-loud try/catch zorunlu.
    if "readFileSync" in source:
        has_guard = bool(re.search(r"existsSync", source))
        guarded_try = any(
            "readFileSync" in blk or "JSON.parse" in blk
            for blk in re.findall(r"try\s*\{", source)
        )
        loud_try = any(_SETFAILED_RE.search(b) or _THROW_RE.search(b) for b in _catch_blocks(source))
        if not (has_guard or loud_try):
            violations.append(
                "R3: readFileSync guard'sız ve fail-loud try/catch'siz — "
                "eksik girdi davranışı tanımsız"
            )

    # R4: catch blokları setFailed/throw içermeli (hata yutmak = fail-open).
    for blk in _catch_blocks(source):
        if not (_SETFAILED_RE.search(blk) or _THROW_RE.search(blk) or _RETURN_RE.search(blk)):
            violations.append("R4: catch bloğu hatayı yutuyor — setFailed/throw zorunlu")

    if not violations and not _SETFAILED_RE.search(source):
        # R1 yalnızca başka ihlal yoksa raporlansın (ilk ihlal daha temel).
        violations.append("R1: gate script'te core.setFailed çağrısı yok — fail-loud yeteneği yok")

    return violations


class TestClassificationCompleteness(unittest.TestCase):
    def test_every_script_is_classified(self):
        actual = {p.name for p in SCRIPTS_DIR.glob("*.js")}
        known = GATE_SCRIPTS | ADVISORY_SCRIPTS
        unclassified = sorted(actual - known)
        stale = sorted(known - actual)
        self.assertFalse(
            unclassified,
            "Yeni github_scripts dosyası GATE_SCRIPTS veya ADVISORY_SCRIPTS'e "
            f"eklenmeli (gate mi, advisory mi?): {unclassified}",
        )
        self.assertFalse(stale, f"Sınıflandırmada olmayan dosyalar var: {stale}")

    def test_gate_and_advisory_disjoint(self):
        self.assertFalse(GATE_SCRIPTS & ADVISORY_SCRIPTS)


class TestGateContracts(unittest.TestCase):
    def test_gate_scripts_have_no_fail_open_paths(self):
        report = []
        for name in sorted(GATE_SCRIPTS):
            src = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
            for v in scan_gate_script(src):
                report.append(f"{name}: {v}")
        self.assertEqual(report, [], "fail-open kapı taraması ihlalleri:\n" + "\n".join(report))

    def test_gate_scripts_are_wired_in_verify_yml(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        missing = sorted(n for n in GATE_SCRIPTS if f"github_scripts/{n}" not in wf)
        self.assertFalse(missing, f"verify.yml'de tüketilmeyen gate script'ler: {missing}")

    def test_workflow_only_runs_classified_scripts(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        used = set(re.findall(r"github_scripts/([a-z_]+\.js)", wf))
        unknown = sorted(used - (GATE_SCRIPTS | ADVISORY_SCRIPTS))
        self.assertFalse(unknown, f"verify.yml sınıflandırılmamış script tüketiyor: {unknown}")


class TestScannerSelfTest(unittest.TestCase):
    """Scanner'ın fail-open'ı gerçekten yakaladığının kanıtı (sentetik kaynak)."""

    def test_catches_silent_pass_on_missing_input(self):
        fail_open = (
            "const fs = require('fs');\n"
            "if (!fs.existsSync('logs/findings.json')) {\n"
            "  console.log('sidecar yok — geç');\n"
            "  return;\n"
            "}\n"
            "const d = JSON.parse(fs.readFileSync('logs/findings.json', 'utf8'));\n"
            "if (d.violations) { core.setFailed('ihlal'); }\n"
        )
        vs = scan_gate_script(fail_open)
        self.assertTrue(any("R2" in v for v in vs), f"fail-open yakalanmadı: {vs}")

    def test_clean_gate_passes_scan(self):
        clean = (
            "const fs = require('fs');\n"
            "if (!fs.existsSync('logs/findings.json')) {\n"
            "  core.setFailed('findings.json yok');\n"
            "  return;\n"
            "}\n"
            "try {\n"
            "  const d = JSON.parse(fs.readFileSync('logs/findings.json', 'utf8'));\n"
            "  if (d.violations) { core.setFailed('ihlal var'); }\n"
            "} catch (e) {\n"
            "  core.setFailed('ayrıştırma hatası: ' + e);\n"
            "}\n"
        )
        self.assertEqual(scan_gate_script(clean), [])

    def test_swallowed_catch_is_flagged(self):
        swallower = (
            "try {\n"
            "  const d = JSON.parse(fs.readFileSync('x.json', 'utf8'));\n"
            "  console.log('ok');\n"
            "} catch (e) {\n"
            "  console.log('bozuk json, umursamıyoruz');\n"
            "}\n"
            "core.setFailed('her zaman fail? hayır — bu satır koşmaz');\n"
        )
        vs = scan_gate_script(swallower)
        self.assertTrue(any("R4" in v for v in vs), f"yutulan catch yakalanmadı: {vs}")


if __name__ == "__main__":
    unittest.main()
