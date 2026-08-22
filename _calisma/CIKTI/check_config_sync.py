#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_config_sync.py — verify.yml "Bundle config snapshot" ↔ CONFIG_BASENAMES senkronu.

verify.yml'deki config artifact'ının kopyaladığı/ürettiği her dosyanın
gen_repro_manifest.py CONFIG_BASENAMES set'inde tanımlı olduğunu ve tersini
doğrular. Drift: workflow'a yeni config dosyası eklenir ama CONFIG_BASENAMES
güncellenmezse (veya tersi) → config dosyası manifest'ten düşer → K10
manifest denetimi o dosyayı göremez → sessiz kapsam kaybı.

Kullanım:
  python3 check_config_sync.py                  # denetle (exit 0/1)
  python3 check_config_sync.py --json            # makine-okur JSON

Exit: 0 = senkron; 1 = drift var (FAIL) veya parse hatası; 2 = kullanım hatası.
"""

import argparse
import ast
import json
import os
import re
import sys

DEFAULT_WORKFLOW = ".github/workflows/verify.yml"
DEFAULT_MANIFEST_SCRIPT = "_calisma/CIKTI/gen_repro_manifest.py"
DEFAULT_CONFIG_JSON = "_calisma/CIKTI/verify_delivery.config.json"

# "Bundle config snapshot" adımındaki cp/sha256sum satırlarından basename çek.
# Desenler:
#   cp kaynak_dosya config/           → basename(kaynak)
#   sha256sum config/* > config/X     → X
#   python3 diff_config... --out-dir config → config-diff.txt + config-diff.json
# (hardcoded: config-diff.{txt,json} her zaman üretilir — _diff_out_basenames)
_CP_RE = re.compile(r"cp\s+\S+\s+config/")
_SHA_RE = re.compile(r"sha256sum.*>.*config/(\S+)")
_DIFF_RE = re.compile(r"diff_config_artifacts\.py")

# diff_config_artifacts.py her zaman bu iki dosyayı üretir (--out-dir config).
_DIFF_OUT_BASENAMES = frozenset({"config-diff.txt", "config-diff.json"})


def extract_workflow_config_basenames(workflow_text: str) -> frozenset:
    """verify.yml "Bundle config snapshot" adımında kopyalanan/üretilen dosya adları."""
    basenames = set()
    in_block = False
    for line in workflow_text.splitlines():
        if "Bundle config snapshot" in line or "Generate config diff" in line:
            in_block = True
            continue
        # "Upload config snapshot" ile config artifact'ı kapanır — dur.
        if in_block and "Upload config snapshot" in line:
            break
        if in_block:
            # cp ile kopyalanan dosya: "cp <kaynak> config/ ..."
            # Whitespace ile böl, 2. token kaynak dosyadır (1. token "cp").
            m = _CP_RE.search(line)
            if m:
                tokens = line.strip().split()
                if len(tokens) >= 2:
                    src = tokens[1]
                    basename = os.path.basename(src)
                    if basename and basename != "config":
                        basenames.add(basename)
            # sha256sum ile üretilen
            m = _SHA_RE.search(line)
            if m:
                basenames.add(m.group(1))
            # diff_config_artifacts.py çıktıları
            if _DIFF_RE.search(line):
                basenames |= _DIFF_OUT_BASENAMES
    return frozenset(basenames)


def extract_config_basenames_from_module(script_text: str) -> frozenset:
    """gen_repro_manifest.py'den CONFIG_BASENAMES frozenset'ini ayıkla."""
    # AST ile CONFIG_BASENAMES atamasını bul.
    try:
        tree = ast.parse(script_text)
    except SyntaxError as e:
        print(f"HATA: gen_repro_manifest.py ayrıştırılamadı: {e}", file=sys.stderr)
        return frozenset()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CONFIG_BASENAMES":
                    if isinstance(node.value, ast.Call):
                        # frozenset({...})
                        if (isinstance(node.value.func, ast.Name) and
                                node.value.func.id == "frozenset"):
                            args = node.value.args
                            if args and isinstance(args[0], ast.Set):
                                return frozenset(
                                    elt.value if isinstance(elt, ast.Constant) else None
                                    for elt in args[0].elts
                                )
    return frozenset()


def extract_config_json_basenames(config_json_text: str) -> frozenset:
    """verify_delivery.config.json'dan config_artifact_basenames listesini ayıkla."""
    try:
        cfg = json.loads(config_json_text)
        lst = cfg.get("config_artifact_basenames")
        if isinstance(lst, list):
            return frozenset(lst)
    except (json.JSONDecodeError, ValueError):
        pass
    return frozenset()


def check(
    workflow_text: str,
    manifest_script_text: str,
    config_json_text: str = "",
) -> tuple:
    """Denetle. Döndürür (wf_basenames, manifest_basenames, config_basenames, error_messages).

    config_json_text verilmişse ÜÇLÜ karşılaştırma yapılır:
    verify.yml snapshot ↔ CONFIG_BASENAMES ↔ verify_delivery.config.json.
    """
    errors = []

    wf_basenames = extract_workflow_config_basenames(workflow_text)
    if not wf_basenames:
        errors.append("verify.yml'de 'Bundle config snapshot' adımı bulunamadı "
                       "veya hiç dosya kopyalanmadı")

    manifest_basenames = extract_config_basenames_from_module(manifest_script_text)
    if not manifest_basenames:
        errors.append(f"gen_repro_manifest.py'de CONFIG_BASENAMES ayıklanamadı")

    config_json_basenames = extract_config_json_basenames(config_json_text)

    if not errors:
        # Workflow'ta var, manifest'te yok → manifest eksik
        only_wf = wf_basenames - manifest_basenames
        for name in sorted(only_wf):
            errors.append(
                f"CONFIG_BASENAMES'te EKSİK: '{name}' — verify.yml config "
                f"snapshot'ında kopyalanıyor ama manifest'te config olarak "
                f"işaretlenmemiş → K10 göremez"
            )

        # Manifest'te var, workflow'da yok → manifest'te hayalet dosya
        only_manifest = manifest_basenames - wf_basenames
        for name in sorted(only_manifest):
            errors.append(
                f"verify.yml config snapshot'ında YOK: '{name}' — "
                f"CONFIG_BASENAMES'te tanımlı ama workflow kopyalamıyor → "
                f"manifest'te sahte dosya"
            )

        # Üçlü: config.json ↔ CONFIG_BASENAMES (yalnızca config.json varsa)
        if config_json_basenames:
            # config.json'da var, CONFIG_BASENAMES'te yok → schema bayat
            only_json = config_json_basenames - manifest_basenames
            for name in sorted(only_json):
                errors.append(
                    f"CONFIG_BASENAMES'te EKSİK (config.json'da var): '{name}' "
                    f"— verify_delivery.config.json schema'da tanımlı ama "
                    f"gen_repro_manifest.py'de yok → schema drift"
                )
            # CONFIG_BASENAMES'te var, config.json'da yok → schema eksik
            only_code = manifest_basenames - config_json_basenames
            for name in sorted(only_code):
                errors.append(
                    f"config_artifact_basenames'te EKSİK: '{name}' — "
                    f"CONFIG_BASENAMES'te tanımlı ama "
                    f"verify_delivery.config.json schema'da yok → "
                    f"schema güncellenmemiş"
                )
            # config.json ↔ workflow da tutarlı olmalı
            only_json_wf = config_json_basenames - wf_basenames
            for name in sorted(only_json_wf):
                errors.append(
                    f"config.json → workflow drift: '{name}' — "
                    f"config_artifact_basenames'te var ama verify.yml "
                    f"snapshot'ında kopyalanmıyor"
                )
            only_wf_json = wf_basenames - config_json_basenames
            for name in sorted(only_wf_json):
                errors.append(
                    f"workflow → config.json drift: '{name}' — "
                    f"verify.yml snapshot'ında kopyalanıyor ama "
                    f"config_artifact_basenames listesinde yok → "
                    f"schema güncellenmemiş"
                )

    return wf_basenames, manifest_basenames, config_json_basenames, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW,
                    help=f"workflow dosyası (varsayılan: {DEFAULT_WORKFLOW})")
    ap.add_argument("--manifest-script", default=DEFAULT_MANIFEST_SCRIPT,
                    help=f"gen_repro_manifest.py yolu (varsayılan: {DEFAULT_MANIFEST_SCRIPT})")
    ap.add_argument("--config-json", default=DEFAULT_CONFIG_JSON,
                    help=f"verify_delivery.config.json yolu "
                         f"(varsayılan: {DEFAULT_CONFIG_JSON})")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)

    for path, label in [(args.workflow, "workflow"),
                         (args.manifest_script, "manifest script")]:
        if not os.path.isfile(path):
            print(f"HATA: {label} bulunamadı: {path}", file=sys.stderr)
            return 2

    try:
        with open(args.workflow, encoding="utf-8") as f:
            wf_text = f.read()
    except OSError as e:
        print(f"HATA: workflow okunamadı ({args.workflow}): {e}", file=sys.stderr)
        return 2

    try:
        with open(args.manifest_script, encoding="utf-8") as f:
            manifest_text = f.read()
    except OSError as e:
        print(f"HATA: gen_repro_manifest.py okunamadı: {e}", file=sys.stderr)
        return 2

    config_text = ""
    if os.path.isfile(args.config_json):
        try:
            with open(args.config_json, encoding="utf-8") as f:
                config_text = f.read()
        except OSError as e:
            print(f"UYARI: config.json okunamadı ({args.config_json}): {e} — "
                  f"üçlü karşılaştırma atlanıyor", file=sys.stderr)

    wf_basenames, manifest_basenames, config_basenames, errors = check(
        wf_text, manifest_text, config_text)

    if args.json:
        print(json.dumps({
            "workflow_config_basenames": sorted(wf_basenames),
            "manifest_config_basenames": sorted(manifest_basenames),
            "config_json_basenames": sorted(config_basenames) if config_basenames else None,
            "has_drift": bool(errors),
            "errors": errors,
        }, indent=2, ensure_ascii=False))
    else:
        print("Config senkron denetimi:")
        print(f"  verify.yml snapshot:  {sorted(wf_basenames)}")
        print(f"  CONFIG_BASENAMES:     {sorted(manifest_basenames)}")
        if config_basenames:
            print(f"  config.json schema:   {sorted(config_basenames)}")
        if errors:
            print(f"\n  DRIFT ({len(errors)} sorun):")
            for e in errors:
                print(f"    - {e}")
            print(f"\n  SONUÇ: FAIL — üç kaynak arasında drift var.")
        else:
            print(f"\n  SONUÇ: PASS — {len(wf_basenames)} dosya üç kaynakta senkron.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())