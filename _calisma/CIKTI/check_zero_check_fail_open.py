#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_zero_check_fail_open.py — tek meta-kapı: "başarı" sıfır denetimle gelirse FAIL.

Kapsanan beş fail-open ailesi (hepsi bu depoda ölçülmüş gerçek olaylardır):

  1. a11y gate        — axe.run() boş/engine'siz sonuç döner, kapı PASS der.
  2. keyboard scope   — role=button taraması 0 element görür, test boşuna geçer.
  3. Playwright       — tüm testler SKIP, runner "OK" diyip rc=0 döner.
  4. prettier         — --require-prettier verilir ama 0 dosya → SKIP/rc=0.
  5. changelog hook   — --check rc=2 (ölçüm yapılamadı) → prune → rc=0.

Her sonda GERÇEK giriş noktasını çalıştırır (kopya/paralel uygulama değil):

  * a11y_gate.main() — collect() sahte bir "tüm kovalar boş" axe yanıtı döndürür.
  * test_dashboard_keyboard_nav.keyboard_scope_verdict(0, []) — gerçek guard.
  * check_unit_tests_hook.sh — all-skip sınıflandırıcısı ve kablolaması.
  * check_prettier_format.py --require-prettier (dosyasız).
  * update_changelog_hook.sh — mock gen_changelog rc=2 + başarılı prune.

Ölçülemeyen sonda PASS değildir: istisna/eksik dosya/ayrıştırılamayan çıktı
`error` döner ve kapı kırmızı olur (fail-closed).

Kullanım:
  python3 _calisma/CIKTI/check_zero_check_fail_open.py
  python3 _calisma/CIKTI/check_zero_check_fail_open.py --json
  python3 _calisma/CIKTI/check_zero_check_fail_open.py --unittest-log LOG

`--unittest-log` modu runner'ın kullandığı hızlı yoldur: log "Ran N" ve
"OK (skipped=K)" satırlarından gerçekten koşan test sayısını çıkarır.
Çıkış: 0 = en az bir gerçek test koştu, 1 = vakuum/ölçüm yok, 2 = kullanım.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent

_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
_SKIPPED_RE = re.compile(r"skipped=(\d+)")


@dataclass(frozen=True)
class ProbeResult:
    key: str
    title: str
    status: str          # ok | vacuous | error
    detail: str


def _result(key, title, status, detail):
    return ProbeResult(key, title, status, detail)


def classify_unittest_log(text, exit_code=0):
    """unittest çıktısını sınıflandır: gerçek test koştu mu?

    `exit_code != 0` runner'ın zaten kırmızı olduğu anlamına gelir (başarı
    raporu değil) → ok. Aksi halde "Ran N" ve "OK (skipped=K)" birlikte
    okunur; N-K <= 0 ise hiçbir test koşmamıştır → vacuous.
    """
    if exit_code != 0:
        return _result("playwright_skips", "Playwright/unittest skips", "ok",
                       "runner zaten rc=%d (başarı raporu değil)" % exit_code)

    # Testin kendi stdout'u "Ran ..." / "OK" satırları basabilir; ÖZET her
    # zaman sonuncudur. İlk eşleşmeyi almak, erken bir "OK" satırının
    # all-skip özetini maskelemesine yol açardı (ölçüldü: 4/4 skip yeşil).
    #
    # ÖZET SON SATIR OLMAK ZORUNDA DEĞİL (ölçüldü 2026-10-21): süitlerin bir
    # kısmı unittest özetinden SONRA kendi raporunu basıyor (ör.
    # test_status_checks "SONUÇ/Durum" bloğu, test_check_action_pins
    # "SONUÇ: PASS — 1 PASS..."). "Son satır OK olmalı" kuralı bu dosyaları
    # topluca VACUOUS sayıp bataryayı kalıcı kırmızı tutuyordu (36 dosya).
    # Kural: özet, son "Ran N tests" satırından SONRAKİ ilk boş-olmayan
    # satırdır. O satır özet değilse (iç içe bir unittest koşumu araya
    # girmiş olabilir) bir önceki "Ran" eşleşmesine dönülür. Eşleşme hiç
    # yoksa vakum: rc=0 tek başına kanıt değildir.
    ran_matches = list(_RAN_RE.finditer(text or ""))
    if not ran_matches:
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "çıktıda 'Ran N tests' yok — ölçüm yok")

    ran = 0
    summary = None
    for ran_match in reversed(ran_matches):
        # `_RAN_RE` "... in " ile biter; süre aynı satırda kalır → satırın
        # kalanını at, özeti SONRAKİ satırlarda ara.
        rest = text[ran_match.end():]
        rest = rest.split("\n", 1)[1] if "\n" in rest else ""
        nxt = next((ln.strip() for ln in rest.splitlines() if ln.strip()), "")
        hit = re.match(r"^OK(?: \(([^)]*)\))?$", nxt)
        if hit is not None:
            ran = int(ran_match.group(1))
            summary = hit
            break
    if summary is None:
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "OK özet satırı yok — rc=0 olsa da sonuç doğrulanamaz")

    skipped_match = _SKIPPED_RE.search(summary.group(1) or "")
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    executed = ran - skipped
    if executed <= 0:
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "Ran %d, skipped=%d → 0 gerçek test" % (ran, skipped))
    return _result("playwright_skips", "Playwright/unittest skips", "ok",
                   "Ran %d, skipped=%d → %d gerçek test"
                   % (ran, skipped, executed))


# ------------------------------------------------------------------ probes

def probe_a11y_gate():
    """Boş axe sonucu PASS'e dönüşüyor mu? Gerçek main() koşulur."""
    try:
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        import a11y_gate  # noqa: PLC0415 (probe import)
    except Exception as exc:  # noqa: BLE001 — ölçülemez = FAIL
        return _result("a11y_gate", "a11y gate — boş axe sonucu", "error",
                       "a11y_gate import edilemedi: %s" % exc)

    # Dört kova da boş + engine damgası var: en aldatıcı "sorun yok" biçimi.
    empty_scan = {
        "violations": [], "passes": [], "incomplete": [],
        "inapplicable": [], "testEngine": {"version": "4.10.3"},
    }

    def fake_collect(**kwargs):
        return (empty_scan, "http://127.0.0.1:1/preview.html",
                {"csp_bypass": False, "csp_bypass_reason": None})

    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_a11y_") as td:
            out_path = Path(td) / "a11y_report.json"
            with mock.patch.object(a11y_gate, "collect", side_effect=fake_collect):
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = a11y_gate.main([
                        "--base-url", "http://127.0.0.1:1",
                        "--output", str(out_path),
                    ])
            report = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _result("a11y_gate", "a11y gate — boş axe sonucu", "error",
                       "main() koşturulamadı: %s" % exc)

    if rc == 0 or report.get("verdict") != "FAIL":
        return _result("a11y_gate", "a11y gate — boş axe sonucu", "vacuous",
                       "boş axe sonucu rc=%r verdict=%r ile geçti"
                       % (rc, report.get("verdict")))
    if "axe sonucu geçersiz" not in (report.get("error") or ""):
        return _result("a11y_gate", "a11y gate — boş axe sonucu", "error",
                       "FAIL gerekçesi beklenen 'axe sonucu geçersiz' değil: %r"
                       % report.get("error"))
    return _result("a11y_gate", "a11y gate — boş axe sonucu", "ok",
                   "boş/engine'li axe sonucu FAIL + rc=1")


def probe_keyboard_scope():
    """0 elementlik klavye-kapsam taraması gerçekten kırmızı mı?"""
    try:
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        import test_dashboard_keyboard_nav as keyboard  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _result("keyboard_scope", "keyboard scope scan", "error",
                       "test modülü import edilemedi: %s" % exc)

    guard = getattr(keyboard, "keyboard_scope_verdict", None)
    if guard is None:
        return _result("keyboard_scope", "keyboard scope scan", "vacuous",
                       "keyboard_scope_verdict guard'ı yok — 0 element geçer")
    try:
        guard(0, [])
    except AssertionError:
        pass
    except Exception as exc:  # noqa: BLE001
        return _result("keyboard_scope", "keyboard scope scan", "error",
                       "guard beklenmeyen istisna üretti: %s" % exc)
    else:
        return _result("keyboard_scope", "keyboard scope scan", "vacuous",
                       "guard 0 elementte hata vermedi")

    if guard(1, []) != []:
        return _result("keyboard_scope", "keyboard scope scan", "error",
                       "guard pozitif taramada ihlalleri bozmadı")

    # Guard'ın gerçek tarayıcı testine BAĞLI olduğunu da doğrula: fonksiyon
    # durup çağrı kaldırılırsa tarama yine boş liste üzerinde yeşil kalırdı.
    try:
        source = (SCRIPT_DIR / "test_dashboard_keyboard_nav.py").read_text(
            encoding="utf-8")
    except OSError as exc:
        return _result("keyboard_scope", "keyboard scope scan", "error",
                       "test kaynağı okunamadı: %s" % exc)
    if 'keyboard_scope_verdict(scan["scanned"], scan["violators"])' not in source:
        return _result("keyboard_scope", "keyboard scope scan", "vacuous",
                       "tarayıcı testi guard'ı çağırmıyor — bağlantı kopuk")
    return _result("keyboard_scope", "keyboard scope scan", "ok",
                   "0 element → AssertionError; tarayıcı testi guard'a bağlı")


def probe_playwright_skips():
    """All-skip sınıflandırıcısı ve runner kablolaması birlikte çalışıyor mu?"""
    all_skip = classify_unittest_log(
        "Ran 18 tests in 0.000s\n\nOK (skipped=18)\n")
    real = classify_unittest_log(
        "Ran 18 tests in 1.0s\n\nOK (skipped=2)\n")
    if all_skip.status != "vacuous":
        return _result("playwright_skips", "Playwright/unittest skips", "error",
                       "all-skip sınıflandırıcısı vakuumu görmedi: %s"
                       % all_skip.detail)
    if real.status != "ok":
        return _result("playwright_skips", "Playwright/unittest skips", "error",
                       "2/18 skip gerçek koşum sayılmadı: %s" % real.detail)

    try:
        hook = (SCRIPT_DIR / "check_unit_tests_hook.sh").read_text(encoding="utf-8")
    except OSError as exc:
        return _result("playwright_skips", "Playwright/unittest skips", "error",
                       "runner okunamadı: %s" % exc)

    if "--unittest-log" not in hook:
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "runner all-skip'i sınıflandırmıyor (--unittest-log yok)")
    if "vacuous " not in hook:
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "runner vakum sonucunu FAIL'e çevirmiyor")
    if re.search(r"-m unittest[^\n]*>\s*/dev/null", hook):
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "runner test çıktısını /dev/null'a atıyor — PASS/all-skip ayrımsız")

    # Somut kanıt: tarayıcısız ortamda klavye süiti TAMAMEN skip olmamalı.
    # (Aynı dosya, aynı unittest; yalnız playwright import'u engellenir.)
    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_nopw_") as td:
            fake = Path(td) / "playwright"
            fake.mkdir()
            (fake / "__init__.py").write_text(
                'raise ImportError("playwright blocked for probe")\n',
                encoding="utf-8")
            env = os.environ.copy()
            before = env.get("PYTHONPATH")
            env["PYTHONPATH"] = td + (os.pathsep + before if before else "")
            proc = subprocess.run(
                [sys.executable, "-m", "unittest",
                 "test_dashboard_keyboard_nav"],
                cwd=str(SCRIPT_DIR), capture_output=True, text=True,
                env=env, timeout=60,
            )
    except Exception as exc:  # noqa: BLE001
        return _result("playwright_skips", "Playwright/unittest skips", "error",
                       "tarayıcısız koşum yapılamadı: %s" % exc)

    no_browser = classify_unittest_log(proc.stdout + proc.stderr,
                                       proc.returncode)
    if proc.returncode != 0:
        return _result("playwright_skips", "Playwright/unittest skips", "error",
                       "klavye süiti tarayıcısız koşumda kırmızı (rc=%d): %s"
                       % (proc.returncode, proc.stderr[-300:]))
    if no_browser.status != "ok":
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "tarayıcısız ortamda dosya tamamen SKIP: %s"
                       % no_browser.detail)
    return _result("playwright_skips", "Playwright/unittest skips", "ok",
                   "all-skip → vacuous; tarayıcısız katman koşuyor (%s)"
                   % no_browser.detail)


def probe_prettier():
    """--require-prettier ile 0 dosya SKIP/rc=0 olabiliyor mu?"""
    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_prettier_") as td:
            env = os.environ.copy()
            env.pop("PRETTIER_BIN", None)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "check_prettier_format.py"),
                 "--require-prettier"],
                cwd=td, capture_output=True, text=True, env=env, timeout=30,
            )
    except Exception as exc:  # noqa: BLE001
        return _result("prettier", "prettier — 0 dosya", "error",
                       "check_prettier_format.py koşturulamadı: %s" % exc)

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return _result("prettier", "prettier — 0 dosya", "vacuous",
                       "0 dosya ile rc=0 döndü: %s" % out.strip()[:200])
    if "OK (0" in out:
        return _result("prettier", "prettier — 0 dosya", "vacuous",
                       "0 dosya 'OK' sayıldı: %s" % out.strip()[:200])
    if "SKIP" in out and "HATA" not in out:
        return _result("prettier", "prettier — 0 dosya", "vacuous",
                       "--require-prettier SKIP'e düştü: %s" % out.strip()[:200])
    if "denetim yapılamaz" not in out.lower():
        return _result("prettier", "prettier — 0 dosya", "error",
                       "beklenen fail-closed gerekçesi yok (rc=%d): %s"
                       % (proc.returncode, out.strip()[:200]))
    return _result("prettier", "prettier — 0 dosya", "ok",
                   "0 dosya fail-closed (rc=%d)" % proc.returncode)


_CHANGELOG_MOCK = """#!/usr/bin/env python3
import sys
mode = sys.argv[1] if len(sys.argv) > 1 else ""
# Ölçüm YOK: --check rc=2. --prune ise "başarılı" ama hiçbir şey yapmaz.
if mode == "--check":
    sys.exit(2)
if mode == "--prune":
    sys.exit(0)
sys.exit(0)
"""

_CHANGELOG_TABLE = (
    "# test repo\n\n## Değişiklik Geçmişi\n\n"
    "| Tarih | Kategori | Değişiklik | Commit |\n"
    "|---|---|---|---|\n"
    "| 2026-08-23 | fix | (test) base | `aaaa1111` |\n"
)


def probe_changelog_hook():
    """--check rc=2 (ölçüm yok) prune ile 'başarıya' dönüşüyor mu?"""
    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_changelog_") as td:
            root = Path(td)
            cikti = root / "_calisma" / "CIKTI"
            cikti.mkdir(parents=True)
            shutil.copy2(SCRIPT_DIR / "update_changelog_hook.sh",
                         cikti / "update_changelog_hook.sh")
            # Hook, unstaged-delta korumasını `check_unstaged_delta`'dan
            # İMPORT eder (tek kaynak). Modül kopyalanmazsa sandbox'ta
            # ModuleNotFoundError → hook "ölçüm yapılamadı" değil "koruma
            # ölçülemedi" der ve sonda ölçmek istediği yolu hiç görmez
            # (ölçüldü 2026-10-21). Fixture, hook'un GERÇEK bağımlılığını
            # taşımak zorunda: aksi hâlde sonda kendi kurulum hatasını ölçer.
            shutil.copy2(SCRIPT_DIR / "check_unstaged_delta.py",
                         cikti / "check_unstaged_delta.py")
            (cikti / "gen_changelog.py").write_text(
                _CHANGELOG_MOCK, encoding="utf-8")
            (root / "README.md").write_text(_CHANGELOG_TABLE, encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "PUBLISH_SCENARIO.md").write_text(
                _CHANGELOG_TABLE, encoding="utf-8")

            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True,
                               capture_output=True, text=True)

            git("init", "-q")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "test")
            git("config", "commit.gpgsign", "false")
            git("add", "-A")
            git("commit", "-q", "-m", "test: base")

            proc = subprocess.run(
                ["bash", str(cikti / "update_changelog_hook.sh")],
                cwd=root, capture_output=True, text=True, timeout=30,
            )
    except Exception as exc:  # noqa: BLE001
        return _result("changelog_hook", "changelog hook — ölçüm yok", "error",
                       "hook sandbox'ı koşturulamadı: %s" % exc)

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return _result("changelog_hook", "changelog hook — ölçüm yok", "vacuous",
                       "--check rc=2 iken prune sonrası rc=0: %s"
                       % out.strip()[:200])
    if "ölçüm yapılamadı" not in out:
        return _result("changelog_hook", "changelog hook — ölçüm yok", "error",
                       "beklenen fail-closed gerekçesi yok (rc=%d): %s"
                       % (proc.returncode, out.strip()[:200]))
    return _result("changelog_hook", "changelog hook — ölçüm yok", "ok",
                   "rc=2 ölçüm hatası bloke edildi (rc=%d)" % proc.returncode)


PROBES = (
    ("a11y_gate", "a11y gate — boş axe sonucu", probe_a11y_gate),
    ("keyboard_scope", "keyboard scope scan", probe_keyboard_scope),
    ("playwright_skips", "Playwright/unittest skips", probe_playwright_skips),
    ("prettier", "prettier — 0 dosya", probe_prettier),
    ("changelog_hook", "changelog hook — ölçüm yok", probe_changelog_hook),
)


def run_probes():
    results = []
    for key, title, fn in PROBES:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001 — sonda çökmesi = FAIL
            results.append(_result(key, title, "error",
                                   "sonda çöktü: %s: %s"
                                   % (type(exc).__name__, exc)))
    return results


# -------------------------------------------------------------------- CLI

def _write_json(document):
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Meta-kapı: başarı raporu sıfır gerçek denetimle gelirse FAIL.")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a tek JSON belgesi yaz (tanılama stderr'e)")
    ap.add_argument("--unittest-log", metavar="PATH",
                    help="unittest log'unu sınıflandır (runner hızlı yolu)")
    args = ap.parse_args(argv)

    if args.unittest_log:
        try:
            text = Path(args.unittest_log).read_text(encoding="utf-8",
                                                     errors="replace")
        except OSError as exc:
            print("HATA: unittest log okunamadı: %s" % exc, file=sys.stderr)
            return 2
        result = classify_unittest_log(text, 0)
        if args.json:
            _write_json({
                "verdict": "PASS" if result.status == "ok" else "FAIL",
                "status": result.status,
                "detail": result.detail,
            })
        else:
            print("%s: %s" % (result.status.upper(), result.detail))
        return 0 if result.status == "ok" else 1

    results = run_probes()
    if not results:
        # Boş kayıt = hiçbir kontrol ölçülmedi; "0/0 PASS" meta fail-open'tır.
        print("HATA: sonda kaydı BOŞ — meta-kapı hiçbir kontrol ölçmedi "
              "(fail-closed).", file=sys.stderr)
        return 1
    bad = [r for r in results if r.status != "ok"]
    verdict = "PASS" if not bad else "FAIL"

    if args.json:
        _write_json({
            "verdict": verdict,
            "probes": [{
                "key": r.key, "title": r.title,
                "status": r.status, "detail": r.detail,
            } for r in results],
        })
        for r in bad:
            print("%s: %s — %s" % (r.key.upper(), r.status, r.detail),
                  file=sys.stderr)
    else:
        for r in results:
            print("[%-7s] %-28s %s" % (r.status.upper(), r.key, r.detail))
        print("verdict: %s (%d/%d)" % (verdict, len(results) - len(bad),
                                       len(results)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
