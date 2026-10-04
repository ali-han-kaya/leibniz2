#!/usr/bin/env python3
"""gen_openapi_docs.py — openapi.json'dan yayınlanabilir statik referans.

Zincirin son halkası: API_CONTRACT → gen_openapi.py → openapi.json →
BURASI → docs/api/index.html (Redoc CE). Sayfa preview sunucusunda
`/api-docs.html` rotasıyla servis edilir (docs/api/ altındaki tek-kaynak
klasörü mirror'a `api-docs.html` adıyla taşınır — sync_verify_mirror.sh
GUIDE_FILES bloğu).

Neden gömülü şema + CDN: Redoc'un ~1 MB'lık standalone bundle'ı repoya
vendor etmek repoyu şişirir; CDN'den sürüm-sabitli (v2.0.0) çekmek
tek-dosya taşınabilirliğini korur. Bedeli: görüntüleme anında internet
gerekir. Şemanın KENDİSİ gömülüdür — sayfa, `openapi.json`'ın birebir
baytlarını taşır, yani ikisi arasında sessiz ayrışma olamaz (sha256
parmak izi sayfada yazılıdır).

Üretim SAF ve DETERMİNİSTİKTİR: zaman damgası, hash-rastgeleliği veya
ortam bilgisi yok — aynı şema aynı baytları verir; bu yüzden `--check`
drift kapısı commit'i fail-closed bloklayabilir.

Kullanım:
  python3 gen_openapi_docs.py           # docs/api/index.html üret + yaz
  python3 gen_openapi_docs.py --check   # diskteki sayfa güncel mi? (rc=1)
"""
import argparse
import hashlib
import json
import pathlib
import sys

CIKTI = pathlib.Path(__file__).resolve().parent
REPO_ROOT = CIKTI.parent.parent

SPEC_PATH = CIKTI / "openapi.json"
OUT_DIR = REPO_ROOT / "docs" / "api"
OUT_PATH = OUT_DIR / "index.html"

# Sürüm sabitli (cdn.redoc.ly/redoc/v2.0.0/... resmi README örneği; canlı
# doğrulandı: HTTP 200, 1042511 bayt). `latest` KULLANILMAZ — sürüm
# kayması commit'ler arasında render'ı sessizce değiştirirdi.
REDOC_VERSION = "2.0.0"
REDOC_URL = ("https://cdn.redoc.ly/redoc/v%s/bundles/redoc.standalone.js"
             % REDOC_VERSION)

# ── HTML kabuğu ────────────────────────────────────────────────────────
# Şema `</` kaçışıyla gömülür: ham `</script>` gömmeyi erken kapatırdı
# (OpenAPI description'ları HTML içerebilir).
PAGE = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESCRIPTION__">
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system,
         "Segoe UI", Roboto, sans-serif; }
  /* Redoc render edilene kadar iskelet: spec gömülü olduğu için
     ilk boya anında yerleşim kayması olmasın. */
  .fallback { max-width: 46rem; margin: 3rem auto; padding: 0 1.25rem;
              line-height: 1.6; }
  .fallback h1 { font-size: 1.5rem; margin-bottom: .25rem; }
  .fallback code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .fallback .meta { opacity: .75; font-size: .875rem; }
  noscript .fallback { display: block; }
</style>
</head>
<body>
<main>
  <noscript>
    <div class="fallback">
      <h1>__TITLE__</h1>
      <p class="meta">Bu sayfa Redoc ile şemayı çalışma anında çizer;
      JavaScript kapalıyken kaynak şemaya bakın:
      <a href="../../_calisma/CIKTI/openapi.json"><code>openapi.json</code></a>.</p>
    </div>
  </noscript>
  <div id="redoc"></div>
</main>
<script id="openapi-spec" type="application/json">
__SPEC__
</script>
<script src="__REDOC_URL__"></script>
<script>
  Redoc.init(
    // JSON.parse ŞART: Redoc.init'in ilk argümanı string ise onu FETCH
    // edilecek URL sanır (ölçüldü: string verilince "Failed to load" +
    // spec'in URL-kodlanmış hâli ekrana dökülüyor). Gömülü şema için
    // nesne geçmeli — metni olduğu gibi vermak render'ı komple kırar.
    JSON.parse(document.getElementById("openapi-spec").textContent),
    { hideDownloadButton: false, pathInMiddlePanel: false,
      nativeScrollbars: true, expandResponses: "200,201" },
    document.getElementById("redoc")
  );
</script>
</body>
</html>
"""


def render(spec_text):
    """openapi.json baytlarından deterministik HTML üretir (saf)."""
    fingerprint = hashlib.sha256(spec_text.encode("utf-8")).hexdigest()
    try:
        info = json.loads(spec_text).get("info", {})
    except json.JSONDecodeError as exc:
        raise SystemExit("HATA: openapi.json okunamadı: %s" % exc)
    title = info.get("title", "API")
    version = info.get("version", "?")
    description = ("%s — OpenAPI %s sözleşmesi (Redoc ile gömülü şemadan "
                   "render edilir)."
                   % (title, json.loads(spec_text).get("openapi", "?")))
    escaped = spec_text.replace("</", "<\\/")
    return (PAGE
            .replace("__TITLE__", _esc(title) + " v" + _esc(str(version)))
            .replace("__DESCRIPTION__", _esc(description))
            .replace("__SPEC__", escaped)
            .replace("__REDOC_URL__", REDOC_URL)
            .replace("</main>", _footer(fingerprint) + "</main>", 1))


def _esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _footer(fingerprint):
    return (
        '\n<footer class="fallback meta" aria-label="üretim kanıtı">\n'
        '  <p>Üretilen dosya — kaynak: <code>_calisma/CIKTI/openapi.json</code>'
        ' · Redoc CE v%s (sürüm sabitli CDN) · şema sha256 '
        '<code>%s</code>. Yeniden üret: '
        '<code>python3 _calisma/CIKTI/gen_openapi_docs.py</code></p>\n'
        '</footer>\n' % (REDOC_VERSION, fingerprint[:16]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="OpenAPI şemasından statik referans sayfası üretici")
    ap.add_argument("--check", action="store_true",
                    help="diskteki sayfa üretim-çıktısıyla aynı mı "
                         "(drift rc=1)")
    ap.add_argument("--output", default=str(OUT_PATH))
    args = ap.parse_args(argv)

    if not SPEC_PATH.is_file():
        print("ŞEMA YOK: %s — önce üretin: python3 %s"
              % (SPEC_PATH, CIKTI / "gen_openapi.py"))
        return 1

    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    rendered = render(spec_text)
    out = pathlib.Path(args.output)

    if args.check:
        if not out.exists():
            print("DOKÜMAN YOK: %s — üretin: python3 %s"
                  % (out, pathlib.Path(__file__).resolve()))
            return 1
        if out.read_text(encoding="utf-8") != rendered:
            print("DOKÜMAN BAYAT — şemayla yeniden üretin: python3 %s"
                  % pathlib.Path(__file__).resolve())
            return 1
        print("api-docs güncel (%d bayt, Redoc v%s)"
              % (len(rendered), REDOC_VERSION))
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(rendered)
    print("api-docs yazıldı (%d bayt): %s" % (len(rendered), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
