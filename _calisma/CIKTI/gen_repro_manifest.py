#!/usr/bin/env python3
"""
gen_repro_manifest.py — reproducibility manifest üretici (tek kaynak).

GitHub Actions verify.yml'deki 'reproducibility' job'ının inline Python
mantığının standalone hali. Aynı kod hem CI'da hem yerelde (mock artifact'larla
simülasyon / doğrulama) çalışır → CI ile yerel arasında drift olmaz.

Çıktılar (--out-dir altına):
  manifest.txt    — insan-okur: FILE + SHA-256 tablosu + CONFIG bölümü
  manifest.json   — makine-okur: tool/generated/run/sha/ref/files{rel: sha256}
                    + config{files, combined_sha256}
                    + refs_trend{files, combined_sha256}
                    + action_runtimes{files, combined_sha256}
                    + python3_shell{files, combined_sha256}
  manifest.sha256 — manifest.json'un kendi SHA-256'sı (sha256sum formatı;
                    kurcalanma / yeniden üretim farkı tek hash ile denetlenir)
  + tüm artifact'ların kopyası (bundle)

CONFIG bölümü: config dosyaları (config/ önekli VEYA CONFIG_BASENAMES ile
isimle tanınan — merge-multiple'ın köke düzleştirmesine dayanıklı) ayrıca
hash'lenir (FILE tablosunda zaten var — bu ayrı bölüm denetlenebilirliği
artırır). combined_sha256 = tüm config dosyalarının (rel\0hash\n sıralı
birleşiminin) SHA-256'sı — deterministik, config'in hangi sürümünün
kullanıldığını tek hash ile özetler.

Ortam değişkenleri (CI'da GitHub Actions set eder; yerelde override edilebilir):
  GITHUB_RUN_ID, GITHUB_SHA, GITHUB_REF, GITHUB_REPOSITORY, GITHUB_RUN_URL

Kullanım:
  python3 gen_repro_manifest.py --artifacts-dir all_artifacts --out-dir reproducibility
  GITHUB_RUN_ID=test-123 python3 gen_repro_manifest.py --artifacts-dir /tmp/mock ...
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Artifact → üreten job eşlemesi. verify.yml'deki her job'ın
# upload-artifact `name` alanının aynasıdır (TEK KAYNAK kuralı: bu tablo ile
# verify.yml birlikte değiştirilmelidir). merge-multiple indirmeleri
# artifact adını köke düzleştirdiği için bu eşleme, bir dosyanın hangi
# job'dan geldiğini denetlenebilir kılar. REPRO_ARTIFACT_JOBS env'i (JSON)
# geçersiz kılma sağlar.
ARTIFACT_JOBS = {
    "verify-report": "verify",
    "budget-verify": "verify",
    "config": "verify",
    "k0-findings": "verify",
    "lineage-findings": "verify",
    "klayers": "verify",
    "unit-tests": "verify",
    "refs-online": "verify",
    "refs-trend": "refs-trend",
    "run-history": "verify",
    "precommit-logs": "verify",
    "budget": "budget",
    "reports": "reports",
    "config-drift": "config-drift",
    "repack-verify": "repack-verify",
    "precheck-report": "precheck",
    "action-runtimes": "action-runtimes",
    "python3-shell": "verify",
    "plist-check": "plist-check",
    "reproducibility": "reproducibility",
}

# Config artifact'ının bilinen dosya ADLARI (basename). Config dosyaları
# normalde bundle'da config/ önekiyle durur; ancak merge-multiple bir gün
# config artifact'ını köke düzleştirirse (config/ öneki kaybolur) bu isimler
# sayesinde config dosyaları yine tanınır. Tek kaynak: config artifact'ının
# içeriği verify.yml "Bundle config snapshot" adımıyla senkron tutulmalıdır.
CONFIG_BASENAMES = frozenset({
    "verify_delivery.config.json",
    "verify_delivery.config.schema.json",
    "effective_config.json",
    "action_pins.json",
    "config.sha256",
    "config-diff.txt",
    "config-diff.json",
})


# Run summary sidecar dosyalarının bilinen ADLARI (basename).
# consolidate_summary.py tarafından üretilen/run summary tarafından okunan
# sidecar dosyaları merge-multiple ile köke düzleşebilir; isimle tanınır.
# Action runtime raporu (action-runtimes job'ı): check_action_runtimes.py
# çıktısı — tek dosya, merge-multiple ile köke düzleşir; isimle tanınır.
ACTION_RUNTIMES_BASENAMES = frozenset({
    "action_runtimes.json",
})


SUMMARY_BASENAMES = frozenset({
    "klayers.json",
    "lineage_findings.json",
    "k0_findings.json",
    "budget_verify.json",
})


def _is_summary_rel(rel: str) -> bool:
    """Bir rel yolunun run summary sidecar dosyası olup olmadığını isimle tanı."""
    return os.path.basename(rel) in SUMMARY_BASENAMES


# CLI override sürüm sidecar'ının bilinen ADI (basename).
# check_cli_overrides.py --version-out ile üretilir; budget veya config-drift
# artifact'ından merge-multiple ile köke düzleşir — önek yoktur, basename ile
# tanınır (CONFIG/SUMMARY desenlerinin aynısı).
OVERRIDES_BASENAMES = frozenset({
    "cli_overrides_version.json",
})


def _is_overrides_rel(rel: str) -> bool:
    """Bir rel yolunun CLI override sidecar dosyası olup olmadığını isimle tanı.

    cli_overrides_version.json farklı işler tarafından (budget, config-drift)
    farklı alt dizinlerde üretilir; merge-multiple köke düzleştirdiğinde
    tek bir kopya kalır. Basename ile tanınır.
    """
    return os.path.basename(rel) in OVERRIDES_BASENAMES


def _is_action_runtimes_rel(rel: str) -> bool:
    """Bir rel yolunun action runtime raporu olup olmadığını isimle tanı.

    action-runtimes job'ı tek dosya üretir (action_runtimes.json);
    merge-multiple köke düzleştirdiği için önek yoktur — basename ile tanınır
    (config/SUMMARY desenlerinin aynısı).
    """
    return os.path.basename(rel) in ACTION_RUNTIMES_BASENAMES


def _is_config_rel(rel: str) -> bool:
    """Bir rel yolunun config dosyası olup olmadığını isimle tanı (önek + basename).

    Önek eşleşmesi (config/…) geriye dönük uyumluluk içindir; basename
    eşleşmesi merge-multiple'ın köke düzleştirmesine karşı dayanıklılık
    sağlar (config/ öneki kaybolsa bile dosya ismiyle tanınır).
    """
    return rel.startswith("config/") or os.path.basename(rel) in CONFIG_BASENAMES


def _load_artifact_jobs() -> dict:
    """ARTIFACT_JOBS'ı env override ile birleştir (REPRO_ARTIFACT_JOBS JSON)."""
    jobs = dict(ARTIFACT_JOBS)
    raw = os.environ.get("REPRO_ARTIFACT_JOBS")
    if raw:
        try:
            override = json.loads(raw)
        except json.JSONDecodeError:
            return jobs
        if isinstance(override, dict):
            jobs.update(override)
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-dir", default="all_artifacts",
                    help="artifact'ların bulunduğu dizin (CI'da download-artifact çıktısı)")
    ap.add_argument("--out-dir", default="reproducibility",
                    help="manifest + bundle çıktı dizini")
    args = ap.parse_args()
    artifact_jobs = _load_artifact_jobs()

    run_id  = os.environ.get("GITHUB_RUN_ID", "local-sim")
    sha     = os.environ.get("GITHUB_SHA", "local-" + hashlib.sha256(b"mock").hexdigest()[:12])
    ref     = os.environ.get("GITHUB_REF", "refs/heads/local-sim")
    repo    = os.environ.get("GITHUB_REPOSITORY", "local/sim")
    run_url = os.environ.get("GITHUB_RUN_URL", f"https://example.local/runs/{run_id}")
    now     = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    root = pathlib.Path(args.artifacts_dir)
    if not root.is_dir():
        raise SystemExit(f"HATA: artifacts dizini yok: {root}")

    lines = [
        "=" * 72,
        "STOIC-HUME V5  —  REPRODUCIBILITY MANIFEST",
        f"generated: {now}",
        f"github_run_id: {run_id}",
        f"github_sha: {sha}",
        f"github_ref: {ref}",
        f"github_repository: {repo}",
        f"github_run_url: {run_url}",
        "=" * 72,
        "",
        f"{'FILE':<55} {'SHA-256'}",
        "-" * 72,
    ]

    file_hashes = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h = sha256_file(p)
            rel = str(p.relative_to(root))
            file_hashes[rel] = h
            lines.append(f"{rel:<55} {h}")

    lines += ["", "-" * 72, f"Total files: {len(file_hashes)}", ""]

    # ── CONFIG bölümü: config dosyaları ayrıca işaretlenir ──────────────────
    # Tanıma: config/ öneki VEYA bilinen config basename'i (merge-multiple'
    # ın köke düzleştirmesi öneki kaybettirse de isimle tanınır).
    config_hashes = {rel: h for rel, h in file_hashes.items()
                     if _is_config_rel(rel)}
    config_combined = None
    if config_hashes:
        sorted_rel = sorted(config_hashes)
        config_combined = hashlib.sha256(
            "".join(f"{rel}\0{config_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        cfg_block = [
            "",
            "=" * 72,
            "CONFIG ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        cfg_block += [f"{rel:<55} {config_hashes[rel]}" for rel in sorted_rel]
        cfg_block += ["-" * 72,
                      f"config_combined_sha256: {config_combined}",
                      "=" * 72]
        lines += cfg_block

    # ── PRECOMMIT LOGS bölümü: precommit-logs/ önekli dosyalar (CONFIG gibi) ──
    # PRECOMMIT_CACHE.md (hook env + cache özeti) öncülüğünde precommit-logs
    # artifact'ının tüm dosyaları ayrıca işaretlenir; combined_sha256 tek hash
    # ile özetler (config.combined_sha256 ile aynı deterministik yöntem).
    precommit_hashes = {rel: h for rel, h in file_hashes.items()
                        if rel.startswith("precommit-logs/")}
    precommit_combined = None
    if precommit_hashes:
        sorted_rel = sorted(precommit_hashes)
        precommit_combined = hashlib.sha256(
            "".join(f"{rel}\0{precommit_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        pc_block = [
            "",
            "=" * 72,
            "PRECOMMIT LOGS ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        pc_block += [f"{rel:<55} {precommit_hashes[rel]}" for rel in sorted_rel]
        pc_block += ["-" * 72,
                     f"precommit_combined_sha256: {precommit_combined}",
                     "=" * 72]
        lines += pc_block

    # ── REFS TREND bölümü: refs-trend/ önekli dosyalar (CONFIG gibi) ──────
    # refs_trend.py'nin çıktısı (refs-trend.md + refs-trend.json) ayrıca
    # işaretlenir; combined_sha256 tek hash ile özetler (config.combined_sha256
    # ile aynı deterministik yöntem). Böylece çevrimiçi referans doğrulama
    # trendi zaman serisi de tek hash ile denetlenebilir.
    refs_trend_hashes = {rel: h for rel, h in file_hashes.items()
                         if rel.startswith("refs-trend/")}
    refs_trend_combined = None
    if refs_trend_hashes:
        sorted_rel = sorted(refs_trend_hashes)
        refs_trend_combined = hashlib.sha256(
            "".join(f"{rel}\0{refs_trend_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        rt_block = [
            "",
            "=" * 72,
            "REFS TREND ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        rt_block += [f"{rel:<55} {refs_trend_hashes[rel]}" for rel in sorted_rel]
        rt_block += ["-" * 72,
                     f"refs_trend_combined_sha256: {refs_trend_combined}",
                     "=" * 72]
        lines += rt_block

    # ── LINEAGE bölümü: lineage-findings/ önekli dosyalar (CONFIG gibi) ──
    # zip_lineage.json sidecar'ı ve --check-lineage çıktısı ayrıca
    # işaretlenir; combined_sha256 tek hash ile özetler (config.combined_sha256
    # ile aynı deterministik yöntem). Böylece soy hattı denetim zinciri
    # (zincir→hash→manifest→sidecar→CI kapısı) tek bir bundle'da tamamlanır.
    lineage_hashes = {rel: h for rel, h in file_hashes.items()
                      if rel.startswith("lineage-findings/")}
    lineage_combined = None
    if lineage_hashes:
        sorted_rel = sorted(lineage_hashes)
        lineage_combined = hashlib.sha256(
            "".join(f"{rel}\0{lineage_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        ln_block = [
            "",
            "=" * 72,
            "LINEAGE ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        ln_block += [f"{rel:<55} {lineage_hashes[rel]}" for rel in sorted_rel]
        ln_block += ["-" * 72,
                     f"lineage_combined_sha256: {lineage_combined}",
                     "=" * 72]
        lines += ln_block

    # ── SUMMARY bölümü: run summary sidecar dosyaları (LINEAGE gibi) ──────
    # consolidate_summary.py tarafından üretilen/run summary tarafından okunan
    # sidecar dosyaları (klayers.json, lineage_findings.json, k0_findings.json,
    # budget_verify.json) ayrıca işaretlenir; combined_sha256 tek hash ile
    # özetler. Böylece run summary üretiminin girdileri de denetim zincirinde.
    summary_hashes = {rel: h for rel, h in file_hashes.items()
                      if _is_summary_rel(rel)}
    summary_combined = None
    if summary_hashes:
        sorted_rel = sorted(summary_hashes)
        summary_combined = hashlib.sha256(
            "".join(f"{rel}\0{summary_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        sm_block = [
            "",
            "=" * 72,
            "SUMMARY ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        sm_block += [f"{rel:<55} {summary_hashes[rel]}" for rel in sorted_rel]
        sm_block += ["-" * 72,
                     f"summary_combined_sha256: {summary_combined}",
                     "=" * 72]
        lines += sm_block

    # ── PRECHECK REPORT bölümü: precheck-report/ önekli dosyalar (CONFIG gibi) ─
    # publish_precheck.sh AŞAMA 0 kapılarının çıktı raporu ayrıca işaretlenir;
    # combined_sha256 tek hash ile özetler (config.combined_sha256 ile aynı
    # deterministik yöntem). Böylece precheck advisory bulguları da
    # denetim zincirinde (precheck→hash→manifest→bundle).
    precheck_hashes = {rel: h for rel, h in file_hashes.items()
                       if rel.startswith("precheck-report/")}
    precheck_combined = None
    if precheck_hashes:
        sorted_rel = sorted(precheck_hashes)
        precheck_combined = hashlib.sha256(
            "".join(f"{rel}\0{precheck_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        pr_block = [
            "",
            "=" * 72,
            "PRECHECK REPORT ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        pr_block += [f"{rel:<55} {precheck_hashes[rel]}" for rel in sorted_rel]
        pr_block += ["-" * 72,
                     f"precheck_combined_sha256: {precheck_combined}",
                     "=" * 72]
        lines += pr_block

    # ── ACTION RUNTIMES bölümü: action_runtimes.json (isimle tanınır) ─────
    # action-runtimes job'ının çıktısı (check_action_runtimes.py →
    # action_runtimes.json) ayrıca işaretlenir; combined_sha256 tek hash ile
    # özetler (config.combined_sha256 ile aynı deterministik yöntem). Böylece
    # node24/native action sürüm denetiminin raporu da denetim zincirinde.
    action_runtimes_hashes = {rel: h for rel, h in file_hashes.items()
                              if _is_action_runtimes_rel(rel)}
    action_runtimes_combined = None
    if action_runtimes_hashes:
        sorted_rel = sorted(action_runtimes_hashes)
        action_runtimes_combined = hashlib.sha256(
            "".join(f"{rel}\0{action_runtimes_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        ar_block = [
            "",
            "=" * 72,
            "ACTION RUNTIMES ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        ar_block += [f"{rel:<55} {action_runtimes_hashes[rel]}" for rel in sorted_rel]
        ar_block += ["-" * 72,
                     f"action_runtimes_combined_sha256: {action_runtimes_combined}",
                     "=" * 72]
        lines += ar_block

    # ── PYTHON3 SHELL bölümü: python3-shell/ önekli dosyalar (CONFIG gibi) ──
    # check_python3_shell.py --json çıktısı (python3_shell_findings.json)
    # ayrıca işaretlenir; combined_sha256 tek hash ile özetler
    # (config.combined_sha256 ile aynı deterministik yöntem). Böylece
    # `shell: python3 {0}` kabuk-komutu denetiminin makine-okur raporu da
    # SHA-256 ile sabitlenmiş denetim zincirinde (python3-shell → hash →
    # manifest → bundle).
    python3_shell_hashes = {rel: h for rel, h in file_hashes.items()
                            if rel.startswith("python3-shell/")}
    python3_shell_combined = None
    if python3_shell_hashes:
        sorted_rel = sorted(python3_shell_hashes)
        python3_shell_combined = hashlib.sha256(
            "".join(f"{rel}\0{python3_shell_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        ps_block = [
            "",
            "=" * 72,
            "PYTHON3 SHELL ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        ps_block += [f"{rel:<55} {python3_shell_hashes[rel]}"
                     for rel in sorted_rel]
        ps_block += ["-" * 72,
                     f"python3_shell_combined_sha256: {python3_shell_combined}",
                     "=" * 72]
        lines += ps_block

    # ── PLIST CHECK bölümü: plist-check/ önekli dosyalar (CONFIG gibi) ──────
    # update_preview.sh --plist-check çıktısı (plist_check_report.txt)
    # + K12 sidecar (plist_report.json) ayrıca işaretlenir;
    # combined_sha256 tek hash ile özetler.
    plist_check_hashes = {rel: h for rel, h in file_hashes.items()
                          if rel.startswith("plist-check/")}
    plist_check_combined = None
    if plist_check_hashes:
        sorted_rel = sorted(plist_check_hashes)
        plist_check_combined = hashlib.sha256(
            "".join(f"{rel}\0{plist_check_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        pc_block = [
            "",
            "=" * 72,
            "PLIST CHECK ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        pc_block += [f"{rel:<55} {plist_check_hashes[rel]}"
                     for rel in sorted_rel]
        pc_block += ["-" * 72,
                     f"plist_check_combined_sha256: {plist_check_combined}",
                     "=" * 72]
        lines += pc_block

    # ── OVERRIDES bölümü: cli_overrides_version.json (CLI override kaydı) ──
    # check_cli_overrides.py --version-out çıktısı; CONFIG gibi ayrıca
    # işaretlenir. combined_sha256 tek hash ile özetler (config.combined_sha256
    # ile aynı deterministik yöntem). Böylece CLI override'ları da denetim
    # zincirinde (override → hash → manifest → bundle).
    overrides_hashes = {rel: h for rel, h in file_hashes.items()
                        if _is_overrides_rel(rel)}
    overrides_combined = None
    if overrides_hashes:
        sorted_rel = sorted(overrides_hashes)
        overrides_combined = hashlib.sha256(
            "".join(f"{rel}\0{overrides_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        ov_block = [
            "",
            "=" * 72,
            "OVERRIDES ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        ov_block += [f"{rel:<55} {overrides_hashes[rel]}"
                     for rel in sorted_rel]
        ov_block += ["-" * 72,
                     f"overrides_combined_sha256: {overrides_combined}",
                     "=" * 72]
        lines += ov_block

    # ── UNIT TESTS bölümü: unit_tests.log (test çıktıları) ──────────────────
    # verify job'undaki unittest discover çıktısı (unit_tests.log) ayrıca
    # işaretlenir; combined_sha256 tek hash ile özetler. Böylece test
    # suite'inin hangi versiyonunun koşulduğu denetim zincirinde sabitlenir.
    unit_test_hashes = {rel: h for rel, h in file_hashes.items()
                        if rel == "unit_tests.log" or rel.startswith("unit-tests/")}
    unit_test_combined = None
    if unit_test_hashes:
        sorted_rel = sorted(unit_test_hashes)
        unit_test_combined = hashlib.sha256(
            "".join(f"{rel}\0{unit_test_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        ut_block = [
            "",
            "=" * 72,
            "UNIT TESTS ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        ut_block += [f"{rel:<55} {unit_test_hashes[rel]}"
                     for rel in sorted_rel]
        ut_block += ["-" * 72,
                     f"unit_tests_combined_sha256: {unit_test_combined}",
                     "=" * 72]
        lines += ut_block

    # ── RUN LOGS bölümü: run-*.json + history.jsonl (denetim zaman serisi) ──
    # preview_server.py RUNS_DIR'deki run-*.json dosyaları VEYA CI'daki
    # run-history artifact'ındaki history.jsonl + .sha256 tarafindan
    # uretilir. combined_sha256 ile sabitlenir.
    run_log_hashes = {rel: h for rel, h in file_hashes.items()
                      if rel.startswith("runs/run-") or rel == "history.jsonl"
                      or rel == "history.jsonl.sha256"
                      or rel.startswith("run-history/")}
    run_log_combined = None
    if run_log_hashes:
        sorted_rel = sorted(run_log_hashes)
        run_log_combined = hashlib.sha256(
            "".join(f"{rel}\0{run_log_hashes[rel]}\n"
                     for rel in sorted_rel).encode()
        ).hexdigest()
        rl_block = [
            "",
            "=" * 72,
            "RUN LOGS ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        rl_block += [f"{rel:<55} {run_log_hashes[rel]}"
                     for rel in sorted_rel]
        rl_block += ["-" * 72,
                     f"run_logs_combined_sha256: {run_log_combined}",
                     "=" * 72]
        lines += rl_block

    # ── PROVENANCE bölümü: artifact → üreten job (denetim izi) ──────────────
    # Her artifact hangi job'da üretildi — tek bakışta kaynak.
    #
    # Üç indirme modu var:
    #   prefixed  — download-artifact name=X, path=all_artifacts/X/
    #               (config, precommit-logs, refs-trend, precheck-report,
    #                python3-shell, plist-check)
    #   merged    — merge-multiple: true + pattern ile indirildi,
    #               dosyalar all_artifacts/ köküne düzleşti
    #  .none      — hiç indirilmedi (reproducibility çıkış artifact'ı)
    PREFIXED = frozenset({
        "config", "precommit-logs", "refs-trend", "precheck-report",
        "python3-shell", "plist-check",
    })
    MERGED = frozenset({
        "verify-report", "budget", "budget-verify", "reports",
        "refs-online", "run-history", "config-drift", "repack-verify",
        "k0-findings", "lineage-findings", "klayers", "unit-tests",
        "action-runtimes",
    })
    # Reed dosyaları artifact'a eşle (isim eşleme: merge ile köke düzleşen
    # dosyalar da doğru artifact'a bağlansın)
    present = {}
    for rel in file_hashes:
        top = rel.split("/", 1)[0]
        # Config dosyaları isimle tanınır: config/ öneki kaybolsa bile
        # (merge-multiple köke düzleştirir) "config" artifact'ına bağlanır.
        if top not in artifact_jobs and _is_config_rel(rel):
            top = "config"
        # Summary sidecar dosyaları isimle tanınır: merge-multiple ile
        # köke düzleşen klayers.json, lineage_findings.json vb.
        if top not in artifact_jobs and _is_summary_rel(rel):
            bn = os.path.basename(rel)
            _SUMMARY_ARTIFACT_MAP = {
                "klayers.json": "klayers",
                "lineage_findings.json": "lineage-findings",
                "k0_findings.json": "k0-findings",
                "budget_verify.json": "budget-verify",
            }
            top = _SUMMARY_ARTIFACT_MAP.get(bn, "klayers")
        # Action runtime raporu isimle tanınır.
        if top not in artifact_jobs and _is_action_runtimes_rel(rel):
            top = "action-runtimes"
        if top in artifact_jobs:
            present.setdefault(top, []).append(rel)
    prov_block = [
        "",
        "=" * 72,
        "PROVENANCE (artifact → job kaynağı)",
        "=" * 72,
        f"{'ARTIFACT':<20} {'JOB':<22} BUNDLE",
        "-" * 72,
    ]
    for art in sorted(artifact_jobs):
        job = artifact_jobs[art]
        files = present.get(art)
        if files:
            if art in PREFIXED:
                note = f"prefixed ({len(files)} dosya)"
            elif art in MERGED:
                note = f"köke düzleştirildi ({len(files)} dosya)"
            else:
                note = f"{len(files)} dosya"
        elif art in PREFIXED:
            note = "YOK (indirilmedi — prefix subdir)"
        elif art in MERGED:
            note = "YOK (merge pattern'de ama dosya tanınamadı)"
        else:
            note = "çıkış artifact'ı (indirilmez)"
        prov_block.append(f"{art:<20} {job:<22} {note}")
    prov_block.append("=" * 72)
    lines += prov_block

    manifest_json = {
        "tool": "stoic-hume-v5-reproducibility",
        "generated": now,
        "github_run_id": run_id,
        "github_sha": sha,
        "github_ref": ref,
        "github_repository": repo,
        "github_run_url": run_url,
        "files": file_hashes,
        "provenance": {"artifact_jobs": dict(sorted(artifact_jobs.items()))},
    }
    if config_hashes:
        manifest_json["config"] = {
            "files": dict(sorted(config_hashes.items())),
            "combined_sha256": config_combined,
        }
    if precommit_hashes:
        manifest_json["precommit_logs"] = {
            "files": dict(sorted(precommit_hashes.items())),
            "combined_sha256": precommit_combined,
        }
    if refs_trend_hashes:
        manifest_json["refs_trend"] = {
            "files": dict(sorted(refs_trend_hashes.items())),
            "combined_sha256": refs_trend_combined,
        }
    if lineage_hashes:
        manifest_json["lineage"] = {
            "files": dict(sorted(lineage_hashes.items())),
            "combined_sha256": lineage_combined,
        }
    if summary_hashes:
        manifest_json["summary"] = {
            "files": dict(sorted(summary_hashes.items())),
            "combined_sha256": summary_combined,
        }
    if precheck_hashes:
        manifest_json["precheck_report"] = {
            "files": dict(sorted(precheck_hashes.items())),
            "combined_sha256": precheck_combined,
        }
    if action_runtimes_hashes:
        manifest_json["action_runtimes"] = {
            "files": dict(sorted(action_runtimes_hashes.items())),
            "combined_sha256": action_runtimes_combined,
        }
    if python3_shell_hashes:
        manifest_json["python3_shell"] = {
            "files": dict(sorted(python3_shell_hashes.items())),
            "combined_sha256": python3_shell_combined,
        }
    if plist_check_hashes:
        manifest_json["plist_check"] = {
            "files": dict(sorted(plist_check_hashes.items())),
            "combined_sha256": plist_check_combined,
        }
    if overrides_hashes:
        manifest_json["overrides"] = {
            "files": dict(sorted(overrides_hashes.items())),
            "combined_sha256": overrides_combined,
        }
    if unit_test_hashes:
        manifest_json["unit_tests"] = {
            "files": dict(sorted(unit_test_hashes.items())),
            "combined_sha256": unit_test_combined,
        }
    if run_log_hashes:
        manifest_json["run_logs"] = {
            "files": dict(sorted(run_log_hashes.items())),
            "combined_sha256": run_log_combined,
        }

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "manifest.txt").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # manifest.json'un kendi SHA-256'sı — sidecar (sha256sum formatı).
    # manifest.json içeriği değişirse sidecar artık eşleşmez; böylece
    # manifest'in kendisi (dosya hash'lerinin listesi) tek hash ile denetlenir.
    manifest_sha = sha256_file(out_dir / "manifest.json")
    (out_dir / "manifest.sha256").write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8")

    # Artifact'ları bundle'a kopyala (manifest yanında)
    for child in root.iterdir():
        dest = out_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    total_bytes = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    print(f"Manifest: {len(file_hashes)} files hashed, run_id={run_id}")
    print(f"Bundle size: {total_bytes} bytes")
    print(f"Output: {out_dir}/manifest.txt, {out_dir}/manifest.json, "
          f"{out_dir}/manifest.sha256")


if __name__ == "__main__":
    main()
