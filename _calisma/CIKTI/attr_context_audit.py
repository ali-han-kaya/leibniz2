#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attr_context_audit.py — nitelik bağlamı kaçırma denetimi (havuz tabanlı).

Havuz: `git ls-files` ile izlenen, HTML üreten kaynaklar (`*.html`, `*.js`,
`*.ts`, `*.tsx`; vendor/derleme çıktısı hariç). Dosya listesi elle tutulmaz:
yeni izli bir şablon dosyası kendiliğinden havuza girer.

Kurallar (fail-closed):

  R1  Ham HTML sink'i yok: TS/TSX'te `dangerouslySetInnerHTML`,
      `insertAdjacentHTML`, `outerHTML =`, `document.write`. JSX metni ve
      niteliği zaten kaçırır; ham sink ancak bilerek eklenir ve burada görünür.
      JS/HTML'deki `innerHTML =` atamaları envanterlenir (sayılır).

  R2  Nitelik değerindeki her `${ifade}` BASELINE'da gözden geçirilmiş
      olmalı. Gözden geçirme sınıfları:
        ESCAPED  — `escapeHTML(...)` ile kaçırılmış veri;
        NUMERIC  — sayısal geometri (SVG koordinatı, genişlik); şekli
                   otomatik doğrulanır (yalnız sayı, aritmetik, `.toFixed`);
        CONSTANT — sabit palet/harita değeri; tanım satırı PIN olarak
                   bağlanır, değişirse kapı kırılır.
      Baseline'da olmayan ifade → R2-UNREVIEWED (bilinmeyen = güvensiz).
      Baseline'da olup dosyada artık geçmeyen giriş → R2-STALE (kayıt
      çürümesin). Pin'li giriş dosyada pin'i kaybederse → R2-PIN.

Sınırlar: R2 satır-içi nitelik bağlamına bakar; çok satıra yayılan şablon
nitelikleri taranmaz. Baseline insan incelemesi gerektirir; bir ifadenin
ilk kez gelmesi kapıyı kapatır, otomatik onaylamaz.

Çalıştırma:
  python3 attr_context_audit.py          # PASS/FAIL, çıkış 0 = temiz
  python3 attr_context_audit.py --json   # makine-okunur rapor
  python3 attr_context_audit.py --list   # nitelik ifadeleri (baseline için)
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

EXCLUDE_PARTS = ("vendor/", "node_modules/", "dist/", ".next/", ".venv",
                 "build/", ".min.js")
SCAN_SUFFIXES = (".html", ".js", ".ts", ".tsx")
RAW_SINK_RE = re.compile(
    r"dangerouslySetInnerHTML|insertAdjacentHTML|outerHTML\s*=(?!=)"
    r"|document\.write\s*\(")
INNER_HTML_ASSIGN_RE = re.compile(r"\binnerHTML\s*=(?!=)")
# Nitelik adı + `=` + (isteğe bağlı kaçış) + açılış tırnağı.
ATTR_OPEN_RE = re.compile(r"([A-Za-z_:][-\w:.]*)\s*=\s*\\?\"")
ESCAPED_RE = re.compile(r"escapeHTML\(.*\)")
NUMERIC_RE = re.compile(r"[\w\s\.\(\),\+\-\*/%]+(?:\.toFixed\(\d+\))?")

# ---------------------------------------------------------------- baseline
# (dosya, ifade) -> gözden geçirme. "pin": dosyada aranan TAM satır parçası.
# Her giriş bir insan incelemesidir; ifade değişirse kapı kırılır.
P = "_calisma/CIKTI/preview.js"

# Biçimi sınanan sayısal ifadeler (NUMERIC: yalnız sayı/aritmetik/.toFixed).
_NUMERIC_EXPRS = [
    "(cx - halfW).toFixed(2)", "(halfW * 2).toFixed(2)",
    "(rHalfW * 2).toFixed(2)", "(x(i) - rHalfW).toFixed(2)",
    "(y(ti) - hc / 2).toFixed(2)", "H - 12", "H / 2", "W / 2",
    "PL - 6", "PL - 8", "PT + 4", "PT + ih", "PT + ih + 2",
    "budAxisX + 6", "durAxisX + 6", "leanAxisX + 6", "zAxisX + 6",
    "cx - 3", "cx0.toFixed(2)", "hc.toFixed(2)", "wCell.toFixed(2)",
    "gy + 4", "limitY - 3", "ly - 3", "yy - 3", "y(ti) + 4",
    "x(i)", "x(i) - 3", "x.toFixed(1)", "xAt(i - 1, n).toFixed(1)",
    "xAt(i, n).toFixed(1)", "y(r.refs_verified)",
]
# Koordinat listeleri: `rows.map(... `${x(i)},${y}`)` ile üretilir.
_JOIN_LISTS = [
    'budPts.join(" ")', 'durPts.join(" ")', 'stepPts.join(" ")',
    'leanPts.join(" ")', 'zPassPts.join(" ")', 'zFailPts.join(" ")',
    'pts.join(" ")',
]

BASELINE = {}
for _e in _NUMERIC_EXPRS:
    BASELINE[(P, _e)] = {"class": "NUMERIC", "reason": "sayısal geometri"}
for _e in _JOIN_LISTS:
    BASELINE[(P, _e)] = {"class": "NUMERIC",
                         "reason": "sayısal koordinat listesi"}

# Tek tanımlayıcılar: ya yerleşim/indeks sabiti (pin yok, gözden geçirildi)
# ya da tanım satırına PIN'li (dosyada kalmalı) kaçırılmış/sabit değer.
BASELINE.update({
    (P, "PL"): {"class": "NUMERIC", "reason": "yerleşim sabiti (çok-tanımlı const)"},
    (P, "PT"): {"class": "NUMERIC", "reason": "yerleşim sabiti (çok-tanımlı const)"},
    (P, "ih"): {"class": "NUMERIC", "reason": "yerleşim yüksekliği"},
    (P, "i"): {"class": "NUMERIC", "reason": "döngü indeksi"},
    (P, "gy"): {"class": "NUMERIC", "reason": "y-ekseni konumu",
               "pin": "const gy = yP(g);"},
    (P, "cx"): {"class": "NUMERIC", "reason": "x-konumu",
               "pin": "const cx = x(i);"},
    (P, "ly"): {"class": "NUMERIC", "reason": "y-konumu",
               "pin": "const ly = yL(leans[i]);"},
    (P, "plotRight"): {"class": "NUMERIC", "reason": "eksen sağ kenarı",
                     "pin": "const plotRight = PL + iw;"},
    (P, "budAxisX"): {"class": "NUMERIC", "reason": "eksen konumu",
                    "pin": "const budAxisX = plotRight + 88;"},
    (P, "durAxisX"): {"class": "NUMERIC", "reason": "eksen konumu",
                    "pin": "const durAxisX = plotRight + 26;"},
    (P, "zAxisX"): {"class": "NUMERIC", "reason": "eksen konumu",
                  "pin": "const zAxisX = plotRight + 150;"},
    (P, "leanAxisX"): {"class": "NUMERIC", "reason": "eksen konumu",
                     "pin": "const leanAxisX = plotRight + 192;"},
    (P, "limitY"): {"class": "NUMERIC", "reason": "bütçe çizgisi konumu",
                  "pin": "const limitY = offScale ? PT + 3 : rawLimitY;"},
    (P, "pts"): {"class": "NUMERIC", "reason": "areaPts çifti (x(i),y(v)) sayı dizgisi",
                "pin": "const areaPts = (vals) => vals.map((v, i) => `${x(i)},${y(v)}`).join(\" \");"},
    (P, "tag"): {"class": "CONSTANT", "reason": "durum rozet sınıfı (sabit dize)",
               "pin": 'const tag = r.tag === "OK" ? "ok" : r.tag === "FAIL" ? "err" : "warn";'},
    (P, "c"): {"class": "CONSTANT", "reason": "sabit palet seçimi",
             "pin": 'const c = r.p0 > 0 ? "#f85149" : r.p1 > 0 ? "#d29922" : "#3fb950";'},
    (P, "color"): {"class": "CONSTANT", "reason": "sabit palet/harita (birden çok tanım)",
                "pin": 'const color = SRC_COLORS[s] || "#8b949e";'},
    (P, "cls"): {"class": "CONSTANT", "reason": "sabit sınıf dizgisi (çok tanım)",
               "pin": ': sv === "FAIL" || sv === "ERROR"'},
    (P, "tsAttr"): {"class": "ESCAPED", "reason": "escapeHTML ile kaçırılmış ts",
                 "pin": 'const tsAttr = r.ts ? escapeHTML(r.ts) : "";'},
    (P, "srcBadge"): {"class": "ESCAPED", "reason": "escapeHTML ile kaçırılmış kaynak",
                  "pin": 'const srcBadge = escapeHTML(r.source || "daemon");'},
    (P, "ld"): {"class": "ESCAPED", "reason": "escapeHTML ile kaçırılmış lean ayrıntısı",
             "pin": 'const ld = r.lean_detail ? " — " + escapeHTML(r.lean_detail) : "";'},
    (P, "fmtLimit(BUDGET_LIMIT)"): {"class": "REVIEWED",
                                  "reason": "fmtLimit yalnız rakam veya '—' döner"},
    (P, "r.budget_usd.toFixed(2)"): {"class": "REVIEWED",
                                    "reason": "toFixed çıktısı sayısal dize"},
    (P, "yP(Math.max(r.p0 || 0, r.p1 || 0))"): {"class": "REVIEWED",
                                              "reason": "y-konumu (sayısal)"},
    (P, "SRC_COLORS[s] || \"#8b949e\""): {"class": "CONSTANT",
                                         "reason": "sabit harita + sabit yedek"},
    (P, "full ? \"#3fb950\" : \"#d29922\""): {"class": "CONSTANT",
                                            "reason": "sabit ternary"},
})

BASELINE_DOC = (
    "Tek tanımlayıcılar ve karmaşık ifadeler elle gözden geçirildi; "
    "pin'li olanlar tanım satırının dosyada kalmasını zorlar.")


def pool(repo=REPO):
    """Git'e izli kaynak dosyaları (repo-göreli)."""
    out = subprocess.run(["git", "ls-files"], cwd=str(repo),
                         capture_output=True, text=True, check=True).stdout
    return [rel for rel in out.splitlines()
            if rel.endswith(SCAN_SUFFIXES)
            and not any(p in rel for p in EXCLUDE_PARTS)]


def expr_span(line, start):
    """`${` sonrasından eşleşen `}` konumuna kadar ifadeyi döndür."""
    depth, i = 1, start
    while i < len(line):
        c = line[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return line[start:i], i
        i += 1
    return None, None


def in_attribute(prefix):
    """Önek bir nitelik değeri içinde açık mı? Dönüş: nitelik adı veya None."""
    last = None
    for m in ATTR_OPEN_RE.finditer(prefix):
        last = m
    if last is None:
        return None
    if re.search(r"\\?\"", prefix[last.end():]):  # tırnak kapanmış → metin
        return None
    return last.group(1)


def scan_text(rel, text):
    """Tek dosya: (innerHTML sayısı, R1 bulguları, nitelik ifadeleri)."""
    suffix = pathlib.Path(rel).suffix
    inner = 0
    raw, hits = [], []
    for ln, line in enumerate(text.splitlines(), 1):
        if suffix in (".ts", ".tsx") and RAW_SINK_RE.search(line):
            raw.append({"file": rel, "line": ln, "kind": "R1-sink",
                        "detail": line.strip()[:120]})
        if suffix in (".js", ".html") and INNER_HTML_ASSIGN_RE.search(line):
            inner += 1
        if suffix not in (".js", ".html") or "${" not in line:
            continue
        pos = 0
        while True:
            idx = line.find("${", pos)
            if idx < 0:
                break
            expr, end = expr_span(line, idx + 2)
            if expr is None:
                break
            attr = in_attribute(line[:idx])
            if attr is not None:
                hits.append({"file": rel, "line": ln, "attr": attr,
                             "expr": expr.strip()})
            pos = end + 1
    return inner, raw, hits


def audit(repo=REPO, baseline=None):
    """Havuzu tara. Dönüş: (envanter, bulgular, nitelik ifadeleri)."""
    base = BASELINE if baseline is None else baseline
    inventory = {"files": 0, "by_suffix": collections.Counter(),
                 "innerHTML_sites": 0, "attr_sites": 0}
    findings, all_hits = [], []
    for rel in pool(repo):
        inventory["files"] += 1
        inventory["by_suffix"][pathlib.Path(rel).suffix] += 1
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append({"file": rel, "line": 0, "kind": "READ-ERROR",
                             "detail": str(exc)})
            continue
        inner, raw, hits = scan_text(rel, text)
        inventory["innerHTML_sites"] += inner
        findings.extend(raw)
        for h in hits:
            all_hits.append(h)
            inventory["attr_sites"] += 1
            key = (h["file"], h["expr"])
            if key not in base:
                findings.append({"file": rel, "line": h["line"],
                                 "kind": "R2-UNREVIEWED", "attr": h["attr"],
                                 "expr": h["expr"],
                                 "detail": "gözden geçirilmemiş ifade"})
    used = {(h["file"], h["expr"]) for h in all_hits}
    for key, entry in base.items():
        if key not in used:
            findings.append({"file": key[0], "line": 0, "kind": "R2-STALE",
                             "expr": key[1],
                             "detail": "baseline girişi artık yok"})
    findings.extend(check_entries(repo, base))
    inventory["by_suffix"] = dict(inventory["by_suffix"])
    return inventory, findings, all_hits


def check_entries(repo, base):
    """Sınıf ile ifade şekli uyuşmalı; pin'li girişler dosyada geçmeli."""
    out = []
    for (rel, expr), entry in base.items():
        cls = entry.get("class")
        is_ident = re.fullmatch(r"\w+", expr) is not None
        if cls == "ESCAPED" and not is_ident and not ESCAPED_RE.fullmatch(expr):
            out.append({"file": rel, "line": 0, "kind": "R2-CLASS",
                        "expr": expr, "detail": "ESCAPED ama escapeHTML değil"})
        if cls == "ESCAPED" and is_ident and not entry.get("pin"):
            out.append({"file": rel, "line": 0, "kind": "R2-CLASS",
                        "expr": expr, "detail": "ESCAPED tanımlayıcı pin ister"})
        if cls == "NUMERIC" and not NUMERIC_RE.fullmatch(
                re.sub(r'\.join\(" "\)', "", expr)):
            out.append({"file": rel, "line": 0, "kind": "R2-CLASS",
                        "expr": expr, "detail": "NUMERIC ama sayısal değil"})
        pin = entry.get("pin")
        if pin:
            try:
                text = (repo / rel).read_text(encoding="utf-8")
            except OSError:
                text = ""
            if pin not in text:
                out.append({"file": rel, "line": 0, "kind": "R2-PIN",
                            "expr": expr,
                            "detail": "pin kayboldu: %s" % pin[:80]})
    return out


def main(argv):
    if "--list" in argv:
        _, _, hits = audit()
        counts = collections.Counter((h["file"], h["expr"]) for h in hits)
        for (rel, expr), n in sorted(counts.items()):
            print("%4d  %s  |  %s" % (n, rel, expr))
        return 0
    inventory, findings, _ = audit()
    if "--json" in argv:
        json.dump({"inventory": inventory, "findings": findings},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print("havuz: %d dosya %s, innerHTML atamaları: %d, "
              "nitelik enterpolasyonları: %d" % (
                  inventory["files"], inventory["by_suffix"],
                  inventory["innerHTML_sites"], inventory["attr_sites"]))
        for f in findings:
            print("  %(kind)s %(file)s:%(line)s %(detail)s" % {
                **f, "line": f.get("line", 0),
                "detail": f.get("detail", "")} + (
                    "  [%s]" % f["expr"] if f.get("expr") else ""))
    verdict = "PASS" if not findings else "FAIL"
    print("attr-context-audit: %s (%d bulgu)" % (verdict, len(findings)),
          file=sys.stderr)
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
