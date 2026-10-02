#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_full_discover_drift_guard.py — kayıt dışı kırmızı test dosyası kapısı.

pre-commit + `check_unit_tests.list` yalnız *kayıtlı* test dosyalarını koşar.
Diskte olup hiçbir kayda (manifest ∪ HOOK_COVERAGE) girmemiş bir test dosyası
bu yüzden kayıtlı bataryada hiç koşmaz. Bu kapı, tam discover (`unittest
discover -p 'test_*.py'`) çıktısını okuyup **kayıt dışı ve muaf olmayan bir
dosyadan gelen FAIL/ERROR varsa** CI'yi kırmızı yapar; yani listeye eklemeyi
unutan geliştirici derhal RED görür.

Neden kayıtlı batarya burada YENİDEN koşulmuyor: aynı CI job'unda
`check-unit-tests` manifest'in tamamını fail-closed olarak koşar. Burada tekrar
koşmak hem boştu hem pahalıydı — eski sürüm 161 dosyayı ayrı alt süreçte
koşuyordu (5m20s) ve komut repo kökünden ÇALIŞMIYORDU (`_calisma/CIKTI` paket
değil: `__init__.py` yok, sys.path'te değil), dolayısıyla her dosya rc=1
dönüyor, `drift_detected` HİÇBİR ZAMAN true olamıyor ve kapı fail-closed
değildi (ölçüldü: files_passed 0/161, verdict PASS).

Kullanım:
  python3 _calisma/CIKTI/ci_full_discover_drift_guard.py [--json-out CIKTI.json]

Çıkış kodları:
  0 — kayıt dışı, muaf olmayan kırmızı test dosyası yok
  1 — drift: kayıt dışı kırmızı dosya var → register edilmeli
  2 — çalma/ortam hatası (discover koşmadı) → fail-closed
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
TEST_DIR = REPO_ROOT / "_calisma" / "CIKTI"
CHECK_UNIT_TESTS_LIST = TEST_DIR / "check_unit_tests.list"

# HOOK_COVERAGE okuması TEK KAYNAKTAN: sync_check_unit_tests'in AST tabanlı
# parse'ı (eski kopya span sezgisi gövde-içi bir yorumdaki `],`'da bloğu
# kırpar — ölçüldü).
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from sync_check_unit_tests import read_hook_coverage as _read_hook_coverage  # noqa: E402

# Full-discover'da kırmızı olabilen ama drift ANLAMI taşımayan dosyalar: kendi
# testleri yoktur / ayrı CI job'larında koşar / ortam bağımlıdır.
EXEMPT_FROM_DIFF_GUARD = frozenset({
    "test_coverage_report.py",
    "test_test_coverage_report.py",
    "test_all_hooks_smoke.py",
    "test_preview_reload_smoke.py",
    "test_budget_scan.js",
    "test_dashboard_playwright_smoke.py",
})

# unittest hata başlıkları: "FAIL: test_x (test_mod.Sinif.test_x)".
# Alt-test/durum çıktıları parantez içermez ve gerçek test hatası değildir
# (ör. "FAIL: README skills index drift") — onlar bu desene takılmaz.
_FAILING_RE = re.compile(r"^(?:FAIL|ERROR): \S+ \(([A-Za-z_]\w*)\.", re.MULTILINE)
_RAN_RE = re.compile(r"Ran (\d+) tests")


def _failing_modules(output):
    """Tam discover çıktısından kırmızı testlerin MODÜL adlarını döndürür."""
    return set(_FAILING_RE.findall(output or ""))


def _drift_modules(output, registered, exempt):
    """Çıktıdaki kırmızı modüllerden kayıt dışı ve muaf olmayanları ayıklar.

    `registered` / `exempt` dosya adı (`.py`) taşıyabilir; modül adına indirilir.
    """
    def mod_names(names):
        return {n[:-3] if n.endswith(".py") else n for n in names}

    return _failing_modules(output) - mod_names(registered) - mod_names(exempt)


def read_hook_coverage_check_unit_tests():
    """HOOK_COVERAGE['check-unit-tests'] listesi — AST tabanlı paylaşımlı
    parse'tan (sync_check_unit_tests tek kaynak); yalnız .py girdileri
    (bu gate'in discover evreni)."""
    entries = _read_hook_coverage(str(TEST_DIR / "test_coverage_report.py"))
    return {e for e in entries if e.endswith(".py")}


def _registered_tests():
    """Kayıtlı bataryanın koştuğu dosyalar: manifest ∪ HOOK_COVERAGE (py)."""
    listed = set()
    if CHECK_UNIT_TESTS_LIST.exists():
        listed = {ln.strip() for ln in
                  CHECK_UNIT_TESTS_LIST.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.strip().startswith("#")}
    return listed | read_hook_coverage_check_unit_tests()


def _run_full_discover():
    """`unittest discover -p 'test_*.py'` koşar → (exit_code, combined, n_tests)."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", str(TEST_DIR), "-p", "test_*.py"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=1800)
    combined = (proc.stdout or "") + (proc.stderr or "")
    m = _RAN_RE.search(combined)
    return proc.returncode, combined, int(m.group(1)) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kayıt dışı kırmızı test kapısı.")
    ap.add_argument("--json-out", help="sonuç JSON'a yaz (CI artifact için)")
    args = ap.parse_args(argv)

    registered = _registered_tests()
    on_disk = {p.name for p in TEST_DIR.glob("test_*.py")}
    unregistered = on_disk - registered - EXEMPT_FROM_DIFF_GUARD
    orphan_registrations = registered - on_disk

    exit_code, output, n_tests = _run_full_discover()
    if n_tests is None:
        print("CI-FULL-DISCOVER-DRIFT-GUARD: HATA — full discover koşmadı "
              "(ortam/sözdizimi hatası), fail-closed.", file=sys.stderr)
        return 2

    drift = sorted(_drift_modules(output, registered, EXEMPT_FROM_DIFF_GUARD))

    summary = {
        "full_discover": {
            "exit_code": exit_code,
            "tests_ran": n_tests,
            "passed": exit_code == 0,
        },
        "registered_files": len(registered & on_disk),
        "unregistered_test_files": sorted(unregistered),
        "orphan_registrations_not_on_disk": sorted(orphan_registrations),
        "drift_modules": drift,
        "drift_detected": bool(drift),
        "verdict": "FAIL" if drift else "PASS",
    }

    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(summary, indent=2))

    p = lambda *a: print(*a, file=sys.stderr)  # noqa: E731 — okuma kolaylığı

    if drift:
        p("CI-FULL-DISCOVER-DRIFT-GUARD: FAIL")
        p(f"  full discover: RED (exit {exit_code}, {n_tests} tests)")
        p("  kayıt dışı ve muaf OLMAYAN kırmızı dosyalar:")
        for name in drift:
            p(f"    - {name}.py")
        p("  → Bu dosyalar manifest'e (check_unit_tests.list) veya HOOK_COVERAGE'a")
        p("    eklenmeli: `python3 sync_check_unit_tests.py --update`.")
        return 1

    p("CI-FULL-DISCOVER-DRIFT-GUARD: PASS")
    p(f"  full discover: {'GREEN' if exit_code == 0 else 'RED'} "
      f"(exit {exit_code}, {n_tests} tests)")
    p(f"  kayıtlı dosya: {len(registered & on_disk)}, "
      f"kayıt dışı: {len(unregistered)}")
    if unregistered:
        p("  not: kayıt dışı dosyalar discover'da yeşil — henüz drift yok.")
    if orphan_registrations:
        p(f"  uyarı: manifest'te var ama diskte yok: "
          f"{', '.join(sorted(orphan_registrations))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
