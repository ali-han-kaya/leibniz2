#!/usr/bin/env python3
"""record_battery_trend.py — unittest batarya süresi trend kaydı.

determinism-trend deseni (record_determinism_trend.py): CI'ın kanonik
unittest bataryasını ZAMANLAR ve ölçümü docs/battery_trend/
battery_trend.jsonl'a tek satır ekler. Amaç: batarya süresinin haftalık
CI + yerel koşumlar arası seyrini izlemek; anormallik (dramatik yavaşlama
veya test-sayısı kayması) trendde ilk haftada görünür.

Kapsam TEK KAYNAK: verify.yml `Run CIKTI unit tests` adımıyla AYNI keşif
komutu (SCOPE — test_record_battery_trend bunu iki dosyada pinler). Farklı
kapsamlar karşılaştırılamaz; scope son kayıtta zorunlu.

Veri sözleşmesi (jsonl — satır başına ölçüm; yalnız eklenir):
  {"date": "YYYY-MM-DD", "duration_s": <float>, "tests": <int>,
   "platform": "darwin|linux", "python": "3.x.y", "gate": "PASS",
   "scope": "unittest discover -s _calisma/CIKTI -p test_*.py"}

--update: bataryayı koşar (RUNNER — test enjeksiyonu GH deseni),
süreyi ölçer. KIRMIZI batarya (rc != 0), sıfır/negatif süre ya da
"Ran N tests" kanıtı olmayan ölçüm YAZILMAZ (rc=1 — ölçülmemiş/kırmızı
PASS yok).

--check değişmezi (fail-closed trend kapısı; CI adımı):
  1. GENÇLİK — son kayıt 7 günden eskiyse FAIL (haftalık cron atlanırsa
     kanıt bayatlar).
  2. YAPISAL — her satırda 0 < duration_s <= 7200 (2 saat üstel = bozuk
     ölçüm) ve tests >= 1; son satırın scope'u SCOPE ile aynı (kapsam
     değişimi bilinçli re-baseline gerektirir).
  3. Bozuk JSONL / boş trend = FAIL (sessiz-PASS yok).
Medyan-sapma (>2×) ve test-sayısı değişimi BİLGİLENDİRİCİ notlardır,
FAIL değil (makine yükü/ortam farkı regresyon sayılmaz — ölçüm notu
kayda girer, kapı kırmızıya dönmez).
"""
import argparse
import datetime
import json
import os
import platform
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TREND = os.path.join(ROOT, "docs", "battery_trend",
                     "battery_trend.jsonl")  # versiyonlu (ci_simulate ignore'da)

# Keşif komutu — verify.yml "Run CIKTI unit tests" ile TEK KAYNAK.
SCOPE = "unittest discover -s _calisma/CIKTI -p test_*.py"

FRESH_DAYS = 7
DURATION_CAP_S = 7200.0
MEDIAN_FACTOR = 2.0
NOTE_WINDOW = 10


def _run_battery():
    """Bataryayı koşar: (rc, süre_s, çıktı). Zamanlayıcı buradadır."""
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", os.path.join("_calisma", "CIKTI"), "-p", "test_*.py"],
        cwd=ROOT, capture_output=True, text=True, errors="replace")
    return proc.returncode, time.monotonic() - t0, (
        proc.stdout + proc.stderr)


# Test-enjeksiyonu için modül-global: main() bunu kullanır (GH deseni).
RUNNER = _run_battery


def _tests_from(output):
    m = re.search(r"^Ran (\d+) tests?", output, re.M)
    if not m:
        raise ValueError("çıktıda 'Ran N tests' kanıtı yok — ölçüm kanıtlanamadı")
    return int(m.group(1))


def build_record(rc, duration, output):
    """Ölçüm satırını üret; geçersiz ölçümde ValueError (fail-closed)."""
    if rc != 0:
        raise ValueError(f"batarya kırmızı (rc={rc}) — kırmızı ölçüm trende yazılmaz")
    if not duration > 0:
        raise ValueError(f"süre pozitif değil: {duration!r}")
    if duration > DURATION_CAP_S:
        raise ValueError(f"süre {DURATION_CAP_S:.0f}s eşiğini aşıyor: "
                         f"{duration:.1f}s — bozuk ölçüm")
    return {
        "date": datetime.date.today().isoformat(),
        "duration_s": round(float(duration), 1),
        "tests": _tests_from(output),
        "platform": platform.system().lower(),
        "python": platform.python_version(),
        "gate": "PASS",
        "scope": SCOPE,
    }


def _append(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _records(path=None):
    if path is None:
        path = TREND  # çağrı-anında bağla (test yönlendirmesi için)
    if not os.path.exists(path):
        return []
    out = []
    for i, raw in enumerate(open(path, encoding="utf-8"), 1):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"satır {i}: bozuk JSONL: {e}") from e
    return out


def _is_fresh(date_str, now=None):
    d = datetime.date.fromisoformat(date_str)
    ref = now or datetime.date.today()
    return (ref - d).days < FRESH_DAYS


def battery_invariant(records, now=None):
    """Trend değişmezi: gençlik + yapısal geçerlilik + scope.

    Döndürür: "OK" ya da noktalı virgülle birleşik ihlal açıklamaları.
    """
    if not records:
        return "trend boş — ilk ölçüm gerekli (--update ile yeşil batarya koşumu)"
    problems = []
    latest = records[-1]

    if not _is_fresh(str(latest.get("date", "")), now):
        problems.append(
            f"son ölçüm bayat ({latest.get('date')}) — haftalık koşum atlanmış")

    for i, r in enumerate(records, 1):
        d = r.get("duration_s")
        if not isinstance(d, (int, float)) or not (0 < d <= DURATION_CAP_S):
            problems.append(
                f"satır {i}: duration_s geçersiz ({d!r}) — 0<{DURATION_CAP_S:.0f} beklenir")
        try:
            if int(r.get("tests")) < 1:
                problems.append(f"satır {i}: tests < 1")
        except (TypeError, ValueError):
            problems.append(f"satır {i}: tests alanı yok/sayı değil")

    if latest.get("scope") != SCOPE:
        problems.append(
            f"son ölçümün scope'u kanonik değil: {latest.get('scope')!r} "
            f"≠ {SCOPE!r} — kapsam değişimi bilinçli re-baseline gerektirir")

    return "; ".join(problems) if problems else "OK"


def _median(values):
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def _notes(records):
    """Bilgilendirici notlar (FAIL DEĞİL): medyan sapması + test sayısı."""
    out = []
    if len(records) >= 4:
        prior = [r["duration_s"] for r in records[-(NOTE_WINDOW + 1):-1]]
        med = _median(prior)
        latest = records[-1]["duration_s"]
        if med > 0 and latest > MEDIAN_FACTOR * med:
            out.append(
                f"not: son süre medyanın {MEDIAN_FACTOR}× üzerinde "
                f"({latest}s vs {med:.1f}s) — makine/koşum yükü araştır; "
                "kapı değil ölçüm notu")
    if len(records) >= 2:
        prev, latest = records[-2], records[-1]
        if prev.get("tests") != latest.get("tests"):
            out.append(
                f"not: test sayısı değişti {prev.get('tests')} → "
                f"{latest.get('tests')} ({latest.get('date')}) — manifest "
                "kayması trendde görünür")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Batarya süresi trend kaydı: --update ölçüm ekler, "
                    "--check trend değişmezlerini doğrular (fail-closed)")
    parser.add_argument("--update", action="store_true",
                        help="bataryayı zamanla ve jsonl'a ekle")
    parser.add_argument("--check", action="store_true",
                        help="trend değişmezlerini doğrula (fail-closed)")
    args = parser.parse_args(argv)
    if not (args.update or args.check):
        parser.error("bir mod gerekli: --update veya --check")

    if args.update:
        rc, duration, output = RUNNER()
        try:
            record = build_record(rc, duration, output)
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        _append(TREND, record)
        print(f"OK: ölçüm eklendi: {TREND}")
        print(f"  date={record['date']} duration_s={record['duration_s']} "
              f"tests={record['tests']} platform={record['platform']} "
              f"python={record['python']}")
        return 0

    # --check modu (fail-closed trend kapısı)
    try:
        records = _records()
        verdict = battery_invariant(records)
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    if verdict != "OK":
        print(f"FAIL: trend değişmezi ihlali: {verdict}", file=sys.stderr)
        return 1
    print(f"battery-trend: OK ({len(records)} ölçüm, "
          f"son {records[-1]['date']}, "
          f"duration_s={records[-1]['duration_s']}, "
          f"tests={records[-1]['tests']}, "
          f"platform={records[-1].get('platform')})")
    for note in _notes(records):
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
