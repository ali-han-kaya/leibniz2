#!/usr/bin/env python3
"""run_summary_k9.py — K9 lake build logunu GITHUB_STEP_SUMMARY'ye yazar.

verify.yml'deki "Run Lean lake build (K5-K11 separate step)" adımı
`verify_lean_lake.sh` çıktısını `tee lean_lake_build.log` ile dosyaya yazar;
bu modül AYNI dosyayı (tek kaynak) okuyup run summary'ye "K9 lake build"
bölümünü ve durum panosuna ✅/🔴/⚠️ satırını taşır.

Durum sözleşmesi (fail-closed):
  - log yok                                      → MISSING (⚠️ advisory not)
  - log `[K9-LAKE] PASS` içeriyor                → PASS
  - log `[K9-LAKE] FAIL` içeriyor                → FAIL
  - log var ama hiçbir verdict yok (timeout/     → FAIL (derleme yarım
    kesilmiş tee çıktısı)                          kalmış sayılır — PASS asla)

NOT: Bu bölüm `verify_delivery` K9'unu (klayers.json `lean_proof`) DEĞİL,
ayrı fail-closed lake adımının kendi çıktısını gösterir ("lake-proof job
ayrıca bağımsız kapıdır" — verify.yml K9 kurulum yorumu).

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import os
import sys


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def _read(path="lean_lake_build.log"):
    """Log yoksa None; varsa metin (tek kaynak okuma)."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _verdict(text):
    """'PASS' | 'FAIL' — işaretlerden fail-closed verdict."""
    if "[K9-LAKE] PASS" in text:
        return "PASS"
    return "FAIL"


def status(path="lean_lake_build.log"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    text = _read(path)
    if text is None:
        return "MISSING"
    return _verdict(text)


def render(sink, path="lean_lake_build.log"):
    """K9 lake build bölümünü sink'e yaz (log yoksa advisory not)."""
    text = _read(path)
    if text is None:
        sink.write("## ⚠️ K9 lake build: log bulunamadı\n\n"
                   "> `lean_lake_build.log` üretilemedi "
                   "(verify job'unun lake adımı hiç çalışmadı mı?).\n")
        return "MISSING"
    markers = [ln for ln in text.splitlines() if "[K9-LAKE]" in ln]
    if _verdict(text) == "PASS":
        sink.write("## ✅ K9 lake build: PASS\n\n")
        sink.write("> `verify_lean_lake.sh` — `lake clean && lake build "
                   "--wfail` tamamlandı.\n\n")
        for ln in markers:
            sink.write(f"- `{ln.strip()}`\n")
        sink.write("\n")
    else:
        sink.write("## 🔴 K9 lake build: FAIL\n\n")
        if markers:
            for ln in markers:
                sink.write(f"- `{ln.strip()}`\n")
            sink.write("\n")
        has_verdict = ("[K9-LAKE] PASS" in text or "[K9-LAKE] FAIL" in text)
        if not has_verdict:
            sink.write("> Log var ama `[K9-LAKE]` verdict işareti yok — "
                       "derleme yarım kaldı (timeout/kesilme). Fail-closed: "
                       "verdict yoksa PASS sayılmaz.\n\n")
        # Hata ipuçları: ilk FAIL/error satırları (en fazla 12).
        clues = [ln for ln in text.splitlines()
                 if "error" in ln.lower() or "failed" in ln.lower()]
        if clues:
            sink.write("Son hata satırları:\n\n```\n")
            for ln in clues[:12]:
                sink.write(ln.rstrip() + "\n")
            sink.write("```\n\n")
    return _verdict(text)


def main() -> None:
    with summary_sink() as s:
        verdict = render(s)
    print(f"K9 lake build summary written ({verdict}).")


if __name__ == "__main__":
    main()
