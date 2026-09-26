#!/usr/bin/env python3
"""build_landing.py — landing_src.html -> landing.html derleyicisi.

image-to-code akışının son halkası. Yapılanlar:
  1. design-system/tokens.css dosya içeriğini @import satırının yerine gömer
     (tek-kaynak sözleşmesi: landing'te sıfır uydurma renk; tüketim
     tokens.css'ten, embed yalnız taşıma).
  2. Mühür placeholder'larını preview_server'ın son koşum snapshot'ındaki
     gerçek hash ile doldurur. Snapshot URL veya JSON/JSONL dosyasından
     okunabilir; yalnız PASS + exit_code=0 + taze 64-hex hash kabul edilir.
     Hash alanı açıkça seçilir (varsayılan: gerçek PDF'in raw SHA-256'sı).
  3. Z3 plakalarını assets/ altına kopyalar ve yolları yeniden yazar
     (self-contained preview: served-root dışı göreceli yollar 404 olur).
  4. Çıktıyı yazar ve basit tutarlılık kontrollerinden geçirir.

Fail-closed ilke: snapshot okunamaz, run tamamlanmamış, FAIL/ERROR veya
hash alanı geçersizse uydurma mühür basılmaz; build exit 1 verir.  Donmuş
qpdf determinizm kaydı bu akışın girdisi değildir.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "landing_src.html"
OUT = Path(__file__).resolve().parent / "landing.html"
ASSETS = Path(__file__).resolve().parent / "assets"
SLIDES = ROOT / "_calisma" / "CIKTI" / "slides_z3"
PLATES = ["P1-a.png", "P2.png", "P3-a.png"]
TOKENS = ROOT / "design-system" / "tokens.css"
DEFAULT_SNAPSHOT_URL = "http://127.0.0.1:8000/api/latest"
SNAPSHOT_HTTP_TIMEOUT = 5.0
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class SnapshotUnavailable(Exception):
    """Snapshot henüz hazır değil veya kaynağa ulaşılamıyor."""


class SnapshotInvalid(ValueError):
    """Snapshot okundu ancak mühür sözleşmesini karşılamıyor."""


def _decode_snapshot(text, source):
    """JSON veya JSONL metninden son snapshot kaydını çöz.

    CI'da run-history artifact'ı JSONL olabilir; dosyanın son kaydı
    preview_server'ın LATEST şemasıdır. Bozuk JSONL satırları sessizce
    atlanmaz — sahte/kısmi snapshot üretmemek için build fail-closed kalır.
    """
    try:
        value = json.loads(text)
    except json.JSONDecodeError as first_error:
        records = []
        for line_no, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SnapshotInvalid(
                    "%s JSONL satırı geçersiz (%d): %s" %
                    (source, line_no, exc)) from exc
        if not records:
            raise SnapshotInvalid("%s JSON/JSONL kaydı yok" % source) \
                from first_error
        value = records[-1]
    if not isinstance(value, dict):
        raise SnapshotInvalid("%s snapshot'ı JSON object değil" % source)
    return value


def load_snapshot(source):
    """preview_server snapshot'ını URL veya yerel dosyadan oku.

    URL kaynağı için ağ/geçici sunucu hataları SnapshotUnavailable'dır;
    bu durumda --wait-seconds ile yeni run beklenebilir. Dosya JSON/JSONL
    olabilir ve JSONL'da son kayıt kullanılır.
    """
    source = str(source)
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ("http", "https"):
        request = urllib.request.Request(
            source, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(
                    request, timeout=SNAPSHOT_HTTP_TIMEOUT) as response:
                text = response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                TimeoutError) as exc:
            raise SnapshotUnavailable(
                "preview_server snapshot okunamadı (%s): %s" % (source, exc)) \
                from exc
        return _decode_snapshot(text, source)

    if parsed.scheme and len(parsed.scheme) > 1:
        raise SnapshotInvalid("desteklenmeyen snapshot şeması: %s" %
                              parsed.scheme)
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SnapshotUnavailable(
            "snapshot dosyası okunamadı (%s): %s" % (path, exc)) from exc
    return _decode_snapshot(text, str(path))


def _snapshot_hash(snapshot, hash_field):
    """Snapshot'ta seçilen hash alanını normalize et ve doğrula."""
    top_key = "%s_sha256" % hash_field
    nested = snapshot.get("pdf_hash")
    nested = nested if isinstance(nested, dict) else {}
    values = []
    for value in (snapshot.get(top_key), nested.get(hash_field)):
        if value is not None:
            values.append(value)
    if not values:
        raise SnapshotInvalid(
            "snapshot'ta %s alanı yok" % top_key)
    normalized = []
    for value in values:
        if not isinstance(value, str) or not HASH_RE.fullmatch(value):
            raise SnapshotInvalid(
                "snapshot %s alanı 64 hex SHA-256 değil" % top_key)
        normalized.append(value.lower())
    if len(set(normalized)) != 1:
        raise SnapshotInvalid(
            "snapshot'ta %s alanları çelişkili" % top_key)
    return normalized[0]


def validate_snapshot(snapshot, hash_field="raw"):
    """Mühür için snapshot sözleşmesini doğrula; hash döndür.

    `preview_server /api/latest` alanları:
      verdict, exit_code, ts, cached, raw_sha256, stripped_sha256
    `run-history.jsonl` aynı özete sadık kaydı taşır; `cached` bu kayıtta
    bulunmayabilir. Eksik cached alanı, tamamlanmış exit_code=0 kaydı için
    taze main verify artifact'ı anlamına gelir; cached=True ise açıkça
    reddedilir.
    """
    if not isinstance(snapshot, dict):
        raise SnapshotInvalid("snapshot JSON object değil")
    if hash_field not in ("raw", "stripped"):
        raise SnapshotInvalid("hash alanı yalnız raw/stripped olabilir")

    verdict = snapshot.get("verdict")
    exit_code = snapshot.get("exit_code")
    # UNKNOWN/INIT ve exit_code'sız kayıt, sunucu hazır olduğu hâlde run
    # devam ediyor olabilir; URL bekleme döngüsü bunları tekrar denesin.
    if verdict in (None, "", "UNKNOWN", "INIT", "RUNNING") or \
            exit_code is None:
        raise SnapshotUnavailable("son koşum henüz tamamlanmadı")
    if snapshot.get("cached") is True:
        raise SnapshotUnavailable("snapshot cached; taze koşum bekleniyor")
    if verdict != "PASS":
        raise SnapshotInvalid(
            "son koşum PASS değil (verdict=%r)" % verdict)
    if exit_code != 0:
        raise SnapshotInvalid(
            "son koşum exit_code=0 değil (%r)" % exit_code)
    for field in ("p0", "p1"):
        value = snapshot.get(field)
        if value is not None and value != 0:
            raise SnapshotInvalid(
                "son koşum %s sıfır değil (%r)" % (field, value))
    ts = snapshot.get("ts")
    if not isinstance(ts, str) or not ts.strip():
        raise SnapshotInvalid("snapshot ts alanı boş")
    return _snapshot_hash(snapshot, hash_field)


def resolve_snapshot(source, hash_field="raw", wait_seconds=0.0,
                     poll_seconds=2.0):
    """Snapshot'ı oku; gerekirse hazır olana kadar URL'yi yokla.

    Returns: (snapshot_dict, normalized_hash)
    """
    if wait_seconds < 0 or poll_seconds <= 0:
        raise ValueError("wait/poll süreleri geçersiz")
    deadline = time.monotonic() + wait_seconds
    last_error = None
    while True:
        try:
            snapshot = load_snapshot(source)
            sha = validate_snapshot(snapshot, hash_field=hash_field)
            return snapshot, sha
        except SnapshotUnavailable as exc:
            last_error = exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SnapshotUnavailable(
                "canlı snapshot hazır değil (%s)" % last_error)
        time.sleep(min(poll_seconds, remaining))


def build_page(snapshot, sha, hash_field="raw", output=None, assets_dir=None):
    """Snapshot hash'ini landing HTML'ine gömer ve çıktıyı yazar."""
    output = Path(output) if output is not None else OUT
    assets_dir = Path(assets_dir) if assets_dir is not None else ASSETS
    if not isinstance(snapshot, dict):
        raise SnapshotInvalid("snapshot JSON object değil")
    if not isinstance(sha, str) or not HASH_RE.fullmatch(sha) or \
            sha != sha.lower():
        raise SnapshotInvalid("doğrulanmamış snapshot hash'i")
    src = SRC.read_text(encoding="utf-8")
    tokens = TOKENS.read_text(encoding="utf-8")

    # 1) token gömme — @import satırını dosya içeriğiyle değiştir
    imp = '<style>@import "../../design-system/tokens.css";</style>'
    if imp not in src:
        raise SnapshotInvalid("@import satırı kaynakta bulunamadı — dosya değişti mi?")
    src = src.replace(imp, "<style>\n" + tokens + "\n</style>")

    # 2) snapshot'tan doğrulanmış gerçek hash (donmuş kayıt yok).
    sha = sha.upper()
    ring = "VERIFIED • %s •" % sha[:12]
    src = src.replace("{{SEAL_RING}}", ring)
    src = src.replace("{{SEAL_CENTER}}", sha[:6] + "…")

    # 3) plakalar: self-contained kopya + yol yeniden yazımı
    assets_dir.mkdir(parents=True, exist_ok=True)
    for plate in PLATES:
        srcp = SLIDES / plate
        if not srcp.is_file():
            raise SnapshotInvalid("plaka bulunamadı: %s" % srcp)
        shutil.copyfile(srcp, assets_dir / plate)
        src = src.replace("../../CIKTI/slides_z3/%s" % plate,
                          "assets/%s" % plate)

    # 4) tutarlılık kontrolleri
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", src)
    if leftover:
        raise SnapshotInvalid("doldurulmamış placeholder: %s" % leftover)
    for banned in ("F4F1EA", "#000000", "quantumly", "nexus", "acme"):
        if banned.lower() in src.lower():
            raise SnapshotInvalid("yasaklı değer/klise: %s" % banned)
    if "--on-accent" not in src:
        raise SnapshotInvalid("btn-primary kontrast token'ı kayıp")
    if "../../CIKTI/slides_z3" in src:
        raise SnapshotInvalid("plaka yolu yeniden yazılamadı — self-contained değil")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(src, encoding="utf-8")
    return sha


def _source_from_args(args):
    if args.snapshot_url and args.snapshot_file:
        raise SnapshotInvalid(
            "--snapshot-url ile --snapshot-file birlikte kullanılamaz")
    if args.snapshot_url:
        return args.snapshot_url
    if args.snapshot_file:
        return str(args.snapshot_file)
    env_url = os.environ.get("PREVIEW_SNAPSHOT_URL")
    env_file = os.environ.get("PREVIEW_SNAPSHOT_FILE")
    if env_url and env_file:
        raise SnapshotInvalid(
            "PREVIEW_SNAPSHOT_URL ve PREVIEW_SNAPSHOT_FILE birlikte verilemez")
    return env_url or env_file or DEFAULT_SNAPSHOT_URL


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--snapshot-url", help="preview_server /api/latest URL'si")
    source.add_argument("--snapshot-file", type=Path,
                         help="preview_server snapshot JSON/JSONL dosyası")
    ap.add_argument("--wait-seconds", type=float, default=0.0,
                    help="URL snapshot hazır olana kadar bekleme süresi")
    ap.add_argument("--poll-seconds", type=float, default=2.0,
                    help="URL bekleme aralığı")
    ap.add_argument("--hash-field", choices=("raw", "stripped"), default="raw",
                    help="mühürde kullanılacak snapshot hash alanı")
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--assets-dir", type=Path, default=ASSETS)
    args = ap.parse_args(argv)

    try:
        source_value = _source_from_args(args)
        snapshot, sha = resolve_snapshot(
            source_value, hash_field=args.hash_field,
            wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)
        build_page(snapshot, sha, hash_field=args.hash_field,
                   output=args.output, assets_dir=args.assets_dir)
    except (SnapshotUnavailable, SnapshotInvalid, ValueError, OSError) as exc:
        print("BUILD FAIL: %s" % exc, file=sys.stderr)
        return 1
    print("OK: %s (%s bayt) — mühür %s (%s snapshot ts=%s)" % (
        args.output, args.output.stat().st_size, sha[:12], args.hash_field,
        snapshot.get("ts")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
