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
  - --check: drift varsa exit 1 (fail-closed kapı — pre-commit/CI)
  - --update: manifest'i senkronlar ve git add ile stage eder (pre-commit kancada)

pre-commit hook entry'si manifest dosyasından okur; böylece TEK KAYNAK diskteki
gerçek test dosyalarıdır ve yeni test dosyası eklendiğinde hiçbir elle düzenleme
gerekmez.

Kullanım:
  python3 sync_check_unit_tests.py --check     # drift varsa exit 1
  python3 sync_check_unit_tests.py --update    # manifest'i senkronla + stage
  python3 sync_check_unit_tests.py --list      # koşulacak testleri yazdır

stdlib only — PyYAML/yok bağımlılık.
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")
MANIFEST = os.path.join(CIKTI, "check_unit_tests.list")

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


def run_check(directory=None, manifest=None):
    """manifest diskle senkron değilse 1 döndür (fail-closed)."""
    disc = discover(directory)
    mf = manifest or MANIFEST
    missing, stale = diff(disc, read_manifest(mf))
    if missing or stale:
        if missing:
            print(f"YENİ test dosyası check-unit-tests listesinde YOK: {', '.join(missing)}")
        if stale:
            print(f"Manifest'te artık olmayan dosya: {', '.join(stale)}")
        print("Çözüm: `pre-commit` hook otomatik günceller — dosyayı stage edip yeniden commit et.")
        return 1
    return 0


def run_update(stage=True, directory=None, manifest=None):
    """manifest'i diskteki gerçek test kümesiyle senkronlar; değiştiyse stage eder."""
    disc = discover(directory)
    mf = manifest or MANIFEST
    missing, stale = diff(disc, read_manifest(mf))
    if not missing and not stale:
        return False
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
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="check-unit-tests liste senkronu")
    ap.add_argument("--check", action="store_true", help="manifest drift'indeyse exit 1")
    ap.add_argument("--update", action="store_true", help="manifest'i güncelle + stage (varsayılan)")
    ap.add_argument("--no-stage", action="store_true", help="git add yapma (test izolasyonu)")
    ap.add_argument("--list", action="store_true", help="koşulacak testleri listele")
    ap.add_argument("--dir", default=None, help="test dizini (test izolasyonu)")
    ap.add_argument("--manifest", default=None, help="manifest yolu (test izolasyonu)")
    args = ap.parse_args(argv)

    mf = args.manifest or MANIFEST

    if args.list:
        for n in discover(args.dir):
            print(n)
        return 0

    if args.update or not args.check:
        run_update(stage=not args.no_stage, directory=args.dir, manifest=mf)
        return 0

    return run_check(args.dir, mf)


if __name__ == "__main__":
    sys.exit(main())