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
  K3) docker_security_smoke.sh çağıran her schedule job'ı, runner'a trivy
      kuran ya da SKIP sözleşmesini uyumlu belgeleyen bir satır taşır.

OFFLINE, stdlib-only, ~0.02s.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

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


if __name__ == "__main__":
    unittest.main()
