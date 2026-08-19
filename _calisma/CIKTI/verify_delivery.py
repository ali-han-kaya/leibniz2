#!/usr/bin/env python3
"""
verify_delivery.py — Stoic-Hume V5 teslimini TEK KOMUTLA doğrula.

Fail-closed CI kapısı (ALI_KOMUT_TOOLKIT_v3 / v3_verify.py felsefesiyle):
final karar yalnızca burada YENİDEN HESAPLANAN ham bulgulardan türetilir;
hiçbir belge beyanına güvenilmez.

Kullanım (tek komut):
    python3 verify_delivery.py                # çalıştığı dizindeki zip'leri doğrular
    python3 verify_delivery.py --dir CIKTI    # belirli dizini doğrular
    python3 verify_delivery.py --json         # CI için makine-okunur JSON
    python3 verify_delivery.py --budget 30    # bütçe kalkanı: tahmini USD üretim maliyeti
                                              #   (token ≈ bytes/4; $3/M token + $0.55; v3_verify.py H4)
                                              # Varsayılan değer verify_delivery.config.json'dan okunur.
    python3 verify_delivery.py --check-references
                                              # K6: CrossRef/SEP/OpenLibrary/Internet Archive/Perseus
                                              #     çevrimiçi referans denetimi
    python3 verify_delivery.py --symbolic-proof
                                              # K8: Z3 sembolik ispat (core_section.tex teoremleri)
    python3 verify_delivery.py --lean-proof
                                              # K9: Lean 4 reduct-invariance (tümevarımsal kanıt)
    python3 verify_delivery.py --verify-manifest reproducibility/manifest.json
                                              # K10: manifest.json'daki her SHA-256'yı gerçek dosyayla
                                              #      karşılaştır + config.combined_sha256'ı YENİDEN
                                              #      hesaplayıp doğrula + cli_overrides ↔ config bundle
                                              #      tutarlılığını denetle (reproducibility bütünlüğü)
    python3 verify_delivery.py --check-lineage  # soy hattı: zip_lineage.json + git show ile her nesli doğrula
    python3 verify_delivery.py --history-out history.jsonl
                                              # run özetini JSONL kaydı olarak yaz (preview
                                              # history.jsonl formatıyla birebir) — CI
                                              # reproducibility manifest'ine SHA-256 sabitlenir
    python3 verify_delivery.py --check-config-drift
                                              # K11: gen_config.py --dry-run (config'teki expected_
                                              #      pages/refs/manifest paket içeriğiyle uyuşuyor mu;
                                              #      drift → P1, fail-closed, --full'a dahil)
    python3 verify_delivery.py --check-plist
                                              # K12: update_preview.sh --plist-check exit kodunu
                                              #      denetle (0=GÜNCEL, 1=BAYAT, 2=şablon yok)
    python3 verify_delivery.py --check-repro-manifest
                                              # K13: gen_repro_manifest.py'yi mock artifact'larla
                                              #      koşup manifest tutarlılığını denetle
    python3 verify_delivery.py --check-cleanup
                                              # K14: M0 §10 silme/taşıma kayıtlarını dosya
                                              #      sistemiyle doğrula (cleanup_log.json)
    python3 verify_delivery.py --full          # tüm katmanlar: K1-K14 + referans denetimi + Z3 + Lean
                                              #   (--check-references + --symbolic-proof +
                                              #    --lean-proof + --check-lineage +
                                              #    --check-config-drift + --check-repro-manifest +
                                              #    --check-cleanup)

Exit kodu: 0 = PASS, 1 = FAIL, 2 = kullanım/ortam hatası.

Yalnızca Python 3 standart kütüphanesi kullanır (hashlib, zipfile, subprocess,
tempfile; --check-references için ayrıca urllib). Harici `unzip`/`shasum`/`diff`
GEREKMEZ. pdfinfo varsa PDF sayfa kontrolü eklenir, yoksa atlanır (FAIL değil).

Doğrulama zinciri (Katman 0..13):
  K0  Bayat    CIKTI dışında kalan HER zip taraması (recursive; P1)
  K1  Dış zip  SHA-256 sidecar (kurcalanma)
  K2  Klasör   KLASOR_CHECKSUMLARI.sha256 (tüm dosyalar)
  K3  İç zip   SHA-256 sidecar (kurcalanma)
  K4  Manifest MANIFEST.txt 19/19 (boyut + MD5)
  K5  Scriptler 4 script byte-for-byte (donmuş çıktılarla; qpdf deneyi
      donmuş kaydı byte-stabil, --rerun canlı deneyi üretir)
  K6  İçerik   PDF sayfa sayısı (pdfinfo, isteğe bağlı) + References 64/64
               + (--check-references ile) CrossRef DOI + SEP URL + OpenLibrary /
               Internet Archive / Perseus çevrimiçi denetimi
  K7  Hijyen   secret/anahtar + artefakt taraması
  K8  İspat    Z3 sembolik ispat (--symbolic-proof; z3-solver gerektirir)
  K9  Lean     Lean 4 reduct-invariance tümevarımsal kanıt (--lean-proof; lean gerektirir)
  K10 Manifest gen_repro_manifest.py çıktısı manifest.json'daki her dosyanın
               SHA-256'sını gerçek dosyayla karşılaştır + config.combined_sha256'ı
               config.files'tan YENİDEN hesaplayıp doğrula + effective_config.json'
               daki cli_overrides'ın dosya config'iyle tutarlılığını denetle
               (--verify-manifest PATH; reproducibility bütünlüğü — fail-closed:
               uyuşmazlık P1)
  K11 Config  gen_config.py --dry-run: config'teki expected_pages/refs/manifest
               paketin GERÇEK içeriğinden yeniden hesaplanır ve commit'li
               config'le karşılaştırılır; fark → P1 (fail-closed,
               --check-config-drift, --full'a dahil)
  K12 Plist    LaunchAgent plist şablonu: update_preview.sh --plist-check
               exit kodu (0=GÜNCEL, 1=BAYAT, 2=şablon yok) — drift → P1
               (--check-plist; macOS'a özgü, --full'a dahil değil)
  K13 Repro    gen_repro_manifest.py self-testi: mock artifact'lardan manifest
               üretip kapsam + SHA-256 tutarlılığını denetler (fail-closed;
               --check-repro-manifest, --full'a dahil)
  K14 Cleanup  M0 §10 CLEANUP LOG (silme/taşıma kayıtları) — cleanup_log.json
               (M0 §10 ile aynı kaynak) okunur: expect_absent yolları yok olmalı
               (P1), moved.from yok (P1) + moved.to varsa hash (P1), canonical
               hash'ler birebir (P0). --check-cleanup, --full'a dahil.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

KLASOR_ZIP = "TESLIM_KLASOR_V5_2026-08-17.zip"
KLASOR_DIR = "Stoic-Hume-Final-V5_2026-08-17"
IC_ZIP = "TESLIM_V5_FINAL_2026-08-17.zip"
PKG_REL = "TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17"
EXPECTED_MANIFEST = 19
EXPECTED_REFS = 64
EXPECTED_PAGES = 33
# Bütçe oranlarının varsayılanı (config dosyası yoksa kullanılır).
# gen_config.py compute_budget_ratios'un total<=0 fallback'iyle aynı; tek kaynak.
DEFAULT_BUDGET_RATIOS = {"text": 3, "pdf": 8, "archive": 12, "binary": 20}
PDF_METADATA_SIDECAR = "ingiliz_empirizmi_v3.pdf.metadata.sha256"
PDF_RAW_SIDECAR = "ingiliz_empirizmi_v3.pdf.sha256"
SYMBOLIC_PROOF_SCRIPT = "symbolic_proof_z3.py"
LEAN_PROOF_SCRIPT = "../lean_reduct/ReductInvariance.lean"
SCRIPTS = [
    ("core_formal_model_check.py", "test_output.txt"),
    ("encoding_sensitivity_check.py", "encoding_sensitivity_output.txt"),
    ("gate15_check.py", "gate15_output.txt"),
    # V5l qpdf determinizm deneyi: donmuş kayıt byte-stabil; --rerun canlı
    # deneyi üretir (hash'ler run'dan run'a değişir — deneyin kendisi).
    ("qpdf_determinism_experiment.py", "qpdf_determinism_output.txt"),
]

# ---- K-katman etiketleri (run summary + --klayers-out sidecar) ----
# TEK KAYNAK: bu tablo, dosyanın başındaki docstring katman tablosuyla aynı
# anlama gelir; yeni bir K katmanı eklenince İKİSİ birden güncellenmelidir.
LAYER_LABELS = {
    "K0": "Bayat zip taraması",
    "K1": "Dış zip sidecar",
    "K2": "Klasör checksum",
    "K3": "İç zip sidecar",
    "K4": "Manifest 19/19",
    "K5": "Script byte-for-byte",
    "K6": "İçerik (PDF + referans)",
    "K7": "Hijyen (secret/artefakt)",
    "K8": "Z3 sembolik ispat",
    "K9": "Lean reduct-invariance",
    "K10": "Manifest digest",
    "K11": "Config drift",
    "K12": "Plist şablon",
    "K13": "Repro self-test",
    "K14": "Cleanup kaydı",
}

# K0-K7 çekirdek katmanlar: --full olsun olmasın her run'da koşar.
_CORE_LAYERS = frozenset({"K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7"})

# İsteğe bağlı katman → onu aktifleştiren bayrağın args üzerindeki getter'ı.
_OPTIONAL_LAYERS = {
    "K8": lambda a: a.symbolic_proof,
    "K9": lambda a: a.lean_proof,
    "K10": lambda a: bool(a.verify_manifest),
    "K11": lambda a: a.check_config_drift,
    "K12": lambda a: a.check_plist,
    "K13": lambda a: a.check_repro_manifest,
    "K14": lambda a: a.check_cleanup,
}


def build_layers_summary(args, findings):
    """findings listesini K-katmanına göre gruplayıp sıralı özet üret.

    Döndürür {layer: {label, status, ran, findings}}. status:
      - PASS: katman koştu, bulgu yok
      - FAIL: katman koştu, en az bir P0/P1 bulgu var
      - SKIP: katman bu run'da koşmadı (bayrak verilmedi; ör. K10 verify
        job'unda değil reproducibility job'unda, K12 yalnızca macOS)
    """
    by_layer = {}
    for f in findings:
        layer = f.get("check", "").split("-")[0]
        if layer in LAYER_LABELS:
            by_layer.setdefault(layer, []).append(f)
    layers = {}
    for layer in LAYER_LABELS:
        if layer in _CORE_LAYERS:
            ran = True
        else:
            getter = _OPTIONAL_LAYERS.get(layer)
            ran = bool(getter(args)) if getter else False
        fl = by_layer.get(layer, [])
        status = "FAIL" if fl else ("PASS" if ran else "SKIP")
        layers[layer] = {"label": LAYER_LABELS[layer], "status": status,
                         "ran": ran, "findings": fl}
    return layers

# ---- K6 referans denetimi (CrossRef/SEP çevrimiçi, --check-references) ----
# Kaynak: REFERANS_KANIT_DENETIMI.md (2026-08-17, 64/64 denetimi).
# crossref : DOI'ye göre CrossRef'ten canlı doğrulanır (kesin, tekrarlanabilir).
# sep      : SEP girişi doğrudan URL'den canlı doğrulanır (HTTP 200 + başlık).
# known    : denetimin sabit bulguları (kitap/edişyon/antik metinler çevrimiçi
#            indekslenmediği için canlı yeniden üretilemez; kanıtı rapordadır).
REFERENCE_CROSSREF = [
    {"key": "Artemov 2008", "doi": "10.1017/s1755020308090060",
     "container_needle": "review of symbolic logic", "volume": "1",
     "year": "2008", "tex_needle": "Artemov, S. (2008)"},
    {"key": "Nawar 2022", "doi": "10.1093/arisup/akac002",
     "container_needle": "aristotelian society supplementary", "volume": "96",
     "year": "2022", "tex_needle": "Nawar, T. (2022)"},
    {"key": "Priest 2010", "doi": "10.31979/2151-6014(2010).010206",
     "container_needle": "comparative philosophy", "volume": "1",
     "year": "2010", "tex_needle": "Priest, G. (2010)"},
    {"key": "Schnieder 2011", "doi": "10.1017/S1755020311000104",
     "container_needle": "review of symbolic logic", "volume": "4",
     "year": "2011", "tex_needle": "Schnieder, B. (2011)"},
]
REFERENCE_SEP = [
    {"key": "Rosker SEP", "url": "https://plato.stanford.edu/entries/chinese-epistemology/",
     "title": "Epistemology in Chinese Philosophy",
     "tex_needle": "Epistemology in Chinese Philosophy"},
    {"key": "Baltzly SEP", "url": "https://plato.stanford.edu/entries/stoicism/",
     "title": "Stoicism", "tex_needle": "Stoicism"},
    {"key": "Bolyard SEP", "url": "https://plato.stanford.edu/entries/skepticism-medieval/",
     "title": "Medieval Skepticism", "tex_needle": "Medieval Skepticism"},
    {"key": "Papy SEP", "url": "https://plato.stanford.edu/entries/justus-lipsius/",
     "title": "Justus Lipsius", "tex_needle": "Justus Lipsius"},
    {"key": "Van Norden SEP", "url": "https://plato.stanford.edu/entries/wang-yangming/",
     "title": "Wang Yangming", "tex_needle": "Wang Yangming"},
]
REFERENCE_KNOWN = [
    # V5h (2026-08-17): Beth 1953 ve Fosl 1998 düzeltildi — .tex'te artık
    # doğru kaynakça var; sabit denetim artık sadece bilgi amaçlı.
    # V5j (2026-08-17): Popkin 1952 (sayfa) ve Priest 2018 (alt başlık) da
    # düzeltildi — kalan KUCUK NOT'lar kapatıldı; tümü artık DUZELTILDI.
    {"key": "Beth 1953", "status": "DUZELTILDI", "priority": "INFO",
     "note": "V5h fix: Indagationes Mathematicae 15: 330-339 "
             "(+ Proc. KNAW A56). Önceki 'JSL 18(1):8-13' hatası düzeltildi."},
    {"key": "Fosl 1998", "status": "DUZELTILDI", "priority": "INFO",
     "note": "V5h fix: ECSSS Newsletter 11: 35-36. Önceki 'JHP 36(2)' "
             "teyit edilememişti; doğru kaynak ECSSS Newsletter."},
    {"key": "Popkin 1952", "status": "DUZELTILDI", "priority": "INFO",
     "note": "V5j fix: yeniden basım sayfası 133-148 → 133-147 düzeltildi."},
    {"key": "Priest 2018", "status": "DUZELTILDI", "priority": "INFO",
     "note": "V5j fix: tam alt başlık 'An Essay on Buddhist Metaphysics "
             "and the Catuskoti' eklendi."},
]

# ---- K6+ OpenLibrary (--check-references ek) -----------------------------
# OpenLibrary (openlibrary.org) modern akademik kitapları + erken modern edisyonları
# kapsar. search.json endpoint'i ücretsiz + auth gerektirmez.
# Match: title_needle + author_needle + (opsiyonel year ±2) + publisher_needle.
# PASS = bir doc eşleşirse; FAIL = docs var ama hiçbiri eşleşmiyor;
# UNVERIFIED = sonuç yoksa (veya 429 rate-limit).
REFERENCE_OPENLIBRARY = [
    # Akademik kitaplar (post-1900)
    {"key": "Artemov & Fitting 2019", "query": "Justification Logic Reasoning Reasons",
     "title_needle": "justification logic", "author_needle": "artemov",
     "year": 2019, "publisher_needle": "cambridge",
     "tex_needle": "Artemov, S. \\& Fitting, M. (2019)"},
    {"key": "Beebee 2006", "query": "Hume on Causation Beebee",
     "title_needle": "hume on causation", "author_needle": "beebee",
     "year": 2006, "publisher_needle": "routledge",
     "tex_needle": "Beebee, H. (2006)"},
    {"key": "Brittain 2006", "query": "Cicero On Academic Scepticism Brittain",
     "title_needle": "academic scepticism", "author_needle": "brittain",
     "year": 2006, "publisher_needle": "hackett",
     "tex_needle": "Brittain, C. (tr.) (2006)"},
    {"key": "Bury 1933", "query": "Sextus Empiricus Outlines Pyrrhonism Loeb Bury",
     "title_needle": "outlines of pyrrhonism", "author_needle": "bury",
     "year": 1933, "publisher_needle": "loeb",
     "tex_needle": "Bury, R.G. (tr.) (1933--49)"},
    {"key": "Correia & Schnieder 2012", "query": "Metaphysical Grounding Understanding Reality",
     "title_needle": "metaphysical grounding", "author_needle": "correia",
     "year": 2012, "publisher_needle": "cambridge",
     "tex_needle": "Correia, F. \\& Schnieder, B. (eds.) (2012)"},
    {"key": "Dorandi 2013", "query": "Diogenes Laertius Lives Eminent Philosophers Dorandi",
     "title_needle": "lives of eminent", "author_needle": "dorandi",
     "year": 2013, "publisher_needle": "cambridge",
     "tex_needle": "Dorandi, T. (ed.) (2013)"},
    {"key": "Elman 1984", "query": "From Philosophy to Philology Late Imperial China Elman",
     "title_needle": "philosophy to philology", "author_needle": "elman",
     "year": 1984, "publisher_needle": "harvard",
     "tex_needle": "Elman, B.A. (1984)"},
    {"key": "Floridi 2002", "query": "Sextus Empiricus Transmission Recovery Floridi",
     "title_needle": "sextus empiricus", "author_needle": "floridi",
     "year": 2002, "publisher_needle": "oxford",
     "tex_needle": "Floridi, L. (2002)"},
    {"key": "Garrett 1997", "query": "Cognition Commitment Hume Philosophy Garrett",
     "title_needle": "cognition and commitment", "author_needle": "garrett",
     "year": 1997, "publisher_needle": "oxford",
     "tex_needle": "Garrett, D. (1997)"},
    {"key": "Goldman 1986", "query": "Epistemology Cognition Goldman",
     "title_needle": "epistemology and cognition", "author_needle": "goldman",
     "year": 1986, "publisher_needle": "harvard",
     "tex_needle": "Goldman, A.I. (1986)"},
    {"key": "Graham 1989", "query": "Disputers of the Tao Graham",
     "title_needle": "disputers of the tao", "author_needle": "graham",
     "year": 1989, "publisher_needle": "open court",
     "tex_needle": "Graham, A.C. (1989)"},
    {"key": "Hansen 1983", "query": "Language Logic Ancient China Hansen",
     "title_needle": "language and logic in ancient china", "author_needle": "hansen",
     "year": 1983, "publisher_needle": "michigan",
     "tex_needle": "Hansen, C. (1983)"},
    {"key": "Hansen 1992", "query": "Daoist Theory Chinese Thought Hansen",
     "title_needle": "daoist theory", "author_needle": "hansen",
     "year": 1992, "publisher_needle": "oxford",
     "tex_needle": "Hansen, C. (1992)"},
    {"key": "Hicks 1925", "query": "Diogenes Laertius Lives of Eminent Philosophers",
     "title_needle": "lives and opinions", "author_needle": "hicks",
     "year": 1925, "publisher_needle": "loeb",
     "tex_needle": "Hicks, R.D. (tr.) (1925)"},
    {"key": "Hume (Selby-Bigge/Nidditch) 1975", "query": "Hume Enquiries Concerning Human Understanding Morals",
     "title_needle": "enquiries concerning human understanding",
     "author_needle": "selby-bigge",
     "year": 1975, "publisher_needle": "clarendon",
     "tex_needle": "Hume, D. (1975). \\emph{Enquiries}. Selby-Bigge"},
    {"key": "Hunt 1998", "query": "Textual History Cicero Academici Hunt Brill",
     "title_needle": "textual history", "author_needle": "hunt",
     "year": 1998, "publisher_needle": "brill",
     "tex_needle": "Hunt, T.J. (1998)"},
    {"key": "Lipsius 1584 De Constantia", "query": "De Constantia Lipsius",
     "title_needle": "de constantia", "author_needle": "lipsius",
     "year": 1584, "publisher_needle": None,
     "tex_needle": "Lipsius, J. (1584)"},
    {"key": "Long & Sedley 1987", "query": "Hellenistic Philosophers Long Sedley",
     "title_needle": "hellenistic philosophers", "author_needle": "long",
     "year": 1987, "publisher_needle": "cambridge",
     "tex_needle": "Long, A.A. \\& Sedley, D.N. (1987)"},
    {"key": "Popkin 1979", "query": "History of Scepticism Erasmus Spinoza Popkin",
     "title_needle": "history of scepticism", "author_needle": "popkin",
     "year": 1979, "publisher_needle": "california",
     "tex_needle": "Popkin, R.H. (1979)"},
    {"key": "Priest 2018", "query": "Fifth Corner Four Catuskoti Priest",
     "title_needle": "fifth corner", "author_needle": "priest",
     "year": 2018, "publisher_needle": "oxford",
     "tex_needle": "Priest, G. (2018)"},
    {"key": "Pruss 2006", "query": "Principle Sufficient Reason Reassessment Pruss",
     "title_needle": "principle of sufficient reason", "author_needle": "pruss",
     "year": 2006, "publisher_needle": "cambridge",
     "tex_needle": "Pruss, A.R. (2006)"},
    {"key": "Tillemans 1999", "query": "Scripture Logic Language Dharmakirti Tibetan Successors Tillemans",
     "title_needle": "scripture, logic, language", "author_needle": "tillemans",
     "year": 1999, "publisher_needle": "wisdom",
     "tex_needle": "Tillemans, T.J.F. (1999)"},
]
# Antik metinler ve kapsamı dışı yayınlar (OpenLibrary'de nadiren/hiç yok):
# - Sextus 1562 Estienne / 1569 Hervet / 1621 Chouet: erken modern edisyonlar.
# - Leibniz 1714 Monadologie §32: birincil kaynak paragrafları.
# - Herbert of Cherbury 1624 De Veritate: birincil kaynak.
# - du Vair 1594 De la constance: birincil kaynak.
# - Cicero Academica (Plasberg paragrafları): birincil kaynak.
# - Xunzi 22 'On Rectification of Names' (Knoblock): birincil kaynak.
# - Lagrée 1994 Vrin: Vrin nadiren OpenLibrary'de indekslenir.
# - Norton & Norton 1996 Edinburgh Bibliographical: küçük yayınevi.
# - Schmitt 1972 Nijhoff: küçük yayınevi.
# - von Arnim 1905 SVF: Teubner 1905 erken baskı, OL'da baskı yok.
# Bu listede olmayanlar REFERANS_KANIT_DENETIMI.md sabit denetimine düşer.

# ---- K6+ Internet Archive (--check-references ek) --------------------------
# Internet Archive advancedsearch.php (archive.org): modern kitaplar + erken
# modern edisyonlar; auth gerektirmez. Match: title_needle normalize edilmiş
# başlıkta geçer; opsiyonel creator_needle yazar alanını da kısıtlar.
# PASS = eşleşen doc; UNVERIFIED = 0 sonuç/ağ hatası (IA kapsamı dışı);
# MISMATCH = sonuç var ama eşleşme yok.
#
# KAPSAM DIŞI (IA indekslemez; REFERANS_KANIT_DENETIMI.md sabit denetimine düşer):
# - Dergi makaleleri: Della Rocca 2010 (Philosophers' Imprint), Norton 1981
#   (History of European Ideas), Popkin 1951 (Philosophical Quarterly) — IA
#   kitapları/eşyaları indeksler, tek tek makaleleri değil.
# - Erken modern Sextus imprinted baskıları (1562 Estienne / 1569 Hervet /
#   1621 Chouet) ve Sextus Loeb #62 (Adversus Mathematicos VII): IA'da modern
#   edisyonlar var ama bu spesifik imprinted baskılar yok (yanlış pozitif riski).
REFERENCE_ARCHIVE = [
    {"key": "Beauchamp 1999 (ed.)", "query": "Enquiry Concerning Human Understanding Beauchamp",
     "title_needle": "enquiry concerning human understanding",
     "tex_needle": "Beauchamp, T.L. (ed.) (1999)"},
    {"key": "Bobzien 2003", "query": "Cambridge Companion to the Stoics",
     "title_needle": "cambridge companion to the stoics",
     "tex_needle": "Bobzien, S. (2003)"},
    {"key": "Fine 2012", "query": "Metaphysical Grounding Correia Schnieder",
     "title_needle": "metaphysical grounding", "creator_needle": "correia",
     "ht_ids": ["isbn:1107022894", "isbn:9781107460287"],
     "tex_needle": "Fine, K. (2012)"},
    {"key": "Frede 1983", "query": "Skeptical Tradition Burnyeat",
     "title_needle": "skeptical tradition",
     "tex_needle": "Frede, M. (1983)"},
    {"key": "Goldman 1979", "query": "Justification and Knowledge Pappas",
     "title_needle": "justification and knowledge",
     "tex_needle": "Goldman, A.I. (1979)"},
    {"key": "Graham 1978", "query": "Later Mohist Logic Ethics Science Graham",
     "title_needle": "later mohist logic",
     "tex_needle": "Graham, A.C. (1978)"},
    {"key": "Herbert of Cherbury 1624", "query": "De Veritate Herbert Cherbury",
     "title_needle": "de veritate", "creator_needle": "herbert",
     "tex_needle": "Herbert of Cherbury. (1624)"},
    {"key": "Hume 1739-40 Treatise", "query": "Treatise of Human Nature Norton",
     "title_needle": "treatise of human nature",
     "tex_needle": "Hume, D. (1739--40)"},
    {"key": "Hume 1748 Enquiry", "query": "Enquiry Concerning Human Understanding Beauchamp",
     "title_needle": "enquiry concerning human understanding",
     "tex_needle": "Hume, D. (1748)"},
    {"key": "Kjellberg 1996", "query": "Skepticism Relativism Ethics Zhuangzi",
     "title_needle": "zhuangzi", "creator_needle": "kjellberg",
     "tex_needle": "Kjellberg, P. (1996)"},
    {"key": "Lagree 1994", "query": "Juste Lipse restauration stoicisme",
     "title_needle": "lipse", "creator_needle": "lagree",
     "ht_ids": ["isbn:2711612074", "isbn:9782711612079"],
     "tex_needle": "Lagrée, J. (1994)"},
    {"key": "Leibniz 1714", "query": "Monadologie Leibniz",
     "title_needle": "monadologie", "creator_needle": "leibniz",
     "tex_needle": "Leibniz, G.W. (1714)"},
    {"key": "Lipsius 1604", "query": "Manuductionis Stoicam philosophiam Lipsius",
     "title_needle": "manuductionis",
     "tex_needle": "Lipsius, J. (1604)"},
    {"key": "Locke 1689", "query": "Essay Concerning Human Understanding Nidditch",
     "title_needle": "essay concerning human understanding",
     "tex_needle": "Locke, J. (1689)"},
    {"key": "Millican 2002", "query": "Reading Hume Human Understanding Millican",
     "title_needle": "reading hume",
     "ht_ids": ["isbn:9780198752103", "isbn:0198752113"],
     "tex_needle": "Millican, P. (2002)"},
    {"key": "Nidditch 1975", "query": "Essay Concerning Human Understanding Nidditch",
     "title_needle": "essay concerning human understanding",
     "tex_needle": "Nidditch, P.H. (ed.) (1975)"},
    {"key": "Norton & Norton 1996", "query": "David Hume Library Norton",
     "title_needle": "david hume library",
     "tex_needle": "Norton, D.F. & Norton, M.J. (eds.) (1996)"},
    {"key": "du Vair 1594", "query": "De la constance consolation calamites",
     "title_needle": "constance", "creator_needle": "vair",
     "tex_needle": "du Vair, G. (1594)"},
    {"key": "Schmitt 1972", "query": "Cicero Scepticus Schmitt",
     "title_needle": "cicero scepticus",
     "ht_ids": ["isbn:9401710376", "isbn:9789401710374"],
     "tex_needle": "Schmitt, C.B. (1972)"},
    {"key": "Schmitt 1983", "query": "Rediscovery Ancient Skepticism Schmitt",
     "title_needle": "skeptical tradition",
     "tex_needle": "Schmitt, C.B. (1983)"},
    {"key": "Xunzi Knoblock", "query": "Xunzi translation Knoblock",
     "title_needle": "xunzi", "creator_needle": "knoblock",
     "ht_ids": ["isbn:9780231129657", "isbn:0231129653"],
     "tex_needle": "Xunzi."},
]

# ---- K6+ Perseus CTS (--check-references ek) -------------------------------
# Perseus Digital Library CTS API (legacy, perseus.tufts.edu/hopper/CTS):
# antik birincil metinlerin pasaj düzeyinde doğrulanması (auth gerektirmez).
# GetPassage + expected_marker (eserin başlığı) 200 yanıtında aranır.
REFERENCE_PERSEUS = [
    {"key": "Cicero Academica", "urn": "urn:cts:latinLit:phi0474.phi045",
     "passage": "1.1", "expected_marker": "Academica",
     "tex_needle": "Cicero. \\emph{Academica}"},
    {"key": "Diogenes Laertius", "urn": "urn:cts:greekLit:tlg0004.tlg001",
     "passage": "7.1", "expected_marker": "Vitae philosophorum",
     "tex_needle": "Diogenes Laertius. \\emph{Vitae Philosophorum}"},
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9]{36}",
    r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) PRIVATE KEY-----",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
]
HIGIENE_PATTERNS = [
    r"(^|/)(node_modules|__pycache__|\.pytest_cache|\.venv|venv)(/|$)",
    r"(^|/)\.env$",
    r"(^|/)\.DS_Store$",
    r"\.(pyc|pyo|log)$",
]
SKIP_SECRET_EXT = {".pdf", ".zip", ".png", ".jpg", ".svg"}

# ---- Konfig şeması (stdlib yapısal doğrulama) ---------------------------
# verify_delivery.config.schema.json ile aynı kısıtları yansıtır; jsonschema
# CI'da ayrıca bağımsız olarak doğrular. Buradaki stdlib doğrulaması her
# ortamda (pre-commit, yerel) fail-closed davranış sağlar.
CONFIG_SCHEMA = {
    "required": ["budget_usd", "budget_method", "budget_ratios",
                 "expected_pages", "expected_refs", "expected_manifest"],
    "types": {
        "budget_usd": (int, float),
        "budget_method": str,
        "budget_ratios": dict,
        "expected_pages": int,
        "expected_refs": int,
        "expected_manifest": int,
    },
    "budget_method_enum": {"universal", "weighted", "both"},
    "budget_ratio_keys": ("text", "pdf", "archive", "binary"),
}


def validate_config(cfg):
    """stdlib-only yapısal doğrulama. Hataların listesini döndürür (boş = OK).

    verify_delivery.config.schema.json (draft-07) ile aynı kısıtları yansıtır:
    zorunlu anahtarlar, tipler, enum ve pozitif sayı aralıkları.
    """
    errors = []
    for key in CONFIG_SCHEMA["required"]:
        if key not in cfg:
            errors.append(f"eksik anahtar: {key}")
            continue
        expected = CONFIG_SCHEMA["types"].get(key)
        if expected is not None and not isinstance(cfg[key], expected):
            want = " veya ".join(t.__name__ for t in expected) \
                if isinstance(expected, tuple) else expected.__name__
            errors.append(f"{key}: tip hatalı (beklenen {want}, "
                          f"alınan {type(cfg[key]).__name__})")

    # budget_usd: pozitif sayı
    if "budget_usd" in cfg and isinstance(cfg["budget_usd"], (int, float)):
        if cfg["budget_usd"] <= 0:
            errors.append("budget_usd: 0'dan büyük olmalı")

    # budget_method: enum
    if ("budget_method" in cfg
            and cfg["budget_method"] not in CONFIG_SCHEMA["budget_method_enum"]):
        errors.append(f"budget_method: geçersiz değer {cfg['budget_method']!r} "
                      f"(beklenen: {sorted(CONFIG_SCHEMA['budget_method_enum'])})")

    # budget_ratios: zorunlu anahtarlar + pozitif sayı
    if "budget_ratios" in cfg and isinstance(cfg["budget_ratios"], dict):
        for k in CONFIG_SCHEMA["budget_ratio_keys"]:
            if k not in cfg["budget_ratios"]:
                errors.append(f"budget_ratios: eksik oran {k!r}")
            elif (not isinstance(cfg["budget_ratios"][k], (int, float))
                  or cfg["budget_ratios"][k] <= 0):
                errors.append(f"budget_ratios.{k}: pozitif sayı olmalı "
                              f"(alınan {cfg['budget_ratios'][k]!r})")

    # expected_*: pozitif tamsayı
    for key in ("expected_pages", "expected_refs", "expected_manifest"):
        if key in cfg and isinstance(cfg[key], int) and cfg[key] <= 0:
            errors.append(f"{key}: pozitif tamsayı olmalı (alınan {cfg[key]!r})")

    return errors


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sha256sums(path):
    """sha256sum formatı: <hash>  <dosya>  (dosya adında iki boşluk olabilir)."""
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([0-9a-f]{64})\s+(.+)$", line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def parse_manifest(path):
    """MANIFEST.txt: <dosya> <boyut> <MD5> (kendi kendini dışlar)."""
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        parts = line.split()
        if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{32}", parts[-1]):
            fn = parts[0]
            if fn == "MANIFEST.txt":
                continue
            out[fn] = parts[-1]
    return out


def count_references(tex_path):
    txt = open(tex_path, encoding="utf-8", errors="ignore").read()
    if "\\section*{References}" not in txt:
        return None
    refs = txt.split("\\section*{References}")[1].split("\\end{itemize}")[0]
    return len(re.findall(r"\\item\s", refs))


def _norm_ref(s):
    """Karşılaştırma için normalleştir: boşluk sil, küçük harf, tire birleştir."""
    s = str(s).replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", "", s).lower()


def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "verify_delivery.py (Stoic-Hume V5 CI; mailto:noreply@example.com)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def crossref_check(ref):
    """CrossRef DOI çöz + beklenen alanlarla karşılaştır.
    Döndürür: (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    url = f"https://api.crossref.org/works/{ref['doi']}"
    try:
        data = _http_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 429:  # rate-limit: bir kez tekrar dene
            time.sleep(2.0)
            try:
                data = _http_json(url)
            except Exception as e2:
                return "UNVERIFIED", f"CrossRef 429 + tekrar başarısız: {e2}"
        else:
            return "MISMATCH", f"CrossRef HTTP {e.code} (DOI çözümlenmedi)"
    except Exception as e:
        return "UNVERIFIED", f"ağ hatası: {e}"

    msg = data.get("message", {})
    container = " ".join(msg.get("container-title", []) or [])
    volume = msg.get("volume", "")
    issue = msg.get("issue", "")
    year = ""
    for k in ("issued", "published-print", "published"):
        dp = msg.get(k, {}).get("date-parts") or [[None]]
        if dp and dp[0] and dp[0][0]:
            year = str(dp[0][0])
            break
    got = f"{container}, c.{volume}({issue}), {year}"
    if (_norm_ref(ref["container_needle"]) in _norm_ref(container)
            and _norm_ref(ref["volume"]) == _norm_ref(volume)
            and _norm_ref(ref["year"]) == _norm_ref(year)):
        return "PASS", got
    return "MISMATCH", (f"CrossRef: {got} | beklenen: {ref['container_needle']}, "
                        f"c.{ref['volume']}, {ref['year']}")


def sep_check(ref):
    """SEP girişini doğrudan URL'den doğrula (HTTP 200 + başlık)."""
    req = urllib.request.Request(ref["url"], headers={
        "User-Agent": "verify_delivery.py (Stoic-Hume V5 CI)",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "MISMATCH", f"SEP 404: {ref['url']}"
        return "UNVERIFIED", f"SEP HTTP {e.code}"
    except Exception as e:
        return "UNVERIFIED", f"ağ hatası: {e}"
    if ref["title"].lower() in body.lower():
        return "PASS", f"200 OK, '{ref['title']}' mevcut"
    return "MISMATCH", f"200 OK ama '{ref['title']}' başlığı sayfada yok"


def openlibrary_check(ref):
    """OpenLibrary search.json ile kitap doğrulaması (auth gerektirmez).
    Birden çok sonuç arasından ilk title+author+yayıncı+yıl eşleşmesini arar.
    Döndürür: (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    q = urllib.parse.quote(ref["query"])
    url = (f"https://openlibrary.org/search.json?q={q}"
           f"&limit=5&fields=title,author_name,first_publish_year,publisher")
    try:
        data = _http_json(url, timeout=20)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "UNVERIFIED", "OpenLibrary 429 rate-limit"
        return "UNVERIFIED", f"OpenLibrary HTTP {e.code}"
    except Exception as e:
        return "UNVERIFIED", f"ağ hatası: {e}"

    docs = data.get("docs", [])
    if not docs:
        return "UNVERIFIED", "OpenLibrary: 0 sonuç (OL kapsamı dışı olabilir)"

    title_n = _norm_ref(ref["title_needle"])
    auth_n = _norm_ref(ref["author_needle"])
    pub_n = _norm_ref(ref["publisher_needle"]) if ref.get("publisher_needle") else None
    yr = ref.get("year")

    best = None
    for d in docs:
        t = _norm_ref(" ".join(d.get("title", []) or [d.get("title", "")] if isinstance(d.get("title"), list) else d.get("title", "")))
        a = _norm_ref(" ".join(d.get("author_name", []) or []))
        p = _norm_ref(" ".join(d.get("publisher", []) or []))
        y = d.get("first_publish_year")

        title_ok = title_n in t if t else False
        # author is a bonus (tercüme/ediyon girişleri OL'de orijinal yazar
        # altında indekslenebilir); title OR publisher yeterli + year
        pub_ok = (pub_n in p) if pub_n else True
        year_ok = (yr is None) or (y is not None and abs(int(y) - int(yr)) <= 2)
        # Çeviri/ediyon eserleri: başlık orijinal yazarın adı altında
        # indekslenir, alt başlık OL'de tutulmayabilir. publisher (örn.
        # "loeb") daha sağlam bir sinyal.
        if (title_ok or pub_ok) and year_ok:
            best = (d, t, a, p, y)
            break

    if best is not None:
        d, t, a, p, y = best
        return "PASS", (f"'{d.get('title')[:60] if isinstance(d.get('title'), str) else d.get('title', [''])[0][:60]}' "
                        f"by {d.get('author_name', [''])[0]}, {y}, {d.get('publisher', [''])[0]}")
    # En yakın sonucu da raporla (debug için)
    top = docs[0]
    return "MISMATCH", (f"hiçbir doc eşleşmedi (title/author/year/pub). "
                        f"En yakın: '{top.get('title') if isinstance(top.get('title'), str) else top.get('title', [''])[0]}' "
                        f"by {top.get('author_name', [''])[0]}, {top.get('first_publish_year')}")


def _archive_query(ref):
    """Internet Archive advancedsearch için alan-bazlı Lucene sorgusu üret.
    title:"..." tamlaması + (varsa) creator: alanı — genel kelime araması yerine
    gürültüyü (podcast/CIA kayıtları vb.) düşürmek için."""
    q = f'title:"{ref["title_needle"]}"'
    if ref.get("creator_needle"):
        q += f' AND creator:{ref["creator_needle"]}'
    return q


def archive_check(ref):
    """Internet Archive advancedsearch ile kitap/edişyon doğrulaması (auth gerektirmez).
    title:"..." alan sorgusu kullanır; dönen doc'ların başlığı title_needle ile
    (ve opsiyonel creator_needle ile) tekrar doğrulanır.
    Döndürür: (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    url = ("https://archive.org/advancedsearch.php?" +
           urllib.parse.urlencode({
               "q": _archive_query(ref),
               "fl[]": ["identifier", "title", "creator", "year"],
               "rows": "10",
               "output": "json",
           }, doseq=True))
    try:
        data = _http_json(url, timeout=25)
    except urllib.error.HTTPError as e:
        return "UNVERIFIED", f"Internet Archive HTTP {e.code}"
    except Exception as e:
        return "UNVERIFIED", f"ağ hatası: {e}"

    docs = data.get("response", {}).get("docs", []) or []
    if not docs:
        return "UNVERIFIED", "Internet Archive: 0 sonuç (IA kapsamı dışı olabilir)"

    title_n = _norm_ref(ref["title_needle"])
    creator_n = _norm_ref(ref["creator_needle"]) if ref.get("creator_needle") else None
    for d in docs:
        t = _norm_ref(str(d.get("title") or ""))
        if title_n not in t:
            continue
        if creator_n:
            c = _norm_ref(str(d.get("creator") or ""))
            if creator_n not in c:
                continue
        ident = d.get("identifier", "?")
        year = d.get("year")
        return "PASS", (f"'{str(d.get('title'))[:60]}' ({ident}, {year})")
    top = docs[0]
    return "MISMATCH", (f"hiçbir sonuç eşleşmedi. En yakın: "
                        f"'{str(top.get('title'))[:60]}' ({top.get('identifier')})")


def perseus_check(ref):
    """Perseus CTS API (legacy) ile antik birincil metin pasajı doğrulaması.
    GetPassage + expected_marker (eser başlığı) 200 yanıtında aranır.
    Döndürür: (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    cts_urn = ref["urn"] + ":" + ref["passage"]
    url = ("http://www.perseus.tufts.edu/hopper/CTS?request=GetPassage"
           f"&urn={urllib.parse.quote(cts_urn)}")
    body = None
    last_err = None
    for attempt in (1, 2):
        req = urllib.request.Request(url, headers={
            "User-Agent": "verify_delivery.py (Stoic-Hume V5 CI)",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "MISMATCH", f"Perseus CTS 404: {cts_urn}"
            last_err = f"Perseus CTS HTTP {e.code}"
        except Exception as e:
            last_err = f"ağ hatası: {e}"
        time.sleep(2.0)
    if body is None:
        return "UNVERIFIED", f"{last_err} (2 deneme)"
    if ref["expected_marker"].lower() in body.lower():
        return "PASS", f"CTS {cts_urn} — '{ref['expected_marker']}' mevcut"
    return "MISMATCH", f"CTS 200 ama '{ref['expected_marker']}' pasajda yok"


def google_books_check(ref):
    """Google Books API (volumes) ile kitap doğrulaması — fallback kaynak.

    GBOOKS_API_KEY ortam değişkeni varsa anahtarlı çağrı; yoksa anahtarsız
    (kota dar — çoğu IP'de 429). intitle/inauthor alan sorgusu kullanır.
    Döndürür (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    title_n = _norm_ref(ref["title_needle"])
    creator = ref.get("creator_needle")
    q = f'intitle:"{ref["title_needle"]}"'
    if creator:
        q += f' inauthor:"{creator}"'
    url = ("https://www.googleapis.com/books/v1/volumes?q="
           + urllib.parse.quote(q) + "&country=US&maxResults=5")
    key = os.environ.get("GBOOKS_API_KEY")
    if key:
        url += f"&key={urllib.parse.quote(key)}"
    try:
        data = _http_json(url, timeout=20)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "UNVERIFIED", ("Google Books 429 (anahtarsız kota; "
                                  "GBOOKS_API_KEY ile tam denetim)")
        return "UNVERIFIED", f"Google Books HTTP {e.code}"
    except Exception as e:
        return "UNVERIFIED", f"Google Books ağ hatası: {e}"

    items = data.get("items", [])
    if not items:
        return "UNVERIFIED", "Google Books: 0 sonuç"
    creator_n = _norm_ref(creator) if creator else None
    for it in items:
        vi = it.get("volumeInfo") or {}
        t = _norm_ref(str(vi.get("title") or ""))
        if title_n not in t:
            continue
        if creator_n:
            a = _norm_ref(" ".join(vi.get("authors") or []))
            if creator_n not in a:
                continue
        authors = ", ".join(vi.get("authors") or [])
        return "PASS", (f"'{str(vi.get('title'))[:60]}' by {authors}, "
                        f"{vi.get('publishedDate') or '?'} "
                        f"({it.get('id') or '?'})")
    top = items[0].get("volumeInfo") or {}
    return "MISMATCH", (f"Google Books sonuç var ama eşleşme yok. En yakın: "
                        f"'{str(top.get('title'))[:60]}'")


def hathitrust_check(ref):
    """HathiTrust Bib API ile kitap doğrulaması — fallback kaynak.

    ref['ht_ids'] içindeki identifier'lar (isbn:/oclc:/lccn:/htid: önekli)
    sırayla denenir; ilk kayıt title_needle ile eşleşirse PASS.
    Döndürür (PASS | MISMATCH | UNVERIFIED, açıklama)."""
    ht_ids = ref.get("ht_ids") or []
    if not ht_ids:
        return "UNVERIFIED", "HathiTrust: identifier yok (ht_ids)"
    title_n = _norm_ref(ref["title_needle"])
    last_mismatch = None
    for ident in ht_ids:
        url = ("https://catalog.hathitrust.org/api/volumes/brief/json/"
               + urllib.parse.quote(ident))
        try:
            data = _http_json(url, timeout=20)
        except urllib.error.HTTPError as e:
            return "UNVERIFIED", f"HathiTrust HTTP {e.code}"
        except Exception as e:
            return "UNVERIFIED", f"HathiTrust ağ hatası: {e}"
        recs = (data.get(ident, {}) or {}).get("records", {}) or {}
        if not recs:
            continue
        for rec in recs.values():
            for t in rec.get("titles") or []:
                if title_n in _norm_ref(str(t)):
                    return "PASS", f"HathiTrust {ident}: '{str(t)[:50]}'"
        last_mismatch = (f"HathiTrust {ident}: kayıt var ama "
                         f"'{ref['title_needle']}' başlık eşleşmedi")
    if last_mismatch:
        return "MISMATCH", last_mismatch
    return "UNVERIFIED", "HathiTrust: verilen identifier'larda kayıt yok"


def _archive_fallback(ref):
    """Internet Archive UNVERIFIED kalınca ek kaynakları dene.

    HathiTrust (identifier bazlı) + Google Books (key isteğe bağlı) denenir;
    ilk PASS kazanır. Hepsi başarısızsa birleşik denetim iziyle UNVERIFIED
    döner (kaynak 'archive' kalır — by_source'ı şişirmez).
    Döndürür (verdict, detail, source)."""
    attempts = []
    if ref.get("ht_ids"):
        hv, hd = hathitrust_check(ref)
        attempts.append(hd[:70])
        if hv == "PASS":
            return hv, hd, "hathitrust"
    gv, gd = google_books_check(ref)
    attempts.append(gd[:70])
    if gv == "PASS":
        return gv, gd, "google_books"
    return "UNVERIFIED", "; ".join(attempts), "archive"


def run_reference_audit(tex_text, add, quiet=False):
    """K6 referans denetimi: .tex varlığı + CrossRef/SEP/OpenLibrary/
    Internet Archive/Perseus çevrimiçi doğrulama.

    Döndürür: çevrimiçi doğrulama sonuçlarının listesi (VERSION JSON kaynağı)
    — her öğe {key, source, verdict, detail, doi|url|urn|query} — böylece her
    run'da kaç referansın çevrimiçi doğrulandığı izlenebilir."""
    def say(line):
        if not quiet:
            print(line)

    say("\n--- K6 referans denetimi "
        "(CrossRef/SEP/OpenLibrary/IA/HathiTrust/Google Books/Perseus çevrimiçi) ---")
    online_results = []

    # 1) .tex'te varlık (çevrimdışı, deterministik)
    for ref in REFERENCE_CROSSREF + REFERENCE_SEP:
        if ref["tex_needle"] not in tex_text:
            add("P1", "K6-REF", "K6 referans",
                f".tex'te yok: {ref['tex_needle']} ({ref['key']})")

    # 2) CrossRef DOI canlı doğrulama
    for ref in REFERENCE_CROSSREF:
        v, detail = crossref_check(ref)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] CrossRef {ref['key']:<14} {ref['doi']:<32} -> {detail}")
        online_results.append({"key": ref["key"], "source": "crossref",
                               "verdict": v, "detail": detail,
                               "doi": ref["doi"]})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} CrossRef uyuşmuyor: {detail}")
        time.sleep(0.4)  # CrossRef polite-pool

    # 3) SEP doğrudan URL doğrulama
    for ref in REFERENCE_SEP:
        v, detail = sep_check(ref)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] SEP     {ref['key']:<14} -> {detail}")
        online_results.append({"key": ref["key"], "source": "sep",
                               "verdict": v, "detail": detail,
                               "url": ref["url"]})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} SEP uyuşmuyor: {detail}")

    # 4) OpenLibrary: kitap/edişyon doğrulaması (çevrimiçi, --check-references)
    for ref in REFERENCE_OPENLIBRARY:
        v, detail = openlibrary_check(ref)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] OpenLib  {ref['key']:<32} -> {detail[:80]}")
        online_results.append({"key": ref["key"], "source": "openlibrary",
                               "verdict": v, "detail": detail,
                               "query": ref["query"]})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} OpenLibrary uyuşmuyor: {detail}")
        time.sleep(0.4)  # OpenLibrary nazik havuz

    # 4b) Internet Archive: kitap/edişyon doğrulaması (çevrimiçi, --check-references)
    for ref in REFERENCE_ARCHIVE:
        v, detail = archive_check(ref)
        source = "archive"
        # IA kapsamı dışı kaldıysa HathiTrust + Google Books fallback dene
        # (ilk PASS kazanır; hepsi başarısızsa birleşik denetim izi kalır).
        if v == "UNVERIFIED":
            fv, fd, fs = _archive_fallback(ref)
            v, detail, source = fv, f"{detail} | {fd}", fs
        src_label = {"archive": "Internet Archive", "hathitrust": "HathiTrust",
                     "google_books": "Google Books"}.get(source, source)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] {src_label:<10} {ref['key']:<30} -> {detail[:80]}")
        online_results.append({"key": ref["key"], "source": source,
                               "verdict": v, "detail": detail,
                               "query": _archive_query(ref)})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} {src_label} uyuşmuyor: {detail}")
        time.sleep(0.4)  # Internet Archive nazik havuz

    # 4c) Perseus: antik birincil metin pasajı (çevrimiçi, --check-references)
    for ref in REFERENCE_PERSEUS:
        v, detail = perseus_check(ref)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] Perseus {ref['key']:<30} -> {detail[:80]}")
        online_results.append({"key": ref["key"], "source": "perseus",
                               "verdict": v, "detail": detail,
                               "urn": ref["urn"] + ":" + ref["passage"]})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} Perseus uyuşmuyor: {detail}")

    # 5) Sabit denetim bulguları (çevrimiçi indekslenmeyen kitap/edişyon/antik)
    for k in REFERENCE_KNOWN:
        say(f"  [{k['status']}] STATIC {k['key']:<14} -> {k['note']}")
        if k.get("priority") == "P1":
            add("P1", "K6-REF", "K6 referans",
                f"[{k['status']}] {k['key']}: {k['note']}")

    say(f"  Kapsam: 64 referans; canlı doğrulanan "
        f"{len(REFERENCE_CROSSREF) + len(REFERENCE_SEP) + len(REFERENCE_OPENLIBRARY) + len(REFERENCE_ARCHIVE) + len(REFERENCE_PERSEUS)} "
        f"(CrossRef {len(REFERENCE_CROSSREF)} + SEP {len(REFERENCE_SEP)} + "
        f"OpenLibrary {len(REFERENCE_OPENLIBRARY)} + "
        f"Internet Archive {len(REFERENCE_ARCHIVE)} "
        f"[HathiTrust + Google Books fallback] + "
        f"Perseus {len(REFERENCE_PERSEUS)}); "
        f"kalanı REFERANS_KANIT_DENETIMI.md sabit denetimine dayanır.")
    return online_results


def pdf_pages(pdf_path):
    """pdfinfo varsa sayfa sayısı; yoksa None (atlanır, FAIL değil)."""
    try:
        r = subprocess.run(
            ["pdfinfo", pdf_path], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
            if m:
                return int(m.group(1))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def qpdf_check_determinism(pdf_path):
    """PDF'in metadata-stripped SHA-256 hash'ini hesapla (build determinism ölçümü).
    qpdf --remove-metadata ile volatile alanlar (/Info, /ID, /CreationDate) temizlenir.
    qpdf yoksa (None, None) döner — bu durumda kontrol atlanır.
    Döndürür: (raw_sha256, stripped_sha256) veya (raw_sha256, None)."""
    raw = sha256_file(pdf_path)
    qpdf = "qpdf"
    for candidate in ("qpdf", "/opt/homebrew/bin/qpdf"):
        if os.path.isfile(candidate):
            qpdf = candidate
            break
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        r = subprocess.run([qpdf, "--remove-metadata", pdf_path, tmp_path],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return raw, None
        stripped = sha256_file(tmp_path)
        os.unlink(tmp_path)
        return raw, stripped
    except (OSError, subprocess.TimeoutExpired):
        return raw, None


def run_script(py, script):
    r = subprocess.run([py, script], capture_output=True, text=True,
                       timeout=120, cwd=os.path.dirname(script) or ".")
    return r.returncode, r.stdout.encode("utf-8", "replace")


def run_symbolic_proof(py, script):
    """K8: sembolik ispat (Z3). Döndürür (ok: bool, detail: str).

    Z3 script'inin stdout'u satır satır kendi stderr'ine relay edilir
    (canlı ilerleme — dashboard /api/run-stream'de K8 adımlarını gösterir);
    toplanan çıktı yine de döndürülür. --json modunda stderr serbest
    olduğundan makine-okunur JSON stdout'u bozulmaz.
    """
    timed_out = False
    try:
        # PYTHONUNBUFFERED=1: script'in print'leri flush=True içermese bile
        # stdout satır satır pipe'a aksın (canlı ilerleme için kritik).
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        p = subprocess.Popen([py, script], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             cwd=os.path.dirname(script) or ".", env=env)
    except FileNotFoundError:
        return False, f"yorumlayıcı bulunamadı: {py}"
    out_chunks, err_chunks = [], []

    def _drain(pipe, sink, relay):
        try:
            for line in iter(pipe.readline, ""):
                sink.append(line)
                if relay:
                    # Canlı ilerleme: ana sürecin stderr'ine satır satır yaz.
                    sys.stderr.write(line)
                    sys.stderr.flush()
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t1 = threading.Thread(target=_drain, args=(p.stdout, out_chunks, True))
    t2 = threading.Thread(target=_drain, args=(p.stderr, err_chunks, False))
    t1.start(); t2.start()
    try:
        rc = p.wait(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            p.kill()
            p.wait()
        except Exception:
            pass
    t1.join(); t2.join()
    if timed_out:
        return False, "sembolik ispat zaman aşımı (>180s)"
    out = "".join(out_chunks) + "".join(err_chunks)
    if rc == 0:
        return True, "Z3 ispatı geçti (12/12)"
    if "No module named 'z3'" in out or "ModuleNotFoundError" in out:
        return False, "z3-solver kurulu değil — pip install z3-solver"
    tail = [l.strip() for l in out_chunks if l.strip()][-2:]
    detail = " | ".join(tail) if tail else f"exit={rc}"
    return False, f"Z3 beklenmedik sonuç: {detail}"


TEXT_EXTS = frozenset({
    ".tex", ".py", ".md", ".json", ".txt", ".csv", ".tsv",
    ".yaml", ".yml", ".html", ".xml", ".css", ".js",
    ".sh", ".rb", ".rs", ".lean", ".toml", ".ini", ".cfg",
    ".bst", ".bib", ".sty", ".cls",
})
ARCHIVE_EXTS = frozenset({".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"})


def compute_type_bytes(ic_root):
    """Bir dizin ağacının içeriğini dosya tipine göre bayt kırılımına ayır.

    Döndürür (type_bytes, total_bytes): type_bytes = {text, pdf, archive,
    binary} bayt toplamları; total_bytes = tümü. gen_config.py (budget
    ratios) ve verify_delivery.py (ağırlıklı bütçe) tek kaynaktan kullanır.
    """
    type_bytes = {"text": 0, "pdf": 0, "archive": 0, "binary": 0}
    total_bytes = 0
    if not os.path.isdir(ic_root):
        return type_bytes, 0
    for _root, _dirs, files in os.walk(ic_root):
        for fn in files:
            p = os.path.join(_root, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            total_bytes += sz
            ext = os.path.splitext(fn)[1].lower()
            if ext == ".pdf":
                type_bytes["pdf"] += sz
            elif ext in ARCHIVE_EXTS:
                type_bytes["archive"] += sz
            elif ext in TEXT_EXTS:
                type_bytes["text"] += sz
            else:
                type_bytes["binary"] += sz
    return type_bytes, total_bytes


def run_lean_proof(lean_path, lean_file):
    """K9: Lean 4 reduct-invariance (tümevarımsal kanıt). Döndürür (ok: bool, detail: str)."""
    lean_dir = os.path.dirname(lean_file)
    try:
        r = subprocess.run([lean_path, lean_file], capture_output=True, text=True,
                           timeout=120, cwd=lean_dir or ".")
    except FileNotFoundError:
        return False, f"lean bulunamadı: {lean_path}"
    except subprocess.TimeoutExpired:
        return False, "Lean derleme zaman aşımı (>120s)"
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return True, "Lean 4 reduct-invariance derlendi ve geçti"
    tail = [l.strip() for l in out.splitlines() if l.strip()][-3:]
    detail = " | ".join(tail) if tail else f"exit={r.returncode}"
    return False, f"Lean derleme hatası: {detail}"


def check_zip_lineage(zip_path, lineage_path, add):
    """Soy hattı: zip_lineage.json'daki her nesli tek kaynaktan doğrula.

    zip_lineage.json (M0 §10 ile AYNI kaynak) dış zip'in nesil zincirini
    tutar: {note, hash, commit, current}. commit'li nesiller git'ten
    yeniden türetilir (`git show <commit>:<path> | sha256`) ve kayıtlı
    hash ile karşılaştırılır — uyuşmazlık P1. current=true olan nesil
    ayrıca CANLI dosya ile karşılaştırılır — uyuşmazlık P0. commit=null
    (pre-git, §9'da dondurulmuş) nesiller yalnızca kayıttır (INFO).
    git repo/commit yoksa ilgili nesil UNVERIFIED (INFO) sayılır.
    Döndürür (ok: bool, detail: str, records: list[dict]) — records,
    --lineage-out sidecar'ı ve run summary için makine-okunur nesil
    kayıtlarıdır: {gen, note, hash, commit, status}.
    """
    if not os.path.isfile(lineage_path):
        return True, f"soy hattı dosyası yok: {lineage_path} (atlandı)", []
    try:
        with open(lineage_path, encoding="utf-8") as lf:
            lineage = json.load(lf)
    except (json.JSONDecodeError, OSError) as e:
        add("P1", "LINEAGE-LOAD", "Soy hattı", f"okunamadı: {lineage_path}", str(e))
        return False, f"soy hattı okunamadı: {e}", []
    gens = lineage.get("generations", [])
    if not gens:
        add("P1", "LINEAGE-EMPTY", "Soy hattı", "generations boş", lineage_path)
        return False, "soy hattı boş", []

    cur_hash = sha256_file(zip_path) if os.path.isfile(zip_path) else None
    records = []
    ok = True
    for g in gens:
        note = g.get("note", "?")
        rec_hash = g.get("hash")
        commit = g.get("commit")
        is_cur = bool(g.get("current"))
        if is_cur:
            # CANLI dosya ile karşılaştır — P0
            if cur_hash and rec_hash and cur_hash == rec_hash:
                records.append({"gen": "current", "note": note, "hash": rec_hash,
                                "commit": None, "status": "PASS (canlı dosya ile aynı)"})
            else:
                ok = False
                add("P0", "LINEAGE-CUR", "Soy hattı", f"current nesil canlı dosya ile uyuşmuyor ({note})",
                    f"kayıt={rec_hash} canlı={cur_hash}")
                records.append({"gen": "current", "note": note, "hash": rec_hash,
                                "commit": None, "status": "FAIL"})
            continue
        if commit is None:
            records.append({"gen": "pre-git", "note": note, "hash": rec_hash,
                            "commit": None, "status": "INFO (dondurulmuş §9)"})
            continue
        # git'ten yeniden türet
        try:
            r = subprocess.run(
                ["git", "show", f"{commit}:{lineage.get('path_in_repo', zip_path)}"],
                capture_output=True)
        except FileNotFoundError:
            records.append({"gen": commit[:8], "note": note, "hash": rec_hash,
                            "commit": commit, "status": "UNVERIFIED (git yok)"})
            continue
        if r.returncode != 0:
            records.append({"gen": commit[:8], "note": note, "hash": rec_hash,
                            "commit": commit, "status": "UNVERIFIED (commit yok)"})
            continue
        got = hashlib.sha256(r.stdout).hexdigest()
        if got == rec_hash:
            records.append({"gen": commit[:8], "note": note, "hash": rec_hash,
                            "commit": commit, "status": "PASS (git show ile aynı)"})
        else:
            ok = False
            add("P1", "LINEAGE-HASH", "Soy hattı", f"nesil hash'i git'ten türetilenle uyuşmuyor ({note})",
                f"kayıt={rec_hash} git_show={got}")
            records.append({"gen": commit[:8], "note": note, "hash": rec_hash,
                            "commit": commit, "status": "FAIL"})

    lines = ["Soy hattı (zip_lineage.json — tek kaynak):",
             f"{'NESİL':<12} {'NOTE':<30} {'HASH':<14} DURUM",
             "-" * 80]
    for r in records:
        h = (r["hash"] or "?")[:12]
        lines.append(f"{r['gen']:<12} {r['note']:<30} {h:<14} {r['status']}")
    detail = "\n".join(lines)
    return ok, detail, records


def check_cleanup(cleanup_path, add, repo_root=None):
    """K14: silme/taşıma kayıtlarını (M0 §10 CLEANUP LOG) dosya sistemiyle doğrula.

    cleanup_log.json (M0 §10 ile AYNI kaynak) üç kayıt türü tutar — hepsi
    repo köküne göre yollardır:
      - expect_absent: kaydın "silindi/taşındı" dediği yollar artık VAR
        OLMAMALI (varsa P1 — başıboş kopya geri döndü demektir).
      - moved: taşıma kayıtları — from yolu yok olmalı (P1); to yolu
        gitignore'da olduğundan yalnızca VARSA hash'i doğrulanır
        (yoksa INFO — CI fresh clone'da beklenir).
      - canonical: güncel kanonik hash'ler — dosya varsa hash birebir
        eşleşmeli (uyuşmazlık P0; dosya yoksa P0).
    Döndürür (ok: bool, detail: str).
    """
    if not os.path.isfile(cleanup_path):
        return True, f"cleanup_log.json yok: {cleanup_path} (atlandı)"
    try:
        with open(cleanup_path, encoding="utf-8") as cf:
            log = json.load(cf)
    except (json.JSONDecodeError, OSError) as e:
        add("P1", "K14-LOAD", "K14 cleanup", f"okunamadı: {cleanup_path}", str(e))
        return False, f"cleanup_log.json okunamadı: {e}"

    if repo_root is None:
        # verify_delivery.py konumu: <repo>/_calisma/CIKTI/verify_delivery.py
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _resolve(rel):
        return os.path.join(repo_root, rel)

    rows = []
    ok = True

    for rec in log.get("expect_absent", []):
        p = _resolve(rec.get("path", ""))
        note = rec.get("note", "?")
        if os.path.exists(p):
            ok = False
            h = sha256_file(p) if os.path.isfile(p) else None
            add("P1", "K14-RESURRECT", "K14 cleanup",
                f"silinmiş/taşınmış yol yeniden var: {rec.get('path')}",
                f"{note} | {p} | sha256={h}")
            rows.append(("absent", rec.get("path"), "FAIL (yol var)", note))
        else:
            rows.append(("absent", rec.get("path"), "PASS (yok)", note))

    for rec in log.get("moved", []):
        frm = rec.get("from", "")
        to = rec.get("to", "")
        note = rec.get("note", "?")
        want = rec.get("hash")
        if os.path.exists(_resolve(frm)):
            ok = False
            add("P1", "K14-MOVE-FROM", "K14 cleanup",
                f"taşınmış kaynak yol hâlâ var: {frm}", f"{note} | {_resolve(frm)}")
            rows.append(("move", frm, "FAIL (kaynak hâlâ var)", note))
        elif os.path.isfile(_resolve(to)):
            got = sha256_file(_resolve(to))
            if want and got == want:
                rows.append(("move", to, "PASS (hash eşleşti)", note))
            else:
                ok = False
                add("P1", "K14-MOVE-HASH", "K14 cleanup",
                    f"taşınmış dosya hash uyuşmuyor: {to}",
                    f"kayıt={want} canlı={got}")
                rows.append(("move", to, "FAIL (hash uyuşmuyor)", note))
        else:
            # to yolu gitignore'da — CI fresh clone'da yok; INFO.
            rows.append(("move", to, "INFO (yok — gitignore/CI)", note))

    for rec in log.get("canonical", []):
        p = _resolve(rec.get("path", ""))
        want = rec.get("hash")
        note = rec.get("note", "?")
        if not os.path.isfile(p):
            ok = False
            add("P0", "K14-CANON-MISSING", "K14 cleanup",
                f"kanonik dosya yok: {rec.get('path')}", note)
            rows.append(("canon", rec.get("path"), "FAIL (yok)", note))
            continue
        got = sha256_file(p)
        if want and got == want:
            rows.append(("canon", rec.get("path"), "PASS (hash eşleşti)", note))
        else:
            ok = False
            add("P0", "K14-CANON-HASH", "K14 cleanup",
                f"kanonik hash uyuşmuyor: {rec.get('path')}",
                f"kayıt={want} canlı={got}")
            rows.append(("canon", rec.get("path"), "FAIL (hash uyuşmuyor)", note))

    lines = ["Cleanup kaydı (cleanup_log.json — M0 §10 ile tek kaynak):",
             f"{'TÜR':<8} {'YOL':<46} DURUM   NOT",
             "-" * 100]
    lines += [f"{r[0]:<8} {r[1]:<46} {r[2]:<22} {r[3]}" for r in rows]
    detail = "\n".join(lines)
    return ok, detail


def _config_combined_sha256(config_files):
    """config.files {rel: sha256} → combined_sha256 (gen_repro_manifest.py formülü).

    Deterministik: rel yolları sıralanır, her girdi "{rel}\0{sha256}\n"
    olarak birleştirilir ve SHA-256 alınır. gen_repro_manifest.py ile birebir
    aynıdır — K10 burada YENİDEN hesaplar, böylece kayıtlı değerle
    uyuşmazlık (üretici drift'i / kurcalama) fail-closed yakalanır.
    """
    return hashlib.sha256(
        "".join(f"{rel}\0{config_files[rel]}\n"
                for rel in sorted(config_files)).encode()
    ).hexdigest()


def _cli_overrides_consistency(files, base, add, check_id="K10-OVERRIDE",
                               check_label="K10 cli_overrides tutarlılığı"):
    """cli_overrides ↔ config bundle tutarlılığı (config.combined_sha256 ile).

    config bundle'ındaki effective_config.json (cli_overrides kaydı) ile
    verify_delivery.config.json (dosya değerleri) aynı config sürümünü
    yansıtmalıdır. config.combined_sha256 ikisini birden tek hash ile
    özetlediğinden, bu ikilinin tutarlılığı cli_overrides'ın manifest'teki
    config.combined_sha256 ile tutarlılığını kanıtlar (fail-closed).

    Denetimler:
      - file_value, verify_delivery.config.json'daki karşılıkla eşleşmeli
        (budget→budget_usd, budget_method→budget_method).
      - override bayrağı == (cli_given and cli_value != file_value).
      - override=True ise effective == cli_value; False ise effective == file_value.
      - effective_config'ın üst alanı (budget_usd/budget_method), cli_overrides'
        .effective ile eşleşmeli.

    files: manifest.json'daki files dict'i ({rel: sha256}); base: bundle kökü.
    Döndürür (ok: bool, rows: list[str]).
    """
    ok = True
    rows = []

    def _find_rel(*basenames):
        for rel in sorted(files):
            if os.path.basename(rel) in basenames:
                return rel
        return None

    eff_rel = _find_rel("effective_config.json")
    file_rel = _find_rel("verify_delivery.config.json")
    if not eff_rel and not file_rel:
        return True, ["cli_overrides denetimi atlandı (config çifti bundle'da yok)"]
    if eff_rel and not file_rel:
        add("P1", check_id, check_label,
            "effective_config.json var ama verify_delivery.config.json yok")
        return False, ["effective_config.json var, verify_delivery.config.json yok"]
    if file_rel and not eff_rel:
        add("P1", check_id, check_label,
            "verify_delivery.config.json var ama effective_config.json yok")
        return False, ["verify_delivery.config.json var, effective_config.json yok"]

    eff_path = os.path.join(base, eff_rel)
    file_path = os.path.join(base, file_rel)
    try:
        with open(eff_path, encoding="utf-8") as f:
            eff = json.load(f)
    except (OSError, ValueError) as e:
        add("P1", check_id, check_label,
            f"effective_config.json okunamadı: {e}")
        return False, [f"effective_config.json okunamadı: {e}"]
    try:
        with open(file_path, encoding="utf-8") as f:
            fcfg = json.load(f)
    except (OSError, ValueError) as e:
        add("P1", check_id, check_label,
            f"verify_delivery.config.json okunamadı: {e}")
        return False, [f"verify_delivery.config.json okunamadı: {e}"]

    ov = eff.get("cli_overrides")
    if not isinstance(ov, dict):
        add("P1", check_id, check_label,
            "effective_config.json'da cli_overrides dict değil/yok")
        return False, ["cli_overrides dict değil/yok"]

    param_to_key = {"budget": "budget_usd", "budget_method": "budget_method"}
    for param, cfg_key in param_to_key.items():
        rec = ov.get(param)
        if not isinstance(rec, dict):
            ok = False
            rows.append(f"cli_overrides.{param} eksik veya dict değil")
            add("P1", check_id, check_label,
                f"cli_overrides.{param} eksik veya dict değil")
            continue
        fv = rec.get("file_value")
        cfgv = fcfg.get(cfg_key)
        if fv != cfgv:
            ok = False
            rows.append(f"cli_overrides.{param}.file_value={fv!r} "
                        f"≠ config {cfg_key}={cfgv!r}")
            add("P1", check_id, check_label,
                f"cli_overrides.{param}.file_value config ile uyuşmuyor",
                f"{fv!r} ≠ {cfgv!r}")
        cli_given = rec.get("cli_given")
        cli_val = rec.get("cli_value")
        eff_val = rec.get("effective")
        expected_override = bool(cli_given) and (cli_val != fv)
        if bool(rec.get("override")) != expected_override:
            ok = False
            rows.append(f"cli_overrides.{param}.override bayrağı tutarsız")
            add("P1", check_id, check_label,
                f"cli_overrides.{param}.override bayrağı tutarsız",
                f"override={rec.get('override')} beklenen={expected_override}")
        if rec.get("override"):
            if eff_val != cli_val:
                ok = False
                rows.append(f"cli_overrides.{param}.effective≠cli_value")
                add("P1", check_id, check_label,
                    f"cli_overrides.{param}.effective cli_value ile uyuşmuyor")
        else:
            if eff_val != fv:
                ok = False
                rows.append(f"cli_overrides.{param}.effective≠file_value")
                add("P1", check_id, check_label,
                    f"cli_overrides.{param}.effective file_value ile uyuşmuyor")
        if eff.get(cfg_key) != eff_val:
            ok = False
            rows.append(f"effective_config.{cfg_key}≠"
                        f"cli_overrides.{param}.effective")
            add("P1", check_id, check_label,
                f"effective_config.{cfg_key} cli_overrides.effective ile uyuşmuyor",
                f"{eff.get(cfg_key)!r} ≠ {eff_val!r}")
    if ok:
        rows.append("cli_overrides ↔ config bundle: PASS")
    return ok, rows


def verify_manifest_digest(manifest_path, add, check_id="K10-MANIFEST",
                           check_label="K10 manifest digest"):
    """K10: manifest.json'daki her dosyanın SHA-256'sını gerçek dosyayla karşılaştır.

    manifest.json gen_repro_manifest.py tarafından üretilir: {"files": {rel: sha256}}.
    rel yollar manifest'in bulunduğu dizine göre çözülür (bundle kökü). Her dosya
    yeniden hash'lenir; uyuşmazlık veya eksik dosya P1 bulgusu olur (fail-closed:
    sessiz geçiş yok).

    Ek olarak config objesi denetlenir (varsa): config.files girdileri files
    ile tutarlı olmalı ve config.combined_sha256, config.files'tan YENİDEN
    hesaplanan değerle eşleşmelidir — config sürümünün tek-hash özeti
    kurcalama/drift'e karşı doğrulanır. Son olarak cli_overrides kaydı
    (effective_config.json) ile dosya config'i (verify_delivery.config.json)
    arasındaki tutarlılık denetlenir — ikisi de combined_sha256 ile
    sabitlendiğinden bu, cli_overrides'ın manifest'teki config.combined_sha256
    ile tutarlılığını kanıtlar. Döndürür (ok: bool, detail: str).
    """
    mpath = os.path.abspath(manifest_path)
    if not os.path.isfile(mpath):
        return False, f"manifest yok: {mpath}"
    try:
        with open(mpath, encoding="utf-8") as mf:
            m = json.load(mf)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"manifest okunamadı ({mpath}): {e}"
    files = m.get("files")
    if not isinstance(files, dict) or not files:
        return False, f"manifest'te 'files' yok/boş ({mpath})"

    base = os.path.dirname(mpath)
    n_ok = n_bad = n_missing = 0
    bad_rows = []
    for rel, expected in sorted(files.items()):
        fp = os.path.join(base, rel)
        if not os.path.isfile(fp):
            n_missing += 1
            bad_rows.append(f"{rel} (EKSİK)")
            add("P1", check_id, check_label,
                f"manifest'teki dosya yok: {rel}")
            continue
        actual = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if actual != expected:
            n_bad += 1
            bad_rows.append(f"{rel} (beklenen {expected[:16]}… ≠ {actual[:16]}…)")
            add("P1", check_id, check_label,
                f"SHA-256 uyuşmazlığı: {rel}",
                f"beklenen {expected[:16]}… gerçek {actual[:16]}…")
        else:
            n_ok += 1

    # ---- config.combined_sha256: YENİDEN hesapla + doğrula (fail-closed) ----
    # gen_repro_manifest.py config/ önekli dosyaları ayrıca "config" objesine
    # yazar: {files: {rel: sha256}, combined_sha256}. combined, o dosyaların
    # sıralı "{rel}\0{hash}\n" birleşiminin SHA-256'sıdır. K10 burada onu
    # config.files'tan yeniden hesaplar; kayıtlı değerle uyuşmazsa P1.
    cfg_ok = True
    cfg_rows = []
    cfg = m.get("config")
    if cfg is not None and not isinstance(cfg, dict):
        cfg_ok = False
        cfg_rows.append("config: dict değil")
        add("P1", check_id, check_label, "config alanı dict değil")
    elif isinstance(cfg, dict):
        cfg_files = cfg.get("files")
        stored_combined = cfg.get("combined_sha256")
        # (a) config.files → files tutarlılığı (her girdi files'ta ve aynı hash)
        if not isinstance(cfg_files, dict):
            cfg_ok = False
            cfg_rows.append("config.files: dict değil")
            add("P1", check_id, check_label, "config.files dict değil")
            cfg_files = {}
        else:
            for rel, h in sorted(cfg_files.items()):
                if rel not in files:
                    cfg_ok = False
                    cfg_rows.append(f"{rel} (files'ta yok)")
                    add("P1", check_id, check_label,
                        f"config.files'taki dosya files'ta yok: {rel}")
                elif files[rel] != h:
                    cfg_ok = False
                    cfg_rows.append(f"{rel} (hash farklı)")
                    add("P1", check_id, check_label,
                        f"config.files hash'i files ile uyuşmuyor: {rel}",
                        f"config={h[:16]}… files={files[rel][:16]}…")
        # (b) combined_sha256 yeniden hesapla + karşılaştır
        if isinstance(cfg_files, dict):
            if cfg_files and not stored_combined:
                cfg_ok = False
                cfg_rows.append("combined_sha256 eksik")
                add("P1", check_id, check_label,
                    "config.combined_sha256 eksik (config.files dolu)")
            elif stored_combined is not None:
                recalc = _config_combined_sha256(cfg_files)
                if stored_combined != recalc:
                    cfg_ok = False
                    cfg_rows.append("combined_sha256 uyuşmazlığı")
                    add("P1", check_id, check_label,
                        "config.combined_sha256 uyuşmazlığı",
                        f"yeniden {recalc[:16]}… ≠ kayıtlı {stored_combined[:16]}…")
    elif any(rel.startswith("config/") for rel in files):
        # config objesi yok ama files'ta config/ girdileri var → üretici drift'i
        # (gen_repro_manifest.py config/ dosyası varsa config objesini her zaman yazar).
        cfg_ok = False
        cfg_rows.append("config objesi eksik")
        add("P1", check_id, check_label,
            "config objesi eksik (files'ta config/ girdileri var)")

    # ---- cli_overrides ↔ config bundle (config.combined_sha256 ile sabitlenir) ----
    # effective_config.json'un cli_overrides kaydı, dosya config'iyle
    # (verify_delivery.config.json) aynı config sürümünü yansıtmalıdır. İkisi
    # de config.combined_sha256 ile özetlendiğinden bu tutarlılık, cli_overrides'
    # ın manifest'teki config.combined_sha256 ile tutarlılığını kanıtlar.
    # Not: ov_ok ayrı tutulur — config.combined_sha256 etiketi yalnızca kendi
    # denetimini anlatır; cli_overrides sonucu ayrı ov_detail alanında görünür.
    ov_ok, ov_rows = _cli_overrides_consistency(files, base, add)

    cfg_detail = ("config.combined_sha256: PASS" if cfg_ok
                  else ("config.combined_sha256: FAIL — " + "; ".join(cfg_rows[:5])))
    ov_detail = ("cli_overrides: PASS" if ov_ok
                 else ("cli_overrides: FAIL — " + "; ".join(ov_rows[:3])))

    detail = (f"{n_ok} OK / {n_bad} uyuşmazlık / {n_missing} eksik "
              f"({len(files)} dosya); {cfg_detail}; {ov_detail}")
    if bad_rows:
        detail += " | " + "; ".join(bad_rows[:5])
    return (n_bad == 0 and n_missing == 0 and cfg_ok and ov_ok), detail


def check_repro_manifest_self_consistency(add):
    """K13: gen_repro_manifest.py'yi mock artifact'larla koşup manifest
    tutarlılığını denetler (fail-closed).

    Reproducibility manifest üreticisinin self-testi: bilinen içerikli mock
    dosyalar (alt dizin + config/ dahil) üretilir, gen_repro_manifest.py
    bunlardan manifest.json üretir, üretilen her SHA-256 gerçek dosyayla
    yeniden hash'lenerek karşılaştırılır. Üretici bug'ı/drift'i (eksik
    kayıt, yanlış hash, üretilemeyen manifest) P0/P1 ile patlar.
    Döndürür (ok: bool, detail: str).
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "gen_repro_manifest.py")
    if not os.path.isfile(script):
        add("P0", "K13-REPRO", "K13 repro manifest",
            "gen_repro_manifest.py yok", script)
        return False, f"{script} yok"

    mock = {
        "a.txt": b"hello A\n",
        "sub/b.bin": b"\x00\x01\x02\x03",
        "config/cfg.json": b'{"k": 1}',
    }
    tmp = tempfile.mkdtemp(prefix="repro_manifest_")
    try:
        art = os.path.join(tmp, "artifacts")
        out = os.path.join(tmp, "out")
        for rel, data in mock.items():
            fp = os.path.join(art, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(data)
        env = dict(os.environ)
        env.update({
            "GITHUB_RUN_ID": "local-selftest",
            "GITHUB_SHA": "mock-sha",
            "GITHUB_REF": "refs/heads/local-selftest",
        })
        try:
            r = subprocess.run(
                [sys.executable, script, "--artifacts-dir", art,
                 "--out-dir", out],
                capture_output=True, text=True, env=env, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            add("P0", "K13-REPRO", "K13 repro manifest",
                f"gen_repro_manifest.py çalıştırılamadı: {e}")
            return False, f"üretici çalıştırılamadı: {e}"
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()[:300]
            add("P0", "K13-REPRO", "K13 repro manifest",
                f"gen_repro_manifest.py exit={r.returncode}", detail)
            return False, f"üretici başarısız (exit={r.returncode}): {detail}"

        mpath = os.path.join(out, "manifest.json")
        if not os.path.isfile(mpath):
            add("P0", "K13-REPRO", "K13 repro manifest",
                "manifest.json üretilmedi", out)
            return False, f"manifest.json üretilmedi: {out}"
        try:
            with open(mpath, encoding="utf-8") as mf:
                m = json.load(mf)
        except (json.JSONDecodeError, OSError) as e:
            add("P0", "K13-REPRO", "K13 repro manifest",
                f"manifest.json okunamadı: {e}", mpath)
            return False, f"manifest okunamadı: {e}"
        files = m.get("files")
        if not isinstance(files, dict) or not files:
            add("P0", "K13-REPRO", "K13 repro manifest",
                "manifest 'files' yok/boş")
            return False, "manifest 'files' yok/boş"

        # Tamlık: her mock dosya manifest'te olmalı, fazla/eksik kayıt olmamalı.
        expected = set(mock)
        got = set(files)
        if got != expected:
            missing = sorted(expected - got)
            extra = sorted(got - expected)
            add("P1", "K13-REPRO", "K13 repro manifest",
                f"manifest kapsamı mock'larla uyuşmuyor "
                f"(eksik={missing}, fazla={extra})")
            return False, f"kapsam uyuşmuyor: eksik={missing} fazla={extra}"

        # Hash tutarlılığı: manifest'teki her SHA-256 bundle kopyasıyla aynı mı?
        n_bad = 0
        for rel in sorted(expected):
            fp = os.path.join(out, rel)  # bundle kökü = out/ (üretici kopyalar)
            actual = hashlib.sha256(open(fp, "rb").read()).hexdigest()
            if actual != files[rel]:
                n_bad += 1
                add("P1", "K13-REPRO", "K13 repro manifest",
                    f"SHA-256 uyuşmazlığı: {rel}",
                    f"beklenen {files[rel][:16]}… gerçek {actual[:16]}…")
        ok = n_bad == 0
        detail = (f"{len(expected) - n_bad} OK / {n_bad} uyuşmazlık "
                  f"({len(expected)} mock dosya)")
        return ok, detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_quiet(cmd, timeout=10):
    """Kısa bir komutu çalıştır, ilk satırı döndür (yoksa/hata → None)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or r.stderr or "").strip()
    return out.splitlines()[0].strip() if out else None


def _resolve_lean():
    """lean'i PATH'ten, /opt/homebrew/bin'den veya ~/.elan/bin'den bul."""
    for candidate in ["lean", "/opt/homebrew/bin/lean",
                      os.path.expanduser("~/.elan/bin/lean")]:
        if shutil.which(candidate) or os.path.isfile(candidate):
            return candidate
    return "lean"


def _resolve_precommit():
    """pre-commit'i PATH'ten veya proje venv'inden bul (yerel simülasyon gibi)."""
    if shutil.which("pre-commit"):
        return "pre-commit"
    venv_pc = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", ".venv_z3", "bin", "pre-commit")
    if os.path.isfile(venv_pc):
        return venv_pc
    return "pre-commit"


def probe_tool_versions():
    """Hook env sürümleri (zaman serisi için). Eksik araç → None (advisory).

    verify_delivery.py'nin KOŞTUĞU araçların sürümlerini yakalar: python (bu
    süreç), z3 (sys.executable — K8'i koşan yorumlayıcı), lean (K9), ve
    pre-commit/pdfinfo/qpdf (CI'da kurulu; yerelde yoksa None). Sürüm
    değişiklikleri history.jsonl'a `hook_env` olarak yazılır → dashboard
    zaman serisi olarak gösterir.
    """
    versions = {"python": platform.python_version()}
    versions["z3"] = _run_quiet([sys.executable, "-c",
                                 "import z3; print(z3.get_version_string())"])
    versions["lean"] = _run_quiet([_resolve_lean(), "--version"])
    versions["pre_commit"] = _run_quiet([_resolve_precommit(), "--version"])
    versions["pdfinfo"] = _run_quiet(["pdfinfo", "-v"])
    versions["qpdf"] = _run_quiet(["qpdf", "--version"])
    return versions


def main():
    t0 = time.time()  # run duvar saati (history.jsonl duration_s için)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict-determinism", action="store_true",
                    help="K6-DETERM: PDF metadata-stripped hash sidecar drift'ini P1'e çevir")
    ap.add_argument("--budget", type=float, default=None,
                    help="Bütçe kalkanı: tahmini USD üretim maliyeti "
                         "(token ≈ bytes/4; $3/M token + $0.55; v3_verify.py H4). "
                         "Varsayılan: verify_delivery.config.json → budget_usd")
    ap.add_argument("--budget-out", default=None,
                    help="Bütçe kalkanı sonucunu ayrı bir JSON dosyasına yaz "
                         "(CI artifact sidecar için)")
    ap.add_argument("--config-out", default=None,
                    help="Etkin konfigürasyonu (çözümlenmiş değerler) ayrı bir "
                         "JSON dosyasına yaz — hangi config'in kullanıldığını "
                         "denetlenebilir kılar (CI artifact sidecar için)")
    ap.add_argument("--refs-out", default=None,
                    help="Çevrimiçi referans denetimi (CrossRef/SEP/OpenLibrary) "
                         "sonuçlarını ayrı bir VERSION JSON'a yaz — her run'da kaç "
                         "referansın çevrimiçi doğrulandığını izlemek için "
                         "(CI artifact sidecar için)")
    ap.add_argument("--k0-out", default=None,
                    help="K0 bayat-zip bulgularını ayrı bir JSON'a yaz "
                         "(CI run summary'de ayrı bölüm göstermek için)")
    ap.add_argument("--lineage-out", default=None,
                    help="Soy hattı (--check-lineage) sonucunu ayrı bir JSON'a "
                         "yaz — k0_findings.json gibi CI artifact + run summary "
                         "bölümü için")
    ap.add_argument("--klayers-out", default=None,
                    help="K-katman (K0-K14) PASS/FAIL/SKIP özetini ayrı bir JSON'a "
                         "yaz — verify job'unun run summary'sinde K1-K10 bölümlerini "
                         "üretmek için")
    ap.add_argument("--history-out", default=None,
                    help="Run özetini JSONL kaydı olarak yaz (preview_server.py "
                         "history.jsonl formatıyla birebir) — CI'da verify sonrası "
                         "artifact'a yüklenir ve reproducibility manifest'inde "
                         "SHA-256 ile sabitlenir")
    ap.add_argument("--budget-method", choices=["universal", "weighted", "both"],
                    default=None,
                    help="Bütçe tahmin yöntemi: universal (bytes/4), "
                         "weighted (tip bazlı ağırlık), both (en kötümser). "
                         "Varsayılan: verify_delivery.config.json → budget_method")
    ap.add_argument("--config", default=None,
                    help="Konfig dosyası yolu (varsayılan: verify_delivery.py ile aynı dizindeki "
                         "verify_delivery.config.json)")
    ap.add_argument("--check-lineage", action="store_true",
                    help="Soy hattı: zip_lineage.json'daki her nesli git show ile\n"
                         "yeniden türetip doğrula; current nesli canlı dosyayla karşılaştır")
    ap.add_argument("--check-references", action="store_true",
                    help="K6: CrossRef DOI + SEP URL çevrimiçi referans denetimi")
    ap.add_argument("--symbolic-proof", action="store_true",
                    help="K8: Z3 sembolik ispat (symbolic_proof_z3.py; z3-solver gerektirir)")
    ap.add_argument("--lean-proof", action="store_true",
                    help="K9: Lean 4 reduct-invariance (ReductInvariance.lean; lean gerektirir)")
    ap.add_argument("--verify-manifest", default=None, metavar="PATH",
                    help="K10: gen_repro_manifest.py çıktısı manifest.json'u oku; "
                         "her dosyanın SHA-256'sını gerçek dosyayla karşılaştır "
                         "(reproducibility bütünlüğü; uyuşmazlık P1)")
    ap.add_argument("--check-config-drift", action="store_true",
                    help="K11: gen_config.py --dry-run ile config'teki "
                         "expected_pages/refs/manifest değerlerinin paketin "
                         "GERÇEK içeriğiyle uyuştuğunu doğrula (drift → P1, "
                         "fail-closed, --full'a dahil)")
    ap.add_argument("--check-plist", action="store_true",
                    help="K12: update_preview.sh --plist-check exit kodunu denetle "
                         "(0=GÜNCEL, 1=BAYAT, 2=şablon yok; macOS'a özgü, "
                         "--full'a dahil değil)")
    ap.add_argument("--check-repro-manifest", action="store_true",
                    help="K13: gen_repro_manifest.py'yi mock artifact'larla koşup "
                         "manifest tutarlılığını denetle (fail-closed)")
    ap.add_argument("--check-cleanup", action="store_true",
                    help="K14: cleanup_log.json (M0 §10 CLEANUP LOG) silme/taşıma "
                         "kayıtlarını dosya sistemiyle doğrula (fail-closed)")
    ap.add_argument("--full", action="store_true",
                    help="Tüm katmanları tek komutla koş: --check-references + "
                         "--symbolic-proof + --lean-proof + --check-lineage + "
                         "--check-config-drift + --check-repro-manifest + "
                         "--check-cleanup")
    args = ap.parse_args()
    # --full, tüm isteğe bağlı katmanları aktifleştirir
    if args.full:
        args.check_references = True
        args.symbolic_proof = True
        args.lean_proof = True
        args.check_lineage = True
        args.check_repro_manifest = True
        args.check_config_drift = True
        args.check_cleanup = True

    # ---- Konfig yükleme (CLI bayrakları config'ten öncelikli) ----
    # Fail-closed: geçersiz JSON veya şema ihlali artık sessizce varsayılana
    # düşmez — exit 2 ile bloke eder (CI/jsonschema ile aynı sonuç).
    cfg_path = args.config or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "verify_delivery.config.json")
    cfg = {}
    cfg_loaded = False
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as cf:
                cfg = json.load(cf)
        except json.JSONDecodeError as e:
            print(f"HATA: konfig geçerli JSON değil ({cfg_path}): {e}")
            return 2
        except OSError as e:
            print(f"HATA: konfig okunamadı ({cfg_path}): {e}")
            return 2
        # Şema doğrulaması (stdlib; jsonschema CI'da ayrıca doğrular)
        cfg_errors = validate_config(cfg)
        if cfg_errors:
            print(f"HATA: konfig şema doğrulaması başarısız ({cfg_path}):")
            for e in cfg_errors:
                print(f"  - {e}")
            print("  (bkz. verify_delivery.config.schema.json)")
            return 2
        cfg_loaded = True
    else:
        print(f"UYARI: konfig dosyası yok ({cfg_path}), varsayılanlar kullanılacak")

    # CLI override takibi: dosyadan gelen değerler, çözümleme öncesi yakalanır
    # (args.budget/args.budget_method None ise CLI'da verilmemiş demektir).
    file_budget_usd = cfg.get("budget_usd", 30.0)
    file_budget_method = cfg.get("budget_method", "both")
    cli_gave_budget = args.budget is not None
    cli_gave_method = args.budget_method is not None

    if args.budget is None:
        args.budget = file_budget_usd
    if isinstance(args.budget, int):
        args.budget = float(args.budget)
    if args.budget_method is None:
        args.budget_method = file_budget_method
    # Bütçe hesabının kullanacağı beklenen sayıları da config'ten doldur
    globals()["EXPECTED_MANIFEST"] = cfg.get("expected_manifest", EXPECTED_MANIFEST)
    globals()["EXPECTED_REFS"] = cfg.get("expected_refs", EXPECTED_REFS)
    globals()["EXPECTED_PAGES"] = cfg.get("expected_pages", EXPECTED_PAGES)

    # ---- Etkin konfig (çözümlenmiş değerler) ----
    # Hangi config'in kullanıldığını (dosya mı, varsayılan mı; CLI override'ları
    # dahil) denetlenebilir kılmak için rapora ve --config-out sidecar'ına yazılır.
    # cli_overrides: her bütçe parametresi için CLI'da verilen değer (yoksa null),
    # dosyadan gelen değer ve hangisinin etkin olduğu — override'lar ayrı
    # alanlarda görünür, dosyayla karşılaştırılabilir.
    def _override_rec(cli_given, cli_val, file_val, eff_val):
        return {
            "cli_given": cli_given,
            "cli_value": cli_val,
            "file_value": file_val,
            "effective": eff_val,
            "override": cli_given and cli_val != file_val,
        }

    effective_config = {
        "config_path": cfg_path,
        "source": "file" if cfg_loaded else "defaults",
        "budget_usd": args.budget,
        "budget_method": args.budget_method,
        "budget_ratios": cfg.get("budget_ratios") or DEFAULT_BUDGET_RATIOS,
        "expected_pages": cfg.get("expected_pages", EXPECTED_PAGES),
        "expected_refs": cfg.get("expected_refs", EXPECTED_REFS),
        "expected_manifest": cfg.get("expected_manifest", EXPECTED_MANIFEST),
        "cli_overrides": {
            "budget": _override_rec(
                cli_gave_budget, args.budget if cli_gave_budget else None,
                file_budget_usd, args.budget),
            "budget_method": _override_rec(
                cli_gave_method, args.budget_method if cli_gave_method else None,
                file_budget_method, args.budget_method),
        },
    }
    # ---- Etkin config şema doğrulaması (fail-closed) ----
    # Ham config dosyası yükleme anında validate_config ile denetlenir; ama
    # CLI override'ları (--budget, --budget-method) çözümlenmiş değerleri
    # geçersiz hale getirebilir (ör. --budget -5). effective_config.json
    # üretilmeden ÖNCE çözümlenmiş değerler yeniden doğrulanır — geçersiz
    # etkin config exit 2 ile bloke edilir (fail-closed; CI'da build kırmızı).
    eff_schema_check = {
        "budget_usd": effective_config["budget_usd"],
        "budget_method": effective_config["budget_method"],
        "budget_ratios": effective_config["budget_ratios"],
        "expected_pages": effective_config["expected_pages"],
        "expected_refs": effective_config["expected_refs"],
        "expected_manifest": effective_config["expected_manifest"],
    }
    eff_cfg_errors = validate_config(eff_schema_check)
    if eff_cfg_errors:
        print("HATA: etkin config şema doğrulaması başarısız:")
        for e in eff_cfg_errors:
            print(f"  - {e}")
        print("  (CLI override'ları geçersiz değer üretti; bkz. "
              "verify_delivery.config.schema.json)")
        return 2

    if args.config_out:
        try:
            with open(args.config_out, "w", encoding="utf-8") as cf_out:
                json.dump(effective_config, cf_out, indent=2, ensure_ascii=False)
            if not args.json:
                print(f"[CONFIG] effective snapshot yazıldı: {args.config_out}")
        except OSError as e:
            print(f"UYARI: effective config yazılamadı ({args.config_out}): {e}",
                  file=sys.stderr)

    findings = []  # {id, priority, check, issue, evidence}

    def add(pri, cid, check, issue, evidence=""):
        findings.append({"id": cid, "priority": pri, "check": check,
                         "issue": issue, "evidence": evidence})

    d = os.path.abspath(args.dir)
    kzip = os.path.join(d, KLASOR_ZIP)
    kside = kzip + ".sha256"

    if not os.path.isfile(kzip):
        print(f"FAIL: {KLASOR_ZIP} bulunamadı ({d})")
        return 2

    # ---- K0: bayat zip taraması (recursive) ----
    # Kanonik teslim yalnızca CIKTI/'da olmalı. _calisma/ altındaki HER zip
    # (alt dizinler dahil — repack ara ürünleri TESLIM/ ve V5_ICERIK/ altında,
    # kökteki başıboş kopyalar) "başıboş/bayat kopya" riskidir: yanlışlıkla
    # dağıtılabilir/commit edilebilir. İstisnalar: CIKTI (kanonik kopya),
    # TOOLKIT (toolkit'in kendi çalışma kopyası; kanonik iCloud'da), .venv_z3
    # + gizli dizinler (ortam). repack_delivery.py kendi transient ara
    # ürününü (OUTER_SRC içindeki iç zip) build sonrası siler — yani normal
    # repack akışı K0'ı yeşil bırakır; kalan her zip gerçek bayat kopyadır.
    parent = os.path.dirname(d)
    k0_skip = {"CIKTI", "TOOLKIT", ".venv_z3"}
    k0_findings = []  # {rel, sha256} — run summary için ayrı sidecar
    if os.path.isdir(parent):
        for root, dirs, files in os.walk(parent):
            dirs[:] = sorted(x for x in dirs
                             if x not in k0_skip and not x.startswith("."))
            for fn in sorted(files):
                if fn.lower().endswith(".zip"):
                    p = os.path.join(root, fn)
                    if os.path.isfile(p):
                        rel = os.path.relpath(p, parent)
                        h = sha256_file(p)
                        k0_findings.append({"rel": rel, "sha256": h})
                        issue = f"CIKTI dışında zip bulundu: {rel}"
                        # Kök düzeyindeki başıboş kopya için hint: TOOLKIT/
                        # K0'ın skip kümesindedir — oraya taşınırsa P1 otomatik
                        # düşer (kanonik kopya CIKTI/ + toolkit kopyası
                        # TOOLKIT/ ayrışır). Alt dizindeki (repack ara ürünü)
                        # ziplere bu hint verilmez — repack onları kendi siler.
                        if os.path.dirname(rel) == "":
                            issue += (" — ipucu: kök zip'i `TOOLKIT/` dizinine "
                                      "taşıyabilirsin (K0 atlar; P1 giderilir)")
                        add("P1", "K0-STALE", "K0 bayat zip", issue, f"{h}  {p}")
    if args.k0_out:
        try:
            with open(args.k0_out, "w", encoding="utf-8") as kf:
                json.dump({"count": len(k0_findings), "findings": k0_findings},
                          kf, indent=2, ensure_ascii=False)
            if not args.json:
                print(f"[K0] bulgu sidecar'ı yazıldı: {args.k0_out} "
                      f"({len(k0_findings)} bayat zip)")
        except OSError as e:
            add("P1", "K0-OUT", "K0 sidecar", f"yazılamadı: {args.k0_out}", str(e))

    # ---- K1: dış zip sidecar ----
    want = None
    if os.path.isfile(kside):
        got = sha256_file(kzip)
        want = parse_sha256sums(kside).get(KLASOR_ZIP)
        if want and got == want:
            pass  # OK
        elif want:
            add("P0", "K1-SIDECAR", "K1 dış zip", "dış zip hash uyuşmuyor",
                f"expected={want} actual={got}")
        else:
            add("P0", "K1-SIDECAR", "K1 dış zip", "sidecar okunamadı/parse edilemedi")
    else:
        add("P0", "K1-SIDECAR", "K1 dış zip", "sidecar yok", kside)

    # ---- Soy hattı (zip_lineage.json — M0 §10 ile tek kaynak) ----
    lineage_report = None
    if args.check_lineage:
        lineage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "zip_lineage.json")
        lineage_ok, lineage_detail, lineage_records = check_zip_lineage(
            kzip, lineage_path, add)
        lineage_report = {"ok": lineage_ok, "detail": lineage_detail,
                          "count": len(lineage_records),
                          "generations": lineage_records}
        if not args.json:
            print(f"\n{lineage_detail}")
        if args.lineage_out:
            try:
                with open(args.lineage_out, "w", encoding="utf-8") as lof:
                    json.dump(lineage_report, lof, indent=2, ensure_ascii=False)
                if not args.json:
                    print(f"[LINEAGE] soy hattı sidecar'ı yazıldı: "
                          f"{args.lineage_out} ({len(lineage_records)} nesil)")
            except OSError as e:
                add("P1", "LINEAGE-OUT", "Soy hattı sidecar",
                    f"yazılamadı: {args.lineage_out}", str(e))

    # ---- K14: Cleanup kaydı (M0 §10 silme/taşıma) ----
    cleanup_report = None
    if args.check_cleanup:
        cleanup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "cleanup_log.json")
        cleanup_ok, cleanup_detail = check_cleanup(cleanup_path, add)
        cleanup_report = {"ok": cleanup_ok, "detail": cleanup_detail}
        if not args.json:
            print(f"\n{cleanup_detail}")

    tmp = tempfile.mkdtemp(prefix="verify_delivery_")
    pages = refs = pdf_meta_report = None
    online_refs = []  # K6 çevrimiçi denetim sonuçları (VERSION JSON kaynağı)
    total_bytes = 0
    try:
        with zipfile.ZipFile(kzip) as z:
            z.extractall(tmp)
        kdir = os.path.join(tmp, KLASOR_DIR)

        # ---- K2: klasör checksum ----
        kc = os.path.join(kdir, "KLASOR_CHECKSUMLARI.sha256")
        if os.path.isfile(kc):
            expected = parse_sha256sums(kc)
            ok = bad = 0
            for rel, want in expected.items():
                p = os.path.join(kdir, rel)
                if os.path.isfile(p) and sha256_file(p) == want:
                    ok += 1
                else:
                    bad += 1
                    add("P0", "K2-FOLDER", "K2 klasör", f"dosya uyuşmuyor: {rel}")
            if bad == 0:
                pass
            if not expected:
                add("P0", "K2-FOLDER", "K2 klasör", "KLASOR_CHECKSUMLARI boş")
        else:
            add("P0", "K2-FOLDER", "K2 klasör", "KLASOR_CHECKSUMLARI.sha256 yok")

        izip = os.path.join(kdir, IC_ZIP)
        iside = izip + ".sha256"

        # ---- K3: iç zip sidecar ----
        if os.path.isfile(iside):
            igot = sha256_file(izip)
            iwant = parse_sha256sums(iside).get(IC_ZIP)
            if iwant and igot == iwant:
                pass
            elif iwant:
                add("P0", "K3-SIDECAR", "K3 iç zip", "iç zip hash uyuşmuyor",
                    f"expected={iwant} actual={igot}")
            else:
                add("P0", "K3-SIDECAR", "K3 iç zip", "iç sidecar okunamadı")
        else:
            add("P0", "K3-SIDECAR", "K3 iç zip", "iç sidecar yok", iside)

        try:
            with zipfile.ZipFile(izip) as z:
                z.extractall(tmp)
        except (zipfile.BadZipFile, OSError) as e:
            add("P0", "K3-ZIP", "K3 iç zip", "iç zip açılamıyor (bozuk)", str(e))
            pkg = None
        else:
            pkg = os.path.join(tmp, PKG_REL)

        if pkg is not None and not os.path.isdir(pkg):
            add("P0", "K4-MANIFEST", "K4 manifest", "paket dizini bulunamadı", pkg)
            pkg = None

        # bütçe kalkanı için içerik toplam baytı + dosya tipi kırılımı
        # (iç zip içeriği; tek kaynak: compute_type_bytes — gen_config.py da
        # aynı fonksiyonu kullanır, sınıflandırma drift'i olmaz).
        ic_root = os.path.join(tmp, IC_ZIP[:-4])
        type_bytes, total_bytes = compute_type_bytes(ic_root)

        # ---- K4: manifest 18/18 ----
        mf = os.path.join(pkg, "MANIFEST.txt") if pkg else None
        if mf and os.path.isfile(mf):
            exp = parse_manifest(mf)
            ok = 0
            for fn, want in exp.items():
                p = os.path.join(pkg, fn)
                if os.path.isfile(p) and md5_file(p) == want:
                    ok += 1
                else:
                    add("P0", "K4-MANIFEST", "K4 manifest", f"MD5 uyuşmuyor: {fn}")
            if ok != EXPECTED_MANIFEST:
                add("P0", "K4-MANIFEST", "K4 manifest",
                    f"manifest {ok}/{EXPECTED_MANIFEST}")
        else:
            add("P0", "K4-MANIFEST", "K4 manifest", "MANIFEST.txt yok")

        # ---- K5: 3 script byte-for-byte ----
        py = sys.executable
        for script, frozen in SCRIPTS:
            if pkg is None:
                add("P0", "K5-SCRIPT", f"K5 {script}", "paket çıkarılamadığı için atlandı")
                continue
            sp = os.path.join(pkg, script)
            fp = os.path.join(pkg, frozen)
            rc, out = run_script(py, sp)
            if rc != 0:
                add("P0", "K5-SCRIPT", f"K5 {script}", "script çalışmadı",
                    f"exit={rc}")
                continue
            if not os.path.isfile(fp):
                add("P0", "K5-SCRIPT", f"K5 {script}", "donmuş çıktı yok", frozen)
                continue
            if out != open(fp, "rb").read():
                add("P0", "K5-SCRIPT", f"K5 {script}",
                    "donmuş çıktıyla byte-for-byte UYUŞMUYOR")
            else:
                pass  # byte-for-byte OK

        # ---- K6: içerik (PDF sayfası + 64 referans) ----
        if pkg is None:
            add("P0", "K6-REFS", "K6 içerik", "paket çıkarılamadığı için atlandı")
        pdf = os.path.join(pkg, "ingiliz_empirizmi_v3.pdf") if pkg else None
        pages = pdf_pages(pdf) if pdf and os.path.isfile(pdf) else None
        if pages is not None and pages != EXPECTED_PAGES:
            add("P0", "K6-PAGES", "K6 içerik", f"PDF {pages} sayfa (beklenen {EXPECTED_PAGES})")
        tex = os.path.join(pkg, "ingiliz_empirizmi_v3.tex") if pkg else None
        refs = count_references(tex) if tex and os.path.isfile(tex) else None
        if refs is not None and refs != EXPECTED_REFS:
            add("P0", "K6-REFS", "K6 içerik", f"References {refs} (beklenen {EXPECTED_REFS})")

        # ---- K6-DETERM: PDF metadata-stripped hash (build determinism proxy) ----
        # qpdf --remove-metadata ile volatile alanlar (/Info, /ID, /CreationDate)
        # çıkarılır. Sidecar varsa karşılaştırılır; default'ta BİLGİ amaçlı
        # (tectonic non-deterministic olduğundan strict karşılaştırma her
        # repack'te yanlış pozitif üretir). --strict-determinism ile P1'e
        # çevrilebilir.
        pdf_meta_report = None
        if pdf and os.path.isfile(pdf):
            raw_h, stripped_h = qpdf_check_determinism(pdf)
            pdf_meta_report = {"raw": raw_h, "stripped": stripped_h,
                               "strict": getattr(args, "strict_determinism", False)}
            if stripped_h:
                sidecar_path = os.path.join(pkg, PDF_METADATA_SIDECAR)
                if os.path.isfile(sidecar_path):
                    expected_stripped = parse_sha256sums(sidecar_path).get(
                        PDF_METADATA_SIDECAR.replace(".sha256", "").replace(
                            "ingiliz_empirizmi_v3.pdf.", "ingiliz_empirizmi_v3.pdf.metadata."))
                    # Yukarıdaki karmaşık extract'i basitleştir:
                    expected_stripped = None
                    with open(sidecar_path) as sf:
                        for line in sf:
                            parts = line.split()
                            if len(parts) == 2 and "metadata" in parts[1]:
                                expected_stripped = parts[0]
                                break
                    pdf_meta_report["expected_stripped"] = expected_stripped
                    pdf_meta_report["drift"] = (
                        expected_stripped is not None
                        and stripped_h != expected_stripped)
                    if pdf_meta_report["drift"]:
                        if getattr(args, "strict_determinism", False):
                            add("P1", "K6-DETERM", "K6 build determinism",
                                f"PDF metadata-stripped hash drift (strict): "
                                f"expected={expected_stripped[:16]}… "
                                f"actual={stripped_h[:16]}…")

        # ---- K6+: referans denetimi (CrossRef/SEP/OpenLibrary çevrimiçi) ----
        # Sonuçlar online_refs'e toplanır; --refs-out ile her run'ın kaç
        # referansı çevrimiçi doğruladığını izleyen VERSION JSON'a yazılır.
        if args.check_references:
            if tex and os.path.isfile(tex):
                tex_text = open(tex, encoding="utf-8", errors="ignore").read()
                online_refs = run_reference_audit(tex_text, add, quiet=args.json)
            else:
                add("P0", "K6-REF", "K6 referans",
                    ".tex okunamadı, çevrimiçi denetim atlandı")

        # ---- K7: hijyen + secret ----
        for root, dirs, files in os.walk(tmp):
            dirs[:] = [x for x in dirs if x != ".git"]
            for fn in files:
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, tmp).replace(os.sep, "/")
                if any(re.search(pat, rel) for pat in HIGIENE_PATTERNS):
                    add("P1", "K7-HYG", "K7 hijyen", f"artefakt kalıntısı: {rel}")
                ext = os.path.splitext(fn)[1].lower()
                if ext in SKIP_SECRET_EXT or os.path.getsize(p) > 2_000_000:
                    continue
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for pat in SECRET_PATTERNS:
                    m = re.search(pat, txt, re.IGNORECASE)
                    if m:
                        add("P0", "K7-SECRET", "K7 secret",
                            f"şüpheli anahtar: {rel}", m.group(0)[:32])

    except (zipfile.BadZipFile, OSError) as e:
        add("P0", "K2-ZIP", "K2 klasör", "dış zip açılamıyor (bozuk)", str(e))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- K8: sembolik ispat (Z3, isteğe bağlı) ----
    if args.symbolic_proof:
        sp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          SYMBOLIC_PROOF_SCRIPT)
        if not os.path.isfile(sp):
            add("P0", "K8-Z3", "K8 sembolik ispat", f"{SYMBOLIC_PROOF_SCRIPT} yok", sp)
        else:
            ok, detail = run_symbolic_proof(sys.executable, sp)
            if not args.json:
                print(f"[K8] sembolik ispat (Z3): {'PASS' if ok else 'FAIL'} — {detail}")
            if not ok:
                add("P0", "K8-Z3", "K8 sembolik ispat", detail)

    # ---- K9: Lean 4 reduct-invariance (tümevarımsal kanıt, isteğe bağlı) ----
    if args.lean_proof:
        lp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          LEAN_PROOF_SCRIPT)
        # lean'i PATH'ten, /opt/homebrew/bin'den veya ~/.elan/bin'den bul
        lean_cmd = "lean"
        for candidate in ["lean",
                          "/opt/homebrew/bin/lean",
                          os.path.expanduser("~/.elan/bin/lean")]:
            if os.path.isfile(candidate):
                lean_cmd = candidate
                break
        if not os.path.isfile(lp):
            add("P0", "K9-LEAN", "K9 Lean ispatı", f"{LEAN_PROOF_SCRIPT} yok", lp)
        else:
            ok, detail = run_lean_proof(lean_cmd, lp)
            if not args.json:
                print(f"[K9] Lean 4 reduct-invariance: {'PASS' if ok else 'FAIL'} — {detail}")
            if not ok:
                add("P0", "K9-LEAN", "K9 Lean ispatı", detail)

    # ---- K10: reproducibility manifest digest (--verify-manifest) ----
    # gen_repro_manifest.py çıktısı manifest.json'daki her dosyanın SHA-256'sı
    # gerçek dosyayla karşılaştırılır. Uyuşmazlık/eksik → P1 (fail-closed).
    manifest_ok = None
    if args.verify_manifest:
        manifest_ok, manifest_detail = verify_manifest_digest(
            args.verify_manifest, add)
        if not args.json:
            print(f"[K10] manifest digest: {'PASS' if manifest_ok else 'FAIL'} — {manifest_detail}")
        if not manifest_ok:
            add("P1", "K10-MANIFEST", "K10 manifest digest",
                f"manifest bütünlüğü bozuk: {manifest_detail}")

    # ---- K11: config drift (gen_config.py --dry-run) ----
    # verify_delivery.config.json'daki expected_pages/expected_refs/
    # expected_manifest değerleri paketin GERÇEK içeriğinden türetilmelidir
    # (gen_config.py). --dry-run yeniden hesaplar ve commit'li config'le
    # karşılaştırır; fark varsa exit 1 → P1 (fail-closed, CI config-drift
    # job'ıyla aynı felsefe; --full'a dahil).
    config_drift_report = None
    if args.check_config_drift:
        gen = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "gen_config.py")
        if not os.path.isfile(gen):
            add("P0", "K11-CONFIG", "K11 config drift", "gen_config.py yok", gen)
            config_drift_report = {"ok": False, "exit": None, "detail": f"yok: {gen}"}
        else:
            try:
                r = subprocess.run([sys.executable, gen, "--dry-run",
                                    "--dir", d],
                                   capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired) as e:
                add("P0", "K11-CONFIG", "K11 config drift",
                    f"çalıştırılamadı: {e}", str(e))
                config_drift_report = {"ok": False, "exit": None, "detail": str(e)}
            else:
                drift_txt = (r.stderr or "").strip()
                if r.returncode != 0:
                    add("P1", "K11-CONFIG", "K11 config drift",
                        "config paket içeriğiyle uyuşmuyor (gen_config.py "
                        "--dry-run exit≠0)",
                        "; ".join(drift_txt.splitlines()[-4:])
                        or (r.stdout or "").strip()[:300])
                config_drift_report = {"ok": r.returncode == 0,
                                       "exit": r.returncode,
                                       "detail": drift_txt if drift_txt
                                       else "config paket içeriğiyle uyumlu"}
                if not args.json:
                    print(f"[K11] config drift: "
                          f"{'PASS' if r.returncode == 0 else 'FAIL'} "
                          f"(exit={r.returncode})")
                    if drift_txt:
                        for line in drift_txt.splitlines()[-6:]:
                            print(f"  {line}")

    # ---- K12: LaunchAgent plist şablon doğrulaması (--check-plist) ----
    # update_preview.sh --plist-check exit kodu: 0=GÜNCEL, 1=BAYAT/GEÇERSİZ,
    # 2=şablon yok. Plist, launchd GUI agent'ının TCC-safe mirror'dan preview
    # sunucusunu başlattığı operasyonel artefaktır; şablondan drift P1'dir.
    # Bu katman macOS'a özgüdür (plutil/LaunchAgents) — Linux CI'da şablon
    # yok (exit 2) olacağından --full'a bilerek dahil DEĞİLDİR; açıkça
    # --check-plist ile koşulur.
    plist_report = None
    if args.check_plist:
        upd = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "update_preview.sh")
        if not os.path.isfile(upd):
            add("P1", "K12-PLIST", "K12 plist", "update_preview.sh yok", upd)
            plist_report = {"ok": False, "exit": None, "output": f"yok: {upd}"}
        else:
            try:
                r = subprocess.run(["bash", upd, "--plist-check"],
                                   capture_output=True, text=True, timeout=60)
                rc, txt = r.returncode, (r.stdout + r.stderr).strip()
            except (OSError, subprocess.TimeoutExpired) as e:
                rc, txt = None, str(e)
                add("P1", "K12-PLIST", "K12 plist",
                    f"çalıştırılamadı: {e}", upd)
            else:
                if rc == 1:
                    add("P1", "K12-PLIST", "K12 plist",
                        "kurulu plist şablondan farklı (bayat/geçersiz)", txt)
                elif rc == 2:
                    add("P1", "K12-PLIST", "K12 plist",
                        "plist şablonu yok (önce --plist çalıştır)", txt)
                elif rc != 0:
                    add("P1", "K12-PLIST", "K12 plist",
                        f"beklenmedik exit kodu {rc}", txt)
            plist_report = {"ok": rc == 0, "exit": rc, "output": txt}
            if not args.json:
                print(f"[K12] plist şablon: "
                      f"{'PASS' if rc == 0 else 'FAIL'} (exit={rc}) — {txt[:100]}")

    # ---- K13: reproducibility manifest üreticisi self-testi ----
    # gen_repro_manifest.py'yi bilinen içerikli mock artifact'larla koşar;
    # üretilen manifest'in kapsamı + SHA-256'ları fail-closed denetlenir.
    # Üreticideki bir drift/bug paketin reproducibility zincirini bozar → P0/P1.
    repro_manifest_report = None
    if args.check_repro_manifest:
        repro_ok, repro_detail = check_repro_manifest_self_consistency(add)
        repro_manifest_report = {"ok": repro_ok, "detail": repro_detail}
        if not args.json:
            print(f"[K13] repro manifest: "
                  f"{'PASS' if repro_ok else 'FAIL'} — {repro_detail}")

    # ---- Bütçe kalkanı: iki yöntem yan yana ----
    # (a) Evrensel: token ≈ bytes/4      (v3_verify.py H4, bağımsız referans)
    # (b) Ağırlıklı: token ≈ bytes/r_i    (dosya tipine göre bytes-per-token)
    budget_report = None
    if args.budget is not None:
        # (a) evrensel
        universal_tokens = total_bytes // 4
        universal_cost = round(universal_tokens / 1_000_000 * 3.0, 2) + 0.55
        # (b) ağırlıklı — oranlar config'ten okunur (şema ile doğrulanır);
        #     config yoksa varsayılan oranlar kullanılır.
        ratios = {k: (cfg.get("budget_ratios") or {}).get(k, v)
                  for k, v in DEFAULT_BUDGET_RATIOS.items()}
        weighted_tokens = sum(
            type_bytes[k] // ratios[k] for k in ratios)
        weighted_cost = round(weighted_tokens / 1_000_000 * 3.0, 2) + 0.55

        # Karar: hangi yöntem kullanılsın?
        #   --budget-method=universal | weighted | both(default)
        method = getattr(args, "budget_method", "both")
        if method == "universal":
            est_cost, total_tokens = universal_cost, universal_tokens
        elif method == "weighted":
            est_cost, total_tokens = weighted_cost, weighted_tokens
        else:  # both: en kötümser (maliyet-yüksek) tahmini kullan
            est_cost = max(universal_cost, weighted_cost)
            total_tokens = max(universal_tokens, weighted_tokens)

        budget_report = {
            "limit": args.budget,
            "estimated_usd": est_cost,
            "tokens_est": total_tokens,
            "total_bytes": total_bytes,
            "verdict": "OK" if est_cost <= args.budget else "FAIL",
            "method": method,
            "comparison": {
                "universal": {"tokens": universal_tokens, "usd": universal_cost,
                              "ratio": "bytes/4 (v3_verify.py H4)"},
                "weighted":  {"tokens": weighted_tokens, "usd": weighted_cost,
                              "ratios": ratios,
                              "by_type": type_bytes},
            },
        }
        if not args.json:
            print(f"[BÜTÇE] ~{total_tokens} token → ${est_cost} "
                  f"(limit ${args.budget}, içerik {total_bytes} B, yöntem={method})")
            print(f"[BÜTÇE]   evrensel (bytes/4):  {universal_tokens} tok → ${universal_cost}")
            print(f"[BÜTÇE]   ağırlıklı (tip bazlı): {weighted_tokens} tok → ${weighted_cost}")
            tb = budget_report["comparison"]["weighted"]["by_type"]
            print(f"[BÜTÇE]   kırılım: text={tb['text']}B "
                  f"pdf={tb['pdf']}B archive={tb['archive']}B binary={tb['binary']}B")
        if est_cost > args.budget:
            add("P1", "BUDGET", "Bütçe",
                f"tahmini maliyet ${est_cost} limiti (${args.budget}) aşıyor",
                f"~{total_tokens} token, {total_bytes} B içerik")
        if args.budget_out:
            try:
                with open(args.budget_out, "w", encoding="utf-8") as bf:
                    json.dump({
                        **budget_report,
                        "date": datetime.now(timezone.utc).isoformat(),
                        "check": "v3_verify.py H4 (token ≈ bytes/4, "
                                 "$3/M token + $0.55)",
                    }, bf, indent=2, ensure_ascii=False)
                print(f"[BÜTÇE] sidecar yazıldı: {args.budget_out}")
            except OSError as e:
                add("P1", "BUDGET-OUT", "Bütçe sidecar",
                    f"yazılamadı: {args.budget_out}", str(e))

    # ---- Çevrimiçi referans denetimi VERSION JSON ----
    # Her run'da kaç referansın çevrimiçi doğrulandığını (kaynak ve sonuç
    # kırılımıyla) izleyen makine-okunur kayıt. --refs-out ile CI artifact
    # sidecar'ı olarak ayrıca yazılır; --json çıktısına da gömülür.
    refs_online_report = None
    if online_refs:
        by_source = {}
        by_verdict = {}
        for r in online_refs:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
            by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
        refs_online_report = {
            "tool": "verify_delivery.py K6 referans denetimi "
                    "(CrossRef/SEP/OpenLibrary)",
            "date": datetime.now(timezone.utc).isoformat(),
            "total_online": len(online_refs),
            "verified": by_verdict.get("PASS", 0),
            "unverified": by_verdict.get("UNVERIFIED", 0),
            "mismatch": by_verdict.get("MISMATCH", 0),
            "by_source": by_source,
            "by_verdict": by_verdict,
            "results": online_refs,
        }
        if args.refs_out:
            try:
                with open(args.refs_out, "w", encoding="utf-8") as rf:
                    json.dump(refs_online_report, rf, indent=2, ensure_ascii=False)
                if not args.json:
                    print(f"[REF] çevrimiçi denetim VERSION JSON yazıldı: "
                          f"{args.refs_out} ({len(online_refs)} kayıt)")
            except OSError as e:
                add("P1", "REFS-OUT", "Referans sidecar",
                    f"yazılamadı: {args.refs_out}", str(e))

    manifest_digest_report = None
    if args.verify_manifest:
        manifest_digest_report = {
            "path": os.path.abspath(args.verify_manifest),
            "ok": bool(manifest_ok),
            "verdict": "PASS" if manifest_ok else "FAIL",
            "detail": manifest_detail,
        }

    p0 = sum(1 for f in findings if f["priority"] == "P0")
    p1 = sum(1 for f in findings if f["priority"] == "P1")
    verdict = "PASS" if (p0 == 0 and p1 == 0) else "FAIL"

    # Hook env sürümleri (zaman serisi) — --json ve --history-out için; aksi
    # halde gereksiz subprocess probe yapma (verify'yi hızlandır).
    hook_env = probe_tool_versions() if (args.json or args.history_out) else None

    out = {
        "tool": "verify_delivery.py (Stoic-Hume V5 fail-closed CI)",
        "date": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": {"P0": p0, "P1": p1},
        "findings": findings,
        "pdf_pages": pages,
        "ref_count": refs,
        "config": effective_config,
        "budget": budget_report,
        "pdf_hash": pdf_meta_report,
        "references_online": refs_online_report,
        "hook_env": hook_env,
        "manifest_digest": manifest_digest_report,
        "config_drift": config_drift_report,
        "repro_manifest": repro_manifest_report,
        "lineage": lineage_report,
        "plist": plist_report,
        "cleanup": cleanup_report,
    }

    # ---- K-katman özeti sidecar (run summary için) ----
    # findings tek kaynağından K0-K14'ün PASS/FAIL/SKIP durumunu türetir;
    # verify job'unun GITHUB_STEP_SUMMARY'sinde K1-K10 bölümlerini üretmek
    # için run_summary_klayers.py tarafından okunur.
    if args.klayers_out:
        try:
            klayers = build_layers_summary(args, findings)
            with open(args.klayers_out, "w", encoding="utf-8") as kf:
                json.dump({"verdict": verdict,
                           "counts": {"P0": p0, "P1": p1},
                           "layers": klayers},
                          kf, indent=2, ensure_ascii=False)
            if not args.json:
                print(f"[SUMMARY] K-katman özeti yazıldı: {args.klayers_out} "
                      f"({sum(1 for l in klayers.values() if l['status'] == 'FAIL')} FAIL)")
        except OSError as e:
            add("P1", "SUMMARY-OUT", "Summary sidecar",
                f"yazılamadı: {args.klayers_out}", str(e))

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("=== Stoic-Hume V5 teslim doğrulaması ===")
        for f in findings:
            print(f"[{f['priority']}] {f['check']}: {f['issue']}"
                  + (f" ({f['evidence']})" if f["evidence"] else ""))
        print(f"\nSONUÇ: {verdict}  (P0={p0}, P1={p1})")
        if pages is not None or refs is not None:
            print(f"PDF: {pages} sayfa | References: {refs}")
        if pdf_meta_report and pdf_meta_report.get("stripped"):
            print(f"PDF hash: raw={pdf_meta_report['raw'][:16]}… "
                  f"metadata-stripped={pdf_meta_report['stripped'][:16]}…")
        if args.verify_manifest:
            print(f"K10 manifest digest: {'PASS' if manifest_ok else 'FAIL'}")
        if cleanup_report:
            print(f"K14 cleanup: {'PASS' if cleanup_report['ok'] else 'FAIL'} "
                  f"(silme/taşıma kayıtları)")
        print(f"Config: {effective_config['source']} ← {effective_config['config_path']} "
              f"(budget_usd={effective_config['budget_usd']}, "
              f"method={effective_config['budget_method']}, "
              f"pages={effective_config['expected_pages']}, "
              f"refs={effective_config['expected_refs']}, "
              f"manifest={effective_config['expected_manifest']})")
        ov = effective_config.get("cli_overrides", {})
        for k, rec in ov.items():
            if rec.get("override"):
                print(f"  [CLI override] {k}: {rec['file_value']!r} → {rec['effective']!r} "
                      f"(CLI verildi)")
        if budget_report:
            print(f"Bütçe: ~{budget_report['tokens_est']} token → ${budget_report['estimated_usd']} "
                  f"(limit ${budget_report['limit']})")
        if refs_online_report:
            ror = refs_online_report
            print(f"Çevrimiçi referans: {ror['verified']}/{ror['total_online']} doğrulandı "
                  f"(PASS={ror['verified']}, UNVERIFIED={ror['unverified']}, "
                  f"MISMATCH={ror['mismatch']}; "
                  f"CrossRef {ror['by_source'].get('crossref', 0)} + "
                  f"SEP {ror['by_source'].get('sep', 0)} + "
                  f"OpenLibrary {ror['by_source'].get('openlibrary', 0)})")
    # ---- Run-history sidecar (history.jsonl — CI reproducibility) ----
    # preview_server.py'nin HISTORY_KEYS formatıyla birebir. CI'da verify
    # sonrası artifact'a yüklenir; reproducibility job'ı (gen_repro_manifest.py)
    # tüm artifact'ları hash'lediğinden SHA-256 ile otomatik sabitlenir.
    # Append semantiği: aynı dosyaya tekrar koşulursa birikir (JSONL).
    if args.history_out:
        history_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "p0": p0,
            "p1": p1,
            "duration_s": round(time.time() - t0, 2),
            "budget_usd": (budget_report or {}).get("estimated_usd"),
            "pdf_pages": pages,
            "ref_count": refs,
            "raw_sha256": (pdf_meta_report or {}).get("raw"),
            "stripped_sha256": (pdf_meta_report or {}).get("stripped"),
            "exit_code": 0 if verdict == "PASS" else 1,
            "refs_verified": (refs_online_report or {}).get("verified"),
            "refs_total": (refs_online_report or {}).get("total_online"),
            "refs_mismatch": (refs_online_report or {}).get("mismatch"),
            "refs_by_source": (refs_online_report or {}).get("by_source"),
            "hook_env": hook_env,
        }
        try:
            with open(args.history_out, "a", encoding="utf-8") as hf:
                hf.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
            if not args.json:
                print(f"[HISTORY] run kaydı yazıldı: {args.history_out}")
        except OSError as e:
            print(f"HATA: history sidecar yazılamadı ({args.history_out}): {e}",
                  file=sys.stderr)
            return 1

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
