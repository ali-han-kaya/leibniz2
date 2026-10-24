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
WORKFLOW = os.path.join(REPO, ".github", "workflows", "video-render.yml")
COMMENT_JS = os.path.join(HERE, "github_scripts", "video_render_comment.js")

SCENES = [
    ("1 · Title", 0, 90),
    ("2 · Timeline", 90, 200),
    ("3 · Evidence", 290, 110),
    ("4 · GateChain", 400, 210),
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

    def test_gate_chain_carries_real_klayers_statuses(self):
        """Sahnenin 16 düğümü klayers.json'dan gelir; uydurma PASS yok."""
        chain = self.payload["gate_chain"]
        self.assertTrue(chain["runs"], "en az bir klayers koşusu olmalı")
        self.assertEqual(chain["run_count"], len(chain["runs"]))
        self.assertFalse(chain["data_missing"])
        self.assertTrue(chain["complete"])
        for run in chain["runs"]:
            self.assertEqual([layer["id"] for layer in run["layers"]],
                             ["K%d" % i for i in range(16)])
            for layer in run["layers"]:
                self.assertIn(layer["status"],
                              {"PASS", "FAIL", "SKIP", "MISSING"})
                self.assertTrue(layer["label"])
            counts = run["counts"]
            self.assertEqual(
                counts["pass"] + counts["fail"] + counts["skip"]
                + counts["missing"],
                16,
            )


GATE_RUNS_TSX = os.path.join(VIDEO, "src", "GateChainRuns.tsx")


def _composition_blocks(src):
    """Root.tsx'teki <Composition … /> bloklarını id → alanlar sözlüğüne çevirir."""
    out = {}
    for block in re.findall(r"<Composition([^>]*)/>", src, re.S):
        cid = re.search(r'id="([^"]+)"', block)
        dur = re.search(r"durationInFrames=\{(\d+)\}", block)
        fps = re.search(r"fps=\{(\d+)\}", block)
        w = re.search(r"width=\{(\d+)\}", block)
        h = re.search(r"height=\{(\d+)\}", block)
        if not (cid and dur and fps and w and h):
            continue
        out[cid.group(1)] = {
            "durationInFrames": int(dur.group(1)),
            "fps": int(fps.group(1)),
            "width": int(w.group(1)),
            "height": int(h.group(1)),
        }
    return out


class TestGateChainRunsComposition(unittest.TestCase):
    """İkinci kompozisyon (GateChainRuns) — kare bütçesi ve kaynak sözleşmesi.

    Sözleşmenin üç yüzeyi aynı sayıyı söylemek zorunda: make_data sabitleri,
    Root.tsx kaydı ve check_render'ın kare bütçesi. Sapma → render farklı
    sürede çıkar veya son kare boş kalır.
    """

    def setUp(self):
        self.mod = _load_make_data()

    def test_frame_budget_is_composed_of_intro_runs_outro(self):
        mod = self.mod
        self.assertEqual(
            mod.GATE_HISTORY_INTRO
            + mod.GATE_HISTORY_RUNS * mod.GATE_HISTORY_PER_RUN
            + mod.GATE_HISTORY_OUTRO,
            mod.GATE_HISTORY_FRAMES,
            "intro + runs×per_run + outro = GATE_HISTORY_FRAMES",
        )
        self.assertEqual(mod.GATE_HISTORY_FRAMES, 630)
        self.assertAlmostEqual(mod.GATE_HISTORY_FRAMES / mod.FPS, 21.0, places=6)

    def test_frames_table_is_single_source(self):
        mod = self.mod
        self.assertEqual(
            mod.FRAMES_BY_COMPOSITION,
            {"LeibnizChain": 760, "GateChainRuns": mod.GATE_HISTORY_FRAMES},
        )

    def test_root_registers_both_compositions_with_matching_budgets(self):
        with open(ROOT_TSX, encoding="utf-8") as fh:
            comps = _composition_blocks(fh.read())
        self.assertEqual(sorted(comps), ["GateChainRuns", "LeibnizChain"])
        self.assertEqual(comps["LeibnizChain"]["durationInFrames"],
                         self.mod.FRAMES)
        self.assertEqual(comps["GateChainRuns"]["durationInFrames"],
                         self.mod.GATE_HISTORY_FRAMES)
        for cid, block in comps.items():
            with self.subTest(composition=cid):
                self.assertEqual(block["fps"], self.mod.FPS)
                self.assertEqual((block["width"], block["height"]),
                                 (self.mod.WIDTH, self.mod.HEIGHT))

    def test_composition_consumes_history_block_not_a_copy(self):
        """Sahne veriyi `data.gate_history`'den okur; sayı kopyalamaz."""
        with open(GATE_RUNS_TSX, encoding="utf-8") as fh:
            src = fh.read()
        for token in (
            "data.gate_history",
            "gh.intro_frames",
            "gh.per_run_frames",
            "gh.outro_frames",
            "KAYIT YOK",
            "board_group_state",
        ):
            self.assertIn(token, src, "GateChainRuns.tsx %s kullanmıyor" % token)
        # Kare bütçesi sahneye gömülmez: süre veriden (gh.*_frames) okunur.
        self.assertNotRegex(src, r"durationInFrames=\{\d+\}")
        self.assertNotRegex(src, r"\bconst\s+[A-Z_]*FRAMES[A-Z_]*\s*=\s*\d+")


class TestGateHistoryData(unittest.TestCase):
    """`gate_history` bloğu history.jsonl satırlarından üretilir, uydurulmaz."""

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

    def test_block_shape_and_source(self):
        gh = self.payload["gate_history"]
        self.assertEqual(gh["composition"], "GateChainRuns")
        self.assertEqual(gh["frames"], self.mod.GATE_HISTORY_FRAMES)
        self.assertEqual(gh["source"], os.path.join("_calisma", "CIKTI", "history.jsonl"))
        self.assertEqual(gh["run_capacity"], self.mod.GATE_HISTORY_RUNS)
        self.assertEqual(gh["gate_count"], 16)
        self.assertFalse(gh["data_missing"])
        self.assertEqual(gh["run_count"], len(gh["runs"]))
        self.assertLessEqual(gh["run_count"], self.mod.GATE_HISTORY_RUNS)

    def test_every_run_carries_all_sixteen_gates(self):
        for run in self.payload["gate_history"]["runs"]:
            with self.subTest(run=run["n"]):
                self.assertEqual([g["id"] for g in run["gates"]],
                                 ["K%d" % i for i in range(16)])
                for gate in run["gates"]:
                    self.assertIn(gate["status"],
                                  self.mod.GATE_HISTORY_STATUSES)
                    self.assertIn(gate["from"], {"layers", "board", None})
                    self.assertTrue(gate["label"])
                self.assertEqual(run["reported"] + run["missing"], 16)
                self.assertEqual(
                    run["reported"],
                    sum(1 for g in run["gates"] if g["status"] != "MISSING"),
                )

    def test_missing_gate_is_never_dressed_as_evidence(self):
        """from=None ⟺ MISSING. Kanıtsız bir renk üretilmez."""
        for run in self.payload["gate_history"]["runs"]:
            for gate in run["gates"]:
                if gate["from"] is None:
                    self.assertEqual(gate["status"], "MISSING", gate)
                else:
                    self.assertNotEqual(gate["status"], "MISSING", gate)

    def test_totals_match_run_cells(self):
        gh = self.payload["gate_history"]
        cells = gh["run_count"] * gh["gate_count"]
        self.assertEqual(gh["totals"]["cells"], cells)
        self.assertEqual(
            gh["totals"]["reported"] + gh["totals"]["missing"], cells
        )
        self.assertEqual(
            gh["totals"]["reported"],
            sum(r["reported"] for r in gh["runs"]),
        )

    def test_runs_are_the_last_history_rows(self):
        """Gösterilen koşular history'nin SON N satırı — başka kaynak karışmaz."""
        runs = self.payload["runs"]
        shown = self.payload["gate_history"]["runs"]
        self.assertEqual([r["n"] for r in shown],
                         [r["n"] for r in runs[-self.mod.GATE_HISTORY_RUNS:]])


class TestGateStateResolution(unittest.TestCase):
    """Durum çözümleme kuralları — kaynak yoksa durum da yok."""

    def setUp(self):
        self.mod = _load_make_data()

    def _run(self, **kw):
        base = {
            "n": 1, "ts": "2026-10-01 00:00:00", "day": "2026-10-01",
            "verdict": "FAIL", "exit_code": 1, "duration_s": 1.0,
            "board": "", "layers": None,
        }
        base.update(kw)
        return base

    def _state(self, record, gid):
        return next(g["status"] for g in record["gates"] if g["id"] == gid)

    def test_no_record_means_all_missing(self):
        rec = self.mod.gate_states_for_run(self._run())
        self.assertEqual(rec["reported"], 0)
        self.assertEqual(rec["missing"], 16)
        self.assertTrue(all(g["status"] == "MISSING" for g in rec["gates"]))
        self.assertFalse(rec["layers_reported"])

    def test_board_names_only_the_gate_it_names(self):
        rec = self.mod.gate_states_for_run(
            self._run(board="Pre-commit \u2705 \u00b7 K0 \u2705 \u00b7 K katmanlar\u0131 \u26a0\ufe0f"))
        self.assertEqual(self._state(rec, "K0"), "PASS")
        self.assertEqual(rec["board_group_state"], "WARN")
        # Grup sinyali 15 kapıya dağıtılmaz.
        for gid in ("K1", "K7", "K15"):
            self.assertEqual(self._state(rec, gid), "MISSING")

    def test_board_fail_is_scoped_to_its_gate(self):
        rec = self.mod.gate_states_for_run(self._run(board="K0 \U0001f534"))
        self.assertEqual(self._state(rec, "K0"), "FAIL")
        self.assertEqual(self._state(rec, "K1"), "MISSING")

    def test_layers_map_wins_over_board(self):
        rec = self.mod.gate_states_for_run(
            self._run(board="K1 \u2705", layers={"K1": {"status": "FAIL"}}))
        self.assertEqual(self._state(rec, "K1"), "FAIL")
        self.assertEqual(
            next(g["from"] for g in rec["gates"] if g["id"] == "K1"),
            "layers")

    def test_unknown_layer_status_stays_missing(self):
        """Tanınmayan durum PASS'a yuvarlanmaz; kayıt yok sayılır."""
        rec = self.mod.gate_states_for_run(
            self._run(layers={"K2": {"status": "UNKNOWN"}}))
        self.assertEqual(self._state(rec, "K2"), "MISSING")

    def test_layer_string_form_is_accepted(self):
        rec = self.mod.gate_states_for_run(self._run(layers={"K3": "skip"}))
        self.assertEqual(self._state(rec, "K3"), "SKIP")

    def test_unknown_board_mark_is_not_pass(self):
        rec = self.mod.gate_states_for_run(self._run(board="K0 ?"))
        self.assertEqual(self._state(rec, "K0"), "MISSING")

    def test_outside_gates_are_reported_not_dropped(self):
        """K16+ kayıtları silinmez: zincir 16 kutu çizer ama FAIL orada olabilir.

        Silinselerdi K16'da kalan bir koşu "16/16 temiz" görünürdü.
        """
        rec = self.mod.gate_states_for_run(self._run(layers={
            "K0": {"status": "PASS"},
            "K16": {"status": "FAIL"},
            "K21": {"status": "PASS"},
        }))
        self.assertEqual(rec["outside"],
                         [{"id": "K16", "status": "FAIL"},
                          {"id": "K21", "status": "PASS"}])
        self.assertEqual(self._state(rec, "K0"), "PASS")
        self.assertEqual(rec["reported"], 1, "kapsam dışı kapı 16'lık sayaca girmez")

    def test_non_gate_keys_stay_out_of_outside(self):
        rec = self.mod.gate_states_for_run(self._run(layers={
            "UNREGISTERED": {"status": "FAIL"},
            "junk": {"status": "FAIL"},
        }))
        self.assertEqual(rec["outside"], [])

    def test_break_selection_skips_unevidenced_newest(self):
        """Sinyalle kesilen #3 rapor üretmedi: animasyon #2'yi çizer, #3'ü adlandırır."""
        states = {
            1: {"n": 1, "reported": 0},
            2: {"n": 2, "reported": 16},
            3: {"n": 3, "reported": 0},
        }
        latest, newest = self.mod.select_break_latest(
            [{"n": 1}, {"n": 2}, {"n": 3}], states)
        self.assertEqual(latest["n"], 2)
        self.assertEqual(newest["n"], 3)

    def test_break_selection_falls_back_when_nothing_has_evidence(self):
        states = {1: {"n": 1, "reported": 0}, 2: {"n": 2, "reported": 0}}
        latest, newest = self.mod.select_break_latest(
            [{"n": 1}, {"n": 2}], states)
        self.assertEqual(latest["n"], 2)
        self.assertEqual(newest["n"], 2)
        self.assertIsNone(self.mod.select_break_latest([], {})[0])

    def test_history_layers_keeps_real_gate_ids(self):
        got = self.mod._history_layers({"layers": {
            "K0": "PASS", "K16": {"status": "fail"}, "nope": "PASS",
        }})
        self.assertEqual(got, {"K0": "PASS", "K16": "FAIL"})

    def test_sentinel_has_no_invented_gate_history(self):
        mod = self.mod
        saved = (mod.HISTORY, mod.KLayers_RUNS, mod.KLayers)
        mod.HISTORY = os.path.join(HERE, "yok-boyle-bir-dosya.jsonl")
        mod.KLayers_RUNS = os.path.join(HERE, "yok-boyle-bir-klayers-runs.json")
        mod.KLayers = os.path.join(HERE, "yok-boyle-bir-klayers.json")
        self.addCleanup(lambda: setattr(mod, "HISTORY", saved[0]))
        self.addCleanup(lambda: setattr(mod, "KLayers_RUNS", saved[1]))
        self.addCleanup(lambda: setattr(mod, "KLayers", saved[2]))
        payload = mod.build(allow_missing=True)
        gh = payload["gate_history"]
        self.assertEqual(gh["runs"], [])
        self.assertTrue(gh["data_missing"])
        self.assertEqual(gh["totals"]["cells"], 0)
        self.assertEqual(gh["frames"], mod.GATE_HISTORY_FRAMES)


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
        # Her tahta kalemi ya bir kapı NUMARASIDIR ya da grup sinyalidir.
        # `ok_ids` yalnız PASS olan kapıları taşır; K0 FAIL ise (`K0 🔴`)
        # listede görünmez ama yine de kapıdır — bu yüzden birleşim kapı
        # kimlikleri üzerinden sınanır, ok_ids üzerinden değil (eski hâli
        # FAIL işaretini tanımadığı için bunu örtüyordu).
        gate_named = [i["label"] for i in gates["board"] if i["label"] in gates["names"]]
        group_named = [i["label"] for i in gates["board"] if i["label"] not in gates["names"]]
        self.assertEqual(sorted(gate_named + group_named),
                         sorted(i["label"] for i in gates["board"]))
        self.assertEqual(sorted(gates["group_warn"]), sorted(group_named))

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

    def test_break_latest_is_newest_run_with_gate_evidence(self):
        """Kırılma animasyonu kanıtlı koşuyu çizer; kayıt uydurulmaz."""
        runs = self.payload["runs"]
        bk = self.payload["gates"]["break"]
        nonzero = [r for r in runs if r["exit_code"] not in (None, 0)]
        if not nonzero:
            self.assertIsNone(bk["latest"])
            self.assertIsNone(bk["newest"])
            return
        expected_newest = nonzero[-1]
        self.assertEqual(bk["newest"]["n"], expected_newest["n"])
        with_gates = [r for r in nonzero
                      if self.mod.gate_states_for_run(r)["reported"] > 0]
        expected = with_gates[-1] if with_gates else expected_newest
        record = self.mod.gate_states_for_run(expected)
        latest = bk["latest"]
        self.assertEqual(latest["n"], expected["n"])
        self.assertEqual(latest["reported"], record["reported"])
        self.assertEqual(latest["failed"],
                         [g["id"] for g in record["gates"] if g["status"] == "FAIL"])
        self.assertEqual(latest["outside_failed"],
                         [g["id"] for g in record["outside"]
                          if g["status"] == "FAIL"])
        self.assertEqual(bk["latest_is_newest"], latest["n"] == bk["newest"]["n"])

    def test_break_outside_failed_comes_from_row_layers(self):
        """Kapsam dışı FAIL listesi satırın kendi `layers` kaydından türer.

        Beklenti HAM arşiv satırından okunur (payload değil): aksi hâlde
        `_history_layers` K16+'yı düşürseydi beklenti de boşalır ve test
        kendi kendini doğrular (boş assertion tuzağı).
        """
        latest = self.payload["gates"]["break"]["latest"]
        if not latest or not latest["layers_reported"]:
            self.skipTest("kanıtlı kırılma koşusu yok")
        with open(self.mod.HISTORY, encoding="utf-8") as fh:
            raw_rows = [json.loads(ln) for ln in fh if ln.strip()]
        raw = raw_rows[latest["n"] - 1]
        layers = raw.get("layers") or {}
        expected = sorted(gid for gid, value in layers.items()
                          if self.mod._is_gate_id(gid)
                          and gid not in self.mod.GATES_ALL
                          and self.mod._layer_status(value) == "FAIL")
        self.assertEqual(sorted(latest["outside_failed"]), expected)

    def test_scene_names_outside_failures_and_newest_break(self):
        """Sahne, kapsam dışı FAIL'i ve en yeni kırılmayı gizleyemez."""
        scene = open(os.path.join(VIDEO, "src", "scenes.tsx"), encoding="utf-8").read()
        self.assertIn("outside_failed", scene)
        self.assertIn("latest_is_newest", scene)
        self.assertIn("kapsam dışı", scene)

    def test_timeline_windows_run_rows_so_footer_stays_in_frame(self):
        """100 koşu satırı 720 px'i aşar: alt blok (KIRILMA) kare dışına taşmıştı.

        Ölçüldü: slice olmadan 100 satır × ~31 px ≈ 3100 px; gizli satırlar da
        yer kapladığı için VERDICT/ÇIKIŞ barları ve KIRILMA animasyonu hiç
        görünmüyordu. Sahne son `TIMELINE_RUNS` koşuyu çizmek ZORUNDA.
        """
        scene = open(os.path.join(VIDEO, "src", "scenes.tsx"), encoding="utf-8").read()
        self.assertIn("data.runs.slice(-TIMELINE_RUNS)", scene)
        self.assertIsNone(re.search(r"\{data\.runs\.map\(", scene),
                          "satır listesi pencerelenmeden çizilmemeli")
        self.assertIn("son ${shownRuns.length} koşu", scene)

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
        # Koşu başına dolu sütun sayısı SABİT DEĞİLDİR ve olmamalıdır:
        # ölçüldü — sinyalle kesilen koşu 3 sütun (yalnız z3 ailesi),
        # tamamlanan PASS koşusu 9 sütun raporluyor. Eski sürüm burada
        # "sabit" diyordu ve o anki 7 BENZER koşuya aşırı uydurulmuştu;
        # history.jsonl'e yeni bir koşu düşünce kapı patladı.
        self.assertLessEqual(0, tel["min_per_run"])
        self.assertLessEqual(tel["min_per_run"], tel["max_per_run"])
        self.assertLessEqual(tel["max_per_run"], tel["columns"])

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
            "data.gate_chain.runs",
            "gate_chain.data_missing",
            "gateTag",
            "KAPI DURUMU",
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
        saved_runs = mod.KLayers_RUNS
        saved_gate = mod.KLayers
        mod.HISTORY = os.path.join(HERE, "yok-boyle-bir-dosya.jsonl")
        mod.KLayers_RUNS = os.path.join(HERE, "yok-boyle-bir-klayers-runs.json")
        mod.KLayers = os.path.join(HERE, "yok-boyle-bir-klayers.json")
        self.addCleanup(setattr, mod, "HISTORY", saved)
        self.addCleanup(setattr, mod, "KLayers_RUNS", saved_runs)
        self.addCleanup(setattr, mod, "KLayers", saved_gate)

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
        self.assertEqual(payload["gate_chain"]["runs"], [])
        self.assertTrue(payload["gate_chain"]["data_missing"])
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


class TestRenderWorkflowContract(unittest.TestCase):
    """video-render işi her commit'te koşmalı ve PR özeti üretmeli.

    Bu testler workflow'un niyetini metin düzeyinde pin'ler: path filtresi
    geri eklenirse, PR yorum adımı düşerse veya sha256 raporu kaybolursa
    kapı kırmızıya döner. Davranışın kendisi `render_report.json` + harness
    ile ayrıca ölçülür.
    """

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as fh:
            cls.workflow = fh.read()
        with open(COMMENT_JS, encoding="utf-8") as fh:
            cls.comment_js = fh.read()

    def test_triggers_every_commit_without_path_filter(self):
        on_block = self.workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("push: {}", on_block)
        self.assertIn("pull_request: {}", on_block)
        self.assertNotIn("paths:", on_block, "path filtresi her commit kuralını bozar")
        # Grup SHA içermezse ardışık commit koşuları birbirini iptal eder.
        self.assertIn(
            "group: video-render-${{ github.ref }}-${{ github.sha }}", self.workflow
        )

    def test_pr_comment_has_write_permission_and_render_outcome(self):
        self.assertIn("pull-requests: write", self.workflow)
        self.assertIn("id: render", self.workflow)
        self.assertIn("RENDER_OUTCOME: ${{ steps.render.outcome }}", self.workflow)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", self.workflow)
        self.assertIn("video_render_comment.js", self.workflow)

    def test_render_elapsed_and_sha_flow_into_artifact(self):
        self.assertIn("render_elapsed_s.txt", self.workflow)
        with open(os.path.join(VIDEO, "check_render.py"), encoding="utf-8") as fh:
            checker = fh.read()
        self.assertIn('track["sha256"] = hashlib.sha256(buf).hexdigest()', checker)

    def test_player_job_builds_and_probes_routes_fail_closed(self):
        """Tarayıcı paketi + /video/* rota kapısı her push'ta koşmalı.

        `dist/` gitignore'da: paket üretilmezse /video.html 404 döner ve kapı
        sessizce "yeşil ama ürün yok" olabilir. Sıra sözleşmesi build →
        prob; `continue-on-error` ise "kırmızı ama yeşil" üretir, bu yüzden
        prob adımında YOKLUĞU pinlenir.
        """
        self.assertIn("\n  player:\n", self.workflow)
        block = self.workflow.split("\n  player:\n", 1)[1]
        self.assertIn("npm ci --prefix _calisma/video", block)
        self.assertIn("npm run build:player:ci --prefix _calisma/video", block)
        self.assertLess(block.index("build:player:ci"),
                        block.index("check_player_routes.py"),
                        "build:player:ci rota probundan önce koşmalı")
        # history.jsonl gitignore'da olduğu için strict `build:player` temiz
        # klonda exit 1 verir; CI yalnız `--allow-missing-data` varyantını
        # kullanabilir.
        self.assertNotIn("npm run build:player --prefix", block)
        self.assertIn("--json-out player_routes.json", block)
        self.assertIn("GITHUB_STEP_SUMMARY", block)
        step = block.split("- name: Verify package + /video/* routes", 1)[1]
        self.assertNotIn("continue-on-error", step,
                         "rota probu advisory olamaz (fail-closed)")

    def test_comment_script_upserts_marker_and_never_invents_metrics(self):
        self.assertIn("<!-- leibniz-chain-video-render -->", self.comment_js)
        self.assertIn("render_report.json", self.comment_js)
        self.assertIn("sha256", self.comment_js)
        self.assertIn("issues.listComments", self.comment_js)
        self.assertIn("issues.updateComment", self.comment_js)
        self.assertIn("issues.createComment", self.comment_js)
        self.assertIn("ölçülemedi", self.comment_js)
        self.assertIn("EXPECTED_FRAMES = 760", self.comment_js)
        self.assertIn("SHA-256 raporu eksik/geçersiz", self.comment_js)


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
