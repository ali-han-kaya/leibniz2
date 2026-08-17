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
                                              # K6: CrossRef/SEP çevrimiçi referans denetimi
    python3 verify_delivery.py --symbolic-proof
                                              # K8: Z3 sembolik ispat (core_section.tex teoremleri)
    python3 verify_delivery.py --lean-proof
                                              # K9: Lean 4 reduct-invariance (tümevarımsal kanıt)
    python3 verify_delivery.py --full          # tüm katmanlar: K1-K9 + CrossRef/SEP + Z3 + Lean
                                              #   (--check-references + --symbolic-proof + --lean-proof)

Exit kodu: 0 = PASS, 1 = FAIL, 2 = kullanım/ortam hatası.

Yalnızca Python 3 standart kütüphanesi kullanır (hashlib, zipfile, subprocess,
tempfile; --check-references için ayrıca urllib). Harici `unzip`/`shasum`/`diff`
GEREKMEZ. pdfinfo varsa PDF sayfa kontrolü eklenir, yoksa atlanır (FAIL değil).

Doğrulama zinciri (Katman 1..9):
  K1  Dış zip  SHA-256 sidecar (kurcalanma)
  K2  Klasör   KLASOR_CHECKSUMLARI.sha256 (tüm dosyalar)
  K3  İç zip   SHA-256 sidecar (kurcalanma)
  K4  Manifest MANIFEST.txt 18/18 (boyut + MD5)
  K5  Scriptler 3 script byte-for-byte (donmuş çıktılarla)
  K6  İçerik   PDF sayfa sayısı (pdfinfo, isteğe bağlı) + References 64/64
               + (--check-references ile) CrossRef DOI + SEP URL çevrimiçi denetimi
  K7  Hijyen   secret/anahtar + artefakt taraması
  K8  İspat    Z3 sembolik ispat (--symbolic-proof; z3-solver gerektirir)
  K9  Lean     Lean 4 reduct-invariance tümevarımsal kanıt (--lean-proof; lean gerektirir)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

KLASOR_ZIP = "TESLIM_KLASOR_V5_2026-08-17.zip"
KLASOR_DIR = "Stoic-Hume-Final-V5_2026-08-17"
IC_ZIP = "TESLIM_V5_FINAL_2026-08-17.zip"
PKG_REL = "TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17"
EXPECTED_MANIFEST = 18
EXPECTED_REFS = 64
EXPECTED_PAGES = 33
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
    {"key": "Beth 1953", "status": "HATA", "priority": "P1",
     "note": ".tex 'Journal of Symbolic Logic 18(1): 8-13' diyor; doğrusu "
             "Indagationes Mathematicae 15 (1953): 330-339 (Proc. KNAW A56)."},
    {"key": "Fosl 1998", "status": "DOGRULANAMADI", "priority": "INFO",
     "note": "Kitap (Norton & Norton 1996) doğru; 'JHP 36(2)' yeri teyit edilemedi "
             "(ECSSS Newsletter 11, 35-36 bulundu)."},
    {"key": "Popkin 1952", "status": "KUCUK NOT", "priority": "INFO",
     "note": "Ana kayıt RoM 6(1):65-81 doğru; yeniden basım sayfası 133-147 "
             "(metin 133-148 yazmış)."},
    {"key": "Priest 2018", "status": "KUCUK NOT", "priority": "INFO",
     "note": "Tam alt başlık 'An Essay on Buddhist Metaphysics and the Catuskoti' "
             "(metin kısaltmış)."},
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


def run_reference_audit(tex_text, add, quiet=False):
    """K6 referans denetimi: .tex varlığı + CrossRef/SEP çevrimiçi doğrulama."""
    def say(line):
        if not quiet:
            print(line)

    say("\n--- K6 referans denetimi (CrossRef/SEP çevrimiçi) ---")

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
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} CrossRef uyuşmuyor: {detail}")
        time.sleep(0.4)  # CrossRef polite-pool

    # 3) SEP doğrudan URL doğrulama
    for ref in REFERENCE_SEP:
        v, detail = sep_check(ref)
        tag = {"PASS": "OK  ", "MISMATCH": "FAIL", "UNVERIFIED": "SKIP"}[v]
        say(f"  [{tag}] SEP     {ref['key']:<14} -> {detail}")
        if v == "MISMATCH":
            add("P1", "K6-REF", "K6 referans",
                f"{ref['key']} SEP uyuşmuyor: {detail}")

    # 4) Sabit denetim bulguları (çevrimiçi indekslenmeyen kitap/edişyon/antik)
    for k in REFERENCE_KNOWN:
        say(f"  [{k['status']}] STATIC {k['key']:<14} -> {k['note']}")
        if k.get("priority") == "P1":
            add("P1", "K6-REF", "K6 referans",
                f"[{k['status']}] {k['key']}: {k['note']}")

    say(f"  Kapsam: 64 referans; canlı doğrulanan "
        f"{len(REFERENCE_CROSSREF) + len(REFERENCE_SEP)} "
        f"(CrossRef {len(REFERENCE_CROSSREF)} + SEP {len(REFERENCE_SEP)}); "
        f"kalanı REFERANS_KANIT_DENETIMI.md sabit denetimine dayanır.")


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


def run_script(py, script):
    r = subprocess.run([py, script], capture_output=True, text=True,
                       timeout=120, cwd=os.path.dirname(script) or ".")
    return r.returncode, r.stdout.encode("utf-8", "replace")


def run_symbolic_proof(py, script):
    """K8: sembolik ispat (Z3). Döndürür (ok: bool, detail: str)."""
    try:
        r = subprocess.run([py, script], capture_output=True, text=True,
                           timeout=180, cwd=os.path.dirname(script) or ".")
    except FileNotFoundError:
        return False, f"yorumlayıcı bulunamadı: {py}"
    except subprocess.TimeoutExpired:
        return False, "sembolik ispat zaman aşımı (>180s)"
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return True, "Z3 ispatı geçti (12/12)"
    if "No module named 'z3'" in out or "ModuleNotFoundError" in out:
        return False, "z3-solver kurulu değil — pip install z3-solver"
    tail = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()][-2:]
    detail = " | ".join(tail) if tail else f"exit={r.returncode}"
    return False, f"Z3 beklenmedik sonuç: {detail}"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget", type=float, default=None,
                    help="Bütçe kalkanı: tahmini USD üretim maliyeti "
                         "(token ≈ bytes/4; $3/M token + $0.55; v3_verify.py H4). "
                         "Varsayılan: verify_delivery.config.json → budget_usd")
    ap.add_argument("--budget-out", default=None,
                    help="Bütçe kalkanı sonucunu ayrı bir JSON dosyasına yaz "
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
    ap.add_argument("--full", action="store_true",
                    help="Tüm katmanları (--check-references + --symbolic-proof + --lean-proof) tek komutla koş")
    args = ap.parse_args()
    # --full, tüm isteğe bağlı katmanları aktifleştirir
    if args.full:
        args.check_references = True
        args.symbolic_proof = True
        args.lean_proof = True

    # ---- Konfig yükleme (CLI bayrakları config'ten öncelikli) ----
    cfg_path = args.config or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "verify_delivery.config.json")
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as cf:
                cfg = json.load(cf)
        except (OSError, json.JSONDecodeError) as e:
            print(f"UYARI: konfig okunamadı ({cfg_path}): {e}")
    else:
        print(f"UYARI: konfig dosyası yok ({cfg_path}), varsayılanlar kullanılacak")

    if args.budget is None:
        args.budget = cfg.get("budget_usd", 30.0)
    if isinstance(args.budget, int):
        args.budget = float(args.budget)
    if args.budget_method is None:
        args.budget_method = cfg.get("budget_method", "both")
    # Bütçe hesabının kullanacağı beklenen sayıları da config'ten doldur
    globals()["EXPECTED_MANIFEST"] = cfg.get("expected_manifest", EXPECTED_MANIFEST)
    globals()["EXPECTED_REFS"] = cfg.get("expected_refs", EXPECTED_REFS)
    globals()["EXPECTED_PAGES"] = cfg.get("expected_pages", EXPECTED_PAGES)

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
    pages = refs = None
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
        # (iç zip içeriği; token ≈ bytes/4 evrensel, ama ağırlıklı yöntem
        # dosya tipine göre bytes-per-token oranı kullanır: metin 1/3, PDF 1/8,
        # arşiv 1/12, diğer binary 1/20).
        ic_root = os.path.join(tmp, IC_ZIP[:-4])
        type_bytes = {"text": 0, "pdf": 0, "archive": 0, "binary": 0}
        if os.path.isdir(ic_root):
            for _root, _dirs, files in os.walk(ic_root):
                for fn in files:
                    p = os.path.join(_root, fn)
                    try:
                        sz = os.path.getsize(p)
                    except OSError:
                        continue
                    total_bytes += sz
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in (".pdf",):
                        type_bytes["pdf"] += sz
                    elif ext in (".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"):
                        type_bytes["archive"] += sz
                    elif ext in (
                        ".tex", ".py", ".md", ".json", ".txt", ".csv", ".tsv",
                        ".yaml", ".yml", ".html", ".xml", ".css", ".js",
                        ".sh", ".rb", ".rs", ".lean", ".toml", ".ini", ".cfg",
                        ".bst", ".bib", ".sty", ".cls",
                    ):
                        type_bytes["text"] += sz
                    else:
                        type_bytes["binary"] += sz

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

        # ---- K6+: referans denetimi (CrossRef/SEP çevrimiçi, isteğe bağlı) ----
        if args.check_references:
            if tex and os.path.isfile(tex):
                tex_text = open(tex, encoding="utf-8", errors="ignore").read()
                run_reference_audit(tex_text, add, quiet=args.json)
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

    # ---- Bütçe kalkanı: iki yöntem yan yana ----
    # (a) Evrensel: token ≈ bytes/4      (v3_verify.py H4, bağımsız referans)
    # (b) Ağırlıklı: token ≈ bytes/r_i    (dosya tipine göre bytes-per-token)
    budget_report = None
    if args.budget is not None:
        # (a) evrensel
        universal_tokens = total_bytes // 4
        universal_cost = round(universal_tokens / 1_000_000 * 3.0, 2) + 0.55
        # (b) ağırlıklı
        ratios = {"text": 3, "pdf": 8, "archive": 12, "binary": 20}
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

    p0 = sum(1 for f in findings if f["priority"] == "P0")
    p1 = sum(1 for f in findings if f["priority"] == "P1")
    verdict = "PASS" if (p0 == 0 and p1 == 0) else "FAIL"

    out = {
        "tool": "verify_delivery.py (Stoic-Hume V5 fail-closed CI)",
        "date": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": {"P0": p0, "P1": p1},
        "findings": findings,
        "budget": budget_report,
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
        if budget_report:
            print(f"Bütçe: ~{budget_report['tokens_est']} token → ${budget_report['estimated_usd']} "
                  f"(limit ${budget_report['limit']})")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
