#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deploy_evidence.py — kanıt-defteri (docs/DEPLOY_EVIDENCE.md) bayatlık kapısı.

Kanıt-defteri, origin/main'in her temiz HEAD'i icin dort workflow kosumunu
(run id + conclusion) kaydeder. Defter elle yazilir; bu kapi onun TAZELIGINI
fail-closed dogrular:

  1) YAPI — tablo basligi beklenen sutunlari tasir, her satir 6 hucrelidir,
     tarih ISO, HEAD kisa-hex, dort kosum hucresi de `<conclusion> #<run_id>`
     biciminde; satirlar tarih bakiminda karsiartmaz.
  2) HEAD KAPSAMI — en yeni satirin HEAD'i origin/main'in atasi (ya da kendisi)
     ve ona en fazla `--max-head-gap` commit uzakta. Defter lag-one tasarimli
     (head'in kosumlari bitmeden kaydi yazilamaz; bir sonraki commit'te yazilir)
     — bu yuzden "0 uzaklik" degil "kucuk uzaklik" beklenir. Buyuk uzaklik =
     kanitsiz ilerlemis main = bayat kanit.
  3) YAS — en yeni satirin tarihi `--max-age-days` gunden eski degil
     (varsayilan 21 gun: haftalik cron + iki haftalik tolerans) ve gelecek
     tarihli olamaz.
  4) KOSUM GERCEKLERI — en yeni `--verify-rows` satirdaki run id'ler GitHub'da
     bulunur VE hucrede yazan conclusion ile gercek conclusion birebir aynidir.
     ESKI satirlar canliya sorulmaz (Actions log/metadatasinin saklama suresi
     gecmiste yanlis kirmizi uretirdi) — onlara yalniz yapi denetimi uygulanir.
     Kosumun head_sha'si HEAD ile esitlenmez: determinism-trend satirlari o
     an guncel olan OLCEK olcum kosumunu da yazabilir.

Kullanim:
  python3 _calisma/CIKTI/deploy_evidence.py --check           # kapi (fail-closed)
  python3 _calisma/CIKTI/deploy_evidence.py --print           # satirlari dok
  python3 _calisma/CIKTI/deploy_evidence.py --check --no-network

Cikis kodlari:
  0 — defter taze ve tutarli
  1 — BAYAT KANIT (yapi / HEAD kapsami / yas / kosum sonucu sapmasi)
  2 — calisma hatasi (defter yok, git veya gh yok)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_LEDGER = REPO_ROOT / "docs" / "DEPLOY_EVIDENCE.md"

EXPECTED_HEADER = ("Tarih", "HEAD (origin/main)", "verify-delivery",
                   "docker-security", "test-smoke", "determinism-trend")
RUN_CELL = re.compile(r"^\[(?P<label>[a-z_]+)\s+#(?P<run>\d+)\](\([^)]*\))?$")
HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KNOWN_CONCLUSIONS = ("success", "failure", "cancelled", "skipped",
                     "timed_out", "neutral", "action_required", "stale")

DEFAULT_MAX_HEAD_GAP = 3
DEFAULT_MAX_AGE_DAYS = 21
DEFAULT_VERIFY_ROWS = 2


@dataclass(frozen=True)
class Row:
    """Defter tablosunun tek satiri."""
    date: str
    head: str
    runs: tuple = ()          # ((conclusion, run_id), ...)


@dataclass
class Env:
    """Dis dunya erisimi — testler sahte (fake) nesnelerle degistirir."""
    git: object = None        # (args: list[str]) -> str
    fetch_run: object = None  # (run_id: str) -> dict | None
    today: dt.date = None
    repo: str = ""


# --------------------------------------------------------------------------
# Git yardimcilari (varsayilan uygulamalar)
# --------------------------------------------------------------------------
def git_runner(root: Path):
    def _git(args):
        proc = subprocess.run(["git", "-C", str(root)] + list(args),
                              capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()
    return _git


def gh_run_fetcher(repo: str):
    """GitHub Actions run bilgisi (conclusion dahil) getirici."""
    def _fetch(run_id: str):
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/runs/{run_id}"],
            capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
    return _fetch


def detect_repo(root: Path, git) -> str:
    """origin remote URL'sinden owner/repo cikar (dosya yolu degil URL olabilir)."""
    url = git(["remote", "get-url", "origin"]) or ""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$", url.strip())
    if not m:
        return ""
    return f"{m.group(1)}/{m.group(2)}"


# --------------------------------------------------------------------------
# Ayristirma + yapi denetimi
# --------------------------------------------------------------------------
def table_cells(text: str):
    """Markdown tablosunun baslik + veri hucrelerini dondurur.

    Satirlar GERCEK markdown satir numarasiyla birlikte gelir — ihlal
    mesajlari dosya satirini gosterir (farkli dosyada da, test fixture'da
    da ayni sozlesme).
    """
    header, rows = None, []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and all(set(c) <= set("-: ") and c for c in cells):
            continue  # ayirici satir
        if header is None:
            header = cells
            continue
        rows.append((lineno, cells))
    return header, rows


def parse_rows(text: str):
    """(satirlar, ihlaller) — yapısal olarak bozuk satırlar ıhlal listesine girer."""
    header, raw = table_cells(text)
    violations = []
    rows = []
    if header is None:
        return rows, ["tablo basligi bulunamadi (markdown tablosu yok)"]
    if tuple(header) != EXPECTED_HEADER:
        violations.append("baslik beklenenden farkli: %s" % " | ".join(header))
    prev_date = None
    for index, cells in raw:
        if len(cells) != len(EXPECTED_HEADER):
            violations.append("satir %d: %d hucre (beklenen %d)"
                              % (index, len(cells), len(EXPECTED_HEADER)))
            continue
        date, head = cells[0], cells[1]
        if not DATE_RE.match(date):
            violations.append("satir %d: tarih ISO degil: %r" % (index, date))
            continue
        if not HEAD_RE.match(head):
            violations.append("satir %d: HEAD kisa-hex degil: %r" % (index, head))
            continue
        parsed = []
        cell_bad = False
        for cell in cells[2:]:
            m = RUN_CELL.match(cell)
            if not m:
                violations.append("satir %d: kosum hucresi bicimi yanlis: %r"
                                  % (index, cell))
                cell_bad = True
                continue
            label = m.group("label")
            if label not in KNOWN_CONCLUSIONS:
                violations.append("satir %d: bilinmeyen conclusion: %r" % (index, label))
                cell_bad = True
                continue
            parsed.append((label, m.group("run")))
        if cell_bad:
            continue
        iso = dt.date.fromisoformat(date)
        if prev_date is not None and iso < prev_date:
            violations.append("satir %d: tarih geriye gidiyor (%s < %s)"
                              % (index, date, prev_date.isoformat()))
            continue
        prev_date = iso
        rows.append(Row(date=date, head=head, runs=tuple(parsed)))
    seen = {}
    for row in rows:
        if row.head in seen:
            violations.append("HEAD %s birden fazla satirda geciyor (%s ve %s)"
                              % (row.head, seen[row.head], row.date))
        seen[row.head] = row.date
    return rows, violations


# --------------------------------------------------------------------------
# Freshness denetimleri
# --------------------------------------------------------------------------
def check_head_coverage(rows, git, max_gap: int):
    """En yeni satir origin/main'i kapsiyor mu? (lag-one toleransi icinde)"""
    if not rows:
        return ["defterde satir yok — HEAD kapsami dogrulanamaz"]
    violations = []
    newest = rows[-1]
    for ref in ("origin/main", "main"):
        main_sha = git(["rev-parse", ref])
        if main_sha:
            break
    else:
        return ["origin/main cozulemedi (git rev-parse basarisiz)"]
    if git(["merge-base", "--is-ancestor", newest.head, main_sha]) is None:
        return ["en yeni satirin HEAD'i %s degil: %s main soyunda degil"
                % (newest.head, main_sha[:7])]
    gap_raw = git(["rev-list", "--count", "%s..%s" % (newest.head, main_sha)])
    try:
        gap = int(gap_raw) if gap_raw is not None else 0
    except ValueError:
        gap = 0
    if gap > max_gap:
        violations.append(
            "en yeni satir %s, main %s'ten %d commit ileride (tolerans %d) — "
            "kanit guncel degil" % (newest.head, main_sha[:7], gap, max_gap))
    return violations


def check_age(rows, today: dt.date, max_age_days: int):
    if not rows:
        return ["defterde satir yok — yas denetimi yapilamaz"]
    newest = rows[-1]
    violations = []
    try:
        row_date = dt.date.fromisoformat(newest.date)
    except ValueError:
        return ["en yeni satirin tarihi cozulemedi: %r" % newest.date]
    age = (today - row_date).days
    if age < 0:
        violations.append("en yeni satir gelecek tarihli: %s (bugun %s)"
                          % (newest.date, today.isoformat()))
    elif age > max_age_days:
        violations.append("en yeni satir %d gun eski (sinir %d gun) — bayat kanit"
                          % (age, max_age_days))
    return violations


def check_runs(rows, fetch, verify_rows: int):
    """En yeni `verify_rows` satirin kosum sonuclari canli ile eslesmeli."""
    violations = []
    for row in rows[-verify_rows:] if verify_rows > 0 else []:
        for label, run_id in row.runs:
            data = fetch(run_id)
            if data is None:
                violations.append("kosum #%s bulunamadi (satir %s) — kayit bayat"
                                  % (run_id, row.date))
                continue
            actual = data.get("conclusion")
            if actual != label:
                violations.append(
                    "kosum #%s sapmasi: defter '%s', canli %r (satir %s)"
                    % (run_id, label, actual, row.date))
    return violations


# --------------------------------------------------------------------------
# Giris noktasi
# --------------------------------------------------------------------------
def run_checks(ledger: Path, env: Env, max_gap: int, max_age: int,
                verify_rows: int, network: bool):
    if not ledger.is_file():
        # Hata (exit 2) — bayat kanit (exit 1) degil: dosya yoksa kapinin
        # konusu (tazelik) olcumlenemez, bu ayrica bir ihlal sayilmaz.
        raise FileNotFoundError(str(ledger))
    rows, violations = parse_rows(ledger.read_text(encoding="utf-8"))
    git = env.git
    if git is not None:
        violations += check_head_coverage(rows, git, max_gap)
        violations += check_age(rows, env.today, max_age)
    if network and env.fetch_run is not None:
        violations += check_runs(rows, env.fetch_run, verify_rows)
    return rows, violations


def build_parser():
    p = argparse.ArgumentParser(description="kanit-defteri bayatlık kapısı")
    p.add_argument("--check", action="store_true",
                   help="kapıyı çalıştır (varsayılan davranış)")
    p.add_argument("--print", dest="dump", action="store_true",
                   help="satırları TSV olarak döker ve çıkar")
    p.add_argument("--no-network", action="store_true",
                   help="canlı koşum doğrulamasını atlar (offline)")
    p.add_argument("--max-head-gap", type=int, default=DEFAULT_MAX_HEAD_GAP)
    p.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    p.add_argument("--verify-rows", type=int, default=DEFAULT_VERIFY_ROWS,
                   help="canlıya sorulan en yeni satır sayısı (0 = hiç)")
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    p.add_argument("--repo", default="", help="owner/repo (gh için)")
    p.add_argument("--json", dest="as_json", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    network = not args.no_network
    if network and not shutil.which("gh"):
        print("hata: gh bulunamadi (canli kosum dogrulamasi icin gerekli; "
              "--no-network ile atlanabilir)", file=sys.stderr)
        return 2
    root = REPO_ROOT
    git = git_runner(root)
    today = dt.datetime.now(dt.timezone.utc).date()
    repo = args.repo or detect_repo(root, git)
    if network and not repo:
        print("hata: owner/repo cozulemedi (--repo verin)", file=sys.stderr)
        return 2
    env = Env(git=git, fetch_run=gh_run_fetcher(repo) if network else None,
              today=today, repo=repo)
    try:
        rows, violations = run_checks(args.ledger, env, args.max_head_gap,
                                      args.max_age_days, args.verify_rows,
                                      network)
    except FileNotFoundError as exc:
        print("hata: kanit-defteri yok: %s" % exc, file=sys.stderr)
        return 2
    if args.dump:
        for row in rows:
            print("\t".join([row.date, row.head] +
                            ["%s #%s" % (lbl, rid) for lbl, rid in row.runs]))
        if not args.as_json:
            return 0
    if args.as_json:
        print(json.dumps({"rows": len(rows), "violations": violations,
                          "verdict": "FAIL" if violations else "PASS"},
                         ensure_ascii=False, indent=2))
    else:
        for item in violations:
            print("BAYAT: %s" % item)
        if not violations:
            print("PASS: kanit-defteri taze (%d satir, en yeni %s)"
                  % (len(rows), rows[-1].date if rows else "-"))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
