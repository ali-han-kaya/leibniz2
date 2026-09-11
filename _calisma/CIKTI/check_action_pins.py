#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_action_pins.py — workflow action major sürümlerini pin'le (downgrade kapısı).

pre-commit hook'u: action_pins.json'daki minimum major sürümleri denetler.
Bir action daha ESKİ bir major'a düşürülürse (ör. actions/checkout@v7 → v6)
commit'i BLOKE eder. Lokal ve OFFLINE'dir — ağ çağrısı ve PyYAML YOKTUR
(yalnızca stdlib + hafif regex ile workflow'daki `uses:` satırları okunur).
Ağ bağımlısı node24 runtime denetimi (check_action_runtimes.py) CI'da ayrı
koşar; bu hook onun commit-öncesi, hızlı tamamlayıcısıdır.

Kurallar (fail-closed):
  - action pin'li VE major < pin   → FAIL  (downgrade — commit bloke edilir)
  - action pin'siz (yeni action)    → FAIL  (pin zorunlu; --update ile ekle)
  - action pin'li VE major == pin  → PASS
  - action pin'li VE major > pin   → WARN  (pin yükseltilebilir — --update)
  - lokal action (./...)            → SKIP  (markette değil)

Kullanım:
  python3 check_action_pins.py                       # .github/workflows/ altındaki tüm YAML (exit 0/1)
  python3 check_action_pins.py --workflow .github/workflows/verify.yml
  python3 check_action_pins.py --workflow .github/workflows   # dizin → tüm YAML
  python3 check_action_pins.py --update        # mevcut major'ları pin dosyasına yaz
  python3 check_action_pins.py --bump          # WARN (upgrade) pin'lerini otomatik yükselt
  python3 check_action_pins.py --json          # makine-okur JSON

Exit: 0 = pin'ler karşılandı; 1 = FAIL var (downgrade/pin'siz); 2 = kullanım hatası.

--workflow bir DOSYA veya DİZİN olabilir: dizin verilirse içindeki tüm
*.yml/*.yaml dosyaları (sıralı) denetlenir; bulgular tek kümede toplanır ve
herhangi bir dosyada FAIL varsa exit 1 döner. --update/--bump da tüm
workflow'ların major'larını birleştirir (tek pin dosyası tüm iş akışlarını
kapsar).

--bump: yalnızca WARN durumlarını (workflow major > pin) yükseltir — mevcut
pin'leri aynen korur, yeni action EKLEMEZ (o iş --update'te), asla DÜŞÜRMEZ.
Fail-closed: FAIL varsa (downgrade / bozuk ref / pin'siz) hiçbir şey yazmaz
ve exit 1 döner — bir düzeltme yanlışlıkla maskelenmesin.
"""
import argparse
import json
import os
import pathlib
import re
import sys
import tempfile

DEFAULT_WORKFLOW = ".github/workflows"
DEFAULT_PINS = "_calisma/CIKTI/action_pins.json"

# Yalnızca kendi satırında `uses:` anahtarı olan satırlar yakalanır; hem
# `- uses: ...` (liste öğesi) hem `        uses: ...` (ayrı satır) biçimini
# yakalar. Değer boşluk/#/tırnakla sınırlanır ki heredoc içi JS/string'ler
# yanlış pozitif üretmesin.
_USES_RE = re.compile(r'^\s*(?:-\s*)?uses:\s*["\']?([^\s"\'#]+)')
# Ref biçimi: 'v7' (major) veya semver 'v0.35.0' / 'v3.1' (major = ilk
# bileşen — pin karşılaştırması major-granularity kalır; minor/patch
# yükselmeleri downgrade sayılmaz). 4+ bileşenli ref beklenmedik biçimdir
# (major=None → FAIL, fail-closed). Mutable ref'ler (@main/@master/@latest)
# yine hiç eşleşmez — 2026 trivy tag-compromise sınıfı asla geçemez.
_REF_RE = re.compile(r"^v(\d+)(?:\.\d+){0,2}$")


def resolve_workflows(path):
    """--workflow değerini workflow dosya listesine çöz (dosya VEYA dizin).

    Dizin verilirse içindeki tüm `*.yml`/`*.yaml` sıralı listelenir — böylece
    `.github/workflows/` altına eklenen yeni bir workflow otomatik denetime
    girer (check_python3_shell.py glob deseni). Dosya verilirse tek elemanlı
    liste döner. Geçersiz/boş yol → ValueError (main'de exit 2).
    """
    p = pathlib.Path(path)
    if p.is_dir():
        files = sorted(list(p.glob("*.yml")) + list(p.glob("*.yaml")))
        if not files:
            raise ValueError(f"dizinde workflow YAML yok: {path}")
        return files
    if p.is_file():
        return [p]
    raise ValueError(f"workflow yolu dosya veya dizin değil: {path}")


def extract_uses(workflow_text):
    """workflow metninden unique `uses:` değerlerini çıkar (görünüm sırasıyla).

    PyYAML gerektirmez; yalnızca satır-başı `uses:` anahtarlarına güvenir.
    """
    seen = set()
    out = []
    for line in workflow_text.splitlines():
        m = _USES_RE.match(line)
        if m:
            value = m.group(1).strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def split_action(action):
    """'actions/checkout@v7' → (owner_repo, ref, major|None)."""
    if "@" not in action:
        return action, "", None
    owner_repo, ref = action.rsplit("@", 1)
    m = _REF_RE.match(ref or "")
    major = int(m.group(1)) if m else None
    return owner_repo, ref, major


def load_pins(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"pin dosyası sözlük olmalı: {path}")
    return data


# actions/github-script@v8 scriptPath input'unu DESTEKLEMEZ (yalnızca
# 'script'). scriptPath kullanımı runtime'da "Input required and not supplied:
# script" ile patlar — çalışma dizininde dosya okunup eval edilmelidir
# (github_scripts_selftest.js harness deseni). Gelecekteki eklemeleri
# fail-closed yakalamak için workflow'da scriptPath geçmemelidir.
_SCRIPTPATH_RE = re.compile(r"^\s*scriptPath:\s*[\"']?([^\s\"'#]+)")


def check(workflow_text, pins):
    """Denetle. Döndürür finding listesi (verdict: PASS|FAIL|WARN|SKIP)."""
    findings = []
    for lineno, line in enumerate(workflow_text.splitlines(), 1):
        m = _SCRIPTPATH_RE.match(line)
        if m:
            findings.append({"action": "github-script", "major": None,
                             "pinned": None, "verdict": "FAIL",
                             "note": f"scriptPath desteklenmiyor (satır {lineno}: "
                                     f"{m.group(1)}) — 'script' input'uyla "
                                     "eval edilmeli (selftest harness deseni)"})
    for action in extract_uses(workflow_text):
        if action.startswith("./") or action.startswith("../"):
            findings.append({"action": action, "major": None, "pinned": None,
                             "verdict": "SKIP",
                             "note": "lokal action (markette değil)"})
            continue
        owner_repo, ref, major = split_action(action)
        if owner_repo in pins:
            pinned = pins[owner_repo]
            if major is None:
                findings.append({"action": action, "major": None, "pinned": pinned,
                                 "verdict": "FAIL",
                                 "note": f"major ayrıştırılamadı (ref='{ref}') — vN bekleniyor"})
            elif major < pinned:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "FAIL",
                                 "note": f"downgrade: v{major} < pin v{pinned}"})
            elif major > pinned:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "WARN",
                                 "note": f"pin yükseltilebilir: v{major} > v{pinned} (--update)"})
            else:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "PASS", "note": f"v{major} == pin"})
        else:
            findings.append({"action": action, "major": major, "pinned": None,
                             "verdict": "FAIL",
                             "note": "pin yok — yeni action action_pins.json'a eklenmeli (--update)"})
    return findings


def collect_pins(workflow_text):
    """Mevcut vN major'ları pin sözlüğü olarak topla (--update için).

    vN biçimli ref'i olmayan (ör. @main/@latest) action'lar atlanır — böylece
    --update asla ayrıştırılamayan bir pin yazmaz (o action sonraki check'te
    "pin yok" FAIL üretir, fail-closed).
    """
    pins = {}
    for action in extract_uses(workflow_text):
        if action.startswith("./") or action.startswith("../"):
            continue
        owner_repo, _ref, major = split_action(action)
        if owner_repo and major is not None:
            pins[owner_repo] = major
    return pins


def _read_workflows(workflow_arg):
    """workflow argümanını (dosya/dizin) dosya-yol→metin sözlüğüne çöz."""
    try:
        paths = resolve_workflows(workflow_arg)
    except ValueError as e:
        print(f"HATA: workflow çözülemedi ({workflow_arg}): {e}", file=sys.stderr)
        return None
    texts = {}
    for p in paths:
        try:
            texts[str(p)] = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"HATA: workflow okunamadı ({p}): {e}", file=sys.stderr)
            return None
    return texts


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW,
                    help="workflow dosyası VEYA dizini (varsayılan: "
                         f"{DEFAULT_WORKFLOW} → içindeki tüm YAML)")
    ap.add_argument("--pins", default=DEFAULT_PINS,
                    help=f"pin dosyası (varsayılan: {DEFAULT_PINS})")
    ap.add_argument("--update", action="store_true",
                    help="mevcut major'ları pin dosyasına yaz (tüm workflow'lar birleşir)")
    ap.add_argument("--bump", action="store_true",
                    help="WARN (upgrade) pin'lerini otomatik yükselt "
                         "(mevcut pin'leri korur, yeni action eklemez, asla düşürmez)")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)

    wf_texts = _read_workflows(args.workflow)
    if wf_texts is None:
        return 2

    if args.update:
        pins = {}
        for text in wf_texts.values():
            pins.update(collect_pins(text))
        try:
            _payload = json.dumps(pins, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            _dir = os.path.dirname(os.path.abspath(args.pins)) or "."
            os.makedirs(_dir, exist_ok=True)
            _fd, _tmp = tempfile.mkstemp(dir=_dir, prefix=os.path.basename(args.pins) + ".tmp.")
            try:
                with os.fdopen(_fd, "w", encoding="utf-8") as _f:
                    _f.write(_payload)
                os.replace(_tmp, args.pins)
            except BaseException:
                try:
                    os.unlink(_tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            print(f"HATA: pin dosyası yazılamadı ({args.pins}): {e}", file=sys.stderr)
            return 2
        print(f"pin dosyası güncellendi: {args.pins} ({len(wf_texts)} workflow)")
        for k in sorted(pins):
            print(f"  {k}: v{pins[k]}")
        return 0

    try:
        pins = load_pins(args.pins)
    except (OSError, ValueError) as e:
        print(f"HATA: pin dosyası okunamadı ({args.pins}): {e}", file=sys.stderr)
        return 2

    # Her workflow ayrı denetlenir; bulgular workflow etiketiyle tek kümede.
    findings = []
    for path, text in wf_texts.items():
        for f in check(text, pins):
            f["workflow"] = path
            findings.append(f)

    if args.bump:
        fails = [f for f in findings if f["verdict"] == "FAIL"]
        if fails:
            print("bump: HAYIR — önce FAIL'leri çöz (downgrade/pin'siz/bozuk ref), "
                  "bump bir düzeltmeyi maskelenemez:", file=sys.stderr)
            for f in fails:
                print(f"  [FAIL] {f['action']} ({f['workflow']}): {f['note']}",
                      file=sys.stderr)
            return 1
        # Yalnızca WARN'ları (workflow major > pin) yükselt — mevcut pin'leri
        # korur, yeni action eklemez, asla düşürmez.
        bumps = {f["action"]: f["major"]
                 for f in findings if f["verdict"] == "WARN" and f["major"]}
        if not bumps:
            print("bump: yükseltilecek pin yok (WARN yok) — pin dosyası değişmedi")
            return 0
        new_pins = dict(pins)
        for action, major in sorted(bumps.items()):
            owner_repo, _ref, _m = split_action(action)
            new_pins[owner_repo] = major
        try:
            _payload = json.dumps(new_pins, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            _dir = os.path.dirname(os.path.abspath(args.pins)) or "."
            os.makedirs(_dir, exist_ok=True)
            _fd, _tmp = tempfile.mkstemp(dir=_dir, prefix=os.path.basename(args.pins) + ".tmp.")
            try:
                with os.fdopen(_fd, "w", encoding="utf-8") as _f:
                    _f.write(_payload)
                os.replace(_tmp, args.pins)
            except BaseException:
                try:
                    os.unlink(_tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            print(f"HATA: pin dosyası yazılamadı ({args.pins}): {e}", file=sys.stderr)
            return 2
        print(f"bump: {len(bumps)} pin yükseltildi → {args.pins}")
        for action in sorted(bumps):
            owner_repo, _ref, _m = split_action(action)
            print(f"  {owner_repo}: v{pins[owner_repo]} → v{bumps[action]}")
        return 0
    fails = [f for f in findings if f["verdict"] == "FAIL"]
    warns = [f for f in findings if f["verdict"] == "WARN"]

    if args.json:
        print(json.dumps({"workflow": args.workflow, "pins": pins,
                          "findings": findings}, indent=2, ensure_ascii=False))
    else:
        print(f"Action pin denetimi (kaynak: {args.workflow})")
        for f in findings:
            tag = {"PASS": "OK  ", "FAIL": "FAIL", "WARN": "WARN",
                   "SKIP": "SKIP"}[f["verdict"]]
            print(f"  [{tag}] {f['action']:<28} {f['note']}")
        print(f"\nSONUÇ: {'FAIL' if fails else 'PASS'} — "
              f"{sum(1 for f in findings if f['verdict'] == 'PASS')} PASS, "
              f"{len(fails)} FAIL, {len(warns)} WARN, "
              f"{sum(1 for f in findings if f['verdict'] == 'SKIP')} SKIP")
        if warns:
            print("Not: WARN bloke etmez; pin'i yükseltmek için `--update` çalıştırın.")
        if fails:
            print("Downgrade/pin'siz action commit'i bloke eder. "
                  "Gerekirse `--update` ile pin'i yeniden üret (önce sürümü doğrula).")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
