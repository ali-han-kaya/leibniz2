#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_sweep.py — tek komutluk doğrulama süpürmesi; TEK verdict.

Neden var: doğrulama parçalı bir alışkanlıktır — batarya, token kapısı, build
ve cache temizliği ayrı ayrı çağrılır. Biri atlandığında süpürme SESSİZCE eksik
kalır ve "yeşil" yanılsaması doğar (ölçülen örnek: taze bir worktree'de batarya
156/158 verdi çünkü gitignore'lu toolchain/canlı veri yoktu — kapı değil ortam
kırıktı; cache/build adımları bunu görünür kılar). Bu betik adımları SIRAYLA
koşar ve sonunda tek verdict basar: `SWEEP: PASS` / `SWEEP: FAIL`, exit 0/1.

Sıra nedenseldir (fail-fast + ölçüm güvenilirliği):
  1-2. cache-clean : ~/.cache/pre-commit yetim patch'leri + K14 cleanup log.
                     Kirli cache/artık, SONRAKİ ölçümleri yanıltabileceği için
                     en başta görünür olmalı (ikisi de ~0.1-0.4s).
  3.   merge-pre   : merge ÖNCÜLÜ denetimi (~0.2s). ADVISORY — raporu görünür
                     kılmak için STRICT YOK: dalların upstream'in gerisinde
                     olması günlük gerçektir (ölçüldü: 18 dalın 6'sı geride,
                     `main` dahil) ve `make verify`'ı kırmak bu adımın işidir.
                     Yalnız ölçüm hatasında (rc 2: git okunamıyor) fail-closed.
                     Ayrıntılı rapor: doğrudan betiği koş veya
                     `verify_sweep.py --verbose`.
  4.   tokens      : design-system token kapısı (~0.1s).
  5.   build       : apps/dashboard-next `next build` — tip kapısının ve canlı
                     smoke'un gördüğü artefakt.
  6.   battery     : check_unit_tests_hook.sh. En yavaşı en sona (adımların
                     çoğu saniyeler, batarya dakikalar) — erken kırıkları
                     dakika beklemeden görürsün.

Zincir sözleşmesiyle aynı: **fail-fast KAPALI** — bir adım kırılsa da zincir
sonuna kadar koşar, böylece tek turda TÜM kırıkları görürsün (süre kazancı
iddiası yok). Kırılan adımların çıktı kuyruğu sonda basılır.

Kapsam dışı: `verify_delivery.py --full` (K-katman zinciri, dakikalar, Z3/Lean
ister) bu süpürmeye DAHİL DEĞİL — ayrı bir bilinçli koşumdur (bkz. AGENTS.md),
aksi halde `make verify` commit-öncesi alışkanlık olamayacak kadar yavaşlar.

Exit: 0 = tüm adımlar PASS, 1 = ≥1 adım FAIL, 2 = kullanım hatası.
Kullanım:
  python3 _calisma/CIKTI/verify_sweep.py             # tam süpürme
  python3 _calisma/CIKTI/verify_sweep.py --list      # adımların sözlüğü
  python3 _calisma/CIKTI/verify_sweep.py --dry-run   # çalıştırmadan plan
  python3 _calisma/CIKTI/verify_sweep.py --only tokens,build
  python3 _calisma/CIKTI/verify_sweep.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Callable, List, NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# Kırılan adımın çıktı KUYRUĞU (satır) — tam build/batarya dökümü raporu gömmez.
TAIL_LINES = 15


class Step(NamedTuple):
    """Bir süpürme adımı: ad + insan-okunur etiket + argv (kabuk YOK)."""

    name: str
    label: str
    cmd: List[str]


# Komutlar argv listesidir (kabuk yorumu/glob yok → enjeksiyon yüzeyi yok).
# Yollar repo-köküne GÖRELİDİR; cwd=ROOT ile koşar. Kapı sözlüğü için: --list.
STEPS: List[Step] = [
    Step(
        "cache-precommit",
        "pre-commit cache kalıntısı (yetim patch)",
        ["python3", "_calisma/CIKTI/check_precommit_orphans.py"],
    ),
    Step(
        "cache-cleanup-log",
        "K14 cleanup log (kanonik dizin dışı artefakt)",
        ["python3", "_calisma/CIKTI/verify_delivery.py", "--check-cleanup"],
    ),
    Step(
        "merge-pre",
        "merge ön-ölçümü (advisory: senkronluk + push edilmemiş iş)",
        ["python3", "_calisma/CIKTI/check_merge_precondition.py"],
    ),
    Step(
        "tokens",
        "design-system token kapısı (import + kopya drift)",
        ["python3", "design-system/scripts/check_tokens.py"],
    ),
    Step(
        "build",
        "dashboard-next next build",
        ["npm", "run", "build", "--prefix", "apps/dashboard-next"],
    ),
    Step(
        "battery",
        "birim test bataryası (check-unit-tests, manifest)",
        ["bash", "_calisma/CIKTI/check_unit_tests_hook.sh"],
    ),
]


def subprocess_runner(cmd: List[str], verbose: bool):
    """Varsayılan koşucu: (rc, output). verbose → çıktı akar, yakalanmaz."""
    if verbose:
        completed = subprocess.run(cmd, cwd=ROOT)
        return completed.returncode, ""
    completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def run_sweep(
    steps: List[Step],
    runner: Callable | None = None,
    verbose: bool = False,
    quiet: bool = False,
) -> List[dict]:
    """Adımları sırayla koşar; her adım için sonuç kaydı döndürür.

    Fail-fast YOK: bir adım kırılsa da kalanlar koşar. Koşucunun fırlattığı
    OSError (komut yok/çalıştırılamaz) crash değil, **kırık adım** sayılır —
    süpürme tüm resmi göstermeye devam eder.

    `runner` ÇAĞRI ANINDA çözülür (varsayılan parametre olarak bağlanmaz):
    aksi halde `sweep.subprocess_runner` monkeypatch'i etkisiz kalır ve
    testler ağır adımları (npm build, batarya) GERÇEKTEN koşardı — ölçüldü.
    """
    if runner is None:
        runner = subprocess_runner
    results: List[dict] = []
    for index, step in enumerate(steps, 1):
        started = time.monotonic()
        try:
            rc, output = runner(step.cmd, verbose)
        except OSError as exc:
            rc, output = 127, f"çalıştırılamadı: {exc}"
        seconds = time.monotonic() - started
        ok = rc == 0
        results.append({
            "name": step.name,
            "label": step.label,
            "cmd": list(step.cmd),
            "rc": rc,
            "ok": ok,
            "seconds": round(seconds, 2),
            "output": output,
        })
        if not quiet:
            status = "PASS" if ok else "FAIL"
            print(f"[{index}/{len(steps)}] {step.name:<18} {status} "
                  f"(rc={rc}, {seconds:.1f}s)  {step.label}")
            sys.stdout.flush()
    return results


def _tail(output: str, lines: int = TAIL_LINES) -> List[str]:
    meaningful = [line for line in (output or "").splitlines() if line.strip()]
    return meaningful[-lines:]


def render_summary(results: List[dict]) -> List[str]:
    """Kırılan adımların çıktı kuyruğu + TEK verdict."""
    lines: List[str] = []
    failed = [r for r in results if not r["ok"]]
    for result in failed:
        lines.append("")
        lines.append(f"--- {result['name']} (rc={result['rc']}) son "
                     f"{TAIL_LINES} satır ---")
        lines.extend(_tail(result["output"]))
    total = round(sum(r["seconds"] for r in results), 1)
    lines.append("")
    if failed:
        lines.append(f"SWEEP: FAIL — {len(failed)}/{len(results)} adım "
                     f"başarısız ({total}s): "
                     + ", ".join(r["name"] for r in failed))
    else:
        lines.append(f"SWEEP: PASS — {len(results)}/{len(results)} adım yeşil "
                     f"({total}s)")
    return lines


def select_steps(only: str | None) -> List[Step]:
    """`--only a,b` filtresi; bilinmeyen ad → None (çağıran exit 2 verir)."""
    if not only:
        return list(STEPS)
    wanted = [part.strip() for part in only.split(",") if part.strip()]
    known = {step.name for step in STEPS}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        print(f"HATA: bilinmeyen adım: {', '.join(unknown)}", file=sys.stderr)
        print("mevcut adımlar: " + ", ".join(s.name for s in STEPS),
              file=sys.stderr)
        return []
    keep = set(wanted)
    return [step for step in STEPS if step.name in keep]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Doğrulama süpürmesi: cache-clean + token + build + batarya "
                    "→ tek verdict.")
    parser.add_argument("--list", action="store_true",
                        help="adımları ve komutlarını listele")
    parser.add_argument("--dry-run", action="store_true",
                        help="planı göster, hiçbir adımı koşma")
    parser.add_argument("--only", default=None,
                        help="yalnız bu adımlar (virgülle; ör. tokens,build)")
    parser.add_argument("--json", action="store_true",
                        help="makine-okunur tek JSON belgesi")
    parser.add_argument("--verbose", action="store_true",
                        help="adım çıktısını canlı akıt (yakalama yok)")
    args = parser.parse_args(argv)

    if args.list:
        for step in STEPS:
            print(f"{step.name:<18} {step.label}")
            print(f"{'':<18} $ {' '.join(step.cmd)}")
        return 0

    steps = select_steps(args.only)
    if not steps:
        return 2

    if args.dry_run:
        print(f"SWEEP PLANI — {len(steps)} adım (kök: {ROOT})")
        for index, step in enumerate(steps, 1):
            print(f"[{index}/{len(steps)}] {step.name:<18} $ {' '.join(step.cmd)}")
        return 0

    results = run_sweep(steps, verbose=args.verbose, quiet=args.json)
    passed = all(r["ok"] for r in results)

    if args.json:
        payload = {
            "verdict": "PASS" if passed else "FAIL",
            "root": ROOT,
            "steps": [
                {key: r[key] for key in ("name", "cmd", "rc", "ok", "seconds")}
                for r in results
            ],
        }
        for result in results:
            if not result["ok"]:
                payload["steps"][results.index(result)]["output_tail"] = \
                    _tail(result["output"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in render_summary(results):
            print(line)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
