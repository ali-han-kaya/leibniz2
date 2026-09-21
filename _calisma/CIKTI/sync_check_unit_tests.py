#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_check_unit_tests.py — check-unit-tests'in test listesini otomatik senkron eder.

Sorun: .pre-commit-config.yaml'daki check-unit-tests hook'u `for t in <17 isim>`
biçiminde SABİT bir liste kullanıyor. Yeni bir test_*.py dosyası eklendiğinde
liste elle güncellenmezse yeni test commit'te koşulmaz (gate kapsamı sessizce
zayıflar).

Bu script, update-config/update-changelog desenindeki gibi auto-sync yapar:
  - _calisma/CIKTI/test_*.py dosyalarını TARAR
  - ORTAM-BAĞIMLI testleri (launchctl/daemon/canlı sunucu; EXCLUDE seti)
    dışarıda tutar — bunlar commit'i yavaşlatır/kırabilir, CI'da ayrı job'ları var
  - check_unit_tests.list manifest'ini günceller (yeni ekle, silineni çıkar)
  - İKİNCİ HEDEF (2026-09-17 boşluğu): test_coverage_report.py içindeki
    HOOK_COVERAGE["check-unit-tests"] listesini de senkron eder. Manifest
    güncelken HOOK_COVERAGE unutulursa check-coverage-report kapısı
    "uncovered by any hook" FAIL'i üretir (ölçüldü: test_texlive_
    determinism_id_residual.py tam bu boşluktan düştü). Yeni keşifler bloğun
    sonuna alfabetik eklenir; mevcut girdiler (.js ve EXCLUDE'lular dahil)
    korunur; yalnız diskte artık bulunmayan girdiler (orphan) çıkarılır.
  - --check: HERHANGİ BİRİ drift'liyse exit 1 (fail-closed kapı — pre-commit/CI)
  - --update: her iki hedefi senkronlar ve değişenleri git add ile stage eder

pre-commit hook entry'si manifest dosyasından okur; böylece TEK KAYNAK diskteki
gerçek test dosyalarıdır ve yeni test dosyası eklendiğinde hiçbir elle düzenleme
gerekmez.

Kullanım:
  python3 sync_check_unit_tests.py --check     # drift varsa exit 1
  python3 sync_check_unit_tests.py --update    # manifest + HOOK_COVERAGE senkron + stage
  python3 sync_check_unit_tests.py --list      # koşulacak testleri yazdır

stdlib only — PyYAML/yok bağımlılık.
"""

import argparse
import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")
MANIFEST = os.path.join(CIKTI, "check_unit_tests.list")
COVERAGE_FILE = os.path.join(CIKTI, "test_coverage_report.py")

# ────────────────────────────────────────────────────────────────────────────
# EXCLUDE — pre-commit'te koşulmaması gereken testler (ortam-bağımlı):
#  - launchctl/plist/daemon/canlı-sunucu gerektiren testler CI job'larında koşar
#    (plist-check, daemon-http, preview-reload-smoke, refs-online)
#  - ağ gerektiren referans doğrulama: refs-online CI job'ında koşar
#  - kendi gate'i olanlar (check-repro-manifest, check-refs-table-sync,
#    check-config-sync, check-dryrun-summary, ...) doğrudan kendi hook'ları
#    tarafından koşulur.
#  ⚠️ Burası YALNIZCA commit hızı/sağlamlığı içindir; CI "tüm test_*.py"
#    discover'ı ile HER ŞEYİ yine koşar (tam suite ~1400 test).
# ────────────────────────────────────────────────────────────────────────────
EXCLUDE = {
    # launchctl / daemon / canlı servis gerektirenler — CI job'larında koşar
    "test_plist_gate_exit.py",        # launchctl + fake HOME (check-plist-drift)
    "test_check_plist_drift.py",      # launchctl (check-plist-drift)
    "test_doc_artifact_sync.py",      # kendi gate'i: check-doc-artifact-sync hook'u
    "test_gen_plist_golden.py",       # plist golden üretir (check-plist-drift)
    "test_daemon_http.py",            # canlı daemon sunucusu (daemon-http job)
    "test_preview_reload_smoke.py",   # canlı preview (preview-reload-smoke job)
    "test_k18_daemon.py",             # canlı daemon smoke (CI)
    "test_cleanup.py",                # launchctl cleanup — ortam-etkili
    "test_fresh_clone_setup.py",      # kurulum betiği — yavaş/CI advisory
    "test_check_history.py",          # daemon history sidecar (CI daemon job)
    "test_preview_prestart.py",       # preview prestart — daemon zinciri (CI)
    "test_lake_evidence_smoke.py",    # lake/lean gerektirir (check-lake-evidence hook'u)

    # ağ gerektiren referans doğrulama (refs-online CI job)
    "test_verify_refs.py",
    "test_ia_ol_fallback_evidence.py",

    # kendi hook'u olan / yavaş kapı testleri (o hook'lar zaten koşar)
    "test_gen_repro_manifest.py",          # check-repro-manifest
    "test_verify_manifest_sidecar.py",     # verify-delivery-repro-manifest
    "test_verify_manifest_overrides.py",   # verify-delivery-repro-manifest
    "test_check_refs_table_sync.py",       # check-refs-table-sync
    "test_check_bibliography_sync.py",     # check-bibliography-sync
    "test_check_review_freshness.py",      # check-review-freshness
    "test_check_config_sync.py",           # check-config-sync
    "test_dryrun_summary.py",              # check-dryrun-summary
    "test_colorize_rules.py",              # check-colorize-rules
    "test_update_changelog_hook.py",       # check-changelog-sync
    "test_gen_changelog.py",               # check-changelog-sync
    "test_gen_config.py",                  # update-config
    "test_github_scripts_battery.py",      # verify-delivery-github-scripts
    "test_all_hooks_smoke.py",             # tüm hook'ları koşar (smoke) — kendini çağırır

    # ağır/kataloglama testleri (manifest/repro) — ayrı job'lar
    "test_repro_manifest_topology.py",

    # Playwright integration smoke test: Chromium needed, ~10s/run, starts
    # its own preview_server.py. Runs standalone, not in the 10s pre-commit
    # gate (pre-commit's check-unit-tests budget would blow up).
    "test_dashboard_playwright_smoke.py",
}


def discover(directory=None):
    """dizindeki test_*.py dosyalarını sıralı döndür (EXCLUDE hariç)."""
    d = directory or CIKTI
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if name.startswith("test_") and name.endswith(".py") and name not in EXCLUDE:
            out.append(name)
    return out


def read_manifest(path=None):
    p = path or MANIFEST
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def write_manifest(files, path=None):
    p = path or MANIFEST
    with open(p, "w", encoding="utf-8") as f:
        f.write("# check-unit-tests koşu listesi — sync_check_unit_tests.py --update ile\n")
        f.write("# otomatik üretilir; elle düzenleme gerekmez (pre-commit okur).\n")
        for n in files:
            f.write(n + "\n")


def diff(discovered, manifest):
    s = set(discovered)
    m = set(manifest)
    return sorted(s - m), sorted(m - s)


# ────────────────────────────────────────────────────────────────────────────
# HOOK_COVERAGE senkronu — test_coverage_report.py'deki
# HOOK_COVERAGE["check-unit-tests"] bloğu. Okuma/yazım AST tabanlıdır:
# anahtar→ilk `],` span sezgisi, gövde-içi bir yorumda geçen `],`'da bloğu
# kırpar (ölçüldü). ci_full_discover_drift_guard.py aynı parse'ı buradan
# kullanır (tek kaynak; kopya sezgi yok).
# ────────────────────────────────────────────────────────────────────────────


def _hook_coverage_list_node(tree):
    """HOOK_COVERAGE["check-unit-tests"] değeri olan ast.List düğümünü döndürür
    (None: blok yok)."""
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "HOOK_COVERAGE"
                        for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == "check-unit-tests":
                    return v
    return None


def read_hook_coverage(path=None):
    """Bloktaki tüm girdileri (py + js) sıra korunarak döndürür (AST tabanlı;
    dosya/blok bozuksa [] — üst katman fail-closed rc=1 verir)."""
    p = path or COVERAGE_FILE
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(p))
    except SyntaxError:
        return []
    node = _hook_coverage_list_node(tree)
    if node is None:
        return []
    return [e.value for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def diff_hook_coverage(discovered, entries, cikti_dir=None):
    """(eklenecekler, silinecek_orphanlar) döndürür.

    Kural: keşfedilen (EXCLUDE'suz) yeni .py testleri blokta YOKSA eklenir;
    diskte artık bulunmayan girdiler orphan sayılır. Mevcut girdiler —
    manifest EXCLUDE'unda olsalar bile (ör. .js testleri, CI-job testleri,
    başka hook'ların dosyaları) — korunur; bu blok coverage-TOPLAMIdır,
    koşu manifest'ten gelir. Yani 'add' yalnız KEŞİF kümesine bakar; blokta
    olan ama keşifte olmayan (başka hook'un dosyası) dosyalara dokunmaz.
    """
    d = cikti_dir or CIKTI
    entry_set = set(entries)
    add = [f for f in discovered if f not in entry_set]
    orphan = [e for e in entries if not os.path.exists(os.path.join(d, e))]
    return sorted(add), orphan


def _rewrite_hook_coverage(src, add, orphan):
    """check-unit-tests listesini yeniden yazıp yeni kaynak döndürür
    (None: blok/segment bulunamadı — çağıran fail-closed raporlar)."""
    node = _hook_coverage_list_node(ast.parse(src))
    if node is None:
        return None
    seg = ast.get_source_segment(src, node)
    if seg is None:
        return None
    orphan_set = set(orphan)
    current = [e.value for e in node.elts
               if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    kept = [e for e in current if e not in orphan_set]
    new_entries = kept + sorted(set(add))
    lines = "".join('\n        "%s",' % e for e in new_entries)
    return src.replace(seg, "[" + lines + "\n    ]", 1)


def run_check_hook_coverage(discovered=None, path=None, cikti_dir=None):
    """HOOK_COVERAGE drift'inde 1 döndürür (fail-closed), değilse 0."""
    d = cikti_dir or CIKTI
    entries = read_hook_coverage(path)
    if not entries:
        print("UYARI: HOOK_COVERAGE['check-unit-tests'] bloğu okunamadı — "
              "check-coverage-report kapısı sahte PASS üretebilir.")
        return 1
    add, orphan = diff_hook_coverage(
        discovered if discovered is not None else discover(), entries, d)
    if add:
        print("YENİ keşfedilen test dosyası HOOK_COVERAGE['check-unit-tests'] "
              "listesinde YOK: " + ", ".join(add))
    if orphan:
        print("HOOK_COVERAGE'ta diskte olmayan girdi: " + ", ".join(orphan))
    if add or orphan:
        print("Çözüm: `python3 _calisma/CIKTI/sync_check_unit_tests.py --update`.")
        return 1
    return 0


def run_update_hook_coverage(stage=True, discovered=None, path=None, cikti_dir=None):
    """Bloğu senkronlar; değiştiyse (changed, added, removed) döndürür."""
    p = path or COVERAGE_FILE
    d = cikti_dir or CIKTI
    try:
        with open(p, encoding="utf-8") as f:
            src = f.read()
        ast.parse(src, filename=str(p))
    except (OSError, SyntaxError) as exc:
        # Hedef bozuksa sessiz başarı yerine dürüst hata; rc'yi update-sonrası
        # run_check fail-closed yapar.
        print(f"HATA: HOOK_COVERAGE dosyası okunamadı/parse edilemedi: {p} "
              f"({exc}) — ikinci hedef senkronlanmadı.")
        return False, [], []
    if _hook_coverage_list_node(ast.parse(src)) is None:
        print(f"HATA: HOOK_COVERAGE['check-unit-tests'] bloğu bulunamadı: {p} "
              "— ikinci hedef senkronlanmadı.")
        return False, [], []
    entries = read_hook_coverage(p)
    add, orphan = diff_hook_coverage(
        discovered if discovered is not None else discover(), entries, d)
    if not add and not orphan:
        return False, [], []
    new_src = _rewrite_hook_coverage(src, add, orphan)
    if new_src is None:
        print(f"HATA: HOOK_COVERAGE bloğu yeniden yazılamadı: {p} "
              "— ikinci hedef senkronlanmadı.")
        return False, [], []
    with open(p, "w", encoding="utf-8") as f:
        f.write(new_src)
    if stage:
        try:
            rel = os.path.relpath(p, ROOT)
            subprocess.run(["git", "add", rel], cwd=ROOT, check=False, capture_output=True)
        except OSError:
            pass
    if add:
        print("HOOK_COVERAGE check-unit-tests listesi güncellendi — EKLENDİ: "
              + ", ".join(sorted(add)))
    if orphan:
        print("HOOK_COVERAGE check-unit-tests listesi güncellendi — ÇIKARILDI: "
              + ", ".join(orphan))
    return True, sorted(add), orphan


def _coverage_target(directory, coverage):
    """HOOK_COVERAGE hedef yolunu döndürür; izole koşumda None.

    KORUMA: --dir ile geçici/izole test dizini verilip --coverage verilmediyse
    gerçek test_coverage_report.py'ye ASLA dokunulmaz (aksi halde test
    ortamındaki sahte isimler gerçek coverage haritasına yazılır — ölçüldü:
    test_a.py/test_b.py kirlenmesi).
    """
    if coverage is not None:
        return coverage
    if directory is not None:
        return None  # izole koşum: ikinci hedef devre dışı
    return COVERAGE_FILE


def run_check(directory=None, manifest=None, coverage=None):
    """manifest VEYA HOOK_COVERAGE drift'liyse 1 döndür (fail-closed)."""
    rc = 0
    disc = discover(directory)
    mf = manifest or MANIFEST
    missing, stale = diff(disc, read_manifest(mf))
    if missing or stale:
        if missing:
            print(f"YENİ test dosyası check-unit-tests listesinde YOK: {', '.join(missing)}")
        if stale:
            print(f"Manifest'te artık olmayan dosya: {', '.join(stale)}")
        print("Çözüm: python3 _calisma/CIKTI/sync_check_unit_tests.py --update "
              "(stage eder) — sonra yeniden commit et.")
        rc = 1
    # İkinci hedef: HOOK_COVERAGE['check-unit-tests'] (coverage rapor kapısı).
    cov = _coverage_target(directory, coverage)
    if cov is not None and run_check_hook_coverage(
            discovered=disc, path=cov, cikti_dir=directory) == 1:
        rc = 1
    return rc


def run_update(stage=True, directory=None, manifest=None, coverage=None):
    """manifest + HOOK_COVERAGE'ı diskteki gerçek test kümesiyle senkronlar."""
    disc = discover(directory)
    changed = False
    mf = manifest or MANIFEST
    missing, stale = diff(disc, read_manifest(mf))
    if missing or stale:
        write_manifest(sorted(disc), mf)
        if stage:
            try:
                rel = os.path.relpath(mf, ROOT)
                subprocess.run(["git", "add", rel], cwd=ROOT, check=False, capture_output=True)
            except OSError:
                pass
        if missing:
            print(f"check-unit-tests list güncellendi — EKLENDİ: {', '.join(missing)}")
        if stale:
            print(f"check-unit-tests list güncellendi — ÇIKARILDI: {', '.join(stale)}")
        changed = True
    cov = _coverage_target(directory, coverage)
    if cov is not None:
        # Orphan kontrolü keşif diziniyle AYNI dizinde yapılır; aksi halde
        # izole koşumda geçici isimler gerçek CIKTI'ya göre orphan sanılır.
        cov_changed, _add, _rem = run_update_hook_coverage(
            stage=stage, discovered=disc, path=cov, cikti_dir=directory)
        changed = changed or cov_changed
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="check-unit-tests liste senkronu")
    ap.add_argument("--check", action="store_true", help="manifest/HOOK_COVERAGE drift'indeyse exit 1")
    ap.add_argument("--update", action="store_true", help="manifest + HOOK_COVERAGE güncelle + stage (varsayılan)")
    ap.add_argument("--no-stage", action="store_true", help="git add yapma (test izolasyonu)")
    ap.add_argument("--list", action="store_true", help="koşulacak testleri listele")
    ap.add_argument("--dir", default=None, help="test dizini (test izolasyonu)")
    ap.add_argument("--manifest", default=None, help="manifest yolu (test izolasyonu)")
    ap.add_argument("--coverage", default=None,
                    help="test_coverage_report.py yolu (HOOK_COVERAGE hedefi; test izolasyonu)")
    args = ap.parse_args(argv)

    mf = args.manifest or MANIFEST
    cov = args.coverage or (COVERAGE_FILE if args.dir is None else None)

    if args.list:
        for n in discover(args.dir):
            print(n)
        return 0

    if args.update or not args.check:
        run_update(stage=not args.no_stage, directory=args.dir, manifest=mf, coverage=cov)
        # rc=0 yalnız iki hedef de diskle senkronsa; değilse fail-closed rc=1.
        return run_check(args.dir, mf, cov)

    return run_check(args.dir, mf, cov)


if __name__ == "__main__":
    sys.exit(main())
