#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_doc_wrapper_sync.py — docs/PUBLISH_SCENARIO.md ↔ docs/publish_wrapper.sh
senkron kapısı (doc-script drift denetimi).

Neden: doc'taki manuel komutlar ile wrapper'daki otomatik komutlar AYNI aksiyonu
tarif eder. Biri değişince diğeri bayat kalırsa "doc-script senkronu" bozulur
(PUBLISH_SCENARIO "Senkron" notu bunu taahhüt eder). Bu script, DEĞİŞMEMESİ
GEREKEN ortak komut çapalarını (bayrak/ad/komut fiili) iki dosyada da arar;
çapa bir dosyada eksikse drift raporlanır.

Kullanım:
  python3 _calisma/CIKTI/check_doc_wrapper_sync.py

Çıkış kodları:
  0 — tüm çapalar iki dosyada da mevcut (senkron)
  1 — en az bir çapa eksik (drift; hangi dosyada eksik olduğu basılır)

Yaklaşım (pragmatik — wrapper değişken/idempotent sarmalayıcı kullanır):
  Wrapper komutları `run` sarmalayıcısı + $REPO_NAME/$OWNER değişkenleriyle
  yazılır; doc ise literal değerlerle yazar. Bu yüzden birebir satır diff'i
  yerine, DEĞİŞMEMESİ GEREKEN literal çapalar (bayrak/ad/komut fiili) iki
  dosyada da aranır.

Bilinçli asimetriler DENETLENMEZ (doc'ta var, wrapper'da olması gerekmez):
  - macOS `open "https://..."` (yerel tarayıcı açma)
  - AŞAMA 0.5 `bash _calisma/CIKTI/ci_repack_test.sh` (opsiyonel yerel adım)
  - `gh run list --limit 3/1` (manuel kolaylık — wrapper `--commit SHA` ile
    filtreler)
  - `git remote add origin git@github.com:$(gh repo view --json owner ...)`
    (doc'taki dinamik URL — wrapper `$OWNER/$REPO_NAME` kullanır)
  - branch protection web UI yönergesi (manuel; wrapper yalnızca link loglar)
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "PUBLISH_SCENARIO.md"
WRAPPER = ROOT / "docs" / "publish_wrapper.sh"

# (etiket, [her biri İKİ dosyada da bulunması gereken literal parçalar])
ANCHORS = [
    ("repo oluşturma açıklaması",
     ["fail-closed academic delivery with Z3 + Lean 4 proofs"]),
    ("repo oluşturma bayrakları",
     ["--public", "--disable-issues=false", "--disable-wiki=true",
      "--disable-projects=true", "--add-readme=false"]),
    ("ana push", ["git push -u origin main"]),
    ("default repo", ["gh repo set-default"]),
    ("remote ekleme + URL şablonu", ["git remote add origin", "git@github.com:"]),
    ("status check tek kaynak", ["status_checks.py --gh"]),
    ("precheck tek komut",
     ["bash docs/publish_precheck.sh", "--allow-remote", "--skip-smoke"]),
    ("CI izleme", ["gh run watch", "--exit-status"]),
    ("CI run listeleme (RUN_ID)", ["gh run list", "--json databaseId"]),
    ("CI job durumu", ["gh run view", "--json jobs"]),
    ("CI artifact listesi", ["--json artifacts", "--jq '.artifacts"]),
    ("incremental push modu", ["--incremental"]),
    ("koruma test branch'i", ["test/protection-check"]),
    ("PR oluşturma", ["gh pr create --base main --head test/protection-check"]),
    ("PR merge", ["gh pr merge --squash"]),
    ("uzak branch temizliği", ["git push origin --delete test/protection-check"]),
]


def check(doc, wrap, anchors=ANCHORS):
    """İki metindeki çapaları karşılaştırır; eksikleri döner.

    Dönen her kayıt: (etiket, parça, eksik_konumlar_tuple). eksik_konumlar
    deterministic sıradadır ("doc" ve/veya "wrapper"). Boş liste = senkron.
    """
    missing = []
    for label, frags in anchors:
        for frag in frags:
            where = []
            if frag not in doc:
                where.append("doc")
            if frag not in wrap:
                where.append("wrapper")
            if where:
                missing.append((label, frag, tuple(where)))
    return missing


def main() -> int:
    if not DOC.is_file() or not WRAPPER.is_file():
        print("HATA: kaynak dosyalar bulunamadı:", file=sys.stderr)
        print(f"  doc:     {DOC}", file=sys.stderr)
        print(f"  wrapper: {WRAPPER}", file=sys.stderr)
        return 2

    doc = DOC.read_text(encoding="utf-8")
    wrap = WRAPPER.read_text(encoding="utf-8")

    print("doc ↔ wrapper senkron denetimi (komut çapaları)")
    print(f"  doc:     {DOC.relative_to(ROOT)}")
    print(f"  wrapper: {WRAPPER.relative_to(ROOT)}")
    print()

    missing = check(doc, wrap)

    # PASS/FAIL satırları — check() sonucundan tek kaynak.
    missing_set = {(m[0], m[1]) for m in missing}
    for label, frags in ANCHORS:
        for frag in frags:
            if (label, frag) in missing_set:
                rec = next(m for m in missing
                           if m[0] == label and m[1] == frag)
                print(f"  [FAIL] {label}: {frag!r}  "
                      f"({' + '.join(rec[2])})")
            else:
                print(f"  [PASS] {label}: {frag!r}")

    print()
    if missing:
        print("SONUÇ: FAIL — doc ↔ wrapper drift:")
        for label, frag, where in missing:
            where_s = " + ".join(where) + " YOK"
            print(f"  - {label}: {frag!r} → {where_s}")
        print("  Düzeltme: doc ile wrapper'ı birlikte güncelle "
              "(PUBLISH_SCENARIO 'Senkron' notu).")
        return 1

    print(f"SONUÇ: PASS — {len(ANCHORS)} çapa grubu iki dosyada da senkron")
    return 0


if __name__ == "__main__":
    sys.exit(main())
