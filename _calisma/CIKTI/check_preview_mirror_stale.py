#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_preview_mirror_stale.py — preview mirror BAYATLIK kapısının negatif kontrolü.

NEDEN (ölçülen boşluk, 2026-11-05): `mirror-check` CI job'ı mirror'ı repo'dan
`--force` ile kurup hemen `--check` koşuyor. Bu sırada `--check` yalnızca
"az önce kopyalanan dosyalar yerinde mi" sorusunu yanıtlar — BAYAT bir
mirror'ı hiç görmez. Kapı fail-open'a düşse (her durumda exit 0) koşum yeşil
kalır ve launchd/TCC rotası bayat `preview.js`/`sw.js` servis etmeye devam
eder (QA F2/F3 olayı: eski JS + 404 sw.js → gömülü webview güncelleme
çekemiyor, dashboard asılı kalıyor).

Bu kapı mirror'ı İZOLE bir temp kökte kendisi kurar ve dört adımı ölçer:

  1. TEMİZ   — `--force` sync + `--check` = 0
  2. BAYAT   — probe dosyasına bir bayt eklenir (repo ilerlemiş gibi) →
               `--check` = 1 ve çıktı `BAYAT/EKSİK: preview/<dosya>`
  3. ZİNCİR  — `verify_delivery.py --check-mirror` = 1 + `[P1] K17` +
               sidecar'da `stale_files` (bayatlık job'ı GERÇEKTEN düşürür)
  4. GERİ    — sync → `--check` = 0 (kapı kendini toparlar)

Gerçek mirror'a (PREVIEW_MIRROR / MIRROR_DIR / LEAN_MIRROR_DIR) ASLA
dokunmaz: adımların ortamı temp köke yönlendirilir ve temp her durumda
silinir. Bu yüzden Linux CI'da da koşar (macOS TCC gerekmez) ve geliştirici
makinesindeki canlı mirror'ı bayatlatmaz.

Exit: 0 = kapı fail-closed (dört adım da tuttu), 1 = sözleşme ihlali
(bayatlık yakalanmadı / K17 zinciri düşmedi / geri dönüş olmadı), 2 = ölçüm
imkânsız (script yok, sync kurulamadı, zaman aşımı).

Kullanım:
  python3 _calisma/CIKTI/check_preview_mirror_stale.py
  python3 _calisma/CIKTI/check_preview_mirror_stale.py --json
  python3 _calisma/CIKTI/check_preview_mirror_stale.py \
      --json-out mirror_stale_probe.json

`--json` stdout'a TEK JSON belgesi basar; `--json-out` yalnızca sidecar
yazar (stdout insan-okunur kalır) — CI raporu ikisini birlikte kullanır.

stdlib only — OFFLINE.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SYNC = os.path.join(HERE, "sync_verify_mirror.sh")
DEFAULT_VERIFY = os.path.join(HERE, "verify_delivery.py")
PROBE_FILE = "preview.js"

# Mirror'ın repo'dan geri kaldığı durumu simüle eden tek fark. İçerik
# deterministiktir (zaman damgası yok) — iki koşum farklı çıktı üretmez.
STALE_MARK = b"\n// stale-probe (check_preview_mirror_stale)\n"

MIRROR_ENV = (("PREVIEW_MIRROR", "preview"),
              ("MIRROR_DIR", "verify"),
              ("LEAN_MIRROR_DIR", "lean"))

SYNC_TIMEOUT = 300
CHECK_TIMEOUT = 180
VERIFY_TIMEOUT = 180


def _run(cmd, env):
    """Komutu koş; (rc, stdout+stderr) döndür. OSError/zaman aşımı → None."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=SYNC_TIMEOUT, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _check(sync_script, env):
    """`sync_verify_mirror.sh --check`: 0=GÜNCEL, 1=BAYAT, 2=hata."""
    try:
        r = subprocess.run(["bash", sync_script, "--check"],
                           capture_output=True, text=True,
                           timeout=CHECK_TIMEOUT, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _emit(report, args, code):
    """İnsan çıktısı + (istenirse) tek-JSON stdout + sidecar. code'u döndürür."""
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            print("[TEMİZ]  --check exit=%s" % report["clean_exit"])
            print("[BAYAT]  --check exit=%s · %s" %
                  (report["stale_exit"],
                   "BAYAT/EKSİK: preview/%s" % report["file"]
                   if report["stale_named"] else "raporlanmadı"))
            print("[K17]    --check-mirror exit=%s · stale_files=%s" %
                  (report["k17_exit"], report["k17_stale_files"]))
            print("[GERİ]   --check exit=%s" % report["restored_exit"])
        if code == 0:
            print("SONUÇ: preview mirror bayatlık kapısı FAIL-CLOSED "
                  "(temiz=0, bayat=1, K17=1, geri=0)")
        else:
            print("SONUÇ: FAIL — %s" % report["reason"])
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print("HATA: sidecar yazılamadı: %s (%s)" % (args.json_out, e),
                  file=sys.stderr)
            # Ölçüm kanıtı yazılamıyorsa PASS iddia edilemez (fail-closed).
            if code == 0:
                code = 2
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sync-script", default=DEFAULT_SYNC,
                    help="sync_verify_mirror.sh yolu (varsayılan: bu dosyanın yanı)")
    ap.add_argument("--verify-delivery", default=DEFAULT_VERIFY,
                    help="verify_delivery.py yolu (varsayılan: bu dosyanın yanı)")
    ap.add_argument("--probe-file", default=PROBE_FILE,
                    help="preview mirror'da bayatlatılacak dosya (varsayılan: preview.js)")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a tek JSON belgesi bas")
    ap.add_argument("--json-out", default=None,
                    help="sidecar JSON yolu (stdout insan-okunur kalır)")
    ap.add_argument("--quiet", action="store_true",
                    help="adım satırlarını basma (SONUÇ kalır)")
    args = ap.parse_args(argv)

    report = {
        "tool": "check_preview_mirror_stale.py",
        "ok": False,
        "file": args.probe_file,
        "clean_exit": None,
        "stale_exit": None,
        "stale_named": False,
        "k17_exit": None,
        "k17_stale_files": [],
        "restored_exit": None,
        "reason": "",
    }

    def finish(code, reason):
        report["ok"] = code == 0
        report["reason"] = reason
        return _emit(report, args, code)

    for path, label in ((args.sync_script, "sync_verify_mirror.sh"),
                        (args.verify_delivery, "verify_delivery.py")):
        if not os.path.isfile(path):
            return finish(2, "%s yok: %s" % (label, path))

    tmp = tempfile.mkdtemp(prefix="preview-mirror-stale-")
    try:
        env = dict(os.environ)
        for key, sub in MIRROR_ENV:
            env[key] = os.path.join(tmp, sub)

        # ── 1) TEMİZ: mirror repo'dan kurulur ve GÜNCEL olmalı ─────────────
        r = _run(["bash", args.sync_script, "--force"], env)
        if r is None:
            return finish(2, "sync --force çalıştırılamadı (OSError/zaman aşımı)")
        if r[0] != 0:
            return finish(2, "sync --force başarısız (exit %s)" % r[0])
        rc, out = _check(args.sync_script, env)
        report["clean_exit"] = rc
        if rc is None:
            return finish(2, "--check çalıştırılamadı (OSError/zaman aşımı)")
        if rc != 0:
            return finish(2 if rc == 2 else 1,
                          "temiz mirror'da --check exit %r — 0 beklenirdi" % (rc,))

        target = os.path.join(env["PREVIEW_MIRROR"], args.probe_file)
        if not os.path.isfile(target):
            return finish(2, "preview mirror'da %s yok — sync listesi eksik"
                          % args.probe_file)

        # ── 2) BAYAT: repo ilerlemiş gibi mirror'ı boz; kapı GÖRMELİ ───────
        with open(target, "ab") as f:
            f.write(STALE_MARK)
        rc, out = _check(args.sync_script, env)
        report["stale_exit"] = rc
        report["stale_named"] = ("BAYAT/EKSİK: preview/%s" % args.probe_file) in out
        if rc is None:
            return finish(2, "bayat mirror'da --check çalıştırılamadı")
        if rc != 1:
            return finish(1, "bayat mirror'da --check exit %r — 1 beklenirdi "
                             "(kapı fail-open?)" % (rc,))
        if not report["stale_named"]:
            return finish(1, "bayat mirror raporlanmadı: "
                             "'BAYAT/EKSİK: preview/%s' çıktıda yok"
                          % args.probe_file)

        # ── 3) ZİNCİR: K17 bayatlığı P1'e ve job'a taşımalı ────────────────
        sidecar = os.path.join(tmp, "mirror_report.json")
        try:
            v = subprocess.run(
                [sys.executable, args.verify_delivery, "--check-mirror",
                 "--mirror-out", sidecar],
                capture_output=True, text=True, timeout=VERIFY_TIMEOUT, env=env)
        except (OSError, subprocess.TimeoutExpired):
            return finish(2, "verify_delivery.py --check-mirror çalıştırılamadı")
        report["k17_exit"] = v.returncode
        vout = (v.stdout or "") + (v.stderr or "")
        if v.returncode != 1:
            return finish(1, "bayat mirror'da K17 exit %r — 1 beklenirdi "
                             "(zincir düşmüyor)" % (v.returncode,))
        if "[P1] K17" not in vout:
            return finish(1, "K17 P1 bulgusu üretmedi — BAYAT job'ı düşürmez")
        try:
            with open(sidecar, encoding="utf-8") as f:
                stale = json.load(f).get("stale_files") or []
        except (OSError, ValueError):
            return finish(2, "K17 sidecar'ı okunamadı: %s" % sidecar)
        report["k17_stale_files"] = stale
        if "preview/%s" % args.probe_file not in stale:
            return finish(1, "K17 stale_files'ta preview/%s yok: %s"
                          % (args.probe_file, stale))

        # ── 4) GERİ: sync bayatlığı gidermeli, kapı yine 0 demeli ──────────
        r = _run(["bash", args.sync_script], env)
        if r is None:
            return finish(2, "geri-sync çalıştırılamadı (OSError/zaman aşımı)")
        if r[0] != 0:
            return finish(1, "geri-sync başarısız (exit %s)" % r[0])
        rc, out = _check(args.sync_script, env)
        report["restored_exit"] = rc
        if rc != 0:
            return finish(1, "--check sync sonrası hâlâ %r — kapı toparlanmıyor"
                          % (rc,))
        return finish(0, "temiz=0, bayat=1, K17=1, geri=0")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
