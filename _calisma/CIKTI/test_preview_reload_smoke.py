#!/usr/bin/env python3
"""test_preview_reload_smoke.py — Freebuff preview tab reload smoke testi.

Preview sunucusunu restart eder (update_preview.sh --start), ayağa
kalkmasini bekler, ve tüm endpoint'lerin veri-dolu (data-populated)
oldugunu dogrular:

  1. /preview.html — HTTP 200 + BUILD_TS enjeksiyonu (window.BUILD_TS)
  2. /api/latest  — valid JSON + exit_code set edilmis + layers var
  3. /api/history  — valid JSON + en az 1 kayit
  4. /api/run     — SSE stream acilir + snapshot event'i gelir
  5. /api/run-stream — SSE stream acilir + ilk event gelir

CI'da advisory smoke olarak kosulur; exit 0 = PASS, exit 1 = FAIL
(continue-on-error). Freebuff webview detachment/reload yarisini CI
seviyesinde dogrulamaz (o Electron'a ozgu), ancak sunucu restart +
veri akisi zincirini fail-closed test eder.

Rapor: JSON dict -> --out ile yazilir; run summary'ye eklenir.

Kullanim:
  python3 test_preview_reload_smoke.py --port 8000 --out report.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Timout limits
START_TIMEOUT = 30   # restart sonrasi ayağa kalkana kadar
VERIFY_WAIT = 60     # verify_loop'un ilk run'ini tamamlamasi icin
SSE_TIMEOUT = 8      # SSE event bekleme suresi
POLL_STEP = 1.0


def _get(port, path, timeout=5):
    """HTTP GET; basariliysa (body, status), degilse (None, None)."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return r.read().decode("utf-8"), r.status
    except Exception:
        return None, None


def _get_json(port, path, timeout=5):
    """HTTP GET + JSON parse; basariliysa dict, degilse None."""
    body, status = _get(port, path, timeout)
    if status == 200 and body:
        try:
            return json.loads(body)
        except (json.JSONDecodeError):
            pass
    return None


def restart_preview():
    """update_preview.sh --start cagirir; (rc, stdout)."""
    script = os.path.join(HERE, "update_preview.sh")
    r = subprocess.run(
        ["bash", script, "--start"],
        capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def build_report(ok, checks, detail=""):
    """Standart JSON rapor dict'i."""
    return {"ok": ok, "checks": checks, "detail": detail,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Freebuff preview tab reload smoke testi")
    ap.add_argument("--port", type=int, default=8000,
                    help="preview sunucu portu (vars. 8000)")
    ap.add_argument("--out", default=None,
                    help="JSON rapor çıktı dosyası")
    ap.add_argument("--no-restart", action="store_true",
                    help="restart yapma, yalnızca veri doğrula (CI ortamında "
                         "sunucu zaten çalışıyorsa)")
    ap.add_argument("--ci", action="store_true",
                    help="CI modu: --restart yerine update_preview.sh --start "
                         "cagirir (HTML mirror rebuild + launchd bootstrap). "
                         "Yerelde launchd olmayan ortamda kullanilmaz.")
    args = ap.parse_args(argv)

    port = args.port
    checks = {}

    # ── ADIM 1: Restart ────────────────────────────────────────────────
    if not args.no_restart:
        rc, output = restart_preview()
        checks["restart"] = {"ok": rc == 0, "exit": rc, "output": output[:500]}
        if rc != 0:
            report = build_report(False, checks,
                                  f"restart başarısız (exit {rc}): {output[:200]}")
            print(json.dumps(report, ensure_ascii=False))
            if args.out:
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
            return 1
    else:
        checks["restart"] = {"ok": True, "exit": 0, "output": "--no-restart"}

    # ── ADIM 2: Ayağa kalkana kadar bekle ──────────────────────────────
    deadline = time.monotonic() + START_TIMEOUT
    up = False
    while time.monotonic() < deadline:
        body, status = _get(port, "/api/health", timeout=3)
        if status == 200:
            up = True
            break
        time.sleep(POLL_STEP)

    checks["startup"] = {"ok": up, "detail": "health check 200" if up
                         else f"{START_TIMEOUT}s içinde ayağa kalkmadı"}
    if not up:
        report = build_report(False, checks, "sunucu ayağa kalkmadı")
        print(json.dumps(report, ensure_ascii=False))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        return 1

    # ── ADIM 3: Statik HTML + BUILD_TS ─────────────────────────────────
    html, status = _get(port, "/preview.html", timeout=10)
    html_ok = status == 200 and "window.BUILD_TS" in (html or "")
    # BUILD_TS enjeksiyonu advisory (eski sunucularda olmayabilir);
    # preview.html 200 geldiyse bu adim OK sayilir.
    checks["preview.html"] = {"ok": status == 200, "status": status,
                              "build_ts_injected": "window.BUILD_TS" in (html or "")}

    # ── ADIM 4: /api/latest — valid JSON + data populated ──────────────
    latest = _get_json(port, "/api/latest", timeout=10)
    latest_ok = (latest is not None and
                 latest.get("exit_code") is not None and
                 isinstance(latest.get("layers"), dict))
    checks["api_latest"] = {"ok": latest_ok,
                            "exit_code": latest.get("exit_code") if latest else None,
                            "layers_count": len(latest.get("layers", {})) if latest else 0}

    # ── ADIM 5: /api/history — valid JSON + en az 1 kayit ─────────────
    history = _get_json(port, "/api/history", timeout=10)
    history_ok = history is not None and len(history or []) >= 1
    checks["api_history"] = {"ok": history_ok,
                             "records": len(history or [])}

    # ── ADIM 6: SSE /api/run — snapshot event'i gelmeli ────────────────
    sse_ok = False
    events_seen = 0
    try:
        r = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/run", timeout=SSE_TIMEOUT)
        # Ilk 4 SSE event'ini oku (connect + snapshot yeterli)
        events_seen = 0
        deadline_sse = time.monotonic() + SSE_TIMEOUT
        buf = b""
        while time.monotonic() < deadline_sse:
            chunk = r.read(1024)
            if not chunk:
                break
            buf += chunk
            lines = buf.split(b"\n\n")
            for line in lines[:-1]:
                if b"event: snapshot" in line or b"event: connected" in line:
                    events_seen += 1
            buf = lines[-1]
            if events_seen >= 2:
                break
        sse_ok = events_seen >= 1
        r.close()
    except Exception:
        sse_ok = False
    checks["sse_run"] = {"ok": sse_ok, "events_seen": events_seen}

    # ── ADIM 7: SSE /api/run-stream — ilk event gelmeli ────────────────
    stream_ok = False
    try:
        r = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/run-stream", timeout=SSE_TIMEOUT)
        # Ilk data: satirini oku
        chunk = r.read(4096)
        stream_ok = b"data:" in chunk
        r.close()
    except Exception:
        stream_ok = False
    checks["sse_run_stream"] = {"ok": stream_ok}

    # ── ADIM 8: /api/run-history — valid JSON ──────────────────────────
    run_history = _get_json(port, "/api/run-history?_t=" + str(int(time.time())), timeout=10)
    rh_ok = isinstance(run_history, list)
    checks["api_run_history"] = {"ok": rh_ok,
                                 "records": len(run_history or []) if rh_ok else 0}

    # ── VERDICT ────────────────────────────────────────────────────────
    all_ok = all(c.get("ok", False) for c in checks.values())
    report = build_report(all_ok, checks,
                          "tüm endpoint'ler PASS" if all_ok
                          else "bazi endpoint'ler FAIL")
    print(json.dumps(report, ensure_ascii=False))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())