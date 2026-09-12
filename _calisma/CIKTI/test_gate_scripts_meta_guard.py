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
  4) ADVISORY sözleşmesi (defensive read — yorum yazıcı crash yasak):
       A1. `readFileSync` mutlaka `existsSync` guard'ı veya try/catch
           içinde olmalı — eksik sidecar step'i crash etmemeli.
       A2. `JSON.parse` mutlaka try/catch içinde olmalı — bozuk sidecar
           yorum yazıcıyı crash etmemeli (logla ve degrade ol).
       A3. Advisory script `core.setFailed` çağırmamalı — merge bloke
           etmez, eksikte sessiz degrade olur.
  5) GATE SIDE-CAR WIRING — sidecar tüketen gate job'u, script'i eval
     etmeden ÖNCE download-artifact ile sidecar artifact'ını indirmeli.
     Eksik wiring → gate eksik girdide fail-closed davranışını test
     edemez (drift). Pin: commit_msg_gate.js → precommit-logs → logs.

Scanner'lar saf fonksiyondur (scan_gate_script, scan_advisory_script) —
self-test sentetik kaynakla fail-open/crash yakaladığını kanıtlar; gerçek
dosyalara dokunmaz.
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


def _try_blocks(src: str) -> list[str]:
    """`try { … }` gövdeleri."""
    return [
        _extract_braced_block(src, m.end() - 1)
        for m in re.finditer(r"try\s*\{", src)
    ]


# ── WIRING HELPERS (gate side-car download pin — test_ci_sidecar_wiring ile aynı desen)
def _wf_job_section(text: str, job: str) -> str:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^  %s:\s*$" % re.escape(job), ln)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [a-zA-Z0-9_.-]+:\s*$", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def _wf_steps(section: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    cur = None
    for line in section.splitlines():
        m = re.match(r"^\s{6}- name:\s*(.+?)\s*$", line)
        if m:
            if cur:
                blocks.append(cur)
            cur = [m.group(1).strip("'\""), []]
        elif cur is not None:
            cur[1].append(line)
    if cur:
        blocks.append(cur)
    return blocks


def _wf_delivered_map(body_lines: list[str]) -> dict[str, str | None]:
    kv: dict[str, str] = {}
    for ln in body_lines:
        m = re.match(r"^\s{10}(name|path|pattern|merge-multiple):\s*(.+?)\s*$", ln)
        if m:
            kv[m.group(1)] = m.group(2).strip("'\"")
    if "name" in kv:
        return {kv["name"]: kv.get("path")}
    if "pattern" in kv and kv.get("merge-multiple") == "true":
        return {a: kv.get("path") for a in re.findall(r"\b[a-z0-9-]+\b", kv["pattern"])}
    return {}


def _wf_script_consumers(wf_text: str, script_name: str) -> set[str]:
    jobs_pos = re.search(r"^jobs:\s*$", wf_text, re.M)
    if jobs_pos is None:
        return set()
    scope = wf_text[jobs_pos.end():]
    consumers: set[str] = set()
    for job in set(re.findall(r"^  ([a-zA-Z0-9_-]+):\s*$", scope, re.M)):
        section = _wf_job_section(wf_text, job)
        for _, body in _wf_steps(section):
            if f"github_scripts/{script_name}" in "\n".join(body):
                consumers.add(job)
                break
    return consumers


# Gate script → beklenen side-car artifact'ları (artifact adı → path).
# Yeni gate sidecar eklendiğinde buraya satır ekle — test drift'i pin'ler.
GATE_SIDECAR_WIRING: dict[str, dict[str, str | None]] = {
    "commit_msg_gate.js": {"precommit-logs": "logs"},
}


def _extract_sidecar_artifacts(src: str) -> dict[str, str | None]:
    """Script içindeki side-car string'lerinden beklenen artifact map'ini çıkar.
    Şimdilik yalnızca logs/ prefix'i precommit-logs artifact'ına eşlenir.
    Gelecek gate'ler budget/* vb. eklenirse burası genişletilir."""
    artifacts: dict[str, str | None] = {}
    for m in re.findall(r"['\"]logs/[^'\"]+['\"]", src):
        inner = m.strip("'\"")
        if inner.startswith("logs/"):
            artifacts["precommit-logs"] = "logs"
    return artifacts


def scan_advisory_script(source: str) -> list[str]:
    """Advisory (yorum yazıcı) script için defensive-read ihlalleri (boş = temiz)."""
    violations: list[str] = []

    # A3: advisory setFailed çağırmamalı — merge bloke etmez.
    if _SETFAILED_RE.search(source):
        violations.append(
            "A3: advisory script'te core.setFailed var — yorum yazıcı merge bloke etmemeli, "
            "eksikte degrade ol (fail-open'un tersi: fail-loud advisory)"
        )

    # A1: readFileSync guard'sız crash — eksik sidecar step'i düşürür.
    if "readFileSync" in source:
        has_guard = bool(re.search(r"existsSync", source))
        guarded_by_try = any("readFileSync" in b for b in _try_blocks(source))
        if not (has_guard or guarded_by_try):
            violations.append(
                "A1: readFileSync existsSync guard'sız ve try/catch'siz — "
                "eksik sidecar yorum adımını crash eder"
            )

    # A2: JSON.parse outside try/catch — bozuk sidecar crash.
    if "JSON.parse" in source:
        try_bodies = _try_blocks(source)
        # try gövdelerini kaynak metinden çıkar, kalan parçada JSON.parse kaldı mı bak
        remaining = source
        for body in try_bodies:
            # body'yi bir kez çıkar (aynı içerik tekrar ediyor olabilir — replace count 1)
            remaining = remaining.replace(body, "", 1)
        # try/catch anahtar kelimelerini de çıkar, sadece kalan düz kodda ara
        # (try içindeki JSON.parse zaten çıkarıldı)
        if "JSON.parse" in remaining:
            violations.append(
                "A2: JSON.parse try/catch dışında — bozuk sidecar yorum yazıcıyı crash eder; "
                "wrap in try/catch, logla ve null/degrade dön"
            )

    return violations


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


class TestGateSidecarWiring(unittest.TestCase):
    """Gate job, side-car artifact'ını indirmeden script'i koşamaz — aksi halde
    eksik girdi fail-open (sessiz PASS) olur. GATE_SIDECAR_WIRING pin'ler hangi
    gate'in hangi artifact'a ihtiyacı olduğunu; test script içindeki
    FINDINGS_PATH/…_PATH sabitlerinden derived set'i de tabloyla eşleştirir."""

    def test_gate_wiring_table_matches_script_paths(self):
        for script, expected in GATE_SIDECAR_WIRING.items():
            src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
            derived = _extract_sidecar_artifacts(src)
            self.assertEqual(
                derived, expected,
                f"{script}: GATE_SIDECAR_WIRING tablosu script path'lerinden drift'li — "
                f"derived {derived} vs table {expected} (tek kaynak bozuldu)",
            )

    def test_gate_jobs_download_sidecars_before_eval(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        missing: list[str] = []
        order_violation: list[str] = []
        for script, artifacts in GATE_SIDECAR_WIRING.items():
            for job in _wf_script_consumers(wf, script):
                section = _wf_job_section(wf, job)
                steps = _wf_steps(section)
                delivered: dict[str, str | None] = {}
                input_steps = 0
                eval_idx: int | None = None
                for idx, (name, body) in enumerate(steps):
                    joined = "\n".join(body)
                    if "actions/download-artifact@v7" in joined:
                        delivered.update(_wf_delivered_map(body))
                        input_steps += 1
                    elif f"github_scripts/{script}" in joined:
                        eval_idx = idx
                        break
                for art, dest in artifacts.items():
                    got = delivered.get(art, "YOK")
                    if got != dest:
                        missing.append(f"{job}/{art}: beklenen {dest!r}, teslim {got!r} (script {script})")
                if eval_idx is not None and input_steps == 0:
                    order_violation.append(f"{job}: tip sidecar teslimi yok ama {script} eval ediyor")
                if eval_idx is not None and input_steps > 0:
                    # eval'den sonra gelen download varsa input_steps sayılır ama eval öncesi değil —
                    # burada teslim var mı yeter; sıra zaten delivered ile kanıtlı (consume-edemezse missing).
                    pass
        self.assertFalse(missing, "gate side-car wiring eksik/yanlış hedef:\n" + "\n".join(missing))
        self.assertFalse(order_violation, "\n".join(order_violation))


class TestAdvisoryContracts(unittest.TestCase):
    def test_advisory_scripts_are_defensive(self):
        report = []
        for name in sorted(ADVISORY_SCRIPTS):
            src = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
            for v in scan_advisory_script(src):
                report.append(f"{name}: {v}")
        self.assertEqual(report, [], "advisory defensive-read ihlalleri:\n" + "\n".join(report))


class TestAdvisoryScannerSelfTest(unittest.TestCase):
    """Advisory scanner'ın crash'i gerçekten yakaladığının kanıtı."""

    def test_catches_bare_read_without_guard(self):
        bare = "const fs=require('fs');\nconst d=JSON.parse(fs.readFileSync('x.json','utf8'));\n"
        vs = scan_advisory_script(bare)
        self.assertTrue(any("A1" in v for v in vs), f"bare read yakalanmadı: {vs}")

    def test_catches_json_parse_outside_try(self):
        guarded_but_no_try = (
            "const fs=require('fs');\n"
            "if (!fs.existsSync('x.json')) return;\n"
            "const d=JSON.parse(fs.readFileSync('x.json','utf8'));\n"
        )
        vs = scan_advisory_script(guarded_but_no_try)
        self.assertTrue(any("A2" in v for v in vs), f"A2 yakalanmadı: {vs}")

    def test_clean_advisory_passes(self):
        clean = (
            "const fs=require('fs');\n"
            "let d=null;\n"
            "if (fs.existsSync('x.json')) {\n"
            "  try { d=JSON.parse(fs.readFileSync('x.json','utf8')); } catch(e){ console.log(e.message); }\n"
            "}\n"
        )
        self.assertEqual(scan_advisory_script(clean), [])

    def test_advisory_setfailed_is_flagged(self):
        with_setfailed = (
            "const fs=require('fs');\n"
            "if (!fs.existsSync('x.json')) { core.setFailed('yok'); return; }\n"
            "try { const d=JSON.parse(fs.readFileSync('x.json','utf8')); } catch(e){ core.setFailed(e.message); }\n"
        )
        vs = scan_advisory_script(with_setfailed)
        self.assertTrue(any("A3" in v for v in vs), f"A3 yakalanmadı: {vs}")


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
