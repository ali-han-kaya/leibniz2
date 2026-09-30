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
  - ÜÇÜNCÜ HEDEF (2026-09-30 boşluğu): EXCLUDE'daki her testin koşma yeri
    AÇIKÇA bildirilir (EXCLUDE_HOOKS → hook id, EXCLUDE_CI_JOBS → CI job id)
    ve bildirilen hedefin repo'da GERÇEKTEN var olduğu doğrulanır. EXCLUDE bir
    testi manifest'ten çıkarır; bağlamasız bir test HİÇBİR YERDE koşmaz.
    Ölçülen boşluk: "CI'da X job'ında koşar" iddiaları yalnızca yorumlarda
    yaşıyordu; tam-discover emniyet ağı olan `ci_full_discover_drift_guard.py`
    ise repo'da hiçbir yere bağlı değildi (workflow/pre-commit/manifest: 0
    eşleşme) — yani job yeniden adlandırıldığında kapı sessizce körleşiyordu.
    Bu hedef YAZMAZ: bildirim gerekçesiyle kod içinde elle verilir.
  - --check: HERHANGİ BİRİ drift'liyse exit 1 (fail-closed kapı — pre-commit/CI)
  - --update: senkronlanabilen hedefleri (manifest + HOOK_COVERAGE) günceller,
    değişenleri git add ile stage eder

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
import os
import re
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
    # ⚠️ changelog'in İKİ-YAZAN değişmezi (bkz. update_changelog_hook.sh):
    # test_update_changelog_hook.py ve test_gen_changelog.py ESKİDEN buradaydı
    # ("check-changelog-sync" koşuyor diye) — ama o hook'un entry'si yalnızca
    # update_changelog_hook.sh'tir; testleri hiç koşmuyordu. 2026-09-30'da
    # EXCLUDE'tan çıkarıldı: artık check-unit-tests manifest'inden GERÇEKTEN
    # koşarlar (fail-closed), yani "kapı var" beyanı doğru olur.
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
    "test_gen_config.py",                  # update-config
    "test_github_scripts_battery.py",      # verify-delivery-github-scripts
    "test_all_hooks_smoke.py",             # tüm hook'ları koşar (smoke) — kendini çağırır

    # ağır/kataloglama testleri (manifest/repro) — ayrı job'lar
    "test_repro_manifest_topology.py",

    # Playwright integration smoke test: Chromium needed, ~10s/run, starts
    # its own preview_server.py. Runs standalone, not in the 10s pre-commit
    # gate (pre-commit's check-unit-tests budget would blow up).
    # Koşma yeri: `verify` job'ının full discover'ı (EXCLUDE_CI_JOBS).
    # Playwright `a11y-gate` job'ında kuruluyor ama o job bu testi koşmuyor;
    # full discover Playwright kurulu olmadan çalıştığı için test CI'da SKIP'e
    # düşer (ortam-yok ≠ kod-bozuk sözleşmesi) — ölçüldü 2026-09-30.
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
# HOOK_COVERAGE["check-unit-tests"] bloğu. ci_full_discover_drift_guard.py
# bu bloğu statik metin parse ile okur (anahtar → ilk `],`); yeniden yazım
# bu formatı birebir korur.
# ────────────────────────────────────────────────────────────────────────────

HOOK_COVERAGE_KEY = '"check-unit-tests":'


def _hook_coverage_span(src):
    """Kaynak metinde bloğun [gövde] span'ını döndürür (None: blok yok)."""
    i = src.find(HOOK_COVERAGE_KEY)
    if i < 0:
        return None
    b = src.find("[", i)
    if b < 0:
        return None
    e = src.find("],", b)
    if e < 0:
        return None
    return b + 1, e


def _entry_indent(body):
    """Bloktaki ilk girdinin girintisini döndürür (8 boşluk beklenir)."""
    m = re.search(r'\n(\s*)"', body)
    return m.group(1) if m else "        "


def read_hook_coverage(path=None):
    """Bloktaki tüm girdileri (py + js) sıra korunarak döndürür."""
    p = path or COVERAGE_FILE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        src = f.read()
    span = _hook_coverage_span(src)
    if span is None:
        return []
    body = src[span[0]:span[1]]
    return re.findall(r'"([^"]+\.(?:py|js))"', body)


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


def _rewrite_hook_coverage(src, entries, add, orphan):
    span = _hook_coverage_span(src)
    body = src[span[0]:span[1]]
    indent = _entry_indent(body)
    orphan_set = set(orphan)
    add_set = set(add)
    kept = [e for e in entries if e not in orphan_set]
    new_entries = kept + [a for a in sorted(add_set)]
    new_body = "\n" + "\n".join(indent + '"%s",' % e for e in new_entries)
    return src[:span[0]] + new_body + src[span[1]:]


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
    with open(p, encoding="utf-8") as f:
        src = f.read()
    span = _hook_coverage_span(src)
    if span is None:
        # Hedef bozuksa sessiz başarı yerine dürüst hata; rc'yi update-sonrası
        # run_check fail-closed yapar.
        print(f"HATA: HOOK_COVERAGE['check-unit-tests'] bloğu okunamadı: {p} "
              "— ikinci hedef senkronlanmadı.")
        return False, [], []
    entries = read_hook_coverage(p)
    add, orphan = diff_hook_coverage(
        discovered if discovered is not None else discover(), entries, d)
    if not add and not orphan:
        return False, [], []
    new_src = _rewrite_hook_coverage(src, entries, add, orphan)
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


# ────────────────────────────────────────────────────────────────────────────
# EXCLUDE ↔ CI-job/hook BAĞLAMASI (2026-09-30, üçüncü hedef)
#
# EXCLUDE, bir testi pre-commit manifest'inden çıkarır; bu testin tek koşma
# yeri ya kendi kapısıdır (pre-commit hook) ya da bir CI job'ıdır. O bağ önceden
# YALNIZCA yorumlarda yaşıyordu ("(plist-check)", "(daemon-http job)", ...) ve
# ölçülen iki kör nokta vardı:
#   1) `ci_full_discover_drift_guard.py` (tam discover emniyet ağı) repo'da
#      HİÇBİR yere bağlı değil → "CI her şeyi koşar" sözleşmesinin makinesel
#      garantisi yok.
#   2) Bir job yeniden adlandırıldığında/kaldırıldığında test sessizce HİÇBİR
#      YERDE koşmaz: manifest koşmaz (EXCLUDE'lu), emniyet ağı da bağlı değil.
# Aşağıdaki iki sözlük o bağı AÇIKÇA bildirir; run_check_exclude_binding()
# her iki yönü de doğrular ve --check'te fail-closed bloklar.
# ────────────────────────────────────────────────────────────────────────────
EXCLUDE_HOOKS = {
    # Kendi kapısı olan testler — hook id, .pre-commit-config.yaml'da yaşar.
    "test_check_bibliography_sync.py":       "check-bibliography-sync",
    "test_check_config_sync.py":             "check-config-sync",
    "test_check_plist_drift.py":             "check-plist-drift",
    "test_check_refs_table_sync.py":         "check-refs-table-sync",
    "test_check_review_freshness.py":        "check-review-freshness",
    "test_colorize_rules.py":                "check-colorize-rules",
    "test_doc_artifact_sync.py":             "check-doc-artifact-sync",
    "test_dryrun_summary.py":                "check-dryrun-summary",
    "test_gen_config.py":                    "update-config",
    "test_gen_plist_golden.py":              "check-plist-drift",
    "test_gen_repro_manifest.py":            "check-repro-manifest",
    "test_github_scripts_battery.py":        "verify-delivery-github-scripts",
    "test_ia_ol_fallback_evidence.py":       "check-fallback-evidence",
    "test_lake_evidence_smoke.py":           "check-lake-evidence",
    "test_plist_gate_exit.py":               "check-plist-drift",
    "test_verify_manifest_overrides.py":     "verify-delivery-repro-manifest",
    "test_verify_manifest_sidecar.py":       "verify-delivery-repro-manifest",
}

EXCLUDE_CI_JOBS = {
    # ÖZEL CI job'ı olanlar — job id, .github/workflows/* içindeki jobs:
    # bloğunda yaşar. Yeniden adlandırılırsa kapı kırılır (istenen davranış).
    "test_daemon_http.py":                   "daemon-http",
    "test_fresh_clone_setup.py":             "fresh-clone-http",
    "test_preview_reload_smoke.py":          "preview-reload-smoke",
    # Özel job'ı olmayanlar — koşma yeri `verify` job'ının tam discover
    # adımıdır (`unittest discover -p "test_*.py"`, verify.yml). Yorumlardaki
    # "CI" imaları buraya bağlanır; sentinel satırı kaybolursa (denetim 4)
    # hepsi birden kırmızıya döner.
    "test_all_hooks_smoke.py":               "verify",
    "test_check_history.py":                 "verify",
    "test_cleanup.py":                       "verify",
    "test_dashboard_playwright_smoke.py":    "verify",  # dashboard-next YOK (ölçüldü)
    "test_k18_daemon.py":                    "verify",
    "test_preview_prestart.py":              "verify",
    "test_repro_manifest_topology.py":       "verify",
    "test_verify_refs.py":                   "verify",  # refs-online adımı verify içinde
}

# "EXCLUDE'lu testleri CI koşar" vaadinin makinesel kanıtı: `verify` job'ının
# tam discover satırı. Bu satır workflow'lardan silinirse (ya da `-p "test_*.py"`
# deseni değişirse) hiçbir EXCLUDE'lu testin koşma yeri kalmaz → FAIL.
FULL_DISCOVER_SENTINEL = '-p "test_*.py"'

WORKFLOWS_DIR = os.path.join(ROOT, ".github", "workflows")
PRECOMMIT_CONFIG = os.path.join(ROOT, ".pre-commit-config.yaml")


def read_workflows_text(workflows_dir=None):
    """Workflow dosyalarının metinleri (dizin yoksa boş liste → kör kapı)."""
    d = workflows_dir or WORKFLOWS_DIR
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith((".yml", ".yaml")):
            try:
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    out.append(fh.read())
            except OSError:
                continue
    return out


def workflow_ci_tokens(workflows_dir=None):
    """CI yüzeyi token'ları: `jobs:` altındaki job id'ler + job/step adları.

    PyYAML yok (stdlib-only kuralı): `jobs:` bloğunu satır taramasıyla bulur,
    iki boşluklu job id'lerini ve blok içindeki `name:` değerlerini toplar.
    """
    tokens = set()
    for blob in read_workflows_text(workflows_dir):
        in_jobs = False
        for line in blob.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line):
                in_jobs = False
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
            if m:
                tokens.add(m.group(1))
            m = re.match(r"^\s*(?:-\s+)?name:\s*(.+?)\s*$", line)
            if m:
                tokens.add(m.group(1).strip().strip("\"'"))
    return tokens


def precommit_hook_ids(config_path=None):
    """`- id: <hook>` girdilerinin kümesi (PyYAML yok, satır taraması)."""
    p = config_path or PRECOMMIT_CONFIG
    try:
        with open(p, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return set()
    return set(re.findall(r"^\s*-\s+id:\s*([A-Za-z0-9_-]+)\s*$", src, re.M))


def run_check_exclude_binding(exclude=None, ci_jobs=None, hooks=None,
                              workflows_dir=None, config_path=None):
    """EXCLUDE ↔ CI-job/hook bağlama kapısı; drift varsa 1 döndür (fail-closed).

    Dört ölçülebilir denetim (hiçbiri yoruma dayanmaz):
      1) BAĞSIZ    — her EXCLUDE girdisi bir hedefe bağlı olmalı (bağlamasız
         test = manifest'te de, CI'da da koşmayan test).
      2) KÖR HEDEF  — bildirilen CI job id'si workflow'larda, hook id'si
         config'de GERÇEKTEN var olmalı; yeniden adlandırılan kapı sessizce
         körleştiremez.
      3) TERS BAĞ   — EXCLUDE'da olmayan teste bildirim ve aynı teste çift
         bağlama (belirsizlik) kabul edilmez.
      4) SÖZLEŞME   — full-discover sentinel satırı workflow'larda durmalı.

    Yazmaz: bildirim gerekçesiyle elle verilir (bu kapının yazma yetkisi
    yok — repo'da üç yazan hook var: update-config, check-changelog-sync,
    check-skills-index).
    """
    ex = set(EXCLUDE if exclude is None else exclude)
    cij = dict(EXCLUDE_CI_JOBS if ci_jobs is None else ci_jobs)
    hk = dict(EXCLUDE_HOOKS if hooks is None else hooks)
    rc = 0

    blobs = read_workflows_text(workflows_dir)
    cfg_ids = precommit_hook_ids(config_path)
    if not blobs and not cfg_ids:
        # İZOLE KOŞUM: hook'un sandbox kopyası (test izolasyonu) — repo yüzeyi
        # YOK. Bu kapı repo-geneldir; doğrulayacak yüzey bulunmadığında "kapalı"
        # denemez, "kapsam dışı" denir. Kısmi yüzey (biri var, diğeri yok) ise
        # drift sayılır → fail-closed.
        print("NOT: repo yüzeyi yok (izole koşum) — EXCLUDE↔CI-job bağlaması "
              "atlandı.")
        return 0
    if not blobs:
        print("HATA: workflow yüzeyi okunamadı — EXCLUDE↔CI-job bağlaması "
              "doğrulanamaz, commit bloklanır.")
        return 1
    if not cfg_ids:
        print("HATA: pre-commit config okunamadı — EXCLUDE↔hook bağlaması "
              "doğrulanamaz, commit bloklanır.")
        return 1

    unbound = sorted(ex - set(cij) - set(hk))
    if unbound:
        print("EXCLUDE'da koşma yeri bildirilmemiş test: " + ", ".join(unbound))
        print("  Çözüm: EXCLUDE_CI_JOBS (CI job id'si) veya EXCLUDE_HOOKS "
              "(hook id) sözlüğüne gerekçeli bir girdi ekle. Bağlamasız test "
              "manifest'te de koşmaz, CI'da da koşmaz — sessiz kapsam kaybı.")
        rc = 1

    tokens = workflow_ci_tokens(workflows_dir)
    missing_jobs = sorted({j for j in cij.values() if j not in tokens})
    if missing_jobs:
        print("EXCLUDE bağlaması, workflow'larda OLMAYAN CI job'a işaret ediyor: "
              + ", ".join(sorted(set(missing_jobs))))
        print("  Çözüm: job id'si workflow'ta gerçekten var mı? Yeniden "
              "adlandırıldıysa EXCLUDE_CI_JOBS güncellenmeli.")
        rc = 1

    missing_hooks = sorted({h for h in hk.values() if h not in cfg_ids})
    if missing_hooks:
        print("EXCLUDE bağlaması, config'de OLMAYAN hook'a işaret ediyor: "
              + ", ".join(sorted(set(missing_hooks))))
        print("  Çözüm: hook id'si .pre-commit-config.yaml'da var mı? Silinmiş/"
              "yeniden adlandırılmışsa EXCLUDE_HOOKS güncellenmeli.")
        rc = 1

    stale = sorted((set(cij) | set(hk)) - ex)
    if stale:
        print("EXCLUDE'da olmayan test için bağlama bildirilmiş (ters bağ): "
              + ", ".join(stale))
        print("  Çözüm: girdiyi kaldır ya da testi gerçekten EXCLUDE et.")
        rc = 1

    both = sorted(set(cij) & set(hk))
    if both:
        print("Aynı test iki hedefe bağlanmış (belirsizlik): " + ", ".join(both))
        print("  Çözüm: tek hedef seç — hangi kapı bu testi fiilen koşuyor?")
        rc = 1

    if not any(FULL_DISCOVER_SENTINEL in b for b in blobs):
        print(f"CI full-discover satırı yok (sentinel: {FULL_DISCOVER_SENTINEL}) — "
              "\"EXCLUDE'lu testleri CI koşar\" sözleşmesi ölçülemez.")
        print("  Çözüm: verify job'ındaki `unittest discover -p \"test_*.py\"` "
              "adımını geri getir ya da EXCLUDE'lu testleri özel job'lara bağla.")
        rc = 1

    return rc


def run_check(directory=None, manifest=None, coverage=None):
    """manifest VEYA HOOK_COVERAGE VEYA EXCLUDE-bağlaması drift'liyse 1 döndür."""
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
    # Üçüncü hedef: EXCLUDE ↔ CI-job/hook bağlaması. Repo-geneli bir
    # denetimdir (EXCLUDE kümesi ve workflow yüzeyi tekil); izole koşumda
    # (--dir) çalıştırılmaz — sandbox testleri kendi yüzeyini enjekte eder.
    if directory is None and run_check_exclude_binding() == 1:
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
    ap.add_argument("--check", action="store_true",
                    help="manifest/HOOK_COVERAGE/EXCLUDE-bağlaması drift'indeyse exit 1")
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
