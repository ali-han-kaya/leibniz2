#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_merge_precondition.py — merge ön-ölçüm kapısının sözleşmeleri.

Fixture = GERÇEK ama geçici git deposu (`git init -b main`, mktemp). Neden
fake değil: bu kapının tamamı git'in topolojisinden besleniyor
(merge-base, --is-ancestor, for-each-ref upstream) — sahte git çıktısı
üreten bir fake, kapının YANLIŞ olduğu yerde yeşil kalırdı. Ağ kullanılmaz.

ÖNEMLİ topoloji kuralı: `commit()` ÇALIŞILAN dala yazar. Yeni commit'i
`work` dalına koymak istiyorsan önce `checkout("work")` şart — testlerin
ilk yazımı bunu atlayıp "kaynak ileride" senaryolarını yanlış kurdu
(kaynak geride kalıyordu ve kapı doğru şekilde "no-op" diyordu; hata
testteydi, kapıda değil).

Kapsanan sözleşmeler:
  - beş turda tekrarlanan no-op: base == source ucu, incoming == 0
  - kesin kanıt (base_is_source_tip) ile zayıf kanıtın (incoming == 0) aynı
    sonuca varması
  - gerçek (uygulanabilir) birleşim: incoming > 0 → no-op DEĞİL
  - ayrışmış (diverged) hedef: incoming > 0 → no-op DEĞİL
  - çözülemeyen ref → rc 2 (kör PASS yok)
  - audit İKİ eyleme dönüşen sinyali AYRI ölçer: stale_local (ff-only) ve
    unpushed (push edilmemiş iş); SENKRON dal SESSİZ kalır (regresyon kilidi)
  - upstream'sız dal hiçbir sinyal doğurmaz (false-positive yok)
  - --subject: özneler target'ta VAR → "yeni yığın" iddiası yanlışlanır
  - CLI: kullanım hatası rc 2 (SystemExit dahil), --json şeması, --strict rc 1
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from _calisma.CIKTI import check_merge_precondition as gate  # noqa: E402


def _git(repo, *args):
    proc = subprocess.run(["git"] + list(args), cwd=repo,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError("git %s → %s" % (" ".join(args), proc.stderr))
    return proc.stdout


class FakeRepo:
    """Geçici git deposu: commit + branch + upstream kurma yardımcıları."""

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="merge-precond-")
        _git(self.path, "init", "-b", "main")
        _git(self.path, "config", "user.email", "t@t")
        _git(self.path, "config", "user.name", "t")

    def commit(self, filename, content, message):
        """ÇALIŞILAN dala commit yazar (branch() sonrası checkout şart)."""
        with open(os.path.join(self.path, filename), "w", encoding="utf-8") as fh:
            fh.write(content)
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", message)
        return _git(self.path, "rev-parse", "--short", "HEAD").strip()

    def branch(self, name, start=None):
        args = ["branch", name] + ([start] if start else [])
        _git(self.path, *args)

    def checkout(self, name):
        _git(self.path, "checkout", name)

    def set_upstream(self, local, upstream):
        _git(self.path, "branch", "--set-upstream-to=" + upstream, local)

    def close(self):
        shutil.rmtree(self.path, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()
        self.addCleanup(self.repo.close)
        # Kapı yazdırıyor; batarya çıktısı okunur kalsın diye bastır.
        sink = contextlib.redirect_stdout(io.StringIO())
        sink.__enter__()
        self.addCleanup(sink.__exit__, None, None, None)
        self.repo.commit("a.txt", "a", "chore: base")


class PairModeTest(Base):
    """Çift (target, source) raporu."""

    def test_source_fully_contained_is_no_op(self):
        """5 turun olgusu: kaynak hedefin içindeyse merge no-op'tur."""
        self.repo.branch("work", "HEAD")
        self.repo.commit("c.txt", "c", "feat: later")  # main ilerledi
        rc, rep = gate.precondition("main", "work", self.repo.path)
        self.assertEqual(rc, 1, "kaynak tamamen içindeyse no-op (rc 1)")
        self.assertTrue(rep["no_op"])
        self.assertEqual(rep["incoming"], 0)
        self.assertTrue(rep["base_is_source_tip"],
                        "merge-base kaynak ucu olmalı — kesin kanıt")

    def test_evidence_agrees_when_contained(self):
        """İki bağımsız kanıt (incoming==0 ve base==source ucu) aynı sonuca."""
        self.repo.branch("work", "HEAD")
        self.repo.commit("c.txt", "c", "feat: later")
        _, rep = gate.precondition("main", "work", self.repo.path)
        self.assertEqual(rep["source_contained"], rep["base_is_source_tip"])

    def test_source_ahead_is_real_merge(self):
        """Kaynak ilerideyse birleşim işe yarar → no-op DEĞİL."""
        self.repo.branch("work", "HEAD")
        self.repo.checkout("work")
        self.repo.commit("w.txt", "w", "feat: real work")
        rc, rep = gate.precondition("main", "work", self.repo.path)
        self.assertEqual(rc, 0)
        self.assertFalse(rep["no_op"])
        self.assertEqual(rep["incoming"], 1)
        self.assertFalse(rep["base_is_source_tip"])

    def test_diverged_target_is_not_no_op(self):
        """Hedef ayrışmışsa (kendi commit'i var) merge boş değildir."""
        self.repo.branch("work", "HEAD")
        self.repo.checkout("work")
        self.repo.commit("w.txt", "w", "feat: side")
        self.repo.checkout("main")
        self.repo.commit("m.txt", "m", "feat: main side")
        rc, rep = gate.precondition("main", "work", self.repo.path)
        self.assertEqual(rc, 0)
        self.assertFalse(rep["no_op"])
        self.assertEqual(rep["incoming"], 1)
        self.assertEqual(rep["ahead"], 1)

    def test_unresolvable_ref_is_rc2(self):
        """Kör PASS üretme: çözülemeyen ref ölçüm hatasıdır."""
        rc, rep = gate.precondition("main", "yok-boyle-dal", self.repo.path)
        self.assertEqual(rc, 2)
        self.assertFalse(rep["ok"])

    def test_identical_refs_are_no_op(self):
        rc, rep = gate.precondition("main", "main", self.repo.path)
        self.assertEqual(rc, 1)
        self.assertTrue(rep["no_op"])


class SubjectTest(Base):
    """--subject: 'stacked commit' iddiasını ÖLÇÜLEBİLİR kılar."""

    def test_subject_already_in_target_is_not_new_work(self):
        """Özne adı geçiyor ama target'ta VARSA istek bayat — asıl ders."""
        sha = self.repo.commit("p.txt", "p",
                               "test(pptx): survive missing node_modules")
        self.repo.branch("work", "HEAD")
        entries = gate.find_subjects("main", "work", ["pptx"], self.repo.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(entries[0]["matches"]), 1)
        self.assertEqual(entries[0]["matches"][0]["sha"], sha)
        self.assertTrue(entries[0]["matches"][0]["in_target"],
                        "özne target'ta → 'yeni yığın' iddiası yanlış")
        self.assertTrue(entries[0]["matches"][0]["in_source"])

    def test_subject_absent_from_target_is_pending(self):
        """Özne target'ta YOKSA gerçek iş — eşleşmesiz raporlanır."""
        self.repo.commit("x.txt", "x", "feat: unrelated")
        entries = gate.find_subjects("main", "work",
                                     ["nonexistent-subject-xyz"], self.repo.path)
        self.assertEqual(entries[0]["matches"], [])

    def test_subject_matching_is_case_insensitive(self):
        self.repo.commit("n.txt", "n", "perf(dashboard): Per-Request Dedup")
        entries = gate.find_subjects("main", "main", ["per-request"], self.repo.path)
        self.assertTrue(entries[0]["matches"],
                        "eşleşme büyük/küçük harf duyarsız")

    def test_blank_subject_is_skipped(self):
        entries = gate.find_subjects("main", "main", ["  "], self.repo.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matches"], [])


class AuditModeTest(Base):
    """Argümansız audit: İKİ eyleme dönüşen sinyal, SESSİZ sağlıklı hal."""

    def test_in_sync_branch_is_not_reported(self):
        """Senkron dal (behind=0, ahead=0) SESSİZ kalmalı.

        İlk sürüm `behind == 0`'ı "no-op adayı" sayıyordu ve gerçek depoda
        18 dalın 7'sini — `main` ve tam senkron dallar dahil — bulgu diye
        işaretledi. Bu regresyon kilitli: sağlıklı hal bulgu ÜRETMEMELİ.

        Fixture notu: senkron dal için upstream'i KENDİSİ yapmak işe
        yaramaz — git reddeder ("not setting branch as its own upstream",
        rc=0 ama upstream boş kalır; ölçüldü). Aynı commit'te duran AYRI
        bir ref upstream olarak kullanılır.
        """
        self.repo.branch("shared", "HEAD")
        self.repo.branch("tip", "HEAD")   # aynı commit → senkron
        self.repo.set_upstream("shared", "tip")
        rc, rep = gate.audit(self.repo.path)
        self.assertEqual(rc, 0)
        row = {r["branch"]: r for r in rep["branches"]}["shared"]
        self.assertEqual(row["behind"], 0)
        self.assertEqual(row["ahead"], 0)
        self.assertFalse(row["stale_local"])
        self.assertFalse(row["unpushed"])
        self.assertEqual(rep["stale_locals"], [])
        self.assertEqual(rep["unpushed_branches"], [])

    def test_unpushed_commits_are_flagged(self):
        """Yerelde upstream'te olmayan commit varsa 'unpushed' sinyali doğar."""
        self.repo.branch("side", "HEAD")
        self.repo.branch("tip", "HEAD")
        self.repo.checkout("side")
        self.repo.commit("s.txt", "s", "feat: local only")
        self.repo.set_upstream("side", "tip")
        rc, rep = gate.audit(self.repo.path)
        self.assertEqual(rc, 0)
        row = {r["branch"]: r for r in rep["branches"]}["side"]
        self.assertEqual(row["ahead"], 1)
        self.assertTrue(row["unpushed"])
        self.assertIn("side", rep["unpushed_branches"])

    def test_stale_local_is_flagged(self):
        """Yerel dal upstream'in GERİSİNDEYSE 'ff-only' sinyali doğar.

        Bu, 2026-09-28'de ÖLÇÜLEN gerçek durumdu: yerel reword-working
        origin'inin 6 commit gerisindeydi.
        """
        self.repo.branch("local", "HEAD")
        self.repo.branch("tip", "HEAD")
        self.repo.checkout("tip")
        self.repo.commit("t.txt", "t", "feat: remote moved")
        self.repo.set_upstream("local", "tip")
        rc, rep = gate.audit(self.repo.path)
        self.assertEqual(rc, 0)
        row = {r["branch"]: r for r in rep["branches"]}["local"]
        self.assertEqual(row["behind"], 1, "local, tip'ten 1 geride")
        self.assertTrue(row["stale_local"])
        self.assertIn("local", rep["stale_locals"])

    def test_diverged_branch_reports_both_signals(self):
        """Ayrışmış dal: behind>0 VE ahead>0 → iki sinyal birden."""
        self.repo.branch("local", "HEAD")
        self.repo.branch("tip", "HEAD")
        self.repo.checkout("tip")
        self.repo.commit("t.txt", "t", "feat: remote")
        self.repo.checkout("local")
        self.repo.commit("l.txt", "l", "feat: local")
        self.repo.set_upstream("local", "tip")
        _, rep = gate.audit(self.repo.path)
        row = {r["branch"]: r for r in rep["branches"]}["local"]
        self.assertEqual(row["behind"], 1)
        self.assertEqual(row["ahead"], 1)
        self.assertTrue(row["stale_local"])
        self.assertTrue(row["unpushed"])

    def test_branch_without_upstream_produces_no_signal(self):
        rc, rep = gate.audit(self.repo.path)
        self.assertEqual(rc, 0)
        for row in rep["branches"]:
            if not row["upstream"]:
                self.assertFalse(row["unpushed"])
                self.assertFalse(row["stale_local"])
                self.assertIsNone(row["behind"])
                self.assertIsNone(row["ahead"])

    def test_audit_is_ok_on_clean_repo(self):
        rc, rep = gate.audit(self.repo.path)
        self.assertEqual(rc, 0)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["stale_locals"], [])
        self.assertEqual(rep["unpushed_branches"], [])


class CliTest(Base):
    """CLI sözleşmesi: rc 0/1/2 ve --json."""

    def test_json_pair_mode(self):
        self.repo.branch("work", "HEAD")
        self.repo.checkout("work")
        self.repo.commit("w.txt", "w", "feat: work")
        rc = gate.main(["main", "work", "--root", self.repo.path, "--json"])
        self.assertEqual(rc, 0)

    def test_json_audit_mode_shape(self):
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "_calisma", "CIKTI",
                                          "check_merge_precondition.py"),
             "--root", self.repo.path, "--json"],
            capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["mode"], "audit")
        for key in ("branches", "unpushed_branches", "stale_locals"):
            self.assertIn(key, payload)

    def test_single_positional_is_usage_error(self):
        self.assertEqual(gate.main(["main"]), 2)

    def test_three_positionals_is_argparse_usage_error(self):
        """argparse fazla konumsalda SystemExit(2) atar — rc sözleşmesi aynı."""
        with self.assertRaises(SystemExit) as ctx:
            gate.main(["main", "work", "third"])
        self.assertEqual(ctx.exception.code, 2)

    def test_strict_no_op_is_rc1_advisory_is_rc0(self):
        self.repo.branch("work", "HEAD")
        self.repo.commit("c.txt", "c", "feat: later")
        self.assertEqual(gate.main(["main", "work", "--root", self.repo.path]), 0)
        self.assertEqual(
            gate.main(["main", "work", "--root", self.repo.path, "--strict"]), 1)

    def test_unresolvable_source_renders_no_verdict(self):
        """ÖlçüleMEYEN iş PASS/FAIL olarak BASILMAZ (regresyon kilidi).

        Ölçüldü (2026-09-28): çözülemeyen kaynak ref'inde kapı doğru rc=2
        döndü ama render yine "PASS: birleşim işe yarar (None commit
        geliyor)" yazıyordu — bir CI günlüğünde ÖLÇÜLEMEN iş BAŞARILI
        görünürdü. Çıkış kodu tek başına yetmez: insan-okunur yüz de aynı
        sözleşmeye bağlıdır.
        """
        import contextlib
        import io as _io

        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gate.main(["main", "silinmis-dal-xyz", "--root",
                            self.repo.path])
        text = buf.getvalue()
        self.assertEqual(rc, 2, "ölçülemezse rc 2 (fail-closed)")
        self.assertNotIn(
            "PASS:", text,
            "ölçülemeyen işe PASS basıldı — kör yeşil:\n%s" % text)
        self.assertIn("ÖLÇÜLEMEDİ", text)

    def test_unresolvable_source_is_not_reported_as_no_op(self):
        """Çözülemeyen ref 'no-op' da sayılmaz — ölçüm yoksa iddia da yok."""
        rc, report = gate.precondition("main", "yok-boyle-dal", self.repo.path)
        self.assertEqual(rc, 2)
        self.assertFalse(report["no_op"],
                         "ölçülemeyen çift no-op SAYILAMAZ")
        self.assertIsNone(report["incoming"])

    def test_render_mentions_evidence_when_no_op(self):
        self.repo.branch("work", "HEAD")
        self.repo.commit("c.txt", "c", "feat: later")
        _, rep = gate.precondition("main", "work", self.repo.path)
        text = "\n".join(gate.render(rep))
        self.assertIn("NO-OP", text)
        self.assertIn("merge-base", text)

    def test_subject_cli_runs_and_returns_zero(self):
        self.repo.branch("work", "HEAD")
        self.repo.commit("w.txt", "w", "feat: brand new thing")
        rc = gate.main(["main", "work", "--root", self.repo.path,
                        "--subject", "brand new thing"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
