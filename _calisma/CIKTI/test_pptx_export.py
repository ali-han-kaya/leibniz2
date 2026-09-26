"""test_pptx_export.py — NATIVE pptx üretimi + yapı sözleşmesi (üç deck).

Deck'ler PNG GÖMMEZ: slayt içeriği pptxgenjs native şekilleri (rect/roundRect/
line) ve GERÇEK metin run'larıdır → aranabilir, kopyalanabilir, düzenlenebilir.
Jeneratörler yalnız İÇERİK taşır; yerleşim/metadata/not altyapısı tek ortak
renderer'dadır: `_calisma/pptx/native_deck.js` (renk/tipografi/ızgara:
`tokens.js` → `design-system/tokens.json`).

Doğrulanan sözleşme (verification_chain, architecture_deepening,
pdf_repro_findings):
  - jeneratör kaynağı `./native_deck` üzerinden `renderDeck(...)` çağırır;
    görsel gömme (`addImage` / `.png`) ve ad-hoc hex renk YOK; çıktı dosyası
    deck adıyla eşleşir
  - ortak renderer export sözleşmesini taşır: `LAYOUT_16x9` + `addNotes` +
    title/subject/author/company (metadata tek yerde; jeneratörde aranmaz)
  - yapı: 5 slayt + 5 not; `ppt/media/` BOŞ (native deck gömülü görsel taşımaz);
    presentation.xml'de 5 sldId
  - metin katmanı: her slaytta gerçek metin run'u, deck başına eşiğin üzerinde;
    deck'e özgü slayt metni (başlık/bulgu/hash) slayt XML'inde geçer —
    aranabilirlik iddiası slayt içeriğinde doğrulanır
  - palet: slaytlardaki HER `srgbClr` değeri design-system/tokens.json
    paletinde (palet dışı hex = FAIL; ad-hoc renk sızıntısı yakalanır)
  - geometri: tüm şekil offset/extent'i kanvas içinde (0…10 x 0…5.625 inç, EMU)
  - notlar deck'in kanıt metnini taşır (deck başına işaretler) ve işaretler
    deck'e özgüdür
  - '#'lı renk değeri (CSS kalıntısı) sızmaz

.pptx üretilen çıktıdır (gitignore'lu); test node varsa TAZE üretir (kaynak
jeneratör/renderer/token dosyaları daha yeniyse yeniden derler). node yok ya da
node_modules kurulu değilse yapı-testi SKIP (sebebiyle birlikte) — modül düzeyi
exception değil (setup başarısızlığı bütün dosyayı error'a çevirirdi).
Jeneratör/kaynak sözleşmesi testleri node'suz da koşar: node yokluğu "desen
hâlâ doğru mu" iddiasını düşürmez, yalnız çıktı yapısı doğrulanamaz.
"""

import json
import pathlib
import re
import shutil
import subprocess
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
PPTX_DIR = HERE.parent / "pptx"
NATIVE_RENDERER = PPTX_DIR / "native_deck.js"
TOKENS_JS = PPTX_DIR / "tokens.js"
TOKENS_JSON = HERE.parent.parent / "design-system" / "tokens.json"

SLIDES = 5
EMU_PER_INCH = 914400
CANVAS_W = int(10 * EMU_PER_INCH)       # 1600 px deck = 10 inç
CANVAS_H = int(5.625 * EMU_PER_INCH)    # 900 px deck  = 5.625 inç
# Çıktı tazelenirken bakılacak ortak bağımlılıklar (jeneratör + tek kaynaklar).
REBUILD_DEPS = (NATIVE_RENDERER, TOKENS_JS, TOKENS_JSON)

TEXT_RUN = re.compile(r"<a:t>")
SRGB = re.compile(r'srgbClr val="([0-9a-fA-F]{6})"')
# Bir şeklin xfrm'i: off + ext bitişik yazılır (chOff/chExt ayrı çift).
XFRM = re.compile(
    r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>')

# Deck başına işaretler. `markers` = notlar (kanıt metni), `slide_markers` =
# slayt metni (aranabilir içerik). Hepsi ASCII-güvenli ve deck'e ÖZGÜ.
DECKS = (
    {
        "name": "verification_chain",
        "min_text_runs": 45,   # gözlenen 56 — metin katmanı düşerse FAIL
        "markers": (
            ("notesSlides/notesSlide1.xml", "Integrity is a chain"),
            ("notesSlides/notesSlide4.xml", "No silent PASS"),
        ),
        "slide_markers": (
            ("slides/slide1.xml", "Integrity is a chain, not a checkbox"),
            ("slides/slide4.xml", "Failure modes are first-class outputs"),
        ),
    },
    {
        "name": "architecture_deepening",
        "min_text_runs": 60,   # gözlenen 75
        "markers": (
            ("notesSlides/notesSlide1.xml", "Three ways to deepen the chain"),
            ("notesSlides/notesSlide2.xml", "projection failure is NOT gate failure"),
            ("notesSlides/notesSlide4.xml", "CI blocks source/PDF drift"),
        ),
        "slide_markers": (
            ("slides/slide1.xml", "Three ways to deepen the chain"),
            ("slides/slide5.xml", "Choose depth without moving the trust boundary"),
        ),
    },
    {
        "name": "pdf_repro_findings",
        "min_text_runs": 45,   # gözlenen 55
        "markers": (
            ("notesSlides/notesSlide1.xml", "The shipped PDF is behind its source"),
            ("notesSlides/notesSlide2.xml", "b090ac01"),
            ("notesSlides/notesSlide3.xml", "NON-DETERMINISTIC"),
            ("notesSlides/notesSlide5.xml", "rejoin the same chain"),
        ),
        "slide_markers": (
            # Hash'ler slaytta MONO fontla gerçek metin: kopyalanabilir olması
            # native rewrite'ın varlık sebebi — bu yüzden işaret olarak durur.
            ("slides/slide2.xml", "b090ac01"),
            ("slides/slide3.xml", "NON-DETERMINISTIC"),
        ),
    },
)

_GENERATED = {}


def generator_path(name):
    return PPTX_DIR / f"{name}_pptx.js"


def pptx_path(name):
    return PPTX_DIR / f"{name}.pptx"


_OPAQUE_HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
# Alpha tint'ler (rgba/rgb): pptx'te karşılığı yok — slaytta GÖRÜNEMEZLER,
# bu yüzden palete girmez ama geçerli token sayılır.
_ALPHA_TINT = re.compile(r"rgba?\([^)]*\)\Z")


def tokens_palette(raw):
    """tokens.json içeriğinden opak palet kümesi (BÜYÜK harf, '#'-siz).

    `color` grubu iç içe olabilir (`color.tint.ok-bg` gibi); yürüyüş özyinelemeli.
    Fail-closed: tanınmayan değer sessizce atlanmaz ve boş palet dönmez — boş
    palet palet kapısını vacuously-pass yapardı.
    """
    colors = raw.get("color") if isinstance(raw, dict) else None
    if not isinstance(colors, dict) or not colors:
        raise ValueError("tokens.json: color grubu yok — palet türetilemez")
    palette = set()

    def walk(prefix, node):
        if isinstance(node, dict):
            if not node:
                raise ValueError("tokens.json: %s boş grup" % prefix)
            for key, value in node.items():
                walk("%s.%s" % (prefix, key), value)
            return
        if not isinstance(node, str):
            raise ValueError("tokens.json: %s metin değil: %r" % (prefix, node))
        value = node.strip()
        if _OPAQUE_HEX.match(value):
            palette.add(value[1:].upper())
        elif not _ALPHA_TINT.match(value):
            raise ValueError(
                "tokens.json: %s ne 6-haneli hex ne rgba tint: %r" % (prefix, value))

    walk("color", colors)
    if not palette:
        raise ValueError("tokens.json: color grubunda opak hex token yok")
    return palette


def load_palette():
    """design-system/tokens.json'dan palet (dosya yoksa test FAIL, SKIP değil)."""
    return tokens_palette(json.loads(TOKENS_JSON.read_text(encoding="utf-8")))


def palette_violations(body, palette):
    """Slayt XML'inde palet DIŞI renkler (sorted, tekilleştirilmiş)."""
    return sorted({value.upper() for value in SRGB.findall(body)} - palette)


def shapes_crossing_canvas(body):
    """Kanvas dışına taşan şekil xfrm'leri [(x, y, cx, cy), …] (EMU)."""
    crossing = []
    for x, y, cx, cy in XFRM.findall(body):
        x, y, cx, cy = int(x), int(y), int(cx), int(cy)
        if x < 0 or y < 0 or x + cx > CANVAS_W or y + cy > CANVAS_H:
            crossing.append((x, y, cx, cy))
    return crossing


def embedded_media(names):
    """Zip girdi listesinden gömülü medya parçaları (dizin girdileri hariç)."""
    return sorted(n for n in names
                  if n.startswith("ppt/media/") and not n.endswith("/"))


def _newest_source(name):
    stamps = [path.stat().st_mtime
              for path in (generator_path(name),) + REBUILD_DEPS if path.is_file()]
    return max(stamps) if stamps else 0.0


def ensure_pptx(node, name):
    """(ok, reason) — çıktı yoksa ya da kaynaklardan eskiyse jeneratörü koşar.

    Tazelik kontrolü: eski bir PNG-embed çıktısı testten geçemez (native
    iddiaları düşer) ama bayat dosya yüzünden yanlış FAIL de olmamalı.
    """
    if name in _GENERATED:
        return _GENERATED[name]
    path = pptx_path(name)
    gen = generator_path(name)
    fresh = path.is_file() and path.stat().st_mtime >= _newest_source(name)
    if fresh:
        result = (True, None)
    elif node is None or not gen.is_file():
        result = (False, "node ya da jeneratör yok")
    else:
        proc = subprocess.run(
            [node, str(gen)], cwd=str(PPTX_DIR), check=False, timeout=60,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode == 0 and path.is_file():
            result = (True, None)
        else:
            # İlk Error satırı asıl nedendir (node'un son satırı sürüm bilgisidir:
            # "Node.js v22…"); yoksa ilk anlamlı satıra düş.
            lines = [line.strip() for line in (proc.stderr or proc.stdout or b"")
                     .decode("utf-8", "replace").splitlines() if line.strip()]
            reason = next((line for line in lines if "error" in line.lower()),
                          lines[0] if lines else "cikti yok")
            result = (False, "pptx üretilemedi (node rc=%s): %s" % (
                proc.returncode, reason[-160:]))
    _GENERATED[name] = result
    return result


class TestPptxExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")

    def test_generators_use_the_shared_native_renderer(self):
        for deck in DECKS:
            name = deck["name"]
            with self.subTest(deck=name):
                gen = generator_path(name)
                self.assertTrue(gen.is_file(), "jeneratör kaynağı eksik: %s" % gen)
                src = gen.read_text(encoding="utf-8")
                # tek ortak renderer: yerleşim/metadata/notlar orada
                self.assertIn('require("./native_deck")', src)
                self.assertIn("renderDeck(", src)
                # çıktı dosyası deck adıyla eşleşir (jeneratör başına tek deck)
                self.assertIn('"%s.pptx"' % name, src)
                # native sözleşme: görsel gömme yok (asıl iddia zip yapısında)
                self.assertNotIn("addImage", src)
                self.assertNotIn(".png", src)
                # renkler rol adıyla seçilir: jeneratörde ad-hoc hex olmaz
                self.assertIsNone(
                    re.search(r"#[0-9a-fA-F]{3,6}\b", src),
                    "jeneratörde ad-hoc hex renk var (tokens rolü kullan)")

    def test_shared_renderer_owns_the_export_contract(self):
        """LAYOUT/metadata/addNotes tek yerde: jeneratörler yalnız içerik taşır."""
        src = NATIVE_RENDERER.read_text(encoding="utf-8")
        self.assertIn('pres.layout = "LAYOUT_16x9"', src)
        self.assertIn("addNotes", src)
        for field in ("pres.title", "pres.subject", "pres.author", "pres.company"):
            self.assertIn(field, src)
        # palet/ızgara token katmanından gelir — renderer hex taşımaz
        self.assertIn("T.colors", src)
        self.assertIn("role(", src)
        self.assertTrue(TOKENS_JS.is_file(), "token katmanı eksik: %s" % TOKENS_JS)

    def test_pptx_is_native_searchable_and_palette_locked(self):
        if self.node is None:
            self.skipTest("node yok")
        palette = load_palette()
        for deck in DECKS:
            name = deck["name"]
            with self.subTest(deck=name):
                ok, reason = ensure_pptx(self.node, name)
                if not ok:
                    self.skipTest(reason)
                path = pptx_path(name)
                self.assertTrue(path.is_file(), "pptx üretilemedi")
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
                    slides = sorted(n for n in names
                                    if re.match(r"ppt/slides/slide\d+\.xml$", n))
                    notes = sorted(n for n in names
                                   if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n))
                    media = embedded_media(names)
                    self.assertEqual(len(slides), SLIDES, "5 slayt beklenir")
                    self.assertEqual(len(notes), SLIDES, "her slaytta not beklenir")
                    self.assertEqual(
                        media, [],
                        "native deck gömülü görsel taşımamalı (ppt/media boş olmalı)")
                    pres = z.read("ppt/presentation.xml").decode("utf-8", "replace")
                    self.assertEqual(pres.count("<p:sldId "), SLIDES,
                                     "sldIdLst slayt sayısıyla birebir olmalı")
                    # kanvas dosya düzeyinde de 16:9 olmalı (10 x 5.625 inç)
                    self.assertIn('<p:sldSz cx="%d" cy="%d"/>' % (CANVAS_W, CANVAS_H),
                                  pres, "slayt boyutu 1600x900 (16:9) olmalı")
                    total_runs = 0
                    for part in slides:
                        body = z.read(part).decode("utf-8", "replace")
                        # aranabilirlik: görsel-only slayt kalmaz
                        runs = len(TEXT_RUN.findall(body))
                        self.assertGreaterEqual(
                            runs, 1, "%s metin run'u taşımalı (görsel-only slayt)" % part)
                        total_runs += runs
                        self.assertEqual(
                            palette_violations(body, palette), [],
                            "%s palet dışı renk taşıyor (design-system/tokens.json)" % part)
                        self.assertEqual(
                            shapes_crossing_canvas(body), [],
                            "%s kanvas dışına taşan şekil içeriyor" % part)
                        self.assertNotIn('val="#"', body)
                    self.assertGreaterEqual(
                        total_runs, deck["min_text_runs"],
                        "%s metin katmanı beklenenden zayıf (%s run)" % (name, total_runs))
                    # slayt metni deck'in içeriğini taşır (aranabilirlik iddiası)
                    for part, marker in deck["slide_markers"]:
                        body = z.read("ppt/" + part).decode("utf-8", "replace")
                        self.assertIn(marker, body,
                                      "%s slayt metni %r taşımalı" % (part, marker))
                    # notlar deck'in kanıt metnini taşır
                    for part, marker in deck["markers"]:
                        body = z.read("ppt/" + part).decode("utf-8", "replace")
                        self.assertIn(marker, body,
                                      "%s notu %r metnini taşımalı" % (part, marker))
                    self.assertNotIn('val="#"', pres)

    def test_markers_are_deck_specific(self):
        """İşaret metni ayırt edici olmalı.

        Aynı metin iki deck'in notlarında geçerse yapı-testi "notlar bu
        deck'ten mi" sorusunu yanıtlamaz (kopyala-yapıştır notlar sessizce
        geçerdi). İşaretler bu yüzden deck başına tek olmalı.
        """
        if self.node is None:
            self.skipTest("node yok")
        bodies = {}
        for deck in DECKS:
            ok, reason = ensure_pptx(self.node, deck["name"])
            if not ok:
                self.skipTest(reason)
            with zipfile.ZipFile(pptx_path(deck["name"])) as z:
                bodies[deck["name"]] = "\n".join(
                    z.read(n).decode("utf-8", "replace")
                    for n in z.namelist()
                    if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n))
        for deck in DECKS:
            for _part, marker in deck["markers"]:
                hits = sorted(name for name, body in bodies.items()
                              if marker in body)
                self.assertEqual(
                    hits, [deck["name"]],
                    "%r işareti tek deck'te geçmeli (bulundu: %s)" % (marker, hits))

    def test_palette_and_canvas_gates_catch_violations(self):
        """Kapıların negatif kontrolü: ihlal GÖRÜLMEZSE kapı sahte-yeşildir."""
        palette = load_palette()
        self.assertGreaterEqual(len(palette), 8,
                                "palet beklenenden küçük — token grubu eksik olabilir")
        # palet dışı hex yakalanır; palete 1 bit yakın sapma bile kaçar (accent #58A6FF → #58A6FE)
        body = '<a:solidFill><a:srgbClr val="FF00FF"/></a:solidFill>'
        self.assertEqual(palette_violations(body, palette), ["FF00FF"])
        self.assertEqual(palette_violations('<a:srgbClr val="58A6FE"/>', palette), ["58A6FE"])
        self.assertEqual(palette_violations('<a:srgbClr val="#58A6FF"/>', palette), [])
        # token'ın kendisi (küçük harfle de olsa) geçerli: karşılaştırma normalize
        token = sorted(palette)[0]
        self.assertEqual(
            palette_violations('<a:srgbClr val="%s"/>' % token.lower(), palette), [])
        # kanvas taşması yakalanır (1 EMU bile kaçmaz)
        overflow = ('<a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/>'
                    % (CANVAS_W, CANVAS_H + 1))
        self.assertEqual(shapes_crossing_canvas(overflow), [(0, 0, CANVAS_W, CANVAS_H + 1)])
        inside = ('<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                  % (CANVAS_W - 10, CANVAS_H - 10, 10, 10))
        self.assertEqual(shapes_crossing_canvas(inside), [])
        # negatif offset de taşma sayılır
        self.assertEqual(len(shapes_crossing_canvas(
            '<a:off x="-1" y="0"/><a:ext cx="10" cy="10"/>')), 1)
        # PNG-embed kalıntısı medya kapısından geçmez: görsel girdisi görünür
        self.assertEqual(
            embedded_media([
                "ppt/media/image1.png", "ppt/media/", "ppt/slides/slide1.xml",
            ]),
            ["ppt/media/image1.png"])
        self.assertEqual(embedded_media(["ppt/slides/slide1.xml"]), [])
        # palet kaynağı: opak hex'ler iç içe gruplardan da toplanır, alpha
        # tint'ler (rgba) palete GİRMEZ (slaytta karşılıkları yok)
        self.assertEqual(
            tokens_palette({"color": {
                "accent": "#58a6ff",
                "tint": {"shadow": "rgba(0,0,0,.5)"},
            }}),
            {"58A6FF"})
        # bozuk kaynak sessizce geçmez (boş palet = vacuously PASS olurdu)
        for broken in (
            {"color": {}},                                  # grup yok
            {"color": {"accent": "58A6FF"}},                # '#'siz hex
            {"color": {"accent": "#58A6F"}},                # eksik hex
            {"color": {"tint": {"shadow": "rgba(0,0,0,.5)"}}},  # yalnız tint
            {},                                              # color yok
        ):
            with self.assertRaises(ValueError):
                tokens_palette(broken)


if __name__ == "__main__":
    unittest.main()
