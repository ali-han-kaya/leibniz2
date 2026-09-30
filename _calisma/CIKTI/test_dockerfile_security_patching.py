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
  8) npm katmanı (TestNpmSecurityLayerContract): context hijyeni
     (.dockerignore'da **/node_modules / **/.next / .worktrees — bare ad
     tuzağı dahil), overrides floor'ları (asla pin) + next doğrudan
     floor'u, lockfile'ın floor'ları karşıladığı (floor → lock uyumu)
     ve npm bölümünün doküman sözleşmesi.

Desen bozulursa (floor silinmesi, tüm-upgrade'e geçiş, hijyen kaybı,
**/node_modules'in bare'a düşmesi) test fail eder → commit bloke olur
(fail-closed). stdlib-only, OFFLINE.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
DOC = ROOT / "docs" / "DOCKER_SECURITY_PATCHING.md"


def _v(spec: str) -> tuple:
    """'8.5.28' / '^8.5.18' / '16.3.6' → karşılaştırılabilir 3'lü (eksik: 0).

    Floor karşılaştırması için: npm aralık operatörü ('^' = '>=' sözleşmesi)
    ve kısa sürüm ('16.3') normalize edilir — tuple karşılaştırmasında
    uzunluk farkı yanlış sonuc verir (16.3 < 15.5.15 gibi).
    """
    core = re.split(r"[-+]", str(spec).strip().lstrip("^~>=<v "))[0]
    nums = [int(c) for c in core.split(".") if c.isdigit()][:3]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


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


class TestNpmSecurityLayerContract(unittest.TestCase):
    """npm katmanı: context hijyeni + `overrides`/lock floor sözleşmesi.

    docs/DOCKER_SECURITY_PATCHING.md'nin "npm katmanı" bölümünü gerçek
    yüzeye bağlar. Gerekçe: image'e node_modules kurulmadığı için Trivy
    npm katmanını yalnızca BAĞLAM SIZINTISI varsa görür; bu yüzden iki
    yüzey de (ignore deseni + sürüm floor'u) kontrat altındadır.
    2026-09-20 ölçümü: .worktrees sızıntısı postcss 8.4.31 + sharp 0.34.5
    üzerinden 4 HIGH bulgu üretti, CI'da hiç görünmedi (parite ihlali).
    """

    @classmethod
    def setUpClass(cls):
        cls._ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        pkg_dir = ROOT / "apps" / "dashboard-next"
        cls._pkg = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8"))
        cls._lock = json.loads(
            (pkg_dir / "package-lock.json").read_text(encoding="utf-8"))
        cls._doc = DOC.read_text(encoding="utf-8")

    def test_context_hygiene_deep_patterns(self):
        # Kural 1: Docker'da bare ad YALNIZ context kökünü eşler →
        # derin ağaçları sızdıran desen '**/' olmalı.
        for pattern in ("**/node_modules", "**/.next", ".worktrees"):
            self.assertIn(pattern, self._ignore,
                          f"context hijyeni kuralı ihlali: {pattern} ignore listesinde değil")
        self.assertRegex(self._ignore, r"(?m)^\*\*?/?node_modules\s*$",
                         "node_modules deseni tam satır olmalı (yorum içinde gömülmemeli)")
        # Kural 2: venv sınıfı da aynı listeye bağlı (aynı sızıntı sınıfı).
        for pattern in ("**/.venv_z3", ".venv_z3"):
            self.assertIn(pattern, self._ignore,
                          f"venv sınıfı ignore dışında kalmış: {pattern}")

    def test_overrides_are_floors_not_pins(self):
        overrides = self._pkg.get("overrides") or {}
        for name, floor in (("postcss", "8.5.18"), ("sharp", "0.35.4")):
            self.assertIn(name, overrides,
                          f"geçişli bağımlılık override'ı eksik: {name}")
            spec = str(overrides[name])
            self.assertTrue(spec.startswith("^"),
                            f"{name} floor ('^') olmalı — pin ('=') yasak: {spec}")
            self.assertGreaterEqual(_v(spec), _v(floor),
                                    f"{name} floor düştü: {spec} < {floor}")
        # Doğrudan bağımlılık floor'u: next (GHSA-mwv6-3258-q52c,
        # GHSA-q4gf-8mx6-v5v3 → fixed 15.5.15).
        nxt = str((self._pkg.get("dependencies") or {}).get("next", ""))
        self.assertTrue(nxt, "dependencies.next kayıp")
        self.assertGreaterEqual(_v(nxt), _v("15.5.15"), f"next floor düştü: {nxt}")

    def test_lockfile_resolves_above_floors(self):
        # Lockfile = floor'un UYGULANMIŞ hâlinin tek kanıtı (npm ci CI'da
        # bunu kurar). Floor yükseldi ama lock geride kaldıysa sözleşme
        # sessizce bozulur — kanıt/iddia ayrışır.
        pkgs = self._lock.get("packages") or {}
        for key, floor in (("node_modules/postcss", "8.5.18"),
                           ("node_modules/sharp", "0.35.4"),
                           ("node_modules/next", "15.5.15")):
            self.assertIn(key, pkgs, f"lockfile'da yok: {key}")
            version = str((pkgs[key] or {}).get("version", ""))
            self.assertTrue(version, f"lockfile sürümü yok: {key}")
            self.assertGreaterEqual(_v(version), _v(floor),
                                    f"lock floor'un altında: {key}={version} < {floor}")

    def test_npm_doc_contract(self):
        for token in ("npm katmanı",
                      "context hijyeni",
                      "overrides",
                      "npm-CVE-defteri",
                      "GHSA-mwv6-3258-q52c",
                      "GHSA-q4gf-8mx6-v5v3",
                      "CVE-2026-45623",
                      "GHSA-f88m-g3jw-g9cj",
                      "**/node_modules",
                      "^8.5.18",
                      "^0.35.4",
                      "npm audit"):
            self.assertIn(token, self._doc,
                          f"npm bölümü doküman sözleşmesi eksik: {token}")


if __name__ == "__main__":
    unittest.main()
