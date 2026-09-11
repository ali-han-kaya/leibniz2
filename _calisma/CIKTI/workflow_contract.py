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

stdlib-only; yan etkisiz. Ağır tek kaynaklara (ARTIFACT_JOBS,
GATE_EXCLUDE) PEP 562 __getattr__ ile lazy erişim sağlar — bu modülü
import etmek PyYAML veya başka bir bağımlılık gerektirmez.
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
# Ağır tek kaynaklar: lazy re-export (modül import'u yan etkisiz kalır).
#   ARTIFACT_JOBS  ← gen_repro_manifest (artifact → üreten job)
#   GATE_EXCLUDE   ← status_checks      (required-olmayan job id'leri)
# ─────────────────────────────────────────────────────────────────────────────

_LAZY = {"ARTIFACT_JOBS": "gen_repro_manifest", "GATE_EXCLUDE": "status_checks"}


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
