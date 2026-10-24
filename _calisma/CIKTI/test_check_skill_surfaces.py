#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_skill_surfaces.py — envanter kapısının sözleşme testleri.

Seam = kapı CLI'si + `check()`/`parse_manifest()` saf fonksiyonları. Ağaç
testleri HERMETIKTİR: geçici kökte sahte package.json + sahte yüzey yolu
üretilir, gerçek repo manifest'i dokunulmadan okunur. Gerçek-repo
invariant'ları ayrı sınıfta (kapının asıl işi).

Kritik sözleşmeler:
  - iki yönlü paket denetimi: hayalet satır (manifest'te var, ağaçta yok)
    VE kayıtsız paket (ağaçta var, manifest'te yok) İKİSİ DE FAIL
  - zero-surface: imza paketi GÖRÜNÜRSE FAIL; alan manifest'te yoksa FAIL
  - identity takma adları (snapshot mirror'lar) hayalet denetiminden muaf
  - arç gürültüsü (prettier/typescript/…) kayıtsız sayılmaz; küme kapalıdır
  - yol varlığı: eksik yüzey fail-closed
  - duplicate satır FAIL; --json tek belge; usage error rc=2
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import check_skill_surfaces as gate  # noqa: E402

REAL_MANIFEST = CIKTI / "skill_surfaces.list"
REAL_ROOT = CIKTI.parent.parent


def _capture(argv):
    """CLI'yi çalıştırır; (rc, stdout, stderr) döndürür.

    argparse bilinmeyen bayrakta SystemExit(2) FIRLATIR — rc'ye çevrilir
    (CLI sözleşmesi: kullanım hatası rc=2).
    """
    buf, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = gate.main(argv) or 0
    except SystemExit as exc:
        rc = exc.code or 0
    return rc, buf.getvalue(), err.getvalue()


class FakeRepo:
    """Geçici kök: package.json'lar + yüzey yolları üretir."""

    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.add_path = None
        self.root = self._td.name

    def cleanup(self):
        self._td.cleanup()

    def package(self, rel, deps, dev=None):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {"name": rel.split("/")[0]}
        if deps:
            data["dependencies"] = {name: "1.0.0" for name in deps}
        if dev:
            data["devDependencies"] = {name: "1.0.0" for name in dev}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def surface(self, rel):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# yüzey\n")

    def manifest(self, text):
        path = os.path.join(self.root, "skill_surfaces.list")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


class ParseTest(unittest.TestCase):
    def test_three_fields_and_inline_comment(self):
        entries, problems = gate.parse_manifest(
            "nextjs  next  apps/dashboard-next  # açıklama\n"
            "# tam yorum satırı\n"
            "rn-expo  zero-surface  findings.md\n")
        self.assertEqual(problems, [])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["domain"], "nextjs")
        self.assertEqual(entries[0]["path"], "apps/dashboard-next")
        self.assertFalse(entries[0]["zero"])
        self.assertTrue(entries[1]["zero"])

    def test_malformed_line_is_a_problem(self):
        entries, problems = gate.parse_manifest("sadece-iki  alan\n")
        self.assertEqual(entries, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("3 alan", problems[0])


class TwoWayPackageTest(unittest.TestCase):
    def test_unlisted_package_fails(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["brand-new-pkg",
                                                   "some-unknown-sdk"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("web  brand-new-pkg  apps/one/src.ts\n")
            ok, findings, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertEqual([u["package"] for u in report["unlisted"]],
                             ["some-unknown-sdk"])
        finally:
            repo.cleanup()

    def test_phantom_row_fails(self):
        repo = FakeRepo()
        try:
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("web  removed-pkg  apps/one/src.ts\n")
            ok, findings, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertIn("removed-pkg", report["phantom"])
        finally:
            repo.cleanup()

    def test_listed_signature_passes(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["next"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("nextjs  next  apps/one/src.ts\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
        finally:
            repo.cleanup()

    def test_dev_dependency_also_counts(self):
        # devDependencies alan yüzeyi sayılır: next dashboard'da dependencies
        # ama diğer paketlerde dev'de görünebilir — ikisi de imzadır.
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", None, dev=["react"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("react-web  react  apps/one/src.ts\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
        finally:
            repo.cleanup()


class ZeroSurfaceTest(unittest.TestCase):
    def test_signature_appearance_breaks_the_claim(self):
        repo = FakeRepo()
        try:
            repo.package("apps/mobile/package.json", ["react-native"])
            repo.surface("apps/web/src.ts")
            manifest = repo.manifest(
                "web  react  apps/web/src.ts\n"
                "rn-expo  zero-surface  apps/web/src.ts\n")
            ok, findings, report = gate.check(root=repo.root, manifest=manifest,
                                              require_zero_domains=False)
            self.assertFalse(ok)
            self.assertTrue(report["zero_violations"])
            violation = next(f for f in findings if "ZERO-SURFACE ihlali" in f)
            self.assertIn("react-native", violation)
            # zero-surface paketi ÇİFT raporlanmamalı (unlisted boş kalır):
            self.assertEqual(
                [u["package"] for u in report["unlisted"]], [],
                "zero imzası unlisted olarak da raporlandı — gürültü")
        finally:
            repo.cleanup()

    def test_zero_domain_missing_from_manifest_fails(self):
        # rn-expo imzası görünmüyor AMA manifest'te zero-surface kaydı da yok
        # → sıfır-yüzey iddiası yazılı değil (sessiz kapsam kaybı).
        repo = FakeRepo()
        try:
            repo.surface("apps/web/src.ts")
            manifest = repo.manifest("web  react  apps/web/src.ts\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertTrue(any("zero-surface alan manifest'te kayıpsız: rn-expo"
                                in f for f in findings))
        finally:
            repo.cleanup()

    def test_zero_claim_holds_when_signatures_absent(self):
        repo = FakeRepo()
        try:
            repo.package("apps/web/package.json", ["react"])
            repo.surface("apps/web/src.ts")
            repo.surface("findings.md")
            manifest = repo.manifest(
                "web  react  apps/web/src.ts\n"
                "rn-expo  zero-surface  findings.md\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
        finally:
            repo.cleanup()


class IdentityAndNoiseTest(unittest.TestCase):
    def test_identity_alias_is_not_phantom(self):
        # Snapshot mirror'lar bağımlılık taşımaz — identity satırı hayalet
        # SAYILMAMALIDIR (yoksa kapı kendi meşru satırlarını kırardı; ölçüldü:
        # ilk koşumda 4 'hayalet' bulgusu kapıyı kendi manifest'inde kırmıştı).
        repo = FakeRepo()
        try:
            repo.surface("design-system/stripe/tokens.css")
            alias = next(iter(gate.IDENTITY_ALIASES))
            manifest = repo.manifest("%s  %s  design-system/stripe/tokens.css\n"
                                     % (alias, alias))
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
            self.assertEqual(gate.IDENTITY_ALIASES,
                             {"stripe-tokens", "linear-tokens",
                              "primer-tokens", "vercel-tokens"},
                             "identity kümesi kapalıdır — yeni girdi gerekçeli "
                             "olmalı (kör genişleme yok)")
        finally:
            repo.cleanup()

    def test_toolchain_noise_is_not_unlisted(self):
        # prettier/typescript gibi araçlar alan yüzeyi değildir; kayıtsız
        # ihlali ÜRETMEZLER (küme kapalı — yeni girdi testte gerekçelenir).
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["typescript", "prettier"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("web  react  apps/one/src.ts\n"
                                     "web  react  apps/one/src.ts\n")
            # duplicate satır FAIL verir ama 'unlisted' boş kalmalı
            ok, findings, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)  # duplicate yüzünden
            self.assertEqual(report["unlisted"], [],
                             "araç paketleri kayıtsız sayılmamalı")
        finally:
            repo.cleanup()

    def test_unknown_package_still_flagged(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["some-unknown-sdk"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("web  react  apps/one/src.ts\n")
            ok, findings, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertEqual(report["unlisted"][0]["package"], "some-unknown-sdk")
        finally:
            repo.cleanup()

    def test_types_packages_are_exempt(self):
        repo = FakeRepo()
        try:
            # @types/react muaf; react'in KENDİSİ imzadır ve devDependencies
            # olarak da görünürlüdür (iki ayrı paket aynı dosyada).
            repo.package("apps/one/package.json", None,
                         dev=["@types/react", "react"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("react-web  react  apps/one/src.ts\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
        finally:
            repo.cleanup()


class PathAndDuplicateTest(unittest.TestCase):
    def test_missing_surface_path_fails(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["next"])
            manifest = repo.manifest("nextjs  next  apps/one/GONE.ts\n")
            ok, findings, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertIn("apps/one/GONE.ts", report["missing_paths"])
        finally:
            repo.cleanup()

    def test_no_path_check_mode_skips_path_audit(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["next"])
            manifest = repo.manifest("nextjs  next  apps/one/GONE.ts\n")
            ok, findings, _ = gate.check(root=repo.root, manifest=manifest,
                                         require_paths=False,
                                         require_zero_domains=False)
            self.assertTrue(ok, findings)
        finally:
            repo.cleanup()

    def test_duplicate_row_fails(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["next"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest(
                "nextjs  next  apps/one/src.ts\n"
                "nextjs  next  apps/one/src.ts\n")
            ok, _, report = gate.check(root=repo.root, manifest=manifest)
            self.assertFalse(ok)
            self.assertEqual(len(report["duplicate_rows"]), 1)
        finally:
            repo.cleanup()


class CliTest(unittest.TestCase):
    def test_json_is_one_document(self):
        rc, out, _ = _capture(["--json"])
        payload = json.loads(out)
        self.assertIn(rc, (0, 1))
        self.assertIn("ok", payload)
        self.assertIn("entries", payload)

    def test_usage_error_on_unknown_flag(self):
        rc, _, err = _capture(["--nope"])
        self.assertEqual(rc, 2)

    def test_update_suggests_but_does_not_write(self):
        repo = FakeRepo()
        try:
            repo.package("apps/one/package.json", ["some-unknown-sdk"])
            repo.surface("apps/one/src.ts")
            manifest = repo.manifest("web  react  apps/one/src.ts\n")
            rc, out, _ = _capture(["--root", repo.root,
                                   "--manifest", manifest, "--update"])
            self.assertEqual(rc, 1)
            self.assertIn("--update ÖNERİSİ", out)
            self.assertIn("some-unknown-sdk", out)
            self.assertIn("alanı elle atayın", out)
            # manifest DOSYASI değişmemeli — öneri yazmaz
            with open(manifest, encoding="utf-8") as fh:
                self.assertNotIn("some-unknown-sdk", fh.read())
        finally:
            repo.cleanup()


class RealRepoTest(unittest.TestCase):
    """Kapının asıl işi: gerçek repo manifest'i ile senkron olmalı."""

    def test_real_repo_is_in_sync(self):
        ok, findings, report = gate.check()
        self.assertTrue(ok, "gerçek repo envanteri bayat: %s" % findings)
        self.assertGreaterEqual(report["entries"], 15)
        self.assertEqual(sorted(report["zero_domains"]),
                         ["rn-expo", "wrangler", "xlsx"])

    def test_real_gate_cli_passes(self):
        rc, out, _ = _capture([])
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_manifest_declares_the_contract_header(self):
        # Başlık biçimi sözleşmeyi taşır: biçim bozulursa (sütun sayısı vs.)
        # parse_manifest zaten yakalar; bu pin başlığın VARLIĞINI korur.
        text = REAL_MANIFEST.read_text(encoding="utf-8")
        self.assertIn("check_skill_surfaces.py", text)
        self.assertIn("zero-surface", text)

    def test_zero_signatures_cover_the_audited_domains(self):
        # 2026-09-19 sıfır-yüzey denetimlerinin ALANLARI manifest'te olmalı:
        # rn-expo (RN/Expo), wrangler (Workers), xlsx (spreadsheet).
        for domain in ("rn-expo", "wrangler", "xlsx"):
            self.assertIn(domain, gate.ZERO_SIGNATURES)
        self.assertIn("react-native", gate.ZERO_SIGNATURES["rn-expo"])
        self.assertIn("expo", gate.ZERO_SIGNATURES["rn-expo"])
        self.assertIn("wrangler", gate.ZERO_SIGNATURES["wrangler"])
        self.assertIn("xlsx", gate.ZERO_SIGNATURES["xlsx"])

    def test_known_signatures_are_consistent_with_manifest_domains(self):
        # KEŞİF haritası (KNOWN_SIGNATURES) manifest'le TUTARLI olmalı:
        # harita bir alanı bilmiyorsa o alanın satırları kayıtsız sanılır.
        text = REAL_MANIFEST.read_text(encoding="utf-8")
        entries, problems = gate.parse_manifest(text)
        self.assertEqual(problems, [])
        for entry in entries:
            if entry["zero"] or entry["package"] in gate.IDENTITY_ALIASES:
                continue
            self.assertIn(entry["package"], gate.KNOWN_SIGNATURES,
                          "manifest paketi keşif haritasında yok: %s"
                          % entry["package"])
            self.assertEqual(gate.KNOWN_SIGNATURES[entry["package"]],
                             entry["domain"],
                             "harita-alanı manifest-alanıyla uyuşmuyor: %s"
                             % entry["package"])


if __name__ == "__main__":
    unittest.main()
