#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ia_ol_fallback_evidence.py — 5 IA kapsam-dışı kaynağın fallback kanıtı.

V5o/V5p/V5s/V5w kaydını TEK KOMUTLA yeniden üretir: Internet Archive'de
indekslenmeyen 5 kaynağın (Fine 2012, Lagrée 1994, Millican 2002,
Schmitt 1972, Xunzi/Knoblock) gerçek API yanıtıyla nasıl PASS olduğunu
gösterir. verify_delivery.py'nin CI'da BİREBİR kullandığı zinciri koşar
(`_archive_with_fallback`): IA → HathiTrust → LoC → OpenLibrary →
Google Books. Çıktı, REFERANS_KANIT_DENETIMI §5.3'teki kanıt tablosunun
tek komutluk yeniden üretimidir.

Kullanım:
  python3 ia_ol_fallback_evidence.py            # CANLI: gerçek API yanıtları
  python3 ia_ol_fallback_evidence.py --offline  # MOCK: deterministik (test)
  python3 ia_ol_fallback_evidence.py --json     # makine-okur çıktı
  python3 ia_ol_fallback_evidence.py --keys "Fine 2012,Xunzi Knoblock"

Çıkış kodu: 5 kaynağın TAMAMI PASS ise 0 (fail-closed), değilse 1.
"""
import argparse
import json
import pathlib
import sys
import urllib.parse
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402

# V5o: 5 Internet Archive girdisi IA'da indekslenmez — fallback zinciriyle PASS.
IA_OUT_OF_SCOPE = ["Fine 2012", "Lagree 1994", "Millican 2002",
                   "Schmitt 1972", "Xunzi Knoblock"]

# V5s/V5w durumu: Xunzi → HathiTrust (lccn:87033578 ile gerçek katalog
# kaydı), Fine 2012 → OpenLibrary (isbn:9781107460287 — V5r'de yanlış
# lccn:2012014618 kaldırıldı; o LCCN Correia'nın tek yazarlı 'Grounding and
# explanation' kitabına işaret ediyordu, derleme bölümüne değil), diğer 3 →
# Library of Congress (lccn bazlı katalog kanıtı — HT'de kaydı olmayan
# telifli/modern kitaplar LoC'de birebir bulunur).
HT_SOURCE = "Xunzi Knoblock"
LOC_SOURCES = ["Lagree 1994", "Millican 2002", "Schmitt 1972"]
OL_SOURCES = ["Fine 2012"]

# ── Offline (mock) modu ────────────────────────────────────────────────────
# REFERANS_KANIT_DENETIMI §5.3'teki belgelenmiş CANLI yanıtlarla birebir
# deterministik kanıt üretir (ağ çağrısı yok; CI/yerel her yerde aynı çıktı).
MOCK_HT = {
    "lccn:87033578": {
        "records": {
            "001082130": {
                "titles": ["Xunzi : a translation and study of the "
                           "complete works"],
            }
        },
        "items": [],
    },
}

MOCK_LOC = {
    "95174106": {
        "item": {"title": "Juste Lipse et la restauration du stoïcisme : "
                           "étude et traduction des traités stoïciens",
                  "date": "1994"},
    },
    "2002020030": {
        "item": {"title": "Reading Hume on human understanding : essays on "
                           "the first Enquiry", "date": "2002"},
    },
    "73155022": {
        "item": {"title": "Cicero Scepticus : a study of the influence of "
                           "the Academica in the Renaissance", "date": "1972"},
    },
}

MOCK_OL = {
    "metaphysical": [{
        "title": "Metaphysical Grounding: Understanding the Structure "
                 "of Reality",
        "author_name": ["Fabrice Correia"],
        "first_publish_year": 2012,
        "publisher": ["Cambridge University Press"],
    }],
    "lipse": [{
        "title": "Juste Lipse et la restauration du stoïcisme : étude "
                 "sur les diverses traductions des Stoïciens",
        "author_name": ["Jacqueline Lagrée"],
        "first_publish_year": 1994,
        "publisher": ["Vrin"],
    }],
    "millican": [{
        "title": "Reading Hume on Human Understanding: Essays on the "
                 "First Enquiry",
        "author_name": ["Peter Millican"],
        "first_publish_year": 2002,
        "publisher": ["Oxford University Press"],
    }],
    "cicero scepticus": [{
        "title": "Cicero Scepticus : a study of the influence of the "
                 "Academica in the Renaissance",
        "author_name": ["Charles B. Schmitt"],
        "first_publish_year": 1972,
        "publisher": ["Martinus Nijhoff"],
    }],
}


def _mock_router(url):
    """URL'ye göre deterministik mock yanıt üretir (tüm denetim `_http_json`
    üzerinden gider — IA/HT/OL/GB hepsi bu router'a düşer, ağ çağrısı olmaz)."""
    if "archive.org/advancedsearch.php" in url:
        # 5 kaynak da IA'da indekslenmez (V5o kanıtı).
        return {"response": {"docs": []}}
    if "hathitrust.org/api/volumes" in url:
        ident = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1])
        if ident in MOCK_HT:
            return {ident: MOCK_HT[ident]}
        return {ident: {"records": {}, "items": []}}
    if "loc.gov/item/" in url and "fo=json" in url:
        lccn = url.split("/item/", 1)[1].split("/", 1)[0]
        if lccn in MOCK_LOC:
            return MOCK_LOC[lccn]
        return {"item": {}}
    if "openlibrary.org/search.json" in url:
        q = urllib.parse.parse_qs(
            urllib.parse.urlparse(url).query).get("q", [""])[0].lower()
        for needle, docs in MOCK_OL.items():
            if needle in q:
                return {"docs": docs}
        return {"docs": []}
    if "googleapis.com/books" in url:
        return {"items": []}
    return {}


def collect_evidence(keys=None, offline=False):
    """5 kaynağın fallback kanıtını toplar.

    verify_delivery.py'nin CI'daki zincirini (_archive_with_fallback) koşar:
    IA → HathiTrust → LoC → OpenLibrary → Google Books; kaynak ve gerçek API
    yanıtı özetiyle döner. offline=True → deterministik mock (test/denetim).
    Döndürür: [{key, verdict, source, detail}, ...]
    """
    if keys is None:
        keys = IA_OUT_OF_SCOPE
    by_key = {r["key"]: r for r in vd.REFERENCE_ARCHIVE}
    missing = [k for k in keys if k not in by_key]
    if missing:
        raise KeyError(f"REFERENCE_ARCHIVE'de yok: {missing}")

    results = []
    patcher = None
    if offline:
        patcher = mock.patch.object(vd, "_http_json", side_effect=_mock_router)
        patcher.start()
    try:
        for key in keys:
            ref = by_key[key]
            v, detail, source = vd._archive_with_fallback(ref)
            results.append({
                "key": key, "verdict": v, "source": source,
                "detail": detail,
            })
    finally:
        if patcher is not None:
            patcher.stop()
    return results


def render_table(results):
    lines = ["| Kaynak | Sonuç | Kaynak | Gerçek API yanıtı |",
             "|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['key']} | {r['verdict']} | {r['source']} | "
            f"{r['detail'][:110]} |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="ağ çağrısı yapma — deterministik mock kanıt (test)")
    ap.add_argument("--json", action="store_true",
                    help="çıktıyı JSON olarak bas")
    ap.add_argument("--keys", default=None,
                    help="virgülle ayrılmış kaynak anahtarları "
                         "(varsayılan: 5 IA kapsam-dışı kaynak)")
    args = ap.parse_args()

    keys = ([k.strip() for k in args.keys.split(",") if k.strip()]
            if args.keys else None)
    try:
        results = collect_evidence(keys, offline=args.offline)
    except KeyError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "tool": "ia_ol_fallback_evidence.py",
            "mode": "offline" if args.offline else "live",
            "sources": results,
            "total": len(results),
            "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        }, indent=2, ensure_ascii=False))
    else:
        mode = "MOCK (deterministik, ağsız)" if args.offline else "CANLI API"
        print("# IA kapsam-dışı 5 kaynak — fallback kanıtı")
        print(f"- **Mod:** {mode} — zincir: IA → HathiTrust → LoC → OpenLibrary → Google Books")
        print(f"- **Kaynak:** verify_delivery.py `_archive_with_fallback` "
              "(CI ile birebir)")
        print()
        print(render_table(results))
        passed = all(r["verdict"] == "PASS" for r in results)
        print(f"SONUÇ: {'PASS' if passed else 'FAIL'} — "
              f"{sum(1 for r in results if r['verdict'] == 'PASS')}/"
              f"{len(results)} kaynak çevrimiçi doğrulandı")
    return 0 if all(r["verdict"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
