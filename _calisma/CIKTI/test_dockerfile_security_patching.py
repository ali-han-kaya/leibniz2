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
import re
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

    def test_precommit_hook_triggers_on_dockerfile_change(self):
        # Commit-anında tetikleme sözleşmesi: Dockerfile değişince sözleşme
        # süiti koşar; değişim-farkında (always_run YOK — başka dosyalı
        # committe koşmaz, nedensel sinyal korunur).
        cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn("- id: check-dockerfile-security-patching", cfg,
                      "pre-commit hook'u config'de yok")
        block = next(b for b in cfg.split("\n      - id: ")
                     if b.startswith("check-dockerfile-security-patching"))
        self.assertIn("test_dockerfile_security_patching", block,
                      "hook sözleşme süitini çağırmalı")
        self.assertRegex(block, r"files: \^Dockerfile\$",
                         "değişim-farkında tetikleme: files Dockerfile'ı eşlemeli")
        # Anahtar-formu araması: description prose'ündeki geçiş sayılmaz
        # (yoksa hook'un kendi açıklaması testi tuzağa düşürür).
        self.assertIsNone(
            re.search(r"^\s*always_run:", block, re.M),
            "değişim-farkında: always_run anahtarı olmamalı (her committe koşmaz)")
        # Regresyon (gerçek koşumda ölçüldü): pass_filenames true kalırsa
        # pre-commit 'Dockerfile'ı unittest'e arg olarak ekler →
        # "No module named 'Dockerfile'" error.
        self.assertIn("pass_filenames: false", block,
                      "dosya adları unittest'e arg olarak geçmemeli")

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

    def test_pip_layer_arg_mechanism(self):
        # Python zinciri apt katmanıyla TEK MEKANİZMADA: floors
        # PYTHON_SECURITY_PATCH_PACKAGES ARG default'unda yaşar (tek kopya,
        # global) ve her stage yeniden beyan eder; RUN satırları hardcoded
        # floor yerine ARG genişlemesi kullanır.
        self.assertIn('ARG PYTHON_SECURITY_PATCH_PACKAGES="setuptools>=80 wheel>=0.46.2"',
                      self._df, "pip floor default'u ARG'de olmalı")
        stage_redeclares = [ln for ln in self._df.splitlines()
                            if ln.strip() == "ARG PYTHON_SECURITY_PATCH_PACKAGES"]
        self.assertEqual(len(stage_redeclares), 2,
                         "builder + runtime stage'leri ARG'yi yeniden beyan etmeli")
        # Empty-guard apt katmanıyla simetrik (ortam/yama yoksa net kanıt).
        self.assertIn('"$PYTHON_SECURITY_PATCH_PACKAGES" | tr -d', self._df)
        self.assertIn("PYTHON_SECURITY_PATCH_PACKAGES empty", self._df)

    def test_pip_floor_pattern(self):
        # Floor'lar ARG default'unda (pip gereksinim sözdizimi, >=); kanıt
        # satırı dpkg-query karşılığı: pip show + floor ekranı kırpma.
        arg_line = next(ln for ln in self._df.splitlines()
                        if ln.startswith('ARG PYTHON_SECURITY_PATCH_PACKAGES='))
        for floor in ("setuptools>=80", "wheel>=0.46.2"):
            self.assertIn(floor, arg_line, f"CVE-defteri floor'u ARG'de: {floor}")
        self.assertIn("pip show", self._df,
                      "pip katmanı kanıtı pip show ile (apt dpkg-query simetrisi)")
        self.assertIn("sed 's/[><=!~].*//'", self._df,
                      "pip show'a floor eki ham geçemez (yalın paket adı)")
        # Fail-closed: floorsuz toplu pip upgrade satırı yasak.
        for ln in self._df.splitlines():
            s = ln.strip()
            if s.startswith("pip install") and "--upgrade" in s:
                # Regresyon (canlı build'de ölçüldü): unquoted $VAR genişlemesi
                # 'setuptools>=80' içindeki '>'yi shell REDIRECT'ine çevirir —
                # floor yutulur, bare latest kurulur (sessiz kontrat ihlali).
                # Güvenli form: quoted printf → tr → -r dosyası.
                self.assertIn("-r /tmp/pip_security_reqs.txt", s,
                              f"pip upgrade -r dosyasından olmalı: {s}")
                self.assertNotIn("$PYTHON_SECURITY_PATCH_PACKAGES", s,
                                 f"pip satırında unquoted $VAR yasak (> redirect tuzakası): {s}")
        # Guard + reqs dosyası QUOTED genişlemeden üretilir ('>' korunur).
        self.assertIn('printf \'%s\\n\' "$PYTHON_SECURITY_PATCH_PACKAGES"',
                      self._df, "reqs dosyası quoted genişlemeden üretilmeli")

    def test_doc_contract(self):
        # Desenin dokümanı: kapalı döngü + defter + smoke aracı + katkı sözleşmesi.
        for token in ("SECURITY_PATCH_PACKAGES",
                      "PYTHON_SECURITY_PATCH_PACKAGES",
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
