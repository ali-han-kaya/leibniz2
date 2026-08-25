#!/usr/bin/env python3
"""test_coverage_report.py — tüm test dosyalarını, pre-commit hook kapsamını
ve CI job sonuçlarını tek bir kapsam raporunda toplar.

Kapsam verileri iki kaynaktan gelir:
  1) Statik envanter: test_*.py dosyaları, test sayıları, pre-commit hook
     mapping'i (.pre-commit-config.yaml'dan unittest discover -p pattern'leri)
  2) Canlı CI sonuçları: gh run view --json ile en son run'un job verdict'leri

Çıktı:
  --json OUT   → JSON kapsam raporu (makine-okunur)
  --md OUT     → Markdown kapsam raporu (insan-okunur, run summary)
  --ci         → gh run view ile canlı CI sonuçlarını da ekle
  (varsayılan) → stdout'a markdown özeti

Pre-commit hook'u olarak:
  check-coverage-report:
    entry: python3 _calisma/CIKTI/test_coverage_report.py --check
    language: system
    pass_filenames: false
    always_run: true
    stages: [pre-commit]
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    yaml = None  # CI'da pyyaml kurulu olmayabilir; --check modu skip eder

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TEST_DIR = REPO_ROOT / "_calisma" / "CIKTI"


# ═══════════════════════════════════════════════════════════════════════════
# STATİK ENVANTER: her test dosyası → hangi pre-commit hook'ları kapsıyor?
# Kaynak: .pre-commit-config.yaml'daki `unittest discover -p "test_X.py"`
# pattern'lerinden ve açık script yollarından türetilir.
# ═══════════════════════════════════════════════════════════════════════════

HOOK_COVERAGE = {
    # Her hook id'si → kapsadığı test dosyaları listesi
    "check-plist-drift":       ["test_plist_gate_exit.py", "test_gen_plist_golden.py"],
    "check-repro-manifest":    ["test_gen_repro_manifest.py"],
    "check-dryrun-summary":    ["test_dryrun_summary.py"],
    "check-colorize-rules":    ["test_colorize_rules.py"],
    "check-budget-scan":       ["test_budget_scan.js"],
    "verify-delivery-repro-manifest": ["test_verify_manifest_sidecar.py"],
    "verify-delivery-github-scripts": ["test_github_scripts_battery.py"],
    "check-pattern-consistency": ["test_gen_repro_manifest.py"],
    "check-config-sync":       ["test_check_config_sync.py"],
    "check-lake-evidence":     ["test_lake_evidence_smoke.py"],
    "check-refs-table-sync":   ["test_check_refs_table_sync.py"],
    "check-changelog-sync":    ["test_update_changelog_hook.py", "test_gen_changelog.py"],
    "check-unit-tests": [
        "test_verify_refs.py",
        "test_verify_checks.py",
        "test_status_checks.py",
        "test_audit_live_ci_sync.py",
        "test_doc_artifact_sync.py",
        "test_incremental_doc_sync.py",
        "test_check_doc_wrapper_sync.py",
        "test_run_summary_refs_trend.py",
        "test_run_summary_budget.py",
        "test_run_summary_changelog.py",
        "test_run_summary_k0.py",
        "test_run_summary_klayers.py",
        "test_run_summary_lineage.py",
        "test_run_summary_precommit.py",
        "test_consolidate_summary.py",
        "test_consolidate_budget.py",
        "test_override_trend.py",
        "test_label_gate_contracts.py",
        "test_refs_trend.py",
        "test_refs_trend_badge.py",
        "test_audit_refs_trend.py",
        "test_check_repro_manifest_hook.py",
        "test_mirror_check.py",
        "test_mirror_panel.py",
        "test_check_mirror_coverage.py",
        "test_cleanup.py",
        "test_check_history.py",
        "test_preview_prestart.py",
        "test_scan_stale_zips.py",
        "test_budget_over_banner.py",
        "test_dashboard_smoke.py",
        "test_lineage_schema.py",
        "test_diff_config_artifacts.py",
        "test_validate_config_schema.py",
        "test_gen_config.py",
        "test_gen_precommit_report.py",
        "test_gen_commit_msg_evidence.py",
        "test_check_cli_overrides.py",
        "test_check_action_pins.py",
        "test_check_action_runtimes.py",
        "test_check_python3_shell.py",
        "test_check_commit_messages.py",
        "test_commit_msg_hook.py",
        "test_enforce_is_on.py",
        "test_readme_badges.py",
        "test_repack_verify.py",
        "test_setup_branch_protection.py",
        "test_preview_server.py",
        "test_fresh_clone_setup.py",
        "test_lean_lake.py",
        "test_coq_lake.py",
        "test_daemon_http.py",
        "test_k18_daemon.py",
        "test_ia_ol_fallback_evidence.py",
        "test_github_scripts.py",
        "test_check_plist_drift.py",
        "test_verify_manifest_overrides.py",
        "test_coverage_report.py",
        "test_test_coverage_report.py",
        "test_sync_check_unit_tests.py",
    ],
}

# verify.yml CI job'ları → kapsadığı test dosyaları
CI_JOB_COVERAGE = {
    "verify": [
        # verify job'ı `python3 -m unittest discover -s _calisma/CIKTI`
        # ile TÜM test_*.py dosyalarını keşfeder
        "ALL",
    ],
    "preview-reload-smoke": ["test_preview_reload_smoke.py"],
    "daemon-http": ["test_daemon_http.py"],
    "plist-check": ["test_plist_gate_exit.py", "test_gen_plist_golden.py"],
    "ci-simulate": ["ALL"],
}


def discover_test_files():
    """Tüm test dosyalarını keşfeder, test sayılarını döndürür."""
    files = {}
    for p in sorted(TEST_DIR.glob("test_*.py")):
        text = p.read_text(encoding="utf-8")
        cnt = len(re.findall(r"^\s+def test_", text, re.MULTILINE))
        files[p.name] = {"test_count": cnt, "path": str(p.relative_to(REPO_ROOT))}
    # Ayrıca JS test'leri
    for p in sorted(TEST_DIR.glob("test_*.js")):
        text = p.read_text(encoding="utf-8")
        # budget_scan.js: `assert(...)` veya `assertEq/assertDeep(...)` desenini say
        cnt = len(re.findall(r"\bassert(Eq|Deep)?\(", text))
        files[p.name] = {"test_count": cnt, "path": str(p.relative_to(REPO_ROOT))}
    return files


def build_hook_map(hook_coverage, test_files):
    """Hook → test dosyaları mapping'ini zenginleştirir."""
    result = {}
    for hook_id, file_list in hook_coverage.items():
        covered = []
        total = 0
        for tf in file_list:
            if tf in test_files:
                covered.append(tf)
                total += test_files[tf]["test_count"]
        result[hook_id] = {
            "test_files": sorted(covered),
            "test_count": total,
        }
    return result


def build_ci_job_map(ci_coverage, all_test_files):
    """CI job → test dosyaları mapping'ini zenginleştirir."""
    result = {}
    for job_id, file_list in ci_coverage.items():
        if file_list == ["ALL"]:
            covered = sorted(all_test_files.keys())
            total = sum(v["test_count"] for v in all_test_files.values())
        else:
            covered = sorted(set(file_list) & set(all_test_files.keys()))
            total = sum(all_test_files[tf]["test_count"] for tf in covered)
        result[job_id] = {
            "test_files": covered if len(covered) < 10 else [f"{len(covered)} file"],
            "test_count": total,
        }
    return result


def discover_hook_entries():
    """.pre-commit-config.yaml'dan hook id → ad listesini okur."""
    pc_path = REPO_ROOT / ".pre-commit-config.yaml"
    if not pc_path.exists() or yaml is None:
        return {}
    pc = yaml.safe_load(pc_path.read_text())
    entries = {}
    for repo in pc.get("repos", []):
        for hook in repo.get("hooks", []):
            hid = hook.get("id", "")
            name = hook.get("name", hid)
            entries[hid] = name
    return entries


def get_ci_run_data():
    """gh run view ile son CI run'ının job sonuçlarını döndürür.
    Ağ yoksa boş dict döner."""
    try:
        r = subprocess.run(
            ["gh", "run", "list", "--limit", "1", "--json", "databaseId,conclusion"],
            capture_output=True, text=True, timeout=15, cwd=str(REPO_ROOT))
        if r.returncode != 0:
            return {}
        runs = json.loads(r.stdout)
        if not runs:
            return {}
        run_id = runs[0]["databaseId"]
        conclusion = runs[0]["conclusion"]
        r2 = subprocess.run(
            ["gh", "run", "view", str(run_id), "--json", "jobs"],
            capture_output=True, text=True, timeout=15, cwd=str(REPO_ROOT))
        if r2.returncode != 0:
            return {"run_id": run_id, "conclusion": conclusion, "jobs": []}
        jobs = json.loads(r2.stdout).get("jobs", [])
        return {
            "run_id": run_id,
            "conclusion": conclusion,
            "jobs": [{"name": j.get("name","?"), "conclusion": j.get("conclusion","?"),
                       "status": j.get("status","?")} for j in jobs],
        }
    except Exception as e:
        return {"error": str(e)}


def detect_gaps(all_files, hook_map):
    """Hangi test dosyaları hiçbir hook tarafından kapsanmıyor?"""
    covered = set()
    for v in hook_map.values():
        covered |= set(v["test_files"])
    uncovered = set(all_files.keys()) - covered
    zero_tests = [k for k, v in all_files.items() if v["test_count"] == 0]
    return {
        "not_covered_by_any_hook": sorted(uncovered),
        "test_files_without_tests": zero_tests,
    }


def render_markdown(report):
    """Markdown kapsam raporu üretir."""
    t = report["totals"]
    lines = []
    lines.append("# Test Coverage Report")
    lines.append(f"**Generated:** {report['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Test files | {t['test_files']} |")
    lines.append(f"| Test methods (Python) | {t['test_methods']} |")
    lines.append(f"| Pre-commit hooks with tests | {t['pre_commit_hooks']} |")
    lines.append(f"| CI jobs running tests | {t['ci_jobs_that_run_tests']} |")
    lines.append(f"| Files not covered by any hook | {t['uncovered_files']} |")

    lines.append("")
    lines.append("## Pre-commit Hook Coverage")
    lines.append("| Hook | Name | Test Files | Test Count |")
    lines.append("|---|---|---|---|")
    hks = sorted(report["hook_coverage"].items(),
                 key=lambda x: -x[1]["test_count"])
    for hid, info in hks:
        name = report.get("hook_names", {}).get(hid, hid)
        fcount = len(info["test_files"])
        lines.append(f"| `{hid}` | {name} | {fcount} | {info['test_count']} |")

    lines.append("")
    lines.append("## CI Job Test Coverage")
    lines.append("| Job | Test Count |")
    lines.append("|---|---|")
    for jid, info in sorted(report["ci_job_coverage"].items()):
        lines.append(f"| `{jid}` | {info['test_count']} |")

    # CI run data (if available)
    if report.get("ci_run"):
        cr = report["ci_run"]
        if cr.get("run_id"):
            lines.append("")
            lines.append("## Last CI Run")
            lines.append(f"- **Run ID:** {cr['run_id']}")
            lines.append(f"- **Conclusion:** `{cr.get('conclusion', '?')}`")
            lines.append(f"- **Jobs:** {len(cr.get('jobs', []))}")
            if cr.get("jobs"):
                lines.append("")
                lines.append("| Job | Conclusion | Status |")
                lines.append("|---|---|---|")
                for j in cr["jobs"]:
                    conc = j.get("conclusion", "?")
                    icon = {"success": "✅", "failure": "❌", "skipped": "⏭"}.get(conc, "❓")
                    lines.append(f"| {j['name']} | {icon} {conc} | {j['status']} |")

    # Gaps
    gaps = report.get("gaps", {})
    if gaps.get("not_covered_by_any_hook"):
        lines.append("")
        lines.append("## ⚠️  Gaps: Files Not Covered by Any Pre-commit Hook")
        for f in gaps["not_covered_by_any_hook"]:
            lines.append(f"- `{f}`")

    if gaps.get("test_files_without_tests"):
        lines.append("")
        lines.append("## ⚠️  Files With Zero Tests")
        for f in gaps["test_files_without_tests"]:
            lines.append(f"- `{f}`")

    return "\n".join(lines)


def build_report(test_files, hook_map, ci_map, hook_names, ci_data=None):
    """Tam kapsam raporunu oluşturur."""
    gaps = detect_gaps(test_files, hook_map)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "test_files": len(test_files),
            "test_methods": sum(v["test_count"] for v in test_files.values()),
            "pre_commit_hooks": len(hook_map),
            "ci_jobs_that_run_tests": len(ci_map),
            "uncovered_files": len(gaps["not_covered_by_any_hook"]),
        },
        "test_files": test_files,
        "hook_coverage": hook_map,
        "ci_job_coverage": ci_map,
        "hook_names": hook_names,
        "gaps": gaps,
        "ci_run": ci_data or {},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Test coverage report aggregator")
    ap.add_argument("--json", dest="json_out", help="JSON output file")
    ap.add_argument("--md", dest="md_out", help="Markdown output file")
    ap.add_argument("--ci", action="store_true", help="Include live CI run data")
    ap.add_argument("--check", action="store_true",
                    help="Fail if any test file is uncovered (for pre-commit)")
    args = ap.parse_args(argv)

    test_files = discover_test_files()
    hook_map = build_hook_map(HOOK_COVERAGE, test_files)
    ci_map = build_ci_job_map(CI_JOB_COVERAGE, test_files)
    hook_names = discover_hook_entries()

    ci_data = None
    if args.ci:
        ci_data = get_ci_run_data()

    report = build_report(test_files, hook_map, ci_map, hook_names, ci_data)

    md = render_markdown(report)

    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"[coverage-report] JSON: {args.json_out}", file=sys.stderr)

    if args.md_out:
        pathlib.Path(args.md_out).write_text(md)
        print(f"[coverage-report] Markdown: {args.md_out}", file=sys.stderr)

    if not args.json_out and not args.md_out:
        print(md)

    # Pre-commit check mode: yalnızca gerçek test dosyalarını kontrol et
    # (meta dosyalar, smoke script'leri, JS-only testleri hariç)
    CHECK_EXEMPT = frozenset({
        "test_coverage_report.py",      # meta: kendi kendini test edemez
        "test_test_coverage_report.py",  # meta: kendini test eder, ayrıca check-unit-tests'te
        "test_preview_reload_smoke.py",  # standalone smoke script, def test_ yok
        "test_all_hooks_smoke.py",       # standalone smoke: tum hook'lari kosar
        "test_budget_scan.js",          # JS-only, ayrı Node hook'unda
    })
    if args.check:
        gaps = [g for g in report["gaps"]["not_covered_by_any_hook"]
                if g not in CHECK_EXEMPT]
        if gaps:
            print(f"\nFAIL: {len(gaps)} test file(s) uncovered by any pre-commit hook:", file=sys.stderr)
            for g in gaps:
                print(f"  - {g}", file=sys.stderr)
            print("Add them to HOOK_COVERAGE in test_coverage_report.py or to a hook in .pre-commit-config.yaml", file=sys.stderr)
            return 1
        print("PASS: all test files covered by at least one pre-commit hook", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())