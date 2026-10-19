#!/usr/bin/env python3
"""gen_preview_contract.py — preview_contract.schema.json'dan TS tiplerini üret.

Tek doğruluk kaynağı şemadır; çıktı apps/dashboard-next/lib/preview-contract.generated.ts
dosyasıdır (ELLE DÜZENLENMEZ). Üreteç fail-closed'dur: desteklenmeyen bir şema
anahtarı, iç içe adsız nesne ya da eksik $ref sessizce atlanmaz, hata verir.

Kullanım:
    python3 gen_preview_contract.py            # --check: üretilmiş dosya güncel mi
    python3 gen_preview_contract.py --write    # yeniden üret

Exit kodu:
    0 = güncel (--check) / yazıldı (--write)
    1 = dosya eski/eksik (--check)
    2 = şema geçersiz, desteklenmeyen anahtar, ya da jsonschema yok

Bağımlılık: şema doğrulaması için `jsonschema` (requirements-z3.txt'te pinli);
üretim yalnız stdlib.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCHEMA_PATH = os.path.join(HERE, "preview_contract.schema.json")
OUT_PATH = os.path.join(REPO_ROOT, "apps", "dashboard-next", "lib",
                        "preview-contract.generated.ts")

HEADER = (
    "// GENERATED — elle düzenlemeyin. Kaynak: _calisma/CIKTI/preview_contract.schema.json\n"
    "// Yeniden üretim: python3 _calisma/CIKTI/gen_preview_contract.py --write\n"
    "// Elle değişiklik `--check` ve test_preview_contract.py'yi kırmızıya düşürür.\n"
)

# Üreteçin bildiği anahtarlar. Bunların dışındaki her şey hata: bir kısıt
# (ör. minimum, enum) TS tipine yansımazsa sessiz bir sözleşme sapması olur.
_ALLOWED_KEYWORDS = {
    "$schema", "$id", "$defs", "title", "description", "type",
    "properties", "required", "items", "$ref",
}
_SCALAR_TS = {"string": "string", "integer": "number",
              "number": "number", "boolean": "boolean"}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEF_PREFIX = "#/$defs/"


class ContractError(Exception):
    """Şema, üreteçin desteklediği alt kümenin dışında."""


def _check_keywords(node, where):
    unknown = set(node) - _ALLOWED_KEYWORDS
    if unknown:
        raise ContractError(
            f"{where}: desteklenmeyen şema anahtarı(ları): {sorted(unknown)}")


def _ts_type(node, where):
    _check_keywords(node, where)
    if "$ref" in node:
        if set(node) - {"$ref", "description"}:
            raise ContractError(f"{where}: $ref yalnız tek başına kullanılabilir")
        ref = node["$ref"]
        if not ref.startswith(_DEF_PREFIX):
            raise ContractError(f"{where}: yalnız {_DEF_PREFIX}… referansları: {ref}")
        return ref[len(_DEF_PREFIX):]

    kinds = node.get("type")
    if kinds is None:
        raise ContractError(f"{where}: type tanımlı değil")
    if isinstance(kinds, str):
        kinds = [kinds]
    nullable = "null" in kinds
    base = [k for k in kinds if k != "null"]
    if len(base) != 1:
        raise ContractError(f"{where}: null dışında tek tip bekleniyor: {kinds}")
    kind = base[0]

    if kind == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            raise ContractError(f"{where}: array için items gerekli")
        inner = _ts_type(items, where + "[]")
        if "|" in inner:
            inner = f"({inner})"
        ts = f"{inner}[]"
    elif kind == "object":
        if node.get("properties"):
            raise ContractError(
                f"{where}: iç içe nesne desteklenmez — adlandırılmış $defs kullanın")
        ts = "{ [key: string]: unknown }"
    elif kind in _SCALAR_TS:
        ts = _SCALAR_TS[kind]
    else:
        raise ContractError(f"{where}: desteklenmeyen tip: {kind}")

    return f"{ts} | null" if nullable else ts


def _render_object(name, node):
    _check_keywords(node, name)
    if node.get("type") != "object":
        raise ContractError(f"{name}: yalnız object tanımları üretilebilir")
    if not _IDENT.match(name):
        raise ContractError(f"{name}: geçersiz TS tip adı")
    props = node.get("properties", {})
    required = node.get("required", [])
    missing = [r for r in required if r not in props]
    if missing:
        raise ContractError(f"{name}: required alanı properties'te yok: {missing}")

    lines = []
    if node.get("description"):
        lines.append(f"/** {node['description']} */")
    lines.append(f"export type {name} = {{")
    for key, sub in props.items():
        if not _IDENT.match(key):
            raise ContractError(f"{name}.{key}: alan adı TS tanımlayıcısı değil")
        ts = _ts_type(sub, f"{name}.{key}")
        if sub.get("description"):
            lines.append(f"  /** {sub['description']} */")
        opt = "" if key in required else "?"
        lines.append(f"  {key}{opt}: {ts};")
    lines.append("};")
    return "\n".join(lines)


def _validate_schema(schema):
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - ortam hatası
        raise SystemExit(f"jsonschema yok (requirements-z3.txt): {exc}")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise ContractError(f"şema geçersiz: {exc.message}")


def render(schema):
    """Şemayı TS kaynağına çevirir. Hata durumunda ContractError fırlatır."""
    _validate_schema(schema)
    defs = schema.get("$defs")
    if not isinstance(defs, dict) or not defs:
        raise ContractError("$defs boş ya da yok")
    blocks = [_render_object(name, node) for name, node in defs.items()]
    return HEADER + "\n" + "\n\n".join(blocks) + "\n"


def load_schema(path=SCHEMA_PATH):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--write", action="store_true",
                    help="çıktı dosyasını yeniden üret (varsayılan: --check)")
    args = ap.parse_args(argv)
    try:
        generated = render(load_schema())
    except ContractError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2

    if args.write:
        with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(generated)
        print(f"yazıldı: {OUT_PATH}")
        return 0

    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            current = f.read()
    except OSError:
        print(f"ESKİ: {OUT_PATH} yok — --write ile üretin", file=sys.stderr)
        return 1
    if current != generated:
        print(f"ESKİ: {OUT_PATH} şemayla uyuşmuyor — --write ile yenileyin",
              file=sys.stderr)
        return 1
    print("güncel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
