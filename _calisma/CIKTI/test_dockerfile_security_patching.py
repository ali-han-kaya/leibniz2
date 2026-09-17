#!/usr/bin/env python3
"""test_dockerfile_security_patching.py — Dockerfile güvenlik-yama deseni kapısı.

docs/DOCKER_SECURITY_PATCHING.md'de dokümante edilen genelleştirilmiş
güvenlik-yama desenini Dockerfile üzerinde sözleşme satırlarıyla sabitler:

  1) SECURITY_PATCH_PACKAGES ARG'si CVE-defteri girdisini default olarak
     taşır (libpcre2-8-0 floor'u + CVE kimlikleri) — kalıcı, işlenmiş kayıt.
  2) Yama YALNIZ etkilenen pakete uygulanır (--only-upgrade); genel
     apt-get upgrade/dist-upgrade yasaktır (taban sürüm kayması, diff
     yüzeyi patlaması).
  3) apt hijyeni: --no-install-recommends + /var/lib/apt/lists temizliği.
  4) Kanıt satırı: kurulan sürümler build log'una yazılır (dpkg-query).
  5) Dağıtım pini: python:3.11-slim-bookworm (trixie genç paket seti
     unfixed CRITICAL/HIGH taşır — bkz. Dockerfile yorumu).
  6) pip katmanı aynı desen: --upgrade "pkg>=floor" — floorsuz toplu
     pip upgrade yasaktır.
  7) Doküman sözleşmesi: kapalı döngü, CVE-defteri ve smoke aracı
     dokümante olmalı.

Desen bozulursa (floor silinmesi, tüm-upgrade'e geçiş, hijyen kaybı)
test fail eder → commit bloke olur (fail-closed). stdlib-only, OFFLINE.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
DOC = ROOT / "docs" / "DOCKER_SECURITY_PATCHING.md"


class TestDockerfileSecurityPatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._df = DOCKERFILE.read_text(encoding="utf-8")
        cls._doc = DOC.read_text(encoding="utf-8")

    def test_patch_layer_present_with_cve_ledger_default(self):
        # ARG default'u floor girdisini taşır + defter CVE kimlikleriyle kayıtlı.
        self.assertIn("ARG SECURITY_PATCH_PACKAGES=", self._df)
        self.assertIn("libpcre2-8-0=10.42-1+deb12u1", self._df)
        self.assertIn("CVE-2026-86145", self._df)
        self.assertIn("CVE-2026-89161", self._df)

    def test_targeted_only_upgrade_not_full_upgrade(self):
        # Yalnız etkilenen paket; genel upgrade/dist-upgrade yasak.
        self.assertIn("--only-upgrade $SECURITY_PATCH_PACKAGES", self._df)
        for forbidden in ("apt-get upgrade", "apt-get dist-upgrade",
                          "apt upgrade", "apt dist-upgrade"):
            self.assertNotIn(forbidden, self._df,
                             f"genel yama yasak: {forbidden}")

    def test_apt_hygiene(self):
        # Recommends'siz kurulum + liste temizliği (katman kalıntısı yok).
        self.assertIn("--no-install-recommends", self._df)
        self.assertIn("rm -rf /var/lib/apt/lists/*", self._df)

    def test_patch_evidence_dpkg_query(self):
        # Kanıt: yamalanan sürümler build log'una yazılır.
        self.assertIn("dpkg-query -W", self._df)
        # Regresyon (canlı build'de ölçüldü): dpkg-query apt'ın
        # 'pkg=sürüm' sözdizimini kabul etmez — yalın paket adı gerekir;
        # kanıt satırı sürüm ekini kırpılmalı (sed), ham ARG'yie geçmemeli.
        self.assertIn("sed 's/=.*//'", self._df)
        self.assertNotIn(
            "dpkg-query -W -f='${Package}\\t${Version}\\n' $SECURITY_PATCH_PACKAGES",
            self._df,
            "dpkg-query'ye ham 'pkg=sürüm' ARG'si geçilemez (canlı build'de patladı)")

    def test_base_image_bookworm_pin(self):
        # Her iki stage de bookworm pininde (trixie genç paket seti riskli).
        pins = [ln for ln in self._df.splitlines()
                if ln.startswith("FROM ")]
        self.assertEqual(len(pins), 2, f"iki stage beklenir: {pins}")
        for ln in pins:
            self.assertIn("python:3.11-slim-bookworm", ln,
                          f"dağıtım pini kaymış: {ln}")

    def test_pip_floor_pattern(self):
        # Python zinciri aynı desen: floor'lu upgrade.
        self.assertIn('pip install --no-cache-dir --upgrade "setuptools>=80"',
                      self._df)
        self.assertIn('"wheel>=0.46.2"', self._df)
        # Fail-closed: floorsuz toplu pip upgrade satırı yasak.
        for ln in self._df.splitlines():
            s = ln.strip()
            if s.startswith("pip install") and "--upgrade" in s:
                self.assertRegex(
                    s, r"--upgrade\s+[\"'][A-Za-z0-9_.-]+(>=|==)",
                    f"floorsuz pip upgrade: {s}")

    def test_doc_contract(self):
        # Desenin dokümanı: kapalı döngü + defter + smoke aracı + katkı sözleşmesi.
        for token in ("SECURITY_PATCH_PACKAGES",
                      "Kapalı döngü",
                      "CVE-defteri",
                      "libpcre2-8-0",
                      "CVE-2026-86145",
                      "10.42-1+deb12u1",
                      "docker_security_smoke.sh",
                      "Katkı sözleşmesi"):
            self.assertIn(token, self._doc,
                          f"doküman sözleşmesi eksik: {token}")
        # Dockerfile dokümana bağlanmalı (keşfedilebilirlik).
        self.assertIn("docs/DOCKER_SECURITY_PATCHING.md", self._df)


if __name__ == "__main__":
    unittest.main()
