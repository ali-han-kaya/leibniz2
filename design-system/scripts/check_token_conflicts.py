#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_token_conflicts.py — token DRIFT + ÇAKIŞMA kapısı (fail-closed).

Neden: design-system'de katman başına drift kapıları var
(check_tokens.py contract 1-9, check_<marka>_tokens.py, check_mirror_bridges.py,
report_vercel_dashboard_drift.py) ama KATMANLAR ARASI çakışmayı ve
KOPYA katmanların sessiz kaymasını ölçen tek bir kapı yoktu. Ölçülen boşluklar:

  * Aynı ad iki dosyada aynı kapsamda FARKLI değerle tanımlıysa (ör. kanonik
    `:root` başka bir katmanda yeniden yazılırsa) kazananı IMPORT SIRASI
    belirler — hiçbir kapı bunu görmez (sessiz tema kayması).
  * Bir dosyada aynı blokta aynı ad iki kez FARKLI değerle geçerse sonuncusu
    sessizce kazanır.
  * `_calisma/landing/landing.html` kanonik paletin ÜRETİLMİŞ kopyasıdır ve
    bağımsız bir kapıya bağlı DEĞİLDİR: tokens.css değişip landing yeniden
    üretilmezse landing sessizce eski paleti gösterir (kanıt: bugün 106/106
    birebir — ama bunu hiçbir kapı çivilemiyordu).
  * Yeni bir token dosyası açmak hiçbir kapıyı kırmaz (kapsam sessizce daralır).

Sözleşmeler (hepsi fail-closed; roller design-system/scripts/token_layers.list):
  K1 BLOK-İÇİ TEKRAR : aynı dosya+kapsam+ad, >1 FARKLI değer → sonuncusu
                        sessizce kazanır.
  K2 KATMAN ÇAKIŞMASI: design-system biriminde (canonical|bridge|variant) aynı
                        kapsam+ad, ≥2 dosyada ve değerler FARKLI → import
                        sırası kazananı belirler. AYNI değer serbesttir
                        (üretilmiş kopyalar böyle çalışır).
  K3 VARYANT KAPSAMI : `variant` katmanı yalnız kendi
                        `:root[data-theme="<marka>"]` kapsamında tanım yapar.
  K4 KOPYA DRIFT     : `copy` katmanının :root + light kümeleri kanonik
                        (design-system/tokens.css) kümeleriyle ad/adet/değer
                        olarak BİREBİR olmalı.
  K5 KAYITSIZ KATMAN : token tanımlayan her dosya roster'da ya da gerekçeli
                        `capture` satırında olmalı; roster'ın hiçbir dosyaya
                        uymayan satırı da ölüdür (iki yönlü kapsam kapısı).
  K6 TÜKETİCİ GÖLGESİ: `consumer` katmanı çıplak `:root`ta kendi yuva
                        eşlemesini kurabilir, ama KANONİK katmanın tanımladığı
                        bir adı FARKLI değerle yeniden yazamaz (kazananı
                        stil-dosyası sırası belirler = sessiz tema kayması).
                        Aynı değerle tanımlamak bulgu değildir.

Fail-closed ölçüm: roster yok/bozuk, kanonik referans kayıtlı değil ya da tarama
kümesi boşsa rc=2 (kör kapı PASS üretmez).

Exit: 0 = çakışma/drift yok, 1 = bulgu var, 2 = kullanım/ölçüm hatası.
--json : stdout TEK JSON belgesi (teşhis satırları stderr'e).
--md-out PATH : insan-okunur rapor yazar.
--list : çözülen katman tablosunu basar (roster/glob teşhisi).

OFFLINE, READ-ONLY, stdlib-only (~0,1s; 10 katman / 5.103 tanım).
"""
import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ROSTER = HERE / "token_layers.list"
CANONICAL_PATH = "design-system/tokens.css"
SCAN_DIRS = ("design-system",)
SCAN_FILES = ("apps/dashboard-next/app/globals.css",
              "_calisma/CIKTI/preview.html")
SCAN_GLOBS = ("_calisma/landing/*.html",)
UNIT_ROLES = ("canonical", "bridge", "variant")   # birlikte yüklenebilir birim
ROLES = ("canonical", "bridge", "variant", "consumer", "copy", "capture")
CONDITIONAL_AT = ("@media", "@supports", "@container", "@layer", "@scope")

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
PAIR_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
THEME_SEL_RE = re.compile(r'^:root\[data-theme="([\w-]+)"\]$')

FINDING_RULES = ("K1", "K2", "K3", "K4", "K5", "K6")


# ── ayrıştırma ────────────────────────────────────────────────────────────
def strip_comments(text):
    return COMMENT_RE.sub("", text)


def _matching_brace(text, start):
    """`{` konumundan eşleşen `}` konumunu bul — sadece parantez derinliği.

    TIRNAK İZLENMEZ (bilinçli): `url("data:image/svg+xml;…")` içindeki
    kaçışsız tırnaklar (primer/tokens.css:16757) tırnak-durumu izleyen bir
    tarayıcıyı blok dışında bırakır ve kapı ölçemez hale gelirdi. Gerçek
    korunma, ayrıştırma sonrası `scan_file` içindeki mutabakat: parse edilen
    (ad, değer) çoklu-kümesi, metnin tamamındaki `--x: …;` çiftleriyle
    BİREBİR eşit olmalı; değilse ölçüm hatası (rc=2) — sessiz PASS yok.
    """
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise MeasurementError("kapanmayan blok: %d. karakter" % start)


def _norm_sel(sel):
    return re.sub(r"\s+", " ", sel).strip()


def _scope_name(sel):
    s = sel.replace(" ", "")
    if s == ":root":
        return "global"
    m = THEME_SEL_RE.match(s)
    if m:
        return "theme:" + m.group(1)
    return "rule:" + sel[:60]


def _join(prefix, name):
    return name if not prefix else "%s > %s" % (prefix, name)


def _pairs(body):
    return [(m.group(1), re.sub(r"\s+", " ", m.group(2)).strip())
            for m in PAIR_RE.finditer(body)]


def parse_blocks(text, prefix=""):
    """Blok ağacını gez → [(kapsam, [(ad, değer), …])].

    Koşullu at-kuralları (@media/@supports/@layer/@container/@scope) iç içe
    geçilir ve kapsam `at:… > …` olarak zincirlenir; `@theme`/`@theme inline`
    kendi kapsamıdır (deklarasyon taşır), diğer at-kurallar da deklarasyon
    taşıyorsa `at:<prelude>` kapsamı olarak raporlanır.
    """
    out = []
    text = strip_comments(text)
    i, prelude, n = 0, "", len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            end = _matching_brace(text, i)
            body = text[i + 1:end]
            raw = _norm_sel(prelude)
            if raw.startswith(CONDITIONAL_AT):
                out.extend(parse_blocks(body, _join(prefix, "at:" + raw)))
            elif raw:
                scope = _join(prefix, "at:" + raw if raw.startswith("@")
                              else _scope_name(raw))
                decls = _pairs(body)
                if decls:
                    out.append((scope, decls))
            prelude = ""
            i = end + 1
        elif ch == "}":
            i += 1
        elif ch == ";":
            prelude = ""
            i += 1
        else:
            prelude += ch
            i += 1
    return out


class MeasurementError(Exception):
    """Ayrıştırma/ölçüm güvenilmez — kör kapı PASS üretmemelidir (rc=2)."""


def read_style_text(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        return "\n".join(m.group(1) for m in STYLE_RE.finditer(text))
    return text


def count_definitions(path):
    """Metindeki `--x: …;` çifti sayısı (yapısal ayrıştırma YOK).

    Kayıt denetimi (K5) yapı bilgisine ihtiyaç duymaz; ham yakalamalarda
    (`linear/raw.css` gibi tire/kaçış yoğun dosyalar) blok ayrıştırması
    güvenilmez olabilir — orada yalnız "token tanımlıyor mu" sorusu sorulur.
    """
    return len(list(PAIR_RE.finditer(strip_comments(read_style_text(path)))))


def scan_file(path):
    """(kapsam, ad, değer) üçlüleri + mutabakat denetimi.

    Ayrıştırıcı ile metnin tamamı aynı çift kümesini görmeli: kapsam ataması
    yanlış olsa bile (K1-K6 bundan etkilenir) bir tanım KAYBOLAMAZ.
    """
    text = read_style_text(path)
    rows = []
    for scope, decls in parse_blocks(text):
        for name, value in decls:
            rows.append((scope, name, value))
    plain = strip_comments(text)
    want = sorted((m.group(1), re.sub(r"\s+", " ", m.group(2)).strip())
                  for m in PAIR_RE.finditer(plain))
    got = sorted((name, value) for _, name, value in rows)
    if want != got:
        raise MeasurementError(
            "%s: ayrıştırılan %d tanım, metindeki %d tanımla uyuşmuyor "
            "(kapsam ataması güvenilmez)" % (path, len(got), len(want)))
    return rows


# ── roster ────────────────────────────────────────────────────────────────
class RosterError(Exception):
    pass


def parse_roster(text):
    entries = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise RosterError("%d. satır eksik: %r" % (lineno, raw))
        role, pattern = parts[0], parts[1]
        reason = " ".join(parts[2:])
        if role not in ROLES:
            raise RosterError("%d. satır bilinmeyen rol: %r" % (lineno, role))
        if role == "capture" and not reason:
            raise RosterError("%d. satır: capture satırı gerekçesiz" % lineno)
        entries.append({"role": role, "pattern": pattern, "reason": reason,
                        "line": lineno, "hits": []})
    if not entries:
        raise RosterError("roster boş")
    return entries


def resolve_role(entries, rel):
    for entry in entries:
        if fnmatch.fnmatchcase(rel, entry["pattern"]):
            return entry
    return None


def surface_files():
    files = set()
    for base in SCAN_DIRS:
        files.update((REPO / base).rglob("*.css"))
    for rel in SCAN_FILES:
        p = REPO / rel
        if p.is_file():
            files.add(p)
    for pattern in SCAN_GLOBS:
        files.update(REPO.glob(pattern))
    return sorted(files)


def rel_of(path):
    return str(path.relative_to(REPO))


# ── denetimler ────────────────────────────────────────────────────────────
def finding(rule, detail, **kw):
    rec = {"rule": rule, "severity": "block", "detail": detail}
    rec.update(kw)
    return rec


def check_intra_block(rel, rows, findings):
    seen = {}
    for scope, name, value in rows:
        seen.setdefault((scope, name), set()).add(value)
    for (scope, name), values in sorted(seen.items()):
        if len(values) > 1:
            findings.append(finding(
                "K1", "aynı blokta %d farklı değer (sonuncusu sessizce kazanır)"
                % len(values), file=rel, scope=scope, name=name,
                values=sorted(values)))


def check_cross_layer(per_file, findings):
    """per_file: {rel: rows} — yalnız UNIT_ROLES dosyaları."""
    owners = {}
    for rel, rows in per_file.items():
        for scope, name, value in rows:
            owners.setdefault((scope, name), {}).setdefault(rel, set()).add(value)
    for (scope, name), files in sorted(owners.items()):
        if len(files) < 2:
            continue
        values = {v for vs in files.values() for v in vs}
        if len(values) > 1:
            findings.append(finding(
                "K2", "%d katman aynı kapsamda FARKLI değer tanımlıyor — "
                "kazananı import sırası belirler" % len(files),
                scope=scope, name=name,
                layers={f: sorted(v) for f, v in sorted(files.items())}))


def check_consumer(rel, rows, canon_rows, findings):
    """K6 — tüketici, kanonik bir adı çıplak :root'ta FARKLI değerle gölgeleyemez.

    Tüketici kendi yuva eşlemesini :root'ta kurabilir (globals.css'te
    `--background: var(--bg)` gibi 29 shadcn yuvası); yasak olan, kanonik
    katmanın TANIMLADIĞI bir adı farklı bir değerle yeniden yazmaktır —
    o zaman kazananı stil dosyası sırası belirler (sessiz tema kayması).
    Aynı ad + AYNI değer bulgu değildir (tutarlı kopya).
    """
    canon = {name: value for scope, name, value in canon_rows
             if scope == "global"}
    clash = {}
    for scope, name, value in rows:
        if scope == "global" and name in canon and canon[name] != value:
            clash[name] = {"kanonik": canon[name], "tüketici": value}
    if clash:
        findings.append(finding(
            "K6", "tüketici %d kanonik token'ı farklı değerle gölgeliyor "
            "(kanonik katmanı yeniden yazıyor)" % len(clash),
            file=rel, differing=dict(sorted(clash.items())[:8])))


def check_variant_scope(rel, rows, brand, findings):
    for scope, name, _ in rows:
        if scope != "theme:" + brand:
            findings.append(finding(
                "K3", "varyant yalnız :root[data-theme=\"%s\"] içinde tanım "
                "yapabilir (bulunan kapsam: %s)" % (brand, scope),
                file=rel, scope=scope, name=name))


def check_copy(reference, rel, rows, findings):
    """copy katmanı kanonik :root + light kümelerinin birebir kopyası olmalı."""
    def sets(rows_):
        out = {}
        for scope, name, value in rows_:
            if scope in ("global", "theme:light"):
                out[(scope, name)] = value
        return out
    want, got = sets(reference), sets(rows)
    missing = sorted(k for k in want if k not in got)
    extra = sorted(k for k in got if k not in want)
    diff = sorted(k for k in want if k in got and want[k] != got[k])
    if missing or extra or diff:
        findings.append(finding(
            "K4", "kopya katman kanonik paletten sapıyor: eksik=%d fazla=%d "
            "değer-farkı=%d (yeniden üret: _calisma/landing/build_landing.py)"
            % (len(missing), len(extra), len(diff)),
            file=rel, missing=["%s %s" % k for k in missing[:6]],
            extra=["%s %s" % k for k in extra[:6]],
            differing={("%s %s" % k): {"kanonik": want[k], "kopya": got[k]}
                       for k in diff[:6]}))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Token drift + çakışma kapısı (fail-closed)")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a tek JSON belgesi yaz")
    ap.add_argument("--md-out", metavar="PATH",
                    help="insan-okunur markdown rapor yaz")
    ap.add_argument("--list", action="store_true",
                    help="çözülen katman/rol tablosunu bas")
    args = ap.parse_args(argv)

    def diag(*a):
        """Teşhis/karar satırları stderr'e — stdout yalnız RAPOR taşır.

        `--json` modunda stdout TEK JSON belgesi olmalı; hata mesajları da
        (roster yok, ölçüm hatası) her modda stderr'e gider ki çağıran
        çıkış kodunu ve gövdeyi ayrı ayrı okuyabilsin.
        """
        print(*a, file=sys.stderr)

    if not ROSTER.is_file():
        diag("HATA: roster yok: %s" % ROSTER)
        return 2
    try:
        entries = parse_roster(ROSTER.read_text(encoding="utf-8"))
    except RosterError as exc:
        diag("HATA: roster okunamadı: %s" % exc)
        return 2

    # Roster'ın ölü satırları (hiçbir dosyaya uymayan glob) — iki yönlü kapı.
    findings = []
    for entry in entries:
        entry["hits"] = sorted(
            rel_of(p) for p in REPO.glob(entry["pattern"]) if p.is_file())
        if not entry["hits"]:
            findings.append(finding(
                "K5", "roster satırı hiçbir dosyaya uymuyor (ölü kayıt)",
                file=entry["pattern"], line=entry["line"], role=entry["role"]))

    files = surface_files()
    if not files:
        diag("HATA: tarama kümesi boş — kör kapı")
        return 2

    # Kanonik referans ÖNCE yüklenir: K2 (birim) ve K4/K6 (kopya/tüketici)
    # ondan türetilir; roster'da `canonical` değilse ya da yoksa kapı körleşir.
    cpath = REPO / CANONICAL_PATH
    centry = resolve_role(entries, CANONICAL_PATH)
    if centry is None or centry["role"] != "canonical" or not cpath.is_file():
        diag("HATA: kanonik referans %s roster'da `canonical` değil ya da yok"
             % CANONICAL_PATH)
        return 2
    try:
        canon_rows = scan_file(cpath)
    except (MeasurementError, ValueError, OSError) as exc:
        diag("HATA: kanonik referans ölçülemedi: %s" % exc)
        return 2

    per_file = {CANONICAL_PATH: canon_rows}
    layers = []
    excluded = []
    for path in files:
        rel = rel_of(path)
        entry = resolve_role(entries, rel)
        role = entry["role"] if entry else None
        if role is None:
            # Kayıtsız dosya: kayıt denetimi yeter (yapısal denetim koşmaz —
            # yapı güvenilmezse zaten K5 nedeniyle KIRMIZI).
            n = count_definitions(path)
            if not n:
                continue                   # token tanımı yok → kapsam dışı
            findings.append(finding(
                "K5", "token tanımlayan dosya roster'da yok — kapsam sessizce "
                "daralmış olabilir (design-system/scripts/token_layers.list)",
                file=rel, definitions=n))
            excluded.append({"path": rel, "role": "UNREGISTERED",
                             "definitions": n})
            continue
        if role == "capture":
            n = count_definitions(path)
            if n:
                excluded.append({"path": rel, "role": role,
                                 "definitions": n})
            continue
        try:
            rows = scan_file(path)
        except (MeasurementError, ValueError, OSError) as exc:
            diag("HATA: %s ölçülemedi: %s" % (rel, exc))
            return 2
        if not rows:
            continue                       # token tanımı yok → kapsam dışı
        layers.append({"path": rel, "role": role, "definitions": len(rows)})
        check_intra_block(rel, rows, findings)
        if role in UNIT_ROLES:
            per_file[rel] = rows
        if role == "variant":
            check_variant_scope(rel, rows, path.parent.name, findings)
        if role == "consumer":
            check_consumer(rel, rows, canon_rows, findings)
        if role == "copy":
            check_copy(canon_rows, rel, rows, findings)

    check_cross_layer(per_file, findings)

    counts = {rule: sum(1 for f in findings if f["rule"] == rule)
              for rule in FINDING_RULES}
    counts["total"] = len(findings)
    status = "ok" if not findings else "blocked"
    by_scope = {}
    for rows in per_file.values():
        for scope, _, _ in rows:
            by_scope[scope] = by_scope.get(scope, 0) + 1
    doc = {"schema": "token-conflicts/1", "status": status,
           "roster": {"path": rel_of(ROSTER), "entries": len(entries),
                      "capture": sum(1 for e in entries
                                     if e["role"] == "capture")},
           "unit": list(UNIT_ROLES),
           "canonical": CANONICAL_PATH,
           "scanned": {"files": len(layers),
                       "definitions": sum(x["definitions"] for x in layers),
                       "by_scope": dict(sorted(by_scope.items()))},
           "layers": layers, "excluded": excluded,
           "counts": counts, "findings": findings}

    if args.list:
        for layer in layers:
            print("%-12s %-46s tanım=%d"
                  % (layer["role"], layer["path"], layer["definitions"]))
        for item in excluded:
            print("%-12s %-46s tanım=%d (taranmadı)"
                  % (item["role"], item["path"], item["definitions"]))

    if args.json:
        print(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1))
    elif not args.list:
        for f in findings:
            print("%s %s" % (f["rule"], f["detail"]))
            if f.get("file"):
                print("   %s%s" % (f["file"],
                                   (" [%s]" % f["scope"]) if f.get("scope")
                                   else ""))
            for key in ("name", "values", "layers", "names", "missing",
                        "extra", "differing"):
                if f.get(key):
                    print("   %s: %s" % (key, f[key]))
        print("katman=%d tanım=%d kapsam=%d"
              % (doc["scanned"]["files"], doc["scanned"]["definitions"],
                 len(by_scope)))
        print("SONUÇ: %s (%s)" % (
            "ÇAKIŞMA/DRIFT YOK — fark edilen katman kümeleri çakışmıyor" if
            status == "ok" else "ÇAKIŞMA/DRIFT", ", ".join(
                "%s=%d" % (k, counts[k]) for k in FINDING_RULES)))

    if args.md_out:
        lines = ["# Token drift & çakışma raporu", "",
                 "- şema: `token-conflicts/1`", "- durum: `%s`" % status,
                 "- katman: %d · tanım: %d" % (doc["scanned"]["files"],
                                               doc["scanned"]["definitions"]),
                 "", "| Kural | Adet |", "|---|---|"]
        lines += ["| %s | %d |" % (k, counts[k]) for k in FINDING_RULES]
        lines += ["", "## Bulgular", ""]
        if not findings:
            lines.append("BULGU YOK — katmanlar arası çakışma/drift ölçülmedi.")
        for f in findings:
            lines.append("- **%s** %s%s" % (
                f["rule"], f["detail"],
                (" — `%s`" % f["file"]) if f.get("file") else ""))
        Path(args.md_out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    diag("[token-conflicts] durum=%s bulgu=%d" % (status, counts["total"]))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
