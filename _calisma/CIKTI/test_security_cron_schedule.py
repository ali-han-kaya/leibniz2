#!/usr/bin/env python3
"""test_security_cron_schedule.py — haftalık güvenlik cron'u sözleşme kapısı.

R4 kaydı (docs/FULL_SCOPE_AUDIT_2026-09-17.md) "PR #52 merge'i ile cron'un
fiilen haftalık ateşlenmesi canlanır" diyordu. Ölçüm (2026-10-02):

  * PR #52 merge: 2026-09-30T22:19:48Z -> `8314fde4a4`
  * `docker-security.yml` main'de `schedule: cron "43 3 * * 1"` içeriyor,
    GitHub API `state=active` -> cron TETIKLENEBILIR
  * ilk ateşleme 2026-10-05T03:43Z (Pzt); 2026-10-31'de `--limit 100`
    penceresi hâlâ 0 gösteriyordu (tarihsel kayıt)
  * 2026-11-01 `--event schedule` yenilemesi: 4 koşum — 2026-10-05
    failure, 2026-10-12 success, 2026-10-19 success, 2026-10-26 failure

Bu test, "tetiklenebilir" ile "ateşlendi" ayrımını prose'a bırakmaz:

  1) cron ifadesi workflow'ta birebir durur ve 5 alanlıdır — haftanın gün
     alanı yanlış yazılırsa cron HIC ateşlenmez ve push koşumları yeşil
     görünürken haftalık tarama hiç olmaz; bu sessiz sönüklüğü kapatır.
  2) `next_fire()` gerçekten Pzt 03:43 UTC verir — hafta sonu sınırında da.
  3) tarihsel "henüz ateşlenmedi / schedule 0" ölçümü kayıtta KORUNUR;
     güncel 4 schedule koşumu ve ilk koşum id'si de kayıtta adlandırılır.
     Böylece eski ölçüm silinmez, yeni ölçüm de görünür olur.
  4) kayıt, ilk ateşlemeyi PR #52 merge'inden sonraki ilk Pazartesi olarak
     adlandırır — merge tarihi kayarsa kayıt kırılır.

OFFLINE, stdlib-only. GitHub'a sorgu atmaz: iddia, kayıtta YAZILI olan
ölçümleri doğrular. Canlı koşum kanıtı run id'siyle gelir.
"""
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security.yml"
AUDIT = ROOT / "docs" / "FULL_SCOPE_AUDIT_2026-09-17.md"

EXPECTED_CRON = "43 3 * * 1"
MERGE_AT = datetime(2026, 9, 30, 22, 19, 48, tzinfo=timezone.utc)
FIRST_FIRE = datetime(2026, 10, 5, 3, 43, tzinfo=timezone.utc)


def next_fire(after, expr=EXPECTED_CRON):
    """Verilen 5 alanlı cron'dan sonraki ateşlemeyi döndürür.

    Yalnız bu cron'un biçimini destekler (dakika saat * * gün-dizisi); genel
    bir cron ayrıştırıcısı değildir. Desteklenmeyen alanlar ValueError ile
    reddedilir — sessizce yanlış ateşleme üretmez.
    """
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("5 alanlı cron beklenir, %d alan: %r" % (len(parts), expr))
    minute, hour, dom, month, dow = parts
    if dom != "*" or month != "*":
        raise ValueError("desteklenmeyen cron alanı: %r" % expr)
    if not minute.isdigit() or not hour.isdigit() or not dow.isdigit():
        raise ValueError("sayısal olmayan alan: %r" % expr)
    minute_i, hour_i, dow_i = int(minute), int(hour), int(dow)
    if not (0 <= minute_i < 60 and 0 <= hour_i < 24 and 0 <= dow_i < 7):
        raise ValueError("cron alanı aralık dışı: %r" % expr)

    target_py = (dow_i + 6) % 7   # git-cron 0=Pazar -> python 0=Pzt
    cur = after.replace(second=0, microsecond=0, hour=hour_i, minute=minute_i)
    if cur <= after:
        cur += timedelta(days=1)
    while cur.weekday() != target_py:
        cur += timedelta(days=1)
    return cur


class TestCronExpression(unittest.TestCase):
    def test_workflow_declares_the_documented_cron(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        # YAML liste öğesi: `    - cron: "43 3 * * 1"` — tire de kabul edilir.
        m = re.search(r"^\s*(?:-\s*)?cron:\s*[\"']([^\"']+)[\"']\s*$", text, re.M)
        self.assertIsNotNone(m, "docker-security.yml'de `cron:` kaydı yok")
        self.assertEqual(m.group(1).strip(), EXPECTED_CRON)

    def test_cron_has_a_weekday_field(self):
        # Sessiz sönüklük: yanlış yazılan gün alanı cron'u HIC tetiklemez.
        self.assertEqual(len(EXPECTED_CRON.split()), 5)
        self.assertEqual(EXPECTED_CRON.split()[4], "1")   # Pazartesi

    def test_next_fire_is_monday_0343_utc(self):
        for ref in ("2026-10-01T00:00:00", "2026-10-02T18:00:00",
                    "2026-10-04T23:59:00", "2026-10-05T03:42:59",
                    "2026-10-05T03:43:00"):
            r = datetime.fromisoformat(ref).replace(tzinfo=timezone.utc)
            got = next_fire(r)
            self.assertEqual(got.weekday(), 0, "%s -> %s Pazartesi degil" % (ref, got))
            self.assertEqual((got.hour, got.minute), (3, 43), "%s -> %s" % (ref, got))

    def test_first_fire_is_the_first_monday_after_the_merge(self):
        self.assertEqual(next_fire(MERGE_AT), FIRST_FIRE)

    def test_unsupported_cron_is_rejected_not_guessed(self):
        for bad in ("43 3 *", "43 3 * * 1 *", "x 3 * * 1", "43 3 5 * 1",
                    "43 3 * * 9", "70 3 * * 1"):
            with self.assertRaises(ValueError, msg="%s reddedilmedi" % bad):
                next_fire(MERGE_AT, bad)


class TestAuditRecord(unittest.TestCase):
    def setUp(self):
        self.row = next(
            (ln for ln in AUDIT.read_text(encoding="utf-8").splitlines()
             if ln.startswith("| R4 ")), None)
        self.assertIsNotNone(self.row, "R4 satırı bulunamadı")

    def test_row_names_the_cron_expression(self):
        self.assertIn("43 3 * * 1", self.row)

    def test_row_preserves_the_historical_zero_measurement(self):
        # Tarihli kayıt silinmez: 2026-10-31'de `--limit 100` penceresi 0
        # gösteriyordu; bu, güncel 4 koşumun kanıtını gizlememeli.
        self.assertIn("henüz ateşlenmedi", self.row)
        self.assertIn("schedule", self.row)

    def test_row_preserves_historical_zero_and_pending_first_fire(self):
        self.assertIn("tetikli koşum sayısı **0**", self.row)
        self.assertIn("2026-10-05T03:43Z", self.row)

    def test_row_records_the_four_observed_schedule_runs(self):
        self.assertIn("2026-11-01 `--event schedule` yenilemesi: 4 koşum", self.row)
        for run_id in ("37299256892", "38242006582", "39229134880",
                       "40299014424"):
            self.assertIn(run_id, self.row)
        self.assertIn("libssl3", self.row)
        self.assertIn("CVE-2026-84782", self.row)

    def test_row_names_the_merge_that_armed_it(self):
        self.assertIn("2026-09-30T22:19:48Z", self.row)
        self.assertIn("8314fde4a4", self.row)

    def test_row_records_the_working_control(self):
        # Mekanizmanın sağlam olduğunun tek doğrudan kanıtı: aynı repoda
        # başka bir workflow schedule ile ateşlenmiş.
        self.assertIn("determinism-trend", self.row)


if __name__ == "__main__":
    unittest.main()
