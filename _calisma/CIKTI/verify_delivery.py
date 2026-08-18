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
                                              #      karşılaştır (reproducibility bütünlüğü)
    python3 verify_delivery.py --full          # tüm katmanlar: K1-K9 + referans denetimi + Z3 + Lean
                                              #   (--check-references + --symbolic-proof + --lean-proof)

Exit kodu: 0 = PASS, 1 = FAIL, 2 = kullanım/ortam hatası.

Yalnızca Python 3 standart kütüphanesi kullanır (hashlib, zipfile, subprocess,
tempfile; --check-references için ayrıca urllib). Harici `unzip`/`shasum`/`diff`
GEREKMEZ. pdfinfo varsa PDF sayfa kontrolü eklenir, yoksa atlanır (FAIL değil).

Doğrulama zinciri (Katman 0..9):
  K0  Bayat    CIKTI dışında kalan HER zip taraması (recursive; P1)
  K1  Dış zip  SHA-256 sidecar (kurcalanma)
  K2  Klasör   KLASOR_CHECKSUMLARI.sha256 (tüm dosyalar)
  K3  İç zip   SHA-256 sidecar (kurcalanma)
  K4  Manifest MANIFEST.txt 18/18 (boyut + MD5)
  K5  Scriptler 3 script byte-for-byte (donmuş çıktılarla)
  K6  İçerik   PDF sayfa sayısı (pdfinfo, isteğe bağlı) + References 64/64
               + (--check-references ile) CrossRef DOI + SEP URL + OpenLibrary /
               Internet Archive / Perseus çevrimiçi denetimi
  K7  Hijyen   secret/anahtar + artefakt taraması
  K8  İspat    Z3 sembolik ispat (--symbolic-proof; z3-solver gerektirir)
  K9  Lean     Lean 4 reduct-invariance tümevarımsal kanıt (--lean-proof; lean gerektirir)
  K10 Manifest gen_repro_manifest.py çıktısı manifest.json'daki her dosyanın
               SHA-256'sını gerçek dosyayla karşılaştır (--verify-manifest PATH;
               reproducibility bütünlüğü — fail-closed: uyuşmazlık P1)
"""
import argparse
import hashlib
import json
import os
import re
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
PDF_METADATA_SIDECAR = "ingiliz_empirizmi_v3.pdf.metadata.sha256"
PDF_RAW_SIDECAR = "ingiliz_empirizmi_v3.pdf.sha256"
SYMBOLIC_PROOF_SCRIPT = "symbolic_proof_z3.py"
LEAN_PROOF_SCRIPT = "../lean_reduct/ReductInvariance.lean"
SCRIPTS = [
    ("core_formal_model_check.py", "test_output.txt"),
    ("encoding_sensitivity_check.py", "encoding_sensitivity_output.txt"),
    ("gate15_check.py", "gate15_output.txt"),
]

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
    {"key": "Hicks 1925", "query": "Diogenes Laertius Lives Opinions Eminent Philosophers Hicks Loeb",
     "title_needle": "lives and opinions", "author_needle": "hicks",
     "year": 1925, "publisher_needle": "loeb",
     "tex_needle": "Hicks, R.D. (tr.) (1925)"},
    {"key": "Hume (Selby-Bigge/Nidditch) 1975", "query": "Hume Enquiries Selby-Bigge Nidditch",
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
     "tex_needle": "Schmitt, C.B. (1972)"},
    {"key": "Schmitt 1983", "query": "Rediscovery Ancient Skepticism Schmitt",
     "title_needle": "skeptical tradition",
     "tex_needle": "Schmitt, C.B. (1983)"},
    {"key": "Xunzi Knoblock", "query": "Xunzi translation Knoblock",
     "title_needle": "xunzi", "creator_needle": "knoblock",
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


def run_reference_audit(tex_text, add, quiet=False):
    """K6 referans denetimi: .tex varlığı + CrossRef/SEP/OpenLibrary/
    Internet Archive/Perseus çevrimiçi doğrulama.

    Döndürür: çevrimiçi doğrulama sonuçlarının listesi (VERSION JSON kaynağı)
    — her öğe {key, source, verdict, detail, doi|url|urn|query} — böylece her
    run'da kaç referansın çevrimiçi doğrulandığı izlenebilir."""
    def say(line):
        if not quiet:
            print(line)

    say("\n--- K6 referans denetimi (CrossRef/SEP/OpenLibrary/IA/Perseus çevrimiçi) ---")
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
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] Archive {ref['key']:<30} -> {detail[:80]}")
        online_results.append({"key": ref["key"], "source": "archive",
                               "verdict": v, "detail": detail,
                               "query": _archive_query(ref)})
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} Internet Archive uyuşmuyor: {detail}")
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
        f"Internet Archive {len(REFERENCE_ARCHIVE)} + "
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


def verify_manifest_digest(manifest_path, add):
    """K10: manifest.json'daki her dosyanın SHA-256'sını gerçek dosyayla karşılaştır.

    manifest.json gen_repro_manifest.py tarafından üretilir: {"files": {rel: sha256}}.
    rel yollar manifest'in bulunduğu dizine göre çözülür (bundle kökü). Her dosya
    yeniden hash'lenir; uyuşmazlık veya eksik dosya P1 bulgusu olur (fail-closed:
    sessiz geçiş yok). Döndürür (ok: bool, detail: str).
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
            add("P1", "K10-MANIFEST", "K10 manifest digest",
                f"manifest'teki dosya yok: {rel}")
            continue
        actual = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if actual != expected:
            n_bad += 1
            bad_rows.append(f"{rel} (beklenen {expected[:16]}… ≠ {actual[:16]}…)")
            add("P1", "K10-MANIFEST", "K10 manifest digest",
                f"SHA-256 uyuşmazlığı: {rel}",
                f"beklenen {expected[:16]}… gerçek {actual[:16]}…")
        else:
            n_ok += 1

    detail = (f"{n_ok} OK / {n_bad} uyuşmazlık / {n_missing} eksik "
              f"({len(files)} dosya)")
    if bad_rows:
        detail += " | " + "; ".join(bad_rows[:5])
    return (n_bad == 0 and n_missing == 0), detail


def main():
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
    ap.add_argument("--budget-method", choices=["universal", "weighted", "both"],
                    default=None,
                    help="Bütçe tahmin yöntemi: universal (bytes/4), "
                         "weighted (tip bazlı ağırlık), both (en kötümser). "
                         "Varsayılan: verify_delivery.config.json → budget_method")
    ap.add_argument("--config", default=None,
                    help="Konfig dosyası yolu (varsayılan: verify_delivery.py ile aynı dizindeki "
                         "verify_delivery.config.json)")
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
    ap.add_argument("--full", action="store_true",
                    help="Tüm katmanları (--check-references + --symbolic-proof + --lean-proof) tek komutla koş")
    args = ap.parse_args()
    # --full, tüm isteğe bağlı katmanları aktifleştirir
    if args.full:
        args.check_references = True
        args.symbolic_proof = True
        args.lean_proof = True

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
        "budget_ratios": cfg.get("budget_ratios"),
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
    if os.path.isdir(parent):
        for root, dirs, files in os.walk(parent):
            dirs[:] = sorted(x for x in dirs
                             if x not in k0_skip and not x.startswith("."))
            for fn in sorted(files):
                if fn.lower().endswith(".zip"):
                    p = os.path.join(root, fn)
                    if os.path.isfile(p):
                        rel = os.path.relpath(p, parent)
                        add("P1", "K0-STALE", "K0 bayat zip",
                            f"CIKTI dışında zip bulundu: {rel}",
                            f"{sha256_file(p)}  {p}")

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
                    f"manifest {ok}/{EXPECTED_MANIFEST} (beklenen 18/18)")
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
        _default_ratios = {"text": 3, "pdf": 8, "archive": 12, "binary": 20}
        ratios = {k: cfg.get("budget_ratios", {}).get(k, v)
                  for k, v in _default_ratios.items()}
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
            "detail": manifest_detail,
        }

    p0 = sum(1 for f in findings if f["priority"] == "P0")
    p1 = sum(1 for f in findings if f["priority"] == "P1")
    verdict = "PASS" if (p0 == 0 and p1 == 0) else "FAIL"

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
        "manifest_digest": manifest_digest_report,
    }
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
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
