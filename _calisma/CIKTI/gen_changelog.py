#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_changelog.py — git log'dan changelog tablosu üret + docs ile senkronize et.

Conventional-commit mesajlarını ayrıştırır (feat/fix/ci/docs/refs/publish/history/
teslim/ispat/test/chore/refactor/perf), her commit için tablo satırı üretir ve
README.md ile docs/PUBLISH_SCENARIO.md'deki changelog bölümlerini günceller.

Modlar:
  --update   mevcut tabloyu yeni commit'lerle genişletir (kaymış satır yoksa)
  --check    docs'taki tablo ↔ git log arasındaki kaymayı raporlar (exit 1 = drift)
  --print    tabloyu stdout'a basar (dosyaya yazmaz)
  --link     tablodaki commit hash'lerini GitHub commit URL'lerine bağlar
             (in-place; satırlar [`hash`](URL) formuna çevrilir, idempotent)

--link / --update URL üssü:
  Base URL varsayılan olarak `git remote get-url origin`'den türetilir
  (github.com formatları: git@github.com:owner/repo, https://..., ssh://...);
  --base-url ile elle verilebilir. --update, tablo zaten bağlıysa YENİ
  satırları da bağlı üretir (karışık format olmaz).

Filtreleme:
  --tag-regex REGEX   yalnızca kategori'si regex'e uyan commit'leri işler
                      (case-insensitive). feat/fix/refs gibi yalnızca belirli
                      kategorileri changelog'a almak için: --tag-regex 'feat|fix|refs'
                      Stale tespiti filtreden ETKİLENMEZ (tablodaki diğer
                      kategoriler yanlışlıkla stale raporlanmaz); yalnızca
                      eksik-commit tespiti ve --print filtreye tabidir.

Mantık:
  - Mevcut tablolardaki commit hash'leri korunur (insan özeti taşıyan satırlar)
  - git log'da olup tabloda olmayan commit'ler (descending) tabloya eklenir
  - tabloda olup git log'da olmayan hash'ler "STALE" olarak işaretlenir
  - İnsan tarafından yazılmış özetler korunur; otomatik üretim yalnızca yeni
    commit'ler için conventional-commit mesajından türetilir

Kullanım:
  python3 _calisma/CIKTI/gen_changelog.py --update
  python3 _calisma/CIKTI/gen_changelog.py --check
  python3 _calisma/CIKTI/gen_changelog.py --print
  python3 _calisma/CIKTI/gen_changelog.py --print --limit 10
  python3 _calisma/CIKTI/gen_changelog.py --print --tag-regex 'feat|fix|refs'
  python3 _calisma/CIKTI/gen_changelog.py --update --tag-regex 'feat|fix|refs'
  python3 _calisma/CIKTI/gen_changelog.py --link
  python3 _calisma/CIKTI/gen_changelog.py --link --base-url https://github.com/owner/repo
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# ─── conventional-commit ayrıştırma ────────────────────────────────────

# type(scope): description  →  type, scope, description
_CC_RE = re.compile(
    r"^(?P<type>feat|fix|ci|docs|refs|publish|history|teslim|ispat|test|chore|refactor|perf|build|style)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r":\s*(?P<desc>.+)$",
    re.IGNORECASE,
)

# Non-conventional ama bilinen prefix'ler (V5h:, Add ..., Basic ...)
_PREFIX_RE = re.compile(
    r"^(?P<type>V\d+\w+|Add|Basic|Setup|Basi)\b[:\s]*(?P<desc>.+)$",
    re.IGNORECASE,
)

# Türkçe kategori eşlemesi
CATEGORY_MAP = {
    "feat": "feat",
    "fix": "fix",
    "ci": "ci",
    "docs": "docs",
    "refs": "refs",
    "publish": "publish",
    "history": "history",
    "teslim": "teslim",
    "ispat": "ispat",
    "test": "test",
    "chore": "chore",
    "refactor": "refactor",
    "perf": "perf",
    "build": "build",
    "style": "style",
    "V": "teslim",  # V5h: prefixed commits
    "add": "feat",
    "basic": "chore",
    "setup": "chore",
}


class CommitInfo(NamedTuple):
    short_hash: str
    full_hash: str
    date: str  # YYYY-MM-DD
    subject: str
    category: str
    description: str


def _run_git(args: list[str]) -> str:
    """git komutunu çalıştır, çıktıyı döndür."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_commit(subject: str) -> tuple[str, str]:
    """Conventional-commit mesajını ayrıştır → (category, description)."""
    m = _CC_RE.match(subject)
    if m:
        raw_type = m.group("type").lower()
        category = CATEGORY_MAP.get(raw_type, raw_type)
        desc = m.group("desc").strip()
        # scope'u açıklamaya ekle (varsa)
        scope = m.group("scope")
        if scope:
            desc = f"({scope}) {desc}"
        return category, desc

    m2 = _PREFIX_RE.match(subject)
    if m2:
        raw_type = m2.group("type").split()[0].lower()  # "V5h:" → "v5h"
        # V5h → "teslim", Add → "feat", Basic → "chore"
        if raw_type.upper().startswith("V"):
            return "teslim", m2.group("desc").strip()
        category = CATEGORY_MAP.get(raw_type, "chore")
        return category, m2.group("desc").strip()

    # fallback: bütün subject'i açıklama olarak kullan, kategori "other"
    return "other", subject


def filter_commits(commits: list[CommitInfo], pattern: str | None) -> list[CommitInfo]:
    """Kategori'si regex'e uyan commit'leri döndür (case-insensitive).

    pattern None/boş → tüm commit'ler (filtre yok). Geçersiz regex → ValueError.
    """
    if not pattern:
        return list(commits)
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"geçersiz --tag-regex '{pattern}': {e}") from e
    return [ci for ci in commits if rx.search(ci.category)]


# GitHub remote URL formatları: git@github.com:o/r.git | https://github.com/o/r(.git) | ssh://git@github.com/o/r
_REMOTE_RE = re.compile(r"(?:github\.com[/:])([^/:]+)/([^/\s]+?)(?:\.git)?$")


def parse_remote_url(url: str) -> str | None:
    """Git remote URL'sinden GitHub base URL türet (https://github.com/owner/repo).

    github.com dışı bir remote (gitlab vb.) → None (bağlanamaz).
    """
    m = _REMOTE_RE.search(url)
    if not m:
        return None
    return f"https://github.com/{m.group(1)}/{m.group(2)}"


def derive_base_url() -> str | None:
    """origin remote'undan GitHub base URL türet; remote yoksa None."""
    try:
        url = _run_git(["remote", "get-url", "origin"])
    except subprocess.CalledProcessError:
        return None
    return parse_remote_url(url)


def link_cell(hash_: str, base_url: str) -> str:
    """Commit hücresi: bağlı form [`hash`](base/commit/hash)."""
    return f"[`{hash_}`]({base_url}/commit/{hash_})"


def rows_linked(content: str, row_re: re.Pattern, section_header: str) -> bool:
    """Tablodaki satırlardan EN AZ biri bağlı formdaysa True (format uyumu)."""
    lines = content.splitlines()
    in_table = False
    for line in lines:
        if section_header in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("#"):
                break
            if row_re.match(line) and "](" in line:
                return True
    return False


def link_file_changelog(
    filepath: Path,
    section_header: str,
    row_re: re.Pattern,
    base_url: str,
    cat_group: str,
) -> tuple[int, int]:
    """Tablodaki commit hash'lerini GitHub commit URL'lerine bağla (in-place).

    Yalnızca row_re ile eşleşen satırlar yeniden yazılır; eşleşmeyenler
    (başlık, ayraç, regresyon satırları vb.) aynen korunur. Zaten bağlı
    satırlar aynı formda üretildiği için değişmez (idempotent).

    Returns: (converted, total) — converted: bu çağrıda değişen satır sayısı.
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()
    in_table = False
    converted = 0
    total = 0
    for i, line in enumerate(lines):
        if section_header in line:
            in_table = True
            continue
        if in_table and line.strip().startswith("#"):
            in_table = False
        if in_table:
            m = row_re.match(line)
            if m:
                total += 1
                cat = m.group(cat_group)
                desc = m.group("desc")
                h = m.group("hash")
                new = (f"| {m.group('date')} | {cat} | {desc} | "
                       f"{link_cell(h, base_url)} |")
                if new != line.strip():
                    converted += 1
                    lines[i] = new
    if converted:
        filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return converted, total


def get_git_log(limit: int | None = None) -> list[CommitInfo]:
    """git log'dan commit listesi al (yeniden eskiye)."""
    fmt = "%H|%h|%aI|%s"
    args = ["log", "--no-merges", f"--format={fmt}"]
    if limit:
        args.append(f"-{limit}")
    raw = _run_git(args)
    if not raw:
        return []

    commits = []
    for line in raw.splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        full_hash, short_hash, iso_date, subject = parts
        date = iso_date[:10]  # YYYY-MM-DD
        category, description = parse_commit(subject)
        commits.append(CommitInfo(short_hash, full_hash, date, subject, category, description))
    return commits


# ─── tablo ayrıştırma/üretme ───────────────────────────────────────────

# README tablo satırı: | Tarih | Kategori | Değişiklik | Commit |
# Commit hücresi bağlı ([`hash`](URL)) veya bağsız (`hash`) olabilir — --link
# tabloyu bağlı forma çevirir, --check/--update her ikisini de okur.
_README_ROW_RE = re.compile(
    r"^\|\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<cat>[^|]+?)\s*\|\s*(?P<desc>[^|]+?)\s*\|\s*(?:\[)?`(?P<hash>[0-9a-f]{7,40})`(?:\]\([^)]*\))?\s*\|$"
)

# PUBLISH_SCENARIO tablo satırı: | Tarih | Bölüm | Değişiklik | Commit |
_PUB_ROW_RE = re.compile(
    r"^\|\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<section>[^|]+?)\s*\|\s*(?P<desc>[^|]+?)\s*\|\s*(?:\[)?`(?P<hash>[0-9a-f]{7,40})`(?:\]\([^)]*\))?\s*\|$"
)

# Regresyon satırı (README): | ID | Tarih | ... | Commit |
_REG_ROW_RE = re.compile(
    r"^\|\s*[Rr]\d+\s*\|"
)


def parse_existing_table(content: str, start_marker: str, end_marker: str,
                         row_re: re.Pattern) -> tuple[list[dict], list[str]]:
    """Belgedeki changelog tablosunu ayrıştır.

    Returns:
        (rows, stale_hashes) — rows: hash→satır bilgisi; stale_hashes: tablo
        sonu işaretçisine kadar olan satırlar (regresyon tablosu vb.)
    """
    lines = content.splitlines()
    in_table = False
    rows: list[dict] = []
    table_lines: list[str] = []
    for line in lines:
        if start_marker in line:
            in_table = True
            continue
        if in_table and end_marker in line:
            break
        if in_table:
            m = row_re.match(line)
            if m:
                rows.append(m.groupdict())
            elif line.strip().startswith("|"):
                table_lines.append(line)
    return rows, table_lines


def _find_section_range(content: str, section_header: str) -> tuple[int, int] | None:
    """Markdown belgede bir başlığın satır aralığını bul (başlık satırı dahil değil).

    Returns: (start_line, end_line) — 1-indexed; end = sonraki ## başlığı veya EOF.
    """
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(section_header):
            start = i
            break
    if start is None:
        return None

    # Sonraki ## veya ### başlığını bul (aynı seviye veya üst)
    header_level = len(section_header.rstrip("#"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i].strip()
        if line.startswith("#" * header_level + " ") or line.startswith("#" * (header_level - 1) + " "):
            end = i
            break
    return start, end


def extract_hashes_from_table(content: str, row_re: re.Pattern, section_header: str) -> set[str]:
    """Belgedeki changelog tablosundan tüm commit hash'lerini çıkar."""
    lines = content.splitlines()
    in_table = False
    hashes: set[str] = set()
    for line in lines:
        if section_header in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("#"):
                break
            m = row_re.match(line)
            if m:
                hashes.add(m.group("hash")[:7])
    return hashes


# ─── yeni satır üretme ─────────────────────────────────────────────────

def format_readme_row(ci: CommitInfo, base_url: str | None = None) -> str:
    """README changelog tablosu için satır üret (base_url verilirse bağlı)."""
    desc = ci.description
    # uzun açıklamaları kısalt
    if len(desc) > 80:
        desc = desc[:77] + "..."
    cell = link_cell(ci.short_hash, base_url) if base_url else f"`{ci.short_hash}`"
    return f"| {ci.date} | {ci.category} | {desc} | {cell} |"


def format_pub_row(ci: CommitInfo, base_url: str | None = None) -> str:
    """PUBLISH_SCENARIO changelog tablosu için satır üret (base_url verilirse bağlı)."""
    desc = ci.description
    if len(desc) > 80:
        desc = desc[:77] + "..."
    section = ci.category  # PUBLISH_SCENARIO'da "Bölüm" sütunu = kategori
    cell = link_cell(ci.short_hash, base_url) if base_url else f"`{ci.short_hash}`"
    return f"| {ci.date} | {section} | {desc} | {cell} |"


# ─── ana mantık ────────────────────────────────────────────────────────

def find_missing_commits(
    git_commits: list[CommitInfo],
    existing_hashes: set[str],
) -> list[CommitInfo]:
    """git log'da olup tabloda olmayan YENİ commit'leri bul (yeniden eskiye).

    Seçilmiş changelog tabloları her commit'i listelemez — yalnızca büyük
    kilometre taşları. Bu yüzden yalnızca tablodaki en yeni tarihten SONRA
    gelen commit'leri ekler; geçmişteki eksik commit'leri (bilinçli olarak
    seçilmemiş) drift olarak raporlamaz.
    """
    if not existing_hashes:
        # Tablo boş → tüm commit'ler "yeni" (ama yine de limit'e saygılı)
        return list(git_commits)

    # Tablodaki en yeni commit'in tarihini bul
    # git_commits descending (yeni→eski), existing_hashes içindeki ilk eşleşmeyi bul
    newest_idx = None
    for i, ci in enumerate(git_commits):
        if ci.short_hash[:7] in existing_hashes:
            newest_idx = i
            break

    if newest_idx is None:
        # Tablodaki hiçbir hash git log'da yok (rebase olmuş olabilir)
        # → güvenli mod: hiçbir şey ekleme, stale olarak raporla
        return []

    # newest_idx'den ÖNCEki commit'ler = tablodaki en yeni commit'ten daha yeni
    return git_commits[:newest_idx]


def find_stale_hashes(
    git_commits: list[CommitInfo],
    existing_hashes: set[str],
) -> set[str]:
    """tabloda olup git log'da olmayan hash'leri bul (silinmiş/rebased)."""
    git_hashes = {ci.short_hash[:7] for ci in git_commits}
    return existing_hashes - git_hashes


def update_file_changelog(
    filepath: Path,
    section_header: str,
    row_re: re.Pattern,
    format_fn,
    git_commits: list[CommitInfo],
    next_section_header: str | None = None,
    all_commits: list[CommitInfo] | None = None,
    base_url: str | None = None,
) -> tuple[list[str], list[str]]:
    """Dosyadaki changelog tablosunu güncelle.

    Mevcut satırları korur; git log'dan yeni commit'ler ekler.
    Stale hash'leri raporlar ama silmez.

    Returns: (added_hashes, stale_hashes)
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Section range
    range_ = _find_section_range(content, section_header)
    if range_ is None:
        print(f"  SKIP: {section_header} bulunamadı ({filepath.name})")
        return [], []

    start, end = range_

    # Mevcut hash'leri çıkar
    existing_hashes = extract_hashes_from_table(content, row_re, section_header)

    # Eksik commit'leri bul (git_commits filtreli olabilir — --tag-regex)
    missing = find_missing_commits(git_commits, existing_hashes)
    # Stale tespiti FİLTRELENMEMIŞ tam listeyle yapılır: tablodaki diğer
    # kategoriler (--tag-regex kapsamı dışı) yanlışlıkla stale raporlanmaz
    stale = find_stale_hashes(all_commits or git_commits, existing_hashes)

    # Tablo satırlarını bul (start+1..end arası, satır sonu ile)
    # Mevcut tabloyu koru, yeni satırları ekle
    # Tabloyu bul: başlıktan sonraki ilk |---| satırından son | satırına kadar
    table_start = None
    table_end = None
    for i in range(start + 1, end):
        if lines[i].strip().startswith("|") and "---" in lines[i]:
            table_start = i + 1
            break
    if table_start is None:
        # | ile başlayan ilk satır
        for i in range(start + 1, end):
            if lines[i].strip().startswith("|"):
                table_start = i
                break

    # Tablo sonu: son | satırı
    if table_start is not None:
        table_end = table_start
        for i in range(table_start, end):
            if lines[i].strip().startswith("|"):
                table_end = i
            elif lines[i].strip() == "":
                break

    if table_start is None or table_end is None:
        print(f"  SKIP: tablo bulunamadı ({filepath.name})")
        return [], []

    # Yeni satırları üret (yeniden eskiye sıralı — git log zaten descending).
    # Tablo bağlıysa ve base_url varsa yeni satırlar da bağlı üretilir
    # (karışık format olmaz).
    linked = rows_linked(content, row_re, section_header) if base_url else False
    new_rows = [format_fn(ci, base_url if linked else None) for ci in missing]

    if not new_rows:
        return [], list(stale)

    # Yeni satırları tablo sonuna ekle (mevcut satırlardan sonra)
    updated_lines = lines[:table_end + 1] + new_rows + lines[table_end + 1:]
    filepath.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    added = [ci.short_hash for ci in missing]
    return added, list(stale)


def check_file_changelog(
    filepath: Path,
    section_header: str,
    row_re: re.Pattern,
    git_commits: list[CommitInfo],
    all_commits: list[CommitInfo] | None = None,
) -> tuple[list[str], list[str]]:
    """Dosyadaki changelog ile git log arasındaki drift'i raporla."""
    content = filepath.read_text(encoding="utf-8")
    existing_hashes = extract_hashes_from_table(content, row_re, section_header)
    # git_commits filtreli (--tag-regex) olabilir; stale her zaman tam listeden
    missing = find_missing_commits(git_commits, existing_hashes)
    stale = find_stale_hashes(all_commits or git_commits, existing_hashes)
    return [ci.short_hash for ci in missing], list(stale)


def print_table(git_commits: list[CommitInfo], format_fn, limit: int | None = None):
    """Tabloyu stdout'a bas."""
    commits = git_commits if limit is None else git_commits[:limit]
    print("| Tarih | Kategori | Değişiklik | Commit |")
    print("|---|---|---|---|")
    for ci in commits:
        print(format_fn(ci))


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Git log'dan changelog tablosu üret + docs ile senkronize et",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--update", action="store_true",
                      help="README.md ve PUBLISH_SCENARIO.md'deki changelog tablolarını güncelle")
    mode.add_argument("--check", action="store_true",
                      help="docs ↔ git log arasındaki drift'i raporla (exit 1 = drift)")
    mode.add_argument("--print", action="store_true",
                      help="Tabloyu stdout'a bas (dosyaya yazmaz)")
    mode.add_argument("--link", action="store_true",
                      help="Tablodaki commit hash'lerini GitHub commit URL'lerine "
                           "bağla (in-place + stdout; git log gerekmez)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Son N commit (varsayılan: tümü)")
    ap.add_argument("--base-url", default=None,
                    help="GitHub repo base URL (örn. https://github.com/owner/repo). "
                         "Varsayılan: git remote get-url origin'den türetilir")
    ap.add_argument("--tag-regex", default=None,
                    help="Yalnızca kategori'si regex'e uyan commit'leri işle "
                         "(case-insensitive; örn. 'feat|fix|refs'). Stale tespiti "
                         "filtreden etkilenmez.")
    ap.add_argument("--readme", default="README.md",
                    help="README dosya yolu (varsayılan: README.md)")
    ap.add_argument("--publish", default="docs/PUBLISH_SCENARIO.md",
                    help="PUBLISH_SCENARIO dosya yolu")
    args = ap.parse_args()

    readme_path = Path(args.readme)
    pub_path = Path(args.publish)

    if args.link:
        # --link: git log GEREKMEZ — mevcut tablo satırlarını bağlı forma çevir.
        base = (args.base_url or derive_base_url() or "").rstrip("/")
        if not base:
            print("HATA: GitHub base URL türetilemedi — --base-url verin "
                  "(git remote get-url origin yok veya github.com değil)",
                  file=sys.stderr)
            sys.exit(2)
        for path, header, row_re, cat_group in [
            (readme_path, "## Değişiklik Geçmişi", _README_ROW_RE, "cat"),
            (pub_path, "## Değişiklik Geçmişi", _PUB_ROW_RE, "section"),
        ]:
            if not path.exists():
                print(f"HATA: {path} bulunamadı", file=sys.stderr)
                sys.exit(2)
            converted, total = link_file_changelog(
                path, header, row_re, base, cat_group)
            print(f"{path.name}: {converted}/{total} satır bağlandı → {base}")
            if converted:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if row_re.match(line) and "](" in line:
                        print(f"  + {line.strip()}")
        return

    # git log al
    git_commits = get_git_log(args.limit)
    if not git_commits:
        print("HATA: git log boş", file=sys.stderr)
        sys.exit(2)

    # Kategori filtresi (yalnızca eksik-commit tespiti ve --print için;
    # stale tespiti tam listeden yapılır)
    try:
        filtered = filter_commits(git_commits, args.tag_regex)
    except ValueError as e:
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(2)

    if args.print:
        print_table(filtered, format_readme_row, args.limit)
        return

    if not readme_path.exists():
        print(f"HATA: {readme_path} bulunamadı", file=sys.stderr)
        sys.exit(2)
    if not pub_path.exists():
        print(f"HATA: {pub_path} bulunamadı", file=sys.stderr)
        sys.exit(2)

    if args.check:
        # Drift kontrolü — missing filtreliden (--tag-regex), stale tam listeden
        readme_missing, readme_stale = check_file_changelog(
            readme_path, "## Değişiklik Geçmişi", _README_ROW_RE, filtered,
            all_commits=git_commits)
        pub_missing, pub_stale = check_file_changelog(
            pub_path, "## Değişiklik Geçmişi", _PUB_ROW_RE, filtered,
            all_commits=git_commits)

        drift = False

        if readme_missing:
            print(f"README.md: {len(readme_missing)} commit tabloda yok:")
            for h in readme_missing[:10]:
                print(f"  + {h}")
            if len(readme_missing) > 10:
                print(f"  ... ve {len(readme_missing) - 10} daha")
            drift = True

        if readme_stale:
            print(f"README.md: {len(readme_stale)} stale hash (git log'da yok):")
            for h in sorted(readme_stale)[:10]:
                print(f"  - {h}")
            if len(readme_stale) > 10:
                print(f"  ... ve {len(readme_stale) - 10} daha")
            drift = True

        if pub_missing:
            print(f"PUBLISH_SCENARIO.md: {len(pub_missing)} commit tabloda yok:")
            for h in pub_missing[:10]:
                print(f"  + {h}")
            if len(pub_missing) > 10:
                print(f"  ... ve {len(pub_missing) - 10} daha")
            drift = True

        if pub_stale:
            print(f"PUBLISH_SCENARIO.md: {len(pub_stale)} stale hash (git log'da yok):")
            for h in sorted(pub_stale)[:10]:
                print(f"  - {h}")
            if len(pub_stale) > 10:
                print(f"  ... ve {len(pub_stale) - 10} daha")
            drift = True

        if drift:
            print("\nDRIFT tespit edildi. Düzeltmek için: python3 _calisma/CIKTI/gen_changelog.py --update")
            sys.exit(1)
        else:
            print("TÜMÜ PASS: changelog tabloları git log ile senkron")
            sys.exit(0)

    if args.update:
        print("=== Changelog senkronizasyonu ===\n")

        base = (args.base_url or derive_base_url() or "").rstrip("/") or None
        # README.md
        print("README.md:")
        r_added, r_stale = update_file_changelog(
            readme_path, "## Değişiklik Geçmişi", _README_ROW_RE,
            format_readme_row, filtered, all_commits=git_commits,
            base_url=base)
        if r_added:
            print(f"  + {len(r_added)} yeni satır eklendi:")
            for h in r_added:
                print(f"    + {h}")
        else:
            print("  (yeni commit yok)")
        if r_stale:
            print(f"  ⚠ {len(r_stale)} stale hash (silinmedi — manuel kontrol gerek):")
            for h in r_stale:
                print(f"    ? {h}")

        # PUBLISH_SCENARIO.md
        print("\ndocs/PUBLISH_SCENARIO.md:")
        p_added, p_stale = update_file_changelog(
            pub_path, "## Değişiklik Geçmişi", _PUB_ROW_RE,
            format_pub_row, filtered, all_commits=git_commits,
            base_url=base)
        if p_added:
            print(f"  + {len(p_added)} yeni satır eklendi:")
            for h in p_added:
                print(f"    + {h}")
        else:
            print("  (yeni commit yok)")
        if p_stale:
            print(f"  ⚠ {len(p_stale)} stale hash (silinmedi — manuel kontrol gerek):")
            for h in p_stale:
                print(f"    ? {h}")

        print("\nTamam.")


if __name__ == "__main__":
    main()
