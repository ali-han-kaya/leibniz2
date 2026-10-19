#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pptx_open_smoke.py — deck'leri GERÇEK bir sunum motorunda açıp metin katmanını
dışa aktarır (headless LibreOffice Impress → PDF → pdftotext).

NEDEN GEREKLİ: `test_pptx_export` deck'in *paketini* doğrular (zip yapısı,
`ppt/media/` boşluğu, palet, kanvas). Paket geçerli olabilir ama dosya bir
sunum uygulamasında AÇILMAYABİLİR: pptxgenjs'in ürettiği ilişkiler
(`_rels`, `[Content_Types].xml`, slayt → layout bağları) bozuksa importer
sessizce boş/eksik sayfa açar. Bu betik o iddiayı dışarıdan ölçer:
LibreOffice deck'i açıp PDF'e render edebiliyorsa dosya gerçekten açılıyor
demektir; pdftotext'in çıkardığı metin katmanı da "slayt var ama yazı yok"
durumunu yakalar (görsel-only deck iddiası metin katmanıyla çürütülür).

Tanık metinler TEK KAYNAKTAN gelir: `test_pptx_export.DECKS[*]["slide_markers"]`.
İki kapı aynı sözleşmeyi ölçer; tanıkları buraya kopyalamak drift üretirdi.

Exit kodları (docx emsali `_calisma/docx/check_docx_libreoffice.sh` ile aynı):
  0 PASS · 1 FAIL (deck açılmadı / sayfa eksik / metin katmanı eksik)
  2 ORTAM HATASI (soffice+pdftotext yok, deck dosyası yok) — sessiz yeşil yok,
    ama "araç yok" ile "deck bozuk" log'da ayırt edilir. CI adımı 2'yi de
    KIRMIZI sayar; betik yalnız teşhisi ayırır.

Kullanım:
  python3 _calisma/CIKTI/pptx_open_smoke.py \
      [--dir _calisma/pptx] [--text-out pptx_text] [--json-out pptx_text/report.json] \
      [--soffice PATH] [--pdftotext PATH]
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_DIR = HERE.parent / "pptx"

# Tanımlar tek kaynak: paket sözleşmesini çivileyen test modülü. `slide_markers`
# slayt XML'inde aranan metinlerdir; metin katmanında da AYNI metinler
# görünmelidir (aranabilirlik iddiası iki yüzeyde de tutarlı).
sys.path.insert(0, str(HERE))
try:
    from test_pptx_export import DECKS as _DECKS  # noqa: E402
except ImportError as exc:  # pragma: no cover — kopya checkout'ta imkânsız
    raise SystemExit("ORTAM HATASI: test_pptx_export okunamadı: %s" % exc)

DECKS = {deck["name"]: tuple(marker for _part, marker in deck["slide_markers"])
         for deck in _DECKS}
SLIDES = 5
# pdftotext metni satır/sayfa sınırlarında böler; tanık araması boşluk
# normalizasyonundan sonra yapılır ("Integrity is a chain,\nnot a checkbox").
_WS = re.compile(r"\s+")
_PAGE_BREAK = "\f"


def normalize(text):
    """Metni tek satır boşluk düzenine indirger (tanık araması için)."""
    return _WS.sub(" ", text).strip()


def page_count(text):
    """pdftotext çıktısındaki DOLU sayfa sayısı (form-feed ayırıcı)."""
    return sum(1 for page in text.split(_PAGE_BREAK) if page.strip())


def missing_markers(text, markers):
    """Metin katmanında GÖRÜNMEYEN tanıklar (normalize edilmiş arama)."""
    flat = normalize(text)
    return [marker for marker in markers if normalize(marker) not in flat]


def deck_paths(directory):
    """[(deck adı, yol)] — bilinen deck'lerin beklenen yolları."""
    return [(name, pathlib.Path(directory) / (name + ".pptx")) for name in DECKS]


def _tool(path, label):
    """`--tool` override'ı ya da PATH'ten çözüm; yoksa None."""
    if path:
        return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
    return shutil.which(label)


def convert_to_pdf(soffice, pptx, work):
    """(pdf_path | None, log) — headless dönüşüm; sayfa sayısı PDF'ten okunur."""
    cmd = [soffice, "--headless", "--norestore",
           "-env:UserInstallation=file://%s/profile" % work,
           # Süzgeç adı verilmez: LibreOffice girdi türüne göre kendi PDF
           # export süzgecini seçer (Impress → impress_pdf_Export). Açık süzgeç
           # adı yanlış yazılırsa dönüşüm sessizce hiçbir şey üretmez.
           "--convert-to", "pdf", "--outdir", work, str(pptx)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=180, check=False)
    log = (proc.stdout or b"").decode("utf-8", "replace").strip()
    pdf = pathlib.Path(work) / (pathlib.Path(pptx).stem + ".pdf")
    if proc.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
        return None, "rc=%s %s" % (proc.returncode, log[-300:])
    return pdf, log[-300:]


def extract_text(pdftotext, pdf, out_dir):
    """(metin | None, txt_path | None, log) — pdftotext -layout."""
    txt = pathlib.Path(out_dir) / (pathlib.Path(pdf).stem + ".txt")
    proc = subprocess.run([pdftotext, "-layout", str(pdf), str(txt)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=120, check=False)
    log = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not txt.is_file():
        return None, None, "rc=%s %s" % (proc.returncode, log[-300:])
    return txt.read_text(encoding="utf-8", errors="replace"), txt, log[-300:]


def run(directory, text_out, soffice=None, pdftotext=None):
    """[(rapor satırı)] döndürür; çağıran exit kodunu `verdict`lerden türetir."""
    text_out = pathlib.Path(text_out)
    text_out.mkdir(parents=True, exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory() as work:
        for name, path in deck_paths(directory):
            row = {"deck": name, "pptx": str(path), "ok": False}
            if not path.is_file():
                row.update(stage="girdi", detail="deck yok: %s" % path)
                reports.append(row)
                continue
            row["pptx_bytes"] = path.stat().st_size
            pdf, log = convert_to_pdf(soffice, path, work)
            row["convert_log"] = log
            if pdf is None:
                row.update(stage="convert", detail="LibreOffice deck'i açamadı")
                reports.append(row)
                continue
            row["pdf_bytes"] = pdf.stat().st_size
            text, txt, log = extract_text(pdftotext, pdf, text_out)
            row["extract_log"] = log
            if text is None:
                row.update(stage="extract", detail="pdftotext metin üretmedi")
                reports.append(row)
                continue
            row["txt"] = str(txt)
            row["text_bytes"] = len(text.encode("utf-8"))
            row["pages"] = page_count(text)
            row["missing"] = missing_markers(text, DECKS[name])
            problems = []
            if row["pages"] != SLIDES:
                problems.append("%d sayfa (beklenen %d)" % (row["pages"], SLIDES))
            if row["missing"]:
                problems.append("metin katmanında yok: %s" % ", ".join(row["missing"]))
            if not normalize(text):
                problems.append("metin katmanı boş (slaytlar yazısız)")
            if problems:
                row.update(stage="contract", detail="; ".join(problems))
            else:
                row.update(stage="ok", ok=True)
            reports.append(row)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--text-out", default="pptx_text")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--soffice", default=None)
    parser.add_argument("--pdftotext", default=None)
    args = parser.parse_args(argv)

    soffice = _tool(args.soffice, "soffice") or _tool(args.soffice, "libreoffice")
    pdftotext = _tool(args.pdftotext, "pdftotext")
    env_problems = []
    if soffice is None:
        env_problems.append("soffice/libreoffice bulunamadı "
                            "(kurulum: libreoffice-impress)")
    if pdftotext is None:
        env_problems.append("pdftotext bulunamadı (kurulum: poppler-utils)")
    if env_problems:
        for problem in env_problems:
            print("ORTAM HATASI: %s" % problem, file=sys.stderr)
        print("verdict=ENV")
        return 2

    reports = run(args.dir, args.text_out, soffice=soffice, pdftotext=pdftotext)
    if args.json_out:
        out = pathlib.Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "soffice": soffice,
            "pdftotext": pdftotext,
            "slides_expected": SLIDES,
            "decks": reports,
            "verdict": "PASS" if all(r["ok"] for r in reports) else "FAIL",
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    env_fail = [r for r in reports if r["stage"] == "girdi"]
    for row in reports:
        print("deck=%s stage=%s pages=%s text_bytes=%s missing=%s" % (
            row["deck"], row["stage"], row.get("pages", "-"),
            row.get("text_bytes", "-"), ",".join(row.get("missing", [])) or "-"))
        if not row["ok"] and row.get("detail"):
            print("  %s" % row["detail"], file=sys.stderr)
    print("soffice=%s" % soffice)
    print("pdftotext=%s" % pdftotext)
    if env_fail:
        print("verdict=ENV (%d deck girdisi yok)" % len(env_fail))
        return 2
    failed = [r for r in reports if not r["ok"]]
    if failed:
        print("verdict=FAIL (%d/%d deck)" % (len(failed), len(reports)))
        return 1
    print("verdict=PASS (%d deck · %d slayt/deck · metin katmanı dışa aktarıldı)"
          % (len(reports), SLIDES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
