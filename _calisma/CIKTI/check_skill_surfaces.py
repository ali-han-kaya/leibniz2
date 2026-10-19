#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skill_surfaces.py — skill-alanı ↔ repo-yüzeyi envanteri kapısı.

Manifest: `_calisma/CIKTI/skill_surfaces.list` (TEK KAYNAK — biçim ve
gerekçe dosyanın başlığında). Amaç: ajan-beceri alanlarının (RN/Expo,
Stripe, Prisma, Postgres, …) bu repodaki GERÇEK yüzeyleri, git geçmişine
değil denetlenen bir manifest'e bağlansın. 2026-09-19 turları sıfır-yüzey
denetimlerini (RN/Expo, Workers/wrangler, xlsx) kanıtlamış, ama kanıt
yalnız findings.md notunda kalmıştı; bu kapı kanıtı YÜZEYDE tutar.

Denetimler (fail-closed — `--check`):
  1. BIÇIM: her etkin satır 3 alan (alan, paket, yol) veya `#` yorum.
  2. YOL VARLIĞI: her yol repo kökünde VAR olmalı (dosya ya da dizin).
     Yol, alanın "nereye bakacağını" sabitler — eksik yüzey bayatlıktır.
  3. PAKET İMZASI ↔ GERÇEKLIK (iki yönlü):
     - Manifest'teki her (alan, paket) için: paket adı repo package.json
       bağımlılıklarında (dependencies/devDependencies/peerDependencies)
       GERÇEKTEN geçmeli — yoksa satır hayalettir (kaldır ya da düzelt).
     - Repo package.json'larında görünen HER bağımlılık için: ya bilinen
       bir alan imzasına düşmeli ya da `# unlisted:` gerekçesiyle manifest
       edilmiş olmalı. Kayıtsız paket = sessiz kapsam kaybı (brand_mirrors
       roster sözleşmesiyle aynı ilke) → FAIL.
  4. ZERO-SURFACE İDDİASI: `zero-surface` alanların imza paketleri
     HİÇBİR package.json'da geçemez; geçerse iddia bozulmuş demektir →
     FAIL. (rn-expo: react-native/expo/…; wrangler; xlsx)
  5. TEK KAYNAK: aynı (alan, paket, yol) üçlüsü iki kez yazılamaz.

Çıkış: 0 = senkron, 1 = drift (fail-closed), 2 = kullanım hatası.
`--json`: makine-okunur rapor. `--update`: kayıtsız paketler için öneri
ÜRETİR ve var olmayan yol satırlarını düzeltir — kayıtsız paketi elle
gerekçelendirmeden otomatik eklemek yanlış olur (alan kararı insana aittir).

stdlib-only. OFFLINE. ~0.05s (6 package.json, budanmış yürüyüş).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MANIFEST = os.path.join(HERE, "skill_surfaces.list")

SKIP_DIRS = {
    "node_modules", ".next", ".git", ".worktrees", ".vercel", ".venv",
    ".venv_z3", "__pycache__", "generated", ".lake", "dist", "build",
    ".pytest_cache", "coverage",
}

# PAKET → alan imzası. Alanın hangi paket adlarıyla görüneceği TEK KAYNAK
# manifest'tir; bu harita yalnız KEŞİF yönünü (paket → hangi alan ailesi)
# kısaltır ve manifest'le TUTARLI olmak zorundadır (test #6 çapraz denetler).
KNOWN_SIGNATURES = {
    "next": "nextjs",
    "react": "react-web",
    "react-dom": "react-web",
    "prisma": "prisma",
    "@prisma/client": "prisma",
    "@prisma/adapter-pg": "prisma",
    "pg": "postgres",
    "remotion": "remotion",
    "@remotion/cli": "remotion",
    "pptxgenjs": "pptx",
    "docx": "docx",
    "tailwindcss": "tailwind",
    "@tailwindcss/postcss": "tailwind",
}

# KIMLIK satırları: package.json bağımlılığı OLMAYAN yüzeyler (snapshot
# mirror'lar — design-system/<brand>/ raw.css/raw.json + tokens). Paket
# sütunu bir takma addır; kapı bunu imza olarak değil YALNIZ yol varlığı
# olarak denetler (hayalet denetimi bu satırlara uygulanmaz). Ölçüldü:
# hiçbir package.json 'stripe-tokens' gibi adlar taşımaz — denetimden
# muaf tutulmazlarsa kapı kendi meşru satırlarını hayalet sanırdı.
IDENTITY_ALIASES = {
    "stripe-tokens", "linear-tokens", "primer-tokens", "vercel-tokens",
}

# Sıfır-yüzey alanların imzaları: bunlar manifest'te `zero-surface` satırında
# taşınır (paket sütununda virgüllü liste) ve GÖRÜNMEMELİDİR.
ZERO_SIGNATURES = {
    "rn-expo": ["react-native", "expo", "@expo/cli", "expo-image",
                "react-native-reanimated", "@react-navigation/native",
                "@shopify/flash-list"],
    "wrangler": ["wrangler", "@cloudflare/workers-types"],
    "xlsx": ["xlsx", "exceljs", "sheetjs"],
}

# ARÇ GÜRÜLTÜSÜ: bu paketler bir beceri-ALANI temsil etmez — derleme,
# biçimlendirme ya da çalıştırıcı aracıdır ve kendi alanı yoktur. Kapının
# kayıtsız-paket ihlalinde SAYILMAZLAR (yoksa her build-tool ekleme süiti
# kırmızıya düşerdi ve sinyal kaybolurdu). Küme kapalıdır: yeni bir girdi
# için TESTTTE gerekçe zorunludur (kör genişleme yok).
TOOLCHAIN_NOISE = {
    "prettier",      # biçimlendirici (check-prettier-format kapısı kullanır)
    "typescript",    # derleyici (tsc --noEmit tip kapısı)
    "esbuild",       # remotion bundle aracı
    "vite",          # dashboard-shadcn derleme aracı
    "@vitejs/plugin-react",
    "tsx",           # trend-db JS çalıştırıcısı (test_trend_db_js_runner)
    "dotenv",        # trend-db env yükleyici (prisma.config.ts)
    "shadcn",        # bileşen-CLI (dashboard-next bileşim aracı)
    "cn",            # 2-satır classnames yardımcı paketi (utility, alan değil)
    "class-variance-authority",  # cva — bileşen varyant yardımcısı
    "lucide-react",  # ikon paketi (UI library, alan değil)
    "@base-ui/react",  # shadcn/UI temel bileşenleri (UI library)
    "tw-animate-css",  # animasyon utility CSS'i
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_manifest(text):
    """Manifest → satır kayıtları. Döner (entries, problems).

    entry = {"domain", "package", "path", "zero", "line"} — zero satırların
    `package` sütunu `zero-surface`, imza listesi ZERO_SIGNATURES'tan gelir.
    """
    entries, problems = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            problems.append("satır %d: 3 alan beklenirdi, %d var — %r"
                            % (lineno, len(parts), raw.strip()))
            continue
        domain, package, rel_path = parts
        entries.append({
            "domain": domain,
            "package": package,
            "path": rel_path,
            "zero": package == "zero-surface",
            "line": lineno,
        })
    return entries, problems


def package_dependencies(root):
    """{package.json göreli yolu: {bağımlılık adı}} — budanmış yürüyüş.

    node_modules/.next/generated gibi ağaçlar ZATEN paket kaynağı değildir
    ve yürüyüşü şişirir; SKIP_DIRS ile budanır (ölçüldü: 0.01s, 6 manifest).
    """
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        if "package.json" not in filenames:
            continue
        full = os.path.join(dirpath, "package.json")
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        try:
            data = json.loads(_read(full))
        except (OSError, ValueError) as exc:
            found[rel] = {"__error__": str(exc)}
            continue
        deps = set()
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update((data.get(section) or {}).keys())
        found[rel] = deps
    return found


def observed_packages(deps_by_file):
    """{paket adı: [package.json yolu…]} — keşif yönü."""
    observed = {}
    for pkg_file, deps in deps_by_file.items():
        if isinstance(deps, dict):  # parse hatası kaydı
            continue
        for name in deps:
            observed.setdefault(name, []).append(pkg_file)
    return {name: sorted(files) for name, files in observed.items()}


def check(root=ROOT, manifest=MANIFEST, require_paths=True,
          require_zero_domains=True):
    """Tam denetim. Döner (ok, findings, report_dict).

    `require_zero_domains`: ZERO_SIGNATURES'taki HER alanın manifest'te
    zero-surface satırı taşıması ZORUNUDUR (gerçek-repo sözleşmesi — sessiz
    kapsam kaybı yasağı). Hermetik fixture testleri tek sözleşmeyi ölçerken
    diğer alanları taşımak zorunda kalmasın diye kapatılabilir.
    """
    findings = []
    report = {
        "manifest": manifest,
        "entries": 0,
        "zero_domains": [],
        "packages": {},
        "unlisted": [],
        "phantom": [],
        "zero_violations": [],
        "missing_paths": [],
        "duplicate_rows": [],
    }

    try:
        text = _read(manifest)
    except OSError as exc:
        return False, [f"manifest okunamadı: {manifest} ({exc})"], report

    entries, parse_problems = parse_manifest(text)
    findings.extend(parse_problems)
    report["entries"] = len(entries)
    deps_by_file = package_dependencies(root)
    observed = observed_packages(deps_by_file)
    report["packages"] = {name: len(files) for name, files in sorted(observed.items())}

    seen = set()
    zero_domains = set()
    for entry in entries:
        key = (entry["domain"], entry["package"], entry["path"])
        if key in seen:
            report["duplicate_rows"].append(key)
            findings.append("satır %d: kayıt iki kez yazılmış — %s" %
                            (entry["line"], key))
        seen.add(key)

        if entry["zero"]:
            zero_domains.add(entry["domain"])
            report["zero_domains"].append(entry["domain"])
            # yol = kanıt kaydı (var olması beklenir ama içeriği denetlenmez)
            if require_paths and not os.path.exists(os.path.join(root, entry["path"])):
                report["missing_paths"].append(entry["path"])
                findings.append("satır %d: kanıt yolu yok — %s"
                                % (entry["line"], entry["path"]))
            continue

        # 2) yol varlığı
        if require_paths and not os.path.exists(os.path.join(root, entry["path"])):
            report["missing_paths"].append(entry["path"])
            findings.append("satır %d: yüzey yolu yok — %s"
                            % (entry["line"], entry["path"]))
        # 3a) imza gerçekten bağımlılıklarda mı (hayalet satır)?
        # KIMLIK takma adları muaf: snapshot mirror'lar bağımlılık
        # taşımaz, yol varlığı onların tek denetimidir.
        locations = observed.get(entry["package"])
        if not locations and entry["package"] not in IDENTITY_ALIASES:
            report["phantom"].append(entry["package"])
            findings.append(
                "satır %d: hayalet satır — %r hiçbir package.json'da yok "
                "(paket kaldırıldıysa satırı sil, alan adıysa düzelt)"
                % (entry["line"], entry["package"]))

    report["zero_domains"] = sorted(set(report["zero_domains"]))

    # 4) zero-surface ihlalleri
    declared_zero = {e["domain"] for e in entries if e["zero"]}
    for domain, signatures in ZERO_SIGNATURES.items():
        if require_zero_domains and domain not in declared_zero:
            findings.append("zero-surface alan manifest'te kayıpsız: %s "
                            "(sıfır-yüzey iddiası yazılı olmalı)" % domain)
            continue
        for signature in signatures:
            if signature in observed:
                report["zero_violations"].append((domain, signature,
                                                  observed[signature]))
                findings.append(
                    "ZERO-SURFACE ihlali: %r paketi göründü ama %r alanı "
                    "sıfır-yüzey iddialı — %s"
                    % (signature, domain, ", ".join(observed[signature])))

    # 3b) kayıtsız paketler (bilinen imzalar dışında görünen her ad)
    declared = {e["package"] for e in entries if not e["zero"]}
    zero_signature_names = {name for names in ZERO_SIGNATURES.values()
                            for name in names}
    for name, files in sorted(observed.items()):
        if name in KNOWN_SIGNATURES or name in declared:
            continue
        if name.startswith("@types/"):
            continue  # tip paketleri alan imzası değil, dili kurar
        if name in zero_signature_names:
            continue  # zero-surface denetimi KAPSAR (çift rapor gürültü olur)
        if name in TOOLCHAIN_NOISE:
            continue  # derleme/arç paketleri: alan yüzeyi değil (gerekçe aşağıda)
        report["unlisted"].append({"package": name, "files": files})
        findings.append(
            "kayıtsız paket: %r (%s) — skill_surfaces.list'e satır ekleyin "
            "(--update öneri üretir) ya da `# unlisted:` gerekçesiyle "
            "manifest edin" % (name, ", ".join(files)))

    report["ok"] = not findings
    return (not findings), findings, report


def suggest_update(root=ROOT, manifest=MANIFEST):
    """Kayıtsız paketler için manifest satırı ÖNERİSİ (yazmaz — önerir).

    Alan kararı insana aittir: betik paketi GÖRÜR, alanını ATAMAZ. Çıktıda
    her paket için `# TODO-alan:` yorumlu aday satır basılır.
    """
    ok, findings, report = check(root, manifest)
    suggestions = []
    for item in report["unlisted"]:
        name = item["package"]
        first = item["files"][0]
        suggestions.append(
            "# TODO-alan: <alan>  %-24s  %s\n"
            "#   → %r şu an %s altında görünüyor; alanı elle atayın\n"
            % (name, "<yüzey-yolu>", name, first))
    return suggestions, report


def render(findings, report):
    lines = ["SKILL-SURFACE ENVANTERİ (check-skill-surfaces)"]
    lines.append("  manifest: %s → %d satır (%d zero-surface alan)"
                 % (os.path.relpath(report["manifest"], ROOT),
                    report["entries"], len(report["zero_domains"])))
    lines.append("  taranan package.json: %d" % len(report["packages"]))
    if not findings:
        lines.append("PASS: envanter repo ile senkron (%d satır)"
                     % report["entries"])
        return lines
    lines.append("BAYAT: envanter repoyu yansıtmıyor.")
    for finding in findings:
        lines.append("  - %s" % finding)
    lines.append("  çözüm: python3 _calisma/CIKTI/check_skill_surfaces.py --update "
                 "(öneri üretir; alan kararı elle)")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="skill-alanı ↔ repo-yüzeyi envanteri kapısı (fail-closed)")
    parser.add_argument("--check", action="store_true",
                        help="drift'te exit 1 (öntanımlı davranış)")
    parser.add_argument("--json", action="store_true",
                        help="makine-okunur rapor")
    parser.add_argument("--update", action="store_true",
                        help="kayıtsız paketler için manifest önerisi üret")
    parser.add_argument("--manifest", default=MANIFEST,
                        help="manifest yolu (test izolasyonu)")
    parser.add_argument("--root", default=ROOT,
                        help="repo kökü (test izolasyonu)")
    parser.add_argument("--no-path-check", action="store_true",
                        help="yol varlık denetimini kapat (yalnız paket kümesi)")
    args = parser.parse_args(argv)

    ok, findings, report = check(
        root=args.root, manifest=args.manifest,
        require_paths=not args.no_path_check)

    if args.json:
        payload = dict(report)
        payload["ok"] = ok
        payload["findings"] = findings
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    for line in render(findings, report):
        print(line)

    if args.update and report["unlisted"]:
        suggestions, _ = suggest_update(args.root, args.manifest)
        print("\n--- --update ÖNERİSİ (manifest'e elle ekleyin) ---")
        for block in suggestions:
            print(block, end="")
        print("NOT: betik paket görür, alanı ATAMAZ — alan kararı elle.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
