#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_video_render.py — check_render.py mp4 ayrıştırıcı testleri.

Neden sentetik dosya: ayrıştırıcı mp4 KUTU ofsetlerine dayanır ve gerçek
dosya ancak `npm run render` sonrası var olur (CI'da 760 kare render 20 sn).
Birim testi bunu beklemez — elle kurulmuş bir mp4 iskeleti üretir ve
alanların DOĞRU kutu içinde olduğunu sabitler.

Bu testin varlık sebebi ölçülmüş bir hata sınıfı: gövde başlangıcı ile kutu
başlangıcı karıştırıldığında (veya alan ofsetleri gövdeye göre yazıldığında)
ayrıştırıcı SESSİZCE yanlış sayı üretiyordu — 760 kare yerine 4010, süre
631 sn, çözünürlük 0x0 ölçüldü. Kutu ofsetleri kayarsa test kırılır.

stdlib unittest — PyYAML/node/ffmpeg gerektirmez.
"""

import importlib.util
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(os.path.dirname(HERE), "video")
GATE = os.path.join(VIDEO, "check_render.py")


def _load_gate():
    spec = importlib.util.spec_from_file_location("video_check_render", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + typ + payload


def _fullbox(typ: bytes, version: int, payload: bytes) -> bytes:
    return _box(typ, struct.pack(">B3s", version, b"\x00\x00\x00") + payload)


def build_mp4(frames=760, timescale=90000, width=1280, height=720,
              duration_units=None, container_scale=1000,
              container_duration=None, include_audio=True):
    """Geçerli bir mp4 iskeleti kurar (tek video trak + istege bağlı ses)."""
    if duration_units is None:
        duration_units = frames * timescale // 30

    mvhd = _fullbox(b"mvhd", 0, struct.pack(">IIII", 0, 0, container_scale,
                                            container_duration or 25387))
    tkhd = _fullbox(b"tkhd", 0, struct.pack(">IIIII", 0, 0, 1, 0,
                                           duration_units) + b"\x00" * 60)

    def video_stbl(frames, timescale, duration_units, width, height):
        avc1 = _box(b"avc1", b"\x00" * 6 + struct.pack(">H", 1)
                    + b"\x00" * 16 + struct.pack(">HH", width, height)
                    + b"\x00" * 50)
        stsd = _fullbox(b"stsd", 0, struct.pack(">I", 1) + avc1)
        stsz = _fullbox(b"stsz", 0, struct.pack(">II", 0, frames))
        stts = _fullbox(b"stts", 0, struct.pack(">I", 1)
                        + struct.pack(">II", frames, timescale // 30))
        return _box(b"stbl", stsd + stts + stsz)

    def media(handler, stbl):
        mdhd = _fullbox(b"mdhd", 0, struct.pack(">IIII", 0, 0, timescale,
                                                duration_units))
        hdlr = _fullbox(b"hdlr", 0, struct.pack(">I", 0) + handler + b"\x00" * 12)
        # minf dogrudan stbl SARAR (gercek mp4 duzeni: minf > stbl).
        # Ic ice stbl sarmalamak ayristiriciyi yaniltir (olculdu).
        minf = _box(b"minf", stbl)
        return _box(b"mdia", mdhd + hdlr + minf)

    video = _box(b"trak", tkhd + media(b"vide", video_stbl(
        frames, timescale, duration_units, width, height)))
    tracks = video
    if include_audio:
        aud_stbl = _box(b"stbl",
                        _fullbox(b"stsd", 0, struct.pack(">I", 1)
                                 + _box(b"mp4a", b"\x00" * 6 + struct.pack(">H", 1)
                                        + b"\x00" * 16 + struct.pack(">HH", 2, 16)
                                        + b"\x00" * 20))
                        + _fullbox(b"stsz", 0, struct.pack(">II", 0, 1190)))
        tracks += _box(b"trak", _fullbox(b"tkhd", 0, b"\x00" * 64)
                       + media(b"soun", aud_stbl))

    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2avc1mp41")
    return ftyp + _box(b"moov", mvhd + tracks) + _box(b"mdat", b"\x00" * 64)


class TestBoxWalker(unittest.TestCase):
    def setUp(self):
        self.gate = _load_gate()

    def test_finds_top_level_boxes(self):
        buf = build_mp4()
        types = [t for _, _, t in self.gate._boxes(buf, 0, len(buf))]
        self.assertEqual(types, [b"ftyp", b"moov", b"mdat"])

    def test_find_returns_body_start_and_box_end(self):
        buf = build_mp4()
        start, end = self.gate._find(buf, [b"moov"])
        size, typ = struct.unpack(">I4s", buf[start - 8:start])
        self.assertEqual(typ, b"moov")
        self.assertEqual(end, (start - 8) + size)

    def test_truncated_box_is_rejected(self):
        """`_boxes` bir GENERATOR — yurutulmedigi icin hata yukselmez."""
        buf = build_mp4()[:-20]
        with self.assertRaises(self.gate.ProbeError):
            list(self.gate._boxes(buf, 0, len(buf)))

    def test_missing_path_raises(self):
        with self.assertRaises(self.gate.ProbeError):
            self.gate._find(build_mp4(), [b"nope"])


class TestProbe(unittest.TestCase):
    """Sentetik dosyadan ölçülen değerler tam olmalı."""

    def setUp(self):
        self.gate = _load_gate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, blob):
        path = os.path.join(self.tmp.name, "x.mp4")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    def test_reads_frames_duration_and_size(self):
        path = self._write(build_mp4())
        t = self.gate.probe(path)
        self.assertEqual(t["frames"], 760)
        self.assertEqual((t["width"], t["height"]), (1280, 720))
        self.assertAlmostEqual(t["duration_s"], 760 / 30, places=3)
        self.assertAlmostEqual(t["container_duration_s"], 25.387, places=3)
        self.assertEqual(t["timescale"], 90000)

    def test_picks_video_track_not_audio(self):
        """Ses trakı önce gelirse bile VIDEOLU trak seçilir (hdlr ayrımı)."""
        path = self._write(build_mp4(include_audio=True))
        t = self.gate.probe(path)
        self.assertEqual(t["frames"], 760)
        self.assertEqual(t["width"], 1280)

    def test_custom_dimensions_are_read(self):
        path = self._write(build_mp4(frames=100, width=1920, height=1080))
        t = self.gate.probe(path)
        self.assertEqual((t["width"], t["height"]), (1920, 1080))
        self.assertEqual(t["frames"], 100)

    def test_non_mp4_rejected(self):
        path = self._write(b"NOTANMP4" + b"\x00" * 64)
        with self.assertRaises(self.gate.ProbeError):
            self.gate.probe(path)


class TestContract(unittest.TestCase):
    """Sözleşme denetimi: sapma varsa FAIL, yoksa PASS."""

    def setUp(self):
        self.gate = _load_gate()

    def test_correct_render_passes(self):
        self.assertEqual(self.gate.check(self._track()), [])

    def _track(self, **kw):
        t = {
            "timescale": 90000,
            "duration_s": 760 / 30,
            "frames": 760,
            "width": 1280,
            "height": 720,
            "file_bytes": 1893475,
            "container_duration_s": 25.387,
        }
        t.update(kw)
        return t

    def test_wrong_frame_count_fails(self):
        self.assertTrue(self.gate.check(self._track(frames=700)))

    def test_wrong_dimensions_fail(self):
        self.assertTrue(self.gate.check(self._track(width=1920, height=1080)))
        self.assertTrue(self.gate.check(self._track(width=0, height=0)))

    def test_wrong_duration_fails(self):
        self.assertTrue(self.gate.check(self._track(duration_s=10.0)))

    def test_duration_tolerance_is_tight(self):
        """±0.1 sn tolerans: 1 kare (0.033 sn) sapma geçer, 2 kare geçmez."""
        self.assertEqual(self.gate.check(self._track(duration_s=760 / 30 + 0.03)), [])
        self.assertTrue(self.gate.check(self._track(duration_s=760 / 30 + 0.5)))

    def test_every_problem_is_reported_not_just_first(self):
        problems = self.gate.check(
            self._track(frames=1, width=1, height=1, duration_s=1.0)
        )
        self.assertEqual(len(problems), 3, problems)


class TestCli(unittest.TestCase):
    """Çıkış kodları: 0 = PASS, 1 = sapma, 2 = okunamıyor."""

    def setUp(self):
        self.gate = _load_gate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, blob, name="x.mp4"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    def test_exit_0_on_match(self):
        self.assertEqual(self.gate.main([self._write(build_mp4())]), 0)

    def test_exit_1_on_contract_violation(self):
        path = self._write(build_mp4(frames=700))
        self.assertEqual(self.gate.main([path]), 1)

    def test_exit_2_on_missing_file(self):
        self.assertEqual(self.gate.main([os.path.join(self.tmp.name, "yok.mp4")]), 2)

    def test_exit_2_on_unparsable(self):
        self.assertEqual(self.gate.main([self._write(b"xxxx")]), 2)

    def test_json_output_shape(self):
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.gate.main([self._write(build_mp4()), "--json"])
        import json

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["track"]["frames"], 760)
        self.assertEqual(payload["problems"], [])


class TestGeneratorsAreStdlib(unittest.TestCase):
    def test_check_render_imports_only_stdlib(self):
        with open(GATE, encoding="utf-8") as fh:
            tree = __import__("ast").parse(fh.read())
        imported = set()
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, __import__("ast").ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(
            imported, {"argparse", "json", "os", "struct", "sys", "make_data"}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
