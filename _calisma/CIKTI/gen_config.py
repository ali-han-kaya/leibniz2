#!/usr/bin/env python3
"""gen_config.py — paket içeriğinden beklenen değerleri hesaplayıp config'i günceller.

verify_delivery.config.json'daki expected_pages / expected_refs /
expected_manifest değerleri, paketin GERÇEK içeriğinden türetilir:

  expected_pages    → ingiliz_empirizmi_v3.pdf  sayfa sayısı (pdfinfo)
  expected_refs     → ingiliz_empirizmi_v3.tex  References \item sayısı
  expected_manifest → MANIFEST.txt girdi sayısı (MANIFEST.txt hariç)

Betik, verify_delivery.py ile AYNI sabitleri ve yardımcı fonksiyonları
kullanır (tek kaynak, drift yok). Diğer config alanları (budget_usd,
budget_method, budget_ratios, _doc, _schema) korunur.

Kullanım:
    python3 gen_config.py                # config'i yerinde güncelle
    python3 gen_config.py --dry-run      # hesapla + göster, yazma
    python3 gen_config.py --out /tmp/cfg.json   # farklı yola yaz
    python3 gen_config.py --dir <zip'lerin olduğu dizin>

Exit kodu: 0 = güncellendi, 1 = şema doğrulaması başarısız,
           2 = ortam/hesap hatası (zip/pdfinfo/tex eksik).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_delivery as vd  # noqa: E402  (sabitler + yardımcılar tek kaynak)

# verify_delivery.py içinde hardcode edilen paket dosya adları.
PDF_NAME = "ingiliz_empirizmi_v3.pdf"
TEX_NAME = "ingiliz_empirizmi_v3.tex"


def extract_package_dir(zip_dir):
    """Dış zip + iç zip'i temp altına çıkar; pkg dizininin path'ini döndür.

    Döndürür: (pkg_path, temp_root) — temp_root çağıran tarafından silinmeli.
    """
    outer_zip = os.path.join(zip_dir, vd.KLASOR_ZIP)
    inner_rel = f"{vd.KLASOR_DIR}/{vd.IC_ZIP}"

    if not os.path.isfile(outer_zip):
        raise RuntimeError(f"dış zip bulunamadı: {outer_zip}")

    tmp = tempfile.mkdtemp(prefix="gen_config_")
    try:
        with zipfile.ZipFile(outer_zip) as z:
            if inner_rel not in z.namelist():
                raise RuntimeError(f"iç zip dış zip'te yok: {inner_rel}")
            z.extract(inner_rel, tmp)
        inner_path = os.path.join(tmp, inner_rel)
        with zipfile.ZipFile(inner_path) as iz:
            iz.extractall(tmp)
        pkg = os.path.join(tmp, vd.PKG_REL)
        if not os.path.isdir(pkg):
            raise RuntimeError(f"paket dizini bulunamadı: {pkg}")
        return pkg, tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def compute_expected(pkg):
    """pkg dizininden (pages, refs, manifest_count) üçlüsünü hesapla."""
    pdf = os.path.join(pkg, PDF_NAME)
    tex = os.path.join(pkg, TEX_NAME)
    manifest = os.path.join(pkg, "MANIFEST.txt")

    if not os.path.isfile(pdf):
        raise RuntimeError(f"PDF bulunamadı: {pdf}")
    if not os.path.isfile(tex):
        raise RuntimeError(f".tex bulunamadı: {tex}")
    if not os.path.isfile(manifest):
        raise RuntimeError(f"MANIFEST.txt bulunamadı: {manifest}")

    pages = vd.pdf_pages(pdf)
    if pages is None:
        raise RuntimeError(
            f"sayfa sayısı hesaplanamadı — pdfinfo kurulu mu? (pdf: {pdf})")

    refs = vd.count_references(tex)
    if refs is None:
        raise RuntimeError(
            f"referans sayısı hesaplanamadı — '\\section*{{References}}' "
            f"bulunamadı ({tex})")

    manifest_count = len(vd.parse_manifest(manifest))
    if manifest_count <= 0:
        raise RuntimeError(f"MANIFEST.txt'te girdi bulunamadı ({manifest})")

    return pages, refs, manifest_count


def load_config(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def validate_final_config(cfg):
    """Final config'i doğrula: önce stdlib, jsonschema varsa ayrıca."""
    errs = vd.validate_config(cfg)
    if errs:
        return errs
    try:
        import jsonschema
        schema_path = os.path.join(HERE, "verify_delivery.config.schema.json")
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        verr = list(jsonschema.Draft7Validator(schema).iter_errors(cfg))
        if verr:
            return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
                    for e in verr]
    except ImportError:
        pass  # jsonschema yoksa stdlib doğrulaması yeterli
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE,
                    help="zip'lerin bulunduğu dizin (varsayılan: bu dosyanın yanı)")
    ap.add_argument("--config", default=os.path.join(HERE, "verify_delivery.config.json"),
                    help="güncellenecek config (varsayılan: verify_delivery.config.json)")
    ap.add_argument("--out", default=None,
                    help="yazılacak config yolu (varsayılan: --config ile aynı)")
    ap.add_argument("--dry-run", action="store_true",
                    help="hesapla + göster, diske yazma")
    args = ap.parse_args()

    out_path = args.out or args.config

    # 1) Paketi çıkar + hesapla
    tmp = None
    try:
        pkg, tmp = extract_package_dir(args.dir)
        pages, refs, manifest_count = compute_expected(pkg)
    except RuntimeError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    # 2) Mevcut config'i yükle, üç değeri güncelle (diğer alanları koru)
    cfg = load_config(args.config)
    before = {
        "expected_pages": cfg.get("expected_pages"),
        "expected_refs": cfg.get("expected_refs"),
        "expected_manifest": cfg.get("expected_manifest"),
    }
    cfg["expected_pages"] = pages
    cfg["expected_refs"] = refs
    cfg["expected_manifest"] = manifest_count

    # 3) Doğrula (fail-closed)
    errs = validate_final_config(cfg)
    if errs:
        print("HATA: üretilen config şema doğrulamasını geçemedi:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # 4) Yaz (veya dry-run göster)
    if args.dry_run:
        print(f"DRY-RUN (yazılmadı) → {out_path}")
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"OK: config güncellendi → {out_path}")

    # 5) Özet (önce → sonra)
    print("\n=== Hesaplanan değerler (paket içeriğinden) ===")
    print(f"  expected_pages    : {before['expected_pages']!r} → {pages}")
    print(f"  expected_refs     : {before['expected_refs']!r} → {refs}")
    print(f"  expected_manifest : {before['expected_manifest']!r} → {manifest_count}")
    print(f"  kaynak            : {vd.KLASOR_ZIP} → {vd.IC_ZIP} → {vd.PKG_REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
