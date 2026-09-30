#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_brand_mirrors.py — marka-mirror drift kapısı (fail-closed, read-only).

Neden ayrı kapı: design-system/{stripe,linear,primer,vercel}/scripts/
check_<marka>_tokens.py dosyaları mirror'ı kendi kaynağına (raw.css/raw.json)
karşı doğrular, ama pre-commit zincirinde bu dördünü koşan bir hook YOKTU —
mirror dosyaları değişse bile drift sessizce commit edilebiliyordu (ölçüm:
2026-09-27, findings.md). Bu kapı dördünü tek roster üzerinden, ADIYLA koşar.

Sözleşmeler (hepsi fail-closed):
  R1 ROSTER BÜTÜNLÜĞÜ : roster yok/boş/<MIN_ENTRY giriş → exit 2.
                        (Toplu silmeye karşı eşik koruması.)
  R2 KAYIT BÜTÜNLÜĞÜ  : her satırda dizin + raw + checker diskte olmalı; pin
                        pozitif tam sayı; yollar mirror dizini dışına çıkamaz
                        (`..`, mutlak yol yasak) → exit 2.
  R3 KAPSAM           : design-system/<dizin>/ altında tokens.json + raw.*
                        taşıyan HER mirror ya roster'da ya da gerekçeli
                        `# exempt:` satırında olmalı — yeni mirror sessizce
                        kapsam dışı kalamaz → exit 2.
  R4 CHECKER KOŞUMU   : her checker rc=0 olmalı; hata çıktısı (kuyruk) basılır
                        → exit 1.
  R5 PİN EŞLEŞMESİ    : checker'ın "OK — N" satırındaki N pinlenen sayıya
                        birebir eşit olmalı. OK satırı yoksa / N=0 ise
                        "vacuous PASS" yasağı → exit 1. Mirror güncellenip
                        tokens.* yenilendiğinde pin BİLİNÇLİ güncellenir.

Exit kodları: 0 = 4/4 PASS, 1 = drift/pin/checker bulgusu, 2 = yapısal hata
(roster/kapsam). READ-ONLY: hiçbir dosyayı yazmaz, silmez, üretmez.
OFFLINE, stdlib-only, ~0.2s.

Kullanım:
  python3 design-system/scripts/check_brand_mirrors.py
  python3 design-system/scripts/check_brand_mirrors.py --root . --roster <dosya>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
DEFAULT_ROSTER = HERE / "brand_mirrors.list"

# R1: dört marka mirror'ı toplu-silme koruması; roster bundan kısa olamaz.
MIN_ENTRY = 4
RAW_NAMES = ("raw.css", "raw.json")
# Checker'ların PASS satırı: "OK — 710 HDS tokens verbatim …" (em/en dash toleranslı)
OK_RE = re.compile(r"OK\s*[\u2014\u2013-]\s*([0-9]+)\b")
EXEMPT_RE = re.compile(
    r"^#\s*exempt\s*:\s*([A-Za-z0-9._-]+)\s*[\u2014\u2013-]\s*(\S.*)$")
EXEMPT_HEAD_RE = re.compile(r"^#\s*exempt\b", re.IGNORECASE)
CHECKER_TIMEOUT_S = 120


class SetupError(Exception):
    """R1/R2/R3 — yapısal bütünlük ihlali (exit 2)."""


def _safe_relative(rel: str) -> bool:
    """Roster'daki yol mirror dizini içinde kalmalı (kaçış/abs yol yasak)."""
    p = Path(rel)
    return (not p.is_absolute()) and (".." not in p.parts) and rel != ""


def load_roster(path: Path):
    """roster'ı (entries, exempt) olarak okur; ihlalde SetupError yükseltir."""
    if not path.is_file():
        raise SetupError(
            f"roster yok: {path} (remedy: git checkout -- "
            f"design-system/scripts/{DEFAULT_ROSTER.name})")

    entries = []
    exempt = {}
    seen = set()
    for lineno, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if EXEMPT_HEAD_RE.match(line) and not EXEMPT_RE.match(line):
                raise SetupError(
                    f"roster satır {lineno}: exempt gerekçesi eksik/bozuk "
                    f"(biçim: '# exempt: <dizin> \u2014 <gerekçe>')")
            m = EXEMPT_RE.match(line)
            if m:
                name, reason = m.group(1), m.group(2).strip()
                if not reason:
                    raise SetupError(
                        f"roster satır {lineno}: exempt gerekçesi boş ({name})")
                if name in exempt:
                    raise SetupError(
                        f"roster satır {lineno}: exempt tekrarı ({name})")
                exempt[name] = reason
            continue

        fields = line.split()
        if len(fields) != 4:
            raise SetupError(
                f"roster satır {lineno}: 4 alan bekleniyor "
                f"(dizin raw pin checker), {len(fields)} bulundu: {line!r}")
        name, raw_name, pin_text, checker = fields

        if name in seen:
            raise SetupError(f"roster satır {lineno}: dizin tekrarı ({name})")
        seen.add(name)
        if name in exempt:
            raise SetupError(
                f"roster satır {lineno}: {name} hem kayıtlı hem exempt")
        if not pin_text.isdigit() or int(pin_text) < 1:
            raise SetupError(
                f"roster satır {lineno}: pin pozitif tam sayı olmalı "
                f"({pin_text!r})")
        if not checker.endswith(".py"):
            raise SetupError(
                f"roster satır {lineno}: checker .py olmalı ({checker!r})")
        if not _safe_relative(raw_name) or not _safe_relative(checker):
            raise SetupError(
                f"roster satır {lineno}: yol mirror dizini dışına çıkamaz "
                f"(raw={raw_name!r}, checker={checker!r})")

        entries.append({
            "dir": name,
            "raw": raw_name,
            "pin": int(pin_text),
            "checker": checker,
        })

    if len(entries) < MIN_ENTRY:
        raise SetupError(
            f"roster yetersiz: {len(entries)} giriş "
            f"(en az {MIN_ENTRY}) — toplu silme koruması")
    return entries, exempt


def mirror_dirs(root: Path):
    """design-system/<dizin>/ içinde tokens.json + raw.* taşıyan mirror'lar."""
    ds = root / "design-system"
    if not ds.is_dir():
        raise SetupError(f"design-system/ yok: {ds}")
    found = []
    for child in sorted(ds.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if not (child / "tokens.json").is_file():
            continue
        if any((child / name).is_file() for name in RAW_NAMES):
            found.append(child.name)
    return found


def verify_registered(entries, root: Path):
    """R2: kayıtlı her mirror'ın dizin+raw+checker'ı diskte olmalı."""
    missing = []
    for e in entries:
        mirror = root / "design-system" / e["dir"]
        if not mirror.is_dir():
            missing.append(f"dizin yok: design-system/{e['dir']}/")
            continue
        for rel in (e["raw"], e["checker"]):
            if not (mirror / rel).is_file():
                missing.append(f"dosya yok: design-system/{e['dir']}/{rel}")
    if missing:
        raise SetupError(
            "roster bütünlüğü bozuk (remedy: git checkout):\n  "
            + "\n  ".join(missing))


def verify_coverage(entries, exempt, root: Path):
    """R3: diskteki HER mirror kayıtlı ya da gerekçeli exempt olmalı."""
    on_disk = set(mirror_dirs(root))
    registered = {e["dir"] for e in entries}
    unregistered = sorted(d for d in on_disk
                          if d not in registered and d not in exempt)
    if unregistered:
        raise SetupError(
            "kayıtsız mirror(lar) var — drift kapısı kapsamı dışında "
            "kalamazlar (remedy: design-system/scripts/brand_mirrors.list "
            "dosyasına 'dizin raw pin checker' satırı ekleyin ya da "
            "gerekçeli '# exempt:' yazın):\n  " + "\n  ".join(unregistered))
    stale = sorted(name for name in exempt if name not in on_disk)
    if stale:
        raise SetupError(
            "exempt satırı diskte mirror'a karşılık gelmiyor (bayat kayıt):\n  "
            + "\n  ".join(stale))


def run_checker(checker: Path, root: Path):
    return subprocess.run(
        [sys.executable, str(checker)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=CHECKER_TIMEOUT_S,
        stdin=subprocess.DEVNULL,
    )


def _tail(text: str, limit: int = 20) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[:limit])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Marka-mirror drift kapısı (fail-closed, read-only)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="repo kökü (varsayılan: script konumundan türetilir)")
    ap.add_argument("--roster", default=str(DEFAULT_ROSTER),
                    help="roster dosyası (varsayılan: brand_mirrors.list)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        entries, exempt = load_roster(Path(args.roster))
        verify_registered(entries, root)
        verify_coverage(entries, exempt, root)
    except SetupError as exc:
        print(f"check-brand-mirrors: YAPISAL HATA: {exc}", file=sys.stderr)
        return 2

    print(f"check-brand-mirrors: roster={len(entries)} pinli giriş"
          f" · exempt={len(exempt)} (taze pin zorunlu)")

    failures = []
    for e in entries:
        mirror = root / "design-system" / e["dir"]
        checker = mirror / e["checker"]
        tag = f"design-system/{e['dir']}"
        try:
            proc = run_checker(checker, root)
        except subprocess.TimeoutExpired:
            failures.append(tag)
            print(f"  FAIL  {tag}: checker {CHECKER_TIMEOUT_S}s içinde bitmedi",
                  file=sys.stderr)
            continue

        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            failures.append(tag)
            print(f"  FAIL  {tag}: {e['checker']} rc={proc.returncode} "
                  f"(raw={e['raw']})", file=sys.stderr)
            print("        " + _tail(combined).replace("\n", "\n        "),
                  file=sys.stderr)
            continue

        counts = OK_RE.findall(proc.stdout or "")
        if not counts:
            failures.append(tag)
            print(f"  FAIL  {tag}: checker 'OK — <sayı>' satırı üretmedi "
                  f"(vacuous PASS yasağı)", file=sys.stderr)
            continue
        observed = int(counts[-1])
        if observed == 0:
            failures.append(tag)
            print(f"  FAIL  {tag}: 0 token doğrulandı (boş mirror — "
                  f"vacuous PASS yasağı)", file=sys.stderr)
            continue
        if observed != e["pin"]:
            failures.append(tag)
            print(f"  FAIL  {tag}: pin {e['pin']} != gözlenen {observed} — "
                  f"mirror değişti. Değişim bilinçliyse "
                  f"design-system/scripts/brand_mirrors.list içindeki pini "
                  f"{observed} yapın.", file=sys.stderr)
            continue

        print(f"  PASS  {tag}  {e['raw']}  {observed}/{e['pin']} token  "
              f"({e['checker']})")

    if failures:
        print(f"check-brand-mirrors: {len(failures)}/{len(entries)} mirror "
              f"FAIL — commit BLOKE ({', '.join(failures)})", file=sys.stderr)
        return 1

    tail = f"; exempt: {', '.join(sorted(exempt))}" if exempt else ""
    print(f"OK — {len(entries)}/{len(entries)} marka mirror drift kapısı geçti "
          f"(pinler birebir{tail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
