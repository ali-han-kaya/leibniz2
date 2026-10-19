#!/usr/bin/env python3
"""test_plist_keepalive_golden.py — keepalive profil mimarisi altın-dosya testi.

update_preview.sh'in PLIST_PROFILES son kolonu (keepalive) ÖLÜ ALAN DEĞİLDİR;
şablona uygulanır:

  keepalive=true  → RunAtLoad <true/>  + KeepAlive{SuccessfulExit:false}
  keepalive=false → RunAtLoad <false/> + KeepAlive bloğu YOK

Bu test script'i HERMETİK render eder (geçici HOME; gerçek LaunchAgents'a ve
launchctl'a dokunmaz) ve üretilen plist GÖVDELERİNİ commit'li altın dosyalarla
bayt-bayt karşılaştırır:

  plist-golden/com.freebuff.preview-leibniz2.plist → keepalive=true
      (birincil: RunAtLoad + KeepAlive ile otomatik yeniden başlatma)
  plist-golden/com.freebuff.preview-server.plist   → keepalive=false
      (yedek: login'de otomatik başlamaz, elle --start kickstart)

Ek olarak keepalive anahtarının gövdeyi GERÇEKTEN sürdüğünü kanıtlar: AYNI
profil satırının yalnız son kolonu true/false yapılarak render edilir; iki gövde
keepalive bölgesi dışında BİREBİR aynı olmalıdır. Kolon ölürse (iki render
özdeşleşirse) veya KeepAlive/RunAtLoad bloğu sessizce değişirse test fail eder.

check_plist_drift.py aynı karşılaştırmayı ADVISORY bir drift kapısı olarak
yapar; bu test onu birim süitin içinde fail-closed bir sözleşmeye çevirir.

stdlib-only, OFFLINE, ~0.3s.
"""
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "update_preview.sh"
GOLDEN_DIR = HERE / "plist-golden"

# Golden'da kullanılan kanonik HOME (gen_plist_golden.py / check_plist_drift.py
# ile aynı): render-home yolu golden'a gömülmez.
CANONICAL_HOME = "/Users/ci"

TRUE_PROFILE = "com.freebuff.preview-leibniz2.plist"   # keepalive=true
FALSE_PROFILE = "com.freebuff.preview-server.plist"    # keepalive=false

RUNATLOAD_KEY = "  <key>RunAtLoad</key>\n"
# keepalive bölgesinin bittiği bir sonraki üst-düzey öğeler: ThrottleInterval
# yorumu (yalnız preview-server şablonunda) veya ilk ortak anahtar.
REGION_STOPS = ("  <key>StandardOutPath</key>", "  <!--")


class TestPlistKeepaliveGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT.is_file():
            raise unittest.SkipTest("update_preview.sh yok")
        cls.rendered = render()  # gerçek PLIST_PROFILES

    # ── altın dosyalar mevcut mu (sessiz kapsam kaybına karşı) ──────────────
    def test_golden_files_exist(self):
        for name in (TRUE_PROFILE, FALSE_PROFILE):
            self.assertTrue((GOLDEN_DIR / name).is_file(),
                            f"altın dosya eksik: {GOLDEN_DIR / name}")

    def test_both_profiles_rendered(self):
        for name in (TRUE_PROFILE, FALSE_PROFILE):
            self.assertIn(name, self.rendered,
                          f"render edilmedi: {name} (profile listesi değişti mi?)")

    # ── asıl altın-dosya karşılaştırması: GÖVDE bayt-bayt ─────────────────
    def test_true_profile_body_matches_golden(self):
        """keepalive=true profili: üretilen gövde altın dosyayla birebir."""
        golden = (GOLDEN_DIR / TRUE_PROFILE).read_text(encoding="utf-8")
        self.assertEqual(self.rendered[TRUE_PROFILE], golden,
                         "keepalive=true gövdesi altın dosyadan farklı "
                         "(şablon/Profil değişti → gen_plist_golden.py)")

    def test_false_profile_body_matches_golden(self):
        """keepalive=false profili: üretilen gövde altın dosyayla birebir."""
        golden = (GOLDEN_DIR / FALSE_PROFILE).read_text(encoding="utf-8")
        self.assertEqual(self.rendered[FALSE_PROFILE], golden,
                         "keepalive=false gövdesi altın dosyadan farklı "
                         "(şablon/Profil değişti → gen_plist_golden.py)")

    # ── semantik: keepalive kolonu → launchd anahtarları ──────────────────
    def test_keepalive_true_semantics(self):
        d = plistlib.loads(self.rendered[TRUE_PROFILE].encode("utf-8"))
        self.assertIs(d.get("RunAtLoad"), True, "true profil RunAtLoad=true olmalı")
        self.assertEqual(d.get("KeepAlive"), {"SuccessfulExit": False},
                         "true profil KeepAlive{SuccessfulExit:false} taşımalı")

    def test_keepalive_false_semantics(self):
        d = plistlib.loads(self.rendered[FALSE_PROFILE].encode("utf-8"))
        self.assertIs(d.get("RunAtLoad"), False, "false profil RunAtLoad=false olmalı")
        self.assertNotIn("KeepAlive", d,
                         "false profilde KeepAlive bloğu OLMAMALI (login'de "
                         "otomatik başlamaz)")

    # ── canlılık: kolon gövdeyi sürüyor mu? (ölü alan regresyonu) ─────────
    def test_switch_isolates_the_body(self):
        """AYNI profil, yalnız keepalive kolonu true/false: fark YALNIZ o bölge.

        Kolon ölürse iki render özdeşleşir ve bölge farkı boşalır → fail.
        """
        primary = first_profile_line()
        fields = primary.split("|")
        self.assertEqual(len(fields), 5, f"profil satırı 5 kolon olmalı: {primary}")
        label = fields[0]
        name = f"{label}.plist"

        true_line = "|".join(fields[:4] + ["true"])
        false_line = "|".join(fields[:4] + ["false"])
        body_true = render([true_line])[name]
        body_false = render([false_line])[name]

        reg_true = keepalive_region(body_true)
        reg_false = keepalive_region(body_false)

        self.assertNotEqual(reg_true, reg_false,
                            "keepalive kolonu gövdeyi değiştirmiyor (ölü alan?)")
        # Gövdeler keepalive bölgesi dışında BİREBİR aynı olmalı.
        self.assertEqual(body_true.replace(reg_true, "<KA>"),
                         body_false.replace(reg_false, "<KA>"),
                         "keepalive dışındaki gövde farklı — kolon fazla etki ediyor")

        # Bölgenin kendisi de altın dosyaların bölgesiyle birebir olmalı.
        self.assertEqual(reg_true,
                         keepalive_region((GOLDEN_DIR / TRUE_PROFILE).read_text("utf-8")))
        self.assertEqual(reg_false,
                         keepalive_region((GOLDEN_DIR / FALSE_PROFILE).read_text("utf-8")))

    def test_keepalive_region_shape(self):
        """Bölge biçimi: true'da KeepAlive+SuccessfulExit, false'ta yalnız RunAtLoad."""
        reg_true = keepalive_region(self.rendered[TRUE_PROFILE])
        reg_false = keepalive_region(self.rendered[FALSE_PROFILE])
        self.assertIn("<true/>", reg_true)
        self.assertIn("<key>KeepAlive</key>", reg_true)
        self.assertIn("<key>SuccessfulExit</key>", reg_true)
        self.assertIn("<false/>", reg_false)
        self.assertNotIn("KeepAlive", reg_false)

    # ── profil listesi sözleşmesi ─────────────────────────────────────────
    def test_profile_array_manages_both_keepalive_regimes(self):
        """Liste her iki rejimi de yönetiyor: en az bir true + bir false."""
        lines = profile_lines()
        self.assertTrue(lines, "PLIST_PROFILES bulunamadı (dizi biçimi değişti?)")
        for ln in lines:
            self.assertEqual(len(ln.split("|")), 5,
                             f"profil satırı 'label|logname|port|interval|keepalive' olmalı: {ln}")
        col = [ln.split("|")[4] for ln in lines]
        self.assertIn("true", col, "keepalive=true profili yok")
        self.assertIn("false", col, "keepalive=false profili yok")


# ══════════════════════════════════════════════════════════════════════════
# Yardımcılar
# ══════════════════════════════════════════════════════════════════════════

_ARRAY_RE = re.compile(r"^PLIST_PROFILES=\(\n(.*?)^\)", re.M | re.S)


def profile_lines():
    """Kaynaktaki PLIST_PROFILES satırları (tırnakları sıyrılmış)."""
    m = _ARRAY_RE.search(SCRIPT.read_text(encoding="utf-8"))
    if not m:
        return []
    return [ln.strip().strip('"') for ln in m.group(1).splitlines() if ln.strip()]


def first_profile_line():
    lines = profile_lines()
    if not lines:
        raise AssertionError("PLIST_PROFILES bulunamadı — dizi biçimi değişti")
    return lines[0]


def render(profiles=None):
    """Hermetik render: geçici HOME + (gerekirse) yamalı script kopyası.

    profiles=None → gerçek script (gerçek PLIST_PROFILES).
    profiles=[...] → YALNIZ PLIST_PROFILES dizisi değiştirilmiş kopya.

    Döner: {dosya_adı: içerik}; render-home yolu kanonik /Users/ci'ye normalize.
    """
    root = Path(tempfile.mkdtemp(prefix="plist-keepalive-test-"))
    try:
        script = SCRIPT
        if profiles is not None:
            src = SCRIPT.read_text(encoding="utf-8")
            block = "\n".join(f'  "{p}"' for p in profiles)
            patched, n = _ARRAY_RE.subn(
                lambda _m: "PLIST_PROFILES=(\n%s\n)" % block, src, count=1)
            if n != 1:
                raise AssertionError("PLIST_PROFILES dizisi yamalanamadı (biçim değişti)")
            script = root / "update_preview.sh"
            script.write_text(patched, encoding="utf-8")

        home = root / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home))
        r = subprocess.run(["bash", str(script), "--plist-force", str(home)],
                           capture_output=True, text=True, timeout=120, env=env)
        if r.returncode != 0:
            raise AssertionError(
                "render başarısız (rc=%d):\n%s" % (r.returncode, r.stdout + r.stderr))

        out = {}
        for p in sorted((home / "Library" / "LaunchAgents").glob("*.plist")):
            out[p.name] = p.read_text(encoding="utf-8").replace(str(home), CANONICAL_HOME)
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)


def keepalive_region(body):
    """Gövdeden keepalive-kararlı bölgeyi çıkar (RunAtLoad + KeepAlive bloğu).

    Bölge, bir sonraki üst-düzey öğeye (StandardOutPath ya da ThrottleInterval
    yorumu) kadar sürer — yani şablondaki KEEPALIVE placeholder'larının tam
    kapladığı aralık (false profildeki boş satır dâhil).
    """
    i = body.find(RUNATLOAD_KEY)
    if i == -1:
        raise AssertionError("gövdede RunAtLoad anahtarı yok")
    rest = body[i + len(RUNATLOAD_KEY):]
    stops = [s for s in (rest.find(stop) for stop in REGION_STOPS) if s != -1]
    if not stops:
        raise AssertionError("keepalive bölgesinin sonu bulunamadı (şablon değişti)")
    return body[i:i + len(RUNATLOAD_KEY) + min(stops)]


if __name__ == "__main__":
    unittest.main()
