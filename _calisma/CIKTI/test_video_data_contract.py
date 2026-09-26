#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_video_data_contract.py — LeibnizChain kompozisyon sözleşmesi.

Kare bütçesi ÜÇ yerde birden yaşar ve üçü de birden doğrulanır:
  1. make_data.py           → meta.frames / meta.fps
  2. src/Root.tsx           → <Composition durationInFrames={…} fps={…}>
  3. src/LeibnizChainView.tsx → <Sequence from=… durationInFrames=…> × 6

Bunlardan biri kayarsa ya render beklenenden farklı sürede çıkar ya da
son kare boş/siyah kalır — iki durumda da teslim edilen mp4 sessizce yanlış
olur. Sözleşme testi bu kopukluğu fail-closed yakalar.

Ayrıca verinin kaynağı: her sayı repodan gelmeli. make_data.py'nin girdileri
(history.jsonl, test_id_residual_acceptance_doc.py) gitignore'dadır; bu yüzden
üretim çevrimdışı ve temiz klonada çalışmayabilir — testler bunu bir SÖZLEŞME
ihlali saymaz, yalnız üretim yapılabiliyorsa doğrular, yapılamıyorsa SKIP eder.
"""

import ast
import importlib.util
import json
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
VIDEO = os.path.join(REPO, "_calisma", "video")
MAKE_DATA = os.path.join(VIDEO, "make_data.py")
ROOT_TSX = os.path.join(VIDEO, "src", "Root.tsx")
# Sahne agaci LeibnizChainView'ta yasar (LeibnizChain yalnizca onu sarar).
CHAIN_TSX = os.path.join(VIDEO, "src", "LeibnizChainView.tsx")

SCENES = [
    ("1 · Title", 0, 90),
    ("2 · Timeline", 90, 200),
    ("3 · Evidence", 290, 120),
    ("4 · Gates", 410, 200),
    ("5 · Seal", 610, 100),
    ("6 · Closing", 710, 50),
]


def _load_make_data():
    spec = importlib.util.spec_from_file_location("video_make_data", MAKE_DATA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFrameBudget(unittest.TestCase):
    """make_data.py ↔ Root.tsx ↔ LeibnizChain.tsx kare bütçesi aynı olmalı."""

    def test_scene_durations_sum_to_composition_length(self):
        total = sum(d for _, _, d in SCENES)
        self.assertEqual(total, 760, "sahne sureleri toplami 760 olmali")

    def test_scenes_are_contiguous_and_non_overlapping(self):
        for i, (name, start, dur) in enumerate(SCENES):
            if i == 0:
                self.assertEqual(start, 0, f"{name} 0'dan baslamali")
                continue
            prev_name, prev_start, prev_dur = SCENES[i - 1]
            self.assertEqual(
                start,
                prev_start + prev_dur,
                f"{name} {prev_name} bittikten sonra baslamali (bosluk/ortusme)",
            )

    def test_root_composition_matches_frame_budget(self):
        with open(ROOT_TSX, encoding="utf-8") as fh:
            src = fh.read()
        dur = re.search(r"durationInFrames=\{(\d+)\}", src)
        fps = re.search(r"fps=\{(\d+)\}", src)
        w = re.search(r"width=\{(\d+)\}", src)
        h = re.search(r"height=\{(\d+)\}", src)
        for label, m in (("durationInFrames", dur), ("fps", fps), ("width", w), ("height", h)):
            self.assertIsNotNone(m, "Root.tsx icinde %s bulunamadi" % label)
        self.assertEqual(int(dur.group(1)), 760, "Root.tsx sure = 760 kare olmali")
        self.assertEqual(int(fps.group(1)), 30)
        self.assertEqual((int(w.group(1)), int(h.group(1))), (1280, 720))

    def test_sequences_match_scene_table(self):
        """LeibnizChainView.tsx'teki Sequence from/duration değerleri sahne tablosuyla aynı."""
        with open(CHAIN_TSX, encoding="utf-8") as fh:
            src = fh.read()
        found = [
            (int(m.group(1)), int(m.group(2)))
            for m in re.finditer(
                r"<Sequence from=\{(\d+)\} durationInFrames=\{(\d+)\}", src
            )
        ]
        expected = [(s, d) for _, s, d in SCENES]
        self.assertEqual(found, expected, "Sequence tablosu sahne butcesiyle ortusmuyor")

    def test_make_data_frame_constants_agree(self):
        mod = _load_make_data()
        self.assertEqual(mod.FRAMES, 760)
        self.assertEqual(mod.FPS, 30)
        self.assertEqual((mod.WIDTH, mod.HEIGHT), (1280, 720))
        self.assertAlmostEqual(mod.FRAMES / mod.FPS, 25.3333, places=3)


class TestGeneratedData(unittest.TestCase):
    """make_data.py çalıştırılabiliyorsa ürettiği sözleşmeye uymak zorunda."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_make_data()
        try:
            cls.payload = cls.mod.build()
            cls.available = True
        except SystemExit:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("canli history.jsonl yok (temiz klon / calisma verisi disinda)")

    def test_meta_matches_composition(self):
        meta = self.payload["meta"]
        self.assertEqual(meta["composition"], "LeibnizChain")
        self.assertEqual(meta["frames"], 760)
        self.assertEqual(meta["fps"], 30)
        self.assertEqual((meta["width"], meta["height"]), (1280, 720))
        self.assertAlmostEqual(meta["duration_s"], 25.33, places=2)

    def test_runs_are_numbered_and_ordered(self):
        runs = self.payload["runs"]
        self.assertTrue(runs, "en az bir kosu olmali")
        for i, run in enumerate(runs, 1):
            self.assertEqual(run["n"], i, "kosu sirasi 1..N olmali")
            self.assertRegex(run["day"], r"^\d{4}-\d{2}-\d{2}$")

    def test_run_span_agrees_with_runs(self):
        span = self.payload["run_span"]
        runs = self.payload["runs"]
        self.assertEqual(span["count"], len(runs))
        self.assertEqual(span["first"], runs[0]["day"])
        self.assertEqual(span["last"], runs[-1]["day"])
        self.assertEqual(sum(span["verdicts"].values()), len(runs))
        self.assertFalse(span["data_missing"])

    def test_seal_hashes_are_64_hex(self):
        seal = self.payload["seal"]
        self.assertEqual(
            sorted(seal), ["delivery_raw", "delivery_stripped", "pdftex_3pass"]
        )
        for name, value in seal.items():
            self.assertEqual(len(value), 64, name)
            self.assertRegex(value, r"^[0-9a-f]{64}$", name)

    def test_gate_list_is_k0_k15_with_core_prefix(self):
        gates = self.payload["gates"]
        self.assertEqual(gates["all"], ["K%d" % i for i in range(16)])
        self.assertEqual(gates["core"], ["K%d" % i for i in range(8)])
        self.assertEqual(sorted(gates["names"]), sorted(gates["all"]))


class TestDistributionData(unittest.TestCase):
    """Verdigrafi ve kapi kirilmasi sahnelerinin girdisi.

    Ikisi de history.jsonl'dan TURETILIR; testler yalnizca "uydurma sayi
    uretilmiyor" diye denetler: dagilimlar kosu sayisina toplanir, kapi
    kirkilmasi gercekten sinyalle kesilen kosu sayisina esit olur.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_make_data()
        try:
            cls.payload = cls.mod.build()
            cls.available = True
        except SystemExit:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("canli history.jsonl yok (temiz klon / calisma verisi disinda)")

    def test_distributions_sum_to_run_count(self):
        span = self.payload["run_span"]
        self.assertEqual(sum(span["verdicts"].values()), span["count"])
        self.assertEqual(sum(e["count"] for e in span["exits"]), span["count"])
        self.assertEqual(sum(span["drift"].values()), span["count"])

    def test_exit_segments_carry_signal_names(self):
        """Negatif kod sinyal kodudur ve adı stdlib'den gelir (-15 -> SIGTERM)."""
        for seg in self.payload["run_span"]["exits"]:
            if seg["code"] is not None and seg["code"] < 0:
                self.assertEqual(seg["signal"], "SIGTERM")
            else:
                self.assertIsNone(seg["signal"])

    def test_severity_totals_agree_with_runs(self):
        runs = self.payload["runs"]
        sev = self.payload["run_span"]["severity"]
        self.assertEqual(sev["p0"], sum(r["p0"] or 0 for r in runs))
        self.assertEqual(sev["p1"], sum(r["p1"] or 0 for r in runs))
        self.assertEqual(sev["findings"], sum(r["findings"] for r in runs))
        self.assertEqual(sev["z3_total"], sum(r["z3_total"] for r in runs))

    def test_status_board_parses_every_recorded_item(self):
        span = self.payload["run_span"]
        raw = span["board_raw"]
        self.assertTrue(raw, "son kosunun status_board metni olmali")
        chunks = [c for c in raw.split("·") if c.strip()]
        self.assertEqual(len(span["board"]), len(chunks), "her tahta kalemi ayristirilmali")
        for item in span["board"]:
            self.assertTrue(item["label"], "bos etiket uretilmemeli")
            self.assertIn(item["state"], {"PASS", "WARN", "FAIL", "UNKNOWN"})

    def test_unknown_board_mark_is_never_upgraded_to_pass(self):
        """Tanınmayan isaret UNKNOWN kalir — sessizce PASS sayilmaz."""
        items = self.mod.parse_status_board("K0 ? · Bütçe ✅")
        self.assertEqual(items[0]["state"], "UNKNOWN")
        self.assertEqual(items[1]["state"], "PASS")
        self.assertEqual(self.mod.parse_status_board(""), [])

    def test_board_marks_split_without_spaces(self):
        """"K0✅" ve "K0 ✅" ayni ayrismali (varyasyon seçici temizlenir)."""
        tight = self.mod.parse_status_board("Pre-commit ⚠️ · K0✅")
        self.assertEqual([i["label"] for i in tight], ["Pre-commit", "K0"])
        self.assertEqual([i["state"] for i in tight], ["WARN", "PASS"])

    def test_gate_marks_only_use_real_gate_ids(self):
        """Yeşil işaret yalnız tahtada ADI OLAN kapılara verilir.

        "K katmanları ⚠️" bir kapı numarası değildir: grup uyarısı olarak
        ayrılır, 15 kapıya uydurma PASS dağıtılmaz.
        """
        gates = self.payload["gates"]
        for gid in gates["ok_ids"]:
            self.assertIn(gid, gates["names"], "olmayan kapi yesil gosterilmemeli")
        for label in gates["group_warn"]:
            self.assertNotIn(label, gates["names"], "kapı olmayan etiket ok_ids olamaz")
        self.assertEqual(
            sorted(gates["ok_ids"] + gates["group_warn"]),
            sorted(i["label"] for i in gates["board"]),
        )

    def test_gate_verdict_counts_every_board_item(self):
        v = self.payload["gates"]["verdict"]
        self.assertEqual(v["ok"] + v["warn"] + v["other"], len(self.payload["gates"]["board"]))

    def test_break_block_matches_actual_signal_runs(self):
        """Kırılma sayısı: exit_code<0 olan koşuların KENDİSİ, sabit değil."""
        runs = self.payload["runs"]
        broken = [r for r in runs if r["exit_code"] is not None and r["exit_code"] < 0]
        bk = self.payload["gates"]["break"]
        self.assertEqual(bk["runs"], len(broken))
        self.assertEqual(bk["of_runs"], len(runs))
        self.assertEqual(
            bk["share_pct"], round(100.0 * len(broken) / len(runs), 1) if runs else 0.0
        )
        if broken:
            self.assertEqual(bk["kind"], "signal")
            self.assertLess(bk["exit_code"], 0)
            self.assertTrue(bk["signal"], "sinyal kodu adı cozulmeli")
        else:
            self.assertEqual(bk["kind"], "none")
            self.assertIsNone(bk["exit_code"])
            self.assertIsNone(bk["signal"])

    def test_telemetry_separates_missing_from_zero(self):
        """0/0 (sutun dolu) ile null (rapor yok) ayrı sayılır.

        Bu ayrım dürüstlüğün temeli: 12 sütundan 3'ü dolu görünse bile
        bunlar z3 ailesidir ve değerleri 0'dır.
        """
        tel = self.payload["run_span"]["telemetry"]
        reported = set(tel["reported"])
        unreported = set(tel["unreported"])
        self.assertEqual(reported & unreported, set(), "bir sutun hem dolu hem bos olamaz")
        self.assertEqual(len(reported) + len(unreported), tel["columns"])
        self.assertEqual(len(self.mod.GATE_TELEMETRY), tel["columns"])
        self.assertEqual(
            tel["min_per_run"], tel["max_per_run"], "kosu basina telemetre sabit olmali"
        )

    def test_scenes_consume_the_new_blocks(self):
        """scenes.tsx yeni alanları kullanmalı — grafik sessizce düşmez.

        Not: Timeline sahnesi `const span = data.run_span` ile ayrıştirdığı
        için alanlar `span.*` ön ekiyle aranır.
        """
        with open(os.path.join(VIDEO, "src", "scenes.tsx"), encoding="utf-8") as fh:
            src = fh.read()
        for token in (
            "span.exits",
            "span.verdicts",
            "span.telemetry",
            "span.severity",
            "g.break",
            "g.ok_ids",
            "g.group_warn",
            "g.board_raw",
            "bk.signal",
        ):
            self.assertTrue(
                token in src, "scenes.tsx %s alanini kullanmiyor" % token
            )

    def test_dump_is_stable_and_prettier_compatible(self):
        """Üretim deterministik: iki çağrı bayt bayt aynı.

        Ayrıca `ensure_ascii=False` korunur (Türkçe karakterler kaçmaz) —
        tersi olsaydı sahne metinleri \\uXXXX olarak görünürdü.
        """
        text = self.mod.dumps(self.mod.build())
        self.assertEqual(text, self.mod.dumps(self.mod.build()))
        self.assertTrue(text.endswith("}\n"))
        self.assertNotIn("\\u", text)
        json.loads(text)  # parse edilebilir


class TestSentinelMode(unittest.TestCase):
    """`--allow-missing-data`: temiz klonda/CI'da veri olmadan da üretilebilir.

    history.jsonl gitignore'dadır (preview_server'ın çalışma zamanı verisi),
    yani CI'da HİÇ YOKTUR. Render kapısı orada da koşabilmeli — ama sessizce
    sahte koşu üretmemeli: liste boş kalır ve data_missing işaretlenir.
    """

    def _missing(self, mod):
        saved = mod.HISTORY
        mod.HISTORY = os.path.join(HERE, "yok-boyle-bir-dosya.jsonl")
        self.addCleanup(setattr, mod, "HISTORY", saved)

    def test_sentinel_is_produced_when_history_absent(self):
        mod = _load_make_data()
        self._missing(mod)
        payload = mod.build(allow_missing=True)
        self.assertEqual(payload["runs"], [])
        self.assertTrue(payload["run_span"]["data_missing"])
        self.assertEqual(payload["run_span"]["count"], 0)
        self.assertIsNone(payload["run_span"]["first"])
        self.assertIsNone(payload["run_span"]["last"])

    def test_sentinel_keeps_seal_and_frame_budget(self):
        """Veri yokken bile mühürler ve kare bütçesi üretilir — sahne iskeleti
        ölçülebilir kalsın diye."""
        mod = _load_make_data()
        self._missing(mod)
        payload = mod.build(allow_missing=True)
        self.assertEqual(payload["meta"]["frames"], 760)
        for value in payload["seal"].values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_sentinel_chart_blocks_are_empty_not_invented(self):
        """Veri yokken grafik boş kalır: sıfır bölme, uydurma segment yok.

        CI'daki video-render işi tam olarak bu yolu çizer; `StackBar`
        `total=0` için `safe=1` ile payı böler, dolayısıyla payload'da
        run olmaması tek başına bölmeyi patlatmamalı.
        """
        mod = _load_make_data()
        self._missing(mod)
        payload = mod.build(allow_missing=True)
        span = payload["run_span"]
        self.assertEqual(span["verdicts"], {})
        self.assertEqual(span["exits"], [], "sinyal kodu uydurulmamali")
        self.assertEqual(span["board"], [])
        self.assertEqual(span["board_raw"], "")
        self.assertEqual(span["severity"]["p0"], 0)
        self.assertEqual(payload["gates"]["ok_ids"], [])
        bk = payload["gates"]["break"]
        self.assertEqual(bk["kind"], "no_data")
        self.assertEqual(bk["runs"], 0)
        self.assertEqual(bk["share_pct"], 0.0)
        self.assertIsNone(bk["signal"])

    def test_sentinel_dumps_to_valid_json(self):
        mod = _load_make_data()
        self._missing(mod)
        text = mod.dumps(mod.build(allow_missing=True))
        self.assertEqual(json.loads(text)["run_span"]["data_missing"], True)

    def test_default_mode_still_fails_closed(self):
        """Bayrak verilmeden aynı durum PATLAR — sentinel opt-in."""
        mod = _load_make_data()
        self._missing(mod)
        with self.assertRaises(SystemExit) as ctx:
            mod.build()
        self.assertNotEqual(ctx.exception.code, 0)


class TestGeneratorFailsClosed(unittest.TestCase):

    def test_missing_history_exits_nonzero(self):
        mod = _load_make_data()
        saved = mod.HISTORY
        mod.HISTORY = os.path.join(HERE, "yok-boyle-bir-dosya.jsonl")
        try:
            with self.assertRaises(SystemExit) as ctx:
                mod.build()
            self.assertNotEqual(ctx.exception.code, 0)
        finally:
            mod.HISTORY = saved

    def test_frozen_constant_must_be_64_hex(self):
        """64 haneli olmayan sabit kabul edilmez (sessiz bozuk mühür olmaz)."""
        mod = _load_make_data()
        saved = mod.FROZEN
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write('DELIVERY_RAW = ("abc")\n')
            bad = fh.name
        mod.FROZEN = bad
        try:
            with self.assertRaises(SystemExit):
                mod.build()
        finally:
            mod.FROZEN = saved
            os.unlink(bad)

    def test_generator_is_stdlib_only(self):
        """Yeni bir üçüncü taraf bağımlılık sızması."""
        with open(MAKE_DATA, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        allowed = {
            "argparse",
            "collections",
            "json",
            "os",
            # signal: exit_code=-15 -> "SIGTERM" adı (kapı kırılma bloğu)
            "signal",
            "sys",
            "tempfile",
            "unittest",
        }
        self.assertLessEqual(imported, allowed, "izin verilmeyen import: %s" % imported)


if __name__ == "__main__":
    unittest.main(verbosity=2)
