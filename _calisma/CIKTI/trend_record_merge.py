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
kayıt birleştirilir — hiçbir satır kaybolmaz, aynı satırlar tekrarlanmaz.

Birleştirme kuralı: JSONL satırı TAM metin olarak kimliktir; satırlar
`{"date": "YYYY-MM-DD", ...}` ile başladığı için sözlüksel sıra = kronolojik
sıra. Sıra zaten append sırasıysa (normal durum) çıktı girdiyle aynıdır —
yani dosya yalnız gerçekten bir kayıt taşındığında değişir.

Kullanım:
  python3 trend_record_merge.py --branch-file /tmp/branch.jsonl --record RECORd.jsonl

Çıkış: 0 (birleştirildi / birleştirilecek bir şey yok — hata değil),
       stdout'ta taşınan satır sayısı. Yazma atomiktir (tmp + os.replace).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def read_records(path: Path):
    """Dosyadaki boş olmayan satırları sırayla döndürür."""
    if not path.is_file():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def merge_lines(branch, local):
    """(birleşik satırlar, yalnız daldan gelenler) — sıra + tekilleştirme korumalı.

    Sıra kuralı: satırlar sözlüksel sıralanır (JSONL satırı `{"date": "..."`
    ile başladığı için bu kronolojik sıradır) ve tam eşleşenler tekrarlanmaz.
    """
    branch_set = set(branch)
    carried = [ln for ln in branch if ln not in set(local)]
    merged = sorted(set(branch) | set(local))
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
    merged, carried = merge_lines(branch, local)
    if not carried:
        print("0")
        return 0
    print("tasinan kayit: %d" % len(carried))
    for line in carried:
        print("  + %s" % line[:96])
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
