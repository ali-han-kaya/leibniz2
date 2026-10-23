#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canlı akış (runstream) DOM-yazım sözleşmesi — rAF-birleştirme (QA bulgusu F4).

preview.js akış yolunda her satır `el.innerHTML = streamLines.join("\\n")`
ile DOM'a yazılıyordu; replay açılışında (≈19k satır) satır-başı tam-DOM
serileştirmesi main-thread'i kilitliyordu (QA bulgusu F4, 2026-09-23; onarım
commit'i: fix(dashboard): mirror frontend deploy seti + stream rAF kilidi).
Onarım, satır-başı yazımı `streamDirty` bayrağı + TEK
`requestAnimationFrame(flushStream)` ile birleştirir; replay-start /
replay-end / end ise bilinçli olarak tek-seferlik doğrudan yazar.

Kapının dişleri kendi içinde kanıtlanır: analiz saf fonksiyondur
(analyze_stream_contract) ve sentetik fixture'larla (a) satır-başı innerHTML
deseninin, (b) yorumla gizlenmiş rAF + gerçek doğrudan yazımın kırmızı
olduğu, (c) yorumlanmış yazımın kırmızı olmadığı gösterilir. Yorumlar koda
sayılmaz — yorumlanmış desen kapıyı ne yeşile çevirir ne de yanlışlıkla
kırmızıya.
"""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW_JS = os.path.join(HERE, "preview.js")

PUSH_YOK = "push-bulunamadi"
PUSH_DOM_YAZIMI = "push-govdesi-dom-yazimi"
PUSH_RAF_ZAMANLAMA = "push-tek-raf-zamanlama"
FLUSH_YOK = "flushstream-bulunamadi"
FLUSH_ERKEN_DONUS = "flushstream-erken-donus"
FLUSH_BAYRAK_SIRASI = "flushstream-bayrak-sirasi"
FLUSH_DOGRUDAN_ARAMA = "flushstream-runstream-arama"
FLUSH_TEK_YAZIM = "flushstream-tek-yazim"
FLUSH_SCROLL = "flushstream-scroll"
DOSYA_TEK_RAF = "dosya-tek-raf-cagrisi"

_IHLAL_ACIKLAMA = {
    PUSH_YOK: "push() akış göndericisi bulunamadı",
    PUSH_DOM_YAZIMI: "push() gövdesi DOM'a doğrudan yazıyor (satır-başı desen)",
    PUSH_RAF_ZAMANLAMA: "push() tek rAF zamanlaması içermiyor",
    FLUSH_YOK: "flushStream() bulunamadı",
    FLUSH_ERKEN_DONUS: "flushStream() temiz bayrakta erken dönmüyor",
    FLUSH_BAYRAK_SIRASI: "streamDirty, innerHTML yazımından önce temizlenmiyor",
    FLUSH_DOGRUDAN_ARAMA: "flushStream() runstream'i kendi çözmüyor",
    FLUSH_TEK_YAZIM: "flushStream() içinde tek streamLines yazımı yok",
    FLUSH_SCROLL: "flushStream() scrollTop'u güncellemiyor",
    DOSYA_TEK_RAF: "requestAnimationFrame(flushStream) çağrısı tam 1 ve push içinde değil",
}

_RAF = r"requestAnimationFrame\s*\(\s*flushStream\s*\)"
_REGEX_BASLATAN = set("([{=,:;!&|?+-*%^~<>")


def _strip_comments(src):
    """Yorumları boşluğa çevirir; (code, shape) görünümlerini döndürür.

    code : yorumlar silinmiş, dizge/regex gövdeleri KORUNMUŞ metin (desen
           aramaları içindir: $("runstream") gibi dizge argümanları görünür).
    shape: yorumlar + dizge/regex gövdeleri boşluk olan metin; yalnızca
           ayraç (brace) eşlemesi içindir — dizge içindeki '{' sayılmaz.
    İki görünüm de kaynakla AYNI uzunluktadır, böylece konum uzayı paylaşılır;
    yeni satırlar her iki görünümde de korunur.
    """
    code = list(src)
    shape = list(src)
    n = len(src)

    def blank(a, b):
        for k in range(a, b):
            if shape[k] != "\n":
                shape[k] = " "

    def blank_code(a, b):
        for k in range(a, b):
            if code[k] != "\n":
                code[k] = " "

    i = 0
    last = ""
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            blank_code(i, j)
            i = j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            blank_code(i, j)
            i = j
            continue
        if c in "\"'`":
            quote = c
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    blank(i, i + 2)
                    i += 2
                    continue
                blank(i, i + 1)
                i += 1
                if ch == quote:
                    break
            last = quote
            continue
        if c == "/" and (last == "" or last in _REGEX_BASLATAN):
            j = i + 1
            in_class = False
            while j < n:
                ch = src[j]
                if ch == "\\" and j + 1 < n:
                    blank(j, j + 2)
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                blank(j, j + 1)
                j += 1
                if ch == "/" and not in_class:
                    break
            i = j
            last = "/"
            continue
        if not c.isspace():
            last = c
        i += 1
    return "".join(code), "".join(shape)


def _block(code, shape, anchor):
    """anchor'ı shape'te bulup { } dengesiyle gövdeyi çıkarır.

    (govde, baslangic, bitis) döner; baslangic = '{' sonrası ilk konum,
    bitis = kapanış '}' konumu. Bulunamazsa None. Dizge/yorum gövdeleri
    shape'te boşaltıldığı için ayraç dengesi yalnızca gerçek kodu sayar.
    """
    m = re.search(anchor, shape)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(shape):
        c = shape[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return code[start:i], start, i
        i += 1
    return None


def analyze_stream_contract(src):
    """Kaynağı F4 sözleşmesine göre denetler; ihlal kimlikleri listesi döner.

    Saf fonksiyon: fixture testleri aynı analizden geçer, böylece kapının
    gerçek dosya dışındaki dişleri de kanıtlanır (fail-closed).
    """
    code, shape = _strip_comments(src)
    violations = []

    push = _block(code, shape, r"\bpush\s*=\s*\([^)]*\)\s*=>\s*\{")
    if push is None:
        violations.append(PUSH_YOK)
    else:
        body = push[0]
        if re.search(r"\binnerHTML\b", body):
            violations.append(PUSH_DOM_YAZIMI)
        tek_zamanlama = (
            r"if\s*\(\s*!\s*streamDirty\s*\)\s*\{\s*"
            r"streamDirty\s*=\s*true\s*;\s*" + _RAF + r"\s*;"
        )
        if not re.search(tek_zamanlama, body):
            violations.append(PUSH_RAF_ZAMANLAMA)
        if len(re.findall(r"\brequestAnimationFrame\s*\(", body)) != 1:
            violations.append(PUSH_RAF_ZAMANLAMA)

    flush = _block(code, shape, r"\bfunction\s+flushStream\s*\(\s*\)\s*\{")
    if flush is None:
        violations.append(FLUSH_YOK)
    else:
        body = flush[0]
        if not re.search(r"if\s*\(\s*!\s*streamDirty\s*\)\s*return\s*;", body):
            violations.append(FLUSH_ERKEN_DONUS)
        once_temiz = re.search(
            r"streamDirty\s*=\s*false\s*;.*?\binnerHTML\b", body, re.S)
        sonra_temiz = re.search(
            r"\binnerHTML\b.*?streamDirty\s*=\s*false\s*;", body, re.S)
        if not once_temiz or sonra_temiz:
            violations.append(FLUSH_BAYRAK_SIRASI)
        if not re.search(r"\$\s*\(\s*[\"']runstream[\"']\s*\)", body):
            violations.append(FLUSH_DOGRUDAN_ARAMA)
        if len(re.findall(r"innerHTML\s*=\s*streamLines\.join\s*\(", body)) != 1:
            violations.append(FLUSH_TEK_YAZIM)
        if not re.search(r"\bscrollTop\s*=", body):
            violations.append(FLUSH_SCROLL)

    rafs = list(re.finditer(_RAF, code))
    if len(rafs) != 1:
        violations.append(DOSYA_TEK_RAF)
    elif push is not None and not (push[1] <= rafs[0].start() < push[2]):
        violations.append(DOSYA_TEK_RAF)

    # ayni kimlik birden fazla kontrolden gelebilir: tekrari tek satira indir
    return list(dict.fromkeys(violations))


def _aciklamali(violations):
    """İhlalleri okunur bir mesaja çevirir."""
    return "; ".join(f"{v} ({_IHLAL_ACIKLAMA.get(v, '?')})" for v in violations)


# --- sentetik fixture'lar (kapının diş kanıtı) ------------------------------

_FLUSH_IYI = (
    "function flushStream() {\n"
    "  if (!streamDirty) return;\n"
    "  streamDirty = false;\n"
    '  const el = $("runstream");\n'
    "  el.innerHTML = streamLines.join(\"\\n\");\n"
    "  el.scrollTop = el.scrollHeight;\n"
    "}"
)

_RAF_BLOK = (
    "    if (!streamDirty) {\n"
    "      streamDirty = true;\n"
    "      requestAnimationFrame(flushStream);\n"
    "    }\n"
)

_YAZIM_SATIRI = "    el.innerHTML = streamLines.join(\"\\n\");\n"

_YORUMLU_RAF = (
    "    // if (!streamDirty) { streamDirty = true; "
    "requestAnimationFrame(flushStream); }\n"
)

_YORUMLU_YAZIM = "    // el.innerHTML = streamLines.join(\"\\n\");\n"

_FLUSH_SIRA_BOZUK = (
    "function flushStream() {\n"
    '  const el = $("runstream");\n'
    "  el.innerHTML = streamLines.join(\"\\n\");\n"
    "  streamDirty = false;\n"
    "  el.scrollTop = el.scrollHeight;\n"
    "}"
)

_FLUSH_CLOSURE_EL = (
    "function flushStream() {\n"
    "  if (!streamDirty) return;\n"
    "  streamDirty = false;\n"
    "  el.innerHTML = streamLines.join(\"\\n\");\n"
    "  el.scrollTop = el.scrollHeight;\n"
    "}"
)


def _fixture(push_govdesi, flush_govdesi=_FLUSH_IYI):
    """Geçerli iskelet + verilen push/flush gövdeleriyle kaynak üretir."""
    return (
        "let streamLines = [];\n"
        "let streamDirty = false;\n"
        + flush_govdesi + "\n"
        + "function connectStream() {\n"
        + '  const el = $("runstream");\n'
        + "  const push = (tag, line, replay) => {\n"
        + "    streamLines.push(colorizeLine(line));\n"
        + push_govdesi
        + "  };\n"
        + "  el.innerHTML = streamLines.join(\"\\n\");\n"
        + "}\n"
    )


class PreviewStreamRafBatchingTest(unittest.TestCase):
    """F4 sözleşmesi: push DOM'a yazmaz, tek rAF ile flushStream'e birleşir."""

    def test_gercek_preview_js_sozlesmeyi_saglar(self):
        """preview.js tüm F4 ihlallerinden arınmış olmalı."""
        with open(PREVIEW_JS, encoding="utf-8") as f:
            violations = analyze_stream_contract(f.read())
        self.assertEqual([], violations,
                         "F4 sözleşme ihlalleri: " + _aciklamali(violations))

    def test_satir_basi_innerhtml_deseni_kirmizi(self):
        """Eski satır-başı innerHTML deseni ihlal üretmeli (diş kanıtı)."""
        src = _fixture(_YAZIM_SATIRI)
        self.assertIn(PUSH_DOM_YAZIMI, analyze_stream_contract(src))

    def test_yorumlanmis_raf_gercek_yazimi_gizleyemez(self):
        """Yorumla kapatılan rAF + gerçek doğrudan yazım kırmızı kalmalı."""
        src = _fixture(_YORUMLU_RAF + _YAZIM_SATIRI)
        violations = analyze_stream_contract(src)
        self.assertIn(PUSH_DOM_YAZIMI, violations)
        self.assertIn(PUSH_RAF_ZAMANLAMA, violations)

    def test_yorumlanmis_yazim_yanlis_kirmizi_uretmez(self):
        """Yorumlanmış yazım kod sayılmamalı (tarayıcı yorum-duyarlı)."""
        src = _fixture(_YORUMLU_YAZIM + _RAF_BLOK)
        self.assertEqual([], analyze_stream_contract(src),
                         "yorumlanmış desen kapıyı kırmızıya çevirmemeli")

    def test_flushstream_bayragi_yazimdan_once_temizler(self):
        """streamDirty=false, innerHTML yazımından ÖNCE gelmeli."""
        src = _fixture(_RAF_BLOK, flush_govdesi=_FLUSH_SIRA_BOZUK)
        violations = analyze_stream_contract(src)
        self.assertIn(FLUSH_BAYRAK_SIRASI, violations)
        self.assertIn(FLUSH_ERKEN_DONUS, violations)

    def test_flushstream_runstreami_kendi_cozer(self):
        """flushStream closure el'e değil kendi $(\"runstream\") çözümüne bağlı."""
        src = _fixture(_RAF_BLOK, flush_govdesi=_FLUSH_CLOSURE_EL)
        self.assertIn(FLUSH_DOGRUDAN_ARAMA, analyze_stream_contract(src))

    def test_ikinci_bir_raf_cagrisi_kirmizi(self):
        """Dosyada ikinci requestAnimationFrame(flushStream) olmamalı."""
        src = _fixture(_RAF_BLOK + _RAF_BLOK)
        self.assertIn(DOSYA_TEK_RAF, analyze_stream_contract(src))


if __name__ == "__main__":
    unittest.main()
