#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workflow_contract.py — verify.yml sözleşme kümeleri için TEK KAYNAK.

Geçmişte aynı kümeler 4+ dosyada elle kopyalandı (merge-pattern EXCLUDED
seti summary_pattern_drift.py, check_pattern_consistency.py,
test_gen_repro_manifest.py ve test_doc_artifact_sync.py'de ayrı ayrı
yaşıyordu). Yeni bir job/artifact eklendiğinde dört dosya birden
sürükleme riski taşıyordu; tek kopya kaçtığında kapılar sessizce ayrışıyordu.

Kural: bir küme burada bir kez tanımlanır, üretici modüller ve testler
BURADAN içe aktarır. Drift'i yakalamak için test_workflow_contract.py
hem bu kümeleri hem üreticilerin attr'larını çapraz doğrular.

stdlib-only; yan etkisiz. Ağır tek kaynağa (ARTIFACT_JOBS) PEP 562
__getattr__ ile lazy erişim sağlar — bu modülü import etmek PyYAML veya
başka bir bağımlılık gerektirmez.
"""
import importlib

# ─────────────────────────────────────────────────────────────────────────────
# Merge pattern dışı artifact'lar (verify.yml download-artifact merge
# pattern'ine GİRMEZ — "kayıt altı" izleyiciler + kendini üreten meta
# artifact'lar). Aday bir job'un çıktısı manifest/repro bundle'a girmesi
# gerekiyorsa bu kümede OLMAMALIDIR; girerse gen_repro_manifest onu sessizce
# düşürür (test_gen_repro_manifest.TestMergePattern konsolida bu sözleşmeyi
# pin'ler).
# ─────────────────────────────────────────────────────────────────────────────
MERGE_PATTERN_EXCLUDED = frozenset({
    "precommit-logs",      # pre-commit ham logları — bundle'da ayrı bölüm
    "refs-trend",          # trend zaman serisi — manifest yerine trend panele
    "override-trend",      # CLI override serisi — aynı şekilde panel-veri
    "precheck-report",     # publish precheck raporu — bundle dışı advisory
    "python3-shell",       # python3-shell adım envanteri — bilgi amaçlı
    "plist-check",         # macOS plist raporu — platform-özel advisory
    "mirror-check",        # TCC mirror senkron raporu — host-özel advisory
    "daemon-http",         # daemon HTTP smoke — host-özel advisory
    "audit-refs-trend",    # refs-trend satır denetimi — advisory meta
    "reproducibility",     # manifest kendisi — merge edilemez (kendi girdisi)
})

# ─────────────────────────────────────────────────────────────────────────────
# PUBLISH_SCENARIO doc "Artifact listesi (N)" bölümünde görünmesi DOĞRU olan
# ama ARTIFACT_JOBS'ta (→ merge pattern) olmaması BİLEREK olan advisory
# artifact'lar. test_doc_artifact_sync fazlalık denetiminde bunları muaf tutar.
# ─────────────────────────────────────────────────────────────────────────────
DOC_ONLY_ADVISORY = frozenset({
    "audit-live-ci",         # advisory meta-denetçi — job output
    "pattern-drift",         # advisory: merge pattern ↔ ARTIFACT_JOBS
    "preview-reload-smoke",  # advisory: preview reload smoke testi
})

# ─────────────────────────────────────────────────────────────────────────────
# check_workflow_artifact_docs muafiyetleri: workflow'da upload-artifact
# adımı olan ama ARTIFACT_JOBS/doc listesine girmeyen özel adlar
# (badge/action-pin/meta denetçi çıktıları).
# ─────────────────────────────────────────────────────────────────────────────
UPLOAD_EXCEPTIONS = frozenset({
    "badge-check",
    "action-pins",
    "audit-live-ci",
    "pattern-drift",
    "preview-reload-smoke",
})

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED vs ADVISORY: required check OLMAYAN job id'leri (banner kapı
# olmasın). status_checks.gate_jobs() bu kümeyi dışlar; required liste bu
# yüzden workflow job'larından TÜRETİLİR. Her üyenin gerekçesi — "PR-only"
# mi "advisory" mi olduğu ve hangi kanıta dayandığı — burada, kümenin
# yanında yaşar: aynı karar iki dosyaya dağılıp ayrışmasın diye
# status_checks.py kopya taşımaz, BURADAN içe aktarır (test_workflow_contract
# drift'i commit anında yakalar). Karar bir POLICY değişikliğidir, test
# düzeltmesi değil (bkz. skills/verify-chain).
# ─────────────────────────────────────────────────────────────────────────────
GATE_EXCLUDE = frozenset({
    "manifest-comment",      # PR-only: yorum düşürme
    "precheck",              # AŞAMA 0 advisory
    "label-gate-p1",         # PR-only: P1 etiket opsiyonel blokaj (required DEĞİL)
    "plist-check",           # macOS-advisory: push'ta çalışmaz
    "mirror-check",          # macOS: sync sonrası K17 fail-closed (advisory)
    "daemon-http",           # advisory: daemon-modu HTTP 200 smoke (advisory)
    "fresh-clone-http",      # advisory: temiz clone + preview HTTP smoke
    "audit-live-ci",         # advisory: doc↔GitHub senkron denetimi
    "audit-refs-trend",      # advisory: refs-trend satırları ↔ kaynak denetimi
    "override-trend",        # advisory: CLI override zaman serisi
    "changelog-drift",       # advisory: gen_changelog --check drift bulguları
    "pattern-drift",         # advisory: merge pattern ↔ ARTIFACT_JOBS drift
    "budget-comment",        # PR-only: bütçe + pre-commit PR yorumu (bütçe kapısı ayrı job)
    "lake-proof",            # ayrı-step K9 lake build (lean-toolchain v4.14.0);
                             #   GitHub required kontrollerinde DEĞİL (advisory) —
                             #   K9, verify job'unun --full içinde de koşar.
})
# Not: "label-gate" (Pre-commit P0 label gate) BİLEREK required check'tir —
# precommit-p0 etiketi varken FAIL verip merge'i bloke eder; bu yüzden
# GATE_EXCLUDE'da DEĞİL. 12'li required liste (2026-08-23): 9 eski gate +
# commit-msg-gate (commit-msg ihlal blokajı — PR-only ama required),
# config-sync (config snapshot ↔ CONFIG_BASENAMES üçlü senkron),
# ci-simulate (yerel CI simülasyonu — full K1-K14 replay).
# 27 job − 14 hariç = 13 required (fresh-clone-http dahil advisory).
#
# 2026-09-04 denetimi (job-id → karar, kanıt verify.yml + GitHub required set):
#   reports          REQUIRED kalır — tüketilen precommit-logs artifact'ı
#                    job içinde indirilir (coe=True), bundle repo-kaynaklı;
#                    kriter: fail-open değil, tüketim bağlı.
#   reproducibility  REQUIRED kalır — K10 bütünlük adımı (--verify-manifest)
#                    set -e altında job'u düşürür (fail-closed uç); manifest
#                    bundle'ı merge-blok kapıdır.
#   refs-trend       REQUIRED kalır — koddan türeyen trend tablosu in-jobs
#                    üretilir (artifact bağımlılığı yok), K6 trend zinciri.
#   lake-proof       ADVISORY kalır (exclude'da) — ayrı-step K9 lake build;
#                    K9, verify --full içinde bağımsız koşar (e30f8ea).

# ─────────────────────────────────────────────────────────────────────────────
# Ağır tek kaynak: lazy re-export (modül import'u yan etkisiz kalır).
#   ARTIFACT_JOBS  ← gen_repro_manifest (artifact → üreten job)
# ─────────────────────────────────────────────────────────────────────────────

_LAZY = {"ARTIFACT_JOBS": "gen_repro_manifest"}


def __getattr__(name):  # PEP 562
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # Paket içi import (python -m unittest _calisma.CIKTI.…) veya düz import
    # (sys.path'e CIKTI eklenmiş) — ikisini de destekle.
    try:
        if __package__:
            mod = importlib.import_module("." + target, __package__)
        else:
            raise ImportError
    except ImportError:
        mod = importlib.import_module(target)
    return getattr(mod, name)


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
