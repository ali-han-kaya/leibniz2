#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_gate_registry.py — `gate_registry.yaml` ↔ gerçek kapılar (iki yönlü,
READ-ONLY) doğrulayıcı. Faz 1: yalnız denetim; üretim/yeniden yazma YOKTUR.

Neden (ölçülen kök neden): "bu kapı koştu ve geçti" tek bir olgu ama bugün
verifier katmanları (K0-K21), CI job'ları (verify.yml), pre-commit hook'ları
(.pre-commit-config.yaml) ve doküman/test kayıtları AYRI ayrı tutuluyor.
`gate_registry.yaml` her kapıyı tek yerde ADLANDIRIR; bu betik beyanla
gerçeğin birebir örtüştüğünü iki yönde de kanıtlar:

  kayıt → gerçek : kayıttaki her id gerçekten var mı?  (phantom kayıt = FAIL)
  gerçek → kayıt : gerçek her kapı kayıtta var mı?     (kapsamsız kapı = FAIL)
  alan           : severity/platform/stage/label/blocking beyanı türetimle
                   aynı mı? (kayıt bir DEKLARASYONdur; türetim tek kaynaktır)

Türetim kaynakları (hepsi salt-okunur):
  * CI job'ları      : `.github/workflows/verify.yml`
                       severity = GATE_EXCLUDE + `if:` (status_checks ile aynı
                       sözleşme; kendi kategorizasyonunu YENİDEN İCAT ETMEZ)
                       platform = `runs-on` (ubuntu→linux, macos→macos)
  * pre-commit       : `.pre-commit-config.yaml` (stages; yoksa pre-commit)
  * K katmanları     : `_calisma/CIKTI/verify_delivery.py` içindeki
                       `LAYER_LABELS` / `_CORE_LAYERS` — modül İMPORT EDİLMEZ
                       (5997 satır + yan etkiler); `ast` ile yalnız literal
                       tablolar okunur.

Read-only sözleşmesi: bu betik hiçbir dosyaya YAZMAZ (açık yazma yok,
yeniden üretim yok). `test_check_gate_registry.py` kaynak dosyaların
sha256 + mtime'ının koşu öncesi/sonrası aynı kaldığını ölçer.

Fail-closed: eksik dosya / bozuk YAML / boş türetim / tanınmayan `runs-on`
→ exit 2 (sessiz PASS yok). Sessiz daralma da FAIL sayılır: kayıt boşsa ya da
bir bölüm tamamen boşsa "iki yön de boş" diye yeşil görünmesin.

Kullanım:
  python3 _calisma/CIKTI/check_gate_registry.py            # denetle
  python3 _calisma/CIKTI/check_gate_registry.py --json     # makine-okur

Exit: 0 = iki yön de birebir; 1 = drift/şema bulgusu; 2 = ölçüm imkânsız.
"""
import argparse
import ast
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REPO = _HERE.parent.parent
REGISTRY = "_calisma/CIKTI/gate_registry.yaml"
WORKFLOW = ".github/workflows/verify.yml"
PRECOMMIT = ".pre-commit-config.yaml"
DELIVERY = "_calisma/CIKTI/verify_delivery.py"

SECTIONS = ("ci_jobs", "hooks", "layers")
JOB_FIELDS = frozenset({"severity", "platform", "note"})
HOOK_FIELDS = frozenset({"stage", "note"})
LAYER_FIELDS = frozenset({"label", "blocking", "note"})
REQUIRED = {
    "ci_jobs": ("severity", "platform"),
    "hooks": ("stage",),
    "layers": ("label", "blocking"),
}
ENUMS = {
    "severity": frozenset({"required", "advisory", "pr_only"}),
    "platform": frozenset({"linux", "macos"}),
    "stage": frozenset({"pre-commit", "commit-msg"}),
}
FIELDS = {"ci_jobs": JOB_FIELDS, "hooks": HOOK_FIELDS, "layers": LAYER_FIELDS}

# Yön etiketleri raporun okunmasını kolaylaştırır; testler bunlara bağlanır.
DIR_REGISTRY_TO_REALITY = "kayıt→gerçek"
DIR_REALITY_TO_REGISTRY = "gerçek→kayıt"


class MeasurementError(RuntimeError):
    """Ölçüm imkânsız (dosya yok, YAML bozuk, türetim kör) — exit 2."""


def _read_text(root, rel):
    path = pathlib.Path(root) / rel
    if not path.is_file():
        raise MeasurementError(f"kaynak yok: {rel}")
    return path.read_text(encoding="utf-8")


def _load_yaml(root, rel, label):
    import yaml  # yerel import: yoksa çağıran yakalar (exit 2)

    try:
        data = yaml.safe_load(_read_text(root, rel))
    except ImportError as exc:  # pragma: no cover — PyYAML'sız ortam
        raise MeasurementError(f"PyYAML yok ({exc}) — venv python kullanın")
    except MeasurementError:
        raise
    except Exception as exc:
        raise MeasurementError(f"{label} ayrıştırılamadı ({rel}): {exc}")
    if not isinstance(data, dict):
        raise MeasurementError(f"{label} beklenen eşleme değil ({rel})")
    return data


def _platform(runs_on):
    """`runs-on` → platform enum. Tanınmayan değer sessizce 'linux' olmaz."""
    if isinstance(runs_on, list):
        values = [str(v) for v in runs_on]
    else:
        values = [str(runs_on)]
    for value in values:
        if value.startswith("ubuntu"):
            return "linux"
        if value.startswith("macos"):
            return "macos"
    raise MeasurementError(f"tanınmayan runs-on: {runs_on!r}")


def _derive_jobs(root):
    """verify.yml job'ları → severity (GATE_EXCLUDE + if:) + platform."""
    import workflow_contract as wc  # tek kaynak: required dışlama listesi

    data = _load_yaml(root, WORKFLOW, "verify.yml")
    jobs = data.get("jobs") or {}
    if not jobs:
        raise MeasurementError("verify.yml'de job yok — türetim kör")
    excluded = set(wc.GATE_EXCLUDE)
    derived = {}
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            raise MeasurementError(f"job '{jid}' eşleme değil")
        condition = str(job.get("if", ""))
        if jid in excluded:
            severity = ("pr_only"
                        if "github.event_name == 'pull_request'" in condition
                        else "advisory")
        else:
            severity = "required"
        derived[jid] = {"severity": severity,
                        "platform": _platform(job.get("runs-on"))}
    return derived


def _derive_hooks(root):
    """pre-commit hook id'leri → stage (stages yoksa pre-commit)."""
    data = _load_yaml(root, PRECOMMIT, ".pre-commit-config.yaml")
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        raise MeasurementError("pre-commit `repos` liste değil")
    derived, seen = {}, set()
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        for hook in repo.get("hooks") or []:
            if not isinstance(hook, dict) or "id" not in hook:
                continue
            hid = str(hook["id"])
            if hid in seen:
                raise MeasurementError(f"pre-commit hook id yineleniyor: {hid}")
            seen.add(hid)
            stages = hook.get("stages")
            stage = (str(stages[0]) if isinstance(stages, list) and stages
                     else "pre-commit")
            derived[hid] = {"stage": stage}
    if not derived:
        raise MeasurementError("hiç pre-commit hook bulunamadı — türetim kör")
    return derived


def _literal(node, label):
    try:
        return ast.literal_eval(node)
    except Exception as exc:
        raise MeasurementError(f"{label} literal olarak okunamadı: {exc}")


def _derive_layers(root):
    """verify_delivery.py → LAYER_LABELS + _CORE_LAYERS (modül import EDİLMEZ)."""
    source = _read_text(root, DELIVERY)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise MeasurementError(f"verify_delivery.py ayrıştırılamadı: {exc}")
    labels = core = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", None)
        if name == "LAYER_LABELS":
            labels = _literal(node.value, "LAYER_LABELS")
        elif name == "_CORE_LAYERS":
            value = node.value
            # `_CORE_LAYERS = frozenset({"K0", ...})` — çağrının argümanı literal.
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            core = _literal(value, "_CORE_LAYERS")
    if not isinstance(labels, dict) or not labels:
        raise MeasurementError("LAYER_LABELS bulunamadı/boş — türetim kör")
    if not isinstance(core, (set, frozenset)):
        raise MeasurementError("_CORE_LAYERS bulunamadı — türetim kör")
    derived = {}
    for layer, label in labels.items():
        if not isinstance(layer, str) or not layer.startswith("K"):
            raise MeasurementError(f"katman adı beklenmedik: {layer!r}")
        derived[layer] = {"label": str(label), "blocking": layer in core}
    return derived


def derive(root=REPO):
    """Üç kaynaktan gerçek kapı kümesini türet (salt-okunur)."""
    return {"ci_jobs": _derive_jobs(root),
            "hooks": _derive_hooks(root),
            "layers": _derive_layers(root)}


def load_registry(root=REPO):
    return _load_yaml(root, REGISTRY, "gate_registry.yaml")


def _schema_findings(registry):
    """Kaydın kendi şekli: yanlış bölüm/alan/adda sessiz geçiş olmamalı."""
    findings = []
    version = registry.get("version")
    if version != 1:
        findings.append({"kind": "schema", "section": "-", "id": "-",
                         "detail": f"version 1 olmalı, kayıt: {version!r}"})
    unknown = sorted(set(registry) - {"version", *SECTIONS})
    for key in unknown:
        findings.append({"kind": "schema", "section": key, "id": "-",
                         "detail": f"bilinmeyen üst düzey anahtar: {key!r}"})
    for section in SECTIONS:
        entries = registry.get(section)
        if not isinstance(entries, dict) or not entries:
            findings.append({"kind": "schema", "section": section, "id": "-",
                             "detail": "bölüm yok/boş (fail-closed: boş bölüm "
                                       "iki yönü de boş gösterir)"})
            continue
        for gid, entry in entries.items():
            if not isinstance(entry, dict):
                findings.append({"kind": "schema", "section": section,
                                 "id": gid, "detail": "girdi eşleme değil"})
                continue
            for field in sorted(set(entry) - FIELDS[section]):
                findings.append({"kind": "schema", "section": section,
                                 "id": gid,
                                 "detail": f"bilinmeyen alan: {field!r}"})
            for field in REQUIRED[section]:
                if field not in entry:
                    findings.append({"kind": "schema", "section": section,
                                     "id": gid,
                                     "detail": f"zorunlu alan eksik: {field}"})
            for field, allowed in ENUMS.items():
                if field in entry and entry[field] not in allowed:
                    findings.append({
                        "kind": "schema", "section": section, "id": gid,
                        "detail": f"{field}={entry[field]!r} geçersiz "
                                  f"(izinli: {sorted(allowed)})"})
            if "blocking" in entry and not isinstance(entry["blocking"], bool):
                findings.append({"kind": "schema", "section": section,
                                 "id": gid,
                                 "detail": "blocking bool olmalı"})
            if "note" in entry and not isinstance(entry["note"], str):
                findings.append({"kind": "schema", "section": section,
                                 "id": gid, "detail": "note str olmalı"})
    return findings


def _diff(registry, derived):
    """İki yönlü küme farkı + ortak id'lerde alan karşılaştırması."""
    findings = []
    for section in SECTIONS:
        reg = registry.get(section) or {}
        if not isinstance(reg, dict):
            continue  # şema bulgusu zaten raporlandı
        real = derived[section]
        for gid in sorted(set(reg) - set(real)):
            findings.append({"kind": "phantom",
                             "direction": DIR_REGISTRY_TO_REALITY,
                             "section": section, "id": gid,
                             "detail": "kayıtta var, gerçekte YOK"})
        for gid in sorted(set(real) - set(reg)):
            findings.append({"kind": "unregistered",
                             "direction": DIR_REALITY_TO_REGISTRY,
                             "section": section, "id": gid,
                             "detail": "gerçekte var, kayıtta YOK"})
        for gid in sorted(set(reg) & set(real)):
            entry = reg[gid]
            if not isinstance(entry, dict):
                continue
            for field, value in real[gid].items():
                if field not in entry:
                    continue  # zorunlu alan eksikliği şema bulgusunda
                if entry[field] != value:
                    findings.append({
                        "kind": "field", "section": section, "id": gid,
                        "field": field, "registry": entry[field],
                        "derived": value,
                        "detail": f"{field}: kayıt={entry[field]!r} "
                                  f"türetim={value!r}"})
    return findings


def check(root=REPO):
    """Tüm sözleşmeyi denetle — (derived, registry, findings) döndür."""
    derived = derive(root)
    registry = load_registry(root)
    findings = _schema_findings(registry)
    findings.extend(_diff(registry, derived))
    return derived, registry, findings


def counts(derived):
    return {section: len(derived[section]) for section in SECTIONS}


def format_report(derived, findings):
    c = counts(derived)
    lines = [
        "check-gate-registry: kayıt ↔ gerçek kapılar (iki yönlü, read-only)",
        f"  türetim: ci_jobs={c['ci_jobs']}  hooks={c['hooks']}  "
        f"layers={c['layers']}",
    ]
    if findings:
        lines.append("FAIL — kapı kaydı drift'i:")
        for f in findings:
            if f["kind"] == "field":
                lines.append(f"  • [alan] {f['section']}.{f['id']}: "
                             f"{f['detail']}")
            elif f["kind"] in ("phantom", "unregistered"):
                lines.append(f"  • [{f['direction']}] {f['section']}: "
                             f"{f['id']} — {f['detail']}")
            else:
                lines.append(f"  • [şema] {f['section']}.{f['id']}: "
                             f"{f['detail']}")
        lines.append("  Remediy: kaydı gerçekle eşitle (ekle/sil/alanı düzelt) "
                     "ya da gerçek kapıyı düzelt — kapı kendini onarmaz.")
    else:
        lines.append("PASS — kayıt iki yönde de birebir")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO),
                    help="repo kökü (varsayılan: script konumu)")
    ap.add_argument("--json", action="store_true", help="makine-okur çıktı")
    args = ap.parse_args(argv)

    try:
        derived, _registry, findings = check(pathlib.Path(args.root))
    except MeasurementError as exc:
        if args.json:
            print(json.dumps({"verdict": "ERROR", "error": str(exc)},
                             ensure_ascii=False, indent=2))
        else:
            print(f"check-gate-registry: ÖLÇÜM İMKÂNSIZ — {exc}",
                  file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "verdict": "FAIL" if findings else "PASS",
            "counts": counts(derived),
            "findings": findings,
        }, ensure_ascii=False, indent=2))
        return 1 if findings else 0

    print(format_report(derived, findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
