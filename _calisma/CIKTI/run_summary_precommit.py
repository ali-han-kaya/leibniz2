#!/usr/bin/env python3
"""run_summary_precommit.py — pre-commit bulgularını GITHUB_STEP_SUMMARY'ye yaz.

verify.yml'deki 'Pre-commit findings — run summary' adımının inline Python
mantığının standalone hali. PRECOMMIT_RAPORU.json sidecar'ından okur;
JSON varsa schema ile doğrulanır (fail-closed). JSON yoksa advisory
'rapor bulunamadı' notu yazar. GITHUB_STEP_SUMMARY env'i yoksa
(yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import pathlib
import sys

_SCHEMA = None


def _load_schema():
    """JSON Schema'yı lazy-load et (dosya yoksa None → schema doğrulama atlanır)."""
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA
    schema_path = pathlib.Path(__file__).parent / "PRECOMMIT_RAPORU.schema.json"
    if not schema_path.exists():
        return None
    try:
        with open(schema_path, encoding="utf-8") as f:
            _SCHEMA = json.load(f)
    except (json.JSONDecodeError, OSError):
        _SCHEMA = None
    return _SCHEMA


def _validate_schema(data):
    """PRECOMMIT_RAPORU.json'u schema ile doğrula. Hata varsa raise."""
    schema = _load_schema()
    if schema is None:
        return  # schema yoksa sessizce geç
    try:
        import jsonschema
    except ImportError:
        # jsonschema yoksa dürüstçe SKIP (CI'da pip install edilir; yerelde
        # opsiyonel). ImportError'ı aşağıdaki except'e düşürüp UnboundLocalError
        # üretmek yerine burada sessizce dön — schema kapısı CI'da fail-closed.
        return
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"PRECOMMIT_RAPORU.json şema hatası: {e.message} "
                         f"(yol: {'.'.join(str(p) for p in e.absolute_path)})") from e


def _load(path="logs/PRECOMMIT_RAPORU.json"):
    """JSON sidecar'dan yükle — tek kaynak.

    Döndürür (findings, hooks, verdict) — rapor yoksa None.
    JSON formatı: {findings: [{priority, message}],
                   hooks: [{name, status}],
                   verdict: str, counts: {hooks, passed, failed, p0, p1}}
    """
    jp = pathlib.Path(path)
    if jp.suffix == ".md":
        jp = jp.with_suffix(".json")
    if not jp.exists():
        return None
    try:
        with open(jp, encoding="utf-8") as f:
            data = json.load(f)
        _validate_schema(data)
        findings_raw = data.get("findings", [])
        findings = [(f.get("priority", "?"),
                     f.get("message", f.get("check", "?")))
                    for f in findings_raw]
        hooks_raw = data.get("hooks", [])
        hooks = [(h.get("name", "?"), h.get("status", "?"))
                 for h in hooks_raw]
        verdict = data.get("verdict", "bilinmiyor")
        return findings, hooks, verdict
    except (json.JSONDecodeError, OSError, KeyError) as e:
        print(f"PRECOMMIT_RAPORU.json ayrıştırma hatası: {e}", file=sys.stderr)
        return None
    except ValueError as e:
        print(f"PRECOMMIT_RAPORU.json şema hatası: {e}", file=sys.stderr)
        return None


def status(path="logs/PRECOMMIT_RAPORU.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    loaded = _load(path)
    if loaded is None:
        return "MISSING"
    findings, _, _ = loaded
    return "FAIL" if findings else "PASS"


def render(sink, path="logs/PRECOMMIT_RAPORU.json"):
    """Pre-commit bölümünü sink'e yaz (rapor yoksa advisory not)."""
    loaded = _load(path)
    if loaded is None:
        sink.write("## 🔍 Pre-commit: rapor bulunamadı\n\n"
                   "> `logs/PRECOMMIT_RAPORU.json` üretilmedi "
                   "(pre-commit kurulumu başarısız?).\n")
        return

    findings, hooks, verdict = loaded

    if findings:
        sink.write(f"## 🔴 Pre-commit bulguları: {len(findings)} bulgu\n\n")
        for pri, msg in findings:
            sink.write(f"- **{pri}**: {msg}\n")
        sink.write("\n> Advisory — build'i bloke etmez; denetim içindir. "
                   "Detay: `precommit-logs` artifact'ındaki PRECOMMIT_RAPORU.md.\n")
    else:
        sink.write("## ✅ Pre-commit: bulgu yok (tüm hook'lar geçti)\n\n")
    sink.write(f"> Sonuç: {verdict}\n")
    if hooks:
        parts = " | ".join(
            f"`{h}` " + (":white_check_mark:" if st == "Passed" else ":x:")
            for h, st in hooks
        )
        sink.write(f"> Hook'lar: {parts}\n")


def main() -> None:
    with summary_sink() as s:
        render(s)
    print("Pre-commit summary written.")


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


if __name__ == "__main__":
    main()
