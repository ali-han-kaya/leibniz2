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
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
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
    "cli_overrides": None,       # son run'un config.cli_overrides'ı (override=true → 'Budget override' rozeti)
    "cli_override_count": 0,     # skaler: override=true anahtar sayısı (trend'e temiz; tam dict sadece SSE'de)
    "hook_env": None,           # hook env sürümleri (zaman serisi; python/z3/lean/…)
    "z3_passed": None,          # K8 Z3: stderr'deki [PASS] P1-5 sayısı (son run)
    "z3_failed": None,          # K8 Z3: stderr'deki [FAIL] P1-5 sayısı
    "z3_total": None,           # K8 Z3: toplam (passed + failed)
    "lean_ok": None,            # K9 Lean: stderr'deki [K9] PASS/FAIL (True/False/None=koşulmadı)
    "lean_detail": None,        # K9 Lean: [K9] satırındaki ayrıntı metni (varsa)
    "layers": None,             # K0-K16 per-katman PASS/FAIL/SKIP (JSON'dan; dashboard "K1-K7" rozeti)
    "lineage_summary": None,    # soy hattı özeti: {ok, count, current_note, current_hash_prefix}
    "lineage_ok": None,          # skaler trend alanı (True/False/None)
    "lineage_count": None,       # skaler trend alanı (int/None)
    "status_board": None,        # tek satır durum panosu (5 ikon: Pre-commit · K0 · Bütçe · Soy hattı · K katmanları)
    "precommit_hooks": None,     # [{name, status}] — pre-commit hook sonuçları (Passed/Failed)
}
LOCK = threading.Lock()
SSE_CLIENTS = []      # bağlı /api/run client listesi (snapshot broadcast)
STREAM_CLIENTS = []   # bağlı /api/run-stream client listesi (satır akışı)
VERIFY_BUSY = threading.Lock()  # aynı anda yalnızca bir verify koşsun (loop + run-now)
VERIFY_DIR = None               # main()'de set edilir; /api/run-now handler'ı kullanır
HISTORY_PATH = None             # main()'de set edilir; JSONL trend dosyası
HISTORY_MAX = 100               # disk'te tutulacak en son run sayısı
RUNS_DIR = None                 # main()'de set edilir; run logları (stdout+stderr) dizini
RUN_LOG_MAX = 20                # disk'te tutulacak + replay edilecek en son run sayısı

HISTORY_KEYS = ("ts", "verdict", "p0", "p1", "duration_s", "budget_usd",
                "pdf_pages", "ref_count", "raw_sha256", "stripped_sha256",
                "exit_code", "refs_verified", "refs_total", "refs_mismatch",
                "refs_by_source", "hook_env", "z3_passed", "z3_failed",
                "z3_total", "lean_ok", "lean_detail", "cli_override_count",
                "lineage_ok", "lineage_count")


def snapshot_dict():
    """LATEST'ten SSE/broadcast/history için ortak snapshot alanlarını al."""
    with LOCK:
        return {k: LATEST[k] for k in HISTORY_KEYS}


# Durum panosu ikonları (CI consolidate_summary.py ile aynı).
_STATUS_ICONS = {True: "✅", False: "🔴", None: "⚠️"}


def _compute_status_board():
    """LATEST alanlarından 5 ikonlu tek satır durum panosu üret.

    CI consolidate_summary.py'deki run summary dashboard ile aynı 5 ikon:
      Pre-commit · K0 · Bütçe · Soy hattı · K katmanları
    Her biri LATEST'teki mevcut veriden hesaplanır; veri yoksa ⚠️.
    """
    ls = LATEST.get("layers") or {}
    budget = LATEST.get("budget_usd")

    # 1. Pre-commit: K1-K7 durumları (layers'dan)
    core = ["K1", "K2", "K3", "K4", "K5", "K6", "K7"]
    core_statuses = [(ls.get(k) or {}).get("status") for k in core]
    core_known = [s for s in core_statuses if s in ("PASS", "FAIL", "SKIP")]
    if any(s == "FAIL" for s in core_known):
        pc_ok = False
    elif core_known and all(s in ("PASS", "SKIP") for s in core_known):
        pc_ok = True
    else:
        pc_ok = None

    # 2. K0: P0=0, P1=0 → PASS
    p0 = LATEST.get("p0")
    p1 = LATEST.get("p1")
    k0_ok = (p0 == 0 and p1 == 0) if p0 is not None else None

    # 3. Bütçe: $30 limit altında → PASS
    budget_ok = (budget is not None and budget < 30) if budget is not None else None

    # 4. Soy hattı: lineage_summary.ok → PASS
    lin_ok = LATEST.get("lineage_ok")

    # 5. K katmanları: K8-K16 (K8 Z3, K9 Lean, K10-K16)
    ext = ["K8", "K9", "K10", "K11", "K12", "K13", "K14", "K16"]
    ext_statuses = [(ls.get(k) or {}).get("status") for k in ext]
    if any(s == "FAIL" for s in ext_statuses):
        kl_ok = False
    elif any(s == "PASS" for s in ext_statuses):
        kl_ok = True
    else:
        kl_ok = None

    parts = [
        ("Pre-commit", pc_ok),
        ("K0", k0_ok),
        ("Bütçe", budget_ok),
        ("Soy hattı", lin_ok),
        ("K katmanları", kl_ok),
    ]
    return " · ".join(f"{label} {_STATUS_ICONS.get(ok, '❓')}" for label, ok in parts)


def persist_history(rec):
    """Bir run kaydını JSONL dosyasına append et; HISTORY_MAX ile sınırla.

    Her satır tek bir run'ın snapshot'ıdır (JSON). En eski satırlar atılır,
    böylece dosya disk'te sonsuz büyümez. Thread-safe: LOCK altında çağrılır
    ve rec zaten LOCK altında alınmış olarak gelir (kilit tekrar alınmaz).

    Her yazımda history.jsonl.sha256 sidecar'ı da atomik üretilir (içeriğin
    tam SHA-256'sı, sha256sum formatında) — verify_delivery.py --check-history
    (K15) bu sidecar'ı fail-closed doğrular.
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
        content = "\n".join(lines) + "\n"
        tmp = HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, HISTORY_PATH)  # atomik: yarı yazılmış dosya asla okunmaz
        # Yanına .sha256 sidecar'ı yaz (K15 doğrulaması + reproducibility).
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sidecar = HISTORY_PATH + ".sha256"
        stmp = sidecar + ".tmp"
        with open(stmp, "w", encoding="utf-8") as f:
            f.write(f"{digest}  history.jsonl\n")
        os.replace(stmp, sidecar)  # atomik: yarı yazılmış sidecar asla okunmaz
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


def _prune_run_logs():
    """RUNS_DIR'deki run loglarını RUN_LOG_MAX ile sınırla (en eskiyi at)."""
    try:
        files = sorted(f for f in os.listdir(RUNS_DIR) if f.endswith(".json"))
    except OSError:
        return
    while len(files) > RUN_LOG_MAX:
        oldest = files.pop(0)
        try:
            os.remove(os.path.join(RUNS_DIR, oldest))
        except OSError:
            pass


def persist_run_log(rec):
    """Bir run'un TAM kaydını (stdout+stderr dahil) RUNS_DIR'e atomik yaz.

    history.jsonl yalnızca özet alanları tutar (küçük kalsın); stdout/stderr
    run loglarında saklanır ki son N run /api/run-stream'den geriye dönük
    replay edilebilsin. Dosya adı sıralanabilir ISO ts'den üretilir
    (run-<ts>.json), böylece lexicographic sıra = kronolojik sıra. Run'lar
    VERIFY_BUSY ile serileştiği için aynı anda yazışma olmaz.
    """
    if not RUNS_DIR or not rec.get("ts"):
        return
    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        safe = rec["ts"].replace(":", "").replace("+", "").replace(".", "")
        path = os.path.join(RUNS_DIR, f"run-{safe}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        os.replace(tmp, path)  # atomik: yarı yazılmış log asla okunmaz
        _prune_run_logs()
    except OSError as e:
        sys.stderr.write(f"[runs] yazılamadı: {e}\n")
        sys.stderr.flush()


def load_run_logs(limit=None):
    """RUNS_DIR'deki son `limit` run logunu oku (en eski → en yeni sırada)."""
    if not RUNS_DIR or not os.path.isdir(RUNS_DIR):
        return []
    limit = RUN_LOG_MAX if limit is None else limit
    try:
        files = sorted(f for f in os.listdir(RUNS_DIR) if f.endswith(".json"))
    except OSError:
        return []
    files = files[-limit:]
    out = []
    for fn in files:
        try:
            with open(os.path.join(RUNS_DIR, fn), encoding="utf-8") as f:
                out.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue  # bozuk logu atla; replay zincirini kırma
    return out


def run_verify(verify_dir, budget_usd=None, budget_method=None):
    """verify_delivery.py --full koş; zaten koşuyorsa atla.

    Busy-guard: verify_loop ve /api/run-now aynı anda iki verify
    çalıştırmasın (LATEST üzerine yazışma / çift maliyet).

    budget_usd / budget_method: manuel override (/api/run-now?budget=…).
    None = dosya config değeri kullanılır (default davranış).
    """
    if not VERIFY_BUSY.acquire(blocking=False):
        sys.stderr.write("[verify] zaten koşuyor — atlandı\n")
        sys.stderr.flush()
        return False
    try:
        return _run_verify_locked(verify_dir, budget_usd=budget_usd,
                                  budget_method=budget_method)
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


def build_replay_events(ts, verdict, stdout, stderr, p0=None, p1=None,
                        budget_usd=None, duration_s=None, first=False):
    """Son tamamlanmış run'un satırlarını SSE event listesi olarak üret.

    Dönüş: [(event_adı, data_json), ...] — replay-start, ardından stderr
    satırları, ardından stdout satırları (her biri `replay: true` işaretli),
    en sonda replay-end. ts yoksa boş liste döner (henüz hiç run yok).

    replay-start event'i son run'un özet alanlarını da taşır (verdict/p0/p1/
    budget_usd/duration_s) — client bunu geçmiş run sınırında görünür bir
    özet satırı olarak render eder (verdict/P0/P1/bütçe).

    Sıra, canlı akıştaki zamansal sırayı yansıtır: verify --full --json
    koşusunda insan-okur ilerleme satırları (K8 Z3 dahil) stderr'e akar,
    makine-okur JSON ise en sonda stdout'a yazılır.
    """
    if not ts:
        return []
    events = [("replay-start", json.dumps(
        {"stream": "replay-start", "ts": ts, "verdict": verdict,
         "p0": p0, "p1": p1, "budget_usd": budget_usd,
         "duration_s": duration_s, "first": first},
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


def build_replay_events_multi(records):
    """Birden çok run kaydını tek SSE replay listesi olarak üret.

    records: en eski → en yeni sıralı run kaydı listesi (load_run_logs çıktısı).
    Her run replay-start (ilk run `first: true`) … satırlar … replay-end
    (son run `last: true`) üretir; client ilk run'da kutuyu temizler, son run'da
    canlı akış sınırını çizer.
    """
    events = []
    n = len(records)
    for i, rec in enumerate(records):
        run_ev = build_replay_events(
            rec.get("ts"), rec.get("verdict"), rec.get("stdout", ""),
            rec.get("stderr", ""), rec.get("p0"), rec.get("p1"),
            rec.get("budget_usd"), rec.get("duration_s"), first=(i == 0))
        if i == n - 1 and run_ev:
            # son run'un replay-end'ine last=true işaretle
            last_name, last_data = run_ev[-1]
            last_data = json.loads(last_data)
            last_data["last"] = True
            run_ev[-1] = (last_name, json.dumps(last_data, ensure_ascii=False))
        events.extend(run_ev)
    return events


def _build_verify_cmd(py, verify_dir, budget_usd=None, budget_method=None):
    """verify_delivery.py --full komutunu kur (override parametreleriyle).

    Manuel override (/api/run-now?budget=25&budget_method=weighted):
    bütçe kalkanı dosya config yerine bu değerlerle koşar — verify_delivery.py
    bunu effective_config.json'a cli_overrides olarak işler; canlı akışta
    [CLI override] uyarısı + sarı vurgu üretir (dashboard renk kuralı).
    None = dosya config değeri (default davranış).
    """
    cmd = [py, os.path.join(verify_dir, "verify_delivery.py"),
           "--dir", verify_dir, "--full", "--json"]
    if budget_usd is not None:
        cmd += ["--budget", str(budget_usd)]
    if budget_method is not None:
        cmd += ["--budget-method", str(budget_method)]
    return cmd


def _run_verify_locked(verify_dir, budget_usd=None, budget_method=None):
    """verify_delivery.py --full komutunu çalıştır, sonucu LATEST'e yaz + broadcast.

    Bu server user shell context'te çalışıyor (bash -c exec argv ...); tüm
    proje dosyalarına tam erişim var. Venv python doğrudan çağrılır.

    Subprocess Popen ile satır satır okunur: her satır /api/run-stream
    client'larına canlı broadcast edilir (K8 Z3 ilerlemesi dahil —
    verify_delivery.py K8 Z3 stdout'unu kendi stderr'ine relay eder).

    venv python tercih et; yoksa system python fallback.
    """
    py = _find_python(verify_dir)
    cmd = _build_verify_cmd(py, verify_dir, budget_usd=budget_usd,
                            budget_method=budget_method)
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


def _parse_z3_counts(stderr):
    """stderr'deki K8 Z3 özet tablosundan [PASS]/[FAIL] P1-5 sayılarını çıkar.

    symbolic_proof_z3.py çıktısındaki özet tablo satırları indented
    '  [PASS] P1-a  …' biçimindedir (canlı ilerleme satırları '[P1-a] …'
    değil). Yalnızca P1-5 etiketleri sayılır — diğer katmanların
    '[PASS] K…' / '[OK]' satırları eşleşmez (yanlış sayım yok).
    Döndürür: (passed, failed).
    """
    passed = failed = 0
    for line in (stderr or "").splitlines():
        m = re.match(r"\s*\[\s*(PASS|FAIL)\s*\]\s*P[1-5]\b", line)
        if m:
            if m.group(1) == "PASS":
                passed += 1
            else:
                failed += 1
    return passed, failed


def _parse_lean_result(stderr):
    """stderr'deki K9 Lean sonuç satırından (ok, detail) çıkar.

    verify_delivery.py --full çıktısındaki satır:
      '[K9] Lean 4 reduct-invariance: PASS — Lean 4 reduct-invariance derlendi ve geçti'
    K9 satırı hiç yoksa (--lean-proof koşulmamışsa) → (None, None) döner;
    dashboard o zaman '?' gösterir. K9 satırı birden çok kez geçerse sonuncusu
    kazanır (tek run, tek K9 sonucu olması gerekir).
    Döndürür: (ok: bool|None, detail: str|None).
    """
    ok = None
    detail = None
    for line in (stderr or "").splitlines():
        m = re.match(r"\s*\[K9\]\s+Lean\s+4\s+reduct-invariance:\s+(PASS|FAIL)"
                     r"(?:\s*[—\-:]\s*(.*))?", line)
        if m:
            ok = m.group(1) == "PASS"
            detail = (m.group(2) or "").strip() or None
    return ok, detail


_HOOK_RE = re.compile(r"^(.+?)\.{4,}(Passed|Failed)\s*$", re.M)


def _parse_precommit_hooks(stderr):
    """stderr'deki pre-commit hook satırlarından [{name, status}] çıkar.

    pre-commit verbose çıktısı:
      Verify Stoic-Hume V5 delivery (fail-closed)........................Passed
    Satır Sonucu/Passed/Failed içeren her hook sonucunu yakalar.
    """
    hooks = []
    for m in _HOOK_RE.finditer(stderr or ""):
        hooks.append({"name": m.group(1).strip(), "status": m.group(2)})
    return hooks or None


def _refresh_precommit_hooks_bg(verify_dir):
    """Arka planda pre-commit çalıştırıp LATEST['precommit_hooks'] güncelle.

    Verify tamamlandıktan sonra çağrılır; pre-commit run (~10-30s)
    ana thread'i bloke etmez. Sonuç doğrudan LATEST'e yazılır +
    status_board yeniden hesaplanır.
    """
    _debug_log = os.path.expanduser("~/Library/Caches/com.freebuff/precommit_bg.log")
    try:
        os.makedirs(os.path.dirname(_debug_log), exist_ok=True)
        with open(_debug_log, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [precommit-bg] baslatildi, verify_dir={verify_dir}\n")
    except Exception:
        pass
    try:
        # pre-commit venv'de olmalı (_find_python system python döndürebilir)
        # ROOT = _calisma/CIKTI; venv _calisma/.venv_z3'de (1 seviye yukarı)
        calisma_dir = os.path.dirname(ROOT)
        venv_py = os.path.join(calisma_dir, ".venv_z3", "bin", "python3")
        if not os.path.isfile(venv_py):
            venv_py = os.path.join(calisma_dir, ".venv", "bin", "python3")
        if not os.path.isfile(venv_py):
            # Fallback: bilinen konumlarda venv ara
            for candidate in (
                os.path.expanduser("~/Desktop/leibniz2/_calisma"),
                os.path.join(os.getcwd(), "_calisma"),
            ):
                c = os.path.join(candidate, ".venv_z3", "bin", "python3")
                if os.path.isfile(c):
                    venv_py = c
                    break
        if os.path.isfile(venv_py):
            py = venv_py
        else:
            py = _find_python(verify_dir)
        # Debug: hangi python kullanılıyor
        try:
            with open(_debug_log, "a") as f:
                f.write(f"{time.strftime('%H:%M:%S')} [precommit-bg] python={py} venv={venv_py} cwd={verify_dir}\n")
        except Exception:
            pass
        # pre-commit run --all-files --show-diff-on-failure verbose çıktı üretir
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run(
            [py, "-m", "pre_commit", "run", "--all-files",
             "--show-diff-on-failure"],
            cwd=verify_dir or os.getcwd(),
            timeout=300, capture_output=True, text=True, env=env)
        # Debug: sonuç
        try:
            with open(_debug_log, "a") as f:
                f.write(f"{time.strftime('%H:%M:%S')} [precommit-bg] rc={result.returncode} stderr_len={len(result.stderr or '')}\n")
                # stderr'in son 500 karakterini de yaz
                if result.stderr:
                    f.write(f"{time.strftime('%H:%M:%S')} [precommit-bg] stderr_tail={result.stderr[-500:]}\n")
        except Exception:
            pass
        # pre-commit verbose çıktısı stderr'de
        output = result.stderr or result.stdout or ""
        hooks = _parse_precommit_hooks(output)
        if hooks:
            with LOCK:
                LATEST["precommit_hooks"] = hooks
                LATEST["status_board"] = _compute_status_board()
            # SSE broadcast
            for q in list(SSE_CLIENTS):
                try:
                    q.put_nowait(json.dumps({
                        "precommit_hooks": hooks,
                        "status_board": _compute_status_board(),
                    }, ensure_ascii=False))
                except Exception:
                    pass
    except Exception as e:
        # Debug: arka plan hatasını dosyaya yaz
        try:
            _debug_log = os.path.expanduser("~/Library/Caches/com.freebuff/precommit_bg.log")
            os.makedirs(os.path.dirname(_debug_log), exist_ok=True)
            with open(_debug_log, "a") as f:
                f.write(f"{time.strftime('%H:%M:%S')} [precommit-bg] hata: {e}\n")
        except Exception:
            pass


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

    z3_passed, z3_failed = _parse_z3_counts(stderr)
    lean_ok, lean_detail = _parse_lean_result(stderr)
    precommit_hooks = _parse_precommit_hooks(stderr)
    # Fallback: CI'da stderr pre-commit çıktısı üretir, yerel run'larda boş
    # olabilir. PRECOMMIT_RAPORU.json sidecar'ından okumayı dene.
    if not precommit_hooks and verify_dir:
        for candidate in (
            os.path.join(verify_dir, "logs", "PRECOMMIT_RAPORU.json"),
            os.path.join(os.path.dirname(verify_dir), "logs", "PRECOMMIT_RAPORU.json"),
            os.path.join(os.getcwd(), "logs", "PRECOMMIT_RAPORU.json"),
        ):
            if os.path.isfile(candidate):
                try:
                    with open(candidate, encoding="utf-8") as f:
                        rpt = json.load(f)
                    hooks_raw = rpt.get("hooks") or []
                    if isinstance(hooks_raw, list):
                        precommit_hooks = [
                            {"name": h.get("name", "?"), "status": h.get("status", "Unknown")}
                            for h in hooks_raw if isinstance(h, dict)
                        ] or None
                except (OSError, ValueError, KeyError):
                    pass
                if precommit_hooks:
                    break

    # Soy hattı özeti: verify_delivery.py --json lineage.generations'dan
    # son nesil (current=true) bilgisini çıkarır — dashboard rozeti için.
    lineage_summary = None
    lin = data.get("lineage") or {}
    lin_gens = lin.get("generations") or []
    if lin_gens:
        cur_gen = next((g for g in lin_gens if g.get("status", "").startswith("PASS")), None)
        if cur_gen is None and lin_gens:
            cur_gen = lin_gens[-1]  # fallback: son nesil
        if cur_gen:
            lineage_summary = {
                "ok": bool(lin.get("ok")),
                "count": len(lin_gens),
                "current_note": cur_gen.get("note", "?"),
                "current_hash": (cur_gen.get("hash") or "?")[:16],
            }

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
            # cli_overrides özeti: bütçe kalkanı dosya config yerine CLI
            # değeriyle koştuysa (--budget/--budget-method override) burada
            # işaretlenir — dashboard akış satırını beklemeden "Budget
            # override" rozeti gösterebilsin. Boş = override yok.
            "cli_overrides": (data.get("config") or {}).get("cli_overrides"),
            # skaler sayaç — tam dict'i history.jsonl'e koymadan trend/SSE'de
            # override varlığını izlenebilir yap (rozete tam dict SSE'de eklenir)
            "cli_override_count": sum(1 for v in
                ((data.get("config") or {}).get("cli_overrides") or {}).values()
                if (v or {}).get("override")),
            # hook env sürümleri (python/z3/lean/…; zaman serisi paneli)
            "hook_env": data.get("hook_env"),
            # K8 Z3: son run'un gerçek sonucu (stderr özet tablosundan)
            "z3_passed": z3_passed,
            "z3_failed": z3_failed,
            "z3_total": z3_passed + z3_failed,
            "layers": data.get("layers"),
            # K9 Lean: son run'un gerçek sonucu (stderr [K9] satırından)
            "lean_ok": lean_ok,
            "lean_detail": lean_detail,
            # Soy hattı özeti: son nesil hash + toplam nesil (dashboard)
            "lineage_summary": lineage_summary,
            # skaler trend alanları (history.jsonl trend grafiği için)
            "lineage_ok": (lineage_summary or {}).get("ok"),
            "lineage_count": (lineage_summary or {}).get("count"),
            # Pre-commit hook durumları (stderr'den ayrıştırıldı)
            "precommit_hooks": precommit_hooks,
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
        # Durum panosu: 5 ikonlu tek satır (CI consolidate_summary.py ile tutarlı)
        LATEST["status_board"] = _compute_status_board()

    # Arka planda pre-commit hook'larını yenile (verify bitti, şimdi hook'dan
    # sonuçları da dashboard'a getir —较重 ~10-30s, async;
    # ana thread'i bloke etmez).
    if verify_dir:
        threading.Thread(target=_refresh_precommit_hooks_bg,
                         args=(verify_dir,), daemon=True).start()

    # Broadcast to all SSE clients + disk'e yaz (trend + run log) + stream sonu
    with LOCK:
        rec = {k: LATEST[k] for k in HISTORY_KEYS}
        full_rec = dict(rec)
        full_rec["stdout"] = LATEST["stdout"]
        full_rec["stderr"] = LATEST["stderr"]
        # rozet için tam cli_overrides dict'i de SSE snapshot'ına gitsin
        # (history kaydına DEĞİL — trend orada sadece skaler cli_override_count
        # okur; dict yalnızca canlı/geçmiş run görünümünde gerekli)
        rec["cli_overrides"] = LATEST["cli_overrides"]
        rec["lineage_summary"] = LATEST["lineage_summary"]
        rec["status_board"] = LATEST["status_board"]
        rec["precommit_hooks"] = LATEST["precommit_hooks"]
        snapshot = json.dumps(rec)
        for q in SSE_CLIENTS:
            try:
                q.put(snapshot)
            except Exception:
                pass
        persist_history(rec)
    persist_run_log(full_rec)  # stdout/stderr dahil — son N run replay için
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
        elif self.path.startswith("/api/run-now"):
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
        if self.path.startswith("/api/run-now"):
            self.trigger_run_now()
        else:
            self._send(404, "404 not found")

    def _replay_last_run(self, ts, verdict, stdout, stderr, p0=None, p1=None,
                         budget_usd=None, duration_s=None):
        """Son tamamlanmış run'un satırlarını canlı akıştan ÖNCE gönder.

        replay-start/end event'leri sınırı işaretler; her satır `replay: true`
        taşır, böylece client geçmiş satırları canlı satırlardan ayırt eder.
        replay-start event'i son run'un özetini de taşır (verdict/P0/P1/bütçe).
        """
        events = build_replay_events(ts, verdict, stdout, stderr,
                                     p0, p1, budget_usd, duration_s)
        if not events:
            return
        buf = "".join(f"event: {ev}\ndata: {data}\n\n" for ev, data in events)
        self.wfile.write(buf.encode())
        self.wfile.flush()

    def _replay_runs(self, records):
        """Son N run'un loglarını canlı akıştan ÖNCE geriye dönük gönder.

        Her run replay-start (ilk run first=true) … satırlar … replay-end
        (son run last=true) üretir; client ilk run'da kutuyu temizler, son
        run'da canlı akış sınırını çizer.
        """
        events = build_replay_events_multi(records)
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

        Bağlantı anında SON N run'un logları geriye dönük akıtılır (her run
        replay-start/end arasında), böylece sayfa açıldığında kutu boş kalmaz:
        önce son N run'un satırları, sonra canlı satırlar gelir.
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
        replay_records = load_run_logs(RUN_LOG_MAX)
        try:
            self.wfile.write(f"event: info\ndata: {info}\n\n".encode())
            self.wfile.flush()
            self._replay_runs(replay_records)
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

        Query parametreleri (GET/POST):
          budget=25.0        → --budget 25.0 (bütçe limitini CLI ile override et;
                               CLI override kaydı + sarı vurgu + VERSION JSON)
          budget_method=X    → --budget-method X (universal|weighted|both)
        Böylece override senaryosu canlı akışta test edilebilir.
        """
        ts = datetime.now(timezone.utc).isoformat()
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        budget_usd = None
        budget_method = None
        if qs.get("budget"):
            try:
                budget_usd = float(qs["budget"][0])
            except ValueError:
                budget_usd = None
        if qs.get("budget_method") and qs["budget_method"][0] in \
                ("universal", "weighted", "both"):
            budget_method = qs["budget_method"][0]

        if not VERIFY_BUSY.acquire(blocking=False):
            self._send(409,
                       json.dumps({"status": "already_running", "ts": ts,
                                   "note": "bir verify zaten koşuyor"}),
                       content_type="application/json; charset=utf-8")
            return
        VERIFY_BUSY.release()  # thread acquire etsin; kilit tutma
        t = threading.Thread(target=run_verify,
                             args=(VERIFY_DIR,),
                             kwargs={"budget_usd": budget_usd,
                                     "budget_method": budget_method},
                             daemon=True, name="run-now")
        t.start()
        note = ("verify başladı; sonuç /api/run (SSE) ile anında yayınlanacak"
                + (f" (override: budget={budget_usd}"
                   if budget_usd is not None else "")
                + (f", method={budget_method}" if budget_method is not None
                   else "") + (")" if budget_usd is not None else ""))
        self._send(200,
                   json.dumps({"status": "started", "ts": ts,
                               "budget_override": budget_usd,
                               "budget_method_override": budget_method,
                               "note": note}),
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
            snapshot = json.dumps({k: LATEST[k] for k in HISTORY_KEYS} |
                                  {"cli_overrides": LATEST["cli_overrides"]} |
                                  {"lineage_summary": LATEST["lineage_summary"]} |
                                  {"status_board": LATEST["status_board"]} |
                                  {"precommit_hooks": LATEST["precommit_hooks"]})
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
    global PREVIEW_DIR, VERIFY_DIR, HISTORY_PATH, RUNS_DIR, RUN_LOG_MAX
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
    ap.add_argument("--replay-runs", type=int, default=RUN_LOG_MAX,
                    help="/api/run-stream'de replay edilecek + disk'te "
                         "tutulacak son run sayısı")
    args = ap.parse_args()

    PREVIEW_DIR = args.preview_dir
    VERIFY_DIR = args.dir
    HISTORY_PATH = os.path.join(args.preview_dir, "history.jsonl")
    RUNS_DIR = os.path.join(args.preview_dir, "runs")
    RUN_LOG_MAX = args.replay_runs

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