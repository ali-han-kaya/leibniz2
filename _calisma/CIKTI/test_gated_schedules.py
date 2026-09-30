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
      çağırır (GATE_SCRIPTS kaydındaki kalıplardan biri).
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

# KAYIT (registry) — cron job'ının KENDİ adımlarıyla yeniden yazmak yerine
# çağırmasına izin verilen repo kapı script'leri. Üyelik kriteri, K1'in
# amacıdır (parity): script'in YEREL bir karşılığı olmalı ve job onu bir
# `run:` adımında çağırmalı — YAML içinde akış yeniden yazılmamalı.
#
# docker_security_smoke.sh bu kaydın bağımsız-script emsalidir: tek başına
# duran bir kapı, hem yerelde hem cron'da AYNI script ile koşar.
# check_protection_drift.py aynı şekle sahiptir (2026-09-30 eklendi): yerel
# CLI'ı var, workflow onu `run:` ile çağırıyor, akış YAML'da tekrar
# edilmiyor. Kayda eklemek kapıyı GEVŞETMEZ: K3'ün SKIP-görünürlüğü kuralı
# burada da geçerli (aşağıdaki test_registry_entries_are_invoked_via_run_not_uses
# ve test_protection_drift_job_documents_token_skip).
GATE_SCRIPTS = (
    "docker_security_smoke.sh",
    "texlive_determinism_test.sh",
    "verify_delivery.py",
    "check_protection_drift.py",
)


def scheduled_workflows():
    return [p for p in sorted(WORKFLOWS.glob("*.yml"))
            if re.search(r"^\s*schedule:", (p.read_text(encoding="utf-8")), re.M)]


def run_bodies(text):
    """Her `run:` adımının GÖVDESİNİ döndürür (blok-skaler dahil).

    Neden `run:.*` yetmiyor: `run: |` biçiminde komut bir SONRAKİ satırdadır,
    yani satır-bazlı arama "`run:` adımında çağrılıyor" iddiasını kanıtlamak
    yerine script metinde herhangi bir yerde geçiyor mu diye bakar. Bu fark
    tam da K2'nin önlemek istediği şeyi kaçırır (uses: ile run: eşit görünür).
    """
    lines = text.splitlines()
    bodies = []
    for i, line in enumerate(lines):
        # İki biçim: `        run: …` (adım anahtarı) ve `      - run: …`
        # (liste öğesinde satır içi). İkincisi atlanırsa yalnız `- name:`
        # kalıbını kullanan dosyalar görülür ve K4 eksik kanıt üretir.
        m = re.match(r"^\s*(?:-\s+)?run:(\s*)(.*)$", line)
        if not m:
            continue
        # Eşik, `run` ANAHTARININ sütunu — `- ` ön eki sayılmaz. Aksi hâlde
        # blok, aynı adımın kardeş anahtarlarını (with:/env:) yanlışlıkla
        # yutar ve K4 komşu adıma ait satırı kanıt sayar.
        key_indent = line.index("run:")
        inline = m.group(2).strip()
        if inline and inline not in ("|", ">", "|-", ">-", "|+", ">+"):
            bodies.append(inline)
            continue
        block = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                block.append(nxt)
                continue
            if len(nxt) - len(nxt.lstrip()) <= key_indent:
                break
            block.append(nxt)
        bodies.append("\n".join(block))
    return bodies


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

    def test_registry_entries_are_invoked_via_run_not_uses(self):
        """K4: kayıtlı her kapı script'i, çağrıldığı scheduled workflow'da `run:`
        adımında çağrılır — metinde geçmesi yetmez (`uses:` ile substitution
        imkânsızdır). Kayıt büyüdükçe bu kural onu dengeler."""
        for wf in scheduled_workflows():
            text = wf.read_text(encoding="utf-8")
            bodies = run_bodies(text)
            for gate in GATE_SCRIPTS:
                if gate not in text:
                    continue
                with self.subTest(workflow=wf.name, gate=gate):
                    self.assertTrue(
                        any(gate in b for b in bodies),
                        f"{wf.name}: '{gate}' metinde var ama bir `run:` adımında "
                        f"çağrılmıyor (uses:/comment ile geçmek kapı-paritesi "
                        f"sağlamaz; blok-skaler `run: |` gövdesi sayılır)",
                    )

    def test_protection_drift_job_documents_token_skip(self):
        """K5: protection-drift job'ı, secret YOKKEN SKIP ettiğini ve secret
        VAR ama okunamazsa KIRMIZI döndüğünü görünür biçimde belgelemeli.

        Aksi hâlde haftalık job her hafta sessizce geçer ve kimse denetimin
        hiç koşmadığını fark etmez — K3'ün docker için önlediği kaybın aynısı.
        """
        text = (WORKFLOWS / "protection-drift.yml").read_text(encoding="utf-8")
        self.assertIn(
            "SKIP", text,
            "protection-drift.yml: token yokken SKIP sözleşmesi belgelenmeli "
            "(görünür dokümansız SKIP sessiz kanıt kaybıdır)",
        )
        self.assertIn("PROTECTION_PAT", text,
                      "protection-drift.yml: okuma yetkisinin hangi secret'tan "
                      "geldiği görünür olmalı")


class TestRunBodyExtractor(unittest.TestCase):
    """run_bodies() öz-testi: blok-skaler gövdeyi gerçekten topluyor mu?

    K4 bu fonksiyona dayanıyor; fonksiyon boş dönerse `any(...)` False olur ve
    K4 her zaman kırmızıya döner (fail-closed). Yine de POZİTİF kanıt gerekir:
    `run: |` gövdesinin toplandığını ve bir SONRAKİ adımın gövdesine
    sızmadığını göstermeden K4'ün yeşilliği anlamsız olurdu.
    """

    def test_collects_block_scalar_body(self):
        wf = (
            "jobs:\n"
            "  drift:\n"
            "    steps:\n"
            "      - name: kapi\n"
            "        run: |\n"
            "          set -o pipefail\n"
            "          python3 _calisma/CIKTI/check_protection_drift.py --json\n"
            "      - name: sonraki\n"
            "        run: echo bitti\n"
        )
        bodies = run_bodies(wf)
        self.assertEqual(len(bodies), 2, f"iki run: adımı beklenirdi: {bodies}")
        self.assertIn("check_protection_drift.py", bodies[0])
        self.assertNotIn(
            "check_protection_drift.py", bodies[1],
            "blok gövdesi sonraki adıma sızdı — K4 yanlış adımı kanıtlar",
        )

    def test_inline_run_body_is_collected(self):
        """`- run: cmd` liste-içi biçim de toplanır."""
        wf = "    steps:\n      - run: bash _calisma/CIKTI/docker_security_smoke.sh\n"
        self.assertEqual(len(run_bodies(wf)), 1)
        self.assertIn("docker_security_smoke.sh", run_bodies(wf)[0])

    def test_block_does_not_swallow_sibling_keys(self):
        """`run: |` bloğu, aynı adımın kardeş anahtarlarını (with:) yutmamalı."""
        wf = (
            "    steps:\n"
            "      - run: |\n"
            "          echo kapi\n"
            "        with:\n"
            "          x: docker_security_smoke.sh\n"
        )
        body = run_bodies(wf)[0]
        self.assertIn("echo kapi", body)
        self.assertNotIn(
            "docker_security_smoke.sh", body,
            "kardeş anahtar bloğa sızdı — K4 grep'in metin-eşleşmesine geriler",
        )

    def test_uses_step_yields_no_body(self):
        """`uses:` bir `run:` gövdesi ÜRETMEZ — K4'ün uses/run ayrımı."""
        wf = "    steps:\n      - uses: actions/checkout@v7\n"
        self.assertEqual(run_bodies(wf), [])

    def test_extractor_finds_every_real_run_step(self):
        """Gerçek workflow'larda en az bir `run:` var; extractor sessizce
        boş dönse K4 vacuous kalırdı."""
        for wf in scheduled_workflows():
            with self.subTest(workflow=wf.name):
                self.assertTrue(
                    run_bodies(wf.read_text(encoding="utf-8")),
                    f"{wf.name}: hiç run: gövdesi bulunamadı — extractor bozuk",
                )


if __name__ == "__main__":
    unittest.main()
