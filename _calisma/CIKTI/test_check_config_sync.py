#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_config_sync.py — check_config_sync.py için birim testler.

Üç senaryo:
  1) Gerçek workflow ↔ gerçek CONFIG_BASENAMES → şu an PASS
  2) Workflow'a sahte dosya ekle (CONFIG_BASENAMES'te yok) → FAIL
  3) CONFIG_BASENAMES'ten dosya sil → workflow'da var, manifest'te yok → FAIL
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

    def test_real_files_synced(self):
        """Gerçek workflow + CONFIG_BASENAMES → PASS."""
        wf, mf, errors = check(self.wf_text, self.manifest_text)
        self.assertFalse(errors, f"Beklenmeyen drift: {errors}")

    def test_workflow_adds_file_not_in_manifest(self):
        """Workflow'a yeni dosya ekle, CONFIG_BASENAMES güncellenmemiş → FAIL."""
        # Yeni cp satırını "Bundle config snapshot" adımının içine,
        # "Upload config snapshot" satırından önce enjekte et.
        modified_wf = self.wf_text.replace(
            "- name: Upload config snapshot",
            "          cp _calisma/CIKTI/new_config.json config/\n"
            "      - name: Upload config snapshot"
        )
        wf, mf, errors = check(modified_wf, self.manifest_text)
        self.assertTrue(errors, f"Drift tespit edilmedi: {errors}")
        self.assertTrue(any("new_config.json" in e for e in errors),
                        f"'new_config.json' tespit edilmedi: {errors}")
        self.assertTrue(any("EKSİK" in e for e in errors),
                        f"'EKSİK' ibaresi yok: {errors}")

    def test_manifest_has_file_not_in_workflow(self):
        """CONFIG_BASENAMES'te tanımlı ama workflow'da kopyalanmıyor → FAIL."""
        # CONFIG_BASENAMES satırına sahte dosya ekle
        modified_manifest = self.manifest_text.replace(
            '"config.sha256",',
            '"config.sha256",\n    "hayalet_config.json",'
        )
        wf, mf, errors = check(self.wf_text, modified_manifest)
        self.assertTrue(errors)
        self.assertTrue(any("hayalet_config.json" in e for e in errors),
                        f"'hayalet_config.json' tespit edilmedi: {errors}")
        self.assertTrue(any("YOK" in e for e in errors),
                        f"'YOK' ibaresi yok: {errors}")

    def test_both_missing(self):
        """İki tarafta da farklıysa iki yönlü drift raporlanır."""
        # CONFIG_BASENAMES'e hayalet ekle
        modified_manifest = self.manifest_text.replace(
            '"config.sha256",',
            '"config.sha256",\n    "phantom.json",'
        )
        # Workflow'a extra.json ekle (Bundle config snapshot içine)
        modified_wf = self.wf_text.replace(
            "- name: Upload config snapshot",
            "          cp _calisma/CIKTI/extra.json config/\n"
            "      - name: Upload config snapshot"
        )
        wf, mf, errors = check(modified_wf, modified_manifest)
        self.assertTrue(len(errors) >= 2, f"En az 2 hata bekleniyor: {errors}")
        self.assertTrue(any("phantom.json" in e for e in errors))
        self.assertTrue(any("extra.json" in e for e in errors))

    def test_json_output(self):
        """--json çıktısı geçerli ve has_drift alanı var."""
        import json
        import subprocess
        # Proje root — testler proje root'undan koşulur
        project_root = os.getcwd()
        result = subprocess.run(
            [sys.executable, "_calisma/CIKTI/check_config_sync.py", "--json"],
            capture_output=True, text=True, cwd=project_root
        )
        data = json.loads(result.stdout)
        self.assertIn("has_drift", data)
        self.assertIn("workflow_config_basenames", data)
        self.assertIn("manifest_config_basenames", data)
        self.assertIsInstance(data["errors"], list)
        self.assertEqual(data["has_drift"], False)


if __name__ == "__main__":
    unittest.main()