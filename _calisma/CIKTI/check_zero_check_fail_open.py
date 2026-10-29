#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_zero_check_fail_open.py — tek meta-kapı: "başarı" sıfır denetimle gelirse FAIL.

Kapsanan beş fail-open ailesi (hepsi bu depoda ölçülmüş gerçek olaylardır):

  1. a11y gate        — tarama ÇÖKER (collect istisna atar) ama kapı PASS der; ayrıca
                        negatif kontrol: gerçekten temiz tarama PASS kalmalı
                        (main'in test_empty_scan_passes sözleşmesi: "violations
                        boş" tek başına arıza değildir — arıza, taramanın hiç
                        koşmamasıdır).
  2. keyboard scope   — role=button taraması 0 element görür, test boşuna geçer.
  3. Playwright       — tüm testler SKIP, runner "OK" diyip rc=0 döner.
  4. prettier         — biçim-uyumsuz dosya varken kapı OK/rc=0 der (vakum
                        geçiş); negatif kontrol: biçimli dosya OK kalır.
  5. changelog hook   — --check rc=2 (ölçüm yapılamadı) → prune → rc=0.

Her sonda GERÇEK giriş noktasını çalıştırır (kopya/paralel uygulama değil):

  * a11y_gate.main() — collect() sahte bir "tüm kovalar boş" axe yanıtı döndürür.
  * test_dashboard_keyboard_nav.keyboard_scope_verdict(0, []) — gerçek guard.
  * check_unit_tests_hook.sh — all-skip sınıflandırıcısı ve kablolaması.
  * check_prettier_format.py — gerçek dosya argümanıyla biçim-uyumsuz/biçimli.
  * update_changelog_hook.sh — mock gen_changelog rc=2 + başarılı prune.

Ölçülemeyen sonda PASS değildir: istisna/eksik dosya/ayrıştırılamayan çıktı
`error` döner ve kapı kırmızı olur (fail-closed).

Kullanım:
  python3 _calisma/CIKTI/check_zero_check_fail_open.py
  python3 _calisma/CIKTI/check_zero_check_fail_open.py --json
  python3 _calisma/CIKTI/check_zero_check_fail_open.py --unittest-log LOG
  python3 _calisma/CIKTI/check_zero_check_fail_open.py --unittest-log LOG --suite test_x.py

`--unittest-log` modu runner'ın kullandığı hızlı yoldur: log "Ran N" ve
"OK (skipped=K)" satırlarından gerçekten koşan test sayısını çıkarır.
Çıkış: 0 = en az bir gerçek test koştu (veya --suite ile izinli ölçülü
tam-skip → ALLOWED), 1 = vakuum/ölçüm yok, 2 = kullanım. İzinli tam-skip
kararının tablosu: docs/CI_GATE_TRIAGE.md "Environment-skip legitimacy";
kayıt + sabitleme: CI_FULL_SKIP_ALLOWANCE + TestCiFullSkipAllowlist.
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


# --- CI'da meşru sayılan ÖLÇÜMLÜ tam-skip (karar + gerekçe) -----------------
# Karar tablosu: docs/CI_GATE_TRIAGE.md "Environment-skip legitimacy".
# Liste bilinçli KISA'dır: yalnızca birim-test adımı çalışırken aracı KURMAYAN
# bir workflow'a bağlı manifest dosyaları girebilir. İçerik
# TestCiFullSkipAllowlist ile birebir sabitlenir — ekleme/çıkarma, karar testi
# ve dokümanı aynı commit'te değiştirmeyi zorunlu kılar.
CI_FULL_SKIP_ALLOWANCE = {
    "test_z3_slide_reproducibility.py":
        "tectonic/TeXLive yalnız determinism-trend workflow'unda kurulur; "
        "verify.yml birim-adımı aracı kurmaz (skip: 'tectonic yok')",
}


def _normalize_suite(name):
    """Manifest girişi/CLI adını kanonik `test_x.py` biçimine indirger."""
    if not name:
        return None
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    return base if base.endswith(".py") else base + ".py"


@dataclass(frozen=True)
class ProbeResult:
    key: str
    title: str
    status: str          # ok | allowed | vacuous | error
    detail: str


def _result(key, title, status, detail):
    return ProbeResult(key, title, status, detail)


def classify_unittest_log(text, exit_code=0, suite=None):
    """unittest çıktısını sınıflandır: gerçek test koştu mu?

    `exit_code != 0` runner'ın zaten kırmızı olduğu anlamına gelir (başarı
    raporu değil) → ok. Aksi halde "Ran N" ve "OK (skipped=K)" birlikte
    okunur; N-K <= 0 ise hiçbir test koşmamıştır → vacuous.

    `suite` (manifest girişi) verilir ve sonuç ÖLÇÜMLÜ tam-skip ise
    (Ran N>0, skipped=N) CI_FULL_SKIP_ALLOWANCE kayıtlı dosya ALLOWED
    döner (rc=0); ölçüm yokluğu asla allowlist ile kurtarılmaz.
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

    # Test-başına satır sayımı önceliklidir (-v logu): setUpClass/
    # setUpModule sahte girdileri "skipped="e girer ama test RAN'a girmez →
    # "Ran - skipped" aritmetiği gerçekte test koşan dosyayı sahte VACUOUS
    # yapar (ölçüldü: webkit smoke — statik katman koşuyorken 0 sayılmıştı).
    # "... ok" satırı ancak bir test gövdesi gerçekten çalışmışsa basılır;
    # ok-satırı yoksa (saf özet logları) aritmetiğe düşülür — ölçüm
    # yokluğu asla kurtarılmaz.
    verbose_ok = len(re.findall(r"\.\.\. ok$", text or "", re.M))
    if verbose_ok > 0:
        executed = verbose_ok
        ok_detail = ("test-başına sayım: %d gerçek test (Ran %d, skipped=%d)"
                     % (executed, ran, skipped))
    else:
        executed = ran - skipped
        ok_detail = ("Ran %d, skipped=%d → %d gerçek test"
                     % (ran, skipped, executed))
    if executed <= 0:
        key = _normalize_suite(suite)
        if ran > 0 and key in CI_FULL_SKIP_ALLOWANCE:
            return _result("playwright_skips", "Playwright/unittest skips",
                           "allowed",
                           "Ran %d, skipped=%d — %s"
                           % (ran, skipped, CI_FULL_SKIP_ALLOWANCE[key]))
        return _result("playwright_skips", "Playwright/unittest skips", "vacuous",
                       "Ran %d, skipped=%d → 0 gerçek test" % (ran, skipped))
    return _result("playwright_skips", "Playwright/unittest skips", "ok",
                   ok_detail)


# ------------------------------------------------------------------ probes

def _run_a11y_main(collect_side_effect):
    """a11y_gate.main()'i verilen collect davranışıyla koşar; (rc, report)."""
    import a11y_gate  # noqa: PLC0415 (probe import)

    with tempfile.TemporaryDirectory(prefix="zero_check_a11y_") as td:
        out_path = Path(td) / "a11y_report.json"
        with mock.patch.object(a11y_gate, "collect",
                               side_effect=collect_side_effect):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = a11y_gate.main([
                    "--base-url", "http://127.0.0.1:1",
                    "--output", str(out_path),
                ])
        return rc, json.loads(out_path.read_text(encoding="utf-8"))


def probe_a11y_gate():
    """Çöken tarama PASS'e dönüşüyor mu? Gerçek main() iki yönle koşulur.

    main() 2026-10-24'ten beri yüzey/tema başına koşar ve `collect`
    `(results, page_url)` döndürür (eski 3-tuple sözleşmesi kalktı). Boş
    `violations` listesi tek başına arıza DEĞİLDİR (temiz sayfa); asıl
    fail-open riski, taramanın hiç koşmamasının "sorun yok" sayılmasıdır.
    """
    try:
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        import a11y_gate  # noqa: PLC0415 (probe import)
    except Exception as exc:  # noqa: BLE001 — ölçülemez = FAIL
        return _result("a11y_gate", "a11y gate — çöken tarama", "error",
                       "a11y_gate import edilemedi: %s" % exc)

    def crashing_collect(*_args, **_kwargs):
        raise RuntimeError("probe: tarayıcı/sunucu arızası")

    def clean_collect(*_args, **_kwargs):
        return ({"violations": [], "incomplete": []},
                "http://127.0.0.1:1/preview.html")

    try:
        rc, report = _run_a11y_main(crashing_collect)
    except Exception as exc:  # noqa: BLE001
        return _result("a11y_gate", "a11y gate — çöken tarama", "error",
                       "main() koşturulamadı: %s" % exc)

    if rc == 0 or report.get("verdict") != "FAIL":
        return _result("a11y_gate", "a11y gate — çöken tarama", "vacuous",
                       "tarama çökmesi rc=%r verdict=%r ile geçti"
                       % (rc, report.get("verdict")))
    if "tarama arızası" not in (report.get("error") or ""):
        return _result("a11y_gate", "a11y gate — çöken tarama", "error",
                       "FAIL gerekçesi beklenen 'tarama arızası' değil: %r"
                       % report.get("error"))

    # Negatif kontrol: gerçekten temiz tarama PASS kalmalı (kapı kör değil).
    rc_clean, report_clean = _run_a11y_main(clean_collect)
    if rc_clean != 0 or report_clean.get("verdict") != "PASS":
        return _result("a11y_gate", "a11y gate — çöken tarama", "error",
                       "temiz tarama PASS olmadı (rc=%r verdict=%r)"
                       % (rc_clean, report_clean.get("verdict")))
    return _result("a11y_gate", "a11y gate — çöken tarama", "ok",
                   "çöken tarama FAIL + rc=1; temiz tarama PASS")


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


def _run_prettier_gate(path):
    env = os.environ.copy()
    env.pop("PRETTIER_BIN", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_prettier_format.py"), str(path)],
        cwd=str(path.parent), capture_output=True, text=True, env=env,
        timeout=60)


def probe_prettier():
    """Biçim-uyumsuz dosya varken kapı "OK" diyebiliyor mu?

    main'in kapısı (2026-10-25) ayrı bir `--require-prettier` bayrağı
    taşımaz: dosya yoksa SKIP, prettier yoksa SKIP, dosya varsa prettier
    gerçekten koşar. Fail-open ölçüsü bu yüzden "vakum OK" değil "bozuk
    dosyayı OK sayma": biçim-uyumsuz dosya rc!=0 vermeli, biçimli dosya
    rc=0 (negatif kontrol — kapı körü körüne kırmızı değil).
    """
    try:
        import check_prettier_format as gate  # noqa: PLC0415 (probe import)
    except Exception as exc:  # noqa: BLE001
        return _result("prettier", "prettier — biçim denetimi", "error",
                       "check_prettier_format import edilemedi: %s" % exc)
    if not gate.PRETTIER.is_file():
        return _result("prettier", "prettier — biçim denetimi", "error",
                       "prettier bulunamadı (%s) — ölçüm imkânsız"
                       % gate.PRETTIER)

    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_prettier_") as td:
            root = Path(td)
            bad = root / "bad.js"
            bad.write_text("const a=1\n", encoding="utf-8")
            good = root / "good.js"
            good.write_text("const a = 1;\n", encoding="utf-8")
            bad_proc = _run_prettier_gate(bad)
            good_proc = _run_prettier_gate(good)
    except Exception as exc:  # noqa: BLE001
        return _result("prettier", "prettier — biçim denetimi", "error",
                       "check_prettier_format.py koşturulamadı: %s" % exc)

    bad_out = ((bad_proc.stdout or "") + (bad_proc.stderr or "")).strip()
    good_out = ((good_proc.stdout or "") + (good_proc.stderr or "")).strip()
    if bad_proc.returncode == 0:
        return _result("prettier", "prettier — biçim denetimi", "vacuous",
                       "biçim-uyumsuz dosya rc=0 ile geçti: %s" % bad_out[:200])
    if "SKIP" in bad_out:
        return _result("prettier", "prettier — biçim denetimi", "vacuous",
                       "biçim denetimi SKIP'e düştü: %s" % bad_out[:200])
    if good_proc.returncode != 0 or "OK (1 dosya" not in good_out:
        return _result("prettier", "prettier — biçim denetimi", "error",
                       "biçimli dosya PASS olmadı (rc=%d): %s"
                       % (good_proc.returncode, good_out[:200]))
    return _result("prettier", "prettier — biçim denetimi", "ok",
                   "biçim-uyumsuz dosya FAIL; biçimli dosya OK (1 dosya)")


_CHANGELOG_MOCK = """#!/usr/bin/env python3
import sys
# Ölçüm İMKÂNSIZ: `--check` de `--update` de rc=2 (gerçek gen_changelog'da
# ikisi aynı ön koşullara bağlı: git log boş / dosya yok / regex bozuk).
# Hook bu durumda `--update` başarısızlığını yutmamalı.
if "--check" in sys.argv or "--update" in sys.argv:
    sys.exit(2)
sys.exit(0)
"""

_CHANGELOG_TABLE = (
    "# test repo\n\n## Değişiklik Geçmişi\n\n"
    "| Tarih | Kategori | Değişiklik | Commit |\n"
    "|---|---|---|---|\n"
    "| 2026-08-23 | fix | (test) base | `aaaa1111` |\n"
)


def probe_changelog_hook():
    """--check rc=2 (ölçüm yok) hook'ta 'başarıya' dönüşüyor mu?

    main'in hook'u (2026-10-21'den beri) `--prune` çağırmaz; `--check`
    nonzero ise `--update` ile yeniden ölçer ve `--update` de düşerse
    fail-closed kapanır. Sonda tam bu çift-arıza yolunu koşar.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="zero_check_changelog_") as td:
            root = Path(td)
            cikti = root / "_calisma" / "CIKTI"
            cikti.mkdir(parents=True)
            shutil.copy2(SCRIPT_DIR / "update_changelog_hook.sh",
                         cikti / "update_changelog_hook.sh")
            # main'in hook'u yalnız gen_changelog.py + git'e bağlıdır
            # (`check_unstaged_delta` bağımlılığı 2026-10-21'de kaldırıldı);
            # fixture hook'un GERÇEK bağımlılıklarını taşır.
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
                       "--check ve --update rc=2 iken hook rc=0: %s"
                       % out.strip()[:200])
    if "gen_changelog --update başarısız" not in out:
        return _result("changelog_hook", "changelog hook — ölçüm yok", "error",
                       "beklenen fail-closed gerekçesi yok (rc=%d): %s"
                       % (proc.returncode, out.strip()[:200]))
    return _result("changelog_hook", "changelog hook — ölçüm yok", "ok",
                   "ölçüm imkânsız (--check+--update rc=2) bloke edildi (rc=%d)"
                   % proc.returncode)


PROBES = (
    ("a11y_gate", "a11y gate — çöken tarama", probe_a11y_gate),
    ("keyboard_scope", "keyboard scope scan", probe_keyboard_scope),
    ("playwright_skips", "Playwright/unittest skips", probe_playwright_skips),
    ("prettier", "prettier — biçim denetimi", probe_prettier),
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
    ap.add_argument("--suite", metavar="NAME",
                    help="log'un ait olduğu manifest dosyası — izinli ölçülü "
                         "tam-skip kararı (CI_FULL_SKIP_ALLOWANCE) yalnız bu "
                         "adla uygulanır")
    args = ap.parse_args(argv)

    if args.unittest_log:
        try:
            text = Path(args.unittest_log).read_text(encoding="utf-8",
                                                     errors="replace")
        except OSError as exc:
            print("HATA: unittest log okunamadı: %s" % exc, file=sys.stderr)
            return 2
        result = classify_unittest_log(text, 0, suite=args.suite)
        passed = result.status in ("ok", "allowed")
        if args.json:
            _write_json({
                "verdict": "PASS" if passed else "FAIL",
                "status": result.status,
                "detail": result.detail,
            })
        else:
            print("%s: %s" % (result.status.upper(), result.detail))
        return 0 if passed else 1

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
