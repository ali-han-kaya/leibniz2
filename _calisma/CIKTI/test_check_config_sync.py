#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_config_sync.py — check_config_sync.py için birim testler.

Dört senaryo:
  1) Gerçek üçlü (workflow + CONFIG_BASENAMES + config.json) → şu an PASS
  2) Workflow'a sahte dosya ekle (CONFIG_BASENAMES'te yok) → FAIL
  3) CONFIG_BASENAMES'ten dosya sil → workflow'da var, manifest'te yok → FAIL
  4) config.json'dan dosya sil (CONFIG_BASENAMES'te var) → FAIL
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from check_config_sync import check


class TestConfigSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(".github/workflows/verify.yml", encoding="utf-8") as f:
            cls.wf_text = f.read()
        with open("_calisma/CIKTI/gen_repro_manifest.py", encoding="utf-8") as f:
            cls.manifest_text = f.read()
        with open("_calisma/CIKTI/verify_delivery.config.json", encoding="utf-8") as f:
            cls.config_text = f.read()

    def test_real_files_three_way_synced(self):
        """Gerçek üçlü (workflow + CONFIG_BASENAMES + config.json) → PASS."""
        wf, mf, cf, errors = check(self.wf_text, self.manifest_text, self.config_text)
        self.assertFalse(errors, f"Beklenmeyen drift: {errors}")

    def test_workflow_adds_file_not_in_manifest(self):
        """Workflow'a yeni dosya ekle, CONFIG_BASENAMES güncellenmemiş → FAIL."""
        modified_wf = self.wf_text.replace(
            "- name: Upload config snapshot",
            "          cp _calisma/CIKTI/new_config.json config/\n"
            "      - name: Upload config snapshot"
        )
        wf, mf, cf, errors = check(modified_wf, self.manifest_text, self.config_text)
        self.assertTrue(errors, f"Drift tespit edilmedi: {errors}")
        self.assertTrue(any("new_config.json" in e for e in errors),
                        f"'new_config.json' tespit edilmedi: {errors}")
        self.assertTrue(any("EKSİK" in e for e in errors),
                        f"'EKSİK' ibaresi yok: {errors}")

    def test_manifest_has_file_not_in_workflow(self):
        """CONFIG_BASENAMES'te tanımlı ama workflow'da kopyalanmıyor → FAIL."""
        modified_manifest = self.manifest_text.replace(
            '"config.sha256",',
            '"config.sha256",\n    "hayalet_config.json",'
        )
        wf, mf, cf, errors = check(self.wf_text, modified_manifest, self.config_text)
        self.assertTrue(errors)
        self.assertTrue(any("hayalet_config.json" in e for e in errors),
                        f"'hayalet_config.json' tespit edilmedi: {errors}")
        self.assertTrue(any("YOK" in e for e in errors),
                        f"'YOK' ibaresi yok: {errors}")

    def test_config_json_has_file_not_in_manifest(self):
        """config.json'daki dosya CONFIG_BASENAMES'te yok → schema drift."""
        modified_config = self.config_text.replace(
            '"config.sha256",',
            '"config.sha256",\n    "phantom_config.json",'
        )
        wf, mf, cf, errors = check(self.wf_text, self.manifest_text, modified_config)
        self.assertTrue(errors)
        self.assertTrue(any("phantom_config.json" in e for e in errors),
                        f"'phantom_config.json' tespit edilmedi: {errors}")
        self.assertTrue(any("schema drift" in e.lower() for e in errors),
                        f"'schema drift' ibaresi yok: {errors}")

    def test_config_json_missing_field_from_manifest(self):
        """CONFIG_BASENAMES'te var, config.json'da yok → schema güncellenmemiş."""
        modified_config = self.config_text.replace(
            '"config.sha256",\n    "effective_config.json",',
            '"config.sha256",'
        )
        wf, mf, cf, errors = check(self.wf_text, self.manifest_text, modified_config)
        self.assertTrue(errors)
        self.assertTrue(any("effective_config.json" in e for e in errors),
                        f"'effective_config.json' eksikliği tespit edilmedi: {errors}")
        self.assertTrue(any("schema güncellenmemiş" in e for e in errors),
                        f"'schema güncellenmemiş' ibaresi yok: {errors}")

    def test_both_missing(self):
        """İki tarafta da farklıysa iki yönlü drift raporlanır."""
        modified_manifest = self.manifest_text.replace(
            '"config.sha256",',
            '"config.sha256",\n    "phantom.json",'
        )
        modified_wf = self.wf_text.replace(
            "- name: Upload config snapshot",
            "          cp _calisma/CIKTI/extra.json config/\n"
            "      - name: Upload config snapshot"
        )
        wf, mf, cf, errors = check(modified_wf, modified_manifest, self.config_text)
        self.assertTrue(len(errors) >= 2, f"En az 2 hata bekleniyor: {errors}")
        self.assertTrue(any("phantom.json" in e for e in errors))
        self.assertTrue(any("extra.json" in e for e in errors))

    def test_json_output(self):
        """--json çıktısı geçerli ve has_drift alanı var."""
        import json
        import subprocess
        project_root = os.getcwd()
        result = subprocess.run(
            [sys.executable, "_calisma/CIKTI/check_config_sync.py", "--json"],
            capture_output=True, text=True, cwd=project_root
        )
        data = json.loads(result.stdout)
        self.assertIn("has_drift", data)
        self.assertIn("workflow_config_basenames", data)
        self.assertIn("manifest_config_basenames", data)
        self.assertIn("config_json_basenames", data)
        self.assertIsInstance(data["errors"], list)
        self.assertEqual(data["has_drift"], False)

    def test_no_config_json_still_works(self):
        """config.json verilmezse ikili karşılaştırma yapar (geriye uyumlu)."""
        wf, mf, cf, errors = check(self.wf_text, self.manifest_text, "")
        self.assertFalse(cf)  # boş frozenset
        self.assertFalse(errors, f"İkili karşılaştırma bozuldu: {errors}")


if __name__ == "__main__":
    unittest.main()