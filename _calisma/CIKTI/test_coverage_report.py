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
import ast
import fnmatch
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import unittest
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
    "verify-delivery-sde":       ["test_check_sde_determinism.py"],
    "texlive-repro-documented":  ["test_texlive_repro_documented.py"],
    "check-z3-slide-sync":       ["test_render_z3_slides.py", "test_render_equation_gallery.py", "test_z3_slide_reproducibility.py"],
    "check-latex-surface":      ["test_check_latex_surface.py"],
    "check-seal-hash":          ["test_check_seal_hash.py"],
    "check-pattern-consistency": ["test_gen_repro_manifest.py"],
    "check-config-sync":       ["test_check_config_sync.py"],
    "check-lake-evidence":     ["test_lake_evidence_smoke.py"],
    "check-refs-table-sync":   ["test_check_refs_table_sync.py"],
    "check-bibliography-sync": ["test_check_bibliography_sync.py"],
    "check-review-freshness":  ["test_check_review_freshness.py"],
    "check-zip-lineage-drift": ["test_check_zip_lineage_drift.py"],
    "check-doc-artifact-sync": ["test_doc_artifact_sync.py"],
    "check-skills-index":       ["test_skills_index.py", "test_readme_skills.py"],
    "check-design-tokens":      ["test_check_design_tokens.py"],
    # Marka mirror drift kapısı (stripe/linear/primer/vercel): roster
    # bütünlüğü + pin eşleşmesi + kapsam sözleşmeleri tek modülde test edilir.
    "check-brand-mirrors":      ["test_brand_mirror_gate.py"],
    # Marka aynası @theme köprüleri (üretici + kapı): ad/ön-ek kuralları,
    # temel palet ayrıklığı, ön-koşul birebirliği ve sayım kilitleri tek
    # modülde test edilir.
    "check-mirror-bridges":     ["test_mirror_bridges.py"],
    # Zincir envanteri ↔ config hook kümesi (advisory uyarı + --strict).
    # Testi aynı zamanda şu değişmezi çiviler: gerçek ağaçta envanter bloğu
    # ile `.pre-commit-config.yaml` hook kümesi BİREBİR eşit olmalı.
    "check-precommit-inventory": ["test_check_precommit_inventory.py"],
    "check-bootstrap-toolchain": ["test_check_bootstrap_toolchain.py"],
    # Skill-alanı ↔ repo-yüzeyi envanteri: iki yönlü paket denetimi +
    # zero-surface iddiaları (rn-expo/wrangler/xlsx). Manifest
    # skill_surfaces.list tek kaynaktır.
    "check-skill-surfaces": ["test_check_skill_surfaces.py"],
    # dashboard-next'in JS kapı çifti: ikisi de aynı yüzeyin (biçim + tip)
    # sözleşmesini denetliyor ve tek bir birim modülü var. HOOK_COVERAGE'a
    # girmeden önce bu iki hook'un kapsam raporunda testi YOKTU.
    "check-prettier-format":    ["test_dashboard_next_style_gates.py"],
    "check-dashboard-typecheck": ["test_dashboard_next_style_gates.py"],
    "check-reproducible-pdf-skill": ["test_reproducible_pdf_skill.py"],
    "check-changelog-sync":    ["test_update_changelog_hook.py", "test_gen_changelog.py"],
    "check-unit-tests": [
        "test_server_events.py",
        "test_workflow_install_hardening.py",
        "test_verify_refs.py",
        "test_verify_checks.py",
        "test_status_checks.py",
        "test_audit_live_ci_sync.py",
        "test_doc_job_sync.py",
        "test_incremental_doc_sync.py",
        "test_check_doc_wrapper_sync.py",
        "test_run_summary_refs_trend.py",
        "test_api_method_contract.py",
        "test_atomic_write_guard.py",
        "test_gate_scripts_meta_guard.py",
        "test_workflow_contract.py",
        "test_advisory_coe_surfacing.py",
        "test_run_now_post_only.py",
        "test_run_summary_budget.py",
        "test_run_summary_changelog.py",
        "test_run_summary_k0.py",
        "test_run_summary_klayers.py",
        "test_run_summary_lineage.py",
        "test_lineage_sidecar_guarantee.py",
        "test_run_summary_precommit.py",
        "test_consolidate_summary.py",
        "test_consolidate_budget.py",
        "test_override_trend.py",
        "test_label_gate_contracts.py",
        "test_refs_trend.py",
        "test_refs_trend_badge.py",
        "test_audit_refs_trend.py",
        "test_check_repro_manifest_hook.py",
        "test_check_hook_unstaged_deps.py",
        "test_extract_unstaged_deps.py",
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
        "test_preview_server_atomic.py",
        "test_fresh_clone_setup.py",
        "test_lean_lake.py",
        "test_coq_lake.py",
        "test_daemon_http.py",
        "test_k18_daemon.py",
        "test_launchd_minimal_path.py",
        "test_ia_ol_fallback_evidence.py",
        "test_github_scripts.py",
        "test_check_plist_drift.py",
        "test_verify_manifest_overrides.py",
        "test_coverage_report.py",
        "test_test_coverage_report.py",
        "test_sync_check_unit_tests.py",
        "test_select_affected_tests.py",
        "test_sync_one_atomic.py",
        "test_check_lean_axioms.py",
        "test_classify_lean_error.py",
        "test_check_latex_surface.py",
        "test_check_lean_statements.py",
        "test_check_sde_determinism.py",
        "test_skill_layer_sync.py",
        "test_gen_k_layer.py",
        "test_reproducible_pdf_skill.py",
        "test_render_equation_gallery.py",
        "test_render_z3_slides.py",
        "test_check_hook_env_matrix.py",
        "test_ci_sidecar_wiring.py",
        "test_actionlint_gate.py",
        "test_audit_octokit_names.py",
        "test_check_badge_endpoints.py",
        "test_check_bootstrap_start_smoke.py",
        "test_check_bootstrap_toolchain.py",
        "test_check_config_drift_summary.py",
        "test_check_coq_axioms.py",
        "test_check_orchestration_stdin.py",
        "test_check_unit_tests_timing.py",
        "test_ci_check_rate.py",
        "test_ci_failure_pattern.py",
        "test_coordinator_loop.py",
        "test_coq_evidence_smoke.py",
        "test_dashboard_k17_exit_sync.py",
        "test_duration_pct_config.py",
        "test_fallback_evidence_hook.py",
        "test_full_publish_doc_sync.py",
        "test_gate_coverage_sync.py",
        "test_gen_ci_trend.py",
        "test_gen_m0_live_table.py",
        "test_gen_publish_artifact_list.py",
        "test_gen_repro_manifest_e2e.py",
        "test_history_sources.py",
        "test_k13_coverage_sync.py",
        "test_k9_lean_files_sync.py",
        "test_lean_override_snapshot.py",
        "test_m0_k12_sidecar_sync.py",
        "test_m0_k_table_sync.py",
        "test_orchestrate_k_dag.py",
        "test_override_trend_badge.py",
        "test_plist_check_workflow.py",
        "test_precheck_advisory_contract.py",
        "test_preview_findings_panel.py",
        "test_repro_artifact_sections_e2e.py",
        "test_sde_texlive_sync.py",
        "test_sidecar_guarantee.py",
        "test_status_checks_smoke.py",
        "test_summary_pattern_drift.py",
        "test_texlive_determinism_hook.py",
        "test_texlive_determinism_id_residual.py",
        "test_trend_tooltip_dom.js",
        "test_update_preview_sync_server.py",
        "test_workflow_timeouts.py",
        "test_workflow_triggers.py",
        "test_z3_slide_gallery.py",
        "test_z3_slide_reproducibility.py",
        "test_architecture_deepening_deck.py",
        "test_k_layer_tokens.py",
        "test_pdf_repro_findings_deck.py",
        "test_pdf_source_freshness.py",
        "test_run_summary_k13.py",
        "test_verification_chain_deck.py",
        "test_verify_k_layers.py",
        "test_ci_stats.py",
        "test_config_sync_badge.py",
        "test_budget_over_detail.js",
        "test_refs_trend_badge_node.js",
        "test_z3_scan.js",
        "test_verify_job_checklist.py",
        "test_check_design_tokens.py",
        "test_check_zip_lineage_drift.py",
        "test_readme_skills.py",
        "test_skills_index.py",
        "test_texlive_repro_documented.py",
        "test_docker_security_smoke.py",
        "test_dockerfile_security_patching.py",
        "test_record_determinism_trend.py",
        "test_stop_post_only.py",
        "test_a11y_gate.py",
        "test_security_headers.py",
        "test_pptx_export.py",
        "test_trend_db_contract.py",
        "test_check_precommit_orphans.py",
        "test_dev_bootstrap.py",
        "test_id_residual_acceptance_doc.py",
        "test_makefile_texlive.py",
        "test_gated_schedules.py",
        "test_sync_lifecycle.py",
        "test_determinism_trend_badge.py",
        "test_dashboard_keyboard_nav.py",
        "test_api_method_matrix.py",
        "test_stop_peer_allowlist.py",
        "test_openapi_schema.py",
        "test_ci_hygiene_gate.py",
        "test_gh_run_rca.py",
        "test_deploy_evidence.py",
        "test_local_security_surface.py",
        "test_vercel_adapter.py",
        "test_canvas_determinism.py",
        "test_determinism_trend_canvas.py",
        "test_incidental_banner.py",
        "test_check_seal_hash.py",
        "test_dashboard_cls_budget.py",
        "test_surface_cwv_report.py",
        "test_shuffle_tests.py",
        "test_repack_idempotence.py",
        "test_check_video_typecheck.py",
        "test_video_data_contract.py",
        "test_check_video_render.py",
        "test_preview_video_player.py",
        "test_preview_hover_tooltip.py",
        "test_preview_escaping.py",
        "test_csp_directives.py",
        "test_security_header_matrix.py",
        "test_static_isolation.py",
        "test_dashboard_next_style_gates.py",
        "test_brand_mirror_gate.py",
        "test_trend_db_index_contract.py",
        "test_trend_db_rls_contract.py",
        "test_mirror_bridges.py",
        "test_trend_db_js_runner.py",
        "test_check_unstaged_delta.py",
        "test_dashboard_next_ui_contract.py",
        "test_check_precommit_inventory.py",
        "test_verify_sweep.py",
        "test_check_skill_surfaces.py",
        "test_check_merge_precondition.py",
        "test_gen_skill_surface_inventory.py",
        "test_dashboard_next_battery_smoke.py",
        "test_trend_record_pr_contract.py",
        "test_check_protection_drift.py",
        "test_check_prettier_format.py",
        "test_plist_keepalive_golden.py",
        "test_gen_id_residual_acceptance.py",
        "test_k6_determ_canonical.py",
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
    # a11y-gate job'ı dashboard'ın axe taramasına ek olarak CLS bütçe kapısını
    # (CLS < 0.1) aynı canlı preview_server üzerinde koşar — "Run CLS budget
    # gate — dashboard (CLS < 0.1)" adımı. İkinci adım ("Run CWV report —
    # dashboard + landing") aynı ölçüm çekirdeğini dashboard + landing
    # yüzeylerine koşturur (CLS/LCP/FCP/TTFB).
    "a11y-gate": ["test_a11y_gate.py", "test_dashboard_cls_budget.py",
                  "test_surface_cwv_report.py"],
    # ÖLÇÜLENLİ BOŞLUK (2026-09-28): `test_dashboard_playwright_smoke.py`
    # HİÇBİR CI JOB'INDA KOŞMUYOR. Önceden burada `dashboard-smoke` diye bir
    # job kayıtlıydı; ölçüldü: verify.yml'de böyle bir job YOK (jobs: verify,
    # a11y-gate, dashboard-next, preview-reload-smoke, …) ve hiçbir workflow bu
    # dosyayı çalıştırmıyor. `verify` job'ı `unittest discover` ile dosyayı
    # KEŞFEDİYOR ama o job'da Playwright kurulu değil (yalnız a11y-gate ve
    # dashboard-next'te kurulu) → süit `skipIf` ile sessizce ATLANIYOR.
    # Yani kayıt, koşan bir kapı varmış gibi rapor veriyordu (fail-open'ın
    # kardeşi: kayıt var, koşum yok). Kayıt KALDIRILDI; dosya CHECK_EXEMPT'te
    # kalıyor ve gerçek bir job eklenirse buraya geri gelmelidir.
    # dashboard-next job'ı panoyu derledikten SONRA yüzey smoke'unu koşar
    # ("Surface smoke — dashboard-next"): bu dosyanın canlı katmanı `next
    # start` + Chromium ister, derleme zaten aynı job'da yapılır. Dosya
    # check_unit_tests.list DIŞINDADIR (EXCLUDE) — pre-commit bütçesi. Statik
    # eşi `test_dashboard_next_ui_contract.py` unit bataryasındadır.
    "dashboard-next": ["test_dashboard_next_surface_smoke.py",
                       # İstek-basi dedup sözleşmesi: SAYAN upstream + `next
                       # start`. Aynı job'da, derlemenin hemen ardından
                       # (Chromium'dan ÖNCE — stdlib HTTP, tarayıcı yok).
                       "test_dashboard_next_request_dedup.py",
                       # Canlı akış sözleşmesi: yayınlayan upstream + Chromium
                       # gerektirir → Chromium kurulumundan SONRA koşmalı.
                       "test_dashboard_next_live_stream.py"],
    "daemon-http": ["test_daemon_http.py"],
    "plist-check": ["test_plist_gate_exit.py", "test_gen_plist_golden.py"],
    "coq-proof": ["test_coq_lake.py"],
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


# ────────────────────────────────────────────────────────────────────────────
# CHECK_EXEMPT — `--check` modunun muafiyet sözleşmesi: bu dosyalar hiçbir
# pre-commit hook'unda koşmaz (standalone smoke/Playwright/JS-only) ve
# kapsamsız kalmaları FAIL sayılmaz. TEK KAYNAK burasıdır; kardeş test
# (test_test_coverage_report.py) eskiden aynı listeyi elle kopyalıyordu ve
# kopya sürüklendiği için süit kırmızıya düştü — artık buradan okunur.
# Modül düzeyinde durur ki test/araç onu import edebilsin. Metin biçimi
# ("CHECK_EXEMPT = frozenset({") test_sync_check_unit_tests.py'nin metin
# ayrıştırmasıyla uyumlu tutulmalıdır.
# ────────────────────────────────────────────────────────────────────────────
CHECK_EXEMPT = frozenset({
    "test_coverage_report.py",      # meta: kendi kendini test edemez
    "test_test_coverage_report.py",  # meta: kendini test eder, ayrıca check-unit-tests'te
    "test_preview_reload_smoke.py",  # standalone smoke script, def test_ yok
    "test_all_hooks_smoke.py",       # standalone smoke: tum hook'lari kosar
    "test_budget_scan.js",          # JS-only, ayrı Node hook'unda
    "test_dashboard_playwright_smoke.py",  # standalone Playwright smoke (Chromium ~10s) — ÖLÇÜLDÜ: hiçbir
                                           # CI job'ında koşmuyor (verify job'ında Playwright yok → skipIf;
                                           # ayrı `dashboard-smoke` job'ı YOK). Kapsam dışı olduğu için
                                           # CHECK_EXEMPT; gerçek job eklenirse CI_JOB_COVERAGE'a girer.
    "test_dashboard_csp_nonce.py",   # standalone Playwright CSP+nonce smoke (Chromium) — canlı sunucu/kendi sunucusu
    "test_dashboard_next_surface_smoke.py",  # standalone Playwright yüzey smoke'u (Chromium + `next start`) — derleme
                                             # gerektirir, pre-commit bütçesine sığmaz; CI_JOB_COVERAGE'da
                                             # `dashboard-next` job'ı ile kayıtlıdır (o job panoyu derler).
    "test_dashboard_next_request_dedup.py",  # standalone istek-basi dedup sözleşmesi (sayan upstream + `next start`)
                                             # — derleme gerektirir, pre-commit bütçesine sığmaz; CI_JOB_COVERAGE'da
                                             # `dashboard-next` job'ı ile kayıtlıdır (o job panoyu derler).
    "test_dashboard_next_live_stream.py",  # standalone canlı akış sözleşmesi (yayınlayan upstream + `next start`
                                           # + Chromium) — pre-commit bütçesine sığmaz; CI_JOB_COVERAGE'da
                                           # `dashboard-next` job'ı ile kayıtlıdır (o job panoyu derler ve
                                           # Chromium kurar).
    "test_refs_trend_badge_node.js", # standalone JS smoke (Node-only assertion), dokümante bilinçlileşti
})


# ══════════════════════════════════════════════════════════════════════════
# ARTIRMLI SEÇİM — kapsam eşlemesi kaynak-dosya GLOB'larına genişletildi
# ══════════════════════════════════════════════════════════════════════════
# Ölçülen boşluk: check-unit-tests her commit'te manifest'in TAMAMINI
# (190 dosya, ~345-370 s) koşuyordu. Commit'in dokunduğu testlerle sınırlı
# bir koşum aynı güvenliği çok daha kısa sürede veriyor.
#
# Eşleme ÜÇ kaynağın BİRLEŞİMİDİR — ve bu kasıtlıdır:
#
#   1. TÜRETİLEN (import): testin `import`'ladığı ve diskte GERÇEKTEN
#      bulunan modüller. Sürükleme İMKANSIZ: eşleme testin kendi
#      kaynak kodundan hesaplanır, ayrı bir tablo kopyalanmaz. Yeni bir
#      import eklemek otomatik olarak kapsamı genişletir.
#   2. BİLANEN (aşağıdaki tablo): import EDİLEMEYEN bağımlılıklar —
#      config dosyaları, YAML, markdown, shell betikleri, JSON manifestler.
#      Bunlar okunur ama import edilmez; elle bildirilir.
#   3. ALWAYS_RUN: hiçbir yolla seçilemeyecek testler. Bir test listede
#      yoksa VE import'ı yoksa artımlı koşumda HİÇ seçilmez — bu sessiz
#      kapsam kaybıdır, bu yüzden varsayılan "hep koş"tur.
#
# ⚠️ FAIL-CLOSED İLKESİ: her manifest testi ya ALWAYS_RUN'da ya en az bir
# glob'a sahip OLMAK ZORUNDA (total erişilebilirlik kuralı, `reachable()`
# ve sync --check bunu denetler). Yeni bir test eklenip glob'u unutulursa
# commit bloklanır — "yavaş çalışsın" değil, "HİÇ çalışmasın" riski
# komşu bir kurala bırakılmaz.
#
# Glob sözdizimi: `fnmatch` — `*` `/` sınırını AŞAR (`*verify.yml`
# `.github/workflows/verify.yml`'yi de tutar). Bu, "hangi klasörde
# olursa olsun" anlamına gelir ve choke-point dosyaları (verify.yml,
# .pre-commit-config.yaml) için ayrı bir tabloya gerek bırakmaz.

# Playwright kapılarının ORTAK kaynak yüzeyi (dört test aynı sunucuyu
# sürüyor). `preview_server.py` sunucuyu başlatan ve statik yüzeyi
# servis eden dosyadır; statik HTML üretilmiş çıktıdır (PREVIEW_DIR =
# kullanıcı önbelleği, repoda izlenmez) — bu yüzden izlenebilir olan
# ÜRETİCİ kaynaklar bildirilir.
PLAYWRIGHT_SOURCES = [
    "_calisma/CIKTI/preview_server.py",
    "design-system/*",
    "apps/dashboard-next/*",
]
TEST_SOURCE_GLOBS = {
    # ── config / workflow choke-point'leri: nerede olurlarsa olsunlar ──
    "test_advisory_coe_surfacing.py": ["*verify.yml", "*github_scripts/*.js"],
    "test_check_unstaged_delta.py": [".pre-commit-config.yaml"],
    "test_ci_sidecar_wiring.py": ["*verify.yml", "*github_scripts/*.js"],
    "test_ci_hygiene_gate.py": ["*.yml"],
    "test_doc_job_sync.py": [".pre-commit-config.yaml", "docs/PUBLISH_SCENARIO.md", "*verify.yml"],
    "test_gate_scripts_meta_guard.py": ["*github_scripts/*.js", "*verify.yml"],
    "test_gated_schedules.py": ["*.yml", "*docker_security_smoke.sh", "*texlive_determinism_test.sh"],
    "test_github_scripts.py": ["*github_scripts/*.js", "*verify.yml"],
    "test_label_gate_contracts.py": ["*label_gate*.js", "*verify.yml"],
    "test_m0_k12_sidecar_sync.py": ["*verify.yml", "docs/*"],
    "test_plist_check_workflow.py": ["*verify.yml"],
    "test_workflow_install_hardening.py": ["*verify.yml"],
    "test_workflow_timeouts.py": ["*verify.yml", "*verify_lean_lake.sh"],
    "test_workflow_triggers.py": ["*verify.yml"],

    # ── marka / tasarım yüzeyleri ──
    "test_brand_mirror_gate.py": ["design-system/*", "apps/dashboard-next/*",
                                  ".pre-commit-config.yaml"],
    "test_check_design_tokens.py": ["design-system/*", "apps/dashboard-next/*"],
    "test_pptx_export.py": ["_calisma/pptx/*", "design-system/tokens.json"],

    # ── preview.js yüzeyi (kaynak kodunu import etmeden okuyan testler) ──
    "test_budget_over_banner.py": ["*preview.js"],
    "test_config_sync_badge.py": ["*preview.js"],
    "test_mirror_panel.py": ["*preview.js", "*sync_verify_mirror.sh"],
    "test_override_trend_badge.py": ["*preview.js"],
    "test_refs_trend_badge.py": ["*preview.js"],

    # ── determinizm / üretim betikleri ──
    "test_canvas_determinism.py": ["*canvas_determinism_test.sh"],
    "test_determinism_trend_canvas.py": ["*canvas_determinism_test.sh", "*determinism-trend.yml"],
    "test_dashboard_k17_exit_sync.py": ["*dashboard_smoke.sh", "*sync_verify_mirror.sh"],
    "test_dashboard_smoke.py": ["*dashboard_smoke.sh"],
    "test_k13_coverage_sync.py": ["*sync_verify_mirror.sh"],
    # K9 Lean senkronu: test iki SCRIPT'I okuyor. `lake-manifest.json` bir
    # ÜRETİLMİŞ artifact'tir (izlenmez, .gitignore'da) ve test onu hiç
    # okumaz — satırda geçen şey `! -name "lake-manifest.json"` ifadesi,
    # yani sync'in onu DIŞLADIğının kanıtı. O dosyaya glob bağlamak iki
    # hataya yol açtı: (1) commit listeleri izlenen dosyalardan geldiği için
    # bu glob HİÇ seçim üretemez, (2) stale denetimi üretilmiş dosyayı
    # gördüğü için ana ağaçta geçer, taze checkout'ta patlıyordu.
    "test_k9_lean_files_sync.py": ["*sync_verify_mirror.sh", "*verify_delivery.py"],
    "test_sync_one_atomic.py": ["*sync_verify_mirror.sh"],
    "test_texlive_determinism_hook.py": ["*texlive_determinism_hook.sh", ".pre-commit-config.yaml"],
    "test_texlive_determinism_id_residual.py": ["*texlive_determinism_test.sh"],
    "test_texlive_repro_documented.py": ["*texlive_determinism_hook.sh", "*texlive_determinism_test.sh",
                                         ".pre-commit-config.yaml", "*REPRODUCIBILITY.md"],
    "test_makefile_texlive.py": ["docs/Makefile.texlive", "docs/Makefile.tectonic",
                                 "docs/ID_RESIDUAL_ACCEPTANCE.md",
                                 "*gen_id_residual_acceptance.py"],
    # K6-DETERM (Faz 4): strict kapı /ID-kanonik hash'e + kabul defterine
    # bağlı. Test verify_delivery.py'nin yeni yardımcılarını (canonical_pdf_sha256,
    # id_residual_ledger_tokens, k6_determ_verdict) ve kaynak sözleşmesini
    # denetler; defter (referans kaydı) değişince de seçilmelidir.
    "test_k6_determ_canonical.py": ["*verify_delivery.py",
                                    "docs/ID_RESIDUAL_ACCEPTANCE.md"],

    # ── docker ──
    "test_docker_security_smoke.py": ["*docker_security_smoke.sh", "Dockerfile"],
    "test_dockerfile_security_patching.py": ["Dockerfile", "docs/DOCKER_SECURITY_PATCHING.md",
                                              "*docker_security_smoke.sh", ".pre-commit-config.yaml"],

    # ── hook betikleri ──
    "test_check_precommit_orphans.py": ["*check_precommit_orphans.py", "*recovery_patches_*"],
    "test_check_video_typecheck.py": ["*check_video_typecheck.sh", "_calisma/video/*"],
    "test_commit_msg_hook.py": ["*commit_msg_hook.sh", "*commit_msg_gate.js"],
    "test_enforce_is_on.py": ["*publish_wrapper.sh"],
    "test_fallback_evidence_hook.py": ["*check_fallback_evidence_hook.sh",
                                       "_calisma/CIKTI/ia_ol_fallback_evidence.py",
                                       ".pre-commit-config.yaml"],
    "test_update_preview_sync_server.py": ["*update_preview.sh"],
    # keepalive profil mimarisi altın-dosya testi: update_preview.sh'in
    # PLIST_PROFILES son kolonunu (true/false) render edip üretilen plist
    # GÖVDELERİNİ commit'li plist-golden/ ile karşılaştırır — drift kapısının
    # (check_plist_drift.py, advisory) fail-closed birim karşılığı. Bu yüzden
    # hem şablon kaynağı hem golden dizini izlenir.
    "test_plist_keepalive_golden.py": ["*update_preview.sh", "*plist-golden/*"],
    "test_verify_checks.py": ["*verify_checks.sh"],

    # ── üretici ↔ doküman sözleşmeleri ──
    "test_gen_commit_msg_evidence.py": ["*commit_msg_hook.sh", "docs/*"],
    "test_gen_k_layer.py": ["skills/*"],
    "test_gen_skill_surface_inventory.py": ["_calisma/CIKTI/gen_skill_surface_inventory.py",
                                            "docs/SKILL_SURFACE_INVENTORY.md",
                                            "findings.md", "*skill_surfaces.list"],
    "test_id_residual_acceptance_doc.py": ["docs/ID_RESIDUAL_ACCEPTANCE.md"],
    # Faz 3 kabul üreticisi: kanıt (determinism raporu) → defter satırı.
    # Üreticiyi, kabul raporunu ve Makefile'ın accept bağını izler.
    "test_gen_id_residual_acceptance.py": ["*gen_id_residual_acceptance.py",
                                           "docs/ID_RESIDUAL_ACCEPTANCE.md",
                                           "docs/Makefile.texlive"],
    "test_duration_pct_config.py": ["*verify_delivery.config.json"],

    # ── trend-db ──
    "test_trend_db_index_contract.py": ["apps/trend-db/*", "README.md"],
    "test_trend_db_rls_contract.py": ["apps/trend-db/*"],
    "test_trend_db_js_runner.py": ["apps/trend-db/*"],
    "test_video_data_contract.py": ["_calisma/video/*"],

    # ── bootstrap / pin kaynağı (bu turun tek-kaynak değişikliği) ──
    "test_dev_bootstrap.py": ["_calisma/dev_bootstrap.sh", "_calisma/requirements-z3.txt",
                              "_calisma/CIKTI/test_dev_bootstrap.py", "README.md",
                              "docs/FIRST_RUN_TUTORIAL.md", "docs/READER_TEST_PROTOCOL.md",
                              ".github/workflows/verify.yml"],

    # ── Playwright / tarayıcı kapıları: AĞIRLIKLARI ölçüldü, kapsamları
    # BİLDİRİLDİ. Dördü birlikte ~181 s (artımlı koşumun ~%80'i) idi ve
    # "ortam-bağımlı" gerekçesiyle ALWAYS_RUN'da tutuluyordu. Gerçek
    # bağımlılık: sunucuyu başlatan preview_server.py + servis ettiği
    # statik yüzey (design-system) + dashboard-next parity'si. Statik
    # HTML'nin kendisi PREVIEW_DIR'de (kullanıcı önbelleği, repoda
    # izlenmez) üretildiği için üretilen çıktı izlenemez; onun yerine
    # ÜRETEN kaynak bildirilir.
    "test_preview_escaping.py": PLAYWRIGHT_SOURCES,
    "test_preview_hover_tooltip.py": PLAYWRIGHT_SOURCES,
    "test_dashboard_keyboard_nav.py": PLAYWRIGHT_SOURCES,
    "test_dashboard_cls_budget.py": PLAYWRIGHT_SOURCES,
}

# Artımlı koşumda HER commit'te çalışan testler. İki gerekçeli küme:
#  - MAKİNE testleri: seçimin kendisini ve kapsam eşlemesini denetleyenler
#    (seçici bozulursa sessizce yanlış testler koşulurdu).
#  - BAĞIMLILIĞI ÖLÇÜLEMEYENLER: kaynağı doğrudan okunabilen bir dosya
#    olmayanlar (git komutları, üretilmiş çıktı, çok geniş yüzeyler).
#    Bunlar "glob tahmin et" yerine "her zaman koş" ile korunur: bir testi
#    yanlışlıkla koşturmak zaman kaybı, yanlışlıkla KOŞMAMAK sessiz
#    regresyondur.
ALWAYS_RUN = frozenset({
    "test_coverage_report.py",              # kapsam eşlemesinin kendisi
    "test_test_coverage_report.py",        # ...ve onun sözleşme testleri
    "test_sync_check_unit_tests.py",       # manifest ↔ HOOK_COVERAGE drift'i
    "test_select_affected_tests.py",       # seçicinin kendisi
    "test_check_precommit_inventory.py",   # hook ↔ doküman envanteri
    "test_verify_job_checklist.py",        # CIKTI geneli dosyaları okur
    "test_atomic_write_guard.py",          # yazma disiplini, geniş yüzey
    "test_check_merge_precondition.py",    # git geçmişi okur
    "test_gen_repro_manifest_e2e.py",      # uçtan uca, dosya listesi sabit değil
    "test_pdf_source_freshness.py",
    "test_repack_idempotence.py",
    "test_repack_verify.py",
    "test_repro_artifact_sections_e2e.py",
    "test_vercel_adapter.py",
    "test_z3_slide_gallery.py",
    "test_z3_slide_reproducibility.py",
    "test_k_layer_tokens.py",
    "test_incidental_banner.py",
    "test_check_video_render.py",          # ortam-bağımlı
    # PR #53 ile geldi (origin/main -> 34b6ea3 ayrışması). Test, izlenen
    # bir kaynak dosyaya BAĞLI DEĞİL: `determinism-trend.yml` akışının
    # branch/PR politikasını sözleşme düzeyinde sınar, bu yüzden hiçbir
    # TEST_SOURCE_GLOBS girdisi onu seçemiyor. Manifest'e girdiği için
    # fail-closed gereği burada olmazsa "sessizce hiç koşmayan test" olurdu.
    "test_trend_record_pr_contract.py",
})
# ⚠️ Playwright testleri ALWAYS_RUN'DAN ÇIKARILDI (2026-09-29, ölçüm):
# dört Playwright testi (dashboard_keyboard_nav, dashboard_cls_budget,
# preview_escaping, preview_hover_tooltip) tek başına ~181 s tutuyordu —
# artımlı koşumun ~%80'i. "Ortam-bağımlı" oldukları için buradaydılar, ama
# bağımlılıkları ÖLÇÜLEBİLİR: repo'daki tek kaynak preview_server.py +
# design-system + apps/dashboard-next. PREVIEW_DIR bir kullanıcı ÖNBELLEĞİ
# (~/Library/Caches) olduğu için repoda izlenmez; üretilen çıktıdır. Yeniden
# adlandırma riskine karşı bildirilen glob'lar "stale" denetimine tabidir:
# diskte hiçbir şeyi tutmazlar kapı KALICI olarak bloklar.

def normalize_path(path: str) -> str:
    """Yolu depo göreli, `/` ayraçlı biçime getirir.

    ⚠️ `lstrip("./")` BURADA KULLANILAMAZ: `lstrip` bir KARAKTER DİZİSİ
    siler, yani `.github/workflows/verify.yml` → `github/workflows/...`
    olurdu. Nokta ile başlayan her yol (.pre-commit-config.yaml dahil)
    sessizce eşleşmez hâle gelirdi. Yalnız gerçek `./` öneki atılır.
    """
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _local_module_path(module: str):
    """`module` CIKTI içinde GERÇEK bir dosyaya mı çözülüyor?

    stdlib listesi YOK: üçüncü taraf ve stdlib adları bu dosya kontrolünde
    doğal olarak elenir. `sys.stdlib_module_names` 3.10+ olduğu için
    3.9'daki venv'de de aynı davranış sağlanır (yoksa stdlib listesi
    güncellenmeyen bir ikinci gerçek kaynak olurdu).

    Testler depo kökünden koştuğu için `_calisma.CIKTI.` önekli import'lar
    da buraya düşer; TEST_DIR zaten `_calisma/CIKTI` olduğu için önek atılır.
    """
    prefix = "_calisma.CIKTI."
    if module.startswith(prefix):
        module = module[len(prefix):]
    rel = module.replace(".", "/")
    for cand in (TEST_DIR / f"{rel}.py", TEST_DIR / rel / "__init__.py"):
        if cand.is_file():
            return cand.relative_to(REPO_ROOT).as_posix()
    return None


def import_globs(test_file: str) -> list:
    """Bir testin import'larından TÜRETİLEN kaynak glob'ları.

    Neden türetmek: eşleme ikinci bir tabloda kopyalanırsa yeni import
    ekleyen biri onu unutur ve test o modülü değiştirdiğimizde koşulmaz —
    sessiz kapsam kaybı. Testin kendi kaynak kodundan okuyorsak bu
    sınıf hata tanım gereği imkânsızdır.
    """
    path = TEST_DIR / test_file
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
            if node.module == "_calisma.CIKTI":
                # `from _calisma.CIKTI import check_x`: modül paketin
                # kendisi; asıl hedef import EDİLEN AD'dır (`*` hariç).
                mods += [a.name for a in node.names if a.name != "*"]
    found = []
    for mod in mods:
        rel = _local_module_path(mod)
        if rel and rel not in found:
            found.append(rel)
    return sorted(found)


def effective_globs(test_file: str) -> list:
    """TÜRETİLEN + BİLANEN glob birleşimi (sıra duyarsız, tekilleştirilmiş)."""
    return sorted(set(import_globs(test_file)) | set(TEST_SOURCE_GLOBS.get(test_file, [])))


def read_manifest():
    """check_unit_tests.list'ten koşulacak test sırası (tek kaynak)."""
    manifest = TEST_DIR / "check_unit_tests.list"
    return [ln.strip() for ln in manifest.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def reachable(manifest=None) -> dict:
    """Manifest testlerinin kaçı artımlı koşumda SEÇİLEBİLİR?

    Kapsam sözleşmesi (fail-closed): `unreachable` BOŞ olmalıdır. Doluysa
    o test hiçbir değişiklikte seçilemez — sessizce hiç koşmaz.
    """
    manifest = manifest if manifest is not None else read_manifest()
    always, reactive, unreachable = [], [], []
    for t in manifest:
        if t in ALWAYS_RUN:
            always.append(t)
        elif effective_globs(t):
            reactive.append(t)
        else:
            unreachable.append(t)
    return {"manifest": list(manifest), "always": sorted(always),
            "reactive": sorted(reactive), "unreachable": sorted(unreachable)}


def affected_tests(paths, manifest=None) -> dict:
    """Değişen dosyalardan koşulacak testleri seçer (artımlı koşum).

    Seçim KAPAYLA (fail-safe): her test ya hep koşar (ALWAYS_RUN), ya da
    değişen yollardan biriyle eşleşirse. "Hiçbir şey tutmuyorsa" çıktısı
    BOŞ olamaz — çünkü ALWAYS_RUN kümesi her zaman devreye girer.
    """
    manifest = list(manifest if manifest is not None else read_manifest())
    changed = [normalize_path(p) for p in paths]
    selected, reasons = [], {}
    for t in manifest:
        if t in ALWAYS_RUN:
            selected.append(t)
            reasons[t] = "always"
            continue
        # "Testin kendisi değişti" → o test koşar. Manifest girdisi çıplak
        # dosya adıdır, değişiklik listesi ise depo göreli yol; bu yüzden
        # karşılaştırma da depo göreli yolla yapılır. Bu satır olmadan
        # `--all-files` (yani CI) TAM BATARYAYI guarantee edemez.
        own = f"_calisma/CIKTI/{t}"
        hit = own if own in changed else None
        if not hit:
            globs = effective_globs(t)
            for p in changed:
                if any(fnmatch.fnmatch(p, g) for g in globs):
                    hit = p
                    break
        if hit:
            selected.append(t)
            reasons[t] = hit
    return {"selected": selected, "reasons": reasons, "total": len(manifest),
            "changed": changed}


def _repo_files():
    """Depo göreli yollar (dosya + dizin) — glob/index için tek tarama.

    `glob.glob` KULLANILMAZ: onun `*` deseni `/` sınırını geçmez, seçim
    ise `fnmatch` ile yapılır ve orada `*` `/`'yi aşar. Aynı eşleştirici
    kullanılmazsa "stale glob" denetimi, sağlam glob'ları yanlışlıkla
    stale ilan eder (ilk çalıştırmada 54 sahte-pozitif üretti).

    Üretilen/ağır dizinler budanır: `node_modules` altında yüz binlerce
    dosya var ve tarama commit süresine yansır.
    """
    prune = {".git", "node_modules", "__pycache__", ".next", ".vercel",
             "generated", ".venv_z3", "dist", "build", ".pytest_cache",
             ".worktrees"}
    out = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in prune]
        rel_dir = pathlib.Path(dirpath).relative_to(REPO_ROOT).as_posix()
        if rel_dir != ".":
            out.append(rel_dir)
        out += [(f"{rel_dir}/{f}" if rel_dir != "." else f) for f in filenames]
    return out


def _selectable_files():
    """Commit'te DEĞİŞTİRİLEBİLECEK depo göreli yollar.

    Seçim commit dosya listeleriyle çalışır; pre-commit bize yalnız izlenen
    (stage'lenmiş) dosyaları verir. Bu yüzden "bu glob bir işe yarıyor mu"
    sorusunun cevabı dosya sistemi taramasıyla değil, GİT'İN KENDİ
    izlenen/ignored ayrımıyla verilmelidir:

      git ls-files --cached --others --exclude-standard
        --cached            izlenen (commit'e girebilir)
        --others            izlenmeyen
        --exclude-standard  ...ama ignored DEĞİL (yani üretilmiş çıktı DEĞİL)

    Ölçülen sahte-pozitif: `*lake-manifest.json` glob'u geliştiricinin
    ağacında ÜRETİLMİŞ (ignored) bir dosyaya tutunduğu için "canlı"
    görünüyordu; ama ignored dosya hiçbir commit listesinde bulunamaz, yani
    o glob seçim üretemiyordu. Dosya sistemi taraması bunu ancak geliştiri-
    cinin ağacında gizliyor, taze checkout'ta kapıyı kırıyordu.

    `--others` dahil OLMADAN sadece `--cached` kullanılsaydı, commit'e
    henüz girmemiş ama ignored OLMAYAN yeni bir kaynak dosya da (ör. yeni
    pin dosyası) geçici olarak "stale" görünürdü — commit'lenmemiş olması
    onu üretilmiş çıktı yapmaz.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
            cwd=str(TEST_DIR.parent.parent))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"UYARI: git ls-files çalışmadı ({exc}) — stale denetimi "
              f"taranan dosyalara düşüyor (sahte-pozitif riski).", file=sys.stderr)
        return None
    return {normalize_path(ln) for ln in out.stdout.splitlines() if ln.strip()}


def stale_globs(manifest=None) -> list:
    """BİLANEN glob'lar commit'te değiştirilebilir HİÇBİR dosyayı tutmayanlar.

    Yeniden adlandırılmış bir gate'in eski glob'u sessizce ölür ve o
    test artık hiç seçilmez. Bu, "kapsam kaybı"nın en kolay görünmeyen
    hâli olduğu için drift kapısı FAIL-CLOSED olmalıdır.

    Taban küme `_selectable_files`'tır: üretilmiş/ignored bir dosyaya
    tutunan glob bir commit'te HİÇ seçim üretemez — canlı görünmesi bir
    illüzyondur. git erişilemezse dosya sistemi taramasına düşülür (fail-open
    değil, yalnız daha zayıf bir kanıt).
    """
    manifest = manifest if manifest is not None else read_manifest()
    files = _selectable_files()
    if files is None:
        files = _repo_files()
    stale = []
    for t in manifest:
        for g in TEST_SOURCE_GLOBS.get(t, []):
            if not any(fnmatch.fnmatch(f, g) for f in files):
                stale.append((t, g))
    return stale


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
    # (meta dosyalar, smoke script'leri, JS-only testleri — modül düzeyi
    # CHECK_EXEMPT ile aynı sözleşme).
    if args.check:
        gaps = [g for g in report["gaps"]["not_covered_by_any_hook"]
                if g not in CHECK_EXEMPT]
        if gaps:
            print(f"\nFAIL: {len(gaps)} test file(s) uncovered by any pre-commit hook:", file=sys.stderr)
            for g in gaps:
                print(f"  - {g}", file=sys.stderr)
            print("Add them to HOOK_COVERAGE in test_coverage_report.py or to a hook in .pre-commit-config.yaml", file=sys.stderr)
            return 1
        print("PASS: all non-exempt test files covered by at least one pre-commit hook", file=sys.stderr)
        return 0

    return 0


class TestCoverageReportSmoke(unittest.TestCase):
    """test_coverage_report.py'yi unittest discover altında da gerçek bir test yapar.

    Bu dosyada daha önce hiç `def test_*` yoktu — `discover -p "test_*.py"`
    kombine koşusunda zararsız bir modüldü, ama check-unit-tests hook'u her
    dosyayı AYRI koştuğunda Python 3.12+ boş discovery'de exit 5 döndürür
    (gh-136442) → CI'da "1/49 BAŞARISIZ". En az bir gerçek test eklemek
    hem kapıyı yeşil yapar hem de --check modunun gerçek repo üzerinde
    çalıştığını doğrular.
    """

    def test_check_passes_on_real_repo(self):
        rc = main(["--check"])
        self.assertEqual(rc, 0, "test_coverage_report.py --check gerçek repoda 0 dönmeli")

    def test_main_accepts_md_flag(self):
        # --md çıktısı üretebilmeli (check-coverage-report hook'unun kardeş modu).
        rc = main(["--md", "/tmp/coverage_smoke_report.md"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists("/tmp/coverage_smoke_report.md"))
        with open("/tmp/coverage_smoke_report.md", encoding="utf-8") as f:
            self.assertIn("## Summary", f.read())


if __name__ == "__main__":
    # Script modu (pre-commit hook: `test_coverage_report.py --check` vb.) → main().
    # Test modu (unittest discover / check-unit-tests) → unittest.main().
    if any(a in ("--check", "--md", "--json", "--ci") for a in sys.argv[1:]):
        sys.exit(main())
    unittest.main()
