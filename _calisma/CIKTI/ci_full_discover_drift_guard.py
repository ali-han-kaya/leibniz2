#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_full_discover_drift_guard.py — CI adımı için gate: yüklü bataryanın
yeşil olduğu halde `unittest discover -p 'test_*.py'` kırmızı (bir veya daha
çok test dosyası kırmızı/hatalı) ise CI'yi FAIL yap.

Motivasyon: pre-commit + check-unit-tests listesi sadece *kayıtlı* test dosyalarını
koşar. Bir test dosyası committed olsa da test_coverage_report.py'nin
HOOK_COVERAGE / check_unit_tests.list'e eklenmemişse, o dosyanın testleri
kayıtlı bataryada hiç koşmaz — yani o dosyada bir hata bile olsa CI geçer.
Bu gate, "kayıtlı batarya yeşil ama tüm discover kırmızı" durumunu yakalar ve
CI'yi fail eder. Böylece yeni test dosyası ekledikten sonra onu listeye
eklemeyi unutan geliştirici CI'da derhal RED görür.

Kullanım (verify.yml'de check-unit-tests job'unun içine, listedeki testlerin
koşulmasının YANINDA):
  python3 _calisma/CIKTI/ci_full_discover_drift_guard.py

Çıkış kodları:
  0 — kayıtlı batarya + full discover aynı anda yeşil (veya full discover de
      yeşil) → sorun yok
  1 — kayıtlı batarya yeşil ama full discover kırmızı → drift → FAIL
  2 — çalma hatası (venv yok, discover kazanamaz, vb.) → CI'nin kendi
      ortam hatásának α�ansı; fail-closed olabilir ama genelde ortam probl.
"""

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
TEST_DIR = REPO_ROOT / "_calisma" / "CIKTI"

# Kayıtlı bataryayı okumak için check_unit_tests.list + test_coverage_report.py
# içindeki HOOK_COVERAGE['check-unit-tests']'u oku. Bu, CI'nin *zaten kullandığı*
# mekanizmayı taklit eder.

CHECK_UNIT_TESTS_LIST = TEST_DIR / "check_unit_tests.list"


def read_check_unit_tests_list():
    if not CHECK_UNIT_TESTS_LIST.exists():
        return set()
    return {ln.strip() for ln in CHECK_UNIT_TESTS_LIST.read_text(encoding="utf-8").splitlines()
            if ln.strip()}


def read_hook_coverage_check_unit_tests():
    """test_coverage_report.py içindeki HOOK_COVERAGE['check-unit-tests'] listesini
    statik parse eder (runtime import etmek yerine)."""
    src = (TEST_DIR / "test_coverage_report.py").read_text(encoding="utf-8")
    i = src.find('"check-unit-tests":')
    if i < 0:
        return set()
    j = src.find("],", i)
    if j < 0:
        return set()
    block = src[i:j + 1]
    # "test_X.py" desenlerini al
    import re
    return {m for m in re.findall(r'"([^"]+\.py)"', block)}


EXEMPT_FROM_DIFF_GUARD = frozenset({
    # Bu dosyaların testleri yoktur / ayrı job'dalar / önemsiz durumlar —
    # full-discover'da.basename olarak çıkarlar ama drift anlamına gelmez.
    "test_coverage_report.py",
    "test_test_coverage_report.py",
    "test_all_hooks_smoke.py",
    "test_preview_reload_smoke.py",
    "test_budget_scan.js",
    "test_dashboard_playwright_smoke.py",
})


def discover_all_py_test_files():
    """_calisma/CIKTI/test_*.py karşılığında koyulacak set (CI'nin `discover -p`
    ile görecek yere benzer, iterator olarak)."""
    return {p.name for p in sorted(TEST_DIR.glob("test_*.py"))}


def run_unittest_discover(test_names=None):
    """test_names verilirse sadece chole koşar; yoksa tüm test_*.py'yi
    `discover -p 'test_*.py'` ile koşturur.

    Döndürür: (exit_code, stdout, stderr, count_ran_or_None).
    """
    cmd = [
        sys.executable, "-m", "unittest", "discover",
        "-s", str(TEST_DIR), "-p", "test_*.py",
    ]
    if test_names:
        # test_names'in tamamını barındıracak şekilde (-p kelime)
        # KEŞİF yerine DOĞRUDAN dosya listesi için `-p` yerine her birini
        # ayrı ayrı koşturmak güvenli ama yavaş; CI için: sadece
        # `discover` ile tümünü koştur → o zaman hangilerinin kırmızı olduğunu
        # sonradan listтен belirlememiz gerekir.
        pass

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=600)
    combined = (r.stdout or "") + (r.stderr or "")
    # `Ran N tests` desenini bul
    import re
    m = re.search(r"Ran (\d+) tests", combined)
    count = int(m.group(1)) if m else None
    return r.returncode, r.stdout, r.stderr, count


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json-out", help="sonuç JSON'a yaz (CI artifact için)")
    args = ap.parse_args(argv)

    # 1) kayıtlı batarya → discover edilmeli olan dosyalar (list + HOOK_COVERAGE)
    listed = read_check_unit_tests_list()
    hooked = read_hook_coverage_check_unit_tests()
    registered = listed | hooked

    # 2) discover'ın göreceği tüm test_*.py dosyaları
    all_discoverable = discover_all_py_test_files()

    # 3) kayıtlı bataryaya GÖRE discover edilmesi GEREKEN dosyalar
    should_run = registered & all_discoverable

    # 4) listede/TSİHOOK_COVERAGE'ta olan ama disk'te yok olanlar (orphan
    #    kayıtlar) — bunlar registered'da ama all_discoverable'da yok.
    orphan_registrations = registered - all_discoverable

    # 5) disk'te var ama hiçbir yerde kayıtlı olmayanlar (potansiyel drift)
    untracked_test_files = all_discoverable - registered

    # 6) FULL discover'i tüm test_*.py üzerinde koştur → sonuç
    exit_code, stdout, stderr, count = run_unittest_discover()

    full_discover_passed = (exit_code == 0)

    # 7) kayıtlı batarya (listed + hooked) sadece bu dosyaları koşar; biz
    #    bunların *hepsinin* full discover'da da yeşil olduğunu bekleriz.
    #    Ancak discover sadece genel sonuç verir; bunun yerine full discover'ın
    #    verdiği `count` ve exit_code kullanarak "kayıtlı batarya aslında
    #    discover'ın tüm dosyaların bir kısmını değil, tamamını koşürdüğü"
    #    gerçeğini kullanabiliriz. Fakat en sağlam yol:
    #
    #    a) kayıtlı dosyaları ayrı ayrı koşturup her birinin exit'ini al
    #       (CI için teknik olarak çok maliyeti yok, batch'te rush hour yok).
    #    b) ayrı ayrı koşma yerine, full discover Sonrası stderr/stdout'dan
    #       hangi test dosyası FAILED/ERROR ettiğini parse et.

    # --- a) ayrı ayrı koş (CI budget içinde, her biri queue'da~) ---
    individual_results = {}
    failed_or_error_files = []
    for name in sorted(should_run):
        # isinstance discovery per-file: `python -m unittest test_X`
        r = subprocess.run(
            [sys.executable, "-m", "unittest", name],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
        individual_results[name] = r.returncode
        if r.returncode != 0:
            failed_or_error_files.append(name)

    # kayıtlı bataryanın *kendi* sonucu = listed + hooked dosyaların ayrı ayrı
    # koşuşunun hepsi 0 ise yeşil.
    registered_battery_green = all(
        individual_results.get(n, 1) == 0 for n in should_run)

    # --- b) full discover'ın verdiği sonuç ile cross-check ---
    # full discover kırmızı ise ve kayıtlı batarya yeşil ise → drift.
    drift_detected = (not full_discover_passed) and registered_battery_green

    # --- c) disk'te var ama kayıtlı olmayanlar (untracked) ---
    # Hangi dosyaların full discover'da kırmızı olduğunu da parse edelim
    # (ayrı ayrı koşudan zaten elde ettik).

    # GÜVENLİK NOTU: untracked dosyaların birçoğu kasıtlı olabilir
    # (smoke test, Playwright, vs.) — bu yüzden bu gate yalnızca şunu
    # bildirir: "kayıtlı batarya yeşil, ama disk'te başka kırmızı test var"
    # — bunun kayıtlı bir dosyanın test edilmemesi ile ilgili olup olmadığını
    # ayırt etmek için `untracked_test_files` kümesini kullan.

    # Özet:
    #  - Eğer full discover PASS → sorun yok, exit 0.
    #  - Eğer full discover FAIL + kayıtlı batarya YEŞİL → drift → exit 1.
    #  - Eğer full discover FAIL + kayıtlı batarya da FAIL → CI zaten
    #    kırmızı (bu gate bir şey kazanmaz, zaten kırmızı).
    #  - Eğer kayıtlı batarya FAIL → zaten kırmızı, bu gate bir şey
    #    kazanmaz, zaten kırmızı.

    # exit karar:
    #   fail = drift_detected (kayıtlı batarya yeşil ama full discover kırmızı)
    fail = drift_detected

    summary = {
        "generated_at": __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
        "full_discover": {
            "exit_code": exit_code,
            "tests_ran": count,
            "passed": full_discover_passed,
        },
        "registered_battery": {
            "files_in_scope": sorted(should_run),
            "files_passed": sum(1 for v in individual_results.values() if v == 0),
            "files_failed": failed_or_error_files,
            "green": registered_battery_green,
        },
        "untracked_test_files_not_in_any_registry": sorted(untracked_test_files - EXEMPT_FROM_DIFF_GUARD),
        "orphan_registrations_not_on_disk": sorted(orphan_registrations),
        "drift_detected": drift_detected,
        "verdict": "FAIL" if fail else "PASS",
    }

    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(summary, indent=2))

    if fail:
        print("CI-FULL-DISCOVER-DRIFT-GUARD: FAIL", file=sys.stderr)
        print(f"  kayıtlı batarya: GREEN ({summary['registered_battery']['files_passed']}/{len(should_run)} passed)",
              file=sys.stderr)
        print(f"  full discover:   RED (exit {exit_code}, {count} tests)", file=sys.stderr)
        print(f"  kayıtlı olmayan kırmızı dosyalar (farklı registry'de olmayanlar):",
              file=sys.stderr)
        for f in sorted(untracked_test_files - EXEMPT_FROM_DIFF_GUARD):
            print(f"    - {f}", file=sys.stderr)
        print(f"  kayıtlı BATARYA'nın ayrı ayrı sonucu FAILED dosyalar (regitred):",
              file=sys.stderr)
        for f in failed_or_error_files:
            print(f"    - {f}", file=sys.stderr)
        print(file=sys.stderr)
        print("  → Kayıtlı batarya yeşil ama FULL discover kırmızı. Yeni test dosyası"
              " eklenmiş veya", file=sys.stderr)
        print("    test dosyası kırmızı ama register edilmemiş → bu register edilmeli.",
              file=sys.stderr)
        return 1

    # PASS
    print("CI-FULL-DISCOVER-DRIFT-GUARD: PASS", file=sys.stderr)
    print(f"  full discover: GREEN (exit 0, {count} tests)", file=sys.stderr)
    print(f"  kayıtlı batarya: GREEN ({summary['registered_battery']['files_passed']}/{len(should_run)} passed)",
          file=sys.stderr)
    if untracked_test_files - EXEMPT_FROM_DIFF_GUARD:
        print(f"  not: {len(untracked_test_files - EXEMPT_FROM_DIFF_GUARD)} untracked test file(s) —"
              " bunlar CI'da ayrı job'larda olsa da full discover'da da yeşil yok"
              " → kayıtlı batarya ile full discover arasındaki fark yok"
              " (zaten tüm discover GREEN)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
