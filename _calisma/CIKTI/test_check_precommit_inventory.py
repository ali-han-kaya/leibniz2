#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_precommit_inventory.py — envanter kapısının sözleşme testleri.

Seam = kapı CLI'si + iki ayrıştırıcı (`config_hook_ids`, `doc_inventory`).
Gerçek repo testi (kapının asıl işi) + hermetik fixture'lar (ağaç/kaynak
gerekmez: sahte config + sahte doküman geçici dizinde yazılır).

Sözleşme noktaları:
  - iki yönlü fark: eksik (config'te var) VE fazla (doc'ta var)
  - varsayılan ADVISORY (bayatlıkta uyarı + exit 0), `--strict` → exit 1
  - körleşme exit 2: `repos:` yok / işaret yok / blok yok / config yok
  - ayrıştırıcı disiplini: yorum içi id'ler, başlık-yorumu (`# - id: …`),
    blok-dışı satırlar ve tekrarlar ölçüme girmez
  - --json gövdesi makine-okunur ve doğru (strict ile rc eşleşir)
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import check_precommit_inventory as gate  # noqa: E402

REAL_CONFIG = CIKTI.parent.parent / ".pre-commit-config.yaml"
REAL_DOC = CIKTI.parent.parent / "skills" / "verify-chain" / "SKILL.md"

# Gerçek zincirin hook sayısı — BİLEREK donmuş literal, otomatik TÜRETİLMEZ.
#
# Neden türetmiyoruz (`len(config_hook_ids(...))` gibi kendi kendini doğrulayan
# bir assert yerine): o zaman "envanter 62 hook" gerçeği hiçbir yerde sabit
# kalmaz ve sayı sessizce kayabilir. Buradaki amaç, zincir büyüdüğünde
# bilinçli bir karar: config'e EKLERSEN bu sabiti de güncelle (biri eklenip
# diğeri unutulursa test kırılır — bkz. 2026-09-28: yeni envanter hook'unda
# 62→63 güncellemesi dört ayrı yerde dağınık haldeydi; tek sabite toplandı).
REAL_HOOK_COUNT = 64

# Gerçek dosyaların biçimine sadık asgari fixture'lar.
FIXTURE_CONFIG = """\
# header comment — never parsed as hooks
#   0) update-config      : documented elsewhere
#   *) check-unstaged-delta
repos:
  - repo: local
    hooks:
      - id: check-unstaged-delta
        name: Block commits while unstaged tracked changes exist
        entry: python3 _calisma/CIKTI/check_unstaged_delta.py
        language: system
      - id: verify-delivery
        name: Verify delivery
        entry: python3 _calisma/CIKTI/verify_delivery_hook.py
        language: system
"""

FIXTURE_DOC = """\
## Wiring

Add a hook per gate. Existing hook inventory:

```
check-unstaged-delta  # first in chain
verify-delivery       # K1-K7 core
```

Rules that keep the chain honest:
"""


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _run(config_path, doc_path):
    """`run()` çağırır; çıktıyı yutar. Döner (rc, report).

    Körleşme vakaları bilerek HATA basar; test çıktısını kirletmesin.
    """
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return gate.run(config_path=config_path, doc_path=doc_path)


def _cli(argv):
    """CLI'yi çağırır; (rc, stdout) döndürür (çıktı stdout'a basılıyor)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gate.main(argv)
    return rc, buf.getvalue()


class ConfigParserTest(unittest.TestCase):
    def test_reads_ids_after_repos_only(self):
        ids = gate.config_hook_ids(FIXTURE_CONFIG)
        self.assertEqual(ids, ["check-unstaged-delta", "verify-delivery"])

    def test_header_comment_ids_are_not_hooks(self):
        # Başlık yorumu `#   *) check-unstaged-delta` içeriyor ama bu bir hook
        # TANIMI değil; yalnız `repos:` sonrası `- id:` satırları sayılır.
        ids = gate.config_hook_ids(FIXTURE_CONFIG)
        self.assertEqual(len(ids), 2)

    def test_missing_repos_returns_none(self):
        self.assertIsNone(gate.config_hook_ids("hooks:\n  - id: x\n"))

    def test_duplicates_collapse_preserving_order(self):
        text = "repos:\n  - repo: local\n    hooks:\n      - id: b\n      - id: a\n      - id: b\n"
        self.assertEqual(gate.config_hook_ids(text), ["b", "a"])

    def test_real_config_hook_count(self):
        # Zincir büyüdükçe bu sayı GÜNCELLENİR (envanter + config birlikte);
        # sayı donmuş değil, "hook'lar tekilleşmiş ve sayılabilir" invariant'ı.
        ids = gate.config_hook_ids(REAL_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(len(ids), REAL_HOOK_COUNT)
        self.assertEqual(len(set(ids)), len(ids))


class DocParserTest(unittest.TestCase):
    def test_reads_block_ids_in_order(self):
        self.assertEqual(gate.doc_inventory(FIXTURE_DOC),
                         ["check-unstaged-delta", "verify-delivery"])

    def test_marker_is_case_insensitive(self):
        doc = "Existing HOOK INVENTORY:\n\n```\nverify-delivery\n```\n"
        self.assertEqual(gate.doc_inventory(doc), ["verify-delivery"])

    def test_comment_text_is_not_an_id(self):
        # Yorumun içindeki kelimeler id sanılmamalı: yalnız `#` ÖNCESİ token.
        doc = "hook inventory:\n\n```\nverify-delivery  # checks K1-K7 core gates\n```\n"
        self.assertEqual(gate.doc_inventory(doc), ["verify-delivery"])

    def test_stops_at_closing_fence(self):
        doc = "hook inventory:\n\n```\nverify-delivery\n```\n\nupdate-config\n"
        self.assertEqual(gate.doc_inventory(doc), ["verify-delivery"])

    def test_no_marker_returns_none(self):
        self.assertIsNone(gate.doc_inventory("```\nverify-delivery\n```\n"))

    def test_marker_without_fence_returns_none(self):
        self.assertIsNone(gate.doc_inventory("hook inventory: see the config\n"))

    def test_real_doc_lists_the_full_chain(self):
        ids = gate.doc_inventory(REAL_DOC.read_text(encoding="utf-8"))
        self.assertIsNotNone(ids)
        # Envanter bloğu config'e birebir eşit olmalı (kapının kendisi de
        # bunu denetler; burada ikinci, bağımsız bir çapa).
        self.assertEqual(set(ids),
                         set(gate.config_hook_ids(REAL_CONFIG.read_text(encoding="utf-8"))))


class DiffTest(unittest.TestCase):
    def test_reports_missing_and_phantom(self):
        missing, phantom = gate.diff_doc(["a", "b"], ["b", "c"])
        self.assertEqual(missing, ["a"])
        self.assertEqual(phantom, ["c"])

    def test_synced_is_empty(self):
        self.assertEqual(gate.diff_doc(["a"], ["a"]), ([], []))


class RealRepoTest(unittest.TestCase):
    def test_inventory_is_synced_strict(self):
        """Kapının ASIL işi: gerçek ağaçta envanter config ile senkron olmalı.

        Yeni bir hook eklenip envanter güncellenmezse bu test kırmızıya düşer
        (bayatlık varsayılan modda yalnız uyarıdır — burada sıkı ölçüyoruz).
        """
        rc, report = _run(str(REAL_CONFIG), str(REAL_DOC))
        self.assertEqual(rc, 0, f"envanter bayat: eksik={report['missing']} "
                                f"fazla={report['phantom']}")
        self.assertEqual(report["config_count"], REAL_HOOK_COUNT)
        self.assertEqual(report["doc_count"], REAL_HOOK_COUNT)

    def test_cli_strict_exits_zero_on_real_repo(self):
        rc, out = _cli(["--strict"])
        self.assertEqual(rc, 0)
        self.assertIn("PASS: envanter senkron (%d hook)" % REAL_HOOK_COUNT, out)


class AdvisoryModeTest(unittest.TestCase):
    """Bayatlık VARSAYILAN modda bloklamaz (istek: 'uyarı versin')."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cfg = _write(self._td.name, "config.yaml", FIXTURE_CONFIG)
        # Envanterde ikinci hook YOK → 'missing' bekleniyor.
        self.doc = _write(self._td.name, "doc.md",
                          "hook inventory:\n\n```\ncheck-unstaged-delta\n```\n")

    def test_advisory_warns_and_exits_zero(self):
        rc, out = _cli(["--config", self.cfg, "--doc", self.doc])
        self.assertEqual(rc, 0)
        self.assertIn("BAYAT", out)
        self.assertIn("verify-delivery", out)
        self.assertIn("UYARI", out)

    def test_strict_exits_one(self):
        rc, out = _cli(["--config", self.cfg, "--doc", self.doc, "--strict"])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", out)

    def test_phantom_hook_names_a_removed_gate(self):
        doc = _write(self._td.name, "doc2.md",
                     "hook inventory:\n\n```\ncheck-unstaged-delta\n"
                     "verify-delivery\ncheck-removed-gate\n```\n")
        rc, report = _run(self.cfg, doc)
        self.assertEqual(rc, 1)
        self.assertEqual(report["phantom"], ["check-removed-gate"])
        self.assertEqual(report["missing"], [])

    def test_synced_fixture_is_clean(self):
        doc = _write(self._td.name, "doc3.md",
                     "hook inventory:\n\n```\ncheck-unstaged-delta\n"
                     "verify-delivery\n```\n")
        rc, out = _cli(["--config", self.cfg, "--doc", doc, "--strict"])
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)


class BlindGateTest(unittest.TestCase):
    """Ölçüm imkânsızsa exit 2 — körleşen kapı sessiz PASS vermez."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cfg = _write(self._td.name, "config.yaml", FIXTURE_CONFIG)

    def test_missing_marker_exits_two(self):
        doc = _write(self._td.name, "d.md", "no marker here\n")
        rc, report = _run(self.cfg, doc)
        self.assertEqual(rc, 2)
        self.assertFalse(report["ok"])

    def test_missing_config_exits_two(self):
        rc, _ = _run(os.path.join(self._td.name, "nope.yaml"), self.cfg)
        self.assertEqual(rc, 2)

    def test_config_without_repos_exits_two(self):
        cfg = _write(self._td.name, "cfg2.yaml", "default_stages: [pre-commit]\n")
        doc = _write(self._td.name, "d2.md", "hook inventory:\n\n```\nverify-delivery\n```\n")
        self.assertEqual(_run(cfg, doc)[0], 2)

    def test_strict_does_not_mask_blind_gate(self):
        doc = _write(self._td.name, "d3.md", "no marker here\n")
        rc, _ = _cli(["--config", self.cfg, "--doc", doc, "--strict"])
        self.assertEqual(rc, 2)


class JsonModeTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cfg = _write(self._td.name, "config.yaml", FIXTURE_CONFIG)
        self.doc = _write(self._td.name, "doc.md",
                          "hook inventory:\n\n```\ncheck-unstaged-delta\n```\n")

    def test_json_payload_is_machine_readable(self):
        rc, out = _cli(["--config", self.cfg, "--doc", self.doc, "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertTrue(payload["stale"])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missing"], ["verify-delivery"])
        self.assertEqual(payload["phantom"], [])
        self.assertEqual(payload["config_count"], 2)
        self.assertEqual(payload["doc_count"], 1)
        self.assertFalse(payload["strict"])

    def test_json_strict_sets_exit_one(self):
        rc, out = _cli(["--config", self.cfg, "--doc", self.doc,
                        "--json", "--strict"])
        self.assertEqual(rc, 1)
        self.assertTrue(json.loads(out)["strict"])

    def test_json_blind_gate_still_exits_two(self):
        doc = _write(self._td.name, "blind.md", "nothing\n")
        rc, _ = _cli(["--config", self.cfg, "--doc", doc, "--json"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
