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
başka bir bağımlılık gerektirmez. GATE_EXCLUDE burada TANIMLI (aşağıda):
status_checks.py onu içe aktarır, kopya tutmaz.
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
    "a11y-report-dark",          # a11y tarayici artifact - reproducibility bundle kapsami disi
    "a11y-report-light",         # a11y tarayici artifact - reproducibility bundle kapsami disi
    "a11y-guide-report-dark",    # a11y tarayici artifact - reproducibility bundle kapsami disi
    "a11y-guide-report-light",   # a11y tarayici artifact - reproducibility bundle kapsami disi
    "a11y-landing-report-dark",  # a11y tarayici artifact - reproducibility bundle kapsami disi
    "a11y-landing-report-light", # a11y tarayici artifact - reproducibility bundle kapsami disi
    "lighthouse-dashboard-dark", # a11y tarayici artifact - reproducibility bundle kapsami disi
    "lighthouse-dashboard-light",# a11y tarayici artifact - reproducibility bundle kapsami disi
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
    "a11y-report-dark",
    "a11y-report-light",
    "a11y-guide-report-dark",
    "a11y-guide-report-light",
    "a11y-landing-report-dark",
    "a11y-landing-report-light",
    "lighthouse-dashboard-dark",
    "lighthouse-dashboard-light",
    "audit-live-ci",
    "pattern-drift",
    "preview-reload-smoke",
})

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED vs ADVISORY: required check OLMAYAN job id'leri (banner kapı
# olmasın). status_checks.gate_jobs() bu kümeyi dışlar; required liste bu
# yüzden workflow job'larından TÜRETİLİR.
#
# YÖN 2026-10-28'de netleşti: küme eskiden status_checks.py'de gömülü bir
# set olarak yaşıyordu, bu modül yalnızca PEP 562 lazy re-export ile onu geri
# veriyordu — yani "sözleşme kümelerinin tek kaynağı" iddiası exclude
# kararını barındırmıyordu. Artık tanım BURADA (frozenset: yanlışlıkla
# mutasyona kapalı); status_checks içe aktarır. Kapı: test_workflow_contract
# nesne-özdeşliğini pin'ler — status_checks.py'ye literal bir kopya geri
# gelirse assertIs FAIL eder. Aynı küme rca_report tarafından da okunur.
#
# DİKKAT: yeni bir job eklendiğinde karar bir POLICY değişikliğidir, test
# düzeltmesi değil (bkz. skills/verify-chain): ya required'a alınır ya da
# buraya gerekçesiyle yazılır. Üye eklemek/çıkarmak zorunlu olarak
# branch protection'daki canlı required seti de etkiler.
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
    "preview-reload-smoke",  # advisory: job adı "Preview reload smoke (advisory, macOS)";
                             #   macOS-only tarayıcı smoke'u — canlı protected sette YOK.
    "webkit-smoke",          # advisory: job adı "WebKit smoke (advisory, Safari/safedriver)";
                             #   macOS safedriver smoke'u — canlı protected sette YOK.
    "lake-proof",            # ayrı-step K9 lake build (lean-toolchain v4.14.0);
                             #   GitHub required kontrollerinde DEĞİL (advisory) —
                             #   K9, verify job'unun --full içinde de koşar.
})

# ─────────────────────────────────────────────────────────────────────────────
# Ağır tek kaynak: lazy re-export (modül import'u yan etkisiz kalır).
#   ARTIFACT_JOBS  ← gen_repro_manifest (artifact → üreten job)
#   GATE_EXCLUDE   → BURADA tanımlı (yukarıda); status_checks içe aktarır.
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
