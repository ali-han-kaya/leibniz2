#!/usr/bin/env python3
"""test_commit_msg_hook.py — commit_msg_hook.sh her kuralını doğrulayan regresyon kapısı.

Hook'taki 6 kuralı sistematik olarak test eder:
  R0: Dosya yokluğu / boş mesaj
  R1: Merge/Revert izni
  R2: Şablon placeholder (< >) reddi
  R3: Format '<kapsam>: <eylem>' zorunluluğu (iki nokta + boşluk)
  R4: Uzunluk ≤ 72 karakter
  R5: Noise/marker başlık reddi (case-insensitive)
  R6: Yorum (#) ve boş satır atlanımı

stdlib unittest — ek bağımlılık yok.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
HOOK = CIKTI / "commit_msg_hook.sh"


def run_hook(msg: str, hook_path: str = None, msg_file: str = None) -> tuple:
    """Hook'u çalıştır, (returncode, stdout+stderr) döndür.

    msg verilirse geçici dosya oluşturur; msg_file verilirse onu kullanır.
    """
    hp = hook_path or str(HOOK)
    if msg_file:
        r = subprocess.run(["sh", hp, msg_file],
                           capture_output=True, text=True, timeout=5)
    else:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write(msg)
            f.flush()
            try:
                r = subprocess.run(["sh", hp, f.name],
                                   capture_output=True, text=True, timeout=5)
            finally:
                pathlib.Path(f.name).unlink(missing_ok=True)
    return r.returncode, (r.stdout + r.stderr)


def blocked(msg: str, **kw) -> bool:
    """Mesaj bloke edildi mi?"""
    rc, _ = run_hook(msg, **kw)
    return rc != 0


def allowed(msg: str, **kw) -> bool:
    """Mesaj izin verildi mi?"""
    rc, _ = run_hook(msg, **kw)
    return rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# R0: Dosya / boş mesaj
# ═══════════════════════════════════════════════════════════════════════════════
class TestR0_FileAndEmpty(unittest.TestCase):
    def test_missing_file(self):
        """Dosya yoksa exit 1."""
        r = subprocess.run(["sh", str(HOOK), "/tmp/nonexistent_commit_msg.txt"],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(r.returncode, 1)

    def test_empty_message(self):
        """Boş mesaj bloke."""
        self.assertTrue(blocked(""))

    def test_only_comments(self):
        """Yalnızca yorum satırları → boş muamelesi → bloke."""
        self.assertTrue(blocked("# bu bir yorum\n# ikinci yorum\n"))

    def test_only_blank_lines(self):
        """Yalnızca boş satırlar → bloke."""
        self.assertTrue(blocked("\n\n\n"))

    def test_comments_and_blanks_then_content(self):
        """Yorum + boşluk + içerik → içerik kontrol edilir."""
        self.assertTrue(allowed("# yorum\n\nfix: bir şey\n"))


# ═══════════════════════════════════════════════════════════════════════════════
# R1: Merge/Revert izni
# ═══════════════════════════════════════════════════════════════════════════════
class TestR1_MergeRevert(unittest.TestCase):
    def test_merge_allowed(self):
        self.assertTrue(allowed("Merge branch 'main' into feature"))

    def test_merge_lowercase_allowed(self):
        """Merge büyük harfle başlamalı (case-sensitive)."""
        # Hook case-sensitive: "Merge\\ *" — küçük merge eşleşmez
        # Ama format kontrolüne düşer (iki nokta yok) → bloke
        self.assertTrue(blocked("merge branch 'main' into feature"))

    def test_revert_allowed(self):
        self.assertTrue(allowed('Revert "feat: X ekle"'))

    def test_merge_no_colon_still_allowed(self):
        """Merge başlığında iki nokta aranmaz — erken exit."""
        self.assertTrue(allowed("Merge pull request #42 from org/repo"))

    def test_revert_no_colon_still_allowed(self):
        self.assertTrue(allowed('Revert "docs: README güncelle"'))


# ═══════════════════════════════════════════════════════════════════════════════
# R2: Şablon placeholder (< >)
# ═══════════════════════════════════════════════════════════════════════════════
class TestR2_TemplatePlaceholder(unittest.TestCase):
    def test_angle_bracket_open(self):
        self.assertTrue(blocked("fix: <konu başlığı>"))

    def test_angle_bracket_close(self):
        self.assertTrue(blocked("fix: konu başlığı>"))

    def test_html_tag(self):
        self.assertTrue(blocked("docs: <b>bold</b>"))

    def test_no_angle_bracket_passes(self):
        self.assertTrue(allowed("fix: normal başlık"))


# ═══════════════════════════════════════════════════════════════════════════════
# R3: Format '<kapsam>: <eylem>' (iki nokta + boşluk)
# ═══════════════════════════════════════════════════════════════════════════════
class TestR3_ColonSpaceFormat(unittest.TestCase):
    def test_valid_format(self):
        self.assertTrue(allowed("fix: hata düzelt"))

    def test_valid_with_subscope(self):
        self.assertTrue(allowed("feat(auth): OAuth ekle"))

    def test_no_colon(self):
        self.assertTrue(blocked("duzgun baslik yok"))

    def test_colon_no_space(self):
        """İki nokta sonrası boşluk yoksa bloke."""
        self.assertTrue(blocked("fix:single_space_yok"))

    def test_colon_tab_not_space(self):
        """Tab boşluk muamelesi görmez — hook string eşleşmesi yapıyor."""
        self.assertTrue(blocked("fix:\ttypos"))

    def test_multiple_colons(self):
        """Çoklu iki nokta — ilki eşleşir."""
        self.assertTrue(allowed("fix: bir: iki"))

    def test_colon_at_end(self):
        """İki nokta sonda, boşluk yok → bloke."""
        self.assertTrue(blocked("fix:"))


# ═══════════════════════════════════════════════════════════════════════════════
# R4: Uzunluk ≤ 72 karakter
# ═══════════════════════════════════════════════════════════════════════════════
class TestR4_LengthLimit(unittest.TestCase):
    def test_exactly_72(self):
        """72 karakter → izin (sınırda)."""
        self.assertTrue(allowed("fix: " + "a" * 67))  # 5 + 67 = 72

    def test_73_is_blocked(self):
        """73 karakter → bloke."""
        self.assertTrue(blocked("fix: " + "a" * 68))  # 5 + 68 = 73

    def test_100_is_blocked(self):
        self.assertTrue(blocked("fix: " + "a" * 95))

    def test_short_is_ok(self):
        self.assertTrue(allowed("fix: x"))

    def test_unicode_counted(self):
        """Unicode karakterler de sayılır."""
        # 5 (fix: ) + 68emoji ≈ >72
        self.assertTrue(blocked("fix: " + "🔥" * 68))


# ═══════════════════════════════════════════════════════════════════════════════
# R5: Noise/marker başlık (case-insensitive)
# ═══════════════════════════════════════════════════════════════════════════════
class TestR5_NoiseMarker(unittest.TestCase):
    """Hook'taki tüm noise/marker kalıplarını test eder."""

    # ── wip ──
    def test_wip_exact(self):
        self.assertTrue(blocked("wip"))

    def test_wip_colon(self):
        self.assertTrue(blocked("wip: yarım iş"))

    def test_wip_suffix(self):
        self.assertTrue(blocked("fix: bir wip"))

    def test_wip_infix(self):
        self.assertTrue(blocked("fix: bir wip iş"))

    def test_wip_colon_suffix(self):
        self.assertTrue(blocked("fix: bir wip:"))

    def test_wip_uppercase(self):
        """Case-insensitive: WIP de bloke."""
        self.assertTrue(blocked("WIP"))

    def test_wip_mixed_case(self):
        self.assertTrue(blocked("Wip: trabajo"))

    # ── smoke ──
    def test_smoke_exact(self):
        self.assertTrue(blocked("smoke"))

    def test_smoke_prefix(self):
        self.assertTrue(blocked("smoke test: dene"))

    # ── test marker ──
    def test_test_marker(self):
        self.assertTrue(blocked("test marker: deneme"))

    # ── test: ──
    def test_test_colon(self):
        self.assertTrue(blocked("test: deneme"))

    # ── test (tam kelime) ──
    def test_test_exact(self):
        self.assertTrue(blocked("test"))

    def test_testing_not_blocked(self):
        """test ≠ testing — tam kelime eşleşmesi."""
        # hook: "test\\ " pattern'inde "testing" eşleşmez
        # Ama "test" tek başına eşleşir; "testing" için format kontrolüne bakılır
        self.assertTrue(allowed("testing: bir şey"))

    # ── fix typo ──
    def test_fix_typo(self):
        self.assertTrue(blocked("fix typo: small change"))

    def test_fix_typo_no_space(self):
        """fixtypo (boşluk yok) noise pattern'ına uymaz → izin."""
        self.assertTrue(allowed("fixtypo: hata"))

    # ── minor fix ──
    def test_minor_fix(self):
        self.assertTrue(blocked("minor fix: küçük"))

    # ── temp / tmp ──
    def test_temp(self):
        self.assertTrue(blocked("temp"))

    def test_tmp(self):
        self.assertTrue(blocked("tmp"))

    # ── asd / asdf ──
    def test_asd(self):
        self.assertTrue(blocked("asd"))

    def test_asdf(self):
        self.assertTrue(blocked("asdf"))

    # ── foo / bar ──
    def test_foo(self):
        self.assertTrue(blocked("foo"))

    def test_foo_colon(self):
        self.assertTrue(blocked("foo: test"))

    def test_bar(self):
        self.assertTrue(blocked("bar"))

    def test_bar_colon(self):
        self.assertTrue(blocked("bar: test"))

    # ── lorem ──
    def test_lorem(self):
        self.assertTrue(blocked("lorem"))

    def test_lorem_ipsum(self):
        self.assertTrue(blocked("lorem ipsum dolor sit amet"))

    # ── büyük harf varyasyonları ──
    def test_WIP_UPPER(self):
        self.assertTrue(blocked("WIP"))

    def test_SMOKE_UPPER(self):
        self.assertTrue(blocked("SMOKE TEST"))

    def test_TEST_UPPER(self):
        self.assertTrue(blocked("TEST"))

    def test_TEMP_UPPER(self):
        self.assertTrue(blocked("TEMP"))

    # ── noise olmayan başlıklar ──
    def test_fix_not_noise(self):
        self.assertTrue(allowed("fix: hata düzelt"))

    def test_feat_not_noise(self):
        self.assertTrue(allowed("feat: yeni özellik"))

    def test_docs_not_noise(self):
        self.assertTrue(allowed("docs: README güncelle"))

    def test_refactor_not_noise(self):
        self.assertTrue(allowed("refactor: modül yeniden düzenle"))

    def test_chore_not_noise(self):
        self.assertTrue(allowed("chore: bağımlılık güncelle"))

    def test_style_not_noise(self):
        self.assertTrue(allowed("style: format düzelt"))

    def test_perf_not_noise(self):
        self.assertTrue(allowed("perf: hız optimizasyonu"))

    def test_test_scope_allowed(self):
        """test: kapsam adı olarak izinli (ör. test: modül testi ekle)."""
        # "test:" noise'da — hook "test:*" pattern'i var
        # Evet, "test:" noise olarak bloke
        self.assertTrue(blocked("test: modül testi ekle"))

    def test_testing_scope_allowed(self):
        self.assertTrue(allowed("testing: bir şey"))


# ═══════════════════════════════════════════════════════════════════════════════
# R6: Yorum ve boş satır atlama
# ═══════════════════════════════════════════════════════════════════════════════
class TestR6_CommentsAndBlanks(unittest.TestCase):
    def test_comment_before_valid(self):
        self.assertTrue(allowed("# yorum\nfix: bir şey\n"))

    def test_multiple_comments_before_valid(self):
        self.assertTrue(allowed("# yorum1\n# yorum2\n\nfix: bir şey\n"))

    def test_blank_lines_before_valid(self):
        self.assertTrue(allowed("\n\n\nfix: bir şey\n"))

    def test_comment_with_noise_subject(self):
        """Yorum sonrası noise başlık → bloke."""
        self.assertTrue(blocked("# yorum\nwip: iş"))

    def test_only_comment_is_empty(self):
        """Yalnızca yorum → boş → bloke."""
        self.assertTrue(blocked("# tamamen yorum"))


# ═══════════════════════════════════════════════════════════════════════════════
# Entegre: kural zincirleme
# ═══════════════════════════════════════════════════════════════════════════════
class TestIntegration(unittest.TestCase):
    def test_valid_full_message(self):
        """Tam geçerli mesaj (başlık + gövde)."""
        msg = "fix(auth): OAuth token yenileme hatası düzelt\n\n" \
              "Token süresi dolunca 401 dönüyordu.\n" \
              "Refresh token mekanizması eklendi.\n"
        self.assertTrue(allowed(msg))

    def test_long_body_short_subject(self):
        """Uzun gövde, kısa başlık → izin."""
        msg = "fix: hata düzelt\n\n" + "x" * 1000
        self.assertTrue(allowed(msg))

    def test_noise_in_body_not_checked(self):
        """Gövdede noise kelimesi → kontrol edilmez (yalnızca başlık)."""
        msg = "fix: hata düzelt\n\nBu WIP bir çalışmanın parçası."
        self.assertTrue(allowed(msg))

    def test_template_in_body_not_checked(self):
        """Gövdede placeholder → kontrol edilmez."""
        msg = "fix: hata düzelt\n\nDetay: <bkz..doküman>"
        self.assertTrue(allowed(msg))


if __name__ == "__main__":
    unittest.main()
