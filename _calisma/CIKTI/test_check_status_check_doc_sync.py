#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_status_check_doc_sync.py — status-check doküman senkron kapısının
birim testleri.

Kapı (check_status_check_doc_sync.py), PUBLISH_SCENARIO.md ile
docs/branch-protection-guide/ içindeki ELLE yazılmış check sayılarını
status_checks.py türetimine (GATE_EXCLUDE + verify.yml job `name:`leri) bağlar.
Bu modül üç katmanı sınar:

  1. STATİK (her ortamda koşar — PyYAML gerekmez): SITES/LIST_SITES
     tablolarının kendi tutarlılığı — benzersiz id, regex grup sayısı ↔
     alan sayısı eşleşmesi, dört türetim anahtarının da en az bir beyanda
     denetlenmesi, liste türlerinin geçerliliği. Tablo bozulursa kapı
     "ölçtüm" derken hiçbir şey ölçmeyebilir; bu katman onu yakalar.
  2. MOCK METİN (her ortamda koşar): doğru beyan → bulgu yok; yanlış sayı →
     drift; beyan kaybolursa (0 eşleşme) / belirsizleşirse (2 eşleşme) →
     match-count bulgusu. Listelerde eksik/fazla öğe, bölge çapası kaybı ve
     iki regresyon: (a) satır başına birden fazla öğe (virgüllü id listesi)
     yalnız ilkini okumamalı, (b) end çapası start'tan SONRA aranmalı
     (`guide.html`'de `.erow` başka ekranda start'tan önce de geçiyor).
  3. GERÇEK AĞAÇ (PyYAML gerekir): türetim iç tutarlılığı
     (required + advisory + pr_only == total), required ad sayısı ==
     required, PR'da koşan required kapıların (label-gate/commit-msg-gate)
     ayırt edilebilmesi, kapının gerçek dokümanlarda YEŞİL olması ve
     `--json` sözleşmesi.

Kapı yeşil değilse bu modül de kırmızıdır — doküman sürüklenmesi commit'i
bloke eder (fail-closed; bilinçli olarak skip yok).
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_status_check_doc_sync as gate  # noqa: E402

try:
    import yaml  # noqa: F401  (yalnız gerektiğinde kullanılır)
    _HAVE_YAML = True
except ImportError:  # pragma: no cover — PyYAML'sız ortam
    _HAVE_YAML = False

needs_yaml = unittest.skipUnless(_HAVE_YAML, "PyYAML yok — türetim koşamaz")

ROOT = CIKTI.parent.parent
PRECOMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"


def _derived(**over):
    """Test için türetim sözlüğü (varsayılan: 3 required, 1 PR-only …)."""
    base = {
        "total": 6, "required": 3, "advisory": 2, "pr_only": 1,
        "required_names": ["Alpha gate", "Beta gate", "Gamma gate"],
        "pr_only_ids": ["comment-pr"],
        "pr_only_required_ids": ["beta-gate"],
    }
    base.update(over)
    return base


# ── 1) Statik: beyan tablosunun kendi tutarlılığı ──────────────────────────

class SiteTableTest(unittest.TestCase):
    def test_all_sites_are_declared(self):
        self.assertTrue(gate.SITES, "hiç sayı beyanı yok — kapı kör kalır")
        self.assertTrue(gate.LIST_SITES, "hiç liste beyanı yok")

    def test_site_ids_are_unique(self):
        ids = [s["id"] for s in gate.SITES] + [s["id"] for s in gate.LIST_SITES]
        self.assertEqual(len(ids), len(set(ids)), f"yinelenen site id: {ids}")

    def test_count_regex_groups_match_fields(self):
        """Her sayı beyanında grup sayısı == alan sayısı (sessiz kayma yok)."""
        for site in gate.SITES:
            groups = re.compile(site["pattern"]).groups
            self.assertEqual(
                groups, len(site["fields"]),
                f"{site['id']}: regex {groups} grup, {len(site['fields'])} alan")

    def test_every_derived_key_is_covered(self):
        """Dört türetim anahtarı da en az bir beyanda denetlenmeli."""
        covered = {f for site in gate.SITES for f in site["fields"]}
        self.assertEqual(covered, set(gate.DERIVED_KEYS),
                         f"denetlenmeyen türetim anahtarı: "
                         f"{set(gate.DERIVED_KEYS) - covered}")

    def test_sites_target_the_three_doc_files(self):
        files = {s["file"] for s in gate.SITES} | {s["file"]
                                                  for s in gate.LIST_SITES}
        self.assertEqual(files, {gate.PUBLISH, gate.GUIDE_README,
                                 gate.GUIDE_HTML})

    def test_list_sites_have_valid_kind_and_compilable_patterns(self):
        for site in gate.LIST_SITES:
            self.assertIn(site["kind"], ("required_names", "pr_only_ids"),
                          site["id"])
            for key in ("start", "end", "item"):
                re.compile(site[key])
            for skip in site["skip"]:
                re.compile(skip)

    def test_each_file_has_a_count_site(self):
        for rel in (gate.PUBLISH, gate.GUIDE_README, gate.GUIDE_HTML):
            self.assertTrue([s for s in gate.SITES if s["file"] == rel],
                            f"{rel} için sayı beyanı yok — dosya kapsam dışı "
                            "kalmış olabilir")


class DeclarationCoverageTest(unittest.TestCase):
    """Kapı körlüğü bekçisi: 'N status checks' biçimindeki HER beyan
    SITES'teki bir desenle kaplanmalı.

    Gerçek vaka (bu testin doğuşu): ADIM 6 ("Create") ekranındaki
    "9 status checks selected · strict" satırı kapsam dışında kalmıştı.
    ADIM 4 ve ADIM 7 beyanları doğru (15) olduğu için kapı, ekranın 9'unu
    hiç görmeden PASS dedi — fail-open. Bu test yeni ekranların da
    kapsanmasını zorlar; PyYAML gerektirmez.
    """

    DECL = re.compile(r"\d+ status checks?\b")

    def test_every_status_check_declaration_is_covered(self):
        for rel in (gate.PUBLISH, gate.GUIDE_README, gate.GUIDE_HTML):
            path = ROOT / rel
            if not path.is_file():
                self.skipTest(f"{rel} yok (izole checkout)")
            text = path.read_text(encoding="utf-8")
            spans = [m.span() for site in gate.SITES if site["file"] == rel
                     for m in re.finditer(site["pattern"], text, re.M)]
            for m in self.DECL.finditer(text):
                covered = any(s <= m.start() and m.end() <= e
                              for s, e in spans)
                line_no = text.count("\n", 0, m.start()) + 1
                self.assertTrue(
                    covered,
                    f"{rel}:{line_no} beyanı kapsanmıyor: {m.group(0)!r} — "
                    "SITES'e yeni bir site ekleyin (yoksa drift sessiz kalır)")


# ── 2) Mock metin: sayı ve liste beyanlarının denetimi ─────────────────────

class CountSiteTest(unittest.TestCase):
    site = {"id": "mock", "file": "mock.md",
            "pattern": r"toplam (\d+) check", "fields": ("required",)}

    def test_correct_number_passes(self):
        findings, matches = gate.check_counts("… toplam 3 check …", _derived(),
                                              self.site)
        self.assertEqual(findings, [])
        self.assertEqual(len(matches), 1)

    def test_wrong_number_is_drift(self):
        findings, _ = gate.check_counts("… toplam 9 check …", _derived(),
                                        self.site)
        self.assertEqual([f["kind"] for f in findings], ["drift"])
        self.assertEqual(findings[0]["doc"], 9)
        self.assertEqual(findings[0]["derived"], 3)

    def test_missing_site_fails_closed(self):
        findings, _ = gate.check_counts("metinde beyan yok", _derived(),
                                        self.site)
        self.assertEqual([f["kind"] for f in findings], ["match-count"])

    def test_ambiguous_site_fails_closed(self):
        text = "toplam 3 check\n… toplam 3 check\n"
        findings, _ = gate.check_counts(text, _derived(), self.site)
        self.assertEqual([f["kind"] for f in findings], ["match-count"])
        self.assertIn("2 eşleşme", findings[0]["detail"])

    def test_group_field_mismatch_raises(self):
        bad = {"id": "bad", "file": "mock.md", "pattern": r"(\d+)-(\d+)",
               "fields": ("required",)}
        with self.assertRaises(gate.MeasurementError):
            gate.check_counts("1-2", _derived(), bad)


class WriteModeTest(unittest.TestCase):
    """`--write`: sayı beyanları ELLE değil türetimden yazılmalı (asıl sözleşme).

    Bu katman olmadan `--write` sessizce yanlış yere rakam basabilir ya da
    yazdığını iddia edip hiçbir şey değiştirmeyebilirdi; ikisi de drift'i
    gizler. Burada (a) rakamların türetimden geldiği, (b) idempotent olduğu,
    (c) çapası kaybolmuş beyanda fail-closed davrandığı, (d) sayı dışı metne
    dokunmadığı pinlenir.
    """

    site = {"id": "mock", "file": "mock.md",
            "pattern": r"toplam (\d+) check", "fields": ("required",)}

    def test_rewrite_uses_derived_value_and_keeps_prose(self):
        text = "önce\n… toplam 9 check …\nsonra\n"
        out, changed = gate.rewrite_counts(text, _derived(), self.site)
        self.assertTrue(changed)
        self.assertEqual(out, "önce\n… toplam 3 check …\nsonra\n")

    def test_rewrite_is_idempotent(self):
        text = "… toplam 3 check …"
        out, changed = gate.rewrite_counts(text, _derived(), self.site)
        self.assertFalse(changed, "doğru sayı yine değiştirildi")
        self.assertEqual(out, text)

    def test_rewrite_refuses_missing_or_ambiguous_anchor(self):
        for text in ("beyan yok", "toplam 3 check\ntoplam 4 check\n"):
            with self.assertRaises(gate.MeasurementError):
                gate.rewrite_counts(text, _derived(), self.site)

    @needs_yaml
    def test_write_follows_verify_yml_not_hardcoded_number(self):
        """Workflow'a job eklenirse sayılar --write ile OTOMATİK değişmeli.

        Geçici ağaç: gerçek verify.yml + PUBLISH_SCENARIO.md kopyası. Kopyaya
        yeni bir required job eklenir; `--write` sonrası doküman sayıları yeni
        türetime eşit, eski (14) değil olmalı.
        """
        import yaml
        td = pathlib.Path(tempfile.mkdtemp())
        try:
            (td / ".github" / "workflows").mkdir(parents=True)
            wf = yaml.safe_load(
                (ROOT / ".github" / "workflows" / "verify.yml")
                .read_text(encoding="utf-8"))
            wf["jobs"]["zz-extra-gate"] = {
                "name": "Zz extra gate", "runs-on": "ubuntu-latest",
                "steps": [{"run": "true"}],
            }
            (td / ".github" / "workflows" / "verify.yml").write_text(
                yaml.safe_dump(wf, sort_keys=False), encoding="utf-8")
            doc = td / gate.PUBLISH
            doc.parent.mkdir(parents=True)
            doc.write_text((ROOT / gate.PUBLISH).read_text(encoding="utf-8"),
                           encoding="utf-8")

            before = gate.derive(td)
            self.assertGreater(before["required"], 14,
                               "eklenen job türetime yansımadı — test kör")
            derived, written = gate.write_counts(td, {gate.PUBLISH})
            self.assertEqual(derived["required"], before["required"])
            self.assertEqual(written, [gate.PUBLISH])

            text = doc.read_text(encoding="utf-8")
            _d, findings, _t = gate.check(td, {gate.PUBLISH})
            drift = [f for f in findings if f["kind"] == "drift"]
            self.assertEqual(drift, [], f"--write sonrası sayı drift'i: {drift}")
            self.assertIn(f"toplam {before['required']} check", text)

            # İkinci yazım dosyaya dokunmamalı (idempotent).
            _d, again = gate.write_counts(td, {gate.PUBLISH})
            self.assertEqual(again, [], "idempotent değil — her koşuda yazıyor")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_cli_rejects_unknown_file_scope(self):
        r = subprocess.run(
            [sys.executable, str(CIKTI / "check_status_check_doc_sync.py"),
             "--write", "--file", "docs/YOK.md"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("bilinmeyen --file", r.stderr)

    def test_cli_write_and_json_are_exclusive(self):
        r = subprocess.run(
            [sys.executable, str(CIKTI / "check_status_check_doc_sync.py"),
             "--write", "--json"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class ListSiteTest(unittest.TestCase):
    names_site = {
        "id": "mock-names", "file": "mock.md", "kind": "required_names",
        "start": r"^LIST-START$", "end": r"^LIST-END$",
        "item": r"^\s*-\s*`([^`]+)`", "skip": (),
    }

    def test_matching_list_passes(self):
        text = ("LIST-START\n- `Alpha gate`\n- `Beta gate`\n- `Gamma gate`\n"
                "LIST-END\n")
        findings, items = gate.check_list(text, _derived(), self.names_site)
        self.assertEqual(findings, [])
        self.assertEqual(len(items), 3)

    def test_missing_and_extra_items_are_reported(self):
        text = ("LIST-START\n- `Alpha gate`\n- `Delta gate`\nLIST-END\n")
        findings, _ = gate.check_list(text, _derived(), self.names_site)
        self.assertEqual(findings[0]["kind"], "list-drift")
        self.assertEqual(findings[0]["missing"], ["Beta gate", "Gamma gate"])
        self.assertEqual(findings[0]["extra"], ["Delta gate"])

    def test_lost_region_fails_closed(self):
        findings, _ = gate.check_list("LIST-START\n- `Alpha gate`\n",
                                      _derived(), self.names_site)
        self.assertEqual(findings[0]["kind"], "match-count")

    def test_end_anchor_searched_after_start(self):
        """`end` metni start'tan ÖNCE de geçebilir (guide.html `.erow`)."""
        text = "LIST-END\n… başka ekran …\nLIST-START\n- `Alpha gate`\n" \
               "- `Beta gate`\n- `Gamma gate`\nLIST-END\n"
        findings, items = gate.check_list(text, _derived(), self.names_site)
        self.assertEqual(findings, [], "start'tan önceki end çapası bölgeyi "
                                       "ters çevirdi")
        self.assertEqual(len(items), 3)

    def test_multiple_items_per_line_are_all_read(self):
        """Virgüllü id listesi: satır başına tek eşleşme almak listeyi eksik okurdu."""
        site = dict(self.names_site, kind="pr_only_ids",
                    item=r"([a-z][a-z0-9]*(?:-[a-z0-9]+)+)")
        text = "LIST-START\ncomment-pr, extra-gate\nLIST-END\n"
        findings, items = gate.check_list(text, _derived(), site)
        self.assertEqual(sorted(items), ["comment-pr", "extra-gate"])
        self.assertEqual(findings[0]["extra"], ["extra-gate"])

    def test_unknown_kind_raises(self):
        site = dict(self.names_site, kind="bogus")
        with self.assertRaises(gate.MeasurementError):
            gate.check_list("LIST-START\nLIST-END\n", _derived(), site)


class ExclusionTest(unittest.TestCase):
    def test_exclusion_anchors_still_exist(self):
        """Kapsam dışı gerekçeleri doğrulanabilir kalmalı (bayat gerekçe yok)."""
        for excl in gate.EXCLUSIONS:
            text = (ROOT / excl["file"]).read_text(encoding="utf-8")
            self.assertIn(excl["anchor"], text,
                          f"gerekçe çürüdü: {excl['file']} — "
                          f"{excl['anchor']!r} yok ({excl['reason']})")

    def test_exclusions_are_not_count_sites(self):
        """Kapsam dışı bırakılan metin bir beyan kalıbına UYMAMALI (çelişki)."""
        for excl in gate.EXCLUSIONS:
            for site in gate.SITES:
                self.assertIsNone(
                    re.search(site["pattern"], excl["anchor"]),
                    f"{excl['anchor']!r} hem kapsam dışı hem {site['id']} "
                    "beyanı — çelişki")


# ── 3) Gerçek ağaç ─────────────────────────────────────────────────────────

@needs_yaml
class RealTreeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.derived = gate.derive(ROOT)

    def test_derivation_is_internally_consistent(self):
        d = self.derived
        self.assertEqual(d["total"], d["required"] + d["advisory"] + d["pr_only"],
                         "kategori split'i toplamı tutmuyor — türetim bozuk")
        self.assertEqual(len(d["required_names"]), d["required"])
        self.assertEqual(len(d["pr_only_ids"]), d["pr_only"])
        self.assertEqual(sorted(d["required_names"]), d["required_names"],
                         "required adları sıralı olmalı (deterministik çıktı)")

    def test_pr_only_required_gates_are_distinguished(self):
        """PR'da koşan ama BİLEREK required kapılar ayrı raporlanmalı.

        Aksi hâlde 'PR-only' kümesi required kapıları da yutar ve dokümandaki
        'N required + M advisory + K PR-only' split'i yanlış türetilir.
        """
        self.assertTrue(self.derived["pr_only_required_ids"],
                        "PR'da koşan required kapı tespit edilemedi — `if:` "
                        "deseni ya da GATE_EXCLUDE değişmiş olabilir")
        overlap = set(self.derived["required_names"]) & set(
            self.derived["pr_only_ids"])
        self.assertEqual(overlap, set(), "required bir job pr_only sayılmış")

    def test_cli_output_and_gate_derivation_agree(self):
        """Operatörün kopyaladığı artefakt `status_checks.py --json`.

        Kapı türetimi modül API'sinden (`gate_jobs()`) gelir; CLI çıktısı ayrı
        bir kod yolundan üretilir. İkisi ayrışırsa dokümanlar API'yi doğrular
        ama operatör GitHub'a FARKLI bir listeyi girer — bu yüzden ikisi
        burada pinlenir (dokümanların türetildiği çıktı, gerçekten söylenen
        çıktı olmalı).
        """
        r = subprocess.run(
            [sys.executable, str(CIKTI / "status_checks.py"), "--json"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        cli_ids = set(payload["gate_jobs"])
        self.assertEqual(
            cli_ids, set(gate._gate_job_ids(ROOT)),
            "status_checks CLI `gate_jobs` ↔ kapının türetimi ayrıştı")
        self.assertEqual(len(cli_ids), self.derived["required"],
                         "CLI required sayısı türetimle uyuşmuyor")

    def test_real_docs_are_in_sync(self):
        """ASIL sözleşme: gerçek dokümanlar türetimle birebir olmalı."""
        _derived, findings, _texts = gate.check(ROOT)
        self.assertEqual(findings, [], f"doküman drift'i: {findings}")

    def test_publish_scenario_is_in_sync(self):
        """PUBLISH_SCENARIO.md KENDİ BAŞINA türetimle birebir kalsın.

        Rehber (guide.html/README) HTML+PNG'ye bağlı ayrı bir dosya kümesi;
        oradaki drift bu dosyanın sözleşmesini gevşetmemeli. Bu test PUBLISH
        sayı+listelerini elle düzenlemeyi kırmızıya çevirir: sayılar yalnızca
        `--write` ile (verify.yml türetiminden) güncellenir.
        """
        _derived, findings, _texts = gate.check(ROOT, {gate.PUBLISH})
        self.assertEqual(
            findings, [],
            f"PUBLISH_SCENARIO.md türetimden koptu: {findings} — düzeltme: "
            "python3 _calisma/CIKTI/check_status_check_doc_sync.py --write "
            "--file docs/PUBLISH_SCENARIO.md")

    def test_main_exit_codes(self):
        r = subprocess.run(
            [sys.executable, str(CIKTI / "check_status_check_doc_sync.py"),
             "--json"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["derived"], self.derived)
        self.assertIn("ps-job-categories", payload["sites"])
        self.assertIn("guide-html-checkboxes", payload["list_sites"])

    def test_measurement_error_is_exit_2(self):
        """Ölçüm imkânsızsa sessiz PASS yok: exit 2 + hata mesajı."""
        td = pathlib.Path(tempfile.mkdtemp())
        try:
            r = subprocess.run(
                [sys.executable, str(CIKTI / "check_status_check_doc_sync.py"),
                 "--root", str(td)], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("ÖLÇÜM İMKÂNSIZ", r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_doc_content_mutation_turns_gate_red(self):
        """Mutasyon kanıtı: dokümandaki bir sayı bozulursa kapı kırmızı olur.

        Gerçek dokümanlara dokunmadan, geçici bir kök ağaçta üç dokümanın
        kopyası + mutant sayı kullanılır (kaçış yolu: kopyalar gerçek ağaçtan).
        """
        td = pathlib.Path(tempfile.mkdtemp())
        try:
            (td / ".github" / "workflows").mkdir(parents=True)
            shutil.copy(ROOT / ".github" / "workflows" / "verify.yml",
                        td / ".github" / "workflows" / "verify.yml")
            mutated = []
            for rel in (gate.PUBLISH, gate.GUIDE_README, gate.GUIDE_HTML):
                # Her dosyada KENDİ beyanından birini boz (README'de 'toplam'
                # yok; sabit bir metin seçmek testi yanlış yere bağlardı).
                site = [s for s in gate.SITES if s["file"] == rel][0]
                dest = td / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                text = (ROOT / rel).read_text(encoding="utf-8")
                m = re.search(site["pattern"], text, re.M)
                self.assertIsNotNone(m, f"mutasyon çapası bulunamadı: {rel}")
                mutant = text[:m.start(1)] + "99" + text[m.end(1):]
                self.assertNotEqual(text, mutant, f"mutasyon etkisiz: {rel}")
                mutated.append(site["id"])
                dest.write_text(mutant, encoding="utf-8")
            _d, findings, _t = gate.check(td)
            drift = [f for f in findings if f["kind"] == "drift"]
            caught = {f["site"] for f in drift}
            # Kopya ağaç gerçek dokümanların kopyasıdır: mevcut drift de
            # gelebilir; ASIL iddia mutasyonun yakalanmasıdır (⊇).
            self.assertTrue(set(mutated) <= caught,
                            f"bozulan beyan yakalanmadı: "
                            f"{set(mutated) - caught}")
            mutant_rows = [f for f in drift if f["site"] in set(mutated)]
            self.assertEqual({f["doc"] for f in mutant_rows}, {99},
                             "mutant değer okunmamış")
            self.assertTrue(all(f["derived"] != 99 for f in drift),
                            "türetim mutanttan geliyor — karşılaştırma vakum")
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ── Hook wiring ────────────────────────────────────────────────────────────

class HookWiringTest(unittest.TestCase):
    """pre-commit hook'u venv-guard'lı olmalı (PyYAML sahte-PASS koruması)."""

    @classmethod
    def setUpClass(cls):
        text = PRECOMMIT_CONFIG.read_text(encoding="utf-8")
        m = re.search(
            r"^( *)- id: check-status-check-doc-sync\n(.*?)(?=^\1- id: |^\1\Z)",
            text, re.M | re.S)
        cls.block = m.group(0) if m else None

    def test_hook_exists_with_venv_guard(self):
        self.assertIsNotNone(self.block, "check-status-check-doc-sync hook'u "
                                         "config'te yok")
        self.assertIn("_calisma/.venv_z3/bin/python", self.block,
                      "hook entry repo venv'ini seçmeli (PyYAML sahte-PASS "
                      "guard'ı)")
        self.assertIn("check_status_check_doc_sync.py", self.block)

    def test_hook_is_change_triggered(self):
        """Yalnız beyan dosyaları/workflow/paylaşılan türetim değişince koşar."""
        self.assertIn("files:", self.block)
        self.assertIn("PUBLISH_SCENARIO", self.block)
        self.assertIn("branch-protection-guide", self.block)
        self.assertIn("verify.yml", self.block)
        self.assertNotIn("always_run: true", self.block)


if __name__ == "__main__":
    unittest.main()
