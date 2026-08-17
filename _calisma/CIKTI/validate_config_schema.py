#!/usr/bin/env python3
"""validate_config_schema.py — verify_delivery.config.json'u JSON Schema ile doğrula.

CI fail-closed kapısı: geçersiz/bozuk konfig build'i bloke eder.
`jsonschema` kütüphanesi gerekir (CI'da `pip install jsonschema`).

Kullanım:
    python3 validate_config_schema.py [schema_path] [config_path]

Exit kodu:
    0 = geçerli
    1 = şema ihlali veya konfig JSON parse hatası (bloke edilmeli)
    2 = ortam hatası (jsonschema/dosya yok, şema bozuk)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(HERE, "verify_delivery.config.schema.json")
DEFAULT_CONFIG = os.path.join(HERE, "verify_delivery.config.json")


def main():
    schema_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCHEMA
    config_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CONFIG

    try:
        import jsonschema
    except ImportError:
        print("HATA: jsonschema kurulu değil — `pip install jsonschema`",
              file=sys.stderr)
        return 2

    if not os.path.isfile(schema_path):
        print(f"HATA: şema bulunamadı: {schema_path}", file=sys.stderr)
        return 2
    if not os.path.isfile(config_path):
        print(f"HATA: konfig bulunamadı: {config_path}", file=sys.stderr)
        return 2

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        print(f"HATA: şema geçerli JSON değil ({schema_path}): {e}",
              file=sys.stderr)
        return 2

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"HATA: konfig geçerli JSON değil ({config_path}): {e}",
              file=sys.stderr)
        return 1  # konfig parse hatası = şema ihlali gibi bloke edilmeli

    # Şema dosyasının kendisini de doğrula (draft-07 metaschema'ya karşı)
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        print(f"HATA: şema geçersiz ({schema_path}): {e}", file=sys.stderr)
        return 2

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))

    if errors:
        print(f"HATA: konfig şema doğrulaması başarısız "
              f"({len(errors)} ihlal):")
        for e in errors:
            path = "/".join(str(p) for p in e.path) or "(root)"
            print(f"  - {path}: {e.message}")
        return 1

    print(f"OK: {os.path.basename(config_path)} → "
          f"{os.path.basename(schema_path)} şemasına uygun")
    return 0


if __name__ == "__main__":
    sys.exit(main())
