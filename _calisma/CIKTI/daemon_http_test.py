#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daemon_http_test.py — preview_server.py DAEMON MODU end-to-end HTTP testi.

Nedir: preview_server.py'nin daemon dalını (PREVIEW_DAEMON=1 → setsid +
redirect_stdio_to_devnull, EBADF'sız stdio yönlendirmesi) GERÇEK süreçte
uçtan uca doğrular:

  1. Gerçek preview_server.py'yi daemon modda başlat (PREVIEW_DAEMON=1),
     geçici bir --dir (stub verify_delivery.py + minik paket) ve geçici bir
     --preview-dir (preview.html kopyası) ile.
  2. Sunucu ayağa kalkana dek /preview.html, /api/latest, /api/history'yi
     poll et; üçü de HTTP 200 dönmeli.
  3. Sunucuyu düzgünce kapat; raporu --out JSON'a yaz.

Sözleşme: exit 0 = üç endpoint de 200 (daemon modu sağlıklı); exit 1 =
zaman aşımı/yanıt yok/200 değil; exit 2 = kullanım hatası. Her adım
fail-closed'dur.

CI bağlamı: advisory job (continue-on-error) — build'i bloke etmez, rapor
artifact + run summary'de denetlenir. Kullanım:

  python3 daemon_http_test.py \
      --server _calisma/CIKTI/preview_server.py \
      --preview-src _calisma/CIKTI/preview.html \
      --out daemon_http_report.json \
      [--port 8799] [--interval 3600] [--dir <stub>]

Stub --dir yoksa script kendisi kurar: paket içeriği (verify_delivery.py,
verify_delivery.config.json, TESLIM zips…) CIKTI'dan kopyalanır, böylece
server'ın açılış kontrolleri (verify_delivery.py yoksa exit 2) geçer ve
verify_loop da gerçek verilerle çalışabilir.
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

ENDPOINTS = ("/preview.html", "/api/latest", "/api/history")
START_TIMEOUT = 60   # daemon ayağa kalkana kadar
POLL_STEP = 1.0
INITIAL_RUN_WAIT = 240  # verify_loop'un ilk (override'sız) run'ı bitene kadar
OVERRIDE_RUN_WAIT = 300  # override run'ının rapor üretmesi için bekleme


def _latest_json(port):
    """/api/latest özetini döndür; hatada None."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/latest", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def trigger_override_run(port, verify_dir,
                         wait_initial=INITIAL_RUN_WAIT,
                         wait_override=OVERRIDE_RUN_WAIT):
    """Budget override'lı bir run tetikleyip OVERRIDE_RAPORU.json üretimini bekle.

    run-now, verify_loop ile VERIFY_BUSY'yi paylaşır: loop'un ilk run'ı
    devam ederken tetiklenirse 409 döner. Bu yüzden önce /api/latest'te
    exit_code görünene dek beklenir (ilk run bitti), sonra
    /api/run-now?budget=1&budget_method=universal çağrılır ve LATEST ts
    değişene + yeni exit_code set edilene dek beklenir (override run bitti).
    Rapor, override run'unun _finalize_run'ı tarafından yazılır.

    Döndürür: (ok, detail). ok=False → advisory (artifact yok, CI adımı raporlar).
    """
    base = f"http://127.0.0.1:{port}"
    # 1) İlk run bitsin (BUSY çakışması / bayat ts karışıklığı olmasın).
    before = None
    deadline = time.monotonic() + wait_initial
    while time.monotonic() < deadline:
        before = _latest_json(port)
        if before and before.get("exit_code") is not None:
            break
        time.sleep(2)
    else:
        return False, "ilk run bitmedi (exit_code hiç görünmedi)"
    # 2) Override run'ı tetikle (--budget 1 + method universal).
    try:
        with urllib.request.urlopen(
                base + "/api/run-now?budget=1&budget_method=universal",
                timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, f"run-now tetiklenemedi: {e}"
    if body.get("status") != "started":
        return False, f"run-now beklenmedik yanıt: {body}"
    # 3) LATEST ts değişip yeni run bitene kadar bekle (exit_code set).
    ts0 = before.get("ts")
    done = False
    deadline = time.monotonic() + wait_override
    while time.monotonic() < deadline:
        cur = _latest_json(port)
        if cur and cur.get("ts") != ts0 and cur.get("exit_code") is not None:
            done = True
            break
        time.sleep(3)
    if not done:
        return False, "override run bitmedi (ts değişmedi / zaman aşımı)"
    # 4) Rapor dosyası: _finalize_run broadcast'ten ÖNCE yazar → hazır olmalı.
    path = os.path.join(verify_dir, "logs", "OVERRIDE_RAPORU.json")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    rpt = json.load(f)
            except (OSError, ValueError):
                time.sleep(0.5)
                continue
            n = rpt.get("override_count", 0)
            ok = n >= 1 or bool(rpt.get("lines"))
            return ok, (f"override_count={n}, lines={len(rpt.get('lines') or [])}, "
                        f"verdict={rpt.get('verdict')}")
        time.sleep(0.5)
    return False, "OVERRIDE_RAPORU.json üretilmedi"

# Daemon modda verify_loop'un gerçek --full koşusunu uzun tut (test boyunca
# tek tur yeter; interval saniye cinsinden).
DEFAULT_INTERVAL = 3600


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_status(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


def make_stub_dir(src_dir, dst_dir):
    """Server açılış kontrollerini geçirecek asgari paket dizinini kurar.

    verify_delivery.py + config + zip'leri CIKTI'dan kopyalar (fail-closed:
    kaynak yoksa hata). Böylece server hem --dir kontrollerini geçer hem de
    verify_loop gerçek paketle tek tur çalışabilir.
    """
    os.makedirs(dst_dir, exist_ok=True)
    needed = ("verify_delivery.py", "verify_delivery.config.json",
              "TESLIM_KLASOR_V5_2026-08-17.zip")
    for rel in needed:
        src = os.path.join(src_dir, rel)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"kaynak yok: {src}")
        shutil.copy2(src, os.path.join(dst_dir, rel))
    # config'in dosya yolları göreli olduğundan PDF/ref kontrolü stub'da
    # eksik olabilir; verify_loop bunu FAIL yapar ama HTTP testi yalnızca
    # 200 bekler — sorun değil (raporlama advisory).
    return dst_dir


def wait_for_server(port, timeout=START_TIMEOUT):
    base = f"http://127.0.0.1:{port}"
    statuses = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        all_ok = True
        for ep in ENDPOINTS:
            if ep not in statuses:
                st = http_status(base + ep)
                if st is not None:
                    statuses[ep] = st
                else:
                    all_ok = False
        if all_ok:
            return True, statuses
        time.sleep(POLL_STEP)
    return False, statuses


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--server", default=os.path.join(HERE, "preview_server.py"))
    ap.add_argument("--preview-src", default=os.path.join(HERE, "preview.html"))
    ap.add_argument("--dir", default=None, help="stub paket dizini (yoksa kurulur)")
    ap.add_argument("--port", type=int, default=0, help="0 = boş port seç")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    ap.add_argument("--start-timeout", type=float, default=START_TIMEOUT,
                    help="sunucu ayağa kalkana kadar beklenecek saniye")
    ap.add_argument("--out", default="daemon_http_report.json")
    ap.add_argument("--history-out", default=None,
                    help="history.jsonl + .sha256 sidecar'ı bu yola kopyala "
                         "(K15 sidecar doğrulaması için)")
    ap.add_argument("--override-out", default=None,
                    help="override run'ı tetikleyip logs/OVERRIDE_RAPORU.json'u "
                         "bu yola kopyala (PRECOMMIT_RAPORU deseni sidecar — "
                         "override-raporu artifact'ı; yoksa advisory not düşülür)")
    args = ap.parse_args()

    if not os.path.isfile(args.server):
        print(f"HATA: server yok: {args.server}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.preview_src):
        print(f"HATA: preview kaynağı yok: {args.preview_src}", file=sys.stderr)
        return 2

    report = {"server": args.server, "ok": False, "port": args.port,
              "endpoints": {}, "error": None, "history_out": args.history_out,
              "override_run": None}

    with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
        verify_dir = args.dir or os.path.join(tmp, "verify")
        preview_dir = os.path.join(tmp, "preview")
        os.makedirs(preview_dir, exist_ok=True)
        shutil.copy2(args.preview_src, os.path.join(preview_dir, "preview.html"))
        if not os.path.isfile(os.path.join(verify_dir, "verify_delivery.py")):
            verify_dir = make_stub_dir(HERE, verify_dir)

        port = args.port or free_port()
        report["port"] = port
        env = dict(os.environ)
        env["PREVIEW_DAEMON"] = "1"
        cmd = [sys.executable, args.server,
               "--dir", verify_dir,
               "--preview-dir", preview_dir,
               "--port", str(port),
               "--interval", str(args.interval)]
        try:
            proc = subprocess.Popen(cmd, env=env,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        except OSError as e:
            report["error"] = f"başlatılamadı: {e}"
            print(f"HATA: {report['error']}", file=sys.stderr)
            _write_report(args.out, report)
            return 1

        try:
            ok, statuses = wait_for_server(port, timeout=args.start_timeout)
            report["endpoints"] = statuses
            report["ok"] = ok and all(
                statuses.get(ep) == 200 for ep in ENDPOINTS)
            # Daemon süreci hâlâ ayakta mı? (setsid + stdio yönlendirmesi
            # sonrası canlı kalmalı — EBADF düzeltmesinin özü.)
            alive = proc.poll() is None
            report["daemon_alive"] = alive
            report["ok"] = report["ok"] and alive
            if not report["ok"]:
                report["error"] = (
                    f"endpoint'ler: {statuses} | daemon_alive={alive}")
                print(f"FAIL: {report['error']}", file=sys.stderr)
            # Override run: [CLI override] satırları ayrı rapora gider
            # (PRECOMMIT_RAPORU deseni). Yalnızca --override-out verilirse
            # tetiklenir (CI); HTTP smoke sonucunu DEĞİŞTİRMEZ (advisory).
            if args.override_out and alive:
                ov_ok, ov_detail = trigger_override_run(port, verify_dir)
                report["override_run"] = {
                    "ok": ov_ok, "detail": ov_detail,
                    "out": args.override_out}
                print(f"override run: {'OK' if ov_ok else 'FAIL'} — {ov_detail}")
                ov_src = os.path.join(verify_dir, "logs", "OVERRIDE_RAPORU.json")
                if os.path.isfile(ov_src):
                    odir = os.path.dirname(args.override_out)
                    if odir:
                        os.makedirs(odir, exist_ok=True)
                    shutil.copy2(ov_src, args.override_out)
        finally:
            # Düzgün kapat (daemon modda SIGTERM handler'ı vardır).
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            # K15: history.jsonl + sidecar'ı tempdir'den dışarı kopyala
            # (tempdir temizlenmeden ÖNCE).
            hist_src = os.path.join(preview_dir, "history.jsonl")
            hist_sha_src = hist_src + ".sha256"
            if args.history_out and os.path.isfile(hist_src):
                hdir = os.path.dirname(args.history_out)
                if hdir:
                    os.makedirs(hdir, exist_ok=True)
                shutil.copy2(hist_src, args.history_out)
                if os.path.isfile(hist_sha_src):
                    shutil.copy2(hist_sha_src, args.history_out + ".sha256")
                report["history_out"] = args.history_out

    _write_report(args.out, report)
    if report["ok"]:
        print("PASS: üç endpoint de HTTP 200, daemon canlı "
              f"(port {port}) — rapor: {args.out}")
        return 0
    return 1


def _write_report(path, report):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"UYARI: rapor yazılamadı {path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
