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
    "statement-inventory",  # K9+kâğıt statement envanteri + drift raporu
                             #   (lake-proof, verify ile paralel advisory is);
                             #   bundle'a girmesi needs grafigini Lean
                             #   kurulumuna baglar — artifact olarak yayinda,
                             #   manifest hash'ine girmez
})

# ─────────────────────────────────────────────────────────────────────────────
# PUBLISH_SCENARIO doc "Artifact listesi (N)" bölümünde görünmesi DOĞRU olan
# ama ARTIFACT_JOBS'ta (→ merge pattern) olmaması BİLEREK olan advisory
# artifact'lar. test_doc_artifact_sync fazlalık denetiminde bunları muaf tutar.
# ─────────────────────────────────────────────────────────────────────────────
DOC_ONLY_ADVISORY = frozenset({
    "a11y-report-dark",      # dashboard dark tarayıcı artifact'ı — bundle dışı
    "a11y-report-light",     # dashboard light tarayıcı artifact'ı — bundle dışı
    "a11y-guide-report-dark",   # guide dark tarayıcı artifact'ı — bundle dışı
    "a11y-guide-report-light",  # guide light tarayıcı artifact'ı — bundle dışı
    "a11y-landing-report-dark",   # landing dark tarayıcı artifact'ı — bundle dışı
    "a11y-landing-report-light",  # landing light tarayıcı artifact'ı — bundle dışı
    "lighthouse-dashboard-dark",  # dashboard dark Lighthouse artifact'ı — bundle dışı
    "lighthouse-dashboard-light", # dashboard light Lighthouse artifact'ı — bundle dışı
    "capture-gate-dark",     # dashboard yakalanabilirlik (kare/PNG) raporu — dark ayağı
    "webkit-smoke",          # macOS Safari/safedriver smoke raporu — platform-özel
    "audit-live-ci",         # advisory meta-denetçi — job output
    "pattern-drift",         # advisory: merge pattern ↔ ARTIFACT_JOBS
    "shuffle-audit",         # advisory: test sıra bağımlılığı/sızıntı bulguları
                             #   (manifest − shuffle_audit.exclude). Teslim
                             #   bundle'ı değil: kapsam/oynak dosyalar ağaca
                             #   bağlı — manifest hash'ine girmesi K10'u her
                             #   sıra bulgusunda oynatırdı.
    "preview-reload-smoke",  # advisory: preview reload smoke testi
    "video-report",          # LeibnizChain mp4 + olcum satiri (video-render,
                              #   advisory) — bundle disi: uretilen video
                              #   teslim zincirinin parcasi degil
    "pptx-decks",            # native pptx jeneratorlerinin URUNU (pptx-export,
                             #   advisory) — uc deck (.pptx) + suits logu;
                             #   yapisal kanit testte, deck'ler insan icin
                             #   artefakt: manifest hash'ine girmez
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
    "capture-gate-dark",
    "webkit-smoke",
    "audit-live-ci",
    "pattern-drift",
    "shuffle-audit",         # test sıra bağımlılığı denetimi (verify.yml
                             #   shuffle-audit job'u) — DOC_ONLY_ADVISORY ile
                             #   aynı gerekçe (alt küme kuralı)
    "preview-reload-smoke",
    "video-report",          # LeibnizChain mp4 + olcum satiri (video-render) —
                             #   DOC_ONLY_ADVISORY ile ayni kumesel (alt kume
                             #   kurali), ARTIFACT_JOBS'a girmez
    "pptx-decks",            # native pptx deck'leri (pptx-export) —
                             #   DOC_ONLY_ADVISORY ile ayni kumesel
})

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED vs ADVISORY: required check OLMAYAN job id'leri (banner kapı
# olmasın). status_checks.gate_jobs() bu kümeyi dışlar; required liste bu
# yüzden workflow job'larından TÜRETİLİR. Her üyenin gerekçesi — "PR-only"
# mi "advisory" mi olduğu ve hangi kanıta dayandığı — kümenin yanında yaşar.
#
# YÖN 2026-09-27'de ters çevrildi: küme önce status_checks.py'de GÖMÜLÜ bir
# set olarak yaşıyordu, bu modül yalnızca PEP 562 lazy re-export ile onu geri
# veriyordu — yani "tek kaynak" yorumu tek kaynağın kendisini barındırmıyordu.
# Artık tanım burada; status_checks içe aktarıyor ve test_workflow_contract
# nesne-özdeşliğini yakalıyor (kopya → assertIs FAIL).
#
# 2026-10-17 denetimi: dashboard-next yüzeyini koşan GERÇEK job
# `dashboard-smoke`; `dashboard-next` id'si workflow'da hiç yoktu (phantom
# exclude). Aynı denetimde job'ı bulunmayan docx-export / video-render /
# all-hooks-smoke id'leri silindi ve iki macOS-advisory kapı
# (webkit-smoke, preview-reload-smoke) required'dan çıkarıldı.
# Sonuç: 33 job − 18 hariç = 15 required (dashboard-smoke dahil).
# (2026-10-18: `pptx-export` eklendi — advisory, required küme değişmedi.)
# Bayat exclude `advisory_contract`'ı FAIL'e düşürür: job geri eklenirse
# buraya da eklenmelidir, aksi halde sessizce required check olur.
# ─────────────────────────────────────────────────────────────────────────────
GATE_EXCLUDE = frozenset({
    "manifest-comment",      # PR-only: yorum düşürme
    "precheck",              # AŞAMA 0 advisory
    "label-gate-p1",         # PR-only: P1 etiket opsiyonel blokaj (required DEĞİL)
    "plist-check",           # macOS-advisory: push'ta çalışmaz
    "mirror-check",          # macOS: sync sonrası K17 fail-closed (advisory)
    "daemon-http",           # advisory: daemon-modu HTTP 200 smoke
    "fresh-clone-http",      # advisory: temiz clone + preview HTTP smoke
    "audit-live-ci",         # advisory: doc↔GitHub senkron denetimi
    "audit-refs-trend",      # advisory: refs-trend satırları ↔ kaynak denetimi
    "cls-trend",             # advisory: CLS bütçe-ALTI regresyon kapısı.
                             #   Job kırmızı olur (regresyon/ERROR) ama merge'i
                             #   bloke ETMEZ: veri kaynağı GitHub artifact API'si
                             #   — geçici API/hız-sınırı hatası required check
                             #   olsaydı merge'i kilitleyecekti (refs-trend ile
                             #   aynı gerekçe). Mutlak bütçe kapısı zaten
                             #   required `a11y-gate` içinde.
    "override-trend",        # advisory: CLI override zaman serisi
    "changelog-drift",       # advisory: gen_changelog --check drift bulguları
    "pattern-drift",         # advisory: merge pattern ↔ ARTIFACT_JOBS drift
    "shuffle-audit",         # advisory: test sıra bağımlılığı/sızıntı denetimi.
                             #   Dışlama listesi bakımı ve ağaç durumu kapıyı
                             #   kırmızı tutabilir (kalıcı kırmızı dosyalar
                             #   bilinçli dışlıdır); required yapmak merge'i
                             #   dışlama-listesi bakımına bağlardı.
    "budget-comment",        # PR-only: bütçe + pre-commit PR yorumu
    "lake-proof",            # ayrı-step K9 lake build (lean-toolchain v4.14.0);
                             #   GitHub required kontrollerinde DEĞİL (advisory) —
                             #   K9, verify job'unun --full içinde de koşar.
    "webkit-smoke",          # macOS Safari/safedriver smoke — kendi job adı
                             #   "advisory"; required'a alınırsa Linux PR'ları
                             #   yalnız macOS runner'a bağlanır.
    "preview-reload-smoke",  # macOS preview restart smoke — job adı
                             #   "advisory"; dashboard-smoke'un Chromium
                             #   katmanı dashboard-next yüzeyini zaten kapsar.
    "docx-export",           # advisory: docx üretimi + LibreOffice açılabilirlik
                             #   doğrulaması (ürün artifact olarak yayında).
                             #   Required yapmak LibreOffice kurulumunu merge
                             #   yoluna bağlar; kapı kendi job'ında fail-closed.
    "pptx-export",           # advisory: native deck yapı kapısı (node +
                             #   pptxgenjs). Teslim PDF zincirinin parçası
                             #   değil; required yapmak GitHub branch
                             #   protection context'i ister. Kapı yine
                             #   fail-closed koşar (SKIP → KIRMIZI).
})
# Not: "label-gate" (Pre-commit P0 label gate) BİLEREK required check'tir —
# precommit-p0 etiketi varken FAIL verip merge'i bloke eder; bu yüzden
# GATE_EXCLUDE'da DEĞİL.

# ─────────────────────────────────────────────────────────────────────────────
# Ağır tek kaynaklar: lazy re-export (modül import'u yan etkisiz kalır).
#   ARTIFACT_JOBS  ← gen_repro_manifest (artifact → üreten job)
#   GATE_EXCLUDE   → BURADA tanımlı (yukarıda); status_checks içe aktarır.
#                    Workflow'da bulunmayan job id'si burada TUTULAMAZ:
#                    advisory_contract bayat exclude'u FAIL sayar.
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
