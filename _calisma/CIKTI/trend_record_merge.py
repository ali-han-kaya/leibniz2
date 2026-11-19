#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trend_record_merge.py — trend kaydını "üstüne yazma" kaybından korur.

determinism-trend haftalık ölçümü önce bot dalına iter, PR yoluyla main'e
girer. Bu yol iki kez kırıldı:

  1) 21 Eylül (koşum 35580855610): bare `git push` → main → GH006 → koşum
     kırmızı. `fa1809b` ile bot-dalı + PR yoluna geçildi.
  2) 5 Ekim (koşum 37297101317): `gh pr create` repo ayarı yüzünden
     yetkisiz ("GitHub Actions is not permitted to create ..."), adım bunu
     `|| echo` ile yutup 0 döndü → koşum YEŞİL ama kayıt dala sıkıştı
     (main 6 satır / dal 7 satır). Sonraki `--force` push, main'den türeyen
     bir commit'i dalın üstüne yazacağı için o ölçümü kalıcı olarak silerdi.

Bu araç (2)'nin kayıp yarısını kapatır: dalın kaydı ile main tabanlı yerel
kayıt birleştirilir — hiçbir **anahtar** kaybolmaz, aynı anahtar tekrarlanmaz.

Birleştirme kuralı (2026-11-19): kayıt kimliği `(date, platform, family)`;
`family` yoksa manuscript. Aynı anahtarın farklı `source_mtime` ile ikinci
satırı ayrı bir ölçüm değil, kopyadır. Yerel (main tabanlı, bu koşumun güncel
kaydı) aynı anahtar için kazanır; daldan yalnız yerelde OLMAYAN anahtarlar
taşınır. Dalda aynı anahtar birden çok kez varsa en yeni `source_mtime`
seçilir. Satırlar `{"date": "YYYY-MM-DD", ...}` ile başladığı için sözlüksel
sıra = kronolojik sıradır; sıra zaten append sırasıysa (normal durum) çıktı
girdiyle aynıdır.

Kullanım:
  python3 trend_record_merge.py --branch-file /tmp/branch.jsonl --record RECORD.jsonl

Çıkış: 0 (birleştirildi / birleştirilecek bir şey yok — hata değil),
       stdout'ta taşınan/tekilleştirilen satır sayısı. Geçersiz JSONL
       fail-closed'dır (çıkış 1). Yazma atomiktir (tmp + os.replace).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

FAMILY_DEFAULT = "manuscript"


def read_records(path: Path):
    """Dosyadaki boş olmayan satırları sırayla döndürür."""
    if not path.is_file():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _parse_record(line: str) -> dict:
    """JSONL satırını sözlük olarak döndürür; geçersizse fail-closed."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("geçersiz JSONL satırı: %s" % exc)
    if not isinstance(record, dict):
        raise ValueError("JSONL satırı nesne değil")
    return record


def record_key(line: str):
    """Kayıt kimliği: `(date, platform, family)`; family yoksa manuscript."""
    record = _parse_record(line)
    date = record.get("date")
    platform = record.get("platform")
    if not isinstance(date, str) or not date.strip():
        raise ValueError("kayıtta date eksik")
    if not isinstance(platform, str) or not platform.strip():
        raise ValueError("kayıtta platform eksik")
    family = record.get("family")
    if not isinstance(family, str) or not family.strip():
        family = FAMILY_DEFAULT
    return (date.strip(), platform.strip(), family)


def _source_mtime(line: str) -> int:
    """Sıralama için source_mtime; eksik/bozuk değer 0 sayılır."""
    try:
        value = _parse_record(line).get("source_mtime")
    except ValueError:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def merge_lines(branch, local):
    """(birleşik satırlar, yalnız daldan gelenler) — anahtar bazında dedupe.

    Yerel kayıt aynı anahtar için otoritedir (bu koşumun güncel ölçümü).
    Daldan yalnız yerelde bulunmayan anahtarlar taşınır; her anahtarın tek
    satırı kalır. Sıra kronolojiktir.
    """
    local_by_key = {}
    for line in local:
        key = record_key(line)
        previous = local_by_key.get(key)
        if previous is None or _source_mtime(line) >= _source_mtime(previous):
            local_by_key[key] = line

    branch_by_key = {}
    for line in branch:
        key = record_key(line)
        previous = branch_by_key.get(key)
        if previous is None or _source_mtime(line) > _source_mtime(previous):
            branch_by_key[key] = line

    carried = sorted(
        line for key, line in branch_by_key.items() if key not in local_by_key
    )
    merged_by_key = dict(local_by_key)
    for line in carried:
        merged_by_key[record_key(line)] = line
    merged = sorted(merged_by_key.values())
    return merged, carried


def write_atomic(path: Path, lines) -> None:
    """Atomik yazma: aynı dizinde geçici dosya + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-merge")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--branch-file", type=Path, required=True,
                    help="bot dalındaki kayıt (git show FETCH_HEAD:... çıktısı)")
    ap.add_argument("--record", type=Path, required=True,
                    help="main tabanlı yerel kayıt dosyası")
    ap.add_argument("--dry-run", action="store_true",
                    help="yazmadan yalnızca taşınacak satırı bildir")
    args = ap.parse_args(argv)

    branch = read_records(args.branch_file)
    local = read_records(args.record)
    try:
        merged, carried = merge_lines(branch, local)
    except ValueError as exc:
        print("FAIL: trend kaydı okunamadı: %s" % exc, file=sys.stderr)
        return 1

    removed = len(local) - len(merged) + len(carried)
    if carried:
        print("tasinan kayit: %d" % len(carried))
        for line in carried:
            print("  + %s" % line[:96])
    elif removed:
        print("tekillestirilen kayit: %d" % removed)
    else:
        print("0")
        return 0
    if args.dry_run:
        return 0
    if merged == local:
        # Taşınmış satır var ama birleşik çıktı yerel ile aynı: dosya zaten
        # sıralı/tekrarsız durumda — gereksiz yeniden yazma (churn) yapma.
        return 0
    write_atomic(args.record, merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
