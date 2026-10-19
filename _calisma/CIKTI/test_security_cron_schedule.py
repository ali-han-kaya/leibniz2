#!/usr/bin/env python3
"""test_security_cron_schedule.py — haftalık güvenlik cron'u sözleşme kapısı.

R4 kaydı (docs/FULL_SCOPE_AUDIT_2026-09-17.md) "PR #52 merge'i ile cron'un
fiilen haftalık ateşlenmesi canlanır" diyordu. Ölçüm (2026-10-02):

  * PR #52 merge: 2026-09-30T22:19:48Z -> `8314fde4a4`
  * `docker-security.yml` main'de `schedule: cron "43 3 * * 1"` içeriyor,
    GitHub API `state=active` -> cron TETİKLENEBİLİR
  * ama `event=schedule` tetikli koşum sayısı 0; ilk ateşleme
    2026-10-05T03:43Z (Pzt) -> henüz GERÇEKLEŞMEDİ
  * kontrol: `determinism-trend` aynı repoda schedule ile 2 kez ateşlendi
    (2026-09-21 failure, 2026-09-28 success) -> mekanizma sağlam

Bu test, "tetiklenebilir" (ölçülebilir, şimdi doğru) ile "ateşlendi"
(ölçülemez, henüz olmadı) ayrımını prose'a bırakmaz:

  1) cron ifadesi workflow'ta birebir durur ve 5 alanlıdır — haftanın
     gün alanı yanlış yazılırsa (`* 3 * * 1` gibi) cron HİÇ ateşlenmez
     ve kimse fark etmez; bu sessiz sönüklüğü kapatır.
  2) `next_fire()` gerçekten Pzt 03:43 UTC verir — birkaç referans
     tarihten, hafta sonu sınırında da.
  3) denetim kaydı "ateşlendi" gibi okunamaz: ilk ateşleme tarihini
     BEKLENMEKTE olarak adlandırır ve kanıt olarak schedule koşum sayısı
     (0) yazar. Kayıt olmuş ama olmamış bir şeyi olmuş gibi gösteremez.
  4) kayıt, ilk ateşlemeyi PR #52 merge'inden sonraki ilk Pazartesi olarak
     adlandırır — merge tarihi kayarsa kayıt kırılır.

OFFLINE, stdlib-only. GitHub'a sorgu atmaz (ağ yok): iddia, kayıtta
YAZILI olan ölçümleri doğrular — canlı koşum kanıtı docs/ci_simulate/
ve run id'leriyle gelir, `verified_schedule_run_id` alanına yazılır.
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


def next_fire(after: datetime, expr: str = EXPECTED_CRON) -> datetime:
    """Verilen 5 alanlı cron'dan sonraki ateşlemeyi döndürür.

    Yalnız bu cron'un biçimini destekler (dakika saat * * gün-dizisi) —
    genel bir cron ayrıştırıcısı değildir; desteklenmeyen alanlar
    ValueError ile reddedilir (sessizce yanlış ateşleme üretmez).
    """
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"5 alanlı cron beklenir, {len(parts)} alan: {expr!r}")
    minute, hour, dom, month, dow = parts
    if dom != "*" or month != "*":
        raise ValueError(f"desteklenmeyen cron alanı: {expr!r}")
    if not minute.isdigit() or not hour.isdigit():
        raise ValueError(f"sayısal olmayan alan: {expr!r}")
    if not dow.isdigit():
        raise ValueError(f"hafta günü alanı sayı olmalı: {expr!r}")
    minute_i, hour_i, dow_i = int(minute), int(hour), int(dow)
    if not (0 <= minute_i < 60 and 0 <= hour_i < 24 and 0 <= dow_i < 7):
        raise ValueError(f"cron alanı aralık dışı: {expr!r}")

    # git-cron hafta günü: 0=Pazar .. 6=Cumartesi; python: 0=Pzt .. 6=Paz
    target_py = (dow_i + 6) % 7
    cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    cur = cur.replace(hour=hour_i, minute=minute_i)
    for _ in range(8):  # bir haftadan fazlasına bakmaya gerek yok
        if cur.weekday() == target_py and cur > after:
            return cur
        cur += timedelta(days=1)
    raise AssertionError(f"7 gün içinde ateşleme bulunamadı: {expr!r} @ {after}")


class TestCronExpression(unittest.TestCase):
    def test_workflow_declares_the_documented_cron(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        m = re.search(r"^\s*cron:\s*[\"']([^\"']+)[\"']\s*$", text, re.M)
        self.assertIsNotNone(m, "docker-security.yml'de `cron:` kaydı yok")
        self.assertEqual(m.group(1).strip(), EXPECTED_CRON)

    def test_cron_has_a_weekday_field(self):
        # Sessiz sönüklük: yanlış yazılan gün alanı cron'u HİÇ tetiklemez
        # ve push koşumları yeşil görünürken haftalık tarama hiç olmaz.
        self.assertEqual(len(EXPECTED_CRON.split()), 5)
        self.assertEqual(EXPECTED_CRON.split()[4], "1")  # Pazartesi

    def test_next_fire_is_monday_0343_utc(self):
        for ref in ("2026-10-01T00:00:00", "2026-10-02T18:00:00",
                    "2026-10-04T23:59:00", "2026-10-05T03:42:59",
                    "2026-10-05T03:43:00"):
            r = datetime.fromisoformat(ref).replace(tzinfo=timezone.utc)
            got = next_fire(r)
            self.assertEqual(got.weekday(), 0, f"{ref} -> {got} Pazartesi değil")
            self.assertEqual((got.hour, got.minute), (3, 43), f"{ref} -> {got}")

    def test_first_fire_is_the_first_monday_after_the_merge(self):
        self.assertEqual(next_fire(MERGE_AT), FIRST_FIRE)

    def test_unsupported_cron_is_rejected_not_guessed(self):
        for bad in ("43 3 *", "43 3 * * 1 *", "x 3 * * 1", "43 3 5 * 1",
                    "43 3 * * 9", "70 3 * * 1"):
            with self.assertRaises(ValueError, msg=f"{bad} reddedilmedi"):
                next_fire(MERGE_AT, bad)


class TestAuditRecord(unittest.TestCase):
    def setUp(self):
        self.row = next(
            (ln for ln in AUDIT.read_text(encoding="utf-8").splitlines()
             if ln.startswith("| R4 ")),
            None,
        )
        self.assertIsNotNone(self.row, "R4 satırı bulunamadı")

    def test_row_names_the_cron_expression(self):
        self.assertIn("43 3 * * 1", self.row)

    def test_row_does_not_claim_the_cron_already_fired(self):
        # Kanıtlanmamış kapanış: kayıt "ateşlendi/canlandı" derse ve
        # schedule koşum sayısını 0 yazmazsa, denetim okuyan biri olmuş
        # sanır — ölçülmemiş bir şey kapatılmış gibi görünür.
        self.assertIn("henüz ateşlenmedi", self.row)
        self.assertIn("schedule", self.row)

    def test_row_records_zero_schedule_runs_and_a_pending_first_fire(self):
        self.assertRegex(self.row, r"schedule tetikli koşum sayısı \*\*0\*\*")
        self.assertIn("2026-10-05T03:43Z", self.row)

    def test_row_names_the_merge_that_armed_it(self):
        self.assertIn("2026-09-30T22:19:48Z", self.row)
        self.assertIn("8314fde4a4", self.row)

    def test_row_records_the_working_control(self):
        # Mekanizmanın sağlam olduğunun tek doğrudan kanıtı: aynı repoda
        # başka bir workflow schedule ile ateşlenmiş. Bunu silmek, cron'un
        # sessizce hiç çalışmadığını düşünmeye yol açardı.
        self.assertIn("determinism-trend", self.row)


if __name__ == "__main__":
    unittest.main()