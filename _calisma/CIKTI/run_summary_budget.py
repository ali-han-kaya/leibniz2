#!/usr/bin/env python3
"""run_summary_budget.py — bütçe kalkanı sonucunu GITHUB_STEP_SUMMARY'ye yaz.

İki girdi şeklini destekler:

1. Aggregated: `budget/index.json` (consolidate_budget.py çıktısı)
   `{failures[], runs[], method, cli_overrides}` — budget job'unda koşar.
2. Single-run: `budget_verify.json` (verify_delivery.py --budget-out çıktısı)
   `{limit, estimated_usd, tokens_est, verdict, method, comparison, ...}` —
   verify job'unda koşar (aynı job'un kendi bütçe sonucu; aggregation
   gerektirmez). Böylece verify job'unun GITHUB_STEP_SUMMARY'si pre-commit +
   K0 + bütçe bölümlerini TEK summary'de birleştirir.

İlk konumsal argüman girdi yolu; yoksa varsayılan `budget/index.json`.
GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import sys

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")
DEFAULT_PATH = "budget/index.json"


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def _normalize(summary):
    """Aggregated ve single-run şeklini ortak {failures, runs} yapısına indir.

    Single-run şeklinde `verdict == "FAIL"` ise tek failure olarak sayılır;
    `verdict == "OK"` ise tek run olarak sayılır. `source` verify job'unun
    kendi bütçesi olduğundan "verify" sabittir.
    """
    if "runs" in summary or "failures" in summary:
        return summary.get("failures", []), summary.get("runs", [])

    # single-run: budget_verify.json (verify_delivery.py --budget-out)
    run = {
        "source": summary.get("source", "verify"),
        "limit": summary.get("limit"),
        "estimated_usd": summary.get("estimated_usd"),
        "tokens_est": summary.get("tokens_est"),
    }
    if summary.get("verdict") == "FAIL":
        return [run], []
    return [], [run]


def render(sink, path=DEFAULT_PATH):
    """Bütçe bölümünü sink'e yaz (aggregated veya single-run şekli)."""
    if not os.path.isfile(path):
        sink.write("## ⚠️ Bütçe kalkanı: sidecar bulunamadı "
                   f"(`{path}` — verify job'u çalışmadı?)\n")
        return

    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    failures, runs = _normalize(summary)

    if failures:
        sink.write("## ⚠️ Bütçe limiti aşıldı\n\n")
        for f in failures:
            src = f.get("source") or "bilinmeyen"
            lim = f.get("limit")
            est = f.get("estimated_usd")
            tok = f.get("tokens_est")
            over = round((est or 0) - (lim or 0), 2)
            sink.write(f"- **{src}**: ${est} / ${lim} limiti "
                       f"(+${over} aşım, ~{tok} token)\n")
        sink.write(f"\n> Yöntem: `{summary.get('method', '')}`. "
                   f"Fail-closed: P1 bulgusu olarak işaretlendi.\n")
    else:
        total = round(sum(r.get("estimated_usd", 0) or 0 for r in runs), 2)
        sink.write("## ✅ Bütçe kalkanı: limit içinde\n\n")
        for r in runs:
            sink.write(f"- **{r.get('source')}**: ${r.get('estimated_usd')} "
                       f"/ ${r.get('limit')} (~{r.get('tokens_est')} token)\n")
        if runs:
            sink.write(f"\nToplam: ${total}\n")
    # CLI override uyarısı (check_cli_overrides.py tarafından index.json'a
    # eklenir): bütçe dosya config değeriyle DEĞİL CLI değeriyle koştuysa
    # tekrarlanabilirlik sapmasını run summary'de görünür yap.
    ov = summary.get("cli_overrides")
    if isinstance(ov, dict) and ov.get("warning"):
        sink.write("\n## ⚠️ Bütçe CLI override uyarısı\n\n")
        for o in ov.get("overrides", []):
            sink.write(f"- **{o.get('key')}**: {o.get('file_value')!r} → "
                       f"{o.get('effective')!r} (CLI verildi)\n")
        sink.write("\n> Bütçe kalkanı bu parametrelerde dosya config "
                   "değeriyle DEĞİL, CLI değeriyle koştu.\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else DEFAULT_PATH
    with summary_sink() as s:
        render(s, path)
    print("Budget summary written to run summary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
