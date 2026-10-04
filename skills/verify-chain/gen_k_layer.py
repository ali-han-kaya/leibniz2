#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_k_layer.py — verify-chain skill: yeni K katmanı iskeleti üreticisi.

SKILL.md "Adding a new K-layer" prosedürünün elle yapılan adımlarını
otomatikleştirir: verilen `--name` (flag) + `--label` ile bir SONRAKİ K
numarasını LAYER_LABELS'ten türetir ve şu enjeksiyonları yapar:

  1. verify_delivery.py docstring katman tablosu (K{n} satırı)
  2. klayers_contract.py LAYER_LABELS girişi      ("K{n}": "<label>")
  3. klayers_contract.py OPTIONAL_LAYERS getter'ı ("K{n}": lambda a: a.<name>)
  4. argparse --<name> bayrağı            (--full ile uyumlu help)
  5. apply_full_flags satırı             (args.<name> = True, --full ise)
  6. main() çağrı bloğu                   ([K{n}] <label> — print + report)
  7. check_<name> fonksiyon iskeleti      (TODO gövde — fail-closed add deseni)
  8. SKILL.md K-layer map satırı         (katman haritası senkronu)
  9. test_<name>.py test şablonu         (exit contract + klayers wiring)

HEDEF BÖLÜŞÜ: katman KAYITLARI (2-3) klayers_contract.py'ye yazılır —
klayers.json sözleşmesinin sahibi orasıdır. Üretim/koşum kodu (1, 4-7)
verify_delivery.py'de kalır. İki dosya da anchor'lı olduğu için bu ayrım
zorunludur; yanlış dosyaya yazılan blok sessizce kaybolur.

Güvenlik: yalnızca ANCHOR satırların SONRASINA ekler (deterministik);
anchor yoksa dosyayı DEĞİŞTİRMEZ, hata basar (fail-closed). --dry-run hiçbir
dosyaya dokunmaz, yapılacak enjeksiyonları önizler. K numarası
klayers_contract.LAYER_LABELS'teki en büyük sayının +1'i (tek kaynak);
sayısal atlama yok.

Kullanım:
    python3 gen_k_layer.py --name check_demo --label "Demo katmanı" [--full] [--dry-run]
    python3 gen_k_layer.py --name check_demo --label "Demo" --core   # çekirdek (K0-K7 deseni)
"""
import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
VD_PATH = os.path.join(REPO_ROOT, "_calisma", "CIKTI", "verify_delivery.py")
CONTRACT_PATH = os.path.join(REPO_ROOT, "_calisma", "CIKTI", "klayers_contract.py")
SKILL_PATH = os.path.join(REPO_ROOT, "skills", "verify-chain", "SKILL.md")
CIKTI = os.path.join(REPO_ROOT, "_calisma", "CIKTI")

# Katman kayıtları klayers_contract.py'de yaşar (klayers.json sözleşmesinin
# sahibi) — LAYER_LABELS / OPTIONAL_LAYERS blokları buraya yazılır.
CONTRACT_BLOCKS = ("labels", "optional")

LAYER_LABELS_RE = re.compile(r'"K(\d+)"\s*:')
OPTIONAL_RE = re.compile(r'"K(\d+)"\s*:\s*lambda')

# ── Anchor'lar: enjeksiyon noktaları (deterministik, sonrasına eklenir) ──
# DİKKAT: anchor TAM SATIR olmalı, ifadenin ilk yarısı değil. Çok satıra
# yayılan yapılarda (docstring tablosu, add_argument, çift satırlı print,
# fonksiyon gövdesi) ilk yarıya enjeksiyon ifadeyi BÖLER (geçmiş hatalar).
# Her anchor, hedef bloğun SON satırının TAM metnidir.
ANCHOR_DOCSTRING_LAST = "  K21 SDE       sde_determinism_experiment.py donmuş kayıt + skill protokolü (--check-sde; --full'a DAHİL)"  # K21 docstring son satırı
ANCHOR_LABELS_LAST = '    "K21": "SDE determinism guard",'
ANCHOR_OPTIONAL_LAST = '    "K21": lambda a: getattr(a, "check_sde", False),'
# --check-sde add_argument çağrısının SON satırı (help metni çok satırlı).
ANCHOR_ARGPARSE_LAST = '                         "skill protokolünü fail-closed doğrula")'
ANCHOR_FULL_LAST = "args.check_sde = True"
# K21 main print'i iki satıra yayılır (json/stdout ayrımı) — anchor TAM
# ikinci satır olmalı.
ANCHOR_MAIN_LAST = "              file=(sys.stderr if args.json else sys.stdout))"
# check_sde_determinism fonksiyonunun SONU (finally + rmtree ikilisi) —
# def satırına enjeksiyon gövdeyi böler.
ANCHOR_CHECK_LAST = "    finally:\n        shutil.rmtree(tmp, ignore_errors=True)"
ANCHOR_SKILL_LAST = "| K21 | SDE determinism guard"


def next_k(contract_text):
    """LAYER_LABELS'teki en büyük K numarasının +1'ini bulur.

    Beklenen girdi klayers_contract.py metnidir (kayıtların sahibi)."""
    nums = [int(m) for m in LAYER_LABELS_RE.findall(contract_text)]
    if not nums:
        raise SystemExit("LAYER_LABELS bulunamadı — klayers_contract.py yapısı değişmiş")
    return max(nums) + 1


def insert_after(text, anchor, block):
    """anchor'ın TAMAMINDAN sonraki satıra block'u ekler; anchor yoksa None.

    Çok satırlı anchor'larda (finally + rmtree ikilisi gibi) ilk yeni satırı
    değil, anchor metninin BİTİMİNDEN sonraki yeni satırı bulur — yoksa
    enjeksiyon `finally:` ile gövdesi arasına girer (geçmiş IndentationError).
    """
    idx = text.find(anchor)
    if idx == -1:
        return None
    nl = text.find("\n", idx + len(anchor))
    if nl == -1:
        return None
    return text[:nl + 1] + block + text[nl + 1:]


def build_blocks(k, name, label, full):
    """Tüm enjeksiyon bloklarını üretir: {etiket: (anchor, blok)}."""
    key = f"K{k}"
    # --name 'check_demo' → args attribute'u + fonksiyon 'check_demo'
    # (check_ öneki yalnızca bir kez), argparse bayrağı '--check-demo'.
    flag = name                      # args attribute'u: a.check_demo
    flag_dash = name.replace("_", "-")  # argparse: --check-demo
    fn = name                        # fonksiyon: check_demo
    full_note = "--full'a DAHİL" if full else "--full'a dahil DEĞİL"
    help_note = "'--full ile otomatik'" if full else "'bağımsız'"
    status_lit = "PASS" if full else "PASS/FAIL"
    var = flag.replace("-", "_")
    return {
        "docstring": (ANCHOR_DOCSTRING_LAST,
                      f"  {key} {label.upper()[:1] + label[1:]} {label} "
                      f"(--{flag_dash}; {full_note})\n"),
        "labels": (ANCHOR_LABELS_LAST,
                   f'    "{key}": "{label}",\n'),
        "optional": (ANCHOR_OPTIONAL_LAST,
                     f'    "{key}": lambda a: a.{flag},\n'),
        "argparse": (ANCHOR_ARGPARSE_LAST,
                     f'    ap.add_argument("--{flag_dash}", action="store_true",\n'
                     f'                    help="{key}: {label} ({help_note})")\n'),
        "full": (ANCHOR_FULL_LAST,
                 f'    args.{flag} = True\n'),
        "main": (ANCHOR_MAIN_LAST,
                 f'    if args.{flag}:\n'
                 f'        {var}_ok, {var}_detail = {fn}(add)\n'
                 f'        if not args.json:\n'
                 f'            print(f"[{key}] {label}: {status_lit} — {{{var}_detail}}")\n'),
        "check": (ANCHOR_CHECK_LAST,
                  f'\n\ndef {fn}(add):\n'
                  f'    """{key}: {label} (fail-closed iskelet — TODO gövde).\n\n'
                  f'    SKILL.md "Adding a new K-layer" adım 2: (ok, detail) döndür,\n'
                  f'    bulguları shared add(priority, id, label, issue, evidence) ile\n'
                  f'    ekle; bulgu id deseni "{key}-<CHECK>". Döndürür (ok, detail).\n'
                  f'    """\n'
                  f'    # TODO: gerçek denetimi uygula; ihlal → P0/P1 + ok=False.\n'
                  f'    return True, f"{key} iskelet — uygulanmadı (TODO)"\n'),
        "skill": (ANCHOR_SKILL_LAST,
                  f'| {key} | {label} | `--{flag_dash}` | {"yes" if full else "no"} |\n'),
    }


def gen_test_template(k, name, label, full):
    """test_<name>.py şablonunu üretir (exit contract + klayers wiring)."""
    flag = name                     # args attribute'u
    fn = name                       # fonksiyon
    key = f"K{k}"
    if full:
        full_block = (
            "    def test_full_enables(self):\n"
            "        self.assertTrue(vd.apply_full_flags("
            "_ns(full=True))." + fn + ")\n"
        )
    else:
        full_block = ""
    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{name}.py — {key} ({label}) iskelet testleri (gen_k_layer.py şablonu).

Skill prosedürü adım 5: exit contract (P0/P1/INFO), pozitif + negatif senaryo,
fail-closed kanıt (kurcalanmış girdi MUTLAKA bulgu üretmeli). TODO: gerçek
denetimin semantiğine göre doldur.
"""
import os
import sys
import unittest

CIKTI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CIKTI)
import klayers_contract as kc  # noqa: E402
import verify_delivery as vd  # noqa: E402


def _ns(**kw):
    import argparse
    ns = argparse.Namespace(
        symbolic_proof=False, lean_proof=False, verify_manifest=None,
        check_config_drift=False, check_plist=False, check_repro_manifest=False,
        check_cleanup=False, check_history=None, check_github_scripts=False,
        check_mirror=False, check_daemon=False, coq_proof=False,
        check_launchd=False, check_sde=False, {fn}=False)
    for k_, v in kw.items():
        setattr(ns, k_, v)
    return ns


class Test{key}Wiring(unittest.TestCase):
    def test_layer_label(self):
        self.assertEqual(kc.LAYER_LABELS["{key}"], "{label}")

    def test_optional_getter(self):
        self.assertTrue(kc.OPTIONAL_LAYERS["{key}"](_ns(**{{"{fn}": True}})))
        self.assertFalse(kc.OPTIONAL_LAYERS["{key}"](_ns()))

{full_block}    def test_klayers_pass(self):
        self.assertEqual(vd.build_layers_summary(_ns(**{{"{fn}": True}}), [])
                         ["{key}"]["status"], "PASS")

    def test_klayers_fail_on_finding(self):
        findings = [{{"priority": "P0", "id": "{key}-TODO",
                      "check": "{key} {label}", "message": "x", "detail": "y"}}]
        self.assertEqual(vd.build_layers_summary(_ns(**{{"{fn}": True}}), findings)
                         ["{key}"]["status"], "FAIL")


class TestCheck{key.replace('K','')}(unittest.TestCase):
    def test_pass(self):
        findings = []
        ok, detail = vd.{fn}(lambda *a: findings.append(a))
        self.assertTrue(ok, detail)
        self.assertEqual(findings, [])

    # TODO: negatif senaryo — kurcalanmış girdi P0/P1 üretmeli (fail-closed).


if __name__ == "__main__":
    unittest.main()
'''


def apply(blocks, vd_text, contract_text, skill_text):
    """Blokları hedef dosyalara enjekte et → (vd, contract, skill, log).

    Anchor bulunamazsa blok ATLANIR ve log'a hedef dosyayı SAYARAK düşer;
    dosya yine de yazılır (fail-closed: yarım katman sessizce kaybolmasın
    diye çağıran `!! ` satırlarını görmek zorunda)."""
    targets = {"klayers_contract.py": contract_text,
               "verify_delivery.py": vd_text,
               "SKILL.md": skill_text}
    changes = []
    for label, (anchor, block) in blocks.items():
        if label == "skill":
            target = "SKILL.md"
        elif label in CONTRACT_BLOCKS:
            target = "klayers_contract.py"
        else:
            target = "verify_delivery.py"
        text = targets[target]
        if anchor not in text:
            changes.append(f"  !! {label}: ANCHOR bulunamadı ({target}) — "
                           f"ATLANDI: {anchor!r}")
            continue
        targets[target] = insert_after(text, anchor, block)
        changes.append(f"  + {label}: K-enjeksiyon OK ({target})")
    return (targets["verify_delivery.py"], targets["klayers_contract.py"],
            targets["SKILL.md"], changes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="flag adı (check_demo → --check-demo)")
    ap.add_argument("--label", required=True, help="katman etiketi (LAYER_LABELS değeri)")
    ap.add_argument("--full", action="store_true",
                    help="--full'a dahil et (apply_full_flags + SKILL.md 'yes')")
    ap.add_argument("--core", action="store_true",
                    help="çekirdek katman (docstring + LAYER_LABELS + test; "
                         "OPTIONAL/flag/full/main atlanır)")
    ap.add_argument("--dry-run", action="store_true",
                    help="hiçbir dosyaya dokunma; enjeksiyonları önizle")
    ap.add_argument("--vd-path", default=VD_PATH)
    ap.add_argument("--contract-path", default=CONTRACT_PATH)
    ap.add_argument("--skill-path", default=SKILL_PATH)
    args = ap.parse_args(argv)

    if not args.name.startswith("check_"):
        raise SystemExit("HATA: --name 'check_<isim>' olmalı (örn. check_demo)")
    if args.core and args.full:
        raise SystemExit("HATA: --core ve --full birlikte kullanılamaz")

    with open(args.vd_path, encoding="utf-8") as f:
        vd_text = f.read()
    with open(args.contract_path, encoding="utf-8") as f:
        contract_text = f.read()
    with open(args.skill_path, encoding="utf-8") as f:
        skill_text = f.read()

    k = next_k(contract_text)
    blocks = build_blocks(k, args.name, args.label, args.full)
    if args.core:
        blocks = {l: b for l, b in blocks.items() if l in ("docstring", "labels")}

    print(f"K{ k } ({args.label}) — name={args.name} "
          f"{'--full' if args.full else ('--core' if args.core else 'bağımsız')} "
          f"{'[DRY-RUN]' if args.dry_run else ''}")
    new_vd, new_contract, new_skill, changes = apply(
        blocks, vd_text, contract_text, skill_text)
    for c in changes:
        print(c)

    tpl = gen_test_template(k, args.name, args.label, args.full)
    # Test şablonu verify_delivery'nin yanına gider; --vd-path verilmişse
    # (kopya üzerinde prova) şablon da o dizine yazılır — gerçek repo'ya
    # dokunmaz.
    tpl_dir = os.path.dirname(args.vd_path) if args.vd_path != VD_PATH \
        else CIKTI
    tpl_path = os.path.join(tpl_dir, f"test_{args.name}.py")
    print(f"  + test: {tpl_path} ({len(tpl.splitlines())} satır şablon)")
    print(f"  + test: SKILL.md 'run summary PASS/FAIL/SKIP' + pre-commit + CI "
          f"(prosedür adım 4/6 — elle)")

    if args.dry_run:
        print("  [dry-run] dosyalar değiştirilmedi")
        return 0
    with open(args.vd_path, "w", encoding="utf-8") as f:
        f.write(new_vd)
    with open(args.contract_path, "w", encoding="utf-8") as f:
        f.write(new_contract)
    with open(args.skill_path, "w", encoding="utf-8") as f:
        f.write(new_skill)
    with open(tpl_path, "w", encoding="utf-8") as f:
        f.write(tpl)
    print(f"  ✓ yazıldı: {args.vd_path}, {args.contract_path}, "
          f"{args.skill_path}, {tpl_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
