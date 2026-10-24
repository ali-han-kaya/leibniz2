#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_player_routes.py — tarayıcı-içi oynatma paketi + /video/* rota kapısı.

Neden ayrı kapı: `_calisma/video/dist/` **gitignore'dadır** ve yalnız
`npm run build:player` üretir. Paket üretilmemişse preview_server
`/video.html` için yol gösteren bir 404 döner — yani "kapı yeşil ama ürün yok"
durumu sessizce mümkündür. Bu betik üç şeyi birlikte kanıtlar:

  1. PAKET: beklenen dört artifact var ve boş değil.
  2. ROTALAR: `/video.html`, `/video/player.js`, `/video/player.css`,
     `/video/leibniz.json` gerçek HTTP üzerinden 200 + doğru Content-Type.
  3. İÇERİK: gövde iddiaları — sayfa kabuğu `#root`/`data-src`/tek `<main>`,
     paket erişilebilirlik sözleşmesini (`Oynatıcı kontrolleri`,
     `Oynatma konumu`, `Sesi kapat`) taşır, JSON geçerli ve `meta.frames`
     beklenen kare sayısıdır. Böylece BAYAT bir paket "200 döndü" diye
     geçemez.

Fail-closed: eksik dosya, yanlış Content-Type, 200 beklenirken başka kod,
marker eksikliği veya beklenmeyen 200 (allowlist dışı `/video/*` yolu) →
exit 1. Tarama sırasında sunucu açılmamışsa `--base-url` verilir; verilmezse
betik kendi in-process preview_server'ını ephemeral portta açar.

Çıktı: stdout tablo + `verdict: PASS|FAIL`; `--json-out` ile makine-okur
sidecar (CI artifact'ına uygun).

Kullanım:
  python3 _calisma/video/check_player_routes.py [--dist PATH] [--base-url URL]
                                                [--json-out PATH]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import threading
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CIKTI = REPO_ROOT / "_calisma" / "CIKTI"

DEFAULT_DIST = HERE / "dist"
EXPECTED_FRAMES = 760


class GateFailure(RuntimeError):
    """Kapı bulgusu — exit 1."""


def _import_preview_server():
    """preview_server'ı paket içinden yükle (betik repo dışından da koşabilsin)."""
    sys.path.insert(0, str(CIKTI))
    import preview_server  # noqa: PLC0415 (lazy: --base-url verilirse gerekmez)

    return preview_server


def check_package(dist):
    """dist/ içinde beklenen artifact'lar var mı? (boyut + kapı)"""
    dist = pathlib.Path(dist)
    expected = ("player.html", "player.js", "player.css", "leibniz.json")
    rows = []
    problems = []
    for name in expected:
        path = dist / name
        if not path.is_file():
            problems.append("paket eksik: %s" % path)
            rows.append({"file": name, "bytes": None, "status": "EKSIK"})
            continue
        size = path.stat().st_size
        rows.append({"file": name, "bytes": size,
                     "status": "OK" if size > 0 else "BOS"})
        if size <= 0:
            problems.append("paket boş: %s" % path)
    return rows, problems


def _http(url, method="GET"):
    """(status, content_type, body_bytes) döndürür; HTTP hatası da döner."""
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    response.headers.get("Content-Type", ""),
                    response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def _content_claims(dist):
    """Gövde iddiaları paketten TÜRETİLİR (bayat kopya kendi kendini geçmesin).

    Sayfa kabuğu ve JSON yerelden okunur — sunucunun servis ettiği içerik
    aynı olmalı; farklıysa bayat/yabancı dist demektir.
    """
    dist = pathlib.Path(dist)
    html = (dist / "player.html").read_text(encoding="utf-8")
    data = json.loads((dist / "leibniz.json").read_text(encoding="utf-8"))
    return {
        "html_markers": ["id=\"root\"", "data-src=\"/video/leibniz.json\"",
                         "player.js"],
        "html_main_count": html.count("<main>"),
        "js_markers": ["Oynatıcı kontrolleri", "Oynatma konumu", "Sesi kapat"],
        "frames": int((data.get("meta") or {}).get("frames", -1)),
    }


_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_js_escapes(text):
    r"""esbuild'ın ASCII kaçışlarını çöz (`\u0131` → `ı`).

    ÖLÇÜLDÜ: esbuild varsayılan `charset: "ascii"` ile Türkçe harfleri
    `\uXXXX` olarak yazar; ham metinde arayan bir marker kontrolü, doğru
    paketi "bayat" diye kırmızıya düşürüyordu. Kapı build ayarından bağımsız
    olmalı: iki biçimi de aynı kabul eder.
    """
    return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def _assert_body(name, body, content_type, claims):
    """Tek yanıtın gövde sözleşmesini doğrular; sorun listesi döndürür."""
    problems = []
    text = body.decode("utf-8", "replace")
    if name == "player.html":
        for marker in claims["html_markers"]:
            if marker not in text:
                problems.append("player.html içinde %r yok" % marker)
        if claims["html_main_count"] != 1:
            problems.append("player.html main landmark sayısı %d (1 beklenir)"
                            % claims["html_main_count"])
    elif name == "player.js":
        if len(body) < 100_000:
            problems.append("player.js %d bayt — paket şüpheli küçük" % len(body))
        js_text = _decode_js_escapes(text)
        for marker in claims["js_markers"]:
            if marker not in js_text:
                problems.append("player.js içinde erişilebilirlik marker'ı %r "
                                "yok (bayat paket?)" % marker)
    elif name == "leibniz.json":
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            problems.append("leibniz.json geçersiz JSON: %s" % exc)
            return problems
        frames = int((parsed.get("meta") or {}).get("frames", -1))
        if frames != EXPECTED_FRAMES:
            problems.append("leibniz.json meta.frames=%s (beklenen %d)"
                            % (frames, EXPECTED_FRAMES))
    if "charset=utf-8" not in content_type.lower():
        # UTF-8 sözleşmesi: Türkçe metin mojibake'e düşmesin.
        problems.append("%s Content-Type charset taşımıyor: %r"
                        % (name, content_type))
    return problems


ROUTES = (
    ("/video.html", "text/html", "player.html"),
    ("/video/player.js", "text/javascript", "player.js"),
    ("/video/player.css", "text/css", "player.css"),
    ("/video/leibniz.json", "application/json", "leibniz.json"),
)

# Allowlist sözleşmesi: `/video/*` altında adı listede olmayan her şey 404.
# (Yol kaçışı dahil — sunucu allowlist dışı adı servis etmemeli.)
NOT_FOUND_ROUTES = ("/video/yok.js", "/video/player.json", "/video/../README.md")


def check_routes(base_url, dist):
    """Rotaları gerçek HTTP ile dener; (rows, problems) döndürür."""
    claims = _content_claims(dist)
    rows, problems = [], []
    for path, expected_type, name in ROUTES:
        status, content_type, body = _http(base_url + path)
        row = {"route": path, "status": status,
               "content_type": content_type.split(";")[0].strip(),
               "bytes": len(body)}
        rows.append(row)
        if status != 200:
            problems.append("%s → %s (200 beklenir)" % (path, status))
            continue
        if expected_type not in content_type.lower():
            problems.append("%s Content-Type %r (beklenen %r)"
                            % (path, content_type, expected_type))
            continue
        problems.extend("%s: %s" % (path, problem)
                        for problem in _assert_body(name, body, content_type, claims))
    for path in NOT_FOUND_ROUTES:
        status, _content_type, _body = _http(base_url + path)
        rows.append({"route": path, "status": status,
                     "content_type": None, "bytes": None})
        if status != 404:
            problems.append("%s → %s (allowlist dışı yol 404 olmalı)"
                            % (path, status))
    return rows, problems


def _serve(dist):
    """In-process preview_server; (base_url, shutdown) döndürür.

    `VIDEO_DIST` modül globali geçici olarak bu dist'e yönlendirilir ve
    shutdown'da ESKİ değerine döndürülür — aynı süreçte koşan testler
    (test_preview_video_player) başka bir dist'i görmeye devam etsin.
    """
    ps = _import_preview_server()
    previous = getattr(ps, "VIDEO_DIST", None)
    ps.VIDEO_DIST = str(dist)
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True,
                     name="player-route-gate").start()

    def shutdown():
        server.shutdown()
        server.server_close()
        if previous is None:
            try:
                del ps.VIDEO_DIST
            except AttributeError:
                pass
        else:
            ps.VIDEO_DIST = previous

    return f"http://127.0.0.1:{port}", shutdown


def run(dist=DEFAULT_DIST, base_url=None):
    """Kapıyı koşar; (exit_code, report) döndürür (sys.exit YOK)."""
    dist = pathlib.Path(dist)
    report = {"dist": str(dist), "base_url": base_url, "package": [],
              "routes": [], "problems": []}
    rows, problems = check_package(dist)
    report["package"] = rows
    report["problems"].extend(problems)
    if problems:
        report["verdict"] = "FAIL"
        return 1, report

    shutdown = None
    try:
        if base_url is None:
            base_url, shutdown = _serve(dist)
        report["base_url"] = base_url
        rows, problems = check_routes(base_url, dist)
        report["routes"] = rows
        report["problems"].extend(problems)
    except Exception as exc:  # noqa: BLE001 — fail-closed: her arıza FAIL
        report["problems"].append("tarama arızası: %s: %s"
                                  % (type(exc).__name__, exc))
    finally:
        if shutdown is not None:
            shutdown()

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    report["checked_routes"] = len(report["routes"])
    return (0 if report["verdict"] == "PASS" else 1), report


def _print_report(report):
    print("paket: %s" % report["dist"])
    for row in report["package"]:
        print("  %-14s %-6s %s" % (row["file"], row["status"],
                                   row["bytes"] if row["bytes"] is not None else "-"))
    if report.get("base_url"):
        print("base: %s" % report["base_url"])
    for row in report["routes"]:
        print("  %-24s %-4s %-16s %s" % (
            row["route"], row["status"], row.get("content_type") or "-",
            row["bytes"] if row["bytes"] is not None else "-"))
    for problem in report["problems"]:
        print("  [FAIL] %s" % problem)
    print("verdict: %s" % report["verdict"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dist", default=str(DEFAULT_DIST),
                    help="build:player çıktı dizini (varsayılan: _calisma/video/dist)")
    ap.add_argument("--base-url", default=None,
                    help="Koşan preview_server; verilmezse betik kendisi açar")
    ap.add_argument("--json-out", default=None,
                    help="Makine-okur rapor yolu (CI artifact'ı)")
    args = ap.parse_args(argv)

    rc, report = run(dist=args.dist, base_url=args.base_url)
    _print_report(report)
    if args.json_out:
        path = pathlib.Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
