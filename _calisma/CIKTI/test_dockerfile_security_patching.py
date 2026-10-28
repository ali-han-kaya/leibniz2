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
  9) npm audit ZORLAYICI kapısı (TestNpmAuditGateEnforcement): CI'daki
     `npm-audit` job'ı + `npm_audit_gate.py`. Kapı advisory'ye dönemez
     (continue-on-error yok), eşik TEK kaynaktan gelir (workflow env
     NPM_AUDIT_GATE_LEVEL, HIGH varsayılanı), eşiğe eşit/ağır bulguda
     exit 1, SKIP CI'da --require-real ile FAIL. 8. madde deseni, 9.
     madde kapının fiilen blokladığını sabitler — biri olmadan diğeri
     yanıltıcıdır (yeşil süit + hiç koşmayan kapı).

Desen bozulursa (floor silinmesi, tüm-upgrade'e geçiş, hijyen kaybı,
**/node_modules'in bare'a düşmesi) test fail eder → commit bloke olur
(fail-closed). stdlib-only, OFFLINE.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
DOC = ROOT / "docs" / "DOCKER_SECURITY_PATCHING.md"

# Sözleşmenin bugün fiilen uygulandığı Dockerfile'lar. Yeni bir Dockerfile
# eklenirse buraya girmeli; girmese kapı sessizce körleşmez — guard FAIL eder
# (aşağıdaki test_no_uncovered_dockerfile).
COVERED_DOCKERFILES = (DOCKERFILE,)

# Keşif sırasında inilmeyecek hijyen dizinleri. Aynı sınıf .dockerignore
# kurallarıyla (bkz. docs/DOCKER_SECURITY_PATCHING.md "Context hijyeni"):
# üretim artefaktı veya venv olan bir dizindeki Dockerfile repo yüzeyi
# değildir. followlinks=False ayrıca sembolik node_modules'a inilmesini
# engeller (denetim döngüsüne girmesin).
_HYGIENE_DIRS = frozenset({
    ".git", ".worktrees", ".next", ".vercel", "node_modules",
    ".venv", ".venv_z3", "__pycache__",
})


def repo_dockerfiles():
    """Repo yüzeyindeki Dockerfile'lar (hijyen dizinleri hariç), sıralı."""
    found = []
    for base, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if d not in _HYGIENE_DIRS]
        if "Dockerfile" in files:
            found.append(Path(base) / "Dockerfile")
    return sorted(found)


def hook_files_pattern():
    """Hook'un `files:` deseni (tırnak varsa soyulur) — derlenmiş regex."""
    cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = next(b for b in cfg.split("\n      - id: ")
                 if b.startswith("check-dockerfile-security-patching"))
    m = re.search(r"^\s*files:\s*'?([^'\"\n]+?)'?\s*$", block, re.M)
    if not m:
        raise AssertionError("hook tanımında files: deseni yok")
    return re.compile(m.group(1))


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
        # 2026-10-28: desen npm yüzeylerini de eşler — .dockerignore veya bir
        # package.json değişip de hook ateşlenmezse npm floor'u/hijyeni
        # commit-anında denetlenmez (sözleşme yalnız Dockerfile'a bakardı).
        pat = hook_files_pattern()
        for surface in ("Dockerfile", "apps/dashboard-next/package.json",
                        "apps/dashboard-next/package-lock.json",
                        ".dockerignore"):
            self.assertIsNotNone(
                pat.search(surface),
                f"değişim-farkında tetikleme: hook deseni eşlemeli: {surface}")
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

    def test_no_uncovered_dockerfile(self):
        # Fail-closed kapsam guard'ı. Ölçülen boşluk (PR #65): sözleşme
        # yalnız kök Dockerfile'ı okuyordu, hook da yalnız onu eşliyordu
        # (files: ^Dockerfile$). İkinci bir Dockerfile eklenmesi onu
        # tamamen kapsam dışı bırakırdı — ne hook ateşlenir ne sözleşme
        # uygulanır. Bu test, kapsam dışı Dockerfile'ın sessizce girmesini
        # reddeder: ya sözleşmeye eklenir ya da kapsam dışı olduğu burada
        # gerekçesiyle bildirilir.
        found = repo_dockerfiles()
        self.assertIn(DOCKERFILE, found,
                      "kök Dockerfile keşfedilmeli (keşif bozuk)")
        uncovered = [str(p.relative_to(ROOT)) for p in found
                     if p not in COVERED_DOCKERFILES]
        self.assertEqual(
            uncovered, [],
            "kapsam dışı Dockerfile eklendi — sözleşme ona uygulanmıyor: "
            + ", ".join(uncovered)
            + " | ya COVERED_DOCKERFILES'a ekle (ve sözleşmeyi genişlet), "
              "ya da kapsam dışı olduğunu gerekçesiyle burada bildir")

    def test_hook_pattern_matches_every_repo_dockerfile(self):
        # Parite: hook'un files: deseni ile keşif aynı yüzeyi görmeli.
        # İki birbirinden ayrılırsa genişleme sessizce işe yaramaz hale
        # gelir (desen daralırsa hook kök dışı Dockerfile'ı yakalamaz).
        pat = hook_files_pattern()
        for p in repo_dockerfiles():
            rel = p.relative_to(ROOT).as_posix()
            self.assertIsNotNone(
                pat.search(rel),
                f"hook deseni repo Dockerfile'ını eşlemeli: {rel}")

    def test_hook_pattern_rejects_near_misses(self):
        # Genişletme aşırı-totaymamalı: yalnız Dockerfile adı olan dosyalar
        # eşleşmeli. Yanlışlıkla 'Dockerfile' deseni gevşetilirse
        # (örn. files: Dockerfile) markdown/şablon dosyaları da hook'u
        # tetikler ve değişim-farkı sözleşmesi bulanıklaşır.
        pat = hook_files_pattern()
        for hit in ("Dockerfile", "apps/x/Dockerfile", "a/b/c/Dockerfile",
                    ".dockerignore", "package.json", "apps/x/package.json",
                    "_calisma/pptx/package-lock.json"):
            self.assertIsNotNone(pat.search(hit), f"eşlemeli: {hit}")
        for miss in ("Dockerfile.md", "Dockerfile.bak", "docs/Dockerfile.txt",
                     "docs/DOCKERFILE.md", "dockerfile",
                     "package.json.bak", "my-package.json",
                     "docs/package.json.md", ".dockerignore.bak"):
            self.assertIsNone(pat.search(miss), f"eşlememeli: {miss}")

    def test_discovery_excludes_hygiene_dirs(self):
        # Keşif, .dockerignore sınıfındaki dizinlere inmemeli: üretim
        # artefaktı (.next/.vercel) ya da venv kökündeki Dockerfile repo
        # yüzeyi değildir — sayılırsa kapsam guard'ı yanlış FAIL verir.
        probe = ROOT / ".next" / "probe"
        probe.mkdir(parents=True, exist_ok=True)
        try:
            (probe / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            found = [p.relative_to(ROOT).as_posix() for p in repo_dockerfiles()]
            self.assertNotIn(".next/probe/Dockerfile", found,
                             "hijyen dizini keşfe sızmamalı")
            self.assertEqual(found, ["Dockerfile"],
                             "hijyen dizini eklenince keşif değişmemeli")
        finally:
            for child in sorted(probe.rglob("*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            probe.rmdir()
            (ROOT / ".next").rmdir()

    def test_patch_layer_present_with_cve_ledger_default(self):
        # ARG default'u floor girdisini taşır + defter CVE kimlikleriyle kayıtlı.
        self.assertIn("ARG SECURITY_PATCH_PACKAGES=", self._df)
        self.assertIn("libpcre2-8-0=10.42-1+deb12u2", self._df)
        self.assertIn("CVE-2026-86145", self._df)
        self.assertIn("CVE-2026-89161", self._df)
        # 2026-10-27 turu: PR #54 gate bulguları — aynı kaynak paket iki
        # adla taranıyor (libssl3 + openssl), tzdata DLA'sı ise UNKNOWN
        # seviye (fail-closed kapı onu da bloklar) — floor'lar kalıcı kayıt.
        self.assertIn("libssl3=3.0.22-1~deb12u2", self._df)
        self.assertIn("openssl=3.0.22-1~deb12u2", self._df)
        self.assertIn("tzdata=2026e-0+deb12u1", self._df)
        self.assertIn("DLA-4792-1", self._df)
        self.assertIn("CVE-2026-63072", self._df)

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
        # 2026-10-27 kararı (PR #54): pip floor'u BİLEREK eklenmez — pip'in
        # son sürümü (26.2.2) vendor SBOM'unda kapı setinde 4 HIGH taşıyor
        # (trivy 0.69.3 ile rc=1 ölçüldü); pip 24.0'ın kendi CVE'leri ise
        # MEDIUM/LOW → kapı setine girmez. Gerekçe: docs/DOCKER_SECURITY_PATCHING.md.
        for floor in ("setuptools>=80", "wheel>=0.46.2"):
            self.assertIn(floor, arg_line, f"CVE-defteri floor'u ARG'de: {floor}")
        self.assertNotIn("pip>=", arg_line,
                         "pip floor'u kasıtlı olarak eklenmemeli (vendor SBOM kapıyı kırar)")
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
                      "10.42-1+deb12u2",
                      "libssl3", "tzdata", "kasıtlı",
                      "docker_security_smoke.sh",
                      "Katkı sözleşmesi"):
            self.assertIn(token, self._doc,
                          f"doküman sözleşmesi eksik: {token}")
        # Dockerfile dokümana bağlanmalı (keşfedilebilirlik).
        self.assertIn("docs/DOCKER_SECURITY_PATCHING.md", self._df)


# ---------------------------------------------------------------------------
# npm çalışma alanı envanteri — sözleşmenin kapsamı
# ---------------------------------------------------------------------------
# Kapsam TEK KAYNAKTAN gelir: `npm_workspaces.py`. Zorlayıcı `npm audit`
# eşik kapısı (npm_audit_gate.py — CI'da `npm-audit` job'ı) da aynı kümeyi
# oradan okur. Liste iki yerde yazılsaydı gate'in sessizce atladığı bir
# çalışma alanı "denetleniyor" görünürdü: fail-open.
#
# Kayıt alanları (ayrıntı: docs/DOCKER_SECURITY_PATCHING.md):
#   "overrides"   geçişli bağımlılık floor'u (package.json `overrides` bloğu)
#   "direct"      doğrudan bağımlılık floor'u (dependencies/devDependencies)
#   "scratch"     çalışma alanının ürettiği, .dockerignore'da SATIR olarak
#                 yaşaması gereken artefakt yüzeyleri
#   "advisories"  floor'u doğuran advisory kimlikleri (doküman defteriyle eş)
#   "optional"    bugün repoda olmayan (land edilmemiş) çalışma alanı
sys.path.insert(0, str(Path(__file__).resolve().parent))
import npm_workspaces  # noqa: E402 — kardeş modül (yol yukarıda eklendi)

NPM_WORKSPACES = npm_workspaces.NPM_WORKSPACES
NPM_OUT_OF_SCOPE = npm_workspaces.NPM_OUT_OF_SCOPE
repo_npm_workspaces = npm_workspaces.repo_npm_workspaces


def _ws_pkg(rel):
    return npm_workspaces.load_package(rel)


def _ws_lock(rel):
    return npm_workspaces.load_lock(rel)


def _ignore_lines():
    """`.dockerignore`'ın YORUM OLMAYAN satırları (desen eşleşmesi tam satır)."""
    return {ln.strip() for ln in
            (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")}


class TestNpmSecurityLayerContract(unittest.TestCase):
    """npm katmanı: TÜM çalışma alanlarında context hijyeni + floor sözleşmesi.

    docs/DOCKER_SECURITY_PATCHING.md'nin "npm katmanı" bölümünü gerçek yüzeye
    bağlar. Gerekçe: image'e node_modules kurulmadığı için Trivy npm katmanını
    yalnızca BAĞLAM SIZINTISI varsa görür; bu yüzden iki yüzey de (ignore
    deseni + sürüm floor'u) kontrat altındadır. 2026-09-20 ölçümü: .worktrees
    sızıntısı postcss 8.4.31 + sharp 0.34.5 üzerinden 4 HIGH bulgu üretti,
    CI'da hiç görünmedi (parite ihlali).

    2026-10-28 genişlemesi: sözleşme tek çalışma alanıyla (dashboard-next)
    sınırlıydı; pptx / dashboard-shadcn / trend-db ölçüldü ve kayda alındı,
    docx land edilmemiş olduğu için `optional` olarak kaydedildi. Ölçülen
    bulgular (hepsi `npm audit` ile, floor'lar `npm install
    --package-lock-only` sonrası lock'ta doğrulandı):
      - shadcn : vite 8.2.2 → 8.3.5 (launch-editor GHSA'ları),
                 source-map-js 1.2.1 → 1.2.2
      - trend-db: prisma 7.10.0 → 7.10.1 (+ @prisma/config), deepmerge-ts
                 <8 DoS, mysql2 ≤3.23.0 auth downgrade, fast-uri 3.1.8
      - pptx   : pptxgenjs 4.0.1'in image-size ^1.2.1'i (JXL/HEIF + ICNS
                 sonsuz döngü) — runtime'da YÜKLENMİYOR (dist yalnız jszip +
                 sizeof require eder), override tabloyu kapatır.
    """

    @classmethod
    def setUpClass(cls):
        cls._ignore = _ignore_lines()
        cls._ignore_text = "\n".join(sorted(cls._ignore))
        cls._doc = DOC.read_text(encoding="utf-8")
        cls._present = repo_npm_workspaces()

    # --- kapsam guard'ı ----------------------------------------------------
    def test_no_unregistered_workspace(self):
        # Fail-closed keşif: yeni bir package.json sessizce kapsam dışı kalmaz.
        missing = [w for w in self._present
                   if w not in NPM_WORKSPACES and w not in NPM_OUT_OF_SCOPE]
        self.assertEqual(
            missing, [],
            "kayıtsız npm çalışma alanı: " + ", ".join(missing)
            + " | NPM_WORKSPACES'a ekle (floor + scratch ile) ya da "
              "NPM_OUT_OF_SCOPE'a GEREKÇEYLE yaz")
        # Kayıtlı her alan gerçekten var olmalı: yol kayması sessiz kapsam
        # kaybıdır (sözleşme var sanılır, denetlenen yüzey yoktur).
        absent = sorted(w for w in NPM_WORKSPACES
                        if w not in self._present
                        and not NPM_WORKSPACES[w].get("optional"))
        self.assertEqual(absent, [],
                         "kayıtlı çalışma alanı repoda yok (yol kaymış): "
                         + ", ".join(absent))
        # Kapsam dışı kaydı gerekçesiz olamaz.
        for ws, reason in NPM_OUT_OF_SCOPE.items():
            self.assertTrue(reason and len(reason) > 40,
                            f"kapsam dışı gerekçesi zayıf: {ws}")

    def test_hook_pattern_covers_every_registered_workspace(self):
        # Parite (2026-10-28): hook deseni ile npm kayıt defteri ayrılırsa
        # yeni çalışma alanı eklenir, sözleşme sessizce ateşlenmez. Her
        # kayıtlı alanın manifest + lock dosyası hook desenini eşlemeli.
        pat = hook_files_pattern()
        for ws in NPM_WORKSPACES:
            for name in ("package.json", "package-lock.json"):
                rel = f"{ws}/{name}"
                self.assertIsNotNone(
                    pat.search(rel),
                    f"hook deseni çalışma alanı manifestini eşlemeli: {rel}")
        self.assertIsNotNone(pat.search(".dockerignore"),
                             "hook deseni .dockerignore'ı eşlemeli")

    def test_optional_workspace_is_documented(self):
        # Bugün olmayan (docx) çalışma alanı kaydı dokümanda görünmeli ki
        # sorumluluk "unutulmuş" değil "bekliyor" olarak okunsun.
        for ws, meta in NPM_WORKSPACES.items():
            if not meta.get("optional"):
                continue
            self.assertIn(ws, self._doc,
                          f"optional çalışma alanı dokümanda yok: {ws}")

    # --- context hijyeni ---------------------------------------------------
    def test_context_hygiene_deep_patterns(self):
        # Kural 1: Docker'da bare ad YALNIZ context kökünü eşler →
        # derin ağaçları sızdıran desen '**/' olmalı.
        for pattern in ("**/node_modules", "**/.next", ".worktrees"):
            self.assertIn(pattern, self._ignore,
                          f"context hijyeni kuralı ihlali: {pattern} ignore listesinde değil")
        self.assertRegex(self._ignore_text, r"(?m)^\*\*?/?node_modules\s*$",
                         "node_modules deseni tam satır olmalı (yorum içinde gömülmemeli)")
        # Kural 2: venv sınıfı da aynı listeye bağlı (aynı sızıntı sınıfı).
        for pattern in ("**/.venv_z3", ".venv_z3"):
            self.assertIn(pattern, self._ignore,
                          f"venv sınıfı ignore dışında kalmış: {pattern}")

    def test_workspace_scratch_surfaces_are_dockerignored(self):
        # Kural 3 (2026-10-28): her çalışma alanının ürettiği artefakt yüzeyi
        # .dockerignore'da SATIR olarak yaşar. Kayıtta scratch var ama
        # ignore'da yoksa bu sessiz tarama körlüğüdür (bağlam üreticisi
        # listeye girmez → image'a sızar → Trivy yanlış sürümü tarar).
        for ws, meta in NPM_WORKSPACES.items():
            for pattern in meta.get("scratch", ()):
                self.assertIn(
                    pattern, self._ignore,
                    f"{ws}: scratch yüzeyi .dockerignore'da yok: {pattern} "
                    "(bare ad yalnız kökü eşler — derinlik deseni gerekir)")

    def test_gitignore_covers_every_workspace(self):
        # Parite: git'in dışladığı ile docker bağlamının dışladığı aynı yüzeyi
        # görmeli. node_modules her çalışma alanında gitignore'da; dockercheck
        # '**/node_modules' ile aynı derinliği kapatır.
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for ws in NPM_WORKSPACES:
            if ws not in self._present:
                continue
            self.assertRegex(
                gitignore, r"(?m)^" + re.escape(ws) + r"/node_modules/?\s*$",
                f"{ws}: node_modules gitignore'da satır olarak yok")
            self.assertIn("**/node_modules", self._ignore,
                          "docker bağlamı node_modules'ü derinlikte kapatmalı")

    # --- floor sözleşmesi --------------------------------------------------
    def test_overrides_are_floors_not_pins(self):
        for ws in self._present:
            if ws not in NPM_WORKSPACES:
                continue
            meta = NPM_WORKSPACES[ws]
            overrides = _ws_pkg(ws).get("overrides") or {}
            for name, floor in meta.get("overrides", {}).items():
                self.assertIn(name, overrides,
                              f"{ws}: geçişli bağımlılık override'ı eksik: {name}")
                spec = str(overrides[name])
                self.assertTrue(
                    spec.startswith("^"),
                    f"{ws}: {name} floor ('^') olmalı — pin ('=') yasak: {spec}")
                self.assertGreaterEqual(_v(spec), _v(floor),
                                        f"{ws}: {name} floor düştü: {spec} < {floor}")

    def test_direct_dependency_floors(self):
        for ws in self._present:
            if ws not in NPM_WORKSPACES:
                continue
            pkg = _ws_pkg(ws)
            for field in ("dependencies", "devDependencies"):
                for name, spec in (pkg.get(field) or {}).items():
                    # 'latest' bir floor DEĞİLDİR: sürüm kararı registry'ye
                    # devredilir, lock ile çözülür, denetlenemez.
                    self.assertNotIn(
                        str(spec).strip().lstrip("^~"),
                        ("latest", "*", "x", "next"),
                        f"{ws}: {field}.{name} floor'suz aralık: {spec}")
            for name, floor in NPM_WORKSPACES[ws].get("direct", {}).items():
                spec = str((pkg.get("dependencies") or {}).get(name)
                           or (pkg.get("devDependencies") or {}).get(name) or "")
                self.assertTrue(spec, f"{ws}: doğrudan bağımlılık kayıp: {name}")
                self.assertGreaterEqual(_v(spec), _v(floor),
                                        f"{ws}: {name} floor düştü: {spec} < {floor}")

    def test_lockfile_resolves_above_floors(self):
        # Lockfile = floor'un UYGULANMIŞ hâlinin tek kanıtı (npm ci CI'da
        # bunu kurar). Floor yükseldi ama lock geride kaldıysa sözleşme
        # sessizce bozulur — kanıt/iddia ayrışır.
        for ws in self._present:
            if ws not in NPM_WORKSPACES:
                continue
            meta = NPM_WORKSPACES[ws]
            lock_path = ROOT / ws / "package-lock.json"
            self.assertTrue(lock_path.is_file(),
                            f"{ws}: package-lock.json yok (lock kanıt değil)")
            lock = _ws_lock(ws)
            self.assertEqual(lock.get("lockfileVersion"), 3,
                             f"{ws}: beklenen lockfileVersion 3")
            pkgs = lock.get("packages") or {}
            floors = dict(meta.get("direct", {}))
            floors.update(meta.get("overrides", {}))
            for name, floor in floors.items():
                key = f"node_modules/{name}"
                self.assertIn(key, pkgs, f"{ws}: lockfile'da yok: {key}")
                version = str((pkgs[key] or {}).get("version", ""))
                self.assertTrue(version, f"{ws}: lockfile sürümü yok: {key}")
                self.assertGreaterEqual(
                    _v(version), _v(floor),
                    f"{ws}: lock floor'un altında: {key}={version} < {floor}")

    # --- doküman sözleşmesi ------------------------------------------------
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
                      "**/dist",
                      "^8.5.18",
                      "^0.35.5",
                      "^1.2.2",
                      "^7.10.1",
                      "^2.0.3",
                      "npm audit"):
            self.assertIn(token, self._doc,
                          f"npm bölümü doküman sözleşmesi eksik: {token}")
        # Kod kaydı ile doküman defteri aynı çalışma alanı kümesini anmalı.
        for ws in NPM_WORKSPACES:
            self.assertIn(ws, self._doc,
                          f"doküman defterinde çalışma alanı yok: {ws}")
        # Her advisory kimliği iki yüzeyde de (kod + doküman) geçmeli.
        for meta in NPM_WORKSPACES.values():
            for adv in meta.get("advisories", ()):
                self.assertIn(adv, self._doc,
                              f"advisory dokümanda yok: {adv}")


# ---------------------------------------------------------------------------
# npm audit ZORLAYICI kapısı — CI'da bloklar (fail-closed)
# ---------------------------------------------------------------------------
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security.yml"
AUDIT_GATE = ROOT / "_calisma" / "CIKTI" / "npm_audit_gate.py"


def _job_block(text, job_id):
    """workflow içindeki tek job bloğu (2-space girinti sınırı)."""
    lines = text.splitlines()
    head = "  %s:" % job_id
    if head not in lines:
        raise AssertionError("workflow'da job yok: %s" % job_id)
    block = []
    for ln in lines[lines.index(head) + 1:]:
        if ln.strip() and not ln.startswith("    "):
            break
        block.append(ln)
    return "\n".join(block)


def _step_with(job_block, needle):
    """Job bloğunda `needle` geçen adımın metni (adım sınırı: `      - name:`)."""
    for chunk in job_block.split("\n      - name:"):
        if needle in chunk:
            return chunk
    raise AssertionError("adım bulunamadı: %s" % needle)


class TestNpmAuditGateEnforcement(unittest.TestCase):
    """Eşik kapısının gerçekten BLOKLADIĞINI sabitler.

    `TestNpmSecurityLayerContract` floor/hijyen *desenini* sabitler; bu sınıf
    kapının CI'da koştuğunu ve eşiğe eşit/ağır bulguda kırmızıya döndüğünü.
    Ayrım nedensel: floor'lar bugün 0 bulgu üretiyor, yani yeni bir CVE
    geldiğinde "süit yeşil" olması hâlâ mümkündür — kırmızıyı üreten şey
    kapının kendisidir. Kapı sessizce advisory'ye dönerse (continue-on-error,
    adım `if:`'i ile daraltma, SKIP'i yutma) süit bunu yakalar.
    """

    @classmethod
    def setUpClass(cls):
        cls._wf = WORKFLOW.read_text(encoding="utf-8")
        cls._job = _job_block(cls._wf, "npm-audit")
        cls._script = AUDIT_GATE.read_text(encoding="utf-8")
        cls._doc = DOC.read_text(encoding="utf-8")
        sys.path.insert(0, str(AUDIT_GATE.parent))
        import npm_audit_gate
        cls.gate = npm_audit_gate

    # --- CI tarafı: kapı zorlayıcı mı? ------------------------------------
    def test_gate_job_is_enforcing(self):
        self.assertNotIn("continue-on-error", self._job,
                         "npm audit kapısı advisory olamaz — bulgu merge'ü "
                         "bloklamalı (continue-on-error yasak)")
        gate_step = _step_with(self._job, "npm_audit_gate.py")
        self.assertIn("--require-real", gate_step,
                      "CI'da SKIP kanıt değildir — --require-real zorunlu")
        self.assertNotIn("if:", gate_step,
                         "kapı adımı koşula bağlanamaz (push/cron'da da "
                         "koşmalı; yalnız PR'da koşan bir kapı kör kalır)")
        self.assertIn("timeout-minutes", self._job,
                      "asma-kilit riski: job timeout'u olmalı")

    def test_threshold_single_source(self):
        # Eşik workflow env'inde beyan edilir; script aynı env'i okur.
        self.assertIn("NPM_AUDIT_GATE_LEVEL", self._wf,
                      "eşik workflow env'inde beyan edilmeli")
        self.assertNotIn("--level", self._job,
                         "adımda literal --level yasak — eşik env'den gelir "
                         "(iki kaynak = sürüklenen bloklama kararı)")
        self.assertIn('os.environ.get("NPM_AUDIT_GATE_LEVEL")', self._script,
                      "script eşiği env'den okumalı")
        self.assertEqual(self.gate.DEFAULT_LEVEL, "high",
                         "env yoksa varsayılan eşik HIGH olmalı (CRITICAL+HIGH)")
        self.assertEqual(self.gate.resolve_level("critical"), "critical")
        os.environ["NPM_AUDIT_GATE_LEVEL"] = "moderate"
        try:
            self.assertEqual(self.gate.resolve_level(), "moderate",
                             "env eşiği CLI yokken geçerli olmalı")
            self.assertEqual(self.gate.resolve_level("high"), "high",
                             "CLI argümanı env'i ezmeli")
        finally:
            del os.environ["NPM_AUDIT_GATE_LEVEL"]
        with self.assertRaises(SystemExit):
            self.gate.resolve_level("yuksek")

    def test_gate_scans_the_contract_workspace_set(self):
        # Kapsam tek kaynak: gate varsayılan kümesi = floor sözleşmesinin
        # kaydı. Liste script'te tekrar yazılsaydı yeni bir çalışma alanı
        # taranmadan "denetleniyor" görünürdü.
        self.assertIn("npm_workspaces.present_workspaces()", self._script,
                      "gate varsayılan kümeyi kayıttan türetmeli")
        present = set(npm_workspaces.present_workspaces())
        self.assertIn("apps/dashboard-next", present,
                      "dashboard-next npm audit kapsamında olmalı")
        for ws in present:
            self.assertIn(ws, NPM_WORKSPACES)
            self.assertNotIn(ws, NPM_OUT_OF_SCOPE,
                             "kapsam-dışı bir alan taranmamalı: %s" % ws)
        for ws in NPM_OUT_OF_SCOPE:
            self.assertNotIn(ws, present,
                             "gerekçeli kapsam-dışı bugün repoda olmamalı: %s" % ws)

    # --- Eşik politikası: hangi seviye bloklar? ---------------------------
    def test_blocking_severity_policy(self):
        self.assertEqual(self.gate.blocking_severities("high"),
                         ("high", "critical"),
                         "HIGH eşiği HIGH+CRITICAL bloklar")
        self.assertEqual(self.gate.blocking_severities("critical"),
                         ("critical",))
        self.assertIn("moderate",
                      self.gate.blocking_severities("moderate"))

        def summary(**vulns):
            return self.gate.summarize(
                {"metadata": {"vulnerabilities": vulns}}, "high")

        self.assertEqual(summary(high=1)["verdict"], "FAIL")
        self.assertEqual(summary(critical=1)["verdict"], "FAIL")
        self.assertEqual(summary(moderate=3, low=2)["verdict"], "PASS",
                         "HIGH eşiğinde MODERATE bloklamaz")
        self.assertEqual(summary()["verdict"], "PASS")
        self.assertEqual(summary(high=2)["blocking_total"], 2)
        # Eşik düşürülünce MODERATE de bloklar (aynı rapor, farklı karar).
        self.assertEqual(
            self.gate.summarize(
                {"metadata": {"vulnerabilities": {"moderate": 1}}},
                "moderate")["verdict"], "FAIL")

    # --- CLI sözleşmesi: çıkış kodu + verdict aynı şeyi söylemeli --------
    def _run(self, fixture_dir, *args):
        cmd = [sys.executable, str(AUDIT_GATE), "--audit-json", str(fixture_dir),
               "--workspace", "apps/dashboard-next", "--json", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc

    def test_cli_verdicts_offline(self):
        ws = "apps__dashboard-next.json"

        def report(vulns):
            return json.dumps({"metadata": {"vulnerabilities": vulns}})

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ws
            path.write_text(
                report({"critical": 0, "high": 0, "moderate": 4, "low": 2}),
                encoding="utf-8")
            proc = self._run(td)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "PASS")
            self.assertIn("workspace=apps/dashboard-next verdict=PASS",
                          proc.stderr, "kanıt satırları stderr'e (JSON modu)")

            path.write_text(report({"critical": 0, "high": 1, "moderate": 0}),
                            encoding="utf-8")
            proc = self._run(td)
            self.assertEqual(proc.returncode, 1,
                             "HIGH bulgu HIGH eşiğinde kapıyı kırmızıya "
                             "çevirmeliydi (fail-closed)")
            doc = json.loads(proc.stdout)
            self.assertEqual(doc["verdict"], "FAIL")
            self.assertEqual(doc["failed"], ["apps/dashboard-next"])
            self.assertEqual(doc["workspaces"][0]["blocking"], {"high": 1,
                                                                "critical": 0})

            # SKIP dürüst: ölçüm yoksa PASS demez (sessiz yeşil yasak)...
            (Path(td) / ws).unlink()
            proc = self._run(td)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "SKIP")
            self.assertEqual(json.loads(proc.stdout)["verdict_reason"],
                             "skip-only")
            # ...ve CI modunda SKIP kırmızıdır (npm kurulu bir runner'da
            # SKIP = kapı körleşti).
            proc = self._run(td, "--require-real")
            self.assertEqual(proc.returncode, 1)
            doc = json.loads(proc.stdout)
            self.assertEqual(doc["verdict"], "FAIL")
            self.assertEqual(doc["verdict_reason"], "skip-with-require-real")

    def test_report_file_is_written(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "apps__dashboard-next.json").write_text(
                json.dumps({"metadata": {"vulnerabilities": {"high": 0}}}),
                encoding="utf-8")
            out = Path(td) / "evidence" / "npm_audit_report.txt"
            cmd = [sys.executable, str(AUDIT_GATE), "--audit-json", td,
                   "--workspace", "apps/dashboard-next", "--report", str(out)]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertTrue(lines[-1].startswith("verdict="),
                            "kanıt dosyası verdict satırıyla bitmeli")

    # --- doküman sözleşmesi ----------------------------------------------
    def test_doc_documents_gate(self):
        for token in ("npm-audit", "NPM_AUDIT_GATE_LEVEL", "--require-real",
                      "npm_audit_gate.py", "eşik"):
            self.assertIn(token, self._doc,
                          f"npm audit kapısı dokümanda eksik: {token}")


if __name__ == "__main__":
    unittest.main()
