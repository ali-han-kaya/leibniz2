#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_prestart.py — launchd PreStart kontrolü (preview mirror bayatlığı).

launchd'de PreStart anahtarı yoktur; plist'in ProgramArguments'u bu script'i
sunucunun YERİNE çalıştırır ve script denetimden GEÇERSE `--` sonrasındaki
sunucu komutunu exec eder (PID korunur → KeepAlive semantiği sunucuya uygulanır;
bayatlıkta sunucu HİÇ başlamaz, log'a ne eksik olduğu yazılır).

TCC-safe: yalnızca ~/Library altı okunur/yazılır (repo'ya DOKUNMAZ — launchd
GUI agent'ı repo'yu okuyamaz; mirror'ın var olma nedeni budur).

Denetimler (fail-closed):
  1) Zorunlu runtime dosyaları var mı?
       preview/: preview_server.py, _daemonize.py, preview.html
       verify/:  verify_delivery.py, verify_delivery.config.json,
                 daemon_http_test.py
  2) py_compile — preview_server.py/_daemonize.py bozuk (yarım sync) değil mi?
  3) Plist şablonu drift'i: preview-template/<label>.plist.tmpl kurulu
     plist'ten farklıysa (şablon yeniden üretilmiş ama plist bayat) → DRIFT.
  4) Yaş kıyası (WARN — fail-closed DEĞİL): mirror dosyaları şablondan ESKİYSE
     mirror bayat olabilir; yalnızca log'a not düşülür.

Exit kodları:
  0 = READY — --check-only: PASS yazar; aksi halde sunucu komutunu exec eder
  1 = BAYAT/EKSİK (dosya eksik, bozuk python, plist drift'i)
  2 = hata (argüman hatası, sunucu komutu yok)

Kullanım (plist ProgramArguments — şablon update_preview.sh'te):
  /usr/bin/python3 .../preview_prestart.py
      --preview-dir .../preview --verify-dir .../verify
      --label com.freebuff.preview-leibniz2
      --log .../prestart-<logname>.log
      --  .../preview_server.py --dir ... --preview-dir ... --port 8000 ...

Test: --check-only (sunucuyu başlatmaz, yalnızca denetler).
"""
import argparse
import os
import plistlib
import py_compile
import sys
import time

REQUIRED_PREVIEW = ("preview_server.py", "_daemonize.py", "preview.html")
REQUIRED_VERIFY = (
    "verify_delivery.py",
    "verify_delivery.config.json",
    "daemon_http_test.py",
)

EXIT_READY = 0
EXIT_STALE = 1
EXIT_ERROR = 2

# Yaş uyarı eşiği (saniye): mirror dosyası şablondan bu kadar ESKİYSE WARN.
# --bootstrap sırası (sync → plist) epsilon'unu eleyip gerçek bayatlığı yakalar.
AGE_WARN_SECONDS = 3600


def home():
    return os.path.expanduser("~")


def tmpl_dir_default():
    return os.path.join(home(), "Library", "Caches", "com.freebuff",
                        "preview-template")


def installed_plist_path(label):
    return os.path.join(home(), "Library", "LaunchAgents", "%s.plist" % label)


def render_tmpl(tmpl_path, values):
    """Şablonu {HOME,LABEL,LOGNAME,PORT,INTERVAL} ile doldur (sed eşdeğeri)."""
    with open(tmpl_path, "r", encoding="utf-8") as f:
        text = f.read()
    for key, val in values.items():
        text = text.replace("{{%s}}" % key, str(val))
    return text


def plist_values(installed):
    """Kurulu plist'ten placeholder değerlerini çıkar (tek kaynak: plist)."""
    with open(installed, "rb") as f:
        d = plistlib.load(f)
    args = d.get("ProgramArguments", []) or []

    def after(flag):
        try:
            return args[args.index(flag) + 1]
        except (ValueError, IndexError):
            return ""

    out = d.get("StandardOutPath") or ""
    return {
        "HOME": home(),
        "LABEL": d.get("Label", ""),
        "LOGNAME": os.path.basename(out).replace(".log", "") if out else "",
        "PORT": after("--port"),
        "INTERVAL": after("--interval"),
    }


def probe(preview_dir, verify_dir, label, tmpl_dir):
    """Denetimi koş. (problems, warnings) döner — her ikisi de sıralı liste."""
    problems = []
    warnings = []

    # 1) Zorunlu runtime dosyaları (mirror self-consistency — K17 EKSİK deseni)
    for name in REQUIRED_PREVIEW:
        p = os.path.join(preview_dir, name)
        if not os.path.isfile(p):
            problems.append("EKSİK: preview/%s (fresh_clone_setup.sh çalıştırın)" % name)
    for name in REQUIRED_VERIFY:
        p = os.path.join(verify_dir, name)
        if not os.path.isfile(p):
            problems.append("EKSİK: verify/%s (fresh_clone_setup.sh çalıştırın)" % name)

    # 2) Python bütünlüğü (yarım sync / bozuk kopya)
    for name in ("preview_server.py", "_daemonize.py"):
        p = os.path.join(preview_dir, name)
        if os.path.isfile(p):
            try:
                py_compile.compile(p, doraise=True)
            except py_compile.PyCompileError as e:
                problems.append("BOZUK: preview/%s (py_compile: %s)" % (name, e))

    # 3) Plist şablonu drift'i (şablon yeniden üretildi ama kurulu plist bayat)
    tmpl = os.path.join(tmpl_dir, "%s.plist.tmpl" % label)
    installed = installed_plist_path(label)
    if os.path.isfile(tmpl) and os.path.isfile(installed):
        try:
            values = plist_values(installed)
            rendered = render_tmpl(tmpl, values)
            with open(installed, "r", encoding="utf-8") as f:
                cur = f.read()
            if rendered != cur:
                problems.append(
                    "DRIFT: kurulu plist şablondan farklı "
                    "(update_preview.sh --plist-force çalıştırın)")
        except Exception as e:  # bozuk plist / okunamadı → fail-closed
            problems.append("plist okunamadı: %s" % e)

    # 4) Yaş kıyası (WARN): mirror dosyası şablondan belirgin şekilde ESKİYSE
    #    bayat olabilir. Eşik 1 saat: --bootstrap sırası (sync → plist) gereği
    #    plist şablondan birkaç saniye SONRA yazılır; bu epsilon'u görmezden
    #    gelmek için yalnızca gerçek bayatlığı (saatlerce eski mirror) uyarır.
    if os.path.isfile(tmpl):
        tm_mtime = os.path.getmtime(tmpl)
        for name in ("preview_server.py", "preview.html"):
            p = os.path.join(preview_dir, name)
            if (os.path.isfile(p)
                    and tm_mtime - os.path.getmtime(p) > AGE_WARN_SECONDS):
                warnings.append(
                    "YAŞ: preview/%s şablondan ESKİ — mirror bayat olabilir "
                    "(fresh_clone_setup.sh çalıştırın)" % name)

    return problems, warnings


def _log(path, text):
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), text))
    except OSError:
        pass  # log yazılamazsa denetim yine de çalışsın


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview-dir", required=True)
    ap.add_argument("--verify-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--tmpl-dir", default=tmpl_dir_default())
    ap.add_argument("--log", default=None,
                    help="prestart log yolu (yoksa yalnızca stdout)")
    ap.add_argument("--check-only", action="store_true",
                    help="sunucuyu başlatma; yalnızca denetle (testler)")
    args, rest = ap.parse_known_args(argv)

    problems, warnings = probe(args.preview_dir, args.verify_dir,
                               args.label, args.tmpl_dir)

    for w in warnings:
        print("UYARI: %s" % w)
        _log(args.log, "UYARI: %s" % w)

    if problems:
        for p in problems:
            print("HATA: %s" % p, file=sys.stderr)
            _log(args.log, "HATA: %s" % p)
        print("PRESTART: BAYAT/EKSİK — sunucu başlatılmadı (exit %d)"
              % EXIT_STALE, file=sys.stderr)
        _log(args.log, "PRESTART: BAYAT/EKSİK — sunucu başlatılmadı")
        return EXIT_STALE

    if args.check_only:
        print("PRESTART: PASS — preview mirror hazır, sunucu başlatılabilir")
        return EXIT_READY

    # parse_known_args '--' ayracını da positional'lara koyar; ayracı at.
    if rest and rest[0] == "--":
        rest = rest[1:]

    if not rest:
        print("HATA: sunucu komutu yok ('--' sonrası)", file=sys.stderr)
        return EXIT_ERROR

    print("PRESTART: PASS — sunucu başlatılıyor: %s" % rest[0])
    _log(args.log, "PRESTART: PASS — sunucu başlatılıyor")
    os.execv(sys.executable, [sys.executable] + rest)
    return EXIT_ERROR  # execv dönerse (asla) hata


if __name__ == "__main__":
    sys.exit(main())
