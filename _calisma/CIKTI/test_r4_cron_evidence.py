#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_r4_cron_evidence.py — R4 cron-kanıtı bekçisinin sözleşmesi.

Kök-neden (ölçüldü, 2026-10-31): R4 satırının en kritik iddiası — "GitHub'ın
kendi `schedule` tetiklemesi oldu mu?" — birinin `gh run list` çağırmayı
hatırlamasına bağlıydı. Satır "ilk ateşleme 2026-10-05" diyordu; dört
Pazartesi geçti, `event=schedule` sayısı 0 kaldı ve hiçbir koşum kırmızıya
dönmedi (tetiklenmeyen cron kırmızı bir koşum üretmez, yalnız sessizlik
üretir). Bekçi (`.github/workflows/docker-security-cron-evidence.yml` +
`r4_cron_evidence.py`) o sessizliği ölçülebilir hâle getirir ve kanıtı R4
satırına yazar.

Bu dosya bekçinin iddialarını çiviler; hepsi OFFLINE ve stdlib-only:

  K1 SEÇİM: cron kanıtı YALNIZ `event=schedule` koşumudur. Push / PR /
     dispatch koşumu aynı işi koşsa da tetikleyici farklıdır — "elle koştum,
     cron çalışıyor" yanılgısı runbook'ta da yasaklanmıştır. Armed tarihten
     (PR #52 sonrası ilk Pzt) ÖNCEKİ schedule koşumu da bu tick'in kanıtı
     değildir.
  K2 HÜKÜM: üç durum + fail-closed çıkış kodları. "Bekleme penceresi" (yeşil)
     ile "tick geçti, koşum yok" (KIRMIZI) karıştırılamaz; fired ama
     conclusion=success DEĞİL ise yine KIRMIZI (cron ateşlendi, kapı düştü).
  K3 ÖLÇÜLEMEDİ ≠ YEŞİL: gh yok / bozuk JSON / işaretler eksik → rc 2 ve
     satıra HİÇBİR ŞEY yazılmaz. Sessiz "temiz" yok.
  K4 YAZMA: kanıt R4 satırındaki İŞARETLİ parçaya yazılır; satırın gövdesi
     (tarihli ölçümler, merge hash'i, cron ifadesi) DEĞİŞMEZ. İşaretler
     tekil değilse yazma reddedilir — sessizce ikinci bir parça eklemek
     "hangi hüküm geçerli?" sorusunu cevapsız bırakır.
  K5 İDEMPOTANS: aynı hüküm (durum, run id, conclusion) tekrar yazılmaz;
     ölçüm saati kimliğe girmez (girseydi nöbet her hafta boşuna PR açardı).
  K6 WORKFLOW: bekçi cron'u beklenen tick'ten SONRA ve diğer haftalık
     cron'larla çakışmadan koşar; mantık YAML'da yeniden yazılmaz (tek giriş
     noktası script, `run:` adımı); kayıt satırı ile kırmızı AYRI adımlardır
     ("kaydettim ama yeşil" sessiz başarı olurdu).
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import r4_cron_evidence as r4  # noqa: E402
import ci_hygiene_gate  # noqa: E402

DOC = ROOT / "docs" / "FULL_SCOPE_AUDIT_2026-09-17.md"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security-cron-evidence.yml"
DOCKER_WF = ROOT / ".github" / "workflows" / "docker-security.yml"


def ts(value):
    return r4.parse_ts(value)


def run(rid, created, event="schedule", status="completed", conclusion="success",
        url=""):
    return r4.Run(id=str(rid), created=ts(created), event=event, status=status,
                  conclusion=conclusion, url=url)


def gh_item(rid, created, event="schedule", status="completed",
            conclusion="success"):
    """`gh run list --json …` biçimindeki ham kayıt."""
    return {"databaseId": rid, "createdAt": created, "event": event,
            "status": status, "conclusion": conclusion,
            "url": "https://github.com/o/r/actions/runs/%s" % rid}


TICK = "2026-10-05T03:43:00Z"
AFTER_TICK = "2026-10-05T10:51:00Z"
AFTER_DEADLINE = "2026-10-06T05:17:00Z"
BEFORE_DEADLINE = "2026-10-05T12:00:00Z"


class TestScheduleRunSelection(unittest.TestCase):
    """K1 — cron kanıtı yalnız `schedule` koşumudur."""

    def test_dispatch_and_push_runs_are_not_cron_evidence(self):
        runs = [run(1, AFTER_TICK, event="workflow_dispatch"),
                run(2, AFTER_TICK, event="push"),
                run(3, AFTER_TICK, event="pull_request")]
        picked, scheduled = r4.select_first_scheduled(runs, ts(TICK))
        self.assertIsNone(picked,
                          "dispatch/push/PR koşumu cron kanıtı sayılmamalı — "
                          "aynı işi koşsalar da tetikleyici farklıdır")
        self.assertEqual(scheduled, 0)

    def test_earliest_schedule_run_after_the_tick_wins(self):
        runs = [run(30, "2026-10-19T09:19:00Z"),
                run(10, AFTER_TICK),
                run(20, "2026-10-12T11:20:00Z")]
        picked, scheduled = r4.select_first_scheduled(runs, ts(TICK))
        self.assertEqual(picked.id, "10", "ilk tick'in koşumu seçilmeli (en erken)")
        self.assertEqual(scheduled, 3)

    def test_schedule_run_before_the_armed_date_is_not_this_ticks_evidence(self):
        # Armed tarih PR #52 merge'i (2026-09-30) sonrası ilk Pazartesi'dir;
        # ondan önceki bir schedule koşumu bu tick'i kanıtlamaz.
        runs = [run(5, "2026-09-28T03:43:00Z")]
        picked, scheduled = r4.select_first_scheduled(runs, ts(TICK))
        self.assertIsNone(picked,
                          "armed tarihten önceki schedule koşumu bu tick'in "
                          "kanıtı değildir (ama sayımda görünür)")
        self.assertEqual(scheduled, 1)

    def test_tie_break_is_deterministic(self):
        a = run(7, AFTER_TICK)
        b = run(9, AFTER_TICK)
        self.assertEqual(r4.select_first_scheduled([b, a], ts(TICK))[0].id,
                         r4.select_first_scheduled([a, b], ts(TICK))[0].id,
                         "aynı created_at'te sıra girdi sırasına bağlı olmamalı")


class TestVerdictStates(unittest.TestCase):
    """K2 — üç durum ve fail-closed çıkış kodları."""

    def test_pending_before_the_hard_deadline_is_green(self):
        v = r4.measure([], ts(BEFORE_DEADLINE))
        self.assertEqual(v.state, "pending")
        self.assertEqual(v.exit_code(), 0,
                         "sert bitişten önce koşum yokluğu HATA değildir")

    def test_missed_after_the_hard_deadline_is_red(self):
        v = r4.measure([], ts(AFTER_DEADLINE))
        self.assertEqual(v.state, "missed")
        self.assertEqual(v.exit_code(), 1,
                         "tick + sert bitiş geçti ve schedule koşumu yok → KIRMIZI "
                         "(sessiz yeşil, R4'ün açık kalan tek şartını gizlerdi)")

    def test_deadline_boundary_flips_pending_to_missed(self):
        self.assertEqual(r4.measure([], ts("2026-10-05T23:42:00Z")).state, "pending")
        self.assertEqual(r4.measure([], ts("2026-10-05T23:43:00Z")).state, "missed")

    def test_fired_success_is_green(self):
        v = r4.measure([run(11, AFTER_TICK)], ts(AFTER_DEADLINE))
        self.assertEqual(v.state, "fired")
        self.assertEqual(v.exit_code(), 0)

    def test_fired_failure_is_red(self):
        v = r4.measure([run(11, AFTER_TICK, conclusion="failure")],
                       ts(AFTER_DEADLINE))
        self.assertEqual(v.state, "fired")
        self.assertEqual(v.exit_code(), 1,
                         "cron ateşlendi ama kapı düştü → bu gerçek sinyaldir, "
                         "kanıt yazılır ama koşum KIRMIZI olur")

    def test_fired_without_conclusion_is_not_evidence_of_success(self):
        v = r4.measure([run(11, AFTER_TICK, status="in_progress", conclusion=None)],
                       ts(AFTER_DEADLINE))
        self.assertEqual(v.state, "fired")
        self.assertEqual(v.exit_code(), 1,
                         "conclusion yokken PASS verilemez (henüz kanıtlanmadı)")

    def test_non_positive_deadline_is_a_measurement_error(self):
        with self.assertRaises(r4.Unmeasured):
            r4.measure([], ts(AFTER_DEADLINE), deadline_hours=0)

    def test_naive_timestamps_are_rejected(self):
        for bad in ("2026-10-05T03:43:00", "", "yarın"):
            with self.subTest(value=bad):
                with self.assertRaises(r4.Unmeasured):
                    r4.parse_ts(bad)

    def test_malformed_run_payload_fails_closed(self):
        for payload in ({"nope": []}, 42, [{"event": "schedule"}]):
            with self.subTest(payload=payload):
                with self.assertRaises(r4.Unmeasured):
                    r4.normalize_runs(payload)


class TestSegmentRendering(unittest.TestCase):
    """K2/K4 — metin, hücre sınırını bozmadan hükmü taşır."""

    def _states(self):
        return {
            "pending": r4.measure([], ts(BEFORE_DEADLINE)),
            "missed": r4.measure([], ts(AFTER_DEADLINE)),
            "fired": r4.measure([run(4242, AFTER_TICK)], ts(AFTER_DEADLINE)),
        }

    def test_segment_names_the_watchdog_and_the_measurement_time(self):
        for state, v in self._states().items():
            with self.subTest(state=state):
                seg = r4.render_segment(v)
                self.assertIn(r4.WATCHDOG_WORKFLOW, seg,
                              "parça hangi akışın yazdığını söylemeli")
                self.assertIn(r4.fmt(v.as_of), seg,
                              "parça ölçüm anını taşımalı (kanıtın tarihi)")

    def test_segment_never_contains_a_cell_separator(self):
        for state, v in self._states().items():
            with self.subTest(state=state):
                self.assertNotIn("|", r4.render_segment(v),
                                 "tablo hücresinde `|` hücreyi böler — satır "
                                 "yapısı sessizce bozulur")

    def test_pending_and_missed_are_lexically_distinct(self):
        segs = self._states()
        pending = r4.render_segment(segs["pending"])
        missed = r4.render_segment(segs["missed"])
        self.assertIn("henüz GEÇMEDİ", pending)
        self.assertIn("**GEÇTİ**", missed)
        self.assertNotEqual(pending, missed,
                            "iki durum aynı metne düşerse okur hangisinin "
                            "geçerli olduğunu anlayamaz")

    def test_missed_segment_states_the_measured_zero(self):
        seg = r4.render_segment(self._states()["missed"])
        self.assertIn("**0**", seg)
        self.assertIn(r4.fmt(ts(TICK)), seg,
                      "hangi tick'in beklendiği yazılı olmalı")

    def test_fired_segment_carries_the_run_identity(self):
        seg = r4.render_segment(self._states()["fired"])
        for needle in ("**KANITLANDI**", "`4242`", "2026-10-05T10:51Z",
                       "conclusion `success`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, seg,
                              "kanıt satırı run kimliğini taşımalı: %s" % needle)


class TestRowWrite(unittest.TestCase):
    """K4 — yazma yalnız işaretli parçaya dokunur."""

    BODY = ("| R4 | risk | kapı | desen: cron `43 3 * * 1`; henüz ateşlenmedi; "
            "tetikli koşum sayısı **0** |")
    SEG = r4.SEGMENT_START + "eski parça" + r4.SEGMENT_END
    DOC_TEXT = "# Denetim\n\n| Kimlik | Risk |\n|---|---|\n" + BODY[:-2] + " " + SEG + " |\n\nson satır\n"

    def test_write_replaces_only_the_marked_segment(self):
        new = r4.write_segment(self.DOC_TEXT, "yeni parça")
        self.assertIn("yeni parça", new)
        self.assertNotIn("eski parça", new)
        self.assertIn("desen: cron `43 3 * * 1`; henüz ateşlenmedi", new,
                      "satırın gövdesi (tarihli ölçümler) korunmalı")
        self.assertIn("\n\nson satır\n", new,
                      "belgenin geri kalanı bayt bayt korunmalı")
        self.assertEqual(len(new.splitlines()), len(self.DOC_TEXT.splitlines()),
                         "yazma satır sayısını değiştirmemeli (tablo bozulmaz)")

    def test_missing_markers_are_refused(self):
        text = "# Denetim\n\n" + self.BODY + "\n"
        with self.assertRaises(r4.DocContractError):
            r4.write_segment(text, "yeni")
        self.assertEqual(text, "# Denetim\n\n" + self.BODY + "\n",
                         "hata hâlinde belge DEĞİŞMEMELİ")

    def test_duplicate_markers_are_refused(self):
        text = self.DOC_TEXT.replace(
            self.SEG, self.SEG + " " + r4.SEGMENT_START + "ikinci" + r4.SEGMENT_END)
        with self.assertRaises(r4.DocContractError):
            r4.write_segment(text, "yeni")

    def test_missing_row_is_refused(self):
        with self.assertRaises(r4.DocContractError):
            r4.write_segment("# boş belge\n", "yeni")

    def test_two_r4_rows_are_refused(self):
        text = self.DOC_TEXT + "\n| R4 | ikinci satır | x | y |\n"
        with self.assertRaises(r4.DocContractError):
            r4.write_segment(text, "yeni")


class TestIdempotence(unittest.TestCase):
    """K5 — aynı hüküm iki kez yazılmaz (haftalık PR gürültüsü yok)."""

    def _doc(self):
        seg = r4.render_segment(r4.measure([], ts(AFTER_DEADLINE)))
        line = ("| R4 | risk | kapı | gövde metni " + r4.SEGMENT_START + seg
                + r4.SEGMENT_END + " |")
        return "| Kimlik | Risk |\n|---|---|\n" + line + "\n"

    def test_same_verdict_with_a_new_measurement_clock_writes_nothing(self):
        doc = self._doc()
        later = r4.measure([], ts("2026-10-13T05:17:00Z"))
        new, changed = r4.apply_verdict(doc, later)
        self.assertFalse(changed,
                         "ölçüm saati değişti diye satır yeniden yazılmamalı")
        self.assertEqual(new, doc)

    def test_state_change_rewrites_the_segment(self):
        doc = self._doc()
        fired = r4.measure([run(777, AFTER_TICK)], ts(AFTER_DEADLINE))
        new, changed = r4.apply_verdict(doc, fired)
        self.assertTrue(changed)
        self.assertIn("**KANITLANDI**", new)
        self.assertIn("`777`", new)
        self.assertIn("gövde metni", new, "gövde korunmalı")

    def test_unparsable_segment_is_replaced_not_preserved(self):
        # Fail-closed: tanınmayan bir parça sessizce korunmaz — ölçümle değişir.
        doc = self._doc().replace("**GEÇTİ**", "elle yazılmış serbest metin")
        fired = r4.measure([run(778, AFTER_TICK)], ts(AFTER_DEADLINE))
        new, changed = r4.apply_verdict(doc, fired)
        self.assertTrue(changed)
        self.assertIn("`778`", new)


class TestRealDocContract(unittest.TestCase):
    """Gerçek R4 satırı: parça tekil, hükmü okunur, tarihli ölçümler korunur."""

    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")
        cls.row = next((ln for ln in cls.text.splitlines()
                        if ln.startswith(r4.ROW_PREFIX)), None)

    def test_row_exists_and_is_a_single_four_cell_row(self):
        self.assertIsNotNone(self.row, "R4 satırı yok")
        self.assertEqual(self.row.count("|"), 5,
                         "R4 satırı 4 hücreli tek tablo satırı olmalı (parça "
                         "`|` içerirse hücre bölünür)")

    def test_segment_markers_are_present_exactly_once(self):
        self.assertEqual(self.row.count(r4.SEGMENT_START), 1)
        self.assertEqual(self.row.count(r4.SEGMENT_END), 1)

    def test_segment_carries_a_recognised_verdict(self):
        identity = r4.segment_identity(r4.read_segment(self.row))
        self.assertIsNotNone(identity,
                             "parça tanınmış bir hüküm taşımalı — okunamayan "
                             "parça 'hangi hüküm geçerli?' sorusunu bırakır")
        self.assertIn(identity[0], r4.STATES)

    def test_segment_names_the_watchdog_workflow(self):
        seg = r4.read_segment(self.row)
        self.assertIn(r4.WATCHDOG_WORKFLOW, seg,
                      "okur, kanıtı hangi akışın yazdığını görebilmeli")

    def test_historical_measurements_are_not_replaced_by_the_machine_segment(self):
        # `test_security_cron_schedule.py` bu iki ölçümü pin'ler; makine
        # parçası onları SİLEMEZ (tarihli kayıt, kanıtın kendisidir).
        for needle in ("henüz ateşlenmedi", "tetikli koşum sayısı **0**",
                       "43 3 * * 1", "8314fde4a4"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.row)

    def test_module_default_doc_is_the_audited_document(self):
        self.assertEqual(r4.DEFAULT_DOC.resolve(), DOC.resolve(),
                         "betiğin varsayılan belgesi denetim satırının "
                         "bulunduğu dosya olmalı (tek kaynak)")

    def test_expected_tick_matches_the_pinned_first_fire(self):
        # `test_security_cron_schedule.FIRST_FIRE` ile aynı an olmalı.
        self.assertEqual(r4.EXPECTED_FIRST_TICK,
                         datetime(2026, 10, 5, 3, 43, tzinfo=timezone.utc))


class TestCliOffline(unittest.TestCase):
    """K3 — uçtan uca: fixture → hüküm → yazma; ölçülemezse yazma YOK."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.doc = self.dir / "audit.md"
        # Başlangıç parçası = bekleme penceresi (armed sonrası ilk ölçüm).
        seg = r4.render_segment(r4.measure([], ts(BEFORE_DEADLINE)))
        self.doc.write_text(
            "| Kimlik | Risk |\n|---|---|\n"
            "| R4 | risk | kapı | gövde " + r4.SEGMENT_START + seg
            + r4.SEGMENT_END + " |\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _runs(self, items):
        p = self.dir / "runs.json"
        p.write_text(json.dumps(items), encoding="utf-8")
        return str(p)

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, str(HERE / "r4_cron_evidence.py"),
             "--doc", str(self.doc), *args],
            capture_output=True, text=True)

    def test_first_schedule_run_is_detected_and_written(self):
        runs = self._runs([gh_item(4242, AFTER_TICK)])
        r = self._cli("--runs-file", runs, "--now", AFTER_DEADLINE,
                      "--apply", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["state"], "fired")
        self.assertEqual(payload["run_id"], "4242")
        self.assertTrue(payload["changed"])
        text = self.doc.read_text(encoding="utf-8")
        self.assertIn("**KANITLANDI**", text)
        self.assertIn("`4242`", text)
        self.assertIn("gövde", text)

    def test_second_run_with_the_same_verdict_writes_nothing(self):
        runs = self._runs([gh_item(4242, AFTER_TICK)])
        first = self._cli("--runs-file", runs, "--now", AFTER_DEADLINE,
                          "--apply", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.doc.read_text(encoding="utf-8")
        second = self._cli("--runs-file", runs, "--now", "2026-10-13T05:17:00Z",
                           "--apply", "--json")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse(json.loads(second.stdout)["changed"])
        self.assertEqual(self.doc.read_text(encoding="utf-8"), before)

    def test_missing_tick_is_red_and_still_recorded(self):
        runs = self._runs([gh_item(9, AFTER_TICK, event="workflow_dispatch")])
        r = self._cli("--runs-file", runs, "--now", AFTER_DEADLINE,
                      "--apply", "--json")
        self.assertEqual(r.returncode, 1,
                         "schedule koşumu yoksa hüküm KIRMIZI olmalı")
        payload = json.loads(r.stdout)
        self.assertEqual(payload["state"], "missed")
        self.assertIn("**GEÇTİ**", self.doc.read_text(encoding="utf-8"),
                      "kırmızı hüküm de KAYDEDİLİR: 'boş = ölçülmedi' ile "
                      "'❌ ölçüldü' farklı iddialardır")

    def test_before_deadline_nothing_is_written(self):
        before = self.doc.read_text(encoding="utf-8")
        runs = self._runs([])
        r = self._cli("--runs-file", runs, "--now", BEFORE_DEADLINE,
                      "--apply", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(json.loads(r.stdout)["changed"])
        self.assertEqual(self.doc.read_text(encoding="utf-8"), before)

    def test_corrupt_fixture_is_a_measurement_error_without_writing(self):
        before = self.doc.read_text(encoding="utf-8")
        bad = self.dir / "bad.json"
        bad.write_text("{bozuk", encoding="utf-8")
        r = self._cli("--runs-file", str(bad), "--now", AFTER_DEADLINE,
                      "--apply", "--json")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "UNMEASURED")
        self.assertEqual(self.doc.read_text(encoding="utf-8"), before,
                         "ölçülemeyen koşum satıra HİÇBİR ŞEY yazmamalı")

    def test_doc_without_markers_is_red_without_writing(self):
        self.doc.write_text("| R4 | risk | kapı | parça yok |\n", encoding="utf-8")
        before = self.doc.read_text(encoding="utf-8")
        runs = self._runs([gh_item(4242, AFTER_TICK)])
        r = self._cli("--runs-file", runs, "--now", AFTER_DEADLINE,
                      "--apply", "--json")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("işaret", r.stderr)
        self.assertEqual(self.doc.read_text(encoding="utf-8"), before)


class TestWorkflowContract(unittest.TestCase):
    """K6 — bekçi akışının zamanlaması, paritesi ve fail-closed bağlanışı."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def _cron(self):
        m = re.search(r'^\s*- cron:\s*[\'"]([^\'"]+)[\'"]', self.text, re.M)
        self.assertIsNotNone(m, "bekçi workflow'unda cron yok")
        return m.group(1)

    def test_workflow_has_schedule_and_manual_dispatch(self):
        self.assertRegex(self.text, r"(?m)^\s*schedule:",
                         "schedule: tetikleyicisi yok — bekçi kendi kendine "
                         "koşmazsa sessizlik yine görünmez olur")
        self.assertRegex(self.text, r"(?m)^\s*workflow_dispatch:", 
                         "workflow_dispatch yok — kanıt elle yeniden üretilemez")

    def test_cron_runs_after_the_expected_tick_with_slack(self):
        """Bekçi, izlediği tick'ten ÖNCE koşmamalı (yoksa hep 'pending' görür)."""
        import test_gated_schedules as tgs
        guard = tgs.cron_minute_of_week(self._cron())
        watched = tgs.cron_minute_of_week(
            re.search(r'^\s*- cron:\s*"([^"]+)"', DOCKER_WF.read_text(
                encoding="utf-8"), re.M).group(1))
        # Pzt 03:43 → Salı 05:17: fark 24*60 + 94 dakika.
        self.assertGreater(guard - watched, 20 * 60,
                           "bekçi, tick + 20sa sert bitişinden SONRA koşmalı "
                           "(fark %d dk)" % (guard - watched))

    def test_cron_does_not_collide_with_other_scheduled_workflows(self):
        expr = self._cron()
        for wf in sorted(WORKFLOW.parent.glob("*.yml")):
            if wf == WORKFLOW:
                continue
            others = re.findall(r'^\s*- cron:\s*[\'"]([^\'"]+)[\'"]',
                                wf.read_text(encoding="utf-8"), re.M)
            with self.subTest(workflow=wf.name):
                self.assertNotIn(expr, others,
                                 f"{wf.name} aynı cron'u paylaşıyor: {expr}")

    def test_logic_is_delegated_to_the_script_via_run(self):
        # `run: |` blok yazımı: script, `run:` satırının ALTINDA gelir — satır
        # bazlı arama çok satırlı run bloklarını kaçırır (test_gated_schedules
        # da bu yüzden adım bloğu üzerinden ölçer).
        blocks = re.split(r"\n(?=\s*- name:)", self.text)
        callers = [b for b in blocks if "r4_cron_evidence.py" in b
                   and re.search(r"(?m)^\s*run:", b)]
        self.assertTrue(callers,
                        "ölçüm/yazma `r4_cron_evidence.py` adımına delege "
                        "edilmeli (YAML'da yeniden yazılmaz)")
        for block in callers:
            self.assertNotIn("uses:", block,
                             "kapı adımı `uses:` içermemeli — action script'i "
                             "substitute edemez")
            self.assertIn("--apply", block,
                          "adım yalnız ölçmemeli, R4 parçasını YAZMALI")
            self.assertNotIn("continue-on-error", block)
            self.assertIn("GH_TOKEN", block,
                          "gh kimliksiz kalırsa ölçüm hiç başlamaz")

    def test_measurement_failure_is_not_swallowed(self):
        blocks = re.split(r"\n(?=\s*- name:)", self.text)
        # Adımla seçilir: başlık yorumu da script adını ve `run:` sözcüğünü
        # geçirdiği için "içeren blok" araması yanlış bloğu yakalıyordu.
        gate = next((b for b in blocks
                     if b.lstrip().startswith("- name: Measure cron evidence")), "")
        self.assertIn("r4_cron_evidence.py", gate, "kapı adımı bulunamadı")
        self.assertIn('if [ "$rc" -eq 2 ]', gate,
                      "ölçülemedi (rc=2) açıkça ele alınmalı")
        self.assertIn("exit 1", gate,
                      "ölçülemediğinde adım DÜŞMELİ (sessiz PASS yok)")
        self.assertNotRegex(gate, r"\|\|\s*true",
                            "hata yutan `|| true` kapı adımında olamaz")

    def test_record_and_verdict_are_separate_steps(self):
        """Kayıt yeşil, hüküm kırmızı olabilir; tek adımda birleşirse biri kaybolur."""
        blocks = re.split(r"\n(?=\s*- name:)", self.text)
        verdict = [b for b in blocks if "Verdict (fail-closed)" in b]
        self.assertEqual(len(verdict), 1,
                         "hüküm adımı tek ve ayrı olmalı")
        v = verdict[0]
        self.assertIn("if: always()", v,
                      "hüküm, önceki adım düşse de koşmalı (yoksa kırmızı "
                      "görünmez olur)")
        self.assertIn("exit 1", v)
        commit = [b for b in blocks if "Commit R4 segment" in b]
        self.assertEqual(len(commit), 1)
        self.assertIn("changed == 'true'", commit[0],
                      "PR yalnız gerçekten bir şey yazıldıysa açılmalı")

    def test_commit_uses_the_evidence_gap_exempt_prefix(self):
        # `docs(deploy)` → deploy_evidence.DEFAULT_GAP_EXEMPT: kanıt kaydı
        # commit'i kanıt boşluğunu ilerletmez.
        self.assertIn("docs(deploy)", self.text)

    def test_workflow_touches_the_same_document_the_script_defaults_to(self):
        """Bot PR'ı, betiğin yazdığı belgenin AYNISINI stage'lemeli."""
        rel = str(r4.DEFAULT_DOC.relative_to(ROOT))
        self.assertIn("git add %s" % rel, self.text,
                      "stage'lenen belge betiğin varsayılan belgesi değil → "
                      "ölçüm bir dosyaya, PR başka dosyaya yazar")
        self.assertIn("git diff --quiet -- %s" % rel, self.text,
                      "'yazdım' iddiası aynı belge üzerinde doğrulanmalı")

    @unittest.skipIf(ci_hygiene_gate.yaml is None,
                     "PyYAML yok — hijyen kapısı ölçülemiyor")
    def test_ci_hygiene_gate_passes_for_this_workflow(self):
        # Kuralları burada yeniden yazmayız: gerçek kapı çalıştırılır.
        findings = ci_hygiene_gate.findings_for(WORKFLOW.parent)
        mine = [f for f in findings if WORKFLOW.name in f]
        self.assertEqual(mine, [], "CI hijyen kapısı bekçi workflow'unda "
                                   "ihlal buldu: %s" % mine)


if __name__ == "__main__":
    unittest.main()
