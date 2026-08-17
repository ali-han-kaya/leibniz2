#!/usr/bin/env python3
"""
preview_server.py — Stoic-Hume V5 preview dashboard.

Tek dosyalık Python HTTP sunucusu (stdlib-only):
  - /            ve /preview.html  → statik HTML
  - /api/run     → Server-Sent Events (SSE): verify_delivery.py --full çıktısını
                   her RUN_INTERVAL saniyede bir stream eder
  - /api/latest  → en son çalıştırmanın JSON özeti (P0/P1, SONUÇ, bütçe, vs.)

Çalıştırma:
  /usr/bin/python3 preview_server.py --dir /path/to/_calisma/CIKTI

Önceki http.server yerine geçer; TCC-safe bir dizinden (ör.
~/Library/Caches/com.freebuff/preview/) çalıştırılır.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PREVIEW_DIR = os.path.expanduser("~/Library/Caches/com.freebuff/preview")


def _find_python(verify_dir):
    """venv python tercih et; yoksa fall back to sys.executable.

    verify_delivery.py z3 import ediyor; z3 yalnızca venv'ta kurulu.

    Sıralama (öncelik sırasıyla):
      1. ~/Library/Caches/com.freebuff/venv_z3/bin/python3  (TCC-safe mirror)
      2. <verify_dir>/../.venv_z3/bin/python3              (proje venv'i)
      3. <verify_dir>/../.venv/bin/python3
      4. sys.executable                                     (system python)
    """
    # 1. TCC-safe mirror (launchd agent'tan okunabilir)
    mirror = os.path.expanduser(
        "~/Library/Caches/com.freebuff/venv_z3/bin/python3")
    if os.path.isfile(mirror) and os.access(mirror, os.X_OK):
        return mirror
    # 2-3. Proje venv'leri
    rel_candidates = [
        os.path.join(verify_dir, "..", ".venv_z3", "bin", "python3"),
        os.path.join(verify_dir, "..", ".venv", "bin", "python3"),
    ]
    for cand in rel_candidates:
        cand = os.path.abspath(cand)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return sys.executable

# Son çalıştırmanın sonucunu paylaşımlı bellekte tut (thread-safe).
LATEST = {
    "ts": None,            # ISO timestamp
    "verdict": "UNKNOWN",
    "stdout": "",
    "stderr": "",
    "exit_code": None,
    "duration_s": None,
    "p0": 0,
    "p1": 0,
    "budget_usd": None,
    "pdf_pages": None,
    "ref_count": None,
    "raw_sha256": None,
    "stripped_sha256": None,
}
LOCK = threading.Lock()
SSE_CLIENTS = []  # bağlı client listesi (broadcast için)


def run_verify(verify_dir):
    """verify_delivery.py --full komutunu çalıştır, sonucu LATEST'e yaz + broadcast.

    Bu server user shell context'te çalışıyor (bash -c exec argv ...); tüm
    proje dosyalarına tam erişim var. Venv python doğrudan çağrılır.

    venv python tercih et; yoksa system python fallback.
    """
    py = _find_python(verify_dir)
    inner = [py, os.path.join(verify_dir, "verify_delivery.py"),
             "--dir", verify_dir, "--full", "--json"]
    cmd = inner
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           cwd=verify_dir)
        stdout, stderr, rc = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        stdout = ""; stderr = "TIMEOUT (>300s)"; rc = 124
    duration = round(time.monotonic() - t0, 2)

    # Parse JSON for structured fields
    data = {}
    try:
        # --json prints a single JSON blob as the entire stdout.
        # Eğer stdout'un tamamı parse edilemezse, son { ... } bloğunu dene.
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            json_start = stdout.rfind("{")
            json_end = stdout.rfind("}")
            if json_start >= 0 and json_end > json_start:
                data = json.loads(stdout[json_start:json_end + 1])
    except (json.JSONDecodeError, ValueError):
        pass

    with LOCK:
        LATEST.update({
            "ts": datetime.now(timezone.utc).isoformat(),
            "verdict": data.get("verdict", "FAIL" if rc else "PASS"),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": rc,
            "duration_s": duration,
            "p0": data.get("counts", {}).get("P0", 0),
            "p1": data.get("counts", {}).get("P1", 0),
            "budget_usd": (data.get("budget") or {}).get("estimated_usd"),
            "pdf_pages": data.get("pdf_pages"),
            "ref_count": data.get("ref_count"),
            "raw_sha256": (data.get("pdf_hash") or {}).get("raw"),
            "stripped_sha256": (data.get("pdf_hash") or {}).get("stripped"),
        })
        # Extract pages + refs from stdout for richer dashboard
        for line in stdout.splitlines():
            if line.startswith("PDF:") and "sayfa" in line:
                # "PDF: 33 sayfa | References: 64"
                parts = line.split("|")
                if len(parts) >= 2 and "References:" in parts[1]:
                    try:
                        LATEST["pdf_pages"] = int(parts[0].split()[-2])
                        LATEST["ref_count"] = int(parts[1].split()[-1])
                    except (ValueError, IndexError):
                        pass

    # Broadcast to all SSE clients
    snapshot = json.dumps({k: LATEST[k] for k in
                          ("ts", "verdict", "p0", "p1", "duration_s",
                           "budget_usd", "pdf_pages", "ref_count",
                           "raw_sha256", "stripped_sha256", "exit_code")})
    with LOCK:
        for q in SSE_CLIENTS:
            try:
                q.put(snapshot)
            except Exception:
                pass


def verify_loop(verify_dir, interval):
    """Her interval saniyede bir run_verify çalıştırır (arka plan thread)."""
    import traceback
    sys.stderr.write("[verify_loop] started\n"); sys.stderr.flush()
    while True:
        try:
            sys.stderr.write(f"[verify_loop] running verify...\n"); sys.stderr.flush()
            run_verify(verify_dir)
            sys.stderr.write(f"[verify_loop] done, sleeping {interval}s\n"); sys.stderr.flush()
        except Exception as e:
            tb = traceback.format_exc()
            sys.stderr.write(f"[verify_loop] EXCEPTION: {e}\n{tb}\n"); sys.stderr.flush()
            with LOCK:
                LATEST.update({"ts": datetime.now(timezone.utc).isoformat(),
                               "verdict": "ERROR", "stderr": str(e),
                               "exit_code": 1})
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Sunucu loglarını kendi dosyamıza yönlendir (stderr'i kirletmesin).
        sys.stderr.write(f"[preview_server] {self.address_string()} {fmt % args}\n")

    def _send(self, status, body, content_type="text/plain; charset=utf-8",
              extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body.encode("utf-8")
                                                if isinstance(body, str) else body)))
        if extra_headers:
            for h, v in extra_headers.items():
                self.send_header(h, v)
        self.end_headers()
        out = body.encode("utf-8") if isinstance(body, str) else body
        self.wfile.write(out)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/preview.html"):
            self.serve_preview()
        elif self.path == "/api/latest":
            self.serve_latest()
        elif self.path == "/api/run":
            self.serve_sse()
        elif self.path == "/api/health":
            self._send(200, "ok")
        else:
            self._send(404, "404 not found")

    def serve_preview(self):
        with open(os.path.join(PREVIEW_DIR, "preview.html"), encoding="utf-8") as f:
            html = f.read()
        self._send(200, html, content_type="text/html; charset=utf-8")

    def serve_latest(self):
        with LOCK:
            snapshot = dict(LATEST)
        # stdout/stderr uzun olabilir; /api/latest için kırpılmış hali.
        snapshot["stdout_short"] = "\n".join(snapshot["stdout"].splitlines()[-50:])
        snapshot["stderr_short"] = "\n".join(snapshot["stderr"].splitlines()[-20:])
        snapshot.pop("stdout", None)
        snapshot.pop("stderr", None)
        self._send(200, json.dumps(snapshot, indent=2),
                   content_type="application/json; charset=utf-8")

    def serve_sse(self):
        """Server-Sent Events: her LATEST güncellemesini broadcast et."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # nginx proxy uyumluluğu
        self.end_headers()

        import queue
        q = queue.Queue(maxsize=64)
        with LOCK:
            SSE_CLIENTS.append(q)
            # Bağlantı anında mevcut snapshot'ı gönder
            snapshot = json.dumps({k: LATEST[k] for k in
                                  ("ts", "verdict", "p0", "p1", "duration_s",
                                   "budget_usd", "pdf_pages", "ref_count",
                                   "raw_sha256", "stripped_sha256", "exit_code")})
        try:
            self.wfile.write(f"event: snapshot\ndata: {snapshot}\n\n".encode())
            self.wfile.flush()
            # Periyodik yorum (SSE keepalive)
            last_keep = time.monotonic()
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"event: update\ndata: {msg}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # keepalive yorumu
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_keep = time.monotonic()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with LOCK:
                try:
                    SSE_CLIENTS.remove(q)
                except ValueError:
                    pass


def main():
    # Daemon modunda: yeni process group + session oluştur (tamamen detach).
    # Bu, parent shell exit ettiğinde SIGHUP/SIGTERM almamızı engeller.
    if os.environ.get("PREVIEW_DAEMON") == "1":
        try:
            os.setsid()
        except OSError:
            pass
        # std fds'yi kapat
        try:
            os.close(0)
        except OSError:
            pass
        try:
            os.close(1)
        except OSError:
            pass
        try:
            os.close(2)
        except OSError:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=ROOT,
                    help="verify_delivery.py'nin bulunduğu dizin")
    ap.add_argument("--preview-dir", default=DEFAULT_PREVIEW_DIR,
                    help="preview.html'ın bulunduğu dizin (TCC-safe olmalı)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--interval", type=int, default=60,
                    help="verify_delivery.py --full kaç saniyede bir koşsun")
    args = ap.parse_args()

    global PREVIEW_DIR
    PREVIEW_DIR = args.preview_dir

    if not os.path.isfile(os.path.join(PREVIEW_DIR, "preview.html")):
        print(f"UYARI: {PREVIEW_DIR}/preview.html bulunamadı; "
              f"sunucu yine de başlatılıyor ama /preview.html 404 döner",
              file=sys.stderr)

    if not os.path.isfile(os.path.join(args.dir, "verify_delivery.py")):
        print(f"HATA: {args.dir}/verify_delivery.py yok", file=sys.stderr)
        sys.exit(2)

    # Sinyal yakalama — neden öldüğümüzü görelim
    import signal
    def _sig(term_frame, signum):
        sys.stderr.write(f"\n[main] SIGTERM/SIGINT received ({signum}), exiting\n")
        sys.stderr.flush()
        sys.exit(143)
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    # Arka plan thread: periyodik verify çalıştırma
    t = threading.Thread(target=verify_loop, args=(args.dir, args.interval),
                         daemon=True, name="verify-loop")
    t.start()

    srv = ThreadingHTTPServer((args.bind, args.port), Handler)
    sys.stderr.write(f"[main] preview_server: serving {PREVIEW_DIR} on http://{args.bind}:{args.port}\n")
    sys.stderr.write(f"[main] preview_server: verify loop interval={args.interval}s, dir={args.dir}\n")
    sys.stderr.write(f"[main] PID={os.getpid()} PGID={os.getpgrp()}\n")
    sys.stderr.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()