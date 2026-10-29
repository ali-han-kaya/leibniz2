#!/usr/bin/env python3
"""check_merge_decision_evidence.py — merge karar dokümanının kanıt sayılarını
commit grafiğinden yeniden ölçer; sapma varsa kırmızı.

Neden: `docs/MERGE_DECISION_*.md` içindeki sayılar (patch-id kesişimi, dosya
örtüşmesi, changelog farklı-SHA sayıları) elle yazıldı. Grafta tek bir rebase,
amend ya da eksik ölçüm bu sayıları sessizce yanlışa çevirir; okuyan kişi ise
"ölçülmüş kanıt" sanır. Bu betik dokümanı TEK KAYNAK kabul eder:

  1. Sayıları markdown tablolarından okur (ikinci kopya yok — doküman ne
     diyorsa o doğrulanır).
  2. Aynı sayıları commit grafiğinden yeniden üretir.
  3. Birebir karşılaştırır; tutmayan her satır `DRIFT` olarak listelenir.

Ölçüm çıpası (§1): dokümanın bildirdiği (dal commit sayısı, dosya, +, −)
dörtlüsünü birlikte sağlayan dal commit'i. §1 karar anındaki dal ucunu
ölçtüğü için, o tarihten sonra inen commit'ler çıpanın dışında kalır; çıpa
bulunamazsa bu "doküman sayıları grafikle bağdaşmıyor" demektir → kırmızı.

Ölçülemeyen durum sessiz PASS değildir: eksik commit/blob, ayrıştırılamayan
satır ya da ayrıştırılamayan merge commit'i → exit 2.

Kullanım:
    python3 _calisma/CIKTI/check_merge_decision_evidence.py
    python3 _calisma/CIKTI/check_merge_decision_evidence.py --json
    python3 _calisma/CIKTI/check_merge_decision_evidence.py --doc docs/MERGE_DECISION_x.md

Çıkış kodları: 0 = tüm sayılar tutuyor, 1 = sapma var, 2 = ölçülemedi.
stdlib-only, OFFLINE.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DOC = ROOT / "docs" / "MERGE_DECISION_reword-working_to_main.md"

# Doküman metnindeki tipografik karakterler: '−' U+2212 (net diff), '—' U+2014.
MINUS = "\u2212"
EMDASH = "\u2014"


class Unmeasurable(Exception):
    """Ölçüm imkânsız (eksik nesne / ayrıştırılamayan satır): exit 2."""


class ClaimDrift(Exception):
    """Doküman sayısı grafikle bağdaşmıyor: exit 1 (ölçüm değil, iddia sorunu)."""

    def __init__(self, claim, expected, measured, note=""):
        super().__init__(claim)
        self.claim = claim
        self.expected = expected
        self.measured = measured
        self.note = note

    def as_row(self):
        return {"claim": self.claim, "expected": self.expected,
                "measured": self.measured, "note": self.note}


# ── git erişimi ──────────────────────────────────────────────────────────────

def git(*args, repo=None, ok_codes=(0,)):
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo or ROOT),
        capture_output=True, text=True, check=False,
    )
    if proc.returncode not in ok_codes:
        raise Unmeasurable(
            "git %s rc=%d: %s" % (" ".join(args), proc.returncode,
                                  (proc.stderr or proc.stdout).strip()[:200]))
    return proc.stdout


def resolve(rev, repo):
    # --verify --quiet: nesne yoksa rc=1 ve BOŞ stdout — rc tek başına hata
    # değil, "commit yok" demek. Ayırt etmezsek mesajsız exit 2 olur.
    out = git("rev-parse", "--verify", "--quiet", rev, repo=repo,
              ok_codes=(0, 1)).strip()
    if not out:
        raise Unmeasurable("commit grafikte yok: %s" % rev)
    return out


def shortstat(a, b, repo):
    """(dosya, eklenen, silinen) — `git diff --shortstat a b`."""
    text = git("diff", "--shortstat", a, b, repo=repo).strip()
    if not text:
        return (0, 0, 0)
    files = int(re.search(r"(\d+) files? changed", text).group(1))
    ins = re.search(r"(\d+) insertions?\(\+\)", text)
    dels = re.search(r"(\d+) deletions?\(-\)", text)
    return (files, int(ins.group(1)) if ins else 0,
            int(dels.group(1)) if dels else 0)


def numstat(a, b, paths, repo):
    """Yol kümesi için (main'e özel satır, dala özel satır) toplamı."""
    if not paths:
        return (0, 0)
    out = git("diff", "--numstat", a, b, "--", *sorted(paths), repo=repo)
    dels = ins = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue  # binary (- -) satırı sayı taşımaz
        add, rem = parts[0], parts[1]
        if add.isdigit():
            ins += int(add)
        if rem.isdigit():
            dels += int(rem)
    return (dels, ins)


def cherry(upstream, head, repo):
    """`git cherry -v upstream head` → (patch-dengi, benzersiz)."""
    out = git("cherry", "-v", upstream, head, repo=repo)
    marks = [ln[:1] for ln in out.splitlines() if ln.strip()]
    return (marks.count("-"), marks.count("+"))


def conflict_paths(a, b, repo):
    """İki uç arasındaki çakışan yollar (ağaç yazmadan, deterministik)."""
    # merge-tree sözleşmesi: 0 = temiz, 1 = çakışma var, >1 = gerçek hata.
    out = git("merge-tree", "--write-tree", a, b, repo=repo, ok_codes=(0, 1))
    paths = []
    for line in out.splitlines():
        m = re.match(r"^CONFLICT \([^)]*\): Merge conflict in (.+)$", line)
        if m:
            paths.append(m.group(1).strip())
    return sorted(set(paths))


def is_ancestor(rev, of, repo):
    """`git merge-base --is-ancestor`: 0 = ata, 1 = değil, >1 = hata."""
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", rev, of],
        cwd=str(repo or ROOT), capture_output=True, text=True, check=False,
    )
    if proc.returncode not in (0, 1):
        raise Unmeasurable("merge-base --is-ancestor rc=%d (%s..%s)"
                           % (proc.returncode, rev, of))
    return proc.returncode == 0


def blob(rev, path, repo):
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "%s:%s" % (rev, path)],
        cwd=str(repo or ROOT), capture_output=True, text=True, check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


# ── doküman ayrıştırma (doküman tek kaynak) ──────────────────────────────────

def _need(pattern, text, what):
    m = re.search(pattern, text, re.M)
    if not m:
        raise Unmeasurable(
            "dokümanda '%s' satırı ayrıştırılamadı (desen: %s)" % (what, pattern))
    return m


def parse_claims(doc):
    c = {}
    c["merge_commit"] = _need(r"merge commit'i: `([0-9a-f]{7,40})`",
                              doc, "§7 merge commit").group(1)
    c["merge_base"] = _need(r"\| merge-base \| `([0-9a-f]{7,40})` \|",
                            doc, "§1 merge-base").group(1)
    c["branch_only"] = int(_need(r"girmemiş commit \| \*\*(\d+)\*\*",
                                 doc, "§1 daldaki benzersiz commit").group(1))
    m = _need(r"olmayan commit \| (\d+) \((\d+)'ü merge",
              doc, "§1 main tarafı commit sayısı")
    c["main_only"], c["main_merges"] = int(m.group(1)), int(m.group(2))
    c["cherry_equiv"] = int(_need(r"`git cherry -`\) \| (\d+)",
                                  doc, "§1 patch-dengi sayısı").group(1))
    c["cherry_unique"] = int(_need(r"`git cherry \+`\) \| (\d+)",
                                   doc, "§1 benzersiz sayısı").group(1))
    c["main_unique"] = int(_need(r"main tarafında benzersiz commit \| (\d+)",
                                 doc, "§1 main benzersiz commit").group(1))
    c["conflicts"] = int(_need(r"rc=1 " + EMDASH + r" (\d+) dosyada çakışma",
                               doc, "§1 çakışan dosya sayısı").group(1))
    m = _need(r"Net içerik farkı[^|]*\| (\d+) dosya, \+(\d+)/"
              + MINUS + r"(\d+) \|",
              doc, "§1 net içerik farkı")
    c["net"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    c["cls_branch"] = int(_need(r"Dal tarafı kazandı[^|]*\| (\d+) \|",
                                doc, "§7.1 dal tarafı").group(1))
    c["cls_main"] = int(_need(r"Main tarafı kazandı[^|]*\| (\d+) \|",
                              doc, "§7.1 main tarafı").group(1))
    c["cls_hand"] = int(_need(r"Elle birleştirildi \| (\d+) \|",
                              doc, "§7.1 elle birleştirme").group(1))
    c["still_branch_blob"] = int(_need(r"taşıyan (\d+) yol",
                                       doc, "§7.1 dal blob'u taşıyan yol").group(1))
    row = _need(r"^\| `[0-9a-f]{7,40}`(?:, `[0-9a-f]{7,40}`)+ \|",
                doc, "§2 changelog farklı-SHA satırı").group(0)
    c["changelog_shas"] = re.findall(r"`([0-9a-f]{7,40})`", row)
    return c


def parse_file_rows(doc):
    """§4 tablosu: [(doküman yolu, main'e özel, dala özel)] — yalnız N↔M satırları."""
    rows = []
    for line in doc.splitlines():
        m = re.match(r"^\|\s*`?([^|`]+?)`?\s*\|\s*(\d+)↔(\d+)\s*\|", line)
        if m:
            rows.append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
    if not rows:
        raise Unmeasurable("§4 dosya tablosundan hiçbir N↔M satırı okunamadı")
    return rows


# ── yol genişletme (§4 satırları glob/brace içerebilir) ──────────────────────

def _brace_expand(pattern):
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out = []
    for alt in m.group(1).split(","):
        out.extend(_brace_expand(pattern[:m.start()] + alt.strip() + pattern[m.end():]))
    return out


def tracked_files(repo):
    return [p for p in git("ls-files", "-z", repo=repo).split("\0") if p]


def _suffix_hits(cand, tracked):
    """`verify.yml` / `verify_mcp/README` gibi kısa yolları tam yola çevirir.

    Son bileşen uzantı toleranslıdır (`server` → `server.py`); ara bileşenler
    birebir eşleşmeli. Tek eşleşme yoksa yol belirsiz sayılır.
    """
    parts = cand.split("/")
    hits = []
    for path in tracked:
        pieces = path.split("/")
        if len(pieces) < len(parts):
            continue
        tail = pieces[-len(parts):]
        if all(t == c for t, c in zip(tail[:-1], parts[:-1])) and (
                tail[-1] == parts[-1] or tail[-1].startswith(parts[-1] + ".")):
            hits.append(path)
    return sorted(hits)


def expand_paths(pattern, repo, tracked):
    """Doküman yolu → (repo içindeki dosyalar, çözülemeyen parçalar).

    Sıra: tam yol (kök, sonra _calisma/CIKTI) → glob → repo genelinde tek
    eşleşmeli son-bileşen araması. Doc §4'ü kısa adlarla yazıyor
    (`verify.yml`, `verify_mcp/README`); tam yol yoksa bu sıra devreye girer.
    Brace kümesinin her parçası ayrı çözümlenir; çözülemeyen ya da birden çok
    eşleşen parça `problems` ile döner → sessiz PASS yok.
    """
    found, problems = [], []
    for pat in _brace_expand(pattern):
        hits = []
        for base in (repo, repo / "_calisma" / "CIKTI"):
            cand = base / pat
            if any(ch in pat for ch in "*?["):
                hits.extend(sorted(str(p.relative_to(repo)) for p in base.glob(pat)
                                   if p.is_file()))
            elif cand.is_file():
                hits.append(str(cand.relative_to(repo)))
            else:
                hits.extend(sorted(str(p.relative_to(repo)) for p in base.glob(pat + "*")
                                   if p.is_file()))
        if hits:
            found.extend(hits)
            continue
        short = _suffix_hits(pat, tracked)
        if len(short) == 1:
            found.extend(short)
        elif len(short) > 1:
            problems.append("belirsiz (%d eşleşme): %s"
                            % (len(short), ", ".join(short[:3])))
        else:
            problems.append("bulunamadı: %s" % pat)
    return sorted(set(found)), problems


# ── ölçüm ────────────────────────────────────────────────────────────────────

def find_anchor(main_tip, branch_tip, want_count, want_diff, repo):
    """§1 çıpası: (main_tip..branch_tip) içinde `want_count`. commit."""
    revs = git("rev-list", "--reverse", "%s..%s" % (main_tip, branch_tip),
               repo=repo).split()
    if len(revs) < want_count:
        raise ClaimDrift("§1 dal commit sayısı", want_count, len(revs),
                         "main..dal aralığında bu kadar commit yok")
    anchor = revs[want_count - 1]
    got = shortstat(main_tip, anchor, repo)
    if got != want_diff:
        raise ClaimDrift("§1 çıpa (commit + net fark dörtlüsü)",
                         (want_count,) + tuple(want_diff),
                         (want_count,) + tuple(got),
                         "%.7s: dörtlüyü birlikte sağlayan dal ucu yok" % anchor)
    return anchor, len(revs) - want_count


def measure(claims, file_rows, repo):
    merge = resolve(claims["merge_commit"], repo)
    parents = git("rev-list", "--parents", "-n", "1", merge, repo=repo).split()[1:]
    if len(parents) != 2:
        raise Unmeasurable("merge commit'i iki ebeveynli değil: %s" % merge)
    branch_tip, main_tip = parents
    base = git("merge-base", branch_tip, main_tip, repo=repo).strip()
    main_now = resolve("origin/main", repo)

    anchor, after = find_anchor(main_tip, branch_tip, claims["branch_only"],
                                claims["net"], repo)

    equiv, unique = cherry(main_tip, anchor, repo)
    main_only = int(git("rev-list", "--count", "%s..%s" % (anchor, main_tip),
                        repo=repo).strip())
    main_merges = int(git("rev-list", "--count", "--merges",
                          "%s..%s" % (anchor, main_tip), repo=repo).strip())
    _, main_unique = cherry(anchor, main_tip, repo)
    net = shortstat(main_tip, anchor, repo)

    paths = conflict_paths(branch_tip, main_tip, repo)
    cls = {"branch": 0, "main": 0, "hand": 0}
    still_branch = 0
    for path in paths:
        a = blob(branch_tip, path, repo)
        b = blob(main_tip, path, repo)
        m = blob(merge, path, repo)
        if a and m and a == m and b != m:
            cls["branch"] += 1
        elif b and m and b == m and a != m:
            cls["main"] += 1
        else:
            cls["hand"] += 1
        now = blob(main_now, path, repo)
        if now and m and now == m and b != m:
            still_branch += 1

    tracked = tracked_files(repo)
    files = {}
    for doc_path, _, _ in file_rows:
        targets, problems = expand_paths(doc_path, repo, tracked)
        files[doc_path] = {"targets": targets, "problems": problems,
                           "numstat": numstat(main_tip, anchor, targets, repo)}

    shas = {}
    for sha in claims["changelog_shas"]:
        full = resolve(sha, repo)
        touches = git("show", "--name-only", "--format=", full, repo=repo)
        shas[sha] = {
            "in_main": is_ancestor(full, main_tip, repo),
            "in_anchor": is_ancestor(full, anchor, repo),
            "touches_readme": "README.md" in touches.split(),
        }

    return {
        "anchor": anchor,
        "commits_after_measurement": after,
        "merge": merge,
        "merge_base": base,
        "branch_tip": branch_tip,
        "main_tip": main_tip,
        "branch_only": len(git("rev-list", "%s..%s" % (main_tip, anchor),
                               repo=repo).split()),
        "cherry_equiv": equiv,
        "cherry_unique": unique,
        "main_only": main_only,
        "main_merges": main_merges,
        "main_unique": main_unique,
        "net": net,
        "conflicts": len(paths),
        "cls": cls,
        "still_branch_blob": still_branch,
        "files": files,
        "changelog_shas": shas,
    }


# ── karşılaştırma ────────────────────────────────────────────────────────────

def compare(claims, file_rows, m):
    drift = []
    total = 0

    def check(name, expected, got, note=""):
        nonlocal total
        total += 1
        if expected != got:
            drift.append({"claim": name, "expected": expected, "measured": got,
                          "note": note})

    check("§1 merge-base", claims["merge_base"], m["merge_base"][:7])
    check("§1 dal commit (A\\main)", claims["branch_only"], m["branch_only"])
    check("§1 patch-dengi (git cherry -)", claims["cherry_equiv"], m["cherry_equiv"])
    check("§1 benzersiz (git cherry +)", claims["cherry_unique"], m["cherry_unique"])
    check("§1 main tarafı benzersiz commit", claims["main_unique"], m["main_unique"])
    check("§1 main tarafı commit (merge dahil)",
          (claims["main_only"], claims["main_merges"]),
          (m["main_only"], m["main_merges"]))
    check("§1 net içerik farkı (dosya,+,−)", claims["net"], m["net"])
    check("§1 çakışan dosya", claims["conflicts"], m["conflicts"])
    check("§7.1 dal tarafı kazandı", claims["cls_branch"], m["cls"]["branch"])
    check("§7.1 main tarafı kazandı", claims["cls_main"], m["cls"]["main"])
    check("§7.1 elle birleştirildi", claims["cls_hand"], m["cls"]["hand"])
    check("§7.1 dal blob'u taşıyan yol", claims["still_branch_blob"],
          m["still_branch_blob"])

    for doc_path, main_side, branch_side in file_rows:
        entry = m["files"][doc_path]
        if entry["problems"]:
            drift.append({"claim": "§4 " + doc_path,
                          "expected": (main_side, branch_side),
                          "measured": entry["numstat"],
                          "note": "; ".join(entry["problems"])})
            continue
        check("§4 " + doc_path, (main_side, branch_side), entry["numstat"])

    for sha, st in m["changelog_shas"].items():
        total += 1
        # §2 iddiası: bu SHA'lar main tarafında ama dalda YOK, ve README'ye
        # dokunuyorlar (aynı iş daldа farklı SHA'larla yaşıyor).
        if not (st["in_main"] and not st["in_anchor"] and st["touches_readme"]):
            drift.append({"claim": "§2 changelog farklı-SHA " + sha,
                          "expected": "main tarafında + dalda yok + README",
                          "measured": st,
                          "note": "commit bu üç koşulu birlikte sağlamıyor"})
    return drift, total


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc", default=str(DEFAULT_DOC),
                    help="ölçülecek karar dokümanı (varsayılan: %(default)s)")
    ap.add_argument("--repo", default=str(ROOT), help="git deposu kökü")
    ap.add_argument("--json", action="store_true", help="tek JSON dokümanı yaz")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    doc_path = Path(args.doc)
    try:
        try:
            doc = doc_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Unmeasurable("doküman okunamadı (%s): %s" % (doc_path, exc))
        claims = parse_claims(doc)
        file_rows = parse_file_rows(doc)
        measured = measure(claims, file_rows, repo)
        drift, total = compare(claims, file_rows, measured)
    except ClaimDrift as exc:
        payload = {"ok": False, "doc": str(doc_path), "error": None,
                   "drift": [exc.as_row()]}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("SAPMA: %s — doküman %s ≠ ölçülen %s%s"
                  % (exc.claim, exc.expected, exc.measured,
                     ("  (%s)" % exc.note) if exc.note else ""), file=sys.stderr)
        return 1
    except Unmeasurable as exc:
        payload = {"ok": False, "doc": str(doc_path), "error": str(exc),
                   "drift": []}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("ÖLÇÜLEMEDİ: %s" % exc, file=sys.stderr)
        return 2

    payload = {
        "ok": not drift,
        "doc": str(doc_path),
        "anchor": measured["anchor"],
        "commits_after_measurement": measured["commits_after_measurement"],
        "claims": claims,
        "measured": {k: v for k, v in measured.items()
                     if k not in ("files", "changelog_shas")},
        "files": measured["files"],
        "changelog_shas": measured["changelog_shas"],
        "drift": drift,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("merge kanıtı yeniden ölçümü — %s" % doc_path.name)
        print("  çıpa: %.7s (§1 dörtlüsünü sağlayan dal commit'i; merge öncesi "
              "%d commit)" % (measured["anchor"], measured["commits_after_measurement"]))
        print("  merge: %.7s  ebeveynler: %.7s (dal) + %.7s (main)"
              % (measured["merge"], measured["branch_tip"], measured["main_tip"]))
        for row in drift:
            print("  DRIFT  %-44s doküman %s ≠ ölçülen %s%s"
                  % (row["claim"], row["expected"], row["measured"],
                     ("  (%s)" % row["note"]) if row["note"] else ""))
        print("  SONUÇ: %d/%d tuttu, %d sapma"
              % (total - len(drift), total, len(drift)))
    return 0 if not drift else 1


if __name__ == "__main__":
    sys.exit(main())
