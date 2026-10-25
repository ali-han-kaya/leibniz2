#!/usr/bin/env python3
"""check_bootstrap_units.py — bootstrap_units.conf bütünlük doğrulaması.

Sözleşme (fail-closed): bootstrap_units.conf'taki HER satır, repodaki gerçek
bir yola/pakete çözülmelidir. Yazım hatası (unit adı, değişken adı, yol, paket
adı, metadata anahtarı) sessizce geçemez.

Her unit satırı için denetlenenler:
  A1  dev_bootstrap.sh'de `check_<unit>` fonksiyonu var       (unit adı yazımı)
  A2  dev_bootstrap.sh'de `provision_<unit>` fonksiyonu var   (yeniden adlandırma artığı)
  A3  check_/provision_ gövdesindeki her $VAR tanımlı          ($PPTXX gibi yazım)
  A4  her yol değişkeni repo-içi göreli bir yola çözülür ve o
      yolun en yakın varolan atası repo içinde bir dizindir    (yol yazımı/kaçış)
  A5  her `require.resolve('pkg')` paketi, çözülen dizinin
      package.json'unda dependencies/devDependencies'te tanımlı (paket yazımı)
  A6  `.bin/<bin>` probu varsa çözülen dizinde package.json var (kurulum hedefi)
  A7  metadata anahtarları bilinen kümeden, değerleri pozitif tamsayı (anahtar/değer yazımı)
  A8  conf'taki her unit UNITS dizisinde, UNITS'teki her girdi conf'ta (iki yönlü kapsam)

Çıktı: PASS/FAIL stderr'de; --json ile stdout'ta tek JSON belgesi.
stdlib-only: venv/node gerekmez.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))

METADATA_KEYS = {"install_time_s", "disk_mb"}
POSITIONAL = set("0123456789@*#?-!$")
# Betikte tanımlı olmasa da ortamdan gelen, gürültü yapmaması gereken adlar.
ENV_WHITELIST = {
    "HOME", "PATH", "PWD", "SHELL", "USER", "LOGNAME", "TMPDIR", "LANG",
    "LC_ALL", "TERM", "CI", "TZ", "HOSTNAME", "OSTYPE", "HOSTTYPE", "BASH_SOURCE",
}

FUNC_HEAD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", re.M)
VAR_ASSIGN = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)="\$([A-Za-z_][A-Za-z0-9_]*)(?:/([^"$]*))?"\s*$', re.M)
LOCAL_DECL = re.compile(r"^\s*local\s+([A-Za-z0-9_ ]+)$", re.M)
SIMPLE_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", re.M)
ARRAY_DECL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=\(([^)]*)\)\s*$", re.M)
UNITS_DECL = re.compile(r"^UNITS=\(([^)]*)\)\s*$", re.M)
# $VAR, ${VAR}, ${VAR:-x}, ${VAR[@]} ... (pozisyonel/special hariç)
BRACED = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
BARE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
REQUIRE_RESOLVE = re.compile(r"""require\.resolve\(\s*['"]([^'"]+)['"]""")
BIN_PROBE = re.compile(r"/node_modules/\.bin/([A-Za-z0-9_.-]+)")


def read_conf(path):
    """(units, metadata, raw_rows) — units: ad->durum, metadata: ad->{anahtar:deger}."""
    units, metadata, rows = {}, {}, []
    current = None
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_]+)((?:\.\w+)+)=(.*)$", stripped)
            if m:
                name, dotted, value = m.group(1), m.group(2), m.group(3).strip()
                meta_key = dotted.lstrip(".")
                if meta_key.count("."):
                    rows.append((lineno, "metadata-cok-noktali", stripped))
                    continue
                if current != name:
                    rows.append((lineno, "metadata-sahipsiz", stripped))
                metadata.setdefault(name, {})[meta_key] = value
                continue
            m = re.match(r"^([A-Za-z0-9_]+)=(.*)$", stripped)
            if m:
                name, value = m.group(1), m.group(2).strip()
                if name in units:
                    rows.append((lineno, "yinelenen-unit", stripped))
                units[name] = value
                metadata.setdefault(name, {})
                current = name
                continue
            rows.append((lineno, "cozulemeyen-satir", stripped))
    return units, metadata, rows


def parse_script(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return text


def function_bodies(text):
    """ad -> gövde metni."""
    bodies = {}
    heads = list(FUNC_HEAD.finditer(text))
    for i, m in enumerate(heads):
        start = m.end()
        end = len(text)
        # gövde, satır başındaki ilk '}' ile biter
        for cm in re.finditer(r"^\}", text[start:], re.M):
            end = start + cm.start()
            break
        bodies[m.group(1)] = text[start:end]
    return bodies


def path_vars(text):
    """Tanımlı yol değişkenleri: ad -> ham tanım (köken_ad, göreli_parça) ya da None."""
    table = {}
    for m in VAR_ASSIGN.finditer(text):
        name, origin, tail = m.group(1), m.group(2), m.group(3) or ""
        table[name] = (origin, tail)
    return table


def resolve_path_var(name, table, seen=None):
    """Yol değişkenini repo-göreli yola çöz; çözülemezse None."""
    seen = seen or set()
    if name in seen:
        return None
    seen.add(name)
    if name not in table:
        return None
    origin, tail = table[name]
    if origin == "ROOT":
        base = ""
    else:
        base = resolve_path_var(origin, table, seen)
        if base is None:
            return None
    parts = [p for p in (base + "/" + tail).split("/") if p not in ("", ".")]
    return "/".join(parts)


def defined_names(text, bodies):
    names = set()
    for pattern in (LOCAL_DECL, SIMPLE_ASSIGN, ARRAY_DECL):
        for m in pattern.finditer(text):
            for tok in m.group(1).split():
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tok):
                    names.add(tok)
    names.update(bodies)
    return names


def var_refs(body):
    refs = set(BRACED.findall(body)) | set(BARE.findall(body))
    return {r for r in refs if r not in POSITIONAL}


def nearest_existing(path):
    cur = path
    while True:
        if os.path.exists(cur):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def validate(root, conf_path, script_path):
    """Dönüş: (errors, info) — errors fail-closed, info raporlama."""
    errors, info = [], []
    if not os.path.isfile(conf_path):
        return ["conf bulunamadı: %s" % conf_path], info
    if not os.path.isfile(script_path):
        return ["betik bulunamadı: %s" % script_path], info

    units, metadata, rows = read_conf(conf_path)
    for lineno, kind, raw in rows:
        errors.append("satır %d [%s]: %s" % (lineno, kind, raw))
    if not units:
        return errors + ["conf'ta hiç unit satırı yok"], info

    text = parse_script(script_path)
    bodies = function_bodies(text)
    table = path_vars(text)
    defined = defined_names(text, bodies)

    units_decl = UNITS_DECL.search(text)
    units_list = units_decl.group(1).split() if units_decl else None

    real_root = os.path.realpath(root)

    for unit in sorted(units):
        # A1 / A2
        check_fn = "check_" + unit
        prov_fn = "provision_" + unit
        if check_fn not in bodies:
            errors.append("%s: A1 — %s() dev_bootstrap.sh'de yok (unit adı yazımı?)" % (unit, check_fn))
            continue
        if prov_fn not in bodies:
            errors.append("%s: A2 — %s() dev_bootstrap.sh'de yok (yeniden adlandırma artığı?)" % (unit, prov_fn))

        for fn in (check_fn, prov_fn):
            body = bodies.get(fn)
            if body is None:
                continue
            # A3 — tanımsız değişken
            for ref in sorted(var_refs(body)):
                if ref in defined or ref in ENV_WHITELIST:
                    continue
                if not re.match(r"^[A-Z][A-Z0-9_]*$", ref):
                    continue
                errors.append("%s: A3 — %s() tanımsız değişken kullanıyor: $%s" % (unit, fn, ref))

            # A4 — yol değişkenleri repo içine çözülmeli
            for ref in sorted(var_refs(body)):
                if ref not in table:
                    continue
                rel = resolve_path_var(ref, table)
                if rel is None:
                    errors.append("%s: A4 — %s() yol değişkeni çözülemiyor: $%s" % (unit, fn, ref))
                    continue
                if os.path.isabs(rel) or rel.startswith("..") or "/../" in "/" + rel:
                    errors.append("%s: A4 — $%s repo dışına çıkıyor: %s" % (unit, ref, rel))
                    continue
                anchor = nearest_existing(os.path.join(real_root, rel))
                if anchor is None:
                    errors.append("%s: A4 — $%s için repo içinde varolan bir ata yok: %s" % (unit, ref, rel))
                    continue
                # realpath DEĞİL: venv/bin/python gibi sembolik bağlar (gitignored
                # kurulum artefaktları) meşru olarak repo dışını gösterebilir.
                if os.path.commonpath([os.path.abspath(anchor), real_root]) != real_root:
                    errors.append("%s: A4 — $%s repo dışına çözülüyor: %s" % (unit, ref, rel))
                    continue
                info.append("%s: $%s -> %s (anchor %s)" % (unit, ref, rel, os.path.relpath(anchor, real_root)))

            # A5 — require.resolve paketleri package.json'da tanımlı olmalı
            body_dirs = [r for r in sorted(var_refs(body)) if r in table]
            for pkg in sorted(set(REQUIRE_RESOLVE.findall(body))):
                dir_rel = resolve_path_var(body_dirs[0], table) if body_dirs else None
                if dir_rel is None:
                    errors.append("%s: A5 — require.resolve('%s') için dizin çözülemedi" % (unit, pkg))
                    continue
                pkg_json = os.path.join(root, dir_rel, "package.json")
                if not os.path.isfile(pkg_json):
                    errors.append("%s: A5 — require.resolve('%s') ama %s/package.json yok" % (unit, pkg, dir_rel))
                    continue
                try:
                    with open(pkg_json, encoding="utf-8") as fh:
                        data = json.loads(fh.read())
                except (OSError, ValueError) as exc:
                    errors.append("%s: A5 — %s/package.json okunamadı: %s" % (unit, dir_rel, exc))
                    continue
                declared = set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
                if pkg not in declared:
                    errors.append(
                        "%s: A5 — paket '%s' %s/package.json içinde tanımlı değil (yazım hatası?)"
                        % (unit, pkg, dir_rel)
                    )

            # A6 — .bin probu varsa dizinde package.json olmalı
            if BIN_PROBE.search(body):
                dir_rel = resolve_path_var(body_dirs[0], table) if body_dirs else None
                if dir_rel and not os.path.isfile(os.path.join(root, dir_rel, "package.json")):
                    errors.append("%s: A6 — .bin probu var ama %s/package.json yok" % (unit, dir_rel))

        # A7 — metadata
        for key, value in sorted(metadata.get(unit, {}).items()):
            if key not in METADATA_KEYS:
                errors.append("%s: A7 — bilinmeyen metadata anahtarı: %s.%s (yazım hatası?)" % (unit, unit, key))
                continue
            try:
                ival = int(value)
            except ValueError:
                errors.append("%s: A7 — %s.%s='%s' pozitif tamsayı değil" % (unit, unit, key, value))
                continue
            if ival <= 0:
                errors.append("%s: A7 — %s.%s=%d pozitif olmalı" % (unit, unit, key, ival))

    # sahipsiz metadata (unit satırı gelmemiş)
    for name in sorted(metadata):
        if name not in units and metadata[name]:
            errors.append("%s: A7 — metadata var ama unit satırı yok" % name)

    # A8 — iki yönlü kapsam
    if units_list is None:
        errors.append("A8 — dev_bootstrap.sh'de UNITS=(...) bulunamadı")
    else:
        missing_in_script = sorted(set(units) - set(units_list))
        missing_in_conf = sorted(set(units_list) - set(units))
        if missing_in_script:
            errors.append("A8 — conf'ta var, UNITS'te yok: %s" % ", ".join(missing_in_script))
        if missing_in_conf:
            errors.append("A8 — UNITS'te var, conf'ta yok: %s" % ", ".join(missing_in_conf))

    return errors, info


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.normpath(os.path.join(here, os.pardir, os.pardir))
    parser = argparse.ArgumentParser(description="bootstrap_units.conf bütünlük doğrulaması")
    parser.add_argument("--json", action="store_true", help="stdout'a tek JSON belgesi yaz")
    parser.add_argument("--root", default=default_root, help="repo kökü (test için)")
    parser.add_argument("--conf", default=None, help="bootstrap_units.conf yolu (test için)")
    parser.add_argument("--script", default=None, help="dev_bootstrap.sh yolu (test için)")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    conf_path = args.conf or os.path.join(root, "_calisma", "bootstrap_units.conf")
    script_path = args.script or os.path.join(root, "_calisma", "dev_bootstrap.sh")

    errors, info = validate(root, conf_path, script_path)

    if args.json:
        # stdout TEK JSON belgesi; insan-okunur tanılama yok.
        print(json.dumps({
            "valid": not errors,
            "root": root,
            "conf": conf_path,
            "script": script_path,
            "resolved": list(dict.fromkeys(info)),
            "errors": errors,
        }, indent=2, ensure_ascii=False))
        return 0 if not errors else 1

    for line in dict.fromkeys(info):
        print("  ok: " + line, file=sys.stderr)
    if errors:
        for line in errors:
            print("FAIL: " + line, file=sys.stderr)
        print("BOOTSTRAP UNITS FAIL: %d sorun" % len(errors), file=sys.stderr)
        return 1
    print("PASS: bootstrap_units.conf satırları gerçek yol/paketlere çözülüyor", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
