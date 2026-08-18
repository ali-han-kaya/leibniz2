#!/usr/bin/env python3
"""run_summary_budget.py — bütçe kalkanı sonucunu GITHUB_STEP_SUMMARY'ye yaz.

verify.yml'deki 'Budget gate — run summary' adımının inline Python mantığının
standalone hali. budget/index.json (consolidate_budget.py çıktısı) okur; limit
aşımı varsa uyarı, yoksa onay bölümü yazar.

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import sys

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def main() -> None:
    path = "budget/index.json"
    if not os.path.isfile(path):
        with summary_sink() as s:
            s.write("## ⚠️ Bütçe kalkanı: sidecar bulunamadı (verify job'u çalışmadı)\n")
        return
    summary = json.load(open(path))
    failures = summary.get("failures", [])
    with summary_sink() as s:
        if failures:
            s.write("## ⚠️ Bütçe limiti aşıldı\n\n")
            for f in failures:
                src = f.get("source") or "bilinmeyen"
                lim = f.get("limit")
                est = f.get("estimated_usd")
                tok = f.get("tokens_est")
                over = round((est or 0) - (lim or 0), 2)
                s.write(f"- **{src}**: ${est} / ${lim} limiti "
                        f"(+${over} aşım, ~{tok} token)\n")
            s.write(f"\n> Yöntem: `{summary.get('method', '')}`. "
                    f"Fail-closed: P1 bulgusu olarak işaretlendi.\n")
        else:
            runs = summary.get("runs", [])
            total = round(sum(r.get("estimated_usd", 0) or 0 for r in runs), 2)
            s.write("## ✅ Bütçe kalkanı: tüm job'lar limit içinde\n\n")
            for r in runs:
                s.write(f"- **{r.get('source')}**: ${r.get('estimated_usd')} "
                        f"/ ${r.get('limit')} (~{r.get('tokens_est')} token)\n")
            if runs:
                s.write(f"\nToplam: ${total}\n")
        # CLI override uyarısı (check_cli_overrides.py tarafından index.json'a
        # eklenir): bütçe dosya config değeriyle DEĞİL CLI değeriyle koştuysa
        # tekrarlanabilirlik sapmasını run summary'de görünür yap.
        ov = summary.get("cli_overrides")
        if isinstance(ov, dict) and ov.get("warning"):
            s.write("\n## ⚠️ Bütçe CLI override uyarısı\n\n")
            for o in ov.get("overrides", []):
                s.write(f"- **{o.get('key')}**: {o.get('file_value')!r} → "
                        f"{o.get('effective')!r} (CLI verildi)\n")
            s.write("\n> Bütçe kalkanı bu parametrelerde dosya config "
                    "değeriyle DEĞİL, CLI değeriyle koştu.\n")
    print("Budget summary written to run summary.")


if __name__ == "__main__":
    main()
