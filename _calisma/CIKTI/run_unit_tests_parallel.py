#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_unit_tests_parallel.py — check-unit-tests hızlı yolu (bütçeli).

Sözleşme: her test dosyası KENDİ yorumlayıcısında koşar. Bu modül yalnız
KOŞUMU eşzamanlı yapar; paylaşılan discovery/süreç YOK — böylece
test_select_affected_tests.TestHookPerFileIsolation'ın pinlediği izolasyon
(env/modül-globali sızıntısı) korunur (mutasyon kanıtı: tek süreçte
test_check_python3_shell.py sahte kırmızı veriyordu).

Bütçe: PARALLEL_BUDGET_S (env: CHECK_UNIT_TEST_BUDGET_S). Hızlı yol bu
duvar-saati bütçesini aşarsa rc=3 döner; kabuk sarmalayıcı
(check_unit_tests_hook.sh) kalan dosyaları dosya-başına SIRALI koşar.
Bütçe aşımı genelde asılı kalan bir süiti işaret eder; sıralı yol o dosyayı
zaman aşımı olmadan koşar (fail-safe: en katı yol kazanır).

Çıktı: <logs-dir>/<slug>.log ve <logs-dir>/<slug>.rc (rc = unittest çıkış
kodu). Kabuk bu iki dosyayı okur; rc dosyası YOKSA dosya "koşulmadı" demektir
ve sıralı yolda yeniden koşulur.

stdlib-only; ağ yok.
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))

# Hızlı yolun duvar-saati bütçesi. Test edilebilir TEK sabit: testler bunu
# içe aktarır, env ile geçersiz kılar. Bütçe aşımı hızlı yolu bırakır,
# sıralı (katı) yola düşer — yani yanlış-pozitif üretmez, yalnız yavaşlar.
PARALLEL_BUDGET_S = 120.0

# Eşzamanlı işçi sayısı: 1 = sıralı yolun kendisi (kabuk onu ayrıca koşar).
DEFAULT_JOBS = min(4, os.cpu_count() or 1)
MAX_JOBS = 8

EXIT_OK = 0
EXIT_BUDGET_EXCEEDED = 3
EXIT_USAGE = 2


def resolve_budget(env=None):
    """Bütçeyi env'den çöz; eksik/bozuk/sıfır değerde varsayılana dön."""
    env = os.environ if env is None else env
    raw = (env.get("CHECK_UNIT_TEST_BUDGET_S") or "").strip()
    if not raw:
        return PARALLEL_BUDGET_S
    try:
        value = float(raw)
    except ValueError:
        return PARALLEL_BUDGET_S
    if value <= 0:
        return PARALLEL_BUDGET_S
    return value


def resolve_jobs(env=None):
    """İşçi sayısını env'den çöz.

    Boş → DEFAULT_JOBS, `0` → DEFAULT_JOBS (auto), sayı olmayan/negatif → 1
    (fail-safe: tek işçi, yani en katı davranış), MAX_JOBS üstü kırpılır.
    """
    env = os.environ if env is None else env
    raw = (env.get("CHECK_UNIT_TEST_JOBS") or "").strip()
    if not raw:
        return DEFAULT_JOBS
    try:
        value = int(raw)
    except ValueError:
        return 1
    if value <= 0:
        return DEFAULT_JOBS
    return min(value, MAX_JOBS)


def read_manifest(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line)
    return entries


def slug(entry):
    name = entry[:-3] if entry.endswith(".py") else entry
    return name.replace("/", "_")


def log_path(logs_dir, entry):
    return os.path.join(logs_dir, slug(entry) + ".log")


def rc_path(logs_dir, entry):
    return os.path.join(logs_dir, slug(entry) + ".rc")


def run_one(entry, python, discover_dir, logs_dir, deadline):
    """Tek dosyayı izole süreçte koş. False → bütçe nedeniyle tamamlanamadı."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    name = entry[:-3] if entry.endswith(".py") else entry
    cmd = [python, "-m", "unittest", "discover", "-s", discover_dir,
           "-p", name + ".py"]
    log = log_path(logs_dir, entry)
    rc = rc_path(logs_dir, entry)
    try:
        with open(log, "wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=remaining, check=False)
    except subprocess.TimeoutExpired:
        return False
    except OSError as exc:
        # Eşzamanlı bir başka dosya ortak yolu (venv/toolchain) kısa süre
        # oynattıysa exec ENOENT verebilir. Bu bir TEST sonucu değildir:
        # rc yazmayız, hızlı yol "tamamlanmadı" der ve dosya sıralı yolda
        # yeniden koşar (sahte kırmızı üretmek yasak).
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("check-unit-tests: hızlı yol başlatamadı: %s\n" % exc)
        return False
    with open(rc, "w", encoding="utf-8") as fh:
        fh.write("%d\n" % proc.returncode)
    # Bu sonucun hızlı yoldan geldiğini işaretle: sarmalayıcı yalnız bu
    # sonuçların kırmızısını izole koşuda doğrular (sıralı yolda koşan
    # dosya zaten izole koştu, ikinci kez koşulmaz).
    with open(os.path.join(logs_dir, slug(entry) + ".fast"), "w",
              encoding="utf-8") as fh:
        fh.write("1\n")
    return True


def run(entries, python, discover_dir, logs_dir, jobs, budget):
    """Tüm dosyaları bütçe içinde eşzamanlı koş.

    Dönüş: (completed, elapsed). completed=False → bütçe aşıldı ya da bir
    dosya bütçe dolduğu için hiç başlamadı/tamamlanmadı.
    """
    os.makedirs(logs_dir, exist_ok=True)
    started = time.monotonic()
    deadline = started + budget
    workers = max(1, min(jobs, len(entries) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, e, python, discover_dir, logs_dir,
                               deadline) for e in entries]
        completed = all(f.result() for f in futures)
    return completed, time.monotonic() - started


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--discover-dir", default="")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--jobs", type=int, default=None,
                        help="0 → CHECK_UNIT_TEST_JOBS/varsayılan")
    parser.add_argument("--budget-s", type=float, default=None)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.manifest):
        print("HATA: manifest yok: %s" % args.manifest, file=sys.stderr)
        return EXIT_USAGE
    entries = read_manifest(args.manifest)
    if not entries:
        print("HATA: manifest boş — koşulacak dosya yok: %s" % args.manifest,
              file=sys.stderr)
        return EXIT_USAGE

    logs_dir = os.path.abspath(args.logs_dir)
    discover_dir = args.discover_dir or os.path.relpath(HERE)

    jobs = resolve_jobs() if args.jobs is None or args.jobs == 0 else \
        max(1, min(args.jobs, MAX_JOBS))
    budget = resolve_budget() if args.budget_s is None else \
        (args.budget_s if args.budget_s > 0 else resolve_budget())

    completed, elapsed = run(entries, args.python, discover_dir, logs_dir,
                             jobs, budget)
    if not completed:
        print("check-unit-tests: hızlı yol tamamlanamadı (%.1fs / bütçe %.1fs, "
              "%d dosya) — kalan dosyalar sıralı koşulmalı"
              % (elapsed, budget, len(entries)), file=sys.stderr)
        return EXIT_BUDGET_EXCEEDED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
