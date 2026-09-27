#!/usr/bin/env python3
"""build_landing.py snapshot/derleme sözleşmesi için stdlib testleri."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "build_landing", HERE / "build_landing.py")
assert SPEC and SPEC.loader
build_landing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_landing)

RAW_SHA = "a" * 64
STRIPPED_SHA = "b" * 64


def snapshot(**overrides):
    value = {
        "ts": "2026-09-25T12:00:00Z",
        "verdict": "PASS",
        "exit_code": 0,
        "p0": 0,
        "p1": 0,
        "raw_sha256": RAW_SHA,
        "stripped_sha256": STRIPPED_SHA,
        "cached": False,
    }
    value.update(overrides)
    return value


class SnapshotValidationTests(unittest.TestCase):
    def test_valid_raw_snapshot_returns_hash(self):
        self.assertEqual(
            build_landing.validate_snapshot(snapshot()), RAW_SHA)

    def test_nested_hash_must_agree_with_top_level(self):
        value = snapshot(pdf_hash={"raw": "c" * 64})
        with self.assertRaisesRegex(
                build_landing.SnapshotInvalid, "çelişkili"):
            build_landing.validate_snapshot(value)

    def test_stripped_field_is_explicit(self):
        self.assertEqual(
            build_landing.validate_snapshot(
                snapshot(), hash_field="stripped"),
            STRIPPED_SHA,
        )

    def test_unfinished_and_cached_snapshots_are_unavailable(self):
        for value in (
                snapshot(verdict="RUNNING", exit_code=None),
                snapshot(cached=True)):
            with self.subTest(value=value):
                with self.assertRaises(build_landing.SnapshotUnavailable):
                    build_landing.validate_snapshot(value)

    def test_failures_are_invalid(self):
        cases = (
            snapshot(verdict="FAIL"),
            snapshot(exit_code=1),
            snapshot(p0=1),
            snapshot(p1=1),
            snapshot(ts=""),
            snapshot(raw_sha256="not-a-sha"),
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(build_landing.SnapshotInvalid):
                    build_landing.validate_snapshot(value)

    def test_jsonl_uses_last_record_and_rejects_corrupt_line(self):
        with tempfile.TemporaryDirectory(prefix="landing-snapshot-") as work:
            path = pathlib.Path(work) / "history.jsonl"
            path.write_text(
                json.dumps(snapshot(raw_sha256="c" * 64)) + "\n" +
                json.dumps(snapshot()) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                build_landing.load_snapshot(str(path))["raw_sha256"],
                RAW_SHA,
            )
            path.write_text(
                json.dumps(snapshot()) + "\nnot-json\n", encoding="utf-8")
            with self.assertRaisesRegex(
                    build_landing.SnapshotInvalid, "JSONL satırı"):
                build_landing.load_snapshot(str(path))


class BuildPageTests(unittest.TestCase):
    def test_build_rejects_unvalidated_hash(self):
        with tempfile.TemporaryDirectory(prefix="landing-build-") as work:
            root = pathlib.Path(work)
            with self.assertRaisesRegex(
                    build_landing.SnapshotInvalid, "doğrulanmamış"):
                build_landing.build_page(
                    snapshot(), "A" * 64, output=root / "landing.html",
                    assets_dir=root / "assets")

    def test_build_embeds_selected_hash_and_stages_assets(self):
        with tempfile.TemporaryDirectory(prefix="landing-build-") as work:
            root = pathlib.Path(work)
            output = root / "landing.html"
            assets = root / "assets"
            build_landing.build_page(
                snapshot(), RAW_SHA, output=output, assets_dir=assets)
            html = output.read_text(encoding="utf-8")
            self.assertIn("VERIFIED • %s •" % RAW_SHA[:12].upper(), html)
            self.assertIn(RAW_SHA[:6].upper() + "…", html)
            self.assertNotIn("{{SEAL_", html)
            self.assertNotIn("../../CIKTI/slides_z3", html)
            for plate in build_landing.PLATES:
                self.assertTrue((assets / plate).is_file())


class ThemeVariantTests(unittest.TestCase):
    """--theme (dark|light|stripe): varsayılan dark dokunulmaz; stripe HDS
    varyantını gömer ve <html data-theme> yazar (JS'siz tema)."""

    def _build(self, theme):
        work = tempfile.mkdtemp(prefix="landing-theme-")
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        root = pathlib.Path(work)
        output = root / "landing.html"
        build_landing.build_page(snapshot(), RAW_SHA, output=output,
                                 assets_dir=root / "assets", theme=theme)
        return output.read_text(encoding="utf-8")

    def test_default_theme_stays_attribute_free(self):
        html = self._build("dark")
        self.assertIn('<html lang="tr">', html)
        self.assertNotIn('<html lang="tr" data-theme', html)
        self.assertNotIn("--hds-color-core-brand-600", html)

    def test_stripe_theme_embeds_variant_and_sets_attribute(self):
        html = self._build("stripe")
        self.assertIn('<html lang="tr" data-theme="stripe">', html)
        self.assertIn(':root[data-theme="stripe"]', html)
        self.assertIn("--hds-color-core-brand-600: #533afd;", html)
        self.assertIn("--accent: var(--hds-color-action-bg-solid);", html)
        self.assertNotIn("{{SEAL_", html)

    def test_light_theme_sets_attribute_without_variant(self):
        html = self._build("light")
        self.assertIn('<html lang="tr" data-theme="light">', html)
        self.assertNotIn("--hds-color-core-brand-600", html)

    def test_unknown_theme_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="landing-theme-") as work:
            root = pathlib.Path(work)
            with self.assertRaisesRegex(build_landing.SnapshotInvalid,
                                        "bilinmeyen tema"):
                build_landing.build_page(
                    snapshot(), RAW_SHA, output=root / "landing.html",
                    assets_dir=root / "assets", theme="neon")


class CliTests(unittest.TestCase):
    def _write_snapshot(self, root, value):
        path = root / "snapshot.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _run_main(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            rc = build_landing.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_hash_sidecar_format_is_standard_sha256(self):
        # Run-history artifact sidecar sözleşmesi: sha256sum çıktısı.
        with tempfile.TemporaryDirectory(prefix="landing-sidecar-") as work:
            path = pathlib.Path(work) / "history.jsonl"
            content = (json.dumps(snapshot()) + "\n").encode("utf-8")
            path.write_bytes(content)
            sidecar = subprocess.check_output(
                ["sha256sum", str(path)], text=True).split()[0]
            path.with_name(path.name + ".sha256").write_text(
                sidecar + "  history.jsonl\n", encoding="utf-8")
            self.assertEqual(
                build_landing._decode_snapshot(
                    path.read_text(encoding="utf-8"), str(path)),
                snapshot(),
            )

    def test_valid_file_build_does_not_touch_frozen_record(self):
        with tempfile.TemporaryDirectory(prefix="landing-cli-") as work:
            root = pathlib.Path(work)
            snap = self._write_snapshot(root, snapshot())
            output = root / "out" / "landing.html"
            assets = root / "out" / "assets"
            rc, out, err = self._run_main([
                "--snapshot-file", str(snap),
                "--output", str(output),
                "--assets-dir", str(assets),
            ])
            self.assertEqual(rc, 0, err)
            self.assertIn("mühür %s" % RAW_SHA[:12], out)
            self.assertTrue(output.is_file())
            source = pathlib.Path(build_landing.__file__).read_text(
                encoding="utf-8")
            self.assertNotIn("DETERMINISM_RECORD", source)
            self.assertNotIn("qpdf_determinism_output.txt", source)

    def test_invalid_snapshot_does_not_write_output(self):
        with tempfile.TemporaryDirectory(prefix="landing-cli-") as work:
            root = pathlib.Path(work)
            snap = self._write_snapshot(root, snapshot(verdict="FAIL"))
            output = root / "landing.html"
            rc, _out, err = self._run_main([
                "--snapshot-file", str(snap),
                "--output", str(output),
                "--assets-dir", str(root / "assets"),
            ])
            self.assertEqual(rc, 1)
            self.assertIn("BUILD FAIL", err)
            self.assertFalse(output.exists())

    def test_environment_sources_are_mutually_exclusive(self):
        old_url = os.environ.get("PREVIEW_SNAPSHOT_URL")
        old_file = os.environ.get("PREVIEW_SNAPSHOT_FILE")
        os.environ["PREVIEW_SNAPSHOT_URL"] = "http://127.0.0.1:8000/api/latest"
        os.environ["PREVIEW_SNAPSHOT_FILE"] = "history.jsonl"
        try:
            rc, _out, err = self._run_main([])
        finally:
            if old_url is None:
                os.environ.pop("PREVIEW_SNAPSHOT_URL", None)
            else:
                os.environ["PREVIEW_SNAPSHOT_URL"] = old_url
            if old_file is None:
                os.environ.pop("PREVIEW_SNAPSHOT_FILE", None)
            else:
                os.environ["PREVIEW_SNAPSHOT_FILE"] = old_file
        self.assertEqual(rc, 1)
        self.assertIn("birlikte verilemez", err)


if __name__ == "__main__":
    unittest.main()
