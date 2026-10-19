#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_static_isolation.py — statik varlık izolasyon sözleşmeleri.

`serve_slides` (`/slides_z3/`) ve `serve_landing_assets` (`/landing/assets/`)
kendi köklerine hapsetmek için DÖRT katman kullanır:

  1. tek path segment (içinde `/` yok),
  2. nokta ile başlamıyor (gizli dosya),
  3. yalnız `.png` uzantısı + `^[A-Za-z0-9._-]+$` karakter kümesi,
  4. `os.path.realpath` + `os.path.commonpath` ile sembol bağı kaçışı engeli.

`/video/` allowlist tabanlı olduğu için (`test_preview_video_player.py`
kapsamında) burada tekrarlanmaz.

**POZİTİF KONTROL ZORUNLU.** Bu modülün asıl tuzağı: guard'lar
"her şeyi reddet" haline gelirse (kırık regex, yanlış dizin, dosya yok)
TÜM saldırı testleri sessizce geçer ve görünürde "izolasyon sağlam"
görünür. Bu yüzden her guard grubu geçerli dosya senaryolarıyla da
sınanır: 200 görmek zorundayız. Sadece 404 gören bir kapı bu testleri
geçemez.

**ÖLÇÜLEN KIRILGANLIK.** Dört katmandan yalnız `realpath`+`commonpath`
davranışsal olarak yük taşıyor: karakter, uzantı ve gizli dosya
filtreleri tek tek devre dışı bırakıldığında sunucu yine de 404 dönüyor
(çünkü o adlar diskte yok). Kalan üçü savunma derinliği. Bunu mutasyonla
ölçtüm; bu yüzden `test_guard_stack_is_still_present_in_source` onları
yapısal olarak sabitler — davranış testleri onları yakalayamaz.
"""

import os
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402

# İçinde gerçekten var olması gereken pozitif kontrol dosyaları.
GOOD_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)


class StaticIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls._tmp.name)
        (root / "preview.html").write_text(
            '<!doctype html><html><body><script data-build-ts>'
            '</script></body></html>', encoding="utf-8")
        for sub in (pathlib.Path("slides_z3"),
                    pathlib.Path("landing") / "assets"):
            (root / sub).mkdir(parents=True, exist_ok=True)

        # Pozitif kontroller: guard'lar bunları SERVIS etmek zorunda.
        (root / "slides_z3" / "P1-a.png").write_bytes(GOOD_PNG)
        (root / "slides_z3" / "K8-z3.png").write_bytes(GOOD_PNG)
        (root / "landing" / "assets" / "hero.png").write_bytes(GOOD_PNG)

        # Sembol bağı kök DIŞINA kaçıyor — gerçek dosya var, yine de
        # 404'lenmeli (realpath + commonpath katmanı).
        cls._outside = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False)
        cls._outside.write(GOOD_PNG)
        cls._outside.close()
        try:
            os.symlink(cls._outside.name,
                       root / "slides_z3" / "linked.png")
            cls.symlink_supported = True
        except (OSError, NotImplementedError):
            cls.symlink_supported = False

        cls._old_preview_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = cls._tmp.name
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        if cls._old_preview_dir is None:
            if hasattr(ps, "PREVIEW_DIR"):
                del ps.PREVIEW_DIR
        else:
            ps.PREVIEW_DIR = cls._old_preview_dir
        try:
            os.unlink(cls._outside.name)
        except OSError:
            pass
        cls._tmp.cleanup()

    def _status(self, path):
        req = urllib.request.Request(self.base + path,
                                     headers={"Host": "127.0.0.1"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _both_prefixes(self, name):
        return ("/slides_z3/" + name, "/landing/assets/" + name)

    # ---- pozitif kontrol: guard'lar her şeyi reddetmiyor ------------------

    def test_valid_png_is_served_on_both_roots(self):
        """Olumlu kontrol: gerçek dosya 200 döner ve bayt bayt gelir."""
        for prefix, name in (("/slides_z3/", "P1-a.png"),
                             ("/slides_z3/", "K8-z3.png"),
                             ("/landing/assets/", "hero.png")):
            status, body = self._status(prefix + name)
            self.assertEqual(status, 200,
                             "%s%s 200 vermedi — guard'lar her şeyi "
                             "reddediyor olabilir" % (prefix, name))
            self.assertEqual(body, GOOD_PNG, prefix + name)

    def test_missing_but_well_formed_name_is_404(self):
        """Kara kutu değil: kök içinde olmayan geçerli ad 404."""
        for prefix in ("/slides_z3/", "/landing/assets/"):
            status, _ = self._status(prefix + "yok-boyle-bir-dosya.png")
            self.assertEqual(status, 404, prefix)

    # ---- yol kaçışı -------------------------------------------------------

    def test_parent_directory_escape_is_refused(self):
        for name in ("../preview.html", "..%2fpreview.html",
                     "../../preview.html", "....//preview.html"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404,
                                 "yol kacisi sizdi: %s" % prefix)

    def test_url_encoded_traversal_is_refused(self):
        """`%2e%2e` tarayıcıda `..` olur — ham metne bakmak yetmez."""
        for name in ("%2e%2e%2fpreview.html", "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                     "%252e%252e%252fpreview.html"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404,
                                 "kodlanmis yol kacisi sizdi: %s" % prefix)

    def test_nested_path_is_refused(self):
        """İçinde `/` olan ad tek segment değildir."""
        for name in ("sub/dir.png", "slides_z3/P1-a.png", "a/b/c/d.png"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404, prefix)

    def test_absolute_and_tilde_paths_are_refused(self):
        for name in ("/etc/passwd", "~root/.ssh/id_rsa", "/tmp/x.png"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404, prefix)

    def test_symlink_pointing_outside_root_is_refused(self):
        """Sembol bağı kökü atlamaya çalışıyor; realpath yakalar."""
        if not self.symlink_supported:
            self.skipTest("platform sembol bagini desteklemiyor")
        for prefix in self._both_prefixes("linked.png"):
            status, _ = self._status(prefix)
            self.assertEqual(status, 404,
                             "sembol bagi kacisi sizdi: %s" % prefix)

    # ---- uzantı / karakter beyaz listesi ---------------------------------

    def test_non_png_extension_is_refused(self):
        for name in ("x.html", "x.htm", "x.svg", "x.js", "x.php",
                     "x.png.html", "x.html.png", "x.PNG.png", "x.sh"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404,
                                 "uzanti filtresi sizdi: %s" % prefix)

    def test_hidden_file_is_refused(self):
        for name in (".env", ".htaccess", "..png", ".hidden.png"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404, prefix)

    def test_shell_and_template_metacharacters_are_refused(self):
        """Kabuk/şablon metakarakterleri — URI'de gecilebilir (sub-delims)."""
        for name in ("a;rm.png", "a$(id).png", "a`id`.png", "a|b.png",
                     "a<b>.png", "a&b.png", "a'b.png", 'a"b.png',
                     "a,b.png", "a=b.png", "a!b.png", "a*b.png"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404,
                                 "karakter filtresi sizdi: %s" % prefix)

    def test_percent_encoded_specials_are_refused(self):
        """Boşluk/NUL/`<` gibi karakterler ham gönderilemez.

        Tarayici bunlari YUZDE KODLAYARAK gonderir — sunucunun gördüğü de
        budur, kodlanmis hali sinanir (kodlamadan onceki hâli degil).
        """
        for name in ("a%20b.png", "a%00b.png", "a%3Cb%3E.png", "a%60id%60.png",
                     "a%7Crm.png", "a%24(id).png", "a%3Brm.png"):
            for prefix in self._both_prefixes(name):
                status, _ = self._status(prefix)
                self.assertEqual(status, 404,
                                 "kodlanmis karakter sizdi: %s" % prefix)

    def test_empty_and_bare_root_are_refused(self):
        for prefix in ("/slides_z3/", "/slides_z3", "/landing/assets/",
                       "/landing/assets"):
            status, _ = self._status(prefix)
            self.assertEqual(status, 404, prefix)

    # ---- çıktı sızmıyor ---------------------------------------------------

    def test_no_listing_of_the_directory(self):
        """Dizin listeleme yok: kök 404, içerik dökülmez."""
        for prefix in ("/slides_z3/", "/landing/assets/"):
            status, body = self._status(prefix)
            self.assertEqual(status, 404, prefix)
            self.assertNotIn(b"P1-a", body,
                             "%s dizin icerigini sizdiriyor" % prefix)

    def test_guard_stack_is_still_present_in_source(self):
        """DÖRT katmanın her biri, her iki handler'da da YAPI olarak sabitli.

        **Ölçülen gerçek:** bu katmanlardan yalnız `realpath`+`commonpath`
        davranışsal olarak yük taşıyor — karakter/uzantı/gizli dosya
        filtreleri kaldırıldığında sunucu yine de 404 dönüyor, çünkü o adlar
        diskte zaten yok. Yani onlar BUGÜN savunma-derinliği (defence in
        depth), yani birinin diğerini kaldırdığında tutan katmanlar.

        Bu yüzden davranış testleri onları "ölçmez". Bu test ölçer: biri
        sessizce silinirse davranış değişmez ama savunma derinliği
        erir, ve en azından biri durur. Katmanları kaldırmak isteyen, önce
        bu testi güncellemeli — ki kaybın farkındalığı kayıtta kalsın.
        """
        src = (CIKTI / "preview_server.py").read_text(encoding="utf-8")
        layers = (
            ("tek segment (icinde / yok)", '"/" in name'),
            ("gizli dosya reddi", 'startswith(".")'),
            ("uzanti beyaz listesi (.png)", 'endswith(".png")'),
            ("karakter beyaz listesi", 'r"[A-Za-z0-9._-]+"'),
            ("realpath + commonpath kacis guard'i", "os.path.commonpath"),
        )
        for func in ("serve_slides", "serve_landing_assets"):
            start = src.index("def %s(" % func)
            end = src.index("\n    def ", start)
            body = src[start:end]
            missing = [why for why, needle in layers if needle not in body]
            self.assertEqual(missing, [],
                             "%s: guard katmani eksik — %s. Davranış testleri "
                             "bunu YAKALAMAZ (ölçüldü: realpath katmanı tek "
                             "başına yeter), savunma derinliği sessizce "
                             "eriyor." % (func, "; ".join(missing)))


if __name__ == "__main__":
    unittest.main()
