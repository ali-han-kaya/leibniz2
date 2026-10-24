#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_security_roster.py — güvenlik-duruşu roster'larını kaynaktan üretir.

Ölçülen yük (2026): `check_security_posture.list` + `check_security_browser.list`
elle bakımlıydı — yeni güvenlik süiti ekleyen, ikinci bir dosyayı da
değiştirmeyi unutabiliyordu (kayıt yok, koşum yok ailesi). Tek kaynak artık
test dosyalarının KENDİSİNDEKİ `# SECURITY-TIER: <tier>` işaretidir; bu script
işaretleri toplayıp iki `.list` dosyasını deterministik üretir.

  python3 _calisma/CIKTI/gen_security_roster.py --check   # doğrula (varsayılan)
  python3 _calisma/CIKTI/gen_security_roster.py --write   # yeniden üret

Tier anlamı (`check_security_posture.sh` tüketir, skip reddeder):
  * static  — her ortamda koşabilen güvenlik sözleşmesi.
  * browser — Playwright/Chromium ister; yalnız tarayıcılı işte koşar.

Fail-closed kurallar (üretim HATA verirse roster yazılmaz):
  * dosyada iki işaret / bilinmeyen tier değeri → hata;
  * `browser` işaretli dosyada playwright kapısı yoksa → hata (tier'in
    skip-reddi varsayımı boşa düşerdi);
  * tarama yalnız `_calisma/CIKTI/test_*.py` (koşturucu `discover -s` aynı
    dizini koşar; docs/ kapsam dışı).

Kapı kalıpları TEK KAYNAKTAN: `test_browser_skip_audit._GATE_RES` (çift
kopya yok — import; o modül stdlib-only, import yan etkisiz).
"""
import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import test_browser_skip_audit as audit  # noqa: E402 (tek-kaynak kapı kalıpları)

MARKER_RE = re.compile(r"^# SECURITY-TIER:\s*(browser|static)\s*$", re.M)
# Bozuk-işaret yakalayıcı yalnız YORUM satırına bakar: test fixture'larındaki
# string literalleri (`"# SECURITY-TIER: banana\n"`) satır başına `"` ile
# başladığı için eşleşmez; gerçek bozuk işaret (`# SECURITY-TIER: x`)
# satır başında `#` taşır ve yakalanır.
MARKER_LIKE_RE = re.compile(r"(?m)^\s*#.*SECURITY-TIER")

STATIC_LIST = os.path.join(SCRIPT_DIR, "check_security_posture.list")
BROWSER_LIST = os.path.join(SCRIPT_DIR, "check_security_browser.list")

HEADER = """\
# {name} — OTOMATİK ÜRETİM (`gen_security_roster.py --write`).
# ELLE YAZMA: üyelik test dosyasındaki `# SECURITY-TIER: <tier>` işaretinden
# gelir. Yeni güvenlik süiti = dosyana işaret koy, bu dosya kendiliğinden
# güncellenir (`--check` drift'i bloklar). Gerekçe: findings.md VERIFY-001.
"""


def collect_markers(directory=SCRIPT_DIR):
    """{tier: [dosya]} — hatalı işaret fail-closed ValueError."""
    found = {"static": [], "browser": []}
    for name in sorted(os.listdir(directory)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        tiers = MARKER_RE.findall(src)
        if len(tiers) > 1:
            raise ValueError("%s: iki SECURITY-TIER işareti" % name)
        if MARKER_LIKE_RE.search(src) and not tiers:
            raise ValueError(
                "%s: bozuk SECURITY-TIER işareti (browser|static olmalı)"
                % name)
        if not tiers:
            continue
        tier = tiers[0]
        if tier == "browser" and not audit._has_gate(src):
            raise ValueError(
                "%s: `browser` işaretli ama playwright kapısı yok — tier "
                "varsayımı (skip reddi) boşa düşer" % name)
        found[tier].append(name)
    return found


def render(tier, members):
    name = ("check_security_posture.list"
            if tier == "static" else "check_security_browser.list")
    lines = [HEADER.format(name=name).rstrip("\n")]
    lines.extend(members)
    return "\n".join(lines) + "\n"


def generate(directory=SCRIPT_DIR):
    found = collect_markers(directory)
    return {
        STATIC_LIST: render("static", found["static"]),
        BROWSER_LIST: render("browser", found["browser"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    written = generate()
    if args.write:
        for path, content in written.items():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        print("roster üretildi: %s" % ", ".join(
            sorted(os.path.basename(p) for p in written)))
        return 0
    drift = [p for p, content in written.items()
             if not (os.path.isfile(p) and
                     open(p, encoding="utf-8").read() == content)]
    if drift:
        sys.stderr.write(
            "roster drift: %s — remedy: gen_security_roster.py --write\n"
            % ", ".join(os.path.basename(p) for p in drift))
        return 1
    print("roster güncel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
