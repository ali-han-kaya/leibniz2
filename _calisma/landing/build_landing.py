#!/usr/bin/env python3
"""build_landing.py — landing_src.html -> landing.html derleyicisi.

image-to-code akışının son halkası. Yapılanlar:
  1. design-system/tokens.css dosya içeriğini @import satırının yerine gömer
     (tek-kaynak sözleşmesi: landing'te sıfır uydurma renk; tüketim
     tokens.css'ten, embed yalnız taşıma).
  2. Mühür placeholder'larını DONMUŞ KAYITTAN doldurur: committed PDF'in
     yanındaki `ingiliz_empirizmi_v3.pdf.metadata.sha256` sidecar'ının
     `# raw: <64 hex>  <name>` satırı mühür hash'inin kaynağıdır. Böylece
     mühür, build'in koştuğu ana değil REPOYA bağlıdır: aynı revizyondan
     her derleme aynı mührü basar, preview_server/koşum gerekmez.
     Hash, sidecar'ın imzaladığı committed PDF'in gerçek baytlarıyla
     çapraz doğrulanır — sidecar bayatlarsa mühür yalan olur, build kapanır.
     Sidecar biçimi ve PDF yolu TEK KAYNAKTAN gelir: `check_seal_hash`
     modülü (`parse_frozen_raw`, `PDF_REL`, `SIDECAR_SUFFIX`).
     Canlı snapshot yolu (URL veya JSON/JSONL dosyası) `--snapshot-url` /
     `--snapshot-file` / `PREVIEW_SNAPSHOT_URL` / `PREVIEW_SNAPSHOT_FILE` ile
     AÇIKÇA istenirse korunur; o modda yalnız PASS + exit_code=0 + taze
     64-hex hash kabul edilir ve doğrulama iki katmanlıdır — şekil katmanı
     doğrudan preview_server modülü (`_validate_snapshot_file_snapshot`)
     üzerinden çalışır, paralel kural yazılmaz (bkz. `validate_snapshot`).
  3. Z3 plakalarını assets/ altına kopyalar ve yolları yeniden yazar
     (self-contained preview: served-root dışı göreceli yollar 404 olur).
  4. Çıktıyı yazar ve basit tutarlılık kontrollerinden geçirir.

Fail-closed ilke: donmuş kayıt yok/bozuksa, kaydın imzaladığı PDF'in
baytlarıyla hash ayrışıyorsa ya da (snapshot modunda) run tamamlanmamış,
FAIL/ERROR veya hash alanı geçersizse uydurma mühür basılmaz; build exit 1
verir. `qpdf_determinism_output.txt` (deney kaydı) bu akışın girdisi
DEĞİLDİR; mühür kaynağı reproducible-pdf-build sidecar'ıdır.
"""
import argparse
import hashlib
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

# Snapshot ŞEKİL sözleşmesi tek kaynaktan gelir: preview_server modülü.
# (test_csp_directives.py deseni — CIKTI sys.path'e eklenir, modül import'la
# yüklenir; alt-süreç/HTTP yok.) Yükleme (URL/dosya IO) landing'te kalır;
# DOĞRULAMA modül üzerinden çalışır (iki katmanlı sözleşme, aşağıda).
_CIKTI = Path(__file__).resolve().parents[1] / "CIKTI"
if str(_CIKTI) not in sys.path:
    sys.path.insert(0, str(_CIKTI))

import preview_server as ps  # noqa: E402
# Donmuş kayıt sözleşmesinin tek kaynağı (sidecar biçimi + committed PDF yolu).
import check_seal_hash as seal_record  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "landing_src.html"
OUT = Path(__file__).resolve().parent / "landing.html"
ASSETS = Path(__file__).resolve().parent / "assets"
SLIDES = ROOT / "_calisma" / "CIKTI" / "slides_z3"
PLATES = ["P1-a.png", "P2.png", "P3-a.png"]
TOKENS = ROOT / "design-system" / "tokens.css"
# Stripe HDS tema varyantı — GENERATED (design-system/stripe/scripts/
# generate_stripe_theme.py; check-design-tokens contract 9 denetler).
# `--theme stripe` derlemesi bunu tokens.css'in yanına gömer ve <html>
# etiketine data-theme="stripe" yazar; varsayılan derleme (dark) dokunulmaz.
STRIPE_THEME = ROOT / "design-system" / "stripe" / "theme.css"
THEMES = ("dark", "light", "stripe")
HTML_TAG = '<html lang="tr">'
# Snapshot yolu VARSAYILAN DEĞİL: env ile (PREVIEW_SNAPSHOT_URL/FILE) ya da
# argümanla açıkça istenir. Varsayılan mühür kaynağı aşağıdaki donmuş kayıttır.
SNAPSHOT_HTTP_TIMEOUT = 5.0
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
# Varsayılan mühür kaynağı: committed PDF + yanındaki donmuş kayıt (sidecar).
DEFAULT_PDF = ROOT / seal_record.PDF_REL
FROZEN_SUFFIX = seal_record.SIDECAR_SUFFIX
SEAL_SOURCES = ("frozen-record", "snapshot")


class SnapshotUnavailable(Exception):
    """Snapshot henüz hazır değil veya kaynağa ulaşılamıyor."""


class SnapshotInvalid(ValueError):
    """Snapshot/donmuş kayıt okundu ancak mühür sözleşmesini karşılamıyor."""


def frozen_record_path_for(pdf_path):
    """Bir PDF'in sidecar (donmuş kayıt) yolu: `<pdf>.metadata.sha256`."""
    pdf_path = Path(pdf_path)
    return pdf_path.with_name(pdf_path.name + FROZEN_SUFFIX)


def load_frozen_seal(sidecar_path):
    """Donmuş kayıttan mühür hash'ini oku; (hash, imzalanan ad) döndür.

    Fail-closed zinciri (hepsi SnapshotInvalid):
      1. sidecar yok  → mühür kaynağı repoda bulunmalı.
      2. `# raw: <64 hex> <name>` satırı yok → sözleşme dışı kayıt.
      3. Kaydın imzaladığı PDF (sidecar'ın yanında, kayıttaki adla) yok.
      4. Kayıttaki hash ile o PDF'in gerçek baytları ayrışıyor → mühür yalan
         olurdu; taze mühür basılmaz.

    Ayrıştırma `check_seal_hash.parse_frozen_raw` üzerinden yapılır: sidecar
    biçimi iki yerde ayrı kurallarla yazılmaz (K-gate ile aynı sözleşme).
    """
    sidecar_path = Path(sidecar_path)
    if not sidecar_path.is_file():
        raise SnapshotInvalid(
            "donmuş kayıt yok: %s (beklenen: committed PDF'in yanındaki "
            "`<pdf>%s`)" % (sidecar_path, FROZEN_SUFFIX))
    try:
        text = sidecar_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SnapshotInvalid(
            "donmuş kayıt okunamadı (%s): %s" % (sidecar_path, exc)) from exc
    raw, name = seal_record.parse_frozen_raw(text)
    if raw is None or name is None:
        raise SnapshotInvalid(
            "donmuş kayıtta `# raw: <64 hex>  <name>` satırı yok: %s"
            % sidecar_path)
    pdf_path = sidecar_path.with_name(name)
    if not pdf_path.is_file():
        raise SnapshotInvalid(
            "donmuş kaydın imzaladığı PDF yok: %s (kayıtta ad: %r)"
            % (pdf_path, name))
    pdf_sha = seal_record.sha256_file(pdf_path)
    if pdf_sha != raw:
        raise SnapshotInvalid(
            "donmuş kayıt ile committed PDF ayrışıyor (%s): kayıt %s, PDF %s "
            "— mühür yalan olurdu; yeniden paketlemeden sonra kaydı tazeleyin"
            % (pdf_path.name, raw, pdf_sha))
    return raw, name


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
    """Seçilen hash alanını döndür (ince seçici — Katman 1 arkasında).

    64-hex geçerlilik + üst/nested tutarlılık Katman 1'de (preview_server
    modülü) zaten doğrulandı; burada yalnız seçim yapılır. Doğrudan,
    doğrulanmamış kayıtla çağrılırsa fail-closed (anahtar yoksa Invalid).
    """
    top_key = "%s_sha256" % hash_field
    try:
        return snapshot[top_key].lower()
    except (KeyError, AttributeError) as exc:
        raise SnapshotInvalid(
            "snapshot'ta %s alanı yok/geçersiz" % top_key) from exc


def validate_snapshot(snapshot, hash_field="raw"):
    """Mühür için snapshot sözleşmesini doğrula; hash döndür.

    İKİ KATMANLI SÖZLEŞME (şekil tek kaynağı: preview_server modülü):
      Katman 2 — landing kullanılabilirlik politikası (önce): run
        tamamlanmamış kayıt (UNKNOWN/INIT/RUNNING/verdictsiz/exit'siz)
        ya da cached kayıt → SnapshotUnavailable; URL bekleme döngüsü
        (`resolve_snapshot`) bunları tekrar dener. hash_field yalnız
        raw/stripped olabilir.
      Katman 1 — modül şekil sözleşmesi: preview_server modülünün
        `_validate_snapshot_file_snapshot` fonksiyonu PASS/0 + ts +
        raw/stripped 64-hex tutarlılığı + p0/p1 + cached şeklini doğrular;
        modülün ValueError'ü SnapshotInvalid'e çevrilir. Bu katman
        gevşetilirse modül kapısı (`test_preview_server.py` snapshot-only
        testleri) ile landing kapısı birbirinden ayrışır — tek kaynak
        budur, burada paralel kural YAZILMAZ.
    Seçim: doğrulanmış kayıttan istenen hash alanı döndürülür.

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
    # Katman 2: tamamlanmamış kayıt — bekleme döngüsü tekrar denesin.
    # (UNKNOWN/INIT ve exit_code'sız kayıt, sunucu hazır olduğu hâlde run
    # devam ediyor olabilir.)
    if verdict in (None, "", "UNKNOWN", "INIT", "RUNNING") or \
            exit_code is None:
        raise SnapshotUnavailable("son koşum henüz tamamlanmadı")
    if snapshot.get("cached") is True:
        raise SnapshotUnavailable("snapshot cached; taze koşum bekleniyor")

    # Katman 1: şekil doğrulaması doğrudan preview_server modülünden.
    try:
        ps._validate_snapshot_file_snapshot(snapshot)
    except ValueError as exc:
        raise SnapshotInvalid(str(exc)) from exc
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


PROVENANCE_FORMAT = "landing-provenance/1"


def provenance_path_for(output):
    """Çıktının yanına yazılan kalıcı provenance artifact'ının yolu."""
    output = Path(output)
    return output.parent / (output.stem + ".provenance.json")


def build_page(snapshot, sha, hash_field="raw", output=None, assets_dir=None,
               theme="dark", seal_source="snapshot", frozen_record_name=None):
    """Mühür hash'ini landing HTML'ine gömer ve çıktıyı yazar.

    `seal_source` mühür hash'inin nereden geldiğini söyler (provenance'a
    yazılır): `frozen-record` → `snapshot` None olur ve `frozen_record_name`
    kaydın imzaladığı dosya adını taşır; `snapshot` → canlı/verilmiş snapshot
    kaydı (ts/verdict provenance'a girer).

    `theme` (dark|light|stripe) yalnız <html data-theme="..."> enjekte eder;
    `stripe` ayrıca GENERATED HDS varyantını (design-system/stripe/theme.css)
    tokens.css'in hemen yanına gömer. Varsayılan `dark` çıktısı bayt-bayt
    aynı kalır (data-theme niteliği yazılmaz).
    """
    if theme not in THEMES:
        raise SnapshotInvalid("bilinmeyen tema: %r (desteklenen: %s)"
                              % (theme, ", ".join(THEMES)))
    if seal_source not in SEAL_SOURCES:
        raise SnapshotInvalid("bilinmeyen mühür kaynağı: %r (desteklenen: %s)"
                              % (seal_source, ", ".join(SEAL_SOURCES)))
    output = Path(output) if output is not None else OUT
    assets_dir = Path(assets_dir) if assets_dir is not None else ASSETS
    if seal_source == "frozen-record":
        if snapshot is not None:
            raise SnapshotInvalid(
                "frozen-record kaynağında snapshot kaydı verilemez")
        if not frozen_record_name:
            raise SnapshotInvalid(
                "frozen-record kaynağında imzalanan dosya adı (sidecar `# raw:` "
                "satırı) zorunlu")
    elif not isinstance(snapshot, dict):
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
    embed = "<style>\n" + tokens + "\n</style>"
    if theme == "stripe":
        if not STRIPE_THEME.is_file():
            raise SnapshotInvalid(
                "stripe tema varyantı yok: %s — üret: python3 design-system/"
                "stripe/scripts/generate_stripe_theme.py" % STRIPE_THEME)
        embed += ("\n<style>\n" + STRIPE_THEME.read_text(encoding="utf-8")
                  + "\n</style>")
    src = src.replace(imp, embed)

    # 1b) tema varyantı — yalnız varsayılan-dışı temalarda nitelik yazılır
    if theme != "dark":
        if HTML_TAG not in src:
            raise SnapshotInvalid(
                "html etiketi beklenen biçimde değil (%s) — data-theme "
                "enjekte edilemedi" % HTML_TAG)
        src = src.replace(HTML_TAG, '<html lang="tr" data-theme="%s">' % theme, 1)

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

    # Kalıcı build provenance artifact'ı: mühürdekiyle AYNI snapshot hash'i
    # + derleme girdileri. Duvar saati yok — girdiler aynıysa bayt-özdeş
    # (yeniden üretilebilirlik kapısı bunu committed kopyayla karşılaştırır).
    plate_hashes = {}
    for plate in PLATES:
        digest = hashlib.sha256()
        with open(assets_dir / plate, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        plate_hashes[plate] = digest.hexdigest()
    html_digest = hashlib.sha256()
    with open(output, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            html_digest.update(chunk)
    provenance = {
        "format": PROVENANCE_FORMAT,
        "seal_source": seal_source,
        "frozen_record_name": frozen_record_name,
        "snapshot_hash": sha.lower(),
        "hash_field": hash_field,
        "snapshot_ts": snapshot.get("ts") if isinstance(snapshot, dict) else None,
        "snapshot_verdict": (snapshot.get("verdict")
                             if isinstance(snapshot, dict) else None),
        "theme": theme,
        "plates": plate_hashes,
        "landing_sha256": html_digest.hexdigest(),
    }
    provenance_path_for(output).write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")
    return sha


def _snapshot_source_from_args(args):
    """Açıkça istenen snapshot kaynağı; yoksa None → donmuş kayıt kullanılır.

    Snapshot artık VARSAYILAN değil (mühür repoya bağlıdır); yalnız argüman ya
    da env ile açıkça istenirse canlı/verilmiş snapshot kullanılır.
    """
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
    return env_url or env_file


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--snapshot-url", help="preview_server /api/latest URL'si")
    source.add_argument("--snapshot-file", type=Path,
                         help="preview_server snapshot JSON/JSONL dosyası "
                              "(mühür kaynağını açıkça snapshot'a çevirir)")
    ap.add_argument("--frozen-record", type=Path, default=None,
                    help="donmuş kayıt (sidecar) yolu; varsayılan: committed "
                         "PDF'in yanındaki `<pdf>%s`" % FROZEN_SUFFIX)
    ap.add_argument("--wait-seconds", type=float, default=0.0,
                    help="URL snapshot hazır olana kadar bekleme süresi")
    ap.add_argument("--poll-seconds", type=float, default=2.0,
                    help="URL bekleme aralığı")
    ap.add_argument("--hash-field", choices=("raw", "stripped"), default="raw",
                    help="mühürde kullanılacak hash alanı (donmuş kayıt yalnız "
                         "raw taşır; stripped snapshot moduna özgüdür)")
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--assets-dir", type=Path, default=ASSETS)
    ap.add_argument("--theme", choices=THEMES, default="dark",
                    help="landing tema varyantı: dark (varsayılan), light ya "
                         "da stripe (HDS varyantı gömülür)")
    args = ap.parse_args(argv)

    try:
        if args.frozen_record is not None and (args.snapshot_url or
                                               args.snapshot_file):
            raise SnapshotInvalid(
                "--frozen-record ile --snapshot-url/--snapshot-file birlikte "
                "kullanılamaz")
        snapshot_source = _snapshot_source_from_args(args)
        snapshot = None
        if snapshot_source is None:
            # Varsayılan yol: mühür repodaki donmuş kayda bağlıdır.
            if args.hash_field != "raw":
                raise SnapshotInvalid(
                    "donmuş kayıt yalnız raw hash taşır (--hash-field %s için "
                    "snapshot kaynağı verin)" % args.hash_field)
            sidecar = (args.frozen_record if args.frozen_record is not None
                       else frozen_record_path_for(DEFAULT_PDF))
            sha, frozen_name = load_frozen_seal(sidecar)
            seal_source = "frozen-record"
        else:
            snapshot, sha = resolve_snapshot(
                snapshot_source, hash_field=args.hash_field,
                wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)
            frozen_name = None
            seal_source = "snapshot"
        build_page(snapshot, sha, hash_field=args.hash_field,
                   output=args.output, assets_dir=args.assets_dir,
                   theme=args.theme, seal_source=seal_source,
                   frozen_record_name=frozen_name)
    except (SnapshotUnavailable, SnapshotInvalid, ValueError, OSError) as exc:
        print("BUILD FAIL: %s" % exc, file=sys.stderr)
        return 1
    print("OK: %s (%s bayt) — mühür %s (%s%s, tema %s)" % (
        args.output, args.output.stat().st_size, sha[:12], seal_source,
        "" if snapshot is None else " snapshot ts=%s" % snapshot.get("ts"),
        args.theme))
    return 0


if __name__ == "__main__":
    sys.exit(main())
