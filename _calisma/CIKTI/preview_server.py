#!/usr/bin/env python3
"""
preview_server.py — Stoic-Hume V5 preview dashboard.

Tek dosyalık Python HTTP sunucusu (stdlib-only):
  - /            ve /preview.html  → statik HTML
  - /api/run     → Server-Sent Events (SSE): verify_delivery.py --full çıktısını
                   her RUN_INTERVAL saniyede bir stream eder (snapshot event'leri)
  - /api/run-stream → canlı satır akışı: verify subprocess'inin stdout/stderr
                   satırları koşarken anında yayınlanır (K8 Z3 ilerlemesi dahil);
                   run bitince `end` event'i + son snapshot gelir. Bağlantı
                   anında son tamamlanmış run'un satırları geriye dönük akıtılır
                   (replay-start/end arasında) — sayfa açılınca kutu boş kalmaz
  - /api/run-now → manuel tetikleme (GET/POST): interval beklemeden hemen
                   verify_delivery.py --full koşar; sonuç SSE ile anında broadcast
  - /api/latest  → en son çalıştırmanın JSON özeti (P0/P1, SONUÇ, bütçe, vs.)
                   + tam references_online raporu (verified/total, by_source)

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
    "budget": None,           # tam bütçe raporu (comparison.ratios + by_type)
    "pdf_pages": None,
    "ref_count": None,
    "raw_sha256": None,
    "stripped_sha256": None,
    "refs_online": None,        # tam references_online raporu (/api/latest için)
    "refs_verified": None,      # özet alanlar (SSE snapshot + history trend için)
    "refs_total": None,
    "refs_mismatch": None,
    "refs_by_source": None,
    "config_diff": None,        # son run'un raw↔effective config diff özeti (dashboard)
    "hook_env": None,           # hook env sürümleri (zaman serisi; python/z3/lean/…)
}
LOCK = threading.Lock()
SSE_CLIENTS = []      # bağlı /api/run client listesi (snapshot broadcast)
STREAM_CLIENTS = []   # bağlı /api/run-stream client listesi (satır akışı)
VERIFY_BUSY = threading.Lock()  # aynı anda yalnızca bir verify koşsun (loop + run-now)
VERIFY_DIR = None               # main()'de set edilir; /api/run-now handler'ı kullanır
HISTORY_PATH = None             # main()'de set edilir; JSONL trend dosyası
HISTORY_MAX = 100               # disk'te tutulacak en son run sayısı

HISTORY_KEYS = ("ts", "verdict", "p0", "p1", "duration_s", "budget_usd",
                "pdf_pages", "ref_count", "raw_sha256", "stripped_sha256",
                "exit_code", "refs_verified", "refs_total", "refs_mismatch",
                "refs_by_source", "hook_env")


def snapshot_dict():
    """LATEST'ten SSE/broadcast/history için ortak snapshot alanlarını al."""
    with LOCK:
        return {k: LATEST[k] for k in HISTORY_KEYS}


def persist_history(rec):
    """Bir run kaydını JSONL dosyasına append et; HISTORY_MAX ile sınırla.

    Her satır tek bir run'ın snapshot'ıdır (JSON). En eski satırlar atılır,
    böylece dosya disk'te sonsuz büyümez. Thread-safe: LOCK altında çağrılır
    ve rec zaten LOCK altında alınmış olarak gelir (kilit tekrar alınmaz).
    """
    if not HISTORY_PATH:
        return
    if not rec.get("ts"):
        return
    try:
        lines = []
        if os.path.isfile(HISTORY_PATH):
            with open(HISTORY_PATH, encoding="utf-8") as f:
                lines = [ln for ln in (l.strip() for l in f) if ln]
        lines.append(json.dumps(rec, ensure_ascii=False))
        # En yeni HISTORY_MAX satırı tut (en eskiyi at)
        if len(lines) > HISTORY_MAX:
            lines = lines[-HISTORY_MAX:]
        tmp = HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, HISTORY_PATH)  # atomik: yarı yazılmış dosya asla okunmaz
    except OSError as e:
        sys.stderr.write(f"[history] yazılamadı: {e}\n")
        sys.stderr.flush()


def load_history():
    """Disk'teki JSONL'ı oku, en son HISTORY_MAX kaydı döndür (en yeni önce)."""
    if not HISTORY_PATH or not os.path.isfile(HISTORY_PATH):
        return []
    out = []
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue  # bozuk satırı atla, dosyayı silme
    except OSError as e:
        sys.stderr.write(f"[history] okunamadı: {e}\n")
        sys.stderr.flush()
        return []
    return out[-HISTORY_MAX:]


def run_verify(verify_dir):
    """verify_delivery.py --full koş; zaten koşuyorsa atla.

    Busy-guard: verify_loop ve /api/run-now aynı anda iki verify
    çalıştırmasın (LATEST üzerine yazışma / çift maliyet).
    """
    if not VERIFY_BUSY.acquire(blocking=False):
        sys.stderr.write("[verify] zaten koşuyor — atlandı\n")
        sys.stderr.flush()
        return False
    try:
        return _run_verify_locked(verify_dir)
    finally:
        VERIFY_BUSY.release()


def _broadcast_stream(tag, line):
    """Bir satırı /api/run-stream client'larına gönder (blocking değil).

    tag: "stdout" | "stderr". Kuyruk doluysa en yeni satırlar önemli
    olduğundan eski satırlar düşer (put_nowait).
    """
    msg = json.dumps({"stream": tag, "line": line}, ensure_ascii=False)
    with LOCK:
        clients = list(STREAM_CLIENTS)
    for q in clients:
        try:
            q.put_nowait(msg)
        except Exception:
            pass


def _broadcast_run_end(rec):
    """Run bitti sinyali: /api/run-stream client'larına son snapshot'ı gönder."""
    msg = json.dumps({"stream": "end", "snapshot": rec}, ensure_ascii=False)
    with LOCK:
        clients = list(STREAM_CLIENTS)
    for q in clients:
        try:
            q.put_nowait(msg)
        except Exception:
            pass


def build_replay_events(ts, verdict, stdout, stderr):
    """Son tamamlanmış run'un satırlarını SSE event listesi olarak üret.

    Dönüş: [(event_adı, data_json), ...] — replay-start, ardından stderr
    satırları, ardından stdout satırları (her biri `replay: true` işaretli),
    en sonda replay-end. ts yoksa boş liste döner (henüz hiç run yok).

    Sıra, canlı akıştaki zamansal sırayı yansıtır: verify --full --json
    koşusunda insan-okur ilerleme satırları (K8 Z3 dahil) stderr'e akar,
    makine-okur JSON ise en sonda stdout'a yazılır.
    """
    if not ts:
        return []
    events = [("replay-start", json.dumps(
        {"stream": "replay-start", "ts": ts, "verdict": verdict},
        ensure_ascii=False))]
    for tag, text in (("stderr", stderr), ("stdout", stdout)):
        if not text:
            continue
        for line in text.splitlines():
            events.append((tag, json.dumps(
                {"stream": tag, "line": line, "replay": True},
                ensure_ascii=False)))
    events.append(("replay-end", json.dumps(
        {"stream": "replay-end", "ts": ts}, ensure_ascii=False)))
    return events


def _run_verify_locked(verify_dir):
    """verify_delivery.py --full komutunu çalıştır, sonucu LATEST'e yaz + broadcast.

    Bu server user shell context'te çalışıyor (bash -c exec argv ...); tüm
    proje dosyalarına tam erişim var. Venv python doğrudan çağrılır.

    Subprocess Popen ile satır satır okunur: her satır /api/run-stream
    client'larına canlı broadcast edilir (K8 Z3 ilerlemesi dahil —
    verify_delivery.py K8 Z3 stdout'unu kendi stderr'ine relay eder).

    venv python tercih et; yoksa system python fallback.
    """
    py = _find_python(verify_dir)
    inner = [py, os.path.join(verify_dir, "verify_delivery.py"),
             "--dir", verify_dir, "--full", "--json"]
    cmd = inner
    t0 = time.monotonic()
    timed_out = False
    try:
        # PYTHONUNBUFFERED=1: verify_delivery.py'nin print'leri flush=True
        # içermese bile satır satır pipe'a aksın (canlı run-stream için).
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, bufsize=1, cwd=verify_dir, env=env)
    except OSError as e:
        stdout, stderr, rc = "", f"başlatılamadı: {e}", 127
        duration = round(time.monotonic() - t0, 2)
        data = {}
        _finalize_run(stdout, stderr, rc, duration, data, verify_dir)
        return True

    out_chunks, err_chunks = [], []

    def _drain(pipe, sink, tag):
        try:
            for line in iter(pipe.readline, ""):
                sink.append(line)
                _broadcast_stream(tag, line.rstrip("\n"))
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_drain, args=(p.stdout, out_chunks, "stdout"))
    t_err = threading.Thread(target=_drain, args=(p.stderr, err_chunks, "stderr"))
    t_out.start(); t_err.start()
    try:
        rc = p.wait(timeout=300)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            p.kill()
            p.wait()
        except Exception:
            pass
    t_out.join(); t_err.join()
    stdout = "".join(out_chunks)
    stderr = "".join(err_chunks)
    if timed_out:
        stderr = (stderr + "\nTIMEOUT (>300s)").strip()
        rc = 124
    duration = round(time.monotonic() - t0, 2)
    _finalize_run(stdout, stderr, rc, duration, None, verify_dir)
    return True


# ---- config diff (raw vs effective) — diff_config_artifacts.py ile birebir ----
# preview_server.py bu mantığı SATIR İÇİ taşır: launchd route'unda verify
# mirror'da diff_config_artifacts.py bulunmayabilir (import edilmez).
# test_preview_server.py iki uygulamanın aynı sonucu ürettiğini denetler (drift
# guard) — buradaki sabitler/sınıflandırma diff_config_artifacts.py ile aynı.
_COMPARE_KEYS = ("budget_usd", "budget_method", "budget_ratios",
                 "expected_pages", "expected_refs", "expected_manifest")
_OVERRIDE_KEY = {"budget_usd": "budget", "budget_method": "budget_method"}


def _config_diff_classify(field, raw_val, eff_val, effective):
    effective = effective if isinstance(effective, dict) else {}
    ov_key = _OVERRIDE_KEY.get(field)
    ov = (effective.get("cli_overrides") or {}).get(ov_key) if ov_key else None
    if ov and ov.get("override"):
        return "cli_override"
    if raw_val is None:
        return "default"
    return "drift"


def _config_diff(raw_cfg, eff_cfg):
    """raw vs effective config farkları — diff_config_artifacts.compute_differences
    ile birebir aynı çıktı: [{field, raw, effective, reason}] döndürür."""
    raw_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
    eff_cfg = eff_cfg if isinstance(eff_cfg, dict) else {}
    differences = []
    for field in _COMPARE_KEYS:
        raw_val = raw_cfg.get(field)
        eff_val = eff_cfg.get(field)
        if raw_val == eff_val:
            continue
        differences.append({
            "field": field,
            "raw": raw_val,
            "effective": eff_val,
            "reason": _config_diff_classify(field, raw_val, eff_val, eff_cfg),
        })
    return differences


def _finalize_run(stdout, stderr, rc, duration, data, verify_dir=None):
    """Run sonucunu LATEST'e yaz, SSE_CLIENTS'a broadcast et, history'ye ekle.

    verify_dir verilirse raw config (verify_delivery.config.json) okunup
    effective config (data['config']) ile karşılaştırılır; sonuç
    LATEST['config_diff'] alanına yazılır (dashboard config-diff bölümü).
    """

    # Parse JSON for structured fields (sadece stdout; stderr insan-okur çıktı)
    if data is None:
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

    # config diff: raw (verify_delivery.config.json) vs effective (data['config'])
    raw_cfg = {}
    if verify_dir:
        cfg_path = os.path.join(verify_dir, "verify_delivery.config.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    raw_cfg = json.load(f)
            except (OSError, ValueError):
                raw_cfg = {}
    diff_rows = _config_diff(raw_cfg, data.get("config") or {})

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
            # Tam bütçe raporu: comparison.ratios (budget_ratios) + by_type
            # (type_bytes) kırılımı — dashboard kartı için.
            "budget": data.get("budget"),
            "pdf_pages": data.get("pdf_pages"),
            "ref_count": data.get("ref_count"),
            "raw_sha256": (data.get("pdf_hash") or {}).get("raw"),
            "stripped_sha256": (data.get("pdf_hash") or {}).get("stripped"),
            # Çevrimiçi referans denetimi (K6): tam rapor /api/latest'e,
            # özet alanlar SSE snapshot + history'ye gider.
            "refs_online": data.get("references_online"),
            "refs_verified": (data.get("references_online") or {}).get("verified"),
            "refs_total": (data.get("references_online") or {}).get("total_online"),
            "refs_mismatch": (data.get("references_online") or {}).get("mismatch"),
            "refs_by_source": (data.get("references_online") or {}).get("by_source"),
            # raw↔effective config diff özeti (dashboard config-diff bölümü)
            "config_diff": {"changed": bool(diff_rows),
                            "differences": diff_rows},
            # hook env sürümleri (python/z3/lean/…; zaman serisi paneli)
            "hook_env": data.get("hook_env"),
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

    # Broadcast to all SSE clients + disk'e yaz (trend) + run-stream sonu
    with LOCK:
        rec = {k: LATEST[k] for k in HISTORY_KEYS}
        snapshot = json.dumps(rec)
        for q in SSE_CLIENTS:
            try:
                q.put(snapshot)
            except Exception:
                pass
        persist_history(rec)
    _broadcast_run_end(rec)


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
        # EBADF'e dayanıklı: daemon modu fds'yi /dev/null'a yönlendirse bile,
        # log kaybı asla bir HTTP isteğini öldürmesin.
        try:
            sys.stderr.write(
                f"[preview_server] {self.address_string()} {fmt % args}\n")
            sys.stderr.flush()
        except Exception:
            pass

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
        elif self.path == "/api/run-now":
            self.trigger_run_now()
        elif self.path == "/api/run-stream":
            self.serve_run_stream()
        elif self.path == "/api/history":
            self.serve_history()
        elif self.path == "/api/health":
            self._send(200, "ok")
        else:
            self._send(404, "404 not found")

    def do_POST(self):
        if self.path == "/api/run-now":
            self.trigger_run_now()
        else:
            self._send(404, "404 not found")

    def _replay_last_run(self, ts, verdict, stdout, stderr):
        """Son tamamlanmış run'un satırlarını canlı akıştan ÖNCE gönder.

        replay-start/end event'leri sınırı işaretler; her satır `replay: true`
        taşır, böylece client geçmiş satırları canlı satırlardan ayırt eder.
        """
        events = build_replay_events(ts, verdict, stdout, stderr)
        if not events:
            return
        buf = "".join(f"event: {ev}\ndata: {data}\n\n" for ev, data in events)
        self.wfile.write(buf.encode())
        self.wfile.flush()

    def serve_run_stream(self):
        """Server-Sent Events: verify subprocess'inin satırlarını canlı akıt.

        Her satır bir `line` event'idir (data: {"stream": "stdout"|"stderr",
        "line": ...}); run bittiğinde `run-end` event'i (son snapshot) gelir.
        Bağlantı anında bekleyen bir verify yoksa keepalive ile bekler.

        Bağlantı anında SON TAMAMLANMIŞ run'un satırları geriye dönük akıtılır
        (replay-start/end arasında), böylece sayfa açıldığında kutu boş kalmaz:
        önce son run'un satırları, sonra canlı satırlar gelir.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        import queue
        q = queue.Queue(maxsize=512)
        with LOCK:
            STREAM_CLIENTS.append(q)
            # Bağlantı anında mevcut durumu bildir + son run'u replay için
            # snapshot'la (canlı satırlar queue'da birikir, önce replay gider).
            info = json.dumps({"stream": "info",
                               "ts": LATEST["ts"],
                               "verdict": LATEST["verdict"]},
                              ensure_ascii=False)
            replay_ts = LATEST["ts"]
            replay_verdict = LATEST["verdict"]
            replay_stdout = LATEST["stdout"]
            replay_stderr = LATEST["stderr"]
        try:
            self.wfile.write(f"event: info\ndata: {info}\n\n".encode())
            self.wfile.flush()
            self._replay_last_run(replay_ts, replay_verdict,
                                  replay_stdout, replay_stderr)
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"event: {json.loads(msg)['stream']}\ndata: {msg}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with LOCK:
                try:
                    STREAM_CLIENTS.remove(q)
                except ValueError:
                    pass

    def serve_history(self):
        """JSONL'daki son run'ları JSON array olarak döndür (trend grafiği için)."""
        data = load_history()
        self._send(200, json.dumps(data, ensure_ascii=False, indent=2),
                   content_type="application/json; charset=utf-8")

    def trigger_run_now(self):
        """Manuel tetikleme: interval beklemeden hemen verify koşar.

        Arka plan thread'inde çalışır, istek anında döner; sonuç hazır
        olunca run_verify içindeki broadcast ile SSE client'larına düşer.
        Zaten bir verify koşuyorsa 409 döner (çakışma yok).
        """
        ts = datetime.now(timezone.utc).isoformat()
        if not VERIFY_BUSY.acquire(blocking=False):
            self._send(409,
                       json.dumps({"status": "already_running", "ts": ts,
                                   "note": "bir verify zaten koşuyor"}),
                       content_type="application/json; charset=utf-8")
            return
        VERIFY_BUSY.release()  # thread acquire etsin; kilit tutma
        t = threading.Thread(target=run_verify, args=(VERIFY_DIR,),
                             daemon=True, name="run-now")
        t.start()
        self._send(200,
                   json.dumps({"status": "started", "ts": ts,
                               "note": "verify başladı; sonuç /api/run (SSE) ile anında yayınlanacak"}),
                   content_type="application/json; charset=utf-8")

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
            # (snapshot_dict() çağrılmaz: LOCK zaten tutuluyor, reentrant değil)
            snapshot = json.dumps({k: LATEST[k] for k in HISTORY_KEYS})
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


def redirect_stdio_to_devnull():
    """fd 0/1/2'yi /dev/null'a YÖNLENDİR (KAPATMAZ — EBADF üretmez).

    Daemon modunda std fds'yi kapatmak, sonraki sys.stderr.write çağrılarını
    (log_message her HTTP isteğinde çalışır) EBADF ile patlatıp isteği
    öldürüyordu. Standart daemon kalıbı kapatmak değil dup2 ile /dev/null'a
    bağlamaktır: fds açık kalır (write güvenli), terminal tutulmaz.
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in (0, 1, 2):
            try:
                os.dup2(devnull, fd)
            except OSError:
                pass
    finally:
        if devnull > 2:
            os.close(devnull)


def main():
    # Daemon modunda: yeni process group + session oluştur (tamamen detach).
    # Bu, parent shell exit ettiğinde SIGHUP/SIGTERM almamızı engeller.
    if os.environ.get("PREVIEW_DAEMON") == "1":
        try:
            os.setsid()
        except OSError:
            pass
        # std fds'yi KAPATMA (EBADF üretir); /dev/null'a YÖNLENDİR.
        redirect_stdio_to_devnull()

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

    global PREVIEW_DIR, VERIFY_DIR, HISTORY_PATH
    PREVIEW_DIR = args.preview_dir
    VERIFY_DIR = args.dir
    HISTORY_PATH = os.path.join(args.preview_dir, "history.jsonl")

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