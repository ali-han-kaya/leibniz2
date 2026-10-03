#!/usr/bin/env python3
"""test_stream_render_coalescing.py — SSE akis render'i kare-basina sozlesmesi.

KOK NEDEN (olcum 2026-10-03, CDP CPU profili; spec: plan dosyasinin
"Evidence" bolumu):
  `push` her satirda `el.innerHTML = streamLines.join("\\n")` ile 600 satirlik
  HTML blogunu yeniden kuruyordu. Replay 14.591 satir oldugunda bu ikinci
  dereceden is 88.0 sn ana-thread kilidi uretti; profilde `push` 62.4 sn
  self-time (311.849/321.552 ornek). Kapinin settle tavani bu yuzden 180 sn'ye
  cikarilmisti.

SOZLESME:
  1) Satir-basina yeniden kurma YOK: `el.innerHTML = streamLines.join` TAM
     OLARAK BIR kez gecer ve o da coalescing yardimcisinin icindedir.
  2) Dort render noktasi da yardimciyi cagirir.
  3) Yardimci bekleyen-bayrak ile korunur: N satir -> tek render.
  4) Kirpma (STREAM_MAX) ve scroll korunur.
  5) rAF DEGIL setTimeout: rAF gizli sekmede duraklatilir, akis bos kalirdi.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW_JS = os.path.join(HERE, "preview.js")

RENDER_BODY = 'el.innerHTML = streamLines.join("\\n");'
HELPER_CALL = "scheduleStreamRender();"


class StreamRenderCoalescingTests(unittest.TestCase):
    """preview.js kaynagi: render kare-basina, satir-basina degil."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_JS, encoding="utf-8") as stream:
            cls.src = stream.read()

    def connect_stream_body(self):
        """connectStream() govdesi (ilk sutun-0 '}' ile biter)."""
        match = re.search(r"function connectStream\(\) \{(.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(match, "connectStream bulunamadi")
        return match.group(1)

    def helper_body(self):
        """scheduleStreamRender govdesi (const ... = () => { ... };)."""
        match = re.search(
            r"const scheduleStreamRender = \(\) => \{(.*?)\n  \};", self.src, re.S
        )
        self.assertIsNotNone(match, "scheduleStreamRender bulunamadi")
        return match.group(1)

    def test_helper_exists_inside_connect_stream(self):
        """Yardimci connectStream icinde olmali: `el` closure'dan gelir."""
        body = self.connect_stream_body()
        self.assertIn("const scheduleStreamRender = () => {", body)

    def test_no_per_line_rebuild_remains(self):
        """Satir-basina yeniden kurma kalkmali.

        Mutation kaniti: `push` icindeki cagriyi eski iki satirlik
        `el.innerHTML = ...` bloguna dondurmek bu testi kirmiziya dusurur.
        """
        body = self.connect_stream_body()
        # push'un kendi govdesinde yeniden kurma YOK
        push = re.search(r"const push = \(tag, line, replay\) => \{(.*?)\n  \};", body, re.S)
        self.assertIsNotNone(push, "push bulunamadi")
        self.assertNotIn(
            RENDER_BODY, push.group(1), "push satir-basina innerHTML kurmamali"
        )

    def test_rebuild_happens_exactly_once_and_in_the_helper(self):
        """`innerHTML = streamLines.join` tam olarak bir kez, yardimci icinde."""
        self.assertEqual(
            self.src.count(RENDER_BODY), 1, "yeniden kurma tek noktada olmali (yardimci)"
        )
        self.assertIn(
            RENDER_BODY, self.helper_body(), "yeniden kurma yardimcinin icinde olmali"
        )

    def test_all_render_sites_use_the_helper(self):
        """Dort render nokasi da (push/replay-start/replay-end/end) yardimciyi cagirir."""
        self.assertEqual(
            self.connect_stream_body().count(HELPER_CALL),
            4,
            "4 render nokasi da scheduleStreamRender cagirmali",
        )

    def test_helper_is_coalesced_with_a_pending_flag(self):
        """N satir -> tek render: bayrak olmadan coalescing olmaz."""
        body = self.helper_body()
        self.assertIn("_streamRenderPending", body)
        self.assertRegex(
            body, r"if \(_streamRenderPending\) return;", "bekleyen render varsa erken donmeli"
        )
        self.assertIn("_streamRenderPending = true;", body)
        self.assertIn("_streamRenderPending = false;", body)

    def test_helper_uses_timeout_not_raf(self):
        """rAF gizli sekmede duraklatilir; akis bos kalmasin diye setTimeout."""
        body = self.helper_body()
        self.assertIn("setTimeout(", body)
        self.assertNotIn("requestAnimationFrame", body)

    def test_trim_and_scroll_preserved(self):
        """Kirpma ve scroll davranisi degismemeli."""
        body = self.helper_body()
        self.assertIn("el.scrollTop = el.scrollHeight;", body)
        # STREAM_MAX kirpmasi connectStream icinde kalmaya devam ediyor
        self.assertIn("STREAM_MAX", self.connect_stream_body())

    def test_no_other_quadratic_renderer_added(self):
        """connectStream tek render noktasi tasimali.

        Dosya genelinde baska `innerHTML = ...join` noktalari var (grafik
        `svg`, tooltip `tip` vb.) ve bunlar akis yolu degil; olcum onlari
        isaret etmedi. Sozlesme yalnizca akis yolunu baglar: connectStream
        icinde TEK join'li innerHTML kalmali ve o da yardimcinin icinde.
        """
        joins = re.findall(
            r"innerHTML = [A-Za-z_]+\.join\(", self.connect_stream_body()
        )
        self.assertEqual(
            len(joins), 1, "akis yolunda tek render noktasi olmali (yardimci)"
        )


if __name__ == "__main__":
    unittest.main()
