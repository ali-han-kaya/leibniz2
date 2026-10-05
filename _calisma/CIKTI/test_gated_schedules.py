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
      KURAN bir adım taşır. Tarihsel neden: ubuntu-latest'te trivy yokken
      job her hafta exit-0 SKIP üretiyordu — yeşil ama kanıtsız. Kuralın
      ikinci yarısı artık zorunlu: kurulum sürüm + sha256 ile pin'lenir
      (tedarik zinciri), ve sürüm image-scan'in motoruyla eşitlenir ki iki
      job tek tarayıcıyla çalışsın.
  4) Runbook (patching doc) beklenen log desenini KAYNAKTAN türetilmiş
      olarak verir: cron ifadesi, gerçek koşumun kanıt satırları
      (verdict=PASS, trivy_findings=0, health_http=200 …), SKIP satırı,
      evidence başlığı/görüntüsü, fallback notu ve assert adımının OK
      mesajı workflow + script'ten okunur, sonra runbook'ta birebir
      aranır. Kopyalanmış metin DRIFT üretir — kural yazısı değişirse
      runbook da değişmezse kapı kırılır (fail-closed).
  5) CI'da SKIP kanıt SAYILMAZ: trivy kurulu bir runner'da SKIP, kurulumun
      sessizce bozulduğunun işaretidir. Workflow bunu fail-closed'a bağlar
      (verdict=PASS yoksa job kırmızı) — aksi halde haftalık SKIP yine
      görünür yeşil olur ve cron'un tek amacı sessizleşir.
  6) Motor paritesi: smoke'un kurduğu Trivy sürümü, image-scan'in taramasıyla
      aynı olmalı. Sürüm iki dosyada yazılıdır (workflow pin'i + runbook'un
      beklenen `trivy=` satırı); bağ testle zorlanır, yoksa iki kapı farklı
      motorlarla çalışıp birbirini çürütebilir.

OFFLINE, stdlib-only, ~0.02s.
"""
import ast
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


def step_body(text, name):
    """`- name: <name>` adımının gövdesi (sonraki `- name:` / job sonuna kadar).

    Workflow'ta birden çok benzer `|| echo` geçebildiği için regex'i TÜM
    dosyada değil, tek adımın gövdesinde koşmak zorunlu — yoksa test yanlış
    satırı kaynak sanar.
    """
    m = re.search(
        r"- name: %s\n(?P<body>.*?)(?=\n      - |\n\Z)" % re.escape(name),
        text, re.S)
    return m.group("body") if m else None


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

    def test_docker_smoke_schedule_job_installs_trivy_pinned(self):
        """K3: cron job'ı runner'a trivy KURAR (sürüm + sha256 pin'li)."""
        text = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        self.assertIn("Install Trivy", text,
                      "docker-security.yml: smoke job'ı trivy kurulum adımı "
                      "taşımalı. Trivysiz runner'da script SKIP üretir (exit 0) "
                      "ve cron haftalık kanıtsız yeşil koşuma düşer — K3'ün "
                      "amacı tam olarak bunu engellemek.")
        m = re.search(r"TRIVY_SHA256:\s*[\"']?([0-9a-f]{64})", text)
        self.assertIsNotNone(m,
                             "trivy kurulumu sha256 ile doğrulanmalı: indirilen "
                             "tarball'ın hash'i release checksums.txt ile eşleşmeli")
        self.assertIn("sha256sum -c", text,
                      "pinlenen hash gerçekten doğrulanmalı (sha256sum -c) — "
                      "sadece yazılı olması kanıt değildir")
        self.assertIn("SKIP", text,
                      "script'in SKIP sözleşmesi hâlâ belgelenmeli: triviysiz "
                      "yerel makinelerde doğru davranış, kurulumu değil betiği "
                      "korumak")


class TestTrivySarifSeverityContract(unittest.TestCase):
    """Trivy SARIF adımı + yorum script'i seviye sözleşmesi (fail-closed).

    Canlı ölçüm (2026-10-05, PR #82): trivy-action@v0.35.0 SARIF'te
    severity'yi KASTEN siler; properties.severity olmadan yorum script'i
    default-deny ile 12 MEDIUM/LOW bulguyu HIGH sayıp temiz taramayı
    kırmızıya çevirdi. İki yüzey birlikte pinlenir:
      1) workflow SARIF adımı `limit-severities-for-sarif: true` taşımalı,
      2) script seviyeyi properties.severity ÖNCE, yoksa message
         "Severity: X" satırından okumalı (v0.69.3 şeması).
    """

    @classmethod
    def setUpClass(cls):
        cls._wf = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        cls._js = (ROOT / "_calisma" / "CIKTI" / "github_scripts" /
                   "trivy_sarif_pr_comment.js").read_text(encoding="utf-8")

    def test_sarif_step_limits_severities(self):
        body = step_body(self._wf, "Scan image with Trivy (SARIF)")
        self.assertIsNotNone(body, "SARIF tarama adımı yok")
        self.assertIn(
            "limit-severities-for-sarif: true", body,
            "SARIF adımı severity'yi sınırlamalı: trivy-action@v0.35.0 bu "
            "input olmadan SARIF'te severity filtresini kaldırır ve tüm "
            "seviyeler taranır (canlı ölçüm: 12 yanlış HIGH).")

    def test_comment_script_reads_severity_from_message_text(self):
        self.assertIn(
            "Severity:", self._js,
            "script message.text gövdesindeki 'Severity: X' satırını "
            "okumalı (v0.69.3 SARIF şeması — properties.severity yok)")
        self.assertRegex(
            self._js,
            r"match\(/\^Severity:\\s\*\(",
            "message'tan seviye çıkaran regex beklenir")

    def test_comment_script_keeps_properties_first(self):
        # properties.severity ÖNCE okunmalı: eski şemada daha kesin kaynaktır.
        i_prop = self._js.index("properties && result.properties.severity")
        i_msg = self._js.index("Severity:\\s*([A-Za-z]+)")
        self.assertLess(i_prop, i_msg,
                        "properties.severity mesajdan önce okunmalı")

    def test_comment_script_keeps_default_deny(self):
        # Seviye hiçbir yerde yoksa hâlâ HIGH (sessiz geçiş yok).
        self.assertIn(
            'return m ? m[1].toUpperCase() : "HIGH";', self._js,
            "seviye-yok default-deny (HIGH) korunmalı")


class TestSkipIsNotEvidenceInCI(unittest.TestCase):
    """K5: trivy kurulu bir CI'da SKIP, kurulumun bozulduğunun işaretidir.

    Tarihsel kök-neden: SKIP exit 0 döndüğü için job yeşil görünür ve cron
    haftalık "başarılı" ama kanıtsız bir koşuma düşer. Trivy kurulumu
    eklendiğinde bu yol kapanmazsa SKIP yeniden sessizleşir. Kapatma
    fail-closed olmalı: verdict=PASS yoksa job KIRMIZI.
    """

    @classmethod
    def setUpClass(cls):
        cls._wf = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")

    def test_smoke_job_asserts_real_run(self):
        body = step_body(self._wf, "Assert real run (SKIP is not evidence in CI)")
        self.assertIsNotNone(body, "assert adımı yok")
        self.assertIn("verdict=PASS", body,
                      "assert adımı gerçek koşum kanıtını zorlamalı: "
                      "verdict=PASS yoksa job kırmızı olmalı (fail-closed)")
        self.assertIn("exit 1", body,
                      "assert adımı kanıt yoksa job'u düşürmeli (exit 1) — "
                      "yoksa SKIP yine yeşil geçer")

    def test_assert_runs_after_the_smoke_step(self):
        # Sıra sözleşmesi: assert, smoke'dan SONRA olmalı; aksi halde
        # kanıt henüz yazılmadan okur ve her koşumda kırmızıya döner
        # (ya da, ters yazım hatasıyla, hiç çalışmaz).
        smoke = self._wf.index("Run local security smoke (SKIP-aware)")
        assert_at = self._wf.index("Assert real run (SKIP is not evidence in CI)")
        self.assertLess(smoke, assert_at,
                        "assert adımı smoke adımından sonra gelmeli")


class TestSmokeHookRegistrationContract(unittest.TestCase):
    """K7: check-docker-security-smoke'un pre-commit kaydı sözleşmedir.

    Boşluk (ölçüldü): patching hook'un kendi kayıt sözleşmesi vardı
    (entry / files / pass_filenames / always_run — test_dockerfile_security_
    patching.py), smoke hook'unki yoktu; yalnız genel hook listesi
    (test_all_hooks_smoke.py) tutuluyordu. Böylece entry yanlışa çevrilse
    ya da files daraltsa hiçbir kapsam testi yakalamıyordu.

    Buradaki asıl sözleşme **paritedir**: hook'un entry'si, CI'ın smoke
    job'ının çağırdığı script ile aynı olmalı. İkisi ayrışırsa yerel
    koşum artık CI'ın birebir karşılığı değildir — ve dokümanın "yerel
    ikizi" iddiası sessizce doğrulanmaz hale gelir. Script yolu
    workflow'dan türetilir, testte sabit yazılmaz.
    """

    @classmethod
    def setUpClass(cls):
        cls._cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        cls._wf = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        cls._block = next(
            (b for b in cls._cfg.split("\n      - id: ")
             if b.startswith("check-docker-security-smoke")), "")

    def test_hook_entry_runs_the_ci_parity_script(self):
        self.assertTrue(self._block,
                        "check-docker-security-smoke config'de yok")
        m = re.search(r"^\s*- cron:", self._wf, re.M)
        self.assertIsNotNone(m, "docker-security.yml'de schedule yok")
        ci = re.search(r"^\s*run:\s*bash\s+(\S*docker_security_smoke\.sh)\s*$",
                       self._wf, re.M)
        self.assertIsNotNone(ci,
                             "CI smoke job'ı script'i run: ile çağırmalı")
        script = ci.group(1)
        entry = re.search(r"^\s*entry:\s*(.+)$", self._block, re.M)
        self.assertIsNotNone(entry,
                             "hook tanımında entry: yok — hook ne çalıştırır?")
        # TAM EŞİTLİK, alt-dize değil: '...smoke.sh.bak' alt-dizde
        # '...smoke.sh'yi barındırır ama hook yanlış dosyayı koşardı
        # (ölçüldü: alt-dize kontrolü bu mutasyonu kaçırdı).
        self.assertIn(script, entry.group(1).split(),
                      "hook'un entry'si CI ile AYNI script'i çalıştırmalı "
                      "(yerel ikizi iddiası): %s" % script)
        self.assertTrue((ROOT / script).is_file(),
                        "parite script'i diskte yok: %s" % script)

    def test_hook_matches_real_dockerfiles_only(self):
        # Tetikleme yüzeyi: kök VE kök altı Dockerfile eşlenmeli —
        # alt dizindeki image de tam build+scan'i hak ediyor. Buna karşılık
        # Dockerfile.md / .bak BELGE ya da yedektir; onları eşlemek
        # dakikalar süren bir build'i boşuna tetikler.
        m = re.search(r"^\s*files:\s*'?([^'\"\n]+?)'?\s*$", self._block, re.M)
        self.assertIsNotNone(m, "hook tanımında files: deseni yok")
        pat = re.compile(m.group(1))
        for hit in ("Dockerfile", "apps/x/Dockerfile", "a/b/Dockerfile"):
            with self.subTest(path=hit):
                self.assertIsNotNone(pat.search(hit),
                                     "gerçek Dockerfile eşlenmeli: %s" % hit)
        for miss in ("Dockerfile.md", "apps/web/Dockerfile.bak",
                     "docs/dockerfile-notes.txt"):
            with self.subTest(path=miss):
                self.assertIsNone(pat.search(miss),
                                  "Dockerfile olmayan dosya eşlenmemeli: %s"
                                  % miss)

    def test_hook_is_change_scoped_not_always_run(self):
        # Tam build dakikalar sürer; hook yalnız surface'te (Dockerfile
        # değişince) koşmalı. always_run eklenirse nedensel sinyal kaybolur
        # ve her commit dakikalar süren bir build'e bağlanır.
        self.assertIsNone(
            re.search(r"^\s*always_run:", self._block, re.M),
            "değişim-farkında: always_run olmamalı (build her committe pahalı)")
        self.assertRegex(self._block, r"(?m)^\s*language:\s*system\s*$",
                         "hook language: system olmalı")
        self.assertRegex(self._block, r"(?m)^\s*stages:\s*\[pre-commit\]",
                         "hook pre-commit aşamasına bağlı olmalı")


class TestDockerGateCiIndependence(unittest.TestCase):
    """K8: docker güvenlik kapısı CI'da hook'tan BAĞIMSIZ çalışır.

    Ölçülen durum: kapı `verify.yml` içinde bir job DEĞİLDİR — ayrı bir
    workflow'tur (`docker-security.yml`), `verify.yml` onu hiç referans
    almaz (0 kez) ve iki job'ın arasında `needs:` yoktur. Yani
    bağımsızlık bugün doğru — ama **kaza**. Kimse eklemedi, kimse
    kaldirmadi; dosyalar arasındaki tesadüfi bir durum.

    Bu test onu sözleşmeye baglar:
      - kapı ayri bir workflow olarak kalmali (verify.yml'e yutulmamali —
        yutulursa verify job'inin ekinde kalsin diye needs: eklenir ve
        kapi bagimsizligini kaybeder)
      - iki job birbirine needs: ile baglanmamali
      - push tetikleyicisi path filtresiyle daraltilmamali (Dockerfile
        degisikliklerinde kapinin susmamasi icin)
    """

    @classmethod
    def setUpClass(cls):
        cls._gate = (WORKFLOWS / "docker-security.yml").read_text(encoding="utf-8")
        cls._verify = (WORKFLOWS / "verify.yml").read_text(encoding="utf-8")

    def test_gate_is_a_separate_workflow(self):
        self.assertNotIn("docker-security", self._verify,
                         "verify.yml docker-security kapisini icermemeli — "
                         "kapı ayrı workflow'tur (bagimsizlik sozlesmesi). "
                         "Yutulursa needs: bagimliligi dogar ve kapı "
                         "verify job'ine baglanir.")
        self.assertIn("name: docker-security", self._gate,
                      "docker-security.yml kapı workflow'u olarak kalmali")

    def test_gate_jobs_have_no_needs(self):
        # needs: eklendiginde smoke job'i image-scan'i (ya da tersi)
        # bekler; kapılar birbirine baglanir ve biri kirmiziya dusunce
        # digerinin kaniti kaybolur.
        self.assertIsNone(
            re.search(r"^\s*needs:", self._gate, re.M),
            "docker-security.yml'de needs: olmamali — iki job birbirinden "
            "bagimsiz kalmali (kanit kaybolmamali)")

    def test_push_trigger_is_not_narrowed_by_paths(self):
        # `push:` altinda paths:/paths-ignore: eklenirse Dockerfile
        # degisikligi kapiyi tetiklemez ve gate sessizce kor olur.
        m = re.search(r"^on:\n((?:  .*\n|\n)*)", self._gate, re.M)
        self.assertIsNotNone(m, "on: blogu yok")
        on_block = m.group(1)
        for narrowing in ("paths:", "paths-ignore:"):
            self.assertNotIn(narrowing, on_block,
                             "push tetikleyicisi %s ile daraltilmamali — "
                             "Dockerfile degisikliginde kapı susmamali"
                             % narrowing)

    def test_patching_contract_also_runs_in_ci(self):
        # Hook degisim-farkinda (yalnizca Dockerfile stage'liyken) kostugu
        # icin, sozlesmenin CI'da da kostugu sart: verify job'i
        # unittest discover ile tum testleri kosuyor ve yama-desen
        # sozlesmesi manifest'te kayitli.
        self.assertIn('unittest discover -s _calisma/CIKTI -p "test_*.py"',
                      self._verify,
                      "verify job'i tam discover kosmali — yoksa kayitli "
                      "olmayan test dosyalari hicbir yerde kosmaz")
        manifest = (ROOT / "_calisma" / "CIKTI" / "check_unit_tests.list").read_text(
            encoding="utf-8")
        for contract in ("test_dockerfile_security_patching.py",
                         "test_gated_schedules.py"):
            with self.subTest(contract=contract):
                self.assertIn(contract, manifest,
                              "kapı sözleşmesi manifest'te kayıtlı olmalı "
                              "(yerel hook + CI aynı bataryayı çalıştırsın): %s"
                              % contract)


class TestGateMergeReportContract(unittest.TestCase):
    """K9: birleşik teslim raporu gerçek sayılarla bağlı kalmalı.

    Rapor PR #65–#69'u özetler. Özet dokümanlar zamanla gerçekten ayrışır:
    test sayısı değişir, commit hash'i yanlış yazılır, bir PR unutulur.
    Buradaki test, raporun sayısal iddialarını **canlı yüzeyden** türetir.

    Özellikle: rapor "SKIP tablosu tek mesajı belgeliyor" diye itiraz
    edildiğinde (aşağıdaki test bunu doğruluyor) raporun da bunu kabul
    etmesi gerekir — aksi halde rapor, düzeltilmiş bir kusuru eski hâliyle
    anlatmaya devam eder.
    """

    @classmethod
    def setUpClass(cls):
        cls._rep = (ROOT / "docs" / "DOCKER_SECURITY_GATE_MERGE_REPORT.md").read_text(
            encoding="utf-8")

    def test_report_lists_every_merged_gate_pr(self):
        # Satır formu aranır ("| #66 |" + backtick'li hex hash), düz geçiş
        # değil: raporda #68 dokuz kez geçiyor ve mutasyon tablosunda da
        # "| #68 | M1 …" satırları var — yalnız "#68" araması ikisini de
        # geçiriyordu (ölçüldü).
        for pr in ("#65", "#66", "#67", "#68", "#69"):
            with self.subTest(pr=pr):
                self.assertRegex(
                    self._rep, r"(?m)^\| %s \|.*`[0-9a-f]{7}`" % pr,
                    "raporda bu PR'ın özet tablo satırı olmalı: %s" % pr)

    def test_report_merge_hashes_match_real_merges(self):
        # Hash, **kendi PR satırında** aranır. Düz `assertIn` yetersiz:
        # her hash ilerleme tablosunda da geçiyor, ilk ölçümde bozulan
        # hash yine bulundu (ölçüldü).
        rows = {}
        for line in self._rep.splitlines():
            # Satır hem PR numarası hem de backtick'li bir hex hash içermeli:
            # raporun mutasyon tablosunda da "| #68 | M1 …" satırları var,
            # onlar gerçek PR satırının üzerine yazıyordu (ölçüldü).
            m = re.match(r"\| (#6[5-9]) \|", line)
            if m and re.search(r"`[0-9a-f]{7}`", line):
                rows.setdefault(m.group(1), line)
        for pr, sha in (("#65", "71a6e09"), ("#66", "47e79ef"),
                        ("#67", "fc8b010"), ("#68", "38c58ba"),
                        ("#69", "674de6f")):
            with self.subTest(pr=pr):
                self.assertIn(pr, rows, "PR satırı yok: %s" % pr)
                self.assertIn(sha, rows[pr],
                              "PR satırındaki merge hash'i yanlış: %s → %s"
                              % (pr, sha))

    def test_report_test_counts_match_live_suites(self):
        # Rapor #65–#69 aralığını 31 -> 45 olarak verir. CANLI toplam
        # 45'den küçükse bir test silinmiş demektir (monoton azalma).
        # Büyükse bu raporun kendi testleri (K9) eklenmiştir — bu bir
        # hata değil, raporun kapsamı o noktada biter.
        # (Eşitlik şartı konulmadı: test kendi eklediği testleri de
        # sayar ve kendini her koşumda kırmızıya döndürürdü.)
        total = 0
        for name in ("test_dockerfile_security_patching", "test_gated_schedules"):
            src = (ROOT / "_calisma" / "CIKTI" / (name + ".py")).read_text(
                encoding="utf-8")
            # AST ile sayılır, grep ile değil: bu dosyanın kendi kaynak
            # satırları test metot imzasını kelime kelime içerdiği için
            # grep tabanlı sayım yanlış pozitif verir (ölçüldü: 33/32).
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                    total += 1
        self.assertGreaterEqual(total, 45,
                               "canlı test toplamı raporun uç noktasından "
                               "kucuk — bir test silinmis olabilir (şu an %d)"
                               % total)
        self.assertIn("**45**", self._rep,
                      "rapor #65-#69 sonrası toplamı vermeli (45)")
        self.assertIn("**31**", self._rep,
                      "rapor oturum başı tabanını vermeli (31)")

    def test_report_records_the_undocumented_skip_messages(self):
        # Script'in birden çok SKIP koşulu var (docker yokluğu, trivy yokluğu,
        # colima/daemon yolları…); runbook yalnız birini belgeler. Rapor
        # **sayıyı** script'ten türetilmiş biçimde vermeli — tek tek mesajı
        # aramak yerine, koşul sayısının doğru yazıldığını kontrol eder.
        sh = (ROOT / "_calisma" / "CIKTI" / "docker_security_smoke.sh").read_text(
            encoding="utf-8")
        skips = re.findall(r'\|\|\s*skip\s+"([^"]+)"', sh)
        skips += re.findall(r'^\s*skip\s+"([^"]+)"', sh, re.M)
        n = len(set(skips))
        self.assertGreaterEqual(n, 5,
                                "script en az 5 SKIP koşulu içermeli (şu an %d)"
                                % n)
        self.assertIn("SKIP koşulu", self._rep,
                      "rapor SKIP koşul sayısını vermeli")
        # Sayı **dijital** ve SKIP koşulu'na bağlı biçimde: serbest bir
        # `\b5\b` araması "5 PR" gibi ilgisiz sayılarla tutuyordu (ölçüldü).
        self.assertRegex(self._rep, r"\*\*%d SKIP koşulu" % n,
                         "rapor SKIP koşulu sayısını doğru vermeli (%d)" % n)
        for head in ("docker CLI yok", "trivy yok"):
            with self.subTest(head=head):
                self.assertIn(head, self._rep,
                              "rapor her SKIP koşulunu adıyla belgelemeli: %s"
                              % head)


class TestCronRunbookParity(unittest.TestCase):
    """K4: cron runbook'ı beklenen log desenini kaynaktan türetilmiş verir.

    Runbook metni elle kopyalanırsa iki yerde birden sessizce eskir. Bunun
    yerine her dizgi workflow ya da script'ten REGEX ile çıkarılır, runbook
    bölümünde birebir aranır. İki mod da (gerçek koşum + SKIP fallback)
    pinlenir — çünkü ikisi de meşru çıkış yollarıdır.
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

    def test_runbook_quotes_real_run_evidence_lines(self):
        # Gerçek koşumun kanıt satırları — script'ten türetilir. Bunlar
        # kanıtın kendisidir: SKIP modunda HİÇBİRİ yazılmaz.
        for pattern, what in (
                (r'log\s+"(trivy_findings=0)"', "trivy_findings"),
                (r'log\s+"(trivy_clean=Clean)"', "trivy_clean"),
                (r'log\s+"(health_http=200)"', "health_http"),
                (r'log\s+"(verdict=PASS)"', "verdict=PASS"),
        ):
            with self.subTest(evidence=what):
                line = self._from(self._sh, pattern, what)
                if "$" in line:  # dinamik değer: yalnız anahtar doğrulanır
                    line = line.split("=", 1)[0] + "="
                self.assertIn(line, self._runbook,
                              "runbook gerçek koşumun kanıt satırını "
                              "script'ten birebir vermeli: %s" % line)

    def test_runbook_pins_healthy_evidence_value(self):
        """container_health=<değer> dinamiktir; kanıt DEĞERİ script'ten gelir.

        Script yalnız `health_status == "healthy"` ise verdict'e geçer; runbook
        bu yüzden `container_health=healthy` demelidir. Değer kopyalanmaz —
        script'in başarı ölçütü önce doğrulanır, sonra beklenen değer aranır.
        """
        self.assertIn('[[ "$health_status" == "healthy" ]]', self._sh,
                      "script'in sağlık başarı ölçütü değişti — runbook'taki "
                      "container_health beklenen değeri güncellenmeli")
        self.assertIn("container_health=healthy", self._runbook,
                      "runbook sağlık kanıtının değerini vermeli: "
                      "container_health=healthy")

    def test_runbook_quotes_pass_message_verbatim(self):
        # printf biçimi: 'PASS: … — kanıt: %s\n' — dinamik kuyruk (%s) ve
        # kaçış dizisi dokümana girmez; sabit önek birebir verilir.
        msg = self._from(
            self._sh, r"printf '(PASS:[^']+?)\s*—\s*kanıt:",
            "PASS mesajı")
        self.assertIn(msg, self._runbook,
                      "runbook script'in PASS mesajını birebir vermeli")

    def test_runbook_quotes_skip_line_verbatim(self):
        # skip() basımı "SKIP: <mesaj>" — mesaj script'ten türetilir.
        msg = self._from(self._sh, r'skip\s+"(trivy yok[^"]*)"',
                         "trivy SKIP mesajı")
        self.assertIn("SKIP: %s" % msg, self._runbook,
                      "runbook SKIP satırını script'ten birebir vermeli. "
                      "Mesaj script'te değiştiyse runbook da değişmeli.")

    def test_runbook_quotes_smoke_evidence_header_and_image(self):
        header = self._from(self._sh, r'log\s+"([^"]*smoke evidence)"',
                            "evidence başlığı")
        tag = self._from(self._sh, r'DOCKER_SMOKE_TAG:-([^}]+)\}',
                         "varsayılan image tag")
        self.assertIn(header, self._runbook,
                      "runbook evidence başlığını script'ten birebir vermeli")
        self.assertIn("image=%s" % tag, self._runbook,
                      "runbook image satırını script'in varsayılan tag'iyle "
                      "birebir vermeli: image=%s" % tag)

    def test_runbook_quotes_evidence_fallback_verbatim(self):
        # NOT: workflow'ta İKİ `|| echo` var (assert adımı + evidence adımı).
        # Tüm dosyada regex koşmak yanlış satırı yakalar; bu yüzden
        # fallback yalnız "Show smoke evidence" adımının gövdesinden aranır.
        body = step_body(self._wf, "Show smoke evidence")
        self.assertIsNotNone(body, "Show smoke evidence adımı yok")
        note = self._from(body, r'\|\| echo\s+"([^"]+)"',
                          "Show smoke evidence fallback notu")
        self.assertIn(note, self._runbook,
                      "runbook fallback notunu workflow'tan birebir vermeli. "
                      "Not, script log()'a ulaşmadan çökerse basılır.")

    def test_runbook_quotes_assert_ok_message_verbatim(self):
        body = step_body(self._wf, "Assert real run (SKIP is not evidence in CI)")
        self.assertIsNotNone(body, "assert adımı yok")
        ok = self._from(body, r'echo\s+"(OK:[^"]+)"', "assert OK mesajı")
        self.assertIn(ok, self._runbook,
                      "runbook assert adımının OK mesajını birebir vermeli")

    def test_runbook_trivy_version_matches_workflow_pin(self):
        """Runbook'un `trivy=<sürüm>` satırı workflow'un pin'iyle aynı olmalı.

        Sapma tablosunun "beklenmeyen sürüm" satırı bu drift'i tarif eder:
        image-scan job'ı `trivy-action@v0.35.0` ile tararken smoke job'ı
        ayrı bir motor kurarsa iki kapı çelişebilir (biri yeşil, biri
        kırmızı — hangisinin doğru olduğu belli değildir). Parite iki
        yerde yazılı olduğu için bağ testle zorlanır.
        """
        version = self._from(self._wf,
                             r'TRIVY_VERSION:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?',
                             "TRIVY_VERSION pin'i")
        self.assertIn("trivy=%s" % version, self._runbook,
                      "runbook'un beklenen `trivy=%s` satırı workflow'un "
                      "TRIVY_VERSION pin'iyle eşleşmeli — iki job tek "
                      "motorla taramalı" % version)

    def test_runbook_compares_the_two_modes(self):
        self.assertIn("### İki mod ve çıktılarının karşılaştırması",
                      self._runbook,
                      "runbook iki modu karşılaştırmalı — SKIP ve gerçek "
                      "koşum farklı kanıt miktarları üretir")
        for marker in ("SKIP modu (araç yok)", "Gerçek koşum (CI'daki beklenti)",
                       "verdict=PASS", "trivy_findings=0"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self._runbook,
                              "karşılaştırma tablosu bu işareti taşımalı: %s"
                              % marker)

    def test_runbook_separates_dispatch_from_schedule_evidence(self):
        """Elle (dispatch) koşumun cron kanıtı SAYILMAMALI — ayrım yazılı kalmalı.

        `workflow_dispatch` aynı workflow'u aynı runner'da çalıştırır, yani
        gerçek koşum yolunu kanıtlar; ama `schedule` tetikleyicisi ayrı bir
        yoldur. Bu ayrım kaybolursa birisi "elle koştu, cron çalışıyor"
        diyerek ilk Pazartesi koşumunu atlayabilir.
        """
        self.assertIn("Elle koşum ne kanıtlar, ne kanıtlamaz", self._runbook,
                      "runbook elle koşumun neyi kanıtladığını/ne "
                      "kanıtlamadığını açıkça ayırmalı")
        for marker in ("workflow_dispatch", "schedule",
                       "scheduler"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self._runbook,
                              "ayrım iki tetikleyiciyi adıyla koymalı: %s"
                              % marker)

    def test_runbook_documents_deviation_actions(self):
        self.assertIn("### Sapma tablosu", self._runbook,
                      "runbook sapma tablosu içermeli")
        for deviation in (
                "verdict=FAIL",
                "workflow_dispatch",
                "image-scan",
                "TRIVY_VERSION",
                "sha256sum",
                "gh run list --workflow docker-security.yml",
        ):
            with self.subTest(deviation=deviation):
                self.assertIn(deviation, self._runbook,
                              "sapma tablosu bu durumu kapsamalı: %s"
                              % deviation)

    def test_runbook_states_skip_is_not_ci_evidence(self):
        # Yeni değişmez: SKIP bir hata değildir, ama CI'da kanıt da
        # değildir — kurulum sessizce bozulduğunun işaretidir.
        self.assertIn("SKIP bir hata değildir, ama CI'da kanıt da değildir",
                      self._runbook,
                      "runbook, CI'da SKIP'in kanıt sayılmadığını açıkça "
                      "söylemeli (assert adımı bunu fail-closed'a bağlar)")


    def _skip_grep_token(self):
        """Script'ten türetilen SKIP **grep kalıbı** (kısa biçim).

        Sayım komutunda aranan kalıp mesajın başıdır (`SKIP: trivy yok`);
        mesajın tamamının birebir verilmesi ayrı bir K-testinin
        (test_runbook_quotes_skip_line_verbatim) görevidir. Burada da
        script'ten türetilir, sabit yazılmaz.
        """
        msg = self._from(self._sh, r'skip\s+"(trivy yok[^"]*)"',
                         "trivy SKIP mesajı")
        return "SKIP: %s" % msg.split(" — ")[0]

    def test_runbook_first_monday_requires_skip_count_zero(self):
        # İlk Pazartesi kabul ölçütü SKIP SAYIMIDIR. Yeşil job tek başına
        # yeterli değil: SKIP modu da exit 0 ve kanıt dosyası üretir, yalnız
        # güvenlik iddiası taşımaz. Bu yüzden bekleyen satır hem verdict
        # hem de SKIP sayımı ölçütünü taşımalı.
        row = next((ln for ln in self._runbook.splitlines()
                    if ln.startswith("| (henüz koşmadı")), "")
        self.assertTrue(row, "koşum kaydında bekleyen ilk Pazartesi satırı yok")
        self.assertIn("`schedule`", row,
                      "bekleyen satır schedule tetikleyicisiyle etiketlenmeli")
        self.assertIn("verdict=PASS", row,
                      "bekleyen satır gerçek koşum ölçütünü içermeli")
        self.assertRegex(row, re.escape(self._skip_grep_token()) + r".{0,20}0 kez",
                         "bekleyen satır SKIP sayımı ölçütünü de içermeli "
                         "(%s 0 kez)" % self._skip_grep_token())

    def test_runbook_deviation_table_covers_skip_appearing(self):
        # SKIP'in logda görünmesi kendi başına sapmadır. assert adımı onu
        # kırmızıya çevirir ama sebebi söylemez — teşhis ancak ayrı satırla
        # yönlendirilebilir.
        #
        # Satır KENDİSİ kapsanır: 'sha256sum' gibi jetonlar sapma tablosunda
        # başka satırlarda da geçtiği için bölüm genelinde aramak, SKIP
        # satırındaki teşhisin silinmesine izin verirdi (ölçüldü).
        sapma = self._runbook.split("### Sapma tablosu", 1)[1]
        sapma = sapma.split("### Koşum kaydı", 1)[0]
        row = next((ln for ln in sapma.splitlines()
                    if ln.startswith("| `SKIP")), "")
        self.assertTrue(row,
                        "sapma tablosunda SKIP'in görünmesini kapsayan "
                        "kendi satırı olmalı")
        for token in (self._skip_grep_token(),
                      "gh run view",
                      "sha256sum"):
            with self.subTest(token=token):
                self.assertIn(token, row,
                              "SKIP sapma satırı bu teşhisi taşımalı: %s"
                              % token)

    def test_runbook_first_monday_pins_measurements(self):
        # Doğrulama prosedürü iki karar verici ölçümü birebir pinlemeli.
        # Komutun TAMAMI aranır: sadece '--event schedule' diye aramak,
        # filtreyi yalnız prose'da geçen bir metne indirgerse yakalamaz
        # (ölçüldü: filtre komuttan silinince test geçiyordu).
        parts = self._runbook.split("### İlk Pazartesi doğrulaması", 1)
        self.assertEqual(len(parts), 2,
                         "ilk Pazartesi doğrulama bölümü yok")
        body = parts[1].split("### ", 1)[0]
        for needle in ("OK: verdict=PASS",
                       self._skip_grep_token(),
                       "gh run list --workflow docker-security.yml "
                       "--event schedule"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body,
                              "ilk Pazartesi bölümü ölçümü pinlemeli: %s"
                              % needle)


if __name__ == "__main__":
    unittest.main()
