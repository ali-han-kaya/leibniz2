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

Kurallar (fail-closed, offline, stdlib-only):

  K1) schedule: içeren her workflow, repo kapı script'lerinden en az birini
      çağırır (GATE_SCRIPTS kaydındaki kalıplardan biri).
  K2) cron içeren job'ın adımlarında gate script'i RUN ile çağrılır (uses:
      adımı sayılmaz — action'lar script'i substitute edemez).
  K3) docker_security_smoke.sh çağıran her schedule job'ı, runner'a trivy
      kuran ya da SKIP sözleşmesini uyumlu belgeleyen bir satır taşır.
  K4) Kayıtlı her kapı script'i, geçtiği scheduled workflow'da `run:`
      adımında çağrılır (metinde geçmesi yetmez — K2'nin genellemesi).
  K5) protection-drift job'ı, secret YOKKEN SKIP ettiğini ve okunamazsa
      KIRMIZI döndüğünü görünür biçimde belgeler.
  K6) prettier-drift job'ı `--require-prettier` kullanır: kurulmamış bir
      prettier'la job yeşil görünüp hiçbir şey ölçmemeli.
  K7) Hiçbir iki scheduled workflow aynı cron'u paylaşmaz (aynı dakikadaki
      iki haftalık koşum runner kuyruğunda birbirini geciktirir).

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
# check_prettier_format.py (2026-09-30): pre-commit hook'unun TÜM takipli
# yüzeye genişletilmiş hâli — aynı script hem hook'ta (stage'li dosyalar)
# hem haftalık cron'da (--all-tracked) koşar. K6, CI'nin SKIP'e düşüp
# sessizce yeşil görünmesini engeller.
# record_battery_trend.py (2026-10-06): determinism-trend deseninde batarya
# süresi zamanlayıcısı — yerel CLI'ı var (aynı komut), battery-trend.yml
# onu `run:` ile çağırır, akış YAML'da tekrar edilmez (check_protection_
# drift.py emsalinin aynısı — K3-sınırı yok: kırmızı batarya --update'i
# kendisi düşürür, SKIP sessizliği yok).
GATE_SCRIPTS = (
    "docker_security_smoke.sh",
    "texlive_determinism_test.sh",
    "verify_delivery.py",
    "check_protection_drift.py",
    "check_prettier_format.py",
    "record_battery_trend.py",
    # vercel-deploy-check.yml (aylık cron) bu script'i `run:` adımında
    # çağırıyor ve workflow'un kendi yorumu "GATE_SCRIPTS kaydı" diyor —
    # kayıtta olmadığı için K1 parity testi kırmızıydı (repo-İÇİ drift,
    # bu dosyanın düzenlemesinden bağımsız). Yerel karşılığı var:
    # `python3 check_vercel_deploy.py --base-url <url>`.
    "check_vercel_deploy.py",
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

    def test_no_two_scheduled_workflows_share_a_cron(self):
        """K7: hiçbir iki scheduled workflow aynı cron'u paylaşmaz.

        Ölçülen vaka (2026-09-30): `protection-drift.yml` ilk eklendiğinde
        `docker-security.yml` ile AYNI `43 3 * * 1`'i almıştı — hem de
        kendi yorumunda "determinism-trend 03:17'den ayrı" diyerek. Kısmi
        kontrol (komşuya bakmak) yeterli değil: çakışma ancak TÜM set
        karşılaştırılınca görünür. Aynı dakikadaki iki haftalık koşum runner
        kuyruğunda birbirini geciktirir ve zamanlama kanıtını (trend kaydı)
        bulanıklaştırır.
        """
        seen = {}
        for wf in scheduled_workflows():
            text = wf.read_text(encoding="utf-8")
            # Cron değeri TIRNAK İÇİNDE ve BOŞLUK taşır ("43 3 * * 1"):
            # `[^\s]+` ile yakalamaya kalkmak hiçbir kayıt bulmaz ve test
            # vacuous kalır (ölçüldü — aşağıdaki non-vacuity kontrolü bu
            # yüzden var).
            for cron in re.findall(r'^\s*-\s*cron:\s*["\']?([^"\']+?)["\']?\s*$',
                                   text, re.M):
                with self.subTest(workflow=wf.name, cron=cron):
                    self.assertNotIn(
                        cron, seen,
                        "%s ve %s AYNI cron'u paylaşıyor (%s) — haftalık "
                        "dakikalar ayrı olmalı"
                        % (wf.name, seen.get(cron), cron))
                seen[cron] = wf.name
        # Non-vacuity: regex kayarsa döngü hiç dönmez ve test yeşil kalırdı.
        self.assertGreaterEqual(
            len(seen), 2, "cron taraması hiç kayıt bulamadı — desen bozuk")

    def test_prettier_drift_job_requires_prettier(self):
        """K6: prettier-drift job'ı `--require-prettier` ile koşmalı.

        `check_prettier_format.py` pre-commit'te ortam-bağımlıdır ve prettier
        yoksa SKIP eder (rc=0). CI'da aynı semantik job'ı anlamsız kılardı:
        prettier kurulmadığı her hafta YEŞİL görünüp hiçbir şey ölçmezdi.
        `--require-prettier` o dalı rc=2'ye çevirir.
        """
        text = (WORKFLOWS / "prettier-drift.yml").read_text(encoding="utf-8")
        bodies = "\n".join(run_bodies(text))
        self.assertIn(
            "--all-tracked", bodies,
            "prettier-drift.yml: job TÜM takipli yüzeyi taramalı "
            "(`--all-tracked`) — yalnız stage'li/dokunulan dosyaları tarayan "
            "pre-commit kapısını kopyalamak grandfather drift'i kapatmaz")
        self.assertIn(
            "--require-prettier", bodies,
            "prettier-drift.yml: `--require-prettier` olmadan prettier "
            "kurulmadığında job rc=0 SKIP ederdi (sessiz kanıt kaybı)")
        self.assertIn(
            "package-lock.json", text,
            "prettier-drift.yml: prettier sürümünün TEK kaynağı "
            "(package-lock) görünür olmalı — sürüm elle yazılırsa iki kopya "
            "olur ve biri kayar")


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




# ── K9 lean varyantı: docker-security.yml içindeki AYRI Trivy job'ı ────────
def workflow_text():
    return (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")


def job_block(text, jid):
    """`  <jid>:` job bloğu — bir sonraki 2-boşluk anahtarına kadar."""
    m = re.search(rf"^  {re.escape(jid)}:\n(.*?)(?=^  \S|\Z)", text,
                  re.M | re.S)
    return m.group(1) if m else None


class TestLeanImageScanJob(unittest.TestCase):
    """K9 varyantı sözleşmesi: ayrı target, ayrı cache, ayrı fail-closed gate.

    Kök-neden (aynı ailenin imaj karşılığı): toolchain yüzeyi taban gate'e
    karışırsa tek tarama iki farklı şeyi birden ölçer; build-args bağlantısı
    koparsa job toolchain'siz bir imajı "temiz" diye rapor ederdi. Bu yüzden
    job AYRI, kanıt adımı Trivy'den ÖNCE gelir ve pin lean-toolchain
    dosyasından (tek kaynak) türetilir.
    """

    def test_job_exists_with_timeout_and_permissions(self):
        block = job_block(workflow_text(), "lean-image-scan")
        self.assertIsNotNone(
            block, "docker-security.yml'de lean-image-scan job'ı yok")
        self.assertIn("Build and scan lean-runtime image (K9 variant)", block)
        m = re.search(r"timeout-minutes:\s*(\d+)", block)
        self.assertIsNotNone(m, "lean-image-scan: timeout-minutes yok (K2)")
        self.assertTrue(1 <= int(m.group(1)) <= 120,
                        f"timeout-minutes aralık dışı: {m.group(1)}")
        self.assertIn("permissions:", block, "job-yetkisi daraltılmalı")
        self.assertIn("security-events: write", block)

    def test_build_targets_lean_runtime_with_opt_in(self):
        block = job_block(workflow_text(), "lean-image-scan")
        self.assertIn("target: lean-runtime", block,
                      "varyant build'i lean-runtime target'ını kullanmalı")
        self.assertIn("INSTALL_LEAN=1", block,
                      "opt-in anahtarı açık olmalı (yoksa job toolchain'siz "
                      "imaj tarar — kayıt-var-koşum-yok)")
        self.assertIn("scope=lean", block,
                      "ayrı cache scope: taban build cache'i 1 GB katmanla "
                      "kirletilmemeli")
        base = job_block(workflow_text(), "image-scan")
        self.assertIsNotNone(base, "taban job yok")
        self.assertNotIn("INSTALL_LEAN", base,
                         "taban job'a INSTALL_LEAN sızdı — yüzeyler karıştı")

    def test_toolchain_evidence_step_precedes_trivy(self):
        block = job_block(workflow_text(), "lean-image-scan")
        ev = block.find("Verify K9 toolchain is installed")
        scan = block.find("Scan lean image with Trivy")
        self.assertNotEqual(ev, -1, "kanıt adımı yok (toolchain'siz yeşil riski)")
        self.assertNotEqual(scan, -1, "Trivy adımı yok")
        self.assertLess(ev, scan, "kanıt adımı Trivy'den ÖNCE gelmeli")
        step = block[ev:scan]
        self.assertIn("docker run --rm", step,
                      "kanıt adımı konteyneri gerçekten çağırmalı (metin değil)")
        self.assertIn("_calisma/lean_reduct/lean-toolchain", step,
                      "pin lean-toolchain dosyasından türetilmeli (tek kaynak)")
        self.assertIn("lean --version", step)

    def test_trivy_gate_is_fail_closed_and_version_pinned(self):
        block = job_block(workflow_text(), "lean-image-scan")
        self.assertIn("aquasecurity/trivy-action@v0.35.0", block,
                      "Trivy action'ı sabit sürüme pin'li olmalı (mutable @master yasak)")
        self.assertIn("exit-code: 1", block, "gate fail-closed olmalı")
        self.assertIn("severity: CRITICAL,HIGH", block)
        self.assertIn("ignore-unfixed: true", block)
        # PR yorumu YOK: aynı dosyaya iki yorum düşmesin (taban job'ın işi)
        self.assertNotIn("trivy_sarif_pr_comment.js", block)


if __name__ == "__main__":
    unittest.main()
