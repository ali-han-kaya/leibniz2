#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_axioms.py — K9 Lean sorry/axiom ön-kapısı (fail-closed).

run_lean_proof ÖNCESİ çalışır: lean_reduct'taki her .lean kaynağında

  * `\bsorry\b`        — kelime sınırlı "sorry" (ispat boşluğu / admit)
  * top-level `axiom`   — satır başında (yalnızca boşluk öncesi) `axiom` bildirimi

aranır. Bulgu varsa exit 1 (fail-closed): K9 derlemeye bile gitmeden FAIL
üretir — `sorry` Lean'de derlenip geçebilir, `--wfail` her durumda yakalamaz;
statik tarama ispat boşluğunu kaynak seviyesinde garanti eder.

Tarama yorum/string farkındadır:

  * `--` satır yorumları ve `/- ... -/` blok yorumları atlanır (içlerindeki
    "sorry"/"axiom" bulgu DEĞİLDİR — belgelerde geçen kelimeler kapıyı
    tetiklemez).
  * `"..."` string literal'leri maskelenir (Lean'de string'lerde geçen
    "sorry" bulgu değildir).
  * `axiom` yalnızca SATIR BAŞINDA (boşluk sonrası) aranır — top-level
    bildirim; `theorem ... := by ...` gövdesinde geçen kelime değil.

AKSİYOM ANALİZİ (sorry_analyzer deseni, --analyze-axioms / --json):
Lean'in `#print axioms <name>` çıktısından her teoremin aksiyom
bağımlılıklarını toplar ve "standart aksiyomlar dışında aksiyom yok"
satırını üretir (K9 çıktı zenginleştirmesi). Standart set — Lean 4 çekirdek
aksiyomları (propext/funext/Classical.choice/Quot.sound) — dışındaki herhangi
bir aksiyom kullanıcı tanımlıdır ve fail-closed bulgudur. Analiz `lean
<dosya + #print axioms>` ile çalışır; lean yoksa SKIP (None) — statik
sorry/axiom taramasından BAĞIMSIZDIR.

Exit: 0 = temiz / 1 = bulgu (fail-closed) / 2 = hata (dizin yok vb.).

Kullanım:
    python3 check_lean_axioms.py [--lean-dir DIR] [--json] [--exit-0]
                                 [--analyze-axioms] [--lean-bin PATH]

    --lean-dir        taranacak dizin (vars. script'in ../lean_reduct)
    --json            makine-okunur {ok, findings:[{file,line,kind,snippet}]}
    --exit-0          bulgu olsa bile exit 0 (advisory; varsayılan fail-closed)
    --analyze-axioms  #print axioms analizi ekle (standart dışı aksiyom bulgusu)
    --lean-bin        lean derleyici yolu (vars. PATH'ten `lean`)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEAN_DIR = os.path.normpath(os.path.join(HERE, "..", "lean_reduct"))

# Lean 4 çekirdek aksiyomları — "standart" sayılır (kullanıcı tanımlı değil).
# `#print axioms` çıktısındaki tam adlar: propext, funext, Classical.choice,
# Quot.sound (+ ayrıca sorry kullanımı sorryAx üretir — zaten K9-AXIOM yakalar).
STANDARD_AXIOMS = {"propext", "funext", "Classical.choice", "Quot.sound"}

_AXIOMS_DEPENDS_RE = re.compile(r"'([^']+)' depends on axioms: \[(.*)\]")
_AXIOMS_NONE_RE = re.compile(r"'([^']+)' does not depend on any axioms")

# Kelime sınırlı "sorry" (admit/boşluk ispatı). Lean'de `sorry` bir term'dir —
# yorum/string dışında geçmesi ispat boşluğudur.
_SORRY_RE = re.compile(r"\bsorry\b")
# Top-level axiom bildirimi: satır başında yalnızca boşluk, sonra `axiom`.
# (Lean 4'te `axiom` yalnızca top-level komuttur; `example`/`theorem` gövdesi
# ayrı satırda `axiom` ile başlayamaz — bu regex gerçek bildirimleri yakalar.)
_AXIOM_RE = re.compile(r"^\s*axiom\b")
_STRING_RE = re.compile(r'"[^"\n]*"')
_LINE_COMMENT_RE = re.compile(r"--")


def strip_comments_and_strings(text):
    """Yorumları/string'leri boşlukla değiştirip tarama için temiz metin üretir.

    Blok yorumlar (`/- ... -/`) çok satırlı olabilir; string maskeleme satır
    satır yapılır (blok yorum içindeki string'ler zaten yorum olarak atlanır).
    Döndürür: (temiz_satırlar: list[str]) — satır numarası korunur.
    """
    lines = text.splitlines()
    clean = []
    in_block = False
    for ln in lines:
        # Blok yorum durumu: açıkken satırı boşalt; `-/` kapanana dek.
        if in_block:
            idx = ln.find("-/")
            if idx == -1:
                clean.append("")
                continue
            ln = ln[idx + 2:]
            in_block = False
        # Satır içinde blok yorum açılışı — kapanana dek gerisini boşalt.
        while True:
            open_idx = ln.find("/-")
            if open_idx == -1:
                break
            close_idx = ln.find("-/", open_idx + 2)
            if close_idx == -1:
                # Açık blok kapanmadı — kalan satırları yut.
                ln = ln[:open_idx]
                in_block = True
                break
            ln = ln[:open_idx] + " " + ln[close_idx + 2:]
        # String literal'leri maskele (blok yorum çıkarıldıktan SONRA).
        ln = _STRING_RE.sub('""', ln)
        # Satır yorumunu kes.
        ln = _LINE_COMMENT_RE.split(ln, 1)[0]
        clean.append(ln)
    return clean


def scan_lean_dir(lean_dir):
    """Dizindeki tüm .lean kaynaklarını tara.

    Döndürür: (ok: bool, findings: list[dict]) — findings her bulgu için
    {file, line, kind, snippet}. `.lake` build dizini hariç tutulur.
    """
    if not os.path.isdir(lean_dir):
        return False, []
    findings = []
    for dirpath, dirnames, filenames in os.walk(lean_dir):
        dirnames[:] = [d for d in dirnames if d != ".lake"]
        for fn in sorted(filenames):
            if not fn.endswith(".lean"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, lean_dir)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                findings.append({"file": rel, "line": 0, "kind": "hata",
                                 "snippet": str(e)})
                continue
            for lineno, ln in enumerate(strip_comments_and_strings(text), 1):
                m = _SORRY_RE.search(ln)
                if m:
                    findings.append({"file": rel, "line": lineno,
                                     "kind": "sorry",
                                     "snippet": ln.strip()[:120]})
                    continue
                if _AXIOM_RE.match(ln):
                    findings.append({"file": rel, "line": lineno,
                                     "kind": "axiom",
                                     "snippet": ln.strip()[:120]})
    return not findings, findings


def parse_axioms_output(text):
    """`lean <file>` çıktısındaki `#print axioms` satırlarını ayrıştırır.

    Döndürür: {teorem_adı: [aksiyom_adları]} — aksiyomsuz teoremler boş liste.
    Çıktı formatı (Lean 4):
        'foo' does not depend on any axioms
        'bar' depends on axioms: [propext, Classical.choice]
    """
    deps = {}
    for ln in text.splitlines():
        m = _AXIOMS_DEPENDS_RE.match(ln.strip())
        if m:
            name = m.group(1)
            axioms = [a.strip() for a in m.group(2).split(",") if a.strip()]
            deps[name] = axioms
            continue
        m = _AXIOMS_NONE_RE.match(ln.strip())
        if m:
            deps[m.group(1)] = []
    return deps


def classify_axioms(deps):
    """Teorem→aksiyom sözlüğünü standart dışı aksiyomlara göre sınıflandırır.

    Döndürür: (ok: bool, non_standard: list[dict]) — non_standard her kayıt
    {theorem, axioms:[standart dışı]} ; boşsa (True, []).
    """
    non_standard = []
    for name in sorted(deps):
        extra = [a for a in deps[name] if a not in STANDARD_AXIOMS]
        if extra:
            non_standard.append({"theorem": name, "axioms": extra})
    return not non_standard, non_standard


def analyze_axioms(lean_dir, lean_bin="lean"):
    """Dizindeki tüm .lean dosyalarının aksiyom bağımlılıklarını analiz eder.

    Her dosyanın sonuna `#print axioms <teorem>` satırları ekleyip `lean` ile
    çalıştırır (geçici kopya — kaynağa dokunmaz). Döndürür:
        (state, detail)
    state: "PASS" (standart dışı yok) / "FAIL" (standart dışı var) /
           "SKIP" (lean yok veya çalışmadı) ; detail her dosya için
           "standart aksiyomlar dışında aksiyom yok" ya da bulgu listesi.
    """
    lean_cmd = shutil.which(lean_bin) or lean_bin
    if not os.path.isfile(lean_cmd) and shutil.which(lean_bin) is None:
        return "SKIP", "lean bulunamadı — aksiyom analizi atlandı"
    details = []
    all_non = []
    for dirpath, dirnames, filenames in os.walk(lean_dir):
        dirnames[:] = [d for d in dirnames if d != ".lake"]
        for fn in sorted(filenames):
            if not fn.endswith(".lean"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, lean_dir)
            try:
                with open(path, encoding="utf-8") as f:
                    src = f.read()
            except OSError as e:
                details.append(f"{rel}: okunamadı ({e})")
                continue
            # Teorem adlarını topla (imza çıkarımı deseninde).
            names = []
            for ln in src.splitlines():
                m = re.match(r"^\s*theorem\s+([A-Za-z0-9_]+)\b", ln)
                if m:
                    names.append(m.group(1))
            if not names:
                details.append(f"{rel}: teorem yok (atlandı)")
                continue
            probe = src + "\n" + "\n".join(
                f"#print axioms {n}" for n in names) + "\n"
            try:
                r = subprocess.run([lean_cmd, "-"], input=probe,
                                   capture_output=True, text=True, timeout=120)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                details.append(f"{rel}: lean çalışmadı (atlandı)")
                continue
            deps = parse_axioms_output((r.stdout or "") + (r.stderr or ""))
            ok, non = classify_axioms(deps)
            if ok:
                details.append(f"{rel}: standart aksiyomlar dışında aksiyom yok")
            else:
                for rec in non:
                    all_non.append({"file": rel, **rec})
                details.append(f"{rel}: standart dışı aksiyom: "
                              + "; ".join(f"{r['theorem']}→{','.join(r['axioms'])}"
                                           for r in non))
    if all_non:
        return "FAIL", "; ".join(details)
    return "PASS", "; ".join(details)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lean-dir", default=DEFAULT_LEAN_DIR)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--exit-0", action="store_true",
                    help="bulgu olsa bile exit 0 (advisory; varsayılan fail-closed)")
    ap.add_argument("--analyze-axioms", action="store_true",
                    help="#print axioms analizi ekle (standart dışı aksiyom bulgusu)")
    ap.add_argument("--lean-bin", default="lean")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.lean_dir):
        print(f"HATA: lean dizini yok: {args.lean_dir}", file=sys.stderr)
        return 2

    ok, findings = scan_lean_dir(args.lean_dir)
    ax_state = None
    ax_detail = None
    if args.analyze_axioms:
        ax_state, ax_detail = analyze_axioms(args.lean_dir, args.lean_bin)
        if ax_state == "FAIL":
            findings.append({"file": "*", "line": 0,
                             "kind": "axioms", "snippet": ax_detail})
    if args.json:
        print(json.dumps({"ok": ok and ax_state != "FAIL",
                          "findings": findings,
                          "axiom_state": ax_state,
                          "axiom_detail": ax_detail,
                          "lean_dir": args.lean_dir}, ensure_ascii=False))
    else:
        print(f"check-lean-axioms: {args.lean_dir}")
        for f in findings:
            print(f"  {f['kind'].upper()} {f['file']}:{f['line']} — {f['snippet']}")
        if ax_state == "PASS":
            print("AKSİYOM: standart aksiyomlar dışında aksiyom yok")
        elif ax_state == "FAIL":
            print(f"AKSİYOM: {ax_detail}")
        elif ax_state == "SKIP":
            print(f"AKSİYOM: atlandı ({ax_detail})")
        if findings:
            print(f"SONUÇ: {len(findings)} bulgu (sorry/axiom/standart dışı aksiyom) — fail-closed")
        else:
            print("SONUÇ: temiz — sorry/axiom yok")
    if findings and not args.exit_0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
