#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_merge_precondition.py — merge ÖNCÜLÜNÜ denemeden ölç.

Neden: "X dalını Y'ye merge et" isteğinin en yaygın ve en sessiz başarısızlık
biçimi NO-OP'tur. Ölçüldü (2026-09-28): aynı istek bu depoda **5 kez** geldi
(`work/2026-09-19` → `reword-working`, "üst üste beş commit var: pptx fix,
composition pass, perf dedup, survey docs") ve **5 kez** no-op çıktı. İstek
metnindeki "beş commit yığını" **yanlıştı**: öznelerin gerçek ref'leri
(`d396b8c` pptx fix, `9ce6e32` composition pass, `b156cb4` perf dedup,
`f0e21fe` RN survey, `41e1f48` client-side nav) çoktan `reword-working` VE
`main` içindeydi. Yani istek, "henüz olmamış bir birleşimi" tarif ediyordu.

İki ayrı hata vardı ve ikisi de pahalı:
  1. Merge denemeden sayılmadı → 5 tur aynı işi ölçtü.
  2. İstekteki özne adları hiç aranmadı → "stacked commit" yanılgısı
     ölçümle çürütülene kadar sürdü.

Bu kapı ikisini de ÖNCÜL olarak ölçer ve merge denemeden raporlar.

Sözleşme (seam = kapı CLI'sı):
- `TARGET SOURCE` verilirse ÇİFT RAPORU: source, target içinde zaten
  tamamen mi? Gelen kaç commit? Ters yön kaç? merge-base nerede?
- `--subject` (tekrarlanabilir) verilirse özne adları ARANIR: her özne için
  eşleşen commit'lerin SHA'sı ve target/source içinde olup OLMADIĞI
  raporlanır. "İstekte adı geçen commit gerçekten yeni mi?" sorusunun
  ölçülebilir hali. (İsim eşleşmesi YETERLİ DEĞİLDİR — tarih/containment
  yerine geçmez; bu yüzden bulgu 'eşleşti' değil 'target içinde mi' diye
  raporlanır.)
- Argümansız (audit modu): YEREL dallar upstream'lerine göre taranır ve İKİ
  eyleme dönüşen sinyal raporlanır — `stale_local` (dal upstream'in
  GERİSİNDE; ölçülen gerçek: yerel reword-working 6 commit gerideydi) ve
  `unpushed` (yerelde push edilmemiş commit var). `behind == 0` bilinçli
  OLARAK sinyal değildir: sıfır, sağlıklı senkron halin işaretidir ve
  no-op tespiti yalnız çift modunda yaşar.

Exit: 0 = ölçülebilir ve birleşim işe yarar (ya da advisory uyarı),
      1 = --strict altında no-op bulundu,
      2 = kullanım/ölçüm hatası (ref çözülemedi → kör PASS üretme).
--json: makine-okunur.

OFFLINE: yalnız yerel git komutları; ağ YOK. stdlib-only.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


class GitError(RuntimeError):
    """git komutu başarısız oldu / ref çözülemedi."""


def git(args, cwd=ROOT):
    """git çalıştırır. (stdout) döner; hata hâlinde GitError yükselir."""
    proc = subprocess.run(
        ["git"] + list(args), cwd=cwd, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise GitError(
            "git %s → rc=%d %s" % (" ".join(args), proc.returncode,
                                   proc.stderr.strip())
        )
    return proc.stdout.strip()


def try_git(args, cwd=ROOT):
    """git çalıştırır, hata hâlinde None (sessiz ölçüm yutması)."""
    try:
        return git(args, cwd)
    except GitError:
        return None


def _int(text):
    """'12\\n' → 12; ölçülemezse None."""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def precondition(target, source, cwd=ROOT):
    """Çift raporu. rc 0/1/2 — sözleşme modül başlığında."""
    report = {
        "target": target,
        "source": source,
        "target_sha": "",
        "source_sha": "",
        "incoming": None,      # target..source  (kaç commit geliyor)
        "ahead": None,         # source..target  (target'da fazladan kaç var)
        "merge_base": "",
        "base_is_source_tip": False,
        "source_contained": False,
        "no_op": False,
        "rc": 2,
        "ok": False,
    }
    try:
        report["target_sha"] = git(["rev-parse", "--short", target], cwd)
        report["source_sha"] = git(["rev-parse", "--short", source], cwd)
    except GitError as exc:
        print("HATA: ref çözülemedi: %s" % exc)
        return 2, report

    base = try_git(["merge-base", target, source], cwd)
    report["merge_base"] = (base or "")[:7]
    incoming = _int(try_git(["rev-list", "--count", "%s..%s" % (target, source)], cwd))
    ahead = _int(try_git(["rev-list", "--count", "%s..%s" % (source, target)], cwd))
    report["incoming"] = incoming
    report["ahead"] = ahead

    # İki bağımsız no-op kanıtı:
    #  (a) incoming == 0 → source'ın getireceği commit yok.
    #  (b) merge-base == source ucu → source ZATEN ortak taban; en kesin
    #      kanıt (fark 0 sayımından güçlü: dalın ucu aynı zamanda taban).
    report["base_is_source_tip"] = bool(
        base and base == try_git(["rev-parse", source], cwd)
    )
    report["source_contained"] = incoming == 0
    report["no_op"] = bool(report["source_contained"] or report["base_is_source_tip"])
    report["rc"] = 1 if report["no_op"] else 0
    report["ok"] = not report["no_op"]
    return report["rc"], report


def find_subjects(target, source, subjects, cwd=ROOT):
    """Özne adlarını ara. [{subject, matches:[{sha, in_target, in_source}]}].

    'in_target'/'in_source' merge-base --is-ancestor ile ÖLÇÜLÜR (isim
    eşleşmesi yeterli değildir — bu turun 5. kez öğrenilen ders).
    """
    out = []
    for raw in subjects:
        needle = raw.strip()
        entry = {"subject": needle, "matches": [], "resolved": False}
        if not needle:
            out.append(entry)
            continue
        # log --grep bir regex'tir; kullanıcı metnini kaçırmak yerine
        # sabit-geçişli arama için --fixed-strings kullanmıyoruz: eşleşen
        # commit'lerin tam listesini isteyelim (grep -i -F).
        text = try_git(
            ["log", "--all", "--oneline", "-i", "--fixed-strings",
             "--grep=" + needle],
            cwd,
        )
        if text is None:
            out.append(entry)
            continue
        entry["resolved"] = True
        for line in text.splitlines():
            sha = line.split(" ", 1)[0].strip()
            if not sha:
                continue
            in_target = subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, target],
                cwd=cwd, capture_output=True,
            ).returncode == 0
            in_source = subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, source],
                cwd=cwd, capture_output=True,
            ).returncode == 0
            entry["matches"].append(
                {"sha": sha[:7], "in_target": in_target, "in_source": in_source}
            )
        out.append(entry)
    return out


def audit(cwd=ROOT):
    """Yerel dallar × upstream denetimi. İKİ AYRI, EYLEME DÖNÜŞEN sinyal.

    `behind` = upstream'de olup yerel dalda OLMAYAN commit sayısı
    (dal upstream'in ne kadar gerisinde); `ahead` = tersi. İki okunur sonuç:

      * `stale_local` (behind > 0) — yerel kopya geride → `pull --ff-only`
        ile ileri alınabilir. ÖLÇÜLEN GERÇEK: yerel reword-working
        6 commit gerideydi.
      * `unpushed` (ahead > 0) — yerelde upstream'te OLMAYAN commit var →
        push edilmemiş iş.

    Neden `behind == 0` bir sinyal DEĞİL: sıfır, sağlıklı halin İŞARETİ
    (dal upstream'te senkron). İlk sürüm `behind == 0`'ı "no-op adayı"
    sayıyordu ve gerçek depoda 18 dalın 7'sini — `main` ve tam senkron
    dallar dahil — "bulgu" diye işaretledi (ölçüldü). Bu kapı sahte ağlama
    üretiyordu; bu yüzden no-op tespiti yalnız ÇİFT modunda yaşar, burada
    değil.
    """
    report = {"mode": "audit", "branches": [], "unpushed_branches": [],
              "stale_locals": [], "rc": 0, "ok": True}
    text = try_git(
        ["for-each-ref", "--format=%(refname:short)|%(upstream:short)",
         "refs/heads/"], cwd,
    )
    if text is None:
        print("HATA: yerel dallar okunamadı (git for-each-ref başarısız).")
        report["rc"] = 2
        report["ok"] = False
        return 2, report
    for line in text.splitlines():
        if "|" not in line:
            continue
        branch, _, upstream = line.partition("|")
        branch, upstream = branch.strip(), upstream.strip()
        row = {"branch": branch, "upstream": upstream,
               "behind": None, "ahead": None,
               "unpushed": False, "stale_local": False}
        if not upstream:
            # upstream yok → karşılaştırma yok, hiçbir sinyal doğmaz.
            report["branches"].append(row)
            continue
        behind = _int(try_git(
            ["rev-list", "--count", "%s..%s" % (branch, upstream)], cwd))
        ahead = _int(try_git(
            ["rev-list", "--count", "%s..%s" % (upstream, branch)], cwd))
        row["behind"], row["ahead"] = behind, ahead
        row["stale_local"] = bool(behind and behind > 0)
        row["unpushed"] = bool(ahead and ahead > 0)
        if row["stale_local"]:
            report["stale_locals"].append(branch)
        if row["unpushed"]:
            report["unpushed_branches"].append(branch)
        report["branches"].append(row)
    return 0, report


def render(report):
    """İnsan-okunur çıktı satırları.

    rc == 2 (ölçülemedi) iken ASLA bir verdict basılmaz. Ölçüldü (2026-09-28):
    çözülemeyen bir kaynak ref'inde kapı doğru şekilde rc=2 döndü ama
    render yine de "PASS: birleşim işe yarar (None commit geliyor)" yazdı —
    yani bir CI günlüğünde ÖLÇÜLEMEN iş, BAŞARILI görünürdü. Çıkış kodu
    fail-closed'u korur; bu blok insan-okunur tarafını aynı sözleşmeye bağlar.
    """
    lines = []
    if report.get("rc") == 2 and report.get("mode") != "audit":
        lines.append("MERGE ÖNCÜLÜ (check-merge-precondition)")
        lines.append("  ÖLÇÜLEMEDİ: hedef veya kaynak ref çözülemedi.")
        lines.append("  Bu bir PASS/FAIL DEĞİLDİR — karar yok. rc=2 "
                     "(fail-closed).")
        lines.append("  Merge denenmedi. Önce ref'in var olduğunu doğrula "
                     "(git rev-parse --verify <ref>).")
        return lines

    if report.get("mode") == "audit":
        lines.append("MERGE ÖNCÜLÜ — YEREL DALLAR (check-merge-precondition)")
        lines.append("  %d dal tarandı (audit: senkronlık + push edilmemiş iş)"
                     % len(report["branches"]))
        for row in [r for r in report["branches"] if r["upstream"]]:
            notes = []
            if row["stale_local"]:
                notes.append("yerel %s commit geride (ff-only)" % row["behind"])
            if row["unpushed"]:
                notes.append("%s commit push edilmemiş" % row["ahead"])
            lines.append("  %-32s behind=%-4s ahead=%-4s%s"
                         % (row["branch"], row["behind"], row["ahead"],
                            "   ← " + ", ".join(notes) if notes else ""))
        if report["stale_locals"]:
            lines.append("BULGU: %d dal upstream'in gerisinde → ilerletilebilir."
                         % len(report["stale_locals"]))
        if report["unpushed_branches"]:
            lines.append("BULGU: %d dalda push edilmemiş commit var."
                         % len(report["unpushed_branches"]))
        if not report["stale_locals"] and not report["unpushed_branches"]:
            lines.append("PASS: bütün dallar upstream ile senkron.")
        return lines

    lines.append("MERGE ÖNCÜLÜ (check-merge-precondition)")
    lines.append("  hedef (target): %s = %s" % (report["target"], report["target_sha"]))
    lines.append("  kaynak (source): %s = %s" % (report["source"], report["source_sha"]))
    lines.append("  gelen commit (target..source): %s" % report["incoming"])
    lines.append("  hedefte fazlalan (source..target): %s" % report["ahead"])
    lines.append("  merge-base: %s" % report["merge_base"])
    if report["no_op"]:
        lines.append("BAYAT: kaynak zaten hedefin İÇİNDE → merge NO-OP.")
        if report["base_is_source_tip"]:
            lines.append("  kesin kanıt: merge-base KAYNAK UCU = "
                         "'Already up to date' beklenir.")
        lines.append("  çözüm: merge deneme. Kaynağın commit'leri zaten "
                     "hedefte; ilerleme için hedefi KENDİ upstream'ine "
                     "fast-forward et veya başka bir kaynak seç.")
    else:
        lines.append("PASS: birleşim işe yarar (%s commit geliyor)."
                     % report["incoming"])
    return lines


def _render_subjects(entries, report, out):
    """Özne bulgularını çıktıya ekler; no-op ise rc 1'e çeker."""
    if not entries:
        return
    out.append("  özne araştırması (--subject):")
    for entry in entries:
        if not entry["resolved"] or not entry["matches"]:
            out.append("    %-16s → eşleşme yok" % entry["subject"])
            continue
        tags = []
        for m in entry["matches"]:
            tags.append(
                "%s [target:%s source:%s]"
                % (m["sha"], "VAR" if m["in_target"] else "yok",
                   "VAR" if m["in_source"] else "yok")
            )
        out.append("    %-16s → %s" % (entry["subject"], ", ".join(tags)))
        # Özne adı geçiyor ama target'da YOKSA istek gerçek bir iş tarif
        # ediyor demektir; hepsi target'ta VARSA istek bayat.
        if not any(m["in_target"] for m in entry["matches"]):
            report["subjects_pending"] = True
            report["ok"] = False
    out.append("  (target:VAR = özne hedef dalda zaten var → 'yeni yığın' "
               "değil, tarih)")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="merge ÖNCÜLÜ denetimi: kaynak hedefe gerçekten bir şey "
                    "getiriyor mu, denemeden ölç. Argümansız: yerel dal "
                    "audit'i.")
    ap.add_argument("target", nargs="?", help="hedef dal (ör. reword-working)")
    ap.add_argument("source", nargs="?",
                    help="kaynak dal (ör. feature/yeni-is)")
    ap.add_argument("--subject", action="append", default=[],
                    help="isteğin öne sürdüğü commit öznesi (tekrarlanabilir)")
    ap.add_argument("--root", default=ROOT, help="git deposu kökü")
    ap.add_argument("--strict", action="store_true",
                    help="no-op bulunursa exit 1 (varsayılan: yalnız uyarı)")
    ap.add_argument("--json", action="store_true", help="makine-okunur JSON")
    args = ap.parse_args(argv)

    if bool(args.target) != bool(args.source):
        print("HATA: target VE source birlikte verilmelidir (ya da hiçbiri "
              "— audit modu).")
        return 2

    if args.target:
        rc, report = precondition(args.target, args.source, args.root)
    else:
        rc, report = audit(args.root)

    report["strict"] = args.strict
    report["subjects"] = (
        find_subjects(args.target, args.source, args.subject, args.root)
        if (args.target and args.subject) else []
    )

    if args.json:
        payload = dict(report)
        payload["ok"] = bool(report["ok"]) and rc == 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if rc == 2:
            return 2
        return rc if args.strict else 0

    lines = render(report)
    _render_subjects(report["subjects"], report, lines)
    for line in lines:
        print(line)

    if rc == 2:
        return 2
    finding = bool(report.get("no_op")) or bool(report.get("stale_locals")) \
        or bool(report.get("unpushed_branches"))
    if finding:
        if args.strict:
            print("SONUÇ: FAIL (--strict) — merge ön-ölçüm bulgusu.")
            return 1
        print("UYARI: merge ön-ölçüm bulgusu (advisory — merge denemeden "
              "önce ff-only çalıştır).")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
