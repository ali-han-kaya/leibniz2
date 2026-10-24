#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profile_load_history.py — load_history önbelleğinin istek maliyetini ölçer.

`findings.md`'deki performans iddiasının (do_GET cumtime 0.051→0.019 s,
json.loads 1500→0) KALICI harness'ı. Amaç: iddiayı bir sayı olarak değil,
tekrar koşulabilir bir ölçüm olarak saklamak.

Ölçüm gerçek kodu çalıştırır: `preview_server.Handler.do_GET` sahte bir
handler örneği üzerinde çağrılır (rota + DNS-rebinding kapısı + serve_history
dahil); yeniden yazılmış bir kopya yoktur. Kullanılan veri GERÇEK
`history.jsonl`'dır (varsayılan: preview server'ın HOME cache yolu); sentetik
fixture üretilmez — AGENTS.md kuralı: boyut/gecikme iddiası gerçek kayıtla
ölçülür. Dosya yoksa araç başarısız olur (rc=2), sessizce fixture'a düşmez.

İki mod, AYNI süreçte, AYNI dosya üzerinde:

  * cache-on  — üretim davranışı. İlk istek parse eder, sonrakiler önbellek.
  * cache-off — önbellek-öncesi davranışa eşdeğer: her istekten önce
                `_history_cache` boşaltılır. Gerçek kod yolu korunur, yalnız
                anahtar eşleşmesi engellenir (parse her istekte çalışır).

Ölçülenler:
  * istek başına duvar süresi (perf_counter; tur başına medyan/ortalama/ilk)
  * `do_GET` cumtime (cProfile) ve `json.loads` çağrı sayısı
  * yanıt gövdelerinin iki modda BİREBİR aynı olduğu (doğruluk kalkanı:
    önbellek içerik değiştirmiyor)

Kullanım:
  python3 docs/perf/profile_load_history.py
  python3 docs/perf/profile_load_history.py --requests 15 --rounds 3
  python3 docs/perf/profile_load_history.py --history ~/yol/history.jsonl

Çıktı: insan-okur tablo + tek JSON bloğu (stdout). Ham kayıt:
docs/perf/load_history_profile.txt.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import os
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CIKTI = ROOT / "_calisma" / "CIKTI"
DEFAULT_HISTORY = os.path.expanduser(
    "~/Library/Caches/com.freebuff/preview/history.jsonl")
DEFAULT_ROUTE = "/api/history"
HOST = "127.0.0.1:8000"


def _display(path: str) -> str:
    """Ev dizinini `~` ile kısalt — commit'te mutlak kullanıcı yolu kalmasın."""
    home = os.path.expanduser("~")
    return ("~" + path[len(home):]) if path.startswith(home) else path


def _load_server():
    sys.path.insert(0, str(CIKTI))
    import preview_server as ps  # noqa: E402
    return ps


def _handler(ps, route):
    """Gerçek Handler örneği; soket döngüsü çalıştırmadan.

    BaseHTTPRequestHandler'ın soket gerektiren parçaları stub'lanır; ölçülen
    yollar (`do_GET`, `_route`, `_trusted_request`, `serve_history`,
    `load_history`, `_send`) ÜRETİMDEKİ kodun kendisidir.
    """
    h = ps.Handler.__new__(ps.Handler)
    h.path = route
    h.command = "GET"
    h.request_version = "HTTP/1.1"
    h.requestline = "GET %s HTTP/1.1" % route
    h.headers = {"Host": HOST}
    h.client_address = ("127.0.0.1", 0)
    h.server = None
    h.wfile = io.BytesIO()
    h.rfile = io.BytesIO(b"")
    h.send_response = lambda code, message=None: setattr(h, "_status", code)
    h.send_header = lambda key, value: None
    h.end_headers = lambda: None
    h.log_message = lambda *a, **k: None
    return h


def _one_request(ps, route, cache):
    if not cache:
        # Önbellek-öncesi davranış: her istek parse eder.
        ps._history_cache = (None, ())
    h = _handler(ps, route)
    t0 = time.perf_counter()
    h.do_GET()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    status = getattr(h, "_status", None)
    body = h.wfile.getvalue()
    if status != 200:
        raise SystemExit("FAIL: %s -> HTTP %r (ölçüm geçersiz)" % (route, status))
    if not body:
        raise SystemExit("FAIL: %s -> boş gövde (ölçüm geçersiz)" % route)
    return elapsed_ms, body


def _timed_round(ps, route, requests, cache):
    times, body = [], b""
    for _ in range(requests):
        ms, body = _one_request(ps, route, cache)
        times.append(ms)
    return times, body


def _profile_pass(ps, route, requests, cache):
    """cProfile: do_GET cumtime + json.loads çağrı sayısı."""
    if not cache:
        ps._history_cache = (None, ())
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(requests):
        _one_request(ps, route, cache)
    profiler.disable()
    stats = pstats.Stats(profiler)

    def cumulative(func, filename_part=None):
        total, calls = 0.0, 0
        for (fn, _line, name), (_cc, nc, _tt, ct, _callers) in stats.stats.items():
            if name != func:
                continue
            if filename_part and filename_part not in fn:
                continue
            total += ct
            calls += nc
        return total, calls

    do_get_s, do_get_calls = cumulative("do_GET", "preview_server.py")
    loads_calls = cumulative("loads", "json/__init__.py")[1]
    if do_get_calls != requests:
        raise SystemExit("FAIL: beklenen %d do_GET, profillenen %d"
                         % (requests, do_get_calls))
    return do_get_s, loads_calls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", default=DEFAULT_HISTORY,
                    help="GERÇEK history.jsonl (varsayılan: %s)"
                         % _display(DEFAULT_HISTORY))
    ap.add_argument("--route", default=DEFAULT_ROUTE,
                    help="ölçülen GET rotası (varsayılan: %s)" % DEFAULT_ROUTE)
    ap.add_argument("--requests", type=int, default=15,
                    help="tur başına istek sayısı (varsayılan: 15)")
    ap.add_argument("--rounds", type=int, default=3,
                    help="ölçüm turu; raporlanan değer turların medyanı")
    args = ap.parse_args(argv)

    hist = os.path.abspath(os.path.expanduser(args.history))
    if not os.path.isfile(hist):
        print("FAIL: gerçek history.jsonl yok: %s" % _display(hist),
              file=sys.stderr)
        print("      Sentetik dosya ÜRETİLMEZ (ölçüm gerçek veri ister).",
              file=sys.stderr)
        print("      Preview server'ı bir kez koşturun ya da --history verin.",
              file=sys.stderr)
        return 2
    if args.requests < 1 or args.rounds < 1:
        print("FAIL: --requests/--rounds >= 1 olmalı", file=sys.stderr)
        return 2

    ps = _load_server()
    ps.HISTORY_PATH = hist
    raw = Path(hist).read_bytes()

    # Satır sayısı: kaynak dosyanın kendisi (parse edilen satır ≠ dönen satır;
    # HISTORY_MAX kırpması ayrıca raporlanır).
    file_rows = sum(1 for ln in raw.decode("utf-8", "replace").splitlines()
                    if ln.strip())
    ps._history_cache = (None, ())
    returned_rows = len(ps.load_history())

    rounds = {"on": [], "off": []}
    payloads = {"on": [], "off": []}
    for _ in range(args.rounds):
        times, body = _timed_round(ps, args.route, args.requests, cache=True)
        rounds["on"].append(times)
        payloads["on"].append(body)
        times, body = _timed_round(ps, args.route, args.requests, cache=False)
        rounds["off"].append(times)
        payloads["off"].append(body)

    prof = {}
    prof["on"] = _profile_pass(ps, args.route, args.requests, cache=True)
    prof["off"] = _profile_pass(ps, args.route, args.requests, cache=False)

    payloads_identical = payloads["on"] == payloads["off"] and \
        len(set(payloads["on"])) == 1

    def summary(mode):
        flat = [ms for rnd in rounds[mode] for ms in rnd]
        first = [rnd[0] for rnd in rounds[mode]]
        cum_s = statistics.median([prof[mode][0]])
        return {
            "median_ms": round(statistics.median(flat), 3),
            "mean_ms": round(statistics.mean(flat), 3),
            "first_request_ms": round(statistics.median(first), 3),
            "total_s": round(sum(flat) / 1000.0, 4),
            "do_get_cum_s": round(cum_s, 4),
            "do_get_mean_ms": round(cum_s * 1000.0 / args.requests, 3),
            "json_loads": prof[mode][1],
            "payload_bytes": len(payloads[mode][0]),
        }

    modes = {"cache_on": summary("on"), "cache_off": summary("off")}

    def pct(before, after):
        return round((after - before) / before * 100.0, 1) if before else None

    delta = {
        "do_get_cum_pct": pct(modes["cache_off"]["do_get_cum_s"],
                              modes["cache_on"]["do_get_cum_s"]),
        "median_pct": pct(modes["cache_off"]["median_ms"],
                          modes["cache_on"]["median_ms"]),
    }

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "route": args.route,
        "requests": args.requests,
        "rounds": args.rounds,
        "history": {
            "path": _display(hist),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "file_rows": file_rows,
            "returned_rows": returned_rows,
            "history_max": ps.HISTORY_MAX,
        },
        "modes": modes,
        "delta": delta,
        "payloads_identical": payloads_identical,
    }

    print("== load_history profile ==")
    print("tarih      : %s" % report["generated_at"])
    print("python     : %s (%s)" % (report["python"], report["platform"]))
    print("rota/istek : %s · %d istek × %d tur"
          % (args.route, args.requests, args.rounds))
    print("kaynak     : %s · %d B · %d dosya satırı → %d dönen satır "
          "(HISTORY_MAX=%d)"
          % (report["history"]["path"], len(raw), file_rows, returned_rows,
             ps.HISTORY_MAX))
    print("sha256     : %s" % report["history"]["sha256"])
    print("")
    print("%-10s %10s %10s %12s %10s %12s"
          % ("mod", "medyan_ms", "ort_ms", "ilk_istek_ms", "cum_s", "json.loads"))
    for label, key in (("cache-on", "cache_on"), ("cache-off", "cache_off")):
        m = modes[key]
        print("%-10s %10.3f %10.3f %12.3f %10.4f %12d"
              % (label, m["median_ms"], m["mean_ms"], m["first_request_ms"],
                 m["do_get_cum_s"], m["json_loads"]))
    print("")
    print("delta      : do_GET cumtime %+.1f%% · medyan %+.1f%%"
          % (delta["do_get_cum_pct"], delta["median_pct"]))
    print("doğruluk   : yanıt gövdeleri iki modda birebir aynı: %s"
          % ("EVET" if payloads_identical else "HAYIR"))
    print("")
    print("JSON: " + json.dumps(report, ensure_ascii=False, sort_keys=True))
    if not payloads_identical:
        print("FAIL: önbellek yanıt içeriğini değiştirdi — ölçüm geçersiz",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
