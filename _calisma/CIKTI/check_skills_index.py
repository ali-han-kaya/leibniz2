#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skills_index.py — UYUMLULUK KATMANI (yalnız yönlendirme, mantık yok).

Ölçüm ve üretim TEK yerde yaşar: `sync_skills_index.py` — README "## Skills"
tablosunun yazarı (auto-sync) ve fail-closed `--check` yüzeyi. Bu dosya iki
nedenle korunur:
  1) `test_skills_index.py` / `test_readme_skills.py` burayı import ediyor
     (import yolu kırılırsa iki test de kırılır — sessiz kapsam kaybı olur),
  2) elle `python3 _calisma/CIKTI/check_skills_index.py` çağrıları ve eski
     doküman notları bu adı kullanıyor.

Kural: burada mantık KOPYALANMAZ. Yeni davranış eklenirse
`sync_skills_index.py`'ye eklenir (iki ölçüm yüzeyi sessizce ayrışmasın).

`check(readme_text, available)` iki yüzeyi bilinçli olarak ayırır:
  - `available` verildiğinde → saf ad-kümesi denetimi (frontmatter'sız,
    veri-temelli birim testlerinin sözleşmesi),
  - verilmediğinde → gerçek drift denetimi (`sync_skills_index --check` ile
    aynı yol: blok işaretçileri + satır içeriği + isim/dizin tutarlılığı).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sync_skills_index as sync  # noqa: E402

ROOT = sync.ROOT
README = sync.README
SKILLS = sync.SKILLS

skill_names = sync.skill_names
readme_skill_names = sync.readme_skill_names


def check(readme_text=None, available=None):
    """available → saf küme denetimi; yoksa → fail-closed drift denetimi."""
    if available is not None:
        return sync.names_check(readme_text=readme_text, available=available)
    return sync.check(readme_text=readme_text)


if __name__ == "__main__":
    sys.exit(check())