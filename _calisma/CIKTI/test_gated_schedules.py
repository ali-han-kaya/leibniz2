#!/usr/bin/env python3
"""test_gated_schedules.py — schedule-tetikli workflow'ların KAPI-PARİTESİ sözleşmesi.

Tarihsel kök-neden (this session, 2026-09-20): docker-security.yml yalnızca
push+dispatch'te koşarken yeni CVE'ler en çok HAZIRLIKSIZ zamanda gelir —
patching doc'unun "Trivy gate kırmızı" döngüsü cron'suz tamamlanamaz. Cron
eklerken iki drift riski ölçüldü:

  1) Job, gate script'ini ÇAĞIRMADAN kendi adımlarıyla akışı yeniden yazar
     (parity kaybı: yerel smoke ↔ CI ayrışır, "birebir yerel karşılığı"
     sözleşmesi sessizce boşalır).
  2) SKIP kuralı runner araçlarına uymaz: ubuntu-latest'te docker+trivy
     YOKTUR — script'in "araç yok → exit 0 SKIP" sözleşmesiyle uyumlu bir
     kurulum satırı yoksa job her hafta SKIP üretir ve kimse fark etmez
     (sessiz kanıt kaybı — cron'un amacıyla çelişir).

Üç kural (fail-closed, offline, stdlib-only):

  K1) schedule: içeren her workflow, repo kapı script'lerinden en az birini
      çağırır (entry'de docker_security_smoke.sh / texlive_determinism_test.sh
      / verify_delivery.py kalıplarından biri).
  K2) cron içeren job'ın adımlarında gate script'i RUN ile çağrılır (uses:
      adımı sayılmaz — action'lar script'i substitute edemez).
  K  3) docker_security_smoke.sh çağıran her schedule job'ı, runner'a trivy
      kuran ya da SKIP sözleşmesini uyumlu belgeleyen bir satır taşır.
  4) Runbook (patching doc) beklenen log desenini KAYNAKTAN türetilmiş
      olarak verir: cron ifadesi, SKIP satırı, evidence başlığı/görüntüsü
      ve fallback notu workflow + script'ten okunur, sonra runbook'ta
      birebir aranır. Kopyalanmış metin DRIFT üretir — kural yazısı
      değişirse runbook da değişmezse kapı kırılır (fail-closed).

OFFLINE, stdlib-only, ~0.02s.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SMOKE = ROOT / "_calisma" / "CIKTI" / "docker_security_smoke.sh"
RUNBOOK = ROOT / "docs" / "DOCKER_SECURITY_PATCHING.md"

RUNBOOK_HEADING = "## Haftalık cron koşumu"
RUNBOOK_END = "## Katkı sözleşmesi"

GATE_SCRIPTS = (
    "docker_security_smoke.sh",
    "texlive_determinism_test.sh",
    "verify_delivery.py",
)


def scheduled_workflows():
    return [p for p in sorted(WORKFLOWS.glob("*.yml"))
            if re.search(r"^\s*schedule:", (p.read_text(encoding="utf-8")), re.M)]


class TestScheduleGateParity(unittest.TestCase):
    """K1+K2: cron job'ları repo kapılarını çağırır — kendi akışını yeniden yazmaz."""

    def test_scheduled_workflows_call_a_gate_script(self):
        wfs = scheduled_workflows()
        self.assertTrue(wfs, "schedule'lı workflow beklenirdi")
        for wf in wfs:
            text = wf.read_text(encoding="utf-8")
            with self.subTest(workflow=wf.name):
                called = [g for g in GATE_SCRIPTS if g in text]
                self.assertTrue(
                    called,
                    f"{wf.name}: schedule'lı workflow kapı script'i çağırmıyor "
                    f"(parity kaybı; beklenenlerden biri: {GATE_SCRIPTS})",
                )

    def test_docker_smoke_cron_job_runs_script_via_run(self):
        """K2: docker_security_smoke.sh bir `run:` adımında çağrılmalı (uses: değil)."""
        text = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        run_lines = re.findall(r"run:.*", text)
        self.assertTrue(
            any("docker_security_smoke.sh" in ln for ln in run_lines),
            "docker-security.yml: smoke script'i `run:` adımında çağrılmalı "
            "(action'lar script'i substitute edemez)",
        )

    def test_docker_smoke_schedule_job_declares_runner_tool_skip(self):
        """K3: cron job'ında trivy kurulu ya da SKIP sözleşmesi runner ile uyumlu."""
        text = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        # SKIP-farkında satır: runner'da docker/trivy yoksa script SKIP üretir
        # (exit 0) — job bunu kasıtlı, görünür semantiyle belgelemeli.
        self.assertIn(
            "SKIP", text,
            "docker-security.yml: runner-araçlarıyla uyumlu SKIP sözleşmesi "
            "belgelenmeli (ubuntu-latest'te trivy yok → script SKIP üretir; "
            "görünür dokümansız SKIP sessiz kanıt kaybıdır)",
        )


class TestCronRunbookParity(unittest.TestCase):
    """K4: cron runbook'ı beklenen log desenini kaynaktan türetilmiş verir.

    Runbook metni elle kopyalanırsa iki yerde birden sessizce eskir: cron'un
    ilk Pazartesi koşumunda "SKIP bekleniyordu ama SKIP satırı yok" durumu
    ancak runbook'a bakarak yakalanır. Bu yüzden her beklenen dizgi workflow
    ya da script'ten REGEX ile çıkarılır, runbook bölümünde birebir aranır.
    """

    @classmethod
    def setUpClass(cls):
        cls._doc = RUNBOOK.read_text(encoding="utf-8")
        cls._wf = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        cls._sh = SMOKE.read_text(encoding="utf-8")
        start = cls._doc.find(RUNBOOK_HEADING)
        assert start != -1, "%s: runbook bölümü yok (%s)" % (RUNBOOK, RUNBOOK_HEADING)
        end = cls._doc.find(RUNBOOK_END, start)
        assert end != -1, "%s: runbook bölümü %s ile kapanmıyor" % (
            RUNBOOK, RUNBOOK_END)
        cls._runbook = cls._doc[start:end]

    def _from(self, text, pattern, what):
        m = re.search(pattern, text)
        self.assertIsNotNone(m, "kaynakta bulunamadı: %s (%r)" % (what, pattern))
        return m.group(1)

    def test_runbook_quotes_cron_expression_verbatim(self):
        cron = self._from(self._wf, r'- cron:\s*"([^"]+)"', "cron ifadesi")
        self.assertIn("`%s`" % cron, self._runbook,
                      "runbook cron ifadesini workflow'tan birebir vermeli: %s"
                      % cron)

    def test_runbook_quotes_skip_line_verbatim(self):
        # skip() basımı "SKIP: <mesaj>" — mesaj script'ten türetilir.
        msg = self._from(
            self._sh, r'skip\s+"(trivy yok[^"]*)"',
            "trivy SKIP mesajı")
        self.assertIn("SKIP: %s" % msg, self._runbook,
                      "runbook SKIP satırını script'ten birebir vermeli. "
                      "Mesaj script'te değiştiyse runbook da değişmeli.")

    def test_runbook_quotes_smoke_evidence_header_and_image(self):
        header = self._from(
            self._sh, r'log\s+"([^"]*smoke evidence)"',
            "evidence başlığı")
        tag = self._from(
            self._sh, r'DOCKER_SMOKE_TAG:-([^}]+)\}', "varsayılan image tag")
        self.assertIn(header, self._runbook,
                      "runbook evidence başlığını script'ten birebir vermeli")
        self.assertIn("image=%s" % tag, self._runbook,
                      "runbook image satırını script'in varsayılan tag'iyle "
                      "birebir vermeli: image=%s" % tag)

    def test_runbook_quotes_evidence_fallback_verbatim(self):
        note = self._from(
            self._wf, r'\|\| echo\s+"([^"]+)"',
            "Show smoke evidence fallback notu")
        self.assertIn(note, self._runbook,
                      "runbook fallback notunu workflow'tan birebir vermeli. "
                      "Not, script log()'a ulaşmadan çökerse basılır.")

    def test_runbook_documents_deviation_actions(self):
        # Sapma tablosu boş olmamalı: "SKIP satırı yok" en kritik sapmadır
        # (yeşil ama kanıtsız koşum K3'ün savunmasını deler).
        self.assertIn("### Sapma tablosu", self._runbook,
                      "runbook sapma tablosu içermeli")
        self.assertIn("SKIP: trivy yok", self._runbook,
                      "tablo, beklenen SKIP satırının KAYBOLMASI durumunu "
                      "adımlarıyla birlikte kapsamalı")
        for deviation in (
                "Show smoke evidence",
                "workflow_dispatch",
                "image-scan",
                "trivy_findings=0",
                "gh run list --workflow docker-security.yml",
        ):
            with self.subTest(deviation=deviation):
                self.assertIn(deviation, self._runbook,
                              "sapma tablosu bu durumu kapsamalı: %s"
                              % deviation)

    def test_runbook_states_skip_is_evidence_not_error(self):
        # Değişmez: SKIP bir hata değil kanıtın kendisi. Runner'a trivy
        # kurmak cron'un görünürlüğünü sessizleştirir.
        self.assertIn("SKIP bir hata değildir", self._runbook,
                      "runbook SKIP'in kanıt olduğunu açıkça söylemeli")


if __name__ == "__main__":
    unittest.main()
