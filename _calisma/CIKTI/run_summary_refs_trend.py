#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_summary_refs_trend.py — refs-trend tablosunu GITHUB_STEP_SUMMARY'ye yaz.

refs-trend job'ı (verify.yml), refs_trend.py'nin ürettiği refs-trend.md
trend tablosunu (run'lar arası çevrimiçi referans doğrulama zaman serisi)
her push'ta run summary'de görünür kılmak için bu script ile
GITHUB_STEP_SUMMARY'ye taşır. Tablo TEK kaynaktır: refs_trend.py üretir,
bu script yalnızca taşır (render mantığı çoğaltılmaz — drift yok).

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.

Kullanım:
  python3 _calisma/CIKTI/run_summary_refs_trend.py [refs-trend/refs-trend.md]
"""
import contextlib
import os
import sys

DEFAULT_MD = "refs-trend/refs-trend.md"


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def render(sink, md_path=DEFAULT_MD):
    """refs-trend.md içeriğini sink'e taşır. True=tablo yazıldı, False=yok."""
    if not os.path.isfile(md_path):
        sink.write("## 📈 Referans trendi: tablo bulunamadı\n\n"
                   "> `refs_trend.py` henüz `refs-trend.md` üretmedi "
                   "(refs-online artifact'ı yok veya indirme başarısız). "
                   "İlk `verify` run'ları bu tabloyu doldurmaya başlar.\n")
        return False
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    sink.write("\n---\n\n## 📈 Çevrimiçi referans doğrulama trendi\n\n")
    sink.write(md)
    if not md.endswith("\n"):
        sink.write("\n")
    sink.write("\n")
    return True


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    md_path = argv[0] if argv else DEFAULT_MD
    with summary_sink() as s:
        ok = render(s, md_path)
    print("refs-trend summary written." if ok else
          "refs-trend summary: tablo yok (advisory).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
