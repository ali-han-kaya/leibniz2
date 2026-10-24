#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_skills_index.py — README "## Skills" tablosunun YAZARI + drift kapısı.

Sorun (ölçüldü): `skills/` dizinine yeni bir `SKILL.md` eklenince README
tablosunu güncellemek elle işti; tablo bayatlarsa `check_skills_index.py`
kırmızıya döndüğü için geliştirici ya `--no-verify` ile zorluyor ya da
kapının kırmızı kalmasına katlanıyordu. Yani kapı ya yalan söylüyor ya da
geliştiriciyi yoruyordu.

Çözüm — update-config / check-changelog-sync deseni (D2 değişmezi):
  --update  tabloyu ÜRETİR: satır kümesi ve sıra `skills/`'ten türetilir,
           değişen dosyayı `git add` eder (YAZAR).
  --check   drift varsa exit 1 (fail-closed; remedy komutu yazdırılır).
  --verify  --update + --check → yakınsamazsa exit 1. Hook bunu koşar:
           önce dener, sonra KENDİ DOĞRULAMASI yapar (sessiz onarım yok).
  --list    skill adlarını basar.

KAYIP YOK KURALI (gen_changelog.py --update ile aynı sözleşme): frontmatter
açıklaması mevcut satırların ÜZERİNE yazılmaz. README'deki insan eliyle
kurulmuş Türkçe özetler ve satır sırası korunur; yalnızca
  - skills/'e eklenen skill'ler tabloya eklenir (alfabetik, sona),
  - skills/'ten silinen skill satırları düşer,
  - blok işaretçileri (skills-index:start/end) yoksa tabloyu çevreleyerek
    eklenir (blok dışına sızan satırlar yönetilemez sayılır → drift).
Böylece `--check`, bugünün README'sinde **PASS** verir: mevcut tablo zaten
skills/ ile senkrondur, sadece satır içi kısaltma yapılmaz.

Ayrıca fail-closed ön kontroller: frontmatter'ı olmayan / `name` veya
`description` eksik / `name` ≠ dizin adı olan SKILL.md üretilemez → exit 1
(sessizce atlanmaz; yanlış satır yazmak daha kötüdür).

stdlib-only (PyYAML yok: frontmatter elle ayrıştırılır — hook ortamında
PyYAML bulunmayabilir).
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SKILLS = ROOT / "skills"

START_MARKER = "<!-- skills-index:start -->"
END_MARKER = "<!-- skills-index:end -->"
TABLE_HEADER = "| Skill | Açıklama |"
TABLE_SEP = "|---|---|"
SECTION_HEADER_RE = re.compile(r"(?im)^##\s+Skills\s*$")
ROW_RE = re.compile(r"^\|\s*`skills/([a-z0-9][a-z0-9-]*)/SKILL\.md`\s*\|\s*(.*?)\s*\|\s*$")
MAX_DESC = 140
REMEDY = "python3 _calisma/CIKTI/sync_skills_index.py --update"


class SkillError(Exception):
    """Üretilemeyen skill girdisi (fail-closed: sessiz atlama yok)."""


class Skill(object):
    __slots__ = ("name", "description", "path")

    def __init__(self, name, description, path):
        self.name = name
        self.description = description
        self.path = path


# ────────────────────────────────────────────────────────────────────────────
# frontmatter (PyYAML'sız)
def parse_frontmatter(path):
    """İlk `--- ... ---` bloğunun ÜST DÜZEY skaler anahtarları.

    İç içe bloklar (ör. `metadata:` → `openclaw:` → `emoji:`) atlanır: bunlar
    satır içi YAML'dır ve README sütununa girmez.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", text, re.S)
    if not m:
        raise SkillError("%s: frontmatter (--- ... ---) yok" % path)
    out = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] in (" ", "\t"):
            continue  # iç içe blok → bu aracın işi değil
        km = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        if not val:
            continue  # "metadata:" gibi anahtarsız blok başlığı
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key] = val
    return out


def load_skills(skills_dir=None):
    """`skills/*/SKILL.md` → [Skill] (dizin adına göre sıralı).

    Fail-closed: eksik name/description veya name≠dizin → SkillError.
    """
    d = pathlib.Path(skills_dir) if skills_dir else SKILLS
    if not d.is_dir():
        raise SkillError("skills dizini yok: %s" % d)
    out = []
    for p in sorted(d.glob("*/SKILL.md")):
        meta = parse_frontmatter(p)
        name = (meta.get("name") or "").strip()
        desc = (meta.get("description") or "").strip()
        if not name:
            raise SkillError("%s: frontmatter'da `name` yok" % p)
        if not desc:
            raise SkillError("%s: frontmatter'da `description` yok (satır "
                             "üretilemez)" % p)
        if name != p.parent.name:
            raise SkillError("%s: frontmatter name=%r, dizin adı=%r "
                             "(uyuşmuyor)" % (p, name, p.parent.name))
        out.append(Skill(name, desc, p))
    return out


# ────────────────────────────────────────────────────────────────────────────
# README tarafı
def skill_names(skills_dir=None):
    return {s.name for s in load_skills(skills_dir)}


def readme_skill_names(text):
    """`## Skills` bölümünde ADI GEÇEN skill adları (blok içi + dışı)."""
    marker = SECTION_HEADER_RE.search(text)
    if not marker:
        return set()
    tail = text[marker.end():]
    nxt = re.search(r"(?m)^##\s+", tail)
    section = tail[:nxt.start()] if nxt else tail
    return set(re.findall(r"`?skills/([a-z0-9][a-z0-9-]*)/SKILL\.md`?", section))


def _rows_in(block_text):
    return [m.groups() for m in
            (ROW_RE.match(ln) for ln in block_text.splitlines()) if m]


def find_block(text):
    """(başlangıç, bitiş) ofsetleri — işaretçiler yoksa None."""
    i = text.find(START_MARKER)
    if i == -1:
        return None
    j = text.find(END_MARKER, i)
    if j == -1:
        return None
    end = j + len(END_MARKER)
    if text[end:end + 1] == "\n":   # satır sonu blokla birlikte tüketilir
        end += 1                    # (yoksa render_readme her çalıştırmada
    return (i, end)                 #  bir boş satır eklerdi — idempotans kırılır)


def find_table_span(text):
    """İşaretçisiz (eski) tabloları bulur: başlıktan ilk `|` olmayan satıra."""
    h = text.find(TABLE_HEADER)
    if h == -1:
        return None
    end = h
    for line in text[h:].splitlines(keepends=True):
        if not line.startswith("|"):
            break
        end += len(line)
    return (h, end)


def section_span(text):
    """`## Skills` bölümünün (içindeki ilk alt-başlığa kadar) ofsetleri."""
    m = SECTION_HEADER_RE.search(text)
    if not m:
        return None
    tail = text[m.end():]
    nxt = re.search(r"(?m)^##\s+", tail)
    return (m.end(), m.end() + (nxt.start() if nxt else len(tail)))


def existing_rows(text):
    """Blok içindeki (yoksa işaretçisiz tablodaki) satırlar — SIRASI KORUNUR."""
    span = find_block(text)
    if span is None:
        span = find_table_span(text)
    if span is None:
        return []
    return _rows_in(text[span[0]:span[1]])


def unmanaged_rows(text):
    """Blok DIŞINDA kalan tablo satırları — yönetilemez (drift)."""
    span = find_block(text)
    if span is None:
        return []
    outside = text[:span[0]] + text[span[1]:]
    return _rows_in(outside)


def clean_desc(raw, cap=True):
    """Frontmatter açıklamasını tablo hücresine çevirir.

    - satır sonu/çoklu boşluk → tek boşluk,
    - `|` → `\\|` (tabloyu bölmeyen escape),
    - uzun metin kelime sınırında `…` ile kırpılır (deterministik tavan).
    """
    val = " ".join(str(raw).split())
    if cap and len(val) > MAX_DESC:
        cut = val[:MAX_DESC - 1]
        sp = cut.rfind(" ")
        if sp > 40:
            cut = cut[:sp]
        val = cut.rstrip(" ,;:.-") + "…"
    return val.replace("|", "\\|")


def render_block(existing, skills):
    """Üretilecek blok metni: sıra + insan özetleri korunur, yeniler eklenir."""
    rows = _rows_in(existing) if isinstance(existing, str) else [
        tuple(r) for r in (existing or [])]
    present = {s.name: s for s in skills}
    out = []
    for name, desc in rows:
        if name in present:               # kurumsal sıra + özet korunur
            out.append((name, desc))
    known = {r[0] for r in rows}
    for name in sorted(present):          # yeniler alfabetik, sona
        if name not in known:
            out.append((name, clean_desc(present[name].description)))
    lines = [START_MARKER, TABLE_HEADER, TABLE_SEP]
    for name, desc in out:
        lines.append("| `skills/%s/SKILL.md` | %s |" % (name, desc))
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def render_readme(text, skills):
    """README metnini hedef metne çevirir (blok ekleme/yenileme dâhil)."""
    if find_block(text) is None:
        tspan = find_table_span(text)
        if tspan is not None:
            i, j = tspan
            body = text[i:j].rstrip("\n")
            text = (text[:i] + START_MARKER + "\n" + body + "\n" + END_MARKER
                    + "\n" + text[j:])
        else:
            span = section_span(text)
            if span is None:
                raise SkillError("README'de `## Skills` bölümü yok — "
                                 "tablo nereye yazılacak?")
            i = span[1]
            while i > 0 and text[i - 1] == "\n":
                i -= 1
            text = text[:i] + "\n\n" + render_block("", skills) + text[i:]
            return text
    i, j = find_block(text)
    return text[:i] + render_block(text[i:j], skills) + text[j:]


def drift_lines(text, skills):
    """Ölçülebilir drift listesi (boş = senkron)."""
    rows = existing_rows(text)
    listed = {name for name, _ in rows}
    expected = {s.name for s in skills}
    out = []
    for name in sorted(expected - listed):
        out.append("eksik: skills/%s/SKILL.md tabloda yok" % name)
    for name in sorted(listed - expected):
        out.append("bayat: skills/%s/SKILL.md artık skills/ altında değil" % name)
    unmanaged = unmanaged_rows(text)
    for name, _ in unmanaged:
        out.append("yönetilmeyen: `%s` satırı blok dışında" % name)
    if find_block(text) is None:
        out.append("blok işaretçisi yok (%s / %s)" % (START_MARKER, END_MARKER))
    elif render_readme(text, skills) != text:
        out.append("tablo içeriği skills/ ile senkron değil")
    return out


def check(readme_text=None, skills_dir=None, readme_path=None):
    """Fail-closed drift denetimi; senkron değilse exit 1."""
    try:
        skills = load_skills(skills_dir)
        text = readme_text if readme_text is not None else _read(readme_path)
        drift = drift_lines(text, skills)
    except SkillError as exc:
        print("FAIL: skills index ölçülemedi — %s" % exc)
        print("  remedy: %s" % REMEDY)
        return 1
    except OSError as exc:
        print("FAIL: README okunamadı — %s" % exc)
        print("  remedy: %s" % REMEDY)
        return 1
    if drift:
        print("FAIL: README skills index drift (%d bulgu)" % len(drift))
        for line in drift:
            print("  " + line)
        print("  remedy: %s" % REMEDY)
        return 1
    print("PASS: README skills index senkron (%d skill)" % len(skills))
    return 0


def update(readme_text=None, skills_dir=None, readme_path=None, stage=True):
    """Tabloyu üretir, README'i yazar, `git add` eder. Değiştiyse True.

    SkillError YAYILIR (fail-closed): yakınsayamayan yazar sessizce geçmez.
    """
    skills = load_skills(skills_dir)
    path = pathlib.Path(readme_path) if readme_path else README
    text = readme_text if readme_text is not None else path.read_text(encoding="utf-8")
    target = render_readme(text, skills)
    if target == text:
        print("skills index: güncel (%d skill)" % len(skills))
        return False
    before = len(existing_rows(text))
    after = len(existing_rows(target))
    path.write_text(target, encoding="utf-8")
    print("ℹ️ README skills index güncellendi: %d → %d satır (%s)"
          % (before, after, path.name))
    if stage:
        try:
            subprocess.run(["git", "add", path.name], cwd=str(path.parent),
                           check=False, capture_output=True)
        except OSError as exc:  # pragma: no cover — git yoksa yazma yine de yapıldı
            print("UYARI: git add başarısız (%s)" % exc)
    return True


def names_check(readme_text=None, available=None):
    """Yalnız ad kümesi denetimi (tablo üretmez) — geriye uyumlu sözleşme.

    `check_skills_index.py` bu yüzeyi korur: veri-temelli birim testleri
    frontmatter'sız kümeler üzerine yazıldı.
    """
    text = readme_text if readme_text is not None else _read(None)
    expected = set(available) if available is not None else skill_names()
    listed = readme_skill_names(text)
    missing = sorted(expected - listed)
    stale = sorted(listed - expected)
    if missing or stale:
        print("FAIL: README skills index drift")
        if missing:
            print("  missing:", ", ".join(missing))
        if stale:
            print("  stale:", ", ".join(stale))
        return 1
    print("PASS: README skills index synced (%d skills)" % len(expected))
    return 0


def _read(readme_path=None):
    path = pathlib.Path(readme_path) if readme_path else README
    return path.read_text(encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="README skills index yazarı + fail-closed drift kapısı")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="drift varsa exit 1 (varsayılan)")
    mode.add_argument("--update", action="store_true",
                      help="tabloyu üret + git add")
    mode.add_argument("--verify", action="store_true",
                      help="--update sonrası --check (yakınsamazsa exit 1)")
    mode.add_argument("--list", action="store_true", help="skill adlarını bas")
    ap.add_argument("--skills", default=None, help="skills dizini (varsayılan: skills/)")
    ap.add_argument("--readme", default=None, help="README yolu (varsayılan: README.md)")
    ap.add_argument("--no-stage", action="store_true", help="git add yapma")
    args = ap.parse_args(argv)

    if args.list:
        try:
            for skill in load_skills(args.skills):
                print(skill.name)
        except SkillError as exc:
            print("HATA: %s" % exc, file=sys.stderr)
            return 1
        return 0

    if args.update:
        try:
            update(skills_dir=args.skills, readme_path=args.readme,
                   stage=not args.no_stage)
        except SkillError as exc:
            print("HATA: %s" % exc, file=sys.stderr)
            print("  remedy: SKILL.md frontmatter'ını düzelt", file=sys.stderr)
            return 1
        return 0

    if args.verify:
        try:
            update(skills_dir=args.skills, readme_path=args.readme,
                   stage=not args.no_stage)
        except SkillError as exc:
            print("HATA: %s" % exc, file=sys.stderr)
            print("  remedy: SKILL.md frontmatter'ını düzelt", file=sys.stderr)
            return 1
        return check(skills_dir=args.skills, readme_path=args.readme)

    return check(skills_dir=args.skills, readme_path=args.readme)


if __name__ == "__main__":
    sys.exit(main())