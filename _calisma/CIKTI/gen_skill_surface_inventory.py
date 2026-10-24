#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_skill_surface_inventory.py — insan-okunur skill↔yüzey envanteri.

Neden ÜRETİLİR (elle yazılmaz): `skill_surfaces.list` + `check_skill_surfaces.py`
zaten alan yüzeylerinin TEK kaynağı. Bu envanter O KAPIDAN türetilir —
sütunların hiçbiri elle yazılmaz, dolayısıyla kapıyla çelişemez. Elle yazılan
bir doküman zamanla bayatlar (ölçüldü 2026-09-28: `SKILL.md` envanteri
19 derken config'te 60 hook idi; 41 kapı belgesiz kalmıştı — bkz.
`check_precommit_inventory.py` gerekçesi). Aynı hatanın bu alanda tekrarlanmaması
için doküman ÜRETİLİR ve `--check` ile kendi kendini denetler.

Kullanım:
    python3 _calisma/CIKTI/gen_skill_surface_inventory.py            # yaz
    python3 _calisma/CIKTI/gen_skill_surface_inventory.py --check     # drift → rc 1
    python3 _calisma/CIKTI/gen_skill_surface_inventory.py --json     # veri

stdlib-only. OFFLINE (yalnız çalışma ağacı okunur).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from _calisma.CIKTI import check_skill_surfaces as gate  # noqa: E402

OUT_PATH = os.path.join(ROOT, "docs", "SKILL_SURFACE_INVENTORY.md")
FINDINGS = os.path.join(ROOT, "findings.md")

# Alan → findings.md kanıt bölümü. Bu eşleme elle bakım gerektirir ama
# `test_gen_skill_surface_inventory.py` her başlığın HÂLÂ dosyada olduğunu
# doğrular; bölüm yeniden adlanırsa test kırılır (sessiz çürüme olmaz).
EVIDENCE = {
    "rn-expo": {
        "section": "vercel-react-native-skills survey (2026-09-19)",
        "note": ("modül-belirteci araması (substring değil — \"export\" kelimesi "
                 "3 dosyada yanlış alarm üretti), hiçbir package.json'da RN "
                 "bağımlılığı, expo/metro/babel yapılandırması veya "
                 "ios/android dizini yok"),
    },
    "wrangler": {
        "section": "wrangler skill turn (2026-09-19, work/2026-09-19)",
        "note": ("CLI yok → yönetilecek komut yok; kurulum bilinçli "
                 "atlandı"),
    },
    "xlsx": {
        "section": "xlsx surface audit (2026-09-19, work/2026-09-19)",
        "note": "xlsx/exceljs bağımlılığı ve okuma/yazma yüzeyi yok",
    },
}

# MANIFEST DIŞINDA kanıtlanmış ama manifest'te OLMAYAN alan. Bu liste, dokümanın
# en değerli kısmıdır: envanter kapısı yalnız MANIFEST'te yazılı alanları
# denetler, yani "kanıt var ama kayıt yok" boşluğunu kendi kapatamaz.
UNREGISTERED_EVIDENCE = {
    "rust-async-patterns": {
        "section": "Rust surface: zero (rust-async-patterns skill)",
        "signatures": ["*.rs", "Cargo.toml", "rust-toolchain*"],
        "note": ("üç kaynaklı kanıt: git-tracked sayım, disk taraması, "
                 "cargo/rustc/rustup yok"),
    },
}


def _manifest_digest(manifest_path):
    """Manifest'in içerik özeti — kararlı (zaman bağımsız) kimlik.

    Neden özet, neden tarih DEĞİL (ölçüldü 2026-09-28): dokümana üretim
    tarihi yazıldığında her yeniden üretim farklı metin verir, dolayısıyla
    `--check` ASLA yeşile dönemez — kapı kalıcı kırmızı olur ve insanlar
    susturur. Bu, kendi koyduğumuz kapının ilk koşumda kırmızı çıkmasıyla
    yakalandı. Doküman NEDEN üretildiğini (hangi girdi) gösterir, NE ZAMAN
    üretildiğini değil: tarih taşıyan bir çıktı kendi kendi bayatlar.
    """
    import hashlib

    with open(manifest_path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def _head(entries, ok, findings, report):
    """Doküman başlığı + yöntem."""
    lines = [
        "# Skill ↔ Yüzey Envanteri",
        "",
        "<!-- ÜRETİLMİŞ DOSYA — elle düzenleme. Kaynak: `_calisma/CIKTI/"
        "skill_surfaces.list` + `check_skill_surfaces.py` canlı ölçümü. -->",
        "",
        "Bu depoda hangi beceri alanının **gerçek kod yüzeyi** var, hangisinin "
        "yok — tek bakışta. Alan yüzeyleri `skill_surfaces.list` manifest'inden, "
        "paket sayıları canlı `package.json` taramasından gelir; ikisi de elle "
        "yazılmaz.",
        "",
        "- **Kaynak manifest**: `_calisma/CIKTI/skill_surfaces.list` "
        "(%d satır, sha256:`%s`)" % (
            len(entries), _manifest_digest(os.path.join(
                HERE, "skill_surfaces.list"))),
        "- **Denetleyen kapı**: `python3 _calisma/CIKTI/check_skill_surfaces.py "
        "--check` (fail-closed)",
        "- **Bu dokümanı yeniden üret**: `python3 _calisma/CIKTI/"
        "gen_skill_surface_inventory.py`",
        "- **Drift denetimi**: `--check` → doküman bayatlarsa exit 1",
        "",
        "> `SIFIR-YÜZEY` bir eksiklik değil, **kanıtlanmış bir iddia**: o alanda "
        "iş kasten yapılmadı, çünkü uygulanacak hedef yoktu. Böyle bir alan "
        "beklenmedik bir iş üretmek zorunda değildir (pinokio emsali).",
        "",
    ]
    if not ok:
        lines += [
            "> ⚠️ **KAPI KIRMIZI**: envanter repo ile senkron DEĞİL — aşağıdaki "
            "tablolar güncel değildir. Önce `check_skill_surfaces.py --check` "
            "hatasını gider.",
            "",
        ]
    return lines


def _zero_table(report, findings_ok):
    """Başlık tablo: sıfır-yüzey alanlar — sorunun cevabı."""
    zero = sorted(report["zero_domains"])
    lines = [
        "## Sıfır-yüzey alanlar (%d) — iddia, ölçümle destekli" % len(zero),
        "",
        "| Alan | İmza paketleri | Ölçülen | Durum | Kanıt |",
        "|---|---|---|---|---|",
    ]
    pkgs = report["packages"]
    for domain in zero:
        sigs = gate.ZERO_SIGNATURES.get(domain, [])
        seen = [s for s in sigs if s in pkgs]
        verdict = "✅ iddia geçerli" if not seen else \
            "❌ İHLAL: %s göründü" % ", ".join(seen)
        ev = EVIDENCE.get(domain, {})
        anchor = "§%s" % ev["section"] if ev.get("section") else "—"
        lines.append(
            "| `%s` | %s | %d/%d imza paketi görünüyor | %s | %s |"
            % (domain, ", ".join("`%s`" % s for s in sigs) or "—",
               len(seen), len(sigs), verdict, anchor))
    if not zero:
        lines.append("| — | — | — | manifest'te zero-surface alan YOK | — |")
    lines.append("")
    if findings_ok:
        for domain in zero:
            ev = EVIDENCE.get(domain, {})
            if ev.get("note"):
                lines.append("- **`%s`** — %s" % (domain, ev["note"]))
        lines.append("")
    return lines


def _active_table(entries, report):
    """Aktif alanlar: manifest satırı + canlı paket ölçümü."""
    pkgs = report["packages"]
    rows = [e for e in entries if not e["zero"]]
    identity = [e for e in rows if e["package"] in gate.IDENTITY_ALIASES]
    code = [e for e in rows if e["package"] not in gate.IDENTITY_ALIASES]

    lines = ["## Aktif alanlar (%d satır) — kod yüzeyi olan" % len(rows), ""]
    lines += [
        "| Alan | Paket imzası | Kaç package.json | Yüzey yolu |",
        "|---|---|---|---|",
    ]
    for entry in code:
        count = pkgs.get(entry["package"], 0)
        lines.append("| `%s` | `%s` | %d | `%s` |"
                     % (entry["domain"], entry["package"], count,
                        entry["path"]))
    lines.append("")
    if identity:
        lines += [
            "### Kimlik aynaları (%d) — bağımlılık taşımaz, yalnız token yüzeyi"
            % len(identity),
            "",
            "| Alan | Takma ad | Yüzey yolu |",
            "|---|---|---|",
        ]
        for entry in identity:
            lines.append("| `%s` | `%s` | `%s` |"
                         % (entry["domain"], entry["package"], entry["path"]))
        lines += [
            "",
            "> Bunlar **paket imzası değil kimliktir**: snapshot `raw.css`/"
            "`raw.json` taşırlar, hiçbir `package.json` bağımlılığı yoktur. "
            "Kapı bunları yalnız yol varlığıyla denetler; yoksa meşru "
            "satırlarını hayalet sanırdı.",
            "",
        ]
    return lines


def _tracked_count(patterns, root=ROOT):
    """`git ls-files` ile izlenen dosya sayısı — bağımsız yüzey ölçümü.

    Disk taraması yerine izlenen dosya sayımı kullanılır: kanıt cümlesi de
    öyle ("git-tracked … = 0"). Disk taraması venv/vendor gürültüsüne takılır —
    ölçüldü: `.venv_z3/.../pre_commit/resources/empty_template_main.rs` tek
    `.rs` dosyasıdır ama **izlenmez** ve alan yüzeyi DEĞİLDİR.
    """
    import subprocess

    out = subprocess.run(["git", "ls-files"] + list(patterns),
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def _gap_section(root=ROOT):
    """MANIFEST DIŞI kanıt — bu dokümanın en dürüst kısmı."""
    lines = ["## ⚠️ Manifest'te olmayan kanıt", ""]
    if not UNREGISTERED_EVIDENCE:
        lines += ["Yok.", ""]
        return lines
    lines += [
        "Aşağıdaki alanlar `findings.md`'de **kanıtlanmış** ama "
        "`skill_surfaces.list`'te **yazılı değil**. Kapı yalnız manifest'te "
        "yazılı alanları denetlediği için bu boşluğu kendi kapatamaz — "
        "manifest'e eklenmeleri gerekir.",
        "",
        "| Alan | Kanıt | Bağımsız ölçüm (git-tracked) | Durum |",
        "|---|---|---|---|",
    ]
    for domain, ev in UNREGISTERED_EVIDENCE.items():
        sigs = ev.get("signatures", [])
        measured = ", ".join(
            "`%s` = %s" % (s, _tracked_count([s], root)) for s in sigs)
        lines.append("| `%s` | §%s | %s | manifest'te **YOK** — eklenmeli |"
                     % (domain, ev["section"], measured))
    lines.append("")
    lines += [
        "Not: bu bir **eksik kayıt**, yüzey ihlali değildir. Ölçülen değerler "
        "sıfırdır, yani iddia bugün de geçerli. Ama alan manifest'te "
        "GÖRÜNMEDİĞİ için kapı, yüzey ileride açılsa (bir `Cargo.toml` "
        "eklense) bunu sessizce geçecekti — denetlenmeyen alan, denetlenmeyen "
        "yüzey demektir.",
        "",
        "Ölçüm `git ls-files` ile yapılır (disk değil): venv/vendor içindeki "
        "izlenmeyen dosyalar alan yüzeyi sayılmaz.",
        "",
    ]
    return lines


def build(root=ROOT):
    """(markdown, veri) — doküman metni ve makine-okunur özet."""
    ok, findings, report = gate.check(root=root)
    entries, _ = gate.parse_manifest(open(
        os.path.join(HERE, "skill_surfaces.list"), encoding="utf-8").read())
    data = {
        "ok": ok,
        # Zaman damgası YOK: bkz. `_manifest_digest` gerekçesi. Özet de
        # kararlı olmalı, yoksa `--json` çıktısını karşılaştıran her şey
        # (test, script) aynı tuzağa düşer.
        "manifest_digest": _manifest_digest(
            os.path.join(HERE, "skill_surfaces.list")),
        "findings": findings,
        "zero_domains": sorted(report["zero_domains"]),
        "entries": len(entries),
    }
    lines = _head(entries, ok, data, report)
    lines += _zero_table(report, True)
    lines += _active_table(entries, report)
    lines += _gap_section(root)
    lines += [
        "## Bu tabloyu güncel tutmak",
        "",
        "1. Yeni bir alan yüzeyi eklendi/silindiyse önce "
        "`skill_surfaces.list`i güncelle "
        "(`check_skill_surfaces.py --update` yalnız ÖNERİ üretir, alan kararı "
        "insana aittir).",
        "2. Ardından bu dokümanı yeniden üret.",
        "3. `--check` kırmızıysa doküman bayattır; elle düzeltme değil, "
        "yeniden üretim gerekir.",
        "",
    ]
    return "\n".join(lines) + "\n", data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="doküman bayalsa exit 1 (fail-closed)")
    ap.add_argument("--json", action="store_true", help="makine-okunur özet")
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args(argv)

    text, data = build(args.root)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data["ok"] else 1

    if args.check:
        try:
            with open(args.out, encoding="utf-8") as fh:
                on_disk = fh.read()
        except OSError as exc:
            print("FAIL: doküman okunamadı: %s (%s)" % (args.out, exc))
            return 1
        if on_disk != text:
            print("FAIL: %s BAYAT — yeniden üret: python3 %s"
                  % (os.path.relpath(args.out, ROOT),
                     os.path.join("_calisma", "CIKTI",
                                  "gen_skill_surface_inventory.py")))
            return 1
        print("PASS: envanter dokümanı güncel (%d alan, %d sıfır-yüzey)"
              % (data["entries"], len(data["zero_domains"])))
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("yazıldı: %s" % args.out)
    print("  %d alan · %d sıfır-yüzey · kapı %s"
          % (data["entries"], len(data["zero_domains"]),
             "yeşil" if data["ok"] else "KIRMIZI"))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
