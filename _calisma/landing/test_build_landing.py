#!/usr/bin/env python3
"""build_landing.py mühür kaynağı/derleme sözleşmesi için stdlib testleri.

Mühür kaynağı DONMUŞ KAYITTIR (committed PDF'in yanındaki
`<pdf>.metadata.sha256` sidecar'ının `# raw:` satırı): build koşum anına değil
repoya bağlıdır. Canlı snapshot yolu açıkça istenirse (`--snapshot-file` /
`--snapshot-url` / env) korunur — bu yüzden iki kaynak da test edilir.
"""
import contextlib
import hashlib
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

# build_landing import'u _calisma/CIKTI'yi sys.path'e koyar; donmuş kayıt
# sözleşmesinin tek kaynağı olan modülü testler de onun üstünden doğrular.
import check_seal_hash as seal_record  # noqa: E402

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

    def test_raw_only_snapshot_rejected_by_module_shape_layer(self):
        """Katman 1 (modül) tek-kaynak katılığı: stripped'sız kayıt geçemez.

        Eski landing-içi doğrulama seçili alanı yalnız başına kabul ederdi;
        preview_server modül sözleşmesi iki hash'i de ister. Bu test delegeyi
        sabitler — Katman 1 gevşetilirse kırmızıya düşer.
        """
        value = snapshot()
        del value["stripped_sha256"]
        with self.assertRaises(build_landing.SnapshotInvalid):
            build_landing.validate_snapshot(value)

    def test_incomplete_states_stay_unavailable_for_wait_loop(self):
        """Katman 2 istisna cinsi: bekleme döngüsü Unavailable'a bağlıdır.

        UNKNOWN/INIT/verdictsiz/cached kayıtlar Invalid DEĞİL Unavailable
        olmalı; yoksa resolve_snapshot beklemez, build erken düşer.
        """
        for value in (
                snapshot(verdict="UNKNOWN", exit_code=None),
                snapshot(verdict="INIT", exit_code=0),
                snapshot(verdict=None, exit_code=None),
                snapshot(cached=True)):
            with self.subTest(value=value):
                with self.assertRaises(build_landing.SnapshotUnavailable):
                    build_landing.validate_snapshot(value)

    def test_module_shape_errors_surface_as_snapshot_invalid(self):
        """Modül şekil hataları SnapshotInvalid'e çevrilir (ValueError sızmaz).

        p0 denetimi modül sözcükleriyle ("sıfır değil") gelir — paralel
        kural yazılmadığının kanıtı.
        """
        with self.assertRaisesRegex(
                build_landing.SnapshotInvalid, "sıfır değil"):
            build_landing.validate_snapshot(snapshot(p0=2))

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


class ProvenanceTests(unittest.TestCase):
    def _build(self, root):
        output = root / "landing.html"
        assets = root / "assets"
        sha = build_landing.build_page(
            snapshot(), RAW_SHA, output=output, assets_dir=assets)
        return output, sha

    def test_provenance_carries_seal_hash(self):
        """Provenance mühürle AYNI snapshot hash'ini taşır (kalıcı artifact)."""
        with tempfile.TemporaryDirectory(prefix="landing-prov-") as work:
            root = pathlib.Path(work)
            output, sha = self._build(root)
            prov_path = root / "landing.provenance.json"
            self.assertTrue(prov_path.is_file())
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            # Provenance kanonik (küçük harf) formu taşır; build_page'in
            # döndürdüğü sha mühürdeki büyük-harflı gösterimdir — aynı hash.
            self.assertEqual(prov["snapshot_hash"], RAW_SHA)
            self.assertEqual(prov["snapshot_hash"].upper(), sha)
            html = output.read_text(encoding="utf-8")
            self.assertIn("VERIFIED • %s •" % sha[:12].upper(), html)

    def test_provenance_bytes_deterministic_across_builds(self):
        """Aynı girdiler → bayt-özdeş provenance (duvar saati/yol yok)."""
        with tempfile.TemporaryDirectory(prefix="landing-prov-a-") as wa, \
                tempfile.TemporaryDirectory(prefix="landing-prov-b-") as wb:
            self._build(pathlib.Path(wa))
            self._build(pathlib.Path(wb))
            pa = (pathlib.Path(wa) / "landing.provenance.json"
                  ).read_bytes()
            pb = (pathlib.Path(wb) / "landing.provenance.json"
                  ).read_bytes()
            self.assertEqual(pa, pb)


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

    def test_snapshot_file_build_does_not_read_frozen_record(self):
        """Açık snapshot kaynağı donmuş kayda hiç bakmaz.

        Varsayılan mühür kaynağı artık donmuş kayıttır; bu test snapshot
        yolunun ondan bağımsız olduğunu kanıtlar: varsayılan PDF kasten
        olmayan bir yola çevrilir, snapshot derlemesi yine geçer.
        """
        with tempfile.TemporaryDirectory(prefix="landing-cli-") as work:
            root = pathlib.Path(work)
            snap = self._write_snapshot(root, snapshot())
            output = root / "out" / "landing.html"
            assets = root / "out" / "assets"
            original = build_landing.DEFAULT_PDF
            build_landing.DEFAULT_PDF = root / "olmayan-committed.pdf"
            try:
                rc, out, err = self._run_main([
                    "--snapshot-file", str(snap),
                    "--output", str(output),
                    "--assets-dir", str(assets),
                ])
            finally:
                build_landing.DEFAULT_PDF = original
            self.assertEqual(rc, 0, err)
            self.assertIn("mühür %s" % RAW_SHA[:12], out)
            self.assertIn("snapshot", out)
            self.assertTrue(output.is_file())

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


def _frozen_fixture(root, recorded=None, signed_name=None, pdf=True,
                    sidecar=True):
    """Geçici kökte committed PDF + donmuş kayıt (sidecar) üretir.

    `recorded` verilmezse kayıt PDF'in GERÇEK sha256'sını taşır (tutarlı
    kayıt); verilirse kayıt kasten bayat olur. `signed_name` başka bir
    dosyayı imzalayan kayıt senaryosudur. Dönen: (pdf, sidecar, raw).
    """
    pdf_path = root / "commitli.pdf"
    if pdf:
        pdf_path.write_bytes(b"%PDF-1.4 landing frozen fixture\n%%EOF\n")
    name = signed_name or pdf_path.name
    raw = recorded
    if raw is None:
        raw = (hashlib.sha256(pdf_path.read_bytes()).hexdigest()
               if pdf else "0" * 64)
    sidecar_path = pdf_path.with_name(pdf_path.name + ".metadata.sha256")
    if sidecar:
        sidecar_path.write_text(
            "%s  %s.metadata\n# raw: %s  %s\n" % ("a" * 64, name, raw, name),
            encoding="utf-8")
    return pdf_path, sidecar_path, raw


class FrozenRecordTests(unittest.TestCase):
    """Mühür kaynağı koşum anı değil REPO: donmuş kayıt (`# raw:` satırı).

    Bu sınıf sözleşmeyi tersine çeviren davranışı sabitler: build mühür
    hash'ini sidecar'dan alır, committed PDF'in baytlarıyla çapraz doğrular
    ve iki kaynak ayrışırsa mühür HİÇ basılmaz (fail-closed).
    """

    def setUp(self):
        self.work = pathlib.Path(
            tempfile.mkdtemp(prefix="landing-frozen-"))
        self.addCleanup(shutil.rmtree, str(self.work), True)

    def _run(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            rc = build_landing.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def _fixture(self, **kwargs):
        root = pathlib.Path(tempfile.mkdtemp(
            prefix="landing-frozen-repo-", dir=str(self.work)))
        pdf, sidecar, raw = _frozen_fixture(root, **kwargs)
        return sidecar, raw

    def _build(self, sidecar, snapshot_file=None, extra=()):
        """Derlemeyi gerçek CLI'yle koşar.

        `snapshot_file` verilirse kaynak açıkça snapshot'a çevrilir; ikisi
        birlikte verilemez (CLI fail-closed: `--frozen-record` ile
        `--snapshot-file` çelişir).
        """
        out_root = self.work / "out"
        output = out_root / "landing.html"
        argv = []
        if snapshot_file is None:
            argv += ["--frozen-record", str(sidecar)]
        else:
            argv += ["--snapshot-file", str(snapshot_file)]
        argv += ["--output", str(output),
                 "--assets-dir", str(out_root / "assets")]
        argv += list(extra)
        rc, out, err = self._run(argv)
        return rc, out, err, output

    def _provenance(self, output):
        path = output.parent / (output.stem + ".provenance.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_frozen_record_drives_the_seal(self):
        sidecar, raw = self._fixture()
        rc, out, err, output = self._build(sidecar)
        self.assertEqual(rc, 0, err)
        self.assertIn("mühür %s" % raw[:12], out)
        self.assertIn("frozen-record", out)
        html = output.read_text(encoding="utf-8")
        self.assertIn("VERIFIED • %s •" % raw[:12].upper(), html)
        prov = self._provenance(output)
        self.assertEqual(prov["seal_source"], "frozen-record")
        self.assertEqual(prov["frozen_record_name"], "commitli.pdf")
        self.assertEqual(prov["snapshot_hash"], raw)
        self.assertIsNone(prov["snapshot_ts"])
        self.assertIsNone(prov["snapshot_verdict"])

    def test_default_record_path_is_the_committed_sidecar(self):
        """Argümansız varsayılan, repodaki donmuş kayda çözülür."""
        self.assertEqual(
            build_landing.DEFAULT_PDF,
            build_landing.ROOT / seal_record.PDF_REL)
        default_record = build_landing.frozen_record_path_for(
            build_landing.DEFAULT_PDF)
        self.assertTrue(default_record.is_file(),
                        "committed donmuş kayıt yok: %s" % default_record)
        raw, name = build_landing.load_frozen_seal(default_record)
        self.assertEqual(name, build_landing.DEFAULT_PDF.name)
        self.assertEqual(raw,
                         seal_record.sha256_file(build_landing.DEFAULT_PDF))

    def test_missing_record_fails_closed(self):
        sidecar, _raw = self._fixture(sidecar=False)
        rc, _out, err, output = self._build(sidecar)
        self.assertEqual(rc, 1)
        self.assertIn("donmuş kayıt yok", err)
        self.assertFalse(output.exists())

    def test_malformed_record_fails_closed(self):
        sidecar, _raw = self._fixture()
        sidecar.write_text("sadece serbest metin\n", encoding="utf-8")
        rc, _out, err, output = self._build(sidecar)
        self.assertEqual(rc, 1)
        self.assertIn("`# raw:", err)
        self.assertIn("satırı yok", err)
        self.assertFalse(output.exists())

    def test_record_signing_another_file_fails_closed(self):
        sidecar, _raw = self._fixture(signed_name="baska.pdf")
        rc, _out, err, output = self._build(sidecar)
        self.assertEqual(rc, 1)
        self.assertIn("imzaladığı PDF yok", err)
        self.assertFalse(output.exists())

    def test_stale_record_fails_closed(self):
        """Kayıt bayatladıysa (hash ≠ committed PDF baytları) mühür basılmaz."""
        sidecar, raw = self._fixture(recorded="b" * 64)
        rc, _out, err, output = self._build(sidecar)
        self.assertEqual(rc, 1)
        self.assertIn("ayrışıyor", err)
        self.assertIn(raw, err)
        self.assertFalse(output.exists())

    def test_missing_pdf_fails_closed(self):
        sidecar, _raw = self._fixture(pdf=False)
        rc, _out, err, output = self._build(sidecar)
        self.assertEqual(rc, 1)
        self.assertIn("imzaladığı PDF yok", err)
        self.assertFalse(output.exists())

    def test_stripped_hash_field_is_snapshot_only(self):
        sidecar, _raw = self._fixture()
        rc, _out, err, output = self._build(sidecar,
                                            extra=("--hash-field", "stripped"))
        self.assertEqual(rc, 1)
        self.assertIn("yalnız raw hash", err)
        self.assertFalse(output.exists())

    def test_qpdf_experiment_record_is_not_an_input(self):
        """qpdf determinizm DENEY kaydı mühür girdisi değildir.

        Aynı dizine yanıltıcı bir `qpdf_determinism_output.txt` konur: mühür
        yine sidecar'ın `# raw:` satırından gelmelidir.
        """
        sidecar, raw = self._fixture()
        decoy = sidecar.parent / "qpdf_determinism_output.txt"
        decoy.write_text("raw: %s\n" % ("c" * 64), encoding="utf-8")
        rc, out, err, output = self._build(sidecar)
        self.assertEqual(rc, 0, err)
        self.assertIn("mühür %s" % raw[:12], out)
        html = output.read_text(encoding="utf-8")
        self.assertIn("VERIFIED • %s •" % raw[:12].upper(), html)
        self.assertNotIn("c" * 12, html)

    def test_snapshot_source_remains_an_explicit_opt_in(self):
        sidecar, _raw = self._fixture(sidecar=False)
        snap = sidecar.parent / "snapshot.json"
        snap.write_text(json.dumps(snapshot(raw_sha256="d" * 64)),
                        encoding="utf-8")
        rc, out, err, output = self._build(sidecar, snapshot_file=snap)
        self.assertEqual(rc, 0, err)
        self.assertIn("mühür %s" % ("d" * 12), out)
        prov = self._provenance(output)
        self.assertEqual(prov["seal_source"], "snapshot")
        self.assertIsNone(prov["frozen_record_name"])
        self.assertEqual(prov["snapshot_verdict"], "PASS")

    def test_frozen_and_snapshot_sources_agree_on_html_bytes(self):
        """Aynı hash iki kaynaktan da aynı HTML'i üretir (mühür = hash)."""
        sidecar, raw = self._fixture()
        rc_frozen, _out, err_frozen, output = self._build(sidecar)
        self.assertEqual(rc_frozen, 0, err_frozen)
        frozen_bytes = output.read_bytes()
        snap = sidecar.parent / "snapshot.json"
        snap.write_text(json.dumps(snapshot(raw_sha256=raw)),
                        encoding="utf-8")
        rc_snap, _out, err_snap, output = self._build(sidecar,
                                                     snapshot_file=snap)
        self.assertEqual(rc_snap, 0, err_snap)
        self.assertEqual(frozen_bytes, output.read_bytes())

    def test_frozen_provenance_bytes_are_deterministic_across_roots(self):
        """Kayıt iki farklı kökte de aynı provenance baytlarını verir
        (yol sızmaz — yeniden üretilebilirlik kapısı bunu karşılaştırır)."""
        bytes_seen = []
        for _ in range(2):
            sidecar, _raw = self._fixture()
            rc, _out, err, output = self._build(sidecar)
            self.assertEqual(rc, 0, err)
            bytes_seen.append(self._provenance_path(output).read_bytes())
        self.assertEqual(bytes_seen[0], bytes_seen[1])

    def _provenance_path(self, output):
        return output.parent / (output.stem + ".provenance.json")


if __name__ == "__main__":
    unittest.main()
