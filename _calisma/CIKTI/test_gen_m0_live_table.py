#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gen_m0_live_table as generator


class TestM0LiveTable(unittest.TestCase):
    def test_render_contains_only_three_requested_layers(self):
        table = generator.render([
            ("K14", "Cleanup", "PASS"),
            ("K16", "Scripts", "PASS"),
            ("K17", "Mirror", "FAIL (exit 1)"),
        ])
        self.assertIn("M0-LIVE-TABLE:START", table)
        self.assertIn("| K17 | Mirror | FAIL (exit 1) |", table)
        self.assertEqual(sum(1 for line in table.splitlines()
                             if line.startswith("| K") and not line.startswith("| Katman")), 3)

    def test_concise_detail_uses_last_layer_line(self):
        output = "[K17] old\n[K17] mirror sync: PASS (exit=0)"
        self.assertEqual(
            generator.concise_detail(output, "K17"),
            "[K17] mirror sync: PASS (exit=0)",
        )

    def test_missing_summary_is_explicit(self):
        self.assertEqual(generator.concise_detail("noise", "K14"),
                         "çıktı özeti bulunamadı")

    def test_update_report_replaces_only_marked_block(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "M0.md"
            report.write_text(
                "before\n" + generator.START + "\nold\n" + generator.END
                + "\nafter\n", encoding="utf-8")
            generator.update_report(report, generator.render([
                ("K14", "Cleanup", "PASS"),
                ("K16", "Scripts", "PASS"),
                ("K17", "Mirror", "PASS"),
            ]))
            text = report.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("before\n"))
            self.assertTrue(text.endswith("after\n"))
            self.assertNotIn("old", text)
            self.assertIn("| K17 | Mirror | PASS |", text)

    def test_update_report_requires_markers(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "M0.md"
            report.write_text("no marker\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                generator.update_report(report, "table")

    @mock.patch.object(generator, "run_gate")
    def test_main_propagates_nonzero_gate(self, run_gate):
        run_gate.side_effect = [
            (0, "[K14] PASS"),
            (0, "[K16] PASS"),
            (1, "[K17] FAIL"),
        ]
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "M0.md"
            report.write_text(generator.START + "\nold\n" + generator.END,
                              encoding="utf-8")
            rc = generator.main(["--verify", str(Path(td) / "verify_delivery.py"),
                                 "--root", td, "--report", str(report)])
            self.assertEqual(rc, 1)
            self.assertIn("FAIL (exit 1)", report.read_text(encoding="utf-8"))
            self.assertEqual(run_gate.call_count, 3)


if __name__ == "__main__":
    unittest.main()
